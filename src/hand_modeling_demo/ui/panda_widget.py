from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QResizeEvent
from PySide6.QtWidgets import QWidget
from panda3d.core import KeyboardButton, WindowProperties


class PandaViewport(QWidget):
    render_size_changed = Signal(int, int)
    orbit_requested = Signal(float, float)
    pan_requested = Signal(float, float)
    zoom_requested = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("black"))
        self.setPalette(palette)
        self._base = None
        self._camera_input_enabled = False
        self._right_dragging = False
        self._drag_mode: str | None = None
        self._last_mouse: tuple[float, float] | None = None

    def attach_base(self, base) -> None:
        self._base = base
        props = WindowProperties()
        props.setParentWindow(int(self.winId()))
        props.setOrigin(0, 0)
        props.setSize(*self.render_size())
        base.openDefaultWindow(props=props)
        self.bind_camera_controls(base)

    def bind_camera_controls(self, base) -> None:
        """Bind to Panda's native child window, which owns real mouse input."""
        self._base = base
        base.disableMouse()
        base.accept("mouse3", self._right_button_down)
        base.accept("mouse3-up", self._right_button_up)
        base.accept("wheel_up", lambda: self._wheel(1.0))
        base.accept("wheel_down", lambda: self._wheel(-1.0))

    def set_camera_input_enabled(self, enabled: bool) -> None:
        self._camera_input_enabled = enabled
        if not enabled:
            self._right_button_up()

    def poll_mouse_camera(self) -> None:
        base = self._base
        if (
            not self._camera_input_enabled
            or not self._right_dragging
            or base is None
            or not base.mouseWatcherNode.hasMouse()
        ):
            return
        point = base.mouseWatcherNode.getMouse()
        current = (float(point.x), float(point.y))
        shift = base.mouseWatcherNode.isButtonDown(KeyboardButton.shift())
        mode = "pan" if shift else "orbit"
        if self._last_mouse is None or mode != self._drag_mode:
            self._last_mouse = current
            self._drag_mode = mode
            return
        delta_x = (current[0] - self._last_mouse[0]) / 2.0
        delta_y = (current[1] - self._last_mouse[1]) / 2.0
        self._last_mouse = current
        if delta_x == 0.0 and delta_y == 0.0:
            return
        if mode == "pan":
            self.pan_requested.emit(delta_x, delta_y)
        else:
            self.orbit_requested.emit(delta_x, delta_y)

    def _right_button_down(self) -> None:
        if not self._camera_input_enabled:
            return
        self._right_dragging = True
        self._drag_mode = None
        self._last_mouse = None

    def _right_button_up(self) -> None:
        self._right_dragging = False
        self._drag_mode = None
        self._last_mouse = None

    def _wheel(self, direction: float) -> None:
        if self._camera_input_enabled:
            self.zoom_requested.emit(direction * 0.1)

    def render_size(self) -> tuple[int, int]:
        scale = self.devicePixelRatioF()
        return (
            max(1, round(self.width() * scale)),
            max(1, round(self.height() * scale)),
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_render_size()

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        dpi_change = getattr(QEvent.Type, "DevicePixelRatioChange", None)
        screen_change = getattr(QEvent.Type, "ScreenChangeInternal", None)
        if event.type() in {kind for kind in (dpi_change, screen_change) if kind is not None}:
            self._sync_render_size()
        return handled

    def _sync_render_size(self) -> None:
        width, height = self.render_size()
        base = getattr(self, "_base", None)
        if base is not None and base.win is not None:
            props = WindowProperties()
            props.setOrigin(0, 0)
            props.setSize(width, height)
            base.win.requestProperties(props)
        self.render_size_changed.emit(width, height)
