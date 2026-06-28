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
          <div><span>可信字段</span><strong>{e(quality.get("trusted_field_count"))}/{e(quality.get("field_count"))}</strong></div>
          <div><span>人工确认</span><strong>{e(quality.get("requires_manual_review"))}</strong></div>
        </div>
        <div class="links">
          {link("review_html", case.get("review_html"))}
          {link("parsed_json", case.get("parsed_json"))}
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


def render_html(summary: dict[str, Any]) -> str:
    overall = summary.get("overall", {}) if isinstance(summary.get("overall"), dict) else {}
    cases = summary.get("cases", []) if isinstance(summary.get("cases"), list) else []
    review_counts = overall.get("review_status_counts", {}) if isinstance(overall.get("review_status_counts"), dict) else {}
    avg = overall.get("average_pass_rate")
    average_pass_rate = "N/A" if avg is None else f"{round(float(avg) * 100, 2)}%"
    conclusion = overall.get("conclusion") or ""
    metrics = [
        metric_card("图片数量", overall.get("case_count", 0), "muted"),
        metric_card("Parsed 成功", overall.get("parse_success_count", 0), "ok"),
        metric_card("PASS", review_counts.get("PASS", 0), "ok"),
        metric_card("NEEDS_REVIEW", review_counts.get("NEEDS_REVIEW", 0), "warn"),
        metric_card("FAIL", review_counts.get("FAIL", 0), "bad"),
        metric_card("Expected 平均", average_pass_rate, "muted"),
        metric_card("Normalized", overall.get("normalized_count", 0), "ok"),
        metric_card("需人工确认", overall.get("requires_manual_review_count", 0), "warn"),
    ]
    cards = "".join(render_case(case) for case in cases) or '<div class="empty">没有可展示的 case。</div>'
    steps = render_steps(summary.get("pipeline_steps", []))
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
    .steps {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }}
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
    .empty {{ padding: 24px; color: var(--muted); background: var(--panel); border: 1px dashed var(--line); border-radius: 8px; }}
    @media (max-width: 900px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .steps {{ grid-template-columns: 1fr; }}
      .case-grid {{ grid-template-columns: 1fr; }}
      .case-card {{ grid-template-columns: 1fr; }}
      .facts {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
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
    {steps}
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
