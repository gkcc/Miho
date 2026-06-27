#!/usr/bin/env python
"""Render a local HTML review page for an official MiYouShe export-image parse result."""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "parsed"

REVIEW_REGION_NAMES = (
    "header",
    "character_card",
    "core_stats",
    "skill_levels",
    "equipment",
    "drive_disc_1",
    "drive_disc_2",
    "drive_disc_3",
    "drive_disc_4",
    "drive_disc_5",
    "drive_disc_6",
)

REGION_COLORS = {
    "header": "#4f46e5",
    "character_card": "#0ea5e9",
    "core_stats": "#16a34a",
    "skill_levels": "#f59e0b",
    "equipment": "#db2777",
    "drive_disc_1": "#dc2626",
    "drive_disc_2": "#9333ea",
    "drive_disc_3": "#0891b2",
    "drive_disc_4": "#65a30d",
    "drive_disc_5": "#ea580c",
    "drive_disc_6": "#475569",
}

STAT_FIELDS = (
    "hp",
    "atk",
    "def",
    "impact",
    "crit_rate",
    "crit_dmg",
    "anomaly_mastery",
    "anomaly_proficiency",
    "pen",
    "energy_regen",
    "physical_dmg_bonus",
)


class ReviewError(RuntimeError):
    pass


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load_image_dependency() -> tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ReviewError("Missing Pillow. Install it with: python -m pip install pillow") from exc
    return Image, ImageDraw, ImageFont


def load_parsed_json(json_path: Path) -> dict[str, Any]:
    if not json_path.exists():
        raise ReviewError(f"Parsed JSON does not exist: {json_path}")
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewError(f"Parsed JSON is invalid: {json_path}. Details: {exc}") from exc


def resolve_output_dir(output_dir: str | None, json_path: Path) -> Path:
    if output_dir:
        path = Path(output_dir).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return json_path.parent if json_path.parent else DEFAULT_OUTPUT_DIR


def resolve_image_path(parsed: dict[str, Any], override: str | None) -> Path:
    raw = override or parsed.get("metadata", {}).get("input_image")
    if not raw:
        raise ReviewError("Original image path is missing. Pass --image to render the review page.")
    image_path = Path(str(raw)).expanduser()
    if not image_path.is_absolute():
        image_path = PROJECT_ROOT / image_path
    image_path = image_path.resolve()
    if not image_path.exists():
        raise ReviewError(f"Original image does not exist: {image_path}. Pass --image if metadata.input_image is redacted or moved.")
    if not image_path.is_file():
        raise ReviewError(f"Original image path is not a file: {image_path}")
    return image_path


def file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def rel_or_abs(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def region_box(region: dict[str, Any]) -> tuple[int, int, int, int] | None:
    box = region.get("box", {})
    try:
        left = int(box.get("left", 0))
        top = int(box.get("top", 0))
        right = int(box.get("right", left + int(box.get("width", 0))))
        bottom = int(box.get("bottom", top + int(box.get("height", 0))))
    except (TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    clean = color.lstrip("#")
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def render_overlay(parsed: dict[str, Any], image_path: Path, overlay_path: Path) -> Path:
    Image, ImageDraw, ImageFont = load_image_dependency()
    image = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    regions = {
        str(region.get("name")): region
        for region in parsed.get("layout_regions", [])
        if str(region.get("name")) in REVIEW_REGION_NAMES
    }

    for name in REVIEW_REGION_NAMES:
        region = regions.get(name)
        if not region:
            continue
        box = region_box(region)
        if not box:
            continue
        color = REGION_COLORS.get(name, "#0f172a")
        rgb = hex_to_rgb(color)
        left, top, right, bottom = box
        draw.rectangle((left, top, right, bottom), outline=rgb + (255,), width=4)
        draw.rectangle((left, top, right, bottom), fill=rgb + (22,))
        label = name
        text_box = draw.textbbox((left + 5, top + 5), label, font=font)
        padding = 4
        draw.rectangle(
            (
                text_box[0] - padding,
                text_box[1] - padding,
                text_box[2] + padding,
                text_box[3] + padding,
            ),
            fill=rgb + (230,),
        )
        draw.text((left + 5, top + 5), label, fill=(255, 255, 255, 255), font=font)

    composed = Image.alpha_composite(image, overlay).convert("RGB")
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    composed.save(overlay_path)
    image.close()
    return overlay_path


def is_field(value: Any) -> bool:
    return isinstance(value, dict) and {"value", "uncertain", "evidence", "source_region"}.issubset(value.keys())


def field_value(field: Any) -> Any:
    return field.get("value") if is_field(field) else None


def field_status(field: Any) -> str:
    value = field_value(field)
    if value in (None, "", []):
        return "missing"
    if bool(field.get("uncertain")):
        return "uncertain"
    return "ok"


def format_value(value: Any) -> str:
    if value in (None, ""):
        return "null"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(isinstance(item, dict) for item in value):
            parts = []
            for item in value:
                stat = item.get("stat")
                stat_value = item.get("value")
                if stat_value in (None, ""):
                    parts.append(str(stat))
                else:
                    parts.append(f"{stat}: {stat_value}")
            return "；".join(parts)
        return " / ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_field(label: str, field: Any, path: str | None = None) -> str:
    status = field_status(field)
    value = format_value(field_value(field))
    source = field.get("source_region") if is_field(field) else None
    uncertainty = "uncertain=true" if is_field(field) and field.get("uncertain") else "uncertain=false"
    path_html = f"<span class=\"path\">{escape(path)}</span>" if path else ""
    source_html = f"<span class=\"source\">{escape(source)}</span>" if source else ""
    return (
        f"<div class=\"field field-{status}\">"
        f"<div class=\"field-main\"><span class=\"field-label\">{escape(label)}</span>{path_html}</div>"
        f"<div class=\"field-value\">{escape(value)}</div>"
        f"<div class=\"field-meta\">{escape(uncertainty)} {source_html}</div>"
        "</div>"
    )


def render_card(title: str, body: str, subtitle: str = "") -> str:
    subtitle_html = f"<p class=\"card-subtitle\">{escape(subtitle)}</p>" if subtitle else ""
    return f"<section class=\"card\"><h2>{escape(title)}</h2>{subtitle_html}<div class=\"card-body\">{body}</div></section>"


def iter_fields(value: Any, prefix: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    if is_field(value):
        yield prefix, value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from iter_fields(item, next_prefix)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            label = item.get("slot", index + 1) if isinstance(item, dict) else index + 1
            next_prefix = f"{prefix}[{label}]"
            yield from iter_fields(item, next_prefix)


def render_character_card(draft: dict[str, Any]) -> str:
    character = draft.get("character", {})
    body = "".join(
        [
            render_field("name", character.get("name"), "character.name"),
            render_field("level", character.get("level"), "character.level"),
            render_field("rank", character.get("rank"), "character.rank"),
        ]
    )
    return render_card("角色卡", body)


def render_stats_card(draft: dict[str, Any]) -> str:
    stats = draft.get("stats", {})
    body = "".join(render_field(name, stats.get(name), f"stats.{name}") for name in STAT_FIELDS)
    return render_card("属性卡", body)


def render_skills_card(draft: dict[str, Any]) -> str:
    skill_levels = draft.get("skill_levels", [])
    body = ""
    for index in range(6):
        item = skill_levels[index] if index < len(skill_levels) and isinstance(skill_levels[index], dict) else {}
        body += render_field(f"skill {index + 1}", item.get("level"), f"skill_levels[{index + 1}].level")
    return render_card("技能卡", body)


def render_equipment_card(draft: dict[str, Any]) -> str:
    equipment = draft.get("equipment", {})
    body = "".join(
        [
            render_field("name", equipment.get("name"), "equipment.name"),
            render_field("level", equipment.get("level"), "equipment.level"),
            render_field("rank", equipment.get("rank"), "equipment.rank"),
        ]
    )
    return render_card("音擎卡", body)


def render_drive_discs_card(draft: dict[str, Any]) -> str:
    discs = draft.get("drive_discs", [])
    disc_html = ""
    for slot in range(1, 7):
        disc = next((item for item in discs if isinstance(item, dict) and item.get("slot") == slot), {})
        body = "".join(
            [
                f"<div class=\"slot-label\">drive_disc_{slot}</div>",
                render_field("slot", {"value": slot, "uncertain": False, "evidence": [], "source_region": f"drive_disc_{slot}"}),
                render_field("set_name", disc.get("set_name"), f"drive_discs[{slot}].set_name"),
                render_field("level", disc.get("level"), f"drive_discs[{slot}].level"),
                render_field("main_stat", disc.get("main_stat"), f"drive_discs[{slot}].main_stat"),
                render_field("sub_stats", disc.get("sub_stats"), f"drive_discs[{slot}].sub_stats"),
            ]
        )
        disc_html += f"<div class=\"mini-card\">{body}</div>"
    return render_card("驱动盘卡", f"<div class=\"disc-grid\">{disc_html}</div>")


def render_missing_card(coverage: dict[str, Any]) -> str:
    missing = coverage.get("missing_fields", [])
    if not missing:
        body = "<div class=\"empty-state\">无缺失字段</div>"
    else:
        body = "".join(f"<div class=\"pill pill-missing\">{escape(item)}</div>" for item in missing)
    return render_card("缺失字段卡", body, "来自 coverage_summary.missing_fields")


def render_coverage_card(coverage: dict[str, Any]) -> str:
    def count_or_list(name: str) -> str:
        values = coverage.get(name, [])
        if isinstance(values, list):
            return str(len(values))
        return str(values)

    body = "".join(
        [
            render_field(
                "coverage_level",
                {
                    "value": coverage.get("coverage_level"),
                    "uncertain": coverage.get("coverage_level") not in {"high", "medium"},
                    "evidence": [],
                    "source_region": "coverage_summary",
                },
                "coverage_summary.coverage_level",
            ),
            render_field(
                "matched_fields",
                {
                    "value": count_or_list("matched_fields"),
                    "uncertain": False,
                    "evidence": [],
                    "source_region": "coverage_summary",
                },
                "coverage_summary.matched_fields",
            ),
            render_field(
                "missing_fields",
                {
                    "value": count_or_list("missing_fields"),
                    "uncertain": bool(coverage.get("missing_fields")),
                    "evidence": [],
                    "source_region": "coverage_summary",
                },
                "coverage_summary.missing_fields",
            ),
            render_field(
                "numeric_fields_detected",
                {
                    "value": count_or_list("numeric_fields_detected"),
                    "uncertain": False,
                    "evidence": [],
                    "source_region": "coverage_summary",
                },
                "coverage_summary.numeric_fields_detected",
            ),
            render_field(
                "chinese_fields_detected",
                {
                    "value": count_or_list("chinese_fields_detected"),
                    "uncertain": False,
                    "evidence": [],
                    "source_region": "coverage_summary",
                },
                "coverage_summary.chinese_fields_detected",
            ),
            render_field(
                "recommendation",
                {
                    "value": coverage.get("recommendation"),
                    "uncertain": False,
                    "evidence": [],
                    "source_region": "coverage_summary",
                },
                "coverage_summary.recommendation",
            ),
        ]
    )
    return render_card("coverage_summary", body)


def render_uncertain_card(draft: dict[str, Any]) -> str:
    uncertain = [(path, field) for path, field in iter_fields(draft) if field.get("uncertain")]
    if not uncertain:
        body = "<div class=\"empty-state\">无 uncertain=true 字段</div>"
    else:
        body = "".join(render_field(path, field, path) for path, field in uncertain)
    return render_card("不确定字段卡", body, "所有 uncertain=true 的字段")


def render_region_legend(parsed: dict[str, Any]) -> str:
    available = {str(region.get("name")) for region in parsed.get("layout_regions", [])}
    items = []
    for name in REVIEW_REGION_NAMES:
        status = "available" if name in available else "missing"
        color = REGION_COLORS.get(name, "#0f172a")
        items.append(
            f"<div class=\"legend-item legend-{status}\">"
            f"<span class=\"legend-swatch\" style=\"background:{escape(color)}\"></span>"
            f"<span>{escape(name)}</span>"
            "</div>"
        )
    return "<div class=\"legend\">" + "".join(items) + "</div>"


def render_html(parsed: dict[str, Any], image_path: Path, overlay_path: Path, html_path: Path) -> str:
    meta = parsed.get("metadata", {})
    coverage = parsed.get("coverage_summary", {})
    draft = parsed.get("extracted_draft", {})
    image_info = parsed.get("image", {})

    card_html = "".join(
        [
            render_character_card(draft),
            render_stats_card(draft),
            render_skills_card(draft),
            render_equipment_card(draft),
            render_drive_discs_card(draft),
            render_coverage_card(coverage),
            render_missing_card(coverage),
            render_uncertain_card(draft),
        ]
    )

    original_src = file_uri(image_path)
    overlay_src = overlay_path.name
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>米游社官方分享图解析验收</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #6b7280;
      --line: #dbe1ea;
      --green: #147a42;
      --green-bg: #e7f7ee;
      --yellow: #93640c;
      --yellow-bg: #fff5d6;
      --red: #b42318;
      --red-bg: #ffe9e6;
      --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      line-height: 1.5;
    }}
    header {{
      padding: 24px 28px 14px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    h1 {{ margin: 0 0 12px; font-size: 26px; }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }}
    .meta-item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #fbfcff;
      min-width: 0;
    }}
    .meta-label {{ color: var(--muted); font-size: 12px; }}
    .meta-value {{ font-weight: 700; overflow-wrap: anywhere; }}
    .meta-wide {{ grid-column: span 3; }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(420px, 48vw) minmax(420px, 1fr);
      gap: 18px;
      padding: 18px;
      align-items: start;
    }}
    .left-column, .right-column {{
      display: grid;
      gap: 16px;
    }}
    .image-card, .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .image-card h2, .card h2 {{
      margin: 0;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      font-size: 18px;
    }}
    .image-card img {{
      display: block;
      width: 100%;
      height: auto;
      background: #eef2f7;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 14px;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 8px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fbfcff;
      font-size: 12px;
      font-weight: 700;
    }}
    .legend-missing {{ opacity: 0.45; }}
    .legend-swatch {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    .card-body {{ padding: 14px; display: grid; gap: 10px; }}
    .card-subtitle {{ margin: 10px 16px 0; color: var(--muted); font-size: 13px; }}
    .field {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 5px;
      min-width: 0;
    }}
    .field-ok {{ border-color: #a7e0bd; background: var(--green-bg); }}
    .field-uncertain {{ border-color: #f4d071; background: var(--yellow-bg); }}
    .field-missing {{ border-color: #ffb4ac; background: var(--red-bg); }}
    .field-main {{
      display: flex;
      gap: 8px;
      align-items: baseline;
      justify-content: space-between;
      min-width: 0;
    }}
    .field-label {{ font-weight: 800; }}
    .path, .source, .field-meta {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .field-value {{
      font-size: 16px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }}
    .field-ok .field-value {{ color: var(--green); }}
    .field-uncertain .field-value {{ color: var(--yellow); }}
    .field-missing .field-value {{ color: var(--red); }}
    .disc-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .mini-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 8px;
      background: #fbfcff;
    }}
    .slot-label {{
      font-size: 15px;
      font-weight: 900;
      letter-spacing: 0;
      color: #243047;
    }}
    .pill {{
      display: inline-flex;
      width: fit-content;
      padding: 7px 10px;
      margin: 0 6px 6px 0;
      border-radius: 999px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }}
    .pill-missing {{ background: var(--red-bg); color: var(--red); border: 1px solid #ffb4ac; }}
    .empty-state {{
      padding: 12px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      background: #fbfcff;
    }}
    .recommendation {{
      padding: 12px 16px;
      background: #f0f7ff;
      border-top: 1px solid var(--line);
      color: #1d4f8f;
      font-weight: 700;
    }}
    @media (max-width: 1100px) {{
      .meta-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .meta-wide {{ grid-column: span 2; }}
      .layout {{ grid-template-columns: 1fr; }}
      .disc-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>米游社官方分享图解析验收</h1>
    <div class="meta-grid">
      <div class="meta-item meta-wide"><div class="meta-label">输入图片路径</div><div class="meta-value">{escape(str(image_path))}</div></div>
      <div class="meta-item"><div class="meta-label">OCR 引擎</div><div class="meta-value">{escape(meta.get("ocr_engine"))}</div></div>
      <div class="meta-item"><div class="meta-label">游戏</div><div class="meta-value">{escape(meta.get("game"))}</div></div>
      <div class="meta-item"><div class="meta-label">布局</div><div class="meta-value">{escape(meta.get("layout"))}</div></div>
      <div class="meta-item"><div class="meta-label">coverage_level</div><div class="meta-value">{escape(coverage.get("coverage_level"))}</div></div>
      <div class="meta-item"><div class="meta-label">图片尺寸</div><div class="meta-value">{escape(image_info.get("width"))} x {escape(image_info.get("height"))}</div></div>
      <div class="meta-item meta-wide"><div class="meta-label">recommendation</div><div class="meta-value">{escape(coverage.get("recommendation"))}</div></div>
      <div class="meta-item"><div class="meta-label">生成时间</div><div class="meta-value">{escape(created_at)}</div></div>
    </div>
  </header>
  <main class="layout">
    <aside class="left-column">
      <section class="image-card">
        <h2>原始分享图</h2>
        <img src="{escape(original_src)}" alt="原始分享图">
      </section>
      <section class="image-card">
        <h2>解析区域 overlay</h2>
        <img src="{escape(overlay_src)}" alt="解析区域 overlay">
        {render_region_legend(parsed)}
      </section>
    </aside>
    <section class="right-column">
      {card_html}
      <section class="card">
        <h2>下一步建议</h2>
        <div class="recommendation">{escape(coverage.get("recommendation"))}</div>
        <div class="card-body">
          <div class="field field-uncertain">
            <div class="field-main"><span class="field-label">验收建议</span></div>
            <div class="field-value">请肉眼确认角色等级、核心属性、六个技能等级、音擎等级和六个驱动盘区域框；确认前不要写正式数据库。</div>
            <div class="field-meta">review_html: {escape(html_path.name)} overlay_png: {escape(overlay_path.name)}</div>
          </div>
        </div>
      </section>
    </section>
  </main>
</body>
</html>
"""


def markdown_review_section(review_html: Path, overlay_png: Path, base_dir: Path) -> str:
    review_rel = rel_or_abs(review_html, base_dir)
    overlay_rel = rel_or_abs(overlay_png, base_dir)
    return (
        "<!-- export-review-start -->\n"
        "## HTML 验收页\n\n"
        f"- review_html: `{review_rel}`\n"
        f"- overlay_png: `{overlay_rel}`\n"
        "- 验收建议：打开 HTML 后肉眼确认 overlay 区域框、角色等级、核心属性、技能等级、音擎等级和驱动盘字段；确认前不要写正式数据库。\n"
        "<!-- export-review-end -->\n"
    )


def update_markdown_summary(json_path: Path, review_html: Path, overlay_png: Path) -> None:
    md_path = json_path.with_suffix(".md")
    if not md_path.exists():
        return
    text = md_path.read_text(encoding="utf-8")
    section = markdown_review_section(review_html, overlay_png, md_path.parent)
    start = "<!-- export-review-start -->"
    end = "<!-- export-review-end -->"
    if start in text and end in text:
        before = text.split(start, 1)[0].rstrip()
        after = text.split(end, 1)[1].lstrip()
        text = f"{before}\n\n{section}\n{after}".rstrip() + "\n"
    else:
        text = text.rstrip() + "\n\n" + section
    md_path.write_text(text, encoding="utf-8")


def render_review(json_path: Path, *, image_override: str | None = None, output_dir: str | None = None) -> dict[str, Any]:
    parsed = load_parsed_json(json_path)
    image_path = resolve_image_path(parsed, image_override)
    target_dir = resolve_output_dir(output_dir, json_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = json_path.stem
    overlay_path = target_dir / f"{stem}_overlay.png"
    html_path = target_dir / f"{stem}_review.html"

    render_overlay(parsed, image_path, overlay_path)
    html_text = render_html(parsed, image_path, overlay_path, html_path)
    html_path.write_text(html_text, encoding="utf-8")
    update_markdown_summary(json_path, html_path, overlay_path)

    return {
        "review_html": str(html_path),
        "overlay_png": str(overlay_path),
        "image": str(image_path),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a local HTML review page for a parsed MiYouShe export-image JSON.")
    parser.add_argument("--json", required=True, help="Path to parsed JSON from export_image_parse_probe.py.")
    parser.add_argument("--image", default=None, help="Override original image path if metadata.input_image is missing or moved.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Default: same directory as parsed JSON.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    json_path = Path(args.json).expanduser()
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path
    json_path = json_path.resolve()

    try:
        result = render_review(json_path, image_override=args.image, output_dir=args.output_dir)
    except ReviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote review HTML: {result['review_html']}")
    print(f"Wrote overlay PNG: {result['overlay_png']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
