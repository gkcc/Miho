use std::path::PathBuf;

use crate::{
    hsr::{CharacterRow, HistographRow, PhaseRow, TeamRow},
    hsr_history::{TierUsageChart, TrendRow},
    hsr_names::{NameResolver, NameRow},
    hsr_sources::{python_csv_value, ChangelogRow},
    normalize::{character_slug_to_english, natural_version_cmp},
    output::{csv_float, ArtifactBundle},
    Result,
};

pub use crate::hsr_sources::TierRow;

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
const HISTOGRAPH_HEADERS: &[&str] = &[
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
];

#[derive(Debug, Clone)]
pub struct HsrExportSlice {
    pub phase: PhaseRow,
    pub characters: Vec<CharacterRow>,
    pub teams: Vec<TeamRow>,
    pub tiers: Vec<TierRow>,
}

#[derive(Debug, Clone)]
pub struct HsrHistographSlice {
    pub phase: PhaseRow,
    pub rows: Vec<HistographRow>,
}

#[derive(Debug, Clone, Default)]
pub struct HsrExportDataset {
    pub slices: Vec<HsrExportSlice>,
    pub histograph_slices: Vec<HsrHistographSlice>,
    pub name_rows: Vec<NameRow>,
    pub tier_current_rows: Vec<TierRow>,
    pub tier_history_rows: Vec<TierRow>,
    pub tier_changelog_rows: Vec<ChangelogRow>,
    pub tier_changelog_history_rows: Vec<ChangelogRow>,
    pub tier_usage_trend_rows: Vec<TrendRow>,
    pub tier_charts: Vec<TierUsageChart>,
    pub display_output_root: Option<PathBuf>,
    pub raw_text_artifacts: Vec<(String, String)>,
}

pub fn build_minimal_export(
    phase: &PhaseRow,
    characters: &[CharacterRow],
    teams: &[TeamRow],
    tiers: &[TierRow],
) -> Result<ArtifactBundle> {
    build_dataset_export(&HsrExportDataset {
        slices: vec![HsrExportSlice {
            phase: phase.clone(),
            characters: characters.to_vec(),
            teams: teams.to_vec(),
            tiers: tiers.to_vec(),
        }],
        histograph_slices: vec![],
        ..Default::default()
    })
}

pub fn build_dataset_export(dataset: &HsrExportDataset) -> Result<ArtifactBundle> {
    build_dataset_export_with_warnings(dataset, &[])
}

pub fn build_dataset_export_with_warnings(
    dataset: &HsrExportDataset,
    warnings: &[String],
) -> Result<ArtifactBundle> {
    let phases = dataset
        .slices
        .iter()
        .map(|slice| &slice.phase)
        .collect::<Vec<_>>();
    let characters = dataset
        .slices
        .iter()
        .flat_map(|slice| slice.characters.iter().map(move |row| (&slice.phase, row)))
        .collect::<Vec<_>>();
    let teams = dataset
        .slices
        .iter()
        .flat_map(|slice| slice.teams.iter().map(move |row| (&slice.phase, row)))
        .collect::<Vec<_>>();
    let histograph = dataset
        .histograph_slices
        .iter()
        .flat_map(|slice| slice.rows.iter().map(move |row| (&slice.phase, row)))
        .collect::<Vec<_>>();
    let ordered_teams = dedup_ordered(&teams);
    let unordered_teams = dedup_unordered(&ordered_teams);
    let mut tiers = dataset
        .slices
        .iter()
        .flat_map(|slice| slice.tiers.iter())
        .collect::<Vec<_>>();
    tiers.extend(dataset.tier_current_rows.iter());
    let names = if dataset.name_rows.is_empty() {
        derived_names(&characters, &histograph, &teams, &tiers)
    } else {
        dataset.name_rows.clone()
    };
    let name_resolver = NameResolver::new(&names);
    let tier_history = if dataset.tier_history_rows.is_empty() {
        tiers.clone()
    } else {
        dataset.tier_history_rows.iter().collect()
    };
    let report_date = phases
        .iter()
        .map(|phase| phase.collect_date.as_str())
        .max()
        .unwrap_or("");
    let mut bundle = ArtifactBundle::default();
    bundle.add_csv(
        "phase_index.csv",
        PHASE_HEADERS,
        phases.iter().map(|phase| {
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
                phase.has_histograph.to_string(),
                phase.note.clone(),
            ]
        }),
    )?;
    bundle.add_csv(
        "character_usage_long.csv",
        CHARACTER_HEADERS,
        characters
            .iter()
            .map(|(phase, row)| character_values(phase, row, &name_resolver)),
    )?;
    bundle.add_csv(
        "team_rank_raw.csv",
        TEAM_HEADERS,
        teams
            .iter()
            .map(|(phase, row)| team_values(phase, row, &name_resolver)),
    )?;
    bundle.add_csv(
        "prydwen_tier_current.csv",
        TIER_HEADERS,
        tiers.iter().map(|row| tier_values(row, &name_resolver)),
    )?;
    bundle.add_csv(
        "histograph_usage_long.csv",
        HISTOGRAPH_HEADERS,
        histograph.iter().map(|(phase, row)| {
            vec![
                phase.snapshot_id.clone(),
                phase.collect_date.clone(),
                phase.mode.clone(),
                phase.mode_cn.clone(),
                row.character_slug.clone(),
                resolved_english(&name_resolver, &row.character_slug, &row.character_name_en),
                name_resolver.chinese(&row.character_slug),
                csv_float(Some(row.usage_value)),
                row.source_file.clone(),
                "trend auxiliary; not a full character usage table".into(),
            ]
        }),
    )?;
    bundle.add_csv(
        "character_usage_phase_latest.csv",
        CHARACTER_HEADERS,
        latest_characters(&characters)
            .into_iter()
            .map(|(phase, row)| character_values(phase, row, &name_resolver)),
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
        ordered_teams.iter().map(|item| {
            team_values(item.phase, item.row, &name_resolver)
                .into_iter()
                .chain([
                    item.signature.clone(),
                    item.count.to_string(),
                    item.files.clone(),
                ])
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
        unordered_teams.iter().map(|item| {
            team_values(item.phase, item.row, &name_resolver)
                .into_iter()
                .chain([
                    item.best_ordered.clone(),
                    item.count.to_string(),
                    item.files.clone(),
                    item.signature.clone(),
                    item.examples.clone(),
                ])
                .collect::<Vec<_>>()
        }),
    )?;
    bundle.add_csv(
        "name_map.csv",
        NAME_HEADERS,
        names.iter().map(|row| {
            vec![
                row.character_slug.clone(),
                row.character_name_en.clone(),
                row.character_name_cn.clone(),
                row.source.clone(),
                row.needs_manual_check.clone(),
                row.aliases.clone(),
            ]
        }),
    )?;
    bundle.add_csv(
        "name_map_unresolved.csv",
        NAME_HEADERS,
        names
            .iter()
            .filter(|row| row.needs_manual_check == "1")
            .map(|row| {
                vec![
                    row.character_slug.clone(),
                    row.character_name_en.clone(),
                    row.character_name_cn.clone(),
                    row.source.clone(),
                    row.needs_manual_check.clone(),
                    row.aliases.clone(),
                ]
            }),
    )?;
    bundle.add_csv(
        "prydwen_tier_history.csv",
        TIER_HEADERS,
        tier_history
            .iter()
            .map(|row| tier_values(row, &name_resolver)),
    )?;
    bundle.add_csv(
        "prydwen_tier_changelog.csv",
        CHANGELOG_HEADERS,
        dataset.tier_changelog_rows.iter().map(changelog_values),
    )?;
    bundle.add_csv(
        "prydwen_tier_changelog_history.csv",
        CHANGELOG_HEADERS,
        dataset
            .tier_changelog_history_rows
            .iter()
            .map(changelog_values),
    )?;
    bundle.add_csv(
        "prydwen_tier_usage_trend.csv",
        TREND_HEADERS,
        dataset
            .tier_usage_trend_rows
            .iter()
            .map(|row| trend_values(row, &name_resolver)),
    )?;
    bundle.add_csv(
        "prydwen_tier_charts.csv",
        CHART_HEADERS,
        dataset.tier_charts.iter().map(|chart| {
            vec![
                chart.tier_mode.clone(),
                chart.tier_mode_cn.clone(),
                chart.role_group.clone(),
                chart.role_group_cn.clone(),
                chart_display_path(dataset, &chart.filename),
                chart.series_count.to_string(),
                chart.point_count.to_string(),
            ]
        }),
    )?;
    for chart in &dataset.tier_charts {
        bundle.add_text(
            format!("charts/prydwen_tier_usage/{}", chart.filename),
            &chart.svg,
        )?;
    }
    for (path, text) in &dataset.raw_text_artifacts {
        bundle.add_text(path, text)?;
    }
    bundle.add_csv(
        "overview.csv",
        OVERVIEW_HEADERS,
        overview_rows(
            &phases,
            OverviewCounts {
                characters: characters.len(),
                raw_teams: teams.len(),
                ordered_teams: ordered_teams.len(),
                unordered_teams: unordered_teams.len(),
                names: names.len(),
                unresolved_names: names
                    .iter()
                    .filter(|row| row.needs_manual_check == "1")
                    .count(),
                tiers: tiers.len(),
                trend_rows: dataset.tier_usage_trend_rows.len(),
                charts: dataset.tier_charts.len(),
            },
            warnings,
        ),
    )?;
    let (dynamic_header_strings, latest_rows) = latest_usage_view(&characters, &name_resolver);
    let dynamic_headers = dynamic_header_strings
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    bundle.add_csv("latest_usage_cn.csv", &dynamic_headers, latest_rows)?;
    let top_rows = top_teams_latest(&unordered_teams, &name_resolver);
    let top_headers: &[&str] = if top_rows.is_empty() {
        &[]
    } else {
        &[
            "mode_cn",
            "mode",
            "sub_mode_cn",
            "sub_mode",
            "phase_ver",
            "rank",
            "team_cn",
            "app_rate",
            "avg_round",
            "source_kind",
            "duplicate_count",
            "unordered_signature",
        ]
    };
    bundle.add_csv("top_teams_latest.csv", top_headers, top_rows)?;
    bundle.add_text("export_report.md", format!("# HSR Endgame Export Report\n\n- from_date / to_date: {0} / {0}\n- 成功读取的 snapshot 数: {5}\n\n## 表行数\n\n- 角色表行数: {1}\n- 队伍 raw 行数: {2}\n- 队伍有序去重后行数: {3}\n- 队伍无序去重后行数: {4}\n\n## Warning 列表\n\n- 无\n\n## Error 列表\n\n- 无\n", report_date, characters.len(), teams.len(), ordered_teams.len(), unordered_teams.len(), phases.iter().map(|p| &p.snapshot_id).collect::<std::collections::BTreeSet<_>>().len()))?;
    let manifest = bundle.manifest();
    bundle.add_json("artifact_manifest.json", &manifest)?;
    Ok(bundle)
}

struct OverviewCounts {
    characters: usize,
    raw_teams: usize,
    ordered_teams: usize,
    unordered_teams: usize,
    names: usize,
    unresolved_names: usize,
    tiers: usize,
    trend_rows: usize,
    charts: usize,
}

fn overview_rows(
    phases: &[&PhaseRow],
    counts: OverviewCounts,
    warnings: &[String],
) -> Vec<Vec<String>> {
    let snapshots = phases
        .iter()
        .map(|phase| phase.snapshot_id.as_str())
        .collect::<std::collections::BTreeSet<_>>()
        .len();
    let modes = phases
        .iter()
        .map(|phase| (phase.mode.as_str(), phase.mode_cn.as_str()))
        .collect::<std::collections::BTreeMap<_, _>>();
    let mode_summary = modes
        .iter()
        .map(|(mode, name)| format!("{name}({mode})"))
        .collect::<Vec<_>>()
        .join(", ");
    let mut rows = vec![
        vec!["summary".into(), "snapshots".into(), snapshots.to_string()],
        vec!["summary".into(), "modes".into(), mode_summary],
        vec![
            "rows".into(),
            "character_usage_long".into(),
            counts.characters.to_string(),
        ],
        vec![
            "rows".into(),
            "team_rank_raw".into(),
            counts.raw_teams.to_string(),
        ],
        vec![
            "rows".into(),
            "team_rank_dedup_ordered".into(),
            counts.ordered_teams.to_string(),
        ],
        vec![
            "rows".into(),
            "team_rank_dedup_unordered".into(),
            counts.unordered_teams.to_string(),
        ],
        vec![
            "dedup".into(),
            "raw_rows_removed_by_ordered_dedup".into(),
            counts
                .raw_teams
                .saturating_sub(counts.ordered_teams)
                .to_string(),
        ],
        vec![
            "dedup".into(),
            "raw_rows_removed_by_unordered_dedup".into(),
            counts
                .raw_teams
                .saturating_sub(counts.unordered_teams)
                .to_string(),
        ],
        vec![
            "display".into(),
            "top_teams_latest".into(),
            "unordered unique Top 100 per mode".into(),
        ],
        vec!["names".into(), "name_map".into(), counts.names.to_string()],
        vec![
            "names".into(),
            "name_map_unresolved".into(),
            counts.unresolved_names.to_string(),
        ],
        vec![
            "prydwen_tier".into(),
            "current_rows".into(),
            counts.tiers.to_string(),
        ],
        vec![
            "prydwen_tier".into(),
            "usage_trend_rows_t0_t2".into(),
            counts.trend_rows.to_string(),
        ],
        vec![
            "prydwen_tier".into(),
            "charts".into(),
            counts.charts.to_string(),
        ],
        vec![
            "quality".into(),
            "warnings".into(),
            warnings.len().to_string(),
        ],
    ];
    for (mode, name) in modes {
        rows.push(vec![
            "coverage".into(),
            name.into(),
            phases
                .iter()
                .filter(|phase| phase.mode == mode)
                .count()
                .to_string(),
        ]);
    }
    for warning in warnings.iter().take(8) {
        rows.push(vec!["warning".into(), String::new(), warning.clone()]);
    }
    rows
}

fn latest_characters<'a>(
    rows: &[(&'a PhaseRow, &'a CharacterRow)],
) -> Vec<(&'a PhaseRow, &'a CharacterRow)> {
    let mut latest = std::collections::BTreeMap::new();
    for &(phase, row) in rows {
        let key = (
            phase.mode.clone(),
            phase.phase_ver.clone(),
            row.character_slug.clone(),
        );
        if latest
            .get(&key)
            .is_none_or(|(old, _): &(&PhaseRow, &CharacterRow)| {
                old.collect_date <= phase.collect_date
            })
        {
            latest.insert(key, (phase, row));
        }
    }
    latest.into_values().collect()
}

struct DerivedName {
    slug: String,
    english: String,
    chinese: String,
    source: String,
}

fn derived_names(
    characters: &[(&PhaseRow, &CharacterRow)],
    histograph: &[(&PhaseRow, &HistographRow)],
    teams: &[(&PhaseRow, &TeamRow)],
    tiers: &[&TierRow],
) -> Vec<NameRow> {
    let mut values = std::collections::BTreeMap::<String, DerivedName>::new();
    for (_, row) in characters {
        add_name_candidate(
            &mut values,
            &row.character_slug,
            &row.character_name_en,
            "",
            if row.source_kind.is_empty() {
                &row.source_file
            } else {
                &row.source_kind
            },
        );
    }
    for (_, row) in histograph {
        add_name_candidate(
            &mut values,
            &row.character_slug,
            &row.character_name_en,
            "",
            &row.source_file,
        );
    }
    for (_, row) in teams {
        for slug in &row.chars {
            add_name_candidate(
                &mut values,
                slug,
                "",
                "",
                if row.source_kind.is_empty() {
                    "team"
                } else {
                    &row.source_kind
                },
            );
        }
    }
    for row in tiers {
        add_name_candidate(
            &mut values,
            &row.character_slug,
            &row.character_name_en,
            &row.character_name_cn,
            "source",
        );
    }
    for row in values.values_mut() {
        if row.english.is_empty() {
            row.english = character_slug_to_english(&row.slug);
        }
    }
    values
        .into_values()
        .map(|row| NameRow {
            character_slug: row.slug,
            character_name_en: row.english,
            needs_manual_check: if row.chinese.is_empty() { "1" } else { "0" }.into(),
            character_name_cn: row.chinese,
            source: row.source,
            aliases: String::new(),
        })
        .collect()
}

fn add_name_candidate(
    values: &mut std::collections::BTreeMap<String, DerivedName>,
    slug: &str,
    english: &str,
    chinese: &str,
    source: &str,
) {
    if slug.is_empty() {
        return;
    }
    let row = values
        .entry(slug.to_owned())
        .or_insert_with(|| DerivedName {
            slug: slug.to_owned(),
            english: String::new(),
            chinese: String::new(),
            source: if source.is_empty() {
                "source".into()
            } else {
                source.into()
            },
        });
    if row.english.is_empty() && !english.is_empty() {
        row.english = english.into();
    }
    if row.chinese.is_empty() && !chinese.is_empty() {
        row.chinese = chinese.into();
    }
}

struct OrderedTeam<'a> {
    phase: &'a PhaseRow,
    row: &'a TeamRow,
    signature: String,
    count: usize,
    files: String,
}
struct UnorderedTeam<'a> {
    phase: &'a PhaseRow,
    row: &'a TeamRow,
    signature: String,
    best_ordered: String,
    count: usize,
    files: String,
    examples: String,
}

fn dedup_ordered<'a>(rows: &[(&'a PhaseRow, &'a TeamRow)]) -> Vec<OrderedTeam<'a>> {
    let mut groups = std::collections::BTreeMap::<String, Vec<(&PhaseRow, &TeamRow)>>::new();
    for &(phase, row) in rows {
        groups
            .entry(row.signatures(phase).0)
            .or_default()
            .push((phase, row));
    }
    let mut output = groups
        .into_iter()
        .map(|(signature, group)| {
            let (phase, row) = *group.iter().min_by(|a, b| team_best_cmp(a.1, b.1)).unwrap();
            let files = group
                .iter()
                .map(|(_, row)| row.source_file.clone())
                .filter(|value| !value.is_empty())
                .collect::<std::collections::BTreeSet<_>>()
                .into_iter()
                .collect::<Vec<_>>()
                .join(";");
            OrderedTeam {
                phase,
                row,
                signature,
                count: group.len(),
                files,
            }
        })
        .collect::<Vec<_>>();
    output.sort_by(|a, b| team_output_cmp(a.phase, a.row, b.phase, b.row));
    output
}

fn dedup_unordered<'a>(rows: &[OrderedTeam<'a>]) -> Vec<UnorderedTeam<'a>> {
    let mut groups = std::collections::BTreeMap::<String, Vec<&OrderedTeam<'a>>>::new();
    for row in rows {
        groups
            .entry(row.row.signatures(row.phase).1)
            .or_default()
            .push(row);
    }
    let mut output = groups
        .into_iter()
        .map(|(signature, group)| {
            let best = *group
                .iter()
                .min_by(|a, b| team_best_cmp(a.row, b.row))
                .unwrap();
            let count = group.iter().map(|row| row.count).sum();
            let files = best.files.clone();
            let examples = group
                .iter()
                .map(|row| row.signature.clone())
                .collect::<std::collections::BTreeSet<_>>()
                .into_iter()
                .collect::<Vec<_>>()
                .join(";");
            UnorderedTeam {
                phase: best.phase,
                row: best.row,
                signature,
                best_ordered: best.signature.clone(),
                count,
                files,
                examples,
            }
        })
        .collect::<Vec<_>>();
    output.sort_by(|a, b| team_output_cmp(a.phase, a.row, b.phase, b.row));
    output
}

fn team_best_cmp(a: &TeamRow, b: &TeamRow) -> std::cmp::Ordering {
    source_priority(&a.source_kind)
        .cmp(&source_priority(&b.source_kind))
        .then_with(|| {
            a.rank
                .unwrap_or(1_000_000.0)
                .partial_cmp(&b.rank.unwrap_or(1_000_000.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .then_with(|| {
            b.app_rate
                .unwrap_or(-1.0)
                .partial_cmp(&a.app_rate.unwrap_or(-1.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
}
fn team_output_cmp(ap: &PhaseRow, a: &TeamRow, bp: &PhaseRow, b: &TeamRow) -> std::cmp::Ordering {
    a.mode
        .cmp(&b.mode)
        .then_with(|| a.sub_mode.cmp(&b.sub_mode))
        .then_with(|| a.phase_ver.cmp(&b.phase_ver))
        .then_with(|| {
            a.rank
                .unwrap_or(1_000_000.0)
                .partial_cmp(&b.rank.unwrap_or(1_000_000.0))
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .then_with(|| ap.collect_date.cmp(&bp.collect_date))
}

struct LatestUsageGroup<'a> {
    slug: String,
    first: &'a CharacterRow,
    modes: Vec<(String, &'a CharacterRow)>,
}

fn latest_usage_view(
    rows: &[(&PhaseRow, &CharacterRow)],
    names: &NameResolver,
) -> (Vec<String>, Vec<Vec<String>>) {
    let mut latest_dates = std::collections::BTreeMap::<String, String>::new();
    for (phase, _) in rows {
        latest_dates
            .entry(phase.mode.clone())
            .and_modify(|date| {
                if phase.collect_date > *date {
                    *date = phase.collect_date.clone();
                }
            })
            .or_insert_with(|| phase.collect_date.clone());
    }
    let mut grouped = Vec::<LatestUsageGroup<'_>>::new();
    for &(phase, row) in rows {
        if latest_dates.get(&phase.mode) != Some(&phase.collect_date) {
            continue;
        }
        let index = grouped
            .iter()
            .position(|entry| entry.slug == row.character_slug)
            .unwrap_or_else(|| {
                let index = grouped.len();
                grouped.push(LatestUsageGroup {
                    slug: row.character_slug.clone(),
                    first: row,
                    modes: vec![],
                });
                index
            });
        let entry = &mut grouped[index];
        if let Some(existing) = entry.modes.iter_mut().find(|(mode, _)| mode == &phase.mode) {
            *existing = (phase.mode.clone(), row);
        } else {
            entry.modes.push((phase.mode.clone(), row));
        }
    }
    let mut records = grouped
        .into_iter()
        .map(|entry| {
            let maximum = entry
                .modes
                .iter()
                .map(|(_, row)| row.app_rate)
                .fold(0.0_f64, f64::max);
            (entry.slug, entry.first, entry.modes, maximum)
        })
        .collect::<Vec<_>>();
    records.sort_by(|a, b| b.3.partial_cmp(&a.3).unwrap_or(std::cmp::Ordering::Equal));
    if records.is_empty() {
        return (vec![], vec![]);
    }
    let mut headers = [
        "character_name_cn",
        "character_name_en",
        "character_slug",
        "role",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    for (_, _, modes, _) in &records {
        for (mode, _) in modes {
            for name in [format!("{mode}_app_rate"), format!("{mode}_avg_round")] {
                if !headers.contains(&name) {
                    headers.push(name);
                }
            }
        }
        if !headers.iter().any(|value| value == "max_app_rate") {
            headers.push("max_app_rate".into());
        }
    }
    let output = records
        .into_iter()
        .map(|(slug, first, modes, maximum)| {
            headers
                .iter()
                .map(|header| match header.as_str() {
                    "character_name_cn" => names.chinese(&slug),
                    "character_name_en" => resolved_english(names, &slug, &first.character_name_en),
                    "character_slug" => slug.clone(),
                    "role" => first.role.clone(),
                    "max_app_rate" => csv_float(Some(maximum)),
                    key if key.ends_with("_app_rate") => modes
                        .iter()
                        .find(|(mode, _)| key == format!("{mode}_app_rate"))
                        .map(|(_, row)| csv_float(Some(row.app_rate)))
                        .unwrap_or_default(),
                    key if key.ends_with("_avg_round") => modes
                        .iter()
                        .find(|(mode, _)| key == format!("{mode}_avg_round"))
                        .map(|(_, row)| csv_float(row.avg_round))
                        .unwrap_or_default(),
                    _ => String::new(),
                })
                .collect()
        })
        .collect();
    (headers, output)
}

fn top_teams_latest(rows: &[UnorderedTeam<'_>], names: &NameResolver) -> Vec<Vec<String>> {
    let mut latest = std::collections::BTreeMap::<String, [String; 3]>::new();
    for item in rows {
        let row = item.row;
        if row.rank.is_none() || !is_comprehensive_scope(&row.scope) {
            continue;
        }
        let observation = top_team_observation(item);
        latest
            .entry(row.mode.clone())
            .and_modify(|current| {
                if top_team_observation_cmp(&observation, current).is_gt() {
                    *current = observation.clone();
                }
            })
            .or_insert(observation);
    }

    let mut groups = std::collections::BTreeMap::<(String, [String; 4]), Vec<usize>>::new();
    for (index, item) in rows.iter().enumerate() {
        let row = item.row;
        if row.rank.is_none()
            || !is_comprehensive_scope(&row.scope)
            || latest.get(&row.mode) != Some(&top_team_observation(item))
        {
            continue;
        }
        let mut chars = row.chars.clone();
        chars.sort();
        groups
            .entry((row.mode.clone(), chars))
            .or_default()
            .push(index);
    }

    let mut selected = groups
        .into_values()
        .map(|indices| {
            let best = *indices
                .iter()
                .min_by(|left, right| {
                    let left = &rows[**left];
                    let right = &rows[**right];
                    team_best_cmp(left.row, right.row)
                        .then_with(|| left.signature.cmp(&right.signature))
                })
                .expect("top team group is non-empty");
            let duplicate_count = indices.iter().fold(0usize, |total, index| {
                total.saturating_add(rows[*index].count)
            });
            let source_kinds = indices
                .iter()
                .flat_map(|index| rows[*index].row.source_kind.split(';'))
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
                .collect::<std::collections::BTreeSet<_>>()
                .into_iter()
                .collect::<Vec<_>>()
                .join(";");
            (best, duplicate_count, source_kinds)
        })
        .collect::<Vec<_>>();
    selected.sort_by(|left, right| {
        let left_row = rows[left.0].row;
        let right_row = rows[right.0].row;
        team_best_cmp(left_row, right_row)
            .then_with(|| rows[left.0].signature.cmp(&rows[right.0].signature))
    });
    let mut counts = std::collections::BTreeMap::<String, usize>::new();
    selected
        .into_iter()
        .filter(|(index, _, _)| {
            let item = &rows[*index];
            let row = item.row;
            let count = counts.entry(row.mode.clone()).or_default();
            if *count >= 100 {
                false
            } else {
                *count += 1;
                true
            }
        })
        .map(|(index, duplicate_count, source_kinds)| {
            let item = &rows[index];
            let phase = item.phase;
            let row = item.row;
            vec![
                phase.mode_cn.clone(),
                row.mode.clone(),
                row.sub_mode_cn.clone(),
                row.sub_mode.clone(),
                row.phase_ver.clone(),
                csv_float(row.rank),
                row.chars
                    .iter()
                    .map(|slug| {
                        let chinese = names.chinese(slug);
                        if chinese.is_empty() {
                            slug.clone()
                        } else {
                            chinese
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(" / "),
                csv_float(row.app_rate),
                csv_float(row.avg_round),
                source_kinds,
                duplicate_count.to_string(),
                item.signature.clone(),
            ]
        })
        .collect()
}

fn top_team_observation(item: &UnorderedTeam<'_>) -> [String; 3] {
    [
        item.phase.collect_date.clone(),
        item.phase.snapshot_id.clone(),
        item.row.phase_ver.clone(),
    ]
}

fn top_team_observation_cmp(left: &[String; 3], right: &[String; 3]) -> std::cmp::Ordering {
    left[0]
        .cmp(&right[0])
        .then_with(|| natural_version_cmp(&left[1], &right[1]))
        .then_with(|| natural_version_cmp(&left[2], &right[2]))
}

fn is_comprehensive_scope(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().replace('_', "-").as_str(),
        "" | "all" | "top" | "all-bosses"
    )
}

fn source_priority(value: &str) -> usize {
    match value {
        "prydwen_page" => 0,
        "hf_comps" => 1,
        _ => 2,
    }
}

fn resolved_english(names: &NameResolver, slug: &str, fallback: &str) -> String {
    if fallback.is_empty() {
        names.english(slug, fallback)
    } else {
        fallback.to_owned()
    }
}

fn team_values(phase: &PhaseRow, row: &TeamRow, names: &NameResolver) -> Vec<String> {
    vec![
        phase.snapshot_id.clone(),
        phase.collect_date.clone(),
        row.mode.clone(),
        phase.mode_cn.clone(),
        row.sub_mode.clone(),
        row.sub_mode_cn.clone(),
        row.phase_ver.clone(),
        phase.phase_name.clone(),
        row.scope.clone(),
        csv_float(row.rank),
        row.comp_name.clone(),
        row.chars[0].clone(),
        row.chars[1].clone(),
        row.chars[2].clone(),
        row.chars[3].clone(),
        names.chinese(&row.chars[0]),
        names.chinese(&row.chars[1]),
        names.chinese(&row.chars[2]),
        names.chinese(&row.chars[3]),
        csv_float(row.app_rate),
        csv_float(row.avg_round),
        csv_float(row.whale_count),
        csv_float(row.app_flat),
        csv_float(row.uses),
        row.source_kind.clone(),
        row.source_file.clone(),
        row.source_url.clone(),
        row.raw_index.to_string(),
        row.raw_json.clone(),
    ]
}

fn character_values(phase: &PhaseRow, row: &CharacterRow, names: &NameResolver) -> Vec<String> {
    vec![
        phase.snapshot_id.clone(),
        phase.collect_date.clone(),
        phase.mode.clone(),
        phase.mode_cn.clone(),
        if phase.mode == "aa" {
            "all_bosses".into()
        } else {
            "all".into()
        },
        if phase.mode == "aa" {
            "全 Boss / 未拆分".into()
        } else {
            "全部".into()
        },
        phase.phase_ver.clone(),
        phase.phase_name.clone(),
        phase.start_date.clone(),
        phase.end_date.clone(),
        row.character_slug.clone(),
        resolved_english(names, &row.character_slug, &row.character_name_en),
        names.chinese(&row.character_slug),
        row.role.clone(),
        row.rarity.clone(),
        csv_float(Some(row.app_rate)),
        csv_float(row.app_rate_e0),
        csv_float(row.avg_round),
        csv_float(row.std_dev_round),
        csv_float(row.q1_round),
        csv_float(row.cons_avg),
        csv_float(row.sample),
        csv_float(row.sample_app_flat),
        row.source_kind.clone(),
        row.source_file.clone(),
        row.source_url.clone(),
        row.quality_flag.clone(),
    ]
}

fn tier_values(row: &TierRow, names: &NameResolver) -> Vec<String> {
    vec![
        row.tier_snapshot_id.clone(),
        row.fetched_at.clone(),
        row.tier_updated_at.clone(),
        row.tier_updated_date.clone(),
        row.tier_mode.clone(),
        row.tier_mode_cn.clone(),
        row.character_slug.clone(),
        resolved_english(names, &row.character_slug, &row.character_name_en),
        {
            let chinese = names.chinese(&row.character_slug);
            if chinese.is_empty() {
                row.character_name_cn.clone()
            } else {
                chinese
            }
        },
        row.prydwen_category.clone(),
        row.prydwen_role.clone(),
        row.role_group.clone(),
        row.role_group_cn.clone(),
        row.tier.clone(),
        row.rating
            .map(|value| value.to_string())
            .unwrap_or_default(),
        python_csv_value(&row.special_rating),
        python_csv_value(&row.tags),
        python_csv_value(&row.marks),
        python_csv_value(&row.is_new),
        row.default_role.clone(),
        row.element.clone(),
        row.path.clone(),
        row.rarity.clone(),
        row.icon_url.clone(),
        row.source_url.clone(),
    ]
}

fn changelog_values(row: &ChangelogRow) -> Vec<String> {
    vec![
        row.changelog_date.clone(),
        row.source_url.clone(),
        row.character_slugs.clone(),
        row.text.clone(),
    ]
}

fn chart_display_path(dataset: &HsrExportDataset, filename: &str) -> String {
    let relative = PathBuf::from("charts")
        .join("prydwen_tier_usage")
        .join(filename);
    dataset
        .display_output_root
        .as_ref()
        .map(|root| root.join(&relative))
        .unwrap_or(relative)
        .to_string_lossy()
        .into_owned()
}

fn trend_values(row: &TrendRow, names: &NameResolver) -> Vec<String> {
    vec![
        row.tier_snapshot_id.clone(),
        row.tier_updated_date.clone(),
        row.tier_mode.clone(),
        row.tier_mode_cn.clone(),
        row.character_slug.clone(),
        resolved_english(names, &row.character_slug, &row.character_name_en),
        {
            let chinese = names.chinese(&row.character_slug);
            if chinese.is_empty() {
                row.character_name_cn.clone()
            } else {
                chinese
            }
        },
        row.prydwen_role.clone(),
        row.role_group.clone(),
        row.role_group_cn.clone(),
        row.tier.clone(),
        row.rating
            .map(|value| value.to_string())
            .unwrap_or_default(),
        python_csv_value(&row.tags),
        python_csv_value(&row.marks),
        row.collect_date.clone(),
        row.phase_ver.clone(),
        row.phase_name.clone(),
        csv_float(Some(row.app_rate)),
        csv_float(row.avg_round),
        row.quality_flag.clone(),
        row.icon_url.clone(),
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
            rating: Some(1),
            source_url: "fixture://tier".into(),
            ..Default::default()
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
        assert_eq!(bundle.manifest().len(), 20);
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
        assert_eq!(actual_manifest.as_array().unwrap().len(), 19);
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

    #[test]
    fn dataset_keeps_multiple_slices_and_derives_globally() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let first = make_phase_row(
            "4.3.2",
            &fixture["config"],
            "moc",
            "4.3.2/",
            true,
            true,
            false,
            "2026-06-25",
        );
        let mut second = first.clone();
        second.snapshot_id = "4.3.3".into();
        second.collect_date = "2026-07-01".into();
        second.mode = "pf".into();
        second.mode_cn = "虚构叙事".into();
        let first_chars = parse_builds_character_rows(&fixture["builds"], "moc");
        let mut second_chars = first_chars.clone();
        second_chars[0].character_slug = "march-7th".into();
        second_chars[0].character_name_en = "March 7th".into();
        let first_teams = parse_team_rows(
            &fixture["teams"],
            "moc",
            "4.2.1",
            "stage_1_combined.json",
            Some(2),
        );
        let mut second_teams = first_teams.clone();
        second_teams[0].mode = "pf".into();
        let dataset = HsrExportDataset {
            slices: vec![
                HsrExportSlice {
                    phase: first,
                    characters: first_chars,
                    teams: first_teams,
                    tiers: vec![],
                },
                HsrExportSlice {
                    phase: second,
                    characters: second_chars,
                    teams: second_teams,
                    tiers: vec![],
                },
            ],
            histograph_slices: vec![HsrHistographSlice {
                phase: make_phase_row(
                    "4.3.2",
                    &fixture["config"],
                    "moc",
                    "4.3.2/",
                    true,
                    true,
                    true,
                    "2026-06-25",
                ),
                rows: crate::hsr::parse_histograph_rows(
                    &fixture["histograph"],
                    "moc",
                    "4.3.2/histograph.json",
                ),
            }],
            ..Default::default()
        };
        let bundle = build_dataset_export(&dataset).unwrap();
        let phases = std::str::from_utf8(bundle.get("phase_index.csv").unwrap()).unwrap();
        let characters =
            std::str::from_utf8(bundle.get("character_usage_phase_latest.csv").unwrap()).unwrap();
        let teams =
            std::str::from_utf8(bundle.get("team_rank_dedup_ordered.csv").unwrap()).unwrap();
        assert!(phases.contains("4.3.2") && phases.contains("4.3.3"));
        assert!(characters.contains("topaz-and-numby") && characters.contains("march-7th"));
        assert!(teams.contains("moc|") && teams.contains("pf|"));
        let latest = std::str::from_utf8(bundle.get("latest_usage_cn.csv").unwrap()).unwrap();
        assert!(latest
            .lines()
            .next()
            .unwrap()
            .contains("moc_app_rate,moc_avg_round,max_app_rate,pf_app_rate,pf_avg_round"));
        for name in ["histograph_usage_long.csv", "top_teams_latest.csv"] {
            let raw = bundle.get(name).unwrap();
            assert!(raw.starts_with(&[0xef, 0xbb, 0xbf]) && raw.ends_with(b"\r\n"));
        }
        let histogram =
            std::str::from_utf8(bundle.get("histograph_usage_long.csv").unwrap()).unwrap();
        assert!(histogram.contains("moc,混沌回忆,topaz-and-numby,Topaz and Numby,,8.25,4.3.2/histograph.json,trend auxiliary; not a full character usage table"));
        for name in [
            "histograph_usage_long.csv",
            "latest_usage_cn.csv",
            "top_teams_latest.csv",
        ] {
            assert!(bundle.manifest().iter().any(|entry| entry.path == name));
        }
    }

    #[test]
    fn raw_ordered_and_unordered_team_sets_do_not_cross_wires() {
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
            true,
            false,
            "2026-06-25",
        );
        let base = TeamRow {
            mode: "moc".into(),
            sub_mode: "all".into(),
            sub_mode_cn: "全部".into(),
            phase_ver: "4.2.1".into(),
            scope: "all".into(),
            raw_index: 1,
            chars: ["a".into(), "b".into(), "c".into(), "d".into()],
            raw_json: "{}".into(),
            rank: Some(1.0),
            comp_name: String::new(),
            app_rate: Some(10.0),
            avg_round: Some(3.0),
            whale_count: None,
            app_flat: None,
            uses: None,
            source_kind: "fixture".into(),
            source_file: "teams.json".into(),
            source_url: "fixture://teams".into(),
        };
        let mut duplicate = base.clone();
        duplicate.raw_index = 2;
        let mut reordered = base.clone();
        reordered.raw_index = 3;
        reordered.chars.swap(0, 1);
        reordered.source_kind = "prydwen_page".into();
        reordered.source_file = "prydwen.html".into();
        reordered.rank = Some(9.0);
        let bundle = build_dataset_export(&HsrExportDataset {
            slices: vec![HsrExportSlice {
                phase,
                characters: vec![],
                teams: vec![base, duplicate, reordered],
                tiers: vec![],
            }],
            histograph_slices: vec![],
            ..Default::default()
        })
        .unwrap();
        assert_eq!(csv_data_rows(&bundle, "team_rank_raw.csv"), 3);
        assert_eq!(csv_data_rows(&bundle, "team_rank_dedup_ordered.csv"), 2);
        assert_eq!(csv_data_rows(&bundle, "team_rank_dedup_unordered.csv"), 1);
        assert_eq!(csv_data_rows(&bundle, "top_teams_latest.csv"), 1);
        let ordered = csv_records(&bundle, "team_rank_dedup_ordered.csv");
        assert_eq!(
            ordered
                .iter()
                .map(|row| row["duplicate_count"].parse::<usize>().unwrap())
                .sum::<usize>(),
            3
        );
        assert_eq!(
            ordered
                .iter()
                .map(|row| row["merged_source_files"].clone())
                .collect::<std::collections::BTreeSet<_>>(),
            ["prydwen.html".to_owned(), "teams.json".to_owned()]
                .into_iter()
                .collect()
        );
        let unordered = csv_records(&bundle, "team_rank_dedup_unordered.csv");
        assert_eq!(unordered[0]["duplicate_count"], "3");
        assert_eq!(unordered[0]["merged_source_files"], "prydwen.html");
        assert_eq!(unordered[0]["source_kind"], "prydwen_page");
        assert_eq!(unordered[0]["rank"], "9.0");
        assert!(
            unordered[0]["ordered_signature_examples"].contains("a>b>c>d")
                && unordered[0]["ordered_signature_examples"].contains("b>a>c>d")
        );
        let top = csv_records(&bundle, "top_teams_latest.csv");
        assert_eq!(top[0]["duplicate_count"], "3");
        assert_eq!(
            top[0]["unordered_signature"],
            unordered[0]["unordered_signature"]
        );
        let names = csv_records(&bundle, "name_map.csv");
        assert_eq!(
            names
                .iter()
                .map(|row| row["character_slug"].as_str())
                .collect::<std::collections::BTreeSet<_>>(),
            ["a", "b", "c", "d"].into_iter().collect()
        );
        assert_eq!(
            csv_data_rows(&bundle, "name_map_unresolved.csv"),
            names.len()
        );
        let report = std::str::from_utf8(bundle.get("export_report.md").unwrap()).unwrap();
        assert!(
            report.contains("队伍有序去重后行数: 2") && report.contains("队伍无序去重后行数: 1")
        );
    }

    #[test]
    fn team_dedup_keeps_same_phase_composition_in_distinct_snapshots() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let old_phase = make_phase_row(
            "4.3.9",
            &fixture["config"],
            "moc",
            "4.3.9/",
            true,
            true,
            false,
            "2026-06-25",
        );
        let mut new_phase = old_phase.clone();
        new_phase.snapshot_id = "4.3.10".into();
        new_phase.source_path = "4.3.10/".into();

        let old_team = TeamRow {
            mode: "moc".into(),
            sub_mode: "all".into(),
            sub_mode_cn: "全部".into(),
            phase_ver: "4.2.1".into(),
            scope: "all".into(),
            raw_index: 1,
            chars: ["a".into(), "b".into(), "c".into(), "d".into()],
            raw_json: "{}".into(),
            rank: Some(1.0),
            comp_name: String::new(),
            app_rate: Some(20.0),
            avg_round: Some(2.0),
            whale_count: None,
            app_flat: None,
            uses: None,
            source_kind: "hf_comps".into(),
            source_file: "4.3.9/moc/comps/top_combined.json".into(),
            source_url: "fixture://old".into(),
        };
        let mut new_team = old_team.clone();
        new_team.rank = Some(999.0);
        new_team.app_rate = Some(1.0);
        new_team.avg_round = Some(9.0);
        new_team.source_file = "4.3.10/moc/comps/top_combined.json".into();
        new_team.source_url = "fixture://new".into();

        let bundle = build_dataset_export(&HsrExportDataset {
            slices: vec![
                HsrExportSlice {
                    phase: old_phase,
                    characters: vec![],
                    teams: vec![old_team],
                    tiers: vec![],
                },
                HsrExportSlice {
                    phase: new_phase,
                    characters: vec![],
                    teams: vec![new_team],
                    tiers: vec![],
                },
            ],
            ..Default::default()
        })
        .unwrap();

        for table in [
            "team_rank_dedup_ordered.csv",
            "team_rank_dedup_unordered.csv",
        ] {
            let rows = csv_records(&bundle, table);
            assert_eq!(rows.len(), 2, "{table} must preserve both observations");
            assert_eq!(
                rows.iter()
                    .map(|row| row["snapshot_id"].as_str())
                    .collect::<std::collections::BTreeSet<_>>(),
                ["4.3.9", "4.3.10"].into_iter().collect()
            );
            assert!(rows.iter().all(|row| row["duplicate_count"] == "1"));
        }

        let unordered = csv_records(&bundle, "team_rank_dedup_unordered.csv");
        for snapshot in ["4.3.9", "4.3.10"] {
            let date = "2026-06-25";
            let expected = format!("{snapshot}|{date}|moc|all|all|4.2.1|Example Phase|a>b>c>d");
            assert!(unordered
                .iter()
                .any(|row| row["unordered_signature"] == expected));
        }

        let latest = csv_records(&bundle, "top_teams_latest.csv");
        assert_eq!(latest.len(), 1);
        assert_eq!(latest[0]["rank"], "999.0");
        assert_eq!(
            latest[0]["unordered_signature"],
            "4.3.10|2026-06-25|moc|all|all|4.2.1|Example Phase|a>b>c>d"
        );
    }

    #[test]
    fn team_dedup_keeps_same_snapshot_composition_in_distinct_scopes() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let mut phase = make_phase_row(
            "4.3.2",
            &fixture["config"],
            "aa",
            "4.3.2/",
            true,
            true,
            false,
            "2026-06-25",
        );
        phase.phase_name = "Example Phase".into();
        let first = TeamRow {
            mode: "aa".into(),
            sub_mode: "all_bosses".into(),
            sub_mode_cn: "全部首领".into(),
            phase_ver: "4.2.1".into(),
            scope: "1-1".into(),
            raw_index: 1,
            chars: ["a".into(), "b".into(), "c".into(), "d".into()],
            raw_json: "{}".into(),
            rank: Some(1.0),
            comp_name: String::new(),
            app_rate: Some(20.0),
            avg_round: None,
            whale_count: None,
            app_flat: None,
            uses: None,
            source_kind: "hf_comps".into(),
            source_file: "4.3.2/aa/comps/1-1.json".into(),
            source_url: "fixture://1-1".into(),
        };
        let mut second = first.clone();
        second.scope = "1-2".into();
        second.raw_index = 2;
        second.source_file = "4.3.2/aa/comps/1-2.json".into();
        second.source_url = "fixture://1-2".into();

        let bundle = build_dataset_export(&HsrExportDataset {
            slices: vec![HsrExportSlice {
                phase,
                characters: vec![],
                teams: vec![first, second],
                tiers: vec![],
            }],
            ..Default::default()
        })
        .unwrap();

        for (table, signature_column) in [
            ("team_rank_dedup_ordered.csv", "ordered_signature"),
            ("team_rank_dedup_unordered.csv", "unordered_signature"),
        ] {
            let rows = csv_records(&bundle, table);
            assert_eq!(rows.len(), 2, "{table} must preserve both scopes");
            assert_eq!(
                rows.iter()
                    .map(|row| row["scope"].as_str())
                    .collect::<std::collections::BTreeSet<_>>(),
                ["1-1", "1-2"].into_iter().collect()
            );
            for scope in ["1-1", "1-2"] {
                let expected =
                    format!("4.3.2|2026-06-25|aa|all_bosses|{scope}|4.2.1|Example Phase|a>b>c>d");
                assert!(rows.iter().any(|row| row[signature_column] == expected));
            }
        }
    }

    #[test]
    fn top_teams_merge_comprehensive_sources_and_exclude_concrete_scopes() {
        fn copies(row: &TeamRow, count: usize) -> Vec<TeamRow> {
            (0..count)
                .map(|offset| {
                    let mut copy = row.clone();
                    copy.raw_index = offset + 1;
                    copy
                })
                .collect()
        }

        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let mut old_moc = make_phase_row(
            "4.3.9",
            &fixture["config"],
            "moc",
            "4.3.9/",
            true,
            true,
            false,
            "2026-07-01",
        );
        old_moc.phase_ver = "4.3.1".into();
        old_moc.phase_name = "Duty Action".into();
        let mut current_moc = old_moc.clone();
        current_moc.snapshot_id = "4.3.10".into();
        current_moc.source_path = "4.3.10/".into();
        current_moc.phase_name = "Zulu metadata spelling".into();
        let mut current_moc_prydwen = current_moc.clone();
        current_moc_prydwen.phase_name = "Duty Action".into();
        let mut current_aa = current_moc.clone();
        current_aa.mode = "aa".into();
        current_aa.mode_cn = "异相仲裁".into();
        current_aa.phase_name = "The Humming Laughter".into();

        let team = |mode: &str, scope: &str, source_kind: &str, rank: f64| TeamRow {
            mode: mode.into(),
            sub_mode: if mode == "aa" {
                "all_bosses".into()
            } else {
                "all".into()
            },
            sub_mode_cn: "全部".into(),
            phase_ver: "4.3.1".into(),
            scope: scope.into(),
            raw_index: 1,
            chars: ["a".into(), "b".into(), "c".into(), "d".into()],
            raw_json: "{}".into(),
            rank: Some(rank),
            comp_name: String::new(),
            app_rate: Some(10.0),
            avg_round: Some(3.0),
            whale_count: None,
            app_flat: None,
            uses: None,
            source_kind: source_kind.into(),
            source_file: format!("{source_kind}/{scope}.json"),
            source_url: format!("fixture://{source_kind}/{scope}"),
        };

        let old_rows = copies(&team("moc", "all", "prydwen_page", 1.0), 7);
        let mut moc_rows = copies(&team("moc", "top", "hf_comps", 1.0), 2);
        moc_rows.extend(copies(&team("moc", "12-1", "hf_comps", 1.0), 50));
        let mut moc_prydwen_rows = copies(&team("moc", "all", "prydwen_page", 9.0), 3);
        moc_prydwen_rows.extend(copies(&team("moc", "1", "prydwen_page", 1.0), 60));
        let mut aa_rows = copies(&team("aa", "all-bosses", "hf_comps", 1.0), 4);
        aa_rows.extend(copies(&team("aa", "all_bosses", "prydwen_page", 8.0), 5));
        aa_rows.extend(copies(&team("aa", "1-1", "hf_comps", 1.0), 80));

        let bundle = build_dataset_export(&HsrExportDataset {
            slices: vec![
                HsrExportSlice {
                    phase: old_moc,
                    characters: vec![],
                    teams: old_rows,
                    tiers: vec![],
                },
                HsrExportSlice {
                    phase: current_moc,
                    characters: vec![],
                    teams: moc_rows,
                    tiers: vec![],
                },
                HsrExportSlice {
                    phase: current_moc_prydwen,
                    characters: vec![],
                    teams: moc_prydwen_rows,
                    tiers: vec![],
                },
                HsrExportSlice {
                    phase: current_aa,
                    characters: vec![],
                    teams: aa_rows,
                    tiers: vec![],
                },
            ],
            ..Default::default()
        })
        .unwrap();

        let top = csv_records(&bundle, "top_teams_latest.csv");
        assert_eq!(top.len(), 2);
        let moc = top.iter().find(|row| row["mode"] == "moc").unwrap();
        assert_eq!(moc["duplicate_count"], "5");
        assert_eq!(moc["source_kind"], "hf_comps;prydwen_page");
        assert_eq!(moc["rank"], "9.0");
        assert_eq!(
            moc["unordered_signature"],
            "4.3.10|2026-07-01|moc|all|all|4.3.1|Duty Action|a>b>c>d"
        );
        let aa = top.iter().find(|row| row["mode"] == "aa").unwrap();
        assert_eq!(aa["duplicate_count"], "9");
        assert_eq!(aa["source_kind"], "hf_comps;prydwen_page");
        assert_eq!(
            aa["unordered_signature"],
            "4.3.10|2026-07-01|aa|all_bosses|all_bosses|4.3.1|The Humming Laughter|a>b>c>d"
        );
    }

    #[test]
    fn latest_usage_uses_newest_collect_date_within_mode() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let old = make_phase_row(
            "4.3.1",
            &fixture["config"],
            "moc",
            "old",
            true,
            false,
            false,
            "2026-06-01",
        );
        let mut new = old.clone();
        new.snapshot_id = "4.3.2".into();
        new.collect_date = "2026-07-01".into();
        let old_row = parse_builds_character_rows(&fixture["builds"], "moc").remove(0);
        let mut new_row = old_row.clone();
        new_row.app_rate = 99.0;
        let names = NameResolver::new(&[]);
        let (headers, rows) = latest_usage_view(&[(&old, &old_row), (&new, &new_row)], &names);
        let rate = headers
            .iter()
            .position(|value| value == "moc_app_rate")
            .unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0][rate], "99.0");
    }

    fn csv_data_rows(bundle: &ArtifactBundle, name: &str) -> usize {
        std::str::from_utf8(bundle.get(name).unwrap())
            .unwrap()
            .lines()
            .count()
            - 1
    }

    fn csv_records(
        bundle: &ArtifactBundle,
        name: &str,
    ) -> Vec<std::collections::HashMap<String, String>> {
        let mut reader = csv::Reader::from_reader(bundle.get(name).unwrap());
        let headers = reader
            .headers()
            .unwrap()
            .iter()
            .map(|value| value.trim_start_matches('\u{feff}').to_owned())
            .collect::<Vec<_>>();
        reader
            .records()
            .map(|record| {
                headers
                    .iter()
                    .cloned()
                    .zip(record.unwrap().iter().map(str::to_owned))
                    .collect()
            })
            .collect()
    }

    fn python_csv_bytes(source: &[u8]) -> Vec<u8> {
        let text = std::str::from_utf8(source).unwrap().replace("\r\n", "\n");
        let mut output = vec![0xEF, 0xBB, 0xBF];
        output.extend_from_slice(text.replace('\n', "\r\n").as_bytes());
        output
    }
}
