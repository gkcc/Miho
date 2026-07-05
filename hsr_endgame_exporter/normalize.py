from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

from .constants import SUB_MODE_CN

_ALIAS_MAP = {
    "topaz-numby": "topaz-and-numby",
    "topaz-and-numby": "topaz-and-numby",
    "dan-heng-imbibitor-lunae": "dan-heng-imbibitor-lunae",
    "march-7th": "march-7th",
}


def normalize_character_id(value: str | None) -> str:
    """Normalize a character display name or slug into a stable slug."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = text.replace("+", " plus ")
    text = text.replace("•", " ")
    text = re.sub(r"[.'’`]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return _ALIAS_MAP.get(text, text)


def character_slug_to_english(slug: str | None) -> str:
    slug = normalize_character_id(slug)
    if not slug:
        return ""
    small_words = {"and", "of", "the"}
    parts = []
    for part in slug.split("-"):
        if part in small_words:
            parts.append(part)
        elif part.isdigit():
            parts.append(part)
        else:
            parts.append(part.capitalize())
    return " ".join(parts)


def parse_percent(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in {"", "-"}:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def parse_number(value) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text in {"", "-"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def parse_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def date_or_none(value: str | None) -> date | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    try:
        return date.fromisoformat(parsed)
    except ValueError:
        return None


def parse_aa_scope(value: str | None) -> tuple[str, str]:
    text = normalize_character_id(value or "")
    original = str(value or "").lower()
    if "骑士" in original or "knights" in text or "knight" in text:
        return "knights", SUB_MODE_CN["knights"]
    if "王棋" in original or "king" in text or "boss" in text:
        return "king_piece", SUB_MODE_CN["king_piece"]
    if "all-bosses" in text or text == "all" or text == "all-bosses":
        return "all_bosses", SUB_MODE_CN["all_bosses"]
    return "all_bosses", SUB_MODE_CN["all_bosses"]


def parse_scope(mode: str, source_name: str | None) -> tuple[str, str]:
    if mode == "aa":
        return parse_aa_scope(source_name)
    base_name = str(source_name or "").replace("\\", "/").split("/")[-1]
    base_name = re.sub(r"\.json$", "", base_name)
    base_name = re.sub(r"_combined$", "", base_name)
    name = normalize_character_id(base_name)
    if not name or name == "top":
        return "all", SUB_MODE_CN["all"]
    return f"stage_{name.replace('-', '_')}", name.replace("-", "-")


def make_ordered_signature(
    mode: str,
    sub_mode: str,
    phase_ver: str,
    chars: Iterable[str],
) -> str:
    char_part = ">".join(normalize_character_id(char) for char in chars)
    return f"{mode}|{sub_mode}|{phase_ver}|{char_part}"


def make_unordered_signature(
    mode: str,
    sub_mode: str,
    phase_ver: str,
    chars: Iterable[str],
) -> str:
    normalized = sorted(normalize_character_id(char) for char in chars)
    return f"{mode}|{sub_mode}|{phase_ver}|{'>'.join(normalized)}"
