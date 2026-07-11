use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

use chrono::Local;
use serde_json::Value;

use crate::{
    contract::{
        diagnostic_code, Diagnostic, DiagnosticSeverity, DiagnosticSource, ExportContext,
        ExportRequestV1, FetchPolicy, Game, GameMode, HistoryPolicy,
    },
    normalize::character_slug,
    output::csv_float,
    supplemental::{
        HoyowikiEntryKind, Locale, SupplementalDocument, SupplementalOrigin, ZzzMode,
        ZzzSupplementalResource, ZzzSupplementalSource,
    },
    zzz::parse_team_rows,
    zzz_export::{NameRow, ZzzExportDataset},
    zzz_history::{
        build_usage_trend, merge_changelog_history, merge_tier_history, UsageRow as HistoryUsageRow,
    },
    zzz_prydwen::{extract_visible_teams, parse_document, ChangelogRow, TierRow},
    zzz_sources::{
        decode_entry_page_response, merge_cached_pages, official_name_map, parse_official_agents,
        parse_official_bangboo, EntryPageData, OfficialMapRow,
    },
    MihoError,
};

pub async fn enrich_zzz_dataset<S: ZzzSupplementalSource + ?Sized>(
    dataset: &mut ZzzExportDataset,
    request: &ExportRequestV1,
    context: &ExportContext,
    source: &S,
) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();

    if request.features.prydwen_visible {
        enrich_visible_teams(dataset, request, context, source, &mut diagnostics).await;
    }
    apply_phase_overrides(dataset, context);

    let mut tiers = Vec::new();
    let mut changelog = Vec::new();
    if request.features.prydwen_tier {
        match source.fetch(ZzzSupplementalResource::PrydwenTier).await {
            Ok(document) => {
                record_cache_fallback(
                    &document,
                    context,
                    DiagnosticSource::Prydwen,
                    None,
                    &mut diagnostics,
                );
                let fetched_at = context
                    .fetched_at
                    .with_timezone(&Local)
                    .format("%Y-%m-%dT%H:%M:%S")
                    .to_string();
                let parsed = parse_document(&document.body, &fetched_at);
                tiers = parsed.tiers;
                changelog = parsed.changelog;
                dataset.raw_text_artifacts.push((
                    "raw/prydwen_tier/tier-list_latest.html".into(),
                    document.body.clone(),
                ));
                if !parsed.snapshot_id.is_empty() {
                    dataset.raw_text_artifacts.push((
                        format!("raw/prydwen_tier/tier-list_{}.html", parsed.snapshot_id),
                        document.body,
                    ));
                }
                if tiers.is_empty() {
                    diagnostics.push(warning(
                        diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                        DiagnosticSource::Prydwen,
                        None,
                        Some("raw/prydwen_tier/tier-list_latest.html"),
                        "Prydwen ZZZ tier parse warning: no tier rows extracted",
                    ));
                }
            }
            Err(error) => diagnostics.push(warning(
                diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                DiagnosticSource::Prydwen,
                None,
                None,
                format!("Prydwen ZZZ tier fetch failed: {error}"),
            )),
        }
    }

    let official = if request.features.official_names {
        load_official_map(source, context, dataset, &mut diagnostics).await
    } else {
        official_name_map(&[], &[])
    };
    let names = build_names(dataset, &tiers, &official);
    enrich_names(dataset, &mut tiers, &names);
    dataset.name_rows = names.clone();
    for slice in &mut dataset.slices {
        slice.names = names.clone();
    }
    dataset.tier_current_rows = tiers;
    dataset.tier_changelog_rows = changelog;

    let (old_tiers, old_changelog) = if request.history == HistoryPolicy::MergeExisting {
        load_existing_history(context, &mut diagnostics)
    } else {
        (Vec::new(), Vec::new())
    };
    dataset.tier_history_rows = merge_tier_history(old_tiers, dataset.tier_current_rows.clone());
    dataset.tier_changelog_history_rows =
        merge_changelog_history(old_changelog, dataset.tier_changelog_rows.clone());
    dataset.tier_usage_trend_rows =
        build_usage_trend(&dataset.tier_current_rows, &history_usage(dataset));
    diagnostics
}

async fn enrich_visible_teams<S: ZzzSupplementalSource + ?Sized>(
    dataset: &mut ZzzExportDataset,
    request: &ExportRequestV1,
    context: &ExportContext,
    source: &S,
    diagnostics: &mut Vec<Diagnostic>,
) {
    for mode in &request.modes {
        let Ok(resource_mode) = ZzzMode::try_from(*mode) else {
            continue;
        };
        let Some(index) = latest_slice_index(dataset, *mode) else {
            diagnostics.push(warning(
                diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                DiagnosticSource::Prydwen,
                Some(*mode),
                None,
                format!(
                    "Prydwen ZZZ visible teams skipped for {}: no local phase row",
                    mode.code()
                ),
            ));
            continue;
        };
        let document = match source
            .fetch(ZzzSupplementalResource::PrydwenTeams {
                mode: resource_mode,
            })
            .await
        {
            Ok(document) => document,
            Err(error) => {
                diagnostics.push(warning(
                    diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                    DiagnosticSource::Prydwen,
                    Some(*mode),
                    None,
                    format!("Prydwen ZZZ {} fetch failed: {error}", mode.code()),
                ));
                continue;
            }
        };
        record_cache_fallback(
            &document,
            context,
            DiagnosticSource::Prydwen,
            Some(*mode),
            diagnostics,
        );
        let visible = extract_visible_teams(&document.body);
        let raw_path = format!("raw/prydwen/{}.html", mode.code());
        let source_url = document.source_url.clone();
        let phase_updates = crate::zzz_sources::extract_phase_updates_from_html(&document.body);
        dataset
            .raw_text_artifacts
            .push((raw_path.clone(), document.body));
        if visible.is_empty() {
            diagnostics.push(warning(
                diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                DiagnosticSource::Prydwen,
                Some(*mode),
                Some(&raw_path),
                format!(
                    "Prydwen ZZZ {} parse warning: no visible teams extracted",
                    mode.code()
                ),
            ));
            continue;
        }
        let slice = &mut dataset.slices[index];
        if slice.phase.collect_date.is_empty() {
            if let Some(update) = phase_updates.get(&slice.phase.phase_ver) {
                preserve_usage_phase(slice);
                slice.phase.collect_date = update.collect_date.clone();
                append_note(
                    &mut slice.phase.note,
                    "collect_date backfilled from Prydwen visible phase selector",
                );
                slice.team_phase = Some(slice.phase.clone());
            }
        }
        for (scope, rows) in visible.into_entries() {
            let rows = rows
                .into_iter()
                .take(request.prydwen_top_n)
                .collect::<Vec<_>>();
            let mut parsed = parse_team_rows(rows, mode.code(), &scope);
            for row in &mut parsed {
                row.source_kind = "prydwen_page".into();
                row.source_file = raw_path.clone();
                row.source_url = source_url.clone();
            }
            slice.teams.extend(parsed);
        }
    }
}

async fn load_official_map<S: ZzzSupplementalSource + ?Sized>(
    source: &S,
    context: &ExportContext,
    dataset: &mut ZzzExportDataset,
    diagnostics: &mut Vec<Diagnostic>,
) -> BTreeMap<String, OfficialMapRow> {
    let agents = load_official_kind(
        source,
        context,
        HoyowikiEntryKind::Agent,
        "agents",
        dataset,
        diagnostics,
    )
    .await;
    let bangboo = load_official_kind(
        source,
        context,
        HoyowikiEntryKind::Bangboo,
        "bangboo",
        dataset,
        diagnostics,
    )
    .await;
    let agents = agents
        .map(|(en, zh)| parse_official_agents(&en, &zh))
        .unwrap_or_default();
    let bangboo = bangboo
        .map(|(en, zh)| parse_official_bangboo(&en, &zh))
        .unwrap_or_default();
    official_name_map(&agents, &bangboo)
}

async fn load_official_kind<S: ZzzSupplementalSource + ?Sized>(
    source: &S,
    context: &ExportContext,
    kind: HoyowikiEntryKind,
    filename_kind: &str,
    dataset: &mut ZzzExportDataset,
    diagnostics: &mut Vec<Diagnostic>,
) -> Option<(Vec<Value>, Vec<Value>)> {
    let zh = fetch_hoyowiki_pages(source, context, kind, Locale::ZhCn, diagnostics).await;
    let Ok(zh) = zh else {
        return None;
    };
    push_official_raw(dataset, filename_kind, "zh-cn", &zh);
    let en = fetch_hoyowiki_pages(source, context, kind, Locale::EnUs, diagnostics).await;
    let Ok(en) = en else {
        return None;
    };
    push_official_raw(dataset, filename_kind, "en-us", &en);
    Some((en, zh))
}

fn push_official_raw(
    dataset: &mut ZzzExportDataset,
    filename_kind: &str,
    locale: &str,
    rows: &[Value],
) {
    if let Ok(text) = serde_json::to_string_pretty(rows) {
        dataset.raw_text_artifacts.push((
            format!("raw/hoyowiki/zzz_{filename_kind}_{locale}.json"),
            text,
        ));
    }
}

async fn fetch_hoyowiki_pages<S: ZzzSupplementalSource + ?Sized>(
    source: &S,
    context: &ExportContext,
    kind: HoyowikiEntryKind,
    locale: Locale,
    diagnostics: &mut Vec<Diagnostic>,
) -> Result<Vec<Value>, ()> {
    let mut pages = Vec::<EntryPageData>::new();
    let mut count = 0_usize;
    let mut total = None;
    let mut page = 1_u32;
    loop {
        let document = match source
            .fetch(ZzzSupplementalResource::HoyowikiEntries {
                entry_kind: kind,
                locale,
                page,
            })
            .await
        {
            Ok(document) => document,
            Err(error) => {
                diagnostics.push(warning(
                    diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                    DiagnosticSource::Hoyowiki,
                    None,
                    None,
                    format!("HoYoWiki official ZZZ {kind:?} fetch failed: {error}"),
                ));
                return Err(());
            }
        };
        record_cache_fallback(
            &document,
            context,
            DiagnosticSource::Hoyowiki,
            None,
            diagnostics,
        );
        let data = match decode_entry_page_response(&document.body) {
            Ok(data) => data,
            Err(error) => {
                diagnostics.push(warning(
                    diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                    DiagnosticSource::Hoyowiki,
                    None,
                    None,
                    format!("HoYoWiki official ZZZ {kind:?} fetch failed: {error}"),
                ));
                return Err(());
            }
        };
        total = total.or(Some(data.total));
        let empty = data.list.is_empty();
        count += data.list.len();
        pages.push(data);
        if empty || total.is_some_and(|total| count >= total) {
            break;
        }
        page += 1;
    }
    Ok(merge_cached_pages(&pages))
}

fn build_names(
    dataset: &ZzzExportDataset,
    tiers: &[TierRow],
    official: &BTreeMap<String, OfficialMapRow>,
) -> Vec<NameRow> {
    let mut slugs = BTreeSet::new();
    for slice in &dataset.slices {
        slugs.extend(slice.usage.iter().map(|row| row.character_slug.clone()));
        for team in &slice.teams {
            slugs.extend([
                team.char_1_slug.clone(),
                team.char_2_slug.clone(),
                team.char_3_slug.clone(),
                team.bangboo_slug.clone(),
            ]);
        }
    }
    slugs.extend(tiers.iter().map(|row| row.character_slug.clone()));
    slugs.retain(|slug| !slug.is_empty());
    let tier_by_slug = tiers
        .iter()
        .map(|row| (character_slug(&row.character_slug), row))
        .collect::<BTreeMap<_, _>>();
    slugs
        .into_iter()
        .map(|raw_slug| {
            let slug = character_slug(&raw_slug);
            if let Some(row) = official.get(&slug) {
                NameRow {
                    character_slug: slug,
                    character_name_en: row.character_name_en.clone(),
                    character_name_cn: row.character_name_cn.clone(),
                    source: row.source.clone(),
                    needs_manual_check: if row.character_name_cn.is_empty() {
                        "1".into()
                    } else {
                        "0".into()
                    },
                    aliases: row.aliases.clone(),
                    kind: row.kind.clone(),
                    release_order: row.release_order.clone(),
                }
            } else {
                let tier = tier_by_slug.get(&slug);
                NameRow {
                    character_slug: slug,
                    character_name_en: tier
                        .map(|row| row.character_name_en.clone())
                        .unwrap_or_default(),
                    character_name_cn: String::new(),
                    source: "Prydwen/HF slug".into(),
                    needs_manual_check: "1".into(),
                    aliases: String::new(),
                    kind: "unknown".into(),
                    release_order: "9999".into(),
                }
            }
        })
        .collect()
}

fn enrich_names(dataset: &mut ZzzExportDataset, tiers: &mut [TierRow], names: &[NameRow]) {
    let names = names
        .iter()
        .map(|row| (row.character_slug.as_str(), row))
        .collect::<BTreeMap<_, _>>();
    let tier_info = tiers
        .iter()
        .map(|row| (row.character_slug.clone(), row.clone()))
        .collect::<BTreeMap<_, _>>();
    for slice in &mut dataset.slices {
        for row in &mut slice.usage {
            let name = names.get(row.character_slug.as_str());
            let tier = tier_info.get(&row.character_slug);
            row.character_name_en = name
                .map(|row| row.character_name_en.clone())
                .filter(|value| !value.is_empty())
                .or_else(|| tier.map(|row| row.character_name_en.clone()))
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| row.character_name_en.clone());
            if row.role.is_empty() {
                row.role = tier
                    .map(|row| {
                        if row.role_group_cn.is_empty() {
                            row.style_cn.clone()
                        } else {
                            row.role_group_cn.clone()
                        }
                    })
                    .unwrap_or_default();
            }
            if row.rarity.is_empty() {
                row.rarity = tier.map(|row| row.rarity.clone()).unwrap_or_default();
            }
        }
    }
    for row in tiers {
        if let Some(name) = names.get(row.character_slug.as_str()) {
            if !name.character_name_en.is_empty() {
                row.character_name_en = name.character_name_en.clone();
            }
            row.character_name_cn = name.character_name_cn.clone();
        }
    }
}

fn load_existing_history(
    context: &ExportContext,
    diagnostics: &mut Vec<Diagnostic>,
) -> (Vec<TierRow>, Vec<ChangelogRow>) {
    let Some(root) = context.existing_output_root.as_deref() else {
        return (Vec::new(), Vec::new());
    };
    let tiers = read_tier_history(&root.join("prydwen_tier_history.csv")).unwrap_or_else(|error| {
        if !is_not_found(&error) {
            diagnostics.push(warning(
                diagnostic_code::HISTORY_READ_FAILED,
                DiagnosticSource::History,
                None,
                Some("prydwen_tier_history.csv"),
                format!("failed to read existing ZZZ tier history: {error}"),
            ));
        }
        Vec::new()
    });
    let changelog = read_changelog_history(&root.join("prydwen_tier_changelog_history.csv"))
        .unwrap_or_else(|error| {
            if !is_not_found(&error) {
                diagnostics.push(warning(
                    diagnostic_code::HISTORY_READ_FAILED,
                    DiagnosticSource::History,
                    None,
                    Some("prydwen_tier_changelog_history.csv"),
                    format!("failed to read existing ZZZ changelog history: {error}"),
                ));
            }
            Vec::new()
        });
    (tiers, changelog)
}

fn read_tier_history(path: &Path) -> Result<Vec<TierRow>, MihoError> {
    Ok(read_csv_maps(path)?
        .into_iter()
        .map(|row| TierRow {
            tier_snapshot_id: cell(&row, "tier_snapshot_id"),
            fetched_at: cell(&row, "fetched_at"),
            tier_updated_at: cell(&row, "tier_updated_at"),
            tier_updated_date: cell(&row, "tier_updated_date"),
            tier_mode: cell(&row, "tier_mode"),
            tier_mode_cn: cell(&row, "tier_mode_cn"),
            character_slug: cell(&row, "character_slug"),
            character_name_en: cell(&row, "character_name_en"),
            character_name_cn: cell(&row, "character_name_cn"),
            prydwen_category: cell(&row, "prydwen_category"),
            prydwen_role: cell(&row, "prydwen_role"),
            role_group: cell(&row, "role_group"),
            role_group_cn: cell(&row, "role_group_cn"),
            tier: cell(&row, "tier"),
            rating: cell(&row, "rating"),
            tags: cell(&row, "tags"),
            marks: cell(&row, "marks"),
            is_new: cell(&row, "is_new"),
            element: cell(&row, "element"),
            element_cn: cell(&row, "element_cn"),
            style: cell(&row, "style"),
            style_cn: cell(&row, "style_cn"),
            faction: cell(&row, "faction"),
            rarity: cell(&row, "rarity"),
            icon_url: cell(&row, "icon_url"),
            source_url: cell(&row, "source_url"),
        })
        .collect())
}

fn read_changelog_history(path: &Path) -> Result<Vec<ChangelogRow>, MihoError> {
    Ok(read_csv_maps(path)?
        .into_iter()
        .map(|row| ChangelogRow {
            changelog_date: cell(&row, "changelog_date"),
            source_url: cell(&row, "source_url"),
            character_slugs: cell(&row, "character_slugs"),
            text: cell(&row, "text"),
        })
        .collect())
}

fn read_csv_maps(path: &Path) -> Result<Vec<BTreeMap<String, String>>, MihoError> {
    let bytes = fs::read(path).map_err(|source| MihoError::Read {
        path: path.to_owned(),
        source,
    })?;
    let bytes = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(&bytes);
    let mut reader = csv::ReaderBuilder::new().flexible(true).from_reader(bytes);
    let headers = reader.headers()?.clone();
    reader
        .records()
        .map(|record| {
            let record = record?;
            Ok(headers
                .iter()
                .zip(record.iter())
                .map(|(key, value)| (key.to_owned(), value.to_owned()))
                .collect())
        })
        .collect()
}

fn history_usage(dataset: &ZzzExportDataset) -> Vec<HistoryUsageRow> {
    dataset
        .slices
        .iter()
        .flat_map(|slice| {
            let phase = slice.usage_phase.as_ref().unwrap_or(&slice.phase);
            slice.usage.iter().map(|row| HistoryUsageRow {
                mode: phase.mode.clone(),
                sub_mode: row.sub_mode.clone(),
                character_slug: row.character_slug.clone(),
                collect_date: phase.collect_date.clone(),
                phase_ver: phase.phase_ver.clone(),
                phase_name: phase.phase_name.clone(),
                app_rate: csv_float(row.app_rate),
                avg_score: csv_float(row.avg_score),
                quality_flag: row.quality_flag.clone(),
            })
        })
        .collect()
}

fn apply_phase_overrides(dataset: &mut ZzzExportDataset, context: &ExportContext) {
    let Some(path) = context.zzz_phase_overrides.as_deref() else {
        return;
    };
    let Some(overrides) = load_phase_overrides(path) else {
        return;
    };
    for slice in &mut dataset.slices {
        let Some(row) = overrides.get(&(slice.phase.mode.clone(), slice.phase.phase_ver.clone()))
        else {
            continue;
        };
        preserve_usage_phase(slice);
        let mut team_phase = slice
            .team_phase
            .clone()
            .unwrap_or_else(|| slice.phase.clone());
        for (source, target) in [
            ("collect_date", &mut slice.phase.collect_date),
            ("start_date", &mut slice.phase.start_date),
            ("end_date", &mut slice.phase.end_date),
            ("source_label", &mut slice.phase.source),
            ("source_url", &mut slice.phase.source_path),
        ] {
            if let Some(value) = row
                .get(source)
                .and_then(Value::as_str)
                .filter(|v| !v.is_empty())
            {
                *target = value.to_owned();
            }
        }
        if let Some(note) = row
            .get("note")
            .and_then(Value::as_str)
            .filter(|v| !v.is_empty())
        {
            append_note(&mut slice.phase.note, note);
        }
        fill_missing(&mut team_phase.collect_date, &slice.phase.collect_date);
        fill_missing(&mut team_phase.start_date, &slice.phase.start_date);
        fill_missing(&mut team_phase.end_date, &slice.phase.end_date);
        slice.team_phase = Some(team_phase);
    }
}

pub fn first_valid_phase_override_path(
    candidates: impl IntoIterator<Item = std::path::PathBuf>,
) -> Option<std::path::PathBuf> {
    candidates
        .into_iter()
        .find(|path| load_phase_overrides(path).is_some())
}

fn load_phase_overrides(
    path: &Path,
) -> Option<BTreeMap<(String, String), serde_json::Map<String, Value>>> {
    let text = fs::read_to_string(path).ok()?;
    let value = serde_json::from_str::<Value>(&text).ok()?;
    let rows = match &value {
        Value::Object(object) => object.get("phases")?.as_array()?,
        Value::Array(rows) => rows,
        _ => return None,
    };
    Some(
        rows.iter()
            .filter_map(|row| {
                let row = row.as_object()?;
                let mode = row.get("mode")?.as_str()?.to_owned();
                let phase_ver = row.get("phase_ver")?.as_str()?.to_owned();
                Some(((mode, phase_ver), row.clone()))
            })
            .collect(),
    )
}

fn latest_slice_index(dataset: &ZzzExportDataset, mode: GameMode) -> Option<usize> {
    let mut latest: Option<(usize, (Vec<u64>, String))> = None;
    for (index, slice) in dataset.slices.iter().enumerate() {
        if slice.phase.mode != mode.code() {
            continue;
        }
        let recency = phase_recency(&slice.phase);
        if latest
            .as_ref()
            .is_none_or(|(_, current)| recency >= *current)
        {
            latest = Some((index, recency));
        }
    }
    latest.map(|(index, _)| index)
}

fn phase_recency(phase: &crate::zzz::PhaseRow) -> (Vec<u64>, String) {
    let snapshot = version_tuple(&phase.snapshot_id);
    let version = if snapshot.is_empty() {
        let phase_version = version_tuple(&phase.phase_ver);
        if phase_version.is_empty() {
            vec![0]
        } else {
            phase_version
        }
    } else {
        snapshot
    };
    (version, phase.collect_date.clone())
}

fn version_tuple(value: &str) -> Vec<u64> {
    value
        .split(|character: char| !character.is_ascii_digit())
        .filter(|part| !part.is_empty())
        .filter_map(|part| part.parse().ok())
        .collect()
}

fn preserve_usage_phase(slice: &mut crate::zzz_export::ZzzExportSlice) {
    if slice.usage_phase.is_none() {
        slice.usage_phase = Some(slice.phase.clone());
    }
}

fn fill_missing(target: &mut String, source: &str) {
    if target.is_empty() && !source.is_empty() {
        *target = source.to_owned();
    }
}

fn append_note(target: &mut String, suffix: &str) {
    if target.is_empty() {
        *target = suffix.to_owned();
    } else if !target.contains(suffix) {
        target.push_str("; ");
        target.push_str(suffix);
    }
}

fn record_cache_fallback(
    document: &SupplementalDocument,
    context: &ExportContext,
    source: DiagnosticSource,
    mode: Option<GameMode>,
    diagnostics: &mut Vec<Diagnostic>,
) {
    if context.fetch_policy == FetchPolicy::Online && document.origin == SupplementalOrigin::Cache {
        let reason = document
            .fallback_reason
            .as_deref()
            .map(|value| format!(": {value}"))
            .unwrap_or_default();
        diagnostics.push(warning(
            diagnostic_code::SUPPLEMENTAL_CACHE_FALLBACK,
            source,
            mode,
            None,
            format!(
                "supplemental source failed; using cached document {}{}",
                document.source_url, reason
            ),
        ));
    }
}

fn warning(
    code: &str,
    source: DiagnosticSource,
    mode: Option<GameMode>,
    path: Option<&str>,
    message: impl Into<String>,
) -> Diagnostic {
    Diagnostic {
        severity: DiagnosticSeverity::Warning,
        code: code.into(),
        source,
        game: Game::Zzz,
        snapshot: None,
        mode,
        path: path.map(str::to_owned),
        message: message.into(),
    }
}

fn cell(row: &BTreeMap<String, String>, key: &str) -> String {
    row.get(key).cloned().unwrap_or_default()
}

fn is_not_found(error: &MihoError) -> bool {
    matches!(
        error,
        MihoError::Read { source, .. } if source.kind() == std::io::ErrorKind::NotFound
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn history_reader_tolerates_short_legacy_records() {
        let path =
            std::env::temp_dir().join(format!("miho-zzz-short-history-{}.csv", std::process::id()));
        fs::write(
            &path,
            "tier_snapshot_id,fetched_at,tier_updated_at,tier_updated_date\r\n20260707,fixture\r\n",
        )
        .unwrap();

        let rows = read_tier_history(&path).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].tier_snapshot_id, "20260707");
        assert_eq!(rows[0].fetched_at, "fixture");
        assert!(rows[0].tier_updated_at.is_empty());
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn phase_recency_prefers_numeric_snapshot_before_collect_date() {
        let older_snapshot = crate::zzz::make_phase_row(crate::zzz::PhaseInput {
            snapshot_id: "1.9.9".into(),
            mode: "sd".into(),
            collect_date: "31/12/2026".into(),
            ver: "99.0".into(),
            name: String::new(),
            start: String::new(),
            end: String::new(),
            source_path: String::new(),
        });
        let newer_snapshot = crate::zzz::make_phase_row(crate::zzz::PhaseInput {
            snapshot_id: "2.0.0".into(),
            mode: "sd".into(),
            collect_date: String::new(),
            ver: "1.0".into(),
            name: String::new(),
            start: String::new(),
            end: String::new(),
            source_path: String::new(),
        });
        assert!(phase_recency(&newer_snapshot) > phase_recency(&older_snapshot));
    }
}
