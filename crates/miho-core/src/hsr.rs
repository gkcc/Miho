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
    pub source_kind: String,
    pub quality_flag: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TeamRow {
    pub mode: String,
    pub sub_mode: String,
    pub phase_ver: String,
    pub scope: String,
    pub raw_index: usize,
    pub chars: [String; 4],
    pub raw_json: String,
}

impl TeamRow {
    pub fn signatures(&self) -> (String, String) {
        (
            ordered_signature(&self.mode, &self.sub_mode, &self.phase_ver, &self.chars),
            unordered_signature(&self.mode, &self.sub_mode, &self.phase_ver, &self.chars),
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
        source_kind: "hf_chars".to_owned(),
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
    let sub_mode = if mode == "aa" {
        "all_bosses".to_owned()
    } else if filename.is_empty() || filename == "top" {
        "all".to_owned()
    } else {
        format!("stage_{}", character_slug(filename).replace('-', "_"))
    };
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
                phase_ver: phase_ver.to_owned(),
                scope: if filename.is_empty() {
                    "all".to_owned()
                } else {
                    filename.to_owned()
                },
                raw_index: index + 1,
                chars,
                raw_json: serde_json::to_string(item).unwrap_or_default(),
            })
        })
        .collect()
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
            teams[0].signatures(),
            (
                "moc|stage_stage_1|4.2.1|d>b>a>c".to_owned(),
                "moc|stage_stage_1|4.2.1|a>b>c>d".to_owned()
            )
        );
    }
}
