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

const SETTINGS_SCHEMA_V1: &str = "miho-desktop-settings-v1";
const WORKSPACE_SUMMARY_SCHEMA_V1: &str = "miho-workspace-summary-v1";

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

    pub fn access(&self, workspace_id: &str) -> Result<PathBuf, WorkspaceError> {
        let active = self.lock_active()?;
        let summary = active.summary(self.session_id);
        if summary.workspace_id != workspace_id {
            return Err(WorkspaceError::StaleWorkspace);
        }
        Ok(active.root.clone())
    }

    pub fn active_root(&self) -> Result<PathBuf, WorkspaceError> {
        Ok(self.lock_active()?.root.clone())
    }

    pub fn native_paths(
        &self,
        workspace_id: &str,
    ) -> Result<(PathBuf, NativeTaskPathsV1), WorkspaceError> {
        let root = self.access(workspace_id)?;
        let data_dir = preferred_zzz_data_dir(&root);
        Ok((
            root.clone(),
            NativeTaskPathsV1 {
                data_dir,
                box_path: root.join(".miho/zzz_box_state.json"),
                rules_path: root.join("configs/zzz_decision_rules.yaml"),
                banner_plan_path: root.join("configs/zzz_banner_plan.json"),
                mechanism_notes_dir: root.join("configs/zzz_mechanism_notes"),
                decision_baseline_path: root.join("configs/zzz_decision_baseline.json"),
            },
        ))
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
        miho_core::config::save_json(&self.settings_path, &settings)
            .map_err(|_| WorkspaceError::Persist)?;
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

    pub fn environment_locked(&self) -> bool {
        self.environment_locked
    }

    fn lock_active(&self) -> Result<MutexGuard<'_, ActiveWorkspace>, WorkspaceError> {
        self.active.lock().map_err(|_| WorkspaceError::State)
    }
}

fn load_settings(path: &Path) -> (Option<DesktopSettingsV1>, Option<String>) {
    if !path.exists() {
        return (None, None);
    }
    match miho_core::config::load::<DesktopSettingsV1>(path) {
        Ok(settings) if settings.schema_version == SETTINGS_SCHEMA_V1 => (Some(settings), None),
        Ok(_) => (
            None,
            Some(
                "Stored workspace settings use an unsupported schema; defaults were restored."
                    .to_owned(),
            ),
        ),
        Err(_) => (
            None,
            Some("Stored workspace settings could not be read; defaults were restored.".to_owned()),
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
    if let Some(root) =
        cwd.filter(|path| path.join(".miho").is_dir() && validate_selected_root(path).is_ok())
    {
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

fn validate_selected_root(root: &Path) -> Result<(), WorkspaceError> {
    let metadata = fs::symlink_metadata(root).map_err(|_| WorkspaceError::InvalidSelection)?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse(&metadata) {
        return Err(WorkspaceError::InvalidSelection);
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
}
