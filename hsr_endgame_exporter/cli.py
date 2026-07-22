from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .constants import DEFAULT_MODES, DEFAULT_REPO_ID, MODE_CN, SUB_MODE_CN
from .exporters import write_all_outputs
from .hf_client import HuggingFaceClient
from .name_map import (
    NameMapBuilder,
    collect_names,
    enrich_character_rows,
    enrich_team_rows,
)
from .normalize import date_or_none, parse_date
from .official_names import load_hoyowiki_official_names
from .parsers import (
    histograph_fallback_character_rows,
    make_phase_row,
    parse_builds_character_rows,
    parse_chars_file_character_rows,
    parse_histograph_rows,
    parse_team_rows,
)
from .prydwen_scraper import PrydwenScraper
from .prydwen_tier import (
    build_tier_usage_trend,
    fetch_and_parse_prydwen_tier,
    generate_tier_usage_charts,
    merge_changelog_history,
    merge_tier_history,
)
from .report import write_report
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
    if args.command == "visualizer":
        try:
            run_visualizer(args)
        except Exception as exc:  # pragma: no cover - command boundary
            print(f"visualizer failed: {exc}", file=sys.stderr)
            return 1
        return 0
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m hsr_endgame_exporter")
    subparsers = parser.add_subparsers(dest="command")
    export = subparsers.add_parser("export", help="Export local HSR endgame data tables")
    today = date.today()
    export.add_argument("--from-date", default=(today - timedelta(days=183)).isoformat())
    export.add_argument("--to-date", default=today.isoformat())
    export.add_argument("--out", default="./hsr_endgame_export")
    export.add_argument("--modes", default=",".join(DEFAULT_MODES))
    export.add_argument(
        "--include-teams",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include team composition data from HF comps files.",
    )
    export.add_argument(
        "--include-prydwen-visible",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Supplement with Prydwen visible ranked teams.",
    )
    export.add_argument(
        "--include-prydwen-tier",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fetch Prydwen tier list roles, tiers, and changelog.",
    )
    export.add_argument("--prydwen-top-n", type=int, default=100)
    export.add_argument("--name-map-seed", default="")
    export.add_argument(
        "--official-name-map",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fill Chinese names from the official HoYoWiki HSR character list.",
    )
    export.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    visualizer = subparsers.add_parser("visualizer", help="Rebuild HSR visualizer from existing export CSV files")
    visualizer.add_argument("--out", default="./hsr_endgame_export", help="Existing export directory and output target")
    return parser


def read_csv(path: Path) -> list[dict[str, Any]]:
    import csv

    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def run_visualizer(args: argparse.Namespace) -> None:
    rebuild_visualizer_from_outputs(Path(args.out))


def rebuild_visualizer_from_outputs(out_dir: Path) -> None:
    dedup_team_path = out_dir / "team_rank_dedup_unordered.csv"
    team_path = dedup_team_path if dedup_team_path.exists() else out_dir / "team_rank_raw.csv"
    write_visualizer_app(
        out_dir,
        trend_rows=read_csv(out_dir / "prydwen_tier_usage_trend.csv"),
        tier_rows=read_csv(out_dir / "prydwen_tier_current.csv"),
        changelog_rows=read_csv(out_dir / "prydwen_tier_changelog_history.csv"),
        chart_rows=read_csv(out_dir / "prydwen_tier_charts.csv"),
        character_usage_rows=read_csv(out_dir / "character_usage_long.csv"),
        team_rank_rows=read_csv(team_path),
    )


def _write_final_outputs_and_visualizer(out_dir: Path, **output_rows: Any) -> dict[str, list[dict[str, Any]]]:
    """Write the canonical CSV artifacts before rebuilding the visualizer from them."""
    tables = write_all_outputs(out_dir, **output_rows)
    rebuild_visualizer_from_outputs(out_dir)
    return tables


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
    phase_rows: list[dict[str, Any]] = []
    character_rows: list[dict[str, Any]] = []
    histograph_rows: list[dict[str, Any]] = []
    team_raw_rows: list[dict[str, Any]] = []
    prydwen_tier_current_rows: list[dict[str, Any]] = []
    prydwen_tier_history_rows: list[dict[str, Any]] = []
    prydwen_tier_changelog_rows: list[dict[str, Any]] = []
    prydwen_tier_changelog_history_rows: list[dict[str, Any]] = []
    prydwen_tier_usage_trend_rows: list[dict[str, Any]] = []
    prydwen_tier_chart_rows: list[dict[str, Any]] = []

    root_tree = _safe_list_tree(client, "", warnings, errors)
    version_dirs = sorted(
        item["path"]
        for item in root_tree
        if item.get("type") == "directory" and VERSION_DIR_RE.match(item.get("path", ""))
    )
    if not version_dirs:
        raise RuntimeError("no version directories found in Hugging Face dataset root")

    config = _download_json_save(client, "config.json", raw_hf_dir / "config.json", warnings, errors)
    prepared_config = _prepare_config(config if isinstance(config, dict) else {})
    _warn_missing_config_snapshots(prepared_config, set(version_dirs), from_dt, to_dt, warnings)

    selected_snapshots = _select_snapshots(version_dirs, prepared_config, from_dt, to_dt, warnings)
    if not selected_snapshots:
        warnings.append("no Hugging Face snapshots matched the requested date range")

    for snapshot_id in selected_snapshots:
        snapshot_phase_rows, snapshot_character_rows, snapshot_histograph_rows, snapshot_team_rows = (
            _process_snapshot(
                client=client,
                snapshot_id=snapshot_id,
                config_entry=prepared_config.get(snapshot_id),
                modes=modes,
                raw_hf_dir=raw_hf_dir,
                include_teams=args.include_teams,
                warnings=warnings,
                errors=errors,
            )
        )
        phase_rows.extend(snapshot_phase_rows)
        character_rows.extend(snapshot_character_rows)
        histograph_rows.extend(snapshot_histograph_rows)
        team_raw_rows.extend(snapshot_team_rows)

    if args.include_prydwen_visible:
        team_raw_rows.extend(
            _process_prydwen(
                modes=modes,
                phase_rows=phase_rows,
                raw_prydwen_dir=raw_prydwen_dir,
                top_n=args.prydwen_top_n,
                warnings=warnings,
                errors=errors,
            )
        )

    if args.include_prydwen_tier:
        prydwen_tier_current_rows, prydwen_tier_changelog_rows = fetch_and_parse_prydwen_tier(
            out_dir / "raw" / "prydwen_tier",
            warnings,
        )

    name_builder = NameMapBuilder()
    if args.official_name_map:
        official_names = load_hoyowiki_official_names(out_dir / "raw" / "hoyowiki", warnings)
        name_builder.load_official(official_names)
    name_builder.load_seed(args.name_map_seed, warnings)
    for rows in (character_rows, histograph_rows, team_raw_rows, prydwen_tier_current_rows):
        collect_names(name_builder, rows)
    name_map_rows, unresolved_rows = name_builder.build_rows()
    enrich_character_rows(name_builder, character_rows)
    enrich_character_rows(name_builder, histograph_rows)
    enrich_character_rows(name_builder, prydwen_tier_current_rows)
    enrich_team_rows(name_builder, team_raw_rows)

    prydwen_tier_history_rows = merge_tier_history(
        out_dir / "prydwen_tier_history.csv",
        prydwen_tier_current_rows,
    )
    prydwen_tier_changelog_history_rows = merge_changelog_history(
        out_dir / "prydwen_tier_changelog_history.csv",
        prydwen_tier_changelog_rows,
    )
    prydwen_tier_usage_trend_rows = build_tier_usage_trend(
        prydwen_tier_current_rows,
        character_rows,
    )
    prydwen_tier_chart_rows = generate_tier_usage_charts(
        prydwen_tier_usage_trend_rows,
        out_dir / "charts" / "prydwen_tier_usage",
    )
    tables = _write_final_outputs_and_visualizer(
        out_dir,
        phase_rows=phase_rows,
        character_rows=character_rows,
        histograph_rows=histograph_rows,
        team_raw_rows=team_raw_rows,
        name_map_rows=name_map_rows,
        name_map_unresolved_rows=unresolved_rows,
        prydwen_tier_current_rows=prydwen_tier_current_rows,
        prydwen_tier_history_rows=prydwen_tier_history_rows,
        prydwen_tier_changelog_rows=prydwen_tier_changelog_rows,
        prydwen_tier_changelog_history_rows=prydwen_tier_changelog_history_rows,
        prydwen_tier_usage_trend_rows=prydwen_tier_usage_trend_rows,
        prydwen_tier_chart_rows=prydwen_tier_chart_rows,
        warnings=warnings,
    )
    write_report(
        out_dir / "export_report.md",
        from_date=from_date,
        to_date=to_date,
        repo_id=args.repo_id,
        modes=modes,
        tables=tables,
        warnings=warnings,
        errors=errors,
    )


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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    collect_date = (config_entry or {}).get("collect_date_iso", "")
    snapshot_tree = _safe_list_tree(client, snapshot_id, warnings, errors)
    snapshot_paths = {item.get("path") for item in snapshot_tree}
    has_histograph = f"{snapshot_id}/histograph.json" in snapshot_paths
    has_builds = f"{snapshot_id}/builds.json" in snapshot_paths

    mode_files: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for mode in modes:
        chars_path = f"{snapshot_id}/{mode}/chars"
        comps_path = f"{snapshot_id}/{mode}/comps"
        mode_files[mode] = {
            "chars": _safe_list_tree(client, chars_path, warnings, errors, optional=True),
            "comps": _safe_list_tree(client, comps_path, warnings, errors, optional=True),
        }

    phase_rows = [
        make_phase_row(
            snapshot_id=snapshot_id,
            config_entry=config_entry,
            mode=mode,
            source_path=f"{snapshot_id}/",
            has_chars=bool(mode_files[mode]["chars"]),
            has_comps=bool(mode_files[mode]["comps"]),
            has_histograph=has_histograph,
            collect_date=collect_date,
            note="" if config_entry else "config missing; dates unavailable",
        )
        for mode in modes
    ]
    phase_by_mode = {row["mode"]: row for row in phase_rows}

    builds_data = None
    if has_builds:
        builds_path = f"{snapshot_id}/builds.json"
        builds_data = _download_json_save(
            client,
            builds_path,
            _raw_path(raw_hf_dir, builds_path),
            warnings,
            errors,
        )
        if not isinstance(builds_data, list):
            builds_data = None
            warnings.append(f"{builds_path} was not a list; skipped as character usage source")

    character_rows: list[dict[str, Any]] = []
    for mode, phase_row in phase_by_mode.items():
        mode_rows: list[dict[str, Any]] = []
        if isinstance(builds_data, list):
            mode_rows.extend(
                parse_builds_character_rows(
                    snapshot_id=snapshot_id,
                    phase_row=phase_row,
                    builds=builds_data,
                    source_file=f"{snapshot_id}/builds.json",
                    source_url=client.raw_url(f"{snapshot_id}/builds.json"),
                )
            )
        if not mode_rows:
            for item in mode_files[mode]["chars"]:
                if item.get("type") != "file" or not str(item.get("path", "")).endswith(".json"):
                    continue
                source_path = item["path"]
                data = _download_json_save(
                    client,
                    source_path,
                    _raw_path(raw_hf_dir, source_path),
                    warnings,
                    errors,
                )
                mode_rows.extend(
                    parse_chars_file_character_rows(
                        snapshot_id=snapshot_id,
                        phase_row=phase_row,
                        data=data,
                        source_file=source_path,
                        source_url=client.raw_url(source_path),
                    )
                )
        character_rows.extend(mode_rows)

    histograph_rows: list[dict[str, Any]] = []
    if has_histograph:
        histograph_path = f"{snapshot_id}/histograph.json"
        histograph_data = _download_json_save(
            client,
            histograph_path,
            _raw_path(raw_hf_dir, histograph_path),
            warnings,
            errors,
        )
        if isinstance(histograph_data, list):
            histograph_rows = parse_histograph_rows(
                snapshot_id=snapshot_id,
                phase_rows=phase_by_mode,
                histograph=histograph_data,
                source_file=histograph_path,
            )
        else:
            warnings.append(f"{histograph_path} was not a list; skipped")

    modes_with_rows = {row["mode"] for row in character_rows}
    missing_modes = set(modes) - modes_with_rows
    if missing_modes and histograph_rows:
        character_rows.extend(
            histograph_fallback_character_rows(histograph_rows, phase_by_mode, missing_modes)
        )

    team_rows: list[dict[str, Any]] = []
    if include_teams:
        for mode, files in mode_files.items():
            for item in files["comps"]:
                if item.get("type") != "file" or not str(item.get("path", "")).endswith(".json"):
                    continue
                source_path = item["path"]
                data = _download_json_save(
                    client,
                    source_path,
                    _raw_path(raw_hf_dir, source_path),
                    warnings,
                    errors,
                )
                team_rows.extend(
                    parse_team_rows(
                        snapshot_id=snapshot_id,
                        phase_row=phase_by_mode[mode],
                        data=data,
                        source_kind="hf_comps",
                        source_file=source_path,
                        source_url=client.raw_url(source_path),
                        scope_hint=source_path,
                    )
                )

    return phase_rows, character_rows, histograph_rows, team_rows


def _process_prydwen(
    *,
    modes: list[str],
    phase_rows: list[dict[str, Any]],
    raw_prydwen_dir: Path,
    top_n: int,
    warnings: list[str],
    errors: list[str],
) -> list[dict[str, Any]]:
    scraper = PrydwenScraper()
    latest_phase = _latest_phase_by_mode(phase_rows)
    team_rows: list[dict[str, Any]] = []
    for mode in modes:
        phase_row = latest_phase.get(mode)
        if not phase_row:
            warnings.append(f"Prydwen skipped for {mode}: no phase row available")
            continue
        try:
            teams_by_scope, source_file, url = scraper.scrape_teams(mode, raw_dir=raw_prydwen_dir)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            warnings.append(f"Prydwen fetch failed for {mode}: {exc}")
            continue
        if not teams_by_scope:
            warnings.append(f"Prydwen parse warning for {mode}: no ranked team JSON block found")
            continue
        for scope, rows in teams_by_scope.items():
            parsed_rows = parse_team_rows(
                snapshot_id=phase_row["snapshot_id"],
                phase_row=phase_row,
                data=rows,
                source_kind="prydwen_page",
                source_file=source_file,
                source_url=url,
                scope_hint="top_combined.json",
                top_n=top_n,
            )
            for row in parsed_rows:
                row["scope"] = str(scope)
                row["sub_mode"] = "all_bosses" if mode == "aa" else "all"
                row["sub_mode_cn"] = SUB_MODE_CN["all_bosses"] if mode == "aa" else SUB_MODE_CN["all"]
            team_rows.extend(parsed_rows)
    return team_rows


def _latest_phase_by_mode(phase_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in phase_rows:
        mode = row["mode"]
        current = latest.get(mode)
        if current is None or str(row.get("collect_date", "")) >= str(current.get("collect_date", "")):
            latest[mode] = row
    return latest


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
        config_entry = prepared_config.get(snapshot_id)
        collect_dt = date_or_none((config_entry or {}).get("collect_date_iso"))
        if collect_dt is None:
            warnings.append(f"{snapshot_id}: collect_date missing; included without date filtering")
            selected.append(snapshot_id)
        elif from_dt <= collect_dt <= to_dt:
            selected.append(snapshot_id)
    return selected


def _warn_missing_config_snapshots(
    prepared_config: dict[str, dict[str, Any]],
    version_dirs: set[str],
    from_dt: date,
    to_dt: date,
    warnings: list[str],
) -> None:
    for snapshot_id, entry in prepared_config.items():
        if not VERSION_DIR_RE.match(snapshot_id) or snapshot_id in version_dirs:
            continue
        collect_dt = date_or_none(entry.get("collect_date_iso"))
        if collect_dt and from_dt <= collect_dt <= to_dt:
            warnings.append(
                f"{snapshot_id}: config is in requested date range but no dataset directory was listed"
            )


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
