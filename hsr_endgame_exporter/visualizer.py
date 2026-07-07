from __future__ import annotations

import csv
import io
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .constants import MODE_CN
from .normalize import normalize_character_id

ELEMENT_CN = {
    "Physical": "物理",
    "Fire": "火",
    "Ice": "冰",
    "Lightning": "雷",
    "Wind": "风",
    "Quantum": "量子",
    "Imaginary": "虚数",
}

PATH_CN = {
    "Destruction": "毁灭",
    "Hunt": "巡猎",
    "Erudition": "智识",
    "Harmony": "同谐",
    "Nihility": "虚无",
    "Preservation": "存护",
    "Abundance": "丰饶",
    "Remembrance": "记忆",
    "Elation": "欢愉",
}

ROLE_ORDER = {"main_dps": 0, "sub_dps": 1, "support": 2, "sustain": 3, "unknown": 9}
ROLE_CN = {
    "main_dps": "主C",
    "sub_dps": "副C",
    "support": "辅助",
    "sustain": "生存位",
    "unknown": "未分类",
}

TIER_KEEP = {"T0", "T0.5", "T1", "T1.5", "T2"}
UNTIERED = "未分档"
RECOMMENDER_LATEST_LIMIT_PER_SCOPE = 1000
RECOMMENDER_HISTORY_LIMIT_PER_SCOPE = 120

VISUALIZER_SLUG_ALIASES = {
    "blade-mortenax": "mortenax-blade",
    "imbibitor-lunae": "dan-heng-imbibitor-lunae",
    "march-7th-evernight": "evernight",
    "march-7th-swordmaster": "march-7th-the-hunt",
    "silver-wolf-lv-999": "silver-wolf-lv999",
    "tingyun-fugue": "fugue",
    "topaz": "topaz-and-numby",
    "trailblazer-destruction": "trailblazer-the-destruction",
    "trailblazer-harmony": "trailblazer-the-harmony",
    "trailblazer-preservation": "trailblazer-the-preservation",
}

SUPPLEMENTAL_CN_NAMES = {
    "aventurine-waveflair": "砂金•戏浪",
    "robin-summeretto": "知更鸟•晴歌",
}

PHASE_NAME_CN_SEED = {
    ("moc", "Breached Nest"): "堤溃蚁穴",
    ("moc", "Cyber Mystery"): "网络谜踪",
    ("moc", "Grand Finale"): "演剧终焉",
    ("moc", "Duty Action"): "值日行动",
    ("pf", "Wordless Novel"): "无字小说",
    ("pf", "Virtual Made Manifest"): "虚境成章",
    ("pf", "Illusory Concepts"): "造象立说",
    ("pf", "Falsehood to Fact"): "借虚成真",
    ("as", "Dominance of Netherveil"): "支配冥茫",
    ("as", "Militant Lupine"): "兵锋天狼",
    ("as", "Idol of the Locusts"): "偶像螟蝗",
    ("as", "Gale of Forgetting"): "遗忘冽风",
    ("aa", "Cyber Crisis"): "网络风波",
    ("aa", "Don't Mess With Pom-Pom"): "别惹帕姆",
    ("aa", "Happiness Syntax"): "幸福语法",
    ("aa", "The Humming Laughter"): "嗡鸣如笑",
}

PHASE_MECHANICS_SEED = {
    ("moc", "4.2.1", "Duty Action"): {
        "mechanic_name": "记忆紊流",
        "mechanic_text": "我方目标施放终结技时造成的暴击伤害提高50%。施放终结技后为「记忆紊流」增加2段攻击段数，最多叠加20段。每个轮开始时，「记忆紊流」的每段攻击对随机敌方目标造成1次真实伤害。",
        "mechanic_source": "官方 4.2 版本更新说明",
        "mechanic_url": "https://hsr.hoyoverse.com/zh-cn/news/163625",
    },
    ("pf", "4.3.1", "Falsehood to Fact"): {
        "mechanic_name": "怪诞逸闻 / 荒腔走板",
        "mechanic_text": "战意机制：我方目标为敌方目标施加负面效果时，使我方额外累积1点「战意值」，每个敌方目标最多触发10次。战熄潮平：敌方效果抵抗降低30%，陷入4个及以上负面效果的敌方受到伤害提高20%。荒腔走板包含「触技」「笑韵」「变奏」三类可选增益。",
        "mechanic_source": "BWIKI 近期深渊总览",
        "mechanic_url": "https://wiki.biligame.com/sr/%E8%BF%91%E6%9C%9F%E6%B7%B1%E6%B8%8A%E6%80%BB%E8%A7%88",
    },
    ("as", "4.3.1", "Gale of Forgetting"): {
        "mechanic_name": "末法余烬 / 终焉公理",
        "mechanic_text": "末法余烬：我方施放终结技攻击敌方目标时，为目标附上「爆裂」，最多叠加6层。目标回合开始或被消灭时，根据「爆裂」层数对该目标及其相邻目标造成固定数值伤害。各首领另有可选「终焉公理」增益。",
        "mechanic_source": "BWIKI 近期深渊总览",
        "mechanic_url": "https://wiki.biligame.com/sr/%E8%BF%91%E6%9C%9F%E6%B7%B1%E6%B8%8A%E6%80%BB%E8%A7%88",
    },
    ("aa", "4.3.1", "The Humming Laughter"): {
        "mechanic_name": "异相仲裁规则 / 裁决象限",
        "mechanic_text": "骑士关含独立异常效果：骑士一入战固定降低我方50%能量，并使回合外能量恢复效率降低50%，持续2回合；敌方受击后叠加减伤/降暴伤，追加攻击或阿哈时刻可削层。骑士二我方造成伤害降低20%、受到伤害降低10%。骑士三我方回合开始损失500生命值，可致命。王棋关另有裁决象限增益。",
        "mechanic_source": "BWIKI 仲裁一览",
        "mechanic_url": "https://wiki.biligame.com/sr/%E4%BB%B2%E8%A3%81%E4%B8%80%E8%A7%88",
    },
}


def _phase_name_cn(mode: Any, phase_name: Any) -> str:
    return PHASE_NAME_CN_SEED.get((str(mode or ""), str(phase_name or "")), "")


def write_visualizer_app(
    out_dir: Path,
    *,
    trend_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    changelog_rows: list[dict[str, Any]],
    chart_rows: list[dict[str, Any]],
    character_usage_rows: list[dict[str, Any]] | None = None,
    team_rank_rows: list[dict[str, Any]] | None = None,
) -> None:
    visualizer_dir = out_dir / "visualizer"
    visualizer_dir.mkdir(parents=True, exist_ok=True)
    name_map_rows = _read_csv(out_dir / "name_map.csv")
    roster_rows = _build_roster_rows(out_dir, tier_rows, character_usage_rows or [], name_map_rows)
    roster_rows = _localize_roster_avatars(out_dir, visualizer_dir, roster_rows)
    usage_rows = _build_usage_rows(character_usage_rows or [], tier_rows, roster_rows)
    phase_info_rows = _build_phase_info_rows(_read_csv(out_dir / "phase_index.csv"))
    team_templates = _build_recommender_rows(
        team_rank_rows if team_rank_rows is not None else _read_csv(out_dir / "team_rank_raw.csv"),
        roster_rows,
    )
    banner_rows = _load_banner_rows(out_dir, roster_rows)
    data = {
        "meta": {
            "generatedAt": _latest_value(tier_rows, "fetched_at"),
            "tierUpdatedAt": _latest_value(tier_rows, "tier_updated_at"),
            "tierUpdatedDate": _latest_value(tier_rows, "tier_updated_date"),
            "source": "Prydwen Tier List + local MocStats processed dataset + HoYoWiki roster",
        },
        "trendRows": trend_rows,
        "usageRows": usage_rows or trend_rows,
        "tierRows": tier_rows,
        "changelogRows": changelog_rows,
        "chartRows": chart_rows,
        "rosterRows": roster_rows,
        "phaseInfoRows": phase_info_rows,
        "teamTemplates": team_templates,
        "bannerRows": banner_rows,
    }
    (visualizer_dir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (visualizer_dir / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    (visualizer_dir / "styles.css").write_text(_STYLES_CSS + _BANNER_CSS + _BUILD_CSS + _RECOMMENDER_CSS, encoding="utf-8")
    (visualizer_dir / "app.js").write_text(_APP_JS, encoding="utf-8")


def _latest_value(rows: list[dict[str, Any]], key: str) -> str:
    values = [str(row.get(key, "")) for row in rows if row.get(key)]
    return max(values) if values else ""


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _read_json_first(paths: list[Path]) -> dict[str, Any] | None:
    for path in paths:
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _first_filter_value(row: dict[str, Any], key: str) -> str:
    values = ((row.get("filter_values") or {}).get(key) or {}).get("values") or []
    return str(values[0]) if values else ""


def _rarity_value(value: Any) -> str:
    text = str(value or "")
    if "5" in text or "五星" in text:
        return "5"
    if "4" in text or "四星" in text:
        return "4"
    return text


def _canonical_slug(value: Any) -> str:
    slug = normalize_character_id(value)
    return VISUALIZER_SLUG_ALIASES.get(slug, slug)


def _merge_aliases(existing: Any, *aliases: Any) -> str:
    values: list[str] = []
    for value in (existing, *aliases):
        for item in str(value or "").split(";"):
            item = item.strip()
            if item and item not in values:
                values.append(item)
    return ";".join(values)


def _build_tier_meta(tier_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for source_row in tier_rows:
        raw_slug = str(source_row.get("character_slug", ""))
        slug = _canonical_slug(raw_slug)
        if not slug:
            continue
        row = dict(source_row)
        row["character_slug"] = slug
        entry = meta.setdefault(
            slug,
            {
                "roles": {},
                "tiers_by_mode": {},
                "aliases": "",
                "character_name_en": row.get("character_name_en", ""),
                "character_name_cn": row.get("character_name_cn", ""),
                "element_en": row.get("element", ""),
                "path_en": row.get("path", ""),
                "rarity": str(row.get("rarity", "")),
                "icon_url": row.get("icon_url", ""),
            },
        )
        entry["aliases"] = _merge_aliases(entry.get("aliases"), raw_slug, slug)
        if not entry.get("character_name_cn") and row.get("character_name_cn"):
            entry["character_name_cn"] = row.get("character_name_cn")
        if row.get("icon_url"):
            entry["icon_url"] = row.get("icon_url")
        if row.get("element"):
            entry["element_en"] = row.get("element")
        if row.get("path"):
            entry["path_en"] = row.get("path")
        role = str(row.get("role_group") or "unknown")
        rating = _to_float(row.get("rating"))
        current = entry["roles"].get(role)
        if current is None or rating > _to_float(current.get("rating")):
            entry["roles"][role] = row
        mode = str(row.get("tier_mode", ""))
        if mode:
            key = (mode, role)
            current = entry["tiers_by_mode"].get(key)
            if current is None or rating > _to_float(current.get("rating")):
                entry["tiers_by_mode"][key] = row
    return meta


def _build_roster_rows(
    out_dir: Path,
    tier_rows: list[dict[str, Any]],
    usage_rows: list[dict[str, Any]],
    name_map_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    tier_meta = _build_tier_meta(tier_rows)
    name_map = {_canonical_slug(row.get("character_slug", "")): row for row in name_map_rows}
    usage_meta: dict[str, dict[str, Any]] = {}
    for source_row in usage_rows:
        slug = _canonical_slug(source_row.get("character_slug", ""))
        if slug and slug not in usage_meta:
            row = dict(source_row)
            row["character_slug"] = slug
            usage_meta[slug] = row

    raw_dir = out_dir / "raw" / "hoyowiki"
    zh_rows = _read_json_list(raw_dir / "hsr_characters_zh-cn.json")
    en_rows = _read_json_list(raw_dir / "hsr_characters_en-us.json")
    zh_by_id = {str(row.get("entry_page_id")): row for row in zh_rows}
    en_by_id = {str(row.get("entry_page_id")): row for row in en_rows}
    zh_order = {str(row.get("entry_page_id")): index for index, row in enumerate(zh_rows)}
    en_order = {str(row.get("entry_page_id")): index for index, row in enumerate(en_rows)}

    roster: dict[str, dict[str, Any]] = {}
    for entry_id in sorted(set(zh_by_id) | set(en_by_id), key=lambda x: min(zh_order.get(x, 9999), en_order.get(x, 9999))):
        en_row = en_by_id.get(entry_id, {})
        zh_row = zh_by_id.get(entry_id, {})
        en_name = str(en_row.get("name") or "").strip()
        if not en_name:
            continue
        raw_slug = normalize_character_id(en_name)
        slug = _canonical_slug(raw_slug)
        if not slug:
            continue
        order = min(zh_order.get(entry_id, 9999), en_order.get(entry_id, 9999))
        entry = _roster_entry(
            slug=slug,
            release_order=order,
            character_name_en=en_name,
            character_name_cn=str(
                zh_row.get("name")
                or SUPPLEMENTAL_CN_NAMES.get(slug)
                or name_map.get(slug, {}).get("character_name_cn")
                or ""
            ).strip(),
            element_cn=_first_filter_value(zh_row, "character_combat_type") or ELEMENT_CN.get(_first_filter_value(en_row, "character_combat_type"), ""),
            element_en=_first_filter_value(en_row, "character_combat_type"),
            path_cn=_first_filter_value(zh_row, "character_paths") or PATH_CN.get(_first_filter_value(en_row, "character_paths"), ""),
            path_en=_first_filter_value(en_row, "character_paths"),
            rarity=_rarity_value(_first_filter_value(en_row, "character_rarity") or _first_filter_value(zh_row, "character_rarity")),
            icon_url=str(zh_row.get("icon_url") or en_row.get("icon_url") or ""),
            tier_meta=tier_meta.get(slug, {}),
            usage_meta=usage_meta.get(slug, {}),
            source="HoYoWiki",
        )
        entry["alias_slugs"] = _merge_aliases(entry.get("alias_slugs"), raw_slug, slug)
        if slug in roster:
            roster[slug] = _merge_roster_entries(roster[slug], entry)
        else:
            roster[slug] = entry

    extra_order = 10000
    for slug, meta in sorted(tier_meta.items()):
        if slug in roster:
            roster[slug] = _merge_roster_entry(roster[slug], meta)
            continue
        extra_order += 1
        roster[slug] = _roster_entry(
            slug=slug,
            release_order=extra_order,
            character_name_en=str(meta.get("character_name_en") or ""),
            character_name_cn=str(
                meta.get("character_name_cn")
                or SUPPLEMENTAL_CN_NAMES.get(slug)
                or name_map.get(slug, {}).get("character_name_cn")
                or ""
            ),
            element_cn=ELEMENT_CN.get(str(meta.get("element_en") or ""), ""),
            element_en=str(meta.get("element_en") or ""),
            path_cn=PATH_CN.get(str(meta.get("path_en") or ""), ""),
            path_en=str(meta.get("path_en") or ""),
            rarity=str(meta.get("rarity") or ""),
            icon_url=str(meta.get("icon_url") or ""),
            tier_meta=meta,
            usage_meta=usage_meta.get(slug, {}),
            source="Prydwen",
        )

    usage_order = 20000
    for slug, row in sorted(usage_meta.items()):
        if slug in roster:
            continue
        usage_order += 1
        roster[slug] = _roster_entry(
            slug=slug,
            release_order=usage_order,
            character_name_en=str(row.get("character_name_en") or slug),
            character_name_cn=str(row.get("character_name_cn") or SUPPLEMENTAL_CN_NAMES.get(slug) or name_map.get(slug, {}).get("character_name_cn") or ""),
            element_cn="",
            element_en="",
            path_cn="",
            path_en="",
            rarity=str(row.get("rarity") or ""),
            icon_url="",
            tier_meta={},
            usage_meta=row,
            source="usage",
        )
    return sorted(roster.values(), key=lambda row: (_sort_order(row.get("release_order")), str(row.get("character_name_en", ""))))


def _sort_order(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 99999


def _roster_entry(
    *,
    slug: str,
    release_order: int,
    character_name_en: str,
    character_name_cn: str,
    element_cn: str,
    element_en: str,
    path_cn: str,
    path_en: str,
    rarity: str,
    icon_url: str,
    tier_meta: dict[str, Any],
    usage_meta: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    roles = sorted((tier_meta.get("roles") or {}).keys(), key=lambda role: ROLE_ORDER.get(role, 9))
    if not roles:
        roles = ["unknown"]
    if not character_name_cn:
        character_name_cn = str(usage_meta.get("character_name_cn") or "")
    if not character_name_en:
        character_name_en = str(usage_meta.get("character_name_en") or slug)
    if not icon_url:
        icon_url = str((tier_meta or {}).get("icon_url") or "")
    if not element_en:
        element_en = str((tier_meta or {}).get("element_en") or "")
    if not element_cn:
        element_cn = ELEMENT_CN.get(element_en, "")
    if not path_en:
        path_en = str((tier_meta or {}).get("path_en") or "")
    if not path_cn:
        path_cn = PATH_CN.get(path_en, "")
    return {
        "character_slug": slug,
        "character_name_en": character_name_en,
        "character_name_cn": character_name_cn,
        "element_cn": element_cn,
        "element_en": element_en,
        "path_cn": path_cn,
        "path_en": path_en,
        "rarity": rarity,
        "icon_url": icon_url,
        "release_order": release_order,
        "role_groups": ";".join(roles),
        "role_group_cns": ";".join(ROLE_CN.get(role, role) for role in roles),
        "alias_slugs": slug,
        "source": source,
    }


def _merge_roster_entries(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged["alias_slugs"] = _merge_aliases(base.get("alias_slugs"), incoming.get("alias_slugs"), incoming.get("character_slug"))
    merged["source"] = _merge_aliases(base.get("source"), incoming.get("source"))
    for key in ("character_name_cn", "character_name_en", "element_cn", "element_en", "path_cn", "path_en", "rarity"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    if _sort_order(incoming.get("release_order")) < _sort_order(merged.get("release_order")):
        merged["release_order"] = incoming.get("release_order")
    if _prefer_icon(incoming.get("icon_url"), merged.get("icon_url"), str(merged.get("character_slug", ""))):
        merged["icon_url"] = incoming.get("icon_url")
    roles = _merge_aliases(base.get("role_groups"), incoming.get("role_groups"))
    if roles:
        ordered_roles = sorted(set(roles.split(";")), key=lambda role: ROLE_ORDER.get(role, 9))
        merged["role_groups"] = ";".join(ordered_roles)
        merged["role_group_cns"] = ";".join(ROLE_CN.get(role, role) for role in ordered_roles)
    return merged


def _merge_roster_entry(entry: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    entry["alias_slugs"] = _merge_aliases(entry.get("alias_slugs"), meta.get("aliases"), entry.get("character_slug"))
    if not entry.get("character_name_cn") and meta.get("character_name_cn"):
        entry["character_name_cn"] = meta["character_name_cn"]
    if not entry.get("character_name_cn"):
        entry["character_name_cn"] = SUPPLEMENTAL_CN_NAMES.get(str(entry.get("character_slug", "")), "")
    if _prefer_icon(meta.get("icon_url"), entry.get("icon_url"), str(entry.get("character_slug", ""))):
        entry["icon_url"] = meta["icon_url"]
    if not entry.get("element_en") and meta.get("element_en"):
        entry["element_en"] = meta["element_en"]
        entry["element_cn"] = ELEMENT_CN.get(str(meta["element_en"]), "")
    if not entry.get("path_en") and meta.get("path_en"):
        entry["path_en"] = meta["path_en"]
        entry["path_cn"] = PATH_CN.get(str(meta["path_en"]), "")
    roles = sorted((meta.get("roles") or {}).keys(), key=lambda role: ROLE_ORDER.get(role, 9))
    if roles:
        entry["role_groups"] = ";".join(roles)
        entry["role_group_cns"] = ";".join(ROLE_CN.get(role, role) for role in roles)
    entry["source"] = _merge_aliases(entry.get("source"), "Prydwen")
    return entry


def _prefer_icon(candidate: Any, current: Any, slug: str) -> bool:
    candidate_text = str(candidate or "")
    current_text = str(current or "")
    if not candidate_text:
        return False
    if not current_text:
        return True
    if slug.startswith("trailblazer-") and "prydwen.gg" in candidate_text:
        return True
    if current_text.lower().endswith(".gif") and not candidate_text.lower().endswith(".gif"):
        return True
    return False


def _build_usage_rows(
    character_usage_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    roster_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not character_usage_rows:
        return []
    tier_meta = _build_tier_meta(tier_rows)
    roster_by_slug: dict[str, dict[str, Any]] = {}
    for row in roster_rows:
        roster_by_slug[str(row["character_slug"])] = row
        for alias in str(row.get("alias_slugs", "")).split(";"):
            if alias:
                roster_by_slug[alias] = row
    output: list[dict[str, Any]] = []
    for source_usage in character_usage_rows:
        usage = dict(source_usage)
        if usage.get("sub_mode") not in {"all", "all_bosses"}:
            continue
        slug = _canonical_slug(usage.get("character_slug", ""))
        if not slug:
            continue
        usage["character_slug"] = slug
        mode = str(usage.get("mode", ""))
        meta = tier_meta.get(slug, {})
        mode_roles = [
            row
            for (tier_mode, _role), row in (meta.get("tiers_by_mode") or {}).items()
            if tier_mode == mode
        ]
        if mode_roles:
            for tier in mode_roles:
                if tier.get("tier") in TIER_KEEP:
                    output.append(_usage_entry(usage, tier, roster_by_slug.get(slug, {})))
        else:
            role_rows = list((meta.get("roles") or {}).values()) or [{}]
            for role_row in role_rows:
                output.append(_usage_entry(usage, role_row, roster_by_slug.get(slug, {}), untiered=True))
    return output


def _usage_entry(
    usage: dict[str, Any],
    tier: dict[str, Any],
    roster: dict[str, Any],
    *,
    untiered: bool = False,
) -> dict[str, Any]:
    slug = str(usage.get("character_slug", ""))
    role_group = str(tier.get("role_group") or _first_semicolon(roster.get("role_groups")) or "unknown")
    return {
        "tier_snapshot_id": tier.get("tier_snapshot_id", ""),
        "tier_updated_date": tier.get("tier_updated_date", ""),
        "tier_mode": usage.get("mode", ""),
        "tier_mode_cn": usage.get("mode_cn") or MODE_CN.get(str(usage.get("mode", "")), ""),
        "sub_mode": usage.get("sub_mode", ""),
        "sub_mode_cn": usage.get("sub_mode_cn", ""),
        "character_slug": slug,
        "character_name_en": usage.get("character_name_en") or roster.get("character_name_en") or slug,
        "character_name_cn": usage.get("character_name_cn") or roster.get("character_name_cn") or "",
        "prydwen_role": tier.get("prydwen_role", ""),
        "role_group": role_group,
        "role_group_cn": ROLE_CN.get(role_group, tier.get("role_group_cn") or "未分类"),
        "tier": UNTIERED if untiered else tier.get("tier", UNTIERED),
        "rating": "" if untiered else tier.get("rating", ""),
        "tags": tier.get("tags", ""),
        "marks": tier.get("marks", ""),
        "collect_date": usage.get("collect_date", ""),
        "phase_ver": usage.get("phase_ver", ""),
        "phase_name": usage.get("phase_name", ""),
        "phase_name_cn": _phase_name_cn(usage.get("mode", ""), usage.get("phase_name", "")),
        "app_rate": usage.get("app_rate", ""),
        "avg_round": usage.get("avg_round", ""),
        "quality_flag": usage.get("quality_flag", ""),
        "icon_url": roster.get("icon_url") or tier.get("icon_url", ""),
        "element_cn": roster.get("element_cn", ""),
        "element_en": roster.get("element_en", ""),
        "path_cn": roster.get("path_cn", ""),
        "path_en": roster.get("path_en", ""),
        "rarity": roster.get("rarity", ""),
    }


def _first_semicolon(value: Any) -> str:
    text = str(value or "")
    return text.split(";")[0] if text else ""


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _localize_roster_avatars(
    out_dir: Path,
    visualizer_dir: Path,
    roster_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del out_dir
    avatars_dir = visualizer_dir / "assets" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for row in roster_rows:
        new_row = dict(row)
        icon_url = str(new_row.get("icon_url") or "")
        slug = str(new_row.get("character_slug") or "")
        if icon_url and slug:
            local_path = avatars_dir / f"{slug}.webp"
            if local_path.exists() or _download_static_avatar(icon_url, local_path):
                new_row["icon_url"] = f"./assets/avatars/{local_path.name}"
        output.append(new_row)
    return output


def _download_static_avatar(url: str, destination: Path) -> bool:
    try:
        from PIL import Image

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 hsr-endgame-exporter/0.1",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        image = Image.open(io.BytesIO(payload))
        image.seek(0)
        frame = image.convert("RGBA")
        frame.thumbnail((160, 160))
        canvas = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        canvas.alpha_composite(frame, ((160 - frame.width) // 2, (160 - frame.height) // 2))
        destination.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(destination, "WEBP", quality=88, method=6)
        return True
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def _build_recommender_rows(
    team_rows: list[dict[str, Any]],
    roster_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not team_rows:
        return []
    roster_lookup = _build_roster_lookup(roster_rows)
    latest_collect_dates: dict[str, str] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        collect_date = str(row.get("collect_date") or "")
        if mode and collect_date and collect_date >= latest_collect_dates.get(mode, ""):
            latest_collect_dates[mode] = collect_date

    grouped: dict[str, dict[str, Any]] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        if not mode or str(row.get("collect_date") or "") != latest_collect_dates.get(mode, ""):
            continue
        chars = [_canonical_slug(row.get(f"char_{index}_slug", "")) for index in range(1, 5)]
        chars = [str(roster_lookup.get(char, {}).get("character_slug") or char) for char in chars]
        if len(chars) != 4 or any(not char for char in chars):
            continue
        scope = str(row.get("scope") or "")
        scope_key, scope_label, scope_order = _recommender_scope(mode, scope)
        template = {
            "mode": mode,
            "mode_cn": row.get("mode_cn") or MODE_CN.get(mode, mode),
            "scope_key": scope_key,
            "scope": scope,
            "scope_label": scope_label,
            "scope_order": scope_order,
            "snapshot_id": row.get("snapshot_id", ""),
            "collect_date": row.get("collect_date", ""),
            "phase_ver": row.get("phase_ver", ""),
            "phase_name": row.get("phase_name", ""),
            "phase_name_cn": _phase_name_cn(mode, row.get("phase_name", "")),
            "rank": _numeric_value(row.get("rank")),
            "app_rate": _numeric_value(row.get("app_rate")),
            "avg_round": _numeric_value(row.get("avg_round")),
            "source_kind": row.get("source_kind", ""),
            "source_file": row.get("source_file", ""),
            "chars": chars,
            "names_cn": [
                str(roster_lookup.get(char, {}).get("character_name_cn") or row.get(f"char_{index}_name_cn") or "")
                for index, char in enumerate(chars, start=1)
            ],
        }
        key = f"{mode}|{scope_key}|{'>'.join(sorted(chars))}"
        current = grouped.get(key)
        if current is None or _template_sort_key(template) < _template_sort_key(current):
            grouped[key] = template

    output: list[dict[str, Any]] = []
    per_scope: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in grouped.values():
        per_scope.setdefault((str(row["mode"]), str(row["scope_key"])), []).append(row)
    for (_mode, scope_key), rows in per_scope.items():
        limit = 240 if scope_key == "all" else RECOMMENDER_LATEST_LIMIT_PER_SCOPE
        output.extend(sorted(rows, key=_template_sort_key)[:limit])
    return sorted(output, key=lambda row: (str(row.get("mode", "")), int(row.get("scope_order") or 99), _template_sort_key(row)))


def _build_phase_info_rows(phase_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in phase_rows:
        key = (str(row.get("mode") or ""), str(row.get("phase_ver") or ""), str(row.get("phase_name") or ""))
        if not key[0] or not key[1]:
            continue
        current = chosen.get(key)
        if current is None or str(row.get("collect_date") or "") >= str(current.get("collect_date") or ""):
            chosen[key] = row
    output: list[dict[str, Any]] = []
    for (mode, phase_ver, phase_name), row in sorted(chosen.items()):
        seeded = PHASE_MECHANICS_SEED.get((mode, phase_ver, phase_name), {})
        output.append(
            {
                "mode": mode,
                "mode_cn": row.get("mode_cn") or MODE_CN.get(mode, mode),
                "snapshot_id": row.get("snapshot_id", ""),
                "collect_date": row.get("collect_date", ""),
                "phase_ver": phase_ver,
                "phase_name": phase_name,
                "phase_name_cn": _phase_name_cn(mode, phase_name),
                "start_date": row.get("start_date", ""),
                "end_date": row.get("end_date", ""),
                "source": row.get("source", ""),
                "source_path": row.get("source_path", ""),
                "mechanic_name": seeded.get("mechanic_name", ""),
                "mechanic_text": seeded.get("mechanic_text", ""),
                "mechanic_source": seeded.get("mechanic_source", ""),
                "mechanic_url": seeded.get("mechanic_url", ""),
            }
        )
    return output


def _load_banner_rows(out_dir: Path, roster_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = _read_json_first(
        [
            out_dir / "hsr_banner_plan.json",
            out_dir.parent / "configs" / "hsr_banner_plan.json",
            Path("configs") / "hsr_banner_plan.json",
        ]
    )
    if not config:
        return []
    roster = {row["character_slug"]: row for row in roster_rows}
    rows: list[dict[str, Any]] = []
    for phase in config.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        for index, char in enumerate(phase.get("characters") or [], start=1):
            if not isinstance(char, dict):
                continue
            slug = _canonical_slug(char.get("slug"))
            if not slug:
                continue
            info = roster.get(slug, {})
            rows.append(
                {
                    "phase_id": phase.get("id", ""),
                    "phase_status": phase.get("status", ""),
                    "phase_title": phase.get("title", ""),
                    "phase_subtitle": phase.get("subtitle", ""),
                    "date_range": phase.get("date_range", ""),
                    "source_label": char.get("source_label") or phase.get("source_label", ""),
                    "source_url": char.get("source_url") or phase.get("source_url", ""),
                    "slot": index,
                    "character_slug": slug,
                    "character_name_cn": char.get("name_cn") or info.get("character_name_cn") or "",
                    "character_name_en": char.get("name_en") or info.get("character_name_en") or "",
                    "banner_role": char.get("banner_role", ""),
                    "rarity": char.get("rarity") or info.get("rarity") or "",
                    "element_cn": char.get("element_cn") or info.get("element_cn") or "",
                    "path_cn": char.get("path_cn") or info.get("path_cn") or "",
                    "role_group_cns": char.get("role_group_cns") or info.get("role_group_cns") or "",
                    "icon_url": char.get("icon_url") or info.get("icon_url") or "",
                    "analysis_tags": char.get("analysis_tags") or [],
                    "focus": char.get("focus", ""),
                }
            )
    return rows


def _build_roster_lookup(roster_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in roster_rows:
        slug = str(row.get("character_slug") or "")
        if slug:
            lookup[slug] = row
            lookup[_canonical_slug(slug)] = row
        for alias in str(row.get("alias_slugs") or "").split(";"):
            alias_slug = _canonical_slug(alias)
            if alias_slug:
                lookup[alias_slug] = row
    return lookup


def _recommender_scope(mode: str, scope: str) -> tuple[str, str, int]:
    text = str(scope or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if normalized in {"", "top", "all"}:
        return "all", "全关", 90
    if mode == "moc":
        if normalized in {"1", "12-1", "stage-12-1"}:
            return "12-1", "12-1 / 上半", 1
        if normalized in {"2", "12-2", "stage-12-2"}:
            return "12-2", "12-2 / 下半", 2
    if mode in {"pf", "as"}:
        stage_map = {
            "1": ("4-1", "4-1 / 第1关", 1),
            "2": ("4-2", "4-2 / 第2关", 2),
            "3": ("4-3", "4-3 / 第3关", 3),
            "4-1": ("4-1", "4-1 / 第1关", 1),
            "4-2": ("4-2", "4-2 / 第2关", 2),
            "4-3": ("4-3", "4-3 / 第3关", 3),
            "stage-4-1": ("4-1", "4-1 / 第1关", 1),
            "stage-4-2": ("4-2", "4-2 / 第2关", 2),
            "stage-4-3": ("4-3", "4-3 / 第3关", 3),
        }
        if normalized in stage_map:
            return stage_map[normalized]
    if mode == "aa":
        stage_map = {
            "1": ("1-1", "1-1", 1),
            "2": ("1-2", "1-2", 2),
            "3": ("1-3", "1-3", 3),
            "4": ("2-1", "2-1", 4),
            "1-1": ("1-1", "1-1", 1),
            "1-2": ("1-2", "1-2", 2),
            "1-3": ("1-3", "1-3", 3),
            "2-1": ("2-1", "2-1", 4),
        }
        if normalized in stage_map:
            return stage_map[normalized]
    return normalized, scope or normalized, 50


def _numeric_value(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _template_sort_key(row: dict[str, Any]) -> tuple[int, int, float, float, float]:
    source_scope = str(row.get("scope") or "")
    normalized_scope = re.sub(r"[^a-z0-9]+", "-", source_scope.lower()).strip("-")
    scope_priority = 0 if "-" in normalized_scope and normalized_scope not in {"all", "top"} else 1
    source_priority = {"hf_comps": 0, "prydwen_page": 1}.get(str(row.get("source_kind") or ""), 2)
    rank = row.get("rank")
    rank_value = float(rank) if isinstance(rank, (int, float)) else 1_000_000.0
    app_rate = row.get("app_rate")
    app_value = float(app_rate) if isinstance(app_rate, (int, float)) else -1.0
    avg_round = row.get("avg_round")
    avg_value = float(avg_round) if isinstance(avg_round, (int, float)) else 1_000_000.0
    return scope_priority, source_priority, rank_value, -app_value, avg_value


_INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HSR 高难与本地 Box 可视化</title>
  <link rel="icon" href="data:," />
  <link rel="stylesheet" href="./styles.css" />
</head>
<body>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <h1>HSR 高难与本地 Box</h1>
        <p id="metaLine">加载数据中...</p>
      </div>
      <div class="toolbar-actions">
        <div class="app-tabs" id="appTabs"></div>
        <button id="resetBtn" type="button" title="恢复当前页默认筛选">重置</button>
        <a href="../hsr_endgame_dataset.xlsx" title="打开本次导出的 Excel 数据集">Excel</a>
      </div>
    </header>

    <section id="analysisView">
      <section class="controls" aria-label="趋势筛选控制">
        <div class="control-group"><label>模式</label><div class="segmented" id="modeControl"></div></div>
        <div class="control-group"><label>视图</label><div class="segmented" id="viewControl"></div></div>
        <div class="control-group"><label>职能</label><div class="segmented" id="roleControl"></div></div>
        <div class="control-group"><label>T档</label><div class="tier-checks" id="tierControl"></div></div>
        <div class="control-group compact"><label>数量</label><select id="limitSelect" title="按最近一期出场率排序后的展示数量"><option value="8">Top 8</option><option value="12" selected>Top 12</option><option value="20">Top 20</option><option value="all">全部</option></select></div>
        <div class="control-group compact"><label>指标</label><select id="metricSelect" title="切换纵轴或色块使用的指标"><option value="app_rate">出场率</option><option value="avg_round">平均值</option></select></div>
        <div class="control-group search"><label>搜索</label><input id="searchInput" type="search" placeholder="中文名 / 英文名 / slug" /></div>
        <div class="control-group compact"><label>节点</label><label class="checkline" title="关闭后以普通圆点显示趋势节点"><input id="avatarToggle" type="checkbox" checked />头像</label></div>
      </section>

      <section class="workspace">
        <section class="chart-panel">
          <div class="panel-head">
            <div><h2 id="chartTitle">趋势图</h2><p id="chartSubtitle"></p></div>
            <div id="summaryBadges" class="summary-badges"></div>
          </div>
          <div class="chart-wrap">
            <svg id="chart" role="img" aria-label="角色出场率可视化图表"></svg>
            <div id="tooltip" class="tooltip" hidden></div>
          </div>
        </section>
        <aside class="side-panel">
          <div class="side-section characters"><h3>角色</h3><div id="characterList" class="character-list"></div></div>
          <div class="side-section changelog"><h3>Changelog</h3><div id="changelogList" class="changelog-list"></div></div>
        </aside>
      </section>
    </section>

    <section id="bannerView" class="hidden">
      <section class="banner-controls" aria-label="卡池情报筛选控制">
        <div class="control-group"><label>阶段</label><div class="segmented" id="bannerPhaseControl"></div></div>
        <div class="control-group search"><label>搜索</label><input id="bannerSearchInput" type="search" placeholder="角色 / 属性 / 命途 / 标签" /></div>
      </section>
      <section class="banner-hero">
        <div><h2 id="bannerTitle">卡池情报</h2><p id="bannerSubtitle"></p></div>
        <div id="bannerBadges" class="summary-badges"></div>
      </section>
      <section id="bannerGrid" class="banner-grid"></section>
      <div id="bannerTooltip" class="tooltip" hidden></div>
    </section>

    <section id="boxView" class="hidden">
      <section class="box-controls" aria-label="Box 筛选控制">
        <div class="control-group"><label>属性</label><div class="segmented" id="boxElementControl"></div></div>
        <div class="control-group"><label>命途</label><div class="segmented" id="boxPathControl"></div></div>
        <div class="control-group"><label>职能</label><div class="segmented" id="boxRoleControl"></div></div>
        <div class="control-group compact"><label>星级</label><select id="boxRaritySelect"><option value="all">全部</option><option value="5">五星</option><option value="4">四星</option></select></div>
        <div class="control-group compact"><label>状态</label><select id="boxOwnedSelect"><option value="all">全部</option><option value="owned">已拥有</option><option value="missing">未拥有</option></select></div>
        <div class="control-group search"><label>搜索</label><input id="boxSearchInput" type="search" placeholder="中文名 / 英文名 / slug" /></div>
        <div class="box-actions">
          <button id="boxExportBtn" type="button">导出Box</button>
          <button id="boxImportBtn" type="button">导入</button>
          <button id="boxMarkVisibleBtn" type="button">筛选设为已拥有</button>
          <button id="boxClearVisibleBtn" type="button">筛选设为未拥有</button>
          <button id="boxBuildVisibleBtn" type="button">筛选设为练满</button>
          <button id="boxClearBuildVisibleBtn" type="button">清筛选练度</button>
          <input id="boxImportInput" type="file" accept="application/json,.json" hidden />
        </div>
      </section>
      <section class="build-editor hidden" id="buildEditor" aria-label="练度编辑">
        <div class="build-editor-head">
          <img id="buildEditorIcon" alt="" />
          <div><h2 id="buildEditorTitle">练度</h2><p id="buildEditorSubtitle"></p></div>
        </div>
        <div class="build-fields">
          <label>等级<select id="buildLevelSelect"></select></label>
          <label>光锥<select id="buildLcSelect"></select></label>
          <label>星魂<select id="buildEidolonSelect"></select></label>
          <label>专武<select id="buildSignatureSelect"></select></label>
          <label>行迹<select id="buildTraceSelect"></select></label>
          <label>遗器<select id="buildRelicSelect"></select></label>
        </div>
        <div class="build-actions">
          <span id="buildScoreText"></span>
          <button id="buildMaxBtn" type="button">设为练满</button>
          <button id="buildClearBtn" type="button">清空练度</button>
        </div>
      </section>
      <section class="box-panel">
        <div class="panel-head">
          <div><h2>我的 Box</h2><p id="boxSubtitle"></p></div>
          <div id="boxBadges" class="summary-badges"></div>
        </div>
        <div id="boxGrid" class="box-grid"></div>
      </section>
      <div id="boxTooltip" class="tooltip" hidden></div>
    </section>

    <section id="recommenderView" class="hidden">
      <section class="rec-controls" aria-label="组队推荐控制">
        <div class="control-group"><label>模式</label><div class="segmented" id="recModeControl"></div></div>
        <div class="control-group compact"><label>关卡</label><select id="recScopeSelect" title="只使用当前模式最新采样期的同关卡队伍模板"></select></div>
        <div class="control-group"><label>推荐属性</label><div class="tier-checks" id="recElementControl"></div></div>
        <div class="control-group compact"><label>缺口</label><select id="recGapSelect" title="限制缺少角色数量"><option value="0">只看可成队</option><option value="1" selected>最多缺1人</option><option value="2">最多缺2人</option><option value="4">显示全部</option></select></div>
        <div class="control-group compact"><label>风险</label><select id="recRiskSelect" title="当前模式 T1及以下、近期走弱或核心属性不匹配时的处理方式"><option value="warn" selected>仅提醒</option><option value="filter">过滤风险</option><option value="off">忽略风险</option></select></div>
        <div class="control-group compact"><label>数量</label><select id="recLimitSelect"><option value="8" selected>Top 8</option><option value="12">Top 12</option><option value="20">Top 20</option></select></div>
        <div class="control-group search"><label>搜索</label><input id="recSearchInput" type="search" placeholder="角色 / 队伍 / 来源" /></div>
      </section>
      <section class="phase-mechanics" id="phaseMechanicsPanel">
        <div>
          <h2 id="phaseMechanicsTitle">本期机制</h2>
          <p id="phaseMechanicsSubtitle"></p>
        </div>
        <p id="phaseMechanicsText"></p>
        <a id="phaseMechanicsSource" href="#" target="_blank" rel="noopener noreferrer"></a>
      </section>
      <section class="rec-layout">
        <section class="rec-panel">
          <div class="panel-head">
            <div><h2 id="recTitle">组队推荐</h2><p id="recSubtitle"></p></div>
            <div id="recBadges" class="summary-badges"></div>
          </div>
          <div id="recList" class="rec-list"></div>
        </section>
        <aside class="rec-slate">
          <div class="panel-head">
            <div><h2>多队方案</h2><p id="recSlateSubtitle"></p></div>
          </div>
          <div id="recSlateList" class="rec-slate-list"></div>
        </aside>
      </section>
      <div id="recTooltip" class="tooltip" hidden></div>
    </section>
  </main>
  <script src="./app.js"></script>
</body>
</html>
"""


_STYLES_CSS = """*{box-sizing:border-box}body{margin:0;background:#f5f7f8;color:#172126;font-family:Inter,Segoe UI,Arial,'Microsoft YaHei',sans-serif}button,input,select{font:inherit}.hidden{display:none!important}.app-shell{min-height:100vh;padding:18px 20px 24px}.topbar{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px}.topbar h1{margin:0 0 6px;font-size:24px;line-height:1.2;letter-spacing:0}.topbar p{margin:0;color:#607079;font-size:13px}.toolbar-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.toolbar-actions a,.toolbar-actions button,.box-actions button{border:1px solid #bac7cc;background:white;color:#1d3942;text-decoration:none;border-radius:6px;padding:8px 12px;cursor:pointer}.toolbar-actions a:hover,.toolbar-actions button:hover,.box-actions button:hover{border-color:#36606a;background:#f8fbfb}.app-tabs{display:flex;gap:6px}.app-tabs button.active{background:#174c5a;color:#fff;border-color:#174c5a}.controls,.box-controls{display:grid;grid-template-columns:1fr .9fr 1.25fr 1.15fr .58fr .58fr 1.1fr .5fr;gap:10px;align-items:end;background:#fff;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.box-controls{grid-template-columns:1.35fr 1.55fr 1.15fr .5fr .55fr 1fr 2fr}.control-group{min-width:0}.control-group label{display:block;color:#607079;font-size:12px;margin-bottom:6px}.control-group input[type=search],.control-group select{width:100%;height:36px;border:1px solid #c8d4d9;background:#fff;border-radius:6px;padding:7px 9px;color:#172126}.segmented,.tier-checks{display:flex;gap:6px;flex-wrap:wrap}.segmented button,.tier-checks button{border:1px solid #c8d4d9;background:#f9fbfb;color:#263a43;border-radius:6px;padding:7px 9px;cursor:pointer;white-space:nowrap}.segmented button:hover,.tier-checks button:hover{border-color:#4f737d}.segmented button.active,.tier-checks button.active{background:#174c5a;color:#fff;border-color:#174c5a}.checkline{display:flex!important;align-items:center;gap:6px;height:36px;border:1px solid #c8d4d9;border-radius:6px;padding:0 9px;background:#f9fbfb;color:#263a43!important;margin:0!important}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:14px}.chart-panel,.side-panel,.box-panel{background:white;border:1px solid #d8e1e5;border-radius:8px}.panel-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;padding:14px 16px 10px;border-bottom:1px solid #edf1f3}.panel-head h2{margin:0 0 4px;font-size:18px;letter-spacing:0}.panel-head p{margin:0;color:#697b83;font-size:12px}.summary-badges{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;max-width:440px}.summary-badges span{border:1px solid #d6e1e5;background:#f8fafb;border-radius:999px;padding:4px 8px;color:#39505a;font-size:11px;font-weight:650}.chart-wrap{position:relative;height:620px;overflow:hidden}#chart{width:100%;height:620px;display:block}.tooltip{position:fixed;z-index:20;width:308px;background:#101820;color:white;border-radius:8px;padding:12px;box-shadow:0 16px 36px rgba(0,0,0,.24);pointer-events:none}.tooltip-head{display:flex;gap:10px;align-items:center;margin-bottom:8px}.tooltip img{width:42px;height:42px;border-radius:50%;border:2px solid rgba(255,255,255,.32);background:#22313a}.tooltip strong{display:block;font-size:15px}.tooltip span{display:block;color:#c9d5da;font-size:12px}.tooltip-grid{display:grid;grid-template-columns:86px 1fr;gap:4px 8px;font-size:12px;line-height:1.35}.tooltip-grid b{color:#9fb7c0;font-weight:500}.side-panel{padding:12px;display:flex;flex-direction:column;gap:12px;max-height:748px;overflow:hidden}.side-section{min-height:0;display:flex;flex-direction:column}.side-section.characters{flex:1 1 auto}.side-section.changelog{flex:0 0 230px}.side-section h3{margin:0 0 8px;font-size:15px;letter-spacing:0}.character-list,.changelog-list{overflow:auto;display:flex;flex-direction:column;gap:7px;padding-right:4px}.character-card{border:1px solid #d8e1e5;background:#fbfcfd;border-radius:7px;padding:8px;display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:8px;align-items:center;cursor:pointer;text-align:left}.character-card:hover{border-color:#86a6af;background:#f4f9fa}.character-card.active{border-color:#174c5a;background:#eaf4f5}.character-card.dim{opacity:.42}.character-card img{width:38px;height:38px;border-radius:50%;background:#e7ecef}.character-card .name{font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.character-card .meta{color:#6b7c84;font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pill{display:inline-flex;align-items:center;justify-content:center;min-width:40px;padding:3px 6px;border-radius:999px;background:#174c5a;color:#fff;font-size:11px;font-weight:700}.rate{font-size:13px;font-weight:700;color:#172126;text-align:right;margin-top:3px}.changelog-item{border-left:3px solid #8aa3ad;background:#f8fafb;border-radius:5px;padding:8px 9px}.changelog-item time{font-weight:700;font-size:12px;color:#174c5a}.changelog-item p{margin:4px 0 0;color:#405158;font-size:12px;line-height:1.45}.axis-label{fill:#51646d;font-size:11px}.grid{stroke:#e7ecef}.axis-line{stroke:#32464f}.series-line{fill:none;stroke-width:2.4;opacity:.88;transition:opacity .12s,stroke-width .12s}.series-hit{fill:none;stroke:transparent;stroke-width:12;pointer-events:stroke;cursor:pointer}.series-line.dim,.avatar-node.dim,.point-node.dim,.bar-line.dim,.heat-cell.dim,.rank-label.dim{opacity:.12}.series-line.focused,.bar-line.focused{stroke-width:4;opacity:1}.avatar-node,.point-node,.heat-cell{cursor:pointer}.avatar-ring{stroke:white;stroke-width:2;filter:drop-shadow(0 1px 2px rgba(0,0,0,.24));pointer-events:none}.rank-label{fill:#263a43;font-size:12px;font-weight:650}.muted-label{fill:#6b7c84;font-size:11px}.empty-state{fill:#6b7c84;font-size:15px}.heat-cell{rx:4;ry:4;stroke:#fff;stroke-width:1}.heat-head{fill:#51646d;font-size:10px}.heat-name{fill:#263a43;font-size:12px;font-weight:650}.box-actions{display:flex;gap:6px;flex-wrap:wrap;align-items:end}.box-panel{min-height:660px}.box-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:10px;padding:14px}.box-card{position:relative;border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;padding:10px 8px 9px;min-height:142px;cursor:pointer;text-align:center}.box-card:hover{border-color:#86a6af;background:#f4f9fa}.box-card.owned{border-color:#2f7b69;background:#f4fbf8}.box-card.missing img{filter:grayscale(1);opacity:.36}.box-card img{width:64px;height:64px;border-radius:50%;background:#e6ecef;object-fit:cover;transition:filter .12s,opacity .12s}.box-card .box-name{margin-top:7px;font-size:12px;font-weight:700;line-height:1.25;min-height:30px;display:flex;align-items:center;justify-content:center}.box-card .box-meta{font-size:11px;color:#637780;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.owned-dot{position:absolute;top:8px;right:8px;width:18px;height:18px;border-radius:50%;background:#dce5e8;border:1px solid #c3d0d5}.box-card.owned .owned-dot{background:#1e7c64;border-color:#1e7c64;box-shadow:inset 0 0 0 4px white}@media(max-width:1180px){.controls,.box-controls{grid-template-columns:1fr 1fr 1fr}.workspace{grid-template-columns:1fr}.side-panel{max-height:none}.chart-wrap,#chart{height:600px}.side-section.changelog{flex-basis:auto}}@media(max-width:720px){.app-shell{padding:14px 12px}.topbar{flex-direction:column}.controls,.box-controls{grid-template-columns:1fr 1fr}.panel-head{flex-direction:column}.summary-badges{justify-content:flex-start}.chart-wrap,#chart{height:560px}.workspace{gap:10px}.side-panel{padding:10px}.box-grid{grid-template-columns:repeat(auto-fill,minmax(92px,1fr));padding:10px}}"""


_BANNER_CSS = """.banner-controls{display:grid;grid-template-columns:minmax(220px,.5fr) minmax(280px,1fr);gap:10px;align-items:end;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.banner-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:#132d34;color:white;border-radius:8px;padding:16px 18px;margin-bottom:14px}.banner-hero h2{margin:0 0 4px;font-size:21px}.banner-hero p{margin:0;color:#c9d8dc;font-size:12px;line-height:1.5}.banner-hero .summary-badges span{background:#183a44;border-color:#315b66;color:#eef6f8}.banner-grid{display:flex;flex-direction:column;gap:14px}.banner-section{background:white;border:1px solid #d8e1e5;border-radius:8px}.banner-section-head{display:flex;justify-content:space-between;gap:10px;padding:14px 16px;border-bottom:1px solid #edf1f3}.banner-section-head h3{margin:0 0 4px;font-size:17px}.banner-section-head p{margin:0;color:#657780;font-size:12px}.banner-section-head a{color:#174c5a;font-size:12px;text-decoration:none;font-weight:700}.banner-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(368px,1fr));gap:12px;padding:14px}.banner-card{display:grid;grid-template-columns:116px minmax(0,1fr);gap:12px;border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;padding:12px;min-height:226px}.banner-card.current{border-left:4px solid #2f7b69}.banner-card.next{border-left:4px solid #266bb0}.banner-card.recent{border-left:4px solid #7d6b2b}.banner-card.owned{background:#f3fbf7}.banner-art{position:relative;border-radius:8px;background:#e8eef1;min-height:144px;display:grid;place-items:center;overflow:hidden}.banner-art img{width:104px;height:104px;border-radius:50%;object-fit:cover;filter:drop-shadow(0 8px 16px rgba(0,0,0,.18))}.avatar-fallback{width:92px;height:92px;border-radius:50%;display:grid;place-items:center;background:#174c5a;color:white;font-weight:800}.mini-owned{position:absolute;left:8px;right:8px;bottom:8px;border:1px solid #c6d2d7;background:white;border-radius:6px;padding:5px 7px;cursor:pointer}.banner-kicker{font-size:11px;color:#607079;font-weight:800}.banner-card h3{margin:3px 0 4px;font-size:18px}.banner-meta{margin:0 0 8px;color:#526971;font-size:12px}.spark{width:100%;height:54px;background:white;border:1px solid #e4ebee;border-radius:6px}.spark-line{fill:none;stroke:#174c5a;stroke-width:2.4}.spark-axis{stroke:#d8e1e5}.spark-dot{fill:#2f7b69;stroke:white;stroke-width:1.5}.spark-empty{fill:#657780;font-size:12px}.banner-facts p{margin:6px 0;color:#2e4149;font-size:12px;line-height:1.45}.banner-relations{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.banner-relations span{border:1px solid #d6e1e5;background:white;border-radius:999px;padding:3px 7px;color:#39505a;font-size:11px}.banner-relations span.owned{border-color:#2f7b69;background:#edf8f2;color:#1f604f}@media(max-width:900px){.banner-controls{grid-template-columns:1fr}.banner-card-grid{grid-template-columns:1fr}}@media(max-width:720px){.banner-card{grid-template-columns:92px minmax(0,1fr);min-height:210px}.banner-art img{width:78px;height:78px}}"""


_BUILD_CSS = """.build-editor{display:grid;grid-template-columns:minmax(220px,.8fr) minmax(0,1.4fr) auto;gap:14px;align-items:center;background:#fff;border:1px solid #d8e1e5;border-radius:8px;padding:12px 14px;margin-bottom:14px}.build-editor-head{display:flex;gap:10px;align-items:center;min-width:0}.build-editor-head img{width:46px;height:46px;border-radius:50%;background:#e7ecef;object-fit:cover}.build-editor h2{margin:0 0 4px;font-size:16px}.build-editor p{margin:0;color:#637780;font-size:12px}.build-fields{display:grid;grid-template-columns:repeat(6,minmax(82px,1fr));gap:8px}.build-fields label{color:#607079;font-size:12px}.build-fields select{display:block;width:100%;height:34px;margin-top:5px;border:1px solid #c8d4d9;border-radius:6px;background:#fff;padding:6px 8px}.build-actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.build-actions span{font-size:12px;color:#39505a;border:1px solid #d6e1e5;background:#f8fafb;border-radius:999px;padding:4px 8px}.build-actions button,.build-button{border:1px solid #bac7cc;background:white;color:#1d3942;border-radius:6px;padding:7px 9px;cursor:pointer}.build-actions button:hover,.build-button:hover{border-color:#36606a;background:#f8fbfb}.build-button{position:absolute;left:8px;top:8px;font-size:11px;padding:3px 6px}.box-card.selected{outline:2px solid #174c5a;outline-offset:2px}.box-build{margin-top:5px;color:#315861!important;font-weight:700}@media(max-width:1180px){.build-editor{grid-template-columns:1fr}.build-actions{justify-content:flex-start}.build-fields{grid-template-columns:repeat(3,minmax(86px,1fr))}}@media(max-width:720px){.build-fields{grid-template-columns:1fr 1fr}.build-editor{padding:10px}}"""


_RECOMMENDER_CSS = """.rec-controls{display:grid;grid-template-columns:1fr .62fr 1.5fr .55fr .58fr .5fr 1fr;gap:10px;align-items:end;background:#fff;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.phase-mechanics{display:grid;grid-template-columns:minmax(220px,.62fr) minmax(0,1fr) auto;gap:14px;align-items:center;background:#fff;border:1px solid #d8e1e5;border-radius:8px;padding:12px 14px;margin-bottom:14px}.phase-mechanics h2{margin:0 0 4px;font-size:16px}.phase-mechanics p{margin:0;color:#42565f;font-size:12px;line-height:1.5}.phase-mechanics>p{color:#243b44}.phase-mechanics a{font-size:12px;color:#174c5a;text-decoration:none;border:1px solid #c8d4d9;border-radius:6px;padding:6px 8px;background:#f8fbfb;white-space:nowrap}.phase-mechanics a.hidden-link{display:none}.rec-layout{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:14px}.rec-panel,.rec-slate{background:white;border:1px solid #d8e1e5;border-radius:8px;min-height:660px}.rec-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px;padding:14px}.rec-card{border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;padding:12px;display:flex;flex-direction:column;gap:10px}.rec-card:hover{border-color:#86a6af;background:#f7fbfb}.rec-card.risky{border-color:#d09b3d;background:#fffaf1}.rec-card-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.rec-card h3{margin:0;font-size:15px;line-height:1.25}.rec-card .rec-meta,.rec-note{color:#657780;font-size:12px;line-height:1.4}.rec-risk-note{border:1px solid #e4bd72;background:#fff8e8;border-radius:6px;padding:7px 8px;color:#724d00;font-size:12px;line-height:1.45}.rec-score{min-width:64px;text-align:right}.rec-score strong{display:block;font-size:20px;color:#174c5a}.rec-score span{font-size:11px;color:#6b7c84}.rec-team{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.rec-member{position:relative;border:1px solid #d8e1e5;background:#fff;border-radius:7px;padding:8px 6px;text-align:center;min-width:0}.rec-member.owned{border-color:#2f7b69;background:#f3fbf7}.rec-member.missing{border-color:#d1a24c;background:#fffaf1}.rec-member.risky{border-color:#c88724;box-shadow:inset 0 0 0 1px #c88724}.rec-member img{width:46px;height:46px;border-radius:50%;object-fit:cover;background:#e7ecef}.rec-member.missing img{filter:grayscale(1);opacity:.42}.rec-member .name{margin-top:5px;font-size:11px;font-weight:700;line-height:1.2;min-height:26px;display:flex;align-items:center;justify-content:center}.rec-member .meta{font-size:10px;color:#637780;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rec-tags{display:flex;gap:6px;flex-wrap:wrap}.rec-tags span{border:1px solid #d6e1e5;background:white;border-radius:999px;padding:3px 7px;color:#39505a;font-size:11px}.rec-tags span.warn{border-color:#dfb86a;background:#fff8e8;color:#7a5200}.rec-tags span.danger{border-color:#cb7a33;background:#fff1e6;color:#7a3300}.rec-subs{display:flex;flex-direction:column;gap:5px}.rec-subline{font-size:12px;color:#41545c;display:flex;gap:6px;align-items:center;flex-wrap:wrap}.rec-subline b{color:#8a5d00;font-weight:700}.rec-mini{display:inline-flex;gap:4px;align-items:center;border:1px solid #d8e1e5;border-radius:999px;background:white;padding:2px 6px}.rec-mini img{width:18px;height:18px;border-radius:50%;object-fit:cover}.rec-slate-list{padding:14px;display:flex;flex-direction:column;gap:10px}.rec-slate-card{border:1px solid #d8e1e5;border-radius:8px;background:#fbfcfd;padding:10px}.rec-slate-card.risky{border-color:#d09b3d;background:#fffaf1}.rec-slate-card h3{margin:0 0 8px;font-size:14px}.rec-slate-team{display:flex;gap:6px;flex-wrap:wrap}.rec-slate-team img{width:34px;height:34px;border-radius:50%;background:#e7ecef}.rec-slate-team img.missing{filter:grayscale(1);opacity:.38}.rec-slate-team img.risky{outline:2px solid #c88724}.rec-empty{padding:28px;color:#657780;text-align:center}@media(max-width:1180px){.rec-controls{grid-template-columns:1fr 1fr 1fr}.phase-mechanics,.rec-layout{grid-template-columns:1fr}}@media(max-width:720px){.rec-controls{grid-template-columns:1fr 1fr}.rec-list{grid-template-columns:1fr;padding:10px}.rec-team{grid-template-columns:repeat(2,minmax(0,1fr))}}"""


_APP_JS = r"""const MODES=[['moc','混沌回忆'],['pf','虚构叙事'],['as','末日幻影'],['aa','异相仲裁']];
const VIEWS=[['trend','趋势'],['latest','排行'],['heatmap','热力']];
const ROLES=[['all','全部'],['main_dps','主C'],['sub_dps','副C'],['support','辅助'],['sustain','生存位'],['unknown','未分类']];
const TIERS=['T0','T0.5','T1','T1.5','T2','未分档'];
const TIER_RANK={'T0':0,'T0.5':0.5,'T1':1,'T1.5':1.5,'T2':2,'T3':3,'T4':4,'T5':5};
const CORE_ROLES=new Set(['main_dps','sub_dps']);
const BUILD_LEVELS=[0,20,40,50,60,70,75,80];
const BUILD_EIDOLONS=[['unset','未录入'],[0,'0魂'],[1,'1魂'],[2,'2魂'],[3,'3魂'],[4,'4魂'],[5,'5魂'],[6,'6魂']];
const BUILD_SIGNATURES=[['unset','未录入'],['no','无专武'],['yes','有专武']];
const BUILD_TRACES=[['unset','未录入',0],['low','低',0.32],['mid','中',0.58],['high','高',0.82],['max','满',1]];
const BUILD_RELICS=[['unset','未录入',0],['none','未刷',0.12],['ok','可用',0.58],['good','成型',0.82],['great','毕业',1]];
const ELEMENT_ORDER=['物理','火','冰','雷','风','量子','虚数'];
const PATH_ORDER=['毁灭','巡猎','智识','同谐','虚无','存护','丰饶','记忆','欢愉'];
const COLORS=['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#be123c','#4f46e5','#65a30d','#a16207','#0f766e','#7c3aed','#db2777','#475569'];
const BOX_KEY='hsr_endgame_box_v1';
const REC_KEY='hsr_endgame_recommender_v1';
let DATA=null;
let state={page:'analysis',mode:'moc',view:'trend',role:'main_dps',tiers:new Set(TIERS),metric:'app_rate',limit:'12',search:'',avatars:true,focus:null,hover:null};
let box={owned:new Set(),builds:{},buildSlug:'',element:'all',path:'all',role:'all',rarity:'all',status:'all',search:'',saveStatus:'浏览器缓存'};
let rec={mode:'moc',scope:'',elements:{},gap:'1',riskMode:'warn',limit:'8',search:''};
let banner={phase:'all',search:''};
let boxSaveTimer=null;

const $=id=>document.getElementById(id);
const ns='http://www.w3.org/2000/svg';
function number(v){const n=Number(v);return Number.isFinite(n)?n:null}
function pct(v){const n=number(v);return n==null?'':`${n.toFixed(2)}%`}
function fmtMetric(v){const n=number(v);if(n==null)return '';return state.metric==='app_rate'?`${n.toFixed(2)}%`:n.toFixed(2)}
function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}

fetch('./data.json')
  .then(r=>r.json())
  .then(data=>{DATA=data;loadBox();loadRecSettings();init();render();syncBoxFromServer();})
  .catch(err=>{document.body.innerHTML=`<main class="app-shell"><h1>数据加载失败</h1><p>${esc(err.message)}</p></main>`;});

function init(){
  $('metaLine').textContent=`Prydwen T榜更新：${DATA.meta.tierUpdatedAt||DATA.meta.tierUpdatedDate||'未知'} · 本地数据生成：${DATA.meta.generatedAt||'未知'} · Box 自动保存`;
  makeButtons('appTabs',[['analysis','趋势分析'],['banner','卡池情报'],['box','我的Box'],['recommender','组队推荐']],state.page,v=>{state.page=v;render();});
  makeButtons('modeControl',MODES,state.mode,v=>{state.mode=v;state.focus=null;state.hover=null;render();});
  makeButtons('viewControl',VIEWS,state.view,v=>{state.view=v;state.focus=null;state.hover=null;render();});
  makeButtons('roleControl',ROLES,state.role,v=>{state.role=v;state.focus=null;state.hover=null;render();});
  const tierBox=$('tierControl');
  TIERS.forEach(t=>{const b=document.createElement('button');b.type='button';b.textContent=t;b.className='active';b.title=`显示或隐藏 ${t}`;b.onclick=()=>{state.tiers.has(t)?state.tiers.delete(t):state.tiers.add(t);b.classList.toggle('active',state.tiers.has(t));state.focus=null;state.hover=null;render();};tierBox.appendChild(b);});
  $('limitSelect').onchange=e=>{state.limit=e.target.value;render();};
  $('metricSelect').onchange=e=>{state.metric=e.target.value;render();};
  $('searchInput').oninput=e=>{state.search=e.target.value.trim().toLowerCase();state.focus=null;state.hover=null;render();};
  $('avatarToggle').onchange=e=>{state.avatars=e.target.checked;render();};
  $('resetBtn').onclick=resetCurrentPage;
  initBannerControls();
  initBoxControls();
  initRecommenderControls();
}

function initBannerControls(){
  makeButtons('bannerPhaseControl',[['all','全部'],['current','当期UP'],['next','后续卡池'],['recent','历史参考']],banner.phase,v=>{banner.phase=v;renderBanner();});
  $('bannerSearchInput').oninput=e=>{banner.search=e.target.value.trim().toLowerCase();renderBanner();};
}

function initBoxControls(){
  const elements=['all',...ELEMENT_ORDER.filter(x=>DATA.rosterRows.some(r=>r.element_cn===x))];
  const paths=['all',...PATH_ORDER.filter(x=>DATA.rosterRows.some(r=>r.path_cn===x))];
  makeButtons('boxElementControl',elements.map(x=>[x,x==='all'?'全部':x]),box.element,v=>{box.element=v;renderBox();});
  makeButtons('boxPathControl',paths.map(x=>[x,x==='all'?'全部':x]),box.path,v=>{box.path=v;renderBox();});
  makeButtons('boxRoleControl',ROLES.map(([v,l])=>[v,l]),box.role,v=>{box.role=v;renderBox();});
  $('boxRaritySelect').onchange=e=>{box.rarity=e.target.value;renderBox();};
  $('boxOwnedSelect').onchange=e=>{box.status=e.target.value;renderBox();};
  $('boxSearchInput').oninput=e=>{box.search=e.target.value.trim().toLowerCase();renderBox();};
  $('boxExportBtn').onclick=exportBox;
  $('boxImportBtn').onclick=()=>$('boxImportInput').click();
  $('boxImportInput').onchange=importBox;
  $('boxMarkVisibleBtn').onclick=()=>markVisible(true);
  $('boxClearVisibleBtn').onclick=()=>markVisible(false);
  $('boxBuildVisibleBtn').onclick=()=>setVisibleBuild('max');
  $('boxClearBuildVisibleBtn').onclick=()=>setVisibleBuild('clear');
  initBuildControls();
}

function initBuildControls(){
  $('buildLevelSelect').innerHTML=BUILD_LEVELS.map(v=>`<option value="${v}">${v?`${v}级`:'未录入'}</option>`).join('');
  $('buildLcSelect').innerHTML=BUILD_LEVELS.map(v=>`<option value="${v}">${v?`${v}级`:'未录入'}</option>`).join('');
  $('buildEidolonSelect').innerHTML=BUILD_EIDOLONS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildSignatureSelect').innerHTML=BUILD_SIGNATURES.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildTraceSelect').innerHTML=BUILD_TRACES.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildRelicSelect').innerHTML=BUILD_RELICS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');
  $('buildLevelSelect').onchange=e=>updateBuildField('level',Number(e.target.value)||0);
  $('buildLcSelect').onchange=e=>updateBuildField('lc',Number(e.target.value)||0);
  $('buildEidolonSelect').onchange=e=>updateBuildField('eidolon',e.target.value==='unset'?'unset':Number(e.target.value));
  $('buildSignatureSelect').onchange=e=>updateBuildField('signature',e.target.value);
  $('buildTraceSelect').onchange=e=>updateBuildField('traces',e.target.value);
  $('buildRelicSelect').onchange=e=>updateBuildField('relics',e.target.value);
  $('buildMaxBtn').onclick=()=>setBuildPreset('max');
  $('buildClearBtn').onclick=()=>setBuildPreset('clear');
}

function initRecommenderControls(){
  const modes=MODES.filter(([mode])=>DATA.teamTemplates?.some(t=>t.mode===mode));
  if(modes.length&&!modes.some(([mode])=>mode===rec.mode))rec.mode=modes[0][0];
  makeButtons('recModeControl',modes.length?modes:MODES,rec.mode,v=>{rec.mode=v;ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();});
  $('recScopeSelect').onchange=e=>{rec.scope=e.target.value;saveRecSettings();syncRecControls();renderRecommender();};
  const elementBox=$('recElementControl');
  elementBox.innerHTML='';
  ELEMENT_ORDER.forEach(element=>{const b=document.createElement('button');b.type='button';b.textContent=element;b.title=`${element} 推荐属性`;b.onclick=()=>{const set=recElementSet();set.has(element)?set.delete(element):set.add(element);setRecElementSet(set);saveRecSettings();syncRecControls();renderRecommender();};elementBox.appendChild(b);});
  $('recGapSelect').onchange=e=>{rec.gap=e.target.value;saveRecSettings();renderRecommender();};
  $('recRiskSelect').onchange=e=>{rec.riskMode=e.target.value;saveRecSettings();renderRecommender();};
  $('recLimitSelect').onchange=e=>{rec.limit=e.target.value;saveRecSettings();renderRecommender();};
  $('recSearchInput').oninput=e=>{rec.search=e.target.value.trim().toLowerCase();saveRecSettings();renderRecommender();};
  ensureRecScope();
  syncRecControls();
}

function makeButtons(id,items,current,onClick){
  const boxEl=$(id);boxEl.innerHTML='';
  items.forEach(([value,label])=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.dataset.value=value;b.className=value===current?'active':'';b.title=label;b.onclick=()=>{[...boxEl.children].forEach(x=>x.classList.remove('active'));b.classList.add('active');onClick(value);};boxEl.appendChild(b);});
}

function resetCurrentPage(){
  if(state.page==='banner'){
    banner={phase:'all',search:''};
    [...$('bannerPhaseControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===banner.phase));
    $('bannerSearchInput').value='';
    renderBanner();return;
  }
  if(state.page==='recommender'){
    rec={...rec,mode:'moc',scope:'',gap:'1',riskMode:'warn',limit:'8',search:''};
    ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();return;
  }
  if(state.page==='box'){
    box={...box,buildSlug:'',element:'all',path:'all',role:'all',rarity:'all',status:'all',search:''};
    syncBoxControls();renderBox();return;
  }
  state={...state,mode:'moc',view:'trend',role:'main_dps',tiers:new Set(TIERS),metric:'app_rate',limit:'12',search:'',avatars:true,focus:null,hover:null};
  syncAnalysisControls();renderAnalysis();
}

function syncAnalysisControls(){
  [...$('modeControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.mode));
  [...$('viewControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.view));
  [...$('roleControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.role));
  [...$('tierControl').children].forEach(b=>b.classList.toggle('active',state.tiers.has(b.textContent)));
  $('limitSelect').value=state.limit;$('metricSelect').value=state.metric;$('searchInput').value=state.search;$('avatarToggle').checked=state.avatars;
}

function syncBoxControls(){
  [...$('boxElementControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===box.element));
  [...$('boxPathControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===box.path));
  [...$('boxRoleControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===box.role));
  $('boxRaritySelect').value=box.rarity;$('boxOwnedSelect').value=box.status;$('boxSearchInput').value=box.search;
}

function syncRecControls(){
  [...$('recModeControl').children].forEach(b=>b.classList.toggle('active',b.dataset.value===rec.mode));
  const options=recScopeOptions(rec.mode);
  const select=$('recScopeSelect');
  select.innerHTML=options.map(o=>`<option value="${esc(o.key)}">${esc(o.label)}</option>`).join('');
  if(!options.some(o=>o.key===rec.scope))rec.scope=options[0]?.key||'';
  select.value=rec.scope;
  const selected=recElementSet();
  [...$('recElementControl').children].forEach(b=>b.classList.toggle('active',selected.has(b.textContent)));
  $('recGapSelect').value=rec.gap;$('recRiskSelect').value=rec.riskMode||'warn';$('recLimitSelect').value=rec.limit;$('recSearchInput').value=rec.search;
}

function render(){
  $('analysisView').classList.toggle('hidden',state.page!=='analysis');
  $('bannerView').classList.toggle('hidden',state.page!=='banner');
  $('boxView').classList.toggle('hidden',state.page!=='box');
  $('recommenderView').classList.toggle('hidden',state.page!=='recommender');
  [...$('appTabs').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.page));
  if(state.page==='banner')renderBanner();else if(state.page==='box')renderBox();else if(state.page==='recommender')renderRecommender();else renderAnalysis();
}

function sourceRows(){
  return DATA.usageRows&&DATA.usageRows.length?DATA.usageRows:DATA.trendRows;
}

function filteredRows(){
  const q=state.search;
  const rows=sourceRows().filter(r=>
    r.tier_mode===state.mode &&
    (state.role==='all'||r.role_group===state.role) &&
    state.tiers.has(r.tier||'未分档') &&
    (!q || [r.character_name_cn,r.character_name_en,r.character_slug,r.tags,r.tier,r.element_cn,r.path_cn].some(x=>String(x||'').toLowerCase().includes(q)))
  );
  const seen=new Set();
  return rows.filter(r=>{
    const key=`${r.tier_mode}|${r.collect_date}|${r.character_slug}`;
    if(state.role==='all'&&seen.has(key))return false;
    seen.add(key);return true;
  });
}

function groupSeries(rows){
  const map=new Map();
  rows.forEach(r=>{if(!map.has(r.character_slug))map.set(r.character_slug,[]);map.get(r.character_slug).push(r);});
  const list=[...map.entries()].map(([slug,points])=>{
    points.sort((a,b)=>String(a.collect_date).localeCompare(String(b.collect_date)));
    const latest=points[points.length-1];
    return{slug,points,latest,max:Math.max(...points.map(p=>number(p[state.metric])||0),0)};
  });
  list.sort((a,b)=>(number(b.latest.app_rate)||0)-(number(a.latest.app_rate)||0)||(number(b.latest.rating)||0)-(number(a.latest.rating)||0)||a.slug.localeCompare(b.slug));
  return list;
}

function limitSeries(series){return state.limit==='all'?series:series.slice(0,Number(state.limit)||12)}

function renderAnalysis(){
  hideTooltip();
  const rows=filteredRows();
  const allSeries=groupSeries(rows);
  const series=limitSeries(allSeries);
  const modeLabel=MODES.find(x=>x[0]===state.mode)?.[1]||state.mode;
  const roleLabel=ROLES.find(x=>x[0]===state.role)?.[1]||state.role;
  const viewLabel=VIEWS.find(x=>x[0]===state.view)?.[1]||state.view;
  $('chartTitle').textContent=`${modeLabel} · ${roleLabel} · ${viewLabel}`;
  const aaNote=state.mode==='aa'?' · AA 为全 Boss / 未拆分本地数据':'';
  $('chartSubtitle').textContent=`展示 ${series.length}/${allSeries.length} 个角色，${rows.length} 个采样点${aaNote}`;
  $('summaryBadges').innerHTML=[`${[...state.tiers].join(' / ')||'未选T档'}`,state.metric==='app_rate'?'出场率':'平均值',state.limit==='all'?'全量':`Top ${state.limit}`].map(x=>`<span>${esc(x)}</span>`).join('');
  if(state.view==='latest')renderLatest(series);else if(state.view==='heatmap')renderHeatmap(series);else renderTrend(series,rows);
  renderCharacters(series);
  renderChangelog(series.length?series:allSeries);
}

function chartBox(){const svg=$('chart');svg.innerHTML='';const rect=svg.getBoundingClientRect();const width=Math.max(760,Math.round(rect.width||1000));const height=Math.max(560,Math.round(rect.height||620));svg.setAttribute('viewBox',`0 0 ${width} ${height}`);return{svg,width,height}}
function add(svg,tag,attrs,parent=svg){const el=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));parent.appendChild(el);return el}
function renderEmpty(svg,width,height){add(svg,'text',{x:width/2,y:height/2,'text-anchor':'middle',class:'empty-state'}).textContent='当前筛选没有数据'}

function renderTrend(series,rows){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const margin={l:62,r:28,t:34,b:54};const cw=width-margin.l-margin.r,ch=height-margin.t-margin.b;
  const dates=[...new Set(rows.map(r=>r.collect_date))].sort();const metric=state.metric;
  const values=rows.map(r=>number(r[metric])).filter(v=>v!=null&&v>=0&&(metric!=='avg_round'||v<99));const max=Math.max(10,...values)*1.14;
  const x=d=>margin.l+(dates.length<=1?cw/2:cw*dates.indexOf(d)/(dates.length-1));const y=v=>margin.t+ch-ch*(Math.min(v,max))/max;
  drawAxes(svg,margin,cw,ch,max,dates,x,y,metric);const defs=add(svg,'defs',{});
  series.forEach((s,idx)=>{const color=COLORS[idx%COLORS.length];const pts=s.points.map(p=>[x(p.collect_date),y(number(p[metric])||0),p]).filter(p=>Number.isFinite(p[1]));if(!pts.length)return;const path=pts.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');const line=add(svg,'path',{d:path,stroke:color,class:`series-line ${dimClass(s.slug)}`});line.dataset.slug=s.slug;const hit=add(svg,'path',{d:path,class:'series-hit'});hit.dataset.slug=s.slug;bindHover(hit,s.latest,s.slug);pts.forEach(([xx,yy,p],pi)=>drawPoint(svg,defs,xx,yy,p,s.slug,color,idx,pi,11));});
}

function drawAxes(svg,margin,cw,ch,max,dates,x,y,metric){
  const label=metric==='app_rate'?'出场率 %':'平均值';
  for(let i=0;i<=5;i++){const val=max*i/5,yy=y(val);add(svg,'line',{x1:margin.l,y1:yy,x2:margin.l+cw,y2:yy,class:'grid'});add(svg,'text',{x:margin.l-10,y:yy+4,'text-anchor':'end',class:'axis-label'}).textContent=val.toFixed(0);}
  add(svg,'line',{x1:margin.l,y1:margin.t,x2:margin.l,y2:margin.t+ch,class:'axis-line'});add(svg,'line',{x1:margin.l,y1:margin.t+ch,x2:margin.l+cw,y2:margin.t+ch,class:'axis-line'});add(svg,'text',{x:margin.l,y:22,class:'axis-label'}).textContent=label;
  dates.forEach((d,i)=>{if(dates.length>14&&i%2===1)return;add(svg,'text',{x:x(d),y:margin.t+ch+24,'text-anchor':'middle',class:'axis-label'}).textContent=String(d).slice(5);});
}

function drawPoint(svg,defs,x,y,row,slug,color,seriesIndex,pointIndex,radius){
  if(state.avatars&&row.icon_url){const clipId=`clip-${seriesIndex}-${pointIndex}-${Math.round(x)}-${Math.round(y)}`;const clip=add(svg,'clipPath',{id:clipId},defs);add(svg,'circle',{cx:x,cy:y,r:radius},clip);const img=add(svg,'image',{href:row.icon_url,x:x-radius,y:y-radius,width:radius*2,height:radius*2,'clip-path':`url(#${clipId})`,class:`avatar-node ${dimClass(slug)}`});img.dataset.slug=slug;add(svg,'circle',{cx:x,cy:y,r:radius,fill:'none',stroke:color,class:`avatar-ring ${dimClass(slug)}`});bindHover(img,row,slug);img.addEventListener('click',()=>toggleFocus(slug));}
  else{const c=add(svg,'circle',{cx:x,cy:y,r:4.6,fill:color,class:`point-node ${dimClass(slug)}`});c.dataset.slug=slug;bindHover(c,row,slug);c.addEventListener('click',()=>toggleFocus(slug));}
}

function renderLatest(series){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const margin={l:158,r:48,t:36,b:38};const rowH=Math.max(34,Math.min(48,(height-margin.t-margin.b)/Math.max(series.length,1)));const chartH=rowH*series.length;const metric=state.metric;
  const values=series.map(s=>number(s.latest[metric])).filter(v=>v!=null&&v>=0&&(metric!=='avg_round'||v<99));const max=Math.max(10,...values)*1.12;const x=v=>margin.l+(width-margin.l-margin.r)*Math.min(v,max)/max;
  add(svg,'text',{x:margin.l,y:22,class:'axis-label'}).textContent=metric==='app_rate'?'最近一期出场率 %':'最近一期平均值';
  for(let i=0;i<=4;i++){const val=max*i/4,xx=x(val);add(svg,'line',{x1:xx,y1:margin.t-10,x2:xx,y2:margin.t+chartH,class:'grid'});add(svg,'text',{x:xx,y:margin.t+chartH+22,'text-anchor':'middle',class:'axis-label'}).textContent=val.toFixed(0);}
  const defs=add(svg,'defs',{});series.forEach((s,idx)=>{const row=s.latest;const color=COLORS[idx%COLORS.length];const yy=margin.t+idx*rowH+rowH/2;const val=number(row[metric])||0;const xx=x(val);add(svg,'text',{x:18,y:yy-2,class:`rank-label ${dimClass(s.slug)}`}).textContent=`${idx+1}. ${row.character_name_cn||row.character_name_en||s.slug}`;add(svg,'text',{x:18,y:yy+14,class:`muted-label ${dimClass(s.slug)}`}).textContent=`${row.tier} · ${row.tags||row.path_cn||row.character_name_en||''}`;const bar=add(svg,'line',{x1:margin.l,y1:yy,x2:xx,y2:yy,stroke:color,'stroke-width':8,'stroke-linecap':'round',class:`bar-line ${dimClass(s.slug)}`});bar.dataset.slug=s.slug;bindHover(bar,row,s.slug);drawPoint(svg,defs,xx,yy,row,s.slug,color,idx,0,14);add(svg,'text',{x:Math.min(width-42,xx+18),y:yy+4,class:'axis-label'}).textContent=fmtMetric(val);});
}

function renderHeatmap(series){
  const {svg,width,height}=chartBox();if(!series.length){renderEmpty(svg,width,height);return;}
  const rows=series.flatMap(s=>s.points);const dates=[...new Set(rows.map(r=>r.collect_date))].sort();const metric=state.metric;const margin={l:156,r:24,t:42,b:36};const cellGap=4;const cw=(width-margin.l-margin.r-(dates.length-1)*cellGap)/Math.max(dates.length,1);const rowH=Math.max(28,Math.min(42,(height-margin.t-margin.b)/Math.max(series.length,1)));const values=rows.map(r=>number(r[metric])).filter(v=>v!=null&&v>=0&&(metric!=='avg_round'||v<99));const max=Math.max(10,...values);const defs=add(svg,'defs',{});
  dates.forEach((d,i)=>add(svg,'text',{x:margin.l+i*(cw+cellGap)+cw/2,y:24,'text-anchor':'middle',class:'heat-head'}).textContent=String(d).slice(5));
  series.forEach((s,idx)=>{const rowY=margin.t+idx*rowH;const latest=s.latest;add(svg,'text',{x:48,y:rowY+rowH/2+4,class:`heat-name ${dimClass(s.slug)}`}).textContent=latest.character_name_cn||latest.character_name_en||s.slug;drawMiniAvatar(svg,defs,24,rowY+rowH/2,latest,s.slug,idx);const byDate=new Map(s.points.map(p=>[p.collect_date,p]));dates.forEach((d,j)=>{const p=byDate.get(d);const val=number(p?.[metric])||0;const intensity=Math.max(.08,Math.min(1,val/max));const fill=metric==='app_rate'?`rgba(23,76,90,${intensity})`:`rgba(37,99,235,${intensity})`;const rect=add(svg,'rect',{x:margin.l+j*(cw+cellGap),y:rowY+5,width:Math.max(10,cw),height:rowH-10,fill,class:`heat-cell ${dimClass(s.slug)}`});rect.dataset.slug=s.slug;if(p)bindHover(rect,p,s.slug);rect.addEventListener('click',()=>toggleFocus(s.slug));});});
}

function drawMiniAvatar(svg,defs,x,y,row,slug,index){if(!row.icon_url)return;const clipId=`mini-${index}-${slug}`;const clip=add(svg,'clipPath',{id:clipId},defs);add(svg,'circle',{cx:x,cy:y,r:14},clip);const img=add(svg,'image',{href:row.icon_url,x:x-14,y:y-14,width:28,height:28,'clip-path':`url(#${clipId})`,class:`avatar-node ${dimClass(slug)}`});img.dataset.slug=slug;bindHover(img,row,slug);img.addEventListener('click',()=>toggleFocus(slug));}
function activeSlug(){return state.focus||state.hover}
function dimClass(slug){const active=activeSlug();return active&&active!==slug?'dim':state.focus===slug?'focused':''}
function toggleFocus(slug){state.focus=state.focus===slug?null:slug;state.hover=null;renderAnalysis();}
function setHover(slug){state.hover=slug;updateFocusClasses();}
function clearHover(){state.hover=null;updateFocusClasses();hideTooltip();}
function updateFocusClasses(){const active=activeSlug();document.querySelectorAll('[data-slug]').forEach(el=>{const slug=el.dataset.slug;el.classList.toggle('dim',Boolean(active&&active!==slug));el.classList.toggle('focused',Boolean(state.focus&&state.focus===slug));});document.querySelectorAll('.character-card').forEach(el=>{const slug=el.dataset.slug;el.classList.toggle('dim',Boolean(active&&active!==slug));el.classList.toggle('active',Boolean(state.focus&&state.focus===slug));});}
function bindHover(el,row,slug){el.addEventListener('mouseenter',evt=>{setHover(slug);showTooltip(evt,row);});el.addEventListener('mousemove',moveTooltip);el.addEventListener('mouseleave',clearHover);}

function showTooltip(evt,row){
  const tt=$('tooltip');tt.hidden=false;
  tt.innerHTML=`<div class="tooltip-head"><img src="${esc(row.icon_url)}" alt=""><div><strong>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</strong><span>${esc(row.character_name_en)} · ${esc(row.character_slug)}</span></div></div><div class="tooltip-grid"><b>模式</b><div>${esc(row.tier_mode_cn)}${row.sub_mode_cn?` · ${esc(row.sub_mode_cn)}`:''}</div><b>职能/T档</b><div>${esc(row.role_group_cn)} · ${esc(row.tier)}${row.rating?` (${esc(row.rating)})`:''}</div><b>属性/命途</b><div>${esc(row.element_cn||'')} ${esc(row.path_cn||'')}</div><b>日期/期数</b><div>${esc(row.collect_date)} · ${esc(row.phase_ver)}</div><b>出场率</b><div>${pct(row.app_rate)}</div><b>平均值</b><div>${esc(row.avg_round??'')}</div><b>标签</b><div>${esc(row.tags||'')}</div><b>质量标记</b><div>${esc(row.quality_flag||'')}</div></div>`;
  moveTooltip(evt);
}
function moveTooltip(evt){const target=evt.currentTarget;const tt=target?.closest?.('.box-card')?$('boxTooltip'):(target?.closest?.('.rec-card')||target?.closest?.('.rec-slate-card'))?$('recTooltip'):$('tooltip');const pad=14;let x=evt.clientX+16,y=evt.clientY+16;const rect=tt.getBoundingClientRect();if(x+rect.width+pad>window.innerWidth)x=evt.clientX-rect.width-16;if(y+rect.height+pad>window.innerHeight)y=evt.clientY-rect.height-16;tt.style.left=`${Math.max(pad,x)}px`;tt.style.top=`${Math.max(pad,y)}px`;}
function hideTooltip(){$('tooltip').hidden=true;}

function renderCharacters(series){
  const boxEl=$('characterList');boxEl.innerHTML='';
  series.forEach((s,idx)=>{const r=s.latest;const card=document.createElement('button');card.type='button';card.dataset.slug=s.slug;card.className=`character-card ${state.focus===s.slug?'active':''} ${activeSlug()&&activeSlug()!==s.slug?'dim':''}`;card.onclick=()=>toggleFocus(s.slug);card.onmouseenter=e=>{setHover(s.slug);showTooltip(e,r);};card.onmousemove=moveTooltip;card.onmouseleave=clearHover;card.innerHTML=`<img src="${esc(r.icon_url)}" alt=""><div><div class="name">${idx+1}. ${esc(r.character_name_cn||r.character_name_en||s.slug)}</div><div class="meta">${esc(r.character_name_en)} · ${esc(r.tier)} · ${esc(r.element_cn||'')} ${esc(r.path_cn||r.tags||'')}</div></div><div><span class="pill">${esc(r.tier)}</span><div class="rate">${pct(r.app_rate)}</div></div>`;boxEl.appendChild(card);});
}

function renderChangelog(series){const slugs=new Set(series.map(s=>s.slug));const boxEl=$('changelogList');boxEl.innerHTML='';const related=DATA.changelogRows.filter(r=>String(r.character_slugs||'').split(';').some(s=>slugs.has(s)));const rows=(related.length?related:DATA.changelogRows).slice(0,8);rows.forEach(r=>{const item=document.createElement('div');item.className='changelog-item';const text=String(r.text||'');item.innerHTML=`<time>${esc(r.changelog_date)}</time><p>${esc(text).slice(0,420)}${text.length>420?'...':''}</p>`;boxEl.appendChild(item);});}

function bannerRows(){const q=banner.search;return (DATA.bannerRows||[]).filter(r=>(banner.phase==='all'||r.phase_status===banner.phase)&&(!q||[r.character_slug,r.character_name_cn,r.character_name_en,r.banner_role,r.element_cn,r.path_cn,r.role_group_cns,...(r.analysis_tags||[])].some(x=>String(x||'').toLowerCase().includes(q))));}
function renderBanner(){const rows=bannerRows();$('bannerTitle').textContent='卡池情报';$('bannerSubtitle').textContent='这里只做数据提炼：复刻看历史趋势和组队占用，新角色/联动角色只做公开信息与 Box 关系识别。';$('bannerBadges').innerHTML=[`角色 ${rows.length}`,`Box ${box.owned.size}`,'趋势仅供参考'].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('bannerGrid');grid.innerHTML='';if(!rows.length){grid.innerHTML='<div class="rec-empty">暂无卡池情报；可更新 configs/hsr_banner_plan.json</div>';return;}const phases=[...new Map(rows.map(r=>[r.phase_id,{id:r.phase_id,title:r.phase_title,subtitle:r.phase_subtitle,date:r.date_range,source:r.source_label,url:r.source_url,status:r.phase_status}])).values()];phases.forEach(phase=>{const section=document.createElement('section');section.className='banner-section';section.innerHTML=`<div class="banner-section-head"><div><h3>${esc(phase.title||'卡池')}</h3><p>${esc(phase.subtitle||'')} · ${esc(phase.date||'时间待确认')}</p></div>${phase.url?`<a href="${esc(phase.url)}" target="_blank" rel="noreferrer">${esc(phase.source||'来源')}</a>`:''}</div><div class="banner-card-grid"></div>`;const inner=section.querySelector('.banner-card-grid');rows.filter(r=>r.phase_id===phase.id).forEach(row=>inner.appendChild(bannerCard(row)));grid.appendChild(section);});}
function bannerCard(row){const slug=row.character_slug,info={...charInfo(slug),...row},ins=bannerInsight(row);const card=document.createElement('article');card.className=`banner-card ${box.owned.has(slug)?'owned':''} ${row.phase_status}`;const tags=(row.analysis_tags||[]).slice(0,5).map(t=>`<span>${esc(t)}</span>`).join('');const name=info.character_name_cn||info.character_name_en||slug;const roleText=info.role_group_cns||roleCn(info)||'未分类';card.innerHTML=`<div class="banner-art">${info.icon_url?`<img src="${esc(info.icon_url)}" alt="" loading="lazy" decoding="async">`:`<div class="avatar-fallback">${esc(name.slice(0,2))}</div>`}<button class="mini-owned" type="button">${box.owned.has(slug)?'已拥有':'加入Box'}</button></div><div class="banner-body"><div class="banner-kicker">${esc(row.banner_role||row.phase_subtitle||'卡池角色')}</div><h3>${esc(name)}</h3><p class="banner-meta">${esc(info.rarity?`${info.rarity}星`:'-')} · ${esc(info.element_cn||'属性未知')} · ${esc(info.path_cn||'命途未知')} · ${esc(roleText)} · ${esc(ins.tierText)}</p><svg class="spark" viewBox="0 0 220 54">${sparkline(ins.points)}</svg><div class="rec-tags">${tags}</div><div class="banner-facts">${ins.lines.slice(0,4).map(x=>`<p>${esc(x)}</p>`).join('')}</div><div class="banner-relations">${ins.relations.slice(0,6).map(x=>`<span class="${x.owned?'owned':''}">${esc(x.name)}${x.count?` ×${x.count}`:''}</span>`).join('')||'<span>暂无历史组合</span>'}</div></div>`;card.querySelector('.mini-owned').onclick=e=>{e.stopPropagation();box.owned.has(slug)?box.owned.delete(slug):box.owned.add(slug);box.buildSlug=slug;saveBox();renderBanner();};card.addEventListener('mouseenter',e=>showBannerTooltip(e,row,ins));card.addEventListener('mousemove',moveBannerTooltip);card.addEventListener('mouseleave',()=>{$('bannerTooltip').hidden=true;});return card;}
function bannerInsight(row){const slug=row.character_slug,info={...charInfo(slug),...row};const grouped=new Map();(DATA.usageRows||DATA.trendRows||[]).filter(r=>r.character_slug===slug&&(r.sub_mode==='all'||r.sub_mode==='all_bosses'||!r.sub_mode)).forEach(r=>{const key=`${r.tier_mode||r.mode}|${r.collect_date||r.tier_updated_date||''}`;const current=grouped.get(key);if(!current||Number(r.app_rate||0)>Number(current.app_rate||0))grouped.set(key,r);});const usage=[...grouped.values()].sort((a,b)=>String(a.collect_date||a.tier_updated_date).localeCompare(String(b.collect_date||b.tier_updated_date)));const points=usage.map(r=>({date:r.collect_date||r.tier_updated_date,value:number(r.app_rate)||0,mode:r.tier_mode_cn||r.mode_cn||r.tier_mode||r.mode}));const tierText=tierSummaryFor(slug),tierDetails=tierDetailsFor(slug);const teams=(DATA.teamTemplates||[]).filter(t=>(t.chars||[]).includes(slug));const relations=relationRows(slug,teams);const ownedRelation=relations.filter(r=>r.owned).slice(0,4).map(r=>r.name).join('、');const lines=[`T档：Prydwen 按模式分档，${tierText}。`];if(points.length){const latest=points[points.length-1],recent=points.slice(-3),avg=recent.reduce((s,p)=>s+p.value,0)/recent.length,delta=points.length>1?latest.value-points[0].value:0;lines.push(`历史：${points.length} 个样本点，最新 ${latest.value.toFixed(2)}%，近三期均值 ${avg.toFixed(2)}%，首尾变化 ${delta.toFixed(2)}%。`);}else lines.push('历史：本地高难暂无完整样本，不能用趋势替代实测。');if(teams.length){const bestRank=Math.min(...teams.map(t=>number(t.rank)||9999));lines.push(`组队：历史模板 ${teams.length} 条，最好 Rank ${bestRank}，常见队友见下方关系。`);}else lines.push('组队：暂无可回溯历史队伍，等待实测或人工分析。');if(ownedRelation)lines.push(`Box关系：你已有角色中，历史上相关度较高的是 ${ownedRelation}。`);else lines.push('Box关系：暂未发现与你已有 Box 的直接历史组合；需要看属性、命途与队友缺口。');if(row.phase_status==='next'||!points.length)lines.push('未知项：技能组、倍率、光锥价值、实战轴和环境适配仍需外部分析确认。');if(row.focus)lines.push(`关注点：${row.focus}`);return{points,relations,lines,tierText,tierDetails};}
function tierRowsFor(slug){const resolved=canonicalSlug(slug);return (DATA.tierRows||[]).filter(r=>canonicalSlug(r.character_slug)===resolved);}
function bestTierInMode(slug,mode){return tierRowsFor(slug).filter(r=>r.tier_mode===mode).sort((a,b)=>(TIER_RANK[a.tier]??9)-(TIER_RANK[b.tier]??9))[0]||null;}
function tierSummaryFor(slug){const modes=[['moc','混沌'],['pf','虚构'],['as','末日']];const rows=tierRowsFor(slug);if(!rows.length)return '未分档';return modes.map(([mode,label])=>{const row=bestTierInMode(slug,mode);return `${label} ${row?.tier||'未分档'}`;}).join(' / ');}
function tierDetailsFor(slug){const modes=[['moc','混沌回忆'],['pf','虚构叙事'],['as','末日幻影']];const rows=tierRowsFor(slug);if(!rows.length)return 'Prydwen 当前未收录 T 档';return modes.map(([mode,label])=>{const row=bestTierInMode(slug,mode);return `${label}：${row?`${row.role_group_cn||row.role_group||''} ${row.tier}`:'未分档'}`;}).join('；');}
function relationRows(slug,teams){const map=new Map();teams.forEach(t=>(t.chars||[]).forEach(c=>{if(c===slug)return;const item=map.get(c)||{slug:c,name:charName(c),count:0,owned:box.owned.has(c)};item.count++;item.owned=box.owned.has(c);map.set(c,item);}));return [...map.values()].sort((a,b)=>Number(b.owned)-Number(a.owned)||b.count-a.count||a.name.localeCompare(b.name));}
function sparkline(points){if(!points.length)return '<text x="10" y="31" class="spark-empty">暂无趋势</text>';const max=Math.max(1,...points.map(p=>p.value)),xs=points.map((p,i)=>8+i*(204/Math.max(1,points.length-1))),ys=points.map(p=>46-(p.value/max)*36),d=xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');return `<path d="${d}" class="spark-line"/><path d="M8 47H212" class="spark-axis"/>${xs.map((x,i)=>`<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="3.2" class="spark-dot"/>`).join('')}`;}
function showBannerTooltip(evt,row,ins){const tt=$('bannerTooltip');tt.innerHTML=`<div class="tooltip-grid"><b>角色</b><span>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</span><b>阶段</b><span>${esc(row.phase_title||'-')}</span><b>定位</b><span>${esc([row.element_cn,row.path_cn,row.role_group_cns].filter(Boolean).join(' · ')||'未知')}</span><b>模式T档</b><span>${esc(ins.tierDetails||ins.tierText||'未分档')}</span><b>分析输入</b><span>${esc(ins.lines.join('；'))}</span></div>`;tt.hidden=false;moveBannerTooltip(evt);}
function moveBannerTooltip(evt){const tt=$('bannerTooltip');let x=evt.clientX+16,y=evt.clientY+16;const rect=tt.getBoundingClientRect();if(x+rect.width+12>innerWidth)x=evt.clientX-rect.width-16;if(y+rect.height+12>innerHeight)y=evt.clientY-rect.height-16;tt.style.left=`${Math.max(12,x)}px`;tt.style.top=`${Math.max(12,y)}px`;}

function loadRecSettings(){try{const raw=JSON.parse(localStorage.getItem(REC_KEY)||'{}');rec={...rec,...raw,elements:raw.elements||{},riskMode:raw.riskMode||'warn'};}catch{rec={...rec,elements:{},riskMode:'warn'};}ensureRecScope();}
function saveRecSettings(){localStorage.setItem(REC_KEY,JSON.stringify({updatedAt:new Date().toISOString(),mode:rec.mode,scope:rec.scope,gap:rec.gap,riskMode:rec.riskMode||'warn',limit:rec.limit,search:rec.search,elements:rec.elements}));}
function recSettingKey(mode=rec.mode,scope=rec.scope){return `${mode}|${scope||''}`}
function recElementSet(mode=rec.mode,scope=rec.scope){return new Set(rec.elements[recSettingKey(mode,scope)]||[])}
function setRecElementSet(set,mode=rec.mode,scope=rec.scope){rec.elements[recSettingKey(mode,scope)]=[...set].sort((a,b)=>ELEMENT_ORDER.indexOf(a)-ELEMENT_ORDER.indexOf(b));}
function recScopeOptions(mode){
  const map=new Map();
  (DATA.teamTemplates||[]).filter(t=>t.mode===mode).forEach(t=>{if(!map.has(t.scope_key))map.set(t.scope_key,{key:t.scope_key,label:t.scope_label||t.scope_key,order:Number(t.scope_order)||90});});
  return [...map.values()].sort((a,b)=>a.order-b.order||a.label.localeCompare(b.label));
}
function ensureRecScope(){const options=recScopeOptions(rec.mode);if(options.length&&!options.some(o=>o.key===rec.scope))rec.scope=options[0].key;}

function boxAliasMap(){const aliases=new Map();(DATA.rosterRows||[]).forEach(r=>String(r.alias_slugs||r.character_slug||'').split(';').forEach(s=>{if(s)aliases.set(s,r.character_slug);}));return aliases;}
function normalizeEidolon(value){const n=Number(value);return Number.isInteger(n)&&n>=0&&n<=6?n:'unset'}
function normalizeSignature(value){const text=String(value).toLowerCase();if(value===true||['yes','owned','signature','s1','专武'].includes(text))return 'yes';if(value===false||['no','none','s0','无专武'].includes(text))return 'no';return 'unset'}
function normalizeBuild(raw={}){const level=BUILD_LEVELS.includes(Number(raw.level))?Number(raw.level):0;const lc=BUILD_LEVELS.includes(Number(raw.lc??raw.lightConeLevel))?Number(raw.lc??raw.lightConeLevel):0;const traceValues=new Set(BUILD_TRACES.map(x=>x[0]));const relicValues=new Set(BUILD_RELICS.map(x=>x[0]));const eidolon=normalizeEidolon(raw.eidolon??raw.eidolons??raw.cons??raw.constellation);const signature=normalizeSignature(raw.signature??raw.signatureWeapon??raw.hasSignature??raw.s);return{level,lc,eidolon,signature,traces:traceValues.has(raw.traces)?raw.traces:'unset',relics:relicValues.has(raw.relics)?raw.relics:'unset'};}
function buildOptionScore(options,value){return options.find(x=>x[0]===value)?.[2]??0}
function buildCoreRecorded(build){return Boolean(build.level||build.lc||build.traces!=='unset'||build.relics!=='unset')}
function buildConfigRecorded(build){return build.eidolon!=='unset'||build.signature!=='unset'}
function buildRecorded(build){return buildCoreRecorded(build)||buildConfigRecorded(build)}
function buildConfigLabel(build){const b=normalizeBuild(build);const e=b.eidolon==='unset'?'E?':`E${b.eidolon}`;const s=b.signature==='yes'?'S1':b.signature==='no'?'S0':'S?';return `${e}${s}`}
function signatureText(value){return BUILD_SIGNATURES.find(x=>x[0]===value)?.[1]||'未录入'}
function buildState(build){const b=normalizeBuild(build);const traceScore=buildOptionScore(BUILD_TRACES,b.traces);const relicScore=buildOptionScore(BUILD_RELICS,b.relics);const baseScore=(b.level/80)*.25+(b.lc/80)*.2+traceScore*.25+relicScore*.3;const configBonus=(b.eidolon==='unset'?0:Number(b.eidolon)*.008)+(b.signature==='yes'?.035:0);const score=Math.min(1,baseScore+configBonus);const recorded=buildRecorded(b);const coreRecorded=buildCoreRecorded(b);const ready=coreRecorded&&baseScore>=.86&&b.level>=75&&b.lc>=70&&traceScore>=.82&&relicScore>=.82;let label='练度未录入';if(ready)label='已成型';else if(coreRecorded&&baseScore>=.72)label='可用';else if(coreRecorded)label='待练';else if(buildConfigRecorded(b))label='仅配置';return{...b,baseScore,score,basePercent:Math.round(baseScore*100),percent:Math.round(score*100),recorded,coreRecorded,ready,label,configLabel:buildConfigLabel(b)};}
function buildFor(slug){return normalizeBuild(box.builds?.[canonicalSlug(slug)]||{})}
function buildShortLabel(slug){const s=buildState(buildFor(slug));return `${s.label}${s.coreRecorded?` ${s.basePercent}%`:''} · ${s.configLabel}`}
function readBoxRaw(){try{return JSON.parse(localStorage.getItem(BOX_KEY)||'{}');}catch{return{};}}
function rawOwnedList(raw){const rows=Array.isArray(raw.owned)?raw.owned:Object.keys(raw.owned||{}).filter(k=>raw.owned[k]);return rows.filter(slug=>slug&&slug!=='__codex_test__');}
function applyBoxRaw(raw){const aliases=boxAliasMap();const owned=rawOwnedList(raw);box.owned=new Set(owned.map(s=>aliases.get(s)||s).filter(Boolean));box.builds={};Object.entries(raw.builds||{}).forEach(([slug,build])=>{const resolved=aliases.get(slug)||slug;if(resolved)box.builds[resolved]=normalizeBuild(build);});box.buildSlug=aliases.get(raw.buildSlug)||raw.buildSlug||'';if(box.buildSlug&&!box.owned.has(box.buildSlug))box.buildSlug='';box.saveStatus=raw.fromServer?'本机自动保存':'浏览器缓存';}
function loadBox(){try{applyBoxRaw(readBoxRaw());}catch{box.owned=new Set();box.builds={};box.buildSlug='';box.saveStatus='浏览器缓存';}}
function boxPayload(){const builds={};Object.entries(box.builds||{}).forEach(([slug,build])=>{const normalized=normalizeBuild(build);if(buildRecorded(normalized))builds[slug]=normalized;});return{version:3,updatedAt:new Date().toISOString(),owned:[...box.owned].sort(),buildSlug:box.buildSlug||'',builds};}
function saveBox(){const payload=boxPayload();localStorage.setItem(BOX_KEY,JSON.stringify(payload));box.saveStatus='已保存到浏览器';clearTimeout(boxSaveTimer);boxSaveTimer=setTimeout(()=>saveBoxToServer(payload),180);if(state.page==='box'||state.page==='banner')requestAnimationFrame(()=>{if(state.page==='box')renderBox();else renderBanner();});}
function hasBoxData(raw){return Boolean(rawOwnedList(raw).length||Object.keys(raw.builds||{}).length);}
function boxTime(raw){const t=Date.parse(raw.updatedAt||raw.exportedAt||'');return Number.isFinite(t)?t:0;}
function syncBoxFromServer(){fetch('/api/hsr/box',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('no api'))).then(server=>{const local=readBoxRaw();server.fromServer=true;const serverWins=Boolean(server.updatedAt)&&boxTime(server)>=boxTime(local);if(serverWins||(hasBoxData(server)&&(!hasBoxData(local)||boxTime(server)>=boxTime(local)))){applyBoxRaw(server);localStorage.setItem(BOX_KEY,JSON.stringify(server));box.saveStatus='本机自动保存';render();}else if(hasBoxData(local)){saveBoxToServer(boxPayload());}else{box.saveStatus='本机自动保存';render();}}).catch(()=>{box.saveStatus='浏览器缓存';if(state.page==='box'||state.page==='banner')render();});}
function saveBoxToServer(payload){fetch('/api/hsr/box',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.ok?r.json():Promise.reject(new Error('save failed'))).then(()=>{box.saveStatus='本机自动保存';if(state.page==='box'||state.page==='banner')render();}).catch(()=>{box.saveStatus='浏览器缓存';if(state.page==='box'||state.page==='banner')render();});}
function releaseOrder(row){const n=Number(row.release_order);return Number.isFinite(n)?n:99999}
function filteredRoster(){const q=box.search;return DATA.rosterRows.filter(r=>(box.element==='all'||r.element_cn===box.element)&&(box.path==='all'||r.path_cn===box.path)&&(box.role==='all'||String(r.role_groups||'').split(';').includes(box.role))&&(box.rarity==='all'||String(r.rarity)===box.rarity)&&(box.status==='all'||(box.status==='owned')===box.owned.has(r.character_slug))&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,r.element_cn,r.path_cn,r.role_group_cns].some(x=>String(x||'').toLowerCase().includes(q)))).sort((a,b)=>releaseOrder(a)-releaseOrder(b)||String(a.character_name_en).localeCompare(String(b.character_name_en)));}
function toggleOwned(slug){const resolved=canonicalSlug(slug);if(box.owned.has(resolved)){box.owned.delete(resolved);if(box.buildSlug===resolved)box.buildSlug='';}else{box.owned.add(resolved);box.buildSlug=resolved;}saveBox();renderBox();}
function renderBox(){const rows=filteredRoster();const total=DATA.rosterRows.length;const owned=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)).length;const built=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)&&buildState(buildFor(r.character_slug)).ready).length;renderBuildEditor();$('boxSubtitle').textContent=`展示 ${rows.length}/${total} 个角色，已拥有 ${owned} 个，已成型 ${built} 个。点击卡片切换拥有，点「练度」维护等级/光锥/星魂/专武/行迹/遗器。`;$('boxBadges').innerHTML=[box.saveStatus||'浏览器缓存',box.element==='all'?'全部属性':box.element,box.path==='all'?'全部命途':box.path,box.status==='all'?'全部状态':box.status==='owned'?'已拥有':'未拥有',`成型 ${built}/${owned||0}`].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('boxGrid');grid.innerHTML='';rows.forEach(row=>{const owned=box.owned.has(row.character_slug);const buildText=owned?buildShortLabel(row.character_slug):'未拥有';const card=document.createElement('article');card.tabIndex=0;card.setAttribute('role','button');card.className=`box-card ${owned?'owned':'missing'} ${box.buildSlug===row.character_slug?'selected':''}`;card.dataset.slug=row.character_slug;card.onclick=()=>toggleOwned(row.character_slug);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleOwned(row.character_slug);}};card.onmouseenter=e=>showBoxTooltip(e,row);card.onmousemove=moveTooltip;card.onmouseleave=()=>{$('boxTooltip').hidden=true;};card.innerHTML=`<button class="build-button" type="button">练度</button><span class="owned-dot"></span><img src="${esc(row.icon_url)}" alt="" loading="lazy" decoding="async"><div class="box-name">${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</div><div class="box-meta">${esc(row.element_cn||'')} · ${esc(row.path_cn||'')}</div><div class="box-meta">${esc(row.role_group_cns||'未分类')}</div><div class="box-meta box-build">${esc(buildText)}</div>`;card.querySelector('.build-button').onclick=e=>{e.stopPropagation();selectBuild(row.character_slug);};grid.appendChild(card);});}
function selectBuild(slug){const resolved=canonicalSlug(slug);box.owned.add(resolved);box.buildSlug=resolved;saveBox();renderBox();}
function renderBuildEditor(){const panel=$('buildEditor');if(!box.buildSlug||!box.owned.has(box.buildSlug)){panel.classList.add('hidden');return;}const row=charInfo(box.buildSlug);const state=buildState(buildFor(box.buildSlug));panel.classList.remove('hidden');$('buildEditorIcon').src=row.icon_url||'';$('buildEditorTitle').textContent=`${charName(box.buildSlug)} · 练度`;$('buildEditorSubtitle').textContent=`${row.element_cn||'未知'} · ${row.path_cn||'未知'} · ${roleCn(row)}`;$('buildLevelSelect').value=String(state.level);$('buildLcSelect').value=String(state.lc);$('buildEidolonSelect').value=String(state.eidolon);$('buildSignatureSelect').value=state.signature;$('buildTraceSelect').value=state.traces;$('buildRelicSelect').value=state.relics;$('buildScoreText').textContent=`${state.label} · ${state.coreRecorded?state.basePercent:0}% · ${state.configLabel}`;}
function updateBuildField(field,value){if(!box.buildSlug)return;const build=buildFor(box.buildSlug);build[field]=value;box.builds[box.buildSlug]=normalizeBuild(build);box.owned.add(box.buildSlug);saveBox();renderBox();}
function fullBuild(prev={}){const b=normalizeBuild(prev);return{...b,level:80,lc:80,traces:'max',relics:'great'}}
function setBuildPreset(kind){if(!box.buildSlug)return;if(kind==='clear')delete box.builds[box.buildSlug];else box.builds[box.buildSlug]=fullBuild(box.builds[box.buildSlug]||{});box.owned.add(box.buildSlug);saveBox();renderBox();}
function setVisibleBuild(kind){filteredRoster().forEach(r=>{if(kind==='clear')delete box.builds[r.character_slug];else{box.owned.add(r.character_slug);box.builds[r.character_slug]=fullBuild(box.builds[r.character_slug]||{});}});saveBox();renderBox();}
function showBoxTooltip(evt,row){const tt=$('boxTooltip');const owned=box.owned.has(row.character_slug);const state=buildState(buildFor(row.character_slug));const eidolonText=state.eidolon==='unset'?'未录入':`${state.eidolon}魂`;tt.hidden=false;tt.innerHTML=`<div class="tooltip-head"><img src="${esc(row.icon_url)}" alt=""><div><strong>${esc(row.character_name_cn||row.character_name_en)}</strong><span>${esc(row.character_name_en)} · ${esc(row.character_slug)}</span></div></div><div class="tooltip-grid"><b>收集状态</b><div>${owned?'已拥有':'未拥有'}</div><b>练度</b><div>${owned?`${esc(state.label)} · ${state.coreRecorded?state.basePercent:0}%`:'未拥有'}</div><b>星魂/专武</b><div>${owned?`${esc(eidolonText)} · ${esc(signatureText(state.signature))}`:'未拥有'}</div><b>属性/命途</b><div>${esc(row.element_cn||'未知')} · ${esc(row.path_cn||'未知')}</div><b>星级</b><div>${esc(row.rarity||'未知')}</div><b>职能</b><div>${esc(row.role_group_cns||'未分类')}</div><b>排序</b><div>新旧序 #${esc(row.release_order)}</div><b>来源</b><div>${esc(row.source||'')}</div></div>`;moveTooltip(evt);}
function markVisible(value){filteredRoster().forEach(r=>{if(value)box.owned.add(r.character_slug);else{box.owned.delete(r.character_slug);if(box.buildSlug===r.character_slug)box.buildSlug='';}});saveBox();renderBox();}
function exportBox(){const blob=new Blob([JSON.stringify({...boxPayload(),exportedAt:new Date().toISOString()},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='hsr_box_state.json';a.click();URL.revokeObjectURL(a.href);}
function importBox(evt){const file=evt.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{const data=JSON.parse(String(reader.result||'{}'));applyBoxRaw(data);box.buildSlug='';saveBox();renderBox();}catch(err){alert(`导入失败：${err.message}`);}finally{evt.target.value='';}};reader.readAsText(file);}

function rosterBySlug(){if(!DATA._rosterBySlug){DATA._rosterBySlug=new Map();(DATA.rosterRows||[]).forEach(r=>{DATA._rosterBySlug.set(r.character_slug,r);String(r.alias_slugs||'').split(';').forEach(s=>{if(s)DATA._rosterBySlug.set(s,r);});});}return DATA._rosterBySlug;}
function charInfo(slug){return rosterBySlug().get(slug)||{character_slug:slug,character_name_cn:'',character_name_en:slug,element_cn:'',path_cn:'',role_groups:'unknown',role_group_cns:'未分类',icon_url:''};}
function charName(slug){const r=charInfo(slug);return r.character_name_cn||r.character_name_en||slug}
function phaseName(row){return row?.phase_name_cn||(row?.phase_name?'中文期名待维护':'')}
function phaseLabel(row){const ver=row?.phase_ver||'';const name=phaseName(row);return `${ver} ${name}`.trim()}
function roleList(row){return String(row.role_groups||'unknown').split(';').filter(Boolean)}
function roleCn(row){return row.role_group_cns||roleList(row).join('/')}
function currentModeTemplates(mode){const rows=(DATA.teamTemplates||[]).filter(t=>t.mode===mode);const latest=rows.reduce((m,t)=>String(t.collect_date||'')>m?String(t.collect_date||''):m,'');return rows.filter(t=>String(t.collect_date||'')===latest);}
function scopeTemplates(mode,scope){return currentModeTemplates(mode).filter(t=>t.scope_key===scope);}
function num(v){const n=Number(v);return Number.isFinite(n)?n:null}
function canonicalSlug(slug){return charInfo(slug).character_slug||slug}
function isCoreMember(info){return roleList(info).some(role=>CORE_ROLES.has(role))}
function tierMetaFor(slug,mode){
  if(!DATA._tierRiskMeta){
    DATA._tierRiskMeta=new Map();
    (DATA.tierRows||[]).forEach(row=>{
      const resolved=canonicalSlug(row.character_slug);
      const key=`${row.tier_mode}|${resolved}`;
      const rank=TIER_RANK[row.tier];
      if(rank==null)return;
      const current=DATA._tierRiskMeta.get(key);
      if(!current||rank<current.rank)DATA._tierRiskMeta.set(key,{tier:row.tier,rank,role:row.role_group_cn||row.role_group||'',rating:num(row.rating)});
    });
  }
  return DATA._tierRiskMeta.get(`${mode}|${canonicalSlug(slug)}`)||null;
}
function usageTrendFor(slug,mode){
  if(!DATA._usageTrendMeta){
    DATA._usageTrendMeta=new Map();
    const grouped=new Map();
    (DATA.usageRows||DATA.trendRows||[]).forEach(row=>{
      const rowMode=row.tier_mode||row.mode;
      const resolved=canonicalSlug(row.character_slug);
      if(!rowMode||!resolved||!row.collect_date)return;
      const key=`${rowMode}|${resolved}|${row.collect_date}`;
      const current=grouped.get(key);
      const rate=num(row.app_rate);
      if(rate==null)return;
      if(!current||rate>current.app_rate)grouped.set(key,{mode:rowMode,slug:resolved,date:row.collect_date,app_rate:rate});
    });
    const byChar=new Map();
    grouped.forEach(point=>{const key=`${point.mode}|${point.slug}`;if(!byChar.has(key))byChar.set(key,[]);byChar.get(key).push(point);});
    byChar.forEach((points,key)=>{
      points.sort((a,b)=>String(a.date).localeCompare(String(b.date)));
      const recent=points.slice(-4);
      if(recent.length<3){DATA._usageTrendMeta.set(key,{risk:false,points:recent});return;}
      const first=recent[0].app_rate,last=recent[recent.length-1].app_rate,prev=recent[recent.length-2].app_rate;
      const drops=recent.slice(1).filter((p,i)=>p.app_rate<recent[i].app_rate).length;
      const absoluteDrop=first-last;
      const relativeDrop=first>0?absoluteDrop/first:0;
      const risk=first>=3&&last<prev&&((drops>=2&&absoluteDrop>=3)||(relativeDrop>=0.45&&absoluteDrop>=2.2));
      DATA._usageTrendMeta.set(key,{risk,points:recent,first,last,drop:absoluteDrop});
    });
  }
  return DATA._usageTrendMeta.get(`${mode}|${canonicalSlug(slug)}`)||{risk:false,points:[]};
}
function memberRisk(member,mode){
  const reasons=[];const tier=tierMetaFor(member.slug,mode);const core=isCoreMember(member.info);const build=member.buildState||buildState(buildFor(member.slug));const built=member.owned&&build.ready;
  if(member.owned){
    if(!build.coreRecorded)reasons.push({type:'build-missing',text:'练度未录入',penalty:core?44:24});
    else if(build.baseScore<.68)reasons.push({type:'build-low',text:`练度待补 ${build.basePercent}%`,penalty:core?70:38,severe:core});
    else if(build.baseScore<.86)reasons.push({type:'build-mid',text:`练度未成型 ${build.basePercent}%`,penalty:core?32:16});
  }
  if(tier){
    if(tier.rank>=5)reasons.push({type:'tier-forgotten',text:`${tier.tier}不建议投入${built?'（已练，降权）':''}`,penalty:built?(core?55:30):(core?120:70),severe:true});
    else if(tier.rank>=3)reasons.push({type:'tier-offmeta',text:`${tier.tier}非主流低档${built?'（已练，降权）':''}`,penalty:built?(core?42:24):(core?85:45),severe:true});
    else if(tier.rank>=1&&!built)reasons.push({type:'tier-caution',text:`${tier.tier}投入谨慎`,penalty:core?34:18});
  }
  const trend=usageTrendFor(member.slug,mode);
  if(trend.risk)reasons.push({type:'trend',text:`近${trend.points.length}期走弱 ${trend.first?.toFixed?.(1)}%→${trend.last?.toFixed?.(1)}%`,penalty:core?55:25});
  return reasons;
}
function teamRisk(members,selectedElements){
  const risks=[];const core=members.filter(m=>isCoreMember(m.info));
  if(selectedElements.size&&core.length){
    const coreHits=core.filter(m=>selectedElements.has(m.info.element_cn)).length;
    const expected=Math.min(2,core.length,selectedElements.size);
    if(coreHits===0)risks.push({type:'core-none',text:'主C/副C均未命中推荐属性',penalty:180,severe:true});
    else if(coreHits<expected)risks.push({type:'core-low',text:`核心属性不足 ${coreHits}/${expected}`,penalty:85,severe:true});
  }
  return risks;
}

function rankedRecommendations(mode=rec.mode,scope=rec.scope,used=new Set(),options={}){
  const selected=recElementSet(mode,scope);
  const maxGap=Number(options.maxGap??rec.gap);
  const q=options.ignoreSearch?'':rec.search;
  return scopeTemplates(mode,scope).map(t=>scoreTemplate(t,selected,used)).filter(item=>{
    if(Number.isFinite(maxGap)&&item.missingCount>maxGap)return false;
    const riskMode=options.riskMode||rec.riskMode||'warn';
    if(riskMode==='filter'&&item.risks.length)return false;
    if(q&&!item.searchText.includes(q))return false;
    return true;
  }).sort((a,b)=>b.score-a.score||a.missingCount-b.missingCount||(num(a.template.rank)||9999)-(num(b.template.rank)||9999));
}

function scoreTemplate(template,selectedElements,used){
  const chars=template.chars||[];
  const members=chars.map(slug=>{const info=charInfo(slug);const build=buildFor(slug);const buildMeta=buildState(build);return{slug,info,build,buildState:buildMeta,owned:box.owned.has(slug),selected:selectedElements.has(info.element_cn),used:used.has(slug),core:isCoreMember(info)}});
  const ownedCount=members.filter(m=>m.owned).length;
  const buildReadyCount=members.filter(m=>m.owned&&m.buildState.ready).length;
  const ownedBuildScore=members.filter(m=>m.owned).reduce((sum,m)=>sum+m.buildState.score,0);
  const missing=members.filter(m=>!m.owned);
  const conflictCount=members.filter(m=>m.owned&&m.used).length;
  const elementHits=members.filter(m=>m.selected).length;
  const coreMembers=members.filter(m=>m.core);
  const coreElementHits=coreMembers.filter(m=>m.selected).length;
  members.forEach(m=>{m.risks=memberRisk(m,template.mode);});
  const reserved=new Set([...chars,...used]);
  const substitutions=missing.map(m=>({missing:m,candidates:substituteCandidates(m.slug,selectedElements,reserved)}));
  const fillCount=substitutions.filter(s=>s.candidates.length).length;
  const memberRisks=members.flatMap(m=>m.risks.map(r=>({...r,slug:m.slug,name:charName(m.slug)})));
  const attributeRisks=teamRisk(members,selectedElements);
  const risks=[...memberRisks,...attributeRisks];
  const riskPenalty=(rec.riskMode==='off'?0:risks.reduce((sum,r)=>sum+(r.penalty||0),0));
  const app=num(template.app_rate)||0;
  const rank=num(template.rank);
  const avg=num(template.avg_round);
  let score=ownedCount*45+ownedBuildScore*90-missing.length*66-conflictCount*180+elementHits*8+coreElementHits*48+fillCount*34+Math.min(app,35)*2.2-riskPenalty;
  if(rank!=null)score+=Math.max(0,160-rank)*0.34;
  if(avg!=null&&avg<99)score-=avg*1.2;
  if(missing.length===0)score+=95;
  if(selectedElements.size&&elementHits===0)score-=40;
  const finalChars=members.map(m=>m.owned?m.slug:(substitutions.find(s=>s.missing.slug===m.slug)?.candidates[0]?.character_slug||m.slug));
  const searchText=[template.phase_name_cn,template.phase_name,template.source_kind,template.scope_label,...chars, ...chars.map(charName),...risks.map(r=>r.text)].join(' ').toLowerCase();
  return{template,members,missingCount:missing.length,ownedCount,buildReadyCount,conflictCount,elementHits,coreElementHits,substitutions,risks,score,finalChars,searchText};
}

function substituteCandidates(missingSlug,selectedElements,reserved){
  const missing=charInfo(missingSlug);
  const missingRoles=new Set(roleList(missing));
  return (DATA.rosterRows||[]).filter(r=>box.owned.has(r.character_slug)&&!reserved.has(r.character_slug)).map(r=>{
    const roles=roleList(r);
    const roleOverlap=roles.some(role=>missingRoles.has(role));
    let score=0;
    if(roleOverlap)score+=58;
    if(r.path_cn&&r.path_cn===missing.path_cn)score+=18;
    if(r.element_cn&&r.element_cn===missing.element_cn)score+=18;
    if(selectedElements.has(r.element_cn))score+=24;
    if(String(r.rarity)==='5')score+=4;
    if(missingRoles.has('sustain')&&roles.includes('sustain'))score+=24;
    if((missingRoles.has('support')||missingRoles.has('sub_dps'))&&(roles.includes('support')||roles.includes('sub_dps')))score+=12;
    return{...r,subScore:score};
  }).filter(r=>r.subScore>0).sort((a,b)=>b.subScore-a.subScore||releaseOrder(a)-releaseOrder(b)).slice(0,3);
}

function renderRecommender(){
  ensureRecScope();syncRecControls();$('recTooltip').hidden=true;
  const modeLabel=MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode;
  const scope=recScopeOptions(rec.mode).find(o=>o.key===rec.scope);
  const templates=scopeTemplates(rec.mode,rec.scope);
  const ranked=rankedRecommendations().slice(0,Number(rec.limit)||8);
  const latest=templates[0]||{};
  const selected=[...recElementSet()];
  renderPhaseMechanics(latest);
  $('recTitle').textContent=`${modeLabel} · ${scope?.label||rec.scope}`;
  $('recSubtitle').textContent=`${phaseLabel(latest)} · ${latest.collect_date||''} · 当前同模式同关卡模板 ${templates.length} 队`;
  const riskLabel=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';
  const tierRiskLabel=rec.riskMode==='off'?'当前模式T档不提醒':'当前模式T1及以下提醒';
  $('recBadges').innerHTML=[selected.length?selected.join(' / '):'未选属性',`缺口 ≤ ${rec.gap}`,riskLabel,tierRiskLabel,`Box ${box.owned.size}`].map(x=>`<span>${esc(x)}</span>`).join('');
  const list=$('recList');list.innerHTML='';
  if(!ranked.length){list.innerHTML='<div class="rec-empty">当前筛选没有可展示队伍</div>';renderRecSlate();return;}
  ranked.forEach((item,index)=>list.appendChild(recCard(item,index+1)));
  renderRecSlate();
}

function phaseInfoFor(template){
  const rows=DATA.phaseInfoRows||[];
  const exact=rows.find(r=>r.mode===rec.mode&&r.phase_ver===template.phase_ver&&r.phase_name===template.phase_name);
  if(exact)return exact;
  const modeRows=rows.filter(r=>r.mode===rec.mode).sort((a,b)=>String(b.collect_date).localeCompare(String(a.collect_date)));
  return modeRows[0]||template||{};
}

function renderPhaseMechanics(template){
  const info=phaseInfoFor(template||{});
  const modeLabel=MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode;
  const phaseTitle=phaseLabel(info)||phaseLabel(template);
  $('phaseMechanicsTitle').textContent=`${modeLabel} · ${phaseTitle||'未识别期名'}`;
  const dates=[info.start_date&&`开始 ${info.start_date}`,info.end_date&&`结束 ${info.end_date}`,info.collect_date&&`采样 ${info.collect_date}`].filter(Boolean).join(' · ');
  $('phaseMechanicsSubtitle').textContent=dates||'期名来自本地 phase_index';
  const mechanicName=info.mechanic_name||'机制效果待维护';
  const mechanicText=info.mechanic_text||'当前本地数据只识别到了期名和采样日期，尚未维护这一期的环境效果。这个状态会明确显示，避免把未知效果误当成已匹配。';
  $('phaseMechanicsText').textContent=`${mechanicName}：${mechanicText}`;
  const source=$('phaseMechanicsSource');
  if(info.mechanic_url){source.href=info.mechanic_url;source.textContent=info.mechanic_source||'机制来源';source.classList.remove('hidden-link');}
  else{source.href='#';source.textContent='';source.classList.add('hidden-link');}
}

function recCard(item,index){
  const t=item.template;
  const card=document.createElement('article');
  card.className=`rec-card ${item.risks.length&&rec.riskMode!=='off'?'risky':''}`;
  card.onmouseenter=e=>showRecTooltip(e,item);
  card.onmousemove=moveTooltip;
  card.onmouseleave=()=>{$('recTooltip').hidden=true;};
  const missingNames=item.members.filter(m=>!m.owned).map(m=>charName(m.slug));
  card.innerHTML=`<div class="rec-card-head"><div><h3>${index}. ${esc((t.names_cn||[]).filter(Boolean).join(' / ')||t.chars.map(charName).join(' / '))}</h3><div class="rec-meta">${esc(t.scope_label)} · Rank ${esc(t.rank??'-')} · ${t.app_rate==null?'-':pct(t.app_rate)} · ${t.avg_round==null?'-':Number(t.avg_round).toFixed(2)}</div></div><div class="rec-score"><strong>${Math.round(item.score)}</strong><span>${item.ownedCount}/4</span></div></div><div class="rec-team">${item.members.map(m=>recMemberHtml(m,item)).join('')}</div><div class="rec-tags">${recTags(item).map(tag=>`<span class="${tag.danger?'danger':tag.warn?'warn':''}">${esc(tag.text)}</span>`).join('')}</div>${riskNoteHtml(item)}${substitutionHtml(item)}${missingNames.length?`<div class="rec-note">缺：${esc(missingNames.join('、'))}</div>`:''}`;
  return card;
}

function recMemberHtml(member,item){
  const r=member.info;
  const riskText=(member.risks||[]).map(x=>x.text).join('；');
  const coreRisk=item?.risks?.some(risk=>(risk.type==='core-none'||risk.type==='core-low')&&member.core&&!member.selected);
  const buildText=member.owned?` · ${member.buildState.label} · ${member.buildState.configLabel}`:'';
  return `<div class="rec-member ${member.owned?'owned':'missing'} ${(riskText||coreRisk)&&rec.riskMode!=='off'?'risky':''}" title="${esc([member.owned?'已拥有':'未拥有',member.owned?`练度 ${member.buildState.label} ${member.buildState.basePercent}% · ${member.buildState.configLabel}`:'',riskText,coreRisk?'核心属性未命中':''].filter(Boolean).join('；'))}"><img src="${esc(r.icon_url)}" alt="" loading="lazy" decoding="async"><div class="name">${esc(r.character_name_cn||r.character_name_en||member.slug)}</div><div class="meta">${esc(r.element_cn||'')} · ${esc(roleCn(r))}${esc(buildText)}</div></div>`;
}

function recTags(item){
  const t=item.template;
  const tags=[{text:item.missingCount?`缺 ${item.missingCount}`:'可成队',warn:item.missingCount>0},{text:`属性命中 ${item.elementHits}`,warn:false},{text:t.source_kind||'source',warn:false}];
  if(item.ownedCount)tags.push({text:`练度 ${item.buildReadyCount}/${item.ownedCount}`,warn:item.buildReadyCount<item.ownedCount});
  if(item.coreElementHits||recElementSet(t.mode,t.scope_key).size)tags.push({text:`核心命中 ${item.coreElementHits}`,warn:item.coreElementHits===0});
  if(item.risks.length&&rec.riskMode!=='off')tags.push({text:`风险 ${item.risks.length}`,danger:item.risks.some(r=>r.severe),warn:true});
  if(item.conflictCount)tags.push({text:`冲突 ${item.conflictCount}`,warn:true});
  return tags;
}

function riskNoteHtml(item){
  if(!item.risks.length||rec.riskMode==='off')return '';
  const text=item.risks.slice(0,4).map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；');
  return `<div class="rec-risk-note">${esc(text)}${item.risks.length>4?'；...':''}</div>`;
}

function substitutionHtml(item){
  const rows=item.substitutions.filter(s=>s.candidates.length);
  if(!rows.length)return '';
  return `<div class="rec-subs">${rows.map(s=>`<div class="rec-subline"><b>${esc(charName(s.missing.slug))}</b>${s.candidates.map(c=>`<span class="rec-mini"><img src="${esc(c.icon_url)}" alt="">${esc(c.character_name_cn||c.character_name_en)}</span>`).join('')}</div>`).join('')}</div>`;
}

function renderRecSlate(){
  const scopes=recScopeOptions(rec.mode).filter(o=>o.key!=='all');
  const used=new Set();
  const chosen=[];
  scopes.forEach(scope=>{
    const best=rankedRecommendations(rec.mode,scope.key,used,{ignoreSearch:true,maxGap:Number(rec.gap)}).find(item=>item.conflictCount===0);
    if(best){chosen.push({scope,item:best});best.finalChars.forEach(slug=>{if(box.owned.has(slug))used.add(slug);});}
    else chosen.push({scope,item:null});
  });
  $('recSlateSubtitle').textContent=`${chosen.filter(x=>x.item).length}/${scopes.length} 队 · 不复用已拥有角色`;
  const boxEl=$('recSlateList');boxEl.innerHTML='';
  if(!chosen.length){boxEl.innerHTML='<div class="rec-empty">暂无当前模式关卡模板</div>';return;}
  chosen.forEach(({scope,item})=>{const card=document.createElement('div');card.className=`rec-slate-card ${item?.risks?.length&&rec.riskMode!=='off'?'risky':''}`;if(!item){card.innerHTML=`<h3>${esc(scope.label)}</h3><div class="rec-note">没有符合缺口限制的队伍</div>`;}else{card.onmouseenter=e=>showRecTooltip(e,item);card.onmousemove=moveTooltip;card.onmouseleave=()=>{$('recTooltip').hidden=true;};card.innerHTML=`<h3>${esc(scope.label)} · ${Math.round(item.score)} · ${item.ownedCount}/4</h3><div class="rec-slate-team">${item.finalChars.map(slug=>{const r=charInfo(slug);const owned=box.owned.has(slug);const member=item.members.find(m=>m.slug===slug);const risky=rec.riskMode!=='off'&&Boolean(member?.risks?.length);return`<img class="${owned?'':'missing'} ${risky?'risky':''}" src="${esc(r.icon_url)}" title="${esc(charName(slug))}" alt="">`;}).join('')}</div>${riskNoteHtml(item)}`;}boxEl.appendChild(card);});
}

function showRecTooltip(evt,item){
  const tt=$('recTooltip');const t=item.template;const selected=[...recElementSet(t.mode,t.scope_key)].join(' / ')||'未选';
  const riskText=item.risks.length&&rec.riskMode!=='off'?item.risks.map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；'):'无';
  const riskMode=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';
  tt.hidden=false;
  tt.innerHTML=`<div class="tooltip-head"><div><strong>${esc(t.mode_cn)} · ${esc(t.scope_label)}</strong><span>${esc(phaseLabel(t))} · ${esc(t.collect_date)}</span></div></div><div class="tooltip-grid"><b>当前约束</b><div>同模式 / 同关卡 / 最新采样</div><b>推荐属性</b><div>${esc(selected)}</div><b>风险模式</b><div>${esc(riskMode)}</div><b>模板表现</b><div>Rank ${esc(t.rank??'-')} · ${t.app_rate==null?'-':pct(t.app_rate)} · ${t.avg_round==null?'-':esc(Number(t.avg_round).toFixed(2))}</div><b>Box命中</b><div>${item.ownedCount}/4，成型 ${item.buildReadyCount}/${item.ownedCount}，缺 ${item.missingCount}</div><b>属性命中</b><div>全队 ${item.elementHits} · 核心 ${item.coreElementHits}</div><b>风险</b><div>${esc(riskText)}</div><b>分数</b><div>${Math.round(item.score)}</div><b>来源</b><div>${esc(t.source_kind||'')} · ${esc(t.source_file||'')}</div></div>`;
  moveTooltip(evt);
}
"""
