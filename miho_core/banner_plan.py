from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .box import load_config


DATE_TIME_RE = re.compile(
    r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)
DATE_DRIVEN_STATUSES = {"current", "next", "previous", "expired", "past"}
STATIC_STATUSES = {"satellite"}
CHINA_STANDARD_TIME = timezone(timedelta(hours=8))


def load_banner_plan(path: str | Path) -> dict[str, Any]:
    return load_config(path)


def effective_banner_phases(
    plan_or_phases: dict[str, Any] | Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if isinstance(plan_or_phases, dict):
        phases = plan_or_phases.get("phases") or []
    else:
        phases = plan_or_phases
    return [with_effective_phase_status(phase, now=now) for phase in phases if isinstance(phase, dict)]


def with_effective_phase_status(phase: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    row = dict(phase)
    declared = str(row.get("status") or "").strip().lower()
    start, end_exclusive = phase_date_bounds(row)
    row["declared_status"] = declared
    row["phase_starts_at"] = _format_boundary(start)
    row["phase_ends_at_exclusive"] = _format_boundary(end_exclusive)
    row["status"] = _effective_phase_status_from_bounds(
        declared,
        start,
        end_exclusive,
        now=now,
    )
    return row


def effective_phase_status(phase: dict[str, Any], *, now: datetime | None = None) -> str:
    declared = str(phase.get("status") or "").strip().lower()
    start, end_exclusive = phase_date_bounds(phase)
    return _effective_phase_status_from_bounds(
        declared,
        start,
        end_exclusive,
        now=now,
    )


def _effective_phase_status_from_bounds(
    declared: str,
    start: datetime | None,
    end_exclusive: datetime | None,
    *,
    now: datetime | None,
) -> str:
    if declared in STATIC_STATUSES:
        return declared
    if start is None and end_exclusive is None:
        return declared
    if declared and declared not in DATE_DRIVEN_STATUSES:
        return declared
    current = now or datetime.now()
    if start is not None and current < start:
        return "next"
    if end_exclusive is not None and current >= end_exclusive:
        return "previous"
    return "current"


def phase_date_bounds(phase: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start = _parse_datetime_value(
        phase.get("start_at")
        or phase.get("starts_at")
        or phase.get("start_time")
        or phase.get("start")
    )
    end_exclusive = _parse_datetime_value(
        phase.get("end_at")
        or phase.get("ends_at")
        or phase.get("end_time")
        or phase.get("end"),
        is_end=True,
    )
    if start is not None or end_exclusive is not None:
        return start, end_exclusive
    return _parse_date_range(str(phase.get("date_range") or ""))


def _parse_date_range(text: str) -> tuple[datetime | None, datetime | None]:
    matches = list(DATE_TIME_RE.finditer(text))
    if not matches:
        return None, None
    values = [_match_to_datetime(match, is_end=index > 0) for index, match in enumerate(matches[:2])]
    if len(values) == 1:
        return values[0], None
    return values[0], values[1]


def _parse_datetime_value(value: Any, *, is_end: bool = False) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = DATE_TIME_RE.search(text)
    if not match:
        return None
    return _match_to_datetime(match, is_end=is_end)


def _match_to_datetime(match: re.Match[str], *, is_end: bool) -> datetime:
    year, month, day = (int(match.group(index)) for index in (1, 2, 3))
    hour_text = match.group(4)
    if hour_text is None:
        value = datetime.combine(datetime(year, month, day).date(), time.min)
        return value + timedelta(days=1) if is_end else value
    hour = int(hour_text)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    value = datetime(year, month, day, hour, minute, second)
    if not is_end:
        return value
    return value + (timedelta(seconds=1) if match.group(6) is not None else timedelta(minutes=1))


def _format_boundary(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(tzinfo=CHINA_STANDARD_TIME).isoformat(timespec="seconds")
