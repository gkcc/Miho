#!/usr/bin/env python
"""Build a local, auditable workflow package for MiYouShe official share-image export."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any

import miyoushe_app_export_runner as app_export_runner


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo" / "app_export_workflow"
DEFAULT_IMAGE_INBOX = PROJECT_ROOT / "figs"
SCHEMA_VERSION = "p4.3-miyoushe-official-export-workflow"
CALIBRATION_TEMPLATE_FILENAME = "miyoushe_app_export_calibration_template.json"

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


def command_text(parts: list[str]) -> str:
    return " ".join(parts)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def default_steps() -> list[dict[str, Any]]:
    return [
        {
            "id": "precheck_window",
            "title": "确认米游社 APP 已打开并已登录",
            "stage": "precheck",
            "current_support": "dry_run",
            "automation_strategy": "window_title_match",
            "uia_keywords": ["米游社"],
            "allowed_action": "read_visible_window_title",
            "user_visible_result": "找到米游社窗口后才允许继续。",
        },
        {
            "id": "go_profile",
            "title": "进入我的",
            "stage": "navigation",
            "current_support": "planned",
            "automation_strategy": "official_ui_click",
            "uia_keywords": ["我的"],
            "allowed_action": "official_ui_only_click",
            "user_visible_result": "进入个人页，不读取账号文件或登录态。",
        },
        {
            "id": "go_battle_record",
            "title": "进入战绩",
            "stage": "navigation",
            "current_support": "planned",
            "automation_strategy": "official_ui_click",
            "uia_keywords": ["战绩", "战绩统计"],
            "allowed_action": "official_ui_only_click",
            "user_visible_result": "进入官方战绩页。",
        },
        {
            "id": "go_agent_list",
            "title": "进入代理人列表",
            "stage": "navigation",
            "current_support": "planned",
            "automation_strategy": "official_ui_click",
            "uia_keywords": ["代理人", "角色"],
            "allowed_action": "official_ui_only_click",
            "user_visible_result": "进入绝区零代理人列表。",
        },
        {
            "id": "open_agent_detail",
            "title": "打开代理人详情",
            "stage": "navigation",
            "current_support": "planned",
            "automation_strategy": "official_ui_click_or_user_selection",
            "uia_keywords": ["详情", "代理人详情"],
            "allowed_action": "official_ui_only_click",
            "user_visible_result": "打开单个代理人练度页。",
        },
        {
            "id": "open_share_menu",
            "title": "打开右上角分享菜单",
            "stage": "export",
            "current_support": "planned",
            "automation_strategy": "official_ui_click",
            "uia_keywords": ["分享", "更多", "导出"],
            "allowed_action": "official_ui_only_click",
            "user_visible_result": "只触发官方分享/导出入口。",
        },
        {
            "id": "save_share_image",
            "title": "保存官方分享图",
            "stage": "export",
            "current_support": "manual_page_probe_available",
            "automation_strategy": "uia_find_share_or_save_button",
            "uia_keywords": ["分享图", "导出图片", "保存图片", "保存到本地"],
            "allowed_action": "uia_invoke_official_button",
            "user_visible_result": "新图片进入本地图片收件箱。",
        },
        {
            "id": "parse_saved_image",
            "title": "解析保存后的分享图",
            "stage": "parse",
            "current_support": "implemented",
            "automation_strategy": "local_image_pipeline",
            "command": "dist\\MihoProbe.exe update",
            "allowed_action": "local_file_parse_requires_review",
            "user_visible_result": "生成 Dashboard、复核页和标准化候选快照。",
        },
    ]


def default_calibration_commands(*, game: str, window_title: str, image_inbox: Path) -> list[dict[str, Any]]:
    inbox = rel_path(image_inbox)
    return [
        {
            "id": "find_window",
            "title": "确认能找到米游社窗口",
            "purpose": "只读窗口标题和窗口大小，不截图、不点击。",
            "command": command_text(
                ["python", "tools/probes/window_screenshot_probe.py", "--window-title", window_title, "--dry-run"]
            ),
            "expected_signal": "输出 matched_windows，并且 selected.title 包含米游社。",
        },
        {
            "id": "capture_grid",
            "title": "生成坐标网格截图",
            "purpose": "人工标注我的、战绩、代理人、分享、保存图片按钮的大致窗口相对坐标。",
            "command": command_text(
                ["python", "tools/probes/window_screenshot_probe.py", "--window-title", window_title, "--grid-size", "100"]
            ),
            "expected_signal": "data/probes/window_screenshots 下生成带网格的截图和 JSON。",
        },
        {
            "id": "probe_visible_share_controls",
            "title": "只读探测分享/保存按钮",
            "purpose": "如果当前页已经在分享入口附近，尝试用可见控件文本找到官方分享或保存按钮。",
            "command": command_text(
                [
                    "python",
                    "tools/probes/miyoushe_export_image_probe.py",
                    "--game",
                    game,
                    "--mode",
                    "manual-page",
                    "--window-title",
                    window_title,
                    "--dry-run",
                ]
            ),
            "expected_signal": "报告 share/save 候选控件；找不到也不点击。",
        },
        {
            "id": "run_calibration_manifest",
            "title": "运行整条校准清单 dry-run",
            "purpose": "读取 calibration_template.json，统一提示缺坐标、未确认或可执行状态；默认不点击。",
            "command": command_text(
                [
                    "dist\\MihoProbe.exe",
                    "app-export-run",
                    "--manifest",
                    f"data/probes/demo/app_export_workflow/{CALIBRATION_TEMPLATE_FILENAME}",
                    "--no-open",
                ]
            ),
            "expected_signal": "输出 needs_coordinates / needs_confirmation / ready_for_dry_run，并生成执行报告。",
        },
        {
            "id": "dry_run_coordinate",
            "title": "校验单个相对坐标",
            "purpose": "把人工标注的坐标先 dry-run 解析成绝对坐标，确认仍在米游社窗口内。",
            "command": command_text(
                [
                    "python",
                    "tools/probes/click_relative_probe.py",
                    "--window-title",
                    window_title,
                    "--x",
                    "<x>",
                    "--y",
                    "<y>",
                ]
            ),
            "expected_signal": "输出 clicked=false 和窗口内 absolute 坐标。",
        },
        {
            "id": "execute_confirmed_coordinate",
            "title": "只执行已确认官方 UI 坐标",
            "purpose": "只有人工确认目标是米游社官方 UI 按钮后，才允许单点执行。",
            "command": command_text(
                [
                    "python",
                    "tools/probes/click_relative_probe.py",
                    "--window-title",
                    window_title,
                    "--x",
                    "<x>",
                    "--y",
                    "<y>",
                    "--execute",
                    "--confirm-official-ui",
                ]
            ),
            "expected_signal": "只点击一次官方 UI；不得用于登录、验证码、游戏客户端或非米游社窗口。",
        },
        {
            "id": "parse_saved_images",
            "title": "解析保存后的分享图",
            "purpose": "官方分享图保存到本地收件箱后，回到本地解析和人工复核。",
            "command": command_text(["dist\\MihoProbe.exe", "update", "--images-dir", inbox, "--open"]),
            "expected_signal": "Dashboard、review HTML、parsed JSON 更新；OCR 结果仍需人工确认。",
        },
    ]


def default_operator_checklist() -> list[str]:
    return [
        "用户先手动打开米游社 APP，并确认账号已登录。",
        "先跑 find_window；找不到窗口时不继续。",
        "先生成网格截图并人工标注官方 UI 坐标，不猜坐标。",
        "每个坐标先 dry-run；确认在窗口内、目标是官方 UI 后才允许 execute。",
        "不点击登录、验证码、广告、隐私弹窗、游戏客户端或任何非米游社窗口。",
        "保存图片后只进入 figs/ 或用户指定图片收件箱，再走本地 update 和人工复核。",
    ]


def default_operator_route(image_inbox: Path) -> dict[str, Any]:
    inbox = rel_path(image_inbox)
    calibration_path = f"data/probes/demo/app_export_workflow/{CALIBRATION_TEMPLATE_FILENAME}"
    return {
        "route_title": "官方分享图路线",
        "current_route_status": "calibration_required",
        "automation_status": "disabled_until_calibrated",
        "next_command": f"dist\\MihoProbe.exe app-export-run --manifest {calibration_path} --no-open",
        "calibration_manifest": calibration_path,
        "calibrate_command": f"dist\\MihoProbe.exe app-export-calibrate --manifest {calibration_path} --open",
        "dry_run_command": f"dist\\MihoProbe.exe app-export-run --manifest {calibration_path} --no-open",
        "execute_command": (
            f"dist\\MihoProbe.exe app-export-run --manifest {calibration_path} "
            "--execute --confirm-official-ui --no-open"
        ),
        "manual_save_to_figs_step": f"在米游社官方 UI 保存分享图到 {inbox}，或手动把官方分享图放进该目录。",
        "update_command": "dist\\MihoProbe.exe update --open",
        "review_gate": "Dashboard 人工复核通过后，才允许进入本地 accepted roster / 高难建议。",
        "route_steps": [
            {
                "label": "1. 打开官方 APP",
                "status": "manual",
                "description": "用户手动打开已登录的米游社 APP；工具不登录、不读 cookie/token。",
                "command": "",
            },
            {
                "label": "2. 校准官方 UI",
                "status": "needed",
                "description": "先生成校准清单，再用网格截图填 x/y；坐标必须由用户确认是官方 UI。",
                "command": f"dist\\MihoProbe.exe app-export-calibrate --manifest {calibration_path} --open",
            },
            {
                "label": "3. 保存官方分享图",
                "status": "manual_or_confirmed_ui_only",
                "description": f"图片进入 {inbox}；不自动点击登录、验证码、广告或游戏客户端。",
                "command": "",
            },
            {
                "label": "4. 本地更新 Dashboard",
                "status": "implemented",
                "description": "只处理本地官方分享图，失败时必须显式非 0 或显示阻断状态。",
                "command": "dist\\MihoProbe.exe update --open",
            },
            {
                "label": "5. 人工复核后再采用",
                "status": "required",
                "description": "OCR/解析候选只进待复核区；人工确认前不进入正式建议依据。",
                "command": "",
            },
        ],
    }


def default_readiness_gates() -> list[dict[str, str]]:
    return [
        {
            "id": "window_found",
            "label": "找到米游社窗口",
            "status": "needed",
            "evidence": "find_window 输出 matched_windows。",
        },
        {
            "id": "coordinates_calibrated",
            "label": "官方 UI 坐标已校准",
            "status": "needed",
            "evidence": "capture_grid 截图 + dry_run_coordinate 证明坐标仍在窗口内。",
        },
        {
            "id": "official_ui_confirmed",
            "label": "只点击已确认官方 UI",
            "status": "needed",
            "evidence": "execute 命令必须带 --confirm-official-ui。",
        },
        {
            "id": "share_image_saved",
            "label": "官方分享图进入 figs",
            "status": "user_action_needed",
            "evidence": "figs/ 下出现用户确认的官方分享图。",
        },
        {
            "id": "local_update_parse",
            "label": "本地 update 可运行",
            "status": "implemented",
            "evidence": "dist\\MihoProbe.exe update --open 生成 Dashboard 或显式失败。",
        },
        {
            "id": "manual_review_gate",
            "label": "人工复核闸门",
            "status": "required_before_import",
            "evidence": "Dashboard/review HTML 确认字段后才可进入 accepted roster。",
        },
    ]


def build_workflow(*, game: str, window_title: str, image_inbox: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "game": game,
        "workflow_name": "米游社官方分享图一键更新练度",
        "current_execution_level": "workflow_defined_dry_run",
        "window_title": window_title,
        "image_inbox": rel_path(image_inbox),
        "official_ui_only": True,
        "requires_user_logged_in_app": True,
        "does_not": list(FORBIDDEN_CAPABILITIES),
        "next_implementation_step": "把 planned 导航步骤逐个绑定 UIA selector 或经用户确认的窗口相对坐标。",
        "operator_route": default_operator_route(image_inbox),
        "calibration_template": f"data/probes/demo/app_export_workflow/{CALIBRATION_TEMPLATE_FILENAME}",
        "readiness_gates": default_readiness_gates(),
        "operator_checklist": default_operator_checklist(),
        "calibration_commands": default_calibration_commands(
            game=game,
            window_title=window_title,
            image_inbox=image_inbox,
        ),
        "steps": default_steps(),
    }


def validate_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if workflow.get("official_ui_only") is not True:
        blockers.append("official_ui_only_not_confirmed")
    forbidden = set(workflow.get("does_not") if isinstance(workflow.get("does_not"), list) else [])
    missing_forbidden = [item for item in FORBIDDEN_CAPABILITIES if item not in forbidden]
    if missing_forbidden:
        blockers.append("missing_forbidden_capability_boundary")
        warnings.append("missing: " + ", ".join(missing_forbidden))
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    if not steps:
        blockers.append("missing_workflow_steps")
    implemented = [step for step in steps if isinstance(step, dict) and step.get("current_support") == "implemented"]
    planned = [step for step in steps if isinstance(step, dict) and step.get("current_support") == "planned"]
    if planned:
        warnings.append(f"{len(planned)} navigation step(s) still need UIA selector calibration.")
    return {
        "status": "blocked" if blockers else "ready_for_calibration",
        "blockers": blockers,
        "warnings": warnings,
        "step_count": len(steps),
        "implemented_step_count": len(implemented),
        "planned_step_count": len(planned),
        "readiness_gate_count": len(workflow.get("readiness_gates", []))
        if isinstance(workflow.get("readiness_gates"), list)
        else 0,
        "calibration_command_count": len(workflow.get("calibration_commands", []))
        if isinstance(workflow.get("calibration_commands"), list)
        else 0,
    }


def render_html(package: dict[str, Any]) -> str:
    workflow = package["workflow"]
    validation = package["validation"]
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    step_cards = []
    for index, step in enumerate(steps, start=1):
        tone = "ok" if step.get("current_support") == "implemented" else "warn"
        if step.get("current_support") in {"dry_run", "manual_page_probe_available"}:
            tone = "soft"
        step_cards.append(
            f'<article class="step {tone}">'
            f"<b>{index}</b>"
            "<div>"
            f"<h3>{escape(str(step.get('title') or step.get('id') or ''))}</h3>"
            f"<p>{escape(str(step.get('user_visible_result') or ''))}</p>"
            f"<span>{escape(str(step.get('current_support') or ''))} · {escape(str(step.get('allowed_action') or ''))}</span>"
            f"<em>{escape(' / '.join(str(item) for item in step.get('uia_keywords', [])) if isinstance(step.get('uia_keywords'), list) else '')}</em>"
            "</div>"
            "</article>"
        )
    warnings = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    warning_items = "".join(f"<li>{escape(str(item))}</li>" for item in warnings) or "<li>无</li>"
    route = workflow.get("operator_route") if isinstance(workflow.get("operator_route"), dict) else {}
    calibration_template = str(route.get("calibration_manifest") or workflow.get("calibration_template") or "")
    calibrate_command = str(route.get("calibrate_command") or "")
    dry_run_command = str(route.get("dry_run_command") or route.get("next_command") or "")
    execute_command = str(route.get("execute_command") or "")
    route_steps = route.get("route_steps") if isinstance(route.get("route_steps"), list) else []
    route_cards = []
    for step in route_steps:
        if not isinstance(step, dict):
            continue
        command = str(step.get("command") or "")
        command_html = f"<code>{escape(command)}</code>" if command else ""
        route_cards.append(
            '<article class="route-card">'
            f"<b>{escape(str(step.get('label') or ''))}</b>"
            f"<span>{escape(str(step.get('status') or ''))}</span>"
            f"<p>{escape(str(step.get('description') or ''))}</p>"
            f"{command_html}"
            "</article>"
        )
    gates = workflow.get("readiness_gates") if isinstance(workflow.get("readiness_gates"), list) else []
    gate_cards = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gate_cards.append(
            '<article class="gate">'
            f"<b>{escape(str(gate.get('label') or gate.get('id') or ''))}</b>"
            f"<span>{escape(str(gate.get('status') or ''))}</span>"
            f"<p>{escape(str(gate.get('evidence') or ''))}</p>"
            "</article>"
        )
    checklist = workflow.get("operator_checklist") if isinstance(workflow.get("operator_checklist"), list) else []
    checklist_items = "".join(f"<li>{escape(str(item))}</li>" for item in checklist) or "<li>无</li>"
    commands = workflow.get("calibration_commands") if isinstance(workflow.get("calibration_commands"), list) else []
    command_cards = []
    for command in commands:
        if not isinstance(command, dict):
            continue
        command_cards.append(
            '<article class="command">'
            f"<h3>{escape(str(command.get('title') or command.get('id') or ''))}</h3>"
            f"<p>{escape(str(command.get('purpose') or ''))}</p>"
            f"<code>{escape(str(command.get('command') or ''))}</code>"
            f"<span>{escape(str(command.get('expected_signal') or ''))}</span>"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>米游社分享图工作流</title>
  <style>
    body {{ margin: 0; background: #f6f8fb; color: #172033; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; }}
    header {{ padding: 26px 30px; background: #101827; color: #fff; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; }}
    header p {{ margin: 0; color: #cbd5e1; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
    .metric, .panel, .step {{ background: #fff; border: 1px solid #dbe3ef; border-radius: 8px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08); }}
    .metric {{ padding: 14px; }}
    .metric span, .step span, .step em {{ display: block; color: #64748b; font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 22px; }}
    .panel {{ padding: 16px; }}
    .panel h2 {{ margin: 0 0 10px; font-size: 18px; }}
    .steps {{ display: grid; gap: 12px; }}
    .step {{ display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 12px; padding: 14px; }}
    .step b {{ display: grid; place-items: center; width: 34px; height: 34px; border-radius: 999px; background: #e2e8f0; }}
    .step h3 {{ margin: 0 0 5px; font-size: 16px; }}
    .step p {{ margin: 0 0 6px; line-height: 1.45; }}
    .step.ok b {{ background: #e9f8ef; color: #16834a; }}
    .step.warn b {{ background: #fff4d8; color: #9a6500; }}
    .step.soft b {{ background: #eff6ff; color: #1d4ed8; }}
    .commands {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }}
    .route, .gates {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .route-card, .gate {{ display: grid; gap: 8px; padding: 14px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fbfcff; }}
    .route-card b, .gate b {{ font-size: 15px; }}
    .route-card span, .gate span {{ width: fit-content; padding: 4px 8px; border-radius: 999px; background: #fff4d8; color: #9a6500; font-size: 12px; font-weight: 900; }}
    .route-card p, .gate p {{ margin: 0; color: #475569; line-height: 1.45; }}
    .route-card code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .command {{ display: grid; gap: 8px; padding: 14px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fbfcff; }}
    .command h3 {{ margin: 0; font-size: 16px; }}
    .command p {{ margin: 0; color: #475569; line-height: 1.45; }}
    .command code {{ display: block; padding: 10px; border-radius: 8px; background: #0f172a; color: #e2e8f0; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .command span {{ color: #64748b; font-size: 13px; }}
    ul {{ margin: 8px 0 0; padding-left: 20px; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(str(workflow.get("workflow_name") or "米游社分享图工作流"))}</h1>
    <p>当前只生成可审计工作流，不自动登录、不读 token、不抓包、不控制游戏客户端。</p>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><span>当前状态</span><strong>{escape(str(validation.get("status") or ""))}</strong></div>
      <div class="metric"><span>步骤数</span><strong>{escape(str(validation.get("step_count") or 0))}</strong></div>
      <div class="metric"><span>已实现步骤</span><strong>{escape(str(validation.get("implemented_step_count") or 0))}</strong></div>
      <div class="metric"><span>待校准导航</span><strong>{escape(str(validation.get("planned_step_count") or 0))}</strong></div>
      <div class="metric"><span>复核闸门</span><strong>{escape(str(validation.get("readiness_gate_count") or 0))}</strong></div>
    </section>
    <section class="panel">
      <h2>当前还不是自动点击</h2>
      <p>{escape(str(route.get("route_title") or "官方分享图路线"))}：{escape(str(route.get("current_route_status") or ""))}；自动化状态：{escape(str(route.get("automation_status") or ""))}。</p>
      <p>下一步：{escape(str(route.get("next_command") or ""))}</p>
      <p>更新命令：{escape(str(route.get("update_command") or ""))}</p>
      <p>复核闸门：{escape(str(route.get("review_gate") or ""))}</p>
      <div class="route">{''.join(route_cards)}</div>
    </section>
    <section class="panel">
      <h2>可执行校准清单</h2>
      <p>先打开 JSON 填 x/y；填完后先 dry-run。真正点击必须额外输入 execute 命令和确认参数。</p>
      <p>清单：{escape(calibration_template)}</p>
      <div class="commands">
        <article class="command">
          <h3>先生成网格截图</h3>
          <p>捕获米游社窗口并显示待填坐标表，不点击。</p>
          <code>{escape(calibrate_command)}</code>
          <span>没有打开米游社时会显示 window_missing。</span>
        </article>
        <article class="command">
          <h3>先 dry-run</h3>
          <p>只解析窗口和坐标，不点击。</p>
          <code>{escape(dry_run_command)}</code>
          <span>缺坐标时报告 needs_coordinates，不会触碰窗口。</span>
        </article>
        <article class="command">
          <h3>确认后执行</h3>
          <p>只有全部坐标人工确认是米游社官方 UI 后才允许。</p>
          <code>{escape(execute_command)}</code>
          <span>仍然不登录、不读 token、不控制游戏客户端。</span>
        </article>
      </div>
    </section>
    <section class="panel">
      <h2>Readiness Gates</h2>
      <div class="gates">{''.join(gate_cards)}</div>
    </section>
    <section class="panel">
      <h2>边界</h2>
      <p>只允许官方 UI 内的可见操作；保存图片进入 {escape(str(workflow.get("image_inbox") or ""))}，后续解析仍需人工复核。</p>
      <ul>{''.join(f"<li>{escape(str(item))}</li>" for item in workflow.get("does_not", []))}</ul>
    </section>
    <section class="panel">
      <h2>操作前检查</h2>
      <ul>{checklist_items}</ul>
    </section>
    <section class="panel">
      <h2>警告</h2>
      <ul>{warning_items}</ul>
    </section>
    <section class="panel">
      <h2>下一步校准命令</h2>
      <div class="commands">{''.join(command_cards)}</div>
    </section>
    <section class="steps">{''.join(step_cards)}</section>
  </main>
</body>
</html>
"""


def build_package(*, output_dir: Path, image_inbox: Path, game: str, window_title: str) -> dict[str, Path | dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    workflow = build_workflow(game=game, window_title=window_title, image_inbox=image_inbox)
    calibration_template_path = output_dir / CALIBRATION_TEMPLATE_FILENAME
    app_export_runner.write_calibration_template(
        path=calibration_template_path,
        game=game,
        window_title=window_title,
        image_inbox=image_inbox,
    )
    validation = validate_workflow(workflow)
    package = {"workflow": workflow, "validation": validation}
    json_path = output_dir / "miyoushe_export_workflow.json"
    html_path = output_dir / "miyoushe_export_workflow.html"
    json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(package), encoding="utf-8")
    return {
        "workflow": package,
        "json_path": json_path,
        "html_path": html_path,
        "calibration_template_path": calibration_template_path,
    }


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the local MiYouShe official share-image export workflow package.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--image-inbox", default=str(DEFAULT_IMAGE_INBOX))
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument("--window-title", default="米游社")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    result = build_package(
        output_dir=resolve_path(args.output_dir),
        image_inbox=resolve_path(args.image_inbox),
        game=args.game,
        window_title=args.window_title,
    )
    workflow = result["workflow"]
    validation = workflow["validation"] if isinstance(workflow, dict) else {}
    print(f"workflow_status: {validation.get('status')}")
    print(f"workflow_json: {result['json_path']}")
    print(f"workflow_html: {result['html_path']}")
    print(f"calibration_template_json: {result['calibration_template_path']}")
    return 0 if validation.get("status") != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
