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
    network::{CachedHttpClient, FetchMode, FetchSource, FetchedText, HttpClient},
    supplemental::{
        HoyowikiEntryKind, Locale, SupplementalDocument, SupplementalFuture, SupplementalOrigin,
        ZzzMode, ZzzSupplementalResource, ZzzSupplementalSource,
    },
    zzz_prydwen::{extract_visible_teams, parse_document, team_url, TIER_URL},
    zzz_sources::{decode_entry_page_response, hoyowiki_menu_id, HOYOWIKI_API_URL, HOYOWIKI_APP},
    MihoError, Result,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ZzzSupplementalEndpoints {
    pub prydwen_sd_url: String,
    pub prydwen_da_url: String,
    pub prydwen_tier_url: String,
    pub hoyowiki_entry_list_url: String,
}

impl Default for ZzzSupplementalEndpoints {
    fn default() -> Self {
        Self {
            prydwen_sd_url: team_url(ZzzMode::Sd).to_owned(),
            prydwen_da_url: team_url(ZzzMode::Da).to_owned(),
            prydwen_tier_url: TIER_URL.to_owned(),
            hoyowiki_entry_list_url: HOYOWIKI_API_URL.to_owned(),
        }
    }
}

impl ZzzSupplementalEndpoints {
    fn team_url(&self, mode: ZzzMode) -> &str {
        match mode {
            ZzzMode::Sd => &self.prydwen_sd_url,
            ZzzMode::Da => &self.prydwen_da_url,
        }
    }
}

#[derive(Clone)]
pub struct ZzzHttpSupplementalSource {
    client: CachedHttpClient,
    mode: FetchMode,
    fetched_at: DateTime<Utc>,
    endpoints: ZzzSupplementalEndpoints,
}

impl ZzzHttpSupplementalSource {
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
            ZzzSupplementalEndpoints::default(),
        )
    }

    pub fn with_endpoints(
        http: HttpClient,
        cache_root: impl Into<PathBuf>,
        mode: FetchMode,
        fetched_at: DateTime<Utc>,
        endpoints: ZzzSupplementalEndpoints,
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
        resource: ZzzSupplementalResource,
    ) -> Result<SupplementalDocument> {
        match resource {
            ZzzSupplementalResource::PrydwenTeams { mode } => {
                let source_url = self.endpoints.team_url(mode).to_owned();
                let headers = prydwen_headers();
                let fetched = self
                    .client
                    .get_browser_text_with_headers_validated_with_source(
                        &source_url,
                        &headers,
                        &team_cache_key(mode),
                        self.mode,
                        validate_prydwen_teams,
                    )
                    .await?;
                Ok(self.document(fetched, source_url))
            }
            ZzzSupplementalResource::PrydwenTier => {
                let source_url = self.endpoints.prydwen_tier_url.clone();
                let headers = prydwen_headers();
                let fetched = self
                    .client
                    .get_browser_text_with_headers_validated_with_source(
                        &source_url,
                        &headers,
                        &tier_cache_key(),
                        self.mode,
                        validate_prydwen_tier,
                    )
                    .await?;
                Ok(self.document(fetched, source_url))
            }
            ZzzSupplementalResource::HoyowikiEntries {
                entry_kind,
                locale,
                page,
            } => {
                validate_page(page)?;
                let menu_id = required_menu_id(entry_kind)?;
                let source_url = self.endpoints.hoyowiki_entry_list_url.clone();
                let headers = hoyowiki_headers(entry_kind, locale)?;
                let body = HoyowikiPageRequest {
                    menu_id,
                    page_num: page,
                    page_size: 50,
                };
                let fetched = self
                    .client
                    .post_json_validated_with_source(
                        &source_url,
                        &headers,
                        &body,
                        &hoyowiki_cache_key(entry_kind, locale, page)?,
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

impl ZzzSupplementalSource for ZzzHttpSupplementalSource {
    fn fetch<'a>(&'a self, resource: ZzzSupplementalResource) -> SupplementalFuture<'a> {
        Box::pin(async move { self.fetch_document(resource).await })
    }
}

#[derive(Debug, Clone)]
pub struct ZzzFixtureSupplementalSource {
    root: PathBuf,
    fetched_at: DateTime<Utc>,
}

impl ZzzFixtureSupplementalSource {
    pub fn new(root: impl Into<PathBuf>, fetched_at: DateTime<Utc>) -> Self {
        Self {
            root: root.into(),
            fetched_at,
        }
    }

    fn read_document(&self, resource: ZzzSupplementalResource) -> Result<SupplementalDocument> {
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

impl ZzzSupplementalSource for ZzzFixtureSupplementalSource {
    fn fetch<'a>(&'a self, resource: ZzzSupplementalResource) -> SupplementalFuture<'a> {
        Box::pin(async move { self.read_document(resource) })
    }
}

#[derive(Debug, Serialize)]
struct HoyowikiPageRequest {
    menu_id: &'static str,
    page_num: u32,
    page_size: u32,
}

fn prydwen_headers() -> HeaderMap {
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
    headers.insert(REFERER, HeaderValue::from_static("https://www.google.com/"));
    headers
}

fn hoyowiki_headers(entry_kind: HoyowikiEntryKind, locale: Locale) -> Result<HeaderMap> {
    required_menu_id(entry_kind)?;
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static("Mozilla/5.0 zzz-endgame-exporter/0.1"),
    );
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    headers.insert(ORIGIN, HeaderValue::from_static("https://wiki.hoyolab.com"));
    headers.insert(REFERER, hoyowiki_referer(entry_kind, locale)?);
    headers.insert(
        HeaderName::from_static("x-rpc-language"),
        HeaderValue::from_static(locale.code()),
    );
    headers.insert(
        HeaderName::from_static("x-rpc-wiki_app"),
        HeaderValue::from_static(HOYOWIKI_APP),
    );
    Ok(headers)
}

fn hoyowiki_referer(entry_kind: HoyowikiEntryKind, locale: Locale) -> Result<HeaderValue> {
    Ok(match (entry_kind, locale) {
        (HoyowikiEntryKind::Agent, Locale::EnUs) => {
            HeaderValue::from_static("https://wiki.hoyolab.com/m/zzz/aggregate/8?lang=en-us")
        }
        (HoyowikiEntryKind::Agent, Locale::ZhCn) => {
            HeaderValue::from_static("https://wiki.hoyolab.com/m/zzz/aggregate/8?lang=zh-cn")
        }
        (HoyowikiEntryKind::Bangboo, Locale::EnUs) => {
            HeaderValue::from_static("https://wiki.hoyolab.com/m/zzz/aggregate/15?lang=en-us")
        }
        (HoyowikiEntryKind::Bangboo, Locale::ZhCn) => {
            HeaderValue::from_static("https://wiki.hoyolab.com/m/zzz/aggregate/15?lang=zh-cn")
        }
        (HoyowikiEntryKind::Character, _) => return Err(unsupported_entry_kind()),
    })
}

fn required_menu_id(entry_kind: HoyowikiEntryKind) -> Result<&'static str> {
    hoyowiki_menu_id(entry_kind).ok_or_else(unsupported_entry_kind)
}

fn unsupported_entry_kind() -> MihoError {
    MihoError::Unsupported("ZZZ HoYoWiki only supports agent and bangboo entries".to_owned())
}

fn validate_page(page: u32) -> Result<()> {
    if page == 0 {
        Err(MihoError::Unsupported(
            "HoYoWiki entry page numbers start at 1".to_owned(),
        ))
    } else {
        Ok(())
    }
}

fn validate_prydwen_teams(text: &str) -> Result<()> {
    if looks_like_html(text) && !extract_visible_teams(text).is_empty() {
        return Ok(());
    }
    reject_html_challenge(text, "Prydwen ZZZ team")?;
    Err(MihoError::Unsupported(
        "Prydwen ZZZ team response contains no ranked team payload".to_owned(),
    ))
}

fn validate_prydwen_tier(text: &str) -> Result<()> {
    let parsed = parse_document(text, "");
    if looks_like_html(text) && !parsed.last_updated.is_empty() && !parsed.tiers.is_empty() {
        return Ok(());
    }
    reject_html_challenge(text, "Prydwen ZZZ tier")?;
    Err(MihoError::Unsupported(
        "Prydwen ZZZ tier response contains no dated character payload".to_owned(),
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
    if !looks_like_html(text) {
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
    decode_entry_page_response(text)
        .map(|_| ())
        .map_err(MihoError::Unsupported)
}

fn team_cache_key(mode: ZzzMode) -> PathBuf {
    Path::new("zzz")
        .join("prydwen")
        .join("teams")
        .join(format!("{}.html", mode.code()))
}

fn tier_cache_key() -> PathBuf {
    Path::new("zzz").join("prydwen").join("tier-list.html")
}

fn hoyowiki_cache_key(entry_kind: HoyowikiEntryKind, locale: Locale, page: u32) -> Result<PathBuf> {
    Ok(Path::new("zzz")
        .join("hoyowiki")
        .join(entry_kind_code(entry_kind)?)
        .join(locale.code())
        .join(format!("page-{page:04}.json")))
}

fn entry_kind_code(entry_kind: HoyowikiEntryKind) -> Result<&'static str> {
    match entry_kind {
        HoyowikiEntryKind::Agent => Ok("agent"),
        HoyowikiEntryKind::Bangboo => Ok("bangboo"),
        HoyowikiEntryKind::Character => Err(unsupported_entry_kind()),
    }
}

fn fixture_location(resource: ZzzSupplementalResource) -> Result<(PathBuf, String)> {
    match resource {
        ZzzSupplementalResource::PrydwenTeams { mode } => Ok((
            Path::new("prydwen")
                .join("teams")
                .join(format!("{}.html", mode.code())),
            team_url(mode).to_owned(),
        )),
        ZzzSupplementalResource::PrydwenTier => Ok((
            Path::new("prydwen").join("tier-list.html"),
            TIER_URL.to_owned(),
        )),
        ZzzSupplementalResource::HoyowikiEntries {
            entry_kind,
            locale,
            page,
        } => {
            validate_page(page)?;
            let kind = entry_kind_code(entry_kind)?;
            Ok((
                Path::new("hoyowiki")
                    .join(kind)
                    .join(locale.code())
                    .join(format!("page-{page:04}.json")),
                HOYOWIKI_API_URL.to_owned(),
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
        Utc.with_ymd_and_hms(2026, 7, 12, 7, 8, 9).unwrap()
    }

    fn temp_dir(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "miho-zzz-supplemental-{label}-{}",
            std::process::id()
        ))
    }

    fn fixture_root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/zzz_supplemental_source")
    }

    const SD_HTML: &str =
        include_str!("../../../tests/fixtures/zzz_supplemental_source/prydwen/teams/sd.html");
    const TIER_HTML: &str =
        include_str!("../../../tests/fixtures/zzz_supplemental_source/prydwen/tier-list.html");
    const AGENT_ZH: &str = include_str!(
        "../../../tests/fixtures/zzz_supplemental_source/hoyowiki/agent/zh-cn/page-0001.json"
    );

    fn local_endpoints(origin: &str) -> ZzzSupplementalEndpoints {
        ZzzSupplementalEndpoints {
            prydwen_sd_url: format!("{origin}/teams/sd"),
            prydwen_da_url: format!("{origin}/teams/da"),
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
    async fn online_prydwen_gets_send_browser_headers_and_use_stable_cache_keys() {
        let root = temp_dir("online-get");
        let _ = fs::remove_dir_all(&root);
        let (origin, requests, server) = serve(vec![SD_HTML, TIER_HTML]);
        let source = ZzzHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            local_endpoints(&origin),
        );
        let teams = source
            .fetch(ZzzSupplementalResource::PrydwenTeams { mode: ZzzMode::Sd })
            .await
            .unwrap();
        let tier = source
            .fetch(ZzzSupplementalResource::PrydwenTier)
            .await
            .unwrap();
        server.join().unwrap();

        assert_eq!(teams.body, SD_HTML);
        assert_eq!(tier.body, TIER_HTML);
        assert_eq!(teams.origin, SupplementalOrigin::Network);
        assert_eq!(teams.fetched_at, fixed_time());
        assert_eq!(teams.source_url, format!("{origin}/teams/sd"));
        let requests = requests.lock().unwrap();
        assert!(requests[0].starts_with("GET /teams/sd HTTP/1.1\r\n"));
        assert!(requests[1].starts_with("GET /tier HTTP/1.1\r\n"));
        for request in requests.iter() {
            let lower = request.to_ascii_lowercase();
            assert!(lower.contains("user-agent: mozilla/5.0 (windows nt 10.0; win64; x64)"));
            assert!(lower.contains(
                "accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            ));
            assert!(lower.contains("accept-language: en-us,en;q=0.9\r\n"));
            assert!(lower.contains("cache-control: no-cache\r\n"));
            assert!(lower.contains("referer: https://www.google.com/\r\n"));
        }
        assert_eq!(
            fs::read_to_string(root.join("zzz/prydwen/teams/sd.html")).unwrap(),
            SD_HTML
        );
        assert_eq!(
            fs::read_to_string(root.join("zzz/prydwen/tier-list.html")).unwrap(),
            TIER_HTML
        );
        drop(requests);
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn hoyowiki_post_uses_kind_specific_menu_referer_and_cache_key() {
        let root = temp_dir("online-post");
        let _ = fs::remove_dir_all(&root);
        let response = r#"{"retcode":0,"data":{"list":[],"total":0}}"#;
        let (origin, requests, server) = serve(vec![response, response]);
        let source = ZzzHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            local_endpoints(&origin),
        );
        source
            .fetch(ZzzSupplementalResource::HoyowikiEntries {
                entry_kind: HoyowikiEntryKind::Agent,
                locale: Locale::ZhCn,
                page: 2,
            })
            .await
            .unwrap();
        source
            .fetch(ZzzSupplementalResource::HoyowikiEntries {
                entry_kind: HoyowikiEntryKind::Bangboo,
                locale: Locale::EnUs,
                page: 3,
            })
            .await
            .unwrap();
        server.join().unwrap();

        let requests = requests.lock().unwrap();
        assert_eq!(requests.len(), 2);
        for (request, menu, locale, page) in [
            (&requests[0], "8", "zh-cn", 2),
            (&requests[1], "15", "en-us", 3),
        ] {
            assert!(request.starts_with("POST /hoyowiki HTTP/1.1\r\n"));
            let lower = request.to_ascii_lowercase();
            assert!(lower.contains("user-agent: mozilla/5.0 zzz-endgame-exporter/0.1\r\n"));
            assert!(lower.contains("accept: application/json\r\n"));
            assert!(lower.contains("content-type: application/json\r\n"));
            assert!(lower.contains("origin: https://wiki.hoyolab.com\r\n"));
            assert!(lower.contains(&format!("x-rpc-language: {locale}\r\n")));
            assert!(lower.contains("x-rpc-wiki_app: zzz\r\n"));
            assert!(lower.contains(&format!(
                "referer: https://wiki.hoyolab.com/m/zzz/aggregate/{menu}?lang={locale}\r\n"
            )));
            let (_, body) = request.split_once("\r\n\r\n").unwrap();
            assert_eq!(
                serde_json::from_str::<serde_json::Value>(body).unwrap(),
                serde_json::json!({"menu_id":menu,"page_num":page,"page_size":50})
            );
        }
        assert!(root
            .join("zzz/hoyowiki/agent/zh-cn/page-0002.json")
            .is_file());
        assert!(root
            .join("zzz/hoyowiki/bangboo/en-us/page-0003.json")
            .is_file());
        drop(requests);
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn offline_and_online_failure_map_to_cache_origin_and_reason() {
        let root = temp_dir("cache");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("zzz/prydwen/teams")).unwrap();
        fs::create_dir_all(root.join("zzz/hoyowiki/agent/zh-cn")).unwrap();
        fs::write(root.join("zzz/prydwen/teams/da.html"), SD_HTML).unwrap();
        fs::write(
            root.join("zzz/hoyowiki/agent/zh-cn/page-0001.json"),
            AGENT_ZH,
        )
        .unwrap();
        let endpoints = local_endpoints("http://127.0.0.1:1");
        let offline = ZzzHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &root,
            FetchMode::Offline,
            fixed_time(),
            endpoints.clone(),
        );
        let team = offline
            .fetch(ZzzSupplementalResource::PrydwenTeams { mode: ZzzMode::Da })
            .await
            .unwrap();
        let agent = offline
            .fetch(ZzzSupplementalResource::HoyowikiEntries {
                entry_kind: HoyowikiEntryKind::Agent,
                locale: Locale::ZhCn,
                page: 1,
            })
            .await
            .unwrap();
        assert_eq!(team.origin, SupplementalOrigin::Cache);
        assert_eq!(team.fallback_reason, None);
        assert_eq!(agent.origin, SupplementalOrigin::Cache);

        let online = ZzzHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            endpoints,
        );
        let fallback = online
            .fetch(ZzzSupplementalResource::PrydwenTeams { mode: ZzzMode::Da })
            .await
            .unwrap();
        assert_eq!(fallback.origin, SupplementalOrigin::Cache);
        assert!(fallback.fallback_reason.is_some());
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn semantic_validation_keeps_last_good_prydwen_and_hoyowiki_cache() {
        let root = temp_dir("semantic-fallback");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("zzz/prydwen/teams")).unwrap();
        fs::create_dir_all(root.join("zzz/hoyowiki/agent/zh-cn")).unwrap();
        fs::write(root.join("zzz/prydwen/teams/sd.html"), SD_HTML).unwrap();
        fs::write(
            root.join("zzz/hoyowiki/agent/zh-cn/page-0001.json"),
            AGENT_ZH,
        )
        .unwrap();
        let (origin, _requests, server) = serve(vec![
            "<html><title>Just a moment...</title>Cloudflare challenge</html>",
            r#"{"retcode":-1,"message":"denied"}"#,
        ]);
        let source = ZzzHttpSupplementalSource::with_endpoints(
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &root,
            FetchMode::Online,
            fixed_time(),
            local_endpoints(&origin),
        );
        let team = source
            .fetch(ZzzSupplementalResource::PrydwenTeams { mode: ZzzMode::Sd })
            .await
            .unwrap();
        let agent = source
            .fetch(ZzzSupplementalResource::HoyowikiEntries {
                entry_kind: HoyowikiEntryKind::Agent,
                locale: Locale::ZhCn,
                page: 1,
            })
            .await
            .unwrap();
        server.join().unwrap();

        assert_eq!(team.body, SD_HTML);
        assert!(team
            .fallback_reason
            .as_deref()
            .is_some_and(|reason| reason.contains("anti-bot challenge")));
        assert_eq!(agent.body, AGENT_ZH);
        assert!(agent
            .fallback_reason
            .as_deref()
            .is_some_and(|reason| reason.contains("retcode -1")));
        assert_eq!(
            fs::read_to_string(root.join("zzz/prydwen/teams/sd.html")).unwrap(),
            SD_HTML
        );
        assert_eq!(
            fs::read_to_string(root.join("zzz/hoyowiki/agent/zh-cn/page-0001.json")).unwrap(),
            AGENT_ZH
        );
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn fixture_adapter_maps_all_resources_and_reports_invalid_or_missing_files() {
        let source = ZzzFixtureSupplementalSource::new(fixture_root(), fixed_time());
        for mode in [ZzzMode::Sd, ZzzMode::Da] {
            let document = source
                .fetch(ZzzSupplementalResource::PrydwenTeams { mode })
                .await
                .unwrap();
            assert_eq!(document.origin, SupplementalOrigin::Fixture);
            assert_eq!(document.source_url, team_url(mode));
            assert!(document.body.contains(&format!("fixture-{}", mode.code())));
        }
        let tier = source
            .fetch(ZzzSupplementalResource::PrydwenTier)
            .await
            .unwrap();
        assert_eq!(tier.source_url, TIER_URL);
        assert!(tier.body.contains("lastUpdated"));
        for entry_kind in [HoyowikiEntryKind::Agent, HoyowikiEntryKind::Bangboo] {
            for locale in [Locale::ZhCn, Locale::EnUs] {
                let document = source
                    .fetch(ZzzSupplementalResource::HoyowikiEntries {
                        entry_kind,
                        locale,
                        page: 1,
                    })
                    .await
                    .unwrap();
                assert_eq!(document.origin, SupplementalOrigin::Fixture);
                assert_eq!(document.source_url, HOYOWIKI_API_URL);
                assert!(document.body.contains("\"retcode\":0"));
            }
        }

        let missing = source
            .fetch(ZzzSupplementalResource::HoyowikiEntries {
                entry_kind: HoyowikiEntryKind::Bangboo,
                locale: Locale::EnUs,
                page: 2,
            })
            .await;
        assert!(
            matches!(missing, Err(MihoError::Read { path, .. }) if path.ends_with("hoyowiki/bangboo/en-us/page-0002.json"))
        );
        assert!(matches!(
            source
                .fetch(ZzzSupplementalResource::HoyowikiEntries {
                    entry_kind: HoyowikiEntryKind::Character,
                    locale: Locale::ZhCn,
                    page: 1,
                })
                .await,
            Err(MihoError::Unsupported(_))
        ));
    }
}
