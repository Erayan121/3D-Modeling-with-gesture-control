"""Deterministic, anatomically coherent MediaPipe hand fixtures."""

from dataclasses import replace
from math import cos, radians, sin

from gesture_control.core.models import HandObservation, HandSide, Point


FINGER_MCP = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}
FINGER_PIP = {"index": 6, "middle": 10, "ring": 14, "pinky": 18}
FINGER_TIP = {"index": 8, "middle": 12, "ring": 16, "pinky": 20}
TIP_TO_FINGER = {tip: name for name, tip in FINGER_TIP.items()}


def _point_between(start: Point, end: Point, fraction: float) -> Point:
    return Point(
        start.x + (end.x - start.x) * fraction,
        start.y + (end.y - start.y) * fraction,
    )


def hand(
    side: HandSide,
    tips: dict[int, tuple[float, float]],
    timestamp_ms: int = 0,
) -> HandObservation:
    """Build a 21-point hand whose raised fingers are straight and curled ones bent."""
    points = [Point(0.50, 0.80) for _ in range(21)]
    points[0] = Point(0.50, 0.82)
    mcp_points = {
        5: Point(0.43, 0.62),
        9: Point(0.50, 0.60),
        13: Point(0.56, 0.63),
        17: Point(0.62, 0.67),
    }
    for index, point in mcp_points.items():
        points[index] = point

    default_tips = {
        4: (0.40, 0.70),
        8: (0.45, 0.76),
        12: (0.51, 0.75),
        16: (0.57, 0.77),
        20: (0.63, 0.79),
    }
    resolved_tips = default_tips | tips
    points[4] = Point(*resolved_tips[4])

    for tip_index, name in TIP_TO_FINGER.items():
        mcp = points[FINGER_MCP[name]]
        tip = Point(*resolved_tips[tip_index])
        points[tip_index] = tip
        if tip.y < mcp.y:
            # A raised finger is a straight MCP--PIP--tip chain.
            points[FINGER_PIP[name]] = _point_between(mcp, tip, 0.48)
        else:
            # A curled finger bends forward at the PIP and keeps its tip below it.
            points[FINGER_PIP[name]] = Point(mcp.x, mcp.y + 0.065)

    return HandObservation(side, 0.95, tuple(points), timestamp_ms)


def compact_pinch(finger: str, side: HandSide = HandSide.RIGHT) -> HandObservation:
    """Build a compact pinch pose without classifying a finger as extended."""
    points = [
        (.50, .82), (.43, .77), (.39, .70), (.41, .66), (.44, .65),
        (.43, .62), (.43, .685), (.445, .67), (.45, .65),
        (.50, .60), (.50, .665), (.505, .71), (.51, .75),
        (.56, .63), (.56, .695), (.565, .735), (.57, .77),
        (.62, .67), (.62, .735), (.625, .765), (.63, .79),
    ]
    if finger == "middle":
        points[3:5] = [(.46, .65), (.50, .65)]
        points[7:9] = [(.44, .72), (.45, .76)]
        points[11:13] = [(.505, .66), (.51, .65)]
    return HandObservation(side, .95, tuple(Point(x, y) for x, y in points), 0)


def scaled(observation: HandObservation, factor: float) -> HandObservation:
    """Return a uniformly scaled copy around the wrist for ratio-invariance tests."""
    origin = observation.landmarks[0]
    points = tuple(
        Point(
            origin.x + (point.x - origin.x) * factor,
            origin.y + (point.y - origin.y) * factor,
            point.z,
        )
        for point in observation.landmarks
    )
    return HandObservation(observation.side, observation.confidence, points, observation.timestamp_ms)


def rotated(observation: HandObservation, angle_degrees: float) -> HandObservation:
    """Rotate every landmark about the wrist, preserving all local geometry."""
    origin = observation.landmarks[0]
    angle = radians(angle_degrees)
    points = tuple(Point(origin.x + cos(angle) * (p.x - origin.x) - sin(angle) * (p.y - origin.y),
                         origin.y + sin(angle) * (p.x - origin.x) + cos(angle) * (p.y - origin.y), p.z)
                   for p in observation.landmarks)
    return replace(observation, landmarks=points)
