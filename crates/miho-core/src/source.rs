use std::{
    future::Future,
    path::{Path, PathBuf},
    pin::Pin,
};

use serde_json::Value;

use crate::{
    contract::DatasetRef,
    hf::{parse_tree_response, HuggingFaceRepo, TreeEntry},
    network::{CachedHttpClient, FetchMode, HttpClient},
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

#[derive(Clone)]
pub struct HfSnapshotSource {
    repo: HuggingFaceRepo,
    client: CachedHttpClient,
    mode: FetchMode,
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
        }
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
}

impl SnapshotSource for HfSnapshotSource {
    fn list_tree<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Vec<TreeEntry>> {
        Box::pin(async move {
            let text = self
                .client
                .get_text(
                    &self.repo.tree_url(path, false),
                    &Self::tree_cache_key(path),
                    self.mode,
                )
                .await?;
            parse_tree_response(&text).map_err(|source| MihoError::Json {
                path: Self::tree_cache_key(path),
                source,
            })
        })
    }

    fn read_json<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Value> {
        Box::pin(async move {
            let key = Self::raw_cache_key(path);
            let text = self
                .client
                .get_text(&self.repo.raw_url(path), &key, self.mode)
                .await?;
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
}
