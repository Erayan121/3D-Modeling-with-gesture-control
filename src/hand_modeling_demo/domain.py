from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import hypot
from types import MappingProxyType
from typing import Mapping

from gesture_control.core.models import HandSide, HandSignals, Point


class AppState(Enum):
    START = "start"
    TUTORIAL = "tutorial"
    SETTINGS = "settings"
    MODELING_ACTIVE = "modeling_active"
    MODELING_PAUSED = "modeling_paused"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class PrimitiveKind(Enum):
    SPHERE = "sphere"
    CUBE = "cube"
    CYLINDER = "cylinder"
    CONE = "cone"
    TORUS = "torus"


class InteractionMode(Enum):
    NEUTRAL = "neutral"
    CREATE = "create"
    BOOLEAN = "boolean"
    DUAL_TRANSFORM = "dual_transform"
    CAMERA_PAN = "camera_pan"
    CAMERA_ZOOM = "camera_zoom"
    CAMERA_ORBIT = "camera_orbit"
    SINGLE_MOVE = "single_move"
    CIRCLE = "circle"


class IntentKind(Enum):
    SESSION_UPDATE = "session_update"
    CAMERA_PAN = "camera_pan"
    CAMERA_ZOOM = "camera_zoom"
    CAMERA_ORBIT = "camera_orbit"
    UNDO = "undo"
    REDO = "redo"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def distance_to(self, other: Vec2) -> float:
        return hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class Intent:
    kind: IntentKind
    mode: InteractionMode = InteractionMode.NEUTRAL
    positions: Mapping[HandSide, Vec2] = field(default_factory=dict)
    target_ids: tuple[str, ...] = ()
    delta: Vec2 | None = None
    scalar: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "positions", MappingProxyType(dict(self.positions)))


@dataclass(frozen=True, slots=True)
class TrackedHand:
    signals: HandSignals
    thumb_tip: Point
    timestamp_ms: int
    camera_fist: bool | None = None


@dataclass(frozen=True, slots=True)
class TrackingSnapshot:
    timestamp_ms: int
    hands: Mapping[HandSide, TrackedHand]
    fresh: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "hands", MappingProxyType(dict(self.hands)))


def midpoint(first: Vec2, second: Vec2) -> Vec2:
    return Vec2((first.x + second.x) / 2.0, (first.y + second.y) / 2.0)
