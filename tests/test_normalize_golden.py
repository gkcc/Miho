import json
from pathlib import Path

from hsr_endgame_exporter.normalize import normalize_character_id, parse_date, parse_percent


CASES = json.loads((Path(__file__).parent / "fixtures" / "normalize_cases.json").read_text(encoding="utf-8"))


def test_slug_golden_cases():
    for case in CASES["slugs"]:
        assert normalize_character_id(case["input"]) == case["expected"]


def test_percent_golden_cases():
    for case in CASES["percents"]:
        assert parse_percent(case["input"]) == case["expected"]


def test_date_golden_cases():
    for case in CASES["dates"]:
        assert parse_date(case["input"]) == case["expected"]
