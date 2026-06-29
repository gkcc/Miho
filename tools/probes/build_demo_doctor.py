#!/usr/bin/env python
"""Build a read-only top-level diagnosis for the demo dashboard."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.9-lite-demo-doctor"


class DemoDoctorError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DemoDoctorError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoDoctorError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise DemoDoctorError(f"Expected JSON object: {path}")
    return data


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return load_json(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_strings(items: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def has_ready_try_now(action_checklist: dict[str, Any] | None) -> bool:
    if not isinstance(action_checklist, dict):
        return False
    for item in as_list(action_checklist.get("items")):
        if isinstance(item, dict) and item.get("item_type") == "try_now" and item.get("status") == "ready":
            return True
    return False


def has_review_snapshot(action_checklist: dict[str, Any] | None) -> bool:
    if not isinstance(action_checklist, dict):
        return False
    return any(isinstance(item, dict) and item.get("item_type") == "review_snapshot" for item in as_list(action_checklist.get("items")))


def has_watch_only(action_checklist: dict[str, Any] | None, final_brief: dict[str, Any] | None) -> bool:
    checklist_items = as_list(action_checklist.get("items")) if isinstance(action_checklist, dict) else []
    brief_cards = as_list(final_brief.get("top_cards")) if isinstance(final_brief, dict) else []
    return any(isinstance(item, dict) and item.get("item_type") == "watch_only" for item in checklist_items) or any(
        isinstance(item, dict) and item.get("card_type") == "watch_only" for item in brief_cards
    )


def pending_review_count(review_inbox: dict[str, Any] | None) -> int:
    if not isinstance(review_inbox, dict):
        return 0
    return int_value(review_inbox.get("pending_count"))


def apply_status(review_apply_receipt: dict[str, Any] | None) -> str:
    if not isinstance(review_apply_receipt, dict):
        return "not_applied"
    if review_apply_receipt.get("apply_status"):
        return str(review_apply_receipt.get("apply_status"))
    if review_apply_receipt.get("schema_version"):
        return "applied"
    return "not_applied"


def preview_accept_count(review_preview: dict[str, Any] | None) -> int:
    summary = review_preview.get("summary") if isinstance(review_preview, dict) and isinstance(review_preview.get("summary"), dict) else {}
    return int_value(summary.get("accept_count"))


def preview_would_update_count(review_preview: dict[str, Any] | None) -> int:
    summary = review_preview.get("summary") if isinstance(review_preview, dict) and isinstance(review_preview.get("summary"), dict) else {}
    return int_value(summary.get("would_update_roster_count"))


def command_state(refresh_status: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(refresh_status, dict):
        return {}
    state = refresh_status.get("command_state")
    return state if isinstance(state, dict) else {}


def refresh_command(refresh_status: dict[str, Any] | None, demo_command: dict[str, Any] | None) -> str | None:
    if isinstance(refresh_status, dict) and refresh_status.get("refresh_command"):
        return str(refresh_status["refresh_command"])
    if isinstance(demo_command, dict) and demo_command.get("command"):
        return str(demo_command["command"])
    return None


def diagnose(
    *,
    refresh_status: dict[str, Any] | None,
    final_brief: dict[str, Any] | None,
    action_checklist: dict[str, Any] | None,
    review_inbox: dict[str, Any] | None,
    review_preview: dict[str, Any] | None,
    review_apply_receipt: dict[str, Any] | None,
    run_manifest: dict[str, Any] | None,
    demo_command: dict[str, Any] | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    blocking_reasons: list[str] = []
    refresh = str(refresh_status.get("refresh_status") if isinstance(refresh_status, dict) else "missing")
    preview_status = str(review_preview.get("preview_status") if isinstance(review_preview, dict) else "missing")
    checklist_status = str(action_checklist.get("checklist_status") if isinstance(action_checklist, dict) else "missing")
    brief_status = str(final_brief.get("brief_status") if isinstance(final_brief, dict) else "missing")
    apply = apply_status(review_apply_receipt)
    run_missing = not isinstance(run_manifest, dict)
    command = command_state(refresh_status)
    command_safe = command.get("safe_to_rerun")

    if run_missing:
        blocking_reasons.append("missing_run_manifest")
    if not isinstance(refresh_status, dict):
        blocking_reasons.append("missing_refresh_status")
    if command_safe is False:
        warnings.append("demo_command_not_safe_to_rerun")
    if has_watch_only(action_checklist, final_brief):
        warnings.append("watch_only_not_try_now")

    if refresh in {"stale_after_apply", "unknown"} or "missing_refresh_status" in blocking_reasons:
        doctor_status = "needs_rerun"
        primary_next_action = "rerun_demo_pipeline"
        headline = "先重跑 demo pipeline，刷新本轮建议"
    elif run_missing:
        doctor_status = "blocked"
        primary_next_action = "rebuild_run_manifest"
        headline = "缺少 run_manifest，无法诊断本轮产物"
    elif preview_status in {"ready", "ready_with_override"} and (preview_accept_count(review_preview) > 0 or preview_would_update_count(review_preview) > 0) and apply not in {"applied", "applied_with_warnings"}:
        doctor_status = "needs_apply"
        primary_next_action = "safe_apply_review_decisions"
        headline = "已有 ready preview，下一步是人工 safe apply"
    elif pending_review_count(review_inbox) > 0 or has_review_snapshot(action_checklist):
        doctor_status = "needs_review"
        primary_next_action = "review_snapshots"
        headline = "先人工复核 pending 快照"
    elif refresh in {"fresh", "not_applied"} and has_ready_try_now(action_checklist):
        doctor_status = "ready_to_try"
        primary_next_action = "try_now"
        headline = "当前有可信 try_now，可按清单先试一次"
    elif checklist_status == "blocked":
        doctor_status = "blocked"
        primary_next_action = "resolve_blockers"
        headline = "执行清单仍有阻断项"
    else:
        doctor_status = "needs_review"
        primary_next_action = "review_dashboard"
        headline = "需要继续查看 Dashboard 明细"

    try_now_allowed = doctor_status == "ready_to_try"
    rerun_required = doctor_status == "needs_rerun"
    safe_apply_required = doctor_status == "needs_apply"
    review_required = doctor_status == "needs_review"
    if not try_now_allowed and has_ready_try_now(action_checklist):
        blocking_reasons.append("ready_try_now_not_actionable_under_current_doctor_status")

    return {
        "doctor_status": doctor_status,
        "headline": headline,
        "try_now_allowed": try_now_allowed,
        "rerun_required": rerun_required,
        "review_required": review_required,
        "safe_apply_required": safe_apply_required,
        "primary_next_action": primary_next_action,
        "summary": {
            "refresh_status": refresh,
            "brief_status": brief_status,
            "checklist_status": checklist_status,
            "preview_status": preview_status,
            "apply_status": apply,
            "pending_review_count": pending_review_count(review_inbox),
            "ready_try_now_count": 1 if has_ready_try_now(action_checklist) else 0,
            "preview_accept_count": preview_accept_count(review_preview),
            "preview_would_update_roster_count": preview_would_update_count(review_preview),
            "run_manifest_exists": isinstance(run_manifest, dict),
            "demo_command_safe_to_rerun": command_safe,
        },
        "commands": {
            "rerun_demo": refresh_command(refresh_status, demo_command),
            "preview": action_checklist.get("preview_command") if isinstance(action_checklist, dict) else None,
            "safe_apply": action_checklist.get("safe_apply_command") if isinstance(action_checklist, dict) else None,
        },
        "blocking_reasons": unique_strings(blocking_reasons),
        "warnings": unique_strings(warnings),
    }


def build_demo_doctor(
    *,
    output_dir: Path,
    refresh_status: Path | None = None,
    final_brief: Path | None = None,
    action_checklist: Path | None = None,
    review_inbox: Path | None = None,
    review_preview: Path | None = None,
    review_apply_receipt: Path | None = None,
    run_manifest: Path | None = None,
    demo_command: Path | None = None,
) -> dict[str, Any]:
    refresh_data = load_optional_json(refresh_status)
    final_data = load_optional_json(final_brief)
    checklist_data = load_optional_json(action_checklist)
    inbox_data = load_optional_json(review_inbox)
    preview_data = load_optional_json(review_preview)
    apply_data = load_optional_json(review_apply_receipt)
    run_data = load_optional_json(run_manifest)
    command_data = load_optional_json(demo_command)
    diagnosis = diagnose(
        refresh_status=refresh_data,
        final_brief=final_data,
        action_checklist=checklist_data,
        review_inbox=inbox_data,
        review_preview=preview_data,
        review_apply_receipt=apply_data,
        run_manifest=run_data,
        demo_command=command_data,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "demo_doctor.json"
    md_path = output_dir / "demo_doctor.md"
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "refresh_status": str(refresh_status) if refresh_status else None,
            "final_brief": str(final_brief) if final_brief else None,
            "action_checklist": str(action_checklist) if action_checklist else None,
            "review_inbox": str(review_inbox) if review_inbox else None,
            "review_preview": str(review_preview) if review_preview else None,
            "review_apply_receipt": str(review_apply_receipt) if review_apply_receipt else None,
            "run_manifest": str(run_manifest) if run_manifest else None,
            "demo_command": str(demo_command) if demo_command else None,
        },
        **diagnosis,
    }
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    lines = [
        "# Demo 当前状态诊断",
        "",
        f"- doctor_status: {result.get('doctor_status')}",
        f"- headline: {result.get('headline')}",
        f"- primary_next_action: {result.get('primary_next_action')}",
        f"- try_now_allowed: {result.get('try_now_allowed')}",
        f"- rerun_required: {result.get('rerun_required')}",
        f"- safe_apply_required: {result.get('safe_apply_required')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    commands = result.get("commands") if isinstance(result.get("commands"), dict) else {}
    lines.extend(["", "## Commands", ""])
    for key in ("rerun_demo", "preview", "safe_apply"):
        value = commands.get(key)
        lines.append(f"- {key}: `{value}`" if value else f"- {key}: N/A")
    blockers = as_list(result.get("blocking_reasons"))
    if blockers:
        lines.extend(["", "## Blocking Reasons", ""])
        for item in blockers:
            lines.append(f"- {item}")
    warnings = as_list(result.get("warnings"))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for item in warnings:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a read-only demo status diagnosis.")
    parser.add_argument("--refresh-status", default=None)
    parser.add_argument("--final-brief", default=None)
    parser.add_argument("--action-checklist", default=None)
    parser.add_argument("--review-inbox", default=None)
    parser.add_argument("--review-preview", default=None)
    parser.add_argument("--review-apply-receipt", default=None)
    parser.add_argument("--run-manifest", default=None)
    parser.add_argument("--demo-command", default=None)
    parser.add_argument("--output-dir", required=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_demo_doctor(
            output_dir=resolve_path(args.output_dir),
            refresh_status=resolve_path(args.refresh_status) if args.refresh_status else None,
            final_brief=resolve_path(args.final_brief) if args.final_brief else None,
            action_checklist=resolve_path(args.action_checklist) if args.action_checklist else None,
            review_inbox=resolve_path(args.review_inbox) if args.review_inbox else None,
            review_preview=resolve_path(args.review_preview) if args.review_preview else None,
            review_apply_receipt=resolve_path(args.review_apply_receipt) if args.review_apply_receipt else None,
            run_manifest=resolve_path(args.run_manifest) if args.run_manifest else None,
            demo_command=resolve_path(args.demo_command) if args.demo_command else None,
        )
    except DemoDoctorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"doctor_status: {result['doctor_status']}")
    print(f"primary_next_action: {result['primary_next_action']}")
    print(f"try_now_allowed: {result['try_now_allowed']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
