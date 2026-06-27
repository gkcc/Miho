from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
