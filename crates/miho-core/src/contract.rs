use std::{collections::BTreeMap, path::PathBuf};

use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};

use crate::{
    output::{ArtifactBundle, ArtifactManifestEntry},
    MihoError, Result,
};

pub const EXPORT_REQUEST_SCHEMA_VERSION: u16 = 1;
pub const EXPORT_RECEIPT_SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "lowercase")]
pub enum Game {
    Hsr,
    Zzz,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum GameMode {
    #[serde(rename = "moc")]
    HsrMoc,
    #[serde(rename = "pf")]
    HsrPf,
    #[serde(rename = "as")]
    HsrAs,
    #[serde(rename = "aa")]
    HsrAa,
    #[serde(rename = "sd")]
    ZzzSd,
    #[serde(rename = "da")]
    ZzzDa,
}

impl GameMode {
    pub fn parse(game: Game, value: &str) -> Result<Self> {
        let mode = match (game, value.trim().to_ascii_lowercase().as_str()) {
            (Game::Hsr, "moc") => Self::HsrMoc,
            (Game::Hsr, "pf") => Self::HsrPf,
            (Game::Hsr, "as") => Self::HsrAs,
            (Game::Hsr, "aa") => Self::HsrAa,
            (Game::Zzz, "sd") => Self::ZzzSd,
            (Game::Zzz, "da") => Self::ZzzDa,
            _ => {
                return Err(MihoError::Unsupported(format!(
                    "mode {value:?} is not valid for {}",
                    game.code()
                )))
            }
        };
        Ok(mode)
    }

    pub const fn game(self) -> Game {
        match self {
            Self::HsrMoc | Self::HsrPf | Self::HsrAs | Self::HsrAa => Game::Hsr,
            Self::ZzzSd | Self::ZzzDa => Game::Zzz,
        }
    }

    pub const fn code(self) -> &'static str {
        match self {
            Self::HsrMoc => "moc",
            Self::HsrPf => "pf",
            Self::HsrAs => "as",
            Self::HsrAa => "aa",
            Self::ZzzSd => "sd",
            Self::ZzzDa => "da",
        }
    }
}

impl std::fmt::Display for GameMode {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.code())
    }
}

impl AsRef<str> for GameMode {
    fn as_ref(&self) -> &str {
        self.code()
    }
}

impl Game {
    pub const fn code(self) -> &'static str {
        match self {
            Self::Hsr => "hsr",
            Self::Zzz => "zzz",
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DateRange {
    pub from: Option<NaiveDate>,
    pub to: Option<NaiveDate>,
}

impl DateRange {
    pub fn contains(&self, date: NaiveDate) -> bool {
        self.from.is_none_or(|from| date >= from) && self.to.is_none_or(|to| date <= to)
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DatasetRef {
    pub repo_id: String,
    pub revision: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FeatureFlags {
    pub hf_teams: bool,
    pub prydwen_visible: bool,
    pub prydwen_tier: bool,
    pub official_names: bool,
}

impl Default for FeatureFlags {
    fn default() -> Self {
        Self {
            hf_teams: true,
            prydwen_visible: true,
            prydwen_tier: true,
            official_names: true,
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum HistoryPolicy {
    Disabled,
    #[default]
    MergeExisting,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkbookPolicy {
    #[default]
    Disabled,
    BestEffort,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExportRequestV1 {
    pub schema_version: u16,
    pub game: Game,
    pub modes: Vec<GameMode>,
    pub date_range: DateRange,
    pub dataset: DatasetRef,
    pub features: FeatureFlags,
    pub prydwen_top_n: usize,
    pub name_map_seed: Option<PathBuf>,
    pub history: HistoryPolicy,
    pub workbook: WorkbookPolicy,
}

impl ExportRequestV1 {
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != EXPORT_REQUEST_SCHEMA_VERSION {
            return Err(MihoError::Unsupported(format!(
                "export request schema {} is not supported",
                self.schema_version
            )));
        }
        if self.dataset.repo_id.trim().is_empty() || self.dataset.revision.trim().is_empty() {
            return Err(MihoError::Unsupported(
                "dataset repo_id and revision must not be empty".into(),
            ));
        }
        if let Some(mode) = self.modes.iter().find(|mode| mode.game() != self.game) {
            return Err(MihoError::Unsupported(format!(
                "mode {} does not belong to {}",
                mode.code(),
                self.game.code()
            )));
        }
        if self.game == Game::Zzz && self.name_map_seed.is_some() {
            return Err(MihoError::Unsupported(
                "name_map_seed is only supported for hsr".into(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FetchPolicy {
    Online,
    CacheOnly,
    Fixture,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ExportContext {
    pub fetched_at: DateTime<Utc>,
    pub fetch_policy: FetchPolicy,
    pub cache_root: PathBuf,
    pub output_root: PathBuf,
    pub existing_output_root: Option<PathBuf>,
    pub zzz_phase_overrides: Option<PathBuf>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DiagnosticSeverity {
    Warning,
    RecoverableError,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DiagnosticSource {
    HuggingFace,
    Prydwen,
    Hoyowiki,
    NameSeed,
    History,
    Workbook,
    Pipeline,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct Diagnostic {
    pub severity: DiagnosticSeverity,
    pub code: String,
    pub source: DiagnosticSource,
    pub game: Game,
    pub snapshot: Option<String>,
    pub mode: Option<GameMode>,
    pub path: Option<String>,
    pub message: String,
}

pub mod diagnostic_code {
    pub const PIPELINE_WARNING: &str = "pipeline.warning";
    pub const PIPELINE_RECOVERABLE: &str = "pipeline.recoverable";
    pub const SUPPLEMENTAL_NOT_CONNECTED: &str = "supplemental.not_connected";
    pub const SNAPSHOT_DATE_MISSING: &str = "hugging_face.snapshot_date_missing";
    pub const NO_MATCHING_SNAPSHOTS: &str = "hugging_face.no_matching_snapshots";
    pub const SUPPLEMENTAL_FETCH_FAILED: &str = "supplemental.fetch_failed";
    pub const SUPPLEMENTAL_PARSE_EMPTY: &str = "supplemental.parse_empty";
    pub const SUPPLEMENTAL_CACHE_FALLBACK: &str = "supplemental.cache_fallback";
    pub const NAME_SEED_FAILED: &str = "name_seed.read_failed";
    pub const HISTORY_READ_FAILED: &str = "history.read_failed";
    pub const WORKBOOK_GENERATION_FAILED: &str = "workbook.generation_failed";
}

#[derive(Debug, Clone, Default, Deserialize, Serialize, PartialEq, Eq)]
pub struct ExportStats {
    pub snapshots: usize,
    pub phases: usize,
    pub phases_by_mode: BTreeMap<GameMode, usize>,
    pub character_rows: usize,
    pub team_rows: usize,
    pub ordered_team_rows: usize,
    pub unordered_team_rows: usize,
    pub name_rows: usize,
    pub unresolved_names: usize,
    pub resolved_name_rows: usize,
    pub tier_rows: usize,
    pub tier_history_rows: usize,
    pub changelog_rows: usize,
    pub trend_rows: usize,
    pub chart_rows: usize,
    pub aa_split: bool,
}

#[derive(Debug)]
pub struct ExportOutcome {
    pub request: ExportRequestV1,
    pub bundle: ArtifactBundle,
    pub diagnostics: Vec<Diagnostic>,
    pub stats: ExportStats,
}

impl ExportOutcome {
    pub fn warning_messages(&self) -> impl Iterator<Item = &str> {
        self.diagnostics
            .iter()
            .filter(|item| item.severity == DiagnosticSeverity::Warning)
            .map(|item| item.message.as_str())
    }

    pub fn error_messages(&self) -> impl Iterator<Item = &str> {
        self.diagnostics
            .iter()
            .filter(|item| item.severity == DiagnosticSeverity::RecoverableError)
            .map(|item| item.message.as_str())
    }

    pub fn receipt(&self) -> ExportReceiptV1 {
        ExportReceiptV1 {
            schema_version: EXPORT_RECEIPT_SCHEMA_VERSION,
            game: self.request.game,
            artifacts: self.bundle.manifest(),
            diagnostics: self.diagnostics.clone(),
            stats: self.stats.clone(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExportReceiptV1 {
    pub schema_version: u16,
    pub game: Game,
    pub artifacts: Vec<ArtifactManifestEntry>,
    pub diagnostics: Vec<Diagnostic>,
    pub stats: ExportStats,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExportFailureV1 {
    pub schema_version: u16,
    pub code: String,
    pub message: String,
    pub diagnostics: Vec<Diagnostic>,
}

impl ExportFailureV1 {
    pub fn pipeline(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            schema_version: EXPORT_RECEIPT_SCHEMA_VERSION,
            code: code.into(),
            message: message.into(),
            diagnostics: vec![],
        }
    }

    pub fn from_error(error: &MihoError) -> Self {
        let code = match error {
            MihoError::Read { .. } => "io.read_failed",
            MihoError::Write { .. } => "io.write_failed",
            MihoError::Json { .. } => "format.invalid_json",
            MihoError::Yaml { .. } => "format.invalid_yaml",
            MihoError::Network(_) => "network.request_failed",
            MihoError::CacheMiss(_) => "cache.miss",
            MihoError::InvalidCacheKey(_) => "cache.invalid_key",
            MihoError::InvalidArtifactPath(_) => "artifact.invalid_path",
            MihoError::CsvWidth { .. } => "format.csv_width",
            MihoError::Csv(_) => "format.csv_failed",
            MihoError::Workbook(_) => "workbook.generation_failed",
            MihoError::Unsupported(_) => "request.unsupported",
        };
        Self::pipeline(code, error.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> ExportRequestV1 {
        ExportRequestV1 {
            schema_version: EXPORT_REQUEST_SCHEMA_VERSION,
            game: Game::Hsr,
            modes: vec![GameMode::HsrMoc, GameMode::HsrPf],
            date_range: DateRange {
                from: NaiveDate::from_ymd_opt(2026, 7, 2),
                to: NaiveDate::from_ymd_opt(2026, 7, 1),
            },
            dataset: DatasetRef {
                repo_id: "owner/repo".into(),
                revision: "main".into(),
            },
            features: FeatureFlags::default(),
            prydwen_top_n: 100,
            name_map_seed: None,
            history: HistoryPolicy::MergeExisting,
            workbook: WorkbookPolicy::Disabled,
        }
    }

    #[test]
    fn request_is_versioned_serializable_and_keeps_inverse_range_compatibility() {
        let request = request();
        request.validate().unwrap();
        assert!(!request
            .date_range
            .contains(NaiveDate::from_ymd_opt(2026, 7, 1).unwrap()));
        let value = serde_json::to_value(&request).unwrap();
        assert_eq!(value["schema_version"], 1);
        assert_eq!(value["modes"], serde_json::json!(["moc", "pf"]));
        assert_eq!(
            serde_json::from_value::<ExportRequestV1>(value).unwrap(),
            request
        );
    }

    #[test]
    fn request_rejects_wrong_version_cross_game_mode_and_zzz_seed() {
        let mut value = request();
        value.schema_version = 2;
        assert!(value.validate().is_err());

        let mut value = request();
        value.modes.push(GameMode::ZzzSd);
        assert!(value.validate().is_err());

        let mut value = request();
        value.game = Game::Zzz;
        value.modes = vec![GameMode::ZzzSd];
        value.name_map_seed = Some("seed.csv".into());
        assert!(value.validate().is_err());
    }

    #[test]
    fn receipt_and_failure_are_versioned_serializable_ipc_boundaries() {
        let mut bundle = ArtifactBundle::default();
        bundle.add_text("report.md", "ok").unwrap();
        let outcome = ExportOutcome {
            request: request(),
            bundle,
            diagnostics: vec![],
            stats: ExportStats {
                phases_by_mode: BTreeMap::from([(GameMode::HsrMoc, 1)]),
                phases: 1,
                ..Default::default()
            },
        };
        let receipt = outcome.receipt();
        let value = serde_json::to_value(&receipt).unwrap();
        assert_eq!(value["schema_version"], EXPORT_RECEIPT_SCHEMA_VERSION);
        assert_eq!(value["stats"]["phases_by_mode"]["moc"], 1);
        assert_eq!(
            serde_json::from_value::<ExportReceiptV1>(value).unwrap(),
            receipt
        );
        assert_eq!(receipt.game, Game::Hsr);

        let failure = ExportFailureV1::pipeline("invalid_request", "bad request");
        assert_eq!(
            serde_json::from_value::<ExportFailureV1>(serde_json::to_value(&failure).unwrap())
                .unwrap(),
            failure
        );
    }

    #[test]
    fn request_rejects_unknown_top_level_and_nested_fields() {
        let mut value = serde_json::to_value(request()).unwrap();
        value["unexpected"] = serde_json::json!(true);
        assert!(serde_json::from_value::<ExportRequestV1>(value).is_err());

        let mut value = serde_json::to_value(request()).unwrap();
        value["features"]["unexpected"] = serde_json::json!(true);
        assert!(serde_json::from_value::<ExportRequestV1>(value).is_err());
    }
}
