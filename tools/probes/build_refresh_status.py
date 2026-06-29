#!/usr/bin/env python
"""Detect whether demo recommendations are stale after review apply."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.7-lite-refresh-status"
FALLBACK_REFRESH_COMMAND = "python tools/probes/run_demo_pipeline.py --clean-demo"


class RefreshStatusError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RefreshStatusError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RefreshStatusError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise RefreshStatusError(f"Expected JSON object: {path}")
    return data


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return load_json(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_strings(items: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed


def receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {}
    summary = receipt.get("summary")
    return summary if isinstance(summary, dict) else {}


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def receipt_changes_roster(summary: dict[str, Any]) -> bool:
    return int_value(summary.get("did_enter_roster_count")) > 0 or int_value(summary.get("did_write_accepted_count")) > 0


def run_roster_hash(run_manifest: dict[str, Any] | None) -> str | None:
    if not isinstance(run_manifest, dict):
        return None
    inputs = run_manifest.get("inputs")
    if not isinstance(inputs, dict):
        return None
    roster = inputs.get("roster_index")
    if not isinstance(roster, dict):
        return None
    value = roster.get("sha256")
    return str(value) if value else None


def affected_artifacts() -> list[str]:
    return ["final_brief", "action_checklist", "endgame_plan", "team_cards", "roster_delta"]


def command_details(demo_command: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(demo_command, dict):
        return {
            "command": FALLBACK_REFRESH_COMMAND,
            "argv": [],
            "safe_to_rerun": False,
            "missing_inputs": ["demo_command"],
            "warnings": ["command_not_replayable"],
        }
    command = str(demo_command.get("command") or "").strip()
    if not command:
        return {
            "command": FALLBACK_REFRESH_COMMAND,
            "argv": [],
            "safe_to_rerun": False,
            "missing_inputs": ["demo_command.command"],
            "warnings": unique_strings(["command_not_replayable"] + as_list(demo_command.get("warnings"))),
        }
    argv = as_list(demo_command.get("argv"))
    missing = [str(item) for item in as_list(demo_command.get("missing_inputs")) if item]
    return {
        "command": command,
        "argv": [str(item) for item in argv],
        "safe_to_rerun": bool(demo_command.get("safe_to_rerun")) and not missing,
        "missing_inputs": missing,
        "warnings": unique_strings(as_list(demo_command.get("warnings"))),
        "source_mode": demo_command.get("source_mode"),
        "output_json": demo_command.get("output_json"),
        "output_md": demo_command.get("output_md"),
    }


def action_state(status: str) -> dict[str, Any]:
    rerun_required = status in {"stale_after_apply", "unknown"}
    return {
        "try_now_allowed": not rerun_required,
        "review_allowed": True,
        "safe_apply_allowed": True,
        "rerun_required": rerun_required,
        "primary_next_action": "rerun_demo_pipeline" if rerun_required else "continue_review_flow",
    }


def build_refresh_status(
    *,
    output_dir: Path,
    review_apply_receipt: Path | None = None,
    run_manifest: Path | None = None,
    roster_index: Path | None = None,
    demo_command: Path | None = None,
    final_brief: Path | None = None,
    action_checklist: Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    stale_reasons: list[str] = []
    receipt_data = load_optional_json(review_apply_receipt)
    run_data = load_optional_json(run_manifest)
    demo_command_data = load_optional_json(demo_command)
    command_info = command_details(demo_command_data)
    warnings.extend(as_list(command_info.get("warnings")))
    receipt_exists = isinstance(receipt_data, dict)
    run_exists = isinstance(run_data, dict)
    summary = receipt_summary(receipt_data)
    current_roster_hash = sha256_file(roster_index)
    manifest_roster_hash = run_roster_hash(run_data)
    receipt_time = parse_iso(receipt_data.get("created_at")) if isinstance(receipt_data, dict) else None
    run_time = parse_iso(run_data.get("created_at")) if isinstance(run_data, dict) else None

    if not receipt_exists:
        status = "not_applied"
    else:
        status = "fresh"
        if receipt_time is None:
            warnings.append("review_apply_receipt 缺少可解析 created_at，无法用时间判断是否 stale。")
        if run_time is None:
            status = "unknown"
            warnings.append("run_manifest 缺少可解析 created_at，无法确认 demo 是否吸收了 apply。")
        if receipt_changes_roster(summary) and receipt_time and run_time and receipt_time > run_time:
            status = "stale_after_apply"
            stale_reasons.append("review_apply_receipt.created_at is newer than run_manifest.created_at")
        if manifest_roster_hash and current_roster_hash and manifest_roster_hash != current_roster_hash:
            status = "stale_after_apply"
            stale_reasons.append("roster_index sha256 differs from run_manifest inputs.roster_index.sha256")
        if not receipt_changes_roster(summary) and int_value(summary.get("did_write_rejected_count")) > 0:
            warnings.append("receipt 只记录 rejected/pending 副作用，未改变 accepted roster；本轮不强制阻断 try_now。")

    needs_refresh = status in {"stale_after_apply", "unknown"}
    current_action_state = action_state(status)
    result = {
        "schema_version": SCHEMA_VERSION,
        "refresh_status": status,
        "summary": {
            "receipt_exists": receipt_exists,
            "apply_status": "applied" if receipt_exists else "not_applied",
            "did_enter_roster_count": int_value(summary.get("did_enter_roster_count")),
            "did_write_accepted_count": int_value(summary.get("did_write_accepted_count")),
            "did_write_rejected_count": int_value(summary.get("did_write_rejected_count")),
            "preview_validated_count": int_value(summary.get("preview_validated_count")),
            "needs_demo_refresh": needs_refresh,
            "run_manifest_exists": run_exists,
            "current_roster_sha256": current_roster_hash,
            "run_manifest_roster_sha256": manifest_roster_hash,
            "demo_command_exists": isinstance(demo_command_data, dict),
            "demo_command_safe_to_rerun": command_info.get("safe_to_rerun"),
        },
        "stale_reasons": unique_strings(stale_reasons),
        "affected_artifacts": affected_artifacts() if needs_refresh else [],
        "refresh_command": command_info["command"],
        "refresh_argv": command_info.get("argv", []),
        "command_state": {
            "safe_to_rerun": command_info.get("safe_to_rerun"),
            "missing_inputs": command_info.get("missing_inputs", []),
            "source_mode": command_info.get("source_mode"),
            "demo_command_json": command_info.get("output_json"),
            "demo_command_md": command_info.get("output_md"),
        },
        "action_state": current_action_state,
        "warnings": unique_strings(warnings),
        "input": {
            "review_apply_receipt": str(review_apply_receipt) if review_apply_receipt else None,
            "run_manifest": str(run_manifest) if run_manifest else None,
            "roster_index": str(roster_index) if roster_index else None,
            "demo_command": str(demo_command) if demo_command else None,
            "final_brief": str(final_brief) if final_brief else None,
            "action_checklist": str(action_checklist) if action_checklist else None,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "refresh_status.json"
    md_path = output_dir / "refresh_status.md"
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Demo 刷新状态",
        "",
        f"- refresh_status: {result.get('refresh_status')}",
        f"- needs_demo_refresh: {result.get('summary', {}).get('needs_demo_refresh')}",
        f"- try_now_allowed: {result.get('action_state', {}).get('try_now_allowed')}",
        f"- primary_next_action: {result.get('action_state', {}).get('primary_next_action')}",
        "",
        "## Stale Reasons",
        "",
    ]
    reasons = as_list(result.get("stale_reasons"))
    if not reasons:
        lines.append("- 无")
    else:
        for item in reasons:
            lines.append(f"- {item}")
    warnings = as_list(result.get("warnings"))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for item in warnings:
            lines.append(f"- {item}")
    command_state = result.get("command_state") if isinstance(result.get("command_state"), dict) else {}
    missing_inputs = as_list(command_state.get("missing_inputs"))
    if missing_inputs:
        lines.extend(["", "## Missing Replay Inputs", ""])
        for item in missing_inputs:
            lines.append(f"- {item}")
    lines.extend(["", "## Refresh Command", "", f"- `{result.get('refresh_command')}`"])
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build demo refresh/freshness status after review apply.")
    parser.add_argument("--review-apply-receipt", default=None, help="review_apply_receipt.json.")
    parser.add_argument("--run-manifest", default=None, help="run_manifest.json.")
    parser.add_argument("--roster-index", default=None, help="Current roster_index.json.")
    parser.add_argument("--demo-command", default=None, help="demo_command.json generated by run_demo_pipeline.")
    parser.add_argument("--final-brief", default=None, help="final_brief.json.")
    parser.add_argument("--action-checklist", default=None, help="action_checklist.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for refresh_status.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_refresh_status(
            review_apply_receipt=resolve_path(args.review_apply_receipt) if args.review_apply_receipt else None,
            run_manifest=resolve_path(args.run_manifest) if args.run_manifest else None,
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            demo_command=resolve_path(args.demo_command) if args.demo_command else None,
            final_brief=resolve_path(args.final_brief) if args.final_brief else None,
            action_checklist=resolve_path(args.action_checklist) if args.action_checklist else None,
            output_dir=resolve_path(args.output_dir),
        )
    except RefreshStatusError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"refresh_status: {result['refresh_status']}")
    print(f"needs_demo_refresh: {result['summary']['needs_demo_refresh']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
