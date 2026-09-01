use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{
    normalize::character_slug,
    supplemental::ZzzMode,
    zzz_sources::{extract_phase_updates_from_html, python_value_string, PhaseUpdate},
};

pub const TIER_URL: &str = "https://www.prydwen.gg/zenless/tier-list";
pub const SHIYU_DEFENSE_URL: &str = "https://www.prydwen.gg/zenless/shiyu-defense/";
pub const DEADLY_ASSAULT_URL: &str = "https://www.prydwen.gg/zenless/deadly-assault/";

pub const fn team_url(mode: ZzzMode) -> &'static str {
    match mode {
        ZzzMode::Sd => SHIYU_DEFENSE_URL,
        ZzzMode::Da => DEADLY_ASSAULT_URL,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
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
    pub rating: String,
    pub tags: String,
    pub marks: String,
    pub is_new: String,
    pub element: String,
    pub element_cn: String,
    pub style: String,
    pub style_cn: String,
    pub faction: String,
    pub rarity: String,
    pub icon_url: String,
    pub source_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChangelogRow {
    pub changelog_date: String,
    pub source_url: String,
    pub character_slugs: String,
    pub text: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ParsedPrydwen {
    pub last_updated: String,
    pub snapshot_id: String,
    pub teams: VisibleTeams,
    pub tiers: Vec<TierRow>,
    pub changelog: Vec<ChangelogRow>,
    pub phases: BTreeMap<String, PhaseUpdate>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct VisibleTeams {
    entries: Vec<(String, Vec<Value>)>,
}

impl VisibleTeams {
    pub fn get(&self, scope: &str) -> Option<&[Value]> {
        self.entries
            .iter()
            .find(|(key, _)| key == scope)
            .map(|(_, rows)| rows.as_slice())
    }

    pub fn iter(&self) -> impl Iterator<Item = (&str, &[Value])> {
        self.entries
            .iter()
            .map(|(scope, rows)| (scope.as_str(), rows.as_slice()))
    }

    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.entries.iter().map(|(scope, _)| scope.as_str())
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn into_entries(self) -> Vec<(String, Vec<Value>)> {
        self.entries
    }

    fn extend(&mut self, scope: &str, rows: &[Value]) {
        if let Some((_, existing)) = self.entries.iter_mut().find(|(key, _)| key == scope) {
            existing.extend(rows.iter().cloned());
        } else {
            self.entries.push((scope.to_owned(), rows.to_vec()));
        }
    }
}

pub fn decode_payload(text: &str) -> String {
    html_unescape(
        &text
            .replace("\\\"", "\"")
            .replace("\\/", "/")
            .replace("\\u003c", "<")
            .replace("\\u003e", ">")
            .replace("\\u0026", "&"),
    )
}

pub fn parse_document(html: &str, fetched_at: &str) -> ParsedPrydwen {
    let decoded = decode_payload(html);
    let last_updated = value_after_string_key(&decoded, "lastUpdated")
        .unwrap_or_else(|| last_updated_html(&decoded));
    let snapshot_id = date_from_prydwen(&last_updated).replace('-', "");
    let characters = values_after_key(&decoded, "characters")
        .into_iter()
        .next()
        .and_then(|v| v.as_array().cloned())
        .unwrap_or_default();
    ParsedPrydwen {
        teams: extract_visible_teams_decoded(&decoded),
        tiers: build_tiers(&characters, &last_updated, &snapshot_id, fetched_at),
        changelog: extract_changelog(&decoded),
        phases: extract_phase_updates_from_html(html),
        last_updated,
        snapshot_id,
    }
}

pub fn extract_visible_teams(text: &str) -> VisibleTeams {
    extract_visible_teams_decoded(&decode_payload(text))
}

fn extract_visible_teams_decoded(text: &str) -> VisibleTeams {
    let mut output = VisibleTeams::default();
    for value in values_after_key(text, "teams") {
        let Some(scopes) = value.as_object() else {
            continue;
        };
        for (scope, rows) in scopes {
            let Some(rows) = rows.as_array() else {
                continue;
            };
            if rows.first().is_some_and(looks_like_team) {
                output.extend(scope, rows);
            }
        }
    }
    output
}

fn build_tiers(chars: &[Value], updated: &str, snapshot: &str, fetched: &str) -> Vec<TierRow> {
    let mut output = vec![];
    for char in chars {
        let name = field_or_empty(char, "name");
        let raw_slug = char
            .get("slug")
            .filter(|value| python_truthy(value))
            .map(python_string)
            .unwrap_or_else(|| name.clone());
        let slug = character_slug(&raw_slug);
        if slug.is_empty() {
            continue;
        }
        for rating in char
            .get("tierRatings")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let category = field_or_empty(rating, "category");
            let raw_rating = rating.get("rating").map(python_string).unwrap_or_default();
            let (role, group, group_cn) = category_role(&category);
            let element = field_or_empty(char, "element");
            let style = field_or_empty(char, "style");
            for (mode, mode_cn) in [("sd", "式舆防卫"), ("da", "危局强袭")] {
                output.push(TierRow {
                    tier_snapshot_id: snapshot.into(),
                    fetched_at: fetched.into(),
                    tier_updated_at: updated.into(),
                    tier_updated_date: date_from_prydwen(updated),
                    tier_mode: mode.into(),
                    tier_mode_cn: mode_cn.into(),
                    character_slug: slug.clone(),
                    character_name_en: name.clone(),
                    character_name_cn: String::new(),
                    prydwen_category: category.clone(),
                    prydwen_role: role.into(),
                    role_group: group.into(),
                    role_group_cn: group_cn.into(),
                    tier: rating_tier(rating.get("rating")).into(),
                    rating: raw_rating.clone(),
                    tags: field_or_empty(rating, "tags"),
                    marks: field_or_empty(rating, "marks"),
                    is_new: field_or_empty(char, "isNew"),
                    element: element.clone(),
                    element_cn: element_cn(&element).into(),
                    style: style.clone(),
                    style_cn: style_cn(&style).into(),
                    faction: field_or_empty(char, "faction"),
                    rarity: field_or_empty(char, "rarity"),
                    icon_url: field_or_empty(char, "smallImage"),
                    source_url: TIER_URL.into(),
                });
            }
        }
    }
    output
}

fn extract_changelog(text: &str) -> Vec<ChangelogRow> {
    let mut heads = vec![];
    let mut at = 0;
    while let Some((pos, tag)) = ["h5", "h6"]
        .into_iter()
        .filter_map(|tag| text[at..].find(&format!("<{tag}")).map(|pos| (pos, tag)))
        .min_by_key(|(pos, _)| *pos)
    {
        let start = at + pos;
        let Some(gt) = text[start..].find('>') else {
            break;
        };
        let body = start + gt + 1;
        let closing = format!("</{tag}>");
        let Some(end) = text[body..].find(&closing) else {
            break;
        };
        let heading = &text[body..body + end];
        let close = body + end + closing.len();
        if is_changelog_date(heading) {
            heads.push((start, close, heading.to_owned()));
        }
        at = close;
    }
    let mut out = vec![];
    for i in 0..heads.len() {
        let end = heads.get(i + 1).map(|v| v.0).unwrap_or(text.len());
        let chunk = &text[heads[i].1..end];
        let date = date_from_prydwen(&heads[i].2);
        let clean = strip_html(chunk);
        if clean.is_empty() {
            continue;
        }
        let mut slugs = vec![];
        let mut rest = chunk;
        while let Some(p) = rest.find("data-slug=\"") {
            rest = &rest[p + 11..];
            if let Some(e) = rest.find('"') {
                slugs.push(rest[..e].to_owned());
                rest = &rest[e + 1..]
            } else {
                break;
            }
        }
        slugs.sort();
        slugs.dedup();
        out.push(ChangelogRow {
            changelog_date: date,
            source_url: TIER_URL.into(),
            character_slugs: slugs.join(";"),
            text: clean,
        });
    }
    out
}

fn values_after_key(text: &str, key: &str) -> Vec<Value> {
    let needle = format!("\"{key}\"");
    let mut out = vec![];
    let mut at = 0;
    while let Some(found) = text[at..].find(&needle) {
        let key_start = at + found;
        let key_end = key_start + needle.len();
        let Some(colon) = text[key_end..].find(':') else {
            break;
        };
        let after_colon = key_end + colon + 1;
        let whitespace = text[after_colon..].len() - text[after_colon..].trim_start().len();
        let value_start = after_colon + whitespace;
        let mut stream =
            serde_json::Deserializer::from_str(&text[value_start..]).into_iter::<Value>();
        if let Some(Ok(value)) = stream.next() {
            out.push(value);
            at = value_start + stream.byte_offset();
        } else {
            at = key_end;
        }
    }
    out
}
fn value_after_string_key(text: &str, key: &str) -> Option<String> {
    values_after_key(text, key)
        .into_iter()
        .find_map(|v| v.as_str().map(str::to_owned))
}
fn looks_like_team(v: &Value) -> bool {
    v.as_object().is_some_and(|o| {
        ["char_one", "char_two", "char_three"]
            .iter()
            .all(|key| o.contains_key(*key))
    })
}

fn field_or_empty(value: &Value, key: &str) -> String {
    value
        .get(key)
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_default()
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

fn python_string(value: &Value) -> String {
    if value.is_null() {
        String::new()
    } else {
        python_value_string(value)
    }
}
fn category_role(v: &str) -> (&str, &str, &str) {
    match v {
        "CritDPS" => ("直伤主C", "crit_dps", "直伤主C"),
        "AnoDPS" => ("异常主C", "anomaly_dps", "异常主C"),
        "Support" => ("辅助", "support", "辅助"),
        _ => (v, "unknown", "未知"),
    }
}
fn rating_tier(value: Option<&Value>) -> &'static str {
    let Some(value) = value.and_then(Value::as_f64) else {
        return "";
    };
    match value {
        11.0 => "T0",
        10.0 => "T0.5",
        9.0 => "T1",
        8.0 => "T1.5",
        7.0 => "T2",
        6.0 => "T3",
        5.0 => "T4",
        4.0 => "T5",
        _ => "",
    }
}
fn element_cn(v: &str) -> &str {
    match v {
        "Fire" => "火",
        "Ice" => "冰",
        "Electric" => "电",
        "Ether" => "以太",
        "Physical" => "物理",
        "Wind" => "风",
        "Auric Ink" => "玄墨",
        _ => "",
    }
}
fn style_cn(v: &str) -> &str {
    match v {
        "Attack" => "强攻",
        "Anomaly" => "异常",
        "Stun" => "击破",
        "Support" => "支援",
        "Defense" | "Defence" => "防护",
        "Rupture" => "命破",
        _ => "",
    }
}
fn date_from_prydwen(v: &str) -> String {
    let value = v.trim();
    for fmt in ["%d/%B/%Y", "%d/%b/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"] {
        if let Ok(d) = chrono::NaiveDate::parse_from_str(value, fmt) {
            return d.format("%Y-%m-%d").to_string();
        }
    }
    value.to_owned()
}
fn last_updated_html(t: &str) -> String {
    t.split("Last updated:")
        .nth(1)
        .and_then(|v| v.split("<strong>").nth(1))
        .and_then(|v| v.split("</strong>").next())
        .unwrap_or("")
        .trim()
        .into()
}

fn is_changelog_date(value: &str) -> bool {
    let parts = value.split('/').collect::<Vec<_>>();
    parts.len() == 3
        && parts[0].len() == 2
        && parts[0].bytes().all(|byte| byte.is_ascii_digit())
        && !parts[1].is_empty()
        && parts[1].bytes().all(|byte| byte.is_ascii_alphabetic())
        && parts[2].len() == 4
        && parts[2].bytes().all(|byte| byte.is_ascii_digit())
}

fn strip_html(t: &str) -> String {
    let without_script = remove_html_blocks(t, "script");
    let without_style = remove_html_blocks(&without_script, "style");
    let mut out = String::new();
    let mut rest = without_style.as_str();
    while let Some(start) = rest.find('<') {
        out.push_str(&rest[..start]);
        let tail = &rest[start..];
        let Some(end) = tail.find('>') else {
            out.push_str(tail);
            rest = "";
            break;
        };
        if end == 1 {
            out.push_str("<>");
        } else {
            out.push(' ');
        }
        rest = &tail[end + 1..];
    }
    out.push_str(rest);
    html_unescape(&out)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn remove_html_blocks(text: &str, tag: &str) -> String {
    let opening = format!("<{tag}");
    let closing = format!("</{tag}>");
    let mut output = String::new();
    let mut rest = text;
    while let Some(start) = rest.find(&opening) {
        output.push_str(&rest[..start]);
        let tail = &rest[start..];
        let Some(end) = tail.find(&closing) else {
            output.push_str(tail);
            return output;
        };
        output.push(' ');
        rest = &tail[end + closing.len()..];
    }
    output.push_str(rest);
    output
}

fn html_unescape(t: &str) -> String {
    let mut output = String::new();
    let mut rest = t;
    while let Some(start) = rest.find('&') {
        output.push_str(&rest[..start]);
        let entity = &rest[start + 1..];
        let Some(end) = entity.find(';').filter(|end| *end <= 32) else {
            output.push('&');
            rest = entity;
            continue;
        };
        let code = &entity[..end];
        if let Some(decoded) = decode_entity(code) {
            output.push_str(&decoded);
            rest = &entity[end + 1..];
        } else {
            output.push('&');
            rest = entity;
        }
    }
    output.push_str(rest);
    output
}

fn decode_entity(entity: &str) -> Option<String> {
    let named = match entity {
        "quot" => Some("\""),
        "amp" => Some("&"),
        "lt" => Some("<"),
        "gt" => Some(">"),
        "apos" | "#39" | "#x27" | "#X27" => Some("'"),
        "nbsp" => Some("\u{00a0}"),
        "lsquo" => Some("‘"),
        "rsquo" => Some("’"),
        "ldquo" => Some("“"),
        "rdquo" => Some("”"),
        "ndash" => Some("–"),
        "mdash" => Some("—"),
        "hellip" => Some("…"),
        _ => None,
    };
    if let Some(value) = named {
        return Some(value.into());
    }
    let number = entity
        .strip_prefix("#x")
        .or_else(|| entity.strip_prefix("#X"))
        .and_then(|value| u32::from_str_radix(value, 16).ok())
        .or_else(|| {
            entity
                .strip_prefix('#')
                .and_then(|value| value.parse::<u32>().ok())
        })?;
    char::from_u32(number).map(|value| value.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_document_matches_python() {
        assert_eq!(team_url(ZzzMode::Sd), SHIYU_DEFENSE_URL);
        assert_eq!(team_url(ZzzMode::Da), DEADLY_ASSAULT_URL);
        let f: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_supplemental/prydwen_document.json"
        ))
        .unwrap();
        let p = parse_document(f["html"].as_str().unwrap(), "2026-07-12T00:00:00");
        assert_eq!(p.snapshot_id, "20260707");
        assert_eq!(p.teams.get("node-a").unwrap().len(), 2);
        assert_eq!(p.tiers.len(), 4);
        assert_eq!(p.tiers[0].tier, "T0");
        assert_eq!(p.tiers[0].is_new, "True");
        assert_eq!(p.changelog[0].character_slugs, "alice-thymefield");
        assert_eq!(p.phases["3.1"].collect_date, "2026-07-07");
        assert_eq!(
            extract_visible_teams(f["html"].as_str().unwrap())
                .get("node-a")
                .unwrap()
                .len(),
            2
        );
        let nested = extract_visible_teams(
            r#"{"teams":{"outer":[{"char_one":"a","char_two":"b","char_three":"c"}],"metadata":{"teams":{"inner":[{"char_one":"d","char_two":"e","char_three":"f"}]}}}}"#,
        );
        assert_eq!(nested.keys().collect::<Vec<_>>(), ["outer"]);
        let ordered = extract_visible_teams(
            r#"{"teams":{"z-scope":[{"char_one":"a","char_two":"b","char_three":"c"}],"a-scope":[{"char_one":"d","char_two":"e","char_three":"f"}]}}"#,
        );
        assert_eq!(ordered.keys().collect::<Vec<_>>(), ["z-scope", "a-scope"]);
    }

    #[test]
    fn tier_values_follow_python_truthiness_and_complete_zzz_mappings() {
        let chars = serde_json::json!([{
            "slug": "sample-agent",
            "name": "Sample Agent",
            "element": "Auric Ink",
            "style": "Rupture",
            "isNew": false,
            "tierRatings": [
                {"category": "AnoDPS", "rating": 10, "tags": ["burst", "O'Brien", true, null]},
                {"category": "Support", "rating": "10"}
            ]
        }]);
        let rows = build_tiers(
            chars.as_array().unwrap(),
            "07/July/2026",
            "20260707",
            "fixture",
        );
        assert_eq!(rows.len(), 4);
        assert_eq!(
            (rows[0].element_cn.as_str(), rows[0].style_cn.as_str()),
            ("玄墨", "命破")
        );
        assert_eq!(
            (rows[0].tier.as_str(), rows[0].rating.as_str()),
            ("T0.5", "10")
        );
        assert_eq!(rows[0].is_new, "");
        assert_eq!(rows[0].tags, "['burst', \"O'Brien\", True, None]");
        // Python's integer-keyed dict does not classify a JSON string rating.
        assert_eq!((rows[2].tier.as_str(), rows[2].rating.as_str()), ("", "10"));
        assert_eq!(element_cn("Wind"), "风");
    }

    #[test]
    fn dates_and_changelog_match_python_fallback_and_cleaning() {
        assert_eq!(date_from_prydwen("17/06/2026"), "2026-06-17");
        assert_eq!(date_from_prydwen("future"), "future");
        let decoded = decode_payload(
            "<h6>Notes</h6><p>ignored before first date</p>\
             <h5>07/July/2026</h5><script>bad script</script><style>bad style</style>\
             <p data-slug=\"alice\">A &amp;amp; B &#x27;x&#x27;</p>\
             <h6>Other</h6><p>kept until next dated heading</p>\
             <h6>08/July/2026</h6><p>second</p>",
        );
        let rows = extract_changelog(&decoded);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].changelog_date, "2026-07-07");
        assert_eq!(rows[0].character_slugs, "alice");
        assert_eq!(
            rows[0].text,
            "A & B 'x' Other kept until next dated heading"
        );
        assert_eq!(rows[1].text, "second");
    }
}
