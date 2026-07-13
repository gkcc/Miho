use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
};

use chrono::{FixedOffset, TimeZone, Timelike};
use miho_app::{
    check_update_health_v1, export_cache_root, run_update_v1, FileUpdateReceiptStore,
    NativeUpdateExecutorV1, UpdateArtifactV1, UpdateConfigV1, UpdateInvocationV1,
    UpdateReceiptStore, UpdateReceiptV1, UpdateRequestV1, UpdateRunStatusV1, UpdateStateV1,
    UpdateStepContextV1, UpdateStepExecutor, UpdateStepFailureV1, UpdateStepFuture,
    UpdateStepKindV1, UpdateStepStatusV1, WorkspaceWriteLease, UPDATE_ATTEMPT_DIRECTORY,
    UPDATE_CANONICAL_RECEIPT_FILE, UPDATE_STATE_FILE,
};
use miho_core::contract::Game;
use sha2::{Digest, Sha256};

#[derive(Clone, Default)]
struct FakeExecutor {
    failures: Arc<Mutex<BTreeSet<UpdateStepKindV1>>>,
    observed: Arc<Mutex<Vec<(UpdateStepKindV1, String, String)>>>,
    unsafe_step: Arc<Mutex<Option<UpdateStepKindV1>>>,
}

impl FakeExecutor {
    fn failing(step: UpdateStepKindV1) -> Self {
        let this = Self::default();
        this.failures.lock().unwrap().insert(step);
        this
    }
}

impl UpdateStepExecutor for FakeExecutor {
    fn execute<'a>(
        &'a self,
        step: UpdateStepKindV1,
        context: &'a UpdateStepContextV1,
    ) -> UpdateStepFuture<'a> {
        Box::pin(async move {
            self.observed.lock().unwrap().push((
                step,
                context.attempt_id.clone(),
                context
                    .local_datetime()
                    .format("%Y-%m-%dT%H:%M:%S%.6f")
                    .to_string(),
            ));
            if self.failures.lock().unwrap().contains(&step) {
                return Err(UpdateStepFailureV1::safe(
                    format!("step.{}.failed", step_name(step)),
                    "the injected step failed",
                    true,
                ));
            }
            if *self.unsafe_step.lock().unwrap() == Some(step) {
                return Ok(vec![UpdateArtifactV1 {
                    path: context.workspace.join("outside.txt"),
                    bytes: 0,
                    sha256: "0".repeat(64),
                }]);
            }
            let relative = PathBuf::from("generated").join(format!("{}.txt", step_name(step)));
            let path = context.workspace.join(&relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            let bytes = format!("{}:{}\n", context.attempt_id, step_name(step)).into_bytes();
            fs::write(&path, &bytes).unwrap();
            Ok(vec![UpdateArtifactV1 {
                path: relative,
                bytes: bytes.len() as u64,
                sha256: format!("{:x}", Sha256::digest(&bytes)),
            }])
        })
    }
}

struct FailSuccessStore {
    inner: FileUpdateReceiptStore,
}

struct FailFailureStore {
    inner: FileUpdateReceiptStore,
}

struct LeaveRunningStore {
    inner: FileUpdateReceiptStore,
}

impl UpdateReceiptStore for LeaveRunningStore {
    fn load_state(&self, workspace: &Path) -> Result<UpdateStateV1, UpdateStepFailureV1> {
        self.inner.load_state(workspace)
    }

    fn write_running(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.write_running(workspace, receipt)?;
        Err(UpdateStepFailureV1::safe(
            "test.abrupt_stop",
            "injected stop after running receipt",
            true,
        ))
    }

    fn commit_success(
        &self,
        workspace: &Path,
        state: &UpdateStateV1,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.commit_success(workspace, state, receipt)
    }

    fn commit_failure(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.commit_failure(workspace, receipt)
    }
}

impl UpdateReceiptStore for FailSuccessStore {
    fn load_state(&self, workspace: &Path) -> Result<UpdateStateV1, UpdateStepFailureV1> {
        self.inner.load_state(workspace)
    }

    fn write_running(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.write_running(workspace, receipt)
    }

    fn commit_success(
        &self,
        _workspace: &Path,
        _state: &UpdateStateV1,
        _receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        Err(UpdateStepFailureV1::safe(
            "update.state_commit_failed",
            "the update success state could not be committed",
            true,
        ))
    }

    fn commit_failure(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.commit_failure(workspace, receipt)
    }
}

impl UpdateReceiptStore for FailFailureStore {
    fn load_state(&self, workspace: &Path) -> Result<UpdateStateV1, UpdateStepFailureV1> {
        self.inner.load_state(workspace)
    }

    fn write_running(
        &self,
        workspace: &Path,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.write_running(workspace, receipt)
    }

    fn commit_success(
        &self,
        workspace: &Path,
        state: &UpdateStateV1,
        receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        self.inner.commit_success(workspace, state, receipt)
    }

    fn commit_failure(
        &self,
        _workspace: &Path,
        _receipt: &UpdateReceiptV1,
    ) -> Result<(), UpdateStepFailureV1> {
        Err(UpdateStepFailureV1::safe(
            "update.receipt_write_failed",
            "the update receipt could not be committed",
            true,
        ))
    }
}

#[tokio::test]
async fn full_success_commits_state_and_canonical_receipt_last() {
    let root = temp_root("success");
    let invocation = invocation();
    let executor = FakeExecutor::default();
    let outcome = run_update_v1(
        &request(&root),
        &invocation,
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.exit_code, 0);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Succeeded);
    assert!(outcome.receipt.state_committed);
    assert!(outcome.receipt.receipt_committed);
    assert!(outcome
        .receipt
        .games
        .iter()
        .all(|game| game.status == UpdateStepStatusV1::Succeeded));

    let state = read_json::<UpdateStateV1>(&root.join(".miho").join(UPDATE_STATE_FILE));
    assert_eq!(state.games.len(), 2);
    assert!(state
        .games
        .values()
        .all(|game| game.attempt_id == invocation.attempt_id));
    let canonical =
        read_json::<UpdateReceiptV1>(&root.join(".miho").join(UPDATE_CANONICAL_RECEIPT_FILE));
    assert_eq!(canonical, outcome.receipt);

    let observed = executor.observed.lock().unwrap();
    assert_eq!(observed.len(), 5);
    assert!(observed.iter().all(|(_, attempt, local)| {
        attempt == &invocation.attempt_id && local == "2026-07-13T09:30:00.123456"
    }));
    cleanup(&root);
}

#[tokio::test]
async fn health_binds_each_split_generation_receipt_to_the_expected_config() {
    let root = temp_root("generation-config-binding");
    let executor = FakeExecutor::default();
    let mut hsr_request = request(&root);
    hsr_request.skip_zzz = true;
    let hsr_invocation = invocation_with("attempt-config-hsr", 31);
    assert_eq!(
        run_update_v1(
            &hsr_request,
            &hsr_invocation,
            &executor,
            &FileUpdateReceiptStore,
        )
        .await
        .exit_code,
        0
    );

    let mut zzz_request = request(&root);
    zzz_request.skip_hsr = true;
    let zzz_invocation = invocation_with("attempt-config-zzz", 32);
    assert_eq!(
        run_update_v1(
            &zzz_request,
            &zzz_invocation,
            &executor,
            &FileUpdateReceiptStore,
        )
        .await
        .exit_code,
        0
    );
    assert!(check_update_health_v1(&root, true, true, &"a".repeat(64)).healthy);

    // Forge the mutable state and latest (ZZZ) canonical generation to claim
    // config B. The older HSR generation receipt still truthfully records A;
    // health must bind that history entry instead of trusting state alone.
    let forged_digest = "b".repeat(64);
    let state_path = root.join(".miho").join(UPDATE_STATE_FILE);
    let mut state = read_json::<UpdateStateV1>(&state_path);
    for game in state.games.values_mut() {
        game.config_sha256 = forged_digest.clone();
    }
    fs::write(&state_path, serde_json::to_vec_pretty(&state).unwrap()).unwrap();

    let canonical_path = root.join(".miho").join(UPDATE_CANONICAL_RECEIPT_FILE);
    let mut canonical = read_json::<UpdateReceiptV1>(&canonical_path);
    canonical.config_sha256 = Some(forged_digest.clone());
    let canonical_bytes = serde_json::to_vec_pretty(&canonical).unwrap();
    fs::write(&canonical_path, &canonical_bytes).unwrap();
    fs::write(
        root.join(".miho")
            .join(UPDATE_ATTEMPT_DIRECTORY)
            .join(format!("{}.json", canonical.attempt_id)),
        canonical_bytes,
    )
    .unwrap();

    let health = check_update_health_v1(&root, true, true, &forged_digest);
    assert!(!health.healthy);
    assert_eq!(
        health.failure.as_ref().map(|failure| failure.code.as_str()),
        Some("update.health_generation_mismatch")
    );
    cleanup(&root);
}

#[tokio::test]
async fn native_executor_rejects_hf_cache_fallback_and_does_not_advance_state() {
    use std::{
        io::{Read, Write},
        net::TcpListener,
        sync::{
            atomic::{AtomicBool, AtomicUsize, Ordering},
            Arc,
        },
        thread,
        time::Duration as StdDuration,
    };

    let root = temp_root("hf-fallback-not-fresh");
    fs::create_dir_all(root.join(".miho")).unwrap();
    let sentinel = UpdateStateV1::default();
    let state_path = root.join(".miho").join(UPDATE_STATE_FILE);
    let sentinel_bytes = serde_json::to_vec_pretty(&sentinel).unwrap();
    fs::write(&state_path, &sentinel_bytes).unwrap();

    let repo_id = "owner/hf-freshness-fixture";
    let revision = "main";
    let cache_root =
        export_cache_root(&root.join(".miho/cache/rust"), Game::Hsr, repo_id, revision);
    fs::create_dir_all(cache_root.join(".trees")).unwrap();
    fs::write(
        cache_root.join(".trees/root.json"),
        br#"[{"type":"directory","path":"1.0.0"}]"#,
    )
    .unwrap();

    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let origin = format!("http://{}", listener.local_addr().unwrap());
    let stop = Arc::new(AtomicBool::new(false));
    let request_count = Arc::new(AtomicUsize::new(0));
    let server_stop = stop.clone();
    let server_count = request_count.clone();
    let server = thread::spawn(move || {
        while !server_stop.load(Ordering::Acquire) {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    server_count.fetch_add(1, Ordering::Relaxed);
                    let mut request = [0_u8; 2048];
                    let _ = stream.read(&mut request);
                    stream
                        .write_all(
                            b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                        )
                        .unwrap();
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(StdDuration::from_millis(2));
                }
                Err(error) => panic!("freshness test server failed: {error}"),
            }
        }
    });

    let config = UpdateConfigV1::parse(
        format!(
            r#"{{
  "schema_version":"miho-update-config-v1",
  "days":183,
  "hsr":{{"output":"out","repo_id":"{repo_id}","revision":"{revision}","modes":["moc"],"prydwen_top_n":100}},
  "zzz":{{"output":"out_zzz","repo_id":"owner/zzz","revision":"main","modes":["sd"],"prydwen_top_n":100,"box":".miho/zzz_box_state.json","banner_plan":"configs/zzz_banner_plan.json","mechanism_notes":"configs/zzz_mechanism_notes","decision_baseline":"configs/zzz_decision_baseline.json"}}
}}"#
        )
        .as_bytes(),
    )
    .unwrap()
    .resolve(&root)
    .unwrap();
    let executor = NativeUpdateExecutorV1::new(config).with_hf_origin(Game::Hsr, origin);
    let mut update_request = request(&root);
    update_request.skip_zzz = true;
    let outcome = run_update_v1(
        &update_request,
        &invocation_with("attempt-hf-cache-fallback", 33),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;
    stop.store(true, Ordering::Release);
    server.join().unwrap();

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(
        request_count.load(Ordering::Relaxed),
        3,
        "strict freshness must stop after the retried root request; a permissive fallback would continue to config/tree requests"
    );
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Failed);
    assert!(!outcome.receipt.state_committed);
    assert!(outcome.receipt.receipt_committed);
    assert_eq!(outcome.receipt.games[0].status, UpdateStepStatusV1::Failed);
    assert_eq!(
        outcome.receipt.games[0].steps[0]
            .failure
            .as_ref()
            .map(|failure| failure.code.as_str()),
        Some("update.hsr_export.failed")
    );
    assert_eq!(fs::read(&state_path).unwrap(), sentinel_bytes);
    let canonical =
        read_json::<UpdateReceiptV1>(&root.join(".miho").join(UPDATE_CANONICAL_RECEIPT_FILE));
    assert_eq!(canonical, outcome.receipt);
    cleanup(&root);
}

#[tokio::test]
async fn hsr_failure_still_runs_zzz_but_does_not_advance_success_state() {
    let root = temp_root("hsr-fail");
    let sentinel = UpdateStateV1 {
        schema_version: miho_app::UPDATE_STATE_SCHEMA_V1.to_owned(),
        games: BTreeMap::new(),
    };
    fs::create_dir_all(root.join(".miho")).unwrap();
    fs::write(
        root.join(".miho").join(UPDATE_STATE_FILE),
        serde_json::to_vec_pretty(&sentinel).unwrap(),
    )
    .unwrap();
    let executor = FakeExecutor::failing(UpdateStepKindV1::HsrExport);
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Partial);
    assert_eq!(outcome.receipt.games[0].status, UpdateStepStatusV1::Failed);
    assert_eq!(
        outcome.receipt.games[1].status,
        UpdateStepStatusV1::Succeeded
    );
    assert_eq!(
        read_json::<UpdateStateV1>(&root.join(".miho").join(UPDATE_STATE_FILE)),
        sentinel
    );
    cleanup(&root);
}

#[tokio::test]
async fn zzz_export_failure_skips_all_derived_steps_and_keeps_state() {
    let root = temp_root("zzz-export-fail");
    let executor = FakeExecutor::failing(UpdateStepKindV1::ZzzExport);
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Partial);
    assert_eq!(
        outcome.receipt.games[0].status,
        UpdateStepStatusV1::Succeeded
    );
    assert_eq!(
        outcome.receipt.games[1].steps[0].status,
        UpdateStepStatusV1::Failed
    );
    assert!(outcome.receipt.games[1].steps[1..]
        .iter()
        .all(|step| step.status == UpdateStepStatusV1::Skipped));
    assert!(!root.join(".miho").join(UPDATE_STATE_FILE).exists());
    cleanup(&root);
}

#[tokio::test]
async fn derived_failure_stops_later_steps_and_cannot_be_false_green() {
    let root = temp_root("derived-fail");
    let executor = FakeExecutor::failing(UpdateStepKindV1::ZzzPullValue);
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Partial);
    assert_eq!(
        outcome.receipt.games[1].steps[2].status,
        UpdateStepStatusV1::Failed
    );
    assert_eq!(
        outcome.receipt.games[1].steps[3].status,
        UpdateStepStatusV1::Skipped
    );
    assert!(!root.join(".miho").join(UPDATE_STATE_FILE).exists());
    cleanup(&root);
}

#[tokio::test]
async fn coverage_failure_stops_pull_and_review_and_cannot_be_false_green() {
    let root = temp_root("coverage-fail");
    let executor = FakeExecutor::failing(UpdateStepKindV1::ZzzCoverage);
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Partial);
    assert_eq!(
        outcome.receipt.games[1].steps[1].status,
        UpdateStepStatusV1::Failed
    );
    assert!(outcome.receipt.games[1].steps[2..]
        .iter()
        .all(|step| step.status == UpdateStepStatusV1::Skipped));
    assert!(!root.join(".miho").join(UPDATE_STATE_FILE).exists());
    cleanup(&root);
}

#[tokio::test]
async fn review_packet_failure_is_terminal_and_cannot_be_false_green() {
    let root = temp_root("review-fail");
    let executor = FakeExecutor::failing(UpdateStepKindV1::ZzzReviewPacket);
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Partial);
    assert!(outcome.receipt.games[1].steps[..3]
        .iter()
        .all(|step| step.status == UpdateStepStatusV1::Succeeded));
    assert_eq!(
        outcome.receipt.games[1].steps[3].status,
        UpdateStepStatusV1::Failed
    );
    assert!(!root.join(".miho").join(UPDATE_STATE_FILE).exists());
    cleanup(&root);
}

#[tokio::test]
async fn state_batch_failure_is_exit_one_and_cannot_advance_state() {
    let root = temp_root("state-fail");
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &FakeExecutor::default(),
        &FailSuccessStore {
            inner: FileUpdateReceiptStore,
        },
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Failed);
    assert!(!outcome.receipt.state_committed);
    assert!(outcome.receipt.receipt_committed);
    assert_eq!(
        outcome.receipt.failure.as_ref().unwrap().code,
        "update.state_commit_failed"
    );
    assert!(!root.join(".miho").join(UPDATE_STATE_FILE).exists());
    cleanup(&root);
}

#[tokio::test]
async fn failure_receipt_commit_failure_is_exit_one_and_leaves_running_evidence() {
    let root = temp_root("failure-receipt-fail");
    let attempt = invocation();
    let outcome = run_update_v1(
        &request(&root),
        &attempt,
        &FakeExecutor::failing(UpdateStepKindV1::HsrExport),
        &FailFailureStore {
            inner: FileUpdateReceiptStore,
        },
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(outcome.receipt.status, UpdateRunStatusV1::Partial);
    assert!(!outcome.receipt.state_committed);
    assert!(!outcome.receipt.receipt_committed);
    assert_eq!(
        outcome.receipt.failure.as_ref().unwrap().code,
        "update.receipt_write_failed"
    );
    assert!(!root.join(".miho").join(UPDATE_STATE_FILE).exists());
    assert!(!root
        .join(".miho")
        .join(UPDATE_CANONICAL_RECEIPT_FILE)
        .exists());
    let running = root
        .join(".miho/update-attempts")
        .join(format!("{}.json", attempt.attempt_id));
    assert_eq!(
        read_json::<UpdateReceiptV1>(&running).status,
        UpdateRunStatusV1::Running
    );
    cleanup(&root);
}

#[tokio::test]
async fn busy_contender_does_not_replace_canonical_receipt() {
    let root = temp_root("busy");
    fs::create_dir_all(root.join(".miho")).unwrap();
    let canonical = root.join(".miho").join(UPDATE_CANONICAL_RECEIPT_FILE);
    fs::write(&canonical, b"sentinel").unwrap();
    let lease = WorkspaceWriteLease::acquire(&root).unwrap();

    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &FakeExecutor::default(),
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(outcome.exit_code, 1);
    assert_eq!(
        outcome.receipt.failure.as_ref().unwrap().code,
        "workspace.write_busy"
    );
    assert_eq!(fs::read(&canonical).unwrap(), b"sentinel");
    drop(lease);
    cleanup(&root);
}

#[tokio::test]
async fn next_lock_owner_marks_a_leftover_running_attempt_interrupted() {
    let root = temp_root("interrupted");
    let first = invocation();
    let stopped = run_update_v1(
        &request(&root),
        &first,
        &FakeExecutor::default(),
        &LeaveRunningStore {
            inner: FileUpdateReceiptStore,
        },
    )
    .await;
    assert_eq!(stopped.exit_code, 1);
    let old_path = root
        .join(".miho/update-attempts")
        .join(format!("{}.json", first.attempt_id));
    assert_eq!(
        read_json::<UpdateReceiptV1>(&old_path).status,
        UpdateRunStatusV1::Running
    );

    let second = UpdateInvocationV1::new(
        "attempt-test-2".to_owned(),
        FixedOffset::east_opt(8 * 60 * 60)
            .unwrap()
            .with_ymd_and_hms(2026, 7, 13, 9, 31, 0)
            .single()
            .unwrap(),
    )
    .unwrap();
    let completed = run_update_v1(
        &request(&root),
        &second,
        &FakeExecutor::default(),
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(completed.exit_code, 0);
    let interrupted = read_json::<UpdateReceiptV1>(&old_path);
    assert_eq!(interrupted.status, UpdateRunStatusV1::Interrupted);
    assert!(!interrupted.receipt_committed);
    assert_eq!(interrupted.failure.unwrap().code, "update.interrupted");
    cleanup(&root);
}

#[tokio::test]
async fn unsafe_or_missing_artifact_turns_step_into_failure() {
    let root = temp_root("unsafe-artifact");
    let executor = FakeExecutor::default();
    *executor.unsafe_step.lock().unwrap() = Some(UpdateStepKindV1::HsrExport);
    let outcome = run_update_v1(
        &request(&root),
        &invocation(),
        &executor,
        &FileUpdateReceiptStore,
    )
    .await;

    assert_eq!(outcome.exit_code, 1);
    assert_eq!(
        outcome.receipt.games[0].steps[0]
            .failure
            .as_ref()
            .unwrap()
            .code,
        "update.artifact_path_unsafe"
    );
    cleanup(&root);
}

#[tokio::test]
async fn skip_is_explicit_and_both_skipped_is_invalid() {
    let root = temp_root("skip");
    let mut hsr_skipped = request(&root);
    hsr_skipped.skip_hsr = true;
    let zzz_only_executor = FakeExecutor::default();
    let zzz_only = run_update_v1(
        &hsr_skipped,
        &invocation(),
        &zzz_only_executor,
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(zzz_only.exit_code, 0);
    assert_eq!(
        zzz_only.receipt.games[0].status,
        UpdateStepStatusV1::Skipped
    );
    assert!(zzz_only_executor
        .observed
        .lock()
        .unwrap()
        .iter()
        .all(|(step, _, _)| step.game() == miho_core::contract::Game::Zzz));

    let mut zzz_skipped = request(&root);
    zzz_skipped.skip_zzz = true;
    let hsr_only_executor = FakeExecutor::default();
    let hsr_only = run_update_v1(
        &zzz_skipped,
        &invocation_with("attempt-hsr-only", 31),
        &hsr_only_executor,
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(hsr_only.exit_code, 0);
    assert_eq!(
        hsr_only.receipt.games[1].status,
        UpdateStepStatusV1::Skipped
    );
    assert_eq!(
        hsr_only_executor.observed.lock().unwrap()[0].0,
        UpdateStepKindV1::HsrExport
    );
    assert_eq!(hsr_only_executor.observed.lock().unwrap().len(), 1);

    let mut neither = request(&root);
    neither.skip_hsr = true;
    neither.skip_zzz = true;
    let invalid = run_update_v1(
        &neither,
        &invocation_with("attempt-neither", 32),
        &FakeExecutor::default(),
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(invalid.exit_code, 1);
    assert_eq!(
        invalid.receipt.failure.as_ref().unwrap().code,
        "update.no_games_selected"
    );
    cleanup(&root);
}

#[tokio::test]
async fn successful_state_never_skips_refresh_and_force_is_recorded_only_as_audit_input() {
    let root = temp_root("always-refresh");
    let first_executor = FakeExecutor::default();
    let first = run_update_v1(
        &request(&root),
        &invocation(),
        &first_executor,
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(first.exit_code, 0);
    assert_eq!(first_executor.observed.lock().unwrap().len(), 5);

    let second_executor = FakeExecutor::default();
    let second = run_update_v1(
        &request(&root),
        &invocation_with("attempt-refresh-without-force", 31),
        &second_executor,
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(second.exit_code, 0);
    assert!(!second.receipt.force);
    assert_eq!(second_executor.observed.lock().unwrap().len(), 5);

    let mut forced_request = request(&root);
    forced_request.force = true;
    let forced_executor = FakeExecutor::default();
    let forced = run_update_v1(
        &forced_request,
        &invocation_with("attempt-refresh-with-force", 32),
        &forced_executor,
        &FileUpdateReceiptStore,
    )
    .await;
    assert_eq!(forced.exit_code, 0);
    assert!(forced.receipt.force);
    assert_eq!(forced_executor.observed.lock().unwrap().len(), 5);

    let state = read_json::<UpdateStateV1>(&root.join(".miho").join(UPDATE_STATE_FILE));
    assert!(state
        .games
        .values()
        .all(|game| game.attempt_id == "attempt-refresh-with-force"));
    cleanup(&root);
}

fn request(root: &Path) -> UpdateRequestV1 {
    UpdateRequestV1 {
        workspace: root.to_path_buf(),
        skip_hsr: false,
        skip_zzz: false,
        force: false,
        config_sha256: Some("a".repeat(64)),
    }
}

fn invocation() -> UpdateInvocationV1 {
    invocation_with("attempt-test-1", 30)
}

fn invocation_with(attempt_id: &str, minute: u32) -> UpdateInvocationV1 {
    UpdateInvocationV1::new(
        attempt_id.to_owned(),
        FixedOffset::east_opt(8 * 60 * 60)
            .unwrap()
            .with_ymd_and_hms(2026, 7, 13, 9, minute, 0)
            .single()
            .unwrap()
            .with_nanosecond(123_456_000)
            .unwrap(),
    )
    .unwrap()
}

fn step_name(step: UpdateStepKindV1) -> &'static str {
    match step {
        UpdateStepKindV1::HsrExport => "hsr-export",
        UpdateStepKindV1::ZzzExport => "zzz-export",
        UpdateStepKindV1::ZzzCoverage => "zzz-coverage",
        UpdateStepKindV1::ZzzPullValue => "zzz-pull-value",
        UpdateStepKindV1::ZzzReviewPacket => "zzz-review-packet",
    }
}

fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> T {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn temp_root(label: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let id = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "miho-update-runner-{label}-{}-{id}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    root
}

fn cleanup(root: &Path) {
    let _ = fs::remove_dir_all(root);
}
