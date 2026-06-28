#!/usr/bin/env python
"""Build a local tier/value watchlist against the accepted roster."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p1.5-lite-tier-watchlist"

HIGH_VALUE_TAGS = {"high_retention", "current_meta", "core", "top_tier", "long_term_value"}
LOW_VALUE_TAGS = {"low_retention", "niche", "replaceable", "declining"}
TIER_SCORES = {
    "T0": 100,
    "SSS": 100,
    "SS+": 97,
    "SS": 95,
    "S+": 92,
    "S": 90,
    "A+": 82,
    "A": 78,
    "B": 65,
    "C": 50,
}


class TierWatchlistError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TierWatchlistError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TierWatchlistError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise TierWatchlistError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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


def percentage_or_number(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        text = str(value).strip().replace(",", "")
        multiplier = 0.01 if text.endswith("%") else 1.0
        text = text.rstrip("%")
        try:
            parsed = float(text) * multiplier
        except ValueError:
            return None
    if parsed > 1.0 and parsed <= 100.0:
        return parsed / 100.0
    return parsed


def tier_score(value: Any) -> int:
    text = str(value or "").strip().upper().replace(" ", "")
    return TIER_SCORES.get(text, 0)


def snapshot_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("entries", "characters", "items"):
        value = snapshot.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise TierWatchlistError("Tier snapshot must contain an entries, characters, or items list")


def source_info(snapshot: dict[str, Any], tier_snapshot_path: Path) -> dict[str, Any]:
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    return {
        "name": source.get("name") or snapshot.get("source_name") or tier_snapshot_path.name,
        "source_type": source.get("source_type") or snapshot.get("source_type") or "local_snapshot",
        "source_ref": source.get("source_ref") or source.get("url") or str(tier_snapshot_path),
        "captured_at": source.get("captured_at") or snapshot.get("captured_at"),
    }


def roster_character_map(roster_index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(roster_index, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    characters = roster_index.get("characters") if isinstance(roster_index.get("characters"), list) else []
    for item in characters:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        names = [str(item["name"])] + normalize_list(item.get("aliases"))
        for name in names:
            result[normalize_name(name)] = item
    return result


def entry_names(entry: dict[str, Any]) -> list[str]:
    names = normalize_list(entry.get("character") or entry.get("name"))
    names.extend(normalize_list(entry.get("aliases")))
    return names or ["unknown_character"]


def entry_character(entry: dict[str, Any]) -> str:
    return entry_names(entry)[0]


def entry_tags(entry: dict[str, Any]) -> set[str]:
    tags = set()
    for key in ("value_tags", "tags", "meta_tags"):
        tags.update(tag.lower() for tag in normalize_list(entry.get(key)))
    return tags


def entry_retention(entry: dict[str, Any]) -> float | None:
    for key in ("retention_score", "value_score", "long_term_value"):
        parsed = percentage_or_number(entry.get(key))
        if parsed is not None:
            return parsed
    return None


def entry_usage(entry: dict[str, Any]) -> float | None:
    for key in ("usage_rate", "pick_rate", "appearance_rate"):
        parsed = percentage_or_number(entry.get(key))
        if parsed is not None:
            return parsed
    return None


def is_high_value(entry: dict[str, Any], score: int, retention: float | None) -> bool:
    tags = entry_tags(entry)
    if tags & HIGH_VALUE_TAGS:
        return True
    if score >= 85:
        return True
    return retention is not None and retention >= 0.8


def is_low_value(entry: dict[str, Any], score: int, retention: float | None) -> bool:
    tags = entry_tags(entry)
    trend = str(entry.get("trend") or "").strip().lower()
    if tags & LOW_VALUE_TAGS:
        return True
    if retention is not None and retention <= 0.45:
        return True
    return score > 0 and score <= 65 and trend in {"down", "declining"}


def recommendation_for(*, owned: bool, high_value: bool, low_value: bool, trend: str) -> tuple[str, str]:
    if owned and high_value:
        return (
            "protect_investment",
            "已在 accepted roster 中，且 tier/保值信号较强；后续培养和配队建议应优先保护这类投入。",
        )
    if owned and low_value:
        return (
            "avoid_overinvestment",
            "已在 accepted roster 中，但保值或趋势偏弱；除非命中具体终局目标，否则不建议继续加码。",
        )
    if owned:
        return (
            "owned_observe",
            "已在 accepted roster 中；当前信号不足以直接提高优先级，继续观察终局适配。",
        )
    if high_value:
        return (
            "watch_candidate",
            "未在 accepted roster 中，但 tier/保值信号较强；这里只做观察候选，不直接生成抽取建议。",
        )
    if trend == "down" or low_value:
        return (
            "low_priority_candidate",
            "未在 accepted roster 中，且趋势或保值偏弱；作为低优先级观察项。",
        )
    return (
        "observe_candidate",
        "未在 accepted roster 中；保留为普通观察项，等待明确终局目标或官方数据确认。",
    )


def output_entry(entry: dict[str, Any], roster_map: dict[str, dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    character = entry_character(entry)
    matched_roster = next((roster_map.get(normalize_name(name)) for name in entry_names(entry) if roster_map.get(normalize_name(name))), None)
    owned = matched_roster is not None
    score = tier_score(entry.get("tier"))
    retention = entry_retention(entry)
    usage = entry_usage(entry)
    trend = str(entry.get("trend") or "unknown").strip().lower() or "unknown"
    high_value = is_high_value(entry, score, retention)
    low_value = is_low_value(entry, score, retention)
    recommendation, reason = recommendation_for(owned=owned, high_value=high_value, low_value=low_value, trend=trend)
    return {
        "character": character,
        "aliases": [name for name in entry_names(entry)[1:]],
        "owned_status": "accepted_roster" if owned else "not_in_roster",
        "tier": entry.get("tier"),
        "tier_score": score,
        "retention_score": retention,
        "usage_rate": usage,
        "trend": trend,
        "role": entry.get("role"),
        "element": entry.get("element") or entry.get("attribute"),
        "modes": normalize_list(entry.get("modes") or entry.get("targets")),
        "value_tags": sorted(entry_tags(entry)),
        "recommendation": recommendation,
        "reason": reason,
        "notes": entry.get("notes") or entry.get("comment"),
        "source": source,
        "roster_snapshot_json": matched_roster.get("snapshot_json") if isinstance(matched_roster, dict) else None,
    }


def sort_key(item: dict[str, Any]) -> tuple[int, int, float, str]:
    recommendation_rank = {
        "protect_investment": 0,
        "watch_candidate": 1,
        "owned_observe": 2,
        "avoid_overinvestment": 3,
        "observe_candidate": 4,
        "low_priority_candidate": 5,
    }.get(str(item.get("recommendation")), 9)
    retention = item.get("retention_score")
    return (
        recommendation_rank,
        -int(item.get("tier_score") or 0),
        -(float(retention) if isinstance(retention, (int, float)) else 0.0),
        str(item.get("character") or ""),
    )


def summary_for(entries: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    accepted = [item for item in entries if item.get("owned_status") == "accepted_roster"]
    return {
        "entry_count": len(entries),
        "accepted_roster_count": len(accepted),
        "candidate_count": len(entries) - len(accepted),
        "owned_high_value_count": sum(1 for item in entries if item.get("recommendation") == "protect_investment"),
        "watch_candidate_count": sum(1 for item in entries if item.get("recommendation") == "watch_candidate"),
        "low_value_owned_count": sum(1 for item in entries if item.get("recommendation") == "avoid_overinvestment"),
        "source_type": source.get("source_type"),
        "source_name": source.get("name"),
    }


def build_tier_watchlist(*, tier_snapshot: Path, output_dir: Path, roster_index: Path | None = None) -> dict[str, Any]:
    snapshot = load_json(tier_snapshot)
    roster = load_json(roster_index) if roster_index and roster_index.exists() else None
    roster_map = roster_character_map(roster)
    source = source_info(snapshot, tier_snapshot)
    entries = [output_entry(entry, roster_map, source) for entry in snapshot_entries(snapshot)]
    entries.sort(key=sort_key)
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "tier_snapshot": str(tier_snapshot),
            "roster_index": str(roster_index) if roster_index else None,
        },
        "source": source,
        "summary": summary_for(entries, source),
        "entries": entries,
        "warnings": [
            "tier watchlist 只读取本地 snapshot；它不是联网爬取，也不是最终抽取建议。",
            "owned_status 只有 accepted_roster 才代表已确认拥有练度。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "tier_watchlist.json"
    md_path = output_dir / "tier_watchlist.md"
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    write_json(json_path, result)
    return result


def percent_label(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{round(float(value) * 100, 1)}%"
    return "N/A"


def render_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    lines = [
        "# Tier / 保值观察",
        "",
        "该文件只做本地观察，不直接生成抽取建议。",
        "",
        f"- entry_count: {summary.get('entry_count', 0)}",
        f"- accepted_roster_count: {summary.get('accepted_roster_count', 0)}",
        f"- owned_high_value_count: {summary.get('owned_high_value_count', 0)}",
        f"- watch_candidate_count: {summary.get('watch_candidate_count', 0)}",
        f"- low_value_owned_count: {summary.get('low_value_owned_count', 0)}",
        "",
        "## Entries",
        "",
    ]
    for index, item in enumerate(result.get("entries", []), start=1):
        lines.extend(
            [
                f"### {index}. {item.get('character')}",
                f"- owned_status: {item.get('owned_status')}",
                f"- tier: {item.get('tier')} ({item.get('tier_score')})",
                f"- retention_score: {percent_label(item.get('retention_score'))}",
                f"- usage_rate: {percent_label(item.get('usage_rate'))}",
                f"- trend: {item.get('trend')}",
                f"- recommendation: {item.get('recommendation')}",
                f"- reason: {item.get('reason')}",
                "",
            ]
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a local tier/value watchlist from a local snapshot.")
    parser.add_argument("--tier-snapshot", required=True, help="Local tier/meta snapshot JSON.")
    parser.add_argument("--roster-index", default=None, help="Optional accepted roster_index.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_tier_watchlist(
            tier_snapshot=resolve_path(args.tier_snapshot),
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            output_dir=resolve_path(args.output_dir),
        )
    except TierWatchlistError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = result["summary"]
    print(f"entry_count: {summary['entry_count']}")
    print(f"accepted_roster_count: {summary['accepted_roster_count']}")
    print(f"owned_high_value_count: {summary['owned_high_value_count']}")
    print(f"watch_candidate_count: {summary['watch_candidate_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
