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


def parsed_json(name: str = "星见雅", image: str = "figs/mock.jpg", atk: str = "200") -> dict:
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
                "atk": field(atk),
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


def targets_json() -> dict:
    return {
        "game": "zzz",
        "source": {"type": "manual", "note": "unit test fixture"},
        "default_minimums": {
            "character_level": 60,
            "equipment_level": 60,
            "skill_level": 8,
            "drive_disc_level": 12,
            "stats": {"atk": 250, "crit_rate": 20},
        },
        "targets": [
            {
                "goal_id": "zzz_mock_crisis",
                "activity_name": "危局强袭战",
                "target_tier": "稳定通关",
                "priority": "high",
                "preferred_characters": ["星见雅"],
                "minimums": {"skill_level": 8},
            }
        ],
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
                    "target_source_manifest": str(root / "target_sources.json"),
                    "history_dir": str(root / "snapshot_history"),
                },
                "warnings": ["当前包含历史 parsed 结果，平均通过率不代表 P0.9 replay batch"],
                "training_plan": {
                    "targets_json": str(root / "targets.json"),
                    "output_json": str(root / "training_priority_report.json"),
                    "output_md": str(root / "training_priority_report.md"),
                    "plan_item_count": 1,
                    "top_plan_items": [
                        {
                            "priority_rank": 1,
                            "character": "星见雅",
                            "target": "危局强袭战 稳定通关",
                            "action": "先人工确认解析结果",
                            "reason": "mock reason",
                            "estimated_days": 0.0,
                            "confidence": "high",
                        }
                    ],
                    "warnings": ["终局目标来自本地配置或 mock"],
                    "error": None,
                },
                "pipeline_steps": [{"name": "Normalized Snapshot", "status": "needs_review"}],
                "target_refresh": {
                    "manifest": str(root / "target_sources.json"),
                    "output_json": str(root / "targets" / "endgame_targets.json"),
                    "source_count": 1,
                    "target_count": 1,
                    "warnings": ["目标来源不是 official_current / official_snapshot"],
                    "error": None,
                    "source_type": "public_web_snapshot",
                    "game": "zzz",
                },
                "snapshot_history": {
                    "history_dir": str(root / "snapshot_history"),
                    "index_json": str(root / "snapshot_history" / "index.json"),
                    "snapshot_count": 1,
                    "diff_count": 1,
                    "changed_character_count": 1,
                    "no_previous_count": 0,
                    "diff_failed_count": 0,
                    "items": [
                        {
                            "character": "星见雅",
                            "case_name": "case_a",
                            "current_snapshot": str(root / "snapshot_history" / "current.json"),
                            "previous_snapshot": str(root / "snapshot_history" / "previous.json"),
                            "diff_md": str(root / "snapshot_history" / "diff.md"),
                            "change_count": 2,
                            "requires_review_change_count": 0,
                            "status": "diffed",
                        }
                    ],
                },
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
            self.assertIn("培养优先级候选", html)
            self.assertIn("终局目标刷新", html)
            self.assertIn("endgame_targets.json", html)
            self.assertIn("快照历史", html)
            self.assertIn("snapshot_diff_md", html)
            self.assertIn("先人工确认解析结果", html)
            self.assertIn("training_priority_report.json", html)
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
            self.assertEqual(summary["snapshot_history"]["snapshot_count"], 1)
            self.assertEqual(summary["snapshot_history"]["no_previous_count"], 1)
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

    def test_run_demo_pipeline_with_targets_generates_training_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            targets_path = root / "targets.json"
            parsed_dir.mkdir()
            parsed_path = parsed_dir / "case_a.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets_json(), ensure_ascii=False), encoding="utf-8")

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=parsed_dir,
                manifest=None,
                output_dir=output_dir,
                open_dashboard=False,
                targets=targets_path,
            )
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")

            self.assertIn("training_plan", summary)
            self.assertGreater(summary["training_plan"]["plan_item_count"], 0)
            self.assertTrue(summary["training_plan"]["history_context"]["available"])
            self.assertEqual(summary["training_plan"]["history_context"]["character_count"], 1)
            self.assertTrue(Path(summary["training_plan"]["output_json"]).exists())
            self.assertTrue(Path(summary["training_plan"]["output_md"]).exists())
            self.assertIn("Training Plan", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("培养优先级候选", dashboard_html)
            self.assertIn("先人工确认解析结果", dashboard_html)

    def test_run_demo_pipeline_refreshes_targets_from_source_manifest_before_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            source_path = root / "endgame_source.html"
            manifest_path = root / "target_sources.json"
            parsed_dir.mkdir()
            parsed_path = parsed_dir / "case_a.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False), encoding="utf-8")
            source_path.write_text(
                "<html><title>危局强袭战 本期目标</title><body>危局强袭战 推荐冰属性与异常队伍。</body></html>",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "game": "zzz",
                        "source_type": "official_snapshot",
                        "default_minimums": {"character_level": 60, "equipment_level": 60, "skill_level": 8},
                        "sources": [
                            {
                                "input": str(source_path),
                                "goal_id": "zzz_mock_refresh",
                                "target_tier": "稳定通关",
                                "priority": "high",
                                "preferred_characters": ["星见雅"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=parsed_dir,
                manifest=None,
                output_dir=output_dir,
                open_dashboard=False,
                target_source_manifest=manifest_path,
            )
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")

            self.assertEqual(summary["target_refresh"]["target_count"], 1)
            self.assertEqual(summary["target_refresh"]["source_count"], 1)
            self.assertTrue(Path(summary["target_refresh"]["output_json"]).exists())
            self.assertIn("training_plan", summary)
            self.assertEqual(summary["training_plan"]["targets_json"], summary["target_refresh"]["output_json"])
            self.assertGreater(summary["training_plan"]["plan_item_count"], 0)
            self.assertIn("Target Refresh", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("终局目标刷新", dashboard_html)
            self.assertIn("endgame_targets.json", dashboard_html)

    def test_run_demo_pipeline_rejects_static_targets_and_target_source_manifest_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(pipeline_tool.DemoPipelineError):
                pipeline_tool.run_pipeline(
                    images_dir=None,
                    parsed_dir=root,
                    manifest=None,
                    output_dir=root / "demo",
                    open_dashboard=False,
                    targets=root / "targets.json",
                    target_source_manifest=root / "target_sources.json",
                )

    def test_run_demo_pipeline_records_snapshot_history_and_diffs_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_parsed_dir = root / "parsed_first"
            second_parsed_dir = root / "parsed_second"
            first_output_dir = root / "demo_first"
            second_output_dir = root / "demo_second"
            history_dir = root / "history"
            first_parsed_dir.mkdir()
            second_parsed_dir.mkdir()
            first_path = first_parsed_dir / "case_first.json"
            second_path = second_parsed_dir / "case_second.json"
            first_path.write_text(json.dumps(parsed_json(atk="200"), ensure_ascii=False), encoding="utf-8")
            second_path.write_text(json.dumps(parsed_json(atk="260"), ensure_ascii=False), encoding="utf-8")

            first = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=first_parsed_dir,
                manifest=None,
                output_dir=first_output_dir,
                history_dir=history_dir,
                open_dashboard=False,
            )
            second = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=second_parsed_dir,
                manifest=None,
                output_dir=second_output_dir,
                history_dir=history_dir,
                open_dashboard=False,
            )

            self.assertEqual(first["snapshot_history"]["snapshot_count"], 1)
            self.assertEqual(first["snapshot_history"]["diff_count"], 0)
            self.assertEqual(first["snapshot_history"]["no_previous_count"], 1)
            self.assertEqual(second["snapshot_history"]["snapshot_count"], 1)
            self.assertEqual(second["snapshot_history"]["diff_count"], 1)
            self.assertEqual(second["snapshot_history"]["changed_character_count"], 1)
            item = second["snapshot_history"]["items"][0]
            self.assertGreater(item["change_count"], 0)
            self.assertTrue(Path(item["current_snapshot"]).exists())
            self.assertTrue(Path(item["previous_snapshot"]).exists())
            self.assertTrue(Path(item["diff_md"]).exists())
            self.assertTrue((history_dir / "index.json").exists())
            dashboard_html = Path(second["dashboard_html"]).read_text(encoding="utf-8")
            self.assertIn("快照历史", dashboard_html)
            self.assertIn("snapshot_diff_md", dashboard_html)

    def test_run_demo_pipeline_image_mode_writes_update_state_and_new_only_skips_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "figs"
            output_dir = root / "demo"
            state_file = root / "update_state.json"
            images_dir.mkdir()
            image_a = images_dir / "a.jpg"
            image_b = images_dir / "b.jpg"
            image_a.write_bytes(b"image-a-v1")
            image_b.write_bytes(b"image-b-v1")
            processed: list[str] = []
            original_process = pipeline_tool.process_image_case

            def fake_process_image_case(image_path, *, name, output_dir, expected_dir, engine, game, layout):  # noqa: ANN001, ANN003
                processed.append(Path(image_path).name)
                case = pipeline_tool.case_template(name)
                case["image"] = str(Path(image_path).resolve())
                case["review_status"] = "PASS"
                return case

            pipeline_tool.process_image_case = fake_process_image_case
            try:
                first = pipeline_tool.run_pipeline(
                    images_dir=images_dir,
                    parsed_dir=None,
                    manifest=None,
                    output_dir=output_dir,
                    state_file=state_file,
                    open_dashboard=False,
                )
                self.assertEqual(processed, ["a.jpg", "b.jpg"])
                self.assertTrue(state_file.exists())
                self.assertEqual(first["update_state"]["processed_image_count"], 2)

                processed.clear()
                second = pipeline_tool.run_pipeline(
                    images_dir=images_dir,
                    parsed_dir=None,
                    manifest=None,
                    output_dir=output_dir,
                    state_file=state_file,
                    new_only=True,
                    open_dashboard=False,
                )
                self.assertEqual(processed, [])
                self.assertEqual(second["overall"]["case_count"], 0)
                self.assertEqual(second["update_state"]["skipped_unchanged_count"], 2)
                self.assertIn("new-only 模式没有发现新增或变更图片", second["warnings"][0])

                image_b.write_bytes(b"image-b-v2")
                processed.clear()
                third = pipeline_tool.run_pipeline(
                    images_dir=images_dir,
                    parsed_dir=None,
                    manifest=None,
                    output_dir=output_dir,
                    state_file=state_file,
                    new_only=True,
                    open_dashboard=False,
                )
                self.assertEqual(processed, ["b.jpg"])
                self.assertEqual(third["update_state"]["status_counts"]["changed"], 1)
                self.assertEqual(third["update_state"]["processed_image_count"], 1)
            finally:
                pipeline_tool.process_image_case = original_process

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
                    new_only=False,
                    clean_demo=False,
                    state_file=None,
                    targets=None,
                    history_dir=None,
                    target_source_manifest=None,
                )
            )
        finally:
            cli_tool.demo_tool.run_pipeline = original_run_pipeline

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["engine"], "paddle")
        self.assertIsNotNone(calls[0]["images_dir"])
        self.assertFalse(calls[0]["latest_only"])
        self.assertFalse(calls[0]["new_only"])
        self.assertIsNone(calls[0]["state_file"])
        self.assertIsNone(calls[0]["targets"])
        self.assertIsNone(calls[0]["history_dir"])
        self.assertIsNone(calls[0]["target_source_manifest"])


if __name__ == "__main__":
    unittest.main()
