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


def normalized_snapshot(name: str = "星见雅") -> dict:
    return {
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
            self.assertIn("终局目标来自本地配置", report["warnings"][0])
            actions = {item["action"] for item in report["plan_items"]}
            self.assertIn("先人工确认解析结果", actions)
            self.assertIn("角色等级提升到 60", actions)
            self.assertIn("音擎等级提升到 60", actions)
            self.assertTrue(any(item["gap_type"] == "drive_disc_quality" for item in report["plan_items"]))
            self.assertEqual(report["plan_items"][0]["priority_rank"], 1)

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

    def test_cli_plan_command_is_registered(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["plan", "--snapshot", "a.json", "--targets", "targets.json", "--history-index", "history/index.json"])

        self.assertEqual(args.handler, cli_tool.run_plan)
        self.assertEqual(args.snapshot, ["a.json"])
        self.assertEqual(args.targets, "targets.json")
        self.assertEqual(args.history_index, "history/index.json")


if __name__ == "__main__":
    unittest.main()
