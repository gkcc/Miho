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

        self.assertEqual(workflow["schema_version"], "p4.2-miyoushe-official-export-workflow")
        self.assertTrue(workflow["official_ui_only"])
        self.assertEqual(validation["status"], "ready_for_calibration")
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
            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["validation"]["status"], "ready_for_calibration")
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("米游社官方分享图一键更新练度", html)
            self.assertIn("不自动登录", html)
            self.assertIn("保存官方分享图", html)
            self.assertIn("解析保存后的分享图", html)


if __name__ == "__main__":
    unittest.main()
