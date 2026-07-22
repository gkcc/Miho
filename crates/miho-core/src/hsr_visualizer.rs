use std::collections::{BTreeMap, BTreeSet, HashMap};

use serde_json::{json, Map, Number, Value};

use crate::{
    normalize::character_slug,
    output::ArtifactBundle,
    visualizer::{
        attach_avatar_assets, attach_hsr_static_assets, compact_json,
        effective_banner_status as shared_effective_banner_status, local_avatar_url,
        python_scalar_text, python_value_truthy, read_csv_rows, safe_link_url, safe_relative_url,
        strict_utf8, validate_json_surrogate_escapes, VisualizerContext,
    },
    MihoError, Result,
};

type Row = BTreeMap<String, String>;

const TIER_KEEP: &[&str] = &["T0", "T0.5", "T1", "T1.5", "T2"];

pub fn attach_hsr_visualizer(
    bundle: &mut ArtifactBundle,
    context: &VisualizerContext,
) -> Result<()> {
    let local_datetime = context.require_local_datetime()?;
    let trend = read_csv_rows(bundle, "prydwen_tier_usage_trend.csv")?;
    let tiers = read_csv_rows(bundle, "prydwen_tier_current.csv")?;
    let changelog = read_csv_rows(bundle, "prydwen_tier_changelog_history.csv")?;
    let charts = read_csv_rows(bundle, "prydwen_tier_charts.csv")?;
    let characters = read_csv_rows(bundle, "character_usage_long.csv")?;
    let teams = read_csv_rows(bundle, "team_rank_raw.csv")?;
    let names = read_csv_rows(bundle, "name_map.csv")?;
    let phases = read_csv_rows(bundle, "phase_index.csv")?;

    let mut roster = build_roster(bundle, &tiers, &characters, &names, context)?;
    let phase_info = build_phase_info(&phases, context);
    let banner = build_banner(context, &roster, local_datetime)?;
    merge_banner_into_roster(&mut roster, &banner);
    let usage = build_usage(&characters, &tiers, &roster, context);
    let team_templates = build_teams(&teams, &phase_info, &roster, context)?;
    let trend_json = sanitize_avatar_rows(&trend, &roster, context);
    let tier_json = sanitize_tier_rows(&tiers, &roster, context);
    let usage_json = if usage.is_empty() {
        trend_json.clone()
    } else {
        usage
    };
    let data = json!({
        "meta": {
            "generatedAt": latest(&tiers, "fetched_at"),
            "tierUpdatedAt": latest(&tiers, "tier_updated_at"),
            "tierUpdatedDate": latest(&tiers, "tier_updated_date"),
            "localDate": context.local_date.to_string(),
            "source": "Prydwen Tier List + local MocStats processed dataset + HoYoWiki roster",
        },
        "metric_policy": {
            "moc": {"field": "avg_round", "label": "平均回合", "direction": "lower", "sentinels": [0, 99.99]},
            "pf": {"field": "avg_round", "label": "虚构得分", "direction": "higher", "sentinels": [0, 99.99]},
            "as": {"field": "avg_round", "label": "末日得分", "direction": "higher", "sentinels": [0, 99.99]},
            "aa": {"field": "avg_round", "label": "表现原值", "direction": null, "sentinels": [0, 99.99]},
        },
        "trendRows": trend_json,
        "usageRows": usage_json,
        "tierRows": tier_json,
        "changelogRows": sanitize_link_rows(&changelog, "source_url"),
        "chartRows": string_rows(&charts),
        "rosterRows": roster,
        "phaseInfoRows": phase_info,
        "teamTemplates": team_templates,
        "bannerRows": banner,
    });
    attach_hsr_static_assets(bundle)?;
    attach_avatar_assets(bundle, context)?;
    bundle.add_bytes(
        "visualizer/data.json",
        compact_json("visualizer/data.json", &data)?,
    )?;
    Ok(())
}

fn latest(rows: &[Row], key: &str) -> String {
    rows.iter()
        .filter_map(|row| nonempty(row, key))
        .max()
        .unwrap_or_default()
}

fn string_rows(rows: &[Row]) -> Vec<Value> {
    rows.iter().map(string_row).collect()
}

fn string_row(row: &Row) -> Value {
    Value::Object(
        row.iter()
            .map(|(key, value)| (key.clone(), Value::String(value.clone())))
            .collect(),
    )
}

fn sanitize_avatar_rows(rows: &[Row], roster: &[Value], context: &VisualizerContext) -> Vec<Value> {
    let roster = roster_lookup(roster);
    rows.iter()
        .map(|row| {
            let mut value = row_map(row);
            let slug = canonical(get(row, "character_slug"));
            let roster_icon = roster
                .get(&slug)
                .and_then(|value| value.get("icon_url"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let icon_url = if context.avatar_webp(&slug).is_some() {
                local_avatar_url(context, &slug)
            } else {
                first(&[
                    nonempty_text(&safe_relative_url(roster_icon)).as_deref(),
                    nonempty_text(&safe_relative_url(get(row, "icon_url"))).as_deref(),
                ])
            };
            value.insert("icon_url".into(), icon_url.into());
            Value::Object(value)
        })
        .collect()
}

fn sanitize_tier_rows(rows: &[Row], roster: &[Value], context: &VisualizerContext) -> Vec<Value> {
    let roster = roster_lookup(roster);
    rows.iter()
        .map(|row| {
            let mut value = row_map(row);
            let slug = canonical(get(row, "character_slug"));
            let roster_icon = roster
                .get(&slug)
                .and_then(|value| value.get("icon_url"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let icon_url = if context.avatar_webp(&slug).is_some() {
                local_avatar_url(context, &slug)
            } else {
                first(&[
                    nonempty_text(&safe_relative_url(roster_icon)).as_deref(),
                    nonempty_text(&safe_relative_url(get(row, "icon_url"))).as_deref(),
                ])
            };
            value.insert("icon_url".into(), icon_url.into());
            value.insert(
                "source_url".into(),
                safe_link_url(get(row, "source_url")).into(),
            );
            Value::Object(value)
        })
        .collect()
}

fn sanitize_link_rows(rows: &[Row], key: &str) -> Vec<Value> {
    rows.iter()
        .map(|row| {
            let mut value = row_map(row);
            value.insert(key.into(), safe_link_url(get(row, key)).into());
            Value::Object(value)
        })
        .collect()
}

fn build_roster(
    bundle: &ArtifactBundle,
    tiers: &[Row],
    usage: &[Row],
    names: &[Row],
    context: &VisualizerContext,
) -> Result<Vec<Value>> {
    let zh_rows = read_official_rows(bundle, "raw/hoyowiki/hsr_characters_zh-cn.json")?;
    let en_rows = read_official_rows(bundle, "raw/hoyowiki/hsr_characters_en-us.json")?;
    Ok(build_official_roster(
        &zh_rows, &en_rows, tiers, usage, names, context,
    ))
}

#[derive(Debug, Default)]
struct TierMeta {
    character_name_en: String,
    character_name_cn: String,
    element_en: String,
    path_en: String,
    rarity: String,
    icon_url: String,
    roles: Vec<String>,
    aliases: String,
}

fn read_official_rows(bundle: &ArtifactBundle, path: &str) -> Result<Vec<Value>> {
    let Some(bytes) = bundle.get(path) else {
        return Ok(vec![]);
    };
    let text = strict_utf8(bytes, path)?;
    validate_json_surrogate_escapes(text, path)?;
    let value: Value = serde_json::from_str(text).map_err(|source| MihoError::Json {
        path: path.into(),
        source,
    })?;
    Ok(value.as_array().cloned().unwrap_or_default())
}

fn build_official_roster(
    zh_rows: &[Value],
    en_rows: &[Value],
    tiers: &[Row],
    usage: &[Row],
    names: &[Row],
    context: &VisualizerContext,
) -> Vec<Value> {
    let tier_meta = build_tier_meta(tiers);
    let name_map = names
        .iter()
        .map(|row| (canonical(get(row, "character_slug")), row))
        .collect::<HashMap<_, _>>();
    let mut usage_meta = HashMap::new();
    for row in usage {
        let slug = canonical(get(row, "character_slug"));
        if !slug.is_empty() {
            usage_meta.entry(slug).or_insert(row);
        }
    }

    let zh_by_id = official_by_id(zh_rows);
    let en_by_id = official_by_id(en_rows);
    let ids = zh_by_id
        .keys()
        .chain(en_by_id.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut ids = ids.into_iter().collect::<Vec<_>>();
    ids.sort_by_key(|id| {
        (
            zh_by_id
                .get(id)
                .map(|(_, order)| *order)
                .unwrap_or(9999)
                .min(en_by_id.get(id).map(|(_, order)| *order).unwrap_or(9999)),
            id.clone(),
        )
    });

    let mut roster = BTreeMap::<String, Map<String, Value>>::new();
    for id in ids {
        let en_row = en_by_id.get(&id).map(|(row, _)| *row);
        let zh_row = zh_by_id.get(&id).map(|(row, _)| *row);
        let en_name = value_text(en_row.and_then(|row| row.get("name")))
            .trim()
            .to_owned();
        if en_name.is_empty() {
            continue;
        }
        let raw_slug = character_slug(&en_name);
        let slug = canonical(&raw_slug);
        if slug.is_empty() {
            continue;
        }
        let order = zh_by_id
            .get(&id)
            .map(|(_, order)| *order)
            .unwrap_or(9999)
            .min(en_by_id.get(&id).map(|(_, order)| *order).unwrap_or(9999));
        let tier = tier_meta.get(&slug);
        let usage = usage_meta.get(&slug).copied();
        let name = name_map.get(&slug).copied();
        let element_en = first_filter_value(en_row, "character_combat_type");
        let path_en = first_filter_value(en_row, "character_paths");
        let character_name_cn = first(&[
            nonempty_value(zh_row.and_then(|row| row.get("name"))).as_deref(),
            supplemental_cn_name(&slug),
            name.and_then(|row| nonempty(row, "character_name_cn"))
                .as_deref(),
        ])
        .trim()
        .to_owned();
        let mut entry = roster_entry(
            &slug,
            order,
            &en_name,
            &character_name_cn,
            &first(&[
                nonempty_text(&first_filter_value(zh_row, "character_combat_type")).as_deref(),
                Some(element_cn(&element_en)),
            ]),
            &element_en,
            &first(&[
                nonempty_text(&first_filter_value(zh_row, "character_paths")).as_deref(),
                Some(path_cn(&path_en)),
            ]),
            &path_en,
            &rarity_value(&first(&[
                nonempty_text(&first_filter_value(en_row, "character_rarity")).as_deref(),
                nonempty_text(&first_filter_value(zh_row, "character_rarity")).as_deref(),
            ])),
            &first(&[
                nonempty_value(zh_row.and_then(|row| row.get("icon_url"))).as_deref(),
                nonempty_value(en_row.and_then(|row| row.get("icon_url"))).as_deref(),
            ]),
            tier,
            usage,
            "HoYoWiki",
        );
        set_merged_field(&mut entry, "alias_slugs", &[&raw_slug, &slug]);
        if let Some(base) = roster.get_mut(&slug) {
            merge_roster_entries(base, &entry);
        } else {
            roster.insert(slug, entry);
        }
    }

    let mut extra_order = 10_000;
    for (slug, meta) in &tier_meta {
        if let Some(entry) = roster.get_mut(slug) {
            merge_tier_meta(entry, meta);
            continue;
        }
        extra_order += 1;
        let usage = usage_meta.get(slug).copied();
        let name = name_map.get(slug).copied();
        roster.insert(
            slug.clone(),
            roster_entry(
                slug,
                extra_order,
                &meta.character_name_en,
                &first(&[
                    nonempty_text(&meta.character_name_cn).as_deref(),
                    supplemental_cn_name(slug),
                    name.and_then(|row| nonempty(row, "character_name_cn"))
                        .as_deref(),
                ]),
                element_cn(&meta.element_en),
                &meta.element_en,
                path_cn(&meta.path_en),
                &meta.path_en,
                &meta.rarity,
                &meta.icon_url,
                Some(meta),
                usage,
                "Prydwen",
            ),
        );
    }

    let mut usage_order = 20_000;
    let mut usage_slugs = usage_meta.keys().cloned().collect::<Vec<_>>();
    usage_slugs.sort();
    for slug in usage_slugs {
        if roster.contains_key(&slug) {
            continue;
        }
        usage_order += 1;
        let row = usage_meta[&slug];
        let name = name_map.get(&slug).copied();
        roster.insert(
            slug.clone(),
            roster_entry(
                &slug,
                usage_order,
                &first(&[nonempty(row, "character_name_en").as_deref(), Some(&slug)]),
                &first(&[
                    nonempty(row, "character_name_cn").as_deref(),
                    supplemental_cn_name(&slug),
                    name.and_then(|row| nonempty(row, "character_name_cn"))
                        .as_deref(),
                ]),
                "",
                "",
                "",
                "",
                get(row, "rarity"),
                "",
                None,
                Some(row),
                "usage",
            ),
        );
    }

    let mut output = roster.into_values().collect::<Vec<_>>();
    for entry in &mut output {
        let slug = entry
            .get("character_slug")
            .and_then(Value::as_str)
            .unwrap_or("");
        let current = entry.get("icon_url").and_then(Value::as_str).unwrap_or("");
        let icon_url = if context.avatar_webp(slug).is_some() {
            local_avatar_url(context, slug)
        } else {
            safe_relative_url(current)
        };
        entry.insert("icon_url".into(), icon_url.into());
    }
    output.sort_by_key(|entry| {
        (
            entry
                .get("release_order")
                .and_then(Value::as_u64)
                .unwrap_or(99999),
            entry
                .get("character_name_en")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned(),
        )
    });
    output.into_iter().map(Value::Object).collect()
}

fn build_tier_meta(tiers: &[Row]) -> BTreeMap<String, TierMeta> {
    let mut output = BTreeMap::<String, TierMeta>::new();
    for row in tiers {
        let raw_slug = get(row, "character_slug");
        let slug = canonical(raw_slug);
        if slug.is_empty() {
            continue;
        }
        let entry = output.entry(slug.clone()).or_insert_with(|| TierMeta {
            character_name_en: get(row, "character_name_en").into(),
            character_name_cn: get(row, "character_name_cn").into(),
            element_en: get(row, "element").into(),
            path_en: get(row, "path").into(),
            rarity: get(row, "rarity").into(),
            icon_url: get(row, "icon_url").into(),
            ..TierMeta::default()
        });
        if entry.character_name_cn.is_empty() && !get(row, "character_name_cn").is_empty() {
            entry.character_name_cn = get(row, "character_name_cn").into();
        }
        for (target, source) in [
            (&mut entry.icon_url, "icon_url"),
            (&mut entry.element_en, "element"),
            (&mut entry.path_en, "path"),
        ] {
            if !get(row, source).is_empty() {
                *target = get(row, source).into();
            }
        }
        let role = get(row, "role_group");
        if !role.is_empty() && !entry.roles.iter().any(|value| value == role) {
            entry.roles.push(role.to_owned());
            entry.roles.sort_by_key(|value| role_order(value));
        }
        entry.aliases = merge_values(&entry.aliases, &[raw_slug, &slug]);
    }
    output
}

fn official_by_id(rows: &[Value]) -> HashMap<String, (&Value, usize)> {
    rows.iter()
        .enumerate()
        .filter_map(|(index, row)| {
            let id = value_text(row.get("entry_page_id"));
            (!id.is_empty()).then_some((id, (row, index)))
        })
        .collect()
}

fn value_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(value)) => value.to_string(),
        _ => String::new(),
    }
}

fn first_filter_value(row: Option<&Value>, key: &str) -> String {
    row.and_then(|row| row.get("filter_values"))
        .and_then(|value| value.get(key))
        .and_then(|value| value.get("values"))
        .and_then(Value::as_array)
        .and_then(|values| values.first())
        .map(|value| value_text(Some(value)))
        .unwrap_or_default()
}

fn nonempty_value(value: Option<&Value>) -> Option<String> {
    nonempty_text(&value_text(value))
}

fn nonempty_text(value: &str) -> Option<String> {
    (!value.trim().is_empty()).then(|| value.to_owned())
}

fn supplemental_cn_name(slug: &str) -> Option<&'static str> {
    match slug {
        "aventurine-waveflair" => Some("砂金•戏浪"),
        "robin-summeretto" => Some("知更鸟•晴歌"),
        _ => None,
    }
}

#[allow(clippy::too_many_arguments)]
fn roster_entry(
    slug: &str,
    release_order: usize,
    character_name_en: &str,
    character_name_cn: &str,
    element_cn_value: &str,
    element_en: &str,
    path_cn_value: &str,
    path_en: &str,
    rarity: &str,
    icon_url: &str,
    tier: Option<&TierMeta>,
    usage: Option<&Row>,
    source: &str,
) -> Map<String, Value> {
    let element_en = if element_en.is_empty() {
        tier.map(|meta| meta.element_en.as_str()).unwrap_or("")
    } else {
        element_en
    };
    let element_cn_value = if element_cn_value.is_empty() {
        element_cn(element_en)
    } else {
        element_cn_value
    };
    let path_en = if path_en.is_empty() {
        tier.map(|meta| meta.path_en.as_str()).unwrap_or("")
    } else {
        path_en
    };
    let path_cn_value = if path_cn_value.is_empty() {
        path_cn(path_en)
    } else {
        path_cn_value
    };
    let icon_url = if icon_url.is_empty() {
        tier.map(|meta| meta.icon_url.as_str()).unwrap_or("")
    } else {
        icon_url
    };
    let roles = tier
        .map(|meta| meta.roles.clone())
        .filter(|roles| !roles.is_empty())
        .unwrap_or_else(|| vec!["unknown".into()]);
    let usage_value = |key| usage.map(|row| get(row, key)).unwrap_or("");
    Map::from_iter([
        ("character_slug".into(), slug.into()),
        ("deployment_group".into(), deployment_group(slug).into()),
        (
            "character_name_en".into(),
            first(&[
                nonempty_text(character_name_en).as_deref(),
                nonempty_text(usage_value("character_name_en")).as_deref(),
                Some(slug),
            ])
            .into(),
        ),
        (
            "character_name_cn".into(),
            first(&[
                nonempty_text(character_name_cn).as_deref(),
                nonempty_text(usage_value("character_name_cn")).as_deref(),
            ])
            .into(),
        ),
        ("element_cn".into(), element_cn_value.into()),
        ("element_en".into(), element_en.into()),
        ("path_cn".into(), path_cn_value.into()),
        ("path_en".into(), path_en.into()),
        ("rarity".into(), rarity.into()),
        ("icon_url".into(), icon_url.into()),
        ("release_order".into(), release_order.into()),
        ("role_groups".into(), roles.join(";").into()),
        (
            "role_group_cns".into(),
            roles
                .iter()
                .map(|role| role_cn(role))
                .collect::<Vec<_>>()
                .join(";")
                .into(),
        ),
        ("alias_slugs".into(), slug.into()),
        ("source".into(), source.into()),
    ])
}

fn merge_roster_entries(base: &mut Map<String, Value>, incoming: &Map<String, Value>) {
    for key in [
        "character_name_cn",
        "character_name_en",
        "element_cn",
        "element_en",
        "path_cn",
        "path_en",
        "rarity",
    ] {
        if base
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or("")
            .is_empty()
        {
            if let Some(value) = incoming
                .get(key)
                .filter(|value| !value.as_str().unwrap_or("").is_empty())
            {
                base.insert(key.into(), value.clone());
            }
        }
    }
    let slug = base
        .get("character_slug")
        .and_then(Value::as_str)
        .unwrap_or("");
    let current_icon = base.get("icon_url").and_then(Value::as_str).unwrap_or("");
    let incoming_icon = incoming
        .get("icon_url")
        .and_then(Value::as_str)
        .unwrap_or("");
    if prefer_icon(incoming_icon, current_icon, slug) {
        base.insert("icon_url".into(), incoming_icon.into());
    }
    let base_order = base
        .get("release_order")
        .and_then(Value::as_u64)
        .unwrap_or(99999);
    let incoming_order = incoming
        .get("release_order")
        .and_then(Value::as_u64)
        .unwrap_or(99999);
    if incoming_order < base_order {
        base.insert("release_order".into(), incoming_order.into());
    }
    for key in ["alias_slugs", "source", "role_groups"] {
        let incoming_value = incoming.get(key).and_then(Value::as_str).unwrap_or("");
        set_merged_field(base, key, &[incoming_value]);
    }
    let mut roles = base
        .get("role_groups")
        .and_then(Value::as_str)
        .unwrap_or("")
        .split(';')
        .filter(|role| !role.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    roles.sort_by_key(|role| role_order(role));
    roles.dedup();
    base.insert("role_groups".into(), roles.join(";").into());
    base.insert(
        "role_group_cns".into(),
        roles
            .iter()
            .map(|role| role_cn(role))
            .collect::<Vec<_>>()
            .join(";")
            .into(),
    );
}

fn merge_tier_meta(entry: &mut Map<String, Value>, meta: &TierMeta) {
    if entry
        .get("character_name_cn")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
        && !meta.character_name_cn.is_empty()
    {
        entry.insert(
            "character_name_cn".into(),
            meta.character_name_cn.clone().into(),
        );
    }
    if entry
        .get("element_en")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
        && !meta.element_en.is_empty()
    {
        entry.insert("element_en".into(), meta.element_en.clone().into());
        entry.insert("element_cn".into(), element_cn(&meta.element_en).into());
    }
    if entry
        .get("path_en")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
        && !meta.path_en.is_empty()
    {
        entry.insert("path_en".into(), meta.path_en.clone().into());
        entry.insert("path_cn".into(), path_cn(&meta.path_en).into());
    }
    let slug = entry
        .get("character_slug")
        .and_then(Value::as_str)
        .unwrap_or("");
    let current_icon = entry.get("icon_url").and_then(Value::as_str).unwrap_or("");
    if prefer_icon(&meta.icon_url, current_icon, slug) {
        entry.insert("icon_url".into(), meta.icon_url.clone().into());
    }
    if !meta.roles.is_empty() {
        entry.insert("role_groups".into(), meta.roles.join(";").into());
        entry.insert(
            "role_group_cns".into(),
            meta.roles
                .iter()
                .map(|role| role_cn(role))
                .collect::<Vec<_>>()
                .join(";")
                .into(),
        );
    }
    set_merged_field(entry, "alias_slugs", &[&meta.aliases]);
    set_merged_field(entry, "source", &["Prydwen"]);
}

fn set_merged_field(entry: &mut Map<String, Value>, key: &str, values: &[&str]) {
    let current = entry.get(key).and_then(Value::as_str).unwrap_or("");
    entry.insert(key.into(), merge_values(current, values).into());
}

fn merge_values(current: &str, values: &[&str]) -> String {
    let mut output = current
        .split(';')
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    for value in values.iter().flat_map(|value| value.split(';')) {
        if !value.is_empty() && !output.iter().any(|item| item == value) {
            output.push(value.to_owned());
        }
    }
    output.join(";")
}

fn rarity_value(value: &str) -> String {
    if value.contains('5') || value.contains("五星") {
        "5".into()
    } else if value.contains('4') || value.contains("四星") {
        "4".into()
    } else {
        value.into()
    }
}

fn prefer_icon(candidate: &str, current: &str, slug: &str) -> bool {
    !candidate.is_empty()
        && (current.is_empty()
            || (slug.starts_with("trailblazer-") && candidate.contains("prydwen.gg"))
            || (current.to_ascii_lowercase().ends_with(".gif")
                && !candidate.to_ascii_lowercase().ends_with(".gif")))
}

fn build_usage(
    usage: &[Row],
    tiers: &[Row],
    roster: &[Value],
    context: &VisualizerContext,
) -> Vec<Value> {
    let roster = roster_lookup(roster);
    let mut output = vec![];
    for row in usage
        .iter()
        .filter(|row| matches!(get(row, "sub_mode"), "all" | "all_bosses"))
    {
        let slug = canonical(get(row, "character_slug"));
        if slug.is_empty() {
            continue;
        }
        let mode_roles = best_role_tiers(tiers, &slug, Some(get(row, "mode")));
        let (selected, untiered) = if mode_roles.is_empty() {
            let roles = best_role_tiers(tiers, &slug, None);
            if roles.is_empty() {
                (vec![None], true)
            } else {
                (roles.into_iter().map(Some).collect(), true)
            }
        } else {
            (
                mode_roles
                    .into_iter()
                    .filter(|tier| TIER_KEEP.contains(&get(tier, "tier")))
                    .map(Some)
                    .collect(),
                false,
            )
        };
        for tier in selected {
            let r = roster.get(&slug);
            let role = tier
                .map(|t| get(t, "role_group"))
                .filter(|v| !v.is_empty())
                .or_else(|| {
                    r.and_then(|v| v.get("role_groups"))
                        .and_then(Value::as_str)
                        .and_then(|v| v.split(';').next())
                })
                .unwrap_or("unknown");
            let role_group_cn = if matches!(
                role,
                "main_dps" | "sub_dps" | "support" | "sustain" | "unknown"
            ) {
                role_cn(role)
            } else {
                tier.map(|t| get(t, "role_group_cn"))
                    .filter(|value| !value.is_empty())
                    .unwrap_or("未分类")
            };
            let roster_value = |key| {
                r.and_then(|value| value.get(key))
                    .and_then(Value::as_str)
                    .unwrap_or("")
            };
            let icon_url = if context.avatar_webp(&slug).is_some() {
                local_avatar_url(context, &slug)
            } else {
                safe_relative_url(&first(&[
                    nonempty_text(roster_value("icon_url")).as_deref(),
                    tier.and_then(|value| nonempty(value, "icon_url"))
                        .as_deref(),
                ]))
            };
            output.push(json!({
                "tier_snapshot_id": tier.map(|t| get(t,"tier_snapshot_id")).unwrap_or(""),
                "tier_updated_date": tier.map(|t| get(t,"tier_updated_date")).unwrap_or(""),
                "tier_mode": get(row,"mode"), "tier_mode_cn": first(&[nonempty(row,"mode_cn").as_deref(), Some(mode_cn(get(row,"mode")))]),
                "sub_mode": get(row,"sub_mode"), "sub_mode_cn": get(row,"sub_mode_cn"),
                "character_slug": slug,
                "character_name_en": first(&[nonempty(row,"character_name_en").as_deref(), nonempty_text(roster_value("character_name_en")).as_deref(), Some(&slug)]),
                "character_name_cn": first(&[nonempty(row,"character_name_cn").as_deref(), nonempty_text(roster_value("character_name_cn")).as_deref()]),
                "prydwen_role": tier.map(|t| get(t,"prydwen_role")).unwrap_or(""),
                "role_group": role, "role_group_cn": role_group_cn,
                "tier": if untiered { "未分档" } else { tier.map(|t| get(t,"tier")).unwrap_or("未分档") },
                "rating": if untiered { "" } else { tier.map(|t| get(t,"rating")).unwrap_or("") },
                "tags": tier.map(|t| get(t,"tags")).unwrap_or(""), "marks": tier.map(|t| get(t,"marks")).unwrap_or(""),
                "collect_date": get(row,"collect_date"), "phase_ver": get(row,"phase_ver"), "phase_name": get(row,"phase_name"),
                "phase_name_cn": phase_name_cn(get(row,"mode"), get(row,"phase_name")),
                "app_rate": get(row,"app_rate"), "avg_round": get(row,"avg_round"), "quality_flag": get(row,"quality_flag"),
                "icon_url": icon_url,
                "element_cn": roster_value("element_cn"),
                "element_en": roster_value("element_en"),
                "path_cn": roster_value("path_cn"),
                "path_en": roster_value("path_en"),
                "rarity": roster_value("rarity"),
            }));
        }
    }
    output
}

fn best_role_tiers<'a>(tiers: &'a [Row], slug: &str, mode: Option<&str>) -> Vec<&'a Row> {
    let mut roles = Vec::<(String, &'a Row)>::new();
    for tier in tiers.iter().filter(|tier| {
        canonical(get(tier, "character_slug")) == slug
            && mode.is_none_or(|expected| get(tier, "tier_mode") == expected)
    }) {
        let role = first(&[nonempty(tier, "role_group").as_deref(), Some("unknown")]);
        if let Some((_, current)) = roles.iter_mut().find(|(current, _)| current == &role) {
            if rating(tier) > rating(current) {
                *current = tier;
            }
        } else {
            roles.push((role, tier));
        }
    }
    roles.into_iter().map(|(_, tier)| tier).collect()
}

fn rating(row: &Row) -> f64 {
    get(row, "rating").parse().unwrap_or(-1.0)
}

fn build_phase_info(phases: &[Row], context: &VisualizerContext) -> Vec<Value> {
    let mut chosen: BTreeMap<(String, String, String), &Row> = BTreeMap::new();
    for row in phases {
        let key: (String, String, String) = (
            get(row, "mode").into(),
            get(row, "phase_ver").into(),
            get(row, "phase_name").into(),
        );
        if key.0.is_empty() || key.1.is_empty() {
            continue;
        }
        if chosen
            .get(&key)
            .is_none_or(|current| get(row, "collect_date") >= get(current, "collect_date"))
        {
            chosen.insert(key, row);
        }
    }
    chosen.into_iter().map(|((mode,ver,name),row)| {
        let (mechanic_name,mechanic_text,mechanic_source,mechanic_url)=mechanic(&mode,&ver,&name);
        json!({"mode":mode,"mode_cn":first(&[nonempty(row,"mode_cn").as_deref(),Some(mode_cn(&mode))]),"snapshot_id":get(row,"snapshot_id"),"collect_date":get(row,"collect_date"),"phase_ver":ver,"phase_name":name,"phase_name_cn":phase_name_cn(&mode,&name),"start_date":get(row,"start_date"),"end_date":get(row,"end_date"),"phase_status":phase_status(get(row,"start_date"),get(row,"end_date"),context),"source":get(row,"source"),"source_path":get(row,"source_path"),"mechanic_name":mechanic_name,"mechanic_text":mechanic_text,"mechanic_source":mechanic_source,"mechanic_url":safe_link_url(mechanic_url),"source_note":get(row,"note")})
    }).collect()
}

fn build_banner(
    context: &VisualizerContext,
    roster: &[Value],
    local_datetime: chrono::NaiveDateTime,
) -> Result<Vec<Value>> {
    let Some(bytes) = context.sidecar("hsr_banner_plan.json") else {
        return Ok(vec![]);
    };
    let text = strict_utf8(bytes, "hsr_banner_plan.json")?;
    validate_json_surrogate_escapes(text, "hsr_banner_plan.json")?;
    let root: Value = serde_json::from_str(text).map_err(|source| MihoError::Json {
        path: "hsr_banner_plan.json".into(),
        source,
    })?;
    let lookup = roster_lookup(roster);
    let mut output = vec![];
    for phase in root
        .get("phases")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let status = shared_effective_banner_status(phase, local_datetime)?;
        for (index, ch) in phase
            .get("characters")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .enumerate()
        {
            let slug = canonical(ch.get("slug").and_then(Value::as_str).unwrap_or(""));
            if slug.is_empty() {
                continue;
            }
            let r = lookup.get(&slug);
            let cv = |k| ch.get(k).and_then(Value::as_str).unwrap_or("");
            let pv = |k| phase.get(k).and_then(Value::as_str).unwrap_or("");
            let source_url_value = [ch.get("source_url"), phase.get("source_url")]
                .into_iter()
                .flatten()
                .find(|value| python_value_truthy(value));
            let source_url = safe_link_url(&python_scalar_text(source_url_value));
            let source_label = [ch.get("source_label"), phase.get("source_label")]
                .into_iter()
                .flatten()
                .find(|value| python_value_truthy(value))
                .cloned()
                .unwrap_or_else(|| Value::String(String::new()));
            let roster_icon = r
                .and_then(|value| value.get("icon_url"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let icon_url = if context.avatar_webp(&slug).is_some() {
                local_avatar_url(context, &slug)
            } else {
                first(&[
                    nonempty_text(&safe_relative_url(&python_scalar_text(ch.get("icon_url"))))
                        .as_deref(),
                    nonempty_text(&safe_relative_url(roster_icon)).as_deref(),
                ])
            };
            output.push(json!({"phase_id":pv("id"),"phase_status":status,"phase_title":pv("title"),"phase_subtitle":pv("subtitle"),"date_range":pv("date_range"),"source_label":source_label,"source_url":source_url,"slot":index+1,"character_slug":slug,"character_name_cn":first(&[Some(cv("name_cn")),r.and_then(|v|v.get("character_name_cn")).and_then(Value::as_str)]),"character_name_en":first(&[Some(cv("name_en")),r.and_then(|v|v.get("character_name_en")).and_then(Value::as_str)]),"banner_role":cv("banner_role"),"rarity":first(&[Some(cv("rarity")),r.and_then(|v|v.get("rarity")).and_then(Value::as_str)]),"element_cn":first(&[Some(cv("element_cn")),r.and_then(|v|v.get("element_cn")).and_then(Value::as_str)]),"path_cn":first(&[Some(cv("path_cn")),r.and_then(|v|v.get("path_cn")).and_then(Value::as_str)]),"role_group_cns":first(&[Some(cv("role_group_cns")),r.and_then(|v|v.get("role_group_cns")).and_then(Value::as_str)]),"icon_url":icon_url,"analysis_tags":ch.get("analysis_tags").cloned().unwrap_or_else(||json!([])),"focus":cv("focus")}));
        }
    }
    Ok(output)
}

fn merge_banner_into_roster(roster: &mut Vec<Value>, banner: &[Value]) {
    let mut by_slug: BTreeMap<String, Value> = roster
        .drain(..)
        .map(|v| (v["character_slug"].as_str().unwrap_or("").into(), v))
        .collect();
    let mut next_order = by_slug
        .values()
        .filter_map(|value| value.get("release_order").and_then(Value::as_u64))
        .max()
        .unwrap_or(0)
        + 1;
    for b in banner {
        let slug = b["character_slug"].as_str().unwrap_or("");
        if slug.is_empty() {
            continue;
        }
        if !by_slug.contains_key(slug) {
            by_slug.insert(
                slug.into(),
                json!({
                    "character_slug": slug,
                    "deployment_group": deployment_group(slug),
                    "character_name_en": first(&[b["character_name_en"].as_str(), Some(slug)]),
                    "character_name_cn": b["character_name_cn"].as_str().unwrap_or(""),
                    "element_cn": b["element_cn"].as_str().unwrap_or(""),
                    "element_en": "",
                    "path_cn": b["path_cn"].as_str().unwrap_or(""),
                    "path_en": "",
                    "rarity": b["rarity"].as_str().unwrap_or(""),
                    "icon_url": b["icon_url"].as_str().unwrap_or(""),
                    "release_order": next_order,
                    "role_groups": "unknown",
                    "role_group_cns": first(&[b["role_group_cns"].as_str(), Some("未分类")]),
                    "alias_slugs": slug,
                    "source": "banner_plan",
                    "banner_statuses": b["phase_status"].as_str().unwrap_or(""),
                    "banner_phase_titles": b["phase_title"].as_str().unwrap_or(""),
                }),
            );
            next_order += 1;
            continue;
        }
        let r = by_slug
            .get_mut(slug)
            .and_then(Value::as_object_mut)
            .expect("existing roster entry must be an object");
        merge_field(
            r,
            "banner_statuses",
            b["phase_status"].as_str().unwrap_or(""),
        );
        merge_field(
            r,
            "banner_phase_titles",
            b["phase_title"].as_str().unwrap_or(""),
        );
        for key in [
            "character_name_cn",
            "character_name_en",
            "element_cn",
            "path_cn",
            "rarity",
            "icon_url",
            "role_group_cns",
        ] {
            if r.get(key).and_then(Value::as_str).unwrap_or("").is_empty() {
                if let Some(value) = b
                    .get(key)
                    .filter(|value| !value.as_str().unwrap_or("").is_empty())
                {
                    r.insert(key.into(), value.clone());
                }
            }
        }
    }
    *roster = by_slug.into_values().collect();
    roster.sort_by_key(|v| {
        (
            v["release_order"].as_u64().unwrap_or(99999),
            v["character_slug"].as_str().unwrap_or("").to_owned(),
        )
    });
}

fn build_teams(
    teams: &[Row],
    phases: &[Value],
    roster: &[Value],
    context: &VisualizerContext,
) -> Result<Vec<Value>> {
    let mut latest = HashMap::<String, String>::new();
    for row in teams {
        let mode = get(row, "mode");
        let collect_date = get(row, "collect_date");
        if !mode.is_empty()
            && !collect_date.is_empty()
            && collect_date >= latest.get(mode).map(String::as_str).unwrap_or("")
        {
            latest.insert(mode.into(), collect_date.into());
        }
    }

    let lookup = roster_lookup(roster);
    let phase_lookup = build_phase_lookup(phases);
    let mut grouped = Vec::<Value>::new();
    let mut grouped_indices = HashMap::<String, usize>::new();
    for row in teams {
        let mode = get(row, "mode");
        if mode.is_empty() || latest.get(mode).map(String::as_str) != Some(get(row, "collect_date"))
        {
            continue;
        }
        let chars = (1..=4)
            .map(|index| {
                let slug = canonical(get(row, &format!("char_{index}_slug")));
                lookup
                    .get(&slug)
                    .and_then(|value| value.get("character_slug"))
                    .and_then(Value::as_str)
                    .unwrap_or(&slug)
                    .to_owned()
            })
            .collect::<Vec<_>>();
        if chars.iter().any(String::is_empty) {
            continue;
        }
        let scope = get(row, "scope");
        let (scope_key, scope_label, scope_order) = scope_info(mode, scope);
        let phase = lookup_phase(&phase_lookup, row);
        let start_date = first(&[
            nonempty(row, "start_date").as_deref(),
            phase
                .and_then(|value| value.get("start_date"))
                .and_then(Value::as_str),
        ]);
        let end_date = first(&[
            nonempty(row, "end_date").as_deref(),
            phase
                .and_then(|value| value.get("end_date"))
                .and_then(Value::as_str),
        ]);
        let phase_status_value = first(&[
            nonempty(row, "phase_status").as_deref(),
            phase
                .and_then(|value| value.get("phase_status"))
                .and_then(Value::as_str),
            Some(phase_status(
                get(row, "start_date"),
                get(row, "end_date"),
                context,
            )),
        ]);
        let names_cn = chars
            .iter()
            .enumerate()
            .map(|(index, slug)| {
                first(&[
                    lookup
                        .get(slug)
                        .and_then(|value| value.get("character_name_cn"))
                        .and_then(Value::as_str),
                    Some(get(row, &format!("char_{}_name_cn", index + 1))),
                ])
            })
            .collect::<Vec<_>>();
        let template = json!({
            "mode": mode,
            "mode_cn": first(&[nonempty(row,"mode_cn").as_deref(), Some(mode_cn(mode))]),
            "scope_key": scope_key,
            "scope": scope,
            "scope_label": scope_label,
            "scope_order": scope_order,
            "snapshot_id": get(row,"snapshot_id"),
            "collect_date": get(row,"collect_date"),
            "phase_ver": get(row,"phase_ver"),
            "phase_name": get(row,"phase_name"),
            "phase_name_cn": phase_name_cn(mode,get(row,"phase_name")),
            "start_date": start_date,
            "end_date": end_date,
            "phase_status": phase_status_value,
            "rank": numeric(get(row,"rank"))?,
            "app_rate": numeric(get(row,"app_rate"))?,
            "avg_round": numeric(get(row,"avg_round"))?,
            "source_kind": get(row,"source_kind"),
            "source_file": get(row,"source_file"),
            "chars": chars,
            "names_cn": names_cn,
        });
        let mut signature_chars = chars.clone();
        signature_chars.sort();
        let key = format!("{mode}|{}|{}", scope_key, signature_chars.join(">"));
        if let Some(index) = grouped_indices.get(&key).copied() {
            if template_cmp(&template, &grouped[index]).is_lt() {
                grouped[index] = template;
            }
        } else {
            grouped_indices.insert(key, grouped.len());
            grouped.push(template);
        }
    }

    let mut per_scope = Vec::<((String, String), Vec<Value>)>::new();
    let mut per_scope_indices = HashMap::<(String, String), usize>::new();
    for template in grouped {
        let key = (
            value_str(&template, "mode").into(),
            value_str(&template, "scope_key").into(),
        );
        if let Some(index) = per_scope_indices.get(&key).copied() {
            per_scope[index].1.push(template);
        } else {
            per_scope_indices.insert(key.clone(), per_scope.len());
            per_scope.push((key, vec![template]));
        }
    }
    let mut output = Vec::new();
    for ((_mode, scope_key), mut rows) in per_scope {
        rows.sort_by(template_cmp);
        if scope_key == "all" {
            output.extend(rows.into_iter().take(240));
        } else {
            output.extend(rows);
        }
    }
    output.sort_by(|left, right| {
        value_str(left, "mode")
            .cmp(value_str(right, "mode"))
            .then_with(|| {
                left["scope_order"]
                    .as_u64()
                    .unwrap_or(99)
                    .cmp(&right["scope_order"].as_u64().unwrap_or(99))
            })
            .then_with(|| template_cmp(left, right))
    });
    Ok(output)
}

fn build_phase_lookup(phases: &[Value]) -> HashMap<(String, String, String), &Value> {
    let mut lookup = HashMap::new();
    for phase in phases {
        let mode = value_str(phase, "mode");
        let phase_ver = value_str(phase, "phase_ver");
        if mode.is_empty() || phase_ver.is_empty() {
            continue;
        }
        for tail in [
            value_str(phase, "phase_name"),
            value_str(phase, "collect_date"),
            "",
        ] {
            lookup
                .entry((mode.into(), phase_ver.into(), tail.into()))
                .or_insert(phase);
        }
    }
    lookup
}

fn lookup_phase<'a>(
    lookup: &'a HashMap<(String, String, String), &'a Value>,
    row: &Row,
) -> Option<&'a Value> {
    let mode = get(row, "mode");
    let version = get(row, "phase_ver");
    for tail in [get(row, "phase_name"), get(row, "collect_date"), ""] {
        if let Some(value) = lookup.get(&(mode.into(), version.into(), tail.into())) {
            return Some(*value);
        }
    }
    None
}

fn value_str<'a>(value: &'a Value, key: &str) -> &'a str {
    value.get(key).and_then(Value::as_str).unwrap_or("")
}

fn template_cmp(left: &Value, right: &Value) -> std::cmp::Ordering {
    template_scope_priority(left)
        .cmp(&template_scope_priority(right))
        .then_with(|| template_source_priority(left).cmp(&template_source_priority(right)))
        .then_with(|| {
            template_number(left, "rank", 1_000_000.0).total_cmp(&template_number(
                right,
                "rank",
                1_000_000.0,
            ))
        })
        .then_with(|| {
            template_number(right, "app_rate", -1.0)
                .total_cmp(&template_number(left, "app_rate", -1.0))
        })
        .then_with(|| template_performance_cmp(left, right))
}

fn template_performance_cmp(left: &Value, right: &Value) -> std::cmp::Ordering {
    if value_str(left, "mode") == "aa" {
        return std::cmp::Ordering::Equal;
    }
    let left_value = template_valid_performance(left);
    let right_value = template_valid_performance(right);
    match (left_value, right_value) {
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => std::cmp::Ordering::Equal,
        (Some(left_value), Some(right_value)) => match value_str(left, "mode") {
            "moc" => left_value.total_cmp(&right_value),
            "pf" | "as" => right_value.total_cmp(&left_value),
            _ => std::cmp::Ordering::Equal,
        },
    }
}

fn template_valid_performance(value: &Value) -> Option<f64> {
    let performance = value.get("avg_round").and_then(Value::as_f64)?;
    (performance > 0.0 && (performance - 99.99).abs() > 0.001).then_some(performance)
}

fn template_scope_priority(value: &Value) -> u8 {
    let scope = normalize_scope(value_str(value, "scope"));
    u8::from(!scope.contains('-') || matches!(scope.as_str(), "all" | "top"))
}

fn template_source_priority(value: &Value) -> u8 {
    match value_str(value, "source_kind") {
        "hf_comps" => 0,
        "prydwen_page" => 1,
        _ => 2,
    }
}

fn template_number(value: &Value, key: &str, fallback: f64) -> f64 {
    value.get(key).and_then(Value::as_f64).unwrap_or(fallback)
}

fn row_map(row: &Row) -> Map<String, Value> {
    row.iter()
        .map(|(k, v)| (k.clone(), Value::String(v.clone())))
        .collect()
}
fn get<'a>(row: &'a Row, key: &str) -> &'a str {
    row.get(key).map(String::as_str).unwrap_or("")
}
fn nonempty(row: &Row, key: &str) -> Option<String> {
    let v = get(row, key);
    (!v.is_empty()).then(|| v.to_owned())
}
fn first(values: &[Option<&str>]) -> String {
    values
        .iter()
        .flatten()
        .find(|v| !v.is_empty())
        .copied()
        .unwrap_or("")
        .to_owned()
}
fn canonical(v: &str) -> String {
    match character_slug(v).as_str() {
        "blade-mortenax" => "mortenax-blade",
        "imbibitor-lunae" => "dan-heng-imbibitor-lunae",
        "march-7th-evernight" => "evernight",
        "march-7th-swordmaster" => "march-7th-the-hunt",
        "silver-wolf-lv-999" => "silver-wolf-lv999",
        "tingyun-fugue" => "fugue",
        "topaz" => "topaz-and-numby",
        "trailblazer-destruction" => "trailblazer-the-destruction",
        "trailblazer-harmony" => "trailblazer-the-harmony",
        "trailblazer-preservation" => "trailblazer-the-preservation",
        _ => return character_slug(v),
    }
    .into()
}

fn deployment_group(slug: &str) -> &str {
    if slug == "march-7th" || matches!(slug, "march-7th-swordmaster" | "march-7th-the-hunt") {
        "march-7th"
    } else if slug == "trailblazer" || slug.starts_with("trailblazer-") {
        "trailblazer"
    } else {
        slug
    }
}
fn role_order(v: &str) -> u8 {
    match v {
        "main_dps" => 0,
        "sub_dps" => 1,
        "support" => 2,
        "sustain" => 3,
        "unknown" => 9,
        _ => 9,
    }
}
fn role_cn(v: &str) -> &str {
    match v {
        "main_dps" => "主C",
        "sub_dps" => "副C",
        "support" => "辅助",
        "sustain" => "生存位",
        "unknown" => "未分类",
        _ => v,
    }
}
fn element_cn(v: &str) -> &str {
    match v {
        "Physical" => "物理",
        "Fire" => "火",
        "Ice" => "冰",
        "Lightning" => "雷",
        "Wind" => "风",
        "Quantum" => "量子",
        "Imaginary" => "虚数",
        _ => "",
    }
}
fn path_cn(v: &str) -> &str {
    match v {
        "Destruction" => "毁灭",
        "Hunt" => "巡猎",
        "Erudition" => "智识",
        "Harmony" => "同谐",
        "Nihility" => "虚无",
        "Preservation" => "存护",
        "Abundance" => "丰饶",
        "Remembrance" => "记忆",
        "Elation" => "欢愉",
        _ => "",
    }
}
fn mode_cn(v: &str) -> &str {
    match v {
        "moc" => "混沌回忆",
        "pf" => "虚构叙事",
        "as" => "末日幻影",
        "aa" => "异相仲裁",
        _ => v,
    }
}
fn phase_name_cn(mode: &str, name: &str) -> &'static str {
    match (mode, name) {
        ("moc", "Breached Nest") => "堤溃蚁穴",
        ("moc", "Cyber Mystery") => "网络谜踪",
        ("moc", "Grand Finale") => "演剧终焉",
        ("moc", "Duty Action") => "值日行动",
        ("pf", "Wordless Novel") => "无字小说",
        ("pf", "Virtual Made Manifest") => "虚境成章",
        ("pf", "Illusory Concepts") => "造象立说",
        ("pf", "Falsehood to Fact") => "借虚成真",
        ("as", "Dominance of Netherveil") => "支配冥茫",
        ("as", "Militant Lupine") => "兵锋天狼",
        ("as", "Idol of the Locusts") => "偶像螟蝗",
        ("as", "Gale of Forgetting") => "遗忘冽风",
        ("aa", "Cyber Crisis") => "网络风波",
        ("aa", "Don't Mess With Pom-Pom") => "别惹帕姆",
        ("aa", "Happiness Syntax") => "幸福语法",
        ("aa", "The Humming Laughter") => "嗡鸣如笑",
        _ => "",
    }
}
fn phase_status(start: &str, end: &str, ctx: &VisualizerContext) -> &'static str {
    let parse =
        |v: &str| chrono::NaiveDate::parse_from_str(v.get(..10).unwrap_or(v), "%Y-%m-%d").ok();
    if parse(end).is_some_and(|d| d < ctx.local_date) {
        "expired"
    } else if parse(start).is_some_and(|d| d > ctx.local_date) {
        "future"
    } else if parse(start).is_some() || parse(end).is_some() {
        "current"
    } else {
        "unknown"
    }
}
fn mechanic(
    mode: &str,
    version: &str,
    name: &str,
) -> (&'static str, &'static str, &'static str, &'static str) {
    match (mode, version, name) {
        ("moc", "4.2.1", "Duty Action") => (
            "记忆紊流",
            "我方目标施放终结技时造成的暴击伤害提高50%。施放终结技后为「记忆紊流」增加2段攻击段数，最多叠加20段。每个轮开始时，「记忆紊流」的每段攻击对随机敌方目标造成1次真实伤害。",
            "官方 4.2 版本更新说明",
            "https://hsr.hoyoverse.com/zh-cn/news/163625",
        ),
        ("pf", "4.3.1", "Falsehood to Fact") => (
            "怪诞逸闻 / 荒腔走板",
            "战意机制：我方目标为敌方目标施加负面效果时，使我方额外累积1点「战意值」，每个敌方目标最多触发10次。战熄潮平：敌方效果抵抗降低30%，陷入4个及以上负面效果的敌方受到伤害提高20%。荒腔走板包含「触技」「笑韵」「变奏」三类可选增益。",
            "BWIKI 近期深渊总览",
            "https://wiki.biligame.com/sr/%E8%BF%91%E6%9C%9F%E6%B7%B1%E6%B8%8A%E6%80%BB%E8%A7%88",
        ),
        ("as", "4.3.1", "Gale of Forgetting") => (
            "末法余烬 / 终焉公理",
            "末法余烬：我方施放终结技攻击敌方目标时，为目标附上「爆裂」，最多叠加6层。目标回合开始或被消灭时，根据「爆裂」层数对该目标及其相邻目标造成固定数值伤害。各首领另有可选「终焉公理」增益。",
            "BWIKI 近期深渊总览",
            "https://wiki.biligame.com/sr/%E8%BF%91%E6%9C%9F%E6%B7%B1%E6%B8%8A%E6%80%BB%E8%A7%88",
        ),
        ("aa", "4.3.1", "The Humming Laughter") => (
            "异相仲裁规则 / 裁决象限",
            "骑士关含独立异常效果：骑士一入战固定降低我方50%能量，并使回合外能量恢复效率降低50%，持续2回合；敌方受击后叠加减伤/降暴伤，追加攻击或阿哈时刻可削层。骑士二我方造成伤害降低20%、受到伤害降低10%。骑士三我方回合开始损失500生命值，可致命。王棋关另有裁决象限增益。",
            "BWIKI 仲裁一览",
            "https://wiki.biligame.com/sr/%E4%BB%B2%E8%A3%81%E4%B8%80%E8%A7%88",
        ),
        _ => ("", "", "", ""),
    }
}
fn roster_lookup(rows: &[Value]) -> HashMap<String, &Value> {
    let mut lookup = HashMap::new();
    for value in rows {
        let slug = value_str(value, "character_slug");
        if !slug.is_empty() {
            lookup.insert(slug.into(), value);
            lookup.insert(canonical(slug), value);
        }
        for alias in value_str(value, "alias_slugs").split(';') {
            let alias = canonical(alias);
            if !alias.is_empty() {
                lookup.insert(alias, value);
            }
        }
    }
    lookup
}
fn merge_field(map: &mut Map<String, Value>, key: &str, value: &str) {
    if value.is_empty() {
        return;
    }
    let current = map.get(key).and_then(Value::as_str).unwrap_or("");
    let mut items = current
        .split(';')
        .filter(|v| !v.is_empty())
        .collect::<Vec<_>>();
    if !items.contains(&value) {
        items.push(value)
    }
    map.insert(key.into(), items.join(";").into());
}
fn numeric(v: &str) -> Result<Value> {
    if v.is_empty() {
        Ok(Value::Null)
    } else if let Ok(f) = v.parse::<f64>() {
        if !f.is_finite() {
            Err(MihoError::Visualizer(format!(
                "non-finite visualizer number: {v:?}"
            )))
        } else if f.fract() == 0.0 && f >= i64::MIN as f64 && f <= i64::MAX as f64 {
            Ok(Value::from(f as i64))
        } else {
            Ok(Number::from_f64(f).map_or(Value::Null, Value::Number))
        }
    } else {
        Ok(Value::Null)
    }
}
fn scope_info(mode: &str, scope: &str) -> (String, String, u64) {
    let normalized = normalize_scope(scope);
    if matches!(normalized.as_str(), "" | "all" | "top") {
        return ("all".into(), "综合队伍池".into(), 90);
    }
    match (mode, normalized.as_str()) {
        ("moc", "1" | "12-1" | "stage-12-1") => ("12-1".into(), "12-1 / 上半".into(), 1),
        ("moc", "2" | "12-2" | "stage-12-2") => ("12-2".into(), "12-2 / 下半".into(), 2),
        ("moc", "3" | "12-3" | "stage-12-3") => {
            ("12-3".into(), "12-3 / 第3战斗侧（星芒）".into(), 3)
        }
        ("pf" | "as", "1" | "4-1" | "stage-4-1") => ("4-1".into(), "4-1 / 第1战斗侧".into(), 1),
        ("pf" | "as", "2" | "4-2" | "stage-4-2") => ("4-2".into(), "4-2 / 第2战斗侧".into(), 2),
        ("pf" | "as", "3" | "4-3" | "stage-4-3") => {
            ("4-3".into(), "4-3 / 第3战斗侧（星芒）".into(), 3)
        }
        ("aa", "1" | "1-1") => ("1-1".into(), "1-1 / 骑士 1".into(), 1),
        ("aa", "2" | "1-2") => ("1-2".into(), "1-2 / 骑士 2".into(), 2),
        ("aa", "3" | "1-3") => ("1-3".into(), "1-3 / 骑士 3".into(), 3),
        ("aa", "4" | "2-1") => ("2-1".into(), "2-1 / 王棋".into(), 4),
        _ => (normalized, scope.to_owned(), 50),
    }
}

fn normalize_scope(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut separator = false;
    for ch in value.trim().to_ascii_lowercase().chars() {
        if ch.is_ascii_alphanumeric() {
            if separator && !output.is_empty() {
                output.push('-');
            }
            separator = false;
            output.push(ch);
        } else {
            separator = true;
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    const AVATAR: &[u8] = &[
        82, 73, 70, 70, 30, 0, 0, 0, 87, 69, 66, 80, 86, 80, 56, 76, 17, 0, 0, 0, 47, 1, 64, 0, 0,
        7, 208, 177, 150, 116, 189, 255, 129, 136, 232, 127, 0, 0,
    ];

    fn row(values: &[(&str, &str)]) -> Row {
        values
            .iter()
            .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
            .collect()
    }

    #[test]
    fn attach_requires_an_explicit_local_datetime() {
        let mut bundle = ArtifactBundle::default();
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let error = attach_hsr_visualizer(&mut bundle, &context).unwrap_err();
        assert!(error.to_string().contains("explicit local datetime"));
    }

    #[test]
    fn invalid_utf8_in_hoyowiki_and_banner_inputs_is_not_silently_ignored() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_bytes(
                "raw/hoyowiki/hsr_characters_en-us.json",
                vec![b'[', 0xff, b']'],
            )
            .unwrap();
        let context = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        let error = build_roster(&bundle, &[], &[], &[], &context).unwrap_err();
        assert!(error
            .to_string()
            .contains("invalid UTF-8 in raw/hoyowiki/hsr_characters_en-us.json"));

        let mut context = context;
        context
            .add_sidecar_bytes("hsr_banner_plan.json", vec![b'{', 0xff, b'}'])
            .unwrap();
        let error =
            build_banner(&context, &[], context.require_local_datetime().unwrap()).unwrap_err();
        assert!(error
            .to_string()
            .contains("invalid UTF-8 in hsr_banner_plan.json"));
    }

    #[test]
    fn official_roster_uses_joined_source_order_and_skips_rows_without_english_names() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_text(
                "raw/hoyowiki/hsr_characters_en-us.json",
                r#"[
                    {"entry_page_id":"2","name":"Agent Two","filter_values":{"character_rarity":{"values":["4-star","5-star"]},"character_combat_type":{"values":["Fire","Ice"]},"character_paths":{"values":["Harmony","Hunt"]}}},
                    {"entry_page_id":"1","name":"Agent One"},
                    {"entry_page_id":"3","name":""}
                ]"#,
            )
            .unwrap();
        bundle
            .add_text(
                "raw/hoyowiki/hsr_characters_zh-cn.json",
                r#"[
                    {"entry_page_id":"2","name":"代理二","filter_values":{"character_rarity":{"values":["四星"]},"character_combat_type":{"values":["火"]},"character_paths":{"values":["同谐"]}}},
                    {"entry_page_id":"1","name":"代理一"},
                    {"entry_page_id":"3","name":"仅中文"}
                ]"#,
            )
            .unwrap();
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let rows = build_roster(&bundle, &[], &[], &[], &context).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0]["character_slug"], "agent-two");
        assert_eq!(rows[0]["release_order"], 0);
        assert_eq!(rows[0]["character_name_cn"], "代理二");
        assert_eq!(rows[0]["element_cn"], "火");
        assert_eq!(rows[0]["element_en"], "Fire");
        assert_eq!(rows[0]["path_cn"], "同谐");
        assert_eq!(rows[0]["path_en"], "Harmony");
        assert_eq!(rows[0]["rarity"], "4");
        assert_eq!(rows[0]["source"], "HoYoWiki");
        assert_eq!(rows[1]["character_slug"], "agent-one");
        assert_eq!(rows[1]["release_order"], 1);
    }

    #[test]
    fn official_roster_merges_tier_alias_roles_icon_and_usage_fallbacks() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_text(
                "raw/hoyowiki/hsr_characters_en-us.json",
                r#"[{"entry_page_id":"7","name":"Topaz"}]"#,
            )
            .unwrap();
        bundle
            .add_text(
                "raw/hoyowiki/hsr_characters_zh-cn.json",
                r#"[{"entry_page_id":"7"}]"#,
            )
            .unwrap();
        let tiers = vec![
            row(&[
                ("character_slug", "topaz"),
                ("character_name_en", "Topaz and Numby"),
                ("element", "Fire"),
                ("path", "Hunt"),
                ("role_group", "support"),
                ("icon_url", "https://www.prydwen.gg/topaz.webp"),
            ]),
            row(&[
                ("character_slug", "topaz-and-numby"),
                ("role_group", "main_dps"),
            ]),
        ];
        let usage = vec![row(&[
            ("character_slug", "topaz-and-numby"),
            ("character_name_cn", "托帕&账账"),
        ])];
        let mut context = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        context.add_avatar_webp("topaz-and-numby", AVATAR).unwrap();

        let rows = build_roster(&bundle, &tiers, &usage, &[], &context).unwrap();
        assert_eq!(rows.len(), 1);
        let topaz = &rows[0];
        assert_eq!(topaz["character_slug"], "topaz-and-numby");
        assert_eq!(topaz["character_name_en"], "Topaz");
        assert_eq!(topaz["character_name_cn"], "托帕&账账");
        assert_eq!(topaz["element_en"], "Fire");
        assert_eq!(topaz["element_cn"], "火");
        assert_eq!(topaz["path_en"], "Hunt");
        assert_eq!(topaz["path_cn"], "巡猎");
        assert_eq!(topaz["role_groups"], "main_dps;support");
        assert_eq!(topaz["role_group_cns"], "主C;辅助");
        assert_eq!(topaz["alias_slugs"], "topaz-and-numby;topaz");
        assert_eq!(topaz["source"], "HoYoWiki;Prydwen");
        assert_eq!(topaz["icon_url"], "./assets/avatars/topaz-and-numby.webp");
    }

    #[test]
    fn phase_names_mechanics_scopes_and_numbers_match_python() {
        for (mode, name, expected) in [
            ("moc", "Breached Nest", "堤溃蚁穴"),
            ("moc", "Cyber Mystery", "网络谜踪"),
            ("moc", "Grand Finale", "演剧终焉"),
            ("moc", "Duty Action", "值日行动"),
            ("pf", "Wordless Novel", "无字小说"),
            ("pf", "Virtual Made Manifest", "虚境成章"),
            ("pf", "Illusory Concepts", "造象立说"),
            ("pf", "Falsehood to Fact", "借虚成真"),
            ("as", "Dominance of Netherveil", "支配冥茫"),
            ("as", "Militant Lupine", "兵锋天狼"),
            ("as", "Idol of the Locusts", "偶像螟蝗"),
            ("as", "Gale of Forgetting", "遗忘冽风"),
            ("aa", "Cyber Crisis", "网络风波"),
            ("aa", "Don't Mess With Pom-Pom", "别惹帕姆"),
            ("aa", "Happiness Syntax", "幸福语法"),
            ("aa", "The Humming Laughter", "嗡鸣如笑"),
        ] {
            assert_eq!(phase_name_cn(mode, name), expected);
        }
        for (mode, version, name) in [
            ("moc", "4.2.1", "Duty Action"),
            ("pf", "4.3.1", "Falsehood to Fact"),
            ("as", "4.3.1", "Gale of Forgetting"),
            ("aa", "4.3.1", "The Humming Laughter"),
        ] {
            let seeded = mechanic(mode, version, name);
            assert!(!seeded.0.is_empty());
            assert!(!seeded.1.is_empty());
            assert!(safe_link_url(seeded.3).starts_with("https://"));
        }
        assert_eq!(scope_info("moc", "stage_12_2").0, "12-2");
        assert_eq!(
            scope_info("moc", "stage_12_3"),
            ("12-3".into(), "12-3 / 第3战斗侧（星芒）".into(), 3)
        );
        assert_eq!(scope_info("pf", "stage_4_3").0, "4-3");
        assert_eq!(scope_info("pf", "top").1, "综合队伍池");
        assert_eq!(scope_info("as", "2").0, "4-2");
        assert_eq!(scope_info("aa", "4").1, "2-1 / 王棋");
        assert_eq!(numeric("1.0").unwrap(), json!(1));
        assert_eq!(numeric("1.25").unwrap(), json!(1.25));
        assert!(numeric("NaN").is_err());
    }

    #[test]
    fn usage_selects_best_tier_per_role_and_expands_untiered_roles() {
        let tiers = vec![
            row(&[
                ("character_slug", "agent-one"),
                ("tier_mode", "moc"),
                ("role_group", "main_dps"),
                ("role_group_cn", "主C"),
                ("tier", "T1"),
                ("rating", "7"),
            ]),
            row(&[
                ("character_slug", "agent-one"),
                ("tier_mode", "moc"),
                ("role_group", "main_dps"),
                ("role_group_cn", "主C"),
                ("tier", "T0"),
                ("rating", "9"),
            ]),
            row(&[
                ("character_slug", "agent-one"),
                ("tier_mode", "moc"),
                ("role_group", "support"),
                ("role_group_cn", "辅助"),
                ("tier", "T1"),
                ("rating", "8"),
            ]),
        ];
        let roster = vec![json!({
            "character_slug":"agent-one",
            "character_name_en":"Agent One",
            "character_name_cn":"代理一",
            "role_groups":"main_dps;support",
            "alias_slugs":"agent-one;agent-1",
            "icon_url":"./assets/avatars/agent-one.webp",
            "element_cn":"火","element_en":"Fire","path_cn":"巡猎","path_en":"Hunt","rarity":"5"
        })];
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let moc = vec![row(&[
            ("mode", "moc"),
            ("sub_mode", "all"),
            ("character_slug", "agent-one"),
        ])];
        let rows = build_usage(&moc, &tiers, &roster, &context);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0]["rating"], "9");
        assert_eq!(rows[1]["rating"], "8");

        let aa = vec![row(&[
            ("mode", "aa"),
            ("sub_mode", "all_bosses"),
            ("character_slug", "agent-one"),
        ])];
        let rows = build_usage(&aa, &tiers, &roster, &context);
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().all(|value| value["tier"] == "未分档"));
        assert!(rows.iter().all(|value| value["rating"] == ""));
        assert_eq!(rows[0]["icon_url"], "./assets/avatars/agent-one.webp");
    }

    #[test]
    fn banner_status_and_banner_only_roster_follow_python() {
        let mut context = VisualizerContext::new_with_local_datetime(
            chrono::NaiveDate::from_ymd_opt(2026, 7, 12)
                .unwrap()
                .and_hms_opt(13, 0, 0)
                .unwrap(),
        );
        context
            .add_sidecar_bytes(
                "hsr_banner_plan.json",
                r#"{"phases":[{
                    "id":"old","status":"current","date_range":"中文 1900/1/1 - 1900/1/2",
                    "title":"旧跃迁","characters":[{
                        "slug":"new-agent","name_cn":"新角色","name_en":"New Agent",
                        "rarity":"5","element_cn":"量子","path_cn":"智识","role_group_cns":"主C",
                        "source_url":1e-7,"icon_url":100000000000000000000000000000
                    },{
                        "slug":"huge-agent","name_cn":"大整数角色","name_en":"Huge Agent",
                        "source_url":100000000000000000000000000001
                    }]
                }]}"#
                    .as_bytes(),
            )
            .unwrap();
        let banner =
            build_banner(&context, &[], context.require_local_datetime().unwrap()).unwrap();
        assert_eq!(banner[0]["phase_status"], "previous");
        assert_eq!(banner[0]["source_url"], "1e-07");
        assert_eq!(banner[0]["icon_url"], "100000000000000000000000000000");
        assert_eq!(banner[1]["source_url"], "100000000000000000000000000001");
        let mut roster = vec![];
        merge_banner_into_roster(&mut roster, &banner);
        assert_eq!(roster.len(), 2);
        let new_agent = roster
            .iter()
            .find(|row| row["character_slug"] == "new-agent")
            .unwrap();
        assert_eq!(new_agent["source"], "banner_plan");
        assert_eq!(new_agent["banner_statuses"], "previous");
    }

    #[test]
    fn teams_use_exact_phase_dedupe_priority_and_aggregate_scope_limit() {
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let phases = build_phase_info(
            &[
                row(&[
                    ("mode", "moc"),
                    ("phase_ver", "4.2.1"),
                    ("phase_name", "Parallel Phase"),
                    ("collect_date", "2026-07-12"),
                    ("start_date", "2026-01-01"),
                    ("end_date", "2026-12-31"),
                ]),
                row(&[
                    ("mode", "moc"),
                    ("phase_ver", "4.2.1"),
                    ("phase_name", "Duty Action"),
                    ("collect_date", "2026-07-12"),
                    ("start_date", "1900-01-01"),
                    ("end_date", "1900-01-02"),
                ]),
            ],
            &context,
        );
        let mut first = row(&[
            ("mode", "moc"),
            ("scope", "1"),
            ("collect_date", "2026-07-12"),
            ("phase_ver", "4.2.1"),
            ("phase_name", "Duty Action"),
            ("rank", "2.0"),
            ("app_rate", "10"),
            ("avg_round", "4"),
            ("source_kind", "hf_comps"),
        ]);
        let mut second = first.clone();
        second.insert("rank".into(), "1".into());
        second.insert("source_kind".into(), "prydwen_page".into());
        for (index, slug) in ["a", "b", "c", "d"].iter().enumerate() {
            first.insert(format!("char_{}_slug", index + 1), (*slug).into());
        }
        for (index, slug) in ["d", "c", "b", "a"].iter().enumerate() {
            second.insert(format!("char_{}_slug", index + 1), (*slug).into());
        }
        let templates = build_teams(&[first, second], &phases, &[], &context).unwrap();
        assert_eq!(templates.len(), 1);
        assert_eq!(templates[0]["source_kind"], "hf_comps");
        assert_eq!(templates[0]["rank"], 2);
        assert_eq!(templates[0]["phase_status"], "expired");

        let tied_team = |prefix: &str| {
            let mut team = row(&[
                ("mode", "moc"),
                ("scope", "all"),
                ("collect_date", "2026-07-12"),
                ("rank", "1"),
                ("app_rate", "10"),
                ("avg_round", "4"),
                ("source_kind", "hf_comps"),
            ]);
            for slot in 1..=4 {
                team.insert(format!("char_{slot}_slug"), format!("{prefix}-{slot}"));
            }
            team
        };
        let tied = build_teams(
            &[tied_team("z-team"), tied_team("a-team")],
            &[],
            &[],
            &context,
        )
        .unwrap();
        assert_eq!(tied.len(), 2);
        assert_eq!(tied[0]["chars"][0], "z-team-1");
        assert_eq!(tied[1]["chars"][0], "a-team-1");

        let mut many = Vec::new();
        for index in 0..241 {
            let mut team = row(&[
                ("mode", "pf"),
                ("scope", "all"),
                ("collect_date", "2026-07-12"),
                ("phase_ver", "4.3.1"),
                ("rank", "1"),
            ]);
            for slot in 1..=4 {
                team.insert(format!("char_{slot}_slug"), format!("agent-{index}-{slot}"));
            }
            many.push(team);
        }
        assert_eq!(build_teams(&many, &[], &[], &context).unwrap().len(), 240);

        let mut many_concrete = Vec::new();
        for index in 0..1001 {
            let mut team = row(&[
                ("mode", "as"),
                ("scope", "4-1"),
                ("collect_date", "2026-07-12"),
                ("phase_ver", "4.3.1"),
                ("rank", "1"),
            ]);
            for slot in 1..=4 {
                team.insert(format!("char_{slot}_slug"), format!("agent-{index}-{slot}"));
            }
            many_concrete.push(team);
        }
        assert_eq!(
            build_teams(&many_concrete, &[], &[], &context)
                .unwrap()
                .len(),
            1001
        );
    }

    #[test]
    fn teams_dedupe_performance_by_mode_and_ignore_aa_direction() {
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        let team = |mode: &str, avg_round: &str| {
            let mut team = row(&[
                ("mode", mode),
                ("scope", "4-1"),
                ("collect_date", "2026-07-12"),
                ("rank", "1"),
                ("app_rate", "10"),
                ("avg_round", avg_round),
                ("source_kind", "hf_comps"),
            ]);
            for (index, slug) in ["a", "b", "c", "d"].iter().enumerate() {
                team.insert(format!("char_{}_slug", index + 1), (*slug).into());
            }
            team
        };

        let selected = |mode: &str, first: &str, second: &str| {
            build_teams(
                &[team(mode, first), team(mode, second)],
                &[],
                &[],
                &context,
            )
            .unwrap()
            .remove(0)["avg_round"]
                .as_f64()
                .unwrap()
        };
        assert_eq!(selected("moc", "8", "2"), 2.0);
        assert_eq!(selected("pf", "3000", "4000"), 4000.0);
        assert_eq!(selected("as", "3000", "4000"), 4000.0);
        assert_eq!(selected("aa", "1", "9999"), 1.0);
        assert_eq!(selected("pf", "99.99", "4000"), 4000.0);
        assert_eq!(selected("moc", "0", "2"), 2.0);
    }

    #[test]
    fn deployment_groups_only_merge_true_form_variants() {
        assert_eq!(deployment_group("trailblazer-harmony"), "trailblazer");
        assert_eq!(deployment_group("trailblazer-the-preservation"), "trailblazer");
        assert_eq!(deployment_group("march-7th"), "march-7th");
        assert_eq!(deployment_group("march-7th-swordmaster"), "march-7th");
        assert_eq!(deployment_group("march-7th-the-hunt"), "march-7th");
        assert_eq!(deployment_group("march-7th-evernight"), "march-7th-evernight");
        assert_eq!(deployment_group("evernight"), "evernight");
    }
}
