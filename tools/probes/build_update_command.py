#!/usr/bin/env python
"""Build a safe local update command pack for the demo dashboard."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p3.9-lite-update-command"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "demo"
DEFAULT_MAX_HISTORY = 30


class UpdateCommandError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def shell_quote(value: str) -> str:
    if not value:
        return '""'
    if any(char.isspace() for char in value) or any(char in value for char in '"`$&|<>'):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def command_from_argv(argv: list[str]) -> str:
    return " ".join(shell_quote(part) for part in argv)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise UpdateCommandError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UpdateCommandError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise UpdateCommandError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_launcher_argv(
    *,
    demo_doctor_path: Path,
    output_dir: Path,
    max_history: int,
) -> list[str]:
    return [
        "python",
        "tools/probes/doctor_launcher.py",
        "--doctor",
        display_path(demo_doctor_path),
        "--execute-rerun",
        "--follow-up-doctor",
        display_path(demo_doctor_path),
        "--refresh-dashboard",
        "--dashboard-summary",
        display_path(output_dir / "demo_summary.json"),
        "--dashboard-html",
        display_path(output_dir / "index.html"),
        "--max-history",
        str(max_history),
    ]


def readiness_blockers(doctor: dict[str, Any], demo_command: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    action_contract = doctor.get("action_contract") if isinstance(doctor.get("action_contract"), dict) else {}
    evidence = doctor.get("evidence_check") if isinstance(doctor.get("evidence_check"), dict) else {}
    if doctor.get("primary_next_action") != "rerun_demo_pipeline":
        blockers.append("primary_next_action_not_rerun_demo_pipeline")
    if action_contract.get("allowed_for_launcher") is not True:
        blockers.append("launcher_not_allowed_by_action_contract")
    if action_contract.get("writes_roster") is not False:
        blockers.append("action_contract_writes_roster")
    if action_contract.get("requires_manual_confirmation") is not False:
        blockers.append("action_contract_requires_manual_confirmation")
    if evidence.get("strict_status") == "blocked":
        blockers.append("evidence_check_strict_status_blocked")
    if demo_command.get("safe_to_rerun") is not True:
        blockers.append("demo_command_not_safe_to_rerun")
    return list(dict.fromkeys(blockers))


def build_update_command(
    *,
    output_dir: Path,
    demo_doctor: Path,
    demo_command: Path,
    max_history: int = DEFAULT_MAX_HISTORY,
) -> dict[str, Any]:
    doctor_data = load_json(demo_doctor)
    command_data = load_json(demo_command)
    blockers = readiness_blockers(doctor_data, command_data)
    warnings: list[str] = []
    if max_history < 1:
        blockers.append("max_history_must_be_positive")
    status = "blocked" if blockers else "ready"
    argv = build_launcher_argv(demo_doctor_path=demo_doctor, output_dir=output_dir, max_history=max_history) if status == "ready" else []
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "status": status,
        "command": command_from_argv(argv) if argv else None,
        "argv": argv,
        "updates": [
            "accepted roster based local suggestions",
            "endgame plan",
            "tier watchlist view",
            "dashboard visualization",
        ],
        "does_not_update": [
            "official account data",
            "tokens/cookies/login state",
            "online tier data",
            "formal database",
        ],
        "blockers": blockers,
        "warnings": warnings,
        "input": {
            "demo_doctor": display_path(demo_doctor),
            "demo_command": display_path(demo_command),
            "demo_doctor_primary_next_action": doctor_data.get("primary_next_action"),
            "demo_command_safe_to_rerun": command_data.get("safe_to_rerun"),
            "max_history": max_history,
        },
    }
    output_path = output_dir / "update_command"
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "update_command.json"
    md_path = output_path / "update_command.md"
    result["output_json"] = display_path(json_path)
    result["output_md"] = display_path(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 本地更新命令",
        "",
        f"- status: {result.get('status')}",
        f"- schema_version: {result.get('schema_version')}",
        "",
        "这是一条本地 demo 更新命令记录，只用于刷新 accepted roster 相关建议、终局方案、tier watchlist 展示和 Dashboard 可视化。",
        "它不会读取登录态、不会联网抓 tier 或高难数据、不会写正式数据库。",
    ]
    command = result.get("command")
    if command:
        lines.extend(["", "## Command", "", f"```powershell\n{command}\n```"])
    blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a safe local update command pack.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--demo-doctor", required=True)
    parser.add_argument("--demo-command", required=True)
    parser.add_argument("--max-history", type=int, default=DEFAULT_MAX_HISTORY)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_update_command(
            output_dir=resolve_path(args.output_dir),
            demo_doctor=resolve_path(args.demo_doctor),
            demo_command=resolve_path(args.demo_command),
            max_history=args.max_history,
        )
    except UpdateCommandError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"status: {result['status']}")
    if result.get("command"):
        print(f"command: {result['command']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
