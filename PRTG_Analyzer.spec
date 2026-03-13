# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PyPRTG_CLA one-file EXE."""
from pathlib import Path

REPO_ROOT = Path(SPECPATH)
SOURCE = REPO_ROOT / "source"

# Version for exe name (build script renames to PyPRTG_CLA_v{version}.exe)
_version = "1.5.8"
_exec_name = f"PyPRTG_CLA_v{_version}"

a = Analysis(
    [str(SOURCE / "run_analyzer.py")],
    pathex=[str(SOURCE)],
    binaries=[],
    datas=[
        (str(SOURCE / "frontend"), "frontend"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=_exec_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
