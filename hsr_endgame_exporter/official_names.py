from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .normalize import normalize_character_id

HOYOWIKI_CHARACTER_MENU_ID = "104"
HOYOWIKI_WIKI_APP = "hsr"
HOYOWIKI_SOURCE = "HoYoWiki official hsr character menu_id=104"

OFFICIAL_SLUG_ALIASES = {
    "blade-mortenax": "mortenax-blade",
    "himeko-nova": "himeko-nova",
    "imbibitor-lunae": "dan-heng-imbibitor-lunae",
    "march-7th-evernight": "evernight",
    "march-7th-swordmaster": "march-7th-the-hunt",
    "silver-wolf-lv-999": "silver-wolf-lv999",
    "tingyun-fugue": "fugue",
    "topaz": "topaz-and-numby",
    "trailblazer-destruction": "trailblazer-the-destruction",
    "trailblazer-harmony": "trailblazer-the-harmony",
    "trailblazer-preservation": "trailblazer-the-preservation",
    "trailblazer-remembrance": "trailblazer-remembrance",
}


class HoYoWikiClient:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def fetch_character_pages(self, lang: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        total: int | None = None
        page = 1
        while total is None or len(rows) < total:
            payload = {
                "menu_id": HOYOWIKI_CHARACTER_MENU_ID,
                "page_num": page,
                "page_size": 50,
            }
            request = urllib.request.Request(
                "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "User-Agent": "Mozilla/5.0 hsr-endgame-exporter/0.1",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": "https://wiki.hoyolab.com",
                    "Referer": f"https://wiki.hoyolab.com/pc/hsr/aggregate/character?lang={lang}",
                    "x-rpc-language": lang,
                    "x-rpc-wiki_app": HOYOWIKI_WIKI_APP,
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


def load_hoyowiki_official_names(
    raw_dir: Path,
    warnings: list[str],
) -> dict[str, dict[str, str]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        zh_rows = _fetch_or_read(raw_dir / "hsr_characters_zh-cn.json", "zh-cn")
        en_rows = _fetch_or_read(raw_dir / "hsr_characters_en-us.json", "en-us")
    except (OSError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        warnings.append(f"HoYoWiki official name fetch failed: {exc}")
        return {}

    zh_by_id = {str(row.get("entry_page_id")): row for row in zh_rows}
    en_by_id = {str(row.get("entry_page_id")): row for row in en_rows}
    official: dict[str, dict[str, str]] = {}
    for entry_id, en_row in en_by_id.items():
        zh_row = zh_by_id.get(entry_id)
        if not zh_row:
            continue
        en_name = _clean_name(en_row.get("name"))
        cn_name = _clean_name(zh_row.get("name"))
        if not en_name or not cn_name:
            continue
        slug = normalize_character_id(en_name)
        official[slug] = {
            "character_slug": slug,
            "character_name_en": en_name,
            "character_name_cn": cn_name,
            "source": HOYOWIKI_SOURCE,
            "needs_manual_check": "0",
            "aliases": "",
        }
    for alias, target in OFFICIAL_SLUG_ALIASES.items():
        if target in official:
            row = dict(official[target])
            row["character_slug"] = alias
            row["aliases"] = target
            official[alias] = row
    return official


def _fetch_or_read(path: Path, lang: str) -> list[dict[str, Any]]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rows = HoYoWikiClient().fetch_character_pages(lang)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def _clean_name(value: Any) -> str:
    return str(value or "").replace("\xa0", " ").strip()

