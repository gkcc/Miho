use std::{
    future::Future,
    path::{Path, PathBuf},
    pin::Pin,
};

use serde_json::Value;

use crate::{
    contract::DatasetRef,
    hf::{parse_tree_response, HuggingFaceRepo, TreeEntry},
    network::{CachedHttpClient, FetchMode, FetchSource, FetchedText, HttpClient},
    MihoError, Result,
};

pub type SourceFuture<'a, T> = Pin<Box<dyn Future<Output = Result<T>> + Send + 'a>>;

pub trait SnapshotSource: Send + Sync {
    fn list_tree<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Vec<TreeEntry>>;
    fn read_json<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Value>;
    fn raw_url(&self, path: &str) -> String;
    fn dataset_ref(&self) -> Option<DatasetRef> {
        None
    }
}

/// Controls whether an online Hugging Face source may silently use its
/// last-good cache after a request or payload-validation failure.
///
/// Direct and interactive exports retain [`Self::Allow`]. Freshness-sensitive
/// orchestration must opt into [`Self::Reject`], which turns every observed
/// online cache fallback into a structured error before cached bytes reach the
/// export pipeline.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum HfCacheFallbackPolicy {
    #[default]
    Allow,
    Reject,
}

#[derive(Clone)]
pub struct HfSnapshotSource {
    repo: HuggingFaceRepo,
    client: CachedHttpClient,
    mode: FetchMode,
    cache_fallback_policy: HfCacheFallbackPolicy,
}

impl HfSnapshotSource {
    pub fn new(
        repo: HuggingFaceRepo,
        http: HttpClient,
        cache_root: impl Into<PathBuf>,
        mode: FetchMode,
    ) -> Self {
        Self {
            repo,
            client: CachedHttpClient::new(http, cache_root),
            mode,
            cache_fallback_policy: HfCacheFallbackPolicy::Allow,
        }
    }

    pub fn with_cache_fallback_policy(mut self, policy: HfCacheFallbackPolicy) -> Self {
        self.cache_fallback_policy = policy;
        self
    }

    fn tree_cache_key(path: &str) -> PathBuf {
        let mut key = PathBuf::from(".trees");
        if path.trim_matches('/').is_empty() {
            key.push("root.json");
        } else {
            for part in path.trim_matches('/').split('/') {
                key.push(part);
            }
            key.push("tree.json");
        }
        key
    }

    fn raw_cache_key(path: &str) -> PathBuf {
        Path::new("hf").join(path.split('/').collect::<PathBuf>())
    }

    fn accept_fetched(&self, fetched: FetchedText, cache_key: &Path) -> Result<String> {
        if self.cache_fallback_policy == HfCacheFallbackPolicy::Reject
            && self.mode == FetchMode::Online
            && fetched.source == FetchSource::Cache
        {
            return Err(MihoError::CacheFallbackRejected(
                cache_key.display().to_string(),
            ));
        }
        Ok(fetched.text)
    }
}

impl SnapshotSource for HfSnapshotSource {
    fn list_tree<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Vec<TreeEntry>> {
        Box::pin(async move {
            let cache_key = Self::tree_cache_key(path);
            let fetched = self
                .client
                .get_text_validated_with_source(
                    &self.repo.tree_url(path, false),
                    &cache_key,
                    self.mode,
                    |text| {
                        parse_tree_response(text)
                            .map(|_| ())
                            .map_err(|source| MihoError::Json {
                                path: cache_key.clone(),
                                source,
                            })
                    },
                )
                .await?;
            let text = self.accept_fetched(fetched, &cache_key)?;
            parse_tree_response(&text).map_err(|source| MihoError::Json {
                path: cache_key,
                source,
            })
        })
    }

    fn read_json<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Value> {
        Box::pin(async move {
            let key = Self::raw_cache_key(path);
            let fetched = self
                .client
                .get_text_validated_with_source(&self.repo.raw_url(path), &key, self.mode, |text| {
                    serde_json::from_str::<Value>(text)
                        .map(|_| ())
                        .map_err(|source| MihoError::Json {
                            path: key.clone(),
                            source,
                        })
                })
                .await?;
            let text = self.accept_fetched(fetched, &key)?;
            serde_json::from_str(&text).map_err(|source| MihoError::Json { path: key, source })
        })
    }

    fn raw_url(&self, path: &str) -> String {
        self.repo.raw_url(path)
    }

    fn dataset_ref(&self) -> Option<DatasetRef> {
        Some(DatasetRef {
            repo_id: self.repo.repo_id.clone(),
            revision: self.repo.revision.clone(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        io::{Read, Write},
        net::TcpListener,
        thread,
        time::Duration,
    };

    fn temp_dir(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!("miho-source-{label}-{}", std::process::id()))
    }

    fn serve_responses(responses: Vec<(u16, &'static str)>) -> (String, thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let origin = format!("http://{}", listener.local_addr().unwrap());
        let server = thread::spawn(move || {
            for (status, body) in responses {
                let (mut stream, _) = listener.accept().unwrap();
                let mut request = [0_u8; 2048];
                let _ = stream.read(&mut request);
                let reason = if status == 200 { "OK" } else { "Error" };
                write!(
                    stream,
                    "HTTP/1.1 {status} {reason}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            }
        });
        (origin, server)
    }

    #[tokio::test]
    async fn offline_adapter_uses_the_same_tree_and_raw_contract() {
        let root = temp_dir("offline");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join(".trees")).unwrap();
        fs::create_dir_all(root.join("hf/1.2.3")).unwrap();
        fs::write(
            root.join(".trees/root.json"),
            r#"[{"type":"directory","path":"1.2.3"}]"#,
        )
        .unwrap();
        fs::write(root.join("hf/1.2.3/builds.json"), r#"[{"char":"A"}]"#).unwrap();
        let source = HfSnapshotSource::new(
            HuggingFaceRepo::new("owner/repo", "main").with_origin("http://127.0.0.1:1"),
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &root,
            FetchMode::Offline,
        );
        assert_eq!(source.list_tree("").await.unwrap()[0].path, "1.2.3");
        assert_eq!(
            source.read_json("1.2.3/builds.json").await.unwrap()[0]["char"],
            "A"
        );
        assert_eq!(
            source.raw_url("a b.json"),
            "http://127.0.0.1:1/datasets/owner/repo/resolve/main/a%20b.json"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn online_adapter_fetches_tree_and_raw_through_one_contract() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let origin = format!("http://{}", listener.local_addr().unwrap());
        let server = thread::spawn(move || {
            for body in [
                r#"[{"type":"directory","path":"2.0.0"}]"#,
                r#"{"collect_date":"2026-07-12"}"#,
            ] {
                let (mut stream, _) = listener.accept().unwrap();
                let mut request = [0_u8; 2048];
                let _ = stream.read(&mut request);
                write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            }
        });
        let root = temp_dir("online");
        let _ = fs::remove_dir_all(&root);
        let source = HfSnapshotSource::new(
            HuggingFaceRepo::new("owner/repo", "main").with_origin(origin),
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
        );
        assert_eq!(source.list_tree("").await.unwrap()[0].path, "2.0.0");
        assert_eq!(
            source.read_json("config.json").await.unwrap()["collect_date"],
            "2026-07-12"
        );
        server.join().unwrap();
        assert!(root.join(".trees/root.json").is_file());
        assert!(root.join("hf/config.json").is_file());
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn online_adapter_allows_last_good_cache_by_default() {
        let root = temp_dir("online-fallback-allowed");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join(".trees")).unwrap();
        fs::create_dir_all(root.join("hf")).unwrap();
        fs::write(
            root.join(".trees/root.json"),
            r#"[{"type":"directory","path":"cached"}]"#,
        )
        .unwrap();
        fs::write(
            root.join("hf/config.json"),
            r#"{"collect_date":"2026-07-12"}"#,
        )
        .unwrap();
        let (origin, server) = serve_responses(vec![(500, "failed"), (500, "failed")]);
        let source = HfSnapshotSource::new(
            HuggingFaceRepo::new("owner/repo", "main").with_origin(origin),
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
        );

        assert_eq!(source.list_tree("").await.unwrap()[0].path, "cached");
        assert_eq!(
            source.read_json("config.json").await.unwrap()["collect_date"],
            "2026-07-12"
        );

        server.join().unwrap();
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn freshness_policy_rejects_every_online_hf_cache_fallback() {
        let root = temp_dir("online-fallback-rejected");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join(".trees")).unwrap();
        fs::create_dir_all(root.join("hf")).unwrap();
        fs::write(
            root.join(".trees/root.json"),
            r#"[{"type":"directory","path":"cached"}]"#,
        )
        .unwrap();
        fs::write(
            root.join("hf/config.json"),
            r#"{"collect_date":"2026-07-12"}"#,
        )
        .unwrap();
        let (origin, server) = serve_responses(vec![(500, "failed"), (500, "failed")]);
        let source = HfSnapshotSource::new(
            HuggingFaceRepo::new("owner/repo", "main").with_origin(origin),
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
        )
        .with_cache_fallback_policy(HfCacheFallbackPolicy::Reject);

        assert!(matches!(
            source.list_tree("").await,
            Err(MihoError::CacheFallbackRejected(key)) if key == ".trees\\root.json" || key == ".trees/root.json"
        ));
        assert!(matches!(
            source.read_json("config.json").await,
            Err(MihoError::CacheFallbackRejected(key)) if key == "hf\\config.json" || key == "hf/config.json"
        ));

        server.join().unwrap();
        let unavailable = TcpListener::bind("127.0.0.1:0").unwrap();
        let unavailable_origin = format!("http://{}", unavailable.local_addr().unwrap());
        drop(unavailable);
        let unavailable_source = HfSnapshotSource::new(
            HuggingFaceRepo::new("owner/repo", "main").with_origin(unavailable_origin),
            HttpClient::new(Duration::from_millis(100), 0).unwrap(),
            &root,
            FetchMode::Online,
        )
        .with_cache_fallback_policy(HfCacheFallbackPolicy::Reject);
        assert!(matches!(
            unavailable_source.list_tree("").await,
            Err(MihoError::CacheFallbackRejected(key)) if key == ".trees\\root.json" || key == ".trees/root.json"
        ));
        let (invalid_origin, invalid_server) = serve_responses(vec![(200, "not-json")]);
        let invalid_source = HfSnapshotSource::new(
            HuggingFaceRepo::new("owner/repo", "main").with_origin(invalid_origin),
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
        )
        .with_cache_fallback_policy(HfCacheFallbackPolicy::Reject);
        assert!(matches!(
            invalid_source.read_json("config.json").await,
            Err(MihoError::CacheFallbackRejected(key)) if key == "hf\\config.json" || key == "hf/config.json"
        ));
        invalid_server.join().unwrap();
        assert_eq!(
            fs::read_to_string(root.join("hf/config.json")).unwrap(),
            r#"{"collect_date":"2026-07-12"}"#
        );
        let _ = fs::remove_dir_all(root);
    }
}
