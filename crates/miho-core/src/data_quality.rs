use std::collections::{BTreeMap, BTreeSet};

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

use crate::{
    contract::{Game, GameMode},
    output::ArtifactBundle,
    visualizer::read_csv_rows,
    MihoError, Result,
};

pub const DATA_QUALITY_SCHEMA_V1: &str = "miho-data-quality-v1";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FreshnessV1 {
    pub status: String,
    pub sample_date: String,
    pub start_date: String,
    pub end_date: String,
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ModeDataQualityV1 {
    pub row_count: usize,
    pub valid_rank_count: usize,
    pub valid_performance_count: usize,
    pub sentinel_count: usize,
    pub sentinel_rate: f64,
    pub source_coverage: Vec<String>,
    pub freshness: FreshnessV1,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DataQualityReportV1 {
    pub schema_version: String,
    pub game: String,
    pub status: String,
    pub warnings: Vec<String>,
    pub alias_conflict_count: usize,
    pub modes: BTreeMap<String, ModeDataQualityV1>,
}

pub fn attach_data_quality_v1(
    bundle: &mut ArtifactBundle,
    game: Game,
    required_modes: &[GameMode],
    local_date: NaiveDate,
    previous: Option<&[u8]>,
) -> Result<DataQualityReportV1> {
    let teams = read_csv_rows(bundle, "team_rank_dedup_unordered.csv")?;
    let phases = read_csv_rows(bundle, "phase_index.csv")?;
    let names = read_csv_rows(bundle, "name_map.csv")?;
    validate_dataset_identity(game, &teams)?;
    let alias_conflicts = alias_conflicts(&names);
    if !alias_conflicts.is_empty() {
        return Err(MihoError::Visualizer(format!(
            "data quality alias conflict: {}",
            alias_conflicts.join(", ")
        )));
    }

    let mut modes = BTreeMap::new();
    for mode in required_modes {
        if mode.game() != game {
            return Err(MihoError::Visualizer(format!(
                "data quality mode {} does not belong to {}",
                mode.code(),
                game.code()
            )));
        }
        let rows = teams
            .iter()
            .filter(|row| value(row, "mode") == mode.code())
            .collect::<Vec<_>>();
        if rows.is_empty() {
            return Err(MihoError::Visualizer(format!(
                "data quality required mode {} is empty",
                mode.code()
            )));
        }
        let valid_rank_count = rows
            .iter()
            .filter(|row| positive(value(row, "rank")).is_some())
            .count();
        let performance_key = if game == Game::Hsr {
            "avg_round"
        } else {
            "avg_score"
        };
        let mut valid_performance_count = 0;
        let mut sentinel_count = 0;
        let mut sources = BTreeSet::new();
        for row in &rows {
            let performance = number(value(row, performance_key));
            if performance.is_some_and(|value| performance_sentinel(game, value)) {
                sentinel_count += 1;
            } else if performance.is_some_and(|value| value > 0.0) {
                valid_performance_count += 1;
            }
            let source = value(row, "source_kind").trim();
            if !source.is_empty() {
                sources.insert(source.to_owned());
            }
        }
        modes.insert(
            mode.code().to_owned(),
            ModeDataQualityV1 {
                row_count: rows.len(),
                valid_rank_count,
                valid_performance_count,
                sentinel_count,
                sentinel_rate: ratio(sentinel_count, rows.len()),
                source_coverage: sources.into_iter().collect(),
                freshness: mode_freshness(&phases, mode.code(), local_date),
            },
        );
    }

    let mut report = DataQualityReportV1 {
        schema_version: DATA_QUALITY_SCHEMA_V1.to_owned(),
        game: game.code().to_owned(),
        status: "ok".to_owned(),
        warnings: Vec::new(),
        alias_conflict_count: 0,
        modes,
    };
    if let Some(previous) = previous.and_then(parse_previous) {
        compare_previous(&mut report, &previous);
    }
    for (mode, quality) in &report.modes {
        if quality.freshness.status == "stale" {
            report
                .warnings
                .push(format!("{mode}: phase is stale and recommendations use historical samples"));
        }
    }
    report.warnings.sort();
    report.warnings.dedup();
    if !report.warnings.is_empty() {
        report.status = "warning".to_owned();
    }
    bundle.add_json("data_quality.json", &report)?;
    Ok(report)
}

fn parse_previous(bytes: &[u8]) -> Option<DataQualityReportV1> {
    serde_json::from_slice::<DataQualityReportV1>(bytes)
        .ok()
        .filter(|report| report.schema_version == DATA_QUALITY_SCHEMA_V1)
}

fn compare_previous(current: &mut DataQualityReportV1, previous: &DataQualityReportV1) {
    if current.game != previous.game {
        current
            .warnings
            .push("previous data-quality identity differs from the current game".to_owned());
        return;
    }
    for (mode, quality) in &current.modes {
        let Some(old) = previous.modes.get(mode) else {
            continue;
        };
        if old.valid_performance_count > 0
            && quality.valid_performance_count * 10 <= old.valid_performance_count * 7
        {
            current.warnings.push(format!(
                "{mode}: valid performance count dropped by at least 30% ({} -> {})",
                old.valid_performance_count, quality.valid_performance_count
            ));
        }
        if quality.sentinel_rate - old.sentinel_rate >= 0.20 - f64::EPSILON {
            current.warnings.push(format!(
                "{mode}: sentinel rate increased by at least 20 percentage points ({:.1}% -> {:.1}%)",
                old.sentinel_rate * 100.0,
                quality.sentinel_rate * 100.0
            ));
        }
    }
}

fn validate_dataset_identity(
    game: Game,
    rows: &[BTreeMap<String, String>],
) -> Result<()> {
    let allowed = match game {
        Game::Hsr => ["moc", "pf", "as", "aa"].as_slice(),
        Game::Zzz => ["sd", "da"].as_slice(),
    };
    if let Some(mode) = rows
        .iter()
        .map(|row| value(row, "mode"))
        .find(|mode| !mode.is_empty() && !allowed.contains(mode))
    {
        return Err(MihoError::Visualizer(format!(
            "data quality dataset identity conflict: mode {mode:?} is not valid for {}",
            game.code()
        )));
    }
    Ok(())
}

fn alias_conflicts(rows: &[BTreeMap<String, String>]) -> Vec<String> {
    let mut owners = BTreeMap::<String, String>::new();
    let mut conflicts = BTreeSet::new();
    for row in rows {
        let owner = value(row, "character_slug").trim();
        if owner.is_empty() {
            continue;
        }
        for alias in std::iter::once(owner).chain(
            value(row, "aliases")
                .split(';')
                .map(str::trim)
                .filter(|alias| !alias.is_empty()),
        ) {
            let alias = alias.to_ascii_lowercase();
            if let Some(existing) = owners.get(&alias) {
                if existing != owner {
                    conflicts.insert(alias);
                }
            } else {
                owners.insert(alias, owner.to_owned());
            }
        }
    }
    conflicts.into_iter().collect()
}

fn mode_freshness(
    phases: &[BTreeMap<String, String>],
    mode: &str,
    local_date: NaiveDate,
) -> FreshnessV1 {
    let latest = phases
        .iter()
        .filter(|row| value(row, "mode") == mode)
        .max_by(|left, right| {
            value(left, "collect_date")
                .cmp(value(right, "collect_date"))
                .then_with(|| value(left, "phase_ver").cmp(value(right, "phase_ver")))
        });
    let Some(row) = latest else {
        return FreshnessV1 {
            status: "unknown".to_owned(),
            sample_date: String::new(),
            start_date: String::new(),
            end_date: String::new(),
            source: String::new(),
        };
    };
    let start = parse_date(value(row, "start_date"));
    let end = parse_date(value(row, "end_date"));
    let status = if start.is_some_and(|date| date > local_date) {
        "future"
    } else if end.is_some_and(|date| date < local_date) {
        "stale"
    } else if start.is_some() || end.is_some() {
        "active"
    } else {
        "unknown"
    };
    FreshnessV1 {
        status: status.to_owned(),
        sample_date: value(row, "collect_date").to_owned(),
        start_date: value(row, "start_date").to_owned(),
        end_date: value(row, "end_date").to_owned(),
        source: [value(row, "source"), value(row, "source_path")]
            .into_iter()
            .find(|value| !value.trim().is_empty())
            .unwrap_or("")
            .to_owned(),
    }
}

fn parse_date(value: &str) -> Option<NaiveDate> {
    let value = value.trim();
    NaiveDate::parse_from_str(value.get(..10).unwrap_or(value), "%Y-%m-%d").ok()
}

fn value<'a>(row: &'a BTreeMap<String, String>, key: &str) -> &'a str {
    row.get(key).map(String::as_str).unwrap_or("")
}

fn number(value: &str) -> Option<f64> {
    let parsed = value.trim().parse::<f64>().ok()?;
    parsed.is_finite().then_some(parsed)
}

fn positive(value: &str) -> Option<f64> {
    number(value).filter(|value| *value > 0.0)
}

fn performance_sentinel(game: Game, value: f64) -> bool {
    value == 0.0 || (game == Game::Hsr && (value - 99.99).abs() <= 0.001)
}

fn ratio(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bundle(rows: &[&[&str]]) -> ArtifactBundle {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_csv(
                "team_rank_dedup_unordered.csv",
                &["mode", "rank", "avg_round", "source_kind"],
                rows.iter().copied(),
            )
            .unwrap();
        bundle
            .add_csv(
                "phase_index.csv",
                &["mode", "collect_date", "phase_ver", "start_date", "end_date", "source", "source_path"],
                [["as", "2026-07-01", "4.3", "2026-07-01", "2026-07-30", "fixture", ""]],
            )
            .unwrap();
        bundle
            .add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>(
                "name_map.csv",
                &["character_slug", "aliases"],
                vec![],
            )
            .unwrap();
        bundle
    }

    #[test]
    fn reports_mode_metrics_and_active_freshness() {
        let mut bundle = bundle(&[
            &["as", "1", "3500", "fixture"],
            &["as", "0", "99.99", "fixture"],
        ]);
        let report = attach_data_quality_v1(
            &mut bundle,
            Game::Hsr,
            &[GameMode::HsrAs],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            None,
        )
        .unwrap();
        let mode = &report.modes["as"];
        assert_eq!(mode.row_count, 2);
        assert_eq!(mode.valid_rank_count, 1);
        assert_eq!(mode.valid_performance_count, 1);
        assert_eq!(mode.sentinel_count, 1);
        assert_eq!(mode.freshness.status, "active");
        assert!(bundle.get("data_quality.json").is_some());
    }

    #[test]
    fn missing_required_mode_and_alias_conflict_fail_closed() {
        let mut missing = bundle(&[&["as", "1", "3500", "fixture"]]);
        assert!(attach_data_quality_v1(
            &mut missing,
            Game::Hsr,
            &[GameMode::HsrPf],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            None,
        )
        .is_err());

        let mut conflict = bundle(&[&["as", "1", "3500", "fixture"]]);
        conflict
            .add_csv(
                "name_map.csv",
                &["character_slug", "aliases"],
                [["one", "shared"], ["two", "shared"]],
            )
            .unwrap();
        assert!(attach_data_quality_v1(
            &mut conflict,
            Game::Hsr,
            &[GameMode::HsrAs],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            None,
        )
        .is_err());
    }
}
