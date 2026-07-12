use std::{fs, path::PathBuf};

use miho_core::box_state::BoxState;
use tauri::{Manager, State};

mod tasks;
mod visualizer_protocol;
mod workspace;

use tasks::DesktopState;
use workspace::{
    box_state_path, validate_workspace_target, workspace_storage_scope, WorkspaceRegistry,
};

pub(crate) const MAX_BOX_BYTES: u64 = 1024 * 1024;
pub(crate) const MAX_BOX_VALUE_DEPTH: usize = 32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BoxStateLimitError {
    TooDeep,
    TooLarge,
    Serialize,
}

fn checked_box_state_path(root: &std::path::Path, game: &str) -> Result<PathBuf, String> {
    let path = box_state_path(root, game).map_err(|_| "Unknown Box game.".to_owned())?;
    validate_workspace_target(root, &path)
        .map_err(|_| "The Box State storage location is not trusted.".to_owned())?;
    Ok(path)
}

pub(crate) fn ensure_box_state_limits(state: &BoxState) -> Result<(), BoxStateLimitError> {
    let mut stack = state
        .builds
        .values()
        .map(|value| (value, 1usize))
        .collect::<Vec<_>>();
    while let Some((value, depth)) = stack.pop() {
        if depth > MAX_BOX_VALUE_DEPTH {
            return Err(BoxStateLimitError::TooDeep);
        }
        match value {
            serde_json::Value::Array(values) => {
                stack.extend(values.iter().map(|value| (value, depth + 1)));
            }
            serde_json::Value::Object(values) => {
                stack.extend(values.values().map(|value| (value, depth + 1)));
            }
            _ => {}
        }
    }
    let serialized = serde_json::to_vec_pretty(state).map_err(|_| BoxStateLimitError::Serialize)?;
    if serialized.len().saturating_add(1) as u64 > MAX_BOX_BYTES {
        return Err(BoxStateLimitError::TooLarge);
    }
    Ok(())
}

fn box_state_limit_message(error: BoxStateLimitError) -> String {
    match error {
        BoxStateLimitError::TooDeep => "The Box State structure is too deeply nested.",
        BoxStateLimitError::TooLarge => "The Box State exceeds the 1 MiB storage limit.",
        BoxStateLimitError::Serialize => "The Box State could not be validated.",
    }
    .to_owned()
}

fn load_checked_box_state(path: &std::path::Path) -> Result<BoxState, String> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(BoxState::default()),
        Ok(metadata) if metadata.is_file() && metadata.len() <= MAX_BOX_BYTES => {
            let box_state = miho_core::box_state::load(path)
                .map_err(|_| "The saved Box State could not be loaded.".to_owned())?;
            ensure_box_state_limits(&box_state).map_err(box_state_limit_message)?;
            Ok(box_state)
        }
        _ => Err("The saved Box State is not a supported local file.".to_owned()),
    }
}

#[tauri::command]
fn get_visualizer_url(game: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let _gate = state
        .lock_gate()
        .map_err(|_| "Desktop state is unavailable.".to_owned())?;
    let (root, workspace) = state
        .workspaces
        .active_access()
        .map_err(|_| "Desktop workspace state is unavailable.".to_owned())?;
    let url = visualizer_protocol::visualizer_url(&game, &workspace.workspace_id)
        .ok_or_else(|| "Unknown visualizer game.".to_owned())?;
    workspace_storage_scope(&root)
        .map_err(|_| "The active workspace storage scope is unavailable.".to_owned())?;
    if !visualizer_protocol::visualizer_is_ready(&root, &game) {
        return Err(
            "The requested visualizer is not available in the active workspace.".to_owned(),
        );
    }
    Ok(url)
}

#[tauri::command]
fn load_box_state(
    game: String,
    workspace_id: String,
    state: State<'_, DesktopState>,
) -> Result<BoxState, String> {
    let _gate = state
        .lock_gate()
        .map_err(|_| "Desktop state is unavailable.".to_owned())?;
    let root = state
        .workspaces
        .access(&workspace_id)
        .map_err(|_| "The workspace selection changed; refresh and retry.".to_owned())?;
    let path = checked_box_state_path(&root, &game)?;
    load_checked_box_state(&path)
}

#[tauri::command]
fn save_box_state(
    game: String,
    workspace_id: String,
    state: BoxState,
    desktop: State<'_, DesktopState>,
) -> Result<BoxState, String> {
    let box_state = state.normalize();
    ensure_box_state_limits(&box_state).map_err(box_state_limit_message)?;
    let _gate = desktop
        .lock_gate()
        .map_err(|_| "Desktop state is unavailable.".to_owned())?;
    let root = desktop
        .workspaces
        .access(&workspace_id)
        .map_err(|_| "The workspace selection changed; refresh and retry.".to_owned())?;
    let path = checked_box_state_path(&root, &game)?;
    miho_core::box_state::save(&path, box_state.clone())
        .map_err(|_| "The Box State could not be saved.".to_owned())?;
    Ok(box_state)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .register_uri_scheme_protocol(
            visualizer_protocol::VISUALIZER_SCHEME,
            |context, request| {
                let state = context.app_handle().state::<DesktopState>();
                let Ok(_gate) = state.lock_gate() else {
                    return visualizer_protocol::unavailable_response();
                };
                let Ok((root, workspace)) = state.workspaces.active_access() else {
                    return visualizer_protocol::unavailable_response();
                };
                let Ok(storage_scope) = workspace_storage_scope(&root) else {
                    return visualizer_protocol::unavailable_response();
                };
                visualizer_protocol::handle_workspace_request(
                    &root,
                    &workspace.workspace_id,
                    &storage_scope,
                    context.webview_label(),
                    request,
                )
            },
        )
        .setup(|app| {
            let app_data = app.path().app_data_dir()?;
            let app_config = app.path().app_config_dir()?;
            std::fs::create_dir_all(&app_data)?;
            std::fs::create_dir_all(&app_config)?;
            let cwd = std::env::current_dir().ok();
            let override_root = std::env::var_os("MIHO_DATA_ROOT").map(PathBuf::from);
            let workspaces =
                WorkspaceRegistry::initialize(app_data, app_config, cwd, override_root);
            app.manage(DesktopState::new(workspaces, miho_app::TaskManager::new()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_box_state,
            save_box_state,
            get_visualizer_url,
            tasks::get_capabilities,
            tasks::select_workspace,
            tasks::start_task,
            tasks::get_task,
            tasks::list_tasks,
            tasks::cancel_task,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Miho desktop");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        path::Path,
        sync::atomic::{AtomicU64, Ordering},
    };

    static NEXT_ID: AtomicU64 = AtomicU64::new(0);

    #[test]
    fn generated_context_uses_isolation_with_identity_hook() {
        let context: tauri::Context<tauri::Wry> = tauri::generate_context!();
        assert!(matches!(
            context.pattern(),
            tauri::Pattern::Isolation { .. }
        ));
        let index = include_str!("../isolation/index.html");
        let hook = include_str!("../isolation/hook.js");
        assert!(index.contains("<script src=\"./hook.js\"></script>"));
        assert!(hook.contains("window.__TAURI_ISOLATION_HOOK__ = (payload) => payload"));
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_eq!(config["app"]["security"]["pattern"]["use"], "isolation");
        assert_eq!(
            config["app"]["security"]["pattern"]["options"]["dir"],
            "isolation"
        );
    }

    fn temp_root(label: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "miho-desktop-box-{label}-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn state_paths_are_legacy_compatible() {
        assert_eq!(
            box_state_path(Path::new("root"), "zzz").unwrap(),
            Path::new("root/.miho/zzz_box_state.json")
        );
        assert!(box_state_path(Path::new("root"), "other").is_err());
    }

    #[test]
    fn box_path_follows_the_active_workspace() {
        let base = temp_root("active");
        let selected = base.join("selected");
        fs::create_dir_all(&selected).unwrap();
        let registry =
            WorkspaceRegistry::initialize(base.join("app-data"), base.join("config"), None, None);
        assert_eq!(
            box_state_path(&registry.active_root().unwrap(), "zzz").unwrap(),
            base.join("app-data/.miho/zzz_box_state.json")
        );
        registry.select(selected.clone()).unwrap();
        assert_eq!(
            box_state_path(&registry.active_root().unwrap(), "zzz").unwrap(),
            selected.join(".miho/zzz_box_state.json")
        );
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn box_limits_reject_oversized_and_deep_build_payloads() {
        let mut oversized = BoxState::default();
        oversized.owned.push("x".repeat(MAX_BOX_BYTES as usize));
        assert_eq!(
            ensure_box_state_limits(&oversized),
            Err(BoxStateLimitError::TooLarge)
        );

        let mut value = serde_json::Value::Null;
        for _ in 0..=MAX_BOX_VALUE_DEPTH {
            value = serde_json::Value::Array(vec![value]);
        }
        let mut deep = BoxState::default();
        deep.builds.insert("agent".to_owned(), value);
        assert_eq!(
            ensure_box_state_limits(&deep),
            Err(BoxStateLimitError::TooDeep)
        );

        let mut boundary = BoxState::default();
        let mut value = serde_json::Value::Null;
        for _ in 1..MAX_BOX_VALUE_DEPTH {
            value = serde_json::Value::Array(vec![value]);
        }
        boundary.builds.insert("agent".to_owned(), value);
        ensure_box_state_limits(&boundary).unwrap();
    }

    #[test]
    fn box_loader_rejects_oversized_files_before_json_parsing() {
        let root = temp_root("oversized-load");
        let path = root.join("box.json");
        fs::write(&path, vec![b' '; MAX_BOX_BYTES as usize + 1]).unwrap();
        assert!(load_checked_box_state(&path)
            .unwrap_err()
            .contains("not a supported local file"));
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn box_commands_reject_reparse_parent_without_leaking_paths() {
        use std::os::windows::fs::symlink_dir;
        let root = temp_root("box-reparse-CANARY_SECRET");
        let external = root.join("external");
        fs::create_dir_all(&external).unwrap();
        if symlink_dir(&external, root.join(".miho")).is_err() {
            fs::remove_dir_all(root).unwrap();
            return;
        }
        let error = checked_box_state_path(&root, "zzz").unwrap_err();
        assert!(!error.contains("CANARY_SECRET"));
        assert!(!external.join("zzz_box_state.json").exists());
        fs::remove_dir_all(root).unwrap();
    }
}
