use std::{
    fs,
    future::Future,
    path::{Component, Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use reqwest::{header::HeaderMap, Client, RequestBuilder};
use serde::{Deserialize, Serialize};
use tokio::time::sleep;

use crate::{atomic, MihoError, Result};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FetchMode {
    Online,
    Offline,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FetchSource {
    Network,
    Cache,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FetchedText {
    pub text: String,
    pub source: FetchSource,
    pub fallback_reason: Option<String>,
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
        self.get_text_with_headers(url, &HeaderMap::new()).await
    }

    pub async fn get_text_with_headers(&self, url: &str, headers: &HeaderMap) -> Result<String> {
        self.send_text(|| self.client.get(url).headers(headers.clone()))
            .await
    }

    pub async fn post_json<T>(&self, url: &str, headers: &HeaderMap, body: &T) -> Result<String>
    where
        T: Serialize + Sync + ?Sized,
    {
        self.send_text(|| self.client.post(url).headers(headers.clone()).json(body))
            .await
    }

    async fn send_text<F>(&self, build_request: F) -> Result<String>
    where
        F: Fn() -> RequestBuilder,
    {
        let mut attempt = 0;
        loop {
            match build_request()
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
        Ok(self.get_text_with_source(url, cache_key, mode).await?.text)
    }

    pub async fn get_text_with_source(
        &self,
        url: &str,
        cache_key: &Path,
        mode: FetchMode,
    ) -> Result<FetchedText> {
        self.get_text_validated_with_source(url, cache_key, mode, |_| Ok(()))
            .await
    }

    pub async fn get_text_validated_with_source<V>(
        &self,
        url: &str,
        cache_key: &Path,
        mode: FetchMode,
        validate: V,
    ) -> Result<FetchedText>
    where
        V: Fn(&str) -> Result<()> + Send + Sync,
    {
        self.get_text_with_headers_validated_with_source(
            url,
            &HeaderMap::new(),
            cache_key,
            mode,
            validate,
        )
        .await
    }

    pub async fn get_text_with_headers_validated_with_source<V>(
        &self,
        url: &str,
        headers: &HeaderMap,
        cache_key: &Path,
        mode: FetchMode,
        validate: V,
    ) -> Result<FetchedText>
    where
        V: Fn(&str) -> Result<()> + Send + Sync,
    {
        self.fetch_validated_with_cache(
            cache_key,
            mode,
            self.http.get_text_with_headers(url, headers),
            validate,
        )
        .await
    }

    pub async fn post_json_with_source<T>(
        &self,
        url: &str,
        headers: &HeaderMap,
        body: &T,
        cache_key: &Path,
        mode: FetchMode,
    ) -> Result<FetchedText>
    where
        T: Serialize + Sync + ?Sized,
    {
        self.post_json_validated_with_source(url, headers, body, cache_key, mode, |_| Ok(()))
            .await
    }

    pub async fn post_json_validated_with_source<T, V>(
        &self,
        url: &str,
        headers: &HeaderMap,
        body: &T,
        cache_key: &Path,
        mode: FetchMode,
        validate: V,
    ) -> Result<FetchedText>
    where
        T: Serialize + Sync + ?Sized,
        V: Fn(&str) -> Result<()> + Send + Sync,
    {
        self.fetch_validated_with_cache(
            cache_key,
            mode,
            self.http.post_json(url, headers, body),
            validate,
        )
        .await
    }

    async fn fetch_validated_with_cache<F, V>(
        &self,
        cache_key: &Path,
        mode: FetchMode,
        network: F,
        validate: V,
    ) -> Result<FetchedText>
    where
        F: Future<Output = Result<String>> + Send,
        V: Fn(&str) -> Result<()> + Send + Sync,
    {
        let path = self.cache_path(cache_key)?;
        if mode == FetchMode::Offline {
            return read_validated_cache(&path, cache_key, &validate, None);
        }
        match network.await {
            Ok(text) => {
                if let Err(validation_error) = validate(&text) {
                    if path.is_file() {
                        return read_validated_cache(
                            &path,
                            cache_key,
                            &validate,
                            Some(validation_error.to_string()),
                        );
                    }
                    return Err(validation_error);
                }
                atomic::write(&path, text.as_bytes())?;
                Ok(FetchedText {
                    text,
                    source: FetchSource::Network,
                    fallback_reason: None,
                })
            }
            Err(network_error) if path.is_file() => {
                let reason = network_error.to_string();
                read_validated_cache(&path, cache_key, &validate, Some(reason))
            }
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

fn read_validated_cache<V>(
    path: &Path,
    key: &Path,
    validate: &V,
    fallback_reason: Option<String>,
) -> Result<FetchedText>
where
    V: Fn(&str) -> Result<()>,
{
    let text = read_cache(path, key)?;
    validate(&text)?;
    Ok(FetchedText {
        text,
        source: FetchSource::Cache,
        fallback_reason,
    })
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
        net::{TcpListener, TcpStream},
        sync::{
            atomic::{AtomicUsize, Ordering},
            Mutex,
        },
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

    fn serve_bodies(bodies: Vec<&'static str>) -> (String, thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let handle = thread::spawn(move || {
            for body in bodies {
                let (mut stream, _) = listener.accept().unwrap();
                let mut request = [0_u8; 1024];
                let _ = stream.read(&mut request);
                write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            }
        });
        (format!("http://{address}/fixture"), handle)
    }

    fn serve_recording(
        statuses: Vec<u16>,
    ) -> (String, Arc<Mutex<Vec<String>>>, thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let requests = Arc::new(Mutex::new(vec![]));
        let observed = requests.clone();
        let handle = thread::spawn(move || {
            for status in statuses {
                let (mut stream, _) = listener.accept().unwrap();
                observed
                    .lock()
                    .unwrap()
                    .push(read_http_request(&mut stream));
                let reason = if status == 200 { "OK" } else { "Error" };
                let body = if status == 200 {
                    r#"{"ok":true}"#
                } else {
                    r#"{"ok":false}"#
                };
                write!(
                    stream,
                    "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            }
        });
        (format!("http://{address}/fixture"), requests, handle)
    }

    fn read_http_request(stream: &mut TcpStream) -> String {
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let mut data = vec![];
        let mut buffer = [0_u8; 1024];
        let expected_len = loop {
            let count = stream.read(&mut buffer).unwrap();
            assert!(count > 0, "request ended before its headers were complete");
            data.extend_from_slice(&buffer[..count]);
            if let Some(header_end) = data.windows(4).position(|part| part == b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&data[..header_end]);
                let content_len = headers
                    .lines()
                    .filter_map(|line| line.split_once(':'))
                    .find(|(name, _)| name.eq_ignore_ascii_case("content-length"))
                    .and_then(|(_, value)| value.trim().parse::<usize>().ok())
                    .unwrap_or(0);
                break header_end + 4 + content_len;
            }
        };
        while data.len() < expected_len {
            let count = stream.read(&mut buffer).unwrap();
            assert!(count > 0, "request ended before its body was complete");
            data.extend_from_slice(&buffer[..count]);
        }
        String::from_utf8(data).unwrap()
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
        let fetched = client
            .get_text_with_source("unused", Path::new("hf/list.json"), FetchMode::Offline)
            .await
            .unwrap();
        assert_eq!(fetched.source, FetchSource::Cache);
        assert_eq!(fetched.text, "cached");
        assert_eq!(fetched.fallback_reason, None);
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
        let fetched = client
            .get_text_with_source(
                "http://127.0.0.1:1/unavailable",
                Path::new("response.txt"),
                FetchMode::Online,
            )
            .await
            .unwrap();
        assert_eq!(fetched.source, FetchSource::Cache);
        assert_eq!(fetched.text, "last-good");
        assert!(fetched
            .fallback_reason
            .as_deref()
            .is_some_and(|reason| reason.contains("network request failed")));
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn online_success_reports_network_and_writes_cache() {
        let root = temp_dir("online-source");
        let _ = fs::remove_dir_all(&root);
        let (url, count) = serve(vec![200]);
        let client =
            CachedHttpClient::new(HttpClient::new(Duration::from_secs(2), 0).unwrap(), &root);
        let fetched = client
            .get_text_with_source(&url, Path::new("response.txt"), FetchMode::Online)
            .await
            .unwrap();
        assert_eq!(fetched.source, FetchSource::Network);
        assert_eq!(fetched.text, "fixed-response");
        assert_eq!(fetched.fallback_reason, None);
        assert_eq!(count.load(Ordering::SeqCst), 1);
        assert_eq!(
            fs::read_to_string(root.join("response.txt")).unwrap(),
            "fixed-response"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn validated_get_sends_custom_browser_headers() {
        let root = temp_dir("get-headers");
        let _ = fs::remove_dir_all(&root);
        let (url, requests, server) = serve_recording(vec![200]);
        let client =
            CachedHttpClient::new(HttpClient::new(Duration::from_secs(2), 0).unwrap(), &root);
        let mut headers = HeaderMap::new();
        headers.insert("user-agent", "Mozilla/5.0 miho-test".parse().unwrap());
        headers.insert("accept", "text/html,application/xhtml+xml".parse().unwrap());
        headers.insert("accept-language", "zh-CN,zh;q=0.9".parse().unwrap());
        headers.insert("cache-control", "no-cache".parse().unwrap());
        headers.insert("referer", "https://www.prydwen.gg/".parse().unwrap());

        let fetched = client
            .get_text_with_headers_validated_with_source(
                &url,
                &headers,
                Path::new("prydwen/page.html"),
                FetchMode::Online,
                |text| {
                    if text == r#"{"ok":true}"# {
                        Ok(())
                    } else {
                        Err(MihoError::Unsupported("unexpected GET response".into()))
                    }
                },
            )
            .await
            .unwrap();
        assert_eq!(fetched.source, FetchSource::Network);
        assert_eq!(fetched.fallback_reason, None);
        server.join().unwrap();

        let requests = requests.lock().unwrap();
        assert_eq!(requests.len(), 1);
        let request = &requests[0];
        assert!(request.starts_with("GET /fixture HTTP/1.1\r\n"));
        let lower = request.to_ascii_lowercase();
        assert!(lower.contains("user-agent: mozilla/5.0 miho-test\r\n"));
        assert!(lower.contains("accept-language: zh-cn,zh;q=0.9\r\n"));
        assert!(lower.contains("cache-control: no-cache\r\n"));
        assert!(lower.contains("referer: https://www.prydwen.gg/\r\n"));
        drop(requests);
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn json_post_retries_with_method_body_headers_and_supports_cache_modes() {
        let root = temp_dir("post");
        let _ = fs::remove_dir_all(&root);
        let (url, requests, server) = serve_recording(vec![500, 200]);
        let client =
            CachedHttpClient::new(HttpClient::new(Duration::from_secs(2), 1).unwrap(), &root);
        let mut headers = HeaderMap::new();
        headers.insert("x-rpc-language", "zh-cn".parse().unwrap());
        headers.insert("x-rpc-wiki_app", "zzz".parse().unwrap());
        let body = serde_json::json!({"filters": ["Agent"], "page_num": 1});
        let cache_key = Path::new("hoyowiki/agents.json");

        let fetched = client
            .post_json_validated_with_source(
                &url,
                &headers,
                &body,
                cache_key,
                FetchMode::Online,
                |text| {
                    if text == r#"{"ok":true}"# {
                        Ok(())
                    } else {
                        Err(MihoError::Unsupported("POST response was not ok".into()))
                    }
                },
            )
            .await
            .unwrap();
        assert_eq!(fetched.source, FetchSource::Network);
        assert_eq!(fetched.text, r#"{"ok":true}"#);
        assert_eq!(fetched.fallback_reason, None);
        server.join().unwrap();

        {
            let requests = requests.lock().unwrap();
            assert_eq!(requests.len(), 2, "transient POST should be retried");
            for request in requests.iter() {
                assert!(request.starts_with("POST /fixture HTTP/1.1\r\n"));
                let lower = request.to_ascii_lowercase();
                assert!(lower.contains("x-rpc-language: zh-cn\r\n"));
                assert!(lower.contains("x-rpc-wiki_app: zzz\r\n"));
                assert!(lower.contains("content-type: application/json\r\n"));
                let (_, request_body) = request.split_once("\r\n\r\n").unwrap();
                assert_eq!(
                    serde_json::from_str::<serde_json::Value>(request_body).unwrap(),
                    body
                );
            }
        }

        let offline = client
            .post_json_with_source(
                "http://127.0.0.1:1/unavailable",
                &headers,
                &body,
                cache_key,
                FetchMode::Offline,
            )
            .await
            .unwrap();
        assert_eq!(offline.source, FetchSource::Cache);
        assert_eq!(offline.text, r#"{"ok":true}"#);
        assert_eq!(offline.fallback_reason, None);

        let fallback = client
            .post_json_with_source(
                "http://127.0.0.1:1/unavailable",
                &headers,
                &body,
                cache_key,
                FetchMode::Online,
            )
            .await
            .unwrap();
        assert_eq!(fallback.source, FetchSource::Cache);
        assert_eq!(fallback.text, r#"{"ok":true}"#);
        assert!(fallback.fallback_reason.is_some());
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn invalid_success_response_keeps_last_good_cache_and_records_reason() {
        fn validate_payload(text: &str) -> Result<()> {
            if text == "last-good" {
                Ok(())
            } else {
                Err(MihoError::Unsupported(
                    "response failed semantic validation".into(),
                ))
            }
        }

        let root = temp_dir("validated");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let cache_key = Path::new("response.txt");
        fs::write(root.join(cache_key), "last-good").unwrap();
        let (url, server) = serve_bodies(vec![
            "<html>cloudflare challenge</html>",
            r#"{"retcode":-1}"#,
        ]);
        let client =
            CachedHttpClient::new(HttpClient::new(Duration::from_secs(2), 0).unwrap(), &root);

        let fetched = client
            .get_text_validated_with_source(&url, cache_key, FetchMode::Online, validate_payload)
            .await
            .unwrap();
        assert_eq!(fetched.source, FetchSource::Cache);
        assert_eq!(fetched.text, "last-good");
        assert_eq!(
            fetched.fallback_reason.as_deref(),
            Some("unsupported operation: response failed semantic validation")
        );
        assert_eq!(
            fs::read_to_string(root.join(cache_key)).unwrap(),
            "last-good"
        );

        let missing_key = Path::new("missing.txt");
        let error = client
            .get_text_validated_with_source(&url, missing_key, FetchMode::Online, validate_payload)
            .await
            .unwrap_err();
        assert!(matches!(
            error,
            MihoError::Unsupported(message)
                if message == "response failed semantic validation"
        ));
        assert!(!root.join(missing_key).exists());
        server.join().unwrap();
        let _ = fs::remove_dir_all(root);
    }
}
