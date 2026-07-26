use std::{
    fs::{self, File, OpenOptions, TryLockError},
    io,
    path::{Path, PathBuf},
};

/// Stable location of the legacy-compatible workspace writer barrier.
pub const WORKSPACE_WRITE_LOCK_RELATIVE_PATH: &str = ".miho/workspace-write-v1.lock";
/// Reader/writer barrier protecting one coherent update-generation snapshot.
pub const WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH: &str = ".miho/workspace-snapshot-v1.lock";
/// New-writer-only mutex; readers never contend on this lock.
pub const WORKSPACE_WRITER_ARBITRATION_LOCK_RELATIVE_PATH: &str =
    ".miho/workspace-writer-arbitration-v1.lock";
/// Crash-released writer intent whose locked byte is probed by readers.
pub const WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH: &str =
    ".miho/workspace-writer-intent-v1.lock";

/// Stable, pathless failure categories for acquiring [`WorkspaceWriteLease`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkspaceWriteLeaseError {
    /// Another process (or another handle in this process) owns the lease.
    Busy,
    /// A workspace component or lock target is not a trusted regular path.
    UnsafeWorkspace,
    /// The operating system could not inspect, create, open, or lock the file.
    Unavailable,
}

impl WorkspaceWriteLeaseError {
    /// Stable machine-readable code suitable for CLI and desktop adapters.
    pub const fn code(self) -> &'static str {
        match self {
            Self::Busy => "workspace.write_busy",
            Self::UnsafeWorkspace => "workspace.write_unsafe",
            Self::Unavailable => "workspace.write_unavailable",
        }
    }
}

impl std::fmt::Display for WorkspaceWriteLeaseError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for WorkspaceWriteLeaseError {}

/// An OS-backed, workspace-wide exclusive writer lease.
///
/// The lock files are intentionally persistent. Dropping this value closes
/// the owned handles and releases the OS locks; crashes and normal process
/// exit receive the same release behavior without deleting or replacing them.
#[derive(Debug)]
pub struct WorkspaceWriteLease {
    workspace_root: PathBuf,
    // Field order is the lock release order: data barriers before intent, and
    // intent before the writer-only mutex.
    _legacy_file: File,
    _snapshot_file: File,
    _intent_file: File,
    _arbitration_file: File,
}

impl WorkspaceWriteLease {
    /// Acquire the exclusive writer lease for an existing workspace directory.
    pub fn acquire(workspace_root: &Path) -> Result<Self, WorkspaceWriteLeaseError> {
        let absolute_root = absolute_without_normalizing(workspace_root)?;
        reject_alias_chain(&absolute_root)?;
        require_directory(&absolute_root)?;

        let canonical_root =
            fs::canonicalize(&absolute_root).map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;
        reject_alias_chain(&canonical_root)?;
        require_directory(&canonical_root)?;

        let metadata_dir = canonical_root.join(".miho");
        ensure_metadata_directory(&metadata_dir)?;
        reject_alias_chain_from(&canonical_root, &metadata_dir)?;
        require_directory(&metadata_dir)?;

        // The arbitration lock is writer-only, so a failed non-blocking lock
        // unambiguously means another new writer is already active or waiting.
        let arbitration_file = open_lock_file(
            &canonical_root,
            WORKSPACE_WRITER_ARBITRATION_LOCK_RELATIVE_PATH,
        )?;
        let intent_file =
            open_lock_file(&canonical_root, WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH)?;
        let snapshot_file = open_lock_file(&canonical_root, WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH)?;
        let legacy_file = open_lock_file(&canonical_root, WORKSPACE_WRITE_LOCK_RELATIVE_PATH)?;

        try_lock_exclusive(&arbitration_file)?;

        // On Windows, readers observe this lock through mandatory byte-range
        // I/O rather than taking a competing lock. Publishing intent can
        // therefore block no first writer and depends on no waiter fairness.
        initialize_writer_intent_byte(&intent_file)?;
        intent_file
            .lock()
            .map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;

        // A reader probes intent both before and after taking its shared data
        // barriers. Once intent is exclusive, every later or in-flight reader
        // releases without reading, so this waits for a finite admitted set.
        snapshot_file
            .lock()
            .map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;

        // Every new reader releases legacy before snapshot. Therefore, after
        // snapshot becomes exclusive, legacy contention can only be an old
        // writer that does not participate in the new protocol.
        match legacy_file.try_lock() {
            Ok(()) => {}
            Err(TryLockError::WouldBlock) => return Err(WorkspaceWriteLeaseError::Busy),
            Err(TryLockError::Error(_)) => return Err(WorkspaceWriteLeaseError::Unavailable),
        }

        Ok(Self {
            workspace_root: canonical_root,
            _legacy_file: legacy_file,
            _snapshot_file: snapshot_file,
            _intent_file: intent_file,
            _arbitration_file: arbitration_file,
        })
    }

    /// Canonical root whose writer namespace this lease protects.
    pub fn workspace_root(&self) -> &Path {
        &self.workspace_root
    }
}

/// Shared, read-only lease for one coherent update-generation snapshot.
/// Writers wait for existing snapshot readers after winning writer
/// arbitration, so a health check can never make a button update fail busy.
#[derive(Debug)]
pub struct WorkspaceSnapshotLease {
    workspace_root: PathBuf,
    // Release legacy before snapshot so a writer that has drained snapshot
    // cannot mistake a still-dropping new reader for an old exclusive writer.
    _legacy_file: File,
    _snapshot_file: File,
}

impl WorkspaceSnapshotLease {
    pub fn acquire(workspace_root: &Path) -> Result<Self, WorkspaceWriteLeaseError> {
        let absolute_root = absolute_without_normalizing(workspace_root)?;
        reject_alias_chain(&absolute_root)?;
        require_directory(&absolute_root)?;

        let canonical_root =
            fs::canonicalize(&absolute_root).map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;
        reject_alias_chain(&canonical_root)?;
        require_directory(&canonical_root)?;

        let metadata_dir = canonical_root.join(".miho");
        ensure_metadata_directory(&metadata_dir)?;
        reject_alias_chain_from(&canonical_root, &metadata_dir)?;
        require_directory(&metadata_dir)?;

        let intent_file =
            open_lock_file(&canonical_root, WORKSPACE_WRITER_INTENT_LOCK_RELATIVE_PATH)?;
        let snapshot_file = open_lock_file(&canonical_root, WORKSPACE_SNAPSHOT_LOCK_RELATIVE_PATH)?;
        let legacy_file = open_lock_file(&canonical_root, WORKSPACE_WRITE_LOCK_RELATIVE_PATH)?;

        probe_writer_intent(&intent_file)?;
        try_lock_shared(&snapshot_file)?;
        try_lock_shared(&legacy_file)?;
        probe_writer_intent(&intent_file)?;

        Ok(Self {
            workspace_root: canonical_root,
            _legacy_file: legacy_file,
            _snapshot_file: snapshot_file,
        })
    }

    pub fn workspace_root(&self) -> &Path {
        &self.workspace_root
    }
}

fn try_lock_exclusive(file: &File) -> Result<(), WorkspaceWriteLeaseError> {
    match file.try_lock() {
        Ok(()) => Ok(()),
        Err(TryLockError::WouldBlock) => Err(WorkspaceWriteLeaseError::Busy),
        Err(TryLockError::Error(_)) => Err(WorkspaceWriteLeaseError::Unavailable),
    }
}

fn try_lock_shared(file: &File) -> Result<(), WorkspaceWriteLeaseError> {
    match file.try_lock_shared() {
        Ok(()) => Ok(()),
        Err(TryLockError::WouldBlock) => Err(WorkspaceWriteLeaseError::Busy),
        Err(TryLockError::Error(_)) => Err(WorkspaceWriteLeaseError::Unavailable),
    }
}

#[cfg(windows)]
fn initialize_writer_intent_byte(file: &File) -> Result<(), WorkspaceWriteLeaseError> {
    use std::os::windows::fs::FileExt;

    match file.seek_write(&[0], 0) {
        Ok(1) => Ok(()),
        Ok(_) => Err(WorkspaceWriteLeaseError::Unavailable),
        Err(_) => Err(WorkspaceWriteLeaseError::Unavailable),
    }
}

#[cfg(windows)]
fn probe_writer_intent(file: &File) -> Result<(), WorkspaceWriteLeaseError> {
    use std::os::windows::fs::FileExt;
    use windows_sys::Win32::Foundation::ERROR_LOCK_VIOLATION;

    match file.seek_write(&[0], 0) {
        Ok(1) => Ok(()),
        Ok(_) => Err(WorkspaceWriteLeaseError::Unavailable),
        Err(error) if error.raw_os_error() == Some(ERROR_LOCK_VIOLATION as i32) => {
            Err(WorkspaceWriteLeaseError::Busy)
        }
        Err(_) => Err(WorkspaceWriteLeaseError::Unavailable),
    }
}

#[cfg(not(windows))]
fn initialize_writer_intent_byte(_file: &File) -> Result<(), WorkspaceWriteLeaseError> {
    Ok(())
}

#[cfg(not(windows))]
fn probe_writer_intent(file: &File) -> Result<(), WorkspaceWriteLeaseError> {
    // Advisory-lock fallback keeps the same safety ordering on non-Windows;
    // the mandatory, fairness-independent product contract is Windows-only.
    try_lock_shared(file)?;
    File::unlock(file).map_err(|_| WorkspaceWriteLeaseError::Unavailable)
}

fn open_lock_file(
    canonical_root: &Path,
    relative_path: &str,
) -> Result<File, WorkspaceWriteLeaseError> {
    let lock_path = canonical_root.join(relative_path);
    reject_existing_lock_target(&lock_path)?;
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(&lock_path)
        .map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;

    // Re-check after opening so a stable symlink/reparse target cannot be
    // accepted merely because it appeared between inspection and open.
    reject_alias_chain_from(canonical_root, &lock_path)?;
    require_regular_file(&lock_path)?;
    Ok(file)
}

fn absolute_without_normalizing(path: &Path) -> Result<PathBuf, WorkspaceWriteLeaseError> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        std::env::current_dir()
            .map(|cwd| cwd.join(path))
            .map_err(|_| WorkspaceWriteLeaseError::Unavailable)
    }
}

fn ensure_metadata_directory(path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    match fs::create_dir(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(_) => Err(WorkspaceWriteLeaseError::Unavailable),
    }
}

fn reject_alias_chain(path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    for candidate in path.ancestors().collect::<Vec<_>>().into_iter().rev() {
        if candidate.as_os_str().is_empty() {
            continue;
        }
        let metadata =
            fs::symlink_metadata(candidate).map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;
        if is_symlink_or_reparse(&metadata) {
            return Err(WorkspaceWriteLeaseError::UnsafeWorkspace);
        }
    }
    Ok(())
}

fn reject_alias_chain_from(root: &Path, path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    let suffix = path
        .strip_prefix(root)
        .map_err(|_| WorkspaceWriteLeaseError::UnsafeWorkspace)?;
    let mut current = root.to_path_buf();
    require_not_alias(&current)?;
    for component in suffix.components() {
        current.push(component);
        require_not_alias(&current)?;
    }
    Ok(())
}

fn reject_existing_lock_target(path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if is_symlink_or_reparse(&metadata) || !metadata.is_file() => {
            Err(WorkspaceWriteLeaseError::UnsafeWorkspace)
        }
        Ok(_) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(_) => Err(WorkspaceWriteLeaseError::Unavailable),
    }
}

fn require_not_alias(path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;
    if is_symlink_or_reparse(&metadata) {
        Err(WorkspaceWriteLeaseError::UnsafeWorkspace)
    } else {
        Ok(())
    }
}

fn require_directory(path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;
    if is_symlink_or_reparse(&metadata) || !metadata.is_dir() {
        Err(WorkspaceWriteLeaseError::UnsafeWorkspace)
    } else {
        Ok(())
    }
}

fn require_regular_file(path: &Path) -> Result<(), WorkspaceWriteLeaseError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| WorkspaceWriteLeaseError::Unavailable)?;
    if is_symlink_or_reparse(&metadata) || !metadata.is_file() {
        Err(WorkspaceWriteLeaseError::UnsafeWorkspace)
    } else {
        Ok(())
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
