"""Explicit, deterministic signal frames; never access tracking or OS input."""

from gesture_control.core.models import GestureFrame, HandSide, HandSignals, Point


def signals(side, extended=(), *, index=(0.5, 0.5), middle=(0.5, 0.5), palm=(0.5, 0.5),
            pinky_pinch=(0.5, 0.5), pinch_index=False, pinch_middle=False,
            pinch_pinky=False, is_fist=False, confidence=1.0,
            index_pinch_ratio=0.2, middle_pinch_ratio=0.2, pinky_pinch_ratio=0.2):
    return HandSignals(side=side, confidence=confidence, extended=frozenset(extended),
                       index_tip=Point(*index), middle_tip=Point(*middle),
                       palm_center=Point(*palm), palm_scale=0.2,
                       pinch_index=pinch_index, pinch_middle=pinch_middle,
                       pinch_pinky=pinch_pinky, is_fist=is_fist,
                       pinky_pinch_point=Point(*pinky_pinch),
                       index_pinch_ratio=index_pinch_ratio, middle_pinch_ratio=middle_pinch_ratio,
                       pinky_pinch_ratio=pinky_pinch_ratio)


def frame(timestamp_ms, *, left=None, right=None):
    hands = {}
    if left is not None:
        hands[HandSide.LEFT] = left
    if right is not None:
        hands[HandSide.RIGHT] = right
    return GestureFrame(timestamp_ms, hands)


def frame_with_pinch(pinch_name, timestamp_ms):
    side, finger = pinch_name.split("_")
    return frame(timestamp_ms, **{side: signals(HandSide(side), **{f"pinch_{finger}": True})})


def frame_without_pinches(timestamp_ms):
    return frame(timestamp_ms, left=signals(HandSide.LEFT), right=signals(HandSide.RIGHT))


def run_all_continuous_workflows(engine):
    commands = []
    for name, start in (("left_index", 0), ("left_middle", 600)):
        commands += engine.step(frame_with_pinch(name, start))
        commands += engine.step(frame_with_pinch(name, start + 350))
        commands += engine.step(frame_without_pinches(start + 400))
    palm = signals(HandSide.RIGHT, {"thumb", "index", "middle", "ring", "pinky"})
    commands += engine.step(frame(1200, right=palm))
    commands += engine.step(frame(1320, right=palm))
    commands += engine.step(frame_without_pinches(1400))
    commands += engine.stop()
    return commands
