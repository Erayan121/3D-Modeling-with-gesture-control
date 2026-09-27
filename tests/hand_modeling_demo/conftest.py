import pytest

from gesture_control.core.classifier import HandClassifier
from gesture_control.core.config import AppConfig
from hand_modeling_demo.domain import TrackedHand
from tests.unit.hand_factory import hand


@pytest.fixture
def tracked_hand_factory():
    classifier = HandClassifier(AppConfig(swap_handedness=False))

    def factory(observation):
        return TrackedHand(
            classifier.classify(observation),
            observation.landmarks[4],
            observation.timestamp_ms,
        )

    return factory


@pytest.fixture
def realistic_pose_hands(tracked_hand_factory):
    from gesture_control.core.models import HandSide

    fist = hand(HandSide.RIGHT, {})
    open_hand = hand(
        HandSide.RIGHT,
        {8: (0.43, 0.28), 12: (0.50, 0.24), 16: (0.57, 0.29), 20: (0.64, 0.34)},
    )
    index_only = hand(HandSide.RIGHT, {8: (0.43, 0.28)})
    return tuple(tracked_hand_factory(item) for item in (fist, open_hand, index_only))
