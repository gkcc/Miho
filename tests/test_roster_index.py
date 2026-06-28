from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROSTER_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_roster_index.py"
DECISION_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "apply_review_decisions.py"

roster_spec = importlib.util.spec_from_file_location("build_roster_index", ROSTER_SCRIPT_PATH)
assert roster_spec is not None
roster_tool = importlib.util.module_from_spec(roster_spec)
assert roster_spec.loader is not None
sys.modules[roster_spec.name] = roster_tool
roster_spec.loader.exec_module(roster_tool)

decision_spec = importlib.util.spec_from_file_location("apply_review_decisions", DECISION_SCRIPT_PATH)
assert decision_spec is not None
decision_tool = importlib.util.module_from_spec(decision_spec)
assert decision_spec.loader is not None
sys.modules[decision_spec.name] = decision_tool
decision_spec.loader.exec_module(decision_tool)


def normalized_snapshot(name: str, *, review_status: str = "PASS", invalid_count: int = 0) -> dict:
    blockers = ["存在 invalid_candidate：equipment.name"] if invalid_count else []
    return {
        "source": {"review_status": review_status, "image": f"figs/{name}.jpg"},
        "character": {
            "name": {"value": name},
            "level": {"value": "60"},
            "rank": {"value": "S"},
        },
        "build_snapshot": {"equipment": {"name": {"value": "幻变魔方"}}},
        "quality": {
            "trusted_field_count": 12,
            "field_count": 16,
            "invalid_field_count": invalid_count,
            "blockers": blockers,
        },
    }


def accepted_snapshot(name: str, *, level: str, accepted_at: str, source_name: str) -> dict:
    snapshot = normalized_snapshot(name)
    snapshot["character"]["level"]["value"] = level
    snapshot["review_decision"] = {
        "schema_version": "p1.4-lite-review-decisions",
        "decision": "accept",
        "note": "人工确认通过",
        "decided_at": accepted_at,
        "accepted_at": accepted_at,
        "source_normalized_json": source_name,
    }
    return snapshot


class RosterIndexTests(unittest.TestCase):
    def test_apply_review_decisions_accepts_rejects_and_blocks_unsafe_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir = root / "normalized"
            roster_dir = root / "roster"
            normalized_dir.mkdir()
            accept_path = normalized_dir / "miyabi.json"
            reject_path = normalized_dir / "koleda.json"
            fail_path = normalized_dir / "bad.json"
            invalid_path = normalized_dir / "invalid.json"
            pending_path = normalized_dir / "pending.json"
            accept_path.write_text(json.dumps(normalized_snapshot("星见雅"), ensure_ascii=False), encoding="utf-8")
            reject_path.write_text(json.dumps(normalized_snapshot("珂蕾妲"), ensure_ascii=False), encoding="utf-8")
            fail_path.write_text(json.dumps(normalized_snapshot("坏结果", review_status="FAIL"), ensure_ascii=False), encoding="utf-8")
            invalid_path.write_text(json.dumps(normalized_snapshot("泛词结果", invalid_count=1), ensure_ascii=False), encoding="utf-8")
            pending_path.write_text(json.dumps(normalized_snapshot("待定"), ensure_ascii=False), encoding="utf-8")
            manifest_path = root / "review_decisions.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "decisions": [
                            {"normalized_json": str(accept_path), "decision": "accept", "note": "人工确认通过"},
                            {"normalized_json": str(reject_path), "decision": "reject", "note": "截图不是当前角色"},
                            {"normalized_json": str(fail_path), "decision": "accept", "note": "不能通过"},
                            {"normalized_json": str(invalid_path), "decision": "accept", "note": "不能通过"},
                            {"normalized_json": str(pending_path), "decision": "pending", "note": "稍后看"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = decision_tool.apply_review_decisions(
                normalized_dir=normalized_dir,
                decision_manifest=manifest_path,
                roster_dir=roster_dir,
            )

            self.assertEqual(result["summary"]["accepted_count"], 1)
            self.assertEqual(result["summary"]["rejected_count"], 1)
            self.assertEqual(result["summary"]["blocked_count"], 2)
            self.assertEqual(result["summary"]["pending_count"], 1)
            self.assertEqual(result["summary"]["error_count"], 0)
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertTrue(Path(result["roster_index"]).exists())

            accepted_files = list((roster_dir / "accepted").glob("*.json"))
            rejected_files = list((roster_dir / "rejected").glob("*.json"))
            self.assertEqual(len(accepted_files), 1)
            self.assertEqual(len(rejected_files), 1)
            accepted_snapshot = json.loads(accepted_files[0].read_text(encoding="utf-8"))
            self.assertEqual(accepted_snapshot["review_decision"]["decision"], "accept")
            self.assertEqual(accepted_snapshot["review_decision"]["source_normalized_json"], str(accept_path))

            roster_index = json.loads(Path(result["roster_index"]).read_text(encoding="utf-8"))
            self.assertEqual(roster_index["schema_version"], "p1.4-lite-roster-index")
            self.assertEqual(roster_index["character_count"], 1)
            self.assertEqual(roster_index["characters"][0]["name"], "星见雅")
            self.assertEqual(roster_index["characters"][0]["review_status"], "accepted")
            self.assertTrue(Path(roster_index["output_md"]).exists())

            blocked_errors = " ".join(str(item.get("error")) for item in result["records"] if item.get("status") == "blocked")
            self.assertIn("review_status=FAIL cannot be accepted", blocked_errors)
            self.assertIn("invalid_candidate fields cannot be accepted", blocked_errors)

    def test_build_roster_index_requires_existing_accepted_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(roster_tool.RosterIndexError):
                roster_tool.build_roster_index(accepted_dir=root / "missing", output_dir=root / "roster")

    def test_build_roster_index_keeps_latest_duplicate_character(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accepted_dir = root / "accepted"
            output_dir = root / "roster"
            accepted_dir.mkdir()
            older = accepted_dir / "miyabi_old.json"
            newer = accepted_dir / "miyabi_new.json"
            other = accepted_dir / "nicole.json"
            older.write_text(
                json.dumps(
                    accepted_snapshot(
                        "星见雅",
                        level="50",
                        accepted_at="2026-06-01T00:00:00+08:00",
                        source_name="old_normalized.json",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            newer.write_text(
                json.dumps(
                    accepted_snapshot(
                        "星见雅",
                        level="60",
                        accepted_at="2026-06-02T00:00:00+08:00",
                        source_name="new_normalized.json",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            other.write_text(
                json.dumps(
                    accepted_snapshot(
                        "妮可",
                        level="55",
                        accepted_at="2026-06-01T12:00:00+08:00",
                        source_name="nicole_normalized.json",
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = roster_tool.build_roster_index(accepted_dir=accepted_dir, output_dir=output_dir)

            self.assertEqual(result["accepted_snapshot_count"], 3)
            self.assertEqual(result["character_count"], 2)
            self.assertEqual(result["summary"]["duplicate_character_count"], 1)
            self.assertEqual(result["summary"]["superseded_snapshot_count"], 1)
            miyabi = next(item for item in result["characters"] if item["name"] == "星见雅")
            self.assertEqual(miyabi["level"], "60")
            self.assertEqual(miyabi["snapshot_json"], str(newer))
            self.assertEqual(miyabi["superseded_snapshot_count"], 1)
            self.assertEqual(miyabi["superseded_snapshots"][0]["snapshot_json"], str(older))
            self.assertIn("同一角色存在多份 accepted snapshot", " ".join(result["warnings"]))
            self.assertEqual(result["duplicates"][0]["kept_snapshot_json"], str(newer))

            markdown = Path(result["output_md"]).read_text(encoding="utf-8")
            self.assertIn("duplicate_character_count: 1", markdown)
            self.assertIn("Superseded snapshots", markdown)

    def test_apply_review_decisions_backs_up_previous_roster_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            normalized_dir = root / "normalized"
            roster_dir = root / "roster"
            normalized_dir.mkdir()
            roster_dir.mkdir()
            previous = roster_dir / "roster_index.json"
            previous.write_text(
                json.dumps(
                    {
                        "schema_version": "p1.4-lite-roster-index",
                        "characters": [{"name": "旧角色"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            accept_path = normalized_dir / "miyabi.json"
            accept_path.write_text(json.dumps(normalized_snapshot("星见雅"), ensure_ascii=False), encoding="utf-8")
            manifest_path = root / "review_decisions.json"
            manifest_path.write_text(
                json.dumps(
                    {"decisions": [{"normalized_json": str(accept_path), "decision": "accept", "note": "人工确认通过"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = decision_tool.apply_review_decisions(
                normalized_dir=normalized_dir,
                decision_manifest=manifest_path,
                roster_dir=roster_dir,
            )

            self.assertIsNotNone(result["previous_roster_index"])
            self.assertTrue(Path(result["previous_roster_index"]).exists())
            self.assertTrue((roster_dir / "history" / "roster_index_previous.json").exists())
            previous_backup = json.loads((roster_dir / "history" / "roster_index_previous.json").read_text(encoding="utf-8"))
            self.assertEqual(previous_backup["characters"][0]["name"], "旧角色")
            current = json.loads((roster_dir / "roster_index.json").read_text(encoding="utf-8"))
            self.assertEqual(current["characters"][0]["name"], "星见雅")


if __name__ == "__main__":
    unittest.main()
