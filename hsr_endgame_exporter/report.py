from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import MODE_CN


def write_report(
    path: Path,
    *,
    from_date: str,
    to_date: str,
    repo_id: str,
    modes: list[str],
    tables: dict[str, list[dict[str, Any]]],
    warnings: list[str],
    errors: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    phase_rows = tables.get("phase_index", [])
    character_rows = tables.get("character_usage_long", [])
    team_raw_rows = tables.get("team_rank_raw", [])
    ordered_rows = tables.get("team_rank_dedup_ordered", [])
    unordered_rows = tables.get("team_rank_dedup_unordered", [])
    unresolved_rows = tables.get("name_map_unresolved", [])
    name_rows = tables.get("name_map", [])
    tier_rows = tables.get("prydwen_tier_current", [])
    tier_history_rows = tables.get("prydwen_tier_history", [])
    tier_changelog_rows = tables.get("prydwen_tier_changelog", [])
    tier_trend_rows = tables.get("prydwen_tier_usage_trend", [])
    tier_chart_rows = tables.get("prydwen_tier_charts", [])

    phase_counts = Counter(row.get("mode") for row in phase_rows)
    aa_sub_modes = {row.get("sub_mode") for row in character_rows if row.get("mode") == "aa"}
    aa_split = bool({"knights", "king_piece"} & aa_sub_modes)

    lines = [
        "# HSR Endgame Export Report",
        "",
        f"- 导出时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- from_date / to_date: {from_date} / {to_date}",
        f"- 数据源: Hugging Face dataset `{repo_id}`; Prydwen visible page data when available",
        f"- 成功读取的 snapshot 数: {len({row.get('snapshot_id') for row in phase_rows})}",
        "",
        "## 各模式 snapshot 覆盖情况",
        "",
    ]
    for mode in modes:
        lines.append(f"- {MODE_CN.get(mode, mode)} ({mode}): {phase_counts.get(mode, 0)}")
    lines.extend(
        [
            "",
            "## 表行数",
            "",
            f"- 角色表行数: {len(character_rows)}",
            f"- 队伍 raw 行数: {len(team_raw_rows)}",
            f"- 队伍有序去重后行数: {len(ordered_rows)}",
            f"- 队伍无序去重后行数: {len(unordered_rows)}",
            f"- raw -> 无序去重移除重复行数: {len(team_raw_rows) - len(unordered_rows)}",
            f"- 未解析角色数量: {len(unresolved_rows)}",
            f"- 官方中文名补全数量: {sum(1 for row in name_rows if row.get('needs_manual_check') in {'0', 0})}",
            "- 简洁视图: `overview.csv`, `latest_usage_cn.csv`, `top_teams_latest.csv`（四人无序去重，每模式 Top 100），Excel 同名 sheet",
            f"- Prydwen 当前 T 榜行数: {len(tier_rows)}",
            f"- Prydwen T 榜本地历史行数: {len(tier_history_rows)}",
            f"- Prydwen changelog 日期段数: {len(tier_changelog_rows)}",
            f"- T0-T2 出场率趋势行数: {len(tier_trend_rows)}",
            f"- T0-T2 趋势图数量: {len(tier_chart_rows)}",
            "- 交互可视化入口: `visualizer/index.html`（含异相仲裁本地趋势与本地 Box 维护页）",
            "",
            "## 异相仲裁拆分情况",
            "",
        ]
    )
    if aa_split:
        lines.append("- 已取得可识别的骑士关卡 / 王棋关卡拆分数据。")
    else:
        lines.append("- 本次未取得骑士关卡 / 王棋关卡角色出场率拆分数据。")
        if "aa" in modes:
            lines.append("- AA 数据已按 `all_bosses` / `全 Boss / 未拆分` 标记。")

    lines.extend(["", "## Warning 列表", ""])
    lines.extend([f"- {item}" for item in warnings] or ["- 无"])
    lines.extend(["", "## Error 列表", ""])
    lines.extend([f"- {item}" for item in errors] or ["- 无"])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
