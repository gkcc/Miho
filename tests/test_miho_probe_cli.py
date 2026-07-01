from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

cli_spec = importlib.util.spec_from_file_location("miho_probe_cli", CLI_SCRIPT_PATH)
assert cli_spec is not None
cli_tool = importlib.util.module_from_spec(cli_spec)
assert cli_spec.loader is not None
sys.modules[cli_spec.name] = cli_tool
cli_spec.loader.exec_module(cli_tool)


def minimal_summary() -> dict:
    return {
        "overall": {
            "case_count": 0,
            "parse_success_count": 0,
            "review_status_counts": {},
            "parse_status_counts": {},
            "expected_status_counts": {},
            "normalized_status_counts": {},
            "import_status_counts": {},
            "demo_status": "READY",
            "average_pass_rate": None,
            "normalized_count": 0,
            "requires_manual_review_count": 0,
            "conclusion": "demo",
        },
        "input": {"source_mode": "manifest controlled mode"},
        "cases": [],
    }


def fill_rect(image, left: int, top: int, right: int, bottom: int, color: tuple[int, int, int]) -> None:
    for x in range(max(0, left), min(image.width, right)):
        for y in range(max(0, top), min(image.height, bottom)):
            image.putpixel((x, y), color)


def draw_mock_rank_glyph(image, box: dict[str, int], rank: str) -> None:
    left = box["left"]
    top = box["top"]
    width = max(1, box["width"])
    height = max(1, box["height"])

    def rect(x1: float, y1: float, x2: float, y2: float, color: tuple[int, int, int]) -> None:
        fill_rect(
            image,
            left + round(width * x1),
            top + round(height * y1),
            left + round(width * x2),
            top + round(height * y2),
            color,
        )

    if rank == "A":
        color = (170, 55, 205)
        rect(0.22, 0.18, 0.34, 0.82, color)
        rect(0.64, 0.18, 0.76, 0.82, color)
        rect(0.34, 0.47, 0.64, 0.60, color)
    else:
        color = (230, 145, 24)
        rect(0.24, 0.18, 0.76, 0.29, color)
        rect(0.24, 0.45, 0.76, 0.56, color)
        rect(0.24, 0.72, 0.76, 0.83, color)
        rect(0.24, 0.29, 0.36, 0.45, color)
        rect(0.64, 0.56, 0.76, 0.72, color)


class MihoProbeCliTests(unittest.TestCase):
    def test_top_level_help_is_user_facing_chinese_menu(self) -> None:
        help_text = cli_tool.render_user_help()

        self.assertIn("MihoProbe 本地体验入口", help_text)
        self.assertIn("打开已有 Dashboard，不跑图片识别", help_text)
        self.assertIn("MihoProbe.exe update", help_text)
        self.assertIn("一键更新练度", help_text)
        self.assertIn("MihoProbe.exe app-export", help_text)
        self.assertIn("官方分享图工作流包", help_text)
        self.assertIn("MihoProbe.exe app-export-calibrate", help_text)
        self.assertIn("捕获米游社窗口网格截图", help_text)
        self.assertIn("MihoProbe.exe app-export-run", help_text)
        self.assertIn("默认 dry-run", help_text)
        self.assertIn("MihoProbe.exe plan-update", help_text)
        self.assertIn("一键更新高难/Tier/配队建议", help_text)
        self.assertIn("MihoProbe.exe box-roster", help_text)
        self.assertIn("脱敏 roster probe", help_text)
        self.assertIn("MihoProbe.exe box-value", help_text)
        self.assertIn("公开 Prydwen meta", help_text)
        self.assertIn("MihoProbe.exe box-status", help_text)
        self.assertIn("只读检查本地 box 图片", help_text)
        self.assertIn("MihoProbe.exe rank-check", help_text)
        self.assertIn("只检查头像/音擎 A/S 艺术字固定区域", help_text)
        self.assertIn("识别 figs\\ 下新增或变更的官方分享图", help_text)
        self.assertIn("用人工对照答案验收解析准确率", help_text)
        self.assertIn("MihoProbe.exe ask-gpt", help_text)
        self.assertIn("生成并复制给右侧 GPT 的固定审查包", help_text)
        self.assertIn("只手动粘贴", help_text)
        self.assertNotIn("positional arguments", help_text)
        self.assertNotIn("Local Miho probe command shell", help_text)

    def test_main_intercepts_top_level_help_before_argparse(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["MihoProbe.exe", "--help"]),
            contextlib.redirect_stdout(output),
        ):
            result = cli_tool.main()

        self.assertEqual(result, 0)
        self.assertIn("MihoProbe 本地体验入口", output.getvalue())
        self.assertIn("MihoProbe.exe update", output.getvalue())
        self.assertIn("MihoProbe.exe fresh", output.getvalue())
        self.assertNotIn("positional arguments", output.getvalue())

    def test_parser_check_path_does_not_import_heavy_workflow_modules(self) -> None:
        lazy_modules = [
            cli_tool.diff_tool,
            cli_tool.gpt_prompt_tool,
            cli_tool.parse_probe,
            cli_tool.app_export_workflow,
            cli_tool.app_export_runner,
            cli_tool.app_export_calibrator,
            cli_tool.normalize_tool,
            cli_tool.planner_tool,
            cli_tool.target_tool,
            cli_tool.dashboard_tool,
            cli_tool.demo_tool,
            cli_tool.box_roster_tool,
            cli_tool.box_value_tool,
        ]
        for lazy_module in lazy_modules:
            lazy_module._module = None

        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["check", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_replay)
        for lazy_module in lazy_modules:
            self.assertIsNone(lazy_module._module)

    def test_dashboard_command_refreshes_legacy_cached_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = root / "demo_summary.json"
            dashboard_path = root / "index.html"
            summary_path.write_text(json.dumps(minimal_summary(), ensure_ascii=False), encoding="utf-8")
            dashboard_path.write_text(
                "<html><body>Brief Warning trusted ready final_brief.md final_brief.json</body></html>",
                encoding="utf-8",
            )

            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(dashboard_path),
                    summary=str(summary_path),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 0)
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("米游社练度识别体验台", html)
            self.assertNotIn("Brief Warning", html)
            self.assertNotIn("trusted ready", html)
            self.assertNotIn("final_brief.md", html)
            self.assertNotIn("final_brief.json", html)

    def test_dashboard_command_injects_cached_rank_check_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = root / "demo_summary.json"
            dashboard_path = root / "index.html"
            rank_check_dir = root / "rank_check"
            rank_check_dir.mkdir(parents=True)
            summary_path.write_text(json.dumps(minimal_summary(), ensure_ascii=False), encoding="utf-8")
            (rank_check_dir / "rank_check.json").write_text(
                json.dumps(
                    {
                        "summary_status": "pass",
                        "recommendation": "评级视觉快检通过：固定 A/S 艺术字区域均有可信颜色信号。",
                        "image_count": 1,
                        "region_count": 2,
                        "ok_region_count": 2,
                        "review_region_count": 0,
                        "entries": [{"image_name": "1782409461508.jpg", "rank_summary": "角色 S / 音擎 A"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (rank_check_dir / "rank_check.html").write_text("<html>rank check</html>", encoding="utf-8")
            dashboard_path.write_text("<html><body>Brief Warning</body></html>", encoding="utf-8")

            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(dashboard_path),
                    summary=str(summary_path),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 0)
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("评级视觉快检", html)
            self.assertIn("A/S 艺术字区域已通过", html)
            self.assertIn("1782409461508.jpg", html)
            self.assertIn("角色 S / 音擎 A", html)
            self.assertIn("评级快检页", html)
            self.assertIn("评级快检数据", html)

    def test_dashboard_command_injects_cached_app_export_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = root / "demo_summary.json"
            dashboard_path = root / "index.html"
            workflow_dir = root / "app_export_workflow"
            workflow_dir.mkdir(parents=True)
            summary_path.write_text(json.dumps(minimal_summary(), ensure_ascii=False), encoding="utf-8")
            (workflow_dir / "miyoushe_export_workflow.json").write_text(
                json.dumps(
                    {
                        "workflow": {
                            "does_not": ["auto_login", "token_read", "cookie_read", "game_client_control"],
                            "operator_route": {
                                "current_route_status": "calibration_required",
                                "automation_status": "disabled_until_calibrated",
                                "next_command": "python tools/probes/window_screenshot_probe.py --window-title 米游社 --dry-run",
                                "manual_save_to_figs_step": "在米游社官方 UI 保存分享图到 figs。",
                                "update_command": r"dist\MihoProbe.exe update --open",
                                "review_gate": "Dashboard 人工复核通过后，才允许进入本地 accepted roster / 高难建议。",
                                "route_steps": [
                                    {
                                        "label": "4. 本地更新 Dashboard",
                                        "status": "implemented",
                                        "description": "只处理本地官方分享图。",
                                        "command": r"dist\MihoProbe.exe update --open",
                                    }
                                ],
                            },
                        },
                        "validation": {
                            "status": "ready_for_calibration",
                            "warnings": ["4 navigation step(s) still need UIA selector calibration."],
                            "readiness_gate_count": 6,
                            "planned_step_count": 4,
                            "implemented_step_count": 1,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workflow_dir / "miyoushe_export_workflow.html").write_text("<html>workflow</html>", encoding="utf-8")
            (workflow_dir / "miyoushe_app_export_run_report.json").write_text(
                json.dumps(
                    {
                        "status": "needs_coordinates",
                        "operator_status": "saved_images_ready",
                        "status_label": "已有分享图可更新",
                        "headline": "已检测到本地官方分享图；下一步进入一键更新和人工复核。",
                        "next_command": r"dist\MihoProbe.exe update --open",
                        "saved_image_count": 2,
                        "operator_route": [
                            "手动在米游社 APP 保存官方分享图到 figs\\",
                            r"运行 dist\MihoProbe.exe update --open",
                            "Dashboard 人工复核后才进入本地角色库/高难建议",
                        ],
                        "safety_boundary": ["不自动登录", "不读取 token/cookie", "不抓包", "不 UIA", "不自动入库"],
                        "preflight_checks": [
                            {"name": "本地分享图", "status": "ready", "detail": "figs 中检测到 2 张图片。"}
                        ],
                        "validation": {"missing_coordinate_count": 6, "unconfirmed_step_count": 6},
                        "clicked_count": 0,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workflow_dir / "miyoushe_app_export_run_report.html").write_text("<html>run</html>", encoding="utf-8")
            dashboard_path.write_text("<html><body>Brief Warning</body></html>", encoding="utf-8")

            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(dashboard_path),
                    summary=str(summary_path),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 0)
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("一键更新练度准备状态", html)
            self.assertIn("已有分享图可更新", html)
            self.assertIn("已检测到本地官方分享图", html)
            self.assertIn("下一步命令", html)
            self.assertIn("dist\\MihoProbe.exe update --open", html)
            self.assertIn("本地分享图 2", html)
            self.assertIn("手动在米游社 APP 保存官方分享图到 figs\\", html)
            self.assertIn("不自动登录、不读取 token/cookie", html)
            self.assertIn("校准清单状态", html)
            self.assertIn("APP 导出流程页", html)
            self.assertIn("APP 导出预检报告", html)
            self.assertIn("官方 UI 坐标校准", html)
            self.assertIn("仍需", html)
            self.assertNotIn("APP 导出执行报告", html)
            self.assertNotIn("UIA selector calibration", html)
            self.assertNotIn("still need", html)
            self.assertNotIn("official_ui_only", html)

    def test_dashboard_command_treats_old_brief_links_as_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_path = Path(temp_dir) / "index.html"
            dashboard_path.write_text("<html><body>简报 Markdown final_brief.md</body></html>", encoding="utf-8")

            self.assertTrue(cli_tool.has_legacy_dashboard_markup(dashboard_path))

    def test_dashboard_command_refreshes_when_renderer_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = root / "demo_summary.json"
            dashboard_path = root / "index.html"
            summary_path.write_text(json.dumps(minimal_summary(), ensure_ascii=False), encoding="utf-8")
            dashboard_path.write_text("<html><body>米游社练度识别体验台 old cache</body></html>", encoding="utf-8")
            old_time = (PROJECT_ROOT / "tools" / "probes" / "render_demo_dashboard.py").stat().st_mtime - 120
            os.utime(dashboard_path, (old_time, old_time))
            os.utime(summary_path, (old_time - 60, old_time - 60))

            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(dashboard_path),
                    summary=str(summary_path),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 0)
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("米游社练度识别体验台", html)
            self.assertNotIn("old cache", html)

    def test_dashboard_command_refreshes_when_rank_check_report_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary_path = root / "demo_summary.json"
            dashboard_path = root / "index.html"
            rank_check_dir = root / "rank_check"
            rank_check_dir.mkdir(parents=True)
            summary_path.write_text(json.dumps(minimal_summary(), ensure_ascii=False), encoding="utf-8")
            rank_check_json = rank_check_dir / "rank_check.json"
            rank_check_json.write_text(
                json.dumps(
                    {
                        "summary_status": "pass",
                        "recommendation": "评级视觉快检通过：完整解析失败时，可以先相信 A/S 艺术字识别，再检查名称、等级和驱动盘字段。",
                        "image_count": 1,
                        "region_count": 2,
                        "ok_region_count": 2,
                        "review_region_count": 0,
                        "entries": [{"image_name": "1782409461508.jpg", "rank_summary": "角色 S / 音擎 A"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            dashboard_path.write_text("<html><body>米游社练度识别体验台 old rank cache</body></html>", encoding="utf-8")
            renderer_time = (PROJECT_ROOT / "tools" / "probes" / "render_demo_dashboard.py").stat().st_mtime
            os.utime(summary_path, (renderer_time + 30, renderer_time + 30))
            os.utime(dashboard_path, (renderer_time + 60, renderer_time + 60))
            os.utime(rank_check_json, (renderer_time + 90, renderer_time + 90))

            result = cli_tool.run_dashboard(
                argparse.Namespace(
                    dashboard=str(dashboard_path),
                    summary=str(summary_path),
                    refresh=False,
                    open=False,
                )
            )

            self.assertEqual(result, 0)
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("评级视觉快检", html)
            self.assertIn("角色 S / 音擎 A", html)
            self.assertNotIn("old rank cache", html)

    def test_dashboard_command_renders_first_run_page_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dashboard_path = root / "index.html"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_dashboard(
                    argparse.Namespace(
                        dashboard=str(dashboard_path),
                        summary=str(root / "missing_summary.json"),
                        refresh=False,
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            self.assertIn("dashboard_first_run:", output.getvalue())
            self.assertTrue(dashboard_path.exists())
            html = dashboard_path.read_text(encoding="utf-8")
            self.assertIn("MihoProbe 初次启动", html)
            self.assertIn("还没有本地 Dashboard 缓存", html)
            self.assertIn("看软件体验", html)
            self.assertIn("一键更新练度", html)
            self.assertIn("MihoProbe.exe update", html)
            self.assertIn("评级快检", html)
            self.assertIn("MihoProbe.exe rank-check", html)
            self.assertIn("准确率验收", html)
            self.assertIn("MihoProbe.exe check --no-open", html)
            self.assertIn("APP 导出流程", html)
            self.assertIn("MihoProbe.exe app-export", html)
            self.assertIn("图片识别是开发慢路径", html)
            self.assertIn("默认入口不会跑图片识别", html)
            self.assertNotIn("Fresh OCR 是开发慢路径", html)
            self.assertNotIn("Brief Warning", html)

    def test_parser_has_app_like_dashboard_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["dashboard", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_dashboard)
        self.assertFalse(args.open)
        self.assertTrue(str(args.dashboard).endswith("data\\probes\\demo\\index.html") or str(args.dashboard).endswith("data/probes/demo/index.html"))

    def test_parser_has_replay_acceptance_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["replay", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_replay)
        self.assertFalse(args.open)
        self.assertIsNone(args.manifest)

    def test_parser_has_fresh_ocr_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["fresh", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_fresh)
        self.assertFalse(args.open)
        self.assertFalse(args.rescan_all)
        self.assertTrue(str(args.images_dir).endswith("figs"))

    def test_parser_has_user_facing_update_alias(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["update", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_fresh)
        self.assertEqual(args.command, "update")
        self.assertFalse(args.open)
        self.assertTrue(str(args.images_dir).endswith("figs"))

    def test_parser_has_user_facing_check_alias(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["check", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_replay)
        self.assertEqual(args.command, "check")
        self.assertFalse(args.open)

    def test_parser_has_user_facing_plan_update_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["plan-update", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_plan_update)
        self.assertEqual(args.command, "plan-update")
        self.assertFalse(args.open)
        self.assertTrue(str(args.roster_dir).endswith("data\\probes\\roster") or str(args.roster_dir).endswith("data/probes/roster"))

    def test_parser_has_rank_check_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["rank-check", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_rank_check)
        self.assertEqual(args.command, "rank-check")
        self.assertFalse(args.open)
        self.assertTrue(str(args.images_dir).endswith("figs"))

    def test_parser_has_box_roster_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["box-roster", "--image", "data/probes/exported_images/zzz_box.png", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_box_roster)
        self.assertEqual(args.command, "box-roster")
        self.assertEqual(args.image, "data/probes/exported_images/zzz_box.png")
        self.assertFalse(args.open)
        self.assertEqual(args.ocr_scale, 2)

    def test_parser_has_box_value_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(
            [
                "box-value",
                "--box-image",
                "data/probes/exported_images/zzz_box.png",
                "--meta-snapshot",
                "data/probes/meta/zzz_prydwen_meta_all_phases.json",
            ]
        )

        self.assertEqual(args.handler, cli_tool.run_box_value)
        self.assertEqual(args.command, "box-value")
        self.assertEqual(args.box_image, "data/probes/exported_images/zzz_box.png")
        self.assertIsNone(args.roster_json)
        self.assertTrue(str(args.output_dir).endswith("data\\probes\\value\\box_value_pipeline") or str(args.output_dir).endswith("data/probes/value/box_value_pipeline"))

    def test_parser_has_box_status_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["box-status", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_box_status)
        self.assertEqual(args.command, "box-status")
        self.assertFalse(args.open)
        self.assertTrue(str(args.meta_dir).endswith("data\\probes\\meta") or str(args.meta_dir).endswith("data/probes/meta"))

    def test_run_box_status_writes_readiness_page_without_ocr_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            output_dir = root / "status"
            images.mkdir()
            meta.mkdir()
            box.mkdir()
            value.mkdir()
            (images / "zzz_box.png").write_bytes(b"fake")
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_box_status(
                    argparse.Namespace(
                        image_dir=[str(images)],
                        meta_dir=str(meta),
                        box_dir=str(box),
                        value_dir=str(value),
                        output_dir=str(output_dir),
                        max_items=8,
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            status_json = output_dir / "box_value_status.json"
            status_html = output_dir / "box_value_status.html"
            self.assertTrue(status_json.exists())
            self.assertTrue(status_html.exists())
            report = json.loads(status_json.read_text(encoding="utf-8"))
            self.assertEqual(report["readiness"], "ready_for_box_value_from_image")
            self.assertTrue(report["safety"]["no_ocr"])
            self.assertTrue(report["safety"]["no_network"])
            self.assertEqual(report["roster_quality"]["status"], "unknown")
            self.assertEqual(report["roster_quality"]["needs_review_count"], 0)
            self.assertIsNone(report["latest"]["roster_review_markdown"])
            self.assertEqual(report["review_gate"]["status"], "no_roster_probe")
            self.assertEqual(report["review_gate"]["review_markdown_status"], "not_applicable")
            self.assertTrue(report["review_gate"]["blocks_accepted_roster"])
            self.assertIn("box-value", report["next_command"])
            html = status_html.read_text(encoding="utf-8")
            self.assertIn("Box 价值输入检查", html)
            self.assertIn("no_ocr=True", html)
            self.assertIn("roster_quality=unknown", html)
            self.assertIn("roster_needs_review=0", html)
            self.assertIn("review_gate=no_roster_probe", html)
            self.assertIn("review_markdown=not_applicable", html)
            self.assertIn("zzz_box.png", html)
            text = output.getvalue()
            self.assertIn("box_status_scope: local_files_only_no_ocr_no_network", text)
            self.assertIn("box_status_readiness: ready_for_box_value_from_image", text)
            self.assertIn("box_status_freshness: current_or_unknown", text)
            self.assertIn("box_status_source_hash_checked: False", text)
            self.assertIn("box_status_roster_quality: unknown", text)
            self.assertIn("box_status_roster_needs_review_count: 0", text)
            self.assertIn("box_status_review_gate: no_roster_probe", text)
            self.assertIn("box_status_roster_review_markdown: missing", text)

    def test_box_status_prefers_existing_roster_over_rerunning_image_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            for path in (images, meta, box, value):
                path.mkdir()
            (images / "zzz_box.png").write_bytes(b"fake")
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")
            (box / "zzz_box_roster_from_box_image.json").write_text(
                json.dumps({"characters": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            report = cli_tool.build_box_status(
                argparse.Namespace(
                    image_dir=[str(images)],
                    meta_dir=str(meta),
                    box_dir=str(box),
                    value_dir=str(value),
                    max_items=8,
                )
            )

            self.assertEqual(report["readiness"], "ready_for_box_value_from_roster")
            self.assertIn("--roster-json", report["next_command"])
            self.assertNotIn("--box-image", report["next_command"])
            self.assertTrue(report["safety"]["no_ocr"])
            self.assertFalse(report["freshness"]["latest_image_newer_than_roster"])
            self.assertEqual(report["roster_quality"]["status"], "ok")
            self.assertEqual(report["roster_quality"]["needs_review_count"], 0)
            self.assertEqual(report["review_gate"]["status"], "quality_ok_manual_confirmation_required")
            self.assertEqual(report["review_gate"]["review_markdown_status"], "missing")
            self.assertFalse(report["review_gate"]["blocks_accepted_roster"])

    def test_run_box_status_exposes_roster_quality_review_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            output_dir = root / "status"
            for path in (images, meta, box, value):
                path.mkdir()
            (images / "zzz_box.png").write_bytes(b"fake")
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")
            roster_json = box / "zzz_box_roster_from_box_image.json"
            roster_md = box / "zzz_box_roster_from_box_image.md"
            roster_json.write_text(
                json.dumps(
                    {
                        "summary": {"needs_review_count": 1},
                        "agents": [{"name": "青衣", "review_status": "ok"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            roster_md.write_text("# review roster\n", encoding="utf-8")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_box_status(
                    argparse.Namespace(
                        image_dir=[str(images)],
                        meta_dir=str(meta),
                        box_dir=str(box),
                        value_dir=str(value),
                        output_dir=str(output_dir),
                        max_items=8,
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            report = json.loads((output_dir / "box_value_status.json").read_text(encoding="utf-8"))
            self.assertEqual(report["readiness"], "ready_for_box_value_from_roster")
            self.assertEqual(report["next_label"], "可跑价值报告，但 roster 仍需人工复核")
            self.assertEqual(report["roster_quality"]["status"], "needs_review")
            self.assertEqual(report["roster_quality"]["needs_review_count"], 1)
            self.assertEqual(report["latest"]["roster_review_markdown"], str(roster_md))
            self.assertEqual(report["review_gate"]["status"], "needs_manual_review")
            self.assertEqual(report["review_gate"]["review_markdown"], str(roster_md))
            self.assertEqual(report["review_gate"]["review_markdown_status"], "available")
            self.assertTrue(report["review_gate"]["blocks_accepted_roster"])
            html = (output_dir / "box_value_status.html").read_text(encoding="utf-8")
            self.assertIn("roster_quality=needs_review", html)
            self.assertIn("roster_needs_review=1", html)
            self.assertIn("review_gate=needs_manual_review", html)
            self.assertIn("review_markdown=available", html)
            self.assertIn("当前 roster 有 1 个待复核项", html)
            self.assertIn(str(roster_md), html)
            text = output.getvalue()
            self.assertIn("box_status_roster_quality: needs_review", text)
            self.assertIn("box_status_roster_needs_review_count: 1", text)
            self.assertIn("box_status_review_gate: needs_manual_review", text)
            self.assertIn(f"box_status_roster_review_markdown: {roster_md}", text)

    def test_box_status_counts_agent_review_status_when_summary_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            for path in (images, meta, box, value):
                path.mkdir()
            (images / "zzz_box.png").write_bytes(b"fake")
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")
            (box / "zzz_box_roster_from_box_image.json").write_text(
                json.dumps(
                    {"agents": [{"name": "青衣", "review_status": "needs_review"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = cli_tool.build_box_status(
                argparse.Namespace(
                    image_dir=[str(images)],
                    meta_dir=str(meta),
                    box_dir=str(box),
                    value_dir=str(value),
                    max_items=8,
                )
            )

            self.assertEqual(report["roster_quality"]["status"], "needs_review")
            self.assertEqual(report["roster_quality"]["needs_review_count"], 1)
            self.assertEqual(report["review_gate"]["status"], "needs_manual_review")

    def test_box_status_requires_roster_refresh_when_box_image_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            for path in (images, meta, box, value):
                path.mkdir()
            image_path = images / "zzz_box.png"
            roster_path = box / "zzz_box_roster_from_box_image.json"
            meta_path = meta / "zzz_prydwen_meta_all_phases.json"
            image_path.write_bytes(b"new fake image")
            roster_path.write_text(json.dumps({"characters": []}, ensure_ascii=False), encoding="utf-8")
            meta_path.write_text("{}", encoding="utf-8")
            os.utime(roster_path, (1_700_000_000, 1_700_000_000))
            os.utime(image_path, (1_700_000_120, 1_700_000_120))

            report = cli_tool.build_box_status(
                argparse.Namespace(
                    image_dir=[str(images)],
                    meta_dir=str(meta),
                    box_dir=str(box),
                    value_dir=str(value),
                    max_items=8,
                )
            )

            self.assertEqual(report["readiness"], "needs_roster_refresh")
            self.assertEqual(report["freshness"]["status"], "roster_stale_by_mtime")
            self.assertTrue(report["freshness"]["latest_image_newer_than_roster"])
            self.assertIn("box-roster", report["next_command"])
            self.assertIn("--image", report["next_command"])
            self.assertIn("--meta-snapshot", report["next_command"])
            self.assertIn("--no-open", report["next_command"])
            self.assertNotIn("box-value", report["next_command"])

    def test_box_status_uses_source_hash_match_before_mtime_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            for path in (images, meta, box, value):
                path.mkdir()
            image_path = images / "zzz_box.png"
            roster_path = box / "zzz_box_roster_from_box_image.json"
            image_bytes = b"same box image"
            image_path.write_bytes(image_bytes)
            roster_path.write_text(
                json.dumps(
                    {
                        "source": {
                            "image_basename": image_path.name,
                            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                        },
                        "agents": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")
            os.utime(roster_path, (1_700_000_000, 1_700_000_000))
            os.utime(image_path, (1_700_000_120, 1_700_000_120))

            report = cli_tool.build_box_status(
                argparse.Namespace(
                    image_dir=[str(images)],
                    meta_dir=str(meta),
                    box_dir=str(box),
                    value_dir=str(value),
                    max_items=8,
                )
            )

            self.assertEqual(report["readiness"], "ready_for_box_value_from_roster")
            self.assertEqual(report["freshness"]["status"], "source_hash_match")
            self.assertTrue(report["freshness"]["latest_image_newer_than_roster"])
            self.assertTrue(report["freshness"]["source_hash_matches_latest_image"])
            self.assertIn("--roster-json", report["next_command"])
            self.assertNotIn("--box-image", report["next_command"])

    def test_box_status_requires_roster_refresh_when_source_hash_mismatches_latest_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "exported_images"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            for path in (images, meta, box, value):
                path.mkdir()
            image_path = images / "zzz_box.png"
            roster_path = box / "zzz_box_roster_from_box_image.json"
            image_path.write_bytes(b"new box image")
            roster_path.write_text(
                json.dumps(
                    {
                        "source": {
                            "image_basename": image_path.name,
                            "image_sha256": hashlib.sha256(b"old box image").hexdigest(),
                        },
                        "agents": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")
            os.utime(image_path, (1_700_000_000, 1_700_000_000))
            os.utime(roster_path, (1_700_000_120, 1_700_000_120))

            report = cli_tool.build_box_status(
                argparse.Namespace(
                    image_dir=[str(images)],
                    meta_dir=str(meta),
                    box_dir=str(box),
                    value_dir=str(value),
                    max_items=8,
                )
            )

            self.assertEqual(report["readiness"], "needs_roster_refresh")
            self.assertEqual(report["freshness"]["status"], "source_hash_mismatch")
            self.assertFalse(report["freshness"]["latest_image_newer_than_roster"])
            self.assertFalse(report["freshness"]["source_hash_matches_latest_image"])
            self.assertIn("box-roster", report["next_command"])
            self.assertNotIn("box-value", report["next_command"])

    def test_box_status_default_does_not_treat_figs_as_box_overview_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exported = root / "exported_images"
            figs = root / "figs"
            meta = root / "meta"
            box = root / "box"
            value = root / "value"
            for path in (exported, figs, meta, box, value):
                path.mkdir()
            (figs / "character_share.jpg").write_bytes(b"fake character share image")
            (meta / "zzz_prydwen_meta_all_phases.json").write_text("{}", encoding="utf-8")

            with (
                mock.patch.object(cli_tool, "DEFAULT_EXPORTED_IMAGES_DIR", exported),
                mock.patch.object(cli_tool, "DEFAULT_FIGS_DIR", figs),
            ):
                report = cli_tool.build_box_status(
                    argparse.Namespace(
                        image_dir=[],
                        meta_dir=str(meta),
                        box_dir=str(box),
                        value_dir=str(value),
                        max_items=8,
                    )
                )

            self.assertEqual(report["readiness"], "needs_box_image")
            self.assertEqual(report["counts"]["image_candidate_count"], 0)
            self.assertEqual(report["inputs"]["image_dirs"], [str(exported)])
            self.assertNotIn("character_share.jpg", json.dumps(report, ensure_ascii=False))

    def test_run_box_roster_uses_redacted_probe_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "zzz_box.png"
            image.write_bytes(b"fake image placeholder")
            fake_box_tool = mock.Mock()
            fake_box_tool.extract_roster_from_image.return_value = {
                "output_json": str(root / "box" / "zzz_box_roster_from_box_image.json"),
                "output_markdown": str(root / "box" / "zzz_box_roster_from_box_image.md"),
                "summary": {"owned_count": 2, "mapped_count": 2, "needs_review_count": 0},
                "warnings": [],
            }
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool, "DEFAULT_BOX_DIR", root / "box"),
                mock.patch.object(cli_tool, "box_roster_tool", fake_box_tool),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_box_roster(
                    argparse.Namespace(
                        image=str(image),
                        output=None,
                        markdown=None,
                        meta_snapshot=None,
                        ocr_scale=2,
                        min_mindscape_confidence=0.85,
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            call = fake_box_tool.extract_roster_from_image.call_args.kwargs
            self.assertEqual(call["image_path"], image.resolve())
            self.assertEqual(call["output_json"], (root / "box" / "zzz_box_roster_from_box_image.json").resolve())
            self.assertEqual(call["output_markdown"], (root / "box" / "zzz_box_roster_from_box_image.md").resolve())
            text = output.getvalue()
            self.assertIn("box_roster_scope: explicit_local_official_box_image_only", text)
            self.assertIn("box_roster_review_gate: manual_confirmation_required_before_accepted_roster", text)
            self.assertIn("needs_review_count: 0", text)

    def test_run_box_value_delegates_to_pipeline_with_safe_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "zzz_box.png"
            meta = root / "meta.json"
            output_dir = root / "value"
            image.write_bytes(b"fake image placeholder")
            meta.write_text("{}", encoding="utf-8")
            fake_value_tool = mock.Mock()
            fake_value_tool.main.return_value = 0
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool, "box_value_tool", fake_value_tool),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_box_value(
                    argparse.Namespace(
                        box_image=str(image),
                        roster_json=None,
                        roster_output=None,
                        meta_snapshot=str(meta),
                        output_dir=str(output_dir),
                        refresh_meta=False,
                        current_only=True,
                        max_phases=1,
                        timeout=9,
                        request_delay=0.25,
                        box_ocr_scale=3,
                        min_mindscape_confidence=0.8,
                    )
                )

            self.assertEqual(result, 0)
            argv = fake_value_tool.main.call_args.args[0]
            self.assertIn("--box-image", argv)
            self.assertIn(str(image.resolve()), argv)
            self.assertIn("--meta-snapshot", argv)
            self.assertIn(str(meta.resolve()), argv)
            self.assertIn("--current-only", argv)
            self.assertIn("--max-phases", argv)
            self.assertIn("1", argv)
            self.assertIn("--box-ocr-scale", argv)
            self.assertIn("3", argv)
            text = output.getvalue()
            self.assertIn("box_value_scope: local_roster_or_box_image_plus_public_meta", text)
            self.assertIn("box_value_review_gate: image_roster_requires_manual_confirmation_before_accepted_roster", text)

    def test_parser_has_app_export_workflow_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["app-export", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_app_export)
        self.assertEqual(args.command, "app-export")
        self.assertFalse(args.open)
        self.assertTrue(str(args.image_inbox).endswith("figs"))
        self.assertTrue(
            str(args.output_dir).endswith("data\\probes\\demo\\app_export_workflow")
            or str(args.output_dir).endswith("data/probes/demo/app_export_workflow")
        )

    def test_parser_has_app_export_run_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["app-export-run", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_app_export_run)
        self.assertEqual(args.command, "app-export-run")
        self.assertFalse(args.open)
        self.assertFalse(args.execute)
        self.assertFalse(args.confirm_official_ui)
        self.assertTrue(str(args.manifest).endswith("miyoushe_app_export_calibration_template.json"))

    def test_parser_has_app_export_calibrate_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["app-export-calibrate", "--no-capture", "--no-open"])

        self.assertEqual(args.handler, cli_tool.run_app_export_calibrate)
        self.assertEqual(args.command, "app-export-calibrate")
        self.assertFalse(args.open)
        self.assertTrue(args.no_capture)
        self.assertTrue(str(args.manifest).endswith("miyoushe_app_export_calibration_template.json"))

    def test_parser_has_gpt_review_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["gpt-review", "--mode", "progress", "--focus", "验收入口太慢", "--no-git-status"])

        self.assertEqual(args.handler, cli_tool.run_gpt_review)
        self.assertEqual(args.mode, "progress")
        self.assertEqual(args.focus, "验收入口太慢")
        self.assertTrue(args.no_git_status)

    def test_parser_has_user_facing_ask_gpt_alias(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["ask-gpt", "--focus", "验收入口太慢", "--no-git-status"])

        self.assertEqual(args.handler, cli_tool.run_gpt_review)
        self.assertEqual(args.command, "ask-gpt")
        self.assertEqual(args.focus, "验收入口太慢")
        self.assertTrue(args.no_git_status)

    def test_ask_gpt_supports_copy_to_clipboard(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["ask-gpt", "--focus", "验收入口太慢", "--copy", "--no-git-status"])

        self.assertTrue(args.copy)

    def test_replay_uses_default_manifest_only_without_inline_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "replay_manifest.json"
            manifest.write_text(
                json.dumps({"cases": [{"name": "case_a", "parsed": "parsed/a.json", "expected": "expected/a.json"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            old_manifest = cli_tool.DEFAULT_REPLAY_MANIFEST
            cli_tool.DEFAULT_REPLAY_MANIFEST = manifest
            try:
                cases = cli_tool.build_replay_cases(
                    argparse.Namespace(manifest=None, case=None, parsed=None, expected=None)
                )
            finally:
                cli_tool.DEFAULT_REPLAY_MANIFEST = old_manifest

            self.assertEqual(cases[0]["name"], "case_a")
            self.assertTrue(cases[0]["parsed"].endswith("parsed\\a.json") or cases[0]["parsed"].endswith("parsed/a.json"))

    def test_replay_inline_case_does_not_require_default_manifest(self) -> None:
        old_manifest = cli_tool.DEFAULT_REPLAY_MANIFEST
        cli_tool.DEFAULT_REPLAY_MANIFEST = PROJECT_ROOT / "missing_replay_manifest.json"
        try:
            cases = cli_tool.build_replay_cases(
                argparse.Namespace(
                    manifest=None,
                    case=["parsed/a.json=expected/a.json"],
                    parsed=None,
                    expected=None,
                )
            )
        finally:
            cli_tool.DEFAULT_REPLAY_MANIFEST = old_manifest

        self.assertEqual(len(cases), 1)
        self.assertTrue(cases[0]["parsed"].endswith("parsed\\a.json") or cases[0]["parsed"].endswith("parsed/a.json"))

    def test_run_replay_prints_user_facing_acceptance_summary(self) -> None:
        summary = {
            "p0_9": {
                "case_count": 3,
                "average_pass_rate_percent": 88.0,
                "meets_p0_9_batch_standard": True,
                "blockers": [],
            },
            "summary_md": str(PROJECT_ROOT / "data" / "probes" / "replay_batches" / "x" / "export_replay_batch_summary.md"),
            "summary_json": str(PROJECT_ROOT / "data" / "probes" / "replay_batches" / "x" / "export_replay_batch_summary.json"),
        }
        fake_replay_tool = mock.Mock()
        fake_replay_tool.run_batch.return_value = summary
        output = io.StringIO()
        with (
            mock.patch.object(cli_tool, "load_replay_tool", return_value=fake_replay_tool),
            contextlib.redirect_stdout(output),
        ):
            result = cli_tool.run_replay(
                argparse.Namespace(
                    manifest=None,
                    case=["parsed/a.json=expected/a.json"],
                    parsed=None,
                    expected=None,
                    output_dir=None,
                    strict_leading_zero=False,
                    no_rebuild=False,
                    open=False,
                )
            )

        self.assertEqual(result, 0)
        self.assertEqual(fake_replay_tool.run_batch.call_count, 1)
        self.assertIn("准确率验收：通过", output.getvalue())
        self.assertIn("summary_md:", output.getvalue())

    def test_run_replay_missing_manifest_writes_readable_help_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_manifest = cli_tool.DEFAULT_REPLAY_MANIFEST
            old_demo_dir = cli_tool.DEFAULT_DEMO_OUTPUT_DIR
            old_figs_dir = cli_tool.DEFAULT_FIGS_DIR
            old_expected_dir = cli_tool.DEFAULT_EXPECTED_DIR
            cli_tool.DEFAULT_REPLAY_MANIFEST = root / "missing_replay_manifest.json"
            cli_tool.DEFAULT_DEMO_OUTPUT_DIR = root / "demo"
            cli_tool.DEFAULT_FIGS_DIR = root / "figs"
            cli_tool.DEFAULT_EXPECTED_DIR = root / "expected"
            cli_tool.DEFAULT_FIGS_DIR.mkdir()
            (cli_tool.DEFAULT_FIGS_DIR / "sample.jpg").write_bytes(b"not-real-image")
            stderr = io.StringIO()
            stdout = io.StringIO()
            try:
                with (
                    mock.patch.object(cli_tool, "load_replay_tool", side_effect=AssertionError("must not load replay tool")),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    result = cli_tool.run_replay(
                        argparse.Namespace(
                            manifest=None,
                            case=None,
                            parsed=None,
                            expected=None,
                            output_dir=None,
                            strict_leading_zero=False,
                            no_rebuild=False,
                            open=False,
                        )
                    )
            finally:
                cli_tool.DEFAULT_REPLAY_MANIFEST = old_manifest
                cli_tool.DEFAULT_DEMO_OUTPUT_DIR = old_demo_dir
                cli_tool.DEFAULT_FIGS_DIR = old_figs_dir
                cli_tool.DEFAULT_EXPECTED_DIR = old_expected_dir

            self.assertEqual(result, 1)
            html_path = root / "demo" / "accuracy_check_missing_manifest.html"
            self.assertTrue(html_path.exists())
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("准确率验收缺少样例清单", html)
            self.assertIn("缺少 replay manifest", html)
            self.assertIn("figs\\ 分享图", html)
            self.assertIn("先识别这批图片", html)
            self.assertIn("检测到 1 张分享图", html)
            self.assertIn("MihoProbe.exe update", html)
            self.assertIn("先验评级区域", html)
            self.assertIn("MihoProbe.exe rank-check", html)
            self.assertIn("准确率验收：缺少样例清单", stderr.getvalue())
            self.assertIn("help_html:", stderr.getvalue())
            self.assertIn("评级怀疑：先跑 MihoProbe.exe rank-check", stderr.getvalue())
            self.assertEqual(stdout.getvalue(), "")

    def test_run_fresh_processes_new_or_changed_images_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            figs = root / "figs"
            figs.mkdir()
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_fresh(
                    argparse.Namespace(
                        command="fresh",
                        images_dir=str(figs),
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        engine="paddle",
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        rescan_all=False,
                        clean_demo=False,
                        targets=None,
                        state_file=None,
                        history_dir=None,
                        target_source_manifest=None,
                        character_catalog=None,
                        roster_dir=str(root / "roster"),
                        tier_snapshot=None,
                        tier_stale_days=60,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 0)
            kwargs = fake_pipeline.call_args.kwargs
            self.assertEqual(kwargs["images_dir"], figs.resolve())
            self.assertTrue(kwargs["new_only"])
            self.assertFalse(kwargs["open_dashboard"])
            self.assertIn("fresh_scope: saved_official_share_images_only", output.getvalue())
            self.assertIn("图片识别慢路径：正在处理本地分享图", output.getvalue())
            self.assertIn("处理模式：只处理新增或变更图片", output.getvalue())
            self.assertIn("如果停在模型加载", output.getvalue())
            self.assertIn("fresh_start:", output.getvalue())
            self.assertIn("mode=new_or_changed_only", output.getvalue())
            self.assertIn("engine=paddle", output.getvalue())
            self.assertIn("fresh_mode: new_or_changed_only", output.getvalue())
            self.assertIn("fresh_status: done", output.getvalue())

    def test_run_fresh_returns_nonzero_when_pipeline_has_hard_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            figs = root / "figs"
            figs.mkdir()
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
                "overall": {
                    "demo_status": "HAS_PARSE_FAILURE",
                    "hard_failure_count": 1,
                    "review_failed_count": 1,
                    "normalization_failed_count": 0,
                },
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_fresh(
                    argparse.Namespace(
                        command="fresh",
                        images_dir=str(figs),
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        engine="paddle",
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        rescan_all=False,
                        clean_demo=False,
                        targets=None,
                        state_file=None,
                        history_dir=None,
                        target_source_manifest=None,
                        character_catalog=None,
                        roster_dir=str(root / "roster"),
                        tier_snapshot=None,
                        tier_stale_days=60,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 3)
            self.assertIn("hard_failure_count: 1", output.getvalue())
            self.assertIn("fresh_status: failed_with_hard_case_failures", output.getvalue())
            self.assertIn("did not succeed", output.getvalue())

    def test_run_update_prints_safe_scope_before_fresh_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            figs = root / "figs"
            figs.mkdir()
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_fresh(
                    argparse.Namespace(
                        command="update",
                        images_dir=str(figs),
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        engine="paddle",
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        rescan_all=False,
                        clean_demo=False,
                        targets=None,
                        state_file=None,
                        history_dir=None,
                        target_source_manifest=None,
                        character_catalog=None,
                        roster_dir=str(root / "roster"),
                        tier_snapshot=None,
                        tier_stale_days=60,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 0)
            self.assertIn("update_scope: saved_official_share_images_only", output.getvalue())
            self.assertIn("一键更新练度：只读取本地已保存的米游社官方分享图", output.getvalue())
            self.assertIn("不会操作米游社 APP、不会登录、不会读取 token/cookie", output.getvalue())
            self.assertIn("处理模式：只处理新增或变更图片", output.getvalue())
            self.assertIn("no app automation", output.getvalue())
            self.assertIn("update_start:", output.getvalue())
            self.assertIn("mode=new_or_changed_only", output.getvalue())

    def test_run_update_returns_nonzero_when_pipeline_has_hard_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            figs = root / "figs"
            figs.mkdir()
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
                "overall": {
                    "demo_status": "HAS_PARSE_FAILURE",
                    "hard_failure_count": 2,
                    "review_failed_count": 1,
                    "normalization_failed_count": 1,
                },
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_fresh(
                    argparse.Namespace(
                        command="update",
                        images_dir=str(figs),
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        engine="paddle",
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        rescan_all=False,
                        clean_demo=False,
                        targets=None,
                        state_file=None,
                        history_dir=None,
                        target_source_manifest=None,
                        character_catalog=None,
                        roster_dir=str(root / "roster"),
                        tier_snapshot=None,
                        tier_stale_days=60,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 3)
            text = output.getvalue()
            self.assertIn("update_scope: saved_official_share_images_only", text)
            self.assertIn("hard_failure_count: 2", text)
            self.assertIn("review_failed_count: 1", text)
            self.assertIn("normalization_failed_count: 1", text)
            self.assertIn("fresh_status: failed_with_hard_case_failures", text)

    def test_run_update_returns_dependency_code_when_frozen_paddleocr_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            figs = root / "figs"
            figs.mkdir()
            fake_pipeline = mock.Mock()
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool, "is_frozen_runtime", return_value=True),
                mock.patch.object(cli_tool.parse_probe, "load_paddle_dependency", side_effect=RuntimeError("missing paddleocr")),
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_fresh(
                    argparse.Namespace(
                        command="update",
                        images_dir=str(figs),
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        engine="paddle",
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        rescan_all=True,
                        clean_demo=False,
                        targets=None,
                        state_file=None,
                        history_dir=None,
                        target_source_manifest=None,
                        character_catalog=None,
                        roster_dir=str(root / "roster"),
                        tier_snapshot=None,
                        tier_stale_days=60,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 5)
            fake_pipeline.assert_not_called()
            text = output.getvalue()
            self.assertIn("fresh_status: dependency_missing", text)
            self.assertIn("fresh_dependency: paddleocr_unavailable_in_frozen_exe", text)
            self.assertIn("fresh_python_fallback:", text)

    def test_run_plan_update_does_not_run_ocr_and_uses_empty_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_plan_update(
                    argparse.Namespace(
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        clean_demo=False,
                        targets=str(root / "targets.json"),
                        target_source_manifest=None,
                        character_catalog=str(root / "catalog.json"),
                        roster_dir=str(root / "roster"),
                        tier_snapshot=str(root / "tier.json"),
                        tier_stale_days=60,
                        history_dir=None,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 0)
            kwargs = fake_pipeline.call_args.kwargs
            self.assertIsNone(kwargs["images_dir"])
            self.assertIsNone(kwargs["parsed_dir"])
            self.assertTrue(str(kwargs["manifest"]).endswith("plan_update_manifest.json"))
            self.assertEqual(json.loads(Path(kwargs["manifest"]).read_text(encoding="utf-8"))["cases"], [])
            self.assertEqual(kwargs["engine"], "none")
            self.assertFalse(kwargs["open_dashboard"])
            self.assertFalse(kwargs["clean_demo"])
            text = output.getvalue()
            self.assertIn("plan_update_scope: local_roster_targets_tier_only", text)
            self.assertIn("不跑 OCR、不联网、不读取账号", text)
            self.assertIn("plan_update_source_status: needs_accepted_roster", text)
            self.assertIn("plan_update_missing_sources: accepted_roster,endgame_targets,tier_snapshot", text)
            readiness_path = root / "demo" / "plan_update_readiness" / "plan_update_readiness.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            self.assertEqual(readiness["source_status"], "needs_accepted_roster")
            self.assertIn("accepted_roster", readiness["missing_blockers"])
            self.assertEqual(readiness["network_policy"]["status"], "local_only")
            self.assertTrue(readiness["input"]["no_ocr"])
            self.assertTrue(readiness["input"]["no_network"])
            self.assertEqual(readiness["input"]["public_url_count"], 0)
            item_details = {item["id"]: item["detail"] for item in readiness["items"]}
            self.assertIn("不联网", item_details["network_boundary"])

    def test_run_plan_update_readiness_reports_ready_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster_dir = root / "roster"
            roster_dir.mkdir()
            (roster_dir / "roster_index.json").write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "character_count": 1,
                        "characters": [{"name": "星见雅"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            targets_path = root / "targets.json"
            targets_path.write_text(json.dumps({"targets": []}, ensure_ascii=False), encoding="utf-8")
            tier_path = root / "tier.json"
            tier_path.write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_plan_update(
                    argparse.Namespace(
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        clean_demo=False,
                        targets=str(targets_path),
                        target_source_manifest=None,
                        character_catalog=None,
                        roster_dir=str(roster_dir),
                        tier_snapshot=str(tier_path),
                        tier_stale_days=60,
                        history_dir=None,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 0)
            text = output.getvalue()
            self.assertIn("plan_update_source_status: ready_for_local_planning", text)
            self.assertIn("plan_update_missing_sources: none", text)
            readiness_path = root / "demo" / "plan_update_readiness" / "plan_update_readiness.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            self.assertEqual(readiness["source_status"], "ready_for_local_planning")
            self.assertEqual(readiness["missing_blockers"], [])
            statuses = {item["id"]: item["status"] for item in readiness["items"]}
            self.assertEqual(statuses["accepted_roster"], "ready")
            self.assertEqual(statuses["endgame_targets"], "ready")
            self.assertEqual(statuses["tier_snapshot"], "ready")
            self.assertEqual(statuses["character_catalog"], "optional_missing")
            self.assertEqual(statuses["network_boundary"], "ready")
            self.assertEqual(readiness["network_policy"]["status"], "local_only")

    def test_run_plan_update_declares_public_source_manifest_network_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster_dir = root / "roster"
            roster_dir.mkdir()
            (roster_dir / "roster_index.json").write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "character_count": 1,
                        "characters": [{"name": "星见雅"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest_path = root / "source_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.0-public-endgame-source-manifest",
                        "sources": [{"id": "public-news", "url": "https://example.com/endgame.html"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tier_path = root / "tier.json"
            tier_path.write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
            summary = {
                "dashboard_html": str(root / "demo" / "index.html"),
                "summary_json": str(root / "demo" / "demo_summary.json"),
            }
            fake_pipeline = mock.Mock(return_value=summary)
            output = io.StringIO()
            with (
                mock.patch.object(cli_tool.demo_tool, "run_pipeline", fake_pipeline),
                contextlib.redirect_stdout(output),
            ):
                result = cli_tool.run_plan_update(
                    argparse.Namespace(
                        output_dir=str(root / "demo"),
                        expected_dir=str(root / "expected"),
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                        clean_demo=False,
                        targets=None,
                        target_source_manifest=str(manifest_path),
                        character_catalog=None,
                        roster_dir=str(roster_dir),
                        tier_snapshot=str(tier_path),
                        tier_stale_days=60,
                        history_dir=None,
                        daily_stamina=None,
                        horizon_days=None,
                    )
                )

            self.assertEqual(result, 0)
            kwargs = fake_pipeline.call_args.kwargs
            self.assertEqual(kwargs["target_source_manifest"], manifest_path)
            text = output.getvalue()
            self.assertIn("plan_update_network_policy: public_sources_declared", text)
            self.assertIn("只访问 --target-source-manifest 声明的公开 http(s) 来源", text)
            self.assertNotIn("plan_update_note: 不跑 OCR、不联网、不读取账号", text)
            readiness_path = root / "demo" / "plan_update_readiness" / "plan_update_readiness.json"
            readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
            self.assertEqual(readiness["source_status"], "ready_for_local_planning")
            self.assertEqual(readiness["missing_blockers"], [])
            self.assertFalse(readiness["input"]["no_network"])
            self.assertEqual(readiness["input"]["public_url_count"], 1)
            self.assertTrue(readiness["input"]["no_account_read"])
            self.assertEqual(readiness["network_policy"]["status"], "public_sources_declared")
            self.assertTrue(readiness["network_policy"]["uses_public_urls"])
            item_details = {item["id"]: item["detail"] for item in readiness["items"]}
            self.assertIn("公开 http(s) 来源", item_details["network_boundary"])

    def test_run_plan_update_local_source_manifest_stays_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "source_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.0-public-endgame-source-manifest",
                        "sources": [{"id": "saved-html", "input": "saved/endgame.html"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                roster_dir=str(root / "roster"),
                targets=None,
                target_source_manifest=str(manifest_path),
                tier_snapshot=str(root / "tier.json"),
                character_catalog=None,
            )
            manifest = root / "demo" / "plan_update_manifest.json"
            report = cli_tool.build_plan_update_readiness(args, root / "demo", manifest)

            self.assertTrue(report["input"]["no_network"])
            self.assertEqual(report["input"]["public_url_count"], 0)
            self.assertEqual(report["network_policy"]["status"], "local_sources_only")
            self.assertEqual(report["network_policy"]["declared_local_input_count"], 1)
            md = cli_tool.render_plan_update_readiness_markdown(report)
            self.assertIn("- 不联网。", md)
            self.assertIn("- 不读取账号、cookie 或 token。", md)

    def test_run_rank_check_writes_visual_region_report_without_ocr(self) -> None:
        Image = cli_tool.parse_probe.load_image_dependency()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "figs"
            images_dir.mkdir()
            image_path = images_dir / "sample.jpg"
            image = Image.new("RGB", (1000, 1600), (18, 20, 24))
            specs = {spec.name: spec for spec in cli_tool.parse_probe.ZZZ_AGENT_CARD_REGIONS}
            character_box = cli_tool.parse_probe.ratio_box_to_pixels(specs["character_rank"].box_ratio, image.width, image.height)
            equipment_box = cli_tool.parse_probe.ratio_box_to_pixels(specs["equipment_rank"].box_ratio, image.width, image.height)
            draw_mock_rank_glyph(image, character_box, "S")
            draw_mock_rank_glyph(image, equipment_box, "A")
            image.save(image_path)

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_rank_check(
                    argparse.Namespace(
                        images_dir=str(images_dir),
                        output_dir=str(root / "rank_check"),
                        game="zzz",
                        layout="zzz-agent-card",
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            report_path = root / "rank_check" / "rank_check.json"
            html_path = root / "rank_check" / "rank_check.html"
            self.assertTrue(report_path.exists())
            self.assertTrue(html_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["scope"], "visual_rank_regions_only")
            self.assertEqual(report["summary_status"], "pass")
            self.assertIn("评级视觉快检通过", report["recommendation"])
            self.assertNotIn("fallback", report["recommendation"])
            self.assertEqual(report["image_count"], 1)
            self.assertEqual(report["ok_region_count"], 2)
            regions = {item["region"]: item for item in report["entries"][0]["regions"]}
            self.assertEqual(report["entries"][0]["rank_summary"], "角色 S / 音擎 A")
            self.assertEqual(regions["character_rank"]["rank"], "S")
            self.assertEqual(regions["equipment_rank"]["rank"], "A")
            self.assertGreater(regions["character_rank"]["scores"]["orange_shape"], 0)
            self.assertGreater(regions["equipment_rank"]["scores"]["purple_shape"], 0)
            self.assertTrue(Path(regions["character_rank"]["crop"]).exists())
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("评级区域快检", html)
            self.assertIn("评级快检通过", html)
            self.assertIn("识别结论：角色 S / 音擎 A", html)
            self.assertIn("颜色/形状证据", html)
            self.assertIn("不跑 OCR", html)
            self.assertIn("角色评级", html)
            self.assertIn("音擎评级", html)
            self.assertIn("rank_check_scope: visual_rank_regions_only", output.getvalue())
            self.assertIn("rank_check_status: pass", output.getvalue())
            self.assertNotIn("fallback", output.getvalue())

    def test_run_app_export_writes_workflow_package_without_clicking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_app_export(
                    argparse.Namespace(
                        output_dir=str(root / "workflow"),
                        image_inbox=str(root / "figs"),
                        game="zzz",
                        window_title="米游社",
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            json_path = root / "workflow" / "miyoushe_export_workflow.json"
            html_path = root / "workflow" / "miyoushe_export_workflow.html"
            calibration_path = root / "workflow" / "miyoushe_app_export_calibration_template.json"
            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            self.assertTrue(calibration_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["validation"]["status"], "ready_for_calibration")
            self.assertIn("app_export_scope: workflow_package_only", output.getvalue())
            self.assertIn("不自动登录、不读取 token/cookie", output.getvalue())
            self.assertIn("calibration_template_json", output.getvalue())
            self.assertIn("app_export_calibrate_command", output.getvalue())
            self.assertIn("app_export_run_command", output.getvalue())

    def test_run_app_export_calibrate_no_capture_writes_report_without_window_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_app_export_calibrate(
                    argparse.Namespace(
                        manifest=str(root / "workflow" / "miyoushe_app_export_calibration_template.json"),
                        output_dir=str(root / "workflow"),
                        image_inbox=str(root / "figs"),
                        game="zzz",
                        window_title="米游社",
                        grid_size=100,
                        match_index=0,
                        no_capture=True,
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            report_json = root / "workflow" / "miyoushe_app_export_calibration_report.json"
            report_html = root / "workflow" / "miyoushe_app_export_calibration_report.html"
            self.assertTrue(report_json.exists())
            self.assertTrue(report_html.exists())
            report = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "needs_window_capture")
            self.assertIn("app_export_calibration_status: needs_window_capture", output.getvalue())

    def test_run_app_export_run_reports_missing_coordinates_without_clicking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow_result = cli_tool.app_export_workflow.build_package(
                output_dir=root / "workflow",
                image_inbox=root / "figs",
                game="zzz",
                window_title="米游社",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli_tool.run_app_export_run(
                    argparse.Namespace(
                        manifest=str(workflow_result["calibration_template_path"]),
                        output_dir=str(root / "workflow"),
                        match_index=0,
                        execute=False,
                        confirm_official_ui=False,
                        open=False,
                    )
                )

            self.assertEqual(result, 0)
            report_json = root / "workflow" / "miyoushe_app_export_run_report.json"
            report_html = root / "workflow" / "miyoushe_app_export_run_report.html"
            self.assertTrue(report_json.exists())
            self.assertTrue(report_html.exists())
            report = json.loads(report_json.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "needs_coordinates")
            self.assertEqual(report["clicked_count"], 0)
            self.assertIn("app_export_run_status: needs_coordinates", output.getvalue())
            self.assertIn("app_export_run_operator_status: not_calibrated", output.getvalue())
            self.assertIn("app_export_run_status_label: 校准未完成", output.getvalue())
            self.assertIn("app_export_run_next_command: dist\\MihoProbe.exe app-export-calibrate", output.getvalue())
            self.assertIn("app_export_run_execution_plan: 执行前人工核对清单", output.getvalue())
            self.assertIn("app_export_run_click_step_count:", output.getvalue())
            self.assertIn("app_export_run_coordinates_complete: False", output.getvalue())
            self.assertIn("app_export_run_ready_for_execute_command: False", output.getvalue())
            self.assertIn("app_export_run_execute_command: dist\\MihoProbe.exe app-export-run --execute --confirm-official-ui", output.getvalue())
            self.assertIn("app_export_run_route_1: 手动在米游社 APP 保存官方分享图到 figs\\", output.getvalue())
            self.assertIn("app_export_run_safety_boundary: 不自动登录、不读取 token/cookie", output.getvalue())

    def test_run_gpt_review_writes_compact_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "review_prompt.md"
            result = cli_tool.run_gpt_review(
                argparse.Namespace(
                    mode="review",
                    focus="修评级识别",
                    evidence=["226 tests OK"],
                    changed_file=["tools/probes/export_image_parse_probe.py: rank source"],
                    completed=[],
                    commit=None,
                    question=[],
                    constraint=[],
                    no_git_status=True,
                    output=str(output_path),
                )
            )

            self.assertEqual(result, 0)
            prompt = output_path.read_text(encoding="utf-8")
            self.assertIn("给右侧 GPT 的审查包", prompt)
            self.assertIn("- 修评级识别", prompt)
            self.assertIn("- 226 tests OK", prompt)
            self.assertIn("tools/probes/export_image_parse_probe.py：rank source", prompt)
            self.assertIn("Findings：", prompt)

    def test_run_gpt_review_writes_progress_sync_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "progress_prompt.md"
            result = cli_tool.run_gpt_review(
                argparse.Namespace(
                    mode="progress",
                    focus="让右侧 GPT 继续挑下一刀",
                    evidence=["264 tests OK"],
                    changed_file=["tools/probes/miho_probe_cli.py: dependency gate"],
                    completed=["EXE update 缺 OCR 依赖时返回 5"],
                    commit="2628cf6 Gate frozen update on OCR dependency",
                    question=[],
                    constraint=[],
                    no_git_status=True,
                    output=str(output_path),
                    copy=False,
                )
            )

            self.assertEqual(result, 0)
            prompt = output_path.read_text(encoding="utf-8")
            self.assertIn("给右侧 GPT 的进展同步包", prompt)
            self.assertIn("- EXE update 缺 OCR 依赖时返回 5", prompt)
            self.assertIn("- 2628cf6 Gate frozen update on OCR dependency", prompt)
            self.assertIn("- 264 tests OK", prompt)

    def test_run_gpt_review_can_copy_without_dumping_prompt(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(cli_tool.gpt_prompt_tool, "copy_text_to_clipboard", return_value=(True, "mock clipboard")),
            contextlib.redirect_stdout(output),
        ):
            result = cli_tool.run_gpt_review(
                argparse.Namespace(
                    mode="review",
                    focus="修右侧 GPT 流程",
                    evidence=[],
                    changed_file=[],
                    completed=[],
                    commit=None,
                    question=[],
                    constraint=[],
                    no_git_status=True,
                    output=None,
                    copy=True,
                )
            )

        self.assertEqual(result, 0)
        self.assertIn("gpt_review_clipboard: copied", output.getvalue())
        self.assertIn("gpt_review_prompt: clipboard", output.getvalue())
        self.assertIn("gpt_review_send_policy: manual_paste_only", output.getvalue())
        self.assertIn("Codex 不自动操作右侧页面", output.getvalue())
        self.assertNotIn("给右侧 GPT 的审查包", output.getvalue())

    def test_run_gpt_review_copy_fallback_writes_handoff_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_prompt = cli_tool.DEFAULT_GPT_REVIEW_PROMPT
            cli_tool.DEFAULT_GPT_REVIEW_PROMPT = Path(temp_dir) / "gpt_review_prompt.md"
            output = io.StringIO()
            try:
                with (
                    mock.patch.object(cli_tool.gpt_prompt_tool, "copy_text_to_clipboard", return_value=(False, "clipboard locked")),
                    contextlib.redirect_stdout(output),
                ):
                    result = cli_tool.run_gpt_review(
                        argparse.Namespace(
                            mode="review",
                            focus="修右侧 GPT 流程",
                            evidence=[],
                            changed_file=[],
                            completed=[],
                            commit=None,
                            question=[],
                            constraint=[],
                            no_git_status=True,
                            output=None,
                            copy=True,
                        )
                    )
            finally:
                cli_tool.DEFAULT_GPT_REVIEW_PROMPT = old_prompt

            self.assertEqual(result, 0)
            self.assertTrue((Path(temp_dir) / "gpt_review_prompt.md").exists())
            self.assertIn("gpt_review_clipboard: unavailable", output.getvalue())
            self.assertIn("gpt_review_open_command:", output.getvalue())
            self.assertIn("gpt_review_prompt.md", output.getvalue())
            self.assertIn("gpt_review_next:", output.getvalue())
            self.assertIn("gpt_review_send_policy: manual_paste_only", output.getvalue())
            self.assertNotIn("给右侧 GPT 的审查包", output.getvalue())

    def test_detect_project_root_points_to_workspace(self) -> None:
        self.assertEqual(cli_tool.detect_project_root(), PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
