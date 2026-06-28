#!/usr/bin/env python
"""Small command shell for local Miho probe workflows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import diff_normalized_snapshots as diff_tool  # noqa: E402
import normalize_export_parse as normalize_tool  # noqa: E402
import run_demo_pipeline as demo_tool  # noqa: E402


def run_demo(args: argparse.Namespace) -> int:
    summary = demo_tool.run_pipeline(
        images_dir=demo_tool.resolve_path(args.images_dir) if args.images_dir else None,
        parsed_dir=demo_tool.resolve_path(args.parsed_dir) if args.parsed_dir else None,
        manifest=demo_tool.resolve_path(args.manifest) if args.manifest else None,
        output_dir=demo_tool.resolve_path(args.output_dir),
        expected_dir=demo_tool.resolve_path(args.expected_dir),
        engine=args.engine,
        game=args.game,
        layout=args.layout,
        open_dashboard=args.open,
    )
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


def run_normalize(args: argparse.Namespace) -> int:
    result = normalize_tool.normalize_file(
        normalize_tool.resolve_path(args.parsed),
        normalize_tool.resolve_path(args.output_dir) if args.output_dir else normalize_tool.DEFAULT_OUTPUT_DIR,
    )
    print(f"normalized_json: {result['normalized_json']}")
    print(f"normalized_md: {result['normalized_md']}")
    return 0


def run_diff(args: argparse.Namespace) -> int:
    result = diff_tool.diff_files(
        normalize_tool.resolve_path(args.old),
        normalize_tool.resolve_path(args.new),
        normalize_tool.resolve_path(args.output_dir) if args.output_dir else None,
    )
    print(f"diff_json: {result['output_json']}")
    print(f"diff_md: {result['output_md']}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Miho probe command shell.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the local demo pipeline and render a dashboard.")
    source = demo.add_mutually_exclusive_group()
    source.add_argument("--images-dir", default=None, help="Image directory. Default is figs when no source is provided.")
    source.add_argument("--parsed-dir", default=None, help="Parsed JSON directory. Does not rerun OCR.")
    source.add_argument("--manifest", default=None, help="Demo manifest with image or parsed cases.")
    demo.add_argument("--output-dir", default=str(demo_tool.DEFAULT_OUTPUT_DIR), help="Output directory.")
    demo.add_argument("--expected-dir", default=str(demo_tool.DEFAULT_EXPECTED_DIR), help="Expected JSON directory.")
    demo.add_argument("--engine", choices=("auto", "tesseract", "paddle", "rapidocr", "none"), default="paddle")
    demo.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    demo.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card")
    demo.add_argument("--open", action="store_true", help="Open generated dashboard.")
    demo.set_defaults(handler=run_demo)

    normalize = subparsers.add_parser("normalize", help="Normalize one parsed JSON.")
    normalize.add_argument("--parsed", required=True, help="Parsed JSON path.")
    normalize.add_argument("--output-dir", default=None, help="Output directory.")
    normalize.set_defaults(handler=run_normalize)

    diff = subparsers.add_parser("diff", help="Diff two normalized snapshots.")
    diff.add_argument("--old", required=True, help="Old normalized JSON.")
    diff.add_argument("--new", required=True, help="New normalized JSON.")
    diff.add_argument("--output-dir", default=None, help="Output directory.")
    diff.set_defaults(handler=run_diff)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
