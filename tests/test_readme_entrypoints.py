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
        self.assertNotIn('"entries"', readme)
        self.assertNotIn("tier-stale-days", readme)


if __name__ == "__main__":
    unittest.main()
