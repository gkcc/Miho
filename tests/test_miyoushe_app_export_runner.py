from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miyoushe_app_export_runner.py"

spec = importlib.util.spec_from_file_location("miyoushe_app_export_runner", SCRIPT_PATH)
assert spec is not None
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def filled_manifest() -> dict:
    manifest = runner.build_calibration_template(
        game="zzz",
        window_title="米游社",
        image_inbox=PROJECT_ROOT / "figs",
        manifest_path=PROJECT_ROOT / "data" / "probes" / "demo" / "app_export_workflow" / "miyoushe_app_export_calibration_template.json",
    )
    x = 100
    y = 120
    for step in manifest["steps"]:
        if step.get("action") == "official_ui_click":
            step["x"] = x
            step["y"] = y
            step["confirmed_official_ui"] = True
            step["wait_after_seconds"] = 0
            x += 20
            y += 15
    return manifest


class MiyousheAppExportRunnerTests(unittest.TestCase):
    def test_template_is_safe_and_needs_coordinates(self) -> None:
        manifest = runner.build_calibration_template(
            game="zzz",
            window_title="米游社",
            image_inbox=PROJECT_ROOT / "figs",
            manifest_path=PROJECT_ROOT / "data" / "probes" / "demo" / "app_export_workflow" / "miyoushe_app_export_calibration_template.json",
        )
        validation = runner.validate_manifest(manifest)

        self.assertEqual(manifest["schema_version"], "p4.4-miyoushe-app-export-calibration")
        self.assertTrue(manifest["official_ui_only"])
        self.assertEqual(validation["status"], "needs_coordinates")
        self.assertGreater(validation["missing_coordinate_count"], 0)
        self.assertIn("--execute --confirm-official-ui", manifest["execute_command"])
        for forbidden in (
            "auto_login",
            "credential_input",
            "captcha_bypass",
            "packet_capture",
            "token_read",
            "cookie_read",
            "game_client_control",
            "formal_database_write",
        ):
            self.assertIn(forbidden, manifest["does_not"])

    def test_execute_requires_cli_confirmation_even_when_manifest_is_confirmed(self) -> None:
        manifest = filled_manifest()
        report = runner.build_report(
            manifest_path=PROJECT_ROOT / "calibration.json",
            manifest=manifest,
            execute=True,
            confirm_official_ui=False,
            match_index=0,
            window_finder=lambda _title: [],
            point_resolver=lambda _window, x, y: {"relative": {"x": x, "y": y}, "absolute": {"x": x, "y": y}},
            clicker=lambda _x, _y: None,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("execute_requires_confirm_official_ui_flag", report["validation"]["blockers"])
        self.assertEqual(report["clicked_count"], 0)

    def test_dry_run_resolves_all_coordinates_without_clicking(self) -> None:
        manifest = filled_manifest()
        clicks: list[tuple[int, int]] = []

        report = runner.build_report(
            manifest_path=PROJECT_ROOT / "calibration.json",
            manifest=manifest,
            execute=False,
            confirm_official_ui=False,
            match_index=0,
            window_finder=lambda _title: [{"title": "米游社", "rect": {"left": 10, "top": 20, "width": 800, "height": 600}}],
            point_resolver=lambda _window, x, y: {"relative": {"x": x, "y": y}, "absolute": {"x": x + 10, "y": y + 20}},
            clicker=lambda x, y: clicks.append((x, y)),
        )

        self.assertEqual(report["status"], "ready_for_dry_run")
        self.assertEqual(clicks, [])
        self.assertEqual(len(report["step_results"]), report["validation"]["click_step_count"])
        self.assertTrue(all(step["status"] == "resolved" for step in report["step_results"]))

    def test_execute_clicks_confirmed_official_ui_steps(self) -> None:
        manifest = filled_manifest()
        clicks: list[tuple[int, int]] = []

        report = runner.build_report(
            manifest_path=PROJECT_ROOT / "calibration.json",
            manifest=manifest,
            execute=True,
            confirm_official_ui=True,
            match_index=0,
            window_finder=lambda _title: [{"title": "米游社", "rect": {"left": 10, "top": 20, "width": 800, "height": 600}}],
            point_resolver=lambda _window, x, y: {"relative": {"x": x, "y": y}, "absolute": {"x": x + 10, "y": y + 20}},
            clicker=lambda x, y: clicks.append((x, y)),
        )

        self.assertEqual(report["status"], "executed")
        self.assertEqual(report["clicked_count"], report["validation"]["click_step_count"])
        self.assertEqual(len(clicks), report["validation"]["click_step_count"])

    def test_risky_step_text_blocks_manifest(self) -> None:
        manifest = filled_manifest()
        manifest["steps"][1]["title"] = "输入账号密码登录"
        validation = runner.validate_manifest(manifest)

        self.assertEqual(validation["status"], "blocked")
        self.assertIn("risky_step_text_detected", validation["blockers"])

    def test_run_manifest_writes_json_and_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "calibration.json"
            manifest_path.write_text(
                json.dumps(
                    runner.build_calibration_template(manifest_path=manifest_path, image_inbox=root / "empty_figs"),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = runner.run_manifest(
                manifest_path=manifest_path,
                output_dir=root / "reports",
                execute=False,
                confirm_official_ui=False,
            )

            self.assertTrue(result["json_path"].exists())
            self.assertTrue(result["html_path"].exists())
            report = json.loads(result["json_path"].read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "needs_coordinates")
            self.assertEqual(report["operator_status"], "not_calibrated")
            self.assertEqual(report["status_label"], "校准未完成")
            self.assertIn("app-export-calibrate", report["next_command"])
            self.assertIn("手动在米游社 APP 保存官方分享图到 figs\\", report["operator_route"])
            self.assertIn("不读取 token/cookie", report["safety_boundary"])
            self.assertFalse(report["gates"]["coordinates_complete"])
            self.assertIn("缺坐标", result["html_path"].read_text(encoding="utf-8"))
            html = result["html_path"].read_text(encoding="utf-8")
            self.assertIn("米游社官方分享图预检报告", html)
            self.assertIn("下一步命令", html)
            self.assertIn("推荐路线", html)
            self.assertIn("安全边界", html)

    def test_saved_images_take_operator_route_to_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "figs"
            inbox.mkdir()
            (inbox / "share.png").write_bytes(b"fake")
            manifest_path = root / "calibration.json"
            manifest = runner.build_calibration_template(image_inbox=inbox, manifest_path=manifest_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            result = runner.run_manifest(
                manifest_path=manifest_path,
                output_dir=root / "reports",
                execute=False,
                confirm_official_ui=False,
            )

            report = json.loads(result["json_path"].read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "needs_coordinates")
            self.assertEqual(report["operator_status"], "saved_images_ready")
            self.assertEqual(report["status_label"], "已有分享图可更新")
            self.assertEqual(report["saved_image_count"], 1)
            self.assertEqual(report["next_command"], "dist\\MihoProbe.exe update --open")
            self.assertTrue(report["gates"]["saved_images_detected"])


if __name__ == "__main__":
    unittest.main()
