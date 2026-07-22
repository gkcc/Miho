use std::{env, fs, path::PathBuf};

use chrono::NaiveDateTime;
use miho_core::{
    hsr_visualizer::attach_hsr_visualizer, output::ArtifactBundle, visualizer::VisualizerContext,
};

const HSR_VISUALIZER_CSVS: &[&str] = &[
    "prydwen_tier_usage_trend.csv",
    "prydwen_tier_current.csv",
    "prydwen_tier_changelog_history.csv",
    "prydwen_tier_charts.csv",
    "character_usage_long.csv",
    "name_map.csv",
    "phase_index.csv",
];

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let (
        Some(csv_root),
        Some(out_root),
        Some(local_datetime),
        Some(banner_json),
        Some(avatar_slug),
        Some(avatar_webp),
    ) = (
        args.next(),
        args.next(),
        args.next(),
        args.next(),
        args.next(),
        args.next(),
    )
    else {
        return Err(
            "usage: hsr_visualizer_contract <csv-root> <out-root> <local-datetime> <banner-json> <avatar-slug> <avatar-webp>"
                .into(),
        );
    };
    if args.next().is_some() {
        return Err("hsr_visualizer_contract received unexpected extra arguments".into());
    }

    let csv_root = PathBuf::from(csv_root);
    let out_root = PathBuf::from(out_root);
    let local_datetime = NaiveDateTime::parse_from_str(&local_datetime, "%Y-%m-%dT%H:%M:%S")?;

    let mut bundle = ArtifactBundle::default();
    for relative in HSR_VISUALIZER_CSVS {
        bundle.add_bytes(relative, fs::read(csv_root.join(relative))?)?;
    }
    let team_path = if csv_root.join("team_rank_dedup_unordered.csv").is_file() {
        "team_rank_dedup_unordered.csv"
    } else {
        "team_rank_raw.csv"
    };
    bundle.add_bytes(team_path, fs::read(csv_root.join(team_path))?)?;
    let data_quality_path = csv_root.join("data_quality.json");
    if data_quality_path.is_file() {
        bundle.add_bytes("data_quality.json", fs::read(data_quality_path)?)?;
    }
    for relative in [
        "raw/hoyowiki/hsr_characters_zh-cn.json",
        "raw/hoyowiki/hsr_characters_en-us.json",
    ] {
        let path = csv_root.join(relative);
        if path.is_file() {
            bundle.add_bytes(relative, fs::read(path)?)?;
        }
    }

    let mut context = VisualizerContext::new_with_local_datetime(local_datetime);
    context.add_sidecar_bytes("hsr_banner_plan.json", fs::read(banner_json)?)?;
    context.add_avatar_webp(&avatar_slug, fs::read(avatar_webp)?)?;

    attach_hsr_visualizer(&mut bundle, &context)?;
    bundle.refresh_manifest("artifact_manifest.json")?;
    bundle.write_to(&out_root)?;
    Ok(())
}
