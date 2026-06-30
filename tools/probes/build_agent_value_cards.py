#!/usr/bin/env python
"""Build local ZZZ box value cards from a roster draft and public meta snapshot."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p0.1-zzz-agent-value-cards"

CN_ALIAS_TO_SLUG = {
    "星徽比利": "billy-starlight",
    "星徽·比利": "billy-starlight",
    "比利星徽": "billy-starlight",
    "青衣": "qingyi",
    "朱鸢": "zhu-yuan",
    "艾莲": "ellen",
    "珂蕾妲": "koleda",
    "柯蕾妲": "koleda",
    "潘引壶": "pan-yinhu",
    "苍角": "soukaku",
    "妮可": "nicole-demara",
    "安比": "anby-demara",
    "比利": "billy-kid",
    "可琳": "corin",
    "派派": "piper",
    "露西": "lucy",
    "维琳娜": "velina",
    "奥菲丝鬼火": "orphie-and-magus",
    "奥菲丝&鬼火": "orphie-and-magus",
    "奥菲丝&「鬼火」": "orphie-and-magus",
    "猫又": "nekomata",
    "真斗": "manato",
    "波可娜": "pulchra",
    "赛斯": "seth",
    "本": "ben",
    "安东": "anton",
}

ROLE_PRIORITY = {
    "Support": 1.08,
    "Stun": 1.04,
    "Defence": 1.02,
    "Anomaly": 1.0,
    "Attack": 1.0,
    "Rupture": 0.98,
}


class AgentValueError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AgentValueError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentValueError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentValueError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_name(value: Any) -> str:
    return re.sub(r"[\s「」\"'`·.\-_:：&＆/\\]+", "", str(value or "")).casefold()


def safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", []):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def latest_phase(mode_data: dict[str, Any]) -> dict[str, Any] | None:
    phases = mode_data.get("phases") if isinstance(mode_data.get("phases"), list) else []
    return phases[0] if phases and isinstance(phases[0], dict) else None


def tier_by_slug(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = meta.get("tier_list", {}).get("entries", [])
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(entries, list):
        return result
    for entry in entries:
        if isinstance(entry, dict) and entry.get("agent_slug"):
            result[str(entry["agent_slug"])] = entry
    return result


def slug_aliases(tier_entries: dict[str, dict[str, Any]]) -> dict[str, str]:
    result = dict(CN_ALIAS_TO_SLUG)
    for slug, entry in tier_entries.items():
        result[normalize_name(slug)] = slug
        if entry.get("name"):
            result[normalize_name(entry["name"])] = slug
        for part in str(entry.get("name") or "").replace(" - ", " ").split():
            if part:
                result.setdefault(normalize_name(part), slug)
    return result


def map_roster_agents(roster: dict[str, Any], tier_entries: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    aliases = slug_aliases(tier_entries)
    agents = roster.get("agents") if isinstance(roster.get("agents"), list) else []
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for item in agents:
        if not isinstance(item, dict):
            continue
        raw_slug = item.get("agent_slug") or item.get("character_id") or item.get("slug")
        name = str(item.get("name") or item.get("character") or "")
        slug = str(raw_slug) if raw_slug else aliases.get(normalize_name(name))
        record = {
            **item,
            "agent_slug": slug,
            "owned": True,
            "name": name,
            "level": int(safe_float(item.get("level"), 0)),
            "mindscape": int(safe_float(item.get("mindscape"), 0)),
        }
        if slug and slug in tier_entries:
            mapped.append(record)
        else:
            record["mapping_warning"] = "missing_slug_mapping"
            unmapped.append(record)
    return mapped, unmapped


def max_tier_rating(entry: dict[str, Any] | None) -> tuple[float, list[str], list[str]]:
    if not entry:
        return 0.0, [], []
    ratings = entry.get("tier_ratings") if isinstance(entry.get("tier_ratings"), list) else []
    max_rating = 0.0
    tags: list[str] = []
    marks: list[str] = []
    for rating in ratings:
        if not isinstance(rating, dict):
            continue
        max_rating = max(max_rating, safe_float(rating.get("rating")))
        if rating.get("tags"):
            tags.extend(str(rating["tags"]).split(","))
        if rating.get("marks"):
            marks.extend(str(rating["marks"]).split(","))
        if rating.get("has_potential"):
            tags.append("has_potential")
    return max_rating, [tag.strip() for tag in tags if tag.strip()], [mark.strip() for mark in marks if mark.strip()]


def character_stats_by_slug(meta: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    modes = meta.get("endgame", {}).get("modes", {})
    if not isinstance(modes, dict):
        return result
    for mode, mode_data in modes.items():
        phases = mode_data.get("phases") if isinstance(mode_data.get("phases"), list) else []
        for phase_index, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            phase_info = phase.get("phase") if isinstance(phase.get("phase"), dict) else {}
            for item in phase.get("character_stats", []):
                if not isinstance(item, dict) or not item.get("agent_slug"):
                    continue
                result.setdefault(str(item["agent_slug"]), []).append(
                    {
                        **item,
                        "mode": mode,
                        "phase_index": phase_index,
                        "phase": phase_info.get("phase"),
                        "phase_label": phase_info.get("label"),
                        "total_users": phase_info.get("total_users"),
                    }
                )
    return result


def latest_mode_stats(stats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in stats:
        mode = str(item.get("mode") or "")
        if mode and mode not in result:
            result[mode] = item
    return result


def readiness_score(level: int) -> float:
    if level >= 60:
        return 100.0
    if level >= 55:
        return 88.0
    if level >= 50:
        return 76.0
    if level >= 40:
        return 55.0
    if level >= 20:
        return 32.0
    if level >= 10:
        return 22.0
    return 10.0


def rank_label(score: float) -> str:
    if score >= 75:
        return "S"
    if score >= 63:
        return "A"
    if score >= 50:
        return "B"
    if score >= 35:
        return "C"
    return "D"


def recommendation_status(reality: float, potential: float, level: int) -> str:
    if reality >= 75 and level >= 50:
        return "core_invest"
    if reality >= 75:
        return "priority_raise_from_low_level"
    if reality >= 63 and level >= 50:
        return "usable_invest"
    if reality >= 63:
        return "raise_if_team_needed"
    if reality >= 45 and potential >= 60:
        return "raise_if_team_needed"
    if potential >= 65 and level < 50:
        return "observe_potential"
    if reality >= 45:
        return "transition_only"
    return "do_not_raise_for_clear"


def mode_public_signal(latest: dict[str, dict[str, Any]]) -> tuple[float, float]:
    app_rate = max((safe_float(item.get("current_app_rate")) for item in latest.values()), default=0.0)
    avg_score = max((safe_float(item.get("current_avg_score")) for item in latest.values()), default=0.0)
    return app_rate, avg_score


def team_presence(slug: str, teams: list[dict[str, Any]]) -> int:
    return sum(
        1
        for team in teams
        if slug in {team.get("agent_1_slug"), team.get("agent_2_slug"), team.get("agent_3_slug")}
    )


def build_owned_latest_teams(meta: dict[str, Any], owned_slugs: set[str]) -> dict[str, list[dict[str, Any]]]:
    modes = meta.get("endgame", {}).get("modes", {})
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(modes, dict):
        return result
    for mode, mode_data in modes.items():
        phase = latest_phase(mode_data if isinstance(mode_data, dict) else {})
        if not phase:
            result[mode] = []
            continue
        teams = phase.get("team_usage") if isinstance(phase.get("team_usage"), list) else []
        owned: list[dict[str, Any]] = []
        for team in teams:
            if not isinstance(team, dict):
                continue
            members = [team.get("agent_1_slug"), team.get("agent_2_slug"), team.get("agent_3_slug")]
            if all(member in owned_slugs for member in members):
                owned.append({**team, "mode": mode, "phase": phase.get("phase", {})})
        result[mode] = owned
    return result


def build_missing_one_teams(meta: dict[str, Any], owned_slugs: set[str]) -> dict[str, list[dict[str, Any]]]:
    modes = meta.get("endgame", {}).get("modes", {})
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(modes, dict):
        return result
    for mode, mode_data in modes.items():
        phase = latest_phase(mode_data if isinstance(mode_data, dict) else {})
        if not phase:
            result[mode] = []
            continue
        teams = phase.get("team_usage") if isinstance(phase.get("team_usage"), list) else []
        partial: list[dict[str, Any]] = []
        for team in teams:
            if not isinstance(team, dict):
                continue
            members = [team.get("agent_1_slug"), team.get("agent_2_slug"), team.get("agent_3_slug")]
            missing = [str(member) for member in members if member not in owned_slugs]
            if len(missing) == 1:
                partial.append({**team, "missing_agent_slugs": missing, "mode": mode, "phase": phase.get("phase", {})})
        result[mode] = partial
    return result


def build_agent_values(
    *,
    meta: dict[str, Any],
    roster: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tier_entries = tier_by_slug(meta)
    mapped, unmapped = map_roster_agents(roster, tier_entries)
    owned_slugs = {str(item["agent_slug"]) for item in mapped}
    latest_owned_teams = build_owned_latest_teams(meta, owned_slugs)
    all_latest_teams = [team for teams in latest_owned_teams.values() for team in teams]
    missing_one_teams = build_missing_one_teams(meta, owned_slugs)
    partial_latest_teams = [team for teams in missing_one_teams.values() for team in teams]
    stats_by_slug = character_stats_by_slug(meta)

    values: list[dict[str, Any]] = []
    for agent in mapped:
        slug = str(agent["agent_slug"])
        tier_entry = tier_entries.get(slug, {})
        rating, tags, marks = max_tier_rating(tier_entry)
        stats = stats_by_slug.get(slug, [])
        latest_stats = latest_mode_stats(stats)
        latest_app_rate, latest_avg_score = mode_public_signal(latest_stats)
        history_count = sum(1 for item in stats if safe_float(item.get("current_app_rate")) > 0.1)
        owned_team_count = team_presence(slug, all_latest_teams)
        partial_team_count = team_presence(slug, partial_latest_teams)
        level = int(agent.get("level") or 0)
        ready = readiness_score(level)
        role_multiplier = ROLE_PRIORITY.get(str(tier_entry.get("specialty") or ""), 1.0)

        tier_component = clamp((rating / 11.0) * 100.0)
        usage_component = clamp((latest_app_rate / 25.0) * 100.0)
        score_component = clamp((latest_avg_score / 35000.0) * 100.0)
        team_component = clamp(owned_team_count * 18.0)
        history_component = clamp(history_count * 4.0)
        potential_tags = any(tag.lower() in {"has_potential", "watchlist [up]", "watchlist [down]"} for tag in tags)

        reality = (
            tier_component * 0.32
            + usage_component * 0.22
            + score_component * 0.16
            + team_component * 0.2
            + history_component * 0.1
        ) * role_multiplier
        if "down" in {mark.lower() for mark in marks}:
            reality -= 4.0

        potential = (
            tier_component * 0.32
            + max(usage_component, score_component) * 0.22
            + history_component * 0.14
            + clamp(partial_team_count * 16.0) * 0.16
            + (100.0 if potential_tags else 0.0) * 0.08
            + (100.0 if str(tier_entry.get("rarity")) == "S" else 55.0) * 0.08
        )

        reality = round(clamp(reality), 2)
        potential = round(clamp(potential), 2)
        value = {
            "agent_slug": slug,
            "name": agent.get("name") or tier_entry.get("name") or slug,
            "level": level,
            "mindscape": agent.get("mindscape", 0),
            "rarity": agent.get("rarity") or tier_entry.get("rarity"),
            "element": tier_entry.get("element"),
            "specialty": tier_entry.get("specialty"),
            "tier_rating": rating,
            "tier_tags": tags,
            "tier_marks": marks,
            "latest_public_signal": {
                "max_app_rate": latest_app_rate,
                "max_avg_score": latest_avg_score,
                "modes": {
                    mode: {
                        "current_app_rate": item.get("current_app_rate"),
                        "current_avg_score": item.get("current_avg_score"),
                        "phase": item.get("phase_label") or item.get("phase"),
                    }
                    for mode, item in latest_stats.items()
                },
            },
            "history_phase_presence_count": history_count,
            "owned_latest_team_count": owned_team_count,
            "missing_one_latest_team_count": partial_team_count,
            "readiness_score": ready,
            "reality_score": reality,
            "potential_score": potential,
            "account_tier": rank_label(reality),
            "recommendation_status": recommendation_status(reality, potential, level),
            "investment_cost_note": investment_cost_note(level),
            "reasons": reasons_for_agent(
                rating=rating,
                latest_app_rate=latest_app_rate,
                latest_avg_score=latest_avg_score,
                level=level,
                owned_team_count=owned_team_count,
                partial_team_count=partial_team_count,
                marks=marks,
            ),
        }
        values.append(value)

    values.sort(key=lambda item: (item["reality_score"], item["potential_score"], item["level"]), reverse=True)
    summary = {
        "owned_count": len(mapped),
        "unmapped_count": len(unmapped),
        "unmapped_agents": unmapped,
        "owned_slugs": sorted(owned_slugs),
    }
    return values, summary


def investment_cost_note(level: int) -> str:
    if level >= 55:
        return "near_ready"
    if level >= 40:
        return "moderate_raise_needed"
    if level >= 20:
        return "large_raise_needed"
    return "from_scratch_raise_needed"


def reasons_for_agent(
    *,
    rating: float,
    latest_app_rate: float,
    latest_avg_score: float,
    level: int,
    owned_team_count: int,
    partial_team_count: int,
    marks: list[str],
) -> list[str]:
    reasons: list[str] = []
    if rating >= 10:
        reasons.append("Prydwen tier rating 处于高位，具备强公开强度信号。")
    elif rating >= 8:
        reasons.append("Prydwen tier rating 中高，可作为账号内可用或观察角色。")
    else:
        reasons.append("公开 tier rating 不高，不能只为凑队重投入。")
    if latest_app_rate >= 5:
        reasons.append(f"当前高难最高出场率约 {latest_app_rate:.2f}%，有现实环境使用信号。")
    elif latest_app_rate > 0:
        reasons.append(f"当前高难出场率较低（最高约 {latest_app_rate:.2f}%），需要结合 box 与已有练度判断。")
    else:
        reasons.append("当前高难没有明显出场率信号。")
    if latest_avg_score >= 30000:
        reasons.append(f"当前高难最高平均分约 {latest_avg_score:.0f}，上限信号较好。")
    if level >= 50:
        reasons.append("当前等级已接近可用线，后续补强成本较低。")
    elif level <= 10:
        reasons.append("当前等级很低，只代表需要从头投入资源；不会直接压低角色价值。")
    if owned_team_count:
        reasons.append(f"当前 phase 公开队伍中存在 {owned_team_count} 个全 owned 候选。")
    elif partial_team_count:
        reasons.append(f"当前 phase 存在 {partial_team_count} 个缺一名队友的潜力队伍，先标观察。")
    if "down" in {mark.lower() for mark in marks}:
        reasons.append("Tier 变动标记含 down，保值评分有惩罚。")
    return reasons


def team_score(team: dict[str, Any], value_by_slug: dict[str, dict[str, Any]]) -> float:
    members = [team.get("agent_1_slug"), team.get("agent_2_slug"), team.get("agent_3_slug")]
    member_score = sum(safe_float(value_by_slug.get(str(member), {}).get("reality_score")) for member in members) / 3.0
    app_component = clamp(safe_float(team.get("app_rate")) * 8.0)
    avg_component = clamp((safe_float(team.get("avg_score")) / 35000.0) * 100.0)
    m1_component = clamp((safe_float(team.get("avg_score_m1plus")) / 38000.0) * 100.0)
    best_score_component = max(avg_component, m1_component * 0.82)
    low_level_penalty = sum(
        12.0
        for member in members
        if safe_float(value_by_slug.get(str(member), {}).get("level")) < 20
    )
    low_value_penalty = sum(
        8.0
        for member in members
        if value_by_slug.get(str(member), {}).get("account_tier") in {"C", "D"}
    )
    return round(clamp(member_score * 0.44 + app_component * 0.2 + best_score_component * 0.36 - low_level_penalty - low_value_penalty), 2)


def build_team_recommendations(meta: dict[str, Any], values: list[dict[str, Any]]) -> dict[str, Any]:
    value_by_slug = {str(item["agent_slug"]): item for item in values}
    owned_slugs = set(value_by_slug)
    owned_by_mode = build_owned_latest_teams(meta, owned_slugs)
    missing_by_mode = build_missing_one_teams(meta, owned_slugs)
    result: dict[str, Any] = {}
    for mode, teams in owned_by_mode.items():
        scored = []
        for team in teams:
            members = [team.get("agent_1_slug"), team.get("agent_2_slug"), team.get("agent_3_slug")]
            score = team_score(team, value_by_slug)
            scored.append(
                {
                    "mode": mode,
                    "scope_key": team.get("scope_key"),
                    "phase": team.get("phase", {}),
                    "rank": team.get("rank"),
                    "members": members,
                    "member_names": [value_by_slug.get(str(member), {}).get("name", member) for member in members],
                    "bangboo_slug": team.get("bangboo_slug"),
                    "app_rate": team.get("app_rate"),
                    "avg_score": team.get("avg_score"),
                    "avg_score_m1plus": team.get("avg_score_m1plus"),
                    "team_score": score,
                    "recommendation_class": "main_candidate" if score >= 58 else "transition_or_low_confidence",
                    "warnings": team_warnings(members, value_by_slug),
                }
            )
        scored.sort(key=lambda item: (item["team_score"], safe_float(item.get("app_rate")), safe_float(item.get("avg_score"))), reverse=True)
        scored = dedupe_team_members(scored)
        partial = []
        for team in missing_by_mode.get(mode, [])[:20]:
            members = [team.get("agent_1_slug"), team.get("agent_2_slug"), team.get("agent_3_slug")]
            partial.append(
                {
                    "scope_key": team.get("scope_key"),
                    "rank": team.get("rank"),
                    "members": members,
                    "owned_members": [member for member in members if member in owned_slugs],
                    "missing_agent_slugs": team.get("missing_agent_slugs", []),
                    "app_rate": team.get("app_rate"),
                    "avg_score": team.get("avg_score"),
                    "note": "缺失角色不能算入当前可用队，只能作为未来配件/抽取问题。",
                }
            )
        result[mode] = {
            "latest_phase": scored[0]["phase"] if scored else None,
            "owned_candidate_count": len(scored),
            "top_owned_candidates": scored[:8],
            "missing_one_watchlist": partial[:8],
        }
    return result


def build_executive_summary(values: list[dict[str, Any]], recommendations: dict[str, Any]) -> dict[str, Any]:
    return {
        "top_current_investments": [
            compact_agent(item)
            for item in values
            if item.get("recommendation_status") in {"core_invest", "priority_raise_from_low_level", "usable_invest"}
        ][:6],
        "raise_if_team_needed": [
            compact_agent(item)
            for item in values
            if item.get("recommendation_status") == "raise_if_team_needed"
        ][:8],
        "do_not_raise_for_clear": [
            compact_agent(item)
            for item in values
            if item.get("recommendation_status") == "do_not_raise_for_clear"
        ][:8],
        "current_endgame_teams": {
            mode: summarize_mode_recommendation(rec)
            for mode, rec in recommendations.items()
        },
        "policy_notes": [
            "低等级只代表培养成本，不直接压低角色价值。",
            "缺失角色只能进入观察队，不能算当前可用队。",
            "低 tier、下坡、生态差、公开使用弱且无法改善终局结果的角色不为过关强拉。",
        ],
    }


def compact_agent(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_slug": item.get("agent_slug"),
        "name": item.get("name"),
        "account_tier": item.get("account_tier"),
        "level": item.get("level"),
        "reality_score": item.get("reality_score"),
        "potential_score": item.get("potential_score"),
        "readiness_score": item.get("readiness_score"),
        "recommendation_status": item.get("recommendation_status"),
        "investment_cost_note": item.get("investment_cost_note"),
    }


def summarize_mode_recommendation(rec: dict[str, Any]) -> dict[str, Any]:
    candidates = rec.get("top_owned_candidates", [])
    main = next((item for item in candidates if item.get("recommendation_class") == "main_candidate"), None)
    fallback = candidates[0] if candidates else None
    selected = main or fallback
    return {
        "recommended_team": compact_team(selected),
        "recommendation_strength": "main_candidate" if main else "transition_or_low_confidence",
        "owned_candidate_count": rec.get("owned_candidate_count", 0),
        "missing_one_watchlist": rec.get("missing_one_watchlist", [])[:3],
    }


def compact_team(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "scope_key": item.get("scope_key"),
        "members": item.get("members"),
        "member_names": item.get("member_names"),
        "team_score": item.get("team_score"),
        "app_rate": item.get("app_rate"),
        "avg_score": item.get("avg_score"),
        "recommendation_class": item.get("recommendation_class"),
        "warnings": item.get("warnings", []),
    }


def dedupe_team_members(teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for team in teams:
        key = tuple(sorted(str(member) for member in team.get("members", [])))
        if key in seen:
            continue
        seen.add(key)
        result.append(team)
    return result


def team_warnings(members: list[Any], value_by_slug: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    low_level = [value_by_slug.get(str(member), {}).get("name", member) for member in members if safe_float(value_by_slug.get(str(member), {}).get("level")) < 20]
    if low_level:
        warnings.append("包含低等级成员，需要从头投入资源；是否值得取决于该队能否显著改善终局结果：" + ", ".join(str(item) for item in low_level))
    low_value = [
        value_by_slug.get(str(member), {}).get("name", member)
        for member in members
        if value_by_slug.get(str(member), {}).get("recommendation_status") == "do_not_raise_for_clear"
    ]
    if low_value:
        warnings.append("包含低现实价值成员，默认不为过关强行培养：" + ", ".join(str(item) for item in low_value))
    return warnings


def render_markdown(result: dict[str, Any]) -> str:
    executive = result.get("executive_summary", {}) if isinstance(result.get("executive_summary"), dict) else {}
    lines = [
        "# ZZZ Box 代理人价值报告",
        "",
        f"generated_at: {result.get('generated_at')}",
        f"owned_count: {result.get('summary', {}).get('owned_count')}",
        f"unmapped_count: {result.get('summary', {}).get('unmapped_count')}",
        "",
        "## 一屏结论",
        "",
        "### 当前优先看",
        "",
    ]
    for item in executive.get("top_current_investments", [])[:5]:
        lines.append(
            f"- {item['name']}：{item['account_tier']}，现实 {item['reality_score']} / 潜力 {item['potential_score']}，{item['recommendation_status']}"
        )
    if executive.get("raise_if_team_needed"):
        lines.extend(["", "### 队伍需要就拉起", ""])
        for item in executive.get("raise_if_team_needed", [])[:5]:
            lines.append(
                f"- {item['name']}：等级 {item['level']}，现实 {item['reality_score']} / 潜力 {item['potential_score']}，成本={item['investment_cost_note']}"
            )
    if executive.get("do_not_raise_for_clear"):
        lines.extend(["", "### 不为了过关强拉", ""])
        for item in executive.get("do_not_raise_for_clear", [])[:5]:
            lines.append(f"- {item['name']}：现实 {item['reality_score']} / 潜力 {item['potential_score']}")
    lines.extend(["", "### 当前两类高难候选", ""])
    for mode, rec in executive.get("current_endgame_teams", {}).items():
        team = rec.get("recommended_team")
        if not team:
            lines.append(f"- {mode}: 暂无全 owned 候选。")
            continue
        warning = "；".join(team.get("warnings", []))
        lines.append(
            f"- {mode}: {' / '.join(str(name) for name in team.get('member_names', []))} "
            f"(score={team.get('team_score')}, {rec.get('recommendation_strength')})"
            + (f"；{warning}" if warning else "")
        )
    lines.extend(
        [
            "",
        "## 账号内代理人 Tier",
        "",
        "| Tier | 代理人 | 等级 | 影画 | 现实价值 | 潜力价值 | 建议 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in result.get("agent_values", []):
        lines.append(
            f"| {item['account_tier']} | {item['name']} | {item['level']} | {item.get('mindscape', 0)} | "
            f"{item['reality_score']} | {item['potential_score']} | {item['recommendation_status']} |"
        )
    lines.extend(["", "## 当前高难候选队伍", ""])
    for mode, rec in result.get("team_recommendations", {}).items():
        lines.append(f"### {mode}")
        lines.append("")
        candidates = rec.get("top_owned_candidates", [])
        if not candidates:
            lines.append("- 没有找到全 owned 的公开队伍候选。")
        for team in candidates[:5]:
            warnings = "；".join(team.get("warnings", []))
            lines.append(
                "- "
                + " / ".join(str(name) for name in team.get("member_names", []))
                + f" | scope={team.get('scope_key')} | score={team.get('team_score')} | "
                + f"app_rate={team.get('app_rate')} | avg_score={team.get('avg_score')} | {team.get('recommendation_class')}"
                + (f" | warning: {warnings}" if warnings else "")
            )
        lines.append("")
        watch = rec.get("missing_one_watchlist", [])
        if watch:
            lines.append("缺一名角色的观察队：")
            for team in watch[:3]:
                lines.append(
                    "- "
                    + " / ".join(str(member) for member in team.get("members", []))
                    + " | missing="
                    + ", ".join(str(member) for member in team.get("missing_agent_slugs", []))
                )
            lines.append("")
    lines.extend(
        [
            "## 边界",
            "",
            "- 该报告基于 roster 图粗字段和 Prydwen 公开统计，不判断毕业度。",
            "- 缺失角色只能进入观察队，不能算当前可用队。",
            "- 低等级只代表培养成本；低 tier、下坡、生态差且无法改善终局结果的角色才不建议为过关重投入。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_agent_value_report(meta_snapshot: Path, roster_json: Path, output_dir: Path) -> dict[str, Any]:
    meta = load_json(meta_snapshot)
    roster = load_json(roster_json)
    values, summary = build_agent_values(meta=meta, roster=roster)
    recommendations = build_team_recommendations(meta, values)
    executive_summary = build_executive_summary(values, recommendations)
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "inputs": {
            "meta_snapshot": str(meta_snapshot),
            "roster_json": str(roster_json),
        },
        "summary": summary,
        "executive_summary": executive_summary,
        "agent_values": values,
        "team_recommendations": recommendations,
        "warnings": [
            "该报告不读取账号、cookie 或 token。",
            "box 图不能证明音擎、驱动盘、技能等级或毕业度。",
            "Prydwen appearance rate 是公开使用信号，不是持有率或抽取价值。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json = output_dir / "agent_value_cards.json"
    output_md = output_dir / "agent_value_cards.md"
    result["output_json"] = str(output_json)
    result["output_markdown"] = str(output_md)
    write_json(output_json, result)
    write_text(output_md, render_markdown(result))
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta-snapshot", required=True)
    parser.add_argument("--roster-json", required=True)
    parser.add_argument("--output-dir", default="data/probes/value")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        result = build_agent_value_report(
            meta_snapshot=resolve_path(args.meta_snapshot),
            roster_json=resolve_path(args.roster_json),
            output_dir=resolve_path(args.output_dir),
        )
    except AgentValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"value_json: {result['output_json']}")
    print(f"value_markdown: {result['output_markdown']}")
    print(f"owned_count: {result['summary']['owned_count']}")
    print(f"unmapped_count: {result['summary']['unmapped_count']}")
    for mode, rec in result.get("team_recommendations", {}).items():
        print(f"{mode}_owned_candidates: {rec.get('owned_candidate_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
