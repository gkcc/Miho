#!/usr/bin/env python
"""Apply local manual review decisions to normalized snapshots."""

from __future__ import annotations

import argparse
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


def apply_decision_item(decision: dict[str, Any], normalized_dir: Path, roster_dir: Path) -> dict[str, Any]:
    source_path = normalized_path_from_decision(decision, normalized_dir)
    snapshot = load_json(source_path)
    decision_value = str(decision.get("decision") or "pending").lower()
    note = str(decision.get("note") or "")
    record = {
        "normalized_json": str(source_path),
        "character": character_name(snapshot),
        "decision": decision_value,
        "note": note,
        "status": "skipped",
        "output_json": None,
        "error": None,
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
        target_dir = roster_dir / "accepted"
    else:
        target_dir = roster_dir / "rejected"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_path_for(snapshot, source_path, target_dir)
    write_json(target_path, snapshot)
    record["status"] = "accepted" if decision_value == "accept" else "rejected"
    record["output_json"] = str(target_path)
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


def apply_review_decisions(*, normalized_dir: Path, decision_manifest: Path, roster_dir: Path) -> dict[str, Any]:
    if not normalized_dir.exists():
        raise ReviewDecisionError(f"Normalized directory does not exist: {normalized_dir}")
    manifest = load_json(decision_manifest)
    records = [apply_decision_item(item, normalized_dir, roster_dir) for item in decision_items(manifest)]
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
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": roster_index.now_iso(),
        "input": {
            "normalized_dir": str(normalized_dir),
            "decision_manifest": str(decision_manifest),
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
    }
    roster_dir.mkdir(parents=True, exist_ok=True)
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
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = apply_review_decisions(
            normalized_dir=resolve_path(args.normalized_dir),
            decision_manifest=resolve_path(args.decision_manifest),
            roster_dir=resolve_path(args.roster_dir),
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
    if result.get("roster_index"):
        print(f"roster_index: {result['roster_index']}")
    if result.get("previous_roster_index"):
        print(f"previous_roster_index: {result['previous_roster_index']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
