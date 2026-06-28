from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_tier_watchlist.py"

tier_spec = importlib.util.spec_from_file_location("build_tier_watchlist", SCRIPT_PATH)
assert tier_spec is not None
tier_tool = importlib.util.module_from_spec(tier_spec)
assert tier_spec.loader is not None
sys.modules[tier_spec.name] = tier_tool
tier_spec.loader.exec_module(tier_tool)


class TierWatchlistTests(unittest.TestCase):
    def test_build_tier_watchlist_highlights_accepted_roster_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tier_snapshot = root / "tier_snapshot.json"
            roster_index = root / "roster_index.json"
            output_dir = root / "tier_watchlist"
            tier_snapshot.write_text(
                json.dumps(
                    {
                        "source": {
                            "name": "unit test tier snapshot",
                            "source_type": "manual",
                            "source_ref": "local",
                        },
                        "entries": [
                            {
                                "character": "星见雅",
                                "tier": "S",
                                "retention_score": 0.91,
                                "usage_rate": "42.5%",
                                "trend": "stable",
                                "modes": ["危局强袭战"],
                                "value_tags": ["high_retention"],
                            },
                            {
                                "character": "耀嘉音",
                                "tier": "S+",
                                "retention_score": "88%",
                                "trend": "up",
                                "modes": ["式舆防卫战"],
                            },
                            {
                                "character": "旧角色",
                                "tier": "B",
                                "retention_score": 0.4,
                                "trend": "down",
                                "value_tags": ["low_retention"],
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            roster_index.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "characters": [
                            {
                                "name": "星见雅",
                                "snapshot_json": str(root / "accepted" / "miyabi.json"),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = tier_tool.build_tier_watchlist(
                tier_snapshot=tier_snapshot,
                roster_index=roster_index,
                output_dir=output_dir,
            )

            self.assertEqual(result["schema_version"], "p1.5-lite-tier-watchlist")
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())
            self.assertEqual(result["summary"]["entry_count"], 3)
            self.assertEqual(result["summary"]["accepted_roster_count"], 1)
            self.assertEqual(result["summary"]["owned_high_value_count"], 1)
            self.assertEqual(result["summary"]["watch_candidate_count"], 1)
            self.assertEqual(result["summary"]["candidate_count"], 2)

            miyabi = next(item for item in result["entries"] if item["character"] == "星见雅")
            self.assertEqual(miyabi["owned_status"], "accepted_roster")
            self.assertEqual(miyabi["recommendation"], "protect_investment")
            self.assertEqual(miyabi["retention_score"], 0.91)
            self.assertEqual(miyabi["usage_rate"], 0.425)
            self.assertIn("保值信号较强", miyabi["reason"])

            yaoqin = next(item for item in result["entries"] if item["character"] == "耀嘉音")
            self.assertEqual(yaoqin["owned_status"], "not_in_roster")
            self.assertEqual(yaoqin["recommendation"], "watch_candidate")
            self.assertIn("不直接生成抽取建议", yaoqin["reason"])

            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("Tier / 保值观察", markdown)
            self.assertIn("accepted_roster_count: 1", markdown)
            self.assertIn("耀嘉音", markdown)

    def test_missing_snapshot_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(tier_tool.TierWatchlistError):
                tier_tool.build_tier_watchlist(
                    tier_snapshot=root / "missing.json",
                    output_dir=root / "out",
                )


if __name__ == "__main__":
    unittest.main()
