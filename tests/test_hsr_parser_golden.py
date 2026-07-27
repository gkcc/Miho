import json
from pathlib import Path

from hsr_endgame_exporter.parsers import (
    attach_team_signatures,
    make_phase_row,
    parse_builds_character_rows,
    parse_chars_file_character_rows,
    parse_histograph_rows,
    parse_team_rows,
)


def test_minimal_hsr_parser_fixture_freezes_python_oracle():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "hsr_parser_minimal.json").read_text(encoding="utf-8"))
    phase = make_phase_row(snapshot_id="4.3.2", config_entry=fixture["config"], mode="moc", source_path="4.3.2/", has_chars=True, has_comps=False, has_histograph=True, collect_date="2026-06-25")
    assert (phase["mode_cn"], phase["phase_ver"], phase["has_chars"], phase["has_comps"]) == ("混沌回忆", "4.2.1", 1, 0)

    builds = parse_builds_character_rows(snapshot_id="4.3.2", phase_row=phase, builds=fixture["builds"], source_file="builds.json", source_url="fixture://builds")
    assert [(row["character_slug"], row["character_name_en"], row["app_rate"], row["app_rate_e0"]) for row in builds] == [("topaz-and-numby", "Topaz and Numby", 12.5, 0.0)]

    chars = parse_chars_file_character_rows(snapshot_id="4.3.2", phase_row=phase, data=fixture["chars"], source_file="chars.json", source_url="fixture://chars")
    assert [(row["character_slug"], row["app_rate"], row["app_rate_e0"]) for row in chars] == [("march-7th", 7.0, 3.0)]

    histograph = parse_histograph_rows(snapshot_id="4.3.2", phase_rows={"moc": phase}, histograph=fixture["histograph"], source_file="4.3.2/histograph.json")
    assert [(row["mode"], row["character_slug"], row["character_name_en"], row["usage_value"], row["source_file"], row["note"]) for row in histograph] == [("moc", "topaz-and-numby", "Topaz and Numby", 8.25, "4.3.2/histograph.json", "trend auxiliary; not a full character usage table")]

    teams = parse_team_rows(snapshot_id="4.3.2", phase_row=phase, data=fixture["teams"], source_kind="fixture", source_file="teams.json", source_url="fixture://teams", scope_hint="stage_1_combined.json", top_n=2)
    assert len(teams) == 1
    assert teams[0]["raw_index"] == 2
    assert attach_team_signatures(teams[0]) == (
        "4.3.2|2026-06-25|moc|stage_stage_1|stage_1|4.2.1|Example Phase|d>b>a>c",
        "4.3.2|2026-06-25|moc|stage_stage_1|stage_1|4.2.1|Example Phase|a>b>c>d",
    )
