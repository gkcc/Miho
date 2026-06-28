from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_endgame_plan.py"

plan_spec = importlib.util.spec_from_file_location("build_endgame_plan", PLAN_SCRIPT_PATH)
assert plan_spec is not None
plan_tool = importlib.util.module_from_spec(plan_spec)
assert plan_spec.loader is not None
sys.modules[plan_spec.name] = plan_tool
plan_spec.loader.exec_module(plan_tool)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def roster_index() -> dict:
    return {
        "schema_version": "p1.4-lite-roster-index",
        "characters": [
            {"name": "星见雅"},
            {"name": "苍角"},
            {"name": "妮可"},
        ],
    }


def targets() -> dict:
    return {
        "game": "zzz",
        "targets": [
            {
                "activity_name": "危局强袭战",
                "target_tier": "稳定通关",
                "priority": "high",
                "source": {"source_ref": "targets/crisis.html", "content_sha256": "a" * 64},
            },
            {"target": "待确认目标", "priority": "high"},
            {"target": "补录目标", "priority": "medium"},
            {"target": "观察目标", "priority": "low"},
            {"target": "陈旧目标", "priority": "medium"},
        ],
    }


def team_cards() -> dict:
    return {
        "schema_version": "p1.3-lite-team-cards",
        "cards": [
            {
                "target": "危局强袭战 稳定通关",
                "team_title": "低保值可用队",
                "team_status": "playable_now",
                "target_priority": "high",
                "members": [{"character": "苍角", "source_class": "owned_snapshot"}],
                "evidence": {"target_source": "targets/crisis.html", "target_hash": "aaaaaaaaaaaa"},
                "warnings": [],
            },
            {
                "target": "危局强袭战 稳定通关",
                "team_title": "高保值可用队",
                "team_status": "playable_now",
                "target_priority": "high",
                "members": [{"character": "星见雅", "source_class": "owned_snapshot"}],
                "evidence": {"target_source": "targets/crisis.html", "target_hash": "aaaaaaaaaaaa"},
                "warnings": [],
            },
            {
                "target": "待确认目标",
                "team_title": "待确认快照队",
                "team_status": "needs_review",
                "members": [{"character": "莱特", "source_class": "pending_snapshot"}],
                "warnings": ["pending snapshot 尚未进入 accepted roster"],
            },
            {
                "target": "补录目标",
                "team_title": "需补录队",
                "team_status": "needs_recording",
                "members": [{"character": "珂蕾妲", "source_class": "catalog_owned_missing_snapshot"}],
                "warnings": [],
            },
            {
                "target": "观察目标",
                "team_title": "观察候选队",
                "team_status": "needs_candidate_confirmation",
                "members": [{"character": "耀嘉音", "source_class": "catalog_candidate"}],
                "warnings": [],
            },
            {
                "target": "陈旧目标",
                "team_title": "陈旧证据队",
                "team_status": "playable_now",
                "members": [{"character": "妮可", "source_class": "owned_snapshot"}],
                "warnings": [],
            },
        ],
    }


def action_cards() -> dict:
    return {
        "schema_version": "p1.2-lite-action-cards",
        "cards": [
            {
                "target": "待确认目标",
                "character": "莱特",
                "action_type": "review_pending_snapshot",
                "priority": "high",
                "title": "复核 莱特 的解析快照",
                "source_class": "pending_snapshot",
                "status": "needs_review",
            },
            {
                "target": "补录目标",
                "character": "珂蕾妲",
                "action_type": "record_missing_character",
                "priority": "medium",
                "title": "补录 珂蕾妲 的官方分享图",
                "source_class": "catalog_owned_missing_snapshot",
                "status": "needs_review",
            },
        ],
    }


def tier_watchlist() -> dict:
    return {
        "schema_version": "p1.5-lite-tier-watchlist",
        "entries": [
            {
                "character": "星见雅",
                "owned_status": "accepted_roster",
                "tier": "S",
                "retention_score": 0.9,
                "trend": "stable",
                "observation_status": "owned_high_value",
                "recommendation": "protect_investment",
                "entry_status": "verified",
            },
            {
                "character": "妮可",
                "owned_status": "accepted_roster",
                "tier": "A",
                "retention_score": 0.7,
                "trend": "down",
                "observation_status": "owned_high_value",
                "recommendation": "protect_investment",
                "entry_status": "stale",
            },
            {
                "character": "耀嘉音",
                "owned_status": "not_in_roster",
                "tier": "S+",
                "retention_score": 0.88,
                "trend": "up",
                "observation_status": "non_owned_watch_only",
                "recommendation": "watch_candidate",
                "entry_status": "verified",
            },
        ],
    }


def roster_delta() -> dict:
    return {
        "schema_version": "p1.8-lite-roster-delta",
        "character_changes": [
            {"character": "星见雅", "change_type": "updated"},
            {"character": "妮可", "change_type": "unchanged"},
        ],
    }


class EndgamePlanTests(unittest.TestCase):
    def test_build_endgame_plan_separates_ready_review_recording_and_watch_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster_path = root / "roster_index.json"
            targets_path = root / "targets.json"
            teams_path = root / "team_cards.json"
            actions_path = root / "action_cards.json"
            tiers_path = root / "tier_watchlist.json"
            delta_path = root / "roster_delta.json"
            output_dir = root / "endgame_plan"
            write_json(roster_path, roster_index())
            write_json(targets_path, targets())
            write_json(teams_path, team_cards())
            write_json(actions_path, action_cards())
            write_json(tiers_path, tier_watchlist())
            write_json(delta_path, roster_delta())

            result = plan_tool.build_endgame_plan(
                roster_index=roster_path,
                targets=targets_path,
                team_cards=teams_path,
                action_cards=actions_path,
                tier_watchlist=tiers_path,
                roster_delta=delta_path,
                output_dir=output_dir,
            )

            self.assertEqual(result["schema_version"], "p1.9-lite-endgame-plan")
            self.assertEqual(result["summary"]["target_count"], 5)
            self.assertEqual(result["summary"]["ready_now_count"], 2)
            self.assertEqual(result["summary"]["needs_review_count"], 1)
            self.assertEqual(result["summary"]["needs_recording_count"], 1)
            self.assertEqual(result["summary"]["watch_only_count"], 1)
            self.assertEqual(result["summary"]["stale_or_unverified_count"], 1)

            plans = {item["target"]: item for item in result["target_plans"]}
            crisis = plans["危局强袭战 稳定通关"]
            self.assertEqual(crisis["plan_status"], "ready_now")
            self.assertEqual(crisis["team_candidates"][0]["team_title"], "高保值可用队")
            self.assertEqual(crisis["team_candidates"][0]["members"][0]["delta_change_type"], "updated")
            self.assertEqual(crisis["team_candidates"][0]["members"][0]["tier_entry_status"], "verified")
            self.assertIn("sha256_short", crisis["evidence"]["input_artifact_hashes"]["team_cards"])
            self.assertEqual(crisis["evidence"]["target_hash"], "aaaaaaaaaaaa")

            review = plans["待确认目标"]
            self.assertEqual(review["plan_status"], "needs_review")
            self.assertEqual(review["team_candidates"][0]["members"][0]["source_class"], "pending_snapshot")
            self.assertEqual(review["next_actions"][0]["action_type"], "review_pending_snapshot")
            self.assertNotEqual(review["plan_status"], "ready_now")

            recording = plans["补录目标"]
            self.assertEqual(recording["plan_status"], "needs_recording")
            self.assertEqual(recording["next_actions"][0]["action_type"], "record_missing_character")

            watch = plans["观察目标"]
            self.assertEqual(watch["plan_status"], "watch_only")
            self.assertIn("不是抽卡建议", " ".join(watch["warnings"]))

            stale = plans["陈旧目标"]
            self.assertEqual(stale["plan_status"], "ready_now")
            self.assertEqual(stale["team_candidates"][0]["verified_high_value_member_count"], 0)
            self.assertEqual(stale["team_candidates"][0]["weak_tier_count"], 1)
            self.assertIn("stale/unverified/low_trust", stale["team_candidates"][0]["rank_reason"])

            self.assertTrue(Path(result["output_json"]).exists())
            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("本期高难方案", markdown)
            self.assertIn("不是抽卡建议", markdown)

    def test_build_endgame_plan_can_degrade_from_team_targets_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster_path = root / "roster_index.json"
            teams_path = root / "team_cards.json"
            output_dir = root / "endgame_plan"
            write_json(roster_path, roster_index())
            write_json(teams_path, {"cards": [team_cards()["cards"][1]]})

            result = plan_tool.build_endgame_plan(
                roster_index=roster_path,
                team_cards=teams_path,
                output_dir=output_dir,
            )

            self.assertEqual(result["summary"]["target_count"], 1)
            self.assertEqual(result["target_plans"][0]["target"], "危局强袭战 稳定通关")
            self.assertEqual(result["target_plans"][0]["plan_status"], "ready_now")
            self.assertIn("缺少 targets JSON", " ".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
