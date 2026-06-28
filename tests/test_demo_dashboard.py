from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "render_demo_dashboard.py"
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "run_demo_pipeline.py"
CLI_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

dashboard_spec = importlib.util.spec_from_file_location("render_demo_dashboard", DASHBOARD_SCRIPT_PATH)
assert dashboard_spec is not None
dashboard_tool = importlib.util.module_from_spec(dashboard_spec)
assert dashboard_spec.loader is not None
sys.modules[dashboard_spec.name] = dashboard_tool
dashboard_spec.loader.exec_module(dashboard_tool)

pipeline_spec = importlib.util.spec_from_file_location("run_demo_pipeline", PIPELINE_SCRIPT_PATH)
assert pipeline_spec is not None
pipeline_tool = importlib.util.module_from_spec(pipeline_spec)
assert pipeline_spec.loader is not None
sys.modules[pipeline_spec.name] = pipeline_tool
pipeline_spec.loader.exec_module(pipeline_tool)

cli_spec = importlib.util.spec_from_file_location("miho_probe_cli", CLI_SCRIPT_PATH)
assert cli_spec is not None
cli_tool = importlib.util.module_from_spec(cli_spec)
assert cli_spec.loader is not None
sys.modules[cli_spec.name] = cli_tool
cli_spec.loader.exec_module(cli_tool)


def field(value, *, uncertain: bool = False, status: str = "ok") -> dict:
    if value is None:
        uncertain = True
        status = "missing"
    return {
        "value": value,
        "status": status,
        "uncertain": uncertain,
        "evidence": ["mock"],
        "source_region": "mock",
    }


def parsed_json(name: str = "星见雅", image: str = "figs/mock.jpg") -> dict:
    return {
        "metadata": {
            "input_image": image,
            "ocr_engine": "paddle",
            "game": "zzz",
            "layout": "zzz-agent-card",
        },
        "coverage_summary": {"coverage_level": "medium"},
        "extracted_draft": {
            "game": "zzz",
            "source_type": "official_export_image",
            "character": {
                "name": field(name, uncertain=True, status="uncertain"),
                "level": field("60"),
                "rank": field("S"),
            },
            "stats": {
                "hp": field("100"),
                "atk": field("200"),
                "def": field("300"),
                "impact": field("90"),
                "crit_rate": field("10%"),
                "crit_dmg": field("50%"),
                "anomaly_mastery": field("100"),
                "anomaly_proficiency": field("120"),
                "pen": field("0"),
                "energy_regen": field("1.2"),
                "physical_dmg_bonus": field("30%"),
            },
            "skill_levels": [{"slot": slot, "level": field(str(slot))} for slot in range(1, 7)],
            "equipment": {"name": field("幻变魔方"), "level": field("60"), "rank": field("A")},
            "drive_discs": [
                {
                    "slot": slot,
                    "set_name": field(f"套装{slot}"),
                    "level": field("15"),
                    "main_stat": field("暴击率 24%"),
                    "sub_stats": field(
                        [{"stat": "攻击力", "value": "19", "enhancement": None, "uncertain": False, "evidence": ["攻击力", "19"]}]
                    ),
                }
                for slot in range(1, 7)
            ],
        },
    }


class DemoDashboardTests(unittest.TestCase):
    def test_dashboard_html_contains_case_links_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "index.html"
            summary = {
                "overall": {
                    "case_count": 1,
                    "parse_success_count": 1,
                    "review_status_counts": {"NEEDS_REVIEW": 1},
                    "average_pass_rate": None,
                    "normalized_count": 1,
                    "requires_manual_review_count": 1,
                    "conclusion": "demo",
                },
                "input": {
                    "source_mode": "parsed replay mode",
                    "images_dir": None,
                    "parsed_dir": "data/probes/parsed",
                    "manifest": None,
                    "latest_only": False,
                    "clean_demo": False,
                },
                "warnings": ["当前包含历史 parsed 结果，平均通过率不代表 P0.9 replay batch"],
                "pipeline_steps": [{"name": "Normalized Snapshot", "status": "needs_review"}],
                "cases": [
                    {
                        "name": "case_a",
                        "image": None,
                        "review_html": str(root / "case_review.html"),
                        "parsed_json": str(root / "case.json"),
                        "normalized_md": str(root / "case_normalized.md"),
                        "normalized_json": str(root / "case_normalized.json"),
                        "expected_json": str(root / "case_expected.json"),
                        "expected_json_name": "case_expected.json",
                        "expected_diff_md": None,
                        "review_status": "NEEDS_REVIEW",
                        "coverage_level": "medium",
                        "pass_rate": None,
                        "character": {"name": "星见雅", "level": "60", "rank": "S"},
                        "equipment": {"name": "幻变魔方"},
                        "quality": {
                            "trusted_field_count": 10,
                            "field_count": 12,
                            "requires_manual_review": True,
                            "blockers": ["character.name 缺失或 uncertain"],
                        },
                        "errors": [],
                    }
                ],
            }

            dashboard_tool.render_dashboard(summary, output)
            html = output.read_text(encoding="utf-8")

            self.assertIn("Miho 本地练度识别体验台", html)
            self.assertIn("parsed replay mode", html)
            self.assertIn("case_a", html)
            self.assertIn("星见雅", html)
            self.assertIn("normalized_json", html)
            self.assertIn("review_html", html)
            self.assertIn("case_expected.json", html)
            self.assertIn("当前包含历史 parsed 结果", html)
            self.assertIn("character.name 缺失或 uncertain", html)
            self.assertIn("N/A", html)

    def test_run_demo_pipeline_parsed_dir_does_not_run_ocr_and_renders_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            parsed_dir.mkdir()
            parsed_path = parsed_dir / "case_a.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False), encoding="utf-8")
            parsed_path.with_name("case_a_review.html").write_text("<html>review</html>", encoding="utf-8")

            original_subprocess_run = pipeline_tool.subprocess.run

            def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("parsed-dir mode must not run OCR review subprocess")

            pipeline_tool.subprocess.run = fail_if_called
            try:
                summary = pipeline_tool.run_pipeline(
                    images_dir=None,
                    parsed_dir=parsed_dir,
                    manifest=None,
                    output_dir=output_dir,
                    open_dashboard=False,
                )
            finally:
                pipeline_tool.subprocess.run = original_subprocess_run

            self.assertEqual(summary["overall"]["case_count"], 1)
            self.assertEqual(summary["overall"]["average_pass_rate"], None)
            self.assertEqual(summary["input"]["source_mode"], "parsed replay mode")
            self.assertIn("parsed-dir 模式会扫描历史 parsed JSON", summary["warnings"][0])
            self.assertTrue(Path(summary["dashboard_html"]).exists())
            self.assertTrue(Path(summary["cases"][0]["normalized_json"]).exists())
            self.assertEqual(summary["cases"][0]["review_html"], str(parsed_path.with_name("case_a_review.html").resolve()))

    def test_run_demo_pipeline_latest_only_keeps_newest_parsed_per_source_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            parsed_dir.mkdir()
            older = parsed_dir / "shared_parsed_20260627_100000.json"
            newer = parsed_dir / "shared_parsed_20260628_100000.json"
            older.write_text(json.dumps(parsed_json("旧结果", image="figs/shared.jpg"), ensure_ascii=False), encoding="utf-8")
            newer.write_text(json.dumps(parsed_json("新结果", image="figs/shared.jpg"), ensure_ascii=False), encoding="utf-8")

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=parsed_dir,
                manifest=None,
                output_dir=output_dir,
                open_dashboard=False,
                latest_only=True,
            )

            self.assertEqual(summary["overall"]["case_count"], 1)
            self.assertEqual(summary["cases"][0]["character"]["name"], "新结果")
            self.assertIn("latest-only", summary["warnings"][0])

    def test_cli_demo_command_calls_pipeline_core(self) -> None:
        calls = []
        original_run_pipeline = cli_tool.demo_tool.run_pipeline

        def fake_run_pipeline(**kwargs):  # noqa: ANN003
            calls.append(kwargs)
            return {"dashboard_html": "demo.html", "summary_json": "summary.json"}

        cli_tool.demo_tool.run_pipeline = fake_run_pipeline
        try:
            exit_code = cli_tool.run_demo(
                argparse.Namespace(
                    images_dir="figs",
                    parsed_dir=None,
                    manifest=None,
                    output_dir="data/probes/demo",
                    expected_dir="data/probes/expected",
                    engine="paddle",
                    game="zzz",
                    layout="zzz-agent-card",
                    open=False,
                    latest_only=False,
                    clean_demo=False,
                )
            )
        finally:
            cli_tool.demo_tool.run_pipeline = original_run_pipeline

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["engine"], "paddle")
        self.assertIsNotNone(calls[0]["images_dir"])
        self.assertFalse(calls[0]["latest_only"])


if __name__ == "__main__":
    unittest.main()
