use std::path::PathBuf;

use miho_core::box_state::BoxState;
use tauri::{Manager, State};

mod tasks;
mod workspace;

use tasks::DesktopState;
use workspace::{box_state_path, WorkspaceRegistry};

#[tauri::command]
fn load_box_state(game: String, state: State<'_, DesktopState>) -> Result<BoxState, String> {
    let root = state
        .workspaces
        .active_root()
        .map_err(|_| "Desktop workspace state is unavailable.".to_owned())?;
    let path = box_state_path(&root, &game)?;
    if !path.exists() {
        return Ok(BoxState::default());
    }
    miho_core::box_state::load(&path)
        .map_err(|_| "The saved Box State could not be loaded.".to_owned())
}

#[tauri::command]
fn save_box_state(
    game: String,
    state: BoxState,
    desktop: State<'_, DesktopState>,
) -> Result<BoxState, String> {
    let box_state = state.normalize();
    let root = desktop
        .workspaces
        .active_root()
        .map_err(|_| "Desktop workspace state is unavailable.".to_owned())?;
    let path = box_state_path(&root, &game)?;
    miho_core::box_state::save(&path, box_state.clone())
        .map_err(|_| "The Box State could not be saved.".to_owned())?;
    Ok(box_state)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let app_data = app.path().app_data_dir()?;
            let app_config = app.path().app_config_dir()?;
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
}
