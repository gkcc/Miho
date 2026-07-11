import json
from pathlib import Path

from zzz_endgame_exporter.prydwen import (
    _date_from_prydwen_date,
    _snapshot_id,
    build_tier_rows,
    decode_payload,
    extract_changelog,
    extract_characters,
    extract_last_updated,
    extract_phase_updates_from_html,
    extract_teams_from_html,
)


def test_prydwen_document_freezes_python_oracle():
    html = json.loads((Path(__file__).parent / "fixtures" / "zzz_supplemental" / "prydwen_document.json").read_text(encoding="utf-8"))["html"]
    decoded = decode_payload(html)
    updated = extract_last_updated(decoded)
    assert updated == "07/July/2026" and _snapshot_id(updated) == "20260707"
    teams = extract_teams_from_html(html)
    assert list(teams) == ["node-a"] and len(teams["node-a"]) == 2
    nested = extract_teams_from_html(
        '{"teams":{"outer":[{"char_one":"a","char_two":"b","char_three":"c"}],'
        '"metadata":{"teams":{"inner":[{"char_one":"d","char_two":"e","char_three":"f"}]}}}}'
    )
    assert list(nested) == ["outer"]
    ordered = extract_teams_from_html(
        '{"teams":{"z-scope":[{"char_one":"a","char_two":"b","char_three":"c"}],'
        '"a-scope":[{"char_one":"d","char_two":"e","char_three":"f"}]}}'
    )
    assert list(ordered) == ["z-scope", "a-scope"]
    tiers = build_tier_rows(extract_characters(decoded), updated, _snapshot_id(updated), "2026-07-12T00:00:00")
    assert len(tiers) == 4
    assert [(row["tier_mode"], row["tier"], row["role_group"]) for row in tiers] == [("sd", "T0", "crit_dps"), ("da", "T0", "crit_dps"), ("sd", "T1", "support"), ("da", "T1", "support")]
    assert extract_changelog(decoded)[0]["character_slugs"] == "alice-thymefield"
    assert extract_phase_updates_from_html(html)["3.1"] == {"collect_date": "2026-07-07", "users": "1234"}


def test_prydwen_edge_values_pin_python_fallback_and_cleaning() -> None:
    rows = build_tier_rows(
        [
            {
                "slug": "sample-agent",
                "name": "Sample Agent",
                "element": "Auric Ink",
                "style": "Rupture",
                "isNew": False,
                "tierRatings": [
                    {"category": "AnoDPS", "rating": 10, "tags": ["burst", "O'Brien", True, None]},
                    {"category": "Support", "rating": "10"},
                ],
            }
        ],
        "07/July/2026",
        "20260707",
        "fixture",
    )
    assert (rows[0]["element_cn"], rows[0]["style_cn"]) == ("玄墨", "命破")
    assert (rows[0]["tier"], rows[0]["rating"], rows[0]["is_new"]) == ("T0.5", 10, "")
    assert str(rows[0]["tags"]) == "['burst', \"O'Brien\", True, None]"
    assert (rows[2]["tier"], rows[2]["rating"]) == ("", "10")
    assert _date_from_prydwen_date("17/06/2026") == "2026-06-17"
    assert _date_from_prydwen_date("future") == "future"
    assert extract_phase_updates_from_html("<option>3.6 - 09/Foo/2026</option>") == {
        "3.6": {"collect_date": "09/Foo/2026", "users": ""}
    }

    html = (
        "<h6>Notes</h6><p>ignored before first date</p>"
        "<h6>07/July/2026</h6><script>bad script</script><style>bad style</style>"
        '<p data-slug="alice">A &amp;amp; B &#x27;x&#x27;</p>'
        "<h6>Other</h6><p>kept until next dated heading</p>"
        "<h6>08/July/2026</h6><p>second</p>"
    )
    changelog = extract_changelog(decode_payload(html))
    assert changelog[0]["text"] == "A & B 'x' Other kept until next dated heading"
