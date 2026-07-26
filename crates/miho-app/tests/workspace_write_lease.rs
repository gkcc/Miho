use std::{
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    process::Command,
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use miho_app::{
    WorkspaceSnapshotLease, WorkspaceWriteLease, WorkspaceWriteLeaseError,
    WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH, WORKSPACE_WRITER_ARBITRATION_LOCK_RELATIVE_PATH,
    WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH, WORKSPACE_WRITE_LOCK_RELATIVE_PATH,
};

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);
const CHILD_ROOT_ENV: &str = "MIHO_WORKSPACE_WRITE_LEASE_CHILD_ROOT";
const KILL_CHILD_ROOT_ENV: &str = "MIHO_WORKSPACE_WRITE_LEASE_KILL_CHILD_ROOT";
const LEGACY_WRITER_CHILD_ROOT_ENV: &str = "MIHO_WORKSPACE_LEGACY_WRITER_CHILD_ROOT";
const INTENT_LOCK_CHILD_ROOT_ENV: &str = "MIHO_WORKSPACE_INTENT_LOCK_CHILD_ROOT";

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

#[cfg(windows)]
fn wait_for_published_writer_intent(root: &Path) {
    use std::os::windows::fs::FileExt;
    use windows_sys::Win32::Foundation::ERROR_LOCK_VIOLATION;

    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        match OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.join(WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH))
        {
            Ok(file) => match file.seek_write(&[0], 0) {
                Err(error) if error.raw_os_error() == Some(ERROR_LOCK_VIOLATION as i32) => {
                    return;
                }
                Ok(1) => {}
                Ok(written) => panic!("unexpected intent probe length: {written}"),
                Err(error) => panic!("unexpected intent probe failure: {error}"),
            },
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => panic!("unexpected intent open failure: {error}"),
        }
        assert!(
            Instant::now() < deadline,
            "writer never published mandatory intent"
        );
        thread::yield_now();
    }
}

#[cfg(not(windows))]
fn wait_for_published_writer_intent(root: &Path) {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        match WorkspaceSnapshotLease::acquire(root) {
            Err(WorkspaceWriteLeaseError::Busy) => return,
            Ok(probe) => drop(probe),
            Err(error) => panic!("unexpected reader-probe failure: {error}"),
        }
        assert!(
            Instant::now() < deadline,
            "writer never published advisory intent"
        );
        thread::yield_now();
    }
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
fn writer_waits_for_health_snapshot_instead_of_reporting_busy() {
    let root = temp_root("snapshot-reader-before-writer");
    let snapshot = WorkspaceSnapshotLease::acquire(&root).unwrap();
    assert_eq!(snapshot.workspace_root(), fs::canonicalize(&root).unwrap());
    assert!(root.join(WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH).is_file());
    let (result_tx, result_rx) = mpsc::channel();
    let writer_root = root.clone();
    let writer = thread::spawn(move || {
        let result = WorkspaceWriteLease::acquire(&writer_root).map(|lease| {
            drop(lease);
        });
        result_tx.send(result).unwrap();
    });

    wait_for_published_writer_intent(&root);
    assert!(
        result_rx.recv_timeout(Duration::from_millis(100)).is_err(),
        "writer should wait for the coherent health snapshot"
    );
    drop(snapshot);
    assert_eq!(
        result_rx.recv_timeout(Duration::from_secs(5)).unwrap(),
        Ok(())
    );
    writer.join().unwrap();
    cleanup(&root);
}

#[cfg(windows)]
#[test]
fn writer_intent_lock_mandatorily_denies_second_handle_io() {
    use std::os::windows::fs::FileExt;
    use windows_sys::Win32::Foundation::ERROR_LOCK_VIOLATION;

    let root = temp_root("mandatory-intent-same-process");
    fs::create_dir_all(root.join(".miho")).unwrap();
    let intent_path = root.join(WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH);
    let writer_handle = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(&intent_path)
        .unwrap();
    assert_eq!(writer_handle.seek_write(&[0], 0).unwrap(), 1);
    writer_handle.lock().unwrap();

    let probe_handle = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&intent_path)
        .unwrap();
    let error = probe_handle.seek_write(&[0], 0).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(ERROR_LOCK_VIOLATION as i32));

    drop(writer_handle);
    assert_eq!(probe_handle.seek_write(&[0], 0).unwrap(), 1);
    drop(probe_handle);
    cleanup(&root);
}

#[cfg(windows)]
#[test]
fn writer_intent_lock_mandatory_io_is_cross_process() {
    use std::os::windows::fs::FileExt;
    use windows_sys::Win32::Foundation::ERROR_LOCK_VIOLATION;

    if let Some(root) = std::env::var_os(INTENT_LOCK_CHILD_ROOT_ENV) {
        let root = PathBuf::from(root);
        fs::create_dir_all(root.join(".miho")).unwrap();
        let intent_file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(root.join(WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH))
            .unwrap();
        assert_eq!(intent_file.seek_write(&[0], 0).unwrap(), 1);
        intent_file.lock().unwrap();
        fs::write(root.join("intent-child-ready"), b"ready").unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        while !root.join("intent-child-release").exists() {
            assert!(Instant::now() < deadline, "parent did not release child");
            thread::sleep(Duration::from_millis(5));
        }
        return;
    }

    let root = temp_root("mandatory-intent-cross-process");
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "writer_intent_lock_mandatory_io_is_cross_process",
            "--nocapture",
        ])
        .env(INTENT_LOCK_CHILD_ROOT_ENV, &root)
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    while !root.join("intent-child-ready").exists() {
        assert!(
            child.try_wait().unwrap().is_none(),
            "intent lock-holder child exited before becoming ready"
        );
        assert!(Instant::now() < deadline, "intent child timed out");
        thread::sleep(Duration::from_millis(5));
    }

    let probe_handle = OpenOptions::new()
        .read(true)
        .write(true)
        .open(root.join(WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH))
        .unwrap();
    let error = probe_handle.seek_write(&[0], 0).unwrap_err();
    assert_eq!(error.raw_os_error(), Some(ERROR_LOCK_VIOLATION as i32));

    fs::write(root.join("intent-child-release"), b"release").unwrap();
    assert!(child.wait().unwrap().success());
    assert_eq!(probe_handle.seek_write(&[0], 0).unwrap(), 1);
    drop(probe_handle);
    cleanup(&root);
}

#[test]
fn pending_writer_blocks_later_readers_and_finishes_after_first_reader_releases() {
    let root = temp_root("pending-writer-closes-reader-gate");
    let first_reader = WorkspaceSnapshotLease::acquire(&root).unwrap();
    let (result_tx, result_rx) = mpsc::channel();
    let writer_root = root.clone();
    let writer = thread::spawn(move || {
        let result = WorkspaceWriteLease::acquire(&writer_root).map(drop);
        result_tx.send(result).unwrap();
    });

    wait_for_published_writer_intent(&root);
    for _ in 0..16 {
        assert_eq!(
            WorkspaceSnapshotLease::acquire(&root).unwrap_err(),
            WorkspaceWriteLeaseError::Busy,
            "every reader arriving behind the writer must be rejected"
        );
    }
    assert!(
        result_rx.recv_timeout(Duration::from_millis(25)).is_err(),
        "writer cannot finish while the first reader still holds its snapshot"
    );

    drop(first_reader);
    assert_eq!(
        result_rx.recv_timeout(Duration::from_secs(5)).unwrap(),
        Ok(())
    );
    writer.join().unwrap();
    cleanup(&root);
}

#[test]
fn second_writer_is_busy_while_first_writer_waits_for_a_reader() {
    let root = temp_root("pending-writer-rejects-second-writer");
    let first_reader = WorkspaceSnapshotLease::acquire(&root).unwrap();
    let (result_tx, result_rx) = mpsc::channel();
    let writer_root = root.clone();
    let first_writer = thread::spawn(move || {
        let result = WorkspaceWriteLease::acquire(&writer_root).map(drop);
        result_tx.send(result).unwrap();
    });

    wait_for_published_writer_intent(&root);
    assert_eq!(
        WorkspaceWriteLease::acquire(&root).unwrap_err(),
        WorkspaceWriteLeaseError::Busy
    );

    drop(first_reader);
    assert_eq!(
        result_rx.recv_timeout(Duration::from_secs(5)).unwrap(),
        Ok(())
    );
    first_writer.join().unwrap();
    cleanup(&root);
}

#[test]
fn health_snapshot_reports_busy_while_writer_is_active() {
    let root = temp_root("writer-before-snapshot-reader");
    let writer = WorkspaceWriteLease::acquire(&root).unwrap();

    assert_eq!(
        WorkspaceSnapshotLease::acquire(&root).unwrap_err(),
        WorkspaceWriteLeaseError::Busy
    );

    drop(writer);
    cleanup(&root);
}

#[test]
fn legacy_writer_only_blocks_new_snapshot_reader_across_processes() {
    if let Some(root) = std::env::var_os(LEGACY_WRITER_CHILD_ROOT_ENV) {
        let root = PathBuf::from(root);
        fs::create_dir_all(root.join(".miho")).unwrap();
        let legacy_file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH))
            .unwrap();
        legacy_file.lock().unwrap();
        fs::write(root.join("legacy-child-ready"), b"ready").unwrap();
        let deadline = Instant::now() + Duration::from_secs(10);
        while !root.join("legacy-child-release").exists() {
            assert!(Instant::now() < deadline, "parent did not release child");
            thread::sleep(Duration::from_millis(5));
        }
        return;
    }

    let root = temp_root("legacy-writer-blocks-reader");
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "legacy_writer_only_blocks_new_snapshot_reader_across_processes",
            "--nocapture",
        ])
        .env(LEGACY_WRITER_CHILD_ROOT_ENV, &root)
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    while !root.join("legacy-child-ready").exists() {
        assert!(
            child.try_wait().unwrap().is_none(),
            "legacy lock-holder child exited before becoming ready"
        );
        assert!(
            Instant::now() < deadline,
            "legacy lock-holder child timed out"
        );
        thread::sleep(Duration::from_millis(5));
    }

    assert!(root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH).is_file());
    assert!(!root.join(WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH).exists());
    assert!(!root
        .join(WORKSPACE_WRITER_ARBITRATION_LOCK_RELATIVE_PATH)
        .exists());
    assert!(!root
        .join(WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH)
        .exists());
    assert_eq!(
        WorkspaceSnapshotLease::acquire(&root).unwrap_err(),
        WorkspaceWriteLeaseError::Busy
    );
    assert_eq!(
        WorkspaceWriteLease::acquire(&root).unwrap_err(),
        WorkspaceWriteLeaseError::Busy,
        "an active legacy writer must also reject a new writer"
    );

    fs::write(root.join("legacy-child-release"), b"release").unwrap();
    assert!(child.wait().unwrap().success());
    drop(WorkspaceSnapshotLease::acquire(&root).unwrap());
    cleanup(&root);
}

#[test]
fn new_writer_yields_safely_to_a_previous_l_then_s_writer_holding_legacy() {
    let root = temp_root("previous-l-then-s-writer-new-wins-snapshot");
    fs::create_dir_all(root.join(".miho")).unwrap();
    let legacy_file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH))
        .unwrap();
    legacy_file.lock().unwrap();
    let snapshot_reader = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(root.join(WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH))
        .unwrap();
    snapshot_reader.lock_shared().unwrap();

    let (result_tx, result_rx) = mpsc::channel();
    let writer_root = root.clone();
    let new_writer = thread::spawn(move || {
        result_tx
            .send(WorkspaceWriteLease::acquire(&writer_root).map(drop))
            .unwrap();
    });
    wait_for_published_writer_intent(&root);

    // The new writer now wins snapshot, observes the previous writer's
    // already-owned legacy lock, and yields Busy without waiting in reverse
    // lock order. The previous writer can then finish L -> S normally.
    drop(snapshot_reader);
    assert_eq!(
        result_rx.recv_timeout(Duration::from_secs(5)).unwrap(),
        Err(WorkspaceWriteLeaseError::Busy)
    );
    new_writer.join().unwrap();
    let previous_snapshot = OpenOptions::new()
        .read(true)
        .write(true)
        .open(root.join(WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH))
        .unwrap();
    previous_snapshot.lock().unwrap();
    drop(previous_snapshot);
    drop(legacy_file);
    cleanup(&root);
}

#[test]
fn new_writer_waits_then_succeeds_after_previous_l_then_s_writer_releases() {
    let root = temp_root("previous-l-then-s-writer-active");
    fs::create_dir_all(root.join(".miho")).unwrap();
    let legacy_file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH))
        .unwrap();
    legacy_file.lock().unwrap();
    let previous_snapshot = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(root.join(WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH))
        .unwrap();
    previous_snapshot.lock().unwrap();

    let (result_tx, result_rx) = mpsc::channel();
    let writer_root = root.clone();
    let new_writer = thread::spawn(move || {
        result_tx
            .send(WorkspaceWriteLease::acquire(&writer_root).map(drop))
            .unwrap();
    });
    wait_for_published_writer_intent(&root);
    assert!(
        result_rx.recv_timeout(Duration::from_millis(50)).is_err(),
        "new writer must wait while the previous writer still owns snapshot"
    );

    // Match the immediately previous implementation's field drop order.
    drop(legacy_file);
    drop(previous_snapshot);
    assert_eq!(
        result_rx.recv_timeout(Duration::from_secs(5)).unwrap(),
        Ok(())
    );
    new_writer.join().unwrap();
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

    let deadline = Instant::now() + Duration::from_secs(5);
    let recovered_reader = loop {
        match WorkspaceSnapshotLease::acquire(&root) {
            Ok(reader) => break reader,
            Err(WorkspaceWriteLeaseError::Busy) if Instant::now() < deadline => {
                thread::sleep(Duration::from_millis(5));
            }
            Err(error) => panic!("snapshot did not recover after writer death: {error}"),
        }
    };
    drop(recovered_reader);
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
