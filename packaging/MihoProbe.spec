# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


spec_path = Path(SPECPATH).resolve()
project_root = spec_path.parent if spec_path.name == 'packaging' else spec_path.parent.parent

probe_hiddenimports = [
    'build_agent_value_cards',
    'extract_zzz_box_roster',
    'prepare_zzz_meta_snapshot',
    'run_zzz_box_value_pipeline',
]

a = Analysis(
    [str(project_root / 'tools' / 'probes' / 'miho_probe_cli.py')],
    pathex=[str(project_root), str(project_root / 'tools' / 'probes')],
    binaries=[],
    datas=[],
    hiddenimports=probe_hiddenimports + [
        'PIL',
        'PIL.Image',
    ],
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
    name='MihoProbe',
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
