from dataclasses import dataclass
from enum import Enum, auto
from types import MappingProxyType
from typing import Mapping


class HandSide(Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
    z: float = 0.0


Landmark = Point


@dataclass(frozen=True, slots=True)
class HandObservation:
    side: HandSide
    confidence: float
    landmarks: tuple[Landmark, ...]
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class HandSignals:
    side: HandSide
    confidence: float
    extended: frozenset[str]
    index_tip: Point
    palm_center: Point
    palm_scale: float
    pinch_index: bool
    pinch_middle: bool
    pinch_pinky: bool
    is_fist: bool
    middle_tip: Point
    pinky_pinch_point: Point
    index_pinch_ratio: float
    middle_pinch_ratio: float
    pinky_pinch_ratio: float


@dataclass(frozen=True, slots=True)
class GestureFrame:
    timestamp_ms: int
    hands: Mapping[HandSide, HandSignals]

    def __post_init__(self) -> None:
        object.__setattr__(self, "hands", MappingProxyType(dict(self.hands)))


@dataclass(frozen=True, slots=True)
class ScreenSize:
    width: int
    height: int


class CommandKind(Enum):
    MOVE_ABSOLUTE = auto()
    SCROLL = auto()
    MOUSE_DOWN = auto()
    MOUSE_UP = auto()
    KEY_DOWN = auto()
    KEY_UP = auto()
    KEY_TAP = auto()
    RELEASE_ALL = auto()


@dataclass(frozen=True, slots=True)
class InputCommand:
    kind: CommandKind
    x: int | None = None
    y: int | None = None
    delta: int = 0
    button: str | None = None
    key: str | None = None
