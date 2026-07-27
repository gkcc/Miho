from __future__ import annotations

import csv
import io
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from miho_core.banner_plan import effective_banner_phases
from miho_core.visualizer_data import compact_visualizer_data

from .constants import MODE_CN
from .normalize import natural_version_key, normalize_character_id

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


def _safe_relative_url(value: Any, *, require_path: bool) -> str:
    text = str(value or "").strip()
    if not text or "\\" in text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        return ""
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme or parts.netloc or text.startswith("/"):
        return ""
    decoded_path = parts.path
    for _ in range(3):
        decoded = urllib.parse.unquote(decoded_path)
        if decoded == decoded_path:
            break
        decoded_path = decoded
    if "\\" in decoded_path or decoded_path.startswith("/"):
        return ""
    if any(part == ".." for part in decoded_path.split("/")):
        return ""
    if require_path and not decoded_path:
        return ""
    return text


def _safe_link_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "\\" in text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        return ""
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme:
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return ""
        if any(char.isspace() for char in parts.netloc):
            return ""
        return text
    return _safe_relative_url(text, require_path=False)


def _safe_avatar_url(value: Any) -> str:
    return _safe_relative_url(value, require_path=True)


def _http_avatar_source(value: Any) -> str:
    text = _safe_link_url(value)
    if not text:
        return ""
    try:
        scheme = urllib.parse.urlsplit(text).scheme.lower()
    except ValueError:
        return ""
    return text if scheme in {"http", "https"} else ""


def read_recommender_team_rows(out_dir: Path) -> list[dict[str, Any]]:
    dedup_path = out_dir / "team_rank_dedup_unordered.csv"
    raw_path = out_dir / "team_rank_raw.csv"
    dedup_rows = _read_csv(dedup_path) if dedup_path.exists() else []
    if _team_rows_use_current_signatures(dedup_rows) or not raw_path.exists():
        return dedup_rows
    # Old unordered signatures collapsed snapshots, dates, phases, and
    # scopes. Raw preserves those rows and can rebuild the complete pool.
    return _read_csv(raw_path)


def _team_rows_use_current_signatures(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    fields = ("snapshot_id", "collect_date", "mode", "sub_mode", "scope", "phase_ver", "phase_name")
    return all(
        str(row.get("unordered_signature") or "").startswith(
            "|".join(str(row.get(field) or "") for field in fields) + "|"
        )
        for row in rows
    )


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
    banner_rows = _load_banner_rows(out_dir, roster_rows)
    roster_rows = _merge_banner_rows_into_roster(roster_rows, banner_rows)
    safe_trend_rows = _sanitize_avatar_rows(trend_rows, roster_rows)
    safe_tier_rows = _sanitize_link_rows(_sanitize_avatar_rows(tier_rows, roster_rows), "source_url")
    safe_changelog_rows = _sanitize_link_rows(changelog_rows, "source_url")
    team_templates = _build_recommender_rows(
        team_rank_rows if team_rank_rows is not None else read_recommender_team_rows(out_dir),
        roster_rows,
        phase_info_rows,
    )
    data_quality = _read_data_quality(out_dir)
    data = {
        "meta": {
            "generatedAt": _latest_value(tier_rows, "fetched_at"),
            "tierUpdatedAt": _latest_value(tier_rows, "tier_updated_at"),
            "tierUpdatedDate": _latest_value(tier_rows, "tier_updated_date"),
            "localDate": date.today().isoformat(),
            "source": "Prydwen Tier List + local MocStats processed dataset + HoYoWiki roster",
        },
        "metric_policy": {
            "moc": {"field": "avg_round", "label": "平均回合", "direction": "lower", "sentinels": [0, 99.99]},
            "pf": {"field": "avg_round", "label": "虚构得分", "direction": "higher", "sentinels": [0, 99.99]},
            "as": {"field": "avg_round", "label": "末日得分", "direction": "higher", "sentinels": [0, 99.99]},
            "aa": {"field": "avg_round", "label": "表现原值", "direction": None, "sentinels": [0, 99.99]},
        },
        "trendRows": safe_trend_rows,
        "usageRows": usage_rows or safe_trend_rows,
        "tierRows": safe_tier_rows,
        "changelogRows": safe_changelog_rows,
        "chartRows": chart_rows,
        "rosterRows": roster_rows,
        "phaseInfoRows": phase_info_rows,
        "teamTemplates": team_templates,
        "bannerRows": banner_rows,
        "data_quality": data_quality,
        "freshness": _data_quality_freshness(data_quality),
    }
    # Keep the original top-level wire shape for one compatibility cycle;
    # current runtimes load the smaller columnar v2 asset first.
    legacy_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    compact_data = json.dumps(
        compact_visualizer_data(data),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    (visualizer_dir / "data.json").write_text(legacy_data, encoding="utf-8")
    (visualizer_dir / "data.v2.json").write_text(compact_data, encoding="utf-8")
    (visualizer_dir / "index.html").write_text(_INDEX_HTML, encoding="utf-8")
    (visualizer_dir / "styles.css").write_text(_STYLES_CSS + _BANNER_CSS + _BUILD_CSS + _RECOMMENDER_CSS, encoding="utf-8")
    (visualizer_dir / "app.js").write_text(_APP_JS, encoding="utf-8")
    (visualizer_dir / "solver.js").write_text(_SOLVER_JS, encoding="utf-8")


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


def _read_data_quality(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "data_quality.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _data_quality_freshness(data_quality: dict[str, Any]) -> dict[str, Any]:
    modes = data_quality.get("modes")
    if not isinstance(modes, dict):
        return {}
    return {
        str(mode): quality.get("freshness", {})
        if isinstance(quality, dict) and isinstance(quality.get("freshness"), dict)
        else {}
        for mode, quality in modes.items()
    }


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
        "deployment_group": _deployment_group(slug),
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


def _deployment_group(slug: str) -> str:
    if slug.startswith("trailblazer-"):
        return "trailblazer"
    if slug in {"march-7th", "march-7th-swordmaster", "march-7th-the-hunt"}:
        return "march-7th"
    return slug


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


def _sanitize_link_rows(rows: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source_row in rows:
        row = dict(source_row)
        for key in keys:
            if key in row:
                row[key] = _safe_link_url(row.get(key))
        output.append(row)
    return output


def _sanitize_avatar_rows(
    rows: list[dict[str, Any]],
    roster_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    roster_lookup = _build_roster_lookup(roster_rows)
    output: list[dict[str, Any]] = []
    for source_row in rows:
        row = dict(source_row)
        slug = _canonical_slug(row.get("character_slug"))
        roster_icon = _safe_avatar_url(roster_lookup.get(slug, {}).get("icon_url"))
        row["icon_url"] = roster_icon or _safe_avatar_url(row.get("icon_url"))
        output.append(row)
    return output


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
        safe_icon_url = _safe_avatar_url(icon_url)
        remote_source = _http_avatar_source(icon_url)
        new_row["icon_url"] = safe_icon_url
        if remote_source and slug:
            local_path = avatars_dir / f"{slug}.webp"
            if local_path.exists() or _download_static_avatar(remote_source, local_path):
                new_row["icon_url"] = f"./assets/avatars/{local_path.name}"
        output.append(new_row)
    return output


def _download_static_avatar(url: str, destination: Path) -> bool:
    safe_url = _http_avatar_source(url)
    if not safe_url:
        return False
    try:
        from PIL import Image

        request = urllib.request.Request(
            safe_url,
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
    phase_info_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not team_rows:
        return []
    roster_lookup = _build_roster_lookup(roster_rows)
    phase_lookup = _build_phase_lookup(phase_info_rows)
    latest_observations: dict[str, tuple[str, str, str]] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        identity = _team_observation_identity(row)
        current = latest_observations.get(mode)
        if mode and identity[0] and (
            current is None or _team_observation_sort_key(identity) > _team_observation_sort_key(current)
        ):
            latest_observations[mode] = identity

    grouped: dict[str, dict[str, Any]] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        if not mode or _team_observation_identity(row) != latest_observations.get(mode):
            continue
        chars = [_canonical_slug(row.get(f"char_{index}_slug", "")) for index in range(1, 5)]
        chars = [str(roster_lookup.get(char, {}).get("character_slug") or char) for char in chars]
        if len(chars) != 4 or any(not char for char in chars):
            continue
        scope = str(row.get("scope") or "")
        scope_key, scope_label, scope_order = _recommender_scope(mode, scope)
        phase_info = _lookup_phase_info(phase_lookup, row)
        stability_component = any(
            "sustain" in {
                role.strip()
                for role in str(roster_lookup.get(char, {}).get("role_groups") or "").split(";")
                if role.strip()
            }
            for char in chars
        )
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
            "start_date": row.get("start_date") or phase_info.get("start_date", ""),
            "end_date": row.get("end_date") or phase_info.get("end_date", ""),
            "phase_status": row.get("phase_status") or phase_info.get("phase_status") or _phase_status(row),
            "rank": _numeric_value(row.get("rank")),
            "app_rate": _numeric_value(row.get("app_rate")),
            "avg_round": _numeric_value(row.get("avg_round")),
            "source_kind": row.get("source_kind", ""),
            "merged_source_kinds": row.get("merged_source_kinds") or row.get("source_kind", ""),
            "source_file": row.get("source_file", ""),
            "source_url": row.get("source_url", ""),
            "merged_source_files": row.get("merged_source_files") or row.get("source_file", ""),
            "quality_flag": row.get("quality_flag", ""),
            "duplicate_count": _evidence_duplicate_count(row.get("duplicate_count")),
            "stability_component": stability_component,
            "chars": chars,
            "names_cn": [
                str(roster_lookup.get(char, {}).get("character_name_cn") or row.get(f"char_{index}_name_cn") or "")
                for index, char in enumerate(chars, start=1)
            ],
        }
        _refresh_hsr_evidence(template)
        key = f"{mode}|{scope_key}|{'>'.join(sorted(chars))}"
        current = grouped.get(key)
        if current is None:
            grouped[key] = template
        else:
            grouped[key] = _merge_hsr_template(current, template)

    return sorted(
        grouped.values(),
        key=lambda row: (
            str(row.get("mode", "")),
            int(row.get("scope_order") or 99),
            _template_sort_key(row),
        ),
    )


def _team_observation_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(
        str(row.get(field) or "")
        for field in ("collect_date", "snapshot_id", "phase_ver")
    )


def _team_observation_sort_key(identity: tuple[str, str, str]) -> tuple[Any, ...]:
    collect_date, snapshot_id, phase_ver = identity
    return collect_date, natural_version_key(snapshot_id), natural_version_key(phase_ver)


def _evidence_duplicate_count(value: Any) -> int:
    try:
        return max(1, int(str(value).strip()))
    except (TypeError, ValueError):
        return 1


def _merged_evidence_values(*values: Any) -> str:
    return ";".join(
        sorted(
            {
                item.strip()
                for value in values
                for item in str(value or "").split(";")
                if item.strip()
            }
        )
    )


def _evidence_quality_allows_a(value: Any) -> bool:
    return all(
        not flag.strip() or flag.strip().lower() in {"ok", "valid", "complete", "clean"}
        for flag in str(value or "").split(";")
    )


def _positive_template_number(template: dict[str, Any], key: str) -> float | None:
    value = template.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _valid_hsr_performance(template: dict[str, Any]) -> float | None:
    value = template.get("avg_round")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0 or abs(number - 99.99) <= 0.001:
        return None
    return number


def _refresh_hsr_evidence(template: dict[str, Any]) -> None:
    count = _evidence_duplicate_count(template.get("duplicate_count"))
    limitations: list[str] = []
    if count < 2:
        limitations.append("仅 1 条记录")
    if _positive_template_number(template, "rank") is None:
        limitations.append("Rank 缺失")
    if _positive_template_number(template, "app_rate") is None:
        limitations.append("占比缺失")
    if _valid_hsr_performance(template) is None:
        limitations.append("表现缺失或为 sentinel")
    if not str(template.get("source_kind") or "") or not str(template.get("merged_source_files") or ""):
        limitations.append("来源字段不完整")
    if not _evidence_quality_allows_a(template.get("quality_flag")):
        limitations.append("质量标记限制")
    if not bool(template.get("stability_component")):
        limitations.append("缺少已知生存/稳定组件")
    if limitations:
        template["evidence_grade"] = "B"
        template["evidence_comment"] = f"真实队伍记录；保守按 B：{'；'.join(limitations)}。"
    else:
        template["evidence_grade"] = "A"
        template["evidence_comment"] = f"重复记录 {count} 条，Rank、占比、表现与来源字段完整。"


def _merge_hsr_template(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    duplicate_count = _evidence_duplicate_count(current.get("duplicate_count")) + _evidence_duplicate_count(
        candidate.get("duplicate_count")
    )
    source_files = _merged_evidence_values(
        current.get("merged_source_files"),
        current.get("source_file"),
        candidate.get("merged_source_files"),
        candidate.get("source_file"),
    )
    source_kinds = _merged_evidence_values(
        current.get("merged_source_kinds"),
        current.get("source_kind"),
        candidate.get("merged_source_kinds"),
        candidate.get("source_kind"),
    )
    quality_flags = _merged_evidence_values(current.get("quality_flag"), candidate.get("quality_flag"))
    selected = dict(candidate if _template_sort_key(candidate) < _template_sort_key(current) else current)
    selected["duplicate_count"] = duplicate_count
    selected["merged_source_files"] = source_files
    selected["merged_source_kinds"] = source_kinds
    selected["quality_flag"] = quality_flags
    _refresh_hsr_evidence(selected)
    return selected


def _build_phase_lookup(phase_info_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in phase_info_rows:
        mode = str(row.get("mode") or "")
        phase_ver = str(row.get("phase_ver") or "")
        phase_name = str(row.get("phase_name") or "")
        collect_date = str(row.get("collect_date") or "")
        if not mode or not phase_ver:
            continue
        for key in (
            (mode, phase_ver, phase_name),
            (mode, phase_ver, collect_date),
            (mode, phase_ver, ""),
        ):
            lookup.setdefault(key, row)
    return lookup


def _lookup_phase_info(lookup: dict[tuple[str, str, str], dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    mode = str(row.get("mode") or "")
    phase_ver = str(row.get("phase_ver") or "")
    phase_name = str(row.get("phase_name") or "")
    collect_date = str(row.get("collect_date") or "")
    return (
        lookup.get((mode, phase_ver, phase_name))
        or lookup.get((mode, phase_ver, collect_date))
        or lookup.get((mode, phase_ver, ""))
        or {}
    )


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
                "phase_status": _phase_status(row),
                "source": row.get("source", ""),
                "source_path": row.get("source_path", ""),
                "mechanic_name": seeded.get("mechanic_name", ""),
                "mechanic_text": seeded.get("mechanic_text", ""),
                "mechanic_source": seeded.get("mechanic_source", ""),
                "mechanic_url": _safe_link_url(seeded.get("mechanic_url", "")),
                "source_note": row.get("note", ""),
            }
        )
    return output


def _phase_status(row: dict[str, Any], *, today: date | None = None) -> str:
    current = today or date.today()
    start = _date_or_none(row.get("start_date"))
    end = _date_or_none(row.get("end_date"))
    if end and end < current:
        return "expired"
    if start and start > current:
        return "future"
    if start or end:
        return "current"
    return "unknown"


def _date_or_none(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


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
    for phase in effective_banner_phases(config):
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
                    "declared_phase_status": phase.get("declared_status", ""),
                    "phase_title": phase.get("title", ""),
                    "phase_subtitle": phase.get("subtitle", ""),
                    "date_range": phase.get("date_range", ""),
                    "phase_starts_at": phase.get("phase_starts_at", ""),
                    "phase_ends_at_exclusive": phase.get("phase_ends_at_exclusive", ""),
                    "source_label": char.get("source_label") or phase.get("source_label", ""),
                    "source_url": _safe_link_url(char.get("source_url") or phase.get("source_url", "")),
                    "slot": index,
                    "character_slug": slug,
                    "character_name_cn": char.get("name_cn") or info.get("character_name_cn") or "",
                    "character_name_en": char.get("name_en") or info.get("character_name_en") or "",
                    "banner_role": char.get("banner_role", ""),
                    "rarity": char.get("rarity") or info.get("rarity") or "",
                    "element_cn": char.get("element_cn") or info.get("element_cn") or "",
                    "path_cn": char.get("path_cn") or info.get("path_cn") or "",
                    "role_group_cns": char.get("role_group_cns") or info.get("role_group_cns") or "",
                    "icon_url": _safe_avatar_url(char.get("icon_url")) or _safe_avatar_url(info.get("icon_url")),
                    "analysis_tags": char.get("analysis_tags") or [],
                    "focus": char.get("focus", ""),
                }
            )
    return rows


def _merge_banner_rows_into_roster(roster_rows: list[dict[str, Any]], banner_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_slug = {str(row.get("character_slug") or ""): dict(row) for row in roster_rows}
    next_order = max((_sort_order(row.get("release_order")) for row in roster_rows), default=0) + 1
    for banner_row in banner_rows:
        slug = _canonical_slug(banner_row.get("character_slug"))
        if not slug:
            continue
        phase_status = str(banner_row.get("phase_status") or "")
        phase_title = str(banner_row.get("phase_title") or "")
        existing = by_slug.get(slug)
        if existing is None:
            by_slug[slug] = {
                "character_slug": slug,
                "deployment_group": _deployment_group(slug),
                "character_name_en": banner_row.get("character_name_en") or slug,
                "character_name_cn": banner_row.get("character_name_cn") or "",
                "element_cn": banner_row.get("element_cn") or "",
                "element_en": "",
                "path_cn": banner_row.get("path_cn") or "",
                "path_en": "",
                "rarity": banner_row.get("rarity") or "",
                "icon_url": banner_row.get("icon_url") or "",
                "release_order": next_order,
                "role_groups": "unknown",
                "role_group_cns": banner_row.get("role_group_cns") or "未分类",
                "alias_slugs": slug,
                "source": "banner_plan",
                "banner_statuses": phase_status,
                "banner_phase_titles": phase_title,
            }
            next_order += 1
            continue
        existing["banner_statuses"] = _merge_aliases(existing.get("banner_statuses"), phase_status)
        existing["banner_phase_titles"] = _merge_aliases(existing.get("banner_phase_titles"), phase_title)
        for key in ("character_name_cn", "character_name_en", "element_cn", "path_cn", "rarity", "icon_url", "role_group_cns"):
            if not existing.get(key) and banner_row.get(key):
                existing[key] = banner_row[key]
        by_slug[slug] = existing
    return sorted(by_slug.values(), key=lambda row: (_sort_order(row.get("release_order")), str(row.get("character_slug"))))


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
        return "all", "综合队伍池", 90
    if mode == "moc":
        if normalized in {"1", "12-1", "stage-12-1"}:
            return "12-1", "12-1 / 上半", 1
        if normalized in {"2", "12-2", "stage-12-2"}:
            return "12-2", "12-2 / 下半", 2
        if normalized in {"3", "12-3", "stage-12-3"}:
            return "12-3", "12-3 / 第3战斗侧（星芒）", 3
    if mode in {"pf", "as"}:
        stage_map = {
            "1": ("4-1", "4-1 / 第1战斗侧", 1),
            "2": ("4-2", "4-2 / 第2战斗侧", 2),
            "3": ("4-3", "4-3 / 第3战斗侧（星芒）", 3),
            "4-1": ("4-1", "4-1 / 第1战斗侧", 1),
            "4-2": ("4-2", "4-2 / 第2战斗侧", 2),
            "4-3": ("4-3", "4-3 / 第3战斗侧（星芒）", 3),
            "stage-4-1": ("4-1", "4-1 / 第1战斗侧", 1),
            "stage-4-2": ("4-2", "4-2 / 第2战斗侧", 2),
            "stage-4-3": ("4-3", "4-3 / 第3战斗侧（星芒）", 3),
        }
        if normalized in stage_map:
            return stage_map[normalized]
    if mode == "aa":
        stage_map = {
            "1": ("1-1", "1-1 / 骑士 1", 1),
            "2": ("1-2", "1-2 / 骑士 2", 2),
            "3": ("1-3", "1-3 / 骑士 3", 3),
            "4": ("2-1", "2-1 / 王棋", 4),
            "1-1": ("1-1", "1-1 / 骑士 1", 1),
            "1-2": ("1-2", "1-2 / 骑士 2", 2),
            "1-3": ("1-3", "1-3 / 骑士 3", 3),
            "2-1": ("2-1", "2-1 / 王棋", 4),
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


def _template_sort_key(row: dict[str, Any]) -> tuple[int, int, float, float, int, float]:
    source_scope = str(row.get("scope") or "")
    normalized_scope = re.sub(r"[^a-z0-9]+", "-", source_scope.lower()).strip("-")
    scope_priority = 0 if "-" in normalized_scope and normalized_scope not in {"all", "top"} else 1
    source_priority = {"hf_comps": 0, "prydwen_page": 1}.get(str(row.get("source_kind") or ""), 2)
    rank = row.get("rank")
    rank_value = float(rank) if isinstance(rank, (int, float)) else 1_000_000.0
    app_rate = row.get("app_rate")
    app_value = float(app_rate) if isinstance(app_rate, (int, float)) else -1.0
    performance = _valid_hsr_performance(row)
    mode = str(row.get("mode") or "")
    if mode == "aa":
        performance_missing, performance_value = 0, 0.0
    elif performance is None:
        performance_missing, performance_value = 1, 0.0
    elif mode == "moc":
        performance_missing, performance_value = 0, performance
    elif mode in {"pf", "as"}:
        performance_missing, performance_value = 0, -performance
    else:
        performance_missing, performance_value = 0, 0.0
    return scope_priority, source_priority, rank_value, -app_value, performance_missing, performance_value


# Python is retained as a migration oracle. Runtime visualizer assets have one
# canonical source under the Rust crate so UI fixes cannot silently drift
# between two embedded copies.
_CANONICAL_VISUALIZER_DIR = Path(__file__).resolve().parents[1] / "crates" / "miho-core" / "assets" / "visualizer" / "hsr"
_INDEX_HTML = (_CANONICAL_VISUALIZER_DIR / "index.html").read_text(encoding="utf-8")
_STYLES_CSS = (_CANONICAL_VISUALIZER_DIR / "styles.css").read_text(encoding="utf-8")
_BANNER_CSS = ""
_BUILD_CSS = ""
_RECOMMENDER_CSS = ""
_APP_JS = (_CANONICAL_VISUALIZER_DIR / "app.js").read_text(encoding="utf-8")
_SOLVER_JS = (_CANONICAL_VISUALIZER_DIR.parent / "solver.js").read_text(encoding="utf-8")
