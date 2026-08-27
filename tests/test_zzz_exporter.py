import json
from datetime import datetime

from miho_core.banner_plan import effective_phase_status
from miho_core.visualizer_data import expand_visualizer_data
from zzz_endgame_exporter.official_names import official_name_map
from zzz_endgame_exporter.parsers import make_phase_row, parse_team_rows, scope_label
from zzz_endgame_exporter.prydwen import _date_from_prydwen_date, build_tier_rows
from zzz_endgame_exporter.visualizer import (
    _avatar_crop_box,
    _build_phase_info_rows,
    _sanitize_output_urls,
    write_visualizer_app,
)


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
    remielle = official_name_map(
        [
            {
                "character_slug": "remielle",
                "character_name_en": "Remielle Dan",
                "character_name_cn": "蕾米埃尔·丹",
                "source": "official",
            }
        ]
    )
    assert remielle["remiel"]["character_slug"] == "remielle"


def test_zzz_avatar_crop_box_accepts_normalized_coordinates():
    assert _avatar_crop_box([0.25, 0.5, 0.75, 1], 1440, 5112) == (360, 2556, 1080, 5112)
    assert _avatar_crop_box({"left": 12, "top": 20, "right": 90, "bottom": 120}, 100, 140) == (12, 20, 90, 120)
    assert _avatar_crop_box("", 100, 100) is None


def test_banner_phase_status_advances_from_date_range():
    phase = {"status": "next", "date_range": "2026-07-08 12:00 至 2026-07-28 14:59"}

    assert effective_phase_status(phase, now=datetime(2026, 7, 8, 11, 59)) == "next"
    assert effective_phase_status(phase, now=datetime(2026, 7, 9, 9, 30)) == "current"
    assert effective_phase_status(phase, now=datetime(2026, 7, 28, 15, 0)) == "previous"


def test_zzz_visualizer_outputs_box_and_keeps_bangboo_out_of_roster(tmp_path):
    (tmp_path / "zzz_banner_plan.json").write_text('{"phases":[]}', encoding="utf-8")
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
    assert (visualizer_dir / "data.v2.json").exists()
    app_text = (visualizer_dir / "app.js").read_text(encoding="utf-8")
    data = json.loads((visualizer_dir / "data.json").read_text(encoding="utf-8"))
    compact_data = expand_visualizer_data(
        json.loads((visualizer_dir / "data.v2.json").read_text(encoding="utf-8"))
    )
    assert compact_data == data
    assert "zzz_endgame_box_v2" in app_text
    assert "api/zzz/box" in app_text
    assert "./data.v2.json" in app_text
    assert "卡池情报" in (visualizer_dir / "index.html").read_text(encoding="utf-8")
    assert "buildEditor" in (visualizer_dir / "index.html").read_text(encoding="utf-8")
    assert "buildMindscape" in (visualizer_dir / "index.html").read_text(encoding="utf-8")
    assert "buildSignature" in (visualizer_dir / "index.html").read_text(encoding="utf-8")
    assert "BUILD_MINDSCAPES" in app_text
    assert "buildConfigLabel" in app_text
    assert "练度未录入" in app_text
    assert [row["character_slug"] for row in data["rosterRows"]] == ["velina", "miyabi"]
    assert data["teamTemplates"][0]["bangboo_name"] == "阿饭"


def test_zzz_visualizer_uses_latest_snapshot_without_collect_date_and_merges_banner_roster(tmp_path):
    (tmp_path / "zzz_banner_plan.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "id": "current",
                        "status": "current",
                        "date_range": "2026-07-08 12:00 起",
                        "characters": [
                            {
                                "slug": "nom",
                                "name_cn": "诺姆·霍洛维尔",
                                "banner_role": "限定 S 级 UP",
                                "rarity": "S",
                                "element_cn": "火",
                                "style_cn": "击破",
                                "role_group_cn": "辅助",
                            }
                        ],
                    }
                    ,
                    {
                        "id": "satellite",
                        "status": "satellite",
                        "characters": [
                            {
                                "slug": "remielle",
                                "name_cn": "蕾米埃尔·丹",
                                "banner_role": "已公开卫星",
                                "rarity": "S",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "phase_index.csv").write_text(
        (
            "snapshot_id,collect_date,mode,mode_cn,phase_ver,phase_name,start_date,end_date,source,source_path,has_chars,has_comps,note\n"
            "3.0.2,,sd,式舆防卫,3.0.2,式舆防卫 3.0.2,,,hf_processed,3.0.2/,1,1,config missing; dates unavailable\n"
        ),
        encoding="utf-8",
    )
    raw_prydwen = tmp_path / "raw" / "prydwen"
    raw_prydwen.mkdir(parents=True)
    (raw_prydwen / "sd.html").write_text(
        '<select><option value="22" selected="">3.0.2 - 06/July/2026 (19,687 users)</option></select>',
        encoding="utf-8",
    )
    (tmp_path / "zzz_endgame_phase_overrides.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "mode": "sd",
                        "phase_ver": "3.0.2",
                        "collect_date": "2026-07-06",
                        "start_date": "2026-06-26",
                        "end_date": "2026-07-10",
                        "source_label": "manual",
                        "source_url": "https://example.com/sd",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
        }
    ]
    tier_rows = [
        {
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
        }
    ]
    team_rows = [
        {
            "snapshot_id": "3.0.1",
            "mode": "sd",
            "mode_cn": "式舆防卫",
            "sub_mode": "5-1",
            "sub_mode_cn": "第5防线 1",
            "collect_date": "2026-06-21",
            "phase_ver": "2.8.3",
            "phase_name": "式舆防卫 2.8.3",
            "rank": 1,
            "app_rate": 26.39,
            "char_1_slug": "miyabi",
            "char_2_slug": "nangong-yu",
            "char_3_slug": "ukinami-yuzuha",
        },
        {
            "snapshot_id": "3.0.2",
            "mode": "sd",
            "mode_cn": "式舆防卫",
            "sub_mode": "5-1",
            "sub_mode_cn": "第5防线 1",
            "collect_date": "",
            "phase_ver": "3.0.2",
            "phase_name": "式舆防卫 3.0.2",
            "rank": 1,
            "app_rate": 28.0,
            "char_1_slug": "miyabi",
            "char_2_slug": "nom",
            "char_3_slug": "ukinami-yuzuha",
        },
    ]
    name_rows = [
        {"character_slug": "miyabi", "character_name_en": "Miyabi", "character_name_cn": "星见 雅", "release_order": "10"},
        {"character_slug": "ukinami-yuzuha", "character_name_en": "Ukinami Yuzuha", "character_name_cn": "浮波柚叶"},
    ]

    write_visualizer_app(
        tmp_path,
        usage_rows=usage_rows,
        tier_rows=tier_rows,
        team_rows=team_rows,
        name_rows=name_rows,
        changelog_rows=[],
    )

    data = expand_visualizer_data(
        json.loads((tmp_path / "visualizer" / "data.json").read_text(encoding="utf-8"))
    )
    app_text = (tmp_path / "visualizer" / "app.js").read_text(encoding="utf-8")
    roster = {row["character_slug"]: row for row in data["rosterRows"]}

    assert [row["character_slug"] for row in data["rosterRows"][:4]] == [
        "remielle",
        "nom",
        "miyabi",
        "ukinami-yuzuha",
    ]
    assert [row["release_order"] for row in data["rosterRows"][:4]] == [0, 1, 2, 3]
    assert roster["nom"]["character_name_cn"] == "诺姆·霍洛维尔"
    assert roster["nom"]["element_cn"] == "火"
    assert roster["nom"]["banner_statuses"] == "current"
    assert roster["remielle"]["banner_statuses"] == "satellite"
    assert data["bannerRows"][0]["phase_status"] == "current"
    assert "banner={phase:loadBannerPhasePreference()" in app_text
    assert "banner_current" in app_text
    assert "no-store" in app_text
    assert data["phaseInfoRows"][0]["collect_date"] == "2026-07-06"
    assert data["phaseInfoRows"][0]["start_date"] == "2026-06-26"
    assert data["phaseInfoRows"][0]["end_date"] == "2026-07-10"
    assert data["phaseInfoRows"][0]["mechanic_url"] == "https://example.com/sd"
    assert "phase_status" in data["phaseInfoRows"][0]
    assert data["phaseInfoRows"][0]["source_limited"] is True
    assert data["teamTemplates"][0]["phase_ver"] == "3.0.2"
    assert data["teamTemplates"][0]["collect_date"] == "2026-07-06"
    assert "nom" in data["teamTemplates"][0]["chars"]


def test_zzz_phase_override_uses_snapshot_and_available_date_identity(tmp_path):
    (tmp_path / "phase_index.csv").write_text(
        (
            "snapshot_id,collect_date,mode,mode_cn,phase_ver,phase_name,start_date,end_date,note\n"
            "snapshot-old,2026-07-01,sd,式舆防卫,repeat,Old phase,,,historical\n"
            "snapshot-current,2026-07-19,sd,式舆防卫,repeat,Current phase,,,current\n"
            "snapshot-ambiguous,,sd,式舆防卫,repeat,Ambiguous phase,,,missing date\n"
            "snapshot-unlisted,2026-07-19,sd,式舆防卫,repeat,Unlisted phase,,,no override\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "zzz_endgame_phase_overrides.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "mode": "sd",
                        "snapshot_id": "snapshot-old",
                        "phase_ver": "repeat",
                        "collect_date": "2026-07-01",
                        "start_date": "2026-06-26",
                        "end_date": "2026-07-09",
                        "source_label": "old exact",
                    },
                    {
                        "mode": "sd",
                        "snapshot_id": "snapshot-current",
                        "phase_ver": "repeat",
                        "collect_date": "2026-07-18",
                        "start_date": "2026-07-04",
                        "end_date": "2026-07-18",
                        "source_label": "wrong date",
                    },
                    {
                        "mode": "sd",
                        "snapshot_id": "snapshot-current",
                        "phase_ver": "repeat",
                        "collect_date": "2026-07-19",
                        "start_date": "2026-07-10",
                        "end_date": "2026-07-24",
                        "source_label": "current exact",
                    },
                    {
                        "mode": "sd",
                        "snapshot_id": "snapshot-ambiguous",
                        "phase_ver": "repeat",
                        "collect_date": "2026-07-18",
                        "start_date": "2026-07-04",
                        "end_date": "2026-07-18",
                    },
                    {
                        "mode": "sd",
                        "snapshot_id": "snapshot-ambiguous",
                        "phase_ver": "repeat",
                        "collect_date": "2026-07-19",
                        "start_date": "2026-07-10",
                        "end_date": "2026-07-24",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = {
        row["snapshot_id"]: row for row in _build_phase_info_rows(tmp_path)
    }

    assert rows["snapshot-old"]["start_date"] == "2026-06-26"
    assert rows["snapshot-old"]["mechanic_source"] == "old exact"
    assert rows["snapshot-current"]["start_date"] == "2026-07-10"
    assert rows["snapshot-current"]["mechanic_source"] == "current exact"
    assert rows["snapshot-ambiguous"]["start_date"] == ""
    assert rows["snapshot-ambiguous"]["mechanic_source"] == "ShiyuDataProcessed config.json"
    assert rows["snapshot-unlisted"]["start_date"] == ""


def test_zzz_official_phase_metadata_requires_exact_identity_and_preserves_evidence(tmp_path):
    (tmp_path / "phase_index.csv").write_text(
        (
            "snapshot_id,collect_date,mode,mode_cn,phase_ver,phase_name,start_date,end_date,note\n"
            "snapshot-current,2026-07-12,sd,式舆防卫,3.2,式舆防卫 3.2,2026-07-10,2026-07-24,hf identity\n"
            "snapshot-history,2026-06-26,sd,式舆防卫,3.1,式舆防卫 3.1,2026-06-26,2026-07-09,historical\n"
        ),
        encoding="utf-8",
    )
    baseline = _build_phase_info_rows(tmp_path)
    exact_identity = {
        "mode": "sd",
        "snapshot_id": "snapshot-current",
        "phase_ver": "3.2",
        "start_date": "2026-07-10",
        "end_date": "2026-07-24",
    }

    def official_row(identity):
        return {
            "identity": identity,
            "phase_name_cn": "26.7.10 式舆防卫战",
            "mechanic_name": "本期增益",
            "mechanic_text": "风/冰属性伤害提升；命中异常敌人时增伤并无视全抗。",
            "source_label": "绝区零官方 HoYoWiki",
            "source_url": "javascript:alert(1)",
        }

    sidecar = tmp_path / "zzz_official_endgame_phases.json"
    for field, mismatch in {
        "mode": "da",
        "snapshot_id": "snapshot-other",
        "phase_ver": "3.2.1",
        "start_date": "2026-07-11",
        "end_date": "2026-07-25",
    }.items():
        identity = {**exact_identity, field: mismatch}
        sidecar.write_text(
            json.dumps({"phases": [official_row(identity)]}, ensure_ascii=False),
            encoding="utf-8",
        )
        rows = _build_phase_info_rows(tmp_path)
        assert rows[0] == baseline[0], f"mismatch in {field} must not bind"

    invalid = official_row(exact_identity)
    invalid["phase_name_cn"] = 123
    sidecar.write_text(
        json.dumps({"phases": [invalid]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert _build_phase_info_rows(tmp_path)[0] == baseline[0]

    sidecar.write_text(
        json.dumps({"phases": [official_row(exact_identity)]}, ensure_ascii=False),
        encoding="utf-8",
    )
    enriched = _build_phase_info_rows(tmp_path)
    for field in (
        "snapshot_id",
        "collect_date",
        "mode",
        "phase_ver",
        "phase_name",
        "start_date",
        "end_date",
        "phase_status",
        "source_limited",
        "source_note",
    ):
        assert enriched[0][field] == baseline[0][field]
    assert enriched[0]["phase_name_cn"] == "26.7.10 式舆防卫战"
    assert enriched[0]["mechanic_name"] == "本期增益"
    assert enriched[0]["mechanic_text"] == "风/冰属性伤害提升；命中异常敌人时增伤并无视全抗。"
    assert enriched[0]["mechanic_source"] == "绝区零官方 HoYoWiki"
    assert enriched[0]["mechanic_url"] == "javascript:alert(1)"
    assert enriched[1] == baseline[1]

    sanitized = _sanitize_output_urls({"phaseInfoRows": enriched})
    assert sanitized["phaseInfoRows"][0]["mechanic_url"] == ""
