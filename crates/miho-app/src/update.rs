use std::{
    collections::BTreeMap,
    fs::{self, File},
    future::Future,
    io::Read,
    path::{Component, Path, PathBuf},
    pin::Pin,
    sync::atomic::{AtomicU64, Ordering},
    time::Instant,
};

use chrono::{
    DateTime, Duration, FixedOffset, Local, NaiveDate, NaiveDateTime, SecondsFormat, Timelike, Utc,
};
use miho_core::{
    atomic,
    contract::{diagnostic_code, FeatureFlags, Game},
    data_quality::{validate_data_quality_report_v1, DataQualityReportV1},
    network::FetchSource,
    output::ArtifactManifestEntry,
    MihoError,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{
    execute_export_observed_v1, execute_export_observed_with_hub_v1, execute_task_observed_v1,
    export_cache_root, AppInvocation, CoverageTaskV1, ExecutionControlError, ExecutionObserver,
    ExportInvocation, ExportObserver, ExportSourceV1, ExportTaskV1, PullTaskV1,
    ResolvedUpdateConfigV1, TaskFreshnessSummaryV1, TaskOperationV1, TaskRequestV1, TaskSpecV1,
    WorkspaceLayout, WorkspaceSnapshotLease, WorkspaceWriteLease, WorkspaceWriteLeaseError,
};

pub const UPDATE_RECEIPT_SCHEMA_V1: &str = "miho-update-receipt-v1";
pub const UPDATE_STATE_SCHEMA_V1: &str = "miho-update-state-v1";
pub const UPDATE_HEALTH_SCHEMA_V1: &str = "miho-update-health-v1";
pub const UPDATE_ATTEMPT_DIRECTORY: &str = "update-attempts";
pub const UPDATE_STATE_FILE: &str = "update-state-v1.json";
pub const UPDATE_CANONICAL_RECEIPT_FILE: &str = "last-update-receipt-v1.json";
pub const MAX_UPDATE_ATTEMPT_ID_BYTES_V1: usize = 96;
const MAX_UPDATE_FRESHNESS_BYTES_V1: u64 = 2 * 1024 * 1024;
const DEFAULT_UPDATE_CONFIG_RELATIVE_PATH_V1: &str = "configs/update_v1.json";

static NEXT_ATTEMPT_ID: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum UpdateRunStatusV1 {
    Running,
    Succeeded,
    Partial,
    Failed,
    Interrupted,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum UpdateStepStatusV1 {
    Pending,
    Running,
    Succeeded,
    Failed,
    Skipped,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "kebab-case")]
pub enum UpdateStepKindV1 {
    HsrExport,
    ZzzExport,
    ZzzCoverage,
    ZzzPullValue,
    ZzzReviewPacket,
}

impl UpdateStepKindV1 {
    pub const fn game(self) -> Game {
        match self {
            Self::HsrExport => Game::Hsr,
            Self::ZzzExport | Self::ZzzCoverage | Self::ZzzPullValue | Self::ZzzReviewPacket => {
                Game::Zzz
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateArtifactV1 {
    /// Workspace-relative path; absolute paths are rejected before a step can
    /// be recorded as successful.
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateStepFailureV1 {
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

impl UpdateStepFailureV1 {
    pub fn safe(code: impl Into<String>, message: impl Into<String>, retryable: bool) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            retryable,
        }
    }
}

impl std::fmt::Display for UpdateStepFailureV1 {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for UpdateStepFailureV1 {}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateStepReceiptV1 {
    pub step: UpdateStepKindV1,
    pub status: UpdateStepStatusV1,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub duration_ms: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    /// Sum of data rows across this step's emitted CSV artifacts. Derived
    /// tables may represent the same source record more than once; this is an
    /// output-volume receipt, not a unique-source-record metric.
    pub row_count: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fetch_source: Option<FetchSource>,
    #[serde(default)]
    pub cache_fallback: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason_code: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub artifacts: Vec<UpdateArtifactV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure: Option<UpdateStepFailureV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateGameReceiptV1 {
    pub game: Game,
    pub selected: bool,
    pub status: UpdateStepStatusV1,
    pub steps: Vec<UpdateStepReceiptV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateReceiptV1 {
    pub schema_version: String,
    pub attempt_id: String,
    pub started_at_utc: String,
    pub invocation_local_datetime: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub finished_at_utc: Option<String>,
    pub status: UpdateRunStatusV1,
    pub force: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub config_sha256: Option<String>,
    pub state_committed: bool,
    pub receipt_committed: bool,
    pub games: Vec<UpdateGameReceiptV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure: Option<UpdateStepFailureV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateStateGameV1 {
    pub attempt_id: String,
    pub completed_at_utc: String,
    pub config_sha256: String,
    pub artifacts: Vec<UpdateArtifactV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateStateV1 {
    pub schema_version: String,
    pub games: BTreeMap<Game, UpdateStateGameV1>,
}

impl Default for UpdateStateV1 {
    fn default() -> Self {
        Self {
            schema_version: UPDATE_STATE_SCHEMA_V1.to_owned(),
            games: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateRequestV1 {
    pub workspace: PathBuf,
    pub skip_hsr: bool,
    pub skip_zzz: bool,
    pub force: bool,
    pub config_sha256: Option<String>,
}

/// Fully resolved single-game update request owned by trusted native code.
///
/// This type deliberately has no serde implementation: a WebView may choose
/// only the public HSR/ZZZ operation while the desktop adapter resolves the
/// configuration, digest, workspace, and invocation locally.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrustedSingleGameUpdateV1 {
    pub config: ResolvedUpdateConfigV1,
    pub config_sha256: String,
    pub game: Game,
    pub invocation: UpdateInvocationV1,
}

impl TrustedSingleGameUpdateV1 {
    pub fn new(
        config: ResolvedUpdateConfigV1,
        config_sha256: String,
        game: Game,
        invocation: UpdateInvocationV1,
    ) -> Result<Self, UpdateStepFailureV1> {
        let request = Self {
            config,
            config_sha256,
            game,
            invocation,
        };
        request.update_request().validate()?;
        Ok(request)
    }

    pub fn operation(&self) -> TaskOperationV1 {
        match self.game {
            Game::Hsr => TaskOperationV1::HsrExport,
            Game::Zzz => TaskOperationV1::ZzzExport,
        }
    }

    pub fn update_request(&self) -> UpdateRequestV1 {
        UpdateRequestV1 {
            workspace: self.config.workspace.clone(),
            skip_hsr: self.game != Game::Hsr,
            skip_zzz: self.game != Game::Zzz,
            // A desktop "update now" request is always an explicit refresh.
            force: true,
            config_sha256: Some(self.config_sha256.clone()),
        }
    }

    pub fn output_root(&self) -> &Path {
        match self.game {
            Game::Hsr => &self.config.hsr.output,
            Game::Zzz => &self.config.zzz.export.output,
        }
    }
}

impl UpdateRequestV1 {
    pub fn validate(&self) -> Result<(), UpdateStepFailureV1> {
        if self.skip_hsr && self.skip_zzz {
            return Err(UpdateStepFailureV1::safe(
                "update.no_games_selected",
                "no game was selected for update",
                false,
            ));
        }
        if self
            .config_sha256
            .as_deref()
            .is_some_and(|value| !valid_sha256(value))
        {
            return Err(UpdateStepFailureV1::safe(
                "update.config_identity_invalid",
                "the update configuration identity is invalid",
                false,
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateInvocationV1 {
    pub attempt_id: String,
    pub observed_at: DateTime<FixedOffset>,
}

impl UpdateInvocationV1 {
    pub fn capture() -> Self {
        let now = Local::now();
        let sequence = NEXT_ATTEMPT_ID.fetch_add(1, Ordering::Relaxed);
        let observed_at = truncate_to_microseconds(now.fixed_offset());
        let started_at_utc = observed_at.with_timezone(&Utc);
        let attempt_id = format!(
            "{}-{}-{sequence}",
            started_at_utc.format("%Y%m%dT%H%M%S%6fZ"),
            std::process::id(),
        );
        debug_assert!(is_valid_update_attempt_id_v1(&attempt_id));
        Self {
            attempt_id,
            observed_at,
        }
    }

    pub fn new(
        attempt_id: String,
        observed_at: DateTime<FixedOffset>,
    ) -> Result<Self, UpdateStepFailureV1> {
        if !is_valid_update_attempt_id_v1(&attempt_id) {
            return Err(UpdateStepFailureV1::safe(
                "update.invalid_attempt_id",
                "attempt identifier is invalid",
                false,
            ));
        }
        Ok(Self {
            attempt_id,
            observed_at: truncate_to_microseconds(observed_at),
        })
    }

    pub fn capture_with_attempt_id(attempt_id: String) -> Result<Self, UpdateStepFailureV1> {
        Self::new(attempt_id, Local::now().fixed_offset())
    }

    pub fn started_at_utc(&self) -> DateTime<Utc> {
        self.observed_at.with_timezone(&Utc)
    }

    pub fn local_datetime(&self) -> NaiveDateTime {
        self.observed_at.naive_local()
    }
}

fn truncate_to_microseconds(value: DateTime<FixedOffset>) -> DateTime<FixedOffset> {
    let nanos = value.nanosecond() / 1_000 * 1_000;
    value.with_nanosecond(nanos).unwrap_or(value)
}

pub fn is_valid_update_attempt_id_v1(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= MAX_UPDATE_ATTEMPT_ID_BYTES_V1
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateStepContextV1 {
    pub workspace: PathBuf,
    pub attempt_id: String,
    pub observed_at: DateTime<FixedOffset>,
    pub force: bool,
}

impl UpdateStepContextV1 {
    pub fn started_at_utc(&self) -> DateTime<Utc> {
        self.observed_at.with_timezone(&Utc)
    }

    pub fn local_datetime(&self) -> NaiveDateTime {
        self.observed_at.naive_local()
    }
}

pub type UpdateStepFuture<'a> =
    Pin<Box<dyn Future<Output = Result<Vec<UpdateArtifactV1>, UpdateStepFailureV1>> + Send + 'a>>;

pub type ObservedUpdateStepFuture<'a> = Pin<
    Box<dyn Future<Output = Result<Vec<UpdateArtifactV1>, UpdateStepExecutionErrorV1>> + Send + 'a>,
>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UpdateStepExecutionErrorV1 {
    Failure(UpdateStepFailureV1),
    Control(ExecutionControlError),
}

pub trait UpdateStepExecutor: Send + Sync {
    fn execute<'a>(
        &'a self,
        step: UpdateStepKindV1,
        context: &'a UpdateStepContextV1,
    ) -> UpdateStepFuture<'a>;

    fn execute_observed<'a>(
        &'a self,
        step: UpdateStepKindV1,
        context: &'a UpdateStepContextV1,
        _observer: &'a dyn ExecutionObserver,
    ) -> ObservedUpdateStepFuture<'a> {
        Box::pin(async move {
            self.execute(step, context)
                .await
                .map_err(UpdateStepExecutionErrorV1::Failure)
        })
    }

    /// Optional safe provenance for a completed execution attempt. The
    /// default preserves compatibility for external/custom executors.
    fn fetch_source(
        &self,
        _step: UpdateStepKindV1,
        _execution_succeeded: bool,
        _failure: Option<&UpdateStepFailureV1>,
    ) -> Option<FetchSource> {
        None
    }

    fn cache_fallback(
        &self,
        _step: UpdateStepKindV1,
        _failure: Option<&UpdateStepFailureV1>,
    ) -> bool {
        false
    }

    /// Trusted configuration used to verify the generation's freshness
    /// evidence before success state is committed and again before the
    /// workspace write lease is released. A successful execution that leaves
    /// this unset is rejected before success state is committed.
    fn freshness_config(&self) -> Option<&ResolvedUpdateConfigV1> {
        None
    }
}

/// Production native backend. It reuses the same export and typed report
/// executors as direct CLI/Tauri calls; no subprocess or Python interpreter is
/// involved.
#[derive(Debug, Clone)]
pub struct NativeUpdateExecutorV1 {
    config: ResolvedUpdateConfigV1,
    fixture_sources: BTreeMap<Game, (PathBuf, Option<PathBuf>)>,
    hf_origins: BTreeMap<Game, String>,
}

impl NativeUpdateExecutorV1 {
    pub fn new(config: ResolvedUpdateConfigV1) -> Self {
        Self {
            config,
            fixture_sources: BTreeMap::new(),
            hf_origins: BTreeMap::new(),
        }
    }

    pub fn config(&self) -> &ResolvedUpdateConfigV1 {
        &self.config
    }

    /// Explicit native test/offline source. Release CLI adapters do not read
    /// environment variables into this seam.
    pub fn with_fixture_source(
        mut self,
        game: Game,
        root: PathBuf,
        supplemental_root: Option<PathBuf>,
    ) -> Self {
        self.fixture_sources.insert(game, (root, supplemental_root));
        self
    }

    /// Explicit trusted test/mirror seam. Release CLI adapters never derive
    /// this value from environment variables or update config.
    pub fn with_hf_origin(mut self, game: Game, origin: impl Into<String>) -> Self {
        self.hf_origins.insert(game, origin.into());
        self
    }
}

impl UpdateStepExecutor for NativeUpdateExecutorV1 {
    fn execute<'a>(
        &'a self,
        step: UpdateStepKindV1,
        context: &'a UpdateStepContextV1,
    ) -> UpdateStepFuture<'a> {
        Box::pin(async move {
            self.execute_step(step, context, None)
                .await
                .map_err(|error| match error {
                    UpdateStepExecutionErrorV1::Failure(failure) => failure,
                    UpdateStepExecutionErrorV1::Control(_) => cancelled_step_failure(),
                })
        })
    }

    fn execute_observed<'a>(
        &'a self,
        step: UpdateStepKindV1,
        context: &'a UpdateStepContextV1,
        observer: &'a dyn ExecutionObserver,
    ) -> ObservedUpdateStepFuture<'a> {
        Box::pin(async move { self.execute_step(step, context, Some(observer)).await })
    }

    fn fetch_source(
        &self,
        step: UpdateStepKindV1,
        execution_succeeded: bool,
        failure: Option<&UpdateStepFailureV1>,
    ) -> Option<FetchSource> {
        if !matches!(
            step,
            UpdateStepKindV1::HsrExport | UpdateStepKindV1::ZzzExport
        ) {
            return None;
        }
        if failure.is_some_and(|failure| is_supplemental_cache_fallback_code(&failure.code)) {
            return (!self.fixture_sources.contains_key(&step.game()))
                .then_some(FetchSource::Network);
        }
        if failure.is_some_and(|failure| is_cache_fallback_code(&failure.code)) {
            return Some(FetchSource::Cache);
        }
        if execution_succeeded && !self.fixture_sources.contains_key(&step.game()) {
            return Some(FetchSource::Network);
        }
        None
    }

    fn cache_fallback(
        &self,
        _step: UpdateStepKindV1,
        failure: Option<&UpdateStepFailureV1>,
    ) -> bool {
        failure.is_some_and(|failure| is_cache_fallback_code(&failure.code))
    }

    fn freshness_config(&self) -> Option<&ResolvedUpdateConfigV1> {
        Some(&self.config)
    }
}

impl NativeUpdateExecutorV1 {
    async fn execute_step(
        &self,
        step: UpdateStepKindV1,
        context: &UpdateStepContextV1,
        observer: Option<&dyn ExecutionObserver>,
    ) -> Result<Vec<UpdateArtifactV1>, UpdateStepExecutionErrorV1> {
        if context.workspace != self.config.workspace {
            return Err(UpdateStepExecutionErrorV1::Failure(
                UpdateStepFailureV1::safe(
                    "update.workspace_mismatch",
                    "the update executor workspace does not match the locked workspace",
                    false,
                ),
            ));
        }
        #[cfg(debug_assertions)]
        wait_for_debug_update_gate().map_err(UpdateStepExecutionErrorV1::Failure)?;
        match step {
            UpdateStepKindV1::HsrExport => self.execute_export(Game::Hsr, context, observer).await,
            UpdateStepKindV1::ZzzExport => self.execute_export(Game::Zzz, context, observer).await,
            UpdateStepKindV1::ZzzCoverage => {
                self.execute_report(UpdateStepKindV1::ZzzCoverage, context, observer)
            }
            UpdateStepKindV1::ZzzPullValue => {
                self.execute_report(UpdateStepKindV1::ZzzPullValue, context, observer)
            }
            UpdateStepKindV1::ZzzReviewPacket => {
                self.execute_report(UpdateStepKindV1::ZzzReviewPacket, context, observer)
            }
        }
    }

    async fn execute_export(
        &self,
        game: Game,
        context: &UpdateStepContextV1,
        observer: Option<&dyn ExecutionObserver>,
    ) -> Result<Vec<UpdateArtifactV1>, UpdateStepExecutionErrorV1> {
        let settings = match game {
            Game::Hsr => &self.config.hsr,
            Game::Zzz => &self.config.zzz.export,
        };
        let invocation = ExportInvocation::new(context.workspace.clone(), context.observed_at)
            .map_err(|_| {
                UpdateStepExecutionErrorV1::Failure(safe_step_failure(
                    game_export_step(game),
                    false,
                ))
            })?;
        let to_date = invocation.local_date();
        let from_date = to_date - Duration::days(i64::from(self.config.days));
        let refresh_official_banners = !self.fixture_sources.contains_key(&game);
        let task = ExportTaskV1 {
            game,
            modes: settings.modes.clone(),
            from_date,
            to_date,
            output_root: settings.output.clone(),
            repo_id: settings.repo_id.clone(),
            revision: settings.revision.clone(),
            features: FeatureFlags {
                hf_teams: true,
                prydwen_visible: true,
                prydwen_tier: true,
                official_names: true,
            },
            prydwen_top_n: settings.prydwen_top_n,
            name_map_seed: None,
            refresh_official_banners,
            source: self
                .fixture_sources
                .get(&game)
                .map(|(root, supplemental_root)| ExportSourceV1::Fixture {
                    root: root.clone(),
                    supplemental_root: supplemental_root.clone(),
                })
                .unwrap_or_else(|| ExportSourceV1::OnlineHfFreshnessRequired {
                    cache_root: export_cache_root(
                        &context.workspace.join(".miho").join("cache").join("rust"),
                        game,
                        &settings.repo_id,
                        &settings.revision,
                    ),
                    hf_origin: self.hf_origins.get(&game).cloned(),
                }),
        };
        let export_observer = NativeUpdateExportObserverV1 { observer };
        let result = if game == Game::Zzz {
            let hsr_directory = self
                .config
                .hsr
                .output
                .file_name()
                .and_then(|value| value.to_str())
                .ok_or_else(|| {
                    UpdateStepExecutionErrorV1::Failure(safe_step_failure(
                        game_export_step(game),
                        false,
                    ))
                })?;
            execute_export_observed_with_hub_v1(&task, &invocation, &export_observer, hsr_directory)
                .await
        } else {
            execute_export_observed_v1(&task, &invocation, &export_observer).await
        };
        let receipt = match result {
            Ok(receipt) => receipt,
            Err(error) if is_execution_cancelled(&error) => {
                return Err(UpdateStepExecutionErrorV1::Control(
                    ExecutionControlError::Cancelled,
                ))
            }
            Err(error) if is_cache_fallback_error(&error) => {
                return Err(UpdateStepExecutionErrorV1::Failure(cache_fallback_failure(
                    game_export_step(game),
                )))
            }
            Err(error) if is_data_quality_freshness_error(&error) => {
                return Err(UpdateStepExecutionErrorV1::Failure(
                    update_freshness_failure_v1(),
                ))
            }
            Err(_) => {
                return Err(UpdateStepExecutionErrorV1::Failure(safe_step_failure(
                    game_export_step(game),
                    true,
                )))
            }
        };
        if receipt
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.code == diagnostic_code::SUPPLEMENTAL_CACHE_FALLBACK)
        {
            return Err(UpdateStepExecutionErrorV1::Failure(
                supplemental_cache_fallback_failure(game_export_step(game)),
            ));
        }
        if receipt
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.code != diagnostic_code::WORKBOOK_GENERATION_FAILED)
        {
            return Err(UpdateStepExecutionErrorV1::Failure(
                UpdateStepFailureV1::safe(
                    format!("update.{}.degraded", step_code(game_export_step(game))),
                    format!(
                        "the {} step completed with incomplete source diagnostics",
                        step_code(game_export_step(game))
                    ),
                    true,
                ),
            ));
        }
        collect_export_artifacts(&context.workspace, &settings.output, game).map_err(|_| {
            UpdateStepExecutionErrorV1::Failure(safe_artifact_failure(game_export_step(game)))
        })
    }

    fn execute_report(
        &self,
        step: UpdateStepKindV1,
        context: &UpdateStepContextV1,
        observer: Option<&dyn ExecutionObserver>,
    ) -> Result<Vec<UpdateArtifactV1>, UpdateStepExecutionErrorV1> {
        let invocation = AppInvocation::new(context.workspace.clone(), context.local_datetime())
            .map_err(|_| UpdateStepExecutionErrorV1::Failure(safe_step_failure(step, false)))?;
        let workspace = WorkspaceLayout {
            data_dir: self.config.zzz.export.output.clone(),
            box_path: self.config.zzz.box_path.clone(),
        };
        let refreshed_plan = self.config.zzz.export.output.join("zzz_banner_plan.json");
        let plan_path = match fs::symlink_metadata(&refreshed_plan) {
            Ok(metadata) if metadata.is_file() && !metadata.file_type().is_symlink() => {
                refreshed_plan
            }
            _ => self.config.zzz.banner_plan.clone(),
        };
        let task = match step {
            UpdateStepKindV1::ZzzCoverage => TaskSpecV1::Coverage(CoverageTaskV1 {
                planned_slugs: Vec::new(),
                plan_path: Some(plan_path.clone()),
                plan_statuses: vec!["current".to_owned(), "next".to_owned()],
                limit: 0,
                min_a_app_rate: "10.0".to_owned(),
                current_output: None,
                target_output: None,
                aggregate_output: None,
            }),
            UpdateStepKindV1::ZzzPullValue | UpdateStepKindV1::ZzzReviewPacket => {
                let task = PullTaskV1 {
                    plan_path,
                    plan_statuses: vec!["current".to_owned(), "next".to_owned()],
                    planned_slugs: Vec::new(),
                    mechanism_notes_dir: Some(self.config.zzz.mechanism_notes.clone()),
                    decision_baseline_path: self.config.zzz.decision_baseline.clone(),
                    output: None,
                };
                if step == UpdateStepKindV1::ZzzPullValue {
                    TaskSpecV1::PullValue(task)
                } else {
                    TaskSpecV1::ReviewPacket(task)
                }
            }
            _ => {
                return Err(UpdateStepExecutionErrorV1::Failure(safe_step_failure(
                    step, false,
                )))
            }
        };
        let request = TaskRequestV1::new(workspace, task);
        let result = if let Some(observer) = observer {
            execute_task_observed_v1(&request, &invocation, observer)
        } else {
            execute_task_observed_v1(&request, &invocation, &DirectUpdateExecutionObserverV1)
        };
        let receipt = result.map_err(|error| {
            if is_execution_cancelled(&error) {
                UpdateStepExecutionErrorV1::Control(ExecutionControlError::Cancelled)
            } else {
                UpdateStepExecutionErrorV1::Failure(safe_step_failure(step, true))
            }
        })?;
        collect_output_artifacts(&context.workspace, &receipt.outputs)
            .map_err(|_| UpdateStepExecutionErrorV1::Failure(safe_artifact_failure(step)))
    }
}

struct NativeUpdateExportObserverV1<'a> {
    observer: Option<&'a dyn ExecutionObserver>,
}

impl ExportObserver for NativeUpdateExportObserverV1<'_> {
    fn before_commit(&self) -> Result<(), ExecutionControlError> {
        self.observer
            .map_or(Ok(()), ExecutionObserver::before_commit)
    }
}

struct DirectUpdateExecutionObserverV1;

impl ExecutionObserver for DirectUpdateExecutionObserverV1 {
    fn before_commit(&self) -> Result<(), ExecutionControlError> {
        Ok(())
    }
}

#[cfg(debug_assertions)]
fn wait_for_debug_update_gate() -> Result<(), UpdateStepFailureV1> {
    use std::{thread, time::Instant};

    let Some(path) = std::env::var_os("MIHO_UPDATE_TEST_PAUSE_FILE").map(PathBuf::from) else {
        return Ok(());
    };
    let deadline = Instant::now() + std::time::Duration::from_secs(30);
    while path.exists() {
        if Instant::now() >= deadline {
            return Err(UpdateStepFailureV1::safe(
                "update.debug_pause_timeout",
                "the debug update synchronization gate timed out",
                true,
            ));
        }
        thread::sleep(std::time::Duration::from_millis(5));
    }
    Ok(())
}

fn game_export_step(game: Game) -> UpdateStepKindV1 {
    match game {
        Game::Hsr => UpdateStepKindV1::HsrExport,
        Game::Zzz => UpdateStepKindV1::ZzzExport,
    }
}

fn safe_step_failure(step: UpdateStepKindV1, retryable: bool) -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        format!("update.{}.failed", step_code(step)),
        format!("the {} step failed", step_code(step)),
        retryable,
    )
}

fn cancelled_step_failure() -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        "task.cancelled",
        "the update was cancelled before its first output commit",
        true,
    )
}

fn is_execution_cancelled(error: &anyhow::Error) -> bool {
    error.chain().any(|cause| {
        cause
            .downcast_ref::<ExecutionControlError>()
            .is_some_and(|control| *control == ExecutionControlError::Cancelled)
    })
}

fn safe_artifact_failure(step: UpdateStepKindV1) -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        format!("update.{}.artifacts_invalid", step_code(step)),
        format!("the {} artifacts failed verification", step_code(step)),
        true,
    )
}

fn cache_fallback_failure(step: UpdateStepKindV1) -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        format!("update.{}.cache_fallback", step_code(step)),
        format!("the {} step used a cache fallback", step_code(step)),
        true,
    )
}

fn supplemental_cache_fallback_failure(step: UpdateStepKindV1) -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        format!("update.{}.supplemental_cache_fallback", step_code(step)),
        format!(
            "the {} step used a supplemental cache fallback",
            step_code(step)
        ),
        true,
    )
}

fn is_cache_fallback_error(error: &anyhow::Error) -> bool {
    error.chain().any(|cause| {
        matches!(
            cause.downcast_ref::<MihoError>(),
            Some(MihoError::CacheFallbackRejected(_))
        ) || cause
            .to_string()
            .to_ascii_lowercase()
            .contains("cache fallback")
    })
}

fn is_data_quality_freshness_error(error: &anyhow::Error) -> bool {
    error.chain().any(|cause| {
        matches!(
            cause.downcast_ref::<MihoError>(),
            Some(MihoError::DataQualityFreshness(_))
        )
    })
}

fn is_cache_fallback_code(code: &str) -> bool {
    (code.starts_with("update.") && code.ends_with(".cache_fallback"))
        || is_supplemental_cache_fallback_code(code)
}

fn is_supplemental_cache_fallback_code(code: &str) -> bool {
    code.starts_with("update.") && code.ends_with(".supplemental_cache_fallback")
}

fn step_code(step: UpdateStepKindV1) -> &'static str {
    match step {
        UpdateStepKindV1::HsrExport => "hsr_export",
        UpdateStepKindV1::ZzzExport => "zzz_export",
        UpdateStepKindV1::ZzzCoverage => "zzz_coverage",
        UpdateStepKindV1::ZzzPullValue => "zzz_pull_value",
        UpdateStepKindV1::ZzzReviewPacket => "zzz_review_packet",
    }
}

fn collect_export_artifacts(
    workspace: &Path,
    output: &Path,
    game: Game,
) -> anyhow::Result<Vec<UpdateArtifactV1>> {
    let manifest_path = output.join("artifact_manifest.json");
    let entries: Vec<ArtifactManifestEntry> = serde_json::from_slice(&fs::read(&manifest_path)?)?;
    if entries.is_empty() {
        anyhow::bail!("export manifest is empty");
    }
    let mut outputs = Vec::with_capacity(entries.len() + 4);
    for entry in entries {
        let path = output.join(&entry.path);
        let relative = workspace_relative(workspace, &path)?;
        let metadata = fs::metadata(&path)?;
        if !metadata.is_file() || metadata.len() != entry.bytes as u64 {
            anyhow::bail!("export artifact metadata does not match manifest");
        }
        outputs.push(UpdateArtifactV1 {
            path: relative,
            bytes: metadata.len(),
            sha256: entry.sha256,
        });
    }
    outputs.push(file_artifact(workspace, &manifest_path)?);
    if game == Game::Zzz {
        let hub = workspace.join("visualizer");
        for name in ["index.html", "app.js", "styles.css"] {
            outputs.push(file_artifact(workspace, &hub.join(name))?);
        }
    }
    Ok(outputs)
}

fn collect_output_artifacts(
    workspace: &Path,
    outputs: &[PathBuf],
) -> anyhow::Result<Vec<UpdateArtifactV1>> {
    outputs
        .iter()
        .map(|path| file_artifact(workspace, path))
        .collect()
}

fn file_artifact(workspace: &Path, path: &Path) -> anyhow::Result<UpdateArtifactV1> {
    let metadata = fs::metadata(path)?;
    if !metadata.is_file() {
        anyhow::bail!("update artifact is not a regular file");
    }
    Ok(UpdateArtifactV1 {
        path: workspace_relative(workspace, path)?,
        bytes: metadata.len(),
        // The single trusted full-file read happens in `validate_artifacts`,
        // which fills this digest before a receipt can succeed.
        sha256: String::new(),
    })
}

fn workspace_relative(workspace: &Path, path: &Path) -> anyhow::Result<PathBuf> {
    let relative = path.strip_prefix(workspace)?;
    if !safe_relative_path(relative) {
        anyhow::bail!("update artifact path is not workspace-relative");
    }
    Ok(relative.to_path_buf())
}

fn hash_file_with_optional_csv_rows(
    path: &Path,
    count_csv_rows: bool,
) -> anyhow::Result<(String, u64, Option<u64>)> {
    #[cfg(test)]
    ARTIFACT_HASH_PASSES_V1.fetch_add(1, Ordering::SeqCst);
    let mut file = open_artifact_for_trusted_read(path)?;
    let metadata_before = file.metadata()?;
    if !metadata_before.is_file() {
        anyhow::bail!("update artifact is not a regular file");
    }
    let mut hasher = Sha256::new();
    let mut csv_rows = count_csv_rows.then(CsvRowCounterV1::default);
    let mut byte_count = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        byte_count = byte_count
            .checked_add(read as u64)
            .ok_or_else(|| anyhow::anyhow!("artifact byte count overflow"))?;
        hasher.update(&buffer[..read]);
        if let Some(counter) = csv_rows.as_mut() {
            counter.push(&buffer[..read]);
        }
    }
    let metadata_after = file.metadata()?;
    if !metadata_after.is_file()
        || metadata_before.len() != metadata_after.len()
        || metadata_after.len() != byte_count
    {
        anyhow::bail!("update artifact changed during trusted read");
    }
    Ok((
        format!("{:x}", hasher.finalize()),
        byte_count,
        csv_rows.map(CsvRowCounterV1::data_rows),
    ))
}

fn open_artifact_for_trusted_read(path: &Path) -> std::io::Result<File> {
    #[cfg(windows)]
    {
        use std::fs::OpenOptions;
        use std::os::windows::fs::OpenOptionsExt;
        use windows_sys::Win32::Storage::FileSystem::FILE_SHARE_READ;

        // Keep the exact file immutable for the lifetime of the hash/read:
        // other readers may coexist, but writers, replacements, and deletes
        // cannot acquire a compatible Windows handle.
        OpenOptions::new()
            .read(true)
            .share_mode(FILE_SHARE_READ)
            .open(path)
    }
    #[cfg(not(windows))]
    {
        File::open(path)
    }
}

#[derive(Debug, Default)]
struct CsvRowCounterV1 {
    in_quotes: bool,
    records: u64,
    saw_any: bool,
    ended_at_record_boundary: bool,
}

impl CsvRowCounterV1 {
    fn push(&mut self, bytes: &[u8]) {
        for &byte in bytes {
            self.saw_any = true;
            if byte == b'"' {
                // A doubled quote toggles twice and therefore preserves the
                // quoted state. Exported CSV is RFC-style and never uses a
                // bare quote inside an unquoted field.
                self.in_quotes = !self.in_quotes;
                self.ended_at_record_boundary = false;
            } else if byte == b'\n' && !self.in_quotes {
                self.records = self.records.saturating_add(1);
                self.ended_at_record_boundary = true;
            } else if byte != b'\r' {
                self.ended_at_record_boundary = false;
            }
        }
    }

    fn data_rows(mut self) -> u64 {
        if self.saw_any && !self.ended_at_record_boundary {
            self.records = self.records.saturating_add(1);
        }
        self.records.saturating_sub(1)
    }
}

pub trait UpdateReceiptStore: Send + Sync {
    fn recover_interrupted(
        &self,
        _workspace: &Path,
        _current_attempt_id: &str,
    ) -> Result<(), UpdateStepFailureV1> {
        Ok(())
    }
    fn load_state(&self, workspace: &Path) -> Result<UpdateStateV1, UpdateStepFailureV1>;
    fn write_running(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1>;
    fn commit_success(
        &self,
        workspace: &Path,
        state: &UpdateStateV1,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1>;
    fn commit_failure(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1>;
    /// Terminalize only this attempt's journal entry after cancellation. The
    /// previously committed state and canonical receipt must remain intact.
    fn commit_interrupted(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1>;
}

#[derive(Debug, Default)]
pub struct FileUpdateReceiptStore;

impl UpdateReceiptStore for FileUpdateReceiptStore {
    fn recover_interrupted(
        &self,
        workspace: &Path,
        current_attempt_id: &str,
    ) -> Result<(), UpdateStepFailureV1> {
        let current_path = attempt_receipt_path(workspace, current_attempt_id);
        match verify_metadata_path(workspace, &current_path, false) {
            Ok(false) => {}
            Ok(true) => {
                return Err(UpdateStepFailureV1::safe(
                    "update.attempt_id_collision",
                    "the update attempt identifier already exists",
                    false,
                ))
            }
            Err(()) => return Err(receipt_history_failure()),
        }
        let directory = metadata_root(workspace).join(UPDATE_ATTEMPT_DIRECTORY);
        match verify_metadata_path(workspace, &directory, true) {
            Ok(true) => {}
            Ok(false) => return Ok(()),
            Err(()) => return Err(receipt_history_failure()),
        }
        let entries = match fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(_) => return Err(receipt_history_failure()),
        };
        let mut replacements = Vec::new();
        for entry in entries {
            let entry = entry.map_err(|_| receipt_history_failure())?;
            let metadata =
                fs::symlink_metadata(entry.path()).map_err(|_| receipt_history_failure())?;
            if metadata.file_type().is_symlink()
                || is_windows_reparse(&metadata)
                || !metadata.is_file()
                || entry.path().extension().and_then(|value| value.to_str()) != Some("json")
            {
                return Err(receipt_history_failure());
            }
            let mut receipt = serde_json::from_slice::<UpdateReceiptV1>(
                &fs::read(entry.path()).map_err(|_| receipt_history_failure())?,
            )
            .map_err(|_| receipt_history_failure())?;
            if receipt.schema_version != UPDATE_RECEIPT_SCHEMA_V1 {
                return Err(receipt_history_failure());
            }
            if receipt.attempt_id != current_attempt_id
                && receipt.status == UpdateRunStatusV1::Running
            {
                receipt.status = UpdateRunStatusV1::Interrupted;
                receipt.finished_at_utc = Some(now_utc_text());
                receipt.state_committed = false;
                // Only the per-attempt history entry is replaced here. The
                // canonical receipt remains owned by its original terminal
                // attempt, so claiming a canonical commit would be false.
                receipt.receipt_committed = false;
                receipt.failure = Some(UpdateStepFailureV1::safe(
                    "update.interrupted",
                    "the previous update attempt was interrupted",
                    true,
                ));
                stabilize_receipt_steps(&mut receipt);
                replacements.push((entry.path(), json_bytes(&receipt)?));
            }
        }
        if replacements.is_empty() {
            return Ok(());
        }
        atomic::write_batch(&replacements).map_err(|_| receipt_history_failure())
    }

    fn load_state(&self, workspace: &Path) -> Result<UpdateStateV1, UpdateStepFailureV1> {
        let path = metadata_root(workspace).join(UPDATE_STATE_FILE);
        match verify_metadata_path(workspace, &path, false) {
            Ok(true) => {}
            Ok(false) => return Ok(UpdateStateV1::default()),
            Err(()) => {
                return Err(UpdateStepFailureV1::safe(
                    "update.state_path_unsafe",
                    "the previous update state path is unsafe",
                    false,
                ))
            }
        }
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Ok(UpdateStateV1::default())
            }
            Err(_) => {
                return Err(UpdateStepFailureV1::safe(
                    "update.state_read_failed",
                    "the previous update state could not be read",
                    false,
                ))
            }
        };
        let state = serde_json::from_slice::<UpdateStateV1>(&bytes).map_err(|_| {
            UpdateStepFailureV1::safe(
                "update.state_invalid",
                "the previous update state is invalid",
                false,
            )
        })?;
        if state.schema_version != UPDATE_STATE_SCHEMA_V1 {
            return Err(UpdateStepFailureV1::safe(
                "update.state_unsupported",
                "the previous update state schema is unsupported",
                false,
            ));
        }
        Ok(state)
    }

    fn write_running(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        let path = attempt_receipt_path(workspace, &receipt.attempt_id);
        match verify_metadata_path(workspace, &path, false) {
            Ok(false) => {}
            Ok(true) => {
                return Err(UpdateStepFailureV1::safe(
                    "update.attempt_id_collision",
                    "the update attempt identifier already exists",
                    false,
                ))
            }
            Err(()) => {
                return Err(UpdateStepFailureV1::safe(
                    "update.attempt_path_unsafe",
                    "the update attempt receipt path is unsafe",
                    false,
                ))
            }
        }
        atomic::write(&path, &json_bytes(receipt)?).map_err(|_| receipt_write_failure())
    }

    fn commit_success(
        &self,
        workspace: &Path,
        state: &UpdateStateV1,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        let root = metadata_root(workspace);
        atomic::write_batch(&[
            (root.join(UPDATE_STATE_FILE), json_bytes(state)?),
            (
                attempt_receipt_path(workspace, &receipt.attempt_id),
                json_bytes(receipt)?,
            ),
            (
                root.join(UPDATE_CANONICAL_RECEIPT_FILE),
                json_bytes(receipt)?,
            ),
        ])
        .map_err(|_| state_commit_failure())
    }

    fn commit_failure(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        let root = metadata_root(workspace);
        atomic::write_batch(&[
            (
                attempt_receipt_path(workspace, &receipt.attempt_id),
                json_bytes(receipt)?,
            ),
            (
                root.join(UPDATE_CANONICAL_RECEIPT_FILE),
                json_bytes(receipt)?,
            ),
        ])
        .map_err(|_| receipt_write_failure())
    }

    fn commit_interrupted(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        atomic::write(
            &attempt_receipt_path(workspace, &receipt.attempt_id),
            &json_bytes(receipt)?,
        )
        .map_err(|_| receipt_write_failure())
    }
}

fn metadata_root(workspace: &Path) -> PathBuf {
    workspace.join(".miho")
}

fn attempt_receipt_path(workspace: &Path, attempt_id: &str) -> PathBuf {
    metadata_root(workspace)
        .join(UPDATE_ATTEMPT_DIRECTORY)
        .join(format!("{attempt_id}.json"))
}

fn json_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, UpdateStepFailureV1> {
    let mut bytes = serde_json::to_vec_pretty(value).map_err(|_| {
        UpdateStepFailureV1::safe(
            "update.receipt_encode_failed",
            "the update receipt could not be encoded",
            false,
        )
    })?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn receipt_write_failure() -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        "update.receipt_write_failed",
        "the update receipt could not be committed",
        true,
    )
}

fn state_commit_failure() -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        "update.state_commit_failed",
        "the update success state could not be committed",
        true,
    )
}

fn receipt_history_failure() -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        "update.receipt_history_invalid",
        "the previous update attempt history is invalid",
        false,
    )
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UpdateRunOutcomeV1 {
    pub receipt: UpdateReceiptV1,
    pub exit_code: i32,
    /// Sanitized freshness captured from the exact committed state/artifact
    /// generation while the workspace write lease is still held. Every
    /// committed-success receipt has `Some`; `None` means the run did not
    /// reach a successful commit.
    pub freshness: Option<Result<BTreeMap<Game, TaskFreshnessSummaryV1>, UpdateStepFailureV1>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateHealthV1 {
    pub schema_version: String,
    pub healthy: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub attempt_id: Option<String>,
    pub checked_games: Vec<Game>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure: Option<UpdateStepFailureV1>,
}

pub fn check_update_health_v1(
    workspace: &Path,
    require_hsr: bool,
    require_zzz: bool,
    expected_config_sha256: &str,
) -> UpdateHealthV1 {
    check_update_health_with_state_v1(workspace, require_hsr, require_zzz, expected_config_sha256).0
}

/// Read health and the desktop-facing update state under one coherent shared
/// snapshot lease so callers cannot combine metadata from two generations. A busy writer is
/// returned as `workspace.write_busy`, allowing the UI to retry instead of
/// briefly reporting an artifact-integrity failure during a commit.
pub fn check_update_health_with_state_v1(
    workspace: &Path,
    require_hsr: bool,
    require_zzz: bool,
    expected_config_sha256: &str,
) -> (UpdateHealthV1, Result<UpdateStateV1, UpdateStepFailureV1>) {
    let (health, state, _) = check_update_health_snapshot_v1(
        workspace,
        require_hsr,
        require_zzz,
        expected_config_sha256,
        None,
    );
    (health, state)
}

/// Read verified health, update provenance, and sanitized per-mode freshness
/// while one shared snapshot lease pins all three views to the same committed
/// generation. The resolved config supplies only native, workspace-confined
/// output paths and is never exposed to the WebView.
pub fn check_update_health_with_state_and_freshness_v1(
    config: &ResolvedUpdateConfigV1,
    require_hsr: bool,
    require_zzz: bool,
    expected_config_sha256: &str,
) -> (
    UpdateHealthV1,
    Result<UpdateStateV1, UpdateStepFailureV1>,
    BTreeMap<Game, TaskFreshnessSummaryV1>,
) {
    check_update_health_snapshot_v1(
        &config.workspace,
        require_hsr,
        require_zzz,
        expected_config_sha256,
        Some(config),
    )
}

/// Load the canonical workspace update config, its digest, committed state,
/// and freshness evidence while one shared snapshot lease remains held. This
/// prevents a release/bootstrap writer from switching config and generation
/// between the desktop's config read and health verification.
pub fn check_update_health_with_workspace_config_and_freshness_v1(
    workspace: &Path,
    require_hsr: bool,
    require_zzz: bool,
) -> (
    UpdateHealthV1,
    Result<UpdateStateV1, UpdateStepFailureV1>,
    BTreeMap<Game, TaskFreshnessSummaryV1>,
) {
    check_update_health_with_workspace_config_path_and_freshness_v1(
        workspace,
        Path::new(DEFAULT_UPDATE_CONFIG_RELATIVE_PATH_V1),
        require_hsr,
        require_zzz,
    )
}

/// Load one caller-selected, workspace-relative update config and verify the
/// committed state, receipts, artifacts, and freshness evidence under the
/// same shared snapshot lease. Keeping the config read inside the lease means
/// automation cannot approve freshness using config bytes from a different
/// generation.
pub fn check_update_health_with_workspace_config_path_and_freshness_v1(
    workspace: &Path,
    config_relative: &Path,
    require_hsr: bool,
    require_zzz: bool,
) -> (
    UpdateHealthV1,
    Result<UpdateStateV1, UpdateStepFailureV1>,
    BTreeMap<Game, TaskFreshnessSummaryV1>,
) {
    check_update_health_with_config_loader_v1(
        workspace,
        require_hsr,
        require_zzz,
        |snapshot_root| {
            if !safe_relative_path(config_relative) {
                return Err(update_health_config_failure_v1());
            }
            // Use the caller's already validated spelling for the file open.
            // On Windows, `canonicalize` may add a verbatim-path prefix that
            // strict component-by-component config validation intentionally
            // does not accept. Resolution still uses the canonical root held
            // by the snapshot lease.
            let config_path = workspace.join(config_relative);
            let loaded = crate::load_update_config_with_digest_v1(&config_path)
                .map_err(|_| update_health_config_failure_v1())?;
            let config = loaded
                .config
                .resolve(snapshot_root)
                .map_err(|_| update_health_config_failure_v1())?;
            Ok((config, loaded.sha256))
        },
    )
}

fn check_update_health_with_config_loader_v1<F>(
    workspace: &Path,
    require_hsr: bool,
    require_zzz: bool,
    load_config: F,
) -> (
    UpdateHealthV1,
    Result<UpdateStateV1, UpdateStepFailureV1>,
    BTreeMap<Game, TaskFreshnessSummaryV1>,
)
where
    F: FnOnce(&Path) -> Result<(ResolvedUpdateConfigV1, String), UpdateStepFailureV1>,
{
    let checked_games = requested_health_games_v1(require_hsr, require_zzz);
    let lease = match WorkspaceSnapshotLease::acquire(workspace) {
        Ok(lease) => lease,
        Err(error) => {
            let failure = lease_failure(error);
            return (
                unhealthy(checked_games, None, failure.clone()),
                Err(failure),
                BTreeMap::new(),
            );
        }
    };
    let snapshot_root = lease.workspace_root();
    let result = match load_config(snapshot_root) {
        Ok((config, config_sha256)) => check_update_health_snapshot_locked_v1(
            snapshot_root,
            checked_games,
            &config_sha256,
            Some(&config),
        ),
        Err(failure) => {
            let state = FileUpdateReceiptStore.load_state(snapshot_root);
            (
                unhealthy(checked_games, None, failure),
                state,
                BTreeMap::new(),
            )
        }
    };
    drop(lease);
    result
}

fn check_update_health_snapshot_v1(
    workspace: &Path,
    require_hsr: bool,
    require_zzz: bool,
    expected_config_sha256: &str,
    freshness_config: Option<&ResolvedUpdateConfigV1>,
) -> (
    UpdateHealthV1,
    Result<UpdateStateV1, UpdateStepFailureV1>,
    BTreeMap<Game, TaskFreshnessSummaryV1>,
) {
    let checked_games = requested_health_games_v1(require_hsr, require_zzz);
    let lease = match WorkspaceSnapshotLease::acquire(workspace) {
        Ok(lease) => lease,
        Err(error) => {
            let failure = lease_failure(error);
            return (
                unhealthy(checked_games, None, failure.clone()),
                Err(failure),
                BTreeMap::new(),
            );
        }
    };
    let workspace = lease.workspace_root();
    let result = check_update_health_snapshot_locked_v1(
        workspace,
        checked_games,
        expected_config_sha256,
        freshness_config,
    );
    drop(lease);
    result
}

fn check_update_health_snapshot_locked_v1(
    workspace: &Path,
    checked_games: Vec<Game>,
    expected_config_sha256: &str,
    freshness_config: Option<&ResolvedUpdateConfigV1>,
) -> (
    UpdateHealthV1,
    Result<UpdateStateV1, UpdateStepFailureV1>,
    BTreeMap<Game, TaskFreshnessSummaryV1>,
) {
    let state = FileUpdateReceiptStore.load_state(workspace);
    let mut health =
        check_update_health_locked_v1(workspace, checked_games, expected_config_sha256, &state);
    let freshness = if health.healthy {
        match (freshness_config, state.as_ref()) {
            (Some(config), Ok(state)) => {
                let freshness =
                    load_generation_dates_locked_v1(workspace, &health.checked_games, state)
                        .and_then(|generation_dates| {
                            load_update_freshness_locked_v1(
                                workspace,
                                &health.checked_games,
                                config,
                                state,
                                &generation_dates,
                            )
                        });
                match freshness {
                    Ok(freshness) => freshness,
                    Err(failure) => {
                        health.healthy = false;
                        health.failure = Some(failure);
                        BTreeMap::new()
                    }
                }
            }
            (None, _) => BTreeMap::new(),
            (Some(_), Err(failure)) => {
                health.healthy = false;
                health.failure = Some(failure.clone());
                BTreeMap::new()
            }
        }
    } else {
        BTreeMap::new()
    };
    (health, state, freshness)
}

fn requested_health_games_v1(require_hsr: bool, require_zzz: bool) -> Vec<Game> {
    [
        require_hsr.then_some(Game::Hsr),
        require_zzz.then_some(Game::Zzz),
    ]
    .into_iter()
    .flatten()
    .collect()
}

fn update_health_config_failure_v1() -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        "update.health_config_invalid",
        "the update health configuration is unavailable or invalid",
        false,
    )
}

fn load_update_freshness_locked_v1(
    workspace: &Path,
    checked_games: &[Game],
    config: &ResolvedUpdateConfigV1,
    state: &UpdateStateV1,
    generation_dates: &BTreeMap<Game, NaiveDate>,
) -> Result<BTreeMap<Game, TaskFreshnessSummaryV1>, UpdateStepFailureV1> {
    if config.workspace != workspace {
        return Err(update_freshness_failure_v1());
    }
    let mut freshness = BTreeMap::new();
    for game in checked_games {
        let (output_root, expected_modes) = match game {
            Game::Hsr => (&config.hsr.output, &config.hsr.modes),
            Game::Zzz => (&config.zzz.export.output, &config.zzz.export.modes),
        };
        let generation_date = generation_dates
            .get(game)
            .copied()
            .ok_or_else(update_freshness_failure_v1)?;
        let path = output_root.join("data_quality.json");
        let relative = path
            .strip_prefix(workspace)
            .map_err(|_| update_freshness_failure_v1())?;
        if !safe_relative_path(relative)
            || verify_metadata_path(workspace, &path, false) != Ok(true)
        {
            return Err(update_freshness_failure_v1());
        }
        let artifact = state
            .games
            .get(game)
            .and_then(|game_state| {
                game_state
                    .artifacts
                    .iter()
                    .find(|artifact| artifact.path == relative)
            })
            .ok_or_else(update_freshness_failure_v1)?;
        if artifact.bytes > MAX_UPDATE_FRESHNESS_BYTES_V1 || !valid_sha256(&artifact.sha256) {
            return Err(update_freshness_failure_v1());
        }
        let mut file =
            open_artifact_for_trusted_read(&path).map_err(|_| update_freshness_failure_v1())?;
        let metadata_before = file.metadata().map_err(|_| update_freshness_failure_v1())?;
        if !metadata_before.is_file() || metadata_before.len() != artifact.bytes {
            return Err(update_freshness_failure_v1());
        }
        let mut bytes = Vec::with_capacity(artifact.bytes as usize);
        file.read_to_end(&mut bytes)
            .map_err(|_| update_freshness_failure_v1())?;
        let metadata_after = file.metadata().map_err(|_| update_freshness_failure_v1())?;
        if metadata_after.len() != metadata_before.len()
            || bytes.len() as u64 != artifact.bytes
            || format!("{:x}", Sha256::digest(&bytes)) != artifact.sha256
        {
            return Err(update_freshness_failure_v1());
        }
        let report = serde_json::from_slice::<DataQualityReportV1>(&bytes)
            .map_err(|_| update_freshness_failure_v1())?;
        validate_data_quality_report_v1(&report, *game, expected_modes, generation_date)
            .map_err(|_| update_freshness_failure_v1())?;
        freshness.insert(*game, TaskFreshnessSummaryV1::from(&report));
    }
    Ok(freshness)
}

fn load_generation_dates_locked_v1(
    workspace: &Path,
    checked_games: &[Game],
    state: &UpdateStateV1,
) -> Result<BTreeMap<Game, NaiveDate>, UpdateStepFailureV1> {
    let mut generation_dates = BTreeMap::new();
    for game in checked_games {
        let game_state = state
            .games
            .get(game)
            .ok_or_else(update_freshness_failure_v1)?;
        let receipt = read_attempt_receipt(workspace, &game_state.attempt_id)
            .map_err(|_| update_freshness_failure_v1())?;
        let game_receipt = receipt
            .games
            .iter()
            .find(|candidate| candidate.game == *game && candidate.selected)
            .ok_or_else(update_freshness_failure_v1)?;
        let receipt_artifacts = game_receipt
            .steps
            .iter()
            .flat_map(|step| step.artifacts.clone())
            .collect::<Vec<_>>();
        if receipt.status != UpdateRunStatusV1::Succeeded
            || !receipt.state_committed
            || !receipt.receipt_committed
            || receipt.attempt_id != game_state.attempt_id
            || receipt.config_sha256.as_deref() != Some(game_state.config_sha256.as_str())
            || game_receipt.status != UpdateStepStatusV1::Succeeded
            || game_receipt
                .steps
                .iter()
                .any(|step| step.status != UpdateStepStatusV1::Succeeded)
            || receipt_artifacts != game_state.artifacts
        {
            return Err(update_freshness_failure_v1());
        }
        generation_dates.insert(*game, generation_local_date_v1(&receipt)?);
    }
    Ok(generation_dates)
}

fn generation_local_date_v1(receipt: &UpdateReceiptV1) -> Result<NaiveDate, UpdateStepFailureV1> {
    let parsed =
        NaiveDateTime::parse_from_str(&receipt.invocation_local_datetime, "%Y-%m-%dT%H:%M:%S%.6f")
            .map_err(|_| update_freshness_failure_v1())?;
    if parsed.format("%Y-%m-%dT%H:%M:%S%.6f").to_string() != receipt.invocation_local_datetime {
        return Err(update_freshness_failure_v1());
    }
    Ok(parsed.date())
}

fn load_committed_attempt_freshness_locked_v1(
    workspace: &Path,
    receipt: &UpdateReceiptV1,
    config: &ResolvedUpdateConfigV1,
    state: &UpdateStateV1,
) -> Result<BTreeMap<Game, TaskFreshnessSummaryV1>, UpdateStepFailureV1> {
    let Some(config_sha256) = receipt.config_sha256.as_deref() else {
        return Err(update_freshness_failure_v1());
    };
    if receipt.status != UpdateRunStatusV1::Succeeded
        || !receipt.state_committed
        || !receipt.receipt_committed
        || !valid_sha256(config_sha256)
    {
        return Err(update_freshness_failure_v1());
    }

    let checked_games = receipt
        .games
        .iter()
        .filter(|game| game.selected)
        .map(|game| game.game)
        .collect::<Vec<_>>();
    if checked_games.is_empty() {
        return Err(update_freshness_failure_v1());
    }

    for game in &checked_games {
        let game_receipt = receipt
            .games
            .iter()
            .find(|candidate| candidate.game == *game && candidate.selected)
            .ok_or_else(update_freshness_failure_v1)?;
        let game_state = state
            .games
            .get(game)
            .ok_or_else(update_freshness_failure_v1)?;
        let receipt_artifacts = game_receipt
            .steps
            .iter()
            .flat_map(|step| step.artifacts.clone())
            .collect::<Vec<_>>();
        if game_receipt.status != UpdateStepStatusV1::Succeeded
            || game_receipt
                .steps
                .iter()
                .any(|step| step.status != UpdateStepStatusV1::Succeeded)
            || game_state.attempt_id != receipt.attempt_id
            || game_state.config_sha256 != config_sha256
            || game_state.artifacts != receipt_artifacts
        {
            return Err(update_freshness_failure_v1());
        }
    }

    let generation_date = generation_local_date_v1(receipt)?;
    let generation_dates = checked_games
        .iter()
        .copied()
        .map(|game| (game, generation_date))
        .collect::<BTreeMap<_, _>>();
    load_update_freshness_locked_v1(workspace, &checked_games, config, state, &generation_dates)
}

fn update_freshness_failure_v1() -> UpdateStepFailureV1 {
    health_artifact_failure("update.health_freshness_invalid")
}

fn check_update_health_locked_v1(
    workspace: &Path,
    checked_games: Vec<Game>,
    expected_config_sha256: &str,
    state: &Result<UpdateStateV1, UpdateStepFailureV1>,
) -> UpdateHealthV1 {
    if checked_games.is_empty() {
        return unhealthy(
            checked_games,
            None,
            UpdateStepFailureV1::safe(
                "update.health_no_games",
                "no game was selected for update health verification",
                false,
            ),
        );
    }
    if !valid_sha256(expected_config_sha256) {
        return unhealthy(
            checked_games,
            None,
            UpdateStepFailureV1::safe(
                "update.health_config_invalid",
                "the expected update configuration identity is invalid",
                false,
            ),
        );
    }
    let receipt = match read_canonical_receipt(workspace) {
        Ok(receipt) => receipt,
        Err(failure) => return unhealthy(checked_games, None, failure),
    };
    let attempt_id = Some(receipt.attempt_id.clone());
    if receipt.status != UpdateRunStatusV1::Succeeded
        || !receipt.state_committed
        || !receipt.receipt_committed
    {
        return unhealthy(
            checked_games,
            attempt_id,
            UpdateStepFailureV1::safe(
                "update.health_not_succeeded",
                "the latest update receipt is not a committed success",
                true,
            ),
        );
    }
    if receipt.config_sha256.as_deref() != Some(expected_config_sha256) {
        return unhealthy(
            checked_games,
            attempt_id,
            health_artifact_failure("update.health_config_mismatch"),
        );
    }
    let canonical_attempt = match read_attempt_receipt(workspace, &receipt.attempt_id) {
        Ok(attempt) if attempt == receipt => attempt,
        Ok(_) | Err(_) => {
            return unhealthy(
                checked_games,
                attempt_id,
                UpdateStepFailureV1::safe(
                    "update.health_receipt_invalid",
                    "the canonical update receipt is invalid",
                    false,
                ),
            )
        }
    };
    debug_assert_eq!(canonical_attempt, receipt);
    let state = match state {
        Ok(state) => state,
        Err(failure) => return unhealthy(checked_games, attempt_id, failure.clone()),
    };
    for game in &checked_games {
        let Some(game_state) = state.games.get(game) else {
            return unhealthy(
                checked_games.clone(),
                attempt_id.clone(),
                health_artifact_failure("update.health_state_missing"),
            );
        };
        if game_state.config_sha256 != expected_config_sha256 {
            return unhealthy(
                checked_games.clone(),
                attempt_id.clone(),
                health_artifact_failure("update.health_config_mismatch"),
            );
        }
        let generation_receipt = match read_attempt_receipt(workspace, &game_state.attempt_id) {
            Ok(receipt) => receipt,
            Err(failure) => return unhealthy(checked_games.clone(), attempt_id.clone(), failure),
        };
        let Some(game_receipt) = generation_receipt.games.iter().find(|receipt_game| {
            receipt_game.game == *game
                && receipt_game.selected
                && receipt_game.status == UpdateStepStatusV1::Succeeded
        }) else {
            return unhealthy(
                checked_games.clone(),
                attempt_id.clone(),
                health_artifact_failure("update.health_generation_mismatch"),
            );
        };
        if generation_receipt.status != UpdateRunStatusV1::Succeeded
            || !generation_receipt.state_committed
            || !generation_receipt.receipt_committed
            || generation_receipt.attempt_id != game_state.attempt_id
            || generation_receipt.config_sha256.as_deref() != Some(expected_config_sha256)
            || generation_receipt.config_sha256.as_deref()
                != Some(game_state.config_sha256.as_str())
        {
            return unhealthy(
                checked_games.clone(),
                attempt_id.clone(),
                health_artifact_failure("update.health_generation_mismatch"),
            );
        }
        let receipt_artifacts = game_receipt
            .steps
            .iter()
            .flat_map(|step| step.artifacts.clone())
            .collect::<Vec<_>>();
        if receipt_artifacts != game_state.artifacts
            || validate_artifacts(workspace, game_state.artifacts.clone()).is_err()
        {
            return unhealthy(
                checked_games.clone(),
                attempt_id.clone(),
                health_artifact_failure("update.health_artifact_invalid"),
            );
        }
    }
    UpdateHealthV1 {
        schema_version: UPDATE_HEALTH_SCHEMA_V1.to_owned(),
        healthy: true,
        attempt_id,
        checked_games,
        failure: None,
    }
}

fn read_canonical_receipt(workspace: &Path) -> Result<UpdateReceiptV1, UpdateStepFailureV1> {
    let path = metadata_root(workspace).join(UPDATE_CANONICAL_RECEIPT_FILE);
    match verify_metadata_path(workspace, &path, false) {
        Ok(true) => {}
        Ok(false) => {
            return Err(UpdateStepFailureV1::safe(
                "update.health_receipt_missing",
                "the canonical update receipt is missing",
                true,
            ))
        }
        Err(()) => {
            return Err(UpdateStepFailureV1::safe(
                "update.health_receipt_invalid",
                "the canonical update receipt path is unsafe",
                false,
            ))
        }
    }
    let receipt = serde_json::from_slice::<UpdateReceiptV1>(&fs::read(&path).map_err(|_| {
        UpdateStepFailureV1::safe(
            "update.health_receipt_missing",
            "the canonical update receipt is missing",
            true,
        )
    })?)
    .map_err(|_| {
        UpdateStepFailureV1::safe(
            "update.health_receipt_invalid",
            "the canonical update receipt is invalid",
            false,
        )
    })?;
    if receipt.schema_version != UPDATE_RECEIPT_SCHEMA_V1 {
        return Err(UpdateStepFailureV1::safe(
            "update.health_receipt_unsupported",
            "the canonical update receipt schema is unsupported",
            false,
        ));
    }
    if !is_valid_update_attempt_id_v1(&receipt.attempt_id) {
        return Err(UpdateStepFailureV1::safe(
            "update.health_receipt_invalid",
            "the canonical update receipt is invalid",
            false,
        ));
    }
    Ok(receipt)
}

fn read_attempt_receipt(
    workspace: &Path,
    attempt_id: &str,
) -> Result<UpdateReceiptV1, UpdateStepFailureV1> {
    if !is_valid_update_attempt_id_v1(attempt_id) {
        return Err(health_artifact_failure("update.health_generation_invalid"));
    }
    let path = attempt_receipt_path(workspace, attempt_id);
    match verify_metadata_path(workspace, &path, false) {
        Ok(true) => {}
        Ok(false) => {
            return Err(health_artifact_failure(
                "update.health_generation_receipt_missing",
            ))
        }
        Err(()) => {
            return Err(health_artifact_failure(
                "update.health_generation_receipt_unsafe",
            ))
        }
    }
    let receipt = serde_json::from_slice::<UpdateReceiptV1>(
        &fs::read(&path)
            .map_err(|_| health_artifact_failure("update.health_generation_receipt_missing"))?,
    )
    .map_err(|_| health_artifact_failure("update.health_generation_receipt_invalid"))?;
    if receipt.schema_version != UPDATE_RECEIPT_SCHEMA_V1 {
        return Err(health_artifact_failure(
            "update.health_generation_receipt_unsupported",
        ));
    }
    Ok(receipt)
}

fn health_artifact_failure(code: &str) -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        code,
        "the committed update generation failed health verification",
        true,
    )
}

fn unhealthy(
    checked_games: Vec<Game>,
    attempt_id: Option<String>,
    failure: UpdateStepFailureV1,
) -> UpdateHealthV1 {
    UpdateHealthV1 {
        schema_version: UPDATE_HEALTH_SCHEMA_V1.to_owned(),
        healthy: false,
        attempt_id,
        checked_games,
        failure: Some(failure),
    }
}

pub async fn run_update_v1<E: UpdateStepExecutor, S: UpdateReceiptStore>(
    request: &UpdateRequestV1,
    invocation: &UpdateInvocationV1,
    executor: &E,
    store: &S,
) -> UpdateRunOutcomeV1 {
    run_update_observed_v1(
        request,
        invocation,
        executor,
        store,
        &DirectUpdateExecutionObserverV1,
    )
    .await
}

pub async fn run_update_observed_v1<E: UpdateStepExecutor, S: UpdateReceiptStore>(
    request: &UpdateRequestV1,
    invocation: &UpdateInvocationV1,
    executor: &E,
    store: &S,
    observer: &dyn ExecutionObserver,
) -> UpdateRunOutcomeV1 {
    let mut receipt = initial_receipt(request, invocation);
    if !is_valid_update_attempt_id_v1(&invocation.attempt_id) {
        return in_memory_failure(
            receipt,
            UpdateStepFailureV1::safe(
                "update.invalid_attempt_id",
                "attempt identifier is invalid",
                false,
            ),
        );
    }
    if let Err(failure) = request.validate() {
        return in_memory_failure(receipt, failure);
    }

    let lease = match WorkspaceWriteLease::acquire(&request.workspace) {
        Ok(lease) => lease,
        Err(error) => return in_memory_failure(receipt, lease_failure(error)),
    };
    let workspace = lease.workspace_root().to_path_buf();

    if let Err(failure) = store.recover_interrupted(&workspace, &invocation.attempt_id) {
        return in_memory_failure(receipt, failure);
    }
    if let Err(failure) = store.write_running(&workspace, &receipt) {
        return in_memory_failure(receipt, failure);
    }

    let mut state = match store.load_state(&workspace) {
        Ok(state) => state,
        Err(failure) => {
            if observer.before_commit().is_err() {
                return finish_interrupted(&workspace, receipt, store);
            }
            return finish_failure(&workspace, receipt, failure, store);
        }
    };

    let context = UpdateStepContextV1 {
        workspace: workspace.clone(),
        attempt_id: invocation.attempt_id.clone(),
        observed_at: invocation.observed_at,
        force: request.force,
    };

    if run_selected_games(&mut receipt, &context, executor, observer)
        .await
        .is_err()
    {
        return finish_interrupted(&workspace, receipt, store);
    }
    let successful = receipt
        .games
        .iter()
        .filter(|game| game.selected)
        .all(|game| game.status == UpdateStepStatusV1::Succeeded);

    receipt.finished_at_utc = Some(now_utc_text());
    if !successful {
        receipt.status = if receipt
            .games
            .iter()
            .any(|game| game.selected && game.status == UpdateStepStatusV1::Succeeded)
        {
            UpdateRunStatusV1::Partial
        } else {
            UpdateRunStatusV1::Failed
        };
        if observer.before_commit().is_err() {
            return finish_interrupted(&workspace, receipt, store);
        }
        let failure = receipt
            .games
            .iter()
            .filter(|game| game.selected)
            .flat_map(|game| &game.steps)
            .find_map(|step| step.failure.clone())
            .unwrap_or_else(|| {
                UpdateStepFailureV1::safe(
                    "update.partial_or_failed",
                    "one or more selected update steps failed",
                    true,
                )
            });
        return finish_failure(&workspace, receipt, failure, store);
    }

    let Some(config_sha256) = receipt.config_sha256.clone() else {
        if observer.before_commit().is_err() {
            return finish_interrupted(&workspace, receipt, store);
        }
        return finish_failure(
            &workspace,
            receipt,
            UpdateStepFailureV1::safe(
                "update.config_identity_missing",
                "the update configuration identity is missing",
                false,
            ),
            store,
        );
    };

    let Some(freshness_config) = executor.freshness_config() else {
        if observer.before_commit().is_err() {
            return finish_interrupted(&workspace, receipt, store);
        }
        return finish_failure(&workspace, receipt, update_freshness_failure_v1(), store);
    };

    for game in receipt.games.iter().filter(|game| game.selected) {
        state.games.insert(
            game.game,
            UpdateStateGameV1 {
                attempt_id: receipt.attempt_id.clone(),
                completed_at_utc: receipt
                    .finished_at_utc
                    .clone()
                    .unwrap_or_else(|| receipt.started_at_utc.clone()),
                config_sha256: config_sha256.clone(),
                artifacts: game
                    .steps
                    .iter()
                    .flat_map(|step| step.artifacts.clone())
                    .collect(),
            },
        );
    }
    let checked_games = receipt
        .games
        .iter()
        .filter(|game| game.selected)
        .map(|game| game.game)
        .collect::<Vec<_>>();
    let generation_date = invocation.local_datetime().date();
    let generation_dates = checked_games
        .iter()
        .copied()
        .map(|game| (game, generation_date))
        .collect::<BTreeMap<_, _>>();
    if let Err(failure) = load_update_freshness_locked_v1(
        &workspace,
        &checked_games,
        freshness_config,
        &state,
        &generation_dates,
    ) {
        if observer.before_commit().is_err() {
            return finish_interrupted(&workspace, receipt, store);
        }
        return finish_failure(&workspace, receipt, failure, store);
    }
    if observer.before_commit().is_err() {
        return finish_interrupted(&workspace, receipt, store);
    }
    receipt.status = UpdateRunStatusV1::Succeeded;
    receipt.state_committed = true;
    receipt.receipt_committed = true;
    match store.commit_success(&workspace, &state, &receipt) {
        Ok(()) => {
            let freshness = load_committed_attempt_freshness_locked_v1(
                &workspace,
                &receipt,
                freshness_config,
                &state,
            );
            let exit_code = if freshness.is_ok() { 0 } else { 1 };
            UpdateRunOutcomeV1 {
                receipt,
                exit_code,
                freshness: Some(freshness),
            }
        }
        Err(failure) => {
            receipt.state_committed = false;
            receipt.receipt_committed = false;
            receipt.status = UpdateRunStatusV1::Failed;
            receipt.failure = Some(failure.clone());
            finish_failure(&workspace, receipt, failure, store)
        }
    }
}

async fn run_selected_games<E: UpdateStepExecutor>(
    receipt: &mut UpdateReceiptV1,
    context: &UpdateStepContextV1,
    executor: &E,
    observer: &dyn ExecutionObserver,
) -> Result<(), ExecutionControlError> {
    for game_index in 0..receipt.games.len() {
        if !receipt.games[game_index].selected {
            continue;
        }
        let mut game_failed = false;
        for step_index in 0..receipt.games[game_index].steps.len() {
            let step = receipt.games[game_index].steps[step_index].step;
            if game_failed {
                let step_receipt = &mut receipt.games[game_index].steps[step_index];
                step_receipt.status = UpdateStepStatusV1::Skipped;
                step_receipt.duration_ms = Some(0);
                step_receipt.reason_code = Some("update.dependency_failed".to_owned());
                continue;
            }
            receipt.games[game_index].status = UpdateStepStatusV1::Running;
            receipt.games[game_index].steps[step_index].status = UpdateStepStatusV1::Running;
            let started_at = Instant::now();
            let execution = executor.execute_observed(step, context, observer).await;
            let execution_succeeded = execution.is_ok();
            let (status, artifacts, row_count, failure) = match execution {
                Ok(artifacts) => match validate_artifacts(&context.workspace, artifacts) {
                    Ok(validated) => (
                        UpdateStepStatusV1::Succeeded,
                        validated.artifacts,
                        validated.row_count,
                        None,
                    ),
                    Err(failure) => {
                        game_failed = true;
                        (UpdateStepStatusV1::Failed, Vec::new(), None, Some(failure))
                    }
                },
                Err(UpdateStepExecutionErrorV1::Failure(failure)) => {
                    game_failed = true;
                    (UpdateStepStatusV1::Failed, Vec::new(), None, Some(failure))
                }
                Err(UpdateStepExecutionErrorV1::Control(control)) => {
                    let step_receipt = &mut receipt.games[game_index].steps[step_index];
                    step_receipt.status = UpdateStepStatusV1::Skipped;
                    step_receipt.duration_ms = Some(
                        started_at
                            .elapsed()
                            .as_millis()
                            .try_into()
                            .unwrap_or(u64::MAX),
                    );
                    step_receipt.reason_code = Some("task.cancelled".to_owned());
                    normalize_interrupted_steps(receipt);
                    return Err(control);
                }
            };
            let fetch_source = executor.fetch_source(step, execution_succeeded, failure.as_ref());
            let cache_fallback = executor.cache_fallback(step, failure.as_ref());
            let reason_code = failure
                .as_ref()
                .map(|failure| safe_reason_code(&failure.code));
            let step_receipt = &mut receipt.games[game_index].steps[step_index];
            step_receipt.status = status;
            step_receipt.duration_ms = Some(
                started_at
                    .elapsed()
                    .as_millis()
                    .try_into()
                    .unwrap_or(u64::MAX),
            );
            step_receipt.row_count = row_count;
            step_receipt.fetch_source = fetch_source;
            step_receipt.cache_fallback = cache_fallback;
            step_receipt.reason_code = reason_code;
            step_receipt.artifacts = artifacts;
            step_receipt.failure = failure;
        }
        receipt.games[game_index].status = if game_failed {
            UpdateStepStatusV1::Failed
        } else {
            UpdateStepStatusV1::Succeeded
        };
    }
    stabilize_receipt_steps(receipt);
    Ok(())
}

#[derive(Debug)]
struct ValidatedArtifactsV1 {
    artifacts: Vec<UpdateArtifactV1>,
    row_count: Option<u64>,
}

fn validate_artifacts(
    workspace: &Path,
    mut artifacts: Vec<UpdateArtifactV1>,
) -> Result<ValidatedArtifactsV1, UpdateStepFailureV1> {
    if artifacts.is_empty() {
        return Err(UpdateStepFailureV1::safe(
            "update.artifacts_empty",
            "an update step produced no verifiable artifacts",
            false,
        ));
    }
    let mut row_count = None::<u64>;
    for artifact in &mut artifacts {
        if !safe_relative_path(&artifact.path) {
            return Err(UpdateStepFailureV1::safe(
                "update.artifact_path_unsafe",
                "an update artifact path is unsafe",
                false,
            ));
        }
        let path = workspace.join(&artifact.path);
        // Reject every existing alias before opening the artifact. Checking
        // only after hashing would already have followed a junction outside
        // the trusted workspace.
        reject_reparse_between(workspace, &path)?;
        let metadata = fs::symlink_metadata(&path).map_err(|_| {
            UpdateStepFailureV1::safe(
                "update.artifact_missing",
                "an expected update artifact is missing",
                true,
            )
        })?;
        let count_csv_rows =
            artifact.path.extension().and_then(|value| value.to_str()) == Some("csv");
        let digest_and_rows = hash_file_with_optional_csv_rows(&path, count_csv_rows);
        let supplied_digest = artifact.sha256.clone();
        if metadata.file_type().is_symlink()
            || is_windows_reparse(&metadata)
            || !metadata.is_file()
            || metadata.len() != artifact.bytes
            || (!supplied_digest.is_empty() && !valid_sha256(&supplied_digest))
            || digest_and_rows
                .as_ref()
                .map(|(digest, bytes, _)| {
                    *bytes != artifact.bytes
                        || (!supplied_digest.is_empty() && digest != &supplied_digest)
                })
                .unwrap_or(true)
        {
            return Err(UpdateStepFailureV1::safe(
                "update.artifact_invalid",
                "an expected update artifact failed validation",
                true,
            ));
        }
        if let Ok((digest, bytes, rows)) = digest_and_rows {
            artifact.sha256 = digest;
            artifact.bytes = bytes;
            let Some(rows) = rows else {
                continue;
            };
            row_count = Some(row_count.unwrap_or(0).saturating_add(rows));
        }
    }
    Ok(ValidatedArtifactsV1 {
        artifacts,
        row_count,
    })
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn safe_reason_code(code: &str) -> String {
    if !code.is_empty()
        && code.len() <= 96
        && code.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
    {
        code.to_owned()
    } else {
        "update.step_failed".to_owned()
    }
}

fn stabilize_receipt_steps(receipt: &mut UpdateReceiptV1) {
    receipt.games.sort_by_key(|game| game.game);
    for game in &mut receipt.games {
        game.steps.sort_by_key(|step| step.step);
        for step in &mut game.steps {
            step.artifacts.sort_by(|left, right| {
                left.path
                    .cmp(&right.path)
                    .then(left.sha256.cmp(&right.sha256))
                    .then(left.bytes.cmp(&right.bytes))
            });
        }
    }
}

fn safe_relative_path(path: &Path) -> bool {
    !path.as_os_str().is_empty()
        && !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn reject_reparse_between(workspace: &Path, path: &Path) -> Result<(), UpdateStepFailureV1> {
    let suffix = path.strip_prefix(workspace).map_err(|_| {
        UpdateStepFailureV1::safe(
            "update.artifact_path_unsafe",
            "an update artifact path is unsafe",
            false,
        )
    })?;
    let mut current = workspace.to_path_buf();
    for component in suffix.components() {
        current.push(component);
        let metadata = fs::symlink_metadata(&current).map_err(|_| {
            UpdateStepFailureV1::safe(
                "update.artifact_missing",
                "an expected update artifact is missing",
                true,
            )
        })?;
        if metadata.file_type().is_symlink() || is_windows_reparse(&metadata) {
            return Err(UpdateStepFailureV1::safe(
                "update.artifact_path_unsafe",
                "an update artifact path is unsafe",
                false,
            ));
        }
    }
    Ok(())
}

/// Verify a metadata path without following any pre-existing symlink/reparse
/// component. `Ok(false)` means the path is absent; callers decide whether
/// absence is an empty initial state or a health failure.
fn verify_metadata_path(workspace: &Path, path: &Path, expect_directory: bool) -> Result<bool, ()> {
    let suffix = path.strip_prefix(workspace).map_err(|_| ())?;
    if suffix.as_os_str().is_empty()
        || suffix
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(());
    }
    let component_count = suffix.components().count();
    let mut current = workspace.to_path_buf();
    for (index, component) in suffix.components().enumerate() {
        current.push(component.as_os_str());
        let metadata = match fs::symlink_metadata(&current) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(_) => return Err(()),
        };
        if metadata.file_type().is_symlink() || is_windows_reparse(&metadata) {
            return Err(());
        }
        let is_leaf = index + 1 == component_count;
        if !is_leaf && !metadata.is_dir() {
            return Err(());
        }
        if is_leaf
            && ((expect_directory && !metadata.is_dir())
                || (!expect_directory && !metadata.is_file()))
        {
            return Err(());
        }
    }
    Ok(true)
}

fn is_windows_reparse(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        let _ = metadata;
        false
    }
}

fn initial_receipt(request: &UpdateRequestV1, invocation: &UpdateInvocationV1) -> UpdateReceiptV1 {
    let mut receipt = UpdateReceiptV1 {
        schema_version: UPDATE_RECEIPT_SCHEMA_V1.to_owned(),
        attempt_id: invocation.attempt_id.clone(),
        started_at_utc: invocation
            .started_at_utc()
            .to_rfc3339_opts(SecondsFormat::Micros, true),
        invocation_local_datetime: invocation
            .local_datetime()
            .format("%Y-%m-%dT%H:%M:%S%.6f")
            .to_string(),
        finished_at_utc: None,
        status: UpdateRunStatusV1::Running,
        force: request.force,
        config_sha256: request.config_sha256.clone(),
        state_committed: false,
        receipt_committed: false,
        games: vec![
            game_receipt(Game::Hsr, !request.skip_hsr),
            game_receipt(Game::Zzz, !request.skip_zzz),
        ],
        failure: None,
    };
    stabilize_receipt_steps(&mut receipt);
    receipt
}

fn game_receipt(game: Game, selected: bool) -> UpdateGameReceiptV1 {
    let steps: &[UpdateStepKindV1] = match game {
        Game::Hsr => &[UpdateStepKindV1::HsrExport],
        Game::Zzz => &[
            UpdateStepKindV1::ZzzExport,
            UpdateStepKindV1::ZzzCoverage,
            UpdateStepKindV1::ZzzPullValue,
            UpdateStepKindV1::ZzzReviewPacket,
        ],
    };
    UpdateGameReceiptV1 {
        game,
        selected,
        status: if selected {
            UpdateStepStatusV1::Pending
        } else {
            UpdateStepStatusV1::Skipped
        },
        steps: steps
            .iter()
            .copied()
            .map(|step| UpdateStepReceiptV1 {
                step,
                status: if selected {
                    UpdateStepStatusV1::Pending
                } else {
                    UpdateStepStatusV1::Skipped
                },
                duration_ms: (!selected).then_some(0),
                row_count: None,
                fetch_source: None,
                cache_fallback: false,
                reason_code: (!selected).then(|| "update.game_not_selected".to_owned()),
                artifacts: Vec::new(),
                failure: None,
            })
            .collect(),
    }
}

fn lease_failure(error: WorkspaceWriteLeaseError) -> UpdateStepFailureV1 {
    let (message, retryable) = match error {
        WorkspaceWriteLeaseError::Busy => ("the workspace is busy", true),
        WorkspaceWriteLeaseError::UnsafeWorkspace => ("the workspace path is unsafe", false),
        WorkspaceWriteLeaseError::Unavailable => ("the workspace lock is unavailable", true),
    };
    UpdateStepFailureV1::safe(error.code(), message, retryable)
}

fn in_memory_failure(
    mut receipt: UpdateReceiptV1,
    failure: UpdateStepFailureV1,
) -> UpdateRunOutcomeV1 {
    receipt.finished_at_utc = Some(now_utc_text());
    receipt.status = UpdateRunStatusV1::Failed;
    receipt.failure = Some(failure);
    stabilize_receipt_steps(&mut receipt);
    UpdateRunOutcomeV1 {
        receipt,
        exit_code: 1,
        freshness: None,
    }
}

fn finish_failure<S: UpdateReceiptStore>(
    workspace: &Path,
    mut receipt: UpdateReceiptV1,
    failure: UpdateStepFailureV1,
    store: &S,
) -> UpdateRunOutcomeV1 {
    if receipt.finished_at_utc.is_none() {
        receipt.finished_at_utc = Some(now_utc_text());
    }
    if receipt.status == UpdateRunStatusV1::Running {
        receipt.status = UpdateRunStatusV1::Failed;
    }
    receipt.state_committed = false;
    receipt.receipt_committed = true;
    receipt.failure = Some(failure);
    stabilize_receipt_steps(&mut receipt);
    if let Err(commit_failure) = store.commit_failure(workspace, &receipt) {
        receipt.receipt_committed = false;
        receipt.failure = Some(commit_failure);
    }
    UpdateRunOutcomeV1 {
        receipt,
        exit_code: 1,
        freshness: None,
    }
}

fn finish_interrupted<S: UpdateReceiptStore>(
    workspace: &Path,
    mut receipt: UpdateReceiptV1,
    store: &S,
) -> UpdateRunOutcomeV1 {
    receipt.finished_at_utc = Some(now_utc_text());
    receipt.status = UpdateRunStatusV1::Interrupted;
    receipt.state_committed = false;
    receipt.receipt_committed = false;
    receipt.failure = Some(cancelled_step_failure());
    normalize_interrupted_steps(&mut receipt);
    stabilize_receipt_steps(&mut receipt);
    let exit_code = match store.commit_interrupted(workspace, &receipt) {
        Ok(()) => 130,
        Err(failure) => {
            receipt.status = UpdateRunStatusV1::Failed;
            receipt.failure = Some(failure);
            1
        }
    };
    UpdateRunOutcomeV1 {
        receipt,
        exit_code,
        freshness: None,
    }
}

fn normalize_interrupted_steps(receipt: &mut UpdateReceiptV1) {
    for game in &mut receipt.games {
        if !game.selected || game.status == UpdateStepStatusV1::Succeeded {
            continue;
        }
        game.status = UpdateStepStatusV1::Skipped;
        for step in &mut game.steps {
            if matches!(
                step.status,
                UpdateStepStatusV1::Pending | UpdateStepStatusV1::Running
            ) {
                step.status = UpdateStepStatusV1::Skipped;
                step.duration_ms.get_or_insert(0);
                step.reason_code = Some("task.cancelled".to_owned());
                step.failure = None;
            }
        }
    }
}

fn now_utc_text() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
}

#[cfg(test)]
static ARTIFACT_HASH_PASSES_V1: AtomicU64 = AtomicU64::new(0);

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        sync::mpsc,
        thread,
        time::{Duration as StdDuration, SystemTime, UNIX_EPOCH},
    };

    static HASH_TEST_GATE: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn workspace_config_loader_runs_inside_the_health_snapshot_lease() {
        let root = std::env::temp_dir().join(format!(
            "miho-update-config-snapshot-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();

        let (start_writer, writer_start) = mpsc::channel();
        let (writer_entered, entered_writer) = mpsc::channel();
        let (writer_finished, finished_writer) = mpsc::channel();
        let writer_root = root.clone();
        let writer = thread::spawn(move || {
            writer_start.recv().unwrap();
            writer_entered.send(()).unwrap();
            let result = WorkspaceWriteLease::acquire(&writer_root).map(drop);
            writer_finished.send(result).unwrap();
        });

        let (health, _, freshness) =
            check_update_health_with_config_loader_v1(&root, true, true, |snapshot_root| {
                assert_eq!(snapshot_root, fs::canonicalize(&root).unwrap());
                start_writer.send(()).unwrap();
                entered_writer.recv().unwrap();
                assert!(
                    matches!(
                        finished_writer.recv_timeout(StdDuration::from_millis(150)),
                        Err(mpsc::RecvTimeoutError::Timeout)
                    ),
                    "a writer switched config/state while the config loader was running"
                );
                Err(update_health_config_failure_v1())
            });

        assert!(!health.healthy);
        assert_eq!(
            health.failure.as_ref().map(|failure| failure.code.as_str()),
            Some("update.health_config_invalid")
        );
        assert!(freshness.is_empty());
        assert_eq!(
            finished_writer
                .recv_timeout(StdDuration::from_secs(5))
                .expect("the writer did not resume after health returned"),
            Ok(())
        );
        writer.join().unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn generation_receipt_local_datetime_requires_exact_writer_round_trip() {
        let mut receipt = UpdateReceiptV1 {
            schema_version: UPDATE_RECEIPT_SCHEMA_V1.to_owned(),
            attempt_id: "attempt-generation-date".to_owned(),
            started_at_utc: "2026-07-13T01:30:00.123456Z".to_owned(),
            invocation_local_datetime: "2026-07-13T09:30:00.123456".to_owned(),
            finished_at_utc: None,
            status: UpdateRunStatusV1::Running,
            force: false,
            config_sha256: None,
            state_committed: false,
            receipt_committed: false,
            games: Vec::new(),
            failure: None,
        };
        assert_eq!(
            generation_local_date_v1(&receipt).unwrap(),
            NaiveDate::from_ymd_opt(2026, 7, 13).unwrap()
        );

        for invalid in [
            "2026-07-13T09:30:00",
            "2026-07-13T09:30:00.123",
            "2026-07-13T09:30:00.1234567",
            "2026-07-13T09:30:00.123456Z",
            "2026-07-13T09:30:00.123456+08:00",
            " 2026-07-13T09:30:00.123456",
            "2026-07-13T09:30:00.123456 ",
            "2026-02-30T09:30:00.123456",
        ] {
            receipt.invocation_local_datetime = invalid.to_owned();
            assert!(
                generation_local_date_v1(&receipt).is_err(),
                "accepted non-canonical generation datetime {invalid:?}"
            );
        }
    }

    #[test]
    fn typed_data_quality_freshness_error_survives_the_anyhow_boundary() {
        let typed = anyhow::Error::new(MihoError::DataQualityFreshness(
            "injected invalid report".to_owned(),
        ));
        assert!(is_data_quality_freshness_error(&typed));
        assert!(!is_data_quality_freshness_error(&anyhow::Error::new(
            MihoError::Visualizer("another visualizer failure".to_owned())
        )));
    }

    #[test]
    fn collected_artifact_is_hashed_once_during_trusted_validation() {
        let _gate = HASH_TEST_GATE.lock().unwrap();
        let root = std::env::temp_dir().join(format!(
            "miho-update-single-hash-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let path = root.join("rows.csv");
        fs::write(&path, b"name,note\nalpha,one\n").unwrap();

        ARTIFACT_HASH_PASSES_V1.store(0, Ordering::SeqCst);
        let artifact = file_artifact(&root, &path).unwrap();
        assert!(artifact.sha256.is_empty());
        let validated = validate_artifacts(&root, vec![artifact]).unwrap();
        assert_eq!(ARTIFACT_HASH_PASSES_V1.load(Ordering::SeqCst), 1);
        assert_eq!(validated.row_count, Some(1));
        assert!(valid_sha256(&validated.artifacts[0].sha256));

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn trusted_artifact_handle_denies_concurrent_write_and_replace() {
        let _gate = HASH_TEST_GATE.lock().unwrap();
        let root = std::env::temp_dir().join(format!(
            "miho-update-immutable-read-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let path = root.join("artifact.json");
        let moved = root.join("artifact-moved.json");
        fs::write(&path, b"{\"stable\":true}\n").unwrap();

        let handle = open_artifact_for_trusted_read(&path).unwrap();
        assert!(fs::OpenOptions::new().write(true).open(&path).is_err());
        assert!(fs::rename(&path, &moved).is_err());
        assert_eq!(handle.metadata().unwrap().len(), 16);

        drop(handle);
        fs::OpenOptions::new()
            .write(true)
            .truncate(true)
            .open(&path)
            .unwrap();
        fs::rename(&path, &moved).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn supplemental_fallback_reports_network_primary_with_cache_degradation() {
        let root = std::env::temp_dir().join(format!(
            "miho-update-source-receipt-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        let config = crate::UpdateConfigV1::parse(
            br#"{
              "schema_version":"miho-update-config-v1",
              "days":30,
              "hsr":{"output":"out","repo_id":"owner/hsr","revision":"main","modes":["moc"],"prydwen_top_n":100},
              "zzz":{"output":"out_zzz","repo_id":"owner/zzz","revision":"main","modes":["sd"],"prydwen_top_n":100,"box":".miho/zzz_box_state.json","banner_plan":"configs/zzz_banner_plan.json","mechanism_notes":"configs/zzz_mechanism_notes","decision_baseline":"configs/zzz_decision_baseline.json"}
            }"#,
        )
        .unwrap()
        .resolve(&root)
        .unwrap();
        let executor = NativeUpdateExecutorV1::new(config);
        let step = UpdateStepKindV1::HsrExport;

        let supplemental = supplemental_cache_fallback_failure(step);
        assert_eq!(
            executor.fetch_source(step, false, Some(&supplemental)),
            Some(FetchSource::Network)
        );
        assert!(executor.cache_fallback(step, Some(&supplemental)));

        let primary = cache_fallback_failure(step);
        assert_eq!(
            executor.fetch_source(step, false, Some(&primary)),
            Some(FetchSource::Cache)
        );
        assert!(executor.cache_fallback(step, Some(&primary)));
        fs::remove_dir_all(root).unwrap();
    }
}
