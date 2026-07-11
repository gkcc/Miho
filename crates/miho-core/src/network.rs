use std::{
    fs,
    path::{Component, Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use reqwest::Client;
use tokio::time::sleep;

use crate::{atomic, MihoError, Result};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FetchMode {
    Online,
    Offline,
}

#[derive(Clone)]
pub struct HttpClient {
    client: Client,
    retries: usize,
    backoff: Arc<[Duration]>,
}

impl HttpClient {
    pub fn new(timeout: Duration, retries: usize) -> Result<Self> {
        Ok(Self {
            client: Client::builder()
                .timeout(timeout)
                .user_agent("miho-endgame/0.1")
                .build()?,
            retries,
            backoff: [
                Duration::from_millis(250),
                Duration::from_secs(1),
                Duration::from_secs(2),
            ]
            .into(),
        })
    }

    pub async fn get_text(&self, url: &str) -> Result<String> {
        let mut attempt = 0;
        loop {
            match self
                .client
                .get(url)
                .send()
                .await
                .and_then(|r| r.error_for_status())
            {
                Ok(response) => return Ok(response.text().await?),
                Err(error) if attempt < self.retries && is_retryable(&error) => {
                    sleep(self.backoff[attempt.min(self.backoff.len() - 1)]).await;
                    attempt += 1;
                    drop(error);
                }
                Err(error) => return Err(error.into()),
            }
        }
    }
}

fn is_retryable(error: &reqwest::Error) -> bool {
    if error.is_timeout() || error.is_connect() {
        return true;
    }
    matches!(
        error.status().map(|status| status.as_u16()),
        Some(408 | 425 | 429 | 500..=599)
    )
}

#[derive(Clone)]
pub struct CachedHttpClient {
    http: HttpClient,
    cache_root: PathBuf,
}

impl CachedHttpClient {
    pub fn new(http: HttpClient, cache_root: impl Into<PathBuf>) -> Self {
        Self {
            http,
            cache_root: cache_root.into(),
        }
    }

    pub async fn get_text(&self, url: &str, cache_key: &Path, mode: FetchMode) -> Result<String> {
        let path = self.cache_path(cache_key)?;
        if mode == FetchMode::Offline {
            return read_cache(&path, cache_key);
        }
        match self.http.get_text(url).await {
            Ok(text) => {
                atomic::write(&path, text.as_bytes())?;
                Ok(text)
            }
            Err(_network_error) if path.is_file() => read_cache(&path, cache_key),
            Err(network_error) => Err(network_error),
        }
    }

    fn cache_path(&self, key: &Path) -> Result<PathBuf> {
        if key.as_os_str().is_empty()
            || key.is_absolute()
            || key
                .components()
                .any(|part| !matches!(part, Component::Normal(_)))
        {
            return Err(MihoError::InvalidCacheKey(key.display().to_string()));
        }
        Ok(self.cache_root.join(key))
    }
}

fn read_cache(path: &Path, key: &Path) -> Result<String> {
    fs::read_to_string(path).map_err(|source| {
        if source.kind() == std::io::ErrorKind::NotFound {
            MihoError::CacheMiss(key.display().to_string())
        } else {
            MihoError::Read {
                path: path.into(),
                source,
            }
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Write},
        net::TcpListener,
        sync::atomic::{AtomicUsize, Ordering},
        thread,
    };

    fn temp_dir(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!("miho-network-{label}-{}", std::process::id()))
    }

    fn serve(statuses: Vec<u16>) -> (String, Arc<AtomicUsize>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let count = Arc::new(AtomicUsize::new(0));
        let observed = count.clone();
        thread::spawn(move || {
            for status in statuses {
                let (mut stream, _) = listener.accept().unwrap();
                let mut request = [0_u8; 1024];
                let _ = stream.read(&mut request);
                observed.fetch_add(1, Ordering::SeqCst);
                let reason = if status == 200 { "OK" } else { "Error" };
                let body = if status == 200 {
                    "fixed-response"
                } else {
                    "failed"
                };
                write!(stream, "HTTP/1.1 {status} {reason}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
            }
        });
        (format!("http://{address}/fixture"), count)
    }

    #[tokio::test]
    async fn retries_transient_status_but_not_permanent_client_error() {
        let http = HttpClient::new(Duration::from_secs(2), 2).unwrap();
        let (url, count) = serve(vec![500, 200]);
        assert_eq!(http.get_text(&url).await.unwrap(), "fixed-response");
        assert_eq!(count.load(Ordering::SeqCst), 2);

        let (url, count) = serve(vec![404]);
        assert!(http.get_text(&url).await.is_err());
        assert_eq!(count.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn offline_reads_cache_and_rejects_traversal() {
        let root = temp_dir("offline");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("hf")).unwrap();
        fs::write(root.join("hf/list.json"), "cached").unwrap();
        let client =
            CachedHttpClient::new(HttpClient::new(Duration::from_secs(1), 0).unwrap(), &root);
        assert_eq!(
            client
                .get_text("unused", Path::new("hf/list.json"), FetchMode::Offline)
                .await
                .unwrap(),
            "cached"
        );
        assert!(matches!(
            client
                .get_text("unused", Path::new("missing"), FetchMode::Offline)
                .await,
            Err(MihoError::CacheMiss(_))
        ));
        assert!(matches!(
            client
                .get_text("unused", Path::new("../escape"), FetchMode::Offline)
                .await,
            Err(MihoError::InvalidCacheKey(_))
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn online_failure_falls_back_to_existing_cache() {
        let root = temp_dir("fallback");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("response.txt"), "last-good").unwrap();
        let client = CachedHttpClient::new(
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &root,
        );
        let text = client
            .get_text(
                "http://127.0.0.1:1/unavailable",
                Path::new("response.txt"),
                FetchMode::Online,
            )
            .await
            .unwrap();
        assert_eq!(text, "last-good");
        let _ = fs::remove_dir_all(root);
    }
}
