#!/usr/bin/env python
"""Extract a redacted ZZZ roster JSON from an official MiYouShe box image.

This probe is intentionally local-only. It reads a user-provided image, runs OCR
over the visible roster grid, and writes only normalized roster fields. Header
UID/nickname OCR is not persisted.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = PROJECT_ROOT / "tools" / "probes"
SCHEMA_VERSION = "p0.1-zzz-box-roster-image"
RAPID_OCR_INSTANCE: Any | None = None
RAPID_OCR_NUMPY: Any | None = None

COUNT_RE = re.compile(r"招募\s*(\d{1,3})\s*名代理人")
LV_RE = re.compile(r"(?i)\bL\s*[Vv]\.?\s*(\d{1,3})\b")
DIGIT_RE = re.compile(r"([1-6])")

REFERENCE_WIDTH = 1449.0
REFERENCE_HEIGHT = 3658.0
COL_CENTER_RATIOS = [216 / REFERENCE_WIDTH, 553 / REFERENCE_WIDTH, 890 / REFERENCE_WIDTH, 1228 / REFERENCE_WIDTH]
ROW_TOP_RATIOS = [310 / REFERENCE_HEIGHT, 825 / REFERENCE_HEIGHT, 1338 / REFERENCE_HEIGHT, 1854 / REFERENCE_HEIGHT, 2368 / REFERENCE_HEIGHT, 2882 / REFERENCE_HEIGHT]
NAME_Y_OFFSET = 408 / REFERENCE_HEIGHT
LEVEL_Y_OFFSET = 305 / REFERENCE_HEIGHT
MIND_X0_OFFSET = 57 / REFERENCE_WIDTH
MIND_X1_OFFSET = 157 / REFERENCE_WIDTH
MIND_Y0_OFFSET = -48 / REFERENCE_HEIGHT
MIND_Y1_OFFSET = 72 / REFERENCE_HEIGHT

CANONICAL_CN_BY_SLUG = {
    "billy-starlight": "星徽·比利",
    "qingyi": "青衣",
    "zhu-yuan": "朱鸢",
    "ellen": "艾莲",
    "koleda": "珂蕾妲",
    "pan-yinhu": "潘引壶",
    "soukaku": "苍角",
    "nicole-demara": "妮可",
    "anby-demara": "安比",
    "billy-kid": "比利",
    "corin": "可琳",
    "piper": "派派",
    "lucy": "露西",
    "velina": "维琳娜",
    "orphie-and-magus": "奥菲丝&「鬼火」",
    "nekomata": "猫又",
    "manato": "真斗",
    "pulchra": "波可娜",
    "seth": "赛斯",
    "ben": "本",
    "anton": "安东",
}


@dataclass(frozen=True)
class OcrBlock:
    text: str
    confidence: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass(frozen=True)
class GridSlot:
    index: int
    row: int
    col: int
    center_x: float
    row_top: float
    name_y: float
    level_y: float


class BoxRosterExtractError(RuntimeError):
    pass


def load_tool(module_name: str, filename: str) -> Any:
    import_name = Path(filename).stem
    try:
        return importlib.import_module(import_name)
    except ImportError:
        pass
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise BoxRosterExtractError(f"Cannot load tool module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


value_tool = load_tool("build_agent_value_cards_for_box_extract", "build_agent_value_cards.py")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_image_dependency() -> Any:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency message path
        raise BoxRosterExtractError("Missing dependency Pillow. Install with: python -m pip install pillow") from exc
    return Image


def load_rapidocr_dependency() -> tuple[Any, Any]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency message path
        raise BoxRosterExtractError("Missing dependency numpy. Install with: python -m pip install numpy") from exc
    try:
        from rapidocr_onnxruntime import RapidOCR

        return np, RapidOCR
    except ImportError:
        pass
    try:
        from rapidocr import RapidOCR  # type: ignore[import-not-found]

        return np, RapidOCR
    except ImportError as exc:  # pragma: no cover - dependency message path
        raise BoxRosterExtractError(
            "Missing dependency RapidOCR. Install with: python -m pip install rapidocr-onnxruntime"
        ) from exc


def get_rapidocr() -> tuple[Any, Any]:
    global RAPID_OCR_INSTANCE, RAPID_OCR_NUMPY
    if RAPID_OCR_INSTANCE is None or RAPID_OCR_NUMPY is None:
        np, RapidOCR = load_rapidocr_dependency()
        RAPID_OCR_NUMPY = np
        RAPID_OCR_INSTANCE = RapidOCR()
    return RAPID_OCR_NUMPY, RAPID_OCR_INSTANCE


def run_rapidocr(image: Any) -> list[Any]:
    np, ocr = get_rapidocr()
    raw = ocr(np.array(image.convert("RGB")))
    if isinstance(raw, tuple):
        result = raw[0]
    else:
        result = raw
    return result or []


def normalize_ocr_blocks(raw_result: list[Any], *, scale: float) -> list[OcrBlock]:
    blocks: list[OcrBlock] = []
    for item in raw_result:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        points, text, confidence = item[0], item[1], item[2]
        try:
            xs = [float(point[0]) / scale for point in points]
            ys = [float(point[1]) / scale for point in points]
            conf = float(confidence)
        except (TypeError, ValueError, IndexError):
            continue
        clean_text = str(text or "").strip()
        if not clean_text:
            continue
        blocks.append(
            OcrBlock(
                text=clean_text,
                confidence=conf,
                left=min(xs),
                top=min(ys),
                right=max(xs),
                bottom=max(ys),
            )
        )
    return blocks


def build_aliases(meta_snapshot: Path | None = None) -> dict[str, str]:
    aliases = dict(value_tool.CN_ALIAS_TO_SLUG)
    if meta_snapshot and meta_snapshot.exists():
        try:
            tier_entries = value_tool.tier_by_slug(load_json(meta_snapshot))
            aliases.update(value_tool.slug_aliases(tier_entries))
        except Exception:
            pass
    return {value_tool.normalize_name(key): value for key, value in aliases.items() if key}


def match_agent_text(text: str, aliases: dict[str, str]) -> tuple[str | None, str | None]:
    normalized = value_tool.normalize_name(str(text).replace("...", "").replace("…", ""))
    if not normalized:
        return None, None
    if "奥菲丝" in normalized and "鬼" in normalized:
        return "orphie-and-magus", CANONICAL_CN_BY_SLUG["orphie-and-magus"]
    if normalized in aliases:
        slug = aliases[normalized]
        return slug, CANONICAL_CN_BY_SLUG.get(slug, text)
    best_slug: str | None = None
    best_len = 0
    for alias, slug in aliases.items():
        if len(alias) < 2:
            continue
        if alias in normalized or normalized in alias:
            if len(alias) > best_len:
                best_slug = slug
                best_len = len(alias)
    if best_slug:
        return best_slug, CANONICAL_CN_BY_SLUG.get(best_slug, text)
    return None, None


def extract_level(text: str) -> int | None:
    match = LV_RE.search(str(text).replace(" ", ""))
    if not match:
        match = LV_RE.search(str(text))
    if not match:
        return None
    level = int(match.group(1))
    if 1 <= level <= 70:
        return level
    return None


def extract_count_claim(blocks: list[OcrBlock]) -> int | None:
    for block in blocks:
        match = COUNT_RE.search(block.text)
        if match:
            return int(match.group(1))
    return None


def build_grid_slots(width: int, height: int, count: int | None) -> list[GridSlot]:
    max_slots = count if count else len(ROW_TOP_RATIOS) * len(COL_CENTER_RATIOS)
    slots: list[GridSlot] = []
    for row, row_top_ratio in enumerate(ROW_TOP_RATIOS, start=1):
        row_top = row_top_ratio * height
        for col, center_ratio in enumerate(COL_CENTER_RATIOS, start=1):
            index = len(slots) + 1
            if index > max_slots:
                return slots
            center_x = center_ratio * width
            slots.append(
                GridSlot(
                    index=index,
                    row=row,
                    col=col,
                    center_x=center_x,
                    row_top=row_top,
                    name_y=row_top + NAME_Y_OFFSET * height,
                    level_y=row_top + LEVEL_Y_OFFSET * height,
                )
            )
    return slots


def nearest_slot(block: OcrBlock, slots: list[GridSlot], *, kind: str, width: int, height: int) -> GridSlot | None:
    target_attr = "level_y" if kind == "level" else "name_y"
    best: tuple[float, GridSlot] | None = None
    for slot in slots:
        target_y = getattr(slot, target_attr)
        score = abs(block.center_x - slot.center_x) / max(width, 1) + abs(block.center_y - target_y) / max(height, 1) * 2.0
        if best is None or score < best[0]:
            best = (score, slot)
    if best is None:
        return None
    slot = best[1]
    max_x_dist = width * 0.12
    max_y_dist = height * (0.035 if kind == "name" else 0.032)
    target_y = getattr(slot, target_attr)
    if abs(block.center_x - slot.center_x) > max_x_dist or abs(block.center_y - target_y) > max_y_dist:
        return None
    return slot


def digit_from_text(text: str) -> int | None:
    clean = str(text).strip().replace("I", "1").replace("l", "1").replace("|", "1")
    digits = DIGIT_RE.findall(clean)
    if not digits:
        return None
    if len(set(digits)) == 1:
        return int(digits[0])
    if len(digits) == 1:
        return int(digits[0])
    return None


def has_digit_like_component(np: Any, crop: Any) -> bool:
    arr = np.array(crop.convert("L"))
    mask = arr > 165
    seen = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            queue = [(x, y)]
            seen[y, x] = True
            xs: list[int] = []
            ys: list[int] = []
            for x0, y0 in queue:
                xs.append(x0)
                ys.append(y0)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x0 + dx, y0 + dy
                        if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            queue.append((nx, ny))
            area = len(xs)
            if area < 150:
                continue
            left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
            comp_width = right - left + 1
            comp_height = bottom - top + 1
            if 10 <= comp_width <= 28 and 25 <= comp_height <= 45 and 25 <= left <= 70 and 35 <= top <= 70:
                return True
    return False


def recognize_mindscape(image: Any, slot: GridSlot, *, min_confidence: float) -> tuple[int, float, str]:
    width, height = image.size
    x0 = max(0, int(slot.center_x + MIND_X0_OFFSET * width))
    x1 = min(width, int(slot.center_x + MIND_X1_OFFSET * width))
    y0 = max(0, int(slot.row_top + MIND_Y0_OFFSET * height))
    y1 = min(height, int(slot.row_top + MIND_Y1_OFFSET * height))
    if x1 <= x0 or y1 <= y0:
        return 0, 0.0, "not_detected"

    np, ocr = get_rapidocr()
    from PIL import ImageEnhance, ImageOps

    crop = image.crop((x0, y0, x1, y1)).convert("L")
    if not has_digit_like_component(np, crop):
        return 0, 0.0, "not_detected"
    candidates: list[tuple[int, float]] = []
    thresholds = (160, 190)
    for threshold in thresholds:
        arr = np.array(crop)
        mask = (arr > threshold).astype("uint8") * 255
        processed = ImageOps.autocontrast(ImageEnhance.Contrast(image_from_array(np, mask)).enhance(2.0))
        processed = processed.resize((processed.width * 8, processed.height * 8))
        raw = ocr(np.array(processed.convert("RGB")))
        result = raw[0] if isinstance(raw, tuple) else raw
        for item in result or []:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            digit = digit_from_text(str(item[1]))
            if digit is None:
                continue
            try:
                confidence = float(item[2])
            except (TypeError, ValueError):
                confidence = 0.0
            candidates.append((digit, confidence))
    if not candidates:
        return 0, 0.0, "not_detected"
    digit, confidence = max(candidates, key=lambda item: item[1])
    if confidence < min_confidence:
        return digit, round(confidence, 3), "needs_review"
    return digit, round(confidence, 3), "ok"


def image_from_array(np: Any, mask: Any) -> Any:
    from PIL import Image

    return Image.fromarray(np.asarray(mask, dtype="uint8"), mode="L")


def assign_blocks_to_slots(
    *,
    blocks: list[OcrBlock],
    slots: list[GridSlot],
    aliases: dict[str, str],
    width: int,
    height: int,
) -> dict[int, dict[str, Any]]:
    slot_records: dict[int, dict[str, Any]] = {slot.index: {"slot": slot} for slot in slots}
    for block in blocks:
        level = extract_level(block.text)
        if level is not None:
            slot = nearest_slot(block, slots, kind="level", width=width, height=height)
            if slot:
                record = slot_records[slot.index]
                if "level_confidence" not in record or block.confidence > record["level_confidence"]:
                    record["level"] = level
                    record["level_text"] = block.text
                    record["level_confidence"] = round(block.confidence, 3)
            continue
        slug, name = match_agent_text(block.text, aliases)
        if slug or name:
            slot = nearest_slot(block, slots, kind="name", width=width, height=height)
            if slot:
                record = slot_records[slot.index]
                if "name_confidence" not in record or block.confidence > record["name_confidence"]:
                    record["name"] = name or block.text
                    record["agent_slug"] = slug
                    record["raw_name_text"] = block.text
                    record["name_confidence"] = round(block.confidence, 3)
    return slot_records


def slot_record_to_agent(record: dict[str, Any]) -> dict[str, Any] | None:
    slot: GridSlot = record["slot"]
    if not record.get("name") and record.get("level") is None:
        return None
    review_status = "ok"
    warnings: list[str] = []
    if not record.get("name") or not record.get("agent_slug"):
        review_status = "needs_review"
        warnings.append("name_or_slug_missing")
    if record.get("level") is None:
        review_status = "needs_review"
        warnings.append("level_missing")
    if record.get("mindscape_status") == "needs_review":
        review_status = "needs_review"
        warnings.append("mindscape_low_confidence")
    return {
        "name": record.get("name") or record.get("raw_name_text") or "",
        "agent_slug": record.get("agent_slug"),
        "level": record.get("level", 0),
        "mindscape": record.get("mindscape", 0),
        "owned": True,
        "source_slot": {"index": slot.index, "row": slot.row, "col": slot.col},
        "confidence": {
            "name": record.get("name_confidence"),
            "level": record.get("level_confidence"),
            "mindscape": record.get("mindscape_confidence"),
        },
        "raw_name_text": record.get("raw_name_text"),
        "review_status": review_status,
        "warnings": warnings,
    }


def extract_roster_from_image(
    *,
    image_path: Path,
    output_json: Path,
    meta_snapshot: Path | None = None,
    output_markdown: Path | None = None,
    ocr_scale: int = 2,
    min_mindscape_confidence: float = 0.85,
) -> dict[str, Any]:
    if not image_path.exists():
        raise BoxRosterExtractError(f"Image does not exist: {image_path}")
    Image = load_image_dependency()
    with Image.open(image_path) as loaded:
        image = loaded.convert("RGB")
    width, height = image.size
    scaled = image.resize((width * ocr_scale, height * ocr_scale))
    blocks = normalize_ocr_blocks(run_rapidocr(scaled), scale=float(ocr_scale))
    count_claim = extract_count_claim(blocks)
    slots = build_grid_slots(width, height, count_claim)
    aliases = build_aliases(meta_snapshot)
    slot_records = assign_blocks_to_slots(blocks=blocks, slots=slots, aliases=aliases, width=width, height=height)

    for record in slot_records.values():
        slot: GridSlot = record["slot"]
        mindscape, confidence, status = recognize_mindscape(
            image,
            slot,
            min_confidence=min_mindscape_confidence,
        )
        record["mindscape"] = mindscape
        record["mindscape_confidence"] = confidence
        record["mindscape_status"] = status

    agents = [agent for record in slot_records.values() if (agent := slot_record_to_agent(record))]
    warnings: list[str] = []
    if count_claim is not None and len(agents) != count_claim:
        warnings.append(f"detected_agent_count {len(agents)} does not match count_claim {count_claim}")
    if any(agent["review_status"] != "ok" for agent in agents):
        warnings.append("some_slots_need_review")
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source": {
            "image_basename": image_path.name,
            "image_size": {"width": width, "height": height},
            "meta_snapshot": str(meta_snapshot) if meta_snapshot else None,
        },
        "recognition": {
            "engine": "rapidocr",
            "layout": "miyoushe_zzz_box_grid_v1",
            "ocr_scale": ocr_scale,
            "count_claim": count_claim,
            "slot_count": len(slots),
        },
        "agents": agents,
        "summary": {
            "owned_count": len(agents),
            "mapped_count": sum(1 for agent in agents if agent.get("agent_slug")),
            "needs_review_count": sum(1 for agent in agents if agent.get("review_status") != "ok"),
        },
        "warnings": warnings,
        "privacy": {
            "header_uid_persisted": False,
            "raw_ocr_blocks_persisted": False,
            "cookie_token_read": False,
        },
    }
    write_json(output_json, result)
    if output_markdown:
        write_text(output_markdown, render_markdown(result, output_json))
    return {**result, "output_json": str(output_json), "output_markdown": str(output_markdown) if output_markdown else None}


def render_markdown(result: dict[str, Any], output_json: Path) -> str:
    lines = [
        "# ZZZ Box 截图 roster 识别",
        "",
        f"generated_at: {result.get('generated_at')}",
        f"json: {output_json}",
        f"owned_count: {result.get('summary', {}).get('owned_count')}",
        f"needs_review_count: {result.get('summary', {}).get('needs_review_count')}",
        f"count_claim: {result.get('recognition', {}).get('count_claim')}",
        "",
        "| Slot | 代理人 | 等级 | 影画 | 状态 | 置信度 |",
        "| ---: | --- | ---: | ---: | --- | --- |",
    ]
    for agent in result.get("agents", []):
        conf = agent.get("confidence", {})
        confidence = f"name={conf.get('name')} level={conf.get('level')} mind={conf.get('mindscape')}"
        lines.append(
            f"| {agent.get('source_slot', {}).get('index')} | {agent.get('name')} | {agent.get('level')} | "
            f"{agent.get('mindscape')} | {agent.get('review_status')} | {confidence} |"
        )
    lines.extend(["", "## 边界", "", "- 不保存 UID / 昵称 / header 原始 OCR。", "- 不读取 cookie/token。", "- 识别结果只作为本地探针输入，仍可人工复核。"])
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Local official MiYouShe ZZZ box image.")
    parser.add_argument("--output", default="data/probes/box/zzz_roster_from_image.json", help="Output roster JSON.")
    parser.add_argument("--markdown", default=None, help="Optional Markdown review output. Defaults to output with .md suffix.")
    parser.add_argument("--meta-snapshot", default=None, help="Optional Prydwen meta snapshot for alias mapping.")
    parser.add_argument("--ocr-scale", type=int, default=2, help="Resize factor before full-image OCR. Default: 2.")
    parser.add_argument("--min-mindscape-confidence", type=float, default=0.85)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv or sys.argv[1:])
    output_json = resolve_path(args.output)
    output_markdown = resolve_path(args.markdown) if args.markdown else output_json.with_suffix(".md")
    try:
        result = extract_roster_from_image(
            image_path=resolve_path(args.image),
            output_json=output_json,
            meta_snapshot=resolve_path(args.meta_snapshot) if args.meta_snapshot else None,
            output_markdown=output_markdown,
            ocr_scale=args.ocr_scale,
            min_mindscape_confidence=args.min_mindscape_confidence,
        )
    except BoxRosterExtractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"roster_json: {result['output_json']}")
    print(f"roster_markdown: {result['output_markdown']}")
    print(f"owned_count: {result['summary']['owned_count']}")
    print(f"mapped_count: {result['summary']['mapped_count']}")
    print(f"needs_review_count: {result['summary']['needs_review_count']}")
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")
    return 0 if result["summary"]["needs_review_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
