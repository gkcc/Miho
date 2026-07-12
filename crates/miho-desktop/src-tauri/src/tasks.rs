use std::{
    sync::{Mutex, MutexGuard},
    time::Duration,
};

use miho_app::{
    parse_task_intent_v1, resolve_task_intent_v1, AppInvocation, CancelOutcomeV1,
    PublicTaskSnapshotV1, PublicTaskUpdateV1, TaskFailureV1, TaskManager, TaskManagerError,
    TaskOperationV1,
};
use serde::Serialize;
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_dialog::DialogExt;

use crate::workspace::{WorkspaceError, WorkspaceRegistry, WorkspaceSummaryV1};

const PUBLIC_COMMAND_FAILURE_SCHEMA_V1: &str = "miho-public-command-failure-v1";
const DESKTOP_CAPABILITIES_SCHEMA_V1: &str = "miho-desktop-capabilities-v1";
const WORKSPACE_SELECTION_SCHEMA_V1: &str = "miho-workspace-selection-v1";
const CANCEL_TASK_RESULT_SCHEMA_V1: &str = "miho-public-cancel-task-result-v1";
const TASK_UPDATE_SCHEMA_V1: &str = "miho-task-update-v1";
pub const TASK_UPDATE_EVENT_V1: &str = "miho-task-update-v1";

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
}

impl DesktopState {
    pub fn new(workspaces: WorkspaceRegistry, tasks: TaskManager) -> Self {
        Self {
            workspaces,
            tasks,
            workspace_task_gate: Mutex::new(()),
        }
    }

    fn lock_gate(&self) -> Result<MutexGuard<'_, ()>, PublicCommandFailureV1> {
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
    let workspace = state.workspaces.select(root).map_err(map_workspace_error)?;
    Ok(WorkspaceSelectionV1 {
        schema_version: WORKSPACE_SELECTION_SCHEMA_V1.to_owned(),
        selected: true,
        workspace,
    })
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
    spawn_task_monitor(app, state.tasks.clone(), snapshot.task_id.clone(), sequence);
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
pub fn cancel_task(task_id: String, state: State<'_, DesktopState>) -> PublicCancelTaskResultV1 {
    let result = state.tasks.cancel(&task_id);
    let task = result.snapshot.map(|snapshot| snapshot.to_public());
    PublicCancelTaskResultV1 {
        schema_version: CANCEL_TASK_RESULT_SCHEMA_V1.to_owned(),
        task_id: result.task_id,
        outcome: result.outcome,
        task,
    }
}

fn capabilities(state: &DesktopState) -> Result<DesktopCapabilitiesV1, PublicCommandFailureV1> {
    let workspace = state.workspaces.summary().map_err(map_workspace_error)?;
    let (_, paths) = state
        .workspaces
        .native_paths(&workspace.workspace_id)
        .map_err(map_workspace_error)?;
    let box_state = [(!paths.box_path.is_file()).then_some("box-state")];
    let evidence_inputs = [
        (!paths.box_path.is_file()).then_some("box-state"),
        (!paths
            .data_dir
            .join("team_rank_dedup_unordered.csv")
            .is_file())
        .then_some("team-rank-dedup"),
        (!paths.banner_plan_path.is_file()).then_some("banner-plan"),
    ];
    let operations = vec![
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
        task_history_persistent: false,
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

fn spawn_task_monitor(app: AppHandle, tasks: TaskManager, task_id: String, mut last_sequence: u64) {
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_millis(50)).await;
            let Some(updates) = pending_updates(&tasks, &task_id, last_sequence) else {
                return;
            };
            for update in updates {
                last_sequence = update.sequence;
                let terminal = update.task.status.is_terminal();
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
        DecisionTaskV1, ExecutionObserver, TaskExecutor, TaskIntentSpecV1, TaskIntentV1,
        TaskReceiptV1, TaskRequestV1, TaskSpecV1, TaskStatusV1, WorkspaceLayout,
        TASK_RECEIPT_SCHEMA_V1,
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
    fn capabilities_are_pathless_and_truthful_about_recovery() {
        let (root, state, _) = state("capabilities-CANARY_SECRET");
        let value = serde_json::to_string(&capabilities(&state).unwrap()).unwrap();
        assert!(!value.contains("CANARY_SECRET"));
        assert!(!value.contains("root"));
        assert!(value.contains("\"abrupt_termination_supported\":false"));
        assert!(value.contains("\"cross_process_recovery_supported\":false"));
        assert!(value.contains("\"max_concurrent_tasks\":1"));
        assert!(value.contains("\"supports_cancel\":true"));
        assert!(value.contains("\"task_history_persistent\":false"));
        assert!(value.contains("\"enabled\":false"));
        fs::remove_dir_all(root).unwrap();
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
