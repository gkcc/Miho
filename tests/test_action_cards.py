from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTION_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_action_cards.py"

action_spec = importlib.util.spec_from_file_location("build_action_cards", ACTION_SCRIPT_PATH)
assert action_spec is not None
action_tool = importlib.util.module_from_spec(action_spec)
assert action_spec.loader is not None
sys.modules[action_spec.name] = action_tool
action_spec.loader.exec_module(action_tool)


def planner_report() -> dict:
    return {
        "schema_version": "p1.2-planner-draft",
        "game": "zzz",
        "input": {"targets": "targets.json", "snapshots": ["normalized/miyabi.json"]},
        "snapshots": [{"character": "星见雅", "source_image": "figs/miyabi.jpg"}],
        "target_coverage": [
            {
                "target": "式舆防卫战 稳定通关",
                "coverage_status": "covered",
                "priority": "high",
                "matched_characters": [{"character": "星见雅"}],
                "catalog_candidates": [],
                "evidence": {
                    "source_ref": "data/probes/targets/mock_source.html",
                    "content_sha256_short": "abcdef123456",
                    "matched_aliases": {"weakness_tags": {"ice": ["冰"]}},
                },
            },
            {
                "target": "危局强袭战 稳定通关",
                "coverage_status": "unmatched",
                "priority": "high",
                "matched_characters": [],
                "catalog_candidates": [{"character": "珂蕾妲", "owned": None, "matched_tags": ["fire", "stun"]}],
                "evidence": {
                    "source_ref": "data/probes/targets/crisis.html",
                    "content_sha256_short": "123456abcdef",
                    "matched_aliases": {"mechanic_tags": {"stun": ["击破"]}},
                },
            },
            {
                "target": "零号空洞 高压",
                "coverage_status": "unmatched",
                "priority": "medium",
                "matched_characters": [],
                "catalog_candidates": [{"character": "莱特", "owned": True, "matched_tags": ["fire", "stun"]}],
                "evidence": {
                    "source_ref": "data/probes/targets/hollow.html",
                    "content_sha256_short": "fedcba654321",
                },
            },
        ],
        "coverage_gap_actions": [
            {
                "rank": 1,
                "target": "危局强袭战 稳定通关",
                "target_priority": "high",
                "character": "珂蕾妲",
                "action_type": "confirm_ownership",
                "action": "先确认是否拥有，拥有后补录官方分享图",
                "reason": "catalog 候选命中目标缺口，但 owned 状态未知，不能直接规划体力。",
                "matched_tags": ["fire", "stun"],
                "match_types": ["tag_overlap"],
                "owned": None,
                "confidence": "low",
            },
            {
                "rank": 2,
                "target": "零号空洞 高压",
                "target_priority": "medium",
                "character": "莱特",
                "action_type": "record_owned_snapshot",
                "action": "补录或更新该角色官方分享图",
                "reason": "catalog 标记已拥有，但当前 snapshots 没有可用于该目标的练度快照。",
                "matched_tags": ["fire", "stun"],
                "match_types": ["preferred_character"],
                "owned": True,
                "confidence": "medium",
            },
        ],
        "plan_items": [
            {
                "priority_rank": 1,
                "priority_score": 48,
                "character": "星见雅",
                "target": "式舆防卫战 稳定通关",
                "gap_type": "skill_level",
                "action": "补关键技能到 9 左右",
                "reason": "高难目标命中，但技能等级不足。",
                "estimated_days": 2.0,
                "confidence": "high",
                "target_match_reasons": ["角色标签命中目标弱点/机制"],
            }
        ],
    }


def tier_watchlist_report(*, miyabi_recommendation: str = "protect_investment") -> dict:
    miyabi_reason = (
        "已在 accepted roster 中，且 tier/保值信号较强；后续培养和配队建议应优先保护这类投入。"
        if miyabi_recommendation == "protect_investment"
        else "已在 accepted roster 中，但保值或趋势偏弱；除非命中具体终局目标，否则不建议继续加码。"
    )
    return {
        "schema_version": "p1.5-lite-tier-watchlist",
        "source": {"name": "unit test tier snapshot", "source_type": "manual", "source_ref": "local"},
        "entries": [
            {
                "character": "星见雅",
                "owned_status": "accepted_roster",
                "tier": "S",
                "tier_score": 90,
                "retention_score": 0.9 if miyabi_recommendation == "protect_investment" else 0.35,
                "trend": "stable" if miyabi_recommendation == "protect_investment" else "down",
                "recommendation": miyabi_recommendation,
                "reason": miyabi_reason,
                "source": {"name": "unit test tier snapshot", "source_ref": "local"},
            },
            {
                "character": "珂蕾妲",
                "owned_status": "not_in_roster",
                "tier": "S+",
                "tier_score": 92,
                "retention_score": 0.88,
                "trend": "up",
                "recommendation": "watch_candidate",
                "reason": "未在 accepted roster 中，但 tier/保值信号较强；这里只做观察候选，不直接生成抽取建议。",
                "source": {"name": "unit test tier snapshot", "source_ref": "local"},
            },
            {
                "character": "莱特",
                "owned_status": "not_in_roster",
                "tier": "B",
                "tier_score": 65,
                "retention_score": 0.4,
                "trend": "down",
                "recommendation": "low_priority_candidate",
                "reason": "未在 accepted roster 中，且趋势或保值偏弱；作为低优先级观察项。",
                "source": {"name": "unit test tier snapshot", "source_ref": "local"},
            },
        ],
        "warnings": [],
    }


class ActionCardTests(unittest.TestCase):
    def test_build_action_cards_keeps_owned_and_catalog_candidates_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "training_priority_report.json"
            targets_path = root / "targets.json"
            snapshots_dir = root / "normalized"
            roster_index = root / "roster_index.json"
            tier_watchlist = root / "tier_watchlist.json"
            output_dir = root / "actions"
            snapshots_dir.mkdir()
            (snapshots_dir / "miyabi.json").write_text("{}", encoding="utf-8")
            report_path.write_text(json.dumps(planner_report(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps({"game": "zzz"}, ensure_ascii=False), encoding="utf-8")
            roster_index.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "characters": [{"name": "星见雅"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tier_watchlist.write_text(json.dumps(tier_watchlist_report(), ensure_ascii=False), encoding="utf-8")

            result = action_tool.build_action_cards(
                planner_report=report_path,
                targets=targets_path,
                snapshots_dir=snapshots_dir,
                roster_index=roster_index,
                tier_watchlist=tier_watchlist,
                output_dir=output_dir,
            )

            self.assertEqual(result["schema_version"], "p1.2-lite-action-cards")
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["output_md"]).exists())
            self.assertEqual(result["summary"]["owned_character_count"], 1)
            self.assertEqual(result["summary"]["pending_snapshot_count"], 0)
            self.assertEqual(result["summary"]["target_count"], 3)
            self.assertEqual(result["summary"]["covered_target_count"], 1)
            self.assertEqual(result["summary"]["uncovered_target_count"], 2)
            self.assertGreaterEqual(result["summary"]["needs_recording_count"], 2)
            self.assertEqual(result["summary"]["tier_signal_count"], 3)
            self.assertEqual(result["summary"]["high_value_owned_action_count"], 1)
            self.assertEqual(result["summary"]["low_value_action_count"], 1)

            train = next(item for item in result["cards"] if item["action_type"] == "train_owned_character")
            self.assertEqual(train["character"], "星见雅")
            self.assertEqual(train["source_class"], "owned_snapshot")
            self.assertEqual(train["status"], "actionable")
            self.assertEqual(train["evidence"]["target_hash"], "abcdef123456")
            self.assertEqual(train["evidence"]["snapshot_source"], "figs/miyabi.jpg")
            self.assertEqual(train["evidence"]["snapshot_json"], "normalized/miyabi.json")
            self.assertEqual(train["links"]["normalized_json"], "normalized/miyabi.json")
            self.assertEqual(train["links"]["snapshot_source"], "figs/miyabi.jpg")
            self.assertEqual(train["tier_signal"]["recommendation"], "protect_investment")
            self.assertIn("优先保护", train["reason"])

            review = next(item for item in result["cards"] if item["character"] == "珂蕾妲")
            self.assertEqual(review["action_type"], "review_candidate")
            self.assertEqual(review["source_class"], "catalog_candidate")
            self.assertIsNone(review["candidate_owned"])
            self.assertEqual(review["status"], "needs_review")
            self.assertIn("stun", review["evidence"]["matched_tags"])
            self.assertEqual(review["evidence"]["target_hash"], "123456abcdef")
            self.assertEqual(review["tier_signal"]["recommendation"], "watch_candidate")
            self.assertIn("不能当作已拥有练度", review["reason"])

            record = next(item for item in result["cards"] if item["character"] == "莱特")
            self.assertEqual(record["action_type"], "record_missing_character")
            self.assertEqual(record["source_class"], "catalog_owned_missing_snapshot")
            self.assertTrue(record["candidate_owned"])
            self.assertEqual(record["priority"], "low")
            self.assertEqual(record["tier_signal"]["recommendation"], "low_priority_candidate")

            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("accepted roster", markdown)
            self.assertIn("珂蕾妲", markdown)
            self.assertIn("tier_signal", markdown)

    def test_build_action_cards_keeps_unaccepted_snapshots_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "training_priority_report.json"
            output_dir = root / "actions"
            report_path.write_text(json.dumps(planner_report(), ensure_ascii=False), encoding="utf-8")

            result = action_tool.build_action_cards(
                planner_report=report_path,
                output_dir=output_dir,
            )

            self.assertEqual(result["summary"]["owned_character_count"], 0)
            self.assertEqual(result["summary"]["pending_snapshot_count"], 1)
            self.assertFalse(any(item["action_type"] == "train_owned_character" for item in result["cards"]))
            pending = next(item for item in result["cards"] if item["action_type"] == "review_pending_snapshot")
            self.assertEqual(pending["character"], "星见雅")
            self.assertEqual(pending["source_class"], "pending_snapshot")
            self.assertEqual(pending["status"], "needs_review")
            self.assertIn("尚未进入 accepted roster", pending["reason"])

    def test_build_action_cards_demotes_low_value_owned_training(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "training_priority_report.json"
            roster_index = root / "roster_index.json"
            tier_watchlist = root / "tier_watchlist.json"
            output_dir = root / "actions"
            report_path.write_text(json.dumps(planner_report(), ensure_ascii=False), encoding="utf-8")
            roster_index.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "characters": [{"name": "星见雅"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tier_watchlist.write_text(
                json.dumps(tier_watchlist_report(miyabi_recommendation="avoid_overinvestment"), ensure_ascii=False),
                encoding="utf-8",
            )

            result = action_tool.build_action_cards(
                planner_report=report_path,
                roster_index=roster_index,
                tier_watchlist=tier_watchlist,
                output_dir=output_dir,
            )

            self.assertFalse(any(item["action_type"] == "train_owned_character" for item in result["cards"]))
            low_value = next(item for item in result["cards"] if item["character"] == "星见雅")
            self.assertEqual(low_value["action_type"], "review_low_value_investment")
            self.assertEqual(low_value["status"], "needs_review")
            self.assertEqual(low_value["priority"], "low")
            self.assertEqual(low_value["tier_signal"]["recommendation"], "avoid_overinvestment")
            self.assertEqual(result["summary"]["low_value_review_count"], 1)
            self.assertIn("不建议为了拿奖励继续加码", low_value["reason"])

    def test_missing_planner_report_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(action_tool.ActionCardError):
                action_tool.build_action_cards(
                    planner_report=root / "missing.json",
                    output_dir=root / "actions",
                )


if __name__ == "__main__":
    unittest.main()
