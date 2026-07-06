from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.hf_client import HuggingFaceClient
from hsr_endgame_exporter.normalize import date_or_none, normalize_character_id, parse_date
from miho_core.evidence import (
    load_name_index,
    load_planned_slugs_from_banner_plan,
    split_slugs,
    write_coverage_reports,
    write_evidence_report,
)
from miho_core.local_server import run_server
from miho_core.pull_value import write_gpt_review_packet, write_pull_value_report

from .constants import DEFAULT_MODES, DEFAULT_REPO_ID, MODE_URLS
from .decision_report import run_decision_report
from .exporters import (
    build_name_rows,
    build_tier_usage_trend,
    enrich_names,
    write_outputs,
)
from .hub import write_visualizer_hub
from .official_names import load_official_agents, load_official_bangboo, official_name_map
from .parsers import (
    make_phase_row,
    parse_bangboo_rows,
    parse_builds_character_rows,
    parse_team_rows,
)
from .prydwen import (
    fetch_and_parse_tier,
    fetch_prydwen_teams,
    merge_changelog_history,
    merge_tier_history,
)
from .visualizer import write_visualizer_app

VERSION_DIR_RE = re.compile(r"^\d+\.\d+\.\d+$")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "export":
        try:
            run_export(args)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"export failed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "decision":
        try:
            run_decision_report(args.box, args.out, args.rules)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"decision failed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "evidence":
        try:
            run_evidence(args)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"evidence failed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "coverage":
        try:
            run_coverage(args)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"coverage failed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "pull-value":
        try:
            run_pull_value(args)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"pull-value failed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "review-packet":
        try:
            run_review_packet(args)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"review-packet failed: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "serve":
        run_server(args.root, args.host, args.port)
        return 0
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m zzz_endgame_exporter")
    subparsers = parser.add_subparsers(dest="command")
    export = subparsers.add_parser("export", help="Export local Zenless Zone Zero endgame data tables")
    today = date.today()
    export.add_argument("--from-date", default=(today - timedelta(days=183)).isoformat())
    export.add_argument("--to-date", default=today.isoformat())
    export.add_argument("--out", default="./zzz_endgame_export")
    export.add_argument("--modes", default=",".join(DEFAULT_MODES))
    export.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    export.add_argument(
        "--include-teams",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include team composition data from Hugging Face comps files.",
    )
    export.add_argument(
        "--include-prydwen-visible",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Supplement with Prydwen visible teams when the page exposes them.",
    )
    export.add_argument(
        "--include-prydwen-tier",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fetch Prydwen ZZZ tier list and changelog.",
    )
    export.add_argument(
        "--official-name-map",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fill Chinese names from official HoYoWiki ZZZ agent and Bangboo lists.",
    )
    export.add_argument("--prydwen-top-n", type=int, default=100)
    decision = subparsers.add_parser("decision", help="Build local Box pull/investment decision cards")
    decision.add_argument("--box", required=True, help="Path to local ZZZ box YAML/JSON file")
    decision.add_argument("--out", default="./zzz_endgame_export", help="Existing export directory and output target")
    decision.add_argument(
        "--rules",
        default="./configs/zzz_decision_rules.yaml",
        help="Decision rule YAML/JSON file. Missing file falls back to built-in defaults.",
    )
    evidence = subparsers.add_parser("evidence", help="Build evidence-first target-account team coverage")
    evidence.add_argument("--box", required=True, help="Path to local ZZZ box YAML/JSON file")
    evidence.add_argument("--out", default="./zzz_endgame_export", help="Existing export directory and output target")
    evidence.add_argument(
        "--planned-slugs",
        default="",
        help="Comma/semicolon separated planned agent slugs, e.g. nom,sunna.",
    )
    evidence.add_argument(
        "--plan",
        default="",
        help="Optional banner-plan YAML/JSON file. Characters in selected statuses are added to planned slugs.",
    )
    evidence.add_argument(
        "--plan-status",
        default="next",
        help="Comma/semicolon separated phase statuses to read from --plan. Defaults to next.",
    )
    evidence.add_argument(
        "--output",
        default="",
        help="Markdown output path. Defaults to <out>/evidence_pool_summary.md.",
    )
    evidence.add_argument("--limit", type=int, default=0, help="Limit evidence rows in Markdown; 0 writes all rows.")
    evidence.add_argument("--min-a-app-rate", type=float, default=10.0, help="Minimum app_rate percent for A confidence.")
    evidence.add_argument(
        "--include-missing",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include records with agents outside owned + planned as C confidence.",
    )
    coverage = subparsers.add_parser("coverage", help="Build split current/target team coverage reports")
    coverage.add_argument("--box", required=True, help="Path to local ZZZ box YAML/JSON file")
    coverage.add_argument("--out", default="./zzz_endgame_export", help="Existing export directory and output target")
    coverage.add_argument("--planned-slugs", default="", help="Comma/semicolon separated planned agent slugs.")
    coverage.add_argument("--plan", default="", help="Optional banner-plan YAML/JSON file.")
    coverage.add_argument("--plan-status", default="next", help="Comma/semicolon separated phase statuses to read from --plan.")
    coverage.add_argument("--limit", type=int, default=0, help="Limit report rows; 0 writes all rows.")
    coverage.add_argument("--min-a-app-rate", type=float, default=10.0, help="Minimum app_rate percent for A confidence.")
    coverage.add_argument("--aggregate-output", default="", help="Defaults to <out>/team_signature_aggregates.csv.")
    coverage.add_argument("--current-output", default="", help="Defaults to <out>/current_box_team_coverage.md.")
    coverage.add_argument("--target-output", default="", help="Defaults to <out>/target_box_team_coverage.md.")
    pull_value = subparsers.add_parser("pull-value", help="Build rerun/new-character pull value report")
    pull_value.add_argument("--box", required=True, help="Path to local ZZZ box YAML/JSON file")
    pull_value.add_argument("--out", default="./zzz_endgame_export", help="Existing export directory and output target")
    pull_value.add_argument("--plan", default="./configs/zzz_banner_plan.json", help="Banner-plan YAML/JSON file")
    pull_value.add_argument("--plan-status", default="current,next", help="Comma/semicolon separated phase statuses to read from --plan.")
    pull_value.add_argument("--planned-slugs", default="", help="Extra comma/semicolon separated planned agent slugs.")
    pull_value.add_argument("--mechanism-notes-dir", default="", help="Defaults to <plan dir>/zzz_mechanism_notes.")
    pull_value.add_argument("--output", default="", help="Explicit single report path. Default writes <out>/current_pull_value_report.md and <out>/next_pull_value_report.md.")
    review_packet = subparsers.add_parser("review-packet", help="Build no-key GPT reviewer packet for interactive X+X review")
    review_packet.add_argument("--box", required=True, help="Path to local ZZZ box YAML/JSON file")
    review_packet.add_argument("--out", default="./zzz_endgame_export", help="Existing export directory and output target")
    review_packet.add_argument("--plan", default="./configs/zzz_banner_plan.json", help="Banner-plan YAML/JSON file")
    review_packet.add_argument("--plan-status", default="current,next", help="Comma/semicolon separated phase statuses to read from --plan.")
    review_packet.add_argument("--planned-slugs", default="", help="Extra comma/semicolon separated planned agent slugs.")
    review_packet.add_argument("--mechanism-notes-dir", default="", help="Defaults to <plan dir>/zzz_mechanism_notes.")
    review_packet.add_argument("--output", default="", help="Explicit single packet path. Default writes <out>/current_gpt_pull_reviewer_packet.md and <out>/next_gpt_pull_reviewer_packet.md.")
    serve = subparsers.add_parser("serve", help="Serve visualizer with local Box auto-save API")
    serve.add_argument("--root", default=".")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def run_evidence(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    names = load_name_index(out_dir)
    planned = split_slugs(args.planned_slugs)
    if args.plan:
        planned.extend(
            load_planned_slugs_from_banner_plan(
                args.plan,
                statuses=split_slugs(args.plan_status),
                names=names,
            )
        )
    planned = list(dict.fromkeys(planned))
    output = Path(args.output) if args.output else out_dir / "evidence_pool_summary.md"
    write_evidence_report(
        out_dir,
        box_path=args.box,
        planned_slugs=planned,
        output_path=output,
        title="绝区零目标账号证据池队伍覆盖",
        include_missing=args.include_missing,
        limit=args.limit,
        min_a_app_rate=args.min_a_app_rate,
    )


def run_coverage(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    planned = _planned_slugs_from_args(args, out_dir)
    write_coverage_reports(
        out_dir,
        box_path=args.box,
        planned_slugs=planned,
        current_output_path=Path(args.current_output) if args.current_output else out_dir / "current_box_team_coverage.md",
        target_output_path=Path(args.target_output) if args.target_output else out_dir / "target_box_team_coverage.md",
        aggregate_output_path=Path(args.aggregate_output) if args.aggregate_output else out_dir / "team_signature_aggregates.csv",
        limit=args.limit,
        min_a_app_rate=args.min_a_app_rate,
    )


def run_pull_value(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    planned = split_slugs(args.planned_slugs)
    statuses = split_slugs(args.plan_status) or ["current", "next"]
    if args.output:
        write_pull_value_report(
            out_dir,
            box_path=args.box,
            plan_path=args.plan if args.plan else None,
            planned_slugs=planned,
            statuses=statuses,
            mechanism_notes_dir=args.mechanism_notes_dir or None,
            output_path=Path(args.output),
        )
        return
    for status in statuses:
        write_pull_value_report(
            out_dir,
            box_path=args.box,
            plan_path=args.plan if args.plan else None,
            planned_slugs=planned,
            statuses=[status],
            mechanism_notes_dir=args.mechanism_notes_dir or None,
            output_path=out_dir / f"{_safe_report_status(status)}_pull_value_report.md",
        )


def run_review_packet(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    planned = split_slugs(args.planned_slugs)
    statuses = split_slugs(args.plan_status) or ["current", "next"]
    if args.output:
        write_gpt_review_packet(
            out_dir,
            box_path=args.box,
            plan_path=args.plan if args.plan else None,
            planned_slugs=planned,
            statuses=statuses,
            mechanism_notes_dir=args.mechanism_notes_dir or None,
            output_path=Path(args.output),
        )
        return
    for status in statuses:
        write_gpt_review_packet(
            out_dir,
            box_path=args.box,
            plan_path=args.plan if args.plan else None,
            planned_slugs=planned,
            statuses=[status],
            mechanism_notes_dir=args.mechanism_notes_dir or None,
            output_path=out_dir / f"{_safe_report_status(status)}_gpt_pull_reviewer_packet.md",
        )


def _safe_report_status(status: str) -> str:
    cleaned = normalize_character_id(status)
    return cleaned or "status"


def _planned_slugs_from_args(args: argparse.Namespace, out_dir: Path) -> list[str]:
    names = load_name_index(out_dir)
    planned = split_slugs(getattr(args, "planned_slugs", ""))
    if getattr(args, "plan", ""):
        planned.extend(
            load_planned_slugs_from_banner_plan(
                args.plan,
                statuses=split_slugs(getattr(args, "plan_status", "next")),
                names=names,
            )
        )
    return list(dict.fromkeys(planned))


def run_export(args: argparse.Namespace) -> None:
    from_date = parse_date(args.from_date)
    to_date = parse_date(args.to_date)
    from_dt = date.fromisoformat(from_date)
    to_dt = date.fromisoformat(to_date)
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    out_dir = Path(args.out)
    raw_hf_dir = out_dir / "raw" / "hf"
    raw_prydwen_dir = out_dir / "raw" / "prydwen"
    warnings: list[str] = []
    errors: list[str] = []

    client = HuggingFaceClient(repo_id=args.repo_id)
    root_tree = _safe_list_tree(client, "", warnings, errors)
    version_dirs = sorted(
        item["path"]
        for item in root_tree
        if item.get("type") == "directory" and VERSION_DIR_RE.match(str(item.get("path", "")))
    )
    if not version_dirs:
        raise RuntimeError("no version directories found in Hugging Face dataset root")

    config = _download_json_save(client, "config.json", raw_hf_dir / "config.json", warnings, errors)
    prepared_config = _prepare_config(config if isinstance(config, dict) else {})
    selected_snapshots = _select_snapshots(version_dirs, prepared_config, from_dt, to_dt, warnings)
    if not selected_snapshots:
        warnings.append("no Hugging Face snapshots matched the requested date range")

    phase_rows: list[dict[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []
    tier_rows: list[dict[str, Any]] = []
    tier_history_rows: list[dict[str, Any]] = []
    changelog_rows: list[dict[str, Any]] = []
    changelog_history_rows: list[dict[str, Any]] = []

    for snapshot_id in selected_snapshots:
        phases, usage, teams = _process_snapshot(
            client=client,
            snapshot_id=snapshot_id,
            config_entry=prepared_config.get(snapshot_id),
            modes=modes,
            raw_hf_dir=raw_hf_dir,
            include_teams=args.include_teams,
            warnings=warnings,
            errors=errors,
        )
        phase_rows.extend(phases)
        usage_rows.extend(usage)
        team_rows.extend(teams)

    if args.include_prydwen_visible:
        team_rows.extend(
            _process_prydwen_visible(
                modes=modes,
                phase_rows=phase_rows,
                raw_prydwen_dir=raw_prydwen_dir,
                top_n=args.prydwen_top_n,
                warnings=warnings,
            )
        )

    if args.include_prydwen_tier:
        tier_rows, changelog_rows = fetch_and_parse_tier(out_dir / "raw" / "prydwen_tier", warnings)

    official_rows: list[dict[str, Any]] = []
    if args.official_name_map:
        hoyowiki_dir = out_dir / "raw" / "hoyowiki"
        official_rows.extend(load_official_agents(hoyowiki_dir, warnings))
        official_rows.extend(load_official_bangboo(hoyowiki_dir, warnings))
    official = official_name_map(official_rows)

    slugs = _collect_slugs(usage_rows, team_rows, tier_rows)
    name_rows, unresolved_rows = build_name_rows(slugs, official, tier_rows)
    for rows in (usage_rows, team_rows, tier_rows):
        enrich_names(rows, name_rows, tier_rows)

    tier_history_rows = merge_tier_history(out_dir / "prydwen_tier_history.csv", tier_rows)
    changelog_history_rows = merge_changelog_history(out_dir / "prydwen_tier_changelog_history.csv", changelog_rows)
    trend_rows = build_tier_usage_trend(tier_rows, usage_rows)

    write_outputs(
        out_dir,
        phase_rows=phase_rows,
        usage_rows=usage_rows,
        team_rows=team_rows,
        name_rows=name_rows,
        unresolved_rows=unresolved_rows,
        tier_rows=tier_rows,
        tier_history_rows=tier_history_rows,
        changelog_rows=changelog_rows,
        changelog_history_rows=changelog_history_rows,
        trend_rows=trend_rows,
        from_date=from_date,
        to_date=to_date,
        repo_id=args.repo_id,
        modes=modes,
        warnings=warnings,
        errors=errors,
    )
    write_visualizer_app(
        out_dir,
        usage_rows=usage_rows,
        tier_rows=tier_rows,
        team_rows=team_rows,
        name_rows=name_rows,
        changelog_rows=changelog_history_rows,
    )
    write_visualizer_hub(out_dir.parent, zzz_dir=out_dir.name)


def _process_snapshot(
    *,
    client: HuggingFaceClient,
    snapshot_id: str,
    config_entry: dict[str, Any] | None,
    modes: list[str],
    raw_hf_dir: Path,
    include_teams: bool,
    warnings: list[str],
    errors: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    snapshot_tree = _safe_list_tree(client, snapshot_id, warnings, errors)
    snapshot_paths = {str(item.get("path")) for item in snapshot_tree}
    has_builds = f"{snapshot_id}/builds.json" in snapshot_paths

    builds_data: list[dict[str, Any]] = []
    if has_builds:
        data = _download_json_save(
            client,
            f"{snapshot_id}/builds.json",
            _raw_path(raw_hf_dir, f"{snapshot_id}/builds.json"),
            warnings,
            errors,
        )
        if isinstance(data, list):
            builds_data = data
        else:
            warnings.append(f"{snapshot_id}/builds.json was not a list; skipped")

    phase_rows: list[dict[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []
    team_rows: list[dict[str, Any]] = []
    fallback_config = {"collect_date": "", **{mode: {"ver": snapshot_id} for mode in modes}}
    config = config_entry or fallback_config

    for mode in modes:
        chars_path = f"{snapshot_id}/{mode}/chars"
        comps_path = f"{snapshot_id}/{mode}/comps"
        char_files = _safe_list_tree(client, chars_path, warnings, errors, optional=True)
        comp_files = _safe_list_tree(client, comps_path, warnings, errors, optional=True)
        phase = make_phase_row(
            snapshot_id,
            mode,
            config,
            source_path=f"{snapshot_id}/",
            has_chars=has_builds or bool(char_files),
            has_comps=bool(comp_files),
            note="" if config_entry else "config missing; dates unavailable",
        )
        if not phase:
            warnings.append(f"{snapshot_id}/{mode}: mode config missing; skipped")
            continue
        phase_rows.append(phase)
        if builds_data:
            usage_rows.extend(
                parse_builds_character_rows(
                    builds_data,
                    phase,
                    source_file=f"{snapshot_id}/builds.json",
                    source_url=client.raw_url(f"{snapshot_id}/builds.json"),
                )
            )
        for item in char_files:
            source_path = str(item.get("path") or "")
            if item.get("type") != "file" or not source_path.endswith(".json"):
                continue
            if not source_path.endswith("bangboo_all.json"):
                continue
            data = _download_json_save(client, source_path, _raw_path(raw_hf_dir, source_path), warnings, errors)
            if isinstance(data, list):
                usage_rows.extend(
                    parse_bangboo_rows(
                        data,
                        phase,
                        source_file=source_path,
                        source_url=client.raw_url(source_path),
                    )
                )
        if include_teams:
            for item in comp_files:
                source_path = str(item.get("path") or "")
                if item.get("type") != "file" or not source_path.endswith(".json"):
                    continue
                data = _download_json_save(client, source_path, _raw_path(raw_hf_dir, source_path), warnings, errors)
                if isinstance(data, list):
                    team_rows.extend(
                        parse_team_rows(
                            data,
                            phase,
                            scope=Path(source_path).name,
                            source_kind="hf_comps",
                            source_file=source_path,
                            source_url=client.raw_url(source_path),
                        )
                    )
    return phase_rows, usage_rows, team_rows


def _process_prydwen_visible(
    *,
    modes: list[str],
    phase_rows: list[dict[str, Any]],
    raw_prydwen_dir: Path,
    top_n: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    latest_phase = _latest_phase_by_mode(phase_rows)
    output: list[dict[str, Any]] = []
    for mode in modes:
        phase = latest_phase.get(mode)
        if not phase:
            warnings.append(f"Prydwen ZZZ visible teams skipped for {mode}: no local phase row")
            continue
        teams_by_scope = fetch_prydwen_teams(mode, raw_prydwen_dir, warnings)
        if not teams_by_scope:
            warnings.append(f"Prydwen ZZZ {mode} parse warning: no visible teams extracted")
            continue
        for scope, rows in teams_by_scope.items():
            output.extend(
                parse_team_rows(
                    rows[:top_n],
                    phase,
                    scope=str(scope),
                    source_kind="prydwen_page",
                    source_file=f"raw/prydwen/{mode}.html",
                    source_url=MODE_URLS.get(mode, ""),
                )
            )
    return output


def _prepare_config(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    prepared: dict[str, dict[str, Any]] = {}
    for snapshot_id, entry in config.items():
        if not isinstance(entry, dict):
            continue
        prepared_entry = dict(entry)
        prepared_entry["collect_date_iso"] = parse_date(entry.get("collect_date"))
        for mode in DEFAULT_MODES:
            mode_config = entry.get(mode)
            if isinstance(mode_config, dict):
                prepared_mode = dict(mode_config)
                prepared_mode["start_iso"] = parse_date(mode_config.get("start"))
                prepared_mode["end_iso"] = parse_date(mode_config.get("end"))
                prepared_entry[mode] = prepared_mode
        prepared[snapshot_id] = prepared_entry
    return prepared


def _select_snapshots(
    version_dirs: list[str],
    prepared_config: dict[str, dict[str, Any]],
    from_dt: date,
    to_dt: date,
    warnings: list[str],
) -> list[str]:
    selected: list[str] = []
    for snapshot_id in version_dirs:
        collect_dt = date_or_none((prepared_config.get(snapshot_id) or {}).get("collect_date_iso"))
        if collect_dt is None:
            warnings.append(f"{snapshot_id}: collect_date missing; included without date filtering")
            selected.append(snapshot_id)
        elif from_dt <= collect_dt <= to_dt:
            selected.append(snapshot_id)
    return selected


def _latest_phase_by_mode(phase_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in phase_rows:
        mode = str(row.get("mode") or "")
        current = latest.get(mode)
        if current is None or str(row.get("collect_date", "")) >= str(current.get("collect_date", "")):
            latest[mode] = row
    return latest


def _collect_slugs(
    usage_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
) -> set[str]:
    slugs: set[str] = set()
    for row in usage_rows + tier_rows:
        slug = normalize_character_id(row.get("character_slug"))
        if slug:
            slugs.add(slug)
    for row in team_rows:
        for key in ("char_1_slug", "char_2_slug", "char_3_slug", "bangboo_slug"):
            slug = normalize_character_id(row.get(key))
            if slug:
                slugs.add(slug)
    return slugs


def _safe_list_tree(
    client: HuggingFaceClient,
    path: str,
    warnings: list[str],
    errors: list[str],
    *,
    optional: bool = False,
) -> list[dict[str, Any]]:
    try:
        return client.list_tree(path)
    except urllib.error.HTTPError as exc:
        message = f"failed to list HF path {path or '/'}: HTTP {exc.code}"
        (warnings if optional and exc.code == 404 else errors).append(message)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        errors.append(f"network failure while listing HF path {path or '/'}: {exc}")
    return []


def _download_json_save(
    client: HuggingFaceClient,
    path: str,
    destination: Path,
    warnings: list[str],
    errors: list[str],
) -> Any | None:
    if destination.exists():
        try:
            return json.loads(destination.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.append(f"cached JSON file {destination} was invalid; redownloading")
    try:
        text = client.download_text(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        return json.loads(text)
    except urllib.error.HTTPError as exc:
        errors.append(f"failed to download HF file {path}: HTTP {exc.code}")
    except json.JSONDecodeError as exc:
        warnings.append(f"failed to parse JSON file {path}: {exc}")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        errors.append(f"network failure while downloading HF file {path}: {exc}")
    return None


def _raw_path(raw_dir: Path, source_path: str) -> Path:
    return raw_dir.joinpath(*source_path.split("/"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
