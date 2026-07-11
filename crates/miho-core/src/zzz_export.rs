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
const PRYDWEN: &[&str] = &[
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
];
const CHANGELOG: &[&str] = &["changelog_date", "source_url", "character_slugs", "text"];

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
        "character_usage_phase_latest.csv",
        USAGE,
        usage.iter().map(|row| usage_values(phase, row)),
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
    // The fixed slice has already been normalized to one row per raw record. The
    // production parser orders rank before app-rate, so stable signature dedup is
    // deterministic here as well.
    let mut dedup = std::collections::BTreeMap::new();
    for row in teams {
        let mut chars = [&row.char_1_slug, &row.char_2_slug, &row.char_3_slug];
        chars.sort();
        let key = format!(
            "{}|{}|{}|{}|{}",
            phase.mode,
            row.sub_mode,
            phase.phase_ver,
            chars.into_iter().cloned().collect::<Vec<_>>().join(">"),
            row.bangboo_slug
        );
        dedup.entry(key).or_insert(row);
    }
    bundle.add_csv(
        "team_rank_dedup_unordered.csv",
        TEAM,
        dedup.into_values().map(|row| team_values(phase, row)),
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
    bundle.add_csv(
        "name_map_unresolved.csv",
        NAMES,
        names
            .iter()
            .filter(|row| row.needs_manual_check == "1")
            .map(name_values),
    )?;
    for name in ["prydwen_tier_current.csv", "prydwen_tier_history.csv"] {
        bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(name, PRYDWEN, vec![])?;
    }
    for name in [
        "prydwen_tier_changelog.csv",
        "prydwen_tier_changelog_history.csv",
    ] {
        bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(name, CHANGELOG, vec![])?;
    }
    let trend = PRYDWEN
        .iter()
        .copied()
        .chain([
            "collect_date",
            "phase_ver",
            "phase_name",
            "app_rate",
            "avg_score",
            "quality_flag",
        ])
        .collect::<Vec<_>>();
    bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
        "prydwen_tier_usage_trend.csv",
        &trend,
        vec![],
    )?;
    bundle.add_text("export_report.md", format!("# 绝区零高难数据导出报告\n\n- 导出时间：fixture\n- 期数行数：1\n- 角色出场率行数：{}\n- 队伍 raw 行数：{}\n- 待人工确认名称：{}\n- Prydwen 当前 T 榜行数：0\n- Prydwen changelog 行数：0\n\n## Warning 列表\n\n- 无\n\n## Error 列表\n\n- 无\n", usage.len(), teams.len(), names.iter().filter(|row| row.needs_manual_check == "1").count()))?;
    let manifest = bundle.manifest();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
}

fn usage_values(phase: &PhaseRow, row: &UsageRow) -> Vec<String> {
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
}
fn team_values(phase: &PhaseRow, row: &TeamRow) -> Vec<String> {
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
}
fn name_values(row: &NameRow) -> Vec<String> {
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
        assert_eq!(bundle.manifest().len(), 14);
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
