from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import MODE_CN
from .normalize import normalize_character_id, parse_date

SOURCE_URL = "https://www.prydwen.gg/star-rail/tier-list"

RATING_TO_TIER = {
    11: "T0",
    10: "T0.5",
    9: "T1",
    8: "T1.5",
    7: "T2",
    6: "T3",
    5: "T4",
    4: "T5",
}

MODE_FIELDS = {
    "moc": ("moc_rating", "moc_special_rating", "moc_tags", "moc_marks"),
    "pf": ("pure_rating", "pure_special_rating", "pure_tags", "pure_marks"),
    "as": ("apo_rating", "apo_special_rating", "apo_tags", "apo_marks"),
}

CATEGORY_TO_ROLE = {
    "DPS": ("DPS", "main_dps", "主C"),
    "Specialist": ("Support DPS", "sub_dps", "副C"),
    "Amplifier": ("Amplifier", "support", "辅助"),
    "Sustain": ("Sustain", "sustain", "生存位"),
}

T0_TO_T2 = {"T0", "T0.5", "T1", "T1.5", "T2"}


class PrydwenTierScraper:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def fetch_html(self) -> str:
        request = urllib.request.Request(
            SOURCE_URL,
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


def fetch_and_parse_prydwen_tier(
    raw_dir: Path,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    try:
        html_text = PrydwenTierScraper().fetch_html()
    except Exception as exc:
        cached = raw_dir / "tier-list_latest.html"
        if cached.exists():
            warnings.append(f"Prydwen tier fetch failed; using cached HTML: {exc}")
            html_text = cached.read_text(encoding="utf-8")
        else:
            warnings.append(f"Prydwen tier fetch failed: {exc}")
            return [], []

    decoded = decode_prydwen_payload(html_text)
    last_updated = extract_last_updated(decoded)
    snapshot_id = _snapshot_id(last_updated)
    raw_dir.joinpath("tier-list_latest.html").write_text(html_text, encoding="utf-8")
    if snapshot_id:
        raw_dir.joinpath(f"tier-list_{snapshot_id}.html").write_text(html_text, encoding="utf-8")

    fetched_at = datetime.now().isoformat(timespec="seconds")
    characters = extract_characters(decoded)
    tier_rows = build_tier_rows(characters, last_updated, snapshot_id, fetched_at)
    changelog_rows = extract_changelog(decoded)
    if not tier_rows:
        warnings.append("Prydwen tier parse warning: no tier rows extracted")
    if not changelog_rows:
        warnings.append("Prydwen tier parse warning: no changelog rows extracted")
    return tier_rows, changelog_rows


def decode_prydwen_payload(html_text: str) -> str:
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
    characters, _ = json.JSONDecoder().raw_decode(decoded[start:])
    return characters if isinstance(characters, list) else []


def build_tier_rows(
    characters: list[dict[str, Any]],
    tier_updated_at: str,
    snapshot_id: str,
    fetched_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tier_updated_date = _date_from_prydwen_date(tier_updated_at)
    for character in characters:
        slug = normalize_character_id(character.get("slug"))
        if not slug:
            continue
        for rating in character.get("tierRatings") or []:
            category = rating.get("category") or ""
            prydwen_role, role_group, role_group_cn = CATEGORY_TO_ROLE.get(
                category,
                (category, "unknown", "未知"),
            )
            for mode, (rating_key, special_key, tags_key, marks_key) in MODE_FIELDS.items():
                raw_rating = rating.get(rating_key)
                tier = RATING_TO_TIER.get(raw_rating, "")
                rows.append(
                    {
                        "tier_snapshot_id": snapshot_id,
                        "fetched_at": fetched_at,
                        "tier_updated_at": tier_updated_at,
                        "tier_updated_date": tier_updated_date,
                        "tier_mode": mode,
                        "tier_mode_cn": MODE_CN.get(mode, mode),
                        "character_slug": slug,
                        "character_name_en": character.get("name") or "",
                        "character_name_cn": "",
                        "prydwen_category": category,
                        "prydwen_role": prydwen_role,
                        "role_group": role_group,
                        "role_group_cn": role_group_cn,
                        "tier": tier,
                        "rating": raw_rating,
                        "special_rating": rating.get(special_key),
                        "tags": rating.get(tags_key) or rating.get("tags") or "",
                        "marks": rating.get(marks_key) or "",
                        "is_new": rating.get("is_new") or character.get("isNew") or "",
                        "default_role": character.get("defaultRole") or "",
                        "element": character.get("element") or "",
                        "path": character.get("path") or "",
                        "rarity": character.get("rarity") or "",
                        "icon_url": character.get("smallImage") or "",
                        "source_url": SOURCE_URL,
                    }
                )
    return rows


def extract_changelog(decoded: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"<h6[^>]*>(\d{2}/[A-Za-z]{3}/\d{4})</h6>", decoded))
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(decoded)
        chunk = decoded[start:end]
        slugs = sorted(set(re.findall(r'data-slug="([^"]+)"', chunk)))
        text = _strip_html(chunk)
        if not text:
            continue
        rows.append(
            {
                "changelog_date": _date_from_prydwen_date(match.group(1)),
                "source_url": SOURCE_URL,
                "character_slugs": ";".join(slugs),
                "text": text,
            }
        )
    return rows


def merge_tier_history(
    existing_path: Path,
    current_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = _read_csv(existing_path)
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in existing + current_rows:
        key = (
            str(row.get("tier_snapshot_id", "")),
            str(row.get("tier_mode", "")),
            str(row.get("character_slug", "")),
            str(row.get("prydwen_category", "")),
        )
        merged[key] = row
    return sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("tier_updated_date", "")),
            str(row.get("tier_mode", "")),
            str(row.get("role_group", "")),
            str(row.get("tier", "")),
            str(row.get("character_slug", "")),
        ),
    )


def merge_changelog_history(
    existing_path: Path,
    current_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = _read_csv(existing_path)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing + current_rows:
        digest = hashlib.sha1(str(row.get("text", "")).encode("utf-8")).hexdigest()
        key = (str(row.get("changelog_date", "")), digest)
        merged[key] = row
    return sorted(merged.values(), key=lambda row: str(row.get("changelog_date", "")), reverse=True)


def build_tier_usage_trend(
    tier_rows: list[dict[str, Any]],
    character_usage_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    usage_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for usage in character_usage_rows:
        if usage.get("sub_mode") not in {"all", "all_bosses"}:
            continue
        key = (str(usage.get("mode", "")), str(usage.get("character_slug", "")))
        usage_by_key.setdefault(key, []).append(usage)

    output: list[dict[str, Any]] = []
    for tier in tier_rows:
        if tier.get("tier") not in T0_TO_T2:
            continue
        key = (str(tier.get("tier_mode", "")), str(tier.get("character_slug", "")))
        for usage in sorted(usage_by_key.get(key, []), key=lambda row: str(row.get("collect_date", ""))):
            output.append(
                {
                    "tier_snapshot_id": tier.get("tier_snapshot_id", ""),
                    "tier_updated_date": tier.get("tier_updated_date", ""),
                    "tier_mode": tier.get("tier_mode", ""),
                    "tier_mode_cn": tier.get("tier_mode_cn", ""),
                    "character_slug": tier.get("character_slug", ""),
                    "character_name_en": tier.get("character_name_en", ""),
                    "character_name_cn": tier.get("character_name_cn", ""),
                    "prydwen_role": tier.get("prydwen_role", ""),
                    "role_group": tier.get("role_group", ""),
                    "role_group_cn": tier.get("role_group_cn", ""),
                    "tier": tier.get("tier", ""),
                    "rating": tier.get("rating", ""),
                    "tags": tier.get("tags", ""),
                    "marks": tier.get("marks", ""),
                    "collect_date": usage.get("collect_date", ""),
                    "phase_ver": usage.get("phase_ver", ""),
                    "phase_name": usage.get("phase_name", ""),
                    "app_rate": usage.get("app_rate", ""),
                    "avg_round": usage.get("avg_round", ""),
                    "quality_flag": usage.get("quality_flag", ""),
                    "icon_url": tier.get("icon_url", ""),
                }
            )
    return output


def generate_tier_usage_charts(
    trend_rows: list[dict[str, Any]],
    charts_dir: Path,
) -> list[dict[str, Any]]:
    charts_dir.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    for mode in ("moc", "pf", "as"):
        for role_group, role_group_cn in (
            ("main_dps", "主C"),
            ("sub_dps", "副C"),
            ("support", "辅助"),
            ("sustain", "生存位"),
        ):
            rows = [
                row
                for row in trend_rows
                if row.get("tier_mode") == mode and row.get("role_group") == role_group
            ]
            if not rows:
                continue
            filename = f"{mode}_{role_group}_t0_t2_usage.svg"
            chart_path = charts_dir / filename
            chart_path.write_text(_render_svg_chart(rows), encoding="utf-8")
            index_rows.append(
                {
                    "tier_mode": mode,
                    "tier_mode_cn": MODE_CN.get(mode, mode),
                    "role_group": role_group,
                    "role_group_cn": role_group_cn,
                    "chart_file": str(chart_path),
                    "series_count": len({row["character_slug"] for row in rows}),
                    "point_count": len(rows),
                }
            )
    return index_rows


def _render_svg_chart(rows: list[dict[str, Any]]) -> str:
    dates = sorted({str(row.get("collect_date", "")) for row in rows if row.get("collect_date")})
    series: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        slug = str(row.get("character_slug", ""))
        series.setdefault(slug, []).append(row)
        meta[slug] = row

    ordered_slugs = sorted(
        series,
        key=lambda slug: (
            -float(series[slug][-1].get("app_rate") or 0),
            str(meta[slug].get("tier", "")),
            slug,
        ),
    )
    max_value = max([float(row.get("app_rate") or 0) for row in rows] + [10.0])
    max_value = min(100.0, max_value * 1.12)
    width = 1180
    legend_width = 330
    chart_left = 74
    chart_top = 70
    chart_width = width - legend_width - chart_left - 30
    chart_height = 360
    height = max(520, chart_top + chart_height + 70, 110 + 22 * len(ordered_slugs))
    colors = [
        "#2563eb",
        "#dc2626",
        "#16a34a",
        "#9333ea",
        "#ea580c",
        "#0891b2",
        "#be123c",
        "#4f46e5",
        "#65a30d",
        "#a16207",
        "#0f766e",
        "#7c3aed",
    ]
    mode_cn = rows[0].get("tier_mode_cn", "")
    role_cn = rows[0].get("role_group_cn", "")
    title = f"Prydwen T0-T2 {role_cn} - {mode_cn} 近半年出场率"

    def x(date: str) -> float:
        if len(dates) <= 1:
            return chart_left + chart_width / 2
        return chart_left + chart_width * dates.index(date) / (len(dates) - 1)

    def y(value: float) -> float:
        return chart_top + chart_height - chart_height * value / max_value

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{chart_left}" y="34" font-size="24" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<text x="{chart_left}" y="56" font-size="13" fill="#6b7280">T档来自 Prydwen 当前榜；出场率来自本地 MocStats long table，数值单位为 %。</text>',
    ]
    for tick in range(0, 6):
        value = max_value * tick / 5
        yy = y(value)
        parts.append(f'<line x1="{chart_left}" y1="{yy:.1f}" x2="{chart_left + chart_width}" y2="{yy:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{chart_left - 10}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">{value:.0f}</text>')
    parts.append(f'<line x1="{chart_left}" y1="{chart_top}" x2="{chart_left}" y2="{chart_top + chart_height}" stroke="#374151"/>')
    parts.append(f'<line x1="{chart_left}" y1="{chart_top + chart_height}" x2="{chart_left + chart_width}" y2="{chart_top + chart_height}" stroke="#374151"/>')
    for date in dates:
        xx = x(date)
        parts.append(f'<text x="{xx:.1f}" y="{chart_top + chart_height + 22}" text-anchor="middle" font-size="11" fill="#374151">{html.escape(date[5:])}</text>')

    for idx, slug in enumerate(ordered_slugs):
        color = colors[idx % len(colors)]
        points = []
        row_by_date = {str(row.get("collect_date", "")): row for row in series[slug]}
        for date in dates:
            row = row_by_date.get(date)
            if not row:
                continue
            points.append((x(date), y(float(row.get("app_rate") or 0))))
        point_text = " ".join(f"{xx:.1f},{yy:.1f}" for xx, yy in points)
        parts.append(f'<polyline points="{point_text}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        for xx, yy in points:
            parts.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="2.8" fill="{color}"/>')
        legend_y = 86 + idx * 22
        label = f"{meta[slug].get('character_name_cn') or slug} {meta[slug].get('tier')}"
        parts.append(f'<line x1="{chart_left + chart_width + 36}" y1="{legend_y - 4}" x2="{chart_left + chart_width + 58}" y2="{legend_y - 4}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{chart_left + chart_width + 66}" y="{legend_y}" font-size="12" fill="#111827">{html.escape(label)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _strip_html(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.DOTALL)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("â", "↑").replace("â", "↓")
    return re.sub(r"\s+", " ", value).strip()


def _snapshot_id(last_updated: str) -> str:
    return _date_from_prydwen_date(last_updated).replace("-", "")


def _date_from_prydwen_date(value: str) -> str:
    text = str(value or "").strip()
    for fmt in ("%d/%B/%Y", "%d/%b/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return parse_date(text)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
