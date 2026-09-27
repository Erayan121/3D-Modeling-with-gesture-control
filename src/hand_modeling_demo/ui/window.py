from __future__ import annotations

from dataclasses import replace
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from hand_modeling_demo.config import ConfigStore, Settings
from hand_modeling_demo.domain import AppState
from hand_modeling_demo.ui.pages import ErrorDialog, PauseDialog, SettingsPage, StartPage, TutorialPage
from hand_modeling_demo.ui.panda_widget import PandaViewport


class MainWindow(QMainWindow):
    start_requested = Signal()
    return_to_start_requested = Signal()
    primitive_key = Signal(int)
    space_pressed = Signal()
    exit_requested = Signal()
    settings_changed = Signal(object)

    def __init__(self, settings: Settings, config_store: ConfigStore, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.config_store = config_store
        self.state = AppState.START
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.start_page = StartPage(settings.language)
        self.tutorial_page = TutorialPage(settings.language)
        self.settings_page = SettingsPage(settings)
        self.viewport = PandaViewport()
        for page in (self.start_page, self.tutorial_page, self.settings_page, self.viewport):
            self.stack.addWidget(page)
        self.pause_dialog = PauseDialog(settings.language, self)
        self.error_dialog = ErrorDialog(settings.language, self)
        self._connect_actions()
        self.show_start()

    def _connect_actions(self) -> None:
        self.start_page.start_requested.connect(self.start_requested)
        self.start_page.tutorial_requested.connect(self.show_tutorial)
        self.start_page.language_requested.connect(self.toggle_language)
        self.start_page.settings_requested.connect(self.show_settings)
        self.start_page.exit_requested.connect(self.close)
        self.tutorial_page.back_requested.connect(self.show_start)
        self.settings_page.back_requested.connect(self.show_start)
        self.settings_page.save_requested.connect(self.apply_settings)
        self.pause_dialog.continue_requested.connect(self._continue_from_dialog)
        self.pause_dialog.exit_requested.connect(self._exit_pause_to_start)

    def visible_actions(self) -> tuple[str, ...]:
        return self.start_page.visible_actions()

    def show_start(self) -> None:
        self.pause_dialog.hide()
        self.viewport.set_camera_input_enabled(False)
        self.state = AppState.START
        self.stack.setCurrentWidget(self.start_page)
        if self.isFullScreen():
            self.showNormal()

    def show_tutorial(self) -> None:
        self.viewport.set_camera_input_enabled(False)
        self.state = AppState.TUTORIAL
        self.stack.setCurrentWidget(self.tutorial_page)

    def show_settings(self) -> None:
        self.viewport.set_camera_input_enabled(False)
        self.state = AppState.SETTINGS
        self.settings_page.load(self.settings)
        self.stack.setCurrentWidget(self.settings_page)

    def show_modeling(self, *, fullscreen: bool = True) -> None:
        self.state = AppState.MODELING_ACTIVE
        self.stack.setCurrentWidget(self.viewport)
        self.viewport.setFocus()
        self.viewport.set_camera_input_enabled(True)
        if fullscreen and os.environ.get("HAND_MODELING_HEADLESS") != "1":
            self.showFullScreen()

    def show_paused(self) -> None:
        self.state = AppState.MODELING_PAUSED
        self.viewport.set_camera_input_enabled(False)
        self.pause_dialog.show()

    def show_error(self, text: str) -> None:
        self.state = AppState.ERROR
        self.viewport.set_camera_input_enabled(False)
        self.error_dialog.show_error(text)

    def toggle_language(self) -> None:
        self.set_language("en-US" if self.settings.language == "zh-CN" else "zh-CN")

    def set_language(self, language: str) -> None:
        self.settings = replace(self.settings, language=language)
        self.config_store.save(self.settings)
        self.start_page.retranslate(language)
        self.tutorial_page.retranslate(language)
        self.settings_page.retranslate(language)
        self.pause_dialog.retranslate(language)

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.config_store.save(settings)
        self.set_language(settings.language)
        self.settings_changed.emit(settings)
        self.show_start()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Space:
            previous_state = self.state
            self.space_pressed.emit()
            if previous_state is AppState.MODELING_ACTIVE and self.state is AppState.MODELING_ACTIVE:
                self.show_paused()
            return
        if self.state is AppState.MODELING_ACTIVE and Qt.Key_1 <= event.key() <= Qt.Key_5:
            self.primitive_key.emit(event.key() - Qt.Key_0)
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.exit_requested.emit()
        event.accept()

    def _continue_from_dialog(self) -> None:
        self.space_pressed.emit()

    def _exit_pause_to_start(self) -> None:
        self.pause_dialog.hide()
        self.return_to_start_requested.emit()
