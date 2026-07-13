//! Trusted application executor for dataset exports and visualizer rebuilds.
//!
//! Frontends translate their arguments and environment into typed requests,
//! capture exactly one [`ExportInvocation`], and delegate all source,
//! enrichment, visualization, manifest, and transactional installation work
//! to this module.

use std::{
    collections::BTreeSet,
    ffi::OsStr,
    fs,
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::Duration as StdDuration,
};

use anyhow::{bail, Context};
use chrono::{DateTime, FixedOffset, Local, NaiveDate, NaiveDateTime, Utc};
use miho_core::{
    contract::{
        DatasetRef, DateRange, Diagnostic, ExportContext, FeatureFlags, FetchPolicy, GameMode,
        HistoryPolicy, WorkbookPolicy, EXPORT_REQUEST_SCHEMA_VERSION,
    },
    hf::HuggingFaceRepo,
    hsr_supplemental::{HsrFixtureSupplementalSource, HsrHttpSupplementalSource},
    hsr_visualizer::attach_hsr_visualizer,
    network::{FetchMode, HttpClient},
    pipeline::{run_hsr_export_v1, run_zzz_export_v1, ExportRequest, Game, OfflineFixture},
    source::{HfCacheFallbackPolicy, HfSnapshotSource},
    visualizer::{attach_visualizer_hub, validate_json_surrogate_escapes, VisualizerContext},
    zzz_enrichment::first_valid_phase_override_path,
    zzz_supplemental::{ZzzFixtureSupplementalSource, ZzzHttpSupplementalSource},
    zzz_visualizer::attach_zzz_visualizer,
    MihoError,
};
use sha2::{Digest, Sha256};

use crate::AppInvocation;

/// One wall-clock observation shared by source metadata, default ranges, and
/// every generated visualizer timestamp in one frontend invocation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportInvocation {
    cwd: PathBuf,
    observed_at: DateTime<FixedOffset>,
}

impl ExportInvocation {
    /// Capture the process directory and wall clock exactly once.
    pub fn capture() -> anyhow::Result<Self> {
        let cwd = std::env::current_dir().context("cannot capture export working directory")?;
        let observed_at = Local::now().fixed_offset();
        Self::new(cwd, observed_at)
    }

    /// Construct an invocation from an explicitly supplied instant and local
    /// offset. Runners can reuse this same value for report tasks through
    /// [`Self::app_invocation`].
    pub fn new(cwd: PathBuf, observed_at: DateTime<FixedOffset>) -> anyhow::Result<Self> {
        Ok(Self {
            cwd: lexical_absolute(&cwd)?,
            observed_at,
        })
    }

    pub fn cwd(&self) -> &Path {
        &self.cwd
    }

    pub fn observed_at(&self) -> DateTime<FixedOffset> {
        self.observed_at
    }

    pub fn fetched_at(&self) -> DateTime<Utc> {
        self.observed_at.with_timezone(&Utc)
    }

    pub fn local_datetime(&self) -> NaiveDateTime {
        self.observed_at.naive_local()
    }

    pub fn local_date(&self) -> NaiveDate {
        self.observed_at.date_naive()
    }

    pub fn resolve(&self, path: &Path) -> PathBuf {
        lexical_normalize(if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.cwd.join(path)
        })
    }

    pub fn app_invocation(&self) -> anyhow::Result<AppInvocation> {
        AppInvocation::new(self.cwd.clone(), self.local_datetime())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExportSourceV1 {
    Online {
        cache_root: PathBuf,
    },
    /// Online source for freshness-sensitive orchestration. Every Hugging Face
    /// tree/raw request must receive and validate a network response; a
    /// last-good cache fallback is a structured export failure.
    OnlineHfFreshnessRequired {
        cache_root: PathBuf,
        /// Trusted test/mirror seam. Production update config does not expose
        /// an origin and therefore retains the official Hugging Face endpoint.
        hf_origin: Option<String>,
    },
    Fixture {
        root: PathBuf,
        supplemental_root: Option<PathBuf>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportTaskV1 {
    pub game: Game,
    pub modes: Vec<GameMode>,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
    pub output_root: PathBuf,
    pub repo_id: String,
    pub revision: String,
    pub features: FeatureFlags,
    pub prydwen_top_n: usize,
    pub name_map_seed: Option<PathBuf>,
    pub source: ExportSourceV1,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExportReceiptV1 {
    pub game: Game,
    pub output_root: PathBuf,
    pub fixture_root: Option<PathBuf>,
    pub diagnostics: Vec<Diagnostic>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VisualizerTaskV1 {
    pub game: Game,
    pub output_root: PathBuf,
}

pub trait ExportObserver: Send + Sync {
    fn fixture_mode(&self, _path: &Path) {}
    fn diagnostic(&self, _diagnostic: &Diagnostic) {}
}

struct DirectExportObserver;

impl ExportObserver for DirectExportObserver {}

/// Execute a complete export and atomically install its output. A successful
/// receipt means the game output (and, for ZZZ, its sibling Hub) was installed.
pub async fn execute_export_v1(
    task: &ExportTaskV1,
    invocation: &ExportInvocation,
) -> anyhow::Result<ExportReceiptV1> {
    execute_export_observed_with_hub_v1(task, invocation, &DirectExportObserver, "out").await
}

/// Execute an export with the actual workspace HSR directory encoded into the
/// sibling Hub. Native update configs may use a safe top-level name other than
/// the legacy `out`; direct CLI compatibility continues to use that default.
pub async fn execute_export_with_hub_v1(
    task: &ExportTaskV1,
    invocation: &ExportInvocation,
    hsr_output_directory: &str,
) -> anyhow::Result<ExportReceiptV1> {
    execute_export_observed_with_hub_v1(
        task,
        invocation,
        &DirectExportObserver,
        hsr_output_directory,
    )
    .await
}

/// Execute an export while exposing the same progress points historically
/// rendered by the CLI. Observers cannot alter application behavior.
pub async fn execute_export_observed_v1(
    task: &ExportTaskV1,
    invocation: &ExportInvocation,
    observer: &dyn ExportObserver,
) -> anyhow::Result<ExportReceiptV1> {
    execute_export_observed_with_hub_v1(task, invocation, observer, "out").await
}

async fn execute_export_observed_with_hub_v1(
    task: &ExportTaskV1,
    invocation: &ExportInvocation,
    observer: &dyn ExportObserver,
    hsr_output_directory: &str,
) -> anyhow::Result<ExportReceiptV1> {
    let output_root = invocation.resolve(&task.output_root);
    if task.game == Game::Zzz {
        validate_zzz_hub_preflight(&output_root, hsr_output_directory)?;
    }
    let request = ExportRequest {
        schema_version: EXPORT_REQUEST_SCHEMA_VERSION,
        game: task.game,
        modes: task.modes.clone(),
        date_range: DateRange {
            from: Some(task.from_date),
            to: Some(task.to_date),
        },
        dataset: DatasetRef {
            repo_id: task.repo_id.clone(),
            revision: task.revision.clone(),
        },
        features: task.features.clone(),
        prydwen_top_n: task.prydwen_top_n,
        name_map_seed: task
            .name_map_seed
            .as_deref()
            .map(|path| invocation.resolve(path)),
        history: HistoryPolicy::MergeExisting,
        workbook: WorkbookPolicy::BestEffort,
    };

    let (mut run, fixture_root) = match &task.source {
        ExportSourceV1::Fixture {
            root,
            supplemental_root,
        } => {
            let fixture_root = invocation.resolve(root);
            let fixture = OfflineFixture::load(&fixture_root)?;
            if fixture.manifest.game != task.game {
                bail!("offline fixture game does not match requested game");
            }
            let context = export_context(
                task.game,
                invocation,
                FetchPolicy::Fixture,
                fixture_root.clone(),
                output_root.clone(),
            );
            let supplemental_root = supplemental_root
                .as_deref()
                .map(|path| invocation.resolve(path))
                .unwrap_or_else(|| fixture_root.join("supplemental"));
            let run = match task.game {
                Game::Hsr => {
                    let supplemental =
                        HsrFixtureSupplementalSource::new(supplemental_root, context.fetched_at);
                    run_hsr_export_v1(&fixture, &supplemental, &request, &context).await?
                }
                Game::Zzz => {
                    let supplemental =
                        ZzzFixtureSupplementalSource::new(supplemental_root, context.fetched_at);
                    run_zzz_export_v1(&fixture, &supplemental, &request, &context).await?
                }
            };
            observer.fixture_mode(root);
            (run, Some(root.clone()))
        }
        ExportSourceV1::Online { cache_root }
        | ExportSourceV1::OnlineHfFreshnessRequired { cache_root, .. } => {
            let cache_root = invocation.resolve(cache_root);
            let mut repo = HuggingFaceRepo::new(&task.repo_id, &task.revision);
            if let ExportSourceV1::OnlineHfFreshnessRequired {
                hf_origin: Some(origin),
                ..
            } = &task.source
            {
                repo = repo.with_origin(origin);
            }
            let source = HfSnapshotSource::new(
                repo,
                HttpClient::new(StdDuration::from_secs(60), 2)?,
                &cache_root,
                FetchMode::Online,
            )
            .with_cache_fallback_policy(
                if matches!(
                    &task.source,
                    ExportSourceV1::OnlineHfFreshnessRequired { .. }
                ) {
                    HfCacheFallbackPolicy::Reject
                } else {
                    HfCacheFallbackPolicy::Allow
                },
            );
            let context = export_context(
                task.game,
                invocation,
                FetchPolicy::Online,
                cache_root.clone(),
                output_root.clone(),
            );
            let run = match task.game {
                Game::Hsr => {
                    let supplemental = HsrHttpSupplementalSource::new(
                        HttpClient::new(StdDuration::from_secs(60), 2)?,
                        cache_root.join("supplemental"),
                        FetchMode::Online,
                        context.fetched_at,
                    );
                    run_hsr_export_v1(&source, &supplemental, &request, &context).await?
                }
                Game::Zzz => {
                    let supplemental = ZzzHttpSupplementalSource::new(
                        HttpClient::new(StdDuration::from_secs(60), 2)?,
                        cache_root.join("supplemental"),
                        FetchMode::Online,
                        context.fetched_at,
                    );
                    run_zzz_export_v1(&source, &supplemental, &request, &context).await?
                }
            };
            (run, None)
        }
    };

    match task.game {
        Game::Hsr => attach_hsr_visualizer_from_output(&mut run.bundle, &output_root, invocation)?,
        Game::Zzz => attach_zzz_visualizer_from_output(&mut run.bundle, &output_root, invocation)?,
    }
    run.bundle.refresh_manifest("artifact_manifest.json")?;
    for diagnostic in &run.diagnostics {
        observer.diagnostic(diagnostic);
    }
    write_bundle_transactionally(&output_root, &run.bundle)?;
    if task.game == Game::Zzz {
        write_zzz_hub(&output_root, hsr_output_directory)?;
    }
    Ok(ExportReceiptV1 {
        game: task.game,
        output_root,
        fixture_root,
        diagnostics: run.diagnostics,
    })
}

pub fn execute_visualizer_v1(
    task: &VisualizerTaskV1,
    invocation: &ExportInvocation,
) -> anyhow::Result<()> {
    let output_root = invocation.resolve(&task.output_root);
    if task.game == Game::Zzz {
        validate_zzz_hub_preflight(&output_root, "out")?;
    }
    validate_output_root(&output_root)?;
    let mut bundle = load_existing_output(&output_root, task.game)?;
    match task.game {
        Game::Hsr => attach_hsr_visualizer_from_output(&mut bundle, &output_root, invocation)?,
        Game::Zzz => attach_zzz_visualizer_from_output(&mut bundle, &output_root, invocation)?,
    }
    bundle.refresh_manifest("artifact_manifest.json")?;
    write_bundle_transactionally(&output_root, &bundle)?;
    if task.game == Game::Zzz {
        write_zzz_hub(&output_root, "out")?;
    }
    Ok(())
}

fn export_context(
    game: Game,
    invocation: &ExportInvocation,
    fetch_policy: FetchPolicy,
    cache_root: PathBuf,
    output_root: PathBuf,
) -> ExportContext {
    ExportContext {
        fetched_at: invocation.fetched_at(),
        fetch_policy,
        cache_root,
        existing_output_root: Some(output_root.clone()),
        zzz_phase_overrides: zzz_phase_override_path(game, &output_root, invocation),
        output_root,
    }
}

fn attach_hsr_visualizer_from_output(
    bundle: &mut miho_core::output::ArtifactBundle,
    out: &Path,
    invocation: &ExportInvocation,
) -> anyhow::Result<()> {
    validate_optional_directory(out)?;
    validate_optional_directory(&out.join("visualizer"))?;
    let avatars = read_existing_visualizer_avatars(out)?;
    for path in hsr_banner_candidates(out, invocation) {
        let Some(bytes) = read_json_object_candidate(&path)? else {
            continue;
        };
        let mut context = visualizer_context(&avatars, invocation)?;
        context.add_sidecar_bytes("hsr_banner_plan.json", bytes)?;
        match attach_hsr_visualizer(bundle, &context) {
            Ok(()) => return Ok(()),
            Err(MihoError::Json { path, .. }) if path == Path::new("hsr_banner_plan.json") => {}
            Err(error) => return Err(error.into()),
        }
    }
    let context = visualizer_context(&avatars, invocation)?;
    attach_hsr_visualizer(bundle, &context)?;
    Ok(())
}

fn attach_zzz_visualizer_from_output(
    bundle: &mut miho_core::output::ArtifactBundle,
    out: &Path,
    invocation: &ExportInvocation,
) -> anyhow::Result<()> {
    validate_optional_directory(out)?;
    validate_optional_directory(&out.join("visualizer"))?;
    let avatars = read_existing_visualizer_avatars(out)?;
    let mut context = visualizer_context(&avatars, invocation)?;
    if let Some(bytes) =
        first_valid_phase_override_candidate(&zzz_phase_override_candidates(out, invocation))?
    {
        context.add_sidecar_bytes("zzz_endgame_phase_overrides.json", bytes)?;
    }
    if let Some(bytes) = first_valid_json_candidate(
        &zzz_banner_candidates(out, invocation),
        serde_json::Value::is_object,
    )? {
        context.add_sidecar_bytes("zzz_banner_plan.json", bytes)?;
    }
    match fs::read(out.join("decision_cards.json")) {
        Ok(bytes) => context.add_sidecar_bytes("decision_cards.json", bytes)?,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    attach_zzz_visualizer(bundle, &context)?;
    Ok(())
}

static NEXT_OUTPUT_TRANSACTION_ID: AtomicU64 = AtomicU64::new(0);

fn write_bundle_transactionally(
    out: &Path,
    bundle: &miho_core::output::ArtifactBundle,
) -> anyhow::Result<()> {
    let name = out.file_name().ok_or_else(|| {
        anyhow::anyhow!(
            "transactional output requires a named directory: {}",
            out.display()
        )
    })?;
    let parent = out
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    let old_exists = match fs::symlink_metadata(out) {
        Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_dir() => true,
        Ok(_) => bail!("refusing unsafe output directory: {}", out.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(error) => return Err(error.into()),
    };
    let old_managed = if old_exists {
        read_manifest_ownership(out)?
    } else {
        None
    };
    let stage = create_transaction_stage(parent, name)?;
    let prepare = (|| -> anyhow::Result<()> {
        if old_exists {
            copy_directory_contents(out, &stage)?;
        }
        remove_staged_visualizer(&stage)?;
        remove_staged_manifest(&stage)?;
        remove_stale_managed(&stage, old_managed.as_ref(), bundle)?;
        bundle.write_to(&stage)?;
        Ok(())
    })();
    if let Err(error) = prepare {
        let _ = fs::remove_dir_all(&stage);
        return Err(error);
    }
    #[cfg(debug_assertions)]
    if std::env::var_os("MIHO_TEST_FAIL_OUTPUT_TRANSACTION_BEFORE_SWAP").is_some() {
        fs::remove_dir_all(&stage)?;
        bail!("injected output transaction failure before swap");
    }
    install_staged_directory(out, parent, name, stage, old_exists, "output")
}

fn write_zzz_hub(out: &Path, hsr_output_directory: &str) -> anyhow::Result<()> {
    validate_zzz_hub_preflight(out, hsr_output_directory)?;
    let zzz_dir = out
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| {
            anyhow::anyhow!("ZZZ output directory name is not UTF-8: {}", out.display())
        })?;
    let workspace = out
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let mut bundle = miho_core::output::ArtifactBundle::default();
    attach_visualizer_hub(&mut bundle, hsr_output_directory, zzz_dir)?;
    write_clean_directory_transactionally(&workspace.join("visualizer"), &bundle)
}

fn validate_zzz_hub_preflight(out: &Path, hsr_output_directory: &str) -> anyhow::Result<()> {
    let zzz_dir = out
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| {
            anyhow::anyhow!("ZZZ output directory name is not UTF-8: {}", out.display())
        })?;
    let workspace = out
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let mut probe = miho_core::output::ArtifactBundle::default();
    attach_visualizer_hub(&mut probe, hsr_output_directory, zzz_dir)?;
    let target = workspace.join("visualizer");
    match fs::symlink_metadata(&target) {
        Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_dir() => Ok(()),
        Ok(_) => bail!("refusing unsafe hub directory: {}", target.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

fn write_clean_directory_transactionally(
    target: &Path,
    bundle: &miho_core::output::ArtifactBundle,
) -> anyhow::Result<()> {
    let name = target.file_name().ok_or_else(|| {
        anyhow::anyhow!(
            "transactional directory requires a name: {}",
            target.display()
        )
    })?;
    let parent = target
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    let old_exists = match fs::symlink_metadata(target) {
        Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_dir() => true,
        Ok(_) => bail!("refusing unsafe hub directory: {}", target.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(error) => return Err(error.into()),
    };
    let stage = create_transaction_stage(parent, name)?;
    if let Err(error) = bundle.write_to(&stage) {
        let _ = fs::remove_dir_all(&stage);
        return Err(error.into());
    }
    #[cfg(debug_assertions)]
    if std::env::var_os("MIHO_TEST_FAIL_HUB_TRANSACTION_BEFORE_SWAP").is_some() {
        fs::remove_dir_all(&stage)?;
        bail!("injected Hub transaction failure before swap");
    }
    install_staged_directory(target, parent, name, stage, old_exists, "Hub")
}

fn install_staged_directory(
    target: &Path,
    parent: &Path,
    name: &OsStr,
    stage: PathBuf,
    old_exists: bool,
    label: &str,
) -> anyhow::Result<()> {
    if !old_exists {
        if let Err(error) = fs::rename(&stage, target) {
            let _ = fs::remove_dir_all(&stage);
            return Err(error.into());
        }
        return Ok(());
    }
    let backup = unused_transaction_sibling(parent, name, "backup")?;
    if let Err(error) = fs::rename(target, &backup) {
        let _ = fs::remove_dir_all(&stage);
        return Err(error.into());
    }
    if let Err(install_error) = fs::rename(&stage, target) {
        let rollback = fs::rename(&backup, target);
        let _ = fs::remove_dir_all(&stage);
        return match rollback {
            Ok(()) => Err(install_error.into()),
            Err(rollback_error) => Err(anyhow::anyhow!(
                "{label} install failed ({install_error}); rollback also failed ({rollback_error}); old {label} remains at {}",
                backup.display()
            )),
        };
    }
    fs::remove_dir_all(backup)?;
    Ok(())
}

fn create_transaction_stage(parent: &Path, name: &OsStr) -> anyhow::Result<PathBuf> {
    loop {
        let stage = transaction_sibling(parent, name, "stage");
        match fs::create_dir(&stage) {
            Ok(()) => return Ok(stage),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error.into()),
        }
    }
}

fn unused_transaction_sibling(parent: &Path, name: &OsStr, kind: &str) -> anyhow::Result<PathBuf> {
    loop {
        let path = transaction_sibling(parent, name, kind);
        match fs::symlink_metadata(&path) {
            Ok(_) => continue,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(path),
            Err(error) => return Err(error.into()),
        }
    }
}

fn transaction_sibling(parent: &Path, name: &OsStr, kind: &str) -> PathBuf {
    let id = NEXT_OUTPUT_TRANSACTION_ID.fetch_add(1, Ordering::Relaxed);
    parent.join(format!(
        ".{}.miho-{kind}-{}-{id}",
        name.to_string_lossy(),
        std::process::id()
    ))
}

fn copy_directory_contents(source: &Path, destination: &Path) -> anyhow::Result<()> {
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let source_path = entry.path();
        let destination_path = destination.join(entry.file_name());
        let file_type = entry.file_type()?;
        if file_type.is_symlink() {
            bail!(
                "refusing symlink in existing output: {}",
                source_path.display()
            );
        }
        if file_type.is_dir() {
            fs::create_dir(&destination_path)?;
            copy_directory_contents(&source_path, &destination_path)?;
        } else if file_type.is_file() {
            fs::copy(&source_path, &destination_path)?;
        } else {
            bail!("unsupported artifact type: {}", source_path.display());
        }
    }
    Ok(())
}

fn remove_staged_visualizer(stage: &Path) -> anyhow::Result<()> {
    let path = stage.join("visualizer");
    match fs::symlink_metadata(&path) {
        Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_dir() => {
            fs::remove_dir_all(path)?;
        }
        Ok(_) => bail!("refusing unsafe staged visualizer path: {}", path.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

fn remove_staged_manifest(stage: &Path) -> anyhow::Result<()> {
    let path = stage.join("artifact_manifest.json");
    match fs::symlink_metadata(&path) {
        Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_file() => {
            fs::remove_file(path)?;
        }
        Ok(_) => bail!("refusing unsafe staged manifest path: {}", path.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

fn remove_stale_managed(
    stage: &Path,
    old_managed: Option<&BTreeSet<PathBuf>>,
    bundle: &miho_core::output::ArtifactBundle,
) -> anyhow::Result<()> {
    let Some(old_managed) = old_managed else {
        return Ok(());
    };
    let new_managed = bundle
        .manifest()
        .into_iter()
        .map(|entry| PathBuf::from(entry.path))
        .collect::<BTreeSet<_>>();
    for relative in old_managed {
        if is_visualizer_path(relative)
            || relative == Path::new("artifact_manifest.json")
            || is_known_sidecar(relative)
            || new_managed.contains(relative)
        {
            continue;
        }
        let path = stage.join(relative);
        match fs::symlink_metadata(&path) {
            Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_file() => {
                fs::remove_file(path)?;
            }
            Ok(_) => bail!("refusing unsafe stale managed path: {}", path.display()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

fn validate_output_root(out: &Path) -> anyhow::Result<()> {
    let metadata = fs::symlink_metadata(out)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        bail!(
            "visualizer output is not a trusted directory: {}",
            out.display()
        );
    }
    Ok(())
}

fn validate_optional_directory(path: &Path) -> anyhow::Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if !metadata.file_type().is_symlink() && metadata.is_dir() => Ok(true),
        Ok(_) => bail!("refusing unsafe directory path: {}", path.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn load_existing_output(
    out: &Path,
    game: Game,
) -> anyhow::Result<miho_core::output::ArtifactBundle> {
    fn visit(
        root: &Path,
        current: &Path,
        game: Game,
        bundle: &mut miho_core::output::ArtifactBundle,
    ) -> anyhow::Result<()> {
        for entry in fs::read_dir(current)? {
            let entry = entry?;
            let path = entry.path();
            let relative = path.strip_prefix(root)?;
            let file_type = entry.file_type()?;
            if is_visualizer_path(relative)
                || relative == Path::new("artifact_manifest.json")
                || is_known_sidecar(relative)
            {
                continue;
            }
            if file_type.is_symlink() {
                bail!("refusing symlink in existing output: {}", path.display());
            }
            if file_type.is_dir() {
                visit(root, &path, game, bundle)?;
            } else if file_type.is_file() && is_legacy_managed_artifact(game, relative) {
                bundle.add_bytes(relative, fs::read(&path)?)?;
            } else if !file_type.is_file() {
                bail!("unsupported artifact type: {}", path.display());
            }
        }
        Ok(())
    }

    let mut bundle = miho_core::output::ArtifactBundle::default();
    if let Some(managed) = read_manifest_ownership(out)? {
        for relative in managed {
            if is_visualizer_path(&relative)
                || relative == Path::new("artifact_manifest.json")
                || is_known_sidecar(&relative)
            {
                continue;
            }
            let path = out.join(&relative);
            let metadata = fs::symlink_metadata(&path).map_err(|error| {
                anyhow::anyhow!(
                    "managed artifact is not readable: {}: {error}",
                    path.display()
                )
            })?;
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                bail!("managed artifact is not a regular file: {}", path.display());
            }
            bundle.add_bytes(relative, fs::read(path)?)?;
        }
    } else {
        visit(out, out, game, &mut bundle)?;
    }
    Ok(bundle)
}

fn is_legacy_managed_artifact(game: Game, path: &Path) -> bool {
    let fixed = match game {
        Game::Hsr => matches!(
            path.to_str(),
            Some(
                "phase_index.csv"
                    | "character_usage_long.csv"
                    | "team_rank_raw.csv"
                    | "prydwen_tier_current.csv"
                    | "histograph_usage_long.csv"
                    | "character_usage_phase_latest.csv"
                    | "team_rank_dedup_ordered.csv"
                    | "team_rank_dedup_unordered.csv"
                    | "name_map.csv"
                    | "name_map_unresolved.csv"
                    | "prydwen_tier_history.csv"
                    | "prydwen_tier_changelog.csv"
                    | "prydwen_tier_changelog_history.csv"
                    | "prydwen_tier_usage_trend.csv"
                    | "prydwen_tier_charts.csv"
                    | "overview.csv"
                    | "latest_usage_cn.csv"
                    | "top_teams_latest.csv"
                    | "export_report.md"
                    | "hsr_endgame_dataset.xlsx"
            )
        ),
        Game::Zzz => matches!(
            path.to_str(),
            Some(
                "phase_index.csv"
                    | "character_usage_long.csv"
                    | "character_usage_phase_latest.csv"
                    | "team_rank_raw.csv"
                    | "team_rank_dedup_unordered.csv"
                    | "name_map.csv"
                    | "name_map_unresolved.csv"
                    | "prydwen_tier_current.csv"
                    | "prydwen_tier_history.csv"
                    | "prydwen_tier_changelog.csv"
                    | "prydwen_tier_changelog_history.csv"
                    | "prydwen_tier_usage_trend.csv"
                    | "export_report.md"
                    | "zzz_endgame_dataset.xlsx"
            )
        ),
    };
    fixed || is_legacy_raw_artifact(game, path) || is_legacy_chart_artifact(game, path)
}

fn is_legacy_raw_artifact(game: Game, path: &Path) -> bool {
    if path.starts_with("raw/hf") {
        return path != Path::new("raw/hf");
    }
    match game {
        Game::Hsr => {
            [
                "raw/prydwen/aa.html",
                "raw/prydwen/as.html",
                "raw/prydwen/moc.html",
                "raw/prydwen/pf.html",
                "raw/hoyowiki/hsr_characters_zh-cn.json",
                "raw/hoyowiki/hsr_characters_en-us.json",
            ]
            .into_iter()
            .any(|candidate| path == Path::new(candidate))
                || is_prydwen_tier_snapshot(path)
        }
        Game::Zzz => {
            [
                "raw/prydwen/sd.html",
                "raw/prydwen/da.html",
                "raw/hoyowiki/zzz_agents_zh-cn.json",
                "raw/hoyowiki/zzz_agents_en-us.json",
                "raw/hoyowiki/zzz_bangboo_zh-cn.json",
                "raw/hoyowiki/zzz_bangboo_en-us.json",
            ]
            .into_iter()
            .any(|candidate| path == Path::new(candidate))
                || is_prydwen_tier_snapshot(path)
        }
    }
}

fn is_prydwen_tier_snapshot(path: &Path) -> bool {
    path.parent() == Some(Path::new("raw/prydwen_tier"))
        && path
            .file_name()
            .and_then(|value| value.to_str())
            .and_then(|value| value.strip_prefix("tier-list_"))
            .and_then(|value| value.strip_suffix(".html"))
            .is_some_and(|snapshot| !snapshot.is_empty())
}

fn is_legacy_chart_artifact(game: Game, path: &Path) -> bool {
    game == Game::Hsr
        && path.parent() == Some(Path::new("charts/prydwen_tier_usage"))
        && path.extension().and_then(|value| value.to_str()) == Some("svg")
        && path.file_stem().is_some_and(|value| !value.is_empty())
}

fn read_manifest_ownership(out: &Path) -> anyhow::Result<Option<BTreeSet<PathBuf>>> {
    let path = out.join("artifact_manifest.json");
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let entries: Vec<miho_core::output::ArtifactManifestEntry> = serde_json::from_slice(&bytes)
        .map_err(|error| anyhow::anyhow!("invalid existing artifact manifest: {error}"))?;
    let mut managed = BTreeSet::new();
    for entry in entries {
        let relative = PathBuf::from(entry.path);
        if relative.as_os_str().is_empty()
            || relative.is_absolute()
            || relative
                .components()
                .any(|component| !matches!(component, Component::Normal(_)))
        {
            bail!(
                "invalid path in existing artifact manifest: {}",
                relative.display()
            );
        }
        if !managed.insert(relative.clone()) {
            bail!(
                "duplicate path in existing artifact manifest: {}",
                relative.display()
            );
        }
    }
    Ok(Some(managed))
}

fn is_visualizer_path(path: &Path) -> bool {
    path == Path::new("visualizer") || path.starts_with("visualizer")
}

fn is_known_sidecar(path: &Path) -> bool {
    matches!(
        path.to_str(),
        Some(
            "hsr_banner_plan.json"
                | "zzz_endgame_phase_overrides.json"
                | "zzz_banner_plan.json"
                | "decision_cards.json"
        )
    )
}

fn read_existing_visualizer_avatars(out: &Path) -> anyhow::Result<Vec<(String, Vec<u8>)>> {
    if !validate_optional_directory(&out.join("visualizer/assets"))? {
        return Ok(Vec::new());
    }
    let root = out.join("visualizer/assets/avatars");
    if !validate_optional_directory(&root)? {
        return Ok(Vec::new());
    }
    let entries = fs::read_dir(&root)?;
    let mut avatars = Vec::new();
    for entry in entries {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let path = entry.path();
        if file_type.is_symlink() {
            bail!("refusing symlink in avatar store: {}", path.display());
        }
        if !file_type.is_file() || path.extension().and_then(|value| value.to_str()) != Some("webp")
        {
            continue;
        }
        let slug = path
            .file_stem()
            .and_then(|value| value.to_str())
            .ok_or_else(|| anyhow::anyhow!("avatar filename is not UTF-8: {}", path.display()))?;
        avatars.push((slug.to_owned(), fs::read(path)?));
    }
    avatars.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(avatars)
}

fn visualizer_context(
    avatars: &[(String, Vec<u8>)],
    invocation: &ExportInvocation,
) -> anyhow::Result<VisualizerContext> {
    let mut context = VisualizerContext::new_with_local_datetime(invocation.local_datetime());
    for (slug, bytes) in avatars {
        context.add_avatar_webp(slug, bytes.clone())?;
    }
    Ok(context)
}

fn hsr_banner_candidates(out: &Path, invocation: &ExportInvocation) -> Vec<PathBuf> {
    let mut candidates = vec![out.join("hsr_banner_plan.json")];
    if let Some(parent) = out.parent() {
        candidates.push(parent.join("configs/hsr_banner_plan.json"));
    }
    candidates.push(invocation.resolve(Path::new("configs/hsr_banner_plan.json")));
    candidates
}

fn zzz_phase_override_candidates(out: &Path, invocation: &ExportInvocation) -> Vec<PathBuf> {
    let mut candidates = vec![out.join("zzz_endgame_phase_overrides.json")];
    if let Some(parent) = out.parent() {
        candidates.push(parent.join("configs/zzz_endgame_phase_overrides.json"));
    }
    candidates.push(invocation.resolve(Path::new("configs/zzz_endgame_phase_overrides.json")));
    candidates
}

fn zzz_banner_candidates(out: &Path, invocation: &ExportInvocation) -> Vec<PathBuf> {
    let mut candidates = vec![out.join("zzz_banner_plan.json")];
    if let Some(parent) = out.parent() {
        candidates.push(parent.join("configs/zzz_banner_plan.json"));
    }
    candidates.push(invocation.resolve(Path::new("configs/zzz_banner_plan.json")));
    candidates
}

fn first_valid_json_candidate(
    paths: &[PathBuf],
    is_valid: fn(&serde_json::Value) -> bool,
) -> anyhow::Result<Option<Vec<u8>>> {
    for path in paths {
        let bytes = match fs::read(path) {
            Ok(bytes) => bytes,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => return Err(error.into()),
        };
        let text = strict_utf8_candidate(&bytes, path)?;
        validate_json_surrogate_escapes(text, &path.display().to_string())?;
        let Ok(value) = serde_json::from_str(text) else {
            continue;
        };
        if is_valid(&value) {
            return Ok(Some(bytes));
        }
    }
    Ok(None)
}

fn first_valid_phase_override_candidate(paths: &[PathBuf]) -> anyhow::Result<Option<Vec<u8>>> {
    for path in paths {
        let Ok(bytes) = fs::read(path) else {
            continue;
        };
        let text = strict_utf8_candidate(&bytes, path)?;
        validate_json_surrogate_escapes(text, &path.display().to_string())?;
        let Ok(value) = serde_json::from_str(text) else {
            continue;
        };
        if is_valid_phase_override(&value) {
            return Ok(Some(bytes));
        }
    }
    Ok(None)
}

fn is_valid_phase_override(value: &serde_json::Value) -> bool {
    value.is_array()
        || value
            .as_object()
            .and_then(|object| object.get("phases"))
            .is_some_and(serde_json::Value::is_array)
}

fn read_json_object_candidate(path: &Path) -> anyhow::Result<Option<Vec<u8>>> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let text = strict_utf8_candidate(&bytes, path)?.trim();
    validate_json_surrogate_escapes(text, &path.display().to_string())?;
    Ok((text.starts_with('{') && text.ends_with('}')).then_some(bytes))
}

fn strict_utf8_candidate<'a>(bytes: &'a [u8], path: &Path) -> anyhow::Result<&'a str> {
    std::str::from_utf8(bytes)
        .map_err(|source| anyhow::anyhow!("invalid UTF-8 in {}: {source}", path.display()))
}

fn zzz_phase_override_path(
    game: Game,
    output_root: &Path,
    invocation: &ExportInvocation,
) -> Option<PathBuf> {
    if game != Game::Zzz {
        return None;
    }
    first_valid_phase_override_path(zzz_phase_override_candidates(output_root, invocation))
}

pub fn export_cache_root(base: &Path, game: Game, repo_id: &str, revision: &str) -> PathBuf {
    base.join(match game {
        Game::Hsr => "hsr",
        Game::Zzz => "zzz",
    })
    .join(safe_cache_component(repo_id))
    .join(safe_cache_component(revision))
}

fn safe_cache_component(value: &str) -> String {
    const READABLE_PREFIX_LENGTH: usize = 48;

    let mut readable_prefix = value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.') {
                character
            } else {
                '_'
            }
        })
        .take(READABLE_PREFIX_LENGTH)
        .collect::<String>();
    if readable_prefix.is_empty() || readable_prefix == "." || readable_prefix == ".." {
        readable_prefix = "_".into();
    }

    let digest = Sha256::digest(value.as_bytes());
    format!("{readable_prefix}--{digest:x}")
}

fn lexical_absolute(path: &Path) -> anyhow::Result<PathBuf> {
    if path.is_absolute() {
        Ok(lexical_normalize(path.to_path_buf()))
    } else {
        Ok(lexical_normalize(
            std::env::current_dir()
                .context("cannot resolve export working directory")?
                .join(path),
        ))
    }
}

fn lexical_normalize(path: PathBuf) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                let _ = normalized.pop();
            }
            Component::Prefix(_) | Component::RootDir | Component::Normal(_) => {
                normalized.push(component.as_os_str());
            }
        }
    }
    normalized
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invocation_derives_utc_local_and_report_time_from_one_instant() {
        let observed_at = DateTime::parse_from_rfc3339("2026-07-13T09:30:01.123456+08:00").unwrap();
        let invocation = ExportInvocation::new(PathBuf::from("."), observed_at).unwrap();
        assert_eq!(
            invocation.fetched_at().to_rfc3339(),
            "2026-07-13T01:30:01.123456+00:00"
        );
        assert_eq!(
            invocation.local_datetime().to_string(),
            "2026-07-13 09:30:01.123456"
        );
        assert_eq!(
            invocation.app_invocation().unwrap().local_datetime(),
            invocation.local_datetime()
        );
    }

    #[test]
    fn cache_path_is_safe_and_isolated_by_repo_and_revision() {
        let base = PathBuf::from("cache-root");
        let first = export_cache_root(&base, Game::Hsr, "owner/repo", "feature/test");
        let second = export_cache_root(&base, Game::Hsr, "owner/other", "main");
        assert!(first.starts_with(base.join("hsr")));
        let components = first
            .strip_prefix(base.join("hsr"))
            .unwrap()
            .components()
            .map(|component| component.as_os_str().to_string_lossy().into_owned())
            .collect::<Vec<_>>();
        assert_eq!(components.len(), 2);
        assert!(components[0].starts_with("owner_repo--"));
        assert!(components[1].starts_with("feature_test--"));
        assert!(components.iter().all(|component| component.len() <= 114));
        assert_ne!(first, second);
        assert!(safe_cache_component("..").starts_with("_--"));
        assert!(safe_cache_component("").starts_with("_--"));
    }

    #[test]
    fn cache_component_hashes_original_utf8_identity_after_sanitizing() {
        let slash = safe_cache_component("feature/test");
        let underscore = safe_cache_component("feature_test");
        assert_eq!(
            slash,
            "feature_test--59e07aa6356bd11ff7777d522432c0202ca2f46966550c43290472e8af410144"
        );
        assert_eq!(
            underscore,
            "feature_test--829f3f51c7bb07537bbbb8c2f1db19f172a4e0ff8e531bf3dd4ba1657a021dae"
        );
        assert_ne!(slash, underscore);

        let unicode = safe_cache_component("öwner/repo");
        let replaced = safe_cache_component("_wner_repo");
        assert!(unicode.starts_with("_wner_repo--"));
        assert!(replaced.starts_with("_wner_repo--"));
        assert_ne!(unicode, replaced);
    }

    #[test]
    fn cache_root_preserves_combined_game_repo_and_revision_identity() {
        let base = PathBuf::from("cache-root");
        let paths = [
            export_cache_root(&base, Game::Hsr, "owner/repo", "feature/test"),
            export_cache_root(&base, Game::Hsr, "owner_repo", "feature/test"),
            export_cache_root(&base, Game::Hsr, "owner/repo", "feature_test"),
            export_cache_root(&base, Game::Zzz, "owner/repo", "feature/test"),
        ];
        let unique = paths.iter().collect::<BTreeSet<_>>();
        assert_eq!(unique.len(), paths.len());
    }

    #[test]
    fn legacy_ownership_allowlist_covers_optional_exports_but_rejects_unknown_files() {
        for path in [
            "hsr_endgame_dataset.xlsx",
            "export_report.md",
            "prydwen_tier_charts.csv",
            "charts/prydwen_tier_usage/moc_sub_dps_t0_t2_usage.svg",
            "raw/hf/4.3.2/moc/comps/stage_1_combined.json",
            "raw/prydwen/pf.html",
            "raw/prydwen_tier/tier-list_20260106.html",
            "raw/hoyowiki/hsr_characters_en-us.json",
        ] {
            assert!(is_legacy_managed_artifact(Game::Hsr, Path::new(path)));
        }
        for (game, path) in [
            (Game::Hsr, "keep-me.txt"),
            (Game::Zzz, "notes/keep-me.txt"),
            (Game::Hsr, "raw/prydwen/keep-me.html"),
            (Game::Zzz, "raw/hoyowiki/keep-me.json"),
        ] {
            assert!(!is_legacy_managed_artifact(game, Path::new(path)));
        }
    }

    #[test]
    fn zzz_phase_override_skips_a_broken_higher_priority_candidate() {
        let root = std::env::temp_dir().join(format!(
            "miho-app-phase-override-{}-{}",
            std::process::id(),
            NEXT_OUTPUT_TRANSACTION_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let out = root.join("out");
        let fallback = root.join("configs/zzz_endgame_phase_overrides.json");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&out).unwrap();
        fs::create_dir_all(fallback.parent().unwrap()).unwrap();
        fs::create_dir(out.join("zzz_endgame_phase_overrides.json")).unwrap();
        fs::write(&fallback, r#"{"phases":[]}"#).unwrap();
        let invocation = ExportInvocation::new(
            root.clone(),
            DateTime::parse_from_rfc3339("2026-07-13T09:30:00+08:00").unwrap(),
        )
        .unwrap();
        assert_eq!(
            zzz_phase_override_path(Game::Zzz, &out, &invocation),
            Some(fallback)
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn typed_executor_uses_the_injected_instant_in_export_bytes() {
        let workspace = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let root = std::env::temp_dir().join(format!(
            "miho-app-export-clock-{}-{}",
            std::process::id(),
            NEXT_OUTPUT_TRANSACTION_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let invocation = ExportInvocation::new(
            workspace.clone(),
            DateTime::parse_from_rfc3339("2026-07-13T09:30:01.123456+08:00").unwrap(),
        )
        .unwrap();
        let output_root = root.join("hsr-out");
        let receipt = execute_export_v1(
            &ExportTaskV1 {
                game: Game::Hsr,
                modes: vec![
                    GameMode::HsrMoc,
                    GameMode::HsrPf,
                    GameMode::HsrAs,
                    GameMode::HsrAa,
                ],
                from_date: NaiveDate::from_ymd_opt(2026, 1, 11).unwrap(),
                to_date: NaiveDate::from_ymd_opt(2026, 7, 13).unwrap(),
                output_root: output_root.clone(),
                repo_id: "LvlUrArti/MocDataProcessed".to_owned(),
                revision: "main".to_owned(),
                features: FeatureFlags {
                    hf_teams: true,
                    prydwen_visible: true,
                    prydwen_tier: true,
                    official_names: true,
                },
                prydwen_top_n: 100,
                name_map_seed: None,
                source: ExportSourceV1::Fixture {
                    root: workspace.join("tests/fixtures/offline_hsr"),
                    supplemental_root: Some(workspace.join("tests/fixtures/hsr_supplemental")),
                },
            },
            &invocation,
        )
        .await
        .unwrap();
        assert_eq!(receipt.output_root, output_root);
        let report = fs::read_to_string(output_root.join("export_report.md")).unwrap();
        assert!(report.contains("2026-07-13T01:30:01Z"), "{report}");
        assert!(output_root.join("visualizer/data.json").is_file());
        assert!(output_root.join("artifact_manifest.json").is_file());
        fs::remove_dir_all(root).unwrap();
    }
}
