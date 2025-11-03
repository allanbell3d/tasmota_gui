# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\Development\\Coding\\Tasmota_GUI\\tasmota_gui_kivy_buildozer\\tasmota_gui_test-main_in_progress\\apps\\desktop.py'],
    pathex=['E:\\Development\\Coding\\Tasmota_GUI\\tasmota_gui_kivy_buildozer\\tasmota_gui_test-main_in_progress\\src'],
    binaries=[],
    datas=[('E:\\Development\\Coding\\Tasmota_GUI\\tasmota_gui_kivy_buildozer\\tasmota_gui_test-main_in_progress\\assets\\commands\\tasmota_commands.json', 'assets/commands')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TasmotaBulkGUI_v0.1.7',
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
