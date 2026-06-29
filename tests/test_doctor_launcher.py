from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
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
        "evidence_check": {"status": "trusted" if strict_status != "blocked" else "blocked", "strict_status": strict_status},
        "action_contract": {
            "primary_next_action": primary_next_action,
            "is_read_only": not writes_roster,
            "writes_roster": writes_roster,
            "requires_manual_confirmation": requires_manual_confirmation,
            "allowed_for_launcher": allowed_for_launcher,
            "reason": reason,
        },
        "commands": commands,
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
        self.assertEqual(exit_code, 0)
        self.assertEqual(json_path.name, "launcher_report.json")
        self.assertEqual(md_path.name, "launcher_report.md")


if __name__ == "__main__":
    unittest.main()
