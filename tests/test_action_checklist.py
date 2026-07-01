from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_action_checklist.py"

checklist_spec = importlib.util.spec_from_file_location("build_action_checklist", CHECKLIST_SCRIPT_PATH)
assert checklist_spec is not None
checklist_tool = importlib.util.module_from_spec(checklist_spec)
assert checklist_spec.loader is not None
sys.modules[checklist_spec.name] = checklist_tool
checklist_spec.loader.exec_module(checklist_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def final_brief(cards: list[dict], *, warnings: list[str] | None = None) -> dict:
    return {
        "schema_version": "p2.1-lite-final-brief",
        "brief_status": "needs_review" if warnings else "ready",
        "summary": {},
        "top_cards": cards,
        "warnings": warnings or [],
    }


def review_inbox() -> dict:
    return {
        "schema_version": "p1.4-lite-review-inbox",
        "pending_count": 1,
        "pending": [
            {
                "character": "雅",
                "review_html": "data/probes/demo/case_review.html",
                "normalized_json": "data/probes/demo/case_normalized.json",
                "blockers": ["requires_manual_review"],
            }
        ],
    }


def run_manifest(*, consistent: bool = True) -> dict:
    status = {"consistent": consistent, "missing": [], "stale_or_mismatched": [], "warnings": []}
    if not consistent:
        status["stale_or_mismatched"] = ["team_cards"]
        status["warnings"] = ["team cards 输入与本轮 roster 不一致"]
    return {"schema_version": "p2.0-lite-run-manifest", "artifact_status": status}


def fresh_refresh_status() -> dict:
    return {
        "schema_version": "p2.7-lite-refresh-status",
        "refresh_status": "fresh",
        "summary": {"needs_demo_refresh": False},
        "stale_reasons": [],
        "warnings": [],
    }


class ActionChecklistTests(unittest.TestCase):
    MISSING_REFRESH = object()

    def build(
        self,
        root: Path,
        *,
        brief: dict,
        inbox: dict | None = None,
        manifest: dict | None = None,
        refresh: object = None,
    ) -> dict:
        brief_path = write_json(root / "final_brief.json", brief)
        inbox_path = write_json(root / "review_inbox.json", inbox if inbox is not None else review_inbox())
        manifest_path = write_json(root / "run_manifest.json", manifest if manifest is not None else run_manifest())
        if refresh is self.MISSING_REFRESH:
            refresh_path = None
        else:
            refresh_path = write_json(root / "refresh_status.json", refresh if isinstance(refresh, dict) else fresh_refresh_status())
        return checklist_tool.build_action_checklist(
            final_brief=brief_path,
            review_inbox=inbox_path,
            run_manifest=manifest_path,
            refresh_status=refresh_path,
            output_dir=root / "action_checklist",
        )

    def test_data_warning_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {"card_type": "data_warning", "title": "先确认数据", "warnings": ["错批"]},
                        {"card_type": "try_now", "title": "可先尝试", "character": "星见雅"},
                    ],
                    warnings=["错批"],
                ),
                manifest=run_manifest(consistent=False),
            )

            self.assertEqual(result["checklist_status"], "blocked")
            self.assertEqual(result["items"][0]["item_type"], "data_warning")
            try_now = next(item for item in result["items"] if item["item_type"] == "try_now")
            self.assertEqual(try_now["status"], "blocked")
            self.assertIn("blocked_by_data_warning", try_now["warnings"])
            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("当前状态：已阻断", markdown)
            self.assertIn("已阻断：先处理数据一致性", markdown)
            self.assertIn("## 概览", markdown)
            self.assertIn("已阻断: 2", markdown)
            self.assertIn("## 复核决策模板", markdown)
            self.assertIn("## 复核决策预览", markdown)
            self.assertIn("## 安全应用", markdown)
            self.assertNotIn("[blocked]", markdown)
            self.assertNotIn("try_now", markdown)
            self.assertNotIn("## Warnings", markdown)

    def test_stale_refresh_status_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {"card_type": "try_now", "title": "可先尝试", "character": "星见雅"},
                    ]
                ),
                refresh={
                    "schema_version": "p2.7-lite-refresh-status",
                    "refresh_status": "stale_after_apply",
                    "summary": {"needs_demo_refresh": True},
                    "stale_reasons": ["roster_index sha256 differs from run_manifest inputs.roster_index.sha256"],
                    "warnings": [],
                },
            )

            self.assertEqual(result["checklist_status"], "blocked")
            self.assertEqual(result["items"][0]["item_type"], "data_warning")
            try_now = next(item for item in result["items"] if item["item_type"] == "try_now")
            self.assertEqual(try_now["status"], "blocked")
            self.assertIn("blocked_by_data_warning", try_now["warnings"])
            self.assertIn("blocked_by_stale_apply_receipt", " ".join(result["warnings"]))

    def test_fresh_refresh_status_warning_does_not_block_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {"card_type": "try_now", "title": "可先尝试", "character": "星见雅"},
                    ]
                ),
                refresh={
                    "schema_version": "p2.7-lite-refresh-status",
                    "refresh_status": "fresh",
                    "summary": {"needs_demo_refresh": False},
                    "warnings": ["receipt 只记录 rejected/pending 副作用，未改变 accepted roster。"],
                },
            )

            self.assertEqual(result["checklist_status"], "ready")
            self.assertEqual(result["items"][0]["item_type"], "try_now")
            self.assertEqual(result["items"][0]["status"], "ready")

    def test_unknown_refresh_status_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {"card_type": "try_now", "title": "可先尝试", "character": "星见雅"},
                    ]
                ),
                refresh={
                    "schema_version": "p2.7-lite-refresh-status",
                    "refresh_status": "unknown",
                    "summary": {"needs_demo_refresh": True},
                    "stale_reasons": [],
                    "warnings": ["run_manifest 缺少可解析 created_at"],
                },
            )

            self.assertEqual(result["checklist_status"], "blocked")
            self.assertEqual(result["items"][0]["item_type"], "data_warning")
            try_now = next(item for item in result["items"] if item["item_type"] == "try_now")
            self.assertEqual(try_now["status"], "blocked")
            self.assertIn("blocked_by_unknown_refresh_status", " ".join(result["warnings"]))

    def test_missing_refresh_status_blocks_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {"card_type": "try_now", "title": "可先尝试", "character": "星见雅"},
                    ]
                ),
                refresh=self.MISSING_REFRESH,
            )

            self.assertEqual(result["checklist_status"], "blocked")
            self.assertEqual(result["items"][0]["item_type"], "data_warning")
            try_now = next(item for item in result["items"] if item["item_type"] == "try_now")
            self.assertEqual(try_now["status"], "blocked")
            self.assertIn("blocked_by_missing_refresh_status", " ".join(result["warnings"]))

    def test_review_snapshot_generates_pending_decision_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {
                            "card_type": "review_snapshot",
                            "title": "复核 雅 的解析快照",
                            "character": "雅",
                            "evidence": {
                                "review_html": "data/probes/demo/case_review.html",
                                "normalized_json": "data/probes/demo/case_normalized.json",
                            },
                        }
                    ]
                ),
            )
            template = json.loads(Path(result["review_decisions_template"]).read_text(encoding="utf-8"))

            self.assertEqual(result["checklist_status"], "needs_review")
            self.assertEqual(result["items"][0]["status"], "needs_review")
            self.assertEqual(result["items"][0]["evidence"]["review_html"], "data/probes/demo/case_review.html")
            self.assertEqual(result["items"][0]["evidence"]["normalized_json"], "data/probes/demo/case_normalized.json")
            self.assertEqual(template["decisions"][0]["decision"], "pending")
            self.assertNotEqual(template["decisions"][0]["decision"], "accept")
            self.assertIn("normalized_json_sha256", template["decisions"][0])
            self.assertIsNone(template["decisions"][0]["normalized_json_sha256"])
            self.assertIn("normalized_json 不存在", " ".join(template["template_warnings"]))
            self.assertTrue(template["source_review_inbox_sha256"])
            self.assertTrue(template["source_run_manifest_sha256"])
            self.assertIn("action_checklist.json", template["source_action_checklist"])
            self.assertIn("preview_review_decisions.py", result["preview_command"])
            self.assertIn("--preview-result", result["safe_apply_command"])
            self.assertIn("--require-preview-ready", result["safe_apply_command"])

    def test_watch_only_keeps_non_gacha_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {
                            "card_type": "watch_only",
                            "title": "仅观察：火弱点",
                            "reason": "不是抽卡建议",
                            "warnings": ["catalog candidate 不代表已拥有。"],
                        }
                    ]
                ),
            )

            self.assertEqual(result["items"][0]["item_type"], "watch_only")
            self.assertIn("不是抽卡建议", " ".join(result["items"][0]["warnings"]))

    def test_record_character_does_not_create_roster_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [{"card_type": "record_character", "title": "补录 莱卡恩 的官方分享图", "character": "莱卡恩"}]
                ),
            )

            self.assertEqual(result["items"][0]["item_type"], "record_character")
            self.assertFalse((root / "roster").exists())

    def test_pending_or_catalog_marker_cannot_be_ready_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                brief=final_brief(
                    [
                        {
                            "card_type": "try_now",
                            "title": "可先尝试",
                            "character": "catalog_candidate",
                            "warnings": ["catalog_candidate"],
                        }
                    ]
                ),
            )

            self.assertEqual(result["items"][0]["item_type"], "try_now")
            self.assertEqual(result["items"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
