import logging
from pathlib import Path

try:
    from .video_processor import process_video
except ImportError:
    from video_processor import process_video


BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = str(BASE_DIR / "weights" / "yolov8n_custom.pt")
VIDEO_PATH = str(BASE_DIR / "video" / "video5.mp4")
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
TARGET_FPS = 30
CAR_CONFIDENCE_THRESHOLD = 0.5
TARGET_VEHICLE_CLASSES = ("car", "truck", "bus")
WINDOW_NAME = "Lane and Car Detection"
FOCAL_LENGTH = 1000.0
KNOWN_CAR_WIDTH_M = 2.0
NEAR_MISS_DISTANCE_THRESHOLD_M = 10.0
NEAR_MISS_DECREASE_STREAK = 3


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    process_video(
        model_path=MODEL_PATH,
        video_path=VIDEO_PATH,
        frame_width=FRAME_WIDTH,
        frame_height=FRAME_HEIGHT,
        target_fps=TARGET_FPS,
        car_confidence_threshold=CAR_CONFIDENCE_THRESHOLD,
        target_vehicle_classes=TARGET_VEHICLE_CLASSES,
        window_name=WINDOW_NAME,
        focal_length=FOCAL_LENGTH,
        known_car_width_m=KNOWN_CAR_WIDTH_M,
        near_miss_distance_threshold_m=NEAR_MISS_DISTANCE_THRESHOLD_M,
        near_miss_decrease_streak=NEAR_MISS_DECREASE_STREAK,
    )


if __name__ == "__main__":
    main()
