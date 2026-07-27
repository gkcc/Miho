use std::collections::{BTreeMap, BTreeSet};

use chrono::{DateTime, NaiveDate};
use serde::{Deserialize, Serialize};

use crate::{
    contract::{Game, GameMode},
    output::ArtifactBundle,
    visualizer::read_csv_rows,
    MihoError, Result,
};

pub const DATA_QUALITY_SCHEMA_V1: &str = "miho-data-quality-v1";
pub const ENDGAME_SAMPLE_STALE_AFTER_DAYS: i64 = 15;

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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub change_from_previous: Option<ModeDataQualityChangeV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ModeDataQualityChangeV1 {
    pub row_count_delta: i64,
    pub valid_rank_count_delta: i64,
    pub valid_performance_count_delta: i64,
    pub sentinel_rate_delta: f64,
    pub sources_added: Vec<String>,
    pub sources_removed: Vec<String>,
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

/// Validate the identity and generation-relative freshness semantics of one
/// data-quality report.
///
/// Known freshness states require strict dates. Every parseable sample must be
/// no newer than the generation date. `unknown` deliberately remains
/// compatible with upstream date values that cannot be parsed, but any valid
/// boundary must still agree with the reported state.
pub fn validate_data_quality_report_v1(
    report: &DataQualityReportV1,
    expected_game: Game,
    required_modes: &[GameMode],
    generation_local_date: NaiveDate,
) -> Result<()> {
    if report.schema_version != DATA_QUALITY_SCHEMA_V1 {
        return Err(data_quality_freshness_error(
            "the report schema version is invalid",
        ));
    }
    if report.game != expected_game.code() {
        return Err(data_quality_freshness_error(
            "the report game identity is invalid",
        ));
    }
    if !matches!(report.status.as_str(), "ok" | "warning") {
        return Err(data_quality_freshness_error("the report status is invalid"));
    }
    if required_modes.is_empty() {
        return Err(data_quality_freshness_error(
            "required modes must not be empty",
        ));
    }

    let mut expected_mode_codes = BTreeSet::new();
    for mode in required_modes {
        if mode.game() != expected_game {
            return Err(data_quality_freshness_error(
                "a required mode belongs to another game",
            ));
        }
        if !expected_mode_codes.insert(mode.code()) {
            return Err(data_quality_freshness_error(
                "required modes must not contain duplicates",
            ));
        }
    }
    let actual_mode_codes = report
        .modes
        .keys()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if actual_mode_codes != expected_mode_codes {
        return Err(data_quality_freshness_error(
            "report modes do not match the required modes",
        ));
    }

    for quality in report.modes.values() {
        validate_mode_freshness_v1(&quality.freshness, generation_local_date)?;
    }
    Ok(())
}

fn validate_mode_freshness_v1(
    freshness: &FreshnessV1,
    generation_local_date: NaiveDate,
) -> Result<()> {
    let known = matches!(freshness.status.as_str(), "active" | "stale" | "future");
    if !known && freshness.status != "unknown" {
        return Err(data_quality_freshness_error(
            "a mode freshness status is invalid",
        ));
    }

    let sample = parse_data_quality_date_v1(&freshness.sample_date);
    let start = parse_data_quality_date_v1(&freshness.start_date);
    let end = parse_data_quality_date_v1(&freshness.end_date);
    if sample.is_some_and(|date| date > generation_local_date) {
        return Err(data_quality_freshness_error(
            "a sample date is newer than its generation",
        ));
    }
    if known {
        if sample.is_none() {
            return Err(data_quality_freshness_error(
                "a known freshness state requires a valid sample date",
            ));
        }
        if (!freshness.start_date.is_empty() && start.is_none())
            || (!freshness.end_date.is_empty() && end.is_none())
        {
            return Err(data_quality_freshness_error(
                "a known freshness state has an invalid boundary date",
            ));
        }
    }
    if matches!((start, end), (Some(start), Some(end)) if start > end) {
        return Err(data_quality_freshness_error(
            "freshness boundary dates are reversed",
        ));
    }

    let recomputed = if start.is_some_and(|date| date > generation_local_date) {
        "future"
    } else if end.is_some_and(|date| date < generation_local_date) {
        "stale"
    } else if start.is_some() || end.is_some() {
        "active"
    } else {
        "unknown"
    };
    if freshness.status != recomputed {
        return Err(data_quality_freshness_error(
            "a mode freshness status does not match its dates",
        ));
    }
    Ok(())
}

/// Parse the exact date shapes accepted by the data-quality freshness
/// contract. Callers that expose freshness must use this parser too, so an
/// upstream value classified as unknown cannot be normalized into a date by a
/// more permissive consumer.
pub fn parse_data_quality_date_v1(value: &str) -> Option<NaiveDate> {
    if value.is_empty() || value != value.trim() {
        return None;
    }
    let bytes = value.as_bytes();
    if bytes.len() == 10
        && bytes[0..4].iter().all(u8::is_ascii_digit)
        && bytes[4] == b'-'
        && bytes[5..7].iter().all(u8::is_ascii_digit)
        && bytes[7] == b'-'
        && bytes[8..10].iter().all(u8::is_ascii_digit)
    {
        return NaiveDate::parse_from_str(value, "%Y-%m-%d").ok();
    }
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|value| value.date_naive())
}

fn data_quality_freshness_error(message: &str) -> MihoError {
    MihoError::DataQualityFreshness(message.to_owned())
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
            for source in row_source_kinds(row) {
                sources.insert(source);
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
                change_from_previous: None,
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
    if let Some(previous) = previous {
        match parse_previous(previous) {
            Ok(previous) => compare_previous(&mut report, &previous),
            Err(()) => report.warnings.push(
                "previous data-quality report is unreadable or incompatible; generation comparison is unavailable"
                    .to_owned(),
            ),
        }
    }
    for (mode, quality) in &report.modes {
        if quality.freshness.status == "stale" {
            report.warnings.push(format!(
                "{mode}: phase is stale and recommendations use historical samples"
            ));
        }
        if let Some(age_days) = sample_age_days(&quality.freshness, local_date) {
            if age_days >= ENDGAME_SAMPLE_STALE_AFTER_DAYS {
                report.warnings.push(format!(
                    "{mode}: latest sample {} is {age_days} days old while phase status remains {}",
                    quality.freshness.sample_date, quality.freshness.status
                ));
            }
        }
    }
    report.warnings.sort();
    report.warnings.dedup();
    if !report.warnings.is_empty() {
        report.status = "warning".to_owned();
    }
    validate_data_quality_report_v1(&report, game, required_modes, local_date)?;
    bundle.add_json("data_quality.json", &report)?;
    Ok(report)
}

fn parse_previous(bytes: &[u8]) -> std::result::Result<DataQualityReportV1, ()> {
    let report = serde_json::from_slice::<DataQualityReportV1>(bytes).map_err(|_| ())?;
    (report.schema_version == DATA_QUALITY_SCHEMA_V1)
        .then_some(report)
        .ok_or(())
}

fn compare_previous(current: &mut DataQualityReportV1, previous: &DataQualityReportV1) {
    if current.game != previous.game {
        current
            .warnings
            .push("previous data-quality identity differs from the current game".to_owned());
        return;
    }
    let mut warnings = Vec::new();
    for (mode, quality) in &mut current.modes {
        let Some(old) = previous.modes.get(mode) else {
            continue;
        };
        let old_sources = old.source_coverage.iter().cloned().collect::<BTreeSet<_>>();
        let current_sources = quality
            .source_coverage
            .iter()
            .cloned()
            .collect::<BTreeSet<_>>();
        quality.change_from_previous = Some(ModeDataQualityChangeV1 {
            row_count_delta: count_delta(quality.row_count, old.row_count),
            valid_rank_count_delta: count_delta(quality.valid_rank_count, old.valid_rank_count),
            valid_performance_count_delta: count_delta(
                quality.valid_performance_count,
                old.valid_performance_count,
            ),
            sentinel_rate_delta: quality.sentinel_rate - old.sentinel_rate,
            sources_added: current_sources.difference(&old_sources).cloned().collect(),
            sources_removed: old_sources.difference(&current_sources).cloned().collect(),
        });
        if old.valid_performance_count > 0
            && (quality.valid_performance_count as u128) * 10
                <= (old.valid_performance_count as u128) * 7
        {
            warnings.push(format!(
                "{mode}: valid performance count dropped by at least 30% ({} -> {})",
                old.valid_performance_count, quality.valid_performance_count
            ));
        }
        if quality.sentinel_rate - old.sentinel_rate >= 0.20 - f64::EPSILON {
            warnings.push(format!(
                "{mode}: sentinel rate increased by at least 20 percentage points ({:.1}% -> {:.1}%)",
                old.sentinel_rate * 100.0,
                quality.sentinel_rate * 100.0
            ));
        }
    }
    current.warnings.extend(warnings);
}

fn count_delta(current: usize, previous: usize) -> i64 {
    if current >= previous {
        i64::try_from(current - previous).unwrap_or(i64::MAX)
    } else {
        -i64::try_from(previous - current).unwrap_or(i64::MAX)
    }
}

fn validate_dataset_identity(game: Game, rows: &[BTreeMap<String, String>]) -> Result<()> {
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

fn sample_age_days(freshness: &FreshnessV1, local_date: NaiveDate) -> Option<i64> {
    parse_data_quality_date_v1(&freshness.sample_date)
        .map(|sample_date| local_date.signed_duration_since(sample_date).num_days())
}

fn row_source_kinds(row: &BTreeMap<String, String>) -> Vec<String> {
    let merged = value(row, "merged_source_kinds").trim();
    let sources = if merged.is_empty() {
        value(row, "source_kind")
    } else {
        merged
    };
    sources
        .split(';')
        .map(str::trim)
        .filter(|source| !source.is_empty())
        .map(str::to_owned)
        .collect()
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
        bundle_with_phases(
            rows,
            &[&[
                "as",
                "2026-07-01",
                "4.3",
                "2026-07-01",
                "2026-07-30",
                "fixture",
                "",
            ]],
        )
    }

    fn bundle_with_phases(rows: &[&[&str]], phases: &[&[&str]]) -> ArtifactBundle {
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
                &[
                    "mode",
                    "collect_date",
                    "phase_ver",
                    "start_date",
                    "end_date",
                    "source",
                    "source_path",
                ],
                phases.iter().copied(),
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

    fn previous_report(mode: &str, quality: ModeDataQualityV1) -> Vec<u8> {
        serde_json::to_vec(&DataQualityReportV1 {
            schema_version: DATA_QUALITY_SCHEMA_V1.to_owned(),
            game: "hsr".to_owned(),
            status: "ok".to_owned(),
            warnings: Vec::new(),
            alias_conflict_count: 0,
            modes: BTreeMap::from([(mode.to_owned(), quality)]),
        })
        .unwrap()
    }

    fn unknown_freshness() -> FreshnessV1 {
        FreshnessV1 {
            status: "unknown".to_owned(),
            sample_date: String::new(),
            start_date: String::new(),
            end_date: String::new(),
            source: String::new(),
        }
    }

    fn quality_with_freshness(
        status: &str,
        sample_date: &str,
        start_date: &str,
        end_date: &str,
    ) -> ModeDataQualityV1 {
        ModeDataQualityV1 {
            row_count: 1,
            valid_rank_count: 1,
            valid_performance_count: 1,
            sentinel_count: 0,
            sentinel_rate: 0.0,
            source_coverage: vec!["fixture".to_owned()],
            freshness: FreshnessV1 {
                status: status.to_owned(),
                sample_date: sample_date.to_owned(),
                start_date: start_date.to_owned(),
                end_date: end_date.to_owned(),
                source: "fixture".to_owned(),
            },
            change_from_previous: None,
        }
    }

    fn freshness_report(
        game: Game,
        modes: impl IntoIterator<Item = (&'static str, ModeDataQualityV1)>,
    ) -> DataQualityReportV1 {
        DataQualityReportV1 {
            schema_version: DATA_QUALITY_SCHEMA_V1.to_owned(),
            game: game.code().to_owned(),
            status: "ok".to_owned(),
            warnings: Vec::new(),
            alias_conflict_count: 0,
            modes: modes
                .into_iter()
                .map(|(mode, quality)| (mode.to_owned(), quality))
                .collect(),
        }
    }

    #[test]
    fn freshness_validator_accepts_recomputed_known_states_and_compatible_unknown() {
        let generation = NaiveDate::from_ymd_opt(2026, 7, 12).unwrap();
        let mut report = freshness_report(
            Game::Hsr,
            [
                (
                    "moc",
                    quality_with_freshness(
                        "active",
                        "2026-07-12T23:59:59+08:00",
                        "2026-07-01",
                        "2026-07-31T23:59:59Z",
                    ),
                ),
                (
                    "pf",
                    quality_with_freshness("stale", "2026-07-10", "2026-06-01", "2026-07-11"),
                ),
                (
                    "as",
                    quality_with_freshness(
                        "future",
                        "2026-07-12",
                        "2026-07-13T00:00:00+08:00",
                        "2026-08-01",
                    ),
                ),
                (
                    "aa",
                    quality_with_freshness(
                        "unknown",
                        "upstream-sample-is-unparseable",
                        "upstream-start-is-unparseable",
                        "upstream-end-is-unparseable",
                    ),
                ),
            ],
        );
        report.status = "warning".to_owned();

        validate_data_quality_report_v1(
            &report,
            Game::Hsr,
            &[
                GameMode::HsrMoc,
                GameMode::HsrPf,
                GameMode::HsrAs,
                GameMode::HsrAa,
            ],
            generation,
        )
        .unwrap();
    }

    #[test]
    fn freshness_validator_rejects_invalid_report_and_required_mode_identity() {
        let generation = NaiveDate::from_ymd_opt(2026, 7, 12).unwrap();
        let valid = freshness_report(
            Game::Hsr,
            [(
                "as",
                quality_with_freshness("active", "2026-07-12", "2026-07-01", "2026-07-31"),
            )],
        );
        let validate = |report: &DataQualityReportV1, modes: &[GameMode]| {
            validate_data_quality_report_v1(report, Game::Hsr, modes, generation)
        };

        let mut wrong_schema = valid.clone();
        wrong_schema.schema_version = "miho-data-quality-v2".to_owned();
        assert!(validate(&wrong_schema, &[GameMode::HsrAs]).is_err());

        let mut wrong_game = valid.clone();
        wrong_game.game = "zzz".to_owned();
        assert!(validate(&wrong_game, &[GameMode::HsrAs]).is_err());

        let mut wrong_status = valid.clone();
        wrong_status.status = "failed".to_owned();
        assert!(validate(&wrong_status, &[GameMode::HsrAs]).is_err());

        assert!(validate(&valid, &[]).is_err());
        assert!(validate(&valid, &[GameMode::HsrAs, GameMode::HsrAs]).is_err());
        assert!(validate(&valid, &[GameMode::ZzzSd]).is_err());

        let mut missing_mode = valid.clone();
        missing_mode.modes.clear();
        assert!(validate(&missing_mode, &[GameMode::HsrAs]).is_err());

        let mut extra_mode = valid.clone();
        extra_mode.modes.insert(
            "pf".to_owned(),
            quality_with_freshness("active", "2026-07-12", "2026-07-01", "2026-07-31"),
        );
        assert!(validate(&extra_mode, &[GameMode::HsrAs]).is_err());
    }

    #[test]
    fn freshness_validator_rejects_invalid_known_dates_and_status_mismatches() {
        let generation = NaiveDate::from_ymd_opt(2026, 7, 12).unwrap();
        let assert_invalid = |quality| {
            let report = freshness_report(Game::Hsr, [("as", quality)]);
            assert!(validate_data_quality_report_v1(
                &report,
                Game::Hsr,
                &[GameMode::HsrAs],
                generation,
            )
            .is_err());
        };

        for sample in [
            "",
            "not-a-date",
            " 2026-07-12",
            "2026-07-12 ",
            "2026-07-12garbage",
            "2026-07-13",
        ] {
            assert_invalid(quality_with_freshness(
                "active",
                sample,
                "2026-07-01",
                "2026-07-31",
            ));
        }
        assert_invalid(quality_with_freshness(
            "active",
            "2026-07-12",
            "not-a-date",
            "2026-07-31",
        ));
        assert_invalid(quality_with_freshness(
            "active",
            "2026-07-12",
            "2026-07-01",
            "2026-07-31garbage",
        ));
        assert_invalid(quality_with_freshness(
            "active",
            "2026-07-12",
            "2026-07-31",
            "2026-07-01",
        ));
        assert_invalid(quality_with_freshness(
            "stale",
            "2026-07-12",
            "2026-07-01",
            "2026-07-31",
        ));
    }

    #[test]
    fn freshness_validator_only_treats_unparseable_unknown_boundaries_as_missing() {
        let generation = NaiveDate::from_ymd_opt(2026, 7, 12).unwrap();
        for quality in [
            quality_with_freshness("unknown", "2026-07-13", "not-a-date", "not-a-date"),
            quality_with_freshness("unknown", "not-a-date", "not-a-date", "2026-07-31"),
            quality_with_freshness("unknown", "not-a-date", "2026-07-13", "not-a-date"),
        ] {
            let report = freshness_report(Game::Hsr, [("as", quality)]);
            assert!(validate_data_quality_report_v1(
                &report,
                Game::Hsr,
                &[GameMode::HsrAs],
                generation,
            )
            .is_err());
        }
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
        assert!((mode.sentinel_rate - 0.5).abs() <= f64::EPSILON);
        assert_eq!(mode.source_coverage, ["fixture"]);
        assert_eq!(mode.freshness.status, "active");
        assert!(bundle.get("data_quality.json").is_some());
    }

    #[test]
    fn source_coverage_prefers_merged_source_kinds_and_splits_each_source() {
        let merged = BTreeMap::from([
            ("source_kind".to_owned(), "hf_comps".to_owned()),
            (
                "merged_source_kinds".to_owned(),
                "hf_comps;prydwen_page".to_owned(),
            ),
        ]);
        assert_eq!(
            row_source_kinds(&merged),
            ["hf_comps".to_owned(), "prydwen_page".to_owned()]
        );

        let legacy = BTreeMap::from([("source_kind".to_owned(), "fixture".to_owned())]);
        assert_eq!(row_source_kinds(&legacy), ["fixture"]);
    }

    #[test]
    fn reports_active_stale_future_and_unknown_freshness() {
        let mut bundle = bundle_with_phases(
            &[
                &["moc", "1", "1", "hf_comps"],
                &["pf", "1", "30000", "hf_comps"],
                &["as", "1", "3500", "supplemental"],
                &["aa", "1", "2.5", "hf_comps"],
            ],
            &[
                &[
                    "moc",
                    "2026-07-10",
                    "4.3",
                    "2026-07-01",
                    "2026-07-31",
                    "hf",
                    "",
                ],
                &[
                    "pf",
                    "2026-07-09",
                    "4.3",
                    "2026-06-01",
                    "2026-07-11",
                    "hf",
                    "",
                ],
                &[
                    "as",
                    "2026-07-11",
                    "4.3",
                    "2026-07-13",
                    "2026-08-01",
                    "hf",
                    "",
                ],
                &["aa", "2026-07-08", "4.3", "", "", "", "raw/aa.json"],
            ],
        );
        let report = attach_data_quality_v1(
            &mut bundle,
            Game::Hsr,
            &[
                GameMode::HsrMoc,
                GameMode::HsrPf,
                GameMode::HsrAs,
                GameMode::HsrAa,
            ],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            None,
        )
        .unwrap();

        assert_eq!(report.modes["moc"].freshness.status, "active");
        assert_eq!(report.modes["pf"].freshness.status, "stale");
        assert_eq!(report.modes["as"].freshness.status, "future");
        assert_eq!(report.modes["aa"].freshness.status, "unknown");
        assert_eq!(report.modes["moc"].freshness.sample_date, "2026-07-10");
        assert_eq!(report.modes["aa"].freshness.source, "raw/aa.json");
        assert_eq!(report.status, "warning");
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.contains("pf: phase is stale")));
    }

    #[test]
    fn active_phase_with_old_sample_reports_sample_staleness_separately() {
        let mut bundle = bundle_with_phases(
            &[&["pf", "1", "30000", "hf_comps"]],
            &[&[
                "pf",
                "2026-06-25",
                "4.3.1",
                "2026-06-22",
                "2026-08-03",
                "huggingface",
                "4.3.2/",
            ]],
        );
        let report = attach_data_quality_v1(
            &mut bundle,
            Game::Hsr,
            &[GameMode::HsrPf],
            NaiveDate::from_ymd_opt(2026, 7, 28).unwrap(),
            None,
        )
        .unwrap();

        assert_eq!(report.modes["pf"].freshness.status, "active");
        assert_eq!(report.status, "warning");
        assert!(report.warnings.iter().any(|warning| {
            warning == "pf: latest sample 2026-06-25 is 33 days old while phase status remains active"
        }));
        assert!(!report
            .warnings
            .iter()
            .any(|warning| warning.contains("pf: phase is stale")));

        let emitted: DataQualityReportV1 =
            serde_json::from_slice(bundle.get("data_quality.json").unwrap()).unwrap();
        assert_eq!(emitted, report);
    }

    #[test]
    fn exact_degradation_thresholds_warn_and_record_generation_changes() {
        let mut bundle = bundle(&[
            &["as", "1", "1", "current-a"],
            &["as", "2", "2", "current-a"],
            &["as", "3", "3", "current-a"],
            &["as", "4", "4", "current-a"],
            &["as", "5", "5", "current-a"],
            &["as", "6", "6", "current-a"],
            &["as", "7", "7", "current-a"],
            &["as", "8", "99.99", "current-b"],
            &["as", "9", "99.99", "current-b"],
            &["as", "10", "", "current-a"],
        ]);
        let previous = previous_report(
            "as",
            ModeDataQualityV1 {
                row_count: 10,
                valid_rank_count: 10,
                valid_performance_count: 10,
                sentinel_count: 0,
                sentinel_rate: 0.0,
                source_coverage: vec!["current-a".to_owned(), "retired".to_owned()],
                freshness: unknown_freshness(),
                change_from_previous: None,
            },
        );
        let report = attach_data_quality_v1(
            &mut bundle,
            Game::Hsr,
            &[GameMode::HsrAs],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            Some(&previous),
        )
        .unwrap();

        assert_eq!(report.status, "warning");
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning
                .contains("valid performance count dropped by at least 30% (10 -> 7)")));
        assert!(report.warnings.iter().any(|warning| warning
            .contains("sentinel rate increased by at least 20 percentage points (0.0% -> 20.0%)")));
        let change = report.modes["as"].change_from_previous.as_ref().unwrap();
        assert_eq!(change.row_count_delta, 0);
        assert_eq!(change.valid_rank_count_delta, 0);
        assert_eq!(change.valid_performance_count_delta, -3);
        assert!((change.sentinel_rate_delta - 0.2).abs() <= f64::EPSILON);
        assert_eq!(change.sources_added, ["current-b"]);
        assert_eq!(change.sources_removed, ["retired"]);

        let emitted: serde_json::Value =
            serde_json::from_slice(bundle.get("data_quality.json").unwrap()).unwrap();
        assert_eq!(
            emitted["modes"]["as"]["change_from_previous"]["valid_performance_count_delta"],
            -3
        );
    }

    #[test]
    fn corrupt_previous_report_warns_without_blocking_current_generation() {
        let mut bundle = bundle(&[&["as", "1", "3500", "fixture"]]);
        let report = attach_data_quality_v1(
            &mut bundle,
            Game::Hsr,
            &[GameMode::HsrAs],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            Some(br#"{"schema_version":"miho-data-quality-v1","game":}broken"#),
        )
        .unwrap();

        assert_eq!(report.status, "warning");
        assert!(report
            .warnings
            .iter()
            .any(|warning| warning.contains("generation comparison is unavailable")));
        let emitted: DataQualityReportV1 =
            serde_json::from_slice(bundle.get("data_quality.json").unwrap()).unwrap();
        assert_eq!(emitted, report);
    }

    #[test]
    fn foreign_game_mode_fails_dataset_identity_validation() {
        let mut bundle = bundle(&[&["sd", "1", "3500", "fixture"]]);
        let error = attach_data_quality_v1(
            &mut bundle,
            Game::Hsr,
            &[GameMode::HsrAs],
            NaiveDate::from_ymd_opt(2026, 7, 12).unwrap(),
            None,
        )
        .unwrap_err();
        assert!(error.to_string().contains("dataset identity conflict"));
        assert!(bundle.get("data_quality.json").is_none());
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
