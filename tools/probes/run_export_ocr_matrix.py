#!/usr/bin/env python
"""Run a small OCR experiment matrix for one official export/share image."""

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
import render_export_review as review_render  # noqa: E402
import review_export_image as review_once  # noqa: E402
import vision_export_image_baseline as vision_baseline  # noqa: E402


DEFAULT_EXPERIMENTS = ["tesseract_eng", "tesseract_chi_sim_eng", "paddle", "rapidocr", "vision_baseline"]
EXPERIMENT_CONFIGS = {
    "tesseract_eng": {"engine": "tesseract", "lang": "eng"},
    "tesseract_chi_sim_eng": {"engine": "tesseract", "lang": "chi_sim+eng"},
    "paddle": {"engine": "paddle", "lang": "chi_sim+eng"},
    "rapidocr": {"engine": "rapidocr", "lang": "chi_sim+eng"},
    "none": {"engine": "none", "lang": "eng"},
}


class MatrixError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def default_output_root(image_path: Path) -> Path:
    return PROJECT_ROOT / "data" / "probes" / "experiments" / image_path.stem


def parse_engine_list(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_EXPERIMENTS)
    engines = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in engines if item not in set(DEFAULT_EXPERIMENTS + ["none"])]
    if unknown:
        raise MatrixError(f"Unsupported experiment name(s): {', '.join(unknown)}")
    return engines


def latest_json_from_result(result: dict[str, Any]) -> Path:
    return Path(result["json_path"])


def evaluate_if_possible(parsed_path: Path, expected_path: Path, output_dir: Path) -> dict[str, Any]:
    diff_json = output_dir / f"{parsed_path.stem}_expected_diff.json"
    diff_md = output_dir / f"{parsed_path.stem}_expected_diff.md"
    return evaluator.evaluate_files(parsed_path, expected_path, diff_json, diff_md)


def run_review_experiment(
    *,
    name: str,
    image_path: Path,
    output_dir: Path,
    expected_path: Path,
    game: str,
    layout: str,
    write_crops: bool,
) -> dict[str, Any]:
    config = EXPERIMENT_CONFIGS[name]
    result = review_once.run_review(
        image_path=image_path,
        output_dir=output_dir,
        engine=config["engine"],
        lang=config["lang"],
        game=game,
        layout=layout,
        write_crops=write_crops,
    )
    parsed_path = latest_json_from_result(result)
    diff = evaluate_if_possible(parsed_path, expected_path, output_dir)
    return {
        "name": name,
        "engine": config["engine"],
        "lang": config["lang"],
        "parse_exit_code": result.get("parse_exit_code"),
        "review_status": result.get("review_status"),
        "coverage_level": result.get("coverage_level"),
        "parsed_json": result.get("json_path"),
        "review_html": result.get("review_html"),
        "expected_diff_json": diff.get("output_json"),
        "expected_diff_md": diff.get("output_md"),
        "pass_rate": diff["summary"].get("pass_rate"),
        "pass_rate_percent": diff["summary"].get("pass_rate_percent"),
        "failed_fields": diff["summary"].get("failed_fields", []),
        "failed_groups": diff["summary"].get("failed_groups", {}),
        "next_action": diff["summary"].get("next_action"),
        "errors": result.get("errors", []),
    }


def run_vision_experiment(
    *,
    image_path: Path,
    output_dir: Path,
    expected_path: Path,
    game: str,
    layout: str,
    write_crops: bool,
) -> dict[str, Any]:
    parsed, exit_code = vision_baseline.build_result(image_path, game=game, layout=layout)
    json_path, md_path = parse_probe.write_outputs(parsed, output_dir, image_path, write_crops=write_crops)
    review = review_render.render_review(json_path, image_override=str(image_path), output_dir=str(output_dir))
    diff = evaluate_if_possible(json_path, expected_path, output_dir)
    return {
        "name": "vision_baseline",
        "engine": "vision-baseline",
        "lang": None,
        "parse_exit_code": exit_code,
        "review_status": "FAIL",
        "coverage_level": parsed.get("coverage_summary", {}).get("coverage_level"),
        "parsed_json": str(json_path),
        "parsed_markdown": str(md_path),
        "review_html": review.get("review_html"),
        "expected_diff_json": diff.get("output_json"),
        "expected_diff_md": diff.get("output_md"),
        "pass_rate": diff["summary"].get("pass_rate"),
        "pass_rate_percent": diff["summary"].get("pass_rate_percent"),
        "failed_fields": diff["summary"].get("failed_fields", []),
        "failed_groups": diff["summary"].get("failed_groups", {}),
        "next_action": diff["summary"].get("next_action"),
        "errors": parsed.get("errors", []),
    }


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 官方分享图 OCR 实验矩阵",
        "",
        f"- image: `{summary['image']}`",
        f"- expected: `{summary['expected']}`",
        f"- created_at: {summary['created_at']}",
        "",
        "| experiment | engine | pass_rate | review_status | coverage | failed_groups | next_action |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in summary["experiments"]:
        failed_groups = ", ".join(f"{key}:{len(value)}" for key, value in item.get("failed_groups", {}).items()) or "none"
        lines.append(
            "| "
            f"{item['name']} | "
            f"{item['engine']} | "
            f"{item.get('pass_rate_percent')} | "
            f"{item.get('review_status')} | "
            f"{item.get('coverage_level')} | "
            f"{failed_groups} | "
            f"{str(item.get('next_action') or '').replace('|', '/')} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_summary(summary: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    json_path = output_root / "ocr_matrix_summary.json"
    md_path = output_root / "ocr_matrix_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_summary_markdown(summary), encoding="utf-8")
    return json_path, md_path


def run_matrix(
    *,
    image_path: Path,
    expected_path: Path,
    output_root: Path,
    engines: list[str],
    game: str,
    layout: str,
    write_crops: bool,
) -> dict[str, Any]:
    if not image_path.exists():
        raise MatrixError(f"Input image does not exist: {image_path}")
    if not expected_path.exists():
        raise MatrixError(f"Expected JSON does not exist: {expected_path}")
    output_root.mkdir(parents=True, exist_ok=True)

    experiments = []
    for name in engines:
        output_dir = output_root / name
        output_dir.mkdir(parents=True, exist_ok=True)
        if name == "vision_baseline":
            item = run_vision_experiment(
                image_path=image_path,
                output_dir=output_dir,
                expected_path=expected_path,
                game=game,
                layout=layout,
                write_crops=write_crops,
            )
        else:
            item = run_review_experiment(
                name=name,
                image_path=image_path,
                output_dir=output_dir,
                expected_path=expected_path,
                game=game,
                layout=layout,
                write_crops=write_crops,
            )
        experiments.append(item)

    experiments.sort(key=lambda item: (item.get("pass_rate") or 0), reverse=True)
    summary = {
        "created_at": parse_probe.now_iso(),
        "image": str(image_path),
        "expected": str(expected_path),
        "output_root": str(output_root),
        "experiments": experiments,
    }
    json_path, md_path = write_summary(summary, output_root)
    summary["summary_json"] = str(json_path)
    summary["summary_md"] = str(md_path)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a P0.8 OCR experiment matrix for one export/share image.")
    parser.add_argument("--image", required=True, help="Local official export/share image path.")
    parser.add_argument("--expected", required=True, help="Manually confirmed expected JSON.")
    parser.add_argument("--output-root", default=None, help="Output root. Default: data/probes/experiments/<image_stem>")
    parser.add_argument(
        "--engines",
        default=None,
        help="Comma-separated experiments. Default: tesseract_eng,tesseract_chi_sim_eng,paddle,rapidocr,vision_baseline",
    )
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz", help="Game layout hint. Default: zzz")
    parser.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card", help="Layout strategy.")
    parser.add_argument("--write-crops", action="store_true", help="Write field-level crops for each experiment.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        image_path = resolve_path(args.image)
        expected_path = resolve_path(args.expected)
        output_root = resolve_path(args.output_root) if args.output_root else default_output_root(image_path)
        summary = run_matrix(
            image_path=image_path,
            expected_path=expected_path,
            output_root=output_root,
            engines=parse_engine_list(args.engines),
            game=args.game,
            layout=args.layout,
            write_crops=args.write_crops,
        )
    except (MatrixError, evaluator.EvaluateError, review_once.ReviewOnceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote matrix JSON: {summary['summary_json']}")
    print(f"Wrote matrix Markdown: {summary['summary_md']}")
    for item in summary["experiments"]:
        print(f"{item['name']}: pass_rate={item.get('pass_rate_percent')} failed={len(item.get('failed_fields', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
