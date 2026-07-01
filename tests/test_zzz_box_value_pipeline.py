from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "run_zzz_box_value_pipeline.py"

spec = importlib.util.spec_from_file_location("run_zzz_box_value_pipeline", SCRIPT_PATH)
assert spec is not None
pipeline = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


class ZzzBoxValuePipelineTests(unittest.TestCase):
    def test_box_image_builds_roster_before_value_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meta = root / "meta.json"
            image = root / "box.png"
            output_dir = root / "value"
            meta.write_text("{}", encoding="utf-8")
            image.write_bytes(b"fake image placeholder")

            fake_box_tool = mock.Mock()
            fake_box_tool.extract_roster_from_image.return_value = {"summary": {"needs_review_count": 0}}
            fake_value_tool = mock.Mock()
            fake_value_tool.build_agent_value_report.return_value = {
                "output_json": str(output_dir / "value.json"),
                "output_markdown": str(output_dir / "value.md"),
                "summary": {"owned_count": 1, "unmapped_count": 0},
                "roster_quality": {"status": "ok", "needs_review_count": 0},
                "executive_summary": {"current_endgame_teams": {}},
            }
            output = io.StringIO()

            with (
                mock.patch.object(pipeline, "box_tool", fake_box_tool),
                mock.patch.object(pipeline, "value_tool", fake_value_tool),
                contextlib.redirect_stdout(output),
            ):
                code = pipeline.main(
                    [
                        "--box-image",
                        str(image),
                        "--meta-snapshot",
                        str(meta),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            roster_path = output_dir / "roster_from_box_image.json"
            fake_box_tool.extract_roster_from_image.assert_called_once()
            call = fake_box_tool.extract_roster_from_image.call_args.kwargs
            self.assertEqual(call["image_path"], image)
            self.assertEqual(call["output_json"], roster_path)
            self.assertEqual(call["meta_snapshot"], meta)
            fake_value_tool.build_agent_value_report.assert_called_once()
            self.assertEqual(fake_value_tool.build_agent_value_report.call_args.kwargs["roster_json"], roster_path)
            self.assertIn("roster_quality: ok", output.getvalue())
            self.assertIn("roster_needs_review_count: 0", output.getvalue())

    def test_existing_roster_json_bypasses_image_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meta = root / "meta.json"
            roster = root / "roster.json"
            output_dir = root / "value"
            meta.write_text("{}", encoding="utf-8")
            roster.write_text('{"agents": []}', encoding="utf-8")

            fake_box_tool = mock.Mock()
            fake_value_tool = mock.Mock()
            fake_value_tool.build_agent_value_report.return_value = {
                "output_json": str(output_dir / "value.json"),
                "output_markdown": str(output_dir / "value.md"),
                "summary": {"owned_count": 0, "unmapped_count": 0},
                "roster_quality": {"status": "needs_review", "needs_review_count": 1},
                "executive_summary": {"current_endgame_teams": {}},
            }
            output = io.StringIO()

            with (
                mock.patch.object(pipeline, "box_tool", fake_box_tool),
                mock.patch.object(pipeline, "value_tool", fake_value_tool),
                contextlib.redirect_stdout(output),
            ):
                code = pipeline.main(
                    [
                        "--roster-json",
                        str(roster),
                        "--meta-snapshot",
                        str(meta),
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(code, 0)
            fake_box_tool.extract_roster_from_image.assert_not_called()
            self.assertEqual(fake_value_tool.build_agent_value_report.call_args.kwargs["roster_json"], roster)
            self.assertIn("roster_quality: needs_review", output.getvalue())
            self.assertIn("roster_needs_review_count: 1", output.getvalue())

    def test_missing_roster_and_image_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meta = root / "meta.json"
            meta.write_text("{}", encoding="utf-8")

            with contextlib.redirect_stderr(io.StringIO()):
                code = pipeline.main(["--meta-snapshot", str(meta), "--output-dir", str(root / "value")])

            self.assertEqual(code, 2)

    def test_roster_json_and_box_image_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meta = root / "meta.json"
            roster = root / "roster.json"
            image = root / "box.png"
            meta.write_text("{}", encoding="utf-8")
            roster.write_text('{"agents": []}', encoding="utf-8")
            image.write_bytes(b"fake image placeholder")

            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                pipeline.main(
                    [
                        "--roster-json",
                        str(roster),
                        "--box-image",
                        str(image),
                        "--meta-snapshot",
                        str(meta),
                        "--output-dir",
                        str(root / "value"),
                    ]
                )

            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
