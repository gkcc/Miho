from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id, parse_percent

from .box import BoxProfile, load_config
from .investment import compare_stages, evaluate_investment
from .replacement import evaluate_replacement_risk

DECISION_ORDER = {"抽": 0, "等实测": 1, "停止加仓": 2, "不抽": 3}


def load_rules(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    rules_path = Path(path)
    if not rules_path.exists():
        return {}
    return load_config(rules_path)


def build_decision_cards(out_dir: str | Path, box: BoxProfile, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or {}
    data = load_decision_data(out_dir)
    tier_index = build_tier_index(data["tier_rows"], data["name_rows"])
    candidate_configs = build_candidate_configs(box, tier_index, rules)
    cards: list[dict[str, Any]] = []
    for candidate in candidate_configs:
        slug = normalize_character_id(candidate.get("slug"))
        if not slug:
            continue
        meta = tier_index.get(slug, _meta_from_candidate(candidate, data["name_rows"]))
        owned_agent = box.owned(slug)
        history = summarize_history(slug, data)
        replacement = evaluate_replacement_risk(slug, meta, box, tier_index)
        investment = evaluate_investment(owned_agent, rules)
        candidate_type = str(candidate.get("banner_type") or candidate.get("release_type") or _infer_candidate_type(meta, history))
        release_risk = evaluate_release_risk(candidate_type, history)
        decision, reasons, warnings, score = decide_candidate(
            candidate=candidate,
            meta=meta,
            owned_agent=owned_agent,
            history=history,
            replacement=replacement,
            investment=investment,
            rules=rules,
        )
        max_stage = str(candidate.get("max_recommended_stage") or rules.get("default_max_recommended_stage") or "0+1")
        stage_comparison = compare_stages(
            agent=owned_agent,
            decision=decision,
            max_recommended_stage=max_stage,
            rules=rules,
        )
        cards.append(
            {
                "slug": slug,
                "name_cn": meta.get("character_name_cn") or candidate.get("name_cn") or meta.get("character_name_en") or slug,
                "name_en": meta.get("character_name_en") or candidate.get("name_en") or "",
                "owned": bool(owned_agent and owned_agent.owned),
                "current_stage": owned_agent.stage if owned_agent and owned_agent.owned else "未拥有",
                "candidate_type": candidate_type,
                "decision": decision,
                "decision_score": score,
                "decision_reasons": reasons,
                "warnings": warnings,
                "tier_summary": {
                    "best_tier": meta.get("best_tier", ""),
                    "best_rating": meta.get("best_rating", ""),
                    "modes": meta.get("modes", {}),
                    "role_group": meta.get("role_group", ""),
                    "role_group_cn": meta.get("role_group_cn", ""),
                    "element": meta.get("element", ""),
                    "element_cn": meta.get("element_cn", ""),
                    "style": meta.get("style", ""),
                    "style_cn": meta.get("style_cn", ""),
                    "rarity": meta.get("rarity", ""),
                },
                "history_summary": history,
                "release_risk": release_risk,
                "replacement_risk": replacement,
                "investment": investment,
                "stage_comparison": stage_comparison,
                "notes": candidate.get("notes", ""),
                "source": candidate.get("source", "generated_from_local_tier"),
            }
        )
    cards.sort(key=lambda card: (DECISION_ORDER.get(str(card["decision"]), 9), -_float(card["decision_score"]), card["slug"]))
    return {
        "summary": build_summary(cards, box, data),
        "cards": cards,
    }


def load_decision_data(out_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    out = Path(out_dir)
    return {
        "tier_rows": _read_csv(out / "prydwen_tier_current.csv"),
        "tier_history_rows": _read_csv(out / "prydwen_tier_history.csv"),
        "usage_rows": _read_csv(out / "character_usage_long.csv"),
        "team_rows": _read_csv(out / "team_rank_raw.csv"),
        "name_rows": _read_csv(out / "name_map.csv"),
        "changelog_rows": _read_csv(out / "prydwen_tier_changelog_history.csv"),
    }


def build_tier_index(tier_rows: list[dict[str, Any]], name_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    names = {normalize_character_id(row.get("character_slug")): row for row in name_rows}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tier_rows:
        slug = normalize_character_id(row.get("character_slug"))
        if slug:
            grouped[slug].append(row)
    output: dict[str, dict[str, Any]] = {}
    for slug, rows in grouped.items():
        best = sorted(rows, key=lambda row: _float(row.get("rating")), reverse=True)[0]
        name = names.get(slug, {})
        modes = {}
        for row in rows:
            mode = str(row.get("tier_mode") or "")
            if not mode:
                continue
            current = modes.get(mode)
            if current is None or _float(row.get("rating")) > _float(current.get("rating")):
                modes[mode] = {
                    "mode_cn": row.get("tier_mode_cn", ""),
                    "tier": row.get("tier", ""),
                    "rating": _float(row.get("rating")),
                    "role_group_cn": row.get("role_group_cn", ""),
                }
        output[slug] = {
            **best,
            "character_slug": slug,
            "character_name_cn": best.get("character_name_cn") or name.get("character_name_cn") or "",
            "character_name_en": best.get("character_name_en") or name.get("character_name_en") or "",
            "best_tier": best.get("tier", ""),
            "best_rating": _float(best.get("rating")),
            "modes": modes,
        }
    return output


def build_candidate_configs(
    box: BoxProfile,
    tier_index: dict[str, dict[str, Any]],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    configured = _candidate_rows(rules.get("candidates"))
    configs: dict[str, dict[str, Any]] = {}
    for row in configured:
        slug = normalize_character_id(row.get("slug") or row.get("character_slug") or row.get("name"))
        if slug:
            configs[slug] = {"slug": slug, "source": "rules", **row}
    min_rating = _float(rules.get("candidate_min_rating", 9))
    generated: list[dict[str, Any]] = []
    for slug, meta in tier_index.items():
        if _float(meta.get("best_rating")) >= min_rating or box.has(slug):
            generated.append({"slug": slug, "source": "generated_from_local_tier"})
    generated.sort(key=lambda row: (-_float(tier_index.get(row["slug"], {}).get("best_rating")), row["slug"]))
    limit = int(_float(rules.get("max_generated_candidates", 30)) or 30)
    for row in generated[:limit]:
        configs.setdefault(row["slug"], row)
    for slug in box.agents:
        if slug in tier_index:
            configs.setdefault(slug, {"slug": slug, "source": "owned_from_box"})
    return list(configs.values())


def summarize_history(slug: str, data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    usage_rows = [row for row in data["usage_rows"] if normalize_character_id(row.get("character_slug")) == slug]
    team_rows = [
        row
        for row in data["team_rows"]
        if slug in {normalize_character_id(row.get("char_1_slug")), normalize_character_id(row.get("char_2_slug")), normalize_character_id(row.get("char_3_slug"))}
    ]
    modes: dict[str, dict[str, Any]] = {}
    for mode, rows in _group_by(usage_rows, "mode").items():
        primary = [row for row in rows if str(row.get("sub_mode") or "") == "all"] or rows
        by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in primary:
            by_date[str(row.get("collect_date") or "")].append(row)
        points: list[tuple[str, float]] = []
        for collect_date, dated_rows in by_date.items():
            value = max(_float(row.get("app_rate")) for row in dated_rows)
            points.append((collect_date, value))
        points.sort(key=lambda item: item[0])
        values = [value for _, value in points]
        if not values:
            continue
        latest_date, latest_value = points[-1]
        modes[mode] = {
            "mode_cn": rows[0].get("mode_cn", mode),
            "points": len(points),
            "latest_collect_date": latest_date,
            "latest_app_rate": latest_value,
            "avg_last3_app_rate": round(sum(values[-3:]) / min(3, len(values)), 3),
            "peak_app_rate": max(values),
            "trend_delta": round(values[-1] - values[0], 3) if len(values) >= 2 else 0,
        }
    best_team_rank = min((_float(row.get("rank")) for row in team_rows if row.get("rank") not in {None, ""}), default=0)
    latest_teams = sorted(team_rows, key=lambda row: (str(row.get("collect_date") or ""), -_float(row.get("app_rate"))), reverse=True)[:5]
    changelog_hits = [
        row
        for row in data["changelog_rows"]
        if slug in str(row.get("character_slugs") or "") or slug.replace("-", " ") in str(row.get("text") or "").lower()
    ]
    return {
        "usage_points": sum(mode["points"] for mode in modes.values()),
        "modes": modes,
        "team_appearances": len(team_rows),
        "best_team_rank": int(best_team_rank) if best_team_rank else "",
        "latest_team_examples": [_team_label(row) for row in latest_teams],
        "changelog_mentions": len(changelog_hits),
        "changelog_latest": (changelog_hits[0].get("changelog_date") if changelog_hits else ""),
    }


def decide_candidate(
    *,
    candidate: dict[str, Any],
    meta: dict[str, Any],
    owned_agent: Any,
    history: dict[str, Any],
    replacement: dict[str, Any],
    investment: dict[str, Any],
    rules: dict[str, Any],
) -> tuple[str, list[str], list[str], float]:
    rating = _float(meta.get("best_rating"))
    owned = bool(owned_agent and owned_agent.owned)
    candidate_type = str(candidate.get("banner_type") or candidate.get("release_type") or _infer_candidate_type(meta, history))
    usage_points = int(history.get("usage_points") or 0)
    replacement_level = str(replacement.get("level") or "")
    low_tier_warning_rating = _float(rules.get("low_tier_warning_rating", 9))
    pull_rating = _float(rules.get("pull_rating", 10))
    skip_rating = _float(rules.get("skip_rating", 8))
    trend_warning_delta = _float(rules.get("trend_warning_delta", -5))
    min_pull_avg_usage = _float(rules.get("min_pull_avg_usage", 5))
    bad_trend_block_delta = _float(rules.get("bad_trend_block_delta", -10))
    bad_trend_block_avg_usage = _float(rules.get("bad_trend_block_avg_usage", 20))
    avg_usage = _max_avg_usage(history)
    worst_trend = _worst_trend(history)
    reasons: list[str] = []
    warnings: list[str] = []
    score = round(rating * 10 + min(avg_usage, 30), 2)

    forced = str(candidate.get("force_decision") or "")
    if forced:
        reasons.append("规则配置指定了决策结论")
        return forced, reasons, warnings, score

    if rating and rating <= low_tier_warning_rating:
        warnings.append(f"当前最好定位为 {meta.get('best_tier') or '低评级'}，属于 T1 或以下，投入前要谨慎")
        score -= 8
    if worst_trend <= trend_warning_delta:
        warnings.append("近半年出场率走势明显下滑")
        score -= 6
    if usage_points > 0 and avg_usage < min_pull_avg_usage:
        warnings.append(f"近三期最高均值出场率低于 {min_pull_avg_usage}%")
        score -= 10
    if replacement_level == "高":
        warnings.append(replacement.get("reason", "存在较强替代"))
        score -= 8
    if investment.get("warnings") and owned:
        warnings.extend(investment["warnings"])

    current_stage = _stage_tuple(owned_agent.stage if owned_agent and owned_agent.owned else "-1+0")
    max_stage = _stage_tuple(str(candidate.get("max_recommended_stage") or rules.get("default_max_recommended_stage") or "0+1"))
    if owned and current_stage >= max_stage:
        reasons.append(f"本地 Box 已达到 {owned_agent.stage}，第一版规则认为无需继续加仓")
        return "停止加仓", reasons, warnings, score

    if candidate_type in {"new", "satellite", "新角色", "卫星"} or (usage_points == 0 and not owned):
        reasons.append("本地高难历史不足，无法验证真实出场率和队伍稳定性")
        return "等实测", reasons, warnings, score - 10

    if owned:
        if rating >= pull_rating and current_stage < max_stage and candidate.get("allow_additional_copies"):
            reasons.append("已拥有但规则允许补到目标档位")
            return "抽", reasons, warnings, score
        reasons.append("已拥有角色优先补练度；命座/专武继续投入先暂停")
        return "停止加仓", reasons, warnings, score

    if usage_points > 0 and avg_usage < min_pull_avg_usage:
        reasons.append("本地出场率过低，暂不进入抽取推荐")
        return "不抽", reasons, warnings, score
    if worst_trend <= bad_trend_block_delta and avg_usage < bad_trend_block_avg_usage:
        reasons.append("近期走势下滑且当前出场率不足以支撑推荐")
        return "不抽", reasons, warnings, score
    if rating >= pull_rating and replacement_level != "高":
        reasons.append(f"当前最好评级 {meta.get('best_tier')}，且 Box 内替代压力不高")
        return "抽", reasons, warnings, score
    if rating <= skip_rating or replacement_level == "高":
        reasons.append("评级或替代收益不足，当前不作为抽取目标")
        return "不抽", reasons, warnings, score
    reasons.append("强度未到必抽线，除非 XP 或当期环境点名")
    return "不抽", reasons, warnings, score


def evaluate_release_risk(candidate_type: str, history: dict[str, Any]) -> dict[str, str]:
    usage_points = int(history.get("usage_points") or 0)
    normalized = str(candidate_type or "").lower()
    if normalized in {"new", "新角色"}:
        return {"level": "高", "reason": "新角色缺少完整高难周期样本，优先等实测"}
    if normalized in {"satellite", "卫星"}:
        return {"level": "高", "reason": "卫星信息不可验证，不能按正式强度处理"}
    if usage_points == 0:
        return {"level": "中", "reason": "本地数据中暂无出场历史"}
    return {"level": "低", "reason": "已有本地高难历史可参考"}


def build_summary(cards: list[dict[str, Any]], box: BoxProfile, data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for card in cards:
        counts[str(card.get("decision") or "")] += 1
    return {
        "owned_agents": sum(1 for agent in box.agents.values() if agent.owned),
        "candidate_count": len(cards),
        "decision_counts": dict(counts),
        "data_rows": {
            "tier_current": len(data["tier_rows"]),
            "usage": len(data["usage_rows"]),
            "teams": len(data["team_rows"]),
            "changelog": len(data["changelog_rows"]),
        },
    }


def _meta_from_candidate(candidate: dict[str, Any], name_rows: list[dict[str, Any]]) -> dict[str, Any]:
    slug = normalize_character_id(candidate.get("slug"))
    name = {normalize_character_id(row.get("character_slug")): row for row in name_rows}.get(slug, {})
    return {
        "character_slug": slug,
        "character_name_cn": candidate.get("name_cn") or name.get("character_name_cn") or "",
        "character_name_en": candidate.get("name_en") or name.get("character_name_en") or "",
        "best_tier": "",
        "best_rating": 0,
        "modes": {},
        "role_group": candidate.get("role_group") or "",
        "role_group_cn": candidate.get("role_group_cn") or "",
        "element": candidate.get("element") or "",
        "element_cn": candidate.get("element_cn") or "",
        "style": candidate.get("style") or "",
        "style_cn": candidate.get("style_cn") or "",
        "rarity": candidate.get("rarity") or "",
    }


def _infer_candidate_type(meta: dict[str, Any], history: dict[str, Any]) -> str:
    if str(meta.get("is_new") or "").lower() in {"true", "1", "yes"}:
        return "new"
    if int(history.get("usage_points") or 0) > 0:
        return "rerun_or_existing"
    return "unknown"


def _candidate_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows = []
        for slug, item in value.items():
            rows.append({"slug": slug, **(dict(item) if isinstance(item, dict) else {})})
        return rows
    return []


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "")].append(row)
    return groups


def _team_label(row: dict[str, Any]) -> dict[str, Any]:
    names = [
        row.get("char_1_name_cn") or row.get("char_1_slug"),
        row.get("char_2_name_cn") or row.get("char_2_slug"),
        row.get("char_3_name_cn") or row.get("char_3_slug"),
    ]
    return {
        "collect_date": row.get("collect_date", ""),
        "mode_cn": row.get("mode_cn", ""),
        "sub_mode_cn": row.get("sub_mode_cn", ""),
        "rank": row.get("rank", ""),
        "app_rate": parse_percent(row.get("app_rate")),
        "team": " / ".join(str(name) for name in names if name),
    }


def _max_avg_usage(history: dict[str, Any]) -> float:
    modes = history.get("modes") or {}
    if not isinstance(modes, dict) or not modes:
        return 0.0
    return max(_float(mode.get("avg_last3_app_rate")) for mode in modes.values() if isinstance(mode, dict))


def _worst_trend(history: dict[str, Any]) -> float:
    modes = history.get("modes") or {}
    if not isinstance(modes, dict) or not modes:
        return 0.0
    return min(_float(mode.get("trend_delta")) for mode in modes.values() if isinstance(mode, dict))


def _stage_tuple(value: str) -> tuple[int, int]:
    try:
        left, right = str(value).split("+", 1)
        return int(left), int(right)
    except (TypeError, ValueError):
        return -1, 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
