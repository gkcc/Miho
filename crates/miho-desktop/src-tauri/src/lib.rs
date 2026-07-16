use std::{fs, path::PathBuf};

use miho_app::{bootstrap_workspace_v1, WorkspaceBootstrapRequestV1, WorkspaceWriteLease};
use miho_core::box_state::BoxState;
use serde::{Deserialize, Serialize};
use tauri::{Manager, State};
use uuid::Uuid;

mod portable;
mod tasks;
mod visualizer_protocol;
mod workspace;

use portable::{detect_portable_workspace_v1, PortableWorkspaceError};
use tasks::{
    acquire_automation_coordinator, acquire_automation_workspace_binding,
    powershell_automation_probe_v1, AutomationExpectedOwnerV1, DesktopState,
};
use workspace::{
    box_state_path, validate_selected_root, validate_workspace_target, WorkspaceRegistry,
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

fn bootstrap_desktop_workspace(workspaces: &WorkspaceRegistry) {
    let Ok((root, _)) = workspaces.active_access() else {
        workspaces.push_warning(
            "The active workspace could not be initialized; select it again before running tasks.",
        );
        return;
    };
    if let Err(error) = bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(root)) {
        workspaces.push_warning(format!(
            "Workspace defaults were not initialized ({}); existing user files were not changed.",
            error.code()
        ));
    }
}

fn bootstrap_desktop_workspace_strict(
    workspaces: &WorkspaceRegistry,
) -> Result<(), miho_app::WorkspaceBootstrapError> {
    let (root, _) = workspaces
        .active_access()
        .map_err(|_| miho_app::WorkspaceBootstrapError::WorkspaceUnavailable)?;
    bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(root)).map(|_| ())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct WorkspaceOverrideResolution {
    root: Option<PathBuf>,
    portable: bool,
}

impl WorkspaceOverrideResolution {
    fn normal(root: Option<PathBuf>) -> Self {
        Self {
            root,
            portable: false,
        }
    }

    fn portable(root: PathBuf) -> Self {
        Self {
            root: Some(root),
            portable: true,
        }
    }
}

fn resolve_workspace_override<F>(
    environment_override: Option<PathBuf>,
    current_executable: F,
) -> Result<WorkspaceOverrideResolution, PortableWorkspaceError>
where
    F: FnOnce() -> std::io::Result<PathBuf>,
{
    if let Some(root) = environment_override {
        validate_selected_root(&root).map_err(|_| PortableWorkspaceError::UnsafePath)?;
        return Ok(WorkspaceOverrideResolution::normal(Some(root)));
    }
    let executable =
        current_executable().map_err(|_| PortableWorkspaceError::InvalidExecutablePath)?;
    Ok(match detect_portable_workspace_v1(&executable)? {
        Some(root) => WorkspaceOverrideResolution::portable(root),
        None => WorkspaceOverrideResolution::normal(None),
    })
}

const PORTABLE_IDENTITY_SCHEMA_V1: &str = "miho-portable-identity-v1";
const PORTABLE_IDENTITY_FILE_V1: &str = "portable-identity-v1.json";
const MAX_PORTABLE_IDENTITY_BYTES_V1: u64 = 4 * 1024;
const INSTALLED_OWNER_REGISTRY_SUBKEY_V1: &str = "Software\\com.miho.endgame";
const INSTALLED_OWNER_REGISTRY_VALUE_V1: &str = "AutomationOwnerInstanceIdV1";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct PortableIdentityV1 {
    schema_version: String,
    owner_kind: String,
    owner_instance_id: String,
}

struct PortableDesktopStateV1 {
    webview: PathBuf,
    storage_identity: String,
}

fn prepare_portable_identity_v1(root: &std::path::Path) -> Result<String, PortableWorkspaceError> {
    let _lease = WorkspaceWriteLease::acquire(root)
        .map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
    let state = root.join(".miho");
    validate_workspace_target(root, &state).map_err(|_| PortableWorkspaceError::UnsafePath)?;
    match fs::symlink_metadata(&state) {
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
        Ok(_) => return Err(PortableWorkspaceError::UnsafePath),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir(&state).map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
        }
        Err(_) => return Err(PortableWorkspaceError::WorkspaceUnavailable),
    }
    validate_workspace_target(root, &state).map_err(|_| PortableWorkspaceError::UnsafePath)?;
    let identity_path = state.join(PORTABLE_IDENTITY_FILE_V1);
    validate_workspace_target(root, &identity_path)
        .map_err(|_| PortableWorkspaceError::UnsafePath)?;
    let identity = match fs::symlink_metadata(&identity_path) {
        Ok(metadata) => {
            if !metadata.is_file()
                || metadata.file_type().is_symlink()
                || metadata.len() > MAX_PORTABLE_IDENTITY_BYTES_V1
            {
                return Err(if metadata.len() > MAX_PORTABLE_IDENTITY_BYTES_V1 {
                    PortableWorkspaceError::IdentityTooLarge
                } else {
                    PortableWorkspaceError::IdentityInvalid
                });
            }
            let bytes =
                fs::read(&identity_path).map_err(|_| PortableWorkspaceError::IdentityInvalid)?;
            let after = fs::symlink_metadata(&identity_path)
                .map_err(|_| PortableWorkspaceError::IdentityInvalid)?;
            if !after.is_file()
                || after.file_type().is_symlink()
                || after.len() > MAX_PORTABLE_IDENTITY_BYTES_V1
                || bytes.len() as u64 > MAX_PORTABLE_IDENTITY_BYTES_V1
                || after.len() != bytes.len() as u64
            {
                return Err(PortableWorkspaceError::IdentityInvalid);
            }
            serde_json::from_slice::<PortableIdentityV1>(&bytes)
                .map_err(|_| PortableWorkspaceError::IdentityInvalid)?
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let identity = PortableIdentityV1 {
                schema_version: PORTABLE_IDENTITY_SCHEMA_V1.to_owned(),
                owner_kind: "portable".to_owned(),
                owner_instance_id: Uuid::new_v4().to_string(),
            };
            let mut bytes = serde_json::to_vec_pretty(&identity)
                .map_err(|_| PortableWorkspaceError::IdentityInvalid)?;
            bytes.push(b'\n');
            miho_core::atomic::write_batch(&[(identity_path.clone(), bytes)])
                .map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
            identity
        }
        Err(_) => return Err(PortableWorkspaceError::IdentityInvalid),
    };
    if identity.schema_version != PORTABLE_IDENTITY_SCHEMA_V1
        || identity.owner_kind != "portable"
        || Uuid::parse_str(&identity.owner_instance_id)
            .ok()
            .is_none_or(|parsed| parsed.to_string() != identity.owner_instance_id)
    {
        return Err(PortableWorkspaceError::IdentityInvalid);
    }
    validate_workspace_target(root, &identity_path)
        .map_err(|_| PortableWorkspaceError::UnsafePath)?;
    Ok(identity.owner_instance_id)
}

fn prepare_portable_webview_v1(
    root: &std::path::Path,
    owner_instance_id: String,
) -> Result<PortableDesktopStateV1, PortableWorkspaceError> {
    let _lease = WorkspaceWriteLease::acquire(root)
        .map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
    let state = root.join(".miho");
    let webview = state.join("webview2");
    for directory in [&state, &webview] {
        validate_workspace_target(root, directory)
            .map_err(|_| PortableWorkspaceError::UnsafePath)?;
        match fs::symlink_metadata(directory) {
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
            Ok(_) => return Err(PortableWorkspaceError::UnsafePath),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                fs::create_dir(directory)
                    .map_err(|_| PortableWorkspaceError::WorkspaceUnavailable)?;
            }
            Err(_) => return Err(PortableWorkspaceError::WorkspaceUnavailable),
        }
        validate_workspace_target(root, directory)
            .map_err(|_| PortableWorkspaceError::UnsafePath)?;
    }
    Ok(PortableDesktopStateV1 {
        webview,
        storage_identity: owner_instance_id,
    })
}

#[cfg(test)]
fn prepare_portable_desktop_state(
    root: &std::path::Path,
) -> Result<PortableDesktopStateV1, PortableWorkspaceError> {
    let owner_instance_id = prepare_portable_identity_v1(root)?;
    prepare_portable_webview_v1(root, owner_instance_id)
}

#[cfg(windows)]
fn read_installed_owner_instance_id_v1() -> std::io::Result<Option<String>> {
    read_installed_owner_registry_value_at_v1(
        INSTALLED_OWNER_REGISTRY_SUBKEY_V1,
        INSTALLED_OWNER_REGISTRY_VALUE_V1,
    )
}

#[cfg(windows)]
fn read_installed_owner_registry_value_at_v1(
    subkey_name: &str,
    value_name: &str,
) -> std::io::Result<Option<String>> {
    use std::{os::windows::ffi::OsStrExt, ptr};
    use windows_sys::Win32::{
        Foundation::{ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_SUCCESS},
        System::Registry::{RegGetValueW, HKEY_CURRENT_USER, REG_SZ, RRF_RT_REG_SZ},
    };

    fn wide(value: &str) -> Vec<u16> {
        std::ffi::OsStr::new(value)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    let subkey = wide(subkey_name);
    let value = wide(value_name);
    let mut value_type = 0_u32;
    let mut byte_count = 0_u32;
    // SAFETY: the UTF-16 inputs are NUL terminated and the first call requests
    // only the required byte count with a null output buffer.
    let first = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            subkey.as_ptr(),
            value.as_ptr(),
            RRF_RT_REG_SZ,
            &mut value_type,
            ptr::null_mut(),
            &mut byte_count,
        )
    };
    if matches!(first, ERROR_FILE_NOT_FOUND | ERROR_PATH_NOT_FOUND) {
        return Ok(None);
    }
    if first != ERROR_SUCCESS
        || value_type != REG_SZ
        || !(2..=160).contains(&byte_count)
        || !byte_count.is_multiple_of(2)
    {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "installed automation owner identity is invalid",
        ));
    }
    let mut buffer = vec![0_u16; byte_count as usize / 2];
    // SAFETY: `buffer` has exactly the byte capacity reported by the first
    // call and remains live for the duration of this second call.
    let second = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            subkey.as_ptr(),
            value.as_ptr(),
            RRF_RT_REG_SZ,
            &mut value_type,
            buffer.as_mut_ptr().cast(),
            &mut byte_count,
        )
    };
    if second != ERROR_SUCCESS {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "installed automation owner identity is invalid",
        ));
    }
    truncate_installed_owner_registry_buffer_v1(&mut buffer, byte_count)?;
    parse_installed_owner_registry_value_v1(value_type, &buffer)
}

fn truncate_installed_owner_registry_buffer_v1(
    buffer: &mut Vec<u16>,
    returned_byte_count: u32,
) -> std::io::Result<()> {
    let returned_byte_count = returned_byte_count as usize;
    if returned_byte_count < 2
        || !returned_byte_count.is_multiple_of(2)
        || returned_byte_count > buffer.len() * 2
    {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "installed automation owner identity is invalid",
        ));
    }
    buffer.truncate(returned_byte_count / 2);
    Ok(())
}

fn parse_installed_owner_registry_value_v1(
    value_type: u32,
    buffer: &[u16],
) -> std::io::Result<Option<String>> {
    #[cfg(windows)]
    let expected_type = windows_sys::Win32::System::Registry::REG_SZ;
    #[cfg(not(windows))]
    let expected_type = 1_u32;
    if value_type != expected_type
        || buffer.last() != Some(&0)
        || buffer.len() < 2
        || buffer[..buffer.len() - 1].contains(&0)
    {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "installed automation owner identity is invalid",
        ));
    }
    let owner_instance_id = String::from_utf16(&buffer[..buffer.len() - 1]).map_err(|_| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "installed automation owner identity is invalid",
        )
    })?;
    if Uuid::parse_str(&owner_instance_id)
        .ok()
        .is_none_or(|parsed| parsed.to_string() != owner_instance_id)
    {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "installed automation owner identity is invalid",
        ));
    }
    Ok(Some(owner_instance_id))
}

#[cfg(not(windows))]
fn read_installed_owner_instance_id_v1() -> std::io::Result<Option<String>> {
    Ok(None)
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
    state
        .storage_scope(&root)
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
    let _lease = WorkspaceWriteLease::acquire(&root)
        .map_err(|error| format!("The workspace cannot be written: {}.", error.code()))?;
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
                let Ok(storage_scope) = state.storage_scope(&root) else {
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
            let cwd = std::env::current_dir().ok();
            let current_executable = std::env::current_exe()?;
            let automation_root = app
                .path()
                .local_data_dir()?
                .join("com.miho.endgame.automation");
            // The global coordinator precedes portable identity creation and
            // every automation-root observation. Scheduler producers use the
            // same sibling file, so an absent root cannot race into existence.
            let automation_coordinator = acquire_automation_coordinator(&automation_root)
                .map_err(|error| std::io::Error::other(error.startup_message()))?;
            let resolution = resolve_workspace_override(
                std::env::var_os("MIHO_DATA_ROOT").map(PathBuf::from),
                || Ok(current_executable.clone()),
            )?;
            let portable_owner_instance_id = if resolution.portable {
                let root = resolution
                    .root
                    .as_ref()
                    .ok_or(PortableWorkspaceError::WorkspaceUnavailable)?;
                Some(prepare_portable_identity_v1(root)?)
            } else {
                None
            };
            let automation_owner = match portable_owner_instance_id.as_ref() {
                Some(owner_instance_id) => Some(
                    AutomationExpectedOwnerV1::new("portable", owner_instance_id.clone())
                        .map_err(|error| std::io::Error::other(error.startup_message()))?,
                ),
                None => read_installed_owner_instance_id_v1()?
                    .map(|owner_instance_id| {
                        AutomationExpectedOwnerV1::new("installed", owner_instance_id)
                            .map_err(|error| std::io::Error::other(error.startup_message()))
                    })
                    .transpose()?,
            };
            let executable_directory = current_executable
                .parent()
                .ok_or_else(|| std::io::Error::other("desktop executable location is invalid"))?;
            let automation_probe_script = executable_directory
                .join(if resolution.portable {
                    "automation"
                } else {
                    "installer"
                })
                .join("task_scheduler_v1.ps1");
            let automation_probe = powershell_automation_probe_v1(automation_probe_script);
            let (app_data, app_config) = if resolution.portable {
                let root = resolution
                    .root
                    .as_ref()
                    .ok_or(PortableWorkspaceError::WorkspaceUnavailable)?;
                (root.clone(), root.join(".miho"))
            } else {
                let app_data = app.path().app_data_dir()?;
                let app_config = app.path().app_config_dir()?;
                std::fs::create_dir_all(&app_data)?;
                std::fs::create_dir_all(&app_config)?;
                (app_data, app_config)
            };
            let workspaces =
                WorkspaceRegistry::initialize(app_data, app_config, cwd, resolution.root.clone());
            let (startup_root, _) = workspaces.active_access()?;
            let mut _automation_guard = acquire_automation_workspace_binding(
                Some(&automation_root),
                &startup_root,
                automation_owner.as_ref(),
                Some(automation_probe.as_ref()),
            )
            .map_err(|error| std::io::Error::other(error.startup_message()))?;
            let portable_state = if resolution.portable {
                bootstrap_desktop_workspace_strict(&workspaces)?;
                let root = resolution
                    .root
                    .as_ref()
                    .ok_or(PortableWorkspaceError::WorkspaceUnavailable)?;
                Some(prepare_portable_webview_v1(
                    root,
                    portable_owner_instance_id
                        .clone()
                        .ok_or(PortableWorkspaceError::IdentityInvalid)?,
                )?)
            } else {
                bootstrap_desktop_workspace(&workspaces);
                None
            };
            if _automation_guard.is_none() {
                _automation_guard = acquire_automation_workspace_binding(
                    Some(&automation_root),
                    &startup_root,
                    automation_owner.as_ref(),
                    Some(automation_probe.as_ref()),
                )
                .map_err(|error| std::io::Error::other(error.startup_message()))?;
            }
            let desktop_state = match portable_state.as_ref() {
                Some(portable) => DesktopState::with_portable_storage_identity(
                    workspaces,
                    miho_app::TaskManager::new(),
                    portable.storage_identity.clone(),
                ),
                None => DesktopState::new(workspaces, miho_app::TaskManager::new()),
            };
            let mut desktop_state = desktop_state
                .with_automation_root(automation_root)
                .with_automation_probe(automation_probe)
                .with_automation_coordinator(automation_coordinator);
            if let Some(owner) = automation_owner {
                desktop_state = desktop_state.with_automation_owner(owner);
            }
            app.manage(desktop_state);

            let window_config =
                app.config().app.windows.first().cloned().ok_or_else(|| {
                    std::io::Error::other("desktop window configuration is missing")
                })?;
            let window_builder =
                tauri::WebviewWindowBuilder::from_config(app.handle(), &window_config)?;
            #[cfg(windows)]
            let window_builder = if let Some(portable) = portable_state {
                window_builder.data_directory(portable.webview)
            } else {
                window_builder
            };
            #[cfg(not(windows))]
            let window_builder = {
                if portable_state.is_some() {
                    return Err(std::io::Error::other(
                        "portable WebView storage is supported only on Windows",
                    )
                    .into());
                }
                window_builder
            };
            window_builder.build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_box_state,
            save_box_state,
            get_visualizer_url,
            tasks::get_capabilities,
            tasks::select_workspace,
            tasks::start_task,
            tasks::start_export_task,
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
    fn installed_owner_registry_value_requires_exact_reg_sz_canonical_uuid() {
        let canonical = "abcdef12-3456-4abc-8def-abcdef123456";
        let mut encoded = canonical.encode_utf16().collect::<Vec<_>>();
        encoded.push(0);
        assert_eq!(
            parse_installed_owner_registry_value_v1(1, &encoded).unwrap(),
            Some(canonical.to_owned())
        );

        let mut upper = canonical.to_uppercase().encode_utf16().collect::<Vec<_>>();
        upper.push(0);
        assert!(parse_installed_owner_registry_value_v1(1, &upper).is_err());
        assert!(parse_installed_owner_registry_value_v1(2, &encoded).is_err());
        assert!(parse_installed_owner_registry_value_v1(1, &encoded[..encoded.len() - 1]).is_err());
        let mut embedded_nul = encoded.clone();
        embedded_nul[4] = 0;
        assert!(parse_installed_owner_registry_value_v1(1, &embedded_nul).is_err());
    }

    #[test]
    fn installed_owner_registry_read_accepts_a_safe_second_call_size_shrink() {
        let canonical = "abcdef12-3456-4abc-8def-abcdef123456";
        let mut exact = canonical.encode_utf16().collect::<Vec<_>>();
        exact.push(0);
        let mut sizing_probe_capacity = exact.clone();
        sizing_probe_capacity.push(0);

        assert!(parse_installed_owner_registry_value_v1(1, &sizing_probe_capacity).is_err());
        truncate_installed_owner_registry_buffer_v1(
            &mut sizing_probe_capacity,
            (exact.len() * 2) as u32,
        )
        .unwrap();

        assert_eq!(sizing_probe_capacity, exact);
        assert_eq!(
            parse_installed_owner_registry_value_v1(1, &sizing_probe_capacity).unwrap(),
            Some(canonical.to_owned())
        );

        let mut invalid = exact.clone();
        assert!(truncate_installed_owner_registry_buffer_v1(&mut invalid, 0).is_err());
        assert!(truncate_installed_owner_registry_buffer_v1(&mut invalid, 3).is_err());
        assert!(truncate_installed_owner_registry_buffer_v1(
            &mut invalid,
            (exact.len() * 2 + 2) as u32,
        )
        .is_err());
    }

    #[cfg(windows)]
    #[test]
    fn installed_owner_registry_reader_accepts_a_real_reg_sz_value() {
        use std::{os::windows::ffi::OsStrExt, ptr};
        use windows_sys::Win32::{
            Foundation::ERROR_SUCCESS,
            System::Registry::{
                RegCloseKey, RegCreateKeyExW, RegDeleteTreeW, RegSetValueExW, HKEY,
                HKEY_CURRENT_USER, KEY_SET_VALUE, REG_OPTION_NON_VOLATILE, REG_SZ,
            },
        };

        fn wide(value: &str) -> Vec<u16> {
            std::ffi::OsStr::new(value)
                .encode_wide()
                .chain(std::iter::once(0))
                .collect()
        }

        struct RegistryTreeGuard(Option<Vec<u16>>);
        impl RegistryTreeGuard {
            fn remove(mut self) -> u32 {
                let result = match self.0.as_ref() {
                    Some(subkey) => {
                        // SAFETY: the guard owns a live, NUL-terminated
                        // absolute HKCU subkey name for the entire call.
                        unsafe { RegDeleteTreeW(HKEY_CURRENT_USER, subkey.as_ptr()) }
                    }
                    None => ERROR_SUCCESS,
                };
                if result == ERROR_SUCCESS {
                    self.0 = None;
                }
                result
            }
        }
        impl Drop for RegistryTreeGuard {
            fn drop(&mut self) {
                if let Some(subkey) = self.0.as_ref() {
                    // SAFETY: the guard owns a live, NUL-terminated absolute
                    // HKCU subkey name for the entire call. Drop is a fallback
                    // for assertion paths; the normal path checks the result.
                    unsafe {
                        RegDeleteTreeW(HKEY_CURRENT_USER, subkey.as_ptr());
                    }
                }
            }
        }

        struct RegistryKeyGuard(windows_sys::Win32::System::Registry::HKEY);
        impl Drop for RegistryKeyGuard {
            fn drop(&mut self) {
                // SAFETY: the handle was returned by RegCreateKeyExW and is
                // closed exactly once by this guard.
                unsafe {
                    RegCloseKey(self.0);
                }
            }
        }

        let subkey_name = format!(
            r"Software\com.miho.endgame-registry-reader-test-{}",
            Uuid::new_v4().simple()
        );
        let subkey = wide(&subkey_name);
        let tree_guard = RegistryTreeGuard(Some(subkey.clone()));
        let mut key: HKEY = ptr::null_mut();
        // SAFETY: every pointer references live, NUL-terminated input or a
        // writable output slot for the duration of the call.
        let created = unsafe {
            RegCreateKeyExW(
                HKEY_CURRENT_USER,
                subkey.as_ptr(),
                0,
                ptr::null(),
                REG_OPTION_NON_VOLATILE,
                KEY_SET_VALUE,
                ptr::null(),
                &mut key,
                ptr::null_mut(),
            )
        };
        assert_eq!(created, ERROR_SUCCESS);
        let key_guard = RegistryKeyGuard(key);

        let value_name = "AutomationOwnerInstanceIdV1";
        let value = wide(value_name);
        let owner_instance_id = Uuid::new_v4().to_string();
        let encoded = wide(&owner_instance_id);
        // SAFETY: the key is open for KEY_SET_VALUE and both UTF-16 buffers
        // remain live for the complete write.
        let written = unsafe {
            RegSetValueExW(
                key_guard.0,
                value.as_ptr(),
                0,
                REG_SZ,
                encoded.as_ptr().cast(),
                (encoded.len() * 2) as u32,
            )
        };
        assert_eq!(written, ERROR_SUCCESS);
        drop(key_guard);

        assert_eq!(
            read_installed_owner_registry_value_at_v1(&subkey_name, value_name).unwrap(),
            Some(owner_instance_id)
        );
        assert_eq!(tree_guard.remove(), ERROR_SUCCESS);
    }

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
        assert_eq!(config["app"]["windows"][0]["create"], false);
        let cargo_manifest = include_str!("../Cargo.toml");
        assert!(cargo_manifest.contains("[features]"));
        assert!(cargo_manifest.contains("custom-protocol = [\"tauri/custom-protocol\"]"));
        let frontend = include_str!("../../src/main.ts");
        assert!(frontend.contains("document.documentElement.dataset.mihoAppReady = \"v1\""));
        assert!(frontend.contains("history.replaceState(null, \"\", \"#miho-app-ready-v1\")"));
        assert!(frontend.contains("main.append(visualizerSection, utilities)"));
        assert!(frontend.contains("pageUrl.hash = \"box\""));
        assert!(frontend.contains(
            "visualizerFrame.setAttribute(\"sandbox\", \"allow-scripts allow-same-origin allow-downloads\")"
        ));
        assert!(!frontend.contains("save_box_state"));
        assert!(!frontend.contains("ownedInput"));
        let binary_entry = include_str!("main.rs");
        assert!(binary_entry
            .contains("#[cfg(all(not(debug_assertions), not(feature = \"custom-protocol\")))]"));
        assert!(binary_entry.contains(
            "compile_error!(\"release miho-desktop.exe requires the custom-protocol feature\")"
        ));
        let release_config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.release.conf.json")).unwrap();
        assert_eq!(release_config["bundle"]["active"], false);
        assert_eq!(release_config["bundle"]["targets"], serde_json::json!([]));
        assert!(release_config["bundle"]["externalBin"].is_null());
        assert!(release_config["bundle"]["resources"].is_null());
        let installer = include_str!("../installer.nsi");
        assert!(installer.contains("${OrIf} $R0 <> 0"));
        assert!(!installer.contains("DeleteAppDataCheckbox"));
        assert!(!installer.contains("$(deleteAppData)"));
        assert!(!include_str!("../nsis/installer-hooks.nsh").contains("DeleteAppDataCheckbox"));
        let uninstall = installer.split("Section Uninstall").nth(1).unwrap();
        assert!(
            uninstall.find("CheckIfAppIsRunning").unwrap()
                < uninstall.find("NSIS_HOOK_PREUNINSTALL").unwrap()
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
    fn environment_override_wins_without_inspecting_a_broken_portable_marker() {
        let base = temp_root("portable-environment-priority");
        let environment = base.join("environment");
        let executable_directory = base.join("app");
        fs::create_dir_all(&environment).unwrap();
        fs::create_dir_all(&executable_directory).unwrap();
        fs::write(
            executable_directory.join(portable::PORTABLE_MARKER_FILE_V1),
            b"broken portable marker",
        )
        .unwrap();

        let resolved = resolve_workspace_override(
            Some(environment.clone()),
            || -> std::io::Result<PathBuf> {
                panic!("current_exe must not be inspected when MIHO_DATA_ROOT is set")
            },
        )
        .unwrap();

        assert_eq!(resolved.root, Some(environment));
        assert!(!resolved.portable);
        assert!(!executable_directory.join("data").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn portable_workspace_overrides_persisted_and_cwd_and_is_locked() {
        let base = temp_root("portable-priority");
        let executable_directory = base.join("portable-app");
        let app_data = base.join("app-data");
        let app_config = base.join("app-config");
        let persisted = base.join("persisted");
        let cwd = base.join("cwd");
        for directory in [
            &executable_directory,
            &app_data,
            &app_config,
            &persisted,
            &cwd,
        ] {
            fs::create_dir_all(directory).unwrap();
        }
        fs::create_dir(cwd.join(".miho")).unwrap();
        fs::write(
            executable_directory.join(portable::PORTABLE_MARKER_FILE_V1),
            br#"{"schema_version":"miho-portable-v1","workspace":"data"}"#,
        )
        .unwrap();
        miho_core::config::save_json(
            &app_config.join("desktop-settings-v1.json"),
            &serde_json::json!({
                "schema_version": "miho-desktop-settings-v1",
                "selected_workspace": persisted,
                "revision": 7,
            }),
        )
        .unwrap();
        let executable = executable_directory.join("miho-desktop.exe");
        let resolved = resolve_workspace_override(None, || Ok(executable)).unwrap();
        assert!(resolved.portable);
        let portable_root = resolved.root.unwrap();

        let registry = WorkspaceRegistry::initialize(
            app_data,
            app_config,
            Some(cwd),
            Some(portable_root.clone()),
        );

        assert_eq!(registry.active_root().unwrap(), portable_root);
        assert_eq!(
            registry.summary().unwrap().source,
            workspace::WorkspaceSourceV1::Environment
        );
        assert!(registry.environment_locked());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn missing_portable_marker_preserves_normal_workspace_selection() {
        let base = temp_root("portable-missing-integration");
        let executable = base.join("miho-desktop.exe");

        assert_eq!(
            resolve_workspace_override(None, || Ok(executable)),
            Ok(WorkspaceOverrideResolution::normal(None))
        );
        assert!(!base.join("data").exists());

        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn portable_desktop_state_stays_inside_the_portable_workspace() {
        let base = temp_root("portable-desktop-state");
        let workspace = base.join("data");
        fs::create_dir(&workspace).unwrap();
        bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(workspace.clone())).unwrap();

        let portable = prepare_portable_desktop_state(&workspace).unwrap();

        assert_eq!(portable.webview, workspace.join(".miho/webview2"));
        assert!(portable.webview.is_dir());
        assert!(workspace.join(".miho/portable-identity-v1.json").is_file());
        assert!(workspace::workspace_storage_scope_from_identity(
            &workspace,
            &portable.storage_identity
        )
        .unwrap()
        .starts_with("storage-"));
        assert!(!base.join("app-data").exists());
        assert!(!base.join("app-config").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn portable_storage_identity_survives_whole_directory_relocation() {
        let base = temp_root("portable-relocation");
        let original = base.join("original");
        let moved = base.join("moved");
        let original_workspace = original.join("data");
        fs::create_dir_all(&original_workspace).unwrap();
        bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(
            original_workspace.clone(),
        ))
        .unwrap();
        let before = prepare_portable_desktop_state(&original_workspace).unwrap();
        let before_scope = workspace::workspace_storage_scope_from_identity(
            &original_workspace,
            &before.storage_identity,
        )
        .unwrap();
        drop(before);

        fs::rename(&original, &moved).unwrap();
        let moved_workspace = moved.join("data");
        let after = prepare_portable_desktop_state(&moved_workspace).unwrap();
        let after_scope = workspace::workspace_storage_scope_from_identity(
            &moved_workspace,
            &after.storage_identity,
        )
        .unwrap();

        assert_eq!(before_scope, after_scope);
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn relative_environment_override_fails_before_portable_fallback() {
        assert_eq!(
            resolve_workspace_override(Some(PathBuf::from("relative-data")), || {
                panic!("portable fallback must not run for an invalid environment override")
            }),
            Err(PortableWorkspaceError::UnsafePath)
        );
    }

    #[test]
    fn malformed_portable_marker_is_pathless_and_never_falls_back() {
        let base = temp_root("portable-malformed-CANARY_SECRET");
        let executable = base.join("miho-desktop.exe");
        fs::write(
            base.join(portable::PORTABLE_MARKER_FILE_V1),
            br#"{"schema_version":"miho-portable-v1","workspace":"../escape"}"#,
        )
        .unwrap();

        let error = resolve_workspace_override(None, || Ok(executable)).unwrap_err();

        assert_eq!(error, PortableWorkspaceError::InvalidMarker);
        assert_eq!(error.to_string(), "portable.marker_invalid");
        assert!(!error.to_string().contains("CANARY_SECRET"));
        assert!(!base.join("data").exists());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn desktop_bootstrap_seeds_the_active_workspace_without_fake_box_data() {
        let base = temp_root("bootstrap");
        let app_data = base.join("app-data");
        fs::create_dir_all(&app_data).unwrap();
        let registry =
            WorkspaceRegistry::initialize(app_data.clone(), base.join("config"), None, None);

        bootstrap_desktop_workspace(&registry);

        assert!(app_data.join("configs/update_v1.json").is_file());
        let box_state = load_checked_box_state(&app_data.join(".miho/zzz_box_state.json")).unwrap();
        assert_eq!(box_state, BoxState::default());
        assert!(registry.warnings().is_empty());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn desktop_bootstrap_busy_warning_is_pathless_and_startup_can_continue() {
        let base = temp_root("bootstrap-busy-CANARY_SECRET");
        let app_data = base.join("app-data");
        fs::create_dir_all(&app_data).unwrap();
        let registry =
            WorkspaceRegistry::initialize(app_data.clone(), base.join("config"), None, None);
        let lease = WorkspaceWriteLease::acquire(&app_data).unwrap();

        bootstrap_desktop_workspace(&registry);

        let warnings = registry.warnings();
        assert_eq!(warnings.len(), 1);
        assert!(warnings[0].contains("workspace.write_busy"));
        assert!(!warnings[0].contains("CANARY_SECRET"));
        assert!(!app_data.join("configs/update_v1.json").exists());
        drop(lease);
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
