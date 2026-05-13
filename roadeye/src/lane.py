import cv2
import numpy as np
from collections import deque


_left_buf:  deque = deque(maxlen=8)
_right_buf: deque = deque(maxlen=8)


def region_of_interest(img: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    mask = np.zeros_like(img)
    cv2.fillPoly(mask, vertices, 255)
    return cv2.bitwise_and(img, mask)


def draw_lane_polygon(
    frame: np.ndarray,
    left_line: tuple[int, int, int, int],
    right_line: tuple[int, int, int, int],
    color: tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    overlay = np.zeros_like(frame)
    poly_points = np.array(
        [[
            (left_line[0], left_line[1]),
            (left_line[2], left_line[3]),
            (right_line[2], right_line[3]),
            (right_line[0], right_line[1]),
        ]],
        dtype=np.int32,
    )
    cv2.fillPoly(overlay, poly_points, color)
    return cv2.addWeighted(frame, 0.8, overlay, 0.5, 0.0)


def detect_lanes(frame: np.ndarray, vehicle_boxes: list | None = None) -> np.ndarray:
    global _left_buf, _right_buf

    height, width = frame.shape[:2]
    roi_vertices = np.array(
        [[(0, height), (width // 2, height // 2), (width, height)]], dtype=np.int32
    )

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    cropped = region_of_interest(edges, roi_vertices)

    lines = cv2.HoughLinesP(
        cropped,
        rho=6,
        theta=np.pi / 60,
        threshold=160,
        minLineLength=40,
        maxLineGap=25,
    )

    max_y = height
    min_y = int(height * 3 / 5)

    left_x: list[int] = []
    left_y: list[int] = []
    right_x: list[int] = []
    right_y: list[int] = []

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 == x1:
                continue
            slope = (y2 - y1) / (x2 - x1)
            if abs(slope) < 0.5 or abs(slope) > 2.0:
                continue
            if slope < 0 and max(x1, x2) < width * 0.7:
                left_x.extend([x1, x2])
                left_y.extend([y1, y2])
            elif slope > 0 and min(x1, x2) > width * 0.3:
                right_x.extend([x1, x2])
                right_y.extend([y1, y2])

    left_start = left_end = None
    right_start = right_end = None

    if left_x and left_y:
        left_fit = np.poly1d(np.polyfit(left_y, left_x, deg=1))
        left_start = int(left_fit(max_y))
        left_end   = int(left_fit(min_y))

    if right_x and right_y:
        right_fit = np.poly1d(np.polyfit(right_y, right_x, deg=1))
        right_start = int(right_fit(max_y))
        right_end   = int(right_fit(min_y))

    if left_start is not None and right_start is not None:
        if left_start >= right_start or left_end >= right_end:
            left_start = left_end = right_start = right_end = None

    if left_start is not None:
        _left_buf.append((left_start, left_end))
    if right_start is not None:
        _right_buf.append((right_start, right_end))

    if not _left_buf or not _right_buf:
        return frame

    left_start  = int(np.mean([v[0] for v in _left_buf]))
    left_end    = int(np.mean([v[1] for v in _left_buf]))
    right_start = min(int(np.mean([v[0] for v in _right_buf])), int(width * 0.80))
    right_end   = int(np.mean([v[1] for v in _right_buf]))

    draw_top_y = min_y
    if vehicle_boxes:
        lane_cx1 = min(left_start, right_start)
        lane_cx2 = max(left_start, right_start)
        for (bx1, by1, bx2, by2) in vehicle_boxes:
            box_cx = (bx1 + bx2) // 2
            if lane_cx1 <= box_cx <= lane_cx2 and by1 > draw_top_y:
                draw_top_y = by1

    return draw_lane_polygon(
        frame,
        (left_start, max_y, left_end, draw_top_y),
        (right_start, max_y, right_end, draw_top_y),
    )