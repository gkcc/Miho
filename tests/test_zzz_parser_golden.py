import json
from pathlib import Path

from zzz_endgame_exporter.parsers import make_phase_row, parse_bangboo_rows, parse_builds_character_rows, parse_team_rows


def test_minimal_fixture_pins_python_oracle():
    data = json.loads((Path(__file__).parent / "fixtures" / "zzz_parser_minimal.json").read_text(encoding="utf-8"))
    source = data["phase"]
    phase = make_phase_row(
        source["snapshot_id"], source["mode"],
        {"collect_date": source["collect_date"], source["mode"]: {"ver": source["ver"], "name": source["name"], "start": source["start"], "end": source["end"]}},
        source_path=source["source_path"],
    )
    usage = parse_builds_character_rows([data["usage"]], phase, source_file="fixture.json", source_url="fixture://local")
    teams = parse_team_rows(data["teams"], phase, scope=data["scope"], source_kind="fixture", source_file="fixture.json", source_url="fixture://local")
    bangboo = parse_bangboo_rows(data["bangboo"], phase, source_file="3.0.1/sd/chars/bangboo_all.json", source_url="fixture://bangboo")

    assert (phase["collect_date"], phase["phase_ver"], phase["phase_name"]) == ("2026-06-21", "2.8.3", "式舆防卫 2.8.3")
    assert [(row["sub_mode"], row["app_rate"], row["avg_score"]) for row in usage] == [("all", 42.0, 33000.0), ("5-1", 26.39, 34468.0)]
    assert [(row["rank"], row["scope"], row["bangboo_slug"]) for row in teams] == [(1, "5-1_combined.json", ""), (2.0, "5-1_combined.json", "biggest-fan")]
    assert [(row["sub_mode"], row["character_slug"], row["role"], row["rarity"], row["app_rate"], row["avg_score"], row["source_kind"], row["source_file"]) for row in bangboo] == [("bangboo", "safety", "bangboo", "S", 7.5, 123, "hf_bangboo", "3.0.1/sd/chars/bangboo_all.json")]
