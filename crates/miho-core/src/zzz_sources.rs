use std::collections::{BTreeMap, HashMap};

use chrono::NaiveDate;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;

use crate::{normalize::character_slug, supplemental::HoyowikiEntryKind};

pub const AGENT_SOURCE: &str = "HoYoWiki official zzz agent menu_id=8";
pub const BANGBOO_SOURCE: &str = "HoYoWiki official zzz bangboo menu_id=15";
pub const HOYOWIKI_API_URL: &str =
    "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list";
pub const HOYOWIKI_APP: &str = "zzz";
pub const HOYOWIKI_AGENT_MENU_ID: &str = "8";
pub const HOYOWIKI_BANGBOO_MENU_ID: &str = "15";

pub const fn hoyowiki_menu_id(kind: HoyowikiEntryKind) -> Option<&'static str> {
    match kind {
        HoyowikiEntryKind::Agent => Some(HOYOWIKI_AGENT_MENU_ID),
        HoyowikiEntryKind::Bangboo => Some(HOYOWIKI_BANGBOO_MENU_ID),
        HoyowikiEntryKind::Character => None,
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct EntryPageResponse {
    pub retcode: i64,
    #[serde(default)]
    pub message: String,
    #[serde(default)]
    pub data: EntryPageData,
}
#[derive(Debug, Clone, Default, Deserialize)]
pub struct EntryPageData {
    #[serde(default, deserialize_with = "deserialize_rows")]
    pub list: Vec<Value>,
    #[serde(default, deserialize_with = "deserialize_total")]
    pub total: usize,
}

pub fn decode_entry_page_response(text: &str) -> std::result::Result<EntryPageData, String> {
    let response: EntryPageResponse = serde_json::from_str(text).map_err(|e| e.to_string())?;
    if response.retcode != 0 {
        return Err(format!(
            "HoYoWiki returned retcode {}: {}",
            response.retcode, response.message
        ));
    }
    Ok(response.data)
}

pub fn merge_cached_pages(pages: &[EntryPageData]) -> Vec<Value> {
    pages
        .iter()
        .flat_map(|page| page.list.iter().cloned())
        .collect()
}

fn deserialize_rows<'de, D>(deserializer: D) -> std::result::Result<Vec<Value>, D::Error>
where
    D: Deserializer<'de>,
{
    Ok(Option::<Vec<Value>>::deserialize(deserializer)?.unwrap_or_default())
}

fn deserialize_total<'de, D>(deserializer: D) -> std::result::Result<usize, D::Error>
where
    D: Deserializer<'de>,
{
    let value = Option::<Value>::deserialize(deserializer)?.unwrap_or(Value::Null);
    Ok(match value {
        Value::Number(value) => value.as_u64().unwrap_or_default() as usize,
        Value::String(value) => value.parse().unwrap_or_default(),
        _ => 0,
    })
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct OfficialMapRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub source: String,
    pub needs_manual_check: String,
    pub aliases: String,
    pub kind: String,
    pub release_order: String,
}

pub fn official_name_map(
    agents: &[OfficialNameRow],
    bangboo: &[OfficialBangbooRow],
) -> BTreeMap<String, OfficialMapRow> {
    let mut output = BTreeMap::new();
    for (slug, en, cn, source, kind, order) in agents
        .iter()
        .map(|r| {
            (
                &r.character_slug,
                &r.character_name_en,
                &r.character_name_cn,
                &r.source,
                &r.kind,
                r.release_order,
            )
        })
        .chain(bangboo.iter().map(|r| {
            (
                &r.character_slug,
                &r.character_name_en,
                &r.character_name_cn,
                &r.source,
                &r.kind,
                r.release_order,
            )
        }))
    {
        let aliases = aliases_for(slug, en);
        let row = OfficialMapRow {
            character_slug: slug.clone(),
            character_name_en: en.clone(),
            character_name_cn: cn.clone(),
            source: source.clone(),
            needs_manual_check: if cn.is_empty() { "1" } else { "0" }.into(),
            aliases: aliases.join(";"),
            kind: kind.clone(),
            release_order: order.to_string(),
        };
        output.entry(slug.clone()).or_insert_with(|| row.clone());
        for alias in aliases {
            output.entry(alias).or_insert_with(|| row.clone());
        }
    }
    for (slug, en, cn, source, kind, order) in [
        (
            "velina",
            "Velina",
            "维琳娜·艾嘉德",
            "HoYoWiki official zzz zh-cn agent menu_id=8",
            "agent",
            "0",
        ),
        (
            "ultra-jake",
            "Ultra Jake",
            "超极杰克",
            "HoYoWiki official zzz zh-cn bangboo menu_id=15",
            "bangboo",
            "1000",
        ),
        (
            "sprout",
            "Sprout",
            "芽芽",
            "HoYoWiki official zzz zh-cn bangboo menu_id=15",
            "bangboo",
            "1003",
        ),
    ] {
        output.entry(slug.into()).or_insert(OfficialMapRow {
            character_slug: slug.into(),
            character_name_en: en.into(),
            character_name_cn: cn.into(),
            source: source.into(),
            needs_manual_check: "0".into(),
            aliases: String::new(),
            kind: kind.into(),
            release_order: order.into(),
        });
    }
    output
}

fn aliases_for(slug: &str, name: &str) -> Vec<String> {
    let mut values = match slug {
        "alexandrina-sebastiane" => vec!["rina"],
        "alice-thymefield" => vec!["alice"],
        "asaba-harumasa" => vec!["harumasa"],
        "billy-starlight" => vec!["starlight-billy"],
        "burnice-white" => vec!["burnice"],
        "caesar-king" => vec!["caesar"],
        "ellen-joe" => vec!["ellen"],
        "evelyn-chevalier" => vec!["evelyn"],
        "hoshimi-miyabi" => vec!["miyabi"],
        "hugo-vlad" => vec!["hugo"],
        "komano-manato" => vec!["manato"],
        "luciana-de-montefio" => vec!["lucy"],
        "nekomiya-mana" => vec!["nekomata"],
        "orphie-magnusson-and-magus" => vec!["orphie-and-magus"],
        "piper-wheel" => vec!["piper"],
        "pulchra-fellini" => vec!["pulchra"],
        "soldier-0-anby" => vec!["anby-demara-soldier-0", "anby-soldier-0"],
        "tsukishiro-yanagi" => vec!["yanagi"],
        "ukinami-yuzuha" => vec!["yuzuha"],
        "vivian-banshee" => vec!["vivian"],
        "von-lycaon" => vec!["lycaon"],
        _ => vec![],
    }
    .into_iter()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    let normalized = character_slug(name);
    if !normalized.is_empty() {
        values.push(normalized.clone());
    }
    let parts = normalized
        .split('-')
        .filter(|v| !matches!(*v, "and" | "de" | "the"))
        .collect::<Vec<_>>();
    if parts.len() >= 2 {
        values.push(parts[0].into());
        values.push(parts[parts.len() - 1].into())
    }
    if name.contains('-') {
        let dash_parts = name
            .split('-')
            .filter(|part| !part.trim().is_empty())
            .map(character_slug)
            .collect::<Vec<_>>();
        if dash_parts.len() == 2 {
            values.push(format!("{}-{}", dash_parts[1], dash_parts[0]));
        }
    }
    values.sort();
    values.dedup();
    values.retain(|v| v != slug);
    values
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PhaseUpdate {
    pub collect_date: String,
    pub users: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OfficialNameRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub element_en: String,
    pub element_cn: String,
    pub style_en: String,
    pub style_cn: String,
    pub faction_en: String,
    pub faction_cn: String,
    pub rarity: String,
    pub icon_url: String,
    pub source: String,
    pub kind: String,
    pub release_order: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OfficialBangbooRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub source: String,
    pub kind: String,
    pub release_order: usize,
}

/// Extract the phase selector embedded in a fixed Prydwen HTML response.
/// Later duplicate phases replace earlier ones, matching Python dict assignment.
pub fn extract_phase_updates_from_html(html: &str) -> BTreeMap<String, PhaseUpdate> {
    let decoded = html
        .replace("\\\"", "\"")
        .replace("\\/", "/")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&amp;", "&");
    let mut output = BTreeMap::new();
    let mut rest = decoded.as_str();
    while let Some(start) = rest.to_ascii_lowercase().find("<option") {
        rest = &rest[start + 7..];
        let Some(close) = rest.find('>') else { break };
        rest = &rest[close + 1..];
        let end = rest.find('<').unwrap_or(rest.len());
        let text = collapse_whitespace(&rest[..end]);
        if let Some((phase, update)) = parse_phase_option(&text) {
            output.insert(phase, update);
        }
        rest = &rest[end..];
    }
    output
}

pub fn parse_official_agents(en_rows: &[Value], zh_rows: &[Value]) -> Vec<OfficialNameRow> {
    parse_official_rows(en_rows, zh_rows)
}

pub fn parse_official_bangboo(en_rows: &[Value], zh_rows: &[Value]) -> Vec<OfficialBangbooRow> {
    let zh_by_id: HashMap<String, &Value> = zh_rows
        .iter()
        .map(|row| (dictionary_entry_id(row), row))
        .collect();
    let zh_order: HashMap<String, usize> = zh_rows
        .iter()
        .enumerate()
        .map(|(index, row)| (dictionary_entry_id(row), index))
        .collect();
    en_rows
        .iter()
        .enumerate()
        .filter_map(|(index, en)| {
            let id = field(en, "entry_page_id");
            let en_name = clean_name(&field(en, "name"));
            if en_name.is_empty() {
                return None;
            }
            Some(OfficialBangbooRow {
                character_slug: character_slug(&en_name),
                character_name_en: en_name,
                character_name_cn: zh_by_id
                    .get(&id)
                    .map(|row| clean_name(&field(row, "name")))
                    .unwrap_or_default(),
                source: BANGBOO_SOURCE.to_owned(),
                kind: "bangboo".to_owned(),
                release_order: 1000 + zh_order.get(&id).copied().unwrap_or(index),
            })
        })
        .collect()
}

fn parse_official_rows(en_rows: &[Value], zh_rows: &[Value]) -> Vec<OfficialNameRow> {
    let zh_by_id: HashMap<String, &Value> = zh_rows
        .iter()
        .map(|row| (dictionary_entry_id(row), row))
        .collect();
    let zh_order: HashMap<String, usize> = zh_rows
        .iter()
        .enumerate()
        .map(|(index, row)| (dictionary_entry_id(row), index))
        .collect();
    en_rows
        .iter()
        .enumerate()
        .filter_map(|(index, en)| {
            let id = field(en, "entry_page_id");
            let zh = zh_by_id.get(&id).copied();
            let en_name = clean_name(&field(en, "name"));
            if en_name.is_empty() {
                return None;
            }
            let cn_name = zh
                .map(|row| clean_name(&field(row, "name")))
                .unwrap_or_default();
            let release_order = zh_order.get(&id).copied().unwrap_or(index);
            Some(OfficialNameRow {
                character_slug: character_slug(&en_name),
                character_name_en: en_name,
                character_name_cn: cn_name,
                element_en: first_filter(en, "agent_stats"),
                element_cn: zh
                    .map(|v| first_filter(v, "agent_stats"))
                    .unwrap_or_default(),
                style_en: first_filter(en, "agent_specialties"),
                style_cn: zh
                    .map(|v| first_filter(v, "agent_specialties"))
                    .unwrap_or_default(),
                faction_en: first_filter(en, "agent_faction"),
                faction_cn: zh
                    .map(|v| first_filter(v, "agent_faction"))
                    .unwrap_or_default(),
                rarity: {
                    let value = first_filter(en, "agent_rarity");
                    if value.is_empty() {
                        zh.map(|v| first_filter(v, "agent_rarity"))
                            .unwrap_or_default()
                    } else {
                        value
                    }
                },
                icon_url: zh
                    .map(|v| field(v, "icon_url"))
                    .filter(|v| !v.is_empty())
                    .unwrap_or_else(|| field(en, "icon_url")),
                source: AGENT_SOURCE.to_owned(),
                kind: "agent".to_owned(),
                release_order,
            })
        })
        .collect()
}

fn parse_phase_option(text: &str) -> Option<(String, PhaseUpdate)> {
    let (phase, tail) = text.split_once('-')?;
    let phase = phase.trim();
    let phase_parts = phase.split('.').collect::<Vec<_>>();
    if phase_parts.len() < 2
        || phase_parts
            .iter()
            .any(|part| part.is_empty() || !part.bytes().all(|byte| byte.is_ascii_digit()))
    {
        return None;
    }
    let tail = tail.trim();
    let date_end = tail
        .find(|character: char| character.is_whitespace() || character == '(')
        .unwrap_or(tail.len());
    let date = &tail[..date_end];
    let remainder = tail[date_end..].trim_start();
    let users = remainder
        .strip_prefix('(')
        .and_then(|value| value.split_once(')'))
        .map(|(value, _)| value.trim())
        .and_then(|value| {
            let lower = value.to_ascii_lowercase();
            lower.strip_suffix("users").and_then(|prefix| {
                let digits = prefix.trim_end();
                (digits.len() < prefix.len()
                    && !digits.is_empty()
                    && digits
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || byte == b','))
                .then(|| digits.replace(',', ""))
            })
        })
        .unwrap_or_default();
    let date_parts = date.split('/').collect::<Vec<_>>();
    if date_parts.len() != 3
        || date_parts[0].is_empty()
        || date_parts[0].len() > 2
        || !date_parts[0].bytes().all(|byte| byte.is_ascii_digit())
        || date_parts[1].is_empty()
        || !date_parts[1].bytes().all(|byte| byte.is_ascii_alphabetic())
        || date_parts[2].len() != 4
        || !date_parts[2].bytes().all(|byte| byte.is_ascii_digit())
    {
        return None;
    }
    let collect_date = ["%d/%B/%Y", "%d/%b/%Y"]
        .iter()
        .find_map(|fmt| NaiveDate::parse_from_str(date, fmt).ok())
        .map(|value| value.format("%Y-%m-%d").to_string())
        .unwrap_or_else(|| date.to_owned());
    Some((
        phase.to_owned(),
        PhaseUpdate {
            collect_date,
            users,
        },
    ))
}

fn field(row: &Value, key: &str) -> String {
    row.get(key)
        .filter(|value| python_truthy(value))
        .map(python_value_string)
        .unwrap_or_default()
}

fn dictionary_entry_id(row: &Value) -> String {
    row.get("entry_page_id")
        .map(python_value_string)
        .unwrap_or_else(|| "None".into())
}

fn first_filter(row: &Value, key: &str) -> String {
    row.pointer(&format!("/filter_values/{key}/values/0"))
        .map(python_value_string)
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

pub(crate) fn python_value_string(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Number(value) => value.to_string(),
        Value::String(value) => value.clone(),
        Value::Array(_) | Value::Object(_) => python_repr(value),
    }
}

fn python_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
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

fn clean_name(value: &str) -> String {
    value.replace('\u{00a0}', " ").trim().to_owned()
}

fn collapse_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_sources_match_python_oracle() {
        assert_eq!(
            hoyowiki_menu_id(HoyowikiEntryKind::Agent),
            Some(HOYOWIKI_AGENT_MENU_ID)
        );
        assert_eq!(hoyowiki_menu_id(HoyowikiEntryKind::Character), None);
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_sources_minimal.json"
        ))
        .unwrap();
        let phases = extract_phase_updates_from_html(fixture["phase_html"].as_str().unwrap());
        assert_eq!(
            phases["3.1"],
            PhaseUpdate {
                collect_date: "2026-07-07".into(),
                users: "1234".into()
            }
        );

        let page = decode_entry_page_response(
            r#"{"retcode":0,"data":{"list":[{"entry_page_id":"1"}],"total":1}}"#,
        )
        .unwrap();
        assert_eq!((page.total, merge_cached_pages(&[page]).len()), (1, 1));
        let pages = [
            decode_entry_page_response(
                r#"{"retcode":0,"data":{"list":[{"entry_page_id":"10"},{"entry_page_id":"2"}],"total":"3"}}"#,
            )
            .unwrap(),
            decode_entry_page_response(
                r#"{"retcode":0,"data":{"list":[{"entry_page_id":"10"}],"total":3}}"#,
            )
            .unwrap(),
        ];
        let merged = merge_cached_pages(&pages);
        assert_eq!(pages[0].total, 3);
        assert_eq!(
            merged
                .iter()
                .map(|row| field(row, "entry_page_id"))
                .collect::<Vec<_>>(),
            ["10", "2", "10"]
        );
        let empty =
            decode_entry_page_response(r#"{"retcode":0,"data":{"list":null,"total":null}}"#)
                .unwrap();
        assert!(empty.list.is_empty());
        assert_eq!(empty.total, 0);
        assert!(
            decode_entry_page_response(r#"{"retcode":-1,"message":"bad"}"#)
                .unwrap_err()
                .contains("retcode -1")
        );
        assert_eq!(phases["3.2"].users, "");

        let agents = parse_official_agents(
            fixture["agents_en"].as_array().unwrap(),
            fixture["agents_zh"].as_array().unwrap(),
        );
        assert_eq!(agents.len(), 1);
        assert_eq!(
            (
                agents[0].character_slug.as_str(),
                agents[0].character_name_cn.as_str(),
                agents[0].release_order
            ),
            ("alice-thymefield", "爱丽丝", 1)
        );
        assert_eq!(agents[0].icon_url, "zh.webp");

        let bangboo = parse_official_bangboo(
            fixture["bangboo_en"].as_array().unwrap(),
            fixture["bangboo_zh"].as_array().unwrap(),
        );
        assert_eq!(bangboo.len(), 1);
        assert_eq!(
            (
                bangboo[0].character_slug.as_str(),
                bangboo[0].character_name_cn.as_str(),
                bangboo[0].release_order
            ),
            ("ultra-jake", "超极杰克", 1001)
        );
        let mapped = official_name_map(&agents, &bangboo);
        assert_eq!(mapped["alice"].character_name_cn, "爱丽丝");
        assert_eq!(mapped["velina"].needs_manual_check, "0");

        let mut renamed = agents[0].clone();
        renamed.character_slug = "canonical-source-id".into();
        let mapped = official_name_map(&[renamed], &[]);
        assert_eq!(
            mapped["alice-thymefield"].character_slug,
            "canonical-source-id"
        );
        let no_id = parse_official_agents(
            &[serde_json::json!({"name": "No ID"})],
            &[serde_json::json!({"name": "Must Not Match"})],
        );
        assert_eq!(no_id[0].character_name_cn, "");

        let escaped = extract_phase_updates_from_html(
            r#"\u003coption\u003e3.4 - 9/Jul/2026 (1,234   USERS)\u003c/option\u003e<option>3..5 - 9/Jul/2026</option>"#,
        );
        assert_eq!(escaped["3.4"].users, "1234");
        assert!(!escaped.contains_key("3..5"));
        let unknown_month = extract_phase_updates_from_html("<option>3.6 - 09/Foo/2026</option>");
        assert_eq!(unknown_month["3.6"].collect_date, "09/Foo/2026");
        assert_eq!(
            python_value_string(&serde_json::json!(["tag", "O'Brien", true, null])),
            "['tag', \"O'Brien\", True, None]"
        );
    }
}
