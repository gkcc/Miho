from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id, parse_date

from .constants import (
    CATEGORY_TO_ROLE,
    CHANGELOG_COLUMNS,
    ELEMENT_CN,
    MODE_CN,
    MODE_URLS,
    PRYDWEN_TIER_COLUMNS,
    RATING_TO_TIER,
    STYLE_CN,
)

TIER_URL = "https://www.prydwen.gg/zenless/tier-list"


class PrydwenClient:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def fetch_html(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", "replace")


def fetch_and_parse_tier(raw_dir: Path, warnings: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = PrydwenClient()
    try:
        html_text = client.fetch_html(TIER_URL)
    except Exception as exc:
        cached = raw_dir / "tier-list_latest.html"
        if not cached.exists():
            warnings.append(f"Prydwen ZZZ tier fetch failed: {exc}")
            return [], []
        warnings.append(f"Prydwen ZZZ tier fetch failed; using cached HTML: {exc}")
        html_text = cached.read_text(encoding="utf-8")
    decoded = decode_payload(html_text)
    raw_dir.joinpath("tier-list_latest.html").write_text(html_text, encoding="utf-8")
    last_updated = extract_last_updated(decoded)
    snapshot_id = _snapshot_id(last_updated)
    if snapshot_id:
        raw_dir.joinpath(f"tier-list_{snapshot_id}.html").write_text(html_text, encoding="utf-8")
    chars = extract_characters(decoded)
    rows = build_tier_rows(chars, last_updated, snapshot_id, datetime.now().isoformat(timespec="seconds"))
    changelog = extract_changelog(decoded)
    if not rows:
        warnings.append("Prydwen ZZZ tier parse warning: no tier rows extracted")
    return rows, changelog


def fetch_prydwen_teams(mode: str, raw_dir: Path, warnings: list[str]) -> dict[str, list[dict[str, Any]]]:
    url = MODE_URLS[mode]
    try:
        html_text = PrydwenClient().fetch_html(url)
    except Exception as exc:
        cached = raw_dir / f"{mode}.html"
        if not cached.exists():
            warnings.append(f"Prydwen ZZZ {mode} fetch failed: {exc}")
            return {}
        warnings.append(f"Prydwen ZZZ {mode} fetch failed; using cached HTML: {exc}")
        html_text = cached.read_text(encoding="utf-8")
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.joinpath(f"{mode}.html").write_text(html_text, encoding="utf-8")
    return extract_teams_from_html(html_text)


def decode_payload(html_text: str) -> str:
    decoded = html_text.replace('\\"', '"').replace("\\/", "/")
    decoded = decoded.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
    return html.unescape(decoded)


def extract_last_updated(decoded: str) -> str:
    match = re.search(r'"lastUpdated":"([^"]+)"', decoded)
    if match:
        return match.group(1)
    match = re.search(r"Last updated:.*?<strong>([^<]+)</strong>", decoded, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_characters(decoded: str) -> list[dict[str, Any]]:
    idx = decoded.find('"characters":')
    if idx == -1:
        return []
    start = decoded.find("[", idx)
    if start == -1:
        return []
    value, _ = json.JSONDecoder().raw_decode(decoded[start:])
    return value if isinstance(value, list) else []


def build_tier_rows(
    characters: list[dict[str, Any]],
    tier_updated_at: str,
    snapshot_id: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    tier_updated_date = _date_from_prydwen_date(tier_updated_at)
    for char in characters:
        slug = normalize_character_id(char.get("slug") or char.get("name"))
        if not slug:
            continue
        for rating in char.get("tierRatings") or []:
            category = str(rating.get("category") or "")
            prydwen_role, role_group, role_group_cn = CATEGORY_TO_ROLE.get(category, (category, "unknown", "未知"))
            tier_rating = rating.get("rating")
            tier = RATING_TO_TIER.get(tier_rating, "")
            base = {
                "tier_snapshot_id": snapshot_id,
                "fetched_at": fetched_at,
                "tier_updated_at": tier_updated_at,
                "tier_updated_date": tier_updated_date,
                "character_slug": slug,
                "character_name_en": char.get("name") or "",
                "character_name_cn": "",
                "prydwen_category": category,
                "prydwen_role": prydwen_role,
                "role_group": role_group,
                "role_group_cn": role_group_cn,
                "tier": tier,
                "rating": tier_rating,
                "tags": rating.get("tags") or "",
                "marks": rating.get("marks") or "",
                "is_new": char.get("isNew") or "",
                "element": char.get("element") or "",
                "element_cn": ELEMENT_CN.get(str(char.get("element") or ""), ""),
                "style": char.get("style") or "",
                "style_cn": STYLE_CN.get(str(char.get("style") or ""), ""),
                "faction": char.get("faction") or "",
                "rarity": char.get("rarity") or "",
                "icon_url": char.get("smallImage") or "",
                "source_url": TIER_URL,
            }
            for mode in MODE_CN:
                row = dict(base)
                row["tier_mode"] = mode
                row["tier_mode_cn"] = MODE_CN[mode]
                output.append(row)
    return output


def extract_changelog(decoded: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"<h6[^>]*>(\d{2}/[A-Za-z]+/\d{4})</h6>", decoded))
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(decoded)
        chunk = decoded[start:end]
        text = _strip_html(chunk)
        if not text:
            continue
        rows.append(
            {
                "changelog_date": _date_from_prydwen_date(match.group(1)),
                "source_url": TIER_URL,
                "character_slugs": ";".join(sorted(set(re.findall(r'data-slug="([^"]+)"', chunk)))),
                "text": text,
            }
        )
    return rows


def merge_tier_history(existing_path: Path, current_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = _read_csv(existing_path, PRYDWEN_TIER_COLUMNS)
    rows: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in existing + current_rows:
        key = (
            str(row.get("tier_snapshot_id", "")),
            str(row.get("tier_mode", "")),
            str(row.get("character_slug", "")),
            str(row.get("prydwen_category", "")),
        )
        rows[key] = row
    return sorted(rows.values(), key=lambda r: (str(r.get("tier_updated_date", "")), str(r.get("tier_mode", "")), str(r.get("character_slug", ""))))


def merge_changelog_history(existing_path: Path, current_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = _read_csv(existing_path, CHANGELOG_COLUMNS)
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing + current_rows:
        digest = hashlib.sha1(str(row.get("text", "")).encode("utf-8")).hexdigest()
        rows[(str(row.get("changelog_date", "")), digest)] = row
    return sorted(rows.values(), key=lambda r: str(r.get("changelog_date", "")), reverse=True)


def extract_teams_from_html(text: str) -> dict[str, list[dict[str, Any]]]:
    teams: dict[str, list[dict[str, Any]]] = {}
    decoded = decode_payload(text)
    for value in _json_values_after_key(decoded, "teams"):
        if isinstance(value, dict):
            for scope, rows in value.items():
                if _looks_like_team_list(rows):
                    teams.setdefault(str(scope), []).extend(rows)
    return teams


def _json_values_after_key(text: str, key: str) -> list[Any]:
    values: list[Any] = []
    decoder = json.JSONDecoder()
    needle = f'"{key}"'
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx == -1:
            break
        colon = text.find(":", idx + len(needle))
        if colon == -1:
            break
        value_start = colon + 1
        while value_start < len(text) and text[value_start].isspace():
            value_start += 1
        try:
            value, offset = decoder.raw_decode(text[value_start:])
        except json.JSONDecodeError:
            start = idx + len(needle)
            continue
        values.append(value)
        start = value_start + offset
    return values


def _looks_like_team_list(value: Any) -> bool:
    return bool(
        isinstance(value, list)
        and value
        and isinstance(value[0], dict)
        and {"char_one", "char_two", "char_three"}.issubset(value[0])
    )


def _strip_html(chunk: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", chunk, flags=re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _snapshot_id(last_updated: str) -> str:
    parsed = _date_from_prydwen_date(last_updated)
    return parsed.replace("-", "") if parsed else ""


def _date_from_prydwen_date(value: str) -> str:
    text = str(value or "").strip()
    for fmt in ("%d/%B/%Y", "%d/%b/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return parse_date(text)


def _read_csv(path: Path, columns: list[str]) -> list[dict[str, Any]]:
    import csv

    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, fieldnames=None))
