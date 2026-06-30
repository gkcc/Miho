from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "tools" / "probes" / "miyoushe_app_export_runner.py"
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miyoushe_app_export_calibrator.py"

runner_spec = importlib.util.spec_from_file_location("miyoushe_app_export_runner", RUNNER_PATH)
assert runner_spec is not None
runner = importlib.util.module_from_spec(runner_spec)
assert runner_spec.loader is not None
sys.modules[runner_spec.name] = runner
runner_spec.loader.exec_module(runner)

spec = importlib.util.spec_from_file_location("miyoushe_app_export_calibrator", SCRIPT_PATH)
assert spec is not None
calibrator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = calibrator
spec.loader.exec_module(calibrator)


class MiyousheAppExportCalibratorTests(unittest.TestCase):
    def test_no_capture_writes_manifest_and_reader_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = calibrator.calibrate(
                manifest_path=root / "workflow" / "calibration.json",
                output_dir=root / "workflow",
                capture=False,
            )

            report = result["report"]
            self.assertEqual(report["status"], "needs_window_capture")
            self.assertTrue((root / "workflow" / "calibration.json").exists())
            self.assertTrue(result["json_path"].exists())
            self.assertTrue(result["html_path"].exists())
            html = result["html_path"].read_text(encoding="utf-8")
            self.assertIn("米游社导出坐标校准", html)
            self.assertIn("还没有截图", html)
            self.assertIn("需要填入清单的坐标", html)
            self.assertIn("你不需要先填坐标", html)
            self.assertIn("手动在米游社 APP 保存官方分享图", html)
            self.assertIn("坐标到底怎么填", html)
            self.assertIn("窗口相对坐标", html)
            self.assertIn("按钮中心点", html)
            self.assertIn("看不到目标时不要猜", html)

    def test_missing_window_is_visible_without_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = calibrator.build_report(
                manifest_path=root / "calibration.json",
                output_dir=root,
                capture=True,
                window_finder=lambda _title: [],
                window_capture=lambda _window, _out, _grid, _draw: {},
            )

            self.assertEqual(report["status"], "window_missing")
            self.assertIn("打开并登录米游社", report["next_action"])
            self.assertGreater(len(report["tasks"]), 0)

    def test_capture_window_records_grid_screenshot_and_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shot_path = root / "window_grid.png"
            shot_path.write_bytes(b"fake")

            def fake_capture(window: dict, output_dir: Path, grid_size: int, draw_grid: bool) -> dict:
                self.assertEqual(grid_size, 80)
                self.assertTrue(draw_grid)
                return {
                    "image": {"path": str(shot_path), "width": 800, "height": 600, "grid_size": grid_size},
                    "metadata_path": str(output_dir / "window_grid.json"),
                    "window": window,
                }

            result = calibrator.calibrate(
                manifest_path=root / "calibration.json",
                output_dir=root,
                grid_size=80,
                capture=True,
                window_finder=lambda _title: [
                    {"title": "米游社", "rect": {"left": 10, "top": 20, "width": 800, "height": 600}}
                ],
                window_capture=fake_capture,
            )

            report = result["report"]
            self.assertEqual(report["status"], "screenshot_captured")
            self.assertEqual(report["screenshot"]["path"], str(shot_path))
            self.assertEqual(report["screenshot"]["grid_size"], 80)
            self.assertTrue(any(task["status"] == "needs_coordinate" for task in report["tasks"]))
            data = json.loads(result["json_path"].read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "screenshot_captured")
            html = result["html_path"].read_text(encoding="utf-8")
            self.assertIn("窗口网格截图", html)
            self.assertIn("window_grid.png", html)
            self.assertIn("应该点哪里", html)
            self.assertIn("只允许点击米游社官方", html)


if __name__ == "__main__":
    unittest.main()
