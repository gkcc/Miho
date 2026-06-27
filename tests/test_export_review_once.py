from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "review_export_image.py"

spec = importlib.util.spec_from_file_location("review_export_image", SCRIPT_PATH)
assert spec is not None
review_once = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = review_once
spec.loader.exec_module(review_once)


class ExportReviewOnceTests(unittest.TestCase):
    def test_one_command_review_generates_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            output_dir = root / "parsed"
            Image.new("RGB", (1000, 1400), "white").save(image_path)

            result = review_once.run_review(
                image_path=image_path,
                output_dir=output_dir,
                engine="none",
                lang="eng",
                game="zzz",
                layout="zzz-agent-card",
            )

            self.assertEqual(result["review_status"], "FAIL")
            self.assertEqual(result["coverage_level"], "low")
            self.assertTrue(Path(result["json_path"]).exists())
            self.assertTrue(Path(result["markdown_path"]).exists())
            self.assertTrue(Path(result["review_html"]).exists())
            self.assertTrue(Path(result["overlay_png"]).exists())
            self.assertIn("start", result["open_command"])

    def test_one_command_review_can_replay_existing_text_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "share.png"
            replay_path = root / "old.json"
            output_dir = root / "parsed"
            Image.new("RGB", (1000, 2000), "white").save(image_path)
            replay_path.write_text(
                json.dumps(
                    {
                        "metadata": {"ocr_engine": "paddle", "lang": "ch"},
                        "image": {"width": 1000, "height": 2000, "mode": "RGB", "format": "PNG"},
                        "layout_regions": [
                            {
                                "name": region.name,
                                "box": review_once.parse_probe.ratio_box_to_pixels(region.box_ratio, 1000, 2000),
                                "preprocess": {"engine_used": "paddle"},
                                "text": "",
                                "text_block_count": 0,
                            }
                            for region in review_once.parse_probe.ZZZ_AGENT_CARD_REGIONS
                        ],
                        "text_blocks": [
                            {
                                "text": "星见雅 LV.60 S",
                                "region": "character_card",
                                "box": {"left": 70, "top": 260, "width": 150, "height": 30},
                                "confidence": 0.95,
                                "candidate_entities": ["unknown"],
                                "uncertain": False,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = review_once.run_review(
                image_path=image_path,
                output_dir=output_dir,
                engine="paddle",
                lang="chi_sim+eng",
                game="zzz",
                layout="zzz-agent-card",
                replay_parsed=replay_path,
            )

            self.assertTrue(Path(result["json_path"]).exists())
            self.assertTrue(Path(result["review_html"]).exists())
            self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
