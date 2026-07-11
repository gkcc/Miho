use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use crate::{MihoError, Result};

pub fn write(path: &Path, contents: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| MihoError::Write {
            path: parent.into(),
            source,
        })?;
    }
    let temp = unique_sibling(path, "tmp");
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|source| MihoError::Write {
                path: temp.clone(),
                source,
            })?;
        file.write_all(contents)
            .and_then(|_| file.sync_all())
            .map_err(|source| MihoError::Write {
                path: temp.clone(),
                source,
            })?;
        replace(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

fn unique_sibling(path: &Path, kind: &str) -> PathBuf {
    let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let name = path.file_name().and_then(|v| v.to_str()).unwrap_or("miho");
    path.with_file_name(format!(".{name}.{kind}.{}.{id}", std::process::id()))
}

fn replace(temp: &Path, target: &Path) -> Result<()> {
    if !target.exists() {
        return fs::rename(temp, target).map_err(|source| MihoError::Write {
            path: target.into(),
            source,
        });
    }

    #[cfg(not(windows))]
    return fs::rename(temp, target).map_err(|source| MihoError::Write {
        path: target.into(),
        source,
    });

    #[cfg(windows)]
    {
        // std::fs::rename cannot replace an existing file on Windows. Keep the
        // old file as a uniquely named sibling so a failed install can restore it.
        let backup = unique_sibling(target, "bak");
        fs::rename(target, &backup).map_err(|source| MihoError::Write {
            path: target.into(),
            source,
        })?;
        match fs::rename(temp, target) {
            Ok(()) => {
                let _ = fs::remove_file(backup);
                Ok(())
            }
            Err(source) => {
                let _ = fs::rename(&backup, target);
                Err(MihoError::Write {
                    path: target.into(),
                    source,
                })
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_path(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "miho-atomic-{label}-{}-{}",
            std::process::id(),
            NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed)
        ))
    }

    #[test]
    fn replaces_existing_contents() {
        let path = test_path("replace");
        fs::write(&path, b"old").unwrap();
        write(&path, b"new").unwrap();
        assert_eq!(fs::read(&path).unwrap(), b"new");
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn concurrent_writes_do_not_share_temporary_files() {
        let path = test_path("concurrent");
        let threads = (0..8)
            .map(|value| {
                let path = path.clone();
                std::thread::spawn(move || write(&path, value.to_string().as_bytes()))
            })
            .collect::<Vec<_>>();
        for thread in threads {
            thread.join().unwrap().unwrap();
        }
        assert!(fs::read_to_string(&path).unwrap().parse::<u8>().is_ok());
        fs::remove_file(path).unwrap();
    }
}
