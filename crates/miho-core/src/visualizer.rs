use std::{
    collections::BTreeMap,
    path::{Component, Path},
};

use chrono::{NaiveDate, NaiveDateTime, NaiveTime};
use serde::Serialize;
use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

use crate::{output::ArtifactBundle, MihoError, Result};

pub const VISUALIZER_CONTEXT_SCHEMA_VERSION: u16 = 2;

const HSR_INDEX_HTML: &str = include_str!("../assets/visualizer/hsr/index.html");
const HSR_STYLES_CSS: &str = include_str!("../assets/visualizer/hsr/styles.css");
const HSR_APP_JS: &str = include_str!("../assets/visualizer/hsr/app.js");
const ZZZ_INDEX_HTML: &str = include_str!("../assets/visualizer/zzz/index.html");
const ZZZ_STYLES_CSS: &str = include_str!("../assets/visualizer/zzz/styles.css");
const ZZZ_APP_JS: &str = include_str!("../assets/visualizer/zzz/app.js");
const HUB_STYLES_CSS: &str = include_str!("../assets/visualizer/hub/styles.css");
const HUB_APP_JS: &str = include_str!("../assets/visualizer/hub/app.js");

/// Returns trusted executable/static visualizer assets embedded at compile time.
/// Mutable workspace data and avatar files are intentionally not exposed here.
pub fn visualizer_static_asset(game: &str, name: &str) -> Option<&'static [u8]> {
    match (game, name) {
        ("hsr", "index.html") => Some(HSR_INDEX_HTML.as_bytes()),
        ("hsr", "app.js") => Some(HSR_APP_JS.as_bytes()),
        ("hsr", "styles.css") => Some(HSR_STYLES_CSS.as_bytes()),
        ("zzz", "index.html") => Some(ZZZ_INDEX_HTML.as_bytes()),
        ("zzz", "app.js") => Some(ZZZ_APP_JS.as_bytes()),
        ("zzz", "styles.css") => Some(ZZZ_STYLES_CSS.as_bytes()),
        _ => None,
    }
}

#[derive(Debug, Clone)]
pub struct VisualizerContext {
    pub schema_version: u16,
    pub local_date: NaiveDate,
    local_datetime: Option<NaiveDateTime>,
    sidecars: BTreeMap<String, Vec<u8>>,
    avatar_webp: BTreeMap<String, Vec<u8>>,
}

impl VisualizerContext {
    pub fn new(local_date: NaiveDate) -> Self {
        Self {
            schema_version: VISUALIZER_CONTEXT_SCHEMA_VERSION,
            local_date,
            local_datetime: None,
            sidecars: BTreeMap::new(),
            avatar_webp: BTreeMap::new(),
        }
    }

    pub fn new_with_local_datetime(local_datetime: NaiveDateTime) -> Self {
        Self {
            schema_version: VISUALIZER_CONTEXT_SCHEMA_VERSION,
            local_date: local_datetime.date(),
            local_datetime: Some(local_datetime),
            sidecars: BTreeMap::new(),
            avatar_webp: BTreeMap::new(),
        }
    }

    pub fn validate(&self) -> Result<()> {
        if self.schema_version != VISUALIZER_CONTEXT_SCHEMA_VERSION {
            return Err(MihoError::Visualizer(format!(
                "visualizer context schema {} is not supported",
                self.schema_version
            )));
        }
        Ok(())
    }

    pub fn require_local_datetime(&self) -> Result<NaiveDateTime> {
        self.validate()?;
        self.local_datetime.ok_or_else(|| {
            MihoError::Visualizer(
                "visualizer context requires an explicit local datetime for banner status".into(),
            )
        })
    }

    pub fn add_sidecar_bytes(
        &mut self,
        path: impl AsRef<Path>,
        value: impl Into<Vec<u8>>,
    ) -> Result<()> {
        let path = safe_relative_string(path.as_ref())?;
        self.sidecars.insert(path, value.into());
        Ok(())
    }

    pub fn add_sidecar_json<T: Serialize>(
        &mut self,
        path: impl AsRef<Path>,
        value: &T,
    ) -> Result<()> {
        let path = path.as_ref();
        let data = serde_json::to_vec(value).map_err(|source| MihoError::Json {
            path: path.to_path_buf(),
            source,
        })?;
        self.add_sidecar_bytes(path, data)
    }

    pub fn sidecar(&self, path: &str) -> Option<&[u8]> {
        self.sidecars.get(path).map(Vec::as_slice)
    }

    pub fn add_avatar_webp(&mut self, slug: &str, bytes: impl Into<Vec<u8>>) -> Result<()> {
        if slug.is_empty()
            || !slug
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        {
            return Err(MihoError::Visualizer(format!(
                "unsafe avatar slug: {slug:?}"
            )));
        }
        let bytes = bytes.into();
        validate_webp(&bytes)?;
        self.avatar_webp.insert(slug.to_owned(), bytes);
        Ok(())
    }

    pub fn avatar_webp(&self, slug: &str) -> Option<&[u8]> {
        self.avatar_webp.get(slug).map(Vec::as_slice)
    }
}

pub fn attach_hsr_static_assets(bundle: &mut ArtifactBundle) -> Result<()> {
    bundle.add_text("visualizer/index.html", HSR_INDEX_HTML)?;
    bundle.add_text("visualizer/styles.css", HSR_STYLES_CSS)?;
    bundle.add_text("visualizer/app.js", HSR_APP_JS)?;
    Ok(())
}

pub fn attach_zzz_static_assets(bundle: &mut ArtifactBundle) -> Result<()> {
    bundle.add_text("visualizer/index.html", ZZZ_INDEX_HTML)?;
    bundle.add_text("visualizer/styles.css", ZZZ_STYLES_CSS)?;
    bundle.add_text("visualizer/app.js", ZZZ_APP_JS)?;
    Ok(())
}

pub fn attach_visualizer_hub(
    bundle: &mut ArtifactBundle,
    hsr_dir: &str,
    zzz_dir: &str,
) -> Result<()> {
    let hsr_segment = safe_directory_segment(hsr_dir)?;
    let zzz_segment = safe_directory_segment(zzz_dir)?;
    let html = format!(
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n  <meta charset=\"utf-8\" />\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n  <title>米哈游终局可视化</title>\n  <link rel=\"stylesheet\" href=\"./styles.css\" />\n</head>\n<body>\n  <main class=\"hub\">\n    <header class=\"topbar\">\n      <div>\n        <h1>米哈游终局可视化</h1>\n        <p id=\"statusLine\">同一个入口切换游戏；Box 数据按游戏分别本地保存。</p>\n      </div>\n      <nav class=\"tabs\">\n        <button data-game=\"hsr\" data-src=\"../{hsr_segment}/visualizer/index.html\">崩坏：星穹铁道</button>\n        <button data-game=\"zzz\" data-src=\"../{zzz_segment}/visualizer/index.html\">绝区零</button>\n      </nav>\n    </header>\n    <iframe id=\"gameFrame\" title=\"终局可视化\"></iframe>\n  </main>\n  <script src=\"./app.js\"></script>\n</body>\n</html>\n"
    );
    bundle.add_text("index.html", html)?;
    bundle.add_text("styles.css", without_patch_newline(HUB_STYLES_CSS))?;
    bundle.add_text("app.js", without_patch_newline(HUB_APP_JS))?;
    Ok(())
}

fn without_patch_newline(value: &str) -> &str {
    value.strip_suffix('\n').unwrap_or(value)
}

fn safe_directory_segment(value: &str) -> Result<String> {
    let text = value.trim();
    if text.is_empty()
        || matches!(text, "." | "..")
        || text.contains('/')
        || text.contains('\\')
        || text
            .chars()
            .any(|value| (value as u32) < 32 || value as u32 == 127)
    {
        return Err(MihoError::Visualizer(format!(
            "unsafe visualizer output directory name: {value:?}"
        )));
    }
    let mut output = String::new();
    for byte in text.as_bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            output.push(*byte as char);
        } else {
            output.push_str(&format!("%{byte:02X}"));
        }
    }
    Ok(output)
}

pub fn attach_avatar_assets(
    bundle: &mut ArtifactBundle,
    context: &VisualizerContext,
) -> Result<()> {
    context.validate()?;
    for (slug, bytes) in &context.avatar_webp {
        bundle.add_bytes(
            format!("visualizer/assets/avatars/{slug}.webp"),
            bytes.clone(),
        )?;
    }
    Ok(())
}

pub fn local_avatar_url(context: &VisualizerContext, slug: &str) -> String {
    if context.avatar_webp(slug).is_some() {
        format!("./assets/avatars/{slug}.webp")
    } else {
        String::new()
    }
}

pub fn read_csv_rows(bundle: &ArtifactBundle, path: &str) -> Result<Vec<BTreeMap<String, String>>> {
    let bytes = bundle.get(path).ok_or_else(|| {
        MihoError::Visualizer(format!("required CSV artifact is missing: {path}"))
    })?;
    let mut reader = csv::ReaderBuilder::new().from_reader(bytes);
    let headers = reader
        .headers()?
        .iter()
        .enumerate()
        .map(|(index, value)| {
            if index == 0 {
                value.trim_start_matches('\u{feff}').to_owned()
            } else {
                value.to_owned()
            }
        })
        .collect::<Vec<_>>();
    reader
        .records()
        .map(|record| {
            let record = record?;
            Ok(headers
                .iter()
                .zip(record.iter())
                .map(|(key, value)| (key.to_owned(), value.to_owned()))
                .collect())
        })
        .collect()
}

pub fn compact_json<T: Serialize>(path: &str, value: &T) -> Result<Vec<u8>> {
    serde_json::to_vec(value).map_err(|source| MihoError::Json {
        path: path.into(),
        source,
    })
}

pub(crate) fn strict_utf8<'a>(bytes: &'a [u8], path: &str) -> Result<&'a str> {
    std::str::from_utf8(bytes)
        .map_err(|source| MihoError::Visualizer(format!("invalid UTF-8 in {path}: {source}")))
}

pub fn validate_json_surrogate_escapes(text: &str, path: &str) -> Result<()> {
    let bytes = text.as_bytes();
    let mut index = 0;
    let mut in_string = false;
    while index < bytes.len() {
        if !in_string {
            if bytes[index] == b'"' {
                in_string = true;
            }
            index += 1;
            continue;
        }
        match bytes[index] {
            b'"' => {
                in_string = false;
                index += 1;
            }
            b'\\' => {
                if bytes.get(index + 1) != Some(&b'u') {
                    index = (index + 2).min(bytes.len());
                    continue;
                }
                let Some(code) = json_hex_escape(bytes, index) else {
                    index += 2;
                    continue;
                };
                if (0xd800..=0xdbff).contains(&code) {
                    let pair_index = index + 6;
                    let pair = json_hex_escape(bytes, pair_index);
                    if !pair.is_some_and(|value| (0xdc00..=0xdfff).contains(&value)) {
                        return Err(MihoError::Visualizer(format!(
                            "unpaired JSON surrogate escape in {path}"
                        )));
                    }
                    index += 12;
                } else if (0xdc00..=0xdfff).contains(&code) {
                    return Err(MihoError::Visualizer(format!(
                        "unpaired JSON surrogate escape in {path}"
                    )));
                } else {
                    index += 6;
                }
            }
            _ => index += 1,
        }
    }
    Ok(())
}

fn json_hex_escape(bytes: &[u8], index: usize) -> Option<u16> {
    if bytes.get(index..index + 2)? != b"\\u" {
        return None;
    }
    bytes
        .get(index + 2..index + 6)?
        .iter()
        .try_fold(0u16, |value, byte| {
            let digit = match byte {
                b'0'..=b'9' => byte - b'0',
                b'a'..=b'f' => byte - b'a' + 10,
                b'A'..=b'F' => byte - b'A' + 10,
                _ => return None,
            };
            Some(value * 16 + u16::from(digit))
        })
}

pub fn safe_link_url(value: &str) -> String {
    let text = value.trim();
    if text.is_empty()
        || text.contains('\\')
        || text.chars().any(|ch| ch.is_control())
        || text.starts_with('/')
    {
        return String::new();
    }
    if let Some((scheme, remainder)) = text.split_once(':') {
        if !matches!(scheme.to_ascii_lowercase().as_str(), "http" | "https")
            || !remainder.starts_with("//")
        {
            return String::new();
        }
        let authority = remainder[2..].split(['/', '?', '#']).next().unwrap_or("");
        if authority.is_empty()
            || authority.chars().any(char::is_whitespace)
            || !python_urlsplit_accepts_nfkc_authority(authority)
            || !python_urlsplit_accepts_bracketed_authority(authority)
        {
            return String::new();
        }
        return text.to_owned();
    }
    safe_relative_url(text)
}

/// Python visualizer URL helpers first evaluate `value or ""` and then call
/// `str(...)`. Keep that scalar boundary explicit for JSON-backed sidecars.
pub fn python_scalar_text(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => String::new(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Number(number)) if number.as_f64() == Some(0.0) => String::new(),
        Some(Value::Number(number)) => python_json_number_repr(number),
        Some(Value::String(value)) => value.clone(),
        Some(Value::Array(values)) if values.is_empty() => String::new(),
        Some(Value::Object(values)) if values.is_empty() => String::new(),
        Some(value) => value.to_string(),
    }
}

pub fn python_value_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().is_some_and(|value| value != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

/// Match Python's JSON/`repr(float)` spelling for a finite JSON number.
///
/// Rust and Python use the same shortest-roundtrip digits, but Rust omits the
/// explicit exponent sign and leading zero that Python emits (for example,
/// `1e-7` versus `1e-07`).
pub(crate) fn python_json_number_repr(number: &serde_json::Number) -> String {
    let token = number.to_string();
    if token == "-0" {
        return "0".to_owned();
    }
    if !token.contains(['.', 'e', 'E']) {
        return token;
    }

    let Ok(value) = token.parse::<f64>() else {
        return token;
    };
    if value.is_infinite() {
        return if value.is_sign_negative() {
            "-inf".into()
        } else {
            "inf".into()
        };
    }
    let rust = format!("{value:?}");
    let Some((mantissa, exponent)) = rust.split_once('e') else {
        return rust;
    };
    let Ok(exponent) = exponent.parse::<i32>() else {
        return rust;
    };
    format!("{mantissa}e{exponent:+03}")
}

pub(crate) fn normalize_python_json_numbers(input: &[u8]) -> Vec<u8> {
    let mut output = Vec::with_capacity(input.len());
    let mut index = 0;
    let mut in_string = false;
    let mut escaped = false;
    while index < input.len() {
        let byte = input[index];
        if in_string {
            output.push(byte);
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                in_string = false;
            }
            index += 1;
            continue;
        }
        if byte == b'"' {
            in_string = true;
            output.push(byte);
            index += 1;
            continue;
        }
        if byte == b'-' || byte.is_ascii_digit() {
            let start = index;
            index += 1;
            while index < input.len()
                && matches!(input[index], b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-')
            {
                index += 1;
            }
            let token = std::str::from_utf8(&input[start..index]).unwrap_or_default();
            if token.contains(['.', 'e', 'E']) {
                if let Ok(Value::Number(number)) = serde_json::from_str::<Value>(token) {
                    output.extend_from_slice(python_json_number_repr(&number).as_bytes());
                    continue;
                }
            }
            output.extend_from_slice(token.as_bytes());
            continue;
        }
        output.push(byte);
        index += 1;
    }
    output
}

fn python_urlsplit_accepts_nfkc_authority(authority: &str) -> bool {
    let reduced = authority
        .chars()
        .filter(|character| !matches!(character, '@' | ':' | '#' | '?'))
        .collect::<String>();
    let normalized = reduced.nfkc().collect::<String>();
    reduced == normalized
        || !normalized
            .chars()
            .any(|character| matches!(character, '/' | '?' | '#' | '@' | ':'))
}

fn python_urlsplit_accepts_bracketed_authority(authority: &str) -> bool {
    let has_open = authority.contains('[');
    let has_close = authority.contains(']');
    if has_open != has_close {
        return false;
    }
    if !has_open {
        return true;
    }

    let hostname_and_port = authority
        .rsplit_once('@')
        .map_or(authority, |(_, host)| host);
    if !hostname_and_port.starts_with('[') {
        return false;
    }
    let Some(close) = hostname_and_port.find(']') else {
        return false;
    };
    let hostname = &hostname_and_port[1..close];
    let port = &hostname_and_port[close + 1..];
    if !port.is_empty() && !port.starts_with(':') {
        return false;
    }

    if let Some(ipv_future) = hostname.strip_prefix('v') {
        let Some((version, address)) = ipv_future.split_once('.') else {
            return false;
        };
        return !version.is_empty()
            && version.bytes().all(|byte| byte.is_ascii_hexdigit())
            && !address.is_empty();
    }

    let address = match hostname.split_once('%') {
        Some((address, scope)) if !scope.is_empty() && !scope.contains('%') => address,
        Some(_) => return false,
        None => hostname,
    };
    !address.is_empty() && address.parse::<std::net::Ipv6Addr>().is_ok()
}

pub fn safe_relative_url(value: &str) -> String {
    let text = value.trim();
    if text.is_empty()
        || text.starts_with('/')
        || text.contains('\\')
        || text.contains(':')
        || text.chars().any(|ch| ch.is_control())
    {
        return String::new();
    }
    let mut path = text.split(['?', '#']).next().unwrap_or("").to_owned();
    for _ in 0..3 {
        let decoded = percent_decode(&path);
        if decoded == path {
            break;
        }
        path = decoded;
    }
    if path.starts_with('/') || path.contains('\\') || path.split('/').any(|part| part == "..") {
        return String::new();
    }
    text.to_owned()
}

pub fn effective_banner_status(phase: &Value, now: NaiveDateTime) -> Result<String> {
    let declared = python_text(phase.get("status")).trim().to_ascii_lowercase();
    if declared == "satellite" {
        return Ok(declared);
    }
    let (start, end) = phase_datetime_bounds(phase)?;
    if start.is_none() && end.is_none() {
        return Ok(declared);
    }
    if !declared.is_empty()
        && !matches!(
            declared.as_str(),
            "current" | "next" | "previous" | "expired" | "past"
        )
    {
        return Ok(declared);
    }
    if start.is_some_and(|value| now < value) {
        Ok("next".into())
    } else if end.is_some_and(|value| now > value) {
        Ok("previous".into())
    } else {
        Ok("current".into())
    }
}

fn phase_datetime_bounds(phase: &Value) -> Result<(Option<NaiveDateTime>, Option<NaiveDateTime>)> {
    let start = ["start_at", "starts_at", "start_time", "start"]
        .iter()
        .find_map(|key| nonempty_python_text(phase.get(key)))
        .map(|value| first_datetime(&value, false))
        .transpose()?
        .flatten();
    let end = ["end_at", "ends_at", "end_time", "end"]
        .iter()
        .find_map(|key| nonempty_python_text(phase.get(key)))
        .map(|value| first_datetime(&value, false))
        .transpose()?
        .flatten();
    if start.is_some() || end.is_some() {
        return Ok((start, end));
    }

    let range = python_text(phase.get("date_range"));
    let matches = datetime_matches(&range, 2)?;
    let start = matches.first().map(|value| value.at_start);
    let end = matches.get(1).map(|value| value.at_end);
    Ok((start, end))
}

#[derive(Debug, Clone, Copy)]
struct ParsedDateTime {
    at_start: NaiveDateTime,
    at_end: NaiveDateTime,
}

fn first_datetime(value: &str, is_end: bool) -> Result<Option<NaiveDateTime>> {
    Ok(datetime_matches(value, 1)?.first().map(
        |value| {
            if is_end {
                value.at_end
            } else {
                value.at_start
            }
        },
    ))
}

fn datetime_matches(value: &str, limit: usize) -> Result<Vec<ParsedDateTime>> {
    let bytes = value.as_bytes();
    let mut output = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        let Some((end, parts)) = datetime_at(value, index) else {
            index += 1;
            continue;
        };
        let date = (parts.year != 0)
            .then(|| NaiveDate::from_ymd_opt(parts.year, parts.month, parts.day))
            .flatten()
            .ok_or_else(|| {
                MihoError::Visualizer(format!("invalid banner date near {:?}", &value[index..end]))
            })?;
        let (at_start, at_end) = if let Some((hour, minute, second)) = parts.time {
            let time = NaiveTime::from_hms_opt(hour, minute, second).ok_or_else(|| {
                MihoError::Visualizer(format!("invalid banner time near {:?}", &value[index..end]))
            })?;
            let value = date.and_time(time);
            (value, value)
        } else {
            (
                date.and_time(NaiveTime::MIN),
                date.and_time(NaiveTime::from_hms_micro_opt(23, 59, 59, 999_999).unwrap()),
            )
        };
        output.push(ParsedDateTime { at_start, at_end });
        if output.len() == limit {
            break;
        }
        index = end;
    }
    Ok(output)
}

#[derive(Debug, Clone, Copy)]
struct DateTimeParts {
    year: i32,
    month: u32,
    day: u32,
    time: Option<(u32, u32, u32)>,
}

fn datetime_at(value: &str, start: usize) -> Option<(usize, DateTimeParts)> {
    let bytes = value.as_bytes();
    let (year, mut index) = unicode_digits_exact(value, start, 4)?;
    if !bytes
        .get(index)
        .is_some_and(|value| matches!(value, b'-' | b'/'))
    {
        return None;
    }
    index += 1;
    let (month, next) = unicode_variable_digits(value, index, 1, 2)?;
    index = next;
    if !bytes
        .get(index)
        .is_some_and(|value| matches!(value, b'-' | b'/'))
    {
        return None;
    }
    index += 1;
    let (day, next) = unicode_variable_digits(value, index, 1, 2)?;
    index = next;

    let date_end = index;
    let mut saw_whitespace = false;
    while let Some(character) = value.get(index..)?.chars().next() {
        if !character.is_whitespace() {
            break;
        }
        saw_whitespace = true;
        index += character.len_utf8();
    }
    let time = if saw_whitespace {
        (|| {
            let (hour, next) = unicode_variable_digits(value, index, 1, 2)?;
            let minute_start = next.checked_add(1)?;
            if bytes.get(next) != Some(&b':') {
                return None;
            }
            let (minute, mut time_end) = unicode_digits_exact(value, minute_start, 2)?;
            let second = if bytes.get(time_end) == Some(&b':') {
                let (second, end) = unicode_digits_exact(value, time_end + 1, 2)?;
                time_end = end;
                second
            } else {
                0
            };
            Some((hour, minute, second, time_end))
        })()
    } else {
        None
    };
    let (time, end) = match time {
        Some((hour, minute, second, end)) => (Some((hour, minute, second)), end),
        None => (None, date_end),
    };
    Some((
        end,
        DateTimeParts {
            year: year as i32,
            month,
            day,
            time,
        },
    ))
}

fn unicode_digits_exact(value: &str, start: usize, count: usize) -> Option<(u32, usize)> {
    let (value, end, actual) = unicode_digits(value, start, count, count)?;
    (actual == count).then_some((value, end))
}

fn unicode_variable_digits(
    value: &str,
    start: usize,
    minimum: usize,
    maximum: usize,
) -> Option<(u32, usize)> {
    let (value, end, _) = unicode_digits(value, start, minimum, maximum)?;
    Some((value, end))
}

fn unicode_digits(
    value: &str,
    start: usize,
    minimum: usize,
    maximum: usize,
) -> Option<(u32, usize, usize)> {
    let mut end = start;
    let mut parsed = 0;
    let mut count = 0;
    while count < maximum {
        let Some(character) = value.get(end..)?.chars().next() else {
            break;
        };
        let Some(digit) = unicode_decimal_digit(character) else {
            break;
        };
        parsed = parsed * 10 + digit;
        count += 1;
        end += character.len_utf8();
    }
    if count < minimum {
        return None;
    }
    Some((parsed, end, count))
}

// Python 3.11's oracle uses Unicode 15.0 `\d`/`int` semantics. Every Nd run
// is ten digits except the five adjacent mathematical digit alphabets.
const UNICODE_DECIMAL_RANGES: &[(u32, u32)] = &[
    (0x00030, 0x00039),
    (0x00660, 0x00669),
    (0x006F0, 0x006F9),
    (0x007C0, 0x007C9),
    (0x00966, 0x0096F),
    (0x009E6, 0x009EF),
    (0x00A66, 0x00A6F),
    (0x00AE6, 0x00AEF),
    (0x00B66, 0x00B6F),
    (0x00BE6, 0x00BEF),
    (0x00C66, 0x00C6F),
    (0x00CE6, 0x00CEF),
    (0x00D66, 0x00D6F),
    (0x00DE6, 0x00DEF),
    (0x00E50, 0x00E59),
    (0x00ED0, 0x00ED9),
    (0x00F20, 0x00F29),
    (0x01040, 0x01049),
    (0x01090, 0x01099),
    (0x017E0, 0x017E9),
    (0x01810, 0x01819),
    (0x01946, 0x0194F),
    (0x019D0, 0x019D9),
    (0x01A80, 0x01A89),
    (0x01A90, 0x01A99),
    (0x01B50, 0x01B59),
    (0x01BB0, 0x01BB9),
    (0x01C40, 0x01C49),
    (0x01C50, 0x01C59),
    (0x0A620, 0x0A629),
    (0x0A8D0, 0x0A8D9),
    (0x0A900, 0x0A909),
    (0x0A9D0, 0x0A9D9),
    (0x0A9F0, 0x0A9F9),
    (0x0AA50, 0x0AA59),
    (0x0ABF0, 0x0ABF9),
    (0x0FF10, 0x0FF19),
    (0x104A0, 0x104A9),
    (0x10D30, 0x10D39),
    (0x11066, 0x1106F),
    (0x110F0, 0x110F9),
    (0x11136, 0x1113F),
    (0x111D0, 0x111D9),
    (0x112F0, 0x112F9),
    (0x11450, 0x11459),
    (0x114D0, 0x114D9),
    (0x11650, 0x11659),
    (0x116C0, 0x116C9),
    (0x11730, 0x11739),
    (0x118E0, 0x118E9),
    (0x11950, 0x11959),
    (0x11C50, 0x11C59),
    (0x11D50, 0x11D59),
    (0x11DA0, 0x11DA9),
    (0x11F50, 0x11F59),
    (0x16A60, 0x16A69),
    (0x16AC0, 0x16AC9),
    (0x16B50, 0x16B59),
    (0x1D7CE, 0x1D7FF),
    (0x1E140, 0x1E149),
    (0x1E2F0, 0x1E2F9),
    (0x1E4F0, 0x1E4F9),
    (0x1E950, 0x1E959),
    (0x1FBF0, 0x1FBF9),
];

fn unicode_decimal_digit(character: char) -> Option<u32> {
    let codepoint = character as u32;
    UNICODE_DECIMAL_RANGES.iter().find_map(|(start, end)| {
        (*start..=*end)
            .contains(&codepoint)
            .then(|| (codepoint - start) % 10)
    })
}

fn nonempty_python_text(value: Option<&Value>) -> Option<String> {
    let value = python_text(value);
    (!value.is_empty()).then_some(value)
}

fn python_text(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) | Some(Value::Bool(false)) => String::new(),
        Some(Value::String(value)) => value.clone(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Number(value)) if value.as_f64() == Some(0.0) => String::new(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Array(values)) if values.is_empty() => String::new(),
        Some(Value::Object(values)) if values.is_empty() => String::new(),
        Some(value) => value.to_string(),
    }
}

fn percent_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            let high = hex_value(bytes[index + 1]);
            let low = hex_value(bytes[index + 2]);
            if let (Some(high), Some(low)) = (high, low) {
                output.push((high << 4) | low);
                index += 3;
                continue;
            }
        }
        output.push(bytes[index]);
        index += 1;
    }
    String::from_utf8_lossy(&output).into_owned()
}

fn hex_value(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

fn safe_relative_string(path: &Path) -> Result<String> {
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(MihoError::Visualizer(format!(
            "unsafe visualizer context path: {}",
            path.display()
        )));
    }
    Ok(path.to_string_lossy().replace('\\', "/"))
}

fn validate_webp(bytes: &[u8]) -> Result<()> {
    let declared_size = bytes
        .get(4..8)
        .and_then(|value| value.try_into().ok())
        .map(u32::from_le_bytes)
        .map(|value| value as usize);
    if bytes.get(..4) != Some(b"RIFF")
        || bytes.get(8..12) != Some(b"WEBP")
        || declared_size != bytes.len().checked_sub(8)
    {
        return Err(MihoError::Visualizer(
            "avatar payload is not a complete WebP RIFF file".into(),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::{json, Value};
    use sha2::{Digest, Sha256};

    use super::*;

    const AVATAR: &[u8] = &[
        82, 73, 70, 70, 30, 0, 0, 0, 87, 69, 66, 80, 86, 80, 56, 76, 17, 0, 0, 0, 47, 1, 64, 0, 0,
        7, 208, 177, 150, 116, 189, 255, 129, 136, 232, 127, 0, 0,
    ];

    fn normalized_hash(bytes: &[u8]) -> String {
        let text = String::from_utf8(bytes.to_vec()).unwrap();
        let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
        format!("{:x}", Sha256::digest(normalized.as_bytes()))
    }

    #[test]
    fn trusted_static_asset_api_excludes_mutable_visualizer_data() {
        assert!(visualizer_static_asset("hsr", "index.html").is_some());
        assert!(visualizer_static_asset("zzz", "app.js").is_some());
        assert!(visualizer_static_asset("hsr", "styles.css").is_some());
        assert!(visualizer_static_asset("hsr", "data.json").is_none());
        assert!(visualizer_static_asset("hsr", "assets/avatars/a.webp").is_none());
        assert!(visualizer_static_asset("other", "app.js").is_none());
    }

    #[test]
    fn context_rejects_traversal_bad_slugs_and_invalid_webp() {
        let mut context = VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        assert!(context.require_local_datetime().is_err());
        assert!(context.add_sidecar_bytes("../escape.json", b"{}").is_err());
        assert!(context.add_avatar_webp("../escape", AVATAR).is_err());
        assert!(context.add_avatar_webp("agent-alpha", b"not-webp").is_err());
    }

    #[test]
    fn explicit_datetime_and_banner_status_match_python_boundaries() {
        let at = |hour, minute| {
            NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(hour, minute, 0)
                .unwrap()
        };
        let context = VisualizerContext::new_with_local_datetime(at(13, 0));
        assert_eq!(context.require_local_datetime().unwrap(), at(13, 0));
        assert_eq!(context.local_date, at(13, 0).date());

        let timed = json!({
            "status": "current",
            "date_range": "2026-07-12 12:00 至 2026-07-12 14:00"
        });
        assert_eq!(effective_banner_status(&timed, at(10, 0)).unwrap(), "next");
        assert_eq!(
            effective_banner_status(&timed, at(13, 0)).unwrap(),
            "current"
        );
        assert_eq!(
            effective_banner_status(&timed, at(15, 0)).unwrap(),
            "previous"
        );

        for separator in ["\u{3000}", "\u{00a0}"] {
            let unicode_whitespace = json!({
                "status": "current",
                "start_at": format!("2026-07-12{separator}12:00:00"),
                "end_at": format!("2026-07-12{separator}14:00:00")
            });
            assert_eq!(
                effective_banner_status(&unicode_whitespace, at(13, 0)).unwrap(),
                "current"
            );
        }
        for (start, end) in [
            (
                "２０２６-０７-１２　１２:００:００",
                "２０２６-０７-１２　１４:００:００",
            ),
            ("٢٠٢٦-٠٧-١٢ ١٢:٠٠:٠٠", "٢٠٢٦-٠٧-١٢ ١٤:٠٠:٠٠"),
        ] {
            let unicode_digits = json!({"status":"current", "start_at":start, "end_at":end});
            assert_eq!(
                effective_banner_status(&unicode_digits, at(10, 0)).unwrap(),
                "next"
            );
            assert_eq!(
                effective_banner_status(&unicode_digits, at(13, 0)).unwrap(),
                "current"
            );
        }
        let missing_whitespace = json!({
            "status": "current",
            "start_at": "2026-07-1212:00:00",
            "end_at": "2026-07-1214:00:00"
        });
        assert_eq!(
            effective_banner_status(&missing_whitespace, at(13, 0)).unwrap(),
            "previous"
        );

        let ignored_third_match = json!({
            "status": "current",
            "date_range": "2026-07-12 12:00 - 2026-07-12 14:00 (bad note 2026-99-99)"
        });
        assert_eq!(
            effective_banner_status(&ignored_third_match, at(13, 0)).unwrap(),
            "current"
        );

        let date_range = json!({
            "status": "current",
            "date_range": "2026-07-12 - 2026-07-12"
        });
        assert_eq!(
            effective_banner_status(&date_range, at(23, 59)).unwrap(),
            "current"
        );
        let explicit_end = json!({"status":"current", "end_at":"2026-07-12"});
        assert_eq!(
            effective_banner_status(&explicit_end, at(13, 0)).unwrap(),
            "previous"
        );
        assert!(effective_banner_status(
            &json!({"status":"current", "start_at":"2026-99-99"}),
            at(13, 0)
        )
        .is_err());
        assert!(effective_banner_status(
            &json!({"status":"current", "start_at":"0000-01-01"}),
            at(13, 0)
        )
        .is_err());
    }

    #[test]
    fn hsr_static_assets_and_avatar_match_the_versioned_contract() {
        let contract: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/visualizer_contract/contract.json"
        ))
        .unwrap();
        let mut context = VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        context.add_avatar_webp("agent-alpha", AVATAR).unwrap();
        let mut bundle = ArtifactBundle::default();
        attach_hsr_static_assets(&mut bundle).unwrap();
        attach_avatar_assets(&mut bundle, &context).unwrap();

        for name in ["app.js", "index.html", "styles.css"] {
            let expected = contract["static_text_sha256"]["hsr"][name]
                .as_str()
                .unwrap();
            assert_eq!(
                normalized_hash(bundle.get(format!("visualizer/{name}")).unwrap()),
                expected
            );
        }
        let avatar = bundle
            .get("visualizer/assets/avatars/agent-alpha.webp")
            .unwrap();
        assert_eq!(
            format!("{:x}", Sha256::digest(avatar)),
            contract["binary_sha256"]["hsr"]["assets/avatars/agent-alpha.webp"]
                .as_str()
                .unwrap()
        );
        assert_eq!(
            local_avatar_url(&context, "agent-alpha"),
            "./assets/avatars/agent-alpha.webp"
        );
        assert_eq!(local_avatar_url(&context, "missing"), "");
    }

    #[test]
    fn zzz_static_assets_match_the_versioned_contract() {
        let contract: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/visualizer_contract/contract.json"
        ))
        .unwrap();
        let mut bundle = ArtifactBundle::default();
        attach_zzz_static_assets(&mut bundle).unwrap();

        for name in ["app.js", "index.html", "styles.css"] {
            let expected = contract["static_text_sha256"]["zzz"][name]
                .as_str()
                .unwrap();
            assert_eq!(
                normalized_hash(bundle.get(format!("visualizer/{name}")).unwrap()),
                expected
            );
        }
    }

    #[test]
    fn hub_assets_and_safe_segments_match_the_versioned_contract() {
        let contract: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/visualizer_contract/contract.json"
        ))
        .unwrap();
        let mut bundle = ArtifactBundle::default();
        attach_visualizer_hub(&mut bundle, "out", "out_zzz").unwrap();
        let expected_files = contract["file_sets"]["hub"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_str().unwrap())
            .collect::<Vec<_>>();
        let actual_files = bundle
            .manifest()
            .into_iter()
            .map(|entry| entry.path)
            .collect::<Vec<_>>();
        assert_eq!(actual_files, expected_files);
        for name in ["app.js", "index.html", "styles.css"] {
            assert_eq!(
                normalized_hash(bundle.get(name).unwrap()),
                contract["static_text_sha256"]["hub"][name]
                    .as_str()
                    .unwrap()
            );
        }

        let mut encoded = ArtifactBundle::default();
        attach_visualizer_hub(&mut encoded, "HSR 中文 空格", "zzz\"><svg>").unwrap();
        let html = std::str::from_utf8(encoded.get("index.html").unwrap()).unwrap();
        assert!(
            html.contains("../HSR%20%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC/visualizer/index.html")
        );
        assert!(html.contains("../zzz%22%3E%3Csvg%3E/visualizer/index.html"));
        assert!(!html.contains("<svg>"));
        for value in ["", ".", "..", "a/b", "a\\b", "bad\nname"] {
            assert!(attach_visualizer_hub(&mut ArtifactBundle::default(), "out", value).is_err());
        }
    }

    #[test]
    fn shared_helpers_preserve_csv_strings_and_reject_active_urls() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_bytes("table.csv", b"\xef\xbb\xbfa,b\r\n1,2.0\r\n".to_vec())
            .unwrap();
        assert_eq!(
            read_csv_rows(&bundle, "table.csv").unwrap()[0],
            BTreeMap::from([("a".into(), "1".into()), ("b".into(), "2.0".into())])
        );
        for value in [
            "javascript:alert(1)",
            "data:text/html,owned",
            "file:///C:/secret",
            "../escape",
            "%252e%252e/escape",
            "\\\\server\\share",
            "/absolute",
        ] {
            assert_eq!(safe_relative_url(value), "");
            assert_eq!(safe_link_url(value), "");
        }
        assert_eq!(
            safe_relative_url("./assets/avatars/agent-alpha.webp"),
            "./assets/avatars/agent-alpha.webp"
        );
        assert_eq!(
            safe_link_url("https://invalid.example/source"),
            "https://invalid.example/source"
        );
        assert_eq!(
            safe_link_url("HTTPS://example.com/X"),
            "HTTPS://example.com/X"
        );
        assert_eq!(safe_link_url("HtTpS://[::1]/X"), "HtTpS://[::1]/X");
        assert_eq!(
            safe_link_url("http://[fe80::1%eth0]/"),
            "http://[fe80::1%eth0]/"
        );
        for value in [
            "https://[",
            "https://[not-an-ipv6]/X",
            "https://example.com／evil",
            "https://example.com：80/x",
            "https://user＠example.com/x",
            "https://example.com？x",
            "http://[fe80::1%eth%0]/",
        ] {
            assert_eq!(safe_link_url(value), "");
        }
    }

    #[test]
    fn visualizer_files_enter_the_refreshed_manifest_before_writeout() {
        let contract: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/visualizer_contract/contract.json"
        ))
        .unwrap();
        let mut context = VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        context.add_avatar_webp("agent-alpha", AVATAR).unwrap();
        let mut bundle = ArtifactBundle::default();
        attach_hsr_static_assets(&mut bundle).unwrap();
        attach_avatar_assets(&mut bundle, &context).unwrap();
        bundle
            .add_bytes("visualizer/data.json", b"{}".to_vec())
            .unwrap();
        bundle.refresh_manifest("artifact_manifest.json").unwrap();

        let manifest: Vec<crate::output::ArtifactManifestEntry> =
            serde_json::from_slice(bundle.get("artifact_manifest.json").unwrap()).unwrap();
        let actual = manifest
            .iter()
            .filter_map(|entry| entry.path.strip_prefix("visualizer/").map(str::to_owned))
            .collect::<Vec<_>>();
        let expected = contract["file_sets"]["hsr"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_str().unwrap().to_owned())
            .collect::<Vec<_>>();
        assert_eq!(actual, expected);
    }
}
