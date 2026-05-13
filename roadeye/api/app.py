import os
import sys
import subprocess
import tempfile
import uuid

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
import logging
import concurrent.futures
import threading
import time

import cv2
import requests
from flask import Flask, Response, jsonify, request
from solana_client import submit_to_solana
from ultralytics import YOLO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from detection import NearMissMonitor, draw_car_detections
from lane import detect_lanes
from pinata_client import PinataClient, PUBLIC_GATEWAY

RUNTIME_DATA_DIR = os.getenv(
    "RUNTIME_DATA_DIR", os.path.join(tempfile.gettempdir(), "roadsense")
)
UPLOAD_FOLDER = os.path.join(RUNTIME_DATA_DIR, "uploads")
CLIP_FOLDER   = os.path.join(RUNTIME_DATA_DIR, "clips")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CLIP_FOLDER, exist_ok=True)

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "src", "weights", "yolov8n_custom.pt"
)
FRAME_WIDTH                  = 640
FRAME_HEIGHT                 = 360
TARGET_FPS                   = 15
CAR_CONFIDENCE_THRESHOLD     = 0.5
TARGET_VEHICLE_CLASSES       = {"car", "truck", "bus"}
FOCAL_LENGTH                 = 1000.0
KNOWN_CAR_WIDTH_M            = 2.0
NEAR_MISS_DISTANCE_THRESHOLD_M = 30.0
NEAR_MISS_DECREASE_STREAK    = 3
CLIP_PRE_ROLL_FRAMES  = 150  
CLIP_POST_ROLL_FRAMES = 150  
PINATA_JWT = os.getenv("PINATA_JWT", "")
CAMERA_ID  = os.getenv("CAMERA_ID", "cam-01")

_upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ipfs-upload")

logging.basicConfig(level=logging.WARNING)           # silence everything by default
logging.getLogger("__main__").setLevel(logging.DEBUG)        # app.py logs (Pinata/Solana)
logging.getLogger("solana_client").setLevel(logging.DEBUG)   # solana_client.py logs
logging.getLogger("pinata_client").setLevel(logging.DEBUG)   # pinata_client.py logs (if any)
logging.getLogger("werkzeug").setLevel(logging.INFO)         # keep Flask HTTP request lines
logging.getLogger("detection").setLevel(logging.WARNING)     # silence Track/TTC spam
logging.getLogger("ultralytics").setLevel(logging.WARNING)   # silence YOLO output
LOGGER = logging.getLogger(__name__)

app   = Flask(__name__)
jobs: dict[str, dict] = {}
job_clips: dict[str, list] = {} 
recorded_incidents: list = []
model = None
model_lock = threading.Lock()


def get_model():
    global model
    with model_lock:
        if model is None:
            model = YOLO(MODEL_PATH)
    return model


def _upload_and_record(clip_path: str, incident_meta: dict, video_id: str) -> None:
    """Upload clip to IPFS; submit to Solana for HIGH/CRITICAL; track locally."""
    try:
        severity           = incident_meta.get("severity_label", "").upper()
        onchain_severities = {"HIGH", "CRITICAL"}
        clip_cid = ""
        tx       = ""
        clip_id  = incident_meta.get("clip_id", uuid.uuid4().hex)

        LOGGER.info("━━━ CLIP READY  clip_id=%s  severity=%s  path=%s",
                    clip_id, severity, clip_path)

        if not PINATA_JWT:
            LOGGER.warning("⚠ PINATA_JWT not set — skipping IPFS upload.")
        else:
            LOGGER.info("⬆ PINATA UPLOAD START  name=%s/%s/%s", CAMERA_ID, video_id, clip_id)
            pinata = PinataClient(jwt_token=PINATA_JWT)
            result = pinata.upload_clip(
                clip_path,
                name=f"{CAMERA_ID}/{video_id}/{clip_id}",
                keyvalues={
                    "camera_id":   CAMERA_ID,
                    "video_id":    video_id,
                    "clip_id":     clip_id,
                    "severity":    severity,
                    "vehicle":     incident_meta["vehicle_class"],
                    "occurred_at": str(incident_meta["occurred_at"]),
                },
            )
            clip_cid = result.ipfs_cid
            ipfs_url = f"{PUBLIC_GATEWAY}/{clip_cid}"
            LOGGER.info("✅ PINATA UPLOAD OK  cid=%s  size=%s bytes  severity=%s",
                        clip_cid, result.size_bytes, severity)
            LOGGER.info("🔗 IPFS URL: %s", ipfs_url)

            job_clips.setdefault(video_id, []).append({
                "clip_id":     clip_id,
                "cid":         clip_cid,
                "ipfs_url":    ipfs_url,
                "severity":    severity,
                "occurred_at": str(incident_meta.get("occurred_at", "")),
                "vehicle":     incident_meta.get("vehicle_class", ""),
            })

            if severity in onchain_severities:
                LOGGER.info("⛓  SOLANA SUBMIT START  cid=%s  severity=%s", clip_cid, severity)
                tx = submit_to_solana(incident_meta, clip_cid) or ""
                if tx:
                    LOGGER.info("✅ SOLANA TX OK  sig=%s", tx)
                    LOGGER.info("🔗 Explorer: https://explorer.solana.com/tx/%s?cluster=devnet", tx)
                else:
                    LOGGER.error("✗  SOLANA TX FAILED — no signature returned")
            else:
                LOGGER.info("📦 Severity=%s — IPFS only, not on-chain.", severity)

        recorded_incidents.append(
            {
                "clip_id":        clip_id,
                "occurred_at":    incident_meta["occurred_at"],
                "vehicle_class":  incident_meta["vehicle_class"],
                "severity_label": incident_meta["severity_label"],
                "severity_score": incident_meta["severity_score"],
                "distance_m":     round(incident_meta["distance_m"], 2),
                "ttc_s":          round(incident_meta["ttc_s"], 2),
                "clip_cid":       clip_cid,
                "onchain":        severity in onchain_severities,
                "tx":             tx,
            }
        )
        LOGGER.info("📝 Incident recorded  clip_id=%s  cid=%s  tx=%s", clip_id, clip_cid, tx or "—")

    except Exception as e:
        LOGGER.error("✗ Upload/record FAILED  clip_id=%s  error=%s",
                     incident_meta.get("clip_id", "?"), e, exc_info=True)
    finally:
        try:
            os.remove(clip_path)
        except Exception:
            pass


def _save_clip(frames: list, fps: int, path: str) -> None:
    if not frames:
        return
    h, w = frames[0].shape[:2]
    raw_path = f"{path}.raw.mp4"
    out = cv2.VideoWriter(raw_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        out.write(f)
    out.release()

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                raw_path,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.remove(raw_path)
    except Exception as e:
        LOGGER.warning("H.264 clip transcode failed, using raw MP4: %s", e)
        os.replace(raw_path, path)


def generate_frames(video_path: str, job_id: str):
    jobs[job_id]["status"] = "running"
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        jobs[job_id]["status"] = "failed"
        return

    yolo = get_model()
    frame_budget = 1.0 / TARGET_FPS
    near_miss_monitor = NearMissMonitor(
        distance_alert_threshold_m=NEAR_MISS_DISTANCE_THRESHOLD_M,
        required_decrease_streak=NEAR_MISS_DECREASE_STREAK,
    )
    previous_frame_start = None

    from collections import deque
    raw_buffer: deque        = deque(maxlen=CLIP_PRE_ROLL_FRAMES)
    post_roll_frames: list   = []
    post_roll_remaining      = 0
    active_incident: dict | None = None

    while cap.isOpened():
        if jobs.get(job_id, {}).get("stop"):
            break

        start = time.perf_counter()
        frame_dt_s = (
            max(start - previous_frame_start, 1e-3)
            if previous_frame_start is not None
            else frame_budget
        )
        previous_frame_start = start

        has_frame, frame = cap.read()
        if not has_frame:
            break

        resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        raw_buffer.append(resized.copy())

        results      = yolo(resized, verbose=False)
        vehicle_boxes = [
            tuple(map(int, box.xyxy[0]))
            for result in results
            for box in result.boxes
            if yolo.names[int(box.cls[0])].lower() in TARGET_VEHICLE_CLASSES
            and float(box.conf[0]) >= CAR_CONFIDENCE_THRESHOLD
        ]
        lane_frame  = detect_lanes(resized, vehicle_boxes=vehicle_boxes)
        frame_alerts = []
        output = draw_car_detections(
            lane_frame,
            results,
            yolo.names,
            CAR_CONFIDENCE_THRESHOLD,
            FOCAL_LENGTH,
            KNOWN_CAR_WIDTH_M,
            frame_dt_s,
            near_miss_monitor,
            TARGET_VEHICLE_CLASSES,
            alert_sink=frame_alerts,
        )

        # Post-roll accumulation — fire upload immediately once complete
        if post_roll_remaining > 0:
            post_roll_frames.append(resized.copy())
            post_roll_remaining -= 1
            if post_roll_remaining == 0 and active_incident:
                clip_path   = os.path.join(
                    CLIP_FOLDER, f"incident_{active_incident['clip_id']}.mp4"
                )
                clip_frames = list(raw_buffer) + post_roll_frames
                _save_clip(clip_frames, TARGET_FPS, clip_path)
                # Fire-and-forget upload in the thread pool — does NOT block the stream
                _upload_executor.submit(
                    _upload_and_record, clip_path, active_incident, job_id
                )
                post_roll_frames = []
                active_incident  = None

        for alert in frame_alerts:
            if active_incident is None and post_roll_remaining == 0:
                if alert["severity_label"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                    active_incident            = dict(alert)
                    active_incident["clip_id"] = uuid.uuid4().hex
                    post_roll_remaining        = CLIP_POST_ROLL_FRAMES
                    LOGGER.info(
                        "Alert triggered — capturing clip for %s (clip_id=%s)",
                        alert["severity_label"],
                        active_incident["clip_id"],
                    )

        _, buffer = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )

        elapsed    = time.perf_counter() - start
        sleep_time = frame_budget - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    cap.release()
    jobs[job_id]["status"] = "completed"


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in {".mp4", ".avi", ".mov", ".mkv"}:
        return jsonify({"error": "Invalid file type"}), 400

    video_id  = uuid.uuid4().hex[:8]
    save_path = os.path.join(UPLOAD_FOLDER, f"{video_id}{ext}")
    f.save(save_path)

    jobs[video_id] = {
        "status":    "queued",
        "path":      save_path,
        "stop":      False,
        "camera_id": CAMERA_ID,
    }
    return jsonify({
        "video_id":  video_id,
        "camera_id": CAMERA_ID,
        "folder":    f"{CAMERA_ID}/{video_id}",
        "message":   "upload successful",
    })


@app.route("/start/<video_id>", methods=["POST"])
def start(video_id):
    job = jobs.get(video_id)
    if not job:
        return jsonify({"error": "Unknown video_id"}), 404
    job["status"] = "running"
    job["stop"] = False
    return jsonify({"video_id": video_id, "status": "running"})


@app.route("/stream/<video_id>")
def stream(video_id):
    job = jobs.get(video_id)
    if not job:
        return jsonify({"error": "Unknown video_id"}), 404
    return Response(
        generate_frames(job["path"], video_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/stop/<video_id>", methods=["POST"])
def stop(video_id):
    job = jobs.get(video_id)
    if not job:
        return jsonify({"error": "Unknown video_id"}), 404
    job["stop"] = True
    return jsonify({"video_id": video_id, "status": "stopped"})


@app.route("/status/<video_id>")
def status(video_id):
    job = jobs.get(video_id)
    if not job:
        return jsonify({"error": "Unknown video_id"}), 404
    return jsonify({"video_id": video_id, "status": job["status"]})


@app.route("/clips/<video_id>")
def get_clips(video_id):
    """Return all clips uploaded for this video (tracked locally after upload)."""
    if video_id not in jobs:
        return jsonify({"error": "Unknown video_id"}), 404

    clips = job_clips.get(video_id, [])
    LOGGER.info("📂 /clips/%s  returning %d clip(s)", video_id, len(clips))
    return jsonify({
        "folder": f"{CAMERA_ID}/{video_id}",
        "clips":  clips,
    })


@app.route("/clip/<cid>")
def proxy_ipfs_clip(cid):
    """Proxy an IPFS clip so browsers can play it from the same backend origin."""
    if not cid:
        return jsonify({"error": "CID is required"}), 400

    source_url = f"{PUBLIC_GATEWAY}/{cid}"
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]

    try:
        upstream = requests.get(source_url, headers=headers, stream=True, timeout=30)
        upstream.raise_for_status()
    except Exception as e:
        LOGGER.error("IPFS clip proxy failed cid=%s error=%s", cid, e)
        return jsonify({"error": "Unable to fetch IPFS clip", "cid": cid}), 502

    response_headers = {
        "Content-Type": upstream.headers.get("Content-Type", "video/mp4"),
        "Accept-Ranges": upstream.headers.get("Accept-Ranges", "bytes"),
        "Cache-Control": "public, max-age=300",
    }
    for header in ("Content-Length", "Content-Range"):
        if upstream.headers.get(header):
            response_headers[header] = upstream.headers[header]

    return Response(
        upstream.iter_content(chunk_size=1024 * 256),
        status=upstream.status_code,
        headers=response_headers,
        direct_passthrough=True,
    )


@app.route("/incidents")
def get_incidents():
    return jsonify({"incidents": recorded_incidents})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
        threaded=True,
    )
