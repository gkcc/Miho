from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "prepare_zzz_meta_snapshot.py"

spec = importlib.util.spec_from_file_location("prepare_zzz_meta_snapshot", SCRIPT_PATH)
assert spec is not None
meta_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = meta_tool
spec.loader.exec_module(meta_tool)


class PrepareZzzMetaSnapshotTests(unittest.TestCase):
    def test_parse_phase_options_from_prydwen_select(self) -> None:
        html = """
        <select id="phase-select">
          <option value="20" selected="">3.0.1 - 21/June/2026 (19,687 users)</option>
          <option value="18">2.8.3 - 15/June/2026 (14,464 users)</option>
        </select>
        """

        phases = meta_tool.parse_phase_options(html)

        self.assertEqual(len(phases), 2)
        self.assertEqual(phases[0]["phase_id"], 20)
        self.assertTrue(phases[0]["selected"])
        self.assertEqual(phases[1]["label"], "2.8.3 - 15/June/2026 (14,464 users)")

    def test_parse_tier_entries_from_escaped_next_payload(self) -> None:
        page_text = (
            'prefix {\\"id\\":\\"agent-1\\",\\"slug\\":\\"miyabi\\",\\"name\\":\\"Miyabi\\",'
            '\\"rarity\\":\\"S\\",\\"element\\":\\"Ice\\",\\"style\\":\\"Anomaly\\",'
            '\\"faction\\":\\"Section 6\\",\\"upcoming\\":false,\\"isNew\\":false,'
            '\\"tierRatings\\":[{\\"slug\\":\\"miyabi\\",\\"category\\":\\"AnoDPS\\",'
            '\\"rating\\":10,\\"tags\\":\\"Expert\\",\\"marks\\":\\"\\",'
            '\\"has_potential\\":\\"TRUE\\"}]} suffix'
        )

        entries = meta_tool.parse_tier_entries(page_text)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["agent_slug"], "miyabi")
        self.assertEqual(entries[0]["name"], "Miyabi")
        self.assertEqual(entries[0]["tier_ratings"][0]["rating"], 10)
        self.assertTrue(entries[0]["tier_ratings"][0]["has_potential"])

    def test_normalize_analytics_keeps_character_and_team_signals(self) -> None:
        normalized = meta_tool.normalize_analytics(
            {
                "phase": {
                    "id": 20,
                    "mode": "shiyu_defense",
                    "phase": "3.0.1",
                    "updateDate": "2026-06-21T00:00:00.000Z",
                    "totalUsers": 19687,
                    "bossNames": ["Stage 5-1", "Stage 5-2", "Stage 5-3"],
                },
                "charStats": [
                    {
                        "char": "miyabi",
                        "name": "Miyabi",
                        "current_app_rate": 42.5,
                        "current_avg_score": 34567,
                        "prev_app_rate": 40.1,
                        "prev_avg_score": 34000,
                        "boss_1_usage": 30.0,
                        "boss_1_score": 35000,
                    }
                ],
                "teams": {
                    "1": [
                        {
                            "rank": 1,
                            "char_one": "miyabi",
                            "char_two": "astra-yao",
                            "char_three": "yanagi",
                            "bangboo": "biggest-fan",
                            "app_rate": 12.34,
                            "avg_round": 34567,
                            "avg_round_m1": 37000,
                        }
                    ]
                },
            },
            phase_label="3.0.1 - mock",
            source_url="https://www.prydwen.gg/api/mock",
            content_sha256="a" * 64,
        )

        self.assertEqual(normalized["phase"]["mode"], "shiyu_defense")
        self.assertEqual(normalized["phase"]["boss_names"], ["Stage 5-1", "Stage 5-2", "Stage 5-3"])
        self.assertEqual(normalized["character_stats"][0]["agent_slug"], "miyabi")
        self.assertEqual(normalized["character_stats"][0]["current_app_rate"], 42.5)
        self.assertEqual(normalized["character_stats"][0]["boss_usage"]["1"], 30.0)
        self.assertEqual(normalized["team_usage"][0]["agent_2_slug"], "astra-yao")
        self.assertEqual(normalized["team_usage"][0]["avg_score"], 34567)
        self.assertEqual(normalized["source"]["content_sha256_short"], "a" * 12)


if __name__ == "__main__":
    unittest.main()
