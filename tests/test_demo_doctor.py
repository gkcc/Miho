from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_demo_doctor.py"

doctor_spec = importlib.util.spec_from_file_location("build_demo_doctor", DOCTOR_SCRIPT_PATH)
assert doctor_spec is not None
doctor_tool = importlib.util.module_from_spec(doctor_spec)
assert doctor_spec.loader is not None
sys.modules[doctor_spec.name] = doctor_tool
doctor_spec.loader.exec_module(doctor_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh(status: str = "fresh", *, safe_to_rerun: bool = True) -> dict:
    return {
        "schema_version": "p2.7-lite-refresh-status",
        "refresh_status": status,
        "refresh_command": "python tools/probes/run_demo_pipeline.py --manifest data/probes/demo_manifest.json",
        "command_state": {"safe_to_rerun": safe_to_rerun},
    }


def checklist(*, item_type: str = "try_now", item_status: str = "ready", ready_try_now_count: int = 1) -> dict:
    items = [{"item_type": item_type, "status": item_status, "title": "unit"}]
    if item_type == "try_now" and item_status == "ready" and ready_try_now_count > 1:
        items.extend({"item_type": "try_now", "status": "ready", "title": f"unit {index}"} for index in range(2, ready_try_now_count + 1))
    return {
        "schema_version": "p2.2-lite-action-checklist",
        "checklist_status": "ready",
        "preview_command": "python tools/probes/preview_review_decisions.py --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json",
        "safe_apply_command": "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json --roster-dir data/probes/roster --preview-result data/probes/demo/review_preview/review_decision_preview.json --require-preview-ready",
        "items": items,
    }


def preview(
    *,
    status: str = "missing",
    accept_count: int = 0,
    blocked_accept_count: int = 0,
    override_accept_count: int = 0,
    would_update: int = 0,
) -> dict:
    return {
        "schema_version": "p2.3-lite-review-decision-preview",
        "preview_status": status,
        "input": {"decision_manifest_sha256": "decision-hash"},
        "summary": {
            "accept_count": accept_count,
            "blocked_accept_count": blocked_accept_count,
            "override_accept_count": override_accept_count,
            "would_update_roster_count": would_update,
        },
    }


class DemoDoctorTests(unittest.TestCase):
    def build(self, root: Path, **parts: dict | None) -> dict:
        paths: dict[str, Path | None] = {}
        for name, data in parts.items():
            paths[name] = write_json(root / f"{name}.json", data) if data is not None else None
        return doctor_tool.build_demo_doctor(
            output_dir=root / "doctor",
            refresh_status=paths.get("refresh_status"),
            final_brief=paths.get("final_brief"),
            action_checklist=paths.get("action_checklist"),
            review_inbox=paths.get("review_inbox"),
            review_preview=paths.get("review_preview"),
            review_apply_receipt=paths.get("review_apply_receipt"),
            run_manifest=paths.get("run_manifest"),
            demo_command=paths.get("demo_command"),
        )

    def test_stale_refresh_blocks_ready_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("stale_after_apply"),
                action_checklist=checklist(),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "needs_rerun")
        self.assertFalse(result["try_now_allowed"])
        self.assertTrue(result["rerun_required"])
        self.assertIn("ready_try_now_not_actionable_under_current_doctor_status", result["blocking_reasons"])

    def test_fresh_ready_try_now_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "ready_to_try")
        self.assertTrue(result["try_now_allowed"])
        self.assertEqual(result["primary_next_action"], "try_now")
        self.assertFalse(result["action_contract"]["allowed_for_launcher"])
        self.assertFalse(result["action_contract"]["writes_roster"])
        self.assertIn("user gameplay action", result["action_contract"]["reason"])

    def test_ready_preview_with_accepts_requires_safe_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(item_type="review_snapshot"),
                review_preview=preview(status="ready", accept_count=1, would_update=1),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "needs_apply")
        self.assertTrue(result["safe_apply_required"])
        self.assertFalse(result["try_now_allowed"])
        self.assertEqual(result["evidence_check"]["status"], "warning")
        self.assertEqual(result["evidence_check"]["strict_status"], "needs_apply")
        self.assertIn("apply_receipt_missing_for_ready_preview", result["evidence_check"]["warnings"])
        self.assertEqual(result["summary"]["preview_accept_count"], 1)
        self.assertEqual(result["summary"]["preview_blocked_accept_count"], 0)
        self.assertEqual(result["summary"]["preview_override_accept_count"], 0)
        self.assertEqual(result["summary"]["preview_would_update_roster_count"], 1)
        self.assertFalse(result["action_contract"]["allowed_for_launcher"])
        self.assertTrue(result["action_contract"]["writes_roster"])
        self.assertTrue(result["action_contract"]["requires_manual_confirmation"])

    def test_doctor_summary_carries_preview_blocked_and_override_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(item_type="review_snapshot"),
                review_preview=preview(
                    status="blocked",
                    accept_count=3,
                    blocked_accept_count=2,
                    override_accept_count=1,
                    would_update=1,
                ),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["summary"]["preview_accept_count"], 3)
        self.assertEqual(result["summary"]["preview_blocked_accept_count"], 2)
        self.assertEqual(result["summary"]["preview_override_accept_count"], 1)
        self.assertEqual(result["summary"]["preview_would_update_roster_count"], 1)

    def test_apply_receipt_missing_preview_hash_needs_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(item_type="review_snapshot"),
                review_preview=preview(status="ready", accept_count=1, would_update=1),
                review_apply_receipt={
                    "schema_version": "p2.5-lite-review-apply-receipt",
                    "input": {"decision_manifest_sha256": "decision-hash"},
                },
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "needs_apply")
        self.assertEqual(result["evidence_check"]["status"], "warning")
        self.assertEqual(result["evidence_check"]["strict_status"], "needs_apply")
        self.assertFalse(result["evidence_check"]["matched_preview_apply"])
        self.assertIn("apply_receipt_preview_result_sha256_missing", result["evidence_check"]["warnings"])

    def test_apply_receipt_missing_decision_hash_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preview_path = write_json(root / "review_preview.json", preview(status="ready", accept_count=1, would_update=1))
            receipt = {
                "schema_version": "p2.5-lite-review-apply-receipt",
                "input": {"preview_result_sha256": sha256(preview_path)},
            }
            result = doctor_tool.build_demo_doctor(
                output_dir=root / "doctor",
                refresh_status=write_json(root / "refresh_status.json", refresh("fresh")),
                action_checklist=write_json(root / "action_checklist.json", checklist(item_type="review_snapshot")),
                review_preview=preview_path,
                review_apply_receipt=write_json(root / "review_apply_receipt.json", receipt),
                run_manifest=write_json(root / "run_manifest.json", {"schema_version": "run"}),
            )
        self.assertEqual(result["doctor_status"], "blocked")
        self.assertEqual(result["primary_next_action"], "repair_evidence_mismatch")
        self.assertEqual(result["evidence_check"]["strict_status"], "blocked")
        self.assertIn("apply_receipt_decision_manifest_sha256_missing", result["evidence_check"]["blockers"])

    def test_old_apply_receipt_does_not_satisfy_current_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(item_type="review_snapshot"),
                review_preview=preview(status="ready", accept_count=1, would_update=1),
                review_apply_receipt={
                    "schema_version": "p2.5-lite-review-apply-receipt",
                    "input": {"preview_result_sha256": "old-preview", "decision_manifest_sha256": "decision-hash"},
                },
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "needs_apply")
        self.assertEqual(result["evidence_check"]["status"], "warning")
        self.assertEqual(result["evidence_check"]["strict_status"], "needs_apply")
        self.assertFalse(result["evidence_check"]["matched_preview_apply"])
        self.assertIn("apply_receipt_preview_result_sha256_mismatch", result["evidence_check"]["warnings"])

    def test_decision_manifest_mismatch_blocks_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(item_type="review_snapshot"),
                review_preview=preview(status="ready", accept_count=1, would_update=1),
                review_apply_receipt={
                    "schema_version": "p2.5-lite-review-apply-receipt",
                    "input": {"decision_manifest_sha256": "old-decision"},
                },
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "blocked")
        self.assertEqual(result["primary_next_action"], "repair_evidence_mismatch")
        self.assertEqual(result["evidence_check"]["status"], "blocked")
        self.assertEqual(result["evidence_check"]["strict_status"], "blocked")
        self.assertIn("apply_receipt_decision_manifest_sha256_mismatch", result["evidence_check"]["blockers"])

    def test_preview_run_manifest_mismatch_blocks_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = write_json(root / "run_manifest.json", {"schema_version": "run"})
            preview_data = preview(status="ready", accept_count=1, would_update=1)
            preview_data["input"]["run_manifest_sha256"] = "old-run"
            result = doctor_tool.build_demo_doctor(
                output_dir=root / "doctor",
                refresh_status=write_json(root / "refresh_status.json", refresh("fresh")),
                action_checklist=write_json(root / "action_checklist.json", checklist(item_type="review_snapshot")),
                review_preview=write_json(root / "review_preview.json", preview_data),
                run_manifest=run_path,
            )
        self.assertEqual(result["doctor_status"], "blocked")
        self.assertFalse(result["evidence_check"]["matched_run_manifest"])
        self.assertEqual(result["evidence_check"]["strict_status"], "blocked")
        self.assertIn("review_preview_run_manifest_sha256_mismatch", result["evidence_check"]["blockers"])

    def test_matching_apply_receipt_marks_preview_apply_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = write_json(root / "run_manifest.json", {"schema_version": "run"})
            preview_data = preview(status="ready", accept_count=1, would_update=1)
            preview_data["input"]["run_manifest_sha256"] = sha256(run_path)
            preview_path = write_json(root / "review_preview.json", preview_data)
            receipt = {
                "schema_version": "p2.5-lite-review-apply-receipt",
                "input": {"preview_result_sha256": sha256(preview_path), "decision_manifest_sha256": "decision-hash"},
            }
            result = doctor_tool.build_demo_doctor(
                output_dir=root / "doctor",
                refresh_status=write_json(root / "refresh_status.json", refresh("fresh")),
                action_checklist=write_json(root / "action_checklist.json", checklist(item_type="review_snapshot")),
                review_preview=preview_path,
                review_apply_receipt=write_json(root / "review_apply_receipt.json", receipt),
                run_manifest=run_path,
            )
        self.assertEqual(result["evidence_check"]["status"], "trusted")
        self.assertEqual(result["evidence_check"]["strict_status"], "trusted")
        self.assertTrue(result["evidence_check"]["matched_preview_apply"])

    def test_apply_receipt_accepted_without_roster_index_blocks_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_path = write_json(root / "run_manifest.json", {"schema_version": "run"})
            preview_data = preview(status="ready", accept_count=1, would_update=1)
            preview_data["input"]["run_manifest_sha256"] = sha256(run_path)
            preview_path = write_json(root / "review_preview.json", preview_data)
            receipt = {
                "schema_version": "p2.5-lite-review-apply-receipt",
                "input": {"preview_result_sha256": sha256(preview_path), "decision_manifest_sha256": "decision-hash"},
                "summary": {"did_write_accepted_count": 1, "did_enter_roster_count": 0},
                "warnings": ["accepted snapshot was written but did not enter roster_index."],
            }
            result = doctor_tool.build_demo_doctor(
                output_dir=root / "doctor",
                refresh_status=write_json(root / "refresh_status.json", refresh("fresh")),
                action_checklist=write_json(root / "action_checklist.json", checklist()),
                review_preview=preview_path,
                review_apply_receipt=write_json(root / "review_apply_receipt.json", receipt),
                run_manifest=run_path,
            )
        self.assertEqual(result["doctor_status"], "blocked")
        self.assertEqual(result["primary_next_action"], "repair_evidence_mismatch")
        self.assertFalse(result["try_now_allowed"])
        self.assertFalse(result["evidence_check"]["matched_preview_apply"])
        self.assertEqual(result["evidence_check"]["strict_status"], "blocked")
        self.assertIn("apply_receipt_accepted_not_in_roster_index", result["evidence_check"]["blockers"])
        self.assertIn("ready_try_now_not_actionable_under_current_doctor_status", result["blocking_reasons"])

    def test_pending_review_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(item_type="review_snapshot"),
                review_inbox={"schema_version": "inbox", "pending_count": 2},
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "needs_review")
        self.assertTrue(result["review_required"])
        self.assertFalse(result["try_now_allowed"])

    def test_watch_only_never_upgrades_to_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                final_brief={"schema_version": "brief", "brief_status": "ready", "top_cards": [{"card_type": "watch_only"}]},
                action_checklist=checklist(item_type="watch_only"),
                run_manifest={"schema_version": "run"},
            )
        self.assertNotEqual(result["doctor_status"], "ready_to_try")
        self.assertFalse(result["try_now_allowed"])
        self.assertIn("watch_only_not_try_now", result["warnings"])

    def test_missing_refresh_status_requires_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(root, action_checklist=checklist(), run_manifest={"schema_version": "run"})
        self.assertEqual(result["doctor_status"], "needs_rerun")
        self.assertIn("missing_refresh_status", result["blocking_reasons"])

    def test_unsafe_demo_command_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh", safe_to_rerun=False),
                action_checklist=checklist(),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "ready_to_try")
        self.assertIn("demo_command_not_safe_to_rerun", result["warnings"])
        self.assertFalse(result["action_contract"]["allowed_for_launcher"])

    def test_stale_refresh_with_unsafe_command_blocks_repair_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("stale_after_apply", safe_to_rerun=False),
                action_checklist=checklist(),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "blocked")
        self.assertEqual(result["primary_next_action"], "repair_demo_command")
        self.assertFalse(result["try_now_allowed"])
        self.assertFalse(result["action_contract"]["allowed_for_launcher"])
        self.assertIn("repaired", result["action_contract"]["reason"])

    def test_stale_refresh_with_safe_command_contract_allows_launcher_print(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("stale_after_apply", safe_to_rerun=True),
                action_checklist=checklist(),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["primary_next_action"], "rerun_demo_pipeline")
        self.assertTrue(result["action_contract"]["allowed_for_launcher"])
        self.assertFalse(result["action_contract"]["writes_roster"])
        self.assertFalse(result["action_contract"]["requires_manual_confirmation"])

    def test_ready_try_now_count_counts_all_ready_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                refresh_status=refresh("fresh"),
                action_checklist=checklist(ready_try_now_count=3),
                run_manifest={"schema_version": "run"},
            )
        self.assertEqual(result["doctor_status"], "ready_to_try")
        self.assertEqual(result["summary"]["ready_try_now_count"], 3)


if __name__ == "__main__":
    unittest.main()
