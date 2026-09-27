from __future__ import annotations

from collections.abc import Callable
from math import hypot
from threading import RLock
from typing import Any

from gesture_control.core.classifier import HandClassifier
from gesture_control.core.config import AppConfig
from gesture_control.core.geometry import FINGER_CHAINS, palm_scale, wristward_displacement
from gesture_control.core.models import HandObservation, HandSide
from gesture_control.vision.camera import CameraSource
from gesture_control.vision.tracker import HandTracker
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import TrackedHand, TrackingSnapshot


CameraFactory = Callable[[int], Any]
TrackerFactory = Callable[[AppConfig, Callable[[tuple[HandObservation, ...], int], None]], Any]
ClassifierFactory = Callable[[AppConfig], Any]


class TrackingService:
    """Owns restartable camera/tracker instances and publishes only latest state."""

    def __init__(
        self,
        settings: Settings,
        *,
        camera_factory: CameraFactory = CameraSource,
        tracker_factory: TrackerFactory | None = None,
        classifier_factory: ClassifierFactory = HandClassifier,
    ) -> None:
        self.settings = settings
        self._camera_factory = camera_factory
        self._tracker_factory = tracker_factory or self._create_tracker
        self._classifier_factory = classifier_factory
        self.camera: Any | None = None
        self.tracker: Any | None = None
        self.classifier: Any | None = None
        self.error: Exception | None = None
        self.last_sequence = -1
        self.pending_count = 0
        self.stable = False
        self._stable_since_ms: int | None = None
        self._observations: tuple[HandObservation, ...] = ()
        self._observation_timestamp_ms = -1
        self._running = False
        self._lock = RLock()

    @staticmethod
    def _create_tracker(config: AppConfig, callback):
        return HandTracker(config, on_result=callback)

    @property
    def is_open(self) -> bool:
        return bool(self.camera is not None and getattr(self.camera, "is_open", True))

    @property
    def running(self) -> bool:
        return self._running

    def open(self, index: int) -> None:
        if self.camera is not None:
            self.close()
        self.error = None
        self.camera = self._camera_factory(index)
        self.camera.open()

    def start(self) -> None:
        if self.camera is None:
            raise RuntimeError("camera must be open before tracking starts")
        if self._running:
            return
        config = self._legacy_config()
        self.classifier = self._classifier_factory(config)
        self.tracker = self._tracker_factory(config, self.accept)
        self._running = True
        self.last_sequence = -1
        self.stable = False
        self._stable_since_ms = None

    def accept(self, observations: tuple[HandObservation, ...], timestamp_ms: int) -> None:
        with self._lock:
            if not self._running or timestamp_ms < self._observation_timestamp_ms:
                return
            strongest: dict[HandSide, HandObservation] = {}
            for observation in observations:
                previous = strongest.get(observation.side)
                if previous is None or observation.confidence > previous.confidence:
                    strongest[observation.side] = observation
            self._observations = tuple(strongest.values())
            self._observation_timestamp_ms = timestamp_ms

    def poll(self, now_ms: int) -> TrackingSnapshot:
        if not self._running:
            return TrackingSnapshot(now_ms, {}, False)
        camera_error = getattr(self.camera, "error", None)
        tracker_error = getattr(self.tracker, "error", None)
        if camera_error is not None or tracker_error is not None:
            self._fail(camera_error or tracker_error)
            return TrackingSnapshot(now_ms, {}, False)

        latest = self.camera.read_latest()
        if latest is not None and latest[0] != self.last_sequence:
            self.last_sequence = latest[0]
            self.tracker.submit(latest[1], latest[2])

        with self._lock:
            observations = self._observations
        hands = {
            observation.side: self._tracked_hand(observation)
            for observation in observations
        }
        fresh = bool(hands) and all(
            0 <= now_ms - hand.timestamp_ms <= 100 for hand in hands.values()
        )
        self._update_stability(fresh, now_ms)
        return TrackingSnapshot(now_ms, hands if fresh else {}, fresh)

    def stop(self) -> None:
        tracker, self.tracker = self.tracker, None
        self._running = False
        self.classifier = None
        self.stable = False
        self._stable_since_ms = None
        with self._lock:
            self._observations = ()
            self._observation_timestamp_ms = -1
        if tracker is not None:
            tracker.close()

    def close(self) -> None:
        camera, self.camera = self.camera, None
        if camera is not None:
            camera.close()

    def _fail(self, error: Exception) -> None:
        self.error = error
        try:
            self.stop()
        finally:
            self.close()

    def _update_stability(self, fresh: bool, now_ms: int) -> None:
        if not fresh:
            self._stable_since_ms = None
            self.stable = False
            return
        if self._stable_since_ms is None:
            self._stable_since_ms = now_ms
        self.stable = now_ms - self._stable_since_ms >= self.settings.stable_ms

    def _legacy_config(self) -> AppConfig:
        return AppConfig(
            control_region_fraction=self.settings.control_region_fraction,
            tracking_loss_release_ms=min(self.settings.tracking_loss_ms, 500),
            pose_stable_ms=self.settings.stable_ms,
            pointer_smoothing=self.settings.pointer_smoothing,
            pointer_dead_zone=self.settings.pointer_deadzone,
            pinch_close_ratio=self.settings.pinch_enter_ratio,
            pinch_open_ratio=self.settings.pinch_release_ratio,
            camera_index=self.settings.camera_index,
            swap_handedness=self.settings.swap_handedness,
        )

    def _tracked_hand(self, observation: HandObservation) -> TrackedHand:
        signals = self.classifier.classify(observation)
        return TrackedHand(
            signals,
            observation.landmarks[4],
            observation.timestamp_ms,
            camera_fist=_camera_fist(observation, signals),
        )


def _camera_fist(observation: HandObservation, signals) -> bool:
    """Lenient fist signal isolated to the modeling camera controls.

    The legacy desktop controller deliberately keeps its stricter classifier.
    Modeling tolerates one noisy curled finger, while distinguishing a compact
    index pinch by where the thumb/index contact sits relative to the palm.
    """
    points = observation.landmarks
    scale = palm_scale(points)
    non_thumb_extended = signals.extended - {"thumb"}
    curled = sum(
        wristward_displacement(points, pip, tip) > -0.015 * scale
        for _, pip, tip in FINGER_CHAINS.values()
    )
    if non_thumb_extended or curled < 3:
        return False
    if not signals.pinch_index:
        return True

    knuckle_x = sum(points[index].x for index in (5, 9, 13, 17)) / 4.0
    knuckle_y = sum(points[index].y for index in (5, 9, 13, 17)) / 4.0
    axis_x = points[0].x - knuckle_x
    axis_y = points[0].y - knuckle_y
    axis_length = hypot(axis_x, axis_y)
    if axis_length <= 1e-6:
        return False
    contact_x = (points[4].x + points[8].x) / 2.0
    contact_y = (points[4].y + points[8].y) / 2.0
    wristward_contact = (
        (contact_x - signals.palm_center.x) * axis_x
        + (contact_y - signals.palm_center.y) * axis_y
    ) / (axis_length * scale)
    return wristward_contact > 0.05
