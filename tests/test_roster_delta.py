from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROSTER_DELTA_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_roster_delta.py"

delta_spec = importlib.util.spec_from_file_location("build_roster_delta", ROSTER_DELTA_SCRIPT_PATH)
assert delta_spec is not None
delta_tool = importlib.util.module_from_spec(delta_spec)
assert delta_spec.loader is not None
sys.modules[delta_spec.name] = delta_tool
delta_spec.loader.exec_module(delta_tool)


def roster_index(items: list[dict]) -> dict:
    return {
        "schema_version": "p1.4-lite-roster-index",
        "characters": items,
    }


def character(name: str, *, level: str, equipment: str, snapshot: str, trusted: int = 10) -> dict:
    return {
        "name": name,
        "level": level,
        "rank": "S",
        "equipment": equipment,
        "snapshot_json": snapshot,
        "source_image": f"figs/{name}.jpg",
        "source_normalized_json": f"normalized/{name}.json",
        "quality": {"trusted_field_count": trusted, "field_count": 16, "blockers": []},
        "review_status": "accepted",
    }


class RosterDeltaTests(unittest.TestCase):
    def test_build_roster_delta_reports_character_team_and_tier_impacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_path = root / "old_roster.json"
            new_path = root / "new_roster.json"
            action_path = root / "action_cards.json"
            team_path = root / "team_cards.json"
            tier_path = root / "tier_watchlist.json"
            output_dir = root / "delta"

            old_path.write_text(
                json.dumps(
                    roster_index(
                        [
                            character("星见雅", level="50", equipment="旧音擎", snapshot="accepted/miyabi_old.json"),
                            character("妮可", level="55", equipment="聚宝箱", snapshot="accepted/nicole.json"),
                        ]
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            new_path.write_text(
                json.dumps(
                    roster_index(
                        [
                            {
                                **character("星见雅", level="60", equipment="新音擎", snapshot="accepted/miyabi_new.json", trusted=14),
                                "superseded_snapshot_count": 1,
                            },
                            character("莱特", level="60", equipment="燃狱齿轮", snapshot="accepted/lighter.json"),
                        ]
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            action_path.write_text(
                json.dumps(
                    {
                        "cards": [
                            {
                                "character": "星见雅",
                                "target": "危局强袭战",
                                "action_type": "train_owned_character",
                                "status": "actionable",
                                "priority": "high",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            team_path.write_text(
                json.dumps(
                    {
                        "cards": [
                            {
                                "target": "危局强袭战",
                                "team_title": "星见雅 核心队",
                                "team_status": "playable_now",
                                "members": [{"character": "星见雅", "source_class": "owned_snapshot"}],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tier_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "character": "星见雅",
                                "owned_status": "accepted_roster",
                                "tier": "S",
                                "retention_score": 0.9,
                                "trend": "up",
                                "entry_status": "verified",
                                "observation_status": "owned_high_value",
                            },
                            {
                                "character": "莱特",
                                "owned_status": "not_in_roster",
                                "tier": "S+",
                                "entry_status": "verified",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = delta_tool.build_roster_delta(
                old_roster_index=old_path,
                new_roster_index=new_path,
                action_cards=action_path,
                team_cards=team_path,
                tier_watchlist=tier_path,
                output_dir=output_dir,
            )

            self.assertEqual(result["schema_version"], "p1.8-lite-roster-delta")
            self.assertEqual(result["summary"]["new_character_count"], 1)
            self.assertEqual(result["summary"]["updated_character_count"], 1)
            self.assertEqual(result["summary"]["removed_character_count"], 1)
            self.assertEqual(result["summary"]["team_impact_count"], 1)
            self.assertEqual(result["summary"]["tier_impact_count"], 1)
            miyabi = next(item for item in result["character_changes"] if item["character"] == "星见雅")
            self.assertEqual(miyabi["change_type"], "updated")
            changed_fields = {item["field"] for item in miyabi["field_changes"]}
            self.assertIn("level", changed_fields)
            self.assertIn("equipment", changed_fields)
            self.assertEqual(miyabi["impacted_targets"], ["危局强袭战"])
            self.assertEqual(miyabi["tier_observation"]["status"], "verified")
            self.assertIn("superseded accepted snapshot", " ".join(miyabi["warnings"]))
            lighter = next(item for item in result["character_changes"] if item["character"] == "莱特")
            self.assertEqual(lighter["change_type"], "new")
            self.assertEqual(lighter["tier_observation"]["status"], "missing")
            nicole = next(item for item in result["character_changes"] if item["character"] == "妮可")
            self.assertEqual(nicole["change_type"], "removed")
            self.assertTrue(Path(result["output_json"]).exists())
            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("本次练度更新影响", markdown)
            self.assertIn("pending snapshot", markdown)


if __name__ == "__main__":
    unittest.main()
