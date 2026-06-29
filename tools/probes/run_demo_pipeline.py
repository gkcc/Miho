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
import build_action_cards as action_cards  # noqa: E402
import build_action_checklist as action_checklist  # noqa: E402
import build_endgame_plan as endgame_plan  # noqa: E402
import build_final_brief as final_brief  # noqa: E402
import build_run_manifest as run_manifest  # noqa: E402
import build_roster_delta as roster_delta  # noqa: E402
import build_team_cards as team_cards  # noqa: E402
import build_tier_watchlist as tier_watchlist  # noqa: E402
import preview_review_decisions as review_preview  # noqa: E402
import normalize_export_parse as normalizer  # noqa: E402
import plan_training_priorities as planner  # noqa: E402
import prepare_endgame_targets as target_intake  # noqa: E402
import render_demo_dashboard as dashboard  # noqa: E402
import render_export_review as review_render  # noqa: E402


DEFAULT_IMAGES_DIR = PROJECT_ROOT / "figs"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_EXPECTED_DIR = PROJECT_ROOT / "data" / "probes" / "expected"
DEFAULT_ROSTER_DIR = PROJECT_ROOT / "data" / "probes" / "roster"
UPDATE_STATE_FILENAME = "update_state.json"
SNAPSHOT_HISTORY_DIRNAME = "snapshot_history"
TARGET_REFRESH_DIRNAME = "targets"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PARSED_DIR_HISTORY_WARNING_CASES = 5
EXPECTED_PASS_RATE_TARGET = 0.8
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


def build_character_update_summary(records: list[dict[str, Any]], cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    case_by_image = {}
    for case in cases:
        if case.get("image"):
            case_by_image[str(Path(str(case["image"])).resolve())] = case
    updates = []
    skipped = []
    for record in records:
        if not record.get("processed"):
            if record.get("status") == "unchanged":
                skipped.append(record.get("name") or record.get("image"))
            continue
        case = case_by_image.get(record.get("image"), {})
        character = case.get("character", {}) if isinstance(case.get("character"), dict) else {}
        quality = case.get("quality", {}) if isinstance(case.get("quality"), dict) else {}
        updates.append(
            {
                "character": character.get("name") or case.get("name") or "unknown_character",
                "image": record.get("image"),
                "image_name": record.get("name"),
                "update_status": record.get("status"),
                "review_status": case.get("review_status"),
                "coverage_level": case.get("coverage_level"),
                "requires_manual_review": quality.get("requires_manual_review"),
                "parsed_json": case.get("parsed_json"),
                "normalized_json": case.get("normalized_json"),
                "errors": case.get("errors", []),
            }
        )
    updates.sort(key=lambda item: (str(item.get("character") or ""), str(item.get("image_name") or "")))
    return updates, skipped


def build_update_summary(path: Path, records: list[dict[str, Any]], cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    counts: dict[str, int] = {"new": 0, "changed": 0, "unchanged": 0}
    for record in records:
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    character_updates, skipped_images = build_character_update_summary(records, cases or [])
    return {
        "state_file": str(path),
        "discovered_image_count": len(records),
        "processed_image_count": sum(1 for record in records if record.get("processed")),
        "skipped_unchanged_count": sum(1 for record in records if record.get("status") == "unchanged" and not record.get("processed")),
        "processed_character_count": len({item.get("character") for item in character_updates if item.get("character")}),
        "processed_characters": sorted({str(item.get("character")) for item in character_updates if item.get("character")}),
        "character_updates": character_updates,
        "skipped_images": skipped_images,
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
    return latest_parsed_paths(parsed_files(parsed_dir))


def latest_parsed_paths(paths: list[Path]) -> list[Path]:
    grouped: dict[str, Path] = {}
    for path in paths:
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
        expected = case.get("expected") or case.get("expected_json")
        if expected:
            case["expected"] = str(resolve_path(str(expected)))
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


def text_contains_any(values: list[str], needles: tuple[str, ...]) -> bool:
    joined = "\n".join(values).lower()
    return any(needle.lower() in joined for needle in needles)


def critical_quality_blockers(case: dict[str, Any]) -> list[str]:
    quality = case.get("quality", {}) if isinstance(case.get("quality"), dict) else {}
    blockers = [str(item) for item in quality.get("blockers", []) if item] if isinstance(quality.get("blockers"), list) else []
    errors = [str(item) for item in case.get("errors", []) if item] if isinstance(case.get("errors"), list) else []
    critical: list[str] = []
    if str(case.get("review_status") or "").upper() == "FAIL" or text_contains_any(errors, ("review failed",)):
        critical.append("review_status=FAIL")
    if not case.get("normalized_json") or text_contains_any(errors, ("normalize failed",)):
        critical.append("normalized 失败")
    if text_contains_any(blockers + errors, ("invalid_candidate",)):
        critical.append("存在 invalid_candidate")
    if text_contains_any(blockers + errors, ("drive_disc 全缺", "drive_discs 全缺", "drive_disc_main_stats 缺失", "drive_disc_sub_stats 缺失")):
        critical.append("驱动盘主副词条缺失")
    return critical


def case_statuses(case: dict[str, Any], source_mode: str | None) -> dict[str, Any]:
    errors = [str(item) for item in case.get("errors", []) if item] if isinstance(case.get("errors"), list) else []
    review_status = str(case.get("review_status") or "").upper()
    if review_status == "FAIL" or text_contains_any(errors, ("review failed",)):
        parse_status = "FAIL"
    elif source_mode == MODE_PARSED_REPLAY and not case.get("review_html"):
        parse_status = "SKIPPED"
    elif case.get("parsed_json"):
        parse_status = "PASS"
    else:
        parse_status = "FAIL" if errors else "SKIPPED"

    if not case.get("expected_json"):
        expected_status = "N/A"
    elif case.get("pass_rate") is None:
        expected_status = "FAIL"
    else:
        expected_status = "PASS" if float(case.get("pass_rate") or 0) >= EXPECTED_PASS_RATE_TARGET else "FAIL"

    normalized_status = "GENERATED" if case.get("normalized_json") else "FAILED"
    critical = critical_quality_blockers(case)
    import_status = "BLOCKED" if critical else "REQUIRES_REVIEW"
    return {
        "parse_status": parse_status,
        "expected_status": expected_status,
        "normalized_status": normalized_status,
        "import_status": import_status,
        "import_blockers": critical,
    }


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
        "parse_status": "SKIPPED",
        "expected_status": "N/A",
        "normalized_status": "FAILED",
        "import_status": "REQUIRES_REVIEW",
        "import_blockers": [],
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
    expected_path: Path | None = None,
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
    evaluate_case(
        parsed_path,
        expected_path or find_expected(image_path=image_path, parsed_path=parsed_path, parsed=parsed, expected_dir=expected_dir),
        case_dir,
        case,
    )
    normalize_case(parsed_path, output_dir, case)
    return case


def process_parsed_case(
    parsed_path: Path,
    *,
    name: str,
    output_dir: Path,
    expected_dir: Path,
    expected_path: Path | None = None,
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
    evaluate_case(
        parsed_path,
        expected_path or find_expected(image_path=Path(image) if image else None, parsed_path=parsed_path, parsed=parsed, expected_dir=expected_dir),
        case_dir,
        case,
    )
    normalize_case(parsed_path, output_dir, case)
    return case


def pipeline_steps(summary: dict[str, Any]) -> list[dict[str, str]]:
    cases = summary.get("cases", [])
    input_info = summary.get("input", {})
    errors = [error for case in cases for error in case.get("errors", [])]
    overall = summary.get("overall", {}) if isinstance(summary.get("overall"), dict) else {}
    normalized_count = overall.get("normalized_count", 0)
    expected_counts = overall.get("expected_status_counts", {}) if isinstance(overall.get("expected_status_counts"), dict) else {}
    parse_counts = overall.get("parse_status_counts", {}) if isinstance(overall.get("parse_status_counts"), dict) else {}
    normalized_counts = overall.get("normalized_status_counts", {}) if isinstance(overall.get("normalized_status_counts"), dict) else {}
    import_counts = overall.get("import_status_counts", {}) if isinstance(overall.get("import_status_counts"), dict) else {}
    plan_info = summary.get("training_plan", {}) if isinstance(summary.get("training_plan"), dict) else {}
    history_info = summary.get("snapshot_history", {}) if isinstance(summary.get("snapshot_history"), dict) else {}
    target_info = summary.get("target_refresh", {}) if isinstance(summary.get("target_refresh"), dict) else {}
    inbox_info = summary.get("review_inbox", {}) if isinstance(summary.get("review_inbox"), dict) else {}
    tier_info = summary.get("tier_watchlist", {}) if isinstance(summary.get("tier_watchlist"), dict) else {}
    delta_info = summary.get("roster_delta", {}) if isinstance(summary.get("roster_delta"), dict) else {}
    endgame_info = summary.get("endgame_plan", {}) if isinstance(summary.get("endgame_plan"), dict) else {}
    manifest_info = summary.get("run_manifest", {}) if isinstance(summary.get("run_manifest"), dict) else {}
    final_info = summary.get("final_brief", {}) if isinstance(summary.get("final_brief"), dict) else {}
    checklist_info = summary.get("action_checklist", {}) if isinstance(summary.get("action_checklist"), dict) else {}
    preview_info = summary.get("review_decision_preview", {}) if isinstance(summary.get("review_decision_preview"), dict) else {}
    expected_step = "FAIL" if expected_counts.get("FAIL") else "PASS" if expected_counts.get("PASS") else "N/A"
    normalized_step = "FAILED" if normalized_counts.get("FAILED") else "GENERATED" if normalized_count else "FAILED"
    manual_review_step = "BLOCKED" if import_counts.get("BLOCKED") else "REQUIRES_REVIEW" if cases else "N/A"
    return [
        {"name": "官方分享图", "status": "done" if input_info.get("images_dir") or any(case.get("image") for case in cases) else "skipped"},
        {"name": "OCR Review", "status": "FAIL" if parse_counts.get("FAIL") or (errors and input_info.get("images_dir")) else "PASS" if parse_counts.get("PASS") else "SKIPPED"},
        {"name": "Expected Diff", "status": expected_step},
        {"name": "Normalized Snapshot", "status": normalized_step},
        {"name": "Manual Review Gate", "status": manual_review_step},
        {"name": "Snapshot Diff", "status": "done" if summary.get("snapshot_diff_md") else "skipped"},
        {
            "name": "Snapshot History",
            "status": "failed" if history_info.get("diff_failed_count") else "done" if history_info.get("snapshot_count") else "skipped",
        },
        {"name": "Target Refresh", "status": "failed" if target_info.get("error") else "done" if target_info.get("output_json") else "skipped"},
        {"name": "Training Plan", "status": "failed" if plan_info.get("error") else "done" if plan_info.get("output_json") else "skipped"},
        {
            "name": "Action Cards",
            "status": "failed"
            if isinstance(summary.get("action_cards"), dict) and summary["action_cards"].get("error")
            else "done"
            if isinstance(summary.get("action_cards"), dict) and summary["action_cards"].get("output_json")
            else "skipped",
        },
        {
            "name": "Review Inbox",
            "status": "done" if isinstance(inbox_info, dict) and inbox_info.get("schema_version") else "skipped",
        },
        {
            "name": "Tier Watchlist",
            "status": "failed"
            if isinstance(tier_info, dict) and tier_info.get("error")
            else "done"
            if isinstance(tier_info, dict) and tier_info.get("output_json")
            else "skipped",
        },
        {
            "name": "Team Cards",
            "status": "failed"
            if isinstance(summary.get("team_cards"), dict) and summary["team_cards"].get("error")
            else "done"
            if isinstance(summary.get("team_cards"), dict) and summary["team_cards"].get("output_json")
            else "skipped",
        },
        {
            "name": "Roster Delta",
            "status": "failed"
            if isinstance(delta_info, dict) and delta_info.get("error")
            else "done"
            if isinstance(delta_info, dict) and delta_info.get("output_json")
            else "skipped",
        },
        {
            "name": "Run Manifest",
            "status": "failed"
            if isinstance(manifest_info, dict) and manifest_info.get("error")
            else "done"
            if isinstance(manifest_info, dict) and manifest_info.get("output_json")
            else "skipped",
        },
        {
            "name": "Endgame Plan",
            "status": "failed"
            if isinstance(endgame_info, dict) and endgame_info.get("error")
            else "done"
            if isinstance(endgame_info, dict) and endgame_info.get("output_json")
            else "skipped",
        },
        {
            "name": "Final Brief",
            "status": "failed"
            if isinstance(final_info, dict) and final_info.get("error")
            else "done"
            if isinstance(final_info, dict) and final_info.get("output_json")
            else "skipped",
        },
        {
            "name": "Action Checklist",
            "status": "failed"
            if isinstance(checklist_info, dict) and checklist_info.get("error")
            else "done"
            if isinstance(checklist_info, dict) and checklist_info.get("output_json")
            else "skipped",
        },
        {
            "name": "Review Decision Preview",
            "status": "failed"
            if isinstance(preview_info, dict) and preview_info.get("error")
            else "done"
            if isinstance(preview_info, dict) and preview_info.get("output_json")
            else "skipped",
        },
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
    source_mode_value = str(input_info.get("source_mode") or "")
    for case in cases:
        case.update(case_statuses(case, source_mode_value))
    parse_success_count = sum(1 for case in cases if case.get("parsed_json"))
    review_counts: dict[str, int] = {}
    parse_status_counts: dict[str, int] = {}
    expected_status_counts: dict[str, int] = {}
    normalized_status_counts: dict[str, int] = {}
    import_status_counts: dict[str, int] = {}
    pass_rates = []
    normalized_paths = []
    requires_review = 0
    for case in cases:
        review_status = case.get("review_status") or "N/A"
        review_counts[review_status] = review_counts.get(review_status, 0) + 1
        for counts, key in (
            (parse_status_counts, "parse_status"),
            (expected_status_counts, "expected_status"),
            (normalized_status_counts, "normalized_status"),
            (import_status_counts, "import_status"),
        ):
            status = str(case.get(key) or "N/A")
            counts[status] = counts.get(status, 0) + 1
        if case.get("pass_rate") is not None:
            pass_rates.append(float(case["pass_rate"]))
        if case.get("normalized_json"):
            normalized_paths.append(Path(case["normalized_json"]))
        if case.get("quality", {}).get("requires_manual_review"):
            requires_review += 1
    errors = [error for case in cases for error in case.get("errors", [])]
    if not cases:
        conclusion = "没有发现可处理的图片或 parsed JSON。"
    elif parse_status_counts.get("FAIL") or normalized_status_counts.get("FAILED"):
        conclusion = "Demo pipeline 已生成 Dashboard，但部分 case 失败，请打开 case 卡片查看错误。"
    elif requires_review:
        conclusion = "已生成标准化快照；当前仍是本地 demo，需要人工确认后才能进入后续导入原型。requires_review 不代表解析失败。"
    else:
        conclusion = "已生成标准化快照；当前阶段仍不会自动写入正式数据库。"
    warnings = build_warnings(cases, input_info)
    if parse_status_counts.get("FAIL") or normalized_status_counts.get("FAILED"):
        demo_status = "HAS_PARSE_FAILURE"
    elif expected_status_counts.get("N/A"):
        demo_status = "MISSING_EXPECTED"
    else:
        demo_status = "READY_FOR_REVIEW"
    summary: dict[str, Any] = {
        "created_at": normalizer.now_iso(),
        "input": input_info,
        "output_dir": str(output_dir),
        "warnings": warnings,
        "overall": {
            "case_count": len(cases),
            "parse_success_count": parse_success_count,
            "review_status_counts": review_counts,
            "parse_status_counts": parse_status_counts,
            "expected_status_counts": expected_status_counts,
            "normalized_status_counts": normalized_status_counts,
            "import_status_counts": import_status_counts,
            "demo_status": demo_status,
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


def build_training_plan(
    cases: list[dict[str, Any]],
    targets_path: Path | None,
    output_dir: Path,
    *,
    snapshot_history: dict[str, Any] | None = None,
    character_catalog: Path | None = None,
    daily_stamina: float | None = None,
    horizon_days: float | None = None,
) -> dict[str, Any] | None:
    if targets_path is None:
        return None
    normalized_paths = [Path(str(case["normalized_json"])) for case in cases if case.get("normalized_json")]
    plan_info: dict[str, Any] = {
        "targets_json": str(targets_path),
        "character_catalog": str(character_catalog) if character_catalog else None,
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
        report = planner.generate_report(
            normalized_paths,
            targets_path,
            output_dir / "planner",
            history_context=snapshot_history,
            character_catalog=character_catalog,
            daily_stamina=daily_stamina,
            horizon_days=horizon_days,
        )
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
            "history_context": report.get("history_context", {}) if isinstance(report.get("history_context"), dict) else {},
            "resource_plan": report.get("resource_plan", {}) if isinstance(report.get("resource_plan"), dict) else {},
            "target_source_status": report.get("target_source_status", {}) if isinstance(report.get("target_source_status"), dict) else {},
            "target_coverage": report.get("target_coverage", []) if isinstance(report.get("target_coverage"), list) else [],
            "coverage_gap_actions": report.get("coverage_gap_actions", []) if isinstance(report.get("coverage_gap_actions"), list) else [],
            "character_catalog_summary": report.get("character_catalog", {}) if isinstance(report.get("character_catalog"), dict) else {},
        }
    )
    return plan_info


def build_demo_action_cards(
    training_plan: dict[str, Any] | None,
    targets_path: Path | None,
    output_dir: Path,
    *,
    roster_index: Path | None = None,
    tier_watchlist: Path | None = None,
) -> dict[str, Any] | None:
    if not isinstance(training_plan, dict) or not training_plan.get("output_json"):
        return None
    info: dict[str, Any] = {
        "output_json": None,
        "output_md": None,
        "summary": {},
        "cards": [],
        "warnings": [],
        "error": None,
    }
    try:
        result = action_cards.build_action_cards(
            planner_report=Path(str(training_plan["output_json"])),
            targets=targets_path,
            snapshots_dir=output_dir / "normalized",
            roster_index=roster_index if roster_index and roster_index.exists() else None,
            tier_watchlist=tier_watchlist if tier_watchlist and tier_watchlist.exists() else None,
            output_dir=output_dir / "actions",
        )
    except action_cards.ActionCardError as exc:
        info["error"] = str(exc)
        return info
    info.update(
        {
            "output_json": result.get("output_json"),
            "output_md": result.get("output_md"),
            "summary": result.get("summary", {}) if isinstance(result.get("summary"), dict) else {},
            "cards": result.get("cards", []) if isinstance(result.get("cards"), list) else [],
            "warnings": result.get("warnings", []) if isinstance(result.get("warnings"), list) else [],
            "input": result.get("input", {}) if isinstance(result.get("input"), dict) else {},
        }
    )
    return info


def build_demo_team_cards(
    action_card_info: dict[str, Any] | None,
    training_plan: dict[str, Any] | None,
    output_dir: Path,
    *,
    character_catalog: Path | None = None,
    roster_index: Path | None = None,
    tier_watchlist: Path | None = None,
) -> dict[str, Any] | None:
    if (
        not isinstance(action_card_info, dict)
        or not action_card_info.get("output_json")
        or not isinstance(training_plan, dict)
        or not training_plan.get("output_json")
    ):
        return None
    info: dict[str, Any] = {
        "output_json": None,
        "output_md": None,
        "summary": {},
        "cards": [],
        "warnings": [],
        "error": None,
    }
    try:
        result = team_cards.build_team_cards(
            action_cards=Path(str(action_card_info["output_json"])),
            planner_report=Path(str(training_plan["output_json"])),
            character_catalog=character_catalog,
            snapshots_dir=output_dir / "normalized",
            roster_index=roster_index if roster_index and roster_index.exists() else None,
            tier_watchlist=tier_watchlist if tier_watchlist and tier_watchlist.exists() else None,
            output_dir=output_dir / "teams",
        )
    except team_cards.TeamCardError as exc:
        info["error"] = str(exc)
        return info
    info.update(
        {
            "output_json": result.get("output_json"),
            "output_md": result.get("output_md"),
            "summary": result.get("summary", {}) if isinstance(result.get("summary"), dict) else {},
            "cards": result.get("cards", []) if isinstance(result.get("cards"), list) else [],
            "warnings": result.get("warnings", []) if isinstance(result.get("warnings"), list) else [],
            "input": result.get("input", {}) if isinstance(result.get("input"), dict) else {},
        }
    )
    return info


def build_demo_tier_watchlist(
    tier_snapshot: Path | None,
    output_dir: Path,
    *,
    roster_index: Path | None = None,
    stale_days: int = 60,
) -> dict[str, Any] | None:
    if tier_snapshot is None:
        return None
    info: dict[str, Any] = {
        "output_json": None,
        "output_md": None,
        "summary": {},
        "entries": [],
        "warnings": [],
        "error": None,
    }
    try:
        result = tier_watchlist.build_tier_watchlist(
            tier_snapshot=tier_snapshot,
            roster_index=roster_index if roster_index and roster_index.exists() else None,
            stale_days=stale_days,
            output_dir=output_dir / "tier_watchlist",
        )
    except tier_watchlist.TierWatchlistError as exc:
        info["error"] = str(exc)
        return info
    info.update(
        {
            "schema_version": result.get("schema_version"),
            "output_json": result.get("output_json"),
            "output_md": result.get("output_md"),
            "summary": result.get("summary", {}) if isinstance(result.get("summary"), dict) else {},
            "entries": result.get("entries", []) if isinstance(result.get("entries"), list) else [],
            "warnings": result.get("warnings", []) if isinstance(result.get("warnings"), list) else [],
            "source": result.get("source", {}) if isinstance(result.get("source"), dict) else {},
        }
    )
    return info


def latest_previous_roster_index(roster_dir: Path) -> Path | None:
    history_dir = roster_dir / "history"
    previous = history_dir / "roster_index_previous.json"
    if previous.exists():
        return previous
    candidates = sorted(history_dir.glob("roster_index_*.json")) if history_dir.exists() else []
    return candidates[-1] if candidates else None


def build_demo_roster_delta(
    *,
    roster_dir: Path,
    output_dir: Path,
    new_roster_index: Path,
    action_cards_path: Path | None = None,
    team_cards_path: Path | None = None,
    tier_watchlist_path: Path | None = None,
) -> dict[str, Any] | None:
    old_roster_index = latest_previous_roster_index(roster_dir)
    if not old_roster_index or not old_roster_index.exists() or not new_roster_index.exists():
        return None
    try:
        return roster_delta.build_roster_delta(
            old_roster_index=old_roster_index,
            new_roster_index=new_roster_index,
            action_cards=action_cards_path if action_cards_path and action_cards_path.exists() else None,
            team_cards=team_cards_path if team_cards_path and team_cards_path.exists() else None,
            tier_watchlist=tier_watchlist_path if tier_watchlist_path and tier_watchlist_path.exists() else None,
            output_dir=output_dir / "roster_delta",
        )
    except roster_delta.RosterDeltaError as exc:
        return {
            "schema_version": roster_delta.SCHEMA_VERSION,
            "input": {
                "old_roster_index": str(old_roster_index),
                "new_roster_index": str(new_roster_index),
            },
            "error": str(exc),
        }


def build_demo_run_manifest(
    *,
    output_dir: Path,
    roster_index: Path | None = None,
    targets_path: Path | None = None,
    team_cards_path: Path | None = None,
    action_cards_path: Path | None = None,
    tier_watchlist_path: Path | None = None,
    roster_delta_path: Path | None = None,
) -> dict[str, Any] | None:
    if not roster_index or not roster_index.exists():
        return None
    try:
        return run_manifest.build_run_manifest(
            output_dir=output_dir,
            roster_index=roster_index,
            targets=targets_path if targets_path and targets_path.exists() else None,
            team_cards=team_cards_path if team_cards_path and team_cards_path.exists() else None,
            action_cards=action_cards_path if action_cards_path and action_cards_path.exists() else None,
            tier_watchlist=tier_watchlist_path if tier_watchlist_path and tier_watchlist_path.exists() else None,
            roster_delta=roster_delta_path if roster_delta_path and roster_delta_path.exists() else None,
        )
    except run_manifest.RunManifestError as exc:
        return {
            "schema_version": run_manifest.SCHEMA_VERSION,
            "input": {
                "roster_index": str(roster_index) if roster_index else None,
                "targets": str(targets_path) if targets_path else None,
                "team_cards": str(team_cards_path) if team_cards_path else None,
                "action_cards": str(action_cards_path) if action_cards_path else None,
                "tier_watchlist": str(tier_watchlist_path) if tier_watchlist_path else None,
                "roster_delta": str(roster_delta_path) if roster_delta_path else None,
            },
            "error": str(exc),
        }


def build_demo_endgame_plan(
    *,
    roster_index: Path,
    output_dir: Path,
    team_cards_path: Path | None,
    targets_path: Path | None = None,
    action_cards_path: Path | None = None,
    tier_watchlist_path: Path | None = None,
    roster_delta_path: Path | None = None,
    run_manifest_path: Path | None = None,
) -> dict[str, Any] | None:
    if not roster_index.exists() or not team_cards_path or not team_cards_path.exists():
        return None
    try:
        return endgame_plan.build_endgame_plan(
            roster_index=roster_index,
            targets=targets_path if targets_path and targets_path.exists() else None,
            team_cards=team_cards_path,
            action_cards=action_cards_path if action_cards_path and action_cards_path.exists() else None,
            tier_watchlist=tier_watchlist_path if tier_watchlist_path and tier_watchlist_path.exists() else None,
            roster_delta=roster_delta_path if roster_delta_path and roster_delta_path.exists() else None,
            run_manifest=run_manifest_path if run_manifest_path and run_manifest_path.exists() else None,
            output_dir=output_dir / "endgame_plan",
        )
    except endgame_plan.EndgamePlanError as exc:
        return {
            "schema_version": endgame_plan.SCHEMA_VERSION,
            "input": {
                "roster_index": str(roster_index),
                "targets": str(targets_path) if targets_path else None,
                "team_cards": str(team_cards_path) if team_cards_path else None,
                "action_cards": str(action_cards_path) if action_cards_path else None,
                "tier_watchlist": str(tier_watchlist_path) if tier_watchlist_path else None,
                "roster_delta": str(roster_delta_path) if roster_delta_path else None,
                "run_manifest": str(run_manifest_path) if run_manifest_path else None,
            },
            "error": str(exc),
        }


def build_demo_final_brief(
    *,
    output_dir: Path,
    review_inbox_path: Path,
    run_manifest_path: Path | None = None,
    roster_index: Path | None = None,
    roster_delta_path: Path | None = None,
    endgame_plan_path: Path | None = None,
    tier_watchlist_path: Path | None = None,
) -> dict[str, Any] | None:
    if not review_inbox_path.exists():
        return None
    try:
        return final_brief.build_final_brief(
            output_dir=output_dir / "final_brief",
            run_manifest=run_manifest_path if run_manifest_path and run_manifest_path.exists() else None,
            roster_index=roster_index if roster_index and roster_index.exists() else None,
            review_inbox=review_inbox_path,
            roster_delta=roster_delta_path if roster_delta_path and roster_delta_path.exists() else None,
            endgame_plan=endgame_plan_path if endgame_plan_path and endgame_plan_path.exists() else None,
            tier_watchlist=tier_watchlist_path if tier_watchlist_path and tier_watchlist_path.exists() else None,
        )
    except final_brief.FinalBriefError as exc:
        return {
            "schema_version": final_brief.SCHEMA_VERSION,
            "input": {
                "run_manifest": str(run_manifest_path) if run_manifest_path else None,
                "roster_index": str(roster_index) if roster_index else None,
                "review_inbox": str(review_inbox_path),
                "roster_delta": str(roster_delta_path) if roster_delta_path else None,
                "endgame_plan": str(endgame_plan_path) if endgame_plan_path else None,
                "tier_watchlist": str(tier_watchlist_path) if tier_watchlist_path else None,
            },
            "error": str(exc),
        }


def build_demo_action_checklist(
    *,
    output_dir: Path,
    final_brief_path: Path,
    review_inbox_path: Path | None = None,
    endgame_plan_path: Path | None = None,
    run_manifest_path: Path | None = None,
) -> dict[str, Any] | None:
    if not final_brief_path.exists():
        return None
    try:
        return action_checklist.build_action_checklist(
            output_dir=output_dir / "action_checklist",
            final_brief=final_brief_path,
            review_inbox=review_inbox_path if review_inbox_path and review_inbox_path.exists() else None,
            endgame_plan=endgame_plan_path if endgame_plan_path and endgame_plan_path.exists() else None,
            run_manifest=run_manifest_path if run_manifest_path and run_manifest_path.exists() else None,
        )
    except action_checklist.ActionChecklistError as exc:
        return {
            "schema_version": action_checklist.SCHEMA_VERSION,
            "input": {
                "final_brief": str(final_brief_path),
                "review_inbox": str(review_inbox_path) if review_inbox_path else None,
                "endgame_plan": str(endgame_plan_path) if endgame_plan_path else None,
                "run_manifest": str(run_manifest_path) if run_manifest_path else None,
            },
            "error": str(exc),
        }


def build_demo_review_decision_preview(
    *,
    output_dir: Path,
    action_checklist_info: dict[str, Any],
    review_inbox_path: Path,
    run_manifest_path: Path | None,
    roster_index_path: Path | None = None,
) -> dict[str, Any] | None:
    template = action_checklist_info.get("review_decisions_template") if isinstance(action_checklist_info, dict) else None
    if not template or not review_inbox_path.exists():
        return None
    try:
        return review_preview.preview_review_decisions(
            decision_manifest=Path(str(template)),
            review_inbox=review_inbox_path,
            run_manifest=run_manifest_path if run_manifest_path and run_manifest_path.exists() else None,
            roster_index=roster_index_path if roster_index_path and roster_index_path.exists() else None,
            output_dir=output_dir / "review_preview",
        )
    except review_preview.ReviewPreviewError as exc:
        return {
            "schema_version": review_preview.SCHEMA_VERSION,
            "input": {
                "decision_manifest": str(template),
                "review_inbox": str(review_inbox_path),
                "run_manifest": str(run_manifest_path),
                "roster_index": str(roster_index_path) if roster_index_path else None,
            },
            "error": str(exc),
        }


def review_decision_source(path: Path) -> str | None:
    try:
        data = load_json(path)
    except normalizer.NormalizeError:
        return None
    decision = data.get("review_decision") if isinstance(data.get("review_decision"), dict) else {}
    return str(decision.get("source_normalized_json") or path)


def roster_snapshot_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_dir():
        return []
    items = []
    for item in sorted(path.glob("*.json")):
        try:
            data = load_json(item)
        except normalizer.NormalizeError:
            continue
        character = normalized_character(data)
        equipment = normalized_equipment(data)
        quality = data.get("quality") if isinstance(data.get("quality"), dict) else {}
        items.append(
            {
                "character": character.get("name") or item.stem,
                "level": character.get("level"),
                "equipment": equipment.get("name"),
                "snapshot_json": str(item),
                "source_normalized_json": review_decision_source(item),
                "quality": {
                    "trusted_field_count": quality.get("trusted_field_count", 0),
                    "field_count": quality.get("field_count", 0),
                    "blockers": quality.get("blockers", []) if isinstance(quality.get("blockers"), list) else [],
                },
            }
        )
    return items


def build_review_inbox(cases: list[dict[str, Any]], roster_dir: Path) -> dict[str, Any]:
    accepted_dir = roster_dir / "accepted"
    rejected_dir = roster_dir / "rejected"
    accepted_items = roster_snapshot_items(accepted_dir)
    rejected_items = roster_snapshot_items(rejected_dir)
    accepted_sources = {str(item.get("source_normalized_json")) for item in accepted_items if item.get("source_normalized_json")}
    rejected_sources = {str(item.get("source_normalized_json")) for item in rejected_items if item.get("source_normalized_json")}
    pending_items = []
    for case in cases:
        normalized_json = case.get("normalized_json")
        if not normalized_json:
            continue
        normalized_text = str(Path(str(normalized_json)).resolve())
        if normalized_text in accepted_sources or normalized_text in rejected_sources or str(normalized_json) in accepted_sources or str(normalized_json) in rejected_sources:
            continue
        character = case.get("character") if isinstance(case.get("character"), dict) else {}
        equipment = case.get("equipment") if isinstance(case.get("equipment"), dict) else {}
        quality = case.get("quality") if isinstance(case.get("quality"), dict) else {}
        pending_items.append(
            {
                "character": character.get("name") or case.get("name"),
                "level": character.get("level"),
                "equipment": equipment.get("name"),
                "trusted_field_count": quality.get("trusted_field_count", 0),
                "field_count": quality.get("field_count", 0),
                "blockers": quality.get("blockers", []) if isinstance(quality.get("blockers"), list) else [],
                "normalized_json": normalized_json,
                "review_html": case.get("review_html"),
            }
        )
    roster_index_path = roster_dir / "roster_index.json"
    receipt_json = roster_dir / "review_apply_receipt.json"
    receipt_md = roster_dir / "review_apply_receipt.md"
    review_log = roster_dir / "review_log.json"
    return {
        "schema_version": "p1.4-lite-review-inbox",
        "roster_dir": str(roster_dir),
        "roster_index_json": str(roster_index_path) if roster_index_path.exists() else None,
        "review_apply_receipt_json": str(receipt_json) if receipt_json.exists() else None,
        "review_apply_receipt_md": str(receipt_md) if receipt_md.exists() else None,
        "review_log_json": str(review_log) if review_log.exists() else None,
        "safe_apply_status": "applied" if receipt_json.exists() else "not_applied",
        "accepted_count": len(accepted_items),
        "rejected_count": len(rejected_items),
        "pending_count": len(pending_items),
        "needs_manual_review_count": sum(1 for item in pending_items if item.get("blockers")),
        "pending": pending_items,
        "accepted": accepted_items,
        "rejected": rejected_items,
        "decision_command": (
            "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized "
            "--decision-manifest data/probes/review_decisions.json --roster-dir data/probes/roster "
            "--preview-result data/probes/demo/review_preview/review_decision_preview.json --require-preview-ready"
        ),
    }


def build_target_refresh(target_source_manifest: Path | None, output_dir: Path) -> dict[str, Any] | None:
    if target_source_manifest is None:
        return None
    info: dict[str, Any] = {
        "manifest": str(target_source_manifest),
        "output_json": None,
        "source_count": 0,
        "target_count": 0,
        "warnings": [],
        "error": None,
    }
    try:
        game, source_type, sources, defaults = target_intake.source_cases_from_manifest(target_source_manifest)
        targets = target_intake.prepare_targets(
            game=game,
            source_type=source_type,
            sources=sources,
            output_dir=output_dir / TARGET_REFRESH_DIRNAME,
            manifest_defaults=defaults,
        )
    except target_intake.TargetIntakeError as exc:
        info["error"] = str(exc)
        return info
    info.update(
        {
            "output_json": targets.get("output_json"),
            "source_count": len(targets.get("sources", [])) if isinstance(targets.get("sources"), list) else 0,
            "target_count": len(targets.get("targets", [])) if isinstance(targets.get("targets"), list) else 0,
            "warnings": targets.get("warnings", []) if isinstance(targets.get("warnings"), list) else [],
            "source_type": targets.get("source", {}).get("type") if isinstance(targets.get("source"), dict) else None,
            "game": targets.get("game"),
            "freshness": targets.get("freshness", {}) if isinstance(targets.get("freshness"), dict) else {},
        }
    )
    return info


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
    target_source_manifest: Path | None = None,
    character_catalog: Path | None = None,
    roster_dir: Path | None = None,
    tier_snapshot: Path | None = None,
    tier_stale_days: int = 60,
    daily_stamina: float | None = None,
    horizon_days: float | None = None,
) -> dict[str, Any]:
    if targets is not None and target_source_manifest is not None:
        raise DemoPipelineError("--targets cannot be combined with --target-source-manifest")
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
        "target_source_manifest": str(target_source_manifest) if target_source_manifest else None,
        "character_catalog": str(character_catalog) if character_catalog else None,
        "roster_dir": str(roster_dir or DEFAULT_ROSTER_DIR),
        "tier_snapshot": str(tier_snapshot) if tier_snapshot else None,
        "tier_stale_days": tier_stale_days,
        "daily_stamina": daily_stamina,
        "horizon_days": horizon_days,
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
                        expected_path=Path(str(raw["expected"])) if raw.get("expected") else None,
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
                        expected_path=Path(str(raw["expected"])) if raw.get("expected") else None,
                    )
                )
    elif parsed_dir:
        discovered_parsed_files = parsed_files(parsed_dir)
        active_parsed_files = latest_parsed_paths(discovered_parsed_files) if latest_only else discovered_parsed_files
        input_info["parsed_dir_discovered_count"] = len(discovered_parsed_files)
        input_info["parsed_dir_selected_count"] = len(active_parsed_files)
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
        input_info["update_state"] = build_update_summary(active_state_file, update_records, cases)

    snapshot_history = build_snapshot_history(cases, history_dir or (output_dir / SNAPSHOT_HISTORY_DIRNAME))
    summary = summarize(cases, output_dir, input_info, snapshot_history)
    if isinstance(input_info.get("update_state"), dict):
        summary["update_state"] = input_info["update_state"]
    target_refresh = build_target_refresh(target_source_manifest, output_dir)
    active_targets = Path(str(target_refresh["output_json"])) if isinstance(target_refresh, dict) and target_refresh.get("output_json") else targets
    if target_refresh is not None:
        summary["target_refresh"] = target_refresh
        if target_refresh.get("warnings"):
            summary.setdefault("warnings", []).extend(target_refresh["warnings"])
        if target_refresh.get("error"):
            summary.setdefault("warnings", []).append(f"Target refresh failed: {target_refresh['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    training_plan = build_training_plan(
        cases,
        active_targets,
        output_dir,
        snapshot_history=snapshot_history,
        character_catalog=character_catalog,
        daily_stamina=daily_stamina,
        horizon_days=horizon_days,
    )
    if training_plan is not None:
        summary["training_plan"] = training_plan
        if training_plan.get("warnings"):
            summary.setdefault("warnings", []).extend(training_plan["warnings"])
        if training_plan.get("error"):
            summary.setdefault("warnings", []).append(f"Training plan failed: {training_plan['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    active_roster_dir = roster_dir or DEFAULT_ROSTER_DIR
    active_roster_index = active_roster_dir / "roster_index.json"
    review_inbox = build_review_inbox(cases, active_roster_dir)
    review_inbox_path = output_dir / "review_inbox.json"
    review_inbox["output_json"] = str(review_inbox_path)
    write_json(review_inbox_path, review_inbox)
    summary["review_inbox"] = review_inbox
    summary["pipeline_steps"] = pipeline_steps(summary)
    roster_index_for_replay = Path(str(review_inbox["roster_index_json"])) if review_inbox.get("roster_index_json") else active_roster_index
    tier_info = build_demo_tier_watchlist(
        tier_snapshot,
        output_dir,
        roster_index=roster_index_for_replay,
        stale_days=tier_stale_days,
    )
    if tier_info is not None:
        summary["tier_watchlist"] = tier_info
        if tier_info.get("warnings"):
            summary.setdefault("warnings", []).extend(tier_info["warnings"])
        if tier_info.get("error"):
            summary.setdefault("warnings", []).append(f"Tier watchlist failed: {tier_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    tier_watchlist_path = Path(str(tier_info["output_json"])) if isinstance(tier_info, dict) and tier_info.get("output_json") else None
    action_card_info = build_demo_action_cards(
        training_plan,
        active_targets,
        output_dir,
        roster_index=roster_index_for_replay,
        tier_watchlist=tier_watchlist_path,
    )
    if action_card_info is not None:
        summary["action_cards"] = action_card_info
        if action_card_info.get("warnings"):
            summary.setdefault("warnings", []).extend(action_card_info["warnings"])
        if action_card_info.get("error"):
            summary.setdefault("warnings", []).append(f"Action cards failed: {action_card_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    team_card_info = build_demo_team_cards(
        action_card_info,
        training_plan,
        output_dir,
        character_catalog=character_catalog,
        roster_index=roster_index_for_replay if roster_index_for_replay.exists() else None,
        tier_watchlist=tier_watchlist_path,
    )
    if team_card_info is not None:
        summary["team_cards"] = team_card_info
        if team_card_info.get("warnings"):
            summary.setdefault("warnings", []).extend(team_card_info["warnings"])
        if team_card_info.get("error"):
            summary.setdefault("warnings", []).append(f"Team cards failed: {team_card_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    action_cards_path = Path(str(action_card_info["output_json"])) if isinstance(action_card_info, dict) and action_card_info.get("output_json") else None
    team_cards_path = Path(str(team_card_info["output_json"])) if isinstance(team_card_info, dict) and team_card_info.get("output_json") else None
    roster_delta_info = build_demo_roster_delta(
        roster_dir=active_roster_dir,
        output_dir=output_dir,
        new_roster_index=roster_index_for_replay,
        action_cards_path=action_cards_path,
        team_cards_path=team_cards_path,
        tier_watchlist_path=tier_watchlist_path,
    )
    if roster_delta_info is not None:
        summary["roster_delta"] = roster_delta_info
        if roster_delta_info.get("warnings"):
            summary.setdefault("warnings", []).extend(roster_delta_info["warnings"])
        if roster_delta_info.get("error"):
            summary.setdefault("warnings", []).append(f"Roster delta failed: {roster_delta_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    roster_delta_path = (
        Path(str(roster_delta_info["output_json"]))
        if isinstance(roster_delta_info, dict) and roster_delta_info.get("output_json")
        else None
    )
    run_manifest_info = build_demo_run_manifest(
        output_dir=output_dir,
        roster_index=roster_index_for_replay if roster_index_for_replay.exists() else None,
        targets_path=active_targets,
        team_cards_path=team_cards_path,
        action_cards_path=action_cards_path,
        tier_watchlist_path=tier_watchlist_path,
        roster_delta_path=roster_delta_path,
    )
    if run_manifest_info is not None:
        summary["run_manifest"] = run_manifest_info
        status = run_manifest_info.get("artifact_status") if isinstance(run_manifest_info.get("artifact_status"), dict) else {}
        if isinstance(status.get("warnings"), list):
            summary.setdefault("warnings", []).extend(status["warnings"])
        if run_manifest_info.get("error"):
            summary.setdefault("warnings", []).append(f"Run manifest failed: {run_manifest_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    run_manifest_path = (
        Path(str(run_manifest_info["output_json"]))
        if isinstance(run_manifest_info, dict) and run_manifest_info.get("output_json")
        else None
    )
    endgame_plan_info = build_demo_endgame_plan(
        roster_index=roster_index_for_replay,
        targets_path=active_targets,
        output_dir=output_dir,
        team_cards_path=team_cards_path,
        action_cards_path=action_cards_path,
        tier_watchlist_path=tier_watchlist_path,
        roster_delta_path=roster_delta_path,
        run_manifest_path=run_manifest_path,
    )
    if endgame_plan_info is not None:
        summary["endgame_plan"] = endgame_plan_info
        if endgame_plan_info.get("warnings"):
            summary.setdefault("warnings", []).extend(endgame_plan_info["warnings"])
        if endgame_plan_info.get("error"):
            summary.setdefault("warnings", []).append(f"Endgame plan failed: {endgame_plan_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    endgame_plan_path = (
        Path(str(endgame_plan_info["output_json"]))
        if isinstance(endgame_plan_info, dict) and endgame_plan_info.get("output_json")
        else None
    )
    final_brief_info = build_demo_final_brief(
        output_dir=output_dir,
        review_inbox_path=review_inbox_path,
        run_manifest_path=run_manifest_path,
        roster_index=roster_index_for_replay if roster_index_for_replay.exists() else None,
        roster_delta_path=roster_delta_path,
        endgame_plan_path=endgame_plan_path,
        tier_watchlist_path=tier_watchlist_path,
    )
    if final_brief_info is not None:
        summary["final_brief"] = final_brief_info
        if final_brief_info.get("warnings"):
            summary.setdefault("warnings", []).extend(final_brief_info["warnings"])
        if final_brief_info.get("error"):
            summary.setdefault("warnings", []).append(f"Final brief failed: {final_brief_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    final_brief_path = (
        Path(str(final_brief_info["output_json"]))
        if isinstance(final_brief_info, dict) and final_brief_info.get("output_json")
        else None
    )
    action_checklist_info = (
        build_demo_action_checklist(
            output_dir=output_dir,
            final_brief_path=final_brief_path,
            review_inbox_path=review_inbox_path,
            endgame_plan_path=endgame_plan_path,
            run_manifest_path=run_manifest_path,
        )
        if final_brief_path is not None
        else None
    )
    if action_checklist_info is not None:
        summary["action_checklist"] = action_checklist_info
        if action_checklist_info.get("warnings"):
            summary.setdefault("warnings", []).extend(action_checklist_info["warnings"])
        if action_checklist_info.get("error"):
            summary.setdefault("warnings", []).append(f"Action checklist failed: {action_checklist_info['error']}")
        summary["pipeline_steps"] = pipeline_steps(summary)
    review_preview_info = (
        build_demo_review_decision_preview(
            output_dir=output_dir,
            action_checklist_info=action_checklist_info,
            review_inbox_path=review_inbox_path,
            run_manifest_path=run_manifest_path,
            roster_index_path=roster_index_for_replay if roster_index_for_replay.exists() else None,
        )
        if isinstance(action_checklist_info, dict)
        else None
    )
    if review_preview_info is not None:
        summary["review_decision_preview"] = review_preview_info
        if review_preview_info.get("error"):
            summary.setdefault("warnings", []).append(f"Review decision preview failed: {review_preview_info['error']}")
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
    parser.add_argument("--target-source-manifest", default=None, help="Optional public/local endgame source manifest. Generates targets before planner.")
    parser.add_argument("--character-catalog", default=None, help="Optional local character tag catalog JSON for planner target matching.")
    parser.add_argument("--roster-dir", default=str(DEFAULT_ROSTER_DIR), help="Local accepted roster directory. Default: data/probes/roster.")
    parser.add_argument("--tier-snapshot", default=None, help="Optional local tier/value snapshot JSON. Does not fetch network data.")
    parser.add_argument("--tier-stale-days", type=int, default=60, help="Mark tier sources older than this many days as stale. Default: 60.")
    parser.add_argument("--history-dir", default=None, help="Snapshot history directory. Default: <output-dir>/snapshot_history.")
    parser.add_argument("--daily-stamina", type=float, default=None, help="Daily stamina/power budget for planner. Default: 240.")
    parser.add_argument("--horizon-days", type=float, default=None, help="Planner horizon in days. Default: 7.")
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
            target_source_manifest=resolve_path(args.target_source_manifest) if args.target_source_manifest else None,
            character_catalog=resolve_path(args.character_catalog) if args.character_catalog else None,
            roster_dir=resolve_path(args.roster_dir) if args.roster_dir else None,
            tier_snapshot=resolve_path(args.tier_snapshot) if args.tier_snapshot else None,
            tier_stale_days=args.tier_stale_days,
            daily_stamina=args.daily_stamina,
            horizon_days=args.horizon_days,
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
        resource_plan = summary["training_plan"].get("resource_plan")
        if isinstance(resource_plan, dict):
            budget = resource_plan.get("budget", {}) if isinstance(resource_plan.get("budget"), dict) else {}
            print(f"daily_stamina: {budget.get('daily_stamina')}")
            print(f"horizon_days: {budget.get('horizon_days')}")
    if isinstance(summary.get("target_refresh"), dict):
        print(f"target_refresh_target_count: {summary['target_refresh'].get('target_count', 0)}")
        print(f"target_refresh_source_count: {summary['target_refresh'].get('source_count', 0)}")
    if isinstance(summary.get("snapshot_history"), dict):
        print(f"history_snapshot_count: {summary['snapshot_history'].get('snapshot_count', 0)}")
        print(f"history_diff_count: {summary['snapshot_history'].get('diff_count', 0)}")
        print(f"history_changed_character_count: {summary['snapshot_history'].get('changed_character_count', 0)}")
    if isinstance(summary.get("review_inbox"), dict):
        print(f"review_pending_count: {summary['review_inbox'].get('pending_count', 0)}")
        print(f"review_accepted_count: {summary['review_inbox'].get('accepted_count', 0)}")
        print(f"review_rejected_count: {summary['review_inbox'].get('rejected_count', 0)}")
    if isinstance(summary.get("tier_watchlist"), dict):
        tier_summary = summary["tier_watchlist"].get("summary", {})
        if isinstance(tier_summary, dict):
            print(f"tier_entry_count: {tier_summary.get('entry_count', 0)}")
            print(f"tier_owned_high_value_count: {tier_summary.get('owned_high_value_count', 0)}")
            print(f"tier_watch_candidate_count: {tier_summary.get('watch_candidate_count', 0)}")
            print(f"tier_stale_entry_count: {tier_summary.get('stale_entry_count', 0)}")
            print(f"tier_unverified_entry_count: {tier_summary.get('unverified_entry_count', 0)}")
    if isinstance(summary.get("roster_delta"), dict):
        delta_summary = summary["roster_delta"].get("summary", {})
        if isinstance(delta_summary, dict):
            print(f"roster_delta_new_count: {delta_summary.get('new_character_count', 0)}")
            print(f"roster_delta_updated_count: {delta_summary.get('updated_character_count', 0)}")
            print(f"roster_delta_team_impact_count: {delta_summary.get('team_impact_count', 0)}")
    if isinstance(summary.get("run_manifest"), dict):
        manifest_status = summary["run_manifest"].get("artifact_status", {})
        if isinstance(manifest_status, dict):
            print(f"run_manifest_consistent: {manifest_status.get('consistent')}")
            print(f"run_manifest_missing_count: {len(manifest_status.get('missing', []))}")
            print(f"run_manifest_stale_or_mismatched_count: {len(manifest_status.get('stale_or_mismatched', []))}")
    if isinstance(summary.get("endgame_plan"), dict):
        plan_summary = summary["endgame_plan"].get("summary", {})
        if isinstance(plan_summary, dict):
            print(f"endgame_plan_target_count: {plan_summary.get('target_count', 0)}")
            print(f"endgame_plan_ready_now_count: {plan_summary.get('ready_now_count', 0)}")
            print(f"endgame_plan_needs_review_count: {plan_summary.get('needs_review_count', 0)}")
            print(f"endgame_plan_needs_recording_count: {plan_summary.get('needs_recording_count', 0)}")
            print(f"endgame_plan_watch_only_count: {plan_summary.get('watch_only_count', 0)}")
    if isinstance(summary.get("final_brief"), dict):
        print(f"final_brief_status: {summary['final_brief'].get('brief_status')}")
        print(f"final_brief_top_card_count: {len(summary['final_brief'].get('top_cards', []))}")
    if isinstance(summary.get("action_checklist"), dict):
        checklist_summary = summary["action_checklist"].get("summary", {})
        print(f"action_checklist_status: {summary['action_checklist'].get('checklist_status')}")
        if isinstance(checklist_summary, dict):
            print(f"action_checklist_item_count: {checklist_summary.get('item_count', 0)}")
    if isinstance(summary.get("review_decision_preview"), dict):
        preview_summary = summary["review_decision_preview"].get("summary", {})
        print(f"review_preview_status: {summary['review_decision_preview'].get('preview_status')}")
        if isinstance(preview_summary, dict):
            print(f"review_preview_would_update_roster_count: {preview_summary.get('would_update_roster_count', 0)}")
    print(f"dashboard_html: {summary['dashboard_html']}")
    print(f"summary_json: {summary['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
