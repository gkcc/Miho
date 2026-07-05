from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id

HOYOWIKI_APP = "zzz"
HOYOWIKI_AGENT_MENU_ID = "8"
HOYOWIKI_BANGBOO_MENU_ID = "15"
HOYOWIKI_SOURCE = "HoYoWiki official zzz agent menu_id=8"
BANGBOO_SOURCE = "HoYoWiki official zzz bangboo menu_id=15"

MANUAL_ALIASES = {
    "alexandrina-sebastiane": ["rina"],
    "alice-thymefield": ["alice"],
    "asaba-harumasa": ["harumasa"],
    "billy-starlight": ["starlight-billy"],
    "burnice-white": ["burnice"],
    "caesar-king": ["caesar"],
    "ellen-joe": ["ellen"],
    "evelyn-chevalier": ["evelyn"],
    "hoshimi-miyabi": ["miyabi"],
    "hugo-vlad": ["hugo"],
    "komano-manato": ["manato"],
    "luciana-de-montefio": ["lucy"],
    "nekomiya-mana": ["nekomata"],
    "orphie-magnusson-and-magus": ["orphie-and-magus"],
    "piper-wheel": ["piper"],
    "pulchra-fellini": ["pulchra"],
    "soldier-0-anby": ["anby-demara-soldier-0", "anby-soldier-0"],
    "tsukishiro-yanagi": ["yanagi"],
    "ukinami-yuzuha": ["yuzuha"],
    "vivian-banshee": ["vivian"],
    "von-lycaon": ["lycaon"],
}

SUPPLEMENTAL_OFFICIAL_ZH = {
    "velina": {
        "character_name_en": "Velina",
        "character_name_cn": "维琳娜·艾嘉德",
        "source": "HoYoWiki official zzz zh-cn agent menu_id=8",
        "kind": "agent",
        "release_order": "0",
    },
    "ultra-jake": {
        "character_name_en": "Ultra Jake",
        "character_name_cn": "超极杰克",
        "source": "HoYoWiki official zzz zh-cn bangboo menu_id=15",
        "kind": "bangboo",
        "release_order": "1000",
    },
    "sprout": {
        "character_name_en": "Sprout",
        "character_name_cn": "芽芽",
        "source": "HoYoWiki official zzz zh-cn bangboo menu_id=15",
        "kind": "bangboo",
        "release_order": "1003",
    },
}


class ZzzHoYoWikiClient:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def fetch_entry_pages(self, menu_id: str, lang: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        total: int | None = None
        page = 1
        while total is None or len(rows) < total:
            payload = {"menu_id": menu_id, "page_num": page, "page_size": 50}
            request = urllib.request.Request(
                "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "User-Agent": "Mozilla/5.0 zzz-endgame-exporter/0.1",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": "https://wiki.hoyolab.com",
                    "Referer": f"https://wiki.hoyolab.com/m/zzz/aggregate/{menu_id}?lang={lang}",
                    "x-rpc-language": lang,
                    "x-rpc-wiki_app": HOYOWIKI_APP,
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
            if data.get("retcode") != 0:
                raise RuntimeError(f"HoYoWiki returned retcode {data.get('retcode')}: {data.get('message')}")
            page_rows = data.get("data", {}).get("list") or []
            total = int(data.get("data", {}).get("total") or 0)
            rows.extend(page_rows)
            if not page_rows:
                break
            page += 1
        return rows

    def fetch_agent_pages(self, lang: str) -> list[dict[str, Any]]:
        return self.fetch_entry_pages(HOYOWIKI_AGENT_MENU_ID, lang)

    def fetch_bangboo_pages(self, lang: str) -> list[dict[str, Any]]:
        return self.fetch_entry_pages(HOYOWIKI_BANGBOO_MENU_ID, lang)


def load_official_agents(raw_dir: Path, warnings: list[str]) -> list[dict[str, Any]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        zh_rows = _fetch_or_read(raw_dir / "zzz_agents_zh-cn.json", "zh-cn")
        en_rows = _fetch_or_read(raw_dir / "zzz_agents_en-us.json", "en-us")
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        warnings.append(f"HoYoWiki official zzz agent fetch failed: {exc}")
        return []
    zh_by_id = {str(row.get("entry_page_id")): row for row in zh_rows}
    zh_order = {str(row.get("entry_page_id")): index for index, row in enumerate(zh_rows)}
    output: list[dict[str, Any]] = []
    for index, en_row in enumerate(en_rows):
        entry_id = str(en_row.get("entry_page_id") or "")
        zh_row = zh_by_id.get(entry_id, {})
        en_name = _clean_name(en_row.get("name"))
        cn_name = _clean_name(zh_row.get("name"))
        if not en_name:
            continue
        output.append(
            {
                "character_slug": normalize_character_id(en_name),
                "character_name_en": en_name,
                "character_name_cn": cn_name,
                "element_en": _first_filter(en_row, "agent_stats"),
                "element_cn": _first_filter(zh_row, "agent_stats"),
                "style_en": _first_filter(en_row, "agent_specialties"),
                "style_cn": _first_filter(zh_row, "agent_specialties"),
                "faction_en": _first_filter(en_row, "agent_faction"),
                "faction_cn": _first_filter(zh_row, "agent_faction"),
                "rarity": _first_filter(en_row, "agent_rarity") or _first_filter(zh_row, "agent_rarity"),
                "icon_url": str(zh_row.get("icon_url") or en_row.get("icon_url") or ""),
                "source": HOYOWIKI_SOURCE,
                "kind": "agent",
                "release_order": zh_order.get(entry_id, index),
            }
        )
    return output


def load_official_bangboo(raw_dir: Path, warnings: list[str]) -> list[dict[str, Any]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        zh_rows = _fetch_or_read(raw_dir / "zzz_bangboo_zh-cn.json", "zh-cn", HOYOWIKI_BANGBOO_MENU_ID)
        en_rows = _fetch_or_read(raw_dir / "zzz_bangboo_en-us.json", "en-us", HOYOWIKI_BANGBOO_MENU_ID)
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        warnings.append(f"HoYoWiki official zzz bangboo fetch failed: {exc}")
        return []
    zh_by_id = {str(row.get("entry_page_id")): row for row in zh_rows}
    zh_order = {str(row.get("entry_page_id")): index for index, row in enumerate(zh_rows)}
    output: list[dict[str, Any]] = []
    for index, en_row in enumerate(en_rows):
        entry_id = str(en_row.get("entry_page_id") or "")
        zh_row = zh_by_id.get(entry_id, {})
        en_name = _clean_name(en_row.get("name"))
        cn_name = _clean_name(zh_row.get("name"))
        if not en_name:
            continue
        output.append(
            {
                "character_slug": normalize_character_id(en_name),
                "character_name_en": en_name,
                "character_name_cn": cn_name,
                "source": BANGBOO_SOURCE,
                "kind": "bangboo",
                "release_order": 1000 + zh_order.get(entry_id, index),
            }
        )
    return output


def official_name_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        slug = normalize_character_id(row.get("character_slug") or row.get("character_name_en"))
        if not slug:
            continue
        mapped = {
            "character_slug": slug,
            "character_name_en": str(row.get("character_name_en") or ""),
            "character_name_cn": str(row.get("character_name_cn") or ""),
            "source": str(row.get("source") or HOYOWIKI_SOURCE),
            "needs_manual_check": "0" if row.get("character_name_cn") else "1",
            "aliases": "",
            "kind": str(row.get("kind") or "agent"),
            "release_order": str(row.get("release_order", index)),
        }
        aliases = _aliases_for_row(slug, mapped["character_name_en"])
        mapped["aliases"] = ";".join(sorted(aliases))
        for alias in {slug, *aliases}:
            output.setdefault(alias, mapped)
    for slug, row in SUPPLEMENTAL_OFFICIAL_ZH.items():
        output.setdefault(
            slug,
            {
                "character_slug": slug,
                "character_name_en": row["character_name_en"],
                "character_name_cn": row["character_name_cn"],
                "source": row["source"],
                "needs_manual_check": "0",
                "aliases": "",
                "kind": row["kind"],
                "release_order": row["release_order"],
            },
        )
    return output


def _aliases_for_row(slug: str, en_name: str) -> set[str]:
    aliases = set(MANUAL_ALIASES.get(slug, []))
    normalized_name = normalize_character_id(en_name)
    if normalized_name:
        aliases.add(normalized_name)
    parts = [part for part in normalized_name.split("-") if part and part not in {"and", "de", "the"}]
    if len(parts) >= 2:
        aliases.add(parts[0])
        aliases.add(parts[-1])
    if "-" in en_name:
        dash_parts = [normalize_character_id(part) for part in en_name.split("-") if part.strip()]
        if len(dash_parts) == 2:
            aliases.add("-".join(reversed(dash_parts)))
    return {alias for alias in aliases if alias and alias != slug}


def _fetch_or_read(path: Path, lang: str, menu_id: str = HOYOWIKI_AGENT_MENU_ID) -> list[dict[str, Any]]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rows = ZzzHoYoWikiClient().fetch_entry_pages(menu_id, lang)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def _clean_name(value: Any) -> str:
    return str(value or "").replace("\xa0", " ").strip()


def _first_filter(row: dict[str, Any], key: str) -> str:
    values = ((row.get("filter_values") or {}).get(key) or {}).get("values") or []
    return str(values[0]) if values else ""
