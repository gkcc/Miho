#!/usr/bin/env python
"""Small command shell for local Miho probe workflows."""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
import sys
import webbrowser
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import diff_normalized_snapshots as diff_tool  # noqa: E402
import normalize_export_parse as normalize_tool  # noqa: E402
import plan_training_priorities as planner_tool  # noqa: E402
import prepare_endgame_targets as target_tool  # noqa: E402
import render_demo_dashboard as dashboard_tool  # noqa: E402
import run_demo_pipeline as demo_tool  # noqa: E402


def detect_project_root() -> Path:
    candidates = [Path.cwd().resolve(), Path(sys.executable).resolve().parent, Path(__file__).resolve().parent]
    for base in candidates:
        for candidate in (base, *base.parents):
            if (candidate / "README.md").exists() and (candidate / "tools" / "probes").exists():
                return candidate
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = detect_project_root()
DEFAULT_DEMO_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_DASHBOARD_HTML = DEFAULT_DEMO_OUTPUT_DIR / "index.html"
DEFAULT_DEMO_SUMMARY = DEFAULT_DEMO_OUTPUT_DIR / "demo_summary.json"
DEFAULT_EXPECTED_DIR = PROJECT_ROOT / "data" / "probes" / "expected"
DEFAULT_ROSTER_DIR = PROJECT_ROOT / "data" / "probes" / "roster"
DEFAULT_NORMALIZED_DIR = PROJECT_ROOT / "data" / "probes" / "normalized"
DEFAULT_PLANNER_DIR = PROJECT_ROOT / "data" / "probes" / "planner"
DEFAULT_TARGETS_DIR = PROJECT_ROOT / "data" / "probes" / "targets"
DEFAULT_REPLAY_MANIFEST = PROJECT_ROOT / "data" / "probes" / "replay_manifest.json"
LEGACY_DASHBOARD_MARKERS = (
    "Brief Warning",
    "brief status",
    "trusted ready",
    "ready targets",
    "pending review",
    "watch only",
    "pending 只会生成复核模板",
    "watch_only",
)
_REPLAY_TOOL = None


class CliReplayError(RuntimeError):
    pass


def load_replay_tool():
    global _REPLAY_TOOL
    if _REPLAY_TOOL is not None:
        return _REPLAY_TOOL
    script_path = PROJECT_ROOT / "tools" / "probes" / "run_export_replay_batch.py"
    if not script_path.exists():
        raise CliReplayError(f"Replay script does not exist: {script_path}")
    spec = importlib.util.spec_from_file_location("run_export_replay_batch_cli", script_path)
    if spec is None or spec.loader is None:
        raise CliReplayError(f"Unable to load replay script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _REPLAY_TOOL = module
    return module


def resolve_cli_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def has_legacy_dashboard_markup(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return any(marker in text for marker in LEGACY_DASHBOARD_MARKERS)


def render_cached_dashboard(summary_path: Path, dashboard_path: Path) -> dict[str, str]:
    summary = dashboard_tool.load_json(summary_path)
    return dashboard_tool.render_dashboard(summary, dashboard_path)


def run_dashboard(args: argparse.Namespace) -> int:
    dashboard_path = resolve_cli_path(args.dashboard)
    summary_path = resolve_cli_path(args.summary)
    should_refresh = bool(args.refresh)
    if dashboard_path.exists() and has_legacy_dashboard_markup(dashboard_path):
        should_refresh = True
    if dashboard_path.exists() and summary_path.exists() and dashboard_path.stat().st_mtime < summary_path.stat().st_mtime:
        should_refresh = True
    if not dashboard_path.exists() or should_refresh:
        if not summary_path.exists():
            print("Miho Dashboard 还没有生成。", file=sys.stderr)
            print("先运行：scripts\\run_miho_demo.bat --fresh", file=sys.stderr)
            return 1
        try:
            render_cached_dashboard(summary_path, dashboard_path)
        except dashboard_tool.DashboardError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"dashboard_refreshed: {dashboard_path}")
    else:
        print(f"dashboard_cached: {dashboard_path}")
    if args.open:
        webbrowser.open(dashboard_path.resolve().as_uri())
        print(f"dashboard_opened: {dashboard_path}")
    else:
        print(f"dashboard_html: {dashboard_path}")
    return 0


def run_demo(args: argparse.Namespace) -> int:
    summary = demo_tool.run_pipeline(
        images_dir=resolve_cli_path(args.images_dir) if args.images_dir else None,
        parsed_dir=resolve_cli_path(args.parsed_dir) if args.parsed_dir else None,
        manifest=resolve_cli_path(args.manifest) if args.manifest else None,
        output_dir=resolve_cli_path(args.output_dir),
        expected_dir=resolve_cli_path(args.expected_dir),
        engine=args.engine,
        game=args.game,
        layout=args.layout,
        open_dashboard=args.open,
        latest_only=args.latest_only,
        clean_demo=args.clean_demo,
        targets=resolve_cli_path(args.targets) if args.targets else None,
        new_only=args.new_only,
        state_file=resolve_cli_path(args.state_file) if args.state_file else None,
        history_dir=resolve_cli_path(args.history_dir) if args.history_dir else None,
        target_source_manifest=resolve_cli_path(args.target_source_manifest) if args.target_source_manifest else None,
        character_catalog=resolve_cli_path(args.character_catalog) if args.character_catalog else None,
        roster_dir=resolve_cli_path(args.roster_dir) if args.roster_dir else None,
        tier_snapshot=resolve_cli_path(args.tier_snapshot) if args.tier_snapshot else None,
        tier_stale_days=getattr(args, "tier_stale_days", 60),
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


def replay_default_output_dir() -> Path:
    stamp = datetime.now().astimezone().isoformat(timespec="seconds").replace(":", "").replace("+", "_").replace("-", "").replace("T", "_")
    return PROJECT_ROOT / "data" / "probes" / "replay_batches" / stamp


def replay_case_from_paths(parsed: str, expected: str, name: str | None = None) -> dict[str, str]:
    parsed_path = resolve_cli_path(parsed)
    expected_path = resolve_cli_path(expected)
    return {
        "name": name or parsed_path.stem,
        "parsed": str(parsed_path),
        "expected": str(expected_path),
    }


def load_replay_manifest(path: Path) -> list[dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliReplayError(f"Replay manifest is invalid JSON: {path}. Details: {exc}") from exc
    if isinstance(data, list):
        raw_cases = data
    elif isinstance(data, dict):
        raw_cases = data.get("cases")
    else:
        raw_cases = None
    if not isinstance(raw_cases, list):
        raise CliReplayError("Replay manifest must be a list or an object with a 'cases' list")
    cases: list[dict[str, str]] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise CliReplayError(f"Manifest case #{index} must be an object")
        parsed = item.get("parsed")
        expected = item.get("expected")
        if not parsed or not expected:
            raise CliReplayError(f"Manifest case #{index} must include parsed and expected")
        cases.append(replay_case_from_paths(str(parsed), str(expected), str(item.get("name") or f"case_{index}")))
    return cases


def build_replay_cases(args: argparse.Namespace) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    has_inline_cases = bool(args.case or args.parsed or args.expected)
    manifest_value = args.manifest
    if not manifest_value and not has_inline_cases:
        manifest_value = DEFAULT_REPLAY_MANIFEST
    if manifest_value:
        manifest_path = resolve_cli_path(manifest_value)
        if not manifest_path.exists():
            raise CliReplayError(f"Replay manifest does not exist: {manifest_path}")
        cases.extend(load_replay_manifest(manifest_path))
    for value in args.case or []:
        if "=" not in value:
            raise CliReplayError("--case must use parsed.json=expected.json")
        parsed, expected = value.split("=", 1)
        cases.append(replay_case_from_paths(parsed.strip(), expected.strip()))
    parsed_values = args.parsed or []
    expected_values = args.expected or []
    if parsed_values or expected_values:
        if len(parsed_values) != len(expected_values):
            raise CliReplayError("--parsed and --expected must be provided in equal counts")
        for parsed, expected in zip(parsed_values, expected_values):
            cases.append(replay_case_from_paths(parsed, expected))
    if not cases:
        raise CliReplayError("Provide at least one replay case or manifest")
    return cases


def run_replay(args: argparse.Namespace) -> int:
    try:
        cases = build_replay_cases(args)
        output_dir = resolve_cli_path(args.output_dir) if args.output_dir else replay_default_output_dir()
        replay_tool = load_replay_tool()
        summary = replay_tool.run_batch(
            cases,
            output_dir=output_dir,
            loose_numeric_text=not args.strict_leading_zero,
            rebuild=not args.no_rebuild,
        )
    except (OSError, CliReplayError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("准确率验收入口：MihoProbe.exe replay --manifest data\\probes\\replay_manifest.json", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("准确率验收入口：MihoProbe.exe replay --manifest data\\probes\\replay_manifest.json", file=sys.stderr)
        return 1
    p0_9 = summary["p0_9"]
    passed = bool(p0_9["meets_p0_9_batch_standard"])
    print("准确率验收：" + ("通过" if passed else "未通过"))
    print(f"case_count: {p0_9['case_count']}")
    print(f"average_pass_rate: {p0_9['average_pass_rate_percent']}%")
    print(f"meets_p0_9_batch_standard: {p0_9['meets_p0_9_batch_standard']}")
    if p0_9.get("blockers"):
        print("blockers:")
        for blocker in p0_9["blockers"]:
            print(f"- {blocker}")
    print(f"summary_md: {summary['summary_md']}")
    print(f"summary_json: {summary['summary_json']}")
    if args.open:
        webbrowser.open(Path(summary["summary_md"]).resolve().as_uri())
        print(f"summary_opened: {summary['summary_md']}")
    return 0 if passed else 1


def run_normalize(args: argparse.Namespace) -> int:
    result = normalize_tool.normalize_file(
        resolve_cli_path(args.parsed),
        resolve_cli_path(args.output_dir) if args.output_dir else DEFAULT_NORMALIZED_DIR,
    )
    print(f"normalized_json: {result['normalized_json']}")
    print(f"normalized_md: {result['normalized_md']}")
    return 0


def run_diff(args: argparse.Namespace) -> int:
    result = diff_tool.diff_files(
        resolve_cli_path(args.old),
        resolve_cli_path(args.new),
        resolve_cli_path(args.output_dir) if args.output_dir else None,
    )
    print(f"diff_json: {result['output_json']}")
    print(f"diff_md: {result['output_md']}")
    return 0


def run_plan(args: argparse.Namespace) -> int:
    snapshot_paths = [resolve_cli_path(path) for path in args.snapshot]
    if args.snapshot_manifest:
        snapshot_paths.extend(planner_tool.load_manifest_snapshots(resolve_cli_path(args.snapshot_manifest)))
    report = planner_tool.generate_report(
        snapshot_paths,
        resolve_cli_path(args.targets),
        resolve_cli_path(args.output_dir),
        history_index=resolve_cli_path(args.history_index) if args.history_index else None,
        character_catalog=resolve_cli_path(args.character_catalog) if args.character_catalog else None,
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
            game, source_type, sources, defaults = target_tool.source_cases_from_manifest(resolve_cli_path(args.manifest))
        else:
            game, source_type, sources, defaults = target_tool.source_cases_from_args(args)
        targets = target_tool.prepare_targets(
            game=game,
            source_type=source_type,
            sources=sources,
            output_dir=resolve_cli_path(args.output_dir),
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

    dashboard = subparsers.add_parser("dashboard", help="Open the cached local dashboard without rerunning OCR.")
    dashboard.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD_HTML), help="Dashboard HTML path.")
    dashboard.add_argument("--summary", default=str(DEFAULT_DEMO_SUMMARY), help="Demo summary JSON used to refresh cached HTML.")
    dashboard.add_argument("--refresh", action="store_true", help="Force refresh from summary before opening.")
    dashboard.add_argument("--open", action="store_true", default=True, help="Open the dashboard in the default browser. Default: true.")
    dashboard.add_argument("--no-open", action="store_false", dest="open", help="Render/check only; do not open a browser.")
    dashboard.set_defaults(handler=run_dashboard)

    demo = subparsers.add_parser("demo", help="Run the local demo pipeline and render a dashboard.")
    source = demo.add_mutually_exclusive_group()
    source.add_argument("--images-dir", default=None, help="Image directory. Default is figs when no source is provided.")
    source.add_argument("--parsed-dir", default=None, help="Parsed JSON directory. Does not rerun OCR.")
    source.add_argument("--manifest", default=None, help="Demo manifest with image or parsed cases.")
    demo.add_argument("--output-dir", default=str(DEFAULT_DEMO_OUTPUT_DIR), help="Output directory.")
    demo.add_argument("--expected-dir", default=str(DEFAULT_EXPECTED_DIR), help="Expected JSON directory.")
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
    demo.add_argument("--roster-dir", default=str(DEFAULT_ROSTER_DIR), help="Local accepted roster directory. Default: data/probes/roster.")
    demo.add_argument("--tier-snapshot", default=None, help="Optional local tier/value snapshot JSON. Does not fetch network data.")
    demo.add_argument("--tier-stale-days", type=int, default=60, help="Mark tier sources older than this many days as stale. Default: 60.")
    demo.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    demo.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget for planner. Default: 240.")
    demo.add_argument("--horizon-days", type=float, default=None, help="Planner horizon in days. Default: 7.")
    demo.set_defaults(handler=run_demo)

    replay = subparsers.add_parser("replay", help="Run P0.9 parsed-vs-expected replay acceptance without OCR.")
    replay.add_argument("--manifest", default=None, help="Replay manifest. Default when no inline cases are provided: data/probes/replay_manifest.json.")
    replay.add_argument("--case", action="append", help="Replay case as parsed.json=expected.json. Can be repeated.")
    replay.add_argument("--parsed", action="append", help="Parsed JSON path. Pair with --expected; can be repeated.")
    replay.add_argument("--expected", action="append", help="Expected JSON path. Pair with --parsed; can be repeated.")
    replay.add_argument("--output-dir", default=None, help="Output directory. Default: data/probes/replay_batches/<timestamp>.")
    replay.add_argument("--strict-leading-zero", action="store_true", help="Treat numeric text such as '08' and '8' as different.")
    replay.add_argument("--no-rebuild", action="store_true", help="Compare stored extracted_draft as-is instead of rebuilding from text_blocks.")
    replay.add_argument("--open", action="store_true", default=True, help="Open the Markdown summary. Default: true.")
    replay.add_argument("--no-open", action="store_false", dest="open", help="Do not open the Markdown summary.")
    replay.set_defaults(handler=run_replay)

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
    plan.add_argument("--output-dir", default=str(DEFAULT_PLANNER_DIR), help="Output directory.")
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
    targets.add_argument("--output-dir", default=str(DEFAULT_TARGETS_DIR), help="Output directory.")
    targets.set_defaults(handler=run_targets)
    return parser


def main() -> int:
    if len(sys.argv) == 1:
        args = argparse.Namespace(
            dashboard=str(DEFAULT_DASHBOARD_HTML),
            summary=str(DEFAULT_DEMO_SUMMARY),
            refresh=False,
            open=True,
        )
        return run_dashboard(args)
    parser = build_arg_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
