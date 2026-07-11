use serde::{Deserialize, Serialize};

use crate::{
    hsr::{CharacterRow, PhaseRow, TeamRow},
    output::{csv_float, ArtifactBundle},
    Result,
};

const PHASE_HEADERS: &[&str] = &[
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
];
const CHARACTER_HEADERS: &[&str] = &[
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
];
const TEAM_HEADERS: &[&str] = &[
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
];
const TIER_HEADERS: &[&str] = &[
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
];
const NAME_HEADERS: &[&str] = &[
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "source",
    "needs_manual_check",
    "aliases",
];
const CHANGELOG_HEADERS: &[&str] = &["changelog_date", "source_url", "character_slugs", "text"];
const TREND_HEADERS: &[&str] = &[
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
];
const CHART_HEADERS: &[&str] = &[
    "tier_mode",
    "tier_mode_cn",
    "role_group",
    "role_group_cn",
    "chart_file",
    "series_count",
    "point_count",
];
const OVERVIEW_HEADERS: &[&str] = &["section", "metric", "value"];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TierRow {
    pub tier_snapshot_id: String,
    pub tier_mode: String,
    pub character_slug: String,
    pub character_name_en: String,
    pub tier: String,
    pub rating: String,
    pub source_url: String,
}

pub fn build_minimal_export(
    phase: &PhaseRow,
    characters: &[CharacterRow],
    teams: &[TeamRow],
    tiers: &[TierRow],
) -> Result<ArtifactBundle> {
    let mut bundle = ArtifactBundle::default();
    bundle.add_csv(
        "phase_index.csv",
        PHASE_HEADERS,
        [[
            phase.snapshot_id.clone(),
            phase.collect_date.clone(),
            phase.mode.clone(),
            phase.mode_cn.clone(),
            phase.phase_ver.clone(),
            phase.phase_name.clone(),
            phase.start_date.clone(),
            phase.end_date.clone(),
            phase.source.clone(),
            phase.source_path.clone(),
            phase.has_chars.to_string(),
            phase.has_comps.to_string(),
            phase.has_histograph.to_string(),
            phase.note.clone(),
        ]],
    )?;
    bundle.add_csv(
        "character_usage_long.csv",
        CHARACTER_HEADERS,
        characters.iter().map(|row| {
            vec![
                phase.snapshot_id.clone(),
                phase.collect_date.clone(),
                phase.mode.clone(),
                phase.mode_cn.clone(),
                "all".into(),
                "全部".into(),
                phase.phase_ver.clone(),
                phase.phase_name.clone(),
                phase.start_date.clone(),
                phase.end_date.clone(),
                row.character_slug.clone(),
                row.character_name_en.clone(),
                String::new(),
                String::new(),
                String::new(),
                csv_float(Some(row.app_rate)),
                csv_float(row.app_rate_e0),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                row.source_kind.clone(),
                "fixture/builds.json".into(),
                "fixture://builds".into(),
                row.quality_flag.clone(),
            ]
        }),
    )?;
    bundle.add_csv(
        "team_rank_raw.csv",
        TEAM_HEADERS,
        teams.iter().map(|row| {
            vec![
                phase.snapshot_id.clone(),
                phase.collect_date.clone(),
                row.mode.clone(),
                phase.mode_cn.clone(),
                row.sub_mode.clone(),
                "stage-1".into(),
                row.phase_ver.clone(),
                phase.phase_name.clone(),
                row.scope.clone(),
                String::new(),
                String::new(),
                row.chars[0].clone(),
                row.chars[1].clone(),
                row.chars[2].clone(),
                row.chars[3].clone(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                "fixture".into(),
                "teams.json".into(),
                "fixture://teams".into(),
                row.raw_index.to_string(),
                row.raw_json.clone(),
            ]
        }),
    )?;
    bundle.add_csv(
        "prydwen_tier_current.csv",
        TIER_HEADERS,
        tiers.iter().map(|row| {
            vec![
                row.tier_snapshot_id.clone(),
                String::new(),
                String::new(),
                String::new(),
                row.tier_mode.clone(),
                String::new(),
                row.character_slug.clone(),
                row.character_name_en.clone(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                row.tier.clone(),
                row.rating.clone(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                row.source_url.clone(),
            ]
        }),
    )?;
    bundle.add_csv(
        "character_usage_phase_latest.csv",
        CHARACTER_HEADERS,
        characters.iter().map(|row| character_values(phase, row)),
    )?;

    let ordered_headers = TEAM_HEADERS
        .iter()
        .copied()
        .chain([
            "ordered_signature",
            "duplicate_count",
            "merged_source_files",
        ])
        .collect::<Vec<_>>();
    bundle.add_csv(
        "team_rank_dedup_ordered.csv",
        &ordered_headers,
        teams.iter().map(|row| {
            let (ordered, _) = row.signatures();
            team_values(phase, row)
                .into_iter()
                .chain([ordered, "1".into(), "teams.json".into()])
                .collect::<Vec<_>>()
        }),
    )?;
    let unordered_headers = ordered_headers
        .iter()
        .copied()
        .chain(["unordered_signature", "ordered_signature_examples"])
        .collect::<Vec<_>>();
    bundle.add_csv(
        "team_rank_dedup_unordered.csv",
        &unordered_headers,
        teams.iter().map(|row| {
            let (ordered, unordered) = row.signatures();
            team_values(phase, row)
                .into_iter()
                .chain([
                    ordered.clone(),
                    "1".into(),
                    "teams.json".into(),
                    unordered,
                    ordered,
                ])
                .collect::<Vec<_>>()
        }),
    )?;
    bundle.add_csv(
        "name_map.csv",
        NAME_HEADERS,
        characters.iter().map(|row| {
            vec![
                row.character_slug.clone(),
                row.character_name_en.clone(),
                String::new(),
                "derived".into(),
                "1".into(),
                String::new(),
            ]
        }),
    )?;
    bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
        "name_map_unresolved.csv",
        NAME_HEADERS,
        vec![],
    )?;
    bundle.add_csv(
        "prydwen_tier_history.csv",
        TIER_HEADERS,
        tiers.iter().map(tier_values),
    )?;
    bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
        "prydwen_tier_changelog.csv",
        CHANGELOG_HEADERS,
        vec![],
    )?;
    bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
        "prydwen_tier_changelog_history.csv",
        CHANGELOG_HEADERS,
        vec![],
    )?;
    bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
        "prydwen_tier_usage_trend.csv",
        TREND_HEADERS,
        vec![],
    )?;
    bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
        "prydwen_tier_charts.csv",
        CHART_HEADERS,
        vec![],
    )?;
    bundle.add_csv(
        "overview.csv",
        OVERVIEW_HEADERS,
        [
            ["rows".to_owned(), "phase_index".to_owned(), "1".to_owned()],
            [
                "rows".to_owned(),
                "character_usage_long".to_owned(),
                characters.len().to_string(),
            ],
            [
                "rows".to_owned(),
                "team_rank_raw".to_owned(),
                teams.len().to_string(),
            ],
            [
                "rows".to_owned(),
                "prydwen_tier_current".to_owned(),
                tiers.len().to_string(),
            ],
        ],
    )?;
    bundle.add_text("export_report.md", format!("# HSR Endgame Export Report\n\n- from_date / to_date: {0} / {0}\n- 成功读取的 snapshot 数: 1\n\n## 表行数\n\n- 角色表行数: {1}\n- 队伍 raw 行数: {2}\n- 队伍有序去重后行数: {2}\n- 队伍无序去重后行数: {2}\n\n## Warning 列表\n\n- 无\n\n## Error 列表\n\n- 无\n", phase.collect_date, characters.len(), teams.len()))?;
    let manifest = bundle.manifest();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
}

fn team_values(phase: &PhaseRow, row: &TeamRow) -> Vec<String> {
    vec![
        phase.snapshot_id.clone(),
        phase.collect_date.clone(),
        row.mode.clone(),
        phase.mode_cn.clone(),
        row.sub_mode.clone(),
        "stage-1".into(),
        row.phase_ver.clone(),
        phase.phase_name.clone(),
        row.scope.clone(),
        String::new(),
        String::new(),
        row.chars[0].clone(),
        row.chars[1].clone(),
        row.chars[2].clone(),
        row.chars[3].clone(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        "fixture".into(),
        "teams.json".into(),
        "fixture://teams".into(),
        row.raw_index.to_string(),
        row.raw_json.clone(),
    ]
}

fn character_values(phase: &PhaseRow, row: &CharacterRow) -> Vec<String> {
    vec![
        phase.snapshot_id.clone(),
        phase.collect_date.clone(),
        phase.mode.clone(),
        phase.mode_cn.clone(),
        "all".into(),
        "全部".into(),
        phase.phase_ver.clone(),
        phase.phase_name.clone(),
        phase.start_date.clone(),
        phase.end_date.clone(),
        row.character_slug.clone(),
        row.character_name_en.clone(),
        String::new(),
        String::new(),
        String::new(),
        csv_float(Some(row.app_rate)),
        csv_float(row.app_rate_e0),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        row.source_kind.clone(),
        "fixture/builds.json".into(),
        "fixture://builds".into(),
        row.quality_flag.clone(),
    ]
}

fn tier_values(row: &TierRow) -> Vec<String> {
    vec![
        row.tier_snapshot_id.clone(),
        String::new(),
        String::new(),
        String::new(),
        row.tier_mode.clone(),
        String::new(),
        row.character_slug.clone(),
        row.character_name_en.clone(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        row.tier.clone(),
        row.rating.clone(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        row.source_url.clone(),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hsr::{make_phase_row, parse_builds_character_rows, parse_team_rows};

    #[test]
    fn writes_minimal_golden_bundle() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let phase = make_phase_row(
            "4.3.2",
            &fixture["config"],
            "moc",
            "4.3.2/",
            true,
            false,
            true,
            "2026-06-25",
        );
        let characters = parse_builds_character_rows(&fixture["builds"], "moc");
        let teams = parse_team_rows(
            &fixture["teams"],
            "moc",
            "4.2.1",
            "stage_1_combined.json",
            Some(2),
        );
        let tiers = [TierRow {
            tier_snapshot_id: "2026-06-25".into(),
            tier_mode: "moc".into(),
            character_slug: "topaz-and-numby".into(),
            character_name_en: "Topaz and Numby".into(),
            tier: "T1".into(),
            rating: "1".into(),
            source_url: "fixture://tier".into(),
        }];
        let bundle = build_minimal_export(&phase, &characters, &teams, &tiers).unwrap();
        for name in [
            "phase_index.csv",
            "character_usage_long.csv",
            "team_rank_raw.csv",
            "prydwen_tier_current.csv",
            "artifact_manifest.json",
        ] {
            assert!(bundle.get(name).is_some(), "missing {name}");
        }
        assert!(
            std::str::from_utf8(bundle.get("character_usage_long.csv").unwrap())
                .unwrap()
                .contains("topaz-and-numby,Topaz and Numby")
        );
        assert_eq!(bundle.manifest().len(), 17);
        for (name, expected) in [
            (
                "phase_index.csv",
                include_bytes!("../../../tests/fixtures/hsr_export_expected/phase_index.csv")
                    .as_slice(),
            ),
            (
                "character_usage_long.csv",
                include_bytes!(
                    "../../../tests/fixtures/hsr_export_expected/character_usage_long.csv"
                )
                .as_slice(),
            ),
            (
                "team_rank_raw.csv",
                include_bytes!("../../../tests/fixtures/hsr_export_expected/team_rank_raw.csv")
                    .as_slice(),
            ),
            (
                "prydwen_tier_current.csv",
                include_bytes!(
                    "../../../tests/fixtures/hsr_export_expected/prydwen_tier_current.csv"
                )
                .as_slice(),
            ),
        ] {
            assert_eq!(
                bundle.get(name).unwrap(),
                python_csv_bytes(expected),
                "golden mismatch: {name}"
            );
        }
        let actual_manifest: serde_json::Value =
            serde_json::from_slice(bundle.get("artifact_manifest.json").unwrap()).unwrap();
        assert_eq!(actual_manifest.as_array().unwrap().len(), 16);
        for name in [
            "name_map_unresolved.csv",
            "prydwen_tier_changelog.csv",
            "prydwen_tier_usage_trend.csv",
            "prydwen_tier_charts.csv",
        ] {
            let bytes = bundle.get(name).unwrap();
            assert!(bytes.starts_with(&[0xef, 0xbb, 0xbf]));
            assert!(bytes.ends_with(b"\r\n"));
        }
    }

    fn python_csv_bytes(source: &[u8]) -> Vec<u8> {
        let text = std::str::from_utf8(source).unwrap().replace("\r\n", "\n");
        let mut output = vec![0xEF, 0xBB, 0xBF];
        output.extend_from_slice(text.replace('\n', "\r\n").as_bytes());
        output
    }
}
