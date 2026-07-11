from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


def compare_artifact_trees(expected: Path, actual: Path, ignored_json_keys: Iterable[str] = ()) -> list[str]:
    ignored = set(ignored_json_keys)
    expected_files = {path.relative_to(expected) for path in expected.rglob("*") if path.is_file()}
    actual_files = {path.relative_to(actual) for path in actual.rglob("*") if path.is_file()}
    differences = [f"missing: {path.as_posix()}" for path in sorted(expected_files - actual_files)]
    differences += [f"unexpected: {path.as_posix()}" for path in sorted(actual_files - expected_files)]
    for relative in sorted(expected_files & actual_files):
        left, right = expected / relative, actual / relative
        if relative.suffix == ".json":
            a, b = _without_keys(json.loads(left.read_text(encoding="utf-8")), ignored), _without_keys(json.loads(right.read_text(encoding="utf-8")), ignored)
        elif relative.suffix == ".csv":
            a, b = _csv_rows(left), _csv_rows(right)
        else:
            a, b = left.read_text(encoding="utf-8"), right.read_text(encoding="utf-8")
        if a != b:
            differences.append(f"content: {relative.as_posix()}")
    return differences


def _csv_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def _without_keys(value, ignored: set[str]):
    if isinstance(value, dict):
        return {key: _without_keys(item, ignored) for key, item in value.items() if key not in ignored}
    if isinstance(value, list):
        return [_without_keys(item, ignored) for item in value]
    return value
