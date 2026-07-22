use std::{
    fs::{self, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    sync::Mutex,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use miho_app::{CancelOutcomeV1, PublicTaskSnapshotV1, TaskOperationV1, TaskStatusV1};
use serde::Serialize;

use crate::workspace::{ensure_safe_directory_chain, validate_existing_file_chain};

const LOG_DIRECTORY_NAME_V1: &str = "logs";
const LOG_FILE_PREFIX_V1: &str = "miho-desktop";
pub(crate) const MAX_LOG_FILES_V1: usize = 5;
pub(crate) const MAX_LOG_BYTES_V1: u64 = 2 * 1024 * 1024;

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "lowercase")]
enum SafeLogLevelV1 {
    Info,
    Warn,
    Error,
}

#[derive(Debug, Clone, Copy, Serialize)]
enum SafeLogEventV1 {
    #[serde(rename = "desktop.started")]
    DesktopStarted,
    #[serde(rename = "task.started")]
    TaskStarted,
    #[serde(rename = "task.status")]
    TaskStatus,
    #[serde(rename = "task.cancel")]
    TaskCancel,
    #[serde(rename = "log.location_opened")]
    LogLocationOpened,
}

/// Deliberately small, write-only diagnostic schema. There is no generic
/// message/context/map field: callers cannot accidentally persist intents,
/// paths, URLs, tokens, or upstream payloads.
#[derive(Debug, Serialize)]
struct SafeLogRecordV1 {
    timestamp_unix_ms: u64,
    level: SafeLogLevelV1,
    event: SafeLogEventV1,
    #[serde(skip_serializing_if = "Option::is_none")]
    code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stage: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    task_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    operation: Option<TaskOperationV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    status: Option<TaskStatusV1>,
    #[serde(skip_serializing_if = "Option::is_none")]
    retryable: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    elapsed_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    cancel_outcome: Option<CancelOutcomeV1>,
}

impl SafeLogRecordV1 {
    fn event(level: SafeLogLevelV1, event: SafeLogEventV1) -> Self {
        Self {
            timestamp_unix_ms: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis()
                .try_into()
                .unwrap_or(u64::MAX),
            level,
            event,
            code: None,
            stage: None,
            task_id: None,
            operation: None,
            status: None,
            retryable: None,
            elapsed_ms: None,
            cancel_outcome: None,
        }
    }
}

#[derive(Debug)]
struct SafeLogWriterV1 {
    maximum_bytes: u64,
    maximum_files: usize,
}

/// Managed Tauri state for bounded, redacted local diagnostics.
pub(crate) struct SafeLogV1 {
    directory: PathBuf,
    writer: Mutex<SafeLogWriterV1>,
}

impl SafeLogV1 {
    /// The caller supplies Tauri's app-local data root; the log directory name
    /// itself is fixed here and is never accepted from the WebView.
    pub(crate) fn initialize_app_local(app_local_data: PathBuf) -> io::Result<Self> {
        ensure_safe_directory_chain(&app_local_data).map_err(unsafe_log_location)?;
        let directory = app_local_data.join(LOG_DIRECTORY_NAME_V1);
        Self::initialize_directory(directory, MAX_LOG_BYTES_V1, MAX_LOG_FILES_V1)
    }

    fn initialize_directory(
        directory: PathBuf,
        maximum_bytes: u64,
        maximum_files: usize,
    ) -> io::Result<Self> {
        if maximum_bytes == 0 || maximum_files == 0 || maximum_files > MAX_LOG_FILES_V1 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "invalid safe log retention limits",
            ));
        }
        ensure_safe_directory_chain(&directory).map_err(unsafe_log_location)?;
        let log = Self {
            directory,
            writer: Mutex::new(SafeLogWriterV1 {
                maximum_bytes,
                maximum_files,
            }),
        };
        {
            let writer = log.lock_writer()?;
            log.validate_and_prune_oversized(&writer)?;
        }
        Ok(log)
    }

    pub(crate) fn record_desktop_started(&self) -> io::Result<()> {
        self.append(SafeLogRecordV1::event(
            SafeLogLevelV1::Info,
            SafeLogEventV1::DesktopStarted,
        ))
    }

    pub(crate) fn record_task_started(&self, snapshot: &PublicTaskSnapshotV1) -> io::Result<()> {
        let mut record = SafeLogRecordV1::event(SafeLogLevelV1::Info, SafeLogEventV1::TaskStarted);
        record.task_id = safe_task_id(&snapshot.task_id);
        record.operation = Some(snapshot.operation);
        record.status = Some(snapshot.status);
        record.elapsed_ms = Some(0);
        self.append(record)
    }

    pub(crate) fn record_task_status(
        &self,
        snapshot: &PublicTaskSnapshotV1,
        elapsed: Duration,
    ) -> io::Result<()> {
        let level = match snapshot.status {
            TaskStatusV1::Failed => SafeLogLevelV1::Error,
            TaskStatusV1::Cancelled | TaskStatusV1::Cancelling => SafeLogLevelV1::Warn,
            _ => SafeLogLevelV1::Info,
        };
        let mut record = SafeLogRecordV1::event(level, SafeLogEventV1::TaskStatus);
        record.task_id = safe_task_id(&snapshot.task_id);
        record.operation = Some(snapshot.operation);
        record.status = Some(snapshot.status);
        record.elapsed_ms = Some(elapsed.as_millis().try_into().unwrap_or(u64::MAX));
        if let Some(failure) = snapshot.failure.as_ref() {
            record.code = safe_machine_value(&failure.code, 96);
            record.stage = safe_machine_value(&failure.stage, 64);
            record.retryable = Some(failure.retryable);
        }
        self.append(record)
    }

    pub(crate) fn record_task_cancel(
        &self,
        task_id: &str,
        outcome: CancelOutcomeV1,
        status: Option<TaskStatusV1>,
    ) -> io::Result<()> {
        let mut record = SafeLogRecordV1::event(
            if matches!(outcome, CancelOutcomeV1::Requested) {
                SafeLogLevelV1::Warn
            } else {
                SafeLogLevelV1::Info
            },
            SafeLogEventV1::TaskCancel,
        );
        record.task_id = safe_task_id(task_id);
        record.status = status;
        record.cancel_outcome = Some(outcome);
        self.append(record)
    }

    pub(crate) fn record_log_location_opened(&self) -> io::Result<()> {
        self.append(SafeLogRecordV1::event(
            SafeLogLevelV1::Info,
            SafeLogEventV1::LogLocationOpened,
        ))
    }

    /// Revalidates the complete chain immediately before the native opener is
    /// invoked. No path supplied by a WebView participates in this operation.
    pub(crate) fn trusted_directory(&self) -> io::Result<PathBuf> {
        validate_safe_directory(&self.directory)?;
        Ok(self.directory.clone())
    }

    fn append(&self, record: SafeLogRecordV1) -> io::Result<()> {
        let mut line = serde_json::to_vec(&record)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        line.push(b'\n');
        let writer = self.lock_writer()?;
        if line.len() as u64 > writer.maximum_bytes {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "safe log record exceeds the bounded file size",
            ));
        }
        validate_safe_directory(&self.directory)?;
        self.validate_and_prune_oversized(&writer)?;
        let current = self.log_path(0);
        let current_bytes = existing_safe_file_len(&current)?;
        if current_bytes.saturating_add(line.len() as u64) > writer.maximum_bytes {
            self.rotate(&writer)?;
        }
        validate_safe_directory(&self.directory)?;
        validate_missing_or_safe_file(&current)?;
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&current)?;
        validate_existing_file_chain(&current).map_err(unsafe_log_location)?;
        if !file.metadata()?.is_file() {
            return Err(unsafe_log_location(()));
        }
        file.write_all(&line)?;
        file.flush()?;
        if file.metadata()?.len() > writer.maximum_bytes {
            return Err(io::Error::other("safe log size boundary was not preserved"));
        }
        Ok(())
    }

    fn validate_and_prune_oversized(&self, writer: &SafeLogWriterV1) -> io::Result<()> {
        validate_safe_directory(&self.directory)?;
        for index in 0..writer.maximum_files {
            let path = self.log_path(index);
            let Some(length) = optional_safe_file_len(&path)? else {
                continue;
            };
            if length > writer.maximum_bytes {
                fs::remove_file(&path)?;
            }
        }
        Ok(())
    }

    fn rotate(&self, writer: &SafeLogWriterV1) -> io::Result<()> {
        validate_safe_directory(&self.directory)?;
        for destination_index in (1..writer.maximum_files).rev() {
            let source = self.log_path(destination_index - 1);
            let destination = self.log_path(destination_index);
            if optional_safe_file_len(&destination)?.is_some() {
                fs::remove_file(&destination)?;
            }
            if optional_safe_file_len(&source)?.is_some() {
                fs::rename(&source, &destination)?;
                validate_existing_file_chain(&destination).map_err(unsafe_log_location)?;
            }
        }
        if writer.maximum_files == 1 {
            let current = self.log_path(0);
            if optional_safe_file_len(&current)?.is_some() {
                fs::remove_file(current)?;
            }
        }
        Ok(())
    }

    fn log_path(&self, index: usize) -> PathBuf {
        self.directory
            .join(format!("{LOG_FILE_PREFIX_V1}.{index}.jsonl"))
    }

    fn lock_writer(&self) -> io::Result<std::sync::MutexGuard<'_, SafeLogWriterV1>> {
        self.writer
            .lock()
            .map_err(|_| io::Error::other("safe log state is unavailable"))
    }

    #[cfg(test)]
    fn initialize_for_test(
        app_local_data: PathBuf,
        maximum_bytes: u64,
        maximum_files: usize,
    ) -> io::Result<Self> {
        ensure_safe_directory_chain(&app_local_data).map_err(unsafe_log_location)?;
        Self::initialize_directory(
            app_local_data.join(LOG_DIRECTORY_NAME_V1),
            maximum_bytes,
            maximum_files,
        )
    }
}

fn safe_task_id(value: &str) -> Option<String> {
    (value.starts_with("task-")
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-'))
    .then(|| value.to_owned())
}

fn safe_machine_value(value: &str, maximum_length: usize) -> Option<String> {
    (!value.is_empty()
        && value.len() <= maximum_length
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        }))
    .then(|| value.to_owned())
}

fn validate_safe_directory(path: &Path) -> io::Result<()> {
    if !path.is_absolute()
        || path.components().any(|component| {
            !matches!(
                component,
                std::path::Component::Prefix(_)
                    | std::path::Component::RootDir
                    | std::path::Component::Normal(_)
            )
        })
    {
        return Err(unsafe_log_location(()));
    }
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(unsafe_log_location(()));
    }
    ensure_safe_directory_chain(path).map_err(unsafe_log_location)
}

fn validate_missing_or_safe_file(path: &Path) -> io::Result<()> {
    match fs::symlink_metadata(path) {
        Ok(_) => validate_existing_file_chain(path).map_err(unsafe_log_location),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

fn optional_safe_file_len(path: &Path) -> io::Result<Option<u64>> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            validate_existing_file_chain(path).map_err(unsafe_log_location)?;
            if !metadata.is_file() || metadata.file_type().is_symlink() {
                return Err(unsafe_log_location(()));
            }
            Ok(Some(metadata.len()))
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error),
    }
}

fn existing_safe_file_len(path: &Path) -> io::Result<u64> {
    optional_safe_file_len(path).map(|length| length.unwrap_or(0))
}

fn unsafe_log_location<T>(_ignored: T) -> io::Error {
    io::Error::new(
        io::ErrorKind::PermissionDenied,
        "safe log location is unavailable or untrusted",
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use miho_app::{PublicArtifactV1, PublicTaskFailureV1, PUBLIC_TASK_SNAPSHOT_SCHEMA_V1};
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_ID: AtomicU64 = AtomicU64::new(0);

    fn temp_root(label: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "miho-safe-log-{label}-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        root
    }

    fn task_snapshot(task_id: String) -> PublicTaskSnapshotV1 {
        PublicTaskSnapshotV1 {
            schema_version: PUBLIC_TASK_SNAPSHOT_SCHEMA_V1.to_owned(),
            task_id,
            operation: TaskOperationV1::Decision,
            status: TaskStatusV1::Failed,
            status_history: vec![TaskStatusV1::Queued, TaskStatusV1::Failed],
            cancellation_requested: false,
            artifacts: Vec::new(),
            failure: None,
            freshness: None,
        }
    }

    #[test]
    fn log_schema_drops_canaries_paths_tokens_and_unlisted_payload_fields() {
        let root = temp_root("redaction");
        let logger = SafeLogV1::initialize_app_local(root.clone()).unwrap();
        let canary = "CANARY-DO-NOT-PERSIST";
        let secret_path = r"C:\\Users\\person\\private-workspace";
        let token = "token=super-secret-value";
        let mut snapshot = task_snapshot(format!("task-{canary}-{secret_path}?{token}"));
        snapshot.failure = Some(PublicTaskFailureV1 {
            code: format!("failure.{canary}.{token}"),
            stage: secret_path.to_owned(),
            retryable: true,
            message: format!("{canary} {secret_path} {token}"),
            action: format!("open https://example.invalid/?{token}"),
        });
        snapshot.artifacts.push(PublicArtifactV1 {
            artifact_id: format!("{canary}:{token}"),
            name: secret_path.to_owned(),
            kind: "json".to_owned(),
        });

        logger
            .record_task_status(&snapshot, Duration::from_millis(17))
            .unwrap();
        let bytes = fs::read(logger.log_path(0)).unwrap();
        let text = String::from_utf8(bytes).unwrap();
        assert!(!text.contains(canary));
        assert!(!text.contains(secret_path));
        assert!(!text.contains(token));
        let value: serde_json::Value = serde_json::from_str(text.trim()).unwrap();
        let keys = value
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect::<Vec<_>>();
        assert_eq!(
            keys,
            vec![
                "timestamp_unix_ms",
                "level",
                "event",
                "operation",
                "status",
                "retryable",
                "elapsed_ms",
            ]
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rotation_never_exceeds_five_files_or_each_configured_file_limit() {
        let root = temp_root("rotation");
        let maximum_bytes = 320;
        let logger =
            SafeLogV1::initialize_for_test(root.clone(), maximum_bytes, MAX_LOG_FILES_V1).unwrap();
        for index in 0..80 {
            let snapshot = task_snapshot(format!("task-123-{index:016}"));
            logger
                .record_task_status(&snapshot, Duration::from_millis(index))
                .unwrap();
        }
        let files = fs::read_dir(logger.trusted_directory().unwrap())
            .unwrap()
            .map(|entry| entry.unwrap())
            .filter(|entry| entry.file_name().to_string_lossy().ends_with(".jsonl"))
            .collect::<Vec<_>>();
        assert_eq!(files.len(), MAX_LOG_FILES_V1);
        assert!(files
            .iter()
            .all(|entry| entry.metadata().unwrap().len() <= maximum_bytes));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn app_local_directory_is_fixed_and_unsafe_chains_are_rejected() {
        let root = temp_root("directory");
        let logger = SafeLogV1::initialize_app_local(root.clone()).unwrap();
        assert_eq!(logger.trusted_directory().unwrap(), root.join("logs"));
        assert!(SafeLogV1::initialize_app_local(PathBuf::from("relative-app-data")).is_err());

        fs::remove_dir_all(root.join("logs")).unwrap();
        fs::write(root.join("logs"), b"not a directory").unwrap();
        assert!(logger.trusted_directory().is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn symlinked_log_directory_is_rejected() {
        use std::os::unix::fs::symlink;

        let root = temp_root("symlink");
        let outside = temp_root("symlink-outside");
        symlink(&outside, root.join("logs")).unwrap();
        assert!(SafeLogV1::initialize_app_local(root.clone()).is_err());
        fs::remove_file(root.join("logs")).unwrap();
        fs::remove_dir_all(root).unwrap();
        fs::remove_dir_all(outside).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn linked_log_directory_is_rejected() {
        use std::os::windows::fs::symlink_dir;

        let root = temp_root("link");
        let outside = temp_root("link-outside");
        if symlink_dir(&outside, root.join("logs")).is_err() {
            fs::remove_dir_all(root).unwrap();
            fs::remove_dir_all(outside).unwrap();
            return;
        }
        assert!(SafeLogV1::initialize_app_local(root.clone()).is_err());
        fs::remove_dir(root.join("logs")).unwrap();
        fs::remove_dir_all(root).unwrap();
        fs::remove_dir_all(outside).unwrap();
    }
}
