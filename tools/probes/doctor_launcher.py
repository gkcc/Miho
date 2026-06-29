from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Callable


SCHEMA_VERSION = "p3.0-lite-doctor-launcher"


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
    return "\n".join(lines)


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
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> tuple[int, dict[str, Any]]:
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
    warnings: list[str] = []
    executed = False
    returncode: int | None = None
    launcher_status = "printed"

    if execute_rerun:
        if blockers:
            launcher_status = "blocked"
        else:
            completed = runner(split_command(str(command)), check=False)
            executed = True
            returncode = int(getattr(completed, "returncode", 0))
            launcher_status = "executed"
            if returncode != 0:
                blockers.append("rerun_command_failed")
    elif not allowed:
        warnings.append("manual_only_action_printed")

    reason = str(action_contract.get("reason") or "")
    report = {
        "schema_version": SCHEMA_VERSION,
        "launcher_status": launcher_status,
        "doctor_status": doctor.get("doctor_status"),
        "headline": doctor.get("headline"),
        "primary_next_action": primary_next_action,
        "strict_status": strict_status,
        "allowed_for_launcher": allowed,
        "executed": executed,
        "returncode": returncode,
        "command": command,
        "reason": reason,
        "action_contract": action_contract,
        "warnings": warnings,
        "blockers": blockers,
    }
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
    parser.add_argument("--print-command", action="store_true", help="Explicitly print/report the command without executing it.")
    parser.add_argument("--execute-rerun", action="store_true", help="Execute only an allowed rerun_demo_pipeline action.")
    return parser


def run_launcher(argv: list[str] | None = None, *, runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run) -> int:
    args = build_arg_parser().parse_args(argv)
    doctor_path = Path(args.doctor)
    output_dir = Path(args.output_dir) if args.output_dir else None
    try:
        exit_code, report = launch_doctor(
            doctor_path=doctor_path,
            output_dir=output_dir,
            execute_rerun=bool(args.execute_rerun),
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
