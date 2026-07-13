use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    thread,
    time::{Duration, Instant},
};

use miho_app::{WorkspaceWriteLease, WorkspaceWriteLeaseError, WORKSPACE_WRITE_LOCK_RELATIVE_PATH};

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);
const CHILD_ROOT_ENV: &str = "MIHO_WORKSPACE_WRITE_LEASE_CHILD_ROOT";
const KILL_CHILD_ROOT_ENV: &str = "MIHO_WORKSPACE_WRITE_LEASE_KILL_CHILD_ROOT";

fn temp_root(label: &str) -> PathBuf {
    let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "miho-workspace-write-lease-{label}-{}-{id}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    root
}

fn cleanup(root: &Path) {
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn concurrent_acquire_reports_stable_busy_without_removing_lock_file() {
    let root = temp_root("busy-CANARY_SECRET");
    let first = WorkspaceWriteLease::acquire(&root).unwrap();
    assert_eq!(first.workspace_root(), fs::canonicalize(&root).unwrap());

    let error = WorkspaceWriteLease::acquire(&root).unwrap_err();
    assert_eq!(error, WorkspaceWriteLeaseError::Busy);
    assert_eq!(error.code(), "workspace.write_busy");
    assert_eq!(error.to_string(), "workspace.write_busy");
    assert!(!error.to_string().contains("CANARY_SECRET"));
    assert!(root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH).is_file());

    drop(first);
    cleanup(&root);
}

#[test]
fn exclusive_lock_contends_across_processes() {
    if let Some(root) = std::env::var_os(CHILD_ROOT_ENV) {
        let root = PathBuf::from(root);
        let _lease = WorkspaceWriteLease::acquire(&root).unwrap();
        fs::write(root.join("child-ready"), b"ready").unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        while !root.join("child-release").exists() {
            assert!(Instant::now() < deadline, "parent did not release child");
            thread::sleep(Duration::from_millis(5));
        }
        return;
    }

    let root = temp_root("cross-process");
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "exclusive_lock_contends_across_processes",
            "--nocapture",
        ])
        .env(CHILD_ROOT_ENV, &root)
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    while !root.join("child-ready").exists() {
        assert!(
            child.try_wait().unwrap().is_none(),
            "lock-holder child exited before becoming ready"
        );
        assert!(Instant::now() < deadline, "lock-holder child timed out");
        thread::sleep(Duration::from_millis(5));
    }

    assert_eq!(
        WorkspaceWriteLease::acquire(&root).unwrap_err(),
        WorkspaceWriteLeaseError::Busy
    );
    fs::write(root.join("child-release"), b"release").unwrap();
    assert!(child.wait().unwrap().success());

    let reacquired = WorkspaceWriteLease::acquire(&root).unwrap();
    drop(reacquired);
    cleanup(&root);
}

#[test]
fn killing_the_lock_owner_releases_the_os_lease_for_reacquisition() {
    if let Some(root) = std::env::var_os(KILL_CHILD_ROOT_ENV) {
        let root = PathBuf::from(root);
        let _lease = WorkspaceWriteLease::acquire(&root).unwrap();
        fs::write(root.join("kill-child-ready"), b"ready").unwrap();
        loop {
            thread::sleep(Duration::from_secs(1));
        }
    }

    let root = temp_root("kill-owner");
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "killing_the_lock_owner_releases_the_os_lease_for_reacquisition",
            "--nocapture",
        ])
        .env(KILL_CHILD_ROOT_ENV, &root)
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    while !root.join("kill-child-ready").exists() {
        assert!(
            child.try_wait().unwrap().is_none(),
            "lock-holder child exited before becoming ready"
        );
        assert!(Instant::now() < deadline, "lock-holder child timed out");
        thread::sleep(Duration::from_millis(5));
    }

    assert_eq!(
        WorkspaceWriteLease::acquire(&root).unwrap_err(),
        WorkspaceWriteLeaseError::Busy
    );
    child.kill().unwrap();
    let status = child.wait().unwrap();
    assert!(
        !status.success(),
        "killed lock-holder unexpectedly succeeded"
    );

    let reacquired = WorkspaceWriteLease::acquire(&root).unwrap();
    drop(reacquired);
    cleanup(&root);
}

#[test]
fn drop_releases_lock_and_reacquire_keeps_the_same_lock_file() {
    let root = temp_root("reacquire");
    let lock_path = root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH);
    {
        let _first = WorkspaceWriteLease::acquire(&root).unwrap();
        assert!(lock_path.is_file());
    }
    assert!(lock_path.is_file());

    let second = WorkspaceWriteLease::acquire(&root).unwrap();
    assert!(lock_path.is_file());
    drop(second);
    cleanup(&root);
}

#[test]
fn non_directory_workspace_is_stably_unsafe_and_pathless() {
    let parent = temp_root("file-root-CANARY_SECRET");
    let root = parent.join("workspace-file");
    fs::write(&root, b"not a directory").unwrap();

    let error = WorkspaceWriteLease::acquire(&root).unwrap_err();
    assert_eq!(error, WorkspaceWriteLeaseError::UnsafeWorkspace);
    assert_eq!(error.code(), "workspace.write_unsafe");
    assert_eq!(error.to_string(), "workspace.write_unsafe");
    assert!(!format!("{error:?}").contains(parent.to_string_lossy().as_ref()));

    cleanup(&parent);
}

#[cfg(any(unix, windows))]
#[test]
fn rejects_symlink_or_reparse_workspace_root_and_metadata_directory() {
    let parent = temp_root("aliases-CANARY_SECRET");
    let real = parent.join("real");
    let alias = parent.join("alias");
    let external = parent.join("external");
    fs::create_dir_all(&real).unwrap();
    fs::create_dir_all(&external).unwrap();

    if create_directory_link(&real, &alias).is_err() {
        cleanup(&parent);
        return;
    }
    let root_error = WorkspaceWriteLease::acquire(&alias).unwrap_err();
    assert_eq!(root_error, WorkspaceWriteLeaseError::UnsafeWorkspace);
    assert!(!root_error.to_string().contains("CANARY_SECRET"));

    fs::remove_dir(&alias).unwrap();
    if create_directory_link(&external, &real.join(".miho")).is_err() {
        cleanup(&parent);
        return;
    }
    let metadata_error = WorkspaceWriteLease::acquire(&real).unwrap_err();
    assert_eq!(metadata_error, WorkspaceWriteLeaseError::UnsafeWorkspace);
    assert!(!metadata_error.to_string().contains("CANARY_SECRET"));

    cleanup(&parent);
}

#[cfg(any(unix, windows))]
#[test]
fn rejects_alias_in_workspace_parent_chain() {
    let parent = temp_root("parent-alias");
    let real_parent = parent.join("real-parent");
    let linked_parent = parent.join("linked-parent");
    let real_workspace = real_parent.join("workspace");
    fs::create_dir_all(&real_workspace).unwrap();

    if create_directory_link(&real_parent, &linked_parent).is_err() {
        cleanup(&parent);
        return;
    }
    let error = WorkspaceWriteLease::acquire(&linked_parent.join("workspace")).unwrap_err();
    assert_eq!(error, WorkspaceWriteLeaseError::UnsafeWorkspace);

    cleanup(&parent);
}

#[cfg(any(unix, windows))]
#[test]
fn rejects_symlink_or_reparse_lock_target() {
    let parent = temp_root("lock-alias-CANARY_SECRET");
    let root = parent.join("workspace");
    let external = parent.join("external.lock");
    fs::create_dir_all(root.join(".miho")).unwrap();
    fs::write(&external, b"external").unwrap();
    let lock_path = root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH);

    if create_file_link(&external, &lock_path).is_err() {
        cleanup(&parent);
        return;
    }
    let error = WorkspaceWriteLease::acquire(&root).unwrap_err();
    assert_eq!(error, WorkspaceWriteLeaseError::UnsafeWorkspace);
    assert!(!error.to_string().contains("CANARY_SECRET"));

    cleanup(&parent);
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
