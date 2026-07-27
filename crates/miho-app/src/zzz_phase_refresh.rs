use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

use anyhow::{anyhow, Context};
use chrono::{DateTime, FixedOffset, NaiveDate};
use miho_core::{
    network::{CachedHttpClient, FetchMode, FetchSource, HttpClient},
    output::ArtifactBundle,
    visualizer::read_csv_rows,
    MihoError,
};
use reqwest::header::{HeaderMap, HeaderName, HeaderValue, ACCEPT, USER_AGENT};
use serde::Serialize;
use serde_json::{json, Value};

const OFFICIAL_INDEX_URL: &str = "https://act-api-takumi-static.mihoyo.com/common/blackboard/zzz_wiki/v1/home/content/list?app_sn=zzz_wiki&channel_id=13";
const OFFICIAL_ENTRY_URL: &str =
    "https://act-api-takumi-static.mihoyo.com/hoyowiki/zzz/wapi/entry_page";
const OFFICIAL_SOURCE_LABEL: &str = "米游社《绝区零》官方百科";
const OFFICIAL_SCHEMA: &str = "miho-zzz-official-endgame-v1";
const SD_MENU_ID: &str = "100";
const DA_MENU_ID: &str = "108";

#[derive(Debug)]
pub(crate) struct OfficialPhaseRefresh {
    pub normalized: Vec<u8>,
    pub raw_artifacts: Vec<(String, Vec<u8>)>,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub(crate) struct PhaseIdentity {
    mode: String,
    snapshot_id: String,
    phase_ver: String,
    start_date: String,
    end_date: String,
}

#[derive(Clone, Debug)]
struct PhaseTarget {
    identity: PhaseIdentity,
    collect_date: String,
}

#[derive(Clone, Debug)]
struct IndexItem {
    id: String,
    title: String,
}

#[derive(Debug)]
struct OfficialIndex {
    sd: Vec<IndexItem>,
    da: Vec<IndexItem>,
}

#[derive(Clone, Debug)]
struct OfficialPage {
    id: String,
    name: String,
    version: String,
    modules: Vec<Value>,
}

#[derive(Clone, Debug, Serialize)]
struct OfficialPhaseRow {
    identity: PhaseIdentity,
    phase_name_cn: String,
    mechanic_name: String,
    mechanic_text: String,
    source_label: String,
    source_url: String,
    entry_page_ids: Vec<String>,
    source_versions: BTreeMap<String, String>,
    source_note: String,
}

struct OfficialClient {
    client: CachedHttpClient,
    headers: HeaderMap,
    raw: BTreeMap<String, Vec<u8>>,
    warnings: Vec<String>,
}

impl OfficialClient {
    fn new(http: HttpClient, cache_root: &Path) -> anyhow::Result<Self> {
        Ok(Self {
            client: CachedHttpClient::new(http, cache_root),
            headers: official_headers()?,
            raw: BTreeMap::new(),
            warnings: Vec::new(),
        })
    }

    async fn index(&mut self) -> anyhow::Result<OfficialIndex> {
        let fetched = self
            .client
            .get_text_with_headers_validated_with_source(
                OFFICIAL_INDEX_URL,
                &self.headers,
                Path::new("zzz/hoyowiki/endgame/index-zh-cn.json"),
                FetchMode::Online,
                |text| {
                    decode_index(text)
                        .map(|_| ())
                        .map_err(MihoError::Unsupported)
                },
            )
            .await?;
        self.record_fallback(
            "官方终局目录",
            fetched.source,
            fetched.fallback_reason.as_deref(),
        );
        self.raw.insert(
            "raw/hoyowiki/endgame/index-zh-cn.json".to_owned(),
            fetched.text.as_bytes().to_vec(),
        );
        decode_index(&fetched.text).map_err(anyhow::Error::msg)
    }

    async fn page(&mut self, id: &str) -> anyhow::Result<OfficialPage> {
        if id.is_empty() || !id.bytes().all(|byte| byte.is_ascii_digit()) {
            return Err(anyhow!("invalid official entry page id: {id}"));
        }
        let url = format!("{OFFICIAL_ENTRY_URL}?entry_page_id={id}&lang=zh-cn");
        let cache_key = PathBuf::from(format!("zzz/hoyowiki/endgame/entry-{id}-zh-cn.json"));
        let expected = id.to_owned();
        let fetched = self
            .client
            .get_text_with_headers_validated_with_source(
                &url,
                &self.headers,
                &cache_key,
                FetchMode::Online,
                move |text| {
                    decode_page(text, &expected)
                        .map(|_| ())
                        .map_err(MihoError::Unsupported)
                },
            )
            .await?;
        self.record_fallback(
            &format!("官方终局词条 {id}"),
            fetched.source,
            fetched.fallback_reason.as_deref(),
        );
        self.raw.insert(
            format!("raw/hoyowiki/endgame/entry-{id}-zh-cn.json"),
            fetched.text.as_bytes().to_vec(),
        );
        decode_page(&fetched.text, id).map_err(anyhow::Error::msg)
    }

    fn record_fallback(&mut self, label: &str, source: FetchSource, reason: Option<&str>) {
        if source == FetchSource::Cache {
            self.warnings.push(match reason {
                Some(reason) if !reason.is_empty() => {
                    format!("{label} 联网失败，沿用最近一次有效缓存：{reason}")
                }
                _ => format!("{label} 使用最近一次有效缓存"),
            });
        }
    }
}

pub(crate) async fn refresh_official_phases(
    bundle: &ArtifactBundle,
    http: HttpClient,
    cache_root: &Path,
    previous_snapshot: Option<&[u8]>,
    fetched_at: DateTime<FixedOffset>,
) -> anyhow::Result<OfficialPhaseRefresh> {
    let targets = latest_targets(bundle)?;
    let mut client = OfficialClient::new(http, cache_root)?;
    let mut rows = Vec::new();
    let mut warnings = Vec::new();

    if targets.is_empty() {
        warnings.push("终局统计没有可用于绑定官方期名的完整周期身份".to_owned());
    } else {
        match client.index().await {
            Ok(index) => {
                for target in targets {
                    let result = match target.identity.mode.as_str() {
                        "sd" => fetch_sd_phase(&mut client, &index, &target).await,
                        "da" => fetch_da_phase(&mut client, &index, &target).await,
                        _ => continue,
                    };
                    match result {
                        Ok(row) => rows.push(row),
                        Err(error) => warnings.push(format!(
                            "{} {} 官方期名/机制未更新：{error}",
                            target.identity.mode, target.identity.start_date
                        )),
                    }
                }
            }
            Err(error) => warnings.push(format!("官方终局目录不可用：{error}")),
        }
    }
    warnings.append(&mut client.warnings);
    let normalized = merge_snapshot(previous_snapshot, rows, fetched_at)?;
    Ok(OfficialPhaseRefresh {
        normalized,
        raw_artifacts: client.raw.into_iter().collect(),
        warnings,
    })
}

fn latest_targets(bundle: &ArtifactBundle) -> anyhow::Result<Vec<PhaseTarget>> {
    let mut latest = BTreeMap::<String, PhaseTarget>::new();
    for row in read_csv_rows(bundle, "phase_index.csv")? {
        let mode = row.get("mode").cloned().unwrap_or_default();
        if !matches!(mode.as_str(), "sd" | "da") {
            continue;
        }
        let target = PhaseTarget {
            identity: PhaseIdentity {
                mode: mode.clone(),
                snapshot_id: row.get("snapshot_id").cloned().unwrap_or_default(),
                phase_ver: row.get("phase_ver").cloned().unwrap_or_default(),
                start_date: row.get("start_date").cloned().unwrap_or_default(),
                end_date: row.get("end_date").cloned().unwrap_or_default(),
            },
            collect_date: row.get("collect_date").cloned().unwrap_or_default(),
        };
        if target.identity.snapshot_id.is_empty()
            || target.identity.phase_ver.is_empty()
            || parse_iso_date(&target.identity.start_date).is_none()
            || parse_iso_date(&target.identity.end_date).is_none()
        {
            continue;
        }
        let key = (
            target.collect_date.as_str(),
            target.identity.start_date.as_str(),
            target.identity.snapshot_id.as_str(),
            target.identity.phase_ver.as_str(),
        );
        let replace = latest.get(&mode).is_none_or(|current| {
            key > (
                current.collect_date.as_str(),
                current.identity.start_date.as_str(),
                current.identity.snapshot_id.as_str(),
                current.identity.phase_ver.as_str(),
            )
        });
        if replace {
            latest.insert(mode, target);
        }
    }
    Ok(latest.into_values().collect())
}

async fn fetch_sd_phase(
    client: &mut OfficialClient,
    index: &OfficialIndex,
    target: &PhaseTarget,
) -> anyhow::Result<OfficialPhaseRow> {
    let start = parse_iso_date(&target.identity.start_date)
        .ok_or_else(|| anyhow!("invalid SD start date"))?;
    let aggregates = index
        .sd
        .iter()
        .filter(|item| sd_aggregate_date(&item.title) == Some(start))
        .cloned()
        .collect::<Vec<_>>();
    if aggregates.len() > 1 {
        return Err(anyhow!(
            "multiple official SD aggregate pages match {start}"
        ));
    }

    let mut source_page = None;
    let stages = if let Some(item) = aggregates.first() {
        let page = client.page(&item.id).await?;
        if sd_aggregate_date(&page.name) != Some(start) {
            return Err(anyhow!(
                "SD aggregate title {} does not match {start}",
                page.name
            ));
        }
        let stages = stage_links(&page)?;
        source_page = Some(page);
        stages
    } else {
        let mut stages = BTreeMap::new();
        for item in &index.sd {
            let Some((date, stage)) = sd_stage_identity(&item.title) else {
                continue;
            };
            if date == start && stages.insert(stage, item.id.clone()).is_some() {
                return Err(anyhow!("duplicate official SD stage {stage} for {start}"));
            }
        }
        validate_five_stages(&stages)?;
        stages
    };

    let mut stage_pages = BTreeMap::<u8, OfficialPage>::new();
    for (stage, id) in stages {
        let page = client.page(&id).await?;
        let actual = sd_stage_identity(&page.name);
        if actual != Some((start, stage)) {
            return Err(anyhow!(
                "official SD stage {id} has mismatched title {}",
                page.name
            ));
        }
        stage_pages.insert(stage, page);
    }
    validate_five_stages(
        &stage_pages
            .iter()
            .map(|(stage, page)| (*stage, page.id.clone()))
            .collect(),
    )?;

    let mechanic_text = shared_sd_mechanic(&stage_pages)?;
    let phase_name_cn = source_page
        .as_ref()
        .map(|page| page.name.clone())
        .unwrap_or_else(|| {
            format!(
                "{}.{}.{}式舆防卫战关卡阵容",
                start.format("%y"),
                start.format("%-m"),
                start.format("%-d")
            )
        });
    let source_id = source_page
        .as_ref()
        .map(|page| page.id.clone())
        .or_else(|| stage_pages.get(&1).map(|page| page.id.clone()))
        .ok_or_else(|| anyhow!("official SD source page missing"))?;
    let mut entry_page_ids = Vec::new();
    let mut source_versions = BTreeMap::new();
    if let Some(page) = source_page {
        entry_page_ids.push(page.id.clone());
        source_versions.insert(page.id, page.version);
    }
    for page in stage_pages.values() {
        entry_page_ids.push(page.id.clone());
        source_versions.insert(page.id.clone(), page.version.clone());
    }
    Ok(OfficialPhaseRow {
        identity: target.identity.clone(),
        phase_name_cn,
        mechanic_name: "全期增益".to_owned(),
        mechanic_text,
        source_label: OFFICIAL_SOURCE_LABEL.to_owned(),
        source_url: public_page_url(&source_id),
        entry_page_ids,
        source_versions,
        source_note: "按官方标题日期精确绑定；全期增益仅采用多条防线首个说明块的唯一共识，未读取房间独立增益。".to_owned(),
    })
}

async fn fetch_da_phase(
    client: &mut OfficialClient,
    index: &OfficialIndex,
    target: &PhaseTarget,
) -> anyhow::Result<OfficialPhaseRow> {
    let start = parse_iso_date(&target.identity.start_date)
        .ok_or_else(|| anyhow!("invalid DA start date"))?;
    let candidates = index
        .da
        .iter()
        .filter(|item| da_phase_number(&item.title).is_some())
        .take(12)
        .cloned()
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Err(anyhow!("official DA index contains no phase pages"));
    }

    let mut pages = Vec::new();
    for item in candidates {
        let page = match client.page(&item.id).await {
            Ok(page) => page,
            Err(error) => {
                client
                    .warnings
                    .push(format!("官方危局词条 {} 不可用：{error}", item.id));
                continue;
            }
        };
        pages.push((item, page));
    }
    let (page, mechanics) = select_unique_da_phase(pages, start)?;
    let mechanic_name = mechanics
        .iter()
        .map(|(name, _)| name.as_str())
        .collect::<Vec<_>>()
        .join(" / ");
    let mechanic_text = mechanics
        .iter()
        .map(|(name, text)| format!("{name}：{text}"))
        .collect::<Vec<_>>()
        .join("\n");
    Ok(OfficialPhaseRow {
        identity: target.identity.clone(),
        phase_name_cn: page.name.clone(),
        mechanic_name,
        mechanic_text,
        source_label: OFFICIAL_SOURCE_LABEL.to_owned(),
        source_url: public_page_url(&page.id),
        entry_page_ids: vec![page.id.clone()],
        source_versions: BTreeMap::from([(page.id, page.version)]),
        source_note:
            "按官方词条 version 的固定 UTC+08:00 日期与统计周期开始日精确绑定；仅采用增益名称/增益效果表。"
                .to_owned(),
    })
}

fn select_unique_da_phase(
    candidates: Vec<(IndexItem, OfficialPage)>,
    start: NaiveDate,
) -> anyhow::Result<(OfficialPage, Vec<(String, String)>)> {
    let mut matches = Vec::new();
    for (item, page) in candidates {
        if page.name != item.title || da_phase_number(&page.name).is_none() {
            continue;
        }
        let Some(version_date) = version_date_cn(&page.version) else {
            continue;
        };
        if version_date != start {
            continue;
        }
        let mechanics = da_mechanics(&page)?;
        matches.push((page, mechanics));
    }
    if matches.len() > 1 {
        let ids = matches
            .iter()
            .map(|(page, _)| page.id.as_str())
            .collect::<Vec<_>>()
            .join(", ");
        return Err(anyhow!(
            "multiple official DA pages exactly match {start}: {ids}"
        ));
    }
    matches
        .pop()
        .ok_or_else(|| anyhow!("no official DA page version date exactly matches {start}"))
}

fn decode_index(text: &str) -> Result<OfficialIndex, String> {
    let value: Value = serde_json::from_str(text).map_err(|error| error.to_string())?;
    require_success(&value)?;
    let roots = value
        .pointer("/data/list")
        .and_then(Value::as_array)
        .ok_or_else(|| "official endgame index has no data.list".to_owned())?;
    let sd = find_menu(roots, SD_MENU_ID)
        .ok_or_else(|| "official endgame index has no SD menu 100".to_owned())?;
    let da = find_menu(roots, DA_MENU_ID)
        .ok_or_else(|| "official endgame index has no DA menu 108".to_owned())?;
    Ok(OfficialIndex {
        sd: index_items(sd)?,
        da: index_items(da)?,
    })
}

fn decode_page(text: &str, expected_id: &str) -> Result<OfficialPage, String> {
    let value: Value = serde_json::from_str(text).map_err(|error| error.to_string())?;
    require_success(&value)?;
    let page = value
        .pointer("/data/page")
        .and_then(Value::as_object)
        .ok_or_else(|| "official endgame response has no data.page".to_owned())?;
    let id = scalar_string(page.get("id"));
    if id != expected_id {
        return Err(format!(
            "official endgame page id mismatch: expected {expected_id}, got {id}"
        ));
    }
    let name = page
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_owned();
    if name.is_empty() {
        return Err("official endgame page name is empty".to_owned());
    }
    let modules = page
        .get("modules")
        .and_then(Value::as_array)
        .cloned()
        .ok_or_else(|| "official endgame page modules are missing".to_owned())?;
    Ok(OfficialPage {
        id,
        name,
        version: scalar_string(page.get("version")),
        modules,
    })
}

fn require_success(value: &Value) -> Result<(), String> {
    if value.get("retcode").and_then(Value::as_i64) == Some(0) {
        Ok(())
    } else {
        Err(format!(
            "official endgame API returned retcode {}",
            scalar_string(value.get("retcode"))
        ))
    }
}

fn find_menu<'a>(nodes: &'a [Value], wanted: &str) -> Option<&'a Value> {
    for node in nodes {
        if scalar_string(node.get("id")) == wanted {
            return Some(node);
        }
        if let Some(children) = node.get("children").and_then(Value::as_array) {
            if let Some(found) = find_menu(children, wanted) {
                return Some(found);
            }
        }
    }
    None
}

fn index_items(menu: &Value) -> Result<Vec<IndexItem>, String> {
    let rows = menu
        .get("list")
        .and_then(Value::as_array)
        .ok_or_else(|| "official endgame menu list is missing".to_owned())?;
    Ok(rows
        .iter()
        .filter_map(|row| {
            let id = scalar_string(row.get("content_id"));
            let title = row.get("title")?.as_str()?.trim().to_owned();
            (!id.is_empty() && !title.is_empty()).then_some(IndexItem { id, title })
        })
        .collect())
}

fn stage_links(page: &OfficialPage) -> anyhow::Result<BTreeMap<u8, String>> {
    let mut stages = BTreeMap::new();
    for module in &page.modules {
        let Some(components) = module.get("components").and_then(Value::as_array) else {
            continue;
        };
        for component in components {
            if component.get("component_id").and_then(Value::as_str) != Some("strategy") {
                continue;
            }
            let data = component_json(component)?;
            collect_stage_links(&data, &mut stages)?;
        }
    }
    validate_five_stages(&stages)?;
    Ok(stages)
}

fn collect_stage_links(value: &Value, stages: &mut BTreeMap<u8, String>) -> anyhow::Result<()> {
    match value {
        Value::Object(object) => {
            if let (Some(tab), Some(link)) = (
                object.get("tab_name").and_then(Value::as_str),
                object.get("link").and_then(Value::as_str),
            ) {
                if let Some(stage) = stage_number(tab) {
                    let id = entry_id_from_link(link)
                        .ok_or_else(|| anyhow!("official SD stage {stage} has invalid link"))?;
                    if stages.insert(stage, id.clone()).is_some() {
                        return Err(anyhow!("duplicate official SD stage link {stage}"));
                    }
                }
            }
            for child in object.values() {
                collect_stage_links(child, stages)?;
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_stage_links(item, stages)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn validate_five_stages<T>(stages: &BTreeMap<u8, T>) -> anyhow::Result<()> {
    let actual = stages.keys().copied().collect::<Vec<_>>();
    if actual != vec![1, 2, 3, 4, 5] {
        return Err(anyhow!(
            "official SD stage links must contain exactly stages 1-5, got {actual:?}"
        ));
    }
    Ok(())
}

fn shared_sd_mechanic(pages: &BTreeMap<u8, OfficialPage>) -> anyhow::Result<String> {
    let mut counts = BTreeMap::<String, usize>::new();
    for stage in 1..=4 {
        let page = pages
            .get(&stage)
            .ok_or_else(|| anyhow!("official SD stage {stage} is missing"))?;
        let candidates = first_module_rich_text(page)?;
        for candidate in candidates.into_iter().collect::<BTreeSet<_>>() {
            *counts.entry(candidate).or_default() += 1;
        }
    }
    let winners = counts
        .into_iter()
        .filter_map(|(text, count)| (count == 4).then_some(text))
        .collect::<Vec<_>>();
    if winners.len() != 1 {
        return Err(anyhow!(
            "official SD stages 1-4 must share exactly one first-module mechanic"
        ));
    }
    Ok(winners.into_iter().next().expect("one winner"))
}

fn first_module_rich_text(page: &OfficialPage) -> anyhow::Result<Vec<String>> {
    let Some(module) = page.modules.first() else {
        return Ok(Vec::new());
    };
    let Some(components) = module.get("components").and_then(Value::as_array) else {
        return Ok(Vec::new());
    };
    let mut text = Vec::new();
    for component in components {
        if component.get("component_id").and_then(Value::as_str) != Some("rich_row_base_info") {
            continue;
        }
        let data = component_json(component)?;
        if let Some(fragment) = data.get("rich_text").and_then(Value::as_str) {
            let clean = html_text(fragment);
            if !clean.is_empty() {
                text.push(clean);
            }
        }
    }
    Ok(text)
}

fn da_mechanics(page: &OfficialPage) -> anyhow::Result<Vec<(String, String)>> {
    let Some(module) = page.modules.first() else {
        return Err(anyhow!("official DA page has no first module"));
    };
    let components = module
        .get("components")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("official DA first module has no components"))?;
    let mut matches = Vec::new();
    for component in components {
        if component.get("component_id").and_then(Value::as_str) != Some("multi_table") {
            continue;
        }
        let data = component_json(component)?;
        let Some(tables) = data.get("tables").and_then(Value::as_array) else {
            continue;
        };
        for table in tables {
            let header = table
                .get("header")
                .and_then(Value::as_array)
                .map(|cells| {
                    cells
                        .iter()
                        .map(|cell| html_text(cell.as_str().unwrap_or("")))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if header != ["增益名称", "增益效果"] {
                continue;
            }
            let rows = table
                .get("row")
                .and_then(Value::as_array)
                .ok_or_else(|| anyhow!("official DA mechanic table has no rows"))?;
            let parsed = rows
                .iter()
                .map(|row| {
                    let cells = row
                        .as_array()
                        .ok_or_else(|| anyhow!("official DA mechanic row is not an array"))?;
                    if cells.len() != 2 {
                        return Err(anyhow!("official DA mechanic row must have two cells"));
                    }
                    let name = html_text(cells[0].as_str().unwrap_or(""));
                    let effect = html_text(cells[1].as_str().unwrap_or(""));
                    if name.is_empty() || effect.is_empty() {
                        return Err(anyhow!("official DA mechanic row contains an empty cell"));
                    }
                    Ok((name, effect))
                })
                .collect::<anyhow::Result<Vec<_>>>()?;
            if parsed.len() != 3 {
                return Err(anyhow!(
                    "official DA mechanic table must contain exactly three rows"
                ));
            }
            matches.push(parsed);
        }
    }
    if matches.len() != 1 {
        return Err(anyhow!(
            "official DA page must contain exactly one mechanic table"
        ));
    }
    Ok(matches.pop().expect("one mechanic table"))
}

fn component_json(component: &Value) -> anyhow::Result<Value> {
    let text = component
        .get("data")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("official component.data is not a JSON string"))?;
    serde_json::from_str(text).context("invalid JSON in official component.data")
}

fn merge_snapshot(
    previous: Option<&[u8]>,
    rows: Vec<OfficialPhaseRow>,
    fetched_at: DateTime<FixedOffset>,
) -> anyhow::Result<Vec<u8>> {
    let mut phases = BTreeMap::<PhaseIdentity, Value>::new();
    if let Some(previous) = previous {
        if let Ok(value) = serde_json::from_slice::<Value>(previous) {
            if let Some(existing) = value.get("phases").and_then(Value::as_array) {
                for row in existing {
                    if let Some(identity) = serialized_identity(row) {
                        phases.insert(identity, row.clone());
                    }
                }
            }
        }
    }
    for row in rows {
        phases.insert(row.identity.clone(), serde_json::to_value(row)?);
    }
    while phases.len() > 48 {
        let Some(key) = phases.keys().next().cloned() else {
            break;
        };
        phases.remove(&key);
    }
    let value = json!({
        "schema_version": OFFICIAL_SCHEMA,
        "fetched_at": fetched_at.to_rfc3339(),
        "phases": phases.into_values().collect::<Vec<_>>(),
    });
    let mut bytes = serde_json::to_vec_pretty(&value)?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn serialized_identity(row: &Value) -> Option<PhaseIdentity> {
    let identity = row.get("identity")?;
    let get = |key| {
        identity
            .get(key)?
            .as_str()
            .filter(|value| !value.is_empty())
    };
    Some(PhaseIdentity {
        mode: get("mode")?.to_owned(),
        snapshot_id: get("snapshot_id")?.to_owned(),
        phase_ver: get("phase_ver")?.to_owned(),
        start_date: get("start_date")?.to_owned(),
        end_date: get("end_date")?.to_owned(),
    })
}

fn official_headers() -> anyhow::Result<HeaderMap> {
    let mut headers = HeaderMap::new();
    headers.insert(
        USER_AGENT,
        HeaderValue::from_static("Mozilla/5.0 miho-endgame/0.1"),
    );
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(
        HeaderName::from_static("x-rpc-wiki_app"),
        HeaderValue::from_static("zzz"),
    );
    headers.insert(
        HeaderName::from_static("x-rpc-language"),
        HeaderValue::from_static("zh-cn"),
    );
    Ok(headers)
}

fn parse_iso_date(value: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d").ok()
}

fn sd_aggregate_date(title: &str) -> Option<NaiveDate> {
    title
        .strip_suffix("式舆防卫战关卡阵容")
        .and_then(parse_title_date)
}

fn sd_stage_identity(title: &str) -> Option<(NaiveDate, u8)> {
    let title = title.trim();
    let title = title
        .strip_prefix('（')
        .and_then(|value| value.split_once('）'))
        .or_else(|| {
            title
                .strip_prefix('(')
                .and_then(|value| value.split_once(')'))
        })?;
    let date = parse_title_date(title.0)?;
    let stage = stage_number(title.1)?;
    Some((date, stage))
}

fn parse_title_date(value: &str) -> Option<NaiveDate> {
    let parts = value
        .trim()
        .split(['.', '/', '-'])
        .map(str::trim)
        .collect::<Vec<_>>();
    if parts.len() != 3 || parts.iter().any(|part| part.is_empty()) {
        return None;
    }
    let mut year = parts[0].parse::<i32>().ok()?;
    if parts[0].len() == 2 {
        year += 2000;
    } else if parts[0].len() != 4 {
        return None;
    }
    NaiveDate::from_ymd_opt(year, parts[1].parse().ok()?, parts[2].parse().ok()?)
}

fn stage_number(value: &str) -> Option<u8> {
    let compact = value.split_whitespace().collect::<String>();
    [
        ("第一防线", 1),
        ("第二防线", 2),
        ("第三防线", 3),
        ("第四防线", 4),
        ("第五防线", 5),
    ]
    .into_iter()
    .find_map(|(needle, stage)| compact.contains(needle).then_some(stage))
}

fn da_phase_number(title: &str) -> Option<u32> {
    let number = title.strip_prefix("危局强袭战（第")?.strip_suffix("期）")?;
    number.parse().ok()
}

fn version_date_cn(value: &str) -> Option<NaiveDate> {
    let timestamp = value.parse::<i64>().ok()?;
    let utc = DateTime::from_timestamp(timestamp, 0)?;
    let offset = FixedOffset::east_opt(8 * 60 * 60)?;
    Some(utc.with_timezone(&offset).date_naive())
}

fn entry_id_from_link(link: &str) -> Option<String> {
    let marker = "/content/";
    let tail = link.split_once(marker)?.1;
    let id = tail
        .chars()
        .take_while(|character| character.is_ascii_digit())
        .collect::<String>();
    (!id.is_empty()).then_some(id)
}

fn public_page_url(id: &str) -> String {
    format!("https://baike.mihoyo.com/zzz/wiki/content/{id}/detail")
}

fn scalar_string(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        _ => String::new(),
    }
}

fn html_text(value: &str) -> String {
    let without_script = remove_html_block(value, "script");
    let without_style = remove_html_block(&without_script, "style");
    let mut text = String::new();
    let mut in_tag = false;
    for character in without_style.chars() {
        match character {
            '<' => in_tag = true,
            '>' if in_tag => {
                in_tag = false;
                text.push(' ');
            }
            _ if !in_tag => text.push(character),
            _ => {}
        }
    }
    html_unescape(&text)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn remove_html_block(value: &str, tag: &str) -> String {
    let lower = value.to_ascii_lowercase();
    let opening = format!("<{tag}");
    let closing = format!("</{tag}>");
    let mut output = String::new();
    let mut cursor = 0;
    while let Some(relative_start) = lower[cursor..].find(&opening) {
        let start = cursor + relative_start;
        output.push_str(&value[cursor..start]);
        let Some(relative_end) = lower[start..].find(&closing) else {
            return output;
        };
        cursor = start + relative_end + closing.len();
        output.push(' ');
    }
    output.push_str(&value[cursor..]);
    output
}

fn html_unescape(value: &str) -> String {
    let mut output = String::new();
    let mut rest = value;
    while let Some(start) = rest.find('&') {
        output.push_str(&rest[..start]);
        let entity = &rest[start + 1..];
        let Some(end) = entity.find(';').filter(|end| *end <= 16) else {
            output.push('&');
            rest = entity;
            continue;
        };
        let code = &entity[..end];
        let decoded = match code {
            "amp" => Some('&'),
            "lt" => Some('<'),
            "gt" => Some('>'),
            "quot" => Some('"'),
            "apos" | "#39" => Some('\''),
            "nbsp" => Some(' '),
            _ if code.starts_with("#x") || code.starts_with("#X") => {
                u32::from_str_radix(&code[2..], 16)
                    .ok()
                    .and_then(char::from_u32)
            }
            _ if code.starts_with('#') => code[1..].parse::<u32>().ok().and_then(char::from_u32),
            _ => None,
        };
        if let Some(character) = decoded {
            output.push(character);
        } else {
            output.push('&');
            output.push_str(code);
            output.push(';');
        }
        rest = &entity[end + 1..];
    }
    output.push_str(rest);
    output
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    fn component(id: &str, data: Value) -> Value {
        json!({"component_id":id,"data":serde_json::to_string(&data).unwrap()})
    }

    fn page(id: &str, name: &str, version: &str, modules: Vec<Value>) -> OfficialPage {
        OfficialPage {
            id: id.to_owned(),
            name: name.to_owned(),
            version: version.to_owned(),
            modules,
        }
    }

    fn rich_module(text: &str) -> Value {
        json!({"id":"354","components":[component(
            "rich_row_base_info",
            json!({"rich_text":text})
        )]})
    }

    #[test]
    fn official_dates_use_sd_title_and_da_fixed_china_timezone() {
        assert_eq!(
            sd_aggregate_date("26.7.10式舆防卫战关卡阵容"),
            NaiveDate::from_ymd_opt(2026, 7, 10)
        );
        assert_eq!(
            sd_stage_identity("（26/7/10）剧变节点第五防线"),
            Some((NaiveDate::from_ymd_opt(2026, 7, 10).unwrap(), 5))
        );
        assert_eq!(
            version_date_cn("1784252125"),
            NaiveDate::from_ymd_opt(2026, 7, 17)
        );
        let utc_crossing = chrono::Utc
            .with_ymd_and_hms(2026, 7, 16, 16, 5, 0)
            .unwrap()
            .timestamp()
            .to_string();
        assert_eq!(
            version_date_cn(&utc_crossing),
            NaiveDate::from_ymd_opt(2026, 7, 17)
        );
        assert_ne!(
            version_date_cn("1784860323"),
            sd_aggregate_date("26.7.10式舆防卫战关卡阵容")
        );
    }

    #[test]
    fn index_discovery_is_dynamic_and_page_decoder_rejects_wrong_identity() {
        let text = serde_json::to_string(&json!({
            "retcode":0,
            "data":{"list":[{"id":13,"children":[
                {"id":100,"list":[
                    {"content_id":2110,"title":"26.7.10式舆防卫战关卡阵容"},
                    {"content_id":3111,"title":"（26/7/24）剧变节点第一防线"}
                ]},
                {"id":"108","list":[
                    {"content_id":"2101","title":"危局强袭战（第41期）"}
                ]}
            ]}]}
        }))
        .unwrap();
        let index = decode_index(&text).unwrap();
        assert_eq!(index.sd[0].id, "2110");
        assert_eq!(index.sd[1].id, "3111");
        assert_eq!(index.da[0].id, "2101");

        let response = serde_json::to_string(&json!({
            "retcode":0,
            "data":{"page":{"id":2101,"name":"危局强袭战（第41期）","version":"1784252125","modules":[]}}
        })).unwrap();
        assert!(decode_page(&response, "2101").is_ok());
        assert!(decode_page(&response, "9999")
            .unwrap_err()
            .contains("id mismatch"));
    }

    #[test]
    fn sd_mechanic_requires_cross_stage_consensus_and_ignores_room_tables() {
        let common_a = "<ul><li><p>代理人的风属性伤害和冰属性伤害提升10%。</p></li><li><p>命中处于属性异常状态中的敌人时，造成的伤害提升15%，无视其10%的全属性伤害抗性。</p></li></ul>";
        let common_b = "<ul> <li>代理人的风属性伤害和冰属性伤害提升10%。</li> <li>命中处于属性异常状态中的敌人时，造成的伤害提升15%，无视其10%的全属性伤害抗性。</li> </ul>";
        let mut pages = BTreeMap::new();
        for stage in 1..=4 {
            pages.insert(
                stage,
                page(
                    &format!("20{stage}"),
                    &format!("（26/7/10）剧变节点第{stage}防线"),
                    "1",
                    vec![rich_module(if stage % 2 == 0 {
                        common_b
                    } else {
                        common_a
                    })],
                ),
            );
        }
        pages.insert(
            5,
            page(
                "205",
                "（26/7/10）剧变节点第五防线",
                "1",
                vec![
                    rich_module("<p></p>"),
                    json!({"components":[component("multi_table",json!({
                        "tables":[{"header":["房间增益"],"row":[["终结技伤害提升40%，攻击力提升30%，计分增益"]]}]
                    }))]}),
                ],
            ),
        );
        let mechanic = shared_sd_mechanic(&pages).unwrap();
        assert!(mechanic.contains("风属性伤害"));
        assert!(mechanic.contains("无视其10%的全属性伤害抗性"));
        assert!(!mechanic.contains("终结技"));
        assert!(!mechanic.contains("攻击力提升30%"));
        assert!(!mechanic.contains("计分"));
    }

    #[test]
    fn sd_mechanic_rejects_three_of_four_majority() {
        let mut pages = BTreeMap::new();
        for stage in 1..=4 {
            pages.insert(
                stage,
                page(
                    &format!("20{stage}"),
                    &format!("（26/7/10）剧变节点第{stage}防线"),
                    "1",
                    vec![rich_module(if stage == 4 {
                        "<p>第四防线独有增益。</p>"
                    } else {
                        "<p>仅在前三条防线重复的增益。</p>"
                    })],
                ),
            );
        }

        assert!(shared_sd_mechanic(&pages).is_err());
    }

    #[test]
    fn da_parser_accepts_only_the_exact_three_row_mechanic_table() {
        let table = json!({
            "tables":[{
                "header":["增益名称","增益效果"],
                "row":[
                    ["<p>凛息</p>","<p>风冰伤害提升。</p>"],
                    ["<p>溃亡</p>","<p>失衡值提升。</p>"],
                    ["<p>构析</p>","<p>异常精通提升。</p>"]
                ]
            }]
        });
        let official = page(
            "2101",
            "危局强袭战（第41期）",
            "1784252125",
            vec![
                json!({"id":"695","components":[component("multi_table",table)]}),
                json!({"id":"713","components":[component("multi_table",json!({
                    "tables":[{"header":["敌情详解"],"row":[["Boss 专属效果"]]}]
                }))]}),
            ],
        );
        let mechanics = da_mechanics(&official).unwrap();
        assert_eq!(
            mechanics
                .iter()
                .map(|row| row.0.as_str())
                .collect::<Vec<_>>(),
            ["凛息", "溃亡", "构析"]
        );
        let joined = mechanics
            .iter()
            .map(|row| row.1.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        assert!(!joined.contains("敌情详解"));
        assert!(!joined.contains("Boss"));
    }

    #[test]
    fn da_selector_rejects_two_valid_pages_on_the_same_date() {
        let table = json!({
            "tables":[{
                "header":["增益名称","增益效果"],
                "row":[
                    ["凛息","风冰伤害提升。"],
                    ["溃亡","失衡值提升。"],
                    ["构析","异常精通提升。"]
                ]
            }]
        });
        let candidates = vec![
            (
                IndexItem {
                    id: "2101".to_owned(),
                    title: "危局强袭战（第41期）".to_owned(),
                },
                page(
                    "2101",
                    "危局强袭战（第41期）",
                    "1784252125",
                    vec![json!({"components":[component("multi_table",table.clone())]})],
                ),
            ),
            (
                IndexItem {
                    id: "2201".to_owned(),
                    title: "危局强袭战（第42期）".to_owned(),
                },
                page(
                    "2201",
                    "危局强袭战（第42期）",
                    "1784252125",
                    vec![json!({"components":[component("multi_table",table)]})],
                ),
            ),
        ];
        let error =
            select_unique_da_phase(candidates, NaiveDate::from_ymd_opt(2026, 7, 17).unwrap())
                .unwrap_err();

        assert!(error
            .to_string()
            .contains("multiple official DA pages exactly match 2026-07-17: 2101, 2201"));
    }

    #[test]
    fn snapshot_merge_replaces_only_the_full_identity() {
        let identity = PhaseIdentity {
            mode: "sd".to_owned(),
            snapshot_id: "3.0.3".to_owned(),
            phase_ver: "3.0.2".to_owned(),
            start_date: "2026-07-10".to_owned(),
            end_date: "2026-07-24".to_owned(),
        };
        let row = OfficialPhaseRow {
            identity: identity.clone(),
            phase_name_cn: "26.7.10式舆防卫战关卡阵容".to_owned(),
            mechanic_name: "全期增益".to_owned(),
            mechanic_text: "正文".to_owned(),
            source_label: OFFICIAL_SOURCE_LABEL.to_owned(),
            source_url: public_page_url("2110"),
            entry_page_ids: vec!["2110".to_owned()],
            source_versions: BTreeMap::new(),
            source_note: "note".to_owned(),
        };
        let old = serde_json::to_vec(&json!({
            "schema_version":OFFICIAL_SCHEMA,
            "phases":[{
                "identity":identity,
                "phase_name_cn":"old",
                "mechanic_name":"old",
                "mechanic_text":"old",
                "source_label":"old",
                "source_url":"https://example.com"
            }]
        }))
        .unwrap();
        let now = FixedOffset::east_opt(8 * 3600)
            .unwrap()
            .with_ymd_and_hms(2026, 7, 27, 23, 0, 0)
            .unwrap();
        let merged = merge_snapshot(Some(&old), vec![row], now).unwrap();
        let value: Value = serde_json::from_slice(&merged).unwrap();
        assert_eq!(value["phases"].as_array().unwrap().len(), 1);
        assert_eq!(
            value["phases"][0]["phase_name_cn"],
            "26.7.10式舆防卫战关卡阵容"
        );
    }
}
