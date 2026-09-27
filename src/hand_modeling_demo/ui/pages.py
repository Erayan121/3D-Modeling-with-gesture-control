from __future__ import annotations

from dataclasses import fields

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from hand_modeling_demo.config import Settings
from hand_modeling_demo.i18n import tr


class StartPage(QWidget):
    start_requested = Signal()
    tutorial_requested = Signal()
    language_requested = Signal()
    settings_requested = Signal()
    exit_requested = Signal()

    def __init__(self, language: str, parent=None) -> None:
        super().__init__(parent)
        self.title = QLabel()
        self.title.setAlignment(Qt.AlignCenter)
        self.start_button = QPushButton()
        self.tutorial_button = QPushButton()
        self.language_button = QPushButton()
        self.settings_button = QPushButton()
        self.exit_button = QPushButton()
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.title)
        for button in self._buttons():
            layout.addWidget(button)
        layout.addStretch()
        self.start_button.clicked.connect(self.start_requested)
        self.tutorial_button.clicked.connect(self.tutorial_requested)
        self.language_button.clicked.connect(self.language_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        self.exit_button.clicked.connect(self.exit_requested)
        self.retranslate(language)

    def _buttons(self):
        return (
            self.start_button,
            self.tutorial_button,
            self.language_button,
            self.settings_button,
            self.exit_button,
        )

    @staticmethod
    def visible_actions() -> tuple[str, ...]:
        return "start", "tutorial", "language", "settings", "exit"

    def retranslate(self, language: str) -> None:
        self.title.setText(tr("app_title", language))
        for key, button in zip(self.visible_actions(), self._buttons()):
            button.setText(tr(key, language))


class TutorialPage(QWidget):
    back_requested = Signal()
    KEYS = (
        "tutorial_pointer",
        "tutorial_camera",
        "tutorial_transform",
        "tutorial_create",
        "tutorial_union",
        "tutorial_history",
        "tutorial_pause",
    )

    def __init__(self, language: str, parent=None) -> None:
        super().__init__(parent)
        self.pages = QStackedWidget()
        self.labels: list[QLabel] = []
        for _ in self.KEYS:
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            self.labels.append(label)
            self.pages.addWidget(label)
        self.previous_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.back_button = QPushButton()
        nav = QHBoxLayout()
        nav.addWidget(self.previous_button)
        nav.addWidget(self.next_button)
        nav.addWidget(self.back_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.pages)
        layout.addLayout(nav)
        self.previous_button.clicked.connect(self._previous)
        self.next_button.clicked.connect(self._next)
        self.back_button.clicked.connect(self.back_requested)
        self.retranslate(language)

    @property
    def page_count(self) -> int:
        return self.pages.count()

    def _previous(self) -> None:
        self.pages.setCurrentIndex((self.pages.currentIndex() - 1) % self.page_count)

    def _next(self) -> None:
        self.pages.setCurrentIndex((self.pages.currentIndex() + 1) % self.page_count)

    def retranslate(self, language: str) -> None:
        for key, label in zip(self.KEYS, self.labels):
            label.setText(tr(key, language))
        self.back_button.setText(tr("back", language))


class SettingsPage(QWidget):
    save_requested = Signal(object)
    back_requested = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._widgets: dict[str, object] = {}
        self.form = QFormLayout()
        for descriptor in fields(Settings):
            widget = self._make_widget(descriptor.name, getattr(settings, descriptor.name))
            self._widgets[descriptor.name] = widget
            self.form.addRow(descriptor.name.replace("_", " "), widget)
            setattr(self, descriptor.name, widget)
        self.reset_button = QPushButton()
        self.save_button = QPushButton("OK")
        self.back_button = QPushButton()
        buttons = QHBoxLayout()
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.back_button)
        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addLayout(buttons)
        self.reset_button.clicked.connect(lambda: self.load(Settings()))
        self.save_button.clicked.connect(lambda: self.save_requested.emit(self.to_settings()))
        self.back_button.clicked.connect(self.back_requested)
        self.retranslate(settings.language)

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(self._widgets)

    def _make_widget(self, name: str, value):
        if name == "language":
            widget = QComboBox()
            widget.addItems(("zh-CN", "en-US"))
            widget.setCurrentText(value)
            return widget
        if isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
            return widget
        if isinstance(value, int):
            widget = QSpinBox()
            ranges = {
                "camera_index": (0, 16), "stable_ms": (50, 500),
                "pinch_release_grace_ms": (0, 500),
                "tracking_loss_ms": (100, 1000), "circle_max_ms": (500, 5000),
            }
            widget.setRange(*ranges.get(name, (0, 10000)))
            widget.setValue(value)
            return widget
        widget = QDoubleSpinBox()
        widget.setDecimals(4)
        widget.setSingleStep(0.01)
        widget.setRange(0.0, 1000.0)
        widget.setValue(value)
        return widget

    def load(self, settings: Settings) -> None:
        for name, widget in self._widgets.items():
            value = getattr(settings, name)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            else:
                widget.setValue(value)

    def to_settings(self) -> Settings:
        values = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, QComboBox):
                values[name] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            else:
                values[name] = widget.value()
        return Settings(**values)

    def retranslate(self, language: str) -> None:
        self.reset_button.setText(tr("reset_defaults", language))
        self.back_button.setText(tr("back", language))


class PauseDialog(QDialog):
    continue_requested = Signal()
    exit_requested = Signal()

    def __init__(self, language: str, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.continue_button = QPushButton()
        self.exit_button = QPushButton()
        layout = QVBoxLayout(self)
        layout.addWidget(self.continue_button)
        layout.addWidget(self.exit_button)
        self.continue_button.clicked.connect(self.continue_requested)
        self.exit_button.clicked.connect(self.exit_requested)
        self.retranslate(language)

    @staticmethod
    def visible_actions() -> tuple[str, str]:
        return "continue", "exit"

    def retranslate(self, language: str) -> None:
        self.continue_button.setText(tr("continue", language))
        self.exit_button.setText(tr("exit", language))


class ErrorDialog(QDialog):
    def __init__(self, language: str, parent=None) -> None:
        super().__init__(parent)
        self.message = QLabel()
        self.ok_button = QPushButton("OK")
        layout = QVBoxLayout(self)
        layout.addWidget(self.message)
        layout.addWidget(self.ok_button)
        self.ok_button.clicked.connect(self.accept)
        self.language = language

    def show_error(self, text: str) -> None:
        self.message.setText(text)
        self.show()
