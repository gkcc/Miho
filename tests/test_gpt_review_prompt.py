from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


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
        self.assertIn("只审本包，不需要读取聊天历史", prompt)
        self.assertIn("Codex 会自行实现、测试、提交和推送", prompt)
        self.assertIn("目标：", prompt)
        self.assertIn("- 让 demo 入口更像软件入口", prompt)
        self.assertIn("- 202 tests OK", prompt)
        self.assertIn("- README.md：增加桌面快捷方式入口", prompt)
        self.assertIn("不读取、打印、保存 cookie/token/stoken/ltoken。", prompt)
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


if __name__ == "__main__":
    unittest.main()
