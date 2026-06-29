from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "preview_review_decisions.py"

preview_spec = importlib.util.spec_from_file_location("preview_review_decisions", PREVIEW_SCRIPT_PATH)
assert preview_spec is not None
preview_tool = importlib.util.module_from_spec(preview_spec)
assert preview_spec.loader is not None
sys.modules[preview_spec.name] = preview_tool
preview_spec.loader.exec_module(preview_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(
    name: str = "雅",
    *,
    review_status: str = "PASS",
    invalid_field_count: int = 0,
    blockers: list[str] | None = None,
) -> dict:
    return {
        "character": {"name": {"value": name}, "level": {"value": 60}},
        "source": {"review_status": review_status},
        "quality": {
            "trusted_field_count": 20,
            "field_count": 24,
            "invalid_field_count": invalid_field_count,
            "blockers": blockers or [],
        },
    }


def run_manifest() -> dict:
    return {"schema_version": "p2.0-lite-run-manifest", "artifact_status": {"consistent": True}}


def review_inbox(normalized_path: Path) -> dict:
    return {
        "schema_version": "p1.4-lite-review-inbox",
        "pending_count": 1,
        "pending": [
            {
                "character": "雅",
                "normalized_json": str(normalized_path),
                "review_html": "data/probes/demo/case_review.html",
                "blockers": [],
            }
        ],
    }


def decision_manifest(
    *,
    decision: str,
    normalized_path: Path,
    review_inbox_path: Path,
    run_manifest_path: Path,
    note: str = "",
    review_hash: str | None = None,
    normalized_hash: str | None = None,
) -> dict:
    return {
        "schema_version": "p2.2-lite-review-decisions-template",
        "source_review_inbox": str(review_inbox_path),
        "source_review_inbox_sha256": review_hash or sha256(review_inbox_path),
        "source_run_manifest": str(run_manifest_path),
        "source_run_manifest_sha256": sha256(run_manifest_path),
        "decisions": [
            {
                "normalized_json": str(normalized_path),
                "normalized_json_sha256": normalized_hash if normalized_hash is not None else sha256(normalized_path),
                "decision": decision,
                "character": "雅",
                "review_html": "data/probes/demo/case_review.html",
                "note": note,
                "blockers": [],
            }
        ],
    }


class ReviewDecisionPreviewTests(unittest.TestCase):
    def build_preview(
        self,
        root: Path,
        *,
        decision: str = "pending",
        snapshot_data: dict | None = None,
        normalized_in_pending: bool = True,
        note: str = "",
        review_hash: str | None = None,
        normalized_hash: str | None = None,
    ) -> dict:
        normalized_path = write_json(root / "normalized" / "miyabi.json", snapshot_data or snapshot())
        pending_path = normalized_path if normalized_in_pending else root / "normalized" / "other.json"
        if not normalized_in_pending:
            write_json(pending_path, snapshot("其他"))
        inbox_path = write_json(root / "review_inbox.json", review_inbox(pending_path))
        run_path = write_json(root / "run_manifest.json", run_manifest())
        decision_path = write_json(
            root / "review_decisions_template.json",
            decision_manifest(
                decision=decision,
                normalized_path=normalized_path,
                review_inbox_path=inbox_path,
                run_manifest_path=run_path,
                note=note,
                review_hash=review_hash,
                normalized_hash=normalized_hash,
            ),
        )
        return preview_tool.preview_review_decisions(
            decision_manifest=decision_path,
            review_inbox=inbox_path,
            run_manifest=run_path,
            roster_index=None,
            output_dir=root / "review_preview",
        )

    def test_template_hash_mismatch_blocks_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(root, decision="accept", review_hash="bad")

            self.assertEqual(result["preview_status"], "blocked")
            self.assertFalse(result["source_check"]["review_inbox_match"])
            self.assertTrue(result["source_check"]["stale_template"])
            self.assertIn("template_source_mismatch", result["items"][0]["blockers"])

    def test_normalized_hash_mismatch_blocks_accept(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(root, decision="accept", normalized_hash="bad")

            self.assertEqual(result["preview_status"], "blocked")
            self.assertFalse(result["items"][0]["normalized_hash_match"])
            self.assertIn("normalized_json_sha256 mismatch", result["items"][0]["blockers"])

    def test_accept_normalized_not_in_pending_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(root, decision="accept", normalized_in_pending=False)

            self.assertEqual(result["preview_status"], "blocked")
            self.assertIn("normalized_json is not in current review_inbox.pending", result["items"][0]["blockers"])

    def test_accept_fail_review_status_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(root, decision="accept", snapshot_data=snapshot(review_status="FAIL"))

            self.assertEqual(result["items"][0]["decision_status"], "blocked")
            self.assertIn("review_status=FAIL cannot be accepted", result["items"][0]["blockers"])

    def test_accept_invalid_candidate_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(
                root,
                decision="accept",
                snapshot_data=snapshot(invalid_field_count=1, blockers=["invalid_candidate fields"]),
            )

            self.assertEqual(result["items"][0]["decision_status"], "blocked")
            self.assertIn("invalid_candidate fields cannot be accepted", result["items"][0]["blockers"])

    def test_accept_with_quality_blockers_needs_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(root, decision="accept", snapshot_data=snapshot(blockers=["low_trusted_field_count"]))

            self.assertEqual(result["preview_status"], "needs_review")
            self.assertEqual(result["items"][0]["decision_status"], "needs_review")
            self.assertFalse(result["items"][0]["would_enter_roster"])

    def test_accept_with_quality_blockers_and_note_is_ready_with_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(
                root,
                decision="accept",
                snapshot_data=snapshot(blockers=["low_trusted_field_count"]),
                note="人工确认可信字段足够，允许覆盖普通质量提示",
            )

            self.assertEqual(result["preview_status"], "ready_with_override")
            self.assertEqual(result["items"][0]["decision_status"], "ready_with_override")
            self.assertTrue(result["items"][0]["would_enter_roster"])

    def test_safe_accept_is_preview_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build_preview(root, decision="accept")

            self.assertEqual(result["preview_status"], "ready")
            self.assertTrue(result["items"][0]["normalized_hash_match"])
            self.assertTrue(result["items"][0]["would_enter_roster"])
            self.assertEqual(result["summary"]["would_update_roster_count"], 1)
            self.assertFalse((root / "accepted").exists())
            self.assertFalse((root / "rejected").exists())

    def test_reject_and_pending_do_not_enter_roster(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rejected = self.build_preview(root, decision="reject")
            pending = self.build_preview(root / "pending_case", decision="pending")

            self.assertFalse(rejected["items"][0]["would_enter_roster"])
            self.assertFalse(pending["items"][0]["would_enter_roster"])
            self.assertEqual(pending["items"][0]["decision_status"], "pending")


if __name__ == "__main__":
    unittest.main()
