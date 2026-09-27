from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    language: str = "zh-CN"
    camera_index: int = 0
    # CameraSource mirrors the selfie image before MediaPipe sees it. On the
    # target Windows camera this keeps physical left/right roles intuitive.
    swap_handedness: bool = True
    control_region_fraction: float = 0.80
    pointer_smoothing: float = 0.60
    pointer_deadzone: float = 0.004
    pinch_enter_ratio: float = 0.35
    pinch_release_ratio: float = 0.48
    pinch_release_grace_ms: int = 120
    stable_ms: int = 120
    tracking_loss_ms: int = 250
    pan_gain: float = 4.0
    orbit_gain: float = 140.0
    zoom_gain: float = 5.0
    model_move_gain: float = 1.0
    model_scale_gain: float = 1.0
    model_rotate_gain: float = 1.0
    create_scale_gain: float = 4.0
    create_min_pull: float = 0.035
    union_confirm_inward: float = 0.03
    circle_min_radius: float = 0.045
    circle_close_ratio: float = 0.45
    circle_max_ms: int = 2500

    def __post_init__(self) -> None:
        self._member("language", self.language, {"zh-CN", "en-US"})
        self._range("camera_index", self.camera_index, 0, 16)
        for name in (
            "control_region_fraction", "pointer_smoothing", "pointer_deadzone",
            "pinch_enter_ratio", "pinch_release_ratio", "circle_min_radius",
            "circle_close_ratio", "create_min_pull", "union_confirm_inward",
        ):
            self._range(name, getattr(self, name), 0.0, 1.0)
        if self.pinch_enter_ratio >= self.pinch_release_ratio:
            raise ValueError("pinch_enter_ratio must be below pinch_release_ratio")
        self._range("pinch_release_grace_ms", self.pinch_release_grace_ms, 0, 500)
        self._range("stable_ms", self.stable_ms, 50, 500)
        self._range("tracking_loss_ms", self.tracking_loss_ms, 100, 1000)
        self._range("circle_max_ms", self.circle_max_ms, 500, 5000)
        for name in (
            "pan_gain", "orbit_gain", "zoom_gain", "model_move_gain",
            "model_scale_gain", "model_rotate_gain", "create_scale_gain",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    @staticmethod
    def _range(name: str, value: float, minimum: float, maximum: float) -> None:
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")

    @staticmethod
    def _member(name: str, value: str, allowed: set[str]) -> None:
        if value not in allowed:
            raise ValueError(f"{name} must be one of {sorted(allowed)}")


class ConfigStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else self.default_path()

    @staticmethod
    def default_path() -> Path:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "HandModelingDemo" / "settings.json"

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings root must be an object")
            if raw.get("union_confirm_inward") == 0.15:
                raw["union_confirm_inward"] = 0.03
            known = {item.name for item in fields(Settings)}
            if set(raw) - known:
                raise ValueError("settings contain unknown keys")
            return Settings(**raw)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            invalid = self.path.with_suffix(self.path.suffix + ".invalid")
            try:
                self.path.replace(invalid)
            except OSError:
                pass
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
