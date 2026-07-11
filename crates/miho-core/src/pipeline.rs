use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};

use chrono::NaiveDate;
use serde::Deserialize;
use serde_json::Value;

pub use crate::contract::{ExportRequestV1 as ExportRequest, Game};

use crate::{
    contract::{
        diagnostic_code, Diagnostic, DiagnosticSeverity, DiagnosticSource, ExportContext,
        ExportOutcome,
    },
    hf::TreeEntry,
    hsr::{
        histograph_fallback_character_rows, make_phase_row as make_hsr_phase,
        parse_builds_character_rows as parse_hsr_builds,
        parse_histograph_rows as parse_hsr_histograph, parse_team_rows as parse_hsr_teams,
    },
    hsr_export::{
        build_dataset_export as build_hsr_dataset, build_minimal_export as build_hsr_export,
        HsrExportDataset, HsrExportSlice, HsrHistographSlice, TierRow,
    },
    normalize::parse_date,
    output::ArtifactBundle,
    report::finalize_export_bundle,
    source::{SnapshotSource, SourceFuture},
    zzz::{
        make_phase_row as make_zzz_phase, parse_bangboo_rows as parse_zzz_bangboo,
        parse_team_rows as parse_zzz_teams, parse_usage, PhaseInput,
    },
    zzz_export::{
        build_dataset_export as build_zzz_dataset, build_minimal_bundle as build_zzz_export,
        fallback_name_rows, NameRow, ZzzExportDataset, ZzzExportSlice,
    },
    MihoError, Result,
};

#[derive(Debug, Deserialize)]
pub struct OfflineManifest {
    pub schema_version: u8,
    pub game: Game,
    pub repo_id: String,
    #[serde(default = "main_revision")]
    pub revision: String,
    #[serde(default)]
    pub root_tree: Vec<TreeEntry>,
    #[serde(default)]
    pub trees: BTreeMap<String, Vec<TreeEntry>>,
    #[serde(default)]
    pub list_failures: BTreeMap<String, Value>,
    #[serde(default)]
    pub download_failures: BTreeMap<String, Value>,
}

fn main_revision() -> String {
    "main".into()
}

pub struct OfflineFixture {
    root: PathBuf,
    pub manifest: OfflineManifest,
}

pub struct PipelineRun {
    pub bundle: ArtifactBundle,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

impl OfflineFixture {
    pub fn load(root: impl Into<PathBuf>) -> Result<Self> {
        let root = root.into();
        let path = root.join("manifest.json");
        let text = fs::read_to_string(&path).map_err(|source| MihoError::Read {
            path: path.clone(),
            source,
        })?;
        let manifest: OfflineManifest =
            serde_json::from_str(&text).map_err(|source| MihoError::Json { path, source })?;
        if manifest.schema_version != 1 {
            return Err(MihoError::Unsupported(format!(
                "offline manifest schema {} is not supported",
                manifest.schema_version
            )));
        }
        Ok(Self { root, manifest })
    }

    pub fn snapshots(&self) -> Vec<String> {
        let mut snapshots = self
            .manifest
            .root_tree
            .iter()
            .filter(|entry| entry.kind == "directory" && is_version(&entry.path))
            .map(|entry| entry.path.clone())
            .collect::<Vec<_>>();
        snapshots.sort();
        snapshots
    }

    pub fn run_hsr(&self, snapshot: &str, mode: &str) -> Result<PipelineRun> {
        if self.manifest.game != Game::Hsr {
            return Err(MihoError::Unsupported("offline fixture is not hsr".into()));
        }
        self.require_snapshot(snapshot)?;
        let mut warnings = vec![];
        let errors = self.failure_messages();
        let config = self.read_json("config.json")?;
        let mut entry = config.get(snapshot).cloned().unwrap_or_else(|| {
            warnings.push(format!("{snapshot}: config missing; dates unavailable"));
            serde_json::json!({})
        });
        prepare_hsr_dates(&mut entry, mode);
        let paths = self.tree_paths(snapshot);
        let builds_path = format!("{snapshot}/builds.json");
        let builds = if paths.contains(&builds_path) {
            self.read_json(&builds_path)?
        } else {
            Value::Array(vec![])
        };
        let characters = parse_hsr_builds(&builds, mode);
        let comp_tree = format!("{snapshot}/{mode}/comps");
        let mut teams = vec![];
        for path in self.json_files(&comp_tree, &mut warnings) {
            teams.extend(parse_hsr_teams(
                &self.read_json(&path)?,
                mode,
                entry
                    .pointer(&format!("/{mode}/ver"))
                    .and_then(Value::as_str)
                    .unwrap_or(snapshot),
                &path,
                None,
            ));
        }
        let phase = make_hsr_phase(
            snapshot,
            &entry,
            mode,
            &format!("{snapshot}/"),
            !characters.is_empty(),
            !teams.is_empty(),
            paths.contains(&format!("{snapshot}/histograph.json")),
            entry
                .get("collect_date")
                .and_then(Value::as_str)
                .map(parse_date)
                .unwrap_or_default()
                .as_str(),
        );
        let bundle = build_hsr_export(&phase, &characters, &teams, &Vec::<TierRow>::new())?;
        Ok(PipelineRun {
            bundle,
            warnings,
            errors,
        })
    }

    pub fn run_zzz(&self, snapshot: &str, mode: &str) -> Result<PipelineRun> {
        if self.manifest.game != Game::Zzz {
            return Err(MihoError::Unsupported("offline fixture is not zzz".into()));
        }
        self.require_snapshot(snapshot)?;
        let mut warnings = vec![];
        let errors = self.failure_messages();
        let config = self.read_json("config.json")?;
        let entry = config.get(snapshot).cloned().unwrap_or_else(|| {
            warnings.push(format!("{snapshot}: config missing; dates unavailable"));
            serde_json::json!({"collect_date":"", mode:{"ver":snapshot}})
        });
        let mode_config = entry.get(mode).and_then(Value::as_object).ok_or_else(|| {
            MihoError::Unsupported(format!("{snapshot}/{mode}: mode config missing"))
        })?;
        let phase = make_zzz_phase(PhaseInput {
            snapshot_id: snapshot.into(),
            mode: mode.into(),
            collect_date: entry
                .get("collect_date")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            ver: mode_config
                .get("ver")
                .and_then(Value::as_str)
                .unwrap_or(snapshot)
                .into(),
            name: mode_config
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            start: mode_config
                .get("start")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            end: mode_config
                .get("end")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            source_path: format!("{snapshot}/"),
        });
        let paths = self.tree_paths(snapshot);
        let builds_path = format!("{snapshot}/builds.json");
        let mut usage = vec![];
        if paths.contains(&builds_path) {
            if let Some(rows) = self.read_json(&builds_path)?.as_array() {
                for row in rows {
                    usage.extend(parse_usage(row, mode));
                }
            } else {
                warnings.push(format!("{builds_path} was not a list; skipped"));
            }
        }
        let comp_tree = format!("{snapshot}/{mode}/comps");
        let mut teams = vec![];
        for path in self.json_files(&comp_tree, &mut warnings) {
            let data = self.read_json(&path)?;
            if let Some(rows) = data.as_array() {
                teams.extend(parse_zzz_teams(
                    rows.clone(),
                    mode,
                    Path::new(&path)
                        .file_name()
                        .and_then(|v| v.to_str())
                        .unwrap_or_default(),
                ));
            }
        }
        let bundle = build_zzz_export(&phase, &usage, &teams, &Vec::<NameRow>::new())?;
        Ok(PipelineRun {
            bundle,
            warnings,
            errors,
        })
    }

    fn read_json(&self, relative: &str) -> Result<Value> {
        if self.manifest.download_failures.contains_key(relative) {
            return Err(MihoError::Unsupported(format!(
                "offline download failure: {relative}"
            )));
        }
        let relative_path = Path::new(relative);
        if relative_path.is_absolute()
            || relative_path
                .components()
                .any(|part| !matches!(part, Component::Normal(_)))
        {
            return Err(MihoError::InvalidCacheKey(relative.into()));
        }
        let path = self.root.join("raw/hf").join(relative_path);
        let text = fs::read_to_string(&path).map_err(|source| MihoError::Read {
            path: path.clone(),
            source,
        })?;
        serde_json::from_str(&text).map_err(|source| MihoError::Json { path, source })
    }

    fn tree_paths(&self, key: &str) -> Vec<String> {
        self.manifest
            .trees
            .get(key)
            .into_iter()
            .flatten()
            .map(|entry| entry.path.clone())
            .collect()
    }

    fn json_files(&self, key: &str, warnings: &mut Vec<String>) -> Vec<String> {
        if let Some(failure) = self.manifest.list_failures.get(key) {
            warnings.push(format!("optional tree {key} unavailable: {failure}"));
            return vec![];
        }
        self.manifest
            .trees
            .get(key)
            .into_iter()
            .flatten()
            .filter(|entry| entry.kind == "file" && entry.path.ends_with(".json"))
            .map(|entry| entry.path.clone())
            .collect()
    }

    fn failure_messages(&self) -> Vec<String> {
        self.manifest
            .download_failures
            .keys()
            .map(|path| format!("offline download failure: {path}"))
            .collect()
    }

    fn require_snapshot(&self, snapshot: &str) -> Result<()> {
        if self.snapshots().iter().any(|value| value == snapshot) {
            Ok(())
        } else {
            Err(MihoError::Unsupported(format!(
                "snapshot not present in root tree: {snapshot}"
            )))
        }
    }
}

impl SnapshotSource for OfflineFixture {
    fn list_tree<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Vec<TreeEntry>> {
        Box::pin(async move {
            if let Some(failure) = self.manifest.list_failures.get(path) {
                return Err(MihoError::Unsupported(format!(
                    "offline list failure for {path}: {failure}"
                )));
            }
            if path.is_empty() {
                Ok(self.manifest.root_tree.clone())
            } else {
                Ok(self.manifest.trees.get(path).cloned().unwrap_or_default())
            }
        })
    }

    fn read_json<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Value> {
        Box::pin(async move { OfflineFixture::read_json(self, path) })
    }

    fn raw_url(&self, path: &str) -> String {
        format!(
            "offline://{}/{}/{}",
            self.manifest.repo_id, self.manifest.revision, path
        )
    }

    fn dataset_ref(&self) -> Option<crate::contract::DatasetRef> {
        Some(crate::contract::DatasetRef {
            repo_id: self.manifest.repo_id.clone(),
            revision: self.manifest.revision.clone(),
        })
    }
}

pub async fn run_source_export<S: SnapshotSource>(
    source: &S,
    request: &ExportRequest,
) -> Result<PipelineRun> {
    request.validate()?;
    if let Some(actual) = source.dataset_ref() {
        if actual != request.dataset {
            return Err(MihoError::Unsupported(format!(
                "snapshot source dataset {}/{} does not match request {}/{}",
                actual.repo_id, actual.revision, request.dataset.repo_id, request.dataset.revision
            )));
        }
    }
    // Python records a failed root-tree request and then fails at the stable
    // structural boundary below. Preserve that public error instead of
    // leaking transport-specific details through the CLI contract.
    let root = source.list_tree("").await.unwrap_or_default();
    let mut snapshots = root
        .into_iter()
        .filter(|entry| entry.kind == "directory" && is_version(&entry.path))
        .map(|entry| entry.path)
        .collect::<Vec<_>>();
    snapshots.sort();
    if snapshots.is_empty() {
        return Err(MihoError::Unsupported(
            "no version directories found in Hugging Face dataset root".into(),
        ));
    }
    let mut warnings = vec![];
    let mut errors = vec![];
    let config = match source.read_json("config.json").await {
        Ok(value) => value,
        Err(error) => {
            errors.push(format!("failed to load config.json: {error}"));
            Value::Object(Default::default())
        }
    };
    snapshots.retain(|snapshot| {
        let raw = config
            .get(snapshot)
            .and_then(|entry| entry.get("collect_date"))
            .and_then(Value::as_str)
            .unwrap_or_default();
        let parsed = parse_date(raw);
        let date = NaiveDate::parse_from_str(&parsed, "%Y-%m-%d").ok();
        let Some(date) = date else {
            warnings.push(format!(
                "{snapshot}: collect_date missing; included without date filtering"
            ));
            return true;
        };
        request.date_range.contains(date)
    });
    if snapshots.is_empty() {
        warnings.push("no Hugging Face snapshots matched the requested date range".into());
    }
    if request.features.prydwen_visible
        || request.features.prydwen_tier
        || request.features.official_names
    {
        warnings.push("supplemental Prydwen/official sources are not yet connected to the generic export pipeline".into());
    }
    let bundle = match request.game {
        Game::Hsr => {
            let mut dataset = HsrExportDataset::default();
            for snapshot in snapshots {
                let snapshot_tree = match source.list_tree(&snapshot).await {
                    Ok(value) => value,
                    Err(error) => {
                        errors.push(format!("failed to list {snapshot}: {error}"));
                        Vec::new()
                    }
                };
                let snapshot_paths = snapshot_tree
                    .iter()
                    .map(|entry| entry.path.as_str())
                    .collect::<Vec<_>>();
                let mut mode_files = BTreeMap::new();
                for mode in &request.modes {
                    let chars_path = format!("{snapshot}/{mode}/chars");
                    let comps_path = format!("{snapshot}/{mode}/comps");
                    let chars =
                        list_optional_tree(source, &chars_path, &mut warnings, &mut errors).await;
                    let comps =
                        list_optional_tree(source, &comps_path, &mut warnings, &mut errors).await;
                    mode_files.insert(*mode, (chars, comps));
                }
                let builds_path = format!("{snapshot}/builds.json");
                let builds = if snapshot_paths.contains(&builds_path.as_str()) {
                    match source.read_json(&builds_path).await {
                        Ok(value) if value.is_array() => value,
                        Ok(_) => {
                            warnings.push(format!(
                                "{builds_path} was not a list; skipped as character usage source"
                            ));
                            Value::Array(vec![])
                        }
                        Err(error) => {
                            errors.push(error.to_string());
                            Value::Array(vec![])
                        }
                    }
                } else {
                    Value::Array(vec![])
                };
                let histograph_path = format!("{snapshot}/histograph.json");
                let histograph = if snapshot_paths.contains(&histograph_path.as_str()) {
                    match source.read_json(&histograph_path).await {
                        Ok(value) if value.is_array() => value,
                        Ok(_) => {
                            warnings.push(format!("{histograph_path} was not a list; skipped"));
                            Value::Array(vec![])
                        }
                        Err(error) => {
                            errors.push(error.to_string());
                            warnings.push(format!("{histograph_path} was not a list; skipped"));
                            Value::Array(vec![])
                        }
                    }
                } else {
                    Value::Array(vec![])
                };
                for mode in &request.modes {
                    let config_missing = config.get(&snapshot).is_none();
                    let mut entry = config
                        .get(&snapshot)
                        .cloned()
                        .unwrap_or_else(|| serde_json::json!({}));
                    prepare_hsr_dates(&mut entry, mode.code());
                    let (char_files, comp_files) = mode_files
                        .get(mode)
                        .expect("requested HSR mode files should be discovered");
                    let mut characters = parse_hsr_builds(&builds, mode.code());
                    for row in &mut characters {
                        row.source_file = builds_path.clone();
                        row.source_url = source.raw_url(&builds_path);
                    }
                    if characters.is_empty() {
                        for file in char_files
                            .iter()
                            .filter(|entry| entry.kind == "file" && entry.path.ends_with(".json"))
                        {
                            match source.read_json(&file.path).await {
                                Ok(value) => {
                                    let mut parsed = crate::hsr::parse_chars_file_character_rows(
                                        &value,
                                        mode.code(),
                                    );
                                    for row in &mut parsed {
                                        row.source_file = file.path.clone();
                                        row.source_url = source.raw_url(&file.path);
                                    }
                                    characters.extend(parsed);
                                }
                                Err(error) => errors.push(error.to_string()),
                            }
                        }
                    }
                    let histograph_rows =
                        parse_hsr_histograph(&histograph, mode.code(), &histograph_path);
                    if characters.is_empty() && !histograph_rows.is_empty() {
                        characters = histograph_fallback_character_rows(&histograph_rows);
                    }
                    let mut teams = vec![];
                    if request.features.hf_teams {
                        for file in comp_files
                            .iter()
                            .filter(|entry| entry.kind == "file" && entry.path.ends_with(".json"))
                        {
                            match source.read_json(&file.path).await {
                                Ok(value) => {
                                    let phase_ver = entry
                                        .pointer(&format!("/{mode}/ver"))
                                        .and_then(Value::as_str)
                                        .unwrap_or(&snapshot);
                                    let mut parsed = parse_hsr_teams(
                                        &value,
                                        mode.code(),
                                        phase_ver,
                                        &file.path,
                                        None,
                                    );
                                    for row in &mut parsed {
                                        row.source_kind = "hf_comps".into();
                                        row.source_file = file.path.clone();
                                        row.source_url = source.raw_url(&file.path);
                                    }
                                    teams.extend(parsed);
                                }
                                Err(error) => errors.push(error.to_string()),
                            }
                        }
                    }
                    let collect_date = entry
                        .get("collect_date")
                        .and_then(Value::as_str)
                        .map(parse_date)
                        .unwrap_or_default();
                    let mut phase = make_hsr_phase(
                        &snapshot,
                        &entry,
                        mode.code(),
                        &format!("{snapshot}/"),
                        !char_files.is_empty(),
                        !comp_files.is_empty(),
                        snapshot_paths.contains(&histograph_path.as_str()),
                        &collect_date,
                    );
                    if config_missing {
                        phase.note = "config missing; dates unavailable".into();
                    }
                    dataset.histograph_slices.push(HsrHistographSlice {
                        phase: phase.clone(),
                        rows: histograph_rows,
                    });
                    dataset.slices.push(HsrExportSlice {
                        phase,
                        characters,
                        teams,
                        tiers: vec![],
                    });
                }
            }
            build_hsr_dataset(&dataset)?
        }
        Game::Zzz => {
            let mut dataset = ZzzExportDataset::default();
            for snapshot in snapshots {
                let snapshot_tree = match source.list_tree(&snapshot).await {
                    Ok(value) => value,
                    Err(error) => {
                        errors.push(format!("failed to list {snapshot}: {error}"));
                        Vec::new()
                    }
                };
                let paths = snapshot_tree
                    .iter()
                    .map(|entry| entry.path.as_str())
                    .collect::<Vec<_>>();
                let builds_path = format!("{snapshot}/builds.json");
                let builds = if paths.contains(&builds_path.as_str()) {
                    match source.read_json(&builds_path).await {
                        Ok(value) if value.is_array() => value,
                        Ok(_) => {
                            warnings.push(format!("{builds_path} was not a list; skipped"));
                            Value::Array(vec![])
                        }
                        Err(error) => {
                            errors.push(error.to_string());
                            Value::Array(vec![])
                        }
                    }
                } else {
                    Value::Array(vec![])
                };
                for mode in &request.modes {
                    let chars_tree = format!("{snapshot}/{mode}/chars");
                    let comps_tree = format!("{snapshot}/{mode}/comps");
                    let char_files =
                        list_optional_tree(source, &chars_tree, &mut warnings, &mut errors).await;
                    let comp_files =
                        list_optional_tree(source, &comps_tree, &mut warnings, &mut errors).await;
                    let config_missing = config.get(&snapshot).is_none();
                    let entry = config.get(&snapshot).cloned().unwrap_or_else(
                        || serde_json::json!({"collect_date":"", (mode.code()):{"ver":snapshot}}),
                    );
                    let Some(mode_config) = entry.get(mode.code()).and_then(Value::as_object)
                    else {
                        warnings.push(format!("{snapshot}/{mode}: mode config missing; skipped"));
                        continue;
                    };
                    let mut phase = make_zzz_phase(PhaseInput {
                        snapshot_id: snapshot.clone(),
                        mode: mode.code().into(),
                        collect_date: entry
                            .get("collect_date")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .into(),
                        ver: mode_config
                            .get("ver")
                            .and_then(Value::as_str)
                            .unwrap_or(&snapshot)
                            .into(),
                        name: mode_config
                            .get("name")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .into(),
                        start: mode_config
                            .get("start")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .into(),
                        end: mode_config
                            .get("end")
                            .and_then(Value::as_str)
                            .unwrap_or_default()
                            .into(),
                        source_path: format!("{snapshot}/"),
                    });
                    phase.has_chars =
                        (paths.contains(&builds_path.as_str()) || !char_files.is_empty()) as i32;
                    phase.has_comps = (!comp_files.is_empty()) as i32;
                    if config_missing {
                        phase.note = "config missing; dates unavailable".into();
                    }
                    let mut usage = vec![];
                    for value in builds.as_array().into_iter().flatten() {
                        let mut parsed = parse_usage(value, mode.code());
                        for row in &mut parsed {
                            row.source_file = builds_path.clone();
                            row.source_url = source.raw_url(&builds_path);
                        }
                        usage.extend(parsed);
                    }
                    for file in char_files.iter().filter(|entry| {
                        entry.kind == "file" && entry.path.ends_with("bangboo_all.json")
                    }) {
                        match source.read_json(&file.path).await {
                            Ok(value) if value.is_array() => usage.extend(parse_zzz_bangboo(
                                value.as_array().expect("array checked above"),
                                &file.path,
                                &source.raw_url(&file.path),
                            )),
                            Ok(_) => {}
                            Err(error) => errors.push(error.to_string()),
                        }
                    }
                    let mut teams = vec![];
                    if request.features.hf_teams {
                        for file in comp_files
                            .iter()
                            .filter(|entry| entry.kind == "file" && entry.path.ends_with(".json"))
                        {
                            match source.read_json(&file.path).await {
                                Ok(value) if value.is_array() => {
                                    let mut parsed = parse_zzz_teams(
                                        value.as_array().unwrap().clone(),
                                        mode.code(),
                                        Path::new(&file.path)
                                            .file_name()
                                            .and_then(|v| v.to_str())
                                            .unwrap_or_default(),
                                    );
                                    for row in &mut parsed {
                                        row.source_file = file.path.clone();
                                        row.source_url = source.raw_url(&file.path);
                                    }
                                    teams.extend(parsed);
                                }
                                Ok(_) => {}
                                Err(error) => errors.push(error.to_string()),
                            }
                        }
                    }
                    dataset.slices.push(ZzzExportSlice {
                        phase,
                        names: fallback_name_rows(&usage, &teams),
                        usage,
                        teams,
                    });
                }
            }
            build_zzz_dataset(&dataset)?
        }
    };
    Ok(PipelineRun {
        bundle,
        warnings,
        errors,
    })
}

pub async fn run_export_v1<S: SnapshotSource>(
    source: &S,
    request: &ExportRequest,
    context: &ExportContext,
) -> Result<ExportOutcome> {
    let PipelineRun {
        mut bundle,
        warnings,
        errors,
    } = run_source_export(source, request).await?;
    let mut diagnostics = warnings
        .into_iter()
        .map(|message| diagnostic_from_message(request.game, DiagnosticSeverity::Warning, message))
        .collect::<Vec<_>>();
    diagnostics.extend(errors.into_iter().map(|message| {
        diagnostic_from_message(request.game, DiagnosticSeverity::RecoverableError, message)
    }));
    let stats = finalize_export_bundle(&mut bundle, request, context, &diagnostics)?;
    Ok(ExportOutcome {
        request: request.clone(),
        bundle,
        diagnostics,
        stats,
    })
}

fn diagnostic_from_message(
    game: Game,
    severity: DiagnosticSeverity,
    message: String,
) -> Diagnostic {
    let code = if message.contains("supplemental Prydwen/official sources") {
        diagnostic_code::SUPPLEMENTAL_NOT_CONNECTED
    } else if message.contains("collect_date missing") {
        diagnostic_code::SNAPSHOT_DATE_MISSING
    } else if message == "no Hugging Face snapshots matched the requested date range" {
        diagnostic_code::NO_MATCHING_SNAPSHOTS
    } else if severity == DiagnosticSeverity::Warning {
        diagnostic_code::PIPELINE_WARNING
    } else {
        diagnostic_code::PIPELINE_RECOVERABLE
    };
    Diagnostic {
        severity,
        code: code.into(),
        source: DiagnosticSource::Pipeline,
        game,
        snapshot: None,
        mode: None,
        path: None,
        message,
    }
}

async fn list_optional_tree<S: SnapshotSource>(
    source: &S,
    path: &str,
    warnings: &mut Vec<String>,
    errors: &mut Vec<String>,
) -> Vec<TreeEntry> {
    match source.list_tree(path).await {
        Ok(files) => files,
        Err(error) => {
            record_optional_tree_error(path, error, warnings, errors);
            Vec::new()
        }
    }
}

fn record_optional_tree_error(
    path: &str,
    error: MihoError,
    warnings: &mut Vec<String>,
    errors: &mut Vec<String>,
) {
    let is_not_found = matches!(
        &error,
        MihoError::Network(source)
            if source.status().is_some_and(|status| status.as_u16() == 404)
    );
    let message = format!("optional tree {path} unavailable: {error}");
    if is_not_found {
        warnings.push(message);
    } else {
        errors.push(message);
    }
}

fn prepare_hsr_dates(entry: &mut Value, mode: &str) {
    if let Some(config) = entry.get_mut(mode).and_then(Value::as_object_mut) {
        for (source, target) in [("start", "start_iso"), ("end", "end_iso")] {
            let value = config
                .get(source)
                .and_then(Value::as_str)
                .map(parse_date)
                .unwrap_or_default();
            config.insert(target.into(), Value::String(value));
        }
    }
}

fn is_version(value: &str) -> bool {
    let parts = value.split('.').collect::<Vec<_>>();
    parts.len() == 3
        && parts
            .iter()
            .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        contract::{
            DatasetRef, DateRange, FeatureFlags, FetchPolicy, GameMode, HistoryPolicy,
            WorkbookPolicy, EXPORT_REQUEST_SCHEMA_VERSION,
        },
        hf::HuggingFaceRepo,
        network::{FetchMode, HttpClient},
        source::HfSnapshotSource,
    };
    use chrono::{TimeZone, Utc};
    use std::{
        collections::BTreeSet,
        fs,
        io::{Read, Write},
        net::TcpListener,
        sync::Mutex,
        thread,
        time::Duration,
    };

    #[derive(Default)]
    struct MemorySource {
        trees: BTreeMap<String, Vec<TreeEntry>>,
        json: BTreeMap<String, Value>,
        list_failures: BTreeSet<String>,
        json_failures: BTreeSet<String>,
        listed: Mutex<Vec<String>>,
        read: Mutex<Vec<String>>,
    }

    impl SnapshotSource for MemorySource {
        fn list_tree<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Vec<TreeEntry>> {
            Box::pin(async move {
                self.listed.lock().unwrap().push(path.to_owned());
                if self.list_failures.contains(path) {
                    Err(MihoError::Unsupported(format!(
                        "memory list failure for {path}"
                    )))
                } else {
                    Ok(self.trees.get(path).cloned().unwrap_or_default())
                }
            })
        }

        fn read_json<'a>(&'a self, path: &'a str) -> SourceFuture<'a, Value> {
            Box::pin(async move {
                self.read.lock().unwrap().push(path.to_owned());
                if self.json_failures.contains(path) {
                    Err(MihoError::Unsupported(format!(
                        "memory download failure for {path}"
                    )))
                } else {
                    self.json.get(path).cloned().ok_or_else(|| {
                        MihoError::Unsupported(format!("memory JSON missing for {path}"))
                    })
                }
            })
        }

        fn raw_url(&self, path: &str) -> String {
            format!("memory://fixture/{path}")
        }
    }

    fn tree_entry(path: &str, kind: &str) -> TreeEntry {
        TreeEntry {
            path: path.into(),
            kind: kind.into(),
            extra: Default::default(),
        }
    }

    fn hsr_request() -> ExportRequest {
        ExportRequest {
            schema_version: EXPORT_REQUEST_SCHEMA_VERSION,
            game: Game::Hsr,
            modes: vec![GameMode::HsrMoc],
            date_range: DateRange {
                from: None,
                to: None,
            },
            dataset: DatasetRef {
                repo_id: "owner/repo".into(),
                revision: "main".into(),
            },
            features: FeatureFlags {
                hf_teams: false,
                prydwen_visible: false,
                prydwen_tier: false,
                official_names: false,
            },
            prydwen_top_n: 100,
            name_map_seed: None,
            history: HistoryPolicy::MergeExisting,
            workbook: WorkbookPolicy::Disabled,
        }
    }

    fn csv_table(bundle: &ArtifactBundle, path: &str) -> (Vec<String>, Vec<Vec<String>>) {
        let bytes = bundle.get(path).expect("CSV artifact should exist");
        let mut reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_reader(&bytes[3..]);
        let headers = reader
            .headers()
            .unwrap()
            .iter()
            .map(str::to_owned)
            .collect();
        let rows = reader
            .records()
            .map(|record| record.unwrap().iter().map(str::to_owned).collect())
            .collect();
        (headers, rows)
    }

    fn field<'a>(headers: &[String], row: &'a [String], name: &str) -> &'a str {
        row[headers.iter().position(|header| header == name).unwrap()].as_str()
    }

    fn fixture(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures")
            .join(name)
    }

    #[test]
    fn discovers_and_runs_hsr_fixture() {
        let fixture = OfflineFixture::load(fixture("offline_hsr")).unwrap();
        assert_eq!(fixture.snapshots(), ["4.3.2"]);
        let run = fixture.run_hsr("4.3.2", "moc").unwrap();
        assert!(run.errors.is_empty());
        assert!(run.bundle.get("phase_index.csv").is_some());
        assert!(run.bundle.get("team_rank_raw.csv").is_some());
        assert!(fixture.run_hsr("9.9.9", "moc").is_err());
        assert!(matches!(
            fixture.read_json("../escape.json"),
            Err(MihoError::InvalidCacheKey(_))
        ));
    }

    #[test]
    fn discovers_and_runs_zzz_fixture() {
        let fixture = OfflineFixture::load(fixture("offline_zzz")).unwrap();
        assert_eq!(fixture.snapshots(), ["3.0.1"]);
        let run = fixture.run_zzz("3.0.1", "sd").unwrap();
        assert!(run.errors.is_empty());
        assert!(run.bundle.get("character_usage_long.csv").is_some());
        assert!(run.bundle.get("team_rank_raw.csv").is_some());
    }

    #[tokio::test]
    async fn generic_source_pipeline_builds_hsr_and_zzz_bundles() {
        let hsr = OfflineFixture::load(fixture("offline_hsr")).unwrap();
        let hsr_run = run_source_export(
            &hsr,
            &ExportRequest {
                dataset: DatasetRef {
                    repo_id: hsr.manifest.repo_id.clone(),
                    revision: hsr.manifest.revision.clone(),
                },
                features: FeatureFlags {
                    hf_teams: true,
                    ..hsr_request().features
                },
                ..hsr_request()
            },
        )
        .await
        .unwrap();
        let hsr_usage =
            std::str::from_utf8(hsr_run.bundle.get("character_usage_long.csv").unwrap()).unwrap();
        assert!(hsr_usage.contains("offline://LvlUrArti/MocDataProcessed/main/4.3.2/builds.json"));

        let zzz = OfflineFixture::load(fixture("offline_zzz")).unwrap();
        let zzz_run = run_source_export(
            &zzz,
            &ExportRequest {
                game: Game::Zzz,
                modes: vec![GameMode::ZzzSd],
                dataset: DatasetRef {
                    repo_id: zzz.manifest.repo_id.clone(),
                    revision: zzz.manifest.revision.clone(),
                },
                features: FeatureFlags {
                    hf_teams: true,
                    ..hsr_request().features
                },
                ..hsr_request()
            },
        )
        .await
        .unwrap();
        let zzz_teams =
            std::str::from_utf8(zzz_run.bundle.get("team_rank_raw.csv").unwrap()).unwrap();
        assert!(
            zzz_teams.contains(
                "offline://LvlUrArti/ShiyuDataProcessed/main/3.0.1/sd/comps/5-1_combined.json"
            ),
            "{zzz_teams}"
        );
    }

    #[tokio::test]
    async fn versioned_export_returns_structured_receipt_and_final_report() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source.json.insert(
            "config.json".into(),
            serde_json::json!({
                "1.0.0": {"collect_date": "2026-01-01", "moc": {"ver": "1"}}
            }),
        );
        let mut request = hsr_request();
        request.date_range = DateRange {
            from: NaiveDate::from_ymd_opt(2026, 1, 1),
            to: NaiveDate::from_ymd_opt(2026, 1, 31),
        };
        let context = ExportContext {
            fetched_at: Utc.with_ymd_and_hms(2026, 7, 12, 1, 2, 3).unwrap(),
            fetch_policy: FetchPolicy::Fixture,
            cache_root: "cache".into(),
            existing_output_root: None,
        };

        let outcome = run_export_v1(&source, &request, &context).await.unwrap();
        assert_eq!(outcome.stats.snapshots, 1);
        assert_eq!(outcome.stats.phases_by_mode[&GameMode::HsrMoc], 1);
        let report = std::str::from_utf8(outcome.bundle.get("export_report.md").unwrap()).unwrap();
        assert!(report.contains("2026-01-01 / 2026-01-31"));
        assert!(report.contains("2026-07-12T01:02:03Z"));
        let receipt = outcome.receipt();
        assert_eq!(receipt.game, Game::Hsr);
        assert!(receipt
            .artifacts
            .iter()
            .any(|artifact| artifact.path == "artifact_manifest.json"));
    }

    #[tokio::test]
    async fn versioned_request_rejects_a_mismatched_snapshot_source() {
        let fixture = OfflineFixture::load(fixture("offline_hsr")).unwrap();
        let error = run_source_export(&fixture, &hsr_request())
            .await
            .err()
            .expect("dataset identity mismatch should fail before reading the source");
        assert!(error.to_string().contains("does not match request"));
    }

    #[tokio::test]
    async fn generic_pipeline_filters_closed_dates_but_keeps_unknown_dates() {
        let mut source = MemorySource::default();
        source.trees.insert(
            String::new(),
            ["1.0.0", "2.0.0", "3.0.0"]
                .into_iter()
                .map(|path| tree_entry(path, "directory"))
                .collect(),
        );
        source.json.insert(
            "config.json".into(),
            serde_json::json!({
                "1.0.0": {"collect_date": "2026-01-01", "moc": {"ver": "1"}},
                "2.0.0": {"collect_date": "2026-01-31", "moc": {"ver": "2"}},
                "3.0.0": {"collect_date": "not-a-date", "moc": {"ver": "3"}}
            }),
        );
        let mut request = hsr_request();
        request.date_range.from = NaiveDate::from_ymd_opt(2026, 1, 10);
        request.date_range.to = NaiveDate::from_ymd_opt(2026, 1, 31);

        let run = run_source_export(&source, &request).await.unwrap();
        let phases = std::str::from_utf8(run.bundle.get("phase_index.csv").unwrap()).unwrap();
        assert!(!phases.contains("1.0.0"));
        assert!(phases.contains("2.0.0") && phases.contains("3.0.0"));
        assert!(run.warnings.iter().any(|warning| {
            warning == "3.0.0: collect_date missing; included without date filtering"
        }));
        let listed = source.listed.lock().unwrap();
        assert!(!listed.iter().any(|path| path == "1.0.0"));
        assert!(listed.iter().any(|path| path.ends_with("/comps")));
    }

    #[tokio::test]
    async fn generic_pipeline_writes_fixed_empty_bundle_when_range_matches_nothing() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source.json.insert(
            "config.json".into(),
            serde_json::json!({
                "1.0.0": {"collect_date": "2026-01-01", "moc": {"ver": "1"}}
            }),
        );
        let mut request = hsr_request();
        request.date_range.from = NaiveDate::from_ymd_opt(2026, 2, 1);
        request.date_range.to = NaiveDate::from_ymd_opt(2026, 2, 28);

        let run = run_source_export(&source, &request).await.unwrap();
        assert!(run.warnings.iter().any(|warning| {
            warning == "no Hugging Face snapshots matched the requested date range"
        }));
        let phases = std::str::from_utf8(run.bundle.get("phase_index.csv").unwrap()).unwrap();
        assert_eq!(phases.lines().count(), 1);
        assert!(run.bundle.get("character_usage_long.csv").is_some());
        assert!(run.bundle.get("team_rank_raw.csv").is_some());
    }

    #[tokio::test]
    async fn generic_pipeline_keeps_partial_snapshot_and_recoverable_errors() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source.list_failures.insert("1.0.0".into());
        source.json_failures.insert("config.json".into());

        let run = run_source_export(&source, &hsr_request()).await.unwrap();
        let phases = std::str::from_utf8(run.bundle.get("phase_index.csv").unwrap()).unwrap();
        assert!(phases.contains("1.0.0"));
        assert!(run
            .errors
            .iter()
            .any(|error| error.contains("failed to load config.json")));
        assert!(run
            .errors
            .iter()
            .any(|error| error.contains("failed to list 1.0.0")));
        assert!(run.warnings.iter().any(|warning| {
            warning == "1.0.0: collect_date missing; included without date filtering"
        }));
    }

    #[tokio::test]
    async fn generic_pipeline_normalizes_missing_root_to_version_error() {
        for source in [
            MemorySource::default(),
            MemorySource {
                list_failures: BTreeSet::from([String::new()]),
                ..Default::default()
            },
        ] {
            let error = run_source_export(&source, &hsr_request())
                .await
                .err()
                .expect("missing version directories must fail");
            assert!(error
                .to_string()
                .contains("no version directories found in Hugging Face dataset root"));
        }
    }

    #[tokio::test]
    async fn hsr_phase_flags_describe_trees_even_when_team_download_is_disabled() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source.trees.insert(
            "1.0.0".into(),
            vec![tree_entry("1.0.0/builds.json", "file")],
        );
        source.trees.insert(
            "1.0.0/moc/comps".into(),
            vec![tree_entry("1.0.0/moc/comps/top.json", "file")],
        );
        source.json.insert(
            "config.json".into(),
            serde_json::json!({
                "1.0.0": {"collect_date": "2026-01-01", "moc": {"ver": "1"}}
            }),
        );
        source.json.insert(
            "1.0.0/builds.json".into(),
            serde_json::json!([{"char": "A", "app_rate_moc": 12.5}]),
        );

        let run = run_source_export(&source, &hsr_request()).await.unwrap();
        assert!(run.errors.is_empty(), "{:?}", run.errors);
        let (headers, rows) = csv_table(&run.bundle, "phase_index.csv");
        assert_eq!(rows.len(), 1);
        assert_eq!(field(&headers, &rows[0], "has_chars"), "0");
        assert_eq!(field(&headers, &rows[0], "has_comps"), "1");
        assert_eq!(csv_table(&run.bundle, "team_rank_raw.csv").1.len(), 0);
        assert!(!source
            .read
            .lock()
            .unwrap()
            .iter()
            .any(|path| path.ends_with("top.json")));
    }

    #[tokio::test]
    async fn hsr_missing_config_sets_phase_note_and_histograph_supplies_fallback() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source.trees.insert(
            "1.0.0".into(),
            vec![tree_entry("1.0.0/histograph.json", "file")],
        );
        source
            .json
            .insert("config.json".into(), serde_json::json!({}));
        source.json.insert(
            "1.0.0/histograph.json".into(),
            serde_json::json!([{"char": "Topaz & Numby", "moc_usage": "8.25%"}]),
        );

        let run = run_source_export(&source, &hsr_request()).await.unwrap();
        let (phase_headers, phases) = csv_table(&run.bundle, "phase_index.csv");
        assert_eq!(
            field(&phase_headers, &phases[0], "note"),
            "config missing; dates unavailable"
        );
        assert_eq!(
            run.warnings
                .iter()
                .filter(|warning| warning.contains("1.0.0"))
                .count(),
            1
        );
        let (_, histograph) = csv_table(&run.bundle, "histograph_usage_long.csv");
        assert_eq!(histograph.len(), 1);
        let (usage_headers, usage) = csv_table(&run.bundle, "character_usage_long.csv");
        assert_eq!(usage.len(), 1);
        assert_eq!(
            field(&usage_headers, &usage[0], "source_kind"),
            "hf_histograph_fallback"
        );
        assert_eq!(
            field(&usage_headers, &usage[0], "source_file"),
            "1.0.0/histograph.json"
        );
    }

    #[tokio::test]
    async fn zzz_pipeline_combines_builds_and_bangboo_and_preserves_phase_flags() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source.trees.insert(
            "1.0.0".into(),
            vec![tree_entry("1.0.0/builds.json", "file")],
        );
        source.trees.insert(
            "1.0.0/sd/chars".into(),
            vec![tree_entry("1.0.0/sd/chars/bangboo_all.json", "file")],
        );
        source.trees.insert(
            "1.0.0/sd/comps".into(),
            vec![tree_entry("1.0.0/sd/comps/5-1.json", "file")],
        );
        source.json.insert(
            "config.json".into(),
            serde_json::json!({
                "1.0.0": {"collect_date": "2026-01-01", "sd": {"ver": "1"}}
            }),
        );
        source.json.insert(
            "1.0.0/builds.json".into(),
            serde_json::json!([{"char": "A", "app_rate_sd": 10}]),
        );
        source.json.insert(
            "1.0.0/sd/chars/bangboo_all.json".into(),
            serde_json::json!([{"char": "Butler", "app_rate": 5, "avg_round": 2}]),
        );
        let mut request = hsr_request();
        request.game = Game::Zzz;
        request.modes = vec![GameMode::ZzzSd];

        let run = run_source_export(&source, &request).await.unwrap();
        assert!(run.errors.is_empty(), "{:?}", run.errors);
        let (phase_headers, phases) = csv_table(&run.bundle, "phase_index.csv");
        assert_eq!(field(&phase_headers, &phases[0], "has_chars"), "1");
        assert_eq!(field(&phase_headers, &phases[0], "has_comps"), "1");
        let (usage_headers, usage) = csv_table(&run.bundle, "character_usage_long.csv");
        assert_eq!(usage.len(), 2);
        assert!(usage.iter().any(|row| {
            field(&usage_headers, row, "source_kind") == "hf_bangboo"
                && field(&usage_headers, row, "source_file") == "1.0.0/sd/chars/bangboo_all.json"
        }));
        let (name_headers, names) = csv_table(&run.bundle, "name_map.csv");
        assert_eq!(names.len(), 2);
        assert!(names.iter().all(|row| {
            field(&name_headers, row, "needs_manual_check") == "1"
                && field(&name_headers, row, "kind") == "unknown"
        }));
        assert_eq!(csv_table(&run.bundle, "team_rank_raw.csv").1.len(), 0);
        assert!(!source
            .read
            .lock()
            .unwrap()
            .iter()
            .any(|path| path.ends_with("5-1.json")));
    }

    #[tokio::test]
    async fn zzz_missing_config_keeps_phase_with_compatibility_note() {
        let mut source = MemorySource::default();
        source
            .trees
            .insert(String::new(), vec![tree_entry("1.0.0", "directory")]);
        source
            .json
            .insert("config.json".into(), serde_json::json!({}));
        let mut request = hsr_request();
        request.game = Game::Zzz;
        request.modes = vec![GameMode::ZzzSd];

        let run = run_source_export(&source, &request).await.unwrap();
        let (headers, rows) = csv_table(&run.bundle, "phase_index.csv");
        assert_eq!(rows.len(), 1);
        assert_eq!(
            field(&headers, &rows[0], "note"),
            "config missing; dates unavailable"
        );
    }

    #[tokio::test]
    async fn generic_pipeline_matches_online_http_and_offline_cache() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let origin = format!("http://{}", listener.local_addr().unwrap());
        let responses = BTreeMap::from([
            (
                "/api/datasets/owner/repo/tree/main".to_owned(),
                r#"[{"type":"directory","path":"1.0.0"}]"#.to_owned(),
            ),
            (
                "/datasets/owner/repo/resolve/main/config.json".to_owned(),
                r#"{"1.0.0":{"collect_date":"2026-01-01","moc":{"ver":"1"}}}"#.to_owned(),
            ),
            (
                "/api/datasets/owner/repo/tree/main/1.0.0".to_owned(),
                r#"[{"type":"file","path":"1.0.0/builds.json"}]"#.to_owned(),
            ),
            (
                "/api/datasets/owner/repo/tree/main/1.0.0/moc/chars".to_owned(),
                "[]".to_owned(),
            ),
            (
                "/api/datasets/owner/repo/tree/main/1.0.0/moc/comps".to_owned(),
                r#"[{"type":"file","path":"1.0.0/moc/comps/top.json"}]"#.to_owned(),
            ),
            (
                "/datasets/owner/repo/resolve/main/1.0.0/builds.json".to_owned(),
                r#"[{"char":"A","app_rate_moc":10}]"#.to_owned(),
            ),
            (
                "/datasets/owner/repo/resolve/main/1.0.0/moc/comps/top.json".to_owned(),
                r#"[{"char_one":"a","char_two":"b","char_three":"c","char_four":"d","rank":1}]"#
                    .to_owned(),
            ),
        ]);
        let response_count = responses.len();
        let server = thread::spawn(move || {
            for _ in 0..response_count {
                let (mut stream, _) = listener.accept().unwrap();
                let mut request = [0_u8; 4096];
                let size = stream.read(&mut request).unwrap();
                let request = String::from_utf8_lossy(&request[..size]);
                let target = request
                    .lines()
                    .next()
                    .and_then(|line| line.split_whitespace().nth(1))
                    .unwrap()
                    .split('?')
                    .next()
                    .unwrap();
                let (status, body) = responses
                    .get(target)
                    .map(|body| ("200 OK", body.as_str()))
                    .unwrap_or(("404 Not Found", "missing fixture response"));
                write!(
                    stream,
                    "HTTP/1.1 {status}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .unwrap();
            }
        });
        let cache =
            std::env::temp_dir().join(format!("miho-pipeline-http-cache-{}", std::process::id()));
        let _ = fs::remove_dir_all(&cache);
        let repo = HuggingFaceRepo::new("owner/repo", "main").with_origin(origin);
        let online_source = HfSnapshotSource::new(
            repo.clone(),
            HttpClient::new(Duration::from_secs(2), 0).unwrap(),
            &cache,
            FetchMode::Online,
        );
        let mut request = hsr_request();
        request.features.hf_teams = true;
        let online = run_source_export(&online_source, &request).await.unwrap();
        server.join().unwrap();
        assert!(online.errors.is_empty(), "{:?}", online.errors);

        let offline_source = HfSnapshotSource::new(
            repo,
            HttpClient::new(Duration::from_millis(50), 0).unwrap(),
            &cache,
            FetchMode::Offline,
        );
        let offline = run_source_export(&offline_source, &request).await.unwrap();
        assert_eq!(online.warnings, offline.warnings);
        assert_eq!(online.errors, offline.errors);
        assert_eq!(online.bundle.manifest(), offline.bundle.manifest());
        for artifact in online.bundle.manifest() {
            assert_eq!(
                online.bundle.get(&artifact.path),
                offline.bundle.get(&artifact.path),
                "online/offline mismatch: {}",
                artifact.path
            );
        }
        let _ = fs::remove_dir_all(cache);
    }
}
