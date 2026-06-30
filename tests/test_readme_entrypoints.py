from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReadmeEntrypointTests(unittest.TestCase):
    def test_readme_points_to_existing_user_entrypoints(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        for relative in (
            "scripts/install_miho_demo_shortcut.bat",
            "scripts/build_miho_probe_exe.ps1",
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

        self.assertIn("现在先点哪里", readme)
        self.assertIn("Dashboard 怎么看", readme)
        self.assertIn("准确率怎么验收", readme)
        self.assertIn("不要先跑 OCR", readme)
        self.assertIn("十分钟", readme)
        self.assertIn("绿色才是可继续", readme)
        self.assertNotIn('"entries"', readme)
        self.assertNotIn("tier-stale-days", readme)

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

    def test_shortcut_installer_exposes_app_like_exe_entry(self) -> None:
        installer = (PROJECT_ROOT / "scripts" / "install_miho_demo_shortcut.ps1").read_text(encoding="utf-8")
        opener = (PROJECT_ROOT / "scripts" / "open_miho_probe_cli.bat").read_text(encoding="utf-8")

        self.assertIn('-Name "MihoProbe"', installer)
        self.assertIn("dist\\MihoProbe.exe", installer)
        self.assertIn("dashboard --open", installer)
        self.assertIn('-Name "MihoProbe Accuracy Check"', installer)
        self.assertIn("replay --open", installer)
        self.assertIn("MihoProbe local dashboard entry", opener)
        self.assertIn("dashboard --open", opener)
        self.assertIn("replay --no-open", opener)

    def test_readme_exposes_exe_replay_acceptance_entry(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("MihoProbe Accuracy Check", readme)
        self.assertIn("dist\\MihoProbe.exe replay", readme)
        self.assertIn("data/probes/replay_manifest.json", readme)


if __name__ == "__main__":
    unittest.main()
