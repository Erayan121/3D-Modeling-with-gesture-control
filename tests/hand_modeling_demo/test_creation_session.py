import pytest

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import PrimitiveKind, Vec2, Vec3
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.model.commands import History
from hand_modeling_demo.model.entities import ModelStore
from hand_modeling_demo.model.sessions import CreationSession


def pointer(side: HandSide, x: float, y: float = 0.5, *, pinched: bool) -> PointerState:
    return PointerState(side, Vec2(x, y), pinched, 0)


class FakeScene:
    def __init__(self):
        self.shown = []

    def screen_plane_point(self, point: Vec2, depth: float) -> Vec3:
        return Vec3(point.x, point.y, depth)

    def set_preview(self, preview) -> None:
        self.shown.append(preview)


@pytest.fixture
def session() -> CreationSession:
    return CreationSession(Settings(), FakeScene(), ModelStore(), History())


def update_pair(
    session: CreationSession,
    left_x: float,
    right_x: float,
    *,
    pinched: bool = True,
) -> None:
    session.update(
        pointer(HandSide.LEFT, left_x, pinched=pinched),
        pointer(HandSide.RIGHT, right_x, pinched=pinched),
    )


def test_waiting_center_follows_live_midpoint_before_pinch(session: CreationSession) -> None:
    session.arm(PrimitiveKind.SPHERE)
    update_pair(session, 0.2, 0.6, pinched=False)
    assert session.waiting_center == Vec2(0.4, 0.5)
    assert session.preview is not None
    assert session.preview.center == Vec2(0.4, 0.5)
    assert session.preview.scale == session.preview_epsilon
    assert session.active is False


def test_preview_locks_midpoint_and_scales_from_initial_distance(session: CreationSession) -> None:
    session.arm(PrimitiveKind.SPHERE)
    update_pair(session, 0.3, 0.7)
    update_pair(session, 0.2, 0.8)

    assert session.preview is not None
    assert session.preview.center == Vec2(0.5, 0.5)
    assert session.preview.scale == pytest.approx(0.8)


def test_release_below_threshold_cancels_without_history(session: CreationSession) -> None:
    session.arm(PrimitiveKind.CUBE)
    update_pair(session, 0.49, 0.51)

    session.release(HandSide.LEFT)

    assert session.store.ids() == ()
    assert session.history.depth == (0, 0)
    assert session.pending is PrimitiveKind.CUBE
    assert session.preview is not None
    assert session.preview.scale == session.preview_epsilon
    assert session.active is False


def test_suspend_hides_seed_but_keeps_armed_primitive(session: CreationSession) -> None:
    session.arm(PrimitiveKind.CONE)
    update_pair(session, 0.3, 0.7, pinched=False)

    session.suspend()

    assert session.pending is PrimitiveKind.CONE
    assert session.preview is None
    assert session.active is False


def test_release_after_outward_pull_commits_one_create_command(session: CreationSession) -> None:
    session.arm(PrimitiveKind.CYLINDER)
    update_pair(session, 0.3, 0.7)
    update_pair(session, 0.2, 0.8)

    session.release(HandSide.RIGHT)

    assert len(session.store.ids()) == 1
    created = session.store.get(session.store.ids()[0])
    assert created.kind is PrimitiveKind.CYLINDER
    assert created.transform.scale == pytest.approx(0.8)
    assert session.history.depth == (1, 0)
    assert session.pending is None


def test_new_digit_replaces_pending_and_cancels_started_preview(session: CreationSession) -> None:
    session.arm(PrimitiveKind.SPHERE)
    update_pair(session, 0.3, 0.7)

    session.arm(PrimitiveKind.TORUS)

    assert session.pending is PrimitiveKind.TORUS
    assert session.preview is None
    assert session.history.depth == (0, 0)


def test_cancel_removes_preview_without_committing(session: CreationSession) -> None:
    session.arm(PrimitiveKind.CONE)
    update_pair(session, 0.3, 0.7)

    session.cancel()

    assert session.preview is None
    assert session.pending is None
    assert session.store.ids() == ()
    assert session.scene.shown[-1] is None
