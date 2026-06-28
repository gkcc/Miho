#!/usr/bin/env python
"""Normalize export-image parsed JSON into a P1.0 draft snapshot."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]

SCHEMA_VERSION = "p1.0-draft"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "normalized"
FIELD_KEYS = {"value", "status", "uncertain", "evidence", "source_region"}
STAT_FIELDS = [
    "hp",
    "atk",
    "def",
    "impact",
    "crit_rate",
    "crit_dmg",
    "anomaly_mastery",
    "anomaly_proficiency",
    "pen",
    "energy_regen",
    "damage_bonus",
]


class NormalizeError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise NormalizeError(f"JSON file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NormalizeError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise NormalizeError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_field(value: Any) -> bool:
    return isinstance(value, dict) and {"value", "uncertain", "evidence", "source_region"}.issubset(value.keys())


def infer_status(value: Any, uncertain: bool) -> str:
    if value in (None, "", []):
        return "missing"
    if uncertain:
        return "uncertain"
    return "ok"


def normalized_field(raw: Any) -> dict[str, Any]:
    if is_field(raw):
        value = raw.get("value")
        uncertain = bool(raw.get("uncertain"))
        status = str(raw.get("status") or infer_status(value, uncertain))
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
        return {
            "value": value,
            "status": status,
            "uncertain": uncertain if status != "ok" else False,
            "evidence": evidence,
            "source_region": raw.get("source_region"),
        }
    value = raw if raw not in ("", []) else None
    status = infer_status(value, value is None)
    return {
        "value": value,
        "status": status,
        "uncertain": status != "ok",
        "evidence": [],
        "source_region": None,
    }


def field_value(raw: Any) -> Any:
    return normalized_field(raw).get("value")


def get_field(root: dict[str, Any], *parts: str) -> dict[str, Any]:
    current: Any = root
    for part in parts:
        if not isinstance(current, dict):
            return normalized_field(None)
        current = current.get(part)
    return normalized_field(current)


def normalize_sub_stats(raw: Any) -> list[dict[str, Any]]:
    value = field_value(raw)
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        uncertain = bool(item.get("uncertain"))
        status = str(item.get("status") or infer_status(item.get("value"), uncertain))
        normalized.append(
            {
                "stat": item.get("stat"),
                "value": item.get("value"),
                "enhancement": item.get("enhancement"),
                "status": status,
                "uncertain": uncertain if status != "ok" else False,
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), list) else [],
            }
        )
    return normalized


def normalize_skills(draft: dict[str, Any]) -> list[dict[str, Any]]:
    raw_skills = draft.get("skill_levels")
    by_slot: dict[int, dict[str, Any]] = {}
    if isinstance(raw_skills, list):
        for index, item in enumerate(raw_skills, start=1):
            if not isinstance(item, dict):
                continue
            slot = int(item.get("slot") or index)
            by_slot[slot] = item
    return [{"slot": slot, "level": normalized_field(by_slot.get(slot, {}).get("level"))} for slot in range(1, 7)]


def normalize_drive_discs(draft: dict[str, Any]) -> list[dict[str, Any]]:
    raw_discs = draft.get("drive_discs")
    by_slot: dict[int, dict[str, Any]] = {}
    if isinstance(raw_discs, list):
        for index, item in enumerate(raw_discs, start=1):
            if not isinstance(item, dict):
                continue
            slot = int(item.get("slot") or index)
            by_slot[slot] = item
    discs: list[dict[str, Any]] = []
    for slot in range(1, 7):
        item = by_slot.get(slot, {})
        discs.append(
            {
                "slot": slot,
                "set_name": normalized_field(item.get("set_name")),
                "level": normalized_field(item.get("level")),
                "main_stat": normalized_field(item.get("main_stat")),
                "sub_stats": normalize_sub_stats(item.get("sub_stats")),
            }
        )
    return discs


def iter_normalized_fields(value: Any, prefix: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict) and FIELD_KEYS.issubset(value.keys()):
        yield prefix, value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from iter_normalized_fields(item, next_prefix)
    elif isinstance(value, list):
        for index, item in enumerate(value, start=1):
            label = item.get("slot", index) if isinstance(item, dict) else index
            yield from iter_normalized_fields(item, f"{prefix}[{label}]")


def source_review_status(parsed: dict[str, Any]) -> str | None:
    for key in ("review_status", "overall_status"):
        value = parsed.get(key)
        if isinstance(value, str):
            return value
    summary = parsed.get("review_summary")
    if isinstance(summary, dict) and isinstance(summary.get("review_status"), str):
        return summary["review_status"]
    return None


def build_quality(normalized: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    fields = list(iter_normalized_fields(normalized))
    field_count = len(fields)
    trusted = [item for _, item in fields if item.get("status") == "ok" and not item.get("uncertain")]
    uncertain = [item for _, item in fields if item.get("uncertain")]
    missing = [item for _, item in fields if item.get("status") == "missing"]
    invalid = [item for _, item in fields if item.get("status") == "invalid_candidate"]
    sub_stat_items = [
        sub
        for disc in normalized["build_snapshot"]["drive_discs"]
        for sub in disc.get("sub_stats", [])
        if isinstance(sub, dict)
    ]
    uncertain.extend([item for item in sub_stat_items if item.get("uncertain")])
    invalid.extend([item for item in sub_stat_items if item.get("status") == "invalid_candidate"])

    blockers: list[str] = []
    character = normalized["character"]
    equipment = normalized["build_snapshot"]["equipment"]
    drive_discs = normalized["build_snapshot"]["drive_discs"]
    if character["name"]["status"] == "missing" or character["name"]["uncertain"]:
        blockers.append("character.name 缺失或 uncertain")
    if character["level"]["status"] == "missing":
        blockers.append("character.level 缺失")
    if equipment["name"]["status"] == "missing" or equipment["name"]["uncertain"]:
        blockers.append("equipment.name 缺失或 uncertain")
    if equipment["level"]["status"] == "missing":
        blockers.append("equipment.level 缺失")
    if len(drive_discs) < 6:
        blockers.append("drive_discs 少于 6 个")
    missing_main = sum(1 for disc in drive_discs if disc["main_stat"]["status"] == "missing")
    if missing_main >= 3:
        blockers.append("drive_disc main_stat 缺失数量 >= 3")
    if not any(disc.get("sub_stats") for disc in drive_discs):
        blockers.append("drive_disc sub_stats 全缺")
    if invalid:
        blockers.append("invalid_candidate 字段存在")

    coverage = parsed.get("coverage_summary", {}) if isinstance(parsed.get("coverage_summary"), dict) else {}
    coverage_level = coverage.get("coverage_level")
    if coverage_level in {"low", "numeric_only"}:
        blockers.append(f"coverage_level 为 {coverage_level}")
    review_status = source_review_status(parsed)
    if review_status == "FAIL":
        blockers.append("review_status 为 FAIL")

    return {
        "field_count": field_count,
        "trusted_field_count": len(trusted),
        "uncertain_field_count": len(uncertain),
        "missing_field_count": len(missing),
        "invalid_field_count": len(invalid),
        "can_import_without_review": False,
        "requires_manual_review": True,
        "blockers": list(dict.fromkeys(blockers)),
    }


def normalize_parsed(parsed: dict[str, Any], parsed_path: Path) -> dict[str, Any]:
    draft = parsed.get("extracted_draft")
    if not isinstance(draft, dict):
        raise NormalizeError("Parsed JSON does not contain extracted_draft")
    metadata = parsed.get("metadata", {}) if isinstance(parsed.get("metadata"), dict) else {}
    coverage = parsed.get("coverage_summary", {}) if isinstance(parsed.get("coverage_summary"), dict) else {}
    stats = draft.get("stats", {}) if isinstance(draft.get("stats"), dict) else {}
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "source_type": "official_export_image",
        "game": metadata.get("game") or draft.get("game"),
        "created_at": now_iso(),
        "source": {
            "parsed_json": str(parsed_path),
            "image": metadata.get("input_image"),
            "ocr_engine": metadata.get("ocr_engine"),
            "layout": metadata.get("layout"),
            "review_status": source_review_status(parsed),
            "coverage_level": coverage.get("coverage_level"),
        },
        "character": {
            "name": get_field(draft, "character", "name"),
            "level": get_field(draft, "character", "level"),
            "rank": get_field(draft, "character", "rank"),
        },
        "build_snapshot": {
            "stats": {
                "hp": normalized_field(stats.get("hp")),
                "atk": normalized_field(stats.get("atk")),
                "def": normalized_field(stats.get("def")),
                "impact": normalized_field(stats.get("impact")),
                "crit_rate": normalized_field(stats.get("crit_rate")),
                "crit_dmg": normalized_field(stats.get("crit_dmg")),
                "anomaly_mastery": normalized_field(stats.get("anomaly_mastery")),
                "anomaly_proficiency": normalized_field(stats.get("anomaly_proficiency")),
                "pen": normalized_field(stats.get("pen")),
                "energy_regen": normalized_field(stats.get("energy_regen")),
                "damage_bonus": normalized_field(stats.get("physical_dmg_bonus")),
            },
            "skill_levels": normalize_skills(draft),
            "equipment": {
                "name": get_field(draft, "equipment", "name"),
                "level": get_field(draft, "equipment", "level"),
                "rank": get_field(draft, "equipment", "rank"),
            },
            "drive_discs": normalize_drive_discs(draft),
        },
    }
    normalized["quality"] = build_quality(normalized, parsed)
    return normalized


def display_value(item: Any) -> str:
    if isinstance(item, dict) and FIELD_KEYS.issubset(item.keys()):
        value = item.get("value")
    else:
        value = item
    if value in (None, ""):
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_sub_stats(sub_stats: list[dict[str, Any]]) -> str:
    if not sub_stats:
        return ""
    pieces = []
    for item in sub_stats:
        enhancement = f"+{item['enhancement']}" if item.get("enhancement") is not None else ""
        pieces.append(" ".join(str(part) for part in [item.get("stat"), item.get("value"), enhancement] if part))
    return "; ".join(pieces)


def render_markdown(normalized: dict[str, Any]) -> str:
    character = normalized["character"]
    snapshot = normalized["build_snapshot"]
    equipment = snapshot["equipment"]
    quality = normalized["quality"]
    lines = [
        "# Export Parse Normalized Snapshot",
        "",
        "## Summary",
        f"- game: {normalized.get('game') or ''}",
        f"- source image: {normalized['source'].get('image') or ''}",
        f"- character: {display_value(character['name'])}",
        f"- level: {display_value(character['level'])}",
        f"- rank: {display_value(character['rank'])}",
        f"- equipment: {display_value(equipment['name'])}",
        f"- quality: {quality['trusted_field_count']}/{quality['field_count']} trusted",
        f"- can_import_without_review: {quality['can_import_without_review']}",
        f"- requires_manual_review: {quality['requires_manual_review']}",
        "",
        "## Stats",
        "",
        "| field | value | status | uncertain |",
        "|---|---|---|---|",
    ]
    for name in STAT_FIELDS:
        item = snapshot["stats"][name]
        lines.append(f"| {name} | {display_value(item)} | {item.get('status')} | {item.get('uncertain')} |")
    lines.extend(["", "## Skills", "", "| slot | level | status | uncertain |", "|---:|---|---|---|"])
    for item in snapshot["skill_levels"]:
        level = item["level"]
        lines.append(f"| {item['slot']} | {display_value(level)} | {level.get('status')} | {level.get('uncertain')} |")
    lines.extend(
        [
            "",
            "## Equipment",
            "",
            f"- name: {display_value(equipment['name'])} ({equipment['name'].get('status')})",
            f"- level: {display_value(equipment['level'])} ({equipment['level'].get('status')})",
            f"- rank: {display_value(equipment['rank'])} ({equipment['rank'].get('status')})",
            "",
            "## Drive Discs",
            "",
            "| slot | set_name | level | main_stat | sub_stats |",
            "|---:|---|---|---|---|",
        ]
    )
    for disc in snapshot["drive_discs"]:
        lines.append(
            f"| {disc['slot']} | {display_value(disc['set_name'])} | {display_value(disc['level'])} | "
            f"{display_value(disc['main_stat'])} | {render_sub_stats(disc['sub_stats'])} |"
        )
    lines.extend(["", "## Quality Blockers", ""])
    blockers = quality.get("blockers", [])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Notes",
            "This is a P1.0 draft normalized snapshot from an official export-image probe. It is not a formal database record and must be manually reviewed before any future import.",
            "",
        ]
    )
    return "\n".join(lines)


def output_paths(parsed_path: Path, output_dir: Path) -> tuple[Path, Path]:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", parsed_path.stem)
    return output_dir / f"{stem}_normalized.json", output_dir / f"{stem}_normalized.md"


def normalize_file(parsed_path: Path, output_dir: Path) -> dict[str, Any]:
    parsed = load_json(parsed_path)
    normalized = normalize_parsed(parsed, parsed_path)
    json_path, md_path = output_paths(parsed_path, output_dir)
    write_json(json_path, normalized)
    md_path.write_text(render_markdown(normalized), encoding="utf-8")
    return {
        "normalized": normalized,
        "normalized_json": str(json_path),
        "normalized_md": str(md_path),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize export-image parsed JSON into a P1.0 draft snapshot.")
    parser.add_argument("--parsed", required=True, help="Parsed JSON path from export_image_parse_probe.py.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Default: data/probes/normalized.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        parsed_path = resolve_path(args.parsed)
        output_dir = resolve_path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
        result = normalize_file(parsed_path, output_dir)
    except NormalizeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    normalized = result["normalized"]
    quality = normalized["quality"]
    print(f"normalized_json: {result['normalized_json']}")
    print(f"normalized_md: {result['normalized_md']}")
    print(f"trusted_field_count: {quality['trusted_field_count']}")
    print(f"requires_manual_review: {quality['requires_manual_review']}")
    if quality.get("blockers"):
        print("quality_blockers:")
        for blocker in quality["blockers"]:
            print(f"- {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
