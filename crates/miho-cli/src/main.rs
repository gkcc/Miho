use std::{path::PathBuf, time::Duration as StdDuration};

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
    network::{FetchMode, HttpClient},
    normalize::parse_date,
    pipeline::{run_export_v1, run_hsr_export_v1, ExportRequest, Game, OfflineFixture},
    source::HfSnapshotSource,
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
    let (game, args, name_map_seed, unsupported_options) = match cli.game {
        GameCommand::Hsr { command: HsrCommand::Export(args) } => {
            let name_map_seed = args.name_map_seed.clone();
            (Game::Hsr, args.effective(), name_map_seed, Vec::new())
        }
        GameCommand::Zzz { command: ZzzCommand::Export(args) } => {
            let unsupported = args
                .common
                .prydwen_top_n
                .is_some()
                .then_some("--prydwen-top-n")
                .into_iter()
                .collect();
            (Game::Zzz, args.effective(), None, unsupported)
        }
        _ => bail!("this command's Rust implementation is registered but not yet enabled; use the Python compatibility command during staged migration"),
    };
    if !unsupported_options.is_empty() {
        bail!(
            "export options are not yet migrated: {}",
            unsupported_options.join(", ")
        );
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
        workbook: WorkbookPolicy::Disabled,
    };
    #[cfg(debug_assertions)]
    let offline_fixture = std::env::var_os("MIHO_OFFLINE_FIXTURE");
    #[cfg(not(debug_assertions))]
    let offline_fixture: Option<std::ffi::OsString> = None;

    let run = if let Some(path) = offline_fixture {
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
            Game::Zzz => run_export_v1(&fixture, &request, &context).await?,
        };
        eprintln!("fixture mode: {}", fixture_path.display());
        run
    } else {
        let supplemental = [
            (args.toggles[1], "prydwen-visible"),
            (args.toggles[2], "prydwen-tier"),
            (args.toggles[3], "official-name-map"),
        ]
        .into_iter()
        .filter_map(|(enabled, name)| enabled.then_some(name))
        .collect::<Vec<_>>();
        if game == Game::Zzz && !supplemental.is_empty() {
            bail!(
                "online supplemental capabilities are not yet migrated: {}; disable them explicitly to use the core Hugging Face export",
                supplemental.join(", ")
            );
        }
        if game == Game::Hsr {
            bail!(
                "HSR supplemental sources are migrated, but the default online export remains gated until XLSX and visualizer artifacts pass the complete-directory compatibility check; use the Python compatibility command"
            );
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
            Game::Zzz => run_export_v1(&source, &request, &context).await?,
        }
    };
    for diagnostic in &run.diagnostics {
        match diagnostic.severity {
            DiagnosticSeverity::Warning => eprintln!("warning: {}", diagnostic.message),
            DiagnosticSeverity::RecoverableError => {
                eprintln!("recoverable error: {}", diagnostic.message)
            }
        }
    }
    run.bundle.write_to(&args.out)?;
    Ok(())
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
}
