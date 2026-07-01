from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEAM_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_team_cards.py"

team_spec = importlib.util.spec_from_file_location("build_team_cards", TEAM_SCRIPT_PATH)
assert team_spec is not None
team_tool = importlib.util.module_from_spec(team_spec)
assert team_spec.loader is not None
sys.modules[team_spec.name] = team_tool
team_spec.loader.exec_module(team_tool)


def planner_report() -> dict:
    return {
        "schema_version": "p1.2-planner-draft",
        "game": "zzz",
        "input": {"snapshots": ["normalized/miyabi.json"], "targets": "targets.json"},
        "snapshots": [{"character": "星见雅", "source_image": "figs/miyabi.jpg"}],
        "target_coverage": [
            {
                "target": "危局强袭战 稳定通关",
                "coverage_status": "covered",
                "priority": "high",
                "matched_characters": [{"character": "星见雅", "match_type": "tag_overlap", "score": 65}],
                "catalog_candidates": [],
                "evidence": {
                    "source_ref": "data/probes/targets/crisis.html",
                    "content_sha256_short": "abcdef123456",
                    "matched_aliases": {"mechanic_tags": {"anomaly": ["异常"]}},
                },
            },
            {
                "target": "式舆防卫战 满星尝试",
                "coverage_status": "unmatched",
                "priority": "high",
                "matched_characters": [],
                "catalog_candidates": [{"character": "珂蕾妲", "owned": None, "matched_tags": ["fire", "stun"]}],
                "evidence": {"source_ref": "data/probes/targets/shiyu.html", "content_sha256_short": "123456abcdef"},
            },
            {
                "target": "零号空洞 高压",
                "coverage_status": "unmatched",
                "priority": "medium",
                "matched_characters": [],
                "catalog_candidates": [{"character": "莱特", "owned": True, "matched_tags": ["fire", "stun"]}],
                "evidence": {"source_ref": "data/probes/targets/hollow.html", "content_sha256_short": "fedcba654321"},
            },
        ],
    }


def action_cards() -> dict:
    return {
        "schema_version": "p1.2-lite-action-cards",
        "cards": [
            {
                "target": "危局强袭战 稳定通关",
                "character": "星见雅",
                "reason": "高难目标命中，但技能等级不足。",
            },
            {
                "target": "式舆防卫战 满星尝试",
                "character": "珂蕾妲",
                "reason": "catalog 候选命中目标缺口，但 owned 状态未知。",
            },
            {
                "target": "零号空洞 高压",
                "character": "莱特",
                "reason": "catalog 标记已拥有，但当前 snapshots 没有练度快照。",
            },
        ],
    }


def tier_watchlist() -> dict:
    return {
        "schema_version": "p1.5-lite-tier-watchlist",
        "summary": {"verified_entry_count": 3},
        "entries": [
            {
                "character": "星见雅",
                "owned_status": "accepted_roster",
                "tier": "S",
                "tier_score": 90,
                "retention_score": 0.9,
                "trend": "stable",
                "observation_status": "owned_high_value",
                "recommendation": "protect_investment",
                "entry_status": "verified",
                "evidence": {
                    "period": "2026-06",
                    "content_sha256_short": "aaaaaaaaaaaa",
                    "source_title": "unit tier",
                },
            },
            {
                "character": "妮可",
                "owned_status": "accepted_roster",
                "tier": "A",
                "tier_score": 78,
                "retention_score": 0.7,
                "trend": "stable",
                "observation_status": "owned_observe",
                "recommendation": "owned_observe",
                "entry_status": "stale",
                "evidence": {
                    "period": "2026-01",
                    "content_sha256_short": "bbbbbbbbbbbb",
                    "source_title": "old tier",
                },
            },
            {
                "character": "珂蕾妲",
                "owned_status": "not_in_roster",
                "tier": "S+",
                "tier_score": 92,
                "retention_score": 0.88,
                "trend": "up",
                "observation_status": "non_owned_watch_only",
                "recommendation": "watch_candidate",
                "entry_status": "verified",
                "evidence": {
                    "period": "2026-06",
                    "content_sha256_short": "cccccccccccc",
                    "source_title": "unit tier",
                },
            },
        ],
    }


class TeamCardTests(unittest.TestCase):
    def test_build_team_cards_keeps_snapshot_and_catalog_sources_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            planner_path = root / "training_priority_report.json"
            action_path = root / "action_cards.json"
            output_dir = root / "teams"
            planner_path.write_text(json.dumps(planner_report(), ensure_ascii=False), encoding="utf-8")
            action_path.write_text(json.dumps(action_cards(), ensure_ascii=False), encoding="utf-8")

            result = team_tool.build_team_cards(
                action_cards=action_path,
                planner_report=planner_path,
                output_dir=output_dir,
            )

            self.assertEqual(result["schema_version"], "p1.3-lite-team-cards")
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())
            self.assertEqual(result["summary"]["target_count"], 3)
            self.assertEqual(result["summary"]["team_card_count"], 3)
            self.assertEqual(result["summary"]["playable_now_count"], 0)
            self.assertEqual(result["summary"]["needs_recording_count"], 1)
            self.assertEqual(result["summary"]["catalog_candidate_count"], 1)
            self.assertEqual(result["summary"]["pending_snapshot_count"], 1)

            covered = next(item for item in result["cards"] if item["target"] == "危局强袭战 稳定通关")
            self.assertEqual(covered["team_status"], "needs_review")
            self.assertEqual(covered["members"][0]["source_class"], "pending_snapshot")
            self.assertEqual(covered["members"][0]["snapshot_json"], "normalized/miyabi.json")
            self.assertEqual(covered["members"][0]["snapshot_source"], "figs/miyabi.jpg")
            self.assertIn("pending snapshot 尚未进入 accepted roster", " ".join(covered["warnings"]))
            self.assertEqual(covered["evidence"]["target_hash"], "abcdef123456")

            candidate = next(item for item in result["cards"] if item["target"] == "式舆防卫战 满星尝试")
            self.assertEqual(candidate["team_status"], "needs_candidate_confirmation")
            self.assertEqual(candidate["members"][0]["source_class"], "catalog_candidate")
            self.assertIsNone(candidate["members"][0]["snapshot_json"])
            self.assertIn("catalog candidate 不代表已拥有", " ".join(candidate["warnings"]))

            missing_snapshot = next(item for item in result["cards"] if item["target"] == "零号空洞 高压")
            self.assertEqual(missing_snapshot["team_status"], "needs_recording")
            self.assertEqual(missing_snapshot["members"][0]["source_class"], "catalog_owned_missing_snapshot")
            self.assertIsNone(missing_snapshot["members"][0]["snapshot_json"])

            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("高难配队候选卡", markdown)
            self.assertIn("## 概览", markdown)
            self.assertIn("## 队伍卡", markdown)
            self.assertIn("队伍状态: 需先复核", markdown)
            self.assertIn("来源 待确认快照", markdown)
            self.assertIn("目录候选不代表已拥有", markdown)
            self.assertIn("待确认快照 尚未进入 已确认角色库", markdown)
            self.assertNotIn("## Summary", markdown)
            self.assertNotIn("## Team Cards", markdown)
            self.assertNotIn("team_status:", markdown)
            self.assertNotIn("source_class", markdown)
            self.assertNotIn("accepted roster", markdown)

    def test_roster_index_controls_which_snapshots_count_as_owned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            planner = planner_report()
            planner["input"]["snapshots"] = ["normalized/miyabi.json", "normalized/nicole.json"]
            planner["snapshots"].append({"character": "妮可", "source_image": "figs/nicole.jpg"})
            planner["target_coverage"][0]["matched_characters"].append(
                {"character": "妮可", "match_type": "tag_overlap", "score": 40}
            )
            planner_path = root / "training_priority_report.json"
            action_path = root / "action_cards.json"
            tier_path = root / "tier_watchlist.json"
            roster_index = root / "roster_index.json"
            output_dir = root / "teams"
            planner_path.write_text(json.dumps(planner, ensure_ascii=False), encoding="utf-8")
            action_path.write_text(json.dumps(action_cards(), ensure_ascii=False), encoding="utf-8")
            tier_path.write_text(json.dumps(tier_watchlist(), ensure_ascii=False), encoding="utf-8")
            roster_index.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "characters": [{"name": "星见雅"}, {"name": "妮可"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = team_tool.build_team_cards(
                action_cards=action_path,
                planner_report=planner_path,
                roster_index=roster_index,
                tier_watchlist=tier_path,
                output_dir=output_dir,
            )

            covered = next(item for item in result["cards"] if item["target"] == "危局强袭战 稳定通关")
            self.assertEqual(covered["team_status"], "playable_now")
            self.assertEqual({item["source_class"] for item in covered["members"]}, {"owned_snapshot"})
            self.assertEqual(covered["team_value"]["accepted_high_value_members"], 1)
            self.assertEqual(covered["team_value"]["stale_meta_count"], 1)
            self.assertEqual(covered["members"][0]["tier_signal"]["entry_status"], "verified")
            self.assertEqual(covered["members"][0]["tier_signal"]["observation_status"], "owned_high_value")
            self.assertEqual(result["summary"]["playable_now_count"], 1)
            self.assertEqual(result["summary"]["high_value_playable_team_count"], 1)
            self.assertEqual(result["summary"]["accepted_high_value_member_count"], 1)
            self.assertEqual(result["summary"]["stale_meta_count"], 1)
            self.assertEqual(result["summary"]["pending_snapshot_count"], 0)
            self.assertEqual(result["input"]["roster_index"], str(roster_index))
            self.assertEqual(result["input"]["tier_watchlist"], str(tier_path))

    def test_tier_watchlist_does_not_promote_pending_or_catalog_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            planner_path = root / "training_priority_report.json"
            action_path = root / "action_cards.json"
            tier_path = root / "tier_watchlist.json"
            output_dir = root / "teams"
            planner_path.write_text(json.dumps(planner_report(), ensure_ascii=False), encoding="utf-8")
            action_path.write_text(json.dumps(action_cards(), ensure_ascii=False), encoding="utf-8")
            tier_path.write_text(json.dumps(tier_watchlist(), ensure_ascii=False), encoding="utf-8")

            result = team_tool.build_team_cards(
                action_cards=action_path,
                planner_report=planner_path,
                tier_watchlist=tier_path,
                output_dir=output_dir,
            )

            covered = next(item for item in result["cards"] if item["target"] == "危局强袭战 稳定通关")
            candidate = next(item for item in result["cards"] if item["target"] == "式舆防卫战 满星尝试")
            self.assertEqual(covered["team_status"], "needs_review")
            self.assertEqual(covered["members"][0]["source_class"], "pending_snapshot")
            self.assertEqual(covered["team_value"]["accepted_high_value_members"], 0)
            self.assertEqual(candidate["team_status"], "needs_candidate_confirmation")
            self.assertEqual(candidate["members"][0]["source_class"], "catalog_candidate")
            self.assertEqual(candidate["members"][0]["tier_signal"]["observation_status"], "non_owned_watch_only")
            self.assertEqual(result["summary"]["high_value_playable_team_count"], 0)
            self.assertIn("非 accepted roster 成员的 tier", " ".join(candidate["warnings"]))

    def test_missing_action_cards_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            planner_path = root / "training_priority_report.json"
            planner_path.write_text(json.dumps(planner_report(), ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(team_tool.TeamCardError):
                team_tool.build_team_cards(
                    action_cards=root / "missing.json",
                    planner_report=planner_path,
                    output_dir=root / "teams",
                )


if __name__ == "__main__":
    unittest.main()
