use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::Duration as StdDuration,
};

use anyhow::bail;
use chrono::{Duration, Local, Utc};
use clap::{Args, Parser, Subcommand};
use miho_core::{
    contract::{
        DatasetRef, DateRange, DiagnosticSeverity, ExportContext, FeatureFlags, FetchPolicy,
        GameMode, HistoryPolicy, WorkbookPolicy, EXPORT_REQUEST_SCHEMA_VERSION,
    },
    hf::HuggingFaceRepo,
    hsr_supplemental::{HsrFixtureSupplementalSource, HsrHttpSupplementalSource},
    hsr_visualizer::attach_hsr_visualizer,
    network::{FetchMode, HttpClient},
    normalize::parse_date,
    pipeline::{run_hsr_export_v1, run_zzz_export_v1, ExportRequest, Game, OfflineFixture},
    source::HfSnapshotSource,
    visualizer::VisualizerContext,
    zzz_enrichment::first_valid_phase_override_path,
    zzz_supplemental::{ZzzFixtureSupplementalSource, ZzzHttpSupplementalSource},
    MihoError,
};

#[derive(Parser)]
#[command(name = "miho", version, about = "HSR and ZZZ endgame data exporter")]
struct Cli {
    #[command(subcommand)]
    game: GameCommand,
}

#[derive(Subcommand)]
enum GameCommand {
    Hsr {
        #[command(subcommand)]
        command: HsrCommand,
    },
    Zzz {
        #[command(subcommand)]
        command: ZzzCommand,
    },
}

#[derive(Subcommand)]
enum HsrCommand {
    Export(HsrExportArgs),
    Visualizer(VisualizerArgs),
}

#[derive(Subcommand)]
enum ZzzCommand {
    Export(ZzzExportArgs),
    Decision(DecisionArgs),
    Evidence(EvidenceArgs),
    Coverage(CoverageArgs),
    #[command(name = "pull-value")]
    PullValue(PullValueArgs),
    #[command(name = "review-packet")]
    ReviewPacket(PullValueArgs),
    Visualizer(VisualizerArgs),
    Serve(ServeArgs),
}

#[derive(Args, Default)]
struct ExportToggles {
    #[arg(long, action = clap::ArgAction::SetTrue, conflicts_with = "no_include_teams")]
    include_teams: bool,
    #[arg(long = "no-include-teams", action = clap::ArgAction::SetTrue)]
    no_include_teams: bool,
    #[arg(long, action = clap::ArgAction::SetTrue, conflicts_with = "no_include_prydwen_visible")]
    include_prydwen_visible: bool,
    #[arg(long = "no-include-prydwen-visible", action = clap::ArgAction::SetTrue)]
    no_include_prydwen_visible: bool,
    #[arg(long, action = clap::ArgAction::SetTrue, conflicts_with = "no_include_prydwen_tier")]
    include_prydwen_tier: bool,
    #[arg(long = "no-include-prydwen-tier", action = clap::ArgAction::SetTrue)]
    no_include_prydwen_tier: bool,
    #[arg(long, action = clap::ArgAction::SetTrue, conflicts_with = "no_official_name_map")]
    official_name_map: bool,
    #[arg(long = "no-official-name-map", action = clap::ArgAction::SetTrue)]
    no_official_name_map: bool,
}

impl ExportToggles {
    fn values(&self) -> [bool; 4] {
        [
            !self.no_include_teams,
            !self.no_include_prydwen_visible,
            !self.no_include_prydwen_tier,
            !self.no_official_name_map,
        ]
    }
}

#[derive(Args)]
struct HsrExportArgs {
    #[command(flatten)]
    common: ExportCommon,
    #[command(flatten)]
    toggles: ExportToggles,
    #[arg(long)]
    name_map_seed: Option<PathBuf>,
}

#[derive(Args)]
struct ZzzExportArgs {
    #[command(flatten)]
    common: ExportCommon,
    #[command(flatten)]
    toggles: ExportToggles,
}

#[derive(Args)]
struct ExportCommon {
    #[arg(long)]
    from_date: Option<String>,
    #[arg(long)]
    to_date: Option<String>,
    #[arg(long)]
    out: Option<PathBuf>,
    #[arg(long)]
    modes: Option<String>,
    #[arg(long)]
    repo_id: Option<String>,
    #[arg(long)]
    prydwen_top_n: Option<usize>,
}

#[derive(Debug, PartialEq)]
struct EffectiveExport {
    from_date: String,
    to_date: String,
    out: PathBuf,
    modes: String,
    repo_id: String,
    prydwen_top_n: usize,
    toggles: [bool; 4],
}

impl ExportCommon {
    fn effective(&self, defaults: (&str, &str, &str), toggles: &ExportToggles) -> EffectiveExport {
        let today = Local::now().date_naive();
        EffectiveExport {
            from_date: self
                .from_date
                .clone()
                .unwrap_or_else(|| (today - Duration::days(183)).to_string()),
            to_date: self.to_date.clone().unwrap_or_else(|| today.to_string()),
            out: self
                .out
                .clone()
                .unwrap_or_else(|| PathBuf::from(defaults.0)),
            modes: self.modes.clone().unwrap_or_else(|| defaults.1.to_owned()),
            repo_id: self
                .repo_id
                .clone()
                .unwrap_or_else(|| defaults.2.to_owned()),
            prydwen_top_n: self.prydwen_top_n.unwrap_or(100),
            toggles: toggles.values(),
        }
    }
}

impl HsrExportArgs {
    fn effective(&self) -> EffectiveExport {
        self.common.effective(
            (
                "./hsr_endgame_export",
                "moc,pf,as,aa",
                "LvlUrArti/MocDataProcessed",
            ),
            &self.toggles,
        )
    }
}

impl ZzzExportArgs {
    fn effective(&self) -> EffectiveExport {
        self.common.effective(
            (
                "./zzz_endgame_export",
                "sd,da",
                "LvlUrArti/ShiyuDataProcessed",
            ),
            &self.toggles,
        )
    }
}

#[derive(Args)]
struct VisualizerArgs {
    #[arg(long)]
    out: Option<PathBuf>,
}

#[derive(Args)]
struct DecisionArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "./zzz_endgame_export")]
    out: PathBuf,
    #[arg(long, default_value = "./configs/zzz_decision_rules.yaml")]
    rules: PathBuf,
}

#[derive(Args)]
struct EvidenceArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "./zzz_endgame_export")]
    out: PathBuf,
    #[arg(long)]
    planned_slugs: Option<String>,
    #[arg(long)]
    plan: Option<PathBuf>,
    #[arg(long, default_value = "next")]
    plan_status: String,
    #[arg(long)]
    output: Option<PathBuf>,
    #[arg(long, default_value_t = 0)]
    limit: usize,
    #[arg(long, default_value = "10.0")]
    min_a_app_rate: String,
    #[arg(long, action = clap::ArgAction::SetTrue, conflicts_with = "no_include_missing")]
    include_missing: bool,
    #[arg(long = "no-include-missing", action = clap::ArgAction::SetTrue)]
    no_include_missing: bool,
}

#[cfg(test)]
impl EvidenceArgs {
    fn effective_include_missing(&self) -> bool {
        self.include_missing && !self.no_include_missing
    }
}

#[derive(Args)]
struct CoverageArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "./zzz_endgame_export")]
    out: PathBuf,
    #[arg(long)]
    planned_slugs: Option<String>,
    #[arg(long)]
    plan: Option<PathBuf>,
    #[arg(long, default_value = "next")]
    plan_status: String,
    #[arg(long, default_value_t = 0)]
    limit: usize,
    #[arg(long, default_value = "10.0")]
    min_a_app_rate: String,
    #[arg(long)]
    aggregate_output: Option<PathBuf>,
    #[arg(long)]
    current_output: Option<PathBuf>,
    #[arg(long)]
    target_output: Option<PathBuf>,
}

#[derive(Args)]
struct PullValueArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "./zzz_endgame_export")]
    out: PathBuf,
    #[arg(long, default_value = "./configs/zzz_banner_plan.json")]
    plan: PathBuf,
    #[arg(long, default_value = "current,next")]
    plan_status: String,
    #[arg(long)]
    planned_slugs: Option<String>,
    #[arg(long)]
    mechanism_notes_dir: Option<PathBuf>,
    #[arg(long, default_value = "./configs/zzz_decision_baseline.json")]
    decision_baseline: PathBuf,
    #[arg(long)]
    output: Option<PathBuf>,
}

#[derive(Args)]
struct ServeArgs {
    #[arg(long, default_value = ".")]
    root: PathBuf,
    #[arg(long, default_value = "127.0.0.1")]
    host: String,
    #[arg(long, default_value_t = 8765)]
    port: u16,
}

#[tokio::main]
async fn main() {
    if let Err(error) = execute(Cli::parse()).await {
        eprintln!("export failed: {error}");
        std::process::exit(1);
    }
}

async fn execute(cli: Cli) -> anyhow::Result<()> {
    if let GameCommand::Hsr {
        command: HsrCommand::Visualizer(args),
    } = &cli.game
    {
        let out = args
            .out
            .clone()
            .unwrap_or_else(|| PathBuf::from("./hsr_endgame_export"));
        return rebuild_hsr_visualizer(&out);
    }
    let (game, args, name_map_seed) = match cli.game {
        GameCommand::Hsr { command: HsrCommand::Export(args) } => {
            let name_map_seed = args.name_map_seed.clone();
            (Game::Hsr, args.effective(), name_map_seed)
        }
        GameCommand::Zzz { command: ZzzCommand::Export(args) } => {
            (Game::Zzz, args.effective(), None)
        }
        _ => bail!("this command's Rust implementation is registered but not yet enabled; use the Python compatibility command during staged migration"),
    };
    let revision = "main";
    let request = ExportRequest {
        schema_version: EXPORT_REQUEST_SCHEMA_VERSION,
        game,
        modes: args
            .modes
            .split(',')
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .map(|value| GameMode::parse(game, value))
            .collect::<miho_core::Result<Vec<_>>>()?,
        date_range: DateRange {
            from: Some(parse_cli_date(&args.from_date)?),
            to: Some(parse_cli_date(&args.to_date)?),
        },
        dataset: DatasetRef {
            repo_id: args.repo_id.clone(),
            revision: revision.into(),
        },
        features: FeatureFlags {
            hf_teams: args.toggles[0],
            prydwen_visible: args.toggles[1],
            prydwen_tier: args.toggles[2],
            official_names: args.toggles[3],
        },
        prydwen_top_n: args.prydwen_top_n,
        name_map_seed,
        history: HistoryPolicy::MergeExisting,
        workbook: WorkbookPolicy::BestEffort,
    };
    #[cfg(debug_assertions)]
    let offline_fixture = std::env::var_os("MIHO_OFFLINE_FIXTURE");
    #[cfg(not(debug_assertions))]
    let offline_fixture: Option<std::ffi::OsString> = None;

    let mut run = if let Some(path) = offline_fixture {
        let fixture_path = PathBuf::from(path);
        let fixture = OfflineFixture::load(&fixture_path)?;
        if fixture.manifest.game != game {
            bail!("offline fixture game does not match requested game");
        }
        let context = ExportContext {
            fetched_at: Utc::now(),
            fetch_policy: FetchPolicy::Fixture,
            cache_root: fixture_path.clone(),
            output_root: args.out.clone(),
            existing_output_root: Some(args.out.clone()),
            zzz_phase_overrides: zzz_phase_override_path(game, &args.out),
        };
        let run = match game {
            Game::Hsr => {
                let supplemental_root = std::env::var_os("MIHO_HSR_SUPPLEMENTAL_FIXTURE")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| fixture_path.join("supplemental"));
                let supplemental =
                    HsrFixtureSupplementalSource::new(supplemental_root, context.fetched_at);
                run_hsr_export_v1(&fixture, &supplemental, &request, &context).await?
            }
            Game::Zzz => {
                let supplemental_root = std::env::var_os("MIHO_ZZZ_SUPPLEMENTAL_FIXTURE")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| fixture_path.join("supplemental"));
                let supplemental =
                    ZzzFixtureSupplementalSource::new(supplemental_root, context.fetched_at);
                run_zzz_export_v1(&fixture, &supplemental, &request, &context).await?
            }
        };
        eprintln!("fixture mode: {}", fixture_path.display());
        run
    } else {
        if let Some(message) = online_export_gate(game) {
            bail!("{message}");
        }
        let cache_root = cache_root(game, &args.repo_id, revision);
        let source = HfSnapshotSource::new(
            HuggingFaceRepo::new(&args.repo_id, revision),
            HttpClient::new(StdDuration::from_secs(60), 2)?,
            &cache_root,
            FetchMode::Online,
        );
        let context = ExportContext {
            fetched_at: Utc::now(),
            fetch_policy: FetchPolicy::Online,
            cache_root: cache_root.clone(),
            output_root: args.out.clone(),
            existing_output_root: Some(args.out.clone()),
            zzz_phase_overrides: zzz_phase_override_path(game, &args.out),
        };
        match game {
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
        }
    };
    if game == Game::Hsr {
        attach_hsr_visualizer_from_output(&mut run.bundle, &args.out)?;
        run.bundle.refresh_manifest("artifact_manifest.json")?;
    }
    for diagnostic in &run.diagnostics {
        match diagnostic.severity {
            DiagnosticSeverity::Warning => eprintln!("warning: {}", diagnostic.message),
            DiagnosticSeverity::RecoverableError => {
                eprintln!("recoverable error: {}", diagnostic.message)
            }
        }
    }
    if game == Game::Hsr {
        write_bundle_transactionally(&args.out, &run.bundle)?;
    } else {
        run.bundle.write_to(&args.out)?;
    }
    Ok(())
}

fn online_export_gate(game: Game) -> Option<&'static str> {
    match game {
        Game::Hsr => None,
        Game::Zzz => Some(
            "ZZZ supplemental sources are migrated and Workbook export now passes compatibility checks, but online export remains gated until visualizer artifacts pass the complete-directory compatibility check; use the Python compatibility command",
        ),
    }
}

fn rebuild_hsr_visualizer(out: &Path) -> anyhow::Result<()> {
    validate_output_root(out)?;
    let mut bundle = load_existing_output(out)?;
    attach_hsr_visualizer_from_output(&mut bundle, out)?;
    bundle.refresh_manifest("artifact_manifest.json")?;
    write_bundle_transactionally(out, &bundle)?;
    Ok(())
}

fn attach_hsr_visualizer_from_output(
    bundle: &mut miho_core::output::ArtifactBundle,
    out: &Path,
) -> anyhow::Result<()> {
    validate_optional_directory(out)?;
    validate_optional_directory(&out.join("visualizer"))?;
    let avatars = read_existing_hsr_avatars(out)?;
    for path in hsr_banner_candidates(out) {
        let Some(bytes) = read_json_object_candidate(&path)? else {
            continue;
        };
        let mut context = hsr_visualizer_context(&avatars)?;
        context.add_sidecar_bytes("hsr_banner_plan.json", bytes)?;
        match attach_hsr_visualizer(bundle, &context) {
            Ok(()) => return Ok(()),
            Err(MihoError::Json { path, .. }) if path == Path::new("hsr_banner_plan.json") => {}
            Err(error) => return Err(error.into()),
        }
    }

    let context = hsr_visualizer_context(&avatars)?;
    attach_hsr_visualizer(bundle, &context)?;
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
    let stage = create_transaction_stage(parent, name)?;
    let prepare = (|| -> anyhow::Result<()> {
        if old_exists {
            copy_directory_contents(out, &stage)?;
        }
        remove_staged_visualizer(&stage)?;
        remove_staged_manifest(&stage)?;
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

    if !old_exists {
        if let Err(error) = fs::rename(&stage, out) {
            let _ = fs::remove_dir_all(&stage);
            return Err(error.into());
        }
        return Ok(());
    }

    let backup = unused_transaction_sibling(parent, name, "backup")?;
    if let Err(error) = fs::rename(out, &backup) {
        let _ = fs::remove_dir_all(&stage);
        return Err(error.into());
    }
    if let Err(install_error) = fs::rename(&stage, out) {
        let rollback = fs::rename(&backup, out);
        let _ = fs::remove_dir_all(&stage);
        return match rollback {
            Ok(()) => Err(install_error.into()),
            Err(rollback_error) => Err(anyhow::anyhow!(
                "output install failed ({install_error}); rollback also failed ({rollback_error}); old output remains at {}",
                backup.display()
            )),
        };
    }
    fs::remove_dir_all(backup)?;
    Ok(())
}

fn create_transaction_stage(parent: &Path, name: &std::ffi::OsStr) -> anyhow::Result<PathBuf> {
    loop {
        let stage = transaction_sibling(parent, name, "stage");
        match fs::create_dir(&stage) {
            Ok(()) => return Ok(stage),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error.into()),
        }
    }
}

fn unused_transaction_sibling(
    parent: &Path,
    name: &std::ffi::OsStr,
    kind: &str,
) -> anyhow::Result<PathBuf> {
    loop {
        let path = transaction_sibling(parent, name, kind);
        match fs::symlink_metadata(&path) {
            Ok(_) => continue,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(path),
            Err(error) => return Err(error.into()),
        }
    }
}

fn transaction_sibling(parent: &Path, name: &std::ffi::OsStr, kind: &str) -> PathBuf {
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

fn load_existing_output(out: &Path) -> anyhow::Result<miho_core::output::ArtifactBundle> {
    fn visit(
        root: &Path,
        current: &Path,
        bundle: &mut miho_core::output::ArtifactBundle,
    ) -> anyhow::Result<()> {
        for entry in fs::read_dir(current)? {
            let entry = entry?;
            let path = entry.path();
            let relative = path.strip_prefix(root)?;
            let file_type = entry.file_type()?;
            if relative == Path::new("visualizer")
                || relative == Path::new("artifact_manifest.json")
            {
                continue;
            }
            if file_type.is_symlink() {
                bail!("refusing symlink in existing output: {}", path.display());
            }
            if file_type.is_dir() {
                visit(root, &path, bundle)?;
            } else if file_type.is_file() {
                bundle.add_bytes(relative, fs::read(&path)?)?;
            } else {
                bail!("unsupported artifact type: {}", path.display());
            }
        }
        Ok(())
    }

    let mut bundle = miho_core::output::ArtifactBundle::default();
    visit(out, out, &mut bundle)?;
    Ok(bundle)
}

fn read_existing_hsr_avatars(out: &Path) -> anyhow::Result<Vec<(String, Vec<u8>)>> {
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

fn hsr_visualizer_context(avatars: &[(String, Vec<u8>)]) -> anyhow::Result<VisualizerContext> {
    let mut context = VisualizerContext::new(Local::now().date_naive());
    for (slug, bytes) in avatars {
        context.add_avatar_webp(slug, bytes.clone())?;
    }
    Ok(context)
}

fn hsr_banner_candidates(out: &Path) -> Vec<PathBuf> {
    let mut candidates = vec![out.join("hsr_banner_plan.json")];
    if let Some(parent) = out.parent() {
        candidates.push(parent.join("configs/hsr_banner_plan.json"));
    }
    candidates.push(PathBuf::from("configs/hsr_banner_plan.json"));
    candidates
}

fn read_json_object_candidate(path: &Path) -> anyhow::Result<Option<Vec<u8>>> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    let text = match std::str::from_utf8(&bytes) {
        Ok(text) => text.trim(),
        Err(_) => return Ok(None),
    };
    Ok((text.starts_with('{') && text.ends_with('}')).then_some(bytes))
}

fn cache_root(game: Game, repo_id: &str, revision: &str) -> PathBuf {
    let base = std::env::var_os("MIHO_CACHE_ROOT")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("LOCALAPPDATA").map(|v| PathBuf::from(v).join("miho-endgame/cache"))
        })
        .unwrap_or_else(|| PathBuf::from(".miho/cache"));
    cache_root_from(&base, game, repo_id, revision)
}

fn zzz_phase_override_path(game: Game, output_root: &std::path::Path) -> Option<PathBuf> {
    if game != Game::Zzz {
        return None;
    }
    let mut candidates = vec![output_root.join("zzz_endgame_phase_overrides.json")];
    if let Some(parent) = output_root.parent() {
        candidates.push(parent.join("configs/zzz_endgame_phase_overrides.json"));
    }
    if let Ok(current) = std::env::current_dir() {
        candidates.push(current.join("configs/zzz_endgame_phase_overrides.json"));
    }
    first_valid_phase_override_path(candidates)
}

fn cache_root_from(base: &std::path::Path, game: Game, repo_id: &str, revision: &str) -> PathBuf {
    base.join(match game {
        Game::Hsr => "hsr",
        Game::Zzz => "zzz",
    })
    .join(safe_cache_component(repo_id))
    .join(safe_cache_component(revision))
}

fn safe_cache_component(value: &str) -> String {
    let value = value
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.') {
                c
            } else {
                '_'
            }
        })
        .collect::<String>();
    if value.is_empty() || value == "." || value == ".." {
        "_".into()
    } else {
        value
    }
}

fn parse_cli_date(value: &str) -> anyhow::Result<chrono::NaiveDate> {
    let normalized = parse_date(value);
    chrono::NaiveDate::parse_from_str(&normalized, "%Y-%m-%d")
        .map_err(|_| anyhow::anyhow!("invalid date: {value}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    #[test]
    fn command_tree_is_valid() {
        Cli::command().debug_assert();
    }

    #[test]
    fn game_help_exposes_only_valid_commands() {
        let mut command = Cli::command();
        let hsr = command.find_subcommand_mut("hsr").unwrap();
        let hsr_names = hsr
            .get_subcommands()
            .map(|v| v.get_name())
            .collect::<Vec<_>>();
        assert_eq!(hsr_names, ["export", "visualizer"]);
        let zzz = Cli::command();
        let zzz_names = zzz
            .find_subcommand("zzz")
            .unwrap()
            .get_subcommands()
            .map(|v| v.get_name())
            .collect::<Vec<_>>();
        assert!(zzz_names.contains(&"decision") && zzz_names.contains(&"serve"));
    }

    #[test]
    fn export_defaults_match_python_contract() {
        let hsr = Cli::try_parse_from(["miho", "hsr", "export"]).unwrap();
        let GameCommand::Hsr {
            command: HsrCommand::Export(args),
        } = hsr.game
        else {
            panic!("expected HSR export")
        };
        let effective = args.effective();
        assert_eq!(effective.out, PathBuf::from("./hsr_endgame_export"));
        assert_eq!(effective.modes, "moc,pf,as,aa");
        assert_eq!(effective.repo_id, "LvlUrArti/MocDataProcessed");
        assert_eq!(effective.prydwen_top_n, 100);
        assert_eq!(effective.toggles, [true; 4]);

        let zzz = Cli::try_parse_from(["miho", "zzz", "export"]).unwrap();
        let GameCommand::Zzz {
            command: ZzzCommand::Export(args),
        } = zzz.game
        else {
            panic!("expected ZZZ export")
        };
        let effective = args.effective();
        assert_eq!(effective.out, PathBuf::from("./zzz_endgame_export"));
        assert_eq!(effective.modes, "sd,da");
        assert_eq!(effective.repo_id, "LvlUrArti/ShiyuDataProcessed");
        assert_eq!(effective.prydwen_top_n, 100);
    }

    #[test]
    fn python_style_boolean_pairs_are_supported_and_conflict() {
        let cli = Cli::try_parse_from(["miho", "zzz", "export", "--no-include-teams"]).unwrap();
        let GameCommand::Zzz {
            command: ZzzCommand::Export(args),
        } = cli.game
        else {
            panic!("expected export")
        };
        assert!(!args.effective().toggles[0]);
        assert!(Cli::try_parse_from([
            "miho",
            "zzz",
            "export",
            "--include-teams",
            "--no-include-teams"
        ])
        .is_err());

        let cli = Cli::try_parse_from(["miho", "zzz", "evidence", "--box", "box.json"]).unwrap();
        let GameCommand::Zzz {
            command: ZzzCommand::Evidence(args),
        } = cli.game
        else {
            panic!("expected evidence")
        };
        assert!(!args.effective_include_missing());
    }

    #[test]
    fn zzz_report_defaults_match_python_contract() {
        let cli = Cli::try_parse_from(["miho", "zzz", "pull-value", "--box", "box.json"]).unwrap();
        let GameCommand::Zzz {
            command: ZzzCommand::PullValue(args),
        } = cli.game
        else {
            panic!("expected pull-value")
        };
        assert_eq!(args.out, PathBuf::from("./zzz_endgame_export"));
        assert_eq!(args.plan, PathBuf::from("./configs/zzz_banner_plan.json"));
        assert_eq!(args.plan_status, "current,next");
        assert_eq!(
            args.decision_baseline,
            PathBuf::from("./configs/zzz_decision_baseline.json")
        );
    }

    #[test]
    fn hsr_visualizer_default_matches_python_contract() {
        let cli = Cli::try_parse_from(["miho", "hsr", "visualizer"]).unwrap();
        let GameCommand::Hsr {
            command: HsrCommand::Visualizer(args),
        } = cli.game
        else {
            panic!("expected HSR visualizer")
        };
        assert_eq!(
            args.out
                .unwrap_or_else(|| PathBuf::from("./hsr_endgame_export")),
            PathBuf::from("./hsr_endgame_export")
        );
    }

    #[test]
    fn online_gate_is_lifted_only_for_hsr() {
        assert!(online_export_gate(Game::Hsr).is_none());
        assert!(online_export_gate(Game::Zzz)
            .unwrap()
            .contains("visualizer artifacts"));
    }

    #[tokio::test]
    async fn unported_command_keeps_explicit_gate() {
        let cli = Cli::try_parse_from(["miho", "zzz", "visualizer"]).unwrap();
        assert!(execute(cli)
            .await
            .unwrap_err()
            .to_string()
            .contains("not yet enabled"));
    }

    #[test]
    fn cache_path_is_safe_and_isolated_by_repo_and_revision() {
        let base = PathBuf::from("cache-root");
        let first = cache_root_from(&base, Game::Hsr, "owner/repo", "feature/test");
        let second = cache_root_from(&base, Game::Hsr, "owner/other", "main");
        assert_eq!(first, base.join("hsr/owner_repo/feature_test"));
        assert_ne!(first, second);
        assert_eq!(safe_cache_component(".."), "_");
        assert_eq!(safe_cache_component(""), "_");
    }

    #[test]
    fn zzz_phase_override_skips_a_broken_higher_priority_candidate() {
        let root =
            std::env::temp_dir().join(format!("miho-cli-phase-override-{}", std::process::id()));
        let out = root.join("out");
        let fallback = root.join("configs/zzz_endgame_phase_overrides.json");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&out).unwrap();
        std::fs::create_dir_all(fallback.parent().unwrap()).unwrap();
        std::fs::write(out.join("zzz_endgame_phase_overrides.json"), "{broken").unwrap();
        std::fs::write(&fallback, r#"{"phases":[]}"#).unwrap();

        assert_eq!(zzz_phase_override_path(Game::Zzz, &out), Some(fallback));
        std::fs::remove_dir_all(root).unwrap();
    }
}
