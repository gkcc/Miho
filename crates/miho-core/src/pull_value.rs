//! Evidence-first V1 pull-value cards and Markdown renderer.
//!
//! This core owns no path discovery or clock access. A trusted adapter supplies
//! all bytes, display labels, and one explicit local datetime.

use std::collections::{BTreeMap, BTreeSet};

use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::evidence::{
    build_evidence_bundle_v1, canonical_slug, field, parse_account, parse_config, parse_csv,
    parse_name_index, push_unique, python_general_number, AccountStateV1, EvidenceConfidenceV1,
    EvidenceContextV1, EvidenceError, EvidenceGameV1, EvidenceInputsV1, EvidenceRecordV1,
    EvidenceRequestV1, NameIndexV1, EVIDENCE_METHOD_VERSION,
};
use crate::normalize::{character_slug, parse_percent};
use crate::visualizer::{effective_banner_status, python_json_number_repr, python_value_truthy};

pub const PULL_VALUE_METHOD_VERSION: &str = EVIDENCE_METHOD_VERSION;

pub const NEW_EVIDENCE_CATEGORIES_V1: &[&str] = &[
    "新一期 SD/DA 出场率显著变化",
    "新队伍 coverage 从 B-/C 提升到 A/B+",
    "专武/影画机制 notes 更新",
    "主流指南共识变化",
    "当前 Box 变化",
    "用户目标或预算变化",
];

#[derive(Debug, thiserror::Error)]
pub enum PullValueError {
    #[error(transparent)]
    Evidence(#[from] EvidenceError),
    #[error("invalid pull-value input: {0}")]
    Invalid(String),
    #[error("cannot serialize pull-value output: {0}")]
    Json(#[from] serde_json::Error),
}

pub type PullValueResult<T> = Result<T, PullValueError>;
type CandidateMap = Map<String, Value>;
type CandidateList = Vec<CandidateMap>;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PullValueInputsV1 {
    pub evidence: EvidenceInputsV1,
    #[serde(default)]
    pub usage_csv: Option<Vec<u8>>,
    /// Final filename-stem to config bytes mapping. The trusted adapter applies
    /// Python's yaml -> yml -> json overwrite precedence before entering core.
    #[serde(default)]
    pub mechanism_notes: BTreeMap<String, Vec<u8>>,
    #[serde(default)]
    pub decision_baseline: Option<Vec<u8>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PullValueRequestV1 {
    #[serde(default = "method_version")]
    pub method_version: String,
    #[serde(default)]
    pub explicit_planned_slugs: Vec<String>,
    #[serde(default = "default_statuses")]
    pub plan_statuses: Vec<String>,
}

impl Default for PullValueRequestV1 {
    fn default() -> Self {
        Self {
            method_version: method_version(),
            explicit_planned_slugs: Vec::new(),
            plan_statuses: default_statuses(),
        }
    }
}

fn method_version() -> String {
    PULL_VALUE_METHOD_VERSION.to_owned()
}

fn default_statuses() -> Vec<String> {
    vec!["next".to_owned()]
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PullValueContextV1 {
    pub local_datetime: NaiveDateTime,
    pub data_dir: String,
    pub box_path: String,
    pub plan_path: String,
    pub mechanism_notes_dir: String,
    pub decision_baseline_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StageRecommendationV1 {
    pub recommended_stage: String,
    pub acceptable_stage: String,
    pub unresolved_stage: String,
    pub stage_confidence: String,
    pub not_recommended_stage: String,
    pub reason: String,
    pub missing_data: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PullEvidenceRefV1 {
    pub evidence_id: String,
    pub evidence_key: String,
    pub confidence: String,
    pub source_confidence: String,
    pub mode: String,
    pub team_slugs: Vec<String>,
    pub plan_dependency: Vec<String>,
    pub phase_versions: Vec<String>,
    pub scopes: Vec<String>,
    pub observation_keys: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PullValueCardV1 {
    pub slug: String,
    pub name_cn: String,
    pub candidate_type: String,
    pub status: String,
    pub pull_value: String,
    pub stage_recommendation: StageRecommendationV1,
    pub prior_final_stage: String,
    pub prior_decision_status: String,
    pub prior_confidence: String,
    pub prior_reason: String,
    pub local_rule_stage: String,
    pub recommended_stage_for_review: String,
    pub final_stage: String,
    pub stage_delta: String,
    pub delta_requires_review: bool,
    pub delta_reason: String,
    pub change_allowed_reason: String,
    pub new_evidence_categories: Vec<String>,
    pub history_summary: String,
    pub global_usage_summary: String,
    pub team_coverage_summary: String,
    pub mechanism_review_summary: String,
    pub mechanism_notes: Value,
    pub mechanism_summary: String,
    pub replacement_risk: String,
    pub decision_basis: Vec<String>,
    pub risk_notes: Vec<String>,
    pub evidence_ids: Vec<String>,
    pub risk_evidence_ids: Vec<String>,
    pub evidence_keys: Vec<String>,
    pub risk_evidence_keys: Vec<String>,
    pub evidence_refs: Vec<PullEvidenceRefV1>,
    pub risk_evidence_refs: Vec<PullEvidenceRefV1>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PullValueSummaryV1 {
    pub method_version: String,
    pub generated_at: String,
    pub data_dir: String,
    pub box_path: String,
    pub plan_path: String,
    pub candidate_count: usize,
    pub planned_slugs: Vec<String>,
    pub reviewed_slugs: Vec<String>,
    pub filtered_low_rarity_slugs: Vec<String>,
    pub current_coverage_records: usize,
    pub target_coverage_records: usize,
    pub mechanism_notes_dir: String,
    pub decision_baseline_path: String,
    pub decision_baseline_slugs: Vec<String>,
    pub new_evidence_categories: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PullValueBundleV1 {
    pub summary: PullValueSummaryV1,
    pub cards: Vec<PullValueCardV1>,
}

#[derive(Debug, Clone, Default)]
struct UsageMode {
    points: usize,
    latest: f64,
    avg_last3: f64,
    trend_delta: f64,
}

#[derive(Debug, Clone, Default)]
struct UsageSummary {
    points: usize,
    modes: BTreeMap<String, UsageMode>,
    mode_order: Vec<String>,
    best_avg_last3: f64,
    best_latest: f64,
    worst_trend_delta: f64,
}

#[derive(Debug, Clone, Default)]
struct UsageIndex {
    summaries: BTreeMap<String, UsageSummary>,
    raw_slugs: BTreeSet<String>,
}

#[derive(Debug, Clone, Default)]
struct TierMeta {
    best_rating: f64,
    best_tier: String,
    values: BTreeMap<String, String>,
    by_mode: BTreeMap<String, BTreeMap<String, String>>,
}

#[derive(Debug, Clone, Default)]
struct BaselineEntry {
    values: Map<String, Value>,
}

#[derive(Debug, Clone)]
struct BaselineFields {
    prior_final_stage: String,
    prior_decision_status: String,
    prior_confidence: String,
    prior_reason: String,
    local_rule_stage: String,
    recommended_stage_for_review: String,
    final_stage: String,
    stage_delta: String,
    delta_requires_review: bool,
    delta_reason: String,
    change_allowed_reason: String,
    new_evidence_categories: Vec<String>,
}

pub fn build_pull_value_bundle_v1(
    inputs: &PullValueInputsV1,
    request: &PullValueRequestV1,
    context: &PullValueContextV1,
) -> PullValueResult<PullValueBundleV1> {
    if request.method_version != PULL_VALUE_METHOD_VERSION {
        return Err(PullValueError::Invalid(format!(
            "unsupported pull-value method: {}",
            request.method_version
        )));
    }
    let names = parse_name_index(inputs.evidence.name_map_csv.as_deref())?;
    let account = parse_account(&inputs.evidence.box_json, &names)?;
    let mut candidates = load_candidates(
        inputs.evidence.banner_plan_json.as_deref(),
        &request.plan_statuses,
        context.local_datetime,
        &names,
    )?;
    let explicit = request
        .explicit_planned_slugs
        .iter()
        .map(|slug| canonical_slug(slug, &names))
        .filter(|slug| !slug.is_empty())
        .collect::<Vec<_>>();
    for slug in &explicit {
        if !candidates
            .iter()
            .any(|candidate| candidate_slug(candidate) == *slug)
        {
            candidates.push(Map::from_iter([
                ("slug".to_owned(), Value::String(slug.clone())),
                ("status".to_owned(), Value::String("planned".to_owned())),
                ("analysis_tags".to_owned(), Value::Array(Vec::new())),
                (
                    "banner_role".to_owned(),
                    Value::String("planned".to_owned()),
                ),
            ]));
        }
    }
    let mut planned = Vec::new();
    for candidate in &candidates {
        push_unique(&mut planned, candidate_slug(candidate));
    }
    for slug in explicit {
        push_unique(&mut planned, slug);
    }

    // Pull-value owns candidate order. Avoid Evidence V1's explicit-first plan
    // order by supplying the already-resolved list as the sole planned input.
    let mut evidence_inputs = inputs.evidence.clone();
    evidence_inputs.banner_plan_json = None;
    let evidence = build_evidence_bundle_v1(
        &evidence_inputs,
        &EvidenceRequestV1 {
            game: EvidenceGameV1::Zzz,
            explicit_planned_slugs: planned.clone(),
            ..EvidenceRequestV1::default()
        },
        &EvidenceContextV1 {
            local_datetime: context.local_datetime,
        },
    )?;

    let usage = parse_usage(inputs.usage_csv.as_deref())?;
    let tiers = parse_tiers(inputs.evidence.tier_csv.as_deref())?;
    let (review_candidates, filtered_candidates) = filter_review_candidates(candidates, &tiers);
    let mechanisms = parse_mechanism_notes(&inputs.mechanism_notes, &review_candidates)?;
    let baseline = parse_baseline(inputs.decision_baseline.as_deref(), &names)?;
    let mut cards = review_candidates
        .iter()
        .map(|candidate| {
            build_card(
                candidate,
                &names,
                &account,
                &evidence.current.records,
                &evidence.target.records,
                &usage,
                &tiers,
                &mechanisms,
                &baseline,
            )
        })
        .collect::<PullValueResult<Vec<_>>>()?;
    cards.sort_by(|left, right| {
        value_sort_key(&left.pull_value)
            .cmp(&value_sort_key(&right.pull_value))
            .then_with(|| left.slug.cmp(&right.slug))
    });
    let mut baseline_slugs = baseline.keys().cloned().collect::<Vec<_>>();
    baseline_slugs.sort();
    Ok(PullValueBundleV1 {
        summary: PullValueSummaryV1 {
            method_version: PULL_VALUE_METHOD_VERSION.to_owned(),
            generated_at: context
                .local_datetime
                .format("%Y-%m-%dT%H:%M:%S")
                .to_string(),
            data_dir: context.data_dir.clone(),
            box_path: context.box_path.clone(),
            plan_path: context.plan_path.clone(),
            candidate_count: cards.len(),
            planned_slugs: planned,
            reviewed_slugs: review_candidates.iter().map(candidate_slug).collect(),
            filtered_low_rarity_slugs: filtered_candidates.iter().map(candidate_slug).collect(),
            current_coverage_records: evidence.current.records.len(),
            target_coverage_records: evidence.target.records.len(),
            mechanism_notes_dir: context.mechanism_notes_dir.clone(),
            decision_baseline_path: context.decision_baseline_path.clone(),
            decision_baseline_slugs: baseline_slugs,
            new_evidence_categories: NEW_EVIDENCE_CATEGORIES_V1
                .iter()
                .map(|value| (*value).to_owned())
                .collect(),
        },
        cards,
    })
}

pub fn render_pull_value_json_v1(bundle: &PullValueBundleV1) -> PullValueResult<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(bundle)?;
    bytes.push(b'\n');
    Ok(bytes)
}

pub fn render_pull_value_markdown_v1(bundle: &PullValueBundleV1) -> String {
    let summary = &bundle.summary;
    let mut lines = vec![
        "# 绝区零 Pull Value Report".to_owned(),
        String::new(),
        format!("- 方法版本：{}", summary.method_version),
        format!("- 生成时间：{}", summary.generated_at),
        format!("- 数据目录：`{}`", summary.data_dir),
        format!("- Box：`{}`", summary.box_path),
        format!(
            "- 卡池计划：`{}`",
            if summary.plan_path.is_empty() {
                "-"
            } else {
                &summary.plan_path
            }
        ),
        format!(
            "- 机制笔记：`{}`",
            if summary.mechanism_notes_dir.is_empty() {
                "-"
            } else {
                &summary.mechanism_notes_dir
            }
        ),
        format!(
            "- 定档 baseline：`{}`；已有基线：{}",
            if summary.decision_baseline_path.is_empty() {
                "-"
            } else {
                &summary.decision_baseline_path
            },
            if summary.decision_baseline_slugs.is_empty() {
                "none".to_owned()
            } else {
                summary.decision_baseline_slugs.join(", ")
            }
        ),
        format!(
            "- 候选角色：{}；planned_slugs：{}",
            summary.candidate_count,
            if summary.planned_slugs.is_empty() {
                "none".to_owned()
            } else {
                summary.planned_slugs.join(", ")
            }
        ),
        format!(
            "- current coverage records：{}；target coverage records：{}",
            summary.current_coverage_records, summary.target_coverage_records
        ),
        String::new(),
        "## 口径".to_owned(),
        String::new(),
        "- 复刻角色：按历史走势、全局出场、队伍覆盖、T 榜定位和 X+X 档位必要性评估。".to_owned(),
        "- 新角色：按机制信息完整度、拼图关系、售后确定性和替代风险评估；没有历史队伍记录是未实测状态，不作为负面扣分。".to_owned(),
        "- A 级 / 四星角色默认不作为独立抽取价值候选；只作为陪跑顺带收益、队友或 coverage 证据保留。".to_owned(),
        "- target coverage 只说明加入计划角色后的队伍覆盖，不单独决定抽取价值。".to_owned(),
        "- mechanism_review 来自 `configs/zzz_mechanism_notes/*.yaml`，用于判断 0+0、0+1、1+0、1+1、2+1 等档位断点。".to_owned(),
        "- 若存在 decision baseline，最终档位沿用 prior_final_stage；本地规则只作为 delta review 输入，不能在无新增证据时覆盖既有 GPT/人工定档。".to_owned(),
        "- 队伍证据只引用 A / B+ / B / B- 聚合记录；C 只作为风险。".to_owned(),
        "- 未拥有候选的主证据只接受 `plan_dependency == [candidate]`；同时依赖其他计划角色的队伍进入 conditional risk。".to_owned(),
        String::new(),
        "## 总览".to_owned(),
        String::new(),
        "| character | type | pull_value | prior_final_stage | local_rule_stage | final_stage | stage_delta | delta_requires_review | change_allowed_reason | acceptable_stage | unresolved_stage | stage_confidence | not_recommended_stage | missing_data | evidence_ids | evidence_keys | risk_evidence_ids | risk_evidence_keys | key_basis | risk |".to_owned(),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|".to_owned(),
    ];
    for card in &bundle.cards {
        let stage = &card.stage_recommendation;
        lines.push(format!(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            markdown(&format!("{} `{}`", card.name_cn, card.slug)),
            markdown(&card.candidate_type),
            markdown(&card.pull_value),
            markdown(or_hyphen(&card.prior_final_stage)),
            markdown(or_hyphen(&card.local_rule_stage)),
            markdown(or_hyphen(&card.final_stage)),
            markdown(or_hyphen(&card.stage_delta)),
            if card.delta_requires_review { "yes" } else { "no" },
            markdown(or_hyphen(&card.change_allowed_reason)),
            markdown(&stage.acceptable_stage),
            markdown(&stage.unresolved_stage),
            markdown(&stage.stage_confidence),
            markdown(&stage.not_recommended_stage),
            markdown(&stage.missing_data),
            markdown(&join_or_hyphen(&card.evidence_ids, ", ")),
            markdown(&join_or_hyphen(&card.evidence_keys, ", ")),
            markdown(&join_or_hyphen(&card.risk_evidence_ids, ", ")),
            markdown(&join_or_hyphen(&card.risk_evidence_keys, ", ")),
            markdown(&join_first_or_hyphen(&card.decision_basis, 3, "；")),
            markdown(&join_first_or(&card.risk_notes, 3, "；", "无")),
        ));
    }
    lines.extend([String::new(), "## 角色明细".to_owned(), String::new()]);
    for card in &bundle.cards {
        append_card_lines(&mut lines, card);
    }
    lines.extend([
        "## 本地 GPT 评判接入状态".to_owned(),
        String::new(),
        "- 当前报告由本地确定性规则生成，可离线复现。".to_owned(),
        "- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。".to_owned(),
        "- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。".to_owned(),
        String::new(),
    ]);
    lines.join("\n")
}

fn append_card_lines(lines: &mut Vec<String>, card: &PullValueCardV1) {
    let stage = &card.stage_recommendation;
    lines.extend([
        format!("### {} `{}`：{}", card.name_cn, card.slug, card.pull_value),
        String::new(),
        format!(
            "- 类型：{}；状态：{}",
            card.candidate_type,
            or_hyphen(&card.status)
        ),
        format!(
            "- prior_final_stage：{}",
            or_hyphen(&card.prior_final_stage)
        ),
        format!(
            "- prior_decision_status：{}；prior_confidence：{}",
            or_hyphen(&card.prior_decision_status),
            or_hyphen(&card.prior_confidence)
        ),
        format!("- prior_reason：{}", or_hyphen(&card.prior_reason)),
        format!("- local_rule_stage：{}", or_hyphen(&card.local_rule_stage)),
        format!(
            "- recommended_stage_for_review：{}",
            or_hyphen(&card.recommended_stage_for_review)
        ),
        format!("- final_stage：{}", or_hyphen(&card.final_stage)),
        format!(
            "- stage_delta：{}；delta_requires_review：{}",
            or_hyphen(&card.stage_delta),
            if card.delta_requires_review {
                "yes"
            } else {
                "no"
            }
        ),
        format!("- delta_reason：{}", or_hyphen(&card.delta_reason)),
        format!(
            "- change_allowed_reason：{}",
            or_hyphen(&card.change_allowed_reason)
        ),
        format!(
            "- new_evidence_categories：{}",
            join_or_hyphen(&card.new_evidence_categories, ", ")
        ),
        format!(
            "- recommended_stage(local_rule)：{}",
            stage.recommended_stage
        ),
        format!("- acceptable_stage：{}", stage.acceptable_stage),
        format!("- unresolved_stage：{}", stage.unresolved_stage),
        format!("- stage_confidence：{}", stage.stage_confidence),
        format!("- not_recommended_stage：{}", stage.not_recommended_stage),
        format!("- stage_reason：{}", stage.reason),
        format!("- missing_data：{}", stage.missing_data),
        format!("- source_quality：{}", {
            let text = source_quality_text(card.mechanism_notes.get("source_quality"));
            if text.is_empty() {
                "-".to_owned()
            } else {
                text
            }
        }),
        format!("- stage_notes：{}", {
            let text = stage_notes_text(card.mechanism_notes.get("stage_notes"));
            if text.is_empty() {
                "-".to_owned()
            } else {
                text
            }
        }),
        format!("- 历史走势：{}", card.history_summary),
        format!("- 全局出场：{}", card.global_usage_summary),
        format!("- 队伍覆盖：{}", card.team_coverage_summary),
        format!("- mechanism_review：{}", card.mechanism_review_summary),
        format!("- 机制/拼图：{}", card.mechanism_summary),
        format!("- 替代风险：{}", card.replacement_risk),
        format!("- 证据：{}", join_or_hyphen(&card.evidence_ids, ", ")),
        format!(
            "- 稳定证据键：{}",
            join_or_hyphen(&card.evidence_keys, ", ")
        ),
        format!(
            "- 风险/条件证据（conditional 或 B-/C）：{}",
            join_or_hyphen(&card.risk_evidence_ids, ", ")
        ),
        format!(
            "- 风险证据键：{}",
            join_or_hyphen(&card.risk_evidence_keys, ", ")
        ),
        format!(
            "- 依据：{}",
            if card.decision_basis.is_empty() {
                "-".to_owned()
            } else {
                card.decision_basis.join("；")
            }
        ),
        format!(
            "- 风险：{}",
            if card.risk_notes.is_empty() {
                "无".to_owned()
            } else {
                card.risk_notes.join("；")
            }
        ),
        String::new(),
    ]);
}

fn markdown(value: &str) -> String {
    value.replace('|', "\\|").replace('\n', " ")
}

fn or_hyphen(value: &str) -> &str {
    if value.is_empty() {
        "-"
    } else {
        value
    }
}

fn join_or_hyphen(values: &[String], separator: &str) -> String {
    if values.is_empty() {
        "-".to_owned()
    } else {
        values.join(separator)
    }
}

fn join_first_or_hyphen(values: &[String], limit: usize, separator: &str) -> String {
    join_first_or(values, limit, separator, "-")
}

fn join_first_or(values: &[String], limit: usize, separator: &str, empty: &str) -> String {
    if values.is_empty() {
        empty.to_owned()
    } else {
        values
            .iter()
            .take(limit)
            .cloned()
            .collect::<Vec<_>>()
            .join(separator)
    }
}

fn load_candidates(
    bytes: Option<&[u8]>,
    statuses: &[String],
    local_datetime: NaiveDateTime,
    names: &NameIndexV1,
) -> PullValueResult<Vec<Map<String, Value>>> {
    let Some(bytes) = bytes else {
        return Ok(Vec::new());
    };
    let value = parse_config(bytes, "pull banner plan")?;
    validate_finite(&value, "pull banner plan")?;
    let object = value
        .as_object()
        .ok_or_else(|| PullValueError::Invalid("banner plan root must be an object".to_owned()))?;
    let status_set = statuses
        .iter()
        .map(|status| status.trim().to_ascii_lowercase())
        .filter(|status| !status.is_empty())
        .collect::<BTreeSet<_>>();
    let global_low = object.get("include_low_rarity").is_some_and(pull_truthy);
    let mut output = Vec::new();
    for phase in object
        .get("phases")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
    {
        let status = effective_banner_status(&Value::Object(phase.clone()), local_datetime)
            .map_err(|error| PullValueError::Invalid(format!("invalid banner plan: {error}")))?;
        if !status_set.is_empty() && !status_set.contains(&status) {
            continue;
        }
        let phase_low = global_low || phase.get("include_low_rarity").is_some_and(pull_truthy);
        for character in phase
            .get("characters")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_object)
        {
            let slug = canonical_slug(&pull_or_text(character.get("slug")), names);
            if slug.is_empty() {
                continue;
            }
            let mut row = character.clone();
            if phase_low && !row.contains_key("include_low_rarity") {
                row.insert("include_low_rarity".to_owned(), Value::Bool(true));
            }
            row.insert("slug".to_owned(), Value::String(slug));
            row.insert("status".to_owned(), Value::String(status.clone()));
            row.insert(
                "phase_title".to_owned(),
                phase.get("title").cloned().unwrap_or_else(empty_string),
            );
            row.insert(
                "phase_subtitle".to_owned(),
                phase.get("subtitle").cloned().unwrap_or_else(empty_string),
            );
            output.push(row);
        }
    }
    Ok(output)
}

fn candidate_slug(candidate: &Map<String, Value>) -> String {
    candidate
        .get("slug")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

fn filter_review_candidates(
    candidates: CandidateList,
    tiers: &BTreeMap<String, TierMeta>,
) -> (CandidateList, CandidateList) {
    let mut review = Vec::new();
    let mut filtered = Vec::new();
    for candidate in candidates {
        if candidate.get("force_review").is_some_and(pull_truthy)
            || candidate.get("include_low_rarity").is_some_and(pull_truthy)
        {
            review.push(candidate);
            continue;
        }
        let slug = candidate_slug(&candidate);
        if is_low_rarity(&candidate, tiers.get(&slug)) {
            filtered.push(candidate);
        } else {
            review.push(candidate);
        }
    }
    (review, filtered)
}

fn is_low_rarity(candidate: &Map<String, Value>, tier: Option<&TierMeta>) -> bool {
    let rarity = pull_or_text(candidate.get("rarity"));
    let rarity = if rarity.is_empty() {
        tier.and_then(|tier| tier.values.get("rarity"))
            .cloned()
            .unwrap_or_default()
    } else {
        rarity
    };
    let rarity = character_slug(&rarity).replace('-', "");
    if matches!(rarity.as_str(), "a" | "4" | "4star" | "fourstar") {
        return true;
    }
    let text = [
        pull_or_text(candidate.get("banner_role")),
        pull_or_text(candidate.get("rarity")),
        candidate
            .get("analysis_tags")
            .and_then(Value::as_array)
            .map(|items| items.iter().map(pull_text).collect::<Vec<_>>().join(" "))
            .unwrap_or_default(),
    ]
    .join(" ")
    .to_ascii_lowercase();
    ["a 级", "a级", "四星", "4星", "4-star", "4 star"]
        .iter()
        .any(|marker| text.contains(marker))
}

fn parse_usage(bytes: Option<&[u8]>) -> PullValueResult<UsageIndex> {
    let Some(bytes) = bytes else {
        return Ok(UsageIndex::default());
    };
    let table = parse_csv(bytes, "character_usage_long.csv")?;
    let mut grouped = BTreeMap::<String, BTreeMap<String, Vec<(String, f64)>>>::new();
    let mut mode_order_by_slug = BTreeMap::<String, Vec<String>>::new();
    let mut raw_slugs = BTreeSet::new();
    for row in table.rows {
        let slug = character_slug(field(&row, "character_slug"));
        if !slug.is_empty() {
            raw_slugs.insert(slug.clone());
        }
        if field(&row, "sub_mode") != "all" {
            continue;
        }
        let Some(rate) = parse_percent(field(&row, "app_rate")).filter(|rate| rate.is_finite())
        else {
            continue;
        };
        let mode = field(&row, "mode").to_owned();
        push_unique(
            mode_order_by_slug.entry(slug.clone()).or_default(),
            mode.clone(),
        );
        grouped
            .entry(slug)
            .or_default()
            .entry(mode)
            .or_default()
            .push((field(&row, "collect_date").to_owned(), rate));
    }
    let mut output = BTreeMap::new();
    for (slug, mut modes) in grouped {
        let mut summary = UsageSummary::default();
        for mode in mode_order_by_slug.remove(&slug).unwrap_or_default() {
            let mut points = modes.remove(&mode).unwrap_or_default();
            points.sort_by(|left, right| left.0.cmp(&right.0));
            if points.is_empty() {
                continue;
            }
            let values = points.iter().map(|(_, value)| *value).collect::<Vec<_>>();
            let take = values.len().min(3);
            let avg = python_round(
                values[values.len() - take..].iter().sum::<f64>() / take as f64,
                3,
            );
            let trend = if values.len() >= 2 {
                python_round(values.last().unwrap() - values.first().unwrap(), 3)
            } else {
                0.0
            };
            let item = UsageMode {
                points: values.len(),
                latest: *values.last().unwrap(),
                avg_last3: avg,
                trend_delta: trend,
            };
            let first_mode = summary.mode_order.is_empty();
            summary.points += item.points;
            if first_mode {
                summary.best_avg_last3 = item.avg_last3;
                summary.best_latest = item.latest;
            } else {
                if item.avg_last3 > summary.best_avg_last3 {
                    summary.best_avg_last3 = item.avg_last3;
                }
                if item.latest > summary.best_latest {
                    summary.best_latest = item.latest;
                }
            }
            summary.mode_order.push(mode.clone());
            summary.modes.insert(mode, item);
        }
        summary.worst_trend_delta = summary
            .mode_order
            .iter()
            .filter_map(|mode| summary.modes.get(mode))
            .map(|mode| mode.trend_delta)
            .reduce(|best, value| if value < best { value } else { best })
            .unwrap_or(0.0);
        output.insert(slug, summary);
    }
    Ok(UsageIndex {
        summaries: output,
        raw_slugs,
    })
}

fn parse_tiers(bytes: Option<&[u8]>) -> PullValueResult<BTreeMap<String, TierMeta>> {
    let Some(bytes) = bytes else {
        return Ok(BTreeMap::new());
    };
    let table = parse_csv(bytes, "prydwen_tier_current.csv")?;
    let mut grouped = BTreeMap::<String, Vec<BTreeMap<String, String>>>::new();
    for row in table.rows {
        let slug = character_slug(field(&row, "character_slug"));
        if !slug.is_empty() {
            grouped.entry(slug).or_default().push(row);
        }
    }
    let mut output = BTreeMap::new();
    for (slug, rows) in grouped {
        let best = first_max_rating(rows.iter()).expect("group is non-empty");
        let mut meta = TierMeta {
            best_rating: finite_float(field(best, "rating")),
            best_tier: field(best, "tier").to_owned(),
            values: best.clone(),
            by_mode: BTreeMap::new(),
        };
        let modes = rows
            .iter()
            .map(|row| field(row, "tier_mode"))
            .filter(|mode| !mode.is_empty())
            .collect::<BTreeSet<_>>();
        for mode in modes {
            let best = first_max_rating(rows.iter().filter(|row| field(row, "tier_mode") == mode))
                .expect("mode group is non-empty");
            let mut values = best.clone();
            values.insert(
                "best_rating".to_owned(),
                python_general_number(finite_float(field(best, "rating"))),
            );
            meta.by_mode.insert(mode.to_owned(), values);
        }
        output.insert(slug, meta);
    }
    Ok(output)
}

fn first_max_rating<'a>(
    rows: impl Iterator<Item = &'a BTreeMap<String, String>>,
) -> Option<&'a BTreeMap<String, String>> {
    rows.reduce(|best, row| {
        if finite_float(field(row, "rating")) > finite_float(field(best, "rating")) {
            row
        } else {
            best
        }
    })
}

fn python_round(value: f64, digits: usize) -> f64 {
    // CPython rounds the original binary64 value through its correctly rounded
    // decimal conversion path. Scaling first changes the tie (for example,
    // Python round(9.9995, 3) is 9.999, not 10.0).
    format!("{value:.digits$}").parse().unwrap_or(value)
}

fn finite_float(value: &str) -> f64 {
    value
        .trim()
        .parse::<f64>()
        .ok()
        .filter(|value| value.is_finite())
        .unwrap_or(0.0)
}

fn parse_mechanism_notes(
    inputs: &BTreeMap<String, Vec<u8>>,
    candidates: &[Map<String, Value>],
) -> PullValueResult<BTreeMap<String, Map<String, Value>>> {
    let wanted = candidates
        .iter()
        .map(candidate_slug)
        .collect::<BTreeSet<_>>();
    let mut output = BTreeMap::new();
    for (raw_slug, bytes) in inputs {
        let slug = character_slug(raw_slug);
        if !wanted.contains(&slug) {
            continue;
        }
        let object = parse_mechanism_note(bytes, &slug)?;
        output.insert(slug, object);
    }
    Ok(output)
}

/// Validate one mechanism-note layer before a later yaml/yml/json layer may
/// overwrite the same slug. Python parses every matching file in order, so an
/// invalid earlier layer must not be hidden by a valid later layer.
pub fn validate_mechanism_note_v1(bytes: &[u8]) -> PullValueResult<()> {
    parse_mechanism_note(bytes, "input").map(|_| ())
}

fn parse_mechanism_note(bytes: &[u8], slug: &str) -> PullValueResult<Map<String, Value>> {
    let value = parse_config(bytes, "mechanism note")?;
    validate_finite(&value, "mechanism note")?;
    value.as_object().cloned().ok_or_else(|| {
        PullValueError::Invalid(format!("mechanism note {slug} root must be an object"))
    })
}

fn parse_baseline(
    bytes: Option<&[u8]>,
    names: &NameIndexV1,
) -> PullValueResult<BTreeMap<String, BaselineEntry>> {
    let Some(bytes) = bytes else {
        return Ok(BTreeMap::new());
    };
    let value = parse_config(bytes, "decision baseline")?;
    validate_finite(&value, "decision baseline")?;
    let object = value.as_object().ok_or_else(|| {
        PullValueError::Invalid("decision baseline root must be an object".to_owned())
    })?;
    let change_policy = object.get("change_policy").and_then(Value::as_object);
    let global_categories = string_list(
        object
            .get("new_evidence_categories")
            .filter(|value| config_truthy(value))
            .or_else(|| {
                object
                    .get("allowed_new_evidence_categories")
                    .filter(|value| config_truthy(value))
            })
            .or_else(|| {
                change_policy
                    .and_then(|policy| policy.get("allowed_new_evidence_categories"))
                    .filter(|value| config_truthy(value))
            }),
    );
    let global_categories = if global_categories.is_empty() {
        NEW_EVIDENCE_CATEGORIES_V1
            .iter()
            .map(|value| (*value).to_owned())
            .collect::<Vec<_>>()
    } else {
        global_categories
    };
    let rows = object
        .get("decisions")
        .filter(|value| config_truthy(value))
        .or_else(|| {
            object
                .get("characters")
                .filter(|value| config_truthy(value))
        })
        .or_else(|| object.get("baseline").filter(|value| config_truthy(value)));
    let mut iterable = Vec::<Map<String, Value>>::new();
    match rows {
        Some(Value::Object(values)) => {
            for (slug, value) in values {
                let mut row = value
                    .as_object()
                    .cloned()
                    .unwrap_or_else(|| Map::from_iter([("final_stage".to_owned(), value.clone())]));
                if !row.contains_key("slug") {
                    row.insert("slug".to_owned(), Value::String(slug.clone()));
                }
                iterable.push(row);
            }
        }
        Some(Value::Array(values)) => {
            iterable.extend(values.iter().filter_map(Value::as_object).cloned());
        }
        _ => {}
    }
    let mut output = BTreeMap::new();
    for mut row in iterable {
        let slug = canonical_slug(&first_pull_text(&row, &["slug", "character_slug"]), names);
        if slug.is_empty() {
            continue;
        }
        row.insert("slug".to_owned(), Value::String(slug.clone()));
        if !row.contains_key("allowed_new_evidence_categories") {
            row.insert(
                "allowed_new_evidence_categories".to_owned(),
                Value::Array(
                    global_categories
                        .iter()
                        .map(|value| Value::String(value.clone()))
                        .collect(),
                ),
            );
        }
        output.insert(slug, BaselineEntry { values: row });
    }
    Ok(output)
}

fn validate_finite(value: &Value, label: &str) -> PullValueResult<()> {
    match value {
        Value::Number(number) => {
            let token = number.to_string();
            let invalid = number
                .as_f64()
                .map(|number| !number.is_finite())
                .unwrap_or_else(|| token.contains(['.', 'e', 'E']));
            if invalid {
                Err(PullValueError::Invalid(format!(
                    "non-finite number in {label}"
                )))
            } else {
                Ok(())
            }
        }
        Value::Array(values) => {
            for value in values {
                validate_finite(value, label)?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for value in values.values() {
                validate_finite(value, label)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

#[allow(clippy::too_many_arguments)]
fn build_card(
    candidate: &Map<String, Value>,
    names: &NameIndexV1,
    account: &AccountStateV1,
    current_pool: &[EvidenceRecordV1],
    target_pool: &[EvidenceRecordV1],
    usage_index: &UsageIndex,
    tier_index: &BTreeMap<String, TierMeta>,
    mechanism_notes: &BTreeMap<String, Map<String, Value>>,
    baseline: &BTreeMap<String, BaselineEntry>,
) -> PullValueResult<PullValueCardV1> {
    let slug = candidate_slug(candidate);
    let usage = usage_index
        .summaries
        .get(&slug)
        .cloned()
        .unwrap_or_default();
    let tier = tier_index.get(&slug).cloned().unwrap_or_default();
    let mechanism = mechanism_notes.get(&slug).cloned().unwrap_or_default();
    let candidate_type = candidate_type(candidate, &slug, usage_index, tier_index);
    let current_records = records_for_slug(current_pool, &slug);
    let target_records = records_for_slug(target_pool, &slug);
    let dependent_records = target_records
        .iter()
        .copied()
        .filter(|record| record.plan_dependency.contains(&slug))
        .collect::<Vec<_>>();
    let exact_dependent = dependent_records
        .iter()
        .copied()
        .filter(|record| record.plan_dependency.as_slice() == [slug.as_str()])
        .collect::<Vec<_>>();
    let conditional_dependent = dependent_records
        .iter()
        .copied()
        .filter(|record| record.plan_dependency.as_slice() != [slug.as_str()])
        .collect::<Vec<_>>();
    let qualifying_exact = exact_dependent
        .iter()
        .copied()
        .filter(|record| is_main_confidence(record.confidence))
        .collect::<Vec<_>>();
    let qualifying_target = target_records
        .iter()
        .copied()
        .filter(|record| is_main_confidence(record.confidence))
        .collect::<Vec<_>>();
    let primary_records = if account.owned.contains(&slug) {
        qualifying_target
    } else {
        qualifying_exact
    };
    let risk_source = if account.owned.contains(&slug) {
        target_records.clone()
    } else {
        exact_dependent.clone()
    };
    let mut risk_records = conditional_dependent.clone();
    risk_records.extend(
        risk_source
            .iter()
            .copied()
            .filter(|record| !is_main_confidence(record.confidence)),
    );
    let risk_records = unique_records(risk_records);
    let primary_top = primary_records.iter().copied().take(5).collect::<Vec<_>>();
    let risk_top = risk_records.iter().copied().take(5).collect::<Vec<_>>();

    let coverage_summary = coverage_text(&current_records, &target_records, &dependent_records);
    let (pull_value, stage, basis, mut risks) = if candidate_type == "new" {
        (
            "等实测".to_owned(),
            stage_from_mechanism(&candidate_type, &mechanism, ""),
            vec![
                "新角色没有历史队伍记录属于正常未实测状态，不作为负面".to_owned(),
                mechanism_text(candidate, &tier, &mechanism),
                "先验证是否补当前 Box 拼图，还是要求后续售后队友".to_owned(),
            ],
            vec![
                if mechanism.is_empty() {
                    "等技能/影画/专武/首轮数据".to_owned()
                } else {
                    nonempty_value(&mechanism, "missing_data")
                        .unwrap_or_else(|| "机制、倍率、专属收益和售后环境尚未落地".to_owned())
                },
                "替代风险无法从当前历史数据判断".to_owned(),
            ],
        )
    } else {
        rerun_value(
            candidate,
            &usage,
            &tier,
            &current_records,
            &target_records,
            &exact_dependent,
            &primary_records,
            account.owned.contains(&slug),
            &mechanism,
        )
    };
    if !conditional_dependent.is_empty() {
        risks.push(format!(
            "{} 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据",
            conditional_dependent.len()
        ));
    }
    let baseline_fields = stage_baseline_fields(&stage, baseline.get(&slug));
    let name_cn = first_nonempty_owned([
        pull_or_text(candidate.get("name_cn")),
        names.names_cn.get(&slug).cloned().unwrap_or_default(),
        tier.values
            .get("character_name_cn")
            .cloned()
            .unwrap_or_default(),
        slug.clone(),
    ]);
    Ok(PullValueCardV1 {
        slug,
        name_cn,
        candidate_type,
        status: pull_or_text(candidate.get("status")),
        pull_value,
        stage_recommendation: stage,
        prior_final_stage: baseline_fields.prior_final_stage,
        prior_decision_status: baseline_fields.prior_decision_status,
        prior_confidence: baseline_fields.prior_confidence,
        prior_reason: baseline_fields.prior_reason,
        local_rule_stage: baseline_fields.local_rule_stage,
        recommended_stage_for_review: baseline_fields.recommended_stage_for_review,
        final_stage: baseline_fields.final_stage,
        stage_delta: baseline_fields.stage_delta,
        delta_requires_review: baseline_fields.delta_requires_review,
        delta_reason: baseline_fields.delta_reason,
        change_allowed_reason: baseline_fields.change_allowed_reason,
        new_evidence_categories: baseline_fields.new_evidence_categories,
        history_summary: history_text(&usage),
        global_usage_summary: global_usage_text(&usage),
        team_coverage_summary: coverage_summary,
        mechanism_review_summary: mechanism_review_text(&mechanism),
        mechanism_notes: Value::Object(mechanism.clone()),
        mechanism_summary: mechanism_text(candidate, &tier, &mechanism),
        replacement_risk: replacement_text(candidate, &tier, &mechanism),
        decision_basis: basis,
        risk_notes: risks,
        evidence_ids: primary_top
            .iter()
            .map(|record| record.evidence_id.clone())
            .collect(),
        risk_evidence_ids: risk_top
            .iter()
            .map(|record| record.evidence_id.clone())
            .collect(),
        evidence_keys: primary_top
            .iter()
            .map(|record| record.evidence_key.clone())
            .collect(),
        risk_evidence_keys: risk_top
            .iter()
            .map(|record| record.evidence_key.clone())
            .collect(),
        evidence_refs: primary_top
            .iter()
            .map(|record| evidence_ref(record))
            .collect(),
        risk_evidence_refs: risk_top.iter().map(|record| evidence_ref(record)).collect(),
    })
}

fn records_for_slug<'a>(records: &'a [EvidenceRecordV1], slug: &str) -> Vec<&'a EvidenceRecordV1> {
    let mut records = records
        .iter()
        .filter(|record| record.team_slugs.iter().any(|value| value == slug))
        .collect::<Vec<_>>();
    records.sort_by(|left, right| {
        confidence_rank(left.confidence)
            .cmp(&confidence_rank(right.confidence))
            .then_with(|| {
                right
                    .max_app_rate
                    .unwrap_or(0.0)
                    .total_cmp(&left.max_app_rate.unwrap_or(0.0))
            })
            .then_with(|| right.record_count.cmp(&left.record_count))
    });
    records
}

fn unique_records(records: Vec<&EvidenceRecordV1>) -> Vec<&EvidenceRecordV1> {
    let mut seen = BTreeSet::new();
    records
        .into_iter()
        .filter(|record| seen.insert(record.evidence_id.clone()))
        .collect()
}

fn confidence_rank(confidence: EvidenceConfidenceV1) -> u8 {
    match confidence {
        EvidenceConfidenceV1::A => 0,
        EvidenceConfidenceV1::BPlus => 1,
        EvidenceConfidenceV1::B => 2,
        EvidenceConfidenceV1::BMinus => 3,
        EvidenceConfidenceV1::C => 4,
    }
}

fn is_main_confidence(confidence: EvidenceConfidenceV1) -> bool {
    matches!(
        confidence,
        EvidenceConfidenceV1::A | EvidenceConfidenceV1::BPlus | EvidenceConfidenceV1::B
    )
}

fn evidence_ref(record: &EvidenceRecordV1) -> PullEvidenceRefV1 {
    PullEvidenceRefV1 {
        evidence_id: record.evidence_id.clone(),
        evidence_key: record.evidence_key.clone(),
        confidence: record.confidence.as_str().to_owned(),
        source_confidence: record.source_confidence.as_str().to_owned(),
        mode: record.mode.clone(),
        team_slugs: record.team_slugs.clone(),
        plan_dependency: record.plan_dependency.clone(),
        phase_versions: record.phase_versions.clone(),
        scopes: record.scopes.clone(),
        observation_keys: record.observation_keys.clone(),
    }
}

#[allow(clippy::too_many_arguments)]
fn rerun_value(
    candidate: &Map<String, Value>,
    usage: &UsageSummary,
    tier: &TierMeta,
    current_records: &[&EvidenceRecordV1],
    target_records: &[&EvidenceRecordV1],
    exact_dependent: &[&EvidenceRecordV1],
    primary_records: &[&EvidenceRecordV1],
    owned: bool,
    mechanism: &Map<String, Value>,
) -> (String, StageRecommendationV1, Vec<String>, Vec<String>) {
    let strong_target = exact_dependent
        .iter()
        .filter(|record| {
            matches!(
                record.confidence,
                EvidenceConfidenceV1::A | EvidenceConfidenceV1::BPlus
            )
        })
        .count();
    let good_target = exact_dependent
        .iter()
        .filter(|record| is_main_confidence(record.confidence))
        .count();
    let mut basis = Vec::new();
    let mut risks = Vec::new();
    if tier.best_rating != 0.0 {
        basis.push(format!(
            "T 榜最好评级 {} / rating {}",
            if tier.best_tier.is_empty() {
                "-"
            } else {
                &tier.best_tier
            },
            python_general_number(tier.best_rating)
        ));
    }
    if usage.points > 0 {
        basis.push(format!(
            "历史出场点 {}，近三期最高均值 {}%",
            usage.points,
            python_general_number(finite_or_zero(usage.best_avg_last3))
        ));
    }
    if !exact_dependent.is_empty() {
        basis.push(format!(
            "目标 Box 新增依赖队伍 {} 条，其中 A/B+ {} 条、A/B+/B {} 条",
            exact_dependent.len(),
            strong_target,
            good_target
        ));
    } else if !target_records.is_empty() {
        basis.push(format!(
            "目标 Box 可组历史队伍 {} 条，但不是该角色作为新增依赖",
            target_records.len()
        ));
    } else {
        risks.push("目标 Box 暂无可组历史队伍证据".to_owned());
    }
    if !current_records.is_empty() {
        basis.push(format!(
            "当前 Box 已有相关队伍 {} 条",
            current_records.len()
        ));
    }
    let modes = primary_records
        .iter()
        .map(|record| record.mode.clone())
        .filter(|mode| !mode.is_empty())
        .collect::<BTreeSet<_>>();
    let mut mode_results = Vec::<(String, String)>::new();
    for mode in modes {
        let records = primary_records
            .iter()
            .filter(|record| record.mode == mode)
            .collect::<Vec<_>>();
        let mode_usage = usage.modes.get(&mode).cloned().unwrap_or_default();
        let mode_rating = tier
            .by_mode
            .get(&mode)
            .and_then(|values| values.get("best_rating"))
            .map(|value| finite_float(value))
            .unwrap_or(0.0);
        let has_a = records
            .iter()
            .any(|record| record.confidence == EvidenceConfidenceV1::A);
        let has_b_plus = records
            .iter()
            .any(|record| record.confidence == EvidenceConfidenceV1::BPlus);
        let b_count = records
            .iter()
            .filter(|record| record.confidence == EvidenceConfidenceV1::B)
            .count();
        let mode_avg = finite_or_zero(mode_usage.avg_last3);
        let value = if mode_rating >= 11.0 && mode_avg >= 30.0 && mode_usage.points >= 6 && has_a {
            Some("高")
        } else if mode_rating >= 10.0 && mode_avg >= 10.0 && (has_a || has_b_plus || b_count >= 2) {
            Some("中高")
        } else if mode_usage.points > 0 {
            Some("中")
        } else {
            None
        };
        if let Some(value) = value {
            mode_results.push((value.to_owned(), mode));
        }
    }
    let pull_value = if mode_results.iter().any(|(value, _)| value == "高") {
        "高"
    } else if mode_results.iter().any(|(value, _)| value == "中高") {
        "中高"
    } else if usage.points > 0 {
        if primary_records.is_empty() {
            risks.push("有 tier/usage 历史强度，但缺目标账号 A/B 真实成队主证据".to_owned());
        } else if mode_results.is_empty() {
            risks.push("tier、usage 与 A/B 证据未在同一 mode 对齐，不给中高/高优先级".to_owned());
        } else {
            risks.push("同 mode 主证据仅支持中优先级".to_owned());
        }
        "中"
    } else {
        risks.push("复刻角色在本地历史样本不足".to_owned());
        "等实测"
    };
    let role = first_nonempty_owned([
        tier.values
            .get("role_group_cn")
            .cloned()
            .unwrap_or_default(),
        pull_or_text(candidate.get("role_group_cn")),
    ]);
    let stage = stage_from_mechanism("rerun", mechanism, &role);
    basis.push(format!(
        "mechanism_review：{}",
        mechanism_review_text(mechanism)
    ));
    for (value, mode) in mode_results {
        basis.push(format!("同模式判定 {mode}: {value}"));
    }
    if owned {
        risks.push("已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序".to_owned());
    }
    if !exact_dependent.is_empty() && current_records.is_empty() {
        risks.push(
            "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性"
                .to_owned(),
        );
    }
    (pull_value.to_owned(), stage, basis, risks)
}

fn candidate_type(
    candidate: &Map<String, Value>,
    slug: &str,
    usage: &UsageIndex,
    tiers: &BTreeMap<String, TierMeta>,
) -> String {
    let text = [
        pull_or_text(candidate.get("banner_role")),
        pull_or_text(candidate.get("status")),
        candidate
            .get("analysis_tags")
            .and_then(Value::as_array)
            .map(|values| values.iter().map(pull_text).collect::<Vec<_>>().join(" "))
            .unwrap_or_default(),
    ]
    .join(" ");
    if text.contains("新角色") || text.to_ascii_lowercase().contains("new") {
        "new".to_owned()
    } else if text.contains("复刻")
        || text.to_ascii_lowercase().contains("rerun")
        || tiers.contains_key(slug)
        || usage.raw_slugs.contains(slug)
    {
        "rerun".to_owned()
    } else {
        "new".to_owned()
    }
}

fn history_text(usage: &UsageSummary) -> String {
    if usage.points == 0 {
        return "暂无历史出场；若为新角色，这是未实测状态，不作为负面".to_owned();
    }
    usage
        .mode_order
        .iter()
        .filter_map(|mode| usage.modes.get(mode).map(|item| (mode, item)))
        .map(|(mode, item)| {
            format!(
                "{}: points {} / latest {}% / avg_last3 {}% / trend {}",
                mode,
                item.points,
                usage_history_number(item.latest),
                usage_history_number(item.avg_last3),
                usage_history_number(item.trend_delta)
            )
        })
        .collect::<Vec<_>>()
        .join("；")
}

fn global_usage_text(usage: &UsageSummary) -> String {
    format!(
        "best_latest={}%；best_avg_last3={}%；worst_trend={}",
        usage_global_number(usage.best_latest),
        usage_global_number(usage.best_avg_last3),
        usage_global_number(usage.worst_trend_delta)
    )
}

fn finite_or_zero(value: f64) -> f64 {
    if value.is_finite() {
        value
    } else {
        0.0
    }
}

fn usage_history_number(value: f64) -> String {
    if value.is_nan() {
        "nan".to_owned()
    } else if value == f64::INFINITY {
        "inf".to_owned()
    } else if value == f64::NEG_INFINITY {
        "-inf".to_owned()
    } else {
        python_general_number(value)
    }
}

fn usage_global_number(value: f64) -> String {
    if value.is_finite() {
        python_general_number(value)
    } else {
        "-".to_owned()
    }
}

fn coverage_text(
    current: &[&EvidenceRecordV1],
    target: &[&EvidenceRecordV1],
    dependent: &[&EvidenceRecordV1],
) -> String {
    fn counts(records: &[&EvidenceRecordV1]) -> String {
        let mut counts = BTreeMap::<u8, (&str, usize)>::new();
        for record in records {
            let rank = confidence_rank(record.confidence);
            counts
                .entry(rank)
                .and_modify(|(_, count)| *count += 1)
                .or_insert((record.confidence.as_str(), 1));
        }
        if counts.is_empty() {
            "0".to_owned()
        } else {
            counts
                .values()
                .map(|(name, count)| format!("{name} {count}"))
                .collect::<Vec<_>>()
                .join(" / ")
        }
    }
    format!(
        "current {}({})；target {}({})；新增依赖 {}({})",
        current.len(),
        counts(current),
        target.len(),
        counts(target),
        dependent.len(),
        counts(dependent)
    )
}

fn mechanism_text(
    candidate: &Map<String, Value>,
    tier: &TierMeta,
    mechanism: &Map<String, Value>,
) -> String {
    let identity = mechanism.get("identity").and_then(Value::as_object);
    let role = first_nonempty_owned([
        pull_or_text(candidate.get("role_group_cn")),
        tier.values
            .get("role_group_cn")
            .cloned()
            .unwrap_or_default(),
        pull_or_text(identity.and_then(|identity| identity.get("role_group_cn"))),
        "未知定位".to_owned(),
    ]);
    let element = first_nonempty_owned([
        pull_or_text(candidate.get("element_cn")),
        tier.values.get("element_cn").cloned().unwrap_or_default(),
        pull_or_text(identity.and_then(|identity| identity.get("element_cn"))),
        "未知属性".to_owned(),
    ]);
    let style = first_nonempty_owned([
        pull_or_text(candidate.get("style_cn")),
        tier.values.get("style_cn").cloned().unwrap_or_default(),
        pull_or_text(identity.and_then(|identity| identity.get("style_cn"))),
        "未知特性".to_owned(),
    ]);
    let focus = first_nonempty_owned([
        pull_or_text(candidate.get("focus")),
        pull_or_text(mechanism.get("mechanism_status")),
        "暂无机制文本".to_owned(),
    ]);
    let rarity = first_nonempty_owned([
        pull_or_text(candidate.get("rarity")),
        pull_or_text(identity.and_then(|identity| identity.get("rarity"))),
    ]);
    let mut extra = Vec::new();
    if !rarity.is_empty() {
        extra.push(format!("稀有度={rarity}"));
    }
    let archetypes = list_text(mechanism.get("archetypes"));
    if !archetypes.is_empty() {
        extra.push(format!("archetype={archetypes}"));
    }
    let teammates = list_text(mechanism.get("key_teammates"));
    if !teammates.is_empty() {
        extra.push(format!("关键队友={teammates}"));
    }
    let suffix = if extra.is_empty() {
        String::new()
    } else {
        format!("；{}", extra.join("；"))
    };
    format!("{element} / {style} / {role}；{focus}{suffix}")
}

fn replacement_text(
    candidate: &Map<String, Value>,
    tier: &TierMeta,
    mechanism: &Map<String, Value>,
) -> String {
    let counter = list_text(mechanism.get("risks_and_counterevidence"));
    if !counter.is_empty() {
        return counter;
    }
    let role = first_nonempty_owned([
        pull_or_text(candidate.get("role_group_cn")),
        tier.values
            .get("role_group_cn")
            .cloned()
            .unwrap_or_default(),
    ]);
    if role.is_empty() {
        "机制未知，替代风险无法判定".to_owned()
    } else if role.contains("辅助") || role.contains("支援") {
        "辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断".to_owned()
    } else {
        "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面".to_owned()
    }
}

fn mechanism_review_text(mechanism: &Map<String, Value>) -> String {
    if mechanism.is_empty() {
        return "暂无 mechanism_notes；等技能/影画/专武/首轮数据".to_owned();
    }
    let mut parts = Vec::new();
    let quality = source_quality_text(mechanism.get("source_quality"));
    if !quality.is_empty() {
        parts.push(format!("source_quality={quality}"));
    }
    if let Some(confidence) = nonempty_value(mechanism, "stage_confidence") {
        parts.push(format!("stage_confidence={confidence}"));
    }
    let stage_notes = stage_notes_text(mechanism.get("stage_notes"));
    if !stage_notes.is_empty() {
        parts.push(stage_notes);
    } else {
        for (stage, key) in [
            ("0+0", "body_completeness_0_0"),
            ("0+1", "signature_value_0_1"),
            ("1+0", "cinema_value_1_0"),
            ("1+1", "combo_value_1_1"),
            ("2+1", "necessity_2_1"),
        ] {
            parts.push(format!(
                "{}={}",
                stage,
                nonempty_value(mechanism, key).unwrap_or_else(|| "-".to_owned())
            ));
        }
    }
    parts.join("；")
}

fn stage_from_mechanism(
    candidate_type: &str,
    mechanism: &Map<String, Value>,
    role: &str,
) -> StageRecommendationV1 {
    if mechanism.is_empty() {
        return StageRecommendationV1 {
            recommended_stage: "等技能/影画/专武/首轮数据".to_owned(),
            acceptable_stage: "暂不预设".to_owned(),
            unresolved_stage: "0+0 / 0+1 / 1+0 / 1+1 / 2+1".to_owned(),
            stage_confidence: "low".to_owned(),
            not_recommended_stage: "暂不判断".to_owned(),
            reason: "缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X".to_owned(),
            missing_data: "技能机制、影画、专武、实战队伍、首轮高难数据".to_owned(),
        };
    }
    let recommended = nonempty_value(mechanism, "recommended_stage").unwrap_or_else(|| {
        if role.contains("辅助") || role.contains("支援") || candidate_type == "rerun" {
            "0+0".to_owned()
        } else {
            "等实测".to_owned()
        }
    });
    let acceptable =
        nonempty_value(mechanism, "acceptable_stage").unwrap_or_else(|| recommended.clone());
    let unresolved = nonempty_value(mechanism, "unresolved_stage")
        .unwrap_or_else(|| unresolved_stage_text(mechanism.get("stage_notes")));
    let confidence = nonempty_value(mechanism, "stage_confidence").unwrap_or_else(|| {
        if mechanism
            .get("stage_notes")
            .is_some_and(python_value_truthy)
        {
            "medium".to_owned()
        } else {
            "low".to_owned()
        }
    });
    let not_recommended = nonempty_value(mechanism, "not_recommended_stage")
        .or_else(|| nonempty_value(mechanism, "higher_stage_note"))
        .unwrap_or_else(|| "高档位暂不判断；只在机制/指南/实战证明必要时考虑".to_owned());
    let reason = nonempty_value(mechanism, "stage_reason")
        .or_else(|| nonempty_value(mechanism, "reason"))
        .unwrap_or_else(|| mechanism_review_text(mechanism));
    let missing_data = nonempty_value(mechanism, "missing_data")
        .or_else(|| {
            let value = stage_missing_data_text(mechanism.get("stage_notes"));
            (!value.is_empty()).then_some(value)
        })
        .unwrap_or_else(|| "持续观察后续版本实战、队友和环境变化".to_owned());
    StageRecommendationV1 {
        recommended_stage: recommended,
        acceptable_stage: acceptable,
        unresolved_stage: unresolved,
        stage_confidence: confidence,
        not_recommended_stage: not_recommended,
        reason,
        missing_data,
    }
}

fn stage_baseline_fields(
    stage: &StageRecommendationV1,
    entry: Option<&BaselineEntry>,
) -> BaselineFields {
    let local = stage.recommended_stage.trim().to_owned();
    let values = entry.map(|entry| &entry.values);
    let prior = values
        .map(|values| {
            first_pull_text(
                values,
                &["final_stage", "prior_final_stage", "recommended_stage"],
            )
        })
        .unwrap_or_default()
        .trim()
        .to_owned();
    let prior_status = values
        .map(|values| first_pull_text(values, &["decision_status", "status"]))
        .unwrap_or_default()
        .trim()
        .to_owned();
    let prior_confidence = values
        .map(|values| first_pull_text(values, &["confidence", "prior_confidence"]))
        .unwrap_or_default()
        .trim()
        .to_owned();
    let prior_reason = values
        .map(|values| first_pull_text(values, &["reason", "prior_reason"]))
        .unwrap_or_default()
        .trim()
        .to_owned();
    let categories = values
        .map(|values| {
            string_list(
                values
                    .get("new_evidence_categories")
                    .filter(|value| config_truthy(value))
                    .or_else(|| {
                        values
                            .get("new_evidence")
                            .filter(|value| config_truthy(value))
                    })
                    .or_else(|| {
                        values
                            .get("changed_by_new_evidence")
                            .filter(|value| config_truthy(value))
                    }),
            )
        })
        .unwrap_or_default();
    if prior.is_empty() {
        return BaselineFields {
            prior_final_stage: String::new(),
            prior_decision_status: prior_status,
            prior_confidence,
            prior_reason,
            local_rule_stage: local.clone(),
            recommended_stage_for_review: local.clone(),
            final_stage: local,
            stage_delta: "none".to_owned(),
            delta_requires_review: false,
            delta_reason: "无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。".to_owned(),
            change_allowed_reason: "no_prior_baseline".to_owned(),
            new_evidence_categories: categories,
        };
    }
    let differs = !local.is_empty() && local != prior;
    let stage_delta = if differs {
        format!(
            "{} -> {}",
            if local.is_empty() { "-" } else { &local },
            prior
        )
    } else {
        "none".to_owned()
    };
    let explicit_change = values.and_then(|values| nonempty_value(values, "change_allowed_reason"));
    let policy = values
        .and_then(|values| nonempty_value(values, "change_policy"))
        .unwrap_or_default();
    let (delta_reason, change_allowed_reason) = if differs && !categories.is_empty() {
        (
            "本地规则与既有 baseline 不同；已登记新增证据类别，需要 GPT/人工复审后才可改最终定档。"
                .to_owned(),
            format!("registered_new_evidence: {}", categories.join("、")),
        )
    } else if differs {
        (
            "本地规则与既有 baseline 不同；未登记新增证据，本地规则不能覆盖既有 GPT/人工定档。"
                .to_owned(),
            explicit_change.unwrap_or_else(|| {
                if policy.is_empty() {
                    "no_new_evidence_baseline_locked".to_owned()
                } else {
                    policy
                }
            }),
        )
    } else {
        (
            "本地规则与 baseline 一致；无需 delta review。".to_owned(),
            explicit_change.unwrap_or_else(|| "baseline_consistent".to_owned()),
        )
    };
    BaselineFields {
        prior_final_stage: prior.clone(),
        prior_decision_status: prior_status,
        prior_confidence,
        prior_reason,
        local_rule_stage: local,
        recommended_stage_for_review: prior.clone(),
        final_stage: prior,
        stage_delta,
        delta_requires_review: differs,
        delta_reason,
        change_allowed_reason,
        new_evidence_categories: categories,
    }
}

fn source_quality_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::Object(values)) => values
            .iter()
            .filter_map(|(key, value)| {
                let value = pull_text(value);
                (!value.is_empty()).then(|| format!("{key}={value}"))
            })
            .collect::<Vec<_>>()
            .join("；"),
        _ => list_text(value),
    }
}

fn stage_notes_text(value: Option<&Value>) -> String {
    let Some(values) = value.and_then(Value::as_object) else {
        return String::new();
    };
    let mut parts = Vec::new();
    for stage in ["0+0", "0+1", "1+0", "1+1", "2+1"] {
        let Some(note) = values.get(stage).and_then(Value::as_object) else {
            continue;
        };
        let mut fields = Vec::new();
        for (label, key) in [
            ("value_type", "value_type"),
            ("evidence", "evidence"),
            ("missing_data", "missing_data"),
        ] {
            if let Some(value) = nonempty_value(note, key) {
                fields.push(format!("{label}={value}"));
            }
        }
        if !fields.is_empty() {
            parts.push(format!("{}({})", stage, fields.join("; ")));
        }
    }
    parts.join("；")
}

fn unresolved_stage_text(value: Option<&Value>) -> String {
    let Some(values) = value.and_then(Value::as_object) else {
        return String::new();
    };
    ["0+1", "1+0", "1+1", "2+1"]
        .iter()
        .filter(|stage| {
            values
                .get(**stage)
                .and_then(Value::as_object)
                .and_then(|note| note.get("missing_data"))
                .is_some_and(python_value_truthy)
        })
        .copied()
        .collect::<Vec<_>>()
        .join(" / ")
}

fn stage_missing_data_text(value: Option<&Value>) -> String {
    let Some(values) = value.and_then(Value::as_object) else {
        return String::new();
    };
    ["0+0", "0+1", "1+0", "1+1", "2+1"]
        .iter()
        .filter_map(|stage| {
            values
                .get(*stage)
                .and_then(Value::as_object)
                .and_then(|note| nonempty_value(note, "missing_data"))
                .map(|value| format!("{stage}: {value}"))
        })
        .collect::<Vec<_>>()
        .join("；")
}

fn string_list(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Object(values)) => values
            .iter()
            .filter(|(_, enabled)| pull_truthy(enabled))
            .map(|(key, _)| key.trim().to_owned())
            .filter(|value| !value.is_empty())
            .collect(),
        Some(Value::Array(values)) => values
            .iter()
            .map(pull_text)
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .collect(),
        Some(value) if scalar_value_present(value) => pull_text(value)
            .replace(['；', '、'], ",")
            .split(',')
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
            .collect(),
        _ => Vec::new(),
    }
}

fn list_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::Array(values)) => values
            .iter()
            .map(pull_text)
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>()
            .join("、"),
        Some(value) if scalar_value_present(value) => pull_text(value),
        _ => String::new(),
    }
}

fn scalar_value_present(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::String(text) => !text.is_empty(),
        _ => true,
    }
}

fn nonempty_value(values: &Map<String, Value>, key: &str) -> Option<String> {
    values
        .get(key)
        .filter(|value| python_value_truthy(value))
        .map(pull_text)
}

fn first_pull_text(values: &Map<String, Value>, keys: &[&str]) -> String {
    keys.iter()
        .find_map(|key| nonempty_value(values, key))
        .unwrap_or_default()
}

fn first_nonempty_owned<const N: usize>(values: [String; N]) -> String {
    values
        .into_iter()
        .find(|value| !value.is_empty())
        .unwrap_or_default()
}

fn config_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().map(|value| value != 0.0).unwrap_or(true),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

fn pull_truthy(value: &Value) -> bool {
    match value {
        Value::Bool(value) => *value,
        Value::Null => false,
        Value::String(value) => {
            !value.is_empty()
                && !matches!(
                    value.trim().to_ascii_lowercase().as_str(),
                    "0" | "false" | "no" | "n" | "未启用"
                )
        }
        _ => pull_text(value).parse::<f64>() != Ok(0.0),
    }
}

fn pull_or_text(value: Option<&Value>) -> String {
    value
        .filter(|value| python_value_truthy(value))
        .map(pull_text)
        .unwrap_or_default()
}

fn pull_text(value: &Value) -> String {
    match value {
        Value::String(value) => value.clone(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(number) => python_json_number_repr(number),
        Value::Null => "None".to_owned(),
        value => value.to_string(),
    }
}

fn empty_string() -> Value {
    Value::String(String::new())
}

fn value_sort_key(value: &str) -> u8 {
    match value {
        "高" => 0,
        "中高" => 1,
        "中" => 2,
        "等实测" => 3,
        "低" => 4,
        _ => 9,
    }
}
