import numpy as np
import pytest

from hand_modeling_demo.domain import PrimitiveKind, Vec3
from hand_modeling_demo.model.commands import (
    CreateCommand,
    History,
    TransformCommand,
    UnionCommand,
)
from hand_modeling_demo.model.entities import MeshEntity, ModelStore, Transform, create_primitive


def entity(
    entity_id: str,
    *,
    kind: PrimitiveKind = PrimitiveKind.CUBE,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> MeshEntity:
    return MeshEntity(
        entity_id,
        kind,
        create_primitive(kind),
        Transform(Vec3(*position)),
    )


@pytest.mark.parametrize("kind", list(PrimitiveKind))
def test_every_primitive_is_watertight_centered_and_positive(kind: PrimitiveKind) -> None:
    mesh = create_primitive(kind)

    assert mesh.is_watertight
    assert mesh.volume > 0
    assert mesh.centroid == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)


def test_store_rejects_duplicate_ids_without_replacing_original() -> None:
    store = ModelStore()
    original = entity("a")
    store.add(original)

    with pytest.raises(ValueError, match="a"):
        store.add(entity("a", kind=PrimitiveKind.SPHERE))

    assert store.get("a") == original


def test_new_command_after_undo_clears_redo() -> None:
    store, history = ModelStore(), History()
    history.execute(CreateCommand(entity("a")), store)
    assert history.undo(store) is True

    history.execute(CreateCommand(entity("b")), store)

    assert history.redo(store) is False
    assert store.ids() == ("b",)


def test_transform_command_round_trips_exact_state() -> None:
    store, history = ModelStore(), History()
    before = entity("a")
    store.add(before)
    after = before.with_transform(position=(2.0, 1.0, 0.0), scale=1.5, roll=30.0)

    history.execute(TransformCommand("a", before.transform, after.transform), store)
    assert store.get("a") == after
    assert history.undo(store) is True
    assert store.get("a") == before
    assert history.redo(store) is True
    assert store.get("a") == after


def test_union_command_restores_both_originals_and_reuses_result() -> None:
    store, history = ModelStore(), History()
    first, second = entity("a"), entity("b", position=(0.25, 0.0, 0.0))
    result = entity("union", kind=PrimitiveKind.SPHERE)
    store.add(first)
    store.add(second)

    history.execute(UnionCommand((first, second), result), store)
    assert store.ids() == ("union",)
    assert history.undo(store) is True
    assert store.ids() == ("a", "b")
    assert history.redo(store) is True
    assert store.get("union") == result


def test_failed_command_does_not_enter_history() -> None:
    store, history = ModelStore(), History()
    store.add(entity("a"))

    with pytest.raises(ValueError, match="a"):
        history.execute(CreateCommand(entity("a")), store)

    assert history.depth == (0, 0)


def test_snapshot_bytes_change_with_transform_and_restore_exactly() -> None:
    store = ModelStore()
    item = entity("a")
    store.add(item)
    before = store.snapshot_bytes()
    store.replace(item.with_transform(position=(1.0, 0.0, 0.0)))
    assert store.snapshot_bytes() != before
    store.replace(item)
    assert store.snapshot_bytes() == before
