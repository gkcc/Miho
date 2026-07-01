#!/usr/bin/env python
"""Build local endgame plan cards from accepted roster and demo artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.0-lite-endgame-plan"

READY_STATUSES = {"ready_now"}
NEEDS_REVIEW_ACTIONS = {"review_pending_snapshot"}
NEEDS_RECORDING_ACTIONS = {"record_missing_character"}
HIGH_VALUE_OBSERVATIONS = {"owned_high_value", "protect_investment"}
WEAK_TIER_STATUSES = {"stale", "unverified", "invalid_source", "low_trust"}


class EndgamePlanError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise EndgamePlanError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EndgamePlanError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise EndgamePlanError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().casefold()


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short_hash(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    return text[:12] if len(text) > 12 else text


def artifact_evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    digest = sha256_file(path)
    return {
        "path": str(path),
        "sha256_short": short_hash(digest),
    }


def artifact_hashes(**paths: Path | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        evidence = artifact_evidence(path)
        if evidence is not None:
            result[name] = evidence
    return result


def fallback_artifact_status(run_manifest: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(run_manifest, dict) and isinstance(run_manifest.get("artifact_status"), dict):
        status = dict(run_manifest["artifact_status"])
        status.setdefault("consistent", False)
        status.setdefault("missing", [])
        status.setdefault("stale_or_mismatched", [])
        status.setdefault("warnings", [])
        return status
    return {
        "consistent": False,
        "missing": ["run_manifest"],
        "stale_or_mismatched": [],
        "warnings": ["缺少 run_manifest；无法确认 roster、targets、team/action cards 是否为同一批生成。"],
    }


def artifact_trust_warnings(artifact_status: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if artifact_status.get("missing"):
        warnings.append(f"运行产物缺失：{', '.join(str(item) for item in artifact_status.get('missing', []))}。")
    if artifact_status.get("stale_or_mismatched"):
        warnings.append(
            "运行产物可能不是同一批生成："
            + ", ".join(str(item) for item in artifact_status.get("stale_or_mismatched", []))
            + "。"
        )
    for warning in artifact_status.get("warnings", []):
        if warning:
            warnings.append(str(warning))
    if artifact_status.get("consistent") is False and not warnings:
        warnings.append("运行产物一致性未通过。")
    return list(dict.fromkeys(warnings))


def roster_map(roster_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    characters = roster_index.get("characters") if isinstance(roster_index.get("characters"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for item in characters:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        names = [str(item["name"])] + normalize_list(item.get("aliases"))
        for name in names:
            result.setdefault(normalize_name(name), item)
    return result


def tier_signal_map(tier_watchlist: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(tier_watchlist, dict):
        return {}
    entries = tier_watchlist.get("entries") if isinstance(tier_watchlist.get("entries"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("character"):
            continue
        names = [str(entry["character"])] + normalize_list(entry.get("aliases"))
        for name in names:
            result.setdefault(normalize_name(name), entry)
    return result


def delta_change_map(roster_delta: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(roster_delta, dict):
        return {}
    changes = roster_delta.get("character_changes") if isinstance(roster_delta.get("character_changes"), list) else []
    result: dict[str, str] = {}
    for item in changes:
        if isinstance(item, dict) and item.get("character"):
            result[normalize_name(item.get("character"))] = str(item.get("change_type") or "missing")
    return result


def target_name(target: dict[str, Any]) -> str:
    for key in ("target", "name", "title"):
        if target.get(key):
            return str(target[key])
    activity = target.get("activity_name") or target.get("activity")
    tier = target.get("target_tier") or target.get("tier")
    if activity and tier:
        return f"{activity} {tier}"
    if activity:
        return str(activity)
    return str(target.get("goal_id") or "unknown_target")


def target_priority(value: Any) -> str:
    text = str(value or "medium").strip().lower()
    return text if text in {"high", "medium", "low"} else "medium"


def target_evidence(target: dict[str, Any]) -> dict[str, Any]:
    evidence = target.get("evidence") if isinstance(target.get("evidence"), dict) else {}
    source = target.get("source") if isinstance(target.get("source"), dict) else {}
    source_ref = (
        evidence.get("source_ref")
        or source.get("source_ref")
        or source.get("path")
        or source.get("uri")
        or target.get("source_ref")
    )
    digest = (
        evidence.get("content_sha256_short")
        or short_hash(evidence.get("content_sha256"))
        or short_hash(source.get("content_sha256"))
        or short_hash(target.get("content_sha256"))
    )
    return {
        "target_source": source_ref,
        "target_hash": digest,
    }


def target_items(targets: dict[str, Any] | None, team_cards: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    raw_targets = targets.get("targets") if isinstance(targets, dict) and isinstance(targets.get("targets"), list) else []
    for item in raw_targets:
        if isinstance(item, dict):
            result.append(item)
    seen = {target_name(item) for item in result}
    cards = team_cards.get("cards") if isinstance(team_cards.get("cards"), list) else []
    for card in cards:
        if not isinstance(card, dict) or not card.get("target"):
            continue
        name = str(card["target"])
        if name in seen:
            continue
        seen.add(name)
        result.append(
            {
                "target": name,
                "priority": card.get("target_priority") or "medium",
                "evidence": card.get("evidence") if isinstance(card.get("evidence"), dict) else {},
            }
        )
    return result


def group_cards_by_target(report: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(report, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    cards = report.get("cards") if isinstance(report.get("cards"), list) else []
    for card in cards:
        if isinstance(card, dict) and card.get("target"):
            result.setdefault(str(card["target"]), []).append(card)
    return result


def member_tier_observation(character: str, tier_signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    signal = tier_signals.get(normalize_name(character))
    if not signal:
        return {
            "tier": None,
            "retention_score": None,
            "tier_entry_status": "missing",
            "trend": None,
            "observation_status": None,
        }
    return {
        "tier": signal.get("tier"),
        "retention_score": signal.get("retention_score"),
        "tier_entry_status": signal.get("entry_status") or "verified",
        "trend": signal.get("trend"),
        "observation_status": signal.get("observation_status") or signal.get("recommendation"),
    }


def member_plan(
    member: dict[str, Any],
    *,
    roster: dict[str, dict[str, Any]],
    tier_signals: dict[str, dict[str, Any]],
    delta_changes: dict[str, str],
) -> tuple[dict[str, Any], list[str]]:
    character = str(member.get("character") or "unknown_character")
    source_class = str(member.get("source_class") or "unknown")
    normalized = normalize_name(character)
    source_class_effective = source_class
    tier = member_tier_observation(character, tier_signals)
    warnings: list[str] = []
    if source_class == "owned_snapshot" and normalized not in roster:
        source_class_effective = "missing_from_current_roster"
        warnings.append(f"{character} 标记为 owned_snapshot，但当前 roster_index 中未命中；请确认产物是否同批生成。")
    if source_class == "pending_snapshot":
        warnings.append(f"{character} 仍是 pending snapshot，不能当作 ready_now 战力。")
    if source_class == "catalog_owned_missing_snapshot":
        warnings.append(f"{character} 需要补录官方分享图后才能判断练度。")
    if source_class == "catalog_candidate":
        warnings.append(f"{character} 只是 catalog candidate，不能当作已拥有。")
    if tier["tier_entry_status"] in WEAK_TIER_STATUSES:
        warnings.append(f"{character} 的 tier 证据为 {tier['tier_entry_status']}，只展示不提升排序。")
    return (
        {
            "character": character,
            "source_class": source_class,
            "source_class_effective": source_class_effective,
            "tier": tier["tier"],
            "retention_score": tier["retention_score"],
            "tier_entry_status": tier["tier_entry_status"],
            "delta_change_type": delta_changes.get(normalized, "missing"),
        },
        warnings,
    )


def status_from_source_classes(source_classes: set[str], team_status: str) -> str:
    if not source_classes:
        return "blocked"
    if "missing_from_current_roster" in source_classes:
        return "needs_review"
    if "pending_snapshot" in source_classes:
        return "needs_review"
    if "catalog_owned_missing_snapshot" in source_classes:
        return "needs_recording"
    if "catalog_candidate" in source_classes or team_status == "needs_candidate_confirmation":
        return "watch_only"
    if source_classes <= {"owned_snapshot"} and team_status == "playable_now":
        return "ready_now"
    if source_classes <= {"owned_snapshot"}:
        return "needs_review"
    return "blocked"


def high_value_verified_count(members: list[dict[str, Any]], tier_signals: dict[str, dict[str, Any]]) -> int:
    count = 0
    for member in members:
        if member.get("source_class_effective", member.get("source_class")) != "owned_snapshot":
            continue
        signal = tier_signals.get(normalize_name(member.get("character")))
        if not signal or (signal.get("entry_status") or "verified") != "verified":
            continue
        observation = str(signal.get("observation_status") or signal.get("recommendation") or "")
        if observation in HIGH_VALUE_OBSERVATIONS:
            count += 1
    return count


def team_candidate(
    card: dict[str, Any],
    *,
    roster: dict[str, dict[str, Any]],
    tier_signals: dict[str, dict[str, Any]],
    delta_changes: dict[str, str],
) -> dict[str, Any]:
    raw_members = card.get("members") if isinstance(card.get("members"), list) else []
    members: list[dict[str, Any]] = []
    warnings: list[str] = []
    for member in raw_members:
        if not isinstance(member, dict):
            continue
        planned_member, member_warnings = member_plan(
            member,
            roster=roster,
            tier_signals=tier_signals,
            delta_changes=delta_changes,
        )
        members.append(planned_member)
        warnings.extend(member_warnings)
    source_classes = {str(member.get("source_class_effective") or member.get("source_class") or "") for member in members}
    plan_status = status_from_source_classes(source_classes, str(card.get("team_status") or ""))
    verified_high_value = high_value_verified_count(members, tier_signals)
    weak_tier_count = sum(1 for member in members if member.get("tier_entry_status") in WEAK_TIER_STATUSES)
    if plan_status == "ready_now":
        rank_reason = "全员来自 accepted roster，可作为本期高难候选。"
    elif plan_status == "needs_review":
        rank_reason = "包含 pending snapshot，需要先人工复核解析快照。"
    elif plan_status == "needs_recording":
        rank_reason = "包含已拥有但缺练度快照角色，需要先补录官方分享图。"
    elif plan_status == "watch_only":
        rank_reason = "包含 catalog candidate，只能观察或确认拥有状态。"
    else:
        rank_reason = "缺少足够证据形成可执行队伍。"
    if verified_high_value:
        rank_reason = f"{rank_reason} {verified_high_value} 名成员有 verified 高保值本地证据。"
    if weak_tier_count:
        rank_reason = f"{rank_reason} 存在 {weak_tier_count} 条 stale/unverified/low_trust tier 弱证据，不提升排序。"
    card_warnings = card.get("warnings") if isinstance(card.get("warnings"), list) else []
    return {
        "team_title": card.get("team_title") or card.get("target"),
        "team_status": plan_status,
        "rank_reason": rank_reason,
        "members": members,
        "warnings": list(dict.fromkeys([str(item) for item in warnings + card_warnings if item])),
        "source_team_status": card.get("team_status"),
        "verified_high_value_member_count": verified_high_value,
        "weak_tier_count": weak_tier_count,
    }


def team_sort_key(candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    status_weight = {
        "ready_now": 0,
        "needs_review": 1,
        "needs_recording": 2,
        "watch_only": 3,
        "blocked": 4,
    }.get(str(candidate.get("team_status") or ""), 9)
    return (
        status_weight,
        -int(candidate.get("verified_high_value_member_count") or 0),
        int(candidate.get("weak_tier_count") or 0),
        str(candidate.get("team_title") or ""),
    )


def plan_status_from_candidates(candidates: list[dict[str, Any]], actions: list[dict[str, Any]]) -> str:
    if candidates:
        return str(candidates[0].get("team_status") or "blocked")
    action_types = {str(item.get("action_type") or "") for item in actions if isinstance(item, dict)}
    if action_types & NEEDS_REVIEW_ACTIONS:
        return "needs_review"
    if action_types & NEEDS_RECORDING_ACTIONS:
        return "needs_recording"
    return "blocked"


def recommended_line(plan_status: str, candidates: list[dict[str, Any]]) -> str:
    if plan_status == "ready_now":
        title = candidates[0].get("team_title") if candidates else "当前 accepted roster 队伍"
        return f"可先尝试：{title}。"
    if plan_status == "needs_review":
        return "先复核 pending snapshot，确认后再作为可出战练度。"
    if plan_status == "needs_recording":
        return "先补录官方分享图，避免只凭 catalog 拿来排队。"
    if plan_status == "watch_only":
        return "仅观察候选或确认拥有状态；这里不生成抽卡建议。"
    return "当前证据不足，先补齐本地确认数据。"


def trust_level_for_plan(
    *,
    source_plan_status: str,
    trust_warnings: list[str],
    candidates: list[dict[str, Any]],
) -> str:
    has_missing_roster = any(
        member.get("source_class_effective") == "missing_from_current_roster"
        for team in candidates
        if isinstance(team, dict)
        for member in team.get("members", [])
        if isinstance(member, dict)
    )
    if source_plan_status == "blocked" or has_missing_roster:
        return "blocked"
    if source_plan_status == "ready_now" and not trust_warnings:
        return "trusted"
    return "warning"


def apply_trust_gate(source_plan_status: str, plan_trust_level: str) -> str:
    if source_plan_status == "ready_now" and plan_trust_level != "trusted":
        return "needs_review"
    return source_plan_status


def next_actions_for_target(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in actions[:8]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "action_type": item.get("action_type"),
                "priority": item.get("priority"),
                "title": item.get("title"),
                "character": item.get("character"),
                "source_class": item.get("source_class"),
                "status": item.get("status"),
                "reason": item.get("reason"),
            }
        )
    return result


def target_plan(
    target: dict[str, Any],
    *,
    teams: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    roster: dict[str, dict[str, Any]],
    tier_signals: dict[str, dict[str, Any]],
    delta_changes: dict[str, str],
    input_artifact_hashes: dict[str, dict[str, Any]],
    artifact_status: dict[str, Any],
) -> dict[str, Any]:
    candidates = [
        team_candidate(card, roster=roster, tier_signals=tier_signals, delta_changes=delta_changes)
        for card in teams
    ]
    candidates.sort(key=team_sort_key)
    source_plan_status = plan_status_from_candidates(candidates, actions)
    evidence = target_evidence(target)
    if (not evidence.get("target_source") or not evidence.get("target_hash")) and teams:
        team_evidence = teams[0].get("evidence") if isinstance(teams[0].get("evidence"), dict) else {}
        evidence["target_source"] = evidence.get("target_source") or team_evidence.get("target_source")
        evidence["target_hash"] = evidence.get("target_hash") or team_evidence.get("target_hash")
    warnings = []
    if not teams:
        warnings.append("该目标没有 team_cards 候选；只能根据 action_cards 降级展示。")
    for candidate in candidates:
        if isinstance(candidate.get("warnings"), list):
            warnings.extend(str(item) for item in candidate["warnings"] if item)
    if not evidence.get("target_source") or not evidence.get("target_hash"):
        warnings.append("目标缺少 target_source 或 target_hash；不能作为完全可信的本期高难结论。")
    if any(candidate.get("weak_tier_count") for candidate in candidates):
        warnings.append("存在 stale/unverified/low_trust tier 证据，只展示不提升排序。")
    artifact_warnings = artifact_trust_warnings(artifact_status)
    warnings.extend(artifact_warnings)
    plan_trust_level = trust_level_for_plan(
        source_plan_status=source_plan_status,
        trust_warnings=warnings,
        candidates=candidates,
    )
    plan_status = apply_trust_gate(source_plan_status, plan_trust_level)
    if plan_status == "watch_only":
        warnings.append("watch_only 不是抽卡建议；catalog candidate 不能当作已拥有战力。")
    return {
        "target": target_name(target),
        "target_priority": target_priority(target.get("priority") or target.get("target_priority")),
        "plan_status": plan_status,
        "source_plan_status": source_plan_status,
        "plan_trust_level": plan_trust_level,
        "recommended_line": recommended_line(plan_status, candidates),
        "team_candidates": candidates,
        "next_actions": next_actions_for_target(actions),
        "evidence": {
            "target_source": evidence.get("target_source"),
            "target_hash": evidence.get("target_hash"),
            "input_artifact_hashes": input_artifact_hashes,
        },
        "warnings": list(dict.fromkeys(warnings)),
    }


def plan_sort_key(plan: dict[str, Any]) -> tuple[int, int, str]:
    status_weight = {
        "ready_now": 0,
        "needs_review": 1,
        "needs_recording": 2,
        "watch_only": 3,
        "blocked": 4,
    }.get(str(plan.get("plan_status") or ""), 9)
    priority_weight = {"high": 0, "medium": 1, "low": 2}.get(str(plan.get("target_priority") or "medium"), 1)
    return status_weight, priority_weight, str(plan.get("target") or "")


def render_markdown(plan: dict[str, Any]) -> str:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    lines = [
        "# 本期高难方案",
        "",
        "本方案只聚合已确认角色库、本地快照、本地目标配置、本地保值观察和角色库变化；不是抽卡建议，也不保证自动通关。",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Target Plans", ""])
    for item in plan.get("target_plans", []):
        lines.extend(
            [
                f"### {item.get('target')}",
                f"- plan_status: {item.get('plan_status')}",
                f"- source_plan_status: {item.get('source_plan_status')}",
                f"- plan_trust_level: {item.get('plan_trust_level')}",
                f"- target_priority: {item.get('target_priority')}",
                f"- recommended_line: {item.get('recommended_line')}",
            ]
        )
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        lines.append(f"- target_source: {evidence.get('target_source') or 'N/A'}")
        lines.append(f"- target_hash: {evidence.get('target_hash') or 'N/A'}")
        lines.append("- team_candidates:")
        for team in item.get("team_candidates", []):
            if not isinstance(team, dict):
                continue
            lines.append(f"  - {team.get('team_title')} ({team.get('team_status')}): {team.get('rank_reason')}")
            for member in team.get("members", []):
                if isinstance(member, dict):
                    lines.append(
                        "    - "
                        f"{member.get('character')} [{member.get('source_class')}] "
                        f"effective={member.get('source_class_effective') or member.get('source_class')} "
                        f"tier={member.get('tier') or 'N/A'} "
                        f"status={member.get('tier_entry_status')} "
                        f"delta={member.get('delta_change_type')}"
                    )
        actions = item.get("next_actions") if isinstance(item.get("next_actions"), list) else []
        if actions:
            lines.append("- next_actions:")
            for action in actions:
                if isinstance(action, dict):
                    lines.append(f"  - {action.get('action_type')}: {action.get('title')}")
        warnings = item.get("warnings") if isinstance(item.get("warnings"), list) else []
        if warnings:
            lines.append("- warnings:")
            for warning in warnings:
                lines.append(f"  - {warning}")
        lines.append("")
    return "\n".join(lines)


def build_endgame_plan(
    *,
    roster_index: Path,
    team_cards: Path,
    output_dir: Path,
    targets: Path | None = None,
    action_cards: Path | None = None,
    tier_watchlist: Path | None = None,
    roster_delta: Path | None = None,
    run_manifest: Path | None = None,
) -> dict[str, Any]:
    roster_index_data = load_json(roster_index)
    team_cards_data = load_json(team_cards)
    targets_data = load_json(targets) if targets and targets.exists() else None
    action_cards_data = load_json(action_cards) if action_cards and action_cards.exists() else None
    tier_watchlist_data = load_json(tier_watchlist) if tier_watchlist and tier_watchlist.exists() else None
    roster_delta_data = load_json(roster_delta) if roster_delta and roster_delta.exists() else None
    run_manifest_data = load_json(run_manifest) if run_manifest and run_manifest.exists() else None
    artifact_status = fallback_artifact_status(run_manifest_data)
    roster = roster_map(roster_index_data)
    tier_signals = tier_signal_map(tier_watchlist_data)
    delta_changes = delta_change_map(roster_delta_data)
    actions_by_target = group_cards_by_target(action_cards_data)
    teams_by_target = group_cards_by_target(team_cards_data)
    input_hashes = artifact_hashes(
        roster_index=roster_index,
        targets=targets,
        team_cards=team_cards,
        action_cards=action_cards,
        tier_watchlist=tier_watchlist,
        roster_delta=roster_delta,
        run_manifest=run_manifest,
    )

    plans = [
        target_plan(
            target,
            teams=teams_by_target.get(target_name(target), []),
            actions=actions_by_target.get(target_name(target), []),
            roster=roster,
            tier_signals=tier_signals,
            delta_changes=delta_changes,
            input_artifact_hashes=input_hashes,
            artifact_status=artifact_status,
        )
        for target in target_items(targets_data, team_cards_data)
    ]
    plans.sort(key=plan_sort_key)
    stale_or_unverified_count = sum(
        1
        for plan in plans
        if any(
            member.get("tier_entry_status") in WEAK_TIER_STATUSES
            for team in plan.get("team_candidates", [])
            if isinstance(team, dict)
            for member in team.get("members", [])
            if isinstance(member, dict)
        )
    )
    summary = {
        "target_count": len(plans),
        "ready_now_count": sum(1 for item in plans if item.get("plan_status") == "ready_now"),
        "needs_review_count": sum(1 for item in plans if item.get("plan_status") == "needs_review"),
        "needs_recording_count": sum(1 for item in plans if item.get("plan_status") == "needs_recording"),
        "watch_only_count": sum(1 for item in plans if item.get("plan_status") == "watch_only"),
        "blocked_count": sum(1 for item in plans if item.get("plan_status") == "blocked"),
        "trusted_plan_count": sum(1 for item in plans if item.get("plan_trust_level") == "trusted"),
        "warning_plan_count": sum(1 for item in plans if item.get("plan_trust_level") == "warning"),
        "blocked_plan_count": sum(1 for item in plans if item.get("plan_trust_level") == "blocked"),
        "stale_or_unverified_count": stale_or_unverified_count,
        "artifact_consistent": bool(artifact_status.get("consistent")) and not artifact_status.get("missing"),
        "artifact_warning_count": len(artifact_trust_warnings(artifact_status)),
    }
    warnings = [
        "本期高难方案只聚合本地已确认角色库、队伍卡、行动卡、保值观察和角色库变化；不是抽卡建议。",
        "待确认快照、目录候选和已拒绝快照不能生成可直接尝试项。",
    ]
    if targets_data is None:
        warnings.append("缺少 targets JSON；已从 team_cards 的 target 字段降级生成方案。")
    if action_cards_data is None:
        warnings.append("缺少 action_cards；next_actions 可能为空。")
    if tier_watchlist_data is None:
        warnings.append("缺少保值观察快照；保值观察为空。")
    if roster_delta_data is None:
        warnings.append("缺少 roster_delta；delta_change_type 将为 missing。")
    if run_manifest_data is None:
        warnings.append("缺少 run_manifest；高难方案会降级为 warning/needs_review。")
    warnings.extend(artifact_trust_warnings(artifact_status))
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "roster_index": str(roster_index),
            "targets": str(targets) if targets else None,
            "team_cards": str(team_cards),
            "action_cards": str(action_cards) if action_cards else None,
            "tier_watchlist": str(tier_watchlist) if tier_watchlist else None,
            "roster_delta": str(roster_delta) if roster_delta else None,
            "run_manifest": str(run_manifest) if run_manifest else None,
        },
        "artifact_status": artifact_status,
        "plan_trust_level": "blocked"
        if summary["blocked_plan_count"]
        else "warning"
        if summary["warning_plan_count"] or summary["artifact_warning_count"]
        else "trusted",
        "summary": summary,
        "target_plans": plans,
        "warnings": warnings,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "endgame_plan.json"
    md_path = output_dir / "endgame_plan.md"
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build local endgame plan pack from demo artifacts.")
    parser.add_argument("--roster-index", required=True, help="Accepted roster_index.json.")
    parser.add_argument("--targets", default=None, help="Optional endgame_targets.json.")
    parser.add_argument("--team-cards", required=True, help="team_cards.json from build_team_cards.py.")
    parser.add_argument("--action-cards", default=None, help="Optional action_cards.json.")
    parser.add_argument("--tier-watchlist", default=None, help="Optional tier_watchlist.json.")
    parser.add_argument("--roster-delta", default=None, help="Optional roster_delta.json.")
    parser.add_argument("--run-manifest", default=None, help="Optional run_manifest.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for endgame_plan.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_endgame_plan(
            roster_index=resolve_path(args.roster_index),
            targets=resolve_path(args.targets) if args.targets else None,
            team_cards=resolve_path(args.team_cards),
            action_cards=resolve_path(args.action_cards) if args.action_cards else None,
            tier_watchlist=resolve_path(args.tier_watchlist) if args.tier_watchlist else None,
            roster_delta=resolve_path(args.roster_delta) if args.roster_delta else None,
            run_manifest=resolve_path(args.run_manifest) if args.run_manifest else None,
            output_dir=resolve_path(args.output_dir),
        )
    except EndgamePlanError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = result["summary"]
    print(f"target_count: {summary['target_count']}")
    print(f"ready_now_count: {summary['ready_now_count']}")
    print(f"needs_review_count: {summary['needs_review_count']}")
    print(f"needs_recording_count: {summary['needs_recording_count']}")
    print(f"watch_only_count: {summary['watch_only_count']}")
    print(f"trusted_plan_count: {summary['trusted_plan_count']}")
    print(f"warning_plan_count: {summary['warning_plan_count']}")
    print(f"blocked_plan_count: {summary['blocked_plan_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
