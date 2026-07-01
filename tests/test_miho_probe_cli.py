from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

spec = importlib.util.spec_from_file_location("miho_probe_cli", SCRIPT_PATH)
assert spec is not None
cli = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = cli
spec.loader.exec_module(cli)


class MihoProbeCliTests(unittest.TestCase):
    def test_help_is_box_tier_first(self) -> None:
        text = cli.render_help()

        self.assertIn("ZZZ box / tier", text)
        self.assertIn("box-roster", text)
        self.assertIn("box-value", text)
        self.assertIn("未来观察", text)

    def test_box_value_delegates_to_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster = root / "roster.json"
            meta = root / "meta.json"
            roster.write_text('{"agents":[]}', encoding="utf-8")
            meta.write_text("{}", encoding="utf-8")
            fake_pipeline = mock.Mock()
            fake_pipeline.main.return_value = 0

            with mock.patch.object(cli, "load_module", return_value=fake_pipeline):
                result = cli.run_box_value(
                    argparse.Namespace(
                        roster_json=str(roster),
                        box_image=None,
                        roster_output=None,
                        meta_snapshot=str(meta),
                        output_dir=str(root / "value"),
                        refresh_meta=False,
                        current_only=False,
                        max_phases=None,
                        timeout=30,
                        request_delay=0.15,
                    )
                )

            self.assertEqual(result, 0)
            argv = fake_pipeline.main.call_args.args[0]
            self.assertIn("--roster-json", argv)
            self.assertIn(str(roster.resolve()), argv)
            self.assertIn("--meta-snapshot", argv)
            self.assertIn(str(meta.resolve()), argv)

    def test_status_prints_next_box_value_when_roster_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meta = root / "meta.json"
            box_dir = root / "box"
            image_dir = root / "images"
            box_dir.mkdir()
            image_dir.mkdir()
            meta.write_text("{}", encoding="utf-8")
            roster = box_dir / "roster.json"
            roster.write_text('{"agents":[]}', encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                result = cli.run_status(
                    argparse.Namespace(
                        meta_snapshot=str(meta),
                        box_dir=str(box_dir),
                        image_dir=str(image_dir),
                    )
                )

            self.assertEqual(result, 0)
            text = output.getvalue()
            self.assertIn("latest_roster_json:", text)
            self.assertIn("box-value", text)
            self.assertIn(str(roster), text)


if __name__ == "__main__":
    unittest.main()
