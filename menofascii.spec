# MenOfAscii.spec
# Build with: py -m PyInstaller --noconfirm --clean MenOfAscii.spec

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path

project_dir = Path(__file__).resolve().parent

datas = [
    (str(project_dir / "assets"), "assets"),
]

hiddenimports = []
hiddenimports += collect_submodules("tcod")

a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MenOfAscii",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # set True if you want a console window
    disable_windowed_traceback=False,
)