//! Shared synchronous application layer for report-producing frontends.
//!
//! CLI and Tauri adapters should translate their user-facing arguments into a
//! versioned [`TaskRequestV1`], capture one [`AppInvocation`], and call
//! [`execute_task_v1`]. Recommendation and evidence rules remain in
//! `miho-core`; this crate owns path discovery, input reads, rendering, and the
//! final batch installation.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path, PathBuf},
};

use anyhow::{bail, Context};
use chrono::{Local, NaiveDateTime, Timelike};
use miho_core::{
    atomic,
    decision_legacy::{
        build_decision_legacy_v0, render_decision_json_legacy_v0,
        render_decision_markdown_legacy_v0, DecisionLegacyContextV0, DecisionLegacyInputsV0,
        DecisionLegacyRequestV0, DECISION_LEGACY_METHOD,
    },
    evidence::{
        build_evidence_bundle_v1, render_aggregate_csv_v1, render_coverage_markdown_v1,
        EvidenceContextV1, EvidenceGameV1, EvidenceInputsV1, EvidenceRequestV1,
        EVIDENCE_METHOD_VERSION,
    },
    pull_value::{
        build_pull_value_bundle_v1, render_gpt_review_packet_v1, render_pull_value_markdown_v1,
        validate_mechanism_note_v1, PullValueContextV1, PullValueInputsV1, PullValueRequestV1,
        PULL_VALUE_METHOD_VERSION,
    },
};
use serde::{Deserialize, Serialize};

mod export;
mod task_manager;
mod update;
mod update_config;
mod workspace_bootstrap;
mod workspace_write_lease;

pub use export::{
    execute_export_observed_v1, execute_export_observed_with_hub_v1, execute_export_v1,
    execute_export_with_hub_v1, execute_visualizer_v1, export_cache_root, ExportInvocation,
    ExportObserver, ExportReceiptV1, ExportSourceV1, ExportTaskV1, TrustedExportTaskV1,
    VisualizerTaskV1,
};
pub use task_manager::{
    CancelOutcomeV1, CancelTaskResultV1, ExportTaskExecutor, PublicArtifactV1, PublicTaskFailureV1,
    PublicTaskSnapshotV1, PublicTaskUpdateV1, TaskExecutor, TaskManager, TaskManagerError,
    TaskSnapshotV1, TaskSpawner, TaskStatusV1, PUBLIC_TASK_SNAPSHOT_SCHEMA_V1,
    TASK_SNAPSHOT_SCHEMA_V1,
};
pub use update::{
    check_update_health_v1, is_valid_update_attempt_id_v1, run_update_v1, FileUpdateReceiptStore,
    NativeUpdateExecutorV1, UpdateArtifactV1, UpdateGameReceiptV1, UpdateHealthV1,
    UpdateInvocationV1, UpdateReceiptStore, UpdateReceiptV1, UpdateRequestV1, UpdateRunOutcomeV1,
    UpdateRunStatusV1, UpdateStateGameV1, UpdateStateV1, UpdateStepContextV1, UpdateStepExecutor,
    UpdateStepFailureV1, UpdateStepFuture, UpdateStepKindV1, UpdateStepReceiptV1,
    UpdateStepStatusV1, MAX_UPDATE_ATTEMPT_ID_BYTES_V1, UPDATE_ATTEMPT_DIRECTORY,
    UPDATE_CANONICAL_RECEIPT_FILE, UPDATE_HEALTH_SCHEMA_V1, UPDATE_RECEIPT_SCHEMA_V1,
    UPDATE_STATE_FILE, UPDATE_STATE_SCHEMA_V1,
};
pub use update_config::{
    load_update_config_v1, load_update_config_with_digest_v1, LoadedUpdateConfigV1,
    ResolvedGameUpdateConfigV1, ResolvedUpdateConfigV1, ResolvedZzzUpdateConfigV1, UpdateConfigV1,
    MAX_PRYDWEN_TOP_N_V1, MAX_UPDATE_CONFIG_BYTES_V1, MAX_UPDATE_DAYS_V1, MIN_PRYDWEN_TOP_N_V1,
    MIN_UPDATE_DAYS_V1, UPDATE_CONFIG_SCHEMA_V1,
};
pub use workspace_bootstrap::{
    begin_workspace_bootstrap_transaction_v1, bootstrap_workspace_v1,
    commit_workspace_bootstrap_transaction_v1, discard_workspace_bootstrap_transaction_v1,
    finalize_workspace_bootstrap_transaction_v1, rollback_workspace_bootstrap_transaction_v1,
    verify_workspace_bootstrap_transaction_v1, WorkspaceBootstrapCompletedOperationV1,
    WorkspaceBootstrapError, WorkspaceBootstrapReceiptV1, WorkspaceBootstrapRequestV1,
    WorkspaceBootstrapTransactionOperationV1, WorkspaceBootstrapTransactionReceiptV1,
    WorkspaceBootstrapTransactionRequestV1, MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1,
    MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1, MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1,
    MAX_RELEASE_BOOTSTRAP_TRANSACTION_STASH_BYTES_V1, RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1,
    RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH, RELEASE_BOOTSTRAP_STATE_SCHEMA_V1,
    RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1,
    RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1,
    RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1, RELEASE_BOOTSTRAP_TRANSACTION_SCHEMA_V1,
    ZZZ_BOX_STATE_RELATIVE_PATH,
};
pub use workspace_write_lease::{
    WorkspaceWriteLease, WorkspaceWriteLeaseError, WORKSPACE_WRITE_LOCK_RELATIVE_PATH,
};

pub const TASK_REQUEST_SCHEMA_V1: &str = "miho-task-request-v1";
pub const TASK_INTENT_SCHEMA_V1: &str = "miho-task-intent-v1";
pub const EXPORT_TASK_INTENT_SCHEMA_V1: &str = "miho-export-task-intent-v1";
pub const TASK_RECEIPT_SCHEMA_V1: &str = "miho-task-receipt-v1";
pub const TASK_FAILURE_SCHEMA_V1: &str = "miho-task-failure-v1";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum TaskOperationV1 {
    HsrExport,
    ZzzExport,
    Decision,
    Evidence,
    Coverage,
    PullValue,
    ReviewPacket,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExportIntentV1 {}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(
    tag = "operation",
    content = "params",
    rename_all = "kebab-case",
    deny_unknown_fields
)]
pub enum ExportTaskIntentSpecV1 {
    HsrExport(ExportIntentV1),
    ZzzExport(ExportIntentV1),
}

impl ExportTaskIntentSpecV1 {
    pub fn operation(&self) -> TaskOperationV1 {
        match self {
            Self::HsrExport(_) => TaskOperationV1::HsrExport,
            Self::ZzzExport(_) => TaskOperationV1::ZzzExport,
        }
    }
}

/// Strict pathless wire intent for starting one native-configured export.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExportTaskIntentV1 {
    pub schema_version: String,
    pub task: ExportTaskIntentSpecV1,
}

impl ExportTaskIntentV1 {
    pub fn new(task: ExportTaskIntentSpecV1) -> Self {
        Self {
            schema_version: EXPORT_TASK_INTENT_SCHEMA_V1.to_owned(),
            task,
        }
    }

    pub fn operation(&self) -> TaskOperationV1 {
        self.task.operation()
    }

    fn validate(&self) -> anyhow::Result<()> {
        if self.schema_version != EXPORT_TASK_INTENT_SCHEMA_V1 {
            bail!(
                "unsupported export task intent schema {}; expected {}",
                self.schema_version,
                EXPORT_TASK_INTENT_SCHEMA_V1
            );
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DecisionIntentV1 {
    pub method: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct EvidenceIntentV1 {
    #[serde(default)]
    pub planned_slugs: Vec<String>,
    #[serde(default = "default_next_status")]
    pub plan_statuses: Vec<String>,
    #[serde(default)]
    pub limit: usize,
    #[serde(default = "default_min_a_app_rate")]
    pub min_a_app_rate: String,
    #[serde(default)]
    pub include_missing: bool,
}

impl Default for EvidenceIntentV1 {
    fn default() -> Self {
        Self {
            planned_slugs: Vec::new(),
            plan_statuses: default_next_status(),
            limit: 0,
            min_a_app_rate: default_min_a_app_rate(),
            include_missing: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CoverageIntentV1 {
    #[serde(default)]
    pub planned_slugs: Vec<String>,
    #[serde(default = "default_next_status")]
    pub plan_statuses: Vec<String>,
    #[serde(default)]
    pub limit: usize,
    #[serde(default = "default_min_a_app_rate")]
    pub min_a_app_rate: String,
}

impl Default for CoverageIntentV1 {
    fn default() -> Self {
        Self {
            planned_slugs: Vec::new(),
            plan_statuses: default_next_status(),
            limit: 0,
            min_a_app_rate: default_min_a_app_rate(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PullValueIntentV1 {
    #[serde(default = "default_pull_statuses")]
    pub plan_statuses: Vec<String>,
    #[serde(default)]
    pub planned_slugs: Vec<String>,
}

impl Default for PullValueIntentV1 {
    fn default() -> Self {
        Self {
            plan_statuses: default_pull_statuses(),
            planned_slugs: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ReviewPacketIntentV1 {
    #[serde(default = "default_pull_statuses")]
    pub plan_statuses: Vec<String>,
    #[serde(default)]
    pub planned_slugs: Vec<String>,
}

impl Default for ReviewPacketIntentV1 {
    fn default() -> Self {
        Self {
            plan_statuses: default_pull_statuses(),
            planned_slugs: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(
    tag = "operation",
    content = "params",
    rename_all = "kebab-case",
    deny_unknown_fields
)]
pub enum TaskIntentSpecV1 {
    Decision(DecisionIntentV1),
    Evidence(EvidenceIntentV1),
    Coverage(CoverageIntentV1),
    PullValue(PullValueIntentV1),
    ReviewPacket(ReviewPacketIntentV1),
}

impl TaskIntentSpecV1 {
    pub fn operation(&self) -> TaskOperationV1 {
        match self {
            Self::Decision(_) => TaskOperationV1::Decision,
            Self::Evidence(_) => TaskOperationV1::Evidence,
            Self::Coverage(_) => TaskOperationV1::Coverage,
            Self::PullValue(_) => TaskOperationV1::PullValue,
            Self::ReviewPacket(_) => TaskOperationV1::ReviewPacket,
        }
    }
}

/// Strict pathless wire intent suitable for a Tauri/WebView boundary.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TaskIntentV1 {
    pub schema_version: String,
    pub task: TaskIntentSpecV1,
}

/// Native-only paths selected or authorized outside the WebView boundary.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeTaskPathsV1 {
    pub data_dir: PathBuf,
    pub box_path: PathBuf,
    pub rules_path: PathBuf,
    pub banner_plan_path: PathBuf,
    pub mechanism_notes_dir: PathBuf,
    pub decision_baseline_path: PathBuf,
}

impl TaskIntentV1 {
    pub fn new(task: TaskIntentSpecV1) -> Self {
        Self {
            schema_version: TASK_INTENT_SCHEMA_V1.to_owned(),
            task,
        }
    }

    pub fn operation(&self) -> TaskOperationV1 {
        self.task.operation()
    }

    pub fn validate(&self) -> anyhow::Result<()> {
        if self.schema_version != TASK_INTENT_SCHEMA_V1 {
            bail!(
                "unsupported task intent schema {}; expected {}",
                self.schema_version,
                TASK_INTENT_SCHEMA_V1
            );
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
/// Trusted filesystem layout constructed by a native CLI/Tauri adapter.
///
/// This is not a WebView wire type: browser-facing commands must resolve
/// pathless intents or opaque native selections before constructing it.
pub struct WorkspaceLayout {
    pub data_dir: PathBuf,
    pub box_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecisionTaskV1 {
    pub method: String,
    pub rules_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EvidenceTaskV1 {
    pub planned_slugs: Vec<String>,
    pub plan_path: Option<PathBuf>,
    pub plan_statuses: Vec<String>,
    pub output: Option<PathBuf>,
    pub limit: usize,
    pub min_a_app_rate: String,
    pub include_missing: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CoverageTaskV1 {
    pub planned_slugs: Vec<String>,
    pub plan_path: Option<PathBuf>,
    pub plan_statuses: Vec<String>,
    pub limit: usize,
    pub min_a_app_rate: String,
    pub current_output: Option<PathBuf>,
    pub target_output: Option<PathBuf>,
    pub aggregate_output: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PullTaskV1 {
    pub plan_path: PathBuf,
    pub plan_statuses: Vec<String>,
    pub planned_slugs: Vec<String>,
    pub mechanism_notes_dir: Option<PathBuf>,
    pub decision_baseline_path: PathBuf,
    pub output: Option<PathBuf>,
}

fn default_next_status() -> Vec<String> {
    vec!["next".to_owned()]
}

fn default_pull_statuses() -> Vec<String> {
    vec!["current".to_owned(), "next".to_owned()]
}

fn default_min_a_app_rate() -> String {
    "10.0".to_owned()
}

fn default_banner_plan() -> PathBuf {
    PathBuf::from("./configs/zzz_banner_plan.json")
}

fn default_decision_baseline() -> PathBuf {
    PathBuf::from("./configs/zzz_decision_baseline.json")
}

impl Default for EvidenceTaskV1 {
    fn default() -> Self {
        Self {
            planned_slugs: Vec::new(),
            plan_path: None,
            plan_statuses: default_next_status(),
            output: None,
            limit: 0,
            min_a_app_rate: default_min_a_app_rate(),
            include_missing: false,
        }
    }
}

impl Default for CoverageTaskV1 {
    fn default() -> Self {
        Self {
            planned_slugs: Vec::new(),
            plan_path: None,
            plan_statuses: default_next_status(),
            limit: 0,
            min_a_app_rate: default_min_a_app_rate(),
            current_output: None,
            target_output: None,
            aggregate_output: None,
        }
    }
}

impl Default for PullTaskV1 {
    fn default() -> Self {
        Self {
            plan_path: default_banner_plan(),
            plan_statuses: default_pull_statuses(),
            planned_slugs: Vec::new(),
            mechanism_notes_dir: None,
            decision_baseline_path: default_decision_baseline(),
            output: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum TaskSpecV1 {
    Decision(DecisionTaskV1),
    Evidence(EvidenceTaskV1),
    Coverage(CoverageTaskV1),
    PullValue(PullTaskV1),
    ReviewPacket(PullTaskV1),
}

impl TaskSpecV1 {
    pub fn operation(&self) -> TaskOperationV1 {
        match self {
            Self::Decision(_) => TaskOperationV1::Decision,
            Self::Evidence(_) => TaskOperationV1::Evidence,
            Self::Coverage(_) => TaskOperationV1::Coverage,
            Self::PullValue(_) => TaskOperationV1::PullValue,
            Self::ReviewPacket(_) => TaskOperationV1::ReviewPacket,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
/// Trusted native application request.
///
/// It deliberately retains arbitrary filesystem paths for CLI compatibility.
/// A future WebView IPC schema must be pathless/opaque and be adapted into this
/// request only after native path selection and authorization.
pub struct TaskRequestV1 {
    pub schema_version: String,
    pub workspace: WorkspaceLayout,
    pub task: TaskSpecV1,
}

impl TaskRequestV1 {
    pub fn new(workspace: WorkspaceLayout, task: TaskSpecV1) -> Self {
        Self {
            schema_version: TASK_REQUEST_SCHEMA_V1.to_owned(),
            workspace,
            task,
        }
    }

    pub fn operation(&self) -> TaskOperationV1 {
        self.task.operation()
    }

    fn validate(&self) -> anyhow::Result<()> {
        if self.schema_version != TASK_REQUEST_SCHEMA_V1 {
            bail!(
                "unsupported task request schema {}; expected {}",
                self.schema_version,
                TASK_REQUEST_SCHEMA_V1
            );
        }
        Ok(())
    }
}

/// Resolve a validated pathless intent with native-authorized paths.
///
/// UI intents cannot select arbitrary output paths: every operation uses its
/// existing application default beneath `data_dir` unless a trusted native
/// caller constructs `TaskRequestV1` directly.
pub fn resolve_task_intent_v1(intent: &TaskIntentV1, paths: &NativeTaskPathsV1) -> TaskRequestV1 {
    let workspace = WorkspaceLayout {
        data_dir: paths.data_dir.clone(),
        box_path: paths.box_path.clone(),
    };
    let task = match &intent.task {
        TaskIntentSpecV1::Decision(params) => TaskSpecV1::Decision(DecisionTaskV1 {
            method: params.method.clone(),
            rules_path: paths.rules_path.clone(),
        }),
        TaskIntentSpecV1::Evidence(params) => TaskSpecV1::Evidence(EvidenceTaskV1 {
            planned_slugs: params.planned_slugs.clone(),
            plan_path: Some(paths.banner_plan_path.clone()),
            plan_statuses: params.plan_statuses.clone(),
            output: None,
            limit: params.limit,
            min_a_app_rate: params.min_a_app_rate.clone(),
            include_missing: params.include_missing,
        }),
        TaskIntentSpecV1::Coverage(params) => TaskSpecV1::Coverage(CoverageTaskV1 {
            planned_slugs: params.planned_slugs.clone(),
            plan_path: Some(paths.banner_plan_path.clone()),
            plan_statuses: params.plan_statuses.clone(),
            limit: params.limit,
            min_a_app_rate: params.min_a_app_rate.clone(),
            current_output: None,
            target_output: None,
            aggregate_output: None,
        }),
        TaskIntentSpecV1::PullValue(params) => TaskSpecV1::PullValue(PullTaskV1 {
            plan_path: paths.banner_plan_path.clone(),
            plan_statuses: params.plan_statuses.clone(),
            planned_slugs: params.planned_slugs.clone(),
            mechanism_notes_dir: Some(paths.mechanism_notes_dir.clone()),
            decision_baseline_path: paths.decision_baseline_path.clone(),
            output: None,
        }),
        TaskIntentSpecV1::ReviewPacket(params) => TaskSpecV1::ReviewPacket(PullTaskV1 {
            plan_path: paths.banner_plan_path.clone(),
            plan_statuses: params.plan_statuses.clone(),
            planned_slugs: params.planned_slugs.clone(),
            mechanism_notes_dir: Some(paths.mechanism_notes_dir.clone()),
            decision_baseline_path: paths.decision_baseline_path.clone(),
            output: None,
        }),
    };
    TaskRequestV1::new(workspace, task)
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TaskReceiptV1 {
    pub schema_version: String,
    pub operation: TaskOperationV1,
    pub method_version: String,
    pub output_schema: String,
    pub local_datetime: String,
    pub outputs: Vec<PathBuf>,
    #[serde(default)]
    pub notices: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TaskFailureV1 {
    pub schema_version: String,
    pub operation: Option<TaskOperationV1>,
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

impl TaskFailureV1 {
    pub fn from_error(operation: Option<TaskOperationV1>, error: &anyhow::Error) -> Self {
        Self {
            schema_version: TASK_FAILURE_SCHEMA_V1.to_owned(),
            operation,
            code: "task.failed".to_owned(),
            message: format!("{error:#}"),
            retryable: false,
        }
    }

    fn request_error(operation: Option<TaskOperationV1>, code: &str, message: String) -> Self {
        Self {
            schema_version: TASK_FAILURE_SCHEMA_V1.to_owned(),
            operation,
            code: code.to_owned(),
            message,
            retryable: false,
        }
    }
}

/// Parse and validate an untrusted pathless intent into a structured boundary.
pub fn parse_task_intent_v1(bytes: &[u8]) -> Result<TaskIntentV1, TaskFailureV1> {
    let operation = identify_intent_operation(bytes);
    let intent = serde_json::from_slice::<TaskIntentV1>(bytes).map_err(|error| {
        TaskFailureV1::request_error(operation, "request.invalid", error.to_string())
    })?;
    intent.validate().map_err(|error| {
        TaskFailureV1::request_error(
            Some(intent.operation()),
            "request.unsupported_schema",
            error.to_string(),
        )
    })?;
    Ok(intent)
}

/// Parse and validate an untrusted pathless export intent. The wire document
/// carries only the game operation; every path and dataset setting comes from
/// a native-resolved workspace configuration.
pub fn parse_export_task_intent_v1(bytes: &[u8]) -> Result<ExportTaskIntentV1, TaskFailureV1> {
    let operation = identify_export_intent_operation(bytes);
    let intent = serde_json::from_slice::<ExportTaskIntentV1>(bytes).map_err(|error| {
        TaskFailureV1::request_error(operation, "request.invalid", error.to_string())
    })?;
    intent.validate().map_err(|error| {
        TaskFailureV1::request_error(
            Some(intent.operation()),
            "request.unsupported_schema",
            error.to_string(),
        )
    })?;
    Ok(intent)
}

fn identify_intent_operation(bytes: &[u8]) -> Option<TaskOperationV1> {
    let value = serde_json::from_slice::<serde_json::Value>(bytes).ok()?;
    serde_json::from_value(value.get("task")?.get("operation")?.clone()).ok()
}

fn identify_export_intent_operation(bytes: &[u8]) -> Option<TaskOperationV1> {
    let value = serde_json::from_slice::<serde_json::Value>(bytes).ok()?;
    match value.get("task")?.get("operation")?.as_str()? {
        "hsr-export" => Some(TaskOperationV1::HsrExport),
        "zzz-export" => Some(TaskOperationV1::ZzzExport),
        _ => None,
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AppInvocation {
    cwd: PathBuf,
    local_datetime: NaiveDateTime,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionControlError {
    Cancelled,
}

impl std::fmt::Display for ExecutionControlError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Cancelled => formatter.write_str("task execution cancelled before commit"),
        }
    }
}

impl std::error::Error for ExecutionControlError {}

pub trait ExecutionObserver: Send + Sync {
    /// Called immediately before the executor's only atomic installation.
    fn before_commit(&self) -> Result<(), ExecutionControlError>;
}

struct DirectExecutionObserver;

impl ExecutionObserver for DirectExecutionObserver {
    fn before_commit(&self) -> Result<(), ExecutionControlError> {
        Ok(())
    }
}

impl AppInvocation {
    pub fn capture() -> anyhow::Result<Self> {
        let cwd = std::env::current_dir().context("cannot capture report working directory")?;
        Self::capture_in(cwd)
    }

    pub fn capture_in(cwd: PathBuf) -> anyhow::Result<Self> {
        #[cfg(debug_assertions)]
        let now = if let Some(value) = std::env::var_os("MIHO_REPORT_LOCAL_DATETIME") {
            NaiveDateTime::parse_from_str(&value.to_string_lossy(), "%Y-%m-%dT%H:%M:%S%.f")
                .context("invalid MIHO_REPORT_LOCAL_DATETIME")?
        } else {
            Local::now().naive_local()
        };
        #[cfg(not(debug_assertions))]
        let now = Local::now().naive_local();
        Self::new(cwd, now)
    }

    pub fn new(cwd: PathBuf, local_datetime: NaiveDateTime) -> anyhow::Result<Self> {
        let nanos = local_datetime.nanosecond() / 1_000 * 1_000;
        let local_datetime = local_datetime
            .with_nanosecond(nanos)
            .context("cannot truncate report local datetime to microseconds")?;
        Ok(Self {
            cwd: lexical_absolute(&cwd)?,
            local_datetime,
        })
    }

    pub fn cwd(&self) -> &Path {
        &self.cwd
    }

    pub fn local_datetime(&self) -> NaiveDateTime {
        self.local_datetime
    }

    pub fn resolve(&self, path: &Path) -> PathBuf {
        lexical_normalize(if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.cwd.join(path)
        })
    }
}

fn lexical_absolute(path: &Path) -> anyhow::Result<PathBuf> {
    if path.is_absolute() {
        Ok(lexical_normalize(path.to_path_buf()))
    } else {
        Ok(lexical_normalize(
            std::env::current_dir()
                .context("cannot resolve application working directory")?
                .join(path),
        ))
    }
}

fn lexical_normalize(path: PathBuf) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                let _ = normalized.pop();
            }
            Component::Prefix(_) | Component::RootDir | Component::Normal(_) => {
                normalized.push(component.as_os_str());
            }
        }
    }
    normalized
}

pub fn execute_task_v1(
    request: &TaskRequestV1,
    invocation: &AppInvocation,
) -> anyhow::Result<TaskReceiptV1> {
    execute_task_observed_v1(request, invocation, &DirectExecutionObserver)
}

pub fn execute_task_observed_v1(
    request: &TaskRequestV1,
    invocation: &AppInvocation,
    observer: &dyn ExecutionObserver,
) -> anyhow::Result<TaskReceiptV1> {
    request.validate()?;
    let operation = request.operation();
    let (outputs, method_version, output_schema, notices) = match &request.task {
        TaskSpecV1::Decision(task) => run_decision(&request.workspace, task, invocation, observer)?,
        TaskSpecV1::Evidence(task) => run_evidence(&request.workspace, task, invocation, observer)?,
        TaskSpecV1::Coverage(task) => run_coverage(&request.workspace, task, invocation, observer)?,
        TaskSpecV1::PullValue(task) => run_pull_artifact(
            &request.workspace,
            task,
            invocation,
            PullArtifactKind::Report,
            observer,
        )?,
        TaskSpecV1::ReviewPacket(task) => run_pull_artifact(
            &request.workspace,
            task,
            invocation,
            PullArtifactKind::ReviewPacket,
            observer,
        )?,
    };
    Ok(TaskReceiptV1 {
        schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
        operation,
        method_version,
        output_schema,
        local_datetime: invocation
            .local_datetime
            .format("%Y-%m-%dT%H:%M:%S%.f")
            .to_string(),
        outputs,
        notices,
    })
}

pub fn execute_task_result_v1(
    request: &TaskRequestV1,
    invocation: &AppInvocation,
) -> Result<TaskReceiptV1, TaskFailureV1> {
    execute_task_v1(request, invocation)
        .map_err(|error| TaskFailureV1::from_error(Some(request.operation()), &error))
}

type RunResult = (Vec<PathBuf>, String, String, Vec<String>);

fn run_decision(
    workspace: &WorkspaceLayout,
    task: &DecisionTaskV1,
    invocation: &AppInvocation,
    observer: &dyn ExecutionObserver,
) -> anyhow::Result<RunResult> {
    if task.method != DECISION_LEGACY_METHOD {
        bail!("unsupported decision method");
    }
    let data_dir = invocation.resolve(&workspace.data_dir);
    let optional = |name: &str| read_optional_input(&data_dir.join(name));
    let rules_path = invocation.resolve(&task.rules_path);
    let inputs = DecisionLegacyInputsV0 {
        box_config: read_input(&invocation.resolve(&workspace.box_path))?,
        rules_config: read_optional_input(&rules_path)?,
        tier_current_csv: optional("prydwen_tier_current.csv")?,
        tier_history_csv: optional("prydwen_tier_history.csv")?,
        usage_csv: optional("character_usage_long.csv")?,
        team_raw_csv: optional("team_rank_raw.csv")?,
        name_map_csv: optional("name_map.csv")?,
        changelog_history_csv: optional("prydwen_tier_changelog_history.csv")?,
    };
    let result = build_decision_legacy_v0(
        &inputs,
        &DecisionLegacyRequestV0 {
            method: DECISION_LEGACY_METHOD.to_owned(),
        },
    )?;
    let json = String::from_utf8(render_decision_json_legacy_v0(&result)?)
        .context("legacy decision JSON renderer returned invalid UTF-8")?;
    let markdown = render_decision_markdown_legacy_v0(
        &result,
        &DecisionLegacyContextV0 {
            local_datetime: invocation.local_datetime,
        },
    );
    let outputs = vec![
        data_dir.join("decision_cards.json"),
        data_dir.join("decision_report.md"),
    ];
    commit_batch(
        observer,
        &[
            (outputs[0].clone(), platform_text_bytes(&json)),
            (outputs[1].clone(), platform_text_bytes(&markdown)),
        ],
    )?;
    Ok((
        outputs,
        DECISION_LEGACY_METHOD.to_owned(),
        "decision-legacy-v0-json+markdown".to_owned(),
        vec![
            "legacy-v0 compatibility only: formal evidence-first advice is provided by pull-value"
                .to_owned(),
        ],
    ))
}

fn run_evidence(
    workspace: &WorkspaceLayout,
    task: &EvidenceTaskV1,
    invocation: &AppInvocation,
    observer: &dyn ExecutionObserver,
) -> anyhow::Result<RunResult> {
    let data_dir = invocation.resolve(&workspace.data_dir);
    let inputs = load_evidence_inputs(
        &data_dir,
        &invocation.resolve(&workspace.box_path),
        task.plan_path
            .as_deref()
            .map(|path| invocation.resolve(path)),
    )?;
    let (default_min_a_app_rate, min_a_app_rate_by_mode) =
        parse_min_a_app_rate(&task.min_a_app_rate)?;
    let bundle = build_evidence_bundle_v1(
        &inputs,
        &EvidenceRequestV1 {
            game: EvidenceGameV1::Zzz,
            explicit_planned_slugs: task.planned_slugs.clone(),
            plan_statuses: task.plan_statuses.clone(),
            include_missing: task.include_missing,
            default_min_a_app_rate,
            min_a_app_rate_by_mode,
            ..EvidenceRequestV1::default()
        },
        &EvidenceContextV1 {
            local_datetime: invocation.local_datetime,
        },
    )?;
    let team_source = data_dir.join("team_rank_dedup_unordered.csv");
    let markdown = render_coverage_markdown_v1(
        &bundle.target,
        "绝区零目标账号证据池队伍覆盖",
        &team_source.to_string_lossy(),
        task.limit,
    );
    let output = task
        .output
        .as_deref()
        .map(|path| invocation.resolve(path))
        .unwrap_or_else(|| data_dir.join("evidence_pool_summary.md"));
    commit_batch(
        observer,
        &[(output.clone(), platform_text_bytes(&markdown))],
    )?;
    Ok((
        vec![output],
        EVIDENCE_METHOD_VERSION.to_owned(),
        "evidence-v1-markdown".to_owned(),
        Vec::new(),
    ))
}

fn run_coverage(
    workspace: &WorkspaceLayout,
    task: &CoverageTaskV1,
    invocation: &AppInvocation,
    observer: &dyn ExecutionObserver,
) -> anyhow::Result<RunResult> {
    let data_dir = invocation.resolve(&workspace.data_dir);
    let inputs = load_evidence_inputs(
        &data_dir,
        &invocation.resolve(&workspace.box_path),
        task.plan_path
            .as_deref()
            .map(|path| invocation.resolve(path)),
    )?;
    let (default_min_a_app_rate, min_a_app_rate_by_mode) =
        parse_min_a_app_rate(&task.min_a_app_rate)?;
    let bundle = build_evidence_bundle_v1(
        &inputs,
        &EvidenceRequestV1 {
            game: EvidenceGameV1::Zzz,
            explicit_planned_slugs: task.planned_slugs.clone(),
            plan_statuses: task.plan_statuses.clone(),
            default_min_a_app_rate,
            min_a_app_rate_by_mode,
            ..EvidenceRequestV1::default()
        },
        &EvidenceContextV1 {
            local_datetime: invocation.local_datetime,
        },
    )?;
    let team_source_path = data_dir.join("team_rank_dedup_unordered.csv");
    let team_source = team_source_path.to_string_lossy();
    let current = render_coverage_markdown_v1(
        &bundle.current,
        "当前 Box 队伍覆盖",
        &team_source,
        task.limit,
    );
    let target = render_coverage_markdown_v1(
        &bundle.target,
        "目标 Box 队伍覆盖",
        &team_source,
        task.limit,
    );
    let aggregate = render_aggregate_csv_v1(&bundle.target.aggregates)?;
    let outputs = vec![
        task.current_output
            .as_deref()
            .map(|path| invocation.resolve(path))
            .unwrap_or_else(|| data_dir.join("current_box_team_coverage.md")),
        task.target_output
            .as_deref()
            .map(|path| invocation.resolve(path))
            .unwrap_or_else(|| data_dir.join("target_box_team_coverage.md")),
        task.aggregate_output
            .as_deref()
            .map(|path| invocation.resolve(path))
            .unwrap_or_else(|| data_dir.join("team_signature_aggregates.csv")),
    ];
    commit_batch(
        observer,
        &[
            (outputs[0].clone(), platform_text_bytes(&current)),
            (outputs[1].clone(), platform_text_bytes(&target)),
            (outputs[2].clone(), aggregate),
        ],
    )?;
    Ok((
        outputs,
        EVIDENCE_METHOD_VERSION.to_owned(),
        "coverage-v1-markdown+csv".to_owned(),
        Vec::new(),
    ))
}

#[derive(Clone, Copy)]
enum PullArtifactKind {
    Report,
    ReviewPacket,
}

impl PullArtifactKind {
    fn filename(self, status: &str) -> String {
        match self {
            Self::Report => format!("{status}_pull_value_report.md"),
            Self::ReviewPacket => format!("{status}_gpt_pull_reviewer_packet.md"),
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Report => "pull-value",
            Self::ReviewPacket => "review-packet",
        }
    }

    fn output_schema(self) -> &'static str {
        match self {
            Self::Report => "pull-value-v1-markdown",
            Self::ReviewPacket => "review-packet-v1-markdown",
        }
    }
}

fn run_pull_artifact(
    workspace: &WorkspaceLayout,
    task: &PullTaskV1,
    invocation: &AppInvocation,
    artifact: PullArtifactKind,
    observer: &dyn ExecutionObserver,
) -> anyhow::Result<RunResult> {
    let data_dir = invocation.resolve(&workspace.data_dir);
    let box_path = invocation.resolve(&workspace.box_path);
    let plan_path = invocation.resolve(&task.plan_path);
    let mechanism_notes_dir = task
        .mechanism_notes_dir
        .as_deref()
        .map(|path| invocation.resolve(path))
        .unwrap_or_else(|| {
            plan_path
                .parent()
                .unwrap_or_else(|| Path::new(""))
                .join("zzz_mechanism_notes")
        });
    let decision_baseline_path = invocation.resolve(&task.decision_baseline_path);
    let statuses = if task.plan_statuses.is_empty() {
        default_pull_statuses()
    } else {
        task.plan_statuses.clone()
    };
    let context = PullValueContextV1 {
        local_datetime: invocation.local_datetime,
        data_dir: data_dir.to_string_lossy().into_owned(),
        box_path: box_path.to_string_lossy().into_owned(),
        plan_path: plan_path.to_string_lossy().into_owned(),
        mechanism_notes_dir: mechanism_notes_dir.to_string_lossy().into_owned(),
        decision_baseline_path: decision_baseline_path.to_string_lossy().into_owned(),
    };
    let output_specs = if let Some(output) = task.output.as_deref() {
        vec![(invocation.resolve(output), statuses.clone())]
    } else {
        let mut seen = BTreeSet::new();
        let mut outputs = Vec::with_capacity(statuses.len());
        for status in statuses.iter().cloned() {
            let safe_status = miho_core::normalize::character_slug(&status);
            let safe_status = if safe_status.is_empty() {
                "status".to_owned()
            } else {
                safe_status
            };
            let output = data_dir.join(artifact.filename(&safe_status));
            if !seen.insert(output.clone()) {
                bail!(
                    "plan statuses resolve to the same {} output: {}",
                    artifact.label(),
                    output.display()
                );
            }
            outputs.push((output, vec![status]));
        }
        outputs
    };
    let evidence = load_evidence_inputs(&data_dir, &box_path, Some(plan_path.clone()))?;
    let mut inputs = PullValueInputsV1 {
        evidence,
        usage_csv: read_optional_input(&data_dir.join("character_usage_long.csv"))?,
        mechanism_notes: BTreeMap::new(),
        decision_baseline: read_optional_input(&decision_baseline_path)?,
    };
    let candidate_scan = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: task.planned_slugs.clone(),
            plan_statuses: statuses,
            ..PullValueRequestV1::default()
        },
        &context,
    )?;
    let reviewed_slugs = candidate_scan
        .summary
        .reviewed_slugs
        .into_iter()
        .collect::<BTreeSet<_>>();
    inputs.mechanism_notes = load_mechanism_note_inputs(&mechanism_notes_dir, &reviewed_slugs)?;
    let mut rendered = Vec::with_capacity(output_specs.len());
    for (output, plan_statuses) in output_specs {
        let bundle = build_pull_value_bundle_v1(
            &inputs,
            &PullValueRequestV1 {
                explicit_planned_slugs: task.planned_slugs.clone(),
                plan_statuses,
                ..PullValueRequestV1::default()
            },
            &context,
        )?;
        let markdown = match artifact {
            PullArtifactKind::Report => render_pull_value_markdown_v1(&bundle),
            PullArtifactKind::ReviewPacket => render_gpt_review_packet_v1(&bundle)?,
        };
        rendered.push((output, platform_text_bytes(&markdown)));
    }
    let outputs = rendered.iter().map(|(path, _)| path.clone()).collect();
    commit_batch(observer, &rendered)?;
    Ok((
        outputs,
        PULL_VALUE_METHOD_VERSION.to_owned(),
        artifact.output_schema().to_owned(),
        Vec::new(),
    ))
}

fn load_mechanism_note_inputs(
    root: &Path,
    reviewed_slugs: &BTreeSet<String>,
) -> anyhow::Result<BTreeMap<String, Vec<u8>>> {
    if reviewed_slugs.is_empty() || !root.is_dir() {
        return Ok(BTreeMap::new());
    }
    let mut by_extension = BTreeMap::<String, Vec<PathBuf>>::new();
    for entry in fs::read_dir(root)
        .with_context(|| format!("cannot read mechanism notes directory {}", root.display()))?
    {
        let path = entry
            .with_context(|| format!("cannot read mechanism notes directory {}", root.display()))?
            .path();
        let Some(extension) = path.extension().and_then(|value| value.to_str()) else {
            continue;
        };
        let extension = extension.to_ascii_lowercase();
        if matches!(extension.as_str(), "yaml" | "yml" | "json") {
            by_extension.entry(extension).or_default().push(path);
        }
    }
    let mut notes = BTreeMap::new();
    for extension in ["yaml", "yml", "json"] {
        let Some(paths) = by_extension.get_mut(extension) else {
            continue;
        };
        paths.sort();
        for path in paths {
            let stem = path
                .file_stem()
                .map(|value| value.to_string_lossy())
                .unwrap_or_default();
            let slug = miho_core::normalize::character_slug(&stem);
            if !reviewed_slugs.contains(&slug) {
                continue;
            }
            let bytes = read_input(path)?;
            validate_mechanism_note_v1(&bytes)?;
            notes.insert(slug, bytes);
        }
    }
    Ok(notes)
}

fn load_evidence_inputs(
    data_dir: &Path,
    box_path: &Path,
    plan_path: Option<PathBuf>,
) -> anyhow::Result<EvidenceInputsV1> {
    Ok(EvidenceInputsV1 {
        team_rank_dedup_unordered_csv: read_input(&data_dir.join("team_rank_dedup_unordered.csv"))?,
        name_map_csv: read_optional_input(&data_dir.join("name_map.csv"))?,
        tier_csv: read_optional_input(&data_dir.join("prydwen_tier_current.csv"))?,
        box_json: read_input(box_path)?,
        banner_plan_json: plan_path.as_deref().map(read_input).transpose()?,
    })
}

fn read_input(path: &Path) -> anyhow::Result<Vec<u8>> {
    fs::read(path).with_context(|| format!("cannot read report input {}", path.display()))
}

fn read_optional_input(path: &Path) -> anyhow::Result<Option<Vec<u8>>> {
    if path.exists() {
        read_input(path).map(Some)
    } else {
        Ok(None)
    }
}

fn parse_min_a_app_rate(value: &str) -> anyhow::Result<(f64, BTreeMap<String, f64>)> {
    let text = value.trim();
    if text.is_empty() {
        return Ok((10.0, BTreeMap::new()));
    }
    if !text.contains('=') {
        return Ok((
            parse_non_negative_finite_threshold(text, "threshold")?,
            BTreeMap::new(),
        ));
    }
    let mut default = 10.0;
    let mut values = BTreeMap::new();
    for item in text
        .split([',', ';'])
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        let (key, raw_number) = item
            .split_once('=')
            .with_context(|| format!("invalid threshold item: {item}"))?;
        let mode = key.trim().to_ascii_lowercase();
        if mode.is_empty() {
            bail!("invalid threshold mode: {item}");
        }
        let number = parse_non_negative_finite_threshold(raw_number.trim(), item)?;
        if mode == "default" {
            default = number;
        }
        values.insert(mode, number);
    }
    if values.is_empty() {
        Ok((10.0, BTreeMap::new()))
    } else {
        Ok((default, values))
    }
}

fn parse_non_negative_finite_threshold(value: &str, label: &str) -> anyhow::Result<f64> {
    let number = value
        .parse::<f64>()
        .with_context(|| format!("invalid {label}: {value}"))?;
    if !number.is_finite() || number < 0.0 {
        bail!("invalid {label}: {value}");
    }
    Ok(number)
}

fn platform_text_bytes(text: &str) -> Vec<u8> {
    #[cfg(windows)]
    {
        text.replace('\n', "\r\n").into_bytes()
    }
    #[cfg(not(windows))]
    {
        text.as_bytes().to_vec()
    }
}

fn commit_batch(
    observer: &dyn ExecutionObserver,
    outputs: &[(PathBuf, Vec<u8>)],
) -> anyhow::Result<()> {
    observer.before_commit()?;
    atomic::write_batch(outputs)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn report_thresholds_match_python_scalar_and_mode_syntax() {
        assert_eq!(parse_min_a_app_rate("5").unwrap(), (5.0, BTreeMap::new()));
        let (default, modes) = parse_min_a_app_rate("sd=5; da=10, default=7").unwrap();
        assert_eq!(default, 7.0);
        assert_eq!(modes.get("sd"), Some(&5.0));
        assert_eq!(modes.get("da"), Some(&10.0));
        assert_eq!(modes.get("default"), Some(&7.0));
        assert!(parse_min_a_app_rate("sd=NaN").is_err());
        assert!(parse_min_a_app_rate("sd=-1").is_err());
    }
}
