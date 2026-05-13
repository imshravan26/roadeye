import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = "https://omchillure-dlproj.hf.space"

st.set_page_config(
    page_title="RoadEye - Live Detection",
    layout="wide",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
    background-color: #080b10;
    color: #f4efe6;
}
.stApp { background: #080b10; }

.main-title {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 3.2rem;
    letter-spacing: -0.03em;
    background: linear-gradient(135deg, #f8fafc 0%, #f59e0b 42%, #ef4444 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.1;
    margin-bottom: 0.2rem;
}
.sub-title {
    font-family: 'Space Mono', monospace;
    font-size: 0.78rem;
    color: #7c8798;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 2rem;
}
.status-badge {
    display: inline-block;
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    padding: 0.3rem 0.8rem;
    border-radius: 20px;
    margin-bottom: 1rem;
}
.status-running { background:#0d2e1a; color:#f59e0b; border:1px solid #f59e0b40; }
.status-idle    { background:#243244; color:#7c8798; border:1px solid #334155; }
.status-failed  { background:#2e0d0d; color:#ff4444; border:1px solid #ff444440; }

.divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #f59e0b55, transparent);
    margin: 1.2rem 0;
}
.stat-card {
    background: #101722;
    border: 1px solid #243244;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
}
.stat-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    color: #7c8798;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}
.stat-value {
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    font-size: 1.3rem;
    color: #f59e0b;
}

.incident-card {
    background: #0c121c;
    border: 1px solid #243244;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.6rem;
    border-left: 3px solid #7c8798;
}
.incident-card.CRITICAL { border-left-color: #ef4444; }
.incident-card.HIGH     { border-left-color: #f97316; }
.incident-card.MEDIUM   { border-left-color: #eab308; }

.incident-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.4rem;
}
.severity-pill {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.15rem 0.6rem;
    border-radius: 20px;
    letter-spacing: 0.1em;
}
.pill-CRITICAL { background:#ef444422; color:#ef4444; border:1px solid #ef444440; }
.pill-HIGH     { background:#f9731622; color:#f97316; border:1px solid #f9731640; }
.pill-MEDIUM   { background:#eab30822; color:#eab308; border:1px solid #eab30840; }
.pill-LOW      { background:#22c55e22; color:#22c55e; border:1px solid #22c55e40; }

.incident-meta {
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem;
    color: #7c8798;
    margin-bottom: 0.5rem;
}
.incident-cid {
    font-family: 'Space Mono', monospace;
    font-size: 0.6rem;
    color: #64748b;
    word-break: break-all;
}
.incident-cid a { color: #38bdf8; text-decoration: none; }
.incident-cid a:hover { text-decoration: underline; }
.tx-link {
    display: inline-block;
    font-family: 'Space Mono', monospace;
    font-size: 0.62rem;
    color: #080b10;
    background: #f59e0b;
    border-radius: 6px;
    padding: 0.28rem 0.5rem;
    text-decoration: none;
    margin-top: 0.45rem;
    font-weight: 700;
}
.tx-link:hover { opacity: 0.85; text-decoration: none; }

.stButton > button {
    background: linear-gradient(135deg, #f59e0b, #ef4444) !important;
    color: #080b10 !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    border: none !important;
    border-radius: 8px !important;
    width: 100% !important;
}
.stButton > button:hover { opacity: 0.85 !important; }
</style>
""",
    unsafe_allow_html=True,
)

if "status" not in st.session_state:
    st.session_state.status = "idle"
if "clips" not in st.session_state:
    st.session_state.clips = []
if "incidents" not in st.session_state:
    st.session_state.incidents = []
if "folder" not in st.session_state:
    st.session_state.folder = None

col_left, col_mid, col_right = st.columns([1, 2.2, 1.1], gap="large")

with col_left:
    st.markdown('<div class="main-title">RoadEye</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Near-Miss Evidence Console</div>', unsafe_allow_html=True
    )
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drop a road video",
        type=["mp4", "avi", "mov", "mkv"],
    )
    st.markdown("<br>", unsafe_allow_html=True)

    start_btn = st.button("▶  Start Detection", disabled=uploaded_file is None)
    stop_btn = st.button("■  Stop", disabled="video_id" not in st.session_state)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    status_placeholder = st.empty()
    info_placeholder = st.empty()

    status_class = {
        "idle": "status-idle",
        "running": "status-running",
        "failed": "status-failed",
        "completed": "status-idle",
    }.get(st.session_state.status, "status-idle")

    status_placeholder.markdown(
        f'<span class="status-badge {status_class}">⬤ &nbsp;{st.session_state.status.upper()}</span>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown(
        """
    <div class="stat-card">
        <div class="stat-label">Model</div>
        <div class="stat-value" style="font-size:0.95rem;color:#f97316;">YOLOv8n</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Targets</div>
        <div class="stat-value" style="font-size:0.9rem;color:#38bdf8;">Car · Truck · Bus</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Chain</div>
        <div class="stat-value" style="font-size:0.9rem;color:#f59e0b;">Solana Devnet</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Storage</div>
        <div class="stat-value" style="font-size:0.9rem;color:#f4efe6;">IPFS · Pinata</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col_mid:
    stream_placeholder = st.empty()
    stream_placeholder.markdown(
        """
    <div style="background:#0c121c;border:1px solid #334155;border-radius:10px;height:500px;
        display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1rem;">
        <div style="font-size:3rem;opacity:0.15;">🎥</div>
        <div style="font-family:'Space Mono',monospace;font-size:0.72rem;color:#64748b;
            letter-spacing:0.15em;text-transform:uppercase;">Upload a video and press Start</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col_right:
    st.markdown(
        '<div class="stat-label" style="margin-bottom:0.8rem;">📁 &nbsp;IPFS CLIPS</div>',
        unsafe_allow_html=True,
    )
    clips_placeholder = st.empty()
    folder_placeholder = st.empty()
    incidents_title_placeholder = st.empty()
    incidents_placeholder = st.empty()

    def render_clips(clips: list, folder: str | None = None, incidents: list | None = None):
        if folder:
            folder_placeholder.markdown(
                f'<div class="incident-cid" style="color:#7c8798;margin-bottom:0.6rem;">'
                f"📂 {folder}</div>",
                unsafe_allow_html=True,
            )

        if not clips:
            clips_placeholder.markdown(
                """
            <div style="font-family:'Space Mono',monospace;font-size:0.65rem;color:#64748b;
                text-align:center;padding:2rem 0;">No clips yet — waiting…</div>
            """,
                unsafe_allow_html=True,
            )
            return

        SEV_COLORS = {
            "CRITICAL": "#ef4444",
            "HIGH": "#f97316",
            "MEDIUM": "#eab308",
            "LOW": "#22c55e",
        }

        incidents_by_clip_id = {
            item.get("clip_id"): item
            for item in (incidents or [])
            if item.get("clip_id")
        }

        with clips_placeholder.container():
            for row_start in range(0, len(clips), 2):
                cols = st.columns(2)
                for col, clip in zip(cols, clips[row_start:row_start + 2]):
                    with col:
                        sev = (clip.get("severity") or "LOW").upper()
                        cid = clip.get("cid", "")
                        url = clip.get("ipfs_url", f"https://gateway.pinata.cloud/ipfs/{cid}")
                        incident = incidents_by_clip_id.get(clip.get("clip_id"), {})
                        tx = incident.get("tx") or ""
                        explorer_url = f"https://explorer.solana.com/tx/{tx}?cluster=devnet"
                        vehicle = clip.get("vehicle", "Vehicle").capitalize()
                        ts = str(clip.get("occurred_at") or "")[:19] or "-"

                        st.markdown(f"**{sev}** | {vehicle}")
                        st.caption(f"{ts}")
                        st.code(cid or "CID pending", language=None)
                        st.markdown(f"[Download / View Clip - Pinata Gateway]({url})")
                        st.markdown(f"[Download Clip - inbrowser.link](https://{cid}.ipfs.inbrowser.link)")
                        st.markdown(f"[Backup Gateway - IPFS.io](https://ipfs.io/ipfs/{cid})")
                        if tx:
                            st.markdown(f"[View Solana TX]({explorer_url})")
                        else:
                            st.caption("No Solana TX")
            return

    render_clips(
        st.session_state.get("clips", []),
        st.session_state.get("folder"),
        st.session_state.get("incidents", []),
    )

    def render_incidents(incidents: list):
        incidents_title_placeholder.markdown(
            '<div class="stat-label" style="margin:1.2rem 0 0.8rem;">ON-CHAIN INCIDENTS</div>',
            unsafe_allow_html=True,
        )

        if not incidents:
            incidents_placeholder.markdown(
                """
            <div style="font-family:'Space Mono',monospace;font-size:0.65rem;color:#64748b;
                text-align:center;padding:1.4rem 0;">No Solana transactions yet</div>
            """,
                unsafe_allow_html=True,
            )
            return

        html = ""
        tx_incidents = [item for item in incidents if item.get("tx")]
        if not tx_incidents:
            incidents_placeholder.markdown(
                """
            <div style="font-family:'Space Mono',monospace;font-size:0.65rem;color:#64748b;
                text-align:center;padding:1.4rem 0;">No Solana transactions yet</div>
            """,
                unsafe_allow_html=True,
            )
            return

        for incident in list(reversed(tx_incidents))[:6]:
            sev = (incident.get("severity_label") or "LOW").upper()
            tx = incident.get("tx") or ""
            cid = incident.get("clip_cid") or ""
            vehicle = incident.get("vehicle_class") or "vehicle"
            distance = incident.get("distance_m", "")
            ttc = incident.get("ttc_s", "")
            onchain = "YES" if incident.get("onchain") else "NO"
            explorer_url = f"https://explorer.solana.com/tx/{tx}?cluster=devnet"
            ipfs_url = f"https://gateway.pinata.cloud/ipfs/{cid}" if cid else ""

            html += f"""
            <div class="incident-card {sev}">
                <div class="incident-top">
                    <span class="severity-pill pill-{sev}">{sev}</span>
                    <span class="incident-meta">ONCHAIN {onchain}</span>
                </div>
                <div class="incident-meta">
                    {vehicle} | {distance}m | TTC {ttc}s
                </div>
                <div class="incident-cid">
                    CID: <a href="{ipfs_url}" target="_blank">{cid or "pending"}</a>
                </div>
            """
            if tx:
                html += f'<a class="tx-link" href="{explorer_url}" target="_blank">View Solana TX</a>'
            html += "</div>"

        incidents_placeholder.markdown(html, unsafe_allow_html=True)

    render_incidents(st.session_state.get("incidents", []))


# ── Button handlers ───────────────────────────────────────────────────────────

if start_btn and uploaded_file is not None:
    with st.spinner("Uploading video..."):
        try:
            res = requests.post(
                f"{BACKEND_URL}/upload",
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        uploaded_file.type,
                    )
                },
                timeout=60,
            )
            res.raise_for_status()
            data = res.json()
            video_id = data["video_id"]
            st.session_state.video_id = video_id
            st.session_state.folder = (
                data.get("folder") or f"{data.get('camera_id', 'cam')}/{video_id}"
            )
            requests.post(f"{BACKEND_URL}/start/{video_id}", timeout=10)
            st.session_state.status = "running"
            st.session_state.clips = []
            st.session_state.incidents = []
            st.rerun()
        except Exception as e:
            st.session_state.status = "failed"
            info_placeholder.error(f"Error: {e}")

if stop_btn and "video_id" in st.session_state:
    try:
        requests.post(f"{BACKEND_URL}/stop/{st.session_state.video_id}", timeout=5)
    except Exception:
        pass
    st.session_state.status = "idle"
    del st.session_state["video_id"]
    st.rerun()


# ── Live streaming loop ───────────────────────────────────────────────────────

if st.session_state.get("status") == "running" and "video_id" in st.session_state:
    video_id = st.session_state.video_id
    stream_url = f"{BACKEND_URL}/stream/{video_id}"

    with col_mid:
        stream_placeholder.markdown(
            f"""<div style="border-radius:14px;overflow:hidden;border:1px solid #334155;">
                <img src="{stream_url}" style="width:100%;display:block;border-radius:14px;" />
            </div>""",
            unsafe_allow_html=True,
        )

    status_placeholder.markdown(
        '<span class="status-badge status-running">⬤ &nbsp;RUNNING</span>',
        unsafe_allow_html=True,
    )

    # Check job completion
    try:
        status_res = requests.get(f"{BACKEND_URL}/status/{video_id}", timeout=3)
        job_status = status_res.json().get("status", "running")
        if job_status in ("completed", "failed"):
            try:
                clip_res = requests.get(f"{BACKEND_URL}/clips/{video_id}", timeout=10)
                payload = clip_res.json()
                st.session_state.clips = payload.get("clips", [])
                st.session_state.folder = payload.get("folder", st.session_state.folder)
            except Exception:
                pass
            try:
                incident_res = requests.get(f"{BACKEND_URL}/incidents", timeout=10)
                st.session_state.incidents = incident_res.json().get("incidents", [])
            except Exception:
                pass
            st.session_state.status = job_status
            st.rerun()
    except Exception:
        pass

    # Poll for new clips every ~9 s (every 3rd rerun × 3 s sleep)
    poll_counter = st.session_state.get("poll_counter", 0) + 1
    st.session_state.poll_counter = poll_counter

    if poll_counter % 3 == 1:  # fetch on 1st run then every ~9 s
        try:
            clip_res = requests.get(f"{BACKEND_URL}/clips/{video_id}", timeout=10)
            payload = clip_res.json()
            st.session_state.clips = payload.get("clips", [])
            st.session_state.folder = payload.get("folder", st.session_state.folder)
        except Exception:
            pass
        try:
            incident_res = requests.get(f"{BACKEND_URL}/incidents", timeout=10)
            st.session_state.incidents = incident_res.json().get("incidents", [])
        except Exception:
            pass

    render_clips(st.session_state.clips, st.session_state.folder, st.session_state.incidents)
    render_incidents(st.session_state.incidents)

    time.sleep(3)
    st.rerun()



