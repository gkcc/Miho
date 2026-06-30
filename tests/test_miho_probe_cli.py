from __future__ import annotations

import argparse
import contextlib
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


class MihoProbeCliTests(unittest.TestCase):
    def test_top_level_help_is_user_facing_chinese_menu(self) -> None:
        help_text = cli_tool.render_user_help()

        self.assertIn("MihoProbe 本地体验入口", help_text)
        self.assertIn("打开已有 Dashboard，不跑 OCR", help_text)
        self.assertIn("MihoProbe.exe update", help_text)
        self.assertIn("一键更新练度", help_text)
        self.assertIn("识别 figs\\ 下新增或变更的官方分享图", help_text)
        self.assertIn("用 expected diff 验收解析准确率", help_text)
        self.assertIn("MihoProbe.exe ask-gpt", help_text)
        self.assertIn("生成给右侧 GPT 的固定审查包", help_text)
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
            self.assertIn("只想验收界面", html)
            self.assertIn("识别新分享图", html)
            self.assertIn("MihoProbe.exe fresh", html)
            self.assertIn("MihoProbe.exe replay --no-open", html)
            self.assertIn("默认入口不会跑 OCR", html)
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

    def test_parser_has_gpt_review_entry(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["gpt-review", "--focus", "验收入口太慢", "--no-git-status"])

        self.assertEqual(args.handler, cli_tool.run_gpt_review)
        self.assertEqual(args.focus, "验收入口太慢")
        self.assertTrue(args.no_git_status)

    def test_parser_has_user_facing_ask_gpt_alias(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["ask-gpt", "--focus", "验收入口太慢", "--no-git-status"])

        self.assertEqual(args.handler, cli_tool.run_gpt_review)
        self.assertEqual(args.command, "ask-gpt")
        self.assertEqual(args.focus, "验收入口太慢")
        self.assertTrue(args.no_git_status)

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
            self.assertIn("fresh_mode: new_or_changed_only", output.getvalue())

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
            self.assertIn("不会自动操作米游社 APP", output.getvalue())

    def test_run_gpt_review_writes_compact_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "review_prompt.md"
            result = cli_tool.run_gpt_review(
                argparse.Namespace(
                    focus="修评级识别",
                    evidence=["226 tests OK"],
                    changed_file=["tools/probes/export_image_parse_probe.py: rank source"],
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

    def test_detect_project_root_points_to_workspace(self) -> None:
        self.assertEqual(cli_tool.detect_project_root(), PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
