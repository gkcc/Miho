from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from miho_core.box import load_box
from miho_core.decision import build_decision_cards, load_rules


def run_decision_report(box_path: str | Path, out_dir: str | Path, rules_path: str | Path | None = None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    box = load_box(box_path)
    rules = load_rules(rules_path)
    result = build_decision_cards(out, box, rules)
    (out / "decision_cards.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "decision_report.md").write_text(format_report(result), encoding="utf-8")
    return result


def format_report(result: dict) -> str:
    summary = result.get("summary") or {}
    cards = result.get("cards") or []
    lines = [
        "# 绝区零 Box 抽取决策报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 已识别拥有角色：{summary.get('owned_agents', 0)}",
        f"- 候选角色数：{summary.get('candidate_count', 0)}",
        f"- 决策分布：{_decision_counts(summary.get('decision_counts') or {})}",
        f"- 数据行：T榜 {summary.get('data_rows', {}).get('tier_current', 0)} / 出场 {summary.get('data_rows', {}).get('usage', 0)} / 队伍 {summary.get('data_rows', {}).get('teams', 0)}",
        "",
        "## 怎么看",
        "",
        "- `抽`：当前数据和你的 Box 都支持优先拿到目标档位。",
        "- `不抽`：评级、出场、替代收益或账号需求不足。",
        "- `等实测`：新角色、卫星或本地高难样本不足，不建议只凭预期下结论。",
        "- `停止加仓`：已经拥有或已达到第一版建议档位，后续优先补练度或等环境变化。",
        "- 档位比较是占位框架：目前只比较 0+0 / 0+1 / 1+1 / 2+1 的投入顺序，不等同于真实命座收益曲线。",
        "",
        "## 候选角色",
        "",
    ]
    if not cards:
        lines.append("- 暂无候选角色。请检查 `prydwen_tier_current.csv` 或在规则文件里维护 `candidates`。")
        return "\n".join(lines) + "\n"
    for card in cards:
        lines.extend(_card_lines(card))
    return "\n".join(lines) + "\n"


def _card_lines(card: dict) -> list[str]:
    tier = card.get("tier_summary") or {}
    history = card.get("history_summary") or {}
    release = card.get("release_risk") or {}
    replacement = card.get("replacement_risk") or {}
    investment = card.get("investment") or {}
    lines = [
        f"### {card.get('name_cn') or card.get('slug')}：{card.get('decision')}",
        "",
        f"- 识别：{'已拥有' if card.get('owned') else '未拥有'}；当前档位：{card.get('current_stage')}",
        f"- 定位：{tier.get('role_group_cn') or '-'} / {tier.get('element_cn') or '-'} / {tier.get('style_cn') or '-'}；最好评级：{tier.get('best_tier') or '-'}",
        f"- 依据：{'；'.join(card.get('decision_reasons') or ['-'])}",
        f"- 历史表现：{_history_text(history)}",
        f"- 新/卫星风险：{release.get('level', '-')}，{release.get('reason', '-')}",
        f"- 替代风险：{replacement.get('level', '-')}，{replacement.get('reason', '-')}",
        f"- 练度：{investment.get('status', '-')}；{_list_text(investment.get('warnings') or [])}",
    ]
    warnings = card.get("warnings") or []
    if warnings:
        lines.append(f"- 高亮提醒：{_list_text(warnings)}")
    replacements = replacement.get("replacements") or []
    if replacements:
        text = "、".join(f"{item.get('name_cn')}({item.get('tier') or '-'})" for item in replacements[:3])
        lines.append(f"- Box 替代：{text}")
    lines.append("- 档位占位：" + "；".join(f"{row.get('stage')} {row.get('value')}({row.get('advice')})" for row in card.get("stage_comparison", [])))
    if card.get("notes"):
        lines.append(f"- 备注：{card.get('notes')}")
    lines.append("")
    return lines


def _decision_counts(counts: dict) -> str:
    return " / ".join(f"{key} {value}" for key, value in counts.items()) if counts else "-"


def _history_text(history: dict) -> str:
    modes = history.get("modes") or {}
    if not modes:
        return "暂无本地高难出场历史"
    parts = []
    for mode in modes.values():
        parts.append(
            f"{mode.get('mode_cn')} 最近{mode.get('latest_app_rate')}%，近三期均值{mode.get('avg_last3_app_rate')}%，趋势{mode.get('trend_delta')}"
        )
    if history.get("team_appearances"):
        parts.append(f"入榜队伍 {history.get('team_appearances')} 条，最好 rank {history.get('best_team_rank') or '-'}")
    return "；".join(parts)


def _list_text(items: list[str]) -> str:
    return "；".join(str(item) for item in items) if items else "无"
