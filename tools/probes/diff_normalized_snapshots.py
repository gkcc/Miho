#!/usr/bin/env python
"""Diff two P1.0 draft normalized export snapshots."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import normalize_export_parse as normalizer  # noqa: E402


class DiffError(RuntimeError):
    pass


def field_parts(path: str) -> list[tuple[str, int | None]]:
    parts: list[tuple[str, int | None]] = []
    for raw in path.split("."):
        if "[" in raw and raw.endswith("]"):
            name, index = raw[:-1].split("[", 1)
            parts.append((name, int(index)))
        else:
            parts.append((raw, None))
    return parts


def select_slot(values: Any, slot: int) -> Any:
    if not isinstance(values, list):
        return None
    for item in values:
        if isinstance(item, dict) and item.get("slot") == slot:
            return item
    index = slot - 1
    return values[index] if 0 <= index < len(values) else None


def get_path(root: dict[str, Any], path: str) -> Any:
    current: Any = root
    for name, slot in field_parts(path):
        if not isinstance(current, dict):
            return None
        current = current.get(name)
        if slot is not None:
            current = select_slot(current, slot)
    return current


def field_state(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and normalizer.FIELD_KEYS.issubset(value.keys()):
        return {
            "value": value.get("value"),
            "status": value.get("status"),
            "uncertain": bool(value.get("uncertain")),
        }
    if isinstance(value, list):
        normalized_rows = []
        row_uncertain = False
        for item in value:
            if not isinstance(item, dict):
                continue
            normalized_rows.append(
                {
                    "stat": item.get("stat"),
                    "value": item.get("value"),
                    "enhancement": item.get("enhancement"),
                }
            )
            row_uncertain = row_uncertain or bool(item.get("uncertain"))
        return {"value": normalized_rows, "status": "ok" if normalized_rows else "missing", "uncertain": row_uncertain}
    return {"value": value, "status": normalizer.infer_status(value, value is None), "uncertain": value is None}


def compare_paths() -> list[str]:
    paths = ["character.level"]
    for field in normalizer.STAT_FIELDS:
        paths.append(f"build_snapshot.stats.{field}")
    for slot in range(1, 7):
        paths.append(f"build_snapshot.skill_levels[{slot}].level")
    for field in ("name", "level", "rank"):
        paths.append(f"build_snapshot.equipment.{field}")
    for slot in range(1, 7):
        paths.append(f"build_snapshot.drive_discs[{slot}].level")
        paths.append(f"build_snapshot.drive_discs[{slot}].set_name")
        paths.append(f"build_snapshot.drive_discs[{slot}].main_stat")
        paths.append(f"build_snapshot.drive_discs[{slot}].sub_stats")
    return paths


def diff_snapshots(old_snapshot: dict[str, Any], new_snapshot: dict[str, Any]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    for path in compare_paths():
        old_state = field_state(get_path(old_snapshot, path))
        new_state = field_state(get_path(new_snapshot, path))
        value_changed = old_state["value"] != new_state["value"]
        status_changed = old_state["status"] != new_state["status"]
        uncertain_changed = old_state["uncertain"] != new_state["uncertain"]
        if not (value_changed or status_changed or uncertain_changed):
            continue
        requires_review = bool(
            old_state.get("uncertain")
            or new_state.get("uncertain")
            or old_state.get("status") != "ok"
            or new_state.get("status") != "ok"
        )
        changes.append(
            {
                "path": path,
                "old_value": old_state["value"],
                "new_value": new_state["value"],
                "value_changed": value_changed,
                "old_status": old_state["status"],
                "new_status": new_state["status"],
                "status_changed": status_changed,
                "old_uncertain": old_state["uncertain"],
                "new_uncertain": new_state["uncertain"],
                "uncertain_changed": uncertain_changed,
                "requires_review": requires_review,
            }
        )
    return {
        "schema_version": "p1.0-draft-diff",
        "created_at": normalizer.now_iso(),
        "old_source": old_snapshot.get("source", {}),
        "new_source": new_snapshot.get("source", {}),
        "summary": {
            "change_count": len(changes),
            "requires_review_change_count": sum(1 for item in changes if item["requires_review"]),
        },
        "changes": changes,
    }


def render_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_markdown(diff: dict[str, Any]) -> str:
    lines = [
        "# Normalized Snapshot Diff",
        "",
        f"- created_at: {diff['created_at']}",
        f"- change_count: {diff['summary']['change_count']}",
        f"- requires_review_change_count: {diff['summary']['requires_review_change_count']}",
        "",
        "| path | old | new | status | requires_review |",
        "|---|---|---|---|---|",
    ]
    for item in diff["changes"]:
        status = f"{item['old_status']} -> {item['new_status']}"
        lines.append(
            f"| {item['path']} | {render_value(item['old_value'])} | {render_value(item['new_value'])} | "
            f"{status} | {item['requires_review']} |"
        )
    if not diff["changes"]:
        lines.append("| none |  |  |  | False |")
    lines.append("")
    return "\n".join(lines)


def output_paths(old_path: Path, new_path: Path, output_dir: Path) -> tuple[Path, Path]:
    old_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", old_path.stem)
    new_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", new_path.stem)
    stem = f"{old_stem}_to_{new_stem}_diff"
    return output_dir / f"{stem}.json", output_dir / f"{stem}.md"


def diff_files(old_path: Path, new_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    old_snapshot = normalizer.load_json(old_path)
    new_snapshot = normalizer.load_json(new_path)
    if old_snapshot.get("schema_version") != normalizer.SCHEMA_VERSION:
        raise DiffError(f"Old snapshot is not {normalizer.SCHEMA_VERSION}: {old_path}")
    if new_snapshot.get("schema_version") != normalizer.SCHEMA_VERSION:
        raise DiffError(f"New snapshot is not {normalizer.SCHEMA_VERSION}: {new_path}")
    diff = diff_snapshots(old_snapshot, new_snapshot)
    out_dir = output_dir or new_path.parent
    json_path, md_path = output_paths(old_path, new_path, out_dir)
    normalizer.write_json(json_path, diff)
    md_path.write_text(render_markdown(diff), encoding="utf-8")
    diff["output_json"] = str(json_path)
    diff["output_md"] = str(md_path)
    return diff


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diff two P1.0 draft normalized export snapshots.")
    parser.add_argument("--old", required=True, help="Old normalized JSON.")
    parser.add_argument("--new", required=True, help="New normalized JSON.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Default: directory of --new.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        old_path = normalizer.resolve_path(args.old)
        new_path = normalizer.resolve_path(args.new)
        output_dir = normalizer.resolve_path(args.output_dir) if args.output_dir else None
        diff = diff_files(old_path, new_path, output_dir)
    except (DiffError, normalizer.NormalizeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"change_count: {diff['summary']['change_count']}")
    print(f"requires_review_change_count: {diff['summary']['requires_review_change_count']}")
    print(f"diff_json: {diff['output_json']}")
    print(f"diff_md: {diff['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
