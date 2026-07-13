use std::{
    fs::{self, File, OpenOptions, TryLockError},
    io,
    path::{Path, PathBuf},
};

/// Stable location of the workspace-wide writer lock.
pub const WORKSPACE_WRITE_LOCK_RELATIVE_PATH: &str = ".miho/workspace-write-v1.lock";

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
/// The lock file is intentionally persistent. Dropping this value closes the
/// only owned handle and releases the OS lock; crashes and normal process exit
/// receive the same release behavior without deleting or replacing the file.
#[derive(Debug)]
pub struct WorkspaceWriteLease {
    workspace_root: PathBuf,
    _file: File,
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

        let lock_path = canonical_root.join(WORKSPACE_WRITE_LOCK_RELATIVE_PATH);
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
        reject_alias_chain_from(&canonical_root, &lock_path)?;
        require_regular_file(&lock_path)?;

        match file.try_lock() {
            Ok(()) => Ok(Self {
                workspace_root: canonical_root,
                _file: file,
            }),
            Err(TryLockError::WouldBlock) => Err(WorkspaceWriteLeaseError::Busy),
            Err(TryLockError::Error(_)) => Err(WorkspaceWriteLeaseError::Unavailable),
        }
    }

    /// Canonical root whose writer namespace this lease protects.
    pub fn workspace_root(&self) -> &Path {
        &self.workspace_root
    }
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
