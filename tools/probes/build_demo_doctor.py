#!/usr/bin/env python
"""Build a read-only top-level diagnosis for the demo dashboard."""

from __future__ import annotations

import argparse
import hashlib
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


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def ready_try_now_count(action_checklist: dict[str, Any] | None) -> int:
    if not isinstance(action_checklist, dict):
        return 0
    return sum(
        1
        for item in as_list(action_checklist.get("items"))
        if isinstance(item, dict) and item.get("item_type") == "try_now" and item.get("status") == "ready"
    )


def has_ready_try_now(action_checklist: dict[str, Any] | None) -> bool:
    return ready_try_now_count(action_checklist) > 0


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


def preview_blocked_accept_count(review_preview: dict[str, Any] | None) -> int:
    summary = review_preview.get("summary") if isinstance(review_preview, dict) and isinstance(review_preview.get("summary"), dict) else {}
    return int_value(summary.get("blocked_accept_count"))


def preview_override_accept_count(review_preview: dict[str, Any] | None) -> int:
    summary = review_preview.get("summary") if isinstance(review_preview, dict) and isinstance(review_preview.get("summary"), dict) else {}
    return int_value(summary.get("override_accept_count"))


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


def input_info(data: dict[str, Any] | None) -> dict[str, Any]:
    raw = data.get("input") if isinstance(data, dict) else {}
    return raw if isinstance(raw, dict) else {}


def apply_receipt_summary(review_apply_receipt: dict[str, Any] | None) -> dict[str, Any]:
    summary = review_apply_receipt.get("summary") if isinstance(review_apply_receipt, dict) else {}
    return summary if isinstance(summary, dict) else {}


def accepted_missing_roster_index(review_apply_receipt: dict[str, Any] | None) -> bool:
    if not isinstance(review_apply_receipt, dict):
        return False
    summary = apply_receipt_summary(review_apply_receipt)
    accepted = int_value(summary.get("did_write_accepted_count"))
    entered = int_value(summary.get("did_enter_roster_count"))
    if accepted > 0 and entered < accepted:
        return True
    warnings = as_list(review_apply_receipt.get("warnings"))
    return any("did not enter roster_index" in str(item) for item in warnings)


def build_evidence_check(
    *,
    refresh_status: dict[str, Any] | None,
    review_preview: dict[str, Any] | None,
    review_apply_receipt: dict[str, Any] | None,
    run_manifest: dict[str, Any] | None,
    demo_command: dict[str, Any] | None,
    hashes: dict[str, str | None],
) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    strict_status = "trusted"
    matched_preview_apply: bool | None = None
    matched_refresh_command: bool | None = None
    matched_run_manifest: bool | None = None

    preview_input = input_info(review_preview)
    receipt_input = input_info(review_apply_receipt)
    current_preview_hash = hashes.get("review_preview")
    current_run_hash = hashes.get("run_manifest")

    receipt_has_unindexed_accept = accepted_missing_roster_index(review_apply_receipt)
    preview_ready = isinstance(review_preview, dict) and str(review_preview.get("preview_status") or "") in {"ready", "ready_with_override"}
    preview_has_apply_work = preview_accept_count(review_preview) > 0 or preview_would_update_count(review_preview) > 0
    if preview_ready and preview_has_apply_work:
        if not isinstance(review_apply_receipt, dict):
            matched_preview_apply = False
            strict_status = "needs_apply"
            warnings.append("apply_receipt_missing_for_ready_preview")
        else:
            matched_preview_apply = True
            expected_preview_hash = receipt_input.get("preview_result_sha256")
            if not expected_preview_hash:
                matched_preview_apply = False
                strict_status = "needs_apply"
                warnings.append("apply_receipt_preview_result_sha256_missing")
            elif not current_preview_hash:
                matched_preview_apply = False
                strict_status = "needs_apply"
                warnings.append("current_review_preview_sha256_missing")
            elif str(expected_preview_hash) != str(current_preview_hash):
                matched_preview_apply = False
                strict_status = "needs_apply"
                warnings.append("apply_receipt_preview_result_sha256_mismatch")
            expected_decision_hash = receipt_input.get("decision_manifest_sha256")
            current_decision_hash = preview_input.get("decision_manifest_sha256")
            if not expected_decision_hash:
                matched_preview_apply = False
                strict_status = "blocked"
                blockers.append("apply_receipt_decision_manifest_sha256_missing")
            elif not current_decision_hash:
                matched_preview_apply = False
                strict_status = "blocked"
                blockers.append("review_preview_decision_manifest_sha256_missing")
            elif str(expected_decision_hash) != str(current_decision_hash):
                matched_preview_apply = False
                strict_status = "blocked"
                blockers.append("apply_receipt_decision_manifest_sha256_mismatch")
    if receipt_has_unindexed_accept:
        matched_preview_apply = False
        strict_status = "blocked"
        blockers.append("apply_receipt_accepted_not_in_roster_index")

    if isinstance(review_preview, dict) and isinstance(run_manifest, dict):
        expected_run_hash = preview_input.get("run_manifest_sha256")
        if expected_run_hash and current_run_hash:
            matched_run_manifest = str(expected_run_hash) == str(current_run_hash)
            if not matched_run_manifest:
                strict_status = "blocked"
                blockers.append("review_preview_run_manifest_sha256_mismatch")

    if isinstance(refresh_status, dict) and isinstance(demo_command, dict):
        refresh_cmd = refresh_status.get("refresh_command")
        command = demo_command.get("command")
        if refresh_cmd and command:
            matched_refresh_command = str(refresh_cmd) == str(command)
            if not matched_refresh_command:
                strict_status = "blocked"
                blockers.append("refresh_command_mismatch")

    status = "trusted"
    if blockers:
        status = "blocked"
        strict_status = "blocked"
    elif warnings:
        status = "warning"
    return {
        "status": status,
        "strict_status": strict_status,
        "matched_preview_apply": matched_preview_apply,
        "matched_refresh_command": matched_refresh_command,
        "matched_run_manifest": matched_run_manifest,
        "artifact_hashes": {key: value for key, value in hashes.items() if value},
        "warnings": unique_strings(warnings),
        "blockers": unique_strings(blockers),
    }


def build_action_contract(
    *,
    primary_next_action: str,
    command_safe: bool | None,
) -> dict[str, Any]:
    base = {
        "primary_next_action": primary_next_action,
        "is_read_only": True,
        "writes_roster": False,
        "requires_manual_confirmation": False,
        "allowed_for_launcher": False,
        "reason": "no launcher action is available for this state",
    }
    if primary_next_action == "safe_apply_review_decisions":
        return {
            **base,
            "is_read_only": False,
            "writes_roster": True,
            "requires_manual_confirmation": True,
            "allowed_for_launcher": False,
            "reason": "write action must be manually confirmed and is never auto-launched",
        }
    if primary_next_action == "rerun_demo_pipeline":
        allowed = command_safe is True
        return {
            **base,
            "is_read_only": False,
            "writes_roster": False,
            "requires_manual_confirmation": False,
            "allowed_for_launcher": allowed,
            "reason": "demo rerun command is safe to print" if allowed else "demo rerun command is not safe to replay",
        }
    if primary_next_action == "try_now":
        return {
            **base,
            "is_read_only": True,
            "writes_roster": False,
            "requires_manual_confirmation": False,
            "allowed_for_launcher": False,
            "reason": "try_now is a user gameplay action, not a tool command",
        }
    if primary_next_action in {"review_snapshots", "review_dashboard"}:
        return {
            **base,
            "requires_manual_confirmation": True,
            "reason": "manual review is required before any command can be launched",
        }
    if primary_next_action == "repair_demo_command":
        return {
            **base,
            "requires_manual_confirmation": True,
            "reason": "demo command must be repaired before rerun can be launched",
        }
    if primary_next_action == "repair_evidence_mismatch":
        return {
            **base,
            "requires_manual_confirmation": True,
            "reason": "evidence mismatch must be repaired before launcher can trust the state",
        }
    return base


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
    evidence_check: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    blocking_reasons: list[str] = []
    refresh = str(refresh_status.get("refresh_status") if isinstance(refresh_status, dict) else "missing")
    preview_status = str(review_preview.get("preview_status") if isinstance(review_preview, dict) else "missing")
    checklist_status = str(action_checklist.get("checklist_status") if isinstance(action_checklist, dict) else "missing")
    brief_status = str(final_brief.get("brief_status") if isinstance(final_brief, dict) else "missing")
    apply = apply_status(review_apply_receipt)
    if evidence_check.get("matched_preview_apply") is False or evidence_check.get("strict_status") == "needs_apply":
        apply = "not_applied"
    run_missing = not isinstance(run_manifest, dict)
    command = command_state(refresh_status)
    command_safe = command.get("safe_to_rerun")

    if run_missing:
        blocking_reasons.append("missing_run_manifest")
    if not isinstance(refresh_status, dict):
        blocking_reasons.append("missing_refresh_status")
    for item in as_list(evidence_check.get("blockers")):
        blocking_reasons.append(str(item))
    for item in as_list(evidence_check.get("warnings")):
        warnings.append(str(item))
    if command_safe is False:
        warnings.append("demo_command_not_safe_to_rerun")
    if has_watch_only(action_checklist, final_brief):
        warnings.append("watch_only_not_try_now")

    if evidence_check.get("strict_status") == "blocked" or evidence_check.get("status") == "blocked":
        doctor_status = "blocked"
        primary_next_action = "repair_evidence_mismatch"
        headline = "诊断证据不一致，先修复错批产物"
    elif (refresh in {"stale_after_apply", "unknown"} or "missing_refresh_status" in blocking_reasons) and command_safe is False:
        doctor_status = "blocked"
        primary_next_action = "repair_demo_command"
        headline = "需要重跑，但 demo 命令不可回放"
    elif refresh in {"stale_after_apply", "unknown"} or "missing_refresh_status" in blocking_reasons:
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

    action_contract = build_action_contract(primary_next_action=primary_next_action, command_safe=command_safe)
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
            "ready_try_now_count": ready_try_now_count(action_checklist),
            "preview_accept_count": preview_accept_count(review_preview),
            "preview_blocked_accept_count": preview_blocked_accept_count(review_preview),
            "preview_override_accept_count": preview_override_accept_count(review_preview),
            "preview_would_update_roster_count": preview_would_update_count(review_preview),
            "run_manifest_exists": isinstance(run_manifest, dict),
            "demo_command_safe_to_rerun": command_safe,
        },
        "commands": {
            "rerun_demo": refresh_command(refresh_status, demo_command),
            "preview": action_checklist.get("preview_command") if isinstance(action_checklist, dict) else None,
            "safe_apply": action_checklist.get("safe_apply_command") if isinstance(action_checklist, dict) else None,
        },
        "evidence_check": evidence_check,
        "action_contract": action_contract,
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
        evidence_check=build_evidence_check(
            refresh_status=refresh_data,
            review_preview=preview_data,
            review_apply_receipt=apply_data,
            run_manifest=run_data,
            demo_command=command_data,
            hashes={
                "refresh_status": sha256_file(refresh_status),
                "final_brief": sha256_file(final_brief),
                "action_checklist": sha256_file(action_checklist),
                "review_inbox": sha256_file(review_inbox),
                "review_preview": sha256_file(review_preview),
                "review_apply_receipt": sha256_file(review_apply_receipt),
                "run_manifest": sha256_file(run_manifest),
                "demo_command": sha256_file(demo_command),
            },
        ),
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
    evidence = result.get("evidence_check") if isinstance(result.get("evidence_check"), dict) else {}
    action_contract = result.get("action_contract") if isinstance(result.get("action_contract"), dict) else {}
    lines = [
        "# Demo 当前状态诊断",
        "",
        f"- doctor_status: {result.get('doctor_status')}",
        f"- headline: {result.get('headline')}",
        f"- primary_next_action: {result.get('primary_next_action')}",
        f"- try_now_allowed: {result.get('try_now_allowed')}",
        f"- rerun_required: {result.get('rerun_required')}",
        f"- safe_apply_required: {result.get('safe_apply_required')}",
        f"- evidence_status: {evidence.get('status', 'missing')}",
        f"- strict_status: {evidence.get('strict_status', 'missing')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    if evidence:
        lines.extend(["", "## Evidence Check", ""])
        for key in ("status", "strict_status", "matched_preview_apply", "matched_refresh_command", "matched_run_manifest"):
            lines.append(f"- {key}: {evidence.get(key)}")
    if action_contract:
        lines.extend(["", "## Action Contract", ""])
        for key in (
            "primary_next_action",
            "is_read_only",
            "writes_roster",
            "requires_manual_confirmation",
            "allowed_for_launcher",
            "reason",
        ):
            lines.append(f"- {key}: {action_contract.get(key)}")
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
