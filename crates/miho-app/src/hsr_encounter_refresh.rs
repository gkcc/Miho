//! Anonymous official Lineup Assistant metadata and published clear records.
//! A published MoC round count belongs to the entire floor, never one side.
use std::collections::{BTreeMap, BTreeSet};

use anyhow::{anyhow, Context};
use chrono::{DateTime, FixedOffset, NaiveDate};
use miho_core::{network::HttpClient, output::ArtifactBundle, visualizer::read_csv_rows};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const BASE: &str = "https://sg-public-api.hoyolab.com/event/rpgsimulator";
const SOURCE: &str = "HoYoLAB 官方阵容助手公开投稿";

fn text<'a>(row: &'a Value, key: &str) -> &'a str {
    row.get(key).and_then(Value::as_str).unwrap_or("")
}
fn alias(value: &str) -> String {
    value
        .chars()
        .filter(|ch| !ch.is_whitespace())
        .map(|ch| {
            if matches!(ch, '•' | '・' | '·') {
                '·'
            } else {
                ch
            }
        })
        .collect::<String>()
        .to_lowercase()
}
fn date(value: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(value.get(..10)?, "%Y-%m-%d").ok()
}
fn response(text: &str) -> anyhow::Result<Value> {
    let root: Value = serde_json::from_str(text)?;
    if root.get("retcode").and_then(Value::as_i64) != Some(0) {
        return Err(anyhow!(
            "official public source rejected request: {}",
            root.get("retcode").unwrap_or(&Value::Null)
        ));
    }
    root.get("data")
        .filter(|value| value.is_object())
        .cloned()
        .ok_or_else(|| anyhow!("official public source has no data object"))
}
fn floor_tags(root: &Value, kind: &str) -> BTreeMap<u64, u64> {
    fn visit(value: &Value, found: &mut BTreeMap<u64, u64>) {
        if let Some(floor) = value.pointer("/extend/floor").and_then(Value::as_u64) {
            if floor > 0
                && floor <= 32
                && value.pointer("/extend/is_tierce").and_then(Value::as_bool) != Some(true)
            {
                if let Some(id) = value.get("id").and_then(Value::as_u64) {
                    found.entry(floor).or_insert(id);
                }
            }
        }
        if let Some(children) = value.get("children").and_then(Value::as_array) {
            for child in children {
                visit(child, found);
            }
        }
    }
    let mut found = BTreeMap::new();
    if let Some(tree) = root.get("tree").and_then(Value::as_array) {
        for entry in tree.iter().filter(|entry| text(entry, "root_type") == kind) {
            visit(entry, &mut found);
        }
    }
    found
}
fn key(group: &str, floor: u64, side: usize) -> String {
    format!("official:rpgsimulator:{group}:{floor}:{side}")
}
fn effects(schedule: &Value, mode: &str, side: usize, source_url: &str) -> Vec<Value> {
    let mut effects = Vec::new();
    let name = text(schedule, "maze_buff_name_mi18n");
    for line in text(schedule, "maze_buff_desc_mi18n")
        .split('\n')
        .filter(|line| !line.trim().is_empty())
    {
        effects.push(json!({"name":name,"text":line,"scope":"phase","verified":true,"source_url":source_url}));
    }
    let choice_key = if mode == "as" {
        format!("addition_buff_{side}")
    } else {
        "addition_buff".into()
    };
    if let Some(choices) = schedule.get(&choice_key).and_then(Value::as_array) {
        for choice in choices {
            effects.push(json!({"name":text(choice,"name"),"text":text(choice,"desc"),
                "scope":"choice","verified":true,"source_url":source_url,"choice_id":text(choice,"id")}));
        }
    }
    effects
}

fn normalize_records(
    payload: &Value,
    mode: &str,
    kind: &str,
    group: &str,
    floor: u64,
    phase_ver: &str,
    names: &BTreeMap<String, String>,
) -> Vec<Value> {
    let Some(rows) = payload.get("list").and_then(Value::as_array) else {
        return Vec::new();
    };
    let mut records = Vec::new();
    for row in rows {
        if text(row, "lineup_type") != kind
            || row.get("floor").and_then(Value::as_u64) != Some(floor)
            || row
                .pointer("/schedule_group/group_id")
                .and_then(Value::as_str)
                != Some(group)
            || row.get("is_deleted").and_then(Value::as_bool) != Some(false)
            || row.get("audit_status").and_then(Value::as_u64) != Some(1)
            || text(row, "publish_type") != "LineupPublishTypeRecord"
            || row.get("is_tierce").and_then(Value::as_bool) == Some(true)
            || row.get("star_num").and_then(Value::as_u64) != Some(3)
        {
            continue;
        }
        let Some(groups) = row.get("avatar_group").and_then(Value::as_array) else {
            continue;
        };
        // The public array carries no explicit side ID. Require both ordered sides
        // before binding its array index to an upper/lower encounter.
        if groups.len() != 2 {
            continue;
        }
        for (index, avatars) in groups.iter().enumerate() {
            let Some(avatars) = avatars.get("group").and_then(Value::as_array) else {
                continue;
            };
            if avatars.len() != 4 {
                continue;
            }
            let Some(chars): Option<Vec<_>> = avatars
                .iter()
                .map(|character| names.get(&alias(text(character, "item_name"))).cloned())
                .collect()
            else {
                continue;
            };
            if chars.iter().collect::<BTreeSet<_>>().len() != 4 {
                continue;
            }
            let (metric_kind, metric_scope, metric) = if mode == "moc" {
                (
                    "cycles",
                    "floor",
                    row.get("round_num").and_then(Value::as_f64),
                )
            } else {
                let info = if mode == "pf" {
                    "story_info"
                } else {
                    "boss_info"
                };
                let metric = row.pointer(&format!("/{info}/points")).and_then(|value| {
                    value
                        .as_f64()
                        .or_else(|| value.as_str().and_then(|text| text.parse::<f64>().ok()))
                });
                ("score", "floor", metric)
            };
            let Some(metric) = metric.filter(|value| value.is_finite() && *value >= 0.0) else {
                continue;
            };
            let id = text(row, "id");
            if id.is_empty() {
                continue;
            }
            let mut digest = Sha256::new();
            digest.update(format!(
                "{}|{group}|{floor}|{index}|{:?}|{}",
                row.get("account_uid").unwrap_or(&Value::Null),
                chars,
                row.get("challenge_time").unwrap_or(&Value::Null)
            ));
            let record_id = format!("{:x}", digest.finalize());
            let build = avatars.iter().map(|character| json!({
                "name":text(character,"item_name"),"eidolon":character.get("rank"),
                "level":character.get("level"),"equipment":character.get("equipment").map(|equipment| json!({
                    "name":text(equipment,"item_name"),"rank":equipment.get("rank")
                }))
            })).collect::<Vec<_>>();
            let post_id = row
                .get("post_id")
                .map(|id| match id {
                    Value::String(value) => value.clone(),
                    other => other.to_string(),
                })
                .unwrap_or_default();
            let source_url = if !post_id.is_empty()
                && post_id.bytes().all(|byte| byte.is_ascii_digit())
            {
                format!("https://www.hoyolab.com/article/{post_id}")
            } else {
                format!("{BASE}/lineup/index?group_id={group}&lineup_type={kind}&game=hkrpg&order=Hot&lang=zh-cn")
            };
            records.push(json!({"game":"hsr","mode":mode,"phase_ver":phase_ver,
                "encounter_key":key(group,floor,index+1),"chars":chars,
                "source_group":"hoyolab-lineup","record_id":record_id,
                "source_url":source_url,
                "source_label":SOURCE,"metric_kind":metric_kind,"metric_scope":metric_scope,
                "metric_value":metric,"evidence_grade":"B","is_quick_clear":false,
                "stars":row.get("star_num"),"build_context":build,
                "performance_note":if mode=="moc" {"成绩为上下两侧合计回合，不能作为单侧预测"} else {"成绩为整层合计得分，不能作为单侧预测"}
            }));
        }
    }
    records
}

pub(crate) async fn refresh(
    bundle: &mut ArtifactBundle,
    observed_at: DateTime<FixedOffset>,
) -> anyhow::Result<Vec<String>> {
    let client = HttpClient::new(std::time::Duration::from_secs(30), 1)?;
    let mut names = BTreeMap::new();
    for row in read_csv_rows(bundle, "name_map.csv")? {
        let Some(slug) = row.get("character_slug").filter(|slug| !slug.is_empty()) else {
            continue;
        };
        for field in ["character_name_cn", "character_name_en"] {
            if let Some(name) = row.get(field).filter(|name| !name.is_empty()) {
                names.insert(alias(name), slug.clone());
            }
        }
        if let Some(aliases) = row.get("aliases") {
            for name in aliases.split(['|', ';']) {
                if !name.trim().is_empty() {
                    names.entry(alias(name)).or_insert_with(|| slug.clone());
                }
            }
        }
    }
    let phases = read_csv_rows(bundle, "phase_index.csv")?;
    let tags_url = format!("{BASE}/tag?game=hkrpg&lang=zh-cn");
    let tags =
        response(&client.get_text(&tags_url).await?).context("HSR official floor directory")?;
    bundle.add_json("raw/hoyolab/encounters/tags-zh-cn.json", &tags)?;
    let mut encounters = Vec::new();
    let mut requests = Vec::new();
    let mut warnings = Vec::new();
    for (mode, kind, endpoint, label) in [
        ("moc", "Chasm", "schedule/list", "混沌回忆"),
        ("pf", "Story", "story_schedule/list", "虚构叙事"),
        ("as", "Boss", "boss_schedule/list", "末日幻影"),
    ] {
        // English names anchor the official schedule to the existing dataset;
        // Chinese names and effects are retained for display.
        let source_url = format!("{BASE}/{endpoint}?game=hkrpg&lang=zh-cn");
        let cn = response(&client.get_text(&source_url).await?)?;
        let en = response(
            &client
                .get_text(&format!("{BASE}/{endpoint}?game=hkrpg&lang=en-us"))
                .await?,
        )?;
        bundle.add_json(
            format!("raw/hoyolab/encounters/{mode}-schedules-zh-cn.json"),
            &cn,
        )?;
        let schedules = cn
            .get("schedule")
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow!("{mode}: missing official schedule"))?;
        let english = en
            .get("schedule")
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow!("{mode}: missing English schedule identity"))?;
        let floor_tags = floor_tags(&tags, kind);
        for schedule in schedules
            .iter()
            .filter(|row| row.get("is_now").and_then(Value::as_bool) == Some(true))
        {
            let group = text(schedule, "group_id");
            let Some(start) = date(text(schedule, "schedule_begin_time")) else {
                continue;
            };
            let Some(end) = date(text(schedule, "schedule_end_time")) else {
                continue;
            };
            if observed_at.date_naive() < start || observed_at.date_naive() > end {
                continue;
            }
            let english_name = english
                .iter()
                .find(|row| text(row, "group_id") == group)
                .map(|row| text(row, "name_mi18n"))
                .unwrap_or("");
            let matching = phases.iter().find(|phase| {
                phase.get("mode").map(String::as_str) == Some(mode)
                    && phase.get("phase_name").map(|name| alias(name)) == Some(alias(english_name))
                    && phase.get("start_date").map(String::as_str) == Some(&start.to_string())
            });
            let phase_ver = matching
                .and_then(|row| row.get("phase_ver"))
                .cloned()
                .unwrap_or_else(|| format!("official-{group}"));
            let max = schedule
                .get("floor_nums")
                .and_then(Value::as_u64)
                .unwrap_or(0)
                .min(32);
            for floor in 1..max {
                let Some(tag) = floor_tags.get(&floor).copied() else {
                    continue;
                };
                for side in 1..=2 {
                    encounters.push(json!({"game":"hsr","mode":mode,"phase_ver":phase_ver,
                        "snapshot_id":group,"start_date":start.to_string(),"end_date":end.to_string(),
                        "floor":floor.to_string(),"side":side.to_string(),"scope_key":key(group,floor,side),
                        "label":format!("{label} · {} · 第{floor}层 · {}半",text(schedule,"name_mi18n"),if side==1 {"上"} else {"下"}),
                        "source_url":source_url,"source_label":"HoYoLAB 官方阵容助手周期与楼层目录",
                        "source_version":group,"weaknesses":[],"resistances":[],"enemies":[],
                        "effects":effects(schedule,mode,side,&source_url),"mechanic_text":text(schedule,"maze_buff_desc_mi18n"),
                        "quality_status":"phase_only","missing_fields":["enemies","weaknesses","resistances"],
                        "source_note":"周期及楼层已核对；该公开目录不提供各侧敌人，可补充自定义敌情。"}));
                }
                requests.push((
                    mode.to_owned(),
                    kind.to_owned(),
                    group.to_owned(),
                    floor,
                    tag,
                    phase_ver.clone(),
                ));
            }
        }
    }
    let mut responses = Vec::new();
    for batch in requests.chunks(4) {
        let mut pending = tokio::task::JoinSet::new();
        for (mode, kind, group, floor, tag, phase_ver) in batch.iter().cloned() {
            let client = client.clone();
            pending.spawn(async move {
                let url = format!("{BASE}/lineup/index?tag_id={tag}&group_id={group}&lineup_type={kind}&game=hkrpg&order=Hot&lang=zh-cn");
                let value = client.get_text(&url).await.map_err(anyhow::Error::from).and_then(|value| response(&value));
                (mode, kind, group, floor, phase_ver, value)
            });
        }
        while let Some(value) = pending.join_next().await {
            responses.push(value.context("official lineup query task")?);
        }
    }
    let mut records = Vec::new();
    for (mode, kind, group, floor, phase_ver, result) in responses {
        match result {
            Ok(payload) => records.extend(normalize_records(
                &payload, &mode, &kind, &group, floor, &phase_ver, &names,
            )),
            Err(error) => warnings.push(format!("官方投稿 {mode} 第{floor}层不可用：{error}")),
        }
    }
    if records.is_empty() {
        warnings.push("本次公开投稿未取得可绑定的完整实战队伍；敌情推荐仍可使用。".into());
    }
    bundle.add_json("hsr_encounters_v1.json",&json!({"schema_version":"miho-encounters-v1","game":"hsr","encounters":encounters,"warnings":warnings}))?;
    bundle.add_json(
        "hsr_battle_records_v1.json",
        &json!({"schema_version":"miho-battle-records-v1","game":"hsr","records":records}),
    )?;
    Ok(warnings)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn published_clear_requires_exact_floor_period_and_complete_members() {
        let names = [("甲", "a"), ("乙", "b"), ("丙", "c"), ("丁", "d")]
            .into_iter()
            .map(|(name, slug)| (alias(name), slug.to_owned()))
            .collect();
        let mut row = json!({"id":"public-post","lineup_type":"Chasm","floor":11,"schedule_group":{"group_id":"1035"},
            "is_deleted":false,"audit_status":1,"publish_type":"LineupPublishTypeRecord","star_num":3,"round_num":0,
            "avatar_group":[{"group":[{"item_name":"甲"},{"item_name":"乙"},{"item_name":"丙"},{"item_name":"丁"}]}]});
        let one_side = row.clone();
        row["avatar_group"]
            .as_array_mut()
            .unwrap()
            .push(one_side["avatar_group"][0].clone());
        let records = normalize_records(
            &json!({"list":[row.clone()]}),
            "moc",
            "Chasm",
            "1035",
            11,
            "4.6.1",
            &names,
        );
        assert_eq!(records.len(), 2);
        assert_eq!(records[0]["metric_scope"], "floor");
        assert_eq!(records[0]["metric_value"], 0.0);
        assert!(normalize_records(
            &json!({"list":[one_side]}),
            "moc",
            "Chasm",
            "1035",
            11,
            "4.6.1",
            &names
        )
        .is_empty());
        let mut partial = row.clone();
        partial["star_num"] = json!(2);
        assert!(normalize_records(
            &json!({"list":[partial]}),
            "moc",
            "Chasm",
            "1035",
            11,
            "4.6.1",
            &names
        )
        .is_empty());
        assert!(normalize_records(
            &json!({"list":[row.clone()]}),
            "moc",
            "Chasm",
            "1035",
            10,
            "4.6.1",
            &names
        )
        .is_empty());
        assert!(normalize_records(
            &json!({"list":[row]}),
            "moc",
            "Chasm",
            "old",
            11,
            "4.6.1",
            &names
        )
        .is_empty());
    }
}
