#!/usr/bin/env python
"""Generate a local P1.2 draft training priority report from normalized snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "planner"
DEFAULT_DAILY_STAMINA = 240
DEFAULT_HORIZON_DAYS = 7
CURRENT_TARGET_SOURCE_TYPES = {"official_current", "official_snapshot", "public_web_snapshot"}
LOCAL_DRAFT_SOURCE_TYPES = {"manual", "mock", "local_mock", "draft"}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


class PlannerError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PlannerError(f"JSON file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlannerError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise PlannerError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def field_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status") or "")
    return "ok" if value not in (None, "", []) else "missing"


def field_uncertain(value: Any) -> bool:
    return bool(value.get("uncertain")) if isinstance(value, dict) else False


def as_number(value: Any) -> float | None:
    raw = field_value(value)
    if raw in (None, "", []):
        return None
    text = str(raw).replace("%", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def positive_number(value: Any, default: float) -> float:
    parsed = as_number(value)
    if parsed is None:
        return default
    return parsed if parsed > 0 else default


def field_trusted(value: Any) -> bool:
    return field_status(value) == "ok" and not field_uncertain(value)


def character_name(snapshot: dict[str, Any]) -> str:
    name = field_value(snapshot.get("character", {}).get("name"))
    return str(name) if name else "unknown_character"


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]
    result = []
    for item in raw_items:
        text = str(field_value(item) or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def catalog_entries(character_catalog: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(character_catalog, dict):
        return []
    entries = character_catalog.get("entries")
    return entries if isinstance(entries, list) else []


def catalog_entry_for_character(name: str, character_catalog: dict[str, Any] | None) -> dict[str, Any] | None:
    wanted = str(name).strip().lower()
    if not wanted:
        return None
    for entry in catalog_entries(character_catalog):
        if not isinstance(entry, dict):
            continue
        names = normalize_list(entry.get("name")) + normalize_list(entry.get("aliases"))
        if wanted in {item.lower() for item in names}:
            return entry
    return None


def catalog_combat_tags(entry: dict[str, Any] | None) -> set[str]:
    if not isinstance(entry, dict):
        return set()
    tags: set[str] = set()
    for key in ("tags", "combat_tags", "element_tags", "role_tags", "mechanic_tags"):
        tags.update(normalize_list(entry.get(key)))
    for key in ("element", "attribute", "role", "path"):
        tags.update(normalize_list(entry.get(key)))
    return {tag.lower() for tag in tags}


def catalog_entry_name(entry: dict[str, Any]) -> str:
    names = normalize_list(entry.get("name"))
    return names[0] if names else "unknown_character"


def catalog_entry_names(entry: dict[str, Any]) -> list[str]:
    return normalize_list(entry.get("name")) + normalize_list(entry.get("aliases"))


def load_manifest_snapshots(manifest: Path) -> list[Path]:
    data = load_json(manifest)
    raw = data.get("snapshots")
    if not isinstance(raw, list):
        raise PlannerError("Snapshot manifest must contain a snapshots list")
    paths = []
    for item in raw:
        if isinstance(item, str):
            paths.append(resolve_path(item))
        elif isinstance(item, dict) and item.get("path"):
            paths.append(resolve_path(str(item["path"])))
        else:
            raise PlannerError("Each snapshot manifest item must be a path string or object with path")
    return paths


def load_targets(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data.get("targets"), list):
        raise PlannerError("Targets JSON must contain a targets list")
    return data


def load_character_catalog(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    data = load_json(path)
    raw = data.get("characters", data)
    entries: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for name, value in raw.items():
            if isinstance(value, dict):
                entry = dict(value)
                entry.setdefault("name", name)
            elif isinstance(value, list):
                entry = {"name": name, "combat_tags": value}
            else:
                entry = {"name": name, "combat_tags": [value]}
            entries.append(entry)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                entries.append(dict(item))
    else:
        raise PlannerError("Character catalog must be an object, a characters object, or a characters list")
    return {"path": str(path), "entries": entries}


def load_history_index(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data.get("characters"), dict):
        raise PlannerError("History index JSON must contain a characters object")
    return data


def history_items_by_character(history_context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(history_context, dict):
        return {}
    items = history_context.get("items")
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        character = str(item.get("character") or "")
        if character:
            result[character] = item
    return result


def history_index_by_character(history_index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(history_index, dict):
        return {}
    characters = history_index.get("characters")
    if not isinstance(characters, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in characters.values():
        if not isinstance(entry, dict):
            continue
        character = str(entry.get("character") or "")
        if character:
            result[character] = entry
    return result


def history_for_character(
    name: str,
    *,
    history_context: dict[str, Any] | None = None,
    history_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context_item = history_items_by_character(history_context).get(name)
    index_item = history_index_by_character(history_index).get(name)
    if context_item:
        return {
            "tracked": True,
            "status": context_item.get("status") or "tracked",
            "recent_change_count": int(context_item.get("change_count") or 0),
            "recent_requires_review_change_count": int(context_item.get("requires_review_change_count") or 0),
            "current_snapshot": context_item.get("current_snapshot"),
            "previous_snapshot": context_item.get("previous_snapshot"),
            "diff_md": context_item.get("diff_md"),
            "last_seen_at": index_item.get("last_seen_at") if index_item else None,
        }
    if index_item:
        return {
            "tracked": True,
            "status": "indexed",
            "recent_change_count": 0,
            "recent_requires_review_change_count": 0,
            "current_snapshot": index_item.get("latest_snapshot"),
            "previous_snapshot": None,
            "diff_md": None,
            "last_seen_at": index_item.get("last_seen_at"),
        }
    return {
        "tracked": False,
        "status": "not_tracked",
        "recent_change_count": 0,
        "recent_requires_review_change_count": 0,
        "current_snapshot": None,
        "previous_snapshot": None,
        "diff_md": None,
        "last_seen_at": None,
    }


def snapshot_combat_tags(snapshot: dict[str, Any], catalog_entry: dict[str, Any] | None = None) -> set[str]:
    tags: set[str] = set()
    character = snapshot.get("character", {}) if isinstance(snapshot.get("character"), dict) else {}
    for key in ("tags", "combat_tags", "element_tags", "role_tags"):
        tags.update(normalize_list(snapshot.get(key)))
        tags.update(normalize_list(character.get(key)))
    for key in ("element", "attribute", "role", "path"):
        tags.update(normalize_list(character.get(key)))
    tags.update(catalog_combat_tags(catalog_entry))
    return {tag.lower() for tag in tags}


def target_tags(target: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for key in ("weakness_tags", "mechanic_tags", "preferred_tags", "required_tags"):
        tags.update(normalize_list(target.get(key)))
    templates = target.get("recommended_team_templates")
    if isinstance(templates, list):
        for template in templates:
            if isinstance(template, dict):
                for key in ("weakness_tags", "mechanic_tags", "preferred_tags", "required_tags"):
                    tags.update(normalize_list(template.get(key)))
    return {tag.lower() for tag in tags}


def target_match_details(
    snapshot: dict[str, Any],
    targets: dict[str, Any],
    character_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    name = character_name(snapshot)
    catalog_entry = catalog_entry_for_character(name, character_catalog)
    character_tags = snapshot_combat_tags(snapshot, catalog_entry)
    matched: list[dict[str, Any]] = []
    for target in targets.get("targets", []):
        if not isinstance(target, dict):
            continue
        preferred = target.get("preferred_characters")
        if isinstance(preferred, list) and name in {str(item) for item in preferred}:
            matched.append(
                {
                    "target": target,
                    "match_type": "preferred_character",
                    "score": 100,
                    "matched_tags": [],
                    "reason": "角色在目标 preferred_characters 中。",
                }
            )
            continue
        templates = target.get("recommended_team_templates")
        if isinstance(templates, list):
            template_matched = False
            for template in templates:
                if isinstance(template, dict) and name in {str(item) for item in template.get("preferred_characters", [])}:
                    matched.append(
                        {
                            "target": target,
                            "match_type": "team_template",
                            "score": 90,
                            "matched_tags": [],
                            "reason": "角色在推荐队伍模板中。",
                        }
                    )
                    template_matched = True
                    break
            if template_matched:
                continue
        overlap = sorted(character_tags & target_tags(target))
        if overlap:
            matched.append(
                {
                    "target": target,
                    "match_type": "tag_overlap",
                    "score": min(80, 35 + len(overlap) * 15),
                    "matched_tags": overlap,
                    "reason": "角色标签命中目标弱点/机制：" + "、".join(overlap),
                }
            )
    matched.sort(key=lambda item: (-int(item["score"]), str(item["target"].get("goal_id") or "")))
    return matched


def match_targets(
    snapshot: dict[str, Any],
    targets: dict[str, Any],
    character_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [item["target"] for item in target_match_details(snapshot, targets, character_catalog)]


def target_priority(targets: list[dict[str, Any]]) -> int:
    if not targets:
        return 1
    priority_map = {"high": 3, "medium": 2, "low": 1}
    return max(priority_map.get(str(target.get("priority") or "medium"), 2) for target in targets)


def target_label(target: dict[str, Any]) -> str:
    activity = target.get("activity_name") or target.get("goal_id") or "unknown_goal"
    tier = target.get("target_tier")
    return f"{activity} {tier}".strip()


def target_names(targets: list[dict[str, Any]]) -> list[str]:
    return [target_label(target) for target in targets]


def target_match_summaries(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for detail in details:
        target = detail.get("target") if isinstance(detail.get("target"), dict) else {}
        summaries.append(
            {
                "target": target_label(target),
                "match_type": detail.get("match_type"),
                "score": detail.get("score"),
                "matched_tags": detail.get("matched_tags", []),
                "reason": detail.get("reason"),
            }
        )
    return summaries


def target_evidence_summary(target: dict[str, Any]) -> dict[str, Any]:
    evidence = target.get("evidence") if isinstance(target.get("evidence"), dict) else {}
    content_hash = str(evidence.get("content_sha256") or "")
    return {
        "source_index": evidence.get("source_index"),
        "source_kind": evidence.get("source_kind"),
        "source_ref": evidence.get("source_ref"),
        "title": evidence.get("title"),
        "content_sha256": content_hash or None,
        "content_sha256_short": content_hash[:12] if content_hash else None,
        "excerpt": evidence.get("excerpt"),
        "matched_aliases": evidence.get("matched_aliases") if isinstance(evidence.get("matched_aliases"), dict) else {},
    }


def alias_evidence_text(matched_aliases: dict[str, Any]) -> str:
    parts = []
    activity = matched_aliases.get("activity")
    if isinstance(activity, list) and activity:
        parts.append("activity=" + "、".join(str(item) for item in activity))
    for group_name in ("weakness_tags", "mechanic_tags"):
        group = matched_aliases.get(group_name)
        if not isinstance(group, dict):
            continue
        for tag, aliases in group.items():
            if isinstance(aliases, list) and aliases:
                parts.append(f"{tag}=" + "、".join(str(item) for item in aliases))
    return "；".join(parts)


def catalog_candidates_for_target(
    target: dict[str, Any],
    character_catalog: dict[str, Any] | None,
    current_characters: set[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    needed_tags = target_tags(target)
    preferred = {str(item).strip().lower() for item in normalize_list(target.get("preferred_characters"))}
    template_names: set[str] = set()
    templates = target.get("recommended_team_templates")
    if isinstance(templates, list):
        for template in templates:
            if isinstance(template, dict):
                template_names.update(str(item).strip().lower() for item in normalize_list(template.get("preferred_characters")))
    if not needed_tags and not preferred and not template_names:
        return []
    candidates = []
    for entry in catalog_entries(character_catalog):
        if not isinstance(entry, dict):
            continue
        name = catalog_entry_name(entry)
        entry_names = {item.lower() for item in catalog_entry_names(entry)}
        reasons = []
        match_types = []
        score = 0
        if preferred & entry_names:
            score = max(score, 95)
            match_types.append("preferred_character")
            reasons.append("角色在目标 preferred_characters 中")
        if template_names & entry_names:
            score = max(score, 90)
            match_types.append("team_template")
            reasons.append("角色在推荐队伍模板中")
        tags = catalog_combat_tags(entry)
        overlap = sorted(tags & needed_tags)
        if overlap:
            score = max(score, min(80, 30 + len(overlap) * 15))
            match_types.append("tag_overlap")
            reasons.append("catalog 标签命中目标弱点/机制：" + "、".join(overlap))
        if not match_types:
            continue
        candidates.append(
            {
                "character": name,
                "match_types": match_types,
                "matched_tags": overlap,
                "score": score,
                "in_current_snapshots": name in current_characters,
                "owned": bool(entry.get("owned")) if "owned" in entry else None,
                "reason": "；".join(reasons),
            }
        )
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["character"])))
    return candidates[:limit]


def target_coverage_summary(
    targets: dict[str, Any],
    character_reports: list[dict[str, Any]],
    character_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    coverage = []
    raw_targets = targets.get("targets") if isinstance(targets.get("targets"), list) else []
    current_characters = {str(report.get("character")) for report in character_reports if report.get("character")}
    for target in raw_targets:
        if not isinstance(target, dict):
            continue
        label = target_label(target)
        matches = []
        for report in character_reports:
            for match in report.get("target_matches", []):
                if isinstance(match, dict) and match.get("target") == label:
                    matches.append(
                        {
                            "character": report.get("character"),
                            "match_type": match.get("match_type"),
                            "score": match.get("score"),
                            "matched_tags": match.get("matched_tags", []),
                            "reason": match.get("reason"),
                        }
                    )
        matches.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("character") or "")))
        catalog_candidates = [] if matches else catalog_candidates_for_target(target, character_catalog, current_characters)
        coverage.append(
            {
                "target": label,
                "goal_id": target.get("goal_id"),
                "activity_name": target.get("activity_name"),
                "target_tier": target.get("target_tier"),
                "priority": target.get("priority"),
                "weakness_tags": normalize_list(target.get("weakness_tags")),
                "mechanic_tags": normalize_list(target.get("mechanic_tags")),
                "coverage_status": "covered" if matches else "unmatched",
                "match_count": len(matches),
                "matched_characters": matches,
                "catalog_candidates": catalog_candidates,
                "evidence": target_evidence_summary(target),
            }
        )
    return coverage


def minimums_for_targets(targets: list[dict[str, Any]], defaults: dict[str, Any]) -> dict[str, Any]:
    minimums = dict(defaults)
    for target in targets:
        raw = target.get("minimums")
        if isinstance(raw, dict):
            minimums.update(raw)
    return minimums


def target_source_status(targets: dict[str, Any]) -> dict[str, Any]:
    source = targets.get("source") if isinstance(targets.get("source"), dict) else {}
    freshness = targets.get("freshness") if isinstance(targets.get("freshness"), dict) else {}
    source_type = str(source.get("type") or "unknown")
    freshness_level = str(freshness.get("level") or "unknown")
    stale_count = int(freshness.get("stale_source_count") or 0) if freshness else 0

    if source_type in LOCAL_DRAFT_SOURCE_TYPES:
        status = "local_draft"
        confidence = "low"
        current_ready = False
        reason = "终局目标来自本地配置或 mock，不能代表当前线上高难。"
    elif freshness_level == "stale" or stale_count:
        status = "stale"
        confidence = "low"
        current_ready = False
        reason = "终局目标来源已过期，当前高难配队建议需要先刷新来源。"
    elif source_type in CURRENT_TARGET_SOURCE_TYPES and freshness_level == "fresh":
        status = "current"
        confidence = "high"
        current_ready = True
        reason = "终局目标来源新鲜，可作为当前高难候选输入。"
    elif source_type in CURRENT_TARGET_SOURCE_TYPES:
        status = "needs_freshness"
        confidence = "medium"
        current_ready = False
        reason = "终局目标来源类型可用，但缺少 freshness 证明，不能直接当作当前高难事实。"
    else:
        status = "unverified"
        confidence = "low"
        current_ready = False
        reason = "终局目标来源类型未验证，建议只能作为本地草案。"

    return {
        "source_type": source_type,
        "status": status,
        "freshness_level": freshness_level,
        "stale_source_count": stale_count,
        "current_endgame_ready": current_ready,
        "planning_confidence": confidence,
        "reason": reason,
    }


def cap_confidence(value: str, cap: str) -> str:
    current_rank = CONFIDENCE_ORDER.get(str(value), 1)
    cap_rank = CONFIDENCE_ORDER.get(str(cap), 1)
    for name, rank in CONFIDENCE_ORDER.items():
        if rank == min(current_rank, cap_rank):
            return name
    return "low"


def source_confidence_note(source_status: dict[str, Any]) -> str:
    status = source_status.get("status")
    if status == "current":
        return ""
    reason = source_status.get("reason")
    return str(reason) if reason else "目标来源未达到当前高难可用标准。"


def add_gap(gaps: list[dict[str, Any]], *, kind: str, severity: int, action: str, reason: str, estimated_days: float, confidence: str) -> None:
    gaps.append(
        {
            "gap_type": kind,
            "severity": severity,
            "action": action,
            "reason": reason,
            "estimated_days": estimated_days,
            "confidence": confidence,
        }
    )


def skill_levels(snapshot: dict[str, Any]) -> list[float]:
    raw = snapshot.get("build_snapshot", {}).get("skill_levels", [])
    if not isinstance(raw, list):
        return []
    levels = []
    for item in raw:
        if isinstance(item, dict):
            level = as_number(item.get("level"))
            if level is not None:
                levels.append(level)
    return levels


def drive_disc_levels(snapshot: dict[str, Any]) -> list[float]:
    raw = snapshot.get("build_snapshot", {}).get("drive_discs", [])
    if not isinstance(raw, list):
        return []
    levels = []
    for item in raw:
        if isinstance(item, dict):
            level = as_number(item.get("level"))
            if level is not None:
                levels.append(level)
    return levels


def drive_disc_quality_gaps(snapshot: dict[str, Any]) -> tuple[int, int]:
    raw = snapshot.get("build_snapshot", {}).get("drive_discs", [])
    if not isinstance(raw, list):
        return 6, 6
    missing_main = 0
    missing_subs = 0
    if len(raw) < 6:
        missing_main += 6 - len(raw)
        missing_subs += 6 - len(raw)
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not field_trusted(item.get("main_stat")):
            missing_main += 1
        sub_stats = item.get("sub_stats")
        if not isinstance(sub_stats, list) or not sub_stats:
            missing_subs += 1
    return missing_main, missing_subs


def stat_gaps(snapshot: dict[str, Any], minimums: dict[str, Any]) -> list[dict[str, Any]]:
    stats = snapshot.get("build_snapshot", {}).get("stats", {})
    if not isinstance(stats, dict):
        return []
    gaps = []
    min_stats = minimums.get("stats")
    if not isinstance(min_stats, dict):
        return gaps
    for stat_name, min_value in min_stats.items():
        current = as_number(stats.get(str(stat_name)))
        required = as_number(min_value)
        if current is None or required is None:
            continue
        if current < required:
            gaps.append(
                {
                    "stat": str(stat_name),
                    "current": current,
                    "required": required,
                    "missing": round(required - current, 2),
                }
            )
    return gaps


def character_gaps(
    snapshot: dict[str, Any],
    targets: dict[str, Any],
    *,
    history_context: dict[str, Any] | None = None,
    history_index: dict[str, Any] | None = None,
    character_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = character_name(snapshot)
    catalog_entry = catalog_entry_for_character(name, character_catalog)
    match_details = target_match_details(snapshot, targets, character_catalog)
    matched_targets = [item["target"] for item in match_details]
    defaults = targets.get("default_minimums", {}) if isinstance(targets.get("default_minimums"), dict) else {}
    minimums = minimums_for_targets(matched_targets, defaults)
    gaps: list[dict[str, Any]] = []
    character = snapshot.get("character", {})
    build = snapshot.get("build_snapshot", {})
    equipment = build.get("equipment", {}) if isinstance(build.get("equipment"), dict) else {}
    quality = snapshot.get("quality", {}) if isinstance(snapshot.get("quality"), dict) else {}
    blocker_count = len(quality.get("blockers", [])) if isinstance(quality.get("blockers"), list) else 0
    priority = target_priority(matched_targets)
    history = history_for_character(name, history_context=history_context, history_index=history_index)

    if blocker_count:
        add_gap(
            gaps,
            kind="data_review",
            severity=4,
            action="先人工确认解析结果",
            reason=f"normalized quality 存在 {blocker_count} 个 blocker，不能把 OCR 结果直接当作养成规划依据。",
            estimated_days=0.0,
            confidence="high",
        )

    required_level = as_number(minimums.get("character_level"))
    current_level = as_number(character.get("level"))
    if required_level is not None and (current_level is None or current_level < required_level):
        missing = required_level if current_level is None else required_level - current_level
        add_gap(
            gaps,
            kind="character_level",
            severity=3 + priority,
            action=f"角色等级提升到 {int(required_level)}",
            reason=f"当前等级 {current_level if current_level is not None else '缺失'}，目标需要 {int(required_level)}。",
            estimated_days=max(1.0, round(missing / 10, 1)),
            confidence="medium" if current_level is not None else "low",
        )

    required_equipment = as_number(minimums.get("equipment_level"))
    current_equipment = as_number(equipment.get("level"))
    if required_equipment is not None and (current_equipment is None or current_equipment < required_equipment):
        missing = required_equipment if current_equipment is None else required_equipment - current_equipment
        add_gap(
            gaps,
            kind="equipment_level",
            severity=2 + priority,
            action=f"音擎等级提升到 {int(required_equipment)}",
            reason=f"当前音擎等级 {current_equipment if current_equipment is not None else '缺失'}，目标需要 {int(required_equipment)}。",
            estimated_days=max(1.0, round(missing / 15, 1)),
            confidence="medium" if current_equipment is not None else "low",
        )

    required_skill = as_number(minimums.get("skill_level"))
    levels = skill_levels(snapshot)
    low_skill_count = sum(1 for level in levels if required_skill is not None and level < required_skill)
    if required_skill is not None and low_skill_count:
        add_gap(
            gaps,
            kind="skill_level",
            severity=2 + priority,
            action=f"补关键技能到 {int(required_skill)} 左右",
            reason=f"{low_skill_count} 个技能低于目标线 {int(required_skill)}；优先补主输出或关键辅助技能。",
            estimated_days=round(low_skill_count * 0.5, 1),
            confidence="medium",
        )

    required_disc = as_number(minimums.get("drive_disc_level"))
    disc_levels = drive_disc_levels(snapshot)
    low_disc_count = sum(1 for level in disc_levels if required_disc is not None and level < required_disc)
    if required_disc is not None and low_disc_count:
        add_gap(
            gaps,
            kind="drive_disc_level",
            severity=1 + priority,
            action=f"驱动盘等级补到 +{int(required_disc)}",
            reason=f"{low_disc_count} 个驱动盘低于 +{int(required_disc)}，属于低成本补强项。",
            estimated_days=round(low_disc_count * 0.3, 1),
            confidence="medium",
        )

    missing_main, missing_subs = drive_disc_quality_gaps(snapshot)
    if missing_main or missing_subs >= 3:
        add_gap(
            gaps,
            kind="drive_disc_quality",
            severity=2 + priority,
            action="确认驱动盘主词条和副词条",
            reason=f"主词条不可信 {missing_main} 个，副词条缺失 {missing_subs} 个；先确认再决定是否刷盘。",
            estimated_days=0.0,
            confidence="high",
        )

    for gap in stat_gaps(snapshot, minimums):
        add_gap(
            gaps,
            kind=f"stat_{gap['stat']}",
            severity=2 + priority,
            action=f"补 {gap['stat']} 到 {gap['required']}",
            reason=f"当前 {gap['stat']}={gap['current']}，目标线 {gap['required']}，缺口 {gap['missing']}。",
            estimated_days=1.0,
            confidence="low",
        )

    return {
        "character": name,
        "catalog_match": {
            "matched": catalog_entry is not None,
            "catalog_name": catalog_entry.get("name") if isinstance(catalog_entry, dict) else None,
            "tags": sorted(catalog_combat_tags(catalog_entry)),
        },
        "matched_targets": target_names(matched_targets),
        "target_matches": target_match_summaries(match_details),
        "target_priority": priority,
        "quality_blockers": quality.get("blockers", []) if isinstance(quality.get("blockers"), list) else [],
        "history": history,
        "gaps": sorted(gaps, key=lambda item: (-int(item["severity"]), str(item["gap_type"]))),
    }


def plan_items(character_reports: list[dict[str, Any]], source_status: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items = []
    active_source_status = source_status or {}
    source_confidence = str(active_source_status.get("planning_confidence") or "medium")
    source_note = source_confidence_note(active_source_status)
    for report in character_reports:
        character = report["character"]
        matched_targets = report.get("matched_targets", [])
        target_label = "、".join(matched_targets) if matched_targets else "长期通用练度"
        match_reasons = [
            str(item.get("reason"))
            for item in report.get("target_matches", [])
            if isinstance(item, dict) and item.get("reason")
        ]
        history = report.get("history", {}) if isinstance(report.get("history"), dict) else {}
        recent_change_count = int(history.get("recent_change_count") or 0)
        continuity_bonus = min(3, recent_change_count)
        for gap in report.get("gaps", []):
            score = int(gap["severity"]) * 10 + int(report.get("target_priority", 1))
            if gap["gap_type"] == "data_review":
                score += 8
                item_bonus = 0
                reason = gap["reason"]
            else:
                item_bonus = continuity_bonus
                score += item_bonus
                reason = gap["reason"]
                if item_bonus:
                    reason = f"{reason} 历史快照显示近期已有 {recent_change_count} 项变化，适合延续投入。"
                if source_note:
                    reason = f"{reason} {source_note}"
            confidence = gap["confidence"] if gap["gap_type"] == "data_review" else cap_confidence(gap["confidence"], source_confidence)
            items.append(
                {
                    "priority_score": score,
                    "character": character,
                    "target": target_label,
                    "gap_type": gap["gap_type"],
                    "action": gap["action"],
                "reason": reason,
                "estimated_days": gap["estimated_days"],
                "confidence": confidence,
                "source_confidence": source_confidence,
                "target_source_status": active_source_status.get("status"),
                "target_match_reasons": match_reasons,
                "continuity_bonus": item_bonus,
                    "recent_change_count": recent_change_count,
                    "recent_diff_md": history.get("diff_md"),
                }
            )
    items.sort(key=lambda item: (-int(item["priority_score"]), str(item["character"]), str(item["gap_type"])))
    for index, item in enumerate(items, start=1):
        item["priority_rank"] = index
    return items


def build_warnings(
    targets: dict[str, Any],
    snapshots: list[dict[str, Any]],
    target_coverage: list[dict[str, Any]] | None = None,
) -> list[str]:
    warnings = []
    source_status = target_source_status(targets)
    if not source_status.get("current_endgame_ready"):
        warnings.append(str(source_status["reason"]))
    unmatched = [
        str(item.get("target"))
        for item in (target_coverage or [])
        if item.get("coverage_status") == "unmatched"
    ]
    if unmatched and source_status.get("current_endgame_ready"):
        warnings.append("当前高难目标暂无当前 box 匹配角色：" + "、".join(unmatched))
    candidate_notes = []
    for item in target_coverage or []:
        candidates = item.get("catalog_candidates") if isinstance(item.get("catalog_candidates"), list) else []
        if item.get("coverage_status") == "unmatched" and candidates:
            names = "、".join(str(candidate.get("character")) for candidate in candidates[:3] if isinstance(candidate, dict))
            if names:
                candidate_notes.append(f"{item.get('target')} -> {names}")
    if candidate_notes:
        warnings.append("未覆盖目标存在 catalog 候选，请确认是否拥有或补录分享图：" + "；".join(candidate_notes))
    if any(snapshot.get("quality", {}).get("requires_manual_review") for snapshot in snapshots if isinstance(snapshot.get("quality"), dict)):
        warnings.append("存在 requires_manual_review 的 normalized snapshot，规划建议只能作为人工确认前的候选。")
    return warnings


def build_coverage_gap_actions(target_coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for coverage in target_coverage:
        if coverage.get("coverage_status") != "unmatched":
            continue
        target = str(coverage.get("target") or "unknown_target")
        priority = str(coverage.get("priority") or "medium")
        candidates = coverage.get("catalog_candidates") if isinstance(coverage.get("catalog_candidates"), list) else []
        for candidate in candidates[:3]:
            if not isinstance(candidate, dict) or not candidate.get("character"):
                continue
            owned = candidate.get("owned")
            if owned is True:
                action_type = "record_owned_snapshot"
                action = "补录或更新该角色官方分享图"
                reason = "catalog 标记已拥有，但当前 snapshots 没有可用于该目标的练度快照。"
                confidence = "medium"
            elif owned is False:
                action_type = "long_term_candidate"
                action = "作为长期抽取或培养候选观察"
                reason = "catalog 标记未拥有；不能进入当前体力预算，只能作为长期补洞方向。"
                confidence = "low"
            else:
                action_type = "confirm_ownership"
                action = "先确认是否拥有，拥有后补录官方分享图"
                reason = "catalog 候选命中目标缺口，但 owned 状态未知，不能直接规划体力。"
                confidence = "low"
            actions.append(
                {
                    "target": target,
                    "target_priority": priority,
                    "character": candidate.get("character"),
                    "action_type": action_type,
                    "action": action,
                    "reason": reason,
                    "candidate_reason": candidate.get("reason"),
                    "matched_tags": candidate.get("matched_tags", []),
                    "match_types": candidate.get("match_types", []),
                    "candidate_score": candidate.get("score"),
                    "owned": owned,
                    "uses_stamina": False,
                    "confidence": confidence,
                }
            )
    priority_weight = {"high": 3, "medium": 2, "low": 1}
    actions.sort(
        key=lambda item: (
            -priority_weight.get(str(item.get("target_priority") or "medium"), 2),
            -int(item.get("candidate_score") or 0),
            str(item.get("target") or ""),
            str(item.get("character") or ""),
        )
    )
    for index, item in enumerate(actions, start=1):
        item["rank"] = index
    return actions


def resource_budget(targets: dict[str, Any], daily_stamina: float | None, horizon_days: float | None) -> dict[str, Any]:
    config = targets.get("resource_budget") if isinstance(targets.get("resource_budget"), dict) else {}
    daily = daily_stamina if daily_stamina is not None else positive_number(config.get("daily_stamina"), DEFAULT_DAILY_STAMINA)
    horizon = horizon_days if horizon_days is not None else positive_number(config.get("horizon_days"), DEFAULT_HORIZON_DAYS)
    if daily <= 0:
        raise PlannerError("daily_stamina must be positive")
    if horizon <= 0:
        raise PlannerError("horizon_days must be positive")
    horizon_int = max(1, int(round(horizon)))
    return {
        "daily_stamina": round(float(daily), 2),
        "horizon_days": horizon_int,
        "total_stamina": round(float(daily) * horizon_int, 2),
    }


def item_stamina_cost(item: dict[str, Any], daily_stamina: float) -> float:
    days = as_number(item.get("estimated_days")) or 0.0
    return round(max(0.0, days) * daily_stamina, 2)


def build_resource_plan(items: list[dict[str, Any]], budget: dict[str, Any]) -> dict[str, Any]:
    daily = float(budget["daily_stamina"])
    total = float(budget["total_stamina"])
    remaining = total
    today_remaining = daily
    today: list[dict[str, Any]] = []
    horizon: list[dict[str, Any]] = []
    no_stamina_actions: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    for item in items:
        cost = item_stamina_cost(item, daily)
        base = {
            "rank": item.get("priority_rank"),
            "character": item.get("character"),
            "action": item.get("action"),
            "gap_type": item.get("gap_type"),
            "priority_score": item.get("priority_score"),
            "estimated_days": item.get("estimated_days"),
            "estimated_stamina": cost,
        }
        if cost <= 0:
            no_stamina_actions.append({**base, "note": "不消耗体力，但需要人工确认或整理。"})
            continue
        allocated = min(cost, remaining)
        status = "planned" if allocated >= cost else "partial" if allocated > 0 else "overflow"
        entry = {
            **base,
            "allocated_stamina": round(allocated, 2),
            "planned_days": round(allocated / daily, 2) if daily else 0,
            "status": status,
        }
        if allocated > 0:
            horizon.append(entry)
            remaining -= allocated
        else:
            overflow.append(entry)
        today_allocated = min(cost, today_remaining)
        if today_allocated > 0:
            today.append(
                {
                    **base,
                    "allocated_stamina": round(today_allocated, 2),
                    "planned_days": round(today_allocated / daily, 2) if daily else 0,
                    "status": "today" if today_allocated >= cost else "today_partial",
                }
            )
            today_remaining -= today_allocated
    return {
        "budget": budget,
        "today": today,
        "horizon": horizon,
        "no_stamina_actions": no_stamina_actions,
        "overflow": overflow,
        "remaining_stamina": round(max(0.0, remaining), 2),
        "today_remaining_stamina": round(max(0.0, today_remaining), 2),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 本地培养优先级报告",
        "",
        "## 输入",
        f"- game: {report.get('game') or ''}",
        f"- snapshot_count: {len(report.get('snapshots', []))}",
        f"- target_source: {report.get('target_source', {}).get('type') or ''}",
        "",
    ]
    source_status = report.get("target_source_status", {}) if isinstance(report.get("target_source_status"), dict) else {}
    if source_status:
        lines.extend(
            [
                "## 目标来源状态",
                "",
                f"- status: {source_status.get('status')}",
                f"- freshness: {source_status.get('freshness_level')}",
                f"- current_endgame_ready: {source_status.get('current_endgame_ready')}",
                f"- planning_confidence: {source_status.get('planning_confidence')}",
                f"- reason: {source_status.get('reason')}",
                "",
            ]
        )
    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    coverage = report.get("target_coverage") if isinstance(report.get("target_coverage"), list) else []
    if coverage:
        lines.extend(["## 目标覆盖", "", "| target | status | matched characters | catalog candidates | tags |", "|---|---|---|---|---|"])
        for item in coverage:
            characters = "、".join(
                str(match.get("character"))
                for match in item.get("matched_characters", [])
                if isinstance(match, dict) and match.get("character")
            )
            candidates = "、".join(
                str(candidate.get("character"))
                for candidate in item.get("catalog_candidates", [])
                if isinstance(candidate, dict) and candidate.get("character")
            )
            tags = "、".join((item.get("weakness_tags") or []) + (item.get("mechanic_tags") or []))
            lines.append(
                f"| {item.get('target')} | {item.get('coverage_status')} | {characters or 'none'} | {candidates or 'none'} | {tags} |"
            )
        lines.append("")
        evidence_rows = []
        for item in coverage:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            if not evidence:
                continue
            alias_text = alias_evidence_text(evidence.get("matched_aliases", {})) if isinstance(evidence.get("matched_aliases"), dict) else ""
            if evidence.get("source_ref") or evidence.get("content_sha256_short") or alias_text:
                evidence_rows.append(
                    {
                        "target": item.get("target"),
                        "source": evidence.get("source_ref") or evidence.get("title") or "N/A",
                        "hash": evidence.get("content_sha256_short") or "N/A",
                        "aliases": alias_text or "N/A",
                    }
                )
        if evidence_rows:
            lines.extend(["## 目标来源证据", "", "| target | source | hash | matched aliases |", "|---|---|---|---|"])
            for row in evidence_rows:
                lines.append(f"| {row['target']} | {row['source']} | {row['hash']} | {row['aliases']} |")
            lines.append("")
    gap_actions = report.get("coverage_gap_actions") if isinstance(report.get("coverage_gap_actions"), list) else []
    if gap_actions:
        lines.extend(
            [
                "## 长期补洞候选",
                "",
                "| rank | target | character | action | reason | stamina | confidence |",
                "|---:|---|---|---|---|---|---|",
            ]
        )
        for item in gap_actions:
            lines.append(
                "| {rank} | {target} | {character} | {action} | {reason} | {stamina} | {confidence} |".format(
                    rank=item.get("rank"),
                    target=item.get("target"),
                    character=item.get("character"),
                    action=item.get("action"),
                    reason=item.get("reason"),
                    stamina="no" if item.get("uses_stamina") is False else "yes",
                    confidence=item.get("confidence"),
                )
            )
        lines.append("")
    lines.extend(["## 优先级", "", "| rank | character | target | action | reason | days | confidence |", "|---|---|---|---|---|---:|---|"])
    for item in report.get("plan_items", []):
        lines.append(
            "| {rank} | {character} | {target} | {action} | {reason} | {days} | {confidence} |".format(
                rank=item["priority_rank"],
                character=item["character"],
                target=item["target"],
                action=item["action"],
                reason=item["reason"],
                days=item["estimated_days"],
                confidence=item["confidence"],
            )
        )
    resource = report.get("resource_plan", {}) if isinstance(report.get("resource_plan"), dict) else {}
    budget = resource.get("budget", {}) if isinstance(resource.get("budget"), dict) else {}
    if resource:
        lines.extend(
            [
                "",
                "## 体力投入计划",
                "",
                f"- daily_stamina: {budget.get('daily_stamina')}",
                f"- horizon_days: {budget.get('horizon_days')}",
                f"- total_stamina: {budget.get('total_stamina')}",
                "",
                "### 今日建议",
                "",
            ]
        )
        today = resource.get("today") if isinstance(resource.get("today"), list) else []
        if today:
            for item in today:
                lines.append(
                    f"- #{item.get('rank')} {item.get('character')}：{item.get('action')}，投入约 {item.get('allocated_stamina')}。"
                )
        else:
            lines.append("- 今日没有需要消耗体力的候选项。")
        no_stamina = resource.get("no_stamina_actions") if isinstance(resource.get("no_stamina_actions"), list) else []
        if no_stamina:
            lines.extend(["", "### 不消耗体力但应先做", ""])
            for item in no_stamina[:5]:
                lines.append(f"- #{item.get('rank')} {item.get('character')}：{item.get('action')}")
    lines.extend(["", "## 角色缺口", ""])
    for character in report.get("characters", []):
        lines.append(f"### {character['character']}")
        targets = "、".join(character.get("matched_targets", [])) or "长期通用练度"
        lines.append(f"- matched_targets: {targets}")
        matches = character.get("target_matches") if isinstance(character.get("target_matches"), list) else []
        if matches:
            lines.append("- target_matches:")
            for match in matches:
                tags = "、".join(match.get("matched_tags", [])) if isinstance(match.get("matched_tags"), list) else ""
                lines.append(
                    "  - {target}: {match_type}, score={score}, tags={tags}, reason={reason}".format(
                        target=match.get("target"),
                        match_type=match.get("match_type"),
                        score=match.get("score"),
                        tags=tags,
                        reason=match.get("reason"),
                    )
                )
        blockers = character.get("quality_blockers", [])
        if blockers:
            lines.append(f"- quality_blockers: {'; '.join(blockers)}")
        history = character.get("history", {}) if isinstance(character.get("history"), dict) else {}
        if history.get("tracked"):
            lines.append(
                "- history: status={status}, recent_change_count={changes}, recent_requires_review_change_count={review}".format(
                    status=history.get("status"),
                    changes=history.get("recent_change_count", 0),
                    review=history.get("recent_requires_review_change_count", 0),
                )
            )
        for gap in character.get("gaps", []):
            lines.append(f"- [{gap['gap_type']}] {gap['action']}：{gap['reason']}")
        lines.append("")
    return "\n".join(lines)


def generate_report(
    snapshot_paths: list[Path],
    targets_path: Path,
    output_dir: Path,
    *,
    history_context: dict[str, Any] | None = None,
    history_index: Path | None = None,
    character_catalog: Path | None = None,
    daily_stamina: float | None = None,
    horizon_days: float | None = None,
) -> dict[str, Any]:
    if not snapshot_paths:
        raise PlannerError("At least one normalized snapshot is required")
    snapshots = [load_json(path) for path in snapshot_paths]
    targets = load_targets(targets_path)
    loaded_history_index = load_history_index(history_index) if history_index else None
    loaded_character_catalog = load_character_catalog(character_catalog)
    characters = [
        character_gaps(
            snapshot,
            targets,
            history_context=history_context,
            history_index=loaded_history_index,
            character_catalog=loaded_character_catalog,
        )
        for snapshot in snapshots
    ]
    source_status = target_source_status(targets)
    target_coverage = target_coverage_summary(targets, characters, loaded_character_catalog)
    coverage_gap_actions = build_coverage_gap_actions(target_coverage)
    items = plan_items(characters, source_status)
    budget = resource_budget(targets, daily_stamina, horizon_days)
    report = {
        "schema_version": "p1.2-planner-draft",
        "created_at": now_iso(),
        "game": targets.get("game") or snapshots[0].get("game"),
        "input": {
            "snapshots": [str(path) for path in snapshot_paths],
            "targets": str(targets_path),
            "history_index": str(history_index) if history_index else None,
            "character_catalog": str(character_catalog) if character_catalog else None,
        },
        "target_source": targets.get("source", {}),
        "target_source_status": source_status,
        "character_catalog": {
            "path": loaded_character_catalog.get("path") if isinstance(loaded_character_catalog, dict) else None,
            "entry_count": len(catalog_entries(loaded_character_catalog)),
        },
        "snapshots": [
            {
                "character": character_name(snapshot),
                "source_image": snapshot.get("source", {}).get("image") if isinstance(snapshot.get("source"), dict) else None,
                "review_status": snapshot.get("source", {}).get("review_status") if isinstance(snapshot.get("source"), dict) else None,
                "coverage_level": snapshot.get("source", {}).get("coverage_level") if isinstance(snapshot.get("source"), dict) else None,
            }
            for snapshot in snapshots
        ],
        "target_coverage": target_coverage,
        "coverage_gap_actions": coverage_gap_actions,
        "characters": characters,
        "plan_items": items,
        "resource_plan": build_resource_plan(items, budget),
        "history_context": {
            "available": bool(history_context or loaded_history_index),
            "character_count": sum(1 for item in characters if item.get("history", {}).get("tracked")),
        },
        "warnings": build_warnings(targets, snapshots, target_coverage),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_priority_report.json"
    md_path = output_dir / "training_priority_report.md"
    write_json(json_path, report)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["output_json"] = str(json_path)
    report["output_md"] = str(md_path)
    write_json(json_path, report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a local training priority report from normalized snapshots.")
    parser.add_argument("--snapshot", action="append", default=[], help="Normalized snapshot JSON. Can be repeated.")
    parser.add_argument("--snapshot-manifest", default=None, help="JSON manifest containing a snapshots list.")
    parser.add_argument("--targets", required=True, help="Local endgame target configuration JSON.")
    parser.add_argument("--history-index", default=None, help="Optional snapshot_history/index.json for long-term continuity context.")
    parser.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for target matching.")
    parser.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget. Default: targets.resource_budget.daily_stamina or 240.")
    parser.add_argument("--horizon-days", type=float, default=None, help="Planning horizon in days. Default: targets.resource_budget.horizon_days or 7.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/planner.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        snapshot_paths = [resolve_path(value) for value in args.snapshot]
        if args.snapshot_manifest:
            snapshot_paths.extend(load_manifest_snapshots(resolve_path(args.snapshot_manifest)))
        report = generate_report(
            snapshot_paths,
            resolve_path(args.targets),
            resolve_path(args.output_dir),
            history_index=resolve_path(args.history_index) if args.history_index else None,
            character_catalog=resolve_path(args.character_catalog) if args.character_catalog else None,
            daily_stamina=args.daily_stamina,
            horizon_days=args.horizon_days,
        )
    except PlannerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    source_status = report.get("target_source_status", {}) if isinstance(report.get("target_source_status"), dict) else {}
    print(f"plan_item_count: {len(report['plan_items'])}")
    print(f"target_source_status: {source_status.get('status')}")
    print(f"planning_confidence: {source_status.get('planning_confidence')}")
    print(f"output_json: {report['output_json']}")
    print(f"output_md: {report['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
