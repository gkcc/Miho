from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "doctor_launcher.py"

launcher_spec = importlib.util.spec_from_file_location("doctor_launcher", LAUNCHER_SCRIPT_PATH)
assert launcher_spec is not None
launcher_tool = importlib.util.module_from_spec(launcher_spec)
assert launcher_spec.loader is not None
sys.modules[launcher_spec.name] = launcher_tool
launcher_spec.loader.exec_module(launcher_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def doctor_json(
    *,
    primary_next_action: str = "rerun_demo_pipeline",
    doctor_status: str = "needs_rerun",
    strict_status: str = "trusted",
    allowed_for_launcher: bool = True,
    writes_roster: bool = False,
    requires_manual_confirmation: bool = False,
    try_now_allowed: bool = False,
    evidence_blockers: list[str] | None = None,
    evidence_warnings: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
    doctor_warnings: list[str] | None = None,
    reason: str = "demo rerun command is safe to print",
    command: str = "python tools/probes/run_demo_pipeline.py --manifest data/probes/demo_manifest.json",
) -> dict:
    commands = {
        "rerun_demo": command,
        "preview": "python tools/probes/preview_review_decisions.py --decision-manifest decisions.json",
        "safe_apply": "python tools/probes/apply_review_decisions.py --require-preview-ready",
    }
    return {
        "schema_version": "p2.9-lite-demo-doctor",
        "doctor_status": doctor_status,
        "headline": "demo",
        "primary_next_action": primary_next_action,
        "try_now_allowed": try_now_allowed,
        "evidence_check": {
            "status": "trusted" if strict_status != "blocked" else "blocked",
            "strict_status": strict_status,
            "blockers": evidence_blockers or [],
            "warnings": evidence_warnings or [],
        },
        "action_contract": {
            "primary_next_action": primary_next_action,
            "is_read_only": not writes_roster,
            "writes_roster": writes_roster,
            "requires_manual_confirmation": requires_manual_confirmation,
            "allowed_for_launcher": allowed_for_launcher,
            "reason": reason,
        },
        "commands": commands,
        "blocking_reasons": blocking_reasons or [],
        "warnings": doctor_warnings or [],
    }


def demo_summary_json() -> dict:
    return {
        "overall": {
            "case_count": 0,
            "parse_success_count": 0,
            "review_status_counts": {},
            "parse_status_counts": {},
            "expected_status_counts": {},
            "normalized_status_counts": {},
            "import_status_counts": {},
            "demo_status": "READY",
            "average_pass_rate": None,
            "normalized_count": 0,
            "requires_manual_review_count": 0,
            "conclusion": "demo",
        },
        "input": {"source_mode": "manifest controlled mode"},
        "cases": [],
    }


def write_history_file(path: Path, *, mtime: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def history_stems(history_dir: Path) -> set[str]:
    return {path.stem for path in history_dir.glob("launcher_report_*.json")} | {
        path.stem for path in history_dir.glob("launcher_report_*.md")
    }


class DoctorLauncherTests(unittest.TestCase):
    def test_default_rerun_only_prints_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, runner=runner)
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, [])
        self.assertEqual(report["launcher_status"], "printed")
        self.assertFalse(report["executed"])
        self.assertTrue(report["allowed_for_launcher"])
        self.assertIn("run_demo_pipeline.py", report["command"])

    def test_execute_rerun_runs_only_allowed_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, execute_rerun=True, runner=runner)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "executed")
        self.assertTrue(report["executed"])
        self.assertEqual(len(calls), 1)
        self.assertTrue(any("run_demo_pipeline.py" in item for item in calls[0]))
        self.assertTrue(any("run_demo_pipeline.py" in item for item in report["command_args"]))
        self.assertEqual(report["command_script_resolved"], str(launcher_tool.RUN_DEMO_PIPELINE_SCRIPT))
        self.assertIsNotNone(report["rerun_started_at"])
        self.assertIsNotNone(report["rerun_finished_at"])

    def test_execute_rerun_reads_follow_up_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            follow_up_path = write_json(
                root / "after" / "demo_doctor.json",
                doctor_json(
                    primary_next_action="try_now",
                    doctor_status="ready_to_try",
                    allowed_for_launcher=False,
                    try_now_allowed=True,
                    reason="try_now is a user gameplay action, not a tool command",
                ),
            )
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                fresh_epoch = time.time() + 1
                os.utime(follow_up_path, (fresh_epoch, fresh_epoch))
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=follow_up_path,
                execute_rerun=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "executed")
        self.assertEqual(len(calls), 1)
        self.assertTrue(report["follow_up"]["loaded"])
        self.assertEqual(report["follow_up"]["doctor_status"], "ready_to_try")
        self.assertEqual(report["follow_up"]["primary_next_action"], "try_now")
        self.assertTrue(report["follow_up"]["try_now_allowed"])
        self.assertEqual(report["follow_up"]["strict_status"], "trusted")
        self.assertEqual(report["follow_up"]["evidence_status"], "trusted")
        self.assertIsNotNone(report["follow_up"]["sha256"])
        self.assertTrue(report["follow_up"]["changed_from_initial_doctor"])
        self.assertIsNotNone(report["follow_up"]["mtime_epoch"])
        self.assertTrue(report["follow_up"]["updated_after_rerun"])

    def test_execute_rerun_reports_follow_up_needs_apply_without_executing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            follow_up_path = write_json(
                root / "after" / "demo_doctor.json",
                doctor_json(
                    primary_next_action="safe_apply_review_decisions",
                    doctor_status="needs_apply",
                    allowed_for_launcher=False,
                    writes_roster=True,
                    requires_manual_confirmation=True,
                    reason="write action must be manually confirmed",
                ),
            )
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                fresh_epoch = time.time() + 1
                os.utime(follow_up_path, (fresh_epoch, fresh_epoch))
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=follow_up_path,
                execute_rerun=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["follow_up"]["doctor_status"], "needs_apply")
        self.assertEqual(report["follow_up"]["primary_next_action"], "safe_apply_review_decisions")
        self.assertFalse(report["follow_up"]["try_now_allowed"])

    def test_follow_up_same_hash_is_reported_as_not_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())

            def runner(args, **kwargs):
                fresh_epoch = time.time() + 1
                os.utime(doctor_path, (fresh_epoch, fresh_epoch))
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=doctor_path,
                execute_rerun=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "executed_with_followup_warning")
        self.assertFalse(report["follow_up"]["changed_from_initial_doctor"])
        self.assertIn("follow_up_doctor_not_changed_after_rerun", report["follow_up"]["warnings"])
        self.assertIn("follow_up_doctor_not_changed_after_rerun", report["warnings"])

    def test_follow_up_blocked_evidence_is_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            follow_up_path = write_json(
                root / "after" / "demo_doctor.json",
                doctor_json(
                    strict_status="blocked",
                    evidence_blockers=["review_preview_run_manifest_sha256_mismatch"],
                    blocking_reasons=["ready_try_now_not_actionable_under_current_doctor_status"],
                    doctor_warnings=["demo_command_not_safe_to_rerun"],
                ),
            )

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=follow_up_path,
                execute_rerun=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "executed_with_followup_warning")
        self.assertEqual(report["follow_up"]["evidence_status"], "blocked")
        self.assertEqual(report["follow_up"]["strict_status"], "blocked")
        self.assertIn("review_preview_run_manifest_sha256_mismatch", report["follow_up"]["evidence_blockers"])
        self.assertIn(
            "ready_try_now_not_actionable_under_current_doctor_status",
            report["follow_up"]["blocking_reasons"],
        )
        self.assertIn("demo_command_not_safe_to_rerun", report["follow_up"]["doctor_warnings"])

    def test_follow_up_stale_mtime_is_reported_as_not_updated_after_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            follow_up_path = write_json(
                root / "after" / "demo_doctor.json",
                doctor_json(primary_next_action="try_now", doctor_status="ready_to_try", allowed_for_launcher=False),
            )
            stale_epoch = time.time() - 3600
            os.utime(follow_up_path, (stale_epoch, stale_epoch))

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=follow_up_path,
                execute_rerun=True,
                fail_on_followup_warning=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["launcher_status"], "executed_with_followup_warning")
        self.assertFalse(report["follow_up"]["updated_after_rerun"])
        self.assertIn("follow_up_doctor_not_updated_after_rerun", report["follow_up"]["warnings"])
        self.assertIn("follow_up_doctor_not_updated_after_rerun", report["warnings"])

    def test_execute_rerun_failure_does_not_read_follow_up_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            follow_up_path = write_json(root / "after" / "demo_doctor.json", doctor_json())

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 7)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=follow_up_path,
                execute_rerun=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 7)
        self.assertNotIn("follow_up", report)
        self.assertIn("rerun_command_failed", report["blockers"])

    def test_missing_follow_up_doctor_is_warning_not_failed_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            missing_follow_up_path = root / "missing" / "demo_doctor.json"

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=missing_follow_up_path,
                execute_rerun=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "executed_with_followup_warning")
        self.assertFalse(report["follow_up"]["loaded"])
        self.assertIn("follow_up_doctor_not_loaded", report["warnings"])
        self.assertIn("follow_up_doctor_missing", report["warnings"])
        self.assertIn("follow_up_doctor_missing", report["follow_up"]["warnings"])

    def test_fail_on_followup_warning_returns_nonzero_for_missing_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            missing_follow_up_path = root / "missing" / "demo_doctor.json"

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=missing_follow_up_path,
                execute_rerun=True,
                fail_on_followup_warning=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["launcher_status"], "executed_with_followup_warning")

    def test_fail_on_followup_warning_returns_nonzero_for_damaged_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            damaged_follow_up_path = root / "after" / "demo_doctor.json"
            damaged_follow_up_path.parent.mkdir(parents=True, exist_ok=True)
            damaged_follow_up_path.write_text("{", encoding="utf-8")

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=damaged_follow_up_path,
                execute_rerun=True,
                fail_on_followup_warning=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["launcher_status"], "executed_with_followup_warning")
        self.assertFalse(report["follow_up"]["loaded"])
        self.assertIsNotNone(report["follow_up"]["sha256"])
        self.assertTrue(any("follow_up_doctor_invalid_json" in item for item in report["follow_up"]["warnings"]))

    def test_execute_rerun_blocks_suffix_match_outside_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_script = root / "outside" / "tools" / "probes" / "run_demo_pipeline.py"
            fake_script.parent.mkdir(parents=True, exist_ok=True)
            fake_script.write_text("print('not the project script')", encoding="utf-8")
            doctor_path = write_json(
                root / "demo_doctor" / "demo_doctor.json",
                doctor_json(command=f"python {fake_script} --manifest data/probes/demo_manifest.json"),
            )
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, execute_rerun=True, runner=runner)
        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, [])
        self.assertIn("launcher_command_path_not_canonical", report["blockers"])
        self.assertEqual(report["command_script_resolved"], str(fake_script.resolve()))

    def test_fail_on_followup_warning_returns_nonzero_for_unchanged_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                follow_up_doctor_path=doctor_path,
                execute_rerun=True,
                fail_on_followup_warning=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 2)
        self.assertIn("follow_up_doctor_not_changed_after_rerun", report["follow_up"]["warnings"])

    def test_execute_rerun_blocks_non_allowlisted_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(
                root / "demo_doctor" / "demo_doctor.json",
                doctor_json(command="python tools/probes/apply_review_decisions.py --require-preview-ready"),
            )
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, execute_rerun=True, runner=runner)
        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, [])
        self.assertIn("launcher_command_not_allowlisted", report["blockers"])
        self.assertIn("launcher_command_forbidden_tool", report["blockers"])

    def test_execute_rerun_blocks_shell_and_script_commands(self) -> None:
        blocked_commands = [
            "powershell scripts/run.ps1",
            "cmd /c tools/probes/run_demo_pipeline.py",
            "bash scripts/run.sh",
            "python tools/probes/run_demo_pipeline.py --manifest x && echo unsafe",
            "scripts/run_demo.bat",
        ]
        for command in blocked_commands:
            with self.subTest(command=command):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json(command=command))
                    calls: list[list[str]] = []

                    def runner(args, **kwargs):
                        calls.append(args)
                        return subprocess.CompletedProcess(args, 0)

                    exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, execute_rerun=True, runner=runner)
                self.assertEqual(exit_code, 2)
                self.assertEqual(calls, [])
                self.assertTrue(
                    {
                        "launcher_command_not_python",
                        "launcher_command_not_allowlisted",
                        "launcher_command_contains_shell_control",
                        "launcher_command_forbidden_script_type",
                    }.intersection(report["blockers"])
                )

    def test_safe_apply_is_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(
                root / "demo_doctor" / "demo_doctor.json",
                doctor_json(
                    primary_next_action="safe_apply_review_decisions",
                    doctor_status="needs_apply",
                    allowed_for_launcher=False,
                    writes_roster=True,
                    requires_manual_confirmation=True,
                    reason="write action must be manually confirmed",
                ),
            )
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, execute_rerun=True, runner=runner)
        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(report["launcher_status"], "blocked")
        self.assertIn("launcher_never_executes_safe_apply", report["blockers"])
        self.assertIn("launcher_disallows_writes_roster", report["blockers"])

    def test_try_now_is_manual_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(
                root / "demo_doctor" / "demo_doctor.json",
                doctor_json(
                    primary_next_action="try_now",
                    doctor_status="ready_to_try",
                    allowed_for_launcher=False,
                    reason="try_now is a user gameplay action, not a tool command",
                ),
            )
            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "printed")
        self.assertFalse(report["executed"])
        self.assertIn("manual_only_action_printed", report["warnings"])
        self.assertEqual(report["command"], None)

    def test_blocked_evidence_never_executes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json(strict_status="blocked"))
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, execute_rerun=True, runner=runner)
        self.assertEqual(exit_code, 2)
        self.assertEqual(calls, [])
        self.assertIn("evidence_strict_status_blocked", report["blockers"])

    def test_blocked_evidence_default_print_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json(strict_status="blocked"))
            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["launcher_status"], "printed")
        self.assertIn("evidence_strict_status_blocked", report["blockers"])

    def test_fail_on_blocked_returns_nonzero_for_print_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json(strict_status="blocked"))
            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, fail_on_blocked=True)
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["launcher_status"], "blocked")
        self.assertIn("evidence_strict_status_blocked", report["blockers"])

    def test_print_and_execute_modes_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            with self.assertRaises(SystemExit) as raised:
                launcher_tool.run_launcher(["--doctor", str(doctor_path), "--print-command", "--execute-rerun"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_malformed_doctor_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bad_path = root / "bad.json"
            bad_path.write_text("{", encoding="utf-8")
            exit_code = launcher_tool.run_launcher(["--doctor", str(bad_path)])
        self.assertNotEqual(exit_code, 0)

    def test_report_paths_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "launcher"
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, output_dir=output_dir)
            json_path = Path(report["output_json"])
            md_path = Path(report["output_md"])
            history_json_path = Path(report["output_history_json"])
            history_md_path = Path(report["output_history_md"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json_path.name, "launcher_report.json")
            self.assertEqual(md_path.name, "launcher_report.md")
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(history_json_path.exists())
            self.assertTrue(history_md_path.exists())
            self.assertEqual(history_json_path.parent.name, "history")
            self.assertNotIn(":", history_json_path.name)
            self.assertNotIn(":", history_md_path.name)
            self.assertIn("argv", report)
            self.assertIn("cwd", report)
            self.assertIn("python_executable", report)
            self.assertIn("started_at", report)
            self.assertIn("finished_at", report)
            self.assertIn("duration_ms", report)

    def test_max_history_retains_newest_groups_and_current_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "launcher"
            history_dir = output_dir / "history"
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            old_pair = "launcher_report_20000101_000000_000000+0000"
            newest_pair = "launcher_report_20000102_000000_000000+0000"
            orphan_json = "launcher_report_20000103_000000_000000+0000"
            orphan_md = "launcher_report_20000104_000000_000000+0000"
            write_history_file(history_dir / f"{old_pair}.json", mtime=100)
            write_history_file(history_dir / f"{old_pair}.md", mtime=100)
            write_history_file(history_dir / f"{newest_pair}.json", mtime=200)
            write_history_file(history_dir / f"{newest_pair}.md", mtime=200)
            write_history_file(history_dir / f"{orphan_json}.json", mtime=50)
            write_history_file(history_dir / f"{orphan_md}.md", mtime=60)
            unrelated = write_history_file(history_dir / "keep_me.txt", mtime=10)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                output_dir=output_dir,
                max_history=2,
            )

            current_stem = Path(report["output_history_json"]).stem
            stems = history_stems(history_dir)
            latest_report = json.loads(Path(report["output_json"]).read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertIn(current_stem, stems)
            self.assertEqual(len(stems), 2)
            self.assertNotIn(old_pair, stems)
            self.assertNotIn(orphan_json, stems)
            self.assertNotIn(orphan_md, stems)
            self.assertTrue(unrelated.exists())
            self.assertTrue(report["history_retention"]["attempted"])
            self.assertEqual(report["history_retention"]["max_history"], 2)
            self.assertEqual(report["history_retention"]["kept_count"], 2)
            self.assertGreaterEqual(len(report["history_retention"]["deleted_files"]), 4)
            self.assertTrue(latest_report["history_retention"]["attempted"])

    def test_history_retention_is_skipped_without_max_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "launcher"
            history_dir = output_dir / "history"
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            old_stem = "launcher_report_20000101_000000_000000+0000"
            old_json = write_history_file(history_dir / f"{old_stem}.json", mtime=100)
            old_md = write_history_file(history_dir / f"{old_stem}.md", mtime=100)

            exit_code, report = launcher_tool.launch_doctor(doctor_path=doctor_path, output_dir=output_dir)

            self.assertEqual(exit_code, 0)
            self.assertFalse(report["history_retention"]["attempted"])
            self.assertTrue(old_json.exists())
            self.assertTrue(old_md.exists())

    def test_refresh_dashboard_updates_summary_and_html_without_rerunning_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            summary_path = write_json(root / "demo_summary.json", demo_summary_json())
            output_dir = root / "launcher"
            demo_pipeline = launcher_tool.import_demo_pipeline_module()
            original_run_pipeline = demo_pipeline.run_pipeline

            def fail_run_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("refresh-dashboard must not rerun the demo pipeline")

            demo_pipeline.run_pipeline = fail_run_pipeline
            try:
                exit_code, report = launcher_tool.launch_doctor(
                    doctor_path=doctor_path,
                    output_dir=output_dir,
                    refresh_dashboard=True,
                )
            finally:
                demo_pipeline.run_pipeline = original_run_pipeline

            dashboard_path = root / "index.html"
            refreshed_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            dashboard_html = dashboard_path.read_text(encoding="utf-8")
            launcher_report_json = json.loads(Path(report["output_json"]).read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(report["dashboard_refresh"]["status"], "refreshed")
            self.assertTrue(report["dashboard_refresh"]["inferred_dashboard_paths"])
            self.assertTrue(report["dashboard_refresh"]["summary_updated"])
            self.assertTrue(report["dashboard_refresh"]["dashboard_rendered"])
            self.assertTrue(launcher_report_json["dashboard_refresh"]["dashboard_rendered"])
            self.assertTrue(dashboard_path.exists())
            self.assertIn("launcher_report", refreshed_summary)
            self.assertEqual(refreshed_summary["launcher_report"]["launcher_status"], "printed")
            self.assertEqual(refreshed_summary["launcher_report"]["dashboard_refresh"]["status"], "refreshed")
            self.assertTrue(refreshed_summary["launcher_report"]["dashboard_refresh"]["summary_updated"])
            self.assertTrue(refreshed_summary["launcher_report"]["dashboard_refresh"]["dashboard_rendered"])
            self.assertIn("启动器执行记录", dashboard_html)
            self.assertIn("dashboard_rendered", dashboard_html)
            self.assertIn("refreshed", dashboard_html)

    def test_refresh_dashboard_uses_explicit_summary_and_html_with_custom_launcher_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            dashboard_dir = root / "dashboard"
            summary_path = write_json(dashboard_dir / "demo_summary.json", demo_summary_json())
            html_path = dashboard_dir / "custom_dashboard.html"

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                output_dir=root / "custom_launcher_reports",
                refresh_dashboard=True,
                dashboard_summary_path=summary_path,
                dashboard_html_path=html_path,
            )

            refreshed_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(report["dashboard_refresh"]["status"], "refreshed")
            self.assertFalse(report["dashboard_refresh"]["inferred_dashboard_paths"])
            self.assertEqual(Path(report["dashboard_refresh"]["summary_json"]), summary_path)
            self.assertEqual(Path(report["dashboard_refresh"]["dashboard_html"]), html_path)
            self.assertNotIn("dashboard_refresh_path_inferred_from_custom_launcher_output", report["dashboard_refresh"]["warnings"])
            self.assertTrue(html_path.exists())
            self.assertIn("launcher_report", refreshed_summary)

    def test_refresh_dashboard_warns_when_custom_output_dir_uses_inferred_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            summary_path = write_json(root / "demo_summary.json", demo_summary_json())

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                output_dir=root / "custom_launcher_reports",
                refresh_dashboard=True,
            )

            refreshed_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["dashboard_refresh"]["status"], "refreshed")
        self.assertTrue(report["dashboard_refresh"]["inferred_dashboard_paths"])
        self.assertIn("dashboard_refresh_path_inferred_from_custom_launcher_output", report["dashboard_refresh"]["warnings"])
        self.assertIn("dashboard_refresh_path_inferred_from_custom_launcher_output", report["warnings"])
        self.assertIn("launcher_report", refreshed_summary)

    def test_refresh_dashboard_warns_when_custom_output_dir_is_named_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            write_json(root / "other" / "demo_summary.json", demo_summary_json())

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                output_dir=root / "other" / "launcher",
                refresh_dashboard=True,
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["dashboard_refresh"]["inferred_dashboard_paths"])
        self.assertIn("dashboard_refresh_path_inferred_from_custom_launcher_output", report["dashboard_refresh"]["warnings"])

    def test_refresh_dashboard_render_failure_records_partial_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            write_json(root / "demo_summary.json", demo_summary_json())
            output_dir = root / "launcher"
            dashboard_path = root / "index.html"
            demo_pipeline = launcher_tool.import_demo_pipeline_module()
            original_render_dashboard = demo_pipeline.dashboard.render_dashboard

            def fail_render_dashboard(*args, **kwargs):  # noqa: ANN002, ANN003
                raise RuntimeError("render failed for test")

            demo_pipeline.dashboard.render_dashboard = fail_render_dashboard
            try:
                exit_code, report = launcher_tool.launch_doctor(
                    doctor_path=doctor_path,
                    output_dir=output_dir,
                    refresh_dashboard=True,
                )
            finally:
                demo_pipeline.dashboard.render_dashboard = original_render_dashboard
            dashboard_exists = dashboard_path.exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["dashboard_refresh"]["status"], "failed")
        self.assertTrue(report["dashboard_refresh"]["summary_updated"])
        self.assertFalse(report["dashboard_refresh"]["dashboard_rendered"])
        self.assertFalse(dashboard_exists)
        self.assertTrue(any("dashboard_refresh_failed" in item for item in report["dashboard_refresh"]["warnings"]))
        self.assertTrue(any("dashboard_refresh_failed" in item for item in report["warnings"]))

    def test_refresh_dashboard_missing_summary_warns_without_failing_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            doctor_path = write_json(root / "demo_doctor" / "demo_doctor.json", doctor_json())
            calls: list[list[str]] = []

            def runner(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0)

            exit_code, report = launcher_tool.launch_doctor(
                doctor_path=doctor_path,
                output_dir=root / "launcher",
                execute_rerun=True,
                refresh_dashboard=True,
                runner=runner,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["launcher_status"], "executed")
        self.assertEqual(report["dashboard_refresh"]["status"], "warning")
        self.assertIn("dashboard_refresh_summary_missing", report["dashboard_refresh"]["warnings"])
        self.assertIn("dashboard_refresh_summary_missing", report["warnings"])


if __name__ == "__main__":
    unittest.main()
