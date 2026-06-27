#!/usr/bin/env python
"""Create a blank expected JSON template from a parsed export-image JSON."""

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


class TemplateError(RuntimeError):
    pass


def blank_template(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "extracted_draft": {
            "character": {
                "name": "",
                "level": "",
                "rank": "",
            },
            "stats": {
                "hp": "",
                "atk": "",
                "def": "",
                "crit_rate": "",
                "crit_dmg": "",
            },
            "skill_levels": [{"slot": slot, "level": ""} for slot in range(1, 7)],
            "equipment": {
                "name": "",
                "level": "",
                "rank": "",
            },
            "drive_discs": [
                {
                    "slot": slot,
                    "level": "",
                    "main_stat": "",
                    "sub_stats": [],
                }
                for slot in range(1, 7)
            ],
        }
    }


def make_template(parsed_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    parsed = evaluator.load_json(parsed_path)
    template = blank_template(parsed)
    output_path = output_path or parsed_path.with_name(f"{parsed_path.stem}_expected_template.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_json": str(output_path), "template": template}


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a blank expected JSON template from a parsed export-image JSON.")
    parser.add_argument("--parsed", required=True, help="Parsed JSON from export_image_parse_probe.py.")
    parser.add_argument(
        "--output",
        default=None,
        help="Output expected template path. Default: <parsed_stem>_expected_template.json",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = make_template(resolve_path(args.parsed), resolve_path(args.output) if args.output else None)
    except (TemplateError, evaluator.EvaluateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote expected template: {result['output_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
