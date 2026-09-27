from __future__ import annotations

from enum import Enum
from math import atan2, hypot, pi

from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import Vec2


class CircleEvent(Enum):
    UNDO = "undo"
    REDO = "redo"


class CircleRecognizer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._points: list[Vec2] = []
        self._timestamps: list[int] = []
        self._armed = True

    def update(self, point: Vec2, timestamp_ms: int) -> CircleEvent | None:
        if not self._armed:
            return None
        if self._timestamps and timestamp_ms - self._timestamps[0] > self.settings.circle_max_ms:
            self._points = [point]
            self._timestamps = [timestamp_ms]
            return None
        self._points.append(point)
        self._timestamps.append(timestamp_ms)
        if len(self._points) < 16:
            return None

        center = Vec2(
            sum(item.x for item in self._points) / len(self._points),
            sum(item.y for item in self._points) / len(self._points),
        )
        radii = [item.distance_to(center) for item in self._points]
        mean_radius = sum(radii) / len(radii)
        if mean_radius < self.settings.circle_min_radius:
            return None
        if max(abs(radius - mean_radius) for radius in radii) > mean_radius * 0.65:
            return None
        if self._points[0].distance_to(self._points[-1]) > mean_radius * self.settings.circle_close_ratio:
            return None

        turn, consistency = _signed_turn_and_consistency(self._points, center)
        if abs(turn) < 3.5 * pi or consistency < 0.85:
            return None
        self._armed = False
        return CircleEvent.REDO if turn > 0 else CircleEvent.UNDO

    def reset(self) -> None:
        self._points.clear()
        self._timestamps.clear()
        self._armed = True


def signed_turn(points: list[Vec2] | tuple[Vec2, ...], center: Vec2) -> float:
    return _signed_turn_and_consistency(points, center)[0]


def _signed_turn_and_consistency(
    points: list[Vec2] | tuple[Vec2, ...], center: Vec2
) -> tuple[float, float]:
    angles = [atan2(item.y - center.y, item.x - center.x) for item in points]
    deltas: list[float] = []
    for previous, current in zip(angles, angles[1:]):
        delta = current - previous
        while delta > pi:
            delta -= 2 * pi
        while delta < -pi:
            delta += 2 * pi
        if abs(delta) > 1e-6:
            deltas.append(delta)
    if not deltas:
        return 0.0, 0.0
    total = sum(deltas)
    direction = 1 if total >= 0 else -1
    matching = sum(1 for delta in deltas if delta * direction > 0)
    return total, matching / len(deltas)
