#!/usr/bin/env python
"""Local-only placeholder for a future vision baseline over export/share images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_image_parse_probe as parse_probe  # noqa: E402


class VisionBaselineError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def resolve_output_dir(value: str | None) -> Path:
    if not value:
        return parse_probe.DEFAULT_OUTPUT_DIR
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def image_info_for_path(image_path: Path) -> dict[str, Any]:
    Image = parse_probe.load_image_dependency()
    with Image.open(image_path) as image:
        return parse_probe.image_info_for(image)


def build_result(image_path: Path, *, game: str, layout: str) -> tuple[dict[str, Any], int]:
    draft = parse_probe.empty_draft(game)
    result: dict[str, Any] = {
        "metadata": {
            "probe": "vision_export_image_baseline",
            "created_at": parse_probe.now_iso(),
            "input_image": parse_probe.relative_or_redacted(image_path),
            "ocr_engine": "vision-baseline",
            "ocr_route": "local_vision_baseline_unavailable",
            "game": game,
            "layout": layout,
            "notes": [
                "Local-only placeholder. It does not upload images.",
                "No local vision model is configured yet, so no fields are inferred.",
                "Use this output only to keep the expected diff/matrix pipeline shape stable.",
            ],
        },
        "image": {},
        "layout_regions": [],
        "summary": {},
        "coverage_summary": {},
        "extracted_draft": draft,
        "text_blocks": [],
        "errors": [],
    }
    if not image_path.exists():
        result["errors"].append(f"Input image does not exist: {parse_probe.relative_or_redacted(image_path)}")
        result["summary"] = parse_probe.summarize_entities([])
        result["coverage_summary"] = parse_probe.summarize_coverage(draft, [])
        return result, 2
    result["image"] = image_info_for_path(image_path)
    result["summary"] = parse_probe.summarize_entities([], draft)
    result["coverage_summary"] = parse_probe.summarize_coverage(draft, [])
    result["coverage_summary"]["coverage_level"] = "low"
    result["coverage_summary"][
        "recommendation"
    ] = "本地视觉模型 baseline 尚未配置；不能作为可导入结果。若 OCR 整体不达标，再接入 local-only 视觉模型。"
    result["coverage_summary"]["ocr_recommendation"] = "vision-baseline 当前仅占位，不上传图片，不推断字段。"
    result["errors"].append("Local vision model is not configured; vision-baseline is unavailable.")
    return result, 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local-only vision baseline placeholder for an export/share image.")
    parser.add_argument("--image", required=True, help="Local official export/share image path.")
    parser.add_argument("--output-dir", default=str(parse_probe.DEFAULT_OUTPUT_DIR), help="Output directory.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz", help="Game layout hint. Default: zzz")
    parser.add_argument(
        "--layout",
        choices=("full", "zzz-agent-card"),
        default="zzz-agent-card",
        help="Layout strategy. Default: zzz-agent-card.",
    )
    parser.add_argument("--write-crops", action="store_true", help="Write field-level crops beside the placeholder result.")
    parser.add_argument("--crop-output-dir", default=str(parse_probe.DEFAULT_CROP_OUTPUT_DIR), help="Crop output directory.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    image_path = resolve_path(args.image)
    output_dir = resolve_output_dir(args.output_dir)
    crop_output_dir = resolve_path(args.crop_output_dir)
    result, exit_code = build_result(image_path, game=args.game, layout=args.layout)
    json_path, md_path = parse_probe.write_outputs(
        result,
        output_dir,
        image_path,
        write_crops=args.write_crops,
        crop_output_dir=crop_output_dir,
    )
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    print("vision_baseline_status: unavailable")
    for error in result.get("errors", []):
        print(f"- {error}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
