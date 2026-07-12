use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::Duration as StdDuration,
};

use anyhow::{bail, Context};
use chrono::{Duration, Local, NaiveDateTime, Timelike, Utc};
use clap::{Args, Parser, Subcommand, ValueEnum};
use miho_core::{
    atomic,
    contract::{
        DatasetRef, DateRange, DiagnosticSeverity, ExportContext, FeatureFlags, FetchPolicy,
        GameMode, HistoryPolicy, WorkbookPolicy, EXPORT_REQUEST_SCHEMA_VERSION,
    },
    decision_legacy::{
        build_decision_legacy_v0, render_decision_json_legacy_v0,
        render_decision_markdown_legacy_v0, DecisionLegacyContextV0, DecisionLegacyInputsV0,
        DecisionLegacyRequestV0, DECISION_LEGACY_METHOD,
    },
    evidence::{
        build_evidence_bundle_v1, render_aggregate_csv_v1, render_coverage_markdown_v1,
        EvidenceContextV1, EvidenceGameV1, EvidenceInputsV1, EvidenceRequestV1,
    },
    hf::HuggingFaceRepo,
    hsr_supplemental::{HsrFixtureSupplementalSource, HsrHttpSupplementalSource},
    hsr_visualizer::attach_hsr_visualizer,
    network::{FetchMode, HttpClient},
    normalize::parse_date,
    pipeline::{run_hsr_export_v1, run_zzz_export_v1, ExportRequest, Game, OfflineFixture},
    source::HfSnapshotSource,
    visualizer::{attach_visualizer_hub, validate_json_surrogate_escapes, VisualizerContext},
    zzz_enrichment::first_valid_phase_override_path,
    zzz_supplemental::{ZzzFixtureSupplementalSource, ZzzHttpSupplementalSource},
    zzz_visualizer::attach_zzz_visualizer,
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
    #[command(about = "Build legacy-v0 compatibility cards; not formal evidence-first advice")]
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
    #[arg(long, value_enum)]
    method: DecisionMethodArg,
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "./zzz_endgame_export")]
    out: PathBuf,
    #[arg(long, default_value = "./configs/zzz_decision_rules.yaml")]
    rules: PathBuf,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum)]
enum DecisionMethodArg {
    #[value(name = "legacy-v0")]
    LegacyV0,
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

impl Cli {
    fn failure_prefix(&self) -> &'static str {
        match &self.game {
            GameCommand::Hsr {
                command: HsrCommand::Export(_),
            }
            | GameCommand::Zzz {
                command: ZzzCommand::Export(_),
            } => "export",
            GameCommand::Hsr {
                command: HsrCommand::Visualizer(_),
            }
            | GameCommand::Zzz {
                command: ZzzCommand::Visualizer(_),
            } => "visualizer",
            GameCommand::Zzz {
                command: ZzzCommand::Decision(_),
            } => "decision",
            GameCommand::Zzz {
                command: ZzzCommand::Evidence(_),
            } => "evidence",
            GameCommand::Zzz {
                command: ZzzCommand::Coverage(_),
            } => "coverage",
            GameCommand::Zzz {
                command: ZzzCommand::PullValue(_),
            } => "pull-value",
            GameCommand::Zzz {
                command: ZzzCommand::ReviewPacket(_),
            } => "review-packet",
            GameCommand::Zzz {
                command: ZzzCommand::Serve(_),
            } => "serve",
        }
    }
}

struct ReportInvocation {
    cwd: PathBuf,
    local_datetime: NaiveDateTime,
}

impl ReportInvocation {
    fn capture() -> anyhow::Result<Self> {
        let cwd = std::env::current_dir().context("cannot capture report working directory")?;
        #[cfg(debug_assertions)]
        let now = if let Some(value) = std::env::var_os("MIHO_REPORT_LOCAL_DATETIME") {
            NaiveDateTime::parse_from_str(&value.to_string_lossy(), "%Y-%m-%dT%H:%M:%S%.f")
                .context("invalid MIHO_REPORT_LOCAL_DATETIME")?
        } else {
            Local::now().naive_local()
        };
        #[cfg(not(debug_assertions))]
        let now = Local::now().naive_local();
        let nanos = now.nanosecond() / 1_000 * 1_000;
        let local_datetime = now
            .with_nanosecond(nanos)
            .context("cannot truncate report local datetime to microseconds")?;
        Ok(Self {
            cwd,
            local_datetime,
        })
    }

    fn resolve(&self, path: &Path) -> PathBuf {
        let joined = if path.is_absolute() {
            path.to_path_buf()
        } else {
            self.cwd.join(path)
        };
        let mut normalized = PathBuf::new();
        for component in joined.components() {
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
}

fn run_zzz_decision(args: &DecisionArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    if args.method != DecisionMethodArg::LegacyV0 {
        bail!("unsupported decision method");
    }
    let data_dir = invocation.resolve(&args.out);
    let optional = |name: &str| read_optional_report_input(&data_dir.join(name));
    let rules_path = invocation.resolve(&args.rules);
    let inputs = DecisionLegacyInputsV0 {
        box_config: read_report_input(&invocation.resolve(&args.box_path))?,
        rules_config: read_optional_report_input(&rules_path)?,
        tier_current_csv: optional("prydwen_tier_current.csv")?,
        tier_history_csv: optional("prydwen_tier_history.csv")?,
        usage_csv: optional("character_usage_long.csv")?,
        team_raw_csv: optional("team_rank_raw.csv")?,
        name_map_csv: optional("name_map.csv")?,
        changelog_history_csv: optional("prydwen_tier_changelog_history.csv")?,
    };
    let result = build_decision_legacy_v0(
        &inputs,
        &DecisionLegacyRequestV0 {
            method: DECISION_LEGACY_METHOD.to_owned(),
        },
    )?;
    let json = render_decision_json_legacy_v0(&result)?;
    let json =
        String::from_utf8(json).context("legacy decision JSON renderer returned invalid UTF-8")?;
    let markdown = render_decision_markdown_legacy_v0(
        &result,
        &DecisionLegacyContextV0 {
            local_datetime: invocation.local_datetime,
        },
    );
    atomic::write_batch(&[
        (
            data_dir.join("decision_cards.json"),
            platform_text_bytes(&json),
        ),
        (
            data_dir.join("decision_report.md"),
            platform_text_bytes(&markdown),
        ),
    ])?;
    eprintln!(
        "legacy-v0 compatibility only: formal evidence-first advice is provided by pull-value"
    );
    Ok(())
}

fn run_zzz_evidence(args: &EvidenceArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    let data_dir = invocation.resolve(&args.out);
    let inputs = load_evidence_inputs(
        &data_dir,
        &invocation.resolve(&args.box_path),
        args.plan.as_deref().map(|path| invocation.resolve(path)),
    )?;
    let (default_min_a_app_rate, min_a_app_rate_by_mode) =
        parse_min_a_app_rate(&args.min_a_app_rate)?;
    let request = EvidenceRequestV1 {
        game: EvidenceGameV1::Zzz,
        explicit_planned_slugs: split_report_values(args.planned_slugs.as_deref()),
        plan_statuses: split_report_values(Some(&args.plan_status)),
        include_missing: args.include_missing && !args.no_include_missing,
        default_min_a_app_rate,
        min_a_app_rate_by_mode,
        ..EvidenceRequestV1::default()
    };
    let context = EvidenceContextV1 {
        local_datetime: invocation.local_datetime,
    };
    let bundle = build_evidence_bundle_v1(&inputs, &request, &context)?;
    let team_source = data_dir.join("team_rank_dedup_unordered.csv");
    let markdown = render_coverage_markdown_v1(
        &bundle.target,
        "绝区零目标账号证据池队伍覆盖",
        &team_source.to_string_lossy(),
        args.limit,
    );
    let output = args
        .output
        .as_deref()
        .map(|path| invocation.resolve(path))
        .unwrap_or_else(|| data_dir.join("evidence_pool_summary.md"));
    atomic::write_batch(&[(output, platform_text_bytes(&markdown))])?;
    Ok(())
}

fn run_zzz_coverage(args: &CoverageArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    let data_dir = invocation.resolve(&args.out);
    let inputs = load_evidence_inputs(
        &data_dir,
        &invocation.resolve(&args.box_path),
        args.plan.as_deref().map(|path| invocation.resolve(path)),
    )?;
    let (default_min_a_app_rate, min_a_app_rate_by_mode) =
        parse_min_a_app_rate(&args.min_a_app_rate)?;
    let request = EvidenceRequestV1 {
        game: EvidenceGameV1::Zzz,
        explicit_planned_slugs: split_report_values(args.planned_slugs.as_deref()),
        plan_statuses: split_report_values(Some(&args.plan_status)),
        default_min_a_app_rate,
        min_a_app_rate_by_mode,
        ..EvidenceRequestV1::default()
    };
    let context = EvidenceContextV1 {
        local_datetime: invocation.local_datetime,
    };
    let bundle = build_evidence_bundle_v1(&inputs, &request, &context)?;
    let team_source = data_dir.join("team_rank_dedup_unordered.csv");
    let team_source = team_source.to_string_lossy();
    let current = render_coverage_markdown_v1(
        &bundle.current,
        "当前 Box 队伍覆盖",
        &team_source,
        args.limit,
    );
    let target = render_coverage_markdown_v1(
        &bundle.target,
        "目标 Box 队伍覆盖",
        &team_source,
        args.limit,
    );
    let aggregate = render_aggregate_csv_v1(&bundle.target.aggregates)?;
    let current_output = args
        .current_output
        .as_deref()
        .map(|path| invocation.resolve(path))
        .unwrap_or_else(|| data_dir.join("current_box_team_coverage.md"));
    let target_output = args
        .target_output
        .as_deref()
        .map(|path| invocation.resolve(path))
        .unwrap_or_else(|| data_dir.join("target_box_team_coverage.md"));
    let aggregate_output = args
        .aggregate_output
        .as_deref()
        .map(|path| invocation.resolve(path))
        .unwrap_or_else(|| data_dir.join("team_signature_aggregates.csv"));
    atomic::write_batch(&[
        (current_output, platform_text_bytes(&current)),
        (target_output, platform_text_bytes(&target)),
        (aggregate_output, aggregate),
    ])?;
    Ok(())
}

fn load_evidence_inputs(
    data_dir: &Path,
    box_path: &Path,
    plan_path: Option<PathBuf>,
) -> anyhow::Result<EvidenceInputsV1> {
    let team_path = data_dir.join("team_rank_dedup_unordered.csv");
    Ok(EvidenceInputsV1 {
        team_rank_dedup_unordered_csv: read_report_input(&team_path)?,
        name_map_csv: read_optional_report_input(&data_dir.join("name_map.csv"))?,
        tier_csv: read_optional_report_input(&data_dir.join("prydwen_tier_current.csv"))?,
        box_json: read_report_input(box_path)?,
        banner_plan_json: plan_path.as_deref().map(read_report_input).transpose()?,
    })
}

fn read_report_input(path: &Path) -> anyhow::Result<Vec<u8>> {
    fs::read(path).with_context(|| format!("cannot read report input {}", path.display()))
}

fn read_optional_report_input(path: &Path) -> anyhow::Result<Option<Vec<u8>>> {
    if path.exists() {
        read_report_input(path).map(Some)
    } else {
        Ok(None)
    }
}

fn split_report_values(value: Option<&str>) -> Vec<String> {
    value
        .into_iter()
        .flat_map(|text| text.split([',', ';']))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect()
}

fn parse_min_a_app_rate(value: &str) -> anyhow::Result<(f64, BTreeMap<String, f64>)> {
    let text = value.trim();
    if text.is_empty() {
        return Ok((10.0, BTreeMap::new()));
    }
    if !text.contains('=') {
        let number = parse_non_negative_finite_threshold(text, "threshold")?;
        return Ok((number, BTreeMap::new()));
    }
    let mut default = 10.0;
    let mut values = BTreeMap::new();
    for item in text
        .split([',', ';'])
        .map(str::trim)
        .filter(|v| !v.is_empty())
    {
        let (key, raw_number) = item
            .split_once('=')
            .with_context(|| format!("invalid threshold item: {item}"))?;
        let mode = key.trim().to_ascii_lowercase();
        if mode.is_empty() {
            bail!("invalid threshold mode: {item}");
        }
        let number = parse_non_negative_finite_threshold(raw_number.trim(), item)?;
        if mode == "default" {
            default = number;
        }
        values.insert(mode, number);
    }
    if values.is_empty() {
        Ok((10.0, BTreeMap::new()))
    } else {
        Ok((default, values))
    }
}

fn parse_non_negative_finite_threshold(value: &str, label: &str) -> anyhow::Result<f64> {
    let number = value
        .parse::<f64>()
        .with_context(|| format!("invalid {label}: {value}"))?;
    if !number.is_finite() || number < 0.0 {
        bail!("invalid {label}: {value}");
    }
    Ok(number)
}

fn platform_text_bytes(text: &str) -> Vec<u8> {
    #[cfg(windows)]
    {
        text.replace('\n', "\r\n").into_bytes()
    }
    #[cfg(not(windows))]
    {
        text.as_bytes().to_vec()
    }
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    let failure_prefix = cli.failure_prefix();
    if let Err(error) = execute(cli).await {
        eprintln!("{failure_prefix} failed: {error}");
        std::process::exit(1);
    }
}

async fn execute(cli: Cli) -> anyhow::Result<()> {
    match &cli.game {
        GameCommand::Hsr {
            command: HsrCommand::Visualizer(args),
        } => {
            let out = args
                .out
                .clone()
                .unwrap_or_else(|| PathBuf::from("./hsr_endgame_export"));
            return rebuild_hsr_visualizer(&out);
        }
        GameCommand::Zzz {
            command: ZzzCommand::Visualizer(args),
        } => {
            let out = args
                .out
                .clone()
                .unwrap_or_else(|| PathBuf::from("./zzz_endgame_export"));
            return rebuild_zzz_visualizer(&out);
        }
        _ => {}
    }
    match &cli.game {
        GameCommand::Zzz {
            command: ZzzCommand::Decision(args),
        } => {
            let invocation = ReportInvocation::capture()?;
            return run_zzz_decision(args, &invocation);
        }
        GameCommand::Zzz {
            command: ZzzCommand::Evidence(args),
        } => {
            let invocation = ReportInvocation::capture()?;
            return run_zzz_evidence(args, &invocation);
        }
        GameCommand::Zzz {
            command: ZzzCommand::Coverage(args),
        } => {
            let invocation = ReportInvocation::capture()?;
            return run_zzz_coverage(args, &invocation);
        }
        _ => {}
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
    if game == Game::Zzz {
        validate_zzz_hub_preflight(&args.out)?;
    }
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
    match game {
        Game::Hsr => attach_hsr_visualizer_from_output(&mut run.bundle, &args.out)?,
        Game::Zzz => attach_zzz_visualizer_from_output(&mut run.bundle, &args.out)?,
    }
    run.bundle.refresh_manifest("artifact_manifest.json")?;
    for diagnostic in &run.diagnostics {
        match diagnostic.severity {
            DiagnosticSeverity::Warning => eprintln!("warning: {}", diagnostic.message),
            DiagnosticSeverity::RecoverableError => {
                eprintln!("recoverable error: {}", diagnostic.message)
            }
        }
    }
    write_bundle_transactionally(&args.out, &run.bundle)?;
    if game == Game::Zzz {
        write_zzz_hub(&args.out)?;
    }
    Ok(())
}

fn online_export_gate(_game: Game) -> Option<&'static str> {
    None
}

fn rebuild_hsr_visualizer(out: &Path) -> anyhow::Result<()> {
    validate_output_root(out)?;
    let mut bundle = load_existing_output(out, Game::Hsr)?;
    attach_hsr_visualizer_from_output(&mut bundle, out)?;
    bundle.refresh_manifest("artifact_manifest.json")?;
    write_bundle_transactionally(out, &bundle)?;
    Ok(())
}

fn rebuild_zzz_visualizer(out: &Path) -> anyhow::Result<()> {
    validate_zzz_hub_preflight(out)?;
    validate_output_root(out)?;
    let mut bundle = load_existing_output(out, Game::Zzz)?;
    attach_zzz_visualizer_from_output(&mut bundle, out)?;
    bundle.refresh_manifest("artifact_manifest.json")?;
    write_bundle_transactionally(out, &bundle)?;
    write_zzz_hub(out)?;
    Ok(())
}

fn attach_hsr_visualizer_from_output(
    bundle: &mut miho_core::output::ArtifactBundle,
    out: &Path,
) -> anyhow::Result<()> {
    validate_optional_directory(out)?;
    validate_optional_directory(&out.join("visualizer"))?;
    let avatars = read_existing_visualizer_avatars(out)?;
    for path in hsr_banner_candidates(out) {
        let Some(bytes) = read_json_object_candidate(&path)? else {
            continue;
        };
        let mut context = visualizer_context(&avatars)?;
        context.add_sidecar_bytes("hsr_banner_plan.json", bytes)?;
        match attach_hsr_visualizer(bundle, &context) {
            Ok(()) => return Ok(()),
            Err(MihoError::Json { path, .. }) if path == Path::new("hsr_banner_plan.json") => {}
            Err(error) => return Err(error.into()),
        }
    }

    let context = visualizer_context(&avatars)?;
    attach_hsr_visualizer(bundle, &context)?;
    Ok(())
}

fn attach_zzz_visualizer_from_output(
    bundle: &mut miho_core::output::ArtifactBundle,
    out: &Path,
) -> anyhow::Result<()> {
    validate_optional_directory(out)?;
    validate_optional_directory(&out.join("visualizer"))?;
    let avatars = read_existing_visualizer_avatars(out)?;
    let mut context = visualizer_context(&avatars)?;

    if let Some(bytes) = first_valid_phase_override_candidate(&zzz_phase_override_candidates(out))?
    {
        context.add_sidecar_bytes("zzz_endgame_phase_overrides.json", bytes)?;
    }
    if let Some(bytes) =
        first_valid_json_candidate(&zzz_banner_candidates(out), serde_json::Value::is_object)?
    {
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

fn write_zzz_hub(out: &Path) -> anyhow::Result<()> {
    validate_zzz_hub_preflight(out)?;
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
    attach_visualizer_hub(&mut bundle, "out", zzz_dir)?;
    write_clean_directory_transactionally(&workspace.join("visualizer"), &bundle)
}

fn validate_zzz_hub_preflight(out: &Path) -> anyhow::Result<()> {
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

    // Build the dynamic Hub in memory first so unsafe output segments are
    // rejected before either the export directory or its sibling Hub changes.
    let mut probe = miho_core::output::ArtifactBundle::default();
    attach_visualizer_hub(&mut probe, "out", zzz_dir)?;

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
                "Hub install failed ({install_error}); rollback also failed ({rollback_error}); old Hub remains at {}",
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
            } else {
                if !file_type.is_file() {
                    bail!("unsupported artifact type: {}", path.display());
                }
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

fn visualizer_context(avatars: &[(String, Vec<u8>)]) -> anyhow::Result<VisualizerContext> {
    let mut context = VisualizerContext::new_with_local_datetime(Local::now().naive_local());
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

fn zzz_phase_override_candidates(out: &Path) -> Vec<PathBuf> {
    let mut candidates = vec![out.join("zzz_endgame_phase_overrides.json")];
    if let Some(parent) = out.parent() {
        candidates.push(parent.join("configs/zzz_endgame_phase_overrides.json"));
    }
    candidates.push(PathBuf::from("configs/zzz_endgame_phase_overrides.json"));
    candidates
}

fn zzz_banner_candidates(out: &Path) -> Vec<PathBuf> {
    let mut candidates = vec![out.join("zzz_banner_plan.json")];
    if let Some(parent) = out.parent() {
        candidates.push(parent.join("configs/zzz_banner_plan.json"));
    }
    candidates.push(PathBuf::from("configs/zzz_banner_plan.json"));
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
    first_valid_phase_override_path(zzz_phase_override_candidates(output_root))
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
            assert!(
                is_legacy_managed_artifact(Game::Hsr, Path::new(path)),
                "HSR allowlist omitted {path}"
            );
        }
        for path in [
            "zzz_endgame_dataset.xlsx",
            "export_report.md",
            "prydwen_tier_usage_trend.csv",
            "raw/hf/3.0.1/sd/comps/5-1_combined.json",
            "raw/prydwen/da.html",
            "raw/prydwen_tier/tier-list_20260707.html",
            "raw/hoyowiki/zzz_bangboo_zh-cn.json",
        ] {
            assert!(
                is_legacy_managed_artifact(Game::Zzz, Path::new(path)),
                "ZZZ allowlist omitted {path}"
            );
        }
        for (game, path) in [
            (Game::Hsr, "keep-me.txt"),
            (Game::Zzz, "notes/keep-me.txt"),
            (Game::Hsr, "raw/prydwen/keep-me.html"),
            (Game::Zzz, "raw/hoyowiki/keep-me.json"),
            (Game::Zzz, "charts/prydwen_tier_usage/foreign.svg"),
        ] {
            assert!(
                !is_legacy_managed_artifact(game, Path::new(path)),
                "unknown file was promoted: {path}"
            );
        }
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

        assert!(Cli::try_parse_from(["miho", "zzz", "decision", "--box", "box.json"]).is_err());
        let decision = Cli::try_parse_from([
            "miho",
            "zzz",
            "decision",
            "--method",
            "legacy-v0",
            "--box",
            "box.json",
        ])
        .unwrap();
        let GameCommand::Zzz {
            command: ZzzCommand::Decision(args),
        } = decision.game
        else {
            panic!("expected decision")
        };
        assert_eq!(args.method, DecisionMethodArg::LegacyV0);
    }

    #[test]
    fn report_thresholds_match_python_scalar_and_mode_syntax() {
        assert_eq!(parse_min_a_app_rate("5").unwrap(), (5.0, BTreeMap::new()));
        let (default, modes) = parse_min_a_app_rate("sd=5; da=10, default=7").unwrap();
        assert_eq!(default, 7.0);
        assert_eq!(modes.get("sd"), Some(&5.0));
        assert_eq!(modes.get("da"), Some(&10.0));
        assert_eq!(modes.get("default"), Some(&7.0));
        assert!(parse_min_a_app_rate("sd=NaN").is_err());
        assert!(parse_min_a_app_rate("sd=-1").is_err());
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
    fn zzz_visualizer_default_matches_python_contract() {
        let cli = Cli::try_parse_from(["miho", "zzz", "visualizer"]).unwrap();
        let GameCommand::Zzz {
            command: ZzzCommand::Visualizer(args),
        } = cli.game
        else {
            panic!("expected ZZZ visualizer")
        };
        assert_eq!(
            args.out
                .unwrap_or_else(|| PathBuf::from("./zzz_endgame_export")),
            PathBuf::from("./zzz_endgame_export")
        );
    }

    #[test]
    fn online_export_gate_is_lifted_for_both_games() {
        assert!(online_export_gate(Game::Hsr).is_none());
        assert!(online_export_gate(Game::Zzz).is_none());
    }

    #[tokio::test]
    async fn unported_command_keeps_explicit_gate() {
        let cli = Cli::try_parse_from(["miho", "zzz", "serve"]).unwrap();
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
        std::fs::create_dir(out.join("zzz_endgame_phase_overrides.json")).unwrap();
        std::fs::write(&fallback, r#"{"phases":[]}"#).unwrap();

        assert_eq!(zzz_phase_override_path(Game::Zzz, &out), Some(fallback));
        std::fs::remove_dir_all(root).unwrap();
    }
}
