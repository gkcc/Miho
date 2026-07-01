#!/usr/bin/env python
"""Small command shell for local Miho probe workflows."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape as html_escape
import importlib
import importlib.util
import json
import sys
import webbrowser
from pathlib import Path
from types import ModuleType
from typing import Any


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - stdio can be a PyInstaller or test harness wrapper.
            pass


configure_stdio()


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


class LazyModule:
    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._module: ModuleType | None = None

    def load(self) -> ModuleType:
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self.load(), name)


diff_tool = LazyModule("diff_normalized_snapshots")
gpt_prompt_tool = LazyModule("build_gpt_review_prompt")
parse_probe = LazyModule("export_image_parse_probe")
app_export_workflow = LazyModule("miyoushe_export_workflow")
app_export_runner = LazyModule("miyoushe_app_export_runner")
app_export_calibrator = LazyModule("miyoushe_app_export_calibrator")
normalize_tool = LazyModule("normalize_export_parse")
planner_tool = LazyModule("plan_training_priorities")
target_tool = LazyModule("prepare_endgame_targets")
dashboard_tool = LazyModule("render_demo_dashboard")
demo_tool = LazyModule("run_demo_pipeline")
box_roster_tool = LazyModule("extract_zzz_box_roster")
box_value_tool = LazyModule("run_zzz_box_value_pipeline")


def detect_project_root() -> Path:
    candidates = [Path.cwd().resolve(), Path(sys.executable).resolve().parent, Path(__file__).resolve().parent]
    for base in candidates:
        for candidate in (base, *base.parents):
            if (candidate / "README.md").exists() and (candidate / "tools" / "probes").exists():
                return candidate
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = detect_project_root()
PROJECT_PROBES_DIR = PROJECT_ROOT / "tools" / "probes"
if PROJECT_PROBES_DIR.exists() and str(PROJECT_PROBES_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_PROBES_DIR))
DEFAULT_DEMO_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_DASHBOARD_HTML = DEFAULT_DEMO_OUTPUT_DIR / "index.html"
DEFAULT_DEMO_SUMMARY = DEFAULT_DEMO_OUTPUT_DIR / "demo_summary.json"
DEFAULT_GPT_REVIEW_PROMPT = DEFAULT_DEMO_OUTPUT_DIR / "gpt_review_prompt.md"
DEFAULT_FIGS_DIR = PROJECT_ROOT / "figs"
DEFAULT_APP_EXPORT_WORKFLOW_DIR = DEFAULT_DEMO_OUTPUT_DIR / "app_export_workflow"
APP_EXPORT_WORKFLOW_FILENAME = "miyoushe_export_workflow.json"
APP_EXPORT_CALIBRATION_FILENAME = "miyoushe_app_export_calibration_template.json"
APP_EXPORT_RUN_REPORT_FILENAME = "miyoushe_app_export_run_report.json"
APP_EXPORT_CALIBRATION_REPORT_FILENAME = "miyoushe_app_export_calibration_report.json"
DEFAULT_EXPECTED_DIR = PROJECT_ROOT / "data" / "probes" / "expected"
DEFAULT_ROSTER_DIR = PROJECT_ROOT / "data" / "probes" / "roster"
DEFAULT_NORMALIZED_DIR = PROJECT_ROOT / "data" / "probes" / "normalized"
DEFAULT_PLANNER_DIR = PROJECT_ROOT / "data" / "probes" / "planner"
DEFAULT_TARGETS_DIR = PROJECT_ROOT / "data" / "probes" / "targets"
DEFAULT_BOX_DIR = PROJECT_ROOT / "data" / "probes" / "box"
DEFAULT_BOX_VALUE_DIR = PROJECT_ROOT / "data" / "probes" / "value" / "box_value_pipeline"
DEFAULT_EXPORTED_IMAGES_DIR = PROJECT_ROOT / "data" / "probes" / "exported_images"
DEFAULT_META_DIR = PROJECT_ROOT / "data" / "probes" / "meta"
DEFAULT_BOX_STATUS_DIR = DEFAULT_DEMO_OUTPUT_DIR / "box_value_status"
DEFAULT_REPLAY_MANIFEST = PROJECT_ROOT / "data" / "probes" / "replay_manifest.json"
DEFAULT_RANK_CHECK_DIR = DEFAULT_DEMO_OUTPUT_DIR / "rank_check"
DEFAULT_MAX_SOURCE_AGE_HOURS = 168
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


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def frozen_ocr_dependency_error(engine: str) -> str | None:
    if not is_frozen_runtime() or engine != "paddle":
        return None
    try:
        parse_probe.load_paddle_dependency()
    except Exception as exc:  # noqa: BLE001 - report the frozen dependency boundary clearly.
        detail = str(exc) or exc.__class__.__name__
        return (
            "PaddleOCR runtime is not available inside this MihoProbe.exe build. "
            "Use the Python command for OCR fresh/update, or rebuild the EXE with OCR dependencies. "
            f"Details: {detail}"
        )
    return None


class CliReplayError(RuntimeError):
    pass


def render_user_help() -> str:
    return """MihoProbe 本地体验入口

最常用：
  MihoProbe.exe
    打开已有 Dashboard，不跑图片识别。验收界面优先点这个。

  MihoProbe.exe update
    一键更新练度（当前安全版）：处理 figs\\ 下已保存的官方分享图，然后打开 Dashboard。

  MihoProbe.exe app-export
    生成米游社 APP 官方分享图工作流包。默认不点击，只沉淀一键更新练度的可审计步骤。

  MihoProbe.exe app-export-calibrate
    捕获米游社窗口网格截图，告诉你每一步该填哪个 x/y 坐标。默认不点击。

  MihoProbe.exe app-export-run
    运行米游社 APP 导出校准清单。默认 dry-run；真正点击必须加 --execute --confirm-official-ui。

  MihoProbe.exe fresh
    update 的开发别名：识别 figs\\ 下新增或变更的官方分享图。会加载图片识别模型，可能慢。

  MihoProbe.exe check --no-open
    用人工对照答案验收解析准确率。不重新图片识别。

  MihoProbe.exe plan-update
    一键更新高难/Tier/配队建议（安全版）：默认不图片识别、不联网；显式 source manifest 只访问公开来源。

  MihoProbe.exe box-roster --image data\\probes\\exported_images\\zzz_box.png
    从米游社官方 box 总览图生成脱敏 roster probe。人工确认前不能进入 accepted roster。

  MihoProbe.exe box-value --box-image data\\probes\\exported_images\\zzz_box.png --meta-snapshot data\\probes\\meta\\zzz_prydwen_meta_all_phases.json
    用本地 box 图或 roster JSON 加公开 Prydwen meta 生成账号内价值报告。

  MihoProbe.exe box-status
    只读检查本地 box 图片、公开 meta、roster probe 和价值报告输出，并生成下一步命令页。

  MihoProbe.exe rank-check
    只检查头像/音擎 A/S 艺术字固定区域。不跑图片识别，用来排查评级识别。

  MihoProbe.exe ask-gpt --focus "本轮要审的问题" --copy
    生成并复制给右侧 GPT 的固定审查包。只手动粘贴，不让 Codex 自动点右侧页面。

先别踩坑：
  - 只看界面，不要跑图片识别慢路径。
  - 慢路径卡住时先关掉，改用 MihoProbe.exe 看缓存 Dashboard。
  - 图片识别结果只进人工复核，不会直接写正式数据库。

开发细参：
  MihoProbe.exe dashboard --help
  MihoProbe.exe app-export --help
  MihoProbe.exe app-export-calibrate --help
  MihoProbe.exe plan-update --help
  MihoProbe.exe box-roster --help
  MihoProbe.exe box-value --help
  MihoProbe.exe box-status --help
  MihoProbe.exe rank-check --help
  MihoProbe.exe fresh --help
  MihoProbe.exe replay --help
  MihoProbe.exe ask-gpt --help
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


def has_newer_rank_check_report(summary_path: Path, dashboard_path: Path) -> bool:
    if not summary_path.exists() or not dashboard_path.exists():
        return False
    dashboard_mtime = dashboard_path.stat().st_mtime
    rank_check_dir = summary_path.parent / "rank_check"
    for report_path in (rank_check_dir / "rank_check.json", rank_check_dir / "rank_check.html"):
        if report_path.exists() and dashboard_mtime < report_path.stat().st_mtime:
            return True
    return False


def has_newer_app_export_workflow(summary_path: Path, dashboard_path: Path) -> bool:
    if not summary_path.exists() or not dashboard_path.exists():
        return False
    dashboard_mtime = dashboard_path.stat().st_mtime
    workflow_dir = summary_path.parent / "app_export_workflow"
    for report_path in (
        workflow_dir / APP_EXPORT_WORKFLOW_FILENAME,
        workflow_dir / "miyoushe_export_workflow.html",
        workflow_dir / APP_EXPORT_CALIBRATION_FILENAME,
        workflow_dir / APP_EXPORT_CALIBRATION_REPORT_FILENAME,
        workflow_dir / "miyoushe_app_export_calibration_report.html",
        workflow_dir / APP_EXPORT_RUN_REPORT_FILENAME,
        workflow_dir / "miyoushe_app_export_run_report.html",
    ):
        if report_path.exists() and dashboard_mtime < report_path.stat().st_mtime:
            return True
    return False


def load_cached_app_export_readiness(summary_path: Path) -> dict[str, Any] | None:
    workflow_path = summary_path.parent / "app_export_workflow" / APP_EXPORT_WORKFLOW_FILENAME
    if not workflow_path.exists():
        return None
    try:
        package = dashboard_tool.load_json(workflow_path)
    except Exception:  # noqa: BLE001 - stale local workflow packages should not block opening the dashboard.
        return None
    workflow = package.get("workflow") if isinstance(package.get("workflow"), dict) else {}
    validation = package.get("validation") if isinstance(package.get("validation"), dict) else {}
    route = workflow.get("operator_route") if isinstance(workflow.get("operator_route"), dict) else {}
    workflow_html = workflow_path.with_suffix(".html")
    workflow_dir = workflow_path.parent
    calibration_template = workflow_dir / APP_EXPORT_CALIBRATION_FILENAME
    calibration_report_json = workflow_dir / APP_EXPORT_CALIBRATION_REPORT_FILENAME
    calibration_report_html = workflow_dir / "miyoushe_app_export_calibration_report.html"
    run_report_json = workflow_dir / APP_EXPORT_RUN_REPORT_FILENAME
    run_report_html = workflow_dir / "miyoushe_app_export_run_report.html"
    calibration_report: dict[str, Any] | None = None
    if calibration_report_json.exists():
        try:
            candidate = dashboard_tool.load_json(calibration_report_json)
        except Exception:  # noqa: BLE001 - stale local calibration reports should not block the dashboard.
            candidate = None
        if isinstance(candidate, dict):
            calibration_report = candidate
    run_report: dict[str, Any] | None = None
    if run_report_json.exists():
        try:
            candidate = dashboard_tool.load_json(run_report_json)
        except Exception:  # noqa: BLE001 - stale local runner reports should not block the dashboard.
            candidate = None
        if isinstance(candidate, dict):
            run_report = candidate
    readiness: dict[str, Any] = {
        "status": (run_report.get("status") if run_report else None) or validation.get("status") or "unknown",
        "workflow_json": str(workflow_path),
        "route_status": route.get("current_route_status") or "unknown",
        "automation_status": route.get("automation_status") or "unknown",
        "next_command": route.get("next_command") or "",
        "update_command": route.get("update_command") or "",
        "review_gate": route.get("review_gate") or "",
        "manual_save_to_figs_step": route.get("manual_save_to_figs_step") or "",
        "readiness_gate_count": validation.get("readiness_gate_count", 0),
        "planned_step_count": validation.get("planned_step_count", 0),
        "implemented_step_count": validation.get("implemented_step_count", 0),
        "warnings": validation.get("warnings") if isinstance(validation.get("warnings"), list) else [],
        "forbidden_boundaries": workflow.get("does_not") if isinstance(workflow.get("does_not"), list) else [],
        "route_steps": route.get("route_steps") if isinstance(route.get("route_steps"), list) else [],
        "calibrate_command": route.get("calibrate_command") or "",
        "dry_run_command": route.get("dry_run_command") or route.get("next_command") or "",
        "execute_command": route.get("execute_command") or "",
    }
    if workflow_html.exists():
        readiness["workflow_html"] = str(workflow_html)
    if calibration_template.exists():
        readiness["calibration_template_json"] = str(calibration_template)
    if calibration_report:
        readiness["calibration_status"] = calibration_report.get("status") or "unknown"
        readiness["calibration_next_action"] = calibration_report.get("next_action") or ""
        readiness["calibration_report_json"] = str(calibration_report_json)
        if calibration_report_html.exists():
            readiness["calibration_report_html"] = str(calibration_report_html)
        screenshot = calibration_report.get("screenshot") if isinstance(calibration_report.get("screenshot"), dict) else {}
        if screenshot.get("path"):
            readiness["calibration_screenshot"] = screenshot.get("path")
    if run_report:
        readiness["runner_status"] = run_report.get("status") or "unknown"
        readiness["operator_status"] = run_report.get("operator_status") or ""
        readiness["status_label"] = run_report.get("status_label") or ""
        readiness["headline"] = run_report.get("headline") or ""
        readiness["next_command"] = run_report.get("next_command") or readiness.get("next_command") or ""
        readiness["saved_image_count"] = run_report.get("saved_image_count", 0)
        readiness["operator_route"] = run_report.get("operator_route") if isinstance(run_report.get("operator_route"), list) else []
        readiness["safety_boundary"] = (
            run_report.get("safety_boundary") if isinstance(run_report.get("safety_boundary"), list) else readiness.get("forbidden_boundaries", [])
        )
        gates = run_report.get("gates") if isinstance(run_report.get("gates"), dict) else {}
        if gates:
            readiness["runner_gates"] = gates
        preflight_checks = run_report.get("preflight_checks") if isinstance(run_report.get("preflight_checks"), list) else []
        if preflight_checks:
            readiness["preflight_checks"] = preflight_checks
        readiness["runner_next_action"] = run_report.get("next_action") or ""
        validation_report = run_report.get("validation") if isinstance(run_report.get("validation"), dict) else {}
        readiness["runner_missing_coordinate_count"] = validation_report.get("missing_coordinate_count", 0)
        readiness["runner_unconfirmed_step_count"] = validation_report.get("unconfirmed_step_count", 0)
        readiness["runner_clicked_count"] = run_report.get("clicked_count", 0)
        readiness["runner_report_json"] = str(run_report_json)
        if run_report_html.exists():
            readiness["runner_report_html"] = str(run_report_html)
    return readiness


def render_cached_dashboard(summary_path: Path, dashboard_path: Path) -> dict[str, str]:
    summary = dashboard_tool.load_json(summary_path)
    rank_check_json = summary_path.parent / "rank_check" / "rank_check.json"
    rank_check_html = summary_path.parent / "rank_check" / "rank_check.html"
    if rank_check_json.exists() and isinstance(summary, dict) and "rank_check" not in summary:
        try:
            rank_check = dashboard_tool.load_json(rank_check_json)
        except Exception:  # noqa: BLE001 - stale local diagnostic reports should not block opening the dashboard.
            rank_check = None
        if isinstance(rank_check, dict):
            rank_check = dict(rank_check)
            rank_check.setdefault("output_json", str(rank_check_json))
            if rank_check_html.exists():
                rank_check.setdefault("output_html", str(rank_check_html))
            summary["rank_check"] = rank_check
    if isinstance(summary, dict) and "app_export_readiness" not in summary:
        app_export_readiness = load_cached_app_export_readiness(summary_path)
        if isinstance(app_export_readiness, dict):
            summary["app_export_readiness"] = app_export_readiness
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
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-top: 18px; }}
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
        <p class="lead">这不是错误。默认入口不会跑图片识别，也不会读取账号登录态；它只打开本地可视化页面。先从下面选一个软件入口。</p>
      </div>
      <div class="grid">
        <article class="card safe">
          <strong>看软件体验</strong>
          <span>有缓存时直接打开 Dashboard；没有缓存时先看本页。不会跑图片识别。</span>
          <code>MihoProbe.exe</code>
        </article>
        <article class="card primary">
          <strong>一键更新练度</strong>
          <span>把米游社官方分享图放进 figs\\ 后再跑。它会处理新图，必要时进入图片识别慢路径。</span>
          <code>MihoProbe.exe update</code>
        </article>
        <article class="card safe">
          <strong>评级快检</strong>
          <span>只看角色头像左上角和音擎评级区的 A/S 艺术字固定区域。不跑图片识别。</span>
          <code>MihoProbe.exe rank-check</code>
        </article>
        <article class="card">
          <strong>准确率验收</strong>
          <span>用人工对照答案回放验收，不重新图片识别，不扫历史解析目录。</span>
          <code>MihoProbe.exe check --no-open</code>
        </article>
        <article class="card">
          <strong>APP 导出流程</strong>
          <span>生成米游社官方分享图工作流和校准命令。不自动登录，不读 token/cookie。</span>
          <code>MihoProbe.exe app-export</code>
        </article>
      </div>
      <div class="note">图片识别是开发慢路径。日常先用 MihoProbe.exe 看缓存，或用 MihoProbe.exe update 更新练度；不要把模型加载当作界面卡死。</div>
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
    readiness = replay_readiness_snapshot()
    expected_path = readiness["expected_dir"]
    figs_path = readiness["figs_dir"]
    parsed_dir = readiness["parsed_dir"]
    image_count = readiness["image_count"]
    expected_count = readiness["expected_count"]
    parsed_count = readiness["parsed_count"]
    if image_count and not parsed_count:
        primary_title = "先识别这批图片"
        primary_text = f"检测到 {image_count} 张分享图，但还没有 parsed JSON。先跑 update 生成解析结果，再人工补 expected。"
        primary_command = "MihoProbe.exe update"
    elif parsed_count and not expected_count:
        primary_title = "先补 expected"
        primary_text = f"检测到 {parsed_count} 个 parsed JSON，但 expected 目录还是空的。打开 review HTML 肉眼确认后补 expected。"
        primary_command = 'notepad "data\\probes\\expected\\<image>_expected.json"'
    elif expected_count:
        primary_title = "补 replay manifest"
        primary_text = f"检测到 {expected_count} 个 expected JSON。现在缺的是把 parsed 和 expected 配对写进固定清单。"
        primary_command = 'notepad "data\\probes\\replay_manifest.json"'
    else:
        primary_title = "先放入分享图"
        primary_text = "还没检测到分享图、parsed 或 expected。先把米游社官方分享图放进 figs\\。"
        primary_command = "MihoProbe.exe update"
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
    .metrics {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fafcff; }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 26px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .card {{ display: grid; gap: 10px; align-content: start; min-height: 180px; padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .card.primary {{ border-color: #bfdbfe; background: var(--blue-bg); }}
    .card.primary strong {{ color: var(--blue); }}
    .card strong {{ font-size: 18px; }}
    .card span {{ color: var(--muted); font-size: 13px; }}
    code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-wrap: anywhere; white-space: pre-wrap; }}
    .paths {{ display: grid; gap: 8px; color: var(--muted); font-size: 13px; }}
    .paths code {{ display: inline; padding: 0; background: transparent; color: var(--text); }}
    @media (max-width: 860px) {{ .grid, .metrics {{ grid-template-columns: 1fr; }} h1 {{ font-size: 28px; }} }}
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
      <div class="metrics">
        <div class="metric"><span>figs\\ 分享图</span><strong>{html_escape(str(image_count))}</strong></div>
        <div class="metric"><span>parsed JSON</span><strong>{html_escape(str(parsed_count))}</strong></div>
        <div class="metric"><span>expected JSON</span><strong>{html_escape(str(expected_count))}</strong></div>
      </div>
      <div class="grid">
        <article class="card primary">
          <strong>{html_escape(primary_title)}</strong>
          <span>{html_escape(primary_text)}</span>
          <code>{html_escape(primary_command)}</code>
        </article>
        <article class="card">
          <strong>先验评级区域</strong>
          <span>评级不是中文 OCR。它只看角色头像左上角和音擎右侧的 A/S 艺术字颜色信号。</span>
          <code>MihoProbe.exe rank-check</code>
        </article>
        <article class="card">
          <strong>只想看软件界面</strong>
          <span>打开缓存 Dashboard，不重新 OCR，不要求 manifest。</span>
          <code>MihoProbe.exe</code>
        </article>
      </div>
      <div class="paths">
        <span>缺少的清单：<code>{html_escape(str(manifest_path))}</code></span>
        <span>分享图目录：<code>{html_escape(str(figs_path))}</code></span>
        <span>parsed 本地目录：<code>{html_escape(str(parsed_dir))}</code></span>
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
    if has_newer_rank_check_report(summary_path, dashboard_path):
        should_refresh = True
    if has_newer_app_export_workflow(summary_path, dashboard_path):
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
    command_name = str(getattr(args, "command", "") or "fresh").lower()
    is_update = command_name == "update"
    images_dir = resolve_cli_path(args.images_dir)
    mode = "rescan_all" if args.rescan_all else "new_or_changed_only"
    mode_label = "重扫全部图片" if args.rescan_all else "只处理新增或变更图片"
    if is_update:
        print("[MihoProbe] 一键更新练度：只读取本地已保存的米游社官方分享图。", flush=True)
        print("[MihoProbe] 不会操作米游社 APP、不会登录、不会读取 token/cookie。", flush=True)
        print("update_scope: saved_official_share_images_only", flush=True)
        print("update_note: safe_mode; reads saved official share images under figs only; no app automation.", flush=True)
    else:
        print("[MihoProbe] 图片识别慢路径：正在处理本地分享图。只看界面请直接运行 MihoProbe.exe。", flush=True)
        print("fresh_scope: saved_official_share_images_only", flush=True)
    print(f"[MihoProbe] 图片目录：{images_dir}", flush=True)
    print(f"[MihoProbe] 处理模式：{mode_label}；识别引擎：{args.engine}。", flush=True)
    print("[MihoProbe] 正在检查输入目录和依赖。后续如果停在模型加载，属于图片识别慢路径，不是 Dashboard 卡死。", flush=True)
    start_label = "update_start" if is_update else "fresh_start"
    print(
        f"{start_label}: images_dir={images_dir}; mode={mode}; engine={args.engine}; game={args.game}",
        flush=True,
    )
    if not images_dir.exists() or not images_dir.is_dir():
        print(f"ERROR: local image directory does not exist: {images_dir}", file=sys.stderr, flush=True)
        print("Put official share images under figs\\, then run MihoProbe.exe update.", file=sys.stderr, flush=True)
        return 1
    dependency_error = frozen_ocr_dependency_error(str(args.engine))
    if dependency_error:
        print("fresh_status: dependency_missing", flush=True)
        print("fresh_dependency: paddleocr_unavailable_in_frozen_exe", flush=True)
        print(f"fresh_note: {dependency_error}", flush=True)
        print(
            "fresh_python_fallback: python tools/probes/run_demo_pipeline.py --images-dir figs --engine paddle --open",
            flush=True,
        )
        return 5
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
    print(f"fresh_mode: {mode}", flush=True)
    print(f"dashboard_html: {summary['dashboard_html']}", flush=True)
    print(f"summary_json: {summary['summary_json']}", flush=True)
    overall = summary.get("overall", {}) if isinstance(summary.get("overall"), dict) else {}
    print(f"hard_failure_count: {overall.get('hard_failure_count', 0)}", flush=True)
    print(f"review_failed_count: {overall.get('review_failed_count', 0)}", flush=True)
    print(f"normalization_failed_count: {overall.get('normalization_failed_count', 0)}", flush=True)
    exit_code = demo_tool.exit_code_for_summary(summary)
    if exit_code:
        print("fresh_status: failed_with_hard_case_failures", flush=True)
        print("fresh_note: Dashboard was generated for diagnosis, but this fresh/update run did not succeed.", flush=True)
    else:
        print("fresh_status: done", flush=True)
    return exit_code


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


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - this is a diagnostic helper, not the parser boundary.
        return None
    return data if isinstance(data, dict) else None


def target_manifest_network_policy(manifest_path: Path | None) -> dict[str, Any]:
    if manifest_path is None:
        return {
            "status": "local_only",
            "uses_public_urls": False,
            "declared_public_url_count": 0,
            "declared_local_input_count": 0,
            "detail": "默认只使用本地已保存 JSON / snapshot，不联网。",
        }
    if not manifest_path.exists():
        return {
            "status": "manifest_missing",
            "uses_public_urls": False,
            "declared_public_url_count": 0,
            "declared_local_input_count": 0,
            "detail": "声明了 source manifest，但文件不存在；本轮不会发起联网请求。",
        }
    manifest = load_optional_json(manifest_path)
    if not manifest:
        return {
            "status": "manifest_unreadable",
            "uses_public_urls": False,
            "declared_public_url_count": 0,
            "declared_local_input_count": 0,
            "detail": "source manifest 无法读取或不是 JSON object；本轮不会发起联网请求。",
        }

    sources = manifest.get("sources") if isinstance(manifest.get("sources"), list) else []
    public_url_count = 0
    local_input_count = 0
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("url"):
            public_url_count += 1
        elif source.get("input"):
            local_input_count += 1

    if public_url_count:
        return {
            "status": "public_sources_declared",
            "uses_public_urls": True,
            "declared_public_url_count": public_url_count,
            "declared_local_input_count": local_input_count,
            "detail": (
                f"只访问 source manifest 声明的 {public_url_count} 个公开 http(s) 来源；"
                "URL 仍会经过 public-only 校验，不复用登录态。"
            ),
        }
    if local_input_count:
        return {
            "status": "local_sources_only",
            "uses_public_urls": False,
            "declared_public_url_count": 0,
            "declared_local_input_count": local_input_count,
            "detail": f"source manifest 只包含 {local_input_count} 个本地 input 文件；不联网。",
        }
    return {
        "status": "manifest_has_no_sources",
        "uses_public_urls": False,
        "declared_public_url_count": 0,
        "declared_local_input_count": 0,
        "detail": "source manifest 没有可用 sources；本轮不会发起联网请求。",
    }


def plan_update_item(item_id: str, title: str, status: str, path: Path | None, detail: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "status": status,
        "path": str(path) if path else None,
        "exists": bool(path and path.exists()),
        "detail": detail,
    }


def build_plan_update_readiness(args: argparse.Namespace, output_dir: Path, manifest_path: Path) -> dict[str, Any]:
    roster_dir = resolve_cli_path(args.roster_dir) if args.roster_dir else DEFAULT_ROSTER_DIR
    roster_index = roster_dir / "roster_index.json"
    roster_data = load_optional_json(roster_index)
    character_count = 0
    if isinstance(roster_data, dict):
        character_count = int(roster_data.get("character_count") or len(roster_data.get("characters") or []) or 0)
    if roster_data and character_count > 0:
        roster_status = "ready"
        roster_detail = f"accepted roster 已就绪，当前确认角色数 {character_count}。"
    elif roster_data:
        roster_status = "empty"
        roster_detail = "roster_index 存在，但 accepted roster 角色数为 0。"
    else:
        roster_status = "missing"
        roster_detail = "缺少 accepted roster；pending/demo snapshot 不能当作已拥有练度。"

    targets_path = resolve_cli_path(args.targets) if args.targets else None
    target_manifest = resolve_cli_path(args.target_source_manifest) if args.target_source_manifest else None
    network_policy = target_manifest_network_policy(target_manifest)
    if targets_path and targets_path.exists():
        target_status = "ready"
        target_detail = "已提供本地高难目标 JSON。"
        target_path = targets_path
    elif target_manifest and target_manifest.exists():
        target_status = "manifest_ready"
        target_detail = f"已提供高难目标 source manifest，本轮会尝试生成本地 targets；{network_policy['detail']}"
        target_path = target_manifest
    elif targets_path or target_manifest:
        target_status = "missing_path"
        target_path = targets_path or target_manifest
        target_detail = "声明了高难目标输入，但文件不存在。"
    else:
        target_status = "missing"
        target_path = None
        target_detail = "缺少高难目标输入；规划只能显示本地/demo 诊断，不能代表 P0/P1 高难建议。"

    tier_snapshot = resolve_cli_path(args.tier_snapshot) if args.tier_snapshot else None
    if tier_snapshot and tier_snapshot.exists():
        tier_status = "ready"
        tier_detail = "已提供本地 Tier/保值快照。"
    elif tier_snapshot:
        tier_status = "missing_path"
        tier_detail = "声明了 Tier/保值快照，但文件不存在。"
    else:
        tier_status = "missing"
        tier_detail = "缺少 Tier/保值快照；队伍排序不会使用保值信号。"

    catalog_path = resolve_cli_path(args.character_catalog) if args.character_catalog else None
    if catalog_path and catalog_path.exists():
        catalog_status = "ready"
        catalog_detail = "已提供本地角色标签 catalog，可辅助目标匹配。"
    elif catalog_path:
        catalog_status = "missing_path"
        catalog_detail = "声明了角色标签 catalog，但文件不存在；本项不阻断 plan-update。"
    else:
        catalog_status = "optional_missing"
        catalog_detail = "未提供角色标签 catalog；本项不阻断 plan-update。"

    items = [
        plan_update_item("accepted_roster", "已确认角色库", roster_status, roster_index, roster_detail),
        plan_update_item("endgame_targets", "高难目标数据", target_status, target_path, target_detail),
        plan_update_item("tier_snapshot", "Tier/保值快照", tier_status, tier_snapshot, tier_detail),
        plan_update_item("character_catalog", "角色标签 catalog", catalog_status, catalog_path, catalog_detail),
        plan_update_item("network_boundary", "联网边界", "ready", target_manifest, network_policy["detail"]),
    ]
    blocking_missing = [
        item["id"]
        for item in items
        if item["id"] in {"accepted_roster", "endgame_targets", "tier_snapshot"}
        and item["status"] not in {"ready", "manifest_ready"}
    ]
    if not blocking_missing:
        source_status = "ready_for_local_planning"
        if network_policy["uses_public_urls"]:
            warning = "本轮可作为本地高难/Tier/配队建议的输入闭环；高难目标只访问 manifest 声明的公开来源，仍不代表官方保证。"
        else:
            warning = "本轮可作为本地高难/Tier/配队建议的输入闭环；默认不联网，也不代表官方保证。"
    elif "accepted_roster" in blocking_missing:
        source_status = "needs_accepted_roster"
        warning = "缺少 accepted roster，本轮不能把 pending/demo snapshot 当作已拥有 box。"
    else:
        source_status = "sources_missing_local_only"
        warning = "当前包含缺失数据源，平均结果只代表本地/demo 诊断，不代表 P0/P1 高难规划验收。"

    next_actions = []
    if "accepted_roster" in blocking_missing:
        next_actions.append("先运行 MihoProbe.exe update --open，人工复核并 accept 后生成 accepted roster。")
    if "endgame_targets" in blocking_missing:
        next_actions.append("补充 --targets 或 --target-source-manifest，再运行 MihoProbe.exe plan-update --open。")
    if "tier_snapshot" in blocking_missing:
        next_actions.append("补充 --tier-snapshot，再运行 MihoProbe.exe plan-update --open。")
    if not next_actions:
        next_actions.append("直接查看 Dashboard 的今日作战简报、队伍建议和高难目标卡。")

    return {
        "schema_version": "p4.4-plan-update-readiness",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_status": source_status,
        "missing_blockers": blocking_missing,
        "warning": warning,
        "items": items,
        "network_policy": network_policy,
        "next_actions": next_actions,
        "input": {
            "output_dir": str(output_dir),
            "plan_update_manifest": str(manifest_path),
            "no_ocr": True,
            "no_network": not bool(network_policy["uses_public_urls"]),
            "public_url_count": int(network_policy["declared_public_url_count"]),
            "no_account_read": True,
        },
    }


def render_plan_update_readiness_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Plan Update 数据源就绪度",
        "",
        f"- source_status: {report.get('source_status')}",
        f"- warning: {report.get('warning')}",
        "",
        "## 数据源",
        "",
    ]
    for item in report.get("items", []):
        lines.append(f"- {item.get('title')}: {item.get('status')}")
        lines.append(f"  - path: {item.get('path') or 'N/A'}")
        lines.append(f"  - detail: {item.get('detail')}")
    lines.extend(["", "## 下一步", ""])
    for action in report.get("next_actions", []):
        lines.append(f"- {action}")
    network_policy = report.get("network_policy") if isinstance(report.get("network_policy"), dict) else {}
    lines.extend(["", "## 安全边界", "", "- 不跑 OCR。"])
    if network_policy.get("uses_public_urls"):
        lines.append(f"- {network_policy.get('detail')}")
    else:
        lines.append("- 不联网。")
    lines.append("- 不读取账号、cookie 或 token。")
    return "\n".join(lines) + "\n"


def write_plan_update_readiness(output_dir: Path, report: dict[str, Any]) -> dict[str, str]:
    report_dir = output_dir / "plan_update_readiness"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "plan_update_readiness.json"
    md_path = report_dir / "plan_update_readiness.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_plan_update_readiness_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def run_plan_update(args: argparse.Namespace) -> int:
    output_dir = resolve_cli_path(args.output_dir)
    if args.clean_demo:
        demo_tool.clean_demo_output_dir(output_dir)
    manifest_path = write_plan_update_manifest(output_dir)
    readiness = build_plan_update_readiness(args, output_dir, manifest_path)
    readiness_paths = write_plan_update_readiness(output_dir, readiness)
    network_policy = readiness.get("network_policy", {})
    print("plan_update_scope: local_roster_targets_tier_only")
    if network_policy.get("uses_public_urls"):
        print(
            "plan_update_note: 不跑 OCR、不读取账号/cookie/token；"
            "只访问 --target-source-manifest 声明的公开 http(s) 来源后重算本地角色库、高难目标、Tier/保值观察和配队建议。"
        )
    else:
        print("plan_update_note: 不跑 OCR、不联网、不读取账号；只重算本地角色库、高难目标、Tier/保值观察和配队建议。")
    print(f"plan_update_network_policy: {network_policy.get('status', 'unknown')}")
    print(f"plan_update_network_detail: {network_policy.get('detail', 'N/A')}")
    print(f"plan_update_source_status: {readiness['source_status']}")
    print(f"plan_update_missing_sources: {','.join(readiness['missing_blockers']) if readiness['missing_blockers'] else 'none'}")
    print(f"plan_update_warning: {readiness['warning']}")
    print(f"plan_update_readiness_json: {readiness_paths['json']}")
    print(f"plan_update_readiness_md: {readiness_paths['md']}")
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


def replay_readiness_snapshot() -> dict[str, Any]:
    parsed_dir = PROJECT_ROOT / "data" / "probes" / "parsed"
    expected_files = sorted(DEFAULT_EXPECTED_DIR.glob("*.json")) if DEFAULT_EXPECTED_DIR.exists() else []
    parsed_files = sorted(parsed_dir.glob("*_parsed_*.json")) if parsed_dir.exists() else []
    return {
        "figs_dir": DEFAULT_FIGS_DIR,
        "parsed_dir": parsed_dir,
        "expected_dir": DEFAULT_EXPECTED_DIR,
        "image_count": len(image_files_in_dir(DEFAULT_FIGS_DIR)),
        "parsed_count": len(parsed_files),
        "expected_count": len(expected_files),
    }


def safe_output_stem(path: Path) -> str:
    text = path.stem
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text) or "image"


def html_file_link(path: Path, label: str) -> str:
    try:
        href = path.resolve().as_uri()
    except ValueError:
        href = str(path)
    return f'<a href="{html_escape(href)}">{html_escape(label)}</a>'


def rank_region_value(entry: dict[str, Any], region_name: str) -> str | None:
    for region in entry.get("regions", []) if isinstance(entry.get("regions"), list) else []:
        if isinstance(region, dict) and region.get("region") == region_name:
            value = region.get("rank")
            return str(value) if value else None
    return None


def rank_entry_summary(entry: dict[str, Any]) -> str:
    character = rank_region_value(entry, "character_rank") or "未识别"
    equipment = rank_region_value(entry, "equipment_rank") or "未识别"
    return f"角色 {character} / 音擎 {equipment}"


def rank_reason_label(reason: Any) -> str:
    labels = {
        "orange_global": "橙色 S 信号稳定",
        "orange_local_peak": "局部橙色 S 信号",
        "purple_global": "紫色 A 信号稳定",
        "purple_local_peak": "局部紫色 A 信号",
        "flat_color_fill": "整块颜色填充，不像 A/S 艺术字",
        "insufficient_color_signal": "颜色信号不足",
    }
    return labels.get(str(reason), str(reason or "未知原因"))


def rank_check_summary(entries: list[dict[str, Any]], *, ok_region_count: int, region_count: int) -> dict[str, str]:
    if not entries:
        return {
            "summary_status": "empty",
            "recommendation": "没有找到分享图。把米游社官方分享图放到 figs\\，再运行 MihoProbe.exe rank-check。",
        }
    if region_count and ok_region_count == region_count:
        return {
            "summary_status": "pass",
            "recommendation": "评级视觉快检通过：完整解析失败时，可以先相信 A/S 艺术字识别，再检查名称、等级和驱动盘字段。",
        }
    return {
        "summary_status": "needs_review",
        "recommendation": "存在评级区域未识别。先打开对应 crop，确认框是否覆盖头像左上角或音擎评级字；若框偏移，再校准 character_rank / equipment_rank 区域。",
    }


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
        "rank_summary": rank_entry_summary({"regions": regions}),
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
                f'<p>置信度 {html_escape(str(region.get("confidence")))} · {html_escape(rank_reason_label(region.get("reason")))}</p>'
                f'<details><summary>颜色/形状证据</summary><p>橙色占比 {html_escape(str(scores.get("orange", 0)))}；紫色占比 {html_escape(str(scores.get("purple", 0)))}；局部峰值 {html_escape(str(scores.get("orange_peak", 0)))} / {html_escape(str(scores.get("purple_peak", 0)))}；形状面积 {html_escape(str(scores.get("orange_bbox_area", 0)))} / {html_escape(str(scores.get("purple_bbox_area", 0)))}</p></details>'
                f'<p>{html_file_link(crop, "打开 crop")}</p></div>'
                "</article>"
            )
        rows.append(
            '<section class="image-card">'
            f'<h2>{html_escape(str(entry.get("image_name") or ""))}</h2>'
            f'<p class="verdict">识别结论：{html_escape(str(entry.get("rank_summary") or rank_entry_summary(entry)))}</p>'
            f'<p class="muted">只检测头像左上角角色评级、音擎右侧评级固定区域；不跑 OCR。</p>'
            f'<div class="regions">{"".join(region_cards)}</div>'
            "</section>"
        )
    body = "".join(rows) if rows else '<section class="image-card"><h2>没有图片</h2><p class="muted">请把官方分享图放到 figs/，或用 --images-dir 指向图片目录。</p></section>'
    summary_status = str(report.get("summary_status") or "needs_review")
    summary_tone = "ok" if summary_status == "pass" else "warn"
    recommendation = str(report.get("recommendation") or "")
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
    .callout {{ border-radius: 8px; padding: 14px 16px; border: 1px solid #dbe3ef; background: #fff; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08); }}
    .callout.ok {{ border-color: #a7e0bd; background: #e8f7ee; color: #147a42; }}
    .callout.warn {{ border-color: #f6cf7c; background: #fff4d5; color: #996500; }}
    .callout strong {{ display: block; font-size: 18px; margin-bottom: 4px; }}
    .image-card {{ padding: 16px; }}
    .image-card h2 {{ margin: 0 0 6px; font-size: 18px; overflow-wrap: anywhere; }}
    .verdict {{ margin: 0 0 6px; color: #172033; font-weight: 900; }}
    .regions {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-top: 12px; }}
    .region {{ display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 12px; padding: 12px; align-items: center; }}
    .region img {{ width: 96px; height: 86px; object-fit: contain; background: #111827; border-radius: 8px; }}
    .region p {{ margin: 5px 0 0; color: #64748b; font-size: 12px; overflow-wrap: anywhere; }}
    .region details {{ margin-top: 6px; color: #64748b; font-size: 12px; }}
    .region summary {{ cursor: pointer; font-weight: 800; }}
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
    <section class="callout {html_escape(summary_tone)}">
      <strong>{html_escape("评级快检通过" if summary_status == "pass" else "评级需要复核")}</strong>
      <p>{html_escape(recommendation)}</p>
    </section>
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
    summary = rank_check_summary(entries, ok_region_count=ok_region_count, region_count=region_count)
    report = {
        "schema_version": "p4.1-rank-region-check",
        "scope": "visual_rank_regions_only",
        **summary,
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
    print(f"rank_check_status: {summary['summary_status']}")
    print(f"rank_check_recommendation: {summary['recommendation']}")
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
    calibration_template_path = result["calibration_template_path"]
    if args.open:
        webbrowser.open(Path(html_path).resolve().as_uri())
    print("app_export_scope: workflow_package_only")
    print("app_export_note: 不自动登录、不读取 token/cookie、不抓包、不控制游戏客户端；当前只生成官方 UI 工作流包。")
    print(f"workflow_status: {validation.get('status')}")
    print(f"workflow_html: {html_path}")
    print(f"workflow_json: {json_path}")
    print(f"calibration_template_json: {calibration_template_path}")
    print(f"app_export_calibrate_command: dist\\MihoProbe.exe app-export-calibrate --manifest {calibration_template_path} --no-open")
    print(f"app_export_run_command: dist\\MihoProbe.exe app-export-run --manifest {calibration_template_path} --no-open")
    return 0 if validation.get("status") != "blocked" else 1


def run_app_export_calibrate(args: argparse.Namespace) -> int:
    manifest_path = resolve_cli_path(args.manifest)
    output_dir = resolve_cli_path(args.output_dir)
    result = app_export_calibrator.calibrate(
        manifest_path=manifest_path,
        output_dir=output_dir,
        game=args.game,
        window_title=args.window_title,
        image_inbox=resolve_cli_path(args.image_inbox),
        grid_size=int(args.grid_size),
        match_index=int(args.match_index),
        capture=not bool(args.no_capture),
    )
    report = result["report"]
    html_path = result["html_path"]
    json_path = result["json_path"]
    if args.open:
        webbrowser.open(Path(html_path).resolve().as_uri())
    print("app_export_calibration_scope: window_grid_screenshot_only")
    print("app_export_calibration_note: 不点击、不登录、不读 token/cookie；只生成网格截图和待填坐标表。")
    print(f"app_export_calibration_status: {report.get('status')}")
    print(f"app_export_calibration_html: {html_path}")
    print(f"app_export_calibration_json: {json_path}")
    screenshot = report.get("screenshot") if isinstance(report.get("screenshot"), dict) else {}
    if screenshot.get("path"):
        print(f"app_export_calibration_screenshot: {screenshot.get('path')}")
    print(f"app_export_calibration_next: {report.get('next_action')}")
    return 1 if report.get("status") == "capture_failed" else 0


def run_app_export_run(args: argparse.Namespace) -> int:
    manifest_path = resolve_cli_path(args.manifest)
    output_dir = resolve_cli_path(args.output_dir)
    result = app_export_runner.run_manifest(
        manifest_path=manifest_path,
        output_dir=output_dir,
        execute=bool(args.execute),
        confirm_official_ui=bool(args.confirm_official_ui),
        match_index=int(args.match_index),
    )
    report = result["report"]
    html_path = result["html_path"]
    json_path = result["json_path"]
    if args.open:
        webbrowser.open(Path(html_path).resolve().as_uri())
    print("app_export_run_scope: calibrated_official_ui_only")
    print("app_export_run_note: 默认只读预检；真正点击必须 --execute --confirm-official-ui，且清单内每步都需 confirmed_official_ui=true。")
    print(f"app_export_run_status: {report.get('status')}")
    print(f"app_export_run_operator_status: {report.get('operator_status')}")
    print(f"app_export_run_status_label: {report.get('status_label')}")
    print(f"app_export_run_headline: {report.get('headline')}")
    print(f"app_export_run_next_command: {report.get('next_command')}")
    print(f"app_export_run_html: {html_path}")
    print(f"app_export_run_json: {json_path}")
    print(f"app_export_run_next: {report.get('next_action')}")
    execution_plan = report.get("execution_plan") if isinstance(report.get("execution_plan"), dict) else {}
    if execution_plan:
        print(f"app_export_run_execution_plan: {execution_plan.get('title')}")
        print(f"app_export_run_click_step_count: {execution_plan.get('click_step_count')}")
        print(f"app_export_run_coordinates_complete: {execution_plan.get('coordinates_complete')}")
        print(f"app_export_run_confirmations_complete: {execution_plan.get('confirmations_complete')}")
        print(f"app_export_run_ready_for_execute_command: {execution_plan.get('ready_for_execute_command')}")
        print(f"app_export_run_execute_command: {execution_plan.get('execute_command')}")
    route = report.get("operator_route") if isinstance(report.get("operator_route"), list) else []
    for index, item in enumerate(route, start=1):
        print(f"app_export_run_route_{index}: {item}")
    boundary = report.get("safety_boundary") if isinstance(report.get("safety_boundary"), list) else []
    print(f"app_export_run_safety_boundary: {'、'.join(str(item) for item in boundary)}")
    return 1 if report.get("status") == "blocked" else 0


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
            print("评级怀疑：先跑 MihoProbe.exe rank-check --no-open；它不跑 OCR，只看 A/S 艺术字区域。", file=sys.stderr)
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


def default_box_roster_output(image_path: Path) -> Path:
    return DEFAULT_BOX_DIR / f"{image_path.stem}_roster_from_box_image.json"


def run_box_roster(args: argparse.Namespace) -> int:
    image_path = resolve_cli_path(args.image)
    output_json = resolve_cli_path(args.output) if args.output else default_box_roster_output(image_path)
    output_markdown = resolve_cli_path(args.markdown) if args.markdown else output_json.with_suffix(".md")
    meta_snapshot = resolve_cli_path(args.meta_snapshot) if args.meta_snapshot else None
    print("[MihoProbe] Box roster probe：只读取用户显式提供的本地米游社官方 box 图。", flush=True)
    print("[MihoProbe] 不读取账号、cookie/token，不保存 header UID/昵称/原始 OCR，不写正式数据库。", flush=True)
    print("box_roster_scope: explicit_local_official_box_image_only", flush=True)
    try:
        result = box_roster_tool.extract_roster_from_image(
            image_path=image_path,
            output_json=output_json,
            meta_snapshot=meta_snapshot,
            output_markdown=output_markdown,
            ocr_scale=args.ocr_scale,
            min_mindscape_confidence=args.min_mindscape_confidence,
        )
    except box_roster_tool.BoxRosterExtractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 2
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    print(f"roster_json: {result['output_json']}", flush=True)
    print(f"roster_markdown: {result['output_markdown']}", flush=True)
    print(f"owned_count: {summary.get('owned_count', 0)}", flush=True)
    print(f"mapped_count: {summary.get('mapped_count', 0)}", flush=True)
    print(f"needs_review_count: {summary.get('needs_review_count', 0)}", flush=True)
    print("box_roster_review_gate: manual_confirmation_required_before_accepted_roster", flush=True)
    for warning in result.get("warnings", []):
        print(f"warning: {warning}", flush=True)
    if args.open and output_markdown.exists():
        webbrowser.open(output_markdown.resolve().as_uri())
        print(f"roster_markdown_opened: {output_markdown}", flush=True)
    needs_review = int(summary.get("needs_review_count") or 0)
    return 0 if needs_review == 0 else 1


def run_box_value(args: argparse.Namespace) -> int:
    argv: list[str] = ["--output-dir", str(resolve_cli_path(args.output_dir))]
    if args.roster_json:
        argv.extend(["--roster-json", str(resolve_cli_path(args.roster_json))])
    if args.box_image:
        argv.extend(["--box-image", str(resolve_cli_path(args.box_image))])
    if args.roster_output:
        argv.extend(["--roster-output", str(resolve_cli_path(args.roster_output))])
    if args.meta_snapshot:
        argv.extend(["--meta-snapshot", str(resolve_cli_path(args.meta_snapshot))])
    if args.refresh_meta:
        argv.append("--refresh-meta")
    if args.current_only:
        argv.append("--current-only")
    if args.max_phases is not None:
        argv.extend(["--max-phases", str(args.max_phases)])
    argv.extend(["--timeout", str(args.timeout)])
    argv.extend(["--request-delay", str(args.request_delay)])
    argv.extend(["--box-ocr-scale", str(args.box_ocr_scale)])
    argv.extend(["--min-mindscape-confidence", str(args.min_mindscape_confidence)])
    print("[MihoProbe] Box value probe：用本地 roster/box 图和公开 Prydwen meta 生成账号内价值报告。", flush=True)
    print("[MihoProbe] 不读取账号登录态，不抓包，不把未拥有角色算作当前可用队伍。", flush=True)
    print("box_value_scope: local_roster_or_box_image_plus_public_meta", flush=True)
    print("box_value_review_gate: image_roster_requires_manual_confirmation_before_accepted_roster", flush=True)
    return int(box_value_tool.main(argv))


def recent_local_files(
    directories: list[Path],
    *,
    suffixes: set[str],
    name_contains: tuple[str, ...] = (),
    recursive: bool = False,
    limit: int = 8,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        iterator = directory.rglob("*") if recursive else directory.iterdir()
        for path in iterator:
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            lower_name = path.name.lower()
            if name_contains and not any(marker in lower_name for marker in name_contains):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            records.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                    "mtime_epoch": stat.st_mtime,
                }
            )
    records.sort(key=lambda item: float(item.get("mtime_epoch") or 0), reverse=True)
    return records[:limit]


def shell_quote_path(path: str | Path) -> str:
    text = str(path)
    return f'"{text}"' if any(char.isspace() for char in text) else text


def build_box_status(args: argparse.Namespace) -> dict[str, Any]:
    image_dirs = [resolve_cli_path(item) for item in (args.image_dir or [])]
    if not image_dirs:
        image_dirs = [DEFAULT_EXPORTED_IMAGES_DIR]
    meta_dir = resolve_cli_path(args.meta_dir)
    box_dir = resolve_cli_path(args.box_dir)
    value_dir = resolve_cli_path(args.value_dir)
    images = recent_local_files(image_dirs, suffixes=IMAGE_EXTENSIONS, limit=args.max_items)
    metas = recent_local_files([meta_dir], suffixes={".json"}, name_contains=("prydwen", "meta"), limit=args.max_items)
    rosters = recent_local_files([box_dir, value_dir], suffixes={".json"}, name_contains=("roster",), recursive=True, limit=args.max_items)
    value_reports = recent_local_files([value_dir], suffixes={".json", ".md"}, name_contains=("agent_value_cards",), recursive=True, limit=args.max_items)

    latest_image = images[0]["path"] if images else None
    latest_meta = metas[0]["path"] if metas else None
    latest_roster = rosters[0]["path"] if rosters else None
    if latest_image and latest_meta:
        next_command = (
            "dist\\MihoProbe.exe box-value "
            f"--box-image {shell_quote_path(latest_image)} "
            f"--meta-snapshot {shell_quote_path(latest_meta)}"
        )
        readiness = "ready_for_box_value_from_image"
        next_label = "可直接生成 box 价值报告"
    elif latest_roster and latest_meta:
        next_command = (
            "dist\\MihoProbe.exe box-value "
            f"--roster-json {shell_quote_path(latest_roster)} "
            f"--meta-snapshot {shell_quote_path(latest_meta)}"
        )
        readiness = "ready_for_box_value_from_roster"
        next_label = "可用已生成 roster probe 跑价值报告"
    elif latest_image:
        next_command = f"dist\\MihoProbe.exe box-roster --image {shell_quote_path(latest_image)} --no-open"
        readiness = "needs_public_meta"
        next_label = "先准备公开 meta，或只生成 roster probe"
    elif latest_meta:
        next_command = "把米游社官方 box 总览图保存到 data\\probes\\exported_images\\ 后运行 dist\\MihoProbe.exe box-status"
        readiness = "needs_box_image"
        next_label = "缺少 box 总览图"
    else:
        next_command = "先准备公开 meta，并把米游社官方 box 总览图保存到 data\\probes\\exported_images\\"
        readiness = "missing_inputs"
        next_label = "缺少 box 图和公开 meta"
    return {
        "schema_version": "p0.2-zzz-box-value-status",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "readiness": readiness,
        "next_label": next_label,
        "next_command": next_command,
        "inputs": {
            "image_dirs": [str(path) for path in image_dirs],
            "meta_dir": str(meta_dir),
            "box_dir": str(box_dir),
            "value_dir": str(value_dir),
        },
        "counts": {
            "image_candidate_count": len(images),
            "meta_snapshot_count": len(metas),
            "roster_probe_count": len(rosters),
            "value_report_count": len(value_reports),
        },
        "latest": {
            "image": latest_image,
            "meta_snapshot": latest_meta,
            "roster_probe": latest_roster,
            "value_report": value_reports[0]["path"] if value_reports else None,
        },
        "images": images,
        "meta_snapshots": metas,
        "roster_probes": rosters,
        "value_reports": value_reports,
        "safety": {
            "no_ocr": True,
            "no_network": True,
            "no_account_read": True,
            "no_database_write": True,
            "manual_confirmation_required_before_accepted_roster": True,
        },
    }


def render_file_list(items: list[dict[str, Any]], empty: str) -> str:
    if not items:
        return f'<div class="empty">{html_escape(empty)}</div>'
    rows = []
    for item in items:
        rows.append(
            "<li>"
            f"<strong>{html_escape(str(item.get('name') or ''))}</strong>"
            f"<span>{html_escape(str(item.get('mtime') or ''))}</span>"
            f"<code>{html_escape(str(item.get('path') or ''))}</code>"
            "</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def render_box_status_html(report: dict[str, Any], output_html: Path) -> None:
    counts = report.get("counts", {}) if isinstance(report.get("counts"), dict) else {}
    safety = report.get("safety", {}) if isinstance(report.get("safety"), dict) else {}
    tone = "ok" if str(report.get("readiness")).startswith("ready") else "warn"
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MihoProbe Box 价值输入检查</title>
  <style>
    body {{ margin: 0; background: #f6f8fb; color: #172033; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; line-height: 1.55; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 22px 44px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    p {{ margin: 0; color: #667085; }}
    code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .hero, .card {{ border: 1px solid #dbe3ef; border-radius: 8px; background: #fff; box-shadow: 0 14px 34px rgba(15, 23, 42, .07); }}
    .hero {{ display: grid; gap: 16px; padding: 22px; margin-bottom: 16px; }}
    .badge {{ width: fit-content; padding: 7px 11px; border-radius: 999px; font-weight: 900; }}
    .badge.ok {{ background: #e8f7ee; color: #147a42; }}
    .badge.warn {{ background: #fff4d5; color: #996500; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ padding: 14px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fafcff; }}
    .metric span {{ display: block; color: #667085; font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 26px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .card {{ padding: 16px; }}
    ul {{ display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }}
    li {{ display: grid; gap: 4px; padding: 10px; border: 1px solid #e6edf6; border-radius: 8px; }}
    li span {{ color: #667085; font-size: 12px; }}
    li code {{ padding: 0; background: transparent; color: #334155; }}
    .empty {{ color: #667085; padding: 10px; border: 1px dashed #cbd5e1; border-radius: 8px; }}
    .safe {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .safe span {{ padding: 6px 9px; border-radius: 999px; background: #eef6ff; color: #1d4ed8; font-size: 12px; font-weight: 800; }}
    @media (max-width: 860px) {{ .metrics, .grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 26px; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="badge {tone}">{html_escape(str(report.get("next_label") or ""))}</div>
      <div>
        <h1>Box 价值输入检查</h1>
        <p>只读检查本地文件，不跑 OCR、不联网、不读取账号。它用来判断下一步该跑 roster probe、meta 刷新，还是直接生成价值报告。</p>
      </div>
      <code>{html_escape(str(report.get("next_command") or ""))}</code>
      <div class="metrics">
        <div class="metric"><span>图片候选</span><strong>{html_escape(str(counts.get("image_candidate_count", 0)))}</strong></div>
        <div class="metric"><span>公开 meta</span><strong>{html_escape(str(counts.get("meta_snapshot_count", 0)))}</strong></div>
        <div class="metric"><span>roster probe</span><strong>{html_escape(str(counts.get("roster_probe_count", 0)))}</strong></div>
        <div class="metric"><span>价值报告</span><strong>{html_escape(str(counts.get("value_report_count", 0)))}</strong></div>
      </div>
      <div class="safe">
        <span>no_ocr={html_escape(str(safety.get("no_ocr")))}</span>
        <span>no_network={html_escape(str(safety.get("no_network")))}</span>
        <span>no_account_read={html_escape(str(safety.get("no_account_read")))}</span>
        <span>manual_review_before_accepted_roster={html_escape(str(safety.get("manual_confirmation_required_before_accepted_roster")))}</span>
      </div>
    </section>
    <section class="grid">
      <article class="card"><h2>图片候选</h2>{render_file_list(report.get("images", []), "没有找到本地图片候选。")}</article>
      <article class="card"><h2>公开 Meta 快照</h2>{render_file_list(report.get("meta_snapshots", []), "没有找到 Prydwen meta JSON。")}</article>
      <article class="card"><h2>Roster Probe</h2>{render_file_list(report.get("roster_probes", []), "还没有生成 roster probe。")}</article>
      <article class="card"><h2>价值报告</h2>{render_file_list(report.get("value_reports", []), "还没有生成 agent_value_cards。")}</article>
    </section>
  </main>
</body>
</html>
"""
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8")


def run_box_status(args: argparse.Namespace) -> int:
    output_dir = resolve_cli_path(args.output_dir)
    output_json = output_dir / "box_value_status.json"
    output_html = output_dir / "box_value_status.html"
    report = build_box_status(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    render_box_status_html(report, output_html)
    print("box_status_scope: local_files_only_no_ocr_no_network", flush=True)
    print(f"box_status_readiness: {report['readiness']}", flush=True)
    print(f"box_status_next: {report['next_command']}", flush=True)
    print(f"box_status_json: {output_json}", flush=True)
    print(f"box_status_html: {output_html}", flush=True)
    if args.open:
        webbrowser.open(output_html.resolve().as_uri())
        print(f"box_status_opened: {output_html}", flush=True)
    return 0


def run_gpt_review(args: argparse.Namespace) -> int:
    prompt = gpt_prompt_tool.render_prompt(
        mode=args.mode,
        focus=args.focus,
        evidence=args.evidence,
        changed_files=args.changed_file,
        completed=args.completed,
        commit=args.commit,
        questions=args.question,
        constraints=args.constraint,
        include_git_status=not args.no_git_status,
    )
    copied = False
    copy_failed_detail = ""
    if getattr(args, "copy", False):
        copied, detail = gpt_prompt_tool.copy_text_to_clipboard(prompt)
        if not copied:
            copy_failed_detail = detail
            print(f"gpt_review_clipboard: unavailable ({detail})")
        else:
            print("gpt_review_clipboard: copied")
    if args.output:
        output_path = resolve_cli_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(prompt, encoding="utf-8")
        print(f"gpt_review_prompt: {output_path}")
    elif copy_failed_detail:
        DEFAULT_GPT_REVIEW_PROMPT.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_GPT_REVIEW_PROMPT.write_text(prompt, encoding="utf-8")
        print(f"gpt_review_prompt: {DEFAULT_GPT_REVIEW_PROMPT}")
        print(f"gpt_review_open_command: {gpt_prompt_tool.prompt_file_open_command(DEFAULT_GPT_REVIEW_PROMPT)}")
        print("gpt_review_next: 打开这个文件，把审查包粘贴到右侧 GPT。")
        print("gpt_review_send_policy: manual_paste_only")
    elif copied:
        print("gpt_review_prompt: clipboard")
        print("gpt_review_next: 粘贴到右侧 GPT 后手动点击发送；Codex 不自动操作右侧页面。")
        print("gpt_review_send_policy: manual_paste_only")
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


def add_box_roster_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--image", required=True, help="Local official MiYouShe ZZZ box overview image.")
    parser.add_argument("--output", default=None, help="Output roster JSON. Default: data/probes/box/<image>_roster_from_box_image.json.")
    parser.add_argument("--markdown", default=None, help="Output Markdown review file. Default: output JSON with .md suffix.")
    parser.add_argument("--meta-snapshot", default=None, help="Optional local Prydwen meta snapshot for alias mapping.")
    parser.add_argument("--ocr-scale", type=int, default=2, help="Resize factor before full-image OCR. Default: 2.")
    parser.add_argument("--min-mindscape-confidence", type=float, default=0.85)
    parser.add_argument("--open", action="store_true", default=True, help="Open generated Markdown review file. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the Markdown review file.")


def add_box_value_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--roster-json", help="Redacted local roster JSON.")
    source.add_argument("--box-image", help="Local official MiYouShe ZZZ box overview image. Creates roster JSON before value report.")
    parser.add_argument("--roster-output", default=None, help="Where to write roster JSON extracted from --box-image.")
    parser.add_argument("--meta-snapshot", default=None, help="Existing public meta snapshot. If omitted, one is created under output-dir.")
    parser.add_argument("--output-dir", default=str(DEFAULT_BOX_VALUE_DIR), help="Output directory. Default: data/probes/value/box_value_pipeline.")
    parser.add_argument("--refresh-meta", action="store_true", help="Fetch public Prydwen meta even if meta-snapshot already exists.")
    parser.add_argument("--current-only", action="store_true", help="Fetch only current Prydwen phases when refreshing meta.")
    parser.add_argument("--max-phases", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--request-delay", type=float, default=0.15)
    parser.add_argument("--box-ocr-scale", type=int, default=2, help="Resize factor before box-image OCR. Default: 2.")
    parser.add_argument("--min-mindscape-confidence", type=float, default=0.85)


def add_box_status_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--image-dir",
        action="append",
        default=[],
        help="Directory containing local box overview image candidates. Can be repeated. Default: data/probes/exported_images.",
    )
    parser.add_argument("--meta-dir", default=str(DEFAULT_META_DIR), help="Directory containing public Prydwen meta snapshots.")
    parser.add_argument("--box-dir", default=str(DEFAULT_BOX_DIR), help="Directory containing roster probe JSON files.")
    parser.add_argument("--value-dir", default=str(DEFAULT_BOX_VALUE_DIR), help="Directory containing box value report outputs.")
    parser.add_argument("--output-dir", default=str(DEFAULT_BOX_STATUS_DIR), help="Output directory for status JSON/HTML.")
    parser.add_argument("--max-items", type=int, default=8, help="Maximum recent files shown per section. Default: 8.")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated HTML. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the HTML report.")


def add_app_export_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default=str(DEFAULT_APP_EXPORT_WORKFLOW_DIR), help="Output directory.")
    parser.add_argument("--image-inbox", default=str(DEFAULT_FIGS_DIR), help="Where official share images should land. Default: figs.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--window-title", default="米游社", help="Target app window title keyword.")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated HTML. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the HTML report.")


def add_app_export_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_APP_EXPORT_WORKFLOW_DIR / APP_EXPORT_CALIBRATION_FILENAME),
        help="Calibration manifest JSON. Default: data/probes/demo/app_export_workflow/miyoushe_app_export_calibration_template.json.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_APP_EXPORT_WORKFLOW_DIR), help="Report output directory.")
    parser.add_argument("--match-index", type=int, default=0, help="Window match index if multiple windows match. Default: 0")
    parser.add_argument("--execute", action="store_true", help="Actually click calibrated official UI steps. Omit for dry-run.")
    parser.add_argument(
        "--confirm-official-ui",
        action="store_true",
        help="Required with --execute and every enabled click step must also be confirmed in the manifest.",
    )
    parser.add_argument("--open", action="store_true", default=True, help="Open generated HTML. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the HTML report.")


def add_app_export_calibrate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_APP_EXPORT_WORKFLOW_DIR / APP_EXPORT_CALIBRATION_FILENAME),
        help="Calibration manifest JSON. Default: data/probes/demo/app_export_workflow/miyoushe_app_export_calibration_template.json.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_APP_EXPORT_WORKFLOW_DIR), help="Calibration report output directory.")
    parser.add_argument("--image-inbox", default=str(DEFAULT_FIGS_DIR), help="Where official share images should land. Default: figs.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--window-title", default="米游社", help="Target app window title keyword.")
    parser.add_argument("--grid-size", type=int, default=100, help="Relative-coordinate grid size in pixels. Default: 100")
    parser.add_argument("--match-index", type=int, default=0, help="Window match index if multiple windows match. Default: 0")
    parser.add_argument("--no-capture", action="store_true", help="Write/read the manifest and report without inspecting windows.")
    parser.add_argument("--open", action="store_true", default=True, help="Open generated HTML. Default: true.")
    parser.add_argument("--no-open", action="store_false", dest="open", help="Do not open the HTML report.")


def add_gpt_review_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("review", "progress"), default="review", help="review=方案审查；progress=完成后同步验收证据。")
    parser.add_argument("--focus", required=True, help="本轮要推进的用户可见目标。")
    parser.add_argument("--evidence", action="append", default=[], help="关键证据，可重复。")
    parser.add_argument("--changed-file", action="append", default=[], help='已改文件，可写 "path: 改了什么"，可重复。')
    parser.add_argument("--completed", action="append", default=[], help="本轮已完成事项，可重复；progress 模式优先使用。")
    parser.add_argument("--commit", default=None, help="已提交的 commit id 或说明；progress 模式使用。")
    parser.add_argument("--question", action="append", default=[], help="额外请审问题，可重复；不传则使用默认问题。")
    parser.add_argument("--constraint", action="append", default=[], help="额外约束，可重复。")
    parser.add_argument("--no-git-status", action="store_true", help="不要自动附带 git status --short。")
    parser.add_argument("--output", default=None, help="可选输出路径；不传则打印到 stdout。")
    parser.add_argument("--copy", action="store_true", help="把审查包复制到系统剪贴板，方便直接粘贴到右侧 GPT。")


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

    app_export_calibrate = subparsers.add_parser("app-export-calibrate", help="Capture a MiYouShe window grid screenshot for calibration.")
    add_app_export_calibrate_args(app_export_calibrate)
    app_export_calibrate.set_defaults(handler=run_app_export_calibrate)

    app_export_run = subparsers.add_parser("app-export-run", help="Run the calibrated MiYouShe export checklist. Dry-run by default.")
    add_app_export_run_args(app_export_run)
    app_export_run.set_defaults(handler=run_app_export_run)

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

    box_roster = subparsers.add_parser("box-roster", help="Extract a redacted roster probe from a local MiYouShe ZZZ box overview image.")
    add_box_roster_args(box_roster)
    box_roster.set_defaults(handler=run_box_roster)

    box_value = subparsers.add_parser("box-value", help="Build ZZZ box value report from a roster JSON or local box overview image.")
    add_box_value_args(box_value)
    box_value.set_defaults(handler=run_box_value)

    box_status = subparsers.add_parser("box-status", help="Check local inputs for the ZZZ box value workflow without OCR or network.")
    add_box_status_args(box_status)
    box_status.set_defaults(handler=run_box_status)

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
    targets.add_argument("--max-source-age-hours", type=float, default=DEFAULT_MAX_SOURCE_AGE_HOURS)
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
