"""Static hand-signal classification from one landmark observation."""

from gesture_control.core.config import AppConfig
from gesture_control.core.geometry import (
    FINGER_CHAINS, distance, extended_fingers, palm_scale, wristward_displacement,
)
from gesture_control.core.models import HandObservation, HandSignals, Point


class HandClassifier:
    """Classify hands while preserving pinch hysteresis for this instance only."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._pinches: dict[tuple[str, str], bool] = {}

    def _pinch(self, side: str, finger: str, ratio: float) -> bool:
        key = (side, finger)
        previous = self._pinches.get(key, False)
        active = ratio < (self.config.pinch_open_ratio if previous else self.config.pinch_close_ratio)
        self._pinches[key] = active
        return active

    def classify(self, observation: HandObservation) -> HandSignals:
        points = observation.landmarks
        scale = palm_scale(points)
        index_ratio = distance(points[4], points[8]) / scale
        middle_ratio = distance(points[4], points[12]) / scale
        pinky_ratio = distance(points[4], points[20]) / scale
        palm = Point(
            sum(points[index].x for index in (0, 5, 9, 13, 17)) / 5,
            sum(points[index].y for index in (0, 5, 9, 13, 17)) / 5,
        )
        extended = extended_fingers(points)
        non_thumb_extended = extended - {"thumb"}
        return HandSignals(
            side=observation.side,
            confidence=observation.confidence,
            extended=extended,
            index_tip=points[8],
            palm_center=palm,
            palm_scale=scale,
            pinch_index=self._pinch(observation.side.value, "index", index_ratio),
            pinch_middle=self._pinch(observation.side.value, "middle", middle_ratio),
            pinch_pinky=self._pinch(observation.side.value, "pinky", pinky_ratio),
            # A bent pinch can have zero straight fingers. A closed fist also
            # folds every non-thumb tip wristward of its PIP. Keep this geometric
            # distinction independent of pinch hysteresis: incidental contact in
            # a true fist must still retain left-fist Delete and double-fist priority.
            is_fist=not non_thumb_extended and all(
                wristward_displacement(points, pip, tip) > 0
                for _, pip, tip in FINGER_CHAINS.values()
            ),
            middle_tip=points[12],
            pinky_pinch_point=Point(
                (points[4].x + points[20].x) / 2,
                (points[4].y + points[20].y) / 2,
            ),
            index_pinch_ratio=index_ratio,
            middle_pinch_ratio=middle_ratio,
            pinky_pinch_ratio=pinky_ratio,
        )
