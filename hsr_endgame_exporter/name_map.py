from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from .constants import NAME_MAP_COLUMNS
from .normalize import character_slug_to_english, normalize_character_id


class NameMapBuilder:
    def __init__(self) -> None:
        self._seed: dict[str, dict[str, str]] = {}
        self._official: dict[str, dict[str, str]] = {}
        self._candidates: dict[str, dict[str, str]] = {}

    def load_seed(self, path: str | None, warnings: list[str]) -> None:
        if not path:
            return
        seed_path = Path(path)
        if not seed_path.exists():
            warnings.append(f"name map seed not found: {seed_path}")
            return
        with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                slug = normalize_character_id(
                    row.get("character_slug")
                    or row.get("slug")
                    or row.get("character_name_en")
                    or row.get("name_en")
                )
                if not slug:
                    continue
                aliases = row.get("aliases") or ""
                self._seed[slug] = {
                    "character_slug": slug,
                    "character_name_en": row.get("character_name_en")
                    or row.get("name_en")
                    or character_slug_to_english(slug),
                    "character_name_cn": row.get("character_name_cn")
                    or row.get("name_cn")
                    or row.get("cn")
                    or "",
                    "source": row.get("source") or "seed",
                    "needs_manual_check": "0",
                    "aliases": aliases,
                }
                for alias in re.split(r"[;,|]", aliases):
                    alias_slug = normalize_character_id(alias)
                    if alias_slug:
                        self._seed[alias_slug] = self._seed[slug]

    def load_official(self, rows_by_slug: dict[str, dict[str, str]]) -> None:
        for slug, row in rows_by_slug.items():
            normalized = normalize_character_id(slug)
            if not normalized:
                continue
            official_row = dict(row)
            official_row["character_slug"] = normalized
            official_row["needs_manual_check"] = "0"
            self._official[normalized] = official_row

    def add_candidate(self, slug: str | None, english_name: str | None = "", source: str = "source") -> None:
        slug = normalize_character_id(slug)
        if not slug:
            return
        current = self._candidates.setdefault(
            slug,
            {
                "character_slug": slug,
                "character_name_en": "",
                "source": source,
            },
        )
        if english_name and not current["character_name_en"]:
            current["character_name_en"] = english_name

    def build_rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        for slug in sorted(self._candidates):
            if slug in self._seed and self._seed[slug].get("character_name_cn"):
                seed_row = dict(self._seed[slug])
                seed_row["character_slug"] = slug
                if not seed_row.get("character_name_en"):
                    seed_row["character_name_en"] = (
                        self._candidates[slug].get("character_name_en")
                        or character_slug_to_english(slug)
                    )
                rows.append(_fill_row(seed_row))
            elif slug in self._official and self._official[slug].get("character_name_cn"):
                official_row = dict(self._official[slug])
                official_row["character_slug"] = slug
                if not official_row.get("character_name_en"):
                    official_row["character_name_en"] = (
                        self._candidates[slug].get("character_name_en")
                        or character_slug_to_english(slug)
                    )
                rows.append(_fill_row(official_row))
            else:
                candidate = self._candidates[slug]
                rows.append(
                    _fill_row(
                        {
                            "character_slug": slug,
                            "character_name_en": candidate.get("character_name_en")
                            or character_slug_to_english(slug),
                            "character_name_cn": "",
                            "source": candidate.get("source") or "source",
                            "needs_manual_check": "1",
                            "aliases": "",
                        }
                    )
                )
        unresolved = [row for row in rows if str(row["needs_manual_check"]) == "1"]
        return rows, unresolved

    def chinese_name(self, slug: str | None) -> str:
        slug = normalize_character_id(slug)
        row = self._seed.get(slug)
        if row and row.get("character_name_cn"):
            return row["character_name_cn"]
        row = self._official.get(slug)
        return row.get("character_name_cn", "") if row else ""

    def english_name(self, slug: str | None) -> str:
        slug = normalize_character_id(slug)
        if not slug:
            return ""
        seed = self._seed.get(slug)
        if seed and seed.get("character_name_en"):
            return seed["character_name_en"]
        official = self._official.get(slug)
        if official and official.get("character_name_en"):
            return official["character_name_en"]
        candidate = self._candidates.get(slug)
        if candidate and candidate.get("character_name_en"):
            return candidate["character_name_en"]
        return character_slug_to_english(slug)


def collect_names(builder: NameMapBuilder, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if "character_slug" in row:
            builder.add_candidate(
                row.get("character_slug"),
                row.get("character_name_en"),
                row.get("source_kind") or row.get("source_file") or "source",
            )
        for index in range(1, 5):
            key = f"char_{index}_slug"
            if key in row:
                builder.add_candidate(row.get(key), "", row.get("source_kind") or "team")


def enrich_character_rows(builder: NameMapBuilder, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        slug = row.get("character_slug")
        row["character_name_en"] = builder.english_name(slug) or row.get("character_name_en") or ""
        row["character_name_cn"] = builder.chinese_name(slug)


def enrich_team_rows(builder: NameMapBuilder, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        for index in range(1, 5):
            slug = row.get(f"char_{index}_slug")
            row[f"char_{index}_name_cn"] = builder.chinese_name(slug)


def _fill_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row.get(column, "") for column in NAME_MAP_COLUMNS}
