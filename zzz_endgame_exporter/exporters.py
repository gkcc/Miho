from __future__ import annotations

import csv
import importlib.util
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id

from .constants import (
    CHANGELOG_COLUMNS,
    CHARACTER_USAGE_COLUMNS,
    NAME_MAP_COLUMNS,
    PHASE_COLUMNS,
    PRYDWEN_TIER_COLUMNS,
    TEAM_RAW_COLUMNS,
)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in columns})


def latest_usage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("mode", "")),
            str(row.get("sub_mode", "")),
            str(row.get("phase_ver", "")),
            str(row.get("character_slug", "")),
        )
        current = chosen.get(key)
        if current is None or str(row.get("collect_date", "")) >= str(current.get("collect_date", "")):
            chosen[key] = row
    return sorted(chosen.values(), key=lambda r: (str(r.get("mode", "")), str(r.get("sub_mode", "")), str(r.get("character_slug", ""))))


def dedup_teams(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        chars = [row.get("char_1_slug"), row.get("char_2_slug"), row.get("char_3_slug")]
        bangboo = normalize_character_id(row.get("bangboo_slug"))
        signature = "|".join(
            [
                str(row.get("mode", "")),
                str(row.get("sub_mode", "")),
                str(row.get("phase_ver", "")),
                ">".join(sorted(normalize_character_id(x) for x in chars if x)),
                f"bangboo:{bangboo}" if bangboo else "bangboo:",
            ]
        )
        groups[signature].append(row)
    output: list[dict[str, Any]] = []
    for group in groups.values():
        output.append(sorted(group, key=_team_sort_key)[0])
    return sorted(output, key=lambda r: (str(r.get("mode", "")), str(r.get("sub_mode", "")), _team_sort_key(r)))


def build_name_rows(
    slugs: set[str],
    official: dict[str, dict[str, str]],
    tier_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tier_by_slug = {normalize_character_id(row.get("character_slug")): row for row in tier_rows}
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for slug in sorted(slugs):
        official_row = official.get(slug)
        tier = tier_by_slug.get(slug, {})
        row = {
            "character_slug": slug,
            "character_name_en": official_row.get("character_name_en") if official_row else tier.get("character_name_en", ""),
            "character_name_cn": official_row.get("character_name_cn") if official_row else "",
            "source": official_row.get("source") if official_row else "Prydwen/HF slug",
            "needs_manual_check": "0" if official_row and official_row.get("character_name_cn") else "1",
            "aliases": official_row.get("aliases", "") if official_row else "",
            "kind": official_row.get("kind", "agent") if official_row else "unknown",
            "release_order": official_row.get("release_order", "9999") if official_row else "9999",
        }
        rows.append(row)
        if row["needs_manual_check"] == "1":
            unresolved.append(row)
    return rows, unresolved


def enrich_names(
    rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
) -> None:
    names = {normalize_character_id(row.get("character_slug")): row for row in name_rows}
    tier = {normalize_character_id(row.get("character_slug")): row for row in tier_rows}
    for row in rows:
        slug = normalize_character_id(row.get("character_slug") or row.get("char_1_slug"))
        if "character_slug" in row:
            _apply_character_name(row, slug, names, tier)
        for index in range(1, 4):
            cslug = normalize_character_id(row.get(f"char_{index}_slug"))
            if cslug:
                row[f"char_{index}_name_cn"] = names.get(cslug, {}).get("character_name_cn", "")
        bslug = normalize_character_id(row.get("bangboo_slug"))
        if bslug:
            row["bangboo_name_cn"] = names.get(bslug, {}).get("character_name_cn", "")


def build_tier_usage_trend(tier_rows: list[dict[str, Any]], usage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usage_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in usage_rows:
        if row.get("sub_mode") != "all":
            continue
        usage_by_key[(str(row.get("mode", "")), str(row.get("character_slug", "")))].append(row)
    output: list[dict[str, Any]] = []
    for tier in tier_rows:
        key = (str(tier.get("tier_mode", "")), str(tier.get("character_slug", "")))
        for usage in sorted(usage_by_key.get(key, []), key=lambda r: str(r.get("collect_date", ""))):
            output.append(
                {
                    **tier,
                    "collect_date": usage.get("collect_date", ""),
                    "phase_ver": usage.get("phase_ver", ""),
                    "phase_name": usage.get("phase_name", ""),
                    "app_rate": usage.get("app_rate", ""),
                    "avg_score": usage.get("avg_score", ""),
                    "quality_flag": usage.get("quality_flag", ""),
                }
            )
    return output


def write_outputs(
    out_dir: Path,
    *,
    phase_rows: list[dict[str, Any]],
    usage_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    tier_history_rows: list[dict[str, Any]],
    changelog_rows: list[dict[str, Any]],
    changelog_history_rows: list[dict[str, Any]],
    trend_rows: list[dict[str, Any]],
    from_date: str = "",
    to_date: str = "",
    repo_id: str = "",
    modes: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> None:
    latest_rows = latest_usage(usage_rows)
    dedup_rows = dedup_teams(team_rows)
    trend_columns = list(dict.fromkeys(PRYDWEN_TIER_COLUMNS + ["collect_date", "phase_ver", "phase_name", "app_rate", "avg_score", "quality_flag"]))
    tables = {
        "phase_index": phase_rows,
        "character_usage_long": usage_rows,
        "character_usage_phase_latest": latest_rows,
        "team_rank_raw": team_rows,
        "team_rank_dedup_unordered": dedup_rows,
        "name_map": name_rows,
        "name_map_unresolved": unresolved_rows,
        "prydwen_tier_current": tier_rows,
        "prydwen_tier_history": tier_history_rows,
        "prydwen_tier_changelog": changelog_rows,
        "prydwen_tier_changelog_history": changelog_history_rows,
        "prydwen_tier_usage_trend": trend_rows,
    }
    write_csv(out_dir / "phase_index.csv", phase_rows, PHASE_COLUMNS)
    write_csv(out_dir / "character_usage_long.csv", usage_rows, CHARACTER_USAGE_COLUMNS)
    write_csv(out_dir / "character_usage_phase_latest.csv", latest_rows, CHARACTER_USAGE_COLUMNS)
    write_csv(out_dir / "team_rank_raw.csv", team_rows, TEAM_RAW_COLUMNS)
    write_csv(out_dir / "team_rank_dedup_unordered.csv", dedup_rows, TEAM_RAW_COLUMNS)
    write_csv(out_dir / "name_map.csv", name_rows, NAME_MAP_COLUMNS)
    write_csv(out_dir / "name_map_unresolved.csv", unresolved_rows, NAME_MAP_COLUMNS)
    write_csv(out_dir / "prydwen_tier_current.csv", tier_rows, PRYDWEN_TIER_COLUMNS)
    write_csv(out_dir / "prydwen_tier_history.csv", tier_history_rows, PRYDWEN_TIER_COLUMNS)
    write_csv(out_dir / "prydwen_tier_changelog.csv", changelog_rows, CHANGELOG_COLUMNS)
    write_csv(out_dir / "prydwen_tier_changelog_history.csv", changelog_history_rows, CHANGELOG_COLUMNS)
    write_csv(out_dir / "prydwen_tier_usage_trend.csv", trend_rows, trend_columns)
    write_excel_if_available(out_dir / "zzz_endgame_dataset.xlsx", tables, warnings or [])
    write_report(
        out_dir / "export_report.md",
        phase_rows,
        usage_rows,
        team_rows,
        unresolved_rows,
        from_date=from_date,
        to_date=to_date,
        repo_id=repo_id,
        modes=modes or [],
        tier_rows=tier_rows,
        tier_history_rows=tier_history_rows,
        changelog_rows=changelog_rows,
        trend_rows=trend_rows,
        warnings=warnings or [],
        errors=errors or [],
    )


def write_report(
    path: Path,
    phase_rows: list[dict[str, Any]],
    usage_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    *,
    from_date: str = "",
    to_date: str = "",
    repo_id: str = "",
    modes: list[str] | None = None,
    tier_rows: list[dict[str, Any]] | None = None,
    tier_history_rows: list[dict[str, Any]] | None = None,
    changelog_rows: list[dict[str, Any]] | None = None,
    trend_rows: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> None:
    modes = modes or []
    warnings = warnings or []
    errors = errors or []
    path.write_text(
        "\n".join(
            [
                "# 绝区零高难数据导出报告",
                "",
                f"- 导出时间：{datetime.now().isoformat(timespec='seconds')}",
                f"- from_date / to_date：{from_date or '-'} / {to_date or '-'}",
                f"- 数据源：Hugging Face dataset `{repo_id or 'LvlUrArti/ShiyuDataProcessed'}` + Prydwen ZZZ + HoYoWiki 官方代理人/邦布列表",
                f"- 模式：{', '.join(modes) if modes else 'sd, da'}",
                f"- 期数行数：{len(phase_rows)}",
                f"- 成功读取 snapshot 数：{len({row.get('snapshot_id') for row in phase_rows})}",
                f"- 角色出场率行数：{len(usage_rows)}",
                f"- 队伍 raw 行数：{len(team_rows)}",
                f"- 队伍无序去重后行数：{len(dedup_teams(team_rows))}",
                f"- 待人工确认名称：{len(unresolved_rows)}",
                f"- Prydwen 当前 T 榜行数：{len(tier_rows or [])}",
                f"- Prydwen T 榜本地历史行数：{len(tier_history_rows or [])}",
                f"- Prydwen changelog 行数：{len(changelog_rows or [])}",
                f"- T 榜角色出场趋势行数：{len(trend_rows or [])}",
                "- 可视化入口：`visualizer/index.html`",
                "",
                "## Warning 列表",
                "",
                *([f"- {item}" for item in warnings] or ["- 无"]),
                "",
                "## Error 列表",
                "",
                *([f"- {item}" for item in errors] or ["- 无"]),
            ]
        ),
        encoding="utf-8",
    )


def write_excel_if_available(
    path: Path,
    tables: dict[str, list[dict[str, Any]]],
    warnings: list[str],
) -> None:
    if not importlib.util.find_spec("pandas") or not importlib.util.find_spec("openpyxl"):
        warnings.append("XLSX skipped because pandas and openpyxl are not both installed")
        return
    import pandas as pd

    columns = {
        "phase_index": PHASE_COLUMNS,
        "character_usage_long": CHARACTER_USAGE_COLUMNS,
        "character_usage_phase_latest": CHARACTER_USAGE_COLUMNS,
        "team_rank_raw": TEAM_RAW_COLUMNS,
        "team_rank_dedup_unordered": TEAM_RAW_COLUMNS,
        "name_map": NAME_MAP_COLUMNS,
        "name_map_unresolved": NAME_MAP_COLUMNS,
        "prydwen_tier_current": PRYDWEN_TIER_COLUMNS,
        "prydwen_tier_history": PRYDWEN_TIER_COLUMNS,
        "prydwen_tier_changelog": CHANGELOG_COLUMNS,
        "prydwen_tier_changelog_history": CHANGELOG_COLUMNS,
    }
    trend_columns = list(dict.fromkeys(PRYDWEN_TIER_COLUMNS + ["collect_date", "phase_ver", "phase_name", "app_rate", "avg_score", "quality_flag"]))
    columns["prydwen_tier_usage_trend"] = trend_columns
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, rows in tables.items():
            pd.DataFrame(rows, columns=columns.get(sheet)).to_excel(writer, sheet_name=sheet[:31], index=False)


def _apply_character_name(
    row: dict[str, Any],
    slug: str,
    names: dict[str, dict[str, Any]],
    tier: dict[str, dict[str, Any]],
) -> None:
    name = names.get(slug, {})
    tier_row = tier.get(slug, {})
    row["character_name_cn"] = name.get("character_name_cn", row.get("character_name_cn", ""))
    row["character_name_en"] = name.get("character_name_en") or tier_row.get("character_name_en") or row.get("character_name_en", "")
    if "role" in row and not row.get("role"):
        row["role"] = tier_row.get("role_group_cn") or tier_row.get("style_cn") or ""
    if "rarity" in row and not row.get("rarity"):
        row["rarity"] = tier_row.get("rarity") or ""


def _team_sort_key(row: dict[str, Any]) -> tuple[int, float, float]:
    rank = row.get("rank")
    try:
        rank_value = int(float(rank))
    except (TypeError, ValueError):
        rank_value = 999999
    try:
        app = -float(row.get("app_rate") or 0)
    except (TypeError, ValueError):
        app = 0.0
    try:
        avg = -float(row.get("avg_score") or 0)
    except (TypeError, ValueError):
        avg = 0.0
    return rank_value, app, avg


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 6)
    return value
