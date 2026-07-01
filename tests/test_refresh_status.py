from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFRESH_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_refresh_status.py"

refresh_spec = importlib.util.spec_from_file_location("build_refresh_status", REFRESH_SCRIPT_PATH)
assert refresh_spec is not None
refresh_tool = importlib.util.module_from_spec(refresh_spec)
assert refresh_spec.loader is not None
sys.modules[refresh_spec.name] = refresh_tool
refresh_spec.loader.exec_module(refresh_tool)


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def receipt(*, created_at: str, entered: int = 1, rejected: int = 0) -> dict:
    return {
        "schema_version": "p2.5-lite-review-apply-receipt",
        "created_at": created_at,
        "summary": {
            "did_enter_roster_count": entered,
            "did_write_accepted_count": entered,
            "did_write_rejected_count": rejected,
            "preview_validated_count": entered,
        },
        "records": [],
    }


def run_manifest(*, created_at: str, roster_sha: str | None) -> dict:
    return {
        "schema_version": "p2.0-lite-run-manifest",
        "created_at": created_at,
        "inputs": {"roster_index": {"path": "roster_index.json", "sha256": roster_sha, "exists": bool(roster_sha)}},
        "artifact_status": {"consistent": True, "missing": [], "stale_or_mismatched": [], "warnings": []},
    }


class RefreshStatusTests(unittest.TestCase):
    def build(
        self,
        root: Path,
        *,
        receipt_data: dict | None,
        manifest_data: dict | None,
        roster_data: dict | None = None,
        demo_command_data: dict | None = None,
        final_brief_data: dict | None = None,
        action_checklist_data: dict | None = None,
    ) -> dict:
        receipt_path = write_json(root / "review_apply_receipt.json", receipt_data) if receipt_data is not None else None
        roster_path = write_json(root / "roster_index.json", roster_data or {"characters": [{"name": "星见雅"}]})
        roster_sha = refresh_tool.sha256_file(roster_path)
        if manifest_data is not None and manifest_data["inputs"]["roster_index"].get("sha256") == "__CURRENT__":
            manifest_data["inputs"]["roster_index"]["sha256"] = roster_sha
        manifest_path = write_json(root / "run_manifest.json", manifest_data) if manifest_data is not None else None
        demo_command_path = write_json(root / "demo_command.json", demo_command_data) if demo_command_data is not None else None
        final_brief_path = write_json(root / "final_brief.json", final_brief_data) if final_brief_data is not None else None
        action_checklist_path = (
            write_json(root / "action_checklist.json", action_checklist_data) if action_checklist_data is not None else None
        )
        return refresh_tool.build_refresh_status(
            output_dir=root / "refresh_status",
            review_apply_receipt=receipt_path,
            run_manifest=manifest_path,
            roster_index=roster_path,
            demo_command=demo_command_path,
            final_brief=final_brief_path,
            action_checklist=action_checklist_path,
        )

    def test_missing_receipt_is_not_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=None,
                manifest_data=run_manifest(created_at="2026-06-29T10:00:00+08:00", roster_sha="__CURRENT__"),
            )

            self.assertEqual(result["refresh_status"], "not_applied")
            self.assertFalse(result["summary"]["needs_demo_refresh"])
            self.assertEqual(result["summary"]["downstream_artifact_status"], "not_checked")
            self.assertTrue(Path(result["output_json"]).exists())

    def test_receipt_newer_than_run_manifest_is_stale_when_roster_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T11:00:00+08:00", entered=1),
                manifest_data=run_manifest(created_at="2026-06-29T10:00:00+08:00", roster_sha="__CURRENT__"),
            )

            self.assertEqual(result["refresh_status"], "stale_after_apply")
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertTrue(result["action_state"]["rerun_required"])
            self.assertFalse(result["action_state"]["try_now_allowed"])
            self.assertIn("review_apply_receipt.created_at", " ".join(result["stale_reasons"]))
            self.assertIn("final_brief", result["affected_artifacts"])

    def test_run_after_receipt_is_fresh_when_roster_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T10:00:00+08:00", entered=1),
                manifest_data=run_manifest(created_at="2026-06-29T11:00:00+08:00", roster_sha="__CURRENT__"),
            )

            self.assertEqual(result["refresh_status"], "fresh")
            self.assertFalse(result["summary"]["needs_demo_refresh"])
            self.assertFalse(result["action_state"]["rerun_required"])
            self.assertTrue(result["action_state"]["try_now_allowed"])

    def test_roster_hash_mismatch_is_stale_even_if_manifest_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T10:00:00+08:00", entered=1),
                manifest_data=run_manifest(created_at="2026-06-29T11:00:00+08:00", roster_sha="different"),
            )

            self.assertEqual(result["refresh_status"], "stale_after_apply")
            self.assertIn("roster_index sha256 differs", " ".join(result["stale_reasons"]))

    def test_reject_only_receipt_does_not_force_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T11:00:00+08:00", entered=0, rejected=1),
                manifest_data=run_manifest(created_at="2026-06-29T10:00:00+08:00", roster_sha="__CURRENT__"),
            )

            self.assertEqual(result["refresh_status"], "fresh")
            self.assertFalse(result["summary"]["needs_demo_refresh"])
            self.assertIn("未改变 accepted roster", " ".join(result["warnings"]))

    def test_refresh_command_uses_demo_command_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T10:00:00+08:00", entered=1),
                manifest_data=run_manifest(created_at="2026-06-29T11:00:00+08:00", roster_sha="__CURRENT__"),
                demo_command_data={
                    "schema_version": "p2.8-lite-demo-command",
                    "command": "python tools/probes/run_demo_pipeline.py --parsed-dir tmp/parsed --latest-only --clean-demo",
                    "argv": ["python", "tools/probes/run_demo_pipeline.py", "--parsed-dir", "tmp/parsed"],
                    "safe_to_rerun": True,
                    "missing_inputs": [],
                    "warnings": [],
                    "source_mode": "parsed_dir",
                },
            )

            self.assertIn("--parsed-dir tmp/parsed", result["refresh_command"])
            self.assertNotIn("replay_manifest", result["refresh_command"])
            self.assertTrue(result["command_state"]["safe_to_rerun"])
            self.assertEqual(result["command_state"]["source_mode"], "parsed_dir")

    def test_missing_demo_command_uses_non_manifest_fallback_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T10:00:00+08:00", entered=1),
                manifest_data=run_manifest(created_at="2026-06-29T11:00:00+08:00", roster_sha="__CURRENT__"),
            )

            self.assertEqual(result["refresh_command"], "python tools/probes/run_demo_pipeline.py --clean-demo")
            self.assertNotIn("replay_manifest", result["refresh_command"])
            self.assertIn("command_not_replayable", result["warnings"])
            self.assertFalse(result["command_state"]["safe_to_rerun"])

    def test_unknown_refresh_status_blocks_try_now_and_requires_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T10:00:00+08:00", entered=1),
                manifest_data=None,
            )

            self.assertEqual(result["refresh_status"], "unknown")
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertTrue(result["action_state"]["rerun_required"])
            self.assertFalse(result["action_state"]["try_now_allowed"])
            self.assertEqual(result["action_state"]["primary_next_action"], "rerun_demo_pipeline")

    def test_downstream_artifact_older_than_apply_marks_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T11:00:00+08:00", entered=1),
                manifest_data=run_manifest(created_at="2026-06-29T12:00:00+08:00", roster_sha="__CURRENT__"),
                final_brief_data={"schema_version": "p2.1-lite-final-brief", "created_at": "2026-06-29T10:30:00+08:00"},
                action_checklist_data={"schema_version": "p2.4-lite-action-checklist", "created_at": "2026-06-29T10:40:00+08:00"},
            )

            self.assertEqual(result["refresh_status"], "stale_after_apply")
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertEqual(result["summary"]["downstream_artifact_status"], "stale")
            self.assertEqual(result["downstream_artifacts"]["final_brief"]["status"], "stale")
            self.assertEqual(result["downstream_artifacts"]["action_checklist"]["status"], "stale")
            self.assertIn("final_brief.created_at is older than review_apply_receipt.created_at", result["stale_reasons"])
            self.assertIn("action_checklist", result["affected_artifacts"])

    def test_action_checklist_older_than_final_brief_is_unknown_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=receipt(created_at="2026-06-29T09:00:00+08:00", entered=0, rejected=1),
                manifest_data=run_manifest(created_at="2026-06-29T12:00:00+08:00", roster_sha="__CURRENT__"),
                final_brief_data={"schema_version": "p2.1-lite-final-brief", "created_at": "2026-06-29T11:00:00+08:00"},
                action_checklist_data={"schema_version": "p2.4-lite-action-checklist", "created_at": "2026-06-29T10:00:00+08:00"},
            )

            self.assertEqual(result["refresh_status"], "unknown")
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertEqual(result["summary"]["downstream_artifact_status"], "stale")
            self.assertIn("action_checklist.created_at is older than final_brief.created_at", result["stale_reasons"])

    def test_downstream_stale_without_receipt_still_requires_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.build(
                root,
                receipt_data=None,
                manifest_data=run_manifest(created_at="2026-06-29T12:00:00+08:00", roster_sha="__CURRENT__"),
                final_brief_data={"schema_version": "p2.1-lite-final-brief", "created_at": "2026-06-29T11:00:00+08:00"},
                action_checklist_data={"schema_version": "p2.4-lite-action-checklist", "created_at": "2026-06-29T10:00:00+08:00"},
            )

            self.assertEqual(result["refresh_status"], "unknown")
            self.assertTrue(result["summary"]["needs_demo_refresh"])
            self.assertFalse(result["action_state"]["try_now_allowed"])
            self.assertIn("action_checklist.created_at is older than final_brief.created_at", result["stale_reasons"])


if __name__ == "__main__":
    unittest.main()
