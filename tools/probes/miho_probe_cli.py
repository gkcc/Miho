#!/usr/bin/env python
"""Small command shell for local Miho probe workflows."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape as html_escape
import importlib.util
import json
import sys
import webbrowser
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import diff_normalized_snapshots as diff_tool  # noqa: E402
import build_gpt_review_prompt as gpt_prompt_tool  # noqa: E402
import export_image_parse_probe as parse_probe  # noqa: E402
import miyoushe_export_workflow as app_export_workflow  # noqa: E402
import normalize_export_parse as normalize_tool  # noqa: E402
import plan_training_priorities as planner_tool  # noqa: E402
import prepare_endgame_targets as target_tool  # noqa: E402
import render_demo_dashboard as dashboard_tool  # noqa: E402
import run_demo_pipeline as demo_tool  # noqa: E402


def detect_project_root() -> Path:
    candidates = [Path.cwd().resolve(), Path(sys.executable).resolve().parent, Path(__file__).resolve().parent]
    for base in candidates:
        for candidate in (base, *base.parents):
            if (candidate / "README.md").exists() and (candidate / "tools" / "probes").exists():
                return candidate
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = detect_project_root()
DEFAULT_DEMO_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_DASHBOARD_HTML = DEFAULT_DEMO_OUTPUT_DIR / "index.html"
DEFAULT_DEMO_SUMMARY = DEFAULT_DEMO_OUTPUT_DIR / "demo_summary.json"
DEFAULT_FIGS_DIR = PROJECT_ROOT / "figs"
DEFAULT_APP_EXPORT_WORKFLOW_DIR = DEFAULT_DEMO_OUTPUT_DIR / "app_export_workflow"
DEFAULT_EXPECTED_DIR = PROJECT_ROOT / "data" / "probes" / "expected"
DEFAULT_ROSTER_DIR = PROJECT_ROOT / "data" / "probes" / "roster"
DEFAULT_NORMALIZED_DIR = PROJECT_ROOT / "data" / "probes" / "normalized"
DEFAULT_PLANNER_DIR = PROJECT_ROOT / "data" / "probes" / "planner"
DEFAULT_TARGETS_DIR = PROJECT_ROOT / "data" / "probes" / "targets"
DEFAULT_REPLAY_MANIFEST = PROJECT_ROOT / "data" / "probes" / "replay_manifest.json"
DEFAULT_RANK_CHECK_DIR = DEFAULT_DEMO_OUTPUT_DIR / "rank_check"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
LEGACY_DASHBOARD_MARKERS = (
    "Brief Warning",
    "brief status",
    "trusted ready",
    "ready targets",
    "pending review",
    "watch only",
    "final_brief.md",
    "final_brief.json",
    "简报 Markdown",
    "简报 JSON",
    "pending 只会生成复核模板",
    "watch_only",
)
_REPLAY_TOOL = None
TOP_LEVEL_HELP_FLAGS = {"--help", "-h", "help", "菜单", "menu"}


class CliReplayError(RuntimeError):
    pass


def render_user_help() -> str:
    return """MihoProbe 本地体验入口

最常用：
  MihoProbe.exe
    打开已有 Dashboard，不跑 OCR。验收界面优先点这个。

  MihoProbe.exe update
    一键更新练度（当前安全版）：处理 figs\\ 下已保存的官方分享图，然后打开 Dashboard。

  MihoProbe.exe app-export
    生成米游社 APP 官方分享图工作流包。默认不点击，只沉淀一键更新练度的可审计步骤。

  MihoProbe.exe fresh
    update 的开发别名：识别 figs\\ 下新增或变更的官方分享图。会跑 PaddleOCR，可能慢。

  MihoProbe.exe check --no-open
    用 expected diff 验收解析准确率。不重新 OCR。

  MihoProbe.exe plan-update
    一键更新高难/Tier/配队建议（本地安全版）：不 OCR、不联网，只重算本地 Dashboard。

  MihoProbe.exe rank-check
    只检查头像/音擎 A/S 艺术字固定区域。不跑 OCR，用来排查评级识别。

  MihoProbe.exe ask-gpt --focus "本轮要审的问题"
    生成给右侧 GPT 的固定审查包，避免反复摸索对话流程。

先别踩坑：
  - 只看界面，不要跑 fresh。
  - fresh 卡住时先关掉，改用 MihoProbe.exe 看缓存 Dashboard。
  - OCR 结果只进人工复核，不会直接写正式数据库。

开发细参：
  MihoProbe.exe dashboard --help
  MihoProbe.exe app-export --help
  MihoProbe.exe plan-update --help
  MihoProbe.exe rank-check --help
  MihoProbe.exe fresh --help
  MihoProbe.exe replay --help
  MihoProbe.exe gpt-review --help
"""


def should_show_top_level_help(argv: list[str]) -> bool:
    return len(argv) == 2 and argv[1].lower() in TOP_LEVEL_HELP_FLAGS


def load_replay_tool():
    global _REPLAY_TOOL
    if _REPLAY_TOOL is not None:
        return _REPLAY_TOOL
    script_path = PROJECT_ROOT / "tools" / "probes" / "run_export_replay_batch.py"
    if not script_path.exists():
        raise CliReplayError(f"Replay script does not exist: {script_path}")
    spec = importlib.util.spec_from_file_location("run_export_replay_batch_cli", script_path)
    if spec is None or spec.loader is None:
        raise CliReplayError(f"Unable to load replay script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _REPLAY_TOOL = module
    return module


def resolve_cli_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def has_legacy_dashboard_markup(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return any(marker in text for marker in LEGACY_DASHBOARD_MARKERS)


def has_stale_dashboard_renderer(path: Path) -> bool:
    if not path.exists():
        return False
    renderer_file = getattr(dashboard_tool, "__file__", None)
    if not renderer_file:
        return False
    renderer_path = Path(renderer_file)
    if not renderer_path.exists():
        return False
    return path.stat().st_mtime < renderer_path.stat().st_mtime


def render_cached_dashboard(summary_path: Path, dashboard_path: Path) -> dict[str, str]:
    summary = dashboard_tool.load_json(summary_path)
    return dashboard_tool.render_dashboard(summary, dashboard_path)


def render_first_run_dashboard(dashboard_path: Path) -> dict[str, str]:
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    figs_path = PROJECT_ROOT / "figs"
    replay_path = DEFAULT_REPLAY_MANIFEST
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MihoProbe 初次启动</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: #dbe3ef;
      --ok: #147a42;
      --ok-bg: #e8f7ee;
      --warn: #996500;
      --warn-bg: #fff4d5;
      --blue: #1d4ed8;
      --blue-bg: #eff6ff;
      --shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      line-height: 1.55;
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 22px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: 0; }}
    p {{ margin: 0; }}
    .lead {{ color: var(--muted); font-size: 16px; }}
    .hero {{
      display: grid;
      gap: 18px;
      padding: 26px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .status {{
      display: inline-flex;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--warn-bg);
      color: var(--warn);
      font-weight: 900;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 18px; }}
    .card {{
      display: grid;
      gap: 10px;
      padding: 16px;
      min-height: 178px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .card strong {{ font-size: 18px; }}
    .card span {{ color: var(--muted); font-size: 13px; }}
    .card code {{
      display: block;
      padding: 10px;
      border-radius: 8px;
      background: #0f172a;
      color: #e2e8f0;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }}
    .primary {{ border-color: #bfdbfe; background: var(--blue-bg); }}
    .primary strong {{ color: var(--blue); }}
    .safe {{ border-color: #a8e1bd; background: var(--ok-bg); }}
    .safe strong {{ color: var(--ok); }}
    .note {{
      margin-top: 18px;
      padding: 14px 16px;
      border: 1px solid #f4d071;
      border-radius: 8px;
      background: var(--warn-bg);
      color: var(--warn);
      font-weight: 800;
    }}
    .paths {{ display: grid; gap: 8px; margin-top: 18px; color: var(--muted); font-size: 13px; }}
    .paths code {{ color: var(--text); }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="status">还没有本地 Dashboard 缓存</div>
      <div>
        <h1>MihoProbe 初次启动</h1>
        <p class="lead">这不是错误。默认入口不会跑 OCR，也不会读取账号登录态；它只打开本地可视化页面。</p>
      </div>
      <div class="grid">
        <article class="card safe">
          <strong>只想验收界面</strong>
          <span>有缓存时直接打开 Dashboard；没有缓存时先看本页。不会跑 OCR。</span>
          <code>MihoProbe.exe</code>
        </article>
        <article class="card primary">
          <strong>识别新分享图</strong>
          <span>把米游社官方分享图放进 figs\\ 后再跑。PaddleOCR 首次加载可能慢。</span>
          <code>MihoProbe.exe fresh</code>
        </article>
        <article class="card">
          <strong>验收解析准确率</strong>
          <span>用 expected diff 回放验收，不重新 OCR，不扫历史 parsed 目录。</span>
          <code>MihoProbe.exe replay --no-open</code>
        </article>
      </div>
      <div class="note">如果 Fresh OCR 十分钟没反应，先关掉它，回到 MihoProbe.exe 看缓存或本页；不要把慢 OCR 当作界面卡死。</div>
      <div class="paths">
        <span>分享图目录：<code>{html_escape(str(figs_path))}</code></span>
        <span>准确率 manifest：<code>{html_escape(str(replay_path))}</code></span>
        <span>本页路径：<code>{html_escape(str(dashboard_path))}</code></span>
      </div>
    </section>
  </main>
</body>
</html>
"""
    dashboard_path.write_text(html, encoding="utf-8")
    return {"dashboard_html": str(dashboard_path)}


def render_missing_replay_manifest_page(manifest_path: Path, output_path: Path) -> dict[str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path = PROJECT_ROOT / "data" / "probes" / "expected"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>准确率验收缺少样例清单</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: #dbe3ef;
      --warn: #996500;
      --warn-bg: #fff4d5;
      --blue: #1d4ed8;
      --blue-bg: #eff6ff;
      --shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; line-height: 1.55; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 22px 48px; }}
    section {{ display: grid; gap: 18px; padding: 26px; border: 1px solid #f4d071; border-radius: 8px; background: var(--panel); box-shadow: var(--shadow); }}
    h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: 0; color: var(--warn); }}
    p {{ margin: 0; color: var(--muted); }}
    .badge {{ display: inline-flex; width: fit-content; padding: 8px 12px; border-radius: 999px; background: var(--warn-bg); color: var(--warn); font-weight: 900; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .card {{ display: grid; gap: 10px; align-content: start; min-height: 180px; padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .card.primary {{ border-color: #bfdbfe; background: var(--blue-bg); }}
    .card.primary strong {{ color: var(--blue); }}
    .card strong {{ font-size: 18px; }}
    .card span {{ color: var(--muted); font-size: 13px; }}
    code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-wrap: anywhere; white-space: pre-wrap; }}
    .paths {{ display: grid; gap: 8px; color: var(--muted); font-size: 13px; }}
    .paths code {{ display: inline; padding: 0; background: transparent; color: var(--text); }}
    @media (max-width: 860px) {{ .grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 28px; }} }}
  </style>
</head>
<body>
  <main>
    <section>
      <div class="badge">验收不能开始</div>
      <div>
        <h1>缺少 replay manifest</h1>
        <p>这不是 OCR 失败，也不是 Dashboard 坏了。准确率验收必须用固定样例清单，避免把历史 parsed JSON 混进平均通过率。</p>
      </div>
      <div class="grid">
        <article class="card primary">
          <strong>已有 3 张 expected</strong>
          <span>把 parsed JSON 和 expected JSON 写进固定清单，然后重新跑验收。</span>
          <code>MihoProbe.exe check --open</code>
        </article>
        <article class="card">
          <strong>只想看软件界面</strong>
          <span>打开缓存 Dashboard，不重新 OCR，不要求 manifest。</span>
          <code>MihoProbe.exe</code>
        </article>
        <article class="card">
          <strong>新图还没识别</strong>
          <span>先把官方分享图放进 figs\\，再跑 fresh。这个入口会慢。</span>
          <code>MihoProbe.exe fresh</code>
        </article>
      </div>
      <div class="paths">
        <span>缺少的清单：<code>{html_escape(str(manifest_path))}</code></span>
        <span>expected 本地目录：<code>{html_escape(str(expected_path))}</code></span>
        <span>本说明页：<code>{html_escape(str(output_path))}</code></span>
      </div>
    </section>
  </main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return {"html_path": str(output_path), "manifest": str(manifest_path)}


def run_dashboard(args: argparse.Namespace) -> int:
    dashboard_path = resolve_cli_path(args.dashboard)
    summary_path = resolve_cli_path(args.summary)
    should_refresh = bool(args.refresh)
    if dashboard_path.exists() and has_legacy_dashboard_markup(dashboard_path):
        should_refresh = True
    if dashboard_path.exists() and has_stale_dashboard_renderer(dashboard_path):
        should_refresh = True
    if dashboard_path.exists() and summary_path.exists() and dashboard_path.stat().st_mtime < summary_path.stat().st_mtime:
        should_refresh = True
    if not dashboard_path.exists() or should_refresh:
        if not summary_path.exists():
            if dashboard_path.exists():
                print("dashboard_cached_without_summary: " + str(dashboard_path))
            else:
                render_first_run_dashboard(dashboard_path)
                print(f"dashboard_first_run: {dashboard_path}")
            should_refresh = False
        if should_refresh:
            try:
                render_cached_dashboard(summary_path, dashboard_path)
            except dashboard_tool.DashboardError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            print(f"dashboard_refreshed: {dashboard_path}")
    else:
        print(f"dashboard_cached: {dashboard_path}")
    if not dashboard_path.exists():
        print("ERROR: dashboard was not created.", file=sys.stderr)
        return 1
    if args.open:
        webbrowser.open(dashboard_path.resolve().as_uri())
        print(f"dashboard_opened: {dashboard_path}")
    else:
        print(f"dashboard_html: {dashboard_path}")
    return 0


def run_demo(args: argparse.Namespace) -> int:
    summary = demo_tool.run_pipeline(
        images_dir=resolve_cli_path(args.images_dir) if args.images_dir else None,
        parsed_dir=resolve_cli_path(args.parsed_dir) if args.parsed_dir else None,
        manifest=resolve_cli_path(args.manifest) if args.manifest else None,
        output_dir=resolve_cli_path(args.output_dir),
        expected_dir=resolve_cli_path(args.expected_dir),
        engine=args.engine,
        game=args.game,
        layout=args.layout,
        open_dashboard=args.open,
        latest_only=args.latest_only,
        clean_demo=args.clean_demo,
        targets=resolve_cli_path(args.targets) if args.targets else None,
        new_only=args.new_only,
        state_file=resolve_cli_path(args.state_file) if args.state_file else None,
        history_dir=resolve_cli_path(args.history_dir) if args.history_dir else None,
        target_source_manifest=resolve_cli_path(args.target_source_manifest) if args.target_source_manifest else None,
        character_catalog=resolve_cli_path(args.character_catalog) if args.character_catalog else None,
        roster_dir=resolve_cli_path(args.roster_dir) if args.roster_dir else None,
        tier_snapshot=resolve_cli_path(args.tier_snapshot) if args.tier_snapshot else None,
        tier_stale_days=getattr(args, "tier_stale_days", 60),
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


def run_fresh(args: argparse.Namespace) -> int:
    if str(getattr(args, "command", "") or "").lower() == "update":
        print("update_scope: saved_official_share_images_only")
        print("update_note: 当前安全版只处理 figs 下已保存的官方分享图；不会自动操作米游社 APP。")
    images_dir = resolve_cli_path(args.images_dir)
    if not images_dir.exists() or not images_dir.is_dir():
        print(f"ERROR: local image directory does not exist: {images_dir}", file=sys.stderr)
        print("Put official share images under figs\\, then run MihoProbe.exe fresh.", file=sys.stderr)
        return 1
    summary = demo_tool.run_pipeline(
        images_dir=images_dir,
        parsed_dir=None,
        manifest=None,
        output_dir=resolve_cli_path(args.output_dir),
        expected_dir=resolve_cli_path(args.expected_dir),
        engine=args.engine,
        game=args.game,
        layout=args.layout,
        open_dashboard=args.open,
        latest_only=False,
        clean_demo=args.clean_demo,
        targets=resolve_cli_path(args.targets) if args.targets else None,
        new_only=not args.rescan_all,
        state_file=resolve_cli_path(args.state_file) if args.state_file else None,
        history_dir=resolve_cli_path(args.history_dir) if args.history_dir else None,
        target_source_manifest=resolve_cli_path(args.target_source_manifest) if args.target_source_manifest else None,
        character_catalog=resolve_cli_path(args.character_catalog) if args.character_catalog else None,
        roster_dir=resolve_cli_path(args.roster_dir) if args.roster_dir else None,
        tier_snapshot=resolve_cli_path(args.tier_snapshot) if args.tier_snapshot else None,
        tier_stale_days=args.tier_stale_days,
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    mode = "rescan_all" if args.rescan_all else "new_or_changed_only"
    print(f"fresh_mode: {mode}")
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


def write_plan_update_manifest(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "plan_update_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "p4.0-local-plan-update-manifest",
                "cases": [],
                "note": "No OCR input. This manifest only triggers local roster/targets/tier/dashboard recomputation.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def run_plan_update(args: argparse.Namespace) -> int:
    output_dir = resolve_cli_path(args.output_dir)
    if args.clean_demo:
        demo_tool.clean_demo_output_dir(output_dir)
    manifest_path = write_plan_update_manifest(output_dir)
    print("plan_update_scope: local_roster_targets_tier_only")
    print("plan_update_note: 不跑 OCR、不联网、不读取账号；只重算本地角色库、高难目标、Tier/保值观察和配队建议。")
    summary = demo_tool.run_pipeline(
        images_dir=None,
        parsed_dir=None,
        manifest=manifest_path,
        output_dir=output_dir,
        expected_dir=resolve_cli_path(args.expected_dir),
        engine="none",
        game=args.game,
        layout=args.layout,
        open_dashboard=args.open,
        latest_only=False,
        clean_demo=False,
        targets=resolve_cli_path(args.targets) if args.targets else None,
        new_only=False,
        state_file=None,
        history_dir=resolve_cli_path(args.history_dir) if args.history_dir else None,
        target_source_manifest=resolve_cli_path(args.target_source_manifest) if args.target_source_manifest else None,
        character_catalog=resolve_cli_path(args.character_catalog) if args.character_catalog else None,
        roster_dir=resolve_cli_path(args.roster_dir) if args.roster_dir else None,
        tier_snapshot=resolve_cli_path(args.tier_snapshot) if args.tier_snapshot else None,
        tier_stale_days=args.tier_stale_days,
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


def rank_region_specs() -> dict[str, Any]:
    return {spec.name: spec for spec in parse_probe.ZZZ_AGENT_CARD_REGIONS if spec.name in {"character_rank", "equipment_rank"}}


def image_files_in_dir(images_dir: Path) -> list[Path]:
    if not images_dir.exists() or not images_dir.is_dir():
        return []
    return sorted(path for path in images_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def safe_output_stem(path: Path) -> str:
    text = path.stem
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text) or "image"


def html_file_link(path: Path, label: str) -> str:
    try:
        href = path.resolve().as_uri()
    except ValueError:
        href = str(path)
    return f'<a href="{html_escape(href)}">{html_escape(label)}</a>'


def rank_check_entry(image_path: Path, output_dir: Path, *, game: str, layout: str) -> dict[str, Any]:
    Image = parse_probe.load_image_dependency()
    specs = rank_region_specs()
    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        regions = []
        for region_name, label in (("character_rank", "角色评级"), ("equipment_rank", "音擎评级")):
            spec = specs[region_name]
            box = parse_probe.ratio_box_to_pixels(spec.box_ratio, image.width, image.height)
            block = parse_probe.visual_rank_block_for_region(image, region_name=region_name, region_box=box)
            crop_path = crops_dir / f"{safe_output_stem(image_path)}_{region_name}.png"
            crop = image.crop((box["left"], box["top"], box["right"], box["bottom"])).convert("RGB")
            crop.save(crop_path)
            regions.append(
                {
                    "region": region_name,
                    "label": label,
                    "rank": block.get("text") if block else None,
                    "confidence": block.get("visual_rank_confidence") if block else 0.0,
                    "reason": block.get("visual_rank_reason") if block else "insufficient_color_signal",
                    "scores": block.get("visual_rank_scores") if block else parse_probe.visual_rank_color_scores(crop),
                    "box": box,
                    "crop": str(crop_path),
                    "status": "ok" if block and not block.get("uncertain") else "needs_review",
                }
            )
    status = "ok" if regions and all(item["status"] == "ok" for item in regions) else "needs_review"
    return {
        "image": str(image_path),
        "image_name": image_path.name,
        "game": game,
        "layout": layout,
        "status": status,
        "regions": regions,
    }


def render_rank_check_html(report: dict[str, Any]) -> str:
    entries = report.get("entries") if isinstance(report.get("entries"), list) else []
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        region_cards = []
        for region in entry.get("regions", []) if isinstance(entry.get("regions"), list) else []:
            if not isinstance(region, dict):
                continue
            crop = Path(str(region.get("crop") or ""))
            scores = region.get("scores") if isinstance(region.get("scores"), dict) else {}
            tone = "ok" if region.get("status") == "ok" else "warn"
            region_cards.append(
                f'<article class="region {tone}">'
                f'<img src="{html_escape(crop.resolve().as_uri())}" alt="{html_escape(str(region.get("label") or ""))}">'
                f'<div><span>{html_escape(str(region.get("label") or region.get("region") or ""))}</span>'
                f'<strong>{html_escape(str(region.get("rank") or "未识别"))}</strong>'
                f'<p>置信度 {html_escape(str(region.get("confidence")))} · {html_escape(str(region.get("reason") or ""))}</p>'
                f'<p>orange {html_escape(str(scores.get("orange", 0)))} / purple {html_escape(str(scores.get("purple", 0)))} / peak {html_escape(str(scores.get("orange_peak", 0)))} / {html_escape(str(scores.get("purple_peak", 0)))}</p>'
                f'<p>{html_file_link(crop, "打开 crop")}</p></div>'
                "</article>"
            )
        rows.append(
            '<section class="image-card">'
            f'<h2>{html_escape(str(entry.get("image_name") or ""))}</h2>'
            f'<p class="muted">只检测头像左上角角色评级、音擎右侧评级固定区域；不跑 OCR。</p>'
            f'<div class="regions">{"".join(region_cards)}</div>'
            "</section>"
        )
    body = "".join(rows) if rows else '<section class="image-card"><h2>没有图片</h2><p class="muted">请把官方分享图放到 figs/，或用 --images-dir 指向图片目录。</p></section>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>评级区域快检</title>
  <style>
    body {{ margin: 0; background: #f6f8fb; color: #172033; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; }}
    header {{ padding: 24px 28px; background: #101827; color: #fff; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; }}
    header p {{ margin: 0; color: #cbd5e1; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric, .image-card, .region {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08); }}
    .metric {{ padding: 14px; }}
    .metric span, .region span, .muted {{ color: #64748b; font-size: 13px; }}
    .metric strong, .region strong {{ display: block; margin-top: 4px; font-size: 24px; }}
    .image-card {{ padding: 16px; }}
    .image-card h2 {{ margin: 0 0 6px; font-size: 18px; overflow-wrap: anywhere; }}
    .regions {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-top: 12px; }}
    .region {{ display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 12px; padding: 12px; align-items: center; }}
    .region img {{ width: 96px; height: 86px; object-fit: contain; background: #111827; border-radius: 8px; }}
    .region p {{ margin: 5px 0 0; color: #64748b; font-size: 12px; overflow-wrap: anywhere; }}
    .region.ok strong {{ color: #16834a; }}
    .region.warn strong {{ color: #9a6500; }}
    a {{ color: #155399; text-decoration: none; font-weight: 700; }}
  </style>
</head>
<body>
  <header>
    <h1>评级区域快检</h1>
    <p>专门检查 A/S 艺术字固定区域：角色头像左上角、音擎评级区域。不跑 OCR，不接触账号数据。</p>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><span>图片数</span><strong>{html_escape(str(report.get("image_count", 0)))}</strong></div>
      <div class="metric"><span>识别成功区域</span><strong>{html_escape(str(report.get("ok_region_count", 0)))}</strong></div>
      <div class="metric"><span>需复核区域</span><strong>{html_escape(str(report.get("review_region_count", 0)))}</strong></div>
      <div class="metric"><span>模式</span><strong>视觉快检</strong></div>
    </section>
    {body}
  </main>
</body>
</html>
"""


def run_rank_check(args: argparse.Namespace) -> int:
    images_dir = resolve_cli_path(args.images_dir)
    output_dir = resolve_cli_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images = image_files_in_dir(images_dir)
    entries = [rank_check_entry(path, output_dir, game=args.game, layout=args.layout) for path in images]
    ok_region_count = sum(
        1
        for entry in entries
        for region in entry.get("regions", [])
        if isinstance(region, dict) and region.get("status") == "ok"
    )
    region_count = sum(len(entry.get("regions", [])) for entry in entries)
    report = {
        "schema_version": "p4.1-rank-region-check",
        "scope": "visual_rank_regions_only",
        "images_dir": str(images_dir),
        "game": args.game,
        "layout": args.layout,
        "image_count": len(entries),
        "region_count": region_count,
        "ok_region_count": ok_region_count,
        "review_region_count": region_count - ok_region_count,
        "entries": entries,
    }
    json_path = output_dir / "rank_check.json"
    html_path = output_dir / "rank_check.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_rank_check_html(report), encoding="utf-8")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())
    print("rank_check_scope: visual_rank_regions_only")
    print("rank_check_note: 不跑 OCR；只检查角色头像左上角和音擎评级固定区域的 A/S 艺术字颜色信号。")
    print(f"rank_check_html: {html_path}")
    print(f"rank_check_json: {json_path}")
    print(f"image_count: {len(entries)}")
    print(f"ok_region_count: {ok_region_count}")
    print(f"review_region_count: {region_count - ok_region_count}")
    return 0


def run_app_export(args: argparse.Namespace) -> int:
    output_dir = resolve_cli_path(args.output_dir)
    image_inbox = resolve_cli_path(args.image_inbox)
    result = app_export_workflow.build_package(
        output_dir=output_dir,
        image_inbox=image_inbox,
        game=args.game,
        window_title=args.window_title,
    )
    workflow = result["workflow"]
    validation = workflow["validation"] if isinstance(workflow, dict) else {}
    html_path = result["html_path"]
    json_path = result["json_path"]
    if args.open:
        webbrowser.open(Path(html_path).resolve().as_uri())
    print("app_export_scope: workflow_package_only")
    print("app_export_note: 不自动登录、不读取 token/cookie、不抓包、不控制游戏客户端；当前只生成官方 UI 工作流包。")
    print(f"workflow_status: {validation.get('status')}")
    print(f"workflow_html: {html_path}")
    print(f"workflow_json: {json_path}")
    return 0 if validation.get("status") != "blocked" else 1


def replay_default_output_dir() -> Path:
    stamp = datetime.now().astimezone().isoformat(timespec="seconds").replace(":", "").replace("+", "_").replace("-", "").replace("T", "_")
    return PROJECT_ROOT / "data" / "probes" / "replay_batches" / stamp


def replay_case_from_paths(parsed: str, expected: str, name: str | None = None) -> dict[str, str]:
    parsed_path = resolve_cli_path(parsed)
    expected_path = resolve_cli_path(expected)
    return {
        "name": name or parsed_path.stem,
        "parsed": str(parsed_path),
        "expected": str(expected_path),
    }


def load_replay_manifest(path: Path) -> list[dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliReplayError(f"Replay manifest is invalid JSON: {path}. Details: {exc}") from exc
    if isinstance(data, list):
        raw_cases = data
    elif isinstance(data, dict):
        raw_cases = data.get("cases")
    else:
        raw_cases = None
    if not isinstance(raw_cases, list):
        raise CliReplayError("Replay manifest must be a list or an object with a 'cases' list")
    cases: list[dict[str, str]] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise CliReplayError(f"Manifest case #{index} must be an object")
        parsed = item.get("parsed")
        expected = item.get("expected")
        if not parsed or not expected:
            raise CliReplayError(f"Manifest case #{index} must include parsed and expected")
        cases.append(replay_case_from_paths(str(parsed), str(expected), str(item.get("name") or f"case_{index}")))
    return cases


def build_replay_cases(args: argparse.Namespace) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    has_inline_cases = bool(args.case or args.parsed or args.expected)
    manifest_value = args.manifest
    if not manifest_value and not has_inline_cases:
        manifest_value = DEFAULT_REPLAY_MANIFEST
    if manifest_value:
        manifest_path = resolve_cli_path(manifest_value)
        if not manifest_path.exists():
            raise CliReplayError(f"Replay manifest does not exist: {manifest_path}")
        cases.extend(load_replay_manifest(manifest_path))
    for value in args.case or []:
        if "=" not in value:
            raise CliReplayError("--case must use parsed.json=expected.json")
        parsed, expected = value.split("=", 1)
        cases.append(replay_case_from_paths(parsed.strip(), expected.strip()))
    parsed_values = args.parsed or []
    expected_values = args.expected or []
    if parsed_values or expected_values:
        if len(parsed_values) != len(expected_values):
            raise CliReplayError("--parsed and --expected must be provided in equal counts")
        for parsed, expected in zip(parsed_values, expected_values):
            cases.append(replay_case_from_paths(parsed, expected))
    if not cases:
        raise CliReplayError("Provide at least one replay case or manifest")
    return cases


def run_replay(args: argparse.Namespace) -> int:
    try:
        cases = build_replay_cases(args)
        output_dir = resolve_cli_path(args.output_dir) if args.output_dir else replay_default_output_dir()
        replay_tool = load_replay_tool()
        summary = replay_tool.run_batch(
            cases,
            output_dir=output_dir,
            loose_numeric_text=not args.strict_leading_zero,
            rebuild=not args.no_rebuild,
        )
    except CliReplayError as exc:
        message = str(exc)
        if "Replay manifest does not exist" in message:
            manifest_path = resolve_cli_path(args.manifest) if args.manifest else DEFAULT_REPLAY_MANIFEST
            guide_path = DEFAULT_DEMO_OUTPUT_DIR / "accuracy_check_missing_manifest.html"
            render_missing_replay_manifest_page(manifest_path, guide_path)
            if args.open:
                webbrowser.open(guide_path.resolve().as_uri())
                print(f"accuracy_check_help_opened: {guide_path}")
            print("准确率验收：缺少样例清单", file=sys.stderr)
            print(f"missing_manifest: {manifest_path}", file=sys.stderr)
            print(f"help_html: {guide_path}", file=sys.stderr)
            print("下一步：补齐 data\\probes\\replay_manifest.json，或用 --case parsed.json=expected.json 指定单次验收。", file=sys.stderr)
            return 1
        print(f"ERROR: {exc}", file=sys.stderr)
        print("准确率验收入口：MihoProbe.exe replay --manifest data\\probes\\replay_manifest.json", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("准确率验收入口：MihoProbe.exe replay --manifest data\\probes\\replay_manifest.json", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("准确率验收入口：MihoProbe.exe replay --manifest data\\probes\\replay_manifest.json", file=sys.stderr)
        return 1
    p0_9 = summary["p0_9"]
    passed = bool(p0_9["meets_p0_9_batch_standard"])
    print("准确率验收：" + ("通过" if passed else "未通过"))
    print(f"case_count: {p0_9['case_count']}")
    print(f"average_pass_rate: {p0_9['average_pass_rate_percent']}%")
    print(f"meets_p0_9_batch_standard: {p0_9['meets_p0_9_batch_standard']}")
    if p0_9.get("blockers"):
        print("blockers:")
        for blocker in p0_9["blockers"]:
            print(f"- {blocker}")
    print(f"summary_md: {summary['summary_md']}")
    print(f"summary_json: {summary['summary_json']}")
    if args.open:
        webbrowser.open(Path(summary["summary_md"]).resolve().as_uri())
        print(f"summary_opened: {summary['summary_md']}")
    return 0 if passed else 1


def run_normalize(args: argparse.Namespace) -> int:
    result = normalize_tool.normalize_file(
        resolve_cli_path(args.parsed),
        resolve_cli_path(args.output_dir) if args.output_dir else DEFAULT_NORMALIZED_DIR,
    )
    print(f"normalized_json: {result['normalized_json']}")
    print(f"normalized_md: {result['normalized_md']}")
    return 0


def run_diff(args: argparse.Namespace) -> int:
    result = diff_tool.diff_files(
        resolve_cli_path(args.old),
        resolve_cli_path(args.new),
        resolve_cli_path(args.output_dir) if args.output_dir else None,
    )
    print(f"diff_json: {result['output_json']}")
    print(f"diff_md: {result['output_md']}")
    return 0


def run_plan(args: argparse.Namespace) -> int:
    snapshot_paths = [resolve_cli_path(path) for path in args.snapshot]
    if args.snapshot_manifest:
        snapshot_paths.extend(planner_tool.load_manifest_snapshots(resolve_cli_path(args.snapshot_manifest)))
    report = planner_tool.generate_report(
        snapshot_paths,
        resolve_cli_path(args.targets),
        resolve_cli_path(args.output_dir),
        history_index=resolve_cli_path(args.history_index) if args.history_index else None,
        character_catalog=resolve_cli_path(args.character_catalog) if args.character_catalog else None,
        daily_stamina=args.daily_stamina,
        horizon_days=args.horizon_days,
    )
    print(f"plan_item_count: {len(report['plan_items'])}")
    print(f"output_json: {report['output_json']}")
    print(f"output_md: {report['output_md']}")
    return 0


def run_targets(args: argparse.Namespace) -> int:
    try:
        if args.manifest and (args.url or args.input):
            raise target_tool.TargetIntakeError("--manifest cannot be combined with --url or --input")
        if args.manifest:
            game, source_type, sources, defaults = target_tool.source_cases_from_manifest(resolve_cli_path(args.manifest))
        else:
            game, source_type, sources, defaults = target_tool.source_cases_from_args(args)
        targets = target_tool.prepare_targets(
            game=game,
            source_type=source_type,
            sources=sources,
            output_dir=resolve_cli_path(args.output_dir),
            manifest_defaults=defaults,
        )
    except target_tool.TargetIntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"target_count: {len(targets['targets'])}")
    print(f"source_count: {len(targets['sources'])}")
    freshness = targets.get("freshness", {}) if isinstance(targets.get("freshness"), dict) else {}
    print(f"freshness_level: {freshness.get('level', 'unknown')}")
    print(f"stale_source_count: {freshness.get('stale_source_count', 0)}")
    for warning in targets.get("warnings", []):
        print(f"warning: {warning}")
    print(f"output_json: {targets['output_json']}")
    return 0


def run_gpt_review(args: argparse.Namespace) -> int:
    prompt = gpt_prompt_tool.render_prompt(
        focus=args.focus,
        evidence=args.evidence,
        changed_files=args.changed_file,
        questions=args.question,
        constraints=args.constraint,
        include_git_status=not args.no_git_status,
    )
    if args.output:
        output_path = resolve_cli_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(prompt, encoding="utf-8")
        print(f"gpt_review_prompt: {output_path}")
    else:
        sys.stdout.write(prompt)
    return 0


def add_fresh_update_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--images-dir", default=str(DEFAULT_FIGS_DIR), help="Image directory. Default: figs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_DEMO_OUTPUT_DIR), help="Output directory.")
    parser.add_argument("--expected-dir", default=str(DEFAULT_EXPECTED_DIR), help="Expected JSON directory.")
    parser.add_argument("--engine", choices=("auto", "tesseract", "paddle", "rapidocr", "none"), default="paddle")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated dashboard. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the dashboard.")
    parser.add_argument("--rescan-all", action="store_true", help="Rescan every image instead of only new or changed images.")
    parser.add_argument("--clean-demo", action="store_true", help="Clean the demo output directory before running. Limited to data/probes subdirectories.")
    parser.add_argument("--state-file", default=None, help="Image update state JSON. Default: <output-dir>/update_state.json.")
    parser.add_argument("--targets", default=None, help="Optional planner targets JSON. Generates a local training priority report.")
    parser.add_argument("--target-source-manifest", default=None, help="Optional public/local endgame source manifest. Generates targets before planner.")
    parser.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for planner target matching.")
    parser.add_argument("--roster-dir", default=str(DEFAULT_ROSTER_DIR), help="Local accepted roster directory. Default: data/probes/roster.")
    parser.add_argument("--tier-snapshot", default=None, help="Optional local tier/value snapshot JSON. Does not fetch network data.")
    parser.add_argument("--tier-stale-days", type=int, default=60, help="Mark tier sources older than this many days as stale. Default: 60.")
    parser.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    parser.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget for planner. Default: 240.")
    parser.add_argument("--horizon-days", type=float, default=None, help="Planner horizon in days. Default: 7.")


def add_replay_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", default=None, help="Replay manifest. Default when no inline cases are provided: data/probes/replay_manifest.json.")
    parser.add_argument("--case", action="append", help="Replay case as parsed.json=expected.json. Can be repeated.")
    parser.add_argument("--parsed", action="append", help="Parsed JSON path. Pair with --expected; can be repeated.")
    parser.add_argument("--expected", action="append", help="Expected JSON path. Pair with --parsed; can be repeated.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Default: data/probes/replay_batches/<timestamp>.")
    parser.add_argument("--strict-leading-zero", action="store_true", help="Treat numeric text such as '08' and '8' as different.")
    parser.add_argument("--no-rebuild", action="store_true", help="Compare stored extracted_draft as-is instead of rebuilding from text_blocks.")
    parser.add_argument("--open", action="store_true", default=True, help="Open the Markdown summary. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the Markdown summary.")


def add_plan_update_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default=str(DEFAULT_DEMO_OUTPUT_DIR), help="Output directory.")
    parser.add_argument("--expected-dir", default=str(DEFAULT_EXPECTED_DIR), help="Expected JSON directory.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated dashboard. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the dashboard.")
    parser.add_argument("--clean-demo", action="store_true", help="Clean demo output before local recompute. Limited to data/probes subdirectories.")
    parser.add_argument("--targets", default=None, help="Optional planner targets JSON.")
    parser.add_argument("--target-source-manifest", default=None, help="Optional public/local endgame source manifest. Generates targets before planner.")
    parser.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for planner target matching.")
    parser.add_argument("--roster-dir", default=str(DEFAULT_ROSTER_DIR), help="Local accepted roster directory. Default: data/probes/roster.")
    parser.add_argument("--tier-snapshot", default=None, help="Optional local tier/value snapshot JSON. Does not fetch network data.")
    parser.add_argument("--tier-stale-days", type=int, default=60, help="Mark tier sources older than this many days as stale. Default: 60.")
    parser.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    parser.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget for planner. Default: 240.")
    parser.add_argument("--horizon-days", type=float, default=None, help="Planner horizon in days. Default: 7.")


def add_rank_check_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--images-dir", default=str(DEFAULT_FIGS_DIR), help="Image directory. Default: figs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_RANK_CHECK_DIR), help="Output directory. Default: data/probes/demo/rank_check.")
    parser.add_argument("--game", choices=("zzz",), default="zzz")
    parser.add_argument("--layout", choices=("zzz-agent-card",), default="zzz-agent-card")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated HTML. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the HTML report.")


def add_app_export_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default=str(DEFAULT_APP_EXPORT_WORKFLOW_DIR), help="Output directory.")
    parser.add_argument("--image-inbox", default=str(DEFAULT_FIGS_DIR), help="Where official share images should land. Default: figs.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--window-title", default="米游社", help="Target app window title keyword.")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated HTML. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the HTML report.")


def add_gpt_review_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--focus", required=True, help="本轮要推进的用户可见目标。")
    parser.add_argument("--evidence", action="append", default=[], help="关键证据，可重复。")
    parser.add_argument("--changed-file", action="append", default=[], help='已改文件，可写 "path: 改了什么"，可重复。')
    parser.add_argument("--question", action="append", default=[], help="额外请审问题，可重复；不传则使用默认问题。")
    parser.add_argument("--constraint", action="append", default=[], help="额外约束，可重复。")
    parser.add_argument("--no-git-status", action="store_true", help="不要自动附带 git status --short。")
    parser.add_argument("--output", default=None, help="可选输出路径；不传则打印到 stdout。")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Miho probe command shell.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dashboard = subparsers.add_parser("dashboard", help="Open the cached local dashboard without rerunning OCR.")
    dashboard.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD_HTML), help="Dashboard HTML path.")
    dashboard.add_argument("--summary", default=str(DEFAULT_DEMO_SUMMARY), help="Demo summary JSON used to refresh cached HTML.")
    dashboard.add_argument("--refresh", action="store_true", help="Force refresh from summary before opening.")
    dashboard.add_argument("--open", action="store_true", default=True, help="Open the dashboard in the default browser. Default: true.")
    dashboard.add_argument("--no-open", action="store_false", dest="open", help="Render/check only; do not open a browser.")
    dashboard.set_defaults(handler=run_dashboard)

    demo = subparsers.add_parser("demo", help="Run the local demo pipeline and render a dashboard.")
    source = demo.add_mutually_exclusive_group()
    source.add_argument("--images-dir", default=None, help="Image directory. Default is figs when no source is provided.")
    source.add_argument("--parsed-dir", default=None, help="Parsed JSON directory. Does not rerun OCR.")
    source.add_argument("--manifest", default=None, help="Demo manifest with image or parsed cases.")
    demo.add_argument("--output-dir", default=str(DEFAULT_DEMO_OUTPUT_DIR), help="Output directory.")
    demo.add_argument("--expected-dir", default=str(DEFAULT_EXPECTED_DIR), help="Expected JSON directory.")
    demo.add_argument("--engine", choices=("auto", "tesseract", "paddle", "rapidocr", "none"), default="paddle")
    demo.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    demo.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card")
    demo.add_argument("--open", action="store_true", help="Open generated dashboard.")
    demo.add_argument("--latest-only", action="store_true", help="In parsed-dir mode, keep only the newest parsed JSON for each source image.")
    demo.add_argument("--new-only", action="store_true", help="In image mode, process only new or changed images according to the update state file.")
    demo.add_argument("--clean-demo", action="store_true", help="Clean the demo output directory before running. Limited to data/probes subdirectories.")
    demo.add_argument("--state-file", default=None, help="Image update state JSON. Default: <output-dir>/update_state.json.")
    demo.add_argument("--targets", default=None, help="Optional planner targets JSON. Generates a local training priority report.")
    demo.add_argument("--target-source-manifest", default=None, help="Optional public/local endgame source manifest. Generates targets before planner.")
    demo.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for planner target matching.")
    demo.add_argument("--roster-dir", default=str(DEFAULT_ROSTER_DIR), help="Local accepted roster directory. Default: data/probes/roster.")
    demo.add_argument("--tier-snapshot", default=None, help="Optional local tier/value snapshot JSON. Does not fetch network data.")
    demo.add_argument("--tier-stale-days", type=int, default=60, help="Mark tier sources older than this many days as stale. Default: 60.")
    demo.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    demo.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget for planner. Default: 240.")
    demo.add_argument("--horizon-days", type=float, default=None, help="Planner horizon in days. Default: 7.")
    demo.set_defaults(handler=run_demo)

    update = subparsers.add_parser("update", help="One-click local practice update from saved official share images under figs.")
    add_fresh_update_args(update)
    update.set_defaults(handler=run_fresh)

    app_export = subparsers.add_parser("app-export", help="Build the official MiYouShe share-image export workflow package.")
    add_app_export_args(app_export)
    app_export.set_defaults(handler=run_app_export)

    fresh = subparsers.add_parser("fresh", help="Developer alias for update: run fresh OCR for official share images under figs.")
    add_fresh_update_args(fresh)
    fresh.set_defaults(handler=run_fresh)

    check = subparsers.add_parser("check", help="Run accuracy acceptance without OCR.")
    add_replay_args(check)
    check.set_defaults(handler=run_replay)

    replay = subparsers.add_parser("replay", help="Developer alias for check: run parsed-vs-expected replay acceptance without OCR.")
    add_replay_args(replay)
    replay.set_defaults(handler=run_replay)

    plan_update = subparsers.add_parser("plan-update", help="One-click local endgame/Tier/team suggestion update without OCR.")
    add_plan_update_args(plan_update)
    plan_update.set_defaults(handler=run_plan_update)

    rank_check = subparsers.add_parser("rank-check", help="Check fixed A/S visual rank regions without OCR.")
    add_rank_check_args(rank_check)
    rank_check.set_defaults(handler=run_rank_check)

    normalize = subparsers.add_parser("normalize", help="Normalize one parsed JSON.")
    normalize.add_argument("--parsed", required=True, help="Parsed JSON path.")
    normalize.add_argument("--output-dir", default=None, help="Output directory.")
    normalize.set_defaults(handler=run_normalize)

    diff = subparsers.add_parser("diff", help="Diff two normalized snapshots.")
    diff.add_argument("--old", required=True, help="Old normalized JSON.")
    diff.add_argument("--new", required=True, help="New normalized JSON.")
    diff.add_argument("--output-dir", default=None, help="Output directory.")
    diff.set_defaults(handler=run_diff)

    plan = subparsers.add_parser("plan", help="Generate a local training priority report from normalized snapshots.")
    plan.add_argument("--snapshot", action="append", default=[], help="Normalized snapshot JSON. Can be repeated.")
    plan.add_argument("--snapshot-manifest", default=None, help="JSON manifest containing a snapshots list.")
    plan.add_argument("--targets", required=True, help="Local endgame target configuration JSON.")
    plan.add_argument("--history-index", default=None, help="Optional snapshot_history/index.json for long-term continuity context.")
    plan.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for target matching.")
    plan.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget. Default: 240.")
    plan.add_argument("--horizon-days", type=float, default=None, help="Planning horizon in days. Default: 7.")
    plan.add_argument("--output-dir", default=str(DEFAULT_PLANNER_DIR), help="Output directory.")
    plan.set_defaults(handler=run_plan)

    targets = subparsers.add_parser("targets", help="Prepare local planner target JSON from public endgame sources.")
    targets.add_argument("--manifest", default=None, help="JSON manifest containing game/source_type/sources.")
    targets.add_argument("--url", action="append", default=[], help="Public http(s) source URL. Can be repeated.")
    targets.add_argument("--input", action="append", default=[], help="Saved public text/HTML source file. Can be repeated.")
    targets.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    targets.add_argument(
        "--source-type",
        choices=("manual", "public_web_snapshot", "official_snapshot", "official_current", "mock"),
        default="public_web_snapshot",
    )
    targets.add_argument("--activity-name", default=None)
    targets.add_argument("--target-tier", default="待确认")
    targets.add_argument("--priority", choices=("high", "medium", "low"), default="medium")
    targets.add_argument("--preferred-character", action="append", default=[])
    targets.add_argument("--mechanic-tag", action="append", default=[])
    targets.add_argument("--weakness-tag", action="append", default=[])
    targets.add_argument("--character-level", default=60)
    targets.add_argument("--equipment-level", default=60)
    targets.add_argument("--skill-level", default=8)
    targets.add_argument("--drive-disc-level", default=12)
    targets.add_argument("--stat", action="append", default=[], help="Minimum stat in key=value form, e.g. atk=2000.")
    targets.add_argument("--max-source-age-hours", type=float, default=target_tool.DEFAULT_MAX_SOURCE_AGE_HOURS)
    targets.add_argument("--output-dir", default=str(DEFAULT_TARGETS_DIR), help="Output directory.")
    targets.set_defaults(handler=run_targets)

    ask_gpt = subparsers.add_parser("ask-gpt", help="Build the fixed review packet for the right-side GPT.")
    add_gpt_review_args(ask_gpt)
    ask_gpt.set_defaults(handler=run_gpt_review)

    gpt_review = subparsers.add_parser("gpt-review", help="Developer alias for ask-gpt.")
    add_gpt_review_args(gpt_review)
    gpt_review.set_defaults(handler=run_gpt_review)
    return parser


def main() -> int:
    if should_show_top_level_help(sys.argv):
        sys.stdout.write(render_user_help())
        return 0
    if len(sys.argv) == 1:
        args = argparse.Namespace(
            dashboard=str(DEFAULT_DASHBOARD_HTML),
            summary=str(DEFAULT_DEMO_SUMMARY),
            refresh=False,
            open=True,
        )
        return run_dashboard(args)
    parser = build_arg_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
