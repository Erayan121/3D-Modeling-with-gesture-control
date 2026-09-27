import pytest
import trimesh

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import PrimitiveKind, Vec2, Vec3
from hand_modeling_demo.model.commands import History
from hand_modeling_demo.model.entities import MeshEntity, ModelStore, Transform, create_primitive
from hand_modeling_demo.model.sessions import (
    TransformSession,
    UnionFeedback,
    UnionSession,
)


class FakeScene:
    def __init__(self):
        self.failures = []

    def screen_plane_point(self, point: Vec2, depth: float) -> Vec3:
        return Vec3(point.x * depth, point.y * depth, depth)

    @staticmethod
    def depth_of(point: Vec3) -> float:
        return point.z

    def show_union_failure(self, ids) -> None:
        self.failures.append(tuple(ids))


def make_entity(entity_id: str, x: float) -> MeshEntity:
    return MeshEntity(
        entity_id,
        PrimitiveKind.CUBE,
        create_primitive(PrimitiveKind.CUBE),
        Transform(Vec3(x, 0.0, 5.0)),
    )


@pytest.fixture
def transform_session() -> TransformSession:
    store, history = ModelStore(), History()
    store.add(make_entity("a", 0.0))
    return TransformSession(Settings(), FakeScene(), store, history)


def test_single_dual_single_transition_has_no_jump(transform_session: TransformSession) -> None:
    transform_session.begin("a", HandSide.RIGHT, Vec2(0.4, 0.5))
    transform_session.update({HandSide.RIGHT: Vec2(0.5, 0.5)})
    before_dual = transform_session.current_transform

    transform_session.add_hand(HandSide.LEFT, Vec2(0.2, 0.5))
    assert transform_session.current_transform == before_dual
    transform_session.remove_hand(HandSide.LEFT)
    assert transform_session.current_transform == before_dual


def test_single_grab_locks_target_and_preserves_depth(transform_session: TransformSession) -> None:
    transform_session.begin("a", HandSide.RIGHT, Vec2(0.4, 0.5))
    depth = transform_session.original_depth

    transform_session.update(
        {HandSide.RIGHT: Vec2(0.7, 0.6)},
        hover_ids={HandSide.RIGHT: "b"},
    )

    assert transform_session.entity_id == "a"
    assert transform_session.current_depth == pytest.approx(depth)


def test_dual_transform_updates_move_scale_and_view_axis_rotation(transform_session: TransformSession) -> None:
    transform_session.begin("a", HandSide.RIGHT, Vec2(0.7, 0.5))
    transform_session.add_hand(HandSide.LEFT, Vec2(0.3, 0.5))

    transform_session.update(
        {HandSide.LEFT: Vec2(0.4, 0.3), HandSide.RIGHT: Vec2(0.8, 0.7)}
    )

    result = transform_session.current_transform
    assert result.position.x > 0.0
    assert result.scale == pytest.approx(2 ** 0.5)
    assert result.roll == pytest.approx(45.0)


def test_last_release_commits_one_transform_and_cancel_restores(transform_session: TransformSession) -> None:
    original = transform_session.store.get("a")
    transform_session.begin("a", HandSide.RIGHT, Vec2(0.4, 0.5))
    transform_session.update({HandSide.RIGHT: Vec2(0.6, 0.5)})
    transform_session.remove_hand(HandSide.RIGHT)
    assert transform_session.history.depth == (1, 0)

    transform_session.history.undo(transform_session.store)
    assert transform_session.store.get("a") == original

    transform_session.begin("a", HandSide.RIGHT, Vec2(0.4, 0.5))
    transform_session.update({HandSide.RIGHT: Vec2(0.8, 0.5)})
    transform_session.cancel()
    assert transform_session.store.get("a") == original
    assert transform_session.history.depth == (0, 1)


def union_session(
    *,
    second_x: float = 0.25,
    union_fn=None,
) -> UnionSession:
    store, history, scene = ModelStore(), History(), FakeScene()
    store.add(make_entity("a", 0.0))
    store.add(make_entity("b", second_x))
    return UnionSession(Settings(), scene, store, history, union_fn=union_fn)


def test_union_confirmation_keeps_inputs_still_until_threshold() -> None:
    session = union_session()
    before = session.store.snapshot_bytes()
    assert session.begin("a", "b", distance=0.6) is True

    assert session.update(distance=0.58) is False

    assert session.store.snapshot_bytes() == before
    assert session.history.depth == (0, 0)


def test_inward_threshold_executes_union_once_and_is_undoable() -> None:
    session = union_session()
    session.begin("a", "b", distance=0.6)

    assert session.update(distance=0.3) is True
    assert session.update(distance=0.2) is False
    assert session.feedback is UnionFeedback.SUCCESS
    assert session.history.depth == (1, 0)
    assert len(session.store.ids()) == 1

    assert session.history.undo(session.store) is True
    assert session.store.ids() == ("a", "b")


@pytest.mark.parametrize("case", ["separate", "backend_error"])
def test_non_intersecting_and_backend_failure_rollback(case: str) -> None:
    def failure(meshes):
        raise RuntimeError("boolean engine failed")

    session = union_session(
        second_x=3.0 if case == "separate" else 0.25,
        union_fn=failure if case == "backend_error" else None,
    )
    before = session.store.snapshot_bytes(), session.history.depth

    eligible = session.begin("a", "b", distance=0.6)
    result = session.confirm() if eligible else False

    assert result is False
    assert (session.store.snapshot_bytes(), session.history.depth) == before
    assert session.feedback is UnionFeedback.RED_FAILURE
    assert session.scene.failures[-1] == ("a", "b")
