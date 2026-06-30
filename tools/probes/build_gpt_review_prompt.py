#!/usr/bin/env python
"""Build a compact review prompt for the Codex/GPT adversarial loop."""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HANDOFF_PROMPT = PROJECT_ROOT / "data" / "probes" / "demo" / "gpt_review_prompt.md"

DEFAULT_CONSTRAINTS = (
    "不换 OCR 引擎，当前主线仍是 PaddleOCR + expected diff + replay batch。",
    "不 UIA，不初始化 Tauri，不自动登录米游社，不控制游戏客户端。",
    "不读取、打印、保存 cookie/token/stoken/ltoken。",
    "不提交 data/probes、真实图片、UID、OCR 原始结果或本地账号数据。",
    "OCR/解析结果只能进入人工复核区，不能自动写正式数据库。",
)

DEFAULT_REVIEW_QUESTIONS = (
    "这个方案有没有方向性问题？",
    "有没有会污染数据、绕过人工确认或误判通过率的风险？",
    "下一步最小可验证实验是什么？",
)

REVIEWER_PROTOCOL = (
    "你是右侧 GPT reviewer，只审本包，不需要读取聊天历史或让 Codex 重新探索页面。",
    "请优先挑 P0/P1 缺陷；没有硬证据时明确写“证据不足”。",
    "不要要求改代码，给出最小实验和验收证据即可；Codex 会自行实现、测试、提交和推送。",
)

EXPECTED_REPLY = (
    "Findings：",
    "- [P0/P1/P2] 问题、影响、证据。",
    "",
    "Risks：",
    "- 可能误伤或需要守住的边界。",
    "",
    "Next experiment：",
    "- 一条最小命令或一个最小改动。",
    "",
    "Acceptance：",
    "- 通过/失败应该看哪条硬证据。",
)


def repo_relative(path_text: str) -> str:
    path = Path(path_text)
    if not path.is_absolute():
        return path_text
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except (OSError, ValueError):
        return str(path_text)


def bullet_lines(items: Iterable[str], fallback: str) -> list[str]:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        cleaned = [fallback]
    return [f"- {item}" for item in cleaned]


def collect_git_status() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return ["git status 不可用。"]
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return [f"git status 失败：{detail or result.returncode}"]
    lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    return lines or ["工作区无 tracked 改动。"]


def normalize_changed_files(values: Iterable[str]) -> list[str]:
    normalized = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if "：" in text:
            path, detail = text.split("：", 1)
            normalized.append(f"{repo_relative(path.strip())}：{detail.strip()}")
        elif ": " in text:
            path, detail = text.split(": ", 1)
            normalized.append(f"{repo_relative(path.strip())}：{detail.strip()}")
        else:
            normalized.append(repo_relative(text))
    return normalized


def render_prompt(
    *,
    focus: str,
    evidence: list[str],
    changed_files: list[str],
    questions: list[str],
    constraints: list[str],
    include_git_status: bool,
) -> str:
    all_constraints = list(DEFAULT_CONSTRAINTS) + constraints
    review_questions = questions or list(DEFAULT_REVIEW_QUESTIONS)
    evidence_lines = list(evidence)
    if include_git_status:
        evidence_lines.append("git status --short：")
        evidence_lines.extend(f"  {line}" for line in collect_git_status())

    sections = [
        "给右侧 GPT 的审查包",
        "",
        "使用方式：",
        "- 把这份审查包完整发给右侧 GPT。",
        "- 右侧 GPT 只按本包审方案和风险，不要求 Codex 继续翻右侧历史。",
        "- 收到 Findings 后，Codex 先本地验证，再决定是否改代码。",
        "",
        "Reviewer protocol：",
        *bullet_lines(REVIEWER_PROTOCOL, "只审本包，按证据输出。"),
        "",
        "目标：",
        f"- {focus.strip() or '请审视当前方案并指出最高风险。'}",
        "",
        "当前证据：",
        *bullet_lines(evidence_lines, "暂无额外证据；以本地仓库和命令输出为准。"),
        "",
        "已改文件：",
        *bullet_lines(normalize_changed_files(changed_files), "暂无已改文件；本轮可能仍在方案审查阶段。"),
        "",
        "请审：",
        *bullet_lines(review_questions, "请指出最高风险和最小下一步实验。"),
        "",
        "约束：",
        *bullet_lines(all_constraints, "遵守项目隐私、安全和人工复核边界。"),
        "",
        "请按以下格式回复：",
        *EXPECTED_REPLY,
        "",
    ]
    return "\n".join(sections)


def copy_text_to_windows_clipboard(text: str) -> tuple[bool, str]:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    cf_unicode_text = 13
    gmem_moveable = 0x0002
    data = (text + "\0").encode("utf-16le")
    for _attempt in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.08)
    else:
        return False, "OpenClipboard failed"
    handle = None
    try:
        if not user32.EmptyClipboard():
            return False, "EmptyClipboard failed"
        handle = kernel32.GlobalAlloc(gmem_moveable, len(data))
        if not handle:
            return False, "GlobalAlloc failed"
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return False, "GlobalLock failed"
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(cf_unicode_text, handle):
            return False, "SetClipboardData failed"
        handle = None
        return True, "Windows Unicode clipboard"
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def copy_text_to_clipboard(text: str) -> tuple[bool, str]:
    if not text:
        return False, "empty prompt"
    if sys.platform.startswith("win"):
        copied, winapi_detail = copy_text_to_windows_clipboard(text)
        if copied:
            return copied, winapi_detail
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
                handle.write(text)
                temp_path = Path(handle.name)
            literal_path = str(temp_path).replace("'", "''")
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-Content -Raw -Encoding UTF8 -LiteralPath '{literal_path}' | Set-Clipboard",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if result.returncode == 0:
                return True, "powershell Set-Clipboard"
            detail = (result.stderr or result.stdout or "").strip()
            powershell_detail = detail or f"Set-Clipboard exited {result.returncode}"
            return False, f"WinAPI failed: {winapi_detail}; PowerShell failed: {powershell_detail}"
        except OSError as exc:
            return False, str(exc)
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    return False, f"clipboard copy is not supported on {sys.platform}"


def write_prompt_file(path: Path, prompt: str) -> Path:
    output_path = path if path.is_absolute() else PROJECT_ROOT / path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a compact prompt for right-side GPT review.")
    parser.add_argument("--focus", required=True, help="本轮要推进的用户可见目标。")
    parser.add_argument("--evidence", action="append", default=[], help="关键证据，可重复。")
    parser.add_argument("--changed-file", action="append", default=[], help='已改文件，可写 "path: 改了什么"，可重复。')
    parser.add_argument("--question", action="append", default=[], help="额外请审问题，可重复；不传则使用默认问题。")
    parser.add_argument("--constraint", action="append", default=[], help="额外约束，可重复。")
    parser.add_argument("--no-git-status", action="store_true", help="不要自动附带 git status --short。")
    parser.add_argument("--output", default=None, help="可选输出路径；不传则打印到 stdout。")
    parser.add_argument("--copy", action="store_true", help="把审查包复制到系统剪贴板，方便直接粘贴到右侧 GPT。")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    prompt = render_prompt(
        focus=args.focus,
        evidence=args.evidence,
        changed_files=args.changed_file,
        questions=args.question,
        constraints=args.constraint,
        include_git_status=not args.no_git_status,
    )
    copied = False
    copy_failed_detail = ""
    if args.copy:
        copied, detail = copy_text_to_clipboard(prompt)
        if not copied:
            copy_failed_detail = detail
            print(f"gpt_review_clipboard: unavailable ({detail})")
        else:
            print("gpt_review_clipboard: copied")
    if args.output:
        output_path = write_prompt_file(Path(args.output), prompt)
        print(f"gpt_review_prompt: {output_path}")
        return 0
    if copy_failed_detail:
        output_path = write_prompt_file(DEFAULT_HANDOFF_PROMPT, prompt)
        print(f"gpt_review_prompt: {output_path}")
        print("gpt_review_next: open the prompt file and paste it into the right-side GPT.")
        return 0
    if copied:
        return 0
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
