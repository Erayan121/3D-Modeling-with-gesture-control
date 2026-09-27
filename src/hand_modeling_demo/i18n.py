from __future__ import annotations

from typing import Final


COPY: Final[dict[str, dict[str, str]]] = {
    "zh-CN": {
        "app_title": "手势三维建模 Demo",
        "start": "开始",
        "tutorial": "教学",
        "language": "语言",
        "settings": "设置",
        "exit": "退出",
        "continue": "继续",
        "back": "返回",
        "reset_defaults": "恢复默认设置",
        "camera_error": "无法打开摄像头 {index}，请检查设备是否被占用。",
        "tracking_error": "手部识别已停止，请返回后重试。",
        "tutorial_pointer": "控制点、悬停与捏合",
        "tutorial_camera": "摄像机平移、缩放与旋转",
        "tutorial_transform": "单手移动与双手组合变换",
        "tutorial_create": "数字键与拉伸创建几何体",
        "tutorial_union": "布尔并集",
        "tutorial_history": "画圈撤销与重做",
        "tutorial_pause": "空格暂停、继续与退出",
        "union_failed": "模型必须是已经相交的封闭实体。",
    },
    "en-US": {
        "app_title": "Gesture 3D Modeling Demo",
        "start": "Start",
        "tutorial": "Tutorial",
        "language": "Language",
        "settings": "Settings",
        "exit": "Exit",
        "continue": "Continue",
        "back": "Back",
        "reset_defaults": "Reset Defaults",
        "camera_error": "Camera {index} could not be opened. Check whether it is in use.",
        "tracking_error": "Hand tracking stopped. Return and try again.",
        "tutorial_pointer": "Pointers, hover, and pinch",
        "tutorial_camera": "Camera pan, zoom, and orbit",
        "tutorial_transform": "One-hand move and two-hand transform",
        "tutorial_create": "Number keys and pull-apart creation",
        "tutorial_union": "Boolean union",
        "tutorial_history": "Circle undo and redo",
        "tutorial_pause": "Space to pause, resume, and exit",
        "union_failed": "Models must be closed solids that already intersect.",
    },
}


def tr(key: str, language: str, **values: object) -> str:
    text = COPY[language][key]
    return text.format(**values) if values else text
