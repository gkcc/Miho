from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReadmeEntrypointTests(unittest.TestCase):
    def test_readme_points_to_existing_user_entrypoints(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        for relative in (
            "scripts/install_miho_demo_shortcut.bat",
            "scripts/build_miho_probe_exe.bat",
            "scripts/build_miho_probe_exe.ps1",
            "packaging/MihoProbe.spec",
            "tools/probes/run_export_replay_batch.py",
            "tools/probes/review_export_image.py",
            "tools/probes/build_gpt_review_prompt.py",
            "tools/probes/README.md",
            "docs/notes/codex-gpt-adversarial-loop.md",
        ):
            self.assertIn(relative, readme)
            self.assertTrue((PROJECT_ROOT / relative).exists(), relative)

    def test_readme_stays_product_facing(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("我只想像软件一样用", readme)
        self.assertIn("先这样用", readme)
        self.assertIn("第一次只做两步", readme)
        self.assertIn("点哪个图标", readme)
        self.assertIn("卡住时先看这里", readme)
        self.assertIn("当前验收怎么看", readme)
        self.assertIn("Dashboard 怎么看", readme)
        self.assertIn("更新和验收", readme)
        self.assertIn("以后日常点桌面图标即可", readme)
        self.assertIn("不要先跑图片识别", readme)
        self.assertIn("Opening cached Dashboard only. Image recognition will NOT run.", readme)
        self.assertIn("如果你等了 30 秒还没有页面", readme)
        self.assertIn("A/S 评级是否稳", readme)
        self.assertIn("颜色/形状证据", readme)
        self.assertIn("如果你只是验收", readme)
        self.assertIn("它会快速失败并给出 Python fallback", readme)
        self.assertIn("不是报错", readme)
        self.assertIn("如果怀疑失败点在评级", readme)
        self.assertIn("绿色才是可继续", readme)
        self.assertIn("查看 APP 导出路线", readme)
        self.assertIn("dist\\MihoProbe.exe app-export", readme)
        self.assertIn("生成 APP 坐标网格", readme)
        self.assertIn("dist\\MihoProbe.exe app-export-calibrate", readme)
        self.assertIn("更新高难配队", readme)
        self.assertIn("dist\\MihoProbe.exe plan-update", readme)
        self.assertIn("排查 A/S 评级", readme)
        self.assertIn("dist\\MihoProbe.exe rank-check", readme)
        self.assertIn("EXE-first 兼容脚本入口", readme)
        self.assertIn("不会自动掉进慢图片识别", readme)
        self.assertIn("不要再让 Codex 反复探索右侧 ChatGPT 页面", readme)
        self.assertNotIn('"entries"', readme)
        self.assertNotIn("tier-stale-days", readme)
        self.assertLess(readme.count("```"), 12)

    def test_demo_launcher_refreshes_old_dashboard_markup(self) -> None:
        launcher = (PROJECT_ROOT / "scripts" / "run_miho_demo.ps1").read_text(encoding="utf-8")

        for marker in (
            "Brief Warning",
            "brief status",
            "trusted ready",
            "pending review",
            "watch only",
            "watch_only",
        ):
            self.assertIn(marker, launcher)

    def test_demo_launcher_default_never_runs_ocr(self) -> None:
        wrapper = (PROJECT_ROOT / "scripts" / "run_miho_demo.bat").read_text(encoding="utf-8")
        launcher = (PROJECT_ROOT / "scripts" / "run_miho_demo.ps1").read_text(encoding="utf-8")
        installer = (PROJECT_ROOT / "scripts" / "install_miho_demo_shortcut.ps1").read_text(encoding="utf-8")

        self.assertIn("dist\\MihoProbe.exe", wrapper)
        self.assertIn("dashboard --open", wrapper)
        self.assertIn("fresh --open", wrapper)
        self.assertIn("Opening cached Dashboard only. Image recognition will NOT run.", wrapper)
        self.assertIn("Image recognition requested. This can be slow", wrapper)
        self.assertIn("For UI acceptance", wrapper)
        self.assertIn("build_miho_probe_exe.bat", wrapper)
        self.assertIn("EXE-first", wrapper)
        self.assertIn("will not fall back to the slow Python image-recognition path by default", wrapper)
        self.assertIn('"%%EXE%%" %%*'.replace("%%", "%"), wrapper)
        self.assertNotIn('powershell -ExecutionPolicy Bypass -File "%~dp0run_miho_demo.ps1" %*', wrapper)
        self.assertIn("Miho Legacy Demo Launcher", launcher)
        self.assertIn("Product entry: dist\\MihoProbe.exe dashboard --open", launcher)
        self.assertIn("It never runs OCR automatically.", launcher)
        self.assertIn("This shortcut does not run OCR automatically.", launcher)
        self.assertIn("scripts\\run_miho_demo.bat --fresh only", launcher)
        self.assertIn("Running fresh OCR", launcher)
        self.assertIn("never reruns OCR automatically", installer)
        self.assertNotIn("or run fresh OCR if no dashboard exists", installer)

    def test_shortcut_installer_exposes_app_like_exe_entry(self) -> None:
        installer = (PROJECT_ROOT / "scripts" / "install_miho_demo_shortcut.ps1").read_text(encoding="utf-8")
        opener = (PROJECT_ROOT / "scripts" / "open_miho_probe_cli.bat").read_text(encoding="utf-8")

        self.assertIn('-Name "MihoProbe"', installer)
        self.assertIn("dist\\MihoProbe.exe", installer)
        self.assertIn("dashboard --open", installer)
        self.assertIn('-Name "MihoProbe App Export Workflow"', installer)
        self.assertIn("app-export --open", installer)
        self.assertIn('-Name "MihoProbe App Export Calibrate"', installer)
        self.assertIn("app-export-calibrate --open", installer)
        self.assertIn('-Name "MihoProbe Update"', installer)
        self.assertIn("update --open", installer)
        self.assertIn('-Name "MihoProbe Plan Update"', installer)
        self.assertIn("plan-update --open", installer)
        self.assertIn('-Name "MihoProbe Box Status"', installer)
        self.assertIn("box-status --open", installer)
        self.assertIn('-Name "MihoProbe Rank Check"', installer)
        self.assertIn("rank-check --open", installer)
        self.assertIn('-Name "MihoProbe Fresh OCR"', installer)
        self.assertIn("fresh --open", installer)
        self.assertIn('-Name "MihoProbe Accuracy Check"', installer)
        self.assertIn("replay --open", installer)
        self.assertIn("MihoProbe local dashboard entry", opener)
        self.assertIn("dashboard --open", opener)
        self.assertIn("app-export --open", opener)
        self.assertIn("app-export-calibrate --open", opener)
        self.assertIn("app-export-run --no-open", opener)
        self.assertIn("update --open", opener)
        self.assertIn("plan-update --open", opener)
        self.assertIn("box-status --open", opener)
        self.assertIn("box-roster --image", opener)
        self.assertIn("box-value --box-image", opener)
        self.assertIn("rank-check --open", opener)
        self.assertIn("fresh --open", opener)
        self.assertIn("check --no-open", opener)
        self.assertIn("replay --no-open", opener)
        self.assertIn("ask-gpt --focus", opener)

    def test_exe_build_uses_tracked_spec_and_clear_dependency_message(self) -> None:
        builder = (PROJECT_ROOT / "scripts" / "build_miho_probe_exe.ps1").read_text(encoding="utf-8")
        wrapper = (PROJECT_ROOT / "scripts" / "build_miho_probe_exe.bat").read_text(encoding="utf-8")
        spec = (PROJECT_ROOT / "packaging" / "MihoProbe.spec").read_text(encoding="utf-8")

        self.assertIn("packaging\\MihoProbe.spec", builder)
        self.assertIn("import PyInstaller", builder)
        self.assertIn("python -m pip install pyinstaller", builder)
        self.assertIn("dist\\MihoProbe.exe", builder)
        self.assertIn("dist\\MihoProbe.exe app-export", builder)
        self.assertIn("dist\\MihoProbe.exe app-export-calibrate", builder)
        self.assertIn("dist\\MihoProbe.exe update", builder)
        self.assertIn("dist\\MihoProbe.exe plan-update", builder)
        self.assertIn("dist\\MihoProbe.exe box-status / box-roster / box-value", builder)
        self.assertIn("dist\\MihoProbe.exe rank-check", builder)
        self.assertIn("dist\\MihoProbe.exe check", builder)
        self.assertIn("dist\\MihoProbe.exe ask-gpt", builder)
        self.assertIn("build_miho_probe_exe.ps1", wrapper)
        self.assertIn("project_root", spec)
        self.assertIn("project_root / 'tools' / 'probes'", spec)
        self.assertIn("probe_hiddenimports", spec)
        self.assertIn("miho_probe_cli.py", spec)
        self.assertIn("'extract_zzz_box_roster'", spec)
        self.assertIn("'run_zzz_box_value_pipeline'", spec)
        self.assertIn("'prepare_zzz_meta_snapshot'", spec)
        self.assertIn("'build_agent_value_cards'", spec)
        self.assertIn("'PIL.Image'", spec)
        self.assertIn("name='MihoProbe'", spec)

    def test_readme_exposes_exe_replay_acceptance_entry(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("MihoProbe Accuracy Check", readme)
        self.assertIn("MihoProbe App Export Workflow", readme)
        self.assertIn("MihoProbe Update", readme)
        self.assertIn("MihoProbe Plan Update", readme)
        self.assertIn("MihoProbe Box Status", readme)
        self.assertIn("MihoProbe Rank Check", readme)
        self.assertIn("MihoProbe Fresh OCR", readme)
        self.assertIn("准确率验收缺少样例清单", readme)
        self.assertIn("dist\\MihoProbe.exe update", readme)
        self.assertIn("dist\\MihoProbe.exe app-export", readme)
        self.assertIn("dist\\MihoProbe.exe app-export-calibrate", readme)
        self.assertIn("dist\\MihoProbe.exe app-export-run", readme)
        self.assertIn("dist\\MihoProbe.exe plan-update", readme)
        self.assertIn("dist\\MihoProbe.exe box-status", readme)
        self.assertIn("dist\\MihoProbe.exe box-roster", readme)
        self.assertIn("dist\\MihoProbe.exe box-value", readme)
        self.assertIn("box_status_freshness", readme)
        self.assertIn("box_status_roster_quality", readme)
        self.assertIn("box_status_review_gate", readme)
        self.assertIn("box_status_roster_review_markdown", readme)
        self.assertIn("accepted roster", readme)
        self.assertIn("源图 hash", readme)
        self.assertIn("dist\\MihoProbe.exe rank-check", readme)
        self.assertIn("--rescan-all", readme)
        self.assertIn("dist\\MihoProbe.exe check", readme)
        self.assertIn("data/probes/replay_manifest.json", readme)
        self.assertIn("dist\\MihoProbe.exe ask-gpt", readme)
        self.assertNotIn("dist\\MihoProbe.exe gpt-review", readme)
        self.assertIn("--mode progress", readme)

    def test_cli_examples_expose_gpt_review_entry(self) -> None:
        opener = (PROJECT_ROOT / "scripts" / "open_miho_probe_cli.bat").read_text(encoding="utf-8")
        protocol = (PROJECT_ROOT / "docs" / "notes" / "codex-gpt-adversarial-loop.md").read_text(encoding="utf-8")

        self.assertIn("dist\\MihoProbe.exe ask-gpt", opener)
        self.assertNotIn("dist\\MihoProbe.exe gpt-review", opener)
        self.assertIn("dist\\MihoProbe.exe ask-gpt", protocol)
        self.assertNotIn("dist\\MihoProbe.exe gpt-review", protocol)
        self.assertIn("--mode progress", protocol)
        self.assertIn("不要再为发送这一条消息重试浏览器自动化", protocol)
        self.assertIn("python tools/probes/build_gpt_review_prompt.py", protocol)
        self.assertIn("禁止重复探索", protocol)
        self.assertIn("不再让 Codex 读取右侧 GPT 的长历史", protocol)
        self.assertIn("不再让 Codex 自动操作右侧 ChatGPT 页面", protocol)
        self.assertIn("不尝试自动点击右侧发送按钮", protocol)


if __name__ == "__main__":
    unittest.main()
