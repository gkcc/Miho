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
from hsr_endgame_exporter.exporters import _build_latest_usage_cn, _build_top_teams_latest, _columns_from_rows, dedup_ordered_teams, dedup_unordered_teams, latest_character_usage, write_csv
from hsr_endgame_exporter.name_map import NameMapBuilder, collect_names
from hsr_endgame_exporter.parsers import make_phase_row, parse_builds_character_rows, parse_team_rows


def test_minimal_export_expected_contract(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    source = json.loads((fixtures / "hsr_parser_minimal.json").read_text(encoding="utf-8"))
    phase = make_phase_row(snapshot_id="4.3.2", config_entry=source["config"], mode="moc", source_path="4.3.2/", has_chars=True, has_comps=False, has_histograph=True, collect_date="2026-06-25")
    characters = parse_builds_character_rows(snapshot_id="4.3.2", phase_row=phase, builds=source["builds"], source_file="fixture/builds.json", source_url="fixture://builds")
    teams = parse_team_rows(snapshot_id="4.3.2", phase_row=phase, data=source["teams"], source_kind="hf_comps", source_file="teams.json", source_url="fixture://teams", scope_hint="stage_1_combined.json", top_n=2)
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


def test_python_oracle_aggregates_two_slices_without_overwrite():
    rows = [
        {"mode": "moc", "sub_mode": "all", "phase_ver": "4.2.1", "character_slug": "topaz", "collect_date": "2026-06-25"},
        {"mode": "pf", "sub_mode": "all", "phase_ver": "4.2.2", "character_slug": "march-7th", "collect_date": "2026-07-01"},
    ]
    latest = latest_character_usage(rows)
    assert {(row["mode"], row["character_slug"]) for row in latest} == {("moc", "topaz"), ("pf", "march-7th")}


def test_python_dynamic_view_column_order_for_multiple_modes():
    rows = [
        {"mode": "moc", "sub_mode": "all", "phase_ver": "1", "character_slug": "a", "character_name_en": "A", "collect_date": "2026-01-01", "app_rate": 10},
        {"mode": "pf", "sub_mode": "all", "phase_ver": "2", "character_slug": "b", "character_name_en": "B", "collect_date": "2026-01-02", "app_rate": 20},
    ]
    view = _build_latest_usage_cn({"character_usage_long": rows})
    columns = _columns_from_rows(view)
    assert columns[:4] == ["character_name_cn", "character_name_en", "character_slug", "role"]
    assert columns == ["character_name_cn", "character_name_en", "character_slug", "role", "pf_app_rate", "pf_avg_round", "max_app_rate", "moc_app_rate", "moc_avg_round"]
    assert {"moc_app_rate", "moc_avg_round", "pf_app_rate", "pf_avg_round"} <= set(columns)
    assert _columns_from_rows(_build_top_teams_latest({"team_rank_dedup_unordered": []})) == []


def test_python_latest_view_uses_newest_collect_date_per_mode():
    rows = [
        {"mode": "moc", "sub_mode": "all", "character_slug": "a", "character_name_en": "A", "collect_date": "2026-06-01", "app_rate": 10},
        {"mode": "moc", "sub_mode": "all", "character_slug": "a", "character_name_en": "A", "collect_date": "2026-07-01", "app_rate": 99},
    ]
    view = _build_latest_usage_cn({"character_usage_long": rows})
    assert len(view) == 1 and view[0]["moc_app_rate"] == 99


def test_python_top_teams_latest_nonempty_contract():
    row = {"mode": "moc", "mode_cn": "混沌回忆", "sub_mode": "all", "sub_mode_cn": "全部", "phase_ver": "1", "collect_date": "2026-07-01", "rank": 1, "char_1_slug": "a", "char_2_slug": "b", "char_3_slug": "c", "char_4_slug": "d", "app_rate": 10, "avg_round": 3, "source_kind": "hf_comps", "duplicate_count": 1, "unordered_signature": "moc|all|1|a>b>c>d"}
    view = _build_top_teams_latest({"team_rank_dedup_unordered": [row]})
    assert _columns_from_rows(view) == ["mode_cn", "mode", "sub_mode_cn", "sub_mode", "phase_ver", "rank", "team_cn", "app_rate", "avg_round", "source_kind", "duplicate_count", "unordered_signature"]
    assert view[0]["team_cn"] == "a / b / c / d"


def test_python_name_map_includes_team_only_characters():
    builder = NameMapBuilder()
    collect_names(
        builder,
        [
            {
                "char_1_slug": "a",
                "char_2_slug": "b",
                "char_3_slug": "c",
                "char_4_slug": "d",
                "source_kind": "hf_comps",
            }
        ],
    )
    rows, unresolved = builder.build_rows()
    assert [row["character_slug"] for row in rows] == ["a", "b", "c", "d"]
    assert len(unresolved) == 4
