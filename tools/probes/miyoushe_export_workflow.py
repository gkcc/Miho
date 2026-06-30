#!/usr/bin/env python
"""Build a local, auditable workflow package for MiYouShe official share-image export."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo" / "app_export_workflow"
DEFAULT_IMAGE_INBOX = PROJECT_ROOT / "figs"
SCHEMA_VERSION = "p4.2-miyoushe-official-export-workflow"

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
    </section>
    <section class="panel">
      <h2>边界</h2>
      <p>只允许官方 UI 内的可见操作；保存图片进入 {escape(str(workflow.get("image_inbox") or ""))}，后续解析仍需人工复核。</p>
      <ul>{''.join(f"<li>{escape(str(item))}</li>" for item in workflow.get("does_not", []))}</ul>
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


def build_package(*, output_dir: Path, image_inbox: Path, game: str, window_title: str) -> dict[str, Path | dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    workflow = build_workflow(game=game, window_title=window_title, image_inbox=image_inbox)
    validation = validate_workflow(workflow)
    package = {"workflow": workflow, "validation": validation}
    json_path = output_dir / "miyoushe_export_workflow.json"
    html_path = output_dir / "miyoushe_export_workflow.html"
    json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_html(package), encoding="utf-8")
    return {"workflow": package, "json_path": json_path, "html_path": html_path}


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
    return 0 if validation.get("status") != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
