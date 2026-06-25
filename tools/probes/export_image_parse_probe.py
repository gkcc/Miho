#!/usr/bin/env python
"""OCR/layout probe for official MiYouShe exported/share images."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "parsed"
PADDLE_OCR_CACHE: dict[str, Any] = {}

SECRET_VALUE_RE = re.compile(
    r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b"
    r"(\s*[:=]\s*)"
    r"([^,\s;\"']+)"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEYED_ID_RE = re.compile(r"(?i)\b(uid|account_id|accountid|user_id|userid)\b(\s*[:=：]?\s*)\d{4,}")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")
NUMERIC_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CJK_TEXT_RE = re.compile(r"[\u4e00-\u9fff][\u4e00-\u9fff·]{1,18}")
LV_RE = re.compile(r"\bL[Vv]\.?\s*(\d{1,3})\b")
FUZZY_LV_RE = re.compile(r"(?i)\b[O0]?[IiLl1]?[VvWw]\.?\s*(\d{1,3})\b")
RANK_RE = re.compile(r"\b([SABC])\s*(?:RANK)?\b", re.IGNORECASE)

FIELD_RULES = [
    ("Character", re.compile(r"(角色|代理人|开拓者|名称|Name|Lv\.?|等级|星魂|影画)", re.IGNORECASE)),
    ("CharacterBuildSnapshot", re.compile(r"(等级|属性|生命|攻击|防御|速度|暴击|暴伤|击破|异常|精通|充能)", re.IGNORECASE)),
    ("Equipment", re.compile(r"(音擎|光锥|武器|装备|叠影|精炼|等级)", re.IGNORECASE)),
    ("SkillOrTrace", re.compile(r"(技能|行迹|普攻|战技|终结技|天赋|秘技|核心技|普通攻击|特殊技|连携技|支援)", re.IGNORECASE)),
    ("ArtifactOrDriveDisc", re.compile(r"(遗器|饰品|位面|驱动盘|套装|主词条|副词条|部位|折枝|云岿)", re.IGNORECASE)),
]

ZZZ_STAT_LABELS = {
    "hp": "生命值",
    "atk": "攻击力",
    "def": "防御力",
    "impact": "冲击力",
    "crit_rate": "暴击率",
    "crit_dmg": "暴击伤害",
    "anomaly_mastery": "异常掌控",
    "anomaly_proficiency": "异常精通",
    "pen": "贯穿力",
    "energy_regen": "能量自动累积",
    "physical_dmg_bonus": "物理伤害加成",
}

STAT_ALIASES = [
    "生命值",
    "攻击力",
    "防御力",
    "冲击力",
    "暴击率",
    "暴击伤害",
    "异常掌控",
    "异常精通",
    "贯穿力",
    "能量自动累积",
    "物理伤害加成",
    "穿透值",
]

TEXT_FILTER_PHRASES = {
    "代理人信息",
    "驱动盘",
    "有效副属性",
    "共命中",
    "生命值",
    "攻击力",
    "防御力",
    "冲击力",
    "暴击率",
    "暴击伤害",
    "异常掌控",
    "异常精通",
    "贯穿力",
    "能量自动累积",
    "物理伤害加成",
    "未命中",
    "米游社",
    "绝区零",
}


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegionSpec:
    name: str
    box_ratio: tuple[float, float, float, float]
    description: str


@dataclass(frozen=True)
class StatZone:
    field: str
    box_ratio: tuple[float, float, float, float]
    value_type: str = "number"


ZZZ_AGENT_CARD_REGIONS: tuple[RegionSpec, ...] = (
    RegionSpec("header", (0.00, 0.00, 1.00, 0.085), "nickname and UID header"),
    RegionSpec("character_card", (0.015, 0.085, 0.315, 0.365), "agent portrait, name, level, rank"),
    RegionSpec("core_stats", (0.315, 0.095, 0.985, 0.300), "core combat stats"),
    RegionSpec("skill_levels", (0.315, 0.292, 0.985, 0.365), "six skill level icons"),
    RegionSpec("equipment", (0.015, 0.365, 0.985, 0.485), "W-Engine summary and set hit count"),
    RegionSpec("equipment_level", (0.120, 0.415, 0.230, 0.455), "W-Engine level value"),
    RegionSpec("equipment_rank", (0.850, 0.385, 0.965, 0.455), "W-Engine rank value"),
    RegionSpec("drive_disc_1", (0.025, 0.470, 0.335, 0.675), "drive disc slot 1"),
    RegionSpec("drive_disc_2", (0.345, 0.470, 0.665, 0.675), "drive disc slot 2"),
    RegionSpec("drive_disc_3", (0.665, 0.470, 0.985, 0.675), "drive disc slot 3"),
    RegionSpec("drive_disc_4", (0.025, 0.675, 0.335, 0.890), "drive disc slot 4"),
    RegionSpec("drive_disc_5", (0.345, 0.675, 0.665, 0.890), "drive disc slot 5"),
    RegionSpec("drive_disc_6", (0.665, 0.675, 0.985, 0.890), "drive disc slot 6"),
)

ZZZ_CORE_STAT_ZONES: tuple[StatZone, ...] = (
    StatZone("hp", (0.565, 0.100, 0.655, 0.135)),
    StatZone("atk", (0.900, 0.100, 0.985, 0.135)),
    StatZone("def", (0.590, 0.132, 0.655, 0.165)),
    StatZone("impact", (0.900, 0.132, 0.985, 0.165)),
    StatZone("crit_rate", (0.565, 0.165, 0.655, 0.200), "percent"),
    StatZone("crit_dmg", (0.880, 0.165, 0.985, 0.200), "percent"),
    StatZone("anomaly_mastery", (0.585, 0.198, 0.655, 0.232)),
    StatZone("anomaly_proficiency", (0.880, 0.198, 0.985, 0.232)),
    StatZone("pen", (0.565, 0.230, 0.655, 0.265)),
    StatZone("energy_regen", (0.880, 0.230, 0.985, 0.265)),
    StatZone("physical_dmg_bonus", (0.555, 0.263, 0.655, 0.300), "percent"),
)

ZZZ_SKILL_ZONES: tuple[tuple[float, float, float, float], ...] = (
    (0.355, 0.318, 0.405, 0.352),
    (0.445, 0.318, 0.495, 0.352),
    (0.530, 0.318, 0.580, 0.352),
    (0.620, 0.318, 0.670, 0.352),
    (0.705, 0.318, 0.755, 0.352),
    (0.795, 0.318, 0.845, 0.352),
)


def redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = KEYED_ID_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_ID]", text)
    text = LONG_DIGIT_RE.sub("[REDACTED_ID]", text)
    return text


def truncate(text: str, limit: int = 200) -> str:
    clean = text.replace("\r", " ").replace("\n", " ").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def markdown_cell(value: Any, limit: int = 100) -> str:
    return truncate(redact_text(value), limit).replace("|", "\\|")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def output_stem(image_path: Path) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", image_path.stem)[:80] or "image"
    return f"{safe_name}_parsed_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def relative_or_redacted(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return redact_text(str(path))


def load_image_dependency() -> Any:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError(
            "Missing image dependency 'Pillow'. Install it if you want to parse exported images: "
            "python -m pip install pillow"
        ) from exc
    return Image


def load_tesseract_dependency() -> Any:
    try:
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError(
            "Missing OCR dependency 'pytesseract'. Install it if you want OCR parsing: "
            "python -m pip install pytesseract"
        ) from exc
    if shutil.which("tesseract") is None:
        for candidate in (
            Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
            Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
        ):
            if candidate.exists():
                pytesseract.pytesseract.tesseract_cmd = str(candidate)
                break
    configure_tessdata_prefix()
    return pytesseract


def configure_tessdata_prefix() -> None:
    candidates: list[Path] = []
    current = os.environ.get("TESSDATA_PREFIX")
    if current:
        current_path = Path(current)
        candidates.extend([current_path, current_path / "tessdata"])

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Tesseract-OCR" / "tessdata")

    for candidate in candidates:
        if (candidate / "chi_sim.traineddata").exists() and (candidate / "eng.traineddata").exists():
            os.environ["TESSDATA_PREFIX"] = str(candidate)
            return


def load_paddle_dependency() -> tuple[Any, Any]:
    try:
        import numpy as np  # type: ignore[import-not-found]
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError(
            "Missing optional PaddleOCR dependencies. Install them only if you want --engine paddle: "
            "python -m pip install paddleocr paddlepaddle"
        ) from exc
    return np, PaddleOCR


def preprocess_for_ocr(image: Any) -> tuple[Any, dict[str, Any]]:
    try:
        from PIL import Image, ImageEnhance, ImageOps  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError("Missing Pillow preprocessing helpers.") from exc

    grayscale = ImageOps.grayscale(image)
    contrasted = ImageEnhance.Contrast(grayscale).enhance(1.8)
    width, height = contrasted.size
    resample = getattr(getattr(Image, "Resampling", object), "LANCZOS", 1)
    enlarged = contrasted.resize((width * 2, height * 2), resample=resample)
    return enlarged, {
        "scale": 2,
        "grayscale": True,
        "contrast": 1.8,
        "source_width": width,
        "source_height": height,
    }


def classify_text(text: str, confidence: float) -> dict[str, Any]:
    labels = []
    for label, pattern in FIELD_RULES:
        if pattern.search(text):
            labels.append(label)

    uncertain = confidence < 60 or not labels
    if not labels:
        labels = ["unknown"]

    return {
        "candidate_entities": labels,
        "confidence": round(confidence / 100.0, 3) if confidence >= 0 else None,
        "uncertain": uncertain,
    }


def parse_confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def ratio_box_to_pixels(box_ratio: tuple[float, float, float, float], width: int, height: int) -> dict[str, int]:
    left = max(0, min(width, round(box_ratio[0] * width)))
    top = max(0, min(height, round(box_ratio[1] * height)))
    right = max(left, min(width, round(box_ratio[2] * width)))
    bottom = max(top, min(height, round(box_ratio[3] * height)))
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def block_center(block: dict[str, Any]) -> tuple[float, float]:
    box = block.get("box", {})
    return (
        float(box.get("left", 0)) + float(box.get("width", 0)) / 2,
        float(box.get("top", 0)) + float(box.get("height", 0)) / 2,
    )


def block_in_box(block: dict[str, Any], box: dict[str, int]) -> bool:
    center_x, center_y = block_center(block)
    return box["left"] <= center_x <= box["right"] and box["top"] <= center_y <= box["bottom"]


def parse_tesseract_blocks(
    data: dict[str, Any],
    *,
    region_name: str,
    region_box: dict[str, int],
    scale: float,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    total = len(data.get("text", []))
    for index in range(total):
        text = redact_text(data["text"][index]).strip()
        if not text:
            continue
        conf = parse_confidence(data.get("conf", [])[index])
        classification = classify_text(text, conf)
        left = region_box["left"] + round(int(data["left"][index]) / scale)
        top = region_box["top"] + round(int(data["top"][index]) / scale)
        width = round(int(data["width"][index]) / scale)
        height = round(int(data["height"][index]) / scale)
        blocks.append(
            {
                "text": text,
                "region": region_name,
                "box": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                },
                "ocr_confidence_raw": conf,
                "candidate_entities": classification["candidate_entities"],
                "confidence": classification["confidence"],
                "uncertain": classification["uncertain"],
            }
        )
    return blocks


def run_tesseract_on_region(
    image: Any,
    *,
    lang: str,
    region_name: str,
    region_box: dict[str, int],
    config: str = "--psm 6",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pytesseract = load_tesseract_dependency()
    crop = image.crop((region_box["left"], region_box["top"], region_box["right"], region_box["bottom"]))
    processed, preprocess_info = preprocess_for_ocr(crop)
    try:
        data = pytesseract.image_to_data(processed, lang=lang, config=config, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        raise ProbeError(
            "OCR failed. Ensure the Tesseract binary is installed and the requested language data exists. "
            f"Details: {redact_text(exc)}"
        ) from exc
    blocks = parse_tesseract_blocks(
        data,
        region_name=region_name,
        region_box=region_box,
        scale=float(preprocess_info["scale"]),
    )
    return blocks, preprocess_info


def paddle_lang_from_tesseract_lang(lang: str) -> str:
    lowered = lang.casefold()
    if "chi" in lowered or "ch" in lowered or "zh" in lowered:
        return "ch"
    return "en"


def iter_paddle_lines(raw_result: Any) -> Iterable[Any]:
    if not raw_result:
        return []
    if isinstance(raw_result, list) and raw_result and isinstance(raw_result[0], list):
        first = raw_result[0]
        if first and isinstance(first[0], list) and len(first[0]) == 2 and isinstance(first[0][1], tuple):
            return first
    return raw_result


def run_paddle_on_region(
    image: Any,
    *,
    lang: str,
    region_name: str,
    region_box: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    np, PaddleOCR = load_paddle_dependency()
    crop = image.crop((region_box["left"], region_box["top"], region_box["right"], region_box["bottom"]))
    processed, preprocess_info = preprocess_for_ocr(crop.convert("RGB"))
    paddle_lang = paddle_lang_from_tesseract_lang(lang)
    try:
        if paddle_lang not in PADDLE_OCR_CACHE:
            PADDLE_OCR_CACHE[paddle_lang] = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
        ocr = PADDLE_OCR_CACHE[paddle_lang]
        raw_result = ocr.ocr(np.array(processed.convert("RGB")), cls=True)
    except Exception as exc:
        raise ProbeError(f"PaddleOCR failed. Details: {redact_text(exc)}") from exc

    blocks: list[dict[str, Any]] = []
    scale = float(preprocess_info["scale"])
    for item in iter_paddle_lines(raw_result):
        try:
            points, payload = item
            text, confidence = payload
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
        except Exception:
            continue
        text = redact_text(text).strip()
        if not text:
            continue
        conf_percent = float(confidence) * 100
        classification = classify_text(text, conf_percent)
        left = region_box["left"] + round(min(xs) / scale)
        top = region_box["top"] + round(min(ys) / scale)
        right = region_box["left"] + round(max(xs) / scale)
        bottom = region_box["top"] + round(max(ys) / scale)
        blocks.append(
            {
                "text": text,
                "region": region_name,
                "box": {
                    "left": left,
                    "top": top,
                    "width": max(0, right - left),
                    "height": max(0, bottom - top),
                },
                "ocr_confidence_raw": round(conf_percent, 3),
                "candidate_entities": classification["candidate_entities"],
                "confidence": classification["confidence"],
                "uncertain": classification["uncertain"],
            }
        )
    return blocks, preprocess_info


def ocr_region(
    image: Any,
    *,
    engine: str,
    lang: str,
    region_name: str,
    region_box: dict[str, int],
    config: str = "--psm 6",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if engine == "none":
        return [], {"scale": 1, "grayscale": False, "contrast": None, "ocr_skipped": True}
    if engine == "tesseract":
        return run_tesseract_on_region(image, lang=lang, region_name=region_name, region_box=region_box, config=config)
    if engine == "paddle":
        return run_paddle_on_region(image, lang=lang, region_name=region_name, region_box=region_box)
    raise ProbeError(f"Unsupported OCR engine: {engine}")


def image_info_for(image: Any) -> dict[str, Any]:
    return {
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "format": image.format,
    }


def render_region_text(blocks: list[dict[str, Any]]) -> str:
    ordered = sorted(blocks, key=lambda block: (block.get("box", {}).get("top", 0), block.get("box", {}).get("left", 0)))
    return " ".join(block["text"] for block in ordered if block.get("text")).strip()


def run_ocr(image_path: Path, *, engine: str, lang: str, game: str | None, layout: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    Image = load_image_dependency()
    image = Image.open(image_path)
    image_info = image_info_for(image)

    region_specs: list[RegionSpec]
    if game == "zzz" and layout == "zzz-agent-card":
        region_specs = list(ZZZ_AGENT_CARD_REGIONS)
        region_specs.extend(
            RegionSpec(f"stat_{zone.field}", zone.box_ratio, f"numeric value for {zone.field}") for zone in ZZZ_CORE_STAT_ZONES
        )
        region_specs.extend(
            RegionSpec(f"skill_level_{index}", zone, f"numeric value for skill level {index}")
            for index, zone in enumerate(ZZZ_SKILL_ZONES, start=1)
        )
    else:
        region_specs = [RegionSpec("full_image", (0.0, 0.0, 1.0, 1.0), "full image")]

    layout_regions: list[dict[str, Any]] = []
    all_blocks: list[dict[str, Any]] = []
    for spec in region_specs:
        region_box = ratio_box_to_pixels(spec.box_ratio, image.width, image.height)
        config = "--psm 6"
        if spec.name.startswith(("stat_", "skill_level_")):
            config = "--psm 6 -c tessedit_char_whitelist=0123456789.%"
        elif spec.name == "equipment_level":
            config = "--psm 6 -c tessedit_char_whitelist=0123456789.LVlvOoiIwW"
        elif spec.name == "equipment_rank":
            config = "--psm 6 -c tessedit_char_whitelist=SABC"
        elif spec.name == "skill_levels":
            config = "--psm 6 -c tessedit_char_whitelist=0123456789.%"
        elif spec.name.startswith("drive_disc_"):
            config = "--psm 6"
        blocks, preprocess_info = ocr_region(
            image,
            engine=engine,
            lang=lang,
            region_name=spec.name,
            region_box=region_box,
            config=config,
        )
        all_blocks.extend(blocks)
        layout_regions.append(
            {
                "name": spec.name,
                "description": spec.description,
                "box": region_box,
                "preprocess": preprocess_info,
                "text": render_region_text(blocks),
                "text_block_count": len(blocks),
            }
        )

    image.close()
    return {"image": image_info, "layout_regions": layout_regions}, all_blocks


def field(value: Any = None, *, uncertain: bool = True, evidence: list[str] | None = None, source_region: str | None = None) -> dict[str, Any]:
    cleaned = redact_text(value).strip() if isinstance(value, str) else value
    if cleaned == "":
        cleaned = None
    return {
        "value": cleaned,
        "uncertain": bool(uncertain if cleaned is not None else True),
        "evidence": evidence or [],
        "source_region": source_region,
    }


def empty_draft(game: str | None) -> dict[str, Any]:
    return {
        "game": game,
        "character": {
            "name": field(),
            "level": field(),
            "rank": field(),
        },
        "stats": {name: field() for name in ZZZ_STAT_LABELS},
        "skill_levels": [{"slot": index, "level": field()} for index in range(1, 7)],
        "equipment": {
            "name": field(),
            "level": field(),
            "rank": field(),
        },
        "drive_discs": [
            {
                "slot": index,
                "set_name": field(),
                "level": field(),
                "main_stat": field(),
                "sub_stats": field([], uncertain=True),
            }
            for index in range(1, 7)
        ],
    }


def text_for_region(blocks: list[dict[str, Any]], region: str) -> str:
    return render_region_text([block for block in blocks if block.get("region") == region])


def blocks_for_region(blocks: list[dict[str, Any]], region: str) -> list[dict[str, Any]]:
    return [block for block in blocks if block.get("region") == region]


def blocks_for_regions(blocks: list[dict[str, Any]], regions: set[str]) -> list[dict[str, Any]]:
    return [block for block in blocks if block.get("region") in regions]


def clean_numeric_token(token: str) -> str:
    return token.strip().replace(" ", "").replace(",", "")


def numeric_tokens(text: str) -> list[str]:
    return [clean_numeric_token(match.group(0)) for match in NUMERIC_RE.finditer(text)]


def best_numeric_in_box(
    blocks: list[dict[str, Any]],
    box: dict[str, int],
    *,
    expect_percent: bool = False,
) -> tuple[str | None, list[str]]:
    candidates: list[tuple[int, float, float, str, str]] = []
    for block in blocks:
        if not block_in_box(block, box):
            continue
        for token in numeric_tokens(str(block.get("text", ""))):
            if not token:
                continue
            has_percent = token.endswith("%")
            if expect_percent and not has_percent:
                continue
            center_x, _ = block_center(block)
            confidence = float(block.get("confidence") or 0)
            region = str(block.get("region", ""))
            priority = 2 if region.startswith(("stat_", "skill_level_")) else 1 if region == "skill_levels" else 0
            candidates.append((priority, center_x, confidence, token, block.get("text", "")))
    if not candidates and expect_percent:
        return best_numeric_in_box(blocks, box, expect_percent=False)
    if not candidates:
        return None, []
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return candidates[0][3], [candidate[4] for candidate in candidates[:3]]


def first_lv(text: str) -> str | None:
    match = LV_RE.search(text)
    if match:
        return match.group(1)
    fuzzy_match = FUZZY_LV_RE.search(text)
    return fuzzy_match.group(1) if fuzzy_match else None


def first_rank(text: str) -> str | None:
    for match in RANK_RE.finditer(text):
        value = match.group(1).upper()
        if value in {"S", "A", "B", "C"}:
            return value
    return None


def cjk_candidates(text: str) -> list[str]:
    candidates = []
    for match in CJK_TEXT_RE.finditer(text):
        candidate = match.group(0).strip(" ·")
        if not candidate or candidate in TEXT_FILTER_PHRASES:
            continue
        if any(phrase in candidate for phrase in TEXT_FILTER_PHRASES):
            continue
        candidates.append(candidate)
    return candidates


def best_cjk_name(text: str) -> str | None:
    candidates = cjk_candidates(text)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (len(item), "·" in item), reverse=True)
    return candidates[0]


def value_from_fixed_zone(
    blocks: list[dict[str, Any]],
    image_width: int,
    image_height: int,
    zone: tuple[float, float, float, float],
    *,
    expect_percent: bool = False,
) -> tuple[str | None, list[str]]:
    box = ratio_box_to_pixels(zone, image_width, image_height)
    return best_numeric_in_box(blocks, box, expect_percent=expect_percent)


def extract_character(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    text = text_for_region(blocks, "character_card")
    name = best_cjk_name(text)
    level = first_lv(text)
    rank = first_rank(text)
    return {
        "name": field(name, uncertain=name is None, evidence=[name] if name else [], source_region="character_card"),
        "level": field(level, uncertain=level is None, evidence=[level] if level else [], source_region="character_card"),
        "rank": field(rank, uncertain=rank is None, evidence=[rank] if rank else [], source_region="character_card"),
    }


def extract_stats(blocks: list[dict[str, Any]], image_width: int, image_height: int) -> dict[str, Any]:
    stats = {name: field() for name in ZZZ_STAT_LABELS}
    for zone in ZZZ_CORE_STAT_ZONES:
        value, evidence = value_from_fixed_zone(
            blocks,
            image_width,
            image_height,
            zone.box_ratio,
            expect_percent=zone.value_type == "percent",
        )
        stats[zone.field] = field(
            value,
            uncertain=value is None,
            evidence=evidence,
            source_region="core_stats",
        )
    return stats


def extract_skill_levels(blocks: list[dict[str, Any]], image_width: int, image_height: int) -> list[dict[str, Any]]:
    skill_levels: list[dict[str, Any]] = []
    for index, zone in enumerate(ZZZ_SKILL_ZONES, start=1):
        value, evidence = value_from_fixed_zone(blocks, image_width, image_height, zone)
        skill_levels.append(
            {
                "slot": index,
                "level": field(value, uncertain=value is None, evidence=evidence, source_region="skill_levels"),
            }
        )
    return skill_levels


def extract_equipment(blocks: list[dict[str, Any]], image_width: int, image_height: int) -> dict[str, Any]:
    equipment_blocks = blocks_for_regions(blocks, {"equipment", "equipment_level", "equipment_rank"})
    text = render_region_text(equipment_blocks)
    level = first_lv(text)
    rank_value, rank_evidence = None, []
    rank_box = ratio_box_to_pixels((0.860, 0.380, 0.965, 0.455), image_width, image_height)
    for block in equipment_blocks:
        if not block_in_box(block, rank_box):
            continue
        possible_rank = first_rank(str(block.get("text", "")))
        if possible_rank:
            rank_value = possible_rank
            rank_evidence = [block.get("text", "")]
            break

    name_box = ratio_box_to_pixels((0.115, 0.380, 0.320, 0.435), image_width, image_height)
    name_text = render_region_text([block for block in equipment_blocks if block_in_box(block, name_box)])
    name = best_cjk_name(name_text) or best_cjk_name(text)
    return {
        "name": field(name, uncertain=name is None, evidence=[name] if name else [], source_region="equipment"),
        "level": field(level, uncertain=level is None, evidence=[level] if level else [], source_region="equipment"),
        "rank": field(rank_value, uncertain=rank_value is None, evidence=rank_evidence, source_region="equipment"),
    }


def local_ratio_box(region_box: dict[str, int], ratio: tuple[float, float, float, float]) -> dict[str, int]:
    width = region_box["width"]
    height = region_box["height"]
    left = region_box["left"] + round(width * ratio[0])
    top = region_box["top"] + round(height * ratio[1])
    right = region_box["left"] + round(width * ratio[2])
    bottom = region_box["top"] + round(height * ratio[3])
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def parse_drive_set_name(text: str, slot: int) -> str | None:
    slot_pattern = re.compile(rf"([\u4e00-\u9fff][\u4e00-\u9fff·]{{1,12}})\s*[\[【(（]\s*{slot}\s*[\]】)）]")
    match = slot_pattern.search(text)
    if match:
        return match.group(1)
    return best_cjk_name(text)


def parse_main_stat(label_text: str, value_text: str) -> str | None:
    label = None
    for alias in STAT_ALIASES:
        if alias in label_text:
            label = alias
            break
    value_candidates = numeric_tokens(value_text)
    if label and value_candidates:
        return f"{label} {value_candidates[-1]}"
    if label:
        return label
    return None


def parse_sub_stats(blocks: list[dict[str, Any]], value_zone: dict[str, int]) -> list[dict[str, Any]]:
    lines = []
    ordered = sorted(blocks, key=lambda block: (block.get("box", {}).get("top", 0), block.get("box", {}).get("left", 0)))
    for block in ordered:
        text = str(block.get("text", ""))
        if not any(alias in text for alias in STAT_ALIASES):
            continue
        value = None
        nearby_values = [
            candidate
            for candidate in ordered
            if block_in_box(candidate, value_zone)
            and abs(block_center(candidate)[1] - block_center(block)[1]) < 36
            and numeric_tokens(str(candidate.get("text", "")))
        ]
        if nearby_values:
            value = numeric_tokens(str(nearby_values[-1].get("text", "")))[-1]
        lines.append(
            {
                "stat": text,
                "value": value,
                "uncertain": value is None,
                "evidence": [text] + ([value] if value else []),
            }
        )
    return lines


def extract_drive_discs(blocks: list[dict[str, Any]], layout_regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    region_by_name = {region["name"]: region for region in layout_regions}
    discs: list[dict[str, Any]] = []
    for slot in range(1, 7):
        region_name = f"drive_disc_{slot}"
        region = region_by_name.get(region_name, {})
        region_box = region.get("box", {})
        disc_blocks = blocks_for_region(blocks, region_name)
        text = render_region_text(disc_blocks)
        level = first_lv(text)
        set_name = parse_drive_set_name(text, slot)

        if region_box:
            main_label_box = local_ratio_box(region_box, (0.035, 0.250, 0.520, 0.430))
            main_value_box = local_ratio_box(region_box, (0.520, 0.235, 0.965, 0.430))
            sub_value_box = local_ratio_box(region_box, (0.600, 0.430, 0.965, 0.970))
            main_label_text = render_region_text([block for block in disc_blocks if block_in_box(block, main_label_box)])
            main_value_text = render_region_text([block for block in disc_blocks if block_in_box(block, main_value_box)])
            sub_blocks = [block for block in disc_blocks if block_in_box(block, local_ratio_box(region_box, (0.035, 0.430, 0.965, 0.970)))]
            sub_stats = parse_sub_stats(sub_blocks, sub_value_box)
        else:
            main_label_text = text
            main_value_text = text
            sub_stats = []

        main_stat = parse_main_stat(main_label_text, main_value_text)
        discs.append(
            {
                "slot": slot,
                "set_name": field(set_name, uncertain=set_name is None, evidence=[set_name] if set_name else [], source_region=region_name),
                "level": field(level, uncertain=level is None, evidence=[level] if level else [], source_region=region_name),
                "main_stat": field(
                    main_stat,
                    uncertain=main_stat is None,
                    evidence=[item for item in [main_label_text, main_value_text] if item],
                    source_region=region_name,
                ),
                "sub_stats": field(sub_stats, uncertain=not bool(sub_stats), evidence=[text] if text else [], source_region=region_name),
            }
        )
    return discs


def extract_zzz_agent_card(
    blocks: list[dict[str, Any]],
    layout_regions: list[dict[str, Any]],
    image_info: dict[str, Any],
    game: str | None,
) -> dict[str, Any]:
    draft = empty_draft(game)
    width = int(image_info.get("width", 0))
    height = int(image_info.get("height", 0))
    draft["character"] = extract_character(blocks)
    draft["stats"] = extract_stats(blocks, width, height)
    draft["skill_levels"] = extract_skill_levels(blocks, width, height)
    draft["equipment"] = extract_equipment(blocks, width, height)
    draft["drive_discs"] = extract_drive_discs(blocks, layout_regions)
    return draft


def build_extracted_draft(
    *,
    game: str | None,
    layout: str,
    blocks: list[dict[str, Any]],
    layout_regions: list[dict[str, Any]],
    image_info: dict[str, Any],
) -> dict[str, Any]:
    if game == "zzz" and layout == "zzz-agent-card":
        return extract_zzz_agent_card(blocks, layout_regions, image_info, game)
    return empty_draft(game)


def walk_fields(value: Any, prefix: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict) and {"value", "uncertain", "evidence", "source_region"}.issubset(value.keys()):
        yield prefix, value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else key
            yield from walk_fields(item, next_prefix)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            label = item.get("slot", index + 1) if isinstance(item, dict) else index + 1
            next_prefix = f"{prefix}[{label}]"
            yield from walk_fields(item, next_prefix)


def summarize_coverage(draft: dict[str, Any], blocks: list[dict[str, Any]]) -> dict[str, Any]:
    matched_fields: list[str] = []
    missing_fields: list[str] = []
    numeric_fields_detected: list[dict[str, Any]] = []
    chinese_fields_detected: list[dict[str, Any]] = []

    for path, item in walk_fields(draft):
        value = item.get("value")
        has_value = value not in (None, "", [])
        if has_value:
            matched_fields.append(path)
            value_text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
            if NUMERIC_RE.search(value_text):
                numeric_fields_detected.append({"field": path, "value": value})
            if CJK_RE.search(value_text):
                chinese_fields_detected.append({"field": path, "value": value})
        else:
            missing_fields.append(path)

    total_fields = len(matched_fields) + len(missing_fields)
    matched_ratio = len(matched_fields) / total_fields if total_fields else 0
    numeric_raw_count = sum(1 for block in blocks if numeric_tokens(str(block.get("text", ""))))
    chinese_raw_count = sum(1 for block in blocks if CJK_RE.search(str(block.get("text", ""))))

    if matched_ratio >= 0.72 and chinese_fields_detected:
        coverage_level = "high"
        recommendation = "字段覆盖较完整，可以继续做人工确认页和 fixture 回放；仍不要直接写正式数据库。"
    elif matched_ratio >= 0.35 or len(numeric_fields_detected) >= 8 or numeric_raw_count >= 12:
        coverage_level = "medium"
        recommendation = "官方分享图路线成立；优先补中文 OCR 语言包或 PaddleOCR，并继续调固定区域字段抽取。"
    else:
        coverage_level = "low"
        recommendation = "当前只能证明图片可离线处理；建议先确认版式、语言包和裁剪区域，再考虑字段抽取 prototype。"

    return {
        "matched_fields": matched_fields,
        "missing_fields": missing_fields,
        "numeric_fields_detected": numeric_fields_detected,
        "chinese_fields_detected": chinese_fields_detected,
        "raw_numeric_text_block_count": numeric_raw_count,
        "raw_chinese_text_block_count": chinese_raw_count,
        "coverage_level": coverage_level,
        "recommendation": recommendation,
    }


def summarize_entities(blocks: list[dict[str, Any]], draft: dict[str, Any] | None = None) -> dict[str, Any]:
    entity_counts: dict[str, int] = {}
    uncertain_count = 0
    for block in blocks:
        if block.get("uncertain"):
            uncertain_count += 1
        for label in block.get("candidate_entities", []):
            entity_counts[label] = entity_counts.get(label, 0) + 1

    adr_entities = ["Character", "CharacterBuildSnapshot", "Equipment", "SkillOrTrace", "ArtifactOrDriveDisc"]
    matches = {entity: entity_counts.get(entity, 0) > 0 for entity in adr_entities}

    if draft:
        character = draft.get("character", {})
        stats = draft.get("stats", {})
        equipment = draft.get("equipment", {})
        skill_levels = draft.get("skill_levels", [])
        drive_discs = draft.get("drive_discs", [])
        matches["Character"] = matches["Character"] or any(character.get(key, {}).get("value") for key in ("name", "level", "rank"))
        matches["CharacterBuildSnapshot"] = matches["CharacterBuildSnapshot"] or any(
            item.get("value") for item in stats.values() if isinstance(item, dict)
        )
        matches["Equipment"] = matches["Equipment"] or any(equipment.get(key, {}).get("value") for key in ("name", "level", "rank"))
        matches["SkillOrTrace"] = matches["SkillOrTrace"] or any(
            item.get("level", {}).get("value") for item in skill_levels if isinstance(item, dict)
        )
        matches["ArtifactOrDriveDisc"] = matches["ArtifactOrDriveDisc"] or any(
            any(disc.get(key, {}).get("value") for key in ("set_name", "level", "main_stat", "sub_stats"))
            for disc in drive_discs
            if isinstance(disc, dict)
        )

    return {
        "text_block_count": len(blocks),
        "uncertain_count": uncertain_count,
        "entity_counts": entity_counts,
        "adr_0003_matches": matches,
    }


def write_outputs(result: dict[str, Any], output_dir: Path, image_path: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(image_path)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def render_field(value: Any) -> str:
    if isinstance(value, dict) and "value" in value:
        return f"{value.get('value')} (uncertain={value.get('uncertain')})"
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    meta = result["metadata"]
    summary = result.get("summary", {})
    coverage = result.get("coverage_summary", {})
    draft = result.get("extracted_draft", {})
    blocks = result.get("text_blocks", [])
    regions = result.get("layout_regions", [])
    errors = result.get("errors", [])

    lines = [
        "# 官方导出/分享图解析 Probe",
        "",
        "## 摘要",
        "",
        f"- 创建时间：{markdown_cell(meta.get('created_at'), 120)}",
        f"- 输入图片：{markdown_cell(meta.get('input_image'), 160)}",
        f"- OCR 引擎：{markdown_cell(meta.get('ocr_engine'))}",
        f"- 游戏：{markdown_cell(meta.get('game'))}",
        f"- 布局：{markdown_cell(meta.get('layout'))}",
        f"- 文本块数量：{summary.get('text_block_count', 0)}",
        f"- 不确定文本块：{summary.get('uncertain_count', 0)}",
        f"- 覆盖等级：{markdown_cell(coverage.get('coverage_level'))}",
        f"- 建议：{markdown_cell(coverage.get('recommendation'), 220)}",
        "",
        "## ADR-0003 匹配",
        "",
    ]

    for entity, matched in summary.get("adr_0003_matches", {}).items():
        lines.append(f"- {entity}: {matched}")
    lines.append("")

    if coverage:
        lines.extend(
            [
                "## Coverage Summary",
                "",
                f"- matched_fields: {len(coverage.get('matched_fields', []))}",
                f"- missing_fields: {len(coverage.get('missing_fields', []))}",
                f"- numeric_fields_detected: {len(coverage.get('numeric_fields_detected', []))}",
                f"- chinese_fields_detected: {len(coverage.get('chinese_fields_detected', []))}",
                "",
            ]
        )

    if draft:
        character = draft.get("character", {})
        stats = draft.get("stats", {})
        equipment = draft.get("equipment", {})
        lines.extend(
            [
                "## Extracted Draft",
                "",
                f"- character.name: {markdown_cell(render_field(character.get('name')), 120)}",
                f"- character.level: {markdown_cell(render_field(character.get('level')), 120)}",
                f"- character.rank: {markdown_cell(render_field(character.get('rank')), 120)}",
                f"- equipment.name: {markdown_cell(render_field(equipment.get('name')), 120)}",
                f"- equipment.level: {markdown_cell(render_field(equipment.get('level')), 120)}",
                f"- equipment.rank: {markdown_cell(render_field(equipment.get('rank')), 120)}",
                "",
                "| stat | value |",
                "|---|---|",
            ]
        )
        for key in ZZZ_STAT_LABELS:
            lines.append(f"| {key} | {markdown_cell(render_field(stats.get(key)), 120)} |")
        lines.append("")

    if regions:
        lines.extend(["## Layout Regions", "", "| name | box | text blocks | text sample |", "|---|---|---:|---|"])
        for region in regions:
            box = region.get("box", {})
            box_text = f"{box.get('left')},{box.get('top')},{box.get('width')},{box.get('height')}"
            lines.append(
                "| "
                f"{markdown_cell(region.get('name'))} | "
                f"{markdown_cell(box_text)} | "
                f"{region.get('text_block_count', 0)} | "
                f"{markdown_cell(region.get('text'), 160)} |"
            )
        lines.append("")

    if errors:
        lines.extend(["## 错误", ""])
        for error in errors:
            lines.append(f"- {markdown_cell(error, 240)}")
        lines.append("")

    lines.extend(
        [
            "## 文本块",
            "",
            "| text | region | box | entities | confidence | uncertain |",
            "|---|---|---|---|---:|---|",
        ]
    )
    for block in blocks[:300]:
        box = block.get("box", {})
        box_text = f"{box.get('left')},{box.get('top')},{box.get('width')},{box.get('height')}"
        lines.append(
            "| "
            f"{markdown_cell(block.get('text'), 120)} | "
            f"{markdown_cell(block.get('region'))} | "
            f"{markdown_cell(box_text)} | "
            f"{markdown_cell(', '.join(block.get('candidate_entities', [])), 120)} | "
            f"{block.get('confidence')} | "
            f"{block.get('uncertain')} |"
        )
    if len(blocks) > 300:
        lines.append(f"| ... | ... | ... | ... | ... | 还有 {len(blocks) - 300} 个文本块 |")
    lines.append("")
    return "\n".join(lines)


def validate_args(args: argparse.Namespace) -> None:
    if args.layout == "zzz-agent-card" and args.game != "zzz":
        raise ProbeError("--layout zzz-agent-card requires --game zzz.")


def build_result(image_path: Path, *, engine: str, lang: str, game: str | None, layout: str) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {
        "metadata": {
            "probe": "export_image_parse_probe",
            "created_at": now_iso(),
            "input_image": relative_or_redacted(image_path),
            "ocr_engine": engine,
            "lang": lang,
            "game": game,
            "layout": layout,
            "notes": [
                "Prototype only. Not a formal collector.",
                "Does not overwrite the input image and does not write a formal database.",
                "OCR/extracted_draft must be manually confirmed before any future import.",
            ],
        },
        "image": {},
        "layout_regions": [],
        "summary": {},
        "coverage_summary": {},
        "extracted_draft": empty_draft(game),
        "text_blocks": [],
        "errors": [],
    }

    if not image_path.exists():
        result["errors"].append(f"Input image does not exist: {relative_or_redacted(image_path)}")
        result["summary"] = summarize_entities([])
        result["coverage_summary"] = summarize_coverage(result["extracted_draft"], [])
        return result, 2
    if not image_path.is_file():
        result["errors"].append(f"Input path is not a file: {relative_or_redacted(image_path)}")
        result["summary"] = summarize_entities([])
        result["coverage_summary"] = summarize_coverage(result["extracted_draft"], [])
        return result, 2

    try:
        ocr_result, blocks = run_ocr(image_path, engine=engine, lang=lang, game=game, layout=layout)
        result["image"] = ocr_result["image"]
        result["layout_regions"] = ocr_result["layout_regions"]
        result["text_blocks"] = blocks
        result["extracted_draft"] = build_extracted_draft(
            game=game,
            layout=layout,
            blocks=blocks,
            layout_regions=result["layout_regions"],
            image_info=result["image"],
        )
        result["summary"] = summarize_entities(blocks, result["extracted_draft"])
        result["coverage_summary"] = summarize_coverage(result["extracted_draft"], blocks)
        return result, 0
    except ProbeError as exc:
        result["errors"].append(str(exc))
        result["summary"] = summarize_entities([], result["extracted_draft"])
        result["coverage_summary"] = summarize_coverage(result["extracted_draft"], [])
        return result, 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR/layout probe for official MiYouShe exported/share images. Does not overwrite images or write a formal DB."
    )
    parser.add_argument("--image", required=True, help="Local image path to parse.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/parsed")
    parser.add_argument("--lang", default="chi_sim+eng", help="OCR language string. Default: chi_sim+eng")
    parser.add_argument(
        "--engine",
        choices=("tesseract", "paddle", "none"),
        default="tesseract",
        help="OCR engine. Default: tesseract",
    )
    parser.add_argument("--game", choices=("zzz", "hsr"), default=None, help="Game layout hint: zzz or hsr.")
    parser.add_argument(
        "--layout",
        choices=("full", "zzz-agent-card"),
        default="full",
        help="Layout strategy. Default: full. zzz-agent-card requires --game zzz.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    image_path = Path(args.image).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    try:
        validate_args(args)
        result, exit_code = build_result(
            image_path,
            engine=args.engine,
            lang=args.lang,
            game=args.game,
            layout=args.layout,
        )
    except ProbeError as exc:
        result = {
            "metadata": {
                "probe": "export_image_parse_probe",
                "created_at": now_iso(),
                "input_image": relative_or_redacted(image_path),
                "ocr_engine": args.engine,
                "lang": args.lang,
                "game": args.game,
                "layout": args.layout,
            },
            "image": {},
            "layout_regions": [],
            "summary": summarize_entities([]),
            "coverage_summary": summarize_coverage(empty_draft(args.game), []),
            "extracted_draft": empty_draft(args.game),
            "text_blocks": [],
            "errors": [str(exc)],
        }
        exit_code = 2

    json_path, md_path = write_outputs(result, output_dir, image_path)
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    if result.get("errors"):
        print("OCR probe did not complete successfully:", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
