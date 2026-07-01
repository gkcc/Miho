#!/usr/bin/env python
"""Apply local manual review decisions to normalized snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_roster_index as roster_index  # noqa: E402


SCHEMA_VERSION = "p1.4-lite-review-decisions"
APPLY_AUDIT_SCHEMA = "p2.4-lite-review-apply-audit"
APPLY_RECEIPT_SCHEMA = "p2.5-lite-review-apply-receipt"
READY_PREVIEW_STATUSES = {"ready", "ready_with_override"}


class ReviewDecisionError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ReviewDecisionError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewDecisionError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise ReviewDecisionError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_keys(value: Any) -> set[str]:
    if not value:
        return set()
    text = str(value)
    keys = {text}
    try:
        keys.add(str(resolve_path(text)))
    except OSError:
        pass
    return keys


def field_value(item: Any) -> Any:
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    return item


def safe_name(value: Any) -> str:
    text = str(value or "unknown_character").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    return (text.strip("._") or "unknown_character")[:80]


def normalized_path_from_decision(decision: dict[str, Any], normalized_dir: Path) -> Path:
    raw = decision.get("normalized_json")
    if not raw:
        raise ReviewDecisionError("Decision item missing normalized_json")
    path = resolve_path(str(raw))
    try:
        path.relative_to(normalized_dir.resolve())
    except ValueError:
        # Explicit files outside normalized_dir are allowed for local replay, but they must exist.
        pass
    return path


def character_name(snapshot: dict[str, Any]) -> str:
    character = snapshot.get("character") if isinstance(snapshot.get("character"), dict) else {}
    return str(field_value(character.get("name")) or "unknown_character")


def is_unsafe_accept(snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    blockers = quality.get("blockers") if isinstance(quality.get("blockers"), list) else []
    if source.get("review_status") == "FAIL":
        reasons.append("review_status=FAIL cannot be accepted")
    if int(quality.get("invalid_field_count") or 0) > 0:
        reasons.append("invalid_candidate fields cannot be accepted")
    if any("invalid_candidate" in str(item) for item in blockers):
        reasons.append("invalid_candidate blocker cannot be accepted")
    if any("review_status 为 FAIL" in str(item) for item in blockers):
        reasons.append("FAIL blocker cannot be accepted")
    return reasons


def target_path_for(snapshot: dict[str, Any], source_path: Path, target_dir: Path) -> Path:
    return target_dir / f"{safe_name(character_name(snapshot))}_{safe_name(source_path.stem)}.json"


def accept_decisions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if str(item.get("decision") or "pending").lower() == "accept"]


def preview_item_key(item: dict[str, Any]) -> set[str]:
    keys = path_keys(item.get("normalized_json"))
    input_info = item.get("input") if isinstance(item.get("input"), dict) else {}
    keys.update(path_keys(input_info.get("normalized_json")))
    return keys


def preview_items_by_path(preview_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    raw_items = preview_result.get("items") if isinstance(preview_result.get("items"), list) else []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        for key in preview_item_key(item):
            lookup[key] = item
    return lookup


def decision_note(decision: dict[str, Any]) -> str:
    return str(decision.get("note") or decision.get("override_reason") or "").strip()


def validate_preview_gate(
    *,
    decisions: list[dict[str, Any]],
    decision_manifest: Path,
    preview_result: Path | None,
    require_preview_ready: bool,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    accepts = accept_decisions(decisions)
    if not accepts and preview_result is None and not require_preview_ready:
        return None, {}
    if preview_result is None:
        reason = "--preview-result is required"
        if accepts:
            reason = "accept decisions require --preview-result"
        raise ReviewDecisionError(reason)
    preview_data = load_json(preview_result)
    preview_status = str(preview_data.get("preview_status") or "").lower()
    if require_preview_ready and preview_status not in READY_PREVIEW_STATUSES:
        raise ReviewDecisionError(f"preview_result.preview_status must be ready/ready_with_override, got {preview_status or 'missing'}")
    if accepts and preview_status not in READY_PREVIEW_STATUSES:
        raise ReviewDecisionError(f"accept decisions require ready preview_result, got {preview_status or 'missing'}")

    input_info = preview_data.get("input") if isinstance(preview_data.get("input"), dict) else {}
    expected_manifest_hash = input_info.get("decision_manifest_sha256")
    actual_manifest_hash = sha256_file(decision_manifest)
    if expected_manifest_hash and actual_manifest_hash and str(expected_manifest_hash) != str(actual_manifest_hash):
        raise ReviewDecisionError("decision_manifest hash does not match preview_result")
    if not expected_manifest_hash:
        raise ReviewDecisionError("preview_result missing decision_manifest_sha256")

    source_check = preview_data.get("source_check") if isinstance(preview_data.get("source_check"), dict) else {}
    if source_check.get("stale_template") or source_check.get("review_inbox_match") is False or source_check.get("run_manifest_match") is False:
        raise ReviewDecisionError("preview_result source_check is stale or mismatched")
    for source_name in ("review_inbox", "run_manifest"):
        source_value = input_info.get(source_name)
        expected_source_hash = input_info.get(f"{source_name}_sha256")
        if source_value and expected_source_hash:
            actual_source_hash = sha256_file(resolve_path(str(source_value)))
            if not actual_source_hash or str(actual_source_hash) != str(expected_source_hash):
                raise ReviewDecisionError(f"{source_name} changed after preview")

    items_by_path = preview_items_by_path(preview_data)
    accept_preview: dict[str, dict[str, Any]] = {}
    for decision in accepts:
        source_path = normalized_path_from_decision(decision, PROJECT_ROOT)
        preview_item = None
        for key in path_keys(source_path):
            preview_item = items_by_path.get(key)
            if preview_item:
                break
        if preview_item is None:
            raise ReviewDecisionError(f"preview_result missing item for accepted normalized_json: {source_path}")
        status = str(preview_item.get("decision_status") or "").lower()
        if status == "blocked":
            raise ReviewDecisionError(f"preview item is blocked for {source_path}: {'; '.join(str(item) for item in preview_item.get('blockers', []))}")
        if status == "needs_review" and not decision_note(decision):
            raise ReviewDecisionError(f"preview item needs_review and has no override note: {source_path}")
        if status not in READY_PREVIEW_STATUSES:
            raise ReviewDecisionError(f"preview item is not ready for accepted normalized_json: {source_path}")
        if preview_item.get("normalized_hash_match") is not True:
            raise ReviewDecisionError(f"normalized_json hash mismatch in preview_result: {source_path}")
        expected_normalized_hash = preview_item.get("normalized_json_sha256_actual") or preview_item.get("normalized_json_sha256_expected")
        actual_normalized_hash = sha256_file(source_path)
        if not expected_normalized_hash or not actual_normalized_hash or str(expected_normalized_hash) != str(actual_normalized_hash):
            raise ReviewDecisionError(f"normalized_json changed after preview: {source_path}")
        if decision.get("normalized_json_sha256") and str(decision.get("normalized_json_sha256")) != str(actual_normalized_hash):
            raise ReviewDecisionError(f"decision normalized_json_sha256 does not match current file: {source_path}")
        accept_preview[str(source_path)] = preview_item
    return preview_data, accept_preview


def apply_audit(
    *,
    decision_manifest: Path,
    preview_result_path: Path | None,
    preview_result: dict[str, Any] | None,
    source_path: Path,
    preview_item: dict[str, Any] | None,
    decision: dict[str, Any],
) -> dict[str, Any] | None:
    if preview_result_path is None or preview_result is None:
        return None
    input_info = preview_result.get("input") if isinstance(preview_result.get("input"), dict) else {}
    status = str((preview_item or {}).get("decision_status") or "")
    note = decision_note(decision)
    evidence = accept_evidence(
        decision=decision,
        source_path=source_path,
        preview_item=preview_item,
        normalized_json_sha256=sha256_file(source_path),
    )
    return {
        "schema_version": APPLY_AUDIT_SCHEMA,
        "decision_manifest": str(decision_manifest),
        "decision_manifest_sha256": sha256_file(decision_manifest),
        "preview_result": str(preview_result_path),
        "preview_result_sha256": sha256_file(preview_result_path),
        "run_manifest": input_info.get("run_manifest"),
        "run_manifest_sha256": input_info.get("run_manifest_sha256"),
        "normalized_json_sha256": sha256_file(source_path),
        "applied_at": roster_index.now_iso(),
        "override_used": status == "ready_with_override",
        "override_note": note if status == "ready_with_override" else "",
        "accept_evidence": evidence,
    }


def accept_evidence(
    *,
    decision: dict[str, Any],
    source_path: Path,
    preview_item: dict[str, Any] | None,
    normalized_json_sha256: str | None,
) -> dict[str, Any]:
    status = str((preview_item or {}).get("decision_status") or "not_provided")
    status_label = {
        "ready": "复核预览已就绪",
        "ready_with_override": "复核预览带人工说明",
        "not_provided": "未提供复核预览",
    }.get(status, f"复核预览状态为 {status}")
    checks = [
        "人工决定为 accept",
        status_label,
        "normalized JSON hash 已与预览结果匹配",
        "unsafe accept 阻断检查已通过",
    ]
    note = decision_note(decision)
    if status == "ready_with_override":
        checks.append("质量提示已有人工说明")
    if note:
        checks.append("人工说明已记录")
    return {
        "summary": "进入已确认角色库的依据：人工接收、复核预览就绪、源文件 hash 匹配，且 unsafe accept 检查通过。",
        "checks": checks,
        "source_normalized_json": str(source_path),
        "normalized_json_sha256": normalized_json_sha256,
        "review_html": decision.get("review_html"),
        "decision_note_present": bool(note),
        "preview_decision_status": status,
    }


def apply_decision_item(
    decision: dict[str, Any],
    normalized_dir: Path,
    roster_dir: Path,
    *,
    decision_manifest: Path,
    preview_result_path: Path | None = None,
    preview_result: dict[str, Any] | None = None,
    preview_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_path = normalized_path_from_decision(decision, normalized_dir)
    snapshot = load_json(source_path)
    decision_value = str(decision.get("decision") or "pending").lower()
    note = str(decision.get("note") or "")
    record = {
        "normalized_json": str(source_path),
        "normalized_json_sha256": sha256_file(source_path),
        "character": character_name(snapshot),
        "decision": decision_value,
        "note": note,
        "status": "skipped",
        "output_json": None,
        "error": None,
        "did_write_accepted": False,
        "did_write_rejected": False,
        "did_enter_roster": False,
        "preview_validation_status": "validated" if preview_result else "not_provided",
        "preview_decision_status": preview_item.get("decision_status") if isinstance(preview_item, dict) else None,
        "accept_evidence": None,
    }
    if decision_value in {"pending", ""}:
        record["status"] = "pending"
        return record
    if decision_value not in {"accept", "reject"}:
        record["status"] = "error"
        record["error"] = f"Unsupported decision: {decision_value}"
        return record

    metadata_key = "accepted_at" if decision_value == "accept" else "rejected_at"
    snapshot["review_decision"] = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision_value,
        "note": note,
        "decided_at": roster_index.now_iso(),
        metadata_key: roster_index.now_iso(),
        "source_normalized_json": str(source_path),
    }
    if decision_value == "accept":
        unsafe = is_unsafe_accept(snapshot)
        if unsafe:
            record["status"] = "blocked"
            record["error"] = "; ".join(unsafe)
            return record
        audit = apply_audit(
            decision_manifest=decision_manifest,
            preview_result_path=preview_result_path,
            preview_result=preview_result,
            source_path=source_path,
            preview_item=preview_item,
            decision=decision,
        )
        if audit:
            snapshot["review_apply_audit"] = audit
            record["accept_evidence"] = audit.get("accept_evidence")
        target_dir = roster_dir / "accepted"
    else:
        target_dir = roster_dir / "rejected"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_path_for(snapshot, source_path, target_dir)
    write_json(target_path, snapshot)
    record["status"] = "accepted" if decision_value == "accept" else "rejected"
    record["output_json"] = str(target_path)
    record["did_write_accepted"] = decision_value == "accept"
    record["did_write_rejected"] = decision_value == "reject"
    return record


def decision_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("decisions")
    if not isinstance(raw, list):
        raise ReviewDecisionError("Decision manifest must contain a decisions list")
    return [item for item in raw if isinstance(item, dict)]


def backup_existing_roster_index(roster_dir: Path) -> str | None:
    current = roster_dir / "roster_index.json"
    if not current.exists():
        return None
    history_dir = roster_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = roster_index.now_iso().replace(":", "").replace("+", "_").replace("-", "")
    target = history_dir / f"roster_index_{timestamp}.json"
    shutil.copy2(current, target)
    latest = history_dir / "roster_index_previous.json"
    shutil.copy2(current, latest)
    return str(target)


def update_roster_entry_status(records: list[dict[str, Any]], index_result: dict[str, Any] | None) -> None:
    entered_sources: set[str] = set()
    if isinstance(index_result, dict):
        characters = index_result.get("characters") if isinstance(index_result.get("characters"), list) else []
        for item in characters:
            if isinstance(item, dict) and item.get("source_normalized_json"):
                entered_sources.add(str(item.get("source_normalized_json")))
    for record in records:
        if record.get("status") != "accepted":
            continue
        if record.get("normalized_json") in entered_sources:
            record["did_enter_roster"] = True
            evidence = record.get("accept_evidence") if isinstance(record.get("accept_evidence"), dict) else {}
            checks = evidence.get("checks") if isinstance(evidence.get("checks"), list) else []
            checks.append("已确认角色库索引已引用该快照")
            evidence["checks"] = list(dict.fromkeys(str(item) for item in checks if item))
            evidence["roster_index_match"] = True
            record["accept_evidence"] = evidence
        else:
            evidence = record.get("accept_evidence") if isinstance(record.get("accept_evidence"), dict) else {}
            if evidence:
                evidence["roster_index_match"] = False
                record["accept_evidence"] = evidence


def receipt_warnings(records: list[dict[str, Any]], preview_data: dict[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    if preview_data is None and any(record.get("status") in {"rejected", "pending"} for record in records):
        warnings.append("reject/pending applied without preview_result; receipt marks source validation as not_provided.")
    if any(record.get("status") == "accepted" and not record.get("did_enter_roster") for record in records):
        warnings.append("accepted snapshot was written but did not enter roster_index.")
    return list(dict.fromkeys(warnings))


def build_apply_receipt(result: dict[str, Any], *, preview_data: dict[str, Any] | None) -> dict[str, Any]:
    records = result.get("records") if isinstance(result.get("records"), list) else []
    return {
        "schema_version": APPLY_RECEIPT_SCHEMA,
        "created_at": result.get("created_at"),
        "input": result.get("input", {}),
        "summary": {
            **(result.get("summary") if isinstance(result.get("summary"), dict) else {}),
            "did_enter_roster_count": sum(1 for item in records if isinstance(item, dict) and item.get("did_enter_roster")),
            "did_write_accepted_count": sum(1 for item in records if isinstance(item, dict) and item.get("did_write_accepted")),
            "did_write_rejected_count": sum(1 for item in records if isinstance(item, dict) and item.get("did_write_rejected")),
            "preview_validated_count": sum(1 for item in records if isinstance(item, dict) and item.get("preview_validation_status") == "validated"),
            "preview_not_provided_count": sum(1 for item in records if isinstance(item, dict) and item.get("preview_validation_status") == "not_provided"),
        },
        "review_apply_gate": result.get("review_apply_gate", {}),
        "records": records,
        "warnings": receipt_warnings(records, preview_data),
    }


def render_receipt_markdown(receipt: dict[str, Any]) -> str:
    summary = receipt.get("summary") if isinstance(receipt.get("summary"), dict) else {}
    lines = [
        "# Review Apply Receipt",
        "",
        f"- schema_version: {receipt.get('schema_version')}",
        f"- accepted_count: {summary.get('accepted_count', 0)}",
        f"- rejected_count: {summary.get('rejected_count', 0)}",
        f"- pending_count: {summary.get('pending_count', 0)}",
        f"- did_enter_roster_count: {summary.get('did_enter_roster_count', 0)}",
        f"- did_write_rejected_count: {summary.get('did_write_rejected_count', 0)}",
        f"- preview_validated_count: {summary.get('preview_validated_count', 0)}",
        f"- preview_not_provided_count: {summary.get('preview_not_provided_count', 0)}",
        "",
        "## Warnings",
        "",
    ]
    warnings = receipt.get("warnings") if isinstance(receipt.get("warnings"), list) else []
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    lines.extend(["", "## Records", ""])
    for item in receipt.get("records", []):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- [{item.get('status')}] {item.get('decision')}: {item.get('character')} "
            f"did_enter_roster={item.get('did_enter_roster')} did_write_rejected={item.get('did_write_rejected')} "
            f"preview={item.get('preview_validation_status')}"
        )
        if item.get("error"):
            lines.append(f"  - error: {item.get('error')}")
        evidence = item.get("accept_evidence") if isinstance(item.get("accept_evidence"), dict) else {}
        if evidence:
            lines.append(f"  - evidence: {evidence.get('summary')}")
            for check in evidence.get("checks", []) if isinstance(evidence.get("checks"), list) else []:
                lines.append(f"    - {check}")
    return "\n".join(lines) + "\n"


def apply_review_decisions(
    *,
    normalized_dir: Path,
    decision_manifest: Path,
    roster_dir: Path,
    preview_result: Path | None = None,
    require_preview_ready: bool = False,
) -> dict[str, Any]:
    if not normalized_dir.exists():
        raise ReviewDecisionError(f"Normalized directory does not exist: {normalized_dir}")
    manifest = load_json(decision_manifest)
    items = decision_items(manifest)
    preview_data, accept_preview = validate_preview_gate(
        decisions=items,
        decision_manifest=decision_manifest,
        preview_result=preview_result,
        require_preview_ready=require_preview_ready,
    )
    records = []
    for item in items:
        source_path = normalized_path_from_decision(item, normalized_dir)
        preview_item = accept_preview.get(str(source_path))
        records.append(
            apply_decision_item(
                item,
                normalized_dir,
                roster_dir,
                decision_manifest=decision_manifest,
                preview_result_path=preview_result,
                preview_result=preview_data,
                preview_item=preview_item,
            )
        )
    accepted_dir = roster_dir / "accepted"
    index_result = None
    previous_roster_index = None
    if accepted_dir.exists():
        try:
            previous_roster_index = backup_existing_roster_index(roster_dir)
            index_result = roster_index.build_roster_index(accepted_dir=accepted_dir, output_dir=roster_dir)
        except roster_index.RosterIndexError as exc:
            records.append(
                {
                    "normalized_json": None,
                    "character": None,
                    "decision": "index",
                    "note": "",
                    "status": "error",
                    "output_json": None,
                    "error": str(exc),
                }
            )
    update_roster_entry_status(records, index_result)
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": roster_index.now_iso(),
        "input": {
            "normalized_dir": str(normalized_dir),
            "decision_manifest": str(decision_manifest),
            "decision_manifest_sha256": sha256_file(decision_manifest),
            "preview_result": str(preview_result) if preview_result else None,
            "preview_result_sha256": sha256_file(preview_result) if preview_result else None,
            "require_preview_ready": require_preview_ready,
            "roster_dir": str(roster_dir),
        },
        "summary": {
            "accepted_count": sum(1 for item in records if item.get("status") == "accepted"),
            "rejected_count": sum(1 for item in records if item.get("status") == "rejected"),
            "pending_count": sum(1 for item in records if item.get("status") == "pending"),
            "blocked_count": sum(1 for item in records if item.get("status") == "blocked"),
            "error_count": sum(1 for item in records if item.get("status") == "error"),
        },
        "records": records,
        "previous_roster_index": previous_roster_index,
        "roster_index": index_result.get("output_json") if isinstance(index_result, dict) else None,
        "review_apply_gate": {
            "status": "ready" if preview_data and preview_data.get("preview_status") in READY_PREVIEW_STATUSES else "not_required",
            "preview_status": preview_data.get("preview_status") if isinstance(preview_data, dict) else None,
        },
    }
    roster_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_apply_receipt(result, preview_data=preview_data)
    receipt_json = roster_dir / "review_apply_receipt.json"
    receipt_md = roster_dir / "review_apply_receipt.md"
    write_json(receipt_json, receipt)
    receipt_md.write_text(render_receipt_markdown(receipt), encoding="utf-8")
    result["review_apply_receipt"] = receipt
    result["receipt_json"] = str(receipt_json)
    result["receipt_md"] = str(receipt_md)
    log_path = roster_dir / "review_log.json"
    write_json(log_path, result)
    result["output_json"] = str(log_path)
    write_json(log_path, result)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply local manual review decisions to normalized snapshots.")
    parser.add_argument("--normalized-dir", required=True, help="Directory containing candidate normalized snapshots.")
    parser.add_argument("--decision-manifest", required=True, help="Local review_decisions.json. Do not commit it.")
    parser.add_argument("--roster-dir", required=True, help="Roster output directory with accepted/rejected/index files.")
    parser.add_argument("--preview-result", default=None, help="Required for accept decisions. Generated by preview_review_decisions.py.")
    parser.add_argument("--require-preview-ready", action="store_true", help="Fail unless preview_result status is ready/ready_with_override.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    effective_require_preview_ready = bool(args.require_preview_ready or args.preview_result)
    try:
        result = apply_review_decisions(
            normalized_dir=resolve_path(args.normalized_dir),
            decision_manifest=resolve_path(args.decision_manifest),
            roster_dir=resolve_path(args.roster_dir),
            preview_result=resolve_path(args.preview_result) if args.preview_result else None,
            require_preview_ready=effective_require_preview_ready,
        )
    except ReviewDecisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = result["summary"]
    print(f"accepted_count: {summary['accepted_count']}")
    print(f"rejected_count: {summary['rejected_count']}")
    print(f"pending_count: {summary['pending_count']}")
    print(f"blocked_count: {summary['blocked_count']}")
    print(f"error_count: {summary['error_count']}")
    print(f"review_log: {result['output_json']}")
    print(f"review_apply_receipt: {result['receipt_json']}")
    if result.get("roster_index"):
        print(f"roster_index: {result['roster_index']}")
    if result.get("previous_roster_index"):
        print(f"previous_roster_index: {result['previous_roster_index']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
