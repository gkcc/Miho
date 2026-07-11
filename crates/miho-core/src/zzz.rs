use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::normalize::character_slug;

#[derive(Debug, Clone, Deserialize)]
pub struct PhaseInput {
    pub snapshot_id: String,
    pub mode: String,
    #[serde(default)]
    pub collect_date: String,
    #[serde(default)]
    pub ver: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub start: String,
    #[serde(default)]
    pub end: String,
    pub source_path: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PhaseRow {
    pub snapshot_id: String,
    pub collect_date: String,
    pub mode_cn: String,
    pub mode: String,
    pub phase_ver: String,
    pub phase_name: String,
    pub start_date: String,
    pub end_date: String,
    pub source: String,
    pub source_path: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TeamInput {
    #[serde(alias = "char_one")]
    pub char_1: Option<String>,
    #[serde(alias = "char_two")]
    pub char_2: Option<String>,
    #[serde(alias = "char_three")]
    pub char_3: Option<String>,
    #[serde(default)]
    pub bangboo: Option<String>,
    #[serde(default)]
    pub rank: Value,
    #[serde(default)]
    pub app_rate: Value,
    #[serde(default)]
    pub avg_round: Value,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TeamRow {
    pub sub_mode: String,
    pub sub_mode_cn: String,
    pub scope: String,
    pub rank: f64,
    pub char_1_slug: String,
    pub char_2_slug: String,
    pub char_3_slug: String,
    pub bangboo_slug: String,
    pub app_rate: Option<f64>,
    pub avg_score: Option<f64>,
    pub raw_index: usize,
    pub raw_json: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct UsageRow {
    pub sub_mode: String,
    pub sub_mode_cn: String,
    pub character_slug: String,
    pub app_rate: Option<f64>,
    pub avg_score: Option<f64>,
}

pub fn make_phase_row(input: PhaseInput) -> PhaseRow {
    let mode_name = mode_cn(&input.mode).to_owned();
    let phase_ver = nonempty(&input.ver)
        .unwrap_or(&input.snapshot_id)
        .to_owned();
    let phase_name = nonempty(&input.name)
        .map(str::to_owned)
        .unwrap_or_else(|| format!("{mode_name} {phase_ver}"));
    PhaseRow {
        snapshot_id: input.snapshot_id,
        collect_date: parse_date(&input.collect_date),
        mode: input.mode,
        mode_cn: mode_name,
        phase_ver,
        phase_name,
        start_date: parse_date(&input.start),
        end_date: parse_date(&input.end),
        source: "hf_processed".into(),
        source_path: input.source_path,
    }
}

pub fn scope_label(mode: &str, scope: &str) -> (String, String) {
    let text = scope
        .replace("_combined.json", "")
        .replace(".json", "")
        .replace("top", "all");
    let normalized = text
        .trim()
        .to_ascii_lowercase()
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' {
                c
            } else {
                '-'
            }
        })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("-");
    if normalized.is_empty() || normalized == "all" {
        return ("all".into(), "全部".into());
    }
    if mode == "sd" && matches!(normalized.as_str(), "1" | "2" | "3") {
        return (format!("5-{normalized}"), format!("第5防线 {normalized}"));
    }
    if mode == "da" && matches!(normalized.as_str(), "1" | "2" | "3") {
        return (format!("1-{normalized}"), format!("首领 {normalized}"));
    }
    if (mode == "sd" && normalized.starts_with("5-"))
        || (mode == "da" && normalized.starts_with("1-"))
    {
        return (normalized.clone(), normalized.replace('-', " / "));
    }
    (normalized.clone(), normalized)
}

pub fn parse_team_rows(teams: Vec<Value>, mode: &str, scope: &str) -> Vec<TeamRow> {
    let (sub_mode, sub_mode_cn) = scope_label(mode, scope);
    teams
        .into_iter()
        .enumerate()
        .filter_map(|(offset, raw)| {
            let item: TeamInput = serde_json::from_value(raw.clone()).ok()?;
            let chars = [item.char_1?, item.char_2?, item.char_3?].map(|v| character_slug(&v));
            if chars.iter().any(|v| v.is_empty() || v == "-") {
                return None;
            }
            let index = offset + 1;
            let rank = number(&item.rank)
                .filter(|v| *v != 0.0)
                .unwrap_or(index as f64);
            Some(TeamRow {
                sub_mode: sub_mode.clone(),
                sub_mode_cn: sub_mode_cn.clone(),
                scope: scope.into(),
                rank,
                char_1_slug: chars[0].clone(),
                char_2_slug: chars[1].clone(),
                char_3_slug: chars[2].clone(),
                bangboo_slug: item.bangboo.map(|v| character_slug(&v)).unwrap_or_default(),
                app_rate: percent(&item.app_rate),
                avg_score: number(&item.avg_round),
                raw_index: index,
                raw_json: serde_json::to_string(&raw).unwrap_or_default(),
            })
        })
        .collect()
}

pub fn parse_usage(item: &Value, mode: &str) -> Vec<UsageRow> {
    let Some(slug) = item.get("char").and_then(Value::as_str).map(character_slug) else {
        return vec![];
    };
    if slug.is_empty() {
        return vec![];
    }
    let mut rows = vec![usage_row(item, mode, &slug, None)];
    for boss in 1..=3 {
        if item.get(format!("app_rate_{mode}_boss_{boss}")).is_some() {
            rows.push(usage_row(item, mode, &slug, Some(boss)));
        }
    }
    rows
}

fn usage_row(item: &Value, mode: &str, slug: &str, boss: Option<usize>) -> UsageRow {
    let (sub_mode, sub_mode_cn, suffix) = match boss {
        None => ("all".into(), "全部".into(), String::new()),
        Some(index) if mode == "sd" => (
            format!("5-{index}"),
            format!("第5防线 {index}"),
            format!("_boss_{index}"),
        ),
        Some(index) => (
            format!("1-{index}"),
            format!("首领 {index}"),
            format!("_boss_{index}"),
        ),
    };
    UsageRow {
        sub_mode,
        sub_mode_cn,
        character_slug: slug.into(),
        app_rate: item
            .get(format!("app_rate_{mode}{suffix}"))
            .and_then(percent),
        avg_score: item
            .get(format!("avg_round_{mode}{suffix}"))
            .and_then(number),
    }
}

fn mode_cn(mode: &str) -> &str {
    match mode {
        "sd" => "式舆防卫",
        "da" => "危局强袭战",
        _ => mode,
    }
}
fn nonempty(value: &str) -> Option<&str> {
    (!value.trim().is_empty()).then_some(value)
}
fn parse_date(value: &str) -> String {
    let parts = value.split('/').collect::<Vec<_>>();
    if parts.len() == 3 {
        format!("{}-{:0>2}-{:0>2}", parts[2], parts[1], parts[0])
    } else {
        value.into()
    }
}
fn number(value: &Value) -> Option<f64> {
    value
        .as_f64()
        .or_else(|| value.as_str()?.trim().replace(',', "").parse().ok())
}
fn percent(value: &Value) -> Option<f64> {
    if let Some(value) = value.as_f64() {
        return Some(value);
    }
    let text = value.as_str()?.trim();
    if text.is_empty() || matches!(text, "-" | "--" | "N/A" | "n/a") {
        return None;
    }
    text.trim_end_matches('%')
        .trim()
        .replace(',', "")
        .parse()
        .ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn minimal_parser_matches_pinned_python_behavior() {
        let phase = make_phase_row(PhaseInput {
            snapshot_id: "3.0.1".into(),
            mode: "sd".into(),
            collect_date: "21/06/2026".into(),
            ver: "2.8.3".into(),
            name: String::new(),
            start: "12/06/2026".into(),
            end: "26/06/2026".into(),
            source_path: "3.0.1/".into(),
        });
        assert_eq!(
            (phase.collect_date.as_str(), phase.phase_ver.as_str()),
            ("2026-06-21", "2.8.3")
        );
        let usage = parse_usage(
            &json!({"char":"Miyabi","app_rate_sd":42,"avg_round_sd":33000,"app_rate_sd_boss_1":"26.39%","avg_round_sd_boss_1":34468}),
            "sd",
        );
        assert_eq!(
            (
                usage[0].sub_mode.as_str(),
                usage[1].sub_mode.as_str(),
                usage[1].app_rate
            ),
            ("all", "5-1", Some(26.39))
        );
    }

    #[test]
    fn team_rank_zero_falls_back_and_missing_bangboo_is_empty() {
        let teams = serde_json::from_value(json!([{"char_one":"miyabi","char_two":"nangong-yu","char_three":"ukinami-yuzuha","rank":0,"app_rate":26.39}])).unwrap();
        let rows = parse_team_rows(teams, "sd", "5-1_combined.json");
        assert_eq!(
            (
                rows[0].rank,
                rows[0].scope.as_str(),
                rows[0].bangboo_slug.as_str()
            ),
            (1.0, "5-1_combined.json", "")
        );
        assert_eq!(
            scope_label("da", "top_combined.json"),
            ("all".into(), "全部".into())
        );
    }
}
