use std::{
    collections::BTreeMap,
    fs::{self, File},
    future::Future,
    io::Read,
    path::{Component, Path, PathBuf},
    pin::Pin,
    sync::atomic::{AtomicU64, Ordering},
};

use chrono::{DateTime, Duration, FixedOffset, Local, NaiveDateTime, SecondsFormat, Timelike, Utc};
use miho_core::{
    atomic,
    contract::{diagnostic_code, FeatureFlags, Game},
    output::ArtifactManifestEntry,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{
    execute_export_v1, execute_export_with_hub_v1, execute_task_v1, export_cache_root,
    AppInvocation, CoverageTaskV1, ExportInvocation, ExportSourceV1, ExportTaskV1, PullTaskV1,
    ResolvedUpdateConfigV1, TaskRequestV1, TaskSpecV1, WorkspaceLayout, WorkspaceWriteLease,
    WorkspaceWriteLeaseError,
};

pub const UPDATE_RECEIPT_SCHEMA_V1: &str = "miho-update-receipt-v1";
pub const UPDATE_STATE_SCHEMA_V1: &str = "miho-update-state-v1";
pub const UPDATE_HEALTH_SCHEMA_V1: &str = "miho-update-health-v1";
pub const UPDATE_ATTEMPT_DIRECTORY: &str = "update-attempts";
pub const UPDATE_STATE_FILE: &str = "update-state-v1.json";
pub const UPDATE_CANONICAL_RECEIPT_FILE: &str = "last-update-receipt-v1.json";

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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateStepReceiptV1 {
    pub step: UpdateStepKindV1,
    pub status: UpdateStepStatusV1,
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
        debug_assert!(valid_attempt_id(&attempt_id));
        Self {
            attempt_id,
            observed_at,
        }
    }

    pub fn new(
        attempt_id: String,
        observed_at: DateTime<FixedOffset>,
    ) -> Result<Self, UpdateStepFailureV1> {
        if !valid_attempt_id(&attempt_id) {
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

fn valid_attempt_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
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

pub trait UpdateStepExecutor: Send + Sync {
    fn execute<'a>(
        &'a self,
        step: UpdateStepKindV1,
        context: &'a UpdateStepContextV1,
    ) -> UpdateStepFuture<'a>;
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
        Box::pin(async move { self.execute_step(step, context).await })
    }
}

impl NativeUpdateExecutorV1 {
    async fn execute_step(
        &self,
        step: UpdateStepKindV1,
        context: &UpdateStepContextV1,
    ) -> Result<Vec<UpdateArtifactV1>, UpdateStepFailureV1> {
        if context.workspace != self.config.workspace {
            return Err(UpdateStepFailureV1::safe(
                "update.workspace_mismatch",
                "the update executor workspace does not match the locked workspace",
                false,
            ));
        }
        #[cfg(debug_assertions)]
        wait_for_debug_update_gate()?;
        match step {
            UpdateStepKindV1::HsrExport => self.execute_export(Game::Hsr, context).await,
            UpdateStepKindV1::ZzzExport => self.execute_export(Game::Zzz, context).await,
            UpdateStepKindV1::ZzzCoverage => {
                self.execute_report(UpdateStepKindV1::ZzzCoverage, context)
            }
            UpdateStepKindV1::ZzzPullValue => {
                self.execute_report(UpdateStepKindV1::ZzzPullValue, context)
            }
            UpdateStepKindV1::ZzzReviewPacket => {
                self.execute_report(UpdateStepKindV1::ZzzReviewPacket, context)
            }
        }
    }

    async fn execute_export(
        &self,
        game: Game,
        context: &UpdateStepContextV1,
    ) -> Result<Vec<UpdateArtifactV1>, UpdateStepFailureV1> {
        let settings = match game {
            Game::Hsr => &self.config.hsr,
            Game::Zzz => &self.config.zzz.export,
        };
        let invocation = ExportInvocation::new(context.workspace.clone(), context.observed_at)
            .map_err(|_| safe_step_failure(game_export_step(game), false))?;
        let to_date = invocation.local_date();
        let from_date = to_date - Duration::days(i64::from(self.config.days));
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
        let receipt = if game == Game::Zzz {
            let hsr_directory = self
                .config
                .hsr
                .output
                .file_name()
                .and_then(|value| value.to_str())
                .ok_or_else(|| safe_step_failure(game_export_step(game), false))?;
            execute_export_with_hub_v1(&task, &invocation, hsr_directory).await
        } else {
            execute_export_v1(&task, &invocation).await
        }
        .map_err(|_| safe_step_failure(game_export_step(game), true))?;
        if receipt
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.code != diagnostic_code::WORKBOOK_GENERATION_FAILED)
        {
            return Err(UpdateStepFailureV1::safe(
                format!("update.{}.degraded", step_code(game_export_step(game))),
                format!(
                    "the {} step completed with incomplete source diagnostics",
                    step_code(game_export_step(game))
                ),
                true,
            ));
        }
        collect_export_artifacts(&context.workspace, &settings.output, game)
            .map_err(|_| safe_artifact_failure(game_export_step(game)))
    }

    fn execute_report(
        &self,
        step: UpdateStepKindV1,
        context: &UpdateStepContextV1,
    ) -> Result<Vec<UpdateArtifactV1>, UpdateStepFailureV1> {
        let invocation = AppInvocation::new(context.workspace.clone(), context.local_datetime())
            .map_err(|_| safe_step_failure(step, false))?;
        let workspace = WorkspaceLayout {
            data_dir: self.config.zzz.export.output.clone(),
            box_path: self.config.zzz.box_path.clone(),
        };
        let task = match step {
            UpdateStepKindV1::ZzzCoverage => TaskSpecV1::Coverage(CoverageTaskV1 {
                planned_slugs: Vec::new(),
                plan_path: Some(self.config.zzz.banner_plan.clone()),
                plan_statuses: vec!["current".to_owned(), "next".to_owned()],
                limit: 0,
                min_a_app_rate: "10.0".to_owned(),
                current_output: None,
                target_output: None,
                aggregate_output: None,
            }),
            UpdateStepKindV1::ZzzPullValue | UpdateStepKindV1::ZzzReviewPacket => {
                let task = PullTaskV1 {
                    plan_path: self.config.zzz.banner_plan.clone(),
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
            _ => return Err(safe_step_failure(step, false)),
        };
        let receipt = execute_task_v1(&TaskRequestV1::new(workspace, task), &invocation)
            .map_err(|_| safe_step_failure(step, true))?;
        collect_output_artifacts(&context.workspace, &receipt.outputs)
            .map_err(|_| safe_artifact_failure(step))
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

fn safe_artifact_failure(step: UpdateStepKindV1) -> UpdateStepFailureV1 {
    UpdateStepFailureV1::safe(
        format!("update.{}.artifacts_invalid", step_code(step)),
        format!("the {} artifacts failed verification", step_code(step)),
        true,
    )
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
        let digest = sha256_file(&path)?;
        if digest != entry.sha256 {
            anyhow::bail!("export artifact digest does not match manifest");
        }
        outputs.push(UpdateArtifactV1 {
            path: relative,
            bytes: metadata.len(),
            sha256: digest,
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
        sha256: sha256_file(path)?,
    })
}

fn workspace_relative(workspace: &Path, path: &Path) -> anyhow::Result<PathBuf> {
    let relative = path.strip_prefix(workspace)?;
    if !safe_relative_path(relative) {
        anyhow::bail!("update artifact path is not workspace-relative");
    }
    Ok(relative.to_path_buf())
}

fn sha256_file(path: &Path) -> anyhow::Result<String> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
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
}

#[derive(Debug, Default)]
pub struct FileUpdateReceiptStore;

impl UpdateReceiptStore for FileUpdateReceiptStore {
    fn recover_interrupted(
        &self,
        workspace: &Path,
        current_attempt_id: &str,
    ) -> Result<(), UpdateStepFailureV1> {
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
    let checked_games = [
        require_hsr.then_some(Game::Hsr),
        require_zzz.then_some(Game::Zzz),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>();
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
    let lease = match WorkspaceWriteLease::acquire(workspace) {
        Ok(lease) => lease,
        Err(error) => return unhealthy(checked_games, None, lease_failure(error)),
    };
    let workspace = lease.workspace_root();
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
    let state = match FileUpdateReceiptStore.load_state(workspace) {
        Ok(state) => state,
        Err(failure) => return unhealthy(checked_games, attempt_id, failure),
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
    if !valid_attempt_id(&receipt.attempt_id) {
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
    if !valid_attempt_id(attempt_id) {
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
    let mut receipt = initial_receipt(request, invocation);
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
        Err(failure) => return finish_failure(&workspace, receipt, failure, store),
    };

    let context = UpdateStepContextV1 {
        workspace: workspace.clone(),
        attempt_id: invocation.attempt_id.clone(),
        observed_at: invocation.observed_at,
        force: request.force,
    };

    run_selected_games(&mut receipt, &context, executor).await;
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
        return finish_failure(
            &workspace,
            receipt,
            UpdateStepFailureV1::safe(
                "update.partial_or_failed",
                "one or more selected update steps failed",
                true,
            ),
            store,
        );
    }

    let Some(config_sha256) = receipt.config_sha256.clone() else {
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
    receipt.status = UpdateRunStatusV1::Succeeded;
    receipt.state_committed = true;
    receipt.receipt_committed = true;
    match store.commit_success(&workspace, &state, &receipt) {
        Ok(()) => UpdateRunOutcomeV1 {
            receipt,
            exit_code: 0,
        },
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
) {
    for game_index in 0..receipt.games.len() {
        if !receipt.games[game_index].selected {
            continue;
        }
        let mut game_failed = false;
        for step_index in 0..receipt.games[game_index].steps.len() {
            let step = receipt.games[game_index].steps[step_index].step;
            if game_failed {
                receipt.games[game_index].steps[step_index].status = UpdateStepStatusV1::Skipped;
                continue;
            }
            receipt.games[game_index].status = UpdateStepStatusV1::Running;
            receipt.games[game_index].steps[step_index].status = UpdateStepStatusV1::Running;
            match executor.execute(step, context).await {
                Ok(artifacts) => match validate_artifacts(&context.workspace, artifacts) {
                    Ok(artifacts) => {
                        let step_receipt = &mut receipt.games[game_index].steps[step_index];
                        step_receipt.status = UpdateStepStatusV1::Succeeded;
                        step_receipt.artifacts = artifacts;
                    }
                    Err(failure) => {
                        let step_receipt = &mut receipt.games[game_index].steps[step_index];
                        step_receipt.status = UpdateStepStatusV1::Failed;
                        step_receipt.failure = Some(failure);
                        game_failed = true;
                    }
                },
                Err(failure) => {
                    let step_receipt = &mut receipt.games[game_index].steps[step_index];
                    step_receipt.status = UpdateStepStatusV1::Failed;
                    step_receipt.failure = Some(failure);
                    game_failed = true;
                }
            }
        }
        receipt.games[game_index].status = if game_failed {
            UpdateStepStatusV1::Failed
        } else {
            UpdateStepStatusV1::Succeeded
        };
    }
}

fn validate_artifacts(
    workspace: &Path,
    artifacts: Vec<UpdateArtifactV1>,
) -> Result<Vec<UpdateArtifactV1>, UpdateStepFailureV1> {
    if artifacts.is_empty() {
        return Err(UpdateStepFailureV1::safe(
            "update.artifacts_empty",
            "an update step produced no verifiable artifacts",
            false,
        ));
    }
    for artifact in &artifacts {
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
        if metadata.file_type().is_symlink()
            || is_windows_reparse(&metadata)
            || !metadata.is_file()
            || metadata.len() != artifact.bytes
            || !valid_sha256(&artifact.sha256)
            || sha256_file(&path)
                .map(|digest| digest != artifact.sha256)
                .unwrap_or(true)
        {
            return Err(UpdateStepFailureV1::safe(
                "update.artifact_invalid",
                "an expected update artifact failed validation",
                true,
            ));
        }
    }
    Ok(artifacts)
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
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
    UpdateReceiptV1 {
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
    }
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
    UpdateRunOutcomeV1 {
        receipt,
        exit_code: 1,
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
    if let Err(commit_failure) = store.commit_failure(workspace, &receipt) {
        receipt.receipt_committed = false;
        receipt.failure = Some(commit_failure);
    }
    UpdateRunOutcomeV1 {
        receipt,
        exit_code: 1,
    }
}

fn now_utc_text() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
}
