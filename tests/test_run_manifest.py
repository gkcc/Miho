from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "build_run_manifest.py"

spec = importlib.util.spec_from_file_location("build_run_manifest", SCRIPT_PATH)
assert spec is not None
run_manifest_tool = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = run_manifest_tool
spec.loader.exec_module(run_manifest_tool)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class RunManifestTests(unittest.TestCase):
    def test_manifest_records_input_paths_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster = root / "roster_index.json"
            targets = root / "targets.json"
            actions = root / "action_cards.json"
            teams = root / "team_cards.json"
            tiers = root / "tier_watchlist.json"
            delta = root / "roster_delta.json"
            write_json(roster, {"characters": [{"name": "星见雅"}]})
            write_json(targets, {"targets": []})
            write_json(actions, {"input": {"roster_index": str(roster), "targets": str(targets), "tier_watchlist": str(tiers)}})
            write_json(teams, {"input": {"action_cards": str(actions), "roster_index": str(roster), "tier_watchlist": str(tiers)}})
            write_json(tiers, {"entries": []})
            write_json(
                delta,
                {
                    "input": {
                        "new_roster_index": str(roster),
                        "action_cards": str(actions),
                        "team_cards": str(teams),
                        "tier_watchlist": str(tiers),
                    }
                },
            )

            result = run_manifest_tool.build_run_manifest(
                output_dir=root,
                roster_index=roster,
                targets=targets,
                team_cards=teams,
                action_cards=actions,
                tier_watchlist=tiers,
                roster_delta=delta,
            )

            self.assertEqual(result["schema_version"], "p2.0-lite-run-manifest")
            self.assertTrue(result["artifact_status"]["consistent"])
            self.assertEqual(result["artifact_status"]["missing"], [])
            self.assertEqual(result["artifact_status"]["stale_or_mismatched"], [])
            self.assertEqual(Path(result["output_json"]).name, "run_manifest.json")
            self.assertTrue(Path(result["output_json"]).exists())
            for name, item in result["inputs"].items():
                self.assertTrue(item["exists"], name)
                self.assertEqual(len(item["sha256"]), 64, name)
                self.assertTrue(Path(item["path"]).exists(), name)

    def test_manifest_warns_when_declared_input_is_from_old_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster = root / "roster_index.json"
            old_roster = root / "old_roster_index.json"
            teams = root / "team_cards.json"
            write_json(roster, {"characters": [{"name": "星见雅"}]})
            write_json(old_roster, {"characters": [{"name": "苍角"}]})
            write_json(teams, {"input": {"roster_index": str(old_roster)}})

            result = run_manifest_tool.build_run_manifest(
                output_dir=root,
                roster_index=roster,
                team_cards=teams,
            )

            status = result["artifact_status"]
            self.assertFalse(status["consistent"])
            self.assertIn("team_cards.roster_index", status["stale_or_mismatched"])
            self.assertIn("targets", status["missing"])
            self.assertIn("可能不是同一批生成", " ".join(status["warnings"]))


if __name__ == "__main__":
    unittest.main()
