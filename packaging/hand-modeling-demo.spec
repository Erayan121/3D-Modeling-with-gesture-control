import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules


root = Path(SPECPATH).parent
onefile = os.environ.get("HAND_MODELING_ONEFILE") == "1"
# Keep unrelated developer tools (for example Poppler's incompatible ICU)
# out of native dependency resolution. Qt uses the Windows system ICU API.
os.environ["PATH"] = os.pathsep.join([
    str(Path(sys.executable).parent),
    str(Path(os.environ["SystemRoot"]) / "System32"),
    os.environ["SystemRoot"],
])
datas = [
    (str(root / "src" / "gesture_control" / "resources" / "hand_landmarker.task"),
     "gesture_control/resources"),
]
binaries = []
hiddenimports = collect_submodules("panda3d") + ["manifold3d"]
for package in ("mediapipe", "trimesh"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
binaries += collect_dynamic_libs("panda3d")
binaries += collect_dynamic_libs("PySide6")

analysis = Analysis(
    [str(root / "src" / "hand_modeling_demo" / "main.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    excludes=["modeling_prototype", "face_recognition", "tkinter", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries if onefile else [],
    analysis.datas if onefile else [],
    [],
    name="HandModelingDemo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    exclude_binaries=not onefile,
)
if not onefile:
    collect = COLLECT(
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name="HandModelingDemo",
    )
