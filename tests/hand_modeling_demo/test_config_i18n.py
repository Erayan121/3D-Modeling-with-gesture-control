from pathlib import Path

import pytest

from hand_modeling_demo.config import ConfigStore, Settings
from hand_modeling_demo.i18n import COPY, tr


def test_defaults_are_safe_and_match_the_spec() -> None:
    cfg = Settings()

    assert cfg.language == "zh-CN"
    assert cfg.camera_index == 0
    assert cfg.swap_handedness is True
    assert cfg.pinch_enter_ratio == 0.35
    assert cfg.pinch_release_ratio == 0.48
    assert cfg.pinch_release_grace_ms == 120
    assert cfg.create_min_pull == 0.035
    assert cfg.union_confirm_inward == 0.03
    assert cfg.tracking_loss_ms == 250


def test_unsafe_threshold_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="pinch"):
        Settings(pinch_enter_ratio=0.45, pinch_release_ratio=0.30)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("language", "fr-FR"),
        ("camera_index", 17),
        ("pointer_smoothing", 1.1),
        ("stable_ms", 49),
        ("tracking_loss_ms", 1001),
        ("circle_max_ms", 499),
        ("pan_gain", 0.0),
    ],
)
def test_settings_reject_values_outside_safe_ranges(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        Settings(**{field: value})


def test_config_round_trip_and_corrupt_fallback(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = ConfigStore(path)
    store.save(Settings(language="en-US", swap_handedness=True))

    assert store.load().swap_handedness is True
    path.write_text("{broken", encoding="utf-8")

    assert store.load() == Settings()
    assert path.with_suffix(".json.invalid").exists()


def test_old_union_threshold_is_migrated_to_lenient_default(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = ConfigStore(path)
    store.save(Settings(union_confirm_inward=0.15))

    assert store.load().union_confirm_inward == 0.03


def test_unknown_config_keys_fall_back_and_preserve_bad_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"language": "zh-CN", "invented": true}', encoding="utf-8")

    assert ConfigStore(path).load() == Settings()
    assert path.with_suffix(".json.invalid").exists()


def test_every_copy_key_exists_in_both_languages() -> None:
    assert set(COPY["zh-CN"]) == set(COPY["en-US"])
    assert tr("start", "zh-CN") == "开始"
    assert tr("continue", "en-US") == "Continue"


def test_unknown_translation_key_is_rejected() -> None:
    with pytest.raises(KeyError, match="missing"):
        tr("missing", "zh-CN")
