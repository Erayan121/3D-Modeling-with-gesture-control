"""Scale-independent geometric helpers for MediaPipe hand landmarks."""

from math import acos, degrees, hypot

from gesture_control.core.models import Point


WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_TIP = 0, 4, 8, 12
FINGER_CHAINS = {
    "index": (5, 6, 8),
    "middle": (9, 10, 12),
    "ring": (13, 14, 16),
    "pinky": (17, 18, 20),
}


def distance(a: Point, b: Point) -> float:
    """Return the Euclidean distance between two normalized image points."""
    return hypot(a.x - b.x, a.y - b.y)


def joint_angle(a: Point, b: Point, c: Point) -> float:
    """Return the angle ABC in degrees, or zero when it is undefined."""
    ab = (a.x - b.x, a.y - b.y)
    cb = (c.x - b.x, c.y - b.y)
    denominator = hypot(*ab) * hypot(*cb)
    if denominator == 0:
        return 0.0
    cosine = max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / denominator))
    return degrees(acos(cosine))


def palm_scale(points: tuple[Point, ...]) -> float:
    """Return a non-zero palm-width reference distance for ratio comparisons."""
    return max(distance(points[5], points[17]), 1e-6)


def wristward_displacement(points: tuple[Point, ...], start: int, end: int) -> float:
    """Project a joint-to-tip vector onto the hand's knuckle-to-wrist axis.

    Positive means curled toward the wrist, negative points beyond the knuckles.
    The dot product uses hand-local geometry and survives image-plane rotation,
    reflection, and translation. A degenerate palm supplies no curl evidence.
    """
    axis_x = points[WRIST].x - sum(points[i].x for i in (5, 9, 13, 17)) / 4
    axis_y = points[WRIST].y - sum(points[i].y for i in (5, 9, 13, 17)) / 4
    length = hypot(axis_x, axis_y)
    if length <= 1e-6:
        return 0.0
    return ((points[end].x - points[start].x) * axis_x
            + (points[end].y - points[start].y) * axis_y) / length


def extended_fingers(points: tuple[Point, ...]) -> frozenset[str]:
    """Classify straight fingers extending away from the wrist."""
    result: set[str] = set()
    for name, (mcp, pip, tip) in FINGER_CHAINS.items():
        if joint_angle(points[mcp], points[pip], points[tip]) >= 155 and wristward_displacement(points, pip, tip) < 0:
            result.add(name)
    if distance(points[THUMB_TIP], points[5]) > 0.55 * palm_scale(points):
        result.add("thumb")
    return frozenset(result)
