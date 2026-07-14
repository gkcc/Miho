use std::{
    fs, io,
    path::{Component, Path, PathBuf},
};

use serde::Deserialize;

pub const PORTABLE_MARKER_SCHEMA_V1: &str = "miho-portable-v1";
pub const PORTABLE_MARKER_FILE_V1: &str = "miho-portable-v1.json";
pub const PORTABLE_WORKSPACE_DIRECTORY_V1: &str = "data";
pub const MAX_PORTABLE_MARKER_BYTES_V1: u64 = 4 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PortableWorkspaceError {
    InvalidExecutablePath,
    UnsafePath,
    MarkerTooLarge,
    MarkerUnavailable,
    InvalidMarker,
    WorkspaceUnavailable,
    IdentityInvalid,
    IdentityTooLarge,
}

impl PortableWorkspaceError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidExecutablePath => "portable.executable_path_invalid",
            Self::UnsafePath => "portable.path_unsafe",
            Self::MarkerTooLarge => "portable.marker_too_large",
            Self::MarkerUnavailable => "portable.marker_unavailable",
            Self::InvalidMarker => "portable.marker_invalid",
            Self::WorkspaceUnavailable => "portable.workspace_unavailable",
            Self::IdentityInvalid => "portable.identity_invalid",
            Self::IdentityTooLarge => "portable.identity_too_large",
        }
    }
}

impl std::fmt::Display for PortableWorkspaceError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for PortableWorkspaceError {}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PortableMarkerV1 {
    schema_version: String,
    workspace: String,
}

/// Detect an explicitly enabled portable workspace beside an executable.
///
/// The executable path must be an absolute, lexically normal path such as the
/// value returned by `std::env::current_exe`. A missing marker means portable
/// mode is disabled. Once a marker exists, every malformed, oversized, linked,
/// or otherwise unsafe state fails closed before the `data` directory is
/// created or returned.
pub fn detect_portable_workspace_v1(
    executable: &Path,
) -> Result<Option<PathBuf>, PortableWorkspaceError> {
    let executable = validate_executable_path(executable)?;
    let executable_directory = executable
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .ok_or(PortableWorkspaceError::InvalidExecutablePath)?;

    let marker_path = executable_directory.join(PORTABLE_MARKER_FILE_V1);
    // A missing marker always means normal installed-mode selection. Only an
    // existing marker opts into the stricter portable path-chain contract.
    match fs::symlink_metadata(&marker_path) {
        Ok(_) => require_existing_directory_chain(executable_directory)?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(PortableWorkspaceError::MarkerUnavailable),
    }
    let marker_bytes = match inspect_marker(&marker_path)? {
        Some(bytes) => bytes,
        // The marker disappeared after the existence check. It participated in
        // portable detection, so fail closed instead of silently falling back.
        None => return Err(PortableWorkspaceError::MarkerUnavailable),
    };
    let marker = serde_json::from_slice::<PortableMarkerV1>(&marker_bytes)
        .map_err(|_| PortableWorkspaceError::InvalidMarker)?;
    if marker.schema_version != PORTABLE_MARKER_SCHEMA_V1
        || marker.workspace != PORTABLE_WORKSPACE_DIRECTORY_V1
    {
        return Err(PortableWorkspaceError::InvalidMarker);
    }

    let workspace = executable_directory.join(&marker.workspace);
    ensure_portable_workspace(&workspace, executable_directory).map(Some)
}

fn validate_executable_path(path: &Path) -> Result<PathBuf, PortableWorkspaceError> {
    if !path.is_absolute() || path.file_name().is_none() {
        return Err(PortableWorkspaceError::InvalidExecutablePath);
    }
    if path.components().any(|component| {
        !matches!(
            component,
            Component::Prefix(_) | Component::RootDir | Component::Normal(_)
        )
    }) {
        return Err(PortableWorkspaceError::InvalidExecutablePath);
    }
    Ok(path.to_path_buf())
}

fn inspect_marker(path: &Path) -> Result<Option<Vec<u8>>, PortableWorkspaceError> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(PortableWorkspaceError::MarkerUnavailable),
    };
    if is_symlink_or_reparse(&metadata) || !metadata.is_file() {
        return Err(PortableWorkspaceError::UnsafePath);
    }
    if metadata.len() > MAX_PORTABLE_MARKER_BYTES_V1 {
        return Err(PortableWorkspaceError::MarkerTooLarge);
    }
    let bytes = fs::read(path).map_err(|_| PortableWorkspaceError::MarkerUnavailable)?;
    let after =
        fs::symlink_metadata(path).map_err(|_| PortableWorkspaceError::MarkerUnavailable)?;
    if is_symlink_or_reparse(&after) || !after.is_file() {
        return Err(PortableWorkspaceError::UnsafePath);
    }
    if after.len() > MAX_PORTABLE_MARKER_BYTES_V1
        || bytes.len() as u64 > MAX_PORTABLE_MARKER_BYTES_V1
    {
        return Err(PortableWorkspaceError::MarkerTooLarge);
    }
    if after.len() != bytes.len() as u64 {
        return Err(PortableWorkspaceError::MarkerUnavailable);
    }
    Ok(Some(bytes))
}

fn ensure_portable_workspace(
    workspace: &Path,
    executable_directory: &Path,
) -> Result<PathBuf, PortableWorkspaceError> {
    // Revalidate immediately before inspecting or creating `data`; marker
    // parsing must not leave a stale parent-chain decision in force.
    require_existing_directory_chain(executable_directory)?;
    match fs::symlink_metadata(workspace) {
        Ok(metadata) => require_safe_directory(&metadata)?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            require_existing_directory_chain(executable_directory)?;
            match fs::create_dir(workspace) {
                Ok(()) => {}
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
                Err(_) => return Err(PortableWorkspaceError::WorkspaceUnavailable),
            }
        }
        Err(_) => return Err(PortableWorkspaceError::WorkspaceUnavailable),
    }

    require_existing_directory_chain(workspace)?;
    let canonical_parent = fs::canonicalize(executable_directory)
        .map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
    let canonical_workspace =
        fs::canonicalize(workspace).map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
    if !paths_equal(
        &canonical_workspace,
        &canonical_parent.join(PORTABLE_WORKSPACE_DIRECTORY_V1),
    ) {
        return Err(PortableWorkspaceError::UnsafePath);
    }
    require_existing_directory_chain(&canonical_workspace)?;
    Ok(canonical_workspace)
}

fn require_existing_directory_chain(path: &Path) -> Result<(), PortableWorkspaceError> {
    for candidate in path.ancestors().collect::<Vec<_>>().into_iter().rev() {
        if candidate.as_os_str().is_empty() {
            continue;
        }
        let metadata = fs::symlink_metadata(candidate)
            .map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
        require_safe_directory(&metadata)?;
    }
    Ok(())
}

fn require_safe_directory(metadata: &fs::Metadata) -> Result<(), PortableWorkspaceError> {
    if is_symlink_or_reparse(metadata) || !metadata.is_dir() {
        Err(PortableWorkspaceError::UnsafePath)
    } else {
        Ok(())
    }
}

fn paths_equal(left: &Path, right: &Path) -> bool {
    #[cfg(windows)]
    {
        left.to_string_lossy()
            .eq_ignore_ascii_case(&right.to_string_lossy())
    }
    #[cfg(not(windows))]
    {
        left == right
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

    fn temp_root(label: &str) -> PathBuf {
        let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
        let root =
            std::env::temp_dir().join(format!("miho-portable-{label}-{}-{id}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root
    }

    fn executable(root: &Path) -> PathBuf {
        root.join("miho-desktop.exe")
    }

    fn marker(root: &Path) -> PathBuf {
        root.join(PORTABLE_MARKER_FILE_V1)
    }

    fn valid_marker() -> &'static [u8] {
        br#"{"schema_version":"miho-portable-v1","workspace":"data"}"#
    }

    #[test]
    fn portable_marker_missing_disables_portable_mode_without_creating_data() {
        let root = temp_root("missing");

        assert_eq!(detect_portable_workspace_v1(&executable(&root)), Ok(None));
        assert!(!root.join(PORTABLE_WORKSPACE_DIRECTORY_V1).exists());

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn portable_marker_missing_does_not_activate_reparse_path_checks() {
        let parent = temp_root("missing-linked-parent");
        let real = parent.join("real-app");
        let linked = parent.join("linked-app");
        fs::create_dir(&real).unwrap();
        if create_directory_link(&real, &linked).is_err() {
            fs::remove_dir_all(parent).unwrap();
            return;
        }

        assert_eq!(detect_portable_workspace_v1(&executable(&linked)), Ok(None));
        assert!(!real.join("data").exists());

        remove_directory_link(&linked);
        fs::remove_dir_all(parent).unwrap();
    }

    #[test]
    fn portable_valid_marker_creates_and_returns_real_absolute_data_directory() {
        let root = temp_root("create-中文 space");
        fs::write(marker(&root), valid_marker()).unwrap();

        let detected = detect_portable_workspace_v1(&executable(&root))
            .unwrap()
            .unwrap();
        assert!(detected.is_absolute());
        assert_eq!(detected, fs::canonicalize(root.join("data")).unwrap());
        assert!(detected.is_dir());

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn portable_existing_data_directory_is_reused_without_touching_contents() {
        let root = temp_root("existing");
        fs::write(marker(&root), valid_marker()).unwrap();
        fs::create_dir(root.join("data")).unwrap();
        fs::write(root.join("data/keep-me.txt"), b"user data").unwrap();

        let detected = detect_portable_workspace_v1(&executable(&root))
            .unwrap()
            .unwrap();
        assert_eq!(
            fs::read(detected.join("keep-me.txt")).unwrap(),
            b"user data"
        );

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn portable_invalid_marker_variants_fail_before_data_creation() {
        let invalid_markers: &[&[u8]] = &[
            br#"{"schema_version":"future","workspace":"data"}"#,
            br#"{"schema_version":"miho-portable-v1","workspace":"Data"}"#,
            br#"{"schema_version":"miho-portable-v1","workspace":"./data"}"#,
            br#"{"schema_version":"miho-portable-v1","workspace":"../data"}"#,
            br#"{"schema_version":"miho-portable-v1","workspace":"data","unknown":true}"#,
            br#"{"schema_version":"miho-portable-v1"}"#,
            br#"not-json"#,
        ];
        for (index, bytes) in invalid_markers.iter().enumerate() {
            let root = temp_root(&format!("invalid-{index}"));
            fs::write(marker(&root), bytes).unwrap();

            assert_eq!(
                detect_portable_workspace_v1(&executable(&root)),
                Err(PortableWorkspaceError::InvalidMarker)
            );
            assert!(!root.join("data").exists());

            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn portable_oversized_marker_fails_before_data_creation() {
        let root = temp_root("oversized");
        fs::write(
            marker(&root),
            vec![b' '; MAX_PORTABLE_MARKER_BYTES_V1 as usize + 1],
        )
        .unwrap();

        assert_eq!(
            detect_portable_workspace_v1(&executable(&root)),
            Err(PortableWorkspaceError::MarkerTooLarge)
        );
        assert!(!root.join("data").exists());

        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn portable_non_regular_marker_and_workspace_fail_closed() {
        let marker_root = temp_root("marker-directory");
        fs::create_dir(marker(&marker_root)).unwrap();
        assert_eq!(
            detect_portable_workspace_v1(&executable(&marker_root)),
            Err(PortableWorkspaceError::UnsafePath)
        );
        assert!(!marker_root.join("data").exists());
        fs::remove_dir_all(marker_root).unwrap();

        let data_root = temp_root("data-file");
        fs::write(marker(&data_root), valid_marker()).unwrap();
        fs::write(data_root.join("data"), b"not a directory").unwrap();
        assert_eq!(
            detect_portable_workspace_v1(&executable(&data_root)),
            Err(PortableWorkspaceError::UnsafePath)
        );
        fs::remove_dir_all(data_root).unwrap();
    }

    #[test]
    fn portable_relative_or_non_normal_executable_path_is_rejected() {
        assert_eq!(
            detect_portable_workspace_v1(Path::new("miho-desktop.exe")),
            Err(PortableWorkspaceError::InvalidExecutablePath)
        );
        let root = temp_root("dot-component");
        let dotted = root.join("sub/../miho-desktop.exe");
        assert_eq!(
            detect_portable_workspace_v1(&dotted),
            Err(PortableWorkspaceError::InvalidExecutablePath)
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn portable_marker_link_fails_closed_without_touching_external_file() {
        let parent = temp_root("marker-link");
        let root = parent.join("app");
        let external = parent.join("external-marker.json");
        fs::create_dir(&root).unwrap();
        fs::write(&external, valid_marker()).unwrap();
        if create_file_link(&external, &marker(&root)).is_err() {
            fs::remove_dir_all(parent).unwrap();
            return;
        }

        assert_eq!(
            detect_portable_workspace_v1(&executable(&root)),
            Err(PortableWorkspaceError::UnsafePath)
        );
        assert_eq!(fs::read(external).unwrap(), valid_marker());
        assert!(!root.join("data").exists());

        fs::remove_dir_all(parent).unwrap();
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn portable_reparse_parent_fails_closed_before_creating_real_data() {
        let parent = temp_root("parent-link");
        let real = parent.join("real-app");
        let linked = parent.join("linked-app");
        fs::create_dir(&real).unwrap();
        fs::write(marker(&real), valid_marker()).unwrap();
        if create_directory_link(&real, &linked).is_err() {
            fs::remove_dir_all(parent).unwrap();
            return;
        }

        assert_eq!(
            detect_portable_workspace_v1(&executable(&linked)),
            Err(PortableWorkspaceError::UnsafePath)
        );
        assert!(!real.join("data").exists());

        remove_directory_link(&linked);
        fs::remove_dir_all(parent).unwrap();
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn portable_linked_data_directory_fails_closed_without_touching_external_data() {
        let parent = temp_root("data-link");
        let root = parent.join("app");
        let external = parent.join("external-data");
        fs::create_dir(&root).unwrap();
        fs::create_dir(&external).unwrap();
        fs::write(marker(&root), valid_marker()).unwrap();
        fs::write(external.join("keep-me.txt"), b"external").unwrap();
        let linked_data = root.join("data");
        if create_directory_link(&external, &linked_data).is_err() {
            fs::remove_dir_all(parent).unwrap();
            return;
        }

        assert_eq!(
            detect_portable_workspace_v1(&executable(&root)),
            Err(PortableWorkspaceError::UnsafePath)
        );
        assert_eq!(fs::read(external.join("keep-me.txt")).unwrap(), b"external");

        remove_directory_link(&linked_data);
        fs::remove_dir_all(parent).unwrap();
    }

    #[test]
    fn portable_errors_are_stable_and_pathless() {
        let root = temp_root("CANARY_USERNAME");
        fs::write(marker(&root), b"broken").unwrap();

        let error = detect_portable_workspace_v1(&executable(&root)).unwrap_err();
        assert_eq!(error.to_string(), "portable.marker_invalid");
        assert!(!error.to_string().contains("CANARY_USERNAME"));
        assert!(!format!("{error:?}").contains(root.to_string_lossy().as_ref()));

        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    fn create_directory_link(target: &Path, link: &Path) -> io::Result<()> {
        std::os::unix::fs::symlink(target, link)
    }

    #[cfg(unix)]
    fn create_file_link(target: &Path, link: &Path) -> io::Result<()> {
        std::os::unix::fs::symlink(target, link)
    }

    #[cfg(unix)]
    fn remove_directory_link(link: &Path) {
        fs::remove_file(link).unwrap();
    }

    #[cfg(windows)]
    fn create_directory_link(target: &Path, link: &Path) -> io::Result<()> {
        if std::os::windows::fs::symlink_dir(target, link).is_ok() {
            return Ok(());
        }
        let status = std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(link)
            .arg(target)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()?;
        if status.success() {
            Ok(())
        } else {
            Err(io::Error::other("cannot create test directory link"))
        }
    }

    #[cfg(windows)]
    fn create_file_link(target: &Path, link: &Path) -> io::Result<()> {
        std::os::windows::fs::symlink_file(target, link)
    }

    #[cfg(windows)]
    fn remove_directory_link(link: &Path) {
        fs::remove_dir(link).unwrap();
    }
}
