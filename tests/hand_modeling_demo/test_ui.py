from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QDockWidget, QMenuBar, QToolBar

from hand_modeling_demo.config import ConfigStore, Settings
from hand_modeling_demo.domain import AppState
from hand_modeling_demo.ui.panda_widget import PandaViewport
from hand_modeling_demo.ui.window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path: Path) -> MainWindow:
    item = MainWindow(Settings(), ConfigStore(tmp_path / "settings.json"))
    qtbot.addWidget(item)
    item.show()
    return item


def test_start_page_has_exact_five_actions(window: MainWindow) -> None:
    assert window.visible_actions() == (
        "start",
        "tutorial",
        "language",
        "settings",
        "exit",
    )


def test_start_page_exit_closes_window_and_emits_shutdown(qtbot, window: MainWindow) -> None:
    exited: list[bool] = []
    window.exit_requested.connect(lambda: exited.append(True))

    qtbot.mouseClick(window.start_page.exit_button, Qt.LeftButton)

    assert exited == [True]
    assert window.isVisible() is False


def test_pause_dialog_has_continue_and_exit_only(qtbot, window: MainWindow) -> None:
    window.show_modeling(fullscreen=False)

    qtbot.keyPress(window, Qt.Key_Space)

    assert window.state is AppState.MODELING_PAUSED
    assert window.pause_dialog.visible_actions() == ("continue", "exit")


def test_language_switch_updates_existing_pages_and_persists(window: MainWindow) -> None:
    window.set_language("en-US")

    assert window.start_page.start_button.text() == "Start"
    assert window.pause_dialog.continue_button.text() == "Continue"
    assert window.config_store.load().language == "en-US"


def test_tutorial_contains_seven_approved_task_pages(window: MainWindow) -> None:
    assert window.tutorial_page.page_count == 7


def test_settings_page_round_trips_approved_values(window: MainWindow) -> None:
    window.settings_page.camera_index.setValue(4)
    window.settings_page.swap_handedness.setChecked(True)

    updated = window.settings_page.to_settings()

    assert updated.camera_index == 4
    assert updated.swap_handedness is True
    assert set(window.settings_page.field_names) == set(Settings.__dataclass_fields__)


def test_modeling_viewport_is_black_and_contains_no_chrome(window: MainWindow) -> None:
    window.show_modeling(fullscreen=False)

    assert window.viewport.palette().color(QPalette.Window) == QColor("black")
    assert window.findChildren(QToolBar) == []
    assert window.findChildren(QMenuBar) == []
    assert window.findChildren(QDockWidget) == []


def test_panda_viewport_converts_qt_size_to_physical_pixels(qtbot, monkeypatch) -> None:
    viewport = PandaViewport()
    qtbot.addWidget(viewport)
    monkeypatch.setattr(PandaViewport, "devicePixelRatioF", lambda self: 1.5)
    viewport.resize(800, 600)

    assert viewport.render_size() == (1200, 900)


def test_panda_native_mouse_events_match_rhino_camera_controls(qtbot) -> None:
    class Point:
        def __init__(self, x: float, y: float):
            self.x = x
            self.y = y

    class Watcher:
        def __init__(self):
            self.point = Point(0.0, 0.0)
            self.shift = False

        def hasMouse(self):
            return True

        def getMouse(self):
            return self.point

        def isButtonDown(self, button):
            return self.shift

    class Base:
        def __init__(self):
            self.mouseWatcherNode = Watcher()
            self.events = {}
            self.disabled = False

        def disableMouse(self):
            self.disabled = True

        def accept(self, name, callback):
            self.events[name] = callback

    viewport = PandaViewport()
    qtbot.addWidget(viewport)
    base = Base()
    orbit = []
    pan = []
    zoom = []
    viewport.orbit_requested.connect(lambda x, y: orbit.append((x, y)))
    viewport.pan_requested.connect(lambda x, y: pan.append((x, y)))
    viewport.zoom_requested.connect(zoom.append)
    viewport.bind_camera_controls(base)
    viewport.set_camera_input_enabled(True)

    base.events["mouse3"]()
    viewport.poll_mouse_camera()
    base.mouseWatcherNode.point = Point(0.4, 0.2)
    viewport.poll_mouse_camera()
    base.mouseWatcherNode.shift = True
    viewport.poll_mouse_camera()  # Modifier change rebases without jumping.
    base.mouseWatcherNode.point = Point(0.6, 0.4)
    viewport.poll_mouse_camera()
    base.events["wheel_up"]()
    base.events["wheel_down"]()
    base.events["mouse3-up"]()

    assert base.disabled is True
    assert orbit == [(0.2, 0.1)]
    assert pan == [(pytest.approx(0.1), pytest.approx(0.1))]
    assert zoom == [0.1, -0.1]
    assert viewport._right_dragging is False


def test_mouse_camera_input_is_disabled_outside_modeling(qtbot, window: MainWindow) -> None:
    window.viewport._right_button_down()
    assert window.viewport._right_dragging is False

    window.show_modeling(fullscreen=False)
    window.viewport._right_button_down()
    assert window.viewport._right_dragging is True

    window.show_paused()
    assert window.viewport._right_dragging is False


def test_number_keys_emit_only_during_active_modeling(qtbot, window: MainWindow) -> None:
    received: list[int] = []
    window.primitive_key.connect(received.append)
    qtbot.keyPress(window, Qt.Key_3)
    window.show_modeling(fullscreen=False)
    qtbot.keyPress(window, Qt.Key_3)

    assert received == [3]


def test_pause_exit_signal_means_return_to_start_not_process_exit(qtbot, window: MainWindow) -> None:
    returned: list[bool] = []
    exited: list[bool] = []
    window.return_to_start_requested.connect(lambda: returned.append(True))
    window.exit_requested.connect(lambda: exited.append(True))
    window.show_modeling(fullscreen=False)
    window.show_paused()

    qtbot.mouseClick(window.pause_dialog.exit_button, Qt.LeftButton)

    assert returned == [True]
    assert exited == []


def test_space_emits_once_for_pause_and_once_for_resume(qtbot, window: MainWindow) -> None:
    events: list[bool] = []
    window.space_pressed.connect(lambda: events.append(True))
    window.show_modeling(fullscreen=False)

    qtbot.keyPress(window, Qt.Key_Space)
    qtbot.keyPress(window, Qt.Key_Space)

    assert events == [True, True]


def test_continue_request_stays_paused_until_tracking_controller_confirms(
    qtbot, window: MainWindow
) -> None:
    window.show_modeling(fullscreen=False)
    window.show_paused()

    qtbot.mouseClick(window.pause_dialog.continue_button, Qt.LeftButton)

    assert window.state is AppState.MODELING_PAUSED
    assert window.pause_dialog.isVisible()
