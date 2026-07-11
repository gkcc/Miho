use std::collections::BTreeMap;

use serde::Serialize;
use serde_json::Value;

use crate::normalize::character_slug;

const SOURCE_URL: &str = "https://www.prydwen.gg/star-rail/tier-list";

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TierRow {
    pub tier_snapshot_id: String,
    pub tier_updated_at: String,
    pub tier_updated_date: String,
    pub tier_mode: String,
    pub character_slug: String,
    pub character_name_en: String,
    pub prydwen_category: String,
    pub prydwen_role: String,
    pub role_group: String,
    pub tier: String,
    pub rating: Option<i64>,
    pub special_rating: Value,
    pub tags: Value,
    pub marks: Value,
    pub source_url: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ChangelogRow {
    pub changelog_date: String,
    pub source_url: String,
    pub character_slugs: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct OfficialName {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub aliases: String,
}

pub fn decode_prydwen_payload(html: &str) -> String {
    html.replace("\\\"", "\"")
        .replace("\\/", "/")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&")
        .replace("&quot;", "\"")
        .replace("&amp;", "&")
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
    let mut output = vec![];
    for character in characters {
        let slug = character
            .get("slug")
            .and_then(Value::as_str)
            .map(character_slug)
            .unwrap_or_default();
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
            let (role, group) = match category.as_str() {
                "DPS" => ("DPS", "main_dps"),
                "Specialist" => ("Support DPS", "sub_dps"),
                "Amplifier" => ("Amplifier", "support"),
                "Sustain" => ("Sustain", "sustain"),
                other => (other, "unknown"),
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
                    tier_updated_at: updated_at.into(),
                    tier_updated_date: prydwen_date(updated_at),
                    tier_mode: mode.into(),
                    character_slug: slug.clone(),
                    character_name_en: string(character.get("name")),
                    prydwen_category: category.clone(),
                    prydwen_role: role.into(),
                    role_group: group.into(),
                    tier: rating_to_tier(raw).into(),
                    rating: raw,
                    special_rating: rating.get(special).cloned().unwrap_or(Value::Null),
                    tags: rating
                        .get(tags)
                        .or_else(|| rating.get("tags"))
                        .cloned()
                        .unwrap_or(Value::String(String::new())),
                    marks: rating
                        .get(marks)
                        .cloned()
                        .unwrap_or(Value::String(String::new())),
                    source_url: SOURCE_URL.into(),
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
        if heading.len() == 11 && heading.as_bytes().get(2) == Some(&b'/') {
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
                changelog_date: prydwen_date(date),
                source_url: SOURCE_URL.into(),
                character_slugs: slugs.join(";"),
                text,
            })
        })
        .collect()
}

pub fn extract_visible_teams(html: &str) -> BTreeMap<String, Vec<Value>> {
    let Some(script) = between(html, "id=\"__NEXT_DATA__\"", "</script>") else {
        return BTreeMap::new();
    };
    let Some(json_start) = script.find('>').map(|v| v + 1) else {
        return BTreeMap::new();
    };
    let Ok(root) = serde_json::from_str::<Value>(&script[json_start..]) else {
        return BTreeMap::new();
    };
    let mut output = BTreeMap::new();
    collect_team_lists(&root, &mut output);
    output
}

pub fn official_names(zh: &[Value], en: &[Value]) -> BTreeMap<String, OfficialName> {
    let zh = zh
        .iter()
        .filter_map(|v| Some((string(v.get("entry_page_id")), clean_name(v.get("name"))?)))
        .collect::<BTreeMap<_, _>>();
    let mut output = BTreeMap::new();
    for row in en {
        let id = string(row.get("entry_page_id"));
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
    output
}

fn collect_team_lists(value: &Value, output: &mut BTreeMap<String, Vec<Value>>) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                if let Some(rows) = child.as_array().filter(|v| looks_like_team_list(v)) {
                    output.entry(key.clone()).or_default().extend(rows.clone());
                } else if key == "teams" {
                    if let Some(scopes) = child.as_object() {
                        for (scope, rows) in scopes {
                            if let Some(rows) = rows.as_array().filter(|v| looks_like_team_list(v))
                            {
                                output
                                    .entry(scope.clone())
                                    .or_default()
                                    .extend(rows.clone());
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
fn prydwen_date(value: &str) -> String {
    let p = value.split('/').collect::<Vec<_>>();
    if p.len() != 3 {
        return value.into();
    }
    let month = match p[1] {
        "Jan" | "January" => "01",
        "Feb" | "February" => "02",
        "Mar" | "March" => "03",
        "Apr" | "April" => "04",
        "May" => "05",
        "Jun" | "June" => "06",
        "Jul" | "July" => "07",
        "Aug" | "August" => "08",
        "Sep" | "September" => "09",
        "Oct" | "October" => "10",
        "Nov" | "November" => "11",
        "Dec" | "December" => "12",
        _ => return value.into(),
    };
    format!("{}-{month}-{:0>2}", p[2], p[0])
}
fn strip_html(value: &str) -> String {
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
    out.replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
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
    value.and_then(Value::as_str).unwrap_or_default().to_owned()
}
fn clean_name(value: Option<&Value>) -> Option<String> {
    let v = string(value).replace('\u{a0}', " ").trim().to_owned();
    (!v.is_empty()).then_some(v)
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
