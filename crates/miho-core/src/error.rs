use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum MihoError {
    #[error("cannot read {path}: {source}")]
    Read {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("cannot write {path}: {source}")]
    Write {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("invalid JSON in {path}: {source}")]
    Json {
        path: PathBuf,
        source: serde_json::Error,
    },
    #[error("invalid YAML in {path}: {source}")]
    Yaml {
        path: PathBuf,
        source: serde_yaml::Error,
    },
    #[error("network request failed: {0}")]
    Network(#[from] reqwest::Error),
    #[error("network request failed: {0}")]
    BrowserNetwork(String),
    #[error("offline cache miss for {0}")]
    CacheMiss(String),
    #[error(
        "online source freshness requires a network response; cache fallback was used for {0}"
    )]
    CacheFallbackRejected(String),
    #[error("invalid cache key: {0}")]
    InvalidCacheKey(String),
    #[error("invalid artifact path: {0}")]
    InvalidArtifactPath(String),
    #[error("CSV row has {actual} values but {expected} headers were declared")]
    CsvWidth { expected: usize, actual: usize },
    #[error("CSV encoding failed: {0}")]
    Csv(#[from] csv::Error),
    #[error("workbook generation failed: {0}")]
    Workbook(String),
    #[error("visualizer generation failed: {0}")]
    Visualizer(String),
    #[error("unsupported operation: {0}")]
    Unsupported(String),
}

pub type Result<T> = std::result::Result<T, MihoError>;
