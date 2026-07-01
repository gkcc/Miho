# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


spec_path = Path(SPECPATH).resolve()
project_root = spec_path.parent if spec_path.name == 'packaging' else spec_path.parent.parent

probe_hiddenimports = [
    'build_action_cards',
    'build_action_checklist',
    'build_agent_value_cards',
    'build_demo_command',
    'build_demo_doctor',
    'build_endgame_plan',
    'build_final_brief',
    'build_gpt_review_prompt',
    'build_refresh_status',
    'build_roster_delta',
    'build_run_manifest',
    'build_team_cards',
    'build_tier_watchlist',
    'build_update_command',
    'diff_normalized_snapshots',
    'evaluate_export_parse',
    'export_image_parse_probe',
    'extract_zzz_box_roster',
    'miyoushe_app_export_calibrator',
    'miyoushe_app_export_runner',
    'miyoushe_export_workflow',
    'normalize_export_parse',
    'plan_training_priorities',
    'prepare_endgame_targets',
    'prepare_zzz_meta_snapshot',
    'preview_review_decisions',
    'render_demo_dashboard',
    'render_export_review',
    'review_export_image',
    'run_demo_pipeline',
    'run_export_replay_batch',
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
        'PIL.ImageDraw',
        'PIL.ImageEnhance',
        'PIL.ImageFilter',
        'PIL.ImageFont',
        'PIL.ImageOps',
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
