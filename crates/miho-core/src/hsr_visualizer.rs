use std::collections::{BTreeMap, HashMap};

use serde_json::{json, Map, Number, Value};

use crate::{
    normalize::character_slug,
    output::ArtifactBundle,
    visualizer::{
        attach_avatar_assets, attach_hsr_static_assets, compact_json, local_avatar_url,
        read_csv_rows, safe_link_url, safe_relative_url, VisualizerContext,
    },
    MihoError, Result,
};

type Row = BTreeMap<String, String>;

const TIER_KEEP: &[&str] = &["T0", "T0.5", "T1", "T1.5", "T2"];

pub fn attach_hsr_visualizer(
    bundle: &mut ArtifactBundle,
    context: &VisualizerContext,
) -> Result<()> {
    context.validate()?;
    reject_unported_official_roster(bundle)?;
    let trend = read_csv_rows(bundle, "prydwen_tier_usage_trend.csv")?;
    let tiers = read_csv_rows(bundle, "prydwen_tier_current.csv")?;
    let changelog = read_csv_rows(bundle, "prydwen_tier_changelog_history.csv")?;
    let charts = read_csv_rows(bundle, "prydwen_tier_charts.csv")?;
    let characters = read_csv_rows(bundle, "character_usage_long.csv")?;
    let teams = read_csv_rows(bundle, "team_rank_raw.csv")?;
    let names = read_csv_rows(bundle, "name_map.csv")?;
    let phases = read_csv_rows(bundle, "phase_index.csv")?;

    let mut roster = build_roster(&tiers, &characters, &names, context);
    let phase_info = build_phase_info(&phases, context);
    let banner = build_banner(context, &roster)?;
    merge_banner_into_roster(&mut roster, &banner);
    let usage = build_usage(&characters, &tiers, &roster, context);
    let trend_json = sanitize_avatar_rows(&trend, context);
    let data = json!({
        "meta": {
            "generatedAt": latest(&tiers, "fetched_at"),
            "tierUpdatedAt": latest(&tiers, "tier_updated_at"),
            "tierUpdatedDate": latest(&tiers, "tier_updated_date"),
            "localDate": context.local_date.to_string(),
            "source": "Prydwen Tier List + local MocStats processed dataset + HoYoWiki roster",
        },
        "trendRows": trend_json,
        "usageRows": if usage.is_empty() { sanitize_avatar_rows(&trend, context) } else { usage },
        "tierRows": sanitize_tier_rows(&tiers, context),
        "changelogRows": sanitize_link_rows(&changelog, "source_url"),
        "chartRows": string_rows(&charts),
        "rosterRows": roster,
        "phaseInfoRows": phase_info,
        "teamTemplates": build_teams(&teams, &phase_info, &roster),
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

fn reject_unported_official_roster(bundle: &ArtifactBundle) -> Result<()> {
    if bundle
        .get("raw/hoyowiki/hsr_characters_zh-cn.json")
        .is_some()
        || bundle
            .get("raw/hoyowiki/hsr_characters_en-us.json")
            .is_some()
    {
        return Err(MihoError::Visualizer(
            "HSR HoYoWiki roster merge is not yet migrated; refusing a partial visualizer".into(),
        ));
    }
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

fn sanitize_avatar_rows(rows: &[Row], context: &VisualizerContext) -> Vec<Value> {
    rows.iter()
        .map(|row| {
            let mut value = row_map(row);
            let slug = canonical(get(row, "character_slug"));
            value.insert("icon_url".into(), local_avatar_url(context, &slug).into());
            Value::Object(value)
        })
        .collect()
}

fn sanitize_tier_rows(rows: &[Row], context: &VisualizerContext) -> Vec<Value> {
    rows.iter()
        .map(|row| {
            let mut value = row_map(row);
            let slug = canonical(get(row, "character_slug"));
            value.insert("icon_url".into(), local_avatar_url(context, &slug).into());
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
    tiers: &[Row],
    usage: &[Row],
    names: &[Row],
    context: &VisualizerContext,
) -> Vec<Value> {
    let name_map = names
        .iter()
        .map(|row| (canonical(get(row, "character_slug")), row))
        .collect::<HashMap<_, _>>();
    let usage_map = usage
        .iter()
        .map(|row| (canonical(get(row, "character_slug")), row))
        .collect::<HashMap<_, _>>();
    let mut grouped: BTreeMap<String, Vec<&Row>> = BTreeMap::new();
    for row in tiers {
        grouped
            .entry(canonical(get(row, "character_slug")))
            .or_default()
            .push(row);
    }
    for row in usage {
        grouped
            .entry(canonical(get(row, "character_slug")))
            .or_default();
    }
    grouped
        .into_iter()
        .filter(|(slug, _)| !slug.is_empty())
        .enumerate()
        .map(|(index, (slug, tier_rows))| {
            let tier = tier_rows.first().copied();
            let usage = usage_map.get(&slug).copied();
            let name = name_map.get(&slug).copied();
            let mut roles = tier_rows
                .iter()
                .map(|row| get(row, "role_group").to_owned())
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>();
            roles.sort_by_key(|role| role_order(role));
            roles.dedup();
            if roles.is_empty() {
                roles.push("unknown".into());
            }
            json!({
                "character_slug": slug,
                "character_name_en": first(&[tier.map(|r| get(r,"character_name_en")), usage.map(|r| get(r,"character_name_en")), Some(slug.as_str())]),
                "character_name_cn": first(&[tier.map(|r| get(r,"character_name_cn")), usage.map(|r| get(r,"character_name_cn")), name.map(|r| get(r,"character_name_cn"))]),
                "element_cn": element_cn(tier.map(|r| get(r,"element")).unwrap_or("")),
                "element_en": tier.map(|r| get(r,"element")).unwrap_or(""),
                "path_cn": path_cn(tier.map(|r| get(r,"path")).unwrap_or("")),
                "path_en": tier.map(|r| get(r,"path")).unwrap_or(""),
                "rarity": first(&[tier.map(|r| get(r,"rarity")), usage.map(|r| get(r,"rarity"))]),
                "icon_url": local_avatar_url(context, &slug),
                "release_order": 10001 + index,
                "role_groups": roles.join(";"),
                "role_group_cns": roles.iter().map(|role| role_cn(role)).collect::<Vec<_>>().join(";"),
                "alias_slugs": slug,
                "source": if tier.is_some() { "Prydwen" } else { "usage" },
            })
        })
        .collect()
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
        let matching = tiers
            .iter()
            .filter(|tier| {
                canonical(get(tier, "character_slug")) == slug
                    && get(tier, "tier_mode") == get(row, "mode")
            })
            .collect::<Vec<_>>();
        let selected = if matching.is_empty() {
            vec![None]
        } else {
            matching
                .into_iter()
                .filter(|tier| TIER_KEEP.contains(&get(tier, "tier")))
                .map(Some)
                .collect()
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
            output.push(json!({
                "tier_snapshot_id": tier.map(|t| get(t,"tier_snapshot_id")).unwrap_or(""),
                "tier_updated_date": tier.map(|t| get(t,"tier_updated_date")).unwrap_or(""),
                "tier_mode": get(row,"mode"), "tier_mode_cn": get(row,"mode_cn"),
                "sub_mode": get(row,"sub_mode"), "sub_mode_cn": get(row,"sub_mode_cn"),
                "character_slug": slug,
                "character_name_en": get(row,"character_name_en"), "character_name_cn": get(row,"character_name_cn"),
                "prydwen_role": tier.map(|t| get(t,"prydwen_role")).unwrap_or(""),
                "role_group": role, "role_group_cn": role_group_cn,
                "tier": tier.map(|t| get(t,"tier")).unwrap_or("未分档"),
                "rating": tier.map(|t| get(t,"rating")).unwrap_or(""),
                "tags": tier.map(|t| get(t,"tags")).unwrap_or(""), "marks": tier.map(|t| get(t,"marks")).unwrap_or(""),
                "collect_date": get(row,"collect_date"), "phase_ver": get(row,"phase_ver"), "phase_name": get(row,"phase_name"),
                "phase_name_cn": phase_name_cn(get(row,"mode"), get(row,"phase_name")),
                "app_rate": get(row,"app_rate"), "avg_round": get(row,"avg_round"), "quality_flag": get(row,"quality_flag"),
                "icon_url": local_avatar_url(context,&slug),
                "element_cn": r.and_then(|v|v.get("element_cn")).and_then(Value::as_str).unwrap_or(""),
                "element_en": r.and_then(|v|v.get("element_en")).and_then(Value::as_str).unwrap_or(""),
                "path_cn": r.and_then(|v|v.get("path_cn")).and_then(Value::as_str).unwrap_or(""),
                "path_en": r.and_then(|v|v.get("path_en")).and_then(Value::as_str).unwrap_or(""),
                "rarity": r.and_then(|v|v.get("rarity")).and_then(Value::as_str).unwrap_or(""),
            }));
        }
    }
    output
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

fn build_banner(context: &VisualizerContext, roster: &[Value]) -> Result<Vec<Value>> {
    let Some(bytes) = context.sidecar("hsr_banner_plan.json") else {
        return Ok(vec![]);
    };
    let root: Value = serde_json::from_slice(bytes).map_err(|source| MihoError::Json {
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
        let status = phase.get("status").and_then(Value::as_str).unwrap_or("");
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
            let source_url = first(&[Some(cv("source_url")), Some(pv("source_url"))]);
            output.push(json!({"phase_id":pv("id"),"phase_status":status,"phase_title":pv("title"),"phase_subtitle":pv("subtitle"),"date_range":pv("date_range"),"source_label":first(&[Some(cv("source_label")),Some(pv("source_label"))]),"source_url":safe_link_url(&source_url),"slot":index+1,"character_slug":slug,"character_name_cn":first(&[Some(cv("name_cn")),r.and_then(|v|v.get("character_name_cn")).and_then(Value::as_str)]),"character_name_en":first(&[Some(cv("name_en")),r.and_then(|v|v.get("character_name_en")).and_then(Value::as_str)]),"banner_role":cv("banner_role"),"rarity":first(&[Some(cv("rarity")),r.and_then(|v|v.get("rarity")).and_then(Value::as_str)]),"element_cn":first(&[Some(cv("element_cn")),r.and_then(|v|v.get("element_cn")).and_then(Value::as_str)]),"path_cn":first(&[Some(cv("path_cn")),r.and_then(|v|v.get("path_cn")).and_then(Value::as_str)]),"role_group_cns":first(&[Some(cv("role_group_cns")),r.and_then(|v|v.get("role_group_cns")).and_then(Value::as_str)]),"icon_url":if context.avatar_webp(&slug).is_some(){local_avatar_url(context,&slug)}else{safe_relative_url(cv("icon_url"))},"analysis_tags":ch.get("analysis_tags").cloned().unwrap_or_else(||json!([])),"focus":cv("focus")}));
        }
    }
    Ok(output)
}

fn merge_banner_into_roster(roster: &mut Vec<Value>, banner: &[Value]) {
    let mut by_slug: BTreeMap<String, Value> = roster
        .drain(..)
        .map(|v| (v["character_slug"].as_str().unwrap_or("").into(), v))
        .collect();
    for b in banner {
        let slug = b["character_slug"].as_str().unwrap_or("");
        if let Some(r) = by_slug.get_mut(slug).and_then(Value::as_object_mut) {
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

fn build_teams(teams: &[Row], phases: &[Value], roster: &[Value]) -> Vec<Value> {
    let mut latest: HashMap<&str, &str> = HashMap::new();
    for r in teams {
        let m = get(r, "mode");
        let d = get(r, "collect_date");
        if d >= latest.get(m).copied().unwrap_or("") {
            latest.insert(m, d);
        }
    }
    let lookup = roster_lookup(roster);
    let mut out = vec![];
    for r in teams
        .iter()
        .filter(|r| get(r, "collect_date") == latest.get(get(r, "mode")).copied().unwrap_or(""))
    {
        let chars = (1..=4)
            .map(|i| canonical(get(r, &format!("char_{i}_slug"))))
            .collect::<Vec<_>>();
        if chars.iter().any(String::is_empty) {
            continue;
        }
        let mode = get(r, "mode");
        let scope = get(r, "scope");
        let (scope_key, scope_label, scope_order) = scope_info(mode, scope);
        let phase = phases
            .iter()
            .find(|p| p["mode"] == mode && p["phase_ver"] == get(r, "phase_ver"));
        out.push(json!({"mode":mode,"mode_cn":first(&[nonempty(r,"mode_cn").as_deref(),Some(mode_cn(mode))]),"scope_key":scope_key,"scope":scope,"scope_label":scope_label,"scope_order":scope_order,"snapshot_id":get(r,"snapshot_id"),"collect_date":get(r,"collect_date"),"phase_ver":get(r,"phase_ver"),"phase_name":get(r,"phase_name"),"phase_name_cn":phase_name_cn(mode,get(r,"phase_name")),"start_date":phase.and_then(|p|p["start_date"].as_str()).unwrap_or(""),"end_date":phase.and_then(|p|p["end_date"].as_str()).unwrap_or(""),"phase_status":phase.and_then(|p|p["phase_status"].as_str()).unwrap_or("unknown"),"rank":numeric(get(r,"rank")),"app_rate":numeric(get(r,"app_rate")),"avg_round":numeric(get(r,"avg_round")),"source_kind":get(r,"source_kind"),"source_file":get(r,"source_file"),"chars":chars,"names_cn":chars.iter().enumerate().map(|(i,s)|lookup.get(s).and_then(|v|v["character_name_cn"].as_str()).unwrap_or_else(||get(r,&format!("char_{}_name_cn",i+1))).to_owned()).collect::<Vec<_>>() }));
    }
    out.sort_by_key(|v| {
        (
            v["mode"].as_str().unwrap_or("").to_owned(),
            v["scope_order"].as_u64().unwrap_or(99),
            v["rank"].as_f64().unwrap_or(1e6).to_bits(),
        )
    });
    out
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
        ("moc", "Duty Action") => "值日行动",
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
    _m: &str,
    _v: &str,
    _n: &str,
) -> (&'static str, &'static str, &'static str, &'static str) {
    ("", "", "", "")
}
fn roster_lookup(rows: &[Value]) -> HashMap<String, &Value> {
    rows.iter()
        .filter_map(|v| v["character_slug"].as_str().map(|s| (s.to_owned(), v)))
        .collect()
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
fn numeric(v: &str) -> Value {
    if v.is_empty() {
        Value::Null
    } else if let Ok(i) = v.parse::<i64>() {
        i.into()
    } else if let Ok(f) = v.parse::<f64>() {
        Number::from_f64(f)
            .map(Value::Number)
            .unwrap_or(Value::Null)
    } else {
        Value::Null
    }
}
fn scope_info(mode: &str, scope: &str) -> (String, String, u64) {
    match (mode, scope) {
        ("moc", "1") => ("12-1".into(), "12-1 / 上半".into(), 1),
        ("moc", "2") => ("12-2".into(), "12-2 / 下半".into(), 2),
        (_, "" | "all" | "top") => ("all".into(), "全关".into(), 90),
        _ => (scope.into(), scope.into(), 50),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn official_roster_is_an_explicit_gate_until_its_merge_is_migrated() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_text("raw/hoyowiki/hsr_characters_zh-cn.json", "[]")
            .unwrap();
        let error = reject_unported_official_roster(&bundle).unwrap_err();
        assert!(error.to_string().contains("refusing a partial visualizer"));
    }
}
