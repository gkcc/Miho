from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from miho_core.visualizer_data import expand_visualizer_data


LOCAL_DATE_POINTER = "/meta/localDate"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def compare_json_contract(
    expected: Any,
    actual: Any,
    *,
    dynamic_pointers: Iterable[str] = (LOCAL_DATE_POINTER,),
) -> list[str]:
    """Compare JSON values without hiding type or array-order differences.

    Object member ordering is not JSON semantics, so keys are compared as
    sets. Every other distinction is strict: ``true`` is not ``1``, an integer
    is not a floating-point number, and arrays retain their source order.
    Differences use RFC 6901 JSON Pointers so a large ``data.json`` remains
    diagnosable.
    """

    differences: list[str] = []
    _compare_json(
        expected,
        actual,
        pointer="",
        dynamic_pointers=set(dynamic_pointers),
        differences=differences,
    )
    return differences


def assert_json_contract_equal(
    expected: Any,
    actual: Any,
    *,
    dynamic_pointers: Iterable[str] = (LOCAL_DATE_POINTER,),
) -> None:
    differences = compare_json_contract(
        expected,
        actual,
        dynamic_pointers=dynamic_pointers,
    )
    if not differences:
        return
    preview = "\n".join(f"- {item}" for item in differences[:60])
    remaining = len(differences) - 60
    suffix = f"\n- ... and {remaining} more difference(s)" if remaining > 0 else ""
    raise AssertionError(
        f"visualizer JSON differs ({len(differences)} difference(s)):\n"
        f"{preview}{suffix}"
    )


def relative_file_set(root: Path) -> list[str]:
    """Return a stable, platform-independent inventory of regular files."""

    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def normalized_utf8(path: Path) -> bytes:
    """Read strict UTF-8 text and normalize only platform line endings."""

    payload = path.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise AssertionError(f"UTF-8 BOM is not allowed: {path}")
    text = payload.decode("utf-8", errors="strict")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def normalized_utf8_sha256(path: Path) -> str:
    return hashlib.sha256(normalized_utf8(path)).hexdigest()


def binary_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return expand_visualizer_data(json.loads(path.read_text(encoding="utf-8")))


def _compare_json(
    expected: Any,
    actual: Any,
    *,
    pointer: str,
    dynamic_pointers: set[str],
    differences: list[str],
) -> None:
    display_pointer = pointer or "/"
    if pointer in dynamic_pointers:
        _validate_local_date(expected, display_pointer, "expected", differences)
        _validate_local_date(actual, display_pointer, "actual", differences)
        return

    if type(expected) is not type(actual):
        differences.append(
            f"{display_pointer}: type {type(expected).__name__} != "
            f"{type(actual).__name__} ({expected!r} != {actual!r})"
        )
        return

    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            differences.append(f"{_join_pointer(pointer, key)}: missing member")
        for key in sorted(actual_keys - expected_keys):
            differences.append(f"{_join_pointer(pointer, key)}: unexpected member")
        for key in sorted(expected_keys & actual_keys):
            _compare_json(
                expected[key],
                actual[key],
                pointer=_join_pointer(pointer, key),
                dynamic_pointers=dynamic_pointers,
                differences=differences,
            )
        return

    if isinstance(expected, list):
        if len(expected) != len(actual):
            differences.append(
                f"{display_pointer}: length {len(expected)} != {len(actual)}"
            )
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            _compare_json(
                expected_item,
                actual_item,
                pointer=_join_pointer(pointer, str(index)),
                dynamic_pointers=dynamic_pointers,
                differences=differences,
            )
        return

    if expected != actual:
        differences.append(f"{display_pointer}: {expected!r} != {actual!r}")


def _validate_local_date(
    value: Any,
    pointer: str,
    side: str,
    differences: list[str],
) -> None:
    if type(value) is not str or not _DATE_RE.fullmatch(value):
        differences.append(
            f"{pointer}: {side} dynamic value is not YYYY-MM-DD text: {value!r}"
        )
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        differences.append(f"{pointer}: {side} dynamic date is invalid: {value!r}")


def _join_pointer(pointer: str, token: str) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}"
