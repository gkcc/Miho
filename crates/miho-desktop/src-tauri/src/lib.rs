use std::{
    path::{Path, PathBuf},
    sync::Mutex,
};

use miho_core::box_state::BoxState;
use tauri::State;

struct WorkspaceRoot(Mutex<PathBuf>);

fn state_path(root: &Path, game: &str) -> Result<PathBuf, String> {
    let filename = match game {
        "hsr" => "hsr_box_state.json",
        "zzz" => "zzz_box_state.json",
        _ => return Err(format!("unknown game: {game}")),
    };
    Ok(root.join(".miho").join(filename))
}

#[tauri::command]
fn load_box_state(game: String, root: State<'_, WorkspaceRoot>) -> Result<BoxState, String> {
    let path = state_path(&root.0.lock().map_err(|e| e.to_string())?, &game)?;
    if !path.exists() {
        return Ok(BoxState::default());
    }
    miho_core::box_state::load(&path).map_err(|e| e.to_string())
}

#[tauri::command]
fn save_box_state(
    game: String,
    state: BoxState,
    root: State<'_, WorkspaceRoot>,
) -> Result<BoxState, String> {
    let state = state.normalize();
    let path = state_path(&root.0.lock().map_err(|e| e.to_string())?, &game)?;
    miho_core::box_state::save(&path, state.clone()).map_err(|e| e.to_string())?;
    Ok(state)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let root = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    tauri::Builder::default()
        .manage(WorkspaceRoot(Mutex::new(root)))
        .invoke_handler(tauri::generate_handler![load_box_state, save_box_state])
        .run(tauri::generate_context!())
        .expect("error while running Miho desktop");
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn state_paths_are_legacy_compatible() {
        assert_eq!(
            state_path(Path::new("root"), "zzz").unwrap(),
            Path::new("root/.miho/zzz_box_state.json")
        );
        assert!(state_path(Path::new("root"), "other").is_err());
    }
}
