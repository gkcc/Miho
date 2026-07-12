use std::collections::{BTreeMap, BTreeSet, HashMap};

use serde_json::{json, Map, Number, Value};

use crate::{
    normalize::character_slug,
    output::ArtifactBundle,
    visualizer::{
        attach_avatar_assets, attach_zzz_static_assets, compact_json,
        effective_banner_status as shared_effective_banner_status, local_avatar_url,
        python_scalar_text, python_value_truthy as python_truthy, read_csv_rows, safe_link_url,
        strict_utf8, validate_json_surrogate_escapes, VisualizerContext,
    },
    zzz_sources::extract_phase_updates_from_html,
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
    let mut banner = build_banner(bundle, context, &roster, local_datetime)?;
    localize_icons(&mut banner, context);
    merge_banner_into_roster(&mut roster, &banner);
    let team_templates = build_team_templates(&teams, &roster, &names, &phase_info)?;
    let decision_cards = read_object_sidecar(bundle, context, "decision_cards.json")?
        .unwrap_or_else(|| json!({"summary":{},"cards":[]}));

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
    });
    sanitize_urls(&mut data, "");
    attach_zzz_static_assets(bundle)?;
    attach_avatar_assets(bundle, context)?;
    bundle.add_bytes(
        "visualizer/data.json",
        compact_json("visualizer/data.json", &data)?,
    )?;
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
    Ok(phases
        .iter()
        .map(|row| {
            let mode = get(row, "mode");
            let version = get(row, "phase_ver");
            let update = updates.get(&(mode.into(), version.into()));
            let override_row = overrides.get(&(mode.into(), version.into()));
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
            json!({
                "snapshot_id": get(row,"snapshot_id"), "collect_date":collect_date,
                "mode":mode, "mode_cn":mode_cn_value, "phase_ver":version,
                "phase_name":phase_name, "phase_name_cn":phase_name,
                "start_date":start, "end_date":end, "mechanic_name":"当期数据",
                "mechanic_text":mechanic_text, "mechanic_source":mechanic_source,
                "mechanic_url":override_row.and_then(|value|value.get("source_url")).cloned().unwrap_or_else(||Value::String(String::new())),
                "phase_status":phase_status(&start,&end,context),
                "source_limited":source_limited,
                "source_note":first(&[(!override_str("note").is_empty()).then(||override_str("note")), nonempty(row,"note")]),
            })
        })
        .collect())
}

fn phase_overrides(
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
) -> Result<HashMap<(String, String), Value>> {
    let Some(value) = read_json_value(bundle, context, "zzz_endgame_phase_overrides.json")? else {
        return Ok(HashMap::new());
    };
    let rows = if let Some(rows) = value.get("phases").and_then(Value::as_array) {
        rows.clone()
    } else {
        value.as_array().cloned().unwrap_or_default()
    };
    Ok(rows
        .into_iter()
        .filter_map(|row| {
            let mode = value_str(&row, "mode").to_owned();
            let version = value_str(&row, "phase_ver").to_owned();
            (!mode.is_empty() && !version.is_empty()).then_some(((mode, version), row))
        })
        .collect())
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
    let zh_by_id = zh
        .iter()
        .map(|row| (json_text(row.get("entry_page_id")), row))
        .collect::<HashMap<_, _>>();
    let zh_order = zh
        .iter()
        .enumerate()
        .map(|(index, row)| (json_text(row.get("entry_page_id")), index))
        .collect::<HashMap<_, _>>();
    let mut output = HashMap::new();
    for (index, en_row) in en.iter().enumerate() {
        let id = json_text(en_row.get("entry_page_id"));
        let zh_row = zh_by_id.get(&id).copied();
        let name = json_text(en_row.get("name")).trim().to_owned();
        let slug = canonical(&name);
        if slug.is_empty() {
            continue;
        }
        output.insert(
            slug,
            OfficialMeta {
                name_en: name,
                name_cn: json_text(zh_row.and_then(|row| row.get("name")))
                    .trim()
                    .to_owned(),
                element_en: first_filter(Some(en_row), "agent_stats"),
                element_cn: first_filter(zh_row, "agent_stats")
                    .trim_end_matches("属性")
                    .to_owned(),
                style_en: first_filter(Some(en_row), "agent_specialties"),
                style_cn: first_filter(zh_row, "agent_specialties"),
                rarity: first(&[
                    nonempty_text(&first_filter(Some(en_row), "agent_rarity")),
                    nonempty_text(&first_filter(zh_row, "agent_rarity")),
                ]),
                icon_url: first(&[
                    nonempty_text(&json_text(zh_row.and_then(|row| row.get("icon_url")))),
                    nonempty_text(&json_text(en_row.get("icon_url"))),
                ]),
                release_order: zh_order.get(&id).copied().unwrap_or(index),
            },
        );
    }
    Ok(output)
}

fn first_filter(row: Option<&Value>, key: &str) -> String {
    row.and_then(|row| row.pointer(&format!("/filter_values/{key}/values/0")))
        .map(|value| json_text(Some(value)))
        .unwrap_or_default()
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

fn nonempty_text(value: &str) -> Option<&str> {
    (!value.is_empty()).then_some(value)
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
    let mut output = Vec::new();
    let mut seen = BTreeSet::new();
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
        if !seen.insert(key) {
            continue;
        }
        let collect_date = first(&[
            nonempty(row, "collect_date"),
            phase_dates
                .get(&(mode.into(), get(row, "phase_ver").into()))
                .map(String::as_str),
        ]);
        let bangboo = canonical(get(row, "bangboo_slug"));
        output.push(json!({
            "mode":mode,"mode_cn":first(&[nonempty(row,"mode_cn"),Some(mode_cn(mode))]),
            "scope_key":first(&[nonempty(row,"sub_mode"),Some("all")]),
            "scope_label":first(&[nonempty(row,"sub_mode_cn"),nonempty(row,"sub_mode"),Some("全部")]),
            "collect_date":collect_date,"phase_ver":get(row,"phase_ver"),"phase_name":get(row,"phase_name"),
            "rank":numeric_float(get(row,"rank"))?,"app_rate":numeric_float(get(row,"app_rate"))?,"avg_score":numeric_float(get(row,"avg_score"))?,
            "bangboo":bangboo,"bangboo_name":first(&[nonempty(row,"bangboo_name_cn"),name_map.get(&bangboo).and_then(|row|nonempty(row,"character_name_cn"))]),
            "source_kind":get(row,"source_kind"),"source_file":get(row,"source_file"),"recency_key":team_recency_key(row,&phase_dates),
            "chars":chars,"names_cn":chars.iter().map(|slug|roster_map.get(slug.as_str()).map(|row|first(&[nonempty_value(row,"character_name_cn"),nonempty_value(row,"character_name_en"),Some(slug)])).unwrap_or_else(||slug.clone())).collect::<Vec<_>>(),
        }));
    }
    output.sort_by(|left, right| {
        value_str(left, "mode")
            .cmp(value_str(right, "mode"))
            .then_with(|| value_str(left, "scope_key").cmp(value_str(right, "scope_key")))
            .then_with(|| team_rank_value(left).total_cmp(&team_rank_value(right)))
    });
    output.truncate(20_000);
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
fn team_rank_value(value: &Value) -> f64 {
    let rank = value.get("rank").and_then(Value::as_f64).unwrap_or(0.0);
    if rank == 0.0 {
        9999.0
    } else {
        rank
    }
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
) -> Result<Vec<Value>> {
    let Some(root) = read_object_sidecar(bundle, context, "zzz_banner_plan.json")? else {
        return Ok(vec![]);
    };
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
    Ok(output)
}

fn merge_banner_into_roster(roster: &mut Vec<Value>, banner: &[Value]) {
    let mut by_slug = roster
        .drain(..)
        .filter_map(|row| {
            let slug = value_str(&row, "character_slug").to_owned();
            (!slug.is_empty()).then_some((slug, row))
        })
        .collect::<BTreeMap<_, _>>();
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
    *roster = by_slug.into_values().collect();
    roster.sort_by(|left, right| {
        release_order(left)
            .total_cmp(&release_order(right))
            .then_with(|| value_str(left, "character_slug").cmp(value_str(right, "character_slug")))
    });
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
        let phase = row(&[("mode", "sd"), ("phase_ver", "3.1")]);
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
        let phase = row(&[("mode", "sd"), ("phase_ver", "3.1")]);
        let rows = build_phase_info(&bundle, std::slice::from_ref(&phase), &context).unwrap();
        assert_eq!(rows[0]["collect_date"], "2026-07-07");
        assert_eq!(rows[0]["source_limited"], true);

        let mut context = context;
        context
            .add_sidecar_json(
                "zzz_endgame_phase_overrides.json",
                &json!({"phases":[{"mode":"sd","phase_ver":"3.1","collect_date":"2026-07-08","start_date":"2026-07-01","end_date":"2026-07-31","source_label":"manual","source_url":123,"note":"override"}]}),
            )
            .unwrap();
        let rows = build_phase_info(&bundle, &[phase], &context).unwrap();
        assert_eq!(rows[0]["collect_date"], "2026-07-08");
        assert_eq!(rows[0]["mechanic_source"], "manual");
        assert_eq!(rows[0]["phase_status"], "current");
        let mut data = json!({"phaseInfoRows": rows});
        sanitize_urls(&mut data, "");
        assert_eq!(data["phaseInfoRows"][0]["mechanic_url"], "123");
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
    fn teams_use_version_recency_first_seen_dedupe_and_float_types() {
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
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
            ("rank", "1"),
            ("app_rate", "12.5"),
            ("avg_score", "32000"),
        ]);
        for (index, slug) in ["a", "b", "c"].iter().enumerate() {
            old.insert(format!("char_{}_slug", index + 1), (*slug).into());
            latest.insert(format!("char_{}_slug", index + 1), (*slug).into());
        }
        let mut permuted = latest.clone();
        for (index, slug) in ["c", "b", "a"].iter().enumerate() {
            permuted.insert(format!("char_{}_slug", index + 1), (*slug).into());
        }
        let rows = build_team_templates(&[old, latest, permuted], &[], &[], &[]).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["rank"], json!(1.0));
        assert_eq!(rows[0]["recency_key"], "0003.0000|2026-07-01");
        assert_eq!(rows[0]["chars"], json!(["a", "b", "c"]));
        assert!(numeric_float("NaN").is_err());
        let _ = context;
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
                &json!({"phases":[{"id":"old","status":"current","date_range":"1900-01-01 - 1900-01-02","source_url":123,"characters":[{"slug":"new-agent","name_cn":"新代理","style_cn":"强攻","icon_url":456,"analysis_tags":["new"]}]}]}),
            )
            .unwrap();
        let mut banner = build_banner(
            &bundle,
            &context,
            &[],
            context.require_local_datetime().unwrap(),
        )
        .unwrap();
        localize_icons(&mut banner, &context);
        assert_eq!(banner[0]["phase_status"], "previous");
        assert_eq!(banner[0]["declared_phase_status"], "current");
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
