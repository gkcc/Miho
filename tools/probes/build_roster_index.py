#!/usr/bin/env python
"""Build a local accepted roster index from manually reviewed snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p1.4-lite-roster-index"


class RosterIndexError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RosterIndexError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RosterIndexError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise RosterIndexError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def field_value(item: Any) -> Any:
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    return item


def character_name(snapshot: dict[str, Any]) -> str:
    character = snapshot.get("character") if isinstance(snapshot.get("character"), dict) else {}
    value = field_value(character.get("name")) if isinstance(character, dict) else None
    return str(value or "unknown_character")


def snapshot_entry(path: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    character = snapshot.get("character") if isinstance(snapshot.get("character"), dict) else {}
    build = snapshot.get("build_snapshot") if isinstance(snapshot.get("build_snapshot"), dict) else {}
    equipment = build.get("equipment") if isinstance(build.get("equipment"), dict) else {}
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    decision = snapshot.get("review_decision") if isinstance(snapshot.get("review_decision"), dict) else {}
    return {
        "name": character_name(snapshot),
        "level": field_value(character.get("level")) if isinstance(character, dict) else None,
        "rank": field_value(character.get("rank")) if isinstance(character, dict) else None,
        "equipment": field_value(equipment.get("name")) if isinstance(equipment, dict) else None,
        "snapshot_json": str(path),
        "source_image": source.get("image"),
        "source_normalized_json": decision.get("source_normalized_json"),
        "accepted_at": decision.get("accepted_at") or decision.get("decided_at"),
        "review_status": "accepted",
        "quality": {
            "trusted_field_count": quality.get("trusted_field_count", 0),
            "field_count": quality.get("field_count", 0),
            "blockers": quality.get("blockers", []) if isinstance(quality.get("blockers"), list) else [],
        },
    }


def build_roster_index(*, accepted_dir: Path, output_dir: Path) -> dict[str, Any]:
    if not accepted_dir.exists():
        raise RosterIndexError(f"Accepted directory does not exist: {accepted_dir}")
    if not accepted_dir.is_dir():
        raise RosterIndexError(f"Accepted path is not a directory: {accepted_dir}")
    characters = []
    for path in sorted(accepted_dir.glob("*.json")):
        snapshot = load_json(path)
        if snapshot.get("review_decision", {}).get("decision") != "accept":
            continue
        characters.append(snapshot_entry(path, snapshot))
    characters.sort(key=lambda item: str(item.get("name") or ""))
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "accepted_dir": str(accepted_dir),
        "character_count": len(characters),
        "characters": characters,
        "warnings": [
            "只有 accepted roster 可以作为已确认拥有练度；demo normalized snapshot 仍需人工确认。"
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "roster_index.json"
    md_path = output_dir / "roster_index.md"
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    return result


def render_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# 已确认 Box Index",
        "",
        "只有 accepted roster 可以作为“已拥有练度”。",
        "",
        f"- character_count: {index.get('character_count', 0)}",
        "",
        "## Characters",
        "",
    ]
    for item in index.get("characters", []):
        lines.extend(
            [
                f"### {item.get('name')}",
                f"- level: {item.get('level')}",
                f"- rank: {item.get('rank')}",
                f"- equipment: {item.get('equipment')}",
                f"- snapshot_json: {item.get('snapshot_json')}",
                f"- source_image: {item.get('source_image') or 'N/A'}",
                f"- accepted_at: {item.get('accepted_at') or 'N/A'}",
                "",
            ]
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build accepted roster index from reviewed normalized snapshots.")
    parser.add_argument("--accepted-dir", required=True, help="Directory containing accepted normalized snapshot JSON files.")
    parser.add_argument("--output-dir", required=True, help="Output directory for roster_index.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_roster_index(
            accepted_dir=resolve_path(args.accepted_dir),
            output_dir=resolve_path(args.output_dir),
        )
    except RosterIndexError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"character_count: {result['character_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
