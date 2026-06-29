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


def refresh(status: str = "fresh", *, safe_to_rerun: bool = True) -> dict:
    return {
        "schema_version": "p2.7-lite-refresh-status",
        "refresh_status": status,
        "refresh_command": "python tools/probes/run_demo_pipeline.py --manifest data/probes/demo_manifest.json",
        "command_state": {"safe_to_rerun": safe_to_rerun},
    }


def checklist(*, item_type: str = "try_now", item_status: str = "ready") -> dict:
    return {
        "schema_version": "p2.2-lite-action-checklist",
        "checklist_status": "ready",
        "preview_command": "python tools/probes/preview_review_decisions.py --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json",
        "safe_apply_command": "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json --roster-dir data/probes/roster --preview-result data/probes/demo/review_preview/review_decision_preview.json --require-preview-ready",
        "items": [{"item_type": item_type, "status": item_status, "title": "unit"}],
    }


def preview(*, status: str = "missing", accept_count: int = 0, would_update: int = 0) -> dict:
    return {
        "schema_version": "p2.3-lite-review-decision-preview",
        "preview_status": status,
        "summary": {"accept_count": accept_count, "would_update_roster_count": would_update},
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


if __name__ == "__main__":
    unittest.main()
