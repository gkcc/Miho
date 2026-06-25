#!/usr/bin/env python
"""Read-only Windows UI Automation dump for the MiYouShe app."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "probes"

CONTROL_TYPE_NAMES = {
    50000: "Button",
    50001: "Calendar",
    50002: "CheckBox",
    50003: "ComboBox",
    50004: "Edit",
    50005: "Hyperlink",
    50006: "Image",
    50007: "ListItem",
    50008: "List",
    50009: "Menu",
    50010: "MenuBar",
    50011: "MenuItem",
    50012: "ProgressBar",
    50013: "RadioButton",
    50014: "ScrollBar",
    50015: "Slider",
    50016: "Spinner",
    50017: "StatusBar",
    50018: "Tab",
    50019: "TabItem",
    50020: "Text",
    50021: "ToolBar",
    50022: "ToolTip",
    50023: "Tree",
    50024: "TreeItem",
    50025: "Custom",
    50026: "Group",
    50027: "Thumb",
    50028: "DataGrid",
    50029: "DataItem",
    50030: "Document",
    50031: "SplitButton",
    50032: "Window",
    50033: "Pane",
    50034: "Header",
    50035: "HeaderItem",
    50036: "Table",
    50037: "TitleBar",
    50038: "Separator",
    50039: "SemanticZoom",
    50040: "AppBar",
}

SECRET_VALUE_RE = re.compile(
    r"(?i)\b(cookie|token|stoken|ltoken|session|auth|authorization)\b"
    r"(\s*[:=]\s*)"
    r"([^,\s;\"']+)"
)
BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._\-+/=]+")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEYED_ID_RE = re.compile(r"(?i)\b(uid|account_id|accountid|user_id|userid)\b(\s*[:=：]?\s*)\d{4,}")
LONG_DIGIT_RE = re.compile(r"(?<!\d)\d{8,12}(?!\d)")


class ProbeError(RuntimeError):
    pass


def redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
    text = BEARER_RE.sub(r"\1[REDACTED_SECRET]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = KEYED_ID_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_ID]", text)
    text = LONG_DIGIT_RE.sub("[REDACTED_ID]", text)
    return text


def truncate(text: str, limit: int = 160) -> str:
    clean = text.replace("\r", " ").replace("\n", " ").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def markdown_cell(value: Any, limit: int = 80) -> str:
    text = truncate(redact_text(value), limit)
    return text.replace("|", "\\|")


def utcish_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def output_stem() -> str:
    return datetime.now().strftime("miyoushe_uia_%Y%m%d_%H%M%S")


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


def element_summary(element: Any, depth: int) -> dict[str, Any]:
    name = redact_text(safe_current(element, "CurrentName", ""))
    control_type = safe_current(element, "CurrentControlType", 0)
    try:
        control_type_id = int(control_type)
    except Exception:
        control_type_id = None
    automation_id = redact_text(safe_current(element, "CurrentAutomationId", ""))
    class_name = redact_text(safe_current(element, "CurrentClassName", ""))
    rect = rect_to_dict(safe_current(element, "CurrentBoundingRectangle", None))
    is_offscreen = bool(safe_current(element, "CurrentIsOffscreen", False))

    return {
        "depth": depth,
        "name": name,
        "control_type": control_type_name(control_type),
        "control_type_id": control_type_id,
        "automation_id": automation_id,
        "class_name": class_name,
        "bounding_rectangle": rect,
        "is_offscreen": is_offscreen,
    }


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
        if keyword in haystack:
            return child, candidates

    return None, candidates


def dump_tree(root: Any, automation: Any, max_depth: int, max_nodes: int) -> tuple[list[dict[str, Any]], list[str], bool]:
    walker = automation.ControlViewWalker
    records: list[dict[str, Any]] = []
    visible_texts: list[str] = []
    seen_texts: set[str] = set()
    truncated_by_limit = False

    def visit(element: Any, depth: int) -> None:
        nonlocal truncated_by_limit
        if len(records) >= max_nodes:
            truncated_by_limit = True
            return

        summary = element_summary(element, depth)
        records.append(summary)

        name = summary.get("name", "").strip()
        if name and not summary.get("is_offscreen") and name not in seen_texts:
            seen_texts.add(name)
            visible_texts.append(name)

        if depth >= max_depth:
            return

        for child in iter_children(walker, element):
            if len(records) >= max_nodes:
                truncated_by_limit = True
                break
            visit(child, depth + 1)

    visit(root, 0)
    return records, visible_texts, truncated_by_limit


def write_outputs(result: dict[str, Any]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem()
    json_path = OUTPUT_DIR / f"{stem}.json"
    md_path = OUTPUT_DIR / f"{stem}.md"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return json_path, md_path


def render_markdown(result: dict[str, Any]) -> str:
    meta = result["metadata"]
    texts = result.get("visible_texts", [])
    controls = result.get("controls", [])
    warnings = result.get("warnings", [])

    lines = [
        "# 米游社 UIA 只读 Dump",
        "",
        "## 摘要",
        "",
        f"- 创建时间：{markdown_cell(meta.get('created_at'), 120)}",
        f"- 窗口标题关键字：{markdown_cell(meta.get('window_title_keyword'), 120)}",
        f"- 匹配窗口：{markdown_cell(meta.get('matched_window', {}).get('name'), 120)}",
        f"- 控件数量：{len(controls)}",
        f"- 可见文本数量：{len(texts)}",
        f"- 最大深度：{meta.get('max_depth')}",
        f"- 最大节点数：{meta.get('max_nodes')}",
        "",
        "## 限制",
        "",
        "- 本工具不点击、不滚动、不截图、不登录、不抓包、不读取 cookie/token/stoken/ltoken。",
        "- 输出已经按内置规则脱敏，但仍应人工复核后再用于后续分析。",
        "- 本文件不得提交 Git。",
        "",
    ]

    if warnings:
        lines.extend(["## 警告", ""])
        for warning in warnings:
            lines.append(f"- {markdown_cell(warning, 160)}")
        lines.append("")

    lines.extend(["## 可见文本", ""])
    for text in texts[:200]:
        lines.append(f"- {markdown_cell(text, 160)}")
    if len(texts) > 200:
        lines.append(f"- ... 还有 {len(texts) - 200} 条")
    lines.append("")

    lines.extend(
        [
            "## 控件树摘要",
            "",
            "| depth | control_type | name | automation_id | class_name | offscreen |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for item in controls[:500]:
        lines.append(
            "| "
            f"{item.get('depth')} | "
            f"{markdown_cell(item.get('control_type'))} | "
            f"{markdown_cell(item.get('name'))} | "
            f"{markdown_cell(item.get('automation_id'))} | "
            f"{markdown_cell(item.get('class_name'))} | "
            f"{item.get('is_offscreen')} |"
        )
    if len(controls) > 500:
        lines.append(f"| ... | ... | 还有 {len(controls) - 500} 个控件 | ... | ... | ... |")

    lines.append("")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only UIA dump for the current MiYouShe window. No clicking, scrolling, screenshots, login, or token reads."
    )
    parser.add_argument("--window-title", default="米游社", help="Window title keyword to match. Default: 米游社")
    parser.add_argument("--depth", type=int, default=8, help="Maximum UIA tree depth. Default: 8")
    parser.add_argument("--max-nodes", type=int, default=3000, help="Maximum controls to dump. Default: 3000")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    max_depth = max(0, min(args.depth, 20))
    max_nodes = max(1, args.max_nodes)

    try:
        automation, _ = load_uia()
        window, candidates = find_window(automation, args.window_title)
        if window is None:
            print(f"ERROR: No top-level window matched title keyword: {args.window_title}", file=sys.stderr)
            if candidates:
                print("Visible top-level windows:", file=sys.stderr)
                for candidate in candidates[:30]:
                    print(
                        "  - "
                        f"{candidate.get('name') or '<empty>'} "
                        f"[{candidate.get('control_type')}, {candidate.get('class_name')}]",
                        file=sys.stderr,
                    )
            return 2

        matched_window = element_summary(window, 0)
        controls, visible_texts, truncated_by_limit = dump_tree(window, automation, max_depth, max_nodes)
        warnings = []
        if truncated_by_limit:
            warnings.append("UIA dump reached --max-nodes and was truncated.")

        result = {
            "metadata": {
                "probe": "miyoushe_uia_dump",
                "created_at": utcish_timestamp(),
                "window_title_keyword": redact_text(args.window_title),
                "matched_window": matched_window,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "notes": [
                    "Read-only UI Automation dump.",
                    "No clicking, scrolling, screenshots, login, packet capture, token reads, or SQLite writes.",
                ],
            },
            "warnings": warnings,
            "visible_texts": visible_texts,
            "controls": controls,
        }

        json_path, md_path = write_outputs(result)
        print(f"Wrote JSON: {json_path}")
        print(f"Wrote Markdown: {md_path}")
        return 0
    except ProbeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
