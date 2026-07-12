use std::{
    any::Any,
    collections::BTreeMap,
    fmt,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex, MutexGuard,
    },
    time::{SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};

use crate::{
    execute_task_observed_v1, AppInvocation, ExecutionControlError, ExecutionObserver,
    TaskFailureV1, TaskOperationV1, TaskReceiptV1, TaskRequestV1, TASK_FAILURE_SCHEMA_V1,
};

pub const TASK_SNAPSHOT_SCHEMA_V1: &str = "miho-task-snapshot-v1";
pub const PUBLIC_TASK_SNAPSHOT_SCHEMA_V1: &str = "miho-public-task-snapshot-v1";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum TaskStatusV1 {
    Queued,
    Running,
    Committing,
    Succeeded,
    Failed,
    Cancelling,
    Cancelled,
}

impl TaskStatusV1 {
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Succeeded | Self::Failed | Self::Cancelled)
    }
}

/// Trusted native snapshot. It intentionally retains native receipts and
/// failures and therefore cannot cross a WebView serde boundary directly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TaskSnapshotV1 {
    pub schema_version: String,
    pub task_id: String,
    pub operation: TaskOperationV1,
    pub status: TaskStatusV1,
    pub status_history: Vec<TaskStatusV1>,
    pub cancellation_requested: bool,
    pub receipt: Option<TaskReceiptV1>,
    pub failure: Option<TaskFailureV1>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CancelOutcomeV1 {
    Requested,
    TooLate,
    AlreadyTerminal,
    NotFound,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CancelTaskResultV1 {
    pub task_id: String,
    pub outcome: CancelOutcomeV1,
    pub snapshot: Option<TaskSnapshotV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicArtifactV1 {
    pub artifact_id: String,
    pub name: String,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicTaskFailureV1 {
    pub code: String,
    pub retryable: bool,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicTaskSnapshotV1 {
    pub schema_version: String,
    pub task_id: String,
    pub operation: TaskOperationV1,
    pub status: TaskStatusV1,
    pub status_history: Vec<TaskStatusV1>,
    pub cancellation_requested: bool,
    pub artifacts: Vec<PublicArtifactV1>,
    pub failure: Option<PublicTaskFailureV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct PublicTaskUpdateV1 {
    pub sequence: u64,
    pub task: PublicTaskSnapshotV1,
}

impl TaskSnapshotV1 {
    pub fn to_public(&self) -> PublicTaskSnapshotV1 {
        self.public_at(self.status_history.len())
    }

    pub fn public_updates_since(&self, after_sequence: u64) -> Vec<PublicTaskUpdateV1> {
        self.status_history
            .iter()
            .enumerate()
            .filter_map(|(index, _)| {
                let sequence = index as u64 + 1;
                (sequence > after_sequence).then(|| PublicTaskUpdateV1 {
                    sequence,
                    task: self.public_at(index + 1),
                })
            })
            .collect()
    }

    fn public_at(&self, history_len: usize) -> PublicTaskSnapshotV1 {
        let history_len = history_len.min(self.status_history.len());
        let status_history = self.status_history[..history_len].to_vec();
        let status = status_history.last().copied().unwrap_or(self.status);
        let cancellation_requested = status_history
            .iter()
            .any(|status| matches!(status, TaskStatusV1::Cancelling | TaskStatusV1::Cancelled));
        PublicTaskSnapshotV1 {
            schema_version: PUBLIC_TASK_SNAPSHOT_SCHEMA_V1.to_owned(),
            task_id: self.task_id.clone(),
            operation: self.operation,
            status,
            status_history,
            cancellation_requested,
            artifacts: if status == TaskStatusV1::Succeeded {
                self.receipt
                    .as_ref()
                    .map(|receipt| {
                        public_artifacts(&self.task_id, self.operation, receipt.outputs.len())
                    })
                    .unwrap_or_default()
            } else {
                Vec::new()
            },
            failure: if status == TaskStatusV1::Failed {
                self.failure.as_ref().map(|failure| PublicTaskFailureV1 {
                    code: failure.code.clone(),
                    retryable: failure.retryable,
                    message: if failure.code == "task.panicked" {
                        "Task failed unexpectedly.".to_owned()
                    } else {
                        "Task failed. Check native logs for details.".to_owned()
                    },
                })
            } else {
                None
            },
        }
    }
}

fn public_artifacts(
    task_id: &str,
    operation: TaskOperationV1,
    count: usize,
) -> Vec<PublicArtifactV1> {
    (0..count)
        .map(|index| {
            let (name, kind) = public_artifact_label(operation, index, count);
            PublicArtifactV1 {
                artifact_id: format!("{task_id}:artifact:{index}"),
                name,
                kind,
            }
        })
        .collect()
}

fn public_artifact_label(
    operation: TaskOperationV1,
    index: usize,
    count: usize,
) -> (String, String) {
    match (operation, index) {
        (TaskOperationV1::Decision, 0) => ("decision_cards.json".to_owned(), "json".to_owned()),
        (TaskOperationV1::Decision, 1) => ("decision_report.md".to_owned(), "markdown".to_owned()),
        (TaskOperationV1::Evidence, _) => {
            ("evidence_pool_summary.md".to_owned(), "markdown".to_owned())
        }
        (TaskOperationV1::Coverage, 0) => (
            "current_box_team_coverage.md".to_owned(),
            "markdown".to_owned(),
        ),
        (TaskOperationV1::Coverage, 1) => (
            "target_box_team_coverage.md".to_owned(),
            "markdown".to_owned(),
        ),
        (TaskOperationV1::Coverage, 2) => {
            ("team_signature_aggregates.csv".to_owned(), "csv".to_owned())
        }
        (TaskOperationV1::PullValue, _) if count == 1 => {
            ("pull_value_report.md".to_owned(), "markdown".to_owned())
        }
        (TaskOperationV1::PullValue, _) => (
            format!("pull_value_report_{}.md", index + 1),
            "markdown".to_owned(),
        ),
        (TaskOperationV1::ReviewPacket, _) if count == 1 => (
            "gpt_pull_reviewer_packet.md".to_owned(),
            "markdown".to_owned(),
        ),
        (TaskOperationV1::ReviewPacket, _) => (
            format!("gpt_pull_reviewer_packet_{}.md", index + 1),
            "markdown".to_owned(),
        ),
        _ => (format!("artifact_{}", index + 1), "binary".to_owned()),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TaskManagerError {
    Busy { active_task_id: String },
    SpawnFailed { message: String },
}

impl fmt::Display for TaskManagerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Busy { active_task_id } => write!(
                formatter,
                "task manager already has an active task: {active_task_id}"
            ),
            Self::SpawnFailed { message } => {
                write!(formatter, "cannot spawn task worker: {message}")
            }
        }
    }
}

impl std::error::Error for TaskManagerError {}

/// Background executors must call `observer.before_commit()` immediately
/// before every filesystem mutation. The built-in executor has one atomic
/// batch per task and follows this contract.
pub trait TaskExecutor: Send + Sync + 'static {
    fn execute(
        &self,
        request: &TaskRequestV1,
        invocation: &AppInvocation,
        observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1>;
}

pub trait TaskSpawner: Send + Sync + 'static {
    fn spawn(&self, name: String, job: Box<dyn FnOnce() + Send + 'static>) -> std::io::Result<()>;
}

struct CoreTaskExecutor;

impl TaskExecutor for CoreTaskExecutor {
    fn execute(
        &self,
        request: &TaskRequestV1,
        invocation: &AppInvocation,
        observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        execute_task_observed_v1(request, invocation, observer)
    }
}

struct ThreadTaskSpawner;

impl TaskSpawner for ThreadTaskSpawner {
    fn spawn(&self, name: String, job: Box<dyn FnOnce() + Send + 'static>) -> std::io::Result<()> {
        std::thread::Builder::new()
            .name(name)
            .spawn(job)
            .map(|_| ())
    }
}

#[derive(Clone)]
pub struct TaskManager {
    inner: Arc<ManagerInner>,
    executor: Arc<dyn TaskExecutor>,
    spawner: Arc<dyn TaskSpawner>,
}

struct ManagerInner {
    next_id: AtomicU64,
    task_prefix: String,
    state: Mutex<ManagerState>,
}

impl ManagerInner {
    fn lock_state(&self) -> MutexGuard<'_, ManagerState> {
        self.state
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

static NEXT_MANAGER_ID: AtomicU64 = AtomicU64::new(1);

#[derive(Default)]
struct ManagerState {
    active: Option<String>,
    tasks: BTreeMap<String, TaskRecord>,
}

struct TaskRecord {
    operation: TaskOperationV1,
    status: TaskStatusV1,
    status_history: Vec<TaskStatusV1>,
    cancellation_requested: bool,
    receipt: Option<TaskReceiptV1>,
    failure: Option<TaskFailureV1>,
}

impl TaskRecord {
    fn new(operation: TaskOperationV1) -> Self {
        Self {
            operation,
            status: TaskStatusV1::Queued,
            status_history: vec![TaskStatusV1::Queued],
            cancellation_requested: false,
            receipt: None,
            failure: None,
        }
    }

    fn transition(&mut self, status: TaskStatusV1) {
        if self.status.is_terminal() || self.status == status {
            return;
        }
        self.status = status;
        self.status_history.push(status);
    }

    fn snapshot(&self, task_id: &str) -> TaskSnapshotV1 {
        TaskSnapshotV1 {
            schema_version: TASK_SNAPSHOT_SCHEMA_V1.to_owned(),
            task_id: task_id.to_owned(),
            operation: self.operation,
            status: self.status,
            status_history: self.status_history.clone(),
            cancellation_requested: self.cancellation_requested,
            receipt: self.receipt.clone(),
            failure: self.failure.clone(),
        }
    }
}

impl Default for TaskManager {
    fn default() -> Self {
        Self::new()
    }
}

impl TaskManager {
    pub fn new() -> Self {
        Self::with_executor(Arc::new(CoreTaskExecutor))
    }

    pub fn with_executor(executor: Arc<dyn TaskExecutor>) -> Self {
        Self::with_runtime(executor, Arc::new(ThreadTaskSpawner))
    }

    pub fn with_runtime(executor: Arc<dyn TaskExecutor>, spawner: Arc<dyn TaskSpawner>) -> Self {
        let epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let manager_id = NEXT_MANAGER_ID.fetch_add(1, Ordering::Relaxed);
        Self {
            inner: Arc::new(ManagerInner {
                next_id: AtomicU64::new(1),
                task_prefix: format!("{}-{epoch}-{manager_id}", std::process::id()),
                state: Mutex::new(ManagerState::default()),
            }),
            executor,
            spawner,
        }
    }

    pub fn start(
        &self,
        request: TaskRequestV1,
        invocation: AppInvocation,
    ) -> Result<TaskSnapshotV1, TaskManagerError> {
        let operation = request.operation();
        let task_id = format!(
            "task-{}-{:016}",
            self.inner.task_prefix,
            self.inner.next_id.fetch_add(1, Ordering::Relaxed)
        );
        let snapshot = {
            let mut state = self.inner.lock_state();
            if let Some(active_task_id) = &state.active {
                return Err(TaskManagerError::Busy {
                    active_task_id: active_task_id.clone(),
                });
            }
            let record = TaskRecord::new(operation);
            let snapshot = record.snapshot(&task_id);
            state.tasks.insert(task_id.clone(), record);
            state.active = Some(task_id.clone());
            snapshot
        };

        let manager = self.clone();
        let worker_task_id = task_id.clone();
        if let Err(error) = self.spawner.spawn(
            format!("miho-{task_id}"),
            Box::new(move || manager.run_worker(worker_task_id, request, invocation)),
        ) {
            let mut state = self.inner.lock_state();
            state.tasks.remove(&task_id);
            if state.active.as_deref() == Some(&task_id) {
                state.active = None;
            }
            return Err(TaskManagerError::SpawnFailed {
                message: error.to_string(),
            });
        }
        Ok(snapshot)
    }

    pub fn get(&self, task_id: &str) -> Option<TaskSnapshotV1> {
        self.inner
            .lock_state()
            .tasks
            .get(task_id)
            .map(|record| record.snapshot(task_id))
    }

    pub fn list(&self) -> Vec<TaskSnapshotV1> {
        self.inner
            .lock_state()
            .tasks
            .iter()
            .map(|(task_id, record)| record.snapshot(task_id))
            .collect()
    }

    pub fn get_public(&self, task_id: &str) -> Option<PublicTaskSnapshotV1> {
        self.get(task_id).map(|snapshot| snapshot.to_public())
    }

    pub fn list_public(&self) -> Vec<PublicTaskSnapshotV1> {
        self.list()
            .into_iter()
            .map(|snapshot| snapshot.to_public())
            .collect()
    }

    pub fn public_updates_since(
        &self,
        task_id: &str,
        after_sequence: u64,
    ) -> Option<Vec<PublicTaskUpdateV1>> {
        self.get(task_id)
            .map(|snapshot| snapshot.public_updates_since(after_sequence))
    }

    pub fn cancel(&self, task_id: &str) -> CancelTaskResultV1 {
        let mut state = self.inner.lock_state();
        let Some(record) = state.tasks.get_mut(task_id) else {
            return CancelTaskResultV1 {
                task_id: task_id.to_owned(),
                outcome: CancelOutcomeV1::NotFound,
                snapshot: None,
            };
        };
        let outcome = match record.status {
            TaskStatusV1::Queued | TaskStatusV1::Running => {
                record.cancellation_requested = true;
                record.transition(TaskStatusV1::Cancelling);
                CancelOutcomeV1::Requested
            }
            TaskStatusV1::Cancelling => CancelOutcomeV1::Requested,
            TaskStatusV1::Committing => CancelOutcomeV1::TooLate,
            TaskStatusV1::Succeeded | TaskStatusV1::Failed | TaskStatusV1::Cancelled => {
                CancelOutcomeV1::AlreadyTerminal
            }
        };
        CancelTaskResultV1 {
            task_id: task_id.to_owned(),
            outcome,
            snapshot: Some(record.snapshot(task_id)),
        }
    }

    fn run_worker(&self, task_id: String, request: TaskRequestV1, invocation: AppInvocation) {
        {
            let mut state = self.inner.lock_state();
            let record = state.tasks.get_mut(&task_id).expect("task record missing");
            if record.cancellation_requested {
                record.transition(TaskStatusV1::Cancelled);
                if state.active.as_deref() == Some(&task_id) {
                    state.active = None;
                }
                return;
            }
            record.transition(TaskStatusV1::Running);
        }

        let observer = ManagerExecutionObserver {
            inner: self.inner.clone(),
            task_id: task_id.clone(),
        };
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            self.executor.execute(&request, &invocation, &observer)
        }));
        let mut state = self.inner.lock_state();
        let record = state.tasks.get_mut(&task_id).expect("task record missing");
        match result {
            Ok(Ok(_receipt)) if record.cancellation_requested => {
                record.transition(TaskStatusV1::Cancelled);
            }
            Ok(Ok(receipt)) => {
                if record.status != TaskStatusV1::Committing {
                    record.transition(TaskStatusV1::Committing);
                }
                record.receipt = Some(receipt);
                record.transition(TaskStatusV1::Succeeded);
            }
            Ok(Err(error)) if error.downcast_ref::<ExecutionControlError>().is_some() => {
                record.transition(TaskStatusV1::Cancelled);
            }
            Ok(Err(error)) => {
                record.failure = Some(TaskFailureV1::from_error(Some(record.operation), &error));
                record.transition(TaskStatusV1::Failed);
            }
            Err(payload) => {
                record.failure = Some(TaskFailureV1 {
                    schema_version: TASK_FAILURE_SCHEMA_V1.to_owned(),
                    operation: Some(record.operation),
                    code: "task.panicked".to_owned(),
                    message: panic_message(payload.as_ref()),
                    retryable: false,
                });
                record.transition(TaskStatusV1::Failed);
            }
        }
        if state.active.as_deref() == Some(&task_id) {
            state.active = None;
        }
    }
}

struct ManagerExecutionObserver {
    inner: Arc<ManagerInner>,
    task_id: String,
}

impl ExecutionObserver for ManagerExecutionObserver {
    fn before_commit(&self) -> Result<(), ExecutionControlError> {
        let mut state = self.inner.lock_state();
        let record = state
            .tasks
            .get_mut(&self.task_id)
            .expect("task record missing");
        if record.cancellation_requested || record.status == TaskStatusV1::Cancelling {
            record.transition(TaskStatusV1::Cancelled);
            return Err(ExecutionControlError::Cancelled);
        }
        record.transition(TaskStatusV1::Committing);
        Ok(())
    }
}

fn panic_message(payload: &(dyn Any + Send)) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        (*message).to_owned()
    } else if let Some(message) = payload.downcast_ref::<String>() {
        message.clone()
    } else {
        "task executor panicked".to_owned()
    }
}
