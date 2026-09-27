from __future__ import annotations

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import AppState, InteractionMode, Intent, IntentKind, PrimitiveKind, Vec2
from hand_modeling_demo.gestures.interpreter import GestureInterpreter, InteractionFrame
from hand_modeling_demo.gestures.pointers import PointerSystem
from hand_modeling_demo.gestures.poses import classify_pose
from hand_modeling_demo.lifecycle import LifecycleController
from hand_modeling_demo.model.commands import History
from hand_modeling_demo.model.entities import ModelStore
from hand_modeling_demo.model.sessions import (
    CreationSession,
    SessionCoordinator,
    TransformSession,
    UnionSession,
)


class HandModelingApp:
    def __init__(self, settings: Settings, tracking, scene, window) -> None:
        self.settings = settings
        self.tracking = tracking
        self.scene = scene
        self.window = window
        self.store = ModelStore()
        self.history = History()
        self.pointer_system = PointerSystem(settings)
        self.interpreter = GestureInterpreter(settings)
        self.creation = CreationSession(settings, scene, self.store, self.history)
        self.transform = TransformSession(settings, scene, self.store, self.history)
        self.union = UnionSession(settings, scene, self.store, self.history)
        self.sessions = SessionCoordinator(self.creation, self.transform, self.union)
        self.lifecycle = LifecycleController(
            settings,
            tracking,
            tracking,
            self.sessions,
            scene,
            self.history,
        )
        self._loss_since_ms: int | None = None
        self._current_frame: InteractionFrame | None = None

    @property
    def state(self) -> AppState:
        return self.lifecycle.state

    def start(self) -> bool:
        if not self.lifecycle.start_modeling():
            self.window.show_error(self.lifecycle.last_error)
            return False
        self.window.show_modeling()
        return True

    def tracking_stable(self) -> None:
        self.lifecycle.tracking_became_stable()
        if self.lifecycle.state is AppState.MODELING_ACTIVE:
            self.window.show_modeling()

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.lifecycle.settings = settings
        self.tracking.settings = settings
        self.scene.settings = settings
        self.pointer_system = PointerSystem(settings)
        self.interpreter = GestureInterpreter(settings)
        self.creation.settings = settings
        self.transform.settings = settings
        self.union.settings = settings

    def press_digit(self, number: int) -> None:
        if self.state is not AppState.MODELING_ACTIVE:
            return
        kinds = {
            1: PrimitiveKind.SPHERE,
            2: PrimitiveKind.CUBE,
            3: PrimitiveKind.CYLINDER,
            4: PrimitiveKind.CONE,
            5: PrimitiveKind.TORUS,
        }
        if number in kinds:
            self.creation.arm(kinds[number])
            self.interpreter.cancel()

    def press_space(self) -> None:
        if self.state is AppState.MODELING_ACTIVE:
            self.interpreter.cancel()
            self.pointer_system.reset()
            self.lifecycle.pause()
            self.window.show_paused()
        elif self.state is AppState.MODELING_PAUSED:
            if not self.lifecycle.resume():
                self.window.show_error(self.lifecycle.last_error)

    def return_to_start(self) -> None:
        self.interpreter.cancel()
        self.pointer_system.reset()
        self.lifecycle.return_to_start()
        self.store.clear()
        self.window.show_start()

    def shutdown(self) -> None:
        self.interpreter.cancel()
        self.lifecycle.shutdown()
        self.store.clear()

    def fail(self, error: Exception) -> None:
        self.interpreter.cancel()
        try:
            self.lifecycle.fail(error)
        finally:
            self.window.show_error(str(error))

    def tick(self, now_ms: int) -> None:
        if self.tracking.error is not None:
            self.fail(self.tracking.error)
            return
        if self.state not in (AppState.MODELING_ACTIVE, AppState.MODELING_PAUSED):
            return
        snapshot = self.tracking.poll(now_ms)
        if self.tracking.error is not None:
            self.fail(self.tracking.error)
            return
        if not self.lifecycle.tracking_ready:
            if self.tracking.stable:
                self.tracking_stable()
            else:
                return
        if self.state is not AppState.MODELING_ACTIVE:
            return
        if not snapshot.fresh:
            if self._loss_since_ms is None:
                self._loss_since_ms = now_ms
            elif now_ms - self._loss_since_ms >= self.settings.tracking_loss_ms:
                self.sessions.suspend_for_tracking_loss()
                self.interpreter.cancel()
                self.pointer_system.reset()
            return
        self._loss_since_ms = None
        pointers = self.pointer_system.update(snapshot)
        self.scene.set_pointers(pointers)
        hover = self.scene.pick_all(pointers)
        self.scene.set_highlights(hover)
        poses = {side: classify_pose(hand) for side, hand in snapshot.hands.items()}
        self.process_interaction_frame(
            InteractionFrame(now_ms, pointers, poses, hover, self.creation.pending)
        )
        self.scene.set_camera_gesture(
            self.interpreter.mode,
            pointers,
            motion_enabled=self.interpreter.camera_motion_enabled,
        )
        self.scene.sync(self.store)

    def process_interaction_frame(self, frame: InteractionFrame) -> None:
        self._current_frame = frame
        for intent in self.interpreter.update(frame):
            self.apply_intent(intent)

    def apply_intent(self, intent: Intent) -> None:
        if intent.kind is IntentKind.CAMERA_PAN and intent.delta is not None:
            self.scene.pan(intent.delta)
        elif intent.kind is IntentKind.CAMERA_ZOOM and intent.scalar is not None:
            self.scene.zoom(intent.scalar)
        elif intent.kind is IntentKind.CAMERA_ORBIT and intent.delta is not None:
            self.scene.orbit(intent.delta)
        elif intent.kind is IntentKind.UNDO:
            self.history.undo(self.store)
        elif intent.kind is IntentKind.REDO:
            self.history.redo(self.store)
        elif intent.kind is IntentKind.SESSION_UPDATE:
            self._update_session(intent)
        elif intent.kind is IntentKind.CANCEL:
            self._end_session(intent.mode)

    def mouse_orbit(self, delta_x: float, delta_y: float) -> None:
        if self.state is AppState.MODELING_ACTIVE:
            self.scene.orbit(Vec2(delta_x, delta_y))

    def mouse_pan(self, delta_x: float, delta_y: float) -> None:
        if self.state is AppState.MODELING_ACTIVE:
            self.scene.pan(Vec2(delta_x, delta_y))

    def mouse_zoom(self, amount: float) -> None:
        if self.state is AppState.MODELING_ACTIVE:
            self.scene.zoom(amount)

    def committed_snapshot(self) -> bytes:
        return self.store.snapshot_bytes()

    def run_smoke(self) -> dict[str, object]:
        report = {
            "state": self.state.value,
            "camera_open": bool(self.tracking.is_open),
            "tracking_running": bool(self.tracking.running),
            "clean_shutdown": False,
        }
        self.shutdown()
        report["clean_shutdown"] = self.state is AppState.SHUTDOWN
        return report

    def _update_session(self, intent: Intent) -> None:
        frame = self._current_frame
        if frame is None:
            return
        positions = dict(intent.positions)
        if intent.mode is InteractionMode.CREATE:
            if HandSide.LEFT not in positions or HandSide.RIGHT not in positions:
                self.creation.suspend()
                return
            left = frame.pointers[HandSide.LEFT]
            right = frame.pointers[HandSide.RIGHT]
            if self.creation.active and not (left.pinched and right.pinched):
                self.creation.release(HandSide.LEFT if not left.pinched else HandSide.RIGHT)
                if self.creation.pending is None:
                    self.interpreter.cancel()
            else:
                self.creation.update(left, right)
        elif intent.mode is InteractionMode.SINGLE_MOVE:
            pinched = [side for side, item in frame.pointers.items() if item.pinched]
            if not self.transform.active and pinched and intent.target_ids:
                side = pinched[0]
                self.transform.begin(intent.target_ids[0], side, positions[side])
            self.transform.update(positions, dict(frame.hover_ids))
        elif intent.mode is InteractionMode.DUAL_TRANSFORM:
            if not self.transform.active and intent.target_ids:
                self.transform.begin(intent.target_ids[0], HandSide.RIGHT, positions[HandSide.RIGHT])
            self.transform.add_hand(HandSide.LEFT, positions[HandSide.LEFT])
            self.transform.add_hand(HandSide.RIGHT, positions[HandSide.RIGHT])
            self.transform.update(positions, dict(frame.hover_ids))
        elif intent.mode is InteractionMode.BOOLEAN and len(intent.target_ids) >= 2:
            distance = positions[HandSide.LEFT].distance_to(positions[HandSide.RIGHT])
            if self.union.feedback.value not in ("ready", "success"):
                self.union.begin(intent.target_ids[0], intent.target_ids[1], distance=distance)
            self.union.update(distance=distance)

    def _end_session(self, mode: InteractionMode) -> None:
        if mode is InteractionMode.CREATE:
            self.creation.release(HandSide.LEFT)
        elif mode in (InteractionMode.SINGLE_MOVE, InteractionMode.DUAL_TRANSFORM):
            frame = self._current_frame
            remaining = set(frame.pointers) if frame else set()
            for side in (HandSide.LEFT, HandSide.RIGHT):
                if side not in remaining or not frame.pointers[side].pinched:
                    self.transform.remove_hand(side)
        elif mode is InteractionMode.BOOLEAN:
            self.union.release()
