from dataclasses import asdict, dataclass, fields
import json
from math import isfinite
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    control_region_fraction: float = 0.70
    long_press_ms: int = 350
    pause_hold_ms: int = 1500
    delete_hold_ms: int = 2000
    tracking_loss_release_ms: int = 250
    start_countdown_seconds: int = 3
    max_hands: int = 2
    min_hand_confidence: float = 0.70
    pose_stable_ms: int = 120
    pointer_smoothing: float = 0.55
    pointer_dead_zone: float = 0.0025
    pinch_close_ratio: float = 0.32
    pinch_open_ratio: float = 0.42
    scroll_dead_zone: float = 0.008
    scroll_gain: float = 1.0
    max_scroll_delta: int = 720
    camera_index: int = 0
    # Some Windows camera drivers already mirror frames before OpenCV sees
    # them. Swap MediaPipe's labels at the adapter boundary when that makes
    # the displayed left/right roles disagree with the user's physical hands.
    swap_handedness: bool = True

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.type is bool:
                valid = type(value) is bool
            elif field.type is int:
                valid = type(value) is int
            else:
                valid = type(value) is int or (type(value) is float and isfinite(value))
            if not valid:
                raise ValueError(field.name)
        checks = {
            "control_region_fraction": 0.50 <= self.control_region_fraction <= 0.90,
            "long_press_ms": 200 <= self.long_press_ms <= 800,
            "pause_hold_ms": 800 <= self.pause_hold_ms <= 3000,
            "delete_hold_ms": 1000 <= self.delete_hold_ms <= 5000,
            "tracking_loss_release_ms": 100 <= self.tracking_loss_release_ms <= 500,
            "start_countdown_seconds": 1 <= self.start_countdown_seconds <= 10,
            "max_hands": 1 <= self.max_hands <= 2,
            "min_hand_confidence": 0.50 <= self.min_hand_confidence <= 0.95,
            "pose_stable_ms": 1 <= self.pose_stable_ms <= 2000,
            "pointer_smoothing": 0.0 <= self.pointer_smoothing <= 1.0,
            "pointer_dead_zone": 0.0 <= self.pointer_dead_zone <= 0.25,
            "pinch_close_ratio": 0.15 <= self.pinch_close_ratio <= 0.40,
            "pinch_open_ratio": self.pinch_close_ratio < self.pinch_open_ratio <= 0.60,
            "scroll_dead_zone": 0.0 <= self.scroll_dead_zone <= 0.25,
            "scroll_gain": 0.01 <= self.scroll_gain <= 10.0,
            "max_scroll_delta": 1 <= self.max_scroll_delta <= 10000,
            "camera_index": self.camera_index >= 0,
        }
        failed = next((name for name, valid in checks.items() if not valid), None)
        if failed:
            raise ValueError(failed)


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(values, dict):
                raise ValueError("configuration root must be an object")
            # Versions before the left-fist hold interaction exposed right-fist
            # swipe tuning. Ignore those retired keys without discarding the
            # user's remaining settings.
            for name in ("swipe_min_dx", "swipe_max_ms", "swipe_vertical_ratio"):
                values.pop(name, None)
            return AppConfig(**values)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            invalid = self.path.with_suffix(self.path.suffix + ".invalid")
            self.path.replace(invalid)
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
        temporary.replace(self.path)
