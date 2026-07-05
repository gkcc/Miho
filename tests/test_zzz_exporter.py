import json

from zzz_endgame_exporter.official_names import official_name_map
from zzz_endgame_exporter.parsers import make_phase_row, parse_team_rows, scope_label
from zzz_endgame_exporter.prydwen import _date_from_prydwen_date, build_tier_rows
from zzz_endgame_exporter.visualizer import write_visualizer_app


def test_zzz_scope_label_matches_processed_files():
    assert scope_label("sd", "5-1_combined.json") == ("5-1", "5 / 1")
    assert scope_label("sd", "top_combined.json") == ("all", "全部")
    assert scope_label("da", "1-3_combined.json") == ("1-3", "1 / 3")


def test_zzz_phase_and_team_rows_include_bangboo():
    phase = make_phase_row(
        "3.0.1",
        "sd",
        {"collect_date": "21/06/2026", "sd": {"ver": "2.8.3", "start": "12/06/2026", "end": "26/06/2026"}},
        source_path="3.0.1/",
    )
    rows = parse_team_rows(
        [
            {
                "char_one": "miyabi",
                "char_two": "nangong-yu",
                "char_three": "ukinami-yuzuha",
                "bangboo": "biggest-fan",
                "app_rate": 26.39,
                "rank": 1,
                "avg_round": 34468,
            }
        ],
        phase,
        scope="5-1_combined.json",
        source_kind="hf_comps",
        source_file="3.0.1/sd/comps/5-1_combined.json",
        source_url="https://example.com",
    )
    assert phase["collect_date"] == "2026-06-21"
    assert rows[0]["sub_mode"] == "5-1"
    assert rows[0]["bangboo_slug"] == "biggest-fan"
    assert rows[0]["avg_score"] == 34468


def test_zzz_prydwen_full_month_date_and_aliases():
    assert _date_from_prydwen_date("17/June/2026") == "2026-06-17"
    rows = build_tier_rows(
        [
            {
                "slug": "billy-starlight",
                "name": "Billy - Starlight",
                "rarity": "S",
                "element": "Physical",
                "style": "Rupture",
                "tierRatings": [{"category": "CritDPS", "rating": 10}],
            }
        ],
        "17/June/2026",
        "20260617",
        "2026-07-05T00:00:00",
    )
    assert rows[0]["tier_updated_date"] == "2026-06-17"
    mapped = official_name_map(
        [
            {
                "character_slug": "starlight-billy",
                "character_name_en": "Starlight - Billy",
                "character_name_cn": "星徽·比利",
                "source": "official",
            }
        ]
    )
    assert mapped["billy-starlight"]["character_name_cn"] == "星徽·比利"


def test_zzz_visualizer_outputs_box_and_keeps_bangboo_out_of_roster(tmp_path):
    usage_rows = [
        {
            "mode": "sd",
            "mode_cn": "式舆防卫",
            "sub_mode": "all",
            "sub_mode_cn": "全部",
            "character_slug": "miyabi",
            "character_name_en": "Miyabi",
            "collect_date": "2026-06-21",
            "phase_ver": "2.8.3",
            "app_rate": 42.0,
            "avg_score": 33000,
        },
        {
            "mode": "sd",
            "mode_cn": "式舆防卫",
            "sub_mode": "bangboo",
            "sub_mode_cn": "邦布",
            "character_slug": "biggest-fan",
            "character_name_en": "Biggest Fan",
            "collect_date": "2026-06-21",
        },
    ]
    tier_rows = [
        {
            "tier_mode": "sd",
            "tier_mode_cn": "式舆防卫",
            "character_slug": "velina",
            "character_name_en": "Velina",
            "character_name_cn": "维琳娜·艾嘉德",
            "role_group": "anomaly_dps",
            "role_group_cn": "异常主C",
            "tier": "T0.5",
            "rating": 10,
            "element": "Wind",
            "element_cn": "风",
            "style": "Anomaly",
            "style_cn": "异常",
            "rarity": "S",
            "icon_url": "https://example.com/velina.webp",
        },
        {
            "tier_mode": "sd",
            "tier_mode_cn": "式舆防卫",
            "character_slug": "miyabi",
            "character_name_en": "Miyabi",
            "character_name_cn": "星见 雅",
            "role_group": "anomaly_dps",
            "role_group_cn": "异常主C",
            "tier": "T0.5",
            "rating": 10,
            "element": "Ice",
            "element_cn": "冰",
            "style": "Anomaly",
            "style_cn": "异常",
            "rarity": "S",
            "icon_url": "https://example.com/miyabi.webp",
        }
    ]
    team_rows = [
        {
            "mode": "sd",
            "mode_cn": "式舆防卫",
            "sub_mode": "5-1",
            "sub_mode_cn": "第5防线 1",
            "collect_date": "2026-06-21",
            "phase_ver": "2.8.3",
            "phase_name": "式舆防卫 2.8.3",
            "rank": 1,
            "app_rate": 26.39,
            "avg_score": 34468,
            "char_1_slug": "miyabi",
            "char_2_slug": "nangong-yu",
            "char_3_slug": "ukinami-yuzuha",
            "bangboo_slug": "biggest-fan",
            "bangboo_name_cn": "阿饭",
        }
    ]
    name_rows = [
        {"character_slug": "velina", "character_name_en": "Velina", "character_name_cn": "维琳娜·艾嘉德", "release_order": "0"},
        {"character_slug": "miyabi", "character_name_en": "Miyabi", "character_name_cn": "星见 雅", "release_order": "10"},
        {"character_slug": "biggest-fan", "character_name_en": "Biggest Fan", "character_name_cn": "阿饭", "kind": "bangboo"},
    ]

    write_visualizer_app(
        tmp_path,
        usage_rows=usage_rows,
        tier_rows=tier_rows,
        team_rows=team_rows,
        name_rows=name_rows,
        changelog_rows=[],
    )

    visualizer_dir = tmp_path / "visualizer"
    assert (visualizer_dir / "index.html").exists()
    assert (visualizer_dir / "app.js").exists()
    app_text = (visualizer_dir / "app.js").read_text(encoding="utf-8")
    data = json.loads((visualizer_dir / "data.json").read_text(encoding="utf-8"))
    assert "zzz_endgame_box_v1" in app_text
    assert "buildEditor" in (visualizer_dir / "index.html").read_text(encoding="utf-8")
    assert "练度未录入" in app_text
    assert [row["character_slug"] for row in data["rosterRows"]] == ["velina", "miyabi"]
    assert data["teamTemplates"][0]["bangboo_name"] == "阿饭"
