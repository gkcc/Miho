use std::{
    collections::BTreeSet,
    fs::{self, OpenOptions},
    io::Write,
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use crate::{MihoError, Result};

pub fn write(path: &Path, contents: &[u8]) -> Result<()> {
    validate_output_path(path)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| MihoError::Write {
            path: parent.into(),
            source,
        })?;
    }
    validate_output_path(path)?;
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
        validate_output_path(path)?;
        replace(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

pub fn write_batch(outputs: &[(PathBuf, Vec<u8>)]) -> Result<()> {
    write_batch_inner(outputs, None)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum BatchMove {
    Backup,
    Install,
    Rollback,
}

fn write_batch_inner(
    outputs: &[(PathBuf, Vec<u8>)],
    fail_before_install: Option<usize>,
) -> Result<()> {
    write_batch_inner_with_rename(
        outputs,
        fail_before_install,
        |source, target, _operation| fs::rename(source, target),
    )
}

fn write_batch_inner_with_rename<R>(
    outputs: &[(PathBuf, Vec<u8>)],
    fail_before_install: Option<usize>,
    mut rename: R,
) -> Result<()>
where
    R: FnMut(&Path, &Path, BatchMove) -> std::io::Result<()>,
{
    let mut seen = BTreeSet::new();
    for (path, _) in outputs {
        let normalized = normalized_absolute(path)?;
        #[cfg(windows)]
        let normalized = PathBuf::from(normalized.to_string_lossy().to_lowercase());
        if !seen.insert(normalized) {
            return Err(MihoError::Unsupported(format!(
                "batch output paths collide: {}",
                path.display()
            )));
        }
        validate_output_path(path)?;
    }

    let mut staged = Vec::with_capacity(outputs.len());
    let mut backups = Vec::new();
    let mut installed = Vec::new();
    let result = (|| {
        for (path, contents) in outputs {
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).map_err(|source| MihoError::Write {
                    path: parent.into(),
                    source,
                })?;
            }
            validate_output_path(path)?;
            let stage = unique_sibling(path, "stage");
            staged.push((path.clone(), stage.clone()));
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&stage)
                .map_err(|source| MihoError::Write {
                    path: stage.clone(),
                    source,
                })?;
            file.write_all(contents)
                .and_then(|_| file.sync_all())
                .map_err(|source| MihoError::Write {
                    path: stage.clone(),
                    source,
                })?;
        }

        for (index, (path, stage)) in staged.iter().enumerate() {
            if fail_before_install == Some(index) {
                return Err(MihoError::Unsupported(format!(
                    "injected batch install failure at {}",
                    path.display()
                )));
            }
            validate_output_path(path)?;
            if path.exists() {
                let backup = unique_sibling(path, "backup");
                install_new_with(path, &backup, |source, target| {
                    rename(source, target, BatchMove::Backup)
                })
                .map_err(|source| MihoError::Write {
                    path: path.clone(),
                    source,
                })?;
                backups.push((path.clone(), backup));
            }
            install_new_with(stage, path, |source, target| {
                rename(source, target, BatchMove::Install)
            })
            .map_err(|source| MihoError::Write {
                path: path.clone(),
                source,
            })?;
            installed.push(path.clone());
        }
        Ok(())
    })();

    if let Err(error) = result {
        for path in installed.iter().rev() {
            let _ = fs::remove_file(path);
        }
        let mut rollback_failures = Vec::new();
        for (path, backup) in &backups {
            if backup.exists() {
                if let Err(source) = install_new_with(backup, path, |source, target| {
                    rename(source, target, BatchMove::Rollback)
                }) {
                    rollback_failures.push(format!(
                        "{} -> {}: {source}",
                        backup.display(),
                        path.display()
                    ));
                }
            }
        }
        for (_, stage) in &staged {
            let _ = fs::remove_file(stage);
        }
        if rollback_failures.is_empty() {
            return Err(error);
        }
        return Err(MihoError::Unsupported(format!(
            "batch install failed ({error}); rollback incomplete: {}",
            rollback_failures.join("; ")
        )));
    }

    for (_, backup) in &backups {
        let _ = fs::remove_file(backup);
    }
    for (_, stage) in &staged {
        let _ = fs::remove_file(stage);
    }
    Ok(())
}

pub(crate) fn read_to_string(path: &Path) -> Result<String> {
    validate_regular_file(path)?;
    fs::read_to_string(path).map_err(|source| MihoError::Read {
        path: path.to_path_buf(),
        source,
    })
}

pub(crate) fn is_safe_regular_file(path: &Path) -> Result<bool> {
    reject_reparse_ancestors(path)?;
    match fs::symlink_metadata(path) {
        Ok(metadata) if is_symlink_or_reparse(&metadata) || !metadata.is_file() => {
            Err(unsafe_path("file target", path))
        }
        Ok(_) => Ok(true),
        Err(source) if source.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(source) => Err(MihoError::Read {
            path: path.to_path_buf(),
            source,
        }),
    }
}

fn validate_output_path(path: &Path) -> Result<()> {
    if path.file_name().is_none() {
        return Err(MihoError::Unsupported(format!(
            "atomic output path has no file name: {}",
            path.display()
        )));
    }
    reject_reparse_ancestors(path)?;
    match fs::symlink_metadata(path) {
        Ok(metadata) if is_symlink_or_reparse(&metadata) || !metadata.is_file() => {
            Err(unsafe_path("output target", path))
        }
        Ok(_) => Ok(()),
        Err(source) if source.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(source) => Err(MihoError::Read {
            path: path.to_path_buf(),
            source,
        }),
    }
}

fn validate_regular_file(path: &Path) -> Result<()> {
    reject_reparse_ancestors(path)?;
    match fs::symlink_metadata(path) {
        Ok(metadata) if is_symlink_or_reparse(&metadata) || !metadata.is_file() => {
            Err(unsafe_path("file target", path))
        }
        Ok(_) => Ok(()),
        Err(source) => Err(MihoError::Read {
            path: path.to_path_buf(),
            source,
        }),
    }
}

fn reject_reparse_ancestors(path: &Path) -> Result<()> {
    let absolute = normalized_absolute(path)?;
    let mut ancestor = absolute.parent();
    while let Some(candidate) = ancestor {
        match fs::symlink_metadata(candidate) {
            Ok(metadata) if is_symlink_or_reparse(&metadata) => {
                return Err(unsafe_path("parent", candidate));
            }
            Ok(_) => {}
            Err(source) if source.kind() == std::io::ErrorKind::NotFound => {}
            Err(source) => {
                return Err(MihoError::Read {
                    path: candidate.to_path_buf(),
                    source,
                });
            }
        }
        ancestor = candidate.parent();
    }
    Ok(())
}

fn unsafe_path(kind: &str, path: &Path) -> MihoError {
    MihoError::Unsupported(format!(
        "atomic {kind} is a symlink or reparse point: {}",
        path.display()
    ))
}

fn is_symlink_or_reparse(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
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

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

fn unique_sibling(path: &Path, kind: &str) -> PathBuf {
    let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let name = path.file_name().and_then(|v| v.to_str()).unwrap_or("miho");
    path.with_file_name(format!(".{name}.{kind}.{}.{id}", std::process::id()))
}

fn normalized_absolute(path: &Path) -> Result<PathBuf> {
    let source = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|source| MihoError::Read {
                path: PathBuf::from("."),
                source,
            })?
            .join(path)
    };
    let mut normalized = PathBuf::new();
    for component in source.components() {
        match component {
            Component::Prefix(_) | Component::RootDir | Component::Normal(_) => {
                normalized.push(component.as_os_str());
            }
            Component::CurDir => {}
            Component::ParentDir => {
                if !normalized.pop() {
                    return Err(MihoError::Unsupported(format!(
                        "batch output path escapes its root: {}",
                        path.display()
                    )));
                }
            }
        }
    }
    Ok(normalized)
}

fn replace(temp: &Path, target: &Path) -> Result<()> {
    if !target.exists() {
        return install_new(temp, target).map_err(|source| MihoError::Write {
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
        install_new(target, &backup).map_err(|source| MihoError::Write {
            path: target.into(),
            source,
        })?;
        match install_new(temp, target) {
            Ok(()) => {
                let _ = fs::remove_file(backup);
                Ok(())
            }
            Err(source) => {
                if let Err(rollback) = install_new(&backup, target) {
                    return Err(MihoError::Unsupported(format!(
                        "atomic replace failed ({source}); rollback failed ({rollback})"
                    )));
                }
                Err(MihoError::Write {
                    path: target.into(),
                    source,
                })
            }
        }
    }
}

fn install_new(temp: &Path, target: &Path) -> std::io::Result<()> {
    install_new_with(temp, target, |source, target| fs::rename(source, target))
}

fn install_new_with<R>(temp: &Path, target: &Path, mut rename: R) -> std::io::Result<()>
where
    R: FnMut(&Path, &Path) -> std::io::Result<()>,
{
    match rename(temp, target) {
        Ok(()) => Ok(()),
        Err(source) if source.kind() == std::io::ErrorKind::CrossesDevices => {
            copy_new_synced(temp, target)
        }
        Err(source) => Err(source),
    }
}

fn copy_new_synced(temp: &Path, target: &Path) -> std::io::Result<()> {
    let mut source = fs::File::open(temp)?;
    let mut target_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)?;
    let result = std::io::copy(&mut source, &mut target_file).and_then(|_| target_file.sync_all());
    drop(target_file);
    if let Err(error) = result {
        let _ = fs::remove_file(target);
        return Err(error);
    }
    if let Err(error) = fs::remove_file(temp) {
        let _ = fs::remove_file(target);
        return Err(error);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(windows)]
    fn create_junction(target: &Path, junction: &Path) {
        let output = std::process::Command::new("cmd.exe")
            .args(["/d", "/c", "mklink", "/J"])
            .arg(junction)
            .arg(target)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "failed to create junction: stdout={} stderr={}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }

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
    fn cross_device_copy_fallback_installs_synced_bytes_and_removes_stage() {
        let root = test_path("cross-device-copy");
        fs::create_dir_all(&root).unwrap();
        let temp = root.join("stage");
        let target = root.join("target");
        fs::write(&temp, b"settings").unwrap();
        copy_new_synced(&temp, &target).unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"settings");
        assert!(!temp.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn cross_device_copy_fallback_can_backup_and_replace_existing_bytes() {
        let root = test_path("cross-device-replace");
        fs::create_dir_all(&root).unwrap();
        let target = root.join("target");
        let backup = root.join("backup");
        let temp = root.join("temp");
        fs::write(&target, b"old-settings").unwrap();
        fs::write(&temp, b"new-settings").unwrap();

        copy_new_synced(&target, &backup).unwrap();
        copy_new_synced(&temp, &target).unwrap();

        assert_eq!(fs::read(&target).unwrap(), b"new-settings");
        assert_eq!(fs::read(&backup).unwrap(), b"old-settings");
        assert!(!temp.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn concurrent_temporary_paths_are_unique() {
        let path = test_path("concurrent");
        let threads = (0..8)
            .map(|_| {
                let path = path.clone();
                std::thread::spawn(move || unique_sibling(&path, "tmp"))
            })
            .collect::<Vec<_>>();
        let paths = threads
            .into_iter()
            .map(|thread| thread.join().unwrap())
            .collect::<BTreeSet<_>>();
        assert_eq!(paths.len(), 8);
        assert!(paths.iter().all(|temp| temp.parent() == path.parent()));
    }

    #[test]
    fn batch_rejects_collisions_before_mutation() {
        let root = test_path("batch-collision");
        fs::create_dir_all(&root).unwrap();
        let path = root.join("same.md");
        fs::write(&path, b"old").unwrap();
        let error = write_batch(&[
            (path.clone(), b"first".to_vec()),
            (path.clone(), b"second".to_vec()),
        ])
        .unwrap_err();
        assert!(error.to_string().contains("collide"));
        assert_eq!(fs::read(&path).unwrap(), b"old");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn batch_rolls_back_all_targets_when_later_install_fails() {
        let root = test_path("batch-rollback");
        fs::create_dir_all(&root).unwrap();
        let first = root.join("first.md");
        let second = root.join("second.md");
        fs::write(&first, b"old-first").unwrap();
        fs::write(&second, b"old-second").unwrap();
        let outputs = [
            (first.clone(), b"new-first".to_vec()),
            (second.clone(), b"new-second".to_vec()),
        ];
        assert!(write_batch_inner(&outputs, Some(1)).is_err());
        assert_eq!(fs::read(&first).unwrap(), b"old-first");
        assert_eq!(fs::read(&second).unwrap(), b"old-second");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 2);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn batch_cross_device_fallback_covers_backup_install_and_rollback() {
        let root = test_path("batch-cross-device-rollback");
        fs::create_dir_all(&root).unwrap();
        let first = root.join("first.md");
        let second = root.join("second.md");
        fs::write(&first, b"old-first").unwrap();
        fs::write(&second, b"old-second").unwrap();
        let outputs = [
            (first.clone(), b"new-first".to_vec()),
            (second.clone(), b"new-second".to_vec()),
        ];
        let mut moves = Vec::new();

        let error =
            write_batch_inner_with_rename(&outputs, Some(1), |_source, _target, operation| {
                moves.push(operation);
                Err(std::io::Error::from(std::io::ErrorKind::CrossesDevices))
            })
            .unwrap_err();

        assert!(error.to_string().contains("injected batch install failure"));
        assert_eq!(
            moves,
            vec![BatchMove::Backup, BatchMove::Install, BatchMove::Rollback]
        );
        assert_eq!(fs::read(&first).unwrap(), b"old-first");
        assert_eq!(fs::read(&second).unwrap(), b"old-second");
        assert_eq!(fs::read_dir(&root).unwrap().count(), 2);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn batch_rejects_aliasing_symlink_parents_before_mutation() {
        let root = test_path("batch-parent-link");
        let real = root.join("real");
        let alias = root.join("alias");
        fs::create_dir_all(&real).unwrap();
        #[cfg(windows)]
        if std::os::windows::fs::symlink_dir(&real, &alias).is_err() {
            fs::remove_dir_all(root).unwrap();
            return;
        }
        #[cfg(unix)]
        std::os::unix::fs::symlink(&real, &alias).unwrap();
        let real_output = real.join("same.md");
        let alias_output = alias.join("same.md");
        let error = write_batch(&[
            (real_output.clone(), b"current".to_vec()),
            (alias_output, b"target".to_vec()),
        ])
        .unwrap_err();
        assert!(error.to_string().contains("symlink or reparse"));
        assert!(!real_output.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn write_rejects_junction_parent_before_creating_or_changing_external_files() {
        let root = test_path("write-junction-root");
        let external = test_path("write-junction-external");
        fs::create_dir_all(root.join(".miho")).unwrap();
        fs::create_dir_all(&external).unwrap();
        let canary = external.join("CANARY.txt");
        fs::write(&canary, b"must remain unchanged").unwrap();
        let junction = root.join(".miho").join("update-attempts");
        create_junction(&external, &junction);

        let target = junction.join("attempt.json");
        let error = write(&target, b"escaped").unwrap_err();

        assert!(error.to_string().contains("symlink or reparse point"));
        assert_eq!(fs::read(&canary).unwrap(), b"must remain unchanged");
        assert_eq!(
            fs::read_dir(&external)
                .unwrap()
                .map(|entry| entry.unwrap().file_name())
                .collect::<Vec<_>>(),
            vec![std::ffi::OsString::from("CANARY.txt")]
        );

        fs::remove_dir(&junction).unwrap();
        fs::remove_dir_all(root).unwrap();
        fs::remove_dir_all(external).unwrap();
    }
}
