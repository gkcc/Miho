use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use miho_app::{
    begin_workspace_bootstrap_transaction_v1, bootstrap_workspace_v1,
    commit_workspace_bootstrap_transaction_v1, discard_workspace_bootstrap_transaction_v1,
    finalize_workspace_bootstrap_transaction_v1, rollback_workspace_bootstrap_transaction_v1,
    verify_workspace_bootstrap_transaction_v1, WorkspaceBootstrapCompletedOperationV1,
    WorkspaceBootstrapError, WorkspaceBootstrapRequestV1, WorkspaceBootstrapTransactionOperationV1,
    WorkspaceBootstrapTransactionRequestV1, WorkspaceWriteLease,
    MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1, MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1,
    MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1, RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1,
    RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH, RELEASE_BOOTSTRAP_STATE_SCHEMA_V1,
    RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1,
    RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1,
    RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1, WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH,
    WORKSPACE_WRITER_ARBITRATION_LOCK_RELATIVE_PATH, WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH,
    WORKSPACE_WRITE_LOCK_RELATIVE_PATH, ZZZ_BOX_STATE_RELATIVE_PATH,
};
use miho_core::box_state::BoxState;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

const CONFIG_PATHS: &[&str] = &[
    "configs/update_v1.json",
    "configs/hsr_banner_plan.json",
    "configs/zzz_banner_plan.json",
    "configs/zzz_endgame_phase_overrides.json",
    "configs/zzz_decision_rules.yaml",
    "configs/zzz_decision_baseline.json",
    "configs/zzz_mechanism_notes/norma.yaml",
    "configs/zzz_mechanism_notes/sunna.yaml",
    "configs/zzz_mechanism_notes/velina.yaml",
    "configs/zzz_mechanism_notes/ye-shunguang.yaml",
];

fn temp_root(label: &str) -> PathBuf {
    let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "miho-workspace-bootstrap-{label}-{}-{id}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    root
}

fn cleanup(root: &Path) {
    fs::remove_dir_all(root).unwrap();
}

fn bootstrap(
    root: &Path,
) -> Result<miho_app::WorkspaceBootstrapReceiptV1, WorkspaceBootstrapError> {
    bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(root.to_path_buf()))
}

fn source_config(relative_path: &str) -> Vec<u8> {
    let repository = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    fs::read(repository.join(relative_path)).unwrap()
}

fn default_box_bytes() -> Vec<u8> {
    let mut bytes = serde_json::to_vec_pretty(&BoxState::default()).unwrap();
    bytes.push(b'\n');
    bytes
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn write_state(root: &Path, managed_files: BTreeMap<String, String>) {
    fs::create_dir_all(root.join(".miho")).unwrap();
    fs::write(
        root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH),
        serde_json::to_vec_pretty(&json!({
            "schema_version": RELEASE_BOOTSTRAP_STATE_SCHEMA_V1,
            "managed_files": managed_files,
        }))
        .unwrap(),
    )
    .unwrap();
}

fn read_state(root: &Path) -> Value {
    serde_json::from_slice(&fs::read(root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH)).unwrap())
        .unwrap()
}

fn snapshot_managed_files(root: &Path) -> BTreeMap<String, Vec<u8>> {
    CONFIG_PATHS
        .iter()
        .copied()
        .chain([
            ZZZ_BOX_STATE_RELATIVE_PATH,
            RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH,
        ])
        .map(|path| (path.to_owned(), fs::read(root.join(path)).unwrap()))
        .collect()
}

fn transaction_paths() -> impl Iterator<Item = &'static str> {
    CONFIG_PATHS.iter().copied().chain([
        ZZZ_BOX_STATE_RELATIVE_PATH,
        RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH,
    ])
}

fn snapshot_transaction_files(root: &Path) -> BTreeMap<String, Option<Vec<u8>>> {
    transaction_paths()
        .map(|path| {
            let bytes = match fs::read(root.join(path)) {
                Ok(bytes) => Some(bytes),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
                Err(error) => panic!("cannot snapshot {path}: {error}"),
            };
            (path.to_owned(), bytes)
        })
        .collect()
}

fn transaction_request(
    workspace: &Path,
    transaction: &Path,
) -> WorkspaceBootstrapTransactionRequestV1 {
    WorkspaceBootstrapTransactionRequestV1::new(workspace.to_path_buf(), transaction.to_path_buf())
}

#[test]
fn workspace_bootstrap_fresh_install_is_exact_and_idempotent() {
    let root = temp_root("fresh");

    let first = bootstrap(&root).unwrap();
    assert_eq!(first.schema_version, RELEASE_BOOTSTRAP_RECEIPT_SCHEMA_V1);
    assert_eq!(first.installed.len(), CONFIG_PATHS.len() + 1);
    assert!(first.upgraded.is_empty());
    assert!(first.preserved.is_empty());
    assert!(first.state_updated);
    for relative_path in CONFIG_PATHS {
        assert_eq!(
            fs::read(root.join(relative_path)).unwrap(),
            source_config(relative_path)
        );
    }
    assert_eq!(
        fs::read(root.join(ZZZ_BOX_STATE_RELATIVE_PATH)).unwrap(),
        default_box_bytes()
    );
    let parsed_box: BoxState =
        serde_json::from_slice(&fs::read(root.join(ZZZ_BOX_STATE_RELATIVE_PATH)).unwrap()).unwrap();
    assert_eq!(parsed_box, BoxState::default());

    let state = read_state(&root);
    assert_eq!(state["schema_version"], RELEASE_BOOTSTRAP_STATE_SCHEMA_V1);
    assert_eq!(
        state["managed_files"].as_object().unwrap().len(),
        CONFIG_PATHS.len() + 1
    );
    let before = snapshot_managed_files(&root);

    let second = bootstrap(&root).unwrap();
    assert!(second.installed.is_empty());
    assert!(second.upgraded.is_empty());
    assert!(second.preserved.is_empty());
    assert_eq!(second.unchanged.len(), CONFIG_PATHS.len() + 1);
    assert!(!second.state_updated);
    assert_eq!(snapshot_managed_files(&root), before);

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_retires_legacy_nom_seed_without_touching_legacy_file() {
    let root = temp_root("legacy-nom-seed");
    let legacy_path = "configs/zzz_mechanism_notes/nom.yaml";
    let canonical_path = "configs/zzz_mechanism_notes/norma.yaml";
    let legacy_bytes = b"user-owned legacy nom note\n";
    fs::create_dir_all(root.join("configs/zzz_mechanism_notes")).unwrap();
    fs::write(root.join(legacy_path), legacy_bytes).unwrap();
    write_state(
        &root,
        BTreeMap::from([(legacy_path.to_owned(), hash(legacy_bytes))]),
    );

    let first = bootstrap(&root).unwrap();
    assert!(first.installed.contains(&canonical_path.to_owned()));
    assert!(!first.installed.contains(&legacy_path.to_owned()));
    assert!(first.state_updated);
    assert_eq!(fs::read(root.join(legacy_path)).unwrap(), legacy_bytes);
    assert_eq!(
        fs::read(root.join(canonical_path)).unwrap(),
        source_config(canonical_path)
    );
    let state = read_state(&root);
    assert!(state["managed_files"].get(legacy_path).is_none());
    assert_eq!(
        state["managed_files"][canonical_path],
        hash(&source_config(canonical_path))
    );

    let second = bootstrap(&root).unwrap();
    assert!(!second.state_updated);
    assert_eq!(fs::read(root.join(legacy_path)).unwrap(), legacy_bytes);

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_transaction_round_trips_legacy_nom_seed() {
    let base = temp_root("transaction-legacy-nom-seed");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    let legacy_path = "configs/zzz_mechanism_notes/nom.yaml";
    let canonical_path = "configs/zzz_mechanism_notes/norma.yaml";
    let legacy_bytes = b"user-owned legacy nom note\n";
    fs::create_dir(&workspace).unwrap();
    fs::create_dir_all(workspace.join("configs/zzz_mechanism_notes")).unwrap();
    fs::write(workspace.join(legacy_path), legacy_bytes).unwrap();
    write_state(
        &workspace,
        BTreeMap::from([(legacy_path.to_owned(), hash(legacy_bytes))]),
    );
    let request = transaction_request(&workspace, &transaction);

    let begun = begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert!(begun
        .bootstrap
        .as_ref()
        .unwrap()
        .installed
        .contains(&canonical_path.to_owned()));
    assert_eq!(fs::read(workspace.join(legacy_path)).unwrap(), legacy_bytes);
    assert!(read_state(&workspace)["managed_files"]
        .get(legacy_path)
        .is_none());

    rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(fs::read(workspace.join(legacy_path)).unwrap(), legacy_bytes);
    assert!(!workspace.join(canonical_path).exists());
    assert_eq!(
        read_state(&workspace)["managed_files"][legacy_path],
        hash(legacy_bytes)
    );
    discard_workspace_bootstrap_transaction_v1(&request).unwrap();

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_direct_preserves_an_old_unchanged_managed_config() {
    let root = temp_root("managed-direct-preserve");
    let relative_path = CONFIG_PATHS[0];
    let old_seed = b"old installer seed\n";
    fs::create_dir_all(root.join("configs")).unwrap();
    fs::write(root.join(relative_path), old_seed).unwrap();
    write_state(
        &root,
        BTreeMap::from([(relative_path.to_owned(), hash(old_seed))]),
    );

    let receipt = bootstrap(&root).unwrap();
    assert!(receipt.upgraded.is_empty());
    assert!(receipt.unchanged.contains(&relative_path.to_owned()));
    assert_eq!(fs::read(root.join(relative_path)).unwrap(), old_seed);
    assert_eq!(
        read_state(&root)["managed_files"][relative_path],
        hash(old_seed)
    );

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_direct_atomically_rebinds_a_missing_owned_config() {
    let base = temp_root("direct-missing-state-rebind");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let relative_path = CONFIG_PATHS[0];
    let old_owner_hash = hash(b"old generation seed");
    write_state(
        &workspace,
        BTreeMap::from([(relative_path.to_owned(), old_owner_hash)]),
    );

    let receipt = bootstrap(&workspace).unwrap();
    assert!(receipt.installed.contains(&relative_path.to_owned()));
    assert!(receipt.state_updated);
    assert_eq!(
        fs::read(workspace.join(relative_path)).unwrap(),
        source_config(relative_path)
    );
    assert_eq!(
        read_state(&workspace)["managed_files"][relative_path],
        hash(&source_config(relative_path))
    );

    let begun =
        begin_workspace_bootstrap_transaction_v1(&transaction_request(&workspace, &transaction))
            .unwrap();
    assert!(begun
        .bootstrap
        .as_ref()
        .unwrap()
        .unchanged
        .contains(&relative_path.to_owned()));
    assert!(!begun
        .bootstrap
        .as_ref()
        .unwrap()
        .preserved
        .contains(&relative_path.to_owned()));

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_direct_claims_each_created_seed_when_existing_state_has_no_entry() {
    let root = temp_root("direct-missing-state-no-entry");
    write_state(&root, BTreeMap::new());

    let receipt = bootstrap(&root).unwrap();
    assert_eq!(receipt.installed.len(), CONFIG_PATHS.len() + 1);
    assert!(receipt.state_updated);
    let state = read_state(&root);
    for relative_path in CONFIG_PATHS {
        assert_eq!(
            state["managed_files"][relative_path],
            hash(&source_config(relative_path))
        );
    }
    assert_eq!(
        state["managed_files"][ZZZ_BOX_STATE_RELATIVE_PATH],
        hash(&default_box_bytes())
    );

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_preserves_user_modified_managed_config_and_old_owner_hash() {
    let root = temp_root("user-modified");
    bootstrap(&root).unwrap();
    let relative_path = CONFIG_PATHS[0];
    let original_hash = read_state(&root)["managed_files"][relative_path]
        .as_str()
        .unwrap()
        .to_owned();
    let user_bytes = b"user-owned customization\n";
    fs::write(root.join(relative_path), user_bytes).unwrap();

    let receipt = bootstrap(&root).unwrap();
    assert!(receipt.preserved.contains(&relative_path.to_owned()));
    assert_eq!(fs::read(root.join(relative_path)).unwrap(), user_bytes);
    assert_eq!(
        read_state(&root)["managed_files"][relative_path],
        original_hash
    );

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_does_not_claim_a_preexisting_file_without_state() {
    let root = temp_root("unowned-existing");
    let relative_path = CONFIG_PATHS[1];
    let user_bytes = b"preexisting user file\n";
    fs::create_dir_all(root.join("configs")).unwrap();
    fs::write(root.join(relative_path), user_bytes).unwrap();

    let receipt = bootstrap(&root).unwrap();
    assert!(receipt.preserved.contains(&relative_path.to_owned()));
    assert_eq!(fs::read(root.join(relative_path)).unwrap(), user_bytes);
    assert!(read_state(&root)["managed_files"]
        .get(relative_path)
        .is_none());

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_box_is_missing_only_and_uses_box_state_default() {
    let root = temp_root("box-missing-only");
    fs::create_dir_all(root.join(".miho")).unwrap();
    let user_box =
        br#"{"version":2,"updatedAt":"user","owned":["nom"],"buildSlug":"","builds":{}}"#;
    fs::write(root.join(ZZZ_BOX_STATE_RELATIVE_PATH), user_box).unwrap();

    let first = bootstrap(&root).unwrap();
    assert!(first
        .preserved
        .contains(&ZZZ_BOX_STATE_RELATIVE_PATH.to_owned()));
    assert_eq!(
        fs::read(root.join(ZZZ_BOX_STATE_RELATIVE_PATH)).unwrap(),
        user_box
    );
    assert!(read_state(&root)["managed_files"]
        .get(ZZZ_BOX_STATE_RELATIVE_PATH)
        .is_none());

    fs::remove_file(root.join(ZZZ_BOX_STATE_RELATIVE_PATH)).unwrap();
    let second = bootstrap(&root).unwrap();
    assert!(second
        .installed
        .contains(&ZZZ_BOX_STATE_RELATIVE_PATH.to_owned()));
    assert_eq!(
        fs::read(root.join(ZZZ_BOX_STATE_RELATIVE_PATH)).unwrap(),
        default_box_bytes()
    );

    let user_box_after_ownership = b"user changed an installer-created box\n";
    fs::write(
        root.join(ZZZ_BOX_STATE_RELATIVE_PATH),
        user_box_after_ownership,
    )
    .unwrap();
    let third = bootstrap(&root).unwrap();
    assert!(third
        .preserved
        .contains(&ZZZ_BOX_STATE_RELATIVE_PATH.to_owned()));
    assert_eq!(
        fs::read(root.join(ZZZ_BOX_STATE_RELATIVE_PATH)).unwrap(),
        user_box_after_ownership
    );

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_rejects_unknown_or_tampered_state_without_partial_files() {
    let invalid_states = [
        json!({
            "schema_version": RELEASE_BOOTSTRAP_STATE_SCHEMA_V1,
            "managed_files": {},
            "unknown": true,
        }),
        json!({"schema_version": "future", "managed_files": {}}),
        json!({
            "schema_version": RELEASE_BOOTSTRAP_STATE_SCHEMA_V1,
            "managed_files": {"private.txt": "0".repeat(64)},
        }),
        json!({
            "schema_version": RELEASE_BOOTSTRAP_STATE_SCHEMA_V1,
            "managed_files": {CONFIG_PATHS[0]: "ABC"},
        }),
    ];

    for (index, invalid) in invalid_states.into_iter().enumerate() {
        let root = temp_root(&format!("invalid-state-{index}"));
        fs::create_dir_all(root.join(".miho")).unwrap();
        let state_bytes = serde_json::to_vec(&invalid).unwrap();
        fs::write(
            root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH),
            &state_bytes,
        )
        .unwrap();

        assert_eq!(bootstrap(&root), Err(WorkspaceBootstrapError::InvalidState));
        assert_eq!(
            fs::read(root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH)).unwrap(),
            state_bytes
        );
        assert!(!root.join(CONFIG_PATHS[0]).exists());
        assert!(!root.join(ZZZ_BOX_STATE_RELATIVE_PATH).exists());
        cleanup(&root);
    }
}

#[test]
fn workspace_bootstrap_rejects_oversized_state_and_target_before_any_batch() {
    let state_root = temp_root("oversized-state");
    fs::create_dir_all(state_root.join(".miho")).unwrap();
    fs::write(
        state_root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH),
        vec![b'x'; MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1 as usize + 1],
    )
    .unwrap();
    assert_eq!(
        bootstrap(&state_root),
        Err(WorkspaceBootstrapError::StateTooLarge)
    );
    assert!(!state_root.join(CONFIG_PATHS[0]).exists());
    cleanup(&state_root);

    let target_root = temp_root("oversized-target");
    fs::create_dir_all(target_root.join("configs")).unwrap();
    fs::write(
        target_root.join(CONFIG_PATHS[0]),
        vec![b'x'; MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1 as usize + 1],
    )
    .unwrap();
    assert_eq!(
        bootstrap(&target_root),
        Err(WorkspaceBootstrapError::TargetTooLarge)
    );
    assert!(!target_root.join(CONFIG_PATHS[1]).exists());
    assert!(!target_root
        .join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH)
        .exists());
    cleanup(&target_root);
}

#[test]
fn workspace_bootstrap_busy_lease_is_stable_and_writes_nothing() {
    let root = temp_root("busy-CANARY_USERNAME");
    let lease = WorkspaceWriteLease::acquire(&root).unwrap();

    let error = bootstrap(&root).unwrap_err();
    assert_eq!(error, WorkspaceBootstrapError::WorkspaceBusy);
    assert_eq!(error.to_string(), "workspace.write_busy");
    assert!(!error.to_string().contains("CANARY_USERNAME"));
    assert!(!root.join(CONFIG_PATHS[0]).exists());
    assert!(!root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH).exists());

    drop(lease);
    cleanup(&root);
}

#[test]
fn workspace_bootstrap_receipt_contains_only_relative_allowlisted_paths() {
    let root = temp_root("receipt-CANARY_USERNAME");
    let receipt = bootstrap(&root).unwrap();
    let json = serde_json::to_string(&receipt).unwrap();

    assert!(!json.contains(root.to_string_lossy().as_ref()));
    assert!(!json.contains("CANARY_USERNAME"));
    for relative_path in receipt
        .installed
        .iter()
        .chain(&receipt.upgraded)
        .chain(&receipt.preserved)
        .chain(&receipt.unchanged)
    {
        assert!(Path::new(relative_path).is_relative());
        assert!(
            CONFIG_PATHS.contains(&relative_path.as_str())
                || relative_path == ZZZ_BOX_STATE_RELATIVE_PATH
        );
    }

    cleanup(&root);
}

#[test]
fn workspace_bootstrap_invalid_late_target_prevents_earlier_installation() {
    let root = temp_root("preflight-no-partial");
    let invalid_target = CONFIG_PATHS[5];
    fs::create_dir_all(root.join(invalid_target)).unwrap();

    assert_eq!(bootstrap(&root), Err(WorkspaceBootstrapError::UnsafeTarget));
    assert!(!root.join(CONFIG_PATHS[0]).exists());
    assert!(!root.join(CONFIG_PATHS[4]).exists());
    assert!(root.join(invalid_target).is_dir());
    assert!(!root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH).exists());

    cleanup(&root);
}

#[cfg(any(unix, windows))]
#[test]
fn workspace_bootstrap_rejects_symlink_or_reparse_target_without_touching_external_file() {
    let parent = temp_root("target-link");
    let root = parent.join("workspace");
    let external = parent.join("external.json");
    fs::create_dir_all(root.join("configs")).unwrap();
    fs::write(&external, b"external-canary").unwrap();
    let target = root.join(CONFIG_PATHS[0]);

    if create_file_link(&external, &target).is_err() {
        cleanup(&parent);
        return;
    }
    assert_eq!(bootstrap(&root), Err(WorkspaceBootstrapError::UnsafeTarget));
    assert_eq!(fs::read(&external).unwrap(), b"external-canary");
    assert!(!root.join(CONFIG_PATHS[1]).exists());

    cleanup(&parent);
}

#[cfg(any(unix, windows))]
#[test]
fn workspace_bootstrap_rejects_symlink_or_reparse_ancestor() {
    let parent = temp_root("ancestor-link");
    let root = parent.join("workspace");
    let external = parent.join("external-configs");
    fs::create_dir_all(&root).unwrap();
    fs::create_dir_all(&external).unwrap();
    fs::write(external.join("update_v1.json"), b"external-canary").unwrap();

    if create_directory_link(&external, &root.join("configs")).is_err() {
        cleanup(&parent);
        return;
    }
    assert_eq!(bootstrap(&root), Err(WorkspaceBootstrapError::UnsafeTarget));
    assert_eq!(
        fs::read(external.join("update_v1.json")).unwrap(),
        b"external-canary"
    );
    assert!(!root.join(RELEASE_BOOTSTRAP_STATE_RELATIVE_PATH).exists());

    cleanup(&parent);
}

#[test]
fn workspace_bootstrap_transaction_fresh_begin_verify_and_missing_rollback_are_exact() {
    let base = temp_root("transaction-fresh-rollback");
    let workspace = base.join("workspace 用户");
    let transaction = base.join("transaction evidence");
    fs::create_dir(&workspace).unwrap();
    let before = snapshot_transaction_files(&workspace);
    assert!(before.values().all(Option::is_none));

    let request = transaction_request(&workspace, &transaction);
    let begun = begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        begun.schema_version,
        RELEASE_BOOTSTRAP_TRANSACTION_RECEIPT_SCHEMA_V1
    );
    assert_eq!(
        begun.operation,
        WorkspaceBootstrapTransactionOperationV1::Begin
    );
    assert_eq!(begun.files_verified, 12);
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
        .is_file());
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
        .is_dir());
    assert!(snapshot_transaction_files(&workspace)
        .values()
        .all(Option::is_some));

    let verified = verify_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        verified.operation,
        WorkspaceBootstrapTransactionOperationV1::Verify
    );
    assert_eq!(verified.files_verified, 12);

    let rolled_back = rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        rolled_back.operation,
        WorkspaceBootstrapTransactionOperationV1::Rollback
    );
    assert_eq!(rolled_back.files_removed, 12);
    assert_eq!(snapshot_transaction_files(&workspace), before);
    assert!(!workspace.join("configs").exists());
    assert!(workspace.join(".miho").is_dir());
    assert!(workspace.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH).is_file());
    assert!(workspace
        .join(WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH)
        .is_file());
    assert!(workspace
        .join(WORKSPACE_WRITER_ARBITRATION_LOCK_RELATIVE_PATH)
        .is_file());
    assert!(workspace
        .join(WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH)
        .is_file());
    assert_eq!(
        fs::read_dir(workspace.join(".miho")).unwrap().count(),
        4,
        "the four persistent protocol locks are the only fresh .miho entries"
    );
    assert!(
        transaction.is_dir(),
        "rollback must retain recovery evidence"
    );

    let second = rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(second.files_restored, 0);
    assert_eq!(second.files_removed, 0);
    assert_eq!(snapshot_transaction_files(&workspace), before);

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_manifest_binds_directory_before_state() {
    let base = temp_root("transaction-directory-manifest");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();

    let manifest: Value = serde_json::from_slice(
        &fs::read(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)).unwrap(),
    )
    .unwrap();
    assert_eq!(
        manifest["directories"],
        json!([
            {"relative_path": ".miho", "before": {"kind": "present"}},
            {"relative_path": "configs", "before": {"kind": "missing"}},
            {
                "relative_path": "configs/zzz_mechanism_notes",
                "before": {"kind": "missing"}
            }
        ])
    );
    assert!(manifest["transaction_token"]
        .as_str()
        .is_some_and(|token| token.len() == 64));

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_rollback_preserves_preexisting_empty_directories() {
    let base = temp_root("transaction-preexisting-directories");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir_all(workspace.join("configs/zzz_mechanism_notes")).unwrap();
    fs::create_dir(workspace.join(".miho")).unwrap();
    let request = transaction_request(&workspace, &transaction);

    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert!(workspace.join(".miho").is_dir());
    assert!(workspace.join("configs").is_dir());
    assert!(workspace.join("configs/zzz_mechanism_notes").is_dir());
    assert_eq!(fs::read_dir(workspace.join("configs")).unwrap().count(), 1);
    assert_eq!(
        fs::read_dir(workspace.join("configs/zzz_mechanism_notes"))
            .unwrap()
            .count(),
        0
    );

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_foreign_directory_content_fails_before_file_rollback() {
    let base = temp_root("transaction-foreign-directory-content");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    let foreign = workspace.join("configs/zzz_mechanism_notes/user-canary.txt");
    fs::write(&foreign, b"keep").unwrap();
    let files_before = snapshot_transaction_files(&workspace);

    assert_eq!(
        rollback_workspace_bootstrap_transaction_v1(&request),
        Err(WorkspaceBootstrapError::TransactionDrift)
    );
    assert_eq!(snapshot_transaction_files(&workspace), files_before);
    assert_eq!(fs::read(&foreign).unwrap(), b"keep");
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
        .is_file());

    cleanup(&base);
}

#[cfg(any(unix, windows))]
#[test]
fn workspace_bootstrap_transaction_reparse_directory_is_not_deleted_by_rollback() {
    let base = temp_root("transaction-reparse-directory-rollback");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    let external = base.join("external-directory");
    fs::create_dir(&workspace).unwrap();
    fs::create_dir(&external).unwrap();
    fs::write(external.join("canary.txt"), b"external").unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    let mechanism = workspace.join("configs/zzz_mechanism_notes");
    for relative_path in &CONFIG_PATHS[6..] {
        fs::remove_file(workspace.join(relative_path)).unwrap();
    }
    fs::remove_dir(&mechanism).unwrap();
    if create_directory_link(&external, &mechanism).is_ok() {
        assert_eq!(
            rollback_workspace_bootstrap_transaction_v1(&request),
            Err(WorkspaceBootstrapError::UnsafeTarget)
        );
        assert!(mechanism.exists());
        assert_eq!(fs::read(external.join("canary.txt")).unwrap(), b"external");
        assert!(transaction.exists());
    }

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_rollback_then_discard_is_exact_and_idempotent() {
    let base = temp_root("transaction-discard");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    rollback_workspace_bootstrap_transaction_v1(&request).unwrap();

    let discarded = discard_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        discarded.operation,
        WorkspaceBootstrapTransactionOperationV1::Discard
    );
    assert!(discarded.transaction_cleaned);
    assert!(!transaction.exists());
    let retried = discard_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        retried.operation,
        WorkspaceBootstrapTransactionOperationV1::Discard
    );
    let finalized = finalize_workspace_bootstrap_transaction_v1(
        &request,
        WorkspaceBootstrapCompletedOperationV1::Discard,
    )
    .unwrap();
    assert_eq!(
        finalized.operation,
        WorkspaceBootstrapTransactionOperationV1::Finalize
    );
    assert_eq!(
        finalized.completed_operation,
        Some(WorkspaceBootstrapCompletedOperationV1::Discard)
    );
    assert_eq!(finalized.files_verified, 12);
    assert_eq!(finalized.completion_marker_removed, Some(true));

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_discard_rejects_third_state_and_retains_evidence() {
    let base = temp_root("transaction-discard-third-state");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    fs::create_dir(workspace.join("configs")).unwrap();
    fs::write(workspace.join(CONFIG_PATHS[0]), b"third-state").unwrap();

    assert_eq!(
        discard_workspace_bootstrap_transaction_v1(&request),
        Err(WorkspaceBootstrapError::TransactionVerificationFailed)
    );
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
        .is_file());
    assert_eq!(
        fs::read(workspace.join(CONFIG_PATHS[0])).unwrap(),
        b"third-state"
    );

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_restores_all_twelve_paths_after_candidate_failure() {
    let base = temp_root("transaction-twelve-restore");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();

    let mut managed = BTreeMap::new();
    for relative_path in CONFIG_PATHS {
        let bytes = format!("old managed seed for {relative_path}\n").into_bytes();
        let target = workspace.join(relative_path);
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        fs::write(&target, &bytes).unwrap();
        managed.insert((*relative_path).to_owned(), hash(&bytes));
    }
    let old_box = b"old installer box seed\n";
    fs::create_dir_all(workspace.join(".miho")).unwrap();
    fs::write(workspace.join(ZZZ_BOX_STATE_RELATIVE_PATH), old_box).unwrap();
    managed.insert(ZZZ_BOX_STATE_RELATIVE_PATH.to_owned(), hash(old_box));
    write_state(&workspace, managed);
    let before = snapshot_transaction_files(&workspace);
    assert_eq!(before.len(), 12);
    assert!(before.values().all(Option::is_some));

    let request = transaction_request(&workspace, &transaction);
    let begun = begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(begun.bootstrap.as_ref().unwrap().upgraded.len(), 10);
    assert_ne!(snapshot_transaction_files(&workspace), before);

    let rolled_back = rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(rolled_back.files_restored, 11);
    assert_eq!(rolled_back.files_removed, 0);
    assert_eq!(snapshot_transaction_files(&workspace), before);

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_only_transaction_begin_upgrades_old_managed_config_and_can_rollback() {
    let base = temp_root("transaction-only-upgrade");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let relative_path = CONFIG_PATHS[0];
    let old_seed = b"old generation-owned config\n";
    fs::create_dir_all(workspace.join("configs")).unwrap();
    fs::write(workspace.join(relative_path), old_seed).unwrap();
    write_state(
        &workspace,
        BTreeMap::from([(relative_path.to_owned(), hash(old_seed))]),
    );

    let direct = bootstrap(&workspace).unwrap();
    assert!(direct.upgraded.is_empty());
    assert_eq!(fs::read(workspace.join(relative_path)).unwrap(), old_seed);
    assert_eq!(
        read_state(&workspace)["managed_files"][relative_path],
        hash(old_seed)
    );
    let before_transaction = snapshot_transaction_files(&workspace);

    let request = transaction_request(&workspace, &transaction);
    let begun = begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(begun.bootstrap.as_ref().unwrap().upgraded, [relative_path]);
    assert_eq!(
        fs::read(workspace.join(relative_path)).unwrap(),
        source_config(relative_path)
    );
    assert_eq!(
        read_state(&workspace)["managed_files"][relative_path],
        hash(&source_config(relative_path))
    );

    rollback_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(snapshot_transaction_files(&workspace), before_transaction);

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_user_drift_refuses_rollback_with_zero_modification() {
    let base = temp_root("transaction-user-drift");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();

    fs::write(
        workspace.join(CONFIG_PATHS[5]),
        b"third state written by user\n",
    )
    .unwrap();
    let workspace_before_attempt = snapshot_transaction_files(&workspace);
    let manifest_before =
        fs::read(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)).unwrap();

    assert_eq!(
        verify_workspace_bootstrap_transaction_v1(&request),
        Err(WorkspaceBootstrapError::TransactionVerificationFailed)
    );
    assert_eq!(
        snapshot_transaction_files(&workspace),
        workspace_before_attempt
    );
    assert_eq!(
        rollback_workspace_bootstrap_transaction_v1(&request),
        Err(WorkspaceBootstrapError::TransactionDrift)
    );
    assert_eq!(
        snapshot_transaction_files(&workspace),
        workspace_before_attempt
    );
    assert_eq!(
        fs::read(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)).unwrap(),
        manifest_before
    );

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_commit_requires_exact_post_and_cleans_only_exact_evidence() {
    let base = temp_root("transaction-commit");
    let workspace = base.join("workspace CANARY_USERNAME");
    let transaction = base.join("transaction CANARY_USERNAME");
    fs::create_dir(&workspace).unwrap();
    bootstrap(&workspace).unwrap();
    let workspace_before = snapshot_transaction_files(&workspace);
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();

    let before_directory = transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1);
    assert_eq!(fs::read_dir(&before_directory).unwrap().count(), 12);
    let verified = verify_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(verified.files_verified, 12);

    let committed = commit_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        committed.operation,
        WorkspaceBootstrapTransactionOperationV1::Commit
    );
    assert_eq!(committed.files_removed, 12);
    assert!(committed.transaction_cleaned);
    assert!(!transaction.exists());
    assert_eq!(snapshot_transaction_files(&workspace), workspace_before);
    let json = serde_json::to_string(&committed).unwrap();
    assert!(!json.contains(base.to_string_lossy().as_ref()));
    assert!(!json.contains("CANARY_USERNAME"));

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_finalize_requires_matching_completion_and_is_idempotent() {
    let base = temp_root("transaction-finalize");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    bootstrap(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();

    assert_eq!(
        finalize_workspace_bootstrap_transaction_v1(
            &request,
            WorkspaceBootstrapCompletedOperationV1::Commit,
        ),
        Err(WorkspaceBootstrapError::TransactionCleanupFailed)
    );
    let committed = commit_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(committed.files_removed, 12);
    assert_eq!(
        fs::read_dir(&base)
            .unwrap()
            .filter_map(Result::ok)
            .filter(|entry| entry
                .file_name()
                .to_string_lossy()
                .contains("bootstrap-commit-completed-v1"))
            .count(),
        1
    );

    // A process restart may replay commit before the caller durably records
    // its completed phase. The marker remains the unambiguous proof.
    let replayed = commit_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(replayed.files_removed, 0);
    assert_eq!(
        finalize_workspace_bootstrap_transaction_v1(
            &request,
            WorkspaceBootstrapCompletedOperationV1::Discard,
        ),
        Err(WorkspaceBootstrapError::TransactionCleanupFailed)
    );

    let finalized = finalize_workspace_bootstrap_transaction_v1(
        &request,
        WorkspaceBootstrapCompletedOperationV1::Commit,
    )
    .unwrap();
    assert_eq!(
        finalized.operation,
        WorkspaceBootstrapTransactionOperationV1::Finalize
    );
    assert_eq!(
        finalized.completed_operation,
        Some(WorkspaceBootstrapCompletedOperationV1::Commit)
    );
    assert_eq!(finalized.files_verified, 12);
    assert_eq!(finalized.files_restored, 0);
    assert_eq!(finalized.files_removed, 0);
    assert!(finalized.transaction_cleaned);
    assert_eq!(finalized.completion_marker_removed, Some(true));
    assert_eq!(
        fs::read_dir(&base)
            .unwrap()
            .filter_map(Result::ok)
            .filter(|entry| entry
                .file_name()
                .to_string_lossy()
                .contains("bootstrap-commit-completed-v1"))
            .count(),
        0
    );

    let idempotent = finalize_workspace_bootstrap_transaction_v1(
        &request,
        WorkspaceBootstrapCompletedOperationV1::Commit,
    )
    .unwrap();
    assert_eq!(idempotent.files_verified, 0);
    assert_eq!(idempotent.completion_marker_removed, Some(false));

    // Once acknowledged, the exact transaction identity is reusable rather
    // than being permanently blocked by a tombstone.
    let next = begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    assert_eq!(
        next.operation,
        WorkspaceBootstrapTransactionOperationV1::Begin
    );

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_commit_refuses_pollution_without_partial_cleanup() {
    let base = temp_root("transaction-commit-pollution");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    bootstrap(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    let pollution = transaction.join("user-canary.txt");
    fs::write(&pollution, b"keep").unwrap();
    let stash_count =
        fs::read_dir(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1))
            .unwrap()
            .count();

    assert_eq!(
        commit_workspace_bootstrap_transaction_v1(&request),
        Err(WorkspaceBootstrapError::InvalidTransaction)
    );
    assert_eq!(fs::read(&pollution).unwrap(), b"keep");
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
        .is_file());
    assert_eq!(
        fs::read_dir(transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1))
            .unwrap()
            .count(),
        stash_count
    );

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_commit_rejects_box_drift_and_preserves_evidence() {
    let base = temp_root("transaction-box-drift");
    let workspace = base.join("workspace");
    let transaction = base.join("transaction");
    fs::create_dir(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    fs::write(
        workspace.join(ZZZ_BOX_STATE_RELATIVE_PATH),
        b"user changed Box after candidate verification\n",
    )
    .unwrap();

    assert_eq!(
        commit_workspace_bootstrap_transaction_v1(&request),
        Err(WorkspaceBootstrapError::TransactionVerificationFailed)
    );
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1)
        .is_file());
    assert!(transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
        .is_dir());

    cleanup(&base);
}

#[test]
fn workspace_bootstrap_transaction_manifest_is_strict_utf8_deny_unknown_and_bounded() {
    for case in [
        "unknown",
        "directory-unknown",
        "directory-order",
        "transaction-token",
        "utf8",
        "oversize",
    ] {
        let base = temp_root(&format!("transaction-manifest-{case}"));
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir(&workspace).unwrap();
        let request = transaction_request(&workspace, &transaction);
        begin_workspace_bootstrap_transaction_v1(&request).unwrap();
        let manifest_path = transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_FILE_V1);
        match case {
            "unknown" => {
                let mut value: Value =
                    serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
                value
                    .as_object_mut()
                    .unwrap()
                    .insert("unknown".to_owned(), json!(true));
                fs::write(&manifest_path, serde_json::to_vec(&value).unwrap()).unwrap();
            }
            "directory-unknown" => {
                let mut value: Value =
                    serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
                value["directories"][0]
                    .as_object_mut()
                    .unwrap()
                    .insert("unknown".to_owned(), json!(true));
                fs::write(&manifest_path, serde_json::to_vec(&value).unwrap()).unwrap();
            }
            "directory-order" => {
                let mut value: Value =
                    serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
                value["directories"].as_array_mut().unwrap().swap(0, 1);
                fs::write(&manifest_path, serde_json::to_vec(&value).unwrap()).unwrap();
            }
            "transaction-token" => {
                let mut value: Value =
                    serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
                value["transaction_token"] = json!("0".repeat(64));
                fs::write(&manifest_path, serde_json::to_vec(&value).unwrap()).unwrap();
            }
            "utf8" => fs::write(&manifest_path, [0xc3, 0x28]).unwrap(),
            "oversize" => fs::write(
                &manifest_path,
                vec![b'x'; MAX_RELEASE_BOOTSTRAP_TRANSACTION_MANIFEST_BYTES_V1 as usize + 1],
            )
            .unwrap(),
            _ => unreachable!(),
        }
        let expected = if case == "oversize" {
            WorkspaceBootstrapError::TransactionTooLarge
        } else {
            WorkspaceBootstrapError::InvalidTransaction
        };
        assert_eq!(
            verify_workspace_bootstrap_transaction_v1(&request),
            Err(expected),
            "case={case}"
        );
        cleanup(&base);
    }
}

#[test]
fn workspace_bootstrap_transaction_rejects_extra_and_oversized_stash_content() {
    for case in ["extra", "target-oversize", "state-oversize"] {
        let base = temp_root(&format!("transaction-stash-{case}"));
        let workspace = base.join("workspace");
        let transaction = base.join("transaction");
        fs::create_dir(&workspace).unwrap();
        bootstrap(&workspace).unwrap();
        let request = transaction_request(&workspace, &transaction);
        begin_workspace_bootstrap_transaction_v1(&request).unwrap();
        let before = transaction.join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1);
        match case {
            "extra" => fs::write(before.join("extra.bin"), b"pollution").unwrap(),
            "target-oversize" => fs::write(
                before.join("00.bin"),
                vec![b'x'; MAX_RELEASE_BOOTSTRAP_TARGET_BYTES_V1 as usize + 1],
            )
            .unwrap(),
            "state-oversize" => fs::write(
                before.join("11.bin"),
                vec![b'x'; MAX_RELEASE_BOOTSTRAP_STATE_BYTES_V1 as usize + 1],
            )
            .unwrap(),
            _ => unreachable!(),
        }
        let expected = if case == "extra" {
            WorkspaceBootstrapError::InvalidTransaction
        } else {
            WorkspaceBootstrapError::TransactionTooLarge
        };
        assert_eq!(
            verify_workspace_bootstrap_transaction_v1(&request),
            Err(expected),
            "case={case}"
        );
        assert!(transaction.exists());
        cleanup(&base);
    }
}

#[test]
fn workspace_bootstrap_transaction_requires_absolute_nonoverlapping_paths() {
    let base = temp_root("transaction-path-contract");
    let workspace = base.join("workspace");
    fs::create_dir(&workspace).unwrap();

    let relative = WorkspaceBootstrapTransactionRequestV1::new(
        workspace.clone(),
        PathBuf::from("relative-transaction"),
    );
    assert_eq!(
        begin_workspace_bootstrap_transaction_v1(&relative),
        Err(WorkspaceBootstrapError::UnsafeTransaction)
    );

    let nested_path = workspace.join("transaction");
    let nested = transaction_request(&workspace, &nested_path);
    assert_eq!(
        begin_workspace_bootstrap_transaction_v1(&nested),
        Err(WorkspaceBootstrapError::TransactionOverlap)
    );
    assert!(!nested_path.exists());

    let outer = base.join("outer transaction");
    let nested_workspace = outer.join("nested workspace");
    fs::create_dir_all(&nested_workspace).unwrap();
    let reverse = transaction_request(&nested_workspace, &outer);
    assert_eq!(
        begin_workspace_bootstrap_transaction_v1(&reverse),
        Err(WorkspaceBootstrapError::TransactionOverlap)
    );

    let occupied = base.join("occupied transaction");
    fs::create_dir(&occupied).unwrap();
    let canary = occupied.join("user-canary.txt");
    fs::write(&canary, b"keep").unwrap();
    let occupied_request = transaction_request(&workspace, &occupied);
    assert_eq!(
        begin_workspace_bootstrap_transaction_v1(&occupied_request),
        Err(WorkspaceBootstrapError::TransactionNotEmpty)
    );
    assert_eq!(fs::read(&canary).unwrap(), b"keep");

    cleanup(&base);
}

#[cfg(any(unix, windows))]
#[test]
fn workspace_bootstrap_transaction_rejects_reparse_root_parent_and_stash() {
    let base = temp_root("transaction-reparse");
    let workspace = base.join("workspace");
    fs::create_dir(&workspace).unwrap();

    let external_root = base.join("external-root");
    fs::create_dir(&external_root).unwrap();
    let linked_root = base.join("linked-transaction");
    if create_directory_link(&external_root, &linked_root).is_ok() {
        let request = transaction_request(&workspace, &linked_root);
        assert_eq!(
            begin_workspace_bootstrap_transaction_v1(&request),
            Err(WorkspaceBootstrapError::UnsafeTransaction)
        );
    }

    let external_parent = base.join("external-parent");
    fs::create_dir(&external_parent).unwrap();
    let linked_parent = base.join("linked-parent");
    if create_directory_link(&external_parent, &linked_parent).is_ok() {
        let request = transaction_request(&workspace, &linked_parent.join("transaction"));
        assert_eq!(
            begin_workspace_bootstrap_transaction_v1(&request),
            Err(WorkspaceBootstrapError::UnsafeTransaction)
        );
    }

    let transaction = base.join("regular-transaction");
    bootstrap(&workspace).unwrap();
    let request = transaction_request(&workspace, &transaction);
    begin_workspace_bootstrap_transaction_v1(&request).unwrap();
    let stash = transaction
        .join(RELEASE_BOOTSTRAP_TRANSACTION_BEFORE_DIRECTORY_V1)
        .join("00.bin");
    let external_file = base.join("external-stash.bin");
    fs::write(&external_file, b"external").unwrap();
    fs::remove_file(&stash).unwrap();
    if create_file_link(&external_file, &stash).is_ok() {
        assert_eq!(
            verify_workspace_bootstrap_transaction_v1(&request),
            Err(WorkspaceBootstrapError::UnsafeTransaction)
        );
        assert_eq!(fs::read(&external_file).unwrap(), b"external");
    }

    cleanup(&base);
}

#[cfg(unix)]
fn create_directory_link(target: &Path, link: &Path) -> std::io::Result<()> {
    std::os::unix::fs::symlink(target, link)
}

#[cfg(unix)]
fn create_file_link(target: &Path, link: &Path) -> std::io::Result<()> {
    std::os::unix::fs::symlink(target, link)
}

#[cfg(windows)]
fn create_directory_link(target: &Path, link: &Path) -> std::io::Result<()> {
    std::os::windows::fs::symlink_dir(target, link)
}

#[cfg(windows)]
fn create_file_link(target: &Path, link: &Path) -> std::io::Result<()> {
    std::os::windows::fs::symlink_file(target, link)
}
