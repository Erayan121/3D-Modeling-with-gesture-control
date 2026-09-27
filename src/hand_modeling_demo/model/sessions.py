from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from math import atan2, degrees

import trimesh

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import PrimitiveKind, Vec2, Vec3, midpoint
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.model.commands import CreateCommand, History
from hand_modeling_demo.model.commands import TransformCommand, UnionCommand
from hand_modeling_demo.model.entities import MeshEntity, ModelStore, Transform, create_primitive


@dataclass(frozen=True, slots=True)
class CreationPreview:
    entity_id: str
    kind: PrimitiveKind
    center: Vec2
    world_center: Vec3
    scale: float

    def to_entity(self) -> MeshEntity:
        return MeshEntity(
            self.entity_id,
            self.kind,
            create_primitive(self.kind),
            Transform(self.world_center, self.scale),
        )


class CreationSession:
    preview_epsilon = 0.04

    def __init__(
        self,
        settings: Settings,
        scene,
        store: ModelStore,
        history: History,
    ) -> None:
        self.settings = settings
        self.scene = scene
        self.store = store
        self.history = history
        self.pending: PrimitiveKind | None = None
        self.waiting_center: Vec2 | None = None
        self.preview: CreationPreview | None = None
        self.active = False
        self.initial_distance = 0.0
        self.outward_distance = 0.0
        self._next_id = 1

    def arm(self, kind: PrimitiveKind) -> None:
        if self.preview is not None:
            self._clear_preview()
        self.pending = kind
        self.waiting_center = None
        self.active = False
        self.initial_distance = 0.0
        self.outward_distance = 0.0

    def update(self, left: PointerState, right: PointerState) -> None:
        if self.pending is None:
            return
        center = midpoint(left.position, right.position)
        self.waiting_center = center
        distance = left.position.distance_to(right.position)
        if not self.active:
            self._show_seed(center)
            if not (left.pinched and right.pinched):
                return
            self.active = True
            self.initial_distance = distance
            entity_id = f"{self.pending.value}-{self._next_id:04d}"
            self._next_id += 1
            world_center = self.scene.screen_plane_point(
                center,
                depth=float(getattr(self.scene, "distance", 12.0)),
            )
            self.preview = CreationPreview(
                entity_id,
                self.pending,
                center,
                world_center,
                self.preview_epsilon,
            )
            self.scene.set_preview(self.preview)
            return
        if not (left.pinched and right.pinched):
            return
        self.outward_distance = max(0.0, distance - self.initial_distance)
        self.preview = replace(self.preview, scale=self._scale(distance))
        self.scene.set_preview(self.preview)

    def release(self, side: HandSide) -> None:
        del side
        if not self.active:
            return
        if self.preview is not None and self.outward_distance >= self.settings.create_min_pull:
            self.history.execute(CreateCommand(self.preview.to_entity()), self.store)
            self.cancel()
            return
        self.active = False
        self.initial_distance = 0.0
        self.outward_distance = 0.0
        if self.waiting_center is not None:
            self._show_seed(self.waiting_center)

    def suspend(self) -> None:
        self._clear_preview()
        self.waiting_center = None
        self.active = False
        self.initial_distance = 0.0
        self.outward_distance = 0.0

    def cancel(self) -> None:
        self._clear_preview()
        self.pending = None
        self.waiting_center = None
        self.active = False
        self.initial_distance = 0.0
        self.outward_distance = 0.0

    def _scale(self, current_distance: float) -> float:
        outward = max(0.0, current_distance - self.initial_distance)
        return max(self.preview_epsilon, outward * self.settings.create_scale_gain)

    def _show_seed(self, center: Vec2) -> None:
        if self.pending is None:
            return
        world_center = self.scene.screen_plane_point(
            center,
            depth=float(getattr(self.scene, "distance", 12.0)),
        )
        self.preview = CreationPreview(
            f"pending-{self.pending.value}",
            self.pending,
            center,
            world_center,
            self.preview_epsilon,
        )
        self.scene.set_preview(self.preview)

    def _clear_preview(self) -> None:
        if self.preview is not None:
            self.scene.set_preview(None)
        self.preview = None


class TransformSession:
    def __init__(
        self,
        settings: Settings,
        scene,
        store: ModelStore,
        history: History,
    ) -> None:
        self.settings = settings
        self.scene = scene
        self.store = store
        self.history = history
        self.entity_id: str | None = None
        self.original_transform: Transform | None = None
        self.original_depth = 0.0
        self._base_transform: Transform | None = None
        self._base_positions: dict[HandSide, Vec2] = {}
        self._current_positions: dict[HandSide, Vec2] = {}

    @property
    def active(self) -> bool:
        return self.entity_id is not None

    @property
    def current_transform(self) -> Transform:
        if self.entity_id is None:
            raise RuntimeError("transform session is not active")
        return self.store.get(self.entity_id).transform

    @property
    def current_depth(self) -> float:
        return self.scene.depth_of(self.current_transform.position)

    def begin(self, entity_id: str, side: HandSide, pointer: Vec2) -> None:
        if self.active:
            raise RuntimeError("transform session is already active")
        entity = self.store.get(entity_id)
        self.entity_id = entity_id
        self.original_transform = entity.transform
        self.original_depth = self.scene.depth_of(entity.transform.position)
        self._current_positions = {side: pointer}
        self._rebase()

    def update(
        self,
        positions: dict[HandSide, Vec2],
        hover_ids: dict[HandSide, str] | None = None,
    ) -> None:
        del hover_ids
        if not self.active or self._base_transform is None:
            return
        active_positions = {
            side: position for side, position in positions.items()
            if side in self._current_positions
        }
        if set(active_positions) != set(self._current_positions):
            return
        self._current_positions = dict(active_positions)
        if len(active_positions) == 1:
            side = next(iter(active_positions))
            start_world = self.scene.screen_plane_point(
                self._base_positions[side], self.original_depth
            )
            now_world = self.scene.screen_plane_point(active_positions[side], self.original_depth)
            gain = self.settings.model_move_gain
            base = self._base_transform.position
            position = Vec3(
                base.x + (now_world.x - start_world.x) * gain,
                base.y + (now_world.y - start_world.y) * gain,
                base.z + (now_world.z - start_world.z) * gain,
            )
            updated = Transform(position, self._base_transform.scale, self._base_transform.roll)
        else:
            start_left = self._base_positions[HandSide.LEFT]
            start_right = self._base_positions[HandSide.RIGHT]
            now_left = active_positions[HandSide.LEFT]
            now_right = active_positions[HandSide.RIGHT]
            start_mid = midpoint(start_left, start_right)
            now_mid = midpoint(now_left, now_right)
            start_world = self.scene.screen_plane_point(start_mid, self.original_depth)
            now_world = self.scene.screen_plane_point(now_mid, self.original_depth)
            base = self._base_transform.position
            gain = self.settings.model_move_gain
            position = Vec3(
                base.x + (now_world.x - start_world.x) * gain,
                base.y + (now_world.y - start_world.y) * gain,
                base.z + (now_world.z - start_world.z) * gain,
            )
            start_distance = max(start_left.distance_to(start_right), 1e-6)
            ratio = now_left.distance_to(now_right) / start_distance
            scale = _clamp(
                self._base_transform.scale * ratio * self.settings.model_scale_gain,
                0.05,
                20.0,
            )
            angle = degrees(_line_angle(now_left, now_right) - _line_angle(start_left, start_right))
            updated = Transform(
                position,
                scale,
                self._base_transform.roll + angle * self.settings.model_rotate_gain,
            )
        entity = self.store.get(self.entity_id)
        self.store.replace(MeshEntity(entity.entity_id, entity.kind, entity.mesh, updated))

    def add_hand(self, side: HandSide, pointer: Vec2) -> None:
        if not self.active or side in self._current_positions:
            return
        self._current_positions[side] = pointer
        self._rebase()

    def remove_hand(self, side: HandSide) -> None:
        if not self.active or side not in self._current_positions:
            return
        self._current_positions.pop(side)
        if self._current_positions:
            self._rebase()
            return
        entity_id = self.entity_id
        before = self.original_transform
        after = self.current_transform
        self._clear()
        if before is not None and after != before:
            self.history.execute(TransformCommand(entity_id, before, after), self.store)

    def cancel(self) -> None:
        if self.active and self.original_transform is not None:
            entity = self.store.get(self.entity_id)
            self.store.replace(
                MeshEntity(entity.entity_id, entity.kind, entity.mesh, self.original_transform)
            )
        self._clear()

    def _rebase(self) -> None:
        self._base_transform = self.current_transform
        self._base_positions = dict(self._current_positions)
        self.original_depth = self.scene.depth_of(self._base_transform.position)

    def _clear(self) -> None:
        self.entity_id = None
        self.original_transform = None
        self.original_depth = 0.0
        self._base_transform = None
        self._base_positions.clear()
        self._current_positions.clear()


class UnionFeedback(Enum):
    NONE = "none"
    READY = "ready"
    RED_FAILURE = "red_failure"
    SUCCESS = "success"


class UnionSession:
    def __init__(
        self,
        settings: Settings,
        scene,
        store: ModelStore,
        history: History,
        *,
        intersection_fn=None,
        union_fn=None,
    ) -> None:
        self.settings = settings
        self.scene = scene
        self.store = store
        self.history = history
        self._intersection_fn = intersection_fn or _intersection
        self._union_fn = union_fn or _union
        self.feedback = UnionFeedback.NONE
        self._originals: tuple[MeshEntity, MeshEntity] | None = None
        self._world_meshes: tuple[trimesh.Trimesh, trimesh.Trimesh] | None = None
        self._initial_distance = 0.0
        self._eligible = False
        self._triggered = False
        self._next_id = 1

    def begin(self, first_id: str, second_id: str, *, distance: float) -> bool:
        self.cancel(reset_feedback=True)
        if first_id == second_id:
            return self._reject((first_id, second_id))
        first, second = self.store.get(first_id), self.store.get(second_id)
        meshes = (first.world_mesh(), second.world_mesh())
        if not all(mesh.is_watertight and mesh.volume > 0 for mesh in meshes):
            return self._reject((first_id, second_id))
        if not _bounds_overlap(meshes[0], meshes[1]):
            return self._reject((first_id, second_id))
        try:
            intersects = self._intersection_fn(meshes)
        except Exception:
            return self._reject((first_id, second_id))
        if not intersects:
            return self._reject((first_id, second_id))
        self._originals = (first, second)
        self._world_meshes = meshes
        self._initial_distance = distance
        self._eligible = True
        self.feedback = UnionFeedback.READY
        return True

    def update(self, *, distance: float) -> bool:
        if not self._eligible or self._triggered:
            return False
        if self._initial_distance - distance < self.settings.union_confirm_inward:
            return False
        return self.confirm()

    def confirm(self) -> bool:
        if not self._eligible or self._triggered or self._originals is None or self._world_meshes is None:
            return False
        self._triggered = True
        ids = tuple(item.entity_id for item in self._originals)
        try:
            mesh = self._union_fn(self._world_meshes)
            if not isinstance(mesh, trimesh.Trimesh) or not mesh.is_watertight or mesh.volume <= 0:
                raise ValueError("union did not produce a closed solid")
            result = MeshEntity(
                f"union-{self._next_id:04d}",
                None,
                mesh.copy(),
                Transform(),
            )
            self._next_id += 1
            self.history.execute(UnionCommand(self._originals, result), self.store)
        except Exception:
            self.feedback = UnionFeedback.RED_FAILURE
            self.scene.show_union_failure(ids)
            return False
        self.feedback = UnionFeedback.SUCCESS
        return True

    def inputs_snapshot_bytes(self) -> bytes:
        return self.store.snapshot_bytes()

    def release(self) -> None:
        self._eligible = False
        self._originals = None
        self._world_meshes = None

    def cancel(self, *, reset_feedback: bool = False) -> None:
        self._eligible = False
        self._triggered = False
        self._originals = None
        self._world_meshes = None
        self._initial_distance = 0.0
        if reset_feedback:
            self.feedback = UnionFeedback.NONE

    def _reject(self, ids: tuple[str, str]) -> bool:
        self.feedback = UnionFeedback.RED_FAILURE
        self.scene.show_union_failure(ids)
        return False


class SessionCoordinator:
    def __init__(
        self,
        creation: CreationSession,
        transform: TransformSession,
        union: UnionSession,
    ) -> None:
        self.creation = creation
        self.transform = transform
        self.union = union

    def cancel_all(self) -> None:
        self.creation.cancel()
        self.transform.cancel()
        self.union.cancel(reset_feedback=True)

    def suspend_for_tracking_loss(self) -> None:
        self.creation.suspend()
        self.transform.cancel()
        self.union.cancel(reset_feedback=True)


def _line_angle(first: Vec2, second: Vec2) -> float:
    return atan2(second.y - first.y, second.x - first.x)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _intersection(meshes) -> bool:
    result = trimesh.boolean.intersection(list(meshes), engine="manifold")
    return bool(isinstance(result, trimesh.Trimesh) and result.volume > 1e-8)


def _bounds_overlap(first: trimesh.Trimesh, second: trimesh.Trimesh) -> bool:
    return all(
        first.bounds[0][axis] < second.bounds[1][axis]
        and second.bounds[0][axis] < first.bounds[1][axis]
        for axis in range(3)
    )


def _union(meshes):
    return trimesh.boolean.union(list(meshes), engine="manifold")
