from __future__ import annotations

import json
import re
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id, parse_date, parse_number, parse_percent

from .constants import MODE_CN


def make_phase_row(
    snapshot_id: str,
    mode: str,
    config: dict[str, Any],
    *,
    source_path: str,
    has_chars: bool = True,
    has_comps: bool = True,
    note: str = "",
) -> dict[str, Any] | None:
    mode_config = config.get(mode)
    if not isinstance(mode_config, dict):
        return None
    phase_ver = str(mode_config.get("ver") or snapshot_id)
    return {
        "snapshot_id": snapshot_id,
        "collect_date": parse_date(config.get("collect_date")),
        "mode": mode,
        "mode_cn": MODE_CN.get(mode, mode),
        "phase_ver": phase_ver,
        "phase_name": str(mode_config.get("name") or f"{MODE_CN.get(mode, mode)} {phase_ver}"),
        "start_date": parse_date(mode_config.get("start")),
        "end_date": parse_date(mode_config.get("end")),
        "source": "hf_processed",
        "source_path": source_path,
        "has_chars": 1 if has_chars else 0,
        "has_comps": 1 if has_comps else 0,
        "note": note,
    }


def parse_builds_character_rows(
    builds: list[dict[str, Any]],
    phase: dict[str, Any],
    *,
    source_file: str,
    source_url: str,
) -> list[dict[str, Any]]:
    mode = str(phase.get("mode") or "")
    rows: list[dict[str, Any]] = []
    for item in builds:
        slug = normalize_character_id(item.get("char"))
        if not slug:
            continue
        rows.append(_usage_row(item, phase, slug, "all", "全部", source_file, source_url))
        for index in range(1, 4):
            key = f"app_rate_{mode}_boss_{index}"
            if key in item:
                if mode == "sd":
                    sub_mode, sub_mode_cn = f"5-{index}", f"第5防线 {index}"
                else:
                    sub_mode, sub_mode_cn = f"1-{index}", f"首领 {index}"
                rows.append(
                    _usage_row(
                        item,
                        phase,
                        slug,
                        sub_mode,
                        sub_mode_cn,
                        source_file,
                        source_url,
                        boss_index=index,
                    )
                )
    return rows


def parse_bangboo_rows(
    rows: list[dict[str, Any]],
    phase: dict[str, Any],
    *,
    source_file: str,
    source_url: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in rows:
        slug = normalize_character_id(item.get("char"))
        if not slug:
            continue
        output.append(
            {
                **_base_phase_fields(phase),
                "sub_mode": "bangboo",
                "sub_mode_cn": "邦布",
                "character_slug": slug,
                "character_name_en": _slug_to_name(slug),
                "character_name_cn": "",
                "role": "bangboo",
                "rarity": item.get("rarity", ""),
                "app_rate": parse_percent(item.get("app_rate")),
                "avg_score": parse_number(item.get("avg_round")),
                "sample": "",
                "sample_players": "",
                "cons_avg": "",
                "char_level": "",
                "w_engine_level": "",
                "core_skill": "",
                "source_kind": "hf_bangboo",
                "source_file": source_file,
                "source_url": source_url,
                "quality_flag": "ok",
            }
        )
    return output


def parse_team_rows(
    teams: list[dict[str, Any]],
    phase: dict[str, Any],
    *,
    scope: str,
    source_kind: str,
    source_file: str,
    source_url: str,
) -> list[dict[str, Any]]:
    sub_mode, sub_mode_cn = scope_label(phase.get("mode", ""), scope)
    output: list[dict[str, Any]] = []
    for index, item in enumerate(teams, start=1):
        chars = [
            normalize_character_id(item.get("char_one") or item.get("char_1")),
            normalize_character_id(item.get("char_two") or item.get("char_2")),
            normalize_character_id(item.get("char_three") or item.get("char_3")),
        ]
        if any(not char or char == "-" for char in chars):
            continue
        output.append(
            {
                **_base_phase_fields(phase),
                "sub_mode": sub_mode,
                "sub_mode_cn": sub_mode_cn,
                "scope": scope,
                "rank": parse_number(item.get("rank")) or index,
                "char_1_slug": chars[0],
                "char_2_slug": chars[1],
                "char_3_slug": chars[2],
                "bangboo_slug": normalize_character_id(item.get("bangboo")),
                "char_1_name_cn": "",
                "char_2_name_cn": "",
                "char_3_name_cn": "",
                "bangboo_name_cn": "",
                "app_rate": parse_percent(item.get("app_rate")),
                "avg_score": parse_number(item.get("avg_round")),
                "avg_score_m1": parse_number(item.get("avg_round_m1")),
                "source_kind": source_kind,
                "source_file": source_file,
                "source_url": source_url,
                "raw_index": index,
                "raw_json": json.dumps(item, ensure_ascii=False, separators=(",", ":")),
            }
        )
    return output


def scope_label(mode: str, scope: str) -> tuple[str, str]:
    text = str(scope or "").replace("_combined.json", "").replace(".json", "")
    text = text.replace("top", "all").strip()
    normalized = re.sub(r"[^0-9a-zA-Z-]+", "-", text).strip("-").lower()
    if normalized in {"", "all"}:
        return "all", "全部"
    if mode == "sd" and normalized in {"1", "2", "3"}:
        return f"5-{normalized}", f"第5防线 {normalized}"
    if mode == "da" and normalized in {"1", "2", "3"}:
        return f"1-{normalized}", f"首领 {normalized}"
    if mode == "sd" and normalized.startswith("5-"):
        return normalized, normalized.replace("-", " / ")
    if mode == "da" and normalized.startswith("1-"):
        return normalized, normalized.replace("-", " / ")
    return normalized or "all", normalized or "全部"


def _usage_row(
    item: dict[str, Any],
    phase: dict[str, Any],
    slug: str,
    sub_mode: str,
    sub_mode_cn: str,
    source_file: str,
    source_url: str,
    *,
    boss_index: int | None = None,
) -> dict[str, Any]:
    mode = str(phase.get("mode") or "")
    suffix = f"_boss_{boss_index}" if boss_index else ""
    return {
        **_base_phase_fields(phase),
        "sub_mode": sub_mode,
        "sub_mode_cn": sub_mode_cn,
        "character_slug": slug,
        "character_name_en": _slug_to_name(slug),
        "character_name_cn": "",
        "role": "",
        "rarity": item.get("rarity", ""),
        "app_rate": parse_percent(item.get(f"app_rate_{mode}{suffix}") if boss_index else item.get(f"app_rate_{mode}")),
        "avg_score": parse_number(item.get(f"avg_round_{mode}{suffix}") if boss_index else item.get(f"avg_round_{mode}")),
        "sample": parse_number(item.get(f"sample_{mode}")),
        "sample_players": parse_number(item.get(f"sample_size_players_{mode}")),
        "cons_avg": parse_number(item.get("cons_avg")),
        "char_level": parse_number(item.get("char_level")),
        "w_engine_level": parse_number(item.get("w_engine_level")),
        "core_skill": parse_number(item.get("core_skill")),
        "source_kind": "hf_builds",
        "source_file": source_file,
        "source_url": source_url,
        "quality_flag": "ok",
    }


def _base_phase_fields(phase: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_id": phase.get("snapshot_id", ""),
        "collect_date": phase.get("collect_date", ""),
        "mode": phase.get("mode", ""),
        "mode_cn": phase.get("mode_cn", ""),
        "phase_ver": phase.get("phase_ver", ""),
        "phase_name": phase.get("phase_name", ""),
        "start_date": phase.get("start_date", ""),
        "end_date": phase.get("end_date", ""),
    }


def _slug_to_name(slug: str) -> str:
    return " ".join(part.capitalize() if not part.isdigit() else part for part in slug.split("-"))
