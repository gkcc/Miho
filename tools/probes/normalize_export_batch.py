#!/usr/bin/env python
"""Batch normalize export-image parsed JSON files without OCR."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import normalize_export_parse as normalizer  # noqa: E402


class NormalizeBatchError(RuntimeError):
    pass


def parse_manifest(path: Path) -> list[Path]:
    if not path.exists():
        raise NormalizeBatchError(f"Manifest does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NormalizeBatchError(f"Invalid manifest JSON: {path}. Details: {exc}") from exc
    raw_cases: Any
    if isinstance(data, dict):
        raw_cases = data.get("cases") or data.get("parsed")
    elif isinstance(data, list):
        raw_cases = data
    else:
        raw_cases = None
    if not isinstance(raw_cases, list):
        raise NormalizeBatchError("Manifest must be a list or an object with a cases/parsed list")
    paths: list[Path] = []
    for index, item in enumerate(raw_cases, start=1):
        if isinstance(item, str):
            parsed = item
        elif isinstance(item, dict) and item.get("parsed"):
            parsed = str(item["parsed"])
        else:
            raise NormalizeBatchError(f"Manifest item #{index} must be a path or object with parsed")
        paths.append(normalizer.resolve_path(parsed))
    return paths


def build_parsed_paths(args: argparse.Namespace) -> list[Path]:
    paths = [normalizer.resolve_path(value) for value in args.parsed or []]
    if args.manifest:
        paths.extend(parse_manifest(normalizer.resolve_path(args.manifest)))
    if not paths:
        raise NormalizeBatchError("Provide at least one --parsed path or --manifest")
    return paths


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Export Parse Normalized Batch",
        "",
        f"- created_at: {summary['created_at']}",
        f"- case_count: {summary['case_count']}",
        f"- trusted_field_count: {summary['trusted_field_count']}",
        f"- requires_manual_review_cases: {len(summary['requires_manual_review_cases'])}",
        "",
        "## Cases",
        "",
        "| parsed | normalized_json | trusted | blockers |",
        "|---|---|---:|---|",
    ]
    for case in summary["cases"]:
        blockers = "; ".join(case.get("blockers", [])) or "none"
        lines.append(
            f"| {case['parsed']} | {case['normalized_json']} | "
            f"{case['trusted_field_count']} | {blockers} |"
        )
    lines.extend(["", "## Blockers Summary", ""])
    if summary["blockers_summary"]:
        for blocker, count in summary["blockers_summary"].items():
            lines.append(f"- {blocker}: {count}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def run_batch(parsed_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    blockers_summary: dict[str, int] = {}
    normalized_json_paths: list[str] = []
    trusted_total = 0
    review_cases: list[str] = []

    for parsed_path in parsed_paths:
        result = normalizer.normalize_file(parsed_path, output_dir)
        normalized = result["normalized"]
        quality = normalized["quality"]
        blockers = quality.get("blockers", [])
        for blocker in blockers:
            blockers_summary[blocker] = blockers_summary.get(blocker, 0) + 1
        trusted_total += int(quality.get("trusted_field_count") or 0)
        if quality.get("requires_manual_review"):
            review_cases.append(str(parsed_path))
        normalized_json_paths.append(result["normalized_json"])
        cases.append(
            {
                "parsed": str(parsed_path),
                "normalized_json": result["normalized_json"],
                "normalized_md": result["normalized_md"],
                "trusted_field_count": quality.get("trusted_field_count"),
                "requires_manual_review": quality.get("requires_manual_review"),
                "blockers": blockers,
            }
        )

    summary = {
        "created_at": normalizer.now_iso(),
        "case_count": len(cases),
        "normalized_json": normalized_json_paths,
        "trusted_field_count": trusted_total,
        "blockers_summary": blockers_summary,
        "requires_manual_review_cases": review_cases,
        "cases": cases,
    }
    json_path = output_dir / "batch_summary.json"
    md_path = output_dir / "batch_summary.md"
    normalizer.write_json(json_path, summary)
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    summary["summary_json"] = str(json_path)
    summary["summary_md"] = str(md_path)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch normalize export-image parsed JSON files without OCR.")
    parser.add_argument("--parsed", action="append", help="Parsed JSON path. Can be repeated.")
    parser.add_argument("--manifest", default=None, help="JSON list or {'cases': [{'parsed': ...}]} manifest.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Default: data/probes/normalized.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        parsed_paths = build_parsed_paths(args)
        output_dir = normalizer.resolve_path(args.output_dir) if args.output_dir else normalizer.DEFAULT_OUTPUT_DIR
        summary = run_batch(parsed_paths, output_dir)
    except (NormalizeBatchError, normalizer.NormalizeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"case_count: {summary['case_count']}")
    print(f"trusted_field_count: {summary['trusted_field_count']}")
    print(f"requires_manual_review_cases: {len(summary['requires_manual_review_cases'])}")
    print(f"summary_json: {summary['summary_json']}")
    print(f"summary_md: {summary['summary_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
