from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINAL_BRIEF_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_final_brief.py"

brief_spec = importlib.util.spec_from_file_location("build_final_brief", FINAL_BRIEF_SCRIPT_PATH)
assert brief_spec is not None
brief_tool = importlib.util.module_from_spec(brief_spec)
assert brief_spec.loader is not None
sys.modules[brief_spec.name] = brief_tool
brief_spec.loader.exec_module(brief_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def run_manifest(*, consistent: bool = True) -> dict:
    status = {"consistent": consistent, "missing": [], "stale_or_mismatched": [], "warnings": []}
    if not consistent:
        status["stale_or_mismatched"] = ["team_cards"]
        status["warnings"] = ["team cards 输入与本轮 roster 不一致"]
    return {
        "schema_version": "p2.0-lite-run-manifest",
        "artifact_status": status,
        "inputs": {},
    }


def roster_index() -> dict:
    return {
        "schema_version": "p1.4-lite-roster-index",
        "characters": [
            {"name": "星见雅", "source_class": "owned_snapshot"},
            {"name": "苍角", "source_class": "owned_snapshot"},
        ],
    }


def review_inbox(*, pending: bool = False) -> dict:
    pending_items = []
    if pending:
        pending_items.append(
            {
                "character": "雅",
                "review_html": "data/probes/demo/case_review.html",
                "normalized_json": "data/probes/demo/case_normalized.json",
                "blockers": ["requires_manual_review"],
            }
        )
    return {
        "schema_version": "p1.4-lite-review-inbox",
        "pending_count": len(pending_items),
        "accepted_count": 2,
        "rejected_count": 0,
        "pending": pending_items,
        "decision_command": "python tools/probes/apply_review_decisions.py --decision-manifest data/probes/review_decisions.json",
    }


def ready_endgame_plan() -> dict:
    return {
        "schema_version": "p2.0-lite-endgame-plan",
        "summary": {
            "target_count": 1,
            "ready_now_count": 1,
            "needs_review_count": 0,
            "needs_recording_count": 0,
            "watch_only_count": 0,
            "trusted_plan_count": 1,
            "warning_plan_count": 0,
        },
        "target_plans": [
            {
                "target": "危局强袭战 稳定通关",
                "plan_status": "ready_now",
                "plan_trust_level": "trusted",
                "recommended_line": "全员来自 accepted roster，可先尝试一次。",
                "evidence": {"target_source": "local", "target_hash": "abcdef123456"},
                "team_candidates": [
                    {
                        "members": [
                            {"character": "星见雅", "source_class": "owned_snapshot", "source_class_effective": "owned_snapshot"},
                            {"character": "苍角", "source_class": "owned_snapshot", "source_class_effective": "owned_snapshot"},
                        ],
                        "rank_reason": "本地确认队伍。",
                    }
                ],
            }
        ],
    }


def fresh_refresh_status() -> dict:
    return {
        "schema_version": "p2.7-lite-refresh-status",
        "refresh_status": "fresh",
        "summary": {"needs_demo_refresh": False},
        "stale_reasons": [],
        "refresh_command": "python tools/probes/run_demo_pipeline.py --clean-demo",
        "warnings": [],
    }


def many_ready_endgame_plan(count: int = 6) -> dict:
    plans = []
    for index in range(count):
        plans.append(
            {
                "target": f"危局强袭战 {index}",
                "plan_status": "ready_now",
                "plan_trust_level": "trusted",
                "recommended_line": "全员来自 accepted roster，可先尝试一次。",
                "evidence": {"target_source": "local", "target_hash": f"hash{index}"},
                "team_candidates": [
                    {
                        "members": [
                            {"character": "星见雅", "source_class": "owned_snapshot", "source_class_effective": "owned_snapshot"},
                        ],
                        "rank_reason": "本地确认队伍。",
                    }
                ],
            }
        )
    return {
        "schema_version": "p2.0-lite-endgame-plan",
        "summary": {
            "target_count": count,
            "ready_now_count": count,
            "needs_review_count": 0,
            "needs_recording_count": 0,
            "watch_only_count": 0,
            "trusted_plan_count": count,
            "warning_plan_count": 0,
        },
        "target_plans": plans,
    }


def mixed_endgame_plan() -> dict:
    return {
        "schema_version": "p2.0-lite-endgame-plan",
        "summary": {
            "target_count": 3,
            "ready_now_count": 0,
            "needs_review_count": 0,
            "needs_recording_count": 1,
            "watch_only_count": 1,
            "trusted_plan_count": 0,
            "warning_plan_count": 1,
        },
        "target_plans": [
            {
                "target": "式舆防卫战 满星尝试",
                "plan_status": "needs_recording",
                "plan_trust_level": "warning",
                "next_actions": [{"action_type": "record_missing_character", "character": "莱卡恩"}],
            },
            {
                "target": "危局强袭战 火弱点",
                "plan_status": "watch_only",
                "plan_trust_level": "warning",
                "warnings": ["catalog candidate 不代表已拥有。"],
            },
        ],
    }


class FinalBriefTests(unittest.TestCase):
    MISSING_REFRESH = object()

    def build(
        self,
        root: Path,
        *,
        manifest: dict | None = None,
        inbox: dict | None = None,
        endgame: dict | None = None,
        refresh: object = None,
    ) -> dict:
        manifest_path = write_json(root / "run_manifest.json", manifest if manifest is not None else run_manifest())
        roster_path = write_json(root / "roster_index.json", roster_index())
        inbox_path = write_json(root / "review_inbox.json", inbox if inbox is not None else review_inbox())
        endgame_path = write_json(root / "endgame_plan.json", endgame if endgame is not None else ready_endgame_plan())
        if refresh is self.MISSING_REFRESH:
            refresh_path = None
        else:
            refresh_path = write_json(root / "refresh_status.json", refresh if isinstance(refresh, dict) else fresh_refresh_status())
        return brief_tool.build_final_brief(
            output_dir=root / "final_brief",
            run_manifest=manifest_path,
            roster_index=roster_path,
            review_inbox=inbox_path,
            endgame_plan=endgame_path,
            refresh_status=refresh_path,
        )

    def test_consistent_manifest_and_trusted_ready_now_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root)

            self.assertEqual(result["schema_version"], "p2.1-lite-final-brief")
            self.assertEqual(result["brief_status"], "ready")
            self.assertEqual(result["top_cards"][0]["card_type"], "try_now")
            self.assertEqual(result["summary"]["ready_now_target_count"], 1)
            self.assertTrue(Path(result["output_json"]).exists())

    def test_mismatched_manifest_makes_first_card_data_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root, manifest=run_manifest(consistent=False))

            self.assertNotEqual(result["brief_status"], "ready")
            self.assertEqual(result["top_cards"][0]["card_type"], "data_warning")
            self.assertNotIn("try_now", {item["card_type"] for item in result["top_cards"]})
            self.assertIn("team_cards", " ".join(result["red_flags"]))
            self.assertNotIn("demo_manifest.json", " ".join(result["next_commands"]))

    def test_stale_refresh_status_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh={
                    "schema_version": "p2.7-lite-refresh-status",
                    "refresh_status": "stale_after_apply",
                    "summary": {"needs_demo_refresh": True},
                    "stale_reasons": ["review_apply_receipt.created_at is newer than run_manifest.created_at"],
                    "refresh_command": "python tools/probes/run_demo_pipeline.py --clean-demo",
                    "warnings": [],
                },
            )

            self.assertNotEqual(result["brief_status"], "ready")
            self.assertEqual(result["top_cards"][0]["card_type"], "data_warning")
            self.assertNotIn("try_now", {item["card_type"] for item in result["top_cards"]})
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertIn("Safe apply 已改变 accepted roster", " ".join(result["warnings"]))
            self.assertIn("--clean-demo", " ".join(result["next_commands"]))

    def test_unknown_refresh_status_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh={
                    "schema_version": "p2.7-lite-refresh-status",
                    "refresh_status": "unknown",
                    "summary": {"needs_demo_refresh": True},
                    "stale_reasons": [],
                    "refresh_command": "python tools/probes/run_demo_pipeline.py --clean-demo",
                    "warnings": ["run_manifest 缺少可解析 created_at"],
                },
            )

            self.assertNotEqual(result["brief_status"], "ready")
            self.assertEqual(result["top_cards"][0]["card_type"], "data_warning")
            self.assertNotIn("try_now", {item["card_type"] for item in result["top_cards"]})
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertIn("无法确认 demo 是否已吸收最新 apply", " ".join(result["warnings"]))
            self.assertIn("--clean-demo", " ".join(result["next_commands"]))

    def test_missing_refresh_status_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root, refresh=self.MISSING_REFRESH)

            self.assertNotEqual(result["brief_status"], "ready")
            self.assertEqual(result["top_cards"][0]["card_type"], "data_warning")
            self.assertNotIn("try_now", {item["card_type"] for item in result["top_cards"]})
            self.assertIn("缺少 refresh_status", " ".join(result["warnings"]))

    def test_pending_snapshot_is_review_snapshot_not_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            no_ready = ready_endgame_plan()
            no_ready["summary"]["ready_now_count"] = 0
            no_ready["summary"]["trusted_plan_count"] = 0
            no_ready["target_plans"] = []
            result = self.build(root, inbox=review_inbox(pending=True), endgame=no_ready)

            self.assertEqual(result["brief_status"], "needs_review")
            self.assertEqual(result["top_cards"][0]["card_type"], "review_snapshot")
            self.assertEqual(result["top_cards"][0]["evidence"]["normalized_json"], "data/probes/demo/case_normalized.json")
            self.assertNotIn("try_now", {item["card_type"] for item in result["top_cards"]})

    def test_ready_with_pending_is_not_plain_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root, inbox=review_inbox(pending=True), endgame=ready_endgame_plan())

            self.assertEqual(result["brief_status"], "ready_with_pending")
            self.assertIn("try_now", {item["card_type"] for item in result["top_cards"]})
            self.assertIn("review_snapshot", {item["card_type"] for item in result["top_cards"]})

    def test_top_cards_are_capped_and_hidden_count_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            endgame = many_ready_endgame_plan()
            mixed = mixed_endgame_plan()
            endgame["target_plans"].extend(mixed["target_plans"])
            endgame["summary"]["needs_recording_count"] = 1
            endgame["summary"]["watch_only_count"] = 1
            result = self.build(root, inbox=review_inbox(pending=True), endgame=endgame)

            self.assertLessEqual(len(result["top_cards"]), 5)
            self.assertGreater(result["hidden_card_count"], 0)
            self.assertGreater(result["summary"]["hidden_card_count"], 0)

    def test_needs_recording_and_watch_only_cards_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root, endgame=mixed_endgame_plan())
            card_types = [item["card_type"] for item in result["top_cards"]]

            self.assertEqual(result["brief_status"], "needs_review")
            self.assertIn("record_character", card_types)
            self.assertIn("watch_only", card_types)
            watch_card = next(item for item in result["top_cards"] if item["card_type"] == "watch_only")
            self.assertIn("不是抽卡建议", watch_card["reason"])
            self.assertIn("不是抽卡建议", " ".join(watch_card["warnings"]))

    def test_no_trusted_ready_now_cannot_be_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root, endgame=mixed_endgame_plan())

            self.assertEqual(result["brief_status"], "needs_review")
            self.assertEqual(result["summary"]["ready_now_target_count"], 0)

    def test_markdown_first_lines_and_sensitive_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root)
            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            first_lines = "\n".join(markdown.splitlines()[:10])
            serialized = json.dumps(result, ensure_ascii=False).lower()

            self.assertIn("今天先做什么", first_lines)
            self.assertIn("当前状态：可继续", first_lines)
            self.assertIn("按清单试一次", markdown)
            self.assertIn("## 概览", markdown)
            self.assertIn("已确认角色: 2", markdown)
            self.assertIn("可直接尝试目标: 1", markdown)
            self.assertNotIn("## Summary", markdown)
            self.assertNotIn("[try_now]", markdown)
            self.assertNotIn("ready_now_target_count", markdown)
            self.assertNotIn("cookie", serialized)
            self.assertNotIn("token", serialized)
            self.assertNotIn("uid", serialized)


if __name__ == "__main__":
    unittest.main()
