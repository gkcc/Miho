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

OBSERVATION_STATUS_BY_RECOMMENDATION = {
    "protect_investment": "owned_high_value",
    "watch_candidate": "non_owned_watch_only",
    "avoid_overinvestment": "owned_low_value_caution",
    "low_priority_candidate": "non_owned_low_priority_watch",
    "owned_observe": "owned_observe",
    "observe_candidate": "non_owned_observe",
}

ENTRY_STATUS_RANK = {
    "verified": 0,
    "low_trust": 1,
    "stale": 2,
    "unverified": 3,
    "invalid_source": 4,
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


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def snapshot_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("entries", "characters", "items"):
        value = snapshot.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise TierWatchlistError("Tier snapshot must contain an entries, characters, or items list")


def normalize_source(source: dict[str, Any], tier_snapshot_path: Path, index: int = 0) -> dict[str, Any]:
    title = source.get("title") or source.get("name") or source.get("source_name") or tier_snapshot_path.name
    source_id = source.get("source_id") or source.get("id") or f"source_{index + 1}"
    return {
        "source_id": source_id,
        "title": title,
        "name": title,
        "source_type": source.get("source_type") or source.get("source_kind") or "local_snapshot",
        "source_ref": source.get("source_ref") or source.get("url") or str(tier_snapshot_path),
        "period": source.get("period"),
        "captured_at": source.get("captured_at"),
        "content_sha256": source.get("content_sha256") or source.get("sha256"),
        "trust_level": str(source.get("trust_level") or "medium").strip().lower(),
    }


def source_infos(snapshot: dict[str, Any], tier_snapshot_path: Path) -> list[dict[str, Any]]:
    sources = snapshot.get("sources")
    if isinstance(sources, list) and sources:
        return [normalize_source(item, tier_snapshot_path, index) for index, item in enumerate(sources) if isinstance(item, dict)]
    source = snapshot.get("source") if isinstance(snapshot.get("source"), dict) else {}
    merged = {
        **source,
        "source_type": source.get("source_type") or snapshot.get("source_type"),
        "captured_at": source.get("captured_at") or snapshot.get("captured_at"),
        "period": source.get("period") or snapshot.get("period"),
        "content_sha256": source.get("content_sha256") or snapshot.get("content_sha256"),
        "trust_level": source.get("trust_level") or snapshot.get("trust_level"),
    }
    return [normalize_source(merged, tier_snapshot_path, 0)]


def source_map(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(source.get("source_id")): source for source in sources if source.get("source_id")}


def entry_source(entry: dict[str, Any], sources_by_id: dict[str, dict[str, Any]], default_source: dict[str, Any]) -> dict[str, Any]:
    ids = normalize_list(entry.get("evidence_source_ids") or entry.get("source_ids") or entry.get("source_id"))
    for source_id in ids:
        if source_id in sources_by_id:
            return sources_by_id[source_id]
    entry_source_value = entry.get("source")
    if isinstance(entry_source_value, dict):
        return normalize_source(entry_source_value, Path(str(default_source.get("source_ref") or PROJECT_ROOT)), 0)
    return default_source


def source_status(source: dict[str, Any], *, stale_days: int, now: datetime | None = None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not source:
        return "invalid_source", ["缺少 evidence source。"]
    missing_proof = False
    missing_time = False
    is_stale = False
    is_low_trust = False
    if not source.get("source_ref") or not source.get("content_sha256"):
        missing_proof = True
        warnings.append("缺少 source_ref 或 content_sha256，tier entry 只能作为未验证参考。")
    captured_at = parse_datetime(source.get("captured_at"))
    if captured_at is None:
        missing_time = True
        warnings.append("缺少 captured_at 或时间格式无法解析，无法判断新鲜度。")
    else:
        current = now or datetime.now(timezone.utc).astimezone()
        age_days = (current - captured_at.astimezone(current.tzinfo)).days
        if age_days > stale_days:
            is_stale = True
            warnings.append(f"source captured_at 已超过 {stale_days} 天，tier entry 标记为 stale。")
    if str(source.get("trust_level") or "").lower() == "low":
        is_low_trust = True
        warnings.append("source trust_level=low，只能作为弱参考。")
    if missing_proof or missing_time:
        return "unverified", warnings
    if is_stale:
        return "stale", warnings
    if is_low_trust:
        return "low_trust", warnings
    return "verified", warnings


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
    observation_status = OBSERVATION_STATUS_BY_RECOMMENDATION.get(recommendation, "observe")
    entry_status = source.get("entry_status") or "verified"
    evidence = {
        "source_id": source.get("source_id"),
        "source_title": source.get("title") or source.get("name"),
        "source_type": source.get("source_type"),
        "source_ref": source.get("source_ref"),
        "period": source.get("period"),
        "captured_at": source.get("captured_at"),
        "content_sha256": source.get("content_sha256"),
        "content_sha256_short": str(source.get("content_sha256") or "")[:12] or None,
        "trust_level": source.get("trust_level"),
    }
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
        "observation_status": observation_status,
        "recommendation": recommendation,
        "reason": reason,
        "entry_status": entry_status,
        "entry_warnings": source.get("entry_warnings", []) if isinstance(source.get("entry_warnings"), list) else [],
        "evidence": evidence,
        "notes": entry.get("notes") or entry.get("comment"),
        "source": source,
        "roster_snapshot_json": matched_roster.get("snapshot_json") if isinstance(matched_roster, dict) else None,
    }


def sort_key(item: dict[str, Any]) -> tuple[int, int, int, float, str]:
    status_rank = ENTRY_STATUS_RANK.get(str(item.get("entry_status") or "verified"), 9)
    observation_rank = {
        "owned_high_value": 0,
        "non_owned_watch_only": 1,
        "owned_observe": 2,
        "owned_low_value_caution": 3,
        "non_owned_observe": 4,
        "non_owned_low_priority_watch": 5,
    }.get(str(item.get("observation_status") or ""), 9)
    retention = item.get("retention_score")
    return (
        status_rank,
        observation_rank,
        -int(item.get("tier_score") or 0),
        -(float(retention) if isinstance(retention, (int, float)) else 0.0),
        str(item.get("character") or ""),
    )


def summary_for(entries: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [item for item in entries if item.get("owned_status") == "accepted_roster"]
    return {
        "entry_count": len(entries),
        "accepted_roster_count": len(accepted),
        "candidate_count": len(entries) - len(accepted),
        "owned_high_value_count": sum(1 for item in entries if item.get("observation_status") == "owned_high_value"),
        "watch_candidate_count": sum(1 for item in entries if item.get("observation_status") == "non_owned_watch_only"),
        "low_value_owned_count": sum(1 for item in entries if item.get("observation_status") == "owned_low_value_caution"),
        "verified_entry_count": sum(1 for item in entries if item.get("entry_status") == "verified"),
        "stale_entry_count": sum(1 for item in entries if item.get("entry_status") == "stale"),
        "unverified_entry_count": sum(1 for item in entries if item.get("entry_status") in {"unverified", "invalid_source"}),
        "low_trust_entry_count": sum(1 for item in entries if item.get("entry_status") == "low_trust"),
        "stale_source_count": sum(1 for item in entries if item.get("entry_status") == "stale"),
        "unverified_source_count": sum(1 for item in entries if item.get("entry_status") in {"unverified", "invalid_source"}),
        "source_type": sources[0].get("source_type") if sources else None,
        "source_name": sources[0].get("name") if sources else None,
    }


def build_tier_watchlist(*, tier_snapshot: Path, output_dir: Path, roster_index: Path | None = None, stale_days: int = 60) -> dict[str, Any]:
    snapshot = load_json(tier_snapshot)
    roster = load_json(roster_index) if roster_index and roster_index.exists() else None
    roster_map = roster_character_map(roster)
    sources = source_infos(snapshot, tier_snapshot)
    sources_by_id = source_map(sources)
    default_source = sources[0] if sources else {}
    entries = []
    for raw_entry in snapshot_entries(snapshot):
        source = entry_source(raw_entry, sources_by_id, default_source)
        entry_status, entry_warnings = source_status(source, stale_days=stale_days)
        source_with_status = {**source, "entry_status": entry_status, "entry_warnings": entry_warnings}
        entries.append(output_entry(raw_entry, roster_map, source_with_status))
    entries.sort(key=sort_key)
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "input": {
            "tier_snapshot": str(tier_snapshot),
            "roster_index": str(roster_index) if roster_index else None,
            "stale_days": stale_days,
        },
        "source": default_source,
        "sources": sources,
        "summary": summary_for(entries, sources),
        "entries": entries,
        "warnings": [
            "tier watchlist 只读取本地 snapshot；它不是联网爬取，也不是最终抽取建议。",
            "owned_status 只有 accepted_roster 才代表已确认拥有练度。",
            "stale/unverified/low_trust tier entry 只能作为弱参考，不得提升 team rank。",
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
        f"- verified_entry_count: {summary.get('verified_entry_count', 0)}",
        f"- stale_entry_count: {summary.get('stale_entry_count', 0)}",
        f"- unverified_entry_count: {summary.get('unverified_entry_count', 0)}",
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
                f"- observation_status: {item.get('observation_status')}",
                f"- entry_status: {item.get('entry_status')}",
                f"- source_period: {(item.get('evidence') or {}).get('period') if isinstance(item.get('evidence'), dict) else 'N/A'}",
                f"- source_hash: {(item.get('evidence') or {}).get('content_sha256_short') if isinstance(item.get('evidence'), dict) else 'N/A'}",
                f"- reason: {item.get('reason')}",
                "",
            ]
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a local tier/value watchlist from a local snapshot.")
    parser.add_argument("--tier-snapshot", required=True, help="Local tier/meta snapshot JSON.")
    parser.add_argument("--roster-index", default=None, help="Optional accepted roster_index.json.")
    parser.add_argument("--stale-days", type=int, default=60, help="Mark tier sources older than this many days as stale. Default: 60.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_tier_watchlist(
            tier_snapshot=resolve_path(args.tier_snapshot),
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            stale_days=args.stale_days,
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
    print(f"verified_entry_count: {summary['verified_entry_count']}")
    print(f"stale_entry_count: {summary['stale_entry_count']}")
    print(f"unverified_entry_count: {summary['unverified_entry_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
