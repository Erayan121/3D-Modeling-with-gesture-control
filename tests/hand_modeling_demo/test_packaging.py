from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_spec_collects_panda3d_display_libraries() -> None:
    spec = (ROOT / "packaging" / "hand-modeling-demo.spec").read_text(encoding="utf-8")

    assert 'collect_dynamic_libs("panda3d")' in spec


def test_runtime_configures_display_pipe_fallbacks() -> None:
    main = (ROOT / "src" / "hand_modeling_demo" / "main.py").read_text(encoding="utf-8")

    assert "load-display pandagl" in main
    assert "aux-display pandadx9" in main
    assert "aux-display p3tinydisplay" in main


def test_packaged_smoke_opens_a_real_graphics_pipe() -> None:
    verifier = (ROOT / "packaging" / "verify-hand-modeling.ps1").read_text(encoding="utf-8")
    main = (ROOT / "src" / "hand_modeling_demo" / "main.py").read_text(encoding="utf-8")

    assert "--graphics-smoke-report" in verifier
    assert "--graphics-smoke-report" in main
    assert "graphics_pipe" in verifier
