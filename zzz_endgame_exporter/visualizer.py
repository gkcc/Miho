from __future__ import annotations

import csv
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id

from miho_core.banner_plan import effective_banner_phases

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
    }
    data = _sanitize_output_urls(data)
    (visualizer_dir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    (visualizer_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (visualizer_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (visualizer_dir / "app.js").write_text(APP_JS, encoding="utf-8")


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
    by_slug = {str(row.get("character_slug") or ""): dict(row) for row in roster_rows}
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
    return sorted(by_slug.values(), key=lambda r: (_release_order_value(r.get("release_order")), str(r.get("character_slug"))))


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
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in team_rows:
        mode = str(row.get("mode") or "")
        if not mode or _team_recency_tuple(row, phase_collect_dates) != latest.get(mode):
            continue
        collect_date = str(row.get("collect_date") or phase_collect_dates.get((mode, str(row.get("phase_ver") or ""))) or "")
        chars = [normalize_character_id(row.get(f"char_{i}_slug")) for i in range(1, 4)]
        if any(not c for c in chars):
            continue
        key = "|".join([mode, str(row.get("sub_mode") or ""), ">".join(sorted(chars))])
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
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
                "bangboo": row.get("bangboo_slug", ""),
                "bangboo_name": row.get("bangboo_name_cn") or name_map.get(normalize_character_id(row.get("bangboo_slug")), {}).get("character_name_cn", ""),
                "source_kind": row.get("source_kind", ""),
                "source_file": row.get("source_file", ""),
                "recency_key": _team_recency_key(row, phase_collect_dates),
                "chars": chars,
                "names_cn": [names.get(char, {}).get("character_name_cn") or names.get(char, {}).get("character_name_en") or char for char in chars],
            }
        )
    return sorted(output, key=lambda r: (str(r["mode"]), str(r["scope_key"]), _num(r.get("rank")) or 9999))[:20000]


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


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ZZZ 高难与本地 Box 可视化</title>
  <link rel="stylesheet" href="./styles.css" />
</head>
<body>
<main class="app">
  <header class="topbar">
    <div><h1>绝区零高难可视化</h1><p id="metaLine"></p></div>
    <nav id="tabs" class="tabs"></nav>
  </header>

  <section id="analysisView">
    <section class="controls">
      <label>模式<div id="modeControl" class="segmented"></div></label>
      <label>职能<div id="roleControl" class="segmented"></div></label>
      <label>视图<div id="viewControl" class="segmented"></div></label>
      <label>数量<select id="limitSelect"><option value="10">Top 10</option><option value="16" selected>Top 16</option><option value="30">Top 30</option></select></label>
      <label>搜索<input id="searchInput" type="search" placeholder="中文名 / 英文名 / slug" /></label>
    </section>
    <section class="analysis-layout">
      <section class="panel chart-panel"><div class="panel-head"><div><h2 id="chartTitle">趋势</h2><p id="chartSubtitle"></p></div><div id="badges" class="badges"></div></div><svg id="chart"></svg><div id="tooltip" class="tooltip" hidden></div></section>
      <aside class="panel side-panel">
        <div class="side-section characters"><h3>角色数据</h3><div id="characterList" class="character-list"></div></div>
        <div class="side-section changelog"><h3>Changelog</h3><div id="changelogList" class="changelog-list"></div></div>
      </aside>
    </section>
  </section>

  <section id="bannerView" class="hidden">
    <section class="controls banner-controls">
      <label>阶段<div id="bannerPhaseControl" class="segmented"></div></label>
      <label>搜索<input id="bannerSearchInput" type="search" placeholder="角色 / 属性 / 标签" /></label>
    </section>
    <section class="banner-hero">
      <div><h2 id="bannerTitle">卡池情报</h2><p id="bannerSubtitle"></p></div>
      <div id="bannerBadges" class="badges"></div>
    </section>
    <section id="bannerGrid" class="banner-grid"></section>
    <div id="bannerTooltip" class="tooltip" hidden></div>
  </section>

  <section id="boxView" class="hidden">
    <section class="controls">
      <label>属性<div id="boxElementControl" class="segmented"></div></label>
      <label>特性<div id="boxStyleControl" class="segmented"></div></label>
      <label>状态<select id="boxOwnedSelect"><option value="all">全部</option><option value="owned">已拥有</option><option value="missing">未拥有</option><option value="banner_current">当期UP</option><option value="banner_next">下一期</option><option value="banner_satellite">卫星</option></select></label>
      <label>搜索<input id="boxSearchInput" type="search" placeholder="中文名 / 英文名 / slug" /></label>
      <div class="actions"><button id="boxExportBtn">导出Box</button><button id="boxImportBtn">导入</button><button id="boxMarkVisibleBtn">筛选设为已拥有</button><button id="boxBuildVisibleBtn">筛选设为练满</button><button id="boxClearBuildVisibleBtn">清筛选练度</button><input id="boxImportInput" type="file" accept="application/json,.json" hidden /></div>
    </section>
    <section id="buildEditor" class="build hidden"><img id="buildIcon" alt=""><div><h2 id="buildTitle">练度</h2><p id="buildSubtitle"></p></div><label>等级<select id="buildLevel"></select></label><label>音擎<select id="buildEngine"></select></label><label>影画<select id="buildMindscape"></select></label><label>专武<select id="buildSignature"></select></label><label>技能<select id="buildSkill"></select></label><label>驱动盘<select id="buildDisc"></select></label><span id="buildScore"></span><button id="buildMaxBtn">设为练满</button><button id="buildClearBtn">清空练度</button></section>
    <section class="panel"><div class="panel-head"><div><h2>我的 Box</h2><p id="boxSubtitle"></p></div><div id="boxBadges" class="badges"></div></div><div id="boxGrid" class="box-grid"></div><div id="boxTooltip" class="tooltip" hidden></div></section>
  </section>

  <section id="recommenderView" class="hidden">
    <section class="controls rec-controls">
      <label>模式<div id="recModeControl" class="segmented"></div></label>
      <label>关卡<select id="recScopeSelect"></select></label>
      <label>推荐属性<div id="recElementControl" class="segmented"></div></label>
      <label>缺口<select id="recGapSelect"><option value="0">只看可成队</option><option value="1" selected>最多缺1人</option><option value="3">显示全部</option></select></label>
      <label>风险<select id="recRiskSelect"><option value="warn" selected>仅提醒</option><option value="filter">过滤风险</option><option value="off">忽略风险</option></select></label>
      <label>数量<select id="recLimitSelect"><option value="8" selected>Top 8</option><option value="12">Top 12</option><option value="20">Top 20</option></select></label>
      <label>搜索<input id="recSearchInput" type="search" placeholder="角色 / 队伍 / 邦布" /></label>
    </section>
    <section id="phaseMechanics" class="phase-mechanics"><div><h2 id="phaseTitle">当期数据</h2><p id="phaseDates"></p></div><p id="phaseText"></p></section>
    <section class="rec-layout">
      <section class="panel"><div class="panel-head"><div><h2 id="recTitle">组队推荐</h2><p id="recSubtitle"></p></div><div id="recBadges" class="badges"></div></div><div id="recList" class="rec-list"></div></section>
      <aside class="panel rec-slate"><div class="panel-head"><div><h2>多队方案</h2><p id="recSlateSubtitle"></p></div></div><div id="recSlateList" class="rec-slate-list"></div></aside>
    </section>
    <div id="recTooltip" class="tooltip" hidden></div>
  </section>
</main>
<script src="./app.js"></script>
</body>
</html>
""" + """.banner-controls{grid-template-columns:1fr 1.4fr}.banner-hero{display:flex;justify-content:space-between;gap:14px;align-items:center;background:#112a32;color:white;border-radius:8px;padding:16px 18px;margin-bottom:14px}.banner-hero h2{margin:0 0 4px;font-size:21px}.banner-hero p{margin:0;color:#c2d2d7;font-size:12px;line-height:1.5}.banner-hero .badges span{background:#173a45;border-color:#315866;color:#e8f2f4}.banner-grid{display:flex;flex-direction:column;gap:14px}.banner-section{background:white;border:1px solid #d8e1e5;border-radius:8px}.banner-section-head{display:flex;justify-content:space-between;gap:10px;padding:14px 16px;border-bottom:1px solid #edf1f3}.banner-section-head h3{margin:0 0 4px;font-size:17px}.banner-section-head p{margin:0;color:#657780;font-size:12px}.banner-section-head a{color:#174c5a;font-size:12px;text-decoration:none;font-weight:700}.banner-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px;padding:14px}.banner-card{display:grid;grid-template-columns:118px minmax(0,1fr);gap:12px;border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;padding:12px;min-height:230px}.banner-card.current{border-left:4px solid #2f7b69}.banner-card.next{border-left:4px solid #266bb0}.banner-card.satellite{border-left:4px solid #8a5a1e}.banner-card.owned{background:#f3fbf7}.banner-art{position:relative;border-radius:8px;background:#e8eef1;min-height:146px;display:grid;place-items:center;overflow:hidden}.banner-art img{width:104px;height:104px;border-radius:50%;object-fit:cover;filter:drop-shadow(0 8px 16px rgba(0,0,0,.18))}.avatar-fallback{width:92px;height:92px;border-radius:50%;display:grid;place-items:center;background:#174c5a;color:white;font-weight:800}.mini-owned{position:absolute;left:8px;right:8px;bottom:8px;border:1px solid #c6d2d7;background:white;border-radius:6px;padding:5px 7px;cursor:pointer}.banner-kicker{font-size:11px;color:#607079;font-weight:800}.banner-card h3{margin:3px 0 4px;font-size:18px}.banner-meta{margin:0 0 8px;color:#526971;font-size:12px}.spark{width:100%;height:54px;background:white;border:1px solid #e4ebee;border-radius:6px}.spark-line{fill:none;stroke:#174c5a;stroke-width:2.4}.spark-axis{stroke:#d8e1e5}.spark-dot{fill:#2f7b69;stroke:white;stroke-width:1.5}.spark-empty{fill:#657780;font-size:12px}.banner-facts p{margin:6px 0;color:#2e4149;font-size:12px;line-height:1.45}.banner-relations{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.banner-relations span{border:1px solid #d6e1e5;background:white;border-radius:999px;padding:3px 7px;color:#39505a;font-size:11px}.banner-relations span.owned{border-color:#2f7b69;background:#edf8f2;color:#1f604f}@media(max-width:1100px){.banner-controls{grid-template-columns:1fr 1fr}}@media(max-width:720px){.banner-card-grid{grid-template-columns:1fr}.banner-card{grid-template-columns:92px minmax(0,1fr)}}"""

BANNER_CSS = INDEX_HTML.split("</html>", 1)[1]
INDEX_HTML = INDEX_HTML.split("</html>", 1)[0] + "</html>\n"


STYLES_CSS = """*{box-sizing:border-box}body{margin:0;background:#f4f7f8;color:#172126;font-family:Inter,Segoe UI,Arial,'Microsoft YaHei',sans-serif}.hidden{display:none!important}.app{padding:18px 20px 26px}.topbar{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}.topbar h1{margin:0 0 5px;font-size:24px}.topbar p,.panel-head p{margin:0;color:#64757d;font-size:12px}.tabs,.segmented,.badges,.actions{display:flex;gap:6px;flex-wrap:wrap}.tabs button,.segmented button,.actions button,.build button{border:1px solid #c6d2d7;background:white;color:#1d3942;border-radius:6px;padding:7px 10px;cursor:pointer}.tabs button.active,.segmented button.active{background:#174c5a;color:white;border-color:#174c5a}.controls{display:grid;grid-template-columns:1fr 1fr 1fr .55fr 1.2fr;gap:10px;align-items:end;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.controls label{display:block;color:#607079;font-size:12px}.controls input,.controls select,.build select{width:100%;height:34px;border:1px solid #c8d4d9;border-radius:6px;background:white;padding:6px 8px;margin-top:5px}.panel{background:white;border:1px solid #d8e1e5;border-radius:8px;min-height:650px}.panel-head{display:flex;justify-content:space-between;gap:12px;padding:14px 16px 10px;border-bottom:1px solid #edf1f3}.panel-head h2,.build h2{margin:0 0 4px;font-size:18px}.badges span{border:1px solid #d6e1e5;background:#f8fafb;border-radius:999px;padding:4px 8px;color:#39505a;font-size:11px;font-weight:650}.analysis-layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:14px}.chart-panel{min-width:0}.side-panel{padding:12px;display:flex;flex-direction:column;gap:12px;max-height:722px;overflow:hidden}.side-section{min-height:0;display:flex;flex-direction:column}.side-section.characters{flex:1 1 auto}.side-section.changelog{flex:0 0 245px}.side-section h3{margin:0 0 8px;font-size:15px}.character-list,.changelog-list{overflow:auto;display:flex;flex-direction:column;gap:7px;padding-right:4px}.character-card{border:1px solid #d8e1e5;background:#fbfcfd;border-radius:7px;padding:8px;display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:8px;align-items:center;cursor:pointer;text-align:left}.character-card:hover{border-color:#86a6af;background:#f4f9fa}.character-card img{width:38px;height:38px;border-radius:50%;background:#e7ecef;object-fit:cover}.character-card .name{font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.character-card .meta{color:#6b7c84;font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.character-card .rate{font-size:13px;font-weight:800;color:#174c5a;text-align:right}.changelog-item{border-left:3px solid #8aa3ad;background:#f8fafb;border-radius:5px;padding:8px 9px}.changelog-item time{font-weight:700;font-size:12px;color:#174c5a}.changelog-item p{margin:4px 0 0;color:#405158;font-size:12px;line-height:1.45}#chart{width:100%;height:620px;display:block}.axis{fill:#546870;font-size:11px}.grid{stroke:#e7ecef}.line{fill:none;stroke-width:2.2}.bar{stroke-width:10;stroke-linecap:round}.avatar,.box-card img,.rec-member img{border-radius:50%;background:#e7ecef;object-fit:cover}.avatar-ring{stroke:white;stroke-width:2;filter:drop-shadow(0 1px 2px rgba(0,0,0,.24));pointer-events:none}.tooltip{position:fixed;z-index:20;width:320px;background:#101820;color:white;border-radius:8px;padding:12px;box-shadow:0 16px 36px rgba(0,0,0,.24);pointer-events:none}.tooltip b{color:#9fb7c0}.tooltip-grid{display:grid;grid-template-columns:84px 1fr;gap:5px 8px;font-size:12px}.heat-cell{rx:4;ry:4;stroke:#fff;stroke-width:1}.heat-name{fill:#263a43;font-size:12px;font-weight:650}.box-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:10px;padding:14px}.box-card{position:relative;border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;min-height:150px;padding:10px 8px;text-align:center;cursor:pointer}.box-card.owned{border-color:#2f7b69;background:#f3fbf7}.box-card.missing img{filter:grayscale(1);opacity:.38}.box-card.selected{outline:2px solid #174c5a;outline-offset:2px}.box-card img{width:64px;height:64px}.box-card .name{font-size:12px;font-weight:700;line-height:1.25;min-height:31px;display:flex;align-items:center;justify-content:center}.box-card .meta{font-size:11px;color:#64777f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.build-btn{position:absolute;left:7px;top:7px;font-size:11px;border:1px solid #c6d2d7;background:white;border-radius:6px;padding:3px 6px}.build{display:grid;grid-template-columns:46px minmax(150px,.8fr) repeat(4,minmax(80px,1fr)) auto auto auto;gap:10px;align-items:center;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.build img{width:46px;height:46px;border-radius:50%}.build label{font-size:12px;color:#607079}.rec-controls{grid-template-columns:1fr .62fr 1.2fr .55fr .55fr .5fr 1fr}.phase-mechanics{display:grid;grid-template-columns:minmax(220px,.62fr) minmax(0,1fr);gap:14px;align-items:center;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px 14px;margin-bottom:14px}.phase-mechanics h2{margin:0 0 4px;font-size:16px}.phase-mechanics p{margin:0;color:#42565f;font-size:12px;line-height:1.5}.rec-layout{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:14px}.rec-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:12px;padding:14px}.rec-card{border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;padding:12px}.rec-card.risky,.rec-slate-card.risky{border-color:#d09b3d;background:#fffaf1}.rec-head{display:flex;justify-content:space-between;gap:10px}.rec-head h3{margin:0;font-size:15px}.score{text-align:right;color:#174c5a;font-weight:800}.rec-team{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}.rec-member{border:1px solid #d8e1e5;border-radius:7px;background:white;text-align:center;padding:8px 6px;min-width:0}.rec-member.owned{border-color:#2f7b69;background:#f3fbf7}.rec-member.missing{border-color:#d1a24c;background:#fffaf1}.rec-member.risky{box-shadow:inset 0 0 0 1px #c88724}.rec-member img{width:46px;height:46px}.rec-member .name{font-size:11px;font-weight:700;line-height:1.2;min-height:26px}.rec-member .meta,.rec-meta,.risk-note{font-size:12px;color:#657780}.tags{display:flex;gap:6px;flex-wrap:wrap}.tags span{border:1px solid #d6e1e5;background:white;border-radius:999px;padding:3px 7px;color:#39505a;font-size:11px}.tags .warn{border-color:#dfb86a;background:#fff8e8;color:#7a5200}.tags .danger{border-color:#cb7a33;background:#fff1e6;color:#7a3300}.risk-note{margin-top:8px;border:1px solid #e4bd72;background:#fff8e8;border-radius:6px;padding:7px 8px;color:#724d00}.rec-slate{min-height:650px}.rec-slate-list{padding:14px;display:flex;flex-direction:column;gap:10px}.rec-slate-card{border:1px solid #d8e1e5;border-radius:8px;background:#fbfcfd;padding:10px}.rec-slate-card h3{margin:0 0 8px;font-size:14px}.rec-slate-team{display:flex;gap:6px;flex-wrap:wrap}.rec-slate-team img{width:34px;height:34px;border-radius:50%;background:#e7ecef}.rec-slate-team img.missing{filter:grayscale(1);opacity:.38}.rec-slate-team img.risky{outline:2px solid #c88724}.empty{padding:28px;text-align:center;color:#657780}@media(max-width:1100px){.controls,.rec-controls,.build{grid-template-columns:1fr 1fr}.panel-head{flex-direction:column}.analysis-layout,.rec-layout,.phase-mechanics{grid-template-columns:1fr}.side-panel{max-height:none}.side-section.changelog{flex-basis:auto}}@media(max-width:720px){.app{padding:14px 12px}.topbar{flex-direction:column}.rec-list{grid-template-columns:1fr}.box-grid{grid-template-columns:repeat(auto-fill,minmax(92px,1fr))}}"""
STYLES_CSS += BANNER_CSS
STYLES_CSS += ".build{grid-template-columns:46px minmax(150px,.8fr) repeat(6,minmax(78px,1fr)) auto auto auto}@media(max-width:1100px){.build{grid-template-columns:1fr 1fr}}"


APP_JS = r"""const MODES=[['sd','式舆防卫'],['da','危局强袭']];
const ROLES=[['all','全部'],['crit_dps','直伤主C'],['anomaly_dps','异常主C'],['support','辅助'],['unknown','未分类']];
const VIEWS=[['trend','趋势'],['latest','排行'],['heatmap','热力']];
const ELEMENTS=['物理','火','冰','电','以太','风','玄墨'];
const STYLES=['强攻','异常','击破','支援','防护','命破'];
const TIER_RANK={'T0':0,'T0.5':.5,'T1':1,'T1.5':1.5,'T2':2,'T3':3,'T4':4,'T5':5,'未分档':9};
const BUILD_LEVELS=[0,20,40,50,55,60], BUILD_MINDSCAPES=[['unset','未录入'],[0,'0影'],[1,'1影'],[2,'2影'],[3,'3影'],[4,'4影'],[5,'5影'],[6,'6影']], BUILD_SIGNATURES=[['unset','未录入'],['no','无专武'],['yes','有专武']], BUILD_SKILLS=[['unset','未录入',0],['low','低',.35],['mid','中',.6],['high','高',.84],['max','满',1]], BUILD_DISCS=[['unset','未录入',0],['none','未刷',.12],['ok','可用',.58],['good','成型',.84],['great','毕业',1]];
const BOX_KEY='zzz_endgame_box_v2', OLD_BOX_KEYS=['zzz_endgame_box_v1'], REC_KEY='zzz_endgame_rec_v1';
let DATA=null,state={page:'analysis',mode:'sd',role:'all',view:'trend',limit:'16',search:''},box={owned:new Set(),builds:{},buildSlug:'',element:'all',style:'all',status:'all',search:'',saveStatus:'浏览器缓存'},rec={mode:'sd',scope:'',elements:{},gap:'1',riskMode:'warn',limit:'8',search:''},banner={phase:'current',search:''},boxSaveTimer=null;
const $=id=>document.getElementById(id), num=v=>{const n=Number(v);return Number.isFinite(n)?n:null}, esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])), pct=v=>num(v)==null?'-':`${num(v).toFixed(2)}%`;
const safeRelative=v=>{const text=String(v??'').trim();if(!text||text.includes('\\')||/[\u0000-\u001f\u007f]/.test(text)||/^[a-z][a-z0-9+.-]*:/i.test(text)||text.startsWith('//'))return '';try{const url=new URL(text,location.href),decoded=decodeURIComponent(url.pathname);if(url.origin!==location.origin||decoded.split('/').some((part,index)=>part==='..'||(part==='.'&&index>0)))return '';return text;}catch{return ''}};
const safeAvatar=v=>safeRelative(v),safeLink=v=>{const text=String(v??'').trim();if(/^https?:\/\//i.test(text)){try{const url=new URL(text);return ['http:','https:'].includes(url.protocol)?text:'';}catch{return ''}}return safeRelative(text)};
fetch(`./data.json?v=${Date.now()}`,{cache:'no-store'}).then(r=>r.json()).then(d=>{DATA=d;loadBox();loadRec();init();render();syncBoxFromServer();}).catch(e=>document.body.innerHTML=`<main class="app"><h1>数据加载失败</h1><p>${esc(e.message)}</p></main>`);
function init(){ $('metaLine').textContent=`Prydwen更新：${DATA.meta.tierUpdatedAt||'未知'} · 本地生成：${DATA.meta.generatedAt||'未知'}`; buttons('tabs',[['analysis','趋势分析'],['banner','卡池情报'],['box','我的Box'],['recommender','组队推荐']],state.page,v=>{state.page=v;render();}); buttons('modeControl',MODES,state.mode,v=>{state.mode=v;render();}); buttons('roleControl',ROLES,state.role,v=>{state.role=v;render();}); buttons('viewControl',VIEWS,state.view,v=>{state.view=v;render();}); $('limitSelect').onchange=e=>{state.limit=e.target.value;renderAnalysis();}; $('searchInput').oninput=e=>{state.search=e.target.value.trim().toLowerCase();renderAnalysis();}; initBanner(); initBox(); initRec();}
function buttons(id,items,current,onClick){const el=$(id); el.innerHTML=''; items.forEach(([v,l])=>{const b=document.createElement('button');b.type='button';b.textContent=l;b.dataset.value=v;b.className=v===current?'active':'';b.onclick=()=>{[...el.children].forEach(x=>x.classList.remove('active'));b.classList.add('active');onClick(v);};el.appendChild(b);});}
function render(){ $('analysisView').classList.toggle('hidden',state.page!=='analysis');$('bannerView').classList.toggle('hidden',state.page!=='banner');$('boxView').classList.toggle('hidden',state.page!=='box');$('recommenderView').classList.toggle('hidden',state.page!=='recommender');[...$('tabs').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.page)); if(state.page==='banner')renderBanner();else if(state.page==='box')renderBox();else if(state.page==='recommender')renderRec();else renderAnalysis();}
function charInfo(slug){return (DATA.rosterRows||[]).find(r=>r.character_slug===slug)||{character_slug:slug,character_name_cn:'',character_name_en:slug,element_cn:'',style_cn:'',role_group:'unknown',role_group_cn:'未分类',tier:'未分档',icon_url:''};}
function charName(slug){const r=charInfo(slug);return r.character_name_cn||r.character_name_en||slug}
function bangbooName(slug, fallback=''){const r=(DATA.nameRows||[]).find(x=>x.character_slug===slug);return fallback||r?.character_name_cn||r?.character_name_en||slug||'-'}
function filteredUsage(){const q=state.search; return (DATA.usageRows||[]).filter(r=>r.mode===state.mode&&r.sub_mode==='all'&&(state.role==='all'||(charInfo(r.character_slug).role_group===state.role))&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,charInfo(r.character_slug).element_cn,charInfo(r.character_slug).style_cn].some(x=>String(x||'').toLowerCase().includes(q))));}
function seriesRows(){const map=new Map();filteredUsage().forEach(r=>{if(!map.has(r.character_slug))map.set(r.character_slug,[]);map.get(r.character_slug).push(r);});return [...map.entries()].map(([slug,rows])=>{rows.sort((a,b)=>String(a.collect_date).localeCompare(String(b.collect_date)));return{slug,rows,latest:rows[rows.length-1]};}).sort((a,b)=>(num(b.latest.app_rate)||0)-(num(a.latest.app_rate)||0)).slice(0,Number(state.limit)||16);}
function renderAnalysis(){const series=seriesRows();$('chartTitle').textContent=`${MODES.find(x=>x[0]===state.mode)?.[1]} · ${ROLES.find(x=>x[0]===state.role)?.[1]} · ${VIEWS.find(x=>x[0]===state.view)?.[1]}`;$('chartSubtitle').textContent=`展示 ${series.length} 个代理人，指标为出场率 / 平均分`; $('badges').innerHTML=[`角色 ${DATA.rosterRows.length}`,`样本点 ${filteredUsage().length}`].map(x=>`<span>${x}</span>`).join(''); state.view==='latest'?drawBars(series):state.view==='heatmap'?drawHeatmap(series):drawLines(series);renderCharacterList(series);renderChangelog(series);}
function chartBox(){const svg=$('chart');svg.innerHTML='';const rect=svg.getBoundingClientRect();const w=Math.max(760,rect.width||1000),h=620;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);return{svg,w,h};}
function add(svg,tag,attrs){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));svg.appendChild(n);return n;}
function drawLines(series){const {svg,w,h}=chartBox();if(!series.length){add(svg,'text',{x:40,y:60,class:'axis'}).textContent='暂无数据';return;}const defs=add(svg,'defs',{});const dates=[...new Set(series.flatMap(s=>s.rows.map(r=>r.collect_date)))].sort();const max=Math.max(1,...series.flatMap(s=>s.rows.map(r=>num(r.app_rate)||0)));const m={l:70,r:44,t:42,b:60},cw=w-m.l-m.r,ch=h-m.t-m.b;const x=d=>m.l+(dates.indexOf(d)/Math.max(1,dates.length-1))*cw,y=v=>m.t+ch-(v/max)*ch;for(let i=0;i<=5;i++){const yy=m.t+ch*i/5;add(svg,'line',{x1:m.l,y1:yy,x2:m.l+cw,y2:yy,class:'grid'});add(svg,'text',{x:m.l-8,y:yy+4,'text-anchor':'end',class:'axis'}).textContent=(max*(1-i/5)).toFixed(0);}dates.forEach((d,i)=>{if(dates.length>12&&i%2)return;add(svg,'text',{x:x(d),y:m.t+ch+24,'text-anchor':'middle',class:'axis'}).textContent=d.slice(5);});series.forEach((s,i)=>{const color=['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2'][i%6];const pts=s.rows.map(r=>[x(r.collect_date),y(num(r.app_rate)||0),r]).filter(p=>Number.isFinite(p[1]));add(svg,'path',{d:pts.map((p,j)=>`${j?'L':'M'}${p[0]} ${p[1]}`).join(' '),stroke:color,class:'line'});pts.forEach(([xx,yy,row],pi)=>drawAvatarPoint(svg,defs,xx,yy,row,s.slug,color,i,pi));});}
function drawAvatarPoint(svg,defs,x,y,row,slug,color,seriesIndex,pointIndex){const info=charInfo(slug),r=11,href=safeAvatar(info.icon_url||row.icon_url);if(href){const clipId=`clip-${seriesIndex}-${pointIndex}-${Math.round(x)}-${Math.round(y)}`;const clip=add(defs,'clipPath',{id:clipId});add(clip,'circle',{cx:x,cy:y,r});const img=add(svg,'image',{href,x:x-r,y:y-r,width:r*2,height:r*2,'clip-path':`url(#${clipId})`,class:'avatar'});add(svg,'circle',{cx:x,cy:y,r,fill:'none',stroke:color,class:'avatar-ring'});img.addEventListener('mouseenter',e=>showChartTip(e,row));img.addEventListener('mousemove',moveTip);img.addEventListener('mouseleave',()=>{$('tooltip').hidden=true;});}else{const c=add(svg,'circle',{cx:x,cy:y,r:4.8,fill:color});c.addEventListener('mouseenter',e=>showChartTip(e,row));c.addEventListener('mousemove',moveTip);c.addEventListener('mouseleave',()=>{$('tooltip').hidden=true;});}}
function drawBars(series){const {svg,w,h}=chartBox();const m={l:170,r:80,t:36,b:36},rowH=Math.max(32,Math.min(44,(h-m.t-m.b)/Math.max(series.length,1)));const max=Math.max(1,...series.map(s=>num(s.latest.app_rate)||0));series.forEach((s,i)=>{const y=m.t+i*rowH+rowH/2,val=num(s.latest.app_rate)||0,x=m.l+(val/max)*(w-m.l-m.r),info=charInfo(s.slug);add(svg,'text',{x:18,y:y+4,class:'axis'}).textContent=`${i+1}. ${charName(s.slug)}`;add(svg,'line',{x1:m.l,y1:y,x2:x,y2:y,stroke:'#174c5a',class:'bar'});add(svg,'text',{x:x+14,y:y+4,class:'axis'}).textContent=pct(val);});}
function drawHeatmap(series){const {svg,w,h}=chartBox();if(!series.length){add(svg,'text',{x:40,y:60,class:'axis'}).textContent='暂无数据';return;}const dates=[...new Set(series.flatMap(s=>s.rows.map(r=>r.collect_date)))].sort();const m={l:180,r:30,t:54,b:42},gap=3,rowH=Math.max(24,Math.min(34,(h-m.t-m.b)/Math.max(series.length,1))),cw=Math.max(12,(w-m.l-m.r-(dates.length-1)*gap)/Math.max(dates.length,1));const max=Math.max(1,...series.flatMap(s=>s.rows.map(r=>num(r.app_rate)||0)));dates.forEach((d,j)=>{if(dates.length>14&&j%2)return;add(svg,'text',{x:m.l+j*(cw+gap)+cw/2,y:m.t-18,'text-anchor':'middle',class:'axis'}).textContent=d.slice(5);});series.forEach((s,i)=>{const y=m.t+i*rowH;add(svg,'text',{x:18,y:y+rowH/2+4,class:'heat-name'}).textContent=`${i+1}. ${charName(s.slug)}`;const byDate=new Map(s.rows.map(r=>[r.collect_date,r]));dates.forEach((d,j)=>{const r=byDate.get(d),val=num(r?.app_rate)||0,intensity=Math.max(.06,Math.min(1,val/max));const rect=add(svg,'rect',{x:m.l+j*(cw+gap),y:y+4,width:cw,height:rowH-8,fill:`rgba(23,76,90,${intensity})`,class:'heat-cell'});if(r){rect.addEventListener('mouseenter',e=>showChartTip(e,r));rect.addEventListener('mousemove',moveTip);rect.addEventListener('mouseleave',()=>{$('tooltip').hidden=true;});}});});}
function showChartTip(evt,row){const tt=$('tooltip');tt.innerHTML=`<div class="tooltip-grid"><b>角色</b><span>${esc(charName(row.character_slug))}</span><b>日期</b><span>${esc(row.collect_date)}</span><b>出场率</b><span>${pct(row.app_rate)}</span><b>平均分</b><span>${esc(row.avg_score||'-')}</span><b>期数</b><span>${esc(row.phase_name||row.phase_ver||'-')}</span></div>`;tt.hidden=false;moveTip(evt);}
function moveTip(evt){const tt=$('tooltip');let x=evt.clientX+16,y=evt.clientY+16;const r=tt.getBoundingClientRect();if(x+r.width+12>innerWidth)x=evt.clientX-r.width-16;if(y+r.height+12>innerHeight)y=evt.clientY-r.height-16;tt.style.left=`${Math.max(12,x)}px`;tt.style.top=`${Math.max(12,y)}px`;}
function renderCharacterList(series){const boxEl=$('characterList');if(!boxEl)return;boxEl.innerHTML='';if(!series.length){boxEl.innerHTML='<div class="empty">暂无角色数据</div>';return;}series.forEach((s,i)=>{const row=s.latest,info=charInfo(s.slug),card=document.createElement('button');card.type='button';card.className='character-card';card.innerHTML=`<img src="${esc(safeAvatar(info.icon_url))}" alt=""><div><div class="name">${esc(charName(s.slug))}</div><div class="meta">${esc(info.tier||'未分档')} · ${esc(info.element_cn||'')} · ${esc(info.style_cn||info.role_group_cn||'')}</div></div><div class="rate">${pct(row.app_rate)}</div>`;card.onclick=()=>{$('searchInput').value=charName(s.slug);state.search=charName(s.slug).toLowerCase();renderAnalysis();};boxEl.appendChild(card);});}
function renderChangelog(series){const boxEl=$('changelogList');if(!boxEl)return;boxEl.innerHTML='';const slugs=new Set(series.map(s=>s.slug));const related=(DATA.changelogRows||[]).filter(r=>String(r.character_slugs||'').split(';').some(slug=>slugs.has(slug)));const rows=(related.length?related:(DATA.changelogRows||[])).slice(0,8);if(!rows.length){boxEl.innerHTML='<div class="empty">暂无 changelog</div>';return;}rows.forEach(r=>{const item=document.createElement('div');item.className='changelog-item';const text=String(r.text||'');item.innerHTML=`<time>${esc(r.changelog_date||'')}</time><p>${esc(text.slice(0,420))}${text.length>420?'...':''}</p>`;boxEl.appendChild(item);});}
function initBanner(){buttons('bannerPhaseControl',[['current','当期UP'],['next','下一期'],['satellite','确定卫星'],['all','全部含已结束']],banner.phase,v=>{banner.phase=v;renderBanner();});$('bannerSearchInput').oninput=e=>{banner.search=e.target.value.trim().toLowerCase();renderBanner();};}
function bannerRows(){const q=banner.search;return (DATA.bannerRows||[]).filter(r=>(banner.phase==='all'||r.phase_status===banner.phase)&&(!q||[r.character_slug,r.character_name_cn,r.character_name_en,r.banner_role,r.element_cn,r.style_cn,r.role_group_cn,...(r.analysis_tags||[])].some(x=>String(x||'').toLowerCase().includes(q))));}
function renderBanner(){const rows=bannerRows();$('bannerTitle').textContent='卡池情报';$('bannerSubtitle').textContent='这里只做数据提炼：复刻看历史趋势和组队占用，新角色/卫星只做公开信息与 Box 关系识别。';$('bannerBadges').innerHTML=[`角色 ${rows.length}`,`Box ${box.owned.size}`,box.saveStatus||'浏览器缓存'].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('bannerGrid');grid.innerHTML='';if(!rows.length){grid.innerHTML='<div class="empty">暂无卡池情报；可更新 configs/zzz_banner_plan.json</div>';return;}const phases=[...new Map(rows.map(r=>[r.phase_id,{id:r.phase_id,title:r.phase_title,subtitle:r.phase_subtitle,date:r.date_range,source:r.source_label,url:r.source_url,status:r.phase_status}])).values()];phases.forEach(phase=>{const section=document.createElement('section'),phaseUrl=safeLink(phase.url);section.className='banner-section';section.innerHTML=`<div class="banner-section-head"><div><h3>${esc(phase.title||'卡池')}</h3><p>${esc(phase.subtitle||'')} · ${esc(phase.date||'时间待确认')}</p></div>${phaseUrl?`<a href="${esc(phaseUrl)}" target="_blank" rel="noopener noreferrer">${esc(phase.source||'来源')}</a>`:''}</div><div class="banner-card-grid"></div>`;const inner=section.querySelector('.banner-card-grid');rows.filter(r=>r.phase_id===phase.id).forEach(row=>inner.appendChild(bannerCard(row)));grid.appendChild(section);});}
function bannerCard(row){const slug=row.character_slug,info={...charInfo(slug),...row},ins=bannerInsight(row),icon=safeAvatar(info.icon_url);const card=document.createElement('article');card.className=`banner-card ${box.owned.has(slug)?'owned':''} ${row.phase_status}`;const tags=(row.analysis_tags||[]).slice(0,5).map(t=>`<span>${esc(t)}</span>`).join('');card.innerHTML=`<div class="banner-art">${icon?`<img src="${esc(icon)}" alt="">`:`<div class="avatar-fallback">${esc((info.character_name_cn||slug).slice(0,2))}</div>`}<button class="mini-owned">${box.owned.has(slug)?'已拥有':'加入Box'}</button></div><div class="banner-body"><div class="banner-kicker">${esc(row.banner_role||row.phase_subtitle||'卡池角色')}</div><h3>${esc(info.character_name_cn||info.character_name_en||slug)}</h3><p class="banner-meta">${esc(info.rarity||'-')} · ${esc(info.element_cn||'属性未知')} · ${esc(info.style_cn||info.role_group_cn||'特性未知')} · ${esc(ins.tierText)}</p><svg class="spark" viewBox="0 0 220 54">${sparkline(ins.points)}</svg><div class="tags">${tags}</div><div class="banner-facts">${ins.lines.slice(0,4).map(x=>`<p>${esc(x)}</p>`).join('')}</div><div class="banner-relations">${ins.relations.slice(0,6).map(x=>`<span class="${x.owned?'owned':''}">${esc(x.name)}${x.count?` ×${x.count}`:''}</span>`).join('')||'<span>暂无历史组合</span>'}</div></div>`;card.querySelector('.mini-owned').onclick=e=>{e.stopPropagation();box.owned.has(slug)?box.owned.delete(slug):box.owned.add(slug);box.buildSlug=slug;saveBox();renderBanner();};card.addEventListener('mouseenter',e=>showBannerTip(e,row,ins));card.addEventListener('mousemove',moveBannerTip);card.addEventListener('mouseleave',()=>{$('bannerTooltip').hidden=true;});return card;}
function bannerInsight(row){const slug=row.character_slug,info={...charInfo(slug),...row},usage=(DATA.usageRows||[]).filter(r=>r.character_slug===slug&&r.sub_mode==='all').sort((a,b)=>String(a.collect_date).localeCompare(String(b.collect_date))),points=usage.map(r=>({date:r.collect_date,value:num(r.app_rate)||0,mode:r.mode_cn||r.mode})),tiers=(DATA.tierRows||[]).filter(r=>r.character_slug===slug),best=tiers.sort((a,b)=>(TIER_RANK[a.tier]??9)-(TIER_RANK[b.tier]??9))[0]||{},teams=(DATA.teamTemplates||[]).filter(t=>(t.chars||[]).includes(slug)),relations=relationRows(slug,teams),ownedRelation=relations.filter(r=>r.owned).slice(0,4).map(r=>r.name).join('、'),lines=[];if(points.length){const latest=points[points.length-1],avg=points.slice(-3).reduce((s,p)=>s+p.value,0)/Math.min(3,points.length),delta=points.length>1?latest.value-points[0].value:0;lines.push(`历史：${points.length} 个样本点，最新 ${latest.value.toFixed(2)}%，近三期均值 ${avg.toFixed(2)}%，首尾变化 ${delta.toFixed(2)}%。`);}else lines.push('历史：本地高难暂无完整样本，不能用趋势替代实测。');if(teams.length){const bestRank=Math.min(...teams.map(t=>num(t.rank)||9999));lines.push(`组队：历史模板 ${teams.length} 条，最好 Rank ${bestRank}，常见队友见下方关系。`);}else lines.push('组队：暂无可回溯历史队伍，等待实测或人工分析。');if(ownedRelation)lines.push(`Box关系：你已有角色中，历史上相关度较高的是 ${ownedRelation}。`);else lines.push(`Box关系：暂未发现与你已有 Box 的直接历史组合；需要看属性/特性是否能补洞。`);if(row.phase_status==='satellite'||!points.length)lines.push('未知项：技能组、倍率、专武价值、实战轴和环境适配仍需外部分析确认。');if(row.focus)lines.push(`关注点：${row.focus}`);return{points,relations,lines,tierText:best.tier||info.tier||'未分档'};}
function relationRows(slug,teams){const map=new Map();teams.forEach(t=>(t.chars||[]).forEach(c=>{if(c===slug)return;const item=map.get(c)||{slug:c,name:charName(c),count:0,owned:box.owned.has(c)};item.count++;item.owned=box.owned.has(c);map.set(c,item);}));return [...map.values()].sort((a,b)=>Number(b.owned)-Number(a.owned)||b.count-a.count||a.name.localeCompare(b.name));}
function sparkline(points){if(!points.length)return '<text x="10" y="31" class="spark-empty">暂无趋势</text>';const max=Math.max(1,...points.map(p=>p.value)),xs=points.map((p,i)=>8+i*(204/Math.max(1,points.length-1))),ys=points.map(p=>46-(p.value/max)*36),d=xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');return `<path d="${d}" class="spark-line"/><path d="M8 47H212" class="spark-axis"/>${xs.map((x,i)=>`<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="3.2" class="spark-dot"/>`).join('')}`;}
function showBannerTip(evt,row,ins){const tt=$('bannerTooltip');tt.innerHTML=`<div class="tooltip-grid"><b>角色</b><span>${esc(row.character_name_cn||row.character_name_en||row.character_slug)}</span><b>阶段</b><span>${esc(row.phase_title||'-')}</span><b>定位</b><span>${esc([row.element_cn,row.style_cn,row.role_group_cn].filter(Boolean).join(' · ')||'未知')}</span>${row.icon_source_label?`<b>图源</b><span>${esc(row.icon_source_label)}</span>`:''}<b>分析输入</b><span>${esc(ins.lines.join('；'))}</span></div>`;tt.hidden=false;moveBannerTip(evt);}
function moveBannerTip(evt){const tt=$('bannerTooltip');let x=evt.clientX+16,y=evt.clientY+16;const r=tt.getBoundingClientRect();if(x+r.width+12>innerWidth)x=evt.clientX-r.width-16;if(y+r.height+12>innerHeight)y=evt.clientY-r.height-16;tt.style.left=`${Math.max(12,x)}px`;tt.style.top=`${Math.max(12,y)}px`;}
function initBox(){buttons('boxElementControl',[['all','全部'],...ELEMENTS.map(x=>[x,x])],box.element,v=>{box.element=v;renderBox();});buttons('boxStyleControl',[['all','全部'],...STYLES.map(x=>[x,x])],box.style,v=>{box.style=v;renderBox();});$('boxOwnedSelect').onchange=e=>{box.status=e.target.value;renderBox();};$('boxSearchInput').oninput=e=>{box.search=e.target.value.trim().toLowerCase();renderBox();};$('boxExportBtn').onclick=exportBox;$('boxImportBtn').onclick=()=>$('boxImportInput').click();$('boxImportInput').onchange=importBox;$('boxMarkVisibleBtn').onclick=()=>{filteredRoster().forEach(r=>box.owned.add(r.character_slug));saveBox();renderBox();};$('boxBuildVisibleBtn').onclick=()=>setVisibleBuild(true);$('boxClearBuildVisibleBtn').onclick=()=>setVisibleBuild(false);initBuild();}
function initBuild(){const levels=BUILD_LEVELS.map(v=>`<option value="${v}">${v?`${v}级`:'未录入'}</option>`).join('');$('buildLevel').innerHTML=levels;$('buildEngine').innerHTML=levels;$('buildMindscape').innerHTML=BUILD_MINDSCAPES.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('buildSignature').innerHTML=BUILD_SIGNATURES.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('buildSkill').innerHTML=BUILD_SKILLS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('buildDisc').innerHTML=BUILD_DISCS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('buildLevel').onchange=e=>buildSet('level',Number(e.target.value));$('buildEngine').onchange=e=>buildSet('engine',Number(e.target.value));$('buildMindscape').onchange=e=>buildSet('mindscape',e.target.value==='unset'?'unset':Number(e.target.value));$('buildSignature').onchange=e=>buildSet('signature',e.target.value);$('buildSkill').onchange=e=>buildSet('skills',e.target.value);$('buildDisc').onchange=e=>buildSet('discs',e.target.value);$('buildMaxBtn').onclick=()=>{if(box.buildSlug){box.builds[box.buildSlug]=fullBuild(box.builds[box.buildSlug]||{});box.owned.add(box.buildSlug);saveBox();renderBox();}};$('buildClearBtn').onclick=()=>{delete box.builds[box.buildSlug];saveBox();renderBox();};}
function readBoxRaw(){for(const key of [BOX_KEY,...OLD_BOX_KEYS]){try{const text=localStorage.getItem(key);if(text)return JSON.parse(text);}catch{}}return{};}
function applyBoxRaw(raw){box.owned=new Set((raw.owned||[]).filter(slug=>slug&&slug!=='__codex_test__'));box.builds={};Object.entries(raw.builds||{}).forEach(([slug,build])=>{if(slug)box.builds[slug]=normBuild(build);});box.buildSlug=raw.buildSlug||'';box.saveStatus=raw.fromServer?'本机自动保存':'浏览器缓存';}
function loadBox(){try{applyBoxRaw(readBoxRaw());}catch{box.owned=new Set();box.builds={};box.buildSlug='';box.saveStatus='浏览器缓存';}}
function boxPayload(){const builds={};Object.entries(box.builds||{}).forEach(([slug,build])=>{const normalized=normBuild(build);if(buildRecorded(normalized))builds[slug]=normalized;});return{version:3,updatedAt:new Date().toISOString(),owned:[...box.owned].sort(),buildSlug:box.buildSlug,builds};}
function saveBox(){const payload=boxPayload();localStorage.setItem(BOX_KEY,JSON.stringify(payload));OLD_BOX_KEYS.forEach(k=>localStorage.removeItem(k));box.saveStatus='已保存到浏览器';clearTimeout(boxSaveTimer);boxSaveTimer=setTimeout(()=>saveBoxToServer(payload),180);if(state.page==='box'||state.page==='banner')requestAnimationFrame(()=>{if(state.page==='box')renderBox();else renderBanner();});}
function hasBoxData(raw){return Boolean((raw.owned||[]).filter(slug=>slug&&slug!=='__codex_test__').length||Object.keys(raw.builds||{}).length);}
function boxTime(raw){const t=Date.parse(raw.updatedAt||raw.exportedAt||'');return Number.isFinite(t)?t:0;}
function syncBoxFromServer(){fetch('/api/zzz/box',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error('no api'))).then(server=>{const local=readBoxRaw();server.fromServer=true;const serverWins=Boolean(server.updatedAt)&&boxTime(server)>=boxTime(local);if(serverWins||(hasBoxData(server)&&(!hasBoxData(local)||boxTime(server)>=boxTime(local)))){applyBoxRaw(server);localStorage.setItem(BOX_KEY,JSON.stringify(server));box.saveStatus='本机自动保存';render();}else if(hasBoxData(local)){saveBoxToServer(boxPayload());}else{box.saveStatus='本机自动保存';render();}}).catch(()=>{box.saveStatus='浏览器缓存';if(state.page==='box'||state.page==='banner')render();});}
function saveBoxToServer(payload){fetch('/api/zzz/box',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.ok?r.json():Promise.reject(new Error('save failed'))).then(()=>{box.saveStatus='本机自动保存';if(state.page==='box'||state.page==='banner')render();}).catch(()=>{box.saveStatus='浏览器缓存';if(state.page==='box'||state.page==='banner')render();});}
function normMindscape(value){const n=Number(value);return Number.isInteger(n)&&n>=0&&n<=6?n:'unset'}
function normSignature(value){const text=String(value).toLowerCase();if(value===true||['yes','owned','signature','s1','专武'].includes(text))return 'yes';if(value===false||['no','none','s0','无专武'].includes(text))return 'no';return 'unset'}
function normBuild(b={}){const skills=BUILD_SKILLS.some(x=>x[0]===b.skills)?b.skills:'unset',discs=BUILD_DISCS.some(x=>x[0]===b.discs)?b.discs:'unset',mindscape=normMindscape(b.mindscape??b.cinema??b.cons??b.eidolon),signature=normSignature(b.signature??b.signatureWeapon??b.hasSignature??b.s);return{level:BUILD_LEVELS.includes(Number(b.level))?Number(b.level):0,engine:BUILD_LEVELS.includes(Number(b.engine))?Number(b.engine):0,mindscape,signature,skills,discs};}
function optScore(opts,v){return opts.find(x=>x[0]===v)?.[2]||0}
function buildCoreRecorded(b){return !!(b.level||b.engine||b.skills!=='unset'||b.discs!=='unset')}
function buildConfigRecorded(b){return b.mindscape!=='unset'||b.signature!=='unset'}
function buildRecorded(b){return buildCoreRecorded(b)||buildConfigRecorded(b)}
function buildConfigLabel(b){const build=normBuild(b),m=build.mindscape==='unset'?'M?':`M${build.mindscape}`,s=build.signature==='yes'?'S1':build.signature==='no'?'S0':'S?';return `${m}${s}`}
function signatureText(v){return BUILD_SIGNATURES.find(x=>x[0]===v)?.[1]||'未录入'}
function buildState(slug){const b=normBuild(box.builds[slug]||{}),baseScore=(b.level/60)*.25+(b.engine/60)*.2+optScore(BUILD_SKILLS,b.skills)*.25+optScore(BUILD_DISCS,b.discs)*.3,score=Math.min(1,baseScore+(b.mindscape==='unset'?0:Number(b.mindscape)*.008)+(b.signature==='yes'?.035:0)),coreRecorded=buildCoreRecorded(b),recorded=buildRecorded(b),ready=coreRecorded&&baseScore>=.86&&b.level>=55&&b.engine>=50&&optScore(BUILD_SKILLS,b.skills)>=.84&&optScore(BUILD_DISCS,b.discs)>=.84;return{...b,baseScore,score,coreRecorded,recorded,ready,basePercent:Math.round(baseScore*100),percent:Math.round(score*100),configLabel:buildConfigLabel(b),label:ready?'已成型':coreRecorded&&baseScore>=.72?'可用':coreRecorded?'待练':buildConfigRecorded(b)?'仅配置':'练度未录入'};}
function fullBuild(prev={}){const b=normBuild(prev);return{...b,level:60,engine:60,skills:'max',discs:'great'}}
function setVisibleBuild(value){filteredRoster().forEach(r=>{if(value){box.owned.add(r.character_slug);box.builds[r.character_slug]=fullBuild(box.builds[r.character_slug]||{});}else delete box.builds[r.character_slug];});saveBox();renderBox();}
function boxStatusLabel(){return{all:'全部状态',owned:'已拥有',missing:'未拥有',banner_current:'当期UP',banner_next:'下一期',banner_satellite:'卫星'}[box.status]||box.status}
function matchesBoxStatus(r){if(box.status==='all')return true;if(box.status==='owned')return box.owned.has(r.character_slug);if(box.status==='missing')return !box.owned.has(r.character_slug);if(box.status.startsWith('banner_'))return String(r.banner_statuses||'').split(';').includes(box.status.replace('banner_',''));return true}
function filteredRoster(){const q=box.search;return DATA.rosterRows.filter(r=>(box.element==='all'||r.element_cn===box.element)&&(box.style==='all'||r.style_cn===box.style)&&matchesBoxStatus(r)&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,r.element_cn,r.style_cn,r.banner_phase_titles].some(x=>String(x||'').toLowerCase().includes(q))));}
function renderBox(){const rows=filteredRoster(),owned=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)).length,built=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)&&buildState(r.character_slug).ready).length;renderBuild();$('boxSubtitle').textContent=`展示 ${rows.length}/${DATA.rosterRows.length} 个代理人，已拥有 ${owned}，已成型 ${built}。点「练度」维护等级/音擎/影画/专武/技能/驱动盘`;$('boxBadges').innerHTML=[box.saveStatus||'浏览器缓存',box.element==='all'?'全部属性':box.element,box.style==='all'?'全部特性':box.style,boxStatusLabel(),`成型 ${built}/${owned||0}`].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('boxGrid');grid.innerHTML='';rows.forEach(r=>{const owned=box.owned.has(r.character_slug),bs=buildState(r.character_slug);const bannerTag=String(r.banner_statuses||'').split(';').filter(Boolean)[0];const card=document.createElement('article');card.className=`box-card ${owned?'owned':'missing'} ${box.buildSlug===r.character_slug?'selected':''}`;card.innerHTML=`<button class="build-btn">练度</button><img src="${esc(r.icon_url)}" alt=""><div class="name">${esc(r.character_name_cn||r.character_name_en)}</div><div class="meta">${esc(r.element_cn)} · ${esc(r.style_cn)}${bannerTag?` · ${esc(boxStatusText(bannerTag))}`:''}</div><div class="meta">${owned?`${bs.label}${bs.coreRecorded?' '+bs.basePercent+'%':''} · ${bs.configLabel}`:'未拥有'}</div>`;card.onclick=()=>{owned?box.owned.delete(r.character_slug):box.owned.add(r.character_slug);box.buildSlug=r.character_slug;saveBox();renderBox();};card.querySelector('.build-btn').onclick=e=>{e.stopPropagation();box.owned.add(r.character_slug);box.buildSlug=r.character_slug;saveBox();renderBox();};grid.appendChild(card);});}
function boxStatusText(status){return{current:'当期UP',next:'下一期',satellite:'卫星',previous:'已结束'}[status]||status}
function renderBuild(){const p=$('buildEditor');if(!box.buildSlug||!box.owned.has(box.buildSlug)){p.classList.add('hidden');return;}const r=charInfo(box.buildSlug),bs=buildState(box.buildSlug),b=normBuild(box.builds[box.buildSlug]||{});p.classList.remove('hidden');$('buildIcon').src=r.icon_url;$('buildTitle').textContent=`${charName(box.buildSlug)} · 练度`;$('buildSubtitle').textContent=`${r.element_cn} · ${r.style_cn}`;$('buildLevel').value=b.level;$('buildEngine').value=b.engine;$('buildMindscape').value=String(b.mindscape);$('buildSignature').value=b.signature;$('buildSkill').value=b.skills;$('buildDisc').value=b.discs;$('buildScore').textContent=`${bs.label} · ${bs.coreRecorded?bs.basePercent:0}% · ${bs.configLabel}`;}
function buildSet(k,v){if(!box.buildSlug)return;box.builds[box.buildSlug]={...normBuild(box.builds[box.buildSlug]||{}),[k]:v};box.owned.add(box.buildSlug);saveBox();renderBox();}
function exportBox(){const blob=new Blob([JSON.stringify({...boxPayload(),exportedAt:new Date().toISOString()},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='zzz_box_state.json';a.click();URL.revokeObjectURL(a.href);}
function importBox(e){const file=e.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{const d=JSON.parse(String(reader.result||'{}'));applyBoxRaw(d);box.buildSlug='';saveBox();renderBox();}catch(err){alert(`导入失败：${err.message}`);}finally{e.target.value='';}};reader.readAsText(file);}
function initRec(){buttons('recModeControl',MODES,rec.mode,v=>{rec.mode=v;ensureScope();saveRec();syncRec();renderRec();});ELEMENTS.forEach(el=>{const b=document.createElement('button');b.textContent=el;b.onclick=()=>{const s=elementSet();s.has(el)?s.delete(el):s.add(el);rec.elements[key()]=[...s];saveRec();syncRec();renderRec();};$('recElementControl').appendChild(b);});$('recScopeSelect').onchange=e=>{rec.scope=e.target.value;saveRec();renderRec();};$('recGapSelect').onchange=e=>{rec.gap=e.target.value;saveRec();renderRec();};$('recRiskSelect').onchange=e=>{rec.riskMode=e.target.value;saveRec();renderRec();};$('recLimitSelect').onchange=e=>{rec.limit=e.target.value;saveRec();renderRec();};$('recSearchInput').oninput=e=>{rec.search=e.target.value.trim().toLowerCase();saveRec();renderRec();};ensureScope();}
function loadRec(){try{rec={...rec,...JSON.parse(localStorage.getItem(REC_KEY)||'{}')};}catch{}}
function saveRec(){localStorage.setItem(REC_KEY,JSON.stringify({...rec,updatedAt:new Date().toISOString()}));}
function key(){return `${rec.mode}|${rec.scope}`}
function elementSet(){return new Set(rec.elements?.[key()]||[])}
function scopes(){const map=new Map();DATA.teamTemplates.filter(t=>t.mode===rec.mode).forEach(t=>map.set(t.scope_key,{key:t.scope_key,label:t.scope_label}));return [...map.values()].sort((a,b)=>a.key.localeCompare(b.key));}
function ensureScope(){const ss=scopes();if(ss.length&&!ss.some(s=>s.key===rec.scope))rec.scope=ss[0].key;}
function syncRec(){const ss=scopes();$('recScopeSelect').innerHTML=ss.map(s=>`<option value="${esc(s.key)}">${esc(s.label)}</option>`).join('');$('recScopeSelect').value=rec.scope;$('recGapSelect').value=rec.gap;$('recRiskSelect').value=rec.riskMode;$('recLimitSelect').value=rec.limit||'8';$('recSearchInput').value=rec.search;const s=elementSet();[...$('recElementControl').children].forEach(b=>b.classList.toggle('active',s.has(b.textContent)));}
function tierMeta(slug){return DATA.tierRows.filter(r=>r.character_slug===slug&&r.tier_mode===rec.mode).sort((a,b)=>(TIER_RANK[a.tier]??9)-(TIER_RANK[b.tier]??9))[0]||{}}
function memberRisk(m){const risks=[],tier=tierMeta(m.slug),rank=TIER_RANK[tier.tier]??9,bs=m.build;if(m.owned){if(!bs.coreRecorded)risks.push({text:'练度未录入',penalty:m.core?42:22});else if(bs.baseScore<.68)risks.push({text:`练度待补 ${bs.basePercent}%`,penalty:m.core?70:36,severe:m.core});}if(rank>=5)risks.push({text:`${tier.tier}不建议投入${bs.ready?'（已练，降权）':''}`,penalty:bs.ready?35:90,severe:true});else if(rank>=3)risks.push({text:`${tier.tier}非主流低档${bs.ready?'（已练，降权）':''}`,penalty:bs.ready?25:62,severe:true});else if(rank>=1&&!bs.ready)risks.push({text:`${tier.tier}投入谨慎`,penalty:m.core?32:18});return risks;}
function scoreTeam(t,used=new Set()){const selected=elementSet();const members=t.chars.map(slug=>{const info=charInfo(slug),bs=buildState(slug),core=['crit_dps','anomaly_dps'].includes(info.role_group);return{slug,info,build:bs,owned:box.owned.has(slug),selected:selected.has(info.element_cn),core,conflict:used.has(slug)};});members.forEach(m=>m.risks=memberRisk(m));const owned=members.filter(m=>m.owned).length,ready=members.filter(m=>m.owned&&m.build.ready).length,miss=3-owned,elementHits=members.filter(m=>m.selected).length,coreHits=members.filter(m=>m.core&&m.selected).length,conflictCount=members.filter(m=>m.conflict&&m.owned).length,risks=members.flatMap(m=>m.risks.map(r=>({...r,name:charName(m.slug)})));if(selected.size&&members.some(m=>m.core)&&coreHits===0)risks.push({text:'主C均未命中推荐属性',penalty:145,severe:true});const penalty=rec.riskMode==='off'?0:risks.reduce((s,r)=>s+(r.penalty||0),0);let score=owned*46+members.filter(m=>m.owned).reduce((s,m)=>s+m.build.score*88,0)-miss*72-conflictCount*160+elementHits*12+coreHits*56+Math.min(num(t.app_rate)||0,35)*2.1-penalty;if(t.rank!=null)score+=Math.max(0,130-t.rank)*.4;if(selected.size&&elementHits===0)score-=35;return{template:t,members,ownedCount:owned,readyCount:ready,missingCount:miss,elementHits,coreHits,conflictCount,risks,score,search:[t.phase_name,t.scope_label,t.bangboo,t.bangboo_name,...t.chars,...t.names_cn,...risks.map(r=>r.text)].join(' ').toLowerCase()};}
function rankedFor(mode=rec.mode,scope=rec.scope,used=new Set(),ignoreSearch=false){return DATA.teamTemplates.filter(t=>t.mode===mode&&t.scope_key===scope).map(t=>scoreTeam(t,used)).filter(i=>i.missingCount<=Number(rec.gap)&&(rec.riskMode!=='filter'||!i.risks.length)&&(ignoreSearch||!rec.search||i.search.includes(rec.search))).sort((a,b)=>b.score-a.score||a.conflictCount-b.conflictCount||a.missingCount-b.missingCount||(a.template.rank||9999)-(b.template.rank||9999));}
function ranked(){return rankedFor();}
function templateRecency(t){return String(t.recency_key||t.collect_date||t.phase_ver||'')}
function phaseInfo(){const templates=DATA.teamTemplates.filter(t=>t.mode===rec.mode&&t.scope_key===rec.scope),latest=templates.slice().sort((a,b)=>templateRecency(b).localeCompare(templateRecency(a)))[0];const rows=DATA.phaseInfoRows||[];return rows.find(r=>r.mode===rec.mode&&r.phase_ver===latest?.phase_ver&&r.collect_date===latest?.collect_date)||rows.find(r=>r.mode===rec.mode&&r.phase_ver===latest?.phase_ver)||rows.filter(r=>r.mode===rec.mode).sort((a,b)=>String(b.phase_ver||b.collect_date).localeCompare(String(a.phase_ver||a.collect_date)))[0]||{};}
function phaseStatusLabel(status){return status==='expired'?'已过期':status==='future'?'未开始':status==='current'?'当前周期':'日期未知'}
function renderPhaseInfo(){const p=phaseInfo();$('phaseTitle').textContent=`${p.mode_cn||MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode} · ${p.phase_name_cn||p.phase_name||p.phase_ver||'当期数据'}`;const range=(p.start_date||p.end_date)?`${p.start_date||'未知'} 至 ${p.end_date||'未知'}`:'周期源未提供',status=p.phase_status||'unknown';$('phaseDates').textContent=`${phaseStatusLabel(status)} · ${range} · 采样 ${p.collect_date||'未知'}`;const expired=status==='expired'?`本地最新 ${p.mode_cn||rec.mode} 数据已于 ${p.end_date||'上一周期'} 结束；请和我对话手动更新至少活动范围，再把当前推荐当作正式参考。`:'';$('phaseText').textContent=expired||p.mechanic_text||'推荐限定当前同模式、同关卡数据源。';}
function renderRec(){ensureScope();syncRec();renderPhaseInfo();const rows=ranked().slice(0,Number(rec.limit)||8),sel=[...elementSet()],templates=DATA.teamTemplates.filter(t=>t.mode===rec.mode&&t.scope_key===rec.scope);$('recTitle').textContent=`${MODES.find(x=>x[0]===rec.mode)?.[1]} · ${scopes().find(s=>s.key===rec.scope)?.label||rec.scope}`;$('recSubtitle').textContent=`当前同模式同关卡模板 ${templates.length} 队`;const riskLabel=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';$('recBadges').innerHTML=[sel.length?sel.join(' / '):'未选属性',`缺口 ≤ ${rec.gap}`,riskLabel,rec.riskMode==='off'?'T档不提醒':'T1及以下提醒',`Box ${box.owned.size}`].map(x=>`<span>${esc(x)}</span>`).join('');const list=$('recList');list.innerHTML='';if(!rows.length){list.innerHTML='<div class="empty">当前筛选没有可展示队伍</div>';renderRecSlate();return;}rows.forEach((item,i)=>list.appendChild(recCard(item,i+1)));renderRecSlate();}
function recCard(item,i){const t=item.template,card=document.createElement('article');card.className=`rec-card ${item.risks.length&&rec.riskMode!=='off'?'risky':''}`;card.innerHTML=`<div class="rec-head"><div><h3>${i}. ${esc(t.names_cn.join(' / '))}</h3><div class="rec-meta">${esc(t.scope_label)} · Rank ${t.rank??'-'} · ${pct(t.app_rate)} · 邦布 ${esc(bangbooName(t.bangboo,t.bangboo_name))}</div></div><div class="score">${Math.round(item.score)}<br><span>${item.ownedCount}/3</span></div></div><div class="rec-team">${item.members.map(m=>memberHtml(m)).join('')}</div><div class="tags"><span class="${item.missingCount?'warn':''}">${item.missingCount?`缺 ${item.missingCount}`:'可成队'}</span>${item.ownedCount?`<span class="${item.readyCount<item.ownedCount?'warn':''}">练度 ${item.readyCount}/${item.ownedCount}</span>`:''}<span>属性命中 ${item.elementHits}</span>${item.conflictCount?`<span class="warn">多队冲突 ${item.conflictCount}</span>`:''}${item.risks.length&&rec.riskMode!=='off'?`<span class="${item.risks.some(r=>r.severe)?'danger':'warn'}">风险 ${item.risks.length}</span>`:''}</div>${riskHtml(item)}`;return card;}
function memberHtml(m){const risky=(m.risks.length&&rec.riskMode!=='off')||m.conflict;return `<div class="rec-member ${m.owned?'owned':'missing'} ${risky?'risky':''}"><img src="${esc(m.info.icon_url)}" alt=""><div class="name">${esc(charName(m.slug))}</div><div class="meta">${esc(m.info.element_cn)} · ${esc(m.info.style_cn)}${m.owned?` · ${esc(m.build.label)} · ${esc(m.build.configLabel)}`:''}${m.conflict?' · 冲突':''}</div></div>`;}
function riskHtml(item){if(!item.risks.length||rec.riskMode==='off')return '';return `<div class="risk-note">${esc(item.risks.slice(0,4).map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；'))}${item.risks.length>4?'；...':''}</div>`;}
function renderRecSlate(){const list=$('recSlateList'),scopeList=scopes().filter(s=>s.key!=='all');list.innerHTML='';const used=new Set(),chosen=[];scopeList.forEach(scope=>{const item=rankedFor(rec.mode,scope.key,used,true).find(x=>x.conflictCount===0)||rankedFor(rec.mode,scope.key,used,true)[0];if(item){item.members.filter(m=>m.owned).forEach(m=>used.add(m.slug));}chosen.push({scope,item});});$('recSlateSubtitle').textContent=`${chosen.filter(x=>x.item).length}/${scopeList.length} 队 · 尽量不复用已拥有角色`;if(!chosen.length){list.innerHTML='<div class="empty">暂无当前模式关卡模板</div>';return;}chosen.forEach(({scope,item})=>{const card=document.createElement('div');card.className=`rec-slate-card ${item?.risks?.length&&rec.riskMode!=='off'?'risky':''}`;if(!item){card.innerHTML=`<h3>${esc(scope.label)}</h3><div class="rec-meta">没有符合缺口限制的队伍</div>`;}else{card.innerHTML=`<h3>${esc(scope.label)} · ${Math.round(item.score)} · ${item.ownedCount}/3</h3><div class="rec-slate-team">${item.members.map(m=>`<img class="${m.owned?'':'missing'} ${m.risks.length&&rec.riskMode!=='off'?'risky':''}" src="${esc(m.info.icon_url)}" title="${esc(charName(m.slug))}" alt="">`).join('')}</div>${riskHtml(item)}`;}list.appendChild(card);});}
"""
