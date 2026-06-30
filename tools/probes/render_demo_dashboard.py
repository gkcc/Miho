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
VISIBLE_BRIEF_CARD_LIMIT = 3


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


def humanize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    sentence_replacements = (
        (
            "run_manifest 显示输入缺失、错批或无法确认；这里不会把方案当作可信 ready。",
            "本轮数据来源对不上：暂时不能把配队建议当作可用结果。",
        ),
        (
            "运行清单 显示输入缺失、错批或无法确认；这里不会把方案当作可信 就绪。",
            "本轮数据来源对不上：暂时不能把配队建议当作可用结果。",
        ),
        (
            "缺少 run_manifest；无法确认本轮产物是否同批生成。",
            "缺少本轮运行清单：这批识别结果、复核预览和建议可能不是同一次生成，先刷新本地演示。",
        ),
        (
            "缺少 运行清单；无法确认本轮产物是否同批生成。",
            "缺少本轮运行清单：这批识别结果、复核预览和建议可能不是同一次生成，先刷新本地演示。",
        ),
        ("missing_run_manifest", "缺少本轮运行清单"),
        ("launcher_command_path_not_canonical", "启动器命令路径不在允许范围"),
        ("launcher_report_follow_up_not_for_current_dashboard", "启动器后续建议不属于当前页面"),
        ("launcher_report_not_for_current_dashboard", "启动器记录不属于当前页面"),
        ("launcher_report_doctor_hash_missing", "启动器诊断校验缺失"),
        ("follow_up_doctor_not_updated_after_rerun", "后续诊断没有在重跑后更新"),
        ("apply_receipt_preview_result_sha256_mismatch", "应用回执与复核预览校验不一致"),
        ("demo rerun command is safe to print", "演示重跑命令可安全展示"),
        ("official account data", "官方账号数据"),
        ("tokens/cookies/login state", "登录态、令牌或 Cookie"),
        ("online tier data", "在线保值数据"),
        ("formal database", "正式数据库"),
        (
            "ready_try_now_not_actionable_under_current_doctor_status",
            "当前诊断状态不允许直接尝试",
        ),
        ("preview_ready_but_apply_missing", "复核预览已生成，但还没人工确认应用"),
        ("accepted roster based local suggestions", "基于已确认角色库的本地建议"),
        ("endgame plan", "高难方案"),
        ("tier watchlist view", "保值观察页"),
        ("dashboard visualization", "页面可视化"),
        (
            "pending snapshot 尚未进入 accepted roster；确认前不能进入 try_now。",
            "这张解析结果还没人工确认：确认前不能当作已拥有练度，也不会进入可尝试队伍。",
        ),
        (
            "待确认快照 尚未进入 已确认角色库；确认前不能进入 可尝试。",
            "这张解析结果还没人工确认：确认前不能当作已拥有练度，也不会进入可尝试队伍。",
        ),
        (
            "重新运行 demo pipeline，或确认 run_manifest 中的输入产物来自同一批生成。",
            "重新运行 scripts/run_miho_demo.bat --fresh，或检查本轮运行清单是否同批生成。",
        ),
        (
            "打开 Dashboard 的本期高难方案，按该队伍先试一次。",
            "打开下方“本期高难方案”，确认队伍后再尝试。",
        ),
    )
    for old, new in sentence_replacements:
        text = text.replace(old, new)
    replacements = (
        ("parsed JSON", "已解析结果"),
        ("Parsed JSON", "已解析结果"),
        ("OCR", "图片识别"),
        ("Demo pipeline", "本地演示流程"),
        ("demo pipeline", "本地演示流程"),
        ("本地 demo", "本地演示"),
        ("本地 Demo", "本地演示"),
        ("Dashboard", "页面"),
        ("dashboard", "页面"),
        ("expected", "验收对照"),
        ("accepted roster", "已确认角色库"),
        ("accepted", "已确认"),
        ("roster", "角色库"),
        ("catalog candidate", "目录候选"),
        ("catalog", "目录"),
        ("tier watchlist", "保值观察"),
        ("roster delta", "角色库变化"),
        ("action/team cards", "行动卡/队伍卡"),
        ("run_manifest", "运行清单"),
        ("doctor", "诊断"),
        ("launcher", "启动器"),
        ("follow-up", "后续建议"),
        ("blockers", "阻断项"),
        ("warnings", "警告"),
        ("requires_review", "待人工确认"),
        ("pending snapshot", "待确认快照"),
        ("needs_review", "待复核"),
        ("data_warning", "数据警告"),
        ("blocked", "已阻断"),
        ("try_now", "可尝试"),
        ("ready", "就绪"),
        ("case", "图片项"),
        ("Case", "图片项"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    text = text.replace("图片项 卡片", "图片卡片")
    text = text.replace("本地演示流程 已", "本地演示流程已")
    text = text.replace("已生成 页面", "已生成页面")
    text = text.replace("部分 图片项", "部分图片项")
    text = text.replace("图片项 失败", "图片项失败")
    text = text.replace("打开 图片", "打开图片")
    text = text.replace("或 已解析结果", "或已解析结果")
    text = text.replace("run_miho_本地演示.bat", "run_miho_demo.bat")
    return text


def he(value: Any) -> str:
    return e(humanize_text(value))


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
    if text in {
        "pass",
        "done",
        "ok",
        "true",
        "generated",
        "ready_for_review",
        "trusted",
        "consistent",
        "applied",
        "fresh",
        "ready",
        "ready_to_try",
        "executed",
        "printed",
        "current",
    }:
        return "ok"
    if text in {
        "needs_review",
        "needs-review",
        "requires_review",
        "missing_expected",
        "uncertain",
        "skipped",
        "n/a",
        "warning",
        "ready_with_pending",
        "ready_with_override",
        "not_applied",
        "applied_with_warnings",
        "unknown",
        "needs_apply",
        "executed_with_followup_warning",
    }:
        return "warn"
    if text in {"fail", "failed", "false", "error", "blocked", "has_parse_failure", "stale_after_apply", "needs_rerun", "stale"}:
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


def summary_card(label: str, title: Any, body: Any, tone: str = "muted") -> str:
    return (
        f'<article class="summary-card {e(tone)}">'
        f"<span>{e(label)}</span>"
        f"<strong>{e(title)}</strong>"
        f"<p>{e(body)}</p>"
        "</article>"
    )


def guide_card(title: str, body: str, command: str | None = None, tone: str = "muted") -> str:
    command_html = f"<code>{e(command)}</code>" if command else ""
    return (
        f'<article class="guide-card {e(tone)}">'
        f"<strong>{e(title)}</strong>"
        f"<p>{e(body)}</p>"
        f"{command_html}"
        "</article>"
    )


def operation_card(title: str, body: str, command: str, tone: str = "muted") -> str:
    return (
        f'<article class="operation-card {e(tone)}">'
        f"<strong>{e(title)}</strong>"
        f"<p>{e(body)}</p>"
        f"<code>{e(command)}</code>"
        "</article>"
    )


def render_operation_bar() -> str:
    cards = [
        operation_card("看软件体验", "打开已有 Dashboard；默认入口不会跑 OCR，也不会读账号登录态。", r"dist\MihoProbe.exe", "safe"),
        operation_card(
            "一键更新练度",
            r"处理 figs\ 里已保存的米游社官方分享图；只有这条会进入图片识别慢路径。",
            r"dist\MihoProbe.exe update --open",
            "primary",
        ),
        operation_card(
            "评级快检",
            "只看角色头像左上角和音擎评级区的 A/S 艺术字；不跑 OCR。",
            r"dist\MihoProbe.exe rank-check --open",
            "safe",
        ),
        operation_card(
            "准确率验收",
            "用 replay manifest 做 expected diff；不扫历史 parsed，也不重新 OCR。",
            r"dist\MihoProbe.exe check --no-open",
            "muted",
        ),
        operation_card(
            "APP 导出流程",
            "生成官方分享图工作流和校准命令；不自动登录，不读 token/cookie。",
            r"dist\MihoProbe.exe app-export --open",
            "warn",
        ),
    ]
    return (
        '<section class="operation-bar" aria-label="软件入口">'
        "<div>"
        "<span>软件入口</span>"
        "<h2>先从这里选动作</h2>"
        "<p>这些卡片只展示本地命令和边界，不会在页面里执行 apply、try_now 或自动登录。</p>"
        "</div>"
        f'<div class="operation-grid">{"".join(cards)}</div>'
        "</section>"
    )


def render_acceptance_guide(
    *,
    can_act_now: bool,
    input_info: dict[str, Any],
    run_info: dict[str, Any],
    run_status: dict[str, Any],
    final_info: dict[str, Any],
    doctor_info: dict[str, Any],
    parse_fail_count: int,
    expected_fail_count: int,
    manual_review_count: int,
    case_count: int,
    average_pass_rate: str,
) -> str:
    final_warnings = final_info.get("warnings") if isinstance(final_info.get("warnings"), list) else []
    missing_run_manifest = not bool(run_info)
    manifest_consistent = run_status.get("consistent") is True if run_status else False
    has_data_warning = missing_run_manifest or (run_info and not manifest_consistent) or bool(final_warnings)
    if has_data_warning:
        tone = "bad"
        headline = "先别把这页当验收结果"
        body = (
            "当前缺少本轮运行清单或数据来源不一致；这页只能用来排查。"
            "准确率验收请用固定样例清单入口，不要扫整个历史解析目录。"
        )
    elif manual_review_count:
        tone = "warn"
        headline = "先复核，再采用建议"
        body = f"还有 {manual_review_count} 个识别结果待人工确认；确认前不会进入本地角色库。"
    elif parse_fail_count or expected_fail_count:
        tone = "warn"
        headline = "识别结果还需要修"
        body = f"当前解析失败 {parse_fail_count}，验收对照未通过 {expected_fail_count}；先跑准确率验收看 top failed fields。"
    elif can_act_now:
        tone = "ok"
        headline = "可以继续看本地建议"
        body = "当前门禁允许继续阅读下方配队和行动建议；它仍然不是抽卡建议，也不会写正式数据库。"
    else:
        tone = "warn"
        headline = "需要先刷新本地状态"
        body = "当前没有足够证据证明这页可直接采用；先按下一步入口刷新或检查。"

    doctor_action = action_label(doctor_info.get("primary_next_action")) if doctor_info else "查看页面明细"
    mode = source_mode_label(input_info.get("source_mode"))
    cards = [
        guide_card(
            "准确率验收",
            "只用固定样例清单里的 3 到 5 张样例算通过率；这是 P0.9 验收入口。",
            "dist\\MihoProbe.exe check --open",
            "ok",
        ),
        guide_card(
            "看软件体验",
            "打开缓存 Dashboard，不重新跑图片识别；如果上次 fresh 卡住，先点这个。",
            "dist\\MihoProbe.exe",
            "ok",
        ),
        guide_card(
            "更新练度",
            "当前安全版只处理 figs 里已经保存的官方分享图；APP 自动点击还在工作流校准。",
            "dist\\MihoProbe.exe update --open",
            "warn",
        ),
        guide_card(
            "更新高难配队",
            "不跑图片识别、不联网，只用本地已确认角色库、目标配置和 Tier/保值快照重算建议。",
            "dist\\MihoProbe.exe plan-update --open",
            "muted",
        ),
    ]
    return (
        f'<section class="acceptance-guide {e(tone)}">'
        "<div>"
        "<span>验收助手</span>"
        f"<h2>{e(headline)}</h2>"
        f"<p>{he(body)}</p>"
        f"<em>当前模式：{e(mode)} · 下一步：{e(doctor_action)} · 样例数：{e(case_count)} · 平均通过率：{e(average_pass_rate)}</em>"
        "</div>"
        f'<div class="guide-cards">{"".join(cards)}</div>'
        "</section>"
    )


def human_status(value: Any) -> str:
    text = str(value or "").lower()
    labels = {
        "ready": "就绪",
        "ready_for_review": "待人工确认",
        "ready_to_try": "可尝试",
        "needs_review": "待复核",
        "requires_review": "待复核",
        "needs_rerun": "需重跑",
        "needs_apply": "需应用复核",
        "not_applied": "未应用",
        "applied": "已应用",
        "blocked": "已阻断",
        "warning": "有警告",
        "trusted": "可信",
        "failed": "失败",
        "fail": "失败",
        "has_parse_failure": "有解析失败",
        "stale_after_apply": "应用后已过期",
        "unknown": "未知",
        "n/a": "无",
    }
    return labels.get(text, str(value or "N/A"))


def brief_card_type_label(value: Any) -> str:
    text = str(value or "").lower()
    labels = {
        "data_warning": "数据一致性",
        "review_snapshot": "人工复核",
        "try_now": "可尝试",
        "needs_recording": "待录入",
        "watch_only": "仅观察",
    }
    return labels.get(text, str(value or "事项"))


def brief_action_label(item: dict[str, Any]) -> str:
    card_type = str(item.get("card_type") or "").lower()
    if card_type == "data_warning":
        return "先处理数据一致性"
    if card_type == "review_snapshot":
        return "打开复核页确认"
    if card_type == "try_now":
        return "可按本地清单试一次"
    if card_type == "needs_recording":
        return "先补录练度数据"
    if card_type == "watch_only":
        return "仅观察，不行动"
    return "查看详情"


def checklist_action_label(item: dict[str, Any]) -> str:
    item_type = str(item.get("item_type") or "").lower()
    status = str(item.get("status") or "").lower()
    if status in {"blocked", "data_warning"} or item_type == "data_warning":
        return "先修数据"
    if item_type == "review_snapshot" or status in {"needs_review", "pending"}:
        return "打开复核页"
    if item_type == "try_now" or status in {"ready", "ready_to_try"}:
        return "可按清单尝试"
    if item_type == "needs_recording":
        return "先补录"
    if item_type == "watch_only":
        return "仅观察"
    return "查看详情"


def checklist_status_line(item: dict[str, Any]) -> str:
    status = human_status(item.get("status"))
    item_type = brief_card_type_label(item.get("item_type"))
    return f"{status} · {item_type}"


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def render_brief_overview(brief: dict[str, Any], brief_summary: dict[str, Any], warnings: list[Any]) -> str:
    status = str(brief.get("brief_status") or "unknown").lower()
    trusted = int_value(brief_summary.get("trusted_plan_count"))
    pending = int_value(brief_summary.get("pending_review_count"))
    ready_targets = int_value(brief_summary.get("ready_now_target_count"))
    recording = int_value(brief_summary.get("needs_recording_target_count"))
    watch_only = int_value(brief_summary.get("watch_only_target_count"))
    warning_count = len(warnings)

    if warning_count:
        tone = "bad"
        title = "这不是验收结果"
        body = (
            "本轮数据来源缺失或不一致，页面只作为排查入口，不代表 P0.9 验收。"
            "先打开缓存入口刷新页面；确实换了新图时，再跑 Fresh OCR。"
        )
    elif status == "needs_review" or pending:
        tone = "warn"
        title = f"先复核 {pending or '待确认'} 张快照"
        body = "还有解析快照没有进入已确认角色库；确认前不会把这些角色当作可用练度。"
    elif trusted or ready_targets:
        tone = "ok"
        title = "可以看本地建议"
        body = f"当前有 {ready_targets or trusted} 个可尝试目标。它仍然只是本地演示建议，不会自动写正式数据库。"
    elif recording:
        tone = "warn"
        title = "先补录练度"
        body = f"{recording} 个目标缺少关键角色或练度快照，补齐后再生成可尝试方案。"
    elif watch_only:
        tone = "warn"
        title = "目前只适合观察"
        body = f"{watch_only} 个目标只有观察价值，还不能作为今天的操作建议。"
    else:
        tone = "muted"
        title = "暂无可执行事项"
        body = "当前没有可信建议或待复核项；可以先补充官方分享图或重跑本地演示流程。"

    return (
        f'<div class="brief-overview {e(tone)}">'
        '<span>一眼结论</span>'
        f"<strong>{e(title)}</strong>"
        f"<p>{e(body)}</p>"
        "</div>"
    )


def brief_evidence_rows(evidence: dict[str, Any]) -> str:
    rows = []
    for label, key in (
        ("复核页", "review_html"),
        ("来源", "source"),
        ("标准化结果", "normalized_json"),
        ("产物", "artifact"),
        ("hash", "hash"),
    ):
        value = evidence.get(key)
        if not value:
            continue
        rows.append(f"<li><strong>{e(label)}</strong><span>{e(rel_label(value))}</span></li>")
    return "".join(rows) or "<li><strong>证据</strong><span>N/A</span></li>"


def command_details(title: str, commands: list[tuple[str, Any]]) -> str:
    rows = []
    for label, command in commands:
        if not command:
            continue
        rows.append(f"<p>{e(label)}</p><pre class=\"command-block\"><code>{e(command)}</code></pre>")
    if not rows:
        return ""
    return f"<details class=\"command-details\"><summary>{e(title)}</summary>{''.join(rows)}</details>"


def stats_details(title: str, rows: list[tuple[str, Any]]) -> str:
    if not rows:
        return ""
    cells = "".join(
        f"<div><span>{e(label)}</span><strong>{e(value)}</strong></div>"
        for label, value in rows
    )
    return f'<details class="soft-details"><summary>{e(title)}</summary><div class="input-grid">{cells}</div></details>'


def command_hint_text(value: Any) -> str:
    text = str(value or "无命令提示")
    stripped = text.lstrip().lower()
    if stripped.startswith(("python ", "powershell ", "scripts\\", "scripts/")) or ".py" in stripped:
        return e(text)
    return he(text)


def command_hint_summary(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "无额外操作。"
    lowered = text.lower()
    if "apply_review_decisions.py" in lowered:
        return "先打开复核页核对字段；确认无误后，再到“执行清单”统一应用复核结果。"
    if "preview_review_decisions.py" in lowered:
        return "先做复核预览，只检查将要应用的决定，不写入角色库。"
    if "run_demo_pipeline.py" in lowered or "run_miho_demo.bat" in lowered:
        return "刷新本地演示流程，重新生成同一批识别、复核和建议产物。"
    if lowered.startswith(("python ", "powershell ", "scripts\\", "scripts/")) or ".py" in lowered:
        return "这是排障命令，普通验收不用复制。"
    return humanize_text(text)


def render_brief_next_step(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    action = brief_action_label(item)
    title = humanize_text(item.get("title"))
    reason = humanize_text(item.get("reason"))
    target_bits = []
    if item.get("target"):
        target_bits.append(f"目标：{item.get('target')}")
    if item.get("character"):
        target_bits.append(f"角色：{item.get('character')}")
    target_text = " · ".join(str(bit) for bit in target_bits if bit) or "不绑定具体目标/角色"
    return (
        '<div class="brief-next-step">'
        "<span>现在先做</span>"
        f"<strong>{e(action)}</strong>"
        f"<p>{he(title)}：{he(reason)}</p>"
        f"<em>{he(target_text)}</em>"
        "</div>"
    )


def render_brief_flow(brief_summary: dict[str, Any], warnings: list[Any]) -> str:
    pending = int_value(brief_summary.get("pending_review_count"))
    ready_targets = int_value(brief_summary.get("ready_now_target_count"))
    recording = int_value(brief_summary.get("needs_recording_target_count"))
    watch_only = int_value(brief_summary.get("watch_only_target_count"))
    if warnings:
        steps = [
            ("1", "刷新本地演示", "先让本轮识别、复核和建议来自同一批数据。"),
            ("2", "确认复核结果", "打开复核页看原图和字段，别直接相信旧快照。"),
            ("3", "再看配队建议", "绿色后再按本地清单尝试。"),
        ]
    elif pending:
        steps = [
            ("1", "打开复核页", f"还有 {pending} 张解析快照待确认。"),
            ("2", "应用复核结果", "确认无误后再进入本地角色库。"),
            ("3", "刷新建议", "让配队只使用已确认练度。"),
        ]
    elif ready_targets:
        steps = [
            ("1", "查看可尝试目标", f"当前有 {ready_targets} 个本地可尝试目标。"),
            ("2", "按清单试一次", "只按已确认角色和本地高难目标行动。"),
            ("3", "记录结果", "打完后再更新练度或目标状态。"),
        ]
    elif recording:
        steps = [
            ("1", "补录官方分享图", f"{recording} 个目标缺少关键练度。"),
            ("2", "复核解析字段", "确认角色、音擎、驱动盘主副词条。"),
            ("3", "重新生成建议", "补齐后再判断是否能打。"),
        ]
    elif watch_only:
        steps = [
            ("1", "只观察", f"{watch_only} 个目标还不能作为行动建议。"),
            ("2", "补齐数据", "先补已拥有角色和练度快照。"),
            ("3", "等待绿色状态", "可信前不按它练角色。"),
        ]
    else:
        steps = [
            ("1", "补充数据", "放入官方分享图或选择已有 parsed replay。"),
            ("2", "生成 Dashboard", "先看本地缓存入口，不要直接跑慢 OCR。"),
            ("3", "复核后再行动", "确认字段后才进入本地建议。"),
        ]
    cells = "".join(
        f'<div class="brief-flow-step"><b>{e(number)}</b><strong>{e(title)}</strong><span>{he(body)}</span></div>'
        for number, title, body in steps
    )
    return f'<div class="brief-flow"><h3>推荐操作路线</h3><div>{cells}</div></div>'


def basename(value: Any) -> str:
    if not value:
        return ""
    return Path(str(value)).name


def derived_case_status(case: dict[str, Any], key: str) -> str:
    existing = case.get(key)
    if existing:
        return str(existing)
    if key == "parse_status":
        if str(case.get("review_status") or "").upper() == "FAIL":
            return "FAIL"
        return "PASS" if case.get("parsed_json") else "SKIPPED"
    if key == "expected_status":
        if not case.get("expected_json"):
            return "N/A"
        if case.get("pass_rate") is None:
            return "FAIL"
        return "PASS" if float(case.get("pass_rate") or 0) >= 0.8 else "FAIL"
    if key == "normalized_status":
        return "GENERATED" if case.get("normalized_json") else "FAILED"
    if key == "import_status":
        return "BLOCKED" if case.get("import_blockers") else "REQUIRES_REVIEW"
    return "N/A"


def evidence_hint(evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return ""
    source = evidence.get("title") or evidence.get("source_ref") or ""
    source_label = basename(source) if source and not str(source).startswith(("http://", "https://")) else str(source)
    content_hash = evidence.get("content_sha256_short") or ""
    if source_label and content_hash:
        return f"证据：{source_label} · {content_hash}"
    if source_label:
        return f"证据：{source_label}"
    if content_hash:
        return f"证据 hash：{content_hash}"
    return ""


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


def bool_text(value: Any) -> str:
    if value is None:
        return "未知"
    return "是" if bool(value) else "否"


def action_label(value: Any) -> str:
    labels = {
        "rerun_demo_pipeline": "重跑演示流程",
        "safe_apply_review_decisions": "人工确认后应用",
        "review_snapshots": "复核待确认快照",
        "try_now": "按清单试一次",
        "review_dashboard": "查看页面明细",
        "rebuild_run_manifest": "刷新本轮数据清单",
        "resolve_blockers": "处理阻断项",
    }
    text = str(value or "unknown")
    return labels.get(text, text)


def source_mode_label(value: Any) -> str:
    labels = {
        "ocr_fresh_image": "新图片识别模式",
        "OCR fresh image mode": "新图片识别模式",
        "parsed_replay": "解析结果回放模式",
        "parsed replay mode": "解析结果回放模式",
        "manifest_controlled": "清单受控回放模式",
        "manifest controlled mode": "清单受控回放模式",
    }
    return labels.get(str(value or ""), str(value or "未知模式"))


def list_block(title: str, items: list[Any], css_class: str) -> str:
    if not items:
        return ""
    html_items = "".join(f"<li>{he(item)}</li>" for item in items)
    return f'<div class="{e(css_class)}"><strong>{he(title)}</strong><ul>{html_items}</ul></div>'


def render_demo_doctor(summary: dict[str, Any]) -> str:
    doctor = summary.get("demo_doctor")
    if not isinstance(doctor, dict):
        return ""
    doctor_summary = doctor.get("summary") if isinstance(doctor.get("summary"), dict) else {}
    evidence = doctor.get("evidence_check") if isinstance(doctor.get("evidence_check"), dict) else {}
    action_contract = doctor.get("action_contract") if isinstance(doctor.get("action_contract"), dict) else {}
    commands = doctor.get("commands") if isinstance(doctor.get("commands"), dict) else {}
    blockers = doctor.get("blocking_reasons") if isinstance(doctor.get("blocking_reasons"), list) else []
    warnings = doctor.get("warnings") if isinstance(doctor.get("warnings"), list) else []
    evidence_blockers = evidence.get("blockers") if isinstance(evidence.get("blockers"), list) else []
    evidence_warnings = evidence.get("warnings") if isinstance(evidence.get("warnings"), list) else []
    status = str(doctor.get("doctor_status") or "unknown")
    if doctor.get("error"):
        body = f'<div class="errors"><strong>诊断失败</strong><ul><li>{he(doctor.get("error"))}</li></ul></div>'
    else:
        command_rows = []
        for label, key in (("重跑命令", "rerun_demo"), ("预览命令", "preview"), ("安全应用命令", "safe_apply")):
            command_rows.append(
                "<article class=\"resource-item\">"
                f"<strong>{e(label)}</strong>"
                f"<span>{e(commands.get(key) or 'N/A')}</span>"
                f"<em>{e(key)}</em>"
                "</article>"
            )
        body = (
            '<div class="resource-plan"><h3>下一步命令</h3>'
            f'<div class="resource-list">{"".join(command_rows)}</div></div>'
        )
    status_copy = ""
    if status == "needs_rerun":
        status_copy = (
            '<div class="errors"><strong>不建议直接尝试</strong>'
            "<ul><li>当前建议可能没有吸收最新人工应用结果，或刷新状态未知；先重跑演示流程。</li></ul></div>"
        )
    elif status == "needs_apply":
        status_copy = (
            '<div class="warnings"><strong>需要人工应用复核决定</strong>'
            "<ul><li>复核预览已就绪，但还没有安全应用回执；先人工确认后应用，再重跑演示流程。</li></ul></div>"
        )
    elif status == "ready_to_try":
        status_copy = (
            '<div class="warnings"><strong>可以尝试但仍是本地演示</strong>'
            "<ul><li>只代表当前本地已确认角色库与目标配置下的可尝试清单，不代表抽卡建议。</li></ul></div>"
        )
    return f"""
    <section class="panel demo-doctor">
      <h2>当前状态诊断</h2>
      <p class="muted-line">先给一个总判断：现在该重跑、复核、人工应用，还是可以按清单试一次。仅观察项不会升级成可尝试项。</p>
      <div class="links">
        {link("demo_doctor.md", doctor.get("output_md"))}
        {link("demo_doctor.json", doctor.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>诊断状态</span><strong>{e(human_status(status))}</strong></div>
        <div><span>诊断结论</span><strong>{he(doctor.get("headline") or "N/A")}</strong></div>
        <div><span>下一步</span><strong>{e(action_label(doctor.get("primary_next_action")))}</strong></div>
        <div><span>允许尝试</span><strong>{e(bool_text(doctor.get("try_now_allowed")))}</strong></div>
        <div><span>需要重跑</span><strong>{e(bool_text(doctor.get("rerun_required")))}</strong></div>
        <div><span>需要复核</span><strong>{e(bool_text(doctor.get("review_required")))}</strong></div>
        <div><span>需要安全应用</span><strong>{e(bool_text(doctor.get("safe_apply_required")))}</strong></div>
        <div><span>刷新状态</span><strong>{e(human_status(doctor_summary.get("refresh_status", "N/A")))}</strong></div>
        <div><span>简报状态</span><strong>{e(human_status(doctor_summary.get("brief_status", "N/A")))}</strong></div>
        <div><span>清单状态</span><strong>{e(human_status(doctor_summary.get("checklist_status", "N/A")))}</strong></div>
        <div><span>复核预览</span><strong>{e(human_status(doctor_summary.get("preview_status", "N/A")))}</strong></div>
        <div><span>应用回执</span><strong>{e(human_status(doctor_summary.get("apply_status", "N/A")))}</strong></div>
        <div><span>诊断证据</span><strong>{e(human_status(evidence.get("status", "N/A")))}</strong></div>
        <div><span>严格状态</span><strong>{e(human_status(evidence.get("strict_status", "N/A")))}</strong></div>
        <div><span>预览-应用一致</span><strong>{e(bool_text(evidence.get("matched_preview_apply")))}</strong></div>
        <div><span>重跑命令一致</span><strong>{e(bool_text(evidence.get("matched_refresh_command")))}</strong></div>
        <div><span>运行清单一致</span><strong>{e(bool_text(evidence.get("matched_run_manifest")))}</strong></div>
        <div><span>动作边界</span><strong>{e(action_label(action_contract.get("primary_next_action")))}</strong></div>
        <div><span>启动器允许</span><strong>{e(bool_text(action_contract.get("allowed_for_launcher")))}</strong></div>
        <div><span>会写角色库</span><strong>{e(bool_text(action_contract.get("writes_roster")))}</strong></div>
        <div><span>需人工确认</span><strong>{e(bool_text(action_contract.get("requires_manual_confirmation")))}</strong></div>
        <div><span>待复核快照</span><strong>{e(doctor_summary.get("pending_review_count", "N/A"))}</strong></div>
        <div><span>可尝试项</span><strong>{e(doctor_summary.get("ready_try_now_count", "N/A"))}</strong></div>
        <div><span>运行清单</span><strong>{e(bool_text(doctor_summary.get("run_manifest_exists")))}</strong></div>
      </div>
      {status_copy}
      {list_block("阻断原因", blockers, "errors")}
      {list_block("诊断警告", warnings, "warnings")}
      {list_block("证据阻断", evidence_blockers, "errors")}
      {list_block("证据警告", evidence_warnings, "warnings")}
      {list_block("动作边界说明", [action_contract.get("reason")] if action_contract.get("reason") else [], "warnings")}
      {body}
    </section>
    """


def render_update_command(summary: dict[str, Any]) -> str:
    command_pack = summary.get("update_command")
    if not isinstance(command_pack, dict):
        return ""
    status = str(command_pack.get("status") or "unknown")
    command = command_pack.get("command")
    updates = command_pack.get("updates") if isinstance(command_pack.get("updates"), list) else []
    does_not_update = command_pack.get("does_not_update") if isinstance(command_pack.get("does_not_update"), list) else []
    blockers = command_pack.get("blockers") if isinstance(command_pack.get("blockers"), list) else []
    warnings = command_pack.get("warnings") if isinstance(command_pack.get("warnings"), list) else []
    command_block = ""
    if status == "ready" and command:
        command_block = (
            '<div class="resource-plan"><h3>可复制命令</h3>'
            f'<pre class="command-block"><code>{e(command)}</code></pre>'
            "<p class=\"muted-line\">这条命令只调用安全启动器：刷新本地演示、读取后续诊断、刷新页面，并保留最近启动器历史。</p></div>"
        )
    else:
        command_block = (
            '<div class="errors"><strong>当前不可作为本地更新命令运行</strong>'
            "<ul><li>请先处理阻断项；页面只展示诊断，不触发工具动作。</li></ul></div>"
        )
    update_items = "".join(f"<li>{he(item)}</li>" for item in updates) or "<li>N/A</li>"
    not_items = "".join(f"<li>{he(item)}</li>" for item in does_not_update) or "<li>N/A</li>"
    return f"""
    <section class="panel update-command">
      <h2>本地更新命令</h2>
      <p class="muted-line">把当前安全链路沉淀成一条可复制命令；它不是抽卡建议，也不会变更账号、登录态、在线数据或正式数据库。</p>
      <div class="links">
        {link("update_command.md", command_pack.get("output_md"))}
        {link("update_command.json", command_pack.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>status</span><strong>{e(status)}</strong></div>
        <div><span>max_history</span><strong>{e(command_pack.get("input", {}).get("max_history") if isinstance(command_pack.get("input"), dict) else "N/A")}</strong></div>
        <div><span>schema</span><strong>{e(command_pack.get("schema_version") or "N/A")}</strong></div>
      </div>
      {command_block}
      <div class="resource-plan">
        <h3>会刷新</h3>
        <ul>{update_items}</ul>
        <h3>不会刷新</h3>
        <ul>{not_items}</ul>
      </div>
      {list_block("阻断原因", blockers, "errors")}
      {list_block("警告", warnings, "warnings")}
    </section>
    """


def render_launcher_report(summary: dict[str, Any]) -> str:
    report = summary.get("launcher_report")
    if not isinstance(report, dict):
        return ""
    follow_up = report.get("follow_up") if isinstance(report.get("follow_up"), dict) else {}
    dashboard_refresh = report.get("dashboard_refresh") if isinstance(report.get("dashboard_refresh"), dict) else {}
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    follow_warnings = follow_up.get("warnings") if isinstance(follow_up.get("warnings"), list) else []
    follow_blockers = []
    for key in ("evidence_blockers", "blocking_reasons", "doctor_warnings"):
        if isinstance(follow_up.get(key), list):
            follow_blockers.extend(follow_up[key])
    status = str(report.get("launcher_status") or "unknown")
    follow_action = str(follow_up.get("primary_next_action") or "N/A")
    freshness = str(report.get("launcher_report_freshness") or "unknown")
    freshness_current = freshness == "current"
    follow_up_current = report.get("follow_up_matches_current_doctor") is True
    operation_state = str(report.get("launcher_report_operation_state") or freshness)
    freshness_note = ""
    if freshness == "stale":
        freshness_note = (
            '<div class="errors"><strong>历史 launcher report，仅供审计</strong>'
            "<ul><li>该 launcher report 不对应当前 demo_doctor；请重新运行 doctor_launcher 或打开 history report 审计，不要按其中 follow-up 下一步执行。</li></ul></div>"
        )
    elif freshness == "unknown":
        freshness_note = (
            '<div class="warnings"><strong>launcher report freshness 未知</strong>'
            "<ul><li>当前无法证明该 launcher report 对应本次 Dashboard；只按历史记录审计，不把 follow-up 当成当前操作建议。</li></ul></div>"
        )
    elif report.get("report_is_initial_doctor_state"):
        freshness_note = (
            '<div class="warnings"><strong>launcher report 匹配启动前 doctor</strong>'
            "<ul><li>该 report 与当前 demo_doctor 匹配，但匹配的是 initial doctor 状态；follow-up 仅供审计，不能当成当前操作建议。</li></ul></div>"
        )
    status_note = ""
    if freshness_current and status == "blocked":
        status_note = (
            '<div class="errors"><strong>启动器已阻断</strong>'
            "<ul><li>本次没有执行 rerun；请先处理 blockers 后再考虑重跑。</li></ul></div>"
        )
    elif freshness_current and status == "executed_with_followup_warning":
        status_note = (
            '<div class="warnings"><strong>重跑完成但 follow-up 需要复核</strong>'
            "<ul><li>先检查 warnings、blockers 和 follow-up 状态，不要把它当成可直接操作的命令。</li></ul></div>"
        )
    elif freshness_current and status == "executed":
        status_note = (
            '<div class="warnings"><strong>启动器已执行安全重跑</strong>'
            "<ul><li>这里仅展示执行记录；Dashboard 不会触发任何工具动作。</li></ul></div>"
        )
    status_note = freshness_note + status_note
    follow_note = ""
    if not follow_up_current:
        follow_note = ""
    elif follow_action == "try_now" and follow_up.get("try_now_allowed"):
        follow_note = (
            '<div class="warnings"><strong>游戏内可尝试</strong>'
            "<ul><li>只读提示：按执行清单去游戏内尝试；Dashboard 不触发工具动作。</li></ul></div>"
        )
    elif follow_action == "safe_apply_review_decisions" or follow_up.get("doctor_status") == "needs_apply":
        follow_note = (
            '<div class="warnings"><strong>应用复核结果前需要人工确认</strong>'
            "<ul><li>请先查看 preview 和 apply 边界；Dashboard 只展示状态。</li></ul></div>"
        )
    elif follow_action and follow_action != "N/A":
        follow_note = (
            '<div class="warnings"><strong>follow-up 下一步</strong>'
            f"<ul><li>{e(action_label(follow_action))}</li></ul></div>"
        )
    if report.get("error"):
        status_note += list_block("启动器报告读取错误", [report.get("error")], "errors")
    return f"""
    <section class="panel launcher-report">
      <h2>启动器执行记录</h2>
      <p class="muted-line">只读展示 latest launcher report：它说明启动器刚才做了什么、有没有阻断、follow-up doctor 是否可信。这里没有执行入口。</p>
      <div class="links">
        {link("launcher_report.md", report.get("output_md"))}
        {link("launcher_report.json", report.get("output_json") or report.get("report_path"))}
        {link("history_json", report.get("output_history_json"))}
        {link("history_md", report.get("output_history_md"))}
      </div>
      <div class="input-grid">
        <div><span>launcher_status</span><strong>{e(status)}</strong></div>
        <div><span>launcher report freshness</span><strong>{e(freshness)}</strong></div>
        <div><span>matches_current_doctor</span><strong>{e(bool_text(report.get("matches_current_doctor")))}</strong></div>
        <div><span>follow_up_matches_current_doctor</span><strong>{e(bool_text(report.get("follow_up_matches_current_doctor")))}</strong></div>
        <div><span>operation_state</span><strong>{e(operation_state)}</strong></div>
        <div><span>freshness_match_source</span><strong>{e(report.get("freshness_match_source") or "N/A")}</strong></div>
        <div><span>executed</span><strong>{e(bool_text(report.get("executed")))}</strong></div>
        <div><span>returncode</span><strong>{e(report.get("returncode") if report.get("returncode") is not None else "N/A")}</strong></div>
        <div><span>command_script_resolved</span><strong>{e(report.get("command_script_resolved") or "N/A")}</strong></div>
        <div><span>rerun_started_at</span><strong>{e(report.get("rerun_started_at") or "N/A")}</strong></div>
        <div><span>rerun_finished_at</span><strong>{e(report.get("rerun_finished_at") or "N/A")}</strong></div>
        <div><span>dashboard_refresh</span><strong>{e(dashboard_refresh.get("status") or "N/A")}</strong></div>
        <div><span>summary_updated</span><strong>{e(bool_text(dashboard_refresh.get("summary_updated")))}</strong></div>
        <div><span>dashboard_rendered</span><strong>{e(bool_text(dashboard_refresh.get("dashboard_rendered")))}</strong></div>
        <div><span>current_demo_doctor_sha256</span><strong>{e(report.get("current_demo_doctor_sha256") or "N/A")}</strong></div>
        <div><span>report.initial_doctor_sha256</span><strong>{e(report.get("report_initial_doctor_sha256") or "N/A")}</strong></div>
        <div><span>report.follow_up.sha256</span><strong>{e(report.get("report_follow_up_sha256") or "N/A")}</strong></div>
        <div><span>follow_up.loaded</span><strong>{e(bool_text(follow_up.get("loaded")))}</strong></div>
        <div><span>follow_up.doctor_status</span><strong>{e(follow_up.get("doctor_status") or "N/A")}</strong></div>
        <div><span>follow_up.primary_next_action</span><strong>{e(action_label(follow_action))}</strong></div>
        <div><span>follow_up.try_now_allowed</span><strong>{e(bool_text(follow_up.get("try_now_allowed")))}</strong></div>
        <div><span>follow-up 严格状态</span><strong>{e(human_status(follow_up.get("strict_status") or "N/A"))}</strong></div>
        <div><span>follow_up.updated_after_rerun</span><strong>{e(bool_text(follow_up.get("updated_after_rerun")))}</strong></div>
      </div>
      {status_note}
      {follow_note}
      {list_block("launcher blockers", blockers, "errors")}
      {list_block("launcher warnings", warnings, "warnings")}
      {list_block("freshness warnings", report.get("freshness_warnings") if isinstance(report.get("freshness_warnings"), list) else [], "warnings")}
      {list_block("dashboard refresh warnings", dashboard_refresh.get("warnings") if isinstance(dashboard_refresh.get("warnings"), list) else [], "warnings")}
      {list_block("follow-up warnings", follow_warnings, "warnings")}
      {list_block("follow-up blockers", follow_blockers, "errors")}
    </section>
    """


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
    parse_status = derived_case_status(case, "parse_status")
    expected_status = derived_case_status(case, "expected_status")
    normalized_status = derived_case_status(case, "normalized_status")
    import_status = derived_case_status(case, "import_status")
    import_blockers = case.get("import_blockers") if isinstance(case.get("import_blockers"), list) else []
    import_blocker_html = "".join(f"<li>{e(item)}</li>" for item in import_blockers)
    if import_blocker_html:
        import_blocker_html = f'<div class="errors"><strong>Import blockers</strong><ul>{import_blocker_html}</ul></div>'

    return f"""
    <article class="case-card">
      <div class="thumb">{image_html}</div>
      <div class="case-body">
        <div class="case-head">
          <h3>{e(case.get("name"))}</h3>
          <span class="badge {status_class(parse_status)}">Parse {e(parse_status)}</span>
        </div>
        <div class="facts">
          <div><span>角色</span><strong>{e(character.get("name") or "")}</strong></div>
          <div><span>等级</span><strong>{e(character.get("level") or "")}</strong></div>
          <div><span>评级</span><strong>{e(character.get("rank") or "")}</strong></div>
          <div><span>音擎</span><strong>{e(equipment.get("name") or "")}</strong></div>
          <div><span>覆盖</span><strong>{e(case.get("coverage_level") or "")}</strong></div>
          <div><span>Parse</span><strong>{e(parse_status)}</strong></div>
          <div><span>Expected 状态</span><strong>{e(expected_status)}</strong></div>
          <div><span>Normalized</span><strong>{e(normalized_status)}</strong></div>
          <div><span>Import</span><strong>{e(import_status)}</strong></div>
          <div><span>Expected</span><strong>{e(pass_rate)}</strong></div>
          <div><span>Expected JSON</span><strong>{e(expected_name)}</strong></div>
          <div><span>可信字段</span><strong>{e(quality.get("trusted_field_count"))}/{e(quality.get("field_count"))}</strong></div>
          <div><span>requires_review</span><strong>{e(quality.get("requires_manual_review"))}</strong></div>
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
        {import_blocker_html}
        {error_html}
      </div>
    </article>
    """


def render_input_panel(summary: dict[str, Any]) -> str:
    input_info = summary.get("input", {}) if isinstance(summary.get("input"), dict) else {}
    warnings = summary.get("warnings", []) if isinstance(summary.get("warnings"), list) else []
    source_mode = input_info.get("source_mode") or "unknown mode"
    warning_html = "".join(f"<li>{he(item)}</li>" for item in warnings)
    warnings_block = f'<div class="warnings"><strong>Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    return f"""
    <section class="panel input-panel">
      <h2>输入模式</h2>
      <div class="input-grid">
        <div><span>Mode</span><strong>{e(source_mode)}</strong></div>
        <div><span>images_dir</span><strong>{e(rel_label(input_info.get("images_dir")) or "N/A")}</strong></div>
        <div><span>parsed_dir</span><strong>{e(rel_label(input_info.get("parsed_dir")) or "N/A")}</strong></div>
        <div><span>manifest</span><strong>{e(rel_label(input_info.get("manifest")) or "N/A")}</strong></div>
        <div><span>parsed found</span><strong>{e(input_info.get("parsed_dir_discovered_count") if input_info.get("parsed_dir_discovered_count") is not None else "N/A")}</strong></div>
        <div><span>parsed used</span><strong>{e(input_info.get("parsed_dir_selected_count") if input_info.get("parsed_dir_selected_count") is not None else "N/A")}</strong></div>
        <div><span>targets</span><strong>{e(rel_label(input_info.get("targets")) or "N/A")}</strong></div>
        <div><span>target_source_manifest</span><strong>{e(rel_label(input_info.get("target_source_manifest")) or "N/A")}</strong></div>
        <div><span>character_catalog</span><strong>{e(rel_label(input_info.get("character_catalog")) or "N/A")}</strong></div>
        <div><span>roster_dir</span><strong>{e(rel_label(input_info.get("roster_dir")) or "N/A")}</strong></div>
        <div><span>tier_snapshot</span><strong>{e(rel_label(input_info.get("tier_snapshot")) or "N/A")}</strong></div>
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
    character_updates = update.get("character_updates") if isinstance(update.get("character_updates"), list) else []
    update_rows = []
    for item in character_updates[:8]:
        if not isinstance(item, dict):
            continue
        update_rows.append(
            '<article class="resource-item">'
            f'<strong>{e(item.get("character"))}</strong>'
            f'<span>{e(item.get("image_name"))} · {e(item.get("update_status"))} · {e(item.get("review_status") or "N/A")}</span>'
            f'<em>{e("review" if item.get("requires_manual_review") else "ok")}</em>'
            '</article>'
        )
    skipped = update.get("skipped_images") if isinstance(update.get("skipped_images"), list) else []
    skipped_text = "、".join(str(item) for item in skipped[:6])
    updates_block = ""
    if update_rows or skipped_text:
        update_list = "".join(update_rows) or '<div class="empty small">本轮没有处理角色。</div>'
        updates_block = (
            '<div class="resource-plan"><h3>本轮角色更新</h3>'
            f'<div class="resource-list">{update_list}</div>'
            f'<p class="muted-line">跳过未变更图片：{e(skipped_text or "none")}</p>'
            '</div>'
        )
    return f"""
    <section class="panel">
      <h2>本地更新扫描</h2>
      <div class="input-grid">
        <div><span>state_file</span><strong>{e(rel_label(update.get("state_file")) or "N/A")}</strong></div>
        <div><span>discovered</span><strong>{e(update.get("discovered_image_count", 0))}</strong></div>
        <div><span>processed</span><strong>{e(update.get("processed_image_count", 0))}</strong></div>
        <div><span>characters</span><strong>{e(update.get("processed_character_count", 0))}</strong></div>
        <div><span>skipped unchanged</span><strong>{e(update.get("skipped_unchanged_count", 0))}</strong></div>
        <div><span>new</span><strong>{e(counts.get("new", 0))}</strong></div>
        <div><span>changed</span><strong>{e(counts.get("changed", 0))}</strong></div>
      </div>
      {updates_block}
    </section>
    """


def render_training_plan(summary: dict[str, Any]) -> str:
    plan = summary.get("training_plan")
    if not isinstance(plan, dict):
        return ""
    error = plan.get("error")
    items = plan.get("top_plan_items") if isinstance(plan.get("top_plan_items"), list) else []
    warnings = plan.get("warnings") if isinstance(plan.get("warnings"), list) else []
    warning_html = "".join(f"<li>{he(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Planner Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    resource = plan.get("resource_plan") if isinstance(plan.get("resource_plan"), dict) else {}
    source_status = plan.get("target_source_status") if isinstance(plan.get("target_source_status"), dict) else {}
    catalog_summary = plan.get("character_catalog_summary") if isinstance(plan.get("character_catalog_summary"), dict) else {}
    coverage = plan.get("target_coverage") if isinstance(plan.get("target_coverage"), list) else []
    gap_actions = plan.get("coverage_gap_actions") if isinstance(plan.get("coverage_gap_actions"), list) else []
    source_status_block = ""
    if source_status:
        source_status_block = f"""
        <div class="input-grid">
          <div><span>source status</span><strong>{e(source_status.get("status", "N/A"))}</strong></div>
          <div><span>source freshness</span><strong>{e(source_status.get("freshness_level", "N/A"))}</strong></div>
          <div><span>current ready</span><strong>{e(source_status.get("current_endgame_ready", "N/A"))}</strong></div>
          <div><span>plan confidence</span><strong>{e(source_status.get("planning_confidence", "N/A"))}</strong></div>
          <div><span>catalog entries</span><strong>{e(catalog_summary.get("entry_count", "N/A"))}</strong></div>
        </div>
        """
    coverage_block = ""
    if coverage:
        rows = []
        for item in coverage[:6]:
            matched = item.get("matched_characters") if isinstance(item.get("matched_characters"), list) else []
            names = "、".join(str(match.get("character")) for match in matched if isinstance(match, dict) and match.get("character"))
            candidates = item.get("catalog_candidates") if isinstance(item.get("catalog_candidates"), list) else []
            candidate_names = "、".join(
                str(candidate.get("character")) for candidate in candidates[:3] if isinstance(candidate, dict) and candidate.get("character")
            )
            detail = names or (f"候选：{candidate_names}" if candidate_names else "none")
            source_hint = evidence_hint(item.get("evidence"))
            detail_text = detail if not source_hint else f"{detail} · {source_hint}"
            rows.append(
                "<article class=\"resource-item\">"
                f"<strong>{e(item.get('target'))}</strong>"
                f"<span>{e(item.get('coverage_status'))}: {e(detail_text)}</span>"
                f"<em>{e(item.get('match_count', 0))}</em>"
                "</article>"
            )
        coverage_block = f"""
        <div class="resource-plan">
          <h3>目标覆盖</h3>
          <div class="resource-list">{''.join(rows)}</div>
        </div>
        """
    gap_action_block = ""
    if gap_actions:
        rows = []
        for item in gap_actions[:6]:
            rows.append(
                "<article class=\"resource-item\">"
                f"<strong>#{e(item.get('rank'))} {e(item.get('character'))}</strong>"
                f"<span>{e(item.get('target'))} · {e(item.get('action'))}</span>"
                f"<em>{e(item.get('confidence'))}</em>"
                "</article>"
            )
        gap_action_block = f"""
        <div class="resource-plan">
          <h3>长期补洞候选</h3>
          <div class="resource-list">{''.join(rows)}</div>
        </div>
        """
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
            match_reasons = item.get("target_match_reasons") if isinstance(item.get("target_match_reasons"), list) else []
            match_hint = f"<span>{e(match_reasons[0])}</span>" if match_reasons else ""
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">#{e(item.get('priority_rank'))}</div>"
                "<div>"
                f"<h3>{e(item.get('character'))} · {e(item.get('action'))}</h3>"
                f"<p>{e(item.get('reason'))}</p>"
                f"<span>{e(item.get('target'))}</span>"
                f"{match_hint}"
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
      {source_status_block}
      {warning_block}
      {coverage_block}
      {gap_action_block}
      {resource_block}
      {body}
    </section>
    """


def render_action_cards(summary: dict[str, Any]) -> str:
    actions = summary.get("action_cards")
    if not isinstance(actions, dict):
        return ""
    error = actions.get("error")
    cards = actions.get("cards") if isinstance(actions.get("cards"), list) else []
    card_summary = actions.get("summary") if isinstance(actions.get("summary"), dict) else {}
    warnings = actions.get("warnings") if isinstance(actions.get("warnings"), list) else []
    warning_html = "".join(f"<li>{he(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Action Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if error:
        body = f'<div class="errors"><strong>Action cards failed</strong><ul><li>{e(error)}</li></ul></div>'
    elif not cards:
        body = '<div class="empty">没有生成下一步行动卡。</div>'
    else:
        rows = []
        for item in cards[:8]:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            tier_signal = item.get("tier_signal") if isinstance(item.get("tier_signal"), dict) else {}
            evidence_bits = []
            if evidence.get("target_source"):
                evidence_bits.append(str(evidence.get("target_source")))
            if evidence.get("target_hash"):
                evidence_bits.append(str(evidence.get("target_hash")))
            tier_bits = []
            if tier_signal:
                tier_bits.append(str(tier_signal.get("recommendation") or "unknown"))
                if tier_signal.get("tier"):
                    tier_bits.append(f"tier {tier_signal.get('tier')}")
                if tier_signal.get("retention_score") is not None:
                    tier_bits.append(f"保值 {percent_label(tier_signal.get('retention_score'))}")
            tier_note = f"<span>保值观察：{e(' · '.join(tier_bits))}</span>" if tier_bits else ""
            source_note = (
                "候选 ≠ 已拥有"
                if item.get("source_class") in {"pending_snapshot", "catalog_candidate", "catalog_owned_missing_snapshot"}
                else "已确认角色库"
            )
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">#{e(item.get('rank'))}</div>"
                "<div>"
                f"<h3>{e(item.get('title'))}</h3>"
                f"<p>{e(item.get('reason'))}</p>"
                f"<span>{e(item.get('target'))}</span>"
                f"<span>{e(source_note)} · 证据：{e(' · '.join(evidence_bits) or 'N/A')}</span>"
                f"{tier_note}"
                "</div>"
                f"<strong>{e(item.get('priority'))}<br>{e(item.get('status'))}</strong>"
                "</article>"
            )
        body = '<div class="plan-list">' + "".join(rows) + "</div>"
    return f"""
    <section class="panel">
      <h2>下一步行动</h2>
      <p class="muted-line">候选 ≠ 已拥有；目录候选必须先确认拥有状态或补录官方分享图。</p>
      <div class="links">
        {link("action_cards.md", actions.get("output_md"))}
        {link("action_cards.json", actions.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>已覆盖目标</span><strong>{e(card_summary.get("covered_target_count", "N/A"))}</strong></div>
        <div><span>未覆盖目标</span><strong>{e(card_summary.get("uncovered_target_count", "N/A"))}</strong></div>
        <div><span>高优先级</span><strong>{e(card_summary.get("high_priority_action_count", "N/A"))}</strong></div>
        <div><span>需补录</span><strong>{e(card_summary.get("needs_recording_count", "N/A"))}</strong></div>
        <div><span>保值信号</span><strong>{e(card_summary.get("tier_signal_count", "N/A"))}</strong></div>
        <div><span>高保值行动</span><strong>{e(card_summary.get("high_value_owned_action_count", "N/A"))}</strong></div>
        <div><span>低保值复核</span><strong>{e(card_summary.get("low_value_review_count", "N/A"))}</strong></div>
        <div><span>已确认角色</span><strong>{e(card_summary.get("owned_character_count", "N/A"))}</strong></div>
        <div><span>待确认快照</span><strong>{e(card_summary.get("pending_snapshot_count", "N/A"))}</strong></div>
        <div><span>snapshot files</span><strong>{e(card_summary.get("snapshot_file_count", "N/A"))}</strong></div>
      </div>
      {warning_block}
      {body}
    </section>
    """


def render_team_cards(summary: dict[str, Any]) -> str:
    teams = summary.get("team_cards")
    if not isinstance(teams, dict):
        return ""
    error = teams.get("error")
    cards = teams.get("cards") if isinstance(teams.get("cards"), list) else []
    team_summary = teams.get("summary") if isinstance(teams.get("summary"), dict) else {}
    warnings = teams.get("warnings") if isinstance(teams.get("warnings"), list) else []
    warning_html = "".join(f"<li>{he(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Team Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if error:
        body = f'<div class="errors"><strong>Team cards failed</strong><ul><li>{e(error)}</li></ul></div>'
    elif not cards:
        body = '<div class="empty">没有生成高难配队候选卡。</div>'
    else:
        rows = []
        for item in cards[:8]:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            team_value = item.get("team_value") if isinstance(item.get("team_value"), dict) else {}
            members = item.get("members") if isinstance(item.get("members"), list) else []
            member_bits = []
            for member in members:
                if not isinstance(member, dict):
                    continue
                tier_signal = member.get("tier_signal") if isinstance(member.get("tier_signal"), dict) else {}
                tier_badge = ""
                if tier_signal:
                    tier_badge = (
                        f" · {tier_signal.get('tier') or 'tier?'}"
                        f"/{tier_signal.get('observation_status') or tier_signal.get('recommendation') or 'observe'}"
                        f"/{tier_signal.get('entry_status') or 'verified'}"
                    )
                member_bits.append(
                    f"{member.get('slot')}: {member.get('character')} [{member.get('source_class')}]{tier_badge}"
                )
            card_warnings = item.get("warnings") if isinstance(item.get("warnings"), list) else []
            warning_text = "；".join(str(warning) for warning in card_warnings) or "none"
            evidence_bits = []
            if evidence.get("target_source"):
                evidence_bits.append(str(evidence.get("target_source")))
            if evidence.get("target_hash"):
                evidence_bits.append(str(evidence.get("target_hash")))
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">#{e(item.get('rank'))}</div>"
                "<div>"
                f"<h3>{e(item.get('team_title'))}</h3>"
                f"<p>{e(item.get('coverage_reason'))}</p>"
                f"<span>{e(' / '.join(member_bits) or '无成员')}</span>"
                f"<span>队伍保值：已确认高保值 {e(team_value.get('accepted_high_value_members', 0))} · 过期 {e(team_value.get('stale_meta_count', 0))} · 未验证 {e(team_value.get('unverified_meta_count', 0))}</span>"
                f"<span>证据：{e(' · '.join(evidence_bits) or 'N/A')}</span>"
                f"<span>警告：{he(warning_text)}</span>"
                "</div>"
                f"<strong>{e(item.get('target_priority'))}<br>{e(item.get('team_status'))}</strong>"
                "</article>"
            )
        body = '<div class="plan-list">' + "".join(rows) + "</div>"
    return f"""
    <section class="panel">
      <h2>高难配队候选</h2>
      <p class="muted-line">队伍候选基于已确认角色库、本地快照、本地目录与本地保值观察；目录候选不代表已拥有，保值观察不是抽取建议。</p>
      <div class="links">
        {link("team_cards.md", teams.get("output_md"))}
        {link("team_cards.json", teams.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>目标数</span><strong>{e(team_summary.get("target_count", "N/A"))}</strong></div>
        <div><span>队伍卡</span><strong>{e(team_summary.get("team_card_count", "N/A"))}</strong></div>
        <div><span>当前可用</span><strong>{e(team_summary.get("playable_now_count", "N/A"))}</strong></div>
        <div><span>需补录</span><strong>{e(team_summary.get("needs_recording_count", "N/A"))}</strong></div>
        <div><span>目录候选</span><strong>{e(team_summary.get("catalog_candidate_count", "N/A"))}</strong></div>
        <div><span>已确认高保值成员</span><strong>{e(team_summary.get("accepted_high_value_member_count", "N/A"))}</strong></div>
        <div><span>高保值可用队伍</span><strong>{e(team_summary.get("high_value_playable_team_count", "N/A"))}</strong></div>
        <div><span>过期保值观察</span><strong>{e(team_summary.get("stale_meta_count", "N/A"))}</strong></div>
        <div><span>未验证保值观察</span><strong>{e(team_summary.get("unverified_meta_count", "N/A"))}</strong></div>
      </div>
      {warning_block}
      {body}
    </section>
    """


def render_review_inbox(summary: dict[str, Any]) -> str:
    inbox = summary.get("review_inbox")
    if not isinstance(inbox, dict):
        return ""
    pending = inbox.get("pending") if isinstance(inbox.get("pending"), list) else []
    accepted = inbox.get("accepted") if isinstance(inbox.get("accepted"), list) else []
    rejected = inbox.get("rejected") if isinstance(inbox.get("rejected"), list) else []
    rows = []
    for item in pending[:8]:
        if not isinstance(item, dict):
            continue
        blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
        rows.append(
            "<article class=\"resource-item\">"
            f"<strong>{e(item.get('character'))}</strong>"
            f"<span>Lv.{e(item.get('level'))} · {e(item.get('equipment'))} · 可信字段 {e(item.get('trusted_field_count'))}/{e(item.get('field_count'))} · 阻断项：{e('；'.join(str(blocker) for blocker in blockers) or '无')}</span>"
            f"<em>{link('review', item.get('review_html'))} {link('json', item.get('normalized_json'))}</em>"
            "</article>"
        )
    pending_block = "".join(rows) if rows else '<div class="empty small">没有待确认快照。</div>'
    accepted_names = "、".join(str(item.get("character")) for item in accepted[:8] if isinstance(item, dict))
    rejected_names = "、".join(str(item.get("character")) for item in rejected[:8] if isinstance(item, dict))
    apply_command = command_details(
        "复核应用命令（确认后再复制）",
        [("应用命令", inbox.get("decision_command"))],
    )
    return f"""
    <section class="panel">
      <h2>练度更新收件箱</h2>
      <p class="muted-line">本地标准化快照只是图片识别/解析候选；只有已确认角色库可以作为已拥有练度。</p>
      <div class="links">
        {link("roster_index.json", inbox.get("roster_index_json"))}
        {link("review_apply_receipt.md", inbox.get("review_apply_receipt_md"))}
        {link("review_apply_receipt.json", inbox.get("review_apply_receipt_json"))}
        {link("review_log.json", inbox.get("review_log_json"))}
      </div>
      <div class="input-grid">
        <div><span>待确认快照</span><strong>{e(inbox.get("pending_count", 0))}</strong></div>
        <div><span>已接收快照</span><strong>{e(inbox.get("accepted_count", 0))}</strong></div>
        <div><span>已拒绝快照</span><strong>{e(inbox.get("rejected_count", 0))}</strong></div>
        <div><span>安全应用</span><strong>{e(human_status(inbox.get("safe_apply_status") or "not_applied"))}</strong></div>
        <div><span>需要复核</span><strong>{e(inbox.get("needs_manual_review_count", 0))}</strong></div>
        <div><span>已确认角色</span><strong>{e(accepted_names or "无")}</strong></div>
        <div><span>已拒绝角色</span><strong>{e(rejected_names or "无")}</strong></div>
      </div>
      {apply_command}
      <div class="resource-plan">
        <h3>待确认快照</h3>
        <div class="resource-list">{pending_block}</div>
      </div>
    </section>
    """


def render_refresh_status(summary: dict[str, Any]) -> str:
    refresh = summary.get("refresh_status")
    if not isinstance(refresh, dict):
        return ""
    refresh_summary = refresh.get("summary") if isinstance(refresh.get("summary"), dict) else {}
    action_state = refresh.get("action_state") if isinstance(refresh.get("action_state"), dict) else {}
    command_state = refresh.get("command_state") if isinstance(refresh.get("command_state"), dict) else {}
    reasons = refresh.get("stale_reasons") if isinstance(refresh.get("stale_reasons"), list) else []
    affected = refresh.get("affected_artifacts") if isinstance(refresh.get("affected_artifacts"), list) else []
    warnings = refresh.get("warnings") if isinstance(refresh.get("warnings"), list) else []
    next_action = str(action_state.get("primary_next_action") or "unknown")
    next_action_label = action_label(next_action) if next_action else "N/A"
    try_now_allowed = action_state.get("try_now_allowed")
    try_now_text = "未知" if try_now_allowed is None else "是" if try_now_allowed else "否"
    rerun_required = action_state.get("rerun_required")
    rerun_text = "未知" if rerun_required is None else "是" if rerun_required else "否"
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Refresh Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if refresh.get("error"):
        body = f'<div class="errors"><strong>Refresh status failed</strong><ul><li>{e(refresh.get("error"))}</li></ul></div>'
    else:
        reason_items = "".join(f"<li>{e(item)}</li>" for item in reasons) or "<li>无</li>"
        affected_text = "、".join(str(item) for item in affected) if affected else "无"
        body = f"""
        <div class="resource-plan">
          <h3>刷新判断</h3>
          <ul>{reason_items}</ul>
          <p class="muted-line">受影响产物：{e(affected_text)}</p>
          <p class="muted-line">{e(refresh.get("refresh_command") or "")}</p>
        </div>
        """
    stale_copy = ""
    if refresh.get("refresh_status") == "stale_after_apply":
        stale_copy = (
            '<div class="errors"><strong>当前简报可能过期</strong>'
            "<ul><li>人工应用已经改变已确认 roster；当前高难方案/今日简报可能仍基于旧 box。请重跑演示流程后再执行可尝试项。</li></ul></div>"
        )
    elif refresh.get("refresh_status") == "unknown":
        stale_copy = (
            '<div class="errors"><strong>刷新状态无法确认</strong>'
            "<ul><li>无法确认当前页面是否已吸收最新人工应用结果；请重跑演示流程后再执行可尝试项。</li></ul></div>"
        )
    return f"""
    <section class="panel refresh-status">
      <h2>刷新状态</h2>
      <p class="muted-line">先判断当前 Dashboard 是否已经吸收最新 review apply。这里不是解析结果，而是最终建议的新鲜度门禁。</p>
      <div class="links">
        {link("refresh_status.md", refresh.get("output_md"))}
        {link("refresh_status.json", refresh.get("output_json"))}
        {link("demo_command.md", command_state.get("demo_command_md"))}
        {link("demo_command.json", command_state.get("demo_command_json"))}
      </div>
      <div class="input-grid">
        <div><span>refresh status</span><strong>{e(refresh.get("refresh_status") or "unknown")}</strong></div>
        <div><span>needs refresh</span><strong>{e(refresh_summary.get("needs_demo_refresh", "N/A"))}</strong></div>
        <div><span>当前下一步</span><strong>{e(next_action_label)}</strong></div>
        <div><span>可执行 try_now</span><strong>{e(try_now_text)}</strong></div>
        <div><span>需要重跑</span><strong>{e(rerun_text)}</strong></div>
        <div><span>receipt exists</span><strong>{e(refresh_summary.get("receipt_exists", "N/A"))}</strong></div>
        <div><span>entered roster</span><strong>{e(refresh_summary.get("did_enter_roster_count", "N/A"))}</strong></div>
        <div><span>wrote accepted</span><strong>{e(refresh_summary.get("did_write_accepted_count", "N/A"))}</strong></div>
        <div><span>wrote rejected</span><strong>{e(refresh_summary.get("did_write_rejected_count", "N/A"))}</strong></div>
      </div>
      {stale_copy}
      {warning_block}
      {body}
    </section>
    """


def render_final_brief(summary: dict[str, Any]) -> str:
    brief = summary.get("final_brief")
    if not isinstance(brief, dict):
        return ""
    brief_summary = brief.get("summary") if isinstance(brief.get("summary"), dict) else {}
    top_cards = brief.get("top_cards") if isinstance(brief.get("top_cards"), list) else []
    warnings = brief.get("warnings") if isinstance(brief.get("warnings"), list) else []
    warning_html = "".join(f"<li>{he(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>为什么不能直接用</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    overview = render_brief_overview(brief, brief_summary, warnings)
    flow = render_brief_flow(brief_summary, warnings)
    valid_cards = [item for item in top_cards if isinstance(item, dict)]
    next_step = render_brief_next_step(valid_cards[0] if valid_cards else None)
    if brief.get("error"):
        body = f'<div class="errors"><strong>简报生成失败</strong><ul><li>{he(brief.get("error"))}</li></ul></div>'
    elif not valid_cards:
        body = '<div class="empty">暂无可执行事项；先补齐本地确认数据。</div>'
    else:
        rows = []
        hidden_items = valid_cards[VISIBLE_BRIEF_CARD_LIMIT:]
        for item in valid_cards[:VISIBLE_BRIEF_CARD_LIMIT]:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            item_warnings = item.get("warnings") if isinstance(item.get("warnings"), list) else []
            warning_text = "；".join(str(warning) for warning in item_warnings if warning)
            card_type = brief_card_type_label(item.get("card_type"))
            target_line = []
            if item.get("target"):
                target_line.append(f"目标：{item.get('target')}")
            if item.get("character"):
                target_line.append(f"角色：{item.get('character')}")
            quick_links = []
            review_href = evidence.get("review_html") or evidence.get("source")
            if review_href:
                quick_links.append(link("打开复核页", review_href))
            if evidence.get("normalized_json"):
                quick_links.append(link("标准化 JSON", evidence.get("normalized_json")))
            details = (
                "<details class=\"brief-details\"><summary>证据明细</summary>"
                f"<p class=\"detail-hint\"><strong>下一步说明</strong><span>{he(command_hint_summary(item.get('command_hint')))}</span></p>"
                f"<ul class=\"brief-evidence\">{brief_evidence_rows(evidence)}</ul>"
                "</details>"
            )
            rows.append(
                "<article class=\"brief-card\">"
                f"<div class=\"plan-rank\">#{e(item.get('rank'))}</div>"
                "<div class=\"brief-main\">"
                f"<div class=\"brief-card-head\"><span class=\"badge muted\">{e(card_type)}</span><h3>{he(item.get('title'))}</h3></div>"
                f"<p>{he(item.get('reason'))}</p>"
                f"<span>{he(' · '.join(target_line) or '本项不绑定具体目标/角色')}</span>"
                f"<div class=\"brief-links\">{''.join(quick_links) or '<span class=\"missing\">暂无可打开证据</span>'}</div>"
                f"{'<span>警告：' + he(warning_text) + '</span>' if warning_text else ''}"
                f"{details}"
                f"<div class=\"brief-action\">{e(brief_action_label(item))}</div>"
                "</div>"
                "</article>"
            )
        hidden_block = ""
        if hidden_items:
            hidden_rows = "".join(
                "<li>"
                f"<strong>#{e(item.get('rank'))} {he(item.get('title'))}</strong>"
                f"<span>{e(brief_action_label(item))}</span>"
                "</li>"
                for item in hidden_items
            )
            hidden_block = (
                f'<details class="more-brief-cards"><summary>还有 {len(hidden_items)} 个待处理项</summary>'
                f"<ul>{hidden_rows}</ul>"
                "</details>"
            )
        body = '<div class="brief-list">' + "".join(rows) + "</div>" + hidden_block
    status_text = human_status(brief.get("brief_status") or "N/A")
    status_note = ""
    if str(brief.get("brief_status") or "").lower() == "needs_review":
        status_note = (
            '<div class="warnings"><strong>当前不能直接按配队行动</strong>'
            "<ul><li>还有解析快照待人工确认。先打开复核页看图和字段，确认后再进入已确认角色库。</li></ul></div>"
        )
    stat_rows = [
        ("总判断", status_text),
        ("可直接行动", brief_summary.get("trusted_plan_count", "N/A")),
        ("待确认快照", brief_summary.get("pending_review_count", "N/A")),
        ("可尝试目标", brief_summary.get("ready_now_target_count", "N/A")),
        ("缺练度目标", brief_summary.get("needs_recording_target_count", "N/A")),
        ("仅观察目标", brief_summary.get("watch_only_target_count", "N/A")),
    ]
    return f"""
    <section class="panel final-brief">
      <h2>今日作战简报</h2>
      <p class="muted-line">先看这一块就够了：它只回答“现在能不能用、卡在哪里、下一步点哪里”。命令和技术证据默认折叠。</p>
      {overview}
      {flow}
      {next_step}
      {status_note}
      {warning_block}
      {body}
      {stats_details("统计数字", stat_rows)}
    </section>
    """


def render_action_checklist(summary: dict[str, Any]) -> str:
    checklist = summary.get("action_checklist")
    if not isinstance(checklist, dict):
        return ""
    checklist_summary = checklist.get("summary") if isinstance(checklist.get("summary"), dict) else {}
    preview = summary.get("review_decision_preview") if isinstance(summary.get("review_decision_preview"), dict) else {}
    preview_summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
    safe_apply = safe_apply_status(summary)
    safe_command = checklist.get("safe_apply_command") or preview.get("next_command") or ""
    items = checklist.get("items") if isinstance(checklist.get("items"), list) else []
    warnings = checklist.get("warnings") if isinstance(checklist.get("warnings"), list) else []
    warning_html = "".join(f"<li>{he(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>清单警告</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if checklist.get("error"):
        body = f'<div class="errors"><strong>执行清单生成失败</strong><ul><li>{e(checklist.get("error"))}</li></ul></div>'
    elif not items:
        body = '<div class="empty">暂无执行项。</div>'
    else:
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            item_warnings = item.get("warnings") if isinstance(item.get("warnings"), list) else []
            warning_text = "；".join(str(warning) for warning in item_warnings if warning)
            target_bits = []
            if item.get("target"):
                target_bits.append(f"目标：{item.get('target')}")
            if item.get("character"):
                target_bits.append(f"角色：{item.get('character')}")
            quick_links = []
            if evidence.get("review_html"):
                quick_links.append(link("打开复核页", evidence.get("review_html")))
            if evidence.get("normalized_json"):
                quick_links.append(link("标准化 JSON", evidence.get("normalized_json")))
            if evidence.get("artifact"):
                quick_links.append(link("相关产物", evidence.get("artifact")))
            detail_rows = []
            for label, value in (
                ("复核页", evidence.get("review_html")),
                ("标准化结果", evidence.get("normalized_json")),
                ("目标 hash", evidence.get("target_hash")),
                ("产物", evidence.get("artifact")),
            ):
                if value:
                    detail_rows.append(f"<li><strong>{e(label)}</strong><span>{e(rel_label(value) or value)}</span></li>")
            details = (
                '<details class="brief-details"><summary>证据明细</summary>'
                f'<p class="detail-hint"><strong>下一步说明</strong><span>{he(command_hint_summary(item.get("command_hint")))}</span></p>'
                f'<ul class="brief-evidence">{"".join(detail_rows) or "<li><strong>证据</strong><span>N/A</span></li>"}</ul>'
                "</details>"
            )
            rows.append(
                "<article class=\"brief-card\">"
                f"<div class=\"plan-rank\">#{e(item.get('rank'))}</div>"
                "<div class=\"brief-main\">"
                f"<h3>{he(item.get('title'))}</h3>"
                f"<p>{he(checklist_status_line(item))}</p>"
                f"<span>{he(' · '.join(target_bits) or '本项不绑定具体目标/角色')}</span>"
                f"<div class=\"brief-links\">{''.join(quick_links) or '<span class=\"missing\">暂无可打开证据</span>'}</div>"
                f"{'<span>警告：' + he(warning_text) + '</span>' if warning_text else ''}"
                f"{details}"
                f"<div class=\"brief-action\">{e(checklist_action_label(item))}</div>"
                "</div>"
                "</article>"
            )
        body = '<div class="brief-list">' + "".join(rows) + "</div>"
    command_block = command_details(
        "复核命令（确认后再复制）",
        [
            ("预览命令", checklist.get("preview_command")),
            (f"应用命令：{safe_apply}", safe_command),
        ],
    )
    return f"""
    <section class="panel action-checklist">
      <h2>执行清单</h2>
      <p class="muted-line">从今日作战简报生成的最多 5 件事；待确认项只会生成复核模板，仅观察项不是抽卡建议。</p>
      <div class="links">
        {link("action_checklist.md", checklist.get("output_md"))}
        {link("action_checklist.json", checklist.get("output_json"))}
        {link("review_decisions_template.json", checklist.get("review_decisions_template"))}
        {link("review_decision_preview.md", preview.get("output_md"))}
        {link("review_decision_preview.json", preview.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>清单状态</span><strong>{e(human_status(checklist.get("checklist_status") or "N/A"))}</strong></div>
        <div><span>预览状态</span><strong>{e(human_status(preview.get("preview_status") or "N/A"))}</strong></div>
        <div><span>安全应用</span><strong>{e(human_status(safe_apply))}</strong></div>
        <div><span>事项数</span><strong>{e(checklist_summary.get("item_count", "N/A"))}</strong></div>
        <div><span>可执行</span><strong>{e(checklist_summary.get("ready_count", "N/A"))}</strong></div>
        <div><span>待复核</span><strong>{e(checklist_summary.get("needs_review_count", "N/A"))}</strong></div>
        <div><span>已阻断</span><strong>{e(checklist_summary.get("blocked_count", "N/A"))}</strong></div>
        <div><span>隐藏项</span><strong>{e(checklist_summary.get("hidden_item_count", "N/A"))}</strong></div>
        <div><span>将写入角色库</span><strong>{e(preview_summary.get("would_update_roster_count", "N/A"))}</strong></div>
      </div>
      <p class="muted-line">复核决策必须先预览，再人工应用；预览不会写 accepted/rejected。</p>
      {warning_block}
      {body}
      {command_block}
    </section>
    """


def safe_apply_status(summary: dict[str, Any]) -> str:
    apply_info = summary.get("review_apply") if isinstance(summary.get("review_apply"), dict) else {}
    if apply_info and not apply_info.get("error") and apply_info.get("output_json"):
        return "applied"
    inbox_info = summary.get("review_inbox") if isinstance(summary.get("review_inbox"), dict) else {}
    if inbox_info.get("safe_apply_status"):
        return str(inbox_info.get("safe_apply_status"))
    if inbox_info.get("review_apply_receipt_json"):
        return "applied"
    preview = summary.get("review_decision_preview") if isinstance(summary.get("review_decision_preview"), dict) else {}
    preview_status = str(preview.get("preview_status") or "").lower()
    if preview_status in {"blocked", "needs_review"}:
        return "blocked"
    return "not_applied"


def render_review_apply(summary: dict[str, Any]) -> str:
    review_apply = summary.get("review_apply")
    if not isinstance(review_apply, dict):
        inbox = summary.get("review_inbox") if isinstance(summary.get("review_inbox"), dict) else {}
        if not inbox.get("review_apply_receipt_json") and not inbox.get("review_apply_receipt_md"):
            return ""
        review_apply = {
            "apply_status": safe_apply_status(summary),
            "output_json": inbox.get("review_apply_receipt_json"),
            "output_md": inbox.get("review_apply_receipt_md"),
            "review_log_json": inbox.get("review_log_json"),
            "summary": {},
            "records": [],
        }
    receipt_summary = review_apply.get("summary") if isinstance(review_apply.get("summary"), dict) else {}
    records = review_apply.get("records") if isinstance(review_apply.get("records"), list) else []
    warnings = review_apply.get("warnings") if isinstance(review_apply.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Apply Receipt Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if review_apply.get("error"):
        body = f'<div class="errors"><strong>Review apply receipt failed</strong><ul><li>{e(review_apply.get("error"))}</li></ul></div>'
    elif not records:
        body = '<div class="empty">还没有 apply receipt；当前只是预览或待人工处理。</div>'
    else:
        rows = []
        for item in records:
            if not isinstance(item, dict):
                continue
            effect = []
            if item.get("did_enter_roster"):
                effect.append("进入 roster")
            if item.get("did_write_accepted"):
                effect.append("写 accepted")
            if item.get("did_write_rejected"):
                effect.append("写 rejected")
            if not effect:
                effect.append("无写入")
            rows.append(
                "<article class=\"resource-item\">"
                f"<strong>{e(item.get('character'))}</strong>"
                f"<span>{e(item.get('decision'))} · {e(item.get('status'))} · {e(' / '.join(effect))} · preview={e(item.get('preview_validation_status'))}</span>"
                f"<em>{e(item.get('preview_decision_status') or item.get('normalized_json_sha256') or 'N/A')}</em>"
                "</article>"
            )
        hidden = review_apply.get("hidden_record_count") or 0
        hidden_text = f'<p class="muted-line">另有 {e(hidden)} 条 receipt record 未展示。</p>' if hidden else ""
        body = f'<div class="resource-plan"><h3>应用回执记录</h3><div class="resource-list">{"".join(rows)}</div>{hidden_text}</div>'
    return f"""
    <section class="panel">
      <h2>复核应用回执</h2>
      <p class="muted-line">这里展示 apply 之后真实发生的副作用：是否写入 accepted/rejected、是否进入 roster index，以及是否经过 preview 校验。</p>
      <div class="links">
        {link("review_apply_receipt.md", review_apply.get("output_md"))}
        {link("review_apply_receipt.json", review_apply.get("output_json"))}
        {link("review_log.json", review_apply.get("review_log_json"))}
      </div>
      <div class="input-grid">
        <div><span>apply status</span><strong>{e(review_apply.get("apply_status") or "not_applied")}</strong></div>
        <div><span>accepted</span><strong>{e(receipt_summary.get("accepted_count", "N/A"))}</strong></div>
        <div><span>rejected</span><strong>{e(receipt_summary.get("rejected_count", "N/A"))}</strong></div>
        <div><span>pending</span><strong>{e(receipt_summary.get("pending_count", "N/A"))}</strong></div>
        <div><span>entered roster</span><strong>{e(receipt_summary.get("did_enter_roster_count", "N/A"))}</strong></div>
        <div><span>wrote accepted</span><strong>{e(receipt_summary.get("did_write_accepted_count", "N/A"))}</strong></div>
        <div><span>wrote rejected</span><strong>{e(receipt_summary.get("did_write_rejected_count", "N/A"))}</strong></div>
        <div><span>preview validated</span><strong>{e(receipt_summary.get("preview_validated_count", "N/A"))}</strong></div>
        <div><span>preview missing</span><strong>{e(receipt_summary.get("preview_not_provided_count", "N/A"))}</strong></div>
      </div>
      {warning_block}
      {body}
    </section>
    """


def render_roster_delta(summary: dict[str, Any]) -> str:
    delta = summary.get("roster_delta")
    if not isinstance(delta, dict):
        return ""
    error = delta.get("error")
    delta_summary = delta.get("summary") if isinstance(delta.get("summary"), dict) else {}
    changes = delta.get("character_changes") if isinstance(delta.get("character_changes"), list) else []
    warnings = delta.get("warnings") if isinstance(delta.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Delta Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if error:
        body = f'<div class="errors"><strong>Roster delta failed</strong><ul><li>{e(error)}</li></ul></div>'
    elif not changes:
        body = '<div class="empty">没有可展示的 accepted roster 变化。</div>'
    else:
        rows = []
        visible_changes = [item for item in changes if isinstance(item, dict) and item.get("change_type") != "unchanged"]
        for item in (visible_changes or changes)[:8]:
            tier = item.get("tier_observation") if isinstance(item.get("tier_observation"), dict) else {}
            field_changes = item.get("field_changes") if isinstance(item.get("field_changes"), list) else []
            fields = "、".join(
                str(change.get("field")) for change in field_changes[:4] if isinstance(change, dict) and change.get("field")
            )
            impacted_targets = "、".join(str(target) for target in item.get("impacted_targets", []) if target)
            warnings_text = "；".join(str(warning) for warning in item.get("warnings", []) if warning)
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">{e(item.get('change_type'))}</div>"
                "<div>"
                f"<h3>{e(item.get('character'))}</h3>"
                f"<p>{e(fields or '字段未变化')}</p>"
                f"<span>受影响目标/队伍：{e(impacted_targets or 'none')}</span>"
                f"<span>tier / 保值观察：{e(tier.get('tier') or 'N/A')} · {e(tier.get('status') or 'missing')} · {e(tier.get('trend') or 'trend?')}</span>"
                f"<span>{e(warnings_text or 'delta 只基于 accepted roster，不包含 pending snapshot')}</span>"
                "</div>"
                f"<strong>{e(item.get('new_snapshot_json') or item.get('old_snapshot_json') or 'N/A')}</strong>"
                "</article>"
            )
        body = '<div class="plan-list">' + "".join(rows) + "</div>"
    return f"""
    <section class="panel">
      <h2>本次练度更新影响</h2>
      <p class="muted-line">delta 只基于 accepted roster，不包含 pending snapshot、rejected snapshot 或 catalog candidate。</p>
      <div class="links">
        {link("roster_delta.md", delta.get("output_md"))}
        {link("roster_delta.json", delta.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>新增角色</span><strong>{e(delta_summary.get("new_character_count", "N/A"))}</strong></div>
        <div><span>更新角色</span><strong>{e(delta_summary.get("updated_character_count", "N/A"))}</strong></div>
        <div><span>移除提示</span><strong>{e(delta_summary.get("removed_character_count", "N/A"))}</strong></div>
        <div><span>未变化角色</span><strong>{e(delta_summary.get("unchanged_character_count", "N/A"))}</strong></div>
        <div><span>队伍影响</span><strong>{e(delta_summary.get("team_impact_count", "N/A"))}</strong></div>
        <div><span>Tier 命中</span><strong>{e(delta_summary.get("tier_impact_count", "N/A"))}</strong></div>
      </div>
      {warning_block}
      {body}
    </section>
    """


def render_run_manifest(summary: dict[str, Any]) -> str:
    manifest = summary.get("run_manifest")
    if not isinstance(manifest, dict):
        return ""
    status = manifest.get("artifact_status") if isinstance(manifest.get("artifact_status"), dict) else {}
    inputs = manifest.get("inputs") if isinstance(manifest.get("inputs"), dict) else {}
    warnings = status.get("warnings") if isinstance(status.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Manifest Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    input_rows = []
    for name, item in inputs.items():
        if not isinstance(item, dict):
            input_rows.append(f"<li>{e(name)}: missing</li>")
            continue
        state = "ok" if item.get("exists") else "missing"
        digest = str(item.get("sha256") or "")
        input_rows.append(
            f"<li>{e(name)}: {e(rel_label(item.get('path')) or 'N/A')} · {e(digest[:12] or state)}</li>"
        )
    input_block = "<ul>" + "".join(input_rows) + "</ul>" if input_rows else "<p class=\"muted-line\">没有记录输入产物。</p>"
    stale = status.get("stale_or_mismatched") if isinstance(status.get("stale_or_mismatched"), list) else []
    missing = status.get("missing") if isinstance(status.get("missing"), list) else []
    error = manifest.get("error")
    error_block = ""
    if error:
        error_block = f'<div class="errors"><strong>Run manifest failed</strong><ul><li>{e(error)}</li></ul></div>'
    return f"""
    <section class="panel">
      <h2>运行一致性</h2>
      <p class="muted-line">用于确认 roster、targets、action/team cards、tier watchlist 和 roster delta 是否为同一批生成。当前包含历史 parsed 结果时，平均通过率不代表 P0.9 replay batch。</p>
      <div class="links">{link("run_manifest.json", manifest.get("output_json"))}</div>
      <div class="input-grid">
        <div><span>run_id</span><strong>{e(manifest.get("run_id") or "N/A")}</strong></div>
        <div><span>created_at</span><strong>{e(manifest.get("created_at") or "N/A")}</strong></div>
        <div><span>consistent</span><strong>{e(status.get("consistent"))}</strong></div>
        <div><span>missing</span><strong>{e(len(missing))}</strong></div>
        <div><span>stale/mismatched</span><strong>{e(len(stale))}</strong></div>
        <div><span>warnings</span><strong>{e(len(warnings))}</strong></div>
      </div>
      <div class="resource-plan">
        <h3>输入产物 hash</h3>
        {input_block}
      </div>
      {warning_block}
      {error_block}
    </section>
    """


def render_endgame_plan(summary: dict[str, Any]) -> str:
    plan = summary.get("endgame_plan")
    if not isinstance(plan, dict):
        return ""
    error = plan.get("error")
    plan_summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    target_plans = plan.get("target_plans") if isinstance(plan.get("target_plans"), list) else []
    warnings = plan.get("warnings") if isinstance(plan.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Plan Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if error:
        body = f'<div class="errors"><strong>Endgame plan failed</strong><ul><li>{e(error)}</li></ul></div>'
    elif not target_plans:
        body = '<div class="empty">没有生成本期高难方案。</div>'
    else:
        rows = []
        for item in target_plans[:8]:
            teams = item.get("team_candidates") if isinstance(item.get("team_candidates"), list) else []
            first_team = teams[0] if teams and isinstance(teams[0], dict) else {}
            members = first_team.get("members") if isinstance(first_team.get("members"), list) else []
            member_bits = []
            for member in members:
                if not isinstance(member, dict):
                    continue
                tier = member.get("tier") or "tier?"
                source_class = member.get("source_class") or "unknown"
                source_effective = member.get("source_class_effective") or source_class
                delta = member.get("delta_change_type") or "missing"
                member_bits.append(
                    f"{member.get('character')} [{source_class}->{source_effective}] · {tier}/{member.get('tier_entry_status') or 'missing'} · delta {delta}"
                )
            actions = item.get("next_actions") if isinstance(item.get("next_actions"), list) else []
            action_bits = "；".join(
                f"{action.get('action_type')}: {action.get('title') or action.get('character') or ''}".strip()
                for action in actions[:3]
                if isinstance(action, dict)
            )
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            artifact_hashes = evidence.get("input_artifact_hashes") if isinstance(evidence.get("input_artifact_hashes"), dict) else {}
            hash_bits = []
            for key, value in artifact_hashes.items():
                if isinstance(value, dict) and value.get("sha256_short"):
                    hash_bits.append(f"{key}:{value.get('sha256_short')}")
            warnings_text = "；".join(str(warning) for warning in item.get("warnings", []) if warning)
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">{e(item.get('plan_status'))}</div>"
                "<div>"
                f"<h3>{e(item.get('target'))}</h3>"
                f"<p>{e(item.get('recommended_line'))}</p>"
                f"<span>队伍：{e(first_team.get('team_title') or '无')} · {he(first_team.get('rank_reason') or 'N/A')}</span>"
                f"<span>成员：{e(' / '.join(member_bits) or '无')}</span>"
                f"<span>下一步：{he(action_bits or '无')}</span>"
                f"<span>证据：{e(evidence.get('target_source') or 'N/A')} · {e(evidence.get('target_hash') or 'hash?')} · {e(' / '.join(hash_bits) or '产物 hash 缺失')}</span>"
                f"<span>可信度：{e(human_status(item.get('plan_trust_level') or 'N/A'))} · 来源状态 {e(human_status(item.get('source_plan_status') or item.get('plan_status')))}</span>"
                f"<span>警告：{he(warnings_text or '无')}</span>"
                "</div>"
                f"<strong>{e(item.get('target_priority'))}<br>{e(first_team.get('team_status') or item.get('plan_status'))}</strong>"
                "</article>"
            )
        body = '<div class="plan-list">' + "".join(rows) + "</div>"
    return f"""
    <section class="panel">
      <h2>本期高难方案</h2>
      <p class="muted-line">这里只聚合已确认角色库、队伍卡、行动卡、角色库变化和本地保值观察；不是抽卡建议，也不是自动通关保证。</p>
      <div class="links">
        {link("endgame_plan.md", plan.get("output_md"))}
        {link("endgame_plan.json", plan.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>目标数</span><strong>{e(plan_summary.get("target_count", "N/A"))}</strong></div>
        <div><span>可直接尝试</span><strong>{e(plan_summary.get("ready_now_count", "N/A"))}</strong></div>
        <div><span>需先复核</span><strong>{e(plan_summary.get("needs_review_count", "N/A"))}</strong></div>
        <div><span>需补录</span><strong>{e(plan_summary.get("needs_recording_count", "N/A"))}</strong></div>
        <div><span>仅观察</span><strong>{e(plan_summary.get("watch_only_count", "N/A"))}</strong></div>
        <div><span>过期/未验证</span><strong>{e(plan_summary.get("stale_or_unverified_count", "N/A"))}</strong></div>
        <div><span>可信等级</span><strong>{e(human_status(plan.get("plan_trust_level", "N/A")))}</strong></div>
        <div><span>可信方案</span><strong>{e(plan_summary.get("trusted_plan_count", "N/A"))}</strong></div>
        <div><span>警告方案</span><strong>{e(plan_summary.get("warning_plan_count", "N/A"))}</strong></div>
        <div><span>阻断方案</span><strong>{e(plan_summary.get("blocked_plan_count", "N/A"))}</strong></div>
        <div><span>产物一致</span><strong>{e(bool_text(plan_summary.get("artifact_consistent")))}</strong></div>
      </div>
      {warning_block}
      {body}
    </section>
    """


def percent_label(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{round(float(value) * 100, 1)}%"
    return "N/A"


def render_tier_watchlist(summary: dict[str, Any]) -> str:
    watchlist = summary.get("tier_watchlist")
    if not isinstance(watchlist, dict):
        return ""
    error = watchlist.get("error")
    entries = watchlist.get("entries") if isinstance(watchlist.get("entries"), list) else []
    tier_summary = watchlist.get("summary") if isinstance(watchlist.get("summary"), dict) else {}
    warnings = watchlist.get("warnings") if isinstance(watchlist.get("warnings"), list) else []
    warning_html = "".join(f"<li>{e(item)}</li>" for item in warnings)
    warning_block = f'<div class="warnings"><strong>Tier Warning</strong><ul>{warning_html}</ul></div>' if warning_html else ""
    if error:
        body = f'<div class="errors"><strong>Tier watchlist failed</strong><ul><li>{e(error)}</li></ul></div>'
    elif not entries:
        body = '<div class="empty">没有 tier / 保值观察条目。</div>'
    else:
        rows = []
        for item in entries[:10]:
            owned_note = "已确认角色库" if item.get("owned_status") == "accepted_roster" else "候选 ≠ 已拥有"
            modes = "、".join(str(mode) for mode in item.get("modes", []) if mode) if isinstance(item.get("modes"), list) else ""
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            detail = (
                f"{owned_note} · tier {item.get('tier')} · 保值 {percent_label(item.get('retention_score'))} "
                f"· 使用 {percent_label(item.get('usage_rate'))} · {modes or '目标未标注'} "
                f"· {item.get('entry_status') or 'verified'} · {evidence.get('period') or 'period?'} · {evidence.get('content_sha256_short') or 'hash?'}"
            )
            rows.append(
                "<article class=\"plan-item\">"
                f"<div class=\"plan-rank\">{e(item.get('tier') or 'N/A')}</div>"
                "<div>"
                f"<h3>{e(item.get('character'))} · {e(item.get('observation_status') or item.get('recommendation'))}</h3>"
                f"<p>{e(item.get('reason'))}</p>"
                f"<span>{e(detail)}</span>"
                "</div>"
                f"<strong>{e(item.get('trend'))}<br>{e(item.get('owned_status'))}</strong>"
                "</article>"
            )
        body = '<div class="plan-list">' + "".join(rows) + "</div>"
    return f"""
    <section class="panel">
      <h2>Tier / 保值观察</h2>
      <p class="muted-line">本区只读取本地保值观察快照和已确认角色库；它不是联网爬取，也不是抽取建议。过期或未验证条目只能作为弱参考。</p>
      <div class="links">
        {link("tier_watchlist.md", watchlist.get("output_md"))}
        {link("tier_watchlist.json", watchlist.get("output_json"))}
      </div>
      <div class="input-grid">
        <div><span>条目数</span><strong>{e(tier_summary.get("entry_count", "N/A"))}</strong></div>
        <div><span>已确认命中</span><strong>{e(tier_summary.get("accepted_roster_count", "N/A"))}</strong></div>
        <div><span>已有高保值</span><strong>{e(tier_summary.get("owned_high_value_count", "N/A"))}</strong></div>
        <div><span>观察候选</span><strong>{e(tier_summary.get("watch_candidate_count", "N/A"))}</strong></div>
        <div><span>低保值已有</span><strong>{e(tier_summary.get("low_value_owned_count", "N/A"))}</strong></div>
        <div><span>已验证</span><strong>{e(tier_summary.get("verified_entry_count", "N/A"))}</strong></div>
        <div><span>已过期</span><strong>{e(tier_summary.get("stale_entry_count", "N/A"))}</strong></div>
        <div><span>未验证</span><strong>{e(tier_summary.get("unverified_entry_count", "N/A"))}</strong></div>
        <div><span>来源</span><strong>{e(tier_summary.get("source_name", "N/A"))}</strong></div>
      </div>
      {warning_block}
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
    freshness = refresh.get("freshness") if isinstance(refresh.get("freshness"), dict) else {}
    return f"""
    <section class="panel">
      <h2>终局目标刷新</h2>
      <div class="input-grid">
        <div><span>manifest</span><strong>{e(rel_label(refresh.get("manifest")) or "N/A")}</strong></div>
        <div><span>source type</span><strong>{e(refresh.get("source_type") or "N/A")}</strong></div>
        <div><span>game</span><strong>{e(refresh.get("game") or "N/A")}</strong></div>
        <div><span>sources</span><strong>{e(refresh.get("source_count", 0))}</strong></div>
        <div><span>targets</span><strong>{e(refresh.get("target_count", 0))}</strong></div>
        <div><span>freshness</span><strong>{e(freshness.get("level", "N/A"))}</strong></div>
        <div><span>stale sources</span><strong>{e(freshness.get("stale_source_count", "N/A"))}</strong></div>
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
    parse_counts = overall.get("parse_status_counts", {}) if isinstance(overall.get("parse_status_counts"), dict) else {}
    expected_counts = overall.get("expected_status_counts", {}) if isinstance(overall.get("expected_status_counts"), dict) else {}
    normalized_counts = overall.get("normalized_status_counts", {}) if isinstance(overall.get("normalized_status_counts"), dict) else {}
    import_counts = overall.get("import_status_counts", {}) if isinstance(overall.get("import_status_counts"), dict) else {}
    avg = overall.get("average_pass_rate")
    average_pass_rate = "N/A" if avg is None else f"{round(float(avg) * 100, 2)}%"
    conclusion = overall.get("conclusion") or ""
    input_info = summary.get("input", {}) if isinstance(summary.get("input"), dict) else {}
    plan_info = summary.get("training_plan", {}) if isinstance(summary.get("training_plan"), dict) else {}
    update_info = summary.get("update_state", {}) if isinstance(summary.get("update_state"), dict) else {}
    history_info = summary.get("snapshot_history", {}) if isinstance(summary.get("snapshot_history"), dict) else {}
    target_info = summary.get("target_refresh", {}) if isinstance(summary.get("target_refresh"), dict) else {}
    action_info = summary.get("action_cards", {}) if isinstance(summary.get("action_cards"), dict) else {}
    action_summary = action_info.get("summary", {}) if isinstance(action_info.get("summary"), dict) else {}
    team_info = summary.get("team_cards", {}) if isinstance(summary.get("team_cards"), dict) else {}
    team_summary = team_info.get("summary", {}) if isinstance(team_info.get("summary"), dict) else {}
    inbox_info = summary.get("review_inbox", {}) if isinstance(summary.get("review_inbox"), dict) else {}
    tier_info = summary.get("tier_watchlist", {}) if isinstance(summary.get("tier_watchlist"), dict) else {}
    tier_summary = tier_info.get("summary", {}) if isinstance(tier_info.get("summary"), dict) else {}
    delta_info = summary.get("roster_delta", {}) if isinstance(summary.get("roster_delta"), dict) else {}
    delta_summary = delta_info.get("summary", {}) if isinstance(delta_info.get("summary"), dict) else {}
    run_info = summary.get("run_manifest", {}) if isinstance(summary.get("run_manifest"), dict) else {}
    run_status = run_info.get("artifact_status", {}) if isinstance(run_info.get("artifact_status"), dict) else {}
    endgame_info = summary.get("endgame_plan", {}) if isinstance(summary.get("endgame_plan"), dict) else {}
    endgame_summary = endgame_info.get("summary", {}) if isinstance(endgame_info.get("summary"), dict) else {}
    final_info = summary.get("final_brief", {}) if isinstance(summary.get("final_brief"), dict) else {}
    checklist_info = summary.get("action_checklist", {}) if isinstance(summary.get("action_checklist"), dict) else {}
    preview_info = summary.get("review_decision_preview", {}) if isinstance(summary.get("review_decision_preview"), dict) else {}
    apply_info = summary.get("review_apply", {}) if isinstance(summary.get("review_apply"), dict) else {}
    apply_summary = apply_info.get("summary", {}) if isinstance(apply_info.get("summary"), dict) else {}
    doctor_info = summary.get("demo_doctor", {}) if isinstance(summary.get("demo_doctor"), dict) else {}
    update_command_info = summary.get("update_command", {}) if isinstance(summary.get("update_command"), dict) else {}
    launcher_info = summary.get("launcher_report", {}) if isinstance(summary.get("launcher_report"), dict) else {}
    refresh_info = summary.get("refresh_status", {}) if isinstance(summary.get("refresh_status"), dict) else {}
    refresh_summary = refresh_info.get("summary", {}) if isinstance(refresh_info.get("summary"), dict) else {}
    safe_apply = safe_apply_status(summary)
    metrics = [
        metric_card("演示状态", human_status(overall.get("demo_status") or "N/A"), status_class(overall.get("demo_status"))),
        metric_card("当前诊断", doctor_info.get("doctor_status", "N/A") if doctor_info else "N/A", status_class(doctor_info.get("doctor_status")) if doctor_info else "muted"),
        metric_card("本地更新命令", update_command_info.get("status", "N/A") if update_command_info else "N/A", status_class(update_command_info.get("status")) if update_command_info else "muted"),
        metric_card("诊断下一步", action_label(doctor_info.get("primary_next_action")) if doctor_info else "N/A", status_class(doctor_info.get("doctor_status")) if doctor_info else "muted"),
        metric_card(
            "诊断证据",
            doctor_info.get("evidence_check", {}).get("status", "N/A") if isinstance(doctor_info.get("evidence_check"), dict) else "N/A",
            status_class(doctor_info.get("evidence_check", {}).get("status")) if isinstance(doctor_info.get("evidence_check"), dict) else "muted",
        ),
        metric_card(
            "启动器",
            launcher_info.get("launcher_status", "N/A") if launcher_info else "N/A",
            status_class(launcher_info.get("launcher_status")) if launcher_info else "muted",
        ),
        metric_card("允许尝试", bool_text(doctor_info.get("try_now_allowed")) if doctor_info else "N/A", "ok" if doctor_info.get("try_now_allowed") else "bad" if doctor_info else "muted"),
        metric_card("刷新状态", refresh_info.get("refresh_status", "N/A") if refresh_info else "N/A", status_class(refresh_info.get("refresh_status")) if refresh_info else "muted"),
        metric_card("需要重跑", refresh_summary.get("needs_demo_refresh", "N/A") if refresh_summary else "N/A", "bad" if refresh_summary.get("needs_demo_refresh") else "muted"),
        metric_card("简报状态", final_info.get("brief_status", "N/A") if final_info else "N/A", status_class(final_info.get("brief_status")) if final_info else "muted"),
        metric_card("清单状态", checklist_info.get("checklist_status", "N/A") if checklist_info else "N/A", status_class(checklist_info.get("checklist_status")) if checklist_info else "muted"),
        metric_card("复核预览", preview_info.get("preview_status", "N/A") if preview_info else "N/A", status_class(preview_info.get("preview_status")) if preview_info else "muted"),
        metric_card("安全应用", safe_apply, status_class(safe_apply)),
        metric_card("已进角色库", apply_summary.get("did_enter_roster_count", "N/A") if apply_summary else "N/A", "ok" if apply_summary.get("did_enter_roster_count") else "muted"),
        metric_card("模式", input_info.get("source_mode") or "unknown", "muted"),
        metric_card("Case 数", overall.get("case_count", 0), "muted"),
        metric_card("Parsed 成功", overall.get("parse_success_count", 0), "ok"),
        metric_card("Parse PASS", parse_counts.get("PASS", 0), "ok"),
        metric_card("Parse FAIL", parse_counts.get("FAIL", 0), "bad"),
        metric_card("Expected PASS", expected_counts.get("PASS", 0), "ok"),
        metric_card("Expected FAIL", expected_counts.get("FAIL", 0), "bad"),
        metric_card("Expected N/A", expected_counts.get("N/A", 0), "warn"),
        metric_card("Normalized GENERATED", normalized_counts.get("GENERATED", overall.get("normalized_count", 0)), "ok"),
        metric_card("Import BLOCKED", import_counts.get("BLOCKED", 0), "bad"),
        metric_card("Import Review", import_counts.get("REQUIRES_REVIEW", 0), "warn"),
        metric_card("PASS", review_counts.get("PASS", 0), "ok"),
        metric_card("NEEDS_REVIEW", review_counts.get("NEEDS_REVIEW", 0), "warn"),
        metric_card("FAIL", review_counts.get("FAIL", 0), "bad"),
        metric_card("Expected 平均", average_pass_rate, "muted"),
        metric_card("Normalized", overall.get("normalized_count", 0), "ok"),
        metric_card("需人工确认", overall.get("requires_manual_review_count", 0), "warn"),
        metric_card("本轮处理图片", update_info.get("processed_image_count", "N/A") if update_info else "N/A", "ok" if update_info.get("processed_image_count") else "muted"),
        metric_card("历史变化", history_info.get("changed_character_count", "N/A") if history_info else "N/A", "warn" if history_info.get("changed_character_count") else "muted"),
        metric_card("终局目标", target_info.get("target_count", "N/A") if target_info else "N/A", "warn" if target_info.get("error") else "ok" if target_info else "muted"),
        metric_card("培养事项", plan_info.get("plan_item_count", 0) if plan_info else "N/A", "warn" if plan_info.get("error") else "ok" if plan_info else "muted"),
        metric_card("高优先级行动", action_summary.get("high_priority_action_count", "N/A") if action_summary else "N/A", "ok" if action_summary.get("high_priority_action_count") else "muted"),
        metric_card("需补录/确认", action_summary.get("needs_recording_count", "N/A") if action_summary else "N/A", "warn" if action_summary.get("needs_recording_count") else "muted"),
        metric_card("待确认快照", inbox_info.get("pending_count", "N/A") if inbox_info else "N/A", "warn" if inbox_info.get("pending_count") else "muted"),
        metric_card("已确认 Box", inbox_info.get("accepted_count", "N/A") if inbox_info else "N/A", "ok" if inbox_info.get("accepted_count") else "muted"),
        metric_card("已有高保值", tier_summary.get("owned_high_value_count", "N/A") if tier_summary else "N/A", "ok" if tier_summary.get("owned_high_value_count") else "muted"),
        metric_card("Tier 观察候选", tier_summary.get("watch_candidate_count", "N/A") if tier_summary else "N/A", "warn" if tier_summary.get("watch_candidate_count") else "muted"),
        metric_card("过期保值观察", tier_summary.get("stale_entry_count", "N/A") if tier_summary else "N/A", "warn" if tier_summary.get("stale_entry_count") else "muted"),
        metric_card("未验证保值观察", tier_summary.get("unverified_entry_count", "N/A") if tier_summary else "N/A", "warn" if tier_summary.get("unverified_entry_count") else "muted"),
        metric_card("本次新增", delta_summary.get("new_character_count", "N/A") if delta_summary else "N/A", "ok" if delta_summary.get("new_character_count") else "muted"),
        metric_card("本次更新", delta_summary.get("updated_character_count", "N/A") if delta_summary else "N/A", "warn" if delta_summary.get("updated_character_count") else "muted"),
        metric_card("更新影响队伍", delta_summary.get("team_impact_count", "N/A") if delta_summary else "N/A", "warn" if delta_summary.get("team_impact_count") else "muted"),
        metric_card("运行一致性", run_status.get("consistent", "N/A") if run_status else "N/A", "ok" if run_status.get("consistent") else "warn" if run_info else "muted"),
        metric_card("错批产物", len(run_status.get("stale_or_mismatched", [])) if run_status else "N/A", "bad" if run_status.get("stale_or_mismatched") else "ok" if run_info else "muted"),
        metric_card("方案 Trust", endgame_info.get("plan_trust_level", "N/A") if endgame_info else "N/A", status_class(endgame_info.get("plan_trust_level")) if endgame_info else "muted"),
        metric_card("高难方案目标", endgame_summary.get("target_count", "N/A") if endgame_summary else "N/A", "ok" if endgame_summary.get("target_count") else "muted"),
        metric_card("可直接尝试", endgame_summary.get("ready_now_count", "N/A") if endgame_summary else "N/A", "ok" if endgame_summary.get("ready_now_count") else "muted"),
        metric_card("先复核", endgame_summary.get("needs_review_count", "N/A") if endgame_summary else "N/A", "warn" if endgame_summary.get("needs_review_count") else "muted"),
        metric_card("需补录", endgame_summary.get("needs_recording_count", "N/A") if endgame_summary else "N/A", "warn" if endgame_summary.get("needs_recording_count") else "muted"),
        metric_card("仅观察", endgame_summary.get("watch_only_count", "N/A") if endgame_summary else "N/A", "warn" if endgame_summary.get("watch_only_count") else "muted"),
        metric_card("可用队伍", team_summary.get("playable_now_count", "N/A") if team_summary else "N/A", "ok" if team_summary.get("playable_now_count") else "muted"),
        metric_card("高保值可用队伍", team_summary.get("high_value_playable_team_count", "N/A") if team_summary else "N/A", "ok" if team_summary.get("high_value_playable_team_count") else "muted"),
        metric_card("需补录队伍", team_summary.get("needs_recording_count", "N/A") if team_summary else "N/A", "warn" if team_summary.get("needs_recording_count") else "muted"),
        metric_card("候选队伍", team_summary.get("catalog_candidate_count", "N/A") if team_summary else "N/A", "warn" if team_summary.get("catalog_candidate_count") else "muted"),
    ]
    demo_status = str(overall.get("demo_status") or "")
    doctor_status = str(doctor_info.get("doctor_status") or "") if doctor_info else ""
    can_act_now = (
        demo_status.lower() in {"ready", "pass", "ok"}
        and doctor_status.lower() in {"ready", "trusted", "ok", ""}
        and safe_apply not in {"blocked", "stale_after_apply"}
    )
    parse_fail_count = int(parse_counts.get("FAIL", 0) or 0)
    parse_pass_count = int(parse_counts.get("PASS", 0) or 0)
    expected_fail_count = int(expected_counts.get("FAIL", 0) or 0)
    manual_review_count = int(overall.get("requires_manual_review_count", 0) or 0)
    case_count = int(overall.get("case_count", 0) or 0)
    ready_count = int(endgame_summary.get("ready_now_count", 0) or 0) if endgame_summary else 0
    review_target_count = int(endgame_summary.get("needs_review_count", 0) or 0) if endgame_summary else 0
    if case_count == 0:
        status_title = "还没有本地数据"
        status_body = "当前没有可用分享图或 parsed JSON；先放入官方分享图，或使用已有 manifest/parsed replay。"
    elif parse_fail_count:
        status_title = "本轮识别失败"
        status_body = (
            f"有 {parse_fail_count} 张图没有成功解析。Dashboard 已生成用于诊断，"
            "但本轮结果不会进入练度建议；fresh/update 会返回非 0。"
        )
    elif expected_fail_count:
        status_title = "准确率验收未通过"
        status_body = f"有 {expected_fail_count} 个样例和 expected 不一致；先看 top failed fields，再改解析规则。"
    elif manual_review_count:
        status_title = "先人工确认"
        status_body = f"有 {manual_review_count} 个识别结果待确认；确认前不会进入本地角色库，也不会作为配队依据。"
    elif can_act_now:
        status_title = "可以按建议行动"
        status_body = "本轮数据已通过门禁，可以继续看下方建议。"
    else:
        status_title = "暂不能直接采用"
        status_body = "当前还有复核未完成、运行清单不一致或本地状态过期，先按下一步处理。"
    next_action = action_label(doctor_info.get("primary_next_action")) if doctor_info else "查看页面明细"
    top_cards = [
        summary_card("当前结论", status_title, status_body, "ok" if can_act_now else "bad"),
        summary_card("下一步", next_action, f"模式：{source_mode_label(input_info.get('source_mode'))}", status_class(doctor_status)),
        summary_card(
            "解析概况",
            f"{parse_pass_count}/{case_count} 张可用",
            f"解析失败 {parse_fail_count}，验收对照未通过 {expected_fail_count}，平均通过率 {average_pass_rate}。",
            "bad" if parse_fail_count or expected_fail_count else "ok",
        ),
        summary_card(
            "人工门禁",
            f"{manual_review_count} 个待确认",
            "即使识别成功，也必须人工确认后才会进入本地角色库。",
            "warn" if manual_review_count else "ok",
        ),
        summary_card(
            "高难建议",
            f"{ready_count} 个可尝试",
            f"{review_target_count} 个目标仍需先复核练度或队伍数据。",
            "ok" if ready_count and not review_target_count else "warn" if review_target_count else "muted",
        ),
        summary_card(
            "会不会重新识别",
            "默认不会",
            "只打开 Dashboard 看缓存不会跑 OCR；点“一键更新练度”才会处理官方分享图。",
            "ok",
        ),
        summary_card(
            "本地安全边界",
            "只进人工确认区",
            "不会登录账号、不会读取 token/cookie、不会自动写正式数据库。",
            "ok",
        ),
    ]
    operation_bar = render_operation_bar()
    acceptance_guide = render_acceptance_guide(
        can_act_now=can_act_now,
        input_info=input_info,
        run_info=run_info,
        run_status=run_status,
        final_info=final_info,
        doctor_info=doctor_info,
        parse_fail_count=parse_fail_count,
        expected_fail_count=expected_fail_count,
        manual_review_count=manual_review_count,
        case_count=case_count,
        average_pass_rate=average_pass_rate,
    )
    cards = "".join(render_case(case) for case in cases) or '<div class="empty">没有可展示的 case。</div>'
    steps = render_steps(summary.get("pipeline_steps", []))
    demo_doctor_panel = render_demo_doctor(summary)
    update_command_panel = render_update_command(summary)
    launcher_report_panel = render_launcher_report(summary)
    refresh_status_panel = render_refresh_status(summary)
    final_brief = render_final_brief(summary)
    action_checklist = render_action_checklist(summary)
    review_apply = render_review_apply(summary)
    input_panel = render_input_panel(summary)
    update_panel = render_update_state(summary)
    snapshot_history = render_snapshot_history(summary)
    target_refresh = render_target_refresh(summary)
    review_inbox = render_review_inbox(summary)
    run_manifest = render_run_manifest(summary)
    endgame_plan = render_endgame_plan(summary)
    roster_delta = render_roster_delta(summary)
    tier_watchlist = render_tier_watchlist(summary)
    training_plan = render_training_plan(summary)
    action_cards = render_action_cards(summary)
    team_cards = render_team_cards(summary)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>米游社练度识别体验台</title>
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
    header > * {{ max-width: 1440px; margin-left: auto; margin-right: auto; }}
    header h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #cbd5e1; max-width: 980px; }}
    header p + p {{ margin-top: 6px; }}
    main {{ width: min(100%, 1440px); margin: 0 auto; padding: 22px; display: grid; gap: 18px; }}
    .operation-bar {{ display: grid; grid-template-columns: minmax(260px, 0.75fr) minmax(520px, 1.8fr); gap: 16px; align-items: stretch; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; box-shadow: var(--shadow); }}
    .operation-bar > div:first-child {{ display: grid; align-content: center; gap: 8px; min-width: 0; }}
    .operation-bar span {{ color: var(--muted); font-size: 13px; font-weight: 800; }}
    .operation-bar h2 {{ margin: 0; font-size: 28px; line-height: 1.15; letter-spacing: 0; }}
    .operation-bar p {{ margin: 0; color: var(--muted); line-height: 1.55; }}
    .operation-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }}
    .operation-card {{ display: grid; gap: 8px; align-content: start; min-width: 0; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #ffffff; }}
    .operation-card strong {{ font-size: 16px; overflow-wrap: anywhere; }}
    .operation-card p {{ color: var(--muted); font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }}
    .operation-card code {{ display: block; width: 100%; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-wrap: anywhere; white-space: normal; }}
    .operation-card.primary {{ border-color: #bfdbfe; background: #eff6ff; }}
    .operation-card.primary strong {{ color: #1d4ed8; }}
    .operation-card.safe {{ border-color: #a7e0bd; background: var(--ok-bg); }}
    .operation-card.safe strong {{ color: var(--ok); }}
    .operation-card.warn {{ border-color: #f6cf7c; background: var(--warn-bg); }}
    .operation-card.warn strong {{ color: var(--warn); }}
    .top-summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .summary-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); min-width: 0; }}
    .summary-card span {{ display: block; color: var(--muted); font-size: 13px; }}
    .summary-card strong {{ display: block; margin-top: 6px; font-size: 22px; line-height: 1.25; overflow-wrap: anywhere; }}
    .summary-card p {{ margin: 8px 0 0; color: var(--muted); font-size: 13px; line-height: 1.45; overflow-wrap: anywhere; }}
    .summary-card.ok strong {{ color: var(--ok); }} .summary-card.warn strong {{ color: var(--warn); }} .summary-card.bad strong {{ color: var(--bad); }}
    .acceptance-guide {{ display: grid; grid-template-columns: minmax(280px, 0.9fr) minmax(420px, 1.6fr); gap: 16px; align-items: stretch; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; box-shadow: var(--shadow); }}
    .acceptance-guide > div:first-child {{ display: grid; align-content: center; gap: 8px; min-width: 0; }}
    .acceptance-guide span {{ color: var(--muted); font-size: 13px; font-weight: 800; }}
    .acceptance-guide h2 {{ margin: 0; font-size: 28px; line-height: 1.15; letter-spacing: 0; }}
    .acceptance-guide p {{ margin: 0; color: var(--muted); line-height: 1.55; }}
    .acceptance-guide em {{ color: var(--muted); font-style: normal; font-size: 13px; overflow-wrap: anywhere; }}
    .acceptance-guide.ok {{ border-color: #a7e0bd; background: linear-gradient(180deg, #ffffff 0%, #f3fbf6 100%); }}
    .acceptance-guide.warn {{ border-color: #f6cf7c; background: linear-gradient(180deg, #ffffff 0%, #fff9e8 100%); }}
    .acceptance-guide.bad {{ border-color: #ffc0ba; background: linear-gradient(180deg, #ffffff 0%, #fff1ef 100%); }}
    .acceptance-guide.ok h2 {{ color: var(--ok); }} .acceptance-guide.warn h2 {{ color: var(--warn); }} .acceptance-guide.bad h2 {{ color: var(--bad); }}
    .guide-cards {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .guide-card {{ display: grid; gap: 7px; align-content: start; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: rgba(255, 255, 255, 0.76); min-width: 0; }}
    .guide-card strong {{ font-size: 16px; overflow-wrap: anywhere; }}
    .guide-card p {{ font-size: 13px; }}
    .guide-card code {{ display: block; width: 100%; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-wrap: anywhere; white-space: normal; }}
    .guide-card.ok strong {{ color: var(--ok); }} .guide-card.warn strong {{ color: var(--warn); }} .guide-card.bad strong {{ color: var(--bad); }}
    .debug-drawer {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); }}
    .debug-drawer > summary {{ font-size: 16px; }}
    .debug-content {{ display: grid; gap: 18px; margin-top: 14px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 24px; }}
    .metric.ok strong {{ color: var(--ok); }} .metric.warn strong {{ color: var(--warn); }} .metric.bad strong {{ color: var(--bad); }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); }}
    .panel h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .steps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
    .input-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    .input-grid div {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px; min-width: 0; }}
    .input-grid span {{ display: block; color: var(--muted); font-size: 12px; }}
    .input-grid strong {{ display: block; overflow-wrap: anywhere; }}
    .warnings {{ margin-top: 12px; border: 1px solid #f6cf7c; background: var(--warn-bg); color: var(--warn); border-radius: 8px; padding: 10px; }}
    .warnings ul {{ margin: 6px 0 0; padding-left: 20px; }}
    .step {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; display: grid; gap: 6px; min-width: 0; }}
    .step strong {{ font-size: 14px; }} .step em {{ font-style: normal; color: var(--muted); font-size: 12px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--muted); }}
    .ok .dot, .badge.ok {{ background: var(--ok); color: #fff; }} .warn .dot, .badge.warn {{ background: var(--warn); color: #fff; }} .bad .dot, .badge.bad {{ background: var(--bad); color: #fff; }}
    .case-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }}
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
    .brief-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .brief-overview {{ margin: 12px 0; border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #f8fbff; }}
    .brief-overview span {{ display: block; color: var(--muted); font-size: 12px; }}
    .brief-overview strong {{ display: block; margin-top: 4px; font-size: 22px; line-height: 1.25; }}
    .brief-overview p {{ margin: 8px 0 0; color: var(--muted); line-height: 1.5; }}
    .brief-overview.ok {{ border-color: #a7e0bd; background: var(--ok-bg); }}
    .brief-overview.warn {{ border-color: #f6cf7c; background: var(--warn-bg); }}
    .brief-overview.bad {{ border-color: #ffc0ba; background: var(--bad-bg); }}
    .brief-overview.ok strong {{ color: var(--ok); }}
    .brief-overview.warn strong {{ color: var(--warn); }}
    .brief-overview.bad strong {{ color: var(--bad); }}
    .brief-flow {{ margin: 12px 0; border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #ffffff; }}
    .brief-flow h3 {{ margin: 0 0 10px; font-size: 15px; }}
    .brief-flow > div {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .brief-flow-step {{ display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 8px; align-items: start; border: 1px solid var(--line); border-radius: 8px; padding: 10px; background: #fbfcff; min-width: 0; }}
    .brief-flow-step b {{ display: grid; place-items: center; width: 28px; height: 28px; border-radius: 999px; background: #e9f8ef; color: var(--ok); }}
    .brief-flow-step strong {{ display: block; overflow-wrap: anywhere; }}
    .brief-flow-step span {{ display: block; color: var(--muted); font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }}
    .brief-next-step {{ margin: 12px 0; border: 1px solid #bfdbfe; border-radius: 8px; padding: 14px; background: #eff6ff; }}
    .brief-next-step span {{ display: block; color: #1d4ed8; font-size: 12px; font-weight: 800; }}
    .brief-next-step strong {{ display: block; margin-top: 4px; font-size: 24px; color: #1d4ed8; line-height: 1.2; }}
    .brief-next-step p {{ margin: 8px 0 0; line-height: 1.45; }}
    .brief-next-step em {{ display: block; margin-top: 6px; color: var(--muted); font-style: normal; font-size: 13px; overflow-wrap: anywhere; }}
    .plan-item {{ display: grid; grid-template-columns: 54px minmax(0, 1fr) 72px; gap: 12px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .brief-card {{ display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 12px; align-items: start; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcff; }}
    .brief-main {{ display: grid; gap: 6px; min-width: 0; }}
    .brief-card-head {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }}
    .brief-card h3 {{ margin: 0 0 4px; font-size: 16px; }}
    .brief-card p {{ margin: 0 0 4px; color: var(--text); }}
    .brief-card span {{ display: block; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .brief-action {{ display: inline-flex; width: fit-content; max-width: 100%; color: var(--warn); overflow-wrap: anywhere; font-size: 13px; line-height: 1.35; border: 1px solid #f6cf7c; background: var(--warn-bg); border-radius: 8px; padding: 7px 9px; font-weight: 800; }}
    .brief-links {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
    .brief-details {{ margin-top: 10px; border-top: 1px solid var(--line); padding-top: 10px; }}
    .detail-hint {{ display: grid; gap: 3px; margin: 8px 0; padding: 8px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    .detail-hint strong {{ color: var(--text); }}
    .detail-hint span {{ font-size: 13px; color: var(--muted); }}
    .command-details {{ margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }}
    .soft-details {{ margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }}
    .soft-details .input-grid {{ margin-top: 10px; }}
    .brief-evidence {{ margin: 8px 0; padding: 0; display: grid; gap: 6px; list-style: none; }}
    .brief-evidence li {{ display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 8px; }}
    .brief-evidence strong {{ color: var(--text); }}
    .final-brief .brief-list {{ grid-template-columns: 1fr; align-items: start; }}
    .final-brief .brief-card {{ grid-template-columns: 1fr; }}
    .final-brief .plan-rank {{ width: fit-content; height: auto; min-height: 0; padding: 5px 9px; border-radius: 999px; }}
    .more-brief-cards {{ margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }}
    .more-brief-cards ul {{ margin: 10px 0 0; padding: 0; list-style: none; display: grid; gap: 8px; }}
    .more-brief-cards li {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
    .more-brief-cards strong {{ overflow-wrap: anywhere; }}
    .more-brief-cards span {{ color: var(--warn); font-weight: 800; }}
    .badge.muted {{ background: #e2e8f0; color: #334155; }}
    .plan-rank {{ display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; background: #e9f8ef; color: var(--ok); font-weight: 900; }}
    .plan-item h3 {{ margin: 0 0 4px; font-size: 16px; }}
    .plan-item p {{ margin: 0 0 4px; color: var(--text); }}
    .plan-item span {{ color: var(--muted); font-size: 12px; }}
    .plan-item > strong {{ color: var(--warn); text-align: right; }}
    .resource-plan {{ margin-top: 12px; display: grid; gap: 10px; }}
    .resource-plan h3 {{ margin: 0; font-size: 15px; }}
    .resource-list {{ display: grid; gap: 8px; }}
    .muted-line {{ margin: 0; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .resource-item {{ display: grid; grid-template-columns: 150px minmax(0, 1fr) 64px; gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
    .resource-item span {{ color: var(--muted); overflow-wrap: anywhere; }}
    .resource-item em {{ font-style: normal; color: var(--warn); font-weight: 900; text-align: right; }}
    .command-block {{ margin: 6px 0 0; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-wrap: anywhere; white-space: pre-wrap; max-height: 220px; overflow: auto; }}
    .history-list {{ display: grid; gap: 10px; margin-top: 12px; }}
    .history-item {{ display: grid; grid-template-columns: minmax(120px, 1fr) 90px 90px minmax(220px, 2fr); gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .history-item span {{ display: block; color: var(--muted); font-size: 12px; }}
    .history-item strong {{ overflow-wrap: anywhere; }}
    .empty {{ padding: 24px; color: var(--muted); background: var(--panel); border: 1px dashed var(--line); border-radius: 8px; }}
    @media (max-width: 900px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .operation-bar {{ grid-template-columns: 1fr; }}
      .acceptance-guide {{ grid-template-columns: 1fr; }}
      .guide-cards {{ grid-template-columns: 1fr; }}
      .top-summary {{ grid-template-columns: 1fr; }}
      .steps {{ grid-template-columns: 1fr; }}
      .input-grid {{ grid-template-columns: 1fr; }}
      .case-grid {{ grid-template-columns: 1fr; }}
      .case-card {{ grid-template-columns: 1fr; }}
      .facts {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .plan-item {{ grid-template-columns: 1fr; }}
      .brief-flow > div {{ grid-template-columns: 1fr; }}
      .brief-card {{ grid-template-columns: 1fr; }}
      .resource-item {{ grid-template-columns: 1fr; }}
      .history-item {{ grid-template-columns: 1fr; }}
      .plan-item > strong {{ text-align: left; }}
      .brief-action {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>米游社练度识别体验台</h1>
    <p>{he(conclusion)}</p>
    <p>当前仍是本地演示流程。即使解析通过，也只进入人工确认区，不会自动写入正式数据。</p>
  </header>
    <main>
    {operation_bar}
    {acceptance_guide}
    <section class="top-summary">{''.join(top_cards)}</section>
    {final_brief}
    {action_checklist}
    {endgame_plan}
    {tier_watchlist}
    {action_cards}
    {team_cards}
    {training_plan}
    <section class="panel"><h2>Case 卡片</h2><div class="case-grid">{cards}</div></section>
    <details class="debug-drawer">
      <summary>调试与产物明细</summary>
      <div class="debug-content">
        <section class="metrics">{''.join(metrics)}</section>
        {demo_doctor_panel}
        {update_command_panel}
        {launcher_report_panel}
        {refresh_status_panel}
        {review_apply}
        {input_panel}
        {update_panel}
        {steps}
        {target_refresh}
        {snapshot_history}
        {review_inbox}
        {run_manifest}
        {roster_delta}
      </div>
    </details>
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
