#!/usr/bin/env python
"""Compare parsed export-image JSON with a manually confirmed expected JSON."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import re
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

NUMERIC_TEXT_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
PERCENT_TEXT_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?%$")


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


def decimal_value(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def numeric_strings_equal(actual: str, expected: str) -> bool:
    actual_number = decimal_value(actual)
    expected_number = decimal_value(expected)
    return actual_number is not None and expected_number is not None and actual_number == expected_number


def compare_string_values(actual: str, expected: str, *, loose_numeric_text: bool) -> bool:
    actual_text = actual.strip()
    expected_text = expected.strip()
    actual_has_percent = "%" in actual_text
    expected_has_percent = "%" in expected_text
    if actual_has_percent or expected_has_percent:
        if actual_has_percent != expected_has_percent:
            return False
        if not (PERCENT_TEXT_RE.fullmatch(actual_text) and PERCENT_TEXT_RE.fullmatch(expected_text)):
            return actual_text == expected_text
        if not loose_numeric_text:
            return actual_text == expected_text
        return numeric_strings_equal(actual_text[:-1], expected_text[:-1])
    if loose_numeric_text and NUMERIC_TEXT_RE.fullmatch(actual_text) and NUMERIC_TEXT_RE.fullmatch(expected_text):
        return numeric_strings_equal(actual_text, expected_text)
    return actual_text == expected_text


def compare_normalized_values(actual_value: Any, expected_value: Any, *, loose_numeric_text: bool) -> bool:
    if isinstance(actual_value, str) and isinstance(expected_value, str):
        return compare_string_values(actual_value, expected_value, loose_numeric_text=loose_numeric_text)
    if isinstance(actual_value, list) and isinstance(expected_value, list):
        if len(actual_value) != len(expected_value):
            return False
        return all(
            compare_normalized_values(actual_item, expected_item, loose_numeric_text=loose_numeric_text)
            for actual_item, expected_item in zip(actual_value, expected_value)
        )
    if isinstance(actual_value, dict) and isinstance(expected_value, dict):
        if set(actual_value.keys()) != set(expected_value.keys()):
            return False
        return all(
            compare_normalized_values(actual_value[key], expected_value[key], loose_numeric_text=loose_numeric_text)
            for key in actual_value
        )
    return actual_value == expected_value


def compare_values(actual: Any, expected: Any, *, loose_numeric_text: bool = True) -> bool:
    actual_value = normalize(actual)
    expected_value = normalize(expected)
    return compare_normalized_values(actual_value, expected_value, loose_numeric_text=loose_numeric_text)


def group_for_path(path: str) -> str:
    if path.startswith("skill_levels"):
        return "skill_levels"
    if path.startswith("drive_discs"):
        return "drive_discs"
    if path.startswith("stats."):
        return "stats"
    return path.split(".", 1)[0]


def summarize_blockers(failed_groups: dict[str, list[str]], pass_rate: float) -> list[str]:
    blockers: list[str] = []
    if pass_rate < 0.8:
        blockers.append("pass_rate below 80% target")
    if "character" in failed_groups:
        blockers.append("character key fields failed")
    if "equipment" in failed_groups:
        blockers.append("equipment key fields failed")
    if "drive_discs" in failed_groups:
        blockers.append("drive disc level/main/sub fields failed")
    if "stats" in failed_groups and len(failed_groups["stats"]) >= 3:
        blockers.append("core stat OCR mismatch is broad")
    if "skill_levels" in failed_groups and len(failed_groups["skill_levels"]) >= 2:
        blockers.append("multiple skill levels failed")
    return blockers


def next_action_for(failed_groups: dict[str, list[str]], pass_rate: float) -> str:
    if not failed_groups:
        return "Diff is clean. Continue to manual review or fixture replay; do not auto-import without explicit confirmation."
    if pass_rate >= 0.8:
        return "Pass rate meets the P0.8 target. Fix the remaining failed fields from their crop images before fixture promotion."
    if "drive_discs" in failed_groups:
        return "Open data/probes/crops for drive_disc_* crops first; main/sub stat crop alignment is the likely bottleneck."
    if "character" in failed_groups or "equipment" in failed_groups:
        return "Open character/equipment crops and rerun with --engine paddle; Chinese OCR quality is the likely bottleneck."
    return "Inspect failed field crops, then adjust OCR engine, crop ratios, or field extraction rules."


def evaluate(parsed: dict[str, Any], expected: dict[str, Any], *, loose_numeric_text: bool = True) -> dict[str, Any]:
    comparisons = []
    failed = 0
    failed_groups: dict[str, list[str]] = {}
    for path in COMPARE_PATHS:
        expected_value = get_value(expected, path)
        actual_value = get_value(parsed, path)
        if expected_value is None and actual_value is None:
            continue
        passed = compare_values(actual_value, expected_value, loose_numeric_text=loose_numeric_text)
        if not passed:
            failed += 1
            failed_groups.setdefault(group_for_path(path), []).append(path)
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
    pass_rate = passed / total if total else 0.0
    blockers = summarize_blockers(failed_groups, pass_rate)
    return {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall_status": "PASS" if failed == 0 else "FAIL",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 4),
            "pass_rate_percent": round(pass_rate * 100, 2),
            "target_pass_rate": 0.8,
            "meets_target": pass_rate >= 0.8,
            "loose_numeric_text": loose_numeric_text,
            "failed_fields": [item for paths in failed_groups.values() for item in paths],
            "failed_groups": failed_groups,
            "blockers": blockers,
            "next_action": next_action_for(failed_groups, pass_rate),
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
        f"- pass_rate: {result['summary']['pass_rate_percent']}%",
        f"- meets_80_percent_target: {result['summary']['meets_target']}",
        f"- blockers: {', '.join(result['summary'].get('blockers', [])) or 'none'}",
        f"- next_action: {result['summary'].get('next_action', '')}",
        "",
        "## Failed Fields By Group",
        "",
    ]
    failed_groups = result["summary"].get("failed_groups", {})
    if failed_groups:
        for group, paths in failed_groups.items():
            lines.append(f"- {group}: {', '.join(paths)}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Field Diff",
            "",
        "| path | status | expected | actual |",
        "|---|---|---|---|",
        ]
    )
    for item in result["comparisons"]:
        expected = json.dumps(item.get("expected"), ensure_ascii=False)
        actual = json.dumps(item.get("actual"), ensure_ascii=False)
        lines.append(f"| {item['path']} | {item['status']} | {expected} | {actual} |")
    lines.append("")
    return "\n".join(lines)


def default_output_paths(parsed_path: Path) -> tuple[Path, Path]:
    return parsed_path.with_name(f"{parsed_path.stem}_expected_diff.json"), parsed_path.with_name(f"{parsed_path.stem}_expected_diff.md")


def evaluate_files(
    parsed_path: Path,
    expected_path: Path,
    output_json: Path | None = None,
    output_md: Path | None = None,
    *,
    loose_numeric_text: bool = True,
) -> dict[str, Any]:
    parsed = load_json(parsed_path)
    expected = load_json(expected_path)
    result = evaluate(parsed, expected, loose_numeric_text=loose_numeric_text)
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
    parser.add_argument(
        "--strict-leading-zero",
        action="store_true",
        help="Treat numeric text such as '08' and '8' as different. Default compares numeric text loosely.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = evaluate_files(
            resolve_path(args.parsed),
            resolve_path(args.expected),
            resolve_path(args.output_json) if args.output_json else None,
            resolve_path(args.output_md) if args.output_md else None,
            loose_numeric_text=not args.strict_leading_zero,
        )
    except EvaluateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"overall_status: {result['overall_status']}")
    print(f"pass_rate: {result['summary']['pass_rate_percent']}%")
    print(f"failed: {result['summary']['failed']}")
    failed_groups = result["summary"].get("failed_groups", {})
    if failed_groups:
        print("failed_groups:")
        for group, paths in failed_groups.items():
            print(f"- {group}: {', '.join(paths)}")
    blockers = result["summary"].get("blockers", [])
    if blockers:
        print("blockers:")
        for blocker in blockers:
            print(f"- {blocker}")
    print(f"next_action: {result['summary'].get('next_action')}")
    print(f"Wrote JSON diff: {result['output_json']}")
    print(f"Wrote Markdown diff: {result['output_md']}")
    return 0 if result["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
