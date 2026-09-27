"""Startup checks that must run in a fresh interpreter process."""

import subprocess
import sys


def test_gui_entry_imports_without_native_crash() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import hand_modeling_demo.main"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
