import json

from hsr_endgame_exporter.visualizer import _recommender_scope, write_visualizer_app
from miho_core.visualizer_data import expand_visualizer_data


def test_recommender_scope_labels_nodes_and_aggregate_pool_precisely():
    assert _recommender_scope("as", "stage_4_1") == ("4-1", "4-1 / 第1战斗侧", 1)
    assert _recommender_scope("pf", "stage_4_3") == (
        "4-3",
        "4-3 / 第3战斗侧（星芒）",
        3,
    )
    assert _recommender_scope("moc", "stage_12_3") == (
        "12-3",
        "12-3 / 第3战斗侧（星芒）",
        3,
    )
    assert _recommender_scope("aa", "4") == ("2-1", "2-1 / 王棋", 4)
    assert _recommender_scope("as", "top") == ("all", "综合队伍池", 90)


def test_write_visualizer_app_outputs_interactive_files(tmp_path):
    (tmp_path / "hsr_banner_plan.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "id": "future",
                        "status": "next",
                        "title": "后续跃迁",
                        "characters": [
                            {
                                "slug": "future-unit",
                                "name_cn": "未来角色",
                                "name_en": "Future Unit",
                                "banner_role": "限定 5 星新角色",
                                "rarity": "5",
                                "element_cn": "量子",
                                "path_cn": "智识",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    trend_rows = [
        {
            "tier_mode": "moc",
            "tier_mode_cn": "混沌回忆",
            "role_group": "main_dps",
            "role_group_cn": "主C",
            "tier": "T0",
            "rating": 11,
            "character_slug": "test-character",
            "character_name_en": "Test Character",
            "character_name_cn": "测试角色",
            "collect_date": "2026-07-04",
            "phase_ver": "4.3.1",
            "app_rate": 42.0,
            "avg_round": 1.0,
            "icon_url": "https://example.com/icon.webp",
        }
    ]
    tier_rows = [
        {
            "fetched_at": "2026-07-04T00:00:00",
            "tier_updated_at": "30/June/2026",
            "tier_mode": "moc",
            "tier_mode_cn": "混沌回忆",
            "character_slug": "test-character",
            "character_name_en": "Test Character",
            "character_name_cn": "测试角色",
            "role_group": "main_dps",
            "role_group_cn": "主C",
            "tier": "T0",
            "rating": 11,
            "element": "Fire",
            "path": "Erudition",
            "rarity": "5",
            "icon_url": "https://example.com/icon.webp",
        }
    ]
    character_usage_rows = [
        {
            "mode": "aa",
            "mode_cn": "异相仲裁",
            "sub_mode": "all_bosses",
            "sub_mode_cn": "全 Boss / 未拆分",
            "character_slug": "test-character",
            "character_name_en": "Test Character",
            "character_name_cn": "测试角色",
            "collect_date": "2026-07-04",
            "phase_ver": "4.3.1",
            "phase_name": "The Humming Laughter",
            "app_rate": 12.3,
            "avg_round": 4.5,
            "quality_flag": "aa_all_bosses_only",
        }
    ]
    team_rank_rows = [
        {
            "mode": "moc",
            "mode_cn": "混沌回忆",
            "scope": "1",
            "snapshot_id": "moc-421",
            "collect_date": "2026-06-25",
            "phase_ver": "4.2.1",
            "phase_name": "Duty Action",
            "rank": "1",
            "app_rate": "12.3",
            "avg_round": "7.8",
            "source_kind": "hf_comps",
            "source_file": "moc/comps/1.json",
            "char_1_slug": "test-character",
            "char_2_slug": "ally-a",
            "char_3_slug": "ally-b",
            "char_4_slug": "ally-c",
            "char_1_name_cn": "测试角色",
            "char_2_name_cn": "队友甲",
            "char_3_name_cn": "队友乙",
            "char_4_name_cn": "队友丙",
        }
    ]
    (tmp_path / "phase_index.csv").write_text(
        (
            "snapshot_id,collect_date,mode,mode_cn,phase_ver,phase_name,start_date,end_date,source,source_path,"
            "has_chars,has_comps,has_histograph,note\n"
            "moc-421,2026-06-25,moc,混沌回忆,4.2.1,Duty Action,2026-06-09,2026-07-21,hf,4.2.1/config.json,1,1,1,\n"
        ),
        encoding="utf-8",
    )

    write_visualizer_app(
        tmp_path,
        trend_rows=trend_rows,
        tier_rows=tier_rows,
        changelog_rows=[],
        chart_rows=[],
        character_usage_rows=character_usage_rows,
        team_rank_rows=team_rank_rows,
    )

    visualizer_dir = tmp_path / "visualizer"
    assert (visualizer_dir / "index.html").exists()
    assert (visualizer_dir / "styles.css").exists()
    assert (visualizer_dir / "app.js").exists()
    assert (visualizer_dir / "data.v2.json").exists()

    index_text = (visualizer_dir / "index.html").read_text(encoding="utf-8")
    app_text = (visualizer_dir / "app.js").read_text(encoding="utf-8")
    data = json.loads((visualizer_dir / "data.json").read_text(encoding="utf-8"))
    compact_data = expand_visualizer_data(
        json.loads((visualizer_dir / "data.v2.json").read_text(encoding="utf-8"))
    )
    assert compact_data == data

    assert 'id="viewControl"' in index_text
    assert 'id="boxView"' in index_text
    assert "renderHeatmap" in app_text
    assert "hsr_endgame_box_v1" in app_text
    assert "phaseName(row)" in app_text
    assert "phaseStatusLabel" in app_text
    assert "banner={phase:'current'" in app_text
    assert "banner_next" in app_text
    assert "no-store" in app_text
    assert "./data.v2.json" in app_text
    assert "T1及以下提醒" in app_text
    assert "当前模式T1及以下提醒" in app_text
    assert "tierSummaryFor" in app_text
    assert "Prydwen 按模式分档" in app_text
    assert "投入谨慎" in app_text
    assert 'id="buildEditor"' in index_text
    assert 'id="buildEidolonSelect"' in index_text
    assert 'id="buildSignatureSelect"' in index_text
    assert "builds" in app_text
    assert "BUILD_EIDOLONS" in app_text
    assert "buildConfigLabel" in app_text
    assert "练度未录入" in app_text
    assert "ownedBuildScore" in app_text
    assert 'id="recSortSelect"' in index_text
    assert '<option value="balanced" selected>综合推荐</option>' in index_text
    assert '<option value="history">历史表现</option>' in index_text
    assert '<option value="box">Box 即战力</option>' in index_text
    assert "sortMode:'balanced'" in app_text
    assert "normalizeRecSortMode" in app_text
    assert "scoreParts" in app_text
    assert "评分拆分" in app_text
    # A failed remote avatar fetch must degrade to the no-avatar UI instead of
    # leaving a network-dependent URL in the portable visualizer bundle.
    assert data["trendRows"][0]["icon_url"] == ""
    assert data["usageRows"][0]["tier_mode"] == "aa"
    assert data["usageRows"][0]["tier"] == "未分档"
    assert data["usageRows"][0]["phase_name_cn"] == "嗡鸣如笑"
    assert data["phaseInfoRows"][0]["phase_name_cn"] == "值日行动"
    assert "phase_status" in data["phaseInfoRows"][0]
    assert data["teamTemplates"][0]["phase_name_cn"] == "值日行动"
    assert "phase_status" in data["teamTemplates"][0]
    future = {row["character_slug"]: row for row in data["rosterRows"]}["future-unit"]
    assert future["character_name_cn"] == "未来角色"
    assert future["banner_statuses"] == "next"
    assert data["rosterRows"][0]["element_cn"] == "火"
