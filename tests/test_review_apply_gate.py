from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLY_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "apply_review_decisions.py"
PREVIEW_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "preview_review_decisions.py"

apply_spec = importlib.util.spec_from_file_location("apply_review_decisions", APPLY_SCRIPT_PATH)
assert apply_spec is not None
apply_tool = importlib.util.module_from_spec(apply_spec)
assert apply_spec.loader is not None
sys.modules[apply_spec.name] = apply_tool
apply_spec.loader.exec_module(apply_tool)

preview_spec = importlib.util.spec_from_file_location("preview_review_decisions", PREVIEW_SCRIPT_PATH)
assert preview_spec is not None
preview_tool = importlib.util.module_from_spec(preview_spec)
assert preview_spec.loader is not None
sys.modules[preview_spec.name] = preview_tool
preview_spec.loader.exec_module(preview_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
        "source": {"review_status": review_status},
        "character": {"name": {"value": name}, "level": {"value": 60}},
        "build_snapshot": {"equipment": {"name": {"value": "专属音擎"}}},
        "quality": {
            "trusted_field_count": 20,
            "field_count": 24,
            "invalid_field_count": invalid_field_count,
            "blockers": blockers or [],
        },
    }


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


def run_manifest() -> dict:
    return {"schema_version": "p2.0-lite-run-manifest", "artifact_status": {"consistent": True}}


def decision_manifest(
    *,
    decision: str,
    normalized_path: Path,
    inbox_path: Path,
    run_path: Path,
    note: str = "",
) -> dict:
    return {
        "schema_version": "p2.4-lite-review-decisions-template",
        "source_review_inbox": str(inbox_path),
        "source_review_inbox_sha256": sha256(inbox_path),
        "source_run_manifest": str(run_path),
        "source_run_manifest_sha256": sha256(run_path),
        "decisions": [
            {
                "normalized_json": str(normalized_path),
                "normalized_json_sha256": sha256(normalized_path),
                "decision": decision,
                "character": "雅",
                "review_html": "data/probes/demo/case_review.html",
                "note": note,
                "blockers": [],
            }
        ],
    }


def build_case(
    root: Path,
    *,
    decision: str = "accept",
    snapshot_data: dict | None = None,
    note: str = "",
) -> tuple[Path, Path, Path, Path, Path]:
    normalized_dir = root / "normalized"
    normalized_path = write_json(normalized_dir / "miyabi.json", snapshot_data or snapshot())
    inbox_path = write_json(root / "review_inbox.json", review_inbox(normalized_path))
    run_path = write_json(root / "run_manifest.json", run_manifest())
    decision_path = write_json(
        root / "review_decisions.json",
        decision_manifest(
            decision=decision,
            normalized_path=normalized_path,
            inbox_path=inbox_path,
            run_path=run_path,
            note=note,
        ),
    )
    return normalized_dir, normalized_path, inbox_path, run_path, decision_path


def build_preview(root: Path, *, decision_path: Path, inbox_path: Path, run_path: Path) -> Path:
    result = preview_tool.preview_review_decisions(
        decision_manifest=decision_path,
        review_inbox=inbox_path,
        run_manifest=run_path,
        roster_index=None,
        output_dir=root / "review_preview",
    )
    return Path(result["output_json"])


class ReviewApplyGateTests(unittest.TestCase):
    def test_accept_without_preview_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, _inbox_path, _run_path, decision_path = build_case(root)

            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "require --preview-result"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                )

    def test_blocked_preview_fails_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(
                root,
                snapshot_data=snapshot(review_status="FAIL"),
            )
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)

            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "preview_result.preview_status"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                    preview_result=preview_path,
                    require_preview_ready=True,
                )

    def test_needs_review_preview_without_note_fails_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(
                root,
                snapshot_data=snapshot(blockers=["low_trusted_field_count"]),
            )
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)

            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "preview_result.preview_status"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                    preview_result=preview_path,
                    require_preview_ready=True,
                )

    def test_normalized_changed_after_preview_fails_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, normalized_path, inbox_path, run_path, decision_path = build_case(root)
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)
            write_json(normalized_path, snapshot(name="雅", blockers=["changed_after_preview"]))

            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "changed after preview"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                    preview_result=preview_path,
                    require_preview_ready=True,
                )

    def test_decision_manifest_changed_after_preview_fails_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(root)
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)
            data = json.loads(decision_path.read_text(encoding="utf-8"))
            data["decisions"][0]["note"] = "changed after preview"
            write_json(decision_path, data)

            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "decision_manifest hash"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                    preview_result=preview_path,
                    require_preview_ready=True,
                )

    def test_review_inbox_or_run_manifest_hash_mismatch_blocks_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(root)
            write_json(inbox_path, {"schema_version": "changed", "pending": []})
            write_json(run_path, {"schema_version": "changed", "artifact_status": {"consistent": False}})
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)
            preview = json.loads(preview_path.read_text(encoding="utf-8"))

            self.assertEqual(preview["preview_status"], "blocked")
            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "preview_result.preview_status"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                    preview_result=preview_path,
                    require_preview_ready=True,
                )

    def test_safe_accept_writes_apply_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(root)
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)

            result = apply_tool.apply_review_decisions(
                normalized_dir=normalized_dir,
                decision_manifest=decision_path,
                roster_dir=root / "roster",
                preview_result=preview_path,
                require_preview_ready=True,
            )

            self.assertEqual(result["summary"]["accepted_count"], 1)
            accepted_files = list((root / "roster" / "accepted").glob("*.json"))
            self.assertEqual(len(accepted_files), 1)
            accepted = json.loads(accepted_files[0].read_text(encoding="utf-8"))
            self.assertEqual(accepted["review_apply_audit"]["schema_version"], "p2.4-lite-review-apply-audit")
            self.assertEqual(accepted["review_apply_audit"]["decision_manifest"], str(decision_path))
            self.assertEqual(accepted["review_apply_audit"]["preview_result"], str(preview_path))
            self.assertTrue(accepted["review_apply_audit"]["normalized_json_sha256"])
            receipt = json.loads(Path(result["receipt_json"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema_version"], "p2.5-lite-review-apply-receipt")
            self.assertEqual(receipt["summary"]["did_enter_roster_count"], 1)
            self.assertEqual(receipt["summary"]["preview_validated_count"], 1)
            self.assertTrue(receipt["records"][0]["did_enter_roster"])

    def test_reject_with_changed_manifest_preview_fails_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(root, decision="reject")
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)
            data = json.loads(decision_path.read_text(encoding="utf-8"))
            data["decisions"][0]["note"] = "changed reject after preview"
            write_json(decision_path, data)

            with self.assertRaisesRegex(apply_tool.ReviewDecisionError, "decision_manifest hash"):
                apply_tool.apply_review_decisions(
                    normalized_dir=normalized_dir,
                    decision_manifest=decision_path,
                    roster_dir=root / "roster",
                    preview_result=preview_path,
                )

    def test_reject_without_preview_writes_rejected_not_roster_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, _inbox_path, _run_path, decision_path = build_case(root, decision="reject")

            result = apply_tool.apply_review_decisions(
                normalized_dir=normalized_dir,
                decision_manifest=decision_path,
                roster_dir=root / "roster",
            )

            self.assertEqual(result["summary"]["rejected_count"], 1)
            self.assertTrue(list((root / "roster" / "rejected").glob("*.json")))
            self.assertIsNone(result["roster_index"])
            self.assertFalse((root / "roster" / "roster_index.json").exists())
            receipt = json.loads(Path(result["receipt_json"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["summary"]["did_write_rejected_count"], 1)
            self.assertEqual(receipt["summary"]["preview_not_provided_count"], 1)
            self.assertTrue(receipt["records"][0]["did_write_rejected"])
            self.assertIn("not_provided", " ".join(receipt["warnings"]))

    def test_pending_without_preview_writes_no_accepted_or_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, _inbox_path, _run_path, decision_path = build_case(root, decision="pending")

            result = apply_tool.apply_review_decisions(
                normalized_dir=normalized_dir,
                decision_manifest=decision_path,
                roster_dir=root / "roster",
            )

            self.assertEqual(result["summary"]["pending_count"], 1)
            self.assertFalse((root / "roster" / "accepted").exists())
            self.assertFalse((root / "roster" / "rejected").exists())
            receipt = json.loads(Path(result["receipt_json"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["summary"]["pending_count"], 1)
            self.assertEqual(receipt["summary"]["did_write_accepted_count"], 0)
            self.assertEqual(receipt["summary"]["did_write_rejected_count"], 0)

    def test_cli_preview_result_requires_ready_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir, _normalized_path, inbox_path, run_path, decision_path = build_case(root, decision="pending")
            preview_path = build_preview(root, decision_path=decision_path, inbox_path=inbox_path, run_path=run_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(APPLY_SCRIPT_PATH),
                    "--normalized-dir",
                    str(normalized_dir),
                    "--decision-manifest",
                    str(decision_path),
                    "--roster-dir",
                    str(root / "roster"),
                    "--preview-result",
                    str(preview_path),
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("preview_result.preview_status", completed.stderr)


if __name__ == "__main__":
    unittest.main()
