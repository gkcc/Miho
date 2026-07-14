use std::{
    collections::{BTreeMap, BTreeSet},
    ffi::OsStr,
    fs::{self, OpenOptions},
    io::{self, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

use miho_core::{atomic, box_state::BoxState};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{WorkspaceWriteLease, WorkspaceWriteLeaseError};

pub const RELEASE_BOOTSTRAP_STATE_SCHEMA_V1: &str = "miho-release-bootstrap-state-v1";
pub const RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1: &str = "miho-release-bootstrap-receipt-v1";
pub const RELEASE_BOOTSTRAP_TRANSACTION_SCHEMA_V1: &str = "miho-release-bootstrap-transaction-v1";
pub const RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1: &str =
    "miho-release-bootstrap-transaction-receipt-v1";
pub const RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH: &str = ".miho/release-bootstrap-state-v1.json";
pub const ZZZ_BOX_STATE_RELATIVE_PATH: &str = ".miho/zzz_box_state.json";
pub const RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1: &str = "manifest-v1.json";
pub const RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1: &str = "before";
pub const MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1: u64 = 64 * 1024;
pub const MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1: u64 = 1024 * 1024;
pub const MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1: u64 = 64 * 1024;
pub const MAX_RELEASE_BOOTSTRAP_TRANSACTION_STASH_BYTES_V1: u64 =
    MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1
        + (CONFIG_SEEDS.len() as u64 + 1) * MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1;

const RELEASE_BOOTSTRAP_TRANSACTION_STAGE_PREFIX_V1: &str = ".miho-bootstrap-stage-v1-";
const RELEASE_BOOTSTRAP_TRANSACTION_COMMIT_QUARANTINE_PREFIX_V1: &str =
    ".miho-bootstrap-commit-quarantine-v1-";
const RELEASE_BOOTSTRAP_TRANSACTION_DISCARD_QUARANTINE_PREFIX_V1: &str =
    ".miho-bootstrap-discard-quarantine-v1-";
const RELEASE_BOOTSTRAP_TRANSACTION_COMMIT_COMPLETION_PREFIX_V1: &str =
    ".miho-bootstrap-commit-completed-v1-";
const RELEASE_BOOTSTRAP_TRANSACTION_DISCARD_COMPLETION_PREFIX_V1: &str =
    ".miho-bootstrap-discard-completed-v1-";
const TRANSACTION_DIRECTORY_PATHS_V1: &[&str] =
    &[".miho", "configs", "configs/zzz_mechanism_notes"];
static NEXT_TRANSACTION_STAGE_ID_V1: AtomicU64 = AtomicU64::new(0);

const CONFIG_SEEDS: &[SeedFile<'static>] = &[
    SeedFile::config(
        "configs/update_v1.json",
        include_bytes!("../../../configs/update_v1.json"),
    ),
    SeedFile::config(
        "configs/hsr_banner_plan.json",
        include_bytes!("../../../configs/hsr_banner_plan.json"),
    ),
    SeedFile::config(
        "configs/zzz_banner_plan.json",
        include_bytes!("../../../configs/zzz_banner_plan.json"),
    ),
    SeedFile::config(
        "configs/zzz_endgame_phase_overrides.json",
        include_bytes!("../../../configs/zzz_endgame_phase_overrides.json"),
    ),
    SeedFile::config(
        "configs/zzz_decision_rules.yaml",
        include_bytes!("../../../configs/zzz_decision_rules.yaml"),
    ),
    SeedFile::config(
        "configs/zzz_decision_baseline.json",
        include_bytes!("../../../configs/zzz_decision_baseline.json"),
    ),
    SeedFile::config(
        "configs/zzz_mechanism_notes/nom.yaml",
        include_bytes!("../../../configs/zzz_mechanism_notes/nom.yaml"),
    ),
    SeedFile::config(
        "configs/zzz_mechanism_notes/sunna.yaml",
        include_bytes!("../../../configs/zzz_mechanism_notes/sunna.yaml"),
    ),
    SeedFile::config(
        "configs/zzz_mechanism_notes/velina.yaml",
        include_bytes!("../../../configs/zzz_mechanism_notes/velina.yaml"),
    ),
    SeedFile::config(
        "configs/zzz_mechanism_notes/ye-shunguang.yaml",
        include_bytes!("../../../configs/zzz_mechanism_notes/ye-shunguang.yaml"),
    ),
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkspaceBootstrapRequestV1 {
    pub workspace: PathBuf,
}

impl WorkspaceBootstrapRequestV1 {
    pub fn new(workspace: PathBuf) -> Self {
        Self { workspace }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkspaceBootstrapTransactionRequestV1 {
    pub workspace: PathBuf,
    pub transaction: PathBuf,
}

impl WorkspaceBootstrapTransactionRequestV1 {
    pub fn new(workspace: PathBuf, transaction: PathBuf) -> Self {
        Self {
            workspace,
            transaction,
        }
    }
}

/// A pathless release-bootstrap result. Every listed path is a fixed,
/// workspace-relative allowlist member and therefore cannot disclose the
/// caller's workspace, username, or installation directory.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceBootstrapReceiptV1 {
    pub schema_version: String,
    pub installed: Vec<String>,
    pub upgraded: Vec<String>,
    pub preserved: Vec<String>,
    pub unchanged: Vec<String>,
    pub state_updated: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum WorkspaceBootstrapTransactionOperationV1 {
    Begin,
    Verify,
    Rollback,
    Commit,
    Discard,
    Finalize,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum WorkspaceBootstrapCompletedOperationV1 {
    Commit,
    Discard,
}

impl WorkspaceBootstrapCompletedOperationV1 {
    fn transaction_operation(self) -> WorkspaceBootstrapTransactionOperationV1 {
        match self {
            Self::Commit => WorkspaceBootstrapTransactionOperationV1::Commit,
            Self::Discard => WorkspaceBootstrapTransactionOperationV1::Discard,
        }
    }

    fn workspace_expectation(self) -> TransactionWorkspaceExpectationV1 {
        match self {
            Self::Commit => TransactionWorkspaceExpectationV1::Post,
            Self::Discard => TransactionWorkspaceExpectationV1::Before,
        }
    }
}

/// A pathless transaction result. Counts always refer to the fixed release
/// bootstrap allowlist; no caller-controlled path is serialized.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceBootstrapTransactionReceiptV1 {
    pub schema_version: String,
    pub operation: WorkspaceBootstrapTransactionOperationV1,
    pub files_verified: u32,
    pub files_restored: u32,
    pub files_removed: u32,
    pub transaction_cleaned: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bootstrap: Option<WorkspaceBootstrapReceiptV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completed_operation: Option<WorkspaceBootstrapCompletedOperationV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completion_marker_removed: Option<bool>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkspaceBootstrapError {
    WorkspaceBusy,
    UnsafeWorkspace,
    WorkspaceUnavailable,
    UnsafeTarget,
    TargetTooLarge,
    TargetReadFailed,
    InvalidState,
    StateTooLarge,
    SerializationFailed,
    CommitFailed,
    UnsafeTransaction,
    TransactionUnavailable,
    TransactionOverlap,
    TransactionNotEmpty,
    InvalidTransaction,
    TransactionTooLarge,
    TransactionDrift,
    TransactionVerificationFailed,
    TransactionRollbackFailed,
    TransactionCleanupFailed,
}

impl WorkspaceBootstrapError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::WorkspaceBusy => "workspace.write_busy",
            Self::UnsafeWorkspace => "workspace.write_unsafe",
            Self::WorkspaceUnavailable => "workspace.write_unavailable",
            Self::UnsafeTarget => "workspace.bootstrap_target_unsafe",
            Self::TargetTooLarge => "workspace.bootstrap_target_too_large",
            Self::TargetReadFailed => "workspace.bootstrap_target_read_failed",
            Self::InvalidState => "workspace.bootstrap_state_invalid",
            Self::StateTooLarge => "workspace.bootstrap_state_too_large",
            Self::SerializationFailed => "workspace.bootstrap_serialize_failed",
            Self::CommitFailed => "workspace.bootstrap_commit_failed",
            Self::UnsafeTransaction => "workspace.bootstrap_transaction_unsafe",
            Self::TransactionUnavailable => "workspace.bootstrap_transaction_unavailable",
            Self::TransactionOverlap => "workspace.bootstrap_transaction_overlap",
            Self::TransactionNotEmpty => "workspace.bootstrap_transaction_not_empty",
            Self::InvalidTransaction => "workspace.bootstrap_transaction_invalid",
            Self::TransactionTooLarge => "workspace.bootstrap_transaction_too_large",
            Self::TransactionDrift => "workspace.bootstrap_transaction_drift",
            Self::TransactionVerificationFailed => {
                "workspace.bootstrap_transaction_verification_failed"
            }
            Self::TransactionRollbackFailed => "workspace.bootstrap_transaction_rollback_failed",
            Self::TransactionCleanupFailed => "workspace.bootstrap_transaction_cleanup_failed",
        }
    }
}

impl std::fmt::Display for WorkspaceBootstrapError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for WorkspaceBootstrapError {}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ReleaseBootstrapStateV1 {
    schema_version: String,
    managed_files: BTreeMap<String, String>,
}

impl ReleaseBootstrapStateV1 {
    fn empty() -> Self {
        Self {
            schema_version: RELEASE_BOOTSTRAP_STATE_SCHEMA_V1.to_owned(),
            managed_files: BTreeMap::new(),
        }
    }

    fn validate(&self) -> Result<(), WorkspaceBootstrapError> {
        if self.schema_version != RELEASE_BOOTSTRAP_STATE_SCHEMA_V1 {
            return Err(WorkspaceBootstrapError::InvalidState);
        }
        let allowlist = seed_paths().collect::<BTreeSet<_>>();
        for (path, hash) in &self.managed_files {
            if !allowlist.contains(path.as_str()) || !is_lower_sha256(hash) {
                return Err(WorkspaceBootstrapError::InvalidState);
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SeedPolicy {
    UpgradeIfManaged,
    MissingOnly,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WorkspaceBootstrapPlanModeV1 {
    DirectMissingOnly,
    TransactionUpgradeManaged,
}

#[derive(Debug, Clone, Copy)]
struct SeedFile<'a> {
    relative_path: &'static str,
    bytes: &'a [u8],
    policy: SeedPolicy,
}

impl SeedFile<'static> {
    const fn config(relative_path: &'static str, bytes: &'static [u8]) -> Self {
        Self {
            relative_path,
            bytes,
            policy: SeedPolicy::UpgradeIfManaged,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum InspectedFile {
    Missing,
    Present(Vec<u8>),
}

#[derive(Debug)]
struct PlannedBootstrapFileV1 {
    relative_path: &'static str,
    before: InspectedFile,
    post: Vec<u8>,
}

#[derive(Debug)]
struct WorkspaceBootstrapPlanV1 {
    outputs: Vec<(PathBuf, Vec<u8>)>,
    files: Vec<PlannedBootstrapFileV1>,
    directories: Vec<PlannedBootstrapDirectoryV1>,
    receipt: WorkspaceBootstrapReceiptV1,
}

#[derive(Debug)]
struct PlannedBootstrapDirectoryV1 {
    relative_path: &'static str,
    before: InspectedDirectoryV1,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum InspectedDirectoryV1 {
    Missing,
    Present,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ReleaseBootstrapTransactionManifestV1 {
    schema_version: String,
    workspace_fingerprint: String,
    transaction_token: String,
    directories: Vec<ReleaseBootstrapTransactionDirectoryV1>,
    files: Vec<ReleaseBootstrapTransactionFileV1>,
    bootstrap_receipt: WorkspaceBootstrapReceiptV1,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ReleaseBootstrapTransactionDirectoryV1 {
    relative_path: String,
    before: ReleaseBootstrapDirectoryBeforeV1,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum ReleaseBootstrapDirectoryBeforeV1 {
    Missing,
    Present,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ReleaseBootstrapTransactionFileV1 {
    relative_path: String,
    before: ReleaseBootstrapBeforeImageV1,
    planned_post: ReleaseBootstrapFileDigestV1,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum ReleaseBootstrapBeforeImageV1 {
    Missing,
    Present {
        stash_file: String,
        size: u64,
        sha256: String,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ReleaseBootstrapFileDigestV1 {
    size: u64,
    sha256: String,
}

#[derive(Debug)]
struct LoadedBootstrapTransactionV1 {
    manifest: ReleaseBootstrapTransactionManifestV1,
    manifest_bytes: Vec<u8>,
    before_bytes: Vec<Option<Vec<u8>>>,
}

/// Install missing release workspace defaults without upgrading any existing
/// target or rewriting an existing ownership state.
///
/// The workspace-wide lease is acquired before any state or target
/// inspection. The complete plan is validated before one `atomic::write_batch`
/// installs both changed seeds and the ownership state.
pub fn bootstrap_workspace_v1(
    request: &WorkspaceBootstrapRequestV1,
) -> Result<WorkspaceBootstrapReceiptV1, WorkspaceBootstrapError> {
    bootstrap_workspace_with_apply_v1(request, |outputs| {
        atomic::write_batch(outputs).map_err(|_| WorkspaceBootstrapError::CommitFailed)
    })
}

fn bootstrap_workspace_with_apply_v1<F>(
    request: &WorkspaceBootstrapRequestV1,
    apply_batch: F,
) -> Result<WorkspaceBootstrapReceiptV1, WorkspaceBootstrapError>
where
    F: FnOnce(&[(PathBuf, Vec<u8>)]) -> Result<(), WorkspaceBootstrapError>,
{
    let lease = WorkspaceWriteLease::acquire(&request.workspace).map_err(map_lease_error)?;
    let workspace = lease.workspace_root();

    let plan =
        plan_workspace_bootstrap_v1(workspace, WorkspaceBootstrapPlanModeV1::DirectMissingOnly)?;
    apply_batch(&plan.outputs)?;
    Ok(plan.receipt)
}

fn plan_workspace_bootstrap_v1(
    workspace: &Path,
    mode: WorkspaceBootstrapPlanModeV1,
) -> Result<WorkspaceBootstrapPlanV1, WorkspaceBootstrapError> {
    let state_path = workspace.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH);
    let state_before = inspect_file(
        workspace,
        RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH,
        MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1,
        WorkspaceBootstrapError::StateTooLarge,
    )?;
    let loaded_state = match &state_before {
        InspectedFile::Missing => None,
        InspectedFile::Present(bytes) => {
            let state = serde_json::from_slice::<ReleaseBootstrapStateV1>(bytes)
                .map_err(|_| WorkspaceBootstrapError::InvalidState)?;
            state.validate()?;
            Some(state)
        }
    };

    let box_bytes = default_box_state_bytes()?;
    let box_seed = SeedFile {
        relative_path: ZZZ_BOX_STATE_RELATIVE_PATH,
        bytes: &box_bytes,
        policy: SeedPolicy::MissingOnly,
    };
    let config_policy = match mode {
        WorkspaceBootstrapPlanModeV1::DirectMissingOnly => SeedPolicy::MissingOnly,
        WorkspaceBootstrapPlanModeV1::TransactionUpgradeManaged => SeedPolicy::UpgradeIfManaged,
    };
    let seeds = CONFIG_SEEDS
        .iter()
        .map(|seed| SeedFile {
            relative_path: seed.relative_path,
            bytes: seed.bytes,
            policy: config_policy,
        })
        .chain(std::iter::once(box_seed))
        .collect::<Vec<_>>();

    // Inspect every allowlisted target before planning any output. A malformed,
    // oversized, non-regular, symlink, or reparse target aborts with no batch.
    let inspected = seeds
        .iter()
        .map(|seed| {
            inspect_file(
                workspace,
                seed.relative_path,
                MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1,
                WorkspaceBootstrapError::TargetTooLarge,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let directories = transaction_directory_paths_v1()
        .map(|relative_path| {
            Ok(PlannedBootstrapDirectoryV1 {
                relative_path,
                before: inspect_directory_v1(workspace, relative_path)?,
            })
        })
        .collect::<Result<Vec<_>, WorkspaceBootstrapError>>()?;

    let mut desired_state = loaded_state
        .clone()
        .unwrap_or_else(ReleaseBootstrapStateV1::empty);
    let mut outputs = Vec::<(PathBuf, Vec<u8>)>::new();
    let mut files = Vec::<PlannedBootstrapFileV1>::new();
    let mut receipt = WorkspaceBootstrapReceiptV1 {
        schema_version: RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1.to_owned(),
        installed: Vec::new(),
        upgraded: Vec::new(),
        preserved: Vec::new(),
        unchanged: Vec::new(),
        state_updated: false,
    };

    for (seed, inspected_file) in seeds.iter().zip(inspected) {
        let seed_hash = sha256_hex(seed.bytes);
        let before = inspected_file.clone();
        let post = match inspected_file {
            InspectedFile::Missing => {
                outputs.push((workspace.join(seed.relative_path), seed.bytes.to_vec()));
                // Any missing target created by this exact batch must be
                // claimed by the state installed in the same atomic batch.
                // Existing target bytes and unrelated state entries remain
                // untouched; only a target proven Missing above is rebound.
                desired_state
                    .managed_files
                    .insert(seed.relative_path.to_owned(), seed_hash);
                receipt.installed.push(seed.relative_path.to_owned());
                seed.bytes.to_vec()
            }
            InspectedFile::Present(bytes) => {
                let current_hash = sha256_hex(&bytes);
                let managed_hash = desired_state.managed_files.get(seed.relative_path);
                match seed.policy {
                    SeedPolicy::UpgradeIfManaged
                        if managed_hash.is_some_and(|hash| hash == &current_hash) =>
                    {
                        if current_hash == seed_hash {
                            receipt.unchanged.push(seed.relative_path.to_owned());
                            bytes
                        } else {
                            outputs.push((workspace.join(seed.relative_path), seed.bytes.to_vec()));
                            desired_state
                                .managed_files
                                .insert(seed.relative_path.to_owned(), seed_hash);
                            receipt.upgraded.push(seed.relative_path.to_owned());
                            seed.bytes.to_vec()
                        }
                    }
                    SeedPolicy::MissingOnly
                        if managed_hash.is_some_and(|hash| hash == &current_hash) =>
                    {
                        receipt.unchanged.push(seed.relative_path.to_owned());
                        bytes
                    }
                    _ => {
                        receipt.preserved.push(seed.relative_path.to_owned());
                        bytes
                    }
                }
            }
        };
        files.push(PlannedBootstrapFileV1 {
            relative_path: seed.relative_path,
            before,
            post,
        });
    }

    let state_updated = loaded_state.as_ref() != Some(&desired_state);
    let state_post = if state_updated {
        let bytes = serialize_json_line(&desired_state)?;
        outputs.push((state_path, bytes.clone()));
        receipt.state_updated = true;
        bytes
    } else {
        match &state_before {
            InspectedFile::Present(bytes) => bytes.clone(),
            InspectedFile::Missing => return Err(WorkspaceBootstrapError::InvalidState),
        }
    };
    files.push(PlannedBootstrapFileV1 {
        relative_path: RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH,
        before: state_before,
        post: state_post,
    });

    Ok(WorkspaceBootstrapPlanV1 {
        outputs,
        files,
        directories,
        receipt,
    })
}

/// Persist a complete before/planned-post transaction and then apply the
/// existing release bootstrap batch. A failed apply deliberately leaves the
/// verified transaction untouched for a later idempotent rollback.
pub fn begin_workspace_bootstrap_transaction_v1(
    request: &WorkspaceBootstrapTransactionRequestV1,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
    begin_workspace_bootstrap_transaction_with_io_v1(
        request,
        |outputs| atomic::write_batch(outputs).map_err(|_| WorkspaceBootstrapError::CommitFailed),
        |_, path, bytes| write_new_synced_file_v1(path, bytes),
        publish_transaction_stage_v1,
    )
}

#[cfg(test)]
fn begin_workspace_bootstrap_transaction_with_apply_v1<F>(
    request: &WorkspaceBootstrapTransactionRequestV1,
    apply_batch: F,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError>
where
    F: FnOnce(&[(PathBuf, Vec<u8>)]) -> Result<(), WorkspaceBootstrapError>,
{
    begin_workspace_bootstrap_transaction_with_io_v1(
        request,
        apply_batch,
        |_, path, bytes| write_new_synced_file_v1(path, bytes),
        publish_transaction_stage_v1,
    )
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TransactionPersistPointV1 {
    Stash(usize),
    Manifest,
}

fn begin_workspace_bootstrap_transaction_with_io_v1<F, W, P>(
    request: &WorkspaceBootstrapTransactionRequestV1,
    apply_batch: F,
    mut write_file: W,
    mut publish_stage: P,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError>
where
    F: FnOnce(&[(PathBuf, Vec<u8>)]) -> Result<(), WorkspaceBootstrapError>,
    W: FnMut(TransactionPersistPointV1, &Path, &[u8]) -> Result<(), WorkspaceBootstrapError>,
    P: FnMut(&Path, &Path) -> Result<(), WorkspaceBootstrapError>,
{
    let lease = WorkspaceWriteLease::acquire(&request.workspace).map_err(map_lease_error)?;
    let workspace = lease.workspace_root();
    let location = transaction_location_v1(workspace, &request.transaction)?;
    require_new_transaction_destination_v1(&location)?;

    // Planning deliberately precedes stage creation. A malformed workspace
    // therefore cannot leave a transaction-looking root behind.
    let plan = plan_workspace_bootstrap_v1(
        workspace,
        WorkspaceBootstrapPlanModeV1::TransactionUpgradeManaged,
    )?;
    let manifest = build_transaction_manifest_v1(workspace, &location.transaction_token, &plan)?;
    let transaction_stage = create_unique_transaction_stage_v1(&location)?;
    persist_transaction_v1(&transaction_stage, &manifest, &plan.files, &mut write_file)?;

    // Full strict reload is the durable hand-off point. Workspace mutation is
    // forbidden until every declared stash and manifest field re-verifies.
    let loaded = load_transaction_v1(workspace, &transaction_stage, &location.transaction_token)?;
    verify_loaded_transaction_matches_plan_v1(&loaded, &manifest, &plan.files)?;
    require_new_transaction_destination_v1(&location)?;
    publish_stage(&transaction_stage, &location.root)?;
    sync_directory_v1(&location.parent)?;
    let published = load_transaction_v1(workspace, &location.root, &location.transaction_token)?;
    verify_loaded_transaction_matches_plan_v1(&published, &manifest, &plan.files)?;
    apply_batch(&plan.outputs)?;
    verify_workspace_matches_post_v1(workspace, &manifest)?;
    let loaded_after_apply =
        load_transaction_v1(workspace, &location.root, &location.transaction_token)?;
    verify_loaded_transaction_matches_plan_v1(&loaded_after_apply, &manifest, &plan.files)?;

    Ok(transaction_receipt_v1(
        WorkspaceBootstrapTransactionOperationV1::Begin,
        transaction_file_count_v1() as u32,
        0,
        0,
        false,
        Some(plan.receipt),
    ))
}

pub fn verify_workspace_bootstrap_transaction_v1(
    request: &WorkspaceBootstrapTransactionRequestV1,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
    let lease = WorkspaceWriteLease::acquire(&request.workspace).map_err(map_lease_error)?;
    let workspace = lease.workspace_root();
    let location = transaction_location_v1(workspace, &request.transaction)?;
    let loaded = load_transaction_v1(workspace, &location.root, &location.transaction_token)?;
    verify_workspace_matches_post_v1(workspace, &loaded.manifest)?;
    Ok(transaction_receipt_v1(
        WorkspaceBootstrapTransactionOperationV1::Verify,
        transaction_file_count_v1() as u32,
        0,
        0,
        false,
        None,
    ))
}

pub fn rollback_workspace_bootstrap_transaction_v1(
    request: &WorkspaceBootstrapTransactionRequestV1,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
    let lease = WorkspaceWriteLease::acquire(&request.workspace).map_err(map_lease_error)?;
    let workspace = lease.workspace_root();
    let location = transaction_location_v1(workspace, &request.transaction)?;
    let loaded = load_transaction_v1(workspace, &location.root, &location.transaction_token)?;
    let current = inspect_transaction_workspace_files_v1(workspace)?;

    // Preflight all twelve files before any restoration. This is the critical
    // user-drift gate: a single third state makes rollback a zero-write error.
    for ((entry, before_bytes), current_file) in loaded
        .manifest
        .files
        .iter()
        .zip(&loaded.before_bytes)
        .zip(&current)
    {
        if !matches_before_v1(entry, before_bytes.as_deref(), current_file)
            && !matches_post_v1(entry, current_file)
        {
            return Err(WorkspaceBootstrapError::TransactionDrift);
        }
    }
    preflight_rollback_directories_v1(workspace, &loaded, &current)?;

    let mut outputs = Vec::<(PathBuf, Vec<u8>)>::new();
    for (((entry, before_bytes), current_file), relative_path) in loaded
        .manifest
        .files
        .iter()
        .zip(&loaded.before_bytes)
        .zip(&current)
        .zip(transaction_paths_v1())
    {
        if let Some(bytes) = before_bytes {
            if !matches_before_v1(entry, Some(bytes), current_file) {
                outputs.push((workspace.join(relative_path), bytes.clone()));
            }
        }
    }
    let restored = outputs.len() as u32;
    atomic::write_batch(&outputs)
        .map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?;

    let mut removed = 0_u32;
    for ((entry, current_file), relative_path) in loaded
        .manifest
        .files
        .iter()
        .zip(&current)
        .zip(transaction_paths_v1())
    {
        if !matches!(entry.before, ReleaseBootstrapBeforeImageV1::Missing) {
            continue;
        }
        match current_file {
            InspectedFile::Missing => {}
            InspectedFile::Present(_) if matches_post_v1(entry, current_file) => {
                remove_workspace_post_file_v1(workspace, relative_path, &entry.planned_post)?;
                removed += 1;
            }
            InspectedFile::Present(_) => return Err(WorkspaceBootstrapError::TransactionDrift),
        }
    }

    restore_missing_directories_v1(workspace, &loaded)?;
    verify_workspace_matches_before_v1(workspace, &loaded)?;
    Ok(transaction_receipt_v1(
        WorkspaceBootstrapTransactionOperationV1::Rollback,
        transaction_file_count_v1() as u32,
        restored,
        removed,
        false,
        None,
    ))
}

pub fn commit_workspace_bootstrap_transaction_v1(
    request: &WorkspaceBootstrapTransactionRequestV1,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
    finish_workspace_bootstrap_transaction_with_io_v1(
        request,
        WorkspaceBootstrapTransactionOperationV1::Commit,
        TransactionWorkspaceExpectationV1::Post,
        rename_transaction_to_quarantine_v1,
        |_, _| Ok(()),
    )
}

/// Discard rollback evidence only after the workspace has returned to the
/// complete before state. Like commit, cleanup is restartable after every
/// individual removal step.
pub fn discard_workspace_bootstrap_transaction_v1(
    request: &WorkspaceBootstrapTransactionRequestV1,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
    finish_workspace_bootstrap_transaction_with_io_v1(
        request,
        WorkspaceBootstrapTransactionOperationV1::Discard,
        TransactionWorkspaceExpectationV1::Before,
        rename_transaction_to_quarantine_v1,
        |_, _| Ok(()),
    )
}

/// Acknowledge a durable caller-side completed phase and remove only the
/// matching completion marker. Commit/discard deliberately retain that marker
/// until this separate call so a process death before the caller persists its
/// phase cannot turn a completed transaction into an ambiguous absence.
pub fn finalize_workspace_bootstrap_transaction_v1(
    request: &WorkspaceBootstrapTransactionRequestV1,
    completed_operation: WorkspaceBootstrapCompletedOperationV1,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
    let lease = WorkspaceWriteLease::acquire(&request.workspace).map_err(map_lease_error)?;
    let workspace = lease.workspace_root();
    let location = transaction_location_v1(workspace, &request.transaction)?;
    let operation = completed_operation.transaction_operation();
    let opposite_operation = match completed_operation {
        WorkspaceBootstrapCompletedOperationV1::Commit => {
            WorkspaceBootstrapTransactionOperationV1::Discard
        }
        WorkspaceBootstrapCompletedOperationV1::Discard => {
            WorkspaceBootstrapTransactionOperationV1::Commit
        }
    };
    let quarantine = transaction_quarantine_path_v1(&location, operation)?;
    let opposite_quarantine = transaction_quarantine_path_v1(&location, opposite_operation)?;
    let completion = transaction_completion_marker_path_v1(&location, operation)?;
    let opposite_completion = transaction_completion_marker_path_v1(&location, opposite_operation)?;

    // Finalize is intentionally narrow: any live final root, either cleanup
    // quarantine, or an opposite-operation marker is a third state. It must
    // never guess which evidence the caller intended to acknowledge.
    if optional_safe_directory_exists_v1(&location.root)?
        || optional_safe_directory_exists_v1(&quarantine)?
        || optional_safe_directory_exists_v1(&opposite_quarantine)?
        || optional_safe_file_exists_v1(&opposite_completion)?
    {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }

    let marker_present = optional_safe_file_exists_v1(&completion)?;
    let files_verified = if marker_present {
        let (manifest, manifest_bytes) =
            load_completion_marker_v1(workspace, &completion, &location.transaction_token)?;
        verify_workspace_matches_expectation_v1(
            workspace,
            &manifest,
            completed_operation.workspace_expectation(),
        )?;
        let current = read_safe_transaction_file_v1(
            &completion,
            MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1,
        )?;
        if current != manifest_bytes {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
        fs::remove_file(&completion)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        sync_directory_v1(&location.parent)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        if optional_safe_file_exists_v1(&completion)? {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
        transaction_file_count_v1() as u32
    } else {
        // Idempotent absence is meaningful only because the external caller
        // promises to invoke finalize from its durable completed phase. Rust
        // cannot re-verify removed manifest bytes and therefore reports zero.
        0
    };

    let mut receipt = transaction_receipt_v1(
        WorkspaceBootstrapTransactionOperationV1::Finalize,
        files_verified,
        0,
        0,
        true,
        None,
    );
    receipt.completed_operation = Some(completed_operation);
    receipt.completion_marker_removed = Some(marker_present);
    Ok(receipt)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TransactionWorkspaceExpectationV1 {
    Before,
    Post,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TransactionCleanupPointV1 {
    Stash(usize),
    BeforeDirectory,
    Manifest,
    Root,
}

fn finish_workspace_bootstrap_transaction_with_io_v1<R, C>(
    request: &WorkspaceBootstrapTransactionRequestV1,
    operation: WorkspaceBootstrapTransactionOperationV1,
    expectation: TransactionWorkspaceExpectationV1,
    mut rename_root: R,
    mut before_cleanup: C,
) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError>
where
    R: FnMut(&Path, &Path) -> Result<(), WorkspaceBootstrapError>,
    C: FnMut(TransactionCleanupPointV1, &Path) -> Result<(), WorkspaceBootstrapError>,
{
    let lease = WorkspaceWriteLease::acquire(&request.workspace).map_err(map_lease_error)?;
    let workspace = lease.workspace_root();
    let location = transaction_location_v1(workspace, &request.transaction)?;
    let quarantine = transaction_quarantine_path_v1(&location, operation)?;
    let completion = transaction_completion_marker_path_v1(&location, operation)?;
    let opposite_operation = match operation {
        WorkspaceBootstrapTransactionOperationV1::Commit => {
            WorkspaceBootstrapTransactionOperationV1::Discard
        }
        WorkspaceBootstrapTransactionOperationV1::Discard => {
            WorkspaceBootstrapTransactionOperationV1::Commit
        }
        _ => return Err(WorkspaceBootstrapError::InvalidTransaction),
    };
    let opposite = transaction_quarantine_path_v1(&location, opposite_operation)?;
    let opposite_completion = transaction_completion_marker_path_v1(&location, opposite_operation)?;
    if optional_safe_directory_exists_v1(&opposite)?
        || optional_safe_file_exists_v1(&opposite_completion)?
    {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }

    let final_exists = optional_safe_directory_exists_v1(&location.root)?;
    let quarantine_exists = optional_safe_directory_exists_v1(&quarantine)?;
    let completion_exists = optional_safe_file_exists_v1(&completion)?;
    if final_exists && (quarantine_exists || completion_exists) {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    if final_exists {
        let loaded = load_transaction_v1(workspace, &location.root, &location.transaction_token)?;
        verify_workspace_matches_expectation_v1(workspace, &loaded.manifest, expectation)?;
        rename_root(&location.root, &quarantine)?;
        sync_directory_v1(&location.parent)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;

        // A strict reload after the atomic rename proves that the quarantine
        // is exactly the evidence that was just authorized for cleanup.
        let quarantined = load_transaction_v1(workspace, &quarantine, &location.transaction_token)?;
        if quarantined.manifest != loaded.manifest
            || quarantined.manifest_bytes != loaded.manifest_bytes
            || quarantined.before_bytes != loaded.before_bytes
        {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
    } else if !quarantine_exists && !completion_exists {
        return Err(WorkspaceBootstrapError::TransactionUnavailable);
    }

    let completed = optional_safe_file_exists_v1(&completion)?;
    let completed_manifest = if completed {
        Some(load_completion_marker_v1(
            workspace,
            &completion,
            &location.transaction_token,
        )?)
    } else {
        None
    };
    let quarantine_exists = optional_safe_directory_exists_v1(&quarantine)?;
    let removed = if quarantine_exists {
        let cleanup =
            load_cleanup_quarantine_v1(workspace, &quarantine, &location.transaction_token)?;
        if cleanup.manifest.is_some() && completed_manifest.is_some() {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
        let authoritative = cleanup
            .manifest
            .as_ref()
            .or_else(|| completed_manifest.as_ref().map(|(manifest, _)| manifest))
            .ok_or(WorkspaceBootstrapError::TransactionCleanupFailed)?;
        verify_workspace_matches_expectation_v1(workspace, authoritative, expectation)?;
        cleanup_transaction_quarantine_v1(workspace, cleanup, &completion, &mut before_cleanup)?
    } else {
        let (manifest, _) = completed_manifest
            .as_ref()
            .ok_or(WorkspaceBootstrapError::TransactionCleanupFailed)?;
        verify_workspace_matches_expectation_v1(workspace, manifest, expectation)?;
        0
    };
    let (completed_manifest, _) =
        load_completion_marker_v1(workspace, &completion, &location.transaction_token)?;
    verify_workspace_matches_expectation_v1(workspace, &completed_manifest, expectation)?;
    Ok(transaction_receipt_v1(
        operation,
        transaction_file_count_v1() as u32,
        0,
        removed,
        true,
        None,
    ))
}

fn transaction_receipt_v1(
    operation: WorkspaceBootstrapTransactionOperationV1,
    files_verified: u32,
    files_restored: u32,
    files_removed: u32,
    transaction_cleaned: bool,
    bootstrap: Option<WorkspaceBootstrapReceiptV1>,
) -> WorkspaceBootstrapTransactionReceiptV1 {
    WorkspaceBootstrapTransactionReceiptV1 {
        schema_version: RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1.to_owned(),
        operation,
        files_verified,
        files_restored,
        files_removed,
        transaction_cleaned,
        bootstrap,
        completed_operation: None,
        completion_marker_removed: None,
    }
}

fn verify_loaded_transaction_matches_plan_v1(
    loaded: &LoadedBootstrapTransactionV1,
    manifest: &ReleaseBootstrapTransactionManifestV1,
    plan_files: &[PlannedBootstrapFileV1],
) -> Result<(), WorkspaceBootstrapError> {
    if &loaded.manifest != manifest
        || loaded.before_bytes.len() != plan_files.len()
        || loaded
            .before_bytes
            .iter()
            .zip(plan_files)
            .any(
                |(loaded_before, planned)| match (&planned.before, loaded_before) {
                    (InspectedFile::Missing, None) => false,
                    (InspectedFile::Present(expected), Some(actual)) => expected != actual,
                    _ => true,
                },
            )
    {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    Ok(())
}

fn seed_paths() -> impl Iterator<Item = &'static str> {
    CONFIG_SEEDS
        .iter()
        .map(|seed| seed.relative_path)
        .chain(std::iter::once(ZZZ_BOX_STATE_RELATIVE_PATH))
}

fn transaction_paths_v1() -> impl Iterator<Item = &'static str> {
    seed_paths().chain(std::iter::once(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH))
}

fn transaction_directory_paths_v1() -> impl DoubleEndedIterator<Item = &'static str> {
    TRANSACTION_DIRECTORY_PATHS_V1.iter().copied()
}

fn transaction_file_count_v1() -> usize {
    CONFIG_SEEDS.len() + 2
}

fn transaction_file_limit_v1(relative_path: &str) -> Option<u64> {
    if relative_path == RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH {
        return Some(MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1);
    }
    seed_paths()
        .any(|allowed| allowed == relative_path)
        .then_some(MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1)
}

fn transaction_stash_file_v1(index: usize) -> String {
    format!("{RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1}/{index:02}.bin")
}

fn build_transaction_manifest_v1(
    workspace: &Path,
    transaction_token: &str,
    plan: &WorkspaceBootstrapPlanV1,
) -> Result<ReleaseBootstrapTransactionManifestV1, WorkspaceBootstrapError> {
    if !is_lower_sha256(transaction_token)
        || plan.files.len() != transaction_file_count_v1()
        || plan
            .files
            .iter()
            .map(|file| file.relative_path)
            .ne(transaction_paths_v1())
        || plan.directories.len() != TRANSACTION_DIRECTORY_PATHS_V1.len()
        || plan
            .directories
            .iter()
            .map(|directory| directory.relative_path)
            .ne(transaction_directory_paths_v1())
    {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }

    let mut total_before = 0_u64;
    let mut files = Vec::with_capacity(plan.files.len());
    for (index, file) in plan.files.iter().enumerate() {
        let limit = transaction_file_limit_v1(file.relative_path)
            .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
        if file.post.len() as u64 > limit {
            return Err(WorkspaceBootstrapError::TransactionTooLarge);
        }
        let before = match &file.before {
            InspectedFile::Missing => ReleaseBootstrapBeforeImageV1::Missing,
            InspectedFile::Present(bytes) => {
                if bytes.len() as u64 > limit {
                    return Err(WorkspaceBootstrapError::TransactionTooLarge);
                }
                total_before = total_before
                    .checked_add(bytes.len() as u64)
                    .ok_or(WorkspaceBootstrapError::TransactionTooLarge)?;
                ReleaseBootstrapBeforeImageV1::Present {
                    stash_file: transaction_stash_file_v1(index),
                    size: bytes.len() as u64,
                    sha256: sha256_hex(bytes),
                }
            }
        };
        files.push(ReleaseBootstrapTransactionFileV1 {
            relative_path: file.relative_path.to_owned(),
            before,
            planned_post: ReleaseBootstrapFileDigestV1 {
                size: file.post.len() as u64,
                sha256: sha256_hex(&file.post),
            },
        });
    }
    if total_before > MAX_RELEASE_BOOTSTRAP_TRANSACTION_STASH_BYTES_V1 {
        return Err(WorkspaceBootstrapError::TransactionTooLarge);
    }

    let directories = plan
        .directories
        .iter()
        .map(|directory| ReleaseBootstrapTransactionDirectoryV1 {
            relative_path: directory.relative_path.to_owned(),
            before: match directory.before {
                InspectedDirectoryV1::Missing => ReleaseBootstrapDirectoryBeforeV1::Missing,
                InspectedDirectoryV1::Present => ReleaseBootstrapDirectoryBeforeV1::Present,
            },
        })
        .collect();

    Ok(ReleaseBootstrapTransactionManifestV1 {
        schema_version: RELEASE_BOOTSTRAP_TRANSACTION_SCHEMA_V1.to_owned(),
        workspace_fingerprint: workspace_fingerprint_v1(workspace),
        transaction_token: transaction_token.to_owned(),
        directories,
        files,
        bootstrap_receipt: plan.receipt.clone(),
    })
}

fn persist_transaction_v1<W>(
    root: &Path,
    manifest: &ReleaseBootstrapTransactionManifestV1,
    plan_files: &[PlannedBootstrapFileV1],
    write_file: &mut W,
) -> Result<(), WorkspaceBootstrapError>
where
    W: FnMut(TransactionPersistPointV1, &Path, &[u8]) -> Result<(), WorkspaceBootstrapError>,
{
    require_empty_safe_directory_v1(root)?;
    let before_directory = root.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1);
    fs::create_dir(&before_directory)
        .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    require_safe_directory_v1(&before_directory)?;

    for (index, file) in plan_files.iter().enumerate() {
        let InspectedFile::Present(bytes) = &file.before else {
            continue;
        };
        let stash_path = before_directory.join(format!("{index:02}.bin"));
        write_file(TransactionPersistPointV1::Stash(index), &stash_path, bytes)?;
    }
    sync_directory_v1(&before_directory)?;

    let manifest_bytes = serialize_json_line(manifest)?;
    if manifest_bytes.len() as u64 > MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1 {
        return Err(WorkspaceBootstrapError::TransactionTooLarge);
    }
    write_file(
        TransactionPersistPointV1::Manifest,
        &root.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1),
        &manifest_bytes,
    )?;
    sync_directory_v1(root)?;
    Ok(())
}

#[derive(Debug, Clone)]
struct BootstrapTransactionLocationV1 {
    root: PathBuf,
    parent: PathBuf,
    transaction_token: String,
}

fn transaction_location_v1(
    workspace: &Path,
    requested: &Path,
) -> Result<BootstrapTransactionLocationV1, WorkspaceBootstrapError> {
    validate_absolute_transaction_syntax_v1(requested)?;
    let requested_parent = requested
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?;
    require_safe_directory_chain_v1(requested_parent)?;
    let parent = fs::canonicalize(requested_parent)
        .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    require_safe_directory_chain_v1(&parent)?;
    require_safe_directory_v1(&parent)?;
    let root = parent.join(
        requested
            .file_name()
            .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?,
    );
    reject_workspace_transaction_overlap_v1(workspace, &root)?;
    let transaction_token = transaction_token_v1(workspace, &root);
    Ok(BootstrapTransactionLocationV1 {
        root,
        parent,
        transaction_token,
    })
}

fn require_new_transaction_destination_v1(
    location: &BootstrapTransactionLocationV1,
) -> Result<(), WorkspaceBootstrapError> {
    match fs::symlink_metadata(&location.root) {
        Ok(metadata) => {
            if is_symlink_or_reparse(&metadata) || !metadata.is_dir() {
                return Err(WorkspaceBootstrapError::UnsafeTransaction);
            }
            // A final transaction root is never cleaned or reused by begin,
            // even if incomplete. It may be applied evidence whose manifest
            // was externally removed.
            return Err(WorkspaceBootstrapError::TransactionNotEmpty);
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(_) => return Err(WorkspaceBootstrapError::TransactionUnavailable),
    }
    for operation in [
        WorkspaceBootstrapTransactionOperationV1::Commit,
        WorkspaceBootstrapTransactionOperationV1::Discard,
    ] {
        let quarantine = transaction_quarantine_path_v1(location, operation)?;
        if optional_safe_directory_exists_v1(&quarantine)? {
            return Err(WorkspaceBootstrapError::TransactionNotEmpty);
        }
        let completion = transaction_completion_marker_path_v1(location, operation)?;
        if optional_safe_file_exists_v1(&completion)? {
            return Err(WorkspaceBootstrapError::TransactionNotEmpty);
        }
    }
    Ok(())
}

fn create_unique_transaction_stage_v1(
    location: &BootstrapTransactionLocationV1,
) -> Result<PathBuf, WorkspaceBootstrapError> {
    let epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    for _ in 0..128 {
        let id = NEXT_TRANSACTION_STAGE_ID_V1.fetch_add(1, Ordering::Relaxed);
        let name = format!(
            "{RELEASE_BOOTSTRAP_TRANSACTION_STAGE_PREFIX_V1}{}-{epoch:x}-{id:x}-{}",
            std::process::id(),
            &location.transaction_token[..16]
        );
        let stage = location.parent.join(name);
        match fs::create_dir(&stage) {
            Ok(()) => {
                require_safe_directory_v1(&stage)?;
                require_empty_safe_directory_v1(&stage)?;
                sync_directory_v1(&location.parent)?;
                return Ok(stage);
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(WorkspaceBootstrapError::TransactionUnavailable),
        }
    }
    Err(WorkspaceBootstrapError::TransactionUnavailable)
}

fn publish_transaction_stage_v1(
    stage: &Path,
    destination: &Path,
) -> Result<(), WorkspaceBootstrapError> {
    if fs::symlink_metadata(destination).is_ok() {
        return Err(WorkspaceBootstrapError::TransactionNotEmpty);
    }
    fs::rename(stage, destination).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)
}

fn transaction_quarantine_path_v1(
    location: &BootstrapTransactionLocationV1,
    operation: WorkspaceBootstrapTransactionOperationV1,
) -> Result<PathBuf, WorkspaceBootstrapError> {
    let prefix = match operation {
        WorkspaceBootstrapTransactionOperationV1::Commit => {
            RELEASE_BOOTSTRAP_TRANSACTION_COMMIT_QUARANTINE_PREFIX_V1
        }
        WorkspaceBootstrapTransactionOperationV1::Discard => {
            RELEASE_BOOTSTRAP_TRANSACTION_DISCARD_QUARANTINE_PREFIX_V1
        }
        _ => return Err(WorkspaceBootstrapError::InvalidTransaction),
    };
    Ok(location
        .parent
        .join(format!("{prefix}{}", location.transaction_token)))
}

fn transaction_completion_marker_path_v1(
    location: &BootstrapTransactionLocationV1,
    operation: WorkspaceBootstrapTransactionOperationV1,
) -> Result<PathBuf, WorkspaceBootstrapError> {
    let prefix = match operation {
        WorkspaceBootstrapTransactionOperationV1::Commit => {
            RELEASE_BOOTSTRAP_TRANSACTION_COMMIT_COMPLETION_PREFIX_V1
        }
        WorkspaceBootstrapTransactionOperationV1::Discard => {
            RELEASE_BOOTSTRAP_TRANSACTION_DISCARD_COMPLETION_PREFIX_V1
        }
        _ => return Err(WorkspaceBootstrapError::InvalidTransaction),
    };
    Ok(location
        .parent
        .join(format!("{prefix}{}.json", location.transaction_token)))
}

fn optional_safe_file_exists_v1(path: &Path) -> Result<bool, WorkspaceBootstrapError> {
    let parent = path
        .parent()
        .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?;
    require_safe_directory_chain_v1(parent)?;
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if is_symlink_or_reparse(&metadata) || !metadata.is_file() {
                return Err(WorkspaceBootstrapError::UnsafeTransaction);
            }
            Ok(true)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(_) => Err(WorkspaceBootstrapError::TransactionUnavailable),
    }
}

fn optional_safe_directory_exists_v1(path: &Path) -> Result<bool, WorkspaceBootstrapError> {
    let parent = path
        .parent()
        .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?;
    require_safe_directory_chain_v1(parent)?;
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if is_symlink_or_reparse(&metadata) || !metadata.is_dir() {
                return Err(WorkspaceBootstrapError::UnsafeTransaction);
            }
            Ok(true)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(_) => Err(WorkspaceBootstrapError::TransactionUnavailable),
    }
}

fn rename_transaction_to_quarantine_v1(
    source: &Path,
    destination: &Path,
) -> Result<(), WorkspaceBootstrapError> {
    if fs::symlink_metadata(destination).is_ok() {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    fs::rename(source, destination).map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)
}

fn validate_absolute_transaction_syntax_v1(path: &Path) -> Result<(), WorkspaceBootstrapError> {
    if !path.is_absolute() || path.file_name().is_none() {
        return Err(WorkspaceBootstrapError::UnsafeTransaction);
    }
    if path.components().any(|component| {
        !matches!(
            component,
            Component::Prefix(_) | Component::RootDir | Component::Normal(_)
        )
    }) {
        return Err(WorkspaceBootstrapError::UnsafeTransaction);
    }
    Ok(())
}

fn reject_workspace_transaction_overlap_v1(
    workspace: &Path,
    transaction: &Path,
) -> Result<(), WorkspaceBootstrapError> {
    let workspace = comparable_path_v1(workspace);
    let transaction = comparable_path_v1(transaction);
    if workspace == transaction
        || workspace.starts_with(&transaction)
        || transaction.starts_with(&workspace)
    {
        return Err(WorkspaceBootstrapError::TransactionOverlap);
    }
    Ok(())
}

#[cfg(windows)]
fn comparable_path_v1(path: &Path) -> PathBuf {
    PathBuf::from(path.to_string_lossy().to_lowercase())
}

#[cfg(not(windows))]
fn comparable_path_v1(path: &Path) -> PathBuf {
    path.to_path_buf()
}

fn load_transaction_v1(
    workspace: &Path,
    requested: &Path,
    expected_transaction_token: &str,
) -> Result<LoadedBootstrapTransactionV1, WorkspaceBootstrapError> {
    let root = resolve_existing_transaction_root_v1(workspace, requested)?;
    let mut saw_manifest = false;
    let mut saw_before = false;
    let entries =
        fs::read_dir(&root).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    for entry in entries {
        let entry = entry.map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceBootstrapError::UnsafeTransaction);
        }
        let name = entry.file_name();
        if name == OsStr::new(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
            && metadata.is_file()
            && !saw_manifest
        {
            saw_manifest = true;
        } else if name == OsStr::new(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
            && metadata.is_dir()
            && !saw_before
        {
            saw_before = true;
        } else {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
    }
    if !saw_manifest || !saw_before {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }

    let manifest_path = root.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1);
    let manifest_bytes = read_safe_transaction_file_v1(
        &manifest_path,
        MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1,
    )?;
    let manifest_text = std::str::from_utf8(&manifest_bytes)
        .map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    let manifest = serde_json::from_str::<ReleaseBootstrapTransactionManifestV1>(manifest_text)
        .map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    validate_transaction_manifest_v1(workspace, expected_transaction_token, &manifest)?;

    let before_directory = root.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1);
    require_safe_directory_v1(&before_directory)?;
    let expected_stashes = manifest
        .files
        .iter()
        .enumerate()
        .filter(|(_, entry)| matches!(entry.before, ReleaseBootstrapBeforeImageV1::Present { .. }))
        .map(|(index, _)| format!("{index:02}.bin"))
        .collect::<BTreeSet<_>>();
    let mut actual_stashes = BTreeSet::new();
    for entry in fs::read_dir(&before_directory)
        .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?
    {
        let entry = entry.map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceBootstrapError::UnsafeTransaction);
        }
        if !metadata.is_file() {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
        let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        };
        if !expected_stashes.contains(&name) || !actual_stashes.insert(name) {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
    }
    if actual_stashes != expected_stashes {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }

    let mut total_before = 0_u64;
    let mut before_bytes = Vec::with_capacity(manifest.files.len());
    for (index, entry) in manifest.files.iter().enumerate() {
        match &entry.before {
            ReleaseBootstrapBeforeImageV1::Missing => before_bytes.push(None),
            ReleaseBootstrapBeforeImageV1::Present { size, sha256, .. } => {
                let limit = transaction_file_limit_v1(&entry.relative_path)
                    .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
                let bytes = read_safe_transaction_file_v1(
                    &before_directory.join(format!("{index:02}.bin")),
                    limit,
                )?;
                if bytes.len() as u64 != *size || sha256_hex(&bytes) != *sha256 {
                    return Err(WorkspaceBootstrapError::InvalidTransaction);
                }
                total_before = total_before
                    .checked_add(bytes.len() as u64)
                    .ok_or(WorkspaceBootstrapError::TransactionTooLarge)?;
                before_bytes.push(Some(bytes));
            }
        }
    }
    if total_before > MAX_RELEASE_BOOTSTRAP_TRANSACTION_STASH_BYTES_V1 {
        return Err(WorkspaceBootstrapError::TransactionTooLarge);
    }

    Ok(LoadedBootstrapTransactionV1 {
        manifest,
        manifest_bytes,
        before_bytes,
    })
}

fn validate_transaction_manifest_v1(
    workspace: &Path,
    expected_transaction_token: &str,
    manifest: &ReleaseBootstrapTransactionManifestV1,
) -> Result<(), WorkspaceBootstrapError> {
    if manifest.schema_version != RELEASE_BOOTSTRAP_TRANSACTION_SCHEMA_V1
        || !is_lower_sha256(&manifest.workspace_fingerprint)
        || manifest.workspace_fingerprint != workspace_fingerprint_v1(workspace)
        || !is_lower_sha256(&manifest.transaction_token)
        || manifest.transaction_token != expected_transaction_token
        || manifest.directories.len() != TRANSACTION_DIRECTORY_PATHS_V1.len()
        || manifest.files.len() != transaction_file_count_v1()
    {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    for (entry, expected_path) in manifest
        .directories
        .iter()
        .zip(transaction_directory_paths_v1())
    {
        if entry.relative_path != expected_path {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
    }
    let mut total_before = 0_u64;
    for ((index, entry), expected_path) in manifest
        .files
        .iter()
        .enumerate()
        .zip(transaction_paths_v1())
    {
        if entry.relative_path != expected_path {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
        let limit = transaction_file_limit_v1(expected_path)
            .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
        if entry.planned_post.size > limit || !is_lower_sha256(&entry.planned_post.sha256) {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
        match &entry.before {
            ReleaseBootstrapBeforeImageV1::Missing => {}
            ReleaseBootstrapBeforeImageV1::Present {
                stash_file,
                size,
                sha256,
            } => {
                if stash_file != &transaction_stash_file_v1(index)
                    || *size > limit
                    || !is_lower_sha256(sha256)
                {
                    return Err(WorkspaceBootstrapError::InvalidTransaction);
                }
                total_before = total_before
                    .checked_add(*size)
                    .ok_or(WorkspaceBootstrapError::TransactionTooLarge)?;
            }
        }
    }
    if total_before > MAX_RELEASE_BOOTSTRAP_TRANSACTION_STASH_BYTES_V1 {
        return Err(WorkspaceBootstrapError::TransactionTooLarge);
    }
    validate_directory_before_consistency_v1(manifest)?;
    validate_bootstrap_receipt_v1(&manifest.bootstrap_receipt, &manifest.files)?;
    Ok(())
}

fn validate_bootstrap_receipt_v1(
    receipt: &WorkspaceBootstrapReceiptV1,
    files: &[ReleaseBootstrapTransactionFileV1],
) -> Result<(), WorkspaceBootstrapError> {
    if receipt.schema_version != RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1
        || files.len() != transaction_file_count_v1()
    {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    let allowed = seed_paths().collect::<BTreeSet<_>>();
    let mut seen = BTreeSet::new();
    for relative_path in receipt
        .installed
        .iter()
        .chain(&receipt.upgraded)
        .chain(&receipt.preserved)
        .chain(&receipt.unchanged)
    {
        if !allowed.contains(relative_path.as_str()) || !seen.insert(relative_path.as_str()) {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        }
    }
    if seen != allowed {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }

    let installed = receipt
        .installed
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let upgraded = receipt
        .upgraded
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let stable = receipt
        .preserved
        .iter()
        .chain(&receipt.unchanged)
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    for entry in files.iter().take(transaction_file_count_v1() - 1) {
        match &entry.before {
            ReleaseBootstrapBeforeImageV1::Missing => {
                if !installed.contains(entry.relative_path.as_str()) {
                    return Err(WorkspaceBootstrapError::InvalidTransaction);
                }
            }
            ReleaseBootstrapBeforeImageV1::Present { size, sha256, .. } => {
                let changed =
                    *size != entry.planned_post.size || sha256 != &entry.planned_post.sha256;
                if (changed && !upgraded.contains(entry.relative_path.as_str()))
                    || (!changed && !stable.contains(entry.relative_path.as_str()))
                {
                    return Err(WorkspaceBootstrapError::InvalidTransaction);
                }
            }
        }
    }
    let state = files
        .last()
        .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
    let state_changed = match &state.before {
        ReleaseBootstrapBeforeImageV1::Missing => true,
        ReleaseBootstrapBeforeImageV1::Present { size, sha256, .. } => {
            *size != state.planned_post.size || sha256 != &state.planned_post.sha256
        }
    };
    if receipt.state_updated != state_changed {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    Ok(())
}

fn validate_directory_before_consistency_v1(
    manifest: &ReleaseBootstrapTransactionManifestV1,
) -> Result<(), WorkspaceBootstrapError> {
    let directories = manifest
        .directories
        .iter()
        .map(|entry| (entry.relative_path.as_str(), &entry.before))
        .collect::<BTreeMap<_, _>>();

    for entry in &manifest.directories {
        if matches!(entry.before, ReleaseBootstrapDirectoryBeforeV1::Present) {
            for ancestor in transaction_directory_paths_v1() {
                if ancestor != entry.relative_path
                    && relative_path_is_ancestor_v1(ancestor, &entry.relative_path)
                    && !matches!(
                        directories.get(ancestor),
                        Some(ReleaseBootstrapDirectoryBeforeV1::Present)
                    )
                {
                    return Err(WorkspaceBootstrapError::InvalidTransaction);
                }
            }
        }
    }
    for file in &manifest.files {
        if !matches!(file.before, ReleaseBootstrapBeforeImageV1::Present { .. }) {
            continue;
        }
        for directory in transaction_directory_paths_v1() {
            if relative_path_is_ancestor_v1(directory, &file.relative_path)
                && !matches!(
                    directories.get(directory),
                    Some(ReleaseBootstrapDirectoryBeforeV1::Present)
                )
            {
                return Err(WorkspaceBootstrapError::InvalidTransaction);
            }
        }
    }
    Ok(())
}

fn relative_path_is_ancestor_v1(parent: &str, child: &str) -> bool {
    child
        .strip_prefix(parent)
        .is_some_and(|suffix| suffix.starts_with('/'))
}

fn resolve_existing_transaction_root_v1(
    workspace: &Path,
    requested: &Path,
) -> Result<PathBuf, WorkspaceBootstrapError> {
    validate_absolute_transaction_syntax_v1(requested)?;
    require_safe_directory_chain_v1(requested)?;
    require_safe_directory_v1(requested)?;
    let canonical =
        fs::canonicalize(requested).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    reject_workspace_transaction_overlap_v1(workspace, &canonical)?;
    Ok(canonical)
}

fn require_safe_directory_chain_v1(path: &Path) -> Result<(), WorkspaceBootstrapError> {
    for candidate in path.ancestors().collect::<Vec<_>>().into_iter().rev() {
        if candidate.as_os_str().is_empty() {
            continue;
        }
        let metadata = fs::symlink_metadata(candidate)
            .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceBootstrapError::UnsafeTransaction);
        }
        if !metadata.is_dir() {
            return Err(WorkspaceBootstrapError::UnsafeTransaction);
        }
    }
    Ok(())
}

fn require_safe_directory_v1(path: &Path) -> Result<(), WorkspaceBootstrapError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    if is_symlink_or_reparse(&metadata) || !metadata.is_dir() {
        return Err(WorkspaceBootstrapError::UnsafeTransaction);
    }
    Ok(())
}

fn require_empty_safe_directory_v1(path: &Path) -> Result<(), WorkspaceBootstrapError> {
    require_safe_directory_v1(path)?;
    let mut nonempty = false;
    for entry in fs::read_dir(path).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)? {
        let entry = entry.map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceBootstrapError::UnsafeTransaction);
        }
        nonempty = true;
    }
    if nonempty {
        return Err(WorkspaceBootstrapError::TransactionNotEmpty);
    }
    Ok(())
}

fn read_safe_transaction_file_v1(
    path: &Path,
    maximum_bytes: u64,
) -> Result<Vec<u8>, WorkspaceBootstrapError> {
    let parent = path
        .parent()
        .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?;
    require_safe_directory_chain_v1(parent)?;
    let metadata =
        fs::symlink_metadata(path).map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    if is_symlink_or_reparse(&metadata) {
        return Err(WorkspaceBootstrapError::UnsafeTransaction);
    }
    if !metadata.is_file() {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    if metadata.len() > maximum_bytes {
        return Err(WorkspaceBootstrapError::TransactionTooLarge);
    }
    let bytes = fs::read(path).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    let after =
        fs::symlink_metadata(path).map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    if is_symlink_or_reparse(&after) {
        return Err(WorkspaceBootstrapError::UnsafeTransaction);
    }
    if !after.is_file() || after.len() != bytes.len() as u64 {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    if after.len() > maximum_bytes || bytes.len() as u64 > maximum_bytes {
        return Err(WorkspaceBootstrapError::TransactionTooLarge);
    }
    Ok(bytes)
}

fn inspect_transaction_workspace_files_v1(
    workspace: &Path,
) -> Result<Vec<InspectedFile>, WorkspaceBootstrapError> {
    transaction_paths_v1()
        .map(|relative_path| {
            let (maximum, too_large) = if relative_path == RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH {
                (
                    MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1,
                    WorkspaceBootstrapError::StateTooLarge,
                )
            } else {
                (
                    MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1,
                    WorkspaceBootstrapError::TargetTooLarge,
                )
            };
            inspect_file(workspace, relative_path, maximum, too_large)
        })
        .collect()
}

fn inspect_transaction_workspace_directories_v1(
    workspace: &Path,
) -> Result<Vec<InspectedDirectoryV1>, WorkspaceBootstrapError> {
    transaction_directory_paths_v1()
        .map(|relative_path| inspect_directory_v1(workspace, relative_path))
        .collect()
}

fn matches_before_v1(
    entry: &ReleaseBootstrapTransactionFileV1,
    before_bytes: Option<&[u8]>,
    current: &InspectedFile,
) -> bool {
    match (&entry.before, before_bytes, current) {
        (ReleaseBootstrapBeforeImageV1::Missing, None, InspectedFile::Missing) => true,
        (
            ReleaseBootstrapBeforeImageV1::Present { .. },
            Some(before),
            InspectedFile::Present(current),
        ) => before == current,
        _ => false,
    }
}

fn matches_post_v1(entry: &ReleaseBootstrapTransactionFileV1, current: &InspectedFile) -> bool {
    match current {
        InspectedFile::Missing => false,
        InspectedFile::Present(bytes) => {
            bytes.len() as u64 == entry.planned_post.size
                && sha256_hex(bytes) == entry.planned_post.sha256
        }
    }
}

fn verify_workspace_matches_post_v1(
    workspace: &Path,
    manifest: &ReleaseBootstrapTransactionManifestV1,
) -> Result<(), WorkspaceBootstrapError> {
    let current = inspect_transaction_workspace_files_v1(workspace)?;
    let directories = inspect_transaction_workspace_directories_v1(workspace)?;
    if manifest.files.len() != current.len()
        || manifest.directories.len() != directories.len()
        || manifest
            .files
            .iter()
            .zip(&current)
            .any(|(entry, current)| !matches_post_v1(entry, current))
        || directories
            .iter()
            .any(|current| *current != InspectedDirectoryV1::Present)
    {
        return Err(WorkspaceBootstrapError::TransactionVerificationFailed);
    }
    Ok(())
}

fn verify_workspace_matches_before_v1(
    workspace: &Path,
    loaded: &LoadedBootstrapTransactionV1,
) -> Result<(), WorkspaceBootstrapError> {
    let current = inspect_transaction_workspace_files_v1(workspace)?;
    let directories = inspect_transaction_workspace_directories_v1(workspace)?;
    if loaded.manifest.files.len() != current.len()
        || loaded.before_bytes.len() != current.len()
        || loaded.manifest.directories.len() != directories.len()
        || loaded
            .manifest
            .files
            .iter()
            .zip(&loaded.before_bytes)
            .zip(&current)
            .any(|((entry, before), current)| !matches_before_v1(entry, before.as_deref(), current))
        || loaded
            .manifest
            .directories
            .iter()
            .zip(&directories)
            .any(|(entry, current)| !matches_directory_before_v1(&entry.before, *current))
    {
        return Err(WorkspaceBootstrapError::TransactionRollbackFailed);
    }
    Ok(())
}

fn verify_workspace_matches_expectation_v1(
    workspace: &Path,
    manifest: &ReleaseBootstrapTransactionManifestV1,
    expectation: TransactionWorkspaceExpectationV1,
) -> Result<(), WorkspaceBootstrapError> {
    if expectation == TransactionWorkspaceExpectationV1::Post {
        return verify_workspace_matches_post_v1(workspace, manifest);
    }
    let current = inspect_transaction_workspace_files_v1(workspace)?;
    let directories = inspect_transaction_workspace_directories_v1(workspace)?;
    if manifest.files.len() != current.len()
        || manifest.directories.len() != directories.len()
        || manifest
            .files
            .iter()
            .zip(&current)
            .any(|(entry, current)| !matches_before_digest_v1(entry, current))
        || manifest
            .directories
            .iter()
            .zip(&directories)
            .any(|(entry, current)| !matches_directory_before_v1(&entry.before, *current))
    {
        return Err(WorkspaceBootstrapError::TransactionVerificationFailed);
    }
    Ok(())
}

fn preflight_rollback_directories_v1(
    workspace: &Path,
    loaded: &LoadedBootstrapTransactionV1,
    current_files: &[InspectedFile],
) -> Result<(), WorkspaceBootstrapError> {
    if current_files.len() != loaded.manifest.files.len() {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    for directory in &loaded.manifest.directories {
        if !matches!(directory.before, ReleaseBootstrapDirectoryBeforeV1::Missing) {
            continue;
        }
        let path = workspace.join(&directory.relative_path);
        match inspect_directory_v1(workspace, &directory.relative_path)? {
            InspectedDirectoryV1::Missing => continue,
            InspectedDirectoryV1::Present => {}
        }

        let mut allowed = BTreeMap::<String, bool>::new();
        for ((file, current), relative_path) in loaded
            .manifest
            .files
            .iter()
            .zip(current_files)
            .zip(transaction_paths_v1())
        {
            if !matches!(file.before, ReleaseBootstrapBeforeImageV1::Missing)
                || Path::new(relative_path).parent() != Some(Path::new(&directory.relative_path))
            {
                continue;
            }
            if !matches!(current, InspectedFile::Missing) && !matches_post_v1(file, current) {
                return Err(WorkspaceBootstrapError::TransactionDrift);
            }
            let name = Path::new(relative_path)
                .file_name()
                .and_then(OsStr::to_str)
                .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
            allowed.insert(name.to_owned(), false);
        }
        for child in &loaded.manifest.directories {
            if !matches!(child.before, ReleaseBootstrapDirectoryBeforeV1::Missing)
                || Path::new(&child.relative_path).parent()
                    != Some(Path::new(&directory.relative_path))
            {
                continue;
            }
            let name = Path::new(&child.relative_path)
                .file_name()
                .and_then(OsStr::to_str)
                .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
            allowed.insert(name.to_owned(), true);
        }

        for entry in
            fs::read_dir(&path).map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?
        {
            let entry = entry.map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?;
            let metadata = fs::symlink_metadata(entry.path())
                .map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?;
            if is_symlink_or_reparse(&metadata) {
                return Err(WorkspaceBootstrapError::TransactionDrift);
            }
            let name = entry
                .file_name()
                .to_str()
                .map(str::to_owned)
                .ok_or(WorkspaceBootstrapError::TransactionDrift)?;
            let Some(expected_directory) = allowed.get(&name) else {
                return Err(WorkspaceBootstrapError::TransactionDrift);
            };
            if (*expected_directory && !metadata.is_dir())
                || (!*expected_directory && !metadata.is_file())
            {
                return Err(WorkspaceBootstrapError::TransactionDrift);
            }
        }
    }
    Ok(())
}

fn restore_missing_directories_v1(
    workspace: &Path,
    loaded: &LoadedBootstrapTransactionV1,
) -> Result<(), WorkspaceBootstrapError> {
    for directory in loaded.manifest.directories.iter().rev() {
        if !matches!(directory.before, ReleaseBootstrapDirectoryBeforeV1::Missing) {
            continue;
        }
        let path = workspace.join(&directory.relative_path);
        match inspect_directory_v1(workspace, &directory.relative_path)? {
            InspectedDirectoryV1::Missing => continue,
            InspectedDirectoryV1::Present => {}
        }
        let mut entries =
            fs::read_dir(&path).map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?;
        if entries
            .next()
            .transpose()
            .map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?
            .is_some()
        {
            return Err(WorkspaceBootstrapError::TransactionDrift);
        }
        fs::remove_dir(&path).map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?;
    }
    Ok(())
}

fn matches_before_digest_v1(
    entry: &ReleaseBootstrapTransactionFileV1,
    current: &InspectedFile,
) -> bool {
    match (&entry.before, current) {
        (ReleaseBootstrapBeforeImageV1::Missing, InspectedFile::Missing) => true,
        (
            ReleaseBootstrapBeforeImageV1::Present { size, sha256, .. },
            InspectedFile::Present(bytes),
        ) => bytes.len() as u64 == *size && sha256_hex(bytes) == *sha256,
        _ => false,
    }
}

fn matches_directory_before_v1(
    before: &ReleaseBootstrapDirectoryBeforeV1,
    current: InspectedDirectoryV1,
) -> bool {
    matches!(
        (before, current),
        (
            ReleaseBootstrapDirectoryBeforeV1::Missing,
            InspectedDirectoryV1::Missing
        ) | (
            ReleaseBootstrapDirectoryBeforeV1::Present,
            InspectedDirectoryV1::Present
        )
    )
}

fn remove_workspace_post_file_v1(
    workspace: &Path,
    relative_path: &str,
    planned_post: &ReleaseBootstrapFileDigestV1,
) -> Result<(), WorkspaceBootstrapError> {
    let (maximum, too_large) = if relative_path == RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH {
        (
            MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1,
            WorkspaceBootstrapError::StateTooLarge,
        )
    } else {
        (
            MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1,
            WorkspaceBootstrapError::TargetTooLarge,
        )
    };
    let current = inspect_file(workspace, relative_path, maximum, too_large)?;
    let expected = ReleaseBootstrapTransactionFileV1 {
        relative_path: relative_path.to_owned(),
        before: ReleaseBootstrapBeforeImageV1::Missing,
        planned_post: planned_post.clone(),
    };
    if !matches_post_v1(&expected, &current) {
        return Err(WorkspaceBootstrapError::TransactionDrift);
    }
    fs::remove_file(workspace.join(relative_path))
        .map_err(|_| WorkspaceBootstrapError::TransactionRollbackFailed)?;
    if !matches!(
        inspect_file(workspace, relative_path, maximum, too_large)?,
        InspectedFile::Missing
    ) {
        return Err(WorkspaceBootstrapError::TransactionRollbackFailed);
    }
    Ok(())
}

#[derive(Debug)]
struct LoadedCleanupQuarantineV1 {
    root: PathBuf,
    manifest: Option<ReleaseBootstrapTransactionManifestV1>,
    manifest_bytes: Option<Vec<u8>>,
    before_directory_present: bool,
    existing_stashes: Vec<usize>,
}

fn load_completion_marker_v1(
    workspace: &Path,
    path: &Path,
    expected_transaction_token: &str,
) -> Result<(ReleaseBootstrapTransactionManifestV1, Vec<u8>), WorkspaceBootstrapError> {
    let bytes =
        read_safe_transaction_file_v1(path, MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1)?;
    let text =
        std::str::from_utf8(&bytes).map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    let manifest = serde_json::from_str::<ReleaseBootstrapTransactionManifestV1>(text)
        .map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    validate_transaction_manifest_v1(workspace, expected_transaction_token, &manifest)?;
    Ok((manifest, bytes))
}

fn load_cleanup_quarantine_v1(
    workspace: &Path,
    root: &Path,
    expected_transaction_token: &str,
) -> Result<LoadedCleanupQuarantineV1, WorkspaceBootstrapError> {
    require_safe_directory_chain_v1(root)?;
    require_safe_directory_v1(root)?;
    let manifest_path = root.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1);
    let before_directory = root.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1);
    let mut saw_manifest = false;
    let mut saw_before = false;
    let mut root_entry_count = 0_usize;
    for entry in
        fs::read_dir(root).map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?
    {
        let entry = entry.map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        let metadata = fs::symlink_metadata(entry.path())
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceBootstrapError::UnsafeTransaction);
        }
        root_entry_count += 1;
        let name = entry.file_name();
        if name == OsStr::new(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
            && metadata.is_file()
            && !saw_manifest
        {
            saw_manifest = true;
        } else if name == OsStr::new(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
            && metadata.is_dir()
            && !saw_before
        {
            saw_before = true;
        } else {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
    }
    if !saw_manifest {
        if root_entry_count != 0 {
            // Cleanup itself always removes the before directory before the
            // manifest. A nonempty manifest-less quarantine is therefore an
            // externally damaged/unknown partial and must not be consumed.
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
        return Ok(LoadedCleanupQuarantineV1 {
            root: root.to_path_buf(),
            manifest: None,
            manifest_bytes: None,
            before_directory_present: false,
            existing_stashes: Vec::new(),
        });
    }

    let manifest_bytes = read_safe_transaction_file_v1(
        &manifest_path,
        MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1,
    )?;
    let manifest_text = std::str::from_utf8(&manifest_bytes)
        .map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    let manifest = serde_json::from_str::<ReleaseBootstrapTransactionManifestV1>(manifest_text)
        .map_err(|_| WorkspaceBootstrapError::InvalidTransaction)?;
    validate_transaction_manifest_v1(workspace, expected_transaction_token, &manifest)?;

    let mut existing_stashes = Vec::new();
    if saw_before {
        require_safe_directory_v1(&before_directory)?;
        let expected = manifest
            .files
            .iter()
            .enumerate()
            .filter_map(|(index, entry)| {
                matches!(entry.before, ReleaseBootstrapBeforeImageV1::Present { .. })
                    .then_some((format!("{index:02}.bin"), index))
            })
            .collect::<BTreeMap<_, _>>();
        for entry in fs::read_dir(&before_directory)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?
        {
            let entry = entry.map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
            let metadata = fs::symlink_metadata(entry.path())
                .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
            if is_symlink_or_reparse(&metadata) || !metadata.is_file() {
                return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
            }
            let name = entry
                .file_name()
                .to_str()
                .map(str::to_owned)
                .ok_or(WorkspaceBootstrapError::TransactionCleanupFailed)?;
            let Some(index) = expected.get(&name).copied() else {
                return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
            };
            let ReleaseBootstrapBeforeImageV1::Present { size, sha256, .. } =
                &manifest.files[index].before
            else {
                return Err(WorkspaceBootstrapError::InvalidTransaction);
            };
            let limit = transaction_file_limit_v1(&manifest.files[index].relative_path)
                .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
            let bytes = read_safe_transaction_file_v1(&entry.path(), limit)?;
            if bytes.len() as u64 != *size || sha256_hex(&bytes) != *sha256 {
                return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
            }
            existing_stashes.push(index);
        }
        existing_stashes.sort_unstable();
    }

    Ok(LoadedCleanupQuarantineV1 {
        root: root.to_path_buf(),
        manifest: Some(manifest),
        manifest_bytes: Some(manifest_bytes),
        before_directory_present: saw_before,
        existing_stashes,
    })
}

fn cleanup_transaction_quarantine_v1<C>(
    workspace: &Path,
    cleanup: LoadedCleanupQuarantineV1,
    completion_marker: &Path,
    before_cleanup: &mut C,
) -> Result<u32, WorkspaceBootstrapError>
where
    C: FnMut(TransactionCleanupPointV1, &Path) -> Result<(), WorkspaceBootstrapError>,
{
    let parent = cleanup
        .root
        .parent()
        .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?
        .to_path_buf();
    let Some(manifest) = cleanup.manifest else {
        if !optional_safe_file_exists_v1(completion_marker)? {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
        require_empty_safe_directory_v1(&cleanup.root)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        before_cleanup(TransactionCleanupPointV1::Root, &cleanup.root)?;
        fs::remove_dir(&cleanup.root)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        sync_directory_v1(&parent)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        return Ok(0);
    };
    let manifest_bytes = cleanup
        .manifest_bytes
        .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
    let before_directory = cleanup
        .root
        .join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1);
    let mut removed = 0_u32;
    for index in cleanup.existing_stashes {
        let path = before_directory.join(format!("{index:02}.bin"));
        let ReleaseBootstrapBeforeImageV1::Present { size, sha256, .. } =
            &manifest.files[index].before
        else {
            return Err(WorkspaceBootstrapError::InvalidTransaction);
        };
        let limit = transaction_file_limit_v1(&manifest.files[index].relative_path)
            .ok_or(WorkspaceBootstrapError::InvalidTransaction)?;
        let current = read_safe_transaction_file_v1(&path, limit)?;
        if current.len() as u64 != *size || sha256_hex(&current) != *sha256 {
            return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
        }
        before_cleanup(TransactionCleanupPointV1::Stash(index), &path)?;
        fs::remove_file(&path).map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        removed += 1;
    }
    if cleanup.before_directory_present {
        require_empty_safe_directory_v1(&before_directory)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
        before_cleanup(
            TransactionCleanupPointV1::BeforeDirectory,
            &before_directory,
        )?;
        fs::remove_dir(&before_directory)
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    }

    let manifest_path = cleanup
        .root
        .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1);
    let current_manifest = read_safe_transaction_file_v1(
        &manifest_path,
        MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1,
    )?;
    if current_manifest != manifest_bytes {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    let mut root_entries = fs::read_dir(&cleanup.root)
        .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    let only_manifest = root_entries
        .next()
        .transpose()
        .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?
        .is_some()
        && root_entries
            .next()
            .transpose()
            .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?
            .is_none();
    if !only_manifest {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    if optional_safe_file_exists_v1(completion_marker)? {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    before_cleanup(TransactionCleanupPointV1::Manifest, &manifest_path)?;
    let current_manifest = read_safe_transaction_file_v1(
        &manifest_path,
        MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1,
    )?;
    if current_manifest != manifest_bytes {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    fs::rename(&manifest_path, completion_marker)
        .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    sync_directory_v1(&parent).map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    let (_, completed_bytes) =
        load_completion_marker_v1(workspace, completion_marker, &manifest.transaction_token)?;
    if completed_bytes != manifest_bytes {
        return Err(WorkspaceBootstrapError::TransactionCleanupFailed);
    }
    require_empty_safe_directory_v1(&cleanup.root)
        .map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    before_cleanup(TransactionCleanupPointV1::Root, &cleanup.root)?;
    fs::remove_dir(&cleanup.root).map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    sync_directory_v1(&parent).map_err(|_| WorkspaceBootstrapError::TransactionCleanupFailed)?;
    Ok(removed)
}

fn write_new_synced_file_v1(path: &Path, bytes: &[u8]) -> Result<(), WorkspaceBootstrapError> {
    let parent = path
        .parent()
        .ok_or(WorkspaceBootstrapError::UnsafeTransaction)?;
    require_safe_directory_chain_v1(parent)?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)?;
    drop(file);
    let current = read_safe_transaction_file_v1(path, bytes.len() as u64)?;
    if current != bytes {
        return Err(WorkspaceBootstrapError::InvalidTransaction);
    }
    Ok(())
}

#[cfg(unix)]
fn sync_directory_v1(path: &Path) -> Result<(), WorkspaceBootstrapError> {
    fs::File::open(path)
        .and_then(|directory| directory.sync_all())
        .map_err(|_| WorkspaceBootstrapError::TransactionUnavailable)
}

#[cfg(windows)]
fn sync_directory_v1(path: &Path) -> Result<(), WorkspaceBootstrapError> {
    // `FlushFileBuffers` rejects directory handles on supported Windows
    // filesystems. Every transaction file is individually `sync_all`'d before
    // the manifest is created; the manifest is the durable completeness gate.
    require_safe_directory_v1(path)
}

fn workspace_fingerprint_v1(workspace: &Path) -> String {
    let mut digest = Sha256::new();
    digest.update(b"miho-release-bootstrap-workspace-v1\0");
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        digest.update(workspace.as_os_str().as_bytes());
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        for unit in workspace.as_os_str().encode_wide() {
            digest.update(unit.to_le_bytes());
        }
    }
    #[cfg(not(any(unix, windows)))]
    digest.update(workspace.to_string_lossy().as_bytes());
    format!("{:x}", digest.finalize())
}

fn transaction_token_v1(workspace: &Path, transaction_root: &Path) -> String {
    let mut digest = Sha256::new();
    digest.update(b"miho-release-bootstrap-transaction-token-v1\0");
    digest.update(workspace_fingerprint_v1(workspace).as_bytes());
    digest.update(b"\0");
    update_digest_path_v1(&mut digest, &comparable_path_v1(transaction_root));
    format!("{:x}", digest.finalize())
}

fn update_digest_path_v1(digest: &mut Sha256, path: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        digest.update(path.as_os_str().as_bytes());
    }
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        for unit in path.as_os_str().encode_wide() {
            digest.update(unit.to_le_bytes());
        }
    }
    #[cfg(not(any(unix, windows)))]
    digest.update(path.to_string_lossy().as_bytes());
}

fn default_box_state_bytes() -> Result<Vec<u8>, WorkspaceBootstrapError> {
    serialize_json_line(&BoxState::default())
}

fn serialize_json_line<T: Serialize>(value: &T) -> Result<Vec<u8>, WorkspaceBootstrapError> {
    let mut bytes = serde_json::to_vec_pretty(value)
        .map_err(|_| WorkspaceBootstrapError::SerializationFailed)?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn inspect_directory_v1(
    workspace: &Path,
    relative_path: &str,
) -> Result<InspectedDirectoryV1, WorkspaceBootstrapError> {
    let relative = Path::new(relative_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(WorkspaceBootstrapError::UnsafeTarget);
    }
    let components = relative.components().collect::<Vec<_>>();
    let mut current = workspace.to_path_buf();
    for component in components {
        current.push(component.as_os_str());
        let metadata = match fs::symlink_metadata(&current) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return Ok(InspectedDirectoryV1::Missing)
            }
            Err(_) => return Err(WorkspaceBootstrapError::TargetReadFailed),
        };
        if is_symlink_or_reparse(&metadata) || !metadata.is_dir() {
            return Err(WorkspaceBootstrapError::UnsafeTarget);
        }
    }
    Ok(InspectedDirectoryV1::Present)
}

fn inspect_file(
    workspace: &Path,
    relative_path: &str,
    maximum_bytes: u64,
    too_large: WorkspaceBootstrapError,
) -> Result<InspectedFile, WorkspaceBootstrapError> {
    let relative = Path::new(relative_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(WorkspaceBootstrapError::UnsafeTarget);
    }

    let components = relative.components().collect::<Vec<_>>();
    let mut current = workspace.to_path_buf();
    for (index, component) in components.iter().enumerate() {
        current.push(component.as_os_str());
        let last = index + 1 == components.len();
        let metadata = match fs::symlink_metadata(&current) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return Ok(InspectedFile::Missing)
            }
            Err(_) => return Err(WorkspaceBootstrapError::TargetReadFailed),
        };
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceBootstrapError::UnsafeTarget);
        }
        if !last {
            if !metadata.is_dir() {
                return Err(WorkspaceBootstrapError::UnsafeTarget);
            }
            continue;
        }
        if !metadata.is_file() {
            return Err(WorkspaceBootstrapError::UnsafeTarget);
        }
        if metadata.len() > maximum_bytes {
            return Err(too_large);
        }
        let bytes = fs::read(&current).map_err(|_| WorkspaceBootstrapError::TargetReadFailed)?;
        let after = fs::symlink_metadata(&current)
            .map_err(|_| WorkspaceBootstrapError::TargetReadFailed)?;
        if is_symlink_or_reparse(&after) || !after.is_file() {
            return Err(WorkspaceBootstrapError::UnsafeTarget);
        }
        if after.len() > maximum_bytes || bytes.len() as u64 > maximum_bytes {
            return Err(too_large);
        }
        if after.len() != bytes.len() as u64 {
            return Err(WorkspaceBootstrapError::TargetReadFailed);
        }
        return Ok(InspectedFile::Present(bytes));
    }
    Err(WorkspaceBootstrapError::UnsafeTarget)
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn is_lower_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn map_lease_error(error: WorkspaceWriteLeaseError) -> WorkspaceBootstrapError {
    match error {
        WorkspaceWriteLeaseError::Busy => WorkspaceBootstrapError::WorkspaceBusy,
        WorkspaceWriteLeaseError::UnsafeWorkspace => WorkspaceBootstrapError::UnsafeWorkspace,
        WorkspaceWriteLeaseError::Unavailable => WorkspaceBootstrapError::WorkspaceUnavailable,
    }
}

fn is_symlink_or_reparse(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        false
    }
}

#[cfg(test)]
mod transaction_apply_tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;

    static NEXT_ID: AtomicU64 = AtomicU64::new(0);

    fn test_base(label: &str) -> PathBuf {
        let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let base = std::env::temp_dir().join(format!(
            "miho-bootstrap-{label}-{}-{id}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();
        base
    }

    fn fully_stashed_transaction(
        label: &str,
    ) -> (
        PathBuf,
        PathBuf,
        PathBuf,
        WorkspaceBootstrapTransactionRequestV1,
    ) {
        let base = test_base(label);
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir(&workspace).unwrap();
        bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(workspace.clone())).unwrap();
        let request =
            WorkspaceBootstrapTransactionRequestV1::new(workspace.clone(), transaction.clone());
        begin_workspace_bootstrap_transaction_v1(&request).unwrap();
        assert_eq!(
            fs::read_dir(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1))
                .unwrap()
                .count(),
            transaction_file_count_v1()
        );
        (base, workspace, transaction, request)
    }

    fn complete_operation(
        operation: WorkspaceBootstrapTransactionOperationV1,
        request: &WorkspaceBootstrapTransactionRequestV1,
    ) -> Result<WorkspaceBootstrapTransactionReceiptV1, WorkspaceBootstrapError> {
        match operation {
            WorkspaceBootstrapTransactionOperationV1::Commit => {
                commit_workspace_bootstrap_transaction_v1(request)
            }
            WorkspaceBootstrapTransactionOperationV1::Discard => {
                discard_workspace_bootstrap_transaction_v1(request)
            }
            _ => unreachable!(),
        }
    }

    #[test]
    fn direct_missing_seed_and_owner_state_share_one_failing_batch() {
        let base = test_base("direct-apply-failure");
        let workspace = base.join("workspace");
        fs::create_dir(&workspace).unwrap();
        fs::create_dir(workspace.join(".miho")).unwrap();
        let relative_path = CONFIG_SEEDS[0].relative_path;
        let old_hash = sha256_hex(b"old generation seed");
        let mut managed_files = BTreeMap::new();
        managed_files.insert(relative_path.to_owned(), old_hash);
        let state_before = serialize_json_line(&ReleaseBootstrapStateV1 {
            schema_version: RELEASE_BOOTSTRAP_STATE_SCHEMA_V1.to_owned(),
            managed_files,
        })
        .unwrap();
        fs::write(
            workspace.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH),
            &state_before,
        )
        .unwrap();

        let request = WorkspaceBootstrapRequestV1::new(workspace.clone());
        let error = bootstrap_workspace_with_apply_v1(&request, |outputs| {
            assert!(outputs.iter().any(
                |(path, bytes)| path.ends_with(relative_path) && bytes == CONFIG_SEEDS[0].bytes
            ));
            let state_output = outputs
                .iter()
                .find(|(path, _)| path.ends_with(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH))
                .unwrap();
            let state: ReleaseBootstrapStateV1 = serde_json::from_slice(&state_output.1).unwrap();
            assert_eq!(
                state.managed_files.get(relative_path),
                Some(&sha256_hex(CONFIG_SEEDS[0].bytes))
            );
            Err(WorkspaceBootstrapError::CommitFailed)
        })
        .unwrap_err();
        assert_eq!(error, WorkspaceBootstrapError::CommitFailed);
        assert!(!workspace.join(relative_path).exists());
        assert_eq!(
            fs::read(workspace.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH)).unwrap(),
            state_before
        );

        fs::remove_dir_all(&base).unwrap();
    }

    #[test]
    fn failed_apply_keeps_complete_evidence_for_idempotent_rollback() {
        let base = test_base("apply-failure");
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir_all(&workspace).unwrap();
        let request =
            WorkspaceBootstrapTransactionRequestV1::new(workspace.clone(), transaction.clone());

        let error = begin_workspace_bootstrap_transaction_with_apply_v1(&request, |outputs| {
            assert!(transaction
                .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
                .is_file());
            assert!(transaction
                .join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
                .is_dir());
            atomic::write_batch(&outputs[..3]).unwrap();
            Err(WorkspaceBootstrapError::CommitFailed)
        })
        .unwrap_err();
        assert_eq!(error, WorkspaceBootstrapError::CommitFailed);
        assert!(transaction
            .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
            .is_file());
        assert!(workspace.join(CONFIG_SEEDS[0].relative_path).is_file());

        let rollback = rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
        assert_eq!(rollback.files_restored, 0);
        assert_eq!(rollback.files_removed, 3);
        for relative_path in transaction_paths_v1() {
            assert!(!workspace.join(relative_path).exists());
        }
        assert!(transaction.is_dir());

        fs::remove_dir_all(&base).unwrap();
    }

    #[test]
    fn plan_failure_creates_no_final_or_stage_root() {
        let base = test_base("plan-failure");
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir(&workspace).unwrap();
        fs::create_dir(workspace.join(".miho")).unwrap();
        fs::write(
            workspace.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH),
            b"not-json",
        )
        .unwrap();
        let request = WorkspaceBootstrapTransactionRequestV1::new(workspace, transaction.clone());

        assert_eq!(
            begin_workspace_bootstrap_transaction_v1(&request),
            Err(WorkspaceBootstrapError::InvalidState)
        );
        assert!(!transaction.exists());
        assert_eq!(
            fs::read_dir(&base)
                .unwrap()
                .filter_map(Result::ok)
                .filter(|entry| {
                    entry
                        .file_name()
                        .to_string_lossy()
                        .starts_with(RELEASE_BOOTSTRAP_TRANSACTION_STAGE_PREFIX_V1)
                })
                .count(),
            0
        );
        fs::remove_dir_all(&base).unwrap();
    }

    #[test]
    fn every_stash_and_manifest_persist_failure_allows_same_path_retry() {
        for failure_ordinal in 0..=transaction_file_count_v1() {
            let base = test_base(&format!("persist-failure-{failure_ordinal}"));
            let workspace = base.join("workspace");
            let transaction = base.join("transaction");
            fs::create_dir(&workspace).unwrap();
            bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(workspace.clone())).unwrap();
            let request =
                WorkspaceBootstrapTransactionRequestV1::new(workspace.clone(), transaction.clone());
            let mut ordinal = 0_usize;
            let failed = begin_workspace_bootstrap_transaction_with_io_v1(
                &request,
                |outputs| {
                    atomic::write_batch(outputs).map_err(|_| WorkspaceBootstrapError::CommitFailed)
                },
                |_, path, bytes| {
                    let current = ordinal;
                    ordinal += 1;
                    if current == failure_ordinal {
                        Err(WorkspaceBootstrapError::TransactionUnavailable)
                    } else {
                        write_new_synced_file_v1(path, bytes)
                    }
                },
                publish_transaction_stage_v1,
            );
            assert_eq!(
                failed,
                Err(WorkspaceBootstrapError::TransactionUnavailable),
                "failure_ordinal={failure_ordinal}"
            );
            assert!(!transaction.exists());
            assert!(fs::read_dir(&base).unwrap().any(|entry| {
                entry
                    .unwrap()
                    .file_name()
                    .to_string_lossy()
                    .starts_with(RELEASE_BOOTSTRAP_TRANSACTION_STAGE_PREFIX_V1)
            }));

            begin_workspace_bootstrap_transaction_v1(&request).unwrap();
            commit_workspace_bootstrap_transaction_v1(&request).unwrap();
            assert!(!transaction.exists());
            fs::remove_dir_all(&base).unwrap();
        }
    }

    #[test]
    fn stale_stage_and_publish_failure_do_not_block_retry() {
        let base = test_base("stage-retry");
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir(&workspace).unwrap();
        fs::create_dir(base.join(format!(
            "{RELEASE_BOOTSTRAP_TRANSACTION_STAGE_PREFIX_V1}stale"
        )))
        .unwrap();
        let request =
            WorkspaceBootstrapTransactionRequestV1::new(workspace.clone(), transaction.clone());
        let failed = begin_workspace_bootstrap_transaction_with_io_v1(
            &request,
            |outputs| {
                atomic::write_batch(outputs).map_err(|_| WorkspaceBootstrapError::CommitFailed)
            },
            |_, path, bytes| write_new_synced_file_v1(path, bytes),
            |_, _| Err(WorkspaceBootstrapError::TransactionUnavailable),
        );
        assert_eq!(failed, Err(WorkspaceBootstrapError::TransactionUnavailable));
        assert!(!transaction.exists());

        begin_workspace_bootstrap_transaction_v1(&request).unwrap();
        commit_workspace_bootstrap_transaction_v1(&request).unwrap();
        fs::remove_dir_all(&base).unwrap();
    }

    #[test]
    fn incomplete_final_without_manifest_is_never_reused_or_cleaned_by_begin() {
        let base = test_base("removed-final-manifest");
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir(&workspace).unwrap();
        let request =
            WorkspaceBootstrapTransactionRequestV1::new(workspace.clone(), transaction.clone());
        begin_workspace_bootstrap_transaction_v1(&request).unwrap();
        fs::remove_file(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)).unwrap();
        let before_entries = fs::read_dir(&transaction).unwrap().count();

        assert_eq!(
            begin_workspace_bootstrap_transaction_v1(&request),
            Err(WorkspaceBootstrapError::TransactionNotEmpty)
        );
        assert_eq!(fs::read_dir(&transaction).unwrap().count(), before_entries);
        assert!(transaction
            .join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
            .is_dir());
        fs::remove_dir_all(&base).unwrap();
    }

    #[test]
    fn commit_and_discard_retry_every_rename_and_cleanup_failure_point() {
        let mut cleanup_points = (0..transaction_file_count_v1())
            .map(TransactionCleanupPointV1::Stash)
            .collect::<Vec<_>>();
        cleanup_points.extend([
            TransactionCleanupPointV1::BeforeDirectory,
            TransactionCleanupPointV1::Manifest,
            TransactionCleanupPointV1::Root,
        ]);

        for operation in [
            WorkspaceBootstrapTransactionOperationV1::Commit,
            WorkspaceBootstrapTransactionOperationV1::Discard,
        ] {
            let expectation = match operation {
                WorkspaceBootstrapTransactionOperationV1::Commit => {
                    TransactionWorkspaceExpectationV1::Post
                }
                WorkspaceBootstrapTransactionOperationV1::Discard => {
                    TransactionWorkspaceExpectationV1::Before
                }
                _ => unreachable!(),
            };

            let (base, _, transaction, request) =
                fully_stashed_transaction(&format!("{operation:?}-rename-failure"));
            assert_eq!(
                finish_workspace_bootstrap_transaction_with_io_v1(
                    &request,
                    operation,
                    expectation,
                    |_, _| Err(WorkspaceBootstrapError::TransactionCleanupFailed),
                    |_, _| Ok(()),
                ),
                Err(WorkspaceBootstrapError::TransactionCleanupFailed)
            );
            assert!(transaction.is_dir());
            complete_operation(operation, &request).unwrap();
            // The durable completion marker makes a post-cleanup retry exact
            // instead of treating an arbitrary absent path as success.
            complete_operation(operation, &request).unwrap();
            fs::remove_dir_all(&base).unwrap();

            for failure_point in &cleanup_points {
                let (base, _, transaction, request) =
                    fully_stashed_transaction(&format!("{operation:?}-cleanup-{failure_point:?}"));
                let mut reached = false;
                let result = finish_workspace_bootstrap_transaction_with_io_v1(
                    &request,
                    operation,
                    expectation,
                    rename_transaction_to_quarantine_v1,
                    |point, _| {
                        if point == *failure_point {
                            reached = true;
                            Err(WorkspaceBootstrapError::TransactionCleanupFailed)
                        } else {
                            Ok(())
                        }
                    },
                );
                assert_eq!(
                    result,
                    Err(WorkspaceBootstrapError::TransactionCleanupFailed),
                    "operation={operation:?}, failure_point={failure_point:?}"
                );
                assert!(reached);
                assert!(!transaction.exists());
                let receipt = complete_operation(operation, &request).unwrap();
                assert!(receipt.transaction_cleaned);
                assert_eq!(receipt.operation, operation);
                complete_operation(operation, &request).unwrap();
                fs::remove_dir_all(&base).unwrap();
            }
        }
    }

    #[test]
    fn polluted_or_manifestless_nonempty_quarantine_is_never_cleaned() {
        for case in ["polluted", "manifestless"] {
            let (base, workspace, _, request) = fully_stashed_transaction(case);
            let canonical_workspace = fs::canonicalize(&workspace).unwrap();
            let location =
                transaction_location_v1(&canonical_workspace, &request.transaction).unwrap();
            let quarantine = transaction_quarantine_path_v1(
                &location,
                WorkspaceBootstrapTransactionOperationV1::Commit,
            )
            .unwrap();
            let mut reached = false;
            assert_eq!(
                finish_workspace_bootstrap_transaction_with_io_v1(
                    &request,
                    WorkspaceBootstrapTransactionOperationV1::Commit,
                    TransactionWorkspaceExpectationV1::Post,
                    rename_transaction_to_quarantine_v1,
                    |point, _| {
                        if point == TransactionCleanupPointV1::Stash(0) {
                            reached = true;
                            Err(WorkspaceBootstrapError::TransactionCleanupFailed)
                        } else {
                            Ok(())
                        }
                    },
                ),
                Err(WorkspaceBootstrapError::TransactionCleanupFailed)
            );
            assert!(reached);
            if case == "polluted" {
                fs::write(quarantine.join("foreign-canary"), b"keep").unwrap();
            } else {
                fs::remove_file(quarantine.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1))
                    .unwrap();
            }
            let stash_count =
                fs::read_dir(quarantine.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1))
                    .unwrap()
                    .count();
            assert_eq!(
                commit_workspace_bootstrap_transaction_v1(&request),
                Err(WorkspaceBootstrapError::TransactionCleanupFailed)
            );
            assert_eq!(
                fs::read_dir(quarantine.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1))
                    .unwrap()
                    .count(),
                stash_count
            );
            assert!(quarantine.exists());
            fs::remove_dir_all(&base).unwrap();
        }
    }
}
