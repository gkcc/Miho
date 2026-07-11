use std::collections::{BTreeMap, HashMap};

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::normalize::character_slug;

pub const AGENT_SOURCE: &str = "HoYoWiki official zzz agent menu_id=8";
pub const BANGBOO_SOURCE: &str = "HoYoWiki official zzz bangboo menu_id=15";

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
        .replace("\\u003c", "<")
        .replace("\\u003e", ">");
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
        .map(|row| (field(row, "entry_page_id"), row))
        .collect();
    let zh_order: HashMap<String, usize> = zh_rows
        .iter()
        .enumerate()
        .map(|(index, row)| (field(row, "entry_page_id"), index))
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
        .map(|row| (field(row, "entry_page_id"), row))
        .collect();
    let zh_order: HashMap<String, usize> = zh_rows
        .iter()
        .enumerate()
        .map(|(index, row)| (field(row, "entry_page_id"), index))
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
    if phase.split('.').count() < 2 || !phase.chars().all(|c| c.is_ascii_digit() || c == '.') {
        return None;
    }
    let tail = tail.trim();
    let (date, users) = if let Some(open) = tail.find('(') {
        let user_text = tail[open + 1..].split(')').next().unwrap_or("");
        let users = user_text
            .strip_suffix(" users")
            .unwrap_or("")
            .replace(',', "");
        (tail[..open].trim(), users)
    } else {
        (tail, String::new())
    };
    let collect_date = ["%d/%B/%Y", "%d/%b/%Y"]
        .iter()
        .find_map(|fmt| NaiveDate::parse_from_str(date, fmt).ok())?
        .format("%Y-%m-%d")
        .to_string();
    Some((
        phase.to_owned(),
        PhaseUpdate {
            collect_date,
            users,
        },
    ))
}

fn field(row: &Value, key: &str) -> String {
    match row.get(key) {
        Some(Value::String(v)) => v.clone(),
        Some(Value::Number(v)) => v.to_string(),
        Some(Value::Bool(v)) => v.to_string(),
        _ => String::new(),
    }
}

fn first_filter(row: &Value, key: &str) -> String {
    row.pointer(&format!("/filter_values/{key}/values/0"))
        .map(|v| match v {
            Value::String(s) => s.clone(),
            _ => v.to_string(),
        })
        .unwrap_or_default()
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
    }
}
