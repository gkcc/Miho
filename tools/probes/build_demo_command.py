#!/usr/bin/env python
"""Write a replayable command record for the local demo pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.8-lite-demo-command"
DEFAULT_IMAGES_DIR = PROJECT_ROOT / "figs"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_EXPECTED_DIR = PROJECT_ROOT / "data" / "probes" / "expected"
DEFAULT_ROSTER_DIR = PROJECT_ROOT / "data" / "probes" / "roster"


class DemoCommandError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def shell_quote(value: str) -> str:
    if not value:
        return '""'
    if any(char.isspace() for char in value) or any(char in value for char in '"`$&|<>'):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def command_from_argv(argv: list[str]) -> str:
    return " ".join(shell_quote(part) for part in argv)


def add_arg(argv: list[str], flag: str, value: Path | str | int | float | None) -> None:
    if value is None:
        return
    argv.extend([flag, display_path(value) if isinstance(value, Path) else str(value)])


def add_flag(argv: list[str], flag: str, enabled: bool) -> None:
    if enabled:
        argv.append(flag)


def missing_input(flag: str, path: Path | None) -> str | None:
    if path is None:
        return None
    return flag if not path.exists() else None


def source_mode_key(*, images_dir: Path | None, parsed_dir: Path | None, manifest: Path | None) -> str:
    if manifest is not None:
        return "manifest"
    if parsed_dir is not None:
        return "parsed_dir"
    return "images_dir"


def source_path_for_mode(*, images_dir: Path | None, parsed_dir: Path | None, manifest: Path | None) -> tuple[str, Path | None]:
    if manifest is not None:
        return "--manifest", manifest
    if parsed_dir is not None:
        return "--parsed-dir", parsed_dir
    return "--images-dir", images_dir or DEFAULT_IMAGES_DIR


def build_demo_command(
    *,
    output_dir: Path,
    images_dir: Path | None = None,
    parsed_dir: Path | None = None,
    manifest: Path | None = None,
    expected_dir: Path = DEFAULT_EXPECTED_DIR,
    engine: str = "paddle",
    game: str = "zzz",
    layout: str | None = "zzz-agent-card",
    latest_only: bool = False,
    clean_demo: bool = False,
    new_only: bool = False,
    state_file: Path | None = None,
    targets: Path | None = None,
    target_source_manifest: Path | None = None,
    character_catalog: Path | None = None,
    roster_dir: Path | None = None,
    tier_snapshot: Path | None = None,
    tier_stale_days: int = 60,
    history_dir: Path | None = None,
    daily_stamina: float | None = None,
    horizon_days: float | None = None,
) -> dict[str, Any]:
    source_flag, source_path = source_path_for_mode(images_dir=images_dir, parsed_dir=parsed_dir, manifest=manifest)
    active_roster_dir = roster_dir or DEFAULT_ROSTER_DIR
    argv = ["python", "tools/probes/run_demo_pipeline.py"]
    add_arg(argv, source_flag, source_path)
    add_arg(argv, "--output-dir", output_dir)
    add_arg(argv, "--expected-dir", expected_dir)
    add_arg(argv, "--engine", engine)
    add_arg(argv, "--game", game)
    add_arg(argv, "--layout", layout)
    add_flag(argv, "--latest-only", latest_only)
    add_flag(argv, "--clean-demo", clean_demo)
    add_flag(argv, "--new-only", new_only)
    add_arg(argv, "--state-file", state_file)
    add_arg(argv, "--targets", targets)
    add_arg(argv, "--target-source-manifest", target_source_manifest)
    add_arg(argv, "--character-catalog", character_catalog)
    add_arg(argv, "--roster-dir", active_roster_dir)
    add_arg(argv, "--tier-snapshot", tier_snapshot)
    if tier_stale_days != 60:
        add_arg(argv, "--tier-stale-days", tier_stale_days)
    add_arg(argv, "--history-dir", history_dir)
    if daily_stamina is not None:
        add_arg(argv, "--daily-stamina", daily_stamina)
    if horizon_days is not None:
        add_arg(argv, "--horizon-days", horizon_days)

    path_checks = [
        missing_input(source_flag, source_path),
        missing_input("--expected-dir", expected_dir),
        missing_input("--state-file", state_file),
        missing_input("--targets", targets),
        missing_input("--target-source-manifest", target_source_manifest),
        missing_input("--character-catalog", character_catalog),
        missing_input("--roster-dir", active_roster_dir),
        missing_input("--tier-snapshot", tier_snapshot),
        missing_input("--history-dir", history_dir),
    ]
    missing_inputs = [item for item in path_checks if item]
    warnings: list[str] = []
    if images_dir is None and parsed_dir is None and manifest is None:
        warnings.append("source_defaults_to_images_dir")
    if missing_inputs:
        warnings.append("missing_replay_inputs")

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "source_mode": source_mode_key(images_dir=images_dir, parsed_dir=parsed_dir, manifest=manifest),
        "command": command_from_argv(argv),
        "argv": argv,
        "safe_to_rerun": not missing_inputs,
        "missing_inputs": missing_inputs,
        "warnings": warnings,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "demo_command.json"
    md_path = output_dir / "demo_command.md"
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Demo 回放命令",
        "",
        f"- source_mode: {result.get('source_mode')}",
        f"- safe_to_rerun: {result.get('safe_to_rerun')}",
        "",
        "## Command",
        "",
        f"```powershell\n{result.get('command')}\n```",
    ]
    missing = result.get("missing_inputs") if isinstance(result.get("missing_inputs"), list) else []
    if missing:
        lines.extend(["", "## Missing Inputs", ""])
        for item in missing:
            lines.append(f"- {item}")
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for item in warnings:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a replayable demo pipeline command record.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--images-dir", default=None)
    source.add_argument("--parsed-dir", default=None)
    source.add_argument("--manifest", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--expected-dir", default=str(DEFAULT_EXPECTED_DIR))
    parser.add_argument("--engine", default="paddle")
    parser.add_argument("--game", default="zzz")
    parser.add_argument("--layout", default="zzz-agent-card")
    parser.add_argument("--latest-only", action="store_true")
    parser.add_argument("--clean-demo", action="store_true")
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--targets", default=None)
    parser.add_argument("--target-source-manifest", default=None)
    parser.add_argument("--character-catalog", default=None)
    parser.add_argument("--roster-dir", default=str(DEFAULT_ROSTER_DIR))
    parser.add_argument("--tier-snapshot", default=None)
    parser.add_argument("--tier-stale-days", type=int, default=60)
    parser.add_argument("--history-dir", default=None)
    parser.add_argument("--daily-stamina", type=float, default=None)
    parser.add_argument("--horizon-days", type=float, default=None)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_demo_command(
            output_dir=resolve_path(args.output_dir),
            images_dir=resolve_path(args.images_dir) if args.images_dir else None,
            parsed_dir=resolve_path(args.parsed_dir) if args.parsed_dir else None,
            manifest=resolve_path(args.manifest) if args.manifest else None,
            expected_dir=resolve_path(args.expected_dir),
            engine=args.engine,
            game=args.game,
            layout=args.layout,
            latest_only=args.latest_only,
            clean_demo=args.clean_demo,
            new_only=args.new_only,
            state_file=resolve_path(args.state_file) if args.state_file else None,
            targets=resolve_path(args.targets) if args.targets else None,
            target_source_manifest=resolve_path(args.target_source_manifest) if args.target_source_manifest else None,
            character_catalog=resolve_path(args.character_catalog) if args.character_catalog else None,
            roster_dir=resolve_path(args.roster_dir) if args.roster_dir else None,
            tier_snapshot=resolve_path(args.tier_snapshot) if args.tier_snapshot else None,
            tier_stale_days=args.tier_stale_days,
            history_dir=resolve_path(args.history_dir) if args.history_dir else None,
            daily_stamina=args.daily_stamina,
            horizon_days=args.horizon_days,
        )
    except DemoCommandError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"source_mode: {result['source_mode']}")
    print(f"safe_to_rerun: {result['safe_to_rerun']}")
    print(f"command: {result['command']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
