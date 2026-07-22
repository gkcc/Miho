use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};

use miho_app::{WorkspaceWriteLease, WorkspaceWriteLeaseError};
use miho_core::box_state::{self, BoxState};
use serde::{Deserialize, Serialize};
use tauri::http::{header, Method, Request, Response, StatusCode};

use crate::{
    ensure_box_state_limits, workspace::box_state_path, BoxStateLimitError, MAX_BOX_BYTES,
};

pub const VISUALIZER_SCHEME: &str = "miho-visualizer";
const MAX_VISUALIZER_DATA_BYTES: u64 = 64 * 1024 * 1024;
const MAX_AVATAR_BYTES: u64 = 8 * 1024 * 1024;
const BOX_EXPORT_RECEIPT_SCHEMA_V1: &str = "miho-box-export-receipt-v1";
const MAX_BOX_EXPORT_COLLISIONS: usize = 10_000;
const VISUALIZER_CSP: &str = "default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self' tauri://localhost http://tauri.localhost https://tauri.localhost http://localhost:5173 http://127.0.0.1:5173";

#[derive(Debug, Clone, PartialEq, Eq)]
enum Route {
    Static {
        game: &'static str,
        relative: PathBuf,
        mime: &'static str,
        cache: &'static str,
    },
    BoxApi {
        game: &'static str,
    },
    BoxExport {
        game: &'static str,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct BoxExportDocumentV1 {
    version: u8,
    updated_at: String,
    owned: Vec<String>,
    build_slug: String,
    builds: std::collections::BTreeMap<String, serde_json::Value>,
    exported_at: String,
}

#[derive(Debug, Serialize)]
struct BoxExportReceiptV1 {
    schema_version: &'static str,
    file_name: String,
    bytes: usize,
}

pub fn visualizer_url(game: &str, workspace_id: &str) -> Option<String> {
    let game = parse_game(game)?;
    if !valid_workspace_token(workspace_id) {
        return None;
    }
    #[cfg(any(windows, target_os = "android"))]
    return Some(format!(
        "https://{VISUALIZER_SCHEME}.localhost/{game}/index.html?workspace={workspace_id}"
    ));
    #[cfg(not(any(windows, target_os = "android")))]
    return Some(format!(
        "{VISUALIZER_SCHEME}://localhost/{game}/index.html?workspace={workspace_id}"
    ));
}

pub fn visualizer_is_ready(root: &Path, game: &str) -> bool {
    let Some(game) = parse_game(game) else {
        return false;
    };
    let Ok(data) = read_workspace_visualizer_file(root, game, Path::new("data.json")) else {
        return false;
    };
    let Ok(value) = serde_json::from_slice::<serde_json::Value>(&data) else {
        return false;
    };
    avatar_references_are_ready(root, game, &value)
}

#[cfg(test)]
pub fn handle_workspace_request(
    root: &Path,
    current_workspace_id: &str,
    storage_scope_id: &str,
    webview_label: &str,
    request: Request<Vec<u8>>,
) -> Response<Vec<u8>> {
    handle_workspace_request_with_export_directory(
        root,
        current_workspace_id,
        storage_scope_id,
        None,
        webview_label,
        request,
    )
}

pub fn handle_workspace_request_with_export_directory(
    root: &Path,
    current_workspace_id: &str,
    storage_scope_id: &str,
    export_directory: Option<&Path>,
    webview_label: &str,
    request: Request<Vec<u8>>,
) -> Response<Vec<u8>> {
    if webview_label != "main" {
        return error_response(StatusCode::FORBIDDEN);
    }
    let route = match parse_route(request.uri().path()) {
        Ok(route) => route,
        Err(status) => return error_response(status),
    };
    let workspace_id = match request_workspace_token(request.uri().query()) {
        Ok(token) if token == current_workspace_id => token,
        Ok(_) => return error_response(StatusCode::CONFLICT),
        Err(status) => return error_response(status),
    };
    match route {
        Route::Static {
            game,
            relative,
            mime,
            cache,
        } => {
            if request.method() != Method::GET && request.method() != Method::HEAD {
                return method_not_allowed("GET, HEAD");
            }
            let bytes =
                match read_protocol_asset(root, game, &relative, &workspace_id, storage_scope_id) {
                    Ok(bytes) => bytes,
                    Err(_) => return error_response(StatusCode::NOT_FOUND),
                };
            let length = bytes.len();
            let body = if request.method() == Method::HEAD {
                Vec::new()
            } else {
                bytes
            };
            response(StatusCode::OK, mime, cache, body, Some(length))
        }
        Route::BoxApi { game } => handle_box(root, game, request),
        Route::BoxExport { game } => handle_box_export(export_directory, game, request),
    }
}

pub(crate) fn unavailable_response() -> Response<Vec<u8>> {
    error_response(StatusCode::SERVICE_UNAVAILABLE)
}

fn handle_box(root: &Path, game: &str, request: Request<Vec<u8>>) -> Response<Vec<u8>> {
    if request.method() == Method::OPTIONS {
        return response(
            StatusCode::NO_CONTENT,
            "text/plain; charset=utf-8",
            "no-store",
            Vec::new(),
            Some(0),
        );
    }
    if request.method() != Method::GET && request.method() != Method::PUT {
        return method_not_allowed("GET, PUT, OPTIONS");
    }
    let path = match box_state_path(root, game) {
        Ok(path) => path,
        Err(_) => return error_response(StatusCode::NOT_FOUND),
    };
    if validate_box_target(root, &path).is_err() {
        return error_response(StatusCode::NOT_FOUND);
    }
    let state = if request.method() == Method::GET {
        match fs::symlink_metadata(&path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => BoxState::default(),
            Ok(metadata) if !metadata.is_file() => {
                return error_response(StatusCode::UNPROCESSABLE_ENTITY)
            }
            Ok(metadata) if metadata.len() > MAX_BOX_BYTES => {
                return error_response(StatusCode::PAYLOAD_TOO_LARGE)
            }
            Ok(_) => match box_state::load(&path) {
                Ok(state) => match ensure_box_state_limits(&state) {
                    Ok(()) => state,
                    Err(error) => return box_limit_error_response(error),
                },
                Err(_) => return error_response(StatusCode::UNPROCESSABLE_ENTITY),
            },
            Err(_) => return error_response(StatusCode::INTERNAL_SERVER_ERROR),
        }
    } else {
        if request.body().len() as u64 > MAX_BOX_BYTES {
            return error_response(StatusCode::PAYLOAD_TOO_LARGE);
        }
        let state = match serde_json::from_slice::<BoxState>(request.body()) {
            Ok(state) => state.normalize(),
            Err(_) => return error_response(StatusCode::BAD_REQUEST),
        };
        if let Err(error) = ensure_box_state_limits(&state) {
            return box_limit_error_response(error);
        }
        let _lease = match WorkspaceWriteLease::acquire(root) {
            Ok(lease) => lease,
            Err(WorkspaceWriteLeaseError::Busy) => return error_response(StatusCode::CONFLICT),
            Err(_) => return error_response(StatusCode::INTERNAL_SERVER_ERROR),
        };
        if box_state::save(&path, state.clone()).is_err() {
            return error_response(StatusCode::INTERNAL_SERVER_ERROR);
        }
        state
    };
    match serde_json::to_vec(&state.normalize()) {
        Ok(body) => response(
            StatusCode::OK,
            "application/json; charset=utf-8",
            "no-store",
            body,
            None,
        ),
        Err(_) => error_response(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

fn handle_box_export(
    export_directory: Option<&Path>,
    game: &str,
    request: Request<Vec<u8>>,
) -> Response<Vec<u8>> {
    if request.method() == Method::OPTIONS {
        return response(
            StatusCode::NO_CONTENT,
            "text/plain; charset=utf-8",
            "no-store",
            Vec::new(),
            Some(0),
        );
    }
    if request.method() != Method::POST {
        return method_not_allowed("POST, OPTIONS");
    }
    if request.body().len() as u64 > MAX_BOX_BYTES {
        return error_response(StatusCode::PAYLOAD_TOO_LARGE);
    }
    let document = match serde_json::from_slice::<BoxExportDocumentV1>(request.body()) {
        Ok(document) => document,
        Err(_) => return error_response(StatusCode::BAD_REQUEST),
    };
    let expected_version = if game == "hsr" { 2 } else { 3 };
    if document.version != expected_version
        || !valid_javascript_iso_timestamp(&document.updated_at)
        || !valid_javascript_iso_timestamp(&document.exported_at)
    {
        return error_response(StatusCode::UNPROCESSABLE_ENTITY);
    }
    let state = BoxState {
        version: document.version,
        updated_at: document.updated_at.clone(),
        owned: document.owned.clone(),
        build_slug: document.build_slug.clone(),
        builds: document.builds.clone(),
    };
    if let Err(error) = ensure_box_state_limits(&state) {
        return box_limit_error_response(error);
    }
    let body = match serde_json::to_vec_pretty(&document) {
        Ok(body) if body.len() as u64 <= MAX_BOX_BYTES => body,
        Ok(_) => return error_response(StatusCode::PAYLOAD_TOO_LARGE),
        Err(_) => return error_response(StatusCode::INTERNAL_SERVER_ERROR),
    };
    let Some(export_directory) = export_directory else {
        return error_response(StatusCode::SERVICE_UNAVAILABLE);
    };
    let file_name = match create_box_export_file(export_directory, game, &body) {
        Ok(file_name) => file_name,
        Err(_) => return error_response(StatusCode::INTERNAL_SERVER_ERROR),
    };
    let receipt = BoxExportReceiptV1 {
        schema_version: BOX_EXPORT_RECEIPT_SCHEMA_V1,
        file_name,
        bytes: body.len(),
    };
    match serde_json::to_vec(&receipt) {
        Ok(body) => response(
            StatusCode::CREATED,
            "application/json; charset=utf-8",
            "no-store",
            body,
            None,
        ),
        Err(_) => error_response(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

fn valid_javascript_iso_timestamp(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 24
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'.'
        || bytes[23] != b'Z'
    {
        return false;
    }
    bytes.iter().enumerate().all(|(index, byte)| {
        matches!(index, 4 | 7 | 10 | 13 | 16 | 19 | 23) || byte.is_ascii_digit()
    })
}

fn create_box_export_file(directory: &Path, game: &str, bytes: &[u8]) -> std::io::Result<String> {
    if !fs::metadata(directory)?.is_dir() {
        return Err(std::io::Error::other("export directory is unavailable"));
    }
    for collision in 0..MAX_BOX_EXPORT_COLLISIONS {
        let file_name = if collision == 0 {
            format!("{game}_box_state.json")
        } else {
            format!("{game}_box_state ({collision}).json")
        };
        let path = directory.join(&file_name);
        let mut file = match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
        {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        };
        if let Err(error) = file.write_all(bytes).and_then(|_| file.sync_all()) {
            drop(file);
            let _ = fs::remove_file(&path);
            return Err(error);
        }
        return Ok(file_name);
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::AlreadyExists,
        "too many Box export name collisions",
    ))
}

fn box_limit_error_response(error: BoxStateLimitError) -> Response<Vec<u8>> {
    match error {
        BoxStateLimitError::TooLarge => error_response(StatusCode::PAYLOAD_TOO_LARGE),
        BoxStateLimitError::TooDeep => error_response(StatusCode::UNPROCESSABLE_ENTITY),
        BoxStateLimitError::Serialize => error_response(StatusCode::INTERNAL_SERVER_ERROR),
    }
}

fn parse_route(raw_path: &str) -> Result<Route, StatusCode> {
    let decoded = strict_percent_decode(raw_path).ok_or(StatusCode::BAD_REQUEST)?;
    if !decoded.starts_with('/')
        || decoded.contains('\\')
        || decoded.contains('\0')
        || decoded.contains('%')
    {
        return Err(StatusCode::BAD_REQUEST);
    }
    let segments: Vec<_> = decoded[1..].split('/').collect();
    if segments
        .iter()
        .any(|part| part.is_empty() || *part == "." || *part == "..")
    {
        return Err(StatusCode::BAD_REQUEST);
    }
    if let ["api", game, "box", "export"] = segments.as_slice() {
        return Ok(Route::BoxExport {
            game: parse_game(game).ok_or(StatusCode::NOT_FOUND)?,
        });
    }
    if let ["api", game, "box"] = segments.as_slice() {
        return Ok(Route::BoxApi {
            game: parse_game(game).ok_or(StatusCode::NOT_FOUND)?,
        });
    }
    let game =
        parse_game(segments.first().copied().unwrap_or_default()).ok_or(StatusCode::NOT_FOUND)?;
    if let [_, name @ ("index.html" | "app.js" | "solver.js" | "styles.css" | "data.json")] = segments.as_slice()
    {
        let (mime, cache) = static_headers(name);
        return Ok(Route::Static {
            game,
            relative: PathBuf::from(name),
            mime,
            cache,
        });
    }
    if let [_, "assets", "avatars", name] = segments.as_slice() {
        let mime = avatar_mime(name).ok_or(StatusCode::NOT_FOUND)?;
        if !safe_avatar_name(name) {
            return Err(StatusCode::BAD_REQUEST);
        }
        return Ok(Route::Static {
            game,
            relative: PathBuf::from("assets").join("avatars").join(name),
            mime,
            cache: "no-store",
        });
    }
    Err(StatusCode::NOT_FOUND)
}

fn parse_game(game: &str) -> Option<&'static str> {
    match game {
        "hsr" => Some("hsr"),
        "zzz" => Some("zzz"),
        _ => None,
    }
}

fn static_headers(name: &str) -> (&'static str, &'static str) {
    match name {
        "index.html" => ("text/html; charset=utf-8", "no-store"),
        "app.js" | "solver.js" => ("text/javascript; charset=utf-8", "no-store"),
        "styles.css" => ("text/css; charset=utf-8", "no-cache"),
        "data.json" => ("application/json; charset=utf-8", "no-store"),
        _ => ("application/octet-stream", "no-store"),
    }
}

fn avatar_mime(name: &str) -> Option<&'static str> {
    match Path::new(name)
        .extension()?
        .to_str()?
        .to_ascii_lowercase()
        .as_str()
    {
        "webp" => Some("image/webp"),
        "png" => Some("image/png"),
        "jpg" | "jpeg" => Some("image/jpeg"),
        _ => None,
    }
}

fn safe_avatar_name(name: &str) -> bool {
    name.as_bytes()
        .first()
        .is_some_and(u8::is_ascii_alphanumeric)
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

fn strict_percent_decode(value: &str) -> Option<String> {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' {
            let high = hex(*bytes.get(index + 1)?)?;
            let low = hex(*bytes.get(index + 2)?)?;
            output.push(high * 16 + low);
            index += 3;
        } else {
            output.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8(output).ok()
}

fn hex(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

fn visualizer_relative_root(root: &Path, game: &str) -> PathBuf {
    let (primary, legacy) = match game {
        "hsr" => ("out", "hsr_endgame_export"),
        _ => ("out_zzz", "zzz_endgame_export"),
    };
    let primary_data = root.join(primary).join("visualizer/data.json");
    if primary_data.exists() || !root.join(legacy).join("visualizer/data.json").is_file() {
        PathBuf::from(primary).join("visualizer")
    } else {
        PathBuf::from(legacy).join("visualizer")
    }
}

fn read_protocol_asset(
    root: &Path,
    game: &str,
    relative: &Path,
    workspace_id: &str,
    storage_scope_id: &str,
) -> std::io::Result<Vec<u8>> {
    if let Some(name) = relative.to_str() {
        if let Some(bytes) = miho_core::visualizer::visualizer_static_asset(game, name) {
            if name == "index.html" {
                return tokenized_index(bytes, workspace_id);
            }
            if name == "app.js" {
                return tokenized_app(bytes, workspace_id, storage_scope_id);
            }
            return Ok(bytes.to_vec());
        }
    }
    let bytes = read_workspace_visualizer_file(root, game, relative)?;
    if relative == Path::new("data.json") {
        return tokenized_data(&bytes, workspace_id);
    }
    Ok(bytes)
}

fn tokenized_index(bytes: &[u8], workspace_id: &str) -> std::io::Result<Vec<u8>> {
    let html = std::str::from_utf8(bytes).map_err(|_| std::io::Error::other("invalid asset"))?;
    if !valid_workspace_token(workspace_id) {
        return Err(std::io::Error::other("invalid workspace token"));
    }
    if !html.contains("href=\"./styles.css\"")
        || !html.contains("src=\"./solver.js\"")
        || !html.contains("src=\"./app.js\"")
    {
        return Err(std::io::Error::other("unsupported trusted index"));
    }
    let styles = format!("href=\"./styles.css?workspace={workspace_id}\"");
    let solver = format!("src=\"./solver.js?workspace={workspace_id}\"");
    let script = format!("src=\"./app.js?workspace={workspace_id}\"");
    let html = html
        .replace("href=\"./styles.css\"", &styles)
        .replace("src=\"./solver.js\"", &solver)
        .replace("src=\"./app.js\"", &script);
    Ok(html.into_bytes())
}

const DESKTOP_APP_BOOTSTRAP: &str = r#"(()=>{
'use strict';
const accessToken='__MIHO_WORKSPACE_TOKEN__';
const storageScope='__MIHO_STORAGE_SCOPE__';
Object.defineProperty(globalThis,'__MIHO_DESKTOP__',{value:true,writable:false,configurable:false});
const nativeFetch=globalThis.fetch.bind(globalThis);
globalThis.fetch=(input,init)=>{
  let target=input;
  if(typeof input==='string'||input instanceof URL){
    const url=new URL(String(input),globalThis.location.href);
    if(url.origin===globalThis.location.origin){
      url.searchParams.set('workspace',accessToken);
      target=url.href;
    }
  }
  return nativeFetch(target,init);
};
const storage=globalThis.localStorage;
const storagePrototype=globalThis.Storage&&globalThis.Storage.prototype;
if(storage&&storagePrototype){
  const prefix=`miho-desktop:${storageScope}:`;
  const nativeGet=storagePrototype.getItem;
  const nativeSet=storagePrototype.setItem;
  const nativeRemove=storagePrototype.removeItem;
  storagePrototype.getItem=function(key){return nativeGet.call(this,this===storage?prefix+String(key):key);};
  storagePrototype.setItem=function(key,value){return nativeSet.call(this,this===storage?prefix+String(key):key,value);};
  storagePrototype.removeItem=function(key){return nativeRemove.call(this,this===storage?prefix+String(key):key);};
}
})();
"#;

fn tokenized_app(
    bytes: &[u8],
    workspace_id: &str,
    storage_scope_id: &str,
) -> std::io::Result<Vec<u8>> {
    if !valid_workspace_token(workspace_id) || !valid_workspace_token(storage_scope_id) {
        return Err(std::io::Error::other("invalid workspace token"));
    }
    std::str::from_utf8(bytes).map_err(|_| std::io::Error::other("invalid asset"))?;
    let bootstrap = DESKTOP_APP_BOOTSTRAP
        .replace("__MIHO_WORKSPACE_TOKEN__", workspace_id)
        .replace("__MIHO_STORAGE_SCOPE__", storage_scope_id);
    let mut output = Vec::with_capacity(bootstrap.len() + bytes.len());
    output.extend_from_slice(bootstrap.as_bytes());
    output.extend_from_slice(bytes);
    Ok(output)
}

fn tokenized_data(bytes: &[u8], workspace_id: &str) -> std::io::Result<Vec<u8>> {
    if !valid_workspace_token(workspace_id) {
        return Err(std::io::Error::other("invalid workspace token"));
    }
    let mut value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|_| std::io::Error::other("invalid data"))?;
    scope_avatar_urls(&mut value, workspace_id);
    serde_json::to_vec(&value).map_err(std::io::Error::other)
}

fn scope_avatar_urls(value: &mut serde_json::Value, workspace_id: &str) {
    match value {
        serde_json::Value::String(value) => {
            if let Some(scoped) = scoped_avatar_url(value, workspace_id) {
                *value = scoped;
            }
        }
        serde_json::Value::Array(values) => {
            for value in values {
                scope_avatar_urls(value, workspace_id);
            }
        }
        serde_json::Value::Object(values) => {
            for value in values.values_mut() {
                scope_avatar_urls(value, workspace_id);
            }
        }
        _ => {}
    }
}

fn scoped_avatar_url(value: &str, workspace_id: &str) -> Option<String> {
    let (without_fragment, fragment) = value
        .split_once('#')
        .map_or((value, None), |(head, tail)| (head, Some(tail)));
    let (path, query) = without_fragment
        .split_once('?')
        .map_or((without_fragment, None), |(path, query)| {
            (path, Some(query))
        });
    let name = path.strip_prefix("./assets/avatars/")?;
    if !safe_avatar_name(name) || avatar_mime(name).is_none() {
        return None;
    }
    let mut query_items: Vec<&str> = query
        .unwrap_or_default()
        .split('&')
        .filter(|item| !item.is_empty())
        .filter(|item| item.split_once('=').unwrap_or((item, "")).0 != "workspace")
        .collect();
    let workspace = format!("workspace={workspace_id}");
    query_items.push(&workspace);
    let mut scoped = format!("{path}?{}", query_items.join("&"));
    if let Some(fragment) = fragment {
        scoped.push('#');
        scoped.push_str(fragment);
    }
    Some(scoped)
}

fn valid_workspace_token(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

fn request_workspace_token(query: Option<&str>) -> Result<String, StatusCode> {
    let mut token = None;
    for item in query
        .unwrap_or_default()
        .split('&')
        .filter(|item| !item.is_empty())
    {
        let (key, value) = item.split_once('=').unwrap_or((item, ""));
        if key != "workspace" {
            continue;
        }
        if token.is_some() {
            return Err(StatusCode::BAD_REQUEST);
        }
        let decoded = strict_percent_decode(value).ok_or(StatusCode::BAD_REQUEST)?;
        if decoded.contains('%') {
            return Err(StatusCode::BAD_REQUEST);
        }
        if !valid_workspace_token(&decoded) {
            return Err(StatusCode::BAD_REQUEST);
        }
        token = Some(decoded);
    }
    token.ok_or(StatusCode::CONFLICT)
}

fn read_workspace_visualizer_file(
    root: &Path,
    game: &str,
    relative: &Path,
) -> std::io::Result<Vec<u8>> {
    let target = checked_workspace_visualizer_file(root, game, relative)?;
    fs::read(target)
}

fn checked_workspace_visualizer_file(
    root: &Path,
    game: &str,
    relative: &Path,
) -> std::io::Result<PathBuf> {
    let limit = if relative == Path::new("data.json") {
        MAX_VISUALIZER_DATA_BYTES
    } else if relative
        .parent()
        .is_some_and(|parent| parent == Path::new("assets/avatars"))
    {
        MAX_AVATAR_BYTES
    } else {
        return Err(std::io::Error::other("unsupported workspace asset"));
    };
    let relative = visualizer_relative_root(root, game).join(relative);
    let target = validate_existing_file(root, &relative)?;
    if fs::metadata(&target)?.len() > limit {
        return Err(std::io::Error::other("workspace asset is too large"));
    }
    Ok(target)
}

fn avatar_references_are_ready(root: &Path, game: &str, value: &serde_json::Value) -> bool {
    match value {
        serde_json::Value::String(value) => {
            let Some(reference) = value.strip_prefix("./assets/avatars/") else {
                return true;
            };
            let name = reference.split(['?', '#']).next().unwrap_or_default();
            safe_avatar_name(name)
                && avatar_mime(name).is_some()
                && checked_workspace_visualizer_file(
                    root,
                    game,
                    &PathBuf::from("assets").join("avatars").join(name),
                )
                .is_ok()
        }
        serde_json::Value::Array(values) => values
            .iter()
            .all(|value| avatar_references_are_ready(root, game, value)),
        serde_json::Value::Object(values) => values
            .values()
            .all(|value| avatar_references_are_ready(root, game, value)),
        _ => true,
    }
}

fn validate_existing_file(root: &Path, relative: &Path) -> std::io::Result<PathBuf> {
    validate_root(root)?;
    let mut current = root.to_path_buf();
    for component in relative.components() {
        let std::path::Component::Normal(component) = component else {
            return Err(std::io::Error::other("unsafe path"));
        };
        current.push(component);
        let metadata = fs::symlink_metadata(&current)?;
        if metadata.file_type().is_symlink() || is_reparse(&metadata) {
            return Err(std::io::Error::other("unsafe path"));
        }
    }
    if !fs::metadata(&current)?.is_file() {
        return Err(std::io::Error::other("not a file"));
    }
    Ok(current)
}

pub(crate) fn validate_box_target(root: &Path, target: &Path) -> std::io::Result<()> {
    validate_root(root)?;
    let relative = target
        .strip_prefix(root)
        .map_err(|_| std::io::Error::other("unsafe path"))?;
    let mut current = root.to_path_buf();
    for component in relative.components() {
        let std::path::Component::Normal(component) = component else {
            return Err(std::io::Error::other("unsafe path"));
        };
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() || is_reparse(&metadata) => {
                return Err(std::io::Error::other("unsafe path"))
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

fn validate_root(root: &Path) -> std::io::Result<()> {
    let metadata = fs::symlink_metadata(root)?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse(&metadata) {
        return Err(std::io::Error::other("unsafe root"));
    }
    Ok(())
}

fn is_reparse(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        metadata.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn response(
    status: StatusCode,
    mime: &str,
    cache: &str,
    body: Vec<u8>,
    length: Option<usize>,
) -> Response<Vec<u8>> {
    let mut builder = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, mime)
        .header("X-Content-Type-Options", "nosniff")
        .header(header::CONTENT_SECURITY_POLICY, VISUALIZER_CSP)
        .header(header::REFERRER_POLICY, "no-referrer")
        .header(header::CACHE_CONTROL, cache)
        .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, protocol_origin())
        .header(
            header::ACCESS_CONTROL_ALLOW_METHODS,
            "GET, PUT, POST, OPTIONS",
        )
        .header(header::ACCESS_CONTROL_ALLOW_HEADERS, "Content-Type")
        .header(header::VARY, "Origin");
    if let Some(length) = length {
        builder = builder.header(header::CONTENT_LENGTH, length);
    }
    builder
        .body(body)
        .expect("static protocol headers are valid")
}

fn error_response(status: StatusCode) -> Response<Vec<u8>> {
    response(
        status,
        "text/plain; charset=utf-8",
        "no-store",
        status
            .canonical_reason()
            .unwrap_or("Request rejected")
            .as_bytes()
            .to_vec(),
        None,
    )
}

fn method_not_allowed(allow: &str) -> Response<Vec<u8>> {
    let mut response = error_response(StatusCode::METHOD_NOT_ALLOWED);
    response
        .headers_mut()
        .insert(header::ALLOW, allow.parse().expect("static Allow header"));
    response
}

fn protocol_origin() -> &'static str {
    #[cfg(any(windows, target_os = "android"))]
    {
        "https://miho-visualizer.localhost"
    }
    #[cfg(not(any(windows, target_os = "android")))]
    {
        "miho-visualizer://localhost"
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);
    const TOKEN: &str = "workspace-test-session-0001";
    const STORAGE_SCOPE: &str =
        "storage-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    fn root() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "miho-protocol-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        for game in ["out", "out_zzz"] {
            let visualizer = root.join(game).join("visualizer");
            fs::create_dir_all(visualizer.join("assets/avatars")).unwrap();
            for (name, data) in [
                ("index.html", b"html".as_slice()),
                ("app.js", b"js"),
                ("solver.js", b"solver"),
                ("styles.css", b"css"),
                ("data.json", b"{}"),
            ] {
                fs::write(visualizer.join(name), data).unwrap();
            }
            fs::write(visualizer.join("assets/avatars/agent-one.webp"), b"webp").unwrap();
        }
        root
    }

    fn request(method: Method, uri: &str, body: Vec<u8>) -> Request<Vec<u8>> {
        Request::builder()
            .method(method)
            .uri(uri)
            .body(body)
            .unwrap()
    }

    fn handle_request(
        root: &Path,
        webview_label: &str,
        request: Request<Vec<u8>>,
    ) -> Response<Vec<u8>> {
        handle_request_with_export_directory(root, None, webview_label, request)
    }

    fn handle_request_with_export_directory(
        root: &Path,
        export_directory: Option<&Path>,
        webview_label: &str,
        mut request: Request<Vec<u8>>,
    ) -> Response<Vec<u8>> {
        let separator = if request.uri().query().is_some() {
            '&'
        } else {
            '?'
        };
        let uri = format!("{}{separator}workspace={TOKEN}", request.uri());
        *request.uri_mut() = uri.parse().unwrap();
        handle_workspace_request_with_export_directory(
            root,
            TOKEN,
            STORAGE_SCOPE,
            export_directory,
            webview_label,
            request,
        )
    }

    #[test]
    fn serves_fixed_resources_queries_mime_and_head() {
        let root = root();
        let get = handle_request(
            &root,
            "main",
            request(Method::GET, "/hsr/app.js?v=1", Vec::new()),
        );
        assert_eq!(get.status(), StatusCode::OK);
        assert_eq!(
            get.headers()[header::CONTENT_TYPE],
            "text/javascript; charset=utf-8"
        );
        assert_eq!(get.headers()[header::CACHE_CONTROL], "no-store");
        let trusted_app = miho_core::visualizer::visualizer_static_asset("hsr", "app.js").unwrap();
        assert_eq!(
            get.body(),
            &tokenized_app(trusted_app, TOKEN, STORAGE_SCOPE).unwrap()
        );
        assert!(get.body().ends_with(trusted_app));
        let app = String::from_utf8_lossy(get.body());
        assert!(app.contains("const accessToken='workspace-test-session-0001'"));
        assert!(app.contains(&format!("const storageScope='{STORAGE_SCOPE}'")));
        assert!(app.contains("Object.defineProperty(globalThis,'__MIHO_DESKTOP__',{value:true"));
        assert!(app.contains("url.searchParams.set('workspace',accessToken)"));
        assert!(app.contains("const prefix=`miho-desktop:${storageScope}:`"));
        assert_ne!(get.body(), b"js");
        for (game, version) in [("hsr", "version:2"), ("zzz", "version:3")] {
            let app = std::str::from_utf8(
                miho_core::visualizer::visualizer_static_asset(game, "app.js").unwrap(),
            )
            .unwrap();
            assert!(app.contains(version));
            assert!(app.contains(&format!("fetch('/api/{game}/box/export'")));
            assert!(app.contains("schema_version!=='miho-box-export-receipt-v1'"));
            assert!(app.contains("button.textContent='已导出到下载文件夹'"));
            assert!(app.contains("button.textContent='导出失败'"));
            assert!(app.contains("setTimeout(()=>URL.revokeObjectURL(url),1000)"));
            assert!(!app.contains("a.click();URL.revokeObjectURL"));
        }
        for name in ["index.html", "solver.js", "styles.css"] {
            let trusted = handle_request(
                &root,
                "main",
                request(Method::GET, &format!("/hsr/{name}"), Vec::new()),
            );
            let expected = miho_core::visualizer::visualizer_static_asset("hsr", name).unwrap();
            if name == "index.html" {
                assert_eq!(trusted.body(), &tokenized_index(expected, TOKEN).unwrap());
                let html = String::from_utf8_lossy(trusted.body());
                assert!(html.contains("./app.js?workspace=workspace-test-session-0001"));
                assert!(html.contains("./solver.js?workspace=workspace-test-session-0001"));
                assert!(html.contains("./styles.css?workspace=workspace-test-session-0001"));
            } else {
                assert_eq!(trusted.body(), expected);
            }
            let workspace_bytes = fs::read(root.join("out/visualizer").join(name)).unwrap();
            assert_ne!(trusted.body().as_slice(), workspace_bytes.as_slice());
        }
        let data = handle_request(
            &root,
            "main",
            request(Method::GET, "/hsr/data.json", Vec::new()),
        );
        assert_eq!(data.body(), b"{}");
        let head = handle_request(
            &root,
            "main",
            request(
                Method::HEAD,
                "/zzz/assets/avatars/agent-one.webp?alias=x",
                Vec::new(),
            ),
        );
        assert_eq!(head.status(), StatusCode::OK);
        assert!(head.body().is_empty());
        assert_eq!(head.headers()[header::CONTENT_LENGTH], "4");
        assert_eq!(head.headers()[header::CACHE_CONTROL], "no-store");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn desktop_box_export_is_strict_collision_safe_and_versioned_per_game() {
        let root = root();
        let downloads = root.join("downloads");
        fs::create_dir(&downloads).unwrap();
        fs::write(downloads.join("hsr_box_state.json"), b"existing-user-file").unwrap();

        let hsr_document = serde_json::json!({
            "version": 2,
            "updatedAt": "2026-07-17T12:34:56.789Z",
            "owned": ["acheron"],
            "buildSlug": "acheron",
            "builds": {"acheron": {"level": 80}},
            "exportedAt": "2026-07-17T12:34:56.789Z"
        });
        let exported = handle_request_with_export_directory(
            &root,
            Some(&downloads),
            "main",
            request(
                Method::POST,
                "/api/hsr/box/export",
                serde_json::to_vec(&hsr_document).unwrap(),
            ),
        );
        assert_eq!(exported.status(), StatusCode::CREATED);
        let receipt: serde_json::Value = serde_json::from_slice(exported.body()).unwrap();
        assert_eq!(receipt["schema_version"], BOX_EXPORT_RECEIPT_SCHEMA_V1);
        assert_eq!(receipt["file_name"], "hsr_box_state (1).json");
        assert_eq!(
            fs::read(downloads.join("hsr_box_state.json")).unwrap(),
            b"existing-user-file"
        );
        let exported_path = downloads.join(receipt["file_name"].as_str().unwrap());
        assert_eq!(
            receipt["bytes"].as_u64().unwrap(),
            fs::metadata(&exported_path).unwrap().len()
        );
        let written: serde_json::Value =
            serde_json::from_slice(&fs::read(&exported_path).unwrap()).unwrap();
        assert_eq!(written, hsr_document);

        let zzz_document = serde_json::json!({
            "version": 3,
            "updatedAt": "2026-07-17T12:34:56.789Z",
            "owned": ["astra-yao"],
            "buildSlug": "astra-yao",
            "builds": {},
            "exportedAt": "2026-07-17T12:34:56.789Z"
        });
        let zzz_exported = handle_request_with_export_directory(
            &root,
            Some(&downloads),
            "main",
            request(
                Method::POST,
                "/api/zzz/box/export",
                serde_json::to_vec(&zzz_document).unwrap(),
            ),
        );
        assert_eq!(zzz_exported.status(), StatusCode::CREATED);
        let zzz_receipt: serde_json::Value = serde_json::from_slice(zzz_exported.body()).unwrap();
        let zzz_written: serde_json::Value = serde_json::from_slice(
            &fs::read(downloads.join(zzz_receipt["file_name"].as_str().unwrap())).unwrap(),
        )
        .unwrap();
        assert_eq!(zzz_written, zzz_document);

        let wrong_game_version = handle_request_with_export_directory(
            &root,
            Some(&downloads),
            "main",
            request(
                Method::POST,
                "/api/zzz/box/export",
                serde_json::to_vec(&hsr_document).unwrap(),
            ),
        );
        assert_eq!(
            wrong_game_version.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let mut unknown_field = hsr_document.clone();
        unknown_field["targetPath"] = serde_json::Value::String("outside.json".to_owned());
        let rejected_unknown = handle_request_with_export_directory(
            &root,
            Some(&downloads),
            "main",
            request(
                Method::POST,
                "/api/hsr/box/export",
                serde_json::to_vec(&unknown_field).unwrap(),
            ),
        );
        assert_eq!(rejected_unknown.status(), StatusCode::BAD_REQUEST);

        let mut nested = serde_json::Value::Null;
        for _ in 0..=crate::MAX_BOX_VALUE_DEPTH {
            nested = serde_json::Value::Array(vec![nested]);
        }
        let mut too_deep = hsr_document.clone();
        too_deep["builds"]["acheron"] = nested;
        let rejected_depth = handle_request_with_export_directory(
            &root,
            Some(&downloads),
            "main",
            request(
                Method::POST,
                "/api/hsr/box/export",
                serde_json::to_vec(&too_deep).unwrap(),
            ),
        );
        assert_eq!(rejected_depth.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let rejected_size = handle_request_with_export_directory(
            &root,
            Some(&downloads),
            "main",
            request(
                Method::POST,
                "/api/hsr/box/export",
                vec![b'x'; MAX_BOX_BYTES as usize + 1],
            ),
        );
        assert_eq!(rejected_size.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert_eq!(fs::read_dir(&downloads).unwrap().count(), 3);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn desktop_data_scopes_only_valid_local_avatar_urls() {
        let root = root();
        fs::write(
            root.join("out/visualizer/data.json"),
            br#"{"plain":"value","external":"https://example.invalid/avatar.webp","avatar":"./assets/avatars/agent-one.webp","nested":["./assets/avatars/agent-one.webp?v=1&workspace=attacker#face","./assets/avatars/../secret.webp"]}"#,
        )
        .unwrap();
        let response = handle_request(
            &root,
            "main",
            request(Method::GET, "/hsr/data.json", Vec::new()),
        );
        assert_eq!(response.status(), StatusCode::OK);
        let data: serde_json::Value = serde_json::from_slice(response.body()).unwrap();
        assert_eq!(data["plain"], "value");
        assert_eq!(data["external"], "https://example.invalid/avatar.webp");
        assert_eq!(
            data["avatar"],
            "./assets/avatars/agent-one.webp?workspace=workspace-test-session-0001"
        );
        assert_eq!(
            data["nested"][0],
            "./assets/avatars/agent-one.webp?v=1&workspace=workspace-test-session-0001#face"
        );
        assert_eq!(data["nested"][1], "./assets/avatars/../secret.webp");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn workspace_tokens_are_bounded_and_injection_safe() {
        let trusted_app = miho_core::visualizer::visualizer_static_asset("hsr", "app.js").unwrap();
        for invalid in [
            "",
            "workspace/slash",
            "workspace'quote",
            "workspace_unicode_工作区",
        ] {
            assert!(visualizer_url("hsr", invalid).is_none());
            assert!(tokenized_index(b"<html></html>", invalid).is_err());
            assert!(tokenized_app(trusted_app, invalid, STORAGE_SCOPE).is_err());
            assert!(tokenized_app(trusted_app, TOKEN, invalid).is_err());
        }
        let too_long = "a".repeat(129);
        assert!(visualizer_url("hsr", &too_long).is_none());
        assert!(tokenized_app(trusted_app, &too_long, STORAGE_SCOPE).is_err());
        assert!(tokenized_app(trusted_app, TOKEN, &too_long).is_err());
    }

    #[test]
    fn box_api_get_put_options_and_normalization() {
        let root = root();
        let initial = handle_request(
            &root,
            "main",
            request(Method::GET, "/api/zzz/box", Vec::new()),
        );
        assert_eq!(initial.status(), StatusCode::OK);
        let put = handle_request(&root, "main", request(Method::PUT, "/api/zzz/box", br#"{"version":1,"updatedAt":"x","owned":[" nom ","nom","__codex_test__"],"buildSlug":"","builds":{}}"#.to_vec()));
        assert_eq!(put.status(), StatusCode::OK);
        let saved: BoxState = serde_json::from_slice(put.body()).unwrap();
        assert_eq!(saved.version, 2);
        assert_eq!(saved.owned, ["nom"]);
        let persisted = handle_request(
            &root,
            "main",
            request(Method::GET, "/api/zzz/box", Vec::new()),
        );
        assert_eq!(
            serde_json::from_slice::<BoxState>(persisted.body())
                .unwrap()
                .owned,
            ["nom"]
        );
        let options = handle_request(
            &root,
            "main",
            request(Method::OPTIONS, "/api/hsr/box", Vec::new()),
        );
        assert_eq!(options.status(), StatusCode::NO_CONTENT);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn box_api_enforces_existing_pretty_size_and_depth_limits() {
        let root = root();
        let box_path = root.join(".miho/zzz_box_state.json");
        fs::create_dir_all(box_path.parent().unwrap()).unwrap();
        let oversized = fs::File::create(&box_path).unwrap();
        oversized.set_len(MAX_BOX_BYTES + 1).unwrap();
        drop(oversized);
        let get = handle_request(
            &root,
            "main",
            request(Method::GET, "/api/zzz/box", Vec::new()),
        );
        assert_eq!(get.status(), StatusCode::PAYLOAD_TOO_LARGE);
        fs::remove_file(&box_path).unwrap();

        let mut deep_value = serde_json::Value::Null;
        for _ in 0..=crate::MAX_BOX_VALUE_DEPTH {
            deep_value = serde_json::Value::Array(vec![deep_value]);
        }
        let mut deep = BoxState::default();
        deep.builds.insert("agent".to_owned(), deep_value);
        let deep_put = handle_request(
            &root,
            "main",
            request(
                Method::PUT,
                "/api/zzz/box",
                serde_json::to_vec(&deep).unwrap(),
            ),
        );
        assert_eq!(deep_put.status(), StatusCode::UNPROCESSABLE_ENTITY);
        assert!(!box_path.exists());

        let mut expanded = BoxState::default();
        expanded.builds.insert(
            "agent".to_owned(),
            serde_json::Value::Array(vec![serde_json::Value::from(0); 150_000]),
        );
        let compact = serde_json::to_vec(&expanded).unwrap();
        let pretty_length = serde_json::to_vec_pretty(&expanded).unwrap().len() + 1;
        assert!(compact.len() as u64 <= MAX_BOX_BYTES);
        assert!(pretty_length as u64 > MAX_BOX_BYTES);
        let expanded_put =
            handle_request(&root, "main", request(Method::PUT, "/api/zzz/box", compact));
        assert_eq!(expanded_put.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert!(!box_path.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_methods_bodies_routes_and_untrusted_webviews_without_path_leaks() {
        let root = root().join("CANARY_SECRET_PATH");
        fs::create_dir_all(&root).unwrap();
        for (method, uri, body, status) in [
            (
                Method::POST,
                "/hsr/index.html",
                Vec::new(),
                StatusCode::METHOD_NOT_ALLOWED,
            ),
            (
                Method::HEAD,
                "/api/hsr/box",
                Vec::new(),
                StatusCode::METHOD_NOT_ALLOWED,
            ),
            (
                Method::PUT,
                "/api/zzz/box",
                vec![b'x'; MAX_BOX_BYTES as usize + 1],
                StatusCode::PAYLOAD_TOO_LARGE,
            ),
            (
                Method::PUT,
                "/api/zzz/box",
                b"{".to_vec(),
                StatusCode::BAD_REQUEST,
            ),
            (
                Method::GET,
                "/api/nope/box",
                Vec::new(),
                StatusCode::NOT_FOUND,
            ),
            (
                Method::GET,
                "/hsr/nope.exe",
                Vec::new(),
                StatusCode::NOT_FOUND,
            ),
        ] {
            let response = handle_request(&root, "main", request(method, uri, body));
            assert_eq!(response.status(), status);
            assert!(!String::from_utf8_lossy(response.body()).contains("CANARY_SECRET_PATH"));
        }
        let forbidden = handle_request(
            &root,
            "other",
            request(Method::GET, "/hsr/index.html", Vec::new()),
        );
        assert_eq!(forbidden.status(), StatusCode::FORBIDDEN);
        fs::remove_dir_all(root.parent().unwrap()).unwrap();
    }

    #[test]
    fn rejects_encoded_double_encoded_and_backslash_traversal() {
        let root = root();
        for uri in [
            "/hsr/../index.html",
            "/hsr/%2e%2e/index.html",
            "/hsr/%252e%252e/index.html",
            "/hsr/%2Findex.html",
            "/hsr/%5c..%5cindex.html",
            "/hsr/%zz/index.html",
            "/hsr/assets/avatars/a%252ewebp",
            "/hsr/assets/avatars/evil.svg",
        ] {
            assert_ne!(
                handle_request(&root, "main", request(Method::GET, uri, Vec::new())).status(),
                StatusCode::OK,
                "{uri}"
            );
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn readiness_and_urls_never_expose_workspace_paths() {
        let base = root();
        let root = base.join("CANARY_SECRET_WORKSPACE");
        fs::create_dir_all(root.join("out/visualizer/assets/avatars")).unwrap();
        for name in ["index.html", "app.js", "solver.js", "styles.css", "data.json"] {
            let bytes = if name == "data.json" {
                b"{}".as_slice()
            } else {
                b"tampered executable".as_slice()
            };
            fs::write(root.join("out/visualizer").join(name), bytes).unwrap();
        }
        assert!(visualizer_is_ready(&root, "hsr"));
        let url = visualizer_url("hsr", TOKEN).unwrap();
        assert!(!url.contains("CANARY_SECRET_WORKSPACE"));
        assert!(url.contains("/hsr/index.html?workspace=workspace-test-session-0001"));
        assert!(visualizer_url("other", TOKEN).is_none());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn readiness_requires_every_referenced_workspace_avatar() {
        let root = root();
        fs::write(
            root.join("out/visualizer/data.json"),
            br#"{"icon_url":"./assets/avatars/missing.webp?alias=safe#fragment"}"#,
        )
        .unwrap();
        assert!(!visualizer_is_ready(&root, "hsr"));
        fs::write(
            root.join("out/visualizer/assets/avatars/missing.webp"),
            b"avatar",
        )
        .unwrap();
        assert!(visualizer_is_ready(&root, "hsr"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn oversized_data_and_avatars_are_rejected_before_reading() {
        let root = root();
        let data_path = root.join("out/visualizer/data.json");
        let data = fs::OpenOptions::new().write(true).open(&data_path).unwrap();
        data.set_len(MAX_VISUALIZER_DATA_BYTES + 1).unwrap();
        drop(data);
        assert!(!visualizer_is_ready(&root, "hsr"));
        assert_eq!(
            handle_request(
                &root,
                "main",
                request(Method::GET, "/hsr/data.json", Vec::new())
            )
            .status(),
            StatusCode::NOT_FOUND
        );

        fs::write(
            &data_path,
            br#"{"icon_url":"./assets/avatars/agent-one.webp"}"#,
        )
        .unwrap();
        let avatar_path = root.join("out/visualizer/assets/avatars/agent-one.webp");
        let avatar = fs::OpenOptions::new()
            .write(true)
            .open(&avatar_path)
            .unwrap();
        avatar.set_len(MAX_AVATAR_BYTES + 1).unwrap();
        drop(avatar);
        assert!(!visualizer_is_ready(&root, "hsr"));
        assert_eq!(
            handle_request(
                &root,
                "main",
                request(
                    Method::GET,
                    "/hsr/assets/avatars/agent-one.webp",
                    Vec::new()
                )
            )
            .status(),
            StatusCode::NOT_FOUND
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn stale_workspace_token_cannot_read_or_write_the_new_workspace() {
        let root_a = root();
        let root_b = root();
        let token_a = "workspace-session-a-0001";
        let token_b = "workspace-session-b-0001";
        let body =
            br#"{"version":2,"updatedAt":"a","owned":["agent-a"],"buildSlug":"","builds":{}}"#
                .to_vec();
        let write_a = handle_workspace_request(
            &root_a,
            token_a,
            STORAGE_SCOPE,
            "main",
            request(
                Method::PUT,
                &format!("/api/zzz/box?workspace={token_a}"),
                body.clone(),
            ),
        );
        assert_eq!(write_a.status(), StatusCode::OK);
        let path_a = root_a.join(".miho/zzz_box_state.json");
        let before_a = fs::read(&path_a).unwrap();
        let stale_put = handle_workspace_request(
            &root_b,
            token_b,
            STORAGE_SCOPE,
            "main",
            request(
                Method::PUT,
                &format!("/api/zzz/box?workspace={token_a}"),
                body,
            ),
        );
        assert_eq!(stale_put.status(), StatusCode::CONFLICT);
        assert_eq!(fs::read(&path_a).unwrap(), before_a);
        assert!(!root_b.join(".miho/zzz_box_state.json").exists());
        let stale_data = handle_workspace_request(
            &root_b,
            token_b,
            STORAGE_SCOPE,
            "main",
            request(
                Method::GET,
                &format!("/zzz/data.json?workspace={token_a}"),
                Vec::new(),
            ),
        );
        assert_eq!(stale_data.status(), StatusCode::CONFLICT);
        for (method, path) in [
            (Method::GET, "/hsr/index.html"),
            (Method::GET, "/hsr/app.js"),
            (Method::GET, "/hsr/solver.js"),
            (Method::GET, "/hsr/styles.css"),
            (Method::GET, "/hsr/assets/avatars/agent-one.webp"),
            (Method::GET, "/api/hsr/box"),
            (Method::OPTIONS, "/api/hsr/box"),
        ] {
            let stale = handle_workspace_request(
                &root_b,
                token_b,
                STORAGE_SCOPE,
                "main",
                request(method, &format!("{path}?workspace={token_a}"), Vec::new()),
            );
            assert_eq!(stale.status(), StatusCode::CONFLICT, "{path}");
        }
        fs::remove_dir_all(root_a).unwrap();
        fs::remove_dir_all(root_b).unwrap();
    }

    #[test]
    fn missing_duplicate_and_double_encoded_workspace_tokens_are_rejected() {
        let root = root();
        let missing = handle_workspace_request(
            &root,
            TOKEN,
            STORAGE_SCOPE,
            "main",
            request(Method::GET, "/hsr/data.json", Vec::new()),
        );
        assert_eq!(missing.status(), StatusCode::CONFLICT);
        let duplicate = handle_workspace_request(
            &root,
            TOKEN,
            STORAGE_SCOPE,
            "main",
            request(
                Method::GET,
                &format!("/hsr/data.json?workspace={TOKEN}&workspace={TOKEN}"),
                Vec::new(),
            ),
        );
        assert_eq!(duplicate.status(), StatusCode::BAD_REQUEST);
        let encoded = handle_workspace_request(
            &root,
            TOKEN,
            STORAGE_SCOPE,
            "main",
            request(
                Method::GET,
                "/hsr/data.json?workspace=workspace%252dtest%252dsession%252d0001",
                Vec::new(),
            ),
        );
        assert_eq!(encoded.status(), StatusCode::BAD_REQUEST);
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn rejects_reparse_point_visualizer_directory() {
        use std::os::windows::fs::symlink_dir;
        let root = root();
        let external = root.join("external");
        fs::create_dir_all(&external).unwrap();
        fs::write(external.join("index.html"), b"secret").unwrap();
        let visualizer = root.join("out/visualizer");
        fs::remove_dir_all(&visualizer).unwrap();
        if symlink_dir(&external, &visualizer).is_err() {
            fs::remove_dir_all(root).unwrap();
            return;
        }
        assert_eq!(
            handle_request(
                &root,
                "main",
                request(Method::GET, "/hsr/index.html", Vec::new())
            )
            .status(),
            StatusCode::NOT_FOUND
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinked_visualizer_files() {
        use std::os::unix::fs::symlink;
        let root = root();
        let target = root.join("secret.html");
        fs::write(&target, b"secret").unwrap();
        let index = root.join("out/visualizer/index.html");
        fs::remove_file(&index).unwrap();
        symlink(&target, &index).unwrap();
        assert_eq!(
            handle_request(
                &root,
                "main",
                request(Method::GET, "/hsr/index.html", Vec::new())
            )
            .status(),
            StatusCode::NOT_FOUND
        );
        fs::remove_dir_all(root).unwrap();
    }
}
