from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any

from .constants import MODE_CN
from .normalize import (
    character_slug_to_english,
    make_ordered_signature,
    make_unordered_signature,
    normalize_character_id,
    parse_number,
    parse_percent,
    parse_scope,
)


def make_phase_row(
    *,
    snapshot_id: str,
    config_entry: dict[str, Any] | None,
    mode: str,
    source_path: str,
    has_chars: bool,
    has_comps: bool,
    has_histograph: bool,
    collect_date: str,
    note: str = "",
) -> dict[str, Any]:
    mode_config = (config_entry or {}).get(mode) if config_entry else None
    mode_config = mode_config or {}
    return {
        "snapshot_id": snapshot_id,
        "collect_date": collect_date,
        "mode": mode,
        "mode_cn": MODE_CN.get(mode, mode),
        "phase_ver": mode_config.get("ver") or snapshot_id,
        "phase_name": mode_config.get("name") or "",
        "start_date": mode_config.get("start_iso") or "",
        "end_date": mode_config.get("end_iso") or "",
        "source": "huggingface",
        "source_path": source_path,
        "has_chars": int(has_chars),
        "has_comps": int(has_comps),
        "has_histograph": int(has_histograph),
        "note": note,
    }


def parse_builds_character_rows(
    *,
    snapshot_id: str,
    phase_row: dict[str, Any],
    builds: list[dict[str, Any]],
    source_file: str,
    source_url: str,
) -> list[dict[str, Any]]:
    mode = phase_row["mode"]
    rows: list[dict[str, Any]] = []
    for item in builds:
        slug = normalize_character_id(item.get("char"))
        if not slug:
            continue
        app_rate = parse_percent(item.get(f"app_rate_{mode}"))
        if app_rate is None:
            continue
        quality_flag = "aa_all_bosses_only" if mode == "aa" else "ok"
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "collect_date": phase_row["collect_date"],
                "mode": mode,
                "mode_cn": phase_row["mode_cn"],
                "sub_mode": "all_bosses" if mode == "aa" else "all",
                "sub_mode_cn": "全 Boss / 未拆分" if mode == "aa" else "全部",
                "phase_ver": phase_row["phase_ver"],
                "phase_name": phase_row["phase_name"],
                "start_date": phase_row["start_date"],
                "end_date": phase_row["end_date"],
                "character_slug": slug,
                "character_name_en": item.get("name") or character_slug_to_english(slug),
                "character_name_cn": "",
                "role": item.get("role") or item.get("special_role") or "",
                "rarity": item.get("rarity") or "",
                "app_rate": app_rate,
                "app_rate_e0": parse_percent(item.get(f"app_rate_{mode}_e0s1")),
                "avg_round": parse_number(item.get(f"avg_round_{mode}")),
                "std_dev_round": parse_number(item.get("std_dev_round")),
                "q1_round": parse_number(item.get("q1_round")),
                "cons_avg": parse_number(item.get("cons_avg")),
                "sample": parse_number(item.get(f"sample_{mode}")),
                "sample_app_flat": parse_number(item.get(f"sample_size_players_{mode}")),
                "source_kind": "hf_chars",
                "source_file": source_file,
                "source_url": source_url,
                "quality_flag": quality_flag,
            }
        )
    return rows


def parse_chars_file_character_rows(
    *,
    snapshot_id: str,
    phase_row: dict[str, Any],
    data: Any,
    source_file: str,
    source_url: str,
) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    mode = phase_row["mode"]
    rows: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        slug = normalize_character_id(item.get("char") or item.get("character"))
        if not slug:
            continue
        app_rate = parse_percent(
            item.get("app_rate")
            if "app_rate" in item
            else item.get("app")
        )
        if app_rate is None:
            continue
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "collect_date": phase_row["collect_date"],
                "mode": mode,
                "mode_cn": phase_row["mode_cn"],
                "sub_mode": "all_bosses" if mode == "aa" else "all",
                "sub_mode_cn": "全 Boss / 未拆分" if mode == "aa" else "全部",
                "phase_ver": phase_row["phase_ver"],
                "phase_name": phase_row["phase_name"],
                "start_date": phase_row["start_date"],
                "end_date": phase_row["end_date"],
                "character_slug": slug,
                "character_name_en": item.get("name") or character_slug_to_english(slug),
                "character_name_cn": "",
                "role": item.get("role") or "",
                "rarity": item.get("rarity") or "",
                "app_rate": app_rate,
                "app_rate_e0": parse_percent(item.get("app_rate_e0") or item.get("app_rate_e1")),
                "avg_round": parse_number(item.get("avg_round")),
                "std_dev_round": parse_number(item.get("std_dev_round")),
                "q1_round": parse_number(item.get("q1_round")),
                "cons_avg": parse_number(item.get("cons_avg")),
                "sample": parse_number(item.get("sample")),
                "sample_app_flat": parse_number(item.get("sample_app_flat") or item.get("app_flat")),
                "source_kind": "hf_chars",
                "source_file": source_file,
                "source_url": source_url,
                "quality_flag": "aa_all_bosses_only" if mode == "aa" else "ok",
            }
        )
    return rows


def parse_histograph_rows(
    *,
    snapshot_id: str,
    phase_rows: dict[str, dict[str, Any]],
    histograph: list[dict[str, Any]],
    source_file: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in histograph:
        if not isinstance(item, dict):
            continue
        slug = normalize_character_id(item.get("char"))
        if not slug:
            continue
        for mode, phase_row in phase_rows.items():
            usage_value = parse_percent(item.get(f"{mode}_usage"))
            if usage_value is None:
                continue
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "collect_date": phase_row["collect_date"],
                    "mode": mode,
                    "mode_cn": phase_row["mode_cn"],
                    "character_slug": slug,
                    "character_name_en": item.get("name") or character_slug_to_english(slug),
                    "character_name_cn": "",
                    "usage_value": usage_value,
                    "source_file": source_file,
                    "note": "trend auxiliary; not a full character usage table",
                }
            )
    return rows


def histograph_fallback_character_rows(
    histograph_rows: list[dict[str, Any]],
    phase_rows: dict[str, dict[str, Any]],
    modes_without_char_rows: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in histograph_rows:
        mode = item["mode"]
        if mode not in modes_without_char_rows:
            continue
        phase_row = phase_rows[mode]
        rows.append(
            {
                "snapshot_id": item["snapshot_id"],
                "collect_date": item["collect_date"],
                "mode": mode,
                "mode_cn": item["mode_cn"],
                "sub_mode": "all_bosses" if mode == "aa" else "all",
                "sub_mode_cn": "全 Boss / 未拆分" if mode == "aa" else "全部",
                "phase_ver": phase_row["phase_ver"],
                "phase_name": phase_row["phase_name"],
                "start_date": phase_row["start_date"],
                "end_date": phase_row["end_date"],
                "character_slug": item["character_slug"],
                "character_name_en": item["character_name_en"],
                "character_name_cn": "",
                "role": "",
                "rarity": "",
                "app_rate": item["usage_value"],
                "app_rate_e0": None,
                "avg_round": None,
                "std_dev_round": None,
                "q1_round": None,
                "cons_avg": None,
                "sample": None,
                "sample_app_flat": None,
                "source_kind": "hf_histograph_fallback",
                "source_file": item["source_file"],
                "source_url": "",
                "quality_flag": "histograph_fallback",
            }
        )
    return rows


def parse_team_rows(
    *,
    snapshot_id: str,
    phase_row: dict[str, Any],
    data: Any,
    source_kind: str,
    source_file: str,
    source_url: str,
    scope_hint: str,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    mode = phase_row["mode"]
    sub_mode, sub_mode_cn = parse_scope(mode, scope_hint)
    scope = _scope_from_source(scope_hint)
    rows: list[dict[str, Any]] = []
    for raw_index, item in enumerate(data, start=1):
        if top_n is not None and raw_index > top_n:
            break
        if not isinstance(item, dict):
            continue
        chars = [
            item.get("char_one") or item.get("char_1"),
            item.get("char_two") or item.get("char_2"),
            item.get("char_three") or item.get("char_3"),
            item.get("char_four") or item.get("char_4"),
        ]
        slugs = [normalize_character_id(char) for char in chars]
        if any(not slug for slug in slugs):
            continue
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "collect_date": phase_row["collect_date"],
                "mode": mode,
                "mode_cn": phase_row["mode_cn"],
                "sub_mode": sub_mode,
                "sub_mode_cn": sub_mode_cn,
                "phase_ver": phase_row["phase_ver"],
                "phase_name": phase_row["phase_name"],
                "scope": scope,
                "rank": parse_number(item.get("rank")),
                "comp_name": item.get("comp_name") or "",
                "char_1_slug": slugs[0],
                "char_2_slug": slugs[1],
                "char_3_slug": slugs[2],
                "char_4_slug": slugs[3],
                "char_1_name_cn": "",
                "char_2_name_cn": "",
                "char_3_name_cn": "",
                "char_4_name_cn": "",
                "app_rate": parse_percent(item.get("app_rate")),
                "avg_round": parse_number(item.get("avg_round")),
                "whale_count": parse_number(item.get("whale_count")),
                "app_flat": parse_number(item.get("app_flat")),
                "uses": parse_number(item.get("uses")),
                "source_kind": source_kind,
                "source_file": source_file,
                "source_url": source_url,
                "raw_index": raw_index,
                "raw_json": json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            }
        )
    return rows


def attach_team_signatures(row: dict[str, Any]) -> tuple[str, str]:
    chars = [row[f"char_{i}_slug"] for i in range(1, 5)]
    identity = (
        row["snapshot_id"],
        row["collect_date"],
        row["mode"],
        row["sub_mode"],
        row["scope"],
        row["phase_ver"],
        row["phase_name"],
    )
    ordered = make_ordered_signature(*identity, chars)
    unordered = make_unordered_signature(*identity, chars)
    return ordered, unordered


def _scope_from_source(source_name: str | None) -> str:
    name = PurePosixPath(source_name or "").name
    name = re.sub(r"\.json$", "", name)
    name = re.sub(r"_combined$", "", name)
    return name or "all"
