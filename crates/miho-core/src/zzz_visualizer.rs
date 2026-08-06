use std::collections::{BTreeMap, BTreeSet, HashMap};

use serde_json::{json, Map, Number, Value};

use crate::{
    normalize::character_slug,
    output::ArtifactBundle,
    visualizer::{
        attach_avatar_assets, attach_visualizer_data, attach_zzz_static_assets,
        banner_phase_boundary_fields, effective_banner_status as shared_effective_banner_status,
        local_avatar_url, python_scalar_text, python_value_truthy as python_truthy, read_csv_rows,
        safe_link_url, strict_utf8, validate_json_surrogate_escapes, VisualizerContext,
    },
    zzz_sources::{extract_phase_updates_from_html, parse_official_agents},
    MihoError, Result,
};

type Row = BTreeMap<String, String>;

pub fn attach_zzz_visualizer(
    bundle: &mut ArtifactBundle,
    context: &VisualizerContext,
) -> Result<()> {
    let local_datetime = context.require_local_datetime()?;
    let usage = read_csv_rows(bundle, "character_usage_long.csv")?;
    let tiers = read_csv_rows(bundle, "prydwen_tier_current.csv")?;
    let teams = read_csv_rows(bundle, "team_rank_dedup_unordered.csv")?;
    let names = read_csv_rows(bundle, "name_map.csv")?;
    let changelog = read_csv_rows(bundle, "prydwen_tier_changelog_history.csv")?;
    let phases = read_csv_rows(bundle, "phase_index.csv")?;

    let mut roster = build_roster(bundle, &usage, &tiers, &names, context)?;
    let phase_info = build_phase_info(bundle, &phases, context)?;
    let (mut banner, banner_refresh) = build_banner(bundle, context, &roster, local_datetime)?;
    localize_icons(&mut banner, context);
    merge_banner_into_roster(&mut roster, &banner);
    let team_templates = build_team_templates(&teams, &roster, &names, &phase_info)?;
    let decision_cards = read_object_sidecar(bundle, context, "decision_cards.json")?
        .unwrap_or_else(|| json!({"summary":{},"cards":[]}));
    let data_quality =
        read_bundle_object(bundle, "data_quality.json")?.unwrap_or_else(|| json!({}));
    let freshness = data_quality_freshness(&data_quality);

    let mut data = json!({
        "meta": {
            "game": "绝区零",
            "generatedAt": latest(&tiers, "fetched_at"),
            "tierUpdatedAt": latest(&tiers, "tier_updated_at"),
            "localDate": context.local_date.to_string(),
            "source": "ShiyuDataProcessed + Prydwen ZZZ + HoYoWiki",
        },
        "usageRows": string_rows(&usage),
        "tierRows": string_rows(&tiers),
        "teamTemplates": team_templates,
        "rosterRows": roster,
        "nameRows": string_rows(&names),
        "phaseInfoRows": phase_info,
        "changelogRows": string_rows(&changelog).into_iter().take(80).collect::<Vec<_>>(),
        "bannerRows": banner,
        "decisionMethodVersion": "legacy-v0",
        "decisionCards": decision_cards,
        "data_quality": data_quality,
        "freshness": freshness,
    });
    if let Some(refresh) = banner_refresh {
        data.as_object_mut()
            .expect("visualizer data must be an object")
            .insert("bannerRefresh".into(), refresh);
    }
    sanitize_urls(&mut data, "");
    attach_zzz_static_assets(bundle)?;
    attach_avatar_assets(bundle, context)?;
    attach_visualizer_data(bundle, &data)?;
    Ok(())
}

fn get<'a>(row: &'a Row, key: &str) -> &'a str {
    row.get(key).map(String::as_str).unwrap_or("")
}

fn nonempty<'a>(row: &'a Row, key: &str) -> Option<&'a str> {
    let value = get(row, key);
    (!value.is_empty()).then_some(value)
}

fn value_str<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or("")
}

fn first(values: &[Option<&str>]) -> String {
    values
        .iter()
        .flatten()
        .find(|value| !value.is_empty())
        .copied()
        .unwrap_or("")
        .to_owned()
}

fn latest(rows: &[Row], key: &str) -> String {
    rows.iter()
        .filter_map(|row| nonempty(row, key))
        .max()
        .unwrap_or("")
        .to_owned()
}

fn string_rows(rows: &[Row]) -> Vec<Value> {
    rows.iter()
        .map(|row| {
            Value::Object(
                row.iter()
                    .map(|(key, value)| (key.clone(), Value::String(value.clone())))
                    .collect(),
            )
        })
        .collect()
}

fn read_json_value(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
    path: &str,
) -> Result<Option<Value>> {
    let Some(bytes) = context.sidecar(path).or_else(|| bundle.get(path)) else {
        return Ok(None);
    };
    let text = strict_utf8(bytes, path)?;
    validate_json_surrogate_escapes(text, path)?;
    match serde_json::from_str(text) {
        Ok(mut value) => {
            normalize_python_json_numbers(&mut value, path)?;
            Ok(Some(value))
        }
        Err(_) if contains_non_finite_json(bytes) => Err(MihoError::Visualizer(format!(
            "non-finite JSON constant in {path}"
        ))),
        Err(_) => Ok(None),
    }
}

fn normalize_python_json_numbers(value: &mut Value, path: &str) -> Result<()> {
    match value {
        Value::Object(map) => {
            for item in map.values_mut() {
                normalize_python_json_numbers(item, path)?;
            }
        }
        Value::Array(items) => {
            for item in items {
                normalize_python_json_numbers(item, path)?;
            }
        }
        Value::Number(number) => {
            let token = number.to_string();
            if token.contains(['.', 'e', 'E']) {
                let parsed = token.parse::<f64>().map_err(|_| {
                    MihoError::Visualizer(format!("invalid JSON number {token:?} in {path}"))
                })?;
                if !parsed.is_finite() {
                    return Err(MihoError::Visualizer(format!(
                        "non-finite JSON number {token:?} in {path}"
                    )));
                }
                *number = serde_json::Number::from_f64(parsed).ok_or_else(|| {
                    MihoError::Visualizer(format!("non-finite JSON number {token:?} in {path}"))
                })?;
            } else if token == "-0" {
                *number = serde_json::Number::from(0);
            }
        }
        Value::Null | Value::Bool(_) | Value::String(_) => {}
    }
    Ok(())
}

fn read_object_sidecar(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
    path: &str,
) -> Result<Option<Value>> {
    Ok(read_json_value(bundle, context, path)?.filter(Value::is_object))
}

fn read_bundle_object(bundle: &ArtifactBundle, path: &str) -> Result<Option<Value>> {
    let Some(bytes) = bundle.get(path) else {
        return Ok(None);
    };
    let text = strict_utf8(bytes, path)?;
    validate_json_surrogate_escapes(text, path)?;
    let mut value: Value = serde_json::from_str(text).map_err(|source| MihoError::Json {
        path: path.into(),
        source,
    })?;
    normalize_python_json_numbers(&mut value, path)?;
    Ok(value.is_object().then_some(value))
}

fn data_quality_freshness(data_quality: &Value) -> Value {
    let mut freshness = Map::new();
    if let Some(modes) = data_quality.get("modes").and_then(Value::as_object) {
        for (mode, quality) in modes {
            freshness.insert(
                mode.clone(),
                quality
                    .get("freshness")
                    .filter(|value| value.is_object())
                    .cloned()
                    .unwrap_or_else(|| json!({})),
            );
        }
    }
    Value::Object(freshness)
}

fn read_json_array(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
    path: &str,
) -> Result<Vec<Value>> {
    Ok(read_json_value(bundle, context, path)?
        .and_then(|value| value.as_array().cloned())
        .unwrap_or_default())
}

fn contains_non_finite_json(bytes: &[u8]) -> bool {
    let mut index = 0;
    let mut in_string = false;
    let mut escaped = false;
    while index < bytes.len() {
        let byte = bytes[index];
        if in_string {
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
            index += 1;
            continue;
        }
        for token in [
            b"NaN".as_slice(),
            b"Infinity".as_slice(),
            b"-Infinity".as_slice(),
        ] {
            if bytes.get(index..index + token.len()) == Some(token)
                && json_token_boundary(bytes.get(index.wrapping_sub(1)).copied())
                && json_token_boundary(bytes.get(index + token.len()).copied())
            {
                return true;
            }
        }
        index += 1;
    }
    false
}

fn json_token_boundary(value: Option<u8>) -> bool {
    value.is_none_or(|byte| {
        byte.is_ascii_whitespace() || matches!(byte, b'[' | b']' | b'{' | b'}' | b':' | b',')
    })
}

fn sanitize_urls(value: &mut Value, key: &str) {
    match value {
        Value::Object(map) => {
            for (item_key, item) in map {
                sanitize_urls(item, item_key);
            }
        }
        Value::Array(items) => {
            for item in items {
                sanitize_urls(item, key);
            }
        }
        scalar if key == "icon_url" => {
            *scalar = Value::String(safe_same_origin_url(&python_url_scalar(scalar)))
        }
        scalar if key == "url" || key.ends_with("_url") => {
            *scalar = Value::String(safe_zzz_link_url(&python_url_scalar(scalar)))
        }
        _ => {}
    }
}

fn python_url_scalar(value: &Value) -> String {
    python_scalar_text(Some(value))
}

fn localize_icons(rows: &mut [Value], context: &VisualizerContext) {
    for row in rows {
        let Some(map) = row.as_object_mut() else {
            continue;
        };
        let slug = canonical(
            map.get("character_slug")
                .or_else(|| map.get("character_name_en"))
                .or_else(|| map.get("character_name_cn"))
                .and_then(Value::as_str)
                .unwrap_or(""),
        );
        let current = python_scalar_text(map.get("icon_url"));
        let safe_current = safe_same_origin_url(&current);
        let icon = if !safe_current.is_empty() {
            safe_current
        } else if context.avatar_webp(&slug).is_some() {
            local_avatar_url(context, &slug)
        } else {
            String::new()
        };
        map.insert("icon_url".into(), icon.into());
    }
}

fn safe_zzz_link_url(value: &str) -> String {
    let http = safe_link_url(value);
    if http
        .split_once(':')
        .is_some_and(|(scheme, _)| matches!(scheme.to_ascii_lowercase().as_str(), "http" | "https"))
    {
        http
    } else {
        safe_same_origin_url(value)
    }
}

fn safe_same_origin_url(value: &str) -> String {
    let text = value.trim();
    if text.is_empty()
        || text.starts_with('/')
        || text.contains('\\')
        || text.chars().any(|ch| ch.is_control() || ch == '\u{7f}')
    {
        return String::new();
    }
    let path = text.split(['?', '#']).next().unwrap_or("");
    if path.contains(':') {
        return String::new();
    }
    let mut decoded = path.to_owned();
    for _ in 0..3 {
        let next = percent_decode(&decoded);
        if next == decoded {
            break;
        }
        decoded = next;
    }
    if decoded.is_empty() || matches!(decoded.as_str(), "." | "/") || decoded.contains('\\') {
        return String::new();
    }
    for (index, segment) in decoded.split('/').enumerate() {
        if segment == ".." || (segment == "." && !(index == 0 && text.starts_with("./"))) {
            return String::new();
        }
    }
    text.to_owned()
}

fn percent_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            if let (Some(high), Some(low)) =
                (hex_value(bytes[index + 1]), hex_value(bytes[index + 2]))
            {
                output.push((high << 4) | low);
                index += 3;
                continue;
            }
        }
        output.push(bytes[index]);
        index += 1;
    }
    String::from_utf8_lossy(&output).into_owned()
}

fn hex_value(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

fn build_phase_info(
    bundle: &ArtifactBundle,
    phases: &[Row],
    context: &VisualizerContext,
) -> Result<Vec<Value>> {
    let mut updates = HashMap::<(String, String), (String, String)>::new();
    for mode in ["sd", "da"] {
        let path = format!("raw/prydwen/{mode}.html");
        let Some(bytes) = bundle.get(&path) else {
            continue;
        };
        let html = strict_utf8(bytes, &path)?;
        for (version, update) in extract_phase_updates_from_html(html) {
            updates.insert((mode.into(), version), (update.collect_date, update.users));
        }
    }
    let overrides = phase_overrides(bundle, context)?;
    let official_phases = official_endgame_phases(bundle, context)?;
    Ok(phases
        .iter()
        .map(|row| {
            let mode = get(row, "mode");
            let version = get(row, "phase_ver");
            let snapshot_id = get(row, "snapshot_id");
            let update = updates.get(&(mode.into(), version.into()));
            let override_row = overrides.get(mode, version, snapshot_id);
            let override_str = |key| override_row.and_then(|value| value.get(key)).and_then(Value::as_str).unwrap_or("");
            let collect_date = first(&[
                nonempty(row, "collect_date"),
                (!override_str("collect_date").is_empty()).then(|| override_str("collect_date")),
                update.map(|value| value.0.as_str()).filter(|value| !value.is_empty()),
            ]);
            let start = first(&[
                nonempty(row, "start_date"),
                (!override_str("start_date").is_empty()).then(|| override_str("start_date")),
            ]);
            let end = first(&[
                nonempty(row, "end_date"),
                (!override_str("end_date").is_empty()).then(|| override_str("end_date")),
            ]);
            let source_limited = get(row, "collect_date").is_empty()
                && update.is_some_and(|value| !value.0.is_empty());
            let (mechanic_text, mechanic_source) = if source_limited && start.is_empty() && end.is_empty() {
                (format!("采样日期 {collect_date} 来自 Prydwen 可见 phase；Hugging Face config 尚未写入本周期起止日期。推荐只使用同模式、同关卡的当前最新队伍模板，周期边界按源限制处理。"), "Prydwen phase selector + ShiyuDataProcessed".to_owned())
            } else if override_row.is_some() {
                (format!("采样日期 {}；周期 {} 至 {}。起止来自手动联网 override，用于弥补上游 config 缺失。", unknown(&collect_date), unknown(&start), unknown(&end)), first(&[(!override_str("source_label").is_empty()).then(|| override_str("source_label")), Some("manual online override")]))
            } else {
                (format!("采样日期 {}；周期 {} 至 {}。推荐只使用同模式、同关卡的当前最新队伍模板。", unknown(&collect_date), unknown(&start), unknown(&end)), "ShiyuDataProcessed config.json".to_owned())
            };
            let mode_cn_value = first(&[nonempty(row, "mode_cn"), Some(mode_cn(mode))]);
            let phase_name = first(&[
                nonempty(row, "phase_name"),
                Some(format!("{mode_cn_value} {version}").trim()),
            ]);
            let official = official_phases.get(&(
                mode.to_owned(),
                snapshot_id.to_owned(),
                version.to_owned(),
                start.clone(),
                end.clone(),
            ));
            let official_str = |key| {
                official
                    .and_then(|value| value.get(key))
                    .and_then(Value::as_str)
                    .filter(|value| !value.trim().is_empty())
            };
            let phase_name_cn = first(&[official_str("phase_name_cn"), Some(&phase_name)]);
            let mechanic_name = first(&[official_str("mechanic_name"), Some("当期数据")]);
            let mechanic_text = first(&[official_str("mechanic_text"), Some(&mechanic_text)]);
            let mechanic_source = first(&[
                official_str("source_label"),
                Some(&mechanic_source),
            ]);
            let mechanic_url = official_str("source_url")
                .map(|value| Value::String(value.to_owned()))
                .unwrap_or_else(|| {
                    override_row
                        .and_then(|value| value.get("source_url"))
                        .cloned()
                        .unwrap_or_else(|| Value::String(String::new()))
                });
            json!({
                "snapshot_id": get(row,"snapshot_id"), "collect_date":collect_date,
                "mode":mode, "mode_cn":mode_cn_value, "phase_ver":version,
                "phase_name":phase_name, "phase_name_cn":phase_name_cn,
                "start_date":start, "end_date":end, "mechanic_name":mechanic_name,
                "mechanic_text":mechanic_text, "mechanic_source":mechanic_source,
                "mechanic_url":mechanic_url,
                "phase_status":phase_status(&start,&end,context),
                "source_limited":source_limited,
                "source_note":first(&[(!override_str("note").is_empty()).then(||override_str("note")), nonempty(row,"note")]),
            })
        })
        .collect())
}

#[derive(Default)]
struct PhaseOverrides {
    exact: HashMap<(String, String, String), Value>,
    legacy: HashMap<(String, String), Value>,
}

impl PhaseOverrides {
    fn get(&self, mode: &str, phase_ver: &str, snapshot_id: &str) -> Option<&Value> {
        self.exact
            .get(&(
                mode.to_owned(),
                phase_ver.to_owned(),
                snapshot_id.to_owned(),
            ))
            .or_else(|| self.legacy.get(&(mode.to_owned(), phase_ver.to_owned())))
    }
}

fn phase_overrides(bundle: &ArtifactBundle, context: &VisualizerContext) -> Result<PhaseOverrides> {
    let Some(value) = read_json_value(bundle, context, "zzz_endgame_phase_overrides.json")? else {
        return Ok(PhaseOverrides::default());
    };
    let rows = if let Some(rows) = value.get("phases").and_then(Value::as_array) {
        rows.clone()
    } else {
        value.as_array().cloned().unwrap_or_default()
    };
    let mut overrides = PhaseOverrides::default();
    for row in rows {
        let mode = value_str(&row, "mode").to_owned();
        let phase_ver = value_str(&row, "phase_ver").to_owned();
        if mode.is_empty() || phase_ver.is_empty() {
            continue;
        }
        let snapshot_id = value_str(&row, "snapshot_id").to_owned();
        if snapshot_id.is_empty() {
            overrides.legacy.insert((mode, phase_ver), row);
        } else {
            overrides.exact.insert((mode, phase_ver, snapshot_id), row);
        }
    }
    Ok(overrides)
}

type OfficialPhaseIdentity = (String, String, String, String, String);

fn official_endgame_phases(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
) -> Result<HashMap<OfficialPhaseIdentity, Value>> {
    let Some(value) = read_json_value(bundle, context, "zzz_official_endgame_phases.json")? else {
        return Ok(HashMap::new());
    };
    let Some(rows) = value.get("phases").and_then(Value::as_array) else {
        return Ok(HashMap::new());
    };
    let mut phases = HashMap::new();
    for row in rows {
        let Some(identity) = row.get("identity").filter(|value| value.is_object()) else {
            continue;
        };
        let key = (
            value_str(identity, "mode").to_owned(),
            value_str(identity, "snapshot_id").to_owned(),
            value_str(identity, "phase_ver").to_owned(),
            value_str(identity, "start_date").to_owned(),
            value_str(identity, "end_date").to_owned(),
        );
        if [&key.0, &key.1, &key.2, &key.3, &key.4]
            .into_iter()
            .any(|value| value.is_empty())
            || [
                "phase_name_cn",
                "mechanic_name",
                "mechanic_text",
                "source_label",
                "source_url",
            ]
            .into_iter()
            .any(|field| {
                row.get(field)
                    .and_then(Value::as_str)
                    .is_none_or(|value| value.trim().is_empty())
            })
        {
            continue;
        }
        phases.insert(key, row.clone());
    }
    Ok(phases)
}

fn unknown(value: &str) -> &str {
    if value.is_empty() {
        "未知"
    } else {
        value
    }
}

fn phase_status(start: &str, end: &str, context: &VisualizerContext) -> &'static str {
    let parse = |value: &str| {
        chrono::NaiveDate::parse_from_str(value.get(..10).unwrap_or(value), "%Y-%m-%d").ok()
    };
    if parse(end).is_some_and(|date| date < context.local_date) {
        "expired"
    } else if parse(start).is_some_and(|date| date > context.local_date) {
        "future"
    } else if parse(start).is_some() || parse(end).is_some() {
        "current"
    } else {
        "unknown"
    }
}

#[derive(Clone, Default)]
struct OfficialMeta {
    name_en: String,
    name_cn: String,
    element_en: String,
    element_cn: String,
    style_en: String,
    style_cn: String,
    rarity: String,
    icon_url: String,
    release_order: usize,
}

fn build_roster(
    bundle: &ArtifactBundle,
    usage: &[Row],
    tiers: &[Row],
    names: &[Row],
    context: &VisualizerContext,
) -> Result<Vec<Value>> {
    let name_map = names
        .iter()
        .map(|row| (canonical(get(row, "character_slug")), row))
        .collect::<HashMap<_, _>>();
    let official = official_roster(bundle, context)?;
    let mut tier_meta = HashMap::<String, &Row>::new();
    for row in tiers {
        let slug = canonical(get(row, "character_slug"));
        if slug.is_empty() {
            continue;
        }
        if tier_meta
            .get(&slug)
            .is_none_or(|current| tier_rank(get(row, "tier")) < tier_rank(get(current, "tier")))
        {
            tier_meta.insert(slug, row);
        }
    }
    let mut usage_meta = HashMap::<String, &Row>::new();
    for row in usage {
        let slug = canonical(get(row, "character_slug"));
        if !slug.is_empty() && get(row, "sub_mode") == "all" {
            usage_meta.entry(slug).or_insert(row);
        }
    }
    let mut slugs = BTreeSet::new();
    slugs.extend(tier_meta.keys().cloned());
    slugs.extend(usage_meta.keys().cloned());
    for row in names
        .iter()
        .filter(|row| first(&[nonempty(row, "kind"), Some("agent")]) == "agent")
    {
        let slug = canonical(get(row, "character_slug"));
        if !slug.is_empty() {
            slugs.insert(slug);
        }
    }
    let mut output = Vec::new();
    for (index, slug) in slugs.into_iter().enumerate() {
        let tier = tier_meta.get(&slug).copied();
        let usage_row = usage_meta.get(&slug).copied();
        let name = name_map.get(&slug).copied();
        let official_row = official.get(&slug);
        let official_value =
            |field: fn(&OfficialMeta) -> &str| official_row.map(field).unwrap_or("");
        let element = first(&[
            tier.and_then(|row| nonempty(row, "element")),
            usage_row.and_then(|row| nonempty(row, "element")),
            (!official_value(|row| &row.element_en).is_empty())
                .then(|| official_value(|row| &row.element_en)),
        ]);
        let style = first(&[
            tier.and_then(|row| nonempty(row, "style")),
            (!official_value(|row| &row.style_en).is_empty())
                .then(|| official_value(|row| &row.style_en)),
        ]);
        let role = first(&[
            tier.and_then(|row| nonempty(row, "role_group")),
            Some(role_from_style(&style)),
        ]);
        let release_order = if let Some(value) = name.and_then(|row| nonempty(row, "release_order"))
        {
            numeric_float(value).unwrap_or(Value::Null)
        } else if let Some(value) = official_row.map(|row| row.release_order) {
            Number::from_f64(value as f64).map_or(Value::Null, Value::Number)
        } else {
            Value::from(9999 + index)
        };
        output.push(json!({
            "character_slug":slug,
            "character_name_en":first(&[name.and_then(|row|nonempty(row,"character_name_en")),tier.and_then(|row|nonempty(row,"character_name_en")),usage_row.and_then(|row|nonempty(row,"character_name_en")),(!official_value(|row|&row.name_en).is_empty()).then(||official_value(|row|&row.name_en)),Some(&slug)]),
            "character_name_cn":first(&[name.and_then(|row|nonempty(row,"character_name_cn")),(!official_value(|row|&row.name_cn).is_empty()).then(||official_value(|row|&row.name_cn))]),
            "element_en":element,
            "element_cn":first(&[tier.and_then(|row|nonempty(row,"element_cn")),(!official_value(|row|&row.element_cn).is_empty()).then(||official_value(|row|&row.element_cn)),Some(element_cn(&element))]),
            "style_en":style,
            "style_cn":first(&[tier.and_then(|row|nonempty(row,"style_cn")),(!official_value(|row|&row.style_cn).is_empty()).then(||official_value(|row|&row.style_cn)),Some(style_cn(&style))]),
            "role_group":role,
            "role_group_cn":first(&[tier.and_then(|row|nonempty(row,"role_group_cn")),Some(role_cn(&role))]),
            "rarity":first(&[tier.and_then(|row|nonempty(row,"rarity")),usage_row.and_then(|row|nonempty(row,"rarity")),(!official_value(|row|&row.rarity).is_empty()).then(||official_value(|row|&row.rarity))]),
            "tier":first(&[tier.and_then(|row|nonempty(row,"tier")),Some("未分档")]),
            "rating":tier.map(|row|get(row,"rating")).unwrap_or(""),
            "tags":tier.map(|row|get(row,"tags")).unwrap_or(""),
            "icon_url":first(&[tier.and_then(|row|nonempty(row,"icon_url")),(!official_value(|row|&row.icon_url).is_empty()).then(||official_value(|row|&row.icon_url))]),
            "release_order":release_order,
        }));
    }
    localize_icons(&mut output, context);
    output.sort_by(|left, right| {
        release_order(left)
            .total_cmp(&release_order(right))
            .then_with(|| value_str(left, "character_slug").cmp(value_str(right, "character_slug")))
    });
    Ok(output)
}

fn official_roster(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
) -> Result<HashMap<String, OfficialMeta>> {
    let zh = read_json_array(bundle, context, "raw/hoyowiki/zzz_agents_zh-cn.json")?;
    let en = read_json_array(bundle, context, "raw/hoyowiki/zzz_agents_en-us.json")?;
    Ok(parse_official_agents(&en, &zh)
        .into_iter()
        .map(|row| {
            (
                row.character_slug,
                OfficialMeta {
                    name_en: row.character_name_en,
                    name_cn: row.character_name_cn,
                    element_en: row.element_en,
                    element_cn: row.element_cn.trim_end_matches("属性").to_owned(),
                    style_en: row.style_en,
                    style_cn: row.style_cn,
                    rarity: row.rarity,
                    icon_url: row.icon_url,
                    release_order: row.release_order,
                },
            )
        })
        .collect())
}

fn json_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Bool(false)) => "False".into(),
        Some(Value::Null) | None => String::new(),
        Some(value) => value.to_string(),
    }
}

fn build_team_templates(
    teams: &[Row],
    roster: &[Value],
    names: &[Row],
    phases: &[Value],
) -> Result<Vec<Value>> {
    let roster_map = roster
        .iter()
        .map(|row| (value_str(row, "character_slug"), row))
        .collect::<HashMap<_, _>>();
    let name_map = names
        .iter()
        .map(|row| (canonical(get(row, "character_slug")), row))
        .collect::<HashMap<_, _>>();
    let mut phase_dates = HashMap::<(String, String), String>::new();
    for row in phases {
        if !value_str(row, "collect_date").is_empty() {
            phase_dates.insert(
                (
                    value_str(row, "mode").into(),
                    value_str(row, "phase_ver").into(),
                ),
                value_str(row, "collect_date").into(),
            );
        }
    }
    let mut latest = HashMap::<String, (Vec<u64>, String)>::new();
    for row in teams {
        let mode = get(row, "mode");
        let recency = team_recency(row, &phase_dates);
        if !mode.is_empty() && latest.get(mode).is_none_or(|current| recency >= *current) {
            latest.insert(mode.into(), recency);
        }
    }
    let mut grouped = Vec::<Vec<Value>>::new();
    let mut grouped_indices = HashMap::<String, usize>::new();
    for row in teams {
        let mode = get(row, "mode");
        if mode.is_empty() || latest.get(mode) != Some(&team_recency(row, &phase_dates)) {
            continue;
        }
        let chars = (1..=3)
            .map(|index| canonical(get(row, &format!("char_{index}_slug"))))
            .collect::<Vec<_>>();
        if chars.iter().any(String::is_empty) {
            continue;
        }
        let mut signature = chars.clone();
        signature.sort();
        let key = format!("{mode}|{}|{}", get(row, "sub_mode"), signature.join(">"));
        let collect_date = first(&[
            nonempty(row, "collect_date"),
            phase_dates
                .get(&(mode.into(), get(row, "phase_ver").into()))
                .map(String::as_str),
        ]);
        let bangboo = canonical(get(row, "bangboo_slug"));
        let stability_component = chars.iter().any(|slug| {
            roster_map
                .get(slug.as_str())
                .and_then(|value| value.get("role_group"))
                .and_then(Value::as_str)
                .is_some_and(|role| role == "support")
        });
        let mut template = json!({
            "mode":mode,"mode_cn":first(&[nonempty(row,"mode_cn"),Some(mode_cn(mode))]),
            "scope_key":first(&[nonempty(row,"sub_mode"),Some("all")]),
            "scope_label":first(&[nonempty(row,"sub_mode_cn"),nonempty(row,"sub_mode"),Some("全部")]),
            "collect_date":collect_date,"phase_ver":get(row,"phase_ver"),"phase_name":get(row,"phase_name"),
            "rank":numeric_float(get(row,"rank"))?,"app_rate":numeric_float(get(row,"app_rate"))?,"avg_score":numeric_float(get(row,"avg_score"))?,
            "bangboo":bangboo,"bangboo_name":first(&[nonempty(row,"bangboo_name_cn"),name_map.get(&bangboo).and_then(|row|nonempty(row,"character_name_cn"))]),
            "source_kind":get(row,"source_kind"),
            "merged_source_kinds":first(&[nonempty(row,"merged_source_kinds"),nonempty(row,"source_kind")]),
            "source_file":get(row,"source_file"),
            "source_url":get(row,"source_url"),
            "merged_source_files":first(&[nonempty(row,"merged_source_files"),nonempty(row,"source_file")]),
            "quality_flag":get(row,"quality_flag"),
            "duplicate_count":evidence_duplicate_count(get(row,"duplicate_count")),
            "stability_component":stability_component,
            "recency_key":team_recency_key(row,&phase_dates),
            "chars":chars,"names_cn":chars.iter().map(|slug|roster_map.get(slug.as_str()).map(|row|first(&[nonempty_value(row,"character_name_cn"),nonempty_value(row,"character_name_en"),Some(slug)])).unwrap_or_else(||slug.clone())).collect::<Vec<_>>(),
        });
        refresh_zzz_evidence(&mut template);
        if let Some(index) = grouped_indices.get(&key).copied() {
            grouped[index].push(template);
        } else {
            grouped_indices.insert(key, grouped.len());
            grouped.push(vec![template]);
        }
    }
    let mut output = grouped
        .into_iter()
        .map(finalize_zzz_template_group)
        .collect::<Vec<_>>();
    output.sort_by(|left, right| {
        value_str(left, "mode")
            .cmp(value_str(right, "mode"))
            .then_with(|| value_str(left, "scope_key").cmp(value_str(right, "scope_key")))
            .then_with(|| zzz_template_cmp(left, right))
    });
    Ok(output)
}

fn nonempty_value<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    let value = value_str(value, key);
    (!value.is_empty()).then_some(value)
}

fn python_or_value(values: &[Option<&Value>]) -> Value {
    values
        .iter()
        .flatten()
        .find(|value| python_truthy(value))
        .map(|value| (*value).clone())
        .unwrap_or_else(|| Value::String(String::new()))
}
fn evidence_duplicate_count(value: &str) -> u64 {
    value.trim().parse::<u64>().unwrap_or(1).max(1)
}
fn template_duplicate_count(value: &Value) -> u64 {
    value
        .get("duplicate_count")
        .and_then(Value::as_u64)
        .unwrap_or(1)
        .max(1)
}
fn merged_evidence_values<'a>(values: impl IntoIterator<Item = &'a str>) -> String {
    values
        .into_iter()
        .flat_map(|value| value.split(';'))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>()
        .join(";")
}
fn evidence_quality_allows_a(value: &str) -> bool {
    value.split(';').map(str::trim).all(|flag| {
        flag.is_empty()
            || matches!(
                flag.to_ascii_lowercase().as_str(),
                "ok" | "valid" | "complete" | "clean"
            )
    })
}
fn positive_template_number(value: &Value, key: &str) -> Option<f64> {
    value
        .get(key)
        .and_then(Value::as_f64)
        .filter(|number| number.is_finite() && *number > 0.0)
}
fn refresh_zzz_evidence(template: &mut Value) {
    let count = template_duplicate_count(template);
    let mut limitations = Vec::new();
    if count < 2 {
        limitations.push("仅 1 条记录");
    }
    if positive_template_number(template, "rank").is_none() {
        limitations.push("Rank 缺失");
    }
    if positive_template_number(template, "app_rate").is_none() {
        limitations.push("占比缺失");
    }
    if positive_template_number(template, "avg_score").is_none() {
        limitations.push("表现缺失或为 sentinel");
    }
    if value_str(template, "merged_source_kinds").is_empty()
        || value_str(template, "merged_source_files").is_empty()
    {
        limitations.push("来源字段不完整");
    }
    if !evidence_quality_allows_a(value_str(template, "quality_flag")) {
        limitations.push("质量标记限制");
    }
    if !template
        .get("stability_component")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        limitations.push("缺少已知稳定组件");
    }
    let (grade, comment) = if limitations.is_empty() {
        (
            "A",
            format!("重复记录 {count} 条，Rank、占比、表现与来源字段完整。"),
        )
    } else {
        (
            "B",
            format!("真实队伍记录；保守按 B：{}。", limitations.join("；")),
        )
    };
    let object = template.as_object_mut().expect("team template is object");
    object.insert("evidence_grade".into(), grade.into());
    object.insert("evidence_comment".into(), comment.into());
}
fn finalize_zzz_template_group(mut templates: Vec<Value>) -> Value {
    templates.sort_by(zzz_template_cmp);
    let duplicate_count = templates
        .iter()
        .map(template_duplicate_count)
        .max()
        .unwrap_or(1);
    let source_files = merged_evidence_values(templates.iter().flat_map(|template| {
        [
            value_str(template, "merged_source_files"),
            value_str(template, "source_file"),
        ]
    }));
    let source_kinds = merged_evidence_values(templates.iter().flat_map(|template| {
        [
            value_str(template, "merged_source_kinds"),
            value_str(template, "source_kind"),
        ]
    }));
    let quality_flags = merged_evidence_values(
        templates
            .iter()
            .map(|template| value_str(template, "quality_flag")),
    );
    let mut selected = templates
        .into_iter()
        .next()
        .expect("team template group is non-empty");
    let object = selected.as_object_mut().expect("team template is object");
    object.insert("duplicate_count".into(), duplicate_count.into());
    object.insert("merged_source_files".into(), source_files.into());
    object.insert("merged_source_kinds".into(), source_kinds.into());
    object.insert("quality_flag".into(), quality_flags.into());
    refresh_zzz_evidence(&mut selected);
    selected
}
fn zzz_template_cmp(left: &Value, right: &Value) -> std::cmp::Ordering {
    positive_template_number(left, "rank")
        .unwrap_or(f64::INFINITY)
        .total_cmp(&positive_template_number(right, "rank").unwrap_or(f64::INFINITY))
        .then_with(|| {
            positive_template_number(right, "app_rate")
                .unwrap_or(-1.0)
                .total_cmp(&positive_template_number(left, "app_rate").unwrap_or(-1.0))
        })
        .then_with(|| {
            positive_template_number(right, "avg_score")
                .unwrap_or(-1.0)
                .total_cmp(&positive_template_number(left, "avg_score").unwrap_or(-1.0))
        })
        .then_with(|| template_duplicate_count(right).cmp(&template_duplicate_count(left)))
        .then_with(|| value_str(left, "source_kind").cmp(value_str(right, "source_kind")))
        .then_with(|| value_str(left, "source_file").cmp(value_str(right, "source_file")))
        .then_with(|| value_str(left, "bangboo").cmp(value_str(right, "bangboo")))
        .then_with(|| value_str(left, "phase_ver").cmp(value_str(right, "phase_ver")))
        .then_with(|| value_str(left, "phase_name").cmp(value_str(right, "phase_name")))
        .then_with(|| template_chars_key(left).cmp(&template_chars_key(right)))
}
fn template_chars_key(value: &Value) -> String {
    value
        .get("chars")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect::<Vec<_>>()
        .join(">")
}
fn team_recency(row: &Row, phase_dates: &HashMap<(String, String), String>) -> (Vec<u64>, String) {
    let version = first_nonempty_version(&[
        get(row, "snapshot_id"),
        source_snapshot(get(row, "source_file")),
        get(row, "phase_ver"),
    ]);
    let date = first(&[
        nonempty(row, "collect_date"),
        phase_dates
            .get(&(get(row, "mode").into(), get(row, "phase_ver").into()))
            .map(String::as_str),
    ]);
    (version, date)
}
fn team_recency_key(row: &Row, phase_dates: &HashMap<(String, String), String>) -> String {
    let (version, date) = team_recency(row, phase_dates);
    format!(
        "{}|{date}",
        version
            .iter()
            .map(|part| format!("{part:04}"))
            .collect::<Vec<_>>()
            .join(".")
    )
}
fn source_snapshot(value: &str) -> &str {
    value.split_once('/').map(|value| value.0).unwrap_or("")
}
fn first_nonempty_version(values: &[&str]) -> Vec<u64> {
    values
        .iter()
        .map(|value| version_tuple(value))
        .find(|value| !value.is_empty())
        .unwrap_or_else(|| vec![0])
}
fn version_tuple(value: &str) -> Vec<u64> {
    let mut output = Vec::new();
    let mut digits = String::new();
    for ch in value.chars() {
        if ch.is_ascii_digit() {
            digits.push(ch)
        } else if !digits.is_empty() {
            output.push(digits.parse().unwrap_or(0));
            digits.clear()
        }
    }
    if !digits.is_empty() {
        output.push(digits.parse().unwrap_or(0))
    }
    output
}
fn numeric_float(value: &str) -> Result<Value> {
    if value.is_empty() {
        return Ok(Value::Null);
    };
    let Ok(number) = value.parse::<f64>() else {
        return Ok(Value::Null);
    };
    if !number.is_finite() {
        return Err(MihoError::Visualizer(format!(
            "non-finite visualizer number: {value:?}"
        )));
    }
    Ok(Number::from_f64(number).map_or(Value::Null, Value::Number))
}

fn build_banner(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
    roster: &[Value],
    local_datetime: chrono::NaiveDateTime,
) -> Result<(Vec<Value>, Option<Value>)> {
    let Some(root) = read_object_sidecar(bundle, context, "zzz_banner_plan.json")? else {
        return Ok((vec![], None));
    };
    let refresh = banner_refresh(&root);
    let roster_map = roster
        .iter()
        .map(|row| (value_str(row, "character_slug"), row))
        .collect::<HashMap<_, _>>();
    let mut output = Vec::new();
    for phase in root
        .get("phases")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let declared = value_str(phase, "status").trim().to_ascii_lowercase();
        let status = shared_effective_banner_status(phase, local_datetime)?;
        let (phase_starts_at, phase_ends_at_exclusive) = banner_phase_boundary_fields(phase)?;
        for (index, ch) in phase
            .get("characters")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let slug = canonical(value_str(ch, "slug"));
            if slug.is_empty() {
                continue;
            }
            let info = roster_map.get(slug.as_str()).copied();
            let cv = |key| value_str(ch, key);
            let pv = |key| value_str(phase, key);
            output.push(json!({
                "phase_id":pv("id"),"phase_status":status,"declared_phase_status":declared,
                "phase_title":pv("title"),"phase_subtitle":pv("subtitle"),"date_range":pv("date_range"),
                "phase_starts_at":phase_starts_at,"phase_ends_at_exclusive":phase_ends_at_exclusive,
                "source_label":python_or_value(&[ch.get("source_label"),phase.get("source_label")]),
                "source_url":python_or_value(&[ch.get("source_url"),phase.get("source_url")]),"slot":index+1,
                "character_slug":slug,"character_name_cn":first(&[nonempty_value(ch,"name_cn"),info.and_then(|row|nonempty_value(row,"character_name_cn"))]),
                "character_name_en":first(&[nonempty_value(ch,"name_en"),info.and_then(|row|nonempty_value(row,"character_name_en"))]),
                "banner_role":cv("banner_role"),"rarity":first(&[nonempty_value(ch,"rarity"),info.and_then(|row|nonempty_value(row,"rarity"))]),
                "element_cn":first(&[nonempty_value(ch,"element_cn"),info.and_then(|row|nonempty_value(row,"element_cn"))]),
                "style_cn":first(&[nonempty_value(ch,"style_cn"),info.and_then(|row|nonempty_value(row,"style_cn"))]),
                "role_group_cn":first(&[nonempty_value(ch,"role_group_cn"),info.and_then(|row|nonempty_value(row,"role_group_cn"))]),
                "icon_url":python_or_value(&[ch.get("icon_url"),info.and_then(|row|row.get("icon_url"))]),
                "icon_crop":ch.get("icon_crop").filter(|value|python_truthy(value)).or_else(||ch.get("avatar_crop").filter(|value|python_truthy(value))).cloned().unwrap_or(Value::String(String::new())),
                "icon_source_label":python_or_value(&[ch.get("icon_source_label")]),"icon_source_url":python_or_value(&[ch.get("icon_source_url")]),
                "analysis_tags":ch.get("analysis_tags").filter(|value|python_truthy(value)).cloned().unwrap_or_else(||json!([])),"focus":cv("focus"),
            }));
        }
    }
    Ok((output, refresh))
}

fn banner_refresh(root: &Value) -> Option<Value> {
    let refresh = root.get("refresh")?.as_object()?;
    let status = refresh.get("status")?.as_str()?.trim();
    let fetched_at = refresh.get("fetched_at")?.as_str()?.trim();
    if status.is_empty() || fetched_at.is_empty() {
        return None;
    }
    Some(json!({
        "status": status,
        "fetched_at": fetched_at,
        "source_label": refresh
            .get("source_label")
            .and_then(Value::as_str)
            .unwrap_or(""),
    }))
}

fn merge_banner_into_roster(roster: &mut Vec<Value>, banner: &[Value]) {
    let original_slugs = roster
        .iter()
        .filter_map(|row| {
            let slug = value_str(row, "character_slug");
            (!slug.is_empty()).then_some(slug.to_owned())
        })
        .collect::<BTreeSet<_>>();
    let mut by_slug = roster
        .drain(..)
        .filter_map(|row| {
            let slug = value_str(&row, "character_slug").to_owned();
            (!slug.is_empty()).then_some((slug, row))
        })
        .collect::<BTreeMap<_, _>>();
    let mut banner_only_slugs = Vec::new();
    let mut next_order = by_slug.values().map(release_order).fold(0.0, f64::max) + 1.0;
    for banner_row in banner {
        let slug = canonical(value_str(banner_row, "character_slug"));
        if slug.is_empty() {
            continue;
        }
        if !by_slug.contains_key(&slug) {
            let style_cn_value = value_str(banner_row, "style_cn");
            let role = role_from_style_cn(style_cn_value);
            let tags = banner_row
                .get("analysis_tags")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .map(|value| json_text(Some(value)))
                        .collect::<Vec<_>>()
                        .join(";")
                })
                .unwrap_or_default();
            by_slug.insert(slug.clone(),json!({
                "character_slug":slug,"character_name_en":first(&[nonempty_value(banner_row,"character_name_en"),Some(&slug)]),
                "character_name_cn":value_str(banner_row,"character_name_cn"),"element_en":value_str(banner_row,"element_en"),"element_cn":value_str(banner_row,"element_cn"),
                "style_en":value_str(banner_row,"style_en"),"style_cn":style_cn_value,"role_group":role,
                "role_group_cn":first(&[nonempty_value(banner_row,"role_group_cn"),Some(role_cn(role))]),"rarity":value_str(banner_row,"rarity"),
                "tier":"未分档","rating":"","tags":tags,"icon_url":value_str(banner_row,"icon_url"),"release_order":next_order,
                "source":"banner_plan","banner_statuses":value_str(banner_row,"phase_status"),"banner_phase_titles":value_str(banner_row,"phase_title"),
            }));
            banner_only_slugs.push(slug);
            next_order += 1.0;
            continue;
        }
        let existing = by_slug
            .get_mut(&slug)
            .and_then(Value::as_object_mut)
            .expect("roster is object");
        merge_semicolon(
            existing,
            "banner_statuses",
            value_str(banner_row, "phase_status"),
        );
        merge_semicolon(
            existing,
            "banner_phase_titles",
            value_str(banner_row, "phase_title"),
        );
        for key in [
            "character_name_en",
            "character_name_cn",
            "element_en",
            "element_cn",
            "style_en",
            "style_cn",
            "role_group",
            "role_group_cn",
            "rarity",
            "icon_url",
        ] {
            if existing
                .get(key)
                .and_then(Value::as_str)
                .unwrap_or("")
                .is_empty()
            {
                if let Some(value) = banner_row.get(key).filter(|value| python_truthy(value)) {
                    existing.insert(key.into(), value.clone());
                }
            }
        }
        if existing
            .get("role_group")
            .and_then(Value::as_str)
            .unwrap_or("")
            .is_empty()
        {
            let role = role_from_style_cn(
                existing
                    .get("style_cn")
                    .and_then(Value::as_str)
                    .unwrap_or(""),
            );
            existing.insert("role_group".into(), role.into());
            if existing
                .get("role_group_cn")
                .and_then(Value::as_str)
                .unwrap_or("")
                .is_empty()
            {
                existing.insert("role_group_cn".into(), role_cn(role).into());
            }
        }
    }

    let mut published = by_slug
        .values()
        .filter(|row| original_slugs.contains(value_str(row, "character_slug")))
        .cloned()
        .collect::<Vec<_>>();
    published.sort_by(|left, right| {
        release_order(left)
            .total_cmp(&release_order(right))
            .then_with(|| value_str(left, "character_slug").cmp(value_str(right, "character_slug")))
    });

    let mut future = Vec::new();
    let mut current = Vec::new();
    let mut undated_history = Vec::new();
    for slug in banner_only_slugs {
        let Some(row) = by_slug.get(&slug).cloned() else {
            continue;
        };
        if has_banner_status(&row, "next") || has_banner_status(&row, "satellite") {
            future.push(row);
        } else if has_banner_status(&row, "current") {
            current.push(row);
        } else {
            undated_history.push(row);
        }
    }

    future.extend(current);
    future.extend(published);
    future.extend(undated_history);
    for (index, row) in future.iter_mut().enumerate() {
        row.as_object_mut()
            .expect("roster is object")
            .insert("release_order".into(), index.into());
    }
    *roster = future;
}

fn has_banner_status(row: &Value, expected: &str) -> bool {
    value_str(row, "banner_statuses")
        .split(';')
        .any(|status| status == expected)
}

fn merge_semicolon(map: &mut Map<String, Value>, key: &str, value: &str) {
    if value.trim().is_empty() {
        return;
    }
    let mut values = map
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("")
        .split(';')
        .filter(|item| !item.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    if !values.iter().any(|item| item == value) {
        values.push(value.into())
    }
    map.insert(key.into(), values.join(";").into());
}

fn release_order(value: &Value) -> f64 {
    value
        .get("release_order")
        .and_then(Value::as_f64)
        .unwrap_or(9999.0)
}
fn tier_rank(value: &str) -> f64 {
    match value {
        "T0" => 0.0,
        "T0.5" => 0.5,
        "T1" => 1.0,
        "T1.5" => 1.5,
        "T2" => 2.0,
        "T3" => 3.0,
        "T4" => 4.0,
        "T5" => 5.0,
        _ => 99.0,
    }
}
fn role_from_style(value: &str) -> &'static str {
    match value {
        "Attack" | "Rupture" => "crit_dps",
        "Anomaly" => "anomaly_dps",
        "Support" | "Stun" | "Defence" | "Defense" => "support",
        _ => "unknown",
    }
}
fn role_from_style_cn(value: &str) -> &'static str {
    match value {
        "强攻" | "命破" => "crit_dps",
        "异常" => "anomaly_dps",
        "支援" | "击破" | "防护" => "support",
        _ => "unknown",
    }
}
fn role_cn(value: &str) -> &'static str {
    match value {
        "crit_dps" => "直伤主C",
        "anomaly_dps" => "异常主C",
        "support" => "辅助",
        _ => "未分类",
    }
}
fn mode_cn(value: &str) -> &str {
    match value {
        "sd" => "式舆防卫",
        "da" => "危局强袭",
        _ => value,
    }
}
fn element_cn(value: &str) -> &'static str {
    match value {
        "Physical" => "物理",
        "Fire" => "火",
        "Ice" => "冰",
        "Electric" => "电",
        "Ether" => "以太",
        "Wind" => "风",
        "Auric Ink" => "玄墨",
        _ => "",
    }
}
fn style_cn(value: &str) -> &'static str {
    match value {
        "Attack" => "强攻",
        "Anomaly" => "异常",
        "Stun" => "击破",
        "Support" => "支援",
        "Defence" | "Defense" => "防护",
        "Rupture" => "命破",
        _ => "",
    }
}
fn canonical(value: &str) -> String {
    character_slug(value)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(values: &[(&str, &str)]) -> Row {
        values
            .iter()
            .map(|(key, value)| ((*key).into(), (*value).into()))
            .collect()
    }

    #[test]
    fn attach_requires_an_explicit_local_datetime() {
        let mut bundle = ArtifactBundle::default();
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let error = attach_zzz_visualizer(&mut bundle, &context).unwrap_err();
        assert!(error.to_string().contains("explicit local datetime"));
    }

    #[test]
    fn invalid_utf8_in_json_and_prydwen_inputs_is_not_silently_ignored() {
        let local_datetime = chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
            .unwrap()
            .and_hms_opt(13, 0, 0)
            .unwrap();
        let bundle = ArtifactBundle::default();
        for path in [
            "zzz_endgame_phase_overrides.json",
            "zzz_official_endgame_phases.json",
            "zzz_banner_plan.json",
            "decision_cards.json",
        ] {
            let mut context = VisualizerContext::new_with_local_datetime(local_datetime);
            context
                .add_sidecar_bytes(path, vec![b'{', 0xff, b'}'])
                .unwrap();
            let error = read_json_value(&bundle, &context, path).unwrap_err();
            assert!(
                error
                    .to_string()
                    .contains(&format!("invalid UTF-8 in {path}")),
                "unexpected error for {path}: {error}"
            );
        }

        let mut official = ArtifactBundle::default();
        official
            .add_bytes("raw/hoyowiki/zzz_agents_en-us.json", vec![b'[', 0xff, b']'])
            .unwrap();
        let context = VisualizerContext::new_with_local_datetime(local_datetime);
        let error = build_roster(&official, &[], &[], &[], &context).unwrap_err();
        assert!(error
            .to_string()
            .contains("invalid UTF-8 in raw/hoyowiki/zzz_agents_en-us.json"));

        let mut prydwen = ArtifactBundle::default();
        prydwen
            .add_bytes("raw/prydwen/sd.html", vec![b'<', 0xff, b'>'])
            .unwrap();
        let phase = row(&[
            ("snapshot_id", "snapshot-new"),
            ("mode", "sd"),
            ("phase_ver", "3.1"),
        ]);
        let error = build_phase_info(&prydwen, &[phase], &context).unwrap_err();
        assert!(error
            .to_string()
            .contains("invalid UTF-8 in raw/prydwen/sd.html"));
    }

    #[test]
    fn phase_uses_prydwen_then_override_and_reports_source_limits() {
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_text(
                "raw/prydwen/sd.html",
                "<option>3.1 - 07/July/2026 (1,234 users)</option>",
            )
            .unwrap();
        let phase = row(&[
            ("snapshot_id", "snapshot-new"),
            ("mode", "sd"),
            ("phase_ver", "3.1"),
        ]);
        let rows = build_phase_info(&bundle, std::slice::from_ref(&phase), &context).unwrap();
        assert_eq!(rows[0]["collect_date"], "2026-07-07");
        assert_eq!(rows[0]["source_limited"], true);

        let mut context = context;
        context
            .add_sidecar_json(
                "zzz_endgame_phase_overrides.json",
                &json!({"phases":[
                    {"mode":"sd","snapshot_id":"snapshot-new","phase_ver":"3.1","collect_date":"2026-07-08","start_date":"2026-07-01","end_date":"2026-07-31","source_label":"manual","source_url":123,"note":"override"},
                    {"mode":"sd","phase_ver":"4.0","collect_date":"2026-08-02","start_date":"2026-08-01","end_date":"2026-08-15","source_label":"legacy"}
                ]}),
            )
            .unwrap();
        let old_phase = row(&[
            ("snapshot_id", "snapshot-old"),
            ("collect_date", "2026-06-30"),
            ("mode", "sd"),
            ("phase_ver", "3.1"),
        ]);
        let legacy_phase = row(&[
            ("snapshot_id", "snapshot-legacy"),
            ("mode", "sd"),
            ("phase_ver", "4.0"),
        ]);
        let rows = build_phase_info(&bundle, &[old_phase, phase, legacy_phase], &context).unwrap();
        assert_eq!(rows[0]["collect_date"], "2026-06-30");
        assert_eq!(rows[0]["start_date"], "");
        assert_ne!(rows[0]["mechanic_source"], "manual");
        assert_eq!(rows[1]["collect_date"], "2026-07-08");
        assert_eq!(rows[1]["mechanic_source"], "manual");
        assert_eq!(rows[1]["mechanic_name"], "当期数据");
        assert_eq!(rows[1]["phase_status"], "current");
        assert_eq!(rows[2]["collect_date"], "2026-08-02");
        assert_eq!(rows[2]["start_date"], "2026-08-01");
        assert_eq!(rows[2]["mechanic_source"], "legacy");
        let mut data = json!({"phaseInfoRows": rows});
        sanitize_urls(&mut data, "");
        assert_eq!(data["phaseInfoRows"][1]["mechanic_url"], "123");
    }

    #[test]
    fn official_phase_metadata_requires_full_identity_and_only_changes_presentation() {
        let local_date = chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap();
        let bundle = ArtifactBundle::default();
        let target = row(&[
            ("snapshot_id", "snapshot-current"),
            ("collect_date", "2026-07-12"),
            ("mode", "sd"),
            ("mode_cn", "式舆防卫"),
            ("phase_ver", "3.2"),
            ("phase_name", "式舆防卫 3.2"),
            ("start_date", "2026-07-10"),
            ("end_date", "2026-07-24"),
            ("note", "hf identity"),
        ]);
        let historical = row(&[
            ("snapshot_id", "snapshot-history"),
            ("collect_date", "2026-06-26"),
            ("mode", "sd"),
            ("mode_cn", "式舆防卫"),
            ("phase_ver", "3.1"),
            ("phase_name", "式舆防卫 3.1"),
            ("start_date", "2026-06-26"),
            ("end_date", "2026-07-09"),
        ]);
        let baseline = build_phase_info(
            &bundle,
            &[target.clone(), historical.clone()],
            &VisualizerContext::new(local_date),
        )
        .unwrap();
        let exact_identity = json!({
            "mode":"sd",
            "snapshot_id":"snapshot-current",
            "phase_ver":"3.2",
            "start_date":"2026-07-10",
            "end_date":"2026-07-24"
        });
        let official_row = |identity: Value| {
            json!({
                "identity": identity,
                "phase_name_cn":"26.7.10 式舆防卫战",
                "mechanic_name":"本期增益",
                "mechanic_text":"风/冰属性伤害提升；命中异常敌人时增伤并无视全抗。",
                "source_label":"绝区零官方 HoYoWiki",
                "source_url":"javascript:alert(1)"
            })
        };

        for (field, mismatch) in [
            ("mode", "da"),
            ("snapshot_id", "snapshot-other"),
            ("phase_ver", "3.2.1"),
            ("start_date", "2026-07-11"),
            ("end_date", "2026-07-25"),
        ] {
            let mut identity = exact_identity.clone();
            identity[field] = mismatch.into();
            let mut context = VisualizerContext::new(local_date);
            context
                .add_sidecar_json(
                    "zzz_official_endgame_phases.json",
                    &json!({"phases":[official_row(identity)]}),
                )
                .unwrap();
            let rows = build_phase_info(&bundle, std::slice::from_ref(&target), &context).unwrap();
            assert_eq!(rows[0], baseline[0], "mismatch in {field} must not bind");
        }

        let mut invalid = official_row(exact_identity.clone());
        invalid["phase_name_cn"] = json!(123);
        let mut invalid_context = VisualizerContext::new(local_date);
        invalid_context
            .add_sidecar_json(
                "zzz_official_endgame_phases.json",
                &json!({"phases":[invalid]}),
            )
            .unwrap();
        let invalid_rows =
            build_phase_info(&bundle, std::slice::from_ref(&target), &invalid_context).unwrap();
        assert_eq!(invalid_rows[0], baseline[0]);

        let mut context = VisualizerContext::new(local_date);
        context
            .add_sidecar_json(
                "zzz_official_endgame_phases.json",
                &json!({"phases":[official_row(exact_identity)]}),
            )
            .unwrap();
        let enriched = build_phase_info(&bundle, &[target, historical], &context).unwrap();
        for field in [
            "snapshot_id",
            "collect_date",
            "mode",
            "phase_ver",
            "phase_name",
            "start_date",
            "end_date",
            "phase_status",
            "source_limited",
            "source_note",
        ] {
            assert_eq!(enriched[0][field], baseline[0][field], "changed {field}");
        }
        assert_eq!(enriched[0]["phase_name_cn"], "26.7.10 式舆防卫战");
        assert_eq!(enriched[0]["mechanic_name"], "本期增益");
        assert_eq!(
            enriched[0]["mechanic_text"],
            "风/冰属性伤害提升；命中异常敌人时增伤并无视全抗。"
        );
        assert_eq!(enriched[0]["mechanic_source"], "绝区零官方 HoYoWiki");
        assert_eq!(enriched[0]["mechanic_url"], "javascript:alert(1)");
        assert_eq!(enriched[1], baseline[1]);

        let mut output = json!({"phaseInfoRows": enriched});
        sanitize_urls(&mut output, "");
        assert_eq!(output["phaseInfoRows"][0]["mechanic_url"], "");
    }

    #[test]
    fn roster_selects_best_tier_ignores_bangboo_names_and_keeps_float_order() {
        let bundle = ArtifactBundle::default();
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let tiers = vec![
            row(&[
                ("character_slug", "agent-one"),
                ("tier", "T2"),
                ("rating", "7"),
            ]),
            row(&[
                ("character_slug", "agent-one"),
                ("tier", "T0.5"),
                ("rating", "10"),
                ("element", "Ether"),
                ("style", "Attack"),
            ]),
        ];
        let names = vec![
            row(&[
                ("character_slug", "agent-one"),
                ("character_name_cn", "代理一"),
                ("kind", "agent"),
                ("release_order", "10"),
            ]),
            row(&[
                ("character_slug", "bangboo-one"),
                ("kind", "bangboo"),
                ("release_order", "1"),
            ]),
        ];
        let rows = build_roster(&bundle, &[], &tiers, &names, &context).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["tier"], "T0.5");
        assert_eq!(rows[0]["element_cn"], "以太");
        assert_eq!(rows[0]["role_group"], "crit_dps");
        assert_eq!(rows[0]["release_order"], json!(10.0));
    }

    #[test]
    fn roster_localizes_and_orders_agent_published_in_chinese_menu_first() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_bytes(
                "raw/hoyowiki/zzz_agents_zh-cn.json",
                serde_json::to_vec(&json!([
                    {"entry_page_id":"1085","name":"诺姆·霍洛维尔"},
                    {"entry_page_id":"1084","name":"维琳娜·艾嘉德"},
                    {
                        "entry_page_id":"1082",
                        "name":"佩洛伊斯",
                        "filter_values": {
                            "agent_stats":{"values":["以太"]},
                            "agent_specialties":{"values":["强攻"]},
                            "agent_faction":{"values":["法厄同"]},
                            "agent_rarity":{"values":["S"]}
                        }
                    }
                ]))
                .unwrap(),
            )
            .unwrap();
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let tiers = vec![
            row(&[
                ("character_slug", "pyrois"),
                ("character_name_en", "Pyrois"),
                ("tier", "T0.5"),
                ("element", "Ether"),
                ("style", "Attack"),
            ]),
            row(&[
                ("character_slug", "old-agent"),
                ("character_name_en", "Old Agent"),
                ("tier", "T1"),
            ]),
        ];
        let names = vec![row(&[
            ("character_slug", "old-agent"),
            ("character_name_cn", "旧代理人"),
            ("kind", "agent"),
            ("release_order", "10"),
        ])];

        let rows = build_roster(&bundle, &[], &tiers, &names, &context).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0]["character_slug"], "pyrois");
        assert_eq!(rows[0]["character_name_cn"], "佩洛伊斯");
        assert_eq!(rows[0]["element_cn"], "以太");
        assert_eq!(rows[0]["style_cn"], "强攻");
        assert_eq!(rows[0]["release_order"], json!(2.0));
        assert_eq!(rows[1]["character_slug"], "old-agent");
    }

    #[test]
    fn banner_only_future_agents_precede_current_release_without_moving_reruns() {
        let mut roster = vec![
            json!({"character_slug":"norma","release_order":0}),
            json!({"character_slug":"velina","release_order":1}),
            json!({"character_slug":"sunna","release_order":8}),
        ];
        let banner = vec![
            json!({"character_slug":"norma","phase_status":"current"}),
            json!({"character_slug":"sunna","phase_status":"current"}),
            json!({"character_slug":"remielle","character_name_cn":"蕾米埃尔·丹","phase_status":"satellite"}),
            json!({"character_slug":"sigrid","character_name_cn":"希格莉德·德拉叙尔","phase_status":"satellite"}),
            json!({"character_slug":"legacy-only","phase_status":"previous"}),
        ];

        merge_banner_into_roster(&mut roster, &banner);

        assert_eq!(
            roster
                .iter()
                .map(|row| value_str(row, "character_slug"))
                .collect::<Vec<_>>(),
            vec![
                "remielle",
                "sigrid",
                "norma",
                "velina",
                "sunna",
                "legacy-only"
            ]
        );
        assert_eq!(
            roster
                .iter()
                .map(|row| row["release_order"].as_u64().unwrap())
                .collect::<Vec<_>>(),
            vec![0, 1, 2, 3, 4, 5]
        );
        assert_eq!(roster[4]["banner_statuses"], "current");
    }

    #[test]
    fn teams_use_version_recency_and_deterministic_best_candidate() {
        let mut old = row(&[
            ("mode", "sd"),
            ("snapshot_id", "2.9"),
            ("collect_date", "2026-07-12"),
            ("sub_mode", "all"),
            ("rank", "1"),
        ]);
        let mut latest = row(&[
            ("mode", "sd"),
            ("snapshot_id", "3.0"),
            ("collect_date", "2026-07-01"),
            ("sub_mode", "all"),
            ("rank", "2"),
            ("app_rate", "12.5"),
            ("avg_score", "32000"),
            ("source_kind", "processed"),
            ("source_file", "z.csv"),
            ("duplicate_count", "2"),
            ("bangboo_slug", "zeta"),
        ]);
        for (index, slug) in ["a", "b", "c"].iter().enumerate() {
            old.insert(format!("char_{}_slug", index + 1), (*slug).into());
            latest.insert(format!("char_{}_slug", index + 1), (*slug).into());
        }
        let mut permuted = latest.clone();
        for (index, slug) in ["c", "b", "a"].iter().enumerate() {
            permuted.insert(format!("char_{}_slug", index + 1), (*slug).into());
        }
        permuted.insert("rank".into(), "1".into());
        permuted.insert("app_rate".into(), "15".into());
        permuted.insert("avg_score".into(), "33000".into());
        permuted.insert("source_file".into(), "a.csv".into());
        permuted.insert("bangboo_slug".into(), "alpha".into());
        let mut high_score_lower_rate = latest.clone();
        high_score_lower_rate.insert("rank".into(), "1".into());
        high_score_lower_rate.insert("app_rate".into(), "10".into());
        high_score_lower_rate.insert("avg_score".into(), "40000".into());
        high_score_lower_rate.insert("source_file".into(), "m.csv".into());

        let input = vec![old, latest, permuted, high_score_lower_rate];
        let roster = vec![json!({"character_slug":"b","role_group":"support"})];
        let rows = build_team_templates(&input, &roster, &[], &[]).unwrap();
        let mut reversed = input;
        reversed.reverse();
        assert_eq!(
            rows,
            build_team_templates(&reversed, &roster, &[], &[]).unwrap()
        );
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["rank"], json!(1.0));
        assert_eq!(rows[0]["app_rate"], json!(15.0));
        assert_eq!(rows[0]["avg_score"], json!(33000.0));
        assert_eq!(rows[0]["recency_key"], "0003.0000|2026-07-01");
        assert_eq!(rows[0]["chars"], json!(["c", "b", "a"]));
        assert_eq!(rows[0]["bangboo"], "alpha");
        assert_eq!(rows[0]["merged_source_files"], "a.csv;m.csv;z.csv");
        assert_eq!(rows[0]["duplicate_count"], 2);
        assert_eq!(rows[0]["stability_component"], true);
        assert_eq!(rows[0]["evidence_grade"], "A");
        assert!(numeric_float("NaN").is_err());
    }

    #[test]
    fn teams_do_not_count_bangboo_variants_as_duplicate_evidence() {
        let team = |bangboo: &str, score: &str, duplicate_count: &str| {
            let mut team = row(&[
                ("mode", "da"),
                ("snapshot_id", "3.0"),
                ("collect_date", "2026-07-01"),
                ("sub_mode", "all"),
                ("rank", "1"),
                ("app_rate", "10"),
                ("avg_score", score),
                ("source_kind", "processed"),
                ("source_file", "da.csv"),
                ("duplicate_count", duplicate_count),
                ("bangboo_slug", bangboo),
            ]);
            for (index, slug) in ["a", "b", "c"].iter().enumerate() {
                team.insert(format!("char_{}_slug", index + 1), (*slug).into());
            }
            team
        };

        let roster = vec![json!({"character_slug":"b","role_group":"support"})];
        let rows = build_team_templates(
            &[team("zeta", "32000", "1"), team("alpha", "32000", "1")],
            &roster,
            &[],
            &[],
        )
        .unwrap();
        assert_eq!(rows[0]["duplicate_count"], 1);
        assert_eq!(rows[0]["bangboo"], "alpha");
        assert_eq!(rows[0]["evidence_grade"], "B");

        let zero = build_team_templates(&[team("alpha", "0", "2")], &roster, &[], &[]).unwrap();
        assert_eq!(zero[0]["evidence_grade"], "B");
        let valid_99 =
            build_team_templates(&[team("alpha", "99.99", "2")], &roster, &[], &[]).unwrap();
        assert_eq!(valid_99[0]["evidence_grade"], "A");
    }

    #[test]
    fn team_pool_keeps_more_than_twenty_thousand_unique_formations() {
        let teams = (0..20_001)
            .map(|index| {
                let mut team = row(&[
                    ("mode", "sd"),
                    ("snapshot_id", "3.0"),
                    ("collect_date", "2026-07-01"),
                    ("sub_mode", "all"),
                    ("rank", "1"),
                    ("app_rate", "1"),
                    ("avg_score", "1"),
                    ("source_kind", "processed"),
                    ("source_file", "all.csv"),
                ]);
                team.insert("char_1_slug".into(), format!("agent-{index:05}"));
                team.insert("char_2_slug".into(), format!("support-{index:05}"));
                team.insert("char_3_slug".into(), format!("flex-{index:05}"));
                team
            })
            .collect::<Vec<_>>();

        let rows = build_team_templates(&teams, &[], &[], &[]).unwrap();
        assert_eq!(rows.len(), 20_001);
    }

    #[test]
    fn data_quality_freshness_defaults_empty_and_maps_each_mode() {
        assert!(
            read_bundle_object(&ArtifactBundle::default(), "data_quality.json")
                .unwrap()
                .is_none()
        );
        assert_eq!(data_quality_freshness(&json!({})), json!({}));
        let expected = json!({
            "schema_version": "miho-data-quality-v1",
            "game": "zzz",
            "status": "ok",
            "warnings": [],
            "alias_conflict_count": 0,
            "modes": {
                "sd": {"freshness": {"status":"active","sample_date":"2026-07-01","start_date":"2026-07-01","end_date":"2026-07-31","source":"fixture"}},
                "da": {}
            }
        });
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_bytes("data_quality.json", serde_json::to_vec(&expected).unwrap())
            .unwrap();
        let quality = read_bundle_object(&bundle, "data_quality.json")
            .unwrap()
            .unwrap();
        assert_eq!(quality, expected);
        let freshness = data_quality_freshness(&quality);
        assert_eq!(freshness["sd"]["status"], "active");
        assert_eq!(freshness["sd"]["source"], "fixture");
        assert_eq!(freshness["da"], json!({}));

        for path in [
            "character_usage_long.csv",
            "prydwen_tier_current.csv",
            "team_rank_dedup_unordered.csv",
            "name_map.csv",
            "prydwen_tier_changelog_history.csv",
            "phase_index.csv",
        ] {
            bundle.add_text(path, "placeholder\n").unwrap();
        }
        let context = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        attach_zzz_visualizer(&mut bundle, &context).unwrap();
        let legacy: Value =
            serde_json::from_slice(bundle.get("visualizer/data.json").unwrap()).unwrap();
        let payload: Value = crate::visualizer::expand_visualizer_data(
            serde_json::from_slice(bundle.get("visualizer/data.v2.json").unwrap()).unwrap(),
        )
        .unwrap();
        assert_eq!(legacy, payload);
        assert_eq!(payload["data_quality"], quality);
        assert_eq!(payload["freshness"], freshness);
    }

    #[test]
    fn banner_effective_status_adds_banner_only_and_recursive_urls_are_safe() {
        let bundle = ArtifactBundle::default();
        let timed = json!({
            "status":"current",
            "date_range":"2026-07-12 12:00 - 2026-07-12 14:00"
        });
        let at = |hour| {
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(hour, 0, 0)
                .unwrap()
        };
        assert_eq!(
            shared_effective_banner_status(&timed, at(10)).unwrap(),
            "next"
        );
        assert_eq!(
            shared_effective_banner_status(&timed, at(13)).unwrap(),
            "current"
        );
        assert_eq!(
            shared_effective_banner_status(&timed, at(15)).unwrap(),
            "previous"
        );
        let mut context = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        context
            .add_sidecar_json(
                "zzz_banner_plan.json",
                &json!({"refresh":{"status":"fresh","fetched_at":"2026-07-24T14:30:00Z","source_label":"绝区零官方内容"},"phases":[{"id":"old","status":"current","date_range":"1900-01-01 - 1900-01-02","source_url":123,"characters":[{"slug":"new-agent","name_cn":"新代理","style_cn":"强攻","icon_url":456,"analysis_tags":["new"]}]}]}),
            )
            .unwrap();
        let (mut banner, refresh) = build_banner(
            &bundle,
            &context,
            &[],
            context.require_local_datetime().unwrap(),
        )
        .unwrap();
        assert_eq!(
            refresh,
            Some(json!({
                "status": "fresh",
                "fetched_at": "2026-07-24T14:30:00Z",
                "source_label": "绝区零官方内容",
            }))
        );
        localize_icons(&mut banner, &context);
        assert_eq!(banner[0]["phase_status"], "previous");
        assert_eq!(banner[0]["declared_phase_status"], "current");
        assert_eq!(banner[0]["phase_starts_at"], "1900-01-01T00:00:00+08:00");
        assert_eq!(
            banner[0]["phase_ends_at_exclusive"],
            "1900-01-03T00:00:00+08:00"
        );
        let mut sanitized_banner = Value::Array(banner.clone());
        sanitize_urls(&mut sanitized_banner, "");
        assert_eq!(sanitized_banner[0]["source_url"], "123");
        assert_eq!(sanitized_banner[0]["icon_url"], "456");
        let mut roster = vec![];
        merge_banner_into_roster(&mut roster, &banner);
        assert_eq!(roster[0]["source"], "banner_plan");
        assert_eq!(roster[0]["role_group"], "crit_dps");

        let mut nested = json!({"icon_url":"https://bad.example/a.png","nested":[{"source_url":"javascript:alert(1)"},{"url":"docs/ok.html"},{"source_url":123},{"source_url":false},{"source_url":"HTTPS://example.com/X"},{"source_url":"hTtPs://[::1]/X"},{"source_url":"https://[not-an-ipv6]/X"}]});
        sanitize_urls(&mut nested, "");
        assert_eq!(nested["icon_url"], "");
        assert_eq!(nested["nested"][0]["source_url"], "");
        assert_eq!(nested["nested"][1]["url"], "docs/ok.html");
        assert_eq!(nested["nested"][2]["source_url"], "123");
        assert_eq!(nested["nested"][3]["source_url"], "");
        assert_eq!(nested["nested"][4]["source_url"], "HTTPS://example.com/X");
        assert_eq!(nested["nested"][5]["source_url"], "hTtPs://[::1]/X");
        assert_eq!(nested["nested"][6]["source_url"], "");

        let mut numeric_urls: Value = serde_json::from_str(
            r#"{
                "huge_url": 100000000000000000000000000000,
                "negative_url": -100000000000000000000000000001,
                "small_url": 1e-7,
                "negative_small_url": -1e-7,
                "fixed_boundary_url": 1e-4,
                "scientific_boundary_url": 1e-5,
                "fixed_large_boundary_url": 1e15,
                "scientific_large_boundary_url": 1e16,
                "float_integer_url": 1.0,
                "zero_url": 0,
                "negative_zero_url": -0.0,
                "true_url": true,
                "false_url": false,
                "null_url": null
            }"#,
        )
        .unwrap();
        sanitize_urls(&mut numeric_urls, "");
        assert_eq!(numeric_urls["huge_url"], "100000000000000000000000000000");
        assert_eq!(
            numeric_urls["negative_url"],
            "-100000000000000000000000000001"
        );
        assert_eq!(numeric_urls["small_url"], "1e-07");
        assert_eq!(numeric_urls["negative_small_url"], "-1e-07");
        assert_eq!(numeric_urls["fixed_boundary_url"], "0.0001");
        assert_eq!(numeric_urls["scientific_boundary_url"], "1e-05");
        assert_eq!(
            numeric_urls["fixed_large_boundary_url"],
            "1000000000000000.0"
        );
        assert_eq!(numeric_urls["scientific_large_boundary_url"], "1e+16");
        assert_eq!(numeric_urls["float_integer_url"], "1.0");
        assert_eq!(numeric_urls["zero_url"], "");
        assert_eq!(numeric_urls["negative_zero_url"], "");
        assert_eq!(numeric_urls["true_url"], "True");
        assert_eq!(numeric_urls["false_url"], "");
        assert_eq!(numeric_urls["null_url"], "");
        assert_eq!(safe_same_origin_url("."), "");
        assert_eq!(safe_same_origin_url("docs/./escape.html"), "");
        assert_eq!(safe_same_origin_url("%252e%252e/escape.html"), "");
        assert_eq!(
            safe_same_origin_url("./assets/avatar.webp?q=a:b"),
            "./assets/avatar.webp?q=a:b"
        );
    }

    #[test]
    fn sidecar_non_finite_constants_fail_but_malformed_json_falls_back() {
        let bundle = ArtifactBundle::default();
        let mut context = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        context
            .add_sidecar_bytes("decision_cards.json", br#"{"summary":{"score":NaN}}"#)
            .unwrap();
        assert!(read_object_sidecar(&bundle, &context, "decision_cards.json").is_err());

        let mut overflow = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        overflow
            .add_sidecar_bytes(
                "decision_cards.json",
                br#"{"summary":{"positive":1e400,"negative":-1e400},"cards":[]}"#,
            )
            .unwrap();
        assert!(read_object_sidecar(&bundle, &overflow, "decision_cards.json").is_err());

        let mut underflow = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        underflow
            .add_sidecar_bytes(
                "decision_cards.json",
                br#"{"summary":{"score":1e-400,"source_url":1e-400,"negative_zero":-0},"cards":[]}"#,
            )
            .unwrap();
        let mut normalized = read_object_sidecar(&bundle, &underflow, "decision_cards.json")
            .unwrap()
            .unwrap();
        assert_eq!(normalized["summary"]["score"].as_f64(), Some(0.0));
        assert_eq!(normalized["summary"]["negative_zero"].as_i64(), Some(0));
        sanitize_urls(&mut normalized, "");
        assert_eq!(normalized["summary"]["source_url"], "");

        let mut malformed = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        malformed
            .add_sidecar_bytes("decision_cards.json", b"{not json")
            .unwrap();
        assert_eq!(
            read_object_sidecar(&bundle, &malformed, "decision_cards.json").unwrap(),
            None
        );

        for payload in [
            br#"{"summary":{"x":"\ud800"},"cards":[]}"#.as_slice(),
            br#"{"summary":{"x":"\udc00"},"cards":[]}"#.as_slice(),
        ] {
            let mut unpaired = VisualizerContext::new_with_local_datetime(
                chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                    .unwrap()
                    .and_hms_opt(13, 0, 0)
                    .unwrap(),
            );
            unpaired
                .add_sidecar_bytes("decision_cards.json", payload)
                .unwrap();
            let error = read_object_sidecar(&bundle, &unpaired, "decision_cards.json").unwrap_err();
            assert!(error
                .to_string()
                .contains("unpaired JSON surrogate escape in decision_cards.json"));
        }

        for payload in [
            br#"{"summary":{"x":"\ud83d\ude00"},"cards":[]}"#.as_slice(),
            br#"{"summary":{"x":"\\ud800"},"cards":[]}"#.as_slice(),
        ] {
            let mut valid = VisualizerContext::new_with_local_datetime(
                chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                    .unwrap()
                    .and_hms_opt(13, 0, 0)
                    .unwrap(),
            );
            valid
                .add_sidecar_bytes("decision_cards.json", payload)
                .unwrap();
            assert!(read_object_sidecar(&bundle, &valid, "decision_cards.json")
                .unwrap()
                .is_some());
        }
    }
}
