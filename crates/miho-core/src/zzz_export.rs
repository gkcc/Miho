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

pub fn fallback_name_rows(usage: &[UsageRow], teams: &[TeamRow]) -> Vec<NameRow> {
    let mut slugs = std::collections::BTreeSet::new();
    slugs.extend(usage.iter().map(|row| row.character_slug.clone()));
    for row in teams {
        slugs.extend([
            row.char_1_slug.clone(),
            row.char_2_slug.clone(),
            row.char_3_slug.clone(),
            row.bangboo_slug.clone(),
        ]);
    }
    slugs
        .into_iter()
        .filter(|slug| !slug.is_empty())
        .map(|slug| NameRow {
            character_slug: slug,
            character_name_en: String::new(),
            character_name_cn: String::new(),
            source: "Prydwen/HF slug".into(),
            needs_manual_check: "1".into(),
            aliases: String::new(),
            kind: "unknown".into(),
            release_order: "9999".into(),
        })
        .collect()
}

#[derive(Debug, Clone)]
pub struct ZzzExportSlice {
    pub phase: PhaseRow,
    pub usage: Vec<UsageRow>,
    pub teams: Vec<TeamRow>,
    pub names: Vec<NameRow>,
}

#[derive(Debug, Clone, Default)]
pub struct ZzzExportDataset {
    pub slices: Vec<ZzzExportSlice>,
}

/// Aggregate all snapshots before writing. Derivations are therefore computed
/// across slice boundaries instead of allowing the last snapshot to overwrite
/// files produced for earlier snapshots.
pub fn build_dataset_export(dataset: &ZzzExportDataset) -> Result<ArtifactBundle> {
    let Some(first) = dataset.slices.first() else {
        return build_empty_dataset_export();
    };
    let mut bundle = build_minimal_bundle(&first.phase, &first.usage, &first.teams, &first.names)?;
    bundle.add_csv(
        "phase_index.csv",
        PHASE,
        dataset
            .slices
            .iter()
            .map(|slice| phase_values(&slice.phase)),
    )?;

    let usage = dataset
        .slices
        .iter()
        .flat_map(|slice| slice.usage.iter().map(move |row| (&slice.phase, row)))
        .collect::<Vec<_>>();
    bundle.add_csv(
        "character_usage_long.csv",
        USAGE,
        usage.iter().map(|(phase, row)| usage_values(phase, row)),
    )?;
    let mut latest = std::collections::BTreeMap::new();
    for (phase, row) in &usage {
        let key = (
            phase.mode.clone(),
            row.sub_mode.clone(),
            phase.phase_ver.clone(),
            row.character_slug.clone(),
        );
        if latest
            .get(&key)
            .is_none_or(|(old, _): &(&PhaseRow, &UsageRow)| phase.collect_date >= old.collect_date)
        {
            latest.insert(key, (*phase, *row));
        }
    }
    let mut latest = latest.into_values().collect::<Vec<_>>();
    latest.sort_by(|(a_phase, a_row), (b_phase, b_row)| {
        a_phase
            .mode
            .cmp(&b_phase.mode)
            .then_with(|| a_row.sub_mode.cmp(&b_row.sub_mode))
            .then_with(|| a_row.character_slug.cmp(&b_row.character_slug))
    });
    bundle.add_csv(
        "character_usage_phase_latest.csv",
        USAGE,
        latest
            .into_iter()
            .map(|(phase, row)| usage_values(phase, row)),
    )?;

    let teams = dataset
        .slices
        .iter()
        .flat_map(|slice| slice.teams.iter().map(move |row| (&slice.phase, row)))
        .collect::<Vec<_>>();
    bundle.add_csv(
        "team_rank_raw.csv",
        TEAM,
        teams.iter().map(|(phase, row)| team_values(phase, row)),
    )?;
    let dedup = dedup_teams(&teams);
    bundle.add_csv(
        "team_rank_dedup_unordered.csv",
        TEAM,
        dedup
            .into_iter()
            .map(|(phase, row)| team_values(phase, row)),
    )?;

    let mut names = std::collections::BTreeMap::new();
    for row in dataset.slices.iter().flat_map(|slice| slice.names.iter()) {
        names.insert(row.character_slug.clone(), row);
    }
    bundle.add_csv(
        "name_map.csv",
        NAMES,
        names.values().map(|row| name_values(row)),
    )?;
    bundle.add_csv(
        "name_map_unresolved.csv",
        NAMES,
        names
            .values()
            .filter(|row| row.needs_manual_check == "1")
            .map(|row| name_values(row)),
    )?;
    bundle.add_text("export_report.md",format!("# 绝区零高难数据导出报告\n\n- 导出时间：fixture\n- 期数行数：{}\n- 角色出场率行数：{}\n- 队伍 raw 行数：{}\n- 待人工确认名称：{}\n",dataset.slices.len(),usage.len(),teams.len(),names.values().filter(|row|row.needs_manual_check=="1").count()))?;
    let manifest = bundle
        .manifest()
        .into_iter()
        .filter(|entry| entry.path != "artifact_manifest.json")
        .collect::<Vec<_>>();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
}

fn build_empty_dataset_export() -> Result<ArtifactBundle> {
    let mut bundle = ArtifactBundle::default();
    for (name, headers) in [
        ("phase_index.csv", PHASE),
        ("character_usage_long.csv", USAGE),
        ("character_usage_phase_latest.csv", USAGE),
        ("team_rank_raw.csv", TEAM),
        ("team_rank_dedup_unordered.csv", TEAM),
        ("name_map.csv", NAMES),
        ("name_map_unresolved.csv", NAMES),
        ("prydwen_tier_current.csv", PRYDWEN),
        ("prydwen_tier_history.csv", PRYDWEN),
        ("prydwen_tier_changelog.csv", CHANGELOG),
        ("prydwen_tier_changelog_history.csv", CHANGELOG),
    ] {
        bundle.add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(name, headers, vec![])?;
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
    bundle.add_text("export_report.md", "# 绝区零高难数据导出报告\n\n- 导出时间：fixture\n- 期数行数：0\n- 角色出场率行数：0\n- 队伍 raw 行数：0\n- 待人工确认名称：0\n- Prydwen 当前 T 榜行数：0\n- Prydwen changelog 行数：0\n\n## Warning 列表\n\n- 无\n\n## Error 列表\n\n- 无\n")?;
    let manifest = bundle.manifest();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
}

fn dedup_teams<'a>(teams: &[(&'a PhaseRow, &'a TeamRow)]) -> Vec<(&'a PhaseRow, &'a TeamRow)> {
    let mut groups = std::collections::BTreeMap::<String, Vec<(&PhaseRow, &TeamRow)>>::new();
    for &(phase, row) in teams {
        let mut chars = [&row.char_1_slug, &row.char_2_slug, &row.char_3_slug];
        chars.sort();
        let signature = format!(
            "{}|{}|{}|{}|bangboo:{}",
            phase.mode,
            row.sub_mode,
            phase.phase_ver,
            chars.into_iter().cloned().collect::<Vec<_>>().join(">"),
            row.bangboo_slug
        );
        groups.entry(signature).or_default().push((phase, row));
    }
    let mut output = groups
        .into_values()
        .map(|group| *group.iter().min_by(|a, b| zzz_team_cmp(a.1, b.1)).unwrap())
        .collect::<Vec<_>>();
    output.sort_by(|a, b| {
        a.0.mode
            .cmp(&b.0.mode)
            .then_with(|| a.1.sub_mode.cmp(&b.1.sub_mode))
            .then_with(|| zzz_team_cmp(a.1, b.1))
    });
    output
}

fn zzz_team_cmp(a: &TeamRow, b: &TeamRow) -> std::cmp::Ordering {
    a.rank
        .trunc()
        .partial_cmp(&b.rank.trunc())
        .unwrap_or(std::cmp::Ordering::Equal)
        .then_with(|| {
            b.app_rate
                .unwrap_or(0.0)
                .partial_cmp(&a.app_rate.unwrap_or(0.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .then_with(|| {
            b.avg_score
                .unwrap_or(0.0)
                .partial_cmp(&a.avg_score.unwrap_or(0.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
}

fn phase_values(phase: &PhaseRow) -> Vec<String> {
    vec![
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
        phase.note.clone(),
    ]
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
            phase.has_chars.to_string(),
            phase.has_comps.to_string(),
            phase.note.clone(),
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
                row.character_name_en.clone(),
                String::new(),
                row.role.clone(),
                row.rarity.clone(),
                csv_float(row.app_rate),
                csv_number(row.avg_score),
                csv_number(row.sample),
                csv_number(row.sample_players),
                csv_number(row.cons_avg),
                csv_number(row.char_level),
                csv_number(row.w_engine_level),
                csv_number(row.core_skill),
                row.source_kind.clone(),
                row.source_file.clone(),
                row.source_url.clone(),
                row.quality_flag.clone(),
            ]
        }),
    )?;
    let mut latest_usage = usage.iter().collect::<Vec<_>>();
    latest_usage.sort_by(|a, b| {
        a.sub_mode
            .cmp(&b.sub_mode)
            .then_with(|| a.character_slug.cmp(&b.character_slug))
    });
    bundle.add_csv(
        "character_usage_phase_latest.csv",
        USAGE,
        latest_usage.into_iter().map(|row| usage_values(phase, row)),
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
                csv_number(row.avg_score_m1),
                row.source_kind.clone(),
                row.source_file.clone(),
                row.source_url.clone(),
                row.raw_index.to_string(),
                row.raw_json.clone(),
            ]
        }),
    )?;
    let team_refs = teams.iter().map(|row| (phase, row)).collect::<Vec<_>>();
    let dedup = dedup_teams(&team_refs);
    bundle.add_csv(
        "team_rank_dedup_unordered.csv",
        TEAM,
        dedup
            .into_iter()
            .map(|(phase, row)| team_values(phase, row)),
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
        row.character_name_en.clone(),
        String::new(),
        row.role.clone(),
        row.rarity.clone(),
        csv_float(row.app_rate),
        csv_number(row.avg_score),
        csv_number(row.sample),
        csv_number(row.sample_players),
        csv_number(row.cons_avg),
        csv_number(row.char_level),
        csv_number(row.w_engine_level),
        csv_number(row.core_skill),
        row.source_kind.clone(),
        row.source_file.clone(),
        row.source_url.clone(),
        row.quality_flag.clone(),
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
        csv_number(row.avg_score_m1),
        row.source_kind.clone(),
        row.source_file.clone(),
        row.source_url.clone(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::zzz::{
        make_phase_row, parse_bangboo_rows, parse_team_rows, parse_usage, PhaseInput,
    };

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

    #[test]
    fn empty_dataset_writes_complete_header_only_export_set() {
        let bundle = build_dataset_export(&ZzzExportDataset::default()).unwrap();
        assert_eq!(bundle.manifest().len(), 14);
        for (name, header) in [
            ("phase_index.csv", "snapshot_id,collect_date"),
            ("character_usage_long.csv", "snapshot_id,collect_date"),
            (
                "character_usage_phase_latest.csv",
                "snapshot_id,collect_date",
            ),
            ("team_rank_raw.csv", "snapshot_id,collect_date"),
            ("team_rank_dedup_unordered.csv", "snapshot_id,collect_date"),
            ("name_map.csv", "character_slug,character_name_en"),
            (
                "name_map_unresolved.csv",
                "character_slug,character_name_en",
            ),
            ("prydwen_tier_current.csv", "tier_snapshot_id,fetched_at"),
            ("prydwen_tier_history.csv", "tier_snapshot_id,fetched_at"),
            ("prydwen_tier_changelog.csv", "changelog_date,source_url"),
            (
                "prydwen_tier_changelog_history.csv",
                "changelog_date,source_url",
            ),
            (
                "prydwen_tier_usage_trend.csv",
                "tier_snapshot_id,fetched_at",
            ),
        ] {
            let bytes = bundle.get(name).unwrap();
            assert!(bytes.starts_with(&[0xef, 0xbb, 0xbf]));
            assert!(bytes.ends_with(b"\r\n"));
            let text = std::str::from_utf8(&bytes[3..]).unwrap();
            assert!(text.starts_with(header), "wrong header: {name}");
            assert_eq!(text.lines().count(), 1, "unexpected data row: {name}");
        }
        let manifest: serde_json::Value =
            serde_json::from_slice(bundle.get("artifact_manifest.json").unwrap()).unwrap();
        assert_eq!(manifest.as_array().unwrap().len(), 13);
        assert!(std::str::from_utf8(bundle.get("export_report.md").unwrap())
            .unwrap()
            .contains("期数行数：0"));
    }

    #[test]
    fn bangboo_usage_preserves_typed_fields_in_export() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_parser_minimal.json"
        ))
        .unwrap();
        let mut phase =
            make_phase_row(serde_json::from_value::<PhaseInput>(fixture["phase"].clone()).unwrap());
        phase.has_chars = 1;
        phase.has_comps = 0;
        phase.note = "config missing; dates unavailable".into();
        let usage = parse_bangboo_rows(
            fixture["bangboo"].as_array().unwrap(),
            "3.0.1/sd/chars/bangboo_all.json",
            "fixture://bangboo",
        );
        let bundle = build_minimal_bundle(&phase, &usage, &[], &[]).unwrap();
        let phase_csv = std::str::from_utf8(bundle.get("phase_index.csv").unwrap()).unwrap();
        assert!(phase_csv.contains(",1,0,config missing; dates unavailable"));
        let usage_csv =
            std::str::from_utf8(bundle.get("character_usage_long.csv").unwrap()).unwrap();
        assert!(usage_csv.contains(",bangboo,邦布,"));
        assert!(usage_csv.contains(",safety,Safety,,bangboo,S,7.5,123,"));
        assert!(
            usage_csv.contains(",hf_bangboo,3.0.1/sd/chars/bangboo_all.json,fixture://bangboo,ok")
        );
    }

    #[test]
    fn unordered_team_dedup_selects_python_sort_key_best_row() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_parser_minimal.json"
        ))
        .unwrap();
        let phase =
            make_phase_row(serde_json::from_value::<PhaseInput>(fixture["phase"].clone()).unwrap());
        let mut rows = parse_team_rows(
            fixture["teams"].as_array().unwrap().clone(),
            "sd",
            fixture["scope"].as_str().unwrap(),
        );
        let mut better = rows.remove(0);
        better.rank = 2.0;
        better.app_rate = Some(90.0);
        better.raw_index = 7;
        let mut worse = better.clone();
        worse.rank = 3.0;
        worse.app_rate = Some(99.0);
        worse.raw_index = 8;
        let dedup = dedup_teams(&[(&phase, &worse), (&phase, &better)]);
        assert_eq!(dedup.len(), 1);
        assert_eq!(dedup[0].1.raw_index, 7);
    }

    #[test]
    fn dataset_export_keeps_two_slices_and_derives_globally() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_parser_minimal.json"
        ))
        .unwrap();
        let first =
            make_phase_row(serde_json::from_value::<PhaseInput>(fixture["phase"].clone()).unwrap());
        let mut second = first.clone();
        second.snapshot_id = "3.0.2".into();
        second.mode = "da".into();
        second.mode_cn = "危局强袭".into();
        second.phase_ver = "3.0.2".into();
        second.collect_date = "2026-07-01".into();
        let usage = parse_usage(&fixture["usage"], "sd");
        let teams = parse_team_rows(
            fixture["teams"].as_array().unwrap().clone(),
            "sd",
            fixture["scope"].as_str().unwrap(),
        );
        let dataset = ZzzExportDataset {
            slices: vec![
                ZzzExportSlice {
                    phase: first,
                    usage: usage.clone(),
                    teams: teams.clone(),
                    names: vec![],
                },
                ZzzExportSlice {
                    phase: second,
                    usage,
                    teams,
                    names: vec![],
                },
            ],
        };
        let bundle = build_dataset_export(&dataset).unwrap();
        let phases = std::str::from_utf8(bundle.get("phase_index.csv").unwrap()).unwrap();
        assert!(phases.contains("3.0.1") && phases.contains("3.0.2"));
        let raw = std::str::from_utf8(bundle.get("team_rank_raw.csv").unwrap()).unwrap();
        assert_eq!(raw.matches("fixture://local").count(), 4);
        let latest =
            std::str::from_utf8(bundle.get("character_usage_phase_latest.csv").unwrap()).unwrap();
        assert!(latest.contains(",sd,") && latest.contains(",da,"));
    }

    fn python_csv_bytes(source: &[u8]) -> Vec<u8> {
        let text = std::str::from_utf8(source).unwrap().replace("\r\n", "\n");
        let mut output = vec![0xEF, 0xBB, 0xBF];
        output.extend_from_slice(text.replace('\n', "\r\n").as_bytes());
        output
    }
}
