#!/usr/bin/env python
"""Build an accepted roster delta report from two roster indexes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p1.8-lite-roster-delta"


class RosterDeltaError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RosterDeltaError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RosterDeltaError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise RosterDeltaError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def character_key(name: Any) -> str:
    return "".join(str(name or "").split()).casefold()


def roster_map(roster_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    characters = roster_index.get("characters") if isinstance(roster_index.get("characters"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for item in characters:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        result[character_key(item.get("name"))] = item
    return result


def value_at(item: dict[str, Any] | None, field: str) -> Any:
    if not isinstance(item, dict):
        return None
    if field == "quality.trusted_field_count":
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        return quality.get("trusted_field_count")
    if field == "quality.field_count":
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        return quality.get("field_count")
    if field == "quality.blocker_count":
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        blockers = quality.get("blockers") if isinstance(quality.get("blockers"), list) else []
        return len(blockers)
    return item.get(field)


COMPARE_FIELDS = [
    "level",
    "rank",
    "equipment",
    "snapshot_json",
    "source_image",
    "source_normalized_json",
    "quality.trusted_field_count",
    "quality.field_count",
    "quality.blocker_count",
]


def field_changes(old_item: dict[str, Any] | None, new_item: dict[str, Any] | None) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for field in COMPARE_FIELDS:
        old_value = value_at(old_item, field)
        new_value = value_at(new_item, field)
        if old_value != new_value:
            changes.append({"field": field, "old": old_value, "new": new_value})
    return changes


def team_impacts(team_cards: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(team_cards, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    cards = team_cards.get("cards") if isinstance(team_cards.get("cards"), list) else []
    for card in cards:
        if not isinstance(card, dict):
            continue
        members = card.get("members") if isinstance(card.get("members"), list) else []
        for member in members:
            if not isinstance(member, dict) or not member.get("character"):
                continue
            key = character_key(member.get("character"))
            result.setdefault(key, []).append(
                {
                    "target": card.get("target"),
                    "team_title": card.get("team_title"),
                    "team_status": card.get("team_status"),
                    "source_class": member.get("source_class"),
                }
            )
    return result


def action_impacts(action_cards: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(action_cards, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    cards = action_cards.get("cards") if isinstance(action_cards.get("cards"), list) else []
    for card in cards:
        if not isinstance(card, dict) or not card.get("character"):
            continue
        result.setdefault(character_key(card.get("character")), []).append(
            {
                "target": card.get("target"),
                "action_type": card.get("action_type"),
                "status": card.get("status"),
                "priority": card.get("priority"),
            }
        )
    return result


def tier_map(tier_watchlist: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(tier_watchlist, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    entries = tier_watchlist.get("entries") if isinstance(tier_watchlist.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("character"):
            continue
        if entry.get("owned_status") != "accepted_roster":
            continue
        result[character_key(entry.get("character"))] = entry
    return result


def tier_observation(key: str, tiers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = tiers.get(key)
    if not entry:
        return {"status": "missing", "tier": None, "retention_score": None, "trend": None}
    return {
        "status": entry.get("entry_status") or "verified",
        "observation_status": entry.get("observation_status") or entry.get("recommendation"),
        "tier": entry.get("tier"),
        "retention_score": entry.get("retention_score"),
        "usage_rate": entry.get("usage_rate"),
        "trend": entry.get("trend"),
        "source": entry.get("evidence") if isinstance(entry.get("evidence"), dict) else entry.get("source"),
    }


def unique_targets(items: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        target = item.get("target")
        if not target:
            continue
        text = str(target)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def build_change(
    *,
    key: str,
    old_item: dict[str, Any] | None,
    new_item: dict[str, Any] | None,
    action_by_character: dict[str, list[dict[str, Any]]],
    team_by_character: dict[str, list[dict[str, Any]]],
    tiers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    name = (new_item or old_item or {}).get("name")
    changes = field_changes(old_item, new_item)
    if old_item is None:
        change_type = "new"
    elif new_item is None:
        change_type = "removed"
    elif changes:
        change_type = "updated"
    else:
        change_type = "unchanged"
    team_hits = team_by_character.get(key, [])
    action_hits = action_by_character.get(key, [])
    warnings = []
    if change_type == "removed":
        warnings.append("该角色不在新的 roster_index 当前版本中；不会自动删除 accepted 目录里的历史文件。")
    if new_item and int(new_item.get("superseded_snapshot_count") or 0) > 0:
        warnings.append("该角色有 superseded accepted snapshot；delta 只比较 roster_index 当前保留版本。")
    return {
        "character": name,
        "change_type": change_type,
        "old_snapshot_json": old_item.get("snapshot_json") if isinstance(old_item, dict) else None,
        "new_snapshot_json": new_item.get("snapshot_json") if isinstance(new_item, dict) else None,
        "field_changes": changes,
        "impacted_targets": unique_targets(team_hits + action_hits),
        "impacted_teams": team_hits,
        "action_impacts": action_hits,
        "tier_observation": tier_observation(key, tiers),
        "warnings": warnings,
    }


def render_markdown(delta: dict[str, Any]) -> str:
    summary = delta.get("summary") if isinstance(delta.get("summary"), dict) else {}
    lines = [
        "# 本次练度更新影响",
        "",
        "delta 只基于 accepted roster 的 roster_index，不包含 pending snapshot / rejected snapshot / catalog candidate。",
        "",
        f"- new_character_count: {summary.get('new_character_count', 0)}",
        f"- updated_character_count: {summary.get('updated_character_count', 0)}",
        f"- removed_character_count: {summary.get('removed_character_count', 0)}",
        f"- unchanged_character_count: {summary.get('unchanged_character_count', 0)}",
        f"- team_impact_count: {summary.get('team_impact_count', 0)}",
        f"- tier_impact_count: {summary.get('tier_impact_count', 0)}",
        "",
        "## Character Changes",
        "",
    ]
    for change in delta.get("character_changes", []):
        lines.extend(
            [
                f"### {change.get('character')}",
                f"- change_type: {change.get('change_type')}",
                f"- old_snapshot_json: {change.get('old_snapshot_json') or 'N/A'}",
                f"- new_snapshot_json: {change.get('new_snapshot_json') or 'N/A'}",
                f"- impacted_targets: {'、'.join(change.get('impacted_targets', [])) or 'none'}",
                f"- tier_status: {(change.get('tier_observation') or {}).get('status')}",
                "",
            ]
        )
        for item in change.get("field_changes", []):
            if not isinstance(item, dict):
                continue
            lines.append(f"  - {item.get('field')}: {item.get('old')} -> {item.get('new')}")
        if change.get("field_changes"):
            lines.append("")
    return "\n".join(lines)


def build_roster_delta(
    *,
    old_roster_index: Path,
    new_roster_index: Path,
    output_dir: Path,
    action_cards: Path | None = None,
    team_cards: Path | None = None,
    tier_watchlist: Path | None = None,
) -> dict[str, Any]:
    old_index = load_json(old_roster_index)
    new_index = load_json(new_roster_index)
    old_map = roster_map(old_index)
    new_map = roster_map(new_index)
    actions = load_json(action_cards) if action_cards and action_cards.exists() else None
    teams = load_json(team_cards) if team_cards and team_cards.exists() else None
    tiers = tier_map(load_json(tier_watchlist) if tier_watchlist and tier_watchlist.exists() else None)
    action_by_character = action_impacts(actions)
    team_by_character = team_impacts(teams)

    keys = sorted(set(old_map) | set(new_map), key=lambda item: str((new_map.get(item) or old_map.get(item) or {}).get("name") or item))
    changes = [
        build_change(
            key=key,
            old_item=old_map.get(key),
            new_item=new_map.get(key),
            action_by_character=action_by_character,
            team_by_character=team_by_character,
            tiers=tiers,
        )
        for key in keys
    ]
    summary = {
        "new_character_count": sum(1 for item in changes if item.get("change_type") == "new"),
        "updated_character_count": sum(1 for item in changes if item.get("change_type") == "updated"),
        "removed_character_count": sum(1 for item in changes if item.get("change_type") == "removed"),
        "unchanged_character_count": sum(1 for item in changes if item.get("change_type") == "unchanged"),
        "team_impact_count": sum(1 for item in changes if item.get("impacted_teams")),
        "tier_impact_count": sum(1 for item in changes if (item.get("tier_observation") or {}).get("status") != "missing"),
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "old_roster_index": str(old_roster_index),
            "new_roster_index": str(new_roster_index),
            "action_cards": str(action_cards) if action_cards else None,
            "team_cards": str(team_cards) if team_cards else None,
            "tier_watchlist": str(tier_watchlist) if tier_watchlist else None,
        },
        "summary": summary,
        "character_changes": changes,
        "warnings": [
            "roster_delta 只基于 accepted roster 的当前 roster_index；pending snapshot、rejected snapshot 和 catalog candidate 不参与已拥有 box 变化。"
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "roster_delta.json"
    md_path = output_dir / "roster_delta.md"
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build accepted roster delta report.")
    parser.add_argument("--old-roster-index", required=True, help="Previous roster_index.json.")
    parser.add_argument("--new-roster-index", required=True, help="Current roster_index.json.")
    parser.add_argument("--action-cards", default=None, help="Optional action_cards.json.")
    parser.add_argument("--team-cards", default=None, help="Optional team_cards.json.")
    parser.add_argument("--tier-watchlist", default=None, help="Optional tier_watchlist.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for roster_delta.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_roster_delta(
            old_roster_index=resolve_path(args.old_roster_index),
            new_roster_index=resolve_path(args.new_roster_index),
            action_cards=resolve_path(args.action_cards) if args.action_cards else None,
            team_cards=resolve_path(args.team_cards) if args.team_cards else None,
            tier_watchlist=resolve_path(args.tier_watchlist) if args.tier_watchlist else None,
            output_dir=resolve_path(args.output_dir),
        )
    except RosterDeltaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = result["summary"]
    print(f"new_character_count: {summary['new_character_count']}")
    print(f"updated_character_count: {summary['updated_character_count']}")
    print(f"removed_character_count: {summary['removed_character_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
