#!/usr/bin/env python
"""Dry-run local review decisions before applying them to the accepted roster."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.3-lite-review-decision-preview"


class ReviewPreviewError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ReviewPreviewError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewPreviewError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise ReviewPreviewError(f"Expected JSON object: {path}")
    return data


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return load_json(path)


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


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_strings(items: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def field_value(item: Any) -> Any:
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    return item


def character_name(snapshot: dict[str, Any]) -> str:
    character = snapshot.get("character") if isinstance(snapshot.get("character"), dict) else {}
    return str(field_value(character.get("name")) or "unknown_character")


def character_key(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


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


def pending_lookup(review_inbox: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not isinstance(review_inbox, dict):
        return lookup
    for item in as_list(review_inbox.get("pending")):
        if not isinstance(item, dict):
            continue
        for key in path_keys(item.get("normalized_json")):
            lookup[key] = item
    return lookup


def accepted_characters(roster_index: dict[str, Any] | None) -> set[str]:
    if not isinstance(roster_index, dict):
        return set()
    characters = roster_index.get("characters") if isinstance(roster_index.get("characters"), list) else []
    return {character_key(item.get("name")) for item in characters if isinstance(item, dict)}


def source_match(
    manifest: dict[str, Any],
    key: str,
    current_path: Path | None,
    warnings: list[str],
) -> bool:
    expected = manifest.get(key)
    actual = sha256_file(current_path)
    if expected and actual and str(expected) == str(actual):
        return True
    if not expected:
        warnings.append(f"{key} 缺失，无法确认模板来源。")
    elif not actual:
        warnings.append(f"{key} 对应的当前文件缺失，无法确认模板来源。")
    else:
        warnings.append(f"{key} 与当前文件不一致。")
    return False


def source_check(
    manifest: dict[str, Any],
    *,
    review_inbox_path: Path | None,
    run_manifest_path: Path | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    review_match = source_match(manifest, "source_review_inbox_sha256", review_inbox_path, warnings)
    run_match = source_match(manifest, "source_run_manifest_sha256", run_manifest_path, warnings)
    stale = not review_match or not run_match
    return {
        "review_inbox_match": review_match,
        "run_manifest_match": run_match,
        "stale_template": stale,
        "warnings": unique_strings(warnings),
    }


def decision_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("decisions")
    if not isinstance(raw, list):
        raise ReviewPreviewError("Decision manifest must contain a decisions list")
    return [item for item in raw if isinstance(item, dict)]


def unsafe_accept_reasons(snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    blockers = as_list(quality.get("blockers"))
    if str(source.get("review_status") or "").upper() == "FAIL":
        reasons.append("review_status=FAIL cannot be accepted")
    if int(quality.get("invalid_field_count") or 0) > 0:
        reasons.append("invalid_candidate fields cannot be accepted")
    if any("invalid_candidate" in str(item) for item in blockers):
        reasons.append("invalid_candidate blocker cannot be accepted")
    if any("review_status 为 FAIL" in str(item) for item in blockers):
        reasons.append("FAIL blocker cannot be accepted")
    if "invalid_candidate" in json.dumps(snapshot, ensure_ascii=False):
        reasons.append("snapshot contains invalid_candidate")
    return unique_strings(reasons)


def quality_blockers(snapshot: dict[str, Any], unsafe: list[str]) -> list[str]:
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    blockers = [str(item) for item in as_list(quality.get("blockers")) if item]
    unsafe_blob = " ".join(unsafe)
    return [item for item in blockers if item not in unsafe_blob and "invalid_candidate" not in item and "FAIL" not in item]


def load_snapshot(path_value: Any) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    if not path_value:
        return None, None, "missing normalized_json"
    path = resolve_path(str(path_value))
    if not path.exists():
        return path, None, f"normalized_json does not exist: {path}"
    return path, load_json(path), None


def preview_item(
    decision: dict[str, Any],
    *,
    pending_by_path: dict[str, dict[str, Any]],
    accepted: set[str],
    stale_template: bool,
) -> dict[str, Any]:
    decision_value = str(decision.get("decision") or "pending").lower()
    normalized_json = decision.get("normalized_json")
    source_path, snapshot, load_error = load_snapshot(normalized_json)
    pending = None
    for key in path_keys(normalized_json):
        pending = pending_by_path.get(key)
        if pending:
            break
    character = decision.get("character") or (pending or {}).get("character")
    if snapshot:
        character = character_name(snapshot)
    blockers: list[str] = []
    warnings: list[str] = []
    status = "pending" if decision_value == "pending" else "ready"
    if decision_value not in {"accept", "reject", "pending", ""}:
        status = "blocked"
        blockers.append(f"Unsupported decision: {decision_value}")
    if stale_template and decision_value == "accept":
        status = "blocked"
        blockers.append("template_source_mismatch")
    if decision_value == "accept" and pending is None:
        status = "blocked"
        blockers.append("normalized_json is not in current review_inbox.pending")
    if load_error and decision_value == "accept":
        status = "blocked"
        blockers.append(load_error)
    unsafe: list[str] = []
    manual_blockers: list[str] = []
    if snapshot and decision_value == "accept":
        unsafe = unsafe_accept_reasons(snapshot)
        if unsafe:
            status = "blocked"
            blockers.extend(unsafe)
        manual_blockers = quality_blockers(snapshot, unsafe)
        note = str(decision.get("note") or decision.get("override_reason") or "").strip()
        if manual_blockers and not note and status != "blocked":
            status = "needs_review"
            warnings.append("quality blockers 存在，accept 前需要填写 note 或 override_reason。")
        elif manual_blockers and note and status != "blocked":
            warnings.append("quality blockers 由 note/override_reason 解释，仅作为 dry-run 预览。")
    would_enter = decision_value == "accept" and status == "ready"
    return {
        "character": character,
        "decision": "pending" if decision_value == "" else decision_value,
        "normalized_json": str(source_path) if source_path else normalized_json,
        "review_html": decision.get("review_html") or (pending or {}).get("review_html"),
        "decision_status": status,
        "would_enter_roster": would_enter,
        "would_replace_existing": bool(would_enter and character_key(character) in accepted),
        "blockers": unique_strings(blockers),
        "warnings": unique_strings(warnings + manual_blockers),
    }


def preview_status(source: dict[str, Any], items: list[dict[str, Any]]) -> str:
    if source.get("stale_template"):
        return "blocked"
    if any(item.get("decision_status") == "blocked" for item in items):
        return "blocked"
    if any(item.get("decision_status") in {"needs_review", "pending"} for item in items):
        return "needs_review"
    return "ready"


def render_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    lines = [
        "# Review Decision Preview",
        "",
        "preview 只做 dry-run，不写 accepted/rejected，不调用 apply_review_decisions。",
        "",
        f"- preview_status: {result.get('preview_status')}",
        f"- accept_count: {summary.get('accept_count', 0)}",
        f"- blocked_accept_count: {summary.get('blocked_accept_count', 0)}",
        f"- would_update_roster_count: {summary.get('would_update_roster_count', 0)}",
        "",
        "## Source Check",
        "",
    ]
    source = result.get("source_check", {}) if isinstance(result.get("source_check"), dict) else {}
    lines.extend(
        [
            f"- review_inbox_match: {source.get('review_inbox_match')}",
            f"- run_manifest_match: {source.get('run_manifest_match')}",
            f"- stale_template: {source.get('stale_template')}",
            "",
        ]
    )
    for warning in as_list(source.get("warnings")):
        lines.append(f"- warning: {warning}")
    lines.extend(["", "## Items", ""])
    for item in as_list(result.get("items")):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- [{item.get('decision_status')}] {item.get('decision')}: {item.get('character')} "
            f"would_enter_roster={item.get('would_enter_roster')}"
        )
        for blocker in as_list(item.get("blockers")):
            lines.append(f"  - blocker: {blocker}")
        for warning in as_list(item.get("warnings")):
            lines.append(f"  - warning: {warning}")
    lines.extend(["", "## Next", "", f"- {result.get('next_command')}"])
    return "\n".join(lines) + "\n"


def next_apply_command(decision_manifest: Path) -> str:
    return (
        "确认 preview 后，再手动运行 apply_review_decisions.py；"
        f"示例：python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized "
        f'--decision-manifest "{decision_manifest}" --roster-dir data/probes/roster'
    )


def preview_review_decisions(
    *,
    decision_manifest: Path,
    review_inbox: Path,
    run_manifest: Path | None,
    output_dir: Path,
    roster_index: Path | None = None,
) -> dict[str, Any]:
    manifest = load_json(decision_manifest)
    review_data = load_json(review_inbox)
    run_data = load_optional_json(run_manifest)
    roster_data = load_optional_json(roster_index)
    del run_data  # Loaded deliberately so invalid JSON fails early.
    source = source_check(manifest, review_inbox_path=review_inbox, run_manifest_path=run_manifest)
    pending_by_path = pending_lookup(review_data)
    accepted = accepted_characters(roster_data)
    items = [
        preview_item(item, pending_by_path=pending_by_path, accepted=accepted, stale_template=bool(source.get("stale_template")))
        for item in decision_items(manifest)
    ]
    summary = {
        "accept_count": sum(1 for item in items if item.get("decision") == "accept"),
        "reject_count": sum(1 for item in items if item.get("decision") == "reject"),
        "pending_count": sum(1 for item in items if item.get("decision") == "pending"),
        "blocked_accept_count": sum(1 for item in items if item.get("decision") == "accept" and item.get("decision_status") == "blocked"),
        "would_update_roster_count": sum(1 for item in items if item.get("would_enter_roster")),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "review_decision_preview.json"
    md_path = output_dir / "review_decision_preview.md"
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "preview_status": preview_status(source, items),
        "input": {
            "decision_manifest": str(decision_manifest),
            "review_inbox": str(review_inbox),
            "run_manifest": str(run_manifest) if run_manifest else None,
            "roster_index": str(roster_index) if roster_index else None,
        },
        "source_check": source,
        "summary": summary,
        "items": items,
        "next_command": next_apply_command(decision_manifest),
        "output_json": str(json_path),
        "output_md": str(md_path),
    }
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview local review decisions without writing roster outputs.")
    parser.add_argument("--decision-manifest", required=True, help="review_decisions_template.json or edited local decision manifest.")
    parser.add_argument("--review-inbox", required=True, help="Current review_inbox.json.")
    parser.add_argument("--run-manifest", required=True, help="Current run_manifest.json.")
    parser.add_argument("--roster-index", default=None, help="Optional current accepted roster_index.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for review preview artifacts.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = preview_review_decisions(
            decision_manifest=resolve_path(args.decision_manifest),
            review_inbox=resolve_path(args.review_inbox),
            run_manifest=resolve_path(args.run_manifest),
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            output_dir=resolve_path(args.output_dir),
        )
    except ReviewPreviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = result["summary"]
    print(f"preview_status: {result['preview_status']}")
    print(f"accept_count: {summary['accept_count']}")
    print(f"reject_count: {summary['reject_count']}")
    print(f"pending_count: {summary['pending_count']}")
    print(f"blocked_accept_count: {summary['blocked_accept_count']}")
    print(f"would_update_roster_count: {summary['would_update_roster_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
