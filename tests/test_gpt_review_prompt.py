from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_gpt_review_prompt.py"

spec = importlib.util.spec_from_file_location("build_gpt_review_prompt", SCRIPT_PATH)
assert spec is not None
prompt_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = prompt_tool
spec.loader.exec_module(prompt_tool)


class GptReviewPromptTests(unittest.TestCase):
    def test_render_prompt_contains_fixed_sections_and_constraints(self) -> None:
        prompt = prompt_tool.render_prompt(
            focus="让 demo 入口更像软件入口",
            evidence=["202 tests OK"],
            changed_files=["README.md: 增加桌面快捷方式入口"],
            questions=[],
            constraints=[],
            include_git_status=False,
        )

        self.assertIn("给右侧 GPT 的审查包", prompt)
        self.assertIn("使用方式：", prompt)
        self.assertIn("把这份审查包完整发给右侧 GPT", prompt)
        self.assertIn("不让 Codex 自动点右侧页面", prompt)
        self.assertIn("只审本包，不需要读取聊天历史", prompt)
        self.assertIn("不要要求 Codex 自动点击、发送或截图右侧 ChatGPT 页面", prompt)
        self.assertIn("Codex 会自行实现、测试、提交和推送", prompt)
        self.assertIn("目标：", prompt)
        self.assertIn("- 让 demo 入口更像软件入口", prompt)
        self.assertIn("- 202 tests OK", prompt)
        self.assertIn("- README.md：增加桌面快捷方式入口", prompt)
        self.assertIn("不读取、打印、保存 cookie/token/stoken/ltoken。", prompt)
        self.assertIn("不要求 Codex 自动操作右侧 ChatGPT 页面", prompt)
        self.assertIn("Findings：", prompt)
        self.assertIn("Acceptance：", prompt)

    def test_render_prompt_accepts_extra_question_and_constraint(self) -> None:
        prompt = prompt_tool.render_prompt(
            focus="修评级识别",
            evidence=[],
            changed_files=[],
            questions=["评级 crop 是否足够稳定？"],
            constraints=["只验证 3 张 fixture。"],
            include_git_status=False,
        )

        self.assertIn("- 暂无额外证据；以本地仓库和命令输出为准。", prompt)
        self.assertIn("- 暂无已改文件；本轮可能仍在方案审查阶段。", prompt)
        self.assertIn("- 评级 crop 是否足够稳定？", prompt)
        self.assertIn("- 只验证 3 张 fixture。", prompt)

    def test_normalize_changed_files_relativizes_absolute_repo_path(self) -> None:
        absolute = PROJECT_ROOT / "tools" / "probes" / "render_demo_dashboard.py"

        result = prompt_tool.normalize_changed_files([f"{absolute}: 改中文文案"])

        self.assertEqual(result, ["tools/probes/render_demo_dashboard.py：改中文文案"])

    def test_parser_supports_copy_to_clipboard(self) -> None:
        parser = prompt_tool.build_arg_parser()
        args = parser.parse_args(["--focus", "修右侧 GPT 流程", "--copy", "--no-git-status"])

        self.assertTrue(args.copy)
        self.assertTrue(args.no_git_status)

    def test_windows_clipboard_falls_back_to_clip_exe_after_powershell_failure(self) -> None:
        powershell_failed = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=1,
            stdout="",
            stderr="clipboard locked",
        )
        clip_ok = subprocess.CompletedProcess(args=["clip.exe"], returncode=0, stdout="", stderr="")

        with (
            mock.patch.object(prompt_tool.sys, "platform", "win32"),
            mock.patch.object(prompt_tool, "copy_text_to_windows_clipboard", return_value=(False, "OpenClipboard failed")),
            mock.patch.object(prompt_tool.subprocess, "run", side_effect=[powershell_failed, clip_ok]) as run_mock,
        ):
            copied, detail = prompt_tool.copy_text_to_clipboard("给右侧 GPT 的审查包")

        self.assertTrue(copied)
        self.assertEqual(detail, "clip.exe")
        self.assertEqual(run_mock.call_args_list[-1].args[0][0], "clip.exe")

    def test_prompt_file_open_command_is_user_facing_on_windows(self) -> None:
        with mock.patch.object(prompt_tool.sys, "platform", "win32"):
            command = prompt_tool.prompt_file_open_command(Path(r"F:\Workspace\MiYo\data\probes\demo\gpt_review_prompt.md"))

        self.assertEqual(command, r'notepad "F:\Workspace\MiYo\data\probes\demo\gpt_review_prompt.md"')


if __name__ == "__main__":
    unittest.main()
