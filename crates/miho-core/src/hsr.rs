use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::normalize::{
    character_slug, character_slug_to_english, ordered_signature, unordered_signature,
};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PhaseRow {
    pub snapshot_id: String,
    pub collect_date: String,
    pub mode: String,
    pub mode_cn: String,
    pub phase_ver: String,
    pub phase_name: String,
    pub start_date: String,
    pub end_date: String,
    pub source: String,
    pub source_path: String,
    pub has_chars: i32,
    pub has_comps: i32,
    pub has_histograph: i32,
    pub note: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CharacterRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub app_rate: f64,
    pub app_rate_e0: Option<f64>,
    pub role: String,
    pub rarity: String,
    pub avg_round: Option<f64>,
    pub std_dev_round: Option<f64>,
    pub q1_round: Option<f64>,
    pub cons_avg: Option<f64>,
    pub sample: Option<f64>,
    pub sample_app_flat: Option<f64>,
    pub source_kind: String,
    pub source_file: String,
    pub source_url: String,
    pub quality_flag: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HistographRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub usage_value: f64,
    pub source_file: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TeamRow {
    pub mode: String,
    pub sub_mode: String,
    pub sub_mode_cn: String,
    pub phase_ver: String,
    pub scope: String,
    pub raw_index: usize,
    pub chars: [String; 4],
    pub raw_json: String,
    pub rank: Option<f64>,
    pub comp_name: String,
    pub app_rate: Option<f64>,
    pub avg_round: Option<f64>,
    pub whale_count: Option<f64>,
    pub app_flat: Option<f64>,
    pub uses: Option<f64>,
    pub source_kind: String,
    pub source_file: String,
    pub source_url: String,
}

impl TeamRow {
    pub fn signatures(&self, phase: &PhaseRow) -> (String, String) {
        (
            ordered_signature(
                &phase.snapshot_id,
                &phase.collect_date,
                &self.mode,
                &self.sub_mode,
                &self.scope,
                &self.phase_ver,
                &phase.phase_name,
                &self.chars,
            ),
            unordered_signature(
                &phase.snapshot_id,
                &phase.collect_date,
                &self.mode,
                &self.sub_mode,
                &self.scope,
                &self.phase_ver,
                &phase.phase_name,
                &self.chars,
            ),
        )
    }
}

#[allow(clippy::too_many_arguments)]
pub fn make_phase_row(
    snapshot_id: &str,
    config: &Value,
    mode: &str,
    source_path: &str,
    has_chars: bool,
    has_comps: bool,
    has_histograph: bool,
    collect_date: &str,
) -> PhaseRow {
    let mode_config = config.get(mode).and_then(Value::as_object);
    let text = |key: &str| {
        mode_config
            .and_then(|v| v.get(key))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_owned()
    };
    PhaseRow {
        snapshot_id: snapshot_id.to_owned(),
        collect_date: collect_date.to_owned(),
        mode: mode.to_owned(),
        mode_cn: match mode {
            "moc" => "混沌回忆",
            "pf" => "虚构叙事",
            "as" => "末日幻影",
            "aa" => "异相仲裁",
            _ => mode,
        }
        .to_owned(),
        phase_ver: {
            let v = text("ver");
            if v.is_empty() {
                snapshot_id.to_owned()
            } else {
                v
            }
        },
        phase_name: text("name"),
        start_date: text("start_iso"),
        end_date: text("end_iso"),
        source: "huggingface".to_owned(),
        source_path: source_path.to_owned(),
        has_chars: has_chars as i32,
        has_comps: has_comps as i32,
        has_histograph: has_histograph as i32,
        note: String::new(),
    }
}

fn number(value: Option<&Value>) -> Option<f64> {
    match value? {
        Value::Bool(_) | Value::Null => None,
        Value::Number(v) => v.as_f64(),
        Value::String(v) => v.trim().trim_end_matches('%').trim().parse().ok(),
        _ => None,
    }
}

fn character_row(item: &Value, mode: &str, builds: bool) -> Option<CharacterRow> {
    let object = item.as_object()?;
    let raw_slug = object
        .get("char")
        .or_else(|| object.get("character"))?
        .as_str()?;
    let slug = character_slug(raw_slug);
    if slug.is_empty() {
        return None;
    }
    let app_key = format!("app_rate_{mode}");
    let e0_key = format!("app_rate_{mode}_e0s1");
    let app_rate = if builds {
        number(object.get(&app_key))
    } else {
        number(object.get("app_rate").or_else(|| object.get("app")))
    }?;
    let app_rate_e0 = if builds {
        number(object.get(&e0_key))
    } else {
        number(
            object
                .get("app_rate_e0")
                .filter(|v| value_truthy(v))
                .or_else(|| object.get("app_rate_e1")),
        )
    };
    let field = |plain: &str, builds_key: Option<String>| {
        number(object.get(builds_key.as_deref().unwrap_or(plain)))
    };
    Some(CharacterRow {
        character_slug: slug.clone(),
        character_name_en: object
            .get("name")
            .filter(|v| value_truthy(v))
            .and_then(Value::as_str)
            .map(str::to_owned)
            .unwrap_or_else(|| character_slug_to_english(&slug)),
        app_rate,
        app_rate_e0,
        role: object
            .get("role")
            .filter(|v| value_truthy(v))
            .or_else(|| object.get("special_role"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_owned(),
        rarity: object.get("rarity").map(value_text).unwrap_or_default(),
        avg_round: field("avg_round", builds.then(|| format!("avg_round_{mode}"))),
        std_dev_round: number(object.get("std_dev_round")),
        q1_round: number(object.get("q1_round")),
        cons_avg: number(object.get("cons_avg")),
        sample: field("sample", builds.then(|| format!("sample_{mode}"))),
        sample_app_flat: if builds {
            number(object.get(&format!("sample_size_players_{mode}")))
        } else {
            number(
                object
                    .get("sample_app_flat")
                    .filter(|v| value_truthy(v))
                    .or_else(|| object.get("app_flat")),
            )
        },
        source_kind: "hf_chars".to_owned(),
        source_file: "fixture/builds.json".to_owned(),
        source_url: "fixture://builds".to_owned(),
        quality_flag: if mode == "aa" {
            "aa_all_bosses_only"
        } else {
            "ok"
        }
        .to_owned(),
    })
}

fn value_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::Number(v) => v.as_f64() != Some(0.0),
        Value::String(v) => !v.is_empty(),
        Value::Array(v) => !v.is_empty(),
        Value::Object(v) => !v.is_empty(),
    }
}

fn value_text(value: &Value) -> String {
    match value {
        Value::String(value) => value.clone(),
        Value::Number(value) => value.to_string(),
        Value::Bool(value) => value.to_string(),
        _ => String::new(),
    }
}

pub fn parse_builds_character_rows(builds: &Value, mode: &str) -> Vec<CharacterRow> {
    builds
        .as_array()
        .map(|v| {
            v.iter()
                .filter_map(|x| character_row(x, mode, true))
                .collect()
        })
        .unwrap_or_default()
}

pub fn parse_chars_file_character_rows(data: &Value, mode: &str) -> Vec<CharacterRow> {
    data.as_array()
        .map(|v| {
            v.iter()
                .filter_map(|x| character_row(x, mode, false))
                .collect()
        })
        .unwrap_or_default()
}

pub fn parse_histograph_rows(data: &Value, mode: &str, source_file: &str) -> Vec<HistographRow> {
    let usage_key = format!("{mode}_usage");
    data.as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| {
                    let object = item.as_object()?;
                    let slug = character_slug(object.get("char")?.as_str()?);
                    if slug.is_empty() {
                        return None;
                    }
                    let usage_value = number(object.get(&usage_key))?;
                    Some(HistographRow {
                        character_slug: slug.clone(),
                        character_name_en: object
                            .get("name")
                            .filter(|value| value_truthy(value))
                            .and_then(Value::as_str)
                            .map(str::to_owned)
                            .unwrap_or_else(|| character_slug_to_english(&slug)),
                        usage_value,
                        source_file: source_file.to_owned(),
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

pub fn histograph_fallback_character_rows(rows: &[HistographRow]) -> Vec<CharacterRow> {
    rows.iter()
        .map(|row| CharacterRow {
            character_slug: row.character_slug.clone(),
            character_name_en: row.character_name_en.clone(),
            app_rate: row.usage_value,
            app_rate_e0: None,
            source_kind: "hf_histograph_fallback".into(),
            role: String::new(),
            rarity: String::new(),
            avg_round: None,
            std_dev_round: None,
            q1_round: None,
            cons_avg: None,
            sample: None,
            sample_app_flat: None,
            source_file: row.source_file.clone(),
            source_url: String::new(),
            quality_flag: "histograph_fallback".into(),
        })
        .collect()
}

pub fn parse_team_rows(
    data: &Value,
    mode: &str,
    phase_ver: &str,
    scope_hint: &str,
    top_n: Option<usize>,
) -> Vec<TeamRow> {
    let Some(items) = data.as_array() else {
        return Vec::new();
    };
    let filename = scope_hint
        .rsplit('/')
        .next()
        .unwrap_or("")
        .trim_end_matches(".json")
        .trim_end_matches("_combined");
    let (sub_mode, sub_mode_cn) = hsr_scope(mode, filename);
    items
        .iter()
        .enumerate()
        .take(top_n.unwrap_or(usize::MAX))
        .filter_map(|(index, item)| {
            let object = item.as_object()?;
            let keys = [
                ("char_one", "char_1"),
                ("char_two", "char_2"),
                ("char_three", "char_3"),
                ("char_four", "char_4"),
            ];
            let chars = keys.map(|(a, b)| {
                object
                    .get(a)
                    .filter(|v| value_truthy(v))
                    .or_else(|| object.get(b))
                    .and_then(Value::as_str)
                    .map(character_slug)
                    .unwrap_or_default()
            });
            if chars.iter().any(String::is_empty) {
                return None;
            }
            Some(TeamRow {
                mode: mode.to_owned(),
                sub_mode: sub_mode.clone(),
                sub_mode_cn: sub_mode_cn.clone(),
                phase_ver: phase_ver.to_owned(),
                scope: if filename.is_empty() {
                    "all".to_owned()
                } else {
                    filename.to_owned()
                },
                raw_index: index + 1,
                chars,
                raw_json: serde_json::to_string(item).unwrap_or_default(),
                rank: number(object.get("rank")),
                comp_name: object.get("comp_name").map(value_text).unwrap_or_default(),
                app_rate: number(object.get("app_rate")),
                avg_round: number(object.get("avg_round")),
                whale_count: number(object.get("whale_count")),
                app_flat: number(object.get("app_flat")),
                uses: number(object.get("uses")),
                source_kind: "hf_comps".to_owned(),
                source_file: "teams.json".to_owned(),
                source_url: "fixture://teams".to_owned(),
            })
        })
        .collect()
}

fn hsr_scope(mode: &str, filename: &str) -> (String, String) {
    let normalized = character_slug(filename);
    if mode == "aa" {
        let lowered = filename.to_lowercase();
        if filename.contains("骑士")
            || normalized.contains("knights")
            || normalized.contains("knight")
        {
            return ("knights".into(), "骑士关卡".into());
        }
        if filename.contains("王棋") || normalized.contains("king") || normalized.contains("boss")
        {
            return ("king_piece".into(), "王棋关卡".into());
        }
        if lowered.contains("all-bosses") || matches!(normalized.as_str(), "all" | "all-bosses") {
            return ("all_bosses".into(), "全 Boss / 未拆分".into());
        }
        return ("all_bosses".into(), "全 Boss / 未拆分".into());
    }
    if normalized.is_empty() || normalized == "top" {
        ("all".into(), "全部".into())
    } else {
        (
            format!("stage_{}", normalized.replace('-', "_")),
            normalized,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn minimal_fixture_matches_python_oracle() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/hsr_parser_minimal.json"
        ))
        .unwrap();
        let phase = make_phase_row(
            "4.3.2",
            &fixture["config"],
            "moc",
            "4.3.2/",
            true,
            false,
            true,
            "2026-06-25",
        );
        assert_eq!(phase.phase_ver, "4.2.1");
        assert_eq!(
            parse_builds_character_rows(&fixture["builds"], "moc")[0].app_rate,
            12.5
        );
        assert_eq!(
            parse_chars_file_character_rows(&fixture["chars"], "moc")[0].app_rate_e0,
            Some(3.0)
        );
        let histograph =
            parse_histograph_rows(&fixture["histograph"], "moc", "4.3.2/histograph.json");
        assert_eq!(
            histograph,
            vec![HistographRow {
                character_slug: "topaz-and-numby".into(),
                character_name_en: "Topaz and Numby".into(),
                usage_value: 8.25,
                source_file: "4.3.2/histograph.json".into(),
            }]
        );
        assert_eq!(
            histograph_fallback_character_rows(&histograph),
            vec![CharacterRow {
                character_slug: "topaz-and-numby".into(),
                character_name_en: "Topaz and Numby".into(),
                app_rate: 8.25,
                app_rate_e0: None,
                role: String::new(),
                rarity: String::new(),
                avg_round: None,
                std_dev_round: None,
                q1_round: None,
                cons_avg: None,
                sample: None,
                sample_app_flat: None,
                source_kind: "hf_histograph_fallback".into(),
                source_file: "4.3.2/histograph.json".into(),
                source_url: String::new(),
                quality_flag: "histograph_fallback".into(),
            }]
        );
        let teams = parse_team_rows(
            &fixture["teams"],
            "moc",
            "4.2.1",
            "stage_1_combined.json",
            Some(2),
        );
        assert_eq!(teams.len(), 1);
        assert_eq!(teams[0].raw_index, 2);
        assert_eq!(
            teams[0].signatures(&phase),
            (
                "4.3.2|2026-06-25|moc|stage_stage_1|stage_1|4.2.1|Example Phase|d>b>a>c".to_owned(),
                "4.3.2|2026-06-25|moc|stage_stage_1|stage_1|4.2.1|Example Phase|a>b>c>d".to_owned()
            )
        );
    }
}
