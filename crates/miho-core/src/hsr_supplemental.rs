use std::{
    fs,
    path::{Path, PathBuf},
};

use chrono::{DateTime, Utc};
use reqwest::header::{
    HeaderMap, HeaderName, HeaderValue, ACCEPT, ACCEPT_LANGUAGE, CACHE_CONTROL, CONTENT_TYPE,
    ORIGIN, REFERER, USER_AGENT,
};
use serde::Serialize;

use crate::{
    hsr_sources::{
        decode_prydwen_payload, extract_characters, extract_last_updated,
        extract_visible_team_scopes, prydwen_visible_url, HOYOWIKI_CHARACTER_MENU_ID,
        HOYOWIKI_WIKI_APP, PRYDWEN_TIER_URL,
    },
    network::{CachedHttpClient, FetchMode, FetchSource, FetchedText, HttpClient},
    supplemental::{
        HsrMode, HsrSupplementalResource, HsrSupplementalSource, Locale, SupplementalDocument,
        SupplementalFuture, SupplementalOrigin,
    },
    MihoError, Result,
};

pub const HOYOWIKI_ENTRY_LIST_URL: &str =
    "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HsrSupplementalEndpoints {
    pub prydwen_moc_url: String,
    pub prydwen_pf_url: String,
    pub prydwen_as_url: String,
    pub prydwen_aa_url: String,
    pub prydwen_tier_url: String,
    pub hoyowiki_entry_list_url: String,
}

impl Default for HsrSupplementalEndpoints {
    fn default() -> Self {
        Self {
            prydwen_moc_url: required_prydwen_url("moc"),
            prydwen_pf_url: required_prydwen_url("pf"),
            prydwen_as_url: required_prydwen_url("as"),
            prydwen_aa_url: required_prydwen_url("aa"),
            prydwen_tier_url: PRYDWEN_TIER_URL.to_owned(),
            hoyowiki_entry_list_url: HOYOWIKI_ENTRY_LIST_URL.to_owned(),
        }
    }
}

impl HsrSupplementalEndpoints {
    fn team_url(&self, mode: HsrMode) -> &str {
        match mode {
            HsrMode::Moc => &self.prydwen_moc_url,
            HsrMode::Pf => &self.prydwen_pf_url,
            HsrMode::As => &self.prydwen_as_url,
            HsrMode::Aa => &self.prydwen_aa_url,
        }
    }
}

#[derive(Clone)]
pub struct HsrHttpSupplementalSource {
    client: CachedHttpClient,
    mode: FetchMode,
    fetched_at: DateTime<Utc>,
    endpoints: HsrSupplementalEndpoints,
}

impl HsrHttpSupplementalSource {
    pub fn new(
        http: HttpClient,
        cache_root: impl Into<PathBuf>,
        mode: FetchMode,
        fetched_at: DateTime<Utc>,
    ) -> Self {
        Self::with_endpoints(
            http,
            cache_root,
            mode,
            fetched_at,
            HsrSupplementalEndpoints::default(),
        )
    }

    pub fn with_endpoints(
        http: HttpClient,
        cache_root: impl Into<PathBuf>,
        mode: FetchMode,
        fetched_at: DateTime<Utc>,
        endpoints: HsrSupplementalEndpoints,
    ) -> Self {
        Self {
            client: CachedHttpClient::new(http, cache_root),
            mode,
            fetched_at,
            endpoints,
        }
    }

    async fn fetch_document(
        &self,
        resource: HsrSupplementalResource,
    ) -> Result<SupplementalDocument> {
        match resource {
            HsrSupplementalResource::PrydwenTeams { mode } => {
                let source_url = self.endpoints.team_url(mode).to_owned();
                let headers = prydwen_headers(false);
                let fetched = self
                    .client
                    .get_text_with_headers_validated_with_source(
                        &source_url,
                        &headers,
                        &team_cache_key(mode),
                        self.mode,
                        validate_prydwen_teams,
                    )
                    .await?;
                Ok(self.document(fetched, source_url))
            }
            HsrSupplementalResource::PrydwenTier => {
                let source_url = self.endpoints.prydwen_tier_url.clone();
                let headers = prydwen_headers(true);
                let fetched = self
                    .client
                    .get_text_with_headers_validated_with_source(
                        &source_url,
                        &headers,
                        &tier_cache_key(),
                        self.mode,
                        validate_prydwen_tier,
                    )
                    .await?;
                Ok(self.document(fetched, source_url))
            }
            HsrSupplementalResource::HoyowikiCharacters { locale, page } => {
                validate_page(page)?;
                let source_url = self.endpoints.hoyowiki_entry_list_url.clone();
                let headers = hoyowiki_headers(locale);
                let body = HoyowikiPageRequest {
                    menu_id: HOYOWIKI_CHARACTER_MENU_ID,
                    page_num: page,
                    page_size: 50,
                };
                let fetched = self
                    .client
                    .post_json_validated_with_source(
                        &source_url,
                        &headers,
                        &body,
                        &hoyowiki_cache_key(locale, page),
                        self.mode,
                        validate_hoyowiki_response,
                    )
                    .await?;
                Ok(self.document(fetched, source_url))
            }
        }
    }

    fn document(&self, fetched: FetchedText, source_url: String) -> SupplementalDocument {
        SupplementalDocument {
            body: fetched.text,
            source_url,
            fetched_at: self.fetched_at,
            origin: match fetched.source {
                FetchSource::Network => SupplementalOrigin::Network,
                FetchSource::Cache => SupplementalOrigin::Cache,
            },
            fallback_reason: fetched.fallback_reason,
        }
    }
}

impl HsrSupplementalSource for HsrHttpSupplementalSource {
    fn fetch<'a>(&'a self, resource: HsrSupplementalResource) -> SupplementalFuture<'a> {
        Box::pin(async move { self.fetch_document(resource).await })
    }
}

#[derive(Debug, Clone)]
pub struct HsrFixtureSupplementalSource {
    root: PathBuf,
    fetched_at: DateTime<Utc>,
}

impl HsrFixtureSupplementalSource {
    pub fn new(root: impl Into<PathBuf>, fetched_at: DateTime<Utc>) -> Self {
        Self {
            root: root.into(),
            fetched_at,
        }
    }

    fn read_document(&self, resource: HsrSupplementalResource) -> Result<SupplementalDocument> {
        let (relative_path, source_url) = fixture_location(resource)?;
        let path = self.root.join(relative_path);
        let body = fs::read_to_string(&path).map_err(|source| MihoError::Read {
            path: path.clone(),
            source,
        })?;
        Ok(SupplementalDocument {
            body,
            source_url,
            fetched_at: self.fetched_at,
            origin: SupplementalOrigin::Fixture,
            fallback_reason: None,
        })
    }
}

impl HsrSupplementalSource for HsrFixtureSupplementalSource {
    fn fetch<'a>(&'a self, resource: HsrSupplementalResource) -> SupplementalFuture<'a> {
        Box::pin(async move { self.read_document(resource) })
    }
}

#[derive(Debug, Serialize)]
struct HoyowikiPageRequest {
    menu_id: &'static str,
    page_num: u32,
    page_size: u32,
}

fn prydwen_headers(include_referer: bool) -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ),
    );
    headers.insert(
        ACCEPT,
        HeaderValue::from_static("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    );
    headers.insert(ACCEPT_LANGUAGE, HeaderValue::from_static("en-US,en;q=0.9"));
    headers.insert(CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    if include_referer {
        headers.insert(REFERER, HeaderValue::from_static("https://www.google.com/"));
    }
    headers
}

fn hoyowiki_headers(locale: Locale) -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static("Mozilla/5.0 hsr-endgame-exporter/0.1"),
    );
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    headers.insert(ORIGIN, HeaderValue::from_static("https://wiki.hoyolab.com"));
    headers.insert(
        REFERER,
        match locale {
            Locale::EnUs => HeaderValue::from_static(
                "https://wiki.hoyolab.com/pc/hsr/aggregate/character?lang=en-us",
            ),
            Locale::ZhCn => HeaderValue::from_static(
                "https://wiki.hoyolab.com/pc/hsr/aggregate/character?lang=zh-cn",
            ),
        },
    );
    headers.insert(
        HeaderName::from_static("x-rpc-language"),
        HeaderValue::from_static(locale.code()),
    );
    headers.insert(
        HeaderName::from_static("x-rpc-wiki_app"),
        HeaderValue::from_static(HOYOWIKI_WIKI_APP),
    );
    headers
}

fn required_prydwen_url(mode: &str) -> String {
    prydwen_visible_url(mode)
        .expect("all typed HSR modes must have a Prydwen URL")
        .to_owned()
}

fn validate_page(page: u32) -> Result<()> {
    if page == 0 {
        Err(MihoError::Unsupported(
            "HoYoWiki character page numbers start at 1".to_owned(),
        ))
    } else {
        Ok(())
    }
}

fn validate_prydwen_teams(text: &str) -> Result<()> {
    if looks_like_html(text) && !extract_visible_team_scopes(text).is_empty() {
        return Ok(());
    }
    reject_html_challenge(text, "Prydwen team")?;
    Err(MihoError::Unsupported(
        "Prydwen team response contains no ranked team payload".to_owned(),
    ))
}

fn validate_prydwen_tier(text: &str) -> Result<()> {
    let decoded = decode_prydwen_payload(text);
    if looks_like_html(text)
        && !extract_last_updated(&decoded).is_empty()
        && !extract_characters(&decoded).is_empty()
    {
        return Ok(());
    }
    reject_html_challenge(text, "Prydwen tier")?;
    Err(MihoError::Unsupported(
        "Prydwen tier response contains no dated character payload".to_owned(),
    ))
}

fn reject_html_challenge(text: &str, source: &str) -> Result<()> {
    let lower = text.to_ascii_lowercase();
    if [
        "cloudflare",
        "just a moment",
        "cf-chl-",
        "captcha",
        "attention required",
    ]
    .iter()
    .any(|marker| lower.contains(marker))
    {
        return Err(MihoError::Unsupported(format!(
            "{source} response is an anti-bot challenge"
        )));
    }
    if !looks_like_html(&lower) {
        return Err(MihoError::Unsupported(format!(
            "{source} response is not HTML"
        )));
    }
    Ok(())
}

fn looks_like_html(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    lower.contains("<html") || lower.contains("<!doctype html")
}

fn validate_hoyowiki_response(text: &str) -> Result<()> {
    let value: serde_json::Value =
        serde_json::from_str(text).map_err(|source| MihoError::Json {
            path: PathBuf::from("hsr/hoyowiki/response.json"),
            source,
        })?;
    let retcode = value.get("retcode").and_then(serde_json::Value::as_i64);
    if retcode != Some(0) {
        let message = value
            .get("message")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("");
        return Err(MihoError::Unsupported(format!(
            "HoYoWiki returned retcode {}: {message}",
            retcode
                .map(|value| value.to_string())
                .unwrap_or_else(|| "<missing>".to_owned())
        )));
    }
    let data = value.get("data");
    if !data
        .and_then(|value| value.get("list"))
        .is_some_and(serde_json::Value::is_array)
    {
        return Err(MihoError::Unsupported(
            "HoYoWiki response data.list is not an array".to_owned(),
        ));
    }
    let total_is_valid = data
        .and_then(|value| value.get("total"))
        .is_some_and(|value| {
            value.as_u64().is_some()
                || value
                    .as_str()
                    .is_some_and(|text| text.parse::<u64>().is_ok())
        });
    if !total_is_valid {
        return Err(MihoError::Unsupported(
            "HoYoWiki response data.total is not a non-negative integer".to_owned(),
        ));
    }
    Ok(())
}

fn team_cache_key(mode: HsrMode) -> PathBuf {
    Path::new("hsr")
        .join("prydwen")
        .join("teams")
        .join(format!("{}.html", mode.code()))
}

fn tier_cache_key() -> PathBuf {
    Path::new("hsr").join("prydwen").join("tier-list.html")
}

fn hoyowiki_cache_key(locale: Locale, page: u32) -> PathBuf {
    Path::new("hsr")
        .join("hoyowiki")
        .join("characters")
        .join(locale.code())
        .join(format!("page-{page:04}.json"))
}

fn fixture_location(resource: HsrSupplementalResource) -> Result<(PathBuf, String)> {
    match resource {
        HsrSupplementalResource::PrydwenTeams { mode } => Ok((
            Path::new("prydwen")
                .join("teams")
                .join(format!("{}.html", mode.code())),
            required_prydwen_url(mode.code()),
        )),
        HsrSupplementalResource::PrydwenTier => Ok((
            Path::new("prydwen").join("tier-list.html"),
            PRYDWEN_TIER_URL.to_owned(),
        )),
        HsrSupplementalResource::HoyowikiCharacters { locale, page } => {
            validate_page(page)?;
            Ok((
                Path::new("hoyowiki")
                    .join("characters")
                    .join(locale.code())
                    .join(format!("page-{page:04}.json")),
                HOYOWIKI_ENTRY_LIST_URL.to_owned(),
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;
    use std::{
        io::{Read, Write},
        net::{TcpListener, TcpStream},
        sync::{Arc, Mutex},
        thread,
        time::Duration,
    };

    fn fixed_time() -> DateTime<Utc> {
        Utc.with_ymd_and_hms(2026, 7, 12, 6, 7, 8).unwrap()
    }

    fn temp_dir(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "miho-hsr-supplemental-{label}-{}",
            std::process::id()
        ))
    }

    fn fixture_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/hsr_supplemental")
    }

    const TEAM_HTML: &str =
        include_str!("../../../tests/fixtures/hsr_supplemental/prydwen/teams/moc.html");
    const TIER_HTML: &str =
        include_str!("../../../tests/fixtures/hsr_supplemental/prydwen/tier-list.html");
    const EN_HOYOWIKI: &str = include_str!(
        "../../../tests/fixtures/hsr_supplemental/hoyowiki/characters/en-us/page-0001.json"
    );
    const ZH_HOYOWIKI: &str = include_str!(
        "../../../tests/fixtures/hsr_supplemental/hoyowiki/characters/zh-cn/page-0001.json"
    );

    fn local_endpoints(origin: &str) -> HsrSupplementalEndpoints {
        HsrSupplementalEndpoints {
            prydwen_moc_url: format!("{origin}/teams/moc"),
            prydwen_pf_url: format!("{origin}/teams/pf"),
            prydwen_as_url: format!("{origin}/teams/as"),
            prydwen_aa_url: format!("{origin}/teams/aa"),
            prydwen_tier_url: format!("{origin}/tier"),
            hoyowiki_entry_list_url: format!("{origin}/hoyowiki"),
        }
    }

    fn serve(
        bodies: Vec<&'static str>,
    ) -> (String, Arc<Mutex<Vec<String>>>, thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let requests = Arc::new(Mutex::new(Vec::new()));
        let observed = requests.clone();
        let handle = thread::spawn(move || {
            for body in bodies {
                let (mut stream, _) = listener.accept().unwrap();
                observed
                    .lock()
                    .unwrap()
                    .push(read_http_request(&mut stream));
                write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            }
        });
        (format!("http://{address}"), requests, handle)
    }

    fn read_http_request(stream: &mut TcpStream) -> String {
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let mut data = Vec::new();
        let mut buffer = [0_u8; 1024];
        let expected_len = loop {
            let count = stream.read(&mut buffer).unwrap();
            assert!(count > 0, "request ended before headers");
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
            assert!(count > 0, "request ended before body");
            data.extend_from_slice(&buffer[..count]);
        }
        String::from_utf8(data).unwrap()
    }

    #[tokio::test]
    async fn online_prydwen_gets_use_stable_cache_keys_and_network_origin() {
        let root = temp_dir("online-get");
        let _ = fs::remove_dir_all(&root);
        let (origin, requests, server) = serve(vec![TEAM_HTML, TIER_HTML]);
        let source = HsrHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            local_endpoints(&origin),
        );

        let teams = source
            .fetch(HsrSupplementalResource::PrydwenTeams { mode: HsrMode::Moc })
            .await
            .unwrap();
        let tier = source
            .fetch(HsrSupplementalResource::PrydwenTier)
            .await
            .unwrap();
        server.join().unwrap();

        assert_eq!(teams.body, TEAM_HTML);
        assert_eq!(tier.body, TIER_HTML);
        assert_eq!(teams.origin, SupplementalOrigin::Network);
        assert_eq!(teams.fetched_at, fixed_time());
        assert_eq!(teams.source_url, format!("{origin}/teams/moc"));
        assert_eq!(tier.source_url, format!("{origin}/tier"));
        let requests = requests.lock().unwrap();
        assert!(requests[0].starts_with("GET /teams/moc HTTP/1.1\r\n"));
        assert!(requests[1].starts_with("GET /tier HTTP/1.1\r\n"));
        let team_request = requests[0].to_ascii_lowercase();
        assert!(team_request.contains("user-agent: mozilla/5.0 (windows nt 10.0; win64; x64)"));
        assert!(team_request.contains(
            "accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
        ));
        assert!(team_request.contains("accept-language: en-us,en;q=0.9\r\n"));
        assert!(team_request.contains("cache-control: no-cache\r\n"));
        assert!(!team_request.contains("referer: https://www.google.com/\r\n"));
        let tier_request = requests[1].to_ascii_lowercase();
        assert!(tier_request.contains("referer: https://www.google.com/\r\n"));
        assert_eq!(
            fs::read_to_string(root.join("hsr/prydwen/teams/moc.html")).unwrap(),
            TEAM_HTML
        );
        assert_eq!(
            fs::read_to_string(root.join("hsr/prydwen/tier-list.html")).unwrap(),
            TIER_HTML
        );
        drop(requests);
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn hoyowiki_post_has_python_headers_body_and_cache_mapping() {
        let root = temp_dir("online-post");
        let _ = fs::remove_dir_all(&root);
        let response = r#"{"retcode":0,"data":{"list":[],"total":0}}"#;
        let (origin, requests, server) = serve(vec![response]);
        let source = HsrHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            local_endpoints(&origin),
        );
        let document = source
            .fetch(HsrSupplementalResource::HoyowikiCharacters {
                locale: Locale::ZhCn,
                page: 2,
            })
            .await
            .unwrap();
        server.join().unwrap();

        assert_eq!(document.origin, SupplementalOrigin::Network);
        assert_eq!(document.source_url, format!("{origin}/hoyowiki"));
        assert_eq!(document.body, response);
        let requests = requests.lock().unwrap();
        let request = &requests[0];
        assert!(request.starts_with("POST /hoyowiki HTTP/1.1\r\n"));
        let lower = request.to_ascii_lowercase();
        assert!(lower.contains("user-agent: mozilla/5.0 hsr-endgame-exporter/0.1\r\n"));
        assert!(lower.contains("accept: application/json\r\n"));
        assert!(lower.contains("content-type: application/json\r\n"));
        assert!(lower.contains("origin: https://wiki.hoyolab.com\r\n"));
        assert!(lower.contains(
            "referer: https://wiki.hoyolab.com/pc/hsr/aggregate/character?lang=zh-cn\r\n"
        ));
        assert!(lower.contains("x-rpc-language: zh-cn\r\n"));
        assert!(lower.contains("x-rpc-wiki_app: hsr\r\n"));
        let (_, body) = request.split_once("\r\n\r\n").unwrap();
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(body).unwrap(),
            serde_json::json!({"menu_id":"104","page_num":2,"page_size":50})
        );
        assert_eq!(
            fs::read_to_string(root.join("hsr/hoyowiki/characters/zh-cn/page-0002.json")).unwrap(),
            response
        );
        drop(requests);
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn cache_origin_is_reported_for_offline_and_online_fallback() {
        let root = temp_dir("cache");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("hsr/prydwen/teams")).unwrap();
        fs::create_dir_all(root.join("hsr/hoyowiki/characters/en-us")).unwrap();
        fs::write(root.join("hsr/prydwen/teams/pf.html"), TEAM_HTML).unwrap();
        fs::write(
            root.join("hsr/hoyowiki/characters/en-us/page-0001.json"),
            EN_HOYOWIKI,
        )
        .unwrap();
        let endpoints = local_endpoints("http://127.0.0.1:1");
        let offline = HsrHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &root,
            FetchMode::Offline,
            fixed_time(),
            endpoints.clone(),
        );
        let teams = offline
            .fetch(HsrSupplementalResource::PrydwenTeams { mode: HsrMode::Pf })
            .await
            .unwrap();
        let names = offline
            .fetch(HsrSupplementalResource::HoyowikiCharacters {
                locale: Locale::EnUs,
                page: 1,
            })
            .await
            .unwrap();
        assert_eq!(
            (teams.body.as_str(), teams.origin),
            (TEAM_HTML, SupplementalOrigin::Cache)
        );
        assert_eq!(
            (names.body.as_str(), names.origin),
            (EN_HOYOWIKI, SupplementalOrigin::Cache)
        );
        assert_eq!(teams.fallback_reason, None);
        assert_eq!(names.fallback_reason, None);

        let online = HsrHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            endpoints,
        );
        let fallback = online
            .fetch(HsrSupplementalResource::PrydwenTeams { mode: HsrMode::Pf })
            .await
            .unwrap();
        assert_eq!(fallback.body, TEAM_HTML);
        assert_eq!(fallback.origin, SupplementalOrigin::Cache);
        assert!(fallback.fallback_reason.is_some());
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn semantic_validation_preserves_last_good_html_and_json_cache() {
        let root = temp_dir("semantic-fallback");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("hsr/prydwen/teams")).unwrap();
        fs::create_dir_all(root.join("hsr/hoyowiki/characters/zh-cn")).unwrap();
        fs::write(root.join("hsr/prydwen/teams/moc.html"), TEAM_HTML).unwrap();
        fs::write(
            root.join("hsr/hoyowiki/characters/zh-cn/page-0001.json"),
            ZH_HOYOWIKI,
        )
        .unwrap();
        let (origin, _requests, server) = serve(vec![
            "<html><title>Just a moment...</title>Cloudflare challenge</html>",
            r#"{"retcode":-1,"message":"denied"}"#,
        ]);
        let source = HsrHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            local_endpoints(&origin),
        );

        let teams = source
            .fetch(HsrSupplementalResource::PrydwenTeams { mode: HsrMode::Moc })
            .await
            .unwrap();
        let names = source
            .fetch(HsrSupplementalResource::HoyowikiCharacters {
                locale: Locale::ZhCn,
                page: 1,
            })
            .await
            .unwrap();
        server.join().unwrap();
        assert_eq!(teams.origin, SupplementalOrigin::Cache);
        assert_eq!(teams.body, TEAM_HTML);
        assert!(teams
            .fallback_reason
            .as_deref()
            .is_some_and(|reason| reason.contains("anti-bot challenge")));
        assert_eq!(names.origin, SupplementalOrigin::Cache);
        assert_eq!(names.body, ZH_HOYOWIKI);
        assert!(names
            .fallback_reason
            .as_deref()
            .is_some_and(|reason| reason.contains("retcode -1")));
        assert_eq!(
            fs::read_to_string(root.join("hsr/prydwen/teams/moc.html")).unwrap(),
            TEAM_HTML
        );
        assert_eq!(
            fs::read_to_string(root.join("hsr/hoyowiki/characters/zh-cn/page-0001.json")).unwrap(),
            ZH_HOYOWIKI
        );
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn fixture_adapter_maps_every_resource_family_and_reports_missing_files() {
        let source = HsrFixtureSupplementalSource::new(fixture_root(), fixed_time());
        let teams = source
            .fetch(HsrSupplementalResource::PrydwenTeams { mode: HsrMode::Aa })
            .await
            .unwrap();
        let tier = source
            .fetch(HsrSupplementalResource::PrydwenTier)
            .await
            .unwrap();
        let names = source
            .fetch(HsrSupplementalResource::HoyowikiCharacters {
                locale: Locale::EnUs,
                page: 1,
            })
            .await
            .unwrap();
        assert_eq!(teams.origin, SupplementalOrigin::Fixture);
        assert_eq!(teams.fetched_at, fixed_time());
        assert!(teams.body.contains("fixture-aa"));
        assert_eq!(teams.source_url, required_prydwen_url("aa"));
        assert!(tier.body.contains("lastUpdated"));
        assert_eq!(tier.source_url, PRYDWEN_TIER_URL);
        assert!(names.body.contains("March 7th"));
        assert_eq!(names.source_url, HOYOWIKI_ENTRY_LIST_URL);

        let missing = source
            .fetch(HsrSupplementalResource::HoyowikiCharacters {
                locale: Locale::EnUs,
                page: 2,
            })
            .await;
        assert!(
            matches!(missing, Err(MihoError::Read { path, .. }) if path.ends_with("hoyowiki/characters/en-us/page-0002.json"))
        );
        assert!(matches!(
            source
                .fetch(HsrSupplementalResource::HoyowikiCharacters {
                    locale: Locale::ZhCn,
                    page: 0,
                })
                .await,
            Err(MihoError::Unsupported(_))
        ));
    }
}
