from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hand_modeling_demo.model.entities import MeshEntity, ModelStore, Transform


class Command(Protocol):
    def apply(self, store: ModelStore) -> None: ...
    def revert(self, store: ModelStore) -> None: ...


@dataclass(frozen=True, slots=True)
class CreateCommand:
    entity: MeshEntity

    def apply(self, store: ModelStore) -> None:
        store.add(self.entity)

    def revert(self, store: ModelStore) -> None:
        store.remove(self.entity.entity_id)


@dataclass(frozen=True, slots=True)
class TransformCommand:
    entity_id: str
    before: Transform
    after: Transform

    def apply(self, store: ModelStore) -> None:
        current = store.get(self.entity_id)
        store.replace(MeshEntity(current.entity_id, current.kind, current.mesh, self.after))

    def revert(self, store: ModelStore) -> None:
        current = store.get(self.entity_id)
        store.replace(MeshEntity(current.entity_id, current.kind, current.mesh, self.before))


@dataclass(frozen=True, slots=True)
class UnionCommand:
    originals: tuple[MeshEntity, MeshEntity]
    result: MeshEntity

    def apply(self, store: ModelStore) -> None:
        first, second = self.originals
        store.get(first.entity_id)
        store.get(second.entity_id)
        if self.result.entity_id in store.ids():
            raise ValueError(f"duplicate entity id: {self.result.entity_id}")
        removed: list[MeshEntity] = []
        try:
            removed.append(store.remove(first.entity_id))
            removed.append(store.remove(second.entity_id))
            store.add(self.result)
        except Exception:
            for item in removed:
                if item.entity_id not in store.ids():
                    store.add(item)
            raise

    def revert(self, store: ModelStore) -> None:
        store.get(self.result.entity_id)
        if any(item.entity_id in store.ids() for item in self.originals):
            raise ValueError("cannot restore union inputs over existing entities")
        result = store.remove(self.result.entity_id)
        try:
            for item in self.originals:
                store.add(item)
        except Exception:
            for item in self.originals:
                if item.entity_id in store.ids():
                    store.remove(item.entity_id)
            store.add(result)
            raise


class History:
    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    @property
    def depth(self) -> tuple[int, int]:
        return len(self._undo), len(self._redo)

    def execute(self, command: Command, store: ModelStore) -> None:
        command.apply(store)
        self._undo.append(command)
        self._redo.clear()

    def undo(self, store: ModelStore) -> bool:
        if not self._undo:
            return False
        command = self._undo[-1]
        command.revert(store)
        self._undo.pop()
        self._redo.append(command)
        return True

    def redo(self, store: ModelStore) -> bool:
        if not self._redo:
            return False
        command = self._redo[-1]
        command.apply(store)
        self._redo.pop()
        self._undo.append(command)
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
