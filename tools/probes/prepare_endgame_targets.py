#!/usr/bin/env python
"""Prepare local endgame target JSON from public web pages or saved text."""

from __future__ import annotations

import argparse
import html
import ipaddress
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "targets"
SCHEMA_VERSION = "p1.3-target-intake-draft"

ACTIVITY_ALIASES = {
    "zzz": ["式舆防卫战", "危局强袭战", "零号空洞", "断层之谜"],
    "hsr": ["混沌回忆", "虚构叙事", "末日幻影", "模拟宇宙", "差分宇宙"],
}

WEAKNESS_ALIASES = {
    "physical": ["物理", "物理属性"],
    "fire": ["火", "火属性"],
    "ice": ["冰", "冰属性"],
    "electric": ["电", "雷", "雷属性", "电属性"],
    "ether": ["以太", "以太属性"],
    "wind": ["风", "风属性"],
    "quantum": ["量子", "量子属性"],
    "imaginary": ["虚数", "虚数属性"],
}

MECHANIC_ALIASES = {
    "anomaly": ["异常", "异常积蓄", "紊乱"],
    "stun": ["击破", "失衡", "削韧"],
    "crit": ["暴击", "暴击伤害", "暴击率"],
    "shield": ["护盾", "护盾量"],
    "follow_up": ["追加攻击", "追击"],
    "dot": ["持续伤害", "dot", "灼烧", "裂伤", "触电"],
    "summon": ["召唤物", "记忆精灵"],
    "aoe": ["群攻", "范围伤害"],
    "single_target": ["单体", "首领"],
    "survival": ["生存", "治疗", "承伤"],
    "energy": ["能量", "终结技", "能量回复"],
}


class TargetIntakeError(RuntimeError):
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
        raise TargetIntakeError(f"JSON file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TargetIntakeError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise TargetIntakeError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_public_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise TargetIntakeError("Only http(s) public URLs are allowed")
    host = parsed.hostname
    if not host:
        raise TargetIntakeError("URL must include a hostname")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise TargetIntakeError("Localhost URLs are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return parsed
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified:
        raise TargetIntakeError("Private, loopback, reserved, or link-local URLs are not allowed")
    return parsed


def fetch_url(url: str, timeout: int = 20) -> tuple[str, dict[str, Any]]:
    validate_public_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MihoProbe/0.1 local endgame target intake",
            "Accept": "text/html,application/json,text/plain;q=0.9,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is validated as public http(s).
            raw = response.read(2_000_000)
            encoding = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(encoding, errors="replace")
            metadata = {
                "kind": "url",
                "uri": url,
                "fetched_at": now_iso(),
                "content_type": response.headers.get("content-type"),
                "byte_count": len(raw),
            }
            return text, metadata
    except (urllib.error.URLError, TimeoutError) as exc:
        raise TargetIntakeError(f"Failed to fetch URL: {url}. Details: {exc}") from exc


def read_text_file(path: Path) -> tuple[str, dict[str, Any]]:
    if not path.exists():
        raise TargetIntakeError(f"Input file does not exist: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, {"kind": "file", "path": str(path), "read_at": now_iso(), "byte_count": path.stat().st_size}


def strip_html_markup(text: str) -> str:
    cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_title(raw_text: str, plain_text: str) -> str | None:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_text)
    if match:
        title = strip_html_markup(match.group(1))
        if title:
            return title[:120]
    return plain_text[:80] if plain_text else None


def contains_alias(text: str, aliases: list[str]) -> bool:
    text_lower = text.lower()
    return any(alias.lower() in text_lower for alias in aliases)


def extract_activity(game: str, text: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for name in ACTIVITY_ALIASES.get(game, []):
        if name in text:
            return name
    return "待确认高难目标"


def extract_tags(text: str, aliases: dict[str, list[str]], explicit: list[str] | None = None) -> list[str]:
    tags = list(explicit or [])
    for tag, words in aliases.items():
        if tag not in tags and contains_alias(text, words):
            tags.append(tag)
    return tags


def parse_stat_minimums(values: list[str]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise TargetIntakeError(f"Stat minimum must use key=value: {value}")
        key, raw = value.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key or not raw:
            raise TargetIntakeError(f"Stat minimum must use key=value: {value}")
        stats[key] = raw
    return stats


def default_minimums(args: argparse.Namespace | dict[str, Any]) -> dict[str, Any]:
    get = args.get if isinstance(args, dict) else lambda key, default=None: getattr(args, key, default)
    minimums = {
        "character_level": get("character_level", 60),
        "equipment_level": get("equipment_level", 60),
        "skill_level": get("skill_level", 8),
        "drive_disc_level": get("drive_disc_level", 12),
    }
    stat_values = get("stat", []) or []
    if isinstance(stat_values, dict):
        minimums["stats"] = stat_values
    else:
        stats = parse_stat_minimums(list(stat_values))
        if stats:
            minimums["stats"] = stats
    return minimums


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def source_cases_from_manifest(path: Path) -> tuple[str, str, list[dict[str, Any]], dict[str, Any]]:
    data = load_json(path)
    game = str(data.get("game") or "zzz")
    source_type = str(data.get("source_type") or data.get("source", {}).get("type") or "public_web_snapshot")
    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list):
        raise TargetIntakeError("Manifest must contain a sources list")
    return game, source_type, [dict(item) for item in raw_sources if isinstance(item, dict)], data


def source_cases_from_args(args: argparse.Namespace) -> tuple[str, str, list[dict[str, Any]], dict[str, Any]]:
    sources = []
    for url in args.url:
        sources.append({"url": url})
    for path in args.input:
        sources.append({"input": path})
    if not sources:
        raise TargetIntakeError("Provide at least one --url, --input, or --manifest source")
    for source in sources:
        source.update(
            {
                "activity_name": args.activity_name,
                "target_tier": args.target_tier,
                "priority": args.priority,
                "preferred_characters": args.preferred_character,
                "mechanic_tags": args.mechanic_tag,
                "weakness_tags": args.weakness_tag,
                "minimums": default_minimums(args),
            }
        )
    return args.game, args.source_type, sources, {}


def load_source_text(source: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if source.get("url"):
        return fetch_url(str(source["url"]))
    if source.get("input"):
        return read_text_file(resolve_path(str(source["input"])))
    raise TargetIntakeError("Each source must include url or input")


def evidence_excerpt(text: str, max_length: int = 240) -> str:
    return text[:max_length].strip()


def build_target_from_source(game: str, source: dict[str, Any], index: int) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    raw_text, metadata = load_source_text(source)
    plain_text = strip_html_markup(raw_text)
    title = extract_title(raw_text, plain_text)
    metadata["title"] = title
    metadata["text_excerpt"] = evidence_excerpt(plain_text)
    activity = extract_activity(game, plain_text, source.get("activity_name"))
    weakness_tags = extract_tags(plain_text, WEAKNESS_ALIASES, normalize_list(source.get("weakness_tags")))
    mechanic_tags = extract_tags(plain_text, MECHANIC_ALIASES, normalize_list(source.get("mechanic_tags")))
    preferred_characters = normalize_list(source.get("preferred_characters"))
    minimums = source.get("minimums") if isinstance(source.get("minimums"), dict) else {}
    target = {
        "goal_id": str(source.get("goal_id") or f"{game}_target_{index}"),
        "activity_name": activity,
        "period": source.get("period") or title,
        "target_tier": source.get("target_tier") or "待确认",
        "priority": source.get("priority") or "medium",
        "weakness_tags": weakness_tags,
        "mechanic_tags": mechanic_tags,
        "preferred_characters": preferred_characters,
        "recommended_team_templates": source.get("recommended_team_templates") if isinstance(source.get("recommended_team_templates"), list) else [],
        "minimums": minimums,
        "evidence": {
            "source_index": index,
            "title": title,
            "excerpt": evidence_excerpt(plain_text),
        },
    }
    warnings = []
    if activity == "待确认高难目标":
        warnings.append(f"source #{index} 未识别出已知高难活动名，需要人工确认 activity_name。")
    if not preferred_characters:
        warnings.append(f"source #{index} 未配置 preferred_characters，planner 只能使用默认长期练度目标。")
    return target, metadata, warnings


def prepare_targets(
    *,
    game: str,
    source_type: str,
    sources: list[dict[str, Any]],
    output_dir: Path,
    manifest_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_defaults = manifest_defaults or {}
    default_minimum_config = manifest_defaults.get("default_minimums")
    if not isinstance(default_minimum_config, dict):
        default_minimum_config = default_minimums(manifest_defaults) if manifest_defaults else {
            "character_level": 60,
            "equipment_level": 60,
            "skill_level": 8,
            "drive_disc_level": 12,
        }
    target_items = []
    source_refs = []
    warnings = []
    for index, source in enumerate(sources, start=1):
        target, metadata, source_warnings = build_target_from_source(game, source, index)
        target_items.append(target)
        source_refs.append(metadata)
        warnings.extend(source_warnings)
    if source_type not in {"official_current", "official_snapshot"}:
        warnings.append("目标来源不是 official_current / official_snapshot，不能当作当前线上高难事实。")
    targets = {
        "schema_version": SCHEMA_VERSION,
        "game": game,
        "created_at": now_iso(),
        "source": {
            "type": source_type,
            "note": "public endgame target intake; no login, no cookies, no session reuse",
            "source_count": len(source_refs),
        },
        "sources": source_refs,
        "default_minimums": default_minimum_config,
        "targets": target_items,
        "warnings": list(dict.fromkeys(warnings)),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json = output_dir / "endgame_targets.json"
    write_json(output_json, targets)
    targets["output_json"] = str(output_json)
    write_json(output_json, targets)
    return targets


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare local planner target JSON from public endgame sources.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--manifest", default=None, help="JSON manifest containing game/source_type/sources.")
    source.add_argument("--url", action="append", default=[], help="Public http(s) source URL. Can be repeated.")
    parser.add_argument("--input", action="append", default=[], help="Saved public text/HTML source file. Can be repeated.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz")
    parser.add_argument(
        "--source-type",
        choices=("manual", "public_web_snapshot", "official_snapshot", "official_current", "mock"),
        default="public_web_snapshot",
    )
    parser.add_argument("--activity-name", default=None)
    parser.add_argument("--target-tier", default="待确认")
    parser.add_argument("--priority", choices=("high", "medium", "low"), default="medium")
    parser.add_argument("--preferred-character", action="append", default=[])
    parser.add_argument("--mechanic-tag", action="append", default=[])
    parser.add_argument("--weakness-tag", action="append", default=[])
    parser.add_argument("--character-level", default=60)
    parser.add_argument("--equipment-level", default=60)
    parser.add_argument("--skill-level", default=8)
    parser.add_argument("--drive-disc-level", default=12)
    parser.add_argument("--stat", action="append", default=[], help="Minimum stat in key=value form, e.g. atk=2000.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/targets.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        if args.manifest and (args.url or args.input):
            raise TargetIntakeError("--manifest cannot be combined with --url or --input")
        if args.manifest:
            game, source_type, sources, defaults = source_cases_from_manifest(resolve_path(args.manifest))
        else:
            game, source_type, sources, defaults = source_cases_from_args(args)
        targets = prepare_targets(
            game=game,
            source_type=source_type,
            sources=sources,
            output_dir=resolve_path(args.output_dir),
            manifest_defaults=defaults,
        )
    except TargetIntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"target_count: {len(targets['targets'])}")
    print(f"source_count: {len(targets['sources'])}")
    for warning in targets.get("warnings", []):
        print(f"warning: {warning}")
    print(f"output_json: {targets['output_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
