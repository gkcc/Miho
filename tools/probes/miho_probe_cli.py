#!/usr/bin/env python
"""Command shell for the ZZZ box / tier planning workflow."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


configure_stdio()

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def detect_project_root() -> Path:
    candidates = [Path.cwd().resolve(), Path(sys.executable).resolve().parent, SCRIPT_DIR]
    for base in candidates:
        for candidate in (base, *base.parents):
            if (candidate / "README.md").exists() and (candidate / "tools" / "probes").exists():
                return candidate
    return SCRIPT_DIR.parents[1]


PROJECT_ROOT = detect_project_root()
DEFAULT_META = PROJECT_ROOT / "data" / "probes" / "meta" / "zzz_prydwen_meta_all_phases.json"
DEFAULT_BOX_DIR = PROJECT_ROOT / "data" / "probes" / "box"
DEFAULT_IMAGE_DIR = PROJECT_ROOT / "data" / "probes" / "exported_images"
DEFAULT_VALUE_DIR = PROJECT_ROOT / "data" / "probes" / "value" / "current"


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_module(name: str) -> Any:
    return importlib.import_module(name)


def render_help() -> str:
    return """MihoProbe ZZZ box / tier 规划入口

常用：
  MihoProbe.exe meta --current-only
    拉取公开 Prydwen ZZZ tier 与当前高难统计。

  MihoProbe.exe box-roster --image data\\probes\\exported_images\\zzz_box_overview.png
    从你显式提供的官方 ZZZ box 总览图生成脱敏 roster 草案。

  MihoProbe.exe box-value --roster-json data\\probes\\box\\zzz_box_roster.json --meta-snapshot data\\probes\\meta\\zzz_prydwen_meta_all_phases.json
    生成账号内价值、配队候选、培养优先级和未来观察报告。

  MihoProbe.exe status
    只读检查本地 meta / roster / value report 是否齐。

边界：
  - 不自动登录。
  - 不读取 cookie/token。
  - 不抓包。
  - 不控制游戏客户端。
  - 不把缺失角色观察队当作确定抽卡建议。
"""


def run_meta(args: argparse.Namespace) -> int:
    meta_tool = load_module("prepare_zzz_meta_snapshot")
    argv = ["--output", str(resolve_path(args.output)), "--timeout", str(args.timeout), "--request-delay", str(args.request_delay)]
    if args.current_only:
        argv.append("--current-only")
    if args.max_phases is not None:
        argv.extend(["--max-phases", str(args.max_phases)])
    return int(meta_tool.main(argv) or 0)


def run_box_roster(args: argparse.Namespace) -> int:
    box_tool = load_module("extract_zzz_box_roster")
    output_json = resolve_path(args.output_json) if args.output_json else DEFAULT_BOX_DIR / "zzz_box_roster.json"
    argv = [
        "--image",
        str(resolve_path(args.image)),
        "--output-json",
        str(output_json),
        "--output-markdown",
        str(resolve_path(args.output_markdown) if args.output_markdown else output_json.with_suffix(".md")),
        "--ocr-scale",
        str(args.ocr_scale),
        "--min-mindscape-confidence",
        str(args.min_mindscape_confidence),
    ]
    if args.meta_snapshot:
        argv.extend(["--meta-snapshot", str(resolve_path(args.meta_snapshot))])
    return int(box_tool.main(argv) or 0)


def run_box_value(args: argparse.Namespace) -> int:
    pipeline = load_module("run_zzz_box_value_pipeline")
    argv = ["--output-dir", str(resolve_path(args.output_dir))]
    if args.roster_json:
        argv.extend(["--roster-json", str(resolve_path(args.roster_json))])
    if args.box_image:
        argv.extend(["--box-image", str(resolve_path(args.box_image))])
    if args.roster_output:
        argv.extend(["--roster-output", str(resolve_path(args.roster_output))])
    if args.meta_snapshot:
        argv.extend(["--meta-snapshot", str(resolve_path(args.meta_snapshot))])
    if args.refresh_meta:
        argv.append("--refresh-meta")
    if args.current_only:
        argv.append("--current-only")
    if args.max_phases is not None:
        argv.extend(["--max-phases", str(args.max_phases)])
    argv.extend(["--timeout", str(args.timeout), "--request-delay", str(args.request_delay)])
    return int(pipeline.main(argv) or 0)


def newest_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    matches = [path for path in root.rglob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def run_status(args: argparse.Namespace) -> int:
    meta = resolve_path(args.meta_snapshot)
    roster = newest_file(resolve_path(args.box_dir), "*.json")
    box_image = newest_file(resolve_path(args.image_dir), "*.png") or newest_file(resolve_path(args.image_dir), "*.jpg")
    value_md = newest_file(PROJECT_ROOT / "data" / "probes" / "value", "agent_value_cards.md")

    print(f"project_root: {PROJECT_ROOT}")
    print(f"meta_snapshot: {meta if meta.exists() else 'missing'}")
    print(f"latest_roster_json: {roster if roster else 'missing'}")
    print(f"latest_box_image: {box_image if box_image else 'missing'}")
    print(f"latest_value_report: {value_md if value_md else 'missing'}")
    if not meta.exists():
        print("next: dist\\MihoProbe.exe meta --current-only")
    elif not roster and box_image:
        print(f"next: dist\\MihoProbe.exe box-roster --image {box_image}")
    elif roster:
        print(f"next: dist\\MihoProbe.exe box-value --roster-json {roster} --meta-snapshot {meta}")
    else:
        print("next: 放入官方 ZZZ box 总览图，或提供脱敏 roster JSON。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MihoProbe ZZZ box / tier planner", add_help=True)
    sub = parser.add_subparsers(dest="command")

    meta = sub.add_parser("meta", help="Fetch public Prydwen ZZZ meta snapshot.")
    meta.add_argument("--output", default=str(DEFAULT_META))
    meta.add_argument("--current-only", action="store_true")
    meta.add_argument("--max-phases", type=int, default=None)
    meta.add_argument("--timeout", type=int, default=30)
    meta.add_argument("--request-delay", type=float, default=0.15)
    meta.set_defaults(handler=run_meta)

    roster = sub.add_parser("box-roster", help="Extract a redacted roster draft from a local ZZZ box overview image.")
    roster.add_argument("--image", required=True)
    roster.add_argument("--meta-snapshot", default=str(DEFAULT_META))
    roster.add_argument("--output-json", default=None)
    roster.add_argument("--output-markdown", default=None)
    roster.add_argument("--ocr-scale", type=int, default=2)
    roster.add_argument("--min-mindscape-confidence", type=float, default=0.85)
    roster.set_defaults(handler=run_box_roster)

    value = sub.add_parser("box-value", help="Build box value, team, training, and future-watch report.")
    source = value.add_mutually_exclusive_group()
    source.add_argument("--roster-json")
    source.add_argument("--box-image")
    value.add_argument("--roster-output")
    value.add_argument("--meta-snapshot", default=str(DEFAULT_META))
    value.add_argument("--output-dir", default=str(DEFAULT_VALUE_DIR))
    value.add_argument("--refresh-meta", action="store_true")
    value.add_argument("--current-only", action="store_true")
    value.add_argument("--max-phases", type=int, default=None)
    value.add_argument("--timeout", type=int, default=30)
    value.add_argument("--request-delay", type=float, default=0.15)
    value.set_defaults(handler=run_box_value)

    status = sub.add_parser("status", help="Check local box/tier workflow inputs.")
    status.add_argument("--meta-snapshot", default=str(DEFAULT_META))
    status.add_argument("--box-dir", default=str(DEFAULT_BOX_DIR))
    status.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR))
    status.set_defaults(handler=run_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(render_help())
        return 0
    if len(argv) == 1 and argv[0] in {"help", "菜单"}:
        print(render_help())
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        print(render_help())
        return 0
    return int(args.handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
