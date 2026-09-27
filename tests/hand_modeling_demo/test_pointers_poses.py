from dataclasses import replace

import pytest

from gesture_control.core.models import HandSide, Point
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import TrackedHand, Vec2
from hand_modeling_demo.gestures.pointers import PointerFilter, PointerProjector
from hand_modeling_demo.gestures.poses import HandPose, classify_pose
from tests.unit.signal_factory import signals
from tests.unit.hand_factory import hand


def tracked(
    *,
    index: tuple[float, float] = (0.7, 0.4),
    thumb: tuple[float, float] = (0.4, 0.4),
    ratio: float = 0.5,
    timestamp_ms: int = 0,
) -> TrackedHand:
    return TrackedHand(
        signals(
            HandSide.RIGHT,
            index=index,
            index_pinch_ratio=ratio,
            pinch_index=ratio <= 0.28,
        ),
        Point(*thumb),
        timestamp_ms,
    )


def test_mirrored_frame_mapping_keeps_horizontal_direction() -> None:
    projector = PointerProjector(control_region_fraction=1.0)

    assert projector.to_viewport(Point(0.25, 0.50)) == Vec2(0.25, 0.50)


def test_control_region_maps_central_area_to_full_viewport() -> None:
    projector = PointerProjector(control_region_fraction=0.8)

    assert projector.to_viewport(Point(0.10, 0.10)) == Vec2(0.0, 0.0)
    assert projector.to_viewport(Point(0.90, 0.90)) == Vec2(1.0, 1.0)
    assert projector.to_viewport(Point(-1.0, 2.0)) == Vec2(0.0, 1.0)


def test_pointer_smoothly_switches_to_pinch_midpoint() -> None:
    pointer_filter = PointerFilter(
        Settings(
            control_region_fraction=1.0,
            pointer_smoothing=0.5,
            pointer_deadzone=0.0,
        )
    )
    normal = pointer_filter.update(tracked())
    pinched = pointer_filter.update(tracked(thumb=(0.6, 0.4), ratio=0.20, timestamp_ms=16))

    assert normal.position.x == pytest.approx(0.7)
    assert pinched.position.x == pytest.approx(0.675)
    assert pinched.pinched is True


def test_pinch_hysteresis_ignores_threshold_jitter() -> None:
    pointer_filter = PointerFilter(Settings(pointer_smoothing=0.0, pointer_deadzone=0.0))

    assert pointer_filter.update(tracked(ratio=0.34)).pinched is True
    assert pointer_filter.update(tracked(ratio=0.46, timestamp_ms=10)).pinched is True
    assert pointer_filter.update(tracked(ratio=0.50, timestamp_ms=20)).pinched is True
    assert pointer_filter.update(tracked(ratio=0.50, timestamp_ms=100)).pinched is True
    assert pointer_filter.update(tracked(ratio=0.50, timestamp_ms=141)).pinched is False


def test_deadzone_suppresses_micro_motion() -> None:
    pointer_filter = PointerFilter(Settings(pointer_smoothing=0.0, pointer_deadzone=0.01))
    first = pointer_filter.update(tracked(index=(0.5, 0.5)))
    second = pointer_filter.update(tracked(index=(0.505, 0.504), timestamp_ms=10))

    assert second.position == first.position


def test_fist_open_and_index_only_are_mutually_exclusive(realistic_pose_hands) -> None:
    assert [classify_pose(item) for item in realistic_pose_hands] == [
        HandPose.FIST,
        HandPose.OPEN,
        HandPose.INDEX_ONLY,
    ]


def test_real_five_finger_palm_is_open(tracked_hand_factory) -> None:
    observation = hand(
        HandSide.RIGHT,
        {
            4: (0.25, 0.55),
            8: (0.43, 0.28),
            12: (0.50, 0.24),
            16: (0.57, 0.29),
            20: (0.64, 0.34),
        },
    )

    assert classify_pose(tracked_hand_factory(observation)) is HandPose.OPEN


def test_two_visible_fingers_do_not_arm_open_palm_camera_gesture(
    tracked_hand_factory,
) -> None:
    observation = hand(
        HandSide.RIGHT,
        {8: (0.43, 0.28), 12: (0.50, 0.24)},
    )

    assert classify_pose(tracked_hand_factory(observation)) is HandPose.NEUTRAL


def test_open_palm_allows_one_missed_fingertip(tracked_hand_factory) -> None:
    observation = hand(
        HandSide.RIGHT,
        {8: (0.43, 0.28), 12: (0.50, 0.24), 16: (0.57, 0.29)},
    )

    assert classify_pose(tracked_hand_factory(observation)) is HandPose.OPEN


def test_three_extended_fingers_without_index_are_not_open_palm(
    tracked_hand_factory,
) -> None:
    observation = hand(
        HandSide.RIGHT,
        {12: (0.50, 0.24), 16: (0.57, 0.29), 20: (0.64, 0.34)},
    )

    assert classify_pose(tracked_hand_factory(observation)) is HandPose.NEUTRAL


def test_real_fist_allows_thumb_to_extend(tracked_hand_factory) -> None:
    observation = hand(HandSide.RIGHT, {4: (0.25, 0.70)})
    tracked = tracked_hand_factory(observation)

    assert tracked.signals.extended == frozenset({"thumb"})
    assert tracked.signals.is_fist is True
    assert classify_pose(tracked) is HandPose.FIST


def test_geometric_fist_wins_over_incidental_pinch(realistic_pose_hands) -> None:
    fist = realistic_pose_hands[0]
    pinched_fist = replace(fist, signals=replace(fist.signals, pinch_index=True))

    assert classify_pose(pinched_fist) is HandPose.FIST


def test_pinched_index_only_hand_is_not_circle_pose(realistic_pose_hands) -> None:
    index_only = realistic_pose_hands[2]
    pinched = replace(index_only, signals=replace(index_only.signals, pinch_index=True))

    assert classify_pose(pinched) is HandPose.NEUTRAL
