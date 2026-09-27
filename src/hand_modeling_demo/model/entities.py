from __future__ import annotations

from dataclasses import dataclass, replace
import json
from math import radians

import numpy as np
import trimesh

from hand_modeling_demo.domain import PrimitiveKind, Vec3


@dataclass(frozen=True, slots=True)
class Transform:
    position: Vec3 = Vec3(0.0, 0.0, 0.0)
    scale: float = 1.0
    roll: float = 0.0

    def __post_init__(self) -> None:
        if not 0.05 <= self.scale <= 20.0:
            raise ValueError("scale must be between 0.05 and 20.0")


@dataclass(frozen=True, slots=True, eq=False)
class MeshEntity:
    entity_id: str
    kind: PrimitiveKind | None
    mesh: trimesh.Trimesh
    transform: Transform = Transform()

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id")
        if not isinstance(self.mesh, trimesh.Trimesh):
            raise TypeError("mesh")

    def with_transform(
        self,
        *,
        position: Vec3 | tuple[float, float, float] | None = None,
        scale: float | None = None,
        roll: float | None = None,
    ) -> MeshEntity:
        resolved_position = self.transform.position if position is None else (
            position if isinstance(position, Vec3) else Vec3(*position)
        )
        return replace(
            self,
            transform=Transform(
                resolved_position,
                self.transform.scale if scale is None else scale,
                self.transform.roll if roll is None else roll,
            ),
        )

    def world_mesh(self) -> trimesh.Trimesh:
        result = self.mesh.copy()
        transform = np.eye(4)
        angle = radians(self.transform.roll)
        cosine, sine = np.cos(angle), np.sin(angle)
        scale = self.transform.scale
        transform[:3, :3] = np.array(
            [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]
        ) * scale
        transform[:3, 3] = (
            self.transform.position.x,
            self.transform.position.y,
            self.transform.position.z,
        )
        result.apply_transform(transform)
        return result

    def __eq__(self, other: object) -> bool:
        return bool(
            isinstance(other, MeshEntity)
            and self.entity_id == other.entity_id
            and self.kind == other.kind
            and self.transform == other.transform
            and np.array_equal(self.mesh.vertices, other.mesh.vertices)
            and np.array_equal(self.mesh.faces, other.mesh.faces)
        )


class ModelStore:
    def __init__(self) -> None:
        self._entities: dict[str, MeshEntity] = {}

    def add(self, entity: MeshEntity) -> None:
        if entity.entity_id in self._entities:
            raise ValueError(f"duplicate entity id: {entity.entity_id}")
        self._entities[entity.entity_id] = entity

    def get(self, entity_id: str) -> MeshEntity:
        try:
            return self._entities[entity_id]
        except KeyError as exc:
            raise KeyError(f"unknown entity: {entity_id}") from exc

    def remove(self, entity_id: str) -> MeshEntity:
        try:
            return self._entities.pop(entity_id)
        except KeyError as exc:
            raise KeyError(f"unknown entity: {entity_id}") from exc

    def replace(self, entity: MeshEntity) -> None:
        if entity.entity_id not in self._entities:
            raise KeyError(f"unknown entity: {entity.entity_id}")
        self._entities[entity.entity_id] = entity

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._entities))

    def values(self) -> tuple[MeshEntity, ...]:
        return tuple(self._entities[key] for key in sorted(self._entities))

    def clear(self) -> None:
        self._entities.clear()

    def snapshot_bytes(self) -> bytes:
        chunks: list[bytes] = []
        for entity in self.values():
            metadata = {
                "id": entity.entity_id,
                "kind": entity.kind.value if entity.kind else None,
                "position": [
                    entity.transform.position.x,
                    entity.transform.position.y,
                    entity.transform.position.z,
                ],
                "scale": entity.transform.scale,
                "roll": entity.transform.roll,
            }
            chunks.extend(
                (
                    json.dumps(metadata, sort_keys=True).encode("utf-8"),
                    np.asarray(entity.mesh.vertices, dtype=np.float64).tobytes(),
                    np.asarray(entity.mesh.faces, dtype=np.int64).tobytes(),
                )
            )
        return b"\x1e".join(chunks)


def create_primitive(kind: PrimitiveKind) -> trimesh.Trimesh:
    factories = {
        PrimitiveKind.SPHERE: lambda: trimesh.creation.icosphere(subdivisions=3),
        PrimitiveKind.CUBE: lambda: trimesh.creation.box((1.0, 1.0, 1.0)),
        PrimitiveKind.CYLINDER: lambda: trimesh.creation.cylinder(0.5, 1.0, sections=48),
        PrimitiveKind.CONE: lambda: trimesh.creation.cone(0.5, 1.0, sections=48),
        PrimitiveKind.TORUS: lambda: trimesh.creation.torus(
            major_radius=0.55, minor_radius=0.18, major_sections=48, minor_sections=24
        ),
    }
    mesh = factories[kind]()
    mesh.apply_translation(-mesh.centroid)
    mesh.remove_unreferenced_vertices()
    return mesh
