import csv
import hashlib
import json
from pathlib import Path

from hsr_endgame_exporter.constants import (
    CHARACTER_USAGE_COLUMNS, NAME_MAP_COLUMNS, PHASE_COLUMNS,
    PRYDWEN_TIER_CHANGELOG_COLUMNS, PRYDWEN_TIER_CHART_COLUMNS,
    PRYDWEN_TIER_COLUMNS, PRYDWEN_TIER_USAGE_TREND_COLUMNS,
    TEAM_ORDERED_COLUMNS, TEAM_RAW_COLUMNS, TEAM_UNORDERED_COLUMNS,
)
from hsr_endgame_exporter.exporters import dedup_ordered_teams, dedup_unordered_teams, latest_character_usage, write_csv
from hsr_endgame_exporter.parsers import make_phase_row, parse_builds_character_rows, parse_team_rows


def test_minimal_export_expected_contract(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    source = json.loads((fixtures / "hsr_parser_minimal.json").read_text(encoding="utf-8"))
    phase = make_phase_row(snapshot_id="4.3.2", config_entry=source["config"], mode="moc", source_path="4.3.2/", has_chars=True, has_comps=False, has_histograph=True, collect_date="2026-06-25")
    characters = parse_builds_character_rows(snapshot_id="4.3.2", phase_row=phase, builds=source["builds"], source_file="fixture/builds.json", source_url="fixture://builds")
    teams = parse_team_rows(snapshot_id="4.3.2", phase_row=phase, data=source["teams"], source_kind="fixture", source_file="teams.json", source_url="fixture://teams", scope_hint="stage_1_combined.json", top_n=2)
    tiers = [{"tier_snapshot_id": "2026-06-25", "tier_mode": "moc", "character_slug": "topaz-and-numby", "character_name_en": "Topaz and Numby", "tier": "T1", "rating": "1", "source_url": "fixture://tier"}]
    tables = [("phase_index.csv", [phase], PHASE_COLUMNS), ("character_usage_long.csv", characters, CHARACTER_USAGE_COLUMNS), ("team_rank_raw.csv", teams, TEAM_RAW_COLUMNS), ("prydwen_tier_current.csv", tiers, PRYDWEN_TIER_COLUMNS)]
    expected = fixtures / "hsr_export_expected"
    for name, rows, columns in tables:
        write_csv(tmp_path / name, rows, columns)
        with (tmp_path / name).open(encoding="utf-8-sig", newline="") as actual_file, (expected / name).open(encoding="utf-8", newline="") as expected_file:
            assert list(csv.reader(actual_file)) == list(csv.reader(expected_file))
    manifest = []
    for name, _, _ in tables:
        text = (expected / name).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        manifest.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    manifest.sort(key=lambda row: row["path"])
    assert json.loads((expected / "artifact_manifest.json").read_text(encoding="utf-8")) == manifest


def test_derived_table_headers_and_rows_are_frozen(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    source = json.loads((fixtures / "hsr_parser_minimal.json").read_text(encoding="utf-8"))
    phase = make_phase_row(snapshot_id="4.3.2", config_entry=source["config"], mode="moc", source_path="4.3.2/", has_chars=True, has_comps=False, has_histograph=True, collect_date="2026-06-25")
    characters = parse_builds_character_rows(snapshot_id="4.3.2", phase_row=phase, builds=source["builds"], source_file="fixture/builds.json", source_url="fixture://builds")
    teams = parse_team_rows(snapshot_id="4.3.2", phase_row=phase, data=source["teams"], source_kind="fixture", source_file="teams.json", source_url="fixture://teams", scope_hint="stage_1_combined.json", top_n=2)
    ordered = dedup_ordered_teams(teams)
    derived = [
        ("character_usage_phase_latest.csv", latest_character_usage(characters), CHARACTER_USAGE_COLUMNS),
        ("team_rank_dedup_ordered.csv", ordered, TEAM_ORDERED_COLUMNS),
        ("team_rank_dedup_unordered.csv", dedup_unordered_teams(ordered), TEAM_UNORDERED_COLUMNS),
        ("name_map.csv", [], NAME_MAP_COLUMNS), ("name_map_unresolved.csv", [], NAME_MAP_COLUMNS),
        ("prydwen_tier_history.csv", [], PRYDWEN_TIER_COLUMNS),
        ("prydwen_tier_changelog.csv", [], PRYDWEN_TIER_CHANGELOG_COLUMNS),
        ("prydwen_tier_changelog_history.csv", [], PRYDWEN_TIER_CHANGELOG_COLUMNS),
        ("prydwen_tier_usage_trend.csv", [], PRYDWEN_TIER_USAGE_TREND_COLUMNS),
        ("prydwen_tier_charts.csv", [], PRYDWEN_TIER_CHART_COLUMNS),
        ("overview.csv", [], ["section", "metric", "value"]),
    ]
    for name, rows, columns in derived:
        write_csv(tmp_path / name, rows, columns)
        raw = (tmp_path / name).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"\r\n")
        with (tmp_path / name).open(encoding="utf-8-sig", newline="") as handle:
            parsed = list(csv.reader(handle))
        assert parsed[0] == columns
    assert len(ordered) == 1 and len(dedup_unordered_teams(ordered)) == 1
