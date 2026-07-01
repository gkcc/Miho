from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_agent_value_cards.py"

spec = importlib.util.spec_from_file_location("build_agent_value_cards", SCRIPT_PATH)
assert spec is not None
value_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = value_tool
spec.loader.exec_module(value_tool)


def mock_meta() -> dict:
    return {
        "tier_list": {
            "entries": [
                {
                    "agent_slug": "qingyi",
                    "name": "Qingyi",
                    "rarity": "S",
                    "element": "Electric",
                    "specialty": "Stun",
                    "tier_ratings": [{"category": "Support", "rating": 9, "marks": "", "tags": "", "has_potential": False}],
                },
                {
                    "agent_slug": "zhu-yuan",
                    "name": "Zhu Yuan",
                    "rarity": "S",
                    "element": "Ether",
                    "specialty": "Attack",
                    "tier_ratings": [{"category": "CritDPS", "rating": 8, "marks": "down", "tags": "", "has_potential": False}],
                },
                {
                    "agent_slug": "nicole-demara",
                    "name": "Nicole",
                    "rarity": "A",
                    "element": "Ether",
                    "specialty": "Support",
                    "tier_ratings": [{"category": "Support", "rating": 10, "marks": "", "tags": "Expert", "has_potential": False}],
                },
                {
                    "agent_slug": "velina",
                    "name": "Velina",
                    "rarity": "S",
                    "element": "Wind",
                    "specialty": "Anomaly",
                    "tier_ratings": [{"category": "AnoDPS", "rating": 10, "marks": "new", "tags": "", "has_potential": False}],
                },
                {
                    "agent_slug": "ukinami-yuzuha",
                    "name": "Yuzuha",
                    "rarity": "S",
                    "element": "Physical",
                    "specialty": "Support",
                    "tier_ratings": [{"category": "Support", "rating": 11, "marks": "", "tags": "", "has_potential": False}],
                },
                {
                    "agent_slug": "piper",
                    "name": "Piper",
                    "rarity": "A",
                    "element": "Physical",
                    "specialty": "Anomaly",
                    "tier_ratings": [{"category": "AnoDPS", "rating": 9, "marks": "", "tags": "", "has_potential": False}],
                },
            ]
        },
        "endgame": {
            "modes": {
                "deadly_assault": {
                    "phases": [
                        {
                            "phase": {"mode": "deadly_assault", "phase": "3.0.1", "label": "3.0.1 mock"},
                            "character_stats": [
                                {"agent_slug": "qingyi", "current_app_rate": 1.2, "current_avg_score": 25000},
                                {"agent_slug": "zhu-yuan", "current_app_rate": 0.8, "current_avg_score": 24000},
                                {"agent_slug": "nicole-demara", "current_app_rate": 3.5, "current_avg_score": 26000},
                                {"agent_slug": "velina", "current_app_rate": 11.0, "current_avg_score": 33000},
                                {"agent_slug": "piper", "current_app_rate": 4.5, "current_avg_score": 26000},
                            ],
                            "team_usage": [
                                {
                                    "scope_key": "2",
                                    "rank": 1,
                                    "agent_1_slug": "zhu-yuan",
                                    "agent_2_slug": "qingyi",
                                    "agent_3_slug": "nicole-demara",
                                    "app_rate": 1.0,
                                    "avg_score": 26000,
                                    "avg_score_m1plus": 30000,
                                },
                                {
                                    "scope_key": "1",
                                    "rank": 2,
                                    "agent_1_slug": "piper",
                                    "agent_2_slug": "velina",
                                    "agent_3_slug": "ukinami-yuzuha",
                                    "app_rate": 8.0,
                                    "avg_score": 32000,
                                    "avg_score_m1plus": 36000,
                                },
                            ],
                        }
                    ]
                }
            }
        },
    }


class AgentValueCardsTests(unittest.TestCase):
    def test_chinese_roster_maps_and_low_level_meta_unit_keeps_value_but_marks_cost(self) -> None:
        roster = {
            "agents": [
                {"name": "青衣", "level": 60, "mindscape": 1},
                {"name": "朱鸢", "level": 60, "mindscape": 0},
                {"name": "妮可", "level": 50, "mindscape": 6},
                {"name": "维琳娜", "level": 1, "mindscape": 0},
                {"name": "派派", "level": 10, "mindscape": 6},
            ]
        }

        values, summary = value_tool.build_agent_values(meta=mock_meta(), roster=roster)

        self.assertEqual(summary["owned_count"], 5)
        self.assertEqual(summary["unmapped_count"], 0)
        by_slug = {item["agent_slug"]: item for item in values}
        self.assertEqual(by_slug["qingyi"]["name"], "青衣")
        self.assertIn(by_slug["velina"]["recommendation_status"], {"raise_if_team_needed", "usable_invest", "priority_raise_from_low_level"})
        self.assertEqual(by_slug["velina"]["investment_cost_note"], "from_scratch_raise_needed")
        self.assertEqual(by_slug["velina"]["readiness_score"], 10.0)
        self.assertGreater(by_slug["velina"]["potential_score"], by_slug["velina"]["reality_score"])
        self.assertIn("不会直接压低角色价值", " ".join(by_slug["velina"]["reasons"]))

    def test_level_does_not_change_agent_value_score(self) -> None:
        low_level = {"agents": [{"name": "维琳娜", "level": 1, "mindscape": 0}]}
        high_level = {"agents": [{"name": "维琳娜", "level": 60, "mindscape": 0}]}

        low_values, _ = value_tool.build_agent_values(meta=mock_meta(), roster=low_level)
        high_values, _ = value_tool.build_agent_values(meta=mock_meta(), roster=high_level)

        self.assertEqual(low_values[0]["reality_score"], high_values[0]["reality_score"])
        self.assertEqual(low_values[0]["potential_score"], high_values[0]["potential_score"])
        self.assertNotEqual(low_values[0]["investment_cost_note"], high_values[0]["investment_cost_note"])

    def test_team_recommendations_keep_missing_units_out_of_current_teams(self) -> None:
        roster = {
            "agents": [
                {"name": "青衣", "level": 60},
                {"name": "朱鸢", "level": 60},
                {"name": "妮可", "level": 50},
                {"name": "维琳娜", "level": 1},
                {"name": "派派", "level": 10},
            ]
        }
        values, _ = value_tool.build_agent_values(meta=mock_meta(), roster=roster)

        recs = value_tool.build_team_recommendations(mock_meta(), values)

        deadly = recs["deadly_assault"]
        self.assertEqual(deadly["owned_candidate_count"], 1)
        self.assertEqual(deadly["top_owned_candidates"][0]["members"], ["zhu-yuan", "qingyi", "nicole-demara"])
        self.assertEqual(deadly["missing_one_watchlist"][0]["missing_agent_slugs"], ["ukinami-yuzuha"])
        self.assertIn("不能算入当前可用队", deadly["missing_one_watchlist"][0]["note"])

    def test_executive_summary_exposes_human_readable_decisions(self) -> None:
        roster = {
            "agents": [
                {"name": "青衣", "level": 60},
                {"name": "朱鸢", "level": 60},
                {"name": "妮可", "level": 50},
                {"name": "维琳娜", "level": 1},
                {"name": "派派", "level": 10},
            ]
        }
        values, _ = value_tool.build_agent_values(meta=mock_meta(), roster=roster)
        recs = value_tool.build_team_recommendations(mock_meta(), values)

        summary = value_tool.build_executive_summary(values, recs)

        self.assertIn("current_endgame_teams", summary)
        team = summary["current_endgame_teams"]["deadly_assault"]["recommended_team"]
        self.assertEqual(team["member_names"], ["朱鸢", "青衣", "妮可"])
        self.assertTrue(summary["policy_notes"])

    def test_value_report_marks_roster_probe_needing_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meta_path = root / "meta.json"
            roster_path = root / "roster.json"
            output_dir = root / "value"
            meta_path.write_text(json.dumps(mock_meta(), ensure_ascii=False), encoding="utf-8")
            roster_path.write_text(
                json.dumps(
                    {
                        "summary": {"needs_review_count": 1},
                        "agents": [
                            {"name": "青衣", "level": 60, "mindscape": 1, "review_status": "needs_review"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = value_tool.build_agent_value_report(meta_path, roster_path, output_dir)

            self.assertEqual(result["roster_quality"]["status"], "needs_review")
            self.assertEqual(result["roster_quality"]["needs_review_count"], 1)
            self.assertTrue(result["roster_quality"]["manual_confirmation_required_before_planning"])
            self.assertIn("人工确认前只能作为候选 box", " ".join(result["warnings"]))
            markdown = Path(result["output_markdown"]).read_text(encoding="utf-8")
            self.assertIn("roster_quality: needs_review", markdown)
            self.assertIn("roster_needs_review_count: 1", markdown)


if __name__ == "__main__":
    unittest.main()
