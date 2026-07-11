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
    let manifest = bundle.manifest();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
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
        assert_eq!(bundle.manifest().len(), 5);
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
        let expected_manifest: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_export_expected/artifact_manifest.json"
        ))
        .unwrap();
        assert_eq!(actual_manifest, expected_manifest);
    }

    fn python_csv_bytes(source: &[u8]) -> Vec<u8> {
        let text = std::str::from_utf8(source).unwrap().replace("\r\n", "\n");
        let mut output = vec![0xEF, 0xBB, 0xBF];
        output.extend_from_slice(text.replace('\n', "\r\n").as_bytes());
        output
    }
}
