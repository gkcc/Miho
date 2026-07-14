use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};

use miho_app::{
    WorkspaceBootstrapCompletedOperationV1, WorkspaceBootstrapReceiptV1,
    WorkspaceBootstrapTransactionOperationV1, WorkspaceBootstrapTransactionReceiptV1,
    RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1, RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH,
    RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1, ZZZ_BOX_STATE_RELATIVE_PATH,
};

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

fn temp_root(label: &str) -> PathBuf {
    let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "miho-workspace-bootstrap-cli-{label}-{}-{id}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    root
}

fn cleanup(root: &Path) {
    fs::remove_dir_all(root).unwrap();
}

fn miho(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(args)
        .output()
        .unwrap()
}

#[test]
fn workspace_bootstrap_cli_installs_unicode_space_workspace_and_prints_pathless_receipt() {
    let parent = temp_root("parent");
    let root = parent.join("中文 workspace CANARY_USERNAME");
    fs::create_dir(&root).unwrap();

    let output = miho(&[
        "workspace",
        "bootstrap",
        "--workspace",
        root.to_str().unwrap(),
    ]);
    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(output.stderr.is_empty());
    let receipt: WorkspaceBootstrapReceiptV1 = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(receipt.schema_version, RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1);
    assert!(receipt.state_updated);
    assert!(root.join("configs/update_v1.json").is_file());
    assert!(root.join(ZZZ_BOX_STATE_RELATIVE_PATH).is_file());
    assert!(root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH).is_file());

    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(!stdout.contains(root.to_string_lossy().as_ref()));
    assert!(!stdout.contains("CANARY_USERNAME"));

    cleanup(&parent);
}

#[test]
fn workspace_bootstrap_cli_runtime_failure_exits_one_with_stable_code() {
    let parent = temp_root("missing");
    let missing = parent.join("does not exist CANARY_USERNAME");
    let output = miho(&[
        "workspace",
        "bootstrap",
        "--workspace",
        missing.to_str().unwrap(),
    ]);

    assert_eq!(output.status.code(), Some(1));
    assert!(output.stdout.is_empty());
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("workspace failed: workspace.write_unavailable"));
    assert!(!stderr.contains("CANARY_USERNAME"));
    assert!(!stderr.contains(missing.to_string_lossy().as_ref()));

    cleanup(&parent);
}

#[test]
fn workspace_bootstrap_cli_usage_failure_exits_two_without_mutation() {
    let root = temp_root("usage");
    let output = miho(&[
        "workspace",
        "bootstrap",
        "--workspace",
        root.to_str().unwrap(),
        "--unknown-option",
    ]);

    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("unexpected argument"));
    assert!(!root.join("configs/update_v1.json").exists());
    assert!(!root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH).exists());

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_transaction_cli_begin_verify_commit_finalize_is_pathless_and_exact() {
    let base = temp_root("transaction-commit-CANARY_USERNAME");
    let workspace = base.join("中文 workspace");
    let transaction = base.join("transaction evidence");
    fs::create_dir(&workspace).unwrap();
    let workspace_text = workspace.to_str().unwrap();
    let transaction_text = transaction.to_str().unwrap();

    let begin = miho(&[
        "workspace",
        "bootstrap-transaction",
        "begin",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
    ]);
    assert!(
        begin.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&begin.stderr)
    );
    assert!(begin.stderr.is_empty());
    let begin_receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&begin.stdout).unwrap();
    assert_eq!(
        begin_receipt.schema_version,
        RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1
    );
    assert_eq!(
        begin_receipt.operation,
        WorkspaceBootstrapTransactionOperationV1::Begin
    );
    assert_eq!(begin_receipt.files_verified, 12);

    let verify = miho(&[
        "workspace",
        "bootstrap-transaction",
        "verify",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
    ]);
    assert!(verify.status.success());
    let verify_receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&verify.stdout).unwrap();
    assert_eq!(
        verify_receipt.operation,
        WorkspaceBootstrapTransactionOperationV1::Verify
    );

    let commit = miho(&[
        "workspace",
        "bootstrap-transaction",
        "commit",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
    ]);
    assert!(
        commit.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&commit.stderr)
    );
    let commit_receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&commit.stdout).unwrap();
    assert_eq!(
        commit_receipt.operation,
        WorkspaceBootstrapTransactionOperationV1::Commit
    );
    assert_eq!(commit_receipt.files_removed, 0);
    assert!(commit_receipt.transaction_cleaned);
    assert!(!transaction.exists());

    let finalize = miho(&[
        "workspace",
        "bootstrap-transaction",
        "finalize",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
        "--completed-operation",
        "commit",
    ]);
    assert!(
        finalize.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&finalize.stderr)
    );
    let finalize_receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&finalize.stdout).unwrap();
    assert_eq!(
        finalize_receipt.operation,
        WorkspaceBootstrapTransactionOperationV1::Finalize
    );
    assert_eq!(
        finalize_receipt.completed_operation,
        Some(WorkspaceBootstrapCompletedOperationV1::Commit)
    );
    assert_eq!(finalize_receipt.files_verified, 12);
    assert_eq!(finalize_receipt.completion_marker_removed, Some(true));

    for output in [
        &begin.stdout,
        &verify.stdout,
        &commit.stdout,
        &finalize.stdout,
    ] {
        let text = String::from_utf8_lossy(output);
        assert!(!text.contains(base.to_string_lossy().as_ref()));
        assert!(!text.contains("CANARY_USERNAME"));
    }

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_cli_rollback_removes_fresh_allowlist() {
    let base = temp_root("transaction-rollback");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let workspace_text = workspace.to_str().unwrap();
    let transaction_text = transaction.to_str().unwrap();
    let begin = miho(&[
        "workspace",
        "bootstrap-transaction",
        "begin",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
    ]);
    assert!(begin.status.success());

    let rollback = miho(&[
        "workspace",
        "bootstrap-transaction",
        "rollback",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
    ]);
    assert!(
        rollback.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&rollback.stderr)
    );
    let receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&rollback.stdout).unwrap();
    assert_eq!(
        receipt.operation,
        WorkspaceBootstrapTransactionOperationV1::Rollback
    );
    assert_eq!(receipt.files_removed, 12);
    assert!(!workspace.join("configs/update_v1.json").exists());
    assert!(!workspace.join(ZZZ_BOX_STATE_RELATIVE_PATH).exists());
    assert!(!workspace
        .join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH)
        .exists());
    assert!(transaction.is_dir());

    let discard = miho(&[
        "workspace",
        "bootstrap-transaction",
        "discard",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
    ]);
    assert!(
        discard.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&discard.stderr)
    );
    let discard_receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&discard.stdout).unwrap();
    assert_eq!(
        discard_receipt.operation,
        WorkspaceBootstrapTransactionOperationV1::Discard
    );
    assert!(discard_receipt.transaction_cleaned);
    assert!(!transaction.exists());

    let finalize = miho(&[
        "workspace",
        "bootstrap-transaction",
        "finalize",
        "--workspace",
        workspace_text,
        "--transaction",
        transaction_text,
        "--completed-operation",
        "discard",
    ]);
    assert!(
        finalize.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&finalize.stderr)
    );
    let finalize_receipt: WorkspaceBootstrapTransactionReceiptV1 =
        serde_json::from_slice(&finalize.stdout).unwrap();
    assert_eq!(
        finalize_receipt.completed_operation,
        Some(WorkspaceBootstrapCompletedOperationV1::Discard)
    );
    assert_eq!(finalize_receipt.files_verified, 12);
    assert_eq!(finalize_receipt.completion_marker_removed, Some(true));

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_cli_rejects_relative_transaction_with_stable_code() {
    let base = temp_root("transaction-relative-CANARY_USERNAME");
    let workspace = base.join("workspace");
    fs::create_dir(&workspace).unwrap();
    let output = miho(&[
        "workspace",
        "bootstrap-transaction",
        "begin",
        "--workspace",
        workspace.to_str().unwrap(),
        "--transaction",
        "relative-CANARY_USERNAME",
    ]);

    assert_eq!(output.status.code(), Some(1));
    assert!(output.stdout.is_empty());
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(stderr.contains("workspace failed: workspace.bootstrap_transaction_unsafe"));
    assert!(!stderr.contains(base.to_string_lossy().as_ref()));
    assert!(!stderr.contains("CANARY_USERNAME"));

    cleanup(&base);
}
