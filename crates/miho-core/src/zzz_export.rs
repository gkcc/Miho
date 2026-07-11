use serde::{Deserialize, Serialize};

use crate::{
    output::{csv_float, csv_number, ArtifactBundle},
    zzz::{PhaseRow, TeamRow, UsageRow},
    Result,
};

const PHASE: &[&str] = &[
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
];
const USAGE: &[&str] = &[
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
];
const TEAM: &[&str] = &[
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
];
const NAMES: &[&str] = &[
    "character_slug",
    "character_name_en",
    "character_name_cn",
    "source",
    "needs_manual_check",
    "aliases",
    "kind",
    "release_order",
];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NameRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub source: String,
    pub needs_manual_check: String,
    #[serde(default)]
    pub aliases: String,
    #[serde(default = "agent")]
    pub kind: String,
    #[serde(default = "last_order")]
    pub release_order: String,
}

fn agent() -> String {
    "agent".into()
}
fn last_order() -> String {
    "9999".into()
}

pub fn build_minimal_bundle(
    phase: &PhaseRow,
    usage: &[UsageRow],
    teams: &[TeamRow],
    names: &[NameRow],
) -> Result<ArtifactBundle> {
    let mut bundle = ArtifactBundle::default();
    bundle.add_csv(
        "phase_index.csv",
        PHASE,
        [vec![
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
            "1".into(),
            "1".into(),
            String::new(),
        ]],
    )?;
    bundle.add_csv(
        "character_usage_long.csv",
        USAGE,
        usage.iter().map(|row| {
            vec![
                phase.snapshot_id.clone(),
                phase.collect_date.clone(),
                phase.mode.clone(),
                phase.mode_cn.clone(),
                row.sub_mode.clone(),
                row.sub_mode_cn.clone(),
                phase.phase_ver.clone(),
                phase.phase_name.clone(),
                phase.start_date.clone(),
                phase.end_date.clone(),
                row.character_slug.clone(),
                slug_name(&row.character_slug),
                String::new(),
                String::new(),
                String::new(),
                csv_float(row.app_rate),
                csv_number(row.avg_score),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                "hf_builds".into(),
                "fixture.json".into(),
                "fixture://local".into(),
                "ok".into(),
            ]
        }),
    )?;
    bundle.add_csv(
        "team_rank_raw.csv",
        TEAM,
        teams.iter().map(|row| {
            vec![
                phase.snapshot_id.clone(),
                phase.collect_date.clone(),
                phase.mode.clone(),
                phase.mode_cn.clone(),
                row.sub_mode.clone(),
                row.sub_mode_cn.clone(),
                phase.phase_ver.clone(),
                phase.phase_name.clone(),
                row.scope.clone(),
                csv_number(Some(row.rank)),
                row.char_1_slug.clone(),
                row.char_2_slug.clone(),
                row.char_3_slug.clone(),
                row.bangboo_slug.clone(),
                String::new(),
                String::new(),
                String::new(),
                String::new(),
                csv_float(row.app_rate),
                csv_number(row.avg_score),
                String::new(),
                "hf_comps".into(),
                "fixture.json".into(),
                "fixture://local".into(),
                row.raw_index.to_string(),
                row.raw_json.clone(),
            ]
        }),
    )?;
    bundle.add_csv(
        "name_map.csv",
        NAMES,
        names.iter().map(|row| {
            vec![
                row.character_slug.clone(),
                row.character_name_en.clone(),
                row.character_name_cn.clone(),
                row.source.clone(),
                row.needs_manual_check.clone(),
                row.aliases.clone(),
                row.kind.clone(),
                row.release_order.clone(),
            ]
        }),
    )?;
    let manifest = bundle.manifest();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
}

fn slug_name(slug: &str) -> String {
    slug.split('-')
        .map(|v| {
            let mut chars = v.chars();
            chars
                .next()
                .map(|c| c.to_uppercase().collect::<String>() + chars.as_str())
                .unwrap_or_default()
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::zzz::{make_phase_row, parse_team_rows, parse_usage, PhaseInput};

    #[test]
    fn minimal_bundle_contains_stable_export_set() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_parser_minimal.json"
        ))
        .unwrap();
        let phase =
            make_phase_row(serde_json::from_value::<PhaseInput>(fixture["phase"].clone()).unwrap());
        let usage = parse_usage(&fixture["usage"], "sd");
        let teams = parse_team_rows(
            fixture["teams"].as_array().unwrap().clone(),
            "sd",
            fixture["scope"].as_str().unwrap(),
        );
        let names = [NameRow {
            character_slug: "miyabi".into(),
            character_name_en: "Miyabi".into(),
            character_name_cn: "星见 雅".into(),
            source: "fixture".into(),
            needs_manual_check: "0".into(),
            aliases: String::new(),
            kind: "agent".into(),
            release_order: "10".into(),
        }];
        let bundle = build_minimal_bundle(&phase, &usage, &teams, &names).unwrap();
        assert_eq!(bundle.manifest().len(), 5);
        assert!(bundle
            .get("phase_index.csv")
            .unwrap()
            .starts_with(b"\xEF\xBB\xBFsnapshot_id,collect_date"));
        assert!(bundle.get("artifact_manifest.json").is_some());
        for (name, expected) in [
            (
                "phase_index.csv",
                include_bytes!("../../../tests/fixtures/zzz_export_expected/phase_index.csv")
                    .as_slice(),
            ),
            (
                "character_usage_long.csv",
                include_bytes!(
                    "../../../tests/fixtures/zzz_export_expected/character_usage_long.csv"
                )
                .as_slice(),
            ),
            (
                "team_rank_raw.csv",
                include_bytes!("../../../tests/fixtures/zzz_export_expected/team_rank_raw.csv")
                    .as_slice(),
            ),
            (
                "name_map.csv",
                include_bytes!("../../../tests/fixtures/zzz_export_expected/name_map.csv")
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
            "../../../tests/fixtures/zzz_export_expected/artifact_manifest.json"
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
