#!/usr/bin/env python
"""Run the ZZZ box value prototype in one command.

This pipeline uses a redacted roster JSON plus a public Prydwen meta snapshot.
If the meta snapshot is missing, it can fetch public Prydwen data first. It does
not parse raw account cookies/tokens and does not treat missing agents as owned.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = PROJECT_ROOT / "tools" / "probes"


def load_tool(module_name: str, filename: str) -> Any:
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load tool module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


meta_tool = load_tool("prepare_zzz_meta_snapshot", "prepare_zzz_meta_snapshot.py")
value_tool = load_tool("build_agent_value_cards", "build_agent_value_cards.py")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def build_meta_if_needed(args: argparse.Namespace, output_dir: Path) -> Path:
    meta_snapshot = resolve_path(args.meta_snapshot) if args.meta_snapshot else output_dir / "zzz_prydwen_meta_snapshot.json"
    if meta_snapshot.exists() and not args.refresh_meta:
        return meta_snapshot
    meta_args = [
        "--output",
        str(meta_snapshot),
        "--timeout",
        str(args.timeout),
        "--request-delay",
        str(args.request_delay),
    ]
    if args.current_only:
        meta_args.append("--current-only")
    if args.max_phases is not None:
        meta_args.extend(["--max-phases", str(args.max_phases)])
    code = meta_tool.main(meta_args)
    if code:
        raise RuntimeError(f"prepare_zzz_meta_snapshot failed with exit code {code}")
    return meta_snapshot


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster-json", required=True, help="Redacted local roster JSON. Raw images are not parsed by this pipeline yet.")
    parser.add_argument("--meta-snapshot", help="Existing public meta snapshot. If omitted, it is created under output-dir.")
    parser.add_argument("--output-dir", default="data/probes/value/box_value_pipeline")
    parser.add_argument("--refresh-meta", action="store_true", help="Fetch public Prydwen meta even if meta-snapshot already exists.")
    parser.add_argument("--current-only", action="store_true", help="Fetch only current Prydwen phases when refreshing meta.")
    parser.add_argument("--max-phases", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--request-delay", type=float, default=0.15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        meta_snapshot = build_meta_if_needed(args, output_dir)
        result = value_tool.build_agent_value_report(
            meta_snapshot=meta_snapshot,
            roster_json=resolve_path(args.roster_json),
            output_dir=output_dir,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"meta_snapshot: {meta_snapshot}")
    print(f"value_json: {result['output_json']}")
    print(f"value_markdown: {result['output_markdown']}")
    print(f"owned_count: {result['summary']['owned_count']}")
    print(f"unmapped_count: {result['summary']['unmapped_count']}")
    for mode, rec in result.get("executive_summary", {}).get("current_endgame_teams", {}).items():
        team = rec.get("recommended_team")
        names = " / ".join(team.get("member_names", [])) if team else "N/A"
        print(f"{mode}_recommended: {names} ({rec.get('recommendation_strength')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
