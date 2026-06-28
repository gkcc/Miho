from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "prepare_endgame_targets.py"
CLI_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

target_spec = importlib.util.spec_from_file_location("prepare_endgame_targets", TARGET_SCRIPT_PATH)
assert target_spec is not None
target_tool = importlib.util.module_from_spec(target_spec)
assert target_spec.loader is not None
sys.modules[target_spec.name] = target_tool
target_spec.loader.exec_module(target_tool)

cli_spec = importlib.util.spec_from_file_location("miho_probe_cli", CLI_SCRIPT_PATH)
assert cli_spec is not None
cli_tool = importlib.util.module_from_spec(cli_spec)
assert cli_spec.loader is not None
sys.modules[cli_spec.name] = cli_tool
cli_spec.loader.exec_module(cli_tool)


class EndgameTargetIntakeTests(unittest.TestCase):
    def test_prepare_targets_from_saved_html_extracts_activity_and_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.html"
            source.write_text(
                """
                <html><head><title>危局强袭战 本期目标</title></head>
                <body>本期危局强袭战推荐火属性与异常队伍，首领机制需要快速击破。</body></html>
                """,
                encoding="utf-8",
            )

            result = target_tool.prepare_targets(
                game="zzz",
                source_type="public_web_snapshot",
                sources=[
                    {
                        "input": str(source),
                        "target_tier": "稳定通关",
                        "priority": "high",
                        "preferred_characters": ["星见雅"],
                        "minimums": {"skill_level": 9},
                    }
                ],
                output_dir=root / "out",
            )

            self.assertTrue(Path(result["output_json"]).exists())
            self.assertEqual(result["schema_version"], "p1.3-target-intake-draft")
            self.assertEqual(result["freshness"]["level"], "fresh")
            self.assertEqual(result["freshness"]["stale_source_count"], 0)
            self.assertEqual(result["targets"][0]["activity_name"], "危局强袭战")
            self.assertIn("fire", result["targets"][0]["weakness_tags"])
            self.assertIn("anomaly", result["targets"][0]["mechanic_tags"])
            self.assertIn("stun", result["targets"][0]["mechanic_tags"])
            self.assertEqual(len(result["sources"][0]["content_sha256"]), 64)
            self.assertEqual(result["targets"][0]["evidence"]["content_sha256"], result["sources"][0]["content_sha256"])
            self.assertEqual(result["targets"][0]["evidence"]["source_kind"], "file")
            self.assertEqual(result["targets"][0]["evidence"]["source_ref"], str(source))
            self.assertIn("危局强袭战", result["targets"][0]["evidence"]["matched_aliases"]["activity"])
            self.assertIn("火属性", result["targets"][0]["evidence"]["matched_aliases"]["weakness_tags"]["fire"])
            self.assertIn("异常", result["targets"][0]["evidence"]["matched_aliases"]["mechanic_tags"]["anomaly"])
            self.assertIn("击破", result["targets"][0]["evidence"]["matched_aliases"]["mechanic_tags"]["stun"])
            self.assertIn("不是 official_current", result["warnings"][-1])

    def test_public_url_validation_blocks_local_and_private_hosts(self) -> None:
        for url in ["http://localhost:8080/a", "http://127.0.0.1/a", "http://10.0.0.2/a", "file:///tmp/a.html"]:
            with self.subTest(url=url):
                with self.assertRaises(target_tool.TargetIntakeError):
                    target_tool.validate_public_url(url)

        parsed = target_tool.validate_public_url("https://example.com/news")
        self.assertEqual(parsed.hostname, "example.com")

    def test_manifest_sources_can_override_target_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            manifest = root / "manifest.json"
            source.write_text("混沌回忆 本期敌人弱物理、量子，适合追加攻击。", encoding="utf-8")
            manifest.write_text(
                json.dumps(
                    {
                        "game": "hsr",
                        "source_type": "official_snapshot",
                        "default_minimums": {"character_level": 80, "equipment_level": 80, "skill_level": 9},
                        "sources": [
                            {
                                "input": str(source),
                                "goal_id": "hsr_mock_moc",
                                "target_tier": "满星尝试",
                                "preferred_characters": ["真理医生"],
                                "minimums": {"skill_level": 10},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            game, source_type, sources, defaults = target_tool.source_cases_from_manifest(manifest)
            result = target_tool.prepare_targets(
                game=game,
                source_type=source_type,
                sources=sources,
                output_dir=root / "out",
                manifest_defaults=defaults,
            )

            self.assertEqual(result["game"], "hsr")
            self.assertEqual(result["source"]["type"], "official_snapshot")
            self.assertEqual(result["default_minimums"]["character_level"], 80)
            self.assertEqual(result["targets"][0]["activity_name"], "混沌回忆")
            self.assertIn("quantum", result["targets"][0]["weakness_tags"])
            self.assertIn("follow_up", result["targets"][0]["mechanic_tags"])
            self.assertIn("量子", result["sources"][0]["matched_aliases"]["weakness_tags"]["quantum"])
            self.assertIn("追加攻击", result["targets"][0]["evidence"]["matched_aliases"]["mechanic_tags"]["follow_up"])

    def test_prepare_targets_marks_stale_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "stale_source.txt"
            source.write_text("危局强袭战 本期敌人弱冰，适合异常队。", encoding="utf-8")
            old_time = time.time() - (4 * 3600)
            os.utime(source, (old_time, old_time))

            result = target_tool.prepare_targets(
                game="zzz",
                source_type="official_current",
                sources=[
                    {
                        "input": str(source),
                        "target_tier": "稳定通关",
                        "preferred_characters": ["星见雅"],
                    }
                ],
                output_dir=root / "out",
                manifest_defaults={"max_source_age_hours": 1},
            )

            self.assertEqual(result["freshness"]["level"], "stale")
            self.assertEqual(result["freshness"]["stale_source_count"], 1)
            self.assertEqual(result["sources"][0]["freshness"]["status"], "stale")
            self.assertTrue(any("已过期" in warning for warning in result["warnings"]))

    def test_cli_targets_command_is_registered(self) -> None:
        parser = cli_tool.build_arg_parser()
        args = parser.parse_args(["targets", "--input", "source.html", "--preferred-character", "星见雅", "--max-source-age-hours", "24"])

        self.assertEqual(args.handler, cli_tool.run_targets)
        self.assertEqual(args.input, ["source.html"])
        self.assertEqual(args.preferred_character, ["星见雅"])
        self.assertEqual(args.max_source_age_hours, 24)


if __name__ == "__main__":
    unittest.main()
