from dataclasses import dataclass, field

import pytest

from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import AppState
from hand_modeling_demo.lifecycle import LifecycleController, LifecycleError


@dataclass
class FakeCamera:
    is_open: bool = False
    open_count: int = 0
    close_count: int = 0
    open_error: Exception | None = None
    events: list[str] = field(default_factory=list)

    def open(self, index: int) -> None:
        self.events.append(f"camera.open:{index}")
        self.open_count += 1
        if self.open_error:
            raise self.open_error
        self.is_open = True

    def close(self) -> None:
        self.events.append("camera.close")
        self.close_count += 1
        self.is_open = False


@dataclass
class FakeTracker:
    running: bool = False
    start_error: Exception | None = None
    events: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.events.append("tracker.start")
        if self.start_error:
            raise self.start_error
        self.running = True

    def stop(self) -> None:
        self.events.append("tracker.stop")
        self.running = False


@dataclass
class FakeSessions:
    cancel_count: int = 0
    events: list[str] = field(default_factory=list)

    def cancel_all(self) -> None:
        self.events.append("sessions.cancel")
        self.cancel_count += 1


@dataclass
class FakeClearable:
    clear_count: int = 0

    def clear(self) -> None:
        self.clear_count += 1


@dataclass
class Resources:
    camera: FakeCamera = field(default_factory=FakeCamera)
    tracker: FakeTracker = field(default_factory=FakeTracker)
    sessions: FakeSessions = field(default_factory=FakeSessions)
    scene: FakeClearable = field(default_factory=FakeClearable)
    history: FakeClearable = field(default_factory=FakeClearable)

    def controller(self, *, camera_index: int = 0) -> LifecycleController:
        return LifecycleController(
            Settings(camera_index=camera_index), self.camera, self.tracker,
            self.sessions, self.scene, self.history,
        )


def test_non_modeling_pages_never_open_camera() -> None:
    resources = Resources()
    controller = resources.controller()

    controller.show_tutorial()
    controller.show_start()
    controller.show_settings()
    controller.return_to_start()

    assert resources.camera.open_count == 0
    assert controller.state is AppState.START


def test_start_opens_configured_camera_and_tracker() -> None:
    resources = Resources()
    controller = resources.controller(camera_index=2)

    assert controller.start_modeling() is True

    assert resources.camera.events == ["camera.open:2"]
    assert resources.tracker.events == ["tracker.start"]
    assert controller.state is AppState.MODELING_ACTIVE
    assert controller.tracking_ready is False


def test_resume_waits_for_fresh_stable_tracking() -> None:
    resources = Resources()
    controller = resources.controller()
    controller.start_modeling()
    controller.pause()

    assert controller.resume() is True
    assert controller.state is AppState.MODELING_PAUSED
    assert resources.camera.is_open and resources.tracker.running

    controller.tracking_became_stable()

    assert controller.state is AppState.MODELING_ACTIVE
    assert controller.tracking_ready is True


def test_failed_open_returns_to_start_and_closes_every_resource() -> None:
    resources = Resources()
    resources.camera.open_error = RuntimeError("camera 2 unavailable")
    controller = resources.controller(camera_index=2)

    assert controller.start_modeling() is False

    assert controller.state is AppState.START
    assert "camera 2" in controller.last_error
    assert resources.tracker.running is False
    assert resources.camera.is_open is False
    assert resources.sessions.cancel_count == 1


def test_pause_cancels_before_tracker_and_camera_release() -> None:
    events: list[str] = []
    resources = Resources(
        camera=FakeCamera(events=events),
        tracker=FakeTracker(events=events),
        sessions=FakeSessions(events=events),
    )
    controller = resources.controller()
    controller.start_modeling()
    events.clear()

    controller.pause()

    assert events == ["sessions.cancel", "tracker.stop", "camera.close"]
    assert controller.state is AppState.MODELING_PAUSED


def test_return_to_start_discards_scene_and_history() -> None:
    resources = Resources()
    controller = resources.controller()
    controller.start_modeling()

    controller.return_to_start()

    assert controller.state is AppState.START
    assert resources.scene.clear_count == 1
    assert resources.history.clear_count == 1


def test_cleanup_attempts_every_operation_and_reports_first_error() -> None:
    resources = Resources()
    controller = resources.controller()
    controller.start_modeling()

    resources.sessions.cancel_all = lambda: (_ for _ in ()).throw(RuntimeError("cancel failed"))
    resources.tracker.stop = lambda: (_ for _ in ()).throw(RuntimeError("tracker failed"))

    with pytest.raises(LifecycleError, match="cancel failed"):
        controller.pause()

    assert resources.camera.is_open is False


def test_shutdown_is_idempotent() -> None:
    resources = Resources()
    controller = resources.controller()
    controller.start_modeling()

    controller.shutdown()
    close_count = resources.camera.close_count
    controller.shutdown()

    assert controller.state is AppState.SHUTDOWN
    assert resources.camera.close_count == close_count
