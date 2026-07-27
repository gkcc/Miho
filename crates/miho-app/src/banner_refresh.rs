//! Official banner-source refresh helpers.
//!
//! This module deliberately separates network fetches from parsing and merge
//! logic. The parsers accept saved API responses, and the merge function only
//! returns a new plan snapshot; it never writes the workspace `configs/`
//! files.

use std::collections::{BTreeMap, BTreeSet};

use anyhow::{bail, Context, Result};
use chrono::{DateTime, Duration, FixedOffset, NaiveDate, NaiveDateTime};
use miho_core::network::HttpClient;
use reqwest::header::{HeaderMap, HeaderValue, ACCEPT, REFERER, USER_AGENT};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

pub const HSR_OFFICIAL_UID: &str = "288909600";
pub const HSR_USER_POST_PAGE_SIZE: usize = 50;
pub const ZZZ_OFFICIAL_APP_ID: &str = "706fd13a87294881";
pub const ZZZ_OFFICIAL_CHANNEL_ID: u64 = 273;
const ZZZ_ANNOUNCEMENT_CHANNEL_ID: u64 = 279;
const MAX_OFFICIAL_POSTS: usize = 16;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HsrOfficialPostRefV1 {
    pub post_id: String,
    pub title: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OfficialBannerCharacterV1 {
    pub name_cn: String,
    pub banner_role: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub descriptor_cn: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OfficialBannerPhaseV1 {
    pub id: String,
    pub title: String,
    pub subtitle: String,
    pub date_range: String,
    pub start_at: String,
    pub end_at: Option<String>,
    pub source_label: String,
    pub source_url: String,
    pub characters: Vec<OfficialBannerCharacterV1>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BannerRefreshMetadataV1 {
    pub fetched_at: String,
    pub source_label: String,
}

pub type BannerNameMapV1 = BTreeMap<String, String>;

#[derive(Debug, Clone)]
struct DateToken {
    end: usize,
    canonical: String,
    value: NaiveDateTime,
    has_time: bool,
}

#[derive(Debug, Clone)]
struct DateWindow {
    date_range: String,
    start_at: String,
    end_at: Option<String>,
}

pub fn hsr_user_post_url() -> String {
    format!(
        "https://bbs-api.miyoushe.com/post/wapi/userPost?uid={HSR_OFFICIAL_UID}&size={HSR_USER_POST_PAGE_SIZE}&offset=0"
    )
}

pub fn hsr_get_post_full_url(post_id: &str) -> Result<String> {
    if post_id.is_empty() || !post_id.bytes().all(|byte| byte.is_ascii_digit()) {
        bail!("invalid HSR official post id {post_id:?}");
    }
    Ok(format!(
        "https://bbs-api.miyoushe.com/post/wapi/getPostFull?gids=6&post_id={post_id}"
    ))
}

pub fn zzz_content_list_url() -> String {
    format!(
        "https://api-takumi-static.mihoyo.com/content_v2_user/app/{ZZZ_OFFICIAL_APP_ID}/getContentList?iChanId={ZZZ_OFFICIAL_CHANNEL_ID}&iPageSize=50&iPage=1&sLangKey=zh-cn"
    )
}

/// Fetches the current page of official HSR posts, follows every strict banner
/// announcement candidate through `getPostFull`, and parses official facts.
pub async fn fetch_hsr_official_banner_phases(
    http: &HttpClient,
) -> Result<Vec<OfficialBannerPhaseV1>> {
    let headers = hsr_headers();
    let list_json = http
        .get_text_with_headers(&hsr_user_post_url(), &headers)
        .await
        .context("fetch HSR official userPost")?;
    let post_refs = parse_hsr_user_post_list_json(&list_json)?;
    let mut phases = Vec::new();
    for post_ref in post_refs {
        let url = hsr_get_post_full_url(&post_ref.post_id)?;
        let post_json = http
            .get_text_with_headers(&url, &headers)
            .await
            .with_context(|| format!("fetch HSR official post {}", post_ref.post_id))?;
        let parsed = parse_hsr_get_post_full_json(&post_json)?;
        if parsed
            .iter()
            .any(|phase| phase.source_url != official_hsr_post_url(&post_ref.post_id))
        {
            bail!(
                "HSR getPostFull response did not match requested official post {}",
                post_ref.post_id
            );
        }
        phases.extend(parsed);
    }
    dedupe_official_phases(phases)
}

/// Fetches and parses the official ZZZ website's channel-273 content list.
pub async fn fetch_zzz_official_banner_phases(
    http: &HttpClient,
) -> Result<Vec<OfficialBannerPhaseV1>> {
    let json = http
        .get_text_with_headers(&zzz_content_list_url(), &zzz_headers())
        .await
        .context("fetch ZZZ official content_v2 getContentList")?;
    parse_zzz_content_list_json(&json)
}

/// Selects strict official banner-announcement references from a Miyoushe
/// `userPost` response. Non-banner posts are ignored.
pub fn parse_hsr_user_post_list_json(input: &str) -> Result<Vec<HsrOfficialPostRefV1>> {
    let root = parse_success_response(input, "HSR userPost")?;
    let list = root
        .pointer("/data/list")
        .and_then(Value::as_array)
        .context("HSR userPost data.list must be an array")?;
    let mut seen = BTreeSet::new();
    let mut output = Vec::new();
    for entry in list {
        let post = entry
            .get("post")
            .and_then(Value::as_object)
            .context("HSR userPost list entry is missing post")?;
        let Some(title) = post.get("subject").and_then(Value::as_str) else {
            continue;
        };
        if !is_hsr_banner_title(title) {
            if is_hsr_banner_like_title(title) {
                bail!("HSR userPost contained an unrecognized official banner title: {title:?}");
            }
            continue;
        }
        validate_hsr_official_post(post, "HSR userPost banner candidate")?;
        let post_id = required_nonempty_string(post, "post_id", "HSR userPost banner candidate")?;
        if !post_id.bytes().all(|byte| byte.is_ascii_digit()) {
            bail!("HSR userPost banner candidate has invalid post_id {post_id:?}");
        }
        if seen.insert(post_id.to_owned()) {
            output.push(HsrOfficialPostRefV1 {
                post_id: post_id.to_owned(),
                title: title.trim().to_owned(),
            });
        }
    }
    if output.is_empty() {
        bail!("HSR userPost contained no strict official banner announcement");
    }
    if output.len() > MAX_OFFICIAL_POSTS {
        bail!(
            "HSR userPost contained too many banner announcements: {}",
            output.len()
        );
    }
    Ok(output)
}

/// Parses one Miyoushe `getPostFull` response into one or more date-distinct
/// banner phases.
pub fn parse_hsr_get_post_full_json(input: &str) -> Result<Vec<OfficialBannerPhaseV1>> {
    let root = parse_success_response(input, "HSR getPostFull")?;
    let post = root
        .pointer("/data/post/post")
        .and_then(Value::as_object)
        .context("HSR getPostFull data.post.post must be an object")?;
    validate_hsr_official_post(post, "HSR getPostFull")?;
    let post_id = required_nonempty_string(post, "post_id", "HSR getPostFull")?;
    if !post_id.bytes().all(|byte| byte.is_ascii_digit()) {
        bail!("HSR getPostFull has invalid post_id {post_id:?}");
    }
    let title = required_nonempty_string(post, "subject", "HSR getPostFull")?;
    if !is_hsr_banner_title(title) {
        bail!("HSR getPostFull title is not a strict banner title: {title:?}");
    }
    let content = required_nonempty_string(post, "content", "HSR getPostFull")?;
    let source_url = official_hsr_post_url(post_id);
    parse_announcement_phases(
        "hsr",
        post_id,
        title,
        content,
        &format!("米游社官方：{title}"),
        &source_url,
        None,
    )
}

/// Parses strict version banner announcements from the official ZZZ
/// content-v2 channel response. New-version notices may express their start
/// as `版本更新后`; those are bound to the matching official maintenance
/// schedule instead of guessing from the announcement publication time.
pub fn parse_zzz_content_list_json(input: &str) -> Result<Vec<OfficialBannerPhaseV1>> {
    let root = parse_success_response(input, "ZZZ getContentList")?;
    let list = root
        .pointer("/data/list")
        .and_then(Value::as_array)
        .context("ZZZ getContentList data.list must be an array")?;
    let mut phases = Vec::new();
    let mut matching_titles = 0_usize;
    for item in list {
        let item = item
            .as_object()
            .context("ZZZ getContentList list item must be an object")?;
        let Some(title) = item.get("sTitle").and_then(Value::as_str) else {
            continue;
        };
        let Some(version) = zzz_banner_version(title) else {
            if is_zzz_banner_like_title(title) {
                bail!(
                    "ZZZ getContentList contained an unrecognized official banner title: {title:?}"
                );
            }
            continue;
        };
        matching_titles += 1;
        let channels = item
            .get("sChanId")
            .and_then(Value::as_array)
            .context("ZZZ banner item sChanId must be an array")?;
        if !channels.iter().any(|value| {
            value.as_u64() == Some(ZZZ_ANNOUNCEMENT_CHANNEL_ID)
                || value.as_str().and_then(|value| value.parse::<u64>().ok())
                    == Some(ZZZ_ANNOUNCEMENT_CHANNEL_ID)
        }) {
            bail!(
                "ZZZ banner item {title:?} is not in official announcement channel {}",
                ZZZ_ANNOUNCEMENT_CHANNEL_ID
            );
        }
        let info_id = item
            .get("iInfoId")
            .and_then(value_as_positive_id)
            .context("ZZZ banner item requires a positive iInfoId")?;
        let intro = item.get("sIntro").and_then(Value::as_str).unwrap_or("");
        let content = item.get("sContent").and_then(Value::as_str).unwrap_or("");
        if intro.trim().is_empty() && content.trim().is_empty() {
            bail!("ZZZ banner item {title:?} has no announcement content");
        }
        let combined = format!("{intro}\n{content}");
        let version_update_at = if combined.contains("版本更新后") {
            Some(find_zzz_version_update_completion(list, &version)?)
        } else {
            None
        };
        let source_url = format!("https://zzz.mihoyo.com/news/{info_id}");
        phases.extend(parse_announcement_phases(
            "zzz",
            &info_id,
            title,
            &combined,
            &format!("《绝区零》官方网站：{title}"),
            &source_url,
            version_update_at,
        )?);
    }
    if matching_titles == 0 {
        bail!("ZZZ getContentList contained no strict official banner announcement");
    }
    dedupe_official_phases(phases)
}

/// Merges official facts into a prior banner plan and returns a pretty JSON
/// snapshot. No filesystem writes occur.
///
/// `name_map` must be the current export bundle's Chinese-name-to-canonical-
/// slug map. New official characters that cannot be resolved fail closed.
pub fn merge_banner_plan_snapshot(
    existing_plan_json: &[u8],
    official_phases: &[OfficialBannerPhaseV1],
    name_map: &BannerNameMapV1,
    refresh: &BannerRefreshMetadataV1,
) -> Result<Vec<u8>> {
    if official_phases.is_empty() {
        bail!("cannot merge an empty official banner refresh");
    }
    let fetched_at = parse_refresh_time(&refresh.fetched_at)?;
    if refresh.source_label.trim().is_empty() {
        bail!("banner refresh source_label must not be empty");
    }
    let mut root: Value =
        serde_json::from_slice(existing_plan_json).context("parse existing banner plan JSON")?;
    let root_object = root
        .as_object_mut()
        .context("existing banner plan root must be an object")?;
    let phases = root_object
        .entry("phases")
        .or_insert_with(|| Value::Array(Vec::new()))
        .as_array_mut()
        .context("existing banner plan phases must be an array")?;

    let existing_character_index = index_existing_characters(phases);
    let official_phases = dedupe_official_phases(official_phases.to_vec())?;
    let official_statuses = official_phases
        .iter()
        .map(|phase| official_phase_status(phase, fetched_at))
        .collect::<Vec<_>>();
    let official_current_phase_count = official_statuses
        .iter()
        .filter(|status| **status == "current")
        .count();
    let official_next_phase_count = official_statuses
        .iter()
        .filter(|status| **status == "next")
        .count();
    let refresh_status = if official_current_phase_count > 0 || official_next_phase_count > 0 {
        "fresh"
    } else {
        "no_current"
    };
    let official_phase_count = official_phases.len();
    let mut used_existing = BTreeSet::new();
    let mut confirmed_slugs = BTreeSet::new();
    for official in &official_phases {
        validate_official_phase(official)?;
        let resolved_characters =
            resolve_official_characters(official, name_map, &existing_character_index)?;
        confirmed_slugs.extend(
            resolved_characters
                .iter()
                .filter_map(|character| character.get("slug").and_then(Value::as_str))
                .map(str::to_owned),
        );
        let match_index =
            find_matching_phase(phases, official, &resolved_characters, &used_existing);
        let status = official_phase_status(official, fetched_at);
        let merged = if let Some(index) = match_index {
            used_existing.insert(index);
            merge_one_phase(phases[index].clone(), official, resolved_characters, status)?
        } else {
            merge_one_phase(
                Value::Object(Map::new()),
                official,
                resolved_characters,
                status,
            )?
        };
        if let Some(index) = match_index {
            phases[index] = merged;
        } else {
            let index = phases.len();
            phases.push(merged);
            // A phase added by this same official response is not an existing
            // baseline candidate for a later phase. Shared rerun/support UP
            // characters must not let one newly announced pool replace
            // another pool from the same source.
            used_existing.insert(index);
        }
    }
    refresh_dated_phase_statuses(phases, fetched_at);
    remove_promoted_satellites(phases, &confirmed_slugs);
    dedupe_plan_phases(phases);

    append_root_sources(root_object, &official_phases)?;
    root_object.insert(
        "refresh".to_owned(),
        json!({
            "status": refresh_status,
            "fetched_at": refresh.fetched_at,
            "source_label": refresh.source_label,
            "official_phase_count": official_phase_count,
            "official_current_phase_count": official_current_phase_count,
            "official_next_phase_count": official_next_phase_count,
        }),
    );
    root_object.insert(
        "updated_at".to_owned(),
        Value::String(fetched_at.date().format("%Y-%m-%d").to_string()),
    );
    serde_json::to_vec_pretty(&root).context("serialize merged banner plan snapshot")
}

fn hsr_headers() -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static("Mozilla/5.0 miho-endgame/0.1"),
    );
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(
        REFERER,
        HeaderValue::from_static("https://www.miyoushe.com/"),
    );
    headers.insert("x-rpc-client_type", HeaderValue::from_static("4"));
    headers.insert("x-rpc-app_version", HeaderValue::from_static("2.89.1"));
    headers
}

fn zzz_headers() -> HeaderMap {
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static("Mozilla/5.0 miho-endgame/0.1"),
    );
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(
        REFERER,
        HeaderValue::from_static("https://zzz.mihoyo.com/news"),
    );
    headers
}

fn parse_success_response(input: &str, label: &str) -> Result<Value> {
    let root: Value = serde_json::from_str(input).with_context(|| format!("parse {label} JSON"))?;
    let retcode = root
        .get("retcode")
        .and_then(Value::as_i64)
        .with_context(|| format!("{label} retcode must be an integer"))?;
    if retcode != 0 {
        let message = root.get("message").and_then(Value::as_str).unwrap_or("");
        bail!("{label} returned retcode {retcode}: {message}");
    }
    Ok(root)
}

fn validate_hsr_official_post(post: &Map<String, Value>, label: &str) -> Result<()> {
    let uid = required_nonempty_string(post, "uid", label)?;
    if uid != HSR_OFFICIAL_UID {
        bail!("{label} has unexpected uid {uid:?}");
    }
    if post
        .get("post_status")
        .and_then(Value::as_object)
        .and_then(|status| status.get("is_official"))
        .and_then(Value::as_bool)
        != Some(true)
    {
        bail!("{label} is not marked official");
    }
    Ok(())
}

fn required_nonempty_string<'a>(
    object: &'a Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<&'a str> {
    object
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .with_context(|| format!("{label} requires non-empty {key}"))
}

fn value_as_positive_id(value: &Value) -> Option<String> {
    if let Some(value) = value.as_u64().filter(|value| *value > 0) {
        return Some(value.to_string());
    }
    value
        .as_str()
        .filter(|value| !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit()))
        .filter(|value| value.bytes().any(|byte| byte != b'0'))
        .map(str::to_owned)
}

fn official_hsr_post_url(post_id: &str) -> String {
    format!("https://www.miyoushe.com/sr/article/{post_id}")
}

fn is_hsr_banner_title(title: &str) -> bool {
    let compact = remove_whitespace(title);
    if compact.ends_with("联动跃迁说明") {
        return compact
            .strip_suffix("联动跃迁说明")
            .is_some_and(|prefix| !prefix.is_empty());
    }
    let Some(version) = compact.strip_suffix("版本活动跃迁（其一）").or_else(|| {
        compact
            .strip_suffix("版本活动跃迁（其二）")
            .or_else(|| compact.strip_suffix("版本活动跃迁（其三）"))
    }) else {
        return false;
    };
    is_version_number(version)
}

fn is_hsr_banner_like_title(title: &str) -> bool {
    let compact = remove_whitespace(title);
    compact.contains("版本活动跃迁") || compact.contains("联动跃迁说明")
}

fn zzz_banner_version(title: &str) -> Option<String> {
    let compact = remove_whitespace(title);
    let Some(version) = compact
        .strip_suffix("版本限时频段（上期）")
        .or_else(|| compact.strip_suffix("版本限时频段（下期）"))
        .or_else(|| compact.strip_suffix("版本限时频段"))
    else {
        return None;
    };
    is_version_number(version).then(|| version.to_owned())
}

fn is_zzz_banner_like_title(title: &str) -> bool {
    remove_whitespace(title).contains("版本限时频段")
}

fn find_zzz_version_update_completion(list: &[Value], version: &str) -> Result<NaiveDateTime> {
    let expected_prefix = format!("{version}版本");
    let mut completions = BTreeSet::new();
    for item in list {
        let item = item
            .as_object()
            .context("ZZZ getContentList list item must be an object")?;
        let Some(title) = item.get("sTitle").and_then(Value::as_str) else {
            continue;
        };
        let compact_title = remove_whitespace(title);
        if !compact_title.starts_with(&expected_prefix) || !compact_title.contains("更新通知") {
            continue;
        }
        let intro = item.get("sIntro").and_then(Value::as_str).unwrap_or("");
        let content = item.get("sContent").and_then(Value::as_str).unwrap_or("");
        if intro.trim().is_empty() && content.trim().is_empty() {
            bail!("ZZZ {version} update notice has no content");
        }
        completions.insert(parse_zzz_version_update_completion(&format!(
            "{intro}\n{content}"
        ))?);
    }
    match completions.len() {
        1 => Ok(*completions.iter().next().unwrap()),
        0 => {
            bail!("ZZZ {version} version-relative banner has no matching official update schedule")
        }
        _ => bail!("ZZZ {version} official update schedules disagree"),
    }
}

fn parse_zzz_version_update_completion(raw_content: &str) -> Result<NaiveDateTime> {
    let text = strip_html(raw_content);
    let marker = text
        .find("【版本更新时间】")
        .map(|index| index + "【版本更新时间】".len())
        .or_else(|| {
            text.find("版本更新时间")
                .map(|index| index + "版本更新时间".len())
        })
        .context("ZZZ official update notice has no version update time section")?;
    let remaining = &text[marker..];
    let section = remaining
        .find('【')
        .and_then(|end| remaining.get(..end))
        .unwrap_or(remaining);
    if !section.contains("开始") || !section.contains("预计需要") {
        bail!("ZZZ official update notice has no bounded maintenance schedule");
    }
    let dates = scan_date_tokens(section);
    if dates.len() != 1 || !dates[0].has_time {
        bail!("ZZZ official update notice has an invalid maintenance start");
    }
    let compact = remove_whitespace(section);
    let duration = compact
        .split_once("预计需要")
        .map(|(_, suffix)| suffix)
        .context("ZZZ official update notice has no maintenance duration")?;
    let digit_count = duration.bytes().take_while(u8::is_ascii_digit).count();
    if digit_count == 0
        || !duration[digit_count..].starts_with("个小时")
            && !duration[digit_count..].starts_with("小时")
    {
        bail!("ZZZ official update notice has an unsupported maintenance duration");
    }
    let hours = duration[..digit_count]
        .parse::<i64>()
        .context("parse ZZZ official maintenance duration")?;
    if !(1..=24).contains(&hours) {
        bail!("ZZZ official maintenance duration is outside the supported range");
    }
    dates[0]
        .value
        .checked_add_signed(Duration::hours(hours))
        .context("ZZZ official update completion overflowed")
}

fn is_version_number(value: &str) -> bool {
    let Some((major, minor)) = value.split_once('.') else {
        return false;
    };
    !major.is_empty()
        && !minor.is_empty()
        && major.bytes().all(|byte| byte.is_ascii_digit())
        && minor.bytes().all(|byte| byte.is_ascii_digit())
}

fn parse_announcement_phases(
    game: &str,
    source_id: &str,
    title: &str,
    raw_content: &str,
    source_label: &str,
    source_url: &str,
    version_update_at: Option<NaiveDateTime>,
) -> Result<Vec<OfficialBannerPhaseV1>> {
    let text = strip_html(raw_content);
    let segments = split_segments(&text);
    let mut windows: BTreeMap<String, (DateWindow, Vec<OfficialBannerCharacterV1>)> =
        BTreeMap::new();
    let mut malformed_relevant_segment = None;
    for (index, segment) in segments.iter().enumerate() {
        if !is_banner_date_segment(segment) {
            continue;
        }
        match parse_date_window(segment, version_update_at) {
            Ok(window) => {
                let mut roles = extract_role_mentions(segment);
                if roles.is_empty() {
                    for following in segments.iter().skip(index + 1) {
                        if is_banner_date_segment(following)
                            || announcement_fact_prefix(following).len() != following.len()
                        {
                            break;
                        }
                        merge_character_facts(&mut roles, &extract_role_mentions(following));
                    }
                }
                windows
                    .entry(window.date_range.clone())
                    .and_modify(|(_, existing)| merge_character_facts(existing, &roles))
                    .or_insert((window, roles));
            }
            Err(error) => malformed_relevant_segment = Some(error.to_string()),
        }
    }
    if windows.is_empty() {
        if let Some(error) = malformed_relevant_segment {
            bail!("{game} banner {title:?} has malformed official date: {error}");
        }
        bail!("{game} banner {title:?} has no official banner date");
    }
    if let Some(error) = malformed_relevant_segment {
        bail!("{game} banner {title:?} has malformed official date: {error}");
    }

    if windows.len() == 1 {
        let (_, roles) = windows.values_mut().next().unwrap();
        if roles.is_empty() {
            *roles = extract_role_mentions(announcement_fact_prefix(&text));
        }
    }
    if windows.values().any(|(_, roles)| roles.is_empty()) {
        bail!("{game} banner {title:?} has a dated phase without an UP character");
    }

    let count = windows.len();
    let mut output = Vec::with_capacity(count);
    for (index, (_, (window, characters))) in windows.into_iter().enumerate() {
        let suffix = if count > 1 {
            format!(" · 官方日期组 {}", index + 1)
        } else {
            " · 官方公告".to_owned()
        };
        let phase = OfficialBannerPhaseV1 {
            id: format!("{game}-official-{source_id}-{}", index + 1),
            title: title.trim().to_owned(),
            subtitle: suffix.trim_start_matches(" · ").to_owned(),
            date_range: window.date_range,
            start_at: window.start_at,
            end_at: window.end_at,
            source_label: source_label.to_owned(),
            source_url: source_url.to_owned(),
            characters,
        };
        validate_official_phase(&phase)?;
        output.push(phase);
    }
    Ok(output)
}

fn is_banner_date_segment(segment: &str) -> bool {
    segment.contains("跃迁时间")
        || ((segment.contains("调频活动时间")
            || segment.contains("活动时间")
            || segment.contains("版本更新后"))
            && !scan_date_tokens(segment).is_empty())
        || (segment.contains("联动跃迁")
            && segment.contains("长期开放")
            && !scan_date_tokens(segment).is_empty())
}

fn parse_date_window(
    segment: &str,
    version_update_at: Option<NaiveDateTime>,
) -> Result<DateWindow> {
    let dates = scan_date_tokens(segment);
    for date in &dates {
        if !date.has_time
            && segment[date.end..]
                .chars()
                .next()
                .is_some_and(|character| character.is_ascii_digit() || character == '：')
        {
            bail!("official date has an invalid or unsupported attached time");
        }
    }
    if dates.len() > 2 {
        bail!("official date sentence contains more than one date range");
    }
    if dates.len() >= 2 {
        let start = &dates[0];
        let end = &dates[1];
        if end.value < start.value {
            bail!(
                "official date range ends before it starts: {} -> {}",
                start.canonical,
                end.canonical
            );
        }
        return Ok(DateWindow {
            date_range: format!("{} 至 {}", start.canonical, end.canonical),
            start_at: start.canonical.clone(),
            end_at: Some(end.canonical.clone()),
        });
    }
    if dates.len() == 1 && segment.contains("长期开放") {
        return Ok(DateWindow {
            date_range: format!("{} 后长期开放", dates[0].canonical),
            start_at: dates[0].canonical.clone(),
            end_at: None,
        });
    }
    if dates.len() == 1 && segment.contains("版本更新后") {
        let start = version_update_at
            .context("version-relative official banner date has no trusted update completion")?;
        let end = &dates[0];
        if end.value < start {
            bail!(
                "official version-relative date range ends before it starts: {} -> {}",
                start.format("%Y-%m-%d %H:%M"),
                end.canonical
            );
        }
        let start_at = start.format("%Y-%m-%d %H:%M").to_string();
        return Ok(DateWindow {
            date_range: format!("{} 至 {}", start_at, end.canonical),
            start_at,
            end_at: Some(end.canonical.clone()),
        });
    }
    bail!("expected a complete date range or one long-term-open date")
}

fn scan_date_tokens(text: &str) -> Vec<DateToken> {
    let mut output = Vec::new();
    let mut consumed_until = 0_usize;
    for (index, character) in text.char_indices() {
        if index < consumed_until || !character.is_ascii_digit() {
            continue;
        }
        let Some(date_text) = text.get(index..index.saturating_add(10)) else {
            continue;
        };
        let bytes = date_text.as_bytes();
        if bytes.len() != 10
            || !bytes[0..4].iter().all(u8::is_ascii_digit)
            || !matches!(bytes[4], b'/' | b'-')
            || bytes[7] != bytes[4]
            || !bytes[5..7].iter().all(u8::is_ascii_digit)
            || !bytes[8..10].iter().all(u8::is_ascii_digit)
        {
            continue;
        }
        let normalized = date_text.replace('/', "-");
        let Ok(date) = NaiveDate::parse_from_str(&normalized, "%Y-%m-%d") else {
            continue;
        };
        let mut end = index + 10;
        while text
            .as_bytes()
            .get(end)
            .is_some_and(|byte| byte.is_ascii_whitespace())
        {
            end += 1;
        }
        let mut canonical = normalized;
        let mut value = date.and_hms_opt(0, 0, 0).unwrap();
        let mut has_time = false;
        if let Some(time_text) = text.get(end..end.saturating_add(5)) {
            let time = time_text.as_bytes();
            if time.len() == 5
                && time[0..2].iter().all(u8::is_ascii_digit)
                && time[2] == b':'
                && time[3..5].iter().all(u8::is_ascii_digit)
            {
                let hour = time_text[0..2].parse::<u32>().ok();
                let minute = time_text[3..5].parse::<u32>().ok();
                if let (Some(hour), Some(minute)) = (hour, minute) {
                    if let Some(date_time) = date.and_hms_opt(hour, minute, 0) {
                        canonical = format!("{} {time_text}", canonical);
                        value = date_time;
                        end += 5;
                        has_time = true;
                    }
                }
            }
        }
        output.push(DateToken {
            end,
            canonical,
            value,
            has_time,
        });
        consumed_until = end;
    }
    output
}

fn extract_role_mentions(text: &str) -> Vec<OfficialBannerCharacterV1> {
    let mut tokens = Vec::new();
    for (open, close) in [('「', '」'), ('[', ']'), ('【', '】')] {
        let mut remainder = text;
        let mut offset = 0_usize;
        while let Some(open_index) = remainder.find(open) {
            let content_start = open_index + open.len_utf8();
            let Some(relative_close) = remainder[content_start..].find(close) else {
                break;
            };
            let close_index = content_start + relative_close;
            let inner = remainder[content_start..close_index].trim();
            let global_open = offset + open_index;
            if let Some(character) = classify_role_token(text, global_open, inner) {
                tokens.push(character);
            }
            let advance = close_index + close.len_utf8();
            offset += advance;
            remainder = &remainder[advance..];
        }
    }
    let mut seen = BTreeSet::new();
    tokens
        .into_iter()
        .filter(|character| seen.insert(normalize_cn_name(&character.name_cn)))
        .collect()
}

fn announcement_fact_prefix(text: &str) -> &str {
    [
        "活动跃迁详细规则",
        "联动跃迁详细说明",
        "调频详情",
        "※详细信息",
    ]
    .iter()
    .filter_map(|marker| text.find(marker))
    .min()
    .and_then(|end| text.get(..end))
    .unwrap_or(text)
}

fn classify_role_token(
    full_text: &str,
    token_start: usize,
    inner: &str,
) -> Option<OfficialBannerCharacterV1> {
    let (parenthesis, open_parenthesis, close_parenthesis) = if let Some(index) = inner.find('（')
    {
        (index, '（', '）')
    } else {
        (inner.find('(')?, '(', ')')
    };
    let name = inner[..parenthesis]
        .trim()
        .trim_matches(['「', '」', '[', ']', '【', '】']);
    if name.is_empty() {
        return None;
    }
    let context = remove_whitespace(&tail_chars(&full_text[..token_start], 120));
    let (role_marker, role_position, banner_role) = [
        ("联动限定5星角色", "联动限定 5 星 UP"),
        ("限定5星角色", "限定 5 星 UP"),
        ("5星角色", "5 星 UP"),
        ("4星角色", "4 星 UP"),
        ("限定S级代理人", "限定 S 级 UP"),
        ("S级代理人", "S 级 UP"),
        ("A级代理人", "A 级 UP"),
    ]
    .into_iter()
    .filter_map(|(marker, label)| {
        context
            .rfind(marker)
            .map(|position| (marker, position, label))
    })
    .max_by_key(|(marker, position, _)| (position + marker.len(), marker.len()))?;
    let equipment = last_marker(&context, &["光锥", "音擎"]);
    if equipment.is_some_and(|(_, position)| position > role_position) {
        return None;
    }
    debug_assert!(context[role_position..].starts_with(role_marker));
    Some(OfficialBannerCharacterV1 {
        name_cn: name.to_owned(),
        banner_role: banner_role.to_owned(),
        descriptor_cn: Some(
            inner[parenthesis + open_parenthesis.len_utf8()..]
                .trim()
                .trim_end_matches(close_parenthesis)
                .trim()
                .to_owned(),
        )
        .filter(|value| !value.is_empty()),
    })
}

fn last_marker<'a>(text: &str, markers: &'a [&'a str]) -> Option<(&'a str, usize)> {
    markers
        .iter()
        .filter_map(|marker| text.rfind(marker).map(|position| (*marker, position)))
        .max_by_key(|(_, position)| *position)
}

fn merge_character_facts(
    target: &mut Vec<OfficialBannerCharacterV1>,
    additional: &[OfficialBannerCharacterV1],
) {
    let mut seen = target
        .iter()
        .map(|character| normalize_cn_name(&character.name_cn))
        .collect::<BTreeSet<_>>();
    for character in additional {
        if seen.insert(normalize_cn_name(&character.name_cn)) {
            target.push(character.clone());
        }
    }
}

fn strip_html(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut in_tag = false;
    let mut tag = String::new();
    for character in value.chars() {
        match character {
            '<' if !in_tag => {
                in_tag = true;
                tag.clear();
            }
            '>' if in_tag => {
                in_tag = false;
                if is_html_segment_boundary_tag(&tag) {
                    output.push('\n');
                }
            }
            _ if in_tag => tag.push(character),
            _ if !in_tag => output.push(character),
            _ => {}
        }
    }
    output
        .replace("&nbsp;", " ")
        .replace("&#160;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
}

fn is_html_segment_boundary_tag(raw_tag: &str) -> bool {
    let tag = raw_tag
        .trim_start()
        .trim_start_matches('/')
        .split(|character: char| character.is_whitespace() || character == '/')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    matches!(
        tag.as_str(),
        "p" | "div"
            | "br"
            | "li"
            | "ul"
            | "ol"
            | "h1"
            | "h2"
            | "h3"
            | "h4"
            | "h5"
            | "h6"
            | "section"
            | "article"
            | "table"
            | "thead"
            | "tbody"
            | "tfoot"
            | "tr"
            | "td"
            | "th"
    )
}

fn split_segments(value: &str) -> Vec<String> {
    value
        .split(['。', '！', '!', '\n', '\r'])
        .map(collapse_whitespace)
        .filter(|segment| !segment.is_empty())
        .collect()
}

fn collapse_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn remove_whitespace(value: &str) -> String {
    value
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect()
}

fn tail_chars(value: &str, limit: usize) -> String {
    let mut reversed = value.chars().rev().take(limit).collect::<Vec<_>>();
    reversed.reverse();
    reversed.into_iter().collect()
}

fn normalize_cn_name(value: &str) -> String {
    value
        .chars()
        .filter(|character| {
            !character.is_whitespace()
                && !matches!(
                    character,
                    '·' | '•' | '・' | '‧' | '.' | '-' | '—' | '_' | '「' | '」' | '[' | ']'
                )
        })
        .flat_map(char::to_lowercase)
        .collect()
}

fn dedupe_official_phases(
    phases: Vec<OfficialBannerPhaseV1>,
) -> Result<Vec<OfficialBannerPhaseV1>> {
    let mut output: Vec<OfficialBannerPhaseV1> = Vec::new();
    for phase in phases {
        validate_official_phase(&phase)?;
        let duplicate_index = output.iter().position(|existing| {
            let same_date = normalize_date_range(&existing.date_range)
                == normalize_date_range(&phase.date_range);
            let same_source = existing.source_url.eq_ignore_ascii_case(&phase.source_url);
            let same_title = remove_whitespace(&existing.title) == remove_whitespace(&phase.title);
            same_date && (same_source || same_title)
        });
        if let Some(index) = duplicate_index {
            merge_character_facts(&mut output[index].characters, &phase.characters);
        } else {
            output.push(phase);
        }
    }
    if output.is_empty() {
        bail!("official banner response produced no phases");
    }
    Ok(output)
}

fn validate_official_phase(phase: &OfficialBannerPhaseV1) -> Result<()> {
    if phase.id.trim().is_empty()
        || phase.title.trim().is_empty()
        || phase.date_range.trim().is_empty()
        || phase.start_at.trim().is_empty()
        || phase.source_label.trim().is_empty()
        || phase.source_url.trim().is_empty()
    {
        bail!("official banner phase contains an empty required field");
    }
    if !(phase
        .source_url
        .starts_with("https://www.miyoushe.com/sr/article/")
        || phase.source_url.starts_with("https://zzz.mihoyo.com/news/"))
    {
        bail!(
            "official banner phase has an unsupported source URL: {}",
            phase.source_url
        );
    }
    let start = parse_canonical_date_time(&phase.start_at, false)
        .with_context(|| format!("invalid phase start_at {}", phase.start_at))?;
    if let Some(end_at) = phase.end_at.as_deref() {
        let end = parse_canonical_date_time(end_at, true)
            .with_context(|| format!("invalid phase end_at {end_at}"))?;
        if end < start {
            bail!("official banner phase ends before it starts");
        }
        let expected = format!("{} 至 {}", phase.start_at, end_at);
        if phase.date_range != expected {
            bail!("official banner phase date_range does not match start/end");
        }
    } else if phase.date_range != format!("{} 后长期开放", phase.start_at) {
        bail!("official long-term banner date_range does not match start_at");
    }
    if phase.characters.is_empty() {
        bail!("official banner phase requires at least one UP character");
    }
    let mut names = BTreeSet::new();
    for character in &phase.characters {
        if character.name_cn.trim().is_empty() || character.banner_role.trim().is_empty() {
            bail!("official banner character contains an empty required field");
        }
        if !names.insert(normalize_cn_name(&character.name_cn)) {
            bail!(
                "official banner phase contains duplicate character {}",
                character.name_cn
            );
        }
    }
    Ok(())
}

fn index_existing_characters(phases: &[Value]) -> BTreeMap<String, Value> {
    let mut output = BTreeMap::new();
    for phase in phases {
        let Some(characters) = phase.get("characters").and_then(Value::as_array) else {
            continue;
        };
        for character in characters {
            let Some(slug) = character.get("slug").and_then(Value::as_str) else {
                continue;
            };
            if is_valid_slug(slug) {
                output
                    .entry(slug.to_owned())
                    .and_modify(|existing: &mut Value| {
                        merge_character_metadata(existing, character);
                    })
                    .or_insert_with(|| character.clone());
            }
        }
    }
    output
}

fn merge_character_metadata(existing: &mut Value, additional: &Value) {
    let (Some(existing_object), Some(additional_object)) =
        (existing.as_object(), additional.as_object())
    else {
        return;
    };
    let mut merged = if additional_object.len() > existing_object.len() {
        additional_object.clone()
    } else {
        existing_object.clone()
    };
    let fallback = if additional_object.len() > existing_object.len() {
        existing_object
    } else {
        additional_object
    };
    for (key, value) in fallback {
        merged.entry(key.clone()).or_insert_with(|| value.clone());
    }
    *existing = Value::Object(merged);
}

fn resolve_official_characters(
    phase: &OfficialBannerPhaseV1,
    name_map: &BannerNameMapV1,
    existing_character_index: &BTreeMap<String, Value>,
) -> Result<Vec<Value>> {
    let normalized_map = name_map
        .iter()
        .map(|(name, slug)| (normalize_cn_name(name), slug.to_owned()))
        .chain(
            existing_character_index
                .iter()
                .filter_map(|(slug, character)| {
                    let name = character.get("name_cn").and_then(Value::as_str)?;
                    let normalized = normalize_cn_name(name);
                    (!normalized.is_empty()).then(|| (normalized, slug.to_owned()))
                }),
        )
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let mut output = Vec::new();
    let mut slugs = BTreeSet::new();
    for official in &phase.characters {
        let needle = normalize_cn_name(&official.name_cn);
        let exact_candidates = normalized_map
            .iter()
            .filter(|(name, _)| name == &needle)
            .map(|(_, slug)| slug.as_str())
            .collect::<BTreeSet<_>>();
        let mut candidates = if exact_candidates.is_empty() {
            normalized_map
                .iter()
                .filter(|(name, _)| name.starts_with(&needle))
                .map(|(_, slug)| slug.as_str())
                .collect::<BTreeSet<_>>()
        } else {
            exact_candidates
        };
        if candidates.len() > 1 {
            let descriptor_terms = official
                .descriptor_cn
                .as_deref()
                .into_iter()
                .flat_map(|descriptor| descriptor.split(['•', '·', '・', '/', '、', ' ']))
                .map(normalize_cn_name)
                .filter(|term| !term.is_empty())
                .collect::<Vec<_>>();
            let hinted = normalized_map
                .iter()
                .filter(|(name, slug)| {
                    candidates.contains(slug.as_str())
                        && descriptor_terms.iter().any(|term| name.contains(term))
                })
                .map(|(_, slug)| slug.as_str())
                .collect::<BTreeSet<_>>();
            if !hinted.is_empty() {
                candidates = hinted;
            }
        }
        if candidates.len() != 1 {
            if candidates.is_empty() {
                bail!(
                    "official character {:?} is missing from the current bundle name_map",
                    official.name_cn
                );
            }
            bail!(
                "official character {:?} resolves to multiple canonical slugs: {:?}",
                official.name_cn,
                candidates
            );
        }
        let slug = *candidates.iter().next().unwrap();
        if !is_valid_slug(slug) {
            bail!(
                "official character {:?} resolved to invalid slug {slug:?}",
                official.name_cn
            );
        }
        if !slugs.insert(slug.to_owned()) {
            bail!("multiple official character names resolved to slug {slug:?}");
        }
        let mut character = existing_character_index
            .get(slug)
            .cloned()
            .unwrap_or_else(|| Value::Object(Map::new()));
        let object = character
            .as_object_mut()
            .context("existing banner character must be an object")?;
        object.insert("slug".to_owned(), Value::String(slug.to_owned()));
        object
            .entry("name_cn")
            .or_insert_with(|| Value::String(official.name_cn.clone()));
        object.insert(
            "banner_role".to_owned(),
            Value::String(official.banner_role.clone()),
        );
        output.push(character);
    }
    Ok(output)
}

fn is_valid_slug(slug: &str) -> bool {
    !slug.is_empty()
        && !slug.starts_with('-')
        && !slug.ends_with('-')
        && slug
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
}

fn find_matching_phase(
    phases: &[Value],
    official: &OfficialBannerPhaseV1,
    resolved_characters: &[Value],
    used: &BTreeSet<usize>,
) -> Option<usize> {
    let incoming_slugs = resolved_characters
        .iter()
        .filter_map(|character| character.get("slug").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let incoming_anchor_slugs = official
        .characters
        .iter()
        .zip(resolved_characters)
        .filter(|(official, _)| is_anchor_banner_role(&official.banner_role))
        .filter_map(|(_, character)| character.get("slug").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    phases
        .iter()
        .enumerate()
        .filter(|(index, _)| !used.contains(index))
        .filter_map(|(index, phase)| {
            if phase.get("status").and_then(Value::as_str) == Some("satellite") {
                return None;
            }
            let source_match = phase.get("source_url").and_then(Value::as_str)
                == Some(official.source_url.as_str());
            let date_match = phase
                .get("date_range")
                .and_then(Value::as_str)
                .is_some_and(|date| {
                    normalize_date_range(date) == normalize_date_range(&official.date_range)
                });
            let title_match = phase
                .get("title")
                .and_then(Value::as_str)
                .is_some_and(|title| {
                    remove_whitespace(title) == remove_whitespace(&official.title)
                });
            let version_match =
                phase_version_key(phase.get("title").and_then(Value::as_str).unwrap_or(""))
                    .is_some_and(|version| {
                        phase_version_key(&official.title).as_deref() == Some(version.as_str())
                    });
            let existing_slugs = phase
                .get("characters")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|character| character.get("slug").and_then(Value::as_str))
                .collect::<BTreeSet<_>>();
            let overlap = incoming_slugs.intersection(&existing_slugs).count();
            let anchor_overlap = incoming_anchor_slugs.intersection(&existing_slugs).count();
            let eligible = (source_match && date_match)
                || (date_match && overlap > 0)
                || (source_match && anchor_overlap > 0)
                || (version_match && anchor_overlap > 0);
            if !eligible {
                return None;
            }
            let score = usize::from(source_match) * 100
                + usize::from(date_match) * 80
                + usize::from(title_match) * 40
                + usize::from(version_match) * 20
                + anchor_overlap * 40
                + overlap * 5;
            Some((score, index))
        })
        .max_by_key(|(score, index)| (*score, usize::MAX - *index))
        .map(|(_, index)| index)
}

fn remove_promoted_satellites(phases: &mut Vec<Value>, confirmed_slugs: &BTreeSet<String>) {
    for phase in phases.iter_mut() {
        if phase.get("status").and_then(Value::as_str) != Some("satellite") {
            continue;
        }
        if let Some(characters) = phase.get_mut("characters").and_then(Value::as_array_mut) {
            characters.retain(|character| {
                character
                    .get("slug")
                    .and_then(Value::as_str)
                    .is_none_or(|slug| !confirmed_slugs.contains(slug))
            });
        }
    }
    phases.retain(|phase| {
        phase.get("status").and_then(Value::as_str) != Some("satellite")
            || phase
                .get("characters")
                .and_then(Value::as_array)
                .is_some_and(|characters| !characters.is_empty())
    });
}

fn is_anchor_banner_role(role: &str) -> bool {
    let compact = remove_whitespace(role);
    compact.contains("5星") || compact.contains("S级")
}

fn phase_version_key(title: &str) -> Option<String> {
    let compact = remove_whitespace(title);
    let mut end = 0_usize;
    let mut seen_dot = false;
    for (index, character) in compact.char_indices() {
        if character.is_ascii_digit() {
            end = index + character.len_utf8();
        } else if character == '.' && !seen_dot && end > 0 {
            seen_dot = true;
            end = index + 1;
        } else {
            break;
        }
    }
    let version = compact.get(..end)?;
    (seen_dot && is_version_number(version)).then(|| version.to_owned())
}

fn merge_one_phase(
    prior: Value,
    official: &OfficialBannerPhaseV1,
    characters: Vec<Value>,
    status: &str,
) -> Result<Value> {
    let mut object = prior
        .as_object()
        .cloned()
        .context("existing banner phase must be an object")?;
    object
        .entry("id")
        .or_insert_with(|| Value::String(official.id.clone()));
    object
        .entry("title")
        .or_insert_with(|| Value::String(official.title.clone()));
    object
        .entry("subtitle")
        .or_insert_with(|| Value::String(official.subtitle.clone()));
    object.insert("status".to_owned(), Value::String(status.to_owned()));
    object.insert(
        "date_range".to_owned(),
        Value::String(official.date_range.clone()),
    );
    object.insert(
        "source_label".to_owned(),
        Value::String(official.source_label.clone()),
    );
    object.insert(
        "source_url".to_owned(),
        Value::String(official.source_url.clone()),
    );
    object.insert("characters".to_owned(), Value::Array(characters));
    Ok(Value::Object(object))
}

fn official_phase_status(phase: &OfficialBannerPhaseV1, fetched_at: NaiveDateTime) -> &'static str {
    let start = parse_canonical_date_time(&phase.start_at, false).unwrap();
    if fetched_at < start {
        return "next";
    }
    if let Some(end_at) = phase.end_at.as_deref() {
        let end = parse_canonical_date_time(end_at, true).unwrap();
        if fetched_at > end {
            return "previous";
        }
    }
    "current"
}

fn refresh_dated_phase_statuses(phases: &mut [Value], fetched_at: NaiveDateTime) {
    for phase in phases {
        if phase.get("status").and_then(Value::as_str) == Some("satellite") {
            continue;
        }
        let Some(date_range) = phase.get("date_range").and_then(Value::as_str) else {
            continue;
        };
        let Some(status) = phase_status_from_date_range(date_range, fetched_at) else {
            continue;
        };
        if let Some(object) = phase.as_object_mut() {
            object.insert("status".to_owned(), Value::String(status.to_owned()));
        }
    }
}

fn phase_status_from_date_range(
    date_range: &str,
    fetched_at: NaiveDateTime,
) -> Option<&'static str> {
    let dates = scan_date_tokens(date_range);
    match dates.as_slice() {
        [start, end] => {
            let inclusive_end = end.value
                + if end.has_time {
                    Duration::seconds(59)
                } else {
                    Duration::days(1) - Duration::seconds(1)
                };
            Some(if fetched_at < start.value {
                "next"
            } else if fetched_at > inclusive_end {
                "previous"
            } else {
                "current"
            })
        }
        [start] if date_range.contains("长期开放") => Some(if fetched_at < start.value {
            "next"
        } else {
            "current"
        }),
        _ => None,
    }
}

fn parse_refresh_time(value: &str) -> Result<NaiveDateTime> {
    if let Ok(value) = DateTime::parse_from_rfc3339(value) {
        let china_standard_time = FixedOffset::east_opt(8 * 60 * 60).unwrap();
        return Ok(value.with_timezone(&china_standard_time).naive_local());
    }
    for format in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"] {
        if let Ok(value) = NaiveDateTime::parse_from_str(value, format) {
            return Ok(value);
        }
    }
    bail!("banner refresh fetched_at must be an RFC3339/local ISO timestamp")
}

fn parse_canonical_date_time(value: &str, end_of_day: bool) -> Result<NaiveDateTime> {
    if let Ok(value) = NaiveDateTime::parse_from_str(value, "%Y-%m-%d %H:%M") {
        return Ok(if end_of_day {
            value + Duration::seconds(59)
        } else {
            value
        });
    }
    if let Ok(value) = NaiveDate::parse_from_str(value, "%Y-%m-%d") {
        return Ok(if end_of_day {
            value.and_hms_opt(23, 59, 59).unwrap()
        } else {
            value.and_hms_opt(0, 0, 0).unwrap()
        });
    }
    bail!("invalid canonical official date {value:?}")
}

fn normalize_date_range(value: &str) -> String {
    remove_whitespace(value)
        .replace('/', "-")
        .replace('~', "至")
        .replace('～', "至")
        .replace('—', "-")
}

fn append_root_sources(
    root: &mut Map<String, Value>,
    official_phases: &[OfficialBannerPhaseV1],
) -> Result<()> {
    let sources = root
        .entry("sources")
        .or_insert_with(|| Value::Array(Vec::new()))
        .as_array_mut()
        .context("existing banner plan sources must be an array")?;
    let mut urls = sources
        .iter()
        .filter_map(|source| source.get("url").and_then(Value::as_str))
        .map(str::to_owned)
        .collect::<BTreeSet<_>>();
    for phase in official_phases {
        if urls.insert(phase.source_url.clone()) {
            sources.push(json!({
                "label": phase.source_label,
                "url": phase.source_url,
            }));
        }
    }
    Ok(())
}

fn dedupe_plan_phases(phases: &mut Vec<Value>) {
    let mut output = Vec::with_capacity(phases.len());
    for phase in phases.drain(..) {
        let duplicate = output.iter().any(|existing: &Value| {
            let same_source = existing.get("source_url").and_then(Value::as_str)
                == phase.get("source_url").and_then(Value::as_str);
            let same_title = existing
                .get("title")
                .and_then(Value::as_str)
                .zip(phase.get("title").and_then(Value::as_str))
                .is_some_and(|(left, right)| remove_whitespace(left) == remove_whitespace(right));
            let same_date = existing
                .get("date_range")
                .and_then(Value::as_str)
                .zip(phase.get("date_range").and_then(Value::as_str))
                .is_some_and(|(left, right)| {
                    normalize_date_range(left) == normalize_date_range(right)
                });
            let same_characters = phase_slug_set(existing) == phase_slug_set(&phase);
            (same_source || same_title) && same_date && same_characters
        });
        if !duplicate {
            output.push(phase);
        }
    }
    *phases = output;
}

fn phase_slug_set(phase: &Value) -> BTreeSet<&str> {
    phase
        .get("characters")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|character| character.get("slug").and_then(Value::as_str))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const HSR_LIST_FIXTURE: &str = r#"{
      "retcode": 0,
      "message": "OK",
      "data": {
        "list": [
          {
            "post": {
              "post_id": "76661906",
              "uid": "288909600",
              "subject": "4.4版本活动跃迁（其一）",
              "post_status": {"is_official": true}
            }
          },
          {
            "post": {
              "post_id": "other",
              "uid": "288909600",
              "subject": "角色预告",
              "post_status": {"is_official": true}
            }
          }
        ]
      }
    }"#;

    const HSR_FULL_FIXTURE: &str = r#"{
      "retcode": 0,
      "message": "OK",
      "data": {
        "post": {
          "post": {
            "post_id": "76661906",
            "uid": "288909600",
            "subject": "4.4版本活动跃迁（其一）",
            "post_status": {"is_official": true},
            "content": "<p>限定5星角色「姬子•启行（智识•火）」与限定5星光锥「当一颗星照亮夜空（智识）」跃迁成功概率限时提升，4星角色「貊泽（巡猎•雷）」「寒鸦（同谐•物理）」跃迁成功概率限时提升，跃迁时间为 2026/07/15 - 2026/08/25 15:00。</p><p>限定5星角色「火花（欢愉•火）」「丹恒•腾荒（存护•物理）」与限定5星光锥「花花世界迷人眼（欢愉）」将会返场，跃迁时间为 2026/07/15 - 2026/08/05 11:59。</p>"
          }
        }
      }
    }"#;

    const ZZZ_LIST_FIXTURE: &str = r#"{
      "retcode": 0,
      "message": "OK",
      "data": {
        "iTotal": 2,
        "list": [
          {
            "sChanId": ["279"],
            "sTitle": "3.0版本限时频段（下期）",
            "sIntro": "本期代理人与音擎调频活动时间为：2026/07/08 12:00~ 2026/07/28 14:59",
            "sContent": "<p>活动期间，限定S级代理人[诺姆(火·击破)]、[千夏(物理·支援)]以及A级代理人[可琳(物理·强攻)]、[波可娜(物理·击破)]的调频获取概率将大幅提升！</p><p>限定S级音擎[首席跟班(击破)]的调频获取概率将大幅提升！</p>",
            "iInfoId": 165152
          },
          {
            "sChanId": ["278"],
            "sTitle": "代理人机制介绍丨蕾米埃尔篇",
            "sIntro": "非卡池公告",
            "sContent": "",
            "iInfoId": 165339
          }
        ]
      }
    }"#;

    const ZZZ_VERSION_RELATIVE_FIXTURE: &str = r#"{
      "retcode": 0,
      "message": "OK",
      "data": {
        "list": [
          {
            "sChanId": ["279"],
            "sTitle": "3.1版本「漫长的告别」预下载开启&更新通知",
            "sIntro": "3.1版本预下载现已开启。",
            "sContent": "<p>【版本更新时间】</p><p>2026/07/29 06:00 开始，预计需要5个小时。</p>",
            "iInfoId": 165374
          },
          {
            "sChanId": ["279"],
            "sTitle": "3.1版本限时频段",
            "sIntro": "活动期间，限定S级代理人[蕾米埃尔(流明·异常)]以及默认A级代理人[派派(物理·异常)]、[赛斯(电·防护)]的调频获取概率将大幅提升！",
            "sContent": "<p>活动时间：3.1版本更新后 ~ 2026/09/08 14:59</p><p>活动期间，限定S级代理<span style=\"color:red\">人[蕾米埃尔(流明·异常)]以及默认A级代理人[派派(物理·异常)]、[赛斯(电·防护)]的调频获取概率将大幅提升！</span></p><p>活动期间，限定S级音擎[空羽复归之诗(异常)]的调频获取概率将大幅提升！</p><p>活动时间：3.1版本更新后 ~ 2026/08/19 11:59</p><p>活动期间，限定S级代理人[爱芮(以太·异常)]以及默认A级代理人[派派(物理·异常)]、[赛斯(电·防护)]的调频获取概率将大幅提升！</p>",
            "iInfoId": 165375
          }
        ]
      }
    }"#;

    const HSR_COLLAB_FIXTURE: &str = r#"{
      "retcode": 0,
      "message": "OK",
      "data": {
        "post": {
          "post": {
            "post_id": "76423940",
            "uid": "288909600",
            "subject": "Fate[UBW] 联动跃迁说明",
            "post_status": {"is_official": true},
            "content": "<p>角色「远坂凛」「吉尔伽美什」及光锥将加入Fate[UBW] 联动跃迁，并于 2026/07/24 12:00 后长期开放。</p><p>联动限定5星角色「远坂凛（智识•量子）」跃迁成功概率提升。</p><p>联动限定5星角色「吉尔伽美什（毁灭•雷）」跃迁成功概率提升。</p><p>▌Fate[UBW]联动跃迁详细说明</p><p>已在开放中的联动限定5星角色「Saber（毁灭•风）」「Archer（巡猎•量子）」也属于联动跃迁。</p>"
          }
        }
      }
    }"#;

    #[test]
    fn hsr_user_post_fixture_selects_only_strict_official_banner() {
        let posts = parse_hsr_user_post_list_json(HSR_LIST_FIXTURE).unwrap();
        assert_eq!(
            posts,
            vec![HsrOfficialPostRefV1 {
                post_id: "76661906".to_owned(),
                title: "4.4版本活动跃迁（其一）".to_owned(),
            }]
        );
    }

    #[test]
    fn hsr_full_fixture_extracts_date_distinct_roles_but_not_light_cones() {
        let phases = parse_hsr_get_post_full_json(HSR_FULL_FIXTURE).unwrap();
        assert_eq!(phases.len(), 2);
        assert_eq!(phases[0].date_range, "2026-07-15 至 2026-08-05 11:59");
        assert_eq!(phases[1].date_range, "2026-07-15 至 2026-08-25 15:00");
        let names = phases
            .iter()
            .flat_map(|phase| phase.characters.iter())
            .map(|character| character.name_cn.as_str())
            .collect::<BTreeSet<_>>();
        assert!(names.contains("姬子•启行"));
        assert!(names.contains("貊泽"));
        assert!(names.contains("火花"));
        assert!(names.contains("丹恒•腾荒"));
        assert!(!names.contains("当一颗星照亮夜空"));
        assert!(!names.contains("花花世界迷人眼"));
    }

    #[test]
    fn hsr_parser_rejects_wrong_uid_title_date_and_empty_roles() {
        for malformed in [
            HSR_FULL_FIXTURE.replace(HSR_OFFICIAL_UID, "1"),
            HSR_FULL_FIXTURE.replace("4.4版本活动跃迁（其一）", "4.4版本角色预告"),
            HSR_FULL_FIXTURE.replace("2026/08/25 15:00", "待定"),
            HSR_FULL_FIXTURE.replace("2026/07/15", "2026/07/15 25:00"),
            HSR_FULL_FIXTURE
                .replace(
                    "角色「姬子•启行（智识•火）」",
                    "光锥「姬子•启行（智识•火）」",
                )
                .replace(
                    "角色「火花（欢愉•火）」「丹恒•腾荒（存护•物理）」",
                    "光锥「火花（欢愉•火）」「丹恒•腾荒（存护•物理）」",
                )
                .replace(
                    "4星角色「貊泽（巡猎•雷）」「寒鸦（同谐•物理）」",
                    "4星光锥「貊泽（巡猎•雷）」「寒鸦（同谐•物理）」",
                ),
        ] {
            assert!(parse_hsr_get_post_full_json(&malformed).is_err());
        }
    }

    #[test]
    fn hsr_long_term_fixture_stops_before_rules_about_already_open_roles() {
        let phases = parse_hsr_get_post_full_json(HSR_COLLAB_FIXTURE).unwrap();
        assert_eq!(phases.len(), 1);
        assert_eq!(phases[0].date_range, "2026-07-24 12:00 后长期开放");
        assert_eq!(
            phases[0]
                .characters
                .iter()
                .map(|character| character.name_cn.as_str())
                .collect::<Vec<_>>(),
            vec!["远坂凛", "吉尔伽美什"]
        );
    }

    #[test]
    fn zzz_fixture_extracts_strict_announcement_dates_and_agents() {
        let phases = parse_zzz_content_list_json(ZZZ_LIST_FIXTURE).unwrap();
        assert_eq!(phases.len(), 1);
        assert_eq!(phases[0].date_range, "2026-07-08 12:00 至 2026-07-28 14:59");
        assert_eq!(
            phases[0]
                .characters
                .iter()
                .map(|character| character.name_cn.as_str())
                .collect::<Vec<_>>(),
            vec!["诺姆", "千夏", "可琳", "波可娜"]
        );
        assert_eq!(
            phases[0]
                .characters
                .iter()
                .map(|character| character.banner_role.as_str())
                .collect::<Vec<_>>(),
            vec!["限定 S 级 UP", "限定 S 级 UP", "A 级 UP", "A 级 UP"]
        );
        assert!(!phases[0]
            .characters
            .iter()
            .any(|character| character.name_cn == "首席跟班"));
    }

    #[test]
    fn zzz_bare_version_banner_uses_the_matching_official_update_completion() {
        let phases = parse_zzz_content_list_json(ZZZ_VERSION_RELATIVE_FIXTURE).unwrap();
        assert_eq!(phases.len(), 2);
        assert!(phases
            .iter()
            .all(|phase| phase.start_at == "2026-07-29 11:00"));
        assert_eq!(phases[0].date_range, "2026-07-29 11:00 至 2026-08-19 11:59");
        assert_eq!(phases[1].date_range, "2026-07-29 11:00 至 2026-09-08 14:59");
        assert_eq!(
            phases[0]
                .characters
                .iter()
                .map(|character| character.name_cn.as_str())
                .collect::<Vec<_>>(),
            vec!["爱芮", "派派", "赛斯"]
        );
        assert_eq!(
            phases[1]
                .characters
                .iter()
                .map(|character| character.name_cn.as_str())
                .collect::<Vec<_>>(),
            vec!["蕾米埃尔", "派派", "赛斯"]
        );
        assert_eq!(
            phases[0]
                .characters
                .iter()
                .map(|character| character.banner_role.as_str())
                .collect::<Vec<_>>(),
            vec!["限定 S 级 UP", "A 级 UP", "A 级 UP"]
        );
        assert_eq!(
            phases[1]
                .characters
                .iter()
                .map(|character| character.banner_role.as_str())
                .collect::<Vec<_>>(),
            vec!["限定 S 级 UP", "A 级 UP", "A 级 UP"]
        );
        assert!(phases
            .iter()
            .all(|phase| phase.source_url == "https://zzz.mihoyo.com/news/165375"));
    }

    #[test]
    fn merge_keeps_distinct_new_pools_that_share_source_and_up_characters() {
        let phases = parse_zzz_content_list_json(ZZZ_VERSION_RELATIVE_FIXTURE).unwrap();
        let snapshot = merge_banner_plan_snapshot(
            br#"{"phases":[]}"#,
            &phases,
            &BTreeMap::from([
                ("爱芮".to_owned(), "aria".to_owned()),
                ("派派".to_owned(), "piper".to_owned()),
                ("赛斯".to_owned(), "seth".to_owned()),
                ("蕾米埃尔".to_owned(), "remiel".to_owned()),
            ]),
            &BannerRefreshMetadataV1 {
                fetched_at: "2026-07-27T12:00:00+08:00".to_owned(),
                source_label: "《绝区零》官方网站".to_owned(),
            },
        )
        .unwrap();
        let value: Value = serde_json::from_slice(&snapshot).unwrap();
        let next = value["phases"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|phase| phase["status"] == "next")
            .collect::<Vec<_>>();
        assert_eq!(next.len(), 2);
        assert_eq!(
            next[0]["date_range"],
            "2026-07-29 11:00 至 2026-08-19 11:59"
        );
        assert_eq!(
            next[1]["date_range"],
            "2026-07-29 11:00 至 2026-09-08 14:59"
        );
        assert_eq!(next[0]["characters"][0]["slug"], "aria");
        assert_eq!(next[1]["characters"][0]["slug"], "remiel");
    }

    #[test]
    fn zzz_version_relative_banner_fails_closed_on_unknown_title_or_schedule() {
        assert!(parse_zzz_content_list_json(
            &ZZZ_VERSION_RELATIVE_FIXTURE
                .replace("3.1版本限时频段\"", "3.1版本限时频段（第一期）\"")
        )
        .is_err());
        assert!(parse_zzz_content_list_json(
            &ZZZ_VERSION_RELATIVE_FIXTURE.replace("预下载开启&更新通知", "预下载说明")
        )
        .is_err());
        assert!(parse_zzz_content_list_json(
            &ZZZ_VERSION_RELATIVE_FIXTURE.replace("预计需要5个小时", "预计完成时间待定")
        )
        .is_err());
    }

    #[test]
    fn zzz_parser_rejects_wrong_channel_title_date_and_empty_roles() {
        for malformed in [
            ZZZ_LIST_FIXTURE.replace(r#""279""#, r#""278""#),
            ZZZ_LIST_FIXTURE.replace("3.0版本限时频段（下期）", "3.0版本活动说明"),
            ZZZ_LIST_FIXTURE.replace("2026/07/28 14:59", "待定"),
            ZZZ_LIST_FIXTURE.replace("2026/07/08 12:00", "2026/07/08 12：00"),
            ZZZ_LIST_FIXTURE.replace("代理人[", "音擎["),
        ] {
            assert!(parse_zzz_content_list_json(&malformed).is_err());
        }
    }

    #[test]
    fn merge_preserves_manual_metadata_resolves_new_slugs_and_keeps_satellites() {
        let existing = r#"{
          "updated_at": "2026-07-09",
          "sources": [],
          "phases": [
            {
              "id": "3.0-second-half",
              "status": "current",
              "title": "3.0 下半调频",
              "subtitle": "当期 UP",
              "date_range": "2026-07-08 12:00 至 2026-07-28 14:59",
              "source_label": "旧来源",
              "source_url": "https://zzz.mihoyo.com/news/165152",
              "characters": [
                {
                  "slug": "sunna",
                  "name_cn": "千夏",
                  "banner_role": "旧角色事实",
                  "analysis_tags": ["人工标签"],
                  "focus": "人工判断",
                  "style_cn": "支援"
                }
              ]
            },
            {
              "id": "announced-satellites",
              "status": "satellite",
              "title": "已公开卫星",
              "date_range": "待官方调频确认",
              "characters": [
                {"slug": "remiel", "analysis_tags": ["卫星"]},
                {
                  "slug": "norma",
                  "name_cn": "诺姆·霍洛维尔",
                  "analysis_tags": ["人工卫星标签"],
                  "focus": "等待调频确认"
                }
              ]
            }
          ]
        }"#
        .as_bytes();
        let phases = parse_zzz_content_list_json(ZZZ_LIST_FIXTURE).unwrap();
        let name_map = BTreeMap::from([
            ("诺姆·霍洛维尔".to_owned(), "norma".to_owned()),
            ("千夏".to_owned(), "sunna".to_owned()),
            ("可琳·威克斯".to_owned(), "corin".to_owned()),
            ("波可娜·费雷尼".to_owned(), "pulchra".to_owned()),
        ]);
        let refresh = BannerRefreshMetadataV1 {
            fetched_at: "2026-07-24T12:00:00+08:00".to_owned(),
            source_label: "《绝区零》官方网站".to_owned(),
        };
        let snapshot = merge_banner_plan_snapshot(existing, &phases, &name_map, &refresh).unwrap();
        let value: Value = serde_json::from_slice(&snapshot).unwrap();
        assert_eq!(value["refresh"]["status"], "fresh");
        assert_eq!(value["refresh"]["fetched_at"], "2026-07-24T12:00:00+08:00");
        assert_eq!(value["updated_at"], "2026-07-24");
        let output_phases = value["phases"].as_array().unwrap();
        assert_eq!(output_phases.len(), 2);
        assert_eq!(output_phases[1]["status"], "satellite");
        assert_eq!(
            output_phases[1]["characters"]
                .as_array()
                .unwrap()
                .iter()
                .map(|character| character["slug"].as_str().unwrap())
                .collect::<Vec<_>>(),
            vec!["remiel"]
        );
        let current = &output_phases[0];
        assert_eq!(current["title"], "3.0 下半调频");
        assert_eq!(current["source_url"], "https://zzz.mihoyo.com/news/165152");
        assert_eq!(current["status"], "current");
        let characters = current["characters"].as_array().unwrap();
        assert_eq!(characters.len(), 4);
        let sunna = characters
            .iter()
            .find(|character| character["slug"] == "sunna")
            .unwrap();
        assert_eq!(sunna["analysis_tags"], json!(["人工标签"]));
        assert_eq!(sunna["focus"], "人工判断");
        assert_eq!(sunna["style_cn"], "支援");
        assert_eq!(sunna["banner_role"], "限定 S 级 UP");
        let norma = characters
            .iter()
            .find(|character| character["slug"] == "norma")
            .unwrap();
        assert_eq!(norma["name_cn"], "诺姆·霍洛维尔");
        assert_eq!(norma["analysis_tags"], json!(["人工卫星标签"]));
        assert_eq!(norma["focus"], "等待调频确认");

        let second = merge_banner_plan_snapshot(&snapshot, &phases, &name_map, &refresh).unwrap();
        let second: Value = serde_json::from_slice(&second).unwrap();
        assert_eq!(second["phases"].as_array().unwrap().len(), 2);
        assert_eq!(second["sources"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn merge_fails_closed_when_bundle_name_map_cannot_resolve_new_character() {
        let phases = parse_zzz_content_list_json(ZZZ_LIST_FIXTURE).unwrap();
        let error = merge_banner_plan_snapshot(
            br#"{"phases":[]}"#,
            &phases,
            &BTreeMap::new(),
            &BannerRefreshMetadataV1 {
                fetched_at: "2026-07-24T12:00:00".to_owned(),
                source_label: "official".to_owned(),
            },
        )
        .unwrap_err();
        assert!(error.to_string().contains("name_map"));
    }

    #[test]
    fn merge_recomputes_unmatched_dated_statuses_without_guessing_undated_previews() {
        let existing = r#"{
          "phases": [
            {
              "id": "stale-current",
              "status": "current",
              "title": "old phase",
              "date_range": "2026-06-01 至 2026-06-21 14:59",
              "characters": [{"slug": "remiel"}]
            },
            {
              "id": "long-term",
              "status": "next",
              "title": "long-term phase",
              "date_range": "2026-07-24 12:00 后长期开放",
              "characters": [{"slug": "saber"}]
            },
            {
              "id": "undated-preview",
              "status": "next",
              "title": "future preview",
              "date_range": "具体起止以公告为准",
              "characters": [{"slug": "cerydra"}]
            }
          ]
        }"#
        .as_bytes();
        let phases = parse_zzz_content_list_json(ZZZ_LIST_FIXTURE).unwrap();
        let snapshot = merge_banner_plan_snapshot(
            existing,
            &phases,
            &BTreeMap::from([
                ("诺姆·霍洛维尔".to_owned(), "norma".to_owned()),
                ("千夏".to_owned(), "sunna".to_owned()),
                ("可琳·威克斯".to_owned(), "corin".to_owned()),
                ("波可娜·费雷尼".to_owned(), "pulchra".to_owned()),
            ]),
            &BannerRefreshMetadataV1 {
                fetched_at: "2026-07-24T12:00:30+08:00".to_owned(),
                source_label: "《绝区零》官方网站".to_owned(),
            },
        )
        .unwrap();
        let value: Value = serde_json::from_slice(&snapshot).unwrap();
        let by_id = value["phases"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|phase| Some((phase.get("id")?.as_str()?, phase.get("status")?.as_str()?)))
            .collect::<BTreeMap<_, _>>();
        assert_eq!(by_id["stale-current"], "previous");
        assert_eq!(by_id["long-term"], "current");
        assert_eq!(by_id["undated-preview"], "next");
    }

    #[test]
    fn refresh_is_not_marked_fresh_when_official_coverage_is_only_historical() {
        let official = OfficialBannerPhaseV1 {
            id: "zzz-official-history-1".to_owned(),
            title: "历史卡池".to_owned(),
            subtitle: "官方公告".to_owned(),
            date_range: "2026-07-01 12:00 至 2026-07-02 14:59".to_owned(),
            start_at: "2026-07-01 12:00".to_owned(),
            end_at: Some("2026-07-02 14:59".to_owned()),
            source_label: "《绝区零》官方网站".to_owned(),
            source_url: "https://zzz.mihoyo.com/news/1".to_owned(),
            characters: vec![OfficialBannerCharacterV1 {
                name_cn: "爱芮".to_owned(),
                banner_role: "限定 S 级 UP".to_owned(),
                descriptor_cn: None,
            }],
        };
        let snapshot = merge_banner_plan_snapshot(
            br#"{"phases":[]}"#,
            &[official],
            &BTreeMap::from([("爱芮".to_owned(), "aria".to_owned())]),
            &BannerRefreshMetadataV1 {
                fetched_at: "2026-07-24T12:00:00+08:00".to_owned(),
                source_label: "《绝区零》官方网站".to_owned(),
            },
        )
        .unwrap();
        let value: Value = serde_json::from_slice(&snapshot).unwrap();
        assert_eq!(value["refresh"]["status"], "no_current");
        assert_eq!(value["refresh"]["official_phase_count"], 1);
        assert_eq!(value["refresh"]["official_current_phase_count"], 0);
        assert_eq!(value["refresh"]["official_next_phase_count"], 0);
    }

    #[test]
    fn descriptor_disambiguates_base_character_forms_when_no_exact_name_exists() {
        let mut phase = parse_hsr_get_post_full_json(HSR_FULL_FIXTURE)
            .unwrap()
            .remove(0);
        phase.characters = vec![OfficialBannerCharacterV1 {
            name_cn: "三月七".to_owned(),
            banner_role: "4 星 UP".to_owned(),
            descriptor_cn: Some("存护•冰".to_owned()),
        }];
        let resolved = resolve_official_characters(
            &phase,
            &BTreeMap::from([
                ("三月七 - 存护".to_owned(), "march-7th".to_owned()),
                ("三月七•巡猎".to_owned(), "march-7th-swordmaster".to_owned()),
            ]),
            &BTreeMap::new(),
        )
        .unwrap();
        assert_eq!(resolved[0]["slug"], "march-7th");
    }

    #[test]
    fn official_short_name_promotes_unique_named_satellite_to_next_phase() {
        let existing = r#"{
          "phases": [{
            "id": "announced-satellites",
            "status": "satellite",
            "title": "已公开卫星",
            "date_range": "待官方调频确认",
            "characters": [{
              "slug": "remiel",
              "name_cn": "蕾米埃尔·丹",
              "analysis_tags": ["卫星"]
            }]
          }]
        }"#;
        let official = OfficialBannerPhaseV1 {
            id: "zzz-official-165375-remiel".to_owned(),
            title: "3.1版本限时频段".to_owned(),
            subtitle: "限定调频".to_owned(),
            date_range: "2026-07-29 11:00 至 2026-09-08 14:59".to_owned(),
            start_at: "2026-07-29 11:00".to_owned(),
            end_at: Some("2026-09-08 14:59".to_owned()),
            source_label: "《绝区零》官方网站".to_owned(),
            source_url: "https://zzz.mihoyo.com/news/165375".to_owned(),
            characters: vec![OfficialBannerCharacterV1 {
                name_cn: "蕾米埃尔".to_owned(),
                banner_role: "限定 S 级 UP".to_owned(),
                descriptor_cn: None,
            }],
        };
        let snapshot = merge_banner_plan_snapshot(
            existing.as_bytes(),
            &[official],
            &BTreeMap::new(),
            &BannerRefreshMetadataV1 {
                fetched_at: "2026-07-27T12:00:00+08:00".to_owned(),
                source_label: "《绝区零》官方网站".to_owned(),
            },
        )
        .unwrap();
        let value: Value = serde_json::from_slice(&snapshot).unwrap();
        let phases = value["phases"].as_array().unwrap();
        assert_eq!(phases.len(), 1);
        assert_eq!(phases[0]["status"], "next");
        assert_eq!(phases[0]["characters"][0]["slug"], "remiel");
        assert_eq!(phases[0]["characters"][0]["name_cn"], "蕾米埃尔·丹");
        assert_eq!(phases[0]["characters"][0]["analysis_tags"], json!(["卫星"]));
    }

    #[test]
    fn official_short_name_fails_closed_when_existing_prefix_is_ambiguous() {
        let phase = OfficialBannerPhaseV1 {
            id: "zzz-official-ambiguous-remiel".to_owned(),
            title: "3.1版本限时频段".to_owned(),
            subtitle: "限定调频".to_owned(),
            date_range: "2026-07-29 11:00 至 2026-09-08 14:59".to_owned(),
            start_at: "2026-07-29 11:00".to_owned(),
            end_at: Some("2026-09-08 14:59".to_owned()),
            source_label: "《绝区零》官方网站".to_owned(),
            source_url: "https://zzz.mihoyo.com/news/165375".to_owned(),
            characters: vec![OfficialBannerCharacterV1 {
                name_cn: "蕾米埃尔".to_owned(),
                banner_role: "限定 S 级 UP".to_owned(),
                descriptor_cn: None,
            }],
        };
        let existing = BTreeMap::from([
            (
                "remiel".to_owned(),
                json!({"slug":"remiel","name_cn":"蕾米埃尔·丹"}),
            ),
            (
                "remiel-alt".to_owned(),
                json!({"slug":"remiel-alt","name_cn":"蕾米埃尔·诺"}),
            ),
        ]);
        let error = resolve_official_characters(&phase, &BTreeMap::new(), &existing)
            .unwrap_err()
            .to_string();
        assert!(error.contains("resolves to multiple canonical slugs"));
        assert!(error.contains("remiel"));
        assert!(error.contains("remiel-alt"));
    }

    #[test]
    fn merge_replaces_same_version_preview_by_character_overlap_and_keeps_metadata() {
        let existing = r#"{
          "phases": [{
            "id": "4.4-second-half",
            "status": "next",
            "title": "4.4 第二期活动跃迁",
            "subtitle": "前瞻阶段",
            "date_range": "4.4 第二期，具体起止以公告为准",
            "source_label": "官方前瞻",
            "source_url": "https://www.miyoushe.com/sr/article/70000000",
            "characters": [{
              "slug": "cerydra",
              "name_cn": "赛飞儿",
              "analysis_tags": ["人工前瞻"],
              "focus": "等待正式公告"
            }]
          }]
        }"#
        .as_bytes();
        let official = OfficialBannerPhaseV1 {
            id: "hsr-official-70000001-1".to_owned(),
            title: "4.4版本活动跃迁（其二）".to_owned(),
            subtitle: "官方公告".to_owned(),
            date_range: "2026-08-05 12:00 至 2026-08-25 15:00".to_owned(),
            start_at: "2026-08-05 12:00".to_owned(),
            end_at: Some("2026-08-25 15:00".to_owned()),
            source_label: "米游社官方：4.4版本活动跃迁（其二）".to_owned(),
            source_url: "https://www.miyoushe.com/sr/article/70000001".to_owned(),
            characters: vec![OfficialBannerCharacterV1 {
                name_cn: "赛飞儿".to_owned(),
                banner_role: "限定 5 星 UP".to_owned(),
                descriptor_cn: Some("同谐•风".to_owned()),
            }],
        };
        let snapshot = merge_banner_plan_snapshot(
            existing,
            &[official],
            &BTreeMap::from([
                ("赛飞儿".to_owned(), "cerydra".to_owned()),
                ("赛飞儿·另一形态".to_owned(), "cerydra-alt".to_owned()),
            ]),
            &BannerRefreshMetadataV1 {
                fetched_at: "2026-07-24T12:00:00+08:00".to_owned(),
                source_label: "米游社官方".to_owned(),
            },
        )
        .unwrap();
        let value: Value = serde_json::from_slice(&snapshot).unwrap();
        let phases = value["phases"].as_array().unwrap();
        assert_eq!(phases.len(), 1);
        assert_eq!(phases[0]["id"], "4.4-second-half");
        assert_eq!(phases[0]["title"], "4.4 第二期活动跃迁");
        assert_eq!(phases[0]["status"], "next");
        assert_eq!(
            phases[0]["date_range"],
            "2026-08-05 12:00 至 2026-08-25 15:00"
        );
        assert_eq!(
            phases[0]["source_url"],
            "https://www.miyoushe.com/sr/article/70000001"
        );
        assert_eq!(
            phases[0]["characters"][0]["analysis_tags"],
            json!(["人工前瞻"])
        );
        assert_eq!(phases[0]["characters"][0]["focus"], "等待正式公告");
    }

    #[test]
    fn cross_date_preview_match_ignores_shared_four_star_characters() {
        let existing = vec![
            json!({
                "title": "4.4 拓星启明",
                "date_range": "2026-07-15 至 2026-08-25 15:00",
                "source_url": "https://www.miyoushe.com/sr/article/76661906",
                "characters": [
                    {"slug": "himeko-nova"},
                    {"slug": "moze"},
                    {"slug": "hanya"},
                    {"slug": "serval"}
                ]
            }),
            json!({
                "title": "4.4 第一期活动跃迁",
                "date_range": "2026-07-15 至 2026-08-05 11:59",
                "source_url": "https://www.miyoushe.com/sr/article/76661906",
                "characters": [
                    {"slug": "sparxie"},
                    {"slug": "moze"},
                    {"slug": "hanya"},
                    {"slug": "serval"}
                ]
            }),
            json!({
                "title": "4.4 第二期活动跃迁",
                "date_range": "具体起止以公告为准",
                "source_url": "https://www.miyoushe.com/sr/article/76423172",
                "characters": [
                    {"slug": "cerydra"},
                    {"slug": "anaxa"},
                    {"slug": "aventurine"}
                ]
            }),
        ];
        let official = OfficialBannerPhaseV1 {
            id: "hsr-official-77000000-1".to_owned(),
            title: "4.4版本活动跃迁（其二）".to_owned(),
            subtitle: "官方公告".to_owned(),
            date_range: "2026-08-05 12:00 至 2026-08-25 15:00".to_owned(),
            start_at: "2026-08-05 12:00".to_owned(),
            end_at: Some("2026-08-25 15:00".to_owned()),
            source_label: "米游社官方".to_owned(),
            source_url: "https://www.miyoushe.com/sr/article/77000000".to_owned(),
            characters: vec![
                OfficialBannerCharacterV1 {
                    name_cn: "赛飞儿".to_owned(),
                    banner_role: "限定 5 星 UP".to_owned(),
                    descriptor_cn: None,
                },
                OfficialBannerCharacterV1 {
                    name_cn: "那刻夏".to_owned(),
                    banner_role: "限定 5 星 UP".to_owned(),
                    descriptor_cn: None,
                },
                OfficialBannerCharacterV1 {
                    name_cn: "砂金".to_owned(),
                    banner_role: "限定 5 星 UP".to_owned(),
                    descriptor_cn: None,
                },
                OfficialBannerCharacterV1 {
                    name_cn: "貊泽".to_owned(),
                    banner_role: "4 星 UP".to_owned(),
                    descriptor_cn: None,
                },
                OfficialBannerCharacterV1 {
                    name_cn: "寒鸦".to_owned(),
                    banner_role: "4 星 UP".to_owned(),
                    descriptor_cn: None,
                },
                OfficialBannerCharacterV1 {
                    name_cn: "希露瓦".to_owned(),
                    banner_role: "4 星 UP".to_owned(),
                    descriptor_cn: None,
                },
            ],
        };
        let resolved = vec![
            json!({"slug": "cerydra", "banner_role": "限定 5 星 UP"}),
            json!({"slug": "anaxa", "banner_role": "限定 5 星 UP"}),
            json!({"slug": "aventurine", "banner_role": "限定 5 星 UP"}),
            json!({"slug": "moze", "banner_role": "4 星 UP"}),
            json!({"slug": "hanya", "banner_role": "4 星 UP"}),
            json!({"slug": "serval", "banner_role": "4 星 UP"}),
        ];
        assert_eq!(
            find_matching_phase(&existing, &official, &resolved, &BTreeSet::new()),
            Some(2)
        );
    }

    #[test]
    fn official_phase_dedupe_accepts_same_title_and_date_from_republished_source() {
        let first = parse_zzz_content_list_json(ZZZ_LIST_FIXTURE)
            .unwrap()
            .remove(0);
        let mut republished = first.clone();
        republished.id = "zzz-official-165153-1".to_owned();
        republished.source_url = "https://zzz.mihoyo.com/news/165153".to_owned();
        republished.characters = vec![OfficialBannerCharacterV1 {
            name_cn: "新代理人".to_owned(),
            banner_role: "限定 S 级 UP".to_owned(),
            descriptor_cn: None,
        }];
        let deduped = dedupe_official_phases(vec![first.clone(), republished]).unwrap();
        assert_eq!(deduped.len(), 1);
        assert_eq!(deduped[0].source_url, first.source_url);
        assert_eq!(deduped[0].characters.len(), 5);
    }

    #[test]
    fn official_endpoint_builders_lock_expected_ids() {
        assert!(hsr_user_post_url().contains("uid=288909600"));
        assert!(hsr_user_post_url().contains("offset=0"));
        assert!(hsr_get_post_full_url("76661906")
            .unwrap()
            .contains("post_id=76661906"));
        assert!(hsr_get_post_full_url("../escape").is_err());
        let zzz = zzz_content_list_url();
        assert!(zzz.contains("/app/706fd13a87294881/"));
        assert!(zzz.contains("iChanId=273"));
    }

    #[tokio::test]
    #[ignore = "read-only live official API smoke test"]
    async fn live_official_endpoints_parse_current_responses() {
        let http =
            HttpClient::new(std::time::Duration::from_secs(30), 1).expect("construct HTTP client");
        let hsr = fetch_hsr_official_banner_phases(&http)
            .await
            .expect("parse live HSR official responses");
        assert!(!hsr.is_empty());
        assert!(hsr.iter().all(|phase| !phase.characters.is_empty()));

        let zzz = fetch_zzz_official_banner_phases(&http)
            .await
            .expect("parse live ZZZ official response");
        assert!(!zzz.is_empty());
        assert!(zzz.iter().all(|phase| !phase.characters.is_empty()));
    }
}
