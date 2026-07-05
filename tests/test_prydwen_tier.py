from hsr_endgame_exporter.prydwen_tier import (
    RATING_TO_TIER,
    build_tier_rows,
    extract_changelog,
)


def test_prydwen_rating_to_tier_mapping():
    assert RATING_TO_TIER[11] == "T0"
    assert RATING_TO_TIER[10] == "T0.5"
    assert RATING_TO_TIER[9] == "T1"
    assert RATING_TO_TIER[8] == "T1.5"
    assert RATING_TO_TIER[7] == "T2"


def test_build_tier_rows_maps_specialist_to_sub_dps():
    rows = build_tier_rows(
        [
            {
                "slug": "anaxa",
                "name": "Anaxa",
                "rarity": "5",
                "element": "Wind",
                "path": "Erudition",
                "defaultRole": "Sub DPS",
                "tierRatings": [
                    {
                        "category": "Specialist",
                        "moc_rating": 8,
                        "moc_special_rating": 8,
                        "pure_rating": 10,
                        "pure_special_rating": 10,
                        "apo_rating": 8,
                        "apo_special_rating": 8,
                        "moc_tags": "Debuff",
                        "pure_tags": "Debuff",
                        "apo_tags": "Debuff",
                    }
                ],
            }
        ],
        "30/June/2026",
        "20260630",
        "2026-07-04T00:00:00",
    )
    moc = [row for row in rows if row["tier_mode"] == "moc"][0]
    assert moc["tier"] == "T1.5"
    assert moc["prydwen_role"] == "Support DPS"
    assert moc["role_group"] == "sub_dps"
    assert moc["role_group_cn"] == "副C"


def test_extract_changelog_dates_and_slugs():
    rows = extract_changelog(
        '<h6>06/Jan/2026</h6><p><span data-slug="archer">Archer</span> T0 ↓ T0.5.</p>'
    )
    assert rows[0]["changelog_date"] == "2026-01-06"
    assert rows[0]["character_slugs"] == "archer"
    assert "Archer" in rows[0]["text"]

