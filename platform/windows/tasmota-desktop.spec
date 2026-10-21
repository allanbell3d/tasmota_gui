# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the desktop (PySide6) app.

Build from any directory, e.g. from the repository root:

    pyinstaller --clean platform/windows/tasmota-desktop.spec

PyInstaller resolves relative paths in a spec against the spec's own folder,
so every path below is anchored to the repository root explicitly.

If ``.private/tasmota_settings.json`` exists at build time it is bundled as
the first-run seed, so a fresh copy of the .exe starts with your IP ranges
and commands. Changes made in the app are saved to ``.private/`` next to the
.exe (or to %APPDATA%/TasmotaBulkTool if that folder is not writable).
The bundled seed is personal data: do not share an .exe built with it.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = [
    (os.path.join(ROOT, "assets", "commands", "tasmota_commands.json"), os.path.join("assets", "commands")),
    (os.path.join(ROOT, "assets", "images", "logo.jpg"), os.path.join("assets", "images")),
]
_seed = os.path.join(ROOT, ".private", "tasmota_settings.json")
if os.path.isfile(_seed):
    datas.append((_seed, ".private"))

a = Analysis(
    [os.path.join(ROOT, "apps", "desktop.py")],
    pathex=[os.path.join(ROOT, "src"), ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["kivy"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='TasmotaBulkGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
