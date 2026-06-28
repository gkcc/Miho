#!/usr/bin/env python
"""Render a static local HTML dashboard for the Miho probe demo pipeline."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "probes" / "demo" / "index.html"


class DashboardError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DashboardError(f"Summary JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DashboardError(f"Invalid summary JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise DashboardError("Summary JSON must be an object")
    return data


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def file_href(value: Any) -> str:
    if not value:
        return ""
    path = Path(str(value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        return path.resolve().as_uri()
    except ValueError:
        return ""


def rel_label(value: Any) -> str:
    if not value:
        return ""
    path = Path(str(value))
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except (ValueError, OSError):
        return str(value)


def status_class(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"pass", "done", "ok", "true"}:
        return "ok"
    if text in {"needs_review", "needs-review", "uncertain", "skipped", "n/a"}:
        return "warn"
    if text in {"fail", "failed", "false", "error"}:
        return "bad"
    return "muted"


def link(label: str, value: Any) -> str:
    if not value:
        return f'<span class="missing">{e(label)} missing</span>'
    href = file_href(value)
    if not href:
        return f'<span class="missing">{e(label)} unavailable</span>'
    return f'<a href="{e(href)}">{e(label)}</a>'


def metric_card(label: str, value: Any, tone: str = "muted") -> str:
    return f'<div class="metric {e(tone)}"><span>{e(label)}</span><strong>{e(value)}</strong></div>'


def basename(value: Any) -> str:
    if not value:
        return ""
    return Path(str(value)).name


def render_steps(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return ""
    items = []
    for step in steps:
        status = str(step.get("status") or "skipped")
        items.append(
            f'<div class="step {status_class(status)}">'
            f'<span class="dot"></span><strong>{e(step.get("name"))}</strong><em>{e(status)}</em></div>'
        )
    return '<section class="panel"><h2>Pipeline 进度</h2><div class="steps">' + "".join(items) + "</div></section>"


def render_case(case: dict[str, Any]) -> str:
    image = case.get("thumbnail") or case.get("image")
    image_src = file_href(image)
    character = case.get("character", {}) if isinstance(case.get("character"), dict) else {}
    equipment = case.get("equipment", {}) if isinstance(case.get("equipment"), dict) else {}
    quality = case.get("quality", {}) if isinstance(case.get("quality"), dict) else {}
    blockers = quality.get("blockers") if isinstance(quality.get("blockers"), list) else []
    pass_rate = "N/A" if case.get("pass_rate") is None else f"{round(float(case.get('pass_rate')) * 100, 2)}%"
    image_html = (
        f'<img src="{e(image_src)}" alt="{e(case.get("name"))}">'
        if image_src
        else '<div class="thumb-empty">No image</div>'
    )
    blocker_html = "".join(f"<li>{e(item)}</li>" for item in blockers) or "<li>none</li>"
    errors = case.get("errors") if isinstance(case.get("errors"), list) else []
    error_html = "".join(f"<li>{e(item)}</li>" for item in errors)
    if error_html:
        error_html = f'<div class="errors"><strong>Errors</strong><ul>{error_html}</ul></div>'
    expected_name = case.get("expected_json_name") or basename(case.get("expected_json")) or "missing"

    return f"""
    <article class="case-card">
      <div class="thumb">{image_html}</div>
      <div class="case-body">
        <div class="case-head">
          <h3>{e(case.get("name"))}</h3>
          <span class="badge {status_class(case.get("review_status"))}">{e(case.get("review_status") or "N/A")}</span>
        </div>
        <div class="facts">
          <div><span>角色</span><strong>{e(character.get("name") or "")}</strong></div>
          <div><span>等级</span><strong>{e(character.get("level") or "")}</strong></div>
          <div><span>评级</span><strong>{e(character.get("rank") or "")}</strong></div>
          <div><span>音擎</span><strong>{e(equipment.get("name") or "")}</strong></div>
          <div><span>覆盖</span><strong>{e(case.get("coverage_level") or "")}</strong></div>
          <div><span>Expected</span><strong>{e(pass_rate)}</strong></div>
          <div><span>Expected JSON</span><strong>{e(expected_name)}</strong></div>
          <div><span>可信字段</span><strong>{e(quality.get("trusted_field_count"))}/{e(quality.get("field_count"))}</strong></div>
          <div><span>人工确认</span><strong>{e(quality.get("requires_manual_review"))}</strong></div>
        </div>
        <div class="links">
          {link("review_html", case.get("review_html"))}
          {link("parsed_json", case.get("parsed_json"))}
          {link("expected_json", case.get("expected_json"))}
          {link("normalized_md", case.get("normalized_md"))}
          {link("normalized_json", case.get("normalized_json"))}
          {link("expected_diff_md", case.get("expected_diff_md"))}
          {link("crops_dir", case.get("crops_dir"))}
        </div>
        <details>
          <summary>Quality blockers</summary>
          <ul>{blocker_html}</ul>
        </details>
        {error_html}
      </div>
    </article>
    """


def render_input_panel(summary: dict[str, Any]) -> str:
    input_info = summary.get("input", {}) if isinstance(summary.get("input"), dict) else {}
    warnings = summary.get("warnings", []) if isinstance(summary.get("warnings"), list) else []
    source_mode = input_info.get("source_mode") or "unknown mode"
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warnings_block = f'<div class="warnings"><strong>Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    return f"""
    <section class="panel input-panel">
      <h2>输入模式</h2>
      <div class="input-grid">
        <div><span>Mode</span><strong>{e(source_mode)}</strong></div>
        <div><span>images_dir</span><strong>{e(rel_label(input_info.get("images_dir")) or "N/A")}</strong></div>
        <div><span>parsed_dir</span><strong>{e(rel_label(input_info.get("parsed_dir")) or "N/A")}</strong></div>
        <div><span>manifest</span><strong>{e(rel_label(input_info.get("manifest")) or "N/A")}</strong></div>
        <div><span>targets</span><strong>{e(rel_label(input_info.get("targets")) or "N/A")}</strong></div>
        <div><span>target_source_manifest</span><strong>{e(rel_label(input_info.get("target_source_manifest")) or "N/A")}</strong></div>
        <div><span>history_dir</span><strong>{e(rel_label(input_info.get("history_dir")) or "N/A")}</strong></div>
        <div><span>latest_only</span><strong>{e(input_info.get("latest_only"))}</strong></div>
        <div><span>new_only</span><strong>{e(input_info.get("new_only"))}</strong></div>
        <div><span>clean_demo</span><strong>{e(input_info.get("clean_demo"))}</strong></div>
        <div><span>state_file</span><strong>{e(rel_label(input_info.get("state_file")) or "N/A")}</strong></div>
      </div>
      {warnings_block}
    </section>
    """


def render_update_state(summary: dict[str, Any]) -> str:
    update = summary.get("update_state")
    if not isinstance(update, dict):
        return ""
    counts = update.get("status_counts") if isinstance(update.get("status_counts"), dict) else {}
    return f"""
    <section class="panel">
      <h2>本地更新扫描</h2>
      <div class="input-grid">
        <div><span>state_file</span><strong>{e(rel_label(update.get("state_file")) or "N/A")}</strong></div>
        <div><span>discovered</span><strong>{e(update.get("discovered_image_count", 0))}</strong></div>
        <div><span>processed</span><strong>{e(update.get("processed_image_count", 0))}</strong></div>
        <div><span>skipped unchanged</span><strong>{e(update.get("skipped_unchanged_count", 0))}</strong></div>
        <div><span>new</span><strong>{e(counts.get("new", 0))}</strong></div>
        <div><span>changed</span><strong>{e(counts.get("changed", 0))}</strong></div>
      </div>
    </section>
    """


def render_training_plan(summary: dict[str, Any]) -> str:
    plan = summary.get("training_plan")
    if not isinstance(plan, dict):
        return ""
    error = plan.get("error")
    items = plan.get("top_plan_items") if isinstance(plan.get("top_plan_items"), list) else []
    warnings = plan.get("warnings") if isinstance(plan.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Planner Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    resource = plan.get("resource_plan") if isinstance(plan.get("resource_plan"), dict) else {}
    resource_block = ""
    if resource:
        budget = resource.get("budget") if isinstance(resource.get("budget"), dict) else {}
        today = resource.get("today") if isinstance(resource.get("today"), list) else []
        today_rows = []
        for item in today[:5]:
            today_rows.append(
                "<article class=\"resource-item\">"
                f"<strong>#{e(item.get('rank'))} {e(item.get('character'))}</strong>"
                f"<span>{e(item.get('action'))}</span>"
                f"<em>{e(item.get('allocated_stamina'))}</em>"
                "</article>"
            )
        if not today_rows:
            today_rows.append('<div class="empty small">今日没有需要消耗体力的候选项。</div>')
        resource_block = f"""
        <div class="resource-plan">
          <div class="input-grid">
            <div><span>daily stamina</span><strong>{e(budget.get("daily_stamina", "N/A"))}</strong></div>
            <div><span>horizon days</span><strong>{e(budget.get("horizon_days", "N/A"))}</strong></div>
            <div><span>remaining</span><strong>{e(resource.get("remaining_stamina", "N/A"))}</strong></div>
          </div>
          <h3>今日投入建议</h3>
          <div class="resource-list">{''.join(today_rows)}</div>
        </div>
        """
    if error:
        body = f'<div class="errors"><strong>Training plan failed</strong><ul><li>{e(error)}</li></ul></div>'
    elif not items:
        body = '<div class="empty">没有生成培养优先级条目。</div>'
    else:
        rows = []
        for item in items:
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">#{e(item.get('priority_rank'))}</div>"
                "<div>"
                f"<h3>{e(item.get('character'))} · {e(item.get('action'))}</h3>"
                f"<p>{e(item.get('reason'))}</p>"
                f"<span>{e(item.get('target'))}</span>"
                "</div>"
                f"<strong>{e(item.get('estimated_days'))} 天</strong>"
                "</article>"
            )
        body = '<div class="plan-list">' + "".join(rows) + "</div>"
    return f"""
    <section class="panel">
      <h2>培养优先级候选</h2>
      <div class="links">
        {link("training_priority_report.md", plan.get("output_md"))}
        {link("training_priority_report.json", plan.get("output_json"))}
        {link("targets_json", plan.get("targets_json"))}
      </div>
      {warning_block}
      {resource_block}
      {body}
    </section>
    """


def render_snapshot_history(summary: dict[str, Any]) -> str:
    history = summary.get("snapshot_history")
    if not isinstance(history, dict) or not history.get("snapshot_count"):
        return ""
    items = history.get("items") if isinstance(history.get("items"), list) else []
    rows = []
    for item in items:
        status = item.get("status") or "unknown"
        rows.append(
            '<article class="history-item">'
            f'<div><strong>{e(item.get("character") or item.get("case_name"))}</strong><span>{e(status)}</span></div>'
            f'<div><span>changes</span><strong>{e(item.get("change_count", 0))}</strong></div>'
            f'<div><span>review</span><strong>{e(item.get("requires_review_change_count", 0))}</strong></div>'
            '<div class="links">'
            f'{link("current_snapshot", item.get("current_snapshot"))}'
            f'{link("previous_snapshot", item.get("previous_snapshot"))}'
            f'{link("snapshot_diff_md", item.get("diff_md"))}'
            "</div>"
            "</article>"
        )
    return f"""
    <section class="panel">
      <h2>快照历史</h2>
      <div class="input-grid">
        <div><span>history_dir</span><strong>{e(rel_label(history.get("history_dir")) or "N/A")}</strong></div>
        <div><span>snapshots</span><strong>{e(history.get("snapshot_count", 0))}</strong></div>
        <div><span>diffs</span><strong>{e(history.get("diff_count", 0))}</strong></div>
        <div><span>changed characters</span><strong>{e(history.get("changed_character_count", 0))}</strong></div>
        <div><span>first snapshots</span><strong>{e(history.get("no_previous_count", 0))}</strong></div>
        <div><span>diff failed</span><strong>{e(history.get("diff_failed_count", 0))}</strong></div>
      </div>
      <div class="links">{link("history_index", history.get("index_json"))}</div>
      <div class="history-list">{''.join(rows)}</div>
    </section>
    """


def render_target_refresh(summary: dict[str, Any]) -> str:
    refresh = summary.get("target_refresh")
    if not isinstance(refresh, dict):
        return ""
    warnings = refresh.get("warnings") if isinstance(refresh.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Target Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    error = refresh.get("error")
    error_block = ""
    if error:
        error_block = f'<div class="errors"><strong>Target refresh failed</strong><ul><li>{e(error)}</li></ul></div>'
    return f"""
    <section class="panel">
      <h2>终局目标刷新</h2>
      <div class="input-grid">
        <div><span>manifest</span><strong>{e(rel_label(refresh.get("manifest")) or "N/A")}</strong></div>
        <div><span>source type</span><strong>{e(refresh.get("source_type") or "N/A")}</strong></div>
        <div><span>game</span><strong>{e(refresh.get("game") or "N/A")}</strong></div>
        <div><span>sources</span><strong>{e(refresh.get("source_count", 0))}</strong></div>
        <div><span>targets</span><strong>{e(refresh.get("target_count", 0))}</strong></div>
        <div><span>status</span><strong>{e("failed" if error else "ok")}</strong></div>
      </div>
      <div class="links">{link("endgame_targets.json", refresh.get("output_json"))}</div>
      {warning_block}
      {error_block}
    </section>
    """


def render_html(summary: dict[str, Any]) -> str:
    overall = summary.get("overall", {}) if isinstance(summary.get("overall"), dict) else {}
    cases = summary.get("cases", []) if isinstance(summary.get("cases"), list) else []
    review_counts = overall.get("review_status_counts", {}) if isinstance(overall.get("review_status_counts"), dict) else {}
    avg = overall.get("average_pass_rate")
    average_pass_rate = "N/A" if avg is None else f"{round(float(avg) * 100, 2)}%"
    conclusion = overall.get("conclusion") or ""
    input_info = summary.get("input", {}) if isinstance(summary.get("input"), dict) else {}
    plan_info = summary.get("training_plan", {}) if isinstance(summary.get("training_plan"), dict) else {}
    update_info = summary.get("update_state", {}) if isinstance(summary.get("update_state"), dict) else {}
    history_info = summary.get("snapshot_history", {}) if isinstance(summary.get("snapshot_history"), dict) else {}
    target_info = summary.get("target_refresh", {}) if isinstance(summary.get("target_refresh"), dict) else {}
    metrics = [
        metric_card("模式", input_info.get("source_mode") or "unknown", "muted"),
        metric_card("Case 数", overall.get("case_count", 0), "muted"),
        metric_card("Parsed 成功", overall.get("parse_success_count", 0), "ok"),
        metric_card("PASS", review_counts.get("PASS", 0), "ok"),
        metric_card("NEEDS_REVIEW", review_counts.get("NEEDS_REVIEW", 0), "warn"),
        metric_card("FAIL", review_counts.get("FAIL", 0), "bad"),
        metric_card("Expected 平均", average_pass_rate, "muted"),
        metric_card("Normalized", overall.get("normalized_count", 0), "ok"),
        metric_card("需人工确认", overall.get("requires_manual_review_count", 0), "warn"),
        metric_card("本轮处理图片", update_info.get("processed_image_count", "N/A") if update_info else "N/A", "ok" if update_info.get("processed_image_count") else "muted"),
        metric_card("历史变化", history_info.get("changed_character_count", "N/A") if history_info else "N/A", "warn" if history_info.get("changed_character_count") else "muted"),
        metric_card("终局目标", target_info.get("target_count", "N/A") if target_info else "N/A", "warn" if target_info.get("error") else "ok" if target_info else "muted"),
        metric_card("Plan Items", plan_info.get("plan_item_count", 0) if plan_info else "N/A", "warn" if plan_info.get("error") else "ok" if plan_info else "muted"),
    ]
    cards = "".join(render_case(case) for case in cases) or '<div class="empty">没有可展示的 case。</div>'
    steps = render_steps(summary.get("pipeline_steps", []))
    input_panel = render_input_panel(summary)
    update_panel = render_update_state(summary)
    snapshot_history = render_snapshot_history(summary)
    target_refresh = render_target_refresh(summary)
    training_plan = render_training_plan(summary)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Miho 本地练度识别体验台</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #1b2435;
      --muted: #657084;
      --line: #dce3ee;
      --ok: #16834a;
      --ok-bg: #e9f8ef;
      --warn: #9a6500;
      --warn-bg: #fff4d8;
      --bad: #bd2a1f;
      --bad-bg: #ffe9e5;
      --shadow: 0 16px 36px rgba(29, 40, 59, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; }}
    header {{ padding: 28px 32px 18px; background: #101827; color: #fff; }}
    header h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #cbd5e1; max-width: 980px; }}
    main {{ padding: 22px; display: grid; gap: 18px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 24px; }}
    .metric.ok strong {{ color: var(--ok); }} .metric.warn strong {{ color: var(--warn); }} .metric.bad strong {{ color: var(--bad); }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); }}
    .panel h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .steps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
    .input-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .input-grid div {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px; min-width: 0; }}
    .input-grid span {{ display: block; color: var(--muted); font-size: 12px; }}
    .input-grid strong {{ display: block; overflow-wrap: anywhere; }}
    .warnings {{ margin-top: 12px; border: 1px solid #f6cf7c; background: var(--warn-bg); color: var(--warn); border-radius: 8px; padding: 10px; }}
    .warnings ul {{ margin: 6px 0 0; padding-left: 20px; }}
    .step {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; display: grid; gap: 6px; min-width: 0; }}
    .step strong {{ font-size: 14px; }} .step em {{ font-style: normal; color: var(--muted); font-size: 12px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--muted); }}
    .ok .dot, .badge.ok {{ background: var(--ok); color: #fff; }} .warn .dot, .badge.warn {{ background: var(--warn); color: #fff; }} .bad .dot, .badge.bad {{ background: var(--bad); color: #fff; }}
    .case-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(540px, 1fr)); gap: 16px; }}
    .case-card {{ display: grid; grid-template-columns: 170px minmax(0, 1fr); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; box-shadow: var(--shadow); }}
    .thumb {{ background: #e9eef6; min-height: 230px; display: flex; align-items: stretch; justify-content: center; }}
    .thumb img {{ width: 100%; height: 100%; max-height: 320px; object-fit: cover; object-position: top center; }}
    .thumb-empty {{ color: var(--muted); align-self: center; }}
    .case-body {{ padding: 14px; display: grid; gap: 12px; min-width: 0; }}
    .case-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
    .case-head h3 {{ margin: 0; font-size: 18px; overflow-wrap: anywhere; }}
    .badge {{ border-radius: 999px; padding: 5px 9px; font-size: 12px; font-weight: 800; background: #e2e8f0; color: #334155; }}
    .facts {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }}
    .facts div {{ border: 1px solid var(--line); border-radius: 8px; padding: 8px; min-width: 0; }}
    .facts span {{ display: block; color: var(--muted); font-size: 12px; }}
    .facts strong {{ display: block; overflow-wrap: anywhere; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .links a, .missing {{ border: 1px solid var(--line); border-radius: 999px; padding: 6px 9px; font-size: 12px; text-decoration: none; color: #155399; background: #f8fbff; }}
    .missing {{ color: var(--muted); }}
    details {{ border-top: 1px solid var(--line); padding-top: 10px; }}
    summary {{ cursor: pointer; font-weight: 800; }}
    .errors {{ border: 1px solid #ffc0ba; background: var(--bad-bg); color: var(--bad); border-radius: 8px; padding: 10px; }}
    .plan-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .plan-item {{ display: grid; grid-template-columns: 54px minmax(0, 1fr) 72px; gap: 12px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .plan-rank {{ display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; background: #e9f8ef; color: var(--ok); font-weight: 900; }}
    .plan-item h3 {{ margin: 0 0 4px; font-size: 16px; }}
    .plan-item p {{ margin: 0 0 4px; color: var(--text); }}
    .plan-item span {{ color: var(--muted); font-size: 12px; }}
    .plan-item > strong {{ color: var(--warn); text-align: right; }}
    .resource-plan {{ margin-top: 12px; display: grid; gap: 10px; }}
    .resource-plan h3 {{ margin: 0; font-size: 15px; }}
    .resource-list {{ display: grid; gap: 8px; }}
    .resource-item {{ display: grid; grid-template-columns: 150px minmax(0, 1fr) 64px; gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
    .resource-item span {{ color: var(--muted); overflow-wrap: anywhere; }}
    .resource-item em {{ font-style: normal; color: var(--warn); font-weight: 900; text-align: right; }}
    .history-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .history-item {{ display: grid; grid-template-columns: minmax(120px, 1fr) 90px 90px minmax(220px, 2fr); gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .history-item span {{ display: block; color: var(--muted); font-size: 12px; }}
    .history-item strong {{ overflow-wrap: anywhere; }}
    .empty {{ padding: 24px; color: var(--muted); background: var(--panel); border: 1px dashed var(--line); border-radius: 8px; }}
    @media (max-width: 900px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .steps {{ grid-template-columns: 1fr; }}
      .input-grid {{ grid-template-columns: 1fr; }}
      .case-grid {{ grid-template-columns: 1fr; }}
      .case-card {{ grid-template-columns: 1fr; }}
      .facts {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .plan-item {{ grid-template-columns: 1fr; }}
      .resource-item {{ grid-template-columns: 1fr; }}
      .history-item {{ grid-template-columns: 1fr; }}
      .plan-item > strong {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Miho 本地练度识别体验台</h1>
    <p>{e(conclusion)}</p>
  </header>
  <main>
    <section class="metrics">{''.join(metrics)}</section>
    {input_panel}
    {update_panel}
    {steps}
    {target_refresh}
    {snapshot_history}
    {training_plan}
    <section class="panel"><h2>Case 卡片</h2><div class="case-grid">{cards}</div></section>
  </main>
</body>
</html>
"""


def render_dashboard(summary: dict[str, Any], output_path: Path) -> dict[str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(summary), encoding="utf-8")
    return {"dashboard_html": str(output_path)}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the local Miho demo dashboard from a summary JSON.")
    parser.add_argument("--summary", required=True, help="Demo summary JSON.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output HTML path. Default: data/probes/demo/index.html")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        summary = load_json(resolve_path(args.summary))
        result = render_dashboard(summary, resolve_path(args.output))
    except DashboardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"dashboard_html: {result['dashboard_html']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
