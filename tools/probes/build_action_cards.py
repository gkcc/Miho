#!/usr/bin/env python
"""Build user-facing next-action cards from a local planner report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p1.2-lite-action-cards"


class ActionCardError(RuntimeError):
    pass


HIGH_VALUE_TIER_RECOMMENDATIONS = {"protect_investment"}
LOW_VALUE_TIER_RECOMMENDATIONS = {"avoid_overinvestment", "low_priority_candidate"}


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ActionCardError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionCardError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise ActionCardError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def short_hash(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    return text[:12] if len(text) > 12 else text


def normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


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


def priority_from_rank(rank: Any) -> str:
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return "medium"
    if value <= 3:
        return "high"
    if value <= 8:
        return "medium"
    return "low"


def priority_from_target(value: Any) -> str:
    text = str(value or "medium").lower()
    if text in {"high", "medium", "low"}:
        return text
    return "medium"


def target_evidence_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report.get("target_coverage", []) if isinstance(report.get("target_coverage"), list) else []:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "")
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        result[target] = evidence
    return result


def coverage_by_target(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report.get("target_coverage", []) if isinstance(report.get("target_coverage"), list) else []:
        if isinstance(item, dict) and item.get("target"):
            result[str(item["target"])] = item
    return result


def snapshot_sources(report: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in report.get("snapshots", []) if isinstance(report.get("snapshots"), list) else []:
        if not isinstance(item, dict):
            continue
        character = item.get("character")
        if character:
            result[str(character)] = str(item.get("source_image") or "")
    return result


def snapshot_json_sources(report: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    snapshot_paths = []
    input_info = report.get("input") if isinstance(report.get("input"), dict) else {}
    if isinstance(input_info.get("snapshots"), list):
        snapshot_paths = [str(item) for item in input_info["snapshots"] if item]
    snapshots = report.get("snapshots") if isinstance(report.get("snapshots"), list) else []
    for index, item in enumerate(snapshots):
        if not isinstance(item, dict) or not item.get("character"):
            continue
        if index < len(snapshot_paths):
            result[str(item["character"])] = snapshot_paths[index]
    return result


def accepted_characters(roster_index: dict[str, Any] | None) -> set[str]:
    if not isinstance(roster_index, dict):
        return set()
    characters = roster_index.get("characters") if isinstance(roster_index.get("characters"), list) else []
    return {str(item.get("name")) for item in characters if isinstance(item, dict) and item.get("name")}


def tier_signal_map(tier_watchlist: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(tier_watchlist, dict):
        return {}
    entries = tier_watchlist.get("entries") if isinstance(tier_watchlist.get("entries"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("character"):
            continue
        names = [str(entry["character"])] + normalize_list(entry.get("aliases"))
        signal = {
            "character": entry.get("character"),
            "owned_status": entry.get("owned_status"),
            "tier": entry.get("tier"),
            "tier_score": entry.get("tier_score"),
            "retention_score": entry.get("retention_score"),
            "usage_rate": entry.get("usage_rate"),
            "trend": entry.get("trend"),
            "recommendation": entry.get("recommendation"),
            "reason": entry.get("reason"),
            "source": entry.get("source") if isinstance(entry.get("source"), dict) else None,
        }
        for name in names:
            result.setdefault(normalize_name(name), signal)
    return result


def tier_signal_for(character: str, signals: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return signals.get(normalize_name(character))


def append_reason(reason: Any, extra: str) -> str:
    base = str(reason or "").strip()
    if not base:
        return extra
    if extra in base:
        return base
    return f"{base} {extra}"


def tier_signal_evidence(signal: dict[str, Any]) -> dict[str, Any]:
    source = signal.get("source") if isinstance(signal.get("source"), dict) else {}
    return {
        "recommendation": signal.get("recommendation"),
        "tier": signal.get("tier"),
        "tier_score": signal.get("tier_score"),
        "retention_score": signal.get("retention_score"),
        "trend": signal.get("trend"),
        "source_name": source.get("name"),
        "source_ref": source.get("source_ref"),
    }


def apply_tier_signal(card: dict[str, Any], signal: dict[str, Any] | None) -> dict[str, Any]:
    if not signal:
        return card
    recommendation = str(signal.get("recommendation") or "")
    card["tier_signal"] = tier_signal_evidence(signal)
    evidence = card.get("evidence") if isinstance(card.get("evidence"), dict) else {}
    evidence["tier_signal"] = card["tier_signal"]
    card["evidence"] = evidence

    if card.get("action_type") == "train_owned_character":
        if recommendation in HIGH_VALUE_TIER_RECOMMENDATIONS:
            card["reason"] = append_reason(
                card.get("reason"),
                "tier/保值信号较强，本地行动卡允许优先保护这类已确认投入。",
            )
        elif recommendation in LOW_VALUE_TIER_RECOMMENDATIONS:
            original_title = card.get("title")
            original_reason = card.get("reason")
            card["action_type"] = "review_low_value_investment"
            card["status"] = "needs_review"
            card["priority"] = "low"
            card["title"] = f"复核 {card.get('character')} 的低保值投入"
            card["reason"] = (
                "tier/保值信号偏弱，不建议为了拿奖励继续加码；"
                f"原行动为「{original_title}」，原因为：{original_reason or 'N/A'}"
            )
    elif recommendation == "watch_candidate":
        card["reason"] = append_reason(
            card.get("reason"),
            "tier/保值信号较强，但这仍只是观察候选；未进入 accepted roster 前不能当作已拥有练度或抽取建议。",
        )
    elif recommendation in LOW_VALUE_TIER_RECOMMENDATIONS:
        card["priority"] = "low"
        card["reason"] = append_reason(
            card.get("reason"),
            "tier/保值信号偏弱；补录或确认前先复核是否真的服务当前终局目标。",
        )
    return card


def first_target_label(value: Any) -> str:
    text = str(value or "")
    if "、" in text:
        return text.split("、", 1)[0]
    return text


def evidence_for(target: str, character: str, report: dict[str, Any]) -> dict[str, Any]:
    evidence = target_evidence_map(report).get(first_target_label(target), {})
    return {
        "target_source": evidence.get("source_ref") or evidence.get("title"),
        "target_hash": evidence.get("content_sha256_short") or short_hash(evidence.get("content_sha256")),
        "matched_aliases": evidence.get("matched_aliases", {}) if isinstance(evidence.get("matched_aliases"), dict) else {},
        "snapshot_source": snapshot_sources(report).get(character),
        "snapshot_json": snapshot_json_sources(report).get(character),
    }


def card_links(
    planner_report: Path,
    target_source: Any | None = None,
    snapshot_json: Any | None = None,
    snapshot_source: Any | None = None,
) -> dict[str, Any]:
    return {
        "planner_report": str(planner_report),
        "target_source": target_source,
        "normalized_json": snapshot_json,
        "snapshot_source": snapshot_source,
    }


def plan_item_card(
    item: dict[str, Any],
    report: dict[str, Any],
    planner_report: Path,
    accepted: set[str],
) -> dict[str, Any]:
    character = str(item.get("character") or "unknown_character")
    target = str(item.get("target") or "长期通用练度")
    action = str(item.get("action") or "补练度")
    gap_type = str(item.get("gap_type") or "")
    is_accepted = character in accepted
    if not is_accepted:
        action_type = "review_pending_snapshot"
        status = "needs_review"
        source_class = "pending_snapshot"
        title = f"复核 {character} 的解析快照"
        reason = f"该角色只有 demo normalized snapshot，尚未进入 accepted roster。原动作：{action}。"
    else:
        action_type = "review_candidate" if gap_type == "data_review" else "train_owned_character"
        status = "needs_review" if gap_type == "data_review" else "actionable"
        source_class = "owned_snapshot"
        title = f"{character}: {action}"
        reason = item.get("reason")
    evidence = evidence_for(target, character, report)
    return {
        "action_type": action_type,
        "priority": priority_from_rank(item.get("priority_rank")),
        "title": title,
        "character": character,
        "target": target,
        "reason": reason,
        "evidence": {
            **evidence,
            "target_match_reasons": item.get("target_match_reasons", []) if isinstance(item.get("target_match_reasons"), list) else [],
        },
        "source_class": source_class,
        "status": status,
        "links": card_links(
            planner_report,
            evidence.get("target_source"),
            evidence.get("snapshot_json"),
            evidence.get("snapshot_source"),
        ),
    }


def gap_action_card(item: dict[str, Any], report: dict[str, Any], planner_report: Path) -> dict[str, Any]:
    character = str(item.get("character") or "unknown_character")
    target = str(item.get("target") or "unknown_target")
    action_type = str(item.get("action_type") or "confirm_ownership")
    if action_type == "record_owned_snapshot":
        card_type = "record_missing_character"
        title = f"补录 {character} 的官方分享图"
        source_class = "catalog_owned_missing_snapshot"
        status = "needs_review"
    elif action_type == "long_term_candidate":
        card_type = "target_gap"
        title = f"长期观察 {character}"
        source_class = "catalog_candidate"
        status = "blocked"
    else:
        card_type = "review_candidate"
        title = f"确认是否拥有 {character}"
        source_class = "catalog_candidate"
        status = "needs_review"
    evidence = evidence_for(target, character, report)
    evidence["matched_aliases"] = evidence.get("matched_aliases") or {}
    evidence["matched_tags"] = item.get("matched_tags", []) if isinstance(item.get("matched_tags"), list) else []
    evidence["match_types"] = item.get("match_types", []) if isinstance(item.get("match_types"), list) else []
    return {
        "action_type": card_type,
        "priority": priority_from_target(item.get("target_priority")),
        "title": title,
        "character": character,
        "target": target,
        "reason": item.get("reason"),
        "evidence": evidence,
        "source_class": source_class,
        "candidate_owned": item.get("owned"),
        "status": status,
        "links": card_links(planner_report, evidence.get("target_source"), None, evidence.get("snapshot_source")),
    }


def card_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    priority_weight = {"high": 0, "medium": 1, "low": 2}
    type_weight = {
        "train_owned_character": 0,
        "review_pending_snapshot": 1,
        "record_missing_character": 2,
        "review_candidate": 3,
        "review_low_value_investment": 4,
        "target_gap": 5,
    }
    return (
        priority_weight.get(str(item.get("priority") or "medium"), 1),
        type_weight.get(str(item.get("action_type") or ""), 9),
        str(item.get("target") or ""),
        str(item.get("character") or ""),
    )


def build_cards(
    report: dict[str, Any],
    planner_report: Path,
    roster_index: dict[str, Any] | None = None,
    tier_watchlist: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cards = []
    accepted = accepted_characters(roster_index)
    tier_signals = tier_signal_map(tier_watchlist)
    for item in report.get("plan_items", []) if isinstance(report.get("plan_items"), list) else []:
        if isinstance(item, dict):
            card = plan_item_card(item, report, planner_report, accepted)
            cards.append(apply_tier_signal(card, tier_signal_for(str(card.get("character") or ""), tier_signals)))
    for item in report.get("coverage_gap_actions", []) if isinstance(report.get("coverage_gap_actions"), list) else []:
        if isinstance(item, dict):
            card = gap_action_card(item, report, planner_report)
            cards.append(apply_tier_signal(card, tier_signal_for(str(card.get("character") or ""), tier_signals)))
    cards.sort(key=card_sort_key)
    for index, item in enumerate(cards, start=1):
        item["rank"] = index
    return cards


def snapshot_count_from_dir(path: Path | None) -> int:
    if path is None or not path.exists() or not path.is_dir():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def summary_for(
    report: dict[str, Any],
    cards: list[dict[str, Any]],
    snapshots_dir: Path | None,
    roster_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coverage = report.get("target_coverage") if isinstance(report.get("target_coverage"), list) else []
    owned = accepted_characters(roster_index)
    return {
        "owned_character_count": len(owned),
        "pending_snapshot_count": sum(1 for item in cards if item.get("source_class") == "pending_snapshot"),
        "snapshot_file_count": snapshot_count_from_dir(snapshots_dir),
        "target_count": len(coverage),
        "covered_target_count": sum(1 for item in coverage if isinstance(item, dict) and item.get("coverage_status") == "covered"),
        "uncovered_target_count": sum(1 for item in coverage if isinstance(item, dict) and item.get("coverage_status") == "unmatched"),
        "needs_recording_count": sum(1 for item in cards if item.get("action_type") in {"record_missing_character", "review_candidate", "review_pending_snapshot"}),
        "high_priority_action_count": sum(1 for item in cards if item.get("priority") == "high"),
        "tier_signal_count": sum(1 for item in cards if isinstance(item.get("tier_signal"), dict)),
        "high_value_owned_action_count": sum(
            1
            for item in cards
            if item.get("action_type") == "train_owned_character"
            and isinstance(item.get("tier_signal"), dict)
            and item["tier_signal"].get("recommendation") == "protect_investment"
        ),
        "low_value_action_count": sum(
            1
            for item in cards
            if isinstance(item.get("tier_signal"), dict)
            and item["tier_signal"].get("recommendation") in LOW_VALUE_TIER_RECOMMENDATIONS
        ),
        "low_value_review_count": sum(1 for item in cards if item.get("action_type") == "review_low_value_investment"),
    }


def render_markdown(action_report: dict[str, Any]) -> str:
    lines = [
        "# 下一步行动卡",
        "",
        "pending snapshot 和 catalog candidate 都不代表可用练度；只有 accepted roster 才算已确认拥有练度。",
        "",
        "## Summary",
        "",
    ]
    for key, value in action_report.get("summary", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Cards", ""])
    for item in action_report.get("cards", []):
        evidence = item.get("evidence", {}) if isinstance(item.get("evidence"), dict) else {}
        tier_signal = item.get("tier_signal", {}) if isinstance(item.get("tier_signal"), dict) else {}
        lines.extend(
            [
                f"### #{item.get('rank')} {item.get('title')}",
                f"- action_type: {item.get('action_type')}",
                f"- priority: {item.get('priority')}",
                f"- status: {item.get('status')}",
                f"- source_class: {item.get('source_class')}",
                f"- target: {item.get('target')}",
                f"- reason: {item.get('reason')}",
                f"- target_source: {evidence.get('target_source') or 'N/A'}",
                f"- target_hash: {evidence.get('target_hash') or 'N/A'}",
                f"- tier_signal: {tier_signal.get('recommendation') or 'N/A'} / {tier_signal.get('tier') or 'N/A'}",
                "",
            ]
        )
    return "\n".join(lines)


def build_action_cards(
    *,
    planner_report: Path,
    output_dir: Path,
    targets: Path | None = None,
    snapshots_dir: Path | None = None,
    roster_index: Path | None = None,
    tier_watchlist: Path | None = None,
) -> dict[str, Any]:
    report = load_json(planner_report)
    if targets is not None and not targets.exists():
        raise ActionCardError(f"Targets JSON does not exist: {targets}")
    loaded_roster_index = load_json(roster_index) if roster_index else None
    loaded_tier_watchlist = load_json(tier_watchlist) if tier_watchlist else None
    cards = build_cards(report, planner_report, loaded_roster_index, loaded_tier_watchlist)
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "planner_report": str(planner_report),
            "targets": str(targets) if targets else report.get("input", {}).get("targets") if isinstance(report.get("input"), dict) else None,
            "snapshots_dir": str(snapshots_dir) if snapshots_dir else None,
            "roster_index": str(roster_index) if roster_index else None,
            "tier_watchlist": str(tier_watchlist) if tier_watchlist else None,
        },
        "summary": summary_for(report, cards, snapshots_dir, loaded_roster_index),
        "cards": cards,
        "warnings": [
            "pending snapshot 和 catalog candidate 都不代表可用练度；只有 accepted roster 才算已确认拥有练度。",
            "tier_signal 只调整本地行动优先级，不是最终抽取建议。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "action_cards.json"
    md_path = output_dir / "action_cards.md"
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build next-action cards from a local planner report.")
    parser.add_argument("--planner-report", required=True, help="training_priority_report.json from plan_training_priorities.py.")
    parser.add_argument("--targets", default=None, help="Optional endgame targets JSON used by the planner.")
    parser.add_argument("--snapshots-dir", default=None, help="Optional normalized snapshot directory for summary counts.")
    parser.add_argument("--roster-index", default=None, help="Optional accepted roster_index.json. Only these characters count as owned_snapshot.")
    parser.add_argument("--tier-watchlist", default=None, help="Optional tier_watchlist.json from build_tier_watchlist.py.")
    parser.add_argument("--output-dir", required=True, help="Output directory for action_cards.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_action_cards(
            planner_report=resolve_path(args.planner_report),
            targets=resolve_path(args.targets) if args.targets else None,
            snapshots_dir=resolve_path(args.snapshots_dir) if args.snapshots_dir else None,
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            tier_watchlist=resolve_path(args.tier_watchlist) if args.tier_watchlist else None,
            output_dir=resolve_path(args.output_dir),
        )
    except ActionCardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"card_count: {len(result['cards'])}")
    print(f"high_priority_action_count: {result['summary']['high_priority_action_count']}")
    print(f"needs_recording_count: {result['summary']['needs_recording_count']}")
    print(f"tier_signal_count: {result['summary']['tier_signal_count']}")
    print(f"low_value_review_count: {result['summary']['low_value_review_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
