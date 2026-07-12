//! Evidence-first V1 team coverage core.
//!
//! This module deliberately owns no path or clock discovery.  Trusted adapters
//! supply the complete input documents and one explicit local datetime.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;

use chrono::NaiveDateTime;
use csv::{ReaderBuilder, StringRecord, WriterBuilder};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::decision_legacy::{
    normalize_pyyaml_11_bool_scalars, PYYAML_NON_FINITE_PREFIX, PYYAML_TIMESTAMP_PREFIX,
};

pub const EVIDENCE_METHOD_VERSION: &str = "evidence-first-v1-20260712";

#[derive(Debug, thiserror::Error)]
pub enum EvidenceError {
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
    #[error("invalid evidence input: {0}")]
    Invalid(String),
}

pub type EvidenceResult<T> = std::result::Result<T, EvidenceError>;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum EvidenceGameV1 {
    Hsr,
    Zzz,
}

impl EvidenceGameV1 {
    fn expected_team_size(self) -> usize {
        match self {
            Self::Hsr => 4,
            Self::Zzz => 3,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EvidenceInputsV1 {
    pub team_rank_dedup_unordered_csv: Vec<u8>,
    #[serde(default)]
    pub name_map_csv: Option<Vec<u8>>,
    #[serde(default)]
    pub tier_csv: Option<Vec<u8>>,
    pub box_json: Vec<u8>,
    #[serde(default)]
    pub banner_plan_json: Option<Vec<u8>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ConfidencePolicyV1 {
    pub a_records: usize,
    pub a_phases: usize,
    pub a_breadth: usize,
    pub a_valid_scores: usize,
    pub a_max_sentinel_ratio: f64,
    pub b_plus_records: usize,
    pub b_plus_phases: usize,
    pub b_plus_breadth: usize,
    pub b_plus_valid_scores: usize,
    pub b_plus_max_sentinel_ratio: f64,
    #[serde(default = "default_true")]
    pub require_stability_for_a: bool,
}

fn default_true() -> bool {
    true
}

impl ConfidencePolicyV1 {
    fn validate(&self, mode: &str) -> EvidenceResult<()> {
        for (label, value) in [
            ("a_max_sentinel_ratio", self.a_max_sentinel_ratio),
            ("b_plus_max_sentinel_ratio", self.b_plus_max_sentinel_ratio),
        ] {
            if !value.is_finite() || !(0.0..=1.0).contains(&value) {
                return Err(EvidenceError::Invalid(format!(
                    "mode policy {mode}.{label} must be finite and within 0..=1"
                )));
            }
        }
        Ok(())
    }
}

pub fn default_mode_policies_v1() -> BTreeMap<String, ConfidencePolicyV1> {
    let zzz = ConfidencePolicyV1 {
        a_records: 12,
        a_phases: 4,
        a_breadth: 3,
        a_valid_scores: 8,
        a_max_sentinel_ratio: 0.25,
        b_plus_records: 6,
        b_plus_phases: 3,
        b_plus_breadth: 2,
        b_plus_valid_scores: 4,
        b_plus_max_sentinel_ratio: 0.5,
        require_stability_for_a: true,
    };
    let hsr = ConfidencePolicyV1 {
        a_records: 8,
        a_phases: 4,
        a_breadth: 1,
        a_valid_scores: 6,
        a_max_sentinel_ratio: 0.25,
        b_plus_records: 4,
        b_plus_phases: 2,
        b_plus_breadth: 1,
        b_plus_valid_scores: 3,
        b_plus_max_sentinel_ratio: 0.5,
        require_stability_for_a: true,
    };
    let mut policies = BTreeMap::new();
    for mode in ["sd", "da"] {
        policies.insert(mode.to_owned(), zzz.clone());
    }
    for mode in ["moc", "pf", "as", "aa"] {
        policies.insert(mode.to_owned(), hsr.clone());
    }
    policies
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidenceRequestV1 {
    #[serde(default = "method_version")]
    pub method_version: String,
    pub game: EvidenceGameV1,
    #[serde(default)]
    pub explicit_planned_slugs: Vec<String>,
    #[serde(default = "default_plan_statuses")]
    pub plan_statuses: Vec<String>,
    #[serde(default)]
    pub include_missing: bool,
    #[serde(default = "default_min_a_app_rate")]
    pub default_min_a_app_rate: f64,
    #[serde(default)]
    pub min_a_app_rate_by_mode: BTreeMap<String, f64>,
    /// Overrides and extensions are explicit; an input row whose mode is absent
    /// from the merged policy map is rejected.
    #[serde(default)]
    pub mode_policy_overrides: BTreeMap<String, ConfidencePolicyV1>,
}

fn method_version() -> String {
    EVIDENCE_METHOD_VERSION.to_owned()
}

fn default_plan_statuses() -> Vec<String> {
    vec!["next".to_owned()]
}

fn default_min_a_app_rate() -> f64 {
    10.0
}

impl Default for EvidenceRequestV1 {
    fn default() -> Self {
        Self {
            method_version: method_version(),
            game: EvidenceGameV1::Zzz,
            explicit_planned_slugs: Vec::new(),
            plan_statuses: default_plan_statuses(),
            include_missing: false,
            default_min_a_app_rate: default_min_a_app_rate(),
            min_a_app_rate_by_mode: BTreeMap::new(),
            mode_policy_overrides: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EvidenceContextV1 {
    pub local_datetime: NaiveDateTime,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct NameIndexV1 {
    pub aliases: BTreeMap<String, String>,
    pub names_cn: BTreeMap<String, String>,
    pub kinds: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct AccountStateV1 {
    pub owned: BTreeSet<String>,
    pub built: BTreeSet<String>,
    pub build_state_known: bool,
    pub owned_bangboo: BTreeSet<String>,
    pub bangboo_ownership_known: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct EvidenceQualityV1 {
    pub rows_total: usize,
    pub rows_included: usize,
    pub skipped_app_rate: usize,
    pub skipped_empty_team: usize,
    pub skipped_partial_team: usize,
    pub skipped_duplicate_agents: usize,
    pub missing_or_non_finite_score_rows: usize,
    pub sentinel_score_rows: usize,
    pub alias_entries: usize,
    pub stability_catalog_entries: usize,
    pub metric_name: String,
    pub modes: Vec<String>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum EvidenceConfidenceV1 {
    #[serde(rename = "A")]
    A,
    #[serde(rename = "B+")]
    BPlus,
    #[serde(rename = "B")]
    B,
    #[serde(rename = "B-")]
    BMinus,
    #[serde(rename = "C")]
    C,
}

impl EvidenceConfidenceV1 {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::A => "A",
            Self::BPlus => "B+",
            Self::B => "B",
            Self::BMinus => "B-",
            Self::C => "C",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TeamSignatureAggregateV1 {
    pub mode: String,
    pub mode_cn: String,
    pub evidence_key: String,
    pub team_signature: String,
    pub agent_signature: String,
    pub full_team_signature: String,
    pub team_slugs: Vec<String>,
    pub team_cn: Vec<String>,
    pub bangboo_slug: String,
    pub bangboo_name_cn: String,
    pub record_count: usize,
    pub duplicate_count: usize,
    pub snapshot_count: usize,
    pub phase_count: usize,
    pub mode_count: usize,
    pub scope_count: usize,
    pub boss_count: usize,
    pub source_kind_count: usize,
    pub max_app_rate: Option<f64>,
    pub median_app_rate: Option<f64>,
    pub best_rank: Option<i64>,
    pub best_score: Option<f64>,
    pub metric_name: String,
    pub metric_direction: String,
    pub non_sentinel_score_count: usize,
    pub sentinel_score_count: usize,
    pub valid_score_ratio: f64,
    pub confidence: EvidenceConfidenceV1,
    pub modes: Vec<String>,
    pub phase_versions: Vec<String>,
    pub phase_names: Vec<String>,
    pub scopes: Vec<String>,
    pub source_kinds: Vec<String>,
    pub observation_keys: Vec<String>,
    pub stability_status: String,
    pub evidence_comment: String,
    pub risk_comment: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidenceRecordV1 {
    pub evidence_id: String,
    pub scenario: String,
    pub mode: String,
    pub mode_cn: String,
    pub evidence_key: String,
    pub team_signature: String,
    pub agent_signature: String,
    pub full_team_signature: String,
    pub team_slugs: Vec<String>,
    pub team_cn: Vec<String>,
    pub bangboo_slug: String,
    pub bangboo_name_cn: String,
    pub bangboo_checked: String,
    pub owned_count: usize,
    pub built_count: usize,
    pub build_checked: String,
    pub unbuilt_parts: Vec<String>,
    pub plan_dependency: Vec<String>,
    pub missing_parts: Vec<String>,
    pub source_confidence: EvidenceConfidenceV1,
    pub confidence: EvidenceConfidenceV1,
    pub record_count: usize,
    pub duplicate_count: usize,
    pub snapshot_count: usize,
    pub phase_count: usize,
    pub mode_count: usize,
    pub scope_count: usize,
    pub boss_count: usize,
    pub source_kind_count: usize,
    pub max_app_rate: Option<f64>,
    pub median_app_rate: Option<f64>,
    pub best_rank: Option<i64>,
    pub best_score: Option<f64>,
    pub metric_name: String,
    pub metric_direction: String,
    pub non_sentinel_score_count: usize,
    pub sentinel_score_count: usize,
    pub valid_score_ratio: f64,
    pub modes: Vec<String>,
    pub phase_versions: Vec<String>,
    pub phase_names: Vec<String>,
    pub scopes: Vec<String>,
    pub source_kinds: Vec<String>,
    pub observation_keys: Vec<String>,
    pub stability_status: String,
    pub evidence_comment: String,
    pub risk_comment: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidenceSummaryV1 {
    pub method_version: String,
    pub generated_at: String,
    pub scenario: String,
    pub owned_count: usize,
    pub planned: Vec<String>,
    pub target_count: usize,
    pub aggregate_count: usize,
    pub composition_count: usize,
    pub included_records: usize,
    pub confidence_counts: BTreeMap<String, usize>,
    pub source_confidence_counts: BTreeMap<String, usize>,
    pub dependency_counts: BTreeMap<String, usize>,
    pub mode_counts: BTreeMap<String, usize>,
    pub include_missing: bool,
    pub default_min_a_app_rate: f64,
    pub min_a_app_rate_by_mode: BTreeMap<String, f64>,
    pub bangboo_ownership_known: bool,
    pub build_state_known: bool,
    pub data_quality: EvidenceQualityV1,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidencePoolV1 {
    pub records: Vec<EvidenceRecordV1>,
    pub summary: EvidenceSummaryV1,
    pub aggregates: Vec<TeamSignatureAggregateV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvidenceBundleV1 {
    pub method_version: String,
    pub generated_at: String,
    pub planned_slugs: Vec<String>,
    pub current: EvidencePoolV1,
    pub target: EvidencePoolV1,
}

#[derive(Debug, Clone)]
pub(crate) struct CsvTable {
    pub(crate) headers: Vec<String>,
    pub(crate) rows: Vec<BTreeMap<String, String>>,
}

#[derive(Debug, Clone)]
struct Observation {
    row: BTreeMap<String, String>,
    app_rate: f64,
    rank: Option<i64>,
    score: Option<f64>,
    score_sentinel: bool,
    metric_direction: String,
    duplicate_count: usize,
}

/// Build current and target pools without reading paths or consulting a clock.
pub fn build_evidence_bundle_v1(
    inputs: &EvidenceInputsV1,
    request: &EvidenceRequestV1,
    context: &EvidenceContextV1,
) -> EvidenceResult<EvidenceBundleV1> {
    validate_request(request)?;
    let names = parse_name_index(inputs.name_map_csv.as_deref())?;
    let account = parse_account(&inputs.box_json, &names)?;
    let stability = parse_stability_roles(inputs.tier_csv.as_deref(), &names)?;
    let mut planned = Vec::new();
    for slug in &request.explicit_planned_slugs {
        push_unique(&mut planned, canonical_slug(slug, &names));
    }
    if let Some(bytes) = inputs.banner_plan_json.as_deref() {
        for slug in planned_from_banner(bytes, request, context, &names)? {
            push_unique(&mut planned, slug);
        }
    }
    let mut policies = default_mode_policies_v1();
    for (mode, policy) in &request.mode_policy_overrides {
        policies.insert(mode.trim().to_ascii_lowercase(), policy.clone());
    }
    let (aggregates, quality) = build_aggregates(inputs, request, &names, &stability, &policies)?;
    let current = make_pool(
        "current_box",
        &aggregates,
        &quality,
        &account,
        &[],
        request,
        context,
    );
    let target = make_pool(
        "target_box",
        &aggregates,
        &quality,
        &account,
        &planned,
        request,
        context,
    );
    Ok(EvidenceBundleV1 {
        method_version: EVIDENCE_METHOD_VERSION.to_owned(),
        generated_at: format_local_datetime(context.local_datetime),
        planned_slugs: planned,
        current,
        target,
    })
}

fn validate_request(request: &EvidenceRequestV1) -> EvidenceResult<()> {
    if request.method_version != EVIDENCE_METHOD_VERSION {
        return Err(EvidenceError::Invalid(format!(
            "unsupported method version: {}",
            request.method_version
        )));
    }
    if !request.default_min_a_app_rate.is_finite() || request.default_min_a_app_rate < 0.0 {
        return Err(EvidenceError::Invalid(
            "default_min_a_app_rate must be finite and non-negative".to_owned(),
        ));
    }
    for (mode, value) in &request.min_a_app_rate_by_mode {
        if !value.is_finite() || *value < 0.0 {
            return Err(EvidenceError::Invalid(format!(
                "min_a_app_rate for {mode} must be finite and non-negative"
            )));
        }
    }
    for (mode, policy) in &request.mode_policy_overrides {
        if mode.trim().is_empty() {
            return Err(EvidenceError::Invalid(
                "mode policy key is empty".to_owned(),
            ));
        }
        policy.validate(mode)?;
    }
    Ok(())
}

pub(crate) fn parse_csv(bytes: &[u8], input: &'static str) -> EvidenceResult<CsvTable> {
    let text =
        std::str::from_utf8(bytes).map_err(|source| EvidenceError::Utf8 { input, source })?;
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let mut reader = ReaderBuilder::new()
        .flexible(false)
        .from_reader(text.as_bytes());
    let header_record = reader
        .headers()
        .map_err(|source| EvidenceError::Csv { input, source })?
        .clone();
    let headers = header_record.iter().map(str::to_owned).collect::<Vec<_>>();
    if headers.iter().any(|header| header.is_empty()) {
        return Err(EvidenceError::Invalid(format!(
            "{input} has an empty header"
        )));
    }
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record.map_err(|source| EvidenceError::Csv { input, source })?;
        rows.push(record_to_map(&header_record, &record));
    }
    Ok(CsvTable { headers, rows })
}

fn record_to_map(headers: &StringRecord, record: &StringRecord) -> BTreeMap<String, String> {
    headers
        .iter()
        .zip(record.iter())
        .map(|(key, value)| (key.to_owned(), value.to_owned()))
        .collect()
}

pub(crate) fn parse_name_index(bytes: Option<&[u8]>) -> EvidenceResult<NameIndexV1> {
    let Some(bytes) = bytes else {
        return Ok(NameIndexV1::default());
    };
    let table = parse_csv(bytes, "name_map.csv")?;
    let mut names = NameIndexV1::default();
    let mut indexed = Vec::new();
    for row in table.rows {
        let slug = normalize_slug(field(&row, "character_slug"));
        if slug.is_empty() {
            continue;
        }
        insert_alias(&mut names.aliases, &slug, &slug)?;
        let name = first_nonempty(&row, &["character_name_cn", "character_name_en"])
            .unwrap_or(&slug)
            .to_owned();
        names.names_cn.insert(slug.clone(), name);
        names
            .kinds
            .insert(slug.clone(), field(&row, "kind").to_owned());
        indexed.push((slug, row));
    }
    for (slug, row) in indexed {
        for alias in split_slugs(field(&row, "aliases")) {
            insert_alias(&mut names.aliases, &alias, &slug)?;
        }
    }
    Ok(names)
}

fn insert_alias(
    aliases: &mut BTreeMap<String, String>,
    alias: &str,
    canonical: &str,
) -> EvidenceResult<()> {
    if let Some(existing) = aliases.get(alias) {
        if existing != canonical {
            return Err(EvidenceError::Invalid(format!(
                "alias conflict: {alias} -> {existing} / {canonical}"
            )));
        }
    } else {
        aliases.insert(alias.to_owned(), canonical.to_owned());
    }
    Ok(())
}

pub(crate) fn parse_config(bytes: &[u8], input: &'static str) -> EvidenceResult<Value> {
    let text =
        std::str::from_utf8(bytes).map_err(|source| EvidenceError::Utf8 { input, source })?;
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    if text.trim_start().starts_with('{') {
        serde_json::from_str(text).map_err(|source| EvidenceError::Json { input, source })
    } else {
        let compatible = normalize_pyyaml_11_bool_scalars(text);
        let mut yaml_value: serde_yaml::Value = serde_yaml::from_str(&compatible)
            .map_err(|source| EvidenceError::Yaml { input, source })?;
        yaml_value
            .apply_merge()
            .map_err(|source| EvidenceError::Yaml { input, source })?;
        let mut value = serde_json::to_value(yaml_value)
            .map_err(|source| EvidenceError::Json { input, source })?;
        restore_or_reject_pyyaml_markers(&mut value, input)?;
        if !config_value_truthy(&value) {
            value = Value::Object(Default::default());
        }
        Ok(value)
    }
}

fn restore_or_reject_pyyaml_markers(value: &mut Value, input: &'static str) -> EvidenceResult<()> {
    match value {
        Value::String(text) if text.starts_with(PYYAML_NON_FINITE_PREFIX) => Err(
            EvidenceError::Invalid(format!("non-finite number in {input}")),
        ),
        Value::String(text) if text.starts_with(PYYAML_TIMESTAMP_PREFIX) => {
            *text = text[PYYAML_TIMESTAMP_PREFIX.len()..].to_owned();
            Ok(())
        }
        Value::Array(values) => {
            for value in values {
                restore_or_reject_pyyaml_markers(value, input)?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for value in values.values_mut() {
                restore_or_reject_pyyaml_markers(value, input)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn config_value_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().map(|value| value != 0.0).unwrap_or(true),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

pub(crate) fn parse_account(bytes: &[u8], names: &NameIndexV1) -> EvidenceResult<AccountStateV1> {
    let value = parse_config(bytes, "box config")?;
    let object = value
        .as_object()
        .ok_or_else(|| EvidenceError::Invalid("box.json root must be an object".to_owned()))?;
    let mut state = AccountStateV1::default();
    if let Some(owned) = object.get("owned") {
        collect_owned(owned, names, &mut state.owned);
    }
    if let Some(agents) = object.get("agents") {
        collect_agents(
            agents,
            names,
            &mut state.owned,
            &mut state.built,
            &mut state.build_state_known,
        );
    }
    if let Some(builds) = object.get("builds").and_then(Value::as_object) {
        state.build_state_known = true;
        for (slug, payload) in builds {
            if explicit_built(payload, true) {
                let slug = canonical_slug(slug, names);
                if !slug.is_empty() {
                    state.built.insert(slug);
                }
            }
        }
    }
    for key in ["bangboo", "bangboos", "owned_bangboo", "owned_bangboos"] {
        if let Some(value) = object.get(key) {
            state.bangboo_ownership_known = true;
            collect_owned(value, names, &mut state.owned_bangboo);
        }
    }
    Ok(state)
}

fn collect_owned(value: &Value, names: &NameIndexV1, output: &mut BTreeSet<String>) {
    match value {
        Value::Array(values) => {
            for item in values {
                if let Some(object) = item.as_object() {
                    if !truthy(object.get("owned").unwrap_or(&Value::Bool(true))) {
                        continue;
                    }
                    if let Some(raw) = object_slug(object) {
                        insert_nonempty(output, canonical_slug(raw, names));
                    }
                } else if let Some(raw) = scalar_text(item) {
                    insert_nonempty(output, canonical_slug(&raw, names));
                }
            }
        }
        Value::Object(values) => {
            for (slug, payload) in values {
                let is_owned = payload
                    .as_object()
                    .and_then(|row| row.get("owned"))
                    .map(truthy)
                    .unwrap_or_else(|| truthy(payload));
                if is_owned {
                    insert_nonempty(output, canonical_slug(slug, names));
                }
            }
        }
        Value::String(text) => {
            for slug in split_slugs(text) {
                insert_nonempty(output, canonical_slug(&slug, names));
            }
        }
        _ => {}
    }
}

fn collect_agents(
    value: &Value,
    names: &NameIndexV1,
    owned: &mut BTreeSet<String>,
    built: &mut BTreeSet<String>,
    build_known: &mut bool,
) {
    match value {
        Value::Array(rows) => {
            for row in rows.iter().filter_map(Value::as_object) {
                let Some(raw) = object_slug(row) else {
                    continue;
                };
                let slug = canonical_slug(raw, names);
                if truthy(row.get("owned").unwrap_or(&Value::Bool(true))) {
                    insert_nonempty(owned, slug.clone());
                }
                if let Some(value) = row.get("built") {
                    *build_known = true;
                    if explicit_built(value, false) {
                        insert_nonempty(built, slug);
                    }
                }
            }
        }
        Value::Object(rows) => {
            for (raw, payload) in rows {
                let slug = canonical_slug(raw, names);
                let is_owned = payload
                    .as_object()
                    .and_then(|row| row.get("owned"))
                    .map(truthy)
                    .unwrap_or_else(|| truthy(payload));
                if is_owned {
                    insert_nonempty(owned, slug.clone());
                }
                if let Some(value) = payload.as_object().and_then(|row| row.get("built")) {
                    *build_known = true;
                    if explicit_built(value, false) {
                        insert_nonempty(built, slug);
                    }
                }
            }
        }
        _ => {}
    }
}

fn object_slug(object: &serde_json::Map<String, Value>) -> Option<&str> {
    ["slug", "id", "name_en", "name"]
        .iter()
        .find_map(|key| object.get(*key).and_then(Value::as_str))
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Bool(value) => *value,
        Value::Null => true,
        _ => scalar_text(value)
            .map(|text| {
                !matches!(
                    text.trim().to_ascii_lowercase().as_str(),
                    "0" | "false" | "no" | "n" | "未拥有"
                )
            })
            .unwrap_or(true),
    }
}

fn explicit_built(value: &Value, allow_payload_mapping: bool) -> bool {
    match value {
        Value::Bool(value) => *value,
        Value::Null => false,
        Value::Number(number) => number.as_f64() == Some(1.0),
        Value::Object(object) => object
            .get("built")
            .map(|value| explicit_built(value, false))
            .unwrap_or(allow_payload_mapping && !object.is_empty()),
        Value::String(value) => matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "y" | "built" | "ready" | "已培养"
        ),
        Value::Array(_) => false,
    }
}

fn scalar_text(value: &Value) -> Option<String> {
    match value {
        Value::String(value) => Some(value.clone()),
        Value::Number(value) => Some(value.to_string()),
        Value::Bool(value) => Some(if *value { "True" } else { "False" }.to_owned()),
        Value::Null => None,
        _ => None,
    }
}

fn parse_stability_roles(
    bytes: Option<&[u8]>,
    names: &NameIndexV1,
) -> EvidenceResult<BTreeMap<String, String>> {
    let Some(bytes) = bytes else {
        return Ok(BTreeMap::new());
    };
    let table = parse_csv(bytes, "tier.csv")?;
    let mut roles = BTreeMap::<String, String>::new();
    for row in table.rows {
        let slug = canonical_slug(field(&row, "character_slug"), names);
        if slug.is_empty() {
            continue;
        }
        let text = [
            "role_group",
            "role_group_cn",
            "style",
            "style_cn",
            "path",
            "path_cn",
        ]
        .iter()
        .map(|key| field(&row, key).trim().to_ascii_lowercase())
        .collect::<Vec<_>>()
        .join(" ");
        roles
            .entry(slug)
            .and_modify(|existing| {
                existing.push(' ');
                existing.push_str(&text);
            })
            .or_insert(text);
    }
    Ok(roles)
}

fn planned_from_banner(
    bytes: &[u8],
    request: &EvidenceRequestV1,
    context: &EvidenceContextV1,
    names: &NameIndexV1,
) -> EvidenceResult<Vec<String>> {
    let value = parse_config(bytes, "banner plan config")?;
    let phases = value
        .as_object()
        .and_then(|object| object.get("phases"))
        .and_then(Value::as_array)
        .ok_or_else(|| {
            EvidenceError::Invalid("banner_plan.json phases must be an array".to_owned())
        })?;
    let statuses = request
        .plan_statuses
        .iter()
        .map(|status| status.trim().to_ascii_lowercase())
        .filter(|status| !status.is_empty())
        .collect::<BTreeSet<_>>();
    let mut planned = Vec::new();
    for phase in phases.iter().filter_map(Value::as_object) {
        let status = crate::visualizer::effective_banner_status(
            &Value::Object(phase.clone()),
            context.local_datetime,
        )
        .map_err(|error| EvidenceError::Invalid(format!("invalid banner plan: {error}")))?;
        if !statuses.is_empty() && !statuses.contains(&status) {
            continue;
        }
        if let Some(characters) = phase.get("characters").and_then(Value::as_array) {
            for character in characters.iter().filter_map(Value::as_object) {
                if let Some(raw) = character.get("slug").and_then(Value::as_str) {
                    push_unique(&mut planned, canonical_slug(raw, names));
                }
            }
        }
    }
    Ok(planned)
}

fn build_aggregates(
    inputs: &EvidenceInputsV1,
    request: &EvidenceRequestV1,
    names: &NameIndexV1,
    stability_roles: &BTreeMap<String, String>,
    policies: &BTreeMap<String, ConfidencePolicyV1>,
) -> EvidenceResult<(Vec<TeamSignatureAggregateV1>, EvidenceQualityV1)> {
    let table = parse_csv(
        &inputs.team_rank_dedup_unordered_csv,
        "team_rank_dedup_unordered.csv",
    )?;
    let mut char_columns = table
        .headers
        .iter()
        .filter_map(|header| {
            header
                .strip_prefix("char_")
                .and_then(|tail| tail.strip_suffix("_slug"))
                .and_then(|number| number.parse::<usize>().ok())
                .map(|number| (number, header.clone()))
        })
        .collect::<Vec<_>>();
    char_columns.sort_by_key(|(number, _)| *number);
    if char_columns.len() != request.game.expected_team_size() {
        return Err(EvidenceError::Invalid(format!(
            "{} requires exactly {} char_<n>_slug columns, found {}",
            match request.game {
                EvidenceGameV1::Hsr => "HSR",
                EvidenceGameV1::Zzz => "ZZZ",
            },
            request.game.expected_team_size(),
            char_columns.len()
        )));
    }
    if !table.headers.iter().any(|header| header == "mode") {
        return Err(EvidenceError::Invalid(
            "team_rank_dedup_unordered.csv is missing mode".to_owned(),
        ));
    }
    let metric_name = ["avg_round", "avg_score", "score"]
        .iter()
        .find(|candidate| table.headers.iter().any(|header| header == **candidate))
        .copied()
        .unwrap_or_default()
        .to_owned();
    let mut quality = EvidenceQualityV1 {
        rows_total: table.rows.len(),
        alias_entries: names.aliases.len(),
        stability_catalog_entries: stability_roles.len(),
        metric_name: metric_name.clone(),
        ..Default::default()
    };
    let mut groups = BTreeMap::<(String, Vec<String>, String), Vec<Observation>>::new();
    for row in table.rows {
        let Some(app_rate) = parse_finite(field(&row, "app_rate")) else {
            quality.skipped_app_rate += 1;
            continue;
        };
        if app_rate <= 0.0 {
            quality.skipped_app_rate += 1;
            continue;
        }
        let team = char_columns
            .iter()
            .map(|(_, column)| canonical_slug(field(&row, column), names))
            .filter(|slug| !slug.is_empty())
            .collect::<Vec<_>>();
        if team.is_empty() {
            quality.skipped_empty_team += 1;
            continue;
        }
        if team.len() != char_columns.len() {
            quality.skipped_partial_team += 1;
            continue;
        }
        if team.iter().collect::<BTreeSet<_>>().len() != team.len() {
            quality.skipped_duplicate_agents += 1;
            continue;
        }
        let mode = field(&row, "mode").trim().to_ascii_lowercase();
        if mode.is_empty() {
            return Err(EvidenceError::Invalid(
                "team evidence row is missing mode".to_owned(),
            ));
        }
        if !policies.contains_key(&mode) {
            return Err(EvidenceError::Invalid(format!(
                "team evidence row contains undeclared mode policy: {mode}"
            )));
        }
        let mut team = team;
        team.sort();
        let bangboo = canonical_slug(field(&row, "bangboo_slug"), names);
        let score = parse_finite(field(&row, &metric_name));
        let score_sentinel = score
            .map(|score| is_sentinel(request.game, &metric_name, score))
            .unwrap_or(true);
        quality.rows_included += 1;
        if score.is_none() {
            quality.missing_or_non_finite_score_rows += 1;
        }
        if score_sentinel {
            quality.sentinel_score_rows += 1;
        }
        let duplicate_count = parse_i64(field(&row, "duplicate_count"))
            .and_then(|value| usize::try_from(value).ok())
            .unwrap_or(1)
            .max(1);
        groups
            .entry((mode.clone(), team, bangboo))
            .or_default()
            .push(Observation {
                metric_direction: metric_direction(&mode, &metric_name).to_owned(),
                rank: parse_i64(field(&row, "rank")),
                row,
                app_rate,
                score,
                score_sentinel,
                duplicate_count,
            });
    }
    let mut aggregates = Vec::new();
    for ((mode, team, bangboo), observations) in groups {
        aggregates.push(aggregate_group(
            &mode,
            &team,
            &bangboo,
            &metric_name,
            observations,
            names,
            stability_roles,
            request,
            policies.get(&mode).expect("mode checked above"),
        ));
    }
    aggregates.sort_by(aggregate_order);
    quality.modes = aggregates
        .iter()
        .map(|aggregate| aggregate.mode.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    Ok((aggregates, quality))
}

#[allow(clippy::too_many_arguments)]
fn aggregate_group(
    mode: &str,
    team: &[String],
    bangboo: &str,
    metric_name: &str,
    observations: Vec<Observation>,
    names: &NameIndexV1,
    stability_roles: &BTreeMap<String, String>,
    request: &EvidenceRequestV1,
    policy: &ConfidencePolicyV1,
) -> TeamSignatureAggregateV1 {
    let mut app_rates = observations
        .iter()
        .map(|item| item.app_rate)
        .collect::<Vec<_>>();
    app_rates.sort_by(f64::total_cmp);
    let max_app_rate = app_rates.last().copied();
    let median_app_rate = median(&app_rates);
    let non_sentinel_scores = observations
        .iter()
        .filter(|item| !item.score_sentinel)
        .filter_map(|item| item.score)
        .collect::<Vec<_>>();
    let sentinel_score_count = observations.len() - non_sentinel_scores.len();
    let direction_set = observations
        .iter()
        .map(|item| item.metric_direction.clone())
        .collect::<BTreeSet<_>>();
    let metric_direction = if direction_set.len() == 1 {
        direction_set
            .iter()
            .next()
            .cloned()
            .unwrap_or_else(|| "unknown".to_owned())
    } else {
        "mixed".to_owned()
    };
    let best_score = match metric_direction.as_str() {
        "higher_better" => non_sentinel_scores.iter().copied().max_by(f64::total_cmp),
        "lower_better" => non_sentinel_scores.iter().copied().min_by(f64::total_cmp),
        _ => None,
    };
    let snapshots = collect_nonempty(&observations, |row| field(row, "snapshot_id").to_owned());
    let phase_versions = collect_nonempty(&observations, |row| {
        let phase = field(row, "phase_ver");
        if phase.is_empty() {
            String::new()
        } else {
            format!("{mode}:{phase}")
        }
    });
    let phase_names = collect_nonempty(&observations, |row| field(row, "phase_name").to_owned());
    let scopes = collect_nonempty(&observations, |row| {
        first_nonempty(row, &["scope", "sub_mode"])
            .unwrap_or_default()
            .to_owned()
    });
    let bosses = collect_nonempty(&observations, boss_key);
    let source_kinds = collect_nonempty(&observations, |row| field(row, "source_kind").to_owned());
    let observation_keys = observations
        .iter()
        .map(|item| observation_key(&item.row))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let stability_status = stability_status(request.game, team, stability_roles);
    let min_a_app_rate = request
        .min_a_app_rate_by_mode
        .get(mode)
        .copied()
        .unwrap_or(request.default_min_a_app_rate);
    let (confidence, evidence_comment, mut risk_comment) = classify(
        policy,
        observations.len(),
        phase_versions.len(),
        1,
        scopes.len(),
        bosses.len(),
        max_app_rate,
        median_app_rate,
        non_sentinel_scores.len(),
        sentinel_score_count,
        &stability_status,
        min_a_app_rate,
    );
    if metric_direction == "mixed" {
        append_comment(&mut risk_comment, "混合指标方向，best_score 不做跨方向比较");
    }
    let full_signature = full_team_signature(team, bangboo);
    let mode_names = collect_nonempty(&observations, |row| field(row, "mode_cn").to_owned());
    let bangboo_name_cn = names
        .names_cn
        .get(bangboo)
        .filter(|name| *name != bangboo)
        .cloned()
        .or_else(|| {
            observations
                .iter()
                .map(|item| field(&item.row, "bangboo_name_cn").trim())
                .find(|name| !name.is_empty())
                .map(str::to_owned)
        })
        .unwrap_or_else(|| bangboo.to_owned());
    TeamSignatureAggregateV1 {
        mode: mode.to_owned(),
        mode_cn: mode_names.first().cloned().unwrap_or_default(),
        evidence_key: format!("{mode}|{full_signature}"),
        team_signature: full_signature.clone(),
        agent_signature: team.join("|"),
        full_team_signature: full_signature,
        team_slugs: team.to_vec(),
        team_cn: team.iter().map(|slug| name_cn(slug, names)).collect(),
        bangboo_slug: bangboo.to_owned(),
        bangboo_name_cn,
        record_count: observations.len(),
        duplicate_count: observations.iter().map(|item| item.duplicate_count).sum(),
        snapshot_count: snapshots.len(),
        phase_count: phase_versions.len(),
        mode_count: 1,
        scope_count: scopes.len(),
        boss_count: bosses.len(),
        source_kind_count: source_kinds.len(),
        max_app_rate,
        median_app_rate,
        best_rank: observations.iter().filter_map(|item| item.rank).min(),
        best_score,
        metric_name: metric_name.to_owned(),
        metric_direction,
        non_sentinel_score_count: non_sentinel_scores.len(),
        sentinel_score_count,
        valid_score_ratio: non_sentinel_scores.len() as f64 / observations.len() as f64,
        confidence,
        modes: vec![mode.to_owned()],
        phase_versions,
        phase_names,
        scopes,
        source_kinds,
        observation_keys,
        stability_status,
        evidence_comment,
        risk_comment,
    }
}

fn collect_nonempty<F>(observations: &[Observation], mut value: F) -> Vec<String>
where
    F: FnMut(&BTreeMap<String, String>) -> String,
{
    observations
        .iter()
        .map(|item| value(&item.row))
        .filter(|value| !value.is_empty())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn classify(
    policy: &ConfidencePolicyV1,
    record_count: usize,
    phase_count: usize,
    mode_count: usize,
    scope_count: usize,
    boss_count: usize,
    max_app_rate: Option<f64>,
    median_app_rate: Option<f64>,
    non_sentinel_score_count: usize,
    sentinel_score_count: usize,
    stability_status: &str,
    min_a_app_rate: f64,
) -> (EvidenceConfidenceV1, String, String) {
    let max_app = max_app_rate.unwrap_or(0.0);
    let median_app = median_app_rate.unwrap_or(0.0);
    let total_scores = non_sentinel_score_count + sentinel_score_count;
    let sentinel_ratio = if total_scores == 0 {
        1.0
    } else {
        sentinel_score_count as f64 / total_scores as f64
    };
    let breadth_count = scope_count.max(boss_count);
    let note = format!(
        "record_count={record_count}；phase_count={phase_count}；mode_count={mode_count}；boss_count={boss_count}；scope_count={scope_count}；valid_score_count={non_sentinel_score_count}；sentinel_ratio={}；stability_status={stability_status}；max_app_rate={}；median_app_rate={}；min_a_app_rate={}",
        number_text(Some(sentinel_ratio)), number_text(max_app_rate), number_text(median_app_rate), number_text(Some(min_a_app_rate))
    );
    let mut risks = Vec::new();
    if non_sentinel_score_count == 0 {
        risks.push("全部表现分数为 sentinel/missing".to_owned());
        return (
            if record_count <= 1 {
                EvidenceConfidenceV1::C
            } else {
                EvidenceConfidenceV1::BMinus
            },
            note,
            risks.join("；"),
        );
    }
    if sentinel_score_count > 0 {
        risks.push(format!(
            "包含 {sentinel_score_count} 条 sentinel/missing 分数"
        ));
    }
    match stability_status {
        "absent" => risks.push("未检出稳定组件，不给 A".to_owned()),
        "unknown" => risks.push("缺角色职能数据，稳定组件未校验，不给 A".to_owned()),
        _ => {}
    }
    let stability_allows_a = !policy.require_stability_for_a || stability_status == "present";
    if record_count >= policy.a_records
        && phase_count >= policy.a_phases
        && breadth_count >= policy.a_breadth
        && non_sentinel_score_count >= policy.a_valid_scores
        && sentinel_ratio <= policy.a_max_sentinel_ratio
        && max_app >= min_a_app_rate
        && median_app >= 1.0
        && stability_allows_a
    {
        return (EvidenceConfidenceV1::A, note, risk_or(&risks, "无"));
    }
    if record_count >= policy.b_plus_records
        && phase_count >= policy.b_plus_phases
        && breadth_count >= policy.b_plus_breadth
        && non_sentinel_score_count >= policy.b_plus_valid_scores
        && sentinel_ratio <= policy.b_plus_max_sentinel_ratio
        && max_app >= (min_a_app_rate / 2.0).max(1.0)
    {
        return (
            EvidenceConfidenceV1::BPlus,
            note,
            risk_or(&risks, "重复度较好，但未达到 A 档广度/强度"),
        );
    }
    if record_count >= 3 && phase_count >= 2 && max_app >= 1.0 {
        return (
            EvidenceConfidenceV1::B,
            note,
            risk_or(&risks, "有重复记录，可作普通证据"),
        );
    }
    risks.push("记录稀疏或出场率较低".to_owned());
    (EvidenceConfidenceV1::BMinus, note, risks.join("；"))
}

fn risk_or(risks: &[String], fallback: &str) -> String {
    if risks.is_empty() {
        fallback.to_owned()
    } else {
        risks.join("；")
    }
}

fn make_pool(
    scenario: &str,
    aggregates: &[TeamSignatureAggregateV1],
    quality: &EvidenceQualityV1,
    account: &AccountStateV1,
    planned: &[String],
    request: &EvidenceRequestV1,
    context: &EvidenceContextV1,
) -> EvidencePoolV1 {
    let target = account
        .owned
        .iter()
        .cloned()
        .chain(planned.iter().cloned())
        .collect::<BTreeSet<_>>();
    let mut records = Vec::new();
    for aggregate in aggregates {
        let missing = aggregate
            .team_slugs
            .iter()
            .filter(|slug| !target.contains(*slug))
            .cloned()
            .collect::<Vec<_>>();
        if !missing.is_empty() && !request.include_missing {
            continue;
        }
        let mut dependency = planned
            .iter()
            .filter(|slug| aggregate.team_slugs.contains(*slug) && !account.owned.contains(*slug))
            .cloned()
            .collect::<Vec<_>>();
        if dependency.is_empty() {
            dependency.push("none".to_owned());
        }
        let unbuilt = if account.build_state_known {
            aggregate
                .team_slugs
                .iter()
                .filter(|slug| !account.built.contains(*slug))
                .cloned()
                .collect::<Vec<_>>()
        } else {
            Vec::new()
        };
        let confidence = account_confidence(
            aggregate.confidence,
            !missing.is_empty(),
            account.build_state_known,
            !unbuilt.is_empty(),
        );
        let bangboo_checked = if aggregate.bangboo_slug.is_empty() {
            "无邦布记录"
        } else if !account.bangboo_ownership_known {
            "邦布未校验"
        } else if account.owned_bangboo.contains(&aggregate.bangboo_slug) {
            "已拥有"
        } else {
            "缺邦布"
        };
        let mut risk = aggregate.risk_comment.clone();
        if !missing.is_empty() {
            append_comment(
                &mut risk,
                &format!("缺目标账号成员：{}", missing.join(", ")),
            );
        }
        match bangboo_checked {
            "缺邦布" => append_comment(
                &mut risk,
                &format!("Bangboo 记录缺拥有校验：{}", aggregate.bangboo_slug),
            ),
            "邦布未校验" => append_comment(&mut risk, "Bangboo 未参与账号覆盖校验"),
            _ => {}
        }
        if !unbuilt.is_empty() {
            append_comment(
                &mut risk,
                &format!("已拥有但未标记已培养：{}", unbuilt.join(", ")),
            );
        } else if !account.build_state_known {
            append_comment(&mut risk, "Box 未提供显式 build 状态，不推断已可上场");
        }
        records.push(EvidenceRecordV1 {
            evidence_id: stable_evidence_id(&aggregate.evidence_key, &aggregate.mode),
            scenario: scenario.to_owned(),
            mode: aggregate.mode.clone(),
            mode_cn: aggregate.mode_cn.clone(),
            evidence_key: aggregate.evidence_key.clone(),
            team_signature: aggregate.team_signature.clone(),
            agent_signature: aggregate.agent_signature.clone(),
            full_team_signature: aggregate.full_team_signature.clone(),
            team_slugs: aggregate.team_slugs.clone(),
            team_cn: aggregate.team_cn.clone(),
            bangboo_slug: aggregate.bangboo_slug.clone(),
            bangboo_name_cn: aggregate.bangboo_name_cn.clone(),
            bangboo_checked: bangboo_checked.to_owned(),
            owned_count: aggregate
                .team_slugs
                .iter()
                .filter(|slug| account.owned.contains(*slug))
                .count(),
            built_count: aggregate
                .team_slugs
                .iter()
                .filter(|slug| account.built.contains(*slug))
                .count(),
            build_checked: if account.build_state_known {
                "已读取"
            } else {
                "未提供"
            }
            .to_owned(),
            unbuilt_parts: none_if_empty(unbuilt),
            plan_dependency: dependency,
            missing_parts: none_if_empty(missing),
            source_confidence: aggregate.confidence,
            confidence,
            record_count: aggregate.record_count,
            duplicate_count: aggregate.duplicate_count,
            snapshot_count: aggregate.snapshot_count,
            phase_count: aggregate.phase_count,
            mode_count: aggregate.mode_count,
            scope_count: aggregate.scope_count,
            boss_count: aggregate.boss_count,
            source_kind_count: aggregate.source_kind_count,
            max_app_rate: aggregate.max_app_rate,
            median_app_rate: aggregate.median_app_rate,
            best_rank: aggregate.best_rank,
            best_score: aggregate.best_score,
            metric_name: aggregate.metric_name.clone(),
            metric_direction: aggregate.metric_direction.clone(),
            non_sentinel_score_count: aggregate.non_sentinel_score_count,
            sentinel_score_count: aggregate.sentinel_score_count,
            valid_score_ratio: aggregate.valid_score_ratio,
            modes: aggregate.modes.clone(),
            phase_versions: aggregate.phase_versions.clone(),
            phase_names: aggregate.phase_names.clone(),
            scopes: aggregate.scopes.clone(),
            source_kinds: aggregate.source_kinds.clone(),
            observation_keys: aggregate.observation_keys.clone(),
            stability_status: aggregate.stability_status.clone(),
            evidence_comment: aggregate.evidence_comment.clone(),
            risk_comment: risk,
        });
    }
    records.sort_by(coverage_order);
    let confidence_counts = count_values(
        records
            .iter()
            .map(|record| record.confidence.as_str().to_owned()),
    );
    let source_confidence_counts = count_values(
        records
            .iter()
            .map(|record| record.source_confidence.as_str().to_owned()),
    );
    let dependency_counts = count_values(
        records
            .iter()
            .map(|record| record.plan_dependency.join(",")),
    );
    let mode_counts = count_values(
        records
            .iter()
            .filter(|record| !record.mode.is_empty())
            .map(|record| record.mode.clone()),
    );
    EvidencePoolV1 {
        summary: EvidenceSummaryV1 {
            method_version: EVIDENCE_METHOD_VERSION.to_owned(),
            generated_at: format_local_datetime(context.local_datetime),
            scenario: scenario.to_owned(),
            owned_count: account.owned.len(),
            planned: planned.to_vec(),
            target_count: target.len(),
            aggregate_count: aggregates.len(),
            composition_count: aggregates
                .iter()
                .map(|aggregate| &aggregate.full_team_signature)
                .collect::<BTreeSet<_>>()
                .len(),
            included_records: records.len(),
            confidence_counts,
            source_confidence_counts,
            dependency_counts,
            mode_counts,
            include_missing: request.include_missing,
            default_min_a_app_rate: request.default_min_a_app_rate,
            min_a_app_rate_by_mode: request.min_a_app_rate_by_mode.clone(),
            bangboo_ownership_known: account.bangboo_ownership_known,
            build_state_known: account.build_state_known,
            data_quality: quality.clone(),
        },
        records,
        aggregates: aggregates.to_vec(),
    }
}

fn count_values<T: Ord>(values: impl Iterator<Item = T>) -> BTreeMap<T, usize> {
    let mut counts = BTreeMap::new();
    for value in values {
        *counts.entry(value).or_insert(0) += 1;
    }
    counts
}

fn account_confidence(
    source: EvidenceConfidenceV1,
    missing: bool,
    build_known: bool,
    unbuilt: bool,
) -> EvidenceConfidenceV1 {
    if missing {
        EvidenceConfidenceV1::C
    } else if (!build_known || unbuilt)
        && matches!(
            source,
            EvidenceConfidenceV1::A | EvidenceConfidenceV1::BPlus
        )
    {
        EvidenceConfidenceV1::B
    } else {
        source
    }
}

fn aggregate_order(
    a: &TeamSignatureAggregateV1,
    b: &TeamSignatureAggregateV1,
) -> std::cmp::Ordering {
    a.confidence
        .cmp(&b.confidence)
        .then_with(|| option_f64_desc(a.max_app_rate, b.max_app_rate))
        .then_with(|| b.record_count.cmp(&a.record_count))
        .then_with(|| a.mode.cmp(&b.mode))
        .then_with(|| a.team_signature.cmp(&b.team_signature))
}

fn coverage_order(a: &EvidenceRecordV1, b: &EvidenceRecordV1) -> std::cmp::Ordering {
    a.confidence
        .cmp(&b.confidence)
        .then_with(|| dependency_group(a).cmp(&dependency_group(b)))
        .then_with(|| option_f64_desc(a.max_app_rate, b.max_app_rate))
        .then_with(|| b.record_count.cmp(&a.record_count))
        .then_with(|| a.mode.cmp(&b.mode))
        .then_with(|| a.team_signature.cmp(&b.team_signature))
}

fn dependency_group(record: &EvidenceRecordV1) -> u8 {
    u8::from(
        record.plan_dependency.len() != 1
            || record.plan_dependency.first().is_none_or(|v| v != "none"),
    )
}

fn option_f64_desc(a: Option<f64>, b: Option<f64>) -> std::cmp::Ordering {
    b.unwrap_or(0.0).total_cmp(&a.unwrap_or(0.0))
}

fn stability_status(
    game: EvidenceGameV1,
    team: &[String],
    roles: &BTreeMap<String, String>,
) -> String {
    let markers: &[&str] = match game {
        EvidenceGameV1::Hsr => &[
            "sustain",
            "healer",
            "preservation",
            "abundance",
            "tank",
            "存护",
            "丰饶",
            "治疗",
            "生存",
            "护盾",
        ],
        EvidenceGameV1::Zzz => &[
            "support", "stun", "defense", "sustain", "healer", "辅助", "支援", "击破", "防护",
            "治疗",
        ],
    };
    let known = team
        .iter()
        .filter_map(|slug| roles.get(slug))
        .collect::<Vec<_>>();
    if known
        .iter()
        .any(|text| markers.iter().any(|marker| text.contains(marker)))
    {
        "present".to_owned()
    } else if !known.is_empty() && known.len() == team.len() {
        "absent".to_owned()
    } else {
        "unknown".to_owned()
    }
}

fn is_sentinel(game: EvidenceGameV1, metric_name: &str, value: f64) -> bool {
    match game {
        EvidenceGameV1::Hsr if metric_name == "avg_round" => value == 0.0 || value == 99.99,
        EvidenceGameV1::Hsr | EvidenceGameV1::Zzz => value == 0.0,
    }
}

fn metric_direction(mode: &str, metric_name: &str) -> &'static str {
    if matches!(metric_name, "avg_score" | "score")
        || (metric_name == "avg_round" && matches!(mode, "sd" | "da"))
    {
        "higher_better"
    } else if metric_name == "avg_round" {
        "lower_better"
    } else {
        "unknown"
    }
}

fn boss_key(row: &BTreeMap<String, String>) -> String {
    let mode = field(row, "mode");
    let sub_mode = field(row, "sub_mode").trim().to_ascii_lowercase();
    let scope = field(row, "scope")
        .replace("_combined.json", "")
        .replace(".json", "")
        .trim()
        .to_ascii_lowercase();
    let value = if sub_mode.is_empty() {
        &scope
    } else {
        &sub_mode
    };
    if matches!(value.as_str(), "" | "all" | "top" | "bangboo") || scope == "top" {
        String::new()
    } else {
        format!("{mode}:{value}")
    }
}

fn observation_key(row: &BTreeMap<String, String>) -> String {
    [
        field(row, "snapshot_id"),
        field(row, "mode"),
        field(row, "phase_ver"),
        field(row, "phase_name"),
        first_nonempty(row, &["scope", "sub_mode"]).unwrap_or_default(),
        field(row, "source_file"),
        field(row, "rank"),
    ]
    .iter()
    .map(|value| {
        if value.trim().is_empty() {
            "-"
        } else {
            value.trim()
        }
    })
    .collect::<Vec<_>>()
    .join(":")
}

fn stable_evidence_id(key: &str, mode: &str) -> String {
    let digest = format!("{:X}", Sha256::digest(key.as_bytes()));
    let label = mode
        .to_ascii_uppercase()
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character
            } else {
                '-'
            }
        })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("-");
    format!(
        "E-{}-{}",
        if label.is_empty() { "UNKNOWN" } else { &label },
        &digest[..10]
    )
}

fn full_team_signature(team: &[String], bangboo: &str) -> String {
    let mut parts = team.to_vec();
    if !bangboo.is_empty() {
        parts.push(format!("bangboo:{bangboo}"));
    }
    parts.join("|")
}

fn median(sorted: &[f64]) -> Option<f64> {
    match sorted.len() {
        0 => None,
        length if length % 2 == 1 => Some(sorted[length / 2]),
        length => Some((sorted[length / 2 - 1] + sorted[length / 2]) / 2.0),
    }
}

pub(crate) fn field<'a>(row: &'a BTreeMap<String, String>, key: &str) -> &'a str {
    row.get(key).map(String::as_str).unwrap_or_default()
}

fn first_nonempty<'a>(row: &'a BTreeMap<String, String>, keys: &[&str]) -> Option<&'a str> {
    keys.iter()
        .map(|key| field(row, key))
        .find(|value| !value.is_empty())
}

fn normalize_slug(value: &str) -> String {
    crate::normalize::character_slug(value)
}

pub(crate) fn canonical_slug(value: &str, names: &NameIndexV1) -> String {
    let slug = normalize_slug(value);
    names.aliases.get(&slug).cloned().unwrap_or(slug)
}

fn split_slugs(value: &str) -> Vec<String> {
    value
        .split([';', ','])
        .map(normalize_slug)
        .filter(|slug| !slug.is_empty())
        .collect()
}

fn parse_finite(value: &str) -> Option<f64> {
    let value = value.trim().trim_end_matches('%').trim();
    if matches!(value, "" | "-") {
        return None;
    }
    value.parse::<f64>().ok().filter(|value| value.is_finite())
}

fn parse_i64(value: &str) -> Option<i64> {
    let number = parse_finite(value)?;
    if number < i64::MIN as f64 || number > i64::MAX as f64 {
        None
    } else {
        Some(number.trunc() as i64)
    }
}

fn name_cn(slug: &str, names: &NameIndexV1) -> String {
    names
        .names_cn
        .get(slug)
        .cloned()
        .unwrap_or_else(|| slug.to_owned())
}

fn insert_nonempty(set: &mut BTreeSet<String>, value: String) {
    if !value.is_empty() {
        set.insert(value);
    }
}

pub(crate) fn push_unique(values: &mut Vec<String>, value: String) {
    if !value.is_empty() && !values.contains(&value) {
        values.push(value);
    }
}

fn none_if_empty(values: Vec<String>) -> Vec<String> {
    if values.is_empty() {
        vec!["none".to_owned()]
    } else {
        values
    }
}

fn append_comment(base: &mut String, addition: &str) {
    if base.is_empty() || base == "无" {
        *base = addition.to_owned();
    } else {
        base.push('；');
        base.push_str(addition);
    }
}

fn format_local_datetime(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S").to_string()
}

fn number_text(value: Option<f64>) -> String {
    match value {
        None => "-".to_owned(),
        Some(value) => python_general_number(value),
    }
}

pub(crate) fn python_general_number(value: f64) -> String {
    if value == 0.0 {
        return if value.is_sign_negative() {
            "-0".to_owned()
        } else {
            "0".to_owned()
        };
    }
    let scientific = format!("{value:.5e}");
    let (_, raw_exponent) = scientific
        .split_once('e')
        .expect("Rust scientific formatting always includes e");
    let exponent = raw_exponent.parse::<i32>().unwrap_or(0);
    if !(-4..6).contains(&exponent) {
        let (mantissa, exponent) = scientific
            .split_once('e')
            .expect("Rust scientific formatting always includes e");
        let mantissa = mantissa.trim_end_matches('0').trim_end_matches('.');
        let exponent_value = exponent.parse::<i32>().unwrap_or(0);
        return format!("{mantissa}e{exponent_value:+03}");
    }
    let decimals = (5 - exponent).max(0) as usize;
    let text = format!("{value:.decimals$}");
    text.trim_end_matches('0').trim_end_matches('.').to_owned()
}

pub const AGGREGATE_COLUMNS_V1: &[&str] = &[
    "mode",
    "mode_cn",
    "evidence_key",
    "team_signature",
    "agent_signature",
    "full_team_signature",
    "team_slugs",
    "team_cn",
    "bangboo_slug",
    "bangboo_name_cn",
    "confidence",
    "record_count",
    "duplicate_count",
    "snapshot_count",
    "phase_count",
    "mode_count",
    "scope_count",
    "boss_count",
    "source_kind_count",
    "max_app_rate",
    "median_app_rate",
    "best_rank",
    "best_score",
    "metric_name",
    "metric_direction",
    "non_sentinel_score_count",
    "sentinel_score_count",
    "valid_score_ratio",
    "modes",
    "phase_versions",
    "phase_names",
    "scopes",
    "source_kinds",
    "observation_keys",
    "stability_status",
    "evidence_comment",
    "risk_comment",
];

pub fn render_aggregate_csv_v1(aggregates: &[TeamSignatureAggregateV1]) -> EvidenceResult<Vec<u8>> {
    let mut bytes = vec![0xEF, 0xBB, 0xBF];
    {
        let mut writer = WriterBuilder::new().from_writer(&mut bytes);
        writer
            .write_record(AGGREGATE_COLUMNS_V1)
            .map_err(|source| EvidenceError::Csv {
                input: "aggregate output",
                source,
            })?;
        for aggregate in aggregates {
            writer
                .write_record(aggregate_csv_row(aggregate))
                .map_err(|source| EvidenceError::Csv {
                    input: "aggregate output",
                    source,
                })?;
        }
        writer.flush().map_err(|source| {
            EvidenceError::Invalid(format!("cannot flush aggregate CSV: {source}"))
        })?;
    }
    Ok(bytes)
}

fn aggregate_csv_row(value: &TeamSignatureAggregateV1) -> Vec<String> {
    vec![
        value.mode.clone(),
        value.mode_cn.clone(),
        value.evidence_key.clone(),
        value.team_signature.clone(),
        value.agent_signature.clone(),
        value.full_team_signature.clone(),
        value.team_slugs.join(", "),
        value.team_cn.join(" / "),
        value.bangboo_slug.clone(),
        value.bangboo_name_cn.clone(),
        value.confidence.as_str().to_owned(),
        value.record_count.to_string(),
        value.duplicate_count.to_string(),
        value.snapshot_count.to_string(),
        value.phase_count.to_string(),
        value.mode_count.to_string(),
        value.scope_count.to_string(),
        value.boss_count.to_string(),
        value.source_kind_count.to_string(),
        number_text(value.max_app_rate),
        number_text(value.median_app_rate),
        value
            .best_rank
            .map(|number| number.to_string())
            .unwrap_or_default(),
        number_text(value.best_score),
        value.metric_name.clone(),
        value.metric_direction.clone(),
        value.non_sentinel_score_count.to_string(),
        value.sentinel_score_count.to_string(),
        number_text(Some(value.valid_score_ratio)),
        value.modes.join(", "),
        value.phase_versions.join(", "),
        value.phase_names.join(", "),
        value.scopes.join(", "),
        value.source_kinds.join(", "),
        value.observation_keys.join("; "),
        value.stability_status.clone(),
        value.evidence_comment.clone(),
        value.risk_comment.clone(),
    ]
}

pub const COVERAGE_COLUMNS_V1: &[&str] = &[
    "evidence_id",
    "evidence_key",
    "scenario",
    "mode",
    "mode_cn",
    "source_confidence",
    "confidence",
    "team_signature",
    "agent_signature",
    "full_team_signature",
    "team_slugs",
    "team_cn",
    "bangboo_slug",
    "bangboo_name_cn",
    "bangboo_checked",
    "owned_count",
    "built_count",
    "build_checked",
    "unbuilt_parts",
    "plan_dependency",
    "missing_parts",
    "record_count",
    "duplicate_count",
    "snapshot_count",
    "phase_count",
    "scope_count",
    "boss_count",
    "source_kind_count",
    "max_app_rate",
    "median_app_rate",
    "best_rank",
    "best_score",
    "metric_name",
    "metric_direction",
    "non_sentinel_score_count",
    "sentinel_score_count",
    "valid_score_ratio",
    "phase_versions",
    "phase_names",
    "scopes",
    "source_kinds",
    "observation_keys",
    "stability_status",
    "evidence_comment",
    "risk_comment",
];

/// Render a deterministic report.  The timestamp comes only from the pool's
/// explicit context-derived summary.
pub fn render_coverage_markdown_v1(
    pool: &EvidencePoolV1,
    title: &str,
    team_source: &str,
    limit: usize,
) -> String {
    let mut output = String::new();
    let summary = &pool.summary;
    let quality = &summary.data_quality;
    writeln!(output, "# {title}\n").unwrap();
    writeln!(output, "- 生成时间：{}", summary.generated_at).unwrap();
    writeln!(output, "- 方法版本：`{}`", summary.method_version).unwrap();
    writeln!(output, "- scenario：`{}`", summary.scenario).unwrap();
    writeln!(output, "- 队伍数据源：`{team_source}`").unwrap();
    writeln!(
        output,
        "- team signature 聚合数：{}",
        summary.aggregate_count
    )
    .unwrap();
    writeln!(output, "- composition 数：{}", summary.composition_count).unwrap();
    writeln!(
        output,
        "- 当前拥有：{}；计划角色：{}；目标账号角色数：{}",
        summary.owned_count,
        if summary.planned.is_empty() {
            "none".to_owned()
        } else {
            summary.planned.join(", ")
        },
        summary.target_count
    )
    .unwrap();
    writeln!(
        output,
        "- 可组 team signature：{}",
        summary.included_records
    )
    .unwrap();
    writeln!(
        output,
        "- A 档 min_app_rate 阈值：{}",
        threshold_text(summary, &pool.records)
    )
    .unwrap();
    writeln!(
        output,
        "- Bangboo 拥有信息：{}",
        if summary.bangboo_ownership_known {
            "已读取"
        } else {
            "未提供，报告标记为邦布未校验"
        }
    )
    .unwrap();
    writeln!(
        output,
        "- Build 信息：{}",
        if summary.build_state_known {
            "已读取显式 built/builds"
        } else {
            "未提供，不从拥有或等级推断已可上场"
        }
    )
    .unwrap();
    writeln!(
        output,
        "- 模式分布：{}",
        sequence_count_text(pool.records.iter().map(|record| record.mode.clone()))
    )
    .unwrap();
    writeln!(output, "- 数据质量：原始 {} 行 / 纳入 {} 行；无效 app_rate {}；空队 {}；不完整队 {}；重复角色 {}。", quality.rows_total, quality.rows_included, quality.skipped_app_rate, quality.skipped_empty_team, quality.skipped_partial_team, quality.skipped_duplicate_agents).unwrap();
    writeln!(
        output,
        "- 表现质量：metric `{}`；missing/non-finite {}；sentinel {}。",
        if quality.metric_name.is_empty() {
            "none"
        } else {
            &quality.metric_name
        },
        quality.missing_or_non_finite_score_rows,
        quality.sentinel_score_rows
    )
    .unwrap();
    writeln!(
        output,
        "- Alias/稳定性目录：alias {}；stability role {}。",
        quality.alias_entries, quality.stability_catalog_entries
    )
    .unwrap();
    writeln!(
        output,
        "- 置信度分布：{}",
        sequence_count_text(
            pool.records
                .iter()
                .map(|record| record.confidence.as_str().to_owned())
        )
    )
    .unwrap();
    writeln!(
        output,
        "- 源证据置信度：{}",
        sequence_count_text(
            pool.records
                .iter()
                .map(|record| record.source_confidence.as_str().to_owned())
        )
    )
    .unwrap();
    writeln!(
        output,
        "- 计划依赖分布：{}\n",
        sequence_count_text(
            pool.records
                .iter()
                .map(|record| record.plan_dependency.join(","))
        )
    )
    .unwrap();
    writeln!(output, "## 置信度口径\n").unwrap();
    writeln!(
        output,
        "- A：单一 mode 内跨多期、多 Boss/范围且出场率较高，非 sentinel 分数充足并有明确稳定组件。"
    )
    .unwrap();
    writeln!(
        output,
        "- B+：重复度和出场率都较好，但广度或稳定性略弱于 A。"
    )
    .unwrap();
    writeln!(
        output,
        "- B：有真实记录和一定重复度，可证明可组与存在感，但不能直接推断长期 auto 稳定。"
    )
    .unwrap();
    writeln!(
        output,
        "- B-：真实记录稀疏、出场率低或 sentinel 较多，只能作为弱证据。"
    )
    .unwrap();
    writeln!(
        output,
        "- C：缺目标账号成员、无有效表现，或证据不足以支撑覆盖结论。\n"
    )
    .unwrap();
    writeln!(output, "## 数据口径\n").unwrap();
    writeln!(output, "- 先按无序三代理人 `agent_signature` 做账号覆盖，再按三代理人 + Bangboo 的 `full_team_signature` 聚合真实队伍证据。").unwrap();
    writeln!(output, "- planned 只作为 target scenario 的增量成员，不和 current_box 结论混写；target 表保留 `plan_dependency`。").unwrap();
    writeln!(output, "- `0`/缺失表现按 sentinel / missing 处理；`99.99` 只是 HSR `avg_round` sentinel，ZZZ 合法分数 `99.99` 仍是有效表现。").unwrap();
    writeln!(output, "- `metric_direction` 控制 best_score 取值方向；SD/DA 本地原始 JSON 的 `avg_round` 实为分数，按 `higher_better` 处理，但 SD/DA 分数仍不互相横比。").unwrap();
    writeln!(output, "- 同一 composition 在不同 mode 生成独立 `evidence_key=mode|full_team_signature`；分数、出场率与置信度均不跨模式合并。").unwrap();
    writeln!(
        output,
        "- A 需满足模式策略的重复度、非 sentinel 比例且有明确稳定组件；稳定性未知时最高 B+。"
    )
    .unwrap();
    writeln!(output, "- `source_confidence` 表示真实队伍数据强度；正式 `confidence` 再结合目标账号 build readiness，未提供或未培养会将源 A/B+ 降为 B。").unwrap();
    writeln!(output, "- Bangboo 写入 full evidence signature；只有 box 提供 Bangboo 拥有信息时才校验，否则标记 `邦布未校验`，不影响三代理人可组判断。\n").unwrap();
    writeln!(output, "## 覆盖记录\n").unwrap();
    markdown_row(&mut output, COVERAGE_COLUMNS_V1.iter().copied());
    markdown_row(
        &mut output,
        std::iter::repeat_n("---", COVERAGE_COLUMNS_V1.len()),
    );
    let take = if limit == 0 {
        pool.records.len()
    } else {
        limit.min(pool.records.len())
    };
    if take == 0 {
        let mut empty = vec!["-".to_owned(); COVERAGE_COLUMNS_V1.len()];
        for column in [
            "owned_count",
            "built_count",
            "record_count",
            "duplicate_count",
            "snapshot_count",
            "phase_count",
            "scope_count",
            "boss_count",
            "source_kind_count",
            "non_sentinel_score_count",
            "sentinel_score_count",
        ] {
            let index = COVERAGE_COLUMNS_V1
                .iter()
                .position(|candidate| *candidate == column)
                .expect("empty report numeric column must exist");
            empty[index] = "0".to_owned();
        }
        empty[COVERAGE_COLUMNS_V1
            .iter()
            .position(|column| *column == "evidence_comment")
            .unwrap()] = "无可组真实队伍记录".to_owned();
        empty[COVERAGE_COLUMNS_V1
            .iter()
            .position(|column| *column == "risk_comment")
            .unwrap()] = "检查 box、计划角色或数据源".to_owned();
        markdown_row(&mut output, empty.iter().map(String::as_str));
    } else {
        for record in pool.records.iter().take(take) {
            markdown_row(
                &mut output,
                coverage_markdown_row(record).iter().map(String::as_str),
            );
        }
    }
    output
}

fn sequence_count_text(values: impl Iterator<Item = String>) -> String {
    let mut counts: Vec<(String, usize)> = Vec::new();
    for value in values.filter(|value| !value.is_empty()) {
        if let Some((_, count)) = counts.iter_mut().find(|(key, _)| *key == value) {
            *count += 1;
        } else {
            counts.push((value, 1));
        }
    }
    if counts.is_empty() {
        "-".to_owned()
    } else {
        counts
            .into_iter()
            .map(|(key, count)| format!("{key} {count}"))
            .collect::<Vec<_>>()
            .join(" / ")
    }
}

fn threshold_text(summary: &EvidenceSummaryV1, records: &[EvidenceRecordV1]) -> String {
    if summary.min_a_app_rate_by_mode.is_empty() {
        return number_text(Some(summary.default_min_a_app_rate));
    }
    let mut modes = Vec::new();
    for record in records {
        if summary.min_a_app_rate_by_mode.contains_key(&record.mode)
            && !modes.contains(&record.mode)
        {
            modes.push(record.mode.clone());
        }
    }
    for mode in summary.min_a_app_rate_by_mode.keys() {
        if !modes.contains(mode) {
            modes.push(mode.clone());
        }
    }
    modes
        .into_iter()
        .map(|mode| {
            format!(
                "{mode}:{}",
                number_text(summary.min_a_app_rate_by_mode.get(&mode).copied())
            )
        })
        .collect::<Vec<_>>()
        .join(", ")
}

fn markdown_row<'a>(output: &mut String, values: impl Iterator<Item = &'a str>) {
    output.push_str("| ");
    output.push_str(&values.map(markdown_escape).collect::<Vec<_>>().join(" | "));
    output.push_str(" |\n");
}

fn markdown_escape(value: &str) -> String {
    value.replace('|', "\\|").replace(['\r', '\n'], " ")
}

fn coverage_markdown_row(value: &EvidenceRecordV1) -> Vec<String> {
    vec![
        value.evidence_id.clone(),
        value.evidence_key.clone(),
        value.scenario.clone(),
        value.mode.clone(),
        value.mode_cn.clone(),
        value.source_confidence.as_str().to_owned(),
        value.confidence.as_str().to_owned(),
        value.team_signature.clone(),
        value.agent_signature.clone(),
        value.full_team_signature.clone(),
        value.team_slugs.join(", "),
        value.team_cn.join(" / "),
        value.bangboo_slug.clone(),
        value.bangboo_name_cn.clone(),
        value.bangboo_checked.clone(),
        value.owned_count.to_string(),
        value.built_count.to_string(),
        value.build_checked.clone(),
        value.unbuilt_parts.join(", "),
        value.plan_dependency.join(", "),
        value.missing_parts.join(", "),
        value.record_count.to_string(),
        value.duplicate_count.to_string(),
        value.snapshot_count.to_string(),
        value.phase_count.to_string(),
        value.scope_count.to_string(),
        value.boss_count.to_string(),
        value.source_kind_count.to_string(),
        number_text(value.max_app_rate),
        number_text(value.median_app_rate),
        value
            .best_rank
            .map(|v| v.to_string())
            .unwrap_or_else(|| "-".to_owned()),
        number_text(value.best_score),
        value.metric_name.clone(),
        value.metric_direction.clone(),
        value.non_sentinel_score_count.to_string(),
        value.sentinel_score_count.to_string(),
        number_text(Some(value.valid_score_ratio)),
        value.phase_versions.join(", "),
        value.phase_names.join(", "),
        value.scopes.join(", "),
        value.source_kinds.join(", "),
        value.observation_keys.join("; "),
        value.stability_status.clone(),
        value.evidence_comment.clone(),
        value.risk_comment.clone(),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;

    fn context() -> EvidenceContextV1 {
        EvidenceContextV1 {
            local_datetime: NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        }
    }

    fn zzz_inputs(rows: &str) -> EvidenceInputsV1 {
        EvidenceInputsV1 {
            team_rank_dedup_unordered_csv: format!("mode,mode_cn,phase_ver,scope,snapshot_id,app_rate,avg_score,rank,duplicate_count,char_1_slug,char_2_slug,char_3_slug,bangboo_slug,source_kind,source_file\n{rows}").into_bytes(),
            name_map_csv: Some(b"character_slug,character_name_cn,aliases,kind\na,\xE7\x94\xB2,alias-a,agent\nb,\xE4\xB9\x99,,agent\nc,\xE4\xB8\x99,,agent\nboo,\xE9\x82\xA6\xE5\xB8\x83,,bangboo\n".to_vec()),
            tier_csv: Some(b"character_slug,style_cn\na,\xE6\x94\xAF\xE6\x8F\xB4\nb,\xE5\xBC\xBA\xE6\x94\xBB\nc,\xE5\xBC\xBA\xE6\x94\xBB\n".to_vec()),
            box_json: br#"{"owned":["alias-a","b","c"],"builds":{"a":true,"b":true,"c":true}}"#.to_vec(),
            banner_plan_json: None,
        }
    }

    #[test]
    fn mode_scoped_key_and_zzz_99_99_is_not_sentinel() {
        let inputs = zzz_inputs("sd,SD,1,all,s1,12,99.99,1,1,a,b,c,boo,hf,x\nda,DA,1,all,s2,12,99.99,1,1,a,b,c,boo,hf,y\n");
        let bundle =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        assert_eq!(bundle.target.aggregates.len(), 2);
        assert_ne!(
            bundle.target.aggregates[0].evidence_key,
            bundle.target.aggregates[1].evidence_key
        );
        assert!(bundle
            .target
            .aggregates
            .iter()
            .all(|row| row.non_sentinel_score_count == 1));
    }

    #[test]
    fn stable_id_does_not_change_when_unrelated_plan_is_added() {
        let inputs = zzz_inputs("sd,SD,1,all,s1,12,30000,1,1,a,b,c,,hf,x\n");
        let first =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        let request = EvidenceRequestV1 {
            explicit_planned_slugs: vec!["unrelated".to_owned()],
            ..Default::default()
        };
        let second = build_evidence_bundle_v1(&inputs, &request, &context()).unwrap();
        assert_eq!(
            first.target.records[0].evidence_id,
            second.target.records[0].evidence_id
        );
    }

    #[test]
    fn alias_collision_is_fatal() {
        let mut inputs = zzz_inputs("sd,SD,1,all,s1,12,30000,1,1,a,b,c,,hf,x\n");
        inputs.name_map_csv = Some(b"character_slug,aliases\na,shared\nb,shared\n".to_vec());
        assert!(
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context())
                .unwrap_err()
                .to_string()
                .contains("alias conflict")
        );
    }

    #[test]
    fn partial_and_duplicate_teams_are_quality_failures() {
        let inputs = zzz_inputs(
            "sd,SD,1,all,s1,12,30000,1,1,a,b,,,hf,x\nsd,SD,1,all,s2,12,30000,1,1,a,a,c,,hf,y\n",
        );
        let bundle =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        assert_eq!(bundle.target.summary.data_quality.skipped_partial_team, 1);
        assert_eq!(
            bundle.target.summary.data_quality.skipped_duplicate_agents,
            1
        );
        assert!(bundle.target.aggregates.is_empty());
    }

    #[test]
    fn non_finite_app_rate_is_skipped_and_score_is_missing() {
        let inputs = zzz_inputs("sd,SD,1,all,s1,NaN,30000,1,1,a,b,c,,hf,x\nsd,SD,1,all,s2,12,Infinity,1,1,a,b,c,,hf,y\n");
        let bundle =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        assert_eq!(bundle.target.summary.data_quality.skipped_app_rate, 1);
        assert_eq!(bundle.target.aggregates[0].sentinel_score_count, 1);
        assert_eq!(
            bundle.target.aggregates[0].confidence,
            EvidenceConfidenceV1::C
        );
    }

    #[test]
    fn build_unknown_caps_source_b_plus_or_a_at_account_b() {
        let mut rows = String::new();
        for phase in 1..=4 {
            for copy in 0..3 {
                writeln!(
                    rows,
                    "sd,SD,{phase},boss-{phase},s-{phase}-{copy},12,30000,1,1,a,b,c,,hf,x"
                )
                .unwrap();
            }
        }
        let mut inputs = zzz_inputs(&rows);
        inputs.box_json = br#"{"owned":["a","b","c"]}"#.to_vec();
        let bundle =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        assert_eq!(
            bundle.target.records[0].source_confidence,
            EvidenceConfidenceV1::A
        );
        assert_eq!(bundle.target.records[0].confidence, EvidenceConfidenceV1::B);
    }

    #[test]
    fn hsr_sentinel_and_stability_markers_are_game_specific() {
        let inputs = EvidenceInputsV1 {
            team_rank_dedup_unordered_csv: b"mode,phase_ver,scope,snapshot_id,app_rate,avg_round,char_1_slug,char_2_slug,char_3_slug,char_4_slug\nmoc,1,all,s1,12,99.99,a,b,c,d\n".to_vec(),
            name_map_csv: None,
            tier_csv: Some(b"character_slug,path_cn\na,\xE5\xAD\x98\xE6\x8A\xA4\nb,\xE5\xB7\xA1\xE7\x8C\x8E\nc,\xE5\xB7\xA1\xE7\x8C\x8E\nd,\xE5\xB7\xA1\xE7\x8C\x8E\n".to_vec()),
            box_json: br#"{"owned":["a","b","c","d"],"builds":{"a":true,"b":true,"c":true,"d":true}}"#.to_vec(),
            banner_plan_json: None,
        };
        let request = EvidenceRequestV1 {
            game: EvidenceGameV1::Hsr,
            ..Default::default()
        };
        let bundle = build_evidence_bundle_v1(&inputs, &request, &context()).unwrap();
        assert_eq!(bundle.target.aggregates[0].sentinel_score_count, 1);
        assert_eq!(bundle.target.aggregates[0].stability_status, "present");
    }

    #[test]
    fn explicit_clock_drives_plan_boundary_and_aliases() {
        let mut inputs = zzz_inputs("sd,SD,1,all,s1,12,30000,1,1,a,b,c,,hf,x\n");
        inputs.banner_plan_json = Some(br#"{"phases":[{"status":"current","date_range":"2026-07-13 - 2026-07-20","characters":[{"slug":"alias-a"}]}]}"#.to_vec());
        let bundle =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        assert_eq!(bundle.planned_slugs, ["a"]);
    }

    #[test]
    fn renderers_are_stable_and_escape_markdown() {
        let mut inputs = zzz_inputs("sd,SD,1,all,s1,12,30000,1,1,a,b,c,,hf,file|x\n");
        inputs.name_map_csv = Some(b"character_slug,character_name_cn\na,A|B\nb,B\nc,C\n".to_vec());
        inputs.box_json = br#"{"owned":["a","b","c"]}"#.to_vec();
        let bundle =
            build_evidence_bundle_v1(&inputs, &EvidenceRequestV1::default(), &context()).unwrap();
        let csv = render_aggregate_csv_v1(&bundle.target.aggregates).unwrap();
        assert!(csv.starts_with(&[0xEF, 0xBB, 0xBF]));
        let md = render_coverage_markdown_v1(&bundle.target, "T", "fixture.csv", 0);
        assert!(md.contains("A\\|B"));
        assert!(md.contains("2026-07-12T13:00:00"));
    }

    #[test]
    fn number_text_matches_python_general_format_boundaries() {
        assert_eq!(number_text(Some(-0.0)), "-0");
        assert_eq!(number_text(Some(5.0 / 6.0)), "0.833333");
        assert_eq!(number_text(Some(999_999.9)), "1e+06");
        assert_eq!(number_text(Some(0.000_01)), "1e-05");
        assert_eq!(number_text(Some(0.000_1)), "0.0001");
    }

    #[test]
    fn yaml_config_matches_pyyaml_booleans_merges_empty_docs_and_non_finite_rejection() {
        let value = parse_config(
            b"defaults: &defaults\n  owned: off\nagent:\n  <<: *defaults\n",
            "yaml fixture",
        )
        .unwrap();
        assert_eq!(value["agent"]["owned"], Value::Bool(false));
        assert_eq!(
            parse_config(b"", "empty yaml").unwrap(),
            Value::Object(Default::default())
        );
        assert!(parse_config(b"value: .nan\n", "nan yaml").is_err());
        assert!(parse_config(b"value: 1.0E+400\n", "overflow yaml").is_err());
        assert_eq!(
            parse_config(b"value: 1e400\n", "string yaml").unwrap()["value"],
            Value::String("1e400".to_owned())
        );
    }
}
