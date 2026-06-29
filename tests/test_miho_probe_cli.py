from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

cli_spec = importlib.util.spec_from_file_location("miho_probe_cli", CLI_SCRIPT_PATH)
assert cli_spec is not None
cli_tool = importlib.util.module_from_spec(cli_spec)
assert cli_spec.loader is not None
sys.modules[cli_spec.name] = cli_tool
cli_spec.loader.exec_module(cli_tool)


def minimal_summary() -> dict:
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


class MihoProbeCliTests(unittest.TestCase):
    def test_dashboard_command_refreshes_legacy_cached_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = root / "demo_summary.json"
            dashboard_path = root / "index.html"
            summary_path.write_text(json.dumps(minimal_summary(), ensure_ascii=False), encoding="utf-8")
            dashboard_path.write_text("<html><body>Brief Warning trusted ready</body></html>", encoding="utf-8")

            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(dashboard_path),
                    summary=str(summary_path),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 0)
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("米游社练度识别体验台", html)
            self.assertNotIn("Brief Warning", html)
            self.assertNotIn("trusted ready", html)

    def test_dashboard_command_reports_missing_cache_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(root / "index.html"),
                    summary=str(root / "missing_summary.json"),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 1)

    def test_parser_has_app_like_dashboard_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["dashboard", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_dashboard)
        self.assertFalse(args.open)
        self.assertTrue(str(args.dashboard).endswith("data\\probes\\demo\\index.html") or str(args.dashboard).endswith("data/probes/demo/index.html"))

    def test_detect_project_root_points_to_workspace(self) -> None:
        self.assertEqual(cli_tool.detect_project_root(), PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
