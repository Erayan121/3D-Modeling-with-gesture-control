from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Mapping

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import (
    InteractionMode,
    Intent,
    IntentKind,
    PrimitiveKind,
    Vec2,
    midpoint,
)
from hand_modeling_demo.gestures.circles import CircleEvent, CircleRecognizer
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.gestures.poses import HandPose


PRIORITY = (
    InteractionMode.CREATE,
    InteractionMode.BOOLEAN,
    InteractionMode.DUAL_TRANSFORM,
    InteractionMode.CAMERA_PAN,
    InteractionMode.CAMERA_ZOOM,
    InteractionMode.CAMERA_ORBIT,
    InteractionMode.SINGLE_MOVE,
    InteractionMode.CIRCLE,
)


@dataclass(frozen=True, slots=True)
class InteractionFrame:
    timestamp_ms: int
    pointers: Mapping[HandSide, PointerState]
    poses: Mapping[HandSide, HandPose]
    hover_ids: Mapping[HandSide, str | None]
    pending: PrimitiveKind | None = None


class GestureInterpreter:
    camera_pose_grace_ms = 250
    camera_motion_tau_ms = 80.0
    camera_motion_deadzone = 0.0008
    camera_max_frame_delta = 0.06

    def __init__(self, settings: Settings):
        self.settings = settings
        self.mode = InteractionMode.NEUTRAL
        self._candidate = InteractionMode.NEUTRAL
        self._candidate_since_ms = 0
        self._last_positions: dict[HandSide, Vec2] = {}
        self._target_ids: tuple[str, ...] = ()
        self._circles = CircleRecognizer(settings)
        self._camera_pose_loss_since_ms: int | None = None
        self._camera_vector_velocity: Vec2 | None = None
        self._camera_scalar_velocity: float | None = None
        self._camera_motion_timestamp_ms = 0
        self._camera_pointer_gap = False

    @property
    def camera_motion_enabled(self) -> bool:
        return (
            self.mode in _CAMERA_MODES
            and self._camera_pose_loss_since_ms is None
            and not self._camera_pointer_gap
        )

    def choose_mode(
        self,
        frame: InteractionFrame,
        pending: PrimitiveKind | None = None,
    ) -> InteractionMode:
        pending = frame.pending if pending is None else pending
        left = frame.pointers.get(HandSide.LEFT)
        right = frame.pointers.get(HandSide.RIGHT)
        left_pose = frame.poses.get(HandSide.LEFT, HandPose.NEUTRAL)
        right_pose = frame.poses.get(HandSide.RIGHT, HandPose.NEUTRAL)
        if pending is not None:
            return InteractionMode.CREATE
        if left and right and left.pinched and right.pinched:
            left_target = frame.hover_ids.get(HandSide.LEFT)
            right_target = frame.hover_ids.get(HandSide.RIGHT)
            if left_target and right_target and left_target != right_target:
                return InteractionMode.BOOLEAN
            if left_target and left_target == right_target:
                return InteractionMode.DUAL_TRANSFORM
        if (
            left and right
            and not left.pinched and not right.pinched
            and left_pose is HandPose.OPEN and right_pose is HandPose.OPEN
        ):
            return InteractionMode.CAMERA_PAN
        if left and right and left_pose is HandPose.FIST and right_pose is HandPose.FIST:
            return InteractionMode.CAMERA_ZOOM
        if right and right_pose is HandPose.FIST and left_pose is not HandPose.FIST:
            return InteractionMode.CAMERA_ORBIT
        pinched = [
            side for side, pointer in frame.pointers.items()
            if pointer.pinched and frame.hover_ids.get(side)
        ]
        if len(pinched) == 1:
            return InteractionMode.SINGLE_MOVE
        if right and right_pose is HandPose.INDEX_ONLY and left is None:
            return InteractionMode.CIRCLE
        return InteractionMode.NEUTRAL

    def update(self, frame: InteractionFrame) -> tuple[Intent, ...]:
        if self.mode is not InteractionMode.NEUTRAL:
            if self._continues(frame):
                if self._camera_pose_loss_since_ms is not None:
                    self._camera_pose_loss_since_ms = None
                    if self._camera_pointer_gap:
                        self._camera_pointer_gap = False
                        self._last_positions = {
                            side: pointer.position for side, pointer in frame.pointers.items()
                        }
                        self._reset_camera_motion(frame.timestamp_ms)
                        return ()
            elif self.mode in _CAMERA_MODES:
                if self._camera_pose_loss_since_ms is None:
                    self._camera_pose_loss_since_ms = frame.timestamp_ms
                if (
                    frame.timestamp_ms - self._camera_pose_loss_since_ms
                    <= self.camera_pose_grace_ms
                ):
                    # Keep the mode during a short pose dropout, but freeze
                    # camera motion until the intended pose is confirmed again.
                    if self._has_camera_pointers(frame):
                        return ()
                    self._camera_pointer_gap = True
                    return ()
                previous = self.mode
                self.cancel()
                return (Intent(IntentKind.CANCEL, mode=previous),)
            else:
                previous = self.mode
                self.cancel()
                return (Intent(IntentKind.CANCEL, mode=previous),)
            if self.mode in _CAMERA_MODES:
                return ()
            return self._emit_active(frame)

        candidate = self.choose_mode(frame)
        if candidate is InteractionMode.NEUTRAL:
            self._candidate = InteractionMode.NEUTRAL
            self._circles.reset()
            return ()
        if candidate in (InteractionMode.CREATE, InteractionMode.BOOLEAN):
            self._activate(candidate, frame)
            return self._emit_active(frame)
        if candidate is not self._candidate:
            self._candidate = candidate
            self._candidate_since_ms = frame.timestamp_ms
            return ()
        if frame.timestamp_ms - self._candidate_since_ms < self.settings.stable_ms:
            return ()
        self._activate(candidate, frame)
        return ()

    def cancel(self) -> None:
        self.mode = InteractionMode.NEUTRAL
        self._candidate = InteractionMode.NEUTRAL
        self._candidate_since_ms = 0
        self._last_positions.clear()
        self._target_ids = ()
        self._circles.reset()
        self._camera_pose_loss_since_ms = None
        self._camera_pointer_gap = False
        self._reset_camera_motion(0)

    def _activate(self, mode: InteractionMode, frame: InteractionFrame) -> None:
        self.mode = mode
        self._candidate = InteractionMode.NEUTRAL
        self._last_positions = {
            side: pointer.position for side, pointer in frame.pointers.items()
        }
        self._target_ids = tuple(
            target for side in (HandSide.LEFT, HandSide.RIGHT)
            if (target := frame.hover_ids.get(side)) is not None
        )
        self._camera_pose_loss_since_ms = None
        self._camera_pointer_gap = False
        self._reset_camera_motion(frame.timestamp_ms)

    def _has_camera_pointers(self, frame: InteractionFrame) -> bool:
        if self.mode in (InteractionMode.CAMERA_PAN, InteractionMode.CAMERA_ZOOM):
            return (
                HandSide.LEFT in frame.pointers
                and HandSide.RIGHT in frame.pointers
            )
        if self.mode is InteractionMode.CAMERA_ORBIT:
            return HandSide.RIGHT in frame.pointers
        return False

    def _continues(self, frame: InteractionFrame) -> bool:
        left = frame.pointers.get(HandSide.LEFT)
        right = frame.pointers.get(HandSide.RIGHT)
        poses = frame.poses
        if self.mode is InteractionMode.CREATE:
            return frame.pending is not None
        if self.mode in (InteractionMode.BOOLEAN, InteractionMode.DUAL_TRANSFORM):
            return bool(left and right and left.pinched and right.pinched)
        if self.mode is InteractionMode.CAMERA_PAN:
            return bool(
                left and right
                and not left.pinched and not right.pinched
                and poses.get(HandSide.LEFT) is HandPose.OPEN
                and poses.get(HandSide.RIGHT) is HandPose.OPEN
            )
        if self.mode is InteractionMode.CAMERA_ZOOM:
            return poses.get(HandSide.LEFT) is HandPose.FIST and poses.get(HandSide.RIGHT) is HandPose.FIST
        if self.mode is InteractionMode.CAMERA_ORBIT:
            return bool(right and poses.get(HandSide.RIGHT) is HandPose.FIST and poses.get(HandSide.LEFT) is not HandPose.FIST)
        if self.mode is InteractionMode.SINGLE_MOVE:
            return sum(pointer.pinched for pointer in frame.pointers.values()) == 1
        if self.mode is InteractionMode.CIRCLE:
            return bool(right and poses.get(HandSide.RIGHT) is HandPose.INDEX_ONLY and left is None)
        return False

    def _emit_active(self, frame: InteractionFrame) -> tuple[Intent, ...]:
        positions = {side: pointer.position for side, pointer in frame.pointers.items()}
        if self.mode is InteractionMode.CAMERA_PAN:
            current = midpoint(positions[HandSide.LEFT], positions[HandSide.RIGHT])
            previous = midpoint(self._last_positions[HandSide.LEFT], self._last_positions[HandSide.RIGHT])
            self._last_positions = positions
            delta = self._filter_camera_vector(current - previous, frame.timestamp_ms)
            if delta == Vec2(0.0, 0.0):
                return ()
            return (Intent(IntentKind.CAMERA_PAN, self.mode, delta=_clean(delta)),)
        if self.mode is InteractionMode.CAMERA_ZOOM:
            current = positions[HandSide.LEFT].distance_to(positions[HandSide.RIGHT])
            previous = self._last_positions[HandSide.LEFT].distance_to(self._last_positions[HandSide.RIGHT])
            self._last_positions = positions
            scalar = self._filter_camera_scalar(current - previous, frame.timestamp_ms)
            if scalar == 0.0:
                return ()
            return (Intent(IntentKind.CAMERA_ZOOM, self.mode, scalar=scalar),)
        if self.mode is InteractionMode.CAMERA_ORBIT:
            current = positions[HandSide.RIGHT]
            previous = self._last_positions[HandSide.RIGHT]
            self._last_positions = positions
            delta = self._filter_camera_vector(current - previous, frame.timestamp_ms)
            if delta == Vec2(0.0, 0.0):
                return ()
            return (Intent(IntentKind.CAMERA_ORBIT, self.mode, delta=_clean(delta)),)
        if self.mode is InteractionMode.CIRCLE:
            event = self._circles.update(positions[HandSide.RIGHT], frame.timestamp_ms)
            if event is CircleEvent.UNDO:
                return (Intent(IntentKind.UNDO, self.mode),)
            if event is CircleEvent.REDO:
                return (Intent(IntentKind.REDO, self.mode),)
            return ()
        self._last_positions = positions
        return (
            Intent(
                IntentKind.SESSION_UPDATE,
                self.mode,
                positions=positions,
                target_ids=self._target_ids,
            ),
        )

    def _filter_camera_vector(self, raw: Vec2, timestamp_ms: int) -> Vec2:
        magnitude = raw.distance_to(Vec2(0.0, 0.0))
        if magnitude <= self.camera_motion_deadzone:
            self._camera_vector_velocity = None
            self._camera_motion_timestamp_ms = timestamp_ms
            return Vec2(0.0, 0.0)
        if magnitude > self.camera_max_frame_delta:
            scale = self.camera_max_frame_delta / magnitude
            raw = raw * scale
        elapsed_ms = max(1, min(100, timestamp_ms - self._camera_motion_timestamp_ms))
        elapsed_seconds = elapsed_ms / 1000.0
        raw_velocity = raw * (1.0 / elapsed_seconds)
        if self._camera_vector_velocity is None:
            velocity = raw_velocity
        else:
            blend = 1.0 - exp(-elapsed_ms / self.camera_motion_tau_ms)
            velocity = (
                self._camera_vector_velocity * (1.0 - blend)
                + raw_velocity * blend
            )
        self._camera_vector_velocity = velocity
        self._camera_motion_timestamp_ms = timestamp_ms
        result = velocity * elapsed_seconds
        result_magnitude = result.distance_to(Vec2(0.0, 0.0))
        if result_magnitude > self.camera_max_frame_delta:
            result = result * (self.camera_max_frame_delta / result_magnitude)
        return result

    def _filter_camera_scalar(self, raw: float, timestamp_ms: int) -> float:
        if abs(raw) <= self.camera_motion_deadzone:
            self._camera_scalar_velocity = None
            self._camera_motion_timestamp_ms = timestamp_ms
            return 0.0
        raw = max(-self.camera_max_frame_delta, min(self.camera_max_frame_delta, raw))
        elapsed_ms = max(1, min(100, timestamp_ms - self._camera_motion_timestamp_ms))
        elapsed_seconds = elapsed_ms / 1000.0
        raw_velocity = raw / elapsed_seconds
        if self._camera_scalar_velocity is None:
            velocity = raw_velocity
        else:
            blend = 1.0 - exp(-elapsed_ms / self.camera_motion_tau_ms)
            velocity = self._camera_scalar_velocity * (1.0 - blend) + raw_velocity * blend
        self._camera_scalar_velocity = velocity
        self._camera_motion_timestamp_ms = timestamp_ms
        return max(
            -self.camera_max_frame_delta,
            min(self.camera_max_frame_delta, velocity * elapsed_seconds),
        )

    def _reset_camera_motion(self, timestamp_ms: int) -> None:
        self._camera_vector_velocity = None
        self._camera_scalar_velocity = None
        self._camera_motion_timestamp_ms = timestamp_ms


def _clean(vector: Vec2) -> Vec2:
    return Vec2(round(vector.x, 12), round(vector.y, 12))


_CAMERA_MODES = frozenset(
    {
        InteractionMode.CAMERA_PAN,
        InteractionMode.CAMERA_ZOOM,
        InteractionMode.CAMERA_ORBIT,
    }
)
