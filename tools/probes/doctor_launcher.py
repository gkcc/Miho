from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Callable


SCHEMA_VERSION = "p3.2-lite-doctor-launcher"
FORBIDDEN_COMMAND_FRAGMENTS = ("&", "|", ";", "`", "$(", ">", "<")
FORBIDDEN_SCRIPT_SUFFIXES = (".bat", ".cmd", ".ps1", ".sh")
FORBIDDEN_TOOL_NAMES = ("apply_review_decisions.py", "preview_review_decisions.py")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"doctor JSON must be an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def default_output_dir(doctor_path: Path) -> Path:
    if doctor_path.parent.name == "demo_doctor":
        return doctor_path.parent.parent / "launcher"
    return doctor_path.parent / "launcher"


def command_for_action(doctor: dict[str, Any], primary_next_action: str) -> str | None:
    commands = doctor.get("commands") if isinstance(doctor.get("commands"), dict) else {}
    if primary_next_action == "rerun_demo_pipeline":
        return commands.get("rerun_demo")
    if primary_next_action == "safe_apply_review_decisions":
        return commands.get("safe_apply")
    if primary_next_action == "review_snapshots":
        return commands.get("preview")
    return None


def split_command(command: str) -> list[str]:
    return shlex.split(command, posix=sys.platform != "win32")


def contains_shell_control(command: str) -> bool:
    return any(fragment in command for fragment in FORBIDDEN_COMMAND_FRAGMENTS)


def is_python_executable(value: str) -> bool:
    name = Path(value).name.lower()
    return name in {"python", "python.exe", "py", "py.exe"}


def is_run_demo_pipeline_script(value: str) -> bool:
    normalized = value.replace("\\", "/").lower()
    return normalized.endswith("tools/probes/run_demo_pipeline.py")


def validate_rerun_command(command: str | None) -> tuple[list[str], list[str]]:
    if not command:
        return [], ["missing_rerun_command"]
    if contains_shell_control(command):
        return [], ["launcher_command_contains_shell_control"]
    try:
        args = split_command(command)
    except ValueError:
        return [], ["launcher_command_parse_failed"]
    blockers: list[str] = []
    lowered = [arg.lower() for arg in args]
    if not args or not is_python_executable(args[0]):
        blockers.append("launcher_command_not_python")
    if len(args) < 2 or not is_run_demo_pipeline_script(args[1]):
        blockers.append("launcher_command_not_allowlisted")
    if any(arg.endswith(FORBIDDEN_SCRIPT_SUFFIXES) for arg in lowered):
        blockers.append("launcher_command_forbidden_script_type")
    if any(any(tool_name in arg for tool_name in FORBIDDEN_TOOL_NAMES) for arg in lowered):
        blockers.append("launcher_command_forbidden_tool")
    return args, list(dict.fromkeys(blockers))


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Doctor Launcher Report",
        "",
        f"- launcher_status: {report.get('launcher_status')}",
        f"- doctor_status: {report.get('doctor_status')}",
        f"- primary_next_action: {report.get('primary_next_action')}",
        f"- allowed_for_launcher: {report.get('allowed_for_launcher')}",
        f"- executed: {report.get('executed')}",
        f"- command: `{report.get('command') or 'N/A'}`",
        f"- reason: {report.get('reason') or 'N/A'}",
        f"- cwd: `{report.get('cwd') or 'N/A'}`",
        f"- python_executable: `{report.get('python_executable') or 'N/A'}`",
        f"- started_at: {report.get('started_at')}",
        f"- finished_at: {report.get('finished_at')}",
        f"- duration_ms: {report.get('duration_ms')}",
        "",
    ]
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
        lines.append("")
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    follow_up = report.get("follow_up") if isinstance(report.get("follow_up"), dict) else {}
    if follow_up:
        lines.extend(["## Follow-up Doctor", ""])
        for key in ("doctor_path", "loaded", "doctor_status", "primary_next_action", "try_now_allowed", "strict_status"):
            lines.append(f"- {key}: {follow_up.get(key)}")
        follow_up_warnings = follow_up.get("warnings") if isinstance(follow_up.get("warnings"), list) else []
        for item in follow_up_warnings:
            lines.append(f"- warning: {item}")
        lines.append("")
    return "\n".join(lines)


def summarize_follow_up_doctor(doctor_path: Path) -> dict[str, Any]:
    follow_up: dict[str, Any] = {
        "doctor_path": str(doctor_path),
        "loaded": False,
        "doctor_status": None,
        "primary_next_action": None,
        "try_now_allowed": None,
        "strict_status": None,
        "warnings": [],
    }
    try:
        doctor = load_json(doctor_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        follow_up["warnings"].append(f"follow_up_doctor_unavailable: {exc}")
        return follow_up
    evidence = doctor.get("evidence_check") if isinstance(doctor.get("evidence_check"), dict) else {}
    follow_up.update(
        {
            "loaded": True,
            "doctor_status": doctor.get("doctor_status"),
            "primary_next_action": doctor.get("primary_next_action"),
            "try_now_allowed": doctor.get("try_now_allowed"),
            "strict_status": evidence.get("strict_status") or evidence.get("status"),
        }
    )
    return follow_up


def build_blockers(
    *,
    primary_next_action: str,
    action_contract: dict[str, Any],
    strict_status: str,
    execute_rerun: bool,
    command: str | None,
) -> list[str]:
    blockers: list[str] = []
    if strict_status == "blocked":
        blockers.append("evidence_strict_status_blocked")
    if action_contract.get("writes_roster") is True:
        blockers.append("launcher_disallows_writes_roster")
    if action_contract.get("requires_manual_confirmation") is True:
        blockers.append("launcher_disallows_manual_confirmation_action")
    if primary_next_action == "safe_apply_review_decisions":
        blockers.append("launcher_never_executes_safe_apply")
    if primary_next_action == "try_now":
        blockers.append("launcher_does_not_execute_try_now")
    if execute_rerun:
        if primary_next_action != "rerun_demo_pipeline":
            blockers.append("execute_rerun_only_supports_rerun_demo_pipeline")
        if action_contract.get("allowed_for_launcher") is not True:
            blockers.append("action_contract_not_allowed_for_launcher")
        if not command:
            blockers.append("missing_rerun_command")
    return list(dict.fromkeys(blockers))


def launch_doctor(
    *,
    doctor_path: Path,
    output_dir: Path | None = None,
    execute_rerun: bool = False,
    fail_on_blocked: bool = False,
    follow_up_doctor_path: Path | None = None,
    argv: list[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> tuple[int, dict[str, Any]]:
    started_monotonic = time.monotonic()
    started_at = now_iso()
    doctor = load_json(doctor_path)
    action_contract = doctor.get("action_contract") if isinstance(doctor.get("action_contract"), dict) else {}
    evidence = doctor.get("evidence_check") if isinstance(doctor.get("evidence_check"), dict) else {}
    primary_next_action = str(doctor.get("primary_next_action") or action_contract.get("primary_next_action") or "unknown")
    strict_status = str(evidence.get("strict_status") or evidence.get("status") or "unknown")
    command = command_for_action(doctor, primary_next_action)
    allowed = action_contract.get("allowed_for_launcher") is True
    blockers = build_blockers(
        primary_next_action=primary_next_action,
        action_contract=action_contract,
        strict_status=strict_status,
        execute_rerun=execute_rerun,
        command=command,
    )
    command_args: list[str] = []
    if execute_rerun:
        command_args, command_blockers = validate_rerun_command(command)
        blockers.extend(command_blockers)
        blockers = list(dict.fromkeys(blockers))
    warnings: list[str] = []
    executed = False
    returncode: int | None = None
    launcher_status = "printed"

    if execute_rerun:
        if blockers:
            launcher_status = "blocked"
        else:
            completed = runner(command_args, check=False)
            executed = True
            returncode = int(getattr(completed, "returncode", 0))
            launcher_status = "executed"
            if returncode != 0:
                blockers.append("rerun_command_failed")
    elif not allowed:
        warnings.append("manual_only_action_printed")
    if fail_on_blocked and blockers and not executed:
        launcher_status = "blocked"
    follow_up: dict[str, Any] | None = None
    if execute_rerun and executed and returncode == 0 and follow_up_doctor_path is not None:
        follow_up = summarize_follow_up_doctor(follow_up_doctor_path)
        if not follow_up.get("loaded"):
            launcher_status = "executed_with_followup_warning"
            warnings.append("follow_up_doctor_unavailable")

    reason = str(action_contract.get("reason") or "")
    finished_at = now_iso()
    report = {
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": round((time.monotonic() - started_monotonic) * 1000, 3),
        "argv": argv or [],
        "cwd": str(Path.cwd()),
        "python_executable": sys.executable,
        "launcher_status": launcher_status,
        "doctor_status": doctor.get("doctor_status"),
        "headline": doctor.get("headline"),
        "primary_next_action": primary_next_action,
        "strict_status": strict_status,
        "allowed_for_launcher": allowed,
        "executed": executed,
        "returncode": returncode,
        "command": command,
        "command_args": command_args,
        "reason": reason,
        "action_contract": action_contract,
        "warnings": warnings,
        "blockers": blockers,
    }
    if follow_up is not None:
        report["follow_up"] = follow_up
    out_dir = output_dir or default_output_dir(doctor_path)
    json_path = out_dir / "launcher_report.json"
    md_path = out_dir / "launcher_report.md"
    report["output_json"] = str(json_path)
    report["output_md"] = str(md_path)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_report(report), encoding="utf-8")

    if launcher_status == "blocked" or (executed and returncode not in (0, None)):
        exit_code = 2 if returncode in (0, None) else int(returncode)
    else:
        exit_code = 0
    return exit_code, report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print or safely launch the current demo doctor action.")
    parser.add_argument("--doctor", required=True, help="Path to demo_doctor.json")
    parser.add_argument("--output-dir", default=None, help="Directory for launcher_report.json/md")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print-command", action="store_true", help="Explicitly print/report the command without executing it.")
    mode.add_argument("--execute-rerun", action="store_true", help="Execute only an allowed rerun_demo_pipeline action.")
    parser.add_argument("--fail-on-blocked", action="store_true", help="Return non-zero when the launcher report contains blockers.")
    parser.add_argument("--follow-up-doctor", default=None, help="Read this demo_doctor.json after a successful rerun and report the next state.")
    return parser


def run_launcher(argv: list[str] | None = None, *, runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run) -> int:
    args = build_arg_parser().parse_args(argv)
    doctor_path = Path(args.doctor)
    output_dir = Path(args.output_dir) if args.output_dir else None
    follow_up_doctor = Path(args.follow_up_doctor) if args.follow_up_doctor else None
    try:
        exit_code, report = launch_doctor(
            doctor_path=doctor_path,
            output_dir=output_dir,
            execute_rerun=bool(args.execute_rerun),
            fail_on_blocked=bool(args.fail_on_blocked),
            follow_up_doctor_path=follow_up_doctor,
            argv=argv if argv is not None else sys.argv[1:],
            runner=runner,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"doctor_launcher_error: {exc}", file=sys.stderr)
        return 2
    print(f"launcher_status: {report['launcher_status']}")
    print(f"doctor_status: {report.get('doctor_status')}")
    print(f"primary_next_action: {report.get('primary_next_action')}")
    print(f"allowed_for_launcher: {report.get('allowed_for_launcher')}")
    print(f"executed: {report.get('executed')}")
    print(f"command: {report.get('command') or 'N/A'}")
    print(f"reason: {report.get('reason') or 'N/A'}")
    print(f"launcher_report_json: {report.get('output_json')}")
    print(f"launcher_report_md: {report.get('output_md')}")
    follow_up = report.get("follow_up") if isinstance(report.get("follow_up"), dict) else {}
    if follow_up:
        print(f"follow_up_loaded: {follow_up.get('loaded')}")
        print(f"follow_up_doctor_status: {follow_up.get('doctor_status')}")
        print(f"follow_up_primary_next_action: {follow_up.get('primary_next_action')}")
        print(f"follow_up_try_now_allowed: {follow_up.get('try_now_allowed')}")
        print(f"follow_up_strict_status: {follow_up.get('strict_status')}")
    if report.get("blockers"):
        print("blockers:")
        for item in report["blockers"]:
            print(f"- {item}")
    if report.get("warnings"):
        print("warnings:")
        for item in report["warnings"]:
            print(f"- {item}")
    return exit_code


def main() -> None:
    raise SystemExit(run_launcher())


if __name__ == "__main__":
    main()
