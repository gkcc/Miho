from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "evaluate_export_parse.py"

spec = importlib.util.spec_from_file_location("evaluate_export_parse", SCRIPT_PATH)
assert spec is not None
evaluate_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = evaluate_tool
spec.loader.exec_module(evaluate_tool)


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
                "crit_rate": field("45.8%"),
                "crit_dmg": field("85.2%"),
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
            self.assertGreater(result["summary"]["failed"], 0)
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())
            failed_paths = {item["path"] for item in result["comparisons"] if item["status"] == "FAIL"}
            self.assertIn("character.name", failed_paths)
            self.assertIn("skill_levels[5].level", failed_paths)
            self.assertIn("equipment.name", failed_paths)


if __name__ == "__main__":
    unittest.main()
