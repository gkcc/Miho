from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
import sys
import unittest

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "export_image_parse_probe.py"

spec = importlib.util.spec_from_file_location("export_image_parse_probe", SCRIPT_PATH)
assert spec is not None
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


IMAGE_WIDTH = 1000
IMAGE_HEIGHT = 2000


def ocr_block(text: str, region: str, left: int, top: int, width: int = 48, height: int = 24) -> dict:
    return {
        "text": text,
        "region": region,
        "box": {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        },
        "confidence": 0.95,
        "candidate_entities": ["unknown"],
        "uncertain": False,
    }


def zzz_layout_regions() -> list[dict]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "box": probe.ratio_box_to_pixels(spec.box_ratio, IMAGE_WIDTH, IMAGE_HEIGHT),
            "preprocess": {"engine_used": "mock"},
            "text": "",
            "text_block_count": 0,
        }
        for spec in probe.ZZZ_AGENT_CARD_REGIONS
    ]


class ExportImageExtractTests(unittest.TestCase):
    def test_arg_parser_defaults_to_auto_engine(self) -> None:
        args = probe.build_arg_parser().parse_args(["--image", "example.png"])

        self.assertEqual(args.engine, "auto")

    def test_arg_parser_accepts_crop_output(self) -> None:
        args = probe.build_arg_parser().parse_args(["--image", "example.png", "--write-crops"])

        self.assertTrue(args.write_crops)

    def test_arg_parser_accepts_rapidocr_engine(self) -> None:
        args = probe.build_arg_parser().parse_args(["--image", "example.png", "--engine", "rapidocr"])

        self.assertEqual(args.engine, "rapidocr")

    def test_extract_zzz_agent_card_from_manual_ocr_blocks(self) -> None:
        blocks = [
            ocr_block("星见雅 LV.60 S", "character_card", 70, 260, 150, 30),
            ocr_block("17398", "stat_hp", 600, 220),
            ocr_block("2194", "stat_atk", 930, 220),
            ocr_block("870", "stat_def", 610, 285),
            ocr_block("116", "stat_impact", 930, 285),
            ocr_block("45.8%", "stat_crit_rate", 590, 350),
            ocr_block("85.2%", "stat_crit_dmg", 910, 350),
            ocr_block("120", "stat_anomaly_mastery", 610, 415),
            ocr_block("118", "stat_anomaly_proficiency", 910, 415),
            ocr_block("0", "stat_pen", 590, 480),
            ocr_block("1.2", "stat_energy_regen", 910, 480),
            ocr_block("30%", "stat_physical_dmg_bonus", 590, 550),
            ocr_block("10", "skill_level_1", 370, 650),
            ocr_block("08", "skill_level_2", 460, 650),
            ocr_block("06", "skill_level_3", 545, 650),
            ocr_block("11", "skill_level_4", 635, 650),
            ocr_block("10", "skill_level_5", 720, 650),
            ocr_block("07", "skill_level_6", 810, 650),
            ocr_block("幻变魔方", "equipment", 140, 800, 110, 28),
            ocr_block("LV.60", "equipment_level", 140, 850, 80, 28),
            ocr_block("S", "equipment_rank", 900, 800, 30, 28),
            ocr_block("啄木鸟电音 [1]", "drive_disc_1", 40, 960, 160, 28),
            ocr_block("LV.15", "drive_disc_1", 250, 960, 70, 28),
            ocr_block("暴击率", "drive_disc_1", 50, 1060, 80, 28),
            ocr_block("24%", "drive_disc_1", 250, 1060, 60, 28),
            ocr_block("攻击刀", "drive_disc_1", 50, 1150, 80, 28),
            ocr_block("+2", "drive_disc_1", 160, 1150, 42, 28),
            ocr_block("219", "drive_disc_1", 250, 1150, 60, 28),
        ]

        draft = probe.build_extracted_draft(
            game="zzz",
            layout="zzz-agent-card",
            blocks=blocks,
            layout_regions=zzz_layout_regions(),
            image_info={"width": IMAGE_WIDTH, "height": IMAGE_HEIGHT},
        )

        self.assertEqual(draft["source_type"], "official_export_image")
        self.assertEqual(draft["character"]["name"]["value"], "星见雅")
        self.assertEqual(draft["character"]["level"]["value"], "60")
        self.assertEqual(draft["character"]["rank"]["value"], "S")
        self.assertEqual(draft["stats"]["hp"]["value"], "17398")
        self.assertEqual(draft["stats"]["atk"]["value"], "2194")
        self.assertEqual(draft["stats"]["def"]["value"], "870")
        self.assertEqual(draft["stats"]["crit_rate"]["value"], "45.8%")
        self.assertEqual(draft["stats"]["crit_dmg"]["value"], "85.2%")
        self.assertEqual([item["level"]["value"] for item in draft["skill_levels"]], ["10", "08", "06", "11", "10", "07"])
        self.assertEqual(draft["equipment"]["name"]["value"], "幻变魔方")
        self.assertEqual(draft["equipment"]["level"]["value"], "60")
        self.assertEqual(draft["drive_discs"][0]["set_name"]["value"], "啄木鸟电音")
        self.assertEqual(draft["drive_discs"][0]["main_stat"]["value"], "暴击率 24%")
        self.assertEqual(draft["drive_discs"][0]["sub_stats"]["value"][0]["stat"], "攻击力")
        self.assertEqual(draft["drive_discs"][0]["sub_stats"]["value"][0]["enhancement"], 2)

        coverage = probe.summarize_coverage(draft, blocks)
        self.assertIn("character_level", coverage["matched_fields"])
        self.assertIn("hp", coverage["matched_fields"])
        self.assertIn("equipment_name", coverage["matched_fields"])
        self.assertIn("drive_disc_sub_stats", coverage["matched_fields"])
        self.assertIn(coverage["coverage_level"], {"medium", "high"})

    def test_invalid_candidates_and_missing_drive_stats_force_low_coverage(self) -> None:
        draft = probe.empty_draft("zzz")
        draft["character"]["level"] = probe.field("60", uncertain=False, source_region="character_card")
        for stat_name in probe.ZZZ_STAT_LABELS:
            draft["stats"][stat_name] = probe.field("100", uncertain=False, source_region="core_stats")
        draft["skill_levels"] = [
            {"slot": slot, "level": probe.field("10", uncertain=False, source_region="skill_levels")}
            for slot in range(1, 7)
        ]
        draft["equipment"] = {
            "name": probe.field("驱动", uncertain=False, source_region="equipment"),
            "level": probe.field("60", uncertain=False, source_region="equipment"),
            "rank": probe.field("A", uncertain=False, source_region="equipment"),
        }
        draft["drive_discs"] = [
            {
                "slot": slot,
                "set_name": probe.field("命中", uncertain=False, source_region=f"drive_disc_{slot}"),
                "level": probe.field("15", uncertain=False, source_region=f"drive_disc_{slot}"),
                "main_stat": probe.field(source_region=f"drive_disc_{slot}"),
                "sub_stats": probe.field([], uncertain=True, source_region=f"drive_disc_{slot}"),
            }
            for slot in range(1, 7)
        ]

        coverage = probe.summarize_coverage(draft, [])

        self.assertEqual(draft["equipment"]["name"]["status"], "invalid_candidate")
        self.assertEqual(draft["drive_discs"][0]["set_name"]["status"], "invalid_candidate")
        self.assertEqual(coverage["coverage_level"], "low")
        self.assertIn("equipment_name", coverage["invalid_fields"])
        self.assertIn("drive_disc_sets", coverage["invalid_fields"])
        self.assertIn("drive_disc_main_stats 全缺", coverage["hard_low_reasons"])
        self.assertIn("drive_disc_sub_stats 全缺", coverage["hard_low_reasons"])

    def test_missing_character_name_can_not_be_high(self) -> None:
        draft = probe.empty_draft("zzz")
        draft["character"]["level"] = probe.field("60", uncertain=False, source_region="character_card")
        draft["character"]["rank"] = probe.field("S", uncertain=False, source_region="character_card")
        for stat_name in probe.ZZZ_STAT_LABELS:
            draft["stats"][stat_name] = probe.field("100", uncertain=False, source_region="core_stats")
        draft["skill_levels"] = [
            {"slot": slot, "level": probe.field("10", uncertain=False, source_region="skill_levels")}
            for slot in range(1, 7)
        ]
        draft["equipment"] = {
            "name": probe.field("幻变魔方", uncertain=False, source_region="equipment"),
            "level": probe.field("60", uncertain=False, source_region="equipment"),
            "rank": probe.field("S", uncertain=False, source_region="equipment"),
        }
        draft["drive_discs"] = [
            {
                "slot": slot,
                "set_name": probe.field(f"套装{slot}", uncertain=False, source_region=f"drive_disc_{slot}"),
                "level": probe.field("15", uncertain=False, source_region=f"drive_disc_{slot}"),
                "main_stat": probe.field("暴击率 24%", uncertain=False, source_region=f"drive_disc_{slot}"),
                "sub_stats": probe.field(
                    [{"stat": "攻击力", "value": "219", "uncertain": False, "evidence": ["攻击力", "219"]}],
                    uncertain=False,
                    source_region=f"drive_disc_{slot}",
                ),
            }
            for slot in range(1, 7)
        ]

        coverage = probe.summarize_coverage(draft, [])

        self.assertNotEqual(coverage["coverage_level"], "high")
        self.assertIn("character.name 缺失或不可信", coverage["high_blockers"])

    def test_write_field_crops_outputs_key_field_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            output_dir = root / "parsed"
            crop_dir = root / "crops"
            Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), "white").save(image_path)

            result, exit_code = probe.build_result(
                image_path,
                engine="none",
                lang="eng",
                game="zzz",
                layout="zzz-agent-card",
            )
            json_path, _ = probe.write_outputs(result, output_dir, image_path, write_crops=True, crop_output_dir=crop_dir)

            self.assertEqual(exit_code, 0)
            self.assertTrue(json_path.exists())
            crop_outputs = result["crop_outputs"]
            crop_names = {Path(item["path"]).name for item in crop_outputs}
            self.assertIn("character_name.png", crop_names)
            self.assertIn("stat_hp.png", crop_names)
            self.assertIn("skill_1.png", crop_names)
            self.assertIn("equipment_name.png", crop_names)
            self.assertIn("drive_disc_1_main_stat.png", crop_names)
            self.assertTrue(list(crop_dir.rglob("character_name.png")))
            self.assertTrue(list(crop_dir.rglob("stat_hp.png")))
            self.assertTrue(list(crop_dir.rglob("skill_1.png")))
            self.assertTrue(list(crop_dir.rglob("equipment_name.png")))
            self.assertTrue(list(crop_dir.rglob("drive_disc_1_main_stat.png")))

    def test_paddle_preprocess_profiles_include_p0_8_variants(self) -> None:
        image = Image.new("RGB", (80, 40), "white")

        profiles = probe.preprocess_for_paddle_profiles(image)
        names = {item[1]["profile"] for item in profiles}

        self.assertIn("rgb_original", names)
        self.assertIn("rgb_2x", names)
        self.assertIn("rgb_3x", names)
        self.assertIn("rgb_2x_sharp_contrast", names)

    def test_parse_paddle_v3_result_dicts(self) -> None:
        raw_result = [
            {
                "rec_texts": ["星徽·比利", "LV.60"],
                "rec_scores": [0.98, 0.99],
                "rec_polys": [
                    [[10, 20], [90, 20], [90, 42], [10, 42]],
                    [[12, 50], [70, 50], [70, 72], [12, 72]],
                ],
            }
        ]
        region_box = {"left": 100, "top": 200, "right": 300, "bottom": 400}

        blocks = probe.parse_paddle_blocks(raw_result, region_name="character_card", region_box=region_box, scale=2)

        self.assertEqual([block["text"] for block in blocks], ["星徽·比利", "LV.60"])
        self.assertEqual(blocks[0]["box"]["left"], 105)
        self.assertEqual(blocks[0]["box"]["top"], 210)
        self.assertGreater(blocks[0]["ocr_confidence_raw"], 97)

    def test_parse_drive_disc_sub_stats_by_rows_with_enhancement(self) -> None:
        blocks = [
            ocr_block("攻击刀", "drive_disc_1", 80, 100, 80, 24),
            ocr_block("19", "drive_disc_1", 320, 98, 40, 24),
            ocr_block("防御刀", "drive_disc_1", 80, 180, 80, 24),
            ocr_block("+2", "drive_disc_1", 210, 178, 40, 24),
            ocr_block("45", "drive_disc_1", 320, 178, 40, 24),
            ocr_block("王命值", "drive_disc_1", 80, 260, 80, 24),
            ocr_block("+1", "drive_disc_1", 210, 258, 40, 24),
            ocr_block("9%", "drive_disc_1", 320, 258, 40, 24),
            ocr_block("异吊精通", "drive_disc_1", 80, 340, 90, 24),
            ocr_block("+3", "drive_disc_1", 210, 338, 40, 24),
            ocr_block("36", "drive_disc_1", 320, 338, 40, 24),
            ocr_block("暴击率", "drive_disc_1", 80, 420, 80, 24),
            ocr_block("2.4%", "drive_disc_1", 320, 418, 60, 24),
        ]
        value_zone = {"left": 280, "top": 0, "right": 390, "bottom": 480, "width": 110, "height": 480}

        sub_stats = probe.parse_sub_stats(blocks, value_zone)

        self.assertEqual(
            sub_stats,
            [
                {"stat": "攻击力", "value": "19", "enhancement": None, "uncertain": False, "evidence": ["攻击刀", "19"]},
                {"stat": "防御力", "value": "45", "enhancement": 2, "uncertain": False, "evidence": ["防御刀", "+2", "45"]},
                {"stat": "生命值", "value": "9%", "enhancement": 1, "uncertain": False, "evidence": ["王命值", "+1", "9%"]},
                {"stat": "异常精通", "value": "36", "enhancement": 3, "uncertain": False, "evidence": ["异吊精通", "+3", "36"]},
            ],
        )

    def test_tesseract_eng_route_is_marked_numeric_debug_only(self) -> None:
        result = {
            "metadata": {"notes": [], "game": "zzz", "layout": "zzz-agent-card"},
            "layout_regions": [{"preprocess": {"engine_used": "tesseract"}}],
            "coverage_summary": {"coverage_level": "high", "recommendation": "mock"},
        }

        probe.apply_ocr_route_recommendation(result, engine="tesseract", lang="eng")

        self.assertEqual(result["metadata"]["ocr_route"], "tesseract_eng_numeric_debug_only")
        self.assertEqual(result["coverage_summary"]["coverage_level"], "numeric_only")
        self.assertIn("不可作为可导入解析结果", result["coverage_summary"]["recommendation"])


if __name__ == "__main__":
    unittest.main()
