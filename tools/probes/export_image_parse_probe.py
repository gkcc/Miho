#!/usr/bin/env python
"""OCR/layout probe for official MiYouShe exported/share images."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "parsed"

SECRET_VALUE_RE = re.compile(
    r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b"
    r"(\s*[:=]\s*)"
    r"([^,\s;\"']+)"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEYED_ID_RE = re.compile(r"(?i)\b(uid|account_id|accountid|user_id|userid)\b(\s*[:=：]?\s*)\d{4,}")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")

FIELD_RULES = [
    ("Character", re.compile(r"(角色|代理人|开拓者|名称|Name|Lv\.?|等级|星魂|影画)", re.IGNORECASE)),
    ("CharacterBuildSnapshot", re.compile(r"(等级|属性|生命|攻击|防御|速度|暴击|暴伤|击破|异常|精通|充能)", re.IGNORECASE)),
    ("Equipment", re.compile(r"(音擎|光锥|武器|装备|叠影|精炼|等级)", re.IGNORECASE)),
    ("SkillOrTrace", re.compile(r"(技能|行迹|普攻|战技|终结技|天赋|秘技|核心技|普通攻击|特殊技|连携技|支援)", re.IGNORECASE)),
    ("ArtifactOrDriveDisc", re.compile(r"(遗器|饰品|位面|驱动盘|套装|主词条|副词条|部位)", re.IGNORECASE)),
]


class ProbeError(RuntimeError):
    pass


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


def load_ocr_dependencies() -> tuple[Any, Any]:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError(
            "Missing OCR image dependency 'Pillow'. Install it if you want to parse exported images: "
            "python -m pip install pillow pytesseract"
        ) from exc

    try:
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError(
            "Missing OCR dependency 'pytesseract'. Install it if you want OCR parsing: "
            "python -m pip install pytesseract"
        ) from exc

    return Image, pytesseract


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


def run_tesseract(image_path: Path, lang: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    Image, pytesseract = load_ocr_dependencies()
    image = Image.open(image_path)
    image_info = {
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "format": image.format,
    }

    try:
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        raise ProbeError(
            "OCR failed. Ensure the Tesseract binary is installed and the requested language data exists. "
            f"Details: {redact_text(exc)}"
        ) from exc

    blocks: list[dict[str, Any]] = []
    total = len(data.get("text", []))
    for index in range(total):
        text = redact_text(data["text"][index]).strip()
        if not text:
            continue
        conf = parse_confidence(data.get("conf", [])[index])
        classification = classify_text(text, conf)
        blocks.append(
            {
                "text": text,
                "box": {
                    "left": int(data["left"][index]),
                    "top": int(data["top"][index]),
                    "width": int(data["width"][index]),
                    "height": int(data["height"][index]),
                },
                "ocr_confidence_raw": conf,
                "candidate_entities": classification["candidate_entities"],
                "confidence": classification["confidence"],
                "uncertain": classification["uncertain"],
            }
        )

    return image_info, blocks


def summarize_entities(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    entity_counts: dict[str, int] = {}
    uncertain_count = 0
    for block in blocks:
        if block.get("uncertain"):
            uncertain_count += 1
        for label in block.get("candidate_entities", []):
            entity_counts[label] = entity_counts.get(label, 0) + 1

    adr_entities = ["Character", "CharacterBuildSnapshot", "Equipment", "SkillOrTrace", "ArtifactOrDriveDisc"]
    return {
        "text_block_count": len(blocks),
        "uncertain_count": uncertain_count,
        "entity_counts": entity_counts,
        "adr_0003_matches": {entity: entity_counts.get(entity, 0) > 0 for entity in adr_entities},
    }


def write_outputs(result: dict[str, Any], output_dir: Path, image_path: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem(image_path)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def render_markdown(result: dict[str, Any]) -> str:
    meta = result["metadata"]
    summary = result.get("summary", {})
    blocks = result.get("text_blocks", [])
    errors = result.get("errors", [])

    lines = [
        "# 官方导出/分享图解析 Probe",
        "",
        "## 摘要",
        "",
        f"- 创建时间：{markdown_cell(meta.get('created_at'), 120)}",
        f"- 输入图片：{markdown_cell(meta.get('input_image'), 160)}",
        f"- OCR 引擎：{markdown_cell(meta.get('ocr_engine'))}",
        f"- 文本块数量：{summary.get('text_block_count', 0)}",
        f"- 不确定文本块：{summary.get('uncertain_count', 0)}",
        "",
        "## ADR-0003 匹配",
        "",
    ]

    for entity, matched in summary.get("adr_0003_matches", {}).items():
        lines.append(f"- {entity}: {matched}")
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
            "| text | box | entities | confidence | uncertain |",
            "|---|---|---|---:|---|",
        ]
    )
    for block in blocks[:300]:
        box = block.get("box", {})
        box_text = f"{box.get('left')},{box.get('top')},{box.get('width')},{box.get('height')}"
        lines.append(
            "| "
            f"{markdown_cell(block.get('text'), 120)} | "
            f"{markdown_cell(box_text)} | "
            f"{markdown_cell(', '.join(block.get('candidate_entities', [])), 120)} | "
            f"{block.get('confidence')} | "
            f"{block.get('uncertain')} |"
        )
    if len(blocks) > 300:
        lines.append(f"| ... | ... | ... | ... | 还有 {len(blocks) - 300} 个文本块 |")
    lines.append("")
    return "\n".join(lines)


def build_result(image_path: Path, lang: str) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {
        "metadata": {
            "probe": "export_image_parse_probe",
            "created_at": now_iso(),
            "input_image": relative_or_redacted(image_path),
            "ocr_engine": "pytesseract",
            "lang": lang,
            "notes": [
                "Prototype only. Not a formal collector.",
                "Does not overwrite the input image and does not write a formal database.",
            ],
        },
        "image": {},
        "summary": {},
        "text_blocks": [],
        "errors": [],
    }

    if not image_path.exists():
        result["errors"].append(f"Input image does not exist: {relative_or_redacted(image_path)}")
        return result, 2
    if not image_path.is_file():
        result["errors"].append(f"Input path is not a file: {relative_or_redacted(image_path)}")
        return result, 2

    try:
        image_info, blocks = run_tesseract(image_path, lang)
        result["image"] = image_info
        result["text_blocks"] = blocks
        result["summary"] = summarize_entities(blocks)
        return result, 0
    except ProbeError as exc:
        result["errors"].append(str(exc))
        result["summary"] = summarize_entities([])
        return result, 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR/layout probe for official MiYouShe exported/share images. Does not overwrite images or write a formal DB."
    )
    parser.add_argument("--image", required=True, help="Local image path to parse.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/parsed")
    parser.add_argument("--lang", default="chi_sim+eng", help="Tesseract language string. Default: chi_sim+eng")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    image_path = Path(args.image).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    result, exit_code = build_result(image_path, args.lang)
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
