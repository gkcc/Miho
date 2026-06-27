from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "evaluate_export_parse.py"
TEMPLATE_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "make_expected_template.py"
MATRIX_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "run_export_ocr_matrix.py"
REPLAY_BATCH_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "run_export_replay_batch.py"

spec = importlib.util.spec_from_file_location("evaluate_export_parse", SCRIPT_PATH)
assert spec is not None
evaluate_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = evaluate_tool
spec.loader.exec_module(evaluate_tool)

template_spec = importlib.util.spec_from_file_location("make_expected_template", TEMPLATE_SCRIPT_PATH)
assert template_spec is not None
template_tool = importlib.util.module_from_spec(template_spec)
assert template_spec.loader is not None
sys.modules[template_spec.name] = template_tool
template_spec.loader.exec_module(template_tool)

matrix_spec = importlib.util.spec_from_file_location("run_export_ocr_matrix", MATRIX_SCRIPT_PATH)
assert matrix_spec is not None
matrix_tool = importlib.util.module_from_spec(matrix_spec)
assert matrix_spec.loader is not None
sys.modules[matrix_spec.name] = matrix_tool
matrix_spec.loader.exec_module(matrix_tool)

batch_spec = importlib.util.spec_from_file_location("run_export_replay_batch", REPLAY_BATCH_SCRIPT_PATH)
assert batch_spec is not None
batch_tool = importlib.util.module_from_spec(batch_spec)
assert batch_spec.loader is not None
sys.modules[batch_spec.name] = batch_tool
batch_spec.loader.exec_module(batch_tool)


def field(value):
    return {"value": value, "uncertain": value is None, "evidence": [], "source_region": "mock"}


def parsed_json(name: str = None, skill_5: str = "9") -> dict:
    return {
        "extracted_draft": {
            "character": {"name": field(name), "level": field("60"), "rank": field(None)},
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
            "skill_levels": [
                {"slot": 1, "level": field("10")},
                {"slot": 2, "level": field("08")},
                {"slot": 3, "level": field("06")},
                {"slot": 4, "level": field("11")},
                {"slot": 5, "level": field(skill_5)},
                {"slot": 6, "level": field("07")},
            ],
            "equipment": {"name": field("驱动"), "level": field("60"), "rank": field("A")},
            "drive_discs": [
                {"slot": slot, "level": field("15"), "main_stat": field(None), "sub_stats": field([])}
                for slot in range(1, 7)
            ],
        }
    }


def expected_json() -> dict:
    expected = parsed_json(name="星见雅", skill_5="10")
    expected["extracted_draft"]["character"]["rank"] = field("S")
    expected["extracted_draft"]["equipment"]["name"] = field("幻变魔方")
    expected["extracted_draft"]["equipment"]["rank"] = field("S")
    return expected


class ExportParseEvaluateTests(unittest.TestCase):
    def test_expected_diff_outputs_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_path = root / "parsed.json"
            expected_path = root / "expected.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False, indent=2), encoding="utf-8")
            expected_path.write_text(json.dumps(expected_json(), ensure_ascii=False, indent=2), encoding="utf-8")

            result = evaluate_tool.evaluate_files(parsed_path, expected_path)

            self.assertEqual(result["overall_status"], "FAIL")
            self.assertLess(result["summary"]["pass_rate"], 1)
            self.assertIn("failed_groups", result["summary"])
            self.assertIn("group_summary", result["summary"])
            self.assertIn("top_failed_fields", result["summary"])
            self.assertIn("p0_9", result["summary"])
            self.assertIn("blockers", result["summary"])
            self.assertIn("next_action", result["summary"])
            self.assertIn("character", result["summary"]["group_summary"])
            self.assertIn("drive_discs", result["summary"]["group_summary"])
            self.assertGreater(result["summary"]["failed"], 0)
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())
            failed_paths = {item["path"] for item in result["comparisons"] if item["status"] == "FAIL"}
            self.assertIn("character.name", failed_paths)
            self.assertIn("skill_levels[5].level", failed_paths)
            self.assertIn("equipment.name", failed_paths)

    def test_p0_9_fails_when_character_all_wrong_even_if_rate_is_high(self) -> None:
        parsed = expected_json()
        expected = expected_json()
        parsed["extracted_draft"]["character"] = {
            "name": field(""),
            "level": field(""),
            "rank": field(""),
        }

        result = evaluate_tool.evaluate(parsed, expected)

        self.assertGreaterEqual(result["summary"]["pass_rate"], 0.8)
        self.assertFalse(result["summary"]["p0_9"]["meets_p0_9_standard"])
        self.assertIn("character fields all failed", result["summary"]["p0_9"]["blockers"])

    def test_numeric_text_is_loose_but_percent_unit_is_strict(self) -> None:
        parsed = parsed_json(name="星见雅", skill_5="10")
        parsed["extracted_draft"]["character"]["rank"] = field("S")
        parsed["extracted_draft"]["equipment"]["name"] = field("幻变魔方")
        parsed["extracted_draft"]["equipment"]["rank"] = field("S")
        expected = json.loads(json.dumps(parsed, ensure_ascii=False))
        expected["extracted_draft"]["skill_levels"][1]["level"] = field("8")

        result = evaluate_tool.evaluate(parsed, expected)

        skill_2 = next(item for item in result["comparisons"] if item["path"] == "skill_levels[2].level")
        self.assertEqual(skill_2["status"], "PASS")

        expected["extracted_draft"]["stats"]["crit_rate"] = field("45.8")
        result = evaluate_tool.evaluate(parsed, expected)
        crit_rate = next(item for item in result["comparisons"] if item["path"] == "stats.crit_rate")
        self.assertEqual(crit_rate["status"], "FAIL")

    def test_sub_stats_compare_enhancement_without_internal_parser_fields(self) -> None:
        parsed = parsed_json(name="星见雅", skill_5="10")
        expected = expected_json()
        actual_sub_stats = [
            {"stat": "防御力", "value": "45", "enhancement": 2, "uncertain": False, "evidence": ["防御力", "+2", "45"]},
            {"stat": "暴击伤害", "value": "14.4%", "enhancement": 2, "uncertain": False, "evidence": ["暴击伤害", "+2", "14.4%"]},
        ]
        expected_sub_stats = [
            {"stat": "防御力", "value": "45", "enhancement": 2},
            {"stat": "暴击伤害", "value": "14.4%", "enhancement": 2},
        ]
        parsed["extracted_draft"]["drive_discs"][0]["sub_stats"] = field(actual_sub_stats)
        expected["extracted_draft"]["drive_discs"][0]["sub_stats"] = expected_sub_stats

        result = evaluate_tool.evaluate(parsed, expected)

        disc_1_sub_stats = next(item for item in result["comparisons"] if item["path"] == "drive_discs[1].sub_stats")
        self.assertEqual(disc_1_sub_stats["status"], "PASS")

    def test_make_expected_template_outputs_only_acceptance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_path = root / "parsed.json"
            output_path = root / "expected.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False, indent=2), encoding="utf-8")

            result = template_tool.make_template(parsed_path, output_path)
            template = json.loads(Path(result["output_json"]).read_text(encoding="utf-8"))

            self.assertIn("extracted_draft", template)
            self.assertNotIn("text_blocks", template)
            self.assertNotIn("layout_regions", template)
            draft = template["extracted_draft"]
            self.assertEqual(draft["character"]["name"], "")
            self.assertEqual(set(draft["stats"]), {
                "hp",
                "atk",
                "def",
                "impact",
                "crit_rate",
                "crit_dmg",
                "anomaly_mastery",
                "anomaly_proficiency",
                "pen",
                "energy_regen",
                "physical_dmg_bonus",
            })
            self.assertEqual(draft["skill_levels"][0], {"slot": 1, "level": ""})
            self.assertEqual(draft["drive_discs"][0], {"slot": 1, "level": "", "main_stat": "", "sub_stats": []})

    def test_matrix_runner_outputs_summary_for_vision_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            expected_path = root / "expected.json"
            output_root = root / "matrix"
            Image.new("RGB", (1000, 1400), "white").save(image_path)
            expected_path.write_text(json.dumps(expected_json(), ensure_ascii=False, indent=2), encoding="utf-8")

            result = matrix_tool.run_matrix(
                image_path=image_path,
                expected_path=expected_path,
                output_root=output_root,
                engines=["vision_baseline"],
                game="zzz",
                layout="zzz-agent-card",
                write_crops=False,
            )

            self.assertTrue(Path(result["summary_json"]).exists())
            self.assertTrue(Path(result["summary_md"]).exists())
            self.assertEqual(result["experiments"][0]["engine"], "vision-baseline")
            self.assertIn("failed_groups", result["experiments"][0])

    def test_replay_batch_outputs_average_and_case_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "batch"
            cases = []
            for index in range(3):
                parsed_path = root / f"parsed_{index}.json"
                expected_path = root / f"expected_{index}.json"
                parsed_path.write_text(json.dumps(expected_json(), ensure_ascii=False, indent=2), encoding="utf-8")
                expected_path.write_text(json.dumps(expected_json(), ensure_ascii=False, indent=2), encoding="utf-8")
                cases.append({"name": f"case_{index}", "parsed": str(parsed_path), "expected": str(expected_path)})

            result = batch_tool.run_batch(cases, output_dir=output_dir)

            self.assertTrue(Path(result["summary_json"]).exists())
            self.assertTrue(Path(result["summary_md"]).exists())
            self.assertEqual(result["p0_9"]["case_count"], 3)
            self.assertEqual(result["p0_9"]["average_pass_rate_percent"], 100.0)
            self.assertTrue(result["p0_9"]["meets_p0_9_batch_standard"])


if __name__ == "__main__":
    unittest.main()
