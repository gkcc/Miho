//! Explicit `legacy-v0` decision compatibility core.
//!
//! This module intentionally preserves the old heuristic, including its
//! cross-mode summaries and raw-team dependency. It is not evidence-first.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;

use chrono::NaiveDateTime;
use csv::{ReaderBuilder, StringRecord};
use serde_json::{json, Map, Number, Value};

use crate::normalize::{character_slug, parse_percent};
use crate::visualizer::python_json_number_repr;

pub const DECISION_LEGACY_METHOD: &str = "legacy-v0";
const PYYAML_TIMESTAMP_PREFIX: &str = "\0pyyaml-timestamp:";
const PYYAML_NON_FINITE_PREFIX: &str = "\0pyyaml-non-finite:";

#[derive(Debug, thiserror::Error)]
pub enum DecisionLegacyError {
    #[error("{input} is not valid UTF-8: {source}")]
    Utf8 {
        input: &'static str,
        source: std::str::Utf8Error,
    },
    #[error("invalid CSV in {input}: {source}")]
    Csv {
        input: &'static str,
        source: csv::Error,
    },
    #[error("invalid JSON in {input}: {source}")]
    Json {
        input: &'static str,
        source: serde_json::Error,
    },
    #[error("invalid YAML in {input}: {source}")]
    Yaml {
        input: &'static str,
        source: serde_yaml::Error,
    },
    #[error("invalid legacy decision input: {0}")]
    Invalid(String),
}

pub type DecisionLegacyResult<T> = Result<T, DecisionLegacyError>;

#[derive(Debug, Clone, Default)]
pub struct DecisionLegacyInputsV0 {
    pub box_config: Vec<u8>,
    pub rules_config: Option<Vec<u8>>,
    pub tier_current_csv: Option<Vec<u8>>,
    pub tier_history_csv: Option<Vec<u8>>,
    pub usage_csv: Option<Vec<u8>>,
    pub team_raw_csv: Option<Vec<u8>>,
    pub name_map_csv: Option<Vec<u8>>,
    pub changelog_history_csv: Option<Vec<u8>>,
}

#[derive(Debug, Clone)]
pub struct DecisionLegacyRequestV0 {
    pub method: String,
}

#[derive(Debug, Clone, Copy)]
pub struct DecisionLegacyContextV0 {
    pub local_datetime: NaiveDateTime,
}

#[derive(Debug, Clone)]
pub struct DecisionLegacyOutputV0 {
    pub payload: Value,
}

type Row = BTreeMap<String, Option<String>>;

#[derive(Debug, Clone, Default)]
struct Agent {
    name_cn: String,
    owned: bool,
    cinema: i64,
    signature: i64,
    level: Option<i64>,
    engine_level: Option<i64>,
    core_skill: Option<i64>,
    drive_discs: String,
}

impl Agent {
    fn stage(&self) -> String {
        format!("{}+{}", self.cinema, self.signature)
    }
}

#[derive(Debug, Clone, Default)]
struct BoxProfile {
    agents: BTreeMap<String, Agent>,
}

#[derive(Debug, Clone, Default)]
struct DecisionData {
    tier_rows: Vec<Row>,
    tier_history_rows: Vec<Row>,
    usage_rows: Vec<Row>,
    team_rows: Vec<Row>,
    name_rows: Vec<Row>,
    changelog_rows: Vec<Row>,
}

pub fn build_decision_legacy_v0(
    inputs: &DecisionLegacyInputsV0,
    request: &DecisionLegacyRequestV0,
) -> DecisionLegacyResult<DecisionLegacyOutputV0> {
    if request.method != DECISION_LEGACY_METHOD {
        return Err(DecisionLegacyError::Invalid(format!(
            "unsupported decision method: {}",
            request.method
        )));
    }
    let box_profile = parse_box(&inputs.box_config)?;
    let rules = match inputs.rules_config.as_deref() {
        Some(bytes) => parse_mapping_config(bytes, "rules config")?,
        None => Map::new(),
    };
    let data = DecisionData {
        tier_rows: parse_optional_csv(inputs.tier_current_csv.as_deref(), "tier current CSV")?,
        tier_history_rows: parse_optional_csv(
            inputs.tier_history_csv.as_deref(),
            "tier history CSV",
        )?,
        usage_rows: parse_optional_csv(inputs.usage_csv.as_deref(), "usage CSV")?,
        team_rows: parse_optional_csv(inputs.team_raw_csv.as_deref(), "raw team CSV")?,
        name_rows: parse_optional_csv(inputs.name_map_csv.as_deref(), "name map CSV")?,
        changelog_rows: parse_optional_csv(
            inputs.changelog_history_csv.as_deref(),
            "changelog history CSV",
        )?,
    };
    let _compatibility_only_unused_tier_history = data.tier_history_rows.len();
    let tier_index = build_tier_index(&data.tier_rows, &data.name_rows)?;
    let candidates = build_candidate_configs(&box_profile, &tier_index, &rules);
    let mut cards = Vec::new();
    for candidate in candidates {
        if let Some(card) = build_card(&candidate, &box_profile, &tier_index, &data, &rules)? {
            cards.push(card);
        }
    }
    cards.sort_by(card_order);
    let mut counts = Map::new();
    for card in &cards {
        let decision = text(card, "decision");
        let count = counts.get(&decision).and_then(Value::as_u64).unwrap_or(0) + 1;
        counts.insert(decision, Value::from(count));
    }
    let summary = json!({
        "owned_agents": box_profile.agents.values().filter(|agent| agent.owned).count(),
        "candidate_count": cards.len(),
        "decision_counts": counts,
        "data_rows": {
            "tier_current": data.tier_rows.len(),
            "usage": data.usage_rows.len(),
            "teams": data.team_rows.len(),
            "changelog": data.changelog_rows.len(),
        }
    });
    Ok(DecisionLegacyOutputV0 {
        payload: json!({"summary": summary, "cards": cards}),
    })
}

pub fn render_decision_json_legacy_v0(
    output: &DecisionLegacyOutputV0,
) -> DecisionLegacyResult<Vec<u8>> {
    reject_non_finite(&output.payload)?;
    let rust_json =
        serde_json::to_vec_pretty(&output.payload).map_err(|source| DecisionLegacyError::Json {
            input: "decision output",
            source,
        })?;
    Ok(normalize_python_json_numbers(&rust_json))
}

pub fn render_decision_markdown_legacy_v0(
    output: &DecisionLegacyOutputV0,
    context: &DecisionLegacyContextV0,
) -> String {
    format_report(&output.payload, context.local_datetime)
}

fn parse_optional_csv(bytes: Option<&[u8]>, input: &'static str) -> DecisionLegacyResult<Vec<Row>> {
    let Some(bytes) = bytes else {
        return Ok(Vec::new());
    };
    let text =
        std::str::from_utf8(bytes).map_err(|source| DecisionLegacyError::Utf8 { input, source })?;
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let mut reader = ReaderBuilder::new()
        // `csv.DictReader` tolerates missing trailing cells and ignores extra
        // cells through its `None` bucket. The compatibility port must do the
        // same for all six legacy CSV inputs.
        .flexible(true)
        .from_reader(text.as_bytes());
    let headers = reader
        .headers()
        .map_err(|source| DecisionLegacyError::Csv { input, source })?
        .clone();
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record.map_err(|source| DecisionLegacyError::Csv { input, source })?;
        rows.push(row_map(&headers, &record));
    }
    Ok(rows)
}

fn row_map(headers: &StringRecord, record: &StringRecord) -> Row {
    headers
        .iter()
        .enumerate()
        .map(|(index, key)| (key.to_owned(), record.get(index).map(str::to_owned)))
        .collect()
}

fn parse_mapping_config(
    bytes: &[u8],
    input: &'static str,
) -> DecisionLegacyResult<Map<String, Value>> {
    let text =
        std::str::from_utf8(bytes).map_err(|source| DecisionLegacyError::Utf8 { input, source })?;
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let is_json = text.trim_start().starts_with('{');
    let value: Value = if is_json {
        serde_json::from_str(text).map_err(|source| DecisionLegacyError::Json { input, source })?
    } else {
        let compatible = normalize_pyyaml_11_bool_scalars(text);
        let mut yaml_value: serde_yaml::Value = serde_yaml::from_str(&compatible)
            .map_err(|source| DecisionLegacyError::Yaml { input, source })?;
        yaml_value
            .apply_merge()
            .map_err(|source| DecisionLegacyError::Yaml { input, source })?;
        serde_json::to_value(yaml_value)
            .map_err(|source| DecisionLegacyError::Json { input, source })?
    };
    reject_numeric_config_non_finite(&value, input)?;
    if !is_json && !python_truthy(&value) {
        return Ok(Map::new());
    }
    value
        .as_object()
        .cloned()
        .ok_or_else(|| DecisionLegacyError::Invalid(format!("{input} root must be a mapping")))
}

/// PyYAML's safe loader still resolves the YAML 1.1 plain scalars
/// yes/no/on/off as booleans, while serde_yaml follows YAML 1.2. Preserve that
/// legacy dialect without changing quoted strings or block-scalar contents.
fn normalize_pyyaml_11_bool_scalars(text: &str) -> String {
    fn replacement(value: &str) -> Option<String> {
        match value.to_ascii_lowercase().as_str() {
            "yes" | "on" => return Some("true".to_owned()),
            "no" | "off" => return Some("false".to_owned()),
            ".inf" | "+.inf" | "-.inf" | ".nan" | "+.nan" | "-.nan" => {
                return Some(format!("\"\\0pyyaml-non-finite:{value}\""));
            }
            _ => {}
        }
        let compact = value.replace('_', "");
        let (sign, unsigned) = match compact.as_bytes().first() {
            Some(b'+') => (1_i128, &compact[1..]),
            Some(b'-') => (-1_i128, &compact[1..]),
            _ => (1_i128, compact.as_str()),
        };
        if unsigned.len() > 1
            && unsigned.starts_with('0')
            && unsigned.bytes().all(|byte| matches!(byte, b'0'..=b'7'))
        {
            if let Ok(number) = i128::from_str_radix(unsigned, 8) {
                return Some((sign * number).to_string());
            }
        }
        let parts = unsigned.split(':').collect::<Vec<_>>();
        if parts.len() >= 2
            && !parts[0].starts_with('0')
            && parts.iter().all(|part| !part.is_empty())
        {
            let mut total = 0_i128;
            let mut valid = true;
            for (index, part) in parts.iter().enumerate() {
                let Ok(number) = part.parse::<i128>() else {
                    valid = false;
                    break;
                };
                if index > 0 && number > 59 {
                    valid = false;
                    break;
                }
                let Some(next) = total.checked_mul(60).and_then(|v| v.checked_add(number)) else {
                    valid = false;
                    break;
                };
                total = next;
            }
            if valid {
                return Some((sign * total).to_string());
            }
        }
        let bytes = value.as_bytes();
        if bytes.len() >= 10
            && bytes[0..4].iter().all(u8::is_ascii_digit)
            && bytes[4] == b'-'
            && bytes[5..7].iter().all(u8::is_ascii_digit)
            && bytes[7] == b'-'
            && bytes[8..10].iter().all(u8::is_ascii_digit)
        {
            return Some(format!("\"\\0pyyaml-timestamp:{value}\""));
        }
        None
    }
    fn comment_start(line: &str) -> usize {
        let mut single = false;
        let mut double = false;
        let mut escaped = false;
        for (index, ch) in line.char_indices() {
            if double {
                if escaped {
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == '"' {
                    double = false;
                }
            } else if single {
                if ch == '\'' {
                    single = false;
                }
            } else if ch == '"' {
                double = true;
            } else if ch == '\'' {
                single = true;
            } else if ch == '#' && (index == 0 || line[..index].ends_with(char::is_whitespace)) {
                return index;
            }
        }
        line.len()
    }
    fn scalar_range(code: &str) -> Option<std::ops::Range<usize>> {
        if code.trim().is_empty() {
            return None;
        }
        let trimmed_start = code.len() - code.trim_start().len();
        let trimmed_end = code.trim_end().len();
        let trimmed = &code[trimmed_start..trimmed_end];
        if replacement(trimmed).is_some() {
            return Some(trimmed_start..trimmed_end);
        }
        if let Some(rest) = trimmed.strip_prefix("- ") {
            let offset = trimmed_start + 2 + (rest.len() - rest.trim_start().len());
            let end = offset + rest.trim().len();
            if replacement(&code[offset..end]).is_some() {
                return Some(offset..end);
            }
        }
        let mut single = false;
        let mut double = false;
        let mut escaped = false;
        for (index, ch) in code.char_indices() {
            if double {
                if escaped {
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == '"' {
                    double = false;
                }
            } else if single {
                if ch == '\'' {
                    single = false;
                }
            } else if ch == '"' {
                double = true;
            } else if ch == '\'' {
                single = true;
            } else if ch == ':' {
                let start = index + 1;
                let tail = &code[start..];
                let offset = start + (tail.len() - tail.trim_start().len());
                let end = offset + tail.trim().len();
                if replacement(&code[offset..end]).is_some() {
                    return Some(offset..end);
                }
            }
        }
        None
    }
    fn replace_segment(segment: &str) -> String {
        let Some(range) = scalar_range(segment) else {
            return segment.to_owned();
        };
        let mut output = String::with_capacity(segment.len());
        output.push_str(&segment[..range.start]);
        output.push_str(
            &replacement(&segment[range.clone()]).expect("range is a legacy PyYAML scalar"),
        );
        output.push_str(&segment[range.end..]);
        output
    }
    fn replace_code(code: &str) -> String {
        let mut output = String::with_capacity(code.len());
        let mut segment_start = 0;
        let mut single = false;
        let mut double = false;
        let mut escaped = false;
        for (index, ch) in code.char_indices() {
            if double {
                if escaped {
                    escaped = false;
                } else if ch == '\\' {
                    escaped = true;
                } else if ch == '"' {
                    double = false;
                }
            } else if single {
                if ch == '\'' {
                    single = false;
                }
            } else if ch == '"' {
                double = true;
            } else if ch == '\'' {
                single = true;
            } else if matches!(ch, '[' | ']' | '{' | '}' | ',') {
                output.push_str(&replace_segment(&code[segment_start..index]));
                output.push(ch);
                segment_start = index + ch.len_utf8();
            }
        }
        output.push_str(&replace_segment(&code[segment_start..]));
        output
    }

    let mut output = String::with_capacity(text.len());
    let mut block_parent_indent = None;
    for inclusive in text.split_inclusive('\n') {
        let line = inclusive.strip_suffix('\n').unwrap_or(inclusive);
        let newline = if inclusive.ends_with('\n') { "\n" } else { "" };
        let indent = line.len() - line.trim_start_matches([' ', '\t']).len();
        if let Some(parent) = block_parent_indent {
            if line.trim().is_empty() || indent > parent {
                output.push_str(line);
                output.push_str(newline);
                continue;
            }
            block_parent_indent = None;
        }
        let comment = comment_start(line);
        let code = &line[..comment];
        let trimmed_code = code.trim_end();
        if trimmed_code.ends_with('|') || trimmed_code.ends_with('>') {
            block_parent_indent = Some(indent);
        }
        output.push_str(&replace_code(code));
        output.push_str(&line[comment..]);
        output.push_str(newline);
    }
    output
}

fn parse_box(bytes: &[u8]) -> DecisionLegacyResult<BoxProfile> {
    let config = parse_mapping_config(bytes, "box config")?;
    let mut profile = BoxProfile::default();
    let Some(agents) = config.get("agents") else {
        return Ok(profile);
    };
    let mut rows = Vec::<Map<String, Value>>::new();
    match agents {
        Value::Array(values) => rows.extend(values.iter().filter_map(Value::as_object).cloned()),
        Value::Object(values) => {
            for (slug, value) in values {
                let mut row = value.as_object().cloned().unwrap_or_default();
                row.entry("slug".to_owned())
                    .or_insert_with(|| Value::String(slug.clone()));
                if !value.is_object() {
                    row.insert("owned".to_owned(), Value::Bool(box_owned_bool(value)));
                }
                rows.push(row);
            }
        }
        _ => {}
    }
    for row in rows {
        let slug =
            normalize(value_text(first_value(&row, &["slug", "id", "name_en", "name"])).as_str());
        if slug.is_empty() {
            continue;
        }
        let agent = Agent {
            name_cn: value_text(first_value(&row, &["name_cn", "name"])),
            owned: row.get("owned").map(box_owned_bool).unwrap_or(true),
            cinema: value_i64(first_existing(&row, &["cinema", "mindscape", "copies"]), 0),
            signature: value_i64(
                first_existing(&row, &["signature", "w_engine_signature"]),
                0,
            ),
            level: optional_i64(row.get("level")),
            engine_level: optional_i64(first_existing(&row, &["w_engine_level", "weapon_level"])),
            core_skill: optional_i64(row.get("core_skill")),
            drive_discs: value_text(first_value(&row, &["drive_discs", "discs"])),
        };
        profile.agents.insert(slug, agent);
    }
    Ok(profile)
}

fn normalize(value: &str) -> String {
    character_slug(value)
}
fn field<'a>(row: &'a Row, key: &str) -> &'a str {
    row.get(key).and_then(Option::as_deref).unwrap_or("")
}
fn row_value_or(row: &Row, key: &str, default: &str) -> Value {
    match row.get(key) {
        None => Value::String(default.to_owned()),
        Some(None) => Value::Null,
        Some(Some(value)) => Value::String(value.clone()),
    }
}
fn row_value_or_null(row: &Row, key: &str) -> Value {
    match row.get(key) {
        Some(Some(value)) => Value::String(value.clone()),
        None | Some(None) => Value::Null,
    }
}
fn value_or_empty(value: &Value, key: &str) -> Value {
    value
        .get(key)
        .cloned()
        .unwrap_or_else(|| Value::String(String::new()))
}
fn text(value: &Value, key: &str) -> String {
    value
        .get(key)
        .map(|value| value_text(Some(value)))
        .unwrap_or_default()
}
fn number(value: f64) -> DecisionLegacyResult<Value> {
    Number::from_f64(value)
        .map(Value::Number)
        .ok_or_else(|| DecisionLegacyError::Invalid("non-finite legacy decision number".to_owned()))
}
fn value_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(v)) => v
            .strip_prefix(PYYAML_TIMESTAMP_PREFIX)
            .unwrap_or(v)
            .to_owned(),
        Some(Value::Bool(v)) => if *v { "True" } else { "False" }.to_owned(),
        Some(Value::Number(v)) => python_json_number_repr(v),
        _ => String::new(),
    }
}
fn first_value<'a>(row: &'a Map<String, Value>, keys: &[&str]) -> Option<&'a Value> {
    keys.iter()
        .find_map(|key| row.get(*key).filter(|v| python_truthy(v)))
}
fn first_existing<'a>(row: &'a Map<String, Value>, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().find_map(|key| row.get(*key))
}
fn python_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().unwrap_or(0.0) != 0.0,
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}
fn reject_numeric_config_non_finite(
    value: &Value,
    input: &'static str,
) -> DecisionLegacyResult<()> {
    const NUMERIC_KEYS: &[&str] = &[
        "cinema",
        "mindscape",
        "copies",
        "signature",
        "w_engine_signature",
        "level",
        "w_engine_level",
        "weapon_level",
        "core_skill",
        "candidate_min_rating",
        "max_generated_candidates",
        "low_tier_warning_rating",
        "pull_rating",
        "skip_rating",
        "trend_warning_delta",
        "min_pull_avg_usage",
        "bad_trend_block_delta",
        "bad_trend_block_avg_usage",
    ];
    match value {
        Value::Array(values) => {
            for value in values {
                reject_numeric_config_non_finite(value, input)?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for (key, value) in values {
                if NUMERIC_KEYS.contains(&key.as_str())
                    && numeric_value(value).is_some_and(|number| !number.is_finite())
                {
                    return Err(DecisionLegacyError::Invalid(format!(
                        "{input} contains a non-finite numeric field {key}"
                    )));
                }
                reject_numeric_config_non_finite(value, input)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}
fn box_owned_bool(value: &Value) -> bool {
    match value {
        Value::Bool(value) => *value,
        Value::String(value) => !matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "0" | "false" | "no" | "n" | "未拥有"
        ),
        Value::Number(value) => value.as_f64() != Some(0.0),
        _ => true,
    }
}
fn value_i64(value: Option<&Value>, default: i64) -> i64 {
    value
        .and_then(numeric_value)
        .map(|v| v as i64)
        .unwrap_or(default)
}
fn optional_i64(value: Option<&Value>) -> Option<i64> {
    value
        .filter(|v| !value_text(Some(v)).is_empty())
        .map(|v| value_i64(Some(v), 0))
}
fn float_text(value: &str) -> f64 {
    parse_legacy_float(value).unwrap_or(0.0)
}
fn value_f64(value: Option<&Value>, default: f64) -> f64 {
    match value {
        None => default,
        Some(value) => numeric_value(value).unwrap_or(0.0),
    }
}
fn numeric_value(value: &Value) -> Option<f64> {
    match value {
        Value::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        Value::Number(value) => value.as_f64(),
        Value::String(value) => parse_legacy_float(value),
        _ => None,
    }
}

fn parse_legacy_float(value: &str) -> Option<f64> {
    let value = value.trim();
    let numeric = value
        .strip_prefix(PYYAML_NON_FINITE_PREFIX)
        .unwrap_or(value);
    match numeric.to_ascii_lowercase().as_str() {
        ".inf" | "+.inf" => Some(f64::INFINITY),
        "-.inf" => Some(f64::NEG_INFINITY),
        ".nan" | "+.nan" | "-.nan" => Some(f64::NAN),
        _ => numeric.parse().ok().or_else(|| {
            let bytes = numeric.as_bytes();
            let valid_underscores = bytes.iter().enumerate().all(|(index, byte)| {
                *byte != b'_'
                    || (index > 0
                        && index + 1 < bytes.len()
                        && bytes[index - 1].is_ascii_digit()
                        && bytes[index + 1].is_ascii_digit())
            });
            (valid_underscores && numeric.contains('_'))
                .then(|| numeric.replace('_', ""))
                .and_then(|value| value.parse().ok())
        }),
    }
}

fn build_tier_index(
    tier_rows: &[Row],
    name_rows: &[Row],
) -> DecisionLegacyResult<BTreeMap<String, Value>> {
    let names = name_rows
        .iter()
        .filter_map(|row| {
            let slug = normalize(field(row, "character_slug"));
            (!slug.is_empty()).then_some((slug, row))
        })
        .collect::<BTreeMap<_, _>>();
    let mut grouped = BTreeMap::<String, Vec<&Row>>::new();
    for row in tier_rows {
        let slug = normalize(field(row, "character_slug"));
        if !slug.is_empty() {
            grouped.entry(slug).or_default().push(row);
        }
    }
    let mut output = BTreeMap::new();
    for (slug, rows) in grouped {
        let mut best = rows[0];
        for row in rows.iter().copied().skip(1) {
            if float_text(field(row, "rating")) > float_text(field(best, "rating")) {
                best = row;
            }
        }
        let name = names.get(&slug).copied();
        let mut modes = Map::new();
        for row in &rows {
            let mode = field(row, "tier_mode");
            if mode.is_empty() {
                continue;
            }
            let rating = float_text(field(row, "rating"));
            let replace = modes
                .get(mode)
                .and_then(|v| v.get("rating"))
                .and_then(Value::as_f64)
                .is_none_or(|old| rating > old);
            if replace {
                modes.insert(
                    mode.to_owned(),
                    json!({
                        "mode_cn": row_value_or(row,"tier_mode_cn", ""), "tier": row_value_or(row,"tier", ""),
                        "rating": number(rating)?, "role_group_cn": row_value_or(row,"role_group_cn", "")
                    }),
                );
            }
        }
        let mut meta = Map::new();
        for (key, value) in best {
            meta.insert(
                key.clone(),
                value
                    .as_ref()
                    .map(|value| Value::String(value.clone()))
                    .unwrap_or(Value::Null),
            );
        }
        meta.insert("character_slug".to_owned(), Value::String(slug.clone()));
        let cn = if !field(best, "character_name_cn").is_empty() {
            field(best, "character_name_cn")
        } else {
            name.map(|r| field(r, "character_name_cn")).unwrap_or("")
        };
        let en = if !field(best, "character_name_en").is_empty() {
            field(best, "character_name_en")
        } else {
            name.map(|r| field(r, "character_name_en")).unwrap_or("")
        };
        meta.insert("character_name_cn".to_owned(), Value::String(cn.to_owned()));
        meta.insert("character_name_en".to_owned(), Value::String(en.to_owned()));
        meta.insert("best_tier".to_owned(), row_value_or(best, "tier", ""));
        meta.insert(
            "best_rating".to_owned(),
            number(float_text(field(best, "rating")))?,
        );
        meta.insert("modes".to_owned(), Value::Object(modes));
        output.insert(slug, Value::Object(meta));
    }
    Ok(output)
}

fn candidate_rows(value: Option<&Value>) -> Vec<Map<String, Value>> {
    match value {
        Some(Value::Array(rows)) => rows.iter().filter_map(Value::as_object).cloned().collect(),
        Some(Value::Object(rows)) => rows
            .iter()
            .map(|(slug, value)| {
                let mut row = value.as_object().cloned().unwrap_or_default();
                row.entry("slug".to_owned())
                    .or_insert_with(|| Value::String(slug.clone()));
                row
            })
            .collect(),
        _ => Vec::new(),
    }
}

fn build_candidate_configs(
    profile: &BoxProfile,
    tiers: &BTreeMap<String, Value>,
    rules: &Map<String, Value>,
) -> Vec<Map<String, Value>> {
    let mut configs = Vec::<Map<String, Value>>::new();
    let mut seen = BTreeSet::new();
    for mut row in candidate_rows(rules.get("candidates")) {
        let slug = normalize(&value_text(first_value(
            &row,
            &["slug", "character_slug", "name"],
        )));
        if slug.is_empty() {
            continue;
        }
        row.entry("slug".to_owned())
            .or_insert_with(|| Value::String(slug.clone()));
        row.entry("source".to_owned())
            .or_insert_with(|| Value::String("rules".to_owned()));
        if seen.insert(slug.clone()) {
            configs.push(row);
        } else if let Some(existing) = configs
            .iter_mut()
            .find(|candidate| normalize(&value_text(candidate.get("slug"))) == slug)
        {
            *existing = row;
        }
    }
    let min_rating = value_f64(rules.get("candidate_min_rating"), 9.0);
    let mut generated = tiers
        .iter()
        .filter(|(slug, meta)| {
            meta.get("best_rating")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
                >= min_rating
                || profile.agents.get(*slug).is_some_and(|a| a.owned)
        })
        .map(|(slug, meta)| {
            (
                slug.clone(),
                meta.get("best_rating")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
            )
        })
        .collect::<Vec<_>>();
    generated.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let raw_limit = value_f64(rules.get("max_generated_candidates"), 30.0);
    let converted_limit = raw_limit as isize;
    let signed_limit = if converted_limit == 0 {
        30
    } else {
        converted_limit
    };
    let limit = if signed_limit < 0 {
        generated.len().saturating_sub(signed_limit.unsigned_abs())
    } else {
        signed_limit as usize
    };
    for (slug, _) in generated.into_iter().take(limit) {
        if seen.insert(slug.clone()) {
            configs.push(Map::from_iter([
                ("slug".to_owned(), Value::String(slug)),
                (
                    "source".to_owned(),
                    Value::String("generated_from_local_tier".to_owned()),
                ),
            ]));
        }
    }
    for slug in profile.agents.keys() {
        if tiers.contains_key(slug) && seen.insert(slug.clone()) {
            configs.push(Map::from_iter([
                ("slug".to_owned(), Value::String(slug.clone())),
                (
                    "source".to_owned(),
                    Value::String("owned_from_box".to_owned()),
                ),
            ]));
        }
    }
    configs
}

fn build_card(
    candidate: &Map<String, Value>,
    profile: &BoxProfile,
    tiers: &BTreeMap<String, Value>,
    data: &DecisionData,
    rules: &Map<String, Value>,
) -> DecisionLegacyResult<Option<Value>> {
    let slug = normalize(&value_text(candidate.get("slug")));
    if slug.is_empty() {
        return Ok(None);
    }
    let meta = tiers
        .get(&slug)
        .cloned()
        .unwrap_or_else(|| meta_from_candidate(candidate, &data.name_rows));
    let agent = profile.agents.get(&slug);
    let history = summarize_history(&slug, data)?;
    let replacement = replacement_risk(&slug, &meta, profile, tiers)?;
    let investment = investment(agent, rules)?;
    let candidate_type = candidate_type(candidate, &meta, &history);
    let release = release_risk(&candidate_type, &history);
    let (decision, reasons, warnings, score) = decide(
        candidate,
        &meta,
        agent,
        &history,
        &replacement,
        &investment,
        rules,
    )?;
    let max_stage = nonempty_candidate_rule(
        candidate,
        "max_recommended_stage",
        rules,
        "default_max_recommended_stage",
        "0+1",
    );
    let stages = compare_stages(agent, &decision, &max_stage, rules)?;
    let name_cn = first_nonempty_strings(&[
        text(&meta, "character_name_cn"),
        value_text(
            candidate
                .get("name_cn")
                .filter(|value| python_truthy(value)),
        ),
        text(&meta, "character_name_en"),
        slug.clone(),
    ]);
    let name_en = first_nonempty_strings(&[
        text(&meta, "character_name_en"),
        value_text(
            candidate
                .get("name_en")
                .filter(|value| python_truthy(value)),
        ),
    ]);
    let modes = meta.get("modes").cloned().unwrap_or_else(|| json!({}));
    let tier_summary = json!({
        "best_tier": value_or_empty(&meta,"best_tier"), "best_rating": meta.get("best_rating").cloned().unwrap_or_else(|| Value::from(0)), "modes": modes,
        "role_group": value_or_empty(&meta,"role_group"), "role_group_cn": value_or_empty(&meta,"role_group_cn"),
        "element": value_or_empty(&meta,"element"), "element_cn": value_or_empty(&meta,"element_cn"), "style": value_or_empty(&meta,"style"), "style_cn": value_or_empty(&meta,"style_cn"), "rarity": value_or_empty(&meta,"rarity")
    });
    Ok(Some(json!({
        "slug": slug, "name_cn": name_cn, "name_en": name_en,
        "owned": agent.is_some_and(|a| a.owned), "current_stage": agent.filter(|a| a.owned).map(Agent::stage).unwrap_or_else(|| "未拥有".to_owned()),
        "candidate_type": candidate_type, "decision": decision, "decision_score": number(score)?, "decision_reasons": reasons, "warnings": warnings,
        "tier_summary": tier_summary, "history_summary": history, "release_risk": release, "replacement_risk": replacement,
        "investment": investment, "stage_comparison": stages,
        "notes": candidate.get("notes").cloned().unwrap_or_else(|| Value::String(String::new())),
        "source": candidate.get("source").cloned().unwrap_or_else(|| Value::String("generated_from_local_tier".to_owned()))
    })))
}

fn meta_from_candidate(candidate: &Map<String, Value>, names: &[Row]) -> Value {
    let slug = normalize(&value_text(candidate.get("slug")));
    let name = names
        .iter()
        .find(|r| normalize(field(r, "character_slug")) == slug);
    json!({"character_slug":slug,
        "character_name_cn":first_nonempty_strings(&[python_or_text(candidate.get("name_cn")),name.map(|r|field(r,"character_name_cn").to_owned()).unwrap_or_default()]),
        "character_name_en":first_nonempty_strings(&[python_or_text(candidate.get("name_en")),name.map(|r|field(r,"character_name_en").to_owned()).unwrap_or_default()]),
        "best_tier":"","best_rating":0,"modes":{},"role_group":python_or_text(candidate.get("role_group")),"role_group_cn":python_or_text(candidate.get("role_group_cn")),
        "element":python_or_text(candidate.get("element")),"element_cn":python_or_text(candidate.get("element_cn")),"style":python_or_text(candidate.get("style")),"style_cn":python_or_text(candidate.get("style_cn")),"rarity":python_or_text(candidate.get("rarity"))})
}

fn first_nonempty_strings(values: &[String]) -> String {
    values
        .iter()
        .find(|v| !v.is_empty())
        .cloned()
        .unwrap_or_default()
}
fn python_or_text(value: Option<&Value>) -> String {
    value
        .filter(|value| python_truthy(value))
        .map(|value| value_text(Some(value)))
        .unwrap_or_default()
}
fn nonempty_candidate_rule(
    candidate: &Map<String, Value>,
    ck: &str,
    rules: &Map<String, Value>,
    rk: &str,
    default: &str,
) -> String {
    let a = python_or_text(candidate.get(ck));
    if !a.is_empty() {
        a
    } else {
        let b = python_or_text(rules.get(rk));
        if b.is_empty() {
            default.to_owned()
        } else {
            b
        }
    }
}

fn summarize_history(slug: &str, data: &DecisionData) -> DecisionLegacyResult<Value> {
    let usage = data
        .usage_rows
        .iter()
        .filter(|r| normalize(field(r, "character_slug")) == slug)
        .collect::<Vec<_>>();
    let teams = data
        .team_rows
        .iter()
        .filter(|r| (1..=3).any(|n| normalize(field(r, &format!("char_{n}_slug"))) == slug))
        .collect::<Vec<_>>();
    let mut mode_order = Vec::new();
    let mut grouped = BTreeMap::<String, Vec<&Row>>::new();
    for row in usage {
        let mode = field(row, "mode").to_owned();
        if !grouped.contains_key(&mode) {
            mode_order.push(mode.clone());
        }
        grouped.entry(mode).or_default().push(row);
    }
    let mut modes = Map::new();
    for mode in mode_order {
        let rows = &grouped[&mode];
        let primary = {
            let all = rows
                .iter()
                .copied()
                .filter(|r| field(r, "sub_mode") == "all")
                .collect::<Vec<_>>();
            if all.is_empty() {
                rows.clone()
            } else {
                all
            }
        };
        let mut dated = BTreeMap::<String, Vec<&Row>>::new();
        for r in primary {
            dated
                .entry(field(r, "collect_date").to_owned())
                .or_default()
                .push(r);
        }
        let mut points = dated
            .into_iter()
            .map(|(d, rs)| {
                (
                    d,
                    rs.iter()
                        .map(|r| float_text(field(r, "app_rate")))
                        .max_by(f64::total_cmp)
                        .unwrap_or(0.0),
                )
            })
            .collect::<Vec<_>>();
        points.sort_by(|a, b| a.0.cmp(&b.0));
        if points.is_empty() {
            continue;
        }
        let values = points.iter().map(|v| v.1).collect::<Vec<_>>();
        let latest = points.last().unwrap();
        let take = values.len().min(3);
        let avg = round3(values[values.len() - take..].iter().sum::<f64>() / take as f64);
        let trend = if values.len() >= 2 {
            round3(values.last().unwrap() - values.first().unwrap())
        } else {
            0.0
        };
        let trend_value = if values.len() >= 2 {
            number(trend)?
        } else {
            Value::from(0)
        };
        let mode_cn = row_value_or(rows[0], "mode_cn", &mode);
        modes.insert(mode.clone(),json!({"mode_cn":mode_cn,"points":points.len(),"latest_collect_date":latest.0,"latest_app_rate":number(latest.1)?,"avg_last3_app_rate":number(avg)?,"peak_app_rate":number(values.iter().copied().max_by(f64::total_cmp).unwrap_or(0.0))?,"trend_delta":trend_value}));
    }
    let mut ranks = Vec::new();
    for row in &teams {
        let raw = field(row, "rank");
        if raw.is_empty() {
            continue;
        }
        let rank = float_text(raw);
        if !rank.is_finite() {
            return Err(DecisionLegacyError::Invalid(
                "non-finite raw team rank".to_owned(),
            ));
        }
        ranks.push(rank);
    }
    let best_rank = ranks.into_iter().min_by(f64::total_cmp).unwrap_or(0.0);
    let mut latest = teams.clone();
    latest.sort_by(|a, b| {
        field(b, "collect_date")
            .cmp(field(a, "collect_date"))
            .then_with(|| {
                float_text(field(a, "app_rate")).total_cmp(&float_text(field(b, "app_rate")))
            })
    });
    latest.truncate(5);
    let examples = latest
        .iter()
        .map(|r| team_label(r))
        .collect::<DecisionLegacyResult<Vec<_>>>()?;
    let hits = data
        .changelog_rows
        .iter()
        .filter(|r| {
            field(r, "character_slugs").contains(slug)
                || field(r, "text")
                    .to_ascii_lowercase()
                    .contains(&slug.replace('-', " "))
        })
        .collect::<Vec<_>>();
    let usage_points = modes
        .values()
        .filter_map(|v| v.get("points").and_then(Value::as_u64))
        .sum::<u64>();
    let changelog_latest = hits
        .first()
        .map(|row| row_value_or_null(row, "changelog_date"))
        .unwrap_or_else(|| Value::String(String::new()));
    Ok(
        json!({"usage_points":usage_points,"modes":modes,"team_appearances":teams.len(),"best_team_rank":if best_rank==0.0{Value::String(String::new())}else{Value::from(best_rank as i64)},"latest_team_examples":examples,"changelog_mentions":hits.len(),"changelog_latest":changelog_latest}),
    )
}

fn team_label(row: &Row) -> DecisionLegacyResult<Value> {
    let names = (1..=3)
        .map(|n| {
            let cn = field(row, &format!("char_{n}_name_cn"));
            if cn.is_empty() {
                field(row, &format!("char_{n}_slug"))
            } else {
                cn
            }
        })
        .filter(|v| !v.is_empty())
        .collect::<Vec<_>>();
    let app_rate = match parse_percent(field(row, "app_rate")) {
        Some(value) => number(value)?,
        None => Value::Null,
    };
    Ok(
        json!({"collect_date":row_value_or(row,"collect_date",""),"mode_cn":row_value_or(row,"mode_cn",""),"sub_mode_cn":row_value_or(row,"sub_mode_cn",""),"rank":row_value_or(row,"rank",""),"app_rate":app_rate,"team":names.join(" / ")}),
    )
}

fn replacement_risk(
    slug: &str,
    meta: &Value,
    profile: &BoxProfile,
    tiers: &BTreeMap<String, Value>,
) -> DecisionLegacyResult<Value> {
    let role = text(meta, "role_group");
    let style = text(meta, "style");
    let element = text(meta, "element");
    let candidate_rating = meta
        .get("best_rating")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let mut reps = Vec::new();
    for (owned_slug, agent) in &profile.agents {
        if owned_slug == slug || !agent.owned {
            continue;
        }
        let owned = tiers.get(owned_slug).cloned().unwrap_or_else(|| json!({}));
        let same_role = legacy_match_value(&role, text(&owned, "role_group") == role);
        let same_style = legacy_match_value(&style, text(&owned, "style") == style);
        let same_element = legacy_match_value(&element, text(&owned, "element") == element);
        if !(python_truthy(&same_role)
            || (python_truthy(&same_style) && python_truthy(&same_element)))
        {
            continue;
        }
        let rating = owned
            .get("best_rating")
            .and_then(Value::as_f64)
            .unwrap_or(0.0);
        reps.push(json!({"slug":owned_slug,"name_cn":if !agent.name_cn.is_empty(){agent.name_cn.clone()}else{first_nonempty_strings(&[text(&owned,"character_name_cn"),text(&owned,"character_name_en"),owned_slug.clone()])},"tier":text(&owned,"best_tier"),"rating":number(rating)?,"same_role":same_role,"same_style":same_style,"same_element":same_element}));
    }
    reps.sort_by(|a, b| {
        b.get("rating")
            .and_then(Value::as_f64)
            .unwrap_or(0.0)
            .total_cmp(&a.get("rating").and_then(Value::as_f64).unwrap_or(0.0))
            .then_with(|| text(a, "slug").cmp(&text(b, "slug")))
    });
    let strong = reps.iter().any(|r| {
        r.get("same_role").is_some_and(python_truthy)
            && r.get("rating").and_then(Value::as_f64).unwrap_or(0.0)
                >= 9.0f64.max(candidate_rating - 1.0)
    });
    let (level, reason) = if strong {
        ("高", "Box 内已有同定位高评级角色，新增收益可能被稀释")
    } else if !reps.is_empty() {
        ("中", "Box 内已有相近定位角色，需要看当期环境是否点名")
    } else {
        ("低", "Box 内暂无明显同定位替代")
    };
    reps.truncate(5);
    Ok(json!({"level":level,"reason":reason,"replacements":reps}))
}

fn legacy_match_value(source: &str, matches: bool) -> Value {
    if source.is_empty() {
        Value::String(String::new())
    } else {
        Value::Bool(matches)
    }
}

fn investment(agent: Option<&Agent>, rules: &Map<String, Value>) -> DecisionLegacyResult<Value> {
    let Some(agent) = agent.filter(|a| a.owned) else {
        return Ok(
            json!({"status":"未拥有","score":0,"warnings":["未拥有，练度不可评估"],"ready":false}),
        );
    };
    let thresholds = rules
        .get("investment_thresholds")
        .and_then(Value::as_object);
    let target = |key: &str, default: i64| {
        thresholds
            .and_then(|m| m.get(key))
            .map(|v| value_i64(Some(v), 0))
            .unwrap_or(default)
    };
    let checks = [
        ("等级", agent.level, target("level", 60)),
        ("音擎等级", agent.engine_level, target("w_engine_level", 60)),
        ("核心技", agent.core_skill, target("core_skill", 6)),
    ];
    let mut passed = 0;
    let mut warnings = Vec::new();
    for (label, value, target) in checks {
        if value.is_some_and(|v| v >= target) {
            passed += 1
        } else {
            warnings.push(format!(
                "{label}未达标：{} / {target}",
                value
                    .map(|v| v.to_string())
                    .unwrap_or_else(|| "未录入".to_owned())
            ));
        }
    }
    if !agent.drive_discs.is_empty()
        && matches!(
            agent.drive_discs.to_ascii_lowercase().as_str(),
            "missing" | "none" | "未刷" | "未成型"
        )
    {
        warnings.push("驱动盘未成型".to_owned());
    }
    let status = if passed == 3 && warnings.is_empty() {
        "已满练"
    } else {
        "需补练度"
    };
    Ok(
        json!({"status":status,"score":number(round3(passed as f64/3.0))?,"warnings":warnings,"ready":status=="已满练"}),
    )
}

fn candidate_type(candidate: &Map<String, Value>, meta: &Value, history: &Value) -> String {
    let direct = first_nonempty_strings(&[
        python_or_text(candidate.get("banner_type")),
        python_or_text(candidate.get("release_type")),
    ]);
    if !direct.is_empty() {
        return direct;
    }
    if matches!(
        text(meta, "is_new").to_ascii_lowercase().as_str(),
        "true" | "1" | "yes"
    ) {
        "new".to_owned()
    } else if history
        .get("usage_points")
        .and_then(Value::as_u64)
        .unwrap_or(0)
        > 0
    {
        "rerun_or_existing".to_owned()
    } else {
        "unknown".to_owned()
    }
}
fn release_risk(kind: &str, history: &Value) -> Value {
    match kind.to_ascii_lowercase().as_str() {
        "new" | "新角色" => {
            json!({"level":"高","reason":"新角色缺少完整高难周期样本，优先等实测"})
        }
        "satellite" | "卫星" => {
            json!({"level":"高","reason":"卫星信息不可验证，不能按正式强度处理"})
        }
        _ if history
            .get("usage_points")
            .and_then(Value::as_u64)
            .unwrap_or(0)
            == 0 =>
        {
            json!({"level":"中","reason":"本地数据中暂无出场历史"})
        }
        _ => json!({"level":"低","reason":"已有本地高难历史可参考"}),
    }
}
fn round3(v: f64) -> f64 {
    (v * 1000.0).round_ties_even() / 1000.0
}
fn round2(v: f64) -> f64 {
    (v * 100.0).round_ties_even() / 100.0
}
fn stage_tuple(value: &str) -> (i64, i64) {
    value
        .split_once('+')
        .and_then(|(a, b)| Some((a.parse().ok()?, b.parse().ok()?)))
        .unwrap_or((-1, 0))
}

fn max_avg(history: &Value) -> f64 {
    history
        .get("modes")
        .and_then(Value::as_object)
        .into_iter()
        .flat_map(|m| m.values())
        .filter_map(|v| v.get("avg_last3_app_rate").and_then(Value::as_f64))
        .max_by(f64::total_cmp)
        .unwrap_or(0.0)
}
fn worst_trend(history: &Value) -> f64 {
    history
        .get("modes")
        .and_then(Value::as_object)
        .into_iter()
        .flat_map(|m| m.values())
        .filter_map(|v| v.get("trend_delta").and_then(Value::as_f64))
        .min_by(f64::total_cmp)
        .unwrap_or(0.0)
}

fn decide(
    candidate: &Map<String, Value>,
    meta: &Value,
    agent: Option<&Agent>,
    history: &Value,
    replacement: &Value,
    investment: &Value,
    rules: &Map<String, Value>,
) -> DecisionLegacyResult<(String, Vec<String>, Vec<String>, f64)> {
    let rating = meta
        .get("best_rating")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let owned = agent.is_some_and(|a| a.owned);
    let kind = candidate_type(candidate, meta, history);
    let points = history
        .get("usage_points")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let rep = text(replacement, "level");
    let rule = |key: &str, default: f64| value_f64(rules.get(key), default);
    let low = rule("low_tier_warning_rating", 9.0);
    let pull = rule("pull_rating", 10.0);
    let skip = rule("skip_rating", 8.0);
    let trend_warn = rule("trend_warning_delta", -5.0);
    let min_usage = rule("min_pull_avg_usage", 5.0);
    let bad_delta = rule("bad_trend_block_delta", -10.0);
    let bad_usage = rule("bad_trend_block_avg_usage", 20.0);
    let avg = max_avg(history);
    let worst = worst_trend(history);
    let mut reasons = Vec::new();
    let mut warnings = Vec::new();
    let mut score = round2(rating * 10.0 + avg.min(30.0));
    let forced = candidate
        .get("force_decision")
        .filter(|value| python_truthy(value))
        .map(|value| value_text(Some(value)))
        .unwrap_or_default();
    if !forced.is_empty() {
        reasons.push("规则配置指定了决策结论".to_owned());
        return Ok((forced, reasons, warnings, score));
    }
    if rating != 0.0 && rating <= low {
        warnings.push(format!(
            "当前最好定位为 {}，属于 T1 或以下，投入前要谨慎",
            {
                let v = text(meta, "best_tier");
                if v.is_empty() {
                    "低评级".to_owned()
                } else {
                    v
                }
            }
        ));
        score -= 8.0;
    }
    if worst <= trend_warn {
        warnings.push("近半年出场率走势明显下滑".to_owned());
        score -= 6.0;
    }
    if points > 0 && avg < min_usage {
        warnings.push(format!(
            "近三期最高均值出场率低于 {}%",
            python_number(min_usage)
        ));
        score -= 10.0;
    }
    if rep == "高" {
        warnings.push({
            let v = text(replacement, "reason");
            if v.is_empty() {
                "存在较强替代".to_owned()
            } else {
                v
            }
        });
        score -= 8.0;
    }
    if owned {
        if let Some(extra) = investment.get("warnings").and_then(Value::as_array) {
            warnings.extend(extra.iter().filter_map(Value::as_str).map(str::to_owned));
        }
    }
    let current = stage_tuple(
        &agent
            .filter(|a| a.owned)
            .map(Agent::stage)
            .unwrap_or_else(|| "-1+0".to_owned()),
    );
    let max = stage_tuple(&nonempty_candidate_rule(
        candidate,
        "max_recommended_stage",
        rules,
        "default_max_recommended_stage",
        "0+1",
    ));
    if owned && current >= max {
        reasons.push(format!(
            "本地 Box 已达到 {}，第一版规则认为无需继续加仓",
            agent.unwrap().stage()
        ));
        return Ok(("停止加仓".to_owned(), reasons, warnings, score));
    }
    if matches!(kind.as_str(), "new" | "satellite" | "新角色" | "卫星") || (points == 0 && !owned)
    {
        reasons.push("本地高难历史不足，无法验证真实出场率和队伍稳定性".to_owned());
        return Ok(("等实测".to_owned(), reasons, warnings, score - 10.0));
    }
    if owned {
        if rating >= pull
            && current < max
            && candidate
                .get("allow_additional_copies")
                .is_some_and(python_truthy)
        {
            reasons.push("已拥有但规则允许补到目标档位".to_owned());
            return Ok(("抽".to_owned(), reasons, warnings, score));
        }
        reasons.push("已拥有角色优先补练度；命座/专武继续投入先暂停".to_owned());
        return Ok(("停止加仓".to_owned(), reasons, warnings, score));
    }
    if points > 0 && avg < min_usage {
        reasons.push("本地出场率过低，暂不进入抽取推荐".to_owned());
        return Ok(("不抽".to_owned(), reasons, warnings, score));
    }
    if worst <= bad_delta && avg < bad_usage {
        reasons.push("近期走势下滑且当前出场率不足以支撑推荐".to_owned());
        return Ok(("不抽".to_owned(), reasons, warnings, score));
    }
    if rating >= pull && rep != "高" {
        reasons.push(format!(
            "当前最好评级 {}，且 Box 内替代压力不高",
            text(meta, "best_tier")
        ));
        return Ok(("抽".to_owned(), reasons, warnings, score));
    }
    if rating <= skip || rep == "高" {
        reasons.push("评级或替代收益不足，当前不作为抽取目标".to_owned());
        return Ok(("不抽".to_owned(), reasons, warnings, score));
    }
    reasons.push("强度未到必抽线，除非 XP 或当期环境点名".to_owned());
    Ok(("不抽".to_owned(), reasons, warnings, score))
}

fn compare_stages(
    agent: Option<&Agent>,
    decision: &str,
    max_stage: &str,
    rules: &Map<String, Value>,
) -> DecisionLegacyResult<Vec<Value>> {
    let default = json!([{"stage":"0+0","label":"0+0 本体","pull_cost":1},{"stage":"0+1","label":"0+1 本体+专武","pull_cost":2},{"stage":"1+1","label":"1+1 一影+专武","pull_cost":3},{"stage":"2+1","label":"2+1 二影+专武","pull_cost":4}]);
    let ladder = rules
        .get("stage_ladder")
        .and_then(Value::as_array)
        .unwrap_or_else(|| default.as_array().unwrap())
        .clone();
    let current = stage_tuple(
        &agent
            .filter(|a| a.owned)
            .map(Agent::stage)
            .unwrap_or_else(|| "-1+0".to_owned()),
    );
    let max = stage_tuple(max_stage);
    let mut rows = Vec::new();
    for item in ladder.iter().filter_map(Value::as_object) {
        let stage = item
            .get("stage")
            .filter(|value| python_truthy(value))
            .map(|value| value_text(Some(value)))
            .unwrap_or_default();
        let tuple = stage_tuple(&stage);
        let reached = current >= tuple;
        let beyond = tuple > max;
        let (value, advice) = if reached {
            ("已达成", "不用再投入")
        } else if beyond {
            ("低", "第一版不建议加仓")
        } else if decision == "抽" && stage == "0+0" {
            ("高", "优先看本体")
        } else if decision == "等实测" {
            ("未知", "等实测后再判断")
        } else if decision == "不抽" {
            ("低", "本期不作为抽取目标")
        } else {
            ("中", "仅作占位比较")
        };
        let label = item
            .get("label")
            .filter(|value| python_truthy(value))
            .cloned()
            .unwrap_or_else(|| Value::String(stage.clone()));
        rows.push(json!({"stage":stage,"label":label,"pull_cost":item.get("pull_cost").cloned().unwrap_or(Value::String(String::new())),"value":value,"advice":advice,"reached":reached,"placeholder":true}));
    }
    Ok(rows)
}

fn card_order(a: &Value, b: &Value) -> std::cmp::Ordering {
    fn rank(v: &str) -> u8 {
        match v {
            "抽" => 0,
            "等实测" => 1,
            "停止加仓" => 2,
            "不抽" => 3,
            _ => 9,
        }
    }
    rank(&text(a, "decision"))
        .cmp(&rank(&text(b, "decision")))
        .then_with(|| {
            b.get("decision_score")
                .and_then(Value::as_f64)
                .unwrap_or(0.0)
                .total_cmp(
                    &a.get("decision_score")
                        .and_then(Value::as_f64)
                        .unwrap_or(0.0),
                )
        })
        .then_with(|| text(a, "slug").cmp(&text(b, "slug")))
}

fn reject_non_finite(value: &Value) -> DecisionLegacyResult<()> {
    match value {
        Value::String(value) if value.starts_with(PYYAML_TIMESTAMP_PREFIX) => Err(
            DecisionLegacyError::Invalid("PyYAML timestamp is not JSON serializable".to_owned()),
        ),
        Value::String(value) if value.starts_with(PYYAML_NON_FINITE_PREFIX) => Err(
            DecisionLegacyError::Invalid("non-finite PyYAML numeric scalar".to_owned()),
        ),
        Value::Number(n) if n.as_f64().is_some_and(|v| !v.is_finite()) => Err(
            DecisionLegacyError::Invalid("non-finite legacy decision output".to_owned()),
        ),
        Value::Array(v) => {
            for x in v {
                reject_non_finite(x)?;
            }
            Ok(())
        }
        Value::Object(v) => {
            for x in v.values() {
                reject_non_finite(x)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}
fn python_number(v: f64) -> String {
    if v.fract() == 0.0 {
        format!("{v:.1}")
    } else {
        Number::from_f64(v)
            .map(|number| python_json_number_repr(&number))
            .unwrap_or_else(|| v.to_string())
    }
}

fn format_report(result: &Value, clock: NaiveDateTime) -> String {
    let summary = result.get("summary").and_then(Value::as_object);
    let cards = result
        .get("cards")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut out = String::new();
    writeln!(out, "# 绝区零 Box 抽取决策报告\n").unwrap();
    writeln!(out, "- 生成时间：{}", clock.format("%Y-%m-%dT%H:%M:%S")).unwrap();
    writeln!(
        out,
        "- 已识别拥有角色：{}",
        summary
            .and_then(|s| s.get("owned_agents"))
            .and_then(Value::as_u64)
            .unwrap_or(0)
    )
    .unwrap();
    writeln!(
        out,
        "- 候选角色数：{}",
        summary
            .and_then(|s| s.get("candidate_count"))
            .and_then(Value::as_u64)
            .unwrap_or(0)
    )
    .unwrap();
    let counts = summary
        .and_then(|s| s.get("decision_counts"))
        .and_then(Value::as_object)
        .map(|m| {
            m.iter()
                .map(|(k, v)| format!("{k} {}", v.as_u64().unwrap_or(0)))
                .collect::<Vec<_>>()
                .join(" / ")
        })
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| "-".to_owned());
    writeln!(out, "- 决策分布：{counts}").unwrap();
    let rows = summary.and_then(|s| s.get("data_rows"));
    writeln!(
        out,
        "- 数据行：T榜 {} / 出场 {} / 队伍 {}\n",
        rows.and_then(|v| v.get("tier_current"))
            .and_then(Value::as_u64)
            .unwrap_or(0),
        rows.and_then(|v| v.get("usage"))
            .and_then(Value::as_u64)
            .unwrap_or(0),
        rows.and_then(|v| v.get("teams"))
            .and_then(Value::as_u64)
            .unwrap_or(0)
    )
    .unwrap();
    out.push_str("## 怎么看\n\n- `抽`：当前数据和你的 Box 都支持优先拿到目标档位。\n- `不抽`：评级、出场、替代收益或账号需求不足。\n- `等实测`：新角色、卫星或本地高难样本不足，不建议只凭预期下结论。\n- `停止加仓`：已经拥有或已达到第一版建议档位，后续优先补练度或等环境变化。\n- 档位比较是占位框架：目前只比较 0+0 / 0+1 / 1+1 / 2+1 的投入顺序，不等同于真实命座收益曲线。\n\n## 候选角色\n\n");
    if cards.is_empty() {
        out.push_str(
            "- 暂无候选角色。请检查 `prydwen_tier_current.csv` 或在规则文件里维护 `candidates`。\n",
        );
        return out;
    }
    for card in cards {
        format_card(&mut out, &card);
    }
    out
}

fn format_card(out: &mut String, card: &Value) {
    let tier = card.get("tier_summary").unwrap_or(&Value::Null);
    let history = card.get("history_summary").unwrap_or(&Value::Null);
    let release = card.get("release_risk").unwrap_or(&Value::Null);
    let replacement = card.get("replacement_risk").unwrap_or(&Value::Null);
    let invest = card.get("investment").unwrap_or(&Value::Null);
    writeln!(
        out,
        "### {}：{}\n",
        {
            let n = text(card, "name_cn");
            if n.is_empty() {
                text(card, "slug")
            } else {
                n
            }
        },
        text(card, "decision")
    )
    .unwrap();
    writeln!(
        out,
        "- 识别：{}；当前档位：{}",
        if card.get("owned").and_then(Value::as_bool).unwrap_or(false) {
            "已拥有"
        } else {
            "未拥有"
        },
        text(card, "current_stage")
    )
    .unwrap();
    writeln!(
        out,
        "- 定位：{} / {} / {}；最好评级：{}",
        or_dash(text(tier, "role_group_cn")),
        or_dash(text(tier, "element_cn")),
        or_dash(text(tier, "style_cn")),
        or_dash(text(tier, "best_tier"))
    )
    .unwrap();
    writeln!(
        out,
        "- 依据：{}",
        array_text(card.get("decision_reasons"), "；", "-")
    )
    .unwrap();
    writeln!(out, "- 历史表现：{}", history_text(history)).unwrap();
    writeln!(
        out,
        "- 新/卫星风险：{}，{}",
        or_dash(text(release, "level")),
        or_dash(text(release, "reason"))
    )
    .unwrap();
    writeln!(
        out,
        "- 替代风险：{}，{}",
        or_dash(text(replacement, "level")),
        or_dash(text(replacement, "reason"))
    )
    .unwrap();
    writeln!(
        out,
        "- 练度：{}；{}",
        or_dash(text(invest, "status")),
        array_text(invest.get("warnings"), "；", "无")
    )
    .unwrap();
    if card
        .get("warnings")
        .and_then(Value::as_array)
        .is_some_and(|a| !a.is_empty())
    {
        writeln!(
            out,
            "- 高亮提醒：{}",
            array_text(card.get("warnings"), "；", "无")
        )
        .unwrap();
    }
    if let Some(reps) = replacement
        .get("replacements")
        .and_then(Value::as_array)
        .filter(|a| !a.is_empty())
    {
        let t = reps
            .iter()
            .take(3)
            .map(|v| format!("{}({})", text(v, "name_cn"), or_dash(text(v, "tier"))))
            .collect::<Vec<_>>()
            .join("、");
        writeln!(out, "- Box 替代：{t}").unwrap();
    }
    let stages = card
        .get("stage_comparison")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(|v| {
            format!(
                "{} {}({})",
                text(v, "stage"),
                text(v, "value"),
                text(v, "advice")
            )
        })
        .collect::<Vec<_>>()
        .join("；");
    writeln!(out, "- 档位占位：{stages}").unwrap();
    if card.get("notes").is_some_and(python_truthy) {
        writeln!(out, "- 备注：{}", text(card, "notes")).unwrap();
    }
    out.push('\n');
}
fn or_dash(v: String) -> String {
    if v.is_empty() {
        "-".to_owned()
    } else {
        v
    }
}
fn array_text(v: Option<&Value>, sep: &str, empty: &str) -> String {
    v.and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join(sep)
        })
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| empty.to_owned())
}
fn history_text(h: &Value) -> String {
    let Some(modes) = h
        .get("modes")
        .and_then(Value::as_object)
        .filter(|m| !m.is_empty())
    else {
        return "暂无本地高难出场历史".to_owned();
    };
    let mut parts = modes
        .values()
        .map(|m| {
            format!(
                "{} 最近{}%，近三期均值{}%，趋势{}",
                text(m, "mode_cn"),
                json_scalar(m.get("latest_app_rate")),
                json_scalar(m.get("avg_last3_app_rate")),
                json_scalar(m.get("trend_delta"))
            )
        })
        .collect::<Vec<_>>();
    let appearances = h
        .get("team_appearances")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    if appearances > 0 {
        parts.push(format!("入榜队伍 {appearances} 条，最好 rank {}", {
            let v = json_scalar(h.get("best_team_rank"));
            if v.is_empty() {
                "-".to_owned()
            } else {
                v
            }
        }));
    }
    parts.join("；")
}
fn json_scalar(v: Option<&Value>) -> String {
    match v {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Number(n)) => python_json_number_repr(n),
        Some(Value::Bool(b)) => b.to_string(),
        _ => String::new(),
    }
}

fn normalize_python_json_numbers(input: &[u8]) -> Vec<u8> {
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
