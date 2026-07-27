MODE_CN = {
    "moc": "混沌回忆",
    "pf": "虚构叙事",
    "as": "末日幻影",
    "aa": "异相仲裁",
}

SUB_MODE_CN = {
    "all": "全部",
    "all_bosses": "全 Boss / 未拆分",
    "knights": "骑士关卡",
    "king_piece": "王棋关卡",
}

DEFAULT_MODES = ("moc", "pf", "as", "aa")
DEFAULT_REPO_ID = "LvlUrArti/MocDataProcessed"
DEFAULT_REVISION = "main"

PRYDWEN_PAGE_URLS = {
    "moc": "https://www.prydwen.gg/star-rail/memory-of-chaos",
    "pf": "https://www.prydwen.gg/star-rail/pure-fiction",
    "as": "https://www.prydwen.gg/star-rail/apocalyptic-shadow",
    "aa": "https://www.prydwen.gg/star-rail/anomaly-arbitration",
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
    "has_histograph",
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
    "app_rate_e0",
    "avg_round",
    "std_dev_round",
    "q1_round",
    "cons_avg",
    "sample",
    "sample_app_flat",
    "source_kind",
    "source_file",
    "source_url",
    "quality_flag",
]

HISTOGRAPH_COLUMNS = [
    "snapshot_id",
    "collect_date",
    "mode",
    "mode_cn",
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "usage_value",
    "source_file",
    "note",
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
    "comp_name",
    "char_1_slug",
    "char_2_slug",
    "char_3_slug",
    "char_4_slug",
    "char_1_name_cn",
    "char_2_name_cn",
    "char_3_name_cn",
    "char_4_name_cn",
    "app_rate",
    "avg_round",
    "whale_count",
    "app_flat",
    "uses",
    "source_kind",
    "source_file",
    "source_url",
    "raw_index",
    "raw_json",
]

TEAM_ORDERED_COLUMNS = TEAM_RAW_COLUMNS + [
    "ordered_signature",
    "duplicate_count",
    "merged_source_files",
    "merged_source_kinds",
]

TEAM_UNORDERED_COLUMNS = TEAM_ORDERED_COLUMNS + [
    "unordered_signature",
    "ordered_signature_examples",
]

NAME_MAP_COLUMNS = [
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "source",
    "needs_manual_check",
    "aliases",
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
    "special_rating",
    "tags",
    "marks",
    "is_new",
    "default_role",
    "element",
    "path",
    "rarity",
    "icon_url",
    "source_url",
]

PRYDWEN_TIER_CHANGELOG_COLUMNS = [
    "changelog_date",
    "source_url",
    "character_slugs",
    "text",
]

PRYDWEN_TIER_USAGE_TREND_COLUMNS = [
    "tier_snapshot_id",
    "tier_updated_date",
    "tier_mode",
    "tier_mode_cn",
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "prydwen_role",
    "role_group",
    "role_group_cn",
    "tier",
    "rating",
    "tags",
    "marks",
    "collect_date",
    "phase_ver",
    "phase_name",
    "app_rate",
    "avg_round",
    "quality_flag",
    "icon_url",
]

PRYDWEN_TIER_CHART_COLUMNS = [
    "tier_mode",
    "tier_mode_cn",
    "role_group",
    "role_group_cn",
    "chart_file",
    "series_count",
    "point_count",
]
