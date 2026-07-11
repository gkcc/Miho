use std::{fs, path::Path};

use serde::{de::DeserializeOwned, Serialize};

use crate::{atomic, MihoError, Result};

pub fn load<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let text = fs::read_to_string(path).map_err(|source| MihoError::Read {
        path: path.into(),
        source,
    })?;
    match path
        .extension()
        .and_then(|v| v.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "yaml" | "yml" => serde_yaml::from_str(&text).map_err(|source| MihoError::Yaml {
            path: path.into(),
            source,
        }),
        _ => serde_json::from_str(&text).map_err(|source| MihoError::Json {
            path: path.into(),
            source,
        }),
    }
}

pub fn save_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let mut data = serde_json::to_vec_pretty(value).map_err(|source| MihoError::Json {
        path: path.into(),
        source,
    })?;
    data.push(b'\n');
    atomic::write(path, &data)
}
