#!/usr/bin/env python
"""Run a calibrated MiYouShe official share-image export checklist."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo" / "app_export_workflow"
DEFAULT_MANIFEST = DEFAULT_OUTPUT_DIR / "miyoushe_app_export_calibration_template.json"
DEFAULT_IMAGE_INBOX = PROJECT_ROOT / "figs"
CALIBRATION_SCHEMA_VERSION = "p4.4-miyoushe-app-export-calibration"
REPORT_SCHEMA_VERSION = "p4.4-miyoushe-app-export-run-report"

FORBIDDEN_CAPABILITIES = (
    "auto_login",
    "credential_input",
    "captcha_bypass",
    "packet_capture",
    "token_read",
    "cookie_read",
    "game_client_control",
    "formal_database_write",
)

RISKY_STEP_KEYWORDS = (
    "登录",
    "验证码",
    "密码",
    "账号密码",
    "token",
    "cookie",
    "stoken",
    "ltoken",
    "抓包",
    "游戏客户端",
    "captcha",
    "password",
    "credential",
)


class AppExportRunnerError(RuntimeError):
    pass


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


def command_text(parts: list[str]) -> str:
    return " ".join(parts)


def default_calibrated_steps() -> list[dict[str, Any]]:
    return [
        {
            "id": "precheck_window",
            "title": "确认米游社窗口",
            "action": "precheck_window",
            "enabled": True,
            "note": "只读确认窗口标题和大小。",
        },
        {
            "id": "go_profile",
            "title": "点击底部“我的”",
            "action": "official_ui_click",
            "enabled": True,
            "x": None,
            "y": None,
            "confirmed_official_ui": False,
            "wait_after_seconds": 1.0,
            "note": "必须由网格截图人工确认坐标落在米游社官方“我的”按钮上。",
        },
        {
            "id": "go_battle_record",
            "title": "进入战绩",
            "action": "official_ui_click",
            "enabled": True,
            "x": None,
            "y": None,
            "confirmed_official_ui": False,
            "wait_after_seconds": 1.5,
            "note": "只允许点击米游社官方战绩/战绩统计入口。",
        },
        {
            "id": "go_agent_list",
            "title": "进入代理人列表",
            "action": "official_ui_click",
            "enabled": True,
            "x": None,
            "y": None,
            "confirmed_official_ui": False,
            "wait_after_seconds": 1.5,
            "note": "只允许点击绝区零代理人/角色列表入口。",
        },
        {
            "id": "open_agent_detail",
            "title": "打开代理人详情",
            "action": "official_ui_click",
            "enabled": True,
            "x": None,
            "y": None,
            "confirmed_official_ui": False,
            "wait_after_seconds": 1.5,
            "note": "用户可以把此步骤坐标指向想更新的代理人卡片；不得用于弹窗、广告或登录。",
        },
        {
            "id": "open_share_menu",
            "title": "打开右上角分享",
            "action": "official_ui_click",
            "enabled": True,
            "x": None,
            "y": None,
            "confirmed_official_ui": False,
            "wait_after_seconds": 1.0,
            "note": "只允许点击官方分享/更多/导出入口。",
        },
        {
            "id": "save_share_image",
            "title": "保存官方分享图",
            "action": "official_ui_click",
            "enabled": True,
            "x": None,
            "y": None,
            "confirmed_official_ui": False,
            "wait_after_seconds": 1.0,
            "note": "只允许点击官方保存图片按钮，图片进入本地收件箱。",
        },
        {
            "id": "parse_saved_image",
            "title": "本地解析保存后的分享图",
            "action": "local_command",
            "enabled": False,
            "command": "dist\\MihoProbe.exe update --open",
            "note": "点击流程结束后回到本地 update；解析结果仍需人工复核。",
        },
    ]


def build_calibration_template(
    *,
    game: str = "zzz",
    window_title: str = "米游社",
    image_inbox: Path = DEFAULT_IMAGE_INBOX,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest_rel = rel_path(manifest_path)
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "created_at": now_iso(),
        "game": game,
        "window_title": window_title,
        "image_inbox": rel_path(image_inbox),
        "official_ui_only": True,
        "requires_user_logged_in_app": True,
        "does_not": list(FORBIDDEN_CAPABILITIES),
        "status_hint": "needs_coordinates",
        "dry_run_command": command_text(
            ["dist\\MihoProbe.exe", "app-export-run", "--manifest", manifest_rel, "--no-open"]
        ),
        "execute_command": command_text(
            [
                "dist\\MihoProbe.exe",
                "app-export-run",
                "--manifest",
                manifest_rel,
                "--execute",
                "--confirm-official-ui",
                "--no-open",
            ]
        ),
        "calibration_notes": [
            "先用 app-export 生成工作流和网格截图。",
            "把每个 official_ui_click 步骤的 x/y 填成窗口相对坐标。",
            "只有人工确认坐标是米游社官方 UI 后，才把 confirmed_official_ui 改为 true。",
            "默认 app-export-run 只 dry-run；真正点击必须同时带 --execute 和 --confirm-official-ui。",
        ],
        "steps": default_calibrated_steps(),
    }


def write_calibration_template(
    *,
    path: Path,
    game: str = "zzz",
    window_title: str = "米游社",
    image_inbox: Path = DEFAULT_IMAGE_INBOX,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_calibration_template(
        game=game,
        window_title=window_title,
        image_inbox=image_inbox,
        manifest_path=path,
    )
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AppExportRunnerError(f"Calibration manifest does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppExportRunnerError(f"Invalid calibration manifest JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise AppExportRunnerError("Calibration manifest must be a JSON object.")
    return data


def is_risky_text(value: Any) -> bool:
    text = "" if value is None else str(value).casefold()
    return any(keyword.casefold() in text for keyword in RISKY_STEP_KEYWORDS)


def enabled_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    steps = manifest.get("steps") if isinstance(manifest.get("steps"), list) else []
    return [step for step in steps if isinstance(step, dict) and step.get("enabled", True) is not False]


def click_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in enabled_steps(manifest) if step.get("action") == "official_ui_click"]


def coordinate_state(step: dict[str, Any]) -> str:
    x = step.get("x")
    y = step.get("y")
    if x is None or y is None:
        return "missing"
    if not isinstance(x, int) or not isinstance(y, int):
        return "invalid_type"
    if x < 0 or y < 0 or x > 20000 or y > 20000:
        return "out_of_range"
    return "ok"


def validate_manifest(manifest: dict[str, Any], *, for_execute: bool = False) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        warnings.append("schema_version_not_current")
    if manifest.get("official_ui_only") is not True:
        blockers.append("official_ui_only_not_confirmed")
    forbidden = set(manifest.get("does_not") if isinstance(manifest.get("does_not"), list) else [])
    missing_forbidden = [item for item in FORBIDDEN_CAPABILITIES if item not in forbidden]
    if missing_forbidden:
        blockers.append("missing_forbidden_capability_boundary")
        warnings.append("missing: " + ", ".join(missing_forbidden))
    window_title = str(manifest.get("window_title") or "")
    if not window_title:
        blockers.append("missing_window_title")
    elif "米游社" not in window_title:
        warnings.append("window_title_does_not_explicitly_contain_miyoushe")
        if for_execute:
            blockers.append("execute_requires_miyoushe_window_title")

    steps = manifest.get("steps") if isinstance(manifest.get("steps"), list) else []
    if not steps:
        blockers.append("missing_steps")
    seen_ids: set[str] = set()
    missing_coordinate_ids: list[str] = []
    invalid_coordinate_ids: list[str] = []
    unconfirmed_ids: list[str] = []
    risky_ids: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            blockers.append("invalid_step_entry")
            continue
        step_id = str(step.get("id") or "")
        if not step_id:
            blockers.append("missing_step_id")
        elif step_id in seen_ids:
            blockers.append("duplicate_step_id")
        else:
            seen_ids.add(step_id)
        if is_risky_text(step.get("id")) or is_risky_text(step.get("title")):
            risky_ids.append(step_id or "<unknown>")
        if step.get("enabled", True) is False:
            continue
        action = step.get("action")
        if action not in {"precheck_window", "official_ui_click", "local_command"}:
            blockers.append(f"unsupported_action:{step_id or action}")
            continue
        if action == "official_ui_click":
            state = coordinate_state(step)
            if state == "missing":
                missing_coordinate_ids.append(step_id)
            elif state != "ok":
                invalid_coordinate_ids.append(step_id)
            if step.get("confirmed_official_ui") is not True:
                unconfirmed_ids.append(step_id)
    if risky_ids:
        blockers.append("risky_step_text_detected")
        warnings.append("risky_steps: " + ", ".join(risky_ids))
    if invalid_coordinate_ids:
        blockers.append("invalid_coordinates")
        warnings.append("invalid_coordinate_steps: " + ", ".join(invalid_coordinate_ids))
    if for_execute and missing_coordinate_ids:
        blockers.append("execute_requires_all_coordinates")
    if for_execute and unconfirmed_ids:
        blockers.append("execute_requires_confirmed_official_ui_steps")

    if blockers:
        status = "blocked"
    elif missing_coordinate_ids:
        status = "needs_coordinates"
    elif unconfirmed_ids:
        status = "needs_confirmation"
    elif for_execute:
        status = "ready_for_execute"
    else:
        status = "ready_for_dry_run"
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "step_count": len(steps),
        "enabled_step_count": len(enabled_steps(manifest)),
        "click_step_count": len(click_steps(manifest)),
        "missing_coordinate_count": len(missing_coordinate_ids),
        "invalid_coordinate_count": len(invalid_coordinate_ids),
        "unconfirmed_step_count": len(unconfirmed_ids),
        "missing_coordinate_steps": missing_coordinate_ids,
        "unconfirmed_steps": unconfirmed_ids,
    }


WindowFinder = Callable[[str], list[dict[str, Any]]]
PointResolver = Callable[[dict[str, Any], int, int], dict[str, Any]]
Clicker = Callable[[int, int], None]


def load_click_probe() -> tuple[WindowFinder, PointResolver, Clicker]:
    import click_relative_probe

    return click_relative_probe.find_windows, click_relative_probe.resolve_point, click_relative_probe.click_absolute


def selected_window(matches: list[dict[str, Any]], match_index: int) -> dict[str, Any]:
    if not matches:
        raise AppExportRunnerError("No visible MiYouShe window was found.")
    if match_index < 0 or match_index >= len(matches):
        raise AppExportRunnerError(f"--match-index {match_index} is out of range. matched_windows={len(matches)}")
    match = matches[match_index]
    if "米游社" not in str(match.get("title") or ""):
        raise AppExportRunnerError("Selected window title does not contain 米游社.")
    return match


def wait_after_step(seconds: Any, *, execute: bool) -> None:
    if not execute:
        return
    try:
        value = float(seconds or 0)
    except (TypeError, ValueError):
        value = 0.0
    value = max(0.0, min(value, 10.0))
    if value:
        time.sleep(value)


def next_action_for_status(status: str) -> str:
    return {
        "needs_coordinates": "先打开工作流 HTML，用网格截图把每个 official_ui_click 步骤的 x/y 填进 calibration_template.json。",
        "needs_confirmation": "坐标已填，但还没有逐步确认 confirmed_official_ui=true；确认每个目标都是米游社官方 UI 后再执行。",
        "ready_for_dry_run": "先运行 dry-run，确认所有坐标都能解析到米游社窗口内。",
        "ready_for_execute": "可执行，但仍必须由用户显式输入 --execute --confirm-official-ui。",
        "executed": "分享图保存后运行 dist\\MihoProbe.exe update --open，并在 Dashboard 人工复核。",
        "blocked": "先修复阻断项，不允许点击。",
    }.get(status, "查看报告中的 warnings 和 blockers。")


def build_report(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    execute: bool,
    confirm_official_ui: bool,
    match_index: int,
    window_finder: WindowFinder | None = None,
    point_resolver: PointResolver | None = None,
    clicker: Clicker | None = None,
) -> dict[str, Any]:
    validation = validate_manifest(manifest, for_execute=execute)
    report_status = validation["status"]
    step_results: list[dict[str, Any]] = []
    clicked_count = 0
    selected: dict[str, Any] | None = None

    if execute and not confirm_official_ui:
        validation = dict(validation)
        validation["status"] = "blocked"
        validation["blockers"] = list(validation.get("blockers", [])) + ["execute_requires_confirm_official_ui_flag"]
        report_status = "blocked"

    should_touch_window = report_status in {"ready_for_dry_run", "ready_for_execute"}
    if execute and report_status == "ready_for_execute":
        should_touch_window = True
    if should_touch_window:
        if window_finder is None or point_resolver is None or clicker is None:
            window_finder, point_resolver, clicker = load_click_probe()
        try:
            selected = selected_window(window_finder(str(manifest.get("window_title") or "米游社")), match_index)
            for step in click_steps(manifest):
                point = point_resolver(selected, int(step["x"]), int(step["y"]))
                step_result: dict[str, Any] = {
                    "id": step.get("id"),
                    "title": step.get("title"),
                    "action": step.get("action"),
                    "status": "clicked" if execute else "resolved",
                    "point": point,
                }
                if execute:
                    clicker(point["absolute"]["x"], point["absolute"]["y"])
                    clicked_count += 1
                    wait_after_step(step.get("wait_after_seconds"), execute=True)
                step_results.append(step_result)
            report_status = "executed" if execute else "ready_for_dry_run"
        except Exception as exc:  # noqa: BLE001 - convert Windows/click probe errors into local reports.
            validation = dict(validation)
            validation["status"] = "blocked"
            validation["blockers"] = list(validation.get("blockers", [])) + ["window_or_coordinate_resolution_failed"]
            validation["warnings"] = list(validation.get("warnings", [])) + [str(exc)]
            report_status = "blocked"
    else:
        for step in enabled_steps(manifest):
            if step.get("action") == "official_ui_click":
                state = coordinate_state(step)
                step_results.append(
                    {
                        "id": step.get("id"),
                        "title": step.get("title"),
                        "action": step.get("action"),
                        "status": "missing_coordinate" if state == "missing" else "needs_confirmation",
                        "x": step.get("x"),
                        "y": step.get("y"),
                        "confirmed_official_ui": step.get("confirmed_official_ui") is True,
                    }
                )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at": now_iso(),
        "manifest_path": str(manifest_path),
        "manifest_schema_version": manifest.get("schema_version"),
        "game": manifest.get("game"),
        "window_title": manifest.get("window_title"),
        "image_inbox": manifest.get("image_inbox"),
        "dry_run": not execute,
        "execute_requested": bool(execute),
        "confirm_official_ui": bool(confirm_official_ui),
        "status": report_status,
        "next_action": next_action_for_status(report_status),
        "validation": validation,
        "window": selected,
        "step_results": step_results,
        "clicked_count": clicked_count,
        "does_not": manifest.get("does_not") if isinstance(manifest.get("does_not"), list) else [],
    }


def render_html(report: dict[str, Any]) -> str:
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    steps = report.get("step_results") if isinstance(report.get("step_results"), list) else []
    step_cards = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "")
        tone = "ok" if status in {"resolved", "clicked"} else "warn"
        point = step.get("point") if isinstance(step.get("point"), dict) else {}
        relative = point.get("relative") if isinstance(point.get("relative"), dict) else {}
        absolute = point.get("absolute") if isinstance(point.get("absolute"), dict) else {}
        coord_text = ""
        if relative or absolute:
            coord_text = f"relative=({relative.get('x')}, {relative.get('y')}) absolute=({absolute.get('x')}, {absolute.get('y')})"
        elif step.get("x") is not None or step.get("y") is not None:
            coord_text = f"relative=({step.get('x')}, {step.get('y')})"
        step_cards.append(
            f'<article class="step {tone}">'
            f"<b>{index}</b>"
            "<div>"
            f"<h3>{escape(str(step.get('title') or step.get('id') or ''))}</h3>"
            f"<span>{escape(status)}</span>"
            f"<p>{escape(coord_text)}</p>"
            "</div>"
            "</article>"
        )
    warnings = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    blockers = validation.get("blockers") if isinstance(validation.get("blockers"), list) else []
    warning_items = "".join(f"<li>{escape(str(item))}</li>" for item in warnings) or "<li>无</li>"
    blocker_items = "".join(f"<li>{escape(str(item))}</li>" for item in blockers) or "<li>无</li>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>米游社导出校准执行报告</title>
  <style>
    body {{ margin: 0; background: #f6f8fb; color: #172033; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; }}
    header {{ padding: 26px 30px; background: #101827; color: #fff; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric, .panel, .step {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08); }}
    .metric {{ padding: 14px; }}
    .metric span {{ display: block; color: #64748b; font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 22px; overflow-wrap: anywhere; }}
    .panel {{ padding: 16px; }}
    .panel h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .steps {{ display: grid; gap: 12px; }}
    .step {{ display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 12px; padding: 14px; }}
    .step b {{ display: grid; place-items: center; width: 34px; height: 34px; border-radius: 999px; background: #fff4d8; color: #9a6500; }}
    .step.ok b {{ background: #e9f8ef; color: #16834a; }}
    .step h3 {{ margin: 0 0 5px; font-size: 16px; }}
    .step span {{ color: #64748b; font-size: 13px; }}
    .step p {{ margin: 6px 0 0; line-height: 1.45; overflow-wrap: anywhere; }}
    code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; white-space: pre-wrap; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>米游社导出校准执行报告</h1>
    <p>默认 dry-run；真正点击必须显式 --execute --confirm-official-ui。</p>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><span>状态</span><strong>{escape(str(report.get("status") or ""))}</strong></div>
      <div class="metric"><span>模式</span><strong>{escape("dry-run" if report.get("dry_run") else "execute")}</strong></div>
      <div class="metric"><span>点击次数</span><strong>{escape(str(report.get("clicked_count") or 0))}</strong></div>
      <div class="metric"><span>缺坐标</span><strong>{escape(str(validation.get("missing_coordinate_count") or 0))}</strong></div>
      <div class="metric"><span>未确认</span><strong>{escape(str(validation.get("unconfirmed_step_count") or 0))}</strong></div>
    </section>
    <section class="panel">
      <h2>下一步</h2>
      <p>{escape(str(report.get("next_action") or ""))}</p>
      <code>{escape(str(report.get("manifest_path") or ""))}</code>
    </section>
    <section class="panel">
      <h2>阻断项</h2>
      <ul>{blocker_items}</ul>
    </section>
    <section class="panel">
      <h2>警告</h2>
      <ul>{warning_items}</ul>
    </section>
    <section class="steps">{''.join(step_cards)}</section>
  </main>
</body>
</html>
"""


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, Path | dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "miyoushe_app_export_run_report.json"
    html_path = output_dir / "miyoushe_app_export_run_report.html"
    report = dict(report)
    report["output_json"] = str(json_path)
    report["output_html"] = str(html_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return {"report": report, "json_path": json_path, "html_path": html_path}


def run_manifest(
    *,
    manifest_path: Path,
    output_dir: Path,
    execute: bool = False,
    confirm_official_ui: bool = False,
    match_index: int = 0,
    window_finder: WindowFinder | None = None,
    point_resolver: PointResolver | None = None,
    clicker: Clicker | None = None,
) -> dict[str, Path | dict[str, Any]]:
    manifest = load_manifest(manifest_path)
    report = build_report(
        manifest_path=manifest_path,
        manifest=manifest,
        execute=execute,
        confirm_official_ui=confirm_official_ui,
        match_index=match_index,
        window_finder=window_finder,
        point_resolver=point_resolver,
        clicker=clicker,
    )
    return write_report(report, output_dir)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a calibrated MiYouShe official UI export checklist.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Calibration manifest JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Report output directory.")
    parser.add_argument("--match-index", type=int, default=0, help="Window match index if multiple windows match. Default: 0")
    parser.add_argument("--execute", action="store_true", help="Actually click the calibrated official UI steps.")
    parser.add_argument(
        "--confirm-official-ui",
        action="store_true",
        help="Required with --execute to confirm every step targets official MiYouShe UI.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = run_manifest(
            manifest_path=resolve_path(args.manifest),
            output_dir=resolve_path(args.output_dir),
            execute=args.execute,
            confirm_official_ui=args.confirm_official_ui,
            match_index=args.match_index,
        )
    except AppExportRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    report = result["report"]
    print(f"app_export_run_status: {report.get('status')}")
    print(f"app_export_run_json: {result['json_path']}")
    print(f"app_export_run_html: {result['html_path']}")
    print(f"app_export_run_next: {report.get('next_action')}")
    return 1 if report.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
