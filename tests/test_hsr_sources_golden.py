import json
from pathlib import Path

import hsr_endgame_exporter.official_names as official_names
from hsr_endgame_exporter.prydwen_scraper import extract_teams_from_html
from hsr_endgame_exporter.prydwen_tier import build_tier_rows, decode_prydwen_payload, extract_changelog, extract_characters, extract_last_updated


def test_fixed_prydwen_fixture_pins_python_oracle(tmp_path, monkeypatch):
    root = Path(__file__).parent / "fixtures"
    html = (root / "hsr_prydwen_minimal.html").read_text(encoding="utf-8")
    decoded = decode_prydwen_payload(html)
    updated = extract_last_updated(decoded)
    rows = build_tier_rows(extract_characters(decoded), updated, "20260106", "fixture-time")
    moc = next(row for row in rows if row["tier_mode"] == "moc")
    assert (updated, moc["character_slug"], moc["tier"], moc["prydwen_role"], moc["special_rating"]) == ("06/Jan/2026", "march-7th", "T0.5", "Support DPS", "E6")
    assert [(row["changelog_date"], row["character_slugs"], row["text"]) for row in extract_changelog(decoded)] == [("2026-01-06", "march-7th", "March 7th moved up .")]
    assert extract_teams_from_html(html)["all"][0]["char_four"] == "aventurine"

    names = json.loads((root / "hsr_prydwen_minimal_names.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(official_names, "_fetch_or_read", lambda _path, lang: names["zh" if lang == "zh-cn" else "en"])
    mapped = official_names.load_hoyowiki_official_names(tmp_path, [])
    assert (mapped["march-7th"]["character_name_en"], mapped["march-7th"]["character_name_cn"]) == ("March 7th", "三月七")
    assert "missing-chinese" not in mapped
