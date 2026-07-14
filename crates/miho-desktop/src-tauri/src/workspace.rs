use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex, MutexGuard,
    },
    time::{SystemTime, UNIX_EPOCH},
};

use miho_app::NativeTaskPathsV1;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const SETTINGS_SCHEMA_V1: &str = "miho-desktop-settings-v1";
const WORKSPACE_SUMMARY_SCHEMA_V1: &str = "miho-workspace-summary-v1";
const MAX_SETTINGS_BYTES_V1: u64 = 64 * 1024;

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum WorkspaceSourceV1 {
    Environment,
    Persisted,
    WorkingDirectory,
    AppData,
    Selected,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceSummaryV1 {
    pub schema_version: String,
    pub workspace_id: String,
    pub label: String,
    pub source: WorkspaceSourceV1,
    pub revision: u64,
}

#[derive(Debug, Clone)]
struct ActiveWorkspace {
    root: PathBuf,
    source: WorkspaceSourceV1,
    revision: u64,
}

impl ActiveWorkspace {
    fn summary(&self, session_id: u128) -> WorkspaceSummaryV1 {
        WorkspaceSummaryV1 {
            schema_version: WORKSPACE_SUMMARY_SCHEMA_V1.to_owned(),
            workspace_id: workspace_id(session_id, self.revision),
            label: "Miho workspace".to_owned(),
            source: self.source,
            revision: self.revision,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct DesktopSettingsV1 {
    schema_version: String,
    selected_workspace: PathBuf,
    revision: u64,
}

#[derive(Debug)]
pub struct WorkspaceRegistry {
    active: Mutex<ActiveWorkspace>,
    settings_path: PathBuf,
    session_id: u128,
    environment_locked: bool,
    warnings: Mutex<Vec<String>>,
}

#[derive(Debug, thiserror::Error)]
pub enum WorkspaceError {
    #[error("workspace selection is locked by MIHO_DATA_ROOT")]
    EnvironmentLocked,
    #[error("workspace selection changed; refresh capabilities and retry")]
    StaleWorkspace,
    #[error("selected workspace is not a trusted directory")]
    InvalidSelection,
    #[error("workspace contains an untrusted linked path")]
    UntrustedPath,
    #[error("cannot persist workspace selection")]
    Persist,
    #[error("workspace state is unavailable")]
    State,
}

impl WorkspaceRegistry {
    pub fn initialize(
        app_data: PathBuf,
        app_config: PathBuf,
        cwd: Option<PathBuf>,
        override_root: Option<PathBuf>,
    ) -> Self {
        let settings_path = app_config.join("desktop-settings-v1.json");
        let (mut stored, mut warning) = load_settings(&settings_path);
        if stored
            .as_ref()
            .is_some_and(|settings| validate_selected_root(&settings.selected_workspace).is_err())
        {
            stored = None;
            warning = Some(
                "Stored workspace settings reference an unavailable or untrusted folder; defaults were restored."
                    .to_owned(),
            );
        }
        let environment_locked = override_root.is_some();
        let active = select_initial_workspace(app_data, cwd, override_root, stored.as_ref());
        Self {
            active: Mutex::new(active),
            settings_path,
            session_id: next_session_id(),
            environment_locked,
            warnings: Mutex::new(warning.into_iter().collect()),
        }
    }

    pub fn summary(&self) -> Result<WorkspaceSummaryV1, WorkspaceError> {
        Ok(self.lock_active()?.summary(self.session_id))
    }

    pub fn active_access(&self) -> Result<(PathBuf, WorkspaceSummaryV1), WorkspaceError> {
        let active = self.lock_active()?;
        Ok((active.root.clone(), active.summary(self.session_id)))
    }

    pub fn access(&self, workspace_id: &str) -> Result<PathBuf, WorkspaceError> {
        let active = self.lock_active()?;
        let summary = active.summary(self.session_id);
        if summary.workspace_id != workspace_id {
            return Err(WorkspaceError::StaleWorkspace);
        }
        Ok(active.root.clone())
    }

    #[cfg(test)]
    pub fn active_root(&self) -> Result<PathBuf, WorkspaceError> {
        self.active_access().map(|(root, _)| root)
    }

    pub fn native_paths(
        &self,
        workspace_id: &str,
    ) -> Result<(PathBuf, NativeTaskPathsV1), WorkspaceError> {
        let root = self.access(workspace_id)?;
        let data_dir = preferred_zzz_data_dir(&root);
        let paths = NativeTaskPathsV1 {
            data_dir,
            box_path: root.join(".miho/zzz_box_state.json"),
            rules_path: root.join("configs/zzz_decision_rules.yaml"),
            banner_plan_path: root.join("configs/zzz_banner_plan.json"),
            mechanism_notes_dir: root.join("configs/zzz_mechanism_notes"),
            decision_baseline_path: root.join("configs/zzz_decision_baseline.json"),
        };
        validate_native_task_paths(&root, &paths)?;
        Ok((root, paths))
    }

    pub fn select(&self, root: PathBuf) -> Result<WorkspaceSummaryV1, WorkspaceError> {
        if self.environment_locked {
            return Err(WorkspaceError::EnvironmentLocked);
        }
        validate_selected_root(&root)?;
        let mut active = self.lock_active()?;
        let revision = active.revision.saturating_add(1).max(1);
        let settings = DesktopSettingsV1 {
            schema_version: SETTINGS_SCHEMA_V1.to_owned(),
            selected_workspace: root.clone(),
            revision,
        };
        let settings_parent = self.settings_path.parent().ok_or(WorkspaceError::Persist)?;
        ensure_safe_directory_chain(settings_parent).map_err(|_| WorkspaceError::Persist)?;
        match fs::symlink_metadata(&self.settings_path) {
            Ok(_) => validate_existing_file_chain(&self.settings_path)
                .map_err(|_| WorkspaceError::Persist)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(WorkspaceError::Persist),
        }
        miho_core::config::save_json(&self.settings_path, &settings)
            .map_err(|_| WorkspaceError::Persist)?;
        validate_existing_file_chain(&self.settings_path).map_err(|_| WorkspaceError::Persist)?;
        *active = ActiveWorkspace {
            root,
            source: WorkspaceSourceV1::Selected,
            revision,
        };
        Ok(active.summary(self.session_id))
    }

    pub fn warnings(&self) -> Vec<String> {
        self.warnings
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    pub fn push_warning(&self, warning: impl Into<String>) {
        self.warnings
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .push(warning.into());
    }

    pub fn environment_locked(&self) -> bool {
        self.environment_locked
    }

    fn lock_active(&self) -> Result<MutexGuard<'_, ActiveWorkspace>, WorkspaceError> {
        self.active.lock().map_err(|_| WorkspaceError::State)
    }
}

fn load_settings(path: &Path) -> (Option<DesktopSettingsV1>, Option<String>) {
    let metadata = match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return (None, None),
        Ok(metadata) => metadata,
        Err(_) => {
            return (
                None,
                Some(
                    "Stored workspace settings could not be read; defaults were restored."
                        .to_owned(),
                ),
            )
        }
    };
    let loaded = (|| {
        validate_existing_file_chain(path)?;
        if !metadata.is_file() || metadata.len() > MAX_SETTINGS_BYTES_V1 {
            return Err(());
        }
        let bytes = fs::read(path).map_err(|_| ())?;
        let after = fs::symlink_metadata(path).map_err(|_| ())?;
        if !after.is_file()
            || after.file_type().is_symlink()
            || is_reparse(&after)
            || after.len() > MAX_SETTINGS_BYTES_V1
            || bytes.len() as u64 > MAX_SETTINGS_BYTES_V1
            || after.len() != bytes.len() as u64
        {
            return Err(());
        }
        let settings = serde_json::from_slice::<DesktopSettingsV1>(&bytes).map_err(|_| ())?;
        if settings.schema_version != SETTINGS_SCHEMA_V1
            || settings.revision == 0
            || validate_selected_root(&settings.selected_workspace).is_err()
        {
            return Err(());
        }
        Ok(settings)
    })();
    match loaded {
        Ok(settings) => (Some(settings), None),
        Err(()) => (
            None,
            Some(
                "Stored workspace settings are invalid, unsafe, or unsupported; defaults were restored."
                    .to_owned(),
            ),
        ),
    }
}

fn select_initial_workspace(
    app_data: PathBuf,
    cwd: Option<PathBuf>,
    override_root: Option<PathBuf>,
    stored: Option<&DesktopSettingsV1>,
) -> ActiveWorkspace {
    if let Some(root) = override_root {
        return ActiveWorkspace {
            root,
            source: WorkspaceSourceV1::Environment,
            revision: 1,
        };
    }
    if let Some(settings) =
        stored.filter(|settings| validate_selected_root(&settings.selected_workspace).is_ok())
    {
        return ActiveWorkspace {
            root: settings.selected_workspace.clone(),
            source: WorkspaceSourceV1::Persisted,
            revision: settings.revision.max(1),
        };
    }
    if let Some(root) = cwd.filter(|root| {
        validate_selected_root(root).is_ok()
            && fs::symlink_metadata(root.join(".miho")).is_ok_and(|metadata| {
                metadata.is_dir() && !metadata.file_type().is_symlink() && !is_reparse(&metadata)
            })
    }) {
        return ActiveWorkspace {
            root,
            source: WorkspaceSourceV1::WorkingDirectory,
            revision: 1,
        };
    }
    ActiveWorkspace {
        root: app_data,
        source: WorkspaceSourceV1::AppData,
        revision: 1,
    }
}

pub(crate) fn validate_selected_root(root: &Path) -> Result<(), WorkspaceError> {
    if !root.is_absolute()
        || root.components().any(|component| {
            !matches!(
                component,
                std::path::Component::Prefix(_)
                    | std::path::Component::RootDir
                    | std::path::Component::Normal(_)
            )
        })
    {
        return Err(WorkspaceError::InvalidSelection);
    }
    for candidate in root.ancestors().collect::<Vec<_>>().into_iter().rev() {
        if candidate.as_os_str().is_empty() {
            continue;
        }
        let metadata =
            fs::symlink_metadata(candidate).map_err(|_| WorkspaceError::InvalidSelection)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse(&metadata) {
            return Err(WorkspaceError::InvalidSelection);
        }
    }
    Ok(())
}

pub(crate) fn validate_existing_file_chain(path: &Path) -> Result<(), ()> {
    if !path.is_absolute() {
        return Err(());
    }
    let parent = path.parent().ok_or(())?;
    for candidate in parent.ancestors().collect::<Vec<_>>().into_iter().rev() {
        if candidate.as_os_str().is_empty() {
            continue;
        }
        let metadata = fs::symlink_metadata(candidate).map_err(|_| ())?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse(&metadata) {
            return Err(());
        }
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| ())?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || is_reparse(&metadata) {
        return Err(());
    }
    Ok(())
}

pub(crate) fn ensure_safe_directory_chain(path: &Path) -> Result<(), ()> {
    if !path.is_absolute()
        || path.components().any(|component| {
            !matches!(
                component,
                std::path::Component::Prefix(_)
                    | std::path::Component::RootDir
                    | std::path::Component::Normal(_)
            )
        })
    {
        return Err(());
    }
    for candidate in path.ancestors().collect::<Vec<_>>().into_iter().rev() {
        if candidate.as_os_str().is_empty() {
            continue;
        }
        match fs::symlink_metadata(candidate) {
            Ok(metadata)
                if metadata.is_dir()
                    && !metadata.file_type().is_symlink()
                    && !is_reparse(&metadata) => {}
            Ok(_) => return Err(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                fs::create_dir(candidate).map_err(|_| ())?;
                let metadata = fs::symlink_metadata(candidate).map_err(|_| ())?;
                if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse(&metadata)
                {
                    return Err(());
                }
            }
            Err(_) => return Err(()),
        }
    }
    Ok(())
}

pub(crate) fn workspace_storage_scope(root: &Path) -> Result<String, WorkspaceError> {
    validate_selected_root(root)?;
    let canonical = fs::canonicalize(root).map_err(|_| WorkspaceError::InvalidSelection)?;
    let mut hasher = Sha256::new();
    hasher.update(b"miho-workspace-storage-v1\0");
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        for unit in canonical.as_os_str().encode_wide() {
            hasher.update(unit.to_le_bytes());
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt;
        hasher.update(canonical.as_os_str().as_bytes());
    }
    #[cfg(not(any(windows, unix)))]
    hasher.update(canonical.to_string_lossy().as_bytes());
    Ok(format!("storage-{:x}", hasher.finalize()))
}

pub(crate) fn workspace_storage_scope_from_identity(
    root: &Path,
    identity: &str,
) -> Result<String, WorkspaceError> {
    validate_selected_root(root)?;
    if identity.len() != 36
        || !identity
            .bytes()
            .enumerate()
            .all(|(index, byte)| match index {
                8 | 13 | 18 | 23 => byte == b'-',
                _ => byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte),
            })
    {
        return Err(WorkspaceError::InvalidSelection);
    }
    let mut hasher = Sha256::new();
    hasher.update(b"miho-portable-storage-v1\0");
    hasher.update(identity.as_bytes());
    Ok(format!("storage-{:x}", hasher.finalize()))
}

/// Validates an authorized workspace descendant without following any existing
/// symlink or Windows reparse-point component. Missing suffixes are allowed so
/// the same boundary can protect both report inputs and future Box targets.
pub(crate) fn validate_workspace_target(root: &Path, target: &Path) -> Result<(), WorkspaceError> {
    validate_selected_root(root).map_err(|_| WorkspaceError::UntrustedPath)?;
    let relative = target
        .strip_prefix(root)
        .map_err(|_| WorkspaceError::UntrustedPath)?;
    let mut current = root.to_path_buf();
    for component in relative.components() {
        let std::path::Component::Normal(component) = component else {
            return Err(WorkspaceError::UntrustedPath);
        };
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() || is_reparse(&metadata) => {
                return Err(WorkspaceError::UntrustedPath);
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
            Err(_) => return Err(WorkspaceError::UntrustedPath),
        }
    }
    Ok(())
}

pub(crate) fn trusted_workspace_file(root: &Path, path: &Path) -> bool {
    validate_workspace_target(root, path).is_ok()
        && fs::symlink_metadata(path).is_ok_and(|metadata| metadata.is_file())
}

const REPORT_DATA_INPUTS: &[&str] = &[
    "team_rank_dedup_unordered.csv",
    "name_map.csv",
    "prydwen_tier_current.csv",
    "prydwen_tier_history.csv",
    "character_usage_long.csv",
    "team_rank_raw.csv",
    "prydwen_tier_changelog_history.csv",
];

fn validate_native_task_paths(
    root: &Path,
    paths: &NativeTaskPathsV1,
) -> Result<(), WorkspaceError> {
    for path in [
        &paths.data_dir,
        &paths.box_path,
        &paths.rules_path,
        &paths.banner_plan_path,
        &paths.mechanism_notes_dir,
        &paths.decision_baseline_path,
    ] {
        validate_workspace_target(root, path)?;
    }
    for name in REPORT_DATA_INPUTS {
        validate_workspace_target(root, &paths.data_dir.join(name))?;
    }
    validate_mechanism_note_entries(root, &paths.mechanism_notes_dir)
}

fn validate_mechanism_note_entries(root: &Path, notes_dir: &Path) -> Result<(), WorkspaceError> {
    let metadata = match fs::symlink_metadata(notes_dir) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(_) => return Err(WorkspaceError::UntrustedPath),
    };
    if !metadata.is_dir() {
        return Ok(());
    }
    for entry in fs::read_dir(notes_dir).map_err(|_| WorkspaceError::UntrustedPath)? {
        let path = entry.map_err(|_| WorkspaceError::UntrustedPath)?.path();
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .map(str::to_ascii_lowercase);
        if extension
            .as_deref()
            .is_some_and(|value| matches!(value, "yaml" | "yml" | "json"))
        {
            validate_workspace_target(root, &path)?;
        }
    }
    Ok(())
}

fn is_reparse(metadata: &fs::Metadata) -> bool {
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

fn preferred_zzz_data_dir(root: &Path) -> PathBuf {
    let project = root.join("out_zzz");
    if project.is_dir() || !root.join("zzz_endgame_export").is_dir() {
        project
    } else {
        root.join("zzz_endgame_export")
    }
}

static NEXT_SESSION_ID: AtomicU64 = AtomicU64::new(1);

fn next_session_id() -> u128 {
    let epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    (epoch << 16) ^ u128::from(NEXT_SESSION_ID.fetch_add(1, Ordering::Relaxed))
}

fn workspace_id(session_id: u128, revision: u64) -> String {
    format!("workspace-{session_id:032x}-{revision:016x}")
}

pub fn box_state_path(root: &Path, game: &str) -> Result<PathBuf, String> {
    let filename = match game {
        "hsr" => "hsr_box_state.json",
        "zzz" => "zzz_box_state.json",
        _ => return Err(format!("unknown game: {game}")),
    };
    Ok(root.join(".miho").join(filename))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_ID: AtomicU64 = AtomicU64::new(0);

    fn temp_root(label: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "miho-desktop-workspace-{label}-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn initial_priority_is_environment_then_stored_then_cwd_then_app_data() {
        let base = temp_root("priority");
        let app_data = base.join("app-data");
        let cwd = base.join("cwd");
        let stored_root = base.join("stored");
        let environment = base.join("environment");
        for root in [&app_data, &cwd, &stored_root, &environment] {
            fs::create_dir_all(root).unwrap();
        }
        fs::create_dir_all(cwd.join(".miho")).unwrap();
        let stored = DesktopSettingsV1 {
            schema_version: SETTINGS_SCHEMA_V1.to_owned(),
            selected_workspace: stored_root.clone(),
            revision: 4,
        };
        assert_eq!(
            select_initial_workspace(
                app_data.clone(),
                Some(cwd.clone()),
                Some(environment.clone()),
                Some(&stored),
            )
            .root,
            environment
        );
        assert_eq!(
            select_initial_workspace(app_data.clone(), Some(cwd.clone()), None, Some(&stored)).root,
            stored_root
        );
        assert_eq!(
            select_initial_workspace(app_data.clone(), Some(cwd.clone()), None, None).root,
            cwd
        );
        assert_eq!(
            select_initial_workspace(app_data.clone(), None, None, None).root,
            app_data
        );
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn summary_is_opaque_and_selection_persists_atomically() {
        let base = temp_root("opaque");
        let registry =
            WorkspaceRegistry::initialize(base.join("app-data"), base.join("config"), None, None);
        let selected = base.join("CANARY_SECRET_PATH");
        fs::create_dir_all(&selected).unwrap();
        let summary = registry.select(selected.clone()).unwrap();
        assert!(summary.workspace_id.starts_with("workspace-"));
        assert!(summary.workspace_id.ends_with("-0000000000000002"));
        let json = serde_json::to_string(&summary).unwrap();
        assert!(!json.contains("CANARY_SECRET_PATH"));
        assert_eq!(registry.access(&summary.workspace_id).unwrap(), selected);
        assert!(matches!(
            registry.access("workspace-stale"),
            Err(WorkspaceError::StaleWorkspace)
        ));
        assert!(base.join("config/desktop-settings-v1.json").is_file());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn active_access_returns_one_consistent_root_and_summary_revision() {
        let base = temp_root("active-access");
        let selected = base.join("selected");
        fs::create_dir_all(&selected).unwrap();
        let registry =
            WorkspaceRegistry::initialize(base.join("app-data"), base.join("config"), None, None);
        let (_, before) = registry.active_access().unwrap();
        let selected_summary = registry.select(selected.clone()).unwrap();
        let (root, after) = registry.active_access().unwrap();
        assert_eq!(root, selected);
        assert_eq!(after, selected_summary);
        assert_ne!(before.workspace_id, after.workspace_id);
        assert!(matches!(
            registry.access(&before.workspace_id),
            Err(WorkspaceError::StaleWorkspace)
        ));
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn native_paths_never_enter_the_public_summary() {
        let base = temp_root("paths");
        fs::create_dir_all(base.join("out_zzz")).unwrap();
        let registry = WorkspaceRegistry::initialize(
            base.clone(),
            base.join("config"),
            None,
            Some(base.clone()),
        );
        let summary = registry.summary().unwrap();
        let (_root, paths) = registry.native_paths(&summary.workspace_id).unwrap();
        assert_eq!(paths.data_dir, base.join("out_zzz"));
        assert_eq!(paths.box_path, base.join(".miho/zzz_box_state.json"));
        assert!(!serde_json::to_string(&summary)
            .unwrap()
            .contains(base.to_string_lossy().as_ref()));
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn workspace_ids_do_not_repeat_between_registry_sessions() {
        let base = temp_root("session");
        let first = WorkspaceRegistry::initialize(
            base.join("app-data"),
            base.join("config-a"),
            None,
            Some(base.clone()),
        )
        .summary()
        .unwrap()
        .workspace_id;
        let second = WorkspaceRegistry::initialize(
            base.join("app-data"),
            base.join("config-b"),
            None,
            Some(base.clone()),
        )
        .summary()
        .unwrap()
        .workspace_id;
        assert_ne!(first, second);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn storage_scope_is_stable_for_one_root_and_distinct_between_roots() {
        let base = temp_root("storage-scope");
        let first = base.join("CANARY_SECRET_FIRST");
        let second = base.join("CANARY_SECRET_SECOND");
        fs::create_dir_all(&first).unwrap();
        fs::create_dir_all(&second).unwrap();
        let first_scope = workspace_storage_scope(&first).unwrap();
        assert_eq!(first_scope, workspace_storage_scope(&first).unwrap());
        assert_ne!(first_scope, workspace_storage_scope(&second).unwrap());
        assert!(first_scope.starts_with("storage-"));
        assert!(first_scope
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-'));
        assert!(!first_scope.contains("CANARY_SECRET"));
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn invalid_persisted_workspace_warns_and_falls_back() {
        let base = temp_root("invalid-persisted");
        let app_data = base.join("app-data");
        let app_config = base.join("config");
        let invalid = base.join("not-a-directory");
        fs::create_dir_all(&app_data).unwrap();
        fs::write(&invalid, b"not a workspace").unwrap();
        miho_core::config::save_json(
            &app_config.join("desktop-settings-v1.json"),
            &DesktopSettingsV1 {
                schema_version: SETTINGS_SCHEMA_V1.to_owned(),
                selected_workspace: invalid,
                revision: 9,
            },
        )
        .unwrap();
        let registry = WorkspaceRegistry::initialize(app_data.clone(), app_config, None, None);
        assert_eq!(registry.active_root().unwrap(), app_data);
        assert_eq!(registry.warnings().len(), 1);
        fs::remove_dir_all(base).unwrap();
    }

    #[cfg(windows)]
    fn create_junction(target: &Path, junction: &Path) -> bool {
        std::process::Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(junction)
            .arg(target)
            .output()
            .is_ok_and(|output| output.status.success())
    }

    #[cfg(windows)]
    #[test]
    fn native_paths_reject_nested_workspace_junctions() {
        for scenario in ["box", "data", "configs", "notes"] {
            let base = temp_root(&format!("junction-{scenario}-CANARY_SECRET"));
            let external = base.join("external");
            let root = base.join("workspace");
            fs::create_dir_all(&external).unwrap();
            fs::create_dir_all(&root).unwrap();
            let junction = match scenario {
                "box" => root.join(".miho"),
                "data" => root.join("out_zzz"),
                "configs" => root.join("configs"),
                "notes" => {
                    fs::create_dir_all(root.join("configs")).unwrap();
                    root.join("configs/zzz_mechanism_notes")
                }
                _ => unreachable!(),
            };
            if !create_junction(&external, &junction) {
                fs::remove_dir_all(base).unwrap();
                continue;
            }
            let registry = WorkspaceRegistry::initialize(
                root.clone(),
                base.join("config"),
                None,
                Some(root.clone()),
            );
            let workspace_id = registry.summary().unwrap().workspace_id;
            let error = registry.native_paths(&workspace_id).unwrap_err();
            assert!(matches!(error, WorkspaceError::UntrustedPath));
            assert!(!error.to_string().contains("CANARY_SECRET"));
            fs::remove_dir(&junction).unwrap();
            fs::remove_dir_all(base).unwrap();
        }
    }
}
