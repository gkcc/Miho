use std::{collections::BTreeMap, fs, path::Path};

use chrono::Local;
use serde_json::Value;

use crate::{
    contract::{
        diagnostic_code, Diagnostic, DiagnosticSeverity, DiagnosticSource, ExportContext,
        ExportRequestV1, FetchPolicy, Game, GameMode, HistoryPolicy,
    },
    hsr::parse_team_rows,
    hsr_export::HsrExportDataset,
    hsr_history::{
        build_tier_usage_trend, merge_changelog_history, merge_tier_history,
        render_tier_usage_charts, UsagePoint,
    },
    hsr_names::{
        add_candidate, build_name_rows, chinese_name, english_name, parse_seed_csv, NameCandidates,
        NameRow,
    },
    hsr_sources::{
        build_tier_rows_at, decode_prydwen_payload, extract_changelog, extract_characters,
        extract_last_updated, extract_visible_team_scopes, official_names, tier_snapshot_id,
        ChangelogRow, OfficialName, TierRow,
    },
    supplemental::{
        HsrMode, HsrSupplementalResource, HsrSupplementalSource, Locale, SupplementalDocument,
        SupplementalOrigin,
    },
    MihoError,
};

pub async fn enrich_hsr_dataset<S: HsrSupplementalSource + ?Sized>(
    dataset: &mut HsrExportDataset,
    request: &ExportRequestV1,
    context: &ExportContext,
    source: &S,
) -> Vec<Diagnostic> {
    let mut diagnostics = Vec::new();
    dataset.display_output_root = Some(context.output_root.clone());

    if request.features.prydwen_visible {
        enrich_visible_teams(dataset, request, context, source, &mut diagnostics).await;
    }

    let mut current_tiers = Vec::new();
    let mut current_changelog = Vec::new();
    if request.features.prydwen_tier {
        match source.fetch(HsrSupplementalResource::PrydwenTier).await {
            Ok(document) => {
                record_cache_fallback(
                    &document,
                    context,
                    DiagnosticSource::Prydwen,
                    None,
                    &mut diagnostics,
                );
                let decoded = decode_prydwen_payload(&document.body);
                let updated_at = extract_last_updated(&decoded);
                let snapshot_id = tier_snapshot_id(&updated_at);
                let fetched_at = context
                    .fetched_at
                    .with_timezone(&Local)
                    .format("%Y-%m-%dT%H:%M:%S")
                    .to_string();
                current_tiers = build_tier_rows_at(
                    &extract_characters(&decoded),
                    &updated_at,
                    &snapshot_id,
                    &fetched_at,
                );
                current_changelog = extract_changelog(&decoded);
                dataset.raw_text_artifacts.push((
                    "raw/prydwen_tier/tier-list_latest.html".into(),
                    document.body.clone(),
                ));
                if !snapshot_id.is_empty() {
                    dataset.raw_text_artifacts.push((
                        format!("raw/prydwen_tier/tier-list_{snapshot_id}.html"),
                        document.body,
                    ));
                }
                if current_tiers.is_empty() {
                    diagnostics.push(warning(
                        diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                        DiagnosticSource::Prydwen,
                        None,
                        Some("raw/prydwen_tier/tier-list_latest.html"),
                        "Prydwen tier parse warning: no tier rows extracted",
                    ));
                }
                if current_changelog.is_empty() {
                    diagnostics.push(warning(
                        diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                        DiagnosticSource::Prydwen,
                        None,
                        Some("raw/prydwen_tier/tier-list_latest.html"),
                        "Prydwen tier parse warning: no changelog rows extracted",
                    ));
                }
            }
            Err(error) => diagnostics.push(warning(
                diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                DiagnosticSource::Prydwen,
                None,
                None,
                format!("Prydwen tier fetch failed: {error}"),
            )),
        }
    }

    let official = if request.features.official_names {
        load_official_names(source, context, dataset, &mut diagnostics).await
    } else {
        BTreeMap::new()
    };
    let seed = load_seed(request, &mut diagnostics);
    let candidates = collect_candidates(dataset, &current_tiers);
    let (name_rows, _) = build_name_rows(&candidates, &seed, &official);
    enrich_names(dataset, &mut current_tiers, &candidates, &seed, &official);
    dataset.name_rows = name_rows;
    dataset.tier_current_rows = current_tiers;
    dataset.tier_changelog_rows = current_changelog;

    let (existing_tiers, existing_changelog) = if request.history == HistoryPolicy::MergeExisting {
        load_existing_history(context, &mut diagnostics)
    } else {
        (Vec::new(), Vec::new())
    };
    dataset.tier_history_rows =
        merge_tier_history(existing_tiers, dataset.tier_current_rows.clone());
    dataset.tier_changelog_history_rows =
        merge_changelog_history(existing_changelog, dataset.tier_changelog_rows.clone());
    let usage = usage_points(dataset);
    dataset.tier_usage_trend_rows = build_tier_usage_trend(&dataset.tier_current_rows, &usage);
    dataset.tier_charts = render_tier_usage_charts(&dataset.tier_usage_trend_rows);

    diagnostics
}

async fn enrich_visible_teams<S: HsrSupplementalSource + ?Sized>(
    dataset: &mut HsrExportDataset,
    request: &ExportRequestV1,
    context: &ExportContext,
    source: &S,
    diagnostics: &mut Vec<Diagnostic>,
) {
    for mode in &request.modes {
        let Ok(resource_mode) = HsrMode::try_from(*mode) else {
            continue;
        };
        let Some(slice_index) = latest_slice_index(dataset, *mode) else {
            diagnostics.push(warning(
                diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                DiagnosticSource::Prydwen,
                Some(*mode),
                None,
                format!(
                    "Prydwen skipped for {}: no phase row available",
                    mode.code()
                ),
            ));
            continue;
        };
        let document = match source
            .fetch(HsrSupplementalResource::PrydwenTeams {
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
                    format!("Prydwen fetch failed for {}: {error}", mode.code()),
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
        let scopes = extract_visible_team_scopes(&document.body);
        let raw_path = format!("raw/prydwen/{}.html", mode.code());
        dataset
            .raw_text_artifacts
            .push((raw_path.clone(), document.body));
        if scopes.is_empty() {
            diagnostics.push(warning(
                diagnostic_code::SUPPLEMENTAL_PARSE_EMPTY,
                DiagnosticSource::Prydwen,
                Some(*mode),
                Some(&raw_path),
                format!(
                    "Prydwen parse warning for {}: no ranked team JSON block found",
                    mode.code()
                ),
            ));
            continue;
        }
        let phase = dataset.slices[slice_index].phase.clone();
        let source_file = display_path(context, &raw_path);
        let mut parsed = Vec::new();
        for scope in scopes {
            let mut rows = parse_team_rows(
                &Value::Array(scope.rows),
                mode.code(),
                &phase.phase_ver,
                "top_combined.json",
                Some(request.prydwen_top_n),
            );
            for row in &mut rows {
                row.scope = scope.scope.clone();
                row.sub_mode = if *mode == GameMode::HsrAa {
                    "all_bosses".into()
                } else {
                    "all".into()
                };
                row.sub_mode_cn = if *mode == GameMode::HsrAa {
                    "全 Boss / 未拆分".into()
                } else {
                    "全部".into()
                };
                row.source_kind = "prydwen_page".into();
                row.source_file = source_file.clone();
                row.source_url = document.source_url.clone();
            }
            parsed.extend(rows);
        }
        dataset.slices[slice_index].teams.extend(parsed);
    }
}

async fn load_official_names<S: HsrSupplementalSource + ?Sized>(
    source: &S,
    context: &ExportContext,
    dataset: &mut HsrExportDataset,
    diagnostics: &mut Vec<Diagnostic>,
) -> BTreeMap<String, OfficialName> {
    let zh = fetch_hoyowiki_language(source, Locale::ZhCn, context, diagnostics).await;
    let en = fetch_hoyowiki_language(source, Locale::EnUs, context, diagnostics).await;
    let (Ok(zh), Ok(en)) = (zh, en) else {
        return BTreeMap::new();
    };
    if let Ok(text) = serde_json::to_string_pretty(&zh) {
        dataset
            .raw_text_artifacts
            .push(("raw/hoyowiki/hsr_characters_zh-cn.json".into(), text));
    }
    if let Ok(text) = serde_json::to_string_pretty(&en) {
        dataset
            .raw_text_artifacts
            .push(("raw/hoyowiki/hsr_characters_en-us.json".into(), text));
    }
    official_names(&zh, &en)
}

async fn fetch_hoyowiki_language<S: HsrSupplementalSource + ?Sized>(
    source: &S,
    locale: Locale,
    context: &ExportContext,
    diagnostics: &mut Vec<Diagnostic>,
) -> Result<Vec<Value>, ()> {
    let mut rows = Vec::new();
    let mut total = None;
    let mut page = 1_u32;
    loop {
        let document = match source
            .fetch(HsrSupplementalResource::HoyowikiCharacters { locale, page })
            .await
        {
            Ok(document) => document,
            Err(error) => {
                diagnostics.push(warning(
                    diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                    DiagnosticSource::Hoyowiki,
                    None,
                    None,
                    format!("HoYoWiki official name fetch failed: {error}"),
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
        let (mut page_rows, page_total) = match decode_hoyowiki_page(&document.body) {
            Ok(value) => value,
            Err(error) => {
                diagnostics.push(warning(
                    diagnostic_code::SUPPLEMENTAL_FETCH_FAILED,
                    DiagnosticSource::Hoyowiki,
                    None,
                    None,
                    format!("HoYoWiki official name fetch failed: {error}"),
                ));
                return Err(());
            }
        };
        total = total.or(Some(page_total));
        let empty = page_rows.is_empty();
        rows.append(&mut page_rows);
        if empty || total.is_some_and(|total| rows.len() >= total) {
            break;
        }
        page += 1;
    }
    Ok(rows)
}

fn decode_hoyowiki_page(text: &str) -> Result<(Vec<Value>, usize), MihoError> {
    let value: Value = serde_json::from_str(text).map_err(|source| MihoError::Json {
        path: "hoyowiki_response.json".into(),
        source,
    })?;
    if value.get("retcode").and_then(Value::as_i64) != Some(0) {
        return Err(MihoError::Unsupported(format!(
            "HoYoWiki returned retcode {}: {}",
            value.get("retcode").map(value_text).unwrap_or_default(),
            value.get("message").map(value_text).unwrap_or_default()
        )));
    }
    let data = value.get("data").and_then(Value::as_object);
    let rows = data
        .and_then(|data| data.get("list"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let total = data
        .and_then(|data| data.get("total"))
        .and_then(value_usize)
        .unwrap_or_default();
    Ok((rows, total))
}

fn load_seed(
    request: &ExportRequestV1,
    diagnostics: &mut Vec<Diagnostic>,
) -> BTreeMap<String, NameRow> {
    let Some(path) = &request.name_map_seed else {
        return BTreeMap::new();
    };
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) => {
            diagnostics.push(warning(
                diagnostic_code::NAME_SEED_FAILED,
                DiagnosticSource::NameSeed,
                None,
                path.to_str(),
                if error.kind() == std::io::ErrorKind::NotFound {
                    format!("name map seed not found: {}", path.display())
                } else {
                    format!("name map seed read failed: {}: {error}", path.display())
                },
            ));
            return BTreeMap::new();
        }
    };
    match parse_seed_csv(&bytes) {
        Ok(rows) => rows,
        Err(error) => {
            diagnostics.push(warning(
                diagnostic_code::NAME_SEED_FAILED,
                DiagnosticSource::NameSeed,
                None,
                path.to_str(),
                format!("name map seed parse failed: {}: {error}", path.display()),
            ));
            BTreeMap::new()
        }
    }
}

fn collect_candidates(dataset: &HsrExportDataset, tiers: &[TierRow]) -> NameCandidates {
    let mut candidates = NameCandidates::new();
    for slice in &dataset.slices {
        for row in &slice.characters {
            add_candidate(
                &mut candidates,
                &row.character_slug,
                &row.character_name_en,
                if row.source_kind.is_empty() {
                    &row.source_file
                } else {
                    &row.source_kind
                },
            );
        }
    }
    for slice in &dataset.histograph_slices {
        for row in &slice.rows {
            add_candidate(
                &mut candidates,
                &row.character_slug,
                &row.character_name_en,
                &row.source_file,
            );
        }
    }
    for slice in &dataset.slices {
        for row in &slice.teams {
            for slug in &row.chars {
                add_candidate(
                    &mut candidates,
                    slug,
                    "",
                    if row.source_kind.is_empty() {
                        "team"
                    } else {
                        &row.source_kind
                    },
                );
            }
        }
    }
    for row in tiers {
        add_candidate(
            &mut candidates,
            &row.character_slug,
            &row.character_name_en,
            "source",
        );
    }
    candidates
}

fn enrich_names(
    dataset: &mut HsrExportDataset,
    tiers: &mut [TierRow],
    candidates: &NameCandidates,
    seed: &BTreeMap<String, NameRow>,
    official: &BTreeMap<String, OfficialName>,
) {
    for slice in &mut dataset.slices {
        for row in &mut slice.characters {
            row.character_name_en = english_name(candidates, seed, official, &row.character_slug);
        }
    }
    for slice in &mut dataset.histograph_slices {
        for row in &mut slice.rows {
            row.character_name_en = english_name(candidates, seed, official, &row.character_slug);
        }
    }
    for row in tiers {
        row.character_name_en = english_name(candidates, seed, official, &row.character_slug);
        row.character_name_cn = chinese_name(seed, official, &row.character_slug);
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
                format!("failed to read existing Prydwen tier history: {error}"),
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
                    format!("failed to read existing Prydwen changelog history: {error}"),
                ));
            }
            Vec::new()
        });
    (tiers, changelog)
}

fn read_tier_history(path: &Path) -> Result<Vec<TierRow>, MihoError> {
    let records = read_csv_maps(path)?;
    Ok(records
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
            rating: row.get("rating").and_then(|value| value.parse().ok()),
            special_rating: Value::String(cell(&row, "special_rating")),
            tags: Value::String(cell(&row, "tags")),
            marks: Value::String(cell(&row, "marks")),
            is_new: Value::String(cell(&row, "is_new")),
            default_role: cell(&row, "default_role"),
            element: cell(&row, "element"),
            path: cell(&row, "path"),
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
    let mut reader = csv::Reader::from_reader(bytes);
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

fn usage_points(dataset: &HsrExportDataset) -> Vec<UsagePoint> {
    dataset
        .slices
        .iter()
        .flat_map(|slice| {
            slice.characters.iter().map(|row| UsagePoint {
                mode: slice.phase.mode.clone(),
                sub_mode: if slice.phase.mode == "aa" {
                    "all_bosses".into()
                } else {
                    "all".into()
                },
                character_slug: row.character_slug.clone(),
                collect_date: slice.phase.collect_date.clone(),
                phase_ver: slice.phase.phase_ver.clone(),
                phase_name: slice.phase.phase_name.clone(),
                app_rate: row.app_rate,
                avg_round: row.avg_round,
                quality_flag: row.quality_flag.clone(),
            })
        })
        .collect()
}

fn latest_slice_index(dataset: &HsrExportDataset, mode: GameMode) -> Option<usize> {
    let mut latest = None;
    for (index, slice) in dataset.slices.iter().enumerate() {
        if slice.phase.mode != mode.code() {
            continue;
        }
        if latest.is_none_or(|(_, date): (usize, &str)| slice.phase.collect_date.as_str() >= date) {
            latest = Some((index, slice.phase.collect_date.as_str()));
        }
    }
    latest.map(|(index, _)| index)
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
            .map(|reason| format!(": {reason}"))
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
        game: Game::Hsr,
        snapshot: None,
        mode,
        path: path.map(str::to_owned),
        message: message.into(),
    }
}

fn display_path(context: &ExportContext, relative: &str) -> String {
    context
        .output_root
        .join(relative.replace('/', std::path::MAIN_SEPARATOR_STR))
        .to_string_lossy()
        .into_owned()
}

fn value_text(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::String(value) => value.clone(),
        _ => value.to_string(),
    }
}

fn value_usize(value: &Value) -> Option<usize> {
    value
        .as_u64()
        .and_then(|value| usize::try_from(value).ok())
        .or_else(|| value.as_str()?.parse().ok())
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
