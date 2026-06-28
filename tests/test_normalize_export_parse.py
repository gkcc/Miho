from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NORMALIZE_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "normalize_export_parse.py"
BATCH_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "normalize_export_batch.py"
DIFF_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "diff_normalized_snapshots.py"

normalize_spec = importlib.util.spec_from_file_location("normalize_export_parse", NORMALIZE_SCRIPT_PATH)
assert normalize_spec is not None
normalize_tool = importlib.util.module_from_spec(normalize_spec)
assert normalize_spec.loader is not None
sys.modules[normalize_spec.name] = normalize_tool
normalize_spec.loader.exec_module(normalize_tool)

batch_spec = importlib.util.spec_from_file_location("normalize_export_batch", BATCH_SCRIPT_PATH)
assert batch_spec is not None
batch_tool = importlib.util.module_from_spec(batch_spec)
assert batch_spec.loader is not None
sys.modules[batch_spec.name] = batch_tool
batch_spec.loader.exec_module(batch_tool)

diff_spec = importlib.util.spec_from_file_location("diff_normalized_snapshots", DIFF_SCRIPT_PATH)
assert diff_spec is not None
diff_tool = importlib.util.module_from_spec(diff_spec)
assert diff_spec.loader is not None
sys.modules[diff_spec.name] = diff_tool
diff_spec.loader.exec_module(diff_tool)


def field(value, *, status: str = "ok", uncertain: bool = False, evidence: list[str] | None = None) -> dict:
    if value is None:
        status = "missing"
        uncertain = True
    return {
        "value": value,
        "status": status,
        "uncertain": uncertain,
        "evidence": evidence or ["mock"],
        "source_region": "mock_region",
    }


def parsed_json(*, character_name=None, equipment_name=None, invalid: bool = False) -> dict:
    equipment_name = equipment_name if equipment_name is not None else "幻变魔方"
    name_status = "invalid_candidate" if invalid else "ok"
    return {
        "metadata": {
            "input_image": "data/probes/exported_images/mock.jpg",
            "ocr_engine": "paddle",
            "game": "zzz",
            "layout": "zzz-agent-card",
        },
        "coverage_summary": {"coverage_level": "high"},
        "extracted_draft": {
            "game": "zzz",
            "source_type": "official_export_image",
            "character": {
                "name": field(character_name, status="uncertain" if character_name else "missing", uncertain=character_name is not None),
                "level": field("60"),
                "rank": field("S"),
            },
            "stats": {
                "hp": field("17398"),
                "atk": field("2194"),
                "def": field("870"),
                "impact": field("95"),
                "crit_rate": field("45.8%"),
                "crit_dmg": field("85.2%"),
                "anomaly_mastery": field("90"),
                "anomaly_proficiency": field("152"),
                "pen": field("2397"),
                "energy_regen": field("2.00"),
                "physical_dmg_bonus": field("30.0%"),
            },
            "skill_levels": [{"slot": slot, "level": field(str(slot + 4))} for slot in range(1, 7)],
            "equipment": {
                "name": field(equipment_name, status=name_status, uncertain=invalid),
                "level": field("60"),
                "rank": field("A"),
            },
            "drive_discs": [
                {
                    "slot": slot,
                    "set_name": field(f"套装{slot}"),
                    "level": field("15"),
                    "main_stat": field("暴击率 24%"),
                    "sub_stats": field(
                        [
                            {
                                "stat": "攻击力",
                                "value": "19",
                                "enhancement": None,
                                "uncertain": False,
                                "evidence": ["攻击力", "19"],
                            }
                        ]
                    ),
                }
                for slot in range(1, 7)
            ],
        },
    }


class NormalizeExportParseTests(unittest.TestCase):
    def test_normalize_maps_parsed_json_and_preserves_field_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_path = root / "parsed.json"
            output_dir = root / "normalized"
            parsed_path.write_text(json.dumps(parsed_json(character_name="星见雅"), ensure_ascii=False), encoding="utf-8")

            result = normalize_tool.normalize_file(parsed_path, output_dir)
            normalized = result["normalized"]

            self.assertTrue(Path(result["normalized_json"]).exists())
            self.assertTrue(Path(result["normalized_md"]).exists())
            self.assertEqual(normalized["schema_version"], "p1.0-draft")
            self.assertEqual(normalized["source_type"], "official_export_image")
            self.assertEqual(normalized["character"]["name"]["value"], "星见雅")
            self.assertTrue(normalized["character"]["name"]["uncertain"])
            self.assertEqual(normalized["character"]["name"]["evidence"], ["mock"])
            self.assertEqual(normalized["build_snapshot"]["stats"]["damage_bonus"]["value"], "30.0%")
            self.assertNotIn("physical_dmg_bonus", normalized["build_snapshot"]["stats"])
            self.assertFalse(normalized["quality"]["can_import_without_review"])
            self.assertTrue(normalized["quality"]["requires_manual_review"])
            self.assertIn("character.name 缺失或 uncertain", normalized["quality"]["blockers"])

    def test_invalid_candidate_triggers_quality_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_path = root / "parsed.json"
            parsed_path.write_text(
                json.dumps(parsed_json(character_name="星见雅", equipment_name="驱动", invalid=True), ensure_ascii=False),
                encoding="utf-8",
            )

            result = normalize_tool.normalize_file(parsed_path, root)

            self.assertIn("invalid_candidate 字段存在", result["normalized"]["quality"]["blockers"])
            self.assertGreater(result["normalized"]["quality"]["invalid_field_count"], 0)

    def test_missing_drive_disc_count_triggers_quality_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_path = root / "parsed.json"
            parsed = parsed_json(character_name="星见雅")
            parsed["extracted_draft"]["drive_discs"] = parsed["extracted_draft"]["drive_discs"][:5]
            parsed_path.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")

            result = normalize_tool.normalize_file(parsed_path, root)

            self.assertEqual(len(result["normalized"]["build_snapshot"]["drive_discs"]), 6)
            self.assertIn("drive_discs 少于 6 个", result["normalized"]["quality"]["blockers"])

    def test_batch_normalize_outputs_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_a = root / "a.json"
            parsed_b = root / "b.json"
            output_dir = root / "batch"
            parsed_a.write_text(json.dumps(parsed_json(character_name="星见雅"), ensure_ascii=False), encoding="utf-8")
            parsed_b.write_text(json.dumps(parsed_json(character_name=None), ensure_ascii=False), encoding="utf-8")

            summary = batch_tool.run_batch([parsed_a, parsed_b], output_dir)

            self.assertEqual(summary["case_count"], 2)
            self.assertEqual(len(summary["normalized_json"]), 2)
            self.assertTrue(Path(summary["summary_json"]).exists())
            self.assertTrue(Path(summary["summary_md"]).exists())
            self.assertGreater(summary["trusted_field_count"], 0)
            self.assertEqual(len(summary["requires_manual_review_cases"]), 2)

    def test_diff_normalized_snapshots_detects_level_stats_skills_equipment_and_discs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_parsed = root / "old_parsed.json"
            new_parsed = root / "new_parsed.json"
            old_data = parsed_json(character_name="星见雅")
            new_data = parsed_json(character_name="星见雅")
            new_data["extracted_draft"]["character"]["level"] = field("61")
            new_data["extracted_draft"]["stats"]["atk"] = field("2300")
            new_data["extracted_draft"]["skill_levels"][0]["level"] = field("10")
            new_data["extracted_draft"]["equipment"]["name"] = field("新音擎")
            new_data["extracted_draft"]["drive_discs"][0]["level"] = field("12")
            new_data["extracted_draft"]["drive_discs"][0]["main_stat"] = field("生命值 2200", status="uncertain", uncertain=True)
            old_parsed.write_text(json.dumps(old_data, ensure_ascii=False), encoding="utf-8")
            new_parsed.write_text(json.dumps(new_data, ensure_ascii=False), encoding="utf-8")
            old_norm = normalize_tool.normalize_file(old_parsed, root)["normalized_json"]
            new_norm = normalize_tool.normalize_file(new_parsed, root)["normalized_json"]

            diff = diff_tool.diff_files(Path(old_norm), Path(new_norm), root)
            paths = {item["path"] for item in diff["changes"]}

            self.assertIn("character.level", paths)
            self.assertIn("build_snapshot.stats.atk", paths)
            self.assertIn("build_snapshot.skill_levels[1].level", paths)
            self.assertIn("build_snapshot.equipment.name", paths)
            self.assertIn("build_snapshot.drive_discs[1].level", paths)
            main_change = next(item for item in diff["changes"] if item["path"] == "build_snapshot.drive_discs[1].main_stat")
            self.assertTrue(main_change["requires_review"])
            self.assertTrue(Path(diff["output_json"]).exists())
            self.assertTrue(Path(diff["output_md"]).exists())


if __name__ == "__main__":
    unittest.main()
