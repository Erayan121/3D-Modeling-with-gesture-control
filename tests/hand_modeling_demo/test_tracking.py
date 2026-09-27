from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gesture_control.core.classifier import HandClassifier
from gesture_control.core.config import AppConfig
from gesture_control.core.models import HandObservation, HandSide, Point
from hand_modeling_demo.config import Settings
from hand_modeling_demo.tracking import TrackingService, _camera_fist
from tests.unit.hand_factory import compact_pinch, hand
from tests.unit.signal_factory import signals


FRAME = np.zeros((8, 8, 3), dtype=np.uint8)


def observation(side: HandSide, confidence: float, timestamp_ms: int = 100) -> HandObservation:
    points = tuple(Point(0.1 + index * 0.01, 0.2, 0.0) for index in range(21))
    return HandObservation(side, confidence, points, timestamp_ms)


class FakeCamera:
    def __init__(self, index: int):
        self.index = index
        self.error: Exception | None = None
        self.is_open = False
        self.latest: tuple[int, np.ndarray, int] | None = None

    def open(self) -> None:
        self.is_open = True

    def read_latest(self):
        return self.latest

    def close(self) -> None:
        self.is_open = False
        self.latest = None


class FakeTracker:
    def __init__(self, config, on_result):
        self.config = config
        self.on_result = on_result
        self.error: Exception | None = None
        self.submitted_timestamps: list[int] = []
        self.closed = False

    def submit(self, frame, timestamp_ms: int) -> None:
        self.submitted_timestamps.append(timestamp_ms)

    def close(self) -> None:
        self.closed = True


@dataclass
class Factories:
    camera: FakeCamera | None = None
    tracker: FakeTracker | None = None

    def camera_factory(self, index: int) -> FakeCamera:
        self.camera = FakeCamera(index)
        return self.camera

    def tracker_factory(self, config, on_result) -> FakeTracker:
        self.tracker = FakeTracker(config, on_result)
        return self.tracker

    @staticmethod
    def classifier_factory(config):
        class Classifier:
            @staticmethod
            def classify(item: HandObservation):
                return signals(item.side, confidence=item.confidence)

        return Classifier()


def started_service(settings: Settings | None = None) -> tuple[TrackingService, Factories]:
    factories = Factories()
    service = TrackingService(
        settings or Settings(),
        camera_factory=factories.camera_factory,
        tracker_factory=factories.tracker_factory,
        classifier_factory=factories.classifier_factory,
    )
    service.open((settings or Settings()).camera_index)
    service.start()
    return service, factories


def test_poll_submits_only_the_newest_sequence_once() -> None:
    service, factories = started_service()
    assert factories.camera is not None and factories.tracker is not None
    factories.camera.latest = (9, FRAME, 90)

    service.poll(90)
    service.poll(91)

    assert factories.tracker.submitted_timestamps == [90]
    assert service.last_sequence == 9
    assert service.pending_count == 0


def test_duplicate_side_labels_publish_only_the_stronger_hand() -> None:
    service, _ = started_service()
    service.accept(
        (observation(HandSide.LEFT, 0.95), observation(HandSide.LEFT, 0.70)),
        100,
    )

    snapshot = service.poll(100)

    assert list(snapshot.hands) == [HandSide.LEFT]
    assert snapshot.hands[HandSide.LEFT].signals.confidence == 0.95


def test_settings_are_mapped_to_legacy_tracking_config() -> None:
    settings = Settings(
        camera_index=3,
        swap_handedness=True,
        pointer_smoothing=0.72,
        tracking_loss_ms=400,
    )
    _, factories = started_service(settings)
    assert factories.camera is not None and factories.tracker is not None

    config = factories.tracker.config
    assert factories.camera.index == 3
    assert config.swap_handedness is True
    assert config.pointer_smoothing == 0.72
    assert config.tracking_loss_release_ms == 400


def test_tracking_becomes_stable_only_after_continuous_fresh_interval() -> None:
    service, _ = started_service(Settings(stable_ms=120))
    service.accept((observation(HandSide.RIGHT, 0.9, 0),), 0)
    assert service.poll(0).fresh is True
    assert service.stable is False

    service.accept((observation(HandSide.RIGHT, 0.9, 119),), 119)
    service.poll(119)
    assert service.stable is False

    service.accept((observation(HandSide.RIGHT, 0.9, 120),), 120)
    service.poll(120)
    assert service.stable is True


def test_camera_stall_releases_resources_and_surfaces_error() -> None:
    service, factories = started_service()
    assert factories.camera is not None and factories.tracker is not None
    factories.camera.error = RuntimeError("stream stopped")

    snapshot = service.poll(400)

    assert snapshot.fresh is False
    assert isinstance(service.error, RuntimeError)
    assert factories.tracker.closed is True
    assert factories.camera.is_open is False


def test_stop_clears_published_hands_and_can_restart() -> None:
    service, factories = started_service()
    service.accept((observation(HandSide.RIGHT, 0.9),), 100)
    service.stop()
    service.close()

    assert service.poll(101).hands == {}

    service.open(0)
    service.start()
    assert factories.camera is not None
    assert factories.camera.is_open is True


def test_modeling_camera_fist_tolerates_one_borderline_curled_finger() -> None:
    pose = hand(HandSide.RIGHT, {16: (0.57, 0.695)})
    classified = HandClassifier(AppConfig()).classify(pose)

    assert classified.is_fist is False
    assert _camera_fist(pose, classified) is True


def test_modeling_camera_fist_does_not_steal_compact_index_pinch() -> None:
    pose = compact_pinch("index")
    classified = HandClassifier(AppConfig()).classify(pose)

    assert classified.pinch_index is True
    assert _camera_fist(pose, classified) is False
