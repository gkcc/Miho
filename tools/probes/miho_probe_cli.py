#!/usr/bin/env python
"""Small command shell for local Miho probe workflows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import diff_normalized_snapshots as diff_tool  # noqa: E402
import normalize_export_parse as normalize_tool  # noqa: E402
import plan_training_priorities as planner_tool  # noqa: E402
import prepare_endgame_targets as target_tool  # noqa: E402
import run_demo_pipeline as demo_tool  # noqa: E402


def run_demo(args: argparse.Namespace) -> int:
    summary = demo_tool.run_pipeline(
        images_dir=demo_tool.resolve_path(args.images_dir) if args.images_dir else None,
        parsed_dir=demo_tool.resolve_path(args.parsed_dir) if args.parsed_dir else None,
        manifest=demo_tool.resolve_path(args.manifest) if args.manifest else None,
        output_dir=demo_tool.resolve_path(args.output_dir),
        expected_dir=demo_tool.resolve_path(args.expected_dir),
        engine=args.engine,
        game=args.game,
        layout=args.layout,
        open_dashboard=args.open,
        latest_only=args.latest_only,
        clean_demo=args.clean_demo,
        targets=demo_tool.resolve_path(args.targets) if args.targets else None,
        new_only=args.new_only,
        state_file=demo_tool.resolve_path(args.state_file) if args.state_file else None,
        history_dir=demo_tool.resolve_path(args.history_dir) if args.history_dir else None,
        target_source_manifest=demo_tool.resolve_path(args.target_source_manifest) if args.target_source_manifest else None,
        character_catalog=demo_tool.resolve_path(args.character_catalog) if args.character_catalog else None,
        roster_dir=demo_tool.resolve_path(args.roster_dir) if args.roster_dir else None,
        tier_snapshot=demo_tool.resolve_path(args.tier_snapshot) if args.tier_snapshot else None,
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


def run_normalize(args: argparse.Namespace) -> int:
    result = normalize_tool.normalize_file(
        normalize_tool.resolve_path(args.parsed),
        normalize_tool.resolve_path(args.output_dir) if args.output_dir else normalize_tool.DEFAULT_OUTPUT_DIR,
    )
    print(f"normalized_json: {result['normalized_json']}")
    print(f"normalized_md: {result['normalized_md']}")
    return 0


def run_diff(args: argparse.Namespace) -> int:
    result = diff_tool.diff_files(
        normalize_tool.resolve_path(args.old),
        normalize_tool.resolve_path(args.new),
        normalize_tool.resolve_path(args.output_dir) if args.output_dir else None,
    )
    print(f"diff_json: {result['output_json']}")
    print(f"diff_md: {result['output_md']}")
    return 0


def run_plan(args: argparse.Namespace) -> int:
    snapshot_paths = [planner_tool.resolve_path(path) for path in args.snapshot]
    if args.snapshot_manifest:
        snapshot_paths.extend(planner_tool.load_manifest_snapshots(planner_tool.resolve_path(args.snapshot_manifest)))
    report = planner_tool.generate_report(
        snapshot_paths,
        planner_tool.resolve_path(args.targets),
        planner_tool.resolve_path(args.output_dir),
        history_index=planner_tool.resolve_path(args.history_index) if args.history_index else None,
        character_catalog=planner_tool.resolve_path(args.character_catalog) if args.character_catalog else None,
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    print(f"plan_item_count: {len(report['plan_items'])}")
    print(f"output_json: {report['output_json']}")
    print(f"output_md: {report['output_md']}")
    return 0


def run_targets(args: argparse.Namespace) -> int:
    try:
        if args.manifest and (args.url or args.input):
            raise target_tool.TargetIntakeError("--manifest cannot be combined with --url or --input")
        if args.manifest:
            game, source_type, sources, defaults = target_tool.source_cases_from_manifest(target_tool.resolve_path(args.manifest))
        else:
            game, source_type, sources, defaults = target_tool.source_cases_from_args(args)
        targets = target_tool.prepare_targets(
            game=game,
            source_type=source_type,
            sources=sources,
            output_dir=target_tool.resolve_path(args.output_dir),
            manifest_defaults=defaults,
        )
    except target_tool.TargetIntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"target_count: {len(targets['targets'])}")
    print(f"source_count: {len(targets['sources'])}")
    freshness = targets.get("freshness", {}) if isinstance(targets.get("freshness"), dict) else {}
    print(f"freshness_level: {freshness.get('level', 'unknown')}")
    print(f"stale_source_count: {freshness.get('stale_source_count', 0)}")
    for warning in targets.get("warnings", []):
        print(f"warning: {warning}")
    print(f"output_json: {targets['output_json']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Miho probe command shell.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the local demo pipeline and render a dashboard.")
    source = demo.add_mutually_exclusive_group()
    source.add_argument("--images-dir", default=None, help="Image directory. Default is figs when no source is provided.")
    source.add_argument("--parsed-dir", default=None, help="Parsed JSON directory. Does not rerun OCR.")
    source.add_argument("--manifest", default=None, help="Demo manifest with image or parsed cases.")
    demo.add_argument("--output-dir", default=str(demo_tool.DEFAULT_OUTPUT_DIR), help="Output directory.")
    demo.add_argument("--expected-dir", default=str(demo_tool.DEFAULT_EXPECTED_DIR), help="Expected JSON directory.")
    demo.add_argument("--engine", choices=("auto", "tesseract", "paddle", "rapidocr", "none"), default="paddle")
    demo.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    demo.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card")
    demo.add_argument("--open", action="store_true", help="Open generated dashboard.")
    demo.add_argument("--latest-only", action="store_true", help="In parsed-dir mode, keep only the newest parsed JSON for each source image.")
    demo.add_argument("--new-only", action="store_true", help="In image mode, process only new or changed images according to the update state file.")
    demo.add_argument("--clean-demo", action="store_true", help="Clean the demo output directory before running. Limited to data/probes subdirectories.")
    demo.add_argument("--state-file", default=None, help="Image update state JSON. Default: <output-dir>/update_state.json.")
    demo.add_argument("--targets", default=None, help="Optional planner targets JSON. Generates a local training priority report.")
    demo.add_argument("--target-source-manifest", default=None, help="Optional public/local endgame source manifest. Generates targets before planner.")
    demo.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for planner target matching.")
    demo.add_argument("--roster-dir", default=str(demo_tool.DEFAULT_ROSTER_DIR), help="Local accepted roster directory. Default: data/probes/roster.")
    demo.add_argument("--tier-snapshot", default=None, help="Optional local tier/value snapshot JSON. Does not fetch network data.")
    demo.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    demo.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget for planner. Default: 240.")
    demo.add_argument("--horizon-days", type=float, default=None, help="Planner horizon in days. Default: 7.")
    demo.set_defaults(handler=run_demo)

    normalize = subparsers.add_parser("normalize", help="Normalize one parsed JSON.")
    normalize.add_argument("--parsed", required=True, help="Parsed JSON path.")
    normalize.add_argument("--output-dir", default=None, help="Output directory.")
    normalize.set_defaults(handler=run_normalize)

    diff = subparsers.add_parser("diff", help="Diff two normalized snapshots.")
    diff.add_argument("--old", required=True, help="Old normalized JSON.")
    diff.add_argument("--new", required=True, help="New normalized JSON.")
    diff.add_argument("--output-dir", default=None, help="Output directory.")
    diff.set_defaults(handler=run_diff)

    plan = subparsers.add_parser("plan", help="Generate a local training priority report from normalized snapshots.")
    plan.add_argument("--snapshot", action="append", default=[], help="Normalized snapshot JSON. Can be repeated.")
    plan.add_argument("--snapshot-manifest", default=None, help="JSON manifest containing a snapshots list.")
    plan.add_argument("--targets", required=True, help="Local endgame target configuration JSON.")
    plan.add_argument("--history-index", default=None, help="Optional snapshot_history/index.json for long-term continuity context.")
    plan.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for target matching.")
    plan.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget. Default: 240.")
    plan.add_argument("--horizon-days", type=float, default=None, help="Planning horizon in days. Default: 7.")
    plan.add_argument("--output-dir", default=str(planner_tool.DEFAULT_OUTPUT_DIR), help="Output directory.")
    plan.set_defaults(handler=run_plan)

    targets = subparsers.add_parser("targets", help="Prepare local planner target JSON from public endgame sources.")
    targets.add_argument("--manifest", default=None, help="JSON manifest containing game/source_type/sources.")
    targets.add_argument("--url", action="append", default=[], help="Public http(s) source URL. Can be repeated.")
    targets.add_argument("--input", action="append", default=[], help="Saved public text/HTML source file. Can be repeated.")
    targets.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    targets.add_argument(
        "--source-type",
        choices=("manual", "public_web_snapshot", "official_snapshot", "official_current", "mock"),
        default="public_web_snapshot",
    )
    targets.add_argument("--activity-name", default=None)
    targets.add_argument("--target-tier", default="待确认")
    targets.add_argument("--priority", choices=("high", "medium", "low"), default="medium")
    targets.add_argument("--preferred-character", action="append", default=[])
    targets.add_argument("--mechanic-tag", action="append", default=[])
    targets.add_argument("--weakness-tag", action="append", default=[])
    targets.add_argument("--character-level", default=60)
    targets.add_argument("--equipment-level", default=60)
    targets.add_argument("--skill-level", default=8)
    targets.add_argument("--drive-disc-level", default=12)
    targets.add_argument("--stat", action="append", default=[], help="Minimum stat in key=value form, e.g. atk=2000.")
    targets.add_argument("--max-source-age-hours", type=float, default=target_tool.DEFAULT_MAX_SOURCE_AGE_HOURS)
    targets.add_argument("--output-dir", default=str(target_tool.DEFAULT_OUTPUT_DIR), help="Output directory.")
    targets.set_defaults(handler=run_targets)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
