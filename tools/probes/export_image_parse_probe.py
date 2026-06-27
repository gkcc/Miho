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
DEFAULT_CROP_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "crops"
PADDLE_OCR_CACHE: dict[str, Any] = {}
RAPID_OCR_CACHE: dict[str, Any] = {}

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

INVALID_CANDIDATE_VALUES = {
    "驱动",
    "驱动盘",
    "命中",
    "共命中",
    "有效副属性",
    "属性",
    "等级",
    "音擎",
    "装备",
    "代理人信息",
}

TRUSTED_NUMERIC_STAT_FIELDS = tuple(ZZZ_STAT_LABELS.keys())


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
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    try:
        import numpy as np  # type: ignore[import-not-found]
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError(
            "PaddleOCR is not available. For real MiYouShe Chinese share-image parsing, install PaddleOCR and rerun "
            "with --engine paddle. Suggested start: python -m pip install paddleocr. If Paddle asks for a PaddlePaddle "
            "wheel, follow the PaddleOCR install guide for your Windows/Python/CUDA environment."
        ) from exc
    return np, PaddleOCR


def create_paddle_ocr(PaddleOCR: Any, paddle_lang: str) -> Any:
    init_attempts = (
        {
            "lang": paddle_lang,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {
            "lang": paddle_lang,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": True,
        },
        {"lang": paddle_lang},
        {"use_angle_cls": True, "lang": paddle_lang},
    )
    errors: list[str] = []
    for kwargs in init_attempts:
        try:
            return PaddleOCR(**kwargs)
        except Exception as exc:
            errors.append(f"{kwargs}: {redact_text(exc)}")
    raise ProbeError("PaddleOCR failed to initialize. Details: " + " | ".join(errors))


def call_paddle_ocr(ocr: Any, image_array: Any) -> Any:
    call_attempts = (
        ("predict", {}),
        ("ocr", {}),
        ("ocr", {"cls": True}),
    )
    errors: list[str] = []
    for method_name, kwargs in call_attempts:
        method = getattr(ocr, method_name, None)
        if method is None:
            continue
        try:
            return method(image_array, **kwargs)
        except TypeError as exc:
            errors.append(f"{method_name}{kwargs}: {redact_text(exc)}")
        except Exception as exc:
            errors.append(f"{method_name}{kwargs}: {redact_text(exc)}")
    raise ProbeError("PaddleOCR call failed. Details: " + " | ".join(errors))


def load_rapidocr_dependency() -> tuple[Any, Any]:
    try:
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError("RapidOCR requires numpy. Suggested start: python -m pip install numpy rapidocr-onnxruntime") from exc
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

        return np, RapidOCR
    except ImportError:
        try:
            from rapidocr import RapidOCR  # type: ignore[import-not-found]

            return np, RapidOCR
        except ImportError as exc:
            raise ProbeError(
                "RapidOCR is not available. It is an optional P0.8 fallback after PaddleOCR. "
                "Suggested start: python -m pip install rapidocr-onnxruntime"
            ) from exc


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


def preprocess_for_paddle_profiles(image: Any) -> list[tuple[Any, dict[str, Any]]]:
    try:
        from PIL import Image, ImageEnhance, ImageFilter  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError("Missing Pillow preprocessing helpers.") from exc

    source = image.convert("RGB")
    width, height = source.size
    resample = getattr(getattr(Image, "Resampling", object), "LANCZOS", 1)

    def scaled(scale: int) -> Any:
        return source.resize((width * scale, height * scale), resample=resample)

    profile_images: list[tuple[str, int, Any, dict[str, Any]]] = [
        ("rgb_original", 1, source, {"rgb": True, "sharpen": False, "contrast": None}),
        ("rgb_2x", 2, scaled(2), {"rgb": True, "sharpen": False, "contrast": None}),
        ("rgb_3x", 3, scaled(3), {"rgb": True, "sharpen": False, "contrast": None}),
    ]

    enhanced = ImageEnhance.Contrast(scaled(2)).enhance(1.35).filter(ImageFilter.SHARPEN)
    profile_images.append(("rgb_2x_sharp_contrast", 2, enhanced, {"rgb": True, "sharpen": True, "contrast": 1.35}))

    return [
        (
            processed,
            {
                "profile": profile_name,
                "scale": scale,
                "grayscale": False,
                "source_width": width,
                "source_height": height,
                **details,
            },
        )
        for profile_name, scale, processed, details in profile_images
    ]


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
        details = redact_text(exc)
        language_hint = ""
        if "chi_sim" in lang or "Error opening data file" in details or "Failed loading language" in details:
            language_hint = (
                " If Chinese OCR is failing, install the Tesseract chi_sim language data or rerun with --lang eng "
                "to validate numeric fixed-region extraction first."
            )
        raise ProbeError(
            "OCR failed. Ensure the Tesseract binary is installed and the requested language data exists. "
            f"{language_hint}Details: {details}"
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
    if isinstance(raw_result, list) and raw_result and isinstance(raw_result[0], dict):
        lines = []
        for page in raw_result:
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            polys = page.get("rec_polys")
            boxes = page.get("rec_boxes")
            for index, text in enumerate(texts):
                if polys is not None and index < len(polys):
                    points = polys[index]
                    if hasattr(points, "tolist"):
                        points = points.tolist()
                elif boxes is not None and index < len(boxes):
                    box = boxes[index]
                    if hasattr(box, "tolist"):
                        box = box.tolist()
                    if len(box) >= 4:
                        left, top, right, bottom = box[:4]
                        points = [[left, top], [right, top], [right, bottom], [left, bottom]]
                    else:
                        continue
                else:
                    continue
                confidence = scores[index] if index < len(scores) else 0
                lines.append((points, (text, confidence)))
        return lines
    if isinstance(raw_result, list) and raw_result and isinstance(raw_result[0], list):
        first = raw_result[0]
        if first and isinstance(first[0], list) and len(first[0]) == 2 and isinstance(first[0][1], tuple):
            return first
    return raw_result


def parse_paddle_blocks(raw_result: Any, *, region_name: str, region_box: dict[str, int], scale: float) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
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
    return blocks


def block_quality_score(blocks: list[dict[str, Any]]) -> tuple[int, int, float]:
    cjk_count = sum(1 for block in blocks if CJK_RE.search(str(block.get("text", ""))))
    confidence_sum = sum(float(block.get("confidence") or 0) for block in blocks)
    return (cjk_count, len(blocks), confidence_sum)


def run_paddle_on_region(
    image: Any,
    *,
    lang: str,
    region_name: str,
    region_box: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    np, PaddleOCR = load_paddle_dependency()
    crop = image.crop((region_box["left"], region_box["top"], region_box["right"], region_box["bottom"]))
    paddle_lang = paddle_lang_from_tesseract_lang(lang)
    try:
        if paddle_lang not in PADDLE_OCR_CACHE:
            PADDLE_OCR_CACHE[paddle_lang] = create_paddle_ocr(PaddleOCR, paddle_lang)
        ocr = PADDLE_OCR_CACHE[paddle_lang]
    except Exception as exc:
        raise ProbeError(f"PaddleOCR failed. Details: {redact_text(exc)}") from exc

    candidates: list[tuple[tuple[int, int, float], list[dict[str, Any]], dict[str, Any]]] = []
    errors: list[str] = []
    for processed, preprocess_info in preprocess_for_paddle_profiles(crop):
        if preprocess_info.get("profile") != "rgb_original":
            errors.append(f"{preprocess_info.get('profile')}: skipped; stable PaddleOCR batch route uses rgb_original only")
            continue
        if float(preprocess_info["scale"]) > 2:
            errors.append(f"{preprocess_info.get('profile')}: skipped; PaddleOCR Windows CPU backend is unstable above 2x")
            continue
        if max(processed.size) > 4000:
            errors.append(
                f"{preprocess_info.get('profile')}: skipped; processed side {max(processed.size)} exceeds PaddleOCR max_side_limit"
            )
            continue
        try:
            raw_result = call_paddle_ocr(ocr, np.array(processed.convert("RGB")))
            blocks = parse_paddle_blocks(
                raw_result,
                region_name=region_name,
                region_box=region_box,
                scale=float(preprocess_info["scale"]),
            )
            candidates.append((block_quality_score(blocks), blocks, preprocess_info))
        except Exception as exc:
            errors.append(f"{preprocess_info.get('profile')}: {redact_text(exc)}")
    if not candidates:
        raise ProbeError("PaddleOCR failed for all preprocessing profiles. Details: " + " | ".join(errors))
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_blocks, best_preprocess = candidates[0]
    best_preprocess = dict(best_preprocess)
    best_preprocess["profile_scores"] = [
        {
            "profile": item[2].get("profile"),
            "cjk_blocks": item[0][0],
            "text_blocks": item[0][1],
            "confidence_sum": round(item[0][2], 3),
        }
        for item in candidates
    ]
    best_preprocess["selected_score"] = {
        "cjk_blocks": best_score[0],
        "text_blocks": best_score[1],
        "confidence_sum": round(best_score[2], 3),
    }
    if errors:
        best_preprocess["profile_errors"] = errors
    return best_blocks, best_preprocess


def parse_rapidocr_blocks(raw_result: Any, *, region_name: str, region_box: dict[str, int], scale: float) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(raw_result, tuple):
        raw_result = raw_result[0]
    if not raw_result:
        return blocks
    for item in raw_result:
        try:
            points, text, confidence = item[0], item[1], item[2]
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
        except Exception:
            continue
        text = redact_text(text).strip()
        if not text:
            continue
        conf_percent = float(confidence) * 100 if float(confidence) <= 1 else float(confidence)
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
    return blocks


def run_rapidocr_on_region(
    image: Any,
    *,
    lang: str,
    region_name: str,
    region_box: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    np, RapidOCR = load_rapidocr_dependency()
    if "default" not in RAPID_OCR_CACHE:
        try:
            RAPID_OCR_CACHE["default"] = RapidOCR()
        except Exception as exc:
            raise ProbeError(f"RapidOCR failed to initialize. Details: {redact_text(exc)}") from exc
    ocr = RAPID_OCR_CACHE["default"]
    crop = image.crop((region_box["left"], region_box["top"], region_box["right"], region_box["bottom"]))
    processed, preprocess_info = preprocess_for_paddle_profiles(crop)[1]
    try:
        raw_result = ocr(np.array(processed.convert("RGB")))
    except Exception as exc:
        raise ProbeError(f"RapidOCR failed. Details: {redact_text(exc)}") from exc
    blocks = parse_rapidocr_blocks(
        raw_result,
        region_name=region_name,
        region_box=region_box,
        scale=float(preprocess_info["scale"]),
    )
    preprocess_info = dict(preprocess_info)
    preprocess_info["engine_note"] = "RapidOCR optional fallback after PaddleOCR"
    preprocess_info["lang_requested"] = lang
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
    if engine == "auto":
        errors = []
        for candidate in ("paddle", "tesseract"):
            try:
                blocks, preprocess_info = ocr_region(
                    image,
                    engine=candidate,
                    lang=lang,
                    region_name=region_name,
                    region_box=region_box,
                    config=config,
                )
                preprocess_info = dict(preprocess_info)
                preprocess_info["engine_used"] = candidate
                if errors:
                    preprocess_info["auto_fallback_errors"] = errors
                return blocks, preprocess_info
            except ProbeError as exc:
                errors.append(f"{candidate}: {exc}")
        joined_errors = " | ".join(errors)
        raise ProbeError(
            "No OCR engine is available for --engine auto. Tried PaddleOCR first, then Tesseract. "
            "Install PaddleOCR with: python -m pip install paddleocr. "
            "Or install Pillow/pytesseract plus the Tesseract desktop binary and language data, then rerun with "
            "--engine tesseract. You can also use --engine none to test layout output without OCR. "
            f"Details: {joined_errors}"
        )
    if engine == "none":
        return [], {"scale": 1, "grayscale": False, "contrast": None, "ocr_skipped": True}
    if engine == "tesseract":
        return run_tesseract_on_region(image, lang=lang, region_name=region_name, region_box=region_box, config=config)
    if engine == "paddle":
        return run_paddle_on_region(image, lang=lang, region_name=region_name, region_box=region_box)
    if engine == "rapidocr":
        return run_rapidocr_on_region(image, lang=lang, region_name=region_name, region_box=region_box)
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
        preprocess_info = dict(preprocess_info)
        preprocess_info.setdefault("engine_used", engine)
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


def normalize_candidate_value(value: Any) -> str:
    return re.sub(r"\s+", "", str(value)).strip().casefold()


def value_has_invalid_candidate(value: Any) -> bool:
    if value in (None, "", []):
        return False
    if isinstance(value, str):
        return normalize_candidate_value(value) in {normalize_candidate_value(item) for item in INVALID_CANDIDATE_VALUES}
    if isinstance(value, list):
        return any(value_has_invalid_candidate(item) for item in value)
    if isinstance(value, dict):
        return any(value_has_invalid_candidate(item) for item in value.values())
    return False


def infer_field_status(value: Any, uncertain: bool) -> str:
    if value in (None, "", []):
        return "missing"
    if value_has_invalid_candidate(value):
        return "invalid_candidate"
    if uncertain:
        return "uncertain"
    return "ok"


def field(value: Any = None, *, uncertain: bool = True, evidence: list[str] | None = None, source_region: str | None = None) -> dict[str, Any]:
    cleaned = redact_text(value).strip() if isinstance(value, str) else value
    if cleaned == "":
        cleaned = None
    status = infer_field_status(cleaned, bool(uncertain if cleaned is not None else True))
    return {
        "value": cleaned,
        "uncertain": status != "ok",
        "status": status,
        "evidence": evidence or [],
        "source_region": source_region,
    }


def empty_draft(game: str | None) -> dict[str, Any]:
    return {
        "game": game,
        "source_type": "official_export_image",
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
        "warnings": [],
        "uncertain": True,
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


def crop_box_tuple(box: dict[str, int]) -> tuple[int, int, int, int]:
    return (
        int(box.get("left", 0)),
        int(box.get("top", 0)),
        int(box.get("right", int(box.get("left", 0)) + int(box.get("width", 0)))),
        int(box.get("bottom", int(box.get("top", 0)) + int(box.get("height", 0)))),
    )


def crop_specs(
    *,
    game: str | None,
    layout: str,
    layout_regions: list[dict[str, Any]],
    image_info: dict[str, Any],
) -> list[dict[str, Any]]:
    if game != "zzz" or layout != "zzz-agent-card":
        return []

    width = int(image_info.get("width", 0))
    height = int(image_info.get("height", 0))
    if width <= 0 or height <= 0:
        return []

    region_by_name = {str(region.get("name")): region for region in layout_regions}
    specs: list[dict[str, Any]] = []

    def add(field_path: str, filename: str, box: dict[str, int]) -> None:
        if box.get("width", 0) > 0 and box.get("height", 0) > 0:
            specs.append({"field_path": field_path, "filename": filename, "box": box})

    character_box = ratio_box_to_pixels((0.015, 0.085, 0.315, 0.365), width, height)
    add("character.name", "character_name.png", character_box)
    add("character.level", "character_level.png", character_box)
    add("character.rank", "character_rank.png", character_box)

    for zone in ZZZ_CORE_STAT_ZONES:
        add(f"stats.{zone.field}", f"stat_{zone.field}.png", ratio_box_to_pixels(zone.box_ratio, width, height))

    for index, zone in enumerate(ZZZ_SKILL_ZONES, start=1):
        add(f"skill_levels[{index}].level", f"skill_{index}.png", ratio_box_to_pixels(zone, width, height))

    add("equipment.name", "equipment_name.png", ratio_box_to_pixels((0.115, 0.380, 0.320, 0.435), width, height))
    add("equipment.level", "equipment_level.png", ratio_box_to_pixels((0.120, 0.415, 0.230, 0.455), width, height))
    add("equipment.rank", "equipment_rank.png", ratio_box_to_pixels((0.860, 0.380, 0.965, 0.455), width, height))

    for slot in range(1, 7):
        region = region_by_name.get(f"drive_disc_{slot}", {})
        region_box = region.get("box")
        if not isinstance(region_box, dict):
            region_box = ratio_box_to_pixels(ZZZ_AGENT_CARD_REGIONS[6 + slot].box_ratio, width, height)
        add(f"drive_discs[{slot}].set_name", f"drive_disc_{slot}_set_name.png", local_ratio_box(region_box, (0.035, 0.030, 0.780, 0.220)))
        add(f"drive_discs[{slot}].level", f"drive_disc_{slot}_level.png", local_ratio_box(region_box, (0.650, 0.020, 0.965, 0.220)))
        add(f"drive_discs[{slot}].main_stat", f"drive_disc_{slot}_main_stat.png", local_ratio_box(region_box, (0.035, 0.235, 0.965, 0.430)))
        add(f"drive_discs[{slot}].sub_stats", f"drive_disc_{slot}_sub_stats.png", local_ratio_box(region_box, (0.035, 0.430, 0.965, 0.970)))

    return specs


def write_field_crops(
    result: dict[str, Any],
    image_path: Path,
    crop_output_dir: Path,
) -> list[dict[str, Any]]:
    specs = crop_specs(
        game=result.get("metadata", {}).get("game"),
        layout=result.get("metadata", {}).get("layout"),
        layout_regions=result.get("layout_regions", []),
        image_info=result.get("image", {}),
    )
    if not specs:
        return []

    Image = load_image_dependency()
    crop_output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    with Image.open(image_path) as image:
        for spec in specs:
            box = spec["box"]
            output_path = crop_output_dir / spec["filename"]
            image.crop(crop_box_tuple(box)).save(output_path)
            outputs.append(
                {
                    "field_path": spec["field_path"],
                    "path": relative_or_redacted(output_path),
                    "box": box,
                }
            )
    return outputs


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


def extracted_value(item: Any) -> Any:
    if isinstance(item, dict) and {"value", "uncertain", "evidence", "source_region"}.issubset(item.keys()):
        return item.get("value")
    return None


def field_status(item: Any) -> str:
    if not isinstance(item, dict) or not {"value", "uncertain", "evidence", "source_region"}.issubset(item.keys()):
        return "missing"
    status = item.get("status")
    if status in {"ok", "missing", "uncertain", "invalid_candidate"}:
        return str(status)
    return infer_field_status(item.get("value"), bool(item.get("uncertain")))


def field_is_trusted(item: Any) -> bool:
    return field_status(item) == "ok"


def field_has_present_value(item: Any) -> bool:
    return extracted_value(item) not in (None, "", [])


def trusted_values(fields: Iterable[Any]) -> list[Any]:
    return [extracted_value(item) for item in fields if field_is_trusted(item)]


def target_coverage_fields(draft: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    character = draft.get("character", {})
    stats = draft.get("stats", {})
    equipment = draft.get("equipment", {})
    skill_levels = draft.get("skill_levels", [])
    drive_discs = draft.get("drive_discs", [])

    return [
        ("character_name", [character.get("name")]),
        ("character_level", [character.get("level")]),
        ("rank", [character.get("rank")]),
        ("hp", [stats.get("hp")]),
        ("atk", [stats.get("atk")]),
        ("def", [stats.get("def")]),
        ("impact", [stats.get("impact")]),
        ("crit_rate", [stats.get("crit_rate")]),
        ("crit_dmg", [stats.get("crit_dmg")]),
        ("anomaly_mastery", [stats.get("anomaly_mastery")]),
        ("anomaly_proficiency", [stats.get("anomaly_proficiency")]),
        ("skill_levels", [item.get("level") for item in skill_levels if isinstance(item, dict)]),
        ("equipment_name", [equipment.get("name")]),
        ("equipment_level", [equipment.get("level")]),
        ("drive_disc_sets", [item.get("set_name") for item in drive_discs if isinstance(item, dict)]),
        ("drive_disc_levels", [item.get("level") for item in drive_discs if isinstance(item, dict)]),
        ("drive_disc_main_stats", [item.get("main_stat") for item in drive_discs if isinstance(item, dict)]),
        ("drive_disc_sub_stats", [item.get("sub_stats") for item in drive_discs if isinstance(item, dict)]),
    ]


def trusted_field_count(items: Iterable[Any]) -> int:
    return sum(1 for item in items if field_is_trusted(item))


def trusted_sub_stat_disc_count(drive_discs: list[Any]) -> int:
    count = 0
    for disc in drive_discs:
        if not isinstance(disc, dict):
            continue
        sub_stats = disc.get("sub_stats")
        if not field_is_trusted(sub_stats):
            continue
        value = extracted_value(sub_stats)
        if not isinstance(value, list):
            continue
        if any(isinstance(item, dict) and item.get("stat") and item.get("value") not in (None, "") for item in value):
            count += 1
    return count


def coverage_metrics(draft: dict[str, Any]) -> dict[str, Any]:
    character = draft.get("character", {})
    stats = draft.get("stats", {})
    equipment = draft.get("equipment", {})
    skill_levels = draft.get("skill_levels", [])
    drive_discs = draft.get("drive_discs", [])
    stat_items = [stats.get(name) for name in TRUSTED_NUMERIC_STAT_FIELDS]
    skill_items = [item.get("level") for item in skill_levels if isinstance(item, dict)]
    drive_level_items = [item.get("level") for item in drive_discs if isinstance(item, dict)]
    drive_main_items = [item.get("main_stat") for item in drive_discs if isinstance(item, dict)]

    return {
        "character_name_ok": field_is_trusted(character.get("name")),
        "character_level_ok": field_is_trusted(character.get("level")),
        "character_rank_ok": field_is_trusted(character.get("rank")),
        "core_stats_trusted": trusted_field_count(stat_items),
        "core_stats_total": len(TRUSTED_NUMERIC_STAT_FIELDS),
        "skill_levels_trusted": trusted_field_count(skill_items),
        "skill_levels_total": 6,
        "equipment_name_ok": field_is_trusted(equipment.get("name")),
        "equipment_level_ok": field_is_trusted(equipment.get("level")),
        "equipment_rank_ok": field_is_trusted(equipment.get("rank")),
        "drive_disc_levels_trusted": trusted_field_count(drive_level_items),
        "drive_disc_main_stats_trusted": trusted_field_count(drive_main_items),
        "drive_disc_sub_stat_discs_trusted": trusted_sub_stat_disc_count(drive_discs if isinstance(drive_discs, list) else []),
    }


def summarize_coverage(draft: dict[str, Any], blocks: list[dict[str, Any]]) -> dict[str, Any]:
    matched_fields: list[str] = []
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    detailed_matched_fields: list[str] = []
    detailed_missing_fields: list[str] = []
    detailed_invalid_fields: list[str] = []
    numeric_fields_detected: list[dict[str, Any]] = []
    chinese_fields_detected: list[dict[str, Any]] = []

    for path, item in walk_fields(draft):
        value = item.get("value")
        status = field_status(item)
        if status == "invalid_candidate":
            detailed_invalid_fields.append(path)
        if field_is_trusted(item):
            detailed_matched_fields.append(path)
        elif status == "invalid_candidate":
            detailed_missing_fields.append(path)
        else:
            detailed_missing_fields.append(path)

    for target_name, fields in target_coverage_fields(draft):
        values_present = trusted_values(fields)
        if any(field_status(item) == "invalid_candidate" for item in fields):
            invalid_fields.append(target_name)
        if values_present:
            matched_fields.append(target_name)
            value: Any = values_present[0] if len(values_present) == 1 else values_present
            value_text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
            if NUMERIC_RE.search(value_text):
                numeric_fields_detected.append({"field": target_name, "value": value})
            if CJK_RE.search(value_text):
                chinese_fields_detected.append({"field": target_name, "value": value})
        else:
            missing_fields.append(target_name)

    total_fields = len(matched_fields) + len(missing_fields)
    matched_ratio = len(matched_fields) / total_fields if total_fields else 0
    numeric_raw_count = sum(1 for block in blocks if numeric_tokens(str(block.get("text", ""))))
    chinese_raw_count = sum(1 for block in blocks if CJK_RE.search(str(block.get("text", ""))))
    metrics = coverage_metrics(draft)

    hard_low_reasons: list[str] = []
    high_blockers: list[str] = []
    if metrics["drive_disc_main_stats_trusted"] == 0:
        hard_low_reasons.append("drive_disc_main_stats 全缺")
    if metrics["drive_disc_sub_stat_discs_trusted"] == 0:
        hard_low_reasons.append("drive_disc_sub_stats 全缺")
    if invalid_fields:
        high_blockers.append("存在 invalid_candidate 字段")
    if not metrics["character_name_ok"]:
        high_blockers.append("character.name 缺失或不可信")
    if not metrics["character_level_ok"]:
        high_blockers.append("character.level 缺失或不可信")
    if not metrics["character_rank_ok"]:
        high_blockers.append("character.rank 缺失或不可信")
    if metrics["core_stats_trusted"] < 10:
        high_blockers.append("核心属性可信字段少于 10/11")
    if metrics["skill_levels_trusted"] < 6:
        high_blockers.append("六个技能等级未全部可信")
    if not metrics["equipment_name_ok"]:
        high_blockers.append("equipment.name 缺失或为泛词")
    if not metrics["equipment_level_ok"]:
        high_blockers.append("equipment.level 缺失或不可信")
    if not metrics["equipment_rank_ok"]:
        high_blockers.append("equipment.rank 缺失或不可信")
    if metrics["drive_disc_levels_trusted"] < 6:
        high_blockers.append("drive_disc level 可信数量少于 6")
    if metrics["drive_disc_main_stats_trusted"] < 4:
        high_blockers.append("drive_disc_main_stats 可信数量少于 4")
    if metrics["drive_disc_sub_stat_discs_trusted"] < 4:
        high_blockers.append("drive_disc_sub_stats 可信盘数少于 4")

    if not high_blockers:
        coverage_level = "high"
        recommendation = "字段覆盖较完整，可以继续做人工确认页和 fixture 回放；仍不要直接写正式数据库。"
    elif hard_low_reasons:
        coverage_level = "low"
        recommendation = "解析可信度失败：" + "；".join(hard_low_reasons) + "。请继续修 OCR、裁剪区域或字段抽取规则，不得进入导入。"
    elif metrics["core_stats_trusted"] >= 8 and metrics["skill_levels_trusted"] >= 4 and (
        not metrics["character_name_ok"] or not metrics["equipment_name_ok"]
    ):
        coverage_level = "numeric_only"
        recommendation = "当前主要是数字字段可用，关键中文字段或装备/驱动盘字段不可信；只能用于版面调试，不能进入 fixture/导入。"
    elif matched_ratio >= 0.35 or len(numeric_fields_detected) >= 8 or numeric_raw_count >= 12:
        coverage_level = "medium"
        recommendation = "部分字段可用于人工比对，但仍有关键字段缺失或不确定；需要人工确认后再决定是否继续 fixture 回放。"
    else:
        coverage_level = "low"
        recommendation = "当前只能证明图片可离线处理；建议先确认版式、语言包和裁剪区域，再考虑字段抽取 prototype。"

    return {
        "matched_fields": matched_fields,
        "missing_fields": missing_fields,
        "invalid_fields": invalid_fields,
        "numeric_fields_detected": numeric_fields_detected,
        "chinese_fields_detected": chinese_fields_detected,
        "detailed_matched_fields": detailed_matched_fields,
        "detailed_missing_fields": detailed_missing_fields,
        "detailed_invalid_fields": detailed_invalid_fields,
        "coverage_metrics": metrics,
        "high_blockers": high_blockers,
        "hard_low_reasons": hard_low_reasons,
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


def write_outputs(
    result: dict[str, Any],
    output_dir: Path,
    image_path: Path,
    *,
    write_crops: bool = False,
    crop_output_dir: Path | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(image_path)
    if write_crops and image_path.exists() and result.get("image"):
        crop_root = crop_output_dir or DEFAULT_CROP_OUTPUT_DIR
        crop_dir = crop_root / stem
        result["crop_outputs"] = write_field_crops(result, image_path, crop_dir)
    elif write_crops:
        result["crop_outputs"] = []
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
    crops = result.get("crop_outputs", [])
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
                f"- matched: {markdown_cell(', '.join(coverage.get('matched_fields', [])), 240)}",
                f"- missing: {markdown_cell(', '.join(coverage.get('missing_fields', [])), 240)}",
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
        lines.extend(["## Layout Regions", "", "| name | engine | box | text blocks | text sample |", "|---|---|---|---:|---|"])
        for region in regions:
            box = region.get("box", {})
            preprocess = region.get("preprocess", {})
            box_text = f"{box.get('left')},{box.get('top')},{box.get('width')},{box.get('height')}"
            lines.append(
                "| "
                f"{markdown_cell(region.get('name'))} | "
                f"{markdown_cell(preprocess.get('engine_used') or meta.get('ocr_engine'))} | "
                f"{markdown_cell(box_text)} | "
                f"{region.get('text_block_count', 0)} | "
                f"{markdown_cell(region.get('text'), 160)} |"
            )
        lines.append("")

    if crops:
        lines.extend(["## Field Crops", "", "| field | crop | box |", "|---|---|---|"])
        for crop in crops:
            box = crop.get("box", {})
            box_text = f"{box.get('left')},{box.get('top')},{box.get('width')},{box.get('height')}"
            lines.append(
                "| "
                f"{markdown_cell(crop.get('field_path'), 120)} | "
                f"{markdown_cell(crop.get('path'), 180)} | "
                f"{markdown_cell(box_text)} |"
            )
        lines.append("")

    if coverage:
        lines.extend(["## 缺失字段", ""])
        missing_fields = coverage.get("missing_fields", [])
        if missing_fields:
            for item in missing_fields:
                lines.append(f"- {markdown_cell(item, 120)}")
        else:
            lines.append("- 无")
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

    lines.extend(
        [
            "## 下一步建议",
            "",
            f"- {markdown_cell(coverage.get('recommendation'), 220)}",
            "- 所有字段仍需人工确认后才能进入任何正式数据库。",
            "- 若中文字段缺失但数字字段较稳定，优先尝试 PaddleOCR 或安装 Tesseract chi_sim 语言包。",
            "- 若固定区域连续错位，先用同一张图校准 zzz-agent-card 裁剪比例，再考虑批量解析。",
            "",
        ]
    )
    return "\n".join(lines)


def validate_args(args: argparse.Namespace) -> None:
    if args.layout == "zzz-agent-card" and args.game != "zzz":
        raise ProbeError("--layout zzz-agent-card requires --game zzz.")


def actual_ocr_engines(layout_regions: list[dict[str, Any]]) -> set[str]:
    engines = set()
    for region in layout_regions:
        preprocess = region.get("preprocess", {})
        engine = preprocess.get("engine_used")
        if engine:
            engines.add(str(engine))
    return engines


def route_uses_tesseract_eng(engine: str, lang: str, layout_regions: list[dict[str, Any]]) -> bool:
    lowered_lang = lang.casefold().replace(" ", "")
    english_only = lowered_lang in {"eng", "en"}
    if not english_only:
        return False
    if engine == "tesseract":
        return True
    engines = actual_ocr_engines(layout_regions)
    return bool(engines) and engines == {"tesseract"}


def apply_ocr_route_recommendation(result: dict[str, Any], *, engine: str, lang: str) -> None:
    coverage = result.get("coverage_summary", {})
    metadata = result.get("metadata", {})
    notes = metadata.setdefault("notes", [])
    if engine == "paddle":
        metadata["ocr_route"] = "paddle_recommended"
        coverage["ocr_recommendation"] = "PaddleOCR 是当前真实中文分享图的推荐路线；继续用 expected diff 和 crop 输出校准字段。"
        return
    if engine == "rapidocr":
        metadata["ocr_route"] = "rapidocr_optional_fallback"
        coverage["ocr_recommendation"] = "RapidOCR 是 PaddleOCR 不达标后的可选 OCR fallback；仍必须以 expected diff pass_rate 验收。"
        return
    if route_uses_tesseract_eng(engine, lang, result.get("layout_regions", [])):
        metadata["ocr_route"] = "tesseract_eng_numeric_debug_only"
        note = "Tesseract eng 只适合固定区域数字调试，不可作为可导入解析结果。真实图片请优先使用 --engine paddle。"
        if note not in notes:
            notes.append(note)
        coverage["ocr_recommendation"] = note
        if coverage.get("coverage_level") == "high":
            coverage["coverage_level"] = "numeric_only"
        recommendation = str(coverage.get("recommendation") or "")
        if "Tesseract eng 只适合固定区域数字调试" not in recommendation:
            coverage["recommendation"] = note + (" " + recommendation if recommendation else "")
        return
    if engine == "auto":
        metadata["ocr_route"] = "auto_paddle_first"
        coverage["ocr_recommendation"] = "auto 会先尝试 PaddleOCR；真实图片识别率不足时请显式运行 --engine paddle 并查看 PaddleOCR 安装错误。"


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
                "For real Chinese share images, prefer --engine paddle; tesseract eng is numeric-debug only.",
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
        apply_ocr_route_recommendation(result, engine=engine, lang=lang)
        return result, 0
    except ProbeError as exc:
        result["errors"].append(str(exc))
        result["summary"] = summarize_entities([], result["extracted_draft"])
        result["coverage_summary"] = summarize_coverage(result["extracted_draft"], [])
        apply_ocr_route_recommendation(result, engine=engine, lang=lang)
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
        choices=("auto", "tesseract", "paddle", "rapidocr", "none"),
        default="auto",
        help="OCR engine. Default: auto (PaddleOCR first, then Tesseract). Use --engine paddle for real share-image OCR.",
    )
    parser.add_argument("--game", choices=("zzz", "hsr"), default=None, help="Game layout hint: zzz or hsr.")
    parser.add_argument(
        "--layout",
        choices=("full", "zzz-agent-card"),
        default="full",
        help="Layout strategy. Default: full. zzz-agent-card requires --game zzz.",
    )
    parser.add_argument(
        "--write-crops",
        action="store_true",
        help="Write field-level crop images for key acceptance fields under data/probes/crops/.",
    )
    parser.add_argument(
        "--crop-output-dir",
        default=str(DEFAULT_CROP_OUTPUT_DIR),
        help="Crop output directory. Default: data/probes/crops",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    image_path = Path(args.image).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    crop_output_dir = Path(args.crop_output_dir).expanduser()
    if not crop_output_dir.is_absolute():
        crop_output_dir = PROJECT_ROOT / crop_output_dir

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

    json_path, md_path = write_outputs(
        result,
        output_dir,
        image_path,
        write_crops=args.write_crops,
        crop_output_dir=crop_output_dir,
    )
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    if args.write_crops:
        print(f"Wrote field crops: {len(result.get('crop_outputs', []))}")
    if result.get("errors"):
        print("OCR probe did not complete successfully:", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
