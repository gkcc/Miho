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
        self.assertIn("MihoProbe.exe app-export", help_text)
        self.assertIn("官方分享图工作流包", help_text)
        self.assertIn("MihoProbe.exe plan-update", help_text)
        self.assertIn("一键更新高难/Tier/配队建议", help_text)
        self.assertIn("MihoProbe.exe rank-check", help_text)
        self.assertIn("只检查头像/音擎 A/S 艺术字固定区域", help_text)
        self.assertIn("识别 figs\\ 下新增或变更的官方分享图", help_text)
        self.assertIn("用 expected diff 验收解析准确率", help_text)
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
            cli_tool.normalize_tool,
            cli_tool.planner_tool,
            cli_tool.target_tool,
            cli_tool.dashboard_tool,
            cli_tool.demo_tool,
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
            self.assertIn("看软件体验", html)
            self.assertIn("一键更新练度", html)
            self.assertIn("MihoProbe.exe update", html)
            self.assertIn("评级快检", html)
            self.assertIn("MihoProbe.exe rank-check", html)
            self.assertIn("准确率验收", html)
            self.assertIn("MihoProbe.exe check --no-open", html)
            self.assertIn("APP 导出流程", html)
            self.assertIn("MihoProbe.exe app-export", html)
            self.assertIn("Fresh OCR 是开发慢路径", html)
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
            self.assertTrue(readiness["input"]["no_ocr"])
            self.assertTrue(readiness["input"]["no_network"])

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
            for x in range(character_box["left"], character_box["right"]):
                for y in range(character_box["top"], character_box["bottom"]):
                    image.putpixel((x, y), (230, 145, 24))
            for x in range(equipment_box["left"], equipment_box["right"]):
                for y in range(equipment_box["top"], equipment_box["bottom"]):
                    image.putpixel((x, y), (170, 55, 205))
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
            self.assertEqual(report["image_count"], 1)
            self.assertEqual(report["ok_region_count"], 2)
            regions = {item["region"]: item for item in report["entries"][0]["regions"]}
            self.assertEqual(regions["character_rank"]["rank"], "S")
            self.assertEqual(regions["equipment_rank"]["rank"], "A")
            self.assertTrue(Path(regions["character_rank"]["crop"]).exists())
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("评级区域快检", html)
            self.assertIn("不跑 OCR", html)
            self.assertIn("角色评级", html)
            self.assertIn("音擎评级", html)
            self.assertIn("rank_check_scope: visual_rank_regions_only", output.getvalue())

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
            self.assertTrue(json_path.exists())
            self.assertTrue(html_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["validation"]["status"], "ready_for_calibration")
            self.assertIn("app_export_scope: workflow_package_only", output.getvalue())
            self.assertIn("不自动登录、不读取 token/cookie", output.getvalue())

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
