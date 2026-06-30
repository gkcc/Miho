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
parse_tool = batch_tool.parse_probe


def field(value):
    return {"value": value, "uncertain": value is None, "evidence": [], "source_region": "mock"}


def block(text: str, left: int, top: int, width: int = 80, height: int = 30, region: str = "core_stats") -> dict:
    return {
        "text": text,
        "confidence": 1.0,
        "region": region,
        "box": {"left": left, "top": top, "width": width, "height": height, "right": left + width, "bottom": top + height},
    }


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

    def test_core_stats_use_label_value_pairs_before_fixed_zones(self) -> None:
        blocks = [
            block("生命值", 800, 403, 100, 37),
            block("7683", 1118, 380, 77, 33),
            block("11708", 1216, 388, 134, 42),
            block("+4025", 1101, 418, 94, 32),
            block("冲击力", 1491, 518, 98, 38),
            block("134", 1881, 497, 61, 33),
            block("166", 1959, 502, 84, 47),
            block("+32", 1879, 534, 63, 33),
            block("穿透值", 799, 983, 99, 37),
            block("45", 1291, 966, 61, 47),
            block("火属性伤害加成", 1495, 985, 217, 33),
            block("30.0%", 1911, 968, 131, 44),
            block("4166", 1922, 489, 128, 68, "stat_impact"),
        ]

        stats = parse_tool.extract_stats(blocks, 2136, 3566)

        self.assertEqual(stats["hp"]["value"], "11708")
        self.assertEqual(stats["impact"]["value"], "166")
        self.assertEqual(stats["pen"]["value"], "45")
        self.assertEqual(stats["physical_dmg_bonus"]["value"], "30.0%")
        self.assertEqual(stats["impact"]["status"], "ok")

    def test_equipment_name_joins_multiline_hyphen_name_and_rank_alias(self) -> None:
        blocks = [
            block("维序者-特化", 313, 1395, 244, 45, "equipment"),
            block("型", 309, 1461, 49, 52, "equipment"),
            block("LV.50", 324, 1561, 96, 34, "equipment"),
            block("5", 1920, 1457, 42, 59, "equipment_rank"),
        ]

        equipment = parse_tool.extract_equipment(blocks, 2136, 3566)

        self.assertEqual(equipment["name"]["value"], "维序者-特化型")
        self.assertEqual(equipment["rank"]["value"], "S")
        self.assertEqual(equipment["rank"]["source_region"], "equipment_rank")
        self.assertEqual(equipment["level"]["value"], "50")

    def test_drive_disc_main_and_sub_stats_use_row_aliases(self) -> None:
        region = {
            "name": "drive_disc_5",
            "box": {"left": 736, "top": 2406, "right": 1420, "bottom": 3173, "width": 684, "height": 767},
        }
        blocks = [
            block("火属性伤害加成", 783, 2692, 266, 39, "drive_disc_5"),
            block("30%", 1265, 2687, 91, 44, "drive_disc_5"),
            block("暴击伤善", 843, 2805, 136, 26, "drive_disc_5"),
            block("4.8%", 1269, 2791, 86, 37, "drive_disc_5"),
            block("恭击率", 843, 2905, 136, 26, "drive_disc_5"),
            block("+2", 1007, 2901, 40, 30, "drive_disc_5"),
            block("2.4%", 1269, 2891, 86, 37, "drive_disc_5"),
        ]

        disc = parse_tool.extract_drive_discs(blocks, [region])[4]

        self.assertEqual(disc["main_stat"]["value"], "火属性伤害加成 30%")
        self.assertEqual(
            disc["sub_stats"]["value"][:2],
            [
                {"stat": "暴击伤害", "value": "4.8%", "enhancement": None, "uncertain": False, "evidence": ["暴击伤善", "4.8%"]},
                {"stat": "暴击率", "value": "2.4%", "enhancement": 2, "uncertain": False, "evidence": ["恭击率", "+2", "2.4%"]},
            ],
        )

    def test_replay_batch_can_rebuild_from_text_blocks_without_ocr(self) -> None:
        parsed = {
            "metadata": {"game": "zzz", "layout": "zzz-agent-card"},
            "image": {"width": 2136, "height": 3566},
            "layout_regions": [],
            "text_blocks": [
                block("生命值", 800, 403, 100, 37),
                block("11708", 1216, 388, 134, 42),
            ],
            "extracted_draft": {"stats": {"hp": field("wrong")}},
        }

        rebuilt, did_rebuild = batch_tool.rebuild_parsed_from_text_blocks(parsed)

        self.assertTrue(did_rebuild)
        self.assertEqual(rebuilt["extracted_draft"]["stats"]["hp"]["value"], "11708")

    def test_replay_batch_adds_visual_rank_blocks_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            image = Image.new("RGB", (2136, 3566), (20, 20, 20))
            character_box = parse_tool.ratio_box_to_pixels((0.030, 0.100, 0.120, 0.150), 2136, 3566)
            equipment_box = parse_tool.ratio_box_to_pixels((0.825, 0.365, 0.970, 0.455), 2136, 3566)
            for x in range(character_box["left"] + 10, character_box["right"] - 10):
                for y in range(character_box["top"] + 10, character_box["bottom"] - 10):
                    image.putpixel((x, y), (210, 55, 235))
            for x in range(equipment_box["left"] + 16, equipment_box["right"] - 16):
                for y in range(equipment_box["top"] + 16, equipment_box["bottom"] - 16):
                    image.putpixel((x, y), (245, 145, 20))
            image.save(image_path)
            parsed = {
                "metadata": {"game": "zzz", "layout": "zzz-agent-card", "input_image": str(image_path)},
                "image": {"width": 2136, "height": 3566},
                "layout_regions": [],
                "text_blocks": [
                    block("潘引壶 LV.55", 80, 460, 180, 40, "character_card"),
                    block("LV.50", 320, 1560, 90, 30, "equipment"),
                ],
                "extracted_draft": {
                    "character": {"rank": field(None)},
                    "equipment": {"rank": field(None)},
                },
            }

            rebuilt, did_rebuild = batch_tool.rebuild_parsed_from_text_blocks(parsed)

        self.assertTrue(did_rebuild)
        self.assertEqual(rebuilt["extracted_draft"]["character"]["rank"]["value"], "A")
        self.assertEqual(rebuilt["extracted_draft"]["character"]["rank"]["source_region"], "character_rank")
        self.assertEqual(rebuilt["extracted_draft"]["equipment"]["rank"]["value"], "S")
        self.assertEqual(rebuilt["extracted_draft"]["equipment"]["rank"]["source_region"], "equipment_rank")


if __name__ == "__main__":
    unittest.main()
