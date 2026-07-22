from __future__ import annotations

import csv
import io
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id

from miho_core.banner_plan import effective_banner_phases
from miho_core.visualizer_data import compact_visualizer_data

from .constants import ELEMENT_CN, MODE_CN, ROLE_ORDER, STYLE_CN
from .prydwen import extract_phase_updates_from_html


def _decoded_url_path(value: str) -> str:
    decoded = value
    for _ in range(3):
        next_value = urllib.parse.unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def _safe_same_origin_relative_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "\\" in text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        return ""
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme or parsed.netloc or text.startswith("/"):
        return ""
    decoded_path = _decoded_url_path(parsed.path)
    if "\\" in decoded_path:
        return ""
    segments = decoded_path.split("/")
    for index, segment in enumerate(segments):
        if segment == ".." or (segment == "." and not (index == 0 and text.startswith("./"))):
            return ""
        if "/" in segment or "\\" in segment:
            return ""
    if not decoded_path or decoded_path in {".", "/"}:
        return ""
    return text


def _safe_http_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or "\\" in text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        return ""
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or any(char.isspace() for char in parsed.netloc)
    ):
        return ""
    return text


def _safe_link_url(value: Any) -> str:
    return _safe_http_url(value) or _safe_same_origin_relative_url(value)


def _sanitize_output_urls(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {item_key: _sanitize_output_urls(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_output_urls(item, key=key) for item in value]
    if key == "icon_url":
        return _safe_same_origin_relative_url(value)
    if key == "url" or key.endswith("_url"):
        return _safe_link_url(value)
    return value


def write_visualizer_app(
    out_dir: Path,
    *,
    usage_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
    changelog_rows: list[dict[str, Any]],
) -> None:
    visualizer_dir = out_dir / "visualizer"
    visualizer_dir.mkdir(parents=True, exist_ok=True)
    roster_rows = _build_roster(out_dir, usage_rows, tier_rows, name_rows)
    roster_rows = _localize_avatar_rows(visualizer_dir, roster_rows)
    phase_info_rows = _build_phase_info_rows(out_dir)
    banner_rows = _load_banner_rows(out_dir, roster_rows)
    banner_rows = _localize_avatar_rows(visualizer_dir, banner_rows)
    roster_rows = _merge_banner_rows_into_roster(roster_rows, banner_rows)
    team_templates = _build_team_templates(team_rows, roster_rows, name_rows, phase_info_rows)
    decision_cards = _load_decision_cards(out_dir)
    data_quality = _read_data_quality(out_dir)
    data = {
        "meta": {
            "game": "绝区零",
            "generatedAt": _latest(tier_rows, "fetched_at"),
            "tierUpdatedAt": _latest(tier_rows, "tier_updated_at"),
            "localDate": date.today().isoformat(),
            "source": "ShiyuDataProcessed + Prydwen ZZZ + HoYoWiki",
        },
        "usageRows": usage_rows,
        "tierRows": tier_rows,
        "teamTemplates": team_templates,
        "rosterRows": roster_rows,
        "nameRows": name_rows,
        "phaseInfoRows": phase_info_rows,
        "changelogRows": changelog_rows[:80],
        "bannerRows": banner_rows,
        "decisionMethodVersion": "legacy-v0",
        "decisionCards": decision_cards,
        "data_quality": data_quality,
        "freshness": _data_quality_freshness(data_quality),
    }
    data = _sanitize_output_urls(data)
    # Keep the original top-level wire shape for one compatibility cycle;
    # current runtimes load the smaller columnar v2 asset first.
    legacy_data = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    compact_data = json.dumps(
        compact_visualizer_data(data),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    (visualizer_dir / "data.json").write_text(legacy_data, encoding="utf-8")
    (visualizer_dir / "data.v2.json").write_text(compact_data, encoding="utf-8")
    (visualizer_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (visualizer_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (visualizer_dir / "app.js").write_text(APP_JS, encoding="utf-8")
    (visualizer_dir / "solver.js").write_text(SOLVER_JS, encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _build_phase_info_rows(out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prydwen_updates = _load_prydwen_phase_updates(out_dir)
    overrides = _load_phase_overrides(out_dir)
    for row in read_csv(out_dir / "phase_index.csv"):
        mode = str(row.get("mode") or "")
        mode_cn = str(row.get("mode_cn") or MODE_CN.get(mode, mode))
        phase_ver = str(row.get("phase_ver") or "")
        prydwen_update = prydwen_updates.get((mode, phase_ver), {})
        override = overrides.get((mode, phase_ver), {})
        collect_date = str(row.get("collect_date") or override.get("collect_date") or prydwen_update.get("collect_date") or "")
        start = str(row.get("start_date") or override.get("start_date") or "")
        end = str(row.get("end_date") or override.get("end_date") or "")
        source_limited = bool((not row.get("collect_date")) and prydwen_update.get("collect_date"))
        if source_limited and not (start or end):
            mechanic_text = (
                f"采样日期 {collect_date} 来自 Prydwen 可见 phase；"
                "Hugging Face config 尚未写入本周期起止日期。推荐只使用同模式、同关卡的当前最新队伍模板，周期边界按源限制处理。"
            )
            mechanic_source = "Prydwen phase selector + ShiyuDataProcessed"
        elif override:
            mechanic_text = (
                f"采样日期 {collect_date or '未知'}；周期 {start or '未知'} 至 {end or '未知'}。"
                "起止来自手动联网 override，用于弥补上游 config 缺失。"
            )
            mechanic_source = override.get("source_label") or "manual online override"
        else:
            mechanic_text = (
                f"采样日期 {collect_date or '未知'}；周期 {start or '未知'} 至 {end or '未知'}。"
                "推荐只使用同模式、同关卡的当前最新队伍模板。"
            )
            mechanic_source = "ShiyuDataProcessed config.json"
        rows.append(
            {
                "snapshot_id": row.get("snapshot_id", ""),
                "collect_date": collect_date,
                "mode": mode,
                "mode_cn": mode_cn,
                "phase_ver": phase_ver,
                "phase_name": row.get("phase_name", "") or f"{mode_cn} {phase_ver}".strip(),
                "phase_name_cn": row.get("phase_name", "") or f"{mode_cn} {phase_ver}".strip(),
                "start_date": start,
                "end_date": end,
                "mechanic_name": "当期数据",
                "mechanic_text": mechanic_text,
                "mechanic_source": mechanic_source,
                "mechanic_url": override.get("source_url", ""),
                "phase_status": _phase_status({"start_date": start, "end_date": end}),
                "source_limited": source_limited,
                "source_note": override.get("note") or row.get("note", ""),
            }
        )
    return rows


def _phase_status(row: dict[str, Any], *, today: date | None = None) -> str:
    current = today or date.today()
    start = _date_or_none(row.get("start_date"))
    end = _date_or_none(row.get("end_date"))
    if end and end < current:
        return "expired"
    if start and start > current:
        return "future"
    if start or end:
        return "current"
    return "unknown"


def _date_or_none(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _load_prydwen_phase_updates(out_dir: Path) -> dict[tuple[str, str], dict[str, str]]:
    updates: dict[tuple[str, str], dict[str, str]] = {}
    for mode in MODE_CN:
        page = out_dir / "raw" / "prydwen" / f"{mode}.html"
        if not page.exists():
            continue
        try:
            mode_updates = extract_phase_updates_from_html(page.read_text(encoding="utf-8"))
        except OSError:
            continue
        for phase_ver, row in mode_updates.items():
            updates[(mode, phase_ver)] = row
    return updates


def _load_phase_overrides(out_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    for path in (
        out_dir / "zzz_endgame_phase_overrides.json",
        out_dir.parent / "configs" / "zzz_endgame_phase_overrides.json",
        Path("configs") / "zzz_endgame_phase_overrides.json",
    ):
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = value.get("phases") if isinstance(value, dict) else value
        if not isinstance(rows, list):
            continue
        return {
            (str(row.get("mode") or ""), str(row.get("phase_ver") or "")): row
            for row in rows
            if isinstance(row, dict) and row.get("mode") and row.get("phase_ver")
        }
    return {}


def _load_banner_rows(out_dir: Path, roster_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = _read_json_first(
        [
            out_dir / "zzz_banner_plan.json",
            out_dir.parent / "configs" / "zzz_banner_plan.json",
            Path("configs") / "zzz_banner_plan.json",
        ]
    )
    if not config:
        return []
    roster = {row["character_slug"]: row for row in roster_rows}
    rows: list[dict[str, Any]] = []
    for phase in effective_banner_phases(config):
        for index, char in enumerate(phase.get("characters") or [], start=1):
            if not isinstance(char, dict):
                continue
            slug = normalize_character_id(char.get("slug"))
            if not slug:
                continue
            info = roster.get(slug, {})
            rows.append(
                {
                    "phase_id": phase.get("id", ""),
                    "phase_status": phase.get("status", ""),
                    "declared_phase_status": phase.get("declared_status", ""),
                    "phase_title": phase.get("title", ""),
                    "phase_subtitle": phase.get("subtitle", ""),
                    "date_range": phase.get("date_range", ""),
                    "source_label": char.get("source_label") or phase.get("source_label", ""),
                    "source_url": char.get("source_url") or phase.get("source_url", ""),
                    "slot": index,
                    "character_slug": slug,
                    "character_name_cn": char.get("name_cn") or info.get("character_name_cn") or "",
                    "character_name_en": char.get("name_en") or info.get("character_name_en") or "",
                    "banner_role": char.get("banner_role", ""),
                    "rarity": char.get("rarity") or info.get("rarity") or "",
                    "element_cn": char.get("element_cn") or info.get("element_cn") or "",
                    "style_cn": char.get("style_cn") or info.get("style_cn") or "",
                    "role_group_cn": char.get("role_group_cn") or info.get("role_group_cn") or "",
                    "icon_url": char.get("icon_url") or info.get("icon_url") or "",
                    "icon_crop": char.get("icon_crop") or char.get("avatar_crop") or "",
                    "icon_source_label": char.get("icon_source_label") or "",
                    "icon_source_url": char.get("icon_source_url") or "",
                    "analysis_tags": char.get("analysis_tags") or [],
                    "focus": char.get("focus", ""),
                }
            )
    return rows


def _merge_banner_rows_into_roster(roster_rows: list[dict[str, Any]], banner_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    original_slugs = {str(row.get("character_slug") or "") for row in roster_rows}
    by_slug = {str(row.get("character_slug") or ""): dict(row) for row in roster_rows}
    banner_only_slugs: list[str] = []
    next_order = max((_release_order_value(row.get("release_order")) for row in roster_rows), default=0) + 1
    for banner_row in banner_rows:
        slug = normalize_character_id(banner_row.get("character_slug"))
        if not slug:
            continue
        phase_status = str(banner_row.get("phase_status") or "")
        phase_title = str(banner_row.get("phase_title") or "")
        existing = by_slug.get(slug)
        if existing is None:
            role_group = str(banner_row.get("role_group") or "") or _role_from_style_cn(str(banner_row.get("style_cn") or ""))
            by_slug[slug] = {
                "character_slug": slug,
                "character_name_en": banner_row.get("character_name_en") or slug,
                "character_name_cn": banner_row.get("character_name_cn") or "",
                "element_en": banner_row.get("element_en") or "",
                "element_cn": banner_row.get("element_cn") or "",
                "style_en": banner_row.get("style_en") or "",
                "style_cn": banner_row.get("style_cn") or "",
                "role_group": role_group,
                "role_group_cn": banner_row.get("role_group_cn") or _role_cn(role_group),
                "rarity": banner_row.get("rarity") or "",
                "tier": "未分档",
                "rating": "",
                "tags": ";".join(str(item) for item in banner_row.get("analysis_tags") or []),
                "icon_url": banner_row.get("icon_url") or "",
                "release_order": next_order,
                "source": "banner_plan",
                "banner_statuses": phase_status,
                "banner_phase_titles": phase_title,
            }
            banner_only_slugs.append(slug)
            next_order += 1
            continue
        existing["banner_statuses"] = _merge_semicolon(existing.get("banner_statuses"), phase_status)
        existing["banner_phase_titles"] = _merge_semicolon(existing.get("banner_phase_titles"), phase_title)
        for key in (
            "character_name_en",
            "character_name_cn",
            "element_en",
            "element_cn",
            "style_en",
            "style_cn",
            "role_group",
            "role_group_cn",
            "rarity",
            "icon_url",
        ):
            if not existing.get(key) and banner_row.get(key):
                existing[key] = banner_row[key]
        if not existing.get("role_group") and existing.get("style_cn"):
            role_group = _role_from_style_cn(str(existing.get("style_cn") or ""))
            existing["role_group"] = role_group
            existing["role_group_cn"] = existing.get("role_group_cn") or _role_cn(role_group)
        by_slug[slug] = existing

    published = sorted(
        (row for slug, row in by_slug.items() if slug in original_slugs),
        key=lambda row: (_release_order_value(row.get("release_order")), str(row.get("character_slug"))),
    )
    banner_only = [by_slug[slug] for slug in banner_only_slugs]
    future = [row for row in banner_only if _has_banner_status(row, "next") or _has_banner_status(row, "satellite")]
    current = [row for row in banner_only if row not in future and _has_banner_status(row, "current")]
    undated_history = [row for row in banner_only if row not in future and row not in current]
    ordered = future + current + published + undated_history
    for release_order, row in enumerate(ordered):
        row["release_order"] = release_order
    return ordered


def _has_banner_status(row: dict[str, Any], expected: str) -> bool:
    return expected in {status for status in str(row.get("banner_statuses") or "").split(";") if status}


def _merge_semicolon(existing: Any, value: Any) -> str:
    values = [item for item in str(existing or "").split(";") if item]
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)
    return ";".join(values)


def _load_decision_cards(out_dir: Path) -> dict[str, Any]:
    return _read_json_first([out_dir / "decision_cards.json"]) or {"summary": {}, "cards": []}


def _read_json_first(paths: list[Path]) -> dict[str, Any] | None:
    for path in paths:
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _read_data_quality(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "data_quality.json"
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _data_quality_freshness(data_quality: dict[str, Any]) -> dict[str, Any]:
    modes = data_quality.get("modes")
    if not isinstance(modes, dict):
        return {}
    return {
        str(mode): quality.get("freshness", {})
        if isinstance(quality, dict) and isinstance(quality.get("freshness"), dict)
        else {}
        for mode, quality in modes.items()
    }


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _first_filter_value(row: dict[str, Any], key: str) -> str:
    values = ((row.get("filter_values") or {}).get(key) or {}).get("values") or []
    return str(values[0]) if values else ""


def _clean_element_cn(value: Any) -> str:
    text = str(value or "").strip()
    return text.removesuffix("属性")


def _localize_avatar_rows(visualizer_dir: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    avatars_dir = visualizer_dir / "assets" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = avatars_dir / "_sources.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    manifest_changed = False
    output: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        icon_url = str(new_row.get("icon_url") or "")
        icon_crop = new_row.get("icon_crop") or ""
        slug = normalize_character_id(new_row.get("character_slug") or new_row.get("character_name_en") or new_row.get("character_name_cn"))
        local_url = _safe_same_origin_relative_url(icon_url)
        new_row["icon_url"] = local_url
        remote_url = _safe_http_url(icon_url)
        if remote_url and slug and not local_url:
            local_path = avatars_dir / f"{slug}.webp"
            source_key = json.dumps({"url": remote_url, "crop": icon_crop or ""}, ensure_ascii=False, sort_keys=True)
            cached_key = manifest.get(local_path.name)
            cache_ok = local_path.exists() and cached_key == source_key
            if cache_ok or _download_static_avatar(remote_url, local_path, icon_crop):
                new_row["icon_url"] = f"./assets/avatars/{local_path.name}"
                if cached_key != source_key:
                    manifest[local_path.name] = source_key
                    manifest_changed = True
        output.append(new_row)
    if manifest_changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return output


def _download_static_avatar(url: str, destination: Path, crop: Any = "") -> bool:
    try:
        from PIL import Image

        safe_url = _safe_http_url(url)
        if not safe_url:
            return False
        request = urllib.request.Request(
            safe_url,
            headers={
                "User-Agent": "Mozilla/5.0 zzz-endgame-exporter/0.1",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        image = Image.open(io.BytesIO(payload))
        image.seek(0)
        frame = image.convert("RGBA")
        crop_box = _avatar_crop_box(crop, frame.width, frame.height)
        if crop_box:
            frame = frame.crop(crop_box)
            frame = _center_square(frame)
            frame = frame.resize((168, 168), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (168, 168), (0, 0, 0, 0))
            canvas.alpha_composite(frame, (0, 0))
        else:
            frame.thumbnail((168, 168))
            canvas = Image.new("RGBA", (168, 168), (0, 0, 0, 0))
            canvas.alpha_composite(frame, ((168 - frame.width) // 2, (168 - frame.height) // 2))
        destination.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(destination, "WEBP", quality=88, method=6)
        return True
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def _avatar_crop_box(crop: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if isinstance(crop, dict):
        values = [crop.get(key) for key in ("left", "top", "right", "bottom")]
    elif isinstance(crop, (list, tuple)):
        values = list(crop[:4])
    else:
        return None
    if len(values) != 4:
        return None
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if all(0 <= value <= 1 for value in numbers):
        left, top, right, bottom = (
            numbers[0] * width,
            numbers[1] * height,
            numbers[2] * width,
            numbers[3] * height,
        )
    else:
        left, top, right, bottom = numbers
    left_i = max(0, min(width - 1, round(left)))
    top_i = max(0, min(height - 1, round(top)))
    right_i = max(left_i + 1, min(width, round(right)))
    bottom_i = max(top_i + 1, min(height, round(bottom)))
    return (left_i, top_i, right_i, bottom_i)


def _center_square(image: Any) -> Any:
    side = min(image.width, image.height)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def _build_roster(
    out_dir: Path,
    usage_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {normalize_character_id(row.get("character_slug")): row for row in name_rows}
    official = _load_official_roster_meta(out_dir)
    tier_meta: dict[str, dict[str, Any]] = {}
    for row in tier_rows:
        slug = normalize_character_id(row.get("character_slug"))
        if not slug:
            continue
        current = tier_meta.get(slug)
        if current is None or _tier_rank(row.get("tier")) < _tier_rank(current.get("tier")):
            tier_meta[slug] = row
    usage_meta: dict[str, dict[str, Any]] = {}
    for row in usage_rows:
        slug = normalize_character_id(row.get("character_slug"))
        if slug and row.get("sub_mode") == "all":
            usage_meta.setdefault(slug, row)
    name_slugs = {
        normalize_character_id(row.get("character_slug"))
        for row in name_rows
        if str(row.get("kind") or "agent") == "agent"
    }
    slugs = sorted(set(tier_meta) | set(usage_meta) | {slug for slug in name_slugs if slug})
    rows: list[dict[str, Any]] = []
    for index, slug in enumerate(slugs):
        tier = tier_meta.get(slug, {})
        name = names.get(slug, {})
        official_row = official.get(slug, {})
        usage = usage_meta.get(slug, {})
        element = tier.get("element") or usage.get("element") or official_row.get("element_en") or ""
        style = tier.get("style") or official_row.get("style_en") or ""
        role_group = tier.get("role_group") or _role_from_style(style)
        rows.append(
            {
                "character_slug": slug,
                "character_name_en": name.get("character_name_en") or tier.get("character_name_en") or usage.get("character_name_en") or official_row.get("character_name_en") or slug,
                "character_name_cn": name.get("character_name_cn") or official_row.get("character_name_cn") or "",
                "element_en": element,
                "element_cn": tier.get("element_cn") or official_row.get("element_cn") or ELEMENT_CN.get(str(element), ""),
                "style_en": style,
                "style_cn": tier.get("style_cn") or official_row.get("style_cn") or STYLE_CN.get(str(style), ""),
                "role_group": role_group,
                "role_group_cn": tier.get("role_group_cn") or _role_cn(role_group),
                "rarity": tier.get("rarity") or usage.get("rarity") or official_row.get("rarity") or "",
                "tier": tier.get("tier") or "未分档",
                "rating": tier.get("rating") or "",
                "tags": tier.get("tags") or "",
                "icon_url": tier.get("icon_url") or official_row.get("icon_url") or "",
                "release_order": _num(name.get("release_order")) if name.get("release_order") not in {"", None} else _num(official_row.get("release_order")) if official_row.get("release_order") not in {"", None} else 9999 + index,
            }
        )
    return sorted(rows, key=lambda r: (_release_order_value(r.get("release_order")), str(r.get("character_slug"))))


def _load_official_roster_meta(out_dir: Path) -> dict[str, dict[str, Any]]:
    raw_dir = out_dir / "raw" / "hoyowiki"
    zh_rows = _read_json_list(raw_dir / "zzz_agents_zh-cn.json")
    en_rows = _read_json_list(raw_dir / "zzz_agents_en-us.json")
    zh_by_id = {str(row.get("entry_page_id")): row for row in zh_rows}
    zh_order = {str(row.get("entry_page_id")): index for index, row in enumerate(zh_rows)}
    output: dict[str, dict[str, Any]] = {}
    for index, en_row in enumerate(en_rows):
        entry_id = str(en_row.get("entry_page_id") or "")
        zh_row = zh_by_id.get(entry_id, {})
        name = str(en_row.get("name") or "").strip()
        slug = normalize_character_id(name)
        if not slug:
            continue
        output[slug] = {
            "character_name_en": name,
            "character_name_cn": str(zh_row.get("name") or "").strip(),
            "element_en": _first_filter_value(en_row, "agent_stats"),
            "element_cn": _clean_element_cn(_first_filter_value(zh_row, "agent_stats")),
            "style_en": _first_filter_value(en_row, "agent_specialties"),
            "style_cn": _first_filter_value(zh_row, "agent_specialties"),
            "rarity": _first_filter_value(en_row, "agent_rarity") or _first_filter_value(zh_row, "agent_rarity"),
            "icon_url": str(zh_row.get("icon_url") or en_row.get("icon_url") or ""),
            "release_order": zh_order.get(entry_id, index),
        }
    return output


def _build_team_templates(
    team_rows: list[dict[str, Any]],
    roster_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
    phase_info_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {row["character_slug"]: row for row in roster_rows}
    name_map = {normalize_character_id(row.get("character_slug")): row for row in name_rows}
    phase_collect_dates = {
        (str(row.get("mode") or ""), str(row.get("phase_ver") or "")): str(row.get("collect_date") or "")
        for row in phase_info_rows
        if row.get("collect_date")
    }
    latest: dict[str, tuple[tuple[int, ...], str]] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        recency = _team_recency_tuple(row, phase_collect_dates)
        if mode and recency >= latest.get(mode, ((0,), "")):
            latest[mode] = recency
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        if not mode or _team_recency_tuple(row, phase_collect_dates) != latest.get(mode):
            continue
        collect_date = str(row.get("collect_date") or phase_collect_dates.get((mode, str(row.get("phase_ver") or ""))) or "")
        chars = [normalize_character_id(row.get(f"char_{i}_slug")) for i in range(1, 4)]
        if any(not c for c in chars):
            continue
        key = "|".join([mode, str(row.get("sub_mode") or ""), ">".join(sorted(chars))])
        bangboo = normalize_character_id(row.get("bangboo_slug"))
        stability_component = any(
            str(names.get(char, {}).get("role_group") or "") == "support" for char in chars
        )
        template = {
            "mode": mode,
            "mode_cn": row.get("mode_cn") or MODE_CN.get(mode, mode),
            "scope_key": row.get("sub_mode") or "all",
            "scope_label": row.get("sub_mode_cn") or row.get("sub_mode") or "全部",
            "collect_date": collect_date,
            "phase_ver": row.get("phase_ver", ""),
            "phase_name": row.get("phase_name", ""),
            "rank": _num(row.get("rank")),
            "app_rate": _num(row.get("app_rate")),
            "avg_score": _num(row.get("avg_score")),
            "bangboo": bangboo,
            "bangboo_name": row.get("bangboo_name_cn")
            or name_map.get(bangboo, {}).get("character_name_cn", ""),
            "source_kind": row.get("source_kind", ""),
            "merged_source_kinds": row.get("merged_source_kinds") or row.get("source_kind", ""),
            "source_file": row.get("source_file", ""),
            "source_url": row.get("source_url", ""),
            "merged_source_files": row.get("merged_source_files") or row.get("source_file", ""),
            "quality_flag": row.get("quality_flag", ""),
            "duplicate_count": _evidence_duplicate_count(row.get("duplicate_count")),
            "stability_component": stability_component,
            "recency_key": _team_recency_key(row, phase_collect_dates),
            "chars": chars,
            "names_cn": [
                names.get(char, {}).get("character_name_cn")
                or names.get(char, {}).get("character_name_en")
                or char
                for char in chars
            ],
        }
        _refresh_zzz_evidence(template)
        grouped.setdefault(key, []).append(template)

    output = [_finalize_zzz_template_group(templates) for templates in grouped.values()]
    return sorted(
        output,
        key=lambda row: (str(row.get("mode") or ""), str(row.get("scope_key") or ""), _zzz_template_sort_key(row)),
    )


def _evidence_duplicate_count(value: Any) -> int:
    try:
        return max(1, int(str(value).strip()))
    except (TypeError, ValueError):
        return 1


def _merged_evidence_values(*values: Any) -> str:
    return ";".join(
        sorted(
            {
                item.strip()
                for value in values
                for item in str(value or "").split(";")
                if item.strip()
            }
        )
    )


def _evidence_quality_allows_a(value: Any) -> bool:
    return all(
        not flag.strip() or flag.strip().lower() in {"ok", "valid", "complete", "clean"}
        for flag in str(value or "").split(";")
    )


def _positive_template_number(template: dict[str, Any], key: str) -> float | None:
    value = template.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _refresh_zzz_evidence(template: dict[str, Any]) -> None:
    count = _evidence_duplicate_count(template.get("duplicate_count"))
    limitations: list[str] = []
    if count < 2:
        limitations.append("仅 1 条记录")
    if _positive_template_number(template, "rank") is None:
        limitations.append("Rank 缺失")
    if _positive_template_number(template, "app_rate") is None:
        limitations.append("占比缺失")
    if _positive_template_number(template, "avg_score") is None:
        limitations.append("表现缺失或为 sentinel")
    if not str(template.get("merged_source_kinds") or "") or not str(template.get("merged_source_files") or ""):
        limitations.append("来源字段不完整")
    if not _evidence_quality_allows_a(template.get("quality_flag")):
        limitations.append("质量标记限制")
    if not bool(template.get("stability_component")):
        limitations.append("缺少已知稳定组件")
    if limitations:
        template["evidence_grade"] = "B"
        template["evidence_comment"] = f"真实队伍记录；保守按 B：{'；'.join(limitations)}。"
    else:
        template["evidence_grade"] = "A"
        template["evidence_comment"] = f"重复记录 {count} 条，Rank、占比、表现与来源字段完整。"


def _zzz_template_sort_key(template: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _positive_template_number(template, "rank") or float("inf"),
        -(_positive_template_number(template, "app_rate") or -1.0),
        -(_positive_template_number(template, "avg_score") or -1.0),
        -_evidence_duplicate_count(template.get("duplicate_count")),
        str(template.get("source_kind") or ""),
        str(template.get("source_file") or ""),
        str(template.get("bangboo") or ""),
        str(template.get("phase_ver") or ""),
        str(template.get("phase_name") or ""),
        ">".join(str(char) for char in template.get("chars") or []),
    )


def _finalize_zzz_template_group(templates: list[dict[str, Any]]) -> dict[str, Any]:
    selected = dict(min(templates, key=_zzz_template_sort_key))
    selected["duplicate_count"] = max(
        (_evidence_duplicate_count(template.get("duplicate_count")) for template in templates),
        default=1,
    )
    selected["merged_source_files"] = _merged_evidence_values(
        *(value for template in templates for value in (template.get("merged_source_files"), template.get("source_file")))
    )
    selected["merged_source_kinds"] = _merged_evidence_values(
        *(value for template in templates for value in (template.get("merged_source_kinds"), template.get("source_kind")))
    )
    selected["quality_flag"] = _merged_evidence_values(*(template.get("quality_flag") for template in templates))
    _refresh_zzz_evidence(selected)
    return selected


def _team_recency_tuple(row: dict[str, Any], phase_collect_dates: dict[tuple[str, str], str] | None = None) -> tuple[tuple[int, ...], str]:
    version = (
        _version_tuple(row.get("snapshot_id"))
        or _version_tuple(_source_snapshot(row.get("source_file")))
        or _version_tuple(row.get("phase_ver"))
        or (0,)
    )
    collect_date = str(row.get("collect_date") or "")
    if not collect_date and phase_collect_dates:
        collect_date = phase_collect_dates.get((str(row.get("mode") or ""), str(row.get("phase_ver") or "")), "")
    return version, collect_date


def _team_recency_key(row: dict[str, Any], phase_collect_dates: dict[tuple[str, str], str] | None = None) -> str:
    version, collect_date = _team_recency_tuple(row, phase_collect_dates)
    version_text = ".".join(f"{part:04d}" for part in version)
    return f"{version_text}|{collect_date}"


def _source_snapshot(value: Any) -> str:
    text = str(value or "")
    return text.split("/", 1)[0] if "/" in text else ""


def _version_tuple(value: Any) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", str(value or ""))]
    return tuple(parts)


def _latest(rows: list[dict[str, Any]], key: str) -> str:
    values = [str(row.get(key, "")) for row in rows if row.get(key)]
    return max(values) if values else ""


def _tier_rank(tier: Any) -> float:
    return {"T0": 0, "T0.5": 0.5, "T1": 1, "T1.5": 1.5, "T2": 2, "T3": 3, "T4": 4, "T5": 5}.get(str(tier), 99)


def _role_from_style(style: str) -> str:
    if style in {"Attack", "Rupture"}:
        return "crit_dps"
    if style == "Anomaly":
        return "anomaly_dps"
    if style in {"Support", "Stun", "Defence", "Defense"}:
        return "support"
    return "unknown"


def _role_from_style_cn(style: str) -> str:
    if style in {"强攻", "命破"}:
        return "crit_dps"
    if style == "异常":
        return "anomaly_dps"
    if style in {"支援", "击破", "防护"}:
        return "support"
    return "unknown"


def _role_cn(role: str) -> str:
    return {"crit_dps": "直伤主C", "anomaly_dps": "异常主C", "support": "辅助", "unknown": "未分类"}.get(role, "未分类")


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _release_order_value(value: Any) -> float:
    number = _num(value)
    return number if number is not None else 9999.0


# Python remains a migration oracle; static UI assets are owned by the Rust
# crate and read here to prevent a second embedded copy from drifting.
_CANONICAL_VISUALIZER_DIR = Path(__file__).resolve().parents[1] / "crates" / "miho-core" / "assets" / "visualizer" / "zzz"
INDEX_HTML = (_CANONICAL_VISUALIZER_DIR / "index.html").read_text(encoding="utf-8")
STYLES_CSS = (_CANONICAL_VISUALIZER_DIR / "styles.css").read_text(encoding="utf-8")
APP_JS = (_CANONICAL_VISUALIZER_DIR / "app.js").read_text(encoding="utf-8")
SOLVER_JS = (_CANONICAL_VISUALIZER_DIR.parent / "solver.js").read_text(encoding="utf-8")
