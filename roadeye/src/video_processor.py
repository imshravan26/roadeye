import time

import cv2
from ultralytics import YOLO

try:
    from .detection import NearMissMonitor, draw_car_detections
    from .lane import detect_lanes
except ImportError:
    from detection import NearMissMonitor, draw_car_detections
    from lane import detect_lanes


def _extract_vehicle_boxes(results, model_names, confidence_threshold, target_classes):
    """Return list of (x1, y1, x2, y2) for all detected vehicles above threshold."""
    boxes = []
    for result in results:
        for box in result.boxes:
            conf = float(box.conf[0])
            cls  = model_names[int(box.cls[0])].lower()
            if cls in target_classes and conf >= confidence_threshold:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                boxes.append((x1, y1, x2, y2))
    return boxes


def process_video(
    model_path: str,
    video_path: str,
    frame_width: int = 1280,
    frame_height: int = 720,
    target_fps: int = 30,
    car_confidence_threshold: float = 0.5,
    window_name: str = "Lane and Car Detection",
    focal_length: float = 1000.0,
    known_car_width_m: float = 2.0,
    near_miss_distance_threshold_m: float = 10.0,
    near_miss_decrease_streak: int = 3,
    target_vehicle_classes: tuple[str, ...] = ("car", "truck", "bus"),
) -> None:
    model = YOLO(model_path)
    capture = cv2.VideoCapture(video_path)

    if not capture.isOpened():
        print(f"Error: Unable to open video file: {video_path}")
        return

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)

    frame_budget = 1.0 / target_fps
    near_miss_monitor = NearMissMonitor(
        distance_alert_threshold_m=near_miss_distance_threshold_m,
        required_decrease_streak=near_miss_decrease_streak,
    )
    target_classes = {name.lower() for name in target_vehicle_classes}
    previous_frame_start = None

    while capture.isOpened():
        start = time.perf_counter()
        frame_dt_s = (
            max(start - previous_frame_start, 1e-3)
            if previous_frame_start is not None
            else frame_budget
        )
        previous_frame_start = start

        has_frame, frame = capture.read()
        if not has_frame:
            break

        resized = cv2.resize(frame, (frame_width, frame_height))

        results = model(resized, verbose=False)
        vehicle_boxes = _extract_vehicle_boxes(
            results, model.names, car_confidence_threshold, target_classes
        )

        lane_frame = detect_lanes(resized, vehicle_boxes=vehicle_boxes)

        output = draw_car_detections(
            lane_frame,
            results,
            model.names,
            car_confidence_threshold,
            focal_length,
            known_car_width_m,
            frame_dt_s,
            near_miss_monitor,
            target_classes,
        )

        cv2.imshow(window_name, output)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        elapsed = time.perf_counter() - start
        sleep_time = frame_budget - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    capture.release()
    cv2.destroyAllWindows()