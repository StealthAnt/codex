# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.building.datastruct import Tree

KODEX_DIR = Path(SPECPATH).parent.resolve()
REA_NODE_MODULES = KODEX_DIR / 'rea' / 'node_modules'
if not (REA_NODE_MODULES / 'rea-agents' / 'scripts' / 'rea.mjs').is_file():
    raise SystemExit('REA is not downloaded. Run npm ci --prefix kodex/rea before building KoDex.')

a = Analysis(
    [str(KODEX_DIR / 'desktop_app.py')],
    pathex=[str(KODEX_DIR)],
    binaries=[],
    datas=[
        (str(KODEX_DIR / 'app_icon.png'), '.'),
        (str(KODEX_DIR / 'KoDexVoiceInput.ps1'), '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += Tree(str(REA_NODE_MODULES), prefix='rea/node_modules')
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KoDex',
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
    icon=[str(KODEX_DIR / 'app_icon.ico')],
)
