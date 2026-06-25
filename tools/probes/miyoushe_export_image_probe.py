#!/usr/bin/env python
"""Prototype RPA probe for MiYouShe official export/share image UI."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = PROJECT_ROOT / "data" / "probes"
DEFAULT_OUTPUT_DIR = PROBE_DIR / "exported_images"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SHARE_KEYWORDS = (
    "分享",
    "分享图",
    "导出",
    "导出图片",
    "保存图片",
    "保存到本地",
    "保存到相册",
    "生成图片",
    "下载图片",
)

CONTROL_TYPE_NAMES = {
    50000: "Button",
    50004: "Edit",
    50005: "Hyperlink",
    50006: "Image",
    50007: "ListItem",
    50008: "List",
    50020: "Text",
    50025: "Custom",
    50026: "Group",
    50030: "Document",
    50032: "Window",
    50033: "Pane",
}

SECRET_VALUE_RE = re.compile(
    r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b"
    r"(\s*[:=]\s*)"
    r"([^,\s;\"']+)"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEYED_ID_RE = re.compile(r"(?i)\b(uid|account_id|accountid|user_id|userid)\b(\s*[:=：]?\s*)\d{4,}")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")


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


def truncate(text: str, limit: int = 180) -> str:
    clean = text.replace("\r", " ").replace("\n", " ").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def markdown_cell(value: Any, limit: int = 100) -> str:
    return truncate(redact_text(value), limit).replace("|", "\\|")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def output_stem() -> str:
    return datetime.now().strftime("miyoushe_export_image_probe_%Y%m%d_%H%M%S")


def load_uia() -> tuple[Any, Any]:
    if sys.platform != "win32":
        raise ProbeError("This probe only works on Windows because it uses Windows UI Automation.")

    try:
        import comtypes.client  # type: ignore[import-not-found]

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation  # type: ignore[import-not-found]

        automation = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
        return automation, comtypes.client
    except ImportError as exc:
        raise ProbeError(
            "Missing optional dependency 'comtypes'. Install it only if you want to run this probe: "
            "python -m pip install comtypes"
        ) from exc
    except Exception as exc:
        raise ProbeError(f"Failed to initialize Windows UI Automation: {exc}") from exc


def safe_current(element: Any, attr: str, default: Any = "") -> Any:
    try:
        return getattr(element, attr)
    except Exception:
        return default


def rect_to_dict(rect: Any) -> dict[str, int] | None:
    if rect is None:
        return None
    try:
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
    except Exception:
        return None
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def control_type_name(control_type: Any) -> str:
    try:
        numeric = int(control_type)
    except Exception:
        return "Unknown"
    return CONTROL_TYPE_NAMES.get(numeric, f"Unknown({numeric})")


def element_summary(element: Any, depth: int = 0) -> dict[str, Any]:
    control_type = safe_current(element, "CurrentControlType", 0)
    try:
        control_type_id = int(control_type)
    except Exception:
        control_type_id = None
    return {
        "depth": depth,
        "name": redact_text(safe_current(element, "CurrentName", "")),
        "control_type": control_type_name(control_type),
        "control_type_id": control_type_id,
        "automation_id": redact_text(safe_current(element, "CurrentAutomationId", "")),
        "class_name": redact_text(safe_current(element, "CurrentClassName", "")),
        "bounding_rectangle": rect_to_dict(safe_current(element, "CurrentBoundingRectangle", None)),
        "is_offscreen": bool(safe_current(element, "CurrentIsOffscreen", False)),
    }


def iter_children(walker: Any, element: Any):
    try:
        child = walker.GetFirstChildElement(element)
    except Exception:
        return
    while child:
        yield child
        try:
            child = walker.GetNextSiblingElement(child)
        except Exception:
            return


def find_window(automation: Any, window_title: str, max_top_windows: int = 200) -> tuple[Any | None, list[dict[str, Any]]]:
    root = automation.GetRootElement()
    walker = automation.ControlViewWalker
    keyword = window_title.casefold()
    candidates: list[dict[str, Any]] = []

    for index, child in enumerate(iter_children(walker, root)):
        if index >= max_top_windows:
            break
        summary = element_summary(child, 0)
        candidates.append(
            {
                "name": summary["name"],
                "control_type": summary["control_type"],
                "class_name": summary["class_name"],
            }
        )
        haystack = f"{summary['name']} {summary['class_name']} {summary['automation_id']}".casefold()
        if keyword.casefold() in haystack:
            return child, candidates
    return None, candidates


def search_share_controls(root: Any, automation: Any, max_depth: int = 8, max_nodes: int = 2500) -> list[dict[str, Any]]:
    walker = automation.ControlViewWalker
    matches: list[dict[str, Any]] = []
    visited = 0

    def visit(element: Any, depth: int) -> None:
        nonlocal visited
        if visited >= max_nodes:
            return
        visited += 1

        summary = element_summary(element, depth)
        haystack = f"{summary['name']} {summary['automation_id']} {summary['class_name']}"
        if not summary.get("is_offscreen") and any(keyword in haystack for keyword in SHARE_KEYWORDS):
            matches.append({"summary": summary, "element": element})

        if depth >= max_depth:
            return
        for child in iter_children(walker, element):
            visit(child, depth + 1)

    visit(root, 0)
    return matches


def invoke_element(element: Any) -> tuple[bool, str]:
    # UIA InvokePatternId is stable at 10000. This is element-based, not fixed-coordinate clicking.
    try:
        pattern = element.GetCurrentPattern(10000)
        pattern.Invoke()
        return True, "Invoked UIA InvokePattern."
    except Exception as exc:
        return False, f"UIA InvokePattern failed: {redact_text(exc)}"


def image_files(directory: Path) -> dict[str, dict[str, Any]]:
    if not directory.exists():
        return {}
    files: dict[str, dict[str, Any]] = {}
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files[str(path.resolve())] = {
            "path": str(path),
            "name": redact_text(path.name),
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        }
    return files


def relative_probe_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return redact_text(str(path))


def write_outputs(result: dict[str, Any]) -> tuple[Path, Path]:
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem()
    json_path = PROBE_DIR / f"{stem}.json"
    md_path = PROBE_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def render_markdown(result: dict[str, Any]) -> str:
    meta = result["metadata"]
    summary = result["summary"]
    candidates = result.get("button_candidates", [])
    new_images = result.get("new_images", [])
    log = result.get("operation_log", [])

    lines = [
        "# 米游社官方导出/分享图 RPA Probe",
        "",
        "## 摘要",
        "",
        f"- 创建时间：{markdown_cell(meta.get('created_at'), 120)}",
        f"- 游戏：{markdown_cell(meta.get('game'))}",
        f"- 模式：{markdown_cell(meta.get('mode'))}",
        f"- dry-run：{meta.get('dry_run')}",
        f"- 找到窗口：{summary.get('window_found')}",
        f"- 找到分享/导出按钮：{summary.get('share_button_found')}",
        f"- 成功触发导出：{summary.get('export_triggered')}",
        f"- 发现新图片：{summary.get('new_image_found')}",
        f"- 错误原因：{markdown_cell(summary.get('error_reason'), 160)}",
        "",
        "## 边界",
        "",
        "- 本工具只操作米游社 APP 官方 UI，不自动登录、不输入账号密码、不抓包、不读 cookie/token/stoken/ltoken。",
        "- 不盲点固定坐标；当前 prototype 只尝试 UIA InvokePattern。",
        "- 真实导出图和 probe 输出不得提交 Git。",
        "",
    ]

    if candidates:
        lines.extend(["## 候选按钮", "", "| name | control_type | automation_id | class_name |", "|---|---|---|---|"])
        for item in candidates[:20]:
            summary_item = item.get("summary", item)
            lines.append(
                "| "
                f"{markdown_cell(summary_item.get('name'))} | "
                f"{markdown_cell(summary_item.get('control_type'))} | "
                f"{markdown_cell(summary_item.get('automation_id'))} | "
                f"{markdown_cell(summary_item.get('class_name'))} |"
            )
        lines.append("")

    if new_images:
        lines.extend(["## 新图片", ""])
        for item in new_images:
            lines.append(f"- {markdown_cell(item.get('path'), 160)} ({item.get('size_bytes')} bytes)")
        lines.append("")

    lines.extend(["## 操作日志", ""])
    for entry in log:
        lines.append(f"- [{markdown_cell(entry.get('step'))}] {markdown_cell(entry.get('message'), 200)}")
    lines.append("")
    return "\n".join(lines)


def assisted_rpa_plan() -> list[dict[str, Any]]:
    steps = [
        "find_window",
        "activate_existing_window",
        "locate_my_tab",
        "locate_game_entry",
        "locate_battle_record_entry",
        "locate_character_overview",
        "locate_character_detail",
        "locate_share_or_export_button",
        "invoke_official_export",
        "wait_for_image_file",
    ]
    return [
        {
            "step": step,
            "status": "planned_only",
            "wait_required": True,
            "fixed_coordinate_click_allowed": False,
        }
        for step in steps
    ]


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    before_images = image_files(output_dir)
    operation_log: list[dict[str, Any]] = []
    summary = {
        "window_found": False,
        "share_button_found": False,
        "export_triggered": False,
        "new_image_found": False,
        "image_paths": [],
        "error_reason": "",
    }

    def log(step: str, message: str) -> None:
        operation_log.append({"time": now_iso(), "step": step, "message": redact_text(message)})

    button_candidates: list[dict[str, Any]] = []
    top_windows: list[dict[str, Any]] = []

    try:
        automation, _ = load_uia()
        log("load_uia", "Windows UI Automation initialized.")
        window, top_windows = find_window(automation, args.window_title)
        if window is None:
            summary["error_reason"] = f"No window matched title keyword: {args.window_title}"
            log("find_window", summary["error_reason"])
        else:
            summary["window_found"] = True
            matched_window = element_summary(window, 0)
            log("find_window", f"Matched window: {matched_window.get('name')}")

            if args.mode == "assisted-rpa":
                log("assisted_rpa", "Prototype only records the planned step framework; full navigation is not implemented.")

            matches = search_share_controls(window, automation, max_depth=8)
            button_candidates = [{"summary": item["summary"]} for item in matches]
            summary["share_button_found"] = bool(matches)
            log("search_share_button", f"Found {len(matches)} share/export/save candidates.")

            if matches and args.mode == "manual-page":
                target = matches[0]
                target_name = target["summary"].get("name") or target["summary"].get("automation_id") or "<unnamed>"
                if args.dry_run:
                    log("trigger_export", f"Dry-run: would invoke candidate '{target_name}'.")
                else:
                    ok, message = invoke_element(target["element"])
                    summary["export_triggered"] = ok
                    log("trigger_export", f"{message} Target: {target_name}")
                    time.sleep(max(0.0, args.wait_seconds))
            elif not matches:
                log(
                    "search_share_button",
                    "No UIA-visible share/export button found. Later work may need image template matching; no fixed-coordinate click was attempted.",
                )
    except ProbeError as exc:
        summary["error_reason"] = str(exc)
        log("probe_error", str(exc))

    after_images = image_files(output_dir)
    new_keys = sorted(set(after_images) - set(before_images))
    new_images = [after_images[key] for key in new_keys]
    summary["new_image_found"] = bool(new_images)
    summary["image_paths"] = [relative_probe_path(Path(item["path"])) for item in new_images]
    if not new_images and not summary["error_reason"]:
        summary["error_reason"] = "No new image file was found in the output directory."

    if args.mode == "assisted-rpa":
        operation_log.extend(assisted_rpa_plan())

    return {
        "metadata": {
            "probe": "miyoushe_export_image_probe",
            "created_at": now_iso(),
            "window_title_keyword": redact_text(args.window_title),
            "game": args.game,
            "mode": args.mode,
            "dry_run": bool(args.dry_run),
            "output_dir": relative_probe_path(output_dir),
            "notes": [
                "Prototype only. Not a formal collector.",
                "No automatic login, credential input, packet capture, token reads, game-client control, or SQLite writes.",
            ],
        },
        "summary": summary,
        "button_candidates": button_candidates,
        "new_images": new_images,
        "top_windows_sample": top_windows[:30],
        "operation_log": operation_log,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prototype RPA probe for MiYouShe official export/share image UI. "
            "Does not log in, read tokens, capture packets, or use fixed-coordinate clicks."
        )
    )
    parser.add_argument("--window-title", default="米游社", help="Window title keyword. Default: 米游社")
    parser.add_argument("--game", choices=("zzz", "hsr"), required=True, help="Game route to probe.")
    parser.add_argument("--mode", choices=("manual-page", "assisted-rpa"), default="manual-page")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to watch for exported images.")
    parser.add_argument("--dry-run", action="store_true", help="Find candidates but do not invoke any UIA action.")
    parser.add_argument("--wait-seconds", type=float, default=3.0, help="Wait after invoking export. Default: 3")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    result = run_probe(args)
    json_path, md_path = write_outputs(result)
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")

    summary = result["summary"]
    if summary.get("window_found") and (args.dry_run or summary.get("export_triggered") or args.mode == "assisted-rpa"):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
