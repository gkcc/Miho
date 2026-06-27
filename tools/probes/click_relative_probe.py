#!/usr/bin/env python
"""Resolve a window-relative coordinate and optionally click it for P0.6 official-UI RPA calibration."""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import time
from ctypes import wintypes
from datetime import datetime
from typing import Any


SECRET_VALUE_RE = re.compile(r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b(\s*[:=]\s*)([^,\s;\"']+)")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class ProbeError(RuntimeError):
    pass


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
    text = LONG_DIGIT_RE.sub("[REDACTED_ID]", text)
    return text


def user32() -> Any:
    if sys.platform != "win32":
        raise ProbeError("click_relative_probe.py currently supports Windows only.")
    api = ctypes.windll.user32
    try:
        api.SetProcessDPIAware()
    except Exception:
        pass
    return api


def window_title(api: Any, hwnd: int) -> str:
    length = api.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    api.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_rect(api: Any, hwnd: int) -> dict[str, int]:
    rect = RECT()
    if not api.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ProbeError(f"Failed to read window rectangle for hwnd={hwnd}.")
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": int(rect.right - rect.left),
        "height": int(rect.bottom - rect.top),
    }


def find_windows(title_contains: str) -> list[dict[str, Any]]:
    api = user32()
    matches: list[dict[str, Any]] = []

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not api.IsWindowVisible(hwnd):
            return True
        title = window_title(api, hwnd)
        if title_contains.casefold() not in title.casefold():
            return True
        rect = window_rect(api, hwnd)
        if rect["width"] <= 0 or rect["height"] <= 0:
            return True
        matches.append({"hwnd": hwnd, "title": redact_text(title), "rect": rect})
        return True

    if not api.EnumWindows(enum_proc_type(callback), 0):
        raise ProbeError("EnumWindows failed.")
    return matches


def resolve_point(match: dict[str, Any], relative_x: int, relative_y: int) -> dict[str, Any]:
    rect = match["rect"]
    if relative_x < 0 or relative_y < 0 or relative_x > rect["width"] or relative_y > rect["height"]:
        raise ProbeError(
            f"Relative coordinate ({relative_x}, {relative_y}) is outside the selected window "
            f"{rect['width']}x{rect['height']}."
        )
    return {
        "relative": {"x": relative_x, "y": relative_y},
        "absolute": {"x": rect["left"] + relative_x, "y": rect["top"] + relative_y},
    }


def click_absolute(x: int, y: int) -> None:
    api = user32()
    if not api.SetCursorPos(x, y):
        raise ProbeError(f"Failed to move cursor to absolute coordinate ({x}, {y}).")
    time.sleep(0.05)
    api.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    api.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve a coordinate relative to the MiYouShe window. Defaults to dry-run and does not click."
    )
    parser.add_argument("--window-title", default="米游社", help="Visible window title substring. Default: 米游社")
    parser.add_argument("--match-index", type=int, default=0, help="Window match index if multiple windows match. Default: 0")
    parser.add_argument("--x", type=int, required=True, help="Relative X coordinate inside the selected window.")
    parser.add_argument("--y", type=int, required=True, help="Relative Y coordinate inside the selected window.")
    parser.add_argument("--execute", action="store_true", help="Actually click the resolved point. Omit for dry-run.")
    parser.add_argument(
        "--confirm-official-ui",
        action="store_true",
        help="Required with --execute to confirm the target is an official MiYouShe UI control.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        matches = find_windows(args.window_title)
        if not matches:
            raise ProbeError(f"No visible window title contains: {redact_text(args.window_title)}")
        if args.match_index < 0 or args.match_index >= len(matches):
            raise ProbeError(f"--match-index {args.match_index} is out of range. matched_windows={len(matches)}")

        match = matches[args.match_index]
        point = resolve_point(match, args.x, args.y)
        result = {
            "probe": "click_relative_probe",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": not args.execute,
            "window": match,
            "point": point,
            "notes": [
                "Default mode only resolves coordinates and does not click.",
                "Do not use this probe for login, captcha, game clients, token reading, packet capture, or database writes.",
            ],
        }

        if args.execute:
            if not args.confirm_official_ui:
                raise ProbeError("--execute requires --confirm-official-ui.")
            if "米游社" not in match["title"]:
                raise ProbeError("--execute is limited to a visible MiYouShe window in this probe.")
            click_absolute(point["absolute"]["x"], point["absolute"]["y"])
            result["clicked"] = True
        else:
            result["clicked"] = False

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ProbeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
