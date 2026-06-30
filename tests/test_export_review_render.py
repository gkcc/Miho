from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "render_export_review.py"

spec = importlib.util.spec_from_file_location("render_export_review", SCRIPT_PATH)
assert spec is not None
review = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = review
spec.loader.exec_module(review)


def parsed_field(value=None, *, uncertain: bool = False, source_region: str | None = None) -> dict:
    if value is None:
        uncertain = True
    return {
        "value": value,
        "uncertain": uncertain,
        "evidence": [] if value is None else [str(value)],
        "source_region": source_region,
    }


def mock_layout_regions() -> list[dict]:
    names = [
        "header",
        "character_card",
        "character_rank",
        "core_stats",
        "skill_levels",
        "equipment",
        "equipment_rank",
        "drive_disc_1",
        "drive_disc_2",
        "drive_disc_3",
        "drive_disc_4",
        "drive_disc_5",
        "drive_disc_6",
    ]
    regions = []
    for index, name in enumerate(names):
        left = 20 + (index % 3) * 300
        top = 20 + (index // 3) * 220
        regions.append(
            {
                "name": name,
                "description": name,
                "box": {
                    "left": left,
                    "top": top,
                    "right": left + 240,
                    "bottom": top + 160,
                    "width": 240,
                    "height": 160,
                },
                "text": name,
                "text_block_count": 1,
            }
        )
    return regions


def mock_parsed_json(image_path: Path) -> dict:
    drive_discs = []
    for slot in range(1, 7):
        drive_discs.append(
            {
                "slot": slot,
                "set_name": parsed_field(f"套装{slot}", source_region=f"drive_disc_{slot}"),
                "level": parsed_field("15", source_region=f"drive_disc_{slot}"),
                "main_stat": parsed_field("暴击率 24%", source_region=f"drive_disc_{slot}"),
                "sub_stats": parsed_field(
                    [{"stat": "攻击力", "value": "219", "enhancement": 2, "uncertain": False, "evidence": ["攻击力", "+2", "219"]}],
                    source_region=f"drive_disc_{slot}",
                ),
            }
        )
    drive_discs[2]["main_stat"] = parsed_field(source_region="drive_disc_3")

    return {
        "metadata": {
            "probe": "export_image_parse_probe",
            "created_at": "2026-06-27T19:10:00+08:00",
            "input_image": str(image_path),
            "ocr_engine": "auto",
            "game": "zzz",
            "layout": "zzz-agent-card",
        },
        "image": {"width": 1000, "height": 1400, "mode": "RGB", "format": "PNG"},
        "layout_regions": mock_layout_regions(),
        "coverage_summary": {
            "matched_fields": ["character_level", "hp", "drive_disc_sets"],
            "missing_fields": ["equipment_name", "drive_disc_main_stats"],
            "numeric_fields_detected": [{"field": "character_level", "value": "60"}],
            "chinese_fields_detected": [],
            "coverage_level": "medium",
            "recommendation": "继续人工验收 fixed-region overlay。",
        },
        "extracted_draft": {
            "game": "zzz",
            "source_type": "official_export_image",
            "character": {
                "name": parsed_field("星见雅", source_region="character_card"),
                "level": parsed_field("60", source_region="character_card"),
                "rank": parsed_field("S", source_region="character_card"),
            },
            "stats": {
                "hp": parsed_field("17398", source_region="core_stats"),
                "atk": parsed_field("2194", source_region="core_stats"),
                "def": parsed_field("870", source_region="core_stats"),
                "impact": parsed_field("116", source_region="core_stats"),
                "crit_rate": parsed_field("45.8%", source_region="core_stats"),
                "crit_dmg": parsed_field("85.2%", source_region="core_stats"),
                "anomaly_mastery": parsed_field("120", source_region="core_stats"),
                "anomaly_proficiency": parsed_field("118", source_region="core_stats"),
                "pen": parsed_field("0", source_region="core_stats"),
                "energy_regen": parsed_field("1.2", uncertain=True, source_region="core_stats"),
                "physical_dmg_bonus": parsed_field(source_region="core_stats"),
            },
            "skill_levels": [
                {"slot": 1, "level": parsed_field("10", source_region="skill_levels")},
                {"slot": 2, "level": parsed_field("08", source_region="skill_levels")},
                {"slot": 3, "level": parsed_field("06", source_region="skill_levels")},
                {"slot": 4, "level": parsed_field("11", source_region="skill_levels")},
                {"slot": 5, "level": parsed_field("10", source_region="skill_levels")},
                {"slot": 6, "level": parsed_field(source_region="skill_levels")},
            ],
            "equipment": {
                "name": parsed_field(source_region="equipment"),
                "level": parsed_field("60", source_region="equipment"),
                "rank": parsed_field("S", source_region="equipment"),
            },
            "drive_discs": drive_discs,
            "warnings": [],
            "uncertain": True,
        },
        "text_blocks": [
            {
                "text": "S",
                "region": "character_rank",
                "visual_rank_fallback": True,
                "visual_rank_scores": {"orange": 0.1364, "purple": 0.0106, "orange_peak": 0.42, "purple_peak": 0.03},
                "visual_rank_method": "color_ratio_with_local_peak",
                "visual_rank_reason": "orange_global",
                "visual_rank_confidence": 0.91,
            },
            {
                "text": "S",
                "region": "equipment_rank",
                "visual_rank_fallback": True,
                "visual_rank_scores": {"orange": 0.1187, "purple": 0.0, "orange_peak": 0.38, "purple_peak": 0.0},
                "visual_rank_method": "color_ratio_with_local_peak",
                "visual_rank_reason": "orange_global",
                "visual_rank_confidence": 0.88,
            },
        ],
        "errors": [],
    }


def failed_review_json(image_path: Path) -> dict:
    parsed = mock_parsed_json(image_path)
    parsed["coverage_summary"]["coverage_level"] = "high"
    parsed["coverage_summary"]["recommendation"] = "字段覆盖较完整，可以继续做人工确认页和 fixture 回放；仍不要直接写正式数据库。"
    parsed["coverage_summary"]["missing_fields"] = ["character_name", "rank", "drive_disc_main_stats", "drive_disc_sub_stats"]
    draft = parsed["extracted_draft"]
    draft["character"]["name"] = parsed_field(source_region="character_card")
    draft["character"]["rank"] = parsed_field(source_region="character_card")
    draft["equipment"]["name"] = parsed_field("驱动", source_region="equipment")
    for disc in draft["drive_discs"]:
        disc["set_name"] = parsed_field("命中", source_region=f"drive_disc_{disc['slot']}")
        disc["main_stat"] = parsed_field(source_region=f"drive_disc_{disc['slot']}")
        disc["sub_stats"] = parsed_field([], uncertain=True, source_region=f"drive_disc_{disc['slot']}")
    return parsed


class ExportReviewRenderTests(unittest.TestCase):
    def test_render_review_html_and_overlay_from_mock_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            Image.new("RGB", (1000, 1400), "white").save(image_path)

            json_path = root / "share_parsed.json"
            json_path.write_text(json.dumps(mock_parsed_json(image_path), ensure_ascii=False, indent=2), encoding="utf-8")
            md_path = root / "share_parsed.md"
            md_path.write_text("# mock parse\n", encoding="utf-8")

            result = review.render_review(json_path)
            html_path = Path(result["review_html"])
            overlay_path = Path(result["overlay_png"])

            self.assertTrue(html_path.exists())
            self.assertTrue(overlay_path.exists())
            self.assertGreater(overlay_path.stat().st_size, 0)

            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("米游社官方分享图解析验收", html_text)
            self.assertIn("character.level", html_text)
            self.assertIn("coverage_summary", html_text)
            self.assertIn("coverage_level", html_text)
            self.assertIn("覆盖摘要", html_text)
            self.assertIn("FAIL", html_text)
            self.assertIn("low", html_text)
            self.assertIn("驱动盘 1", html_text)
            self.assertIn("drive_disc_1", html_text)
            self.assertIn("角色评级区域 (character_rank)", html_text)
            self.assertIn("音擎评级区域 (equipment_rank)", html_text)
            self.assertIn("评级视觉证据", html_text)
            self.assertIn("固定区域视觉识别，不重新跑 OCR", html_text)
            self.assertIn("橙色占比 0.1364", html_text)
            self.assertIn("橙色局部峰值 0.42", html_text)
            self.assertIn("判定方法：color_ratio_with_local_peak", html_text)
            self.assertIn("理由：orange_global", html_text)
            self.assertIn("置信度：0.91", html_text)
            self.assertIn("攻击力: 219 (+2)", html_text)
            self.assertIn("equipment_name", html_text)

            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("review_html", md_text)
            self.assertIn("overlay_png", md_text)

    def test_render_review_marks_invalid_high_coverage_as_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            Image.new("RGB", (1000, 1400), "white").save(image_path)

            json_path = root / "failed_parsed.json"
            json_path.write_text(json.dumps(failed_review_json(image_path), ensure_ascii=False, indent=2), encoding="utf-8")

            result = review.render_review(json_path)
            html_text = Path(result["review_html"]).read_text(encoding="utf-8")

            self.assertIn("FAIL", html_text)
            self.assertIn("coverage_level", html_text)
            self.assertIn("low", html_text)
            self.assertNotIn("字段覆盖较完整，可以继续做人工确认页", html_text)
            self.assertIn("invalid_candidate", html_text)
            self.assertIn("equipment.name", html_text)
            self.assertIn("驱动", html_text)
            self.assertIn("命中", html_text)


if __name__ == "__main__":
    unittest.main()
