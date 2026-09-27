from __future__ import annotations

from dataclasses import dataclass

import pytest

from gesture_control.core.models import HandSide
from hand_modeling_demo.app import HandModelingApp
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import (
    AppState,
    InteractionMode,
    Intent,
    IntentKind,
    PrimitiveKind,
    TrackingSnapshot,
    Vec2,
    Vec3,
)
from hand_modeling_demo.gestures.interpreter import InteractionFrame
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.gestures.poses import HandPose
from hand_modeling_demo.model.entities import MeshEntity, Transform, create_primitive


class FakeTracking:
    def __init__(self):
        self.is_open = False
        self.running = False
        self.error = None
        self.stable = False
        self.poll_count = 0
        self.snapshot = TrackingSnapshot(0, {}, False)

    def open(self, index: int) -> None:
        self.is_open = True

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def close(self) -> None:
        self.is_open = False

    def poll(self, now_ms: int) -> TrackingSnapshot:
        self.poll_count += 1
        return self.snapshot


class FakeScene:
    distance = 12.0

    def __init__(self):
        self.preview = None
        self.camera_calls: list[tuple[str, object]] = []
        self.failures = []
        self.sync_count = 0
        self.camera_gesture = None

    def screen_plane_point(self, point: Vec2, depth: float) -> Vec3:
        return Vec3(point.x * depth, point.y * depth, depth)

    @staticmethod
    def depth_of(point: Vec3) -> float:
        return point.z

    def set_preview(self, preview) -> None:
        self.preview = preview

    def show_union_failure(self, ids) -> None:
        self.failures.append(tuple(ids))

    def pan(self, value) -> None:
        self.camera_calls.append(("pan", value))

    def zoom(self, value) -> None:
        self.camera_calls.append(("zoom", value))

    def orbit(self, value) -> None:
        self.camera_calls.append(("orbit", value))

    def sync(self, store) -> None:
        self.sync_count += 1

    def clear(self) -> None:
        pass

    def set_pointers(self, pointers) -> None:
        pass

    def set_camera_gesture(self, mode, pointers, *, motion_enabled=True) -> None:
        self.camera_gesture = (mode, dict(pointers), motion_enabled)

    def pick_all(self, pointers):
        return {side: None for side in pointers}

    def set_highlights(self, hover):
        pass


@dataclass
class FakeWindow:
    state: AppState = AppState.START
    error: str = ""

    def show_modeling(self, *, fullscreen: bool = True) -> None:
        self.state = AppState.MODELING_ACTIVE

    def show_paused(self) -> None:
        self.state = AppState.MODELING_PAUSED

    def show_start(self) -> None:
        self.state = AppState.START

    def show_error(self, text: str) -> None:
        self.state = AppState.ERROR
        self.error = text


@pytest.fixture
def app() -> HandModelingApp:
    return HandModelingApp(Settings(stable_ms=100), FakeTracking(), FakeScene(), FakeWindow())


def pointer(side: HandSide, x: float, *, pinched: bool = True) -> PointerState:
    return PointerState(side, Vec2(x, 0.5), pinched, 0)


def add_cube(app: HandModelingApp, entity_id: str, x: float = 0.0) -> None:
    app.store.add(
        MeshEntity(
            entity_id,
            PrimitiveKind.CUBE,
            create_primitive(PrimitiveKind.CUBE),
            Transform(Vec3(x, 0.0, 5.0)),
        )
    )


def test_start_create_transform_undo_redo_and_discard(app: HandModelingApp) -> None:
    assert app.start() is True
    app.tracking_stable()
    app.press_digit(2)
    app.creation.update(pointer(HandSide.LEFT, 0.3), pointer(HandSide.RIGHT, 0.7))
    app.creation.update(pointer(HandSide.LEFT, 0.2), pointer(HandSide.RIGHT, 0.8))
    app.creation.release(HandSide.LEFT)
    cube = app.store.ids()[0]
    created = app.store.get(cube)

    app.transform.begin(cube, HandSide.RIGHT, Vec2(0.4, 0.5))
    app.transform.update({HandSide.RIGHT: Vec2(0.6, 0.5)})
    app.transform.remove_hand(HandSide.RIGHT)
    moved = app.store.get(cube)
    assert moved != created
    assert app.history.undo(app.store) is True
    assert app.store.get(cube) == created
    assert app.history.redo(app.store) is True
    assert app.store.get(cube) == moved

    app.return_to_start()

    assert app.store.ids() == ()
    assert app.window.state is AppState.START


def test_boolean_locks_immediately_and_merges_after_small_inward_motion(
    app: HandModelingApp,
) -> None:
    app.start()
    app.tracking_stable()
    add_cube(app, "a", 0.0)
    add_cube(app, "b", 0.25)
    before = app.store.snapshot_bytes()

    app.process_interaction_frame(
        InteractionFrame(
            0,
            {
                HandSide.LEFT: pointer(HandSide.LEFT, 0.2),
                HandSide.RIGHT: pointer(HandSide.RIGHT, 0.8),
            },
            {},
            {HandSide.LEFT: "a", HandSide.RIGHT: "b"},
        )
    )

    assert app.interpreter.mode is InteractionMode.BOOLEAN
    assert app.store.snapshot_bytes() == before

    app.process_interaction_frame(
        InteractionFrame(
            20,
            {
                HandSide.LEFT: pointer(HandSide.LEFT, 0.22),
                HandSide.RIGHT: pointer(HandSide.RIGHT, 0.78),
            },
            {},
            {HandSide.LEFT: "a", HandSide.RIGHT: "b"},
        )
    )

    assert len(app.store.ids()) == 1
    assert app.store.ids()[0].startswith("union-")
    assert app.history.depth == (1, 0)


@pytest.mark.parametrize("active", ["create", "transform", "union", "circle"])
def test_space_cancels_uncommitted_session_and_releases_camera(
    app: HandModelingApp, active: str
) -> None:
    app.start()
    app.tracking_stable()
    add_cube(app, "a", 0.0)
    if active == "create":
        app.press_digit(1)
        app.creation.update(pointer(HandSide.LEFT, 0.3), pointer(HandSide.RIGHT, 0.7))
    elif active == "transform":
        app.transform.begin("a", HandSide.RIGHT, Vec2(0.4, 0.5))
        app.transform.update({HandSide.RIGHT: Vec2(0.7, 0.5)})
    elif active == "union":
        add_cube(app, "b", 0.25)
        assert app.union.begin("a", "b", distance=0.6)
    else:
        app.interpreter.mode = InteractionMode.CIRCLE
    committed = app.committed_snapshot()
    if active == "transform":
        committed = MeshEntity(
            "a", PrimitiveKind.CUBE, create_primitive(PrimitiveKind.CUBE), Transform(Vec3(0.0, 0.0, 5.0))
        )

    app.press_space()

    if active == "transform":
        assert app.store.get("a") == committed
    assert app.history.depth == (0, 0)
    assert app.tracking.is_open is False
    assert app.interpreter.mode is InteractionMode.NEUTRAL
    assert app.window.state is AppState.MODELING_PAUSED


def test_resume_keeps_pause_visible_until_tracking_is_stable(app: HandModelingApp) -> None:
    app.start(); app.tracking_stable(); app.press_space()

    app.press_space()

    assert app.tracking.is_open is True
    assert app.window.state is AppState.MODELING_PAUSED
    app.tracking_stable()
    assert app.window.state is AppState.MODELING_ACTIVE


def test_tick_polls_until_tracking_is_stable_without_manual_callback(
    app: HandModelingApp,
) -> None:
    app.start()
    app.press_space()
    app.press_space()
    app.tracking.stable = True

    app.tick(100)

    assert app.tracking.poll_count == 1
    assert app.lifecycle.tracking_ready is True
    assert app.window.state is AppState.MODELING_ACTIVE


def test_creation_commits_when_either_hand_releases_through_interpreter(
    app: HandModelingApp,
) -> None:
    app.start()
    app.tracking_stable()
    app.press_digit(1)

    def creation_frame(timestamp: int, left_x: float, right_x: float, *, left_pinched: bool):
        app.process_interaction_frame(
            InteractionFrame(
                timestamp,
                {
                    HandSide.LEFT: pointer(HandSide.LEFT, left_x, pinched=left_pinched),
                    HandSide.RIGHT: pointer(HandSide.RIGHT, right_x),
                },
                {},
                {},
                PrimitiveKind.SPHERE,
            )
        )

    creation_frame(0, 0.3, 0.7, left_pinched=False)
    creation_frame(100, 0.3, 0.7, left_pinched=False)
    creation_frame(120, 0.3, 0.7, left_pinched=True)
    creation_frame(140, 0.2, 0.8, left_pinched=True)
    creation_frame(160, 0.2, 0.8, left_pinched=False)

    assert len(app.store.ids()) == 1
    assert app.creation.pending is None
    assert app.interpreter.mode is InteractionMode.NEUTRAL


def test_single_grab_upgrades_to_dual_transform_without_releasing_model(
    app: HandModelingApp,
) -> None:
    app.start()
    app.tracking_stable()
    add_cube(app, "a")

    def interaction(timestamp: int, left: PointerState | None, right: PointerState):
        pointers = {HandSide.RIGHT: right}
        hover = {HandSide.RIGHT: "a"}
        if left is not None:
            pointers[HandSide.LEFT] = left
            hover[HandSide.LEFT] = "a"
        app.process_interaction_frame(InteractionFrame(timestamp, pointers, {}, hover))

    interaction(0, None, pointer(HandSide.RIGHT, 0.5))
    interaction(100, None, pointer(HandSide.RIGHT, 0.5))
    interaction(120, None, pointer(HandSide.RIGHT, 0.6))
    interaction(140, None, pointer(HandSide.RIGHT, 0.7))
    interaction(160, pointer(HandSide.LEFT, 0.3), pointer(HandSide.RIGHT, 0.7))
    interaction(180, pointer(HandSide.LEFT, 0.3), pointer(HandSide.RIGHT, 0.7))
    interaction(280, pointer(HandSide.LEFT, 0.3), pointer(HandSide.RIGHT, 0.7))
    interaction(300, pointer(HandSide.LEFT, 0.2), pointer(HandSide.RIGHT, 0.8))

    assert app.transform.active is True
    assert app.transform.current_transform.scale > 1.0


def test_settings_changes_reconfigure_every_runtime_component(app: HandModelingApp) -> None:
    updated = Settings(camera_index=3, pointer_smoothing=0.2, zoom_gain=9.0)

    app.apply_settings(updated)

    assert app.settings is updated
    assert app.lifecycle.settings is updated
    assert app.tracking.settings is updated
    assert app.scene.settings is updated
    assert app.interpreter.settings is updated
    assert app.creation.settings is updated
    assert app.transform.settings is updated
    assert app.union.settings is updated
    assert app.pointer_system._filters[HandSide.LEFT].settings is updated


def test_camera_actions_never_change_history(app: HandModelingApp) -> None:
    app.apply_intent(Intent(IntentKind.CAMERA_PAN, delta=Vec2(0.1, 0.2)))
    app.apply_intent(Intent(IntentKind.CAMERA_ZOOM, scalar=0.2))
    app.apply_intent(Intent(IntentKind.CAMERA_ORBIT, delta=Vec2(-0.1, 0.1)))

    assert app.history.depth == (0, 0)
    assert [name for name, _ in app.scene.camera_calls] == ["pan", "zoom", "orbit"]


def test_tick_freezes_camera_during_pinched_transition(
    app: HandModelingApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.start()
    app.tracking_stable()
    monkeypatch.setattr("hand_modeling_demo.app.classify_pose", lambda hand: HandPose.OPEN)

    def fake_pointers(snapshot):
        pinched = snapshot.timestamp_ms == 120
        return {
            HandSide.LEFT: PointerState(
                HandSide.LEFT, Vec2(0.2, 0.5), pinched, snapshot.timestamp_ms
            ),
            HandSide.RIGHT: PointerState(
                HandSide.RIGHT, Vec2(0.8, 0.5), False, snapshot.timestamp_ms
            ),
        }

    monkeypatch.setattr(app.pointer_system, "update", fake_pointers)
    for time_ms in (0, 100, 120):
        app.tracking.snapshot = TrackingSnapshot(
            time_ms, {HandSide.LEFT: object(), HandSide.RIGHT: object()}, True
        )
        app.tick(time_ms)

    assert app.interpreter.mode is InteractionMode.CAMERA_PAN
    assert app.scene.camera_gesture[0] is InteractionMode.CAMERA_PAN
    assert app.scene.camera_gesture[2] is False


def test_rhino_mouse_camera_controls_apply_only_while_modeling(
    app: HandModelingApp,
) -> None:
    app.mouse_orbit(0.1, -0.2)
    app.mouse_pan(0.2, 0.1)
    app.mouse_zoom(0.1)
    assert app.scene.camera_calls == []

    app.start()
    app.tracking_stable()
    app.mouse_orbit(0.1, -0.2)
    app.mouse_pan(0.2, 0.1)
    app.mouse_zoom(0.1)

    assert [name for name, _ in app.scene.camera_calls] == ["orbit", "pan", "zoom"]
    assert app.history.depth == (0, 0)


def test_tracking_error_cancels_and_shows_recoverable_error(app: HandModelingApp) -> None:
    app.start(); app.tracking_stable()
    app.tracking.error = RuntimeError("stream stopped")

    app.tick(500)

    assert app.window.state is AppState.ERROR
    assert "stream stopped" in app.window.error
    assert app.tracking.is_open is False


def test_smoke_mode_never_opens_camera(app: HandModelingApp) -> None:
    report = app.run_smoke()

    assert report == {
        "state": "start",
        "camera_open": False,
        "tracking_running": False,
        "clean_shutdown": True,
    }
