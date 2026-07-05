MODE_CN = {
    "sd": "式舆防卫",
    "da": "危局强袭",
}

MODE_URLS = {
    "sd": "https://www.prydwen.gg/zenless/shiyu-defense/",
    "da": "https://www.prydwen.gg/zenless/deadly-assault/",
}

DEFAULT_MODES = ("sd", "da")
DEFAULT_REPO_ID = "LvlUrArti/ShiyuDataProcessed"

ELEMENT_CN = {
    "Physical": "物理",
    "Fire": "火",
    "Ice": "冰",
    "Electric": "电",
    "Ether": "以太",
    "Wind": "风",
    "Auric Ink": "玄墨",
}

STYLE_CN = {
    "Attack": "强攻",
    "Anomaly": "异常",
    "Stun": "击破",
    "Support": "支援",
    "Defence": "防护",
    "Defense": "防护",
    "Rupture": "命破",
}

CATEGORY_TO_ROLE = {
    "CritDPS": ("直伤主C", "crit_dps", "直伤主C"),
    "AnoDPS": ("异常主C", "anomaly_dps", "异常主C"),
    "Support": ("辅助", "support", "辅助"),
}

ROLE_ORDER = {"crit_dps": 0, "anomaly_dps": 1, "support": 2, "unknown": 9}

RATING_TO_TIER = {
    11: "T0",
    10: "T0.5",
    9: "T1",
    8: "T1.5",
    7: "T2",
    6: "T3",
    5: "T4",
    4: "T5",
}

PHASE_COLUMNS = [
    "snapshot_id",
    "collect_date",
    "mode",
    "mode_cn",
    "phase_ver",
    "phase_name",
    "start_date",
    "end_date",
    "source",
    "source_path",
    "has_chars",
    "has_comps",
    "note",
]

CHARACTER_USAGE_COLUMNS = [
    "snapshot_id",
    "collect_date",
    "mode",
    "mode_cn",
    "sub_mode",
    "sub_mode_cn",
    "phase_ver",
    "phase_name",
    "start_date",
    "end_date",
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "role",
    "rarity",
    "app_rate",
    "avg_score",
    "sample",
    "sample_players",
    "cons_avg",
    "char_level",
    "w_engine_level",
    "core_skill",
    "source_kind",
    "source_file",
    "source_url",
    "quality_flag",
]

TEAM_RAW_COLUMNS = [
    "snapshot_id",
    "collect_date",
    "mode",
    "mode_cn",
    "sub_mode",
    "sub_mode_cn",
    "phase_ver",
    "phase_name",
    "scope",
    "rank",
    "char_1_slug",
    "char_2_slug",
    "char_3_slug",
    "bangboo_slug",
    "char_1_name_cn",
    "char_2_name_cn",
    "char_3_name_cn",
    "bangboo_name_cn",
    "app_rate",
    "avg_score",
    "avg_score_m1",
    "source_kind",
    "source_file",
    "source_url",
    "raw_index",
    "raw_json",
]

NAME_MAP_COLUMNS = [
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "source",
    "needs_manual_check",
    "aliases",
    "kind",
    "release_order",
]

PRYDWEN_TIER_COLUMNS = [
    "tier_snapshot_id",
    "fetched_at",
    "tier_updated_at",
    "tier_updated_date",
    "tier_mode",
    "tier_mode_cn",
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "prydwen_category",
    "prydwen_role",
    "role_group",
    "role_group_cn",
    "tier",
    "rating",
    "tags",
    "marks",
    "is_new",
    "element",
    "element_cn",
    "style",
    "style_cn",
    "faction",
    "rarity",
    "icon_url",
    "source_url",
]

CHANGELOG_COLUMNS = ["changelog_date", "source_url", "character_slugs", "text"]
