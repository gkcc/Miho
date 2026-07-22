use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc::{self, Receiver, Sender},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};

use anyhow::bail;
use chrono::{DateTime, NaiveDate, NaiveDateTime};
use miho_app::{
    AppInvocation, CancelOutcomeV1, EvidenceTaskV1, ExecutionObserver, ExportInvocation,
    ExportSourceV1, ExportTaskExecutor, ExportTaskV1, PublicTaskSnapshotV1, PullTaskV1,
    TaskExecutor, TaskFailureV1, TaskFreshnessSummaryV1, TaskManager, TaskManagerError,
    TaskModeFreshnessV1, TaskOperationV1, TaskReceiptV1, TaskRequestV1, TaskSnapshotV1,
    TaskSpawner, TaskSpecV1, TaskStatusV1, TrustedExportTaskV1, WorkspaceLayout,
    WorkspaceWriteLease, TASK_FAILURE_SCHEMA_V1, TASK_RECEIPT_SCHEMA_V1, TASK_SNAPSHOT_SCHEMA_V1,
};
use miho_core::{
    contract::{FeatureFlags, GameMode},
    pipeline::Game,
};

static NEXT_ID: AtomicU64 = AtomicU64::new(0);

fn temp_root(label: &str) -> PathBuf {
    let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "miho-task-manager-{label}-{}-{id}",
        std::process::id()
    ));
    if root.exists() {
        fs::remove_dir_all(&root).unwrap();
    }
    fs::create_dir_all(&root).unwrap();
    root
}

fn request() -> TaskRequestV1 {
    TaskRequestV1::new(
        WorkspaceLayout {
            data_dir: PathBuf::from("data"),
            box_path: PathBuf::from("box.json"),
        },
        TaskSpecV1::Evidence(EvidenceTaskV1::default()),
    )
}

fn invocation(root: PathBuf) -> AppInvocation {
    AppInvocation::new(
        root,
        NaiveDateTime::parse_from_str("2026-07-13T09:10:11", "%Y-%m-%dT%H:%M:%S").unwrap(),
    )
    .unwrap()
}

fn export_invocation(root: PathBuf) -> ExportInvocation {
    ExportInvocation::new(
        root,
        DateTime::parse_from_rfc3339("2026-07-13T09:10:11+08:00").unwrap(),
    )
    .unwrap()
}

fn export_request(root: &std::path::Path, game: Game) -> TrustedExportTaskV1 {
    let modes = match game {
        Game::Hsr => vec![GameMode::HsrMoc],
        Game::Zzz => vec![GameMode::ZzzSd],
    };
    TrustedExportTaskV1 {
        workspace: root.to_path_buf(),
        task: ExportTaskV1 {
            game,
            modes,
            from_date: NaiveDate::from_ymd_opt(2026, 1, 1).unwrap(),
            to_date: NaiveDate::from_ymd_opt(2026, 7, 13).unwrap(),
            output_root: root.join(match game {
                Game::Hsr => "CANARY_NATIVE_HSR_OUTPUT",
                Game::Zzz => "CANARY_NATIVE_ZZZ_OUTPUT",
            }),
            repo_id: "CANARY_NATIVE_REPO".to_owned(),
            revision: "CANARY_NATIVE_REVISION".to_owned(),
            features: FeatureFlags {
                hf_teams: true,
                prydwen_visible: true,
                prydwen_tier: true,
                official_names: true,
            },
            prydwen_top_n: 100,
            name_map_seed: None,
            source: ExportSourceV1::Fixture {
                root: root.join("CANARY_NATIVE_FIXTURE"),
                supplemental_root: None,
            },
        },
        hsr_output_directory: "CANARY_NATIVE_HSR_DIRECTORY".to_owned(),
    }
}

fn receipt() -> TaskReceiptV1 {
    TaskReceiptV1 {
        schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
        operation: TaskOperationV1::Evidence,
        method_version: "evidence-first-test".to_owned(),
        output_schema: "test".to_owned(),
        local_datetime: "2026-07-13T09:10:11".to_owned(),
        outputs: Vec::new(),
        notices: Vec::new(),
        freshness: None,
    }
}

fn freshness() -> TaskFreshnessSummaryV1 {
    TaskFreshnessSummaryV1 {
        status: "warning".to_owned(),
        modes: BTreeMap::from([(
            "sd".to_owned(),
            TaskModeFreshnessV1 {
                status: "stale".to_owned(),
                sample_date: "2026-07-01".to_owned(),
                start_date: "2026-06-01".to_owned(),
                end_date: "2026-06-30".to_owned(),
            },
        )]),
    }
}

struct ControlledExecutor {
    pre_commit_reached: Sender<()>,
    release_pre_commit: Mutex<Receiver<()>>,
    committing_reached: Sender<()>,
    release_commit: Mutex<Receiver<()>>,
    output: PathBuf,
}

impl TaskExecutor for ControlledExecutor {
    fn execute(
        &self,
        _request: &TaskRequestV1,
        _invocation: &AppInvocation,
        observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        self.pre_commit_reached.send(()).unwrap();
        self.release_pre_commit.lock().unwrap().recv().unwrap();
        observer.before_commit()?;
        self.committing_reached.send(()).unwrap();
        self.release_commit.lock().unwrap().recv().unwrap();
        fs::write(&self.output, b"committed")?;
        Ok(receipt())
    }
}

struct FailingExecutor;

impl TaskExecutor for FailingExecutor {
    fn execute(
        &self,
        _request: &TaskRequestV1,
        _invocation: &AppInvocation,
        _observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        bail!("injected executor failure")
    }
}

struct ImmediateSuccessExecutor;

impl TaskExecutor for ImmediateSuccessExecutor {
    fn execute(
        &self,
        _request: &TaskRequestV1,
        _invocation: &AppInvocation,
        observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        observer.before_commit()?;
        let mut value = receipt();
        value.outputs = vec![PathBuf::from("C:/NATIVE_ONLY/report.md")];
        Ok(value)
    }
}

struct ControlledExportExecutor {
    pre_commit_reached: Sender<()>,
    release_pre_commit: Mutex<Receiver<()>>,
    output: PathBuf,
}

impl ExportTaskExecutor for ControlledExportExecutor {
    fn execute(
        &self,
        request: &TrustedExportTaskV1,
        invocation: &ExportInvocation,
        observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        self.pre_commit_reached.send(()).unwrap();
        self.release_pre_commit.lock().unwrap().recv().unwrap();
        observer.before_commit()?;
        fs::write(&self.output, b"export committed")?;
        Ok(TaskReceiptV1 {
            schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
            operation: request.operation(),
            method_version: "export-test".to_owned(),
            output_schema: "test".to_owned(),
            local_datetime: invocation.local_datetime().to_string(),
            outputs: vec![request.task.output_root.clone()],
            notices: Vec::new(),
            freshness: Some(freshness()),
        })
    }
}

struct FailingExportExecutor;

impl ExportTaskExecutor for FailingExportExecutor {
    fn execute(
        &self,
        _request: &TrustedExportTaskV1,
        _invocation: &ExportInvocation,
        _observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        bail!("CANARY_RAW_EXPORT_ERROR C:/CANARY_EXPORT_PATH")
    }
}

struct PanickingExecutor;

impl TaskExecutor for PanickingExecutor {
    fn execute(
        &self,
        _request: &TaskRequestV1,
        _invocation: &AppInvocation,
        _observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        panic!("CANARY_RAW_PANIC_PATH")
    }
}

struct FailingSpawner;

impl TaskSpawner for FailingSpawner {
    fn spawn(
        &self,
        _name: String,
        _job: Box<dyn FnOnce() + Send + 'static>,
    ) -> std::io::Result<()> {
        Err(std::io::Error::other("injected spawn failure"))
    }
}

struct ObserverHoldExecutor {
    pre_commit_reached: Sender<()>,
    release_pre_commit: Mutex<Receiver<()>>,
    observer_returned: Sender<()>,
    release_executor_return: Mutex<Receiver<()>>,
}

impl TaskExecutor for ObserverHoldExecutor {
    fn execute(
        &self,
        _request: &TaskRequestV1,
        _invocation: &AppInvocation,
        observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        self.pre_commit_reached.send(()).unwrap();
        self.release_pre_commit.lock().unwrap().recv().unwrap();
        let control = observer.before_commit();
        self.observer_returned.send(()).unwrap();
        self.release_executor_return.lock().unwrap().recv().unwrap();
        control?;
        Ok(receipt())
    }
}

struct OrdinaryFailureAfterCancelExecutor {
    entered: Sender<()>,
    release: Mutex<Receiver<()>>,
}

impl TaskExecutor for OrdinaryFailureAfterCancelExecutor {
    fn execute(
        &self,
        _request: &TaskRequestV1,
        _invocation: &AppInvocation,
        _observer: &dyn ExecutionObserver,
    ) -> anyhow::Result<TaskReceiptV1> {
        self.entered.send(()).unwrap();
        self.release.lock().unwrap().recv().unwrap();
        bail!("ordinary executor failure after cancellation request")
    }
}

struct ControlledHarness {
    manager: TaskManager,
    pre_commit_reached: Receiver<()>,
    release_pre_commit: Sender<()>,
    committing_reached: Receiver<()>,
    release_commit: Sender<()>,
}

fn controlled_manager(output: PathBuf) -> ControlledHarness {
    let (pre_commit_tx, pre_commit_rx) = mpsc::channel();
    let (release_pre_tx, release_pre_rx) = mpsc::channel();
    let (committing_tx, committing_rx) = mpsc::channel();
    let (release_commit_tx, release_commit_rx) = mpsc::channel();
    ControlledHarness {
        manager: TaskManager::with_executor(Arc::new(ControlledExecutor {
            pre_commit_reached: pre_commit_tx,
            release_pre_commit: Mutex::new(release_pre_rx),
            committing_reached: committing_tx,
            release_commit: Mutex::new(release_commit_rx),
            output,
        })),
        pre_commit_reached: pre_commit_rx,
        release_pre_commit: release_pre_tx,
        committing_reached: committing_rx,
        release_commit: release_commit_tx,
    }
}

fn wait_terminal(manager: &TaskManager, task_id: &str) -> TaskSnapshotV1 {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let snapshot = manager.get(task_id).unwrap();
        if snapshot.status.is_terminal() {
            return snapshot;
        }
        assert!(
            Instant::now() < deadline,
            "task did not reach terminal state"
        );
        thread::sleep(Duration::from_millis(5));
    }
}

#[test]
fn default_task_executor_respects_the_cross_process_workspace_lease() {
    let root = temp_root("workspace-busy");
    let lease = WorkspaceWriteLease::acquire(&root).unwrap();
    let manager = TaskManager::new();
    let queued = manager.start(request(), invocation(root.clone())).unwrap();
    let failed = wait_terminal(&manager, &queued.task_id);
    assert_eq!(failed.status, TaskStatusV1::Failed);
    let failure = failed.failure.unwrap();
    assert_eq!(failure.code, "workspace.write_busy");
    assert_eq!(failure.message, "workspace.write_busy");
    assert!(failure.retryable);
    drop(lease);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn default_export_executor_respects_the_same_workspace_writer_lease() {
    let root = temp_root("export-workspace-busy");
    let lease = WorkspaceWriteLease::acquire(&root).unwrap();
    let manager = TaskManager::new();
    let queued = manager
        .start_export(
            export_request(&root, Game::Hsr),
            export_invocation(root.clone()),
        )
        .unwrap();
    let failed = wait_terminal(&manager, &queued.task_id);
    assert_eq!(failed.operation, TaskOperationV1::HsrExport);
    assert_eq!(failed.status, TaskStatusV1::Failed);
    assert_eq!(failed.failure.unwrap().message, "workspace.write_busy");
    drop(lease);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn default_managed_export_executes_fixture_and_returns_a_pathless_bundle_receipt() {
    let root = temp_root("managed-export-fixture");
    let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut request = export_request(&root, Game::Hsr);
    request.task.output_root = root.join("out");
    request.task.source = ExportSourceV1::Fixture {
        root: repository.join("tests/fixtures/offline_hsr"),
        supplemental_root: Some(repository.join("tests/fixtures/hsr_supplemental")),
    };
    request.task.repo_id = "LvlUrArti/MocDataProcessed".to_owned();
    request.task.revision = "main".to_owned();
    request.hsr_output_directory = "out".to_owned();
    let manager = TaskManager::new();
    let queued = manager
        .start_export(request, export_invocation(root.clone()))
        .unwrap();
    let succeeded = wait_terminal(&manager, &queued.task_id);
    assert_eq!(
        succeeded.status,
        TaskStatusV1::Succeeded,
        "managed export snapshot: {succeeded:#?}"
    );
    assert_eq!(
        succeeded.receipt.as_ref().unwrap().outputs,
        [root.join("out/artifact_manifest.json")]
    );
    let native_freshness = succeeded
        .receipt
        .as_ref()
        .unwrap()
        .freshness
        .as_ref()
        .unwrap();
    assert_eq!(native_freshness.status, "warning");
    assert_eq!(native_freshness.modes["moc"].status, "stale");
    assert_eq!(native_freshness.modes["moc"].sample_date, "2026-06-25");
    assert_eq!(native_freshness.modes["moc"].start_date, "2026-06-01");
    assert_eq!(native_freshness.modes["moc"].end_date, "2026-06-15");
    assert!(root.join("out/artifact_manifest.json").is_file());
    let public = succeeded.to_public();
    assert_eq!(public.artifacts.len(), 1);
    assert_eq!(public.artifacts[0].name, "hsr-export-bundle");
    assert_eq!(
        manager.artifact_path(&public.artifacts[0].artifact_id),
        Some(root.join("out/artifact_manifest.json"))
    );
    assert!(manager
        .artifact_path(&format!("{}:artifact:1", succeeded.task_id))
        .is_none());
    assert_eq!(public.freshness.as_ref(), Some(native_freshness));
    let updates = manager.public_updates_since(&succeeded.task_id, 0).unwrap();
    assert!(updates[..updates.len() - 1]
        .iter()
        .all(|update| update.task.freshness.is_none()));
    assert_eq!(updates.last().unwrap().task.freshness, public.freshness);
    let mut public_value = serde_json::to_value(&public).unwrap();
    assert!(public_value["freshness"]["modes"]["moc"]
        .get("source")
        .is_none());
    let public_json = serde_json::to_string(&public_value).unwrap();
    assert!(!public_json.contains(&root.to_string_lossy().to_string()));
    public_value.as_object_mut().unwrap().remove("freshness");
    let old_snapshot: PublicTaskSnapshotV1 = serde_json::from_value(public_value).unwrap();
    assert!(old_snapshot.freshness.is_none());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn hsr_cancel_and_zzz_receipt_share_global_state_without_public_native_leaks() {
    for (game, cancel_before_commit) in [(Game::Hsr, true), (Game::Zzz, false)] {
        let root = temp_root(match game {
            Game::Hsr => "managed-hsr-export",
            Game::Zzz => "managed-zzz-export",
        });
        let output = root.join("must-only-exist-after-permit");
        let (pre_tx, pre_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let manager = TaskManager::with_executors(
            Arc::new(ImmediateSuccessExecutor),
            Arc::new(ControlledExportExecutor {
                pre_commit_reached: pre_tx,
                release_pre_commit: Mutex::new(release_rx),
                output: output.clone(),
            }),
        );
        let queued = manager
            .start_export(export_request(&root, game), export_invocation(root.clone()))
            .unwrap();
        pre_rx.recv().unwrap();
        assert!(matches!(
            manager.start(request(), invocation(root.clone())),
            Err(TaskManagerError::Busy { active_task_id }) if active_task_id == queued.task_id
        ));

        if cancel_before_commit {
            assert_eq!(
                manager.cancel(&queued.task_id).outcome,
                CancelOutcomeV1::Requested
            );
        }
        release_tx.send(()).unwrap();
        let terminal = wait_terminal(&manager, &queued.task_id);
        let public = terminal.to_public();
        let serialized = serde_json::to_string(&public).unwrap();
        for canary in [
            "CANARY_NATIVE_HSR_OUTPUT",
            "CANARY_NATIVE_ZZZ_OUTPUT",
            "CANARY_NATIVE_REPO",
            "CANARY_NATIVE_REVISION",
            "CANARY_NATIVE_FIXTURE",
            "CANARY_NATIVE_HSR_DIRECTORY",
        ] {
            assert!(
                !serialized.contains(canary),
                "{canary} leaked into {serialized}"
            );
        }
        if cancel_before_commit {
            assert_eq!(terminal.status, TaskStatusV1::Cancelled);
            assert!(!output.exists());
            assert!(public.artifacts.is_empty());
            assert!(public.freshness.is_none());
        } else {
            assert_eq!(terminal.status, TaskStatusV1::Succeeded);
            assert_eq!(fs::read(&output).unwrap(), b"export committed");
            assert_eq!(public.artifacts.len(), 1);
            assert_eq!(public.artifacts[0].name, "zzz-export-bundle");
            assert_eq!(public.artifacts[0].kind, "artifact-bundle");
            assert_eq!(public.freshness, Some(freshness()));
        }
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn export_failure_snapshot_keeps_raw_error_native_only() {
    let root = temp_root("managed-export-failure");
    let manager = TaskManager::with_export_executor(Arc::new(FailingExportExecutor));
    let queued = manager
        .start_export(
            export_request(&root, Game::Zzz),
            export_invocation(root.clone()),
        )
        .unwrap();
    let failed = wait_terminal(&manager, &queued.task_id);
    assert_eq!(failed.status, TaskStatusV1::Failed);
    assert!(failed
        .failure
        .as_ref()
        .unwrap()
        .message
        .contains("CANARY_RAW_EXPORT_ERROR"));
    let public_json = serde_json::to_string(&failed.to_public()).unwrap();
    assert!(!public_json.contains("CANARY_RAW_EXPORT_ERROR"));
    assert!(!public_json.contains("CANARY_EXPORT_PATH"));
    assert!(!public_json.contains("freshness"));
    assert!(public_json.contains("The task could not be completed."));
    assert!(public_json.contains("Review the task inputs and retry."));
    fs::remove_dir_all(root).unwrap();
}

fn terminal_count(snapshot: &TaskSnapshotV1) -> usize {
    snapshot
        .status_history
        .iter()
        .filter(|status| status.is_terminal())
        .count()
}

#[test]
fn fast_success_rebuilds_contiguous_historical_updates_and_paginates() {
    let root = temp_root("fast-updates");
    let manager = TaskManager::with_executor(Arc::new(ImmediateSuccessExecutor));
    let task = manager.start(request(), invocation(root.clone())).unwrap();
    wait_terminal(&manager, &task.task_id);
    let updates = manager.public_updates_since(&task.task_id, 0).unwrap();
    assert_eq!(
        updates
            .iter()
            .map(|update| update.sequence)
            .collect::<Vec<_>>(),
        vec![1, 2, 3, 4]
    );
    assert_eq!(
        updates
            .iter()
            .map(|update| update.task.status)
            .collect::<Vec<_>>(),
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Committing,
            TaskStatusV1::Succeeded,
        ]
    );
    for (index, update) in updates.iter().enumerate() {
        assert_eq!(update.task.status_history.len(), index + 1);
        assert_eq!(update.task.status_history.last(), Some(&update.task.status));
        assert!(update.task.failure.is_none());
        if update.task.status == TaskStatusV1::Succeeded {
            assert_eq!(update.task.artifacts.len(), 1);
        } else {
            assert!(update.task.artifacts.is_empty());
        }
    }
    let paged = manager.public_updates_since(&task.task_id, 2).unwrap();
    assert_eq!(
        paged
            .iter()
            .map(|update| update.sequence)
            .collect::<Vec<_>>(),
        vec![3, 4]
    );
    assert!(manager.public_updates_since("missing", 0).is_none());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn success_sequence_rejects_global_concurrency_and_commit_cancel_is_too_late() {
    let root = temp_root("success");
    let output = root.join("output.md");
    let harness = controlled_manager(output.clone());
    let queued = harness
        .manager
        .start(request(), invocation(root.clone()))
        .unwrap();
    assert_eq!(queued.status, TaskStatusV1::Queued);
    assert_eq!(queued.status_history, vec![TaskStatusV1::Queued]);

    harness.pre_commit_reached.recv().unwrap();
    let running = harness.manager.get(&queued.task_id).unwrap();
    assert_eq!(running.status, TaskStatusV1::Running);
    assert_eq!(
        running.status_history,
        vec![TaskStatusV1::Queued, TaskStatusV1::Running]
    );
    assert!(matches!(
        harness.manager.start(request(), invocation(root.clone())),
        Err(TaskManagerError::Busy { .. })
    ));
    let different_operation = TaskRequestV1::new(
        WorkspaceLayout {
            data_dir: PathBuf::from("other-data"),
            box_path: PathBuf::from("other-box.json"),
        },
        TaskSpecV1::ReviewPacket(PullTaskV1::default()),
    );
    assert!(matches!(
        harness
            .manager
            .start(different_operation, invocation(root.clone())),
        Err(TaskManagerError::Busy { .. })
    ));

    harness.release_pre_commit.send(()).unwrap();
    harness.committing_reached.recv().unwrap();
    let cancel = harness.manager.cancel(&queued.task_id);
    assert_eq!(cancel.outcome, CancelOutcomeV1::TooLate);
    assert_eq!(cancel.snapshot.unwrap().status, TaskStatusV1::Committing);
    harness.release_commit.send(()).unwrap();

    let succeeded = wait_terminal(&harness.manager, &queued.task_id);
    assert_eq!(
        succeeded.status_history,
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Committing,
            TaskStatusV1::Succeeded,
        ]
    );
    assert_eq!(terminal_count(&succeeded), 1);
    assert!(succeeded.receipt.is_some());
    assert!(succeeded.failure.is_none());
    assert_eq!(fs::read(&output).unwrap(), b"committed");
    assert_eq!(harness.manager.list(), vec![succeeded.clone()]);

    let public = harness.manager.get_public(&queued.task_id).unwrap();
    assert_eq!(public.artifacts.len(), 0);
    assert_eq!(harness.manager.list_public(), vec![public.clone()]);
    let mut serialized = serde_json::to_value(&public).unwrap();
    serialized["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<PublicTaskSnapshotV1>(serialized).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn cancel_before_commit_reaches_cancelled_without_creating_output() {
    let root = temp_root("cancel");
    let output = root.join("must-not-exist.md");
    let harness = controlled_manager(output.clone());
    let queued = harness
        .manager
        .start(request(), invocation(root.clone()))
        .unwrap();
    harness.pre_commit_reached.recv().unwrap();

    let cancellation = harness.manager.cancel(&queued.task_id);
    assert_eq!(cancellation.outcome, CancelOutcomeV1::Requested);
    assert_eq!(
        cancellation.snapshot.unwrap().status,
        TaskStatusV1::Cancelling
    );
    harness.release_pre_commit.send(()).unwrap();

    let cancelled = wait_terminal(&harness.manager, &queued.task_id);
    assert_eq!(
        cancelled.status_history,
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Cancelling,
            TaskStatusV1::Cancelled,
        ]
    );
    assert_eq!(terminal_count(&cancelled), 1);
    assert!(cancelled.receipt.is_none());
    assert!(cancelled.failure.is_none());
    assert!(!output.exists());
    let updates = harness
        .manager
        .public_updates_since(&queued.task_id, 0)
        .unwrap();
    assert_eq!(
        updates
            .iter()
            .map(|update| update.task.status)
            .collect::<Vec<_>>(),
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Cancelling,
            TaskStatusV1::Cancelled,
        ]
    );
    assert_eq!(
        updates
            .iter()
            .map(|update| update.task.cancellation_requested)
            .collect::<Vec<_>>(),
        vec![false, false, true, true]
    );
    assert!(updates
        .iter()
        .all(|update| update.task.artifacts.is_empty() && update.task.failure.is_none()));
    assert_eq!(
        harness.manager.cancel(&queued.task_id).outcome,
        CancelOutcomeV1::AlreadyTerminal
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn cancel_before_commit_preserves_an_existing_output_byte_for_byte() {
    let root = temp_root("cancel-old-output");
    let output = root.join("existing.md");
    fs::write(&output, b"old-output").unwrap();
    let harness = controlled_manager(output.clone());
    let queued = harness
        .manager
        .start(request(), invocation(root.clone()))
        .unwrap();
    harness.pre_commit_reached.recv().unwrap();
    assert_eq!(
        harness.manager.cancel(&queued.task_id).outcome,
        CancelOutcomeV1::Requested
    );
    harness.release_pre_commit.send(()).unwrap();
    let cancelled = wait_terminal(&harness.manager, &queued.task_id);
    assert_eq!(cancelled.status, TaskStatusV1::Cancelled);
    assert_eq!(fs::read(&output).unwrap(), b"old-output");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn executor_failure_has_one_failed_terminal_and_list_recovers_it() {
    let root = temp_root("failure");
    let manager = TaskManager::with_executor(Arc::new(FailingExecutor));
    let queued = manager.start(request(), invocation(root.clone())).unwrap();
    let failed = wait_terminal(&manager, &queued.task_id);
    assert_eq!(
        failed.status_history,
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Failed,
        ]
    );
    assert_eq!(terminal_count(&failed), 1);
    assert!(failed.receipt.is_none());
    assert_eq!(failed.failure.as_ref().unwrap().code, "task.failed");
    assert_eq!(manager.get("missing"), None);
    assert_eq!(manager.cancel("missing").outcome, CancelOutcomeV1::NotFound);
    assert_eq!(manager.list(), vec![failed]);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn spawn_failure_rolls_back_active_and_queued_record() {
    let root = temp_root("spawn-failure");
    let manager = TaskManager::with_runtime(Arc::new(FailingExecutor), Arc::new(FailingSpawner));
    assert!(matches!(
        manager.start(request(), invocation(root.clone())),
        Err(TaskManagerError::SpawnFailed { .. })
    ));
    assert!(manager.list().is_empty());
    assert!(matches!(
        manager.start(request(), invocation(root.clone())),
        Err(TaskManagerError::SpawnFailed { .. })
    ));
    assert!(manager.list().is_empty());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn executor_panic_becomes_failed_and_manager_accepts_a_new_task() {
    let root = temp_root("panic");
    let manager = TaskManager::with_executor(Arc::new(PanickingExecutor));
    let first = manager.start(request(), invocation(root.clone())).unwrap();
    let first_failed = wait_terminal(&manager, &first.task_id);
    assert_eq!(first_failed.status, TaskStatusV1::Failed);
    assert_eq!(terminal_count(&first_failed), 1);
    assert_eq!(first_failed.failure.as_ref().unwrap().code, "task.panicked");

    let second = manager.start(request(), invocation(root.clone())).unwrap();
    assert_ne!(first.task_id, second.task_id);
    let second_failed = wait_terminal(&manager, &second.task_id);
    assert_eq!(second_failed.status, TaskStatusV1::Failed);
    assert_eq!(terminal_count(&second_failed), 1);
    assert_eq!(manager.list().len(), 2);

    let other_manager = TaskManager::with_executor(Arc::new(FailingExecutor));
    let other = other_manager
        .start(request(), invocation(root.clone()))
        .unwrap();
    assert_ne!(first.task_id, other.task_id);
    wait_terminal(&other_manager, &other.task_id);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn public_snapshot_omits_native_paths_and_raw_failure_details() {
    let succeeded_native = TaskSnapshotV1 {
        schema_version: TASK_SNAPSHOT_SCHEMA_V1.to_owned(),
        task_id: "task-safe".to_owned(),
        operation: TaskOperationV1::Evidence,
        status: TaskStatusV1::Succeeded,
        status_history: vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Committing,
            TaskStatusV1::Succeeded,
        ],
        cancellation_requested: false,
        receipt: Some(TaskReceiptV1 {
            schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
            operation: TaskOperationV1::Evidence,
            method_version: "method".to_owned(),
            output_schema: "schema".to_owned(),
            local_datetime: "2026-07-13T09:10:11".to_owned(),
            outputs: vec![PathBuf::from("C:/CANARY_ROOT/CANARY_FILE.md")],
            notices: Vec::new(),
            freshness: Some(freshness()),
        }),
        failure: None,
    };
    let public = succeeded_native.to_public();
    assert_eq!(public.artifacts.len(), 1);
    assert_eq!(public.artifacts[0].name, "evidence_pool_summary.md");
    assert!(public.freshness.is_none());
    let succeeded_json = serde_json::to_string(&public).unwrap();

    let failed_native = TaskSnapshotV1 {
        schema_version: TASK_SNAPSHOT_SCHEMA_V1.to_owned(),
        task_id: "task-failed-safe".to_owned(),
        operation: TaskOperationV1::Evidence,
        status: TaskStatusV1::Failed,
        status_history: vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Failed,
        ],
        cancellation_requested: false,
        receipt: None,
        failure: Some(TaskFailureV1 {
            schema_version: TASK_FAILURE_SCHEMA_V1.to_owned(),
            operation: Some(TaskOperationV1::Evidence),
            code: "task.failed".to_owned(),
            message: "CANARY_RAW_ERROR_PATH".to_owned(),
            retryable: false,
        }),
    };
    let failed_public = failed_native.to_public();
    assert!(failed_public.artifacts.is_empty());
    assert!(failed_public.failure.is_some());
    let failed_json = serde_json::to_string(&failed_public).unwrap();
    for canary in ["CANARY_ROOT", "CANARY_FILE", "CANARY_RAW_ERROR_PATH"] {
        assert!(
            !succeeded_json.contains(canary) && !failed_json.contains(canary),
            "{canary} leaked into public snapshot"
        );
    }
}

#[test]
fn cancelled_observer_keeps_active_owned_until_worker_finalizes() {
    let root = temp_root("active-owner");
    let (pre_tx, pre_rx) = mpsc::channel();
    let (release_pre_tx, release_pre_rx) = mpsc::channel();
    let (returned_tx, returned_rx) = mpsc::channel();
    let (release_return_tx, release_return_rx) = mpsc::channel();
    let manager = TaskManager::with_executor(Arc::new(ObserverHoldExecutor {
        pre_commit_reached: pre_tx,
        release_pre_commit: Mutex::new(release_pre_rx),
        observer_returned: returned_tx,
        release_executor_return: Mutex::new(release_return_rx),
    }));

    let task_a = manager.start(request(), invocation(root.clone())).unwrap();
    pre_rx.recv().unwrap();
    assert_eq!(
        manager.cancel(&task_a.task_id).outcome,
        CancelOutcomeV1::Requested
    );
    release_pre_tx.send(()).unwrap();
    returned_rx.recv().unwrap();
    assert_eq!(
        manager.get(&task_a.task_id).unwrap().status,
        TaskStatusV1::Cancelled
    );
    assert!(matches!(
        manager.start(request(), invocation(root.clone())),
        Err(TaskManagerError::Busy { .. })
    ));

    release_return_tx.send(()).unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    let task_b = loop {
        match manager.start(request(), invocation(root.clone())) {
            Ok(task) => break task,
            Err(TaskManagerError::Busy { .. }) => {
                assert!(
                    Instant::now() < deadline,
                    "task A did not release active ownership"
                );
                thread::sleep(Duration::from_millis(5));
            }
            Err(error) => panic!("unexpected start error: {error}"),
        }
    };
    pre_rx.recv().unwrap();
    assert!(matches!(
        manager.start(request(), invocation(root.clone())),
        Err(TaskManagerError::Busy { active_task_id }) if active_task_id == task_b.task_id
    ));
    release_pre_tx.send(()).unwrap();
    returned_rx.recv().unwrap();
    assert_eq!(
        manager.get(&task_b.task_id).unwrap().status,
        TaskStatusV1::Committing
    );
    assert!(matches!(
        manager.start(request(), invocation(root.clone())),
        Err(TaskManagerError::Busy { active_task_id }) if active_task_id == task_b.task_id
    ));
    release_return_tx.send(()).unwrap();
    assert_eq!(
        wait_terminal(&manager, &task_b.task_id).status,
        TaskStatusV1::Succeeded
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn ordinary_executor_error_after_cancel_request_is_failed_not_cancelled() {
    let root = temp_root("cancel-race-error");
    let (entered_tx, entered_rx) = mpsc::channel();
    let (release_tx, release_rx) = mpsc::channel();
    let manager = TaskManager::with_executor(Arc::new(OrdinaryFailureAfterCancelExecutor {
        entered: entered_tx,
        release: Mutex::new(release_rx),
    }));
    let task = manager.start(request(), invocation(root.clone())).unwrap();
    entered_rx.recv().unwrap();
    assert_eq!(
        manager.cancel(&task.task_id).outcome,
        CancelOutcomeV1::Requested
    );
    release_tx.send(()).unwrap();
    let failed = wait_terminal(&manager, &task.task_id);
    assert_eq!(failed.status, TaskStatusV1::Failed);
    assert_eq!(
        failed.status_history,
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Cancelling,
            TaskStatusV1::Failed,
        ]
    );
    assert_eq!(terminal_count(&failed), 1);
    let updates = manager.public_updates_since(&task.task_id, 0).unwrap();
    assert_eq!(
        updates
            .iter()
            .map(|update| update.task.status)
            .collect::<Vec<_>>(),
        vec![
            TaskStatusV1::Queued,
            TaskStatusV1::Running,
            TaskStatusV1::Cancelling,
            TaskStatusV1::Failed,
        ]
    );
    assert!(updates[2].task.failure.is_none());
    assert!(updates[2].task.cancellation_requested);
    assert!(updates[3].task.failure.is_some());
    assert!(updates[3].task.cancellation_requested);
    assert_eq!(failed.failure.unwrap().code, "task.failed");
    fs::remove_dir_all(root).unwrap();
}
