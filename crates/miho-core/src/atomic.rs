use std::{fs, path::Path};

use crate::{MihoError, Result};

pub fn write(path: &Path, contents: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| MihoError::Write {
            path: parent.into(),
            source,
        })?;
    }
    let temp = path.with_extension("tmp");
    fs::write(&temp, contents).map_err(|source| MihoError::Write {
        path: temp.clone(),
        source,
    })?;
    if path.exists() {
        fs::remove_file(path).map_err(|source| MihoError::Write {
            path: path.into(),
            source,
        })?;
    }
    fs::rename(&temp, path).map_err(|source| MihoError::Write {
        path: path.into(),
        source,
    })
}
