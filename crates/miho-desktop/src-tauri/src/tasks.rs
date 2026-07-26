use std::{
    ffi::{OsStr, OsString},
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::Arc,
    sync::{Mutex, MutexGuard},
    time::{Duration, Instant},
};

use miho_app::{
    bootstrap_workspace_v1, check_update_health_v1, is_valid_update_attempt_id_v1,
    load_update_config_v1, load_update_config_with_digest_v1, parse_export_task_intent_v1,
    parse_task_intent_v1, resolve_task_intent_v1, AppInvocation, CancelOutcomeV1, ExportInvocation,
    ExportTaskIntentSpecV1, FileUpdateReceiptStore, PublicTaskSnapshotV1, PublicTaskUpdateV1,
    ResolvedUpdateConfigV1, TaskFailureV1, TaskManager, TaskManagerError, TaskOperationV1,
    TrustedExportTaskV1, UpdateHealthV1, UpdateReceiptStore, UpdateStateV1, UpdateStepFailureV1,
    WorkspaceBootstrapError, WorkspaceBootstrapRequestV1, UPDATE_HEALTH_SCHEMA_V1,
};
use miho_core::pipeline::Game;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use crate::secure_log::SafeLogV1;
use crate::workspace::{
    trusted_workspace_file, validate_existing_file_chain, validate_selected_root,
    validate_workspace_target, workspace_storage_scope, workspace_storage_scope_from_identity,
    WorkspaceError, WorkspaceRegistry, WorkspaceSummaryV1,
};

const PUBLIC_COMMAND_FAILURE_SCHEMA_V1: &str = "miho-public-command-failure-v1";
const DESKTOP_CAPABILITIES_SCHEMA_V1: &str = "miho-desktop-capabilities-v1";
const DESKTOP_UPDATE_HEALTH_SCHEMA_V1: &str = "miho-desktop-update-health-v1";
const WORKSPACE_SELECTION_SCHEMA_V1: &str = "miho-workspace-selection-v1";
const CANCEL_TASK_RESULT_SCHEMA_V1: &str = "miho-public-cancel-task-result-v1";
const TASK_UPDATE_SCHEMA_V1: &str = "miho-task-update-v1";
const AUTOMATION_OWNER_SCHEMA_V1: &str = "miho-automation-owner-v1";
const AUTOMATION_OWNER_MANIFEST_V1: &str = "automation-owner-v1.json";
const AUTOMATION_AUTHORITY_SCHEMA_V1: &str = "miho-automation-authority-v1";
const AUTOMATION_AUTHORITY_V1: &str = "automation-authority-v1.json";
const AUTOMATION_UNBOUND_SCHEMA_V1: &str = "miho-automation-unbound-v1";
const AUTOMATION_UNBOUND_V1: &str = "automation-unbound-v1.json";
const AUTOMATION_CLAIM_INTENT_SUFFIX_V1: &str = ".claim-intent-v1.json";
const AUTOMATION_RELEASE_INTENT_SUFFIX_V1: &str = ".release-intent-v1.json";
const AUTOMATION_CLAIM_JOURNAL_V1: &str = "automation-owner-claim-journal-v1.json";
const AUTOMATION_JOURNAL_V1: &str = "automation-switch-journal-v1.json";
const AUTOMATION_LOCK_V1: &str = ".automation-switch-v1.lock";
const AUTOMATION_COORDINATOR_SUFFIX_V1: &str = ".coordinator-v1.lock";
const MAX_AUTOMATION_MANIFEST_BYTES_V1: u64 = 64 * 1024;
const DESKTOP_AUTOMATION_PROBE_SCHEMA_V1: &str = "miho-desktop-automation-binding-v1";
const DESKTOP_AUTOMATION_PROBE_TIMEOUT_V1: Duration = Duration::from_secs(30);
#[cfg(windows)]
const CREATE_NO_WINDOW_V1: u32 = 0x0800_0000;
const SCHEDULER_SCRIPT_BYTES_V1: &[u8] =
    include_bytes!("../../../../scripts/task_scheduler_v1.ps1");
const POWERSHELL_PROBE_COMMAND_V1: &str = r#"$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest; $utf8=New-Object System.Text.UTF8Encoding($false); [Console]::OutputEncoding=$utf8; $OutputEncoding=$utf8; . $env:MIHO_DESKTOP_SCHEDULER_SCRIPT_V1; $ownerKind=$env:MIHO_DESKTOP_EXPECTED_OWNER_KIND_V1; $ownerId=$env:MIHO_DESKTOP_EXPECTED_OWNER_INSTANCE_ID_V1; $workspace=$env:MIHO_DESKTOP_EXPECTED_WORKSPACE_V1; $holds=[bool]::Parse($env:MIHO_DESKTOP_HOLDS_SWITCH_LEASE_V1); $result=Test-MihoDesktopAutomationBindingV1 -AutomationRoot $env:MIHO_DESKTOP_AUTOMATION_ROOT_V1 -ExpectedOwnerKind $ownerKind -ExpectedOwnerInstanceId $ownerId -ExpectedWorkspace $workspace -CallerHoldsSwitchLease $holds; $result | ConvertTo-Json -Compress -Depth 4"#;
pub const TASK_UPDATE_EVENT_V1: &str = "miho-task-update-v1";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AutomationOwnerManifestV1 {
    schema: String,
    owner_sid: String,
    owner_kind: String,
    owner_instance_id: String,
    owner_epoch: String,
    install_id: String,
    task_name: String,
    task_path: String,
    canonical_workspace: PathBuf,
    canonical_config: PathBuf,
    config_relative: PathBuf,
    generation: String,
    version: String,
    generation_path: PathBuf,
    exe_path: PathBuf,
    exe_sha256: String,
    action_fingerprint: String,
    task_xml_sha256: String,
    task_sddl_sha256: String,
    source: String,
    schedule_at: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AutomationAuthorityV1 {
    schema: String,
    owner_kind: String,
    owner_instance_id: String,
    owner_epoch: String,
    owner_sid: String,
    task_name: String,
    task_path: String,
    automation_root: PathBuf,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct AutomationUnboundV1 {
    schema: String,
    owner_kind: String,
    owner_instance_id: String,
    owner_epoch: String,
    owner_sid: String,
    task_name: String,
    task_path: String,
    automation_root: PathBuf,
    prior_install_id: String,
    prior_manifest_sha256: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct DesktopAutomationProbeReceiptV1 {
    schema: String,
    status: String,
    manifest_sha256: String,
    exe_sha256: String,
    authority_sha256: String,
    unbound_sha256: String,
    task_xml_sha256: String,
    task_sddl_sha256: String,
}

pub(crate) struct AutomationProbeRunV1 {
    receipt: DesktopAutomationProbeReceiptV1,
    pinned_handles: Vec<File>,
}

#[derive(Debug)]
pub(crate) struct AutomationProbeRequestV1<'a> {
    automation_root: &'a Path,
    selected_workspace: &'a Path,
    expected_owner: Option<&'a AutomationExpectedOwnerV1>,
    caller_holds_switch_lease: bool,
}

pub(crate) trait AutomationProbeRunnerV1: Send + Sync {
    fn probe(
        &self,
        request: &AutomationProbeRequestV1<'_>,
    ) -> Result<AutomationProbeRunV1, AutomationBindingError>;
}

struct PowerShellAutomationProbeRunnerV1 {
    script_path: PathBuf,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum AutomationBindingError {
    Busy,
    Invalid,
    Conflict,
}

impl AutomationBindingError {
    pub(crate) fn startup_message(self) -> &'static str {
        match self {
            Self::Busy => {
                "Scheduled automation is changing or awaiting recovery; startup was stopped."
            }
            Self::Invalid => {
                "Scheduled automation ownership is invalid or unsafe; startup was stopped."
            }
            Self::Conflict => {
                "Scheduled automation is bound to another workspace; startup was stopped."
            }
        }
    }
}

pub(crate) struct AutomationBindingGuard {
    _lease: File,
    _identity_handles: Vec<File>,
}

pub(crate) struct AutomationCoordinatorGuard {
    _lease: File,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct AutomationExpectedOwnerV1 {
    pub(crate) kind: String,
    pub(crate) instance_id: String,
}

pub(crate) fn powershell_automation_probe_v1(
    script_path: PathBuf,
) -> Arc<dyn AutomationProbeRunnerV1> {
    Arc::new(PowerShellAutomationProbeRunnerV1 { script_path })
}

impl AutomationExpectedOwnerV1 {
    pub(crate) fn new(kind: &str, instance_id: String) -> Result<Self, AutomationBindingError> {
        if !matches!(kind, "installed" | "portable") || !is_canonical_uuid(&instance_id) {
            return Err(AutomationBindingError::Invalid);
        }
        Ok(Self {
            kind: kind.to_owned(),
            instance_id,
        })
    }
}

impl AutomationProbeRunnerV1 for PowerShellAutomationProbeRunnerV1 {
    fn probe(
        &self,
        request: &AutomationProbeRequestV1<'_>,
    ) -> Result<AutomationProbeRunV1, AutomationBindingError> {
        validate_existing_file_chain(&self.script_path)
            .map_err(|_| AutomationBindingError::Invalid)?;
        let mut script_handle = open_path_without_write_or_delete_sharing(&self.script_path)?;
        let script_bytes = read_bounded_trusted_file_handle(
            &mut script_handle,
            &self.script_path,
            2 * 1024 * 1024,
        )?;
        if sha256_hex(&script_bytes) != sha256_hex(SCHEDULER_SCRIPT_BYTES_V1) {
            return Err(AutomationBindingError::Invalid);
        }

        let powershell = windows_powershell_path_v1()?;
        validate_existing_file_chain(&powershell).map_err(|_| AutomationBindingError::Invalid)?;
        let powershell_handle = open_path_without_write_or_delete_sharing(&powershell)?;
        let (owner_kind, owner_instance_id) = request
            .expected_owner
            .map(|owner| (owner.kind.as_str(), owner.instance_id.as_str()))
            .unwrap_or(("", ""));
        let mut powershell_command = Command::new(&powershell);
        #[cfg(windows)]
        powershell_command.creation_flags(CREATE_NO_WINDOW_V1);
        let mut child = powershell_command
            .args([
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                POWERSHELL_PROBE_COMMAND_V1,
            ])
            .env("MIHO_DESKTOP_SCHEDULER_SCRIPT_V1", &self.script_path)
            .env("MIHO_DESKTOP_AUTOMATION_ROOT_V1", request.automation_root)
            .env(
                "MIHO_DESKTOP_EXPECTED_WORKSPACE_V1",
                request.selected_workspace,
            )
            .env("MIHO_DESKTOP_EXPECTED_OWNER_KIND_V1", owner_kind)
            .env(
                "MIHO_DESKTOP_EXPECTED_OWNER_INSTANCE_ID_V1",
                owner_instance_id,
            )
            .env(
                "MIHO_DESKTOP_HOLDS_SWITCH_LEASE_V1",
                if request.caller_holds_switch_lease {
                    "true"
                } else {
                    "false"
                },
            )
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|_| AutomationBindingError::Invalid)?;
        let started = Instant::now();
        loop {
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) if started.elapsed() < DESKTOP_AUTOMATION_PROBE_TIMEOUT_V1 => {
                    std::thread::sleep(Duration::from_millis(20));
                }
                Ok(None) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(AutomationBindingError::Invalid);
                }
                Err(_) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(AutomationBindingError::Invalid);
                }
            }
        }
        let output = child
            .wait_with_output()
            .map_err(|_| AutomationBindingError::Invalid)?;
        if !output.status.success() || !output.stderr.is_empty() {
            return Err(AutomationBindingError::Invalid);
        }
        let stdout =
            String::from_utf8(output.stdout).map_err(|_| AutomationBindingError::Invalid)?;
        let json = stdout
            .strip_suffix("\r\n")
            .or_else(|| stdout.strip_suffix('\n'))
            .unwrap_or(&stdout);
        if json.is_empty() || json.contains(['\r', '\n']) {
            return Err(AutomationBindingError::Invalid);
        }
        let receipt: DesktopAutomationProbeReceiptV1 =
            serde_json::from_str(json).map_err(|_| AutomationBindingError::Invalid)?;
        validate_probe_receipt_shape_v1(&receipt)?;
        Ok(AutomationProbeRunV1 {
            receipt,
            pinned_handles: vec![script_handle, powershell_handle],
        })
    }
}

fn validate_probe_receipt_shape_v1(
    receipt: &DesktopAutomationProbeReceiptV1,
) -> Result<(), AutomationBindingError> {
    if receipt.schema != DESKTOP_AUTOMATION_PROBE_SCHEMA_V1 {
        return Err(AutomationBindingError::Invalid);
    }
    let fields = [
        receipt.manifest_sha256.as_str(),
        receipt.exe_sha256.as_str(),
        receipt.authority_sha256.as_str(),
        receipt.unbound_sha256.as_str(),
        receipt.task_xml_sha256.as_str(),
        receipt.task_sddl_sha256.as_str(),
    ];
    let empty = |index: usize| fields[index].is_empty();
    let hash = |index: usize| is_lower_hex_sha256(fields[index]);
    let valid = match receipt.status.as_str() {
        "active" => hash(0) && hash(1) && hash(2) && empty(3) && hash(4) && hash(5),
        "clean-unbound" => empty(0) && empty(1) && hash(2) && hash(3) && empty(4) && empty(5),
        "absent" | "busy" | "invalid" | "conflict" => fields.iter().all(|value| value.is_empty()),
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err(AutomationBindingError::Invalid)
    }
}

#[cfg(windows)]
fn windows_powershell_path_v1() -> Result<PathBuf, AutomationBindingError> {
    use windows_sys::Win32::System::SystemInformation::GetSystemDirectoryW;

    let mut buffer = vec![0_u16; 32_768];
    // SAFETY: `buffer` is writable for the supplied length and remains alive
    // until the API returns the number of UTF-16 code units written.
    let length = unsafe { GetSystemDirectoryW(buffer.as_mut_ptr(), buffer.len() as u32) };
    if length == 0 || length as usize >= buffer.len() {
        return Err(AutomationBindingError::Invalid);
    }
    buffer.truncate(length as usize);
    let system_directory =
        String::from_utf16(&buffer).map_err(|_| AutomationBindingError::Invalid)?;
    Ok(PathBuf::from(system_directory)
        .join("WindowsPowerShell")
        .join("v1.0")
        .join("powershell.exe"))
}

#[cfg(not(windows))]
fn windows_powershell_path_v1() -> Result<PathBuf, AutomationBindingError> {
    Err(AutomationBindingError::Invalid)
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicCommandFailureV1 {
    pub schema_version: String,
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

impl PublicCommandFailureV1 {
    fn new(code: &str, message: &str, retryable: bool) -> Self {
        Self {
            schema_version: PUBLIC_COMMAND_FAILURE_SCHEMA_V1.to_owned(),
            code: code.to_owned(),
            message: message.to_owned(),
            retryable,
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationCapabilityV1 {
    pub operation: TaskOperationV1,
    pub enabled: bool,
    pub missing_inputs: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DesktopCapabilitiesV1 {
    pub schema_version: String,
    pub workspace: WorkspaceSummaryV1,
    pub workspace_selection_enabled: bool,
    pub operations: Vec<OperationCapabilityV1>,
    pub max_concurrent_tasks: u8,
    pub supports_cancel: bool,
    pub task_history_persistent: bool,
    pub task_update_event: String,
    pub task_queries_are_authoritative: bool,
    pub abrupt_termination_supported: bool,
    pub cross_process_recovery_supported: bool,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DesktopUpdateHealthGameV1 {
    pub game: Game,
    pub attempt_id: String,
    pub completed_at_utc: String,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DesktopUpdateHealthV1 {
    pub schema_version: String,
    pub workspace_id: String,
    pub healthy: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub attempt_id: Option<String>,
    pub checked_games: Vec<Game>,
    pub games: Vec<DesktopUpdateHealthGameV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure_code: Option<String>,
    pub retryable: bool,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceSelectionV1 {
    pub schema_version: String,
    pub selected: bool,
    pub workspace: WorkspaceSummaryV1,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicCancelTaskResultV1 {
    pub schema_version: String,
    pub task_id: String,
    pub outcome: CancelOutcomeV1,
    pub task: Option<PublicTaskSnapshotV1>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct DesktopTaskUpdateV1 {
    schema_version: String,
    sequence: u64,
    task: PublicTaskSnapshotV1,
}

pub struct DesktopState {
    pub workspaces: WorkspaceRegistry,
    pub tasks: TaskManager,
    workspace_task_gate: Mutex<()>,
    portable_storage_identity: Option<String>,
    automation_root: Option<PathBuf>,
    automation_owner: Option<AutomationExpectedOwnerV1>,
    automation_probe: Option<Arc<dyn AutomationProbeRunnerV1>>,
    _automation_coordinator: Option<AutomationCoordinatorGuard>,
}

impl DesktopState {
    pub fn new(workspaces: WorkspaceRegistry, tasks: TaskManager) -> Self {
        Self {
            workspaces,
            tasks,
            workspace_task_gate: Mutex::new(()),
            portable_storage_identity: None,
            automation_root: None,
            automation_owner: None,
            automation_probe: None,
            _automation_coordinator: None,
        }
    }

    pub fn with_portable_storage_identity(
        workspaces: WorkspaceRegistry,
        tasks: TaskManager,
        identity: String,
    ) -> Self {
        Self {
            workspaces,
            tasks,
            workspace_task_gate: Mutex::new(()),
            portable_storage_identity: Some(identity),
            automation_root: None,
            automation_owner: None,
            automation_probe: None,
            _automation_coordinator: None,
        }
    }

    pub fn with_automation_root(mut self, automation_root: PathBuf) -> Self {
        self.automation_root = Some(automation_root);
        self
    }

    pub(crate) fn with_automation_owner(mut self, owner: AutomationExpectedOwnerV1) -> Self {
        self.automation_owner = Some(owner);
        self
    }

    pub(crate) fn with_automation_probe(mut self, probe: Arc<dyn AutomationProbeRunnerV1>) -> Self {
        self.automation_probe = Some(probe);
        self
    }

    pub fn with_automation_coordinator(mut self, coordinator: AutomationCoordinatorGuard) -> Self {
        self._automation_coordinator = Some(coordinator);
        self
    }

    pub(crate) fn storage_scope(&self, root: &std::path::Path) -> Result<String, WorkspaceError> {
        match self.portable_storage_identity.as_deref() {
            Some(identity) => workspace_storage_scope_from_identity(root, identity),
            None => workspace_storage_scope(root),
        }
    }

    pub(crate) fn lock_gate(&self) -> Result<MutexGuard<'_, ()>, PublicCommandFailureV1> {
        self.workspace_task_gate.lock().map_err(|_| {
            PublicCommandFailureV1::new(
                "desktop.state_unavailable",
                "Desktop state is unavailable.",
                true,
            )
        })
    }

    fn has_active_task(&self) -> bool {
        self.tasks
            .list_public()
            .iter()
            .any(|task| !task.status.is_terminal())
    }
}

#[tauri::command]
pub fn get_capabilities(
    state: State<'_, DesktopState>,
) -> Result<DesktopCapabilitiesV1, PublicCommandFailureV1> {
    capabilities(&state)
}

#[tauri::command]
pub async fn get_update_health(
    state: State<'_, DesktopState>,
) -> Result<DesktopUpdateHealthV1, PublicCommandFailureV1> {
    let (root, workspace) = state
        .workspaces
        .active_access()
        .map_err(map_workspace_error)?;
    let workspace_id = workspace.workspace_id;
    tauri::async_runtime::spawn_blocking(move || get_update_health_blocking(root, workspace_id))
        .await
        .map_err(|_| {
            PublicCommandFailureV1::new(
                "update.health_check_failed",
                "Update health could not be checked.",
                true,
            )
        })?
}

#[tauri::command]
pub async fn select_workspace(
    app: AppHandle,
    state: State<'_, DesktopState>,
) -> Result<WorkspaceSelectionV1, PublicCommandFailureV1> {
    if state.workspaces.environment_locked() {
        return Err(map_workspace_error(WorkspaceError::EnvironmentLocked));
    }
    {
        let _gate = state.lock_gate()?;
        ensure_idle(&state)?;
    }

    let picker_app = app.clone();
    let selected = tauri::async_runtime::spawn_blocking(move || {
        picker_app.dialog().file().blocking_pick_folder()
    })
    .await
    .map_err(|_| {
        PublicCommandFailureV1::new(
            "workspace.dialog_failed",
            "The native folder picker could not be opened.",
            true,
        )
    })?;

    let Some(selected) = selected else {
        return Ok(WorkspaceSelectionV1 {
            schema_version: WORKSPACE_SELECTION_SCHEMA_V1.to_owned(),
            selected: false,
            workspace: state.workspaces.summary().map_err(map_workspace_error)?,
        });
    };
    let root = selected.into_path().map_err(|_| {
        PublicCommandFailureV1::new(
            "workspace.invalid_selection",
            "The selected folder is not a supported local workspace.",
            false,
        )
    })?;

    let _gate = state.lock_gate()?;
    ensure_idle(&state)?;
    let workspace = commit_workspace_selection(&state, root)?;
    Ok(WorkspaceSelectionV1 {
        schema_version: WORKSPACE_SELECTION_SCHEMA_V1.to_owned(),
        selected: true,
        workspace,
    })
}

fn commit_workspace_selection(
    state: &DesktopState,
    root: std::path::PathBuf,
) -> Result<WorkspaceSummaryV1, PublicCommandFailureV1> {
    validate_selected_root(&root).map_err(map_workspace_error)?;
    let mut _automation_guard = acquire_automation_workspace_binding(
        state.automation_root.as_deref(),
        &root,
        state.automation_owner.as_ref(),
        state.automation_probe.as_deref(),
    )
    .map_err(map_automation_binding_error)?;
    bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(root.clone()))
        .map_err(map_workspace_bootstrap_error)?;
    if _automation_guard.is_none() {
        _automation_guard = acquire_automation_workspace_binding(
            state.automation_root.as_deref(),
            &root,
            state.automation_owner.as_ref(),
            state.automation_probe.as_deref(),
        )
        .map_err(map_automation_binding_error)?;
    }
    state.workspaces.select(root).map_err(map_workspace_error)
}

pub(crate) fn acquire_automation_workspace_binding(
    automation_root: Option<&Path>,
    selected_workspace: &Path,
    expected_owner: Option<&AutomationExpectedOwnerV1>,
    probe: Option<&dyn AutomationProbeRunnerV1>,
) -> Result<Option<AutomationBindingGuard>, AutomationBindingError> {
    let Some(automation_root) = automation_root else {
        return Ok(None);
    };
    validate_selected_root(selected_workspace).map_err(|_| AutomationBindingError::Invalid)?;
    let root_exists = match fs::symlink_metadata(automation_root) {
        Ok(_) => {
            validate_selected_root(automation_root).map_err(|_| AutomationBindingError::Invalid)?;
            true
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let mut intent_exists = false;
            for intent_path in [
                automation_claim_intent_path_v1(automation_root)?,
                automation_release_intent_path_v1(automation_root)?,
            ] {
                match fs::symlink_metadata(&intent_path) {
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                    Ok(_) => {
                        validate_existing_file_chain(&intent_path)
                            .map_err(|_| AutomationBindingError::Invalid)?;
                        intent_exists = true;
                    }
                    Err(_) => return Err(AutomationBindingError::Invalid),
                }
            }
            if !intent_exists {
                return Ok(None);
            }
            false
        }
        Err(_) => return Err(AutomationBindingError::Invalid),
    };
    let lock_path = automation_root.join(AUTOMATION_LOCK_V1);
    let lock_exists = match fs::symlink_metadata(&lock_path) {
        Ok(_) => {
            validate_existing_file_chain(&lock_path)
                .map_err(|_| AutomationBindingError::Invalid)?;
            true
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(_) => return Err(AutomationBindingError::Invalid),
    };
    if !lock_exists {
        let run =
            probe
                .ok_or(AutomationBindingError::Invalid)?
                .probe(&AutomationProbeRequestV1 {
                    automation_root,
                    selected_workspace,
                    expected_owner,
                    caller_holds_switch_lease: false,
                })?;
        validate_probe_receipt_shape_v1(&run.receipt)?;
        return match run.receipt.status.as_str() {
            "busy" => Err(AutomationBindingError::Busy),
            "conflict" => Err(AutomationBindingError::Conflict),
            "invalid" => Err(AutomationBindingError::Invalid),
            _ => Err(AutomationBindingError::Invalid),
        };
    }
    if !root_exists {
        return Err(AutomationBindingError::Invalid);
    }
    let expected_owner = expected_owner.ok_or(AutomationBindingError::Invalid)?;
    let mut identity_handles = vec![open_path_without_delete_sharing(automation_root)?];
    validate_selected_root(automation_root).map_err(|_| AutomationBindingError::Invalid)?;
    let mut options = OpenOptions::new();
    options.read(true).write(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0);
    }
    let lease = options.open(&lock_path).map_err(|error| {
        if is_automation_lock_contention(&error) {
            AutomationBindingError::Busy
        } else {
            AutomationBindingError::Invalid
        }
    })?;
    validate_existing_file_chain(&lock_path).map_err(|_| AutomationBindingError::Invalid)?;
    let run = probe
        .ok_or(AutomationBindingError::Invalid)?
        .probe(&AutomationProbeRequestV1 {
            automation_root,
            selected_workspace,
            expected_owner: Some(expected_owner),
            caller_holds_switch_lease: true,
        })?;
    validate_probe_receipt_shape_v1(&run.receipt)?;
    identity_handles.extend(run.pinned_handles);
    match run.receipt.status.as_str() {
        "active" => validate_active_automation_evidence_v1(
            &run.receipt,
            automation_root,
            selected_workspace,
            expected_owner,
            &mut identity_handles,
        )?,
        "clean-unbound" => validate_clean_unbound_automation_evidence_v1(
            &run.receipt,
            automation_root,
            expected_owner,
            &mut identity_handles,
        )?,
        "busy" => return Err(AutomationBindingError::Busy),
        "conflict" => return Err(AutomationBindingError::Conflict),
        "invalid" | "absent" => return Err(AutomationBindingError::Invalid),
        _ => return Err(AutomationBindingError::Invalid),
    }
    Ok(Some(AutomationBindingGuard {
        _lease: lease,
        _identity_handles: identity_handles,
    }))
}

fn automation_claim_intent_path_v1(
    automation_root: &Path,
) -> Result<PathBuf, AutomationBindingError> {
    automation_sibling_intent_path_v1(automation_root, AUTOMATION_CLAIM_INTENT_SUFFIX_V1)
}

fn automation_release_intent_path_v1(
    automation_root: &Path,
) -> Result<PathBuf, AutomationBindingError> {
    automation_sibling_intent_path_v1(automation_root, AUTOMATION_RELEASE_INTENT_SUFFIX_V1)
}

fn automation_sibling_intent_path_v1(
    automation_root: &Path,
    suffix: &str,
) -> Result<PathBuf, AutomationBindingError> {
    if !automation_root.is_absolute()
        || automation_root.components().any(|component| {
            !matches!(
                component,
                std::path::Component::Prefix(_)
                    | std::path::Component::RootDir
                    | std::path::Component::Normal(_)
            )
        })
    {
        return Err(AutomationBindingError::Invalid);
    }
    let parent = automation_root
        .parent()
        .ok_or(AutomationBindingError::Invalid)?;
    let file_name = automation_root
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or(AutomationBindingError::Invalid)?;
    Ok(parent.join(format!("{file_name}{suffix}")))
}

fn validate_active_automation_evidence_v1(
    receipt: &DesktopAutomationProbeReceiptV1,
    automation_root: &Path,
    selected_workspace: &Path,
    expected_owner: &AutomationExpectedOwnerV1,
    identity_handles: &mut Vec<File>,
) -> Result<(), AutomationBindingError> {
    validate_active_automation_evidence_with_final_hook_v1(
        receipt,
        automation_root,
        selected_workspace,
        expected_owner,
        identity_handles,
        || {},
    )
}

fn validate_active_automation_evidence_with_final_hook_v1<F: FnOnce()>(
    receipt: &DesktopAutomationProbeReceiptV1,
    automation_root: &Path,
    selected_workspace: &Path,
    expected_owner: &AutomationExpectedOwnerV1,
    identity_handles: &mut Vec<File>,
    before_final_generation_check: F,
) -> Result<(), AutomationBindingError> {
    assert_automation_path_absent_v1(&automation_root.join(AUTOMATION_UNBOUND_V1))?;
    assert_automation_path_absent_v1(&automation_root.join(AUTOMATION_CLAIM_JOURNAL_V1))?;
    assert_automation_path_absent_v1(&automation_root.join(AUTOMATION_JOURNAL_V1))?;
    assert_automation_path_absent_v1(&automation_claim_intent_path_v1(automation_root)?)?;
    assert_automation_path_absent_v1(&automation_release_intent_path_v1(automation_root)?)?;

    let authority_path = automation_root.join(AUTOMATION_AUTHORITY_V1);
    let (authority, authority_bytes, authority_handle) =
        read_bounded_json_evidence_v1::<AutomationAuthorityV1>(&authority_path)?;
    if sha256_hex(&authority_bytes) != receipt.authority_sha256 {
        return Err(AutomationBindingError::Invalid);
    }
    identity_handles.push(authority_handle);
    validate_automation_authority_v1(
        &authority,
        automation_root,
        expected_owner,
        identity_handles,
    )?;

    let manifest_path = automation_root.join(AUTOMATION_OWNER_MANIFEST_V1);
    let (manifest, manifest_bytes, manifest_handle) =
        read_bounded_json_evidence_v1::<AutomationOwnerManifestV1>(&manifest_path)?;
    if sha256_hex(&manifest_bytes) != receipt.manifest_sha256 {
        return Err(AutomationBindingError::Invalid);
    }
    identity_handles.push(manifest_handle);
    validate_automation_owner_manifest(&manifest, automation_root, identity_handles)?;
    if manifest.owner_kind != expected_owner.kind
        || manifest.owner_instance_id != expected_owner.instance_id
        || manifest.owner_kind != authority.owner_kind
        || manifest.owner_instance_id != authority.owner_instance_id
        || manifest.owner_epoch != authority.owner_epoch
        || manifest.owner_sid != authority.owner_sid
        || manifest.task_name != authority.task_name
        || manifest.task_path != authority.task_path
        || manifest.task_xml_sha256 != receipt.task_xml_sha256
        || manifest.task_sddl_sha256 != receipt.task_sddl_sha256
        || manifest.exe_sha256 != receipt.exe_sha256
        || manifest.source
            != format!(
                "com.miho.endgame/automation-v1/{}/{}/{}/{}",
                manifest.owner_kind,
                manifest.owner_instance_id,
                manifest.owner_epoch,
                manifest.install_id
            )
        || manifest
            .generation_path
            .file_name()
            .is_none_or(|name| name != manifest.generation.as_str())
    {
        return Err(AutomationBindingError::Invalid);
    }
    if !trusted_directories_equal(
        &manifest.canonical_workspace,
        selected_workspace,
        identity_handles,
    )? {
        return Err(AutomationBindingError::Conflict);
    }
    let mut executable_handle = open_path_without_write_or_delete_sharing(&manifest.exe_path)?;
    let actual_executable_hash = hash_file_handle_v1(&mut executable_handle, &manifest.exe_path)?;
    if actual_executable_hash != receipt.exe_sha256 {
        return Err(AutomationBindingError::Invalid);
    }
    identity_handles.push(executable_handle);
    before_final_generation_check();
    // The process-wide coordinator and switch lease exclude every cooperative
    // producer. Keep the exact membership check last so the accepted snapshot
    // is linearized at the end of validation. Retained directory handles pin
    // path identity; they do not claim to freeze membership on Windows.
    validate_owned_generation_root_v1(automation_root, &manifest, identity_handles)?;
    Ok(())
}

fn validate_owned_generation_root_v1(
    automation_root: &Path,
    manifest: &AutomationOwnerManifestV1,
    identity_handles: &mut Vec<File>,
) -> Result<(), AutomationBindingError> {
    let generations = automation_root.join("generations");
    validate_selected_root(&generations).map_err(|_| AutomationBindingError::Invalid)?;
    let generations_handle = open_path_without_delete_sharing(&generations)?;
    for _ in 0..2 {
        let mut found_generation = false;
        for entry in fs::read_dir(&generations).map_err(|_| AutomationBindingError::Invalid)? {
            let entry = entry.map_err(|_| AutomationBindingError::Invalid)?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| AutomationBindingError::Invalid)?;
            let file_type = entry
                .file_type()
                .map_err(|_| AutomationBindingError::Invalid)?;
            if name == manifest.generation {
                if found_generation || !file_type.is_dir() {
                    return Err(AutomationBindingError::Invalid);
                }
                found_generation = true;
            } else if !is_private_generation_staging_name_v1(&name) || !file_type.is_dir() {
                return Err(AutomationBindingError::Invalid);
            }
            validate_selected_root(&entry.path()).map_err(|_| AutomationBindingError::Invalid)?;
        }
        if !found_generation {
            return Err(AutomationBindingError::Invalid);
        }
    }
    identity_handles.push(generations_handle);

    let generation_path = &manifest.generation_path;
    validate_selected_root(generation_path).map_err(|_| AutomationBindingError::Invalid)?;
    let generation_handle = open_path_without_delete_sharing(generation_path)?;
    for _ in 0..2 {
        let mut entries =
            fs::read_dir(generation_path).map_err(|_| AutomationBindingError::Invalid)?;
        let entry = entries
            .next()
            .transpose()
            .map_err(|_| AutomationBindingError::Invalid)?
            .ok_or(AutomationBindingError::Invalid)?;
        if entry.file_name() != "miho.exe"
            || entries.next().is_some()
            || !entry
                .file_type()
                .map_err(|_| AutomationBindingError::Invalid)?
                .is_file()
        {
            return Err(AutomationBindingError::Invalid);
        }
        validate_existing_file_chain(&entry.path()).map_err(|_| AutomationBindingError::Invalid)?;
    }
    identity_handles.push(generation_handle);
    Ok(())
}

fn is_private_generation_staging_name_v1(name: &str) -> bool {
    name.strip_prefix(".staging-").is_some_and(|nonce| {
        nonce.len() == 32
            && nonce
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    })
}

fn validate_clean_unbound_automation_evidence_v1(
    receipt: &DesktopAutomationProbeReceiptV1,
    automation_root: &Path,
    expected_owner: &AutomationExpectedOwnerV1,
    identity_handles: &mut Vec<File>,
) -> Result<(), AutomationBindingError> {
    validate_clean_unbound_automation_evidence_with_final_hook_v1(
        receipt,
        automation_root,
        expected_owner,
        identity_handles,
        || {},
    )
}

fn validate_clean_unbound_automation_evidence_with_final_hook_v1<F: FnOnce()>(
    receipt: &DesktopAutomationProbeReceiptV1,
    automation_root: &Path,
    expected_owner: &AutomationExpectedOwnerV1,
    identity_handles: &mut Vec<File>,
    before_final_generation_check: F,
) -> Result<(), AutomationBindingError> {
    for path in [
        automation_root.join(AUTOMATION_OWNER_MANIFEST_V1),
        automation_root.join(AUTOMATION_CLAIM_JOURNAL_V1),
        automation_root.join(AUTOMATION_JOURNAL_V1),
        automation_claim_intent_path_v1(automation_root)?,
        automation_release_intent_path_v1(automation_root)?,
    ] {
        assert_automation_path_absent_v1(&path)?;
    }
    let generations = automation_root.join("generations");
    validate_workspace_target(automation_root, &generations)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_selected_root(&generations).map_err(|_| AutomationBindingError::Invalid)?;
    let generations_handle = open_path_without_delete_sharing(&generations)?;
    if fs::read_dir(&generations)
        .map_err(|_| AutomationBindingError::Invalid)?
        .next()
        .is_some()
    {
        return Err(AutomationBindingError::Invalid);
    }
    validate_selected_root(&generations).map_err(|_| AutomationBindingError::Invalid)?;
    if fs::read_dir(&generations)
        .map_err(|_| AutomationBindingError::Invalid)?
        .next()
        .is_some()
    {
        return Err(AutomationBindingError::Invalid);
    }
    identity_handles.push(generations_handle);
    let authority_path = automation_root.join(AUTOMATION_AUTHORITY_V1);
    let (authority, authority_bytes, authority_handle) =
        read_bounded_json_evidence_v1::<AutomationAuthorityV1>(&authority_path)?;
    if sha256_hex(&authority_bytes) != receipt.authority_sha256 {
        return Err(AutomationBindingError::Invalid);
    }
    identity_handles.push(authority_handle);
    validate_automation_authority_v1(
        &authority,
        automation_root,
        expected_owner,
        identity_handles,
    )?;

    let unbound_path = automation_root.join(AUTOMATION_UNBOUND_V1);
    let (unbound, unbound_bytes, unbound_handle) =
        read_bounded_json_evidence_v1::<AutomationUnboundV1>(&unbound_path)?;
    if sha256_hex(&unbound_bytes) != receipt.unbound_sha256
        || unbound.schema != AUTOMATION_UNBOUND_SCHEMA_V1
        || unbound.owner_kind != authority.owner_kind
        || unbound.owner_instance_id != authority.owner_instance_id
        || unbound.owner_epoch != authority.owner_epoch
        || unbound.owner_sid != authority.owner_sid
        || unbound.task_name != authority.task_name
        || unbound.task_path != authority.task_path
        || (unbound.prior_install_id.is_empty() != unbound.prior_manifest_sha256.is_empty())
        || (!unbound.prior_install_id.is_empty()
            && (!is_canonical_uuid(&unbound.prior_install_id)
                || !is_lower_hex_sha256(&unbound.prior_manifest_sha256)))
    {
        return Err(AutomationBindingError::Invalid);
    }
    if !trusted_directories_equal(&unbound.automation_root, automation_root, identity_handles)? {
        return Err(AutomationBindingError::Invalid);
    }
    identity_handles.push(unbound_handle);
    before_final_generation_check();
    validate_selected_root(&generations).map_err(|_| AutomationBindingError::Invalid)?;
    if fs::read_dir(&generations)
        .map_err(|_| AutomationBindingError::Invalid)?
        .next()
        .is_some()
    {
        return Err(AutomationBindingError::Invalid);
    }
    Ok(())
}

fn validate_automation_authority_v1(
    authority: &AutomationAuthorityV1,
    automation_root: &Path,
    expected_owner: &AutomationExpectedOwnerV1,
    identity_handles: &mut Vec<File>,
) -> Result<(), AutomationBindingError> {
    let sid_hash = sha256_hex(authority.owner_sid.as_bytes());
    if authority.schema != AUTOMATION_AUTHORITY_SCHEMA_V1
        || authority.owner_kind != expected_owner.kind
        || authority.owner_instance_id != expected_owner.instance_id
        || !is_canonical_uuid(&authority.owner_instance_id)
        || !is_canonical_uuid(&authority.owner_epoch)
        || authority.owner_sid.trim().is_empty()
        || authority.task_path != "\\"
        || authority.task_name != format!("MihoEndgameDailyUpdate-{}", &sid_hash[..16])
    {
        return Err(AutomationBindingError::Invalid);
    }
    if !trusted_directories_equal(
        &authority.automation_root,
        automation_root,
        identity_handles,
    )? {
        return Err(AutomationBindingError::Invalid);
    }
    Ok(())
}

fn read_bounded_json_evidence_v1<T: serde::de::DeserializeOwned>(
    path: &Path,
) -> Result<(T, Vec<u8>, File), AutomationBindingError> {
    validate_existing_file_chain(path).map_err(|_| AutomationBindingError::Invalid)?;
    let mut handle = open_path_without_write_or_delete_sharing(path)?;
    let first =
        read_bounded_trusted_file_handle(&mut handle, path, MAX_AUTOMATION_MANIFEST_BYTES_V1)?;
    let second =
        read_bounded_trusted_file_handle(&mut handle, path, MAX_AUTOMATION_MANIFEST_BYTES_V1)?;
    if first != second {
        return Err(AutomationBindingError::Invalid);
    }
    let parsed =
        serde_json::from_slice::<T>(&first).map_err(|_| AutomationBindingError::Invalid)?;
    Ok((parsed, first, handle))
}

fn hash_file_handle_v1(file: &mut File, path: &Path) -> Result<String, AutomationBindingError> {
    validate_existing_file_chain(path).map_err(|_| AutomationBindingError::Invalid)?;
    let before = file
        .metadata()
        .map_err(|_| AutomationBindingError::Invalid)?;
    file.seek(SeekFrom::Start(0))
        .map_err(|_| AutomationBindingError::Invalid)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total = 0_u64;
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|_| AutomationBindingError::Invalid)?;
        if read == 0 {
            break;
        }
        total = total
            .checked_add(read as u64)
            .ok_or(AutomationBindingError::Invalid)?;
        hasher.update(&buffer[..read]);
    }
    let after = file
        .metadata()
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_existing_file_chain(path).map_err(|_| AutomationBindingError::Invalid)?;
    if before.len() != total || after.len() != total {
        return Err(AutomationBindingError::Invalid);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn assert_automation_path_absent_v1(path: &Path) -> Result<(), AutomationBindingError> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        _ => Err(AutomationBindingError::Invalid),
    }
}

pub(crate) fn acquire_automation_coordinator(
    automation_root: &Path,
) -> Result<AutomationCoordinatorGuard, AutomationBindingError> {
    if !automation_root.is_absolute()
        || automation_root.components().any(|component| {
            !matches!(
                component,
                std::path::Component::Prefix(_)
                    | std::path::Component::RootDir
                    | std::path::Component::Normal(_)
            )
        })
    {
        return Err(AutomationBindingError::Invalid);
    }
    let parent = automation_root
        .parent()
        .ok_or(AutomationBindingError::Invalid)?;
    validate_selected_root(parent).map_err(|_| AutomationBindingError::Invalid)?;
    let file_name = automation_root
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(AutomationBindingError::Invalid)?;
    let coordinator_path = parent.join(format!("{file_name}{AUTOMATION_COORDINATOR_SUFFIX_V1}"));
    match fs::symlink_metadata(&coordinator_path) {
        Ok(_) => validate_existing_file_chain(&coordinator_path)
            .map_err(|_| AutomationBindingError::Invalid)?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err(AutomationBindingError::Invalid),
    }
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0);
    }
    let lease = options.open(&coordinator_path).map_err(|error| {
        if is_automation_lock_contention(&error) {
            AutomationBindingError::Busy
        } else {
            AutomationBindingError::Invalid
        }
    })?;
    validate_existing_file_chain(&coordinator_path).map_err(|_| AutomationBindingError::Invalid)?;
    Ok(AutomationCoordinatorGuard { _lease: lease })
}

fn is_automation_lock_contention(error: &std::io::Error) -> bool {
    if matches!(
        error.kind(),
        std::io::ErrorKind::PermissionDenied | std::io::ErrorKind::WouldBlock
    ) {
        return true;
    }
    #[cfg(windows)]
    {
        // ERROR_SHARING_VIOLATION / ERROR_LOCK_VIOLATION are surfaced as raw
        // OS errors by std on some Windows toolchains.
        matches!(error.raw_os_error(), Some(32 | 33))
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn read_bounded_trusted_file_handle(
    file: &mut File,
    path: &Path,
    maximum_bytes: u64,
) -> Result<Vec<u8>, AutomationBindingError> {
    validate_existing_file_chain(path).map_err(|_| AutomationBindingError::Invalid)?;
    let metadata = file
        .metadata()
        .map_err(|_| AutomationBindingError::Invalid)?;
    if metadata.len() > maximum_bytes {
        return Err(AutomationBindingError::Invalid);
    }
    file.seek(SeekFrom::Start(0))
        .map_err(|_| AutomationBindingError::Invalid)?;
    let mut bytes = Vec::new();
    (&mut *file)
        .take(maximum_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|_| AutomationBindingError::Invalid)?;
    if bytes.len() as u64 > maximum_bytes || bytes.len() as u64 != metadata.len() {
        return Err(AutomationBindingError::Invalid);
    }
    validate_existing_file_chain(path).map_err(|_| AutomationBindingError::Invalid)?;
    let after = file
        .metadata()
        .map_err(|_| AutomationBindingError::Invalid)?;
    if after.len() != bytes.len() as u64 {
        return Err(AutomationBindingError::Invalid);
    }
    Ok(bytes)
}

fn validate_automation_owner_manifest(
    manifest: &AutomationOwnerManifestV1,
    automation_root: &Path,
    identity_handles: &mut Vec<File>,
) -> Result<(), AutomationBindingError> {
    if manifest.schema != AUTOMATION_OWNER_SCHEMA_V1
        || !matches!(
            manifest.owner_kind.as_str(),
            "installed" | "portable" | "manual"
        )
        || !is_canonical_uuid(&manifest.owner_instance_id)
        || !is_canonical_uuid(&manifest.owner_epoch)
        || !is_canonical_uuid(&manifest.install_id)
        || manifest.owner_sid.trim().is_empty()
        || manifest.task_name.trim().is_empty()
        || manifest.task_path != "\\"
        || manifest.generation.trim().is_empty()
        || manifest.version.trim().is_empty()
        || manifest.source.trim().is_empty()
        || !is_schedule_time(&manifest.schedule_at)
        || ![
            &manifest.exe_sha256,
            &manifest.action_fingerprint,
            &manifest.task_xml_sha256,
            &manifest.task_sddl_sha256,
        ]
        .into_iter()
        .all(|value| is_lower_hex_sha256(value))
        || manifest.config_relative.as_os_str().is_empty()
        || manifest.config_relative.is_absolute()
        || !manifest
            .config_relative
            .components()
            .all(|component| matches!(component, std::path::Component::Normal(_)))
    {
        return Err(AutomationBindingError::Invalid);
    }
    validate_selected_root(&manifest.canonical_workspace)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_workspace_target(&manifest.canonical_workspace, &manifest.canonical_config)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_existing_file_chain(&manifest.canonical_config)
        .map_err(|_| AutomationBindingError::Invalid)?;
    let expected_config = manifest.canonical_workspace.join(&manifest.config_relative);
    validate_workspace_target(&manifest.canonical_workspace, &expected_config)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_existing_file_chain(&expected_config).map_err(|_| AutomationBindingError::Invalid)?;
    if !trusted_existing_paths_equal(
        &manifest.canonical_config,
        &expected_config,
        identity_handles,
    )? {
        return Err(AutomationBindingError::Invalid);
    }
    let generations = automation_root.join("generations");
    validate_workspace_target(automation_root, &generations)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_selected_root(&generations).map_err(|_| AutomationBindingError::Invalid)?;
    validate_workspace_target(automation_root, &manifest.generation_path)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_selected_root(&manifest.generation_path)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_workspace_target(&manifest.generation_path, &manifest.exe_path)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_existing_file_chain(&manifest.exe_path)
        .map_err(|_| AutomationBindingError::Invalid)?;
    let expected_executable = manifest.generation_path.join("miho.exe");
    validate_workspace_target(&manifest.generation_path, &expected_executable)
        .map_err(|_| AutomationBindingError::Invalid)?;
    validate_existing_file_chain(&expected_executable)
        .map_err(|_| AutomationBindingError::Invalid)?;
    if !trusted_existing_paths_equal(
        manifest
            .generation_path
            .parent()
            .ok_or(AutomationBindingError::Invalid)?,
        &generations,
        identity_handles,
    )? || !trusted_existing_paths_equal(
        &manifest.exe_path,
        &expected_executable,
        identity_handles,
    )? {
        return Err(AutomationBindingError::Invalid);
    }
    Ok(())
}

fn is_canonical_uuid(value: &str) -> bool {
    uuid::Uuid::parse_str(value)
        .ok()
        .is_some_and(|parsed| parsed.to_string() == value)
}

fn is_lower_hex_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn is_schedule_time(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 5
        && bytes[2] == b':'
        && bytes[0].is_ascii_digit()
        && bytes[1].is_ascii_digit()
        && bytes[3].is_ascii_digit()
        && bytes[4].is_ascii_digit()
        && value[..2].parse::<u8>().is_ok_and(|hour| hour < 24)
        && value[3..].parse::<u8>().is_ok_and(|minute| minute < 60)
}

fn trusted_directories_equal(
    left: &Path,
    right: &Path,
    identity_handles: &mut Vec<File>,
) -> Result<bool, AutomationBindingError> {
    validate_selected_root(left).map_err(|_| AutomationBindingError::Invalid)?;
    validate_selected_root(right).map_err(|_| AutomationBindingError::Invalid)?;
    trusted_existing_paths_equal(left, right, identity_handles)
}

fn trusted_existing_paths_equal(
    left: &Path,
    right: &Path,
    identity_handles: &mut Vec<File>,
) -> Result<bool, AutomationBindingError> {
    #[cfg(windows)]
    {
        let left = open_path_without_delete_sharing(left)?;
        let right = open_path_without_delete_sharing(right)?;
        let left_identity = windows_file_identity(&left)?;
        let right_identity = windows_file_identity(&right)?;
        identity_handles.push(left);
        identity_handles.push(right);
        Ok(left_identity == right_identity)
    }
    #[cfg(not(windows))]
    {
        let left = fs::canonicalize(left).map_err(|_| AutomationBindingError::Invalid)?;
        let right = fs::canonicalize(right).map_err(|_| AutomationBindingError::Invalid)?;
        let equal = left == right;
        identity_handles.push(open_path_without_delete_sharing(&left)?);
        identity_handles.push(open_path_without_delete_sharing(&right)?);
        Ok(equal)
    }
}

#[cfg(windows)]
fn windows_file_identity(file: &File) -> Result<(u32, u64), AutomationBindingError> {
    use std::{mem::MaybeUninit, os::windows::io::AsRawHandle};
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };
    let mut information = MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    // SAFETY: `file` owns a valid Windows handle for the duration of the call,
    // and `information` points to writable storage for the documented result.
    let succeeded =
        unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) };
    if succeeded == 0 {
        return Err(AutomationBindingError::Invalid);
    }
    // SAFETY: the API returned success and initialized the full structure.
    let information = unsafe { information.assume_init() };
    Ok((
        information.dwVolumeSerialNumber,
        (u64::from(information.nFileIndexHigh) << 32) | u64::from(information.nFileIndexLow),
    ))
}

fn open_path_without_delete_sharing(path: &Path) -> Result<File, AutomationBindingError> {
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        use windows_sys::Win32::Storage::FileSystem::{
            FILE_FLAG_BACKUP_SEMANTICS, FILE_SHARE_READ, FILE_SHARE_WRITE,
        };

        OpenOptions::new()
            .read(true)
            .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
            .open(path)
            .map_err(|_| AutomationBindingError::Invalid)
    }
    #[cfg(not(windows))]
    {
        File::open(path).map_err(|_| AutomationBindingError::Invalid)
    }
}

fn open_path_without_write_or_delete_sharing(path: &Path) -> Result<File, AutomationBindingError> {
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        use windows_sys::Win32::Storage::FileSystem::{
            FILE_FLAG_BACKUP_SEMANTICS, FILE_SHARE_READ,
        };

        OpenOptions::new()
            .read(true)
            .share_mode(FILE_SHARE_READ)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
            .open(path)
            .map_err(|_| AutomationBindingError::Invalid)
    }
    #[cfg(not(windows))]
    {
        File::open(path).map_err(|_| AutomationBindingError::Invalid)
    }
}

#[tauri::command]
pub fn start_task(
    app: AppHandle,
    workspace_id: String,
    intent_json: String,
    state: State<'_, DesktopState>,
) -> Result<PublicTaskSnapshotV1, PublicCommandFailureV1> {
    let _gate = state.lock_gate()?;
    let (request, invocation) = prepare_task(&state, &workspace_id, &intent_json)?;
    let snapshot = state
        .tasks
        .start(request, invocation)
        .map_err(map_task_manager_error)?
        .to_public();
    let sequence = snapshot.status_history.len() as u64;
    emit_update(&app, sequence, snapshot.clone());
    let _ = app.state::<SafeLogV1>().record_task_started(&snapshot);
    spawn_task_monitor(
        app,
        state.tasks.clone(),
        snapshot.task_id.clone(),
        sequence,
        Instant::now(),
    );
    Ok(snapshot)
}

#[tauri::command]
pub fn start_export_task(
    app: AppHandle,
    workspace_id: String,
    intent_json: String,
    state: State<'_, DesktopState>,
) -> Result<PublicTaskSnapshotV1, PublicCommandFailureV1> {
    let _gate = state.lock_gate()?;
    let (request, invocation) = prepare_export_task(&state, &workspace_id, &intent_json)?;
    let snapshot = state
        .tasks
        .start_export(request, invocation)
        .map_err(map_task_manager_error)?
        .to_public();
    let sequence = snapshot.status_history.len() as u64;
    emit_update(&app, sequence, snapshot.clone());
    let _ = app.state::<SafeLogV1>().record_task_started(&snapshot);
    spawn_task_monitor(
        app,
        state.tasks.clone(),
        snapshot.task_id.clone(),
        sequence,
        Instant::now(),
    );
    Ok(snapshot)
}

#[tauri::command]
pub fn get_task(
    task_id: String,
    state: State<'_, DesktopState>,
) -> Result<PublicTaskSnapshotV1, PublicCommandFailureV1> {
    state.tasks.get_public(&task_id).ok_or_else(|| {
        PublicCommandFailureV1::new("task.not_found", "The requested task was not found.", false)
    })
}

#[tauri::command]
pub fn list_tasks(state: State<'_, DesktopState>) -> Vec<PublicTaskSnapshotV1> {
    state.tasks.list_public()
}

#[tauri::command]
pub fn open_artifact(
    artifact_id: String,
    state: State<'_, DesktopState>,
) -> Result<(), PublicCommandFailureV1> {
    let _gate = state.lock_gate()?;
    let (root, _) = state
        .workspaces
        .active_access()
        .map_err(map_workspace_error)?;
    let path = trusted_artifact_path(&state, &root, &artifact_id)?;
    open_native_target(path.as_os_str()).map_err(|_| {
        PublicCommandFailureV1::new(
            "artifact.open_failed",
            "The result file could not be opened.",
            true,
        )
    })
}

#[tauri::command]
pub fn reveal_artifact(
    artifact_id: String,
    state: State<'_, DesktopState>,
) -> Result<(), PublicCommandFailureV1> {
    let _gate = state.lock_gate()?;
    let (root, _) = state
        .workspaces
        .active_access()
        .map_err(map_workspace_error)?;
    let path = trusted_artifact_path(&state, &root, &artifact_id)?;
    reveal_native_target(&path).map_err(|_| {
        PublicCommandFailureV1::new(
            "artifact.reveal_failed",
            "The result file could not be shown in the file manager.",
            true,
        )
    })
}

#[tauri::command]
pub fn open_external_https(url: String) -> Result<(), PublicCommandFailureV1> {
    let parsed = validated_external_https(&url)?;
    open_native_target(OsStr::new(parsed.as_str())).map_err(|_| {
        PublicCommandFailureV1::new(
            "external_url.open_failed",
            "The source link could not be opened.",
            true,
        )
    })
}

fn validated_external_https(url: &str) -> Result<tauri::Url, PublicCommandFailureV1> {
    if url.len() > 2_048 || url.chars().any(char::is_control) {
        return Err(PublicCommandFailureV1::new(
            "external_url.invalid",
            "Only valid HTTPS source links can be opened.",
            false,
        ));
    }
    let parsed = tauri::Url::parse(url).map_err(|_| {
        PublicCommandFailureV1::new(
            "external_url.invalid",
            "Only valid HTTPS source links can be opened.",
            false,
        )
    })?;
    if parsed.scheme() != "https"
        || parsed.host_str().is_none()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return Err(PublicCommandFailureV1::new(
            "external_url.invalid",
            "Only valid HTTPS source links can be opened.",
            false,
        ));
    }
    Ok(parsed)
}

#[tauri::command]
pub fn open_log_location(logger: State<'_, SafeLogV1>) -> Result<(), PublicCommandFailureV1> {
    let directory = logger.trusted_directory().map_err(|_| {
        PublicCommandFailureV1::new(
            "log.location_unavailable",
            "The application log folder is unavailable or no longer trusted.",
            true,
        )
    })?;
    open_native_target(directory.as_os_str()).map_err(|_| {
        PublicCommandFailureV1::new(
            "log.open_failed",
            "The application log folder could not be opened.",
            true,
        )
    })?;
    let _ = logger.record_log_location_opened();
    Ok(())
}

#[tauri::command]
pub fn cancel_task(
    app: AppHandle,
    task_id: String,
    state: State<'_, DesktopState>,
) -> PublicCancelTaskResultV1 {
    let result = state.tasks.cancel(&task_id);
    let task = result.snapshot.map(|snapshot| snapshot.to_public());
    let public = PublicCancelTaskResultV1 {
        schema_version: CANCEL_TASK_RESULT_SCHEMA_V1.to_owned(),
        task_id: result.task_id,
        outcome: result.outcome,
        task,
    };
    let _ = app.state::<SafeLogV1>().record_task_cancel(
        &public.task_id,
        public.outcome,
        public.task.as_ref().map(|task| task.status),
    );
    public
}

fn trusted_artifact_path(
    state: &DesktopState,
    root: &Path,
    artifact_id: &str,
) -> Result<PathBuf, PublicCommandFailureV1> {
    let path = state.tasks.artifact_path(artifact_id).ok_or_else(|| {
        PublicCommandFailureV1::new(
            "artifact.not_found",
            "The requested result file is no longer available.",
            false,
        )
    })?;
    validate_workspace_target(root, &path).map_err(|_| {
        PublicCommandFailureV1::new(
            "artifact.untrusted",
            "The requested result file is outside the active workspace.",
            false,
        )
    })?;
    validate_existing_file_chain(&path).map_err(|_| {
        PublicCommandFailureV1::new(
            "artifact.unavailable",
            "The requested result file is missing or no longer trusted.",
            false,
        )
    })?;
    Ok(path)
}

#[cfg(windows)]
fn open_native_target(target: &OsStr) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::UI::{Shell::ShellExecuteW, WindowsAndMessaging::SW_SHOWNORMAL};

    let verb = OsStr::new("open")
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let target = target
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let result = unsafe {
        ShellExecuteW(
            std::ptr::null_mut(),
            verb.as_ptr(),
            target.as_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            SW_SHOWNORMAL,
        )
    };
    if result as isize <= 32 {
        Err(std::io::Error::other("ShellExecuteW failed"))
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn open_native_target(target: &OsStr) -> std::io::Result<()> {
    let program = if cfg!(target_os = "macos") {
        "open"
    } else {
        "xdg-open"
    };
    Command::new(program)
        .arg(target)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(|_| ())
}

#[cfg(windows)]
fn reveal_native_target(path: &Path) -> std::io::Result<()> {
    let mut select = OsString::from("/select,");
    select.push(path.as_os_str());
    Command::new("explorer.exe")
        .arg(select)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(|_| ())
}

#[cfg(not(windows))]
fn reveal_native_target(path: &Path) -> std::io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| std::io::Error::other("missing parent"))?;
    open_native_target(parent.as_os_str())
}

fn capabilities(state: &DesktopState) -> Result<DesktopCapabilitiesV1, PublicCommandFailureV1> {
    let workspace = state.workspaces.summary().map_err(map_workspace_error)?;
    let (root, paths) = state
        .workspaces
        .native_paths(&workspace.workspace_id)
        .map_err(map_workspace_error)?;
    let box_ready = trusted_workspace_file(&root, &paths.box_path);
    let team_ready =
        trusted_workspace_file(&root, &paths.data_dir.join("team_rank_dedup_unordered.csv"));
    let plan_ready = trusted_workspace_file(&root, &paths.banner_plan_path);
    let box_state = [(!box_ready).then_some("box-state")];
    let evidence_inputs = [
        (!box_ready).then_some("box-state"),
        (!team_ready).then_some("team-rank-dedup"),
        (!plan_ready).then_some("banner-plan"),
    ];
    let export_config_ready = load_resolved_update_config(&root).is_ok();
    let operations = vec![
        operation_capability(
            TaskOperationV1::HsrExport,
            [(!export_config_ready).then_some("update-config")],
        ),
        operation_capability(
            TaskOperationV1::ZzzExport,
            [(!export_config_ready).then_some("update-config")],
        ),
        operation_capability(TaskOperationV1::Decision, box_state),
        operation_capability(TaskOperationV1::Evidence, evidence_inputs),
        operation_capability(TaskOperationV1::Coverage, evidence_inputs),
        operation_capability(TaskOperationV1::PullValue, evidence_inputs),
        operation_capability(TaskOperationV1::ReviewPacket, evidence_inputs),
    ];
    Ok(DesktopCapabilitiesV1 {
        schema_version: DESKTOP_CAPABILITIES_SCHEMA_V1.to_owned(),
        workspace,
        workspace_selection_enabled: !state.workspaces.environment_locked(),
        operations,
        max_concurrent_tasks: 1,
        supports_cancel: true,
        task_history_persistent: true,
        task_update_event: TASK_UPDATE_EVENT_V1.to_owned(),
        task_queries_are_authoritative: true,
        abrupt_termination_supported: false,
        cross_process_recovery_supported: false,
        warnings: state.workspaces.warnings(),
    })
}

fn operation_capability(
    operation: TaskOperationV1,
    missing: impl IntoIterator<Item = Option<&'static str>>,
) -> OperationCapabilityV1 {
    let missing_inputs: Vec<_> = missing.into_iter().flatten().map(str::to_owned).collect();
    OperationCapabilityV1 {
        operation,
        enabled: missing_inputs.is_empty(),
        missing_inputs,
    }
}

fn prepare_task(
    state: &DesktopState,
    workspace_id: &str,
    intent_json: &str,
) -> Result<(miho_app::TaskRequestV1, AppInvocation), PublicCommandFailureV1> {
    let intent = parse_task_intent_v1(intent_json.as_bytes()).map_err(map_intent_failure)?;
    let (root, native_paths) = state
        .workspaces
        .native_paths(workspace_id)
        .map_err(map_workspace_error)?;
    let request = resolve_task_intent_v1(&intent, &native_paths);
    let invocation = AppInvocation::capture_in(root).map_err(|_| {
        PublicCommandFailureV1::new(
            "task.invocation_failed",
            "The task invocation could not be prepared.",
            true,
        )
    })?;
    Ok((request, invocation))
}

fn prepare_export_task(
    state: &DesktopState,
    workspace_id: &str,
    intent_json: &str,
) -> Result<(TrustedExportTaskV1, ExportInvocation), PublicCommandFailureV1> {
    let intent = parse_export_task_intent_v1(intent_json.as_bytes()).map_err(map_intent_failure)?;
    let root = state
        .workspaces
        .access(workspace_id)
        .map_err(map_workspace_error)?;
    let config = load_resolved_update_config(&root).map_err(|_| {
        PublicCommandFailureV1::new(
            "export.config_invalid",
            "The native export configuration is missing, invalid, or unsafe.",
            false,
        )
    })?;
    let invocation = ExportInvocation::capture_in(config.workspace.clone()).map_err(|_| {
        PublicCommandFailureV1::new(
            "task.invocation_failed",
            "The task invocation could not be prepared.",
            true,
        )
    })?;
    let game = match intent.task {
        ExportTaskIntentSpecV1::HsrExport(_) => Game::Hsr,
        ExportTaskIntentSpecV1::ZzzExport(_) => Game::Zzz,
    };
    let request =
        TrustedExportTaskV1::from_update_config_v1(&config, game, &invocation).map_err(|_| {
            PublicCommandFailureV1::new(
                "export.config_invalid",
                "The native export configuration is missing, invalid, or unsafe.",
                false,
            )
        })?;
    Ok((request, invocation))
}

fn load_resolved_update_config(root: &Path) -> Result<ResolvedUpdateConfigV1, ()> {
    let config_path = root.join("configs/update_v1.json");
    validate_workspace_target(root, &config_path).map_err(|_| ())?;
    load_update_config_v1(&config_path)
        .and_then(|config| config.resolve(root))
        .map_err(|_| ())
}

fn get_update_health_blocking(
    root: PathBuf,
    workspace_id: String,
) -> Result<DesktopUpdateHealthV1, PublicCommandFailureV1> {
    validate_selected_root(&root).map_err(map_workspace_error)?;
    let health = match load_update_config_digest_v1(&root) {
        Ok(config_sha256) => check_update_health_v1(&root, true, true, &config_sha256),
        Err(()) => invalid_update_health_config_v1(),
    };
    let state = FileUpdateReceiptStore.load_state(&root);
    Ok(map_desktop_update_health_v1(workspace_id, health, state))
}

fn load_update_config_digest_v1(root: &Path) -> Result<String, ()> {
    let config_path = root.join("configs/update_v1.json");
    validate_workspace_target(root, &config_path).map_err(|_| ())?;
    let loaded = load_update_config_with_digest_v1(&config_path).map_err(|_| ())?;
    loaded.config.resolve(root).map_err(|_| ())?;
    Ok(loaded.sha256)
}

fn invalid_update_health_config_v1() -> UpdateHealthV1 {
    UpdateHealthV1 {
        schema_version: UPDATE_HEALTH_SCHEMA_V1.to_owned(),
        healthy: false,
        attempt_id: None,
        checked_games: desktop_update_health_games_v1(),
        failure: Some(UpdateStepFailureV1::safe(
            "update.health_config_invalid",
            "the update health configuration is unavailable or invalid",
            false,
        )),
    }
}

fn map_desktop_update_health_v1(
    workspace_id: String,
    mut health: UpdateHealthV1,
    state: Result<UpdateStateV1, UpdateStepFailureV1>,
) -> DesktopUpdateHealthV1 {
    let state = match state {
        Ok(state) => state,
        Err(failure) if health.healthy => {
            health.healthy = false;
            health.failure = Some(failure);
            UpdateStateV1::default()
        }
        Err(_) => UpdateStateV1::default(),
    };
    let games = [Game::Hsr, Game::Zzz]
        .into_iter()
        .filter_map(|game| {
            state.games.get(&game).and_then(|game_state| {
                (is_valid_update_attempt_id_v1(&game_state.attempt_id)
                    && is_public_update_completed_at_v1(&game_state.completed_at_utc))
                .then(|| DesktopUpdateHealthGameV1 {
                    game,
                    attempt_id: game_state.attempt_id.clone(),
                    completed_at_utc: game_state.completed_at_utc.clone(),
                })
            })
        })
        .collect::<Vec<_>>();
    let checked_games = desktop_update_health_games_v1();
    let attempt_id = health
        .attempt_id
        .take()
        .filter(|value| is_valid_update_attempt_id_v1(value));
    if health.healthy
        && (attempt_id.is_none()
            || checked_games
                .iter()
                .any(|game| !games.iter().any(|entry| entry.game == *game)))
    {
        health.healthy = false;
        health.failure = Some(UpdateStepFailureV1::safe(
            "update.health_state_missing",
            "the committed update state is incomplete",
            true,
        ));
    }
    let failure_code = health.failure.as_ref().map(|failure| failure.code.clone());
    let retryable = health
        .failure
        .as_ref()
        .is_some_and(|failure| failure.retryable);
    DesktopUpdateHealthV1 {
        schema_version: DESKTOP_UPDATE_HEALTH_SCHEMA_V1.to_owned(),
        workspace_id,
        healthy: health.healthy,
        attempt_id,
        checked_games,
        games,
        failure_code,
        retryable,
    }
}

fn desktop_update_health_games_v1() -> Vec<Game> {
    vec![Game::Hsr, Game::Zzz]
}

fn is_public_update_completed_at_v1(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 27
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'.'
        || bytes[26] != b'Z'
        || bytes.iter().enumerate().any(|(index, byte)| {
            !matches!(index, 4 | 7 | 10 | 13 | 16 | 19 | 26) && !byte.is_ascii_digit()
        })
    {
        return false;
    }
    let pair = |start: usize| (bytes[start] - b'0') * 10 + (bytes[start + 1] - b'0');
    let year = bytes[..4]
        .iter()
        .fold(0_u16, |value, digit| value * 10 + u16::from(*digit - b'0'));
    let month = pair(5);
    let day = pair(8);
    let leap_year = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days_in_month = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap_year => 29,
        2 => 28,
        _ => 0,
    };
    year != 0
        && (1..=days_in_month).contains(&day)
        && pair(11) <= 23
        && pair(14) <= 59
        && pair(17) <= 59
}

fn ensure_idle(state: &DesktopState) -> Result<(), PublicCommandFailureV1> {
    if state.has_active_task() {
        Err(PublicCommandFailureV1::new(
            "workspace.busy",
            "The workspace cannot change while a task is active.",
            true,
        ))
    } else {
        Ok(())
    }
}

fn map_workspace_error(error: WorkspaceError) -> PublicCommandFailureV1 {
    match error {
        WorkspaceError::EnvironmentLocked => PublicCommandFailureV1::new(
            "workspace.environment_locked",
            "Workspace selection is locked by the native environment.",
            false,
        ),
        WorkspaceError::StaleWorkspace => PublicCommandFailureV1::new(
            "workspace.stale",
            "The workspace selection changed; refresh capabilities and retry.",
            true,
        ),
        WorkspaceError::InvalidSelection => PublicCommandFailureV1::new(
            "workspace.invalid_selection",
            "The selected folder is not a supported local workspace.",
            false,
        ),
        WorkspaceError::UntrustedPath => PublicCommandFailureV1::new(
            "workspace.untrusted_path",
            "The workspace contains an untrusted linked path.",
            false,
        ),
        WorkspaceError::Persist => PublicCommandFailureV1::new(
            "workspace.persist_failed",
            "The workspace selection could not be saved.",
            true,
        ),
        WorkspaceError::State => PublicCommandFailureV1::new(
            "desktop.state_unavailable",
            "Desktop state is unavailable.",
            true,
        ),
    }
}

fn map_automation_binding_error(error: AutomationBindingError) -> PublicCommandFailureV1 {
    match error {
        AutomationBindingError::Busy => PublicCommandFailureV1::new(
            "workspace.automation_busy",
            "Scheduled automation is changing or awaiting recovery; retry after it is repaired.",
            true,
        ),
        AutomationBindingError::Invalid => PublicCommandFailureV1::new(
            "workspace.automation_state_invalid",
            "Scheduled automation ownership is invalid or unsafe; repair it before changing workspaces.",
            false,
        ),
        AutomationBindingError::Conflict => PublicCommandFailureV1::new(
            "workspace.automation_conflict",
            "Scheduled automation is bound to another workspace; explicitly remove or rebind it before switching.",
            false,
        ),
    }
}

fn map_workspace_bootstrap_error(error: WorkspaceBootstrapError) -> PublicCommandFailureV1 {
    PublicCommandFailureV1::new(
        error.code(),
        "Workspace defaults could not be initialized; existing user files were not changed.",
        matches!(error, WorkspaceBootstrapError::WorkspaceBusy),
    )
}

fn map_intent_failure(failure: TaskFailureV1) -> PublicCommandFailureV1 {
    let message = match failure.code.as_str() {
        "request.unsupported_schema" => "The task intent schema is not supported.",
        _ => "The task intent is invalid.",
    };
    PublicCommandFailureV1::new(&failure.code, message, failure.retryable)
}

fn map_task_manager_error(error: TaskManagerError) -> PublicCommandFailureV1 {
    match error {
        TaskManagerError::Busy { .. } => {
            PublicCommandFailureV1::new("task.busy", "Another task is already active.", true)
        }
        TaskManagerError::SpawnFailed { .. } => PublicCommandFailureV1::new(
            "task.spawn_failed",
            "The background task could not be started.",
            true,
        ),
    }
}

fn emit_update(app: &AppHandle, sequence: u64, task: PublicTaskSnapshotV1) {
    let _ = app.emit_to(
        "main",
        TASK_UPDATE_EVENT_V1,
        DesktopTaskUpdateV1 {
            schema_version: TASK_UPDATE_SCHEMA_V1.to_owned(),
            sequence,
            task,
        },
    );
}

fn pending_updates(
    tasks: &TaskManager,
    task_id: &str,
    after_sequence: u64,
) -> Option<Vec<PublicTaskUpdateV1>> {
    tasks.public_updates_since(task_id, after_sequence)
}

fn spawn_task_monitor(
    app: AppHandle,
    tasks: TaskManager,
    task_id: String,
    mut last_sequence: u64,
    started_at: Instant,
) {
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_millis(50)).await;
            let Some(updates) = pending_updates(&tasks, &task_id, last_sequence) else {
                return;
            };
            for update in updates {
                last_sequence = update.sequence;
                let terminal = update.task.status.is_terminal();
                let _ = app
                    .state::<SafeLogV1>()
                    .record_task_status(&update.task, started_at.elapsed());
                emit_update(&app, update.sequence, update.task);
                if terminal {
                    return;
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use miho_app::{
        DecisionTaskV1, ExecutionObserver, ExportIntentV1, ExportSourceV1, ExportTaskIntentV1,
        TaskExecutor, TaskIntentSpecV1, TaskIntentV1, TaskReceiptV1, TaskRequestV1, TaskSpecV1,
        TaskStatusV1, UpdateStateGameV1, WorkspaceLayout, TASK_RECEIPT_SCHEMA_V1,
    };
    use std::{
        fs,
        path::PathBuf,
        sync::{
            atomic::{AtomicU64, Ordering},
            Arc,
        },
        time::{Duration, Instant},
    };

    static NEXT_ID: AtomicU64 = AtomicU64::new(0);

    struct ImmediateSuccess;

    struct FixedOutputSuccess {
        output: PathBuf,
    }

    const TEST_OWNER_INSTANCE_ID: &str = "11111111-1111-4111-8111-111111111111";
    const TEST_OWNER_EPOCH: &str = "33333333-3333-4333-8333-333333333333";
    const TEST_INSTALL_ID: &str = "22222222-2222-4222-8222-222222222222";
    const TEST_OWNER_SID: &str = "S-1-5-21-1000";

    struct FixedProbeRunner {
        receipt: DesktopAutomationProbeReceiptV1,
    }

    impl AutomationProbeRunnerV1 for FixedProbeRunner {
        fn probe(
            &self,
            _request: &AutomationProbeRequestV1<'_>,
        ) -> Result<AutomationProbeRunV1, AutomationBindingError> {
            Ok(AutomationProbeRunV1 {
                receipt: self.receipt.clone(),
                pinned_handles: Vec::new(),
            })
        }
    }

    impl TaskExecutor for ImmediateSuccess {
        fn execute(
            &self,
            request: &TaskRequestV1,
            _invocation: &AppInvocation,
            observer: &dyn ExecutionObserver,
        ) -> anyhow::Result<TaskReceiptV1> {
            observer.before_commit()?;
            Ok(TaskReceiptV1 {
                schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
                operation: request.operation(),
                method_version: "test".to_owned(),
                output_schema: "test".to_owned(),
                local_datetime: "2026-07-13T00:00:00".to_owned(),
                outputs: Vec::new(),
                notices: Vec::new(),
                freshness: None,
            })
        }
    }

    impl TaskExecutor for FixedOutputSuccess {
        fn execute(
            &self,
            request: &TaskRequestV1,
            _invocation: &AppInvocation,
            observer: &dyn ExecutionObserver,
        ) -> anyhow::Result<TaskReceiptV1> {
            observer.before_commit()?;
            Ok(TaskReceiptV1 {
                schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
                operation: request.operation(),
                method_version: "artifact-test".to_owned(),
                output_schema: "test".to_owned(),
                local_datetime: "2026-07-23T00:00:00".to_owned(),
                outputs: vec![self.output.clone()],
                notices: Vec::new(),
                freshness: None,
            })
        }
    }

    fn state(label: &str) -> (PathBuf, DesktopState, String) {
        let root = std::env::temp_dir().join(format!(
            "miho-desktop-tasks-{label}-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let workspaces = WorkspaceRegistry::initialize(
            root.clone(),
            root.join("config"),
            None,
            Some(root.clone()),
        );
        let workspace_id = workspaces.summary().unwrap().workspace_id;
        (
            root,
            DesktopState::new(workspaces, TaskManager::new()),
            workspace_id,
        )
    }

    #[test]
    fn desktop_update_health_mapping_is_pathless_and_orders_games() {
        let mut update_state = UpdateStateV1::default();
        update_state.games.insert(
            Game::Zzz,
            UpdateStateGameV1 {
                attempt_id: "20260726T020000000000Z-zzzzzzzzzzzz".to_owned(),
                completed_at_utc: "2026-07-26T02:00:00.000000Z".to_owned(),
                config_sha256: "b".repeat(64),
                artifacts: Vec::new(),
            },
        );
        update_state.games.insert(
            Game::Hsr,
            UpdateStateGameV1 {
                attempt_id: "20260726T010000000000Z-hhhhhhhhhhhh".to_owned(),
                completed_at_utc: "2026-07-26T01:00:00.000000Z".to_owned(),
                config_sha256: "a".repeat(64),
                artifacts: Vec::new(),
            },
        );
        let mapped = map_desktop_update_health_v1(
            "workspace-opaque".to_owned(),
            UpdateHealthV1 {
                schema_version: UPDATE_HEALTH_SCHEMA_V1.to_owned(),
                healthy: false,
                attempt_id: Some("20260726T030000000000Z-latestlatest".to_owned()),
                checked_games: vec![Game::Hsr, Game::Zzz],
                failure: Some(UpdateStepFailureV1::safe(
                    "workspace.write_busy",
                    r#"C:\Users\private\workspace is busy"#,
                    true,
                )),
            },
            Ok(update_state),
        );

        assert_eq!(
            mapped
                .games
                .iter()
                .map(|game| game.game)
                .collect::<Vec<_>>(),
            vec![Game::Hsr, Game::Zzz]
        );
        let serialized = serde_json::to_value(&mapped).unwrap();
        assert_eq!(
            serialized["schema_version"],
            DESKTOP_UPDATE_HEALTH_SCHEMA_V1
        );
        assert_eq!(serialized["failure_code"], "workspace.write_busy");
        assert_eq!(serialized["retryable"], true);
        assert!(serialized.get("message").is_none());
        assert!(!serialized.to_string().contains("private"));
        assert!(!serialized.to_string().contains("workspace is busy"));
    }

    #[test]
    fn desktop_update_health_timestamp_validates_the_gregorian_calendar() {
        for valid in [
            "2000-02-29T23:59:59.999999Z",
            "2024-02-29T00:00:00.000000Z",
            "2026-04-30T12:34:56.123456Z",
            "9999-12-31T23:59:59.999999Z",
        ] {
            assert!(is_public_update_completed_at_v1(valid), "{valid}");
        }
        for invalid in [
            "0000-01-01T00:00:00.000000Z",
            "1900-02-29T00:00:00.000000Z",
            "2023-02-29T00:00:00.000000Z",
            "2026-00-01T00:00:00.000000Z",
            "2026-01-00T00:00:00.000000Z",
            "2026-02-30T00:00:00.000000Z",
            "2026-04-31T00:00:00.000000Z",
            "2026-06-31T00:00:00.000000Z",
            "2026-09-31T00:00:00.000000Z",
            "2026-11-31T00:00:00.000000Z",
            "2026-13-01T00:00:00.000000Z",
        ] {
            assert!(!is_public_update_completed_at_v1(invalid), "{invalid}");
        }
    }

    #[test]
    fn desktop_update_health_invalid_config_maps_to_expected_unhealthy_dto() {
        let mapped = map_desktop_update_health_v1(
            "workspace-opaque".to_owned(),
            invalid_update_health_config_v1(),
            Ok(UpdateStateV1::default()),
        );
        let serialized = serde_json::to_value(&mapped).unwrap();

        assert_eq!(serialized["healthy"], false);
        assert_eq!(
            serialized["checked_games"],
            serde_json::json!(["hsr", "zzz"])
        );
        assert_eq!(serialized["games"], serde_json::json!([]));
        assert_eq!(serialized["failure_code"], "update.health_config_invalid");
        assert_eq!(serialized["retryable"], false);
        assert!(serialized.get("attempt_id").is_none());
    }

    #[test]
    fn desktop_update_health_mapping_omits_untrusted_state_text() {
        let mut update_state = UpdateStateV1::default();
        update_state.games.insert(
            Game::Hsr,
            UpdateStateGameV1 {
                attempt_id: r#"C:\Users\private\attempt"#.to_owned(),
                completed_at_utc: r#"C:\Users\private\timestamp"#.to_owned(),
                config_sha256: "a".repeat(64),
                artifacts: Vec::new(),
            },
        );
        let mapped = map_desktop_update_health_v1(
            "workspace-opaque".to_owned(),
            UpdateHealthV1 {
                schema_version: UPDATE_HEALTH_SCHEMA_V1.to_owned(),
                healthy: false,
                attempt_id: None,
                checked_games: vec![Game::Hsr, Game::Zzz],
                failure: Some(UpdateStepFailureV1::safe(
                    "workspace.write_busy",
                    r#"C:\Users\private\workspace"#,
                    true,
                )),
            },
            Ok(update_state),
        );
        let serialized = serde_json::to_string(&mapped).unwrap();

        assert!(mapped.games.is_empty());
        assert!(!serialized.contains("private"));
        assert!(!serialized.contains("Users"));
        assert!(!serialized.contains("message"));
    }

    #[test]
    fn desktop_update_health_blocking_maps_missing_config_to_data() {
        let (root, _, workspace_id) = state("update-health-missing-config");

        let health = get_update_health_blocking(root.clone(), workspace_id.clone()).unwrap();

        assert_eq!(health.workspace_id, workspace_id);
        assert!(!health.healthy);
        assert_eq!(
            health.failure_code.as_deref(),
            Some("update.health_config_invalid")
        );
        assert!(!health.retryable);
        assert_eq!(health.checked_games, vec![Game::Hsr, Game::Zzz]);
        assert!(health.games.is_empty());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn desktop_update_health_blocking_uses_valid_config_digest() {
        let (root, _, workspace_id) = state("update-health-valid-config");
        fs::create_dir_all(root.join("configs")).unwrap();
        fs::write(
            root.join("configs/update_v1.json"),
            include_bytes!("../../../../configs/update_v1.json"),
        )
        .unwrap();

        let health = get_update_health_blocking(root.clone(), workspace_id).unwrap();

        assert!(!health.healthy);
        assert_eq!(
            health.failure_code.as_deref(),
            Some("update.health_receipt_missing")
        );
        assert!(health.retryable);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn desktop_update_health_blocking_rejects_stale_workspace_access() {
        let (root, _, workspace_id) = state("update-health-stale-root");
        fs::remove_dir_all(&root).unwrap();

        let error = get_update_health_blocking(root, workspace_id).unwrap_err();

        assert_eq!(error.code, "workspace.invalid_selection");
        assert!(!error.retryable);
    }

    fn write_automation_manifest(
        automation_root: &std::path::Path,
        workspace: &std::path::Path,
    ) -> std::path::PathBuf {
        let generations = automation_root.join("generations");
        let generation = generations.join("sha256-test-generation");
        let executable = generation.join("miho.exe");
        let config = workspace.join("configs/update_v1.json");
        fs::create_dir_all(&generation).unwrap();
        fs::create_dir_all(config.parent().unwrap()).unwrap();
        fs::write(automation_root.join(AUTOMATION_LOCK_V1), b"").unwrap();
        fs::write(&executable, b"test executable").unwrap();
        fs::write(&config, b"{}\n").unwrap();
        let task_name = format!(
            "MihoEndgameDailyUpdate-{}",
            &sha256_hex(TEST_OWNER_SID.as_bytes())[..16]
        );
        miho_core::config::save_json(
            &automation_root.join(AUTOMATION_AUTHORITY_V1),
            &serde_json::json!({
                "schema": AUTOMATION_AUTHORITY_SCHEMA_V1,
                "owner_kind": "installed",
                "owner_instance_id": TEST_OWNER_INSTANCE_ID,
                "owner_epoch": TEST_OWNER_EPOCH,
                "owner_sid": TEST_OWNER_SID,
                "task_name": task_name,
                "task_path": "\\",
                "automation_root": automation_root
            }),
        )
        .unwrap();
        let manifest_path = automation_root.join(AUTOMATION_OWNER_MANIFEST_V1);
        miho_core::config::save_json(
            &manifest_path,
            &serde_json::json!({
                "schema": AUTOMATION_OWNER_SCHEMA_V1,
                "owner_sid": TEST_OWNER_SID,
                "owner_kind": "installed",
                "owner_instance_id": TEST_OWNER_INSTANCE_ID,
                "owner_epoch": TEST_OWNER_EPOCH,
                "install_id": TEST_INSTALL_ID,
                "task_name": task_name,
                "task_path": "\\",
                "canonical_workspace": workspace,
                "canonical_config": config,
                "config_relative": "configs/update_v1.json",
                "generation": "sha256-test-generation",
                "version": "0.1.0",
                "generation_path": generation,
                "exe_path": executable,
                "exe_sha256": sha256_hex(b"test executable"),
                "action_fingerprint": sha256_hex(b"exact mock action fingerprint v1"),
                "task_xml_sha256": sha256_hex(b"exact mock task xml v1"),
                "task_sddl_sha256": sha256_hex(b"exact mock task sddl v1"),
                "source": format!("com.miho.endgame/automation-v1/installed/{TEST_OWNER_INSTANCE_ID}/{TEST_OWNER_EPOCH}/{TEST_INSTALL_ID}"),
                "schedule_at": "09:30"
            }),
        )
        .unwrap();
        manifest_path
    }

    fn test_expected_owner() -> AutomationExpectedOwnerV1 {
        AutomationExpectedOwnerV1::new("installed", TEST_OWNER_INSTANCE_ID.to_owned()).unwrap()
    }

    fn active_probe_receipt(automation_root: &Path) -> DesktopAutomationProbeReceiptV1 {
        let manifest_bytes = fs::read(automation_root.join(AUTOMATION_OWNER_MANIFEST_V1)).unwrap();
        let manifest: AutomationOwnerManifestV1 = serde_json::from_slice(&manifest_bytes).unwrap();
        let authority_bytes = fs::read(automation_root.join(AUTOMATION_AUTHORITY_V1)).unwrap();
        DesktopAutomationProbeReceiptV1 {
            schema: DESKTOP_AUTOMATION_PROBE_SCHEMA_V1.to_owned(),
            status: "active".to_owned(),
            manifest_sha256: sha256_hex(&manifest_bytes),
            exe_sha256: manifest.exe_sha256,
            authority_sha256: sha256_hex(&authority_bytes),
            unbound_sha256: String::new(),
            task_xml_sha256: manifest.task_xml_sha256,
            task_sddl_sha256: manifest.task_sddl_sha256,
        }
    }

    fn write_clean_unbound_automation(automation_root: &Path) -> DesktopAutomationProbeReceiptV1 {
        fs::create_dir_all(automation_root.join("generations")).unwrap();
        fs::write(automation_root.join(AUTOMATION_LOCK_V1), b"").unwrap();
        let task_name = format!(
            "MihoEndgameDailyUpdate-{}",
            &sha256_hex(TEST_OWNER_SID.as_bytes())[..16]
        );
        let common = serde_json::json!({
            "owner_kind": "installed",
            "owner_instance_id": TEST_OWNER_INSTANCE_ID,
            "owner_epoch": TEST_OWNER_EPOCH,
            "owner_sid": TEST_OWNER_SID,
            "task_name": task_name,
            "task_path": "\\",
            "automation_root": automation_root
        });
        let mut authority = common.as_object().unwrap().clone();
        authority.insert(
            "schema".to_owned(),
            serde_json::json!(AUTOMATION_AUTHORITY_SCHEMA_V1),
        );
        let mut unbound = common.as_object().unwrap().clone();
        unbound.insert(
            "schema".to_owned(),
            serde_json::json!(AUTOMATION_UNBOUND_SCHEMA_V1),
        );
        unbound.insert("prior_install_id".to_owned(), serde_json::json!(""));
        unbound.insert("prior_manifest_sha256".to_owned(), serde_json::json!(""));
        miho_core::config::save_json(&automation_root.join(AUTOMATION_AUTHORITY_V1), &authority)
            .unwrap();
        miho_core::config::save_json(&automation_root.join(AUTOMATION_UNBOUND_V1), &unbound)
            .unwrap();
        let authority_bytes = fs::read(automation_root.join(AUTOMATION_AUTHORITY_V1)).unwrap();
        let unbound_bytes = fs::read(automation_root.join(AUTOMATION_UNBOUND_V1)).unwrap();
        DesktopAutomationProbeReceiptV1 {
            schema: DESKTOP_AUTOMATION_PROBE_SCHEMA_V1.to_owned(),
            status: "clean-unbound".to_owned(),
            manifest_sha256: String::new(),
            exe_sha256: String::new(),
            authority_sha256: sha256_hex(&authority_bytes),
            unbound_sha256: sha256_hex(&unbound_bytes),
            task_xml_sha256: String::new(),
            task_sddl_sha256: String::new(),
        }
    }

    fn status_probe_receipt(status: &str) -> DesktopAutomationProbeReceiptV1 {
        DesktopAutomationProbeReceiptV1 {
            schema: DESKTOP_AUTOMATION_PROBE_SCHEMA_V1.to_owned(),
            status: status.to_owned(),
            manifest_sha256: String::new(),
            exe_sha256: String::new(),
            authority_sha256: String::new(),
            unbound_sha256: String::new(),
            task_xml_sha256: String::new(),
            task_sddl_sha256: String::new(),
        }
    }

    fn with_test_automation(
        state: DesktopState,
        automation_root: PathBuf,
        receipt: DesktopAutomationProbeReceiptV1,
    ) -> DesktopState {
        state
            .with_automation_root(automation_root)
            .with_automation_owner(test_expected_owner())
            .with_automation_probe(Arc::new(FixedProbeRunner { receipt }))
    }

    #[test]
    fn capabilities_are_pathless_and_truthful_about_recovery() {
        let (root, state, _) = state("capabilities-CANARY_SECRET");
        let value = serde_json::to_string(&capabilities(&state).unwrap()).unwrap();
        assert!(!value.contains("CANARY_SECRET"));
        assert!(!value.contains("root"));
        assert!(value.contains("\"abrupt_termination_supported\":false"));
        assert!(value.contains("\"cross_process_recovery_supported\":false"));
        assert!(value.contains("\"max_concurrent_tasks\":1"));
        assert!(value.contains("\"supports_cancel\":true"));
        assert!(value.contains("\"task_history_persistent\":true"));
        assert!(value.contains("\"enabled\":false"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn external_links_accept_only_bounded_https_without_credentials() {
        let accepted = validated_external_https("https://example.com/source?q=1#section").unwrap();
        assert_eq!(accepted.scheme(), "https");
        assert_eq!(accepted.host_str(), Some("example.com"));

        for invalid in [
            "http://example.com",
            "javascript:alert(1)",
            "https://user@example.com/source",
            "https://user:password@example.com/source",
            "https://",
            "https://[::1",
            "https://example.com/\nsource",
        ] {
            let failure = validated_external_https(invalid).unwrap_err();
            assert_eq!(failure.code, "external_url.invalid", "{invalid}");
            assert!(!failure.retryable, "{invalid}");
        }
        let oversized = format!("https://example.com/{}", "a".repeat(2_048));
        assert_eq!(
            validated_external_https(&oversized).unwrap_err().code,
            "external_url.invalid"
        );
    }

    #[test]
    fn artifact_ids_are_bound_to_existing_files_in_the_active_workspace() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-artifact-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let other_workspace = base.join("other");
        fs::create_dir_all(&workspace).unwrap();
        fs::create_dir_all(&other_workspace).unwrap();
        let output = workspace.join("report.md");
        fs::write(&output, "report").unwrap();
        let manager = TaskManager::with_executor(Arc::new(FixedOutputSuccess {
            output: output.clone(),
        }));
        let request = TaskRequestV1::new(
            WorkspaceLayout {
                data_dir: workspace.join("data"),
                box_path: workspace.join("box.json"),
            },
            TaskSpecV1::Decision(DecisionTaskV1 {
                method: "legacy-v0".to_owned(),
                rules_path: workspace.join("rules.yaml"),
            }),
        );
        let queued = manager
            .start(
                request,
                AppInvocation::capture_in(workspace.clone()).unwrap(),
            )
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        while !manager.get(&queued.task_id).unwrap().status.is_terminal() {
            assert!(Instant::now() < deadline, "artifact task did not finish");
            std::thread::yield_now();
        }
        let artifact_id = manager.get_public(&queued.task_id).unwrap().artifacts[0]
            .artifact_id
            .clone();
        let workspaces =
            WorkspaceRegistry::initialize(workspace.clone(), base.join("config"), None, None);
        let state = DesktopState::new(workspaces, manager);

        assert_eq!(
            trusted_artifact_path(&state, &workspace, &artifact_id).unwrap(),
            output
        );
        fs::remove_file(&output).unwrap();
        assert_eq!(
            trusted_artifact_path(&state, &workspace, &artifact_id)
                .unwrap_err()
                .code,
            "artifact.unavailable"
        );
        fs::write(&output, "report").unwrap();
        state.workspaces.select(other_workspace.clone()).unwrap();
        assert_eq!(
            trusted_artifact_path(&state, &other_workspace, &artifact_id)
                .unwrap_err()
                .code,
            "artifact.untrusted"
        );

        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn artifact_reparse_targets_are_rejected() {
        use std::os::windows::fs::symlink_file;

        let base = std::env::temp_dir().join(format!(
            "miho-desktop-artifact-link-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        fs::create_dir_all(&workspace).unwrap();
        let external = base.join("external.md");
        let linked = workspace.join("report.md");
        fs::write(&external, "outside").unwrap();
        if symlink_file(&external, &linked).is_err() {
            fs::remove_dir_all(base).unwrap();
            return;
        }
        let manager = TaskManager::with_executor(Arc::new(FixedOutputSuccess {
            output: linked.clone(),
        }));
        let request = TaskRequestV1::new(
            WorkspaceLayout {
                data_dir: workspace.join("data"),
                box_path: workspace.join("box.json"),
            },
            TaskSpecV1::Decision(DecisionTaskV1 {
                method: "legacy-v0".to_owned(),
                rules_path: workspace.join("rules.yaml"),
            }),
        );
        let queued = manager
            .start(
                request,
                AppInvocation::capture_in(workspace.clone()).unwrap(),
            )
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        while !manager.get(&queued.task_id).unwrap().status.is_terminal() {
            assert!(Instant::now() < deadline, "artifact task did not finish");
            std::thread::yield_now();
        }
        let artifact_id = manager.get_public(&queued.task_id).unwrap().artifacts[0]
            .artifact_id
            .clone();
        let workspaces =
            WorkspaceRegistry::initialize(workspace.clone(), base.join("config"), None, None);
        let state = DesktopState::new(workspaces, manager);
        let failure = trusted_artifact_path(&state, &workspace, &artifact_id).unwrap_err();
        assert!(matches!(
            failure.code.as_str(),
            "artifact.untrusted" | "artifact.unavailable"
        ));
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn capabilities_follow_required_inputs_not_optional_files() {
        let (root, state, _) = state("capability-inputs");
        fs::create_dir_all(root.join(".miho")).unwrap();
        fs::create_dir_all(root.join("out_zzz")).unwrap();
        fs::create_dir_all(root.join("configs")).unwrap();
        fs::write(root.join(".miho/zzz_box_state.json"), b"{}").unwrap();
        fs::write(
            root.join("out_zzz/team_rank_dedup_unordered.csv"),
            b"mode,rank\n",
        )
        .unwrap();
        fs::write(root.join("configs/zzz_banner_plan.json"), b"{}").unwrap();
        fs::write(
            root.join("configs/update_v1.json"),
            include_bytes!("../../../../configs/update_v1.json"),
        )
        .unwrap();
        let capabilities = capabilities(&state).unwrap();
        assert!(capabilities
            .operations
            .iter()
            .all(|operation| operation.enabled && operation.missing_inputs.is_empty()));
        assert!(!root.join("configs/zzz_decision_rules.yaml").exists());
        assert!(!root.join("configs/zzz_mechanism_notes").exists());
        assert!(!root.join("configs/zzz_decision_baseline.json").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn selecting_an_empty_workspace_bootstraps_defaults_before_commit() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-bootstrap-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&base);
        let app_data = base.join("app-data");
        let selected = base.join("中文 selected workspace");
        fs::create_dir_all(&app_data).unwrap();
        fs::create_dir_all(&selected).unwrap();
        let workspaces = WorkspaceRegistry::initialize(app_data, base.join("config"), None, None);
        let state = DesktopState::new(workspaces, TaskManager::new());

        let summary = commit_workspace_selection(&state, selected.clone()).unwrap();

        assert_eq!(state.workspaces.summary().unwrap(), summary);
        assert!(selected.join("configs/update_v1.json").is_file());
        assert!(selected.join("configs/zzz_banner_plan.json").is_file());
        assert!(selected.join(".miho/zzz_box_state.json").is_file());
        let evidence = capabilities(&state)
            .unwrap()
            .operations
            .into_iter()
            .find(|operation| operation.operation == TaskOperationV1::Evidence)
            .unwrap();
        assert_eq!(evidence.missing_inputs, ["team-rank-dedup"]);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn workspace_selection_rejects_a_valid_automation_binding_to_another_workspace() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-automation-conflict-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let bound = base.join("bound-workspace");
        let selected = base.join("selected-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &bound, &selected] {
            fs::create_dir_all(directory).unwrap();
        }
        write_automation_manifest(&automation_root, &bound);
        let receipt = active_probe_receipt(&automation_root);
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data.clone(), app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let error = commit_workspace_selection(&state, selected.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_conflict");
        assert!(!selected.join("configs").exists());
        assert!(!selected.join(".miho").exists());
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        assert_eq!(state.workspaces.active_root().unwrap(), app_data);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn workspace_selection_accepts_the_exact_automation_workspace_under_the_same_lease() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-automation-match-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let selected = base.join("selected-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &selected] {
            fs::create_dir_all(directory).unwrap();
        }
        write_automation_manifest(&automation_root, &selected);
        let receipt = active_probe_receipt(&automation_root);
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let summary = commit_workspace_selection(&state, selected.clone()).unwrap();

        assert_eq!(state.workspaces.summary().unwrap(), summary);
        assert_eq!(state.workspaces.active_root().unwrap(), selected);
        assert!(app_config.join("desktop-settings-v1.json").is_file());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn active_automation_rejects_an_unrecorded_generation_side_load_file() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-generation-extra-file-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        write_automation_manifest(&automation_root, &workspace);
        let receipt = active_probe_receipt(&automation_root);
        fs::write(
            automation_root.join("generations/sha256-test-generation/version.dll"),
            b"unrecorded side-load payload",
        )
        .unwrap();
        let owner = test_expected_owner();
        let probe = FixedProbeRunner { receipt };

        let error = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&owner),
            Some(&probe),
        )
        .err()
        .unwrap();

        assert_eq!(error, AutomationBindingError::Invalid);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn active_automation_accepts_a_preserved_private_staging_sibling() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-generation-private-staging-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        write_automation_manifest(&automation_root, &workspace);
        let receipt = active_probe_receipt(&automation_root);
        let staging = automation_root.join("generations/.staging-0123456789abcdef0123456789abcdef");
        fs::create_dir_all(&staging).unwrap();
        fs::write(staging.join("unknown-sentinel.txt"), b"preserve").unwrap();
        let owner = test_expected_owner();
        let probe = FixedProbeRunner { receipt };

        let guard = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&owner),
            Some(&probe),
        )
        .unwrap()
        .unwrap();

        drop(guard);
        assert!(staging.join("unknown-sentinel.txt").is_file());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn active_automation_final_enumeration_rejects_a_late_side_load_file() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-generation-late-extra-file-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        write_automation_manifest(&automation_root, &workspace);
        let receipt = active_probe_receipt(&automation_root);
        let owner = test_expected_owner();
        let late_file = automation_root.join("generations/sha256-test-generation/version.dll");
        let mut handles = Vec::new();

        let error = validate_active_automation_evidence_with_final_hook_v1(
            &receipt,
            &automation_root,
            &workspace,
            &owner,
            &mut handles,
            || fs::write(&late_file, b"late side-load payload").unwrap(),
        )
        .unwrap_err();

        assert_eq!(error, AutomationBindingError::Invalid);
        drop(handles);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn workspace_selection_fails_closed_for_old_or_unknown_automation_manifests() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-automation-invalid-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let selected = base.join("selected-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &selected] {
            fs::create_dir_all(directory).unwrap();
        }
        let manifest_path = write_automation_manifest(&automation_root, &selected);
        let receipt = active_probe_receipt(&automation_root);
        let mut manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        manifest
            .as_object_mut()
            .unwrap()
            .remove("owner_instance_id");
        manifest["unexpected"] = serde_json::json!(true);
        miho_core::config::save_json(&manifest_path, &manifest).unwrap();
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let error = commit_workspace_selection(&state, selected.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_state_invalid");
        assert!(!selected.join(".miho").exists());
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn workspace_selection_rejects_a_malformed_automation_transaction_journal_as_invalid() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-automation-journal-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let selected = base.join("selected-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &selected, &automation_root] {
            fs::create_dir_all(directory).unwrap();
        }
        fs::write(automation_root.join(AUTOMATION_LOCK_V1), b"").unwrap();
        fs::write(automation_root.join(AUTOMATION_JOURNAL_V1), b"{}\n").unwrap();
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            status_probe_receipt("invalid"),
        );

        let error = commit_workspace_selection(&state, selected.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_state_invalid");
        assert!(!selected.join("configs").exists());
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn missing_automation_root_is_a_read_only_probe() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-missing-root-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();

        let guard =
            acquire_automation_workspace_binding(Some(&automation_root), &workspace, None, None)
                .unwrap();

        assert!(guard.is_none());
        assert!(!base.join("local-data").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn missing_automation_root_with_release_intent_is_busy() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-release-intent-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(automation_root.parent().unwrap()).unwrap();
        fs::create_dir_all(&workspace).unwrap();
        fs::write(
            automation_release_intent_path_v1(&automation_root).unwrap(),
            b"release intent evidence",
        )
        .unwrap();
        let probe = FixedProbeRunner {
            receipt: status_probe_receipt("busy"),
        };

        let error = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&test_expected_owner()),
            Some(&probe),
        )
        .err()
        .unwrap();

        assert_eq!(error, AutomationBindingError::Busy);
        assert!(!automation_root.exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn partial_claim_root_without_switch_lock_is_busy() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-partial-claim-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&automation_root).unwrap();
        fs::create_dir_all(&workspace).unwrap();
        let probe = FixedProbeRunner {
            receipt: status_probe_receipt("busy"),
        };

        let error = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&test_expected_owner()),
            Some(&probe),
        )
        .err()
        .unwrap();

        assert_eq!(error, AutomationBindingError::Busy);
        assert!(!automation_root.join(AUTOMATION_LOCK_V1).exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn clean_unbound_owner_accepts_an_empty_pinned_generations_directory() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-clean-unbound-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        let receipt = write_clean_unbound_automation(&automation_root);
        let owner = test_expected_owner();
        let probe = FixedProbeRunner { receipt };

        let guard = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&owner),
            Some(&probe),
        )
        .unwrap()
        .unwrap();

        drop(guard);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn clean_unbound_startup_guard_release_allows_same_session_workspace_selection() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-clean-unbound-reselect-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let initial = base.join("initial-workspace");
        let selected = base.join("selected-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &initial, &selected] {
            fs::create_dir_all(directory).unwrap();
        }
        let receipt = write_clean_unbound_automation(&automation_root);
        let owner = test_expected_owner();
        let probe = FixedProbeRunner {
            receipt: receipt.clone(),
        };
        let startup_guard = acquire_automation_workspace_binding(
            Some(&automation_root),
            &initial,
            Some(&owner),
            Some(&probe),
        )
        .unwrap()
        .unwrap();
        drop(startup_guard);
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config, Some(initial), None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let summary = commit_workspace_selection(&state, selected.clone()).unwrap();

        assert_eq!(state.workspaces.summary().unwrap(), summary);
        assert_eq!(state.workspaces.active_root().unwrap(), selected);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn clean_unbound_owner_rejects_a_nonempty_generations_directory() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-clean-unbound-nonempty-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        let receipt = write_clean_unbound_automation(&automation_root);
        fs::write(automation_root.join("generations/orphan"), b"orphan").unwrap();
        let owner = test_expected_owner();
        let probe = FixedProbeRunner { receipt };

        let error = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&owner),
            Some(&probe),
        )
        .err()
        .unwrap();

        assert_eq!(error, AutomationBindingError::Invalid);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn clean_unbound_final_enumeration_rejects_a_late_orphan() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-clean-unbound-late-orphan-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        let receipt = write_clean_unbound_automation(&automation_root);
        let owner = test_expected_owner();
        let orphan = automation_root.join("generations/orphan");
        let mut handles = Vec::new();

        let error = validate_clean_unbound_automation_evidence_with_final_hook_v1(
            &receipt,
            &automation_root,
            &owner,
            &mut handles,
            || fs::write(&orphan, b"late orphan").unwrap(),
        )
        .unwrap_err();

        assert_eq!(error, AutomationBindingError::Invalid);
        drop(handles);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn existing_automation_root_requires_an_explicit_product_owner_identity() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-owner-required-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        let receipt = write_clean_unbound_automation(&automation_root);
        let probe = FixedProbeRunner { receipt };

        let error = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            None,
            Some(&probe),
        )
        .err()
        .unwrap();

        assert_eq!(error, AutomationBindingError::Invalid);
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn installed_coordinator_linearizes_absent_root_without_creating_it() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-coordinator-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let local_data = base.join("local-data");
        let automation_root = local_data.join("com.miho.endgame.automation");
        fs::create_dir_all(&local_data).unwrap();

        let coordinator = acquire_automation_coordinator(&automation_root).unwrap();

        assert!(!automation_root.exists());
        assert!(local_data
            .join("com.miho.endgame.automation.coordinator-v1.lock")
            .is_file());
        assert_eq!(
            acquire_automation_coordinator(&automation_root)
                .err()
                .unwrap(),
            AutomationBindingError::Busy
        );
        drop(coordinator);
        drop(acquire_automation_coordinator(&automation_root).unwrap());
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn packaged_powershell_probe_round_trips_an_absent_pathless_state() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-powershell-probe-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let local_data = base.join("local-data");
        let workspace = base.join("workspace");
        let automation_root = local_data.join("com.miho.endgame.automation");
        fs::create_dir_all(&local_data).unwrap();
        fs::create_dir_all(&workspace).unwrap();
        let coordinator = acquire_automation_coordinator(&automation_root).unwrap();
        let script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../scripts/task_scheduler_v1.ps1");
        let runner = PowerShellAutomationProbeRunnerV1 {
            script_path: script,
        };
        let owner = test_expected_owner();

        let run = runner
            .probe(&AutomationProbeRequestV1 {
                automation_root: &automation_root,
                selected_workspace: &workspace,
                expected_owner: Some(&owner),
                caller_holds_switch_lease: false,
            })
            .unwrap();

        assert_eq!(run.receipt, status_probe_receipt("absent"));
        assert!(!automation_root.exists());
        assert!(!automation_claim_intent_path_v1(&automation_root)
            .unwrap()
            .exists());
        drop(run);
        drop(coordinator);
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn powershell_probe_rejects_a_runtime_script_that_differs_from_embedded_bytes() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-powershell-probe-drift-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let local_data = base.join("local-data");
        let workspace = base.join("workspace");
        let automation_root = local_data.join("com.miho.endgame.automation");
        fs::create_dir_all(&local_data).unwrap();
        fs::create_dir_all(&workspace).unwrap();
        let coordinator = acquire_automation_coordinator(&automation_root).unwrap();
        let script = base.join("task_scheduler_v1.ps1");
        fs::write(&script, b"# not the embedded scheduler script\n").unwrap();
        let runner = PowerShellAutomationProbeRunnerV1 {
            script_path: script,
        };
        let owner = test_expected_owner();

        let error = runner
            .probe(&AutomationProbeRequestV1 {
                automation_root: &automation_root,
                selected_workspace: &workspace,
                expected_owner: Some(&owner),
                caller_holds_switch_lease: false,
            })
            .err()
            .unwrap();

        assert_eq!(error, AutomationBindingError::Invalid);
        drop(coordinator);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn missing_manifest_with_generation_evidence_fails_closed() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-incomplete-owner-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(automation_root.join("generations/orphan")).unwrap();
        fs::create_dir_all(&workspace).unwrap();
        fs::write(automation_root.join(AUTOMATION_LOCK_V1), b"").unwrap();
        fs::write(
            automation_root.join("generations/orphan/miho.exe"),
            b"orphan",
        )
        .unwrap();

        let owner = test_expected_owner();
        let probe = FixedProbeRunner {
            receipt: status_probe_receipt("invalid"),
        };
        let error = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&owner),
            Some(&probe),
        )
        .err()
        .unwrap();

        assert_eq!(error, AutomationBindingError::Invalid);
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn workspace_selection_cannot_race_an_active_automation_transaction_lease() {
        use std::os::windows::fs::OpenOptionsExt;

        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-automation-lease-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let selected = base.join("selected-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &selected, &automation_root] {
            fs::create_dir_all(directory).unwrap();
        }
        let held_lease = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .share_mode(0)
            .open(automation_root.join(AUTOMATION_LOCK_V1))
            .unwrap();
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            status_probe_receipt("invalid"),
        );

        let error = commit_workspace_selection(&state, selected.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_busy");
        assert!(!selected.join("configs").exists());
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        drop(held_lease);
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn automation_guard_pins_manifest_and_workspace_names_until_selection_commits() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-pinned-handles-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let workspace = base.join("workspace");
        let moved_workspace = base.join("moved-workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        fs::create_dir_all(&workspace).unwrap();
        let manifest = write_automation_manifest(&automation_root, &workspace);
        let receipt = active_probe_receipt(&automation_root);
        let replacement = automation_root.join("replacement.json");
        fs::write(&replacement, fs::read(&manifest).unwrap()).unwrap();

        let owner = test_expected_owner();
        let probe = FixedProbeRunner { receipt };
        let guard = acquire_automation_workspace_binding(
            Some(&automation_root),
            &workspace,
            Some(&owner),
            Some(&probe),
        )
        .unwrap()
        .unwrap();

        assert!(fs::rename(&workspace, &moved_workspace).is_err());
        assert!(fs::rename(&replacement, &manifest).is_err());
        drop(guard);
        fs::rename(&workspace, &moved_workspace).unwrap();
        fs::remove_file(&manifest).unwrap();
        fs::rename(&replacement, &manifest).unwrap();
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn workspace_selection_uses_file_identity_for_case_sensitive_ntfs_directories() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-select-case-sensitive-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let case_root = base.join("case-root");
        fs::create_dir_all(&case_root).unwrap();
        let enabled = std::process::Command::new("fsutil")
            .args(["file", "SetCaseSensitiveInfo"])
            .arg(&case_root)
            .arg("enable")
            .output()
            .is_ok_and(|output| output.status.success());
        if !enabled {
            fs::remove_dir_all(base).unwrap();
            return;
        }
        let bound = case_root.join("A");
        let selected = case_root.join("a");
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&bound, &selected, &app_data] {
            fs::create_dir_all(directory).unwrap();
        }
        assert_eq!(fs::read_dir(&case_root).unwrap().count(), 2);
        write_automation_manifest(&automation_root, &bound);
        let receipt = active_probe_receipt(&automation_root);
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let error = commit_workspace_selection(&state, selected.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_conflict");
        assert!(!selected.join("configs").exists());
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn automation_manifest_rejects_a_workspace_config_junction_even_when_file_ids_match() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-config-junction-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &workspace] {
            fs::create_dir_all(directory).unwrap();
        }
        write_automation_manifest(&automation_root, &workspace);
        let receipt = active_probe_receipt(&automation_root);
        let external = base.join("external-configs");
        fs::rename(workspace.join("configs"), &external).unwrap();
        let junction = workspace.join("configs");
        let linked = std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(&junction)
            .arg(&external)
            .output()
            .is_ok_and(|output| output.status.success());
        if !linked {
            fs::remove_dir_all(base).unwrap();
            return;
        }
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let error = commit_workspace_selection(&state, workspace.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_state_invalid");
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        fs::remove_dir(&junction).unwrap();
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn automation_manifest_rejects_a_generation_root_junction_even_when_file_ids_match() {
        let base = std::env::temp_dir().join(format!(
            "miho-desktop-automation-generation-junction-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let workspace = base.join("workspace");
        let automation_root = base.join("local-data/com.miho.endgame.automation");
        for directory in [&app_data, &workspace] {
            fs::create_dir_all(directory).unwrap();
        }
        write_automation_manifest(&automation_root, &workspace);
        let receipt = active_probe_receipt(&automation_root);
        let external = base.join("external-generations");
        fs::rename(automation_root.join("generations"), &external).unwrap();
        let junction = automation_root.join("generations");
        let linked = std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(&junction)
            .arg(&external)
            .output()
            .is_ok_and(|output| output.status.success());
        if !linked {
            fs::remove_dir_all(base).unwrap();
            return;
        }
        let state = with_test_automation(
            DesktopState::new(
                WorkspaceRegistry::initialize(app_data, app_config.clone(), None, None),
                TaskManager::new(),
            ),
            automation_root,
            receipt,
        );

        let error = commit_workspace_selection(&state, workspace.clone()).unwrap_err();

        assert_eq!(error.code, "workspace.automation_state_invalid");
        assert!(!app_config.join("desktop-settings-v1.json").exists());
        fs::remove_dir(&junction).unwrap();
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn task_preparation_rejects_stale_workspace_and_invalid_intent() {
        let (root, state, workspace_id) = state("prepare");
        let intent = serde_json::to_string(&TaskIntentV1::new(TaskIntentSpecV1::Evidence(
            Default::default(),
        )))
        .unwrap();
        let stale = prepare_task(&state, "workspace-stale", &intent).unwrap_err();
        assert_eq!(stale.code, "workspace.stale");
        let invalid = prepare_task(&state, &workspace_id, "{not-json").unwrap_err();
        assert_eq!(invalid.code, "request.invalid");
        assert!(!serde_json::to_string(&invalid)
            .unwrap()
            .contains("not-json"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn export_capabilities_require_one_valid_native_update_config() {
        let (root, state, _) = state("export-capabilities");
        let export_capabilities = |state: &DesktopState| {
            capabilities(state)
                .unwrap()
                .operations
                .into_iter()
                .filter(|capability| {
                    matches!(
                        capability.operation,
                        TaskOperationV1::HsrExport | TaskOperationV1::ZzzExport
                    )
                })
                .collect::<Vec<_>>()
        };
        let missing = export_capabilities(&state);
        assert_eq!(missing.len(), 2);
        assert!(missing.iter().all(|capability| {
            !capability.enabled && capability.missing_inputs == ["update-config"]
        }));

        fs::create_dir_all(root.join("configs")).unwrap();
        fs::write(root.join("configs/update_v1.json"), b"{broken").unwrap();
        assert!(export_capabilities(&state)
            .iter()
            .all(|capability| !capability.enabled));

        fs::write(
            root.join("configs/update_v1.json"),
            include_bytes!("../../../../configs/update_v1.json"),
        )
        .unwrap();
        assert!(export_capabilities(&state)
            .iter()
            .all(|capability| capability.enabled && capability.missing_inputs.is_empty()));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn both_export_intents_resolve_configured_native_paths_and_never_wire_them() {
        let (root, state, workspace_id) = state("export-prepare-CANARY_NATIVE");
        let missing = prepare_export_task(
            &state,
            &workspace_id,
            &serde_json::to_string(&ExportTaskIntentV1::new(ExportTaskIntentSpecV1::HsrExport(
                ExportIntentV1::default(),
            )))
            .unwrap(),
        )
        .unwrap_err();
        assert_eq!(missing.code, "export.config_invalid");
        assert!(!serde_json::to_string(&missing)
            .unwrap()
            .contains("CANARY_NATIVE"));

        fs::create_dir_all(root.join("configs")).unwrap();
        fs::write(
            root.join("configs/update_v1.json"),
            include_bytes!("../../../../configs/update_v1.json"),
        )
        .unwrap();
        let canonical = fs::canonicalize(&root).unwrap();
        for (intent, game, output, operation) in [
            (
                ExportTaskIntentV1::new(ExportTaskIntentSpecV1::HsrExport(
                    ExportIntentV1::default(),
                )),
                Game::Hsr,
                "out",
                TaskOperationV1::HsrExport,
            ),
            (
                ExportTaskIntentV1::new(ExportTaskIntentSpecV1::ZzzExport(
                    ExportIntentV1::default(),
                )),
                Game::Zzz,
                "out_zzz",
                TaskOperationV1::ZzzExport,
            ),
        ] {
            let intent_json = serde_json::to_string(&intent).unwrap();
            for forbidden in ["CANARY_NATIVE", "workspace", "path", "output", "cache"] {
                assert!(!intent_json
                    .to_ascii_lowercase()
                    .contains(&forbidden.to_ascii_lowercase()));
            }
            let (request, invocation) =
                prepare_export_task(&state, &workspace_id, &intent_json).unwrap();
            assert_eq!(request.operation(), operation);
            assert_eq!(request.task.game, game);
            assert_eq!(request.workspace, canonical);
            assert_eq!(request.task.output_root, canonical.join(output));
            assert_eq!(invocation.cwd(), canonical.as_path());
            assert_eq!(request.hsr_output_directory, "out");
            match &request.task.source {
                ExportSourceV1::Online { cache_root } => {
                    assert!(cache_root.starts_with(canonical.join(".miho/cache/rust")));
                }
                source => panic!("desktop export used unexpected source: {source:?}"),
            }
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn all_operations_resolve_only_native_paths() {
        let (root, state, workspace_id) = state("operations-CANARY_NATIVE");
        let intents = [
            TaskIntentSpecV1::Decision(miho_app::DecisionIntentV1 {
                method: "legacy-v0".to_owned(),
            }),
            TaskIntentSpecV1::Evidence(Default::default()),
            TaskIntentSpecV1::Coverage(Default::default()),
            TaskIntentSpecV1::PullValue(Default::default()),
            TaskIntentSpecV1::ReviewPacket(Default::default()),
        ];
        for intent in intents {
            let json = serde_json::to_string(&TaskIntentV1::new(intent)).unwrap();
            let (request, invocation) = prepare_task(&state, &workspace_id, &json).unwrap();
            assert_eq!(invocation.cwd(), root.as_path());
            assert_eq!(request.workspace.data_dir, root.join("out_zzz"));
            assert_eq!(
                request.workspace.box_path,
                root.join(".miho/zzz_box_state.json")
            );
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn task_manager_and_intent_errors_are_safely_mapped() {
        let busy = map_task_manager_error(TaskManagerError::Busy {
            active_task_id: "CANARY_NATIVE_TASK".to_owned(),
        });
        assert_eq!(busy.code, "task.busy");
        assert!(!serde_json::to_string(&busy)
            .unwrap()
            .contains("CANARY_NATIVE_TASK"));
        let failure = TaskFailureV1 {
            schema_version: "native".to_owned(),
            operation: None,
            code: "request.invalid".to_owned(),
            message: "CANARY_RAW_FAILURE".to_owned(),
            retryable: false,
        };
        let public = map_intent_failure(failure);
        assert!(!serde_json::to_string(&public)
            .unwrap()
            .contains("CANARY_RAW_FAILURE"));
        let unsafe_path = map_workspace_error(WorkspaceError::UntrustedPath);
        assert_eq!(unsafe_path.code, "workspace.untrusted_path");
        assert!(!serde_json::to_string(&unsafe_path)
            .unwrap()
            .contains("CANARY_SECRET"));
    }

    #[cfg(windows)]
    #[test]
    fn capabilities_and_task_prepare_reject_linked_inputs_before_execution() {
        let (root, state, workspace_id) = state("linked-input-CANARY_SECRET");
        let external = root.join("external");
        fs::create_dir_all(&external).unwrap();
        fs::write(
            external.join("team_rank_dedup_unordered.csv"),
            b"mode,rank\n",
        )
        .unwrap();
        let junction = root.join("out_zzz");
        let linked = std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(&junction)
            .arg(&external)
            .output()
            .is_ok_and(|output| output.status.success());
        if !linked {
            fs::remove_dir_all(root).unwrap();
            return;
        }

        let capability_error = capabilities(&state).unwrap_err();
        assert_eq!(capability_error.code, "workspace.untrusted_path");
        assert!(!serde_json::to_string(&capability_error)
            .unwrap()
            .contains("CANARY_SECRET"));

        let intent = serde_json::to_string(&TaskIntentV1::new(TaskIntentSpecV1::Evidence(
            Default::default(),
        )))
        .unwrap();
        let prepare_error = prepare_task(&state, &workspace_id, &intent).unwrap_err();
        assert_eq!(prepare_error.code, "workspace.untrusted_path");
        assert!(!serde_json::to_string(&prepare_error)
            .unwrap()
            .contains("CANARY_SECRET"));

        fs::remove_dir(&junction).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn pending_update_batch_preserves_every_fast_terminal_transition() {
        let root = std::env::temp_dir().join(format!(
            "miho-desktop-update-batch-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let request = TaskRequestV1::new(
            WorkspaceLayout {
                data_dir: root.join("data"),
                box_path: root.join("box.json"),
            },
            TaskSpecV1::Decision(DecisionTaskV1 {
                method: "legacy-v0".to_owned(),
                rules_path: root.join("rules.yaml"),
            }),
        );
        let manager = TaskManager::with_executor(Arc::new(ImmediateSuccess));
        let queued = manager
            .start(request, AppInvocation::capture_in(root.clone()).unwrap())
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(2);
        while !manager.get(&queued.task_id).unwrap().status.is_terminal() {
            assert!(Instant::now() < deadline, "immediate task did not finish");
            std::thread::yield_now();
        }
        let updates = pending_updates(&manager, &queued.task_id, 0).unwrap();
        assert_eq!(
            updates
                .iter()
                .map(|update| (update.sequence, update.task.status))
                .collect::<Vec<_>>(),
            vec![
                (1, TaskStatusV1::Queued),
                (2, TaskStatusV1::Running),
                (3, TaskStatusV1::Committing),
                (4, TaskStatusV1::Succeeded),
            ]
        );
        assert_eq!(
            pending_updates(&manager, &queued.task_id, 1)
                .unwrap()
                .iter()
                .map(|update| update.sequence)
                .collect::<Vec<_>>(),
            vec![2, 3, 4]
        );
        fs::remove_dir_all(root).unwrap();
    }
}
