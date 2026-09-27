from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import InteractionMode, IntentKind, PrimitiveKind, Vec2
from hand_modeling_demo.gestures.interpreter import GestureInterpreter, InteractionFrame
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.gestures.poses import HandPose


def pointer(side: HandSide, x: float, y: float = 0.5, *, pinched: bool = False, t: int = 0):
    return PointerState(side, Vec2(x, y), pinched, t)


def frame(
    timestamp_ms: int,
    *,
    left: PointerState | None = None,
    right: PointerState | None = None,
    left_pose: HandPose = HandPose.NEUTRAL,
    right_pose: HandPose = HandPose.NEUTRAL,
    left_hover: str | None = None,
    right_hover: str | None = None,
    pending: PrimitiveKind | None = None,
) -> InteractionFrame:
    pointers = {}
    poses = {}
    hover = {}
    if left is not None:
        pointers[HandSide.LEFT] = left
        poses[HandSide.LEFT] = left_pose
        hover[HandSide.LEFT] = left_hover
    if right is not None:
        pointers[HandSide.RIGHT] = right
        poses[HandSide.RIGHT] = right_pose
        hover[HandSide.RIGHT] = right_hover
    return InteractionFrame(timestamp_ms, pointers, poses, hover, pending)


def test_priority_order_is_exact() -> None:
    interpreter = GestureInterpreter(Settings())
    different = frame(
        0,
        left=pointer(HandSide.LEFT, 0.2, pinched=True),
        right=pointer(HandSide.RIGHT, 0.8, pinched=True),
        left_pose=HandPose.OPEN,
        right_pose=HandPose.OPEN,
        left_hover="a",
        right_hover="b",
    )
    same = frame(
        0,
        left=pointer(HandSide.LEFT, 0.2, pinched=True),
        right=pointer(HandSide.RIGHT, 0.8, pinched=True),
        left_hover="a",
        right_hover="a",
    )

    assert interpreter.choose_mode(different, pending=PrimitiveKind.CUBE) is InteractionMode.CREATE
    assert interpreter.choose_mode(different, pending=None) is InteractionMode.BOOLEAN
    assert interpreter.choose_mode(same, pending=None) is InteractionMode.DUAL_TRANSFORM


def test_pending_creation_activates_and_updates_without_stability_delay() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=120))
    armed = frame(
        0,
        left=pointer(HandSide.LEFT, 0.3),
        right=pointer(HandSide.RIGHT, 0.7),
        pending=PrimitiveKind.SPHERE,
    )

    intents = interpreter.update(armed)

    assert interpreter.mode is InteractionMode.CREATE
    assert len(intents) == 1
    assert intents[0].kind is IntentKind.SESSION_UPDATE


def test_boolean_lock_activates_without_stability_delay() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=500))
    pinched = frame(
        0,
        left=pointer(HandSide.LEFT, 0.2, pinched=True),
        right=pointer(HandSide.RIGHT, 0.8, pinched=True),
        left_hover="a",
        right_hover="b",
    )

    intents = interpreter.update(pinched)

    assert interpreter.mode is InteractionMode.BOOLEAN
    assert len(intents) == 1
    assert intents[0].kind is IntentKind.SESSION_UPDATE
    assert intents[0].target_ids == ("a", "b")


def test_camera_pose_mapping_uses_only_approved_combinations() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    both_open = frame(
        0,
        left=pointer(HandSide.LEFT, 0.2), right=pointer(HandSide.RIGHT, 0.8),
        left_pose=HandPose.OPEN, right_pose=HandPose.OPEN,
    )
    assert interpreter.update(both_open) == ()
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(frame(100, left=pointer(HandSide.LEFT, 0.2, t=100), right=pointer(HandSide.RIGHT, 0.8, t=100), left_pose=HandPose.OPEN, right_pose=HandPose.OPEN))
    assert interpreter.mode is InteractionMode.CAMERA_PAN

    interpreter.cancel()
    both_fists = frame(0, left=pointer(HandSide.LEFT, 0.2), right=pointer(HandSide.RIGHT, 0.8), left_pose=HandPose.FIST, right_pose=HandPose.FIST)
    assert interpreter.update(both_fists) == ()
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(frame(100, left=pointer(HandSide.LEFT, 0.2, t=100), right=pointer(HandSide.RIGHT, 0.8, t=100), left_pose=HandPose.FIST, right_pose=HandPose.FIST))
    assert interpreter.mode is InteractionMode.CAMERA_ZOOM

    interpreter.cancel()
    right_fist = frame(0, right=pointer(HandSide.RIGHT, 0.7), right_pose=HandPose.FIST)
    assert interpreter.update(right_fist) == ()
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(frame(100, right=pointer(HandSide.RIGHT, 0.7, t=100), right_pose=HandPose.FIST))
    assert interpreter.mode is InteractionMode.CAMERA_ORBIT


def test_pinching_either_hand_blocks_open_palm_camera_pan() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    for time_ms in (0, 100, 200):
        interpreter.update(frame(
            time_ms,
            left=pointer(HandSide.LEFT, 0.2, pinched=True, t=time_ms),
            right=pointer(HandSide.RIGHT, 0.8, t=time_ms),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        ))
    assert interpreter.mode is InteractionMode.NEUTRAL


def test_transition_pose_must_stabilize_before_camera_starts() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=120))
    interpreter.update(frame(
        0, left=pointer(HandSide.LEFT, 0.2), right=pointer(HandSide.RIGHT, 0.8),
        left_pose=HandPose.OPEN, right_pose=HandPose.OPEN,
    ))
    interpreter.update(frame(
        60, left=pointer(HandSide.LEFT, 0.2, t=60), right=pointer(HandSide.RIGHT, 0.8, t=60),
        left_pose=HandPose.FIST, right_pose=HandPose.FIST,
    ))
    interpreter.update(frame(
        150, left=pointer(HandSide.LEFT, 0.2, t=150), right=pointer(HandSide.RIGHT, 0.8, t=150),
        left_pose=HandPose.FIST, right_pose=HandPose.FIST,
    ))
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(frame(
        180, left=pointer(HandSide.LEFT, 0.2, t=180), right=pointer(HandSide.RIGHT, 0.8, t=180),
        left_pose=HandPose.FIST, right_pose=HandPose.FIST,
    ))
    assert interpreter.mode is InteractionMode.CAMERA_ZOOM


def test_right_fist_to_two_fists_freezes_orbit_until_zoom_is_stable() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))

    def pose_frame(time_ms: int, *, left_fist: bool) -> InteractionFrame:
        return frame(
            time_ms,
            left=pointer(HandSide.LEFT, 0.2, t=time_ms) if left_fist else None,
            right=pointer(HandSide.RIGHT, 0.8, t=time_ms),
            left_pose=HandPose.FIST if left_fist else HandPose.NEUTRAL,
            right_pose=HandPose.FIST,
        )

    interpreter.update(pose_frame(0, left_fist=False))
    interpreter.update(pose_frame(100, left_fist=False))
    assert interpreter.mode is InteractionMode.CAMERA_ORBIT
    assert interpreter.camera_motion_enabled is True

    interpreter.update(pose_frame(120, left_fist=True))
    assert interpreter.mode is InteractionMode.CAMERA_ORBIT
    assert interpreter.camera_motion_enabled is False

    interpreter.update(pose_frame(380, left_fist=True))
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(pose_frame(400, left_fist=True))
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(pose_frame(500, left_fist=True))
    assert interpreter.mode is InteractionMode.CAMERA_ZOOM


def test_camera_motion_freezes_during_pose_transition_and_resumes_from_new_base() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    interpreter.update(frame(
        0, left=pointer(HandSide.LEFT, 0.2), right=pointer(HandSide.RIGHT, 0.8),
        left_pose=HandPose.OPEN, right_pose=HandPose.OPEN,
    ))
    interpreter.update(frame(
        100, left=pointer(HandSide.LEFT, 0.2, t=100), right=pointer(HandSide.RIGHT, 0.8, t=100),
        left_pose=HandPose.OPEN, right_pose=HandPose.OPEN,
    ))
    assert interpreter.camera_motion_enabled is True
    interpreter.update(frame(
        120, left=pointer(HandSide.LEFT, 0.3, pinched=True, t=120),
        right=pointer(HandSide.RIGHT, 0.9, t=120),
        left_pose=HandPose.OPEN, right_pose=HandPose.OPEN,
    ))
    assert interpreter.mode is InteractionMode.CAMERA_PAN
    assert interpreter.camera_motion_enabled is False
    interpreter.update(frame(
        160, left=pointer(HandSide.LEFT, 0.3, t=160),
        right=pointer(HandSide.RIGHT, 0.9, t=160),
        left_pose=HandPose.OPEN, right_pose=HandPose.OPEN,
    ))
    assert interpreter.camera_motion_enabled is True


def test_two_hand_candidate_suppresses_single_hand_during_stability() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    one = frame(0, right=pointer(HandSide.RIGHT, 0.7, pinched=True), right_hover="a")
    two = frame(
        20,
        left=pointer(HandSide.LEFT, 0.3, pinched=True, t=20),
        right=pointer(HandSide.RIGHT, 0.7, pinched=True, t=20),
        left_hover="a", right_hover="a",
    )

    assert interpreter.update(one) == ()
    assert interpreter.update(two) == ()
    assert interpreter.mode is InteractionMode.NEUTRAL


def test_active_camera_modes_leave_motion_to_the_visible_scene_controller() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    first = frame(0, left=pointer(HandSide.LEFT, 0.2), right=pointer(HandSide.RIGHT, 0.8), left_pose=HandPose.OPEN, right_pose=HandPose.OPEN)
    stable = frame(100, left=pointer(HandSide.LEFT, 0.2, t=100), right=pointer(HandSide.RIGHT, 0.8, t=100), left_pose=HandPose.OPEN, right_pose=HandPose.OPEN)
    moved = frame(120, left=pointer(HandSide.LEFT, 0.3, t=120), right=pointer(HandSide.RIGHT, 0.9, t=120), left_pose=HandPose.OPEN, right_pose=HandPose.OPEN)
    interpreter.update(first)
    assert interpreter.update(stable) == ()

    assert interpreter.update(moved) == ()
    assert interpreter.mode is InteractionMode.CAMERA_PAN


def test_active_camera_mode_freezes_during_short_pose_dropout() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    active = frame(
        0,
        left=pointer(HandSide.LEFT, 0.2),
        right=pointer(HandSide.RIGHT, 0.8),
        left_pose=HandPose.OPEN,
        right_pose=HandPose.OPEN,
    )
    interpreter.update(active)
    interpreter.update(
        frame(
            100,
            left=pointer(HandSide.LEFT, 0.2, t=100),
            right=pointer(HandSide.RIGHT, 0.8, t=100),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )

    dropout_motion = interpreter.update(
        frame(
            120,
            left=pointer(HandSide.LEFT, 0.3, t=120),
            right=pointer(HandSide.RIGHT, 0.9, t=120),
        )
    )
    assert dropout_motion == ()
    assert interpreter.mode is InteractionMode.CAMERA_PAN
    assert interpreter.camera_motion_enabled is False

    recovered = interpreter.update(
        frame(
            180,
            left=pointer(HandSide.LEFT, 0.3, t=180),
            right=pointer(HandSide.RIGHT, 0.9, t=180),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )

    assert recovered == ()
    assert interpreter.mode is InteractionMode.CAMERA_PAN
    assert interpreter.camera_motion_enabled is True


def test_camera_mode_rebases_after_a_pointer_disappears() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    interpreter.update(
        frame(
            0,
            left=pointer(HandSide.LEFT, 0.2),
            right=pointer(HandSide.RIGHT, 0.8),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )
    interpreter.update(
        frame(
            100,
            left=pointer(HandSide.LEFT, 0.2, t=100),
            right=pointer(HandSide.RIGHT, 0.8, t=100),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )
    assert interpreter.mode is InteractionMode.CAMERA_PAN

    assert interpreter.update(
        frame(120, right=pointer(HandSide.RIGHT, 0.9, t=120))
    ) == ()
    assert interpreter.camera_motion_enabled is False
    recovered = interpreter.update(
        frame(
            140,
            left=pointer(HandSide.LEFT, 0.3, t=140),
            right=pointer(HandSide.RIGHT, 0.9, t=140),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )

    assert recovered == ()
    assert interpreter.mode is InteractionMode.CAMERA_PAN
    assert interpreter.camera_motion_enabled is True


def test_camera_candidate_restarts_after_pinched_transition() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    interpreter.update(
        frame(
            0,
            left=pointer(HandSide.LEFT, 0.2),
            right=pointer(HandSide.RIGHT, 0.8),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )
    assert interpreter.update(
        frame(
            80,
            left=pointer(HandSide.LEFT, 0.2, pinched=True, t=80),
            right=pointer(HandSide.RIGHT, 0.8, t=80),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    ) == ()
    interpreter.update(
        frame(
            120,
            left=pointer(HandSide.LEFT, 0.2, t=120),
            right=pointer(HandSide.RIGHT, 0.8, t=120),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )
    assert interpreter.mode is InteractionMode.NEUTRAL
    interpreter.update(
        frame(
            220,
            left=pointer(HandSide.LEFT, 0.2, t=220),
            right=pointer(HandSide.RIGHT, 0.8, t=220),
            left_pose=HandPose.OPEN,
            right_pose=HandPose.OPEN,
        )
    )
    assert interpreter.mode is InteractionMode.CAMERA_PAN


def test_camera_motion_is_not_duplicated_as_an_interpreter_intent() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    start = frame(
        0,
        right=pointer(HandSide.RIGHT, 0.2),
        right_pose=HandPose.FIST,
    )
    stable = frame(
        100,
        right=pointer(HandSide.RIGHT, 0.2, t=100),
        right_pose=HandPose.FIST,
    )
    interpreter.update(start)
    interpreter.update(stable)

    spike = interpreter.update(
        frame(
            120,
            right=pointer(HandSide.RIGHT, 0.9, t=120),
            right_pose=HandPose.FIST,
        )
    )
    stopped = interpreter.update(
        frame(
            140,
            right=pointer(HandSide.RIGHT, 0.9, t=140),
            right_pose=HandPose.FIST,
        )
    )

    assert spike == ()
    assert stopped == ()


def test_cancel_clears_mode_candidate_and_circle_state() -> None:
    interpreter = GestureInterpreter(Settings(stable_ms=100))
    candidate = frame(0, right=pointer(HandSide.RIGHT, 0.7), right_pose=HandPose.FIST)
    interpreter.update(candidate)

    interpreter.cancel()

    assert interpreter.mode is InteractionMode.NEUTRAL
    assert interpreter.update(frame(100, right=pointer(HandSide.RIGHT, 0.7, t=100), right_pose=HandPose.FIST)) == ()
