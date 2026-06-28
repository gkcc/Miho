#!/usr/bin/env python
"""Build local team candidate cards from planner evidence and action cards."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p1.3-lite-team-cards"


class TeamCardError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TeamCardError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TeamCardError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise TeamCardError(f"Expected JSON object: {path}")
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


def coverage_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    items = report.get("target_coverage")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def snapshot_json_by_character(report: dict[str, Any]) -> dict[str, str]:
    input_info = report.get("input") if isinstance(report.get("input"), dict) else {}
    paths = [str(item) for item in input_info.get("snapshots", []) if item] if isinstance(input_info.get("snapshots"), list) else []
    snapshots = report.get("snapshots") if isinstance(report.get("snapshots"), list) else []
    result: dict[str, str] = {}
    for index, item in enumerate(snapshots):
        if isinstance(item, dict) and item.get("character") and index < len(paths):
            result[str(item["character"])] = paths[index]
    return result


def source_image_by_character(report: dict[str, Any]) -> dict[str, str]:
    snapshots = report.get("snapshots") if isinstance(report.get("snapshots"), list) else []
    result: dict[str, str] = {}
    for item in snapshots:
        if isinstance(item, dict) and item.get("character"):
            result[str(item["character"])] = str(item.get("source_image") or "")
    return result


def accepted_characters(roster_index: dict[str, Any] | None) -> set[str]:
    if not isinstance(roster_index, dict):
        return set()
    characters = roster_index.get("characters") if isinstance(roster_index.get("characters"), list) else []
    return {str(item.get("name")) for item in characters if isinstance(item, dict) and item.get("name")}


def action_reason_map(action_report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    cards = action_report.get("cards") if isinstance(action_report.get("cards"), list) else []
    for item in cards:
        if isinstance(item, dict) and item.get("target") and item.get("character"):
            result[(str(item["target"]), str(item["character"]))] = item
    return result


def evidence_from_coverage(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    return {
        "target_source": evidence.get("source_ref") or evidence.get("title"),
        "target_hash": evidence.get("content_sha256_short") or short_hash(evidence.get("content_sha256")),
        "matched_aliases": evidence.get("matched_aliases", {}) if isinstance(evidence.get("matched_aliases"), dict) else {},
    }


def target_priority(item: dict[str, Any]) -> str:
    text = str(item.get("priority") or item.get("target_priority") or "medium").lower()
    if text in {"high", "medium", "low"}:
        return text
    return "medium"


def slot_for_index(index: int) -> str:
    slots = ["core", "support", "sustain", "flex"]
    return slots[index] if index < len(slots) else "flex"


def owned_member(
    match: dict[str, Any],
    *,
    target: str,
    index: int,
    snapshot_jsons: dict[str, str],
    source_images: dict[str, str],
    accepted: set[str],
    action_reasons: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    character = str(match.get("character") or "unknown_character")
    action = action_reasons.get((target, character), {})
    reason = action.get("reason") or match.get("match_type") or "本地 normalized snapshot 命中该目标。"
    if match.get("score") is not None:
        reason = f"{reason} score={match.get('score')}"
    source_class = "owned_snapshot" if character in accepted else "pending_snapshot"
    return {
        "slot": slot_for_index(index),
        "character": character,
        "source_class": source_class,
        "snapshot_json": snapshot_jsons.get(character),
        "snapshot_source": source_images.get(character),
        "confidence": "high" if source_class == "owned_snapshot" else "medium",
        "reason": reason,
    }


def candidate_source_class(candidate: dict[str, Any]) -> str:
    if candidate.get("owned") is True:
        return "catalog_owned_missing_snapshot"
    if candidate.get("owned") is False:
        return "catalog_candidate"
    return "catalog_candidate"


def candidate_member(
    candidate: dict[str, Any],
    *,
    target: str,
    index: int,
    action_reasons: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    character = str(candidate.get("character") or "unknown_character")
    action = action_reasons.get((target, character), {})
    matched_tags = candidate.get("matched_tags") if isinstance(candidate.get("matched_tags"), list) else []
    reason = action.get("reason") or "catalog 候选命中目标标签，但没有本地练度快照。"
    if matched_tags:
        reason = f"{reason} matched_tags={','.join(str(tag) for tag in matched_tags)}"
    source_class = candidate_source_class(candidate)
    return {
        "slot": slot_for_index(index),
        "character": character,
        "source_class": source_class,
        "snapshot_json": None,
        "snapshot_source": None,
        "confidence": "medium" if source_class == "catalog_owned_missing_snapshot" else "low",
        "reason": reason,
    }


def team_status_for(coverage_status: str, members: list[dict[str, Any]]) -> str:
    if not members:
        return "incomplete"
    source_classes = {str(item.get("source_class") or "") for item in members}
    owned_count = sum(1 for item in members if item.get("source_class") == "owned_snapshot")
    if coverage_status == "covered" and source_classes <= {"owned_snapshot"}:
        return "playable_now" if owned_count >= 2 else "incomplete"
    if "pending_snapshot" in source_classes:
        return "needs_review"
    if "catalog_owned_missing_snapshot" in source_classes:
        return "needs_recording"
    if "catalog_candidate" in source_classes:
        return "needs_candidate_confirmation"
    return "incomplete"


def warnings_for(status: str, members: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if any(item.get("source_class") == "catalog_candidate" for item in members):
        warnings.append("catalog candidate 不代表已拥有；需要人工确认或补录官方分享图。")
    if any(item.get("source_class") == "catalog_owned_missing_snapshot" for item in members):
        warnings.append("catalog 标记已拥有但缺少 normalized snapshot，不能视为可出战练度。")
    if any(item.get("source_class") == "pending_snapshot" for item in members):
        warnings.append("pending snapshot 尚未进入 accepted roster，不能视为可出战练度。")
    if status == "incomplete":
        warnings.append("当前只是队伍雏形，不代表完整可用配队。")
    return warnings


def coverage_reason(status: str, members: list[dict[str, Any]]) -> str:
    names = "、".join(str(item.get("character")) for item in members if item.get("character"))
    if not names:
        return "该目标没有命中本地快照或 catalog 候选。"
    if status == "playable_now":
        return f"本地快照已有 {names}，可作为当前目标的候选队伍基础。"
    if status == "needs_recording":
        return f"{names} 需要补录官方分享图后才能判断练度。"
    if status == "needs_candidate_confirmation":
        return f"{names} 仍是 catalog 候选，先确认拥有状态。"
    if status == "needs_review":
        return f"{names} 已有本地 normalized snapshot，但尚未进入 accepted roster。"
    return f"{names} 只能形成队伍雏形，缺少完整队伍证据。"


def build_card(
    item: dict[str, Any],
    *,
    snapshot_jsons: dict[str, str],
    source_images: dict[str, str],
    accepted: set[str],
    action_reasons: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    target = str(item.get("target") or "unknown_target")
    coverage_status = str(item.get("coverage_status") or "unmatched")
    matched = item.get("matched_characters") if isinstance(item.get("matched_characters"), list) else []
    candidates = item.get("catalog_candidates") if isinstance(item.get("catalog_candidates"), list) else []
    members: list[dict[str, Any]] = []
    if matched:
        for index, match in enumerate(matched[:4]):
            if isinstance(match, dict):
                members.append(
                    owned_member(
                        match,
                        target=target,
                        index=index,
                        snapshot_jsons=snapshot_jsons,
                        source_images=source_images,
                        accepted=accepted,
                        action_reasons=action_reasons,
                    )
                )
    else:
        for index, candidate in enumerate(candidates[:4]):
            if isinstance(candidate, dict):
                members.append(candidate_member(candidate, target=target, index=index, action_reasons=action_reasons))
    status = team_status_for(coverage_status, members)
    title_prefix = {
        "playable_now": "可用队伍候选",
        "needs_review": "待确认快照队伍",
        "needs_recording": "需补录队伍候选",
        "needs_candidate_confirmation": "待确认队伍候选",
        "incomplete": "队伍雏形",
    }.get(status, "队伍候选")
    return {
        "target": target,
        "target_priority": target_priority(item),
        "team_status": status,
        "team_title": f"{title_prefix}: {target}",
        "members": members,
        "coverage_reason": coverage_reason(status, members),
        "evidence": evidence_from_coverage(item),
        "warnings": warnings_for(status, members),
    }


def build_cards(
    planner_report: dict[str, Any],
    action_report: dict[str, Any],
    roster_index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    snapshot_jsons = snapshot_json_by_character(planner_report)
    source_images = source_image_by_character(planner_report)
    accepted = accepted_characters(roster_index)
    action_reasons = action_reason_map(action_report)
    cards = [
        build_card(
            item,
            snapshot_jsons=snapshot_jsons,
            source_images=source_images,
            accepted=accepted,
            action_reasons=action_reasons,
        )
        for item in coverage_items(planner_report)
    ]
    cards = cards[: max(0, len(coverage_items(planner_report)) * 2)]
    for index, card in enumerate(cards, start=1):
        card["rank"] = index
    return cards


def summary_for(cards: list[dict[str, Any]], planner_report: dict[str, Any]) -> dict[str, Any]:
    members = [member for card in cards for member in card.get("members", []) if isinstance(member, dict)]
    return {
        "target_count": len(coverage_items(planner_report)),
        "team_card_count": len(cards),
        "playable_now_count": sum(1 for item in cards if item.get("team_status") == "playable_now"),
        "needs_recording_count": sum(1 for item in cards if item.get("team_status") == "needs_recording"),
        "catalog_candidate_count": sum(1 for item in members if item.get("source_class") == "catalog_candidate"),
        "pending_snapshot_count": sum(1 for item in members if item.get("source_class") == "pending_snapshot"),
    }


def render_markdown(team_report: dict[str, Any]) -> str:
    lines = [
        "# 高难配队候选卡",
        "",
        "队伍候选基于 accepted roster、本地快照和本地 catalog；catalog candidate 不代表已拥有。",
        "",
        "## Summary",
        "",
    ]
    for key, value in team_report.get("summary", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Team Cards", ""])
    for card in team_report.get("cards", []):
        evidence = card.get("evidence") if isinstance(card.get("evidence"), dict) else {}
        lines.extend(
            [
                f"### #{card.get('rank')} {card.get('team_title')}",
                f"- target: {card.get('target')}",
                f"- team_status: {card.get('team_status')}",
                f"- target_priority: {card.get('target_priority')}",
                f"- coverage_reason: {card.get('coverage_reason')}",
                f"- target_source: {evidence.get('target_source') or 'N/A'}",
                f"- target_hash: {evidence.get('target_hash') or 'N/A'}",
                "- members:",
            ]
        )
        for member in card.get("members", []):
            if isinstance(member, dict):
                lines.append(
                    f"  - {member.get('slot')}: {member.get('character')} "
                    f"({member.get('source_class')}, {member.get('confidence')})"
                )
        warnings = card.get("warnings") if isinstance(card.get("warnings"), list) else []
        if warnings:
            lines.append("- warnings:")
            for warning in warnings:
                lines.append(f"  - {warning}")
        lines.append("")
    return "\n".join(lines)


def build_team_cards(
    *,
    action_cards: Path,
    planner_report: Path,
    output_dir: Path,
    character_catalog: Path | None = None,
    snapshots_dir: Path | None = None,
    roster_index: Path | None = None,
) -> dict[str, Any]:
    action_report = load_json(action_cards)
    planner = load_json(planner_report)
    if character_catalog is not None and not character_catalog.exists():
        raise TeamCardError(f"Character catalog JSON does not exist: {character_catalog}")
    loaded_roster_index = load_json(roster_index) if roster_index else None
    cards = build_cards(planner, action_report, loaded_roster_index)
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "action_cards": str(action_cards),
            "planner_report": str(planner_report),
            "character_catalog": str(character_catalog) if character_catalog else None,
            "snapshots_dir": str(snapshots_dir) if snapshots_dir else None,
            "roster_index": str(roster_index) if roster_index else None,
        },
        "summary": summary_for(cards, planner),
        "cards": cards,
        "warnings": [
            "队伍候选基于 accepted roster、本地快照和本地 catalog；catalog candidate 不代表已拥有。"
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "team_cards.json"
    md_path = output_dir / "team_cards.md"
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build local team candidate cards from planner evidence.")
    parser.add_argument("--action-cards", required=True, help="action_cards.json from build_action_cards.py.")
    parser.add_argument("--planner-report", required=True, help="training_priority_report.json from plan_training_priorities.py.")
    parser.add_argument("--character-catalog", default=None, help="Optional local character catalog JSON.")
    parser.add_argument("--snapshots-dir", default=None, help="Optional normalized snapshot directory for input metadata.")
    parser.add_argument("--roster-index", default=None, help="Optional accepted roster_index.json. Only these characters count as owned_snapshot.")
    parser.add_argument("--output-dir", required=True, help="Output directory for team_cards.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_team_cards(
            action_cards=resolve_path(args.action_cards),
            planner_report=resolve_path(args.planner_report),
            character_catalog=resolve_path(args.character_catalog) if args.character_catalog else None,
            snapshots_dir=resolve_path(args.snapshots_dir) if args.snapshots_dir else None,
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            output_dir=resolve_path(args.output_dir),
        )
    except TeamCardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"team_card_count: {result['summary']['team_card_count']}")
    print(f"playable_now_count: {result['summary']['playable_now_count']}")
    print(f"needs_recording_count: {result['summary']['needs_recording_count']}")
    print(f"catalog_candidate_count: {result['summary']['catalog_candidate_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
