from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Callable


SCHEMA_VERSION = "p3.4-lite-doctor-launcher"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_DEMO_PIPELINE_SCRIPT = (PROJECT_ROOT / "tools" / "probes" / "run_demo_pipeline.py").resolve()
FORBIDDEN_COMMAND_FRAGMENTS = ("&", "|", ";", "`", "$(", ">", "<")
FORBIDDEN_SCRIPT_SUFFIXES = (".bat", ".cmd", ".ps1", ".sh")
FORBIDDEN_TOOL_NAMES = ("apply_review_decisions.py", "preview_review_decisions.py")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def history_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S_%f%z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


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


def resolve_command_script(value: str) -> Path:
    script_path = Path(value)
    if not script_path.is_absolute():
        script_path = PROJECT_ROOT / script_path
    return script_path.resolve()


def validate_rerun_command(command: str | None) -> tuple[list[str], list[str], str | None]:
    if not command:
        return [], ["missing_rerun_command"], None
    if contains_shell_control(command):
        return [], ["launcher_command_contains_shell_control"], None
    try:
        args = split_command(command)
    except ValueError:
        return [], ["launcher_command_parse_failed"], None
    blockers: list[str] = []
    command_script_resolved: str | None = None
    lowered = [arg.lower() for arg in args]
    if not args or not is_python_executable(args[0]):
        blockers.append("launcher_command_not_python")
    if len(args) < 2 or not is_run_demo_pipeline_script(args[1]):
        blockers.append("launcher_command_not_allowlisted")
    if len(args) >= 2:
        try:
            resolved_script = resolve_command_script(args[1])
            command_script_resolved = str(resolved_script)
            if is_run_demo_pipeline_script(args[1]) and resolved_script != RUN_DEMO_PIPELINE_SCRIPT:
                blockers.append("launcher_command_path_not_canonical")
        except (OSError, RuntimeError, ValueError):
            blockers.append("launcher_command_path_resolve_failed")
    if any(arg.endswith(FORBIDDEN_SCRIPT_SUFFIXES) for arg in lowered):
        blockers.append("launcher_command_forbidden_script_type")
    if any(any(tool_name in arg for tool_name in FORBIDDEN_TOOL_NAMES) for arg in lowered):
        blockers.append("launcher_command_forbidden_tool")
    return args, list(dict.fromkeys(blockers)), command_script_resolved


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
        f"- rerun_started_at: {report.get('rerun_started_at')}",
        f"- rerun_finished_at: {report.get('rerun_finished_at')}",
        f"- command_script_resolved: `{report.get('command_script_resolved') or 'N/A'}`",
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
        for key in (
            "doctor_path",
            "loaded",
            "sha256",
            "changed_from_initial_doctor",
            "mtime_epoch",
            "updated_after_rerun",
            "doctor_status",
            "primary_next_action",
            "try_now_allowed",
            "strict_status",
            "evidence_status",
        ):
            lines.append(f"- {key}: {follow_up.get(key)}")
        for label, key in (
            ("evidence_blocker", "evidence_blockers"),
            ("evidence_warning", "evidence_warnings"),
            ("blocking_reason", "blocking_reasons"),
            ("doctor_warning", "doctor_warnings"),
            ("warning", "warnings"),
        ):
            items = follow_up.get(key) if isinstance(follow_up.get(key), list) else []
            for item in items:
                lines.append(f"- {label}: {item}")
        lines.append("")
    return "\n".join(lines)


def summarize_follow_up_doctor(
    doctor_path: Path,
    *,
    initial_doctor_sha256: str | None,
    rerun_started_epoch: float | None,
) -> dict[str, Any]:
    follow_up: dict[str, Any] = {
        "doctor_path": str(doctor_path),
        "loaded": False,
        "sha256": None,
        "changed_from_initial_doctor": None,
        "mtime_epoch": None,
        "updated_after_rerun": None,
        "doctor_status": None,
        "primary_next_action": None,
        "try_now_allowed": None,
        "strict_status": None,
        "evidence_status": None,
        "evidence_blockers": [],
        "evidence_warnings": [],
        "blocking_reasons": [],
        "doctor_warnings": [],
        "warnings": [],
    }
    try:
        mtime_epoch = doctor_path.stat().st_mtime
    except FileNotFoundError:
        follow_up["warnings"].append("follow_up_doctor_missing")
        return follow_up
    except OSError as exc:
        follow_up["warnings"].append(f"follow_up_doctor_unreadable: {exc}")
        return follow_up
    follow_up["mtime_epoch"] = mtime_epoch
    if rerun_started_epoch is not None:
        updated_after_rerun = mtime_epoch >= rerun_started_epoch
        follow_up["updated_after_rerun"] = updated_after_rerun
        if not updated_after_rerun:
            follow_up["warnings"].append("follow_up_doctor_not_updated_after_rerun")
    try:
        follow_up_sha256 = file_sha256(doctor_path)
    except OSError as exc:
        follow_up["warnings"].append(f"follow_up_doctor_unreadable: {exc}")
        return follow_up
    follow_up["sha256"] = follow_up_sha256
    if initial_doctor_sha256:
        changed = follow_up_sha256 != initial_doctor_sha256
        follow_up["changed_from_initial_doctor"] = changed
        if not changed:
            follow_up["warnings"].append("follow_up_doctor_not_changed_after_rerun")
    try:
        doctor = load_json(doctor_path)
    except json.JSONDecodeError as exc:
        follow_up["warnings"].append(f"follow_up_doctor_invalid_json: {exc}")
        return follow_up
    except ValueError as exc:
        follow_up["warnings"].append(f"follow_up_doctor_not_object: {exc}")
        return follow_up
    except OSError as exc:
        follow_up["warnings"].append(f"follow_up_doctor_unreadable: {exc}")
        return follow_up
    evidence = doctor.get("evidence_check") if isinstance(doctor.get("evidence_check"), dict) else {}
    follow_up.update(
        {
            "loaded": True,
            "doctor_status": doctor.get("doctor_status"),
            "primary_next_action": doctor.get("primary_next_action"),
            "try_now_allowed": doctor.get("try_now_allowed"),
            "strict_status": evidence.get("strict_status") or evidence.get("status"),
            "evidence_status": evidence.get("status"),
            "evidence_blockers": as_string_list(evidence.get("blockers")),
            "evidence_warnings": as_string_list(evidence.get("warnings")),
            "blocking_reasons": as_string_list(doctor.get("blocking_reasons")),
            "doctor_warnings": as_string_list(doctor.get("warnings")),
        }
    )
    return follow_up


def follow_up_has_warning(follow_up: dict[str, Any]) -> bool:
    if not follow_up.get("loaded"):
        return True
    if follow_up.get("warnings"):
        return True
    if follow_up.get("strict_status") == "blocked" or follow_up.get("evidence_status") == "blocked":
        return True
    return bool(
        follow_up.get("evidence_blockers")
        or follow_up.get("evidence_warnings")
        or follow_up.get("blocking_reasons")
        or follow_up.get("doctor_warnings")
    )


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
    fail_on_followup_warning: bool = False,
    follow_up_doctor_path: Path | None = None,
    argv: list[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> tuple[int, dict[str, Any]]:
    started_monotonic = time.monotonic()
    started_at = now_iso()
    doctor = load_json(doctor_path)
    initial_doctor_sha256 = file_sha256(doctor_path)
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
    command_script_resolved: str | None = None
    if execute_rerun:
        command_args, command_blockers, command_script_resolved = validate_rerun_command(command)
        blockers.extend(command_blockers)
        blockers = list(dict.fromkeys(blockers))
    warnings: list[str] = []
    executed = False
    returncode: int | None = None
    rerun_started_at: str | None = None
    rerun_finished_at: str | None = None
    rerun_started_epoch: float | None = None
    rerun_finished_epoch: float | None = None
    launcher_status = "printed"

    if execute_rerun:
        if blockers:
            launcher_status = "blocked"
        else:
            rerun_started_at = now_iso()
            rerun_started_epoch = time.time()
            completed = runner(command_args, check=False)
            rerun_finished_epoch = time.time()
            rerun_finished_at = now_iso()
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
        follow_up = summarize_follow_up_doctor(
            follow_up_doctor_path,
            initial_doctor_sha256=initial_doctor_sha256,
            rerun_started_epoch=rerun_started_epoch,
        )
        if follow_up_has_warning(follow_up):
            launcher_status = "executed_with_followup_warning"
            if not follow_up.get("loaded"):
                warnings.append("follow_up_doctor_not_loaded")
            if follow_up.get("warnings"):
                warnings.extend(as_string_list(follow_up.get("warnings")))
            if follow_up.get("strict_status") == "blocked" or follow_up.get("evidence_status") == "blocked":
                warnings.append("follow_up_doctor_blocked")
            if follow_up.get("evidence_warnings"):
                warnings.append("follow_up_evidence_warning")
            if follow_up.get("blocking_reasons"):
                warnings.append("follow_up_blocking_reasons")
            if follow_up.get("doctor_warnings"):
                warnings.append("follow_up_doctor_warning")

    reason = str(action_contract.get("reason") or "")
    finished_at = now_iso()
    report = {
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": round((time.monotonic() - started_monotonic) * 1000, 3),
        "rerun_started_at": rerun_started_at,
        "rerun_finished_at": rerun_finished_at,
        "rerun_started_epoch": rerun_started_epoch,
        "rerun_finished_epoch": rerun_finished_epoch,
        "argv": argv or [],
        "cwd": str(Path.cwd()),
        "python_executable": sys.executable,
        "initial_doctor_sha256": initial_doctor_sha256,
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
        "command_script_resolved": command_script_resolved,
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
    history_dir = out_dir / "history"
    history_stem = f"launcher_report_{history_timestamp()}"
    history_json_path = history_dir / f"{history_stem}.json"
    history_md_path = history_dir / f"{history_stem}.md"
    report["output_json"] = str(json_path)
    report["output_md"] = str(md_path)
    report["output_history_json"] = str(history_json_path)
    report["output_history_md"] = str(history_md_path)
    write_json(json_path, report)
    write_json(history_json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    report_markdown = markdown_report(report)
    md_path.write_text(report_markdown, encoding="utf-8")
    history_md_path.parent.mkdir(parents=True, exist_ok=True)
    history_md_path.write_text(report_markdown, encoding="utf-8")

    if launcher_status == "blocked" or (executed and returncode not in (0, None)):
        exit_code = 2 if returncode in (0, None) else int(returncode)
    elif fail_on_followup_warning and follow_up is not None and follow_up_has_warning(follow_up):
        exit_code = 2
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
    parser.add_argument(
        "--fail-on-followup-warning",
        action="store_true",
        help="Return non-zero when follow-up doctor is missing, damaged, unchanged, blocked, or otherwise warning-worthy.",
    )
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
            fail_on_followup_warning=bool(args.fail_on_followup_warning),
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
    print(f"rerun_started_at: {report.get('rerun_started_at') or 'N/A'}")
    print(f"rerun_finished_at: {report.get('rerun_finished_at') or 'N/A'}")
    print(f"command_script_resolved: {report.get('command_script_resolved') or 'N/A'}")
    print(f"launcher_report_json: {report.get('output_json')}")
    print(f"launcher_report_md: {report.get('output_md')}")
    print(f"launcher_report_history_json: {report.get('output_history_json')}")
    print(f"launcher_report_history_md: {report.get('output_history_md')}")
    follow_up = report.get("follow_up") if isinstance(report.get("follow_up"), dict) else {}
    if follow_up:
        print(f"follow_up_loaded: {follow_up.get('loaded')}")
        print(f"follow_up_sha256: {follow_up.get('sha256')}")
        print(f"follow_up_changed_from_initial_doctor: {follow_up.get('changed_from_initial_doctor')}")
        print(f"follow_up_mtime_epoch: {follow_up.get('mtime_epoch')}")
        print(f"follow_up_updated_after_rerun: {follow_up.get('updated_after_rerun')}")
        print(f"follow_up_doctor_status: {follow_up.get('doctor_status')}")
        print(f"follow_up_primary_next_action: {follow_up.get('primary_next_action')}")
        print(f"follow_up_try_now_allowed: {follow_up.get('try_now_allowed')}")
        print(f"follow_up_strict_status: {follow_up.get('strict_status')}")
        print(f"follow_up_evidence_status: {follow_up.get('evidence_status')}")
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
