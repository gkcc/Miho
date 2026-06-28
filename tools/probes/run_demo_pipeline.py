#!/usr/bin/env python
"""Run the local Miho probe demo pipeline and render a dashboard."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import diff_normalized_snapshots as normalized_diff  # noqa: E402
import evaluate_export_parse as evaluator  # noqa: E402
import normalize_export_parse as normalizer  # noqa: E402
import plan_training_priorities as planner  # noqa: E402
import render_demo_dashboard as dashboard  # noqa: E402
import render_export_review as review_render  # noqa: E402


DEFAULT_IMAGES_DIR = PROJECT_ROOT / "figs"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_EXPECTED_DIR = PROJECT_ROOT / "data" / "probes" / "expected"
UPDATE_STATE_FILENAME = "update_state.json"
SNAPSHOT_HISTORY_DIRNAME = "snapshot_history"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PARSED_DIR_HISTORY_WARNING_CASES = 5
MODE_OCR_FRESH_IMAGE = "OCR fresh image mode"
MODE_PARSED_REPLAY = "parsed replay mode"
MODE_MANIFEST_CONTROLLED = "manifest controlled mode"
SNAPSHOT_HISTORY_SCHEMA = "p1.1-snapshot-history-draft"


class DemoPipelineError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    return normalizer.load_json(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    normalizer.write_json(path, data)


def path_or_none(value: str | None) -> Path | None:
    return Path(value).resolve() if value else None


def field_value(item: Any) -> Any:
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    return item


def normalized_character(normalized: dict[str, Any] | None) -> dict[str, Any]:
    character = normalized.get("character", {}) if isinstance(normalized, dict) else {}
    return {
        "name": field_value(character.get("name")) if isinstance(character, dict) else None,
        "level": field_value(character.get("level")) if isinstance(character, dict) else None,
        "rank": field_value(character.get("rank")) if isinstance(character, dict) else None,
    }


def normalized_equipment(normalized: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = normalized.get("build_snapshot", {}) if isinstance(normalized, dict) else {}
    equipment = snapshot.get("equipment", {}) if isinstance(snapshot, dict) else {}
    return {
        "name": field_value(equipment.get("name")) if isinstance(equipment, dict) else None,
        "level": field_value(equipment.get("level")) if isinstance(equipment, dict) else None,
        "rank": field_value(equipment.get("rank")) if isinstance(equipment, dict) else None,
    }


def empty_quality() -> dict[str, Any]:
    return {
        "trusted_field_count": 0,
        "field_count": 0,
        "requires_manual_review": True,
        "blockers": [],
    }


def source_image_from_parsed(parsed: dict[str, Any]) -> str | None:
    metadata = parsed.get("metadata", {}) if isinstance(parsed.get("metadata"), dict) else {}
    image = metadata.get("input_image")
    return str(image) if image else None


def review_status_from_parsed(parsed: dict[str, Any]) -> tuple[str | None, str | None]:
    draft = parsed.get("extracted_draft", {}) if isinstance(parsed.get("extracted_draft"), dict) else {}
    coverage = review_render.normalized_coverage_for_review(parsed.get("coverage_summary", {}), draft)
    return review_render.review_status(coverage, draft), coverage.get("coverage_level")


def image_files(images_dir: Path) -> list[Path]:
    if not images_dir.exists():
        raise DemoPipelineError(f"Images directory does not exist: {images_dir}")
    if not images_dir.is_dir():
        raise DemoPipelineError(f"Images path is not a directory: {images_dir}")
    return sorted(path for path in images_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": sha256_file(path),
    }


def load_update_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "p1.4-update-state-draft", "images": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoPipelineError(f"Invalid update state JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise DemoPipelineError(f"Expected update state object: {path}")
    if not isinstance(data.get("images"), dict):
        data["images"] = {}
    data.setdefault("schema_version", "p1.4-update-state-draft")
    return data


def image_update_records(paths: list[Path], state: dict[str, Any], new_only: bool) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    selected: list[Path] = []
    images = state.get("images", {}) if isinstance(state.get("images"), dict) else {}
    for path in paths:
        fingerprint = image_fingerprint(path)
        previous = images.get(fingerprint["path"])
        if not isinstance(previous, dict):
            status = "new"
        elif previous.get("sha256") == fingerprint["sha256"]:
            status = "unchanged"
        else:
            status = "changed"
        should_process = (not new_only) or status in {"new", "changed"}
        if should_process:
            selected.append(path)
        records.append(
            {
                "image": fingerprint["path"],
                "name": fingerprint["name"],
                "sha256": fingerprint["sha256"],
                "size": fingerprint["size"],
                "mtime": fingerprint["mtime"],
                "previous_sha256": previous.get("sha256") if isinstance(previous, dict) else None,
                "status": status,
                "processed": should_process,
            }
        )
    return records, selected


def update_case_state_entry(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": record["image"],
        "name": record["name"],
        "sha256": record["sha256"],
        "size": record["size"],
        "mtime": record["mtime"],
        "last_seen_at": normalizer.now_iso(),
        "last_processed_at": normalizer.now_iso() if record.get("processed") else None,
        "update_status": record["status"],
        "review_status": case.get("review_status"),
        "coverage_level": case.get("coverage_level"),
        "parsed_json": case.get("parsed_json"),
        "normalized_json": case.get("normalized_json"),
        "character": case.get("character"),
        "equipment": case.get("equipment"),
        "errors": case.get("errors", []),
    }


def write_update_state(path: Path, state: dict[str, Any], records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> None:
    images = state.get("images", {}) if isinstance(state.get("images"), dict) else {}
    case_by_image = {}
    for case in cases:
        if case.get("image"):
            case_by_image[str(Path(str(case["image"])).resolve())] = case
    for record in records:
        if not record.get("processed"):
            continue
        case = case_by_image.get(record["image"], {})
        images[record["image"]] = update_case_state_entry(case, record)
    state["images"] = images
    state["updated_at"] = normalizer.now_iso()
    write_json(path, state)


def safe_history_key(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("._")
    return (text[:80] or "unknown_character")


def safe_timestamp() -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", normalizer.now_iso()).strip("_")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def load_snapshot_history_index(history_dir: Path) -> dict[str, Any]:
    index_path = history_dir / "index.json"
    if not index_path.exists():
        return {"schema_version": SNAPSHOT_HISTORY_SCHEMA, "characters": {}}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoPipelineError(f"Invalid snapshot history index JSON: {index_path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise DemoPipelineError(f"Snapshot history index must be an object: {index_path}")
    if not isinstance(data.get("characters"), dict):
        data["characters"] = {}
    data.setdefault("schema_version", SNAPSHOT_HISTORY_SCHEMA)
    return data


def case_history_identity(case: dict[str, Any]) -> tuple[str, str]:
    character = case.get("character", {}) if isinstance(case.get("character"), dict) else {}
    name = character.get("name") or case.get("name") or "unknown_character"
    return str(name), safe_history_key(name)


def build_snapshot_history(cases: list[dict[str, Any]], history_dir: Path) -> dict[str, Any]:
    history_dir.mkdir(parents=True, exist_ok=True)
    index = load_snapshot_history_index(history_dir)
    characters = index.get("characters", {}) if isinstance(index.get("characters"), dict) else {}
    items: list[dict[str, Any]] = []
    timestamp = safe_timestamp()
    for case in cases:
        if not case.get("normalized_json"):
            continue
        source_path = Path(str(case["normalized_json"]))
        if not source_path.exists():
            continue
        character_name, key = case_history_identity(case)
        character_dir = history_dir / "characters" / key
        character_dir.mkdir(parents=True, exist_ok=True)
        current_path = unique_path(character_dir / f"{timestamp}_{safe_history_key(source_path.stem)}.json")
        shutil.copy2(source_path, current_path)
        previous_entry = characters.get(key) if isinstance(characters.get(key), dict) else {}
        previous_snapshot = previous_entry.get("latest_snapshot") if isinstance(previous_entry, dict) else None
        previous_path = Path(str(previous_snapshot)) if previous_snapshot else None
        item: dict[str, Any] = {
            "character": character_name,
            "key": key,
            "case_name": case.get("name"),
            "current_snapshot": str(current_path),
            "previous_snapshot": str(previous_path) if previous_path and previous_path.exists() else None,
            "diff_json": None,
            "diff_md": None,
            "change_count": 0,
            "requires_review_change_count": 0,
            "status": "first_snapshot",
            "error": None,
        }
        if previous_path and previous_path.exists():
            try:
                diff = normalized_diff.diff_files(previous_path, current_path, history_dir / "diffs" / key)
                item.update(
                    {
                        "diff_json": diff.get("output_json"),
                        "diff_md": diff.get("output_md"),
                        "change_count": diff.get("summary", {}).get("change_count", 0),
                        "requires_review_change_count": diff.get("summary", {}).get("requires_review_change_count", 0),
                        "status": "diffed",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                item["status"] = "diff_failed"
                item["error"] = str(exc)
        case["snapshot_history"] = item
        items.append(item)
        characters[key] = {
            "character": character_name,
            "latest_snapshot": str(current_path),
            "last_seen_at": normalizer.now_iso(),
            "case_name": case.get("name"),
            "source_image": case.get("image"),
            "review_status": case.get("review_status"),
            "coverage_level": case.get("coverage_level"),
            "normalized_json": case.get("normalized_json"),
        }
    index["schema_version"] = SNAPSHOT_HISTORY_SCHEMA
    index["updated_at"] = normalizer.now_iso()
    index["characters"] = characters
    index_path = history_dir / "index.json"
    write_json(index_path, index)
    return {
        "schema_version": SNAPSHOT_HISTORY_SCHEMA,
        "history_dir": str(history_dir),
        "index_json": str(index_path),
        "snapshot_count": len(items),
        "diff_count": sum(1 for item in items if item.get("diff_md")),
        "changed_character_count": sum(1 for item in items if int(item.get("change_count") or 0) > 0),
        "no_previous_count": sum(1 for item in items if item.get("status") == "first_snapshot"),
        "diff_failed_count": sum(1 for item in items if item.get("status") == "diff_failed"),
        "items": items,
    }


def build_update_summary(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {"new": 0, "changed": 0, "unchanged": 0}
    for record in records:
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "state_file": str(path),
        "discovered_image_count": len(records),
        "processed_image_count": sum(1 for record in records if record.get("processed")),
        "skipped_unchanged_count": sum(1 for record in records if record.get("status") == "unchanged" and not record.get("processed")),
        "status_counts": counts,
        "records": records,
    }


def parsed_files(parsed_dir: Path) -> list[Path]:
    if not parsed_dir.exists():
        raise DemoPipelineError(f"Parsed directory does not exist: {parsed_dir}")
    if not parsed_dir.is_dir():
        raise DemoPipelineError(f"Parsed path is not a directory: {parsed_dir}")
    paths = []
    for path in sorted(parsed_dir.glob("*.json")):
        try:
            data = load_json(path)
        except normalizer.NormalizeError:
            continue
        if isinstance(data.get("extracted_draft"), dict):
            paths.append(path)
    return paths


def parsed_case_key(path: Path, parsed: dict[str, Any]) -> str:
    image = source_image_from_parsed(parsed)
    if image:
        return Path(image).stem
    stem = path.stem
    if "_parsed_" in stem:
        return stem.split("_parsed_", 1)[0]
    return stem


def parsed_sort_key(path: Path) -> tuple[str, float, str]:
    timestamp = ""
    if "_parsed_" in path.stem:
        timestamp = path.stem.split("_parsed_", 1)[1]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return timestamp, mtime, path.name


def latest_parsed_files(parsed_dir: Path) -> list[Path]:
    grouped: dict[str, Path] = {}
    for path in parsed_files(parsed_dir):
        try:
            parsed = load_json(path)
        except normalizer.NormalizeError:
            continue
        key = parsed_case_key(path, parsed)
        current = grouped.get(key)
        if current is None or parsed_sort_key(path) > parsed_sort_key(current):
            grouped[key] = path
    return sorted(grouped.values())


def manifest_cases(manifest: Path) -> list[dict[str, Any]]:
    if not manifest.exists():
        raise DemoPipelineError(f"Manifest does not exist: {manifest}")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoPipelineError(f"Invalid manifest JSON: {manifest}. Details: {exc}") from exc
    raw_cases: Any
    if isinstance(data, dict):
        raw_cases = data.get("cases")
    elif isinstance(data, list):
        raw_cases = data
    else:
        raw_cases = None
    if not isinstance(raw_cases, list):
        raise DemoPipelineError("Manifest must be a list or an object with a cases list")
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(raw_cases, start=1):
        if isinstance(item, str):
            path = resolve_path(item)
            key = "image" if path.suffix.lower() in IMAGE_EXTENSIONS else "parsed"
            cases.append({"name": path.stem, key: str(path)})
            continue
        if not isinstance(item, dict):
            raise DemoPipelineError(f"Manifest case #{index} must be an object or path")
        case = dict(item)
        if "image" in case:
            case["image"] = str(resolve_path(str(case["image"])))
        if "parsed" in case:
            case["parsed"] = str(resolve_path(str(case["parsed"])))
        if "image" not in case and "parsed" not in case:
            raise DemoPipelineError(f"Manifest case #{index} must include image or parsed")
        case.setdefault("name", Path(str(case.get("image") or case.get("parsed"))).stem)
        cases.append(case)
    return cases


def expected_candidates(stem: str, expected_dir: Path) -> list[Path]:
    return [
        expected_dir / f"{stem}_expected.json",
        expected_dir / f"{stem}.expected.json",
        expected_dir / f"{stem}_expected_template.json",
    ]


def find_expected(*, image_path: Path | None, parsed_path: Path | None, parsed: dict[str, Any] | None, expected_dir: Path) -> Path | None:
    stems: list[str] = []
    if image_path:
        stems.append(image_path.stem)
    if parsed_path:
        stems.append(parsed_path.stem)
    if parsed:
        image_text = source_image_from_parsed(parsed)
        if image_text:
            stems.append(Path(image_text).stem)
    for stem in dict.fromkeys(stems):
        for candidate in expected_candidates(stem, expected_dir):
            if candidate.exists():
                return candidate.resolve()
    return None


def nearby_review_html(parsed_path: Path) -> str | None:
    candidate = parsed_path.with_name(f"{parsed_path.stem}_review.html")
    return str(candidate.resolve()) if candidate.exists() else None


def case_template(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "image": None,
        "thumbnail": None,
        "parsed_json": None,
        "parsed_markdown": None,
        "review_html": None,
        "overlay_png": None,
        "normalized_json": None,
        "normalized_md": None,
        "expected_json": None,
        "expected_json_name": None,
        "expected_diff_json": None,
        "expected_diff_md": None,
        "review_status": None,
        "coverage_level": None,
        "pass_rate": None,
        "character": {"name": None, "level": None, "rank": None},
        "equipment": {"name": None, "level": None, "rank": None},
        "quality": empty_quality(),
        "crops_dir": None,
        "errors": [],
    }


def normalize_case(parsed_path: Path, output_dir: Path, case: dict[str, Any]) -> dict[str, Any] | None:
    try:
        result = normalizer.normalize_file(parsed_path, output_dir / "normalized")
    except normalizer.NormalizeError as exc:
        case["errors"].append(f"normalize failed: {exc}")
        return None
    normalized = result["normalized"]
    case["normalized_json"] = result["normalized_json"]
    case["normalized_md"] = result["normalized_md"]
    case["character"] = normalized_character(normalized)
    case["equipment"] = normalized_equipment(normalized)
    case["quality"] = normalized.get("quality", empty_quality())
    return normalized


def evaluate_case(parsed_path: Path, expected_path: Path | None, case_dir: Path, case: dict[str, Any]) -> None:
    if expected_path is None:
        return
    case["expected_json"] = str(expected_path)
    case["expected_json_name"] = expected_path.name
    try:
        result = evaluator.evaluate_files(
            parsed_path,
            expected_path,
            case_dir / f"{parsed_path.stem}_expected_diff.json",
            case_dir / f"{parsed_path.stem}_expected_diff.md",
        )
    except evaluator.EvaluateError as exc:
        case["errors"].append(f"expected diff failed: {exc}")
        return
    case["expected_diff_json"] = result.get("output_json")
    case["expected_diff_md"] = result.get("output_md")
    case["pass_rate"] = result.get("summary", {}).get("pass_rate")


def process_image_case(
    image_path: Path,
    *,
    name: str,
    output_dir: Path,
    expected_dir: Path,
    engine: str,
    game: str,
    layout: str,
) -> dict[str, Any]:
    case = case_template(name)
    case["image"] = str(image_path)
    case["thumbnail"] = str(image_path)
    case_dir = output_dir / "cases" / name
    crop_dir = output_dir / "crops" / name
    case["crops_dir"] = str(crop_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(SCRIPT_DIR / "review_export_image.py"),
        "--image",
        str(image_path),
        "--output-dir",
        str(case_dir),
        "--engine",
        engine,
        "--lang",
        "chi_sim+eng",
        "--game",
        game,
        "--layout",
        layout,
        "--write-crops",
        "--crop-output-dir",
        str(crop_dir),
    ]
    completed = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True)
    output_values: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        output_values[key.strip()] = value.strip()
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        case["errors"].append(f"review failed: {detail}")
        return case
    case["parsed_json"] = output_values.get("parsed_json")
    case["parsed_markdown"] = output_values.get("parsed_markdown")
    case["review_html"] = output_values.get("review_html")
    case["overlay_png"] = output_values.get("overlay_png")
    case["review_status"] = output_values.get("review_status")
    case["coverage_level"] = output_values.get("coverage_level")
    parsed_path = path_or_none(case["parsed_json"])
    if not parsed_path:
        return case
    try:
        parsed = load_json(parsed_path)
    except normalizer.NormalizeError as exc:
        case["errors"].append(f"parsed JSON read failed: {exc}")
        return case
    evaluate_case(parsed_path, find_expected(image_path=image_path, parsed_path=parsed_path, parsed=parsed, expected_dir=expected_dir), case_dir, case)
    normalize_case(parsed_path, output_dir, case)
    return case


def process_parsed_case(
    parsed_path: Path,
    *,
    name: str,
    output_dir: Path,
    expected_dir: Path,
) -> dict[str, Any]:
    case = case_template(name)
    case["parsed_json"] = str(parsed_path)
    case_dir = output_dir / "cases" / name
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        parsed = load_json(parsed_path)
    except normalizer.NormalizeError as exc:
        case["errors"].append(f"parsed JSON read failed: {exc}")
        return case
    image = source_image_from_parsed(parsed)
    case["image"] = image
    case["thumbnail"] = image
    case["parsed_markdown"] = str(parsed_path.with_suffix(".md")) if parsed_path.with_suffix(".md").exists() else None
    case["review_html"] = nearby_review_html(parsed_path)
    review_status, coverage_level = review_status_from_parsed(parsed)
    case["review_status"] = review_status
    case["coverage_level"] = coverage_level
    evaluate_case(parsed_path, find_expected(image_path=Path(image) if image else None, parsed_path=parsed_path, parsed=parsed, expected_dir=expected_dir), case_dir, case)
    normalize_case(parsed_path, output_dir, case)
    return case


def pipeline_steps(summary: dict[str, Any]) -> list[dict[str, str]]:
    cases = summary.get("cases", [])
    input_info = summary.get("input", {})
    errors = [error for case in cases for error in case.get("errors", [])]
    normalized_count = summary["overall"].get("normalized_count", 0)
    expected_count = summary["overall"].get("expected_available_count", 0)
    needs_review = summary["overall"].get("requires_manual_review_count", 0)
    plan_info = summary.get("training_plan", {}) if isinstance(summary.get("training_plan"), dict) else {}
    history_info = summary.get("snapshot_history", {}) if isinstance(summary.get("snapshot_history"), dict) else {}
    return [
        {"name": "官方分享图", "status": "done" if input_info.get("images_dir") or any(case.get("image") for case in cases) else "skipped"},
        {"name": "OCR Review", "status": "failed" if errors and input_info.get("images_dir") else "done" if any(case.get("review_html") for case in cases) else "skipped"},
        {"name": "Expected Diff", "status": "done" if expected_count else "skipped"},
        {"name": "Normalized Snapshot", "status": "needs_review" if normalized_count and needs_review else "done" if normalized_count else "failed"},
        {"name": "Snapshot Diff", "status": "done" if summary.get("snapshot_diff_md") else "skipped"},
        {
            "name": "Snapshot History",
            "status": "failed" if history_info.get("diff_failed_count") else "done" if history_info.get("snapshot_count") else "skipped",
        },
        {"name": "Training Plan", "status": "failed" if plan_info.get("error") else "done" if plan_info.get("output_json") else "skipped"},
    ]


def source_mode(*, images_dir: Path | None, parsed_dir: Path | None, manifest: Path | None) -> str:
    if manifest:
        return MODE_MANIFEST_CONTROLLED
    if parsed_dir:
        return MODE_PARSED_REPLAY
    return MODE_OCR_FRESH_IMAGE


def build_warnings(cases: list[dict[str, Any]], input_info: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if input_info.get("source_mode") == MODE_PARSED_REPLAY:
        if input_info.get("latest_only"):
            warnings.append("parsed-dir 模式已启用 latest-only，仅展示每个源图最新 parsed JSON。")
        else:
            warnings.append("parsed-dir 模式会扫描历史 parsed JSON，可能包含旧失败结果；准确率验收请使用 manifest。")
        if not input_info.get("latest_only") and len(cases) > PARSED_DIR_HISTORY_WARNING_CASES:
            warnings.append("当前包含历史 parsed 结果，平均通过率不代表 P0.9 replay batch")
    update_state = input_info.get("update_state")
    if isinstance(update_state, dict) and input_info.get("new_only") and update_state.get("processed_image_count") == 0:
        warnings.append("new-only 模式没有发现新增或变更图片，本轮不会重新 OCR。")
    return warnings


def summarize(cases: list[dict[str, Any]], output_dir: Path, input_info: dict[str, Any], snapshot_history: dict[str, Any] | None = None) -> dict[str, Any]:
    parse_success_count = sum(1 for case in cases if case.get("parsed_json"))
    review_counts: dict[str, int] = {}
    pass_rates = []
    normalized_paths = []
    requires_review = 0
    for case in cases:
        review_status = case.get("review_status") or "N/A"
        review_counts[review_status] = review_counts.get(review_status, 0) + 1
        if case.get("pass_rate") is not None:
            pass_rates.append(float(case["pass_rate"]))
        if case.get("normalized_json"):
            normalized_paths.append(Path(case["normalized_json"]))
        if case.get("quality", {}).get("requires_manual_review"):
            requires_review += 1
    errors = [error for case in cases for error in case.get("errors", [])]
    if not cases:
        conclusion = "没有发现可处理的图片或 parsed JSON。"
    elif errors:
        conclusion = "Demo pipeline 已生成 Dashboard，但部分 case 失败，请打开 case 卡片查看错误。"
    elif requires_review:
        conclusion = "已生成标准化快照；当前仍是本地 demo，需要人工确认后才能进入后续导入原型。"
    else:
        conclusion = "已生成标准化快照；当前阶段仍不会自动写入正式数据库。"
    warnings = build_warnings(cases, input_info)
    summary: dict[str, Any] = {
        "created_at": normalizer.now_iso(),
        "input": input_info,
        "output_dir": str(output_dir),
        "warnings": warnings,
        "overall": {
            "case_count": len(cases),
            "parse_success_count": parse_success_count,
            "review_status_counts": review_counts,
            "expected_available_count": sum(1 for case in cases if case.get("expected_json")),
            "average_pass_rate": round(sum(pass_rates) / len(pass_rates), 4) if pass_rates else None,
            "normalized_count": len(normalized_paths),
            "requires_manual_review_count": requires_review,
            "conclusion": conclusion,
        },
        "cases": cases,
    }
    if snapshot_history is not None:
        summary["snapshot_history"] = snapshot_history
    if len(normalized_paths) >= 2:
        try:
            diff = normalized_diff.diff_files(normalized_paths[0], normalized_paths[1], output_dir / "diff")
            summary["snapshot_diff_json"] = diff.get("output_json")
            summary["snapshot_diff_md"] = diff.get("output_md")
        except Exception as exc:  # noqa: BLE001
            summary["snapshot_diff_error"] = str(exc)
    summary["pipeline_steps"] = pipeline_steps(summary)
    return summary


def build_training_plan(cases: list[dict[str, Any]], targets_path: Path | None, output_dir: Path) -> dict[str, Any] | None:
    if targets_path is None:
        return None
    normalized_paths = [Path(str(case["normalized_json"])) for case in cases if case.get("normalized_json")]
    plan_info: dict[str, Any] = {
        "targets_json": str(targets_path),
        "snapshot_count": len(normalized_paths),
        "output_json": None,
        "output_md": None,
        "plan_item_count": 0,
        "top_plan_items": [],
        "warnings": [],
        "error": None,
    }
    if not normalized_paths:
        plan_info["error"] = "No normalized snapshots available for planner."
        return plan_info
    try:
        report = planner.generate_report(normalized_paths, targets_path, output_dir / "planner")
    except planner.PlannerError as exc:
        plan_info["error"] = str(exc)
        return plan_info
    plan_info.update(
        {
            "output_json": report.get("output_json"),
            "output_md": report.get("output_md"),
            "plan_item_count": len(report.get("plan_items", [])) if isinstance(report.get("plan_items"), list) else 0,
            "top_plan_items": report.get("plan_items", [])[:5] if isinstance(report.get("plan_items"), list) else [],
            "warnings": report.get("warnings", []) if isinstance(report.get("warnings"), list) else [],
        }
    )
    return plan_info


def clean_demo_output_dir(output_dir: Path) -> None:
    resolved = output_dir.resolve()
    allowed_root = (PROJECT_ROOT / "data" / "probes").resolve()
    if not resolved.exists():
        return
    if not resolved.is_dir():
        raise DemoPipelineError(f"Clean target is not a directory: {resolved}")
    if resolved == allowed_root or allowed_root not in resolved.parents:
        raise DemoPipelineError(f"--clean-demo only cleans subdirectories under {allowed_root}: {resolved}")
    shutil.rmtree(resolved)


def run_pipeline(
    *,
    images_dir: Path | None,
    parsed_dir: Path | None,
    manifest: Path | None,
    output_dir: Path,
    expected_dir: Path = DEFAULT_EXPECTED_DIR,
    engine: str = "paddle",
    game: str = "zzz",
    layout: str = "zzz-agent-card",
    open_dashboard: bool = False,
    latest_only: bool = False,
    clean_demo: bool = False,
    targets: Path | None = None,
    new_only: bool = False,
    state_file: Path | None = None,
    history_dir: Path | None = None,
) -> dict[str, Any]:
    if clean_demo:
        clean_demo_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    input_info = {
        "images_dir": str(images_dir) if images_dir else None,
        "parsed_dir": str(parsed_dir) if parsed_dir else None,
        "manifest": str(manifest) if manifest else None,
        "source_mode": source_mode(images_dir=images_dir, parsed_dir=parsed_dir, manifest=manifest),
        "latest_only": bool(latest_only),
        "clean_demo": bool(clean_demo),
        "targets": str(targets) if targets else None,
        "new_only": bool(new_only),
        "state_file": str(state_file) if state_file else None,
        "history_dir": str(history_dir or (output_dir / SNAPSHOT_HISTORY_DIRNAME)),
    }
    if manifest:
        for raw in manifest_cases(manifest):
            if raw.get("image"):
                image_path = Path(str(raw["image"]))
                cases.append(
                    process_image_case(
                        image_path,
                        name=str(raw.get("name") or image_path.stem),
                        output_dir=output_dir,
                        expected_dir=expected_dir,
                        engine=engine,
                        game=game,
                        layout=layout,
                    )
                )
            elif raw.get("parsed"):
                parsed_path = Path(str(raw["parsed"]))
                cases.append(
                    process_parsed_case(
                        parsed_path,
                        name=str(raw.get("name") or parsed_path.stem),
                        output_dir=output_dir,
                        expected_dir=expected_dir,
                    )
                )
    elif parsed_dir:
        active_parsed_files = latest_parsed_files(parsed_dir) if latest_only else parsed_files(parsed_dir)
        for parsed_path in active_parsed_files:
            cases.append(process_parsed_case(parsed_path, name=parsed_path.stem, output_dir=output_dir, expected_dir=expected_dir))
    else:
        active_images_dir = images_dir or DEFAULT_IMAGES_DIR
        input_info["images_dir"] = str(active_images_dir)
        active_state_file = state_file or (output_dir / UPDATE_STATE_FILENAME)
        input_info["state_file"] = str(active_state_file)
        state = load_update_state(active_state_file)
        update_records, selected_images = image_update_records(image_files(active_images_dir), state, new_only)
        input_info["update_state"] = build_update_summary(active_state_file, update_records)
        for image_path in selected_images:
            cases.append(
                process_image_case(
                    image_path,
                    name=image_path.stem,
                    output_dir=output_dir,
                    expected_dir=expected_dir,
                    engine=engine,
                    game=game,
                    layout=layout,
                )
            )
        write_update_state(active_state_file, state, update_records, cases)

    snapshot_history = build_snapshot_history(cases, history_dir or (output_dir / SNAPSHOT_HISTORY_DIRNAME))
    summary = summarize(cases, output_dir, input_info, snapshot_history)
    if isinstance(input_info.get("update_state"), dict):
        summary["update_state"] = input_info["update_state"]
    training_plan = build_training_plan(cases, targets, output_dir)
    if training_plan is not None:
        summary["training_plan"] = training_plan
        if training_plan.get("warnings"):
            summary.setdefault("warnings", []).extend(training_plan["warnings"])
        if training_plan.get("error"):
            summary.setdefault("warnings", []).append(f"Training plan failed: {training_plan['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    summary_path = output_dir / "demo_summary.json"
    write_json(summary_path, summary)
    dashboard_path = output_dir / "index.html"
    dashboard.render_dashboard(summary, dashboard_path)
    summary["summary_json"] = str(summary_path)
    summary["dashboard_html"] = str(dashboard_path)
    write_json(summary_path, summary)
    if open_dashboard:
        webbrowser.open(dashboard_path.resolve().as_uri())
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Miho probe demo pipeline and render a dashboard.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--images-dir", default=None, help="Directory of local official share images. Default: figs.")
    source.add_argument("--parsed-dir", default=None, help="Directory of parsed JSON files. Does not rerun OCR.")
    source.add_argument("--manifest", default=None, help="Demo manifest with image or parsed cases.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/demo.")
    parser.add_argument("--expected-dir", default=str(DEFAULT_EXPECTED_DIR), help="Expected JSON directory. Default: data/probes/expected.")
    parser.add_argument("--engine", choices=("auto", "tesseract", "paddle", "rapidocr", "none"), default="paddle", help="OCR engine for image mode. Default: paddle.")
    parser.add_argument("--game", choices=("zzz", "hsr"), default="zzz", help="Game hint. Default: zzz.")
    parser.add_argument("--layout", choices=("full", "zzz-agent-card"), default="zzz-agent-card", help="Layout hint. Default: zzz-agent-card.")
    parser.add_argument("--open", action="store_true", help="Open generated dashboard in the default browser.")
    parser.add_argument("--latest-only", action="store_true", help="In parsed-dir mode, keep only the newest parsed JSON for each source image.")
    parser.add_argument("--new-only", action="store_true", help="In image mode, process only new or changed images according to the update state file.")
    parser.add_argument("--clean-demo", action="store_true", help="Clean the demo output directory before running. Limited to data/probes subdirectories.")
    parser.add_argument("--state-file", default=None, help="Image update state JSON. Default: <output-dir>/update_state.json.")
    parser.add_argument("--targets", default=None, help="Optional planner targets JSON. Generates a local training priority report from normalized snapshots.")
    parser.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        summary = run_pipeline(
            images_dir=resolve_path(args.images_dir) if args.images_dir else None,
            parsed_dir=resolve_path(args.parsed_dir) if args.parsed_dir else None,
            manifest=resolve_path(args.manifest) if args.manifest else None,
            output_dir=resolve_path(args.output_dir),
            expected_dir=resolve_path(args.expected_dir),
            engine=args.engine,
            game=args.game,
            layout=args.layout,
            open_dashboard=args.open,
            latest_only=args.latest_only,
            clean_demo=args.clean_demo,
            targets=resolve_path(args.targets) if args.targets else None,
            new_only=args.new_only,
            state_file=resolve_path(args.state_file) if args.state_file else None,
            history_dir=resolve_path(args.history_dir) if args.history_dir else None,
        )
    except (DemoPipelineError, normalizer.NormalizeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    overall = summary["overall"]
    print(f"mode: {summary['input'].get('source_mode')}")
    for warning in summary.get("warnings", []):
        print(f"warning: {warning}")
    print(f"case_count: {overall['case_count']}")
    print(f"parse_success_count: {overall['parse_success_count']}")
    print(f"normalized_count: {overall['normalized_count']}")
    print(f"requires_manual_review_count: {overall['requires_manual_review_count']}")
    if isinstance(summary.get("update_state"), dict):
        print(f"processed_image_count: {summary['update_state'].get('processed_image_count', 0)}")
        print(f"skipped_unchanged_count: {summary['update_state'].get('skipped_unchanged_count', 0)}")
    if isinstance(summary.get("training_plan"), dict):
        print(f"plan_item_count: {summary['training_plan'].get('plan_item_count', 0)}")
    if isinstance(summary.get("snapshot_history"), dict):
        print(f"history_snapshot_count: {summary['snapshot_history'].get('snapshot_count', 0)}")
        print(f"history_diff_count: {summary['snapshot_history'].get('diff_count', 0)}")
        print(f"history_changed_character_count: {summary['snapshot_history'].get('changed_character_count', 0)}")
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
