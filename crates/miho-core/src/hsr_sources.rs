use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::normalize::character_slug;

pub const PRYDWEN_TIER_URL: &str = "https://www.prydwen.gg/star-rail/tier-list";
pub const HOYOWIKI_CHARACTER_MENU_ID: &str = "104";
pub const HOYOWIKI_WIKI_APP: &str = "hsr";
pub const HOYOWIKI_SOURCE: &str = "HoYoWiki official hsr character menu_id=104";

pub fn prydwen_visible_url(mode: &str) -> Option<&'static str> {
    match mode {
        "moc" => Some("https://www.prydwen.gg/star-rail/memory-of-chaos"),
        "pf" => Some("https://www.prydwen.gg/star-rail/pure-fiction"),
        "as" => Some("https://www.prydwen.gg/star-rail/apocalyptic-shadow"),
        "aa" => Some("https://www.prydwen.gg/star-rail/anomaly-arbitration"),
        _ => None,
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct TierRow {
    pub tier_snapshot_id: String,
    pub fetched_at: String,
    pub tier_updated_at: String,
    pub tier_updated_date: String,
    pub tier_mode: String,
    pub tier_mode_cn: String,
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub prydwen_category: String,
    pub prydwen_role: String,
    pub role_group: String,
    pub role_group_cn: String,
    pub tier: String,
    pub rating: Option<i64>,
    pub special_rating: Value,
    pub tags: Value,
    pub marks: Value,
    pub is_new: Value,
    pub default_role: String,
    pub element: String,
    pub path: String,
    pub rarity: String,
    pub icon_url: String,
    pub source_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChangelogRow {
    pub changelog_date: String,
    pub source_url: String,
    pub character_slugs: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OfficialName {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub aliases: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct VisibleTeamScope {
    pub scope: String,
    pub rows: Vec<Value>,
}

pub fn decode_prydwen_payload(html: &str) -> String {
    let decoded = html
        .replace("\\\"", "\"")
        .replace("\\/", "/")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&");
    unescape_html(&decoded)
}

pub fn extract_last_updated(decoded: &str) -> String {
    value_after(decoded, "\"lastUpdated\":\"")
        .or_else(|| {
            between(decoded, "Last updated:", "</strong>").and_then(|v| v.rsplit('>').next())
        })
        .unwrap_or_default()
        .trim()
        .to_owned()
}

pub fn extract_characters(decoded: &str) -> Vec<Value> {
    let Some(index) = decoded.find("\"characters\":") else {
        return vec![];
    };
    let Some(start) = decoded[index..].find('[').map(|v| index + v) else {
        return vec![];
    };
    serde_json::Deserializer::from_str(&decoded[start..])
        .into_iter::<Value>()
        .next()
        .and_then(Result::ok)
        .and_then(|v| v.as_array().cloned())
        .unwrap_or_default()
}

pub fn build_tier_rows(characters: &[Value], updated_at: &str, snapshot: &str) -> Vec<TierRow> {
    build_tier_rows_at(characters, updated_at, snapshot, "")
}

pub fn build_tier_rows_at(
    characters: &[Value],
    updated_at: &str,
    snapshot: &str,
    fetched_at: &str,
) -> Vec<TierRow> {
    let mut output = vec![];
    for character in characters {
        let slug = character_slug(&string(character.get("slug")));
        if slug.is_empty() {
            continue;
        }
        for rating in character
            .get("tierRatings")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let category = string(rating.get("category"));
            let (role, group, group_cn) = match category.as_str() {
                "DPS" => ("DPS", "main_dps", "主C"),
                "Specialist" => ("Support DPS", "sub_dps", "副C"),
                "Amplifier" => ("Amplifier", "support", "辅助"),
                "Sustain" => ("Sustain", "sustain", "生存位"),
                other => (other, "unknown", "未知"),
            };
            for (mode, key, special, tags, marks) in [
                (
                    "moc",
                    "moc_rating",
                    "moc_special_rating",
                    "moc_tags",
                    "moc_marks",
                ),
                (
                    "pf",
                    "pure_rating",
                    "pure_special_rating",
                    "pure_tags",
                    "pure_marks",
                ),
                (
                    "as",
                    "apo_rating",
                    "apo_special_rating",
                    "apo_tags",
                    "apo_marks",
                ),
            ] {
                let raw = rating.get(key).and_then(Value::as_i64);
                output.push(TierRow {
                    tier_snapshot_id: snapshot.into(),
                    fetched_at: fetched_at.into(),
                    tier_updated_at: updated_at.into(),
                    tier_updated_date: prydwen_updated_date(updated_at),
                    tier_mode: mode.into(),
                    tier_mode_cn: match mode {
                        "moc" => "混沌回忆",
                        "pf" => "虚构叙事",
                        "as" => "末日幻影",
                        _ => mode,
                    }
                    .into(),
                    character_slug: slug.clone(),
                    character_name_en: string(character.get("name")),
                    character_name_cn: String::new(),
                    prydwen_category: category.clone(),
                    prydwen_role: role.into(),
                    role_group: group.into(),
                    role_group_cn: group_cn.into(),
                    tier: rating_to_tier(raw).into(),
                    rating: raw,
                    special_rating: rating.get(special).cloned().unwrap_or(Value::Null),
                    tags: python_or(
                        rating.get(tags),
                        rating.get("tags"),
                        Value::String(String::new()),
                    ),
                    marks: python_or(rating.get(marks), None, Value::String(String::new())),
                    is_new: python_or(
                        rating.get("is_new"),
                        character.get("isNew"),
                        Value::String(String::new()),
                    ),
                    default_role: string(character.get("defaultRole")),
                    element: string(character.get("element")),
                    path: string(character.get("path")),
                    rarity: string(character.get("rarity")),
                    icon_url: string(character.get("smallImage")),
                    source_url: PRYDWEN_TIER_URL.into(),
                });
            }
        }
    }
    output
}

pub fn extract_changelog(decoded: &str) -> Vec<ChangelogRow> {
    let mut headings = vec![];
    let mut cursor = 0;
    while let Some(relative) = decoded[cursor..].find("<h6") {
        let start = cursor + relative;
        let Some(close) = decoded[start..].find("</h6>").map(|v| start + v + 5) else {
            break;
        };
        let heading = strip_html(&decoded[start..close]);
        if is_changelog_date(&heading) {
            headings.push((start, close, heading));
        }
        cursor = close;
    }
    headings
        .iter()
        .enumerate()
        .filter_map(|(index, (_, start, date))| {
            let end = headings
                .get(index + 1)
                .map(|v| v.0)
                .unwrap_or(decoded.len());
            let chunk = &decoded[*start..end];
            let text = strip_html(chunk);
            if text.is_empty() {
                return None;
            }
            let mut slugs = values_after(chunk, "data-slug=\"");
            slugs.sort();
            slugs.dedup();
            Some(ChangelogRow {
                changelog_date: prydwen_updated_date(date),
                source_url: PRYDWEN_TIER_URL.into(),
                character_slugs: slugs.join(";"),
                text,
            })
        })
        .collect()
}

pub fn extract_visible_teams(html: &str) -> BTreeMap<String, Vec<Value>> {
    extract_visible_team_scopes(html)
        .into_iter()
        .map(|scope| (scope.scope, scope.rows))
        .collect()
}

/// Extract visible teams while retaining Python dictionary insertion order.
/// Export adapters should use this ordered form; `extract_visible_teams` is a
/// lookup-oriented compatibility wrapper.
pub fn extract_visible_team_scopes(html: &str) -> Vec<VisibleTeamScope> {
    let mut output = Vec::new();
    if let Some(root) = extract_next_data(html) {
        collect_team_lists(&root, &mut output);
    }
    let unescaped = unescape_html(html);
    let mut variants = vec![unescaped.clone()];
    if let Some(decoded) = decode_unicode_escapes(&unescaped) {
        variants.push(decoded);
    }
    for text in variants {
        for value in json_values_after_key(&text, "teams") {
            collect_team_value(&value, &mut output);
        }
    }
    output
}

fn json_values_after_key(text: &str, key: &str) -> Vec<Value> {
    let needle = format!("\"{key}\"");
    let mut cursor = 0;
    let mut out = vec![];
    while let Some(i) = text[cursor..].find(&needle) {
        let at = cursor + i + needle.len();
        let Some(colon) = text[at..].find(':').map(|v| at + v + 1) else {
            break;
        };
        let tail = text[colon..].trim_start();
        let whitespace = text[colon..].len() - tail.len();
        let mut stream = serde_json::Deserializer::from_str(tail).into_iter::<Value>();
        if let Some(Ok(v)) = stream.next() {
            let consumed = stream.byte_offset();
            out.push(v);
            cursor = colon + whitespace + consumed;
        } else {
            cursor = at;
        }
    }
    out
}
fn collect_team_value(value: &Value, output: &mut Vec<VisibleTeamScope>) {
    if let Some(map) = value.as_object() {
        for (scope, rows) in map {
            if let Some(rows) = rows.as_array().filter(|v| looks_like_team_list(v)) {
                append_team_rows(output, scope, rows);
            }
        }
    } else if let Some(rows) = value.as_array().filter(|v| looks_like_team_list(v)) {
        append_team_rows(output, "all", rows);
    }
}

pub fn official_names(zh: &[Value], en: &[Value]) -> BTreeMap<String, OfficialName> {
    let zh = zh
        .iter()
        .filter_map(|v| {
            Some((
                python_string(v.get("entry_page_id")),
                clean_name(v.get("name"))?,
            ))
        })
        .collect::<BTreeMap<_, _>>();
    let mut output = BTreeMap::new();
    for row in en {
        let id = python_string(row.get("entry_page_id"));
        let Some(cn) = zh.get(&id) else { continue };
        let Some(name) = clean_name(row.get("name")) else {
            continue;
        };
        let slug = character_slug(&name);
        output.insert(
            slug.clone(),
            OfficialName {
                character_slug: slug,
                character_name_en: name,
                character_name_cn: cn.clone(),
                aliases: String::new(),
            },
        );
    }
    for (alias, target) in [
        ("blade-mortenax", "mortenax-blade"),
        ("himeko-nova", "himeko-nova"),
        ("imbibitor-lunae", "dan-heng-imbibitor-lunae"),
        ("march-7th-evernight", "evernight"),
        ("march-7th-swordmaster", "march-7th-the-hunt"),
        ("silver-wolf-lv-999", "silver-wolf-lv999"),
        ("tingyun-fugue", "fugue"),
        ("topaz", "topaz-and-numby"),
        ("trailblazer-destruction", "trailblazer-the-destruction"),
        ("trailblazer-harmony", "trailblazer-the-harmony"),
        ("trailblazer-preservation", "trailblazer-the-preservation"),
        ("trailblazer-remembrance", "trailblazer-remembrance"),
    ] {
        if let Some(target_row) = output.get(target).cloned() {
            let mut row = target_row;
            row.character_slug = alias.into();
            row.aliases = target.into();
            output.insert(alias.into(), row);
        }
    }
    output
}

fn collect_team_lists(value: &Value, output: &mut Vec<VisibleTeamScope>) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                if let Some(rows) = child.as_array().filter(|v| looks_like_team_list(v)) {
                    append_team_rows(output, key, rows);
                } else if key == "teams" {
                    if let Some(scopes) = child.as_object() {
                        for (scope, rows) in scopes {
                            if let Some(rows) = rows.as_array().filter(|v| looks_like_team_list(v))
                            {
                                append_team_rows(output, scope, rows);
                            }
                        }
                    }
                } else {
                    collect_team_lists(child, output);
                }
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_team_lists(item, output);
            }
        }
        _ => {}
    }
}

fn append_team_rows(output: &mut Vec<VisibleTeamScope>, scope: &str, rows: &[Value]) {
    if let Some(existing) = output.iter_mut().find(|item| item.scope == scope) {
        existing.rows.extend_from_slice(rows);
    } else {
        output.push(VisibleTeamScope {
            scope: scope.to_owned(),
            rows: rows.to_vec(),
        });
    }
}
fn looks_like_team_list(rows: &[Value]) -> bool {
    rows.first().and_then(Value::as_object).is_some_and(|v| {
        ["char_one", "char_two", "char_three", "char_four"]
            .iter()
            .all(|k| v.contains_key(*k))
            || ["char_1", "char_2", "char_3", "char_4"]
                .iter()
                .all(|k| v.contains_key(*k))
    })
}
fn rating_to_tier(value: Option<i64>) -> &'static str {
    match value {
        Some(11) => "T0",
        Some(10) => "T0.5",
        Some(9) => "T1",
        Some(8) => "T1.5",
        Some(7) => "T2",
        Some(6) => "T3",
        Some(5) => "T4",
        Some(4) => "T5",
        _ => "",
    }
}
pub fn prydwen_updated_date(value: &str) -> String {
    let text = value.trim();
    for format in ["%d/%B/%Y", "%d/%b/%Y"] {
        if let Ok(date) = NaiveDate::parse_from_str(text, format) {
            return date.format("%Y-%m-%d").to_string();
        }
    }
    crate::normalize::parse_date(text)
}

pub fn tier_snapshot_id(updated_at: &str) -> String {
    prydwen_updated_date(updated_at).replace('-', "")
}
fn strip_html(value: &str) -> String {
    let value = remove_html_element(value, "script");
    let value = remove_html_element(&value, "style");
    let mut out = String::new();
    let mut tag = false;
    for c in value.chars() {
        match c {
            '<' => tag = true,
            '>' => {
                tag = false;
                out.push(' ')
            }
            _ if !tag => out.push(c),
            _ => {}
        }
    }
    unescape_html(&out)
        .replace("â", "↑")
        .replace("â", "↓")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn is_changelog_date(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 11
        && bytes[0..2].iter().all(u8::is_ascii_digit)
        && bytes[2] == b'/'
        && bytes[3..6].iter().all(u8::is_ascii_alphabetic)
        && bytes[6] == b'/'
        && bytes[7..11].iter().all(u8::is_ascii_digit)
}

fn extract_next_data(text: &str) -> Option<Value> {
    let mut cursor = 0;
    while let Some(relative) = text[cursor..].find("<script") {
        let start = cursor + relative;
        let open_end = text[start..].find('>').map(|offset| start + offset)?;
        let opening = &text[start..=open_end];
        if opening.contains("id=\"__NEXT_DATA__\"") || opening.contains("id='__NEXT_DATA__'") {
            let close = text[open_end + 1..]
                .find("</script>")
                .map(|offset| open_end + 1 + offset)?;
            return serde_json::from_str(&unescape_html(&text[open_end + 1..close])).ok();
        }
        cursor = open_end + 1;
    }
    None
}

fn decode_unicode_escapes(value: &str) -> Option<String> {
    let mut chars = value.chars().peekable();
    let mut output = String::with_capacity(value.len());
    while let Some(character) = chars.next() {
        if character != '\\' {
            output.push(character);
            continue;
        }
        let escaped = chars.next()?;
        match escaped {
            '\\' => output.push('\\'),
            '\'' => output.push('\''),
            '"' => output.push('"'),
            '/' => output.push('/'),
            'n' => output.push('\n'),
            'r' => output.push('\r'),
            't' => output.push('\t'),
            'b' => output.push('\u{0008}'),
            'f' => output.push('\u{000c}'),
            'u' => {
                let digits = chars.by_ref().take(4).collect::<String>();
                if digits.len() != 4 {
                    return None;
                }
                let mut code = u32::from_str_radix(&digits, 16).ok()?;
                if (0xd800..=0xdbff).contains(&code) {
                    let mut lookahead = chars.clone();
                    if lookahead.next() == Some('\\') && lookahead.next() == Some('u') {
                        let low_digits = lookahead.by_ref().take(4).collect::<String>();
                        if let Ok(low) = u32::from_str_radix(&low_digits, 16) {
                            if (0xdc00..=0xdfff).contains(&low) {
                                code = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00);
                                chars = lookahead;
                            }
                        }
                    }
                }
                output.push(char::from_u32(code).unwrap_or('\u{fffd}'));
            }
            'x' => {
                let digits = chars.by_ref().take(2).collect::<String>();
                if digits.len() != 2 {
                    return None;
                }
                let code = u32::from_str_radix(&digits, 16).ok()?;
                output.push(char::from_u32(code)?);
            }
            other => {
                output.push('\\');
                output.push(other);
            }
        }
    }
    Some(output)
}

fn unescape_html(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut cursor = 0;
    while let Some(relative) = value[cursor..].find('&') {
        let start = cursor + relative;
        output.push_str(&value[cursor..start]);
        let Some(relative_end) = value[start + 1..].find(';') else {
            output.push_str(&value[start..]);
            return output;
        };
        let end = start + 1 + relative_end;
        let entity = &value[start + 1..end];
        let decoded = match entity {
            "amp" => Some('&'),
            "quot" => Some('"'),
            "apos" | "#39" | "#x27" | "#X27" => Some('\''),
            "lt" => Some('<'),
            "gt" => Some('>'),
            "nbsp" => Some('\u{00a0}'),
            "ndash" => Some('–'),
            "mdash" => Some('—'),
            "hellip" => Some('…'),
            "lsquo" => Some('‘'),
            "rsquo" => Some('’'),
            "ldquo" => Some('“'),
            "rdquo" => Some('”'),
            "uarr" => Some('↑'),
            "darr" => Some('↓'),
            numeric if numeric.starts_with("#x") || numeric.starts_with("#X") => {
                u32::from_str_radix(&numeric[2..], 16)
                    .ok()
                    .and_then(char::from_u32)
            }
            numeric if numeric.starts_with('#') => {
                numeric[1..].parse::<u32>().ok().and_then(char::from_u32)
            }
            _ => None,
        };
        if let Some(character) = decoded {
            output.push(character);
        } else {
            output.push_str(&value[start..=end]);
        }
        cursor = end + 1;
    }
    output.push_str(&value[cursor..]);
    output
}

fn remove_html_element(value: &str, element: &str) -> String {
    let opening = format!("<{element}");
    let closing = format!("</{element}>");
    let mut output = String::with_capacity(value.len());
    let mut cursor = 0;
    while let Some(relative_start) = value[cursor..].find(&opening) {
        let start = cursor + relative_start;
        let Some(relative_end) = value[start..].find(&closing) else {
            break;
        };
        let end = start + relative_end + closing.len();
        output.push_str(&value[cursor..start]);
        output.push(' ');
        cursor = end;
    }
    output.push_str(&value[cursor..]);
    output
}

fn python_or(primary: Option<&Value>, secondary: Option<&Value>, fallback: Value) -> Value {
    primary
        .filter(|value| python_truthy(value))
        .or_else(|| secondary.filter(|value| python_truthy(value)))
        .cloned()
        .unwrap_or(fallback)
}

fn python_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().is_some_and(|value| value != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}
fn between<'a>(value: &'a str, start: &str, end: &str) -> Option<&'a str> {
    let a = value.find(start)? + start.len();
    let b = value[a..].find(end)? + a;
    Some(&value[a..b])
}
fn value_after<'a>(value: &'a str, start: &str) -> Option<&'a str> {
    let a = value.find(start)? + start.len();
    let b = value[a..].find('"')? + a;
    Some(&value[a..b])
}
fn values_after(value: &str, start: &str) -> Vec<String> {
    let mut out = vec![];
    let mut cursor = 0;
    while let Some(i) = value[cursor..].find(start) {
        let a = cursor + i + start.len();
        let Some(n) = value[a..].find('"') else { break };
        out.push(value[a..a + n].into());
        cursor = a + n + 1
    }
    out
}
fn string(value: Option<&Value>) -> String {
    value
        .filter(|value| python_truthy(value))
        .map(python_value_string)
        .unwrap_or_default()
}

fn python_string(value: Option<&Value>) -> String {
    value
        .map(python_value_string)
        .unwrap_or_else(|| "None".to_owned())
}

/// Convert a JSON-backed Prydwen field the way Python's `csv.writer` does.
/// Scalars remain plain cell values; containers use Python `repr` syntax.
pub fn python_csv_value(value: &Value) -> String {
    if value.is_null() {
        String::new()
    } else if let Value::String(value) = value {
        value.clone()
    } else {
        python_repr(value)
    }
}

fn python_value_string(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => value.clone(),
        Value::Array(_) | Value::Object(_) => python_repr(value),
    }
}

fn python_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => python_string_repr(value),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(python_repr)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        Value::Object(values) => format!(
            "{{{}}}",
            values
                .iter()
                .map(|(key, value)| format!("{}: {}", python_string_repr(key), python_repr(value)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn python_string_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut output = String::with_capacity(value.len() + 2);
    output.push(quote);
    for character in value.chars() {
        match character {
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            '\u{0008}' => output.push_str("\\x08"),
            '\u{000c}' => output.push_str("\\x0c"),
            character if character == quote => {
                output.push('\\');
                output.push(character);
            }
            character if character.is_control() => {
                use std::fmt::Write;
                let _ = write!(output, "\\x{:02x}", character as u32);
            }
            character => output.push(character),
        }
    }
    output.push(quote);
    output
}
fn clean_name(value: Option<&Value>) -> Option<String> {
    let v = string(value).replace('\u{a0}', " ").trim().to_owned();
    (!v.is_empty()).then_some(v)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn fixed_sources_match_python_oracle() {
        let html = include_str!("../../../tests/fixtures/hsr_prydwen_minimal.html");
        let decoded = decode_prydwen_payload(html);
        let updated = extract_last_updated(&decoded);
        let rows = build_tier_rows(&extract_characters(&decoded), &updated, "20260106");
        let moc = rows.iter().find(|row| row.tier_mode == "moc").unwrap();
        assert_eq!(
            (
                &updated,
                moc.character_slug.as_str(),
                moc.tier.as_str(),
                moc.prydwen_role.as_str()
            ),
            (
                &"06/Jan/2026".to_owned(),
                "march-7th",
                "T0.5",
                "Support DPS"
            )
        );
        assert_eq!(moc.special_rating, Value::String("E6".into()));
        let changelog = extract_changelog(&decoded);
        assert_eq!(
            (
                changelog[0].changelog_date.as_str(),
                changelog[0].character_slugs.as_str()
            ),
            ("2026-01-06", "march-7th")
        );
        assert_eq!(
            extract_visible_teams(html)["all"][0]["char_four"],
            "aventurine"
        );

        let names: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_prydwen_minimal_names.json"
        ))
        .unwrap();
        let mapped = official_names(
            names["zh"].as_array().unwrap(),
            names["en"].as_array().unwrap(),
        );
        assert_eq!(
            (
                mapped["march-7th"].character_name_en.as_str(),
                mapped["march-7th"].character_name_cn.as_str()
            ),
            ("March 7th", "三月七")
        );
        assert!(!mapped.contains_key("missing-chinese"));
    }

    #[test]
    fn tier_fields_follow_python_falsey_fallbacks_and_date_parsing() {
        let characters = vec![json!({
            "slug": "Fallback Tester",
            "name": "Fallback Tester",
            "isNew": "character-new",
            "rarity": 5,
            "tierRatings": [{
                "category": "DPS",
                "moc_rating": 11,
                "moc_tags": null,
                "tags": "generic-tag",
                "moc_marks": null,
                "is_new": false
            }]
        })];
        let rows = build_tier_rows_at(&characters, "06/01/2026", "20260106", "fixture-time");
        assert_eq!(rows.len(), 3);
        assert!(rows.iter().all(|row| {
            row.tier_updated_date == "2026-01-06"
                && row.fetched_at == "fixture-time"
                && row.tags == json!("generic-tag")
                && row.marks == json!("")
                && row.is_new == json!("character-new")
                && row.rarity == "5"
        }));
        assert_eq!(tier_snapshot_id("06/January/2026"), "20260106");
    }

    #[test]
    fn changelog_strips_non_content_and_decodes_entities() {
        let decoded = decode_prydwen_payload(
            r#"<h6>06/Jan/2026</h6><p>A &amp; B &#x2191;</p><script>ignored</script><style>ignored too</style>"#,
        );
        let rows = extract_changelog(&decoded);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].text, "A & B ↑");
    }

    #[test]
    fn visible_team_fallbacks_match_python_scan_boundaries() {
        let team = r#"{"char_1":"a","char_2":"b","char_3":"c","char_4":"d"}"#;
        let single_quoted_next = format!(
            r#"<script type='application/json' id='__NEXT_DATA__'>{{"props":{{"teams":{{"all":[{team}]}}}}}}</script>"#
        );
        assert_eq!(extract_visible_teams(&single_quoted_next)["all"].len(), 3);

        let escaped = format!(
            r#"<script>window.x={{\"teams\":{{\"all\":[{}]}}}}</script>"#,
            team.replace('"', "\\\"")
        );
        assert_eq!(extract_visible_teams(&escaped)["all"].len(), 1);

        let nested = format!(
            r#"<script>window.x={{"teams":{{"nested":{{"teams":{{"all":[{team}]}}}}}}}}</script>"#
        );
        assert!(extract_visible_teams(&nested).is_empty());

        let ordered = format!(
            r#"<script id="__NEXT_DATA__">{{"teams":{{"z_scope":[{team}],"a_scope":[{team}]}}}}</script>"#
        );
        assert_eq!(
            extract_visible_team_scopes(&ordered)
                .iter()
                .map(|item| item.scope.as_str())
                .collect::<Vec<_>>(),
            ["z_scope", "a_scope"]
        );
    }

    #[test]
    fn official_aliases_match_python_table() {
        let zh = vec![
            json!({"entry_page_id": 1, "name": "刃·摩腾纳克斯"}),
            json!({"entry_page_id": 2, "name": "姬子·诺瓦"}),
        ];
        let en = vec![
            json!({"entry_page_id": 1, "name": "Mortenax Blade"}),
            json!({"entry_page_id": 2, "name": "Himeko Nova"}),
        ];
        let names = official_names(&zh, &en);
        assert_eq!(names["blade-mortenax"].aliases, "mortenax-blade");
        assert_eq!(names["himeko-nova"].aliases, "himeko-nova");
    }

    #[test]
    fn json_fields_use_python_csv_container_format() {
        assert_eq!(python_csv_value(&Value::Null), "");
        assert_eq!(python_csv_value(&json!("FUA")), "FUA");
        assert_eq!(
            python_csv_value(&json!(["FUA", "O'Brien", true, null])),
            r#"['FUA', "O'Brien", True, None]"#
        );
        assert_eq!(
            python_csv_value(&json!({"tag": "AoE", "count": 2})),
            "{'tag': 'AoE', 'count': 2}"
        );
    }
}
