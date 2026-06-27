#!/usr/bin/env python
"""Compare parsed export-image JSON with a manually confirmed expected JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMPARE_PATHS = [
    "character.name",
    "character.level",
    "character.rank",
    "stats.hp",
    "stats.atk",
    "stats.def",
    "stats.crit_rate",
    "stats.crit_dmg",
    "skill_levels[1].level",
    "skill_levels[2].level",
    "skill_levels[3].level",
    "skill_levels[4].level",
    "skill_levels[5].level",
    "skill_levels[6].level",
    "equipment.name",
    "equipment.level",
    "equipment.rank",
    "drive_discs[1].level",
    "drive_discs[1].main_stat",
    "drive_discs[1].sub_stats",
    "drive_discs[2].level",
    "drive_discs[2].main_stat",
    "drive_discs[2].sub_stats",
    "drive_discs[3].level",
    "drive_discs[3].main_stat",
    "drive_discs[3].sub_stats",
    "drive_discs[4].level",
    "drive_discs[4].main_stat",
    "drive_discs[4].sub_stats",
    "drive_discs[5].level",
    "drive_discs[5].main_stat",
    "drive_discs[5].sub_stats",
    "drive_discs[6].level",
    "drive_discs[6].main_stat",
    "drive_discs[6].sub_stats",
]


class EvaluateError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise EvaluateError(f"JSON file does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvaluateError(f"Invalid JSON: {path}. Details: {exc}") from exc


def path_parts(path: str) -> list[tuple[str, int | None]]:
    parts: list[tuple[str, int | None]] = []
    for raw in path.split("."):
        if "[" in raw and raw.endswith("]"):
            name, slot_text = raw[:-1].split("[", 1)
            parts.append((name, int(slot_text)))
        else:
            parts.append((raw, None))
    return parts


def unwrap_field(value: Any) -> Any:
    if isinstance(value, dict) and {"value", "uncertain", "evidence", "source_region"}.issubset(value.keys()):
        return value.get("value")
    return value


def select_list_item(values: Any, slot: int) -> Any:
    if not isinstance(values, list):
        return None
    for item in values:
        if isinstance(item, dict) and item.get("slot") == slot:
            return item
    index = slot - 1
    if 0 <= index < len(values):
        return values[index]
    return None


def get_value(root: dict[str, Any], path: str) -> Any:
    current: Any = root.get("extracted_draft", root)
    for name, slot in path_parts(path):
        current = unwrap_field(current)
        if not isinstance(current, dict):
            return None
        current = current.get(name)
        if slot is not None:
            current = select_list_item(current, slot)
    return unwrap_field(current)


def normalize(value: Any) -> Any:
    value = unwrap_field(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in sorted(value.items()) if key not in {"evidence", "source_region"}}
    return value


def compare_values(actual: Any, expected: Any) -> bool:
    return normalize(actual) == normalize(expected)


def evaluate(parsed: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    comparisons = []
    failed = 0
    for path in COMPARE_PATHS:
        expected_value = get_value(expected, path)
        actual_value = get_value(parsed, path)
        if expected_value is None and actual_value is None:
            continue
        passed = compare_values(actual_value, expected_value)
        if not passed:
            failed += 1
        comparisons.append(
            {
                "path": path,
                "status": "PASS" if passed else "FAIL",
                "expected": expected_value,
                "actual": actual_value,
            }
        )
    total = len(comparisons)
    passed = total - failed
    return {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall_status": "PASS" if failed == 0 else "FAIL",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
        },
        "comparisons": comparisons,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 官方分享图解析 expected diff",
        "",
        f"- overall_status: {result['overall_status']}",
        f"- total: {result['summary']['total']}",
        f"- passed: {result['summary']['passed']}",
        f"- failed: {result['summary']['failed']}",
        "",
        "| path | status | expected | actual |",
        "|---|---|---|---|",
    ]
    for item in result["comparisons"]:
        expected = json.dumps(item.get("expected"), ensure_ascii=False)
        actual = json.dumps(item.get("actual"), ensure_ascii=False)
        lines.append(f"| {item['path']} | {item['status']} | {expected} | {actual} |")
    lines.append("")
    return "\n".join(lines)


def default_output_paths(parsed_path: Path) -> tuple[Path, Path]:
    return parsed_path.with_name(f"{parsed_path.stem}_expected_diff.json"), parsed_path.with_name(f"{parsed_path.stem}_expected_diff.md")


def evaluate_files(parsed_path: Path, expected_path: Path, output_json: Path | None = None, output_md: Path | None = None) -> dict[str, Any]:
    parsed = load_json(parsed_path)
    expected = load_json(expected_path)
    result = evaluate(parsed, expected)
    default_json, default_md = default_output_paths(parsed_path)
    output_json = output_json or default_json
    output_md = output_md or default_md
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(result), encoding="utf-8")
    result["output_json"] = str(output_json)
    result["output_md"] = str(output_md)
    return result


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare parsed export-image JSON with manually confirmed expected JSON.")
    parser.add_argument("--parsed", required=True, help="Parsed JSON from export_image_parse_probe.py.")
    parser.add_argument("--expected", required=True, help="Manually confirmed expected JSON.")
    parser.add_argument("--output-json", default=None, help="Output JSON diff path. Default: <parsed_stem>_expected_diff.json")
    parser.add_argument("--output-md", default=None, help="Output Markdown diff path. Default: <parsed_stem>_expected_diff.md")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = evaluate_files(
            resolve_path(args.parsed),
            resolve_path(args.expected),
            resolve_path(args.output_json) if args.output_json else None,
            resolve_path(args.output_md) if args.output_md else None,
        )
    except EvaluateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"overall_status: {result['overall_status']}")
    print(f"failed: {result['summary']['failed']}")
    print(f"Wrote JSON diff: {result['output_json']}")
    print(f"Wrote Markdown diff: {result['output_md']}")
    return 0 if result["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
