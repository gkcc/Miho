#!/usr/bin/env python
"""Prepare a local ZZZ public-meta snapshot from Prydwen pages.

The script only reads public pages/API endpoints and writes ignored local probe
artifacts under data/probes by default. It does not read account state,
cookies, tokens, or MiYo local app data.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p0.1-zzz-public-meta-snapshot"
PRYDWEN_BASE_URL = "https://www.prydwen.gg"
TIER_URL = f"{PRYDWEN_BASE_URL}/zenless/tier-list"
ENDGAME_PAGES = {
    "shiyu_defense": f"{PRYDWEN_BASE_URL}/zenless/shiyu-defense",
    "deadly_assault": f"{PRYDWEN_BASE_URL}/zenless/deadly-assault",
}
ANALYTICS_API_PATH = "/api/zenless/analytics"


class MetaSnapshotError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def short_hash(value: str | None) -> str | None:
    if not value:
        return None
    return value[:12]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_url(url: str, *, timeout: int, user_agent: str, accept: str = "*/*") -> tuple[bytes, dict[str, str]]:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": accept,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), {key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        raise MetaSnapshotError(f"HTTP {exc.code} while fetching {url}") from exc
    except URLError as exc:
        raise MetaSnapshotError(f"Network error while fetching {url}: {exc.reason}") from exc


def decode_text(content: bytes, headers: dict[str, str]) -> str:
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.I)
    encoding = match.group(1) if match else "utf-8"
    return content.decode(encoding, errors="replace")


def unescape_rsc_payload(text: str) -> str:
    return (
        text.replace('\\"', '"')
        .replace("\\/", "/")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&")
        .replace("\\u0027", "'")
    )


def balanced_json_object(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_tier_entries(page_text: str) -> list[dict[str, Any]]:
    payload = unescape_rsc_payload(page_text)
    entries: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r'"tierRatings"\s*:\s*\[', payload):
        start = payload.rfind('{"id"', 0, match.start())
        if start < 0:
            start = payload.rfind('{"slug"', 0, match.start())
        if start < 0:
            continue
        raw_object = balanced_json_object(payload, start)
        if not raw_object:
            continue
        try:
            item = json.loads(raw_object)
        except json.JSONDecodeError:
            continue
        slug = item.get("slug")
        ratings = item.get("tierRatings")
        if not slug or not isinstance(ratings, list):
            continue
        entries[str(slug)] = {
            "agent_slug": slug,
            "name": item.get("name"),
            "rarity": item.get("rarity"),
            "element": item.get("element"),
            "specialty": item.get("style"),
            "faction": item.get("faction"),
            "is_upcoming": bool(item.get("upcoming")),
            "is_new": bool(item.get("isNew")),
            "upcoming_version": item.get("upcomingVersion"),
            "tier_ratings": [
                {
                    "category": rating.get("category"),
                    "rating": rating.get("rating"),
                    "tags": rating.get("tags"),
                    "marks": rating.get("marks"),
                    "has_potential": truthy_text(rating.get("has_potential")),
                }
                for rating in ratings
                if isinstance(rating, dict)
            ],
        }
    return sorted(entries.values(), key=lambda item: str(item.get("agent_slug") or ""))


def truthy_text(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def parse_phase_options(page_text: str) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for match in re.finditer(r'<option value="(\d+)"([^>]*)>(.*?)</option>', page_text, flags=re.S):
        label = html.unescape(re.sub(r"<[^>]+>", "", match.group(3)))
        options.append(
            {
                "phase_id": int(match.group(1)),
                "label": re.sub(r"\s+", " ", label).strip(),
                "selected": "selected" in match.group(2),
            }
        )
    return options


def analytics_api_url(phase_id: int) -> str:
    return f"{PRYDWEN_BASE_URL}{ANALYTICS_API_PATH}?phaseId={phase_id}"


def normalize_character_stats(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("char"):
            continue
        result.append(
            {
                "agent_slug": item.get("char"),
                "name": item.get("name"),
                "current_app_rate": item.get("current_app_rate"),
                "previous_app_rate": item.get("prev_app_rate"),
                "current_avg_score": item.get("current_avg_score"),
                "previous_avg_score": item.get("prev_avg_score"),
                "app_free": item.get("app_free"),
                "app_dupes": item.get("app_dupes"),
                "avg_score_free": item.get("round_free"),
                "avg_score_dupes": item.get("round_dupes"),
                "boss_usage": {
                    "1": item.get("boss_1_usage"),
                    "2": item.get("boss_2_usage"),
                    "3": item.get("boss_3_usage"),
                },
                "boss_avg_score": {
                    "1": item.get("boss_1_score"),
                    "2": item.get("boss_2_score"),
                    "3": item.get("boss_3_score"),
                },
                "boss_usage_free": {
                    "1": item.get("boss_1_usage_free"),
                    "2": item.get("boss_2_usage_free"),
                    "3": item.get("boss_3_usage_free"),
                },
                "boss_usage_dupes": {
                    "1": item.get("boss_1_usage_dupes"),
                    "2": item.get("boss_2_usage_dupes"),
                    "3": item.get("boss_3_usage_dupes"),
                },
                "boss_avg_score_free": {
                    "1": item.get("boss_1_score_free"),
                    "2": item.get("boss_2_score_free"),
                    "3": item.get("boss_3_score_free"),
                },
                "boss_avg_score_dupes": {
                    "1": item.get("boss_1_score_dupes"),
                    "2": item.get("boss_2_score_dupes"),
                    "3": item.get("boss_3_score_dupes"),
                },
            }
        )
    return result


def normalize_team_usage(teams: Any) -> list[dict[str, Any]]:
    if not isinstance(teams, dict):
        return []
    result: list[dict[str, Any]] = []
    for scope_key, scope_items in teams.items():
        if not isinstance(scope_items, list):
            continue
        for item in scope_items:
            if not isinstance(item, dict):
                continue
            result.append(
                {
                    "scope_key": str(scope_key),
                    "rank": item.get("rank"),
                    "agent_1_slug": item.get("char_one"),
                    "agent_2_slug": item.get("char_two"),
                    "agent_3_slug": item.get("char_three"),
                    "bangboo_slug": item.get("bangboo"),
                    "app_rate": item.get("app_rate"),
                    "avg_score": item.get("avg_round"),
                    "avg_score_m1plus": item.get("avg_round_m1"),
                }
            )
    return result


def normalize_analytics(data: dict[str, Any], *, phase_label: str | None, source_url: str, content_sha256: str) -> dict[str, Any]:
    phase = data.get("phase") if isinstance(data.get("phase"), dict) else {}
    return {
        "phase": {
            "phase_id": phase.get("id"),
            "mode": phase.get("mode"),
            "phase": phase.get("phase"),
            "label": phase_label,
            "update_date": phase.get("updateDate"),
            "total_users": phase.get("totalUsers"),
            "source_counts": {
                "prydwen": phase.get("prydwenUsers"),
                "stardb": phase.get("stardbUsers"),
                "hoyobuddy": phase.get("hoyobuddyUsers"),
                "interknot": phase.get("interknotUsers"),
                "random_uid": phase.get("randomUidUsers"),
                "self_reported": phase.get("selfReportedUsers"),
            },
            "boss_names": phase.get("bossNames", []) if isinstance(phase.get("bossNames"), list) else [],
            "new_agent_slugs": phase.get("newCharSlugs", []) if isinstance(phase.get("newCharSlugs"), list) else [],
        },
        "source": {
            "source_ref": source_url,
            "content_sha256": content_sha256,
            "content_sha256_short": short_hash(content_sha256),
            "trust_level": "medium",
            "source_type": "public_prydwen_analytics_api",
        },
        "character_stats": normalize_character_stats(data.get("charStats")),
        "team_usage": normalize_team_usage(data.get("teams")),
    }


def fetch_text_source(url: str, *, timeout: int, user_agent: str) -> dict[str, Any]:
    content, headers = fetch_url(url, timeout=timeout, user_agent=user_agent, accept="text/html,application/xhtml+xml")
    digest = sha256_bytes(content)
    return {
        "url": url,
        "content": content,
        "text": decode_text(content, headers),
        "content_sha256": digest,
        "headers": headers,
    }


def fetch_json_source(url: str, *, timeout: int, user_agent: str) -> dict[str, Any]:
    content, headers = fetch_url(url, timeout=timeout, user_agent=user_agent, accept="application/json")
    digest = sha256_bytes(content)
    try:
        parsed = json.loads(decode_text(content, headers))
    except json.JSONDecodeError as exc:
        raise MetaSnapshotError(f"Invalid JSON from {url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MetaSnapshotError(f"Expected JSON object from {url}")
    return {
        "url": url,
        "content_sha256": digest,
        "headers": headers,
        "json": parsed,
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    user_agent = args.user_agent
    tier_page = fetch_text_source(TIER_URL, timeout=args.timeout, user_agent=user_agent)
    tier_entries = parse_tier_entries(tier_page["text"])

    modes: dict[str, Any] = {}
    page_sources: list[dict[str, Any]] = [
        {
            "source_key": "prydwen_zzz_tier_list",
            "source_ref": TIER_URL,
            "content_sha256": tier_page["content_sha256"],
            "content_sha256_short": short_hash(tier_page["content_sha256"]),
        }
    ]
    for mode, page_url in ENDGAME_PAGES.items():
        page = fetch_text_source(page_url, timeout=args.timeout, user_agent=user_agent)
        phase_options = parse_phase_options(page["text"])
        selected = [item for item in phase_options if item.get("selected")]
        chosen_options = selected if args.current_only else phase_options
        if args.max_phases is not None:
            chosen_options = chosen_options[: args.max_phases]
        phases: list[dict[str, Any]] = []
        for index, option in enumerate(chosen_options):
            if index and args.request_delay > 0:
                time.sleep(args.request_delay)
            url = analytics_api_url(int(option["phase_id"]))
            api = fetch_json_source(url, timeout=args.timeout, user_agent=user_agent)
            phases.append(
                normalize_analytics(
                    api["json"],
                    phase_label=str(option.get("label") or ""),
                    source_url=url,
                    content_sha256=api["content_sha256"],
                )
            )
        modes[mode] = {
            "page_url": page_url,
            "page_content_sha256": page["content_sha256"],
            "available_phases": phase_options,
            "phases": phases,
        }
        page_sources.append(
            {
                "source_key": f"prydwen_zzz_{mode}",
                "source_ref": page_url,
                "content_sha256": page["content_sha256"],
                "content_sha256_short": short_hash(page["content_sha256"]),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_policy": {
            "network": "public_prydwen_pages_and_public_analytics_api_only",
            "no_account_state": True,
            "no_cookies_or_tokens": True,
            "raw_pages_committed": False,
            "notes": [
                "Prydwen appearance rate is a usage signal, not ownership rate or pull value.",
                "Endgame scores and team usage are community-submitted statistics and must be combined with local box constraints.",
            ],
        },
        "sources": page_sources,
        "tier_list": {
            "source_ref": TIER_URL,
            "content_sha256": tier_page["content_sha256"],
            "entries": tier_entries,
        },
        "endgame": {
            "modes": modes,
        },
    }


def print_summary(snapshot: dict[str, Any], output: Path) -> None:
    tier_entries = snapshot.get("tier_list", {}).get("entries", [])
    print(f"snapshot_json: {output}")
    print(f"tier_entries: {len(tier_entries)}")
    modes = snapshot.get("endgame", {}).get("modes", {})
    for mode, data in modes.items():
        phases = data.get("phases", [])
        char_count = sum(len(item.get("character_stats", [])) for item in phases if isinstance(item, dict))
        team_count = sum(len(item.get("team_usage", [])) for item in phases if isinstance(item, dict))
        labels = [str(item.get("phase", {}).get("label") or item.get("phase", {}).get("phase")) for item in phases if isinstance(item, dict)]
        print(f"{mode}: phases={len(phases)} character_rows={char_count} team_rows={team_count}")
        print(f"{mode}_phase_labels: {', '.join(labels)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="data/probes/meta/zzz_prydwen_meta_snapshot.json",
        help="Output JSON path. Defaults to ignored data/probes/meta.",
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Fetch only the currently selected phase from each endgame page.",
    )
    parser.add_argument(
        "--max-phases",
        type=int,
        default=None,
        help="Limit phases per mode while debugging.",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--request-delay", type=float, default=0.15)
    parser.add_argument(
        "--user-agent",
        default="MihoProbe/0.1 public-meta-snapshot (+local personal research)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output = resolve_path(args.output)
    try:
        snapshot = build_snapshot(args)
        write_json(output, snapshot)
        print_summary(snapshot, output)
    except MetaSnapshotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
