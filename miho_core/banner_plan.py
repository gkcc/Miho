from __future__ import annotations

import re
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterable

from .box import load_config


DATE_TIME_RE = re.compile(
    r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)
DATE_DRIVEN_STATUSES = {"current", "next", "previous", "expired", "past"}
STATIC_STATUSES = {"satellite"}


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
    row["declared_status"] = declared
    row["status"] = effective_phase_status(row, now=now)
    return row


def effective_phase_status(phase: dict[str, Any], *, now: datetime | None = None) -> str:
    declared = str(phase.get("status") or "").strip().lower()
    if declared in STATIC_STATUSES:
        return declared
    start, end = phase_date_bounds(phase)
    if start is None and end is None:
        return declared
    if declared and declared not in DATE_DRIVEN_STATUSES:
        return declared
    current = now or datetime.now()
    if start is not None and current < start:
        return "next"
    if end is not None and current > end:
        return "previous"
    return "current"


def phase_date_bounds(phase: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start = _parse_datetime_value(
        phase.get("start_at")
        or phase.get("starts_at")
        or phase.get("start_time")
        or phase.get("start")
    )
    end = _parse_datetime_value(
        phase.get("end_at")
        or phase.get("ends_at")
        or phase.get("end_time")
        or phase.get("end")
    )
    if start is not None or end is not None:
        return start, end
    return _parse_date_range(str(phase.get("date_range") or ""))


def _parse_date_range(text: str) -> tuple[datetime | None, datetime | None]:
    matches = list(DATE_TIME_RE.finditer(text))
    if not matches:
        return None, None
    values = [_match_to_datetime(match, is_end=index > 0) for index, match in enumerate(matches[:2])]
    if len(values) == 1:
        return values[0], None
    return values[0], values[1]


def _parse_datetime_value(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = DATE_TIME_RE.search(text)
    if not match:
        return None
    return _match_to_datetime(match, is_end=False)


def _match_to_datetime(match: re.Match[str], *, is_end: bool) -> datetime:
    year, month, day = (int(match.group(index)) for index in (1, 2, 3))
    hour_text = match.group(4)
    if hour_text is None:
        return datetime.combine(datetime(year, month, day).date(), time.max if is_end else time.min)
    hour = int(hour_text)
    minute = int(match.group(5) or 0)
    second = int(match.group(6) or 0)
    return datetime(year, month, day, hour, minute, second)
