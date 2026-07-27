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


def test_team_dedup_is_scoped_to_snapshot_collect_date_and_phase_identity():
    base = {
        "snapshot_id": "4.3.1",
        "collect_date": "2026-06-11",
        "mode": "moc",
        "sub_mode": "all",
        "scope": "top",
        "phase_ver": "4.2.1",
        "phase_name": "Duty Action",
        "rank": 1,
        "app_rate": 10,
        "source_kind": "hf_comps",
        "source_file": "4.3.1/moc/comps/top_combined.json",
        "char_1_slug": "a",
        "char_2_slug": "b",
        "char_3_slug": "c",
        "char_4_slug": "d",
    }

    exact_duplicate = {**base, "source_file": "4.3.1/moc/comps/12-1_combined.json"}
    reordered = {
        **base,
        "source_file": "4.3.1/moc/comps/12-2_combined.json",
        "char_1_slug": "b",
        "char_2_slug": "a",
    }
    other_snapshot = {
        **base,
        "snapshot_id": "4.3.2",
        "source_file": "4.3.2/moc/comps/top_combined.json",
    }
    other_collect_date = {
        **base,
        "collect_date": "2026-06-12",
        "source_file": "late/moc/comps/top_combined.json",
    }
    other_phase_name = {
        **base,
        "phase_name": "Different Phase",
        "source_file": "alternate/moc/comps/top_combined.json",
    }
    other_scope = {
        **base,
        "scope": "12-1",
        "source_file": "4.3.1/moc/comps/12-1_combined.json",
    }

    ordered = dedup_ordered_teams(
        [
            base,
            exact_duplicate,
            reordered,
            other_snapshot,
            other_collect_date,
            other_phase_name,
            other_scope,
        ]
    )
    unordered = dedup_unordered_teams(ordered)

    assert len(ordered) == 6
    assert sorted(row["duplicate_count"] for row in ordered) == [1, 1, 1, 1, 1, 2]
    assert len(unordered) == 5
    assert sorted(row["duplicate_count"] for row in unordered) == [1, 1, 1, 1, 3]
    assert len({row["unordered_signature"] for row in unordered}) == 5
    assert {
        tuple(row["unordered_signature"].split("|", 7)[:7]) for row in unordered
    } == {
        ("4.3.1", "2026-06-11", "moc", "all", "top", "4.2.1", "Duty Action"),
        ("4.3.2", "2026-06-11", "moc", "all", "top", "4.2.1", "Duty Action"),
        ("4.3.1", "2026-06-12", "moc", "all", "top", "4.2.1", "Duty Action"),
        ("4.3.1", "2026-06-11", "moc", "all", "top", "4.2.1", "Different Phase"),
        ("4.3.1", "2026-06-11", "moc", "all", "12-1", "4.2.1", "Duty Action"),
    }


def test_team_dedup_cross_source_mirrors_keep_hf_counts_and_traceability():
    base = {
        "snapshot_id": "4.3.2",
        "collect_date": "2026-06-25",
        "mode": "moc",
        "sub_mode": "all",
        "scope": "all",
        "phase_ver": "4.2.1",
        "phase_name": "Duty Action",
        "app_rate": 10,
        "avg_round": 3,
    }

    def team(chars, source_kind, source_file, rank):
        return {
            **base,
            "source_kind": source_kind,
            "source_file": source_file,
            "rank": rank,
            **{
                f"char_{index}_slug": slug
                for index, slug in enumerate(chars, start=1)
            },
        }

    raw = [
        *[
            team("abcd", "hf_comps", f"hf-{index}.json", 9)
            for index in range(1, 3)
        ],
        *[
            team("abcd", "prydwen_page", f"prydwen-{index}.html", 1)
            for index in range(1, 4)
        ],
        team("wxyz", "hf_comps", "hf-single.json", 9),
        team("wxyz", "prydwen_page", "prydwen-single.html", 1),
    ]
    ordered = dedup_ordered_teams(raw)
    unordered = dedup_unordered_teams(ordered)

    for rows in (ordered, unordered):
        assert len(rows) == 2
        by_first = {row["char_1_slug"]: row for row in rows}
        repeated = by_first["a"]
        assert repeated["duplicate_count"] == 2
        assert repeated["source_kind"] == "hf_comps"
        assert repeated["rank"] == 9
        assert repeated["merged_source_kinds"] == "hf_comps;prydwen_page"
        assert repeated["merged_source_files"] == (
            "hf-1.json;hf-2.json;prydwen-1.html;prydwen-2.html;prydwen-3.html"
        )
        single = by_first["w"]
        assert single["duplicate_count"] == 1
        assert single["source_kind"] == "hf_comps"
        assert single["merged_source_kinds"] == "hf_comps;prydwen_page"
        assert single["merged_source_files"] == (
            "hf-single.json;prydwen-single.html"
        )


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
    row = {"snapshot_id": "1.0.1", "mode": "moc", "mode_cn": "混沌回忆", "sub_mode": "all", "sub_mode_cn": "全部", "scope": "top", "phase_ver": "1", "phase_name": "Phase 1", "collect_date": "2026-07-01", "rank": 1, "char_1_slug": "a", "char_2_slug": "b", "char_3_slug": "c", "char_4_slug": "d", "app_rate": 10, "avg_round": 3, "source_kind": "hf_comps", "duplicate_count": 1, "unordered_signature": "1.0.1|2026-07-01|moc|all|top|1|Phase 1|a>b>c>d"}
    view = _build_top_teams_latest({"team_rank_dedup_unordered": [row]})
    assert _columns_from_rows(view) == ["mode_cn", "mode", "sub_mode_cn", "sub_mode", "phase_ver", "rank", "team_cn", "app_rate", "avg_round", "source_kind", "duplicate_count", "unordered_signature"]
    assert view[0]["team_cn"] == "a / b / c / d"


def test_python_top_teams_latest_merges_aggregate_sources_and_excludes_concrete_scopes():
    def team(
        *,
        mode: str = "moc",
        scope: str,
        source_kind: str,
        duplicate_count: int,
        snapshot_id: str = "4.3.10",
        collect_date: str = "2026-07-01",
        rank: int = 1,
        phase_name: str | None = None,
    ) -> dict[str, object]:
        sub_mode = "all_bosses" if mode == "aa" else "all"
        phase_name = phase_name or ("The Humming Laughter" if mode == "aa" else "Duty Action")
        chars = ["a", "b", "c", "d"]
        return {
            "snapshot_id": snapshot_id,
            "collect_date": collect_date,
            "mode": mode,
            "mode_cn": {"moc": "混沌回忆", "aa": "异相仲裁"}[mode],
            "sub_mode": sub_mode,
            "sub_mode_cn": "全部",
            "scope": scope,
            "phase_ver": "4.3.1",
            "phase_name": phase_name,
            "rank": rank,
            "app_rate": 10,
            "avg_round": 3,
            "source_kind": source_kind,
            "source_file": f"{source_kind}/{scope}.json",
            "duplicate_count": duplicate_count,
            **{f"char_{index}_slug": slug for index, slug in enumerate(chars, start=1)},
            "unordered_signature": (
                f"{snapshot_id}|{collect_date}|{mode}|{sub_mode}|{scope}|"
                f"4.3.1|{phase_name}|a>b>c>d"
            ),
        }

    rows = [
        team(
            scope="top",
            source_kind="hf_comps",
            duplicate_count=2,
            rank=1,
            phase_name="Zulu metadata spelling",
        ),
        team(scope="all", source_kind="prydwen_page", duplicate_count=3, rank=9),
        team(scope="12-1", source_kind="hf_comps", duplicate_count=50),
        team(scope="1", source_kind="prydwen_page", duplicate_count=60),
        team(scope="all", source_kind="prydwen_page", duplicate_count=70, snapshot_id="4.3.9"),
        team(mode="aa", scope="all-bosses", source_kind="hf_comps", duplicate_count=4),
        team(mode="aa", scope="all_bosses", source_kind="prydwen_page", duplicate_count=5, rank=8),
        team(mode="aa", scope="1-1", source_kind="hf_comps", duplicate_count=80),
    ]

    view = _build_top_teams_latest({"team_rank_dedup_unordered": rows})
    assert len(view) == 2
    by_mode = {row["mode"]: row for row in view}
    assert by_mode["moc"]["duplicate_count"] == 2
    assert by_mode["moc"]["source_kind"] == "hf_comps;prydwen_page"
    assert by_mode["moc"]["rank"] == 1
    assert str(by_mode["moc"]["unordered_signature"]).startswith("4.3.10|")
    assert "|top|" in str(by_mode["moc"]["unordered_signature"])
    assert by_mode["aa"]["duplicate_count"] == 4
    assert by_mode["aa"]["source_kind"] == "hf_comps;prydwen_page"
    assert by_mode["aa"]["rank"] == 1
    assert str(by_mode["aa"]["unordered_signature"]).startswith("4.3.10|")
    assert "|all_bosses|" in str(by_mode["aa"]["unordered_signature"])


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
