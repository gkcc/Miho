#!/usr/bin/env python
"""Capture a window screenshot with a relative-coordinate grid for P0.6 RPA calibration."""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "window_screenshots"

SECRET_VALUE_RE = re.compile(r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b(\s*[:=]\s*)([^,\s;\"']+)")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")


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


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_image_grab() -> tuple[Any, Any]:
    try:
        from PIL import ImageDraw, ImageGrab  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProbeError("Missing Pillow. Install it with: python -m pip install pillow") from exc
    return ImageDraw, ImageGrab


def user32() -> Any:
    if sys.platform != "win32":
        raise ProbeError("window_screenshot_probe.py currently supports Windows only.")
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


def add_grid(image: Any, grid_size: int) -> None:
    if grid_size <= 0:
        return
    from PIL import ImageDraw  # type: ignore[import-not-found]

    draw = ImageDraw.Draw(image)
    width, height = image.size
    line_color = (255, 0, 0)
    text_color = (255, 0, 0)
    for x in range(0, width, grid_size):
        draw.line((x, 0, x, height), fill=line_color, width=1)
        draw.text((x + 4, 4), str(x), fill=text_color)
    for y in range(0, height, grid_size):
        draw.line((0, y, width, y), fill=line_color, width=1)
        draw.text((4, y + 4), str(y), fill=text_color)


def capture_window(match: dict[str, Any], output_dir: Path, grid_size: int, draw_grid: bool) -> dict[str, Any]:
    _image_draw, image_grab = load_image_grab()
    output_dir.mkdir(parents=True, exist_ok=True)
    rect = match["rect"]
    bbox = (rect["left"], rect["top"], rect["right"], rect["bottom"])
    image = image_grab.grab(bbox=bbox)
    if draw_grid:
        add_grid(image, grid_size)
    stem = f"window_screenshot_{now_stamp()}"
    image_path = output_dir / f"{stem}.png"
    json_path = output_dir / f"{stem}.json"
    image.save(image_path)

    result = {
        "probe": "window_screenshot_probe",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "window": match,
        "image": {
            "path": str(image_path),
            "width": image.width,
            "height": image.height,
            "grid_size": grid_size if draw_grid else None,
        },
        "notes": [
            "Probe only. Screenshot may contain private account-visible UI.",
            "Do not commit data/probes outputs.",
            "No clicking, login, token reading, packet capture, or database write is performed.",
        ],
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["metadata_path"] = str(json_path)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture a target window screenshot with an optional coordinate grid.")
    parser.add_argument("--window-title", default="米游社", help="Visible window title substring. Default: 米游社")
    parser.add_argument("--match-index", type=int, default=0, help="Window match index if multiple windows match. Default: 0")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/window_screenshots")
    parser.add_argument("--grid-size", type=int, default=100, help="Relative-coordinate grid size in pixels. Default: 100")
    parser.add_argument("--no-grid", action="store_true", help="Capture without drawing a coordinate grid.")
    parser.add_argument("--dry-run", action="store_true", help="Only print matching window geometry; do not capture a screenshot.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    try:
        matches = find_windows(args.window_title)
        if not matches:
            raise ProbeError(f"No visible window title contains: {redact_text(args.window_title)}")
        if args.match_index < 0 or args.match_index >= len(matches):
            raise ProbeError(f"--match-index {args.match_index} is out of range. matched_windows={len(matches)}")
        match = matches[args.match_index]
        if args.dry_run:
            print(json.dumps({"matched_windows": matches, "selected": match}, ensure_ascii=False, indent=2))
            return 0
        result = capture_window(match, output_dir, args.grid_size, not args.no_grid)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ProbeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
