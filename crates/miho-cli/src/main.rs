#![cfg_attr(
    all(feature = "automation-no-window", target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions, TryLockError},
    path::{Component, Path, PathBuf},
};

use anyhow::bail;
use chrono::{Duration, NaiveDate};
use clap::{Args, Parser, Subcommand, ValueEnum};
use miho_app::{
    begin_workspace_bootstrap_transaction_v1, bootstrap_workspace_v1,
    check_update_health_with_workspace_config_path_and_freshness_v1,
    commit_workspace_bootstrap_transaction_v1, discard_workspace_bootstrap_transaction_v1,
    execute_export_observed_v1, execute_task_v1, execute_visualizer_v1, export_cache_root,
    finalize_workspace_bootstrap_transaction_v1, is_valid_update_attempt_id_v1,
    load_update_config_with_digest_v1, rollback_workspace_bootstrap_transaction_v1, run_update_v1,
    verify_workspace_bootstrap_transaction_v1, AppInvocation, CoverageTaskV1, DecisionTaskV1,
    EvidenceTaskV1, ExportInvocation, ExportObserver, ExportSourceV1, ExportTaskV1,
    FileUpdateReceiptStore, NativeUpdateExecutorV1, PullTaskV1, TaskFreshnessSummaryV1,
    TaskRequestV1, TaskSpecV1, UpdateArtifactV1, UpdateInvocationV1, UpdateRequestV1,
    UpdateStepContextV1, UpdateStepExecutor, UpdateStepFailureV1, UpdateStepFuture,
    UpdateStepKindV1, VisualizerTaskV1, WorkspaceBootstrapCompletedOperationV1,
    WorkspaceBootstrapRequestV1, WorkspaceBootstrapTransactionRequestV1, WorkspaceLayout,
    WorkspaceWriteLease,
};
use miho_core::{
    contract::{DiagnosticSeverity, FeatureFlags, GameMode},
    normalize::parse_date,
    pipeline::Game,
};
use sha2::{Digest, Sha256};

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
    Update {
        #[command(subcommand)]
        command: UpdateCommand,
    },
    Workspace {
        #[command(subcommand)]
        command: WorkspaceCommand,
    },
}

#[derive(Subcommand)]
enum UpdateCommand {
    Run(UpdateRunArgs),
    Health(UpdateHealthArgs),
}

#[derive(Subcommand)]
enum WorkspaceCommand {
    Bootstrap(WorkspaceBootstrapArgs),
    #[command(name = "bootstrap-transaction")]
    BootstrapTransaction {
        #[command(subcommand)]
        command: WorkspaceBootstrapTransactionCommand,
    },
}

#[derive(Args)]
struct WorkspaceBootstrapArgs {
    #[arg(long)]
    workspace: PathBuf,
}

#[derive(Subcommand)]
enum WorkspaceBootstrapTransactionCommand {
    Begin(WorkspaceBootstrapTransactionArgs),
    Verify(WorkspaceBootstrapTransactionArgs),
    Rollback(WorkspaceBootstrapTransactionArgs),
    Commit(WorkspaceBootstrapTransactionArgs),
    Discard(WorkspaceBootstrapTransactionArgs),
    Finalize(WorkspaceBootstrapFinalizeArgs),
}

#[derive(Args)]
struct WorkspaceBootstrapTransactionArgs {
    #[arg(long)]
    workspace: PathBuf,
    #[arg(long)]
    transaction: PathBuf,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum WorkspaceBootstrapCompletedOperationArg {
    Commit,
    Discard,
}

impl From<WorkspaceBootstrapCompletedOperationArg> for WorkspaceBootstrapCompletedOperationV1 {
    fn from(value: WorkspaceBootstrapCompletedOperationArg) -> Self {
        match value {
            WorkspaceBootstrapCompletedOperationArg::Commit => Self::Commit,
            WorkspaceBootstrapCompletedOperationArg::Discard => Self::Discard,
        }
    }
}

#[derive(Args)]
struct WorkspaceBootstrapFinalizeArgs {
    #[arg(long)]
    workspace: PathBuf,
    #[arg(long)]
    transaction: PathBuf,
    #[arg(long, value_enum)]
    completed_operation: WorkspaceBootstrapCompletedOperationArg,
}

#[derive(Args)]
struct UpdateRunArgs {
    #[arg(long)]
    workspace: PathBuf,
    #[arg(long, default_value = "configs/update_v1.json")]
    config: PathBuf,
    #[arg(long, action = clap::ArgAction::SetTrue)]
    skip_hsr: bool,
    #[arg(long, action = clap::ArgAction::SetTrue)]
    skip_zzz: bool,
    #[arg(long, action = clap::ArgAction::SetTrue)]
    force: bool,
    #[arg(long, value_parser = parse_update_attempt_id_v1)]
    attempt_id: Option<String>,
}

fn parse_update_attempt_id_v1(value: &str) -> Result<String, String> {
    if is_valid_update_attempt_id_v1(value) {
        Ok(value.to_owned())
    } else {
        Err("attempt ID must match [A-Za-z0-9_-]{1,96}".to_owned())
    }
}

#[derive(Args)]
struct UpdateHealthArgs {
    #[arg(long)]
    workspace: PathBuf,
    #[arg(long, default_value = "configs/update_v1.json")]
    config: PathBuf,
    #[arg(long, action = clap::ArgAction::SetTrue)]
    skip_hsr: bool,
    #[arg(long, action = clap::ArgAction::SetTrue)]
    skip_zzz: bool,
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
    fn effective(
        &self,
        defaults: (&str, &str, &str),
        toggles: &ExportToggles,
        today: NaiveDate,
    ) -> EffectiveExport {
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
    fn effective(&self, today: NaiveDate) -> EffectiveExport {
        self.common.effective(
            (
                "./hsr_endgame_export",
                "moc,pf,as,aa",
                "LvlUrArti/MocDataProcessed",
            ),
            &self.toggles,
            today,
        )
    }
}

impl ZzzExportArgs {
    fn effective(&self, today: NaiveDate) -> EffectiveExport {
        self.common.effective(
            (
                "./zzz_endgame_export",
                "sd,da",
                "LvlUrArti/ShiyuDataProcessed",
            ),
            &self.toggles,
            today,
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
            GameCommand::Update {
                command: UpdateCommand::Run(_) | UpdateCommand::Health(_),
            } => "update",
            GameCommand::Workspace {
                command:
                    WorkspaceCommand::Bootstrap(_) | WorkspaceCommand::BootstrapTransaction { .. },
            } => "workspace",
        }
    }
}

type ReportInvocation = AppInvocation;

fn execute_report_task(
    box_path: PathBuf,
    data_dir: PathBuf,
    task: TaskSpecV1,
    invocation: &ReportInvocation,
) -> anyhow::Result<()> {
    let output_workspace = report_writer_workspace(&task, &data_dir, invocation)?;
    let resolved_data_dir = invocation.resolve(&data_dir);
    let data_workspace = resolved_data_dir
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .ok_or_else(|| anyhow::anyhow!("workspace.write_unavailable"))?;
    let mut writer_workspaces = vec![output_workspace];
    if managed_update_workspace(data_workspace) {
        writer_workspaces.push(data_workspace.to_path_buf());
    }
    let mut canonical_workspaces = writer_workspaces
        .into_iter()
        .map(|workspace| {
            fs::create_dir_all(&workspace)
                .map_err(|_| anyhow::anyhow!("workspace.write_unavailable"))?;
            fs::canonicalize(workspace).map_err(|_| anyhow::anyhow!("workspace.write_unavailable"))
        })
        .collect::<anyhow::Result<Vec<_>>>()?;
    canonical_workspaces.sort_by_key(|path| path.to_string_lossy().to_lowercase());
    canonical_workspaces.dedup_by(|left, right| {
        left.to_string_lossy()
            .eq_ignore_ascii_case(&right.to_string_lossy())
    });
    let _leases = canonical_workspaces
        .iter()
        .map(|workspace| {
            WorkspaceWriteLease::acquire(workspace).map_err(|error| anyhow::anyhow!(error.code()))
        })
        .collect::<anyhow::Result<Vec<_>>>()?;
    let receipt = execute_task_v1(
        &TaskRequestV1::new(WorkspaceLayout { data_dir, box_path }, task),
        invocation,
    )?;
    for notice in receipt.notices {
        eprintln!("{notice}");
    }
    Ok(())
}

fn managed_update_workspace(workspace: &Path) -> bool {
    workspace.join("configs/update_v1.json").is_file()
        || workspace.join(".miho/update-state-v1.json").is_file()
        || workspace.join(".miho/update-attempts").is_dir()
}

fn report_writer_workspace(
    task: &TaskSpecV1,
    data_dir: &Path,
    invocation: &ReportInvocation,
) -> anyhow::Result<PathBuf> {
    let data_dir = invocation.resolve(data_dir);
    let default_workspace = data_dir
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .ok_or_else(|| anyhow::anyhow!("workspace.write_unavailable"))?;
    let explicit_outputs = match task {
        TaskSpecV1::Decision(_) => Vec::new(),
        TaskSpecV1::Evidence(task) => task.output.iter().collect::<Vec<_>>(),
        TaskSpecV1::Coverage(task) => {
            let outputs = [
                task.current_output.as_ref(),
                task.target_output.as_ref(),
                task.aggregate_output.as_ref(),
            ];
            if outputs.iter().any(|output| output.is_none()) {
                let outside = outputs
                    .into_iter()
                    .flatten()
                    .any(|output| !invocation.resolve(output).starts_with(default_workspace));
                if outside {
                    bail!("workspace.write_unsafe");
                }
                return Ok(default_workspace.to_path_buf());
            }
            outputs.into_iter().flatten().collect::<Vec<_>>()
        }
        TaskSpecV1::PullValue(task) | TaskSpecV1::ReviewPacket(task) => {
            task.output.iter().collect::<Vec<_>>()
        }
    };
    if explicit_outputs.is_empty() {
        return Ok(default_workspace.to_path_buf());
    }
    let resolved_outputs = explicit_outputs
        .into_iter()
        .map(|output| invocation.resolve(output))
        .collect::<Vec<_>>();
    if resolved_outputs
        .iter()
        .all(|output| output.starts_with(default_workspace))
    {
        return Ok(default_workspace.to_path_buf());
    }
    let parents = resolved_outputs
        .into_iter()
        .map(|output| {
            output
                .parent()
                .filter(|path| !path.as_os_str().is_empty())
                .map(Path::to_path_buf)
                .ok_or_else(|| anyhow::anyhow!("workspace.write_unavailable"))
        })
        .collect::<anyhow::Result<Vec<_>>>()?;
    common_workspace(&parents).ok_or_else(|| anyhow::anyhow!("workspace.write_unsafe"))
}

fn common_workspace(paths: &[PathBuf]) -> Option<PathBuf> {
    let first = paths.first()?;
    first
        .ancestors()
        .find(|candidate| {
            candidate.parent().is_some() && paths.iter().all(|path| path.starts_with(candidate))
        })
        .map(Path::to_path_buf)
}

fn run_zzz_decision(args: &DecisionArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    let method = match args.method {
        DecisionMethodArg::LegacyV0 => "legacy-v0",
    };
    execute_report_task(
        args.box_path.clone(),
        args.out.clone(),
        TaskSpecV1::Decision(DecisionTaskV1 {
            method: method.to_owned(),
            rules_path: args.rules.clone(),
        }),
        invocation,
    )
}

fn run_zzz_evidence(args: &EvidenceArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    execute_report_task(
        args.box_path.clone(),
        args.out.clone(),
        TaskSpecV1::Evidence(EvidenceTaskV1 {
            planned_slugs: split_report_values(args.planned_slugs.as_deref()),
            plan_path: args.plan.clone(),
            plan_statuses: split_report_values(Some(&args.plan_status)),
            output: args.output.clone(),
            limit: args.limit,
            min_a_app_rate: args.min_a_app_rate.clone(),
            include_missing: args.include_missing && !args.no_include_missing,
        }),
        invocation,
    )
}

fn run_zzz_coverage(args: &CoverageArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    execute_report_task(
        args.box_path.clone(),
        args.out.clone(),
        TaskSpecV1::Coverage(CoverageTaskV1 {
            planned_slugs: split_report_values(args.planned_slugs.as_deref()),
            plan_path: args.plan.clone(),
            plan_statuses: split_report_values(Some(&args.plan_status)),
            limit: args.limit,
            min_a_app_rate: args.min_a_app_rate.clone(),
            current_output: args.current_output.clone(),
            target_output: args.target_output.clone(),
            aggregate_output: args.aggregate_output.clone(),
        }),
        invocation,
    )
}

fn run_zzz_pull_value(args: &PullValueArgs, invocation: &ReportInvocation) -> anyhow::Result<()> {
    run_zzz_pull_task(args, invocation, false)
}

fn run_zzz_review_packet(
    args: &PullValueArgs,
    invocation: &ReportInvocation,
) -> anyhow::Result<()> {
    run_zzz_pull_task(args, invocation, true)
}

fn run_zzz_pull_task(
    args: &PullValueArgs,
    invocation: &ReportInvocation,
    review_packet: bool,
) -> anyhow::Result<()> {
    let task = PullTaskV1 {
        plan_path: args.plan.clone(),
        plan_statuses: split_report_values(Some(&args.plan_status)),
        planned_slugs: split_report_values(args.planned_slugs.as_deref()),
        mechanism_notes_dir: args.mechanism_notes_dir.clone(),
        decision_baseline_path: args.decision_baseline.clone(),
        output: args.output.clone(),
    };
    let task = if review_packet {
        TaskSpecV1::ReviewPacket(task)
    } else {
        TaskSpecV1::PullValue(task)
    };
    execute_report_task(args.box_path.clone(), args.out.clone(), task, invocation)
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

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    let failure_prefix = cli.failure_prefix();
    if let Err(error) = execute(cli).await {
        eprintln!("{failure_prefix} failed: {error}");
        std::process::exit(1);
    }
}

struct CliExportObserver;

impl ExportObserver for CliExportObserver {
    fn fixture_mode(&self, path: &std::path::Path) {
        eprintln!("fixture mode: {}", path.display());
    }

    fn diagnostic(&self, diagnostic: &miho_core::contract::Diagnostic) {
        match diagnostic.severity {
            DiagnosticSeverity::Warning => eprintln!("warning: {}", diagnostic.message),
            DiagnosticSeverity::RecoverableError => {
                eprintln!("recoverable error: {}", diagnostic.message);
            }
        }
    }
}

async fn execute(cli: Cli) -> anyhow::Result<()> {
    if let GameCommand::Workspace {
        command: WorkspaceCommand::Bootstrap(args),
    } = &cli.game
    {
        let receipt =
            bootstrap_workspace_v1(&WorkspaceBootstrapRequestV1::new(args.workspace.clone()))?;
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if let GameCommand::Workspace {
        command: WorkspaceCommand::BootstrapTransaction { command },
    } = &cli.game
    {
        let receipt = match command {
            WorkspaceBootstrapTransactionCommand::Begin(args) => {
                begin_workspace_bootstrap_transaction_v1(
                    &WorkspaceBootstrapTransactionRequestV1::new(
                        args.workspace.clone(),
                        args.transaction.clone(),
                    ),
                )?
            }
            WorkspaceBootstrapTransactionCommand::Verify(args) => {
                verify_workspace_bootstrap_transaction_v1(
                    &WorkspaceBootstrapTransactionRequestV1::new(
                        args.workspace.clone(),
                        args.transaction.clone(),
                    ),
                )?
            }
            WorkspaceBootstrapTransactionCommand::Rollback(args) => {
                rollback_workspace_bootstrap_transaction_v1(
                    &WorkspaceBootstrapTransactionRequestV1::new(
                        args.workspace.clone(),
                        args.transaction.clone(),
                    ),
                )?
            }
            WorkspaceBootstrapTransactionCommand::Commit(args) => {
                commit_workspace_bootstrap_transaction_v1(
                    &WorkspaceBootstrapTransactionRequestV1::new(
                        args.workspace.clone(),
                        args.transaction.clone(),
                    ),
                )?
            }
            WorkspaceBootstrapTransactionCommand::Discard(args) => {
                discard_workspace_bootstrap_transaction_v1(
                    &WorkspaceBootstrapTransactionRequestV1::new(
                        args.workspace.clone(),
                        args.transaction.clone(),
                    ),
                )?
            }
            WorkspaceBootstrapTransactionCommand::Finalize(args) => {
                finalize_workspace_bootstrap_transaction_v1(
                    &WorkspaceBootstrapTransactionRequestV1::new(
                        args.workspace.clone(),
                        args.transaction.clone(),
                    ),
                    args.completed_operation.into(),
                )?
            }
        };
        println!("{}", serde_json::to_string(&receipt)?);
        return Ok(());
    }
    if let GameCommand::Update {
        command: UpdateCommand::Run(args),
    } = &cli.game
    {
        return run_native_update(args).await;
    }
    if let GameCommand::Update {
        command: UpdateCommand::Health(args),
    } = &cli.game
    {
        return check_native_update_health(args);
    }
    match &cli.game {
        GameCommand::Hsr {
            command: HsrCommand::Visualizer(args),
        } => {
            let invocation = ExportInvocation::capture()?;
            let output_root = args
                .out
                .clone()
                .unwrap_or_else(|| PathBuf::from("./hsr_endgame_export"));
            let _lease = acquire_writer_lease(&invocation.resolve(&output_root))?;
            return execute_visualizer_v1(
                &VisualizerTaskV1 {
                    game: Game::Hsr,
                    output_root,
                },
                &invocation,
            );
        }
        GameCommand::Zzz {
            command: ZzzCommand::Visualizer(args),
        } => {
            let invocation = ExportInvocation::capture()?;
            let output_root = args
                .out
                .clone()
                .unwrap_or_else(|| PathBuf::from("./zzz_endgame_export"));
            let _lease = acquire_writer_lease(&invocation.resolve(&output_root))?;
            return execute_visualizer_v1(
                &VisualizerTaskV1 {
                    game: Game::Zzz,
                    output_root,
                },
                &invocation,
            );
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
        GameCommand::Zzz {
            command: ZzzCommand::PullValue(args),
        } => {
            let invocation = ReportInvocation::capture()?;
            return run_zzz_pull_value(args, &invocation);
        }
        GameCommand::Zzz {
            command: ZzzCommand::ReviewPacket(args),
        } => {
            let invocation = ReportInvocation::capture()?;
            return run_zzz_review_packet(args, &invocation);
        }
        _ => {}
    }

    let invocation = ExportInvocation::capture()?;
    let today = invocation.local_date();
    let (game, args, name_map_seed) = match cli.game {
        GameCommand::Hsr {
            command: HsrCommand::Export(args),
        } => {
            let name_map_seed = args.name_map_seed.clone();
            (Game::Hsr, args.effective(today), name_map_seed)
        }
        GameCommand::Zzz {
            command: ZzzCommand::Export(args),
        } => (Game::Zzz, args.effective(today), None),
        _ => bail!("this command's Rust implementation is registered but not yet enabled; use the Python compatibility command during staged migration"),
    };
    let revision = "main".to_owned();
    let source = export_source(game, &args.repo_id, &revision);
    let refresh_official_banners = !matches!(&source, ExportSourceV1::Fixture { .. });
    let _lease = acquire_writer_lease(&invocation.resolve(&args.out))?;
    execute_export_observed_v1(
        &ExportTaskV1 {
            game,
            modes: args
                .modes
                .split(',')
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(|value| GameMode::parse(game, value))
                .collect::<miho_core::Result<Vec<_>>>()?,
            from_date: parse_cli_date(&args.from_date)?,
            to_date: parse_cli_date(&args.to_date)?,
            output_root: args.out,
            repo_id: args.repo_id,
            revision,
            features: FeatureFlags {
                hf_teams: args.toggles[0],
                prydwen_visible: args.toggles[1],
                prydwen_tier: args.toggles[2],
                official_names: args.toggles[3],
            },
            prydwen_top_n: args.prydwen_top_n,
            name_map_seed,
            refresh_official_banners,
            source,
        },
        &invocation,
        &CliExportObserver,
    )
    .await?;
    Ok(())
}

fn check_native_update_health(args: &UpdateHealthArgs) -> anyhow::Result<()> {
    workspace_config_path(&args.workspace, &args.config)
        .map_err(|_| anyhow::anyhow!("update.config_invalid"))?;
    let (health, _, _) = check_update_health_with_workspace_config_path_and_freshness_v1(
        &args.workspace,
        &args.config,
        !args.skip_hsr,
        !args.skip_zzz,
    );
    println!("{}", serde_json::to_string(&health)?);
    if health.healthy {
        return Ok(());
    }
    bail!(
        "{}",
        health
            .failure
            .as_ref()
            .map(|failure| failure.code.as_str())
            .unwrap_or("update.health_failed")
    )
}

async fn run_native_update(args: &UpdateRunArgs) -> anyhow::Result<()> {
    let invocation = match &args.attempt_id {
        Some(attempt_id) => UpdateInvocationV1::capture_with_attempt_id(attempt_id.clone())
            .map_err(|failure| anyhow::anyhow!(failure.code))?,
        None => UpdateInvocationV1::capture(),
    };
    let request = UpdateRequestV1 {
        workspace: args.workspace.clone(),
        skip_hsr: args.skip_hsr,
        skip_zzz: args.skip_zzz,
        force: args.force,
        config_sha256: None,
    };
    let config = workspace_config_path(&args.workspace, &args.config)
        .and_then(|path| load_update_config_with_digest_v1(&path))
        .and_then(|loaded| {
            loaded
                .config
                .resolve(&args.workspace)
                .map(|config| (config, loaded.sha256))
        });
    let outcome = match config {
        Ok((config, config_sha256)) => {
            let request = UpdateRequestV1 {
                workspace: config.workspace.clone(),
                config_sha256: Some(config_sha256),
                ..request
            };
            let executor = NativeUpdateExecutorV1::new(config);
            #[cfg(debug_assertions)]
            let executor = update_fixture_sources(executor);
            run_update_v1(&request, &invocation, &executor, &FileUpdateReceiptStore).await
        }
        Err(_) => {
            run_update_v1(
                &request,
                &invocation,
                &RejectedUpdateExecutor,
                &FileUpdateReceiptStore,
            )
            .await
        }
    };
    if outcome.exit_code == 0 {
        if let Some(failure) = committed_freshness_failure_code(outcome.freshness.as_ref()) {
            bail!("{failure}");
        }
        eprintln!("update succeeded: {}", outcome.receipt.attempt_id);
        return Ok(());
    }
    let failure = outcome
        .receipt
        .failure
        .as_ref()
        .map(|failure| failure.code.as_str())
        .unwrap_or("update.failed");
    bail!("{failure}")
}

fn committed_freshness_failure_code(
    freshness: Option<&Result<BTreeMap<Game, TaskFreshnessSummaryV1>, UpdateStepFailureV1>>,
) -> Option<&str> {
    match freshness {
        Some(Ok(freshness)) if !freshness.is_empty() => None,
        Some(Err(failure)) => Some(failure.code.as_str()),
        Some(Ok(_)) | None => Some("update.health_freshness_invalid"),
    }
}

struct RejectedUpdateExecutor;

impl UpdateStepExecutor for RejectedUpdateExecutor {
    fn execute<'a>(
        &'a self,
        _step: UpdateStepKindV1,
        _context: &'a UpdateStepContextV1,
    ) -> UpdateStepFuture<'a> {
        Box::pin(async {
            Err::<Vec<UpdateArtifactV1>, _>(UpdateStepFailureV1::safe(
                "update.config_invalid",
                "the native update configuration is invalid",
                false,
            ))
        })
    }
}

#[cfg(debug_assertions)]
fn update_fixture_sources(mut executor: NativeUpdateExecutorV1) -> NativeUpdateExecutorV1 {
    for (game, fixture_name, supplemental_name) in [
        (
            Game::Hsr,
            "MIHO_HSR_OFFLINE_FIXTURE",
            "MIHO_HSR_SUPPLEMENTAL_FIXTURE",
        ),
        (
            Game::Zzz,
            "MIHO_ZZZ_OFFLINE_FIXTURE",
            "MIHO_ZZZ_SUPPLEMENTAL_FIXTURE",
        ),
    ] {
        if let Some(root) = std::env::var_os(fixture_name).map(PathBuf::from) {
            executor = executor.with_fixture_source(
                game,
                root,
                std::env::var_os(supplemental_name).map(PathBuf::from),
            );
        }
    }
    executor
}

fn workspace_config_path(workspace: &Path, config: &Path) -> anyhow::Result<PathBuf> {
    if config.as_os_str().is_empty()
        || config.is_absolute()
        || config
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        bail!("update config must be a normal workspace-relative path");
    }
    Ok(workspace.join(config))
}

enum CliWriterLease {
    Workspace { _lease: WorkspaceWriteLease },
    Output { _file: File },
}

fn acquire_writer_lease(output_root: &Path) -> anyhow::Result<CliWriterLease> {
    let parent = output_root
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .ok_or_else(|| anyhow::anyhow!("workspace.write_unavailable"))?;
    // An update config only permits top-level game outputs, so the output's
    // immediate parent is the one authoritative workspace identity. Inferring
    // it from cwd lets the same absolute output acquire a different lock when
    // launched from a parent directory.
    match fs::symlink_metadata(parent) {
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            return WorkspaceWriteLease::acquire(parent)
                .map(|lease| CliWriterLease::Workspace { _lease: lease })
                .map_err(|error| anyhow::anyhow!(error.code()));
        }
        Ok(_) => bail!("workspace.write_unsafe"),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => bail!("workspace.write_unavailable"),
    }

    // A missing parent cannot be a configured top-level update output because
    // update workspaces already exist. Preserve direct nested-output support
    // with a deterministic output lock until the exporter creates the parent.
    let lock_directory = std::env::temp_dir().join("miho-endgame-direct-write-locks-v1");
    fs::create_dir_all(&lock_directory)
        .map_err(|_| anyhow::anyhow!("workspace.write_unavailable"))?;
    #[cfg(windows)]
    let identity = output_root.to_string_lossy().to_lowercase();
    #[cfg(not(windows))]
    let identity = output_root.to_string_lossy().into_owned();
    let digest = Sha256::digest(identity.as_bytes());
    let path = lock_directory.join(format!("{digest:x}.lock"));
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
        .map_err(|_| anyhow::anyhow!("workspace.write_unavailable"))?;
    match file.try_lock() {
        Ok(()) => Ok(CliWriterLease::Output { _file: file }),
        Err(TryLockError::WouldBlock) => bail!("workspace.write_busy"),
        Err(TryLockError::Error(_)) => bail!("workspace.write_unavailable"),
    }
}

fn export_source(game: Game, repo_id: &str, revision: &str) -> ExportSourceV1 {
    #[cfg(debug_assertions)]
    if let Some(root) = std::env::var_os("MIHO_OFFLINE_FIXTURE").map(PathBuf::from) {
        let supplemental_root = match game {
            Game::Hsr => std::env::var_os("MIHO_HSR_SUPPLEMENTAL_FIXTURE").map(PathBuf::from),
            Game::Zzz => std::env::var_os("MIHO_ZZZ_SUPPLEMENTAL_FIXTURE").map(PathBuf::from),
        };
        return ExportSourceV1::Fixture {
            root,
            supplemental_root,
        };
    }
    let cache_base = std::env::var_os("MIHO_CACHE_ROOT")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("LOCALAPPDATA")
                .map(|value| PathBuf::from(value).join("miho-endgame/cache"))
        })
        .unwrap_or_else(|| PathBuf::from(".miho/cache"));
    ExportSourceV1::Online {
        cache_root: export_cache_root(&cache_base, game, repo_id, revision),
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
        let today = NaiveDate::from_ymd_opt(2026, 7, 13).unwrap();
        let hsr = Cli::try_parse_from(["miho", "hsr", "export"]).unwrap();
        let GameCommand::Hsr {
            command: HsrCommand::Export(args),
        } = hsr.game
        else {
            panic!("expected HSR export")
        };
        let effective = args.effective(today);
        assert_eq!(effective.from_date, "2026-01-11");
        assert_eq!(effective.to_date, "2026-07-13");
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
        let effective = args.effective(today);
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
        assert!(
            !args
                .effective(NaiveDate::from_ymd_opt(2026, 7, 13).unwrap())
                .toggles[0]
        );
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
    fn successful_update_requires_verified_nonempty_freshness() {
        let verified = Ok(BTreeMap::from([(
            Game::Hsr,
            TaskFreshnessSummaryV1 {
                status: "warning".to_owned(),
                modes: BTreeMap::new(),
            },
        )]));
        assert_eq!(committed_freshness_failure_code(Some(&verified)), None);

        let empty = Ok(BTreeMap::new());
        assert_eq!(
            committed_freshness_failure_code(Some(&empty)),
            Some("update.health_freshness_invalid")
        );
        assert_eq!(
            committed_freshness_failure_code(None),
            Some("update.health_freshness_invalid")
        );

        let invalid = Err(UpdateStepFailureV1::safe(
            "update.health_freshness_invalid",
            "invalid fixture freshness",
            false,
        ));
        assert_eq!(
            committed_freshness_failure_code(Some(&invalid)),
            Some("update.health_freshness_invalid")
        );
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
}
