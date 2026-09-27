from enum import Enum

from hand_modeling_demo.domain import TrackedHand


class HandPose(Enum):
    NEUTRAL = "neutral"
    FIST = "fist"
    OPEN = "open"
    INDEX_ONLY = "index_only"


def classify_pose(hand: TrackedHand) -> HandPose:
    signals = hand.signals
    is_fist = hand.camera_fist if hand.camera_fist is not None else signals.is_fist
    if is_fist:
        return HandPose.FIST
    if signals.pinch_index:
        return HandPose.NEUTRAL
    non_thumb = signals.extended - {"thumb"}
    # A thumb/index pinch can leave the other three fingers extended.
    # Require the index plus two other fingers before arming camera panning.
    if "index" in non_thumb and len(non_thumb & {"middle", "ring", "pinky"}) >= 2:
        return HandPose.OPEN
    if non_thumb == frozenset({"index"}):
        return HandPose.INDEX_ONLY
    return HandPose.NEUTRAL
