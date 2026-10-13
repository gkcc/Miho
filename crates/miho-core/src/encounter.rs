//! Target encounter data is separate from historical team performance.
//!
//! Optional local records retain their original encounter and metric scope;
//! no exporter is allowed to manufacture per-side performance from a floor total.
use std::collections::BTreeSet;

use chrono::NaiveDate;
use serde_json::{json, Value};

use crate::{
    output::ArtifactBundle,
    visualizer::{safe_link_url, validate_json_surrogate_escapes, VisualizerContext},
    MihoError, Result,
};

const SCHEMA: &str = "miho-encounters-v1";
const MAX_ROWS: usize = 20_000;
const MAX_BYTES: usize = 16 * 1024 * 1024;

fn load(bundle: &ArtifactBundle, context: &VisualizerContext, name: &str) -> Result<Option<Value>> {
    let Some(bytes) = bundle.get(name).or_else(|| context.sidecar(name)) else {
        return Ok(None);
    };
    if bytes.len() > MAX_BYTES {
        return Err(MihoError::Visualizer(format!(
            "{name}: encounter input exceeds size limit"
        )));
    }
    let decoded = std::str::from_utf8(bytes)
        .map_err(|_| error(name, "encounter input is not valid UTF-8"))?;
    validate_json_surrogate_escapes(decoded, name)?;
    serde_json::from_slice(bytes)
        .map(Some)
        .map_err(|source| MihoError::Json {
            path: name.into(),
            source,
        })
}

fn text<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or("")
}

fn error(name: &str, message: &str) -> MihoError {
    MihoError::Visualizer(format!("{name}: {message}"))
}

fn sanitize_links(value: &mut Value) {
    match value {
        Value::Object(map) => {
            for (key, item) in map {
                if key.ends_with("url") {
                    if let Some(url) = item.as_str() {
                        *item = Value::String(safe_link_url(url));
                    }
                } else {
                    sanitize_links(item);
                }
            }
        }
        Value::Array(values) => values.iter_mut().for_each(sanitize_links),
        _ => {}
    }
}

/// Add the same versioned, provenance-preserving contract to both games.
pub fn attach_advice_data(
    game: &str,
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
    data: &mut Value,
) -> Result<()> {
    let name = format!("{game}_encounters_v1.json");
    let mut encounters = Vec::new();
    let mut records = Vec::new();
    let mut profiles = Vec::new();
    let mut warnings = Vec::new();
    let mut keys = BTreeSet::new();
    if let Some(root) = load(bundle, context, &name)? {
        if text(&root, "schema_version") != SCHEMA || text(&root, "game") != game {
            return Err(error(&name, "schema or game identity mismatch"));
        }
        let rows = root
            .get("encounters")
            .and_then(Value::as_array)
            .ok_or_else(|| error(&name, "encounters must be an array"))?;
        if rows.len() > MAX_ROWS {
            return Err(error(&name, "too many encounters"));
        }
        for original in rows {
            let mut row = original.clone();
            let key = text(&row, "scope_key").to_owned();
            if text(&row, "game") != game
                || text(&row, "mode").is_empty()
                || text(&row, "phase_ver").is_empty()
                || key.is_empty()
                || text(&row, "label").is_empty()
                || !keys.insert(key)
            {
                return Err(error(
                    &name,
                    "incomplete, duplicate, or wrong-game encounter identity",
                ));
            }
            for field in ["weaknesses", "resistances", "enemies", "effects"] {
                if !row.get(field).is_some_and(Value::is_array) {
                    return Err(error(&name, "encounter list field is missing or invalid"));
                }
            }
            let start = NaiveDate::parse_from_str(text(&row, "start_date"), "%Y-%m-%d").ok();
            let end = NaiveDate::parse_from_str(text(&row, "end_date"), "%Y-%m-%d").ok();
            let status = match (start, end) {
                (Some(start), Some(end)) if end >= start => {
                    if context.local_date < start {
                        "future"
                    } else if context.local_date > end {
                        "expired"
                    } else {
                        "current"
                    }
                }
                _ => "unknown",
            };
            row["phase_status"] = json!(status);
            sanitize_links(&mut row);
            encounters.push(row);
        }
        if let Some(rows) = root.get("warnings").and_then(Value::as_array) {
            warnings.extend(rows.iter().filter_map(Value::as_str).map(str::to_owned));
        }
    }
    let record_name = format!("{game}_battle_records_v1.json");
    if let Some(root) = load(bundle, context, &record_name)? {
        if text(&root, "schema_version") != "miho-battle-records-v1" || text(&root, "game") != game
        {
            return Err(error(&record_name, "schema or game identity mismatch"));
        }
        let rows = root
            .get("records")
            .and_then(Value::as_array)
            .ok_or_else(|| error(&record_name, "records must be an array"))?;
        if rows.len() > MAX_ROWS {
            return Err(error(&record_name, "too many battle records"));
        }
        let mut seen = BTreeSet::new();
        for original in rows {
            let mut row = original.clone();
            let Some(chars) = row.get("chars").and_then(Value::as_array) else {
                continue;
            };
            let members: BTreeSet<_> = chars.iter().filter_map(Value::as_str).collect();
            let count = if game == "hsr" { 4 } else { 3 };
            let metric = row.get("metric_value").and_then(Value::as_f64);
            if text(&row, "game") != game
                || chars.len() != count
                || members.len() != count
                || members.iter().any(|member| member.is_empty())
                || text(&row, "mode").is_empty()
                || text(&row, "phase_ver").is_empty()
                || text(&row, "encounter_key").is_empty()
                || text(&row, "source_group").is_empty()
                || text(&row, "record_id").is_empty()
                || row.get("is_quick_clear").and_then(Value::as_bool) != Some(false)
                || !metric.is_some_and(|value| {
                    value.is_finite()
                        && (value > 0.0 || (value == 0.0 && text(&row, "metric_kind") == "cycles"))
                        && value != 99.99
                })
                || !matches!(
                    text(&row, "metric_scope"),
                    "encounter" | "floor" | "node" | "stage" | "side"
                )
            {
                warnings.push("已跳过缺少完整阵容、有效成绩或实战标记的战绩记录。".into());
                continue;
            }
            let identity = format!(
                "{}|{}|{}|{}|{}",
                text(&row, "source_group"),
                text(&row, "record_id"),
                text(&row, "mode"),
                text(&row, "phase_ver"),
                text(&row, "encounter_key")
            );
            if !seen.insert(identity) {
                continue;
            }
            // A single record is evidence of a clear, never population-level A evidence.
            row["evidence_grade"] = json!("B");
            sanitize_links(&mut row);
            records.push(row);
        }
    }
    let profile_name = format!("{game}_team_profiles_v1.json");
    if let Some(root) = load(bundle, context, &profile_name)? {
        if text(&root, "schema_version") != "miho-team-profiles-v1" || text(&root, "game") != game {
            return Err(error(&profile_name, "schema or game identity mismatch"));
        }
        let rows = root
            .get("profiles")
            .and_then(Value::as_array)
            .ok_or_else(|| error(&profile_name, "profiles must be an array"))?;
        if rows.len() > MAX_ROWS {
            return Err(error(&profile_name, "too many team profiles"));
        }
        for original in rows {
            let mut row = original.clone();
            let count = if game == "hsr" { 4 } else { 3 };
            let members = row.get("chars").and_then(Value::as_array);
            if !members.is_some_and(|members| {
                members.len() == count
                    && members
                        .iter()
                        .filter_map(Value::as_str)
                        .collect::<BTreeSet<_>>()
                        .len()
                        == count
            }) || !row.get("primary_tags").is_some_and(Value::is_array)
                || !row.get("secondary_tags").is_some_and(Value::is_array)
            {
                return Err(error(&profile_name, "invalid complete-team profile"));
            }
            sanitize_links(&mut row);
            profiles.push(row);
        }
    }
    warnings.sort();
    warnings.dedup();
    data["encounterRows"] = json!(encounters);
    data["battleRecordRows"] = json!(records);
    data["teamProfileRows"] = json!(profiles);
    data["encounterDataQuality"] = json!({
        "schema_version":SCHEMA,"game":game,
        "encounter_count":encounters.len(),"battle_record_count":records.len(),
        "profile_count":profiles.len(),"warnings":warnings,
        "public_record_status":if records.is_empty() {"no_verified_records"} else {"available"}
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn context() -> VisualizerContext {
        VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 10, 13).unwrap())
    }

    #[test]
    fn encounter_identity_cannot_cross_games_or_duplicate_targets() {
        let mut bundle = ArtifactBundle::default();
        let row = json!({"game":"zzz","mode":"sd","phase_ver":"3.2.3",
            "scope_key":"official:3.2.3:4:1","label":"第四防线第一队",
            "start_date":"2026-10-02","end_date":"2026-10-15",
            "weaknesses":["风","电"],"resistances":["冰"],"enemies":[],"effects":[]});
        bundle
            .add_json(
                "zzz_encounters_v1.json",
                &json!({"schema_version":SCHEMA,"game":"zzz","encounters":[row.clone()]}),
            )
            .unwrap();
        let mut data = json!({});
        attach_advice_data("zzz", &bundle, &context(), &mut data).unwrap();
        assert_eq!(data["encounterRows"][0]["phase_status"], "current");
        assert_eq!(data["encounterRows"][0]["resistances"], json!(["冰"]));
        bundle
            .add_json(
                "zzz_encounters_v1.json",
                &json!({"schema_version":SCHEMA,"game":"zzz","encounters":[row.clone(),row]}),
            )
            .unwrap();
        assert!(attach_advice_data("zzz", &bundle, &context(), &mut data).is_err());
        bundle
            .add_json(
                "zzz_encounters_v1.json",
                &json!({"schema_version":SCHEMA,"game":"hsr","encounters":[]}),
            )
            .unwrap();
        assert!(attach_advice_data("zzz", &bundle, &context(), &mut data).is_err());
    }

    #[test]
    fn quick_clear_and_duplicates_are_not_promoted_to_real_target_samples() {
        let mut bundle = ArtifactBundle::default();
        let row = json!({"game":"hsr","mode":"moc","phase_ver":"4.6.1",
            "encounter_key":"official:1035:11:1","chars":["a","b","c","d"],
            "source_group":"same-origin","record_id":"clear-1","metric_kind":"cycles",
            "metric_scope":"floor","metric_value":0,"evidence_grade":"A","is_quick_clear":false,
            "source_url":"javascript:alert(1)"});
        let mut quick = row.clone();
        quick["record_id"] = json!("quick");
        quick["is_quick_clear"] = json!(true);
        bundle.add_json("hsr_battle_records_v1.json",&json!({"schema_version":"miho-battle-records-v1","game":"hsr","records":[row.clone(),row,quick]})).unwrap();
        let mut data = json!({});
        attach_advice_data("hsr", &bundle, &context(), &mut data).unwrap();
        assert_eq!(data["battleRecordRows"].as_array().unwrap().len(), 1);
        assert_eq!(data["battleRecordRows"][0]["evidence_grade"], "B");
        assert_eq!(data["battleRecordRows"][0]["metric_scope"], "floor");
        assert_eq!(data["battleRecordRows"][0]["source_url"], "");
    }

    #[test]
    fn missing_sources_remain_disclosed_in_both_games() {
        for game in ["hsr", "zzz"] {
            let mut data = json!({});
            attach_advice_data(game, &ArtifactBundle::default(), &context(), &mut data).unwrap();
            assert_eq!(
                data["encounterDataQuality"]["public_record_status"],
                "no_verified_records"
            );
            assert!(data["encounterRows"].as_array().unwrap().is_empty());
        }
    }
}
