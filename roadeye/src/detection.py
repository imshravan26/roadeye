import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

LOGGER = logging.getLogger(__name__)


def estimate_distance(
    bbox_width: int,
    focal_length: float,
    known_width_m: float,
) -> float:
    if bbox_width <= 0:
        return float("inf")
    return (known_width_m * focal_length) / bbox_width


@dataclass
class _TrackState:
    center: tuple[int, int]
    distance_m: float
    decrease_streak: int
    last_seen_frame: int


class NearMissMonitor:
    def __init__(
        self,
        distance_alert_threshold_m: float = 10.0,
        required_decrease_streak: int = 3,
        max_match_distance_px: float = 120.0,
        min_distance_delta_m: float = 0.05,
        stale_frames: int = 8,
    ) -> None:
        self.distance_alert_threshold_m = distance_alert_threshold_m
        self.required_decrease_streak = required_decrease_streak
        self.max_match_distance_px = max_match_distance_px
        self.min_distance_delta_m = min_distance_delta_m
        self.stale_frames = stale_frames

        self._frame_index = 0
        self._next_track_id = 1
        self._tracks: dict[int, _TrackState] = {}
        self._assigned_tracks: set[int] = set()

    def begin_frame(self) -> None:
        self._frame_index += 1
        self._assigned_tracks.clear()
        cutoff = self._frame_index - self.stale_frames
        self._tracks = {
            track_id: state
            for track_id, state in self._tracks.items()
            if state.last_seen_frame >= cutoff
        }

    def _match_track(self, center: tuple[int, int]) -> int | None:
        best_id = None
        best_distance = float("inf")
        cx, cy = center

        for track_id, state in self._tracks.items():
            if track_id in self._assigned_tracks:
                continue
            dx = cx - state.center[0]
            dy = cy - state.center[1]
            dist_px = math.hypot(dx, dy)
            if dist_px < best_distance and dist_px <= self.max_match_distance_px:
                best_distance = dist_px
                best_id = track_id

        return best_id

    @staticmethod
    def _score_severity(ttc_s: float) -> tuple[int, str]:
        if not math.isfinite(ttc_s):
            return 0, "SAFE"
        if ttc_s <= 1.0:
            return 100, "CRITICAL"
        if ttc_s <= 2.0:
            return 85, "HIGH"
        if ttc_s <= 3.5:
            return 65, "MEDIUM"
        if ttc_s <= 5.0:
            return 45, "LOW"
        return 20, "LOW"

    def evaluate(
        self,
        center: tuple[int, int],
        distance_m: float,
        dt_s: float,
    ) -> tuple[float, int, str, bool, int]:
        track_id = self._match_track(center)
        approach_speed_mps = 0.0
        decrease_streak = 0

        if track_id is None:
            track_id = self._next_track_id
            self._next_track_id += 1
        else:
            prev = self._tracks[track_id]
            distance_drop = prev.distance_m - distance_m
            if distance_drop > self.min_distance_delta_m:
                approach_speed_mps = distance_drop / max(dt_s, 1e-3)
                decrease_streak = prev.decrease_streak + 1

        ttc_s = (
            distance_m / approach_speed_mps
            if approach_speed_mps > 0
            else float("inf")
        )
        score, severity = self._score_severity(ttc_s)
        should_alert = (
            distance_m < self.distance_alert_threshold_m
            and decrease_streak >= self.required_decrease_streak
            and math.isfinite(ttc_s)
        )

        self._tracks[track_id] = _TrackState(
            center=center,
            distance_m=distance_m,
            decrease_streak=decrease_streak,
            last_seen_frame=self._frame_index,
        )
        self._assigned_tracks.add(track_id)

        return ttc_s, score, severity, should_alert, track_id


def draw_car_detections(
    frame: np.ndarray,
    results,
    model_names,
    confidence_threshold: float,
    focal_length: float,
    known_width_m: float,
    frame_dt_s: float,
    near_miss_monitor: NearMissMonitor,
    target_vehicle_classes: set[str],
    alert_sink: list | None = None,
) -> np.ndarray:
    near_miss_monitor.begin_frame()

    for result in results:
        boxes = result.boxes
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = model_names[class_id]

            if class_name not in target_vehicle_classes or confidence < confidence_threshold:
                continue

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(
                frame,
                f"{class_name} {confidence:.2f}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                2,
            )

            distance_m = estimate_distance(x2 - x1, focal_length, known_width_m)
            center = ((x1 + x2) // 2, (y1 + y2) // 2)
            ttc_s, score, severity, should_alert, track_id = near_miss_monitor.evaluate(
                center=center,
                distance_m=distance_m,
                dt_s=frame_dt_s,
            )

            ttc_text = f"{ttc_s:.2f}s" if math.isfinite(ttc_s) else "inf"
            LOGGER.info(
                "Track %d | distance=%.2fm | TTC=%s | severity=%s | score=%d",
                track_id,
                distance_m,
                ttc_text,
                severity,
                score,
            )

            cv2.putText(
                frame,
                f"Distance: {distance_m:.2f}m",
                (x1, y2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 0, 0),
                2,
            )
            cv2.putText(
                frame,
                f"TTC: {ttc_text}",
                (x1, y2 + 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 165, 255),
                2,
            )
            cv2.putText(
                frame,
                f"Risk: {severity} ({score})",
                (x1, y2 + 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 165, 255),
                2,
            )

            if should_alert:
                cv2.putText(
                    frame,
                    f"ALERT {severity}",
                    (x1 + 5, y1 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 0, 255),
                    2,
                )

            # Record clip for ANY severity as long as vehicle is within range.
            # HIGH/CRITICAL require the full should_alert gate (streak + finite TTC).
            # LOW/MEDIUM fire on distance alone — they may not be approaching yet.
            import time as _time
            import math as _math
            _record = False
            if severity in ("HIGH", "CRITICAL"):
                _record = should_alert
            elif severity in ("LOW", "MEDIUM"):
                _record = distance_m < near_miss_monitor.distance_alert_threshold_m

            if _record and alert_sink is not None:
                alert_sink.append({
                    "occurred_at":    int(_time.time()),
                    "vehicle_class":  class_name,
                    "distance_m":     distance_m,
                    "ttc_s":          ttc_s if _math.isfinite(ttc_s) else 0.0,
                    "severity_score": score,
                    "severity_label": severity,
                })

    return frame