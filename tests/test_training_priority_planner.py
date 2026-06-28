from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANNER_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "plan_training_priorities.py"
CLI_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

planner_spec = importlib.util.spec_from_file_location("plan_training_priorities", PLANNER_SCRIPT_PATH)
assert planner_spec is not None
planner_tool = importlib.util.module_from_spec(planner_spec)
assert planner_spec.loader is not None
sys.modules[planner_spec.name] = planner_tool
planner_spec.loader.exec_module(planner_tool)

cli_spec = importlib.util.spec_from_file_location("miho_probe_cli", CLI_SCRIPT_PATH)
assert cli_spec is not None
cli_tool = importlib.util.module_from_spec(cli_spec)
assert cli_spec.loader is not None
sys.modules[cli_spec.name] = cli_tool
cli_spec.loader.exec_module(cli_tool)


def field(value, *, status: str = "ok", uncertain: bool = False) -> dict:
    if value is None:
        status = "missing"
        uncertain = True
    return {
        "value": value,
        "status": status,
        "uncertain": uncertain,
        "evidence": ["mock"],
        "source_region": "mock",
    }


def normalized_snapshot(name: str = "星见雅", combat_tags: list[str] | None = None) -> dict:
    snapshot = {
        "schema_version": "p1.0-draft",
        "source_type": "official_export_image",
        "game": "zzz",
        "source": {
            "image": "figs/mock.jpg",
            "review_status": "NEEDS_REVIEW",
            "coverage_level": "medium",
        },
        "character": {
            "name": field(name),
            "level": field("50"),
            "rank": field("S"),
        },
        "build_snapshot": {
            "stats": {
                "hp": field("10000"),
                "atk": field("1800"),
                "def": field("800"),
                "impact": field("90"),
                "crit_rate": field("35%"),
                "crit_dmg": field("70%"),
                "anomaly_mastery": field("80"),
                "anomaly_proficiency": field("120"),
                "pen": field("0"),
                "energy_regen": field("1.2"),
                "damage_bonus": field("20%"),
            },
            "skill_levels": [{"slot": slot, "level": field("6")} for slot in range(1, 7)],
            "equipment": {
                "name": field("霰落星殿"),
                "level": field("40"),
                "rank": field("S"),
            },
            "drive_discs": [
                {
                    "slot": slot,
                    "set_name": field("折枝剑歌"),
                    "level": field("9" if slot <= 3 else "15"),
                    "main_stat": field("暴击率 24%" if slot <= 4 else None),
                    "sub_stats": [
                        {"stat": "攻击力", "value": "19", "enhancement": None, "status": "ok", "uncertain": False, "evidence": ["mock"]}
                    ]
                    if slot <= 2
                    else [],
                }
                for slot in range(1, 7)
            ],
        },
        "quality": {
            "trusted_field_count": 44,
            "field_count": 50,
            "requires_manual_review": True,
            "blockers": ["drive_disc sub_stats 全缺"],
        },
    }
    if combat_tags:
        snapshot["combat_tags"] = combat_tags
    return snapshot


def targets_json() -> dict:
    return {
        "game": "zzz",
        "source": {"type": "mock", "note": "unit test fixture"},
        "default_minimums": {
            "character_level": 60,
            "equipment_level": 60,
            "skill_level": 8,
            "drive_disc_level": 12,
            "stats": {"atk": 2000, "crit_rate": 45},
        },
        "targets": [
            {
                "goal_id": "zzz_mock_shiyu",
                "activity_name": "式舆防卫战",
                "target_tier": "稳定通关",
                "priority": "high",
                "preferred_characters": ["星见雅"],
                "minimums": {"skill_level": 9},
            }
        ],
    }


class TrainingPriorityPlannerTests(unittest.TestCase):
    def test_generate_report_prioritizes_review_and_training_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            output_dir = root / "planner"
            snapshot_path.write_text(json.dumps(normalized_snapshot(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets_json(), ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, output_dir)

            self.assertTrue(Path(report["output_json"]).exists())
            self.assertTrue(Path(report["output_md"]).exists())
            self.assertEqual(report["schema_version"], "p1.2-planner-draft")
            self.assertEqual(report["target_source_status"]["status"], "local_draft")
            self.assertEqual(report["target_source_status"]["planning_confidence"], "low")
            self.assertIn("终局目标来自本地配置", report["warnings"][0])
            actions = {item["action"] for item in report["plan_items"]}
            self.assertIn("先人工确认解析结果", actions)
            self.assertIn("角色等级提升到 60", actions)
            self.assertIn("音擎等级提升到 60", actions)
            self.assertTrue(any(item["gap_type"] == "drive_disc_quality" for item in report["plan_items"]))
            training_items = [item for item in report["plan_items"] if item["gap_type"] != "data_review"]
            self.assertTrue(training_items)
            self.assertTrue(all(item["confidence"] == "low" for item in training_items))
            self.assertTrue(any("不能代表当前线上高难" in item["reason"] for item in training_items))
            self.assertEqual(report["plan_items"][0]["priority_rank"], 1)
            self.assertEqual(report["resource_plan"]["budget"]["daily_stamina"], 240.0)
            self.assertEqual(report["resource_plan"]["budget"]["horizon_days"], 7)
            self.assertTrue(report["resource_plan"]["today"])
            self.assertTrue(report["resource_plan"]["no_stamina_actions"])

    def test_generate_report_marks_fresh_official_targets_current_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            targets = targets_json()
            targets["source"] = {"type": "official_snapshot", "note": "fresh saved public official page"}
            targets["freshness"] = {"level": "fresh", "stale_source_count": 0, "max_source_age_hours": 168}
            snapshot_path.write_text(json.dumps(normalized_snapshot(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner")

            self.assertEqual(report["target_source_status"]["status"], "current")
            self.assertTrue(report["target_source_status"]["current_endgame_ready"])
            self.assertFalse(any("本地配置或 mock" in warning for warning in report["warnings"]))
            training_items = [item for item in report["plan_items"] if item["gap_type"] != "data_review"]
            self.assertTrue(training_items)
            self.assertTrue(all(item["source_confidence"] == "high" for item in training_items))

    def test_generate_report_matches_targets_by_combat_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            targets = targets_json()
            targets["source"] = {"type": "official_snapshot"}
            targets["freshness"] = {"level": "fresh", "stale_source_count": 0}
            targets["targets"][0].pop("preferred_characters")
            targets["targets"][0]["weakness_tags"] = ["ice"]
            targets["targets"][0]["mechanic_tags"] = ["anomaly"]
            snapshot_path.write_text(json.dumps(normalized_snapshot(combat_tags=["ice", "anomaly"]), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner")

            character = report["characters"][0]
            self.assertEqual(character["matched_targets"], ["式舆防卫战 稳定通关"])
            self.assertEqual(character["target_matches"][0]["match_type"], "tag_overlap")
            self.assertEqual(character["target_matches"][0]["matched_tags"], ["anomaly", "ice"])
            self.assertEqual(report["target_coverage"][0]["coverage_status"], "covered")
            self.assertEqual(report["target_coverage"][0]["matched_characters"][0]["character"], "星见雅")
            self.assertTrue(any("角色标签命中目标弱点/机制" in item["target_match_reasons"][0] for item in report["plan_items"]))
            markdown = Path(report["output_md"]).read_text(encoding="utf-8")
            self.assertIn("目标覆盖", markdown)
            self.assertIn("target_matches", markdown)
            self.assertIn("tag_overlap", markdown)

    def test_generate_report_matches_targets_by_character_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            catalog_path = root / "catalog.json"
            targets = targets_json()
            targets["source"] = {"type": "official_snapshot"}
            targets["freshness"] = {"level": "fresh", "stale_source_count": 0}
            targets["targets"][0].pop("preferred_characters")
            targets["targets"][0]["weakness_tags"] = ["ice"]
            targets["targets"][0]["mechanic_tags"] = ["anomaly"]
            catalog_path.write_text(
                json.dumps(
                    {"characters": [{"name": "星见雅", "element": "ice", "combat_tags": ["anomaly", "slash"]}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot_path.write_text(json.dumps(normalized_snapshot(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner", character_catalog=catalog_path)

            character = report["characters"][0]
            self.assertEqual(report["character_catalog"]["entry_count"], 1)
            self.assertTrue(character["catalog_match"]["matched"])
            self.assertEqual(character["catalog_match"]["catalog_name"], "星见雅")
            self.assertEqual(character["target_matches"][0]["match_type"], "tag_overlap")
            self.assertEqual(character["target_matches"][0]["matched_tags"], ["anomaly", "ice"])

    def test_generate_report_warns_for_uncovered_current_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            targets = targets_json()
            targets["source"] = {"type": "official_snapshot"}
            targets["freshness"] = {"level": "fresh", "stale_source_count": 0}
            targets["targets"][0].pop("preferred_characters")
            targets["targets"][0]["weakness_tags"] = ["fire"]
            targets["targets"][0]["mechanic_tags"] = ["stun"]
            snapshot_path.write_text(json.dumps(normalized_snapshot(combat_tags=["ice", "anomaly"]), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner")

            self.assertEqual(report["target_coverage"][0]["coverage_status"], "unmatched")
            self.assertEqual(report["target_coverage"][0]["match_count"], 0)
            self.assertTrue(any("暂无当前 box 匹配角色" in warning for warning in report["warnings"]))

    def test_generate_report_lists_catalog_candidates_for_uncovered_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            catalog_path = root / "catalog.json"
            targets = targets_json()
            targets["source"] = {"type": "official_snapshot"}
            targets["freshness"] = {"level": "fresh", "stale_source_count": 0}
            targets["targets"][0].pop("preferred_characters")
            targets["targets"][0]["weakness_tags"] = ["fire"]
            targets["targets"][0]["mechanic_tags"] = ["stun"]
            catalog_path.write_text(
                json.dumps(
                    {
                        "characters": [
                            {"name": "珂蕾妲", "element": "fire", "combat_tags": ["stun"]},
                            {"name": "星见雅", "element": "ice", "combat_tags": ["anomaly"]},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot_path.write_text(json.dumps(normalized_snapshot(combat_tags=["ice", "anomaly"]), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner", character_catalog=catalog_path)

            coverage = report["target_coverage"][0]
            self.assertEqual(coverage["coverage_status"], "unmatched")
            self.assertEqual(coverage["catalog_candidates"][0]["character"], "珂蕾妲")
            self.assertEqual(coverage["catalog_candidates"][0]["matched_tags"], ["fire", "stun"])
            self.assertTrue(any("catalog 候选" in warning for warning in report["warnings"]))
            markdown = Path(report["output_md"]).read_text(encoding="utf-8")
            self.assertIn("珂蕾妲", markdown)

    def test_catalog_candidates_include_preferred_characters_not_in_current_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            catalog_path = root / "catalog.json"
            targets = targets_json()
            targets["source"] = {"type": "official_snapshot"}
            targets["freshness"] = {"level": "fresh", "stale_source_count": 0}
            targets["targets"][0]["preferred_characters"] = ["莱特"]
            catalog_path.write_text(
                json.dumps({"characters": [{"name": "莱特", "element": "fire", "combat_tags": ["stun"]}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            snapshot_path.write_text(json.dumps(normalized_snapshot(name="星见雅"), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner", character_catalog=catalog_path)

            candidate = report["target_coverage"][0]["catalog_candidates"][0]
            self.assertEqual(candidate["character"], "莱特")
            self.assertIn("preferred_character", candidate["match_types"])
            self.assertEqual(candidate["score"], 95)

    def test_generate_report_warns_on_stale_target_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            targets = targets_json()
            targets["source"] = {"type": "official_current"}
            targets["freshness"] = {"level": "stale", "stale_source_count": 1, "max_source_age_hours": 24}
            snapshot_path.write_text(json.dumps(normalized_snapshot(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report([snapshot_path], targets_path, root / "planner")

            self.assertEqual(report["target_source_status"]["status"], "stale")
            self.assertFalse(report["target_source_status"]["current_endgame_ready"])
            self.assertTrue(any("来源已过期" in warning for warning in report["warnings"]))
            self.assertTrue(any("先刷新来源" in item["reason"] for item in report["plan_items"] if item["gap_type"] != "data_review"))

    def test_snapshot_manifest_input_loads_multiple_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_a = root / "a.json"
            snapshot_b = root / "b.json"
            manifest = root / "manifest.json"
            targets_path = root / "targets.json"
            snapshot_a.write_text(json.dumps(normalized_snapshot("星见雅"), ensure_ascii=False), encoding="utf-8")
            snapshot_b.write_text(json.dumps(normalized_snapshot("苍角"), ensure_ascii=False), encoding="utf-8")
            manifest.write_text(json.dumps({"snapshots": [str(snapshot_a), str(snapshot_b)]}, ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets_json(), ensure_ascii=False), encoding="utf-8")

            paths = planner_tool.load_manifest_snapshots(manifest)
            report = planner_tool.generate_report(paths, targets_path, root / "planner")

            self.assertEqual(len(paths), 2)
            self.assertEqual(len(report["characters"]), 2)
            self.assertEqual(report["characters"][0]["character"], "星见雅")
            self.assertEqual(report["characters"][1]["character"], "苍角")

    def test_generate_report_uses_history_context_for_continuity_bonus(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            output_dir = root / "planner"
            snapshot_path.write_text(json.dumps(normalized_snapshot(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets_json(), ensure_ascii=False), encoding="utf-8")
            history_context = {
                "items": [
                    {
                        "character": "星见雅",
                        "status": "diffed",
                        "current_snapshot": str(snapshot_path),
                        "previous_snapshot": str(root / "previous.json"),
                        "diff_md": str(root / "diff.md"),
                        "change_count": 4,
                        "requires_review_change_count": 1,
                    }
                ]
            }

            report = planner_tool.generate_report([snapshot_path], targets_path, output_dir, history_context=history_context)

            self.assertTrue(report["history_context"]["available"])
            self.assertEqual(report["history_context"]["character_count"], 1)
            self.assertEqual(report["characters"][0]["history"]["recent_change_count"], 4)
            boosted_items = [item for item in report["plan_items"] if item["continuity_bonus"] > 0]
            self.assertTrue(boosted_items)
            self.assertTrue(any("历史快照显示近期已有 4 项变化" in item["reason"] for item in boosted_items))

    def test_generate_report_accepts_resource_budget_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "snapshot.json"
            targets_path = root / "targets.json"
            snapshot_path.write_text(json.dumps(normalized_snapshot(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets_json(), ensure_ascii=False), encoding="utf-8")

            report = planner_tool.generate_report(
                [snapshot_path],
                targets_path,
                root / "planner",
                daily_stamina=120,
                horizon_days=3,
            )

            self.assertEqual(report["resource_plan"]["budget"]["daily_stamina"], 120.0)
            self.assertEqual(report["resource_plan"]["budget"]["horizon_days"], 3)
            self.assertEqual(report["resource_plan"]["budget"]["total_stamina"], 360.0)
            self.assertTrue(report["resource_plan"]["horizon"])

    def test_cli_plan_command_is_registered(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(
            [
                "plan",
                "--snapshot",
                "a.json",
                "--targets",
                "targets.json",
                "--history-index",
                "history/index.json",
                "--character-catalog",
                "catalog.json",
                "--daily-stamina",
                "180",
                "--horizon-days",
                "5",
            ]
        )

        self.assertEqual(args.handler, cli_tool.run_plan)
        self.assertEqual(args.snapshot, ["a.json"])
        self.assertEqual(args.targets, "targets.json")
        self.assertEqual(args.history_index, "history/index.json")
        self.assertEqual(args.character_catalog, "catalog.json")
        self.assertEqual(args.daily_stamina, 180)
        self.assertEqual(args.horizon_days, 5)


if __name__ == "__main__":
    unittest.main()
