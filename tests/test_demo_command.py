from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMAND_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_demo_command.py"

command_spec = importlib.util.spec_from_file_location("build_demo_command", COMMAND_SCRIPT_PATH)
assert command_spec is not None
command_tool = importlib.util.module_from_spec(command_spec)
assert command_spec.loader is not None
sys.modules[command_spec.name] = command_tool
command_spec.loader.exec_module(command_tool)


class DemoCommandTests(unittest.TestCase):
    def test_parsed_dir_command_records_latest_clean_and_local_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            expected_dir = root / "expected"
            roster_dir = root / "roster"
            tier_snapshot = root / "tier.json"
            parsed_dir.mkdir()
            expected_dir.mkdir()
            roster_dir.mkdir()
            tier_snapshot.write_text("{}", encoding="utf-8")

            result = command_tool.build_demo_command(
                output_dir=root / "demo",
                parsed_dir=parsed_dir,
                expected_dir=expected_dir,
                latest_only=True,
                clean_demo=True,
                roster_dir=roster_dir,
                tier_snapshot=tier_snapshot,
            )

            command = result["command"]
            self.assertEqual(result["schema_version"], "p2.8-lite-demo-command")
            self.assertEqual(result["source_mode"], "parsed_dir")
            self.assertTrue(result["safe_to_rerun"])
            self.assertIn("--parsed-dir", result["argv"])
            self.assertIn(str(parsed_dir), result["argv"])
            self.assertIn("--latest-only", result["argv"])
            self.assertIn("--clean-demo", result["argv"])
            self.assertIn("--roster-dir", result["argv"])
            self.assertIn("--tier-snapshot", result["argv"])
            self.assertIn("--parsed-dir", command)
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())

    def test_manifest_command_records_manifest_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "manifest.json"
            expected_dir = root / "expected"
            roster_dir = root / "roster"
            manifest.write_text('{"cases": []}', encoding="utf-8")
            expected_dir.mkdir()
            roster_dir.mkdir()

            result = command_tool.build_demo_command(
                output_dir=root / "demo",
                manifest=manifest,
                expected_dir=expected_dir,
                roster_dir=roster_dir,
            )

            self.assertEqual(result["source_mode"], "manifest")
            self.assertTrue(result["safe_to_rerun"])
            self.assertIn("--manifest", result["argv"])
            self.assertIn(str(manifest), result["argv"])

    def test_missing_source_marks_command_not_safe_to_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected_dir = root / "expected"
            roster_dir = root / "roster"
            expected_dir.mkdir()
            roster_dir.mkdir()

            result = command_tool.build_demo_command(
                output_dir=root / "demo",
                manifest=root / "missing_manifest.json",
                expected_dir=expected_dir,
                roster_dir=roster_dir,
            )

            self.assertFalse(result["safe_to_rerun"])
            self.assertIn("--manifest", result["missing_inputs"])
            self.assertIn("missing_replay_inputs", result["warnings"])


if __name__ == "__main__":
    unittest.main()
