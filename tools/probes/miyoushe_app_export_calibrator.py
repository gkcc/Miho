#!/usr/bin/env python
"""Create a visual calibration report for MiYouShe official share-image export."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any, Callable

import miyoushe_app_export_runner as runner


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo" / "app_export_workflow"
DEFAULT_MANIFEST = DEFAULT_OUTPUT_DIR / "miyoushe_app_export_calibration_template.json"
DEFAULT_IMAGE_INBOX = PROJECT_ROOT / "figs"
DEFAULT_GRID_SIZE = 100
REPORT_SCHEMA_VERSION = "p4.5-miyoushe-app-export-calibration-report"


class AppExportCalibrationError(RuntimeError):
    pass


WindowFinder = Callable[[str], list[dict[str, Any]]]
WindowCapture = Callable[[dict[str, Any], Path, int, bool], dict[str, Any]]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def rel_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_window_probe() -> tuple[WindowFinder, WindowCapture]:
    import window_screenshot_probe

    return window_screenshot_probe.find_windows, window_screenshot_probe.capture_window


def ensure_manifest(
    *,
    manifest_path: Path,
    game: str,
    window_title: str,
    image_inbox: Path,
) -> dict[str, Any]:
    if manifest_path.exists():
        return runner.load_manifest(manifest_path)
    return runner.write_calibration_template(
        path=manifest_path,
        game=game,
        window_title=window_title,
        image_inbox=image_inbox,
    )


def calibration_tasks(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for step in runner.click_steps(manifest):
        state = runner.coordinate_state(step)
        if state == "ok" and step.get("confirmed_official_ui") is True:
            status = "ready"
        elif state == "ok":
            status = "needs_confirmation"
        else:
            status = "needs_coordinate"
        tasks.append(
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "x": step.get("x"),
                "y": step.get("y"),
                "confirmed_official_ui": step.get("confirmed_official_ui") is True,
                "status": status,
                "note": step.get("note") or "",
            }
        )
    return tasks


def next_action(status: str) -> str:
    return {
        "screenshot_captured": "照着网格截图，把每个步骤的 x/y 填入校准清单；填完先运行 app-export-run --no-open。",
        "needs_window_capture": "打开已登录的米游社 APP，然后运行 app-export-calibrate 捕获网格截图。",
        "window_missing": "没有找到米游社窗口：先打开并登录米游社 APP，再重新运行 app-export-calibrate。",
        "capture_failed": "截图失败：确认米游社窗口未最小化、Pillow 可用，然后重新运行。",
    }.get(status, "查看报告中的下一步。")


def select_window(matches: list[dict[str, Any]], match_index: int) -> dict[str, Any] | None:
    if not matches:
        return None
    if match_index < 0 or match_index >= len(matches):
        raise AppExportCalibrationError(f"--match-index {match_index} is out of range. matched_windows={len(matches)}")
    return matches[match_index]


def build_report(
    *,
    manifest_path: Path,
    output_dir: Path,
    game: str = "zzz",
    window_title: str = "米游社",
    image_inbox: Path = DEFAULT_IMAGE_INBOX,
    grid_size: int = DEFAULT_GRID_SIZE,
    match_index: int = 0,
    capture: bool = True,
    window_finder: WindowFinder | None = None,
    window_capture: WindowCapture | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = ensure_manifest(
        manifest_path=manifest_path,
        game=game,
        window_title=window_title,
        image_inbox=image_inbox,
    )
    validation = runner.validate_manifest(manifest)
    tasks = calibration_tasks(manifest)
    screenshot: dict[str, Any] | None = None
    window: dict[str, Any] | None = None
    warnings: list[str] = []

    if not capture:
        status = "needs_window_capture"
    else:
        if window_finder is None or window_capture is None:
            window_finder, window_capture = load_window_probe()
        try:
            matches = window_finder(str(manifest.get("window_title") or window_title))
            window = select_window(matches, match_index)
            if window is None:
                status = "window_missing"
                warnings.append("No visible MiYouShe window matched the configured title.")
            else:
                screenshot_result = window_capture(window, output_dir, grid_size, True)
                screenshot = screenshot_result.get("image") if isinstance(screenshot_result.get("image"), dict) else {}
                if isinstance(screenshot, dict):
                    screenshot["metadata_path"] = screenshot_result.get("metadata_path")
                status = "screenshot_captured"
        except Exception as exc:  # noqa: BLE001 - keep calibration failures visible in the local report.
            status = "capture_failed"
            warnings.append(str(exc))

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at": now_iso(),
        "status": status,
        "next_action": next_action(status),
        "manifest_path": str(manifest_path),
        "manifest_validation": validation,
        "window_title": manifest.get("window_title") or window_title,
        "image_inbox": manifest.get("image_inbox") or rel_path(image_inbox),
        "grid_size": grid_size,
        "window": window,
        "screenshot": screenshot,
        "tasks": tasks,
        "warnings": warnings,
        "dry_run_command": manifest.get("dry_run_command") or "",
        "execute_command": manifest.get("execute_command") or "",
        "does_not": manifest.get("does_not") if isinstance(manifest.get("does_not"), list) else [],
    }


def image_src(path_value: Any) -> str:
    if not path_value:
        return ""
    path = Path(str(path_value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        return path.resolve().as_uri()
    except ValueError:
        return ""


def render_html(report: dict[str, Any]) -> str:
    tasks = report.get("tasks") if isinstance(report.get("tasks"), list) else []
    manifest_path = str(report.get("manifest_path") or "")
    task_rows = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_rows.append(
            "<tr>"
            f"<td>{escape(str(task.get('title') or task.get('id') or ''))}</td>"
            f"<td>{escape(str(task.get('x') if task.get('x') is not None else '待填'))}</td>"
            f"<td>{escape(str(task.get('y') if task.get('y') is not None else '待填'))}</td>"
            f"<td>{escape('已确认' if task.get('confirmed_official_ui') else '待确认')}</td>"
            f"<td>{escape(str(task.get('status') or ''))}</td>"
            f"<td>{escape(str(task.get('note') or ''))}</td>"
            "</tr>"
        )
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    warning_items = "".join(f"<li>{escape(str(item))}</li>" for item in warnings) or "<li>无</li>"
    screenshot = report.get("screenshot") if isinstance(report.get("screenshot"), dict) else {}
    shot_src = image_src(screenshot.get("path"))
    shot_html = (
        f'<img src="{escape(shot_src)}" alt="米游社窗口网格截图">'
        if shot_src
        else '<div class="empty">还没有截图。打开米游社 APP 后重新运行 app-export-calibrate。</div>'
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>米游社导出坐标校准</title>
  <style>
    body {{ margin: 0; background: #f6f8fb; color: #172033; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; }}
    header {{ padding: 26px 30px; background: #101827; color: #fff; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric, .panel {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08); }}
    .metric {{ padding: 14px; }}
    .metric span {{ display: block; color: #64748b; font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 22px; overflow-wrap: anywhere; }}
    .panel {{ padding: 16px; }}
    .panel h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .callout {{ padding: 16px; border: 1px solid #fed7aa; border-radius: 8px; background: #fff7ed; color: #7c2d12; }}
    .callout h2 {{ margin: 0 0 8px; font-size: 20px; }}
    .callout p {{ margin: 0; line-height: 1.6; }}
    .guide {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }}
    .guide article {{ padding: 14px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fbfcff; }}
    .guide b {{ display: inline-grid; place-items: center; width: 26px; height: 26px; margin-bottom: 8px; border-radius: 999px; background: #eef6ff; color: #1d4ed8; }}
    .guide h3 {{ margin: 0 0 6px; font-size: 15px; }}
    .guide p {{ margin: 0; color: #475569; line-height: 1.5; }}
    .shot {{ display: grid; gap: 10px; }}
    .shot img {{ width: 100%; max-height: 760px; object-fit: contain; border: 1px solid #dbe3ef; border-radius: 8px; background: #111827; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #dbe3ef; vertical-align: top; }}
    th {{ color: #64748b; font-size: 13px; }}
    code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .empty {{ padding: 24px; border: 1px dashed #dbe3ef; border-radius: 8px; color: #64748b; background: #fbfcff; }}
  </style>
</head>
<body>
  <header>
    <h1>米游社导出坐标校准</h1>
    <p>这一步只生成网格截图和待填坐标表，不点击、不登录、不读 token/cookie。</p>
  </header>
  <main>
    <section class="callout">
      <h2>先说结论：你不需要先填坐标</h2>
      <p>坐标校准只服务“以后自动点击米游社官方 UI”的实验路线。如果你现在只是想验收端到端体验，直接手动在米游社 APP 保存官方分享图到 <strong>figs\\</strong>，再运行 <strong>MihoProbe Update</strong> 或 <strong>dist\\MihoProbe.exe update --open</strong>。</p>
    </section>
    <section class="metrics">
      <div class="metric"><span>状态</span><strong>{escape(str(report.get("status") or ""))}</strong></div>
      <div class="metric"><span>网格</span><strong>{escape(str(report.get("grid_size") or ""))} px</strong></div>
      <div class="metric"><span>待填步骤</span><strong>{escape(str(sum(1 for task in tasks if isinstance(task, dict) and task.get("status") == "needs_coordinate")))}</strong></div>
      <div class="metric"><span>待确认步骤</span><strong>{escape(str(sum(1 for task in tasks if isinstance(task, dict) and task.get("status") == "needs_confirmation")))}</strong></div>
    </section>
    <section class="panel">
      <h2>下一步</h2>
      <p>{escape(str(report.get("next_action") or ""))}</p>
      <code>{escape(manifest_path)}</code>
    </section>
    <section class="panel">
      <h2>坐标到底怎么填</h2>
      <div class="guide">
        <article><b>1</b><h3>先看截图</h3><p>打开已登录的米游社 APP，停在当前步骤对应页面，运行 app-export-calibrate。下方截图会覆盖网格。</p></article>
        <article><b>2</b><h3>读窗口相对坐标</h3><p>x/y 是米游社窗口左上角开始算的相对坐标，不是整个屏幕坐标。网格线间距就是上方显示的 px。</p></article>
        <article><b>3</b><h3>取按钮中心点</h3><p>每一行填目标按钮或卡片中心点，比如“我的”就取底部“我的”按钮中心。看不到目标时不要猜。</p></article>
        <article><b>4</b><h3>改清单 JSON</h3><p>在清单里给对应步骤填 x/y，并只在确认它是米游社官方 UI 后，把 confirmed_official_ui 改为 true。</p></article>
      </div>
      <p>清单文件：</p>
      <code>{escape(manifest_path)}</code>
      <p>如果某一步的目标按钮不在当前截图里，先手动切到那一步所在页面，再重新生成网格截图；不要凭记忆乱填坐标。</p>
    </section>
    <section class="panel shot">
      <h2>窗口网格截图</h2>
      {shot_html}
    </section>
    <section class="panel">
      <h2>需要填入清单的坐标</h2>
      <table>
        <thead><tr><th>步骤</th><th>x</th><th>y</th><th>确认</th><th>状态</th><th>应该点哪里</th></tr></thead>
        <tbody>{''.join(task_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>填完以后</h2>
      <p>先 dry-run，不点击：</p>
      <code>{escape(str(report.get("dry_run_command") or ""))}</code>
      <p>全部确认后才允许执行：</p>
      <code>{escape(str(report.get("execute_command") or ""))}</code>
    </section>
    <section class="panel">
      <h2>警告</h2>
      <ul>{warning_items}</ul>
    </section>
  </main>
</body>
</html>
"""


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path | dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "miyoushe_app_export_calibration_report.json"
    html_path = output_dir / "miyoushe_app_export_calibration_report.html"
    report = dict(report)
    report["output_json"] = str(json_path)
    report["output_html"] = str(html_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return {"report": report, "json_path": json_path, "html_path": html_path}


def calibrate(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    game: str = "zzz",
    window_title: str = "米游社",
    image_inbox: Path = DEFAULT_IMAGE_INBOX,
    grid_size: int = DEFAULT_GRID_SIZE,
    match_index: int = 0,
    capture: bool = True,
    window_finder: WindowFinder | None = None,
    window_capture: WindowCapture | None = None,
) -> dict[str, Path | dict[str, Any]]:
    report = build_report(
        manifest_path=manifest_path,
        output_dir=output_dir,
        game=game,
        window_title=window_title,
        image_inbox=image_inbox,
        grid_size=grid_size,
        match_index=match_index,
        capture=capture,
        window_finder=window_finder,
        window_capture=window_capture,
    )
    return write_report(report, output_dir)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a MiYouShe window grid screenshot for app-export calibration.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Calibration manifest JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Calibration output directory.")
    parser.add_argument("--image-inbox", default=str(DEFAULT_IMAGE_INBOX), help="Where official share images should land. Default: figs.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--window-title", default="米游社", help="Target app window title keyword.")
    parser.add_argument("--grid-size", type=int, default=DEFAULT_GRID_SIZE, help="Relative-coordinate grid size in pixels.")
    parser.add_argument("--match-index", type=int, default=0, help="Window match index if multiple windows match. Default: 0")
    parser.add_argument("--no-capture", action="store_true", help="Only write/read the calibration manifest and report; do not inspect windows.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    result = calibrate(
        manifest_path=resolve_path(args.manifest),
        output_dir=resolve_path(args.output_dir),
        game=args.game,
        window_title=args.window_title,
        image_inbox=resolve_path(args.image_inbox),
        grid_size=args.grid_size,
        match_index=args.match_index,
        capture=not args.no_capture,
    )
    report = result["report"]
    print(f"app_export_calibration_status: {report.get('status')}")
    print(f"app_export_calibration_html: {result['html_path']}")
    print(f"app_export_calibration_json: {result['json_path']}")
    screenshot = report.get("screenshot") if isinstance(report.get("screenshot"), dict) else {}
    if screenshot.get("path"):
        print(f"app_export_calibration_screenshot: {screenshot.get('path')}")
    print(f"app_export_calibration_next: {report.get('next_action')}")
    return 1 if report.get("status") == "capture_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
