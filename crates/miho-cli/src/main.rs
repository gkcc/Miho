use std::path::PathBuf;

use clap::{Args, Parser, Subcommand, ValueEnum};

#[derive(Parser)]
#[command(name = "miho", version, about = "HSR and ZZZ endgame data exporter")]
struct Cli {
    #[arg(value_enum)]
    game: Game,
    #[command(subcommand)]
    command: Command,
}

#[derive(Clone, ValueEnum)]
enum Game {
    Hsr,
    Zzz,
}

#[derive(Subcommand)]
enum Command {
    Export(ExportArgs),
    Visualizer(VisualizerArgs),
    Decision(DecisionArgs),
    Evidence(EvidenceArgs),
    Coverage(CoverageArgs),
    #[command(name = "pull-value")]
    PullValue(PullValueArgs),
    #[command(name = "review-packet")]
    ReviewPacket(PullValueArgs),
    Serve(ServeArgs),
}

#[derive(Args)]
struct ExportArgs {
    #[arg(long)]
    from_date: Option<String>,
    #[arg(long)]
    to_date: Option<String>,
    #[arg(long, default_value = "out")]
    out: PathBuf,
    #[arg(long)]
    modes: Option<String>,
    #[arg(long)]
    repo_id: Option<String>,
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    include_teams: bool,
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    include_prydwen_visible: bool,
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    include_prydwen_tier: bool,
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    official_name_map: bool,
    #[arg(long, default_value_t = 20)]
    prydwen_top_n: usize,
    #[arg(long)]
    name_map_seed: Option<PathBuf>,
}

#[derive(Args)]
struct VisualizerArgs {
    #[arg(long, default_value = "out")]
    out: PathBuf,
}
#[derive(Args)]
struct DecisionArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "out_zzz")]
    out: PathBuf,
    #[arg(long)]
    rules: Option<PathBuf>,
}

#[derive(Args)]
struct EvidenceArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "out_zzz")]
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
    #[arg(long)]
    min_a_app_rate: Option<String>,
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    include_missing: bool,
}

#[derive(Args)]
struct CoverageArgs {
    #[arg(long = "box")]
    box_path: PathBuf,
    #[arg(long, default_value = "out_zzz")]
    out: PathBuf,
    #[arg(long)]
    planned_slugs: Option<String>,
    #[arg(long)]
    plan: Option<PathBuf>,
    #[arg(long, default_value = "next")]
    plan_status: String,
    #[arg(long, default_value_t = 0)]
    limit: usize,
    #[arg(long)]
    min_a_app_rate: Option<String>,
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
    #[arg(long, default_value = "out_zzz")]
    out: PathBuf,
    #[arg(long)]
    plan: Option<PathBuf>,
    #[arg(long, default_value = "next")]
    plan_status: String,
    #[arg(long)]
    planned_slugs: Option<String>,
    #[arg(long)]
    mechanism_notes_dir: Option<PathBuf>,
    #[arg(long)]
    decision_baseline: Option<PathBuf>,
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

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    validate_command(&cli)?;
    anyhow::bail!("this command's Rust implementation is registered but not yet enabled; use the Python compatibility command during staged migration")
}

fn validate_command(cli: &Cli) -> anyhow::Result<()> {
    let zzz_only = matches!(
        cli.command,
        Command::Decision(_)
            | Command::Evidence(_)
            | Command::Coverage(_)
            | Command::PullValue(_)
            | Command::ReviewPacket(_)
            | Command::Serve(_)
    );
    if zzz_only && !matches!(cli.game, Game::Zzz) {
        anyhow::bail!("command is only available for zzz");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;
    #[test]
    fn command_tree_is_valid() {
        Cli::command().debug_assert();
    }
}
