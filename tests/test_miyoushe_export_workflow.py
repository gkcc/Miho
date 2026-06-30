from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miyoushe_export_workflow.py"

spec = importlib.util.spec_from_file_location("miyoushe_export_workflow", SCRIPT_PATH)
assert spec is not None
workflow_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = workflow_tool
spec.loader.exec_module(workflow_tool)


class MiyousheExportWorkflowTests(unittest.TestCase):
    def test_default_workflow_records_safe_official_ui_boundaries(self) -> None:
        workflow = workflow_tool.build_workflow(
            game="zzz",
            window_title="米游社",
            image_inbox=PROJECT_ROOT / "figs",
        )
        validation = workflow_tool.validate_workflow(workflow)

        self.assertEqual(workflow["schema_version"], "p4.3-miyoushe-official-export-workflow")
        self.assertTrue(workflow["official_ui_only"])
        self.assertEqual(validation["status"], "ready_for_calibration")
        self.assertEqual(workflow["operator_route"]["automation_status"], "disabled_until_calibrated")
        self.assertEqual(workflow["operator_route"]["update_command"], "dist\\MihoProbe.exe update --open")
        self.assertIn("Dashboard 人工复核", workflow["operator_route"]["review_gate"])
        self.assertGreaterEqual(validation["readiness_gate_count"], 6)
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
            self.assertIn(forbidden, workflow["does_not"])
        step_ids = [step["id"] for step in workflow["steps"]]
        self.assertEqual(step_ids[0], "precheck_window")
        self.assertIn("save_share_image", step_ids)
        self.assertIn("parse_saved_image", step_ids)
        self.assertGreater(validation["planned_step_count"], 0)
        self.assertGreaterEqual(validation["calibration_command_count"], 5)
        command_ids = [command["id"] for command in workflow["calibration_commands"]]
        self.assertEqual(command_ids[0], "find_window")
        self.assertIn("capture_grid", command_ids)
        self.assertIn("execute_confirmed_coordinate", command_ids)
        self.assertIn("parse_saved_images", command_ids)
        self.assertTrue(any("--confirm-official-ui" in command["command"] for command in workflow["calibration_commands"]))
        self.assertTrue(any("dist\\MihoProbe.exe update" in command["command"] for command in workflow["calibration_commands"]))
        self.assertTrue(any("app-export-run" in command["command"] for command in workflow["calibration_commands"]))
        self.assertIn("app-export-calibrate", workflow["operator_route"]["calibrate_command"])
        self.assertTrue(any("--open" in command["command"] for command in workflow["calibration_commands"]))
        checklist = "\n".join(workflow["operator_checklist"])
        self.assertIn("不点击登录", checklist)
        self.assertIn("先生成网格截图", checklist)

    def test_build_package_writes_manifest_and_reader_friendly_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = workflow_tool.build_package(
                output_dir=root / "workflow",
                image_inbox=root / "figs",
                game="zzz",
                window_title="米游社",
            )

            json_path = result["json_path"]
            html_path = result["html_path"]
            calibration_path = result["calibration_template_path"]
            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            self.assertTrue(calibration_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["validation"]["status"], "ready_for_calibration")
            self.assertEqual(data["workflow"]["operator_route"]["current_route_status"], "calibration_required")
            calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            self.assertEqual(calibration["schema_version"], "p4.4-miyoushe-app-export-calibration")
            self.assertIn("app-export-run", calibration["dry_run_command"])
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("米游社官方分享图一键更新练度", html)
            self.assertIn("当前还不是自动点击", html)
            self.assertIn("可执行校准清单", html)
            self.assertIn("先生成网格截图", html)
            self.assertIn("app-export-calibrate", html)
            self.assertIn("miyoushe_app_export_calibration_template.json", html)
            self.assertIn("app-export-run", html)
            self.assertIn("官方分享图路线", html)
            self.assertIn("dist\\MihoProbe.exe update --open", html)
            self.assertIn("Dashboard 人工复核", html)
            self.assertIn("Readiness Gates", html)
            self.assertIn("不自动登录", html)
            self.assertIn("操作前检查", html)
            self.assertIn("下一步校准命令", html)
            self.assertIn("window_screenshot_probe.py", html)
            self.assertIn("click_relative_probe.py", html)
            self.assertIn("--confirm-official-ui", html)
            self.assertIn("保存官方分享图", html)
            self.assertIn("解析保存后的分享图", html)
            self.assertNotIn("自动导出已可用", html)


if __name__ == "__main__":
    unittest.main()
