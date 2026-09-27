from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from gesture_control.core.models import HandSide, Point
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import TrackedHand, TrackingSnapshot, Vec2


@dataclass(frozen=True, slots=True)
class PointerState:
    side: HandSide
    position: Vec2
    pinched: bool
    timestamp_ms: int
    visible: bool = True


class PointerProjector:
    def __init__(self, control_region_fraction: float):
        if not 0.0 < control_region_fraction <= 1.0:
            raise ValueError("control_region_fraction")
        self.fraction = control_region_fraction
        self.margin = (1.0 - control_region_fraction) / 2.0

    def to_viewport(self, point: Point | Vec2) -> Vec2:
        return Vec2(
            _clamp((point.x - self.margin) / self.fraction),
            _clamp((point.y - self.margin) / self.fraction),
        )


class PointerFilter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projector = PointerProjector(settings.control_region_fraction)
        self._pinched = False
        self._release_since_ms: int | None = None
        self._position: Vec2 | None = None

    def update(self, hand: TrackedHand) -> PointerState:
        ratio = hand.signals.index_pinch_ratio
        if self._pinched:
            if ratio < self.settings.pinch_release_ratio:
                self._release_since_ms = None
            elif self._release_since_ms is None:
                self._release_since_ms = hand.timestamp_ms
            elif hand.timestamp_ms - self._release_since_ms >= self.settings.pinch_release_grace_ms:
                self._pinched = False
                self._release_since_ms = None
        else:
            self._pinched = ratio <= self.settings.pinch_enter_ratio
            self._release_since_ms = None

        raw = target_point(hand, self._pinched)
        target = self.projector.to_viewport(raw)
        if self._position is None:
            position = target
        elif self._position.distance_to(target) <= self.settings.pointer_deadzone:
            position = self._position
        else:
            strength = self.settings.pointer_smoothing
            position = self._position * strength + target * (1.0 - strength)
        self._position = position
        return PointerState(
            hand.signals.side,
            position,
            self._pinched,
            hand.timestamp_ms,
        )

    def reset(self) -> None:
        self._pinched = False
        self._release_since_ms = None
        self._position = None


class PointerSystem:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._filters = {
            HandSide.LEFT: PointerFilter(settings),
            HandSide.RIGHT: PointerFilter(settings),
        }

    def update(self, snapshot: TrackingSnapshot) -> Mapping[HandSide, PointerState]:
        visible: dict[HandSide, PointerState] = {}
        for side, pointer_filter in self._filters.items():
            hand = snapshot.hands.get(side)
            if hand is None or snapshot.timestamp_ms - hand.timestamp_ms > self.settings.tracking_loss_ms:
                pointer_filter.reset()
                continue
            visible[side] = pointer_filter.update(hand)
        return visible

    def reset(self) -> None:
        for pointer_filter in self._filters.values():
            pointer_filter.reset()


def target_point(hand: TrackedHand, pinched: bool) -> Vec2:
    signals = hand.signals
    if pinched:
        return Vec2(
            (signals.index_tip.x + hand.thumb_tip.x) / 2.0,
            (signals.index_tip.y + hand.thumb_tip.y) / 2.0,
        )
    return Vec2(signals.index_tip.x, signals.index_tip.y)


def _clamp(value: float) -> float:
    if abs(value) < 1e-12:
        return 0.0
    if abs(value - 1.0) < 1e-12:
        return 1.0
    return max(0.0, min(1.0, value))
