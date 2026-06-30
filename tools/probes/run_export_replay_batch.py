#!/usr/bin/env python
"""Replay parsed export-image JSON files against expected JSON files without OCR."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import evaluate_export_parse as evaluator  # noqa: E402
import export_image_parse_probe as parse_probe  # noqa: E402


class ReplayBatchError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def default_output_dir() -> Path:
    stamp = parse_probe.now_iso().replace(":", "").replace("+", "_").replace("-", "").replace("T", "_")
    return PROJECT_ROOT / "data" / "probes" / "replay_batches" / stamp


def case_from_paths(parsed: str, expected: str, name: str | None = None) -> dict[str, str]:
    parsed_path = resolve_path(parsed)
    expected_path = resolve_path(expected)
    return {
        "name": name or parsed_path.stem,
        "parsed": str(parsed_path),
        "expected": str(expected_path),
    }


def parse_case_arg(value: str) -> dict[str, str]:
    if "=" not in value:
        raise ReplayBatchError("--case must use parsed.json=expected.json")
    parsed, expected = value.split("=", 1)
    if not parsed.strip() or not expected.strip():
        raise ReplayBatchError("--case must include both parsed and expected paths")
    return case_from_paths(parsed.strip(), expected.strip())


def load_manifest(path: Path) -> list[dict[str, str]]:
    data = evaluator.load_json(path)
    if isinstance(data, list):
        raw_cases = data
    elif isinstance(data, dict):
        raw_cases = data.get("cases")
    else:
        raw_cases = None
    if not isinstance(raw_cases, list):
        raise ReplayBatchError("Replay manifest must be a list or an object with a 'cases' list")
    cases: list[dict[str, str]] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise ReplayBatchError(f"Manifest case #{index} must be an object")
        parsed = item.get("parsed")
        expected = item.get("expected")
        if not parsed or not expected:
            raise ReplayBatchError(f"Manifest case #{index} must include parsed and expected")
        cases.append(case_from_paths(str(parsed), str(expected), str(item.get("name") or f"case_{index}")))
    return cases


def build_cases(args: argparse.Namespace) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    if args.manifest:
        cases.extend(load_manifest(resolve_path(args.manifest)))
    for value in args.case or []:
        cases.append(parse_case_arg(value))
    parsed_values = args.parsed or []
    expected_values = args.expected or []
    if parsed_values or expected_values:
        if len(parsed_values) != len(expected_values):
            raise ReplayBatchError("--parsed and --expected must be provided in equal counts")
        for parsed, expected in zip(parsed_values, expected_values):
            cases.append(case_from_paths(parsed, expected))
    if not cases:
        raise ReplayBatchError("Provide at least one --case, --parsed/--expected pair, or --manifest")
    return cases


def resolve_replay_image_path(parsed: dict[str, Any]) -> Path | None:
    metadata = parsed.get("metadata", {}) if isinstance(parsed.get("metadata"), dict) else {}
    image_value = metadata.get("input_image")
    if not image_value:
        return None
    image_path = Path(str(image_value)).expanduser()
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    try:
        image_path = image_path.resolve()
    except OSError:
        return None
    return image_path if image_path.is_file() else None


def visual_rank_blocks_from_image(parsed: dict[str, Any], blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata = parsed.get("metadata", {}) if isinstance(parsed.get("metadata"), dict) else {}
    image_path = resolve_replay_image_path(parsed)
    if image_path is None:
        return []
    return parse_probe.visual_rank_blocks_from_image_path(
        image_path,
        game=metadata.get("game"),
        layout=str(metadata.get("layout") or ""),
        blocks=blocks,
    )


def rebuild_parsed_from_text_blocks(parsed: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    blocks = parsed.get("text_blocks")
    if not isinstance(blocks, list):
        return parsed, False
    metadata = parsed.get("metadata", {}) if isinstance(parsed.get("metadata"), dict) else {}
    replay_blocks = list(blocks)
    replay_blocks.extend(visual_rank_blocks_from_image(parsed, replay_blocks))
    rebuilt = dict(parsed)
    draft = parse_probe.build_extracted_draft(
        game=metadata.get("game"),
        layout=str(metadata.get("layout") or ""),
        blocks=replay_blocks,
        layout_regions=parsed.get("layout_regions", []) if isinstance(parsed.get("layout_regions"), list) else [],
        image_info=parsed.get("image", {}) if isinstance(parsed.get("image"), dict) else {},
    )
    rebuilt["extracted_draft"] = draft
    rebuilt["text_blocks"] = replay_blocks
    rebuilt["coverage_summary"] = parse_probe.summarize_coverage(draft, replay_blocks)
    return rebuilt, True


def evaluate_case(case: dict[str, str], *, loose_numeric_text: bool, rebuild: bool) -> dict[str, Any]:
    parsed_path = Path(case["parsed"])
    expected_path = Path(case["expected"])
    parsed = evaluator.load_json(parsed_path)
    rebuilt_from_text_blocks = False
    if rebuild:
        parsed, rebuilt_from_text_blocks = rebuild_parsed_from_text_blocks(parsed)
    expected = evaluator.load_json(expected_path)
    result = evaluator.evaluate(parsed, expected, loose_numeric_text=loose_numeric_text)
    summary = result["summary"]
    return {
        "name": case["name"],
        "parsed": str(parsed_path),
        "expected": str(expected_path),
        "rebuilt_from_text_blocks": rebuilt_from_text_blocks,
        "overall_status": result["overall_status"],
        "pass_rate": summary.get("pass_rate"),
        "pass_rate_percent": summary.get("pass_rate_percent"),
        "meets_target": summary.get("meets_target"),
        "meets_p0_9_standard": summary.get("p0_9", {}).get("meets_p0_9_standard"),
        "p0_9_blockers": summary.get("p0_9", {}).get("blockers", []),
        "failed": summary.get("failed"),
        "failed_fields": summary.get("failed_fields", []),
        "failed_groups": summary.get("failed_groups", {}),
        "group_summary": summary.get("group_summary", {}),
        "top_failed_fields": summary.get("top_failed_fields", []),
        "next_action": summary.get("next_action"),
    }


def aggregate_top_failed(cases: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for case in cases:
        for item in case.get("top_failed_fields", []):
            path = item["path"]
            entry = counts.setdefault(path, {"path": path, "group": item.get("group"), "count": 0, "cases": []})
            entry["count"] += 1
            entry["cases"].append(case["name"])
    ranked = sorted(counts.values(), key=lambda item: (-item["count"], item["group"] or "", item["path"]))
    return ranked[:limit]


def batch_p0_9(cases: list[dict[str, Any]]) -> dict[str, Any]:
    pass_rates = [float(item.get("pass_rate") or 0.0) for item in cases]
    average = sum(pass_rates) / len(pass_rates) if pass_rates else 0.0
    blockers: list[str] = []
    if len(cases) < 3:
        blockers.append("fewer than 3 replay cases")
    if average < 0.85:
        blockers.append("average pass_rate below 85%")
    failing_cases = [item["name"] for item in cases if not item.get("meets_p0_9_standard")]
    if failing_cases:
        blockers.append("case-level P0.9 blockers: " + ", ".join(failing_cases))
    return {
        "case_count": len(cases),
        "average_pass_rate": round(average, 4),
        "average_pass_rate_percent": round(average * 100, 2),
        "target_case_count": 3,
        "target_average_pass_rate": 0.85,
        "meets_case_count": len(cases) >= 3,
        "meets_average_pass_rate": average >= 0.85,
        "meets_p0_9_batch_standard": not blockers,
        "blockers": blockers,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    p0_9 = summary["p0_9"]
    lines = [
        "# 官方分享图解析 replay batch",
        "",
        f"- created_at: {summary['created_at']}",
        f"- case_count: {p0_9['case_count']}",
        f"- average_pass_rate: {p0_9['average_pass_rate_percent']}%",
        f"- meets_p0_9_batch_standard: {p0_9['meets_p0_9_batch_standard']}",
        f"- blockers: {', '.join(p0_9.get('blockers', [])) or 'none'}",
        "",
        "## Cases",
        "",
        "| case | pass_rate | P0.9 | rebuilt | failed | failed_groups | next_action |",
        "|---|---:|---|---|---:|---|---|",
    ]
    for case in summary["cases"]:
        failed_groups = ", ".join(f"{key}:{len(value)}" for key, value in case.get("failed_groups", {}).items()) or "none"
        next_action = str(case.get("next_action") or "").replace("|", "/")
        lines.append(
            f"| {case['name']} | {case.get('pass_rate_percent')}% | {case.get('meets_p0_9_standard')} | "
            f"{case.get('rebuilt_from_text_blocks')} | "
            f"{case.get('failed')} | {failed_groups} | {next_action} |"
        )
    lines.extend(["", "## Top Failed Fields", ""])
    top_failed = summary.get("top_failed_fields", [])
    if top_failed:
        for item in top_failed:
            lines.append(f"- {item['path']} ({item['group']}): {item['count']} case(s) [{', '.join(item['cases'])}]")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def write_summary(summary: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "export_replay_batch_summary.json"
    md_path = output_dir / "export_replay_batch_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    return json_path, md_path


def run_batch(
    cases: list[dict[str, str]],
    *,
    output_dir: Path,
    loose_numeric_text: bool = True,
    rebuild: bool = True,
) -> dict[str, Any]:
    evaluated = [evaluate_case(case, loose_numeric_text=loose_numeric_text, rebuild=rebuild) for case in cases]
    p0_9 = batch_p0_9(evaluated)
    summary = {
        "created_at": parse_probe.now_iso(),
        "output_dir": str(output_dir),
        "rebuild_from_text_blocks": rebuild,
        "p0_9": p0_9,
        "cases": evaluated,
        "top_failed_fields": aggregate_top_failed(evaluated),
    }
    json_path, md_path = write_summary(summary, output_dir)
    summary["summary_json"] = str(json_path)
    summary["summary_md"] = str(md_path)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay parsed export-image JSON files against expected JSON files without OCR.")
    parser.add_argument("--case", action="append", help="Replay case as parsed.json=expected.json. Can be repeated.")
    parser.add_argument("--parsed", action="append", help="Parsed JSON path. Pair with --expected; can be repeated.")
    parser.add_argument("--expected", action="append", help="Expected JSON path. Pair with --parsed; can be repeated.")
    parser.add_argument("--manifest", default=None, help="JSON list or {'cases': [...]} with name, parsed, expected.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Default: data/probes/replay_batches/<timestamp>.")
    parser.add_argument(
        "--strict-leading-zero",
        action="store_true",
        help="Treat numeric text such as '08' and '8' as different. Default compares numeric text loosely.",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Compare stored extracted_draft as-is. Default rebuilds it from stored text_blocks without OCR.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        cases = build_cases(args)
        output_dir = resolve_path(args.output_dir) if args.output_dir else default_output_dir()
        summary = run_batch(
            cases,
            output_dir=output_dir,
            loose_numeric_text=not args.strict_leading_zero,
            rebuild=not args.no_rebuild,
        )
    except (ReplayBatchError, evaluator.EvaluateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    p0_9 = summary["p0_9"]
    print(f"case_count: {p0_9['case_count']}")
    print(f"average_pass_rate: {p0_9['average_pass_rate_percent']}%")
    print(f"meets_p0_9_batch_standard: {p0_9['meets_p0_9_batch_standard']}")
    if p0_9.get("blockers"):
        print("batch_blockers:")
        for blocker in p0_9["blockers"]:
            print(f"- {blocker}")
    print(f"Wrote JSON summary: {summary['summary_json']}")
    print(f"Wrote Markdown summary: {summary['summary_md']}")
    return 0 if p0_9["meets_p0_9_batch_standard"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
