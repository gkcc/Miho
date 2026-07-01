from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "extract_zzz_box_roster.py"

spec = importlib.util.spec_from_file_location("extract_zzz_box_roster", SCRIPT_PATH)
assert spec is not None
box_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = box_tool
spec.loader.exec_module(box_tool)


def ocr_item(text: str, center_x: float, center_y: float, *, confidence: float = 0.98, scale: int = 2) -> list:
    width = 80
    height = 24
    left = (center_x - width / 2) * scale
    top = (center_y - height / 2) * scale
    right = (center_x + width / 2) * scale
    bottom = (center_y + height / 2) * scale
    return [[[left, top], [right, top], [right, bottom], [left, bottom]], text, confidence]


class ZzzBoxRosterExtractTests(unittest.TestCase):
    def test_assign_blocks_to_slots_maps_name_level_and_review_status(self) -> None:
        width = int(box_tool.REFERENCE_WIDTH)
        height = int(box_tool.REFERENCE_HEIGHT)
        slot = box_tool.build_grid_slots(width, height, 1)[0]
        blocks = [
            box_tool.OcrBlock("青衣", 0.99, slot.center_x - 20, slot.name_y - 10, slot.center_x + 20, slot.name_y + 10),
            box_tool.OcrBlock("LV.60", 0.96, slot.center_x - 20, slot.level_y - 10, slot.center_x + 20, slot.level_y + 10),
        ]

        records = box_tool.assign_blocks_to_slots(
            blocks=blocks,
            slots=[slot],
            aliases=box_tool.build_aliases(None),
            width=width,
            height=height,
        )
        records[1]["mindscape"] = 2
        records[1]["mindscape_confidence"] = 0.91
        records[1]["mindscape_status"] = "ok"

        agent = box_tool.slot_record_to_agent(records[1])

        assert agent is not None
        self.assertEqual(agent["name"], "青衣")
        self.assertEqual(agent["agent_slug"], "qingyi")
        self.assertEqual(agent["level"], 60)
        self.assertEqual(agent["mindscape"], 2)
        self.assertEqual(agent["review_status"], "ok")

    def test_extract_roster_from_image_writes_redacted_probe_outputs(self) -> None:
        width = int(box_tool.REFERENCE_WIDTH)
        height = int(box_tool.REFERENCE_HEIGHT)
        slot = box_tool.build_grid_slots(width, height, 1)[0]
        raw_ocr = [
            ocr_item("招募1名代理人", 200, 120),
            ocr_item("青衣", slot.center_x, slot.name_y),
            ocr_item("LV.60", slot.center_x, slot.level_y),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "box.png"
            output_json = root / "roster.json"
            output_md = root / "roster.md"
            Image.new("RGB", (width, height), (255, 255, 255)).save(image_path)

            with (
                mock.patch.object(box_tool, "run_rapidocr", return_value=raw_ocr),
                mock.patch.object(box_tool, "recognize_mindscape", return_value=(1, 0.93, "ok")),
            ):
                result = box_tool.extract_roster_from_image(
                    image_path=image_path,
                    output_json=output_json,
                    output_markdown=output_md,
                    ocr_scale=2,
                )

            saved = json.loads(output_json.read_text(encoding="utf-8"))
            expected_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            self.assertEqual(saved["schema_version"], "p0.2-zzz-box-roster-image")
            self.assertEqual(saved["summary"]["owned_count"], 1)
            self.assertEqual(saved["summary"]["needs_review_count"], 0)
            self.assertEqual(saved["agents"][0]["agent_slug"], "qingyi")
            self.assertEqual(saved["source"]["image_sha256"], expected_hash)
            self.assertEqual(saved["source"]["image_file_size"], image_path.stat().st_size)
            self.assertEqual(saved["source"]["image_mtime_epoch"], image_path.stat().st_mtime)
            self.assertEqual(saved["recognition"]["count_claim"], 1)
            self.assertEqual(saved["privacy"]["header_uid_persisted"], False)
            self.assertEqual(saved["privacy"]["raw_ocr_blocks_persisted"], False)
            self.assertEqual(saved["privacy"]["cookie_token_read"], False)
            self.assertNotIn("raw_ocr_blocks", saved)
            self.assertIn("ZZZ Box 截图 roster 识别", output_md.read_text(encoding="utf-8"))
            self.assertEqual(result["output_json"], str(output_json))


if __name__ == "__main__":
    unittest.main()
