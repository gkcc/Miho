from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPDATE_COMMAND_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_update_command.py"

update_spec = importlib.util.spec_from_file_location("build_update_command", UPDATE_COMMAND_SCRIPT_PATH)
assert update_spec is not None
update_tool = importlib.util.module_from_spec(update_spec)
assert update_spec.loader is not None
sys.modules[update_spec.name] = update_tool
update_spec.loader.exec_module(update_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def doctor_json(
    *,
    primary_next_action: str = "rerun_demo_pipeline",
    allowed_for_launcher: bool = True,
    writes_roster: bool = False,
    requires_manual_confirmation: bool = False,
    strict_status: str = "trusted",
) -> dict:
    return {
        "schema_version": "p2.9-lite-demo-doctor",
        "primary_next_action": primary_next_action,
        "action_contract": {
            "primary_next_action": primary_next_action,
            "allowed_for_launcher": allowed_for_launcher,
            "writes_roster": writes_roster,
            "requires_manual_confirmation": requires_manual_confirmation,
        },
        "evidence_check": {"strict_status": strict_status},
    }


def demo_command_json(*, safe_to_rerun: bool = True) -> dict:
    return {
        "schema_version": "p2.8-lite-demo-command",
        "safe_to_rerun": safe_to_rerun,
        "command": "python tools/probes/run_demo_pipeline.py --manifest data/probes/demo_manifest.json",
    }


class UpdateCommandTests(unittest.TestCase):
    def build_case(self, root: Path, doctor: dict, command: dict) -> dict:
        output_dir = root / "demo"
        doctor_path = write_json(output_dir / "demo_doctor" / "demo_doctor.json", doctor)
        command_path = write_json(output_dir / "demo_command.json", command)
        return update_tool.build_update_command(
            output_dir=output_dir,
            demo_doctor=doctor_path,
            demo_command=command_path,
        )

    def test_ready_update_command_uses_safe_launcher_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_case(root, doctor_json(), demo_command_json())

            self.assertEqual(result["status"], "ready")
            self.assertIn("--execute-rerun", result["argv"])
            self.assertIn("--follow-up-doctor", result["argv"])
            self.assertIn("--refresh-dashboard", result["argv"])
            self.assertIn("--dashboard-summary", result["argv"])
            self.assertIn("--dashboard-html", result["argv"])
            self.assertIn("--max-history", result["argv"])
            self.assertIn("tools/probes/doctor_launcher.py", result["command"])
            self.assertIn("tools/probes/run_demo_pipeline.py", demo_command_json()["command"])
            self.assertNotIn("safe_apply_review_decisions.py", result["command"])
            self.assertNotIn("try_now", result["command"])
            self.assertNotIn("token", result["command"].lower())
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())

    def test_blocked_states_do_not_emit_runnable_command(self) -> None:
        cases = [
            ("safe_apply_review_decisions", doctor_json(primary_next_action="safe_apply_review_decisions"), demo_command_json()),
            ("try_now", doctor_json(primary_next_action="try_now"), demo_command_json()),
            ("writes_roster", doctor_json(writes_roster=True), demo_command_json()),
            ("manual_confirmation", doctor_json(requires_manual_confirmation=True), demo_command_json()),
            ("strict_blocked", doctor_json(strict_status="blocked"), demo_command_json()),
            ("unsafe_demo_command", doctor_json(), demo_command_json(safe_to_rerun=False)),
        ]
        for name, doctor, command in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    result = self.build_case(Path(temp_dir), doctor, command)

                    self.assertEqual(result["status"], "blocked")
                    self.assertIsNone(result["command"])
                    self.assertEqual(result["argv"], [])
                    self.assertGreater(len(result["blockers"]), 0)

    def test_invalid_max_history_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "demo"
            doctor_path = write_json(output_dir / "demo_doctor" / "demo_doctor.json", doctor_json())
            command_path = write_json(output_dir / "demo_command.json", demo_command_json())

            result = update_tool.build_update_command(
                output_dir=output_dir,
                demo_doctor=doctor_path,
                demo_command=command_path,
                max_history=0,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("max_history_must_be_positive", result["blockers"])


if __name__ == "__main__":
    unittest.main()
