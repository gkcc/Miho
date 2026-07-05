from __future__ import annotations

import html
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

from .constants import PRYDWEN_PAGE_URLS


class PrydwenScraper:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def fetch_html(self, mode: str) -> tuple[str, str]:
        url = PRYDWEN_PAGE_URLS[mode]
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
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", "replace"), url

    def scrape_teams(
        self,
        mode: str,
        *,
        raw_dir: Path | None = None,
    ) -> tuple[dict[str, list[dict[str, Any]]], str, str]:
        text, url = self.fetch_html(mode)
        source_file = url
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            path = raw_dir / f"{mode}.html"
            path.write_text(text, encoding="utf-8")
            source_file = str(path)
        return extract_teams_from_html(text), source_file, url


def extract_teams_from_html(text: str) -> dict[str, list[dict[str, Any]]]:
    teams: dict[str, list[dict[str, Any]]] = {}
    next_data = _extract_next_data(text)
    if next_data is not None:
        _collect_team_lists(next_data, teams)
    for candidate_text in _decoded_text_variants(text):
        for value in _json_values_after_key(candidate_text, "teams"):
            if isinstance(value, dict):
                for key, rows in value.items():
                    if _looks_like_team_list(rows):
                        teams.setdefault(str(key), []).extend(rows)
            elif _looks_like_team_list(value):
                teams.setdefault("all", []).extend(value)
    return teams


def _extract_next_data(text: str) -> Any | None:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        text,
        flags=re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None


def _collect_team_lists(value: Any, output: dict[str, list[dict[str, Any]]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "teams" and isinstance(child, dict):
                for scope, rows in child.items():
                    if _looks_like_team_list(rows):
                        output.setdefault(str(scope), []).extend(rows)
            elif _looks_like_team_list(child):
                output.setdefault(str(key), []).extend(child)
            else:
                _collect_team_lists(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_team_lists(child, output)


def _decoded_text_variants(text: str) -> list[str]:
    variants = [html.unescape(text)]
    try:
        variants.append(variants[0].encode("utf-8").decode("unicode_escape"))
    except UnicodeDecodeError:
        pass
    return variants


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
    if not isinstance(value, list) or not value:
        return False
    sample = value[0]
    return isinstance(sample, dict) and (
        {"char_one", "char_two", "char_three", "char_four"}.issubset(sample)
        or {"char_1", "char_2", "char_3", "char_4"}.issubset(sample)
    )

