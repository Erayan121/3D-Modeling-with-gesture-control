from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from time import monotonic_ns

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from direct.showbase.ShowBase import ShowBase
from panda3d.core import loadPrcFileData


DISPLAY_PRC = """\
load-display pandagl
aux-display pandadx9
aux-display p3tinydisplay
audio-library-name null
"""


def _report_path(flag: str) -> Path | None:
    if flag not in sys.argv:
        return None
    index = sys.argv.index(flag)
    try:
        return Path(sys.argv[index + 1])
    except IndexError:
        return None


def _configure_panda(window_type: str) -> None:
    loadPrcFileData("", DISPLAY_PRC + f"window-type {window_type}\n")


def _graphics_smoke(report_path: Path) -> int:
    _configure_panda("none")
    base = None
    try:
        base = ShowBase(windowType="none")
        base.makeDefaultPipe()
        pipe = base.pipe
        graphics_ready = pipe is not None
        report_path.write_text(
            json.dumps(
                {
                    "state": "graphics-ready" if graphics_ready else "graphics-unavailable",
                    "graphics_pipe": graphics_ready,
                    "pipe_type": pipe.getType().getName() if pipe is not None else "",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0 if graphics_ready else 3
    finally:
        if base is not None:
            base.destroy()


def main() -> int:
    report_path = _report_path("--smoke-report")
    if "--smoke-report" in sys.argv:
        if report_path is None:
            return 2
        report_path.write_text(
            json.dumps(
                {
                    "state": "start",
                    "camera_open": False,
                    "tracking_running": False,
                    "clean_shutdown": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    graphics_report_path = _report_path("--graphics-smoke-report")
    if "--graphics-smoke-report" in sys.argv:
        if graphics_report_path is None:
            return 2
        return _graphics_smoke(graphics_report_path)

    from hand_modeling_demo.app import HandModelingApp
    from hand_modeling_demo.config import ConfigStore
    from hand_modeling_demo.rendering.scene import PandaScene
    from hand_modeling_demo.tracking import TrackingService
    from hand_modeling_demo.ui.window import MainWindow

    qt_app = QApplication.instance() or QApplication(sys.argv)
    store = ConfigStore()
    settings = store.load()
    headless = os.environ.get("HAND_MODELING_HEADLESS") == "1"
    _configure_panda("offscreen" if headless else "none")
    base = ShowBase(windowType="offscreen" if headless else "none")
    window = MainWindow(settings, store)
    window.show()
    if not headless:
        window.viewport.attach_base(base)
    viewport_size = (
        (max(1, window.width()), max(1, window.height()))
        if headless else window.viewport.render_size()
    )
    scene = PandaScene(base, settings, viewport_size)
    if not headless:
        window.viewport.render_size_changed.connect(scene.resize_viewport)
    tracking = TrackingService(settings)
    controller = HandModelingApp(settings, tracking, scene, window)
    window.start_requested.connect(controller.start)
    window.return_to_start_requested.connect(controller.return_to_start)
    window.primitive_key.connect(controller.press_digit)
    window.space_pressed.connect(controller.press_space)
    window.settings_changed.connect(controller.apply_settings)
    window.exit_requested.connect(controller.shutdown)
    window.viewport.orbit_requested.connect(controller.mouse_orbit)
    window.viewport.pan_requested.connect(controller.mouse_pan)
    window.viewport.zoom_requested.connect(controller.mouse_zoom)

    timer = QTimer()
    timer.setInterval(16)
    timer.timeout.connect(base.taskMgr.step)
    timer.timeout.connect(window.viewport.poll_mouse_camera)
    timer.timeout.connect(lambda: controller.tick(monotonic_ns() // 1_000_000))
    timer.start()
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
