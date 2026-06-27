#!/usr/bin/env python
"""One-command local review for an official MiYouShe export/share image."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import export_image_parse_probe as parse_probe  # noqa: E402
import render_export_review as review_render  # noqa: E402


class ReviewOnceError(RuntimeError):
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


def powershell_start_command(path: Path) -> str:
    return f'start "" "{path}"'


def run_review(
    *,
    image_path: Path,
    output_dir: Path,
    engine: str,
    lang: str,
    game: str,
    layout: str,
    open_html: bool = False,
    write_crops: bool = False,
    crop_output_dir: Path | None = None,
) -> dict[str, Any]:
    if layout == "zzz-agent-card" and game != "zzz":
        raise ReviewOnceError("--layout zzz-agent-card requires --game zzz.")
    if not image_path.exists():
        raise ReviewOnceError(f"Input image does not exist: {image_path}")
    if not image_path.is_file():
        raise ReviewOnceError(f"Input image is not a file: {image_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    parsed, parse_exit_code = parse_probe.build_result(
        image_path,
        engine=engine,
        lang=lang,
        game=game,
        layout=layout,
    )
    json_path, md_path = parse_probe.write_outputs(
        parsed,
        output_dir,
        image_path,
        write_crops=write_crops,
        crop_output_dir=crop_output_dir,
    )
    review_result = review_render.render_review(json_path, image_override=str(image_path), output_dir=str(output_dir))

    draft = parsed.get("extracted_draft", {})
    coverage = review_render.normalized_coverage_for_review(parsed.get("coverage_summary", {}), draft)
    review_status = review_render.review_status(coverage, draft)
    html_path = Path(review_result["review_html"])
    overlay_path = Path(review_result["overlay_png"])

    if open_html:
        webbrowser.open(html_path.resolve().as_uri())

    return {
        "review_status": review_status,
        "coverage_level": coverage.get("coverage_level"),
        "recommendation": coverage.get("recommendation"),
        "parse_exit_code": parse_exit_code,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "review_html": str(html_path),
        "overlay_png": str(overlay_path),
        "crop_outputs": parsed.get("crop_outputs", []),
        "open_command": powershell_start_command(html_path),
        "errors": parsed.get("errors", []),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run parse + HTML review in one command for a local official MiYouShe export/share image."
    )
    parser.add_argument("--image", required=True, help="Local official export/share image path.")
    parser.add_argument("--output-dir", default=str(parse_probe.DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/parsed")
    parser.add_argument("--engine", choices=("auto", "tesseract", "paddle", "none"), default="auto", help="OCR engine. Default: auto")
    parser.add_argument("--lang", default="chi_sim+eng", help="OCR language string. Default: chi_sim+eng")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz", help="Game layout hint. Default: zzz")
    parser.add_argument(
        "--layout",
        choices=("full", "zzz-agent-card"),
        default="zzz-agent-card",
        help="Layout strategy. Default: zzz-agent-card.",
    )
    parser.add_argument("--open", action="store_true", help="Open the generated HTML review page in the default browser.")
    parser.add_argument(
        "--write-crops",
        action="store_true",
        help="Write field-level crop images for key acceptance fields under data/probes/crops/.",
    )
    parser.add_argument(
        "--crop-output-dir",
        default=str(parse_probe.DEFAULT_CROP_OUTPUT_DIR),
        help="Crop output directory. Default: data/probes/crops",
    )
    parser.add_argument(
        "--strict-exit",
        action="store_true",
        help="Return non-zero if parsing errors occurred or review_status is FAIL. Default returns 0 when reports are generated.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = run_review(
            image_path=resolve_path(args.image),
            output_dir=resolve_output_dir(args.output_dir),
            engine=args.engine,
            lang=args.lang,
            game=args.game,
            layout=args.layout,
            open_html=args.open,
            write_crops=args.write_crops,
            crop_output_dir=resolve_path(args.crop_output_dir),
        )
    except ReviewOnceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"review_status: {result['review_status']}")
    print(f"coverage_level: {result['coverage_level']}")
    print(f"recommendation: {result['recommendation']}")
    print(f"parsed_json: {result['json_path']}")
    print(f"parsed_markdown: {result['markdown_path']}")
    print(f"review_html: {result['review_html']}")
    print(f"overlay_png: {result['overlay_png']}")
    if args.write_crops:
        print(f"field_crops: {len(result.get('crop_outputs', []))}")
    print(f"open_command: {result['open_command']}")
    if result["errors"]:
        print("parse_errors:")
        for error in result["errors"]:
            print(f"- {error}")

    if args.strict_exit and (result["parse_exit_code"] != 0 or result["review_status"] == "FAIL"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
