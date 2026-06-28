#!/usr/bin/env python
"""Build a run-level artifact manifest for local demo reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.0-lite-run-manifest"


class RunManifestError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_timestamp() -> str:
    return now_iso().replace(":", "").replace("+", "_").replace("-", "").replace("T", "_")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RunManifestError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RunManifestError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise RunManifestError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_entry(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists() or not path.is_file():
        return {"path": str(path), "sha256": None, "exists": False}
    return {"path": str(path), "sha256": sha256_file(path), "exists": True}


def artifact_inputs(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = load_json(path)
    except RunManifestError:
        return {}
    return data.get("input") if isinstance(data.get("input"), dict) else {}


def same_path(left: Any, right: Path | None) -> bool:
    if not left or right is None:
        return True
    try:
        return resolve_path(str(left)) == right.resolve()
    except OSError:
        return False


def add_path_check(
    *,
    stale_or_mismatched: list[str],
    warnings: list[str],
    artifact_name: str,
    input_name: str,
    declared_path: Any,
    expected_path: Path | None,
) -> None:
    if expected_path is None or declared_path in (None, ""):
        return
    if same_path(declared_path, expected_path):
        return
    stale_or_mismatched.append(f"{artifact_name}.{input_name}")
    warnings.append(
        f"{artifact_name} 声明的 {input_name}={declared_path}，与本轮输入 {expected_path} 不一致；该产物可能不是同一批生成。"
    )


def artifact_status(
    *,
    inputs: dict[str, dict[str, Any] | None],
    roster_index: Path | None,
    targets: Path | None,
    team_cards: Path | None,
    action_cards: Path | None,
    tier_watchlist: Path | None,
    roster_delta: Path | None,
) -> dict[str, Any]:
    missing = [name for name, item in inputs.items() if item is None or item.get("exists") is False]
    stale_or_mismatched: list[str] = []
    warnings: list[str] = []
    if missing:
        warnings.append(f"缺少输入产物：{', '.join(missing)}。相关报告会降级展示。")

    action_input = artifact_inputs(action_cards)
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="action_cards",
        input_name="roster_index",
        declared_path=action_input.get("roster_index"),
        expected_path=roster_index,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="action_cards",
        input_name="targets",
        declared_path=action_input.get("targets"),
        expected_path=targets,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="action_cards",
        input_name="tier_watchlist",
        declared_path=action_input.get("tier_watchlist"),
        expected_path=tier_watchlist,
    )

    team_input = artifact_inputs(team_cards)
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="team_cards",
        input_name="action_cards",
        declared_path=team_input.get("action_cards"),
        expected_path=action_cards,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="team_cards",
        input_name="roster_index",
        declared_path=team_input.get("roster_index"),
        expected_path=roster_index,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="team_cards",
        input_name="tier_watchlist",
        declared_path=team_input.get("tier_watchlist"),
        expected_path=tier_watchlist,
    )

    delta_input = artifact_inputs(roster_delta)
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="roster_delta",
        input_name="new_roster_index",
        declared_path=delta_input.get("new_roster_index"),
        expected_path=roster_index,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="roster_delta",
        input_name="action_cards",
        declared_path=delta_input.get("action_cards"),
        expected_path=action_cards,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="roster_delta",
        input_name="team_cards",
        declared_path=delta_input.get("team_cards"),
        expected_path=team_cards,
    )
    add_path_check(
        stale_or_mismatched=stale_or_mismatched,
        warnings=warnings,
        artifact_name="roster_delta",
        input_name="tier_watchlist",
        declared_path=delta_input.get("tier_watchlist"),
        expected_path=tier_watchlist,
    )
    return {
        "consistent": not missing and not stale_or_mismatched,
        "missing": missing,
        "stale_or_mismatched": stale_or_mismatched,
        "warnings": warnings,
    }


def build_run_manifest(
    *,
    output_dir: Path,
    roster_index: Path | None = None,
    targets: Path | None = None,
    team_cards: Path | None = None,
    action_cards: Path | None = None,
    tier_watchlist: Path | None = None,
    roster_delta: Path | None = None,
) -> dict[str, Any]:
    inputs = {
        "roster_index": artifact_entry(roster_index),
        "targets": artifact_entry(targets),
        "team_cards": artifact_entry(team_cards),
        "action_cards": artifact_entry(action_cards),
        "tier_watchlist": artifact_entry(tier_watchlist),
        "roster_delta": artifact_entry(roster_delta),
    }
    status = artifact_status(
        inputs=inputs,
        roster_index=roster_index,
        targets=targets,
        team_cards=team_cards,
        action_cards=action_cards,
        tier_watchlist=tier_watchlist,
        roster_delta=roster_delta,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"demo_{safe_timestamp()}",
        "created_at": now_iso(),
        "inputs": inputs,
        "artifact_status": status,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "run_manifest.json"
    result["output_json"] = str(json_path)
    write_json(json_path, result)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build local demo run manifest.")
    parser.add_argument("--roster-index", default=None, help="Current roster_index.json.")
    parser.add_argument("--targets", default=None, help="Current endgame_targets.json.")
    parser.add_argument("--team-cards", default=None, help="Current team_cards.json.")
    parser.add_argument("--action-cards", default=None, help="Current action_cards.json.")
    parser.add_argument("--tier-watchlist", default=None, help="Current tier_watchlist.json.")
    parser.add_argument("--roster-delta", default=None, help="Current roster_delta.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for run_manifest.json.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_run_manifest(
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            targets=resolve_path(args.targets) if args.targets else None,
            team_cards=resolve_path(args.team_cards) if args.team_cards else None,
            action_cards=resolve_path(args.action_cards) if args.action_cards else None,
            tier_watchlist=resolve_path(args.tier_watchlist) if args.tier_watchlist else None,
            roster_delta=resolve_path(args.roster_delta) if args.roster_delta else None,
            output_dir=resolve_path(args.output_dir),
        )
    except RunManifestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    status = result["artifact_status"]
    print(f"consistent: {status['consistent']}")
    print(f"missing_count: {len(status['missing'])}")
    print(f"stale_or_mismatched_count: {len(status['stale_or_mismatched'])}")
    print(f"output_json: {result['output_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
