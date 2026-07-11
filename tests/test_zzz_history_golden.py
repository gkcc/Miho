from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from zzz_endgame_exporter.constants import PRYDWEN_TIER_COLUMNS
from zzz_endgame_exporter.exporters import build_tier_usage_trend
from zzz_endgame_exporter.prydwen import merge_changelog_history, merge_tier_history


FIXTURE = Path(__file__).parent / "fixtures" / "zzz_history_minimal.json"


def test_history_fixture_pins_python_merge_and_trend_order(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    existing_path = tmp_path / "prydwen_tier_history.csv"
    with existing_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRYDWEN_TIER_COLUMNS)
        writer.writeheader()
        writer.writerows(data["existing_tier"])

    tiers = merge_tier_history(existing_path, data["current_tier"])
    assert len(tiers) == 2
    assert tiers[0]["tier"] == "T0.5"
    assert tiers[0]["character_name_cn"] == "爱丽丝"
    assert tiers[1]["prydwen_category"] == "Support"

    trends = build_tier_usage_trend(tiers, data["usage"])
    assert [row["collect_date"] for row in trends] == [
        "2026-01-01",
        "2026-02-01",
        "2026-01-01",
        "2026-02-01",
    ]
    assert trends[2]["prydwen_category"] == "Support"
    assert trends[0]["fetched_at"] == "2026-07-12T00:00:00"

    changelog = merge_changelog_history(tmp_path / "missing.csv", data["changelog"])
    assert len(changelog) == 1
    assert (
        hashlib.sha1(changelog[0]["text"].encode()).hexdigest()
        == "c516faa085d41bb9e6c8b0afdd8979341d56db2a"
    )
