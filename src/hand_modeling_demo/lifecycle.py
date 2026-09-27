from __future__ import annotations

from typing import Protocol

from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import AppState


class LifecycleError(RuntimeError):
    pass


class CameraPort(Protocol):
    def open(self, index: int) -> None: ...
    def close(self) -> None: ...


class TrackerPort(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class SessionPort(Protocol):
    def cancel_all(self) -> None: ...


class ClearablePort(Protocol):
    def clear(self) -> None: ...


class LifecycleController:
    def __init__(
        self,
        settings: Settings,
        camera: CameraPort,
        tracker: TrackerPort,
        sessions: SessionPort,
        scene: ClearablePort,
        history: ClearablePort,
    ) -> None:
        self.settings = settings
        self.camera = camera
        self.tracker = tracker
        self.sessions = sessions
        self.scene = scene
        self.history = history
        self.state = AppState.START
        self.last_error = ""
        self.tracking_ready = False
        self._runtime_started = False

    def show_start(self) -> None:
        if self.state is not AppState.SHUTDOWN:
            self.state = AppState.START

    def show_tutorial(self) -> None:
        self._require_non_modeling()
        self.state = AppState.TUTORIAL

    def show_settings(self) -> None:
        self._require_non_modeling()
        self.state = AppState.SETTINGS

    def start_modeling(self) -> bool:
        if self.state is AppState.SHUTDOWN:
            return False
        self.last_error = ""
        self.tracking_ready = False
        try:
            self._start_runtime()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                self._release_runtime(force=True)
            except LifecycleError:
                pass
            self.state = AppState.START
            return False
        self.state = AppState.MODELING_ACTIVE
        return True

    def pause(self) -> None:
        if self.state is AppState.SHUTDOWN:
            return
        if self.state not in (AppState.MODELING_ACTIVE, AppState.MODELING_PAUSED):
            return
        self.tracking_ready = False
        try:
            self._release_runtime()
        finally:
            self.state = AppState.MODELING_PAUSED

    def resume(self) -> bool:
        if self.state is not AppState.MODELING_PAUSED or self._runtime_started:
            return False
        self.last_error = ""
        self.tracking_ready = False
        try:
            self._start_runtime()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                self._release_runtime(force=True)
            except LifecycleError:
                pass
            return False
        return True

    def tracking_became_stable(self) -> None:
        if self._runtime_started and self.state in (
            AppState.MODELING_ACTIVE,
            AppState.MODELING_PAUSED,
        ):
            self.tracking_ready = True
            self.state = AppState.MODELING_ACTIVE

    def return_to_start(self) -> None:
        if self.state is AppState.SHUTDOWN:
            return
        release_error: LifecycleError | None = None
        if self._runtime_started or self.state in (
            AppState.MODELING_ACTIVE,
            AppState.MODELING_PAUSED,
            AppState.ERROR,
        ):
            try:
                self._release_runtime(force=self._runtime_started)
            except LifecycleError as exc:
                release_error = exc
        self.scene.clear()
        self.history.clear()
        self.tracking_ready = False
        self.state = AppState.START
        if release_error is not None:
            raise release_error

    def fail(self, error: Exception) -> None:
        self.last_error = str(error)
        try:
            self._release_runtime(force=True)
        finally:
            self.tracking_ready = False
            self.state = AppState.ERROR

    def shutdown(self) -> None:
        if self.state is AppState.SHUTDOWN:
            return
        try:
            self._release_runtime(force=self._runtime_started)
        finally:
            self.tracking_ready = False
            self.state = AppState.SHUTDOWN

    def _start_runtime(self) -> None:
        self.camera.open(self.settings.camera_index)
        self.tracker.start()
        self._runtime_started = True

    def _release_runtime(self, *, force: bool = False) -> None:
        if not self._runtime_started and not force:
            return
        self._runtime_started = False
        first: Exception | None = None
        for operation in (
            self.sessions.cancel_all,
            self.tracker.stop,
            self.camera.close,
        ):
            try:
                operation()
            except Exception as exc:
                first = first or exc
        if first is not None:
            raise LifecycleError(str(first)) from first

    def _require_non_modeling(self) -> None:
        if self.state in (
            AppState.MODELING_ACTIVE,
            AppState.MODELING_PAUSED,
            AppState.SHUTDOWN,
        ):
            raise LifecycleError(f"cannot navigate from {self.state.value}")
