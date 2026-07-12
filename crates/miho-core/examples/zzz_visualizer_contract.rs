use std::{env, fs, path::PathBuf};

use chrono::NaiveDateTime;
use miho_core::{
    output::ArtifactBundle, visualizer::VisualizerContext, zzz_visualizer::attach_zzz_visualizer,
};

const ZZZ_VISUALIZER_CSVS: &[&str] = &[
    "character_usage_long.csv",
    "prydwen_tier_current.csv",
    "team_rank_dedup_unordered.csv",
    "name_map.csv",
    "prydwen_tier_changelog_history.csv",
    "phase_index.csv",
];

const ZZZ_VISUALIZER_RAW: &[&str] = &[
    "raw/prydwen/sd.html",
    "raw/prydwen/da.html",
    "raw/hoyowiki/zzz_agents_zh-cn.json",
    "raw/hoyowiki/zzz_agents_en-us.json",
];

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let (
        Some(csv_root),
        Some(out_root),
        Some(local_datetime),
        Some(phase_overrides),
        Some(banner_json),
        Some(decision_json),
        Some(avatar_slug),
        Some(avatar_webp),
    ) = (
        args.next(),
        args.next(),
        args.next(),
        args.next(),
        args.next(),
        args.next(),
        args.next(),
        args.next(),
    )
    else {
        return Err(
            "usage: zzz_visualizer_contract <csv-root> <out-root> <local-datetime> <phase-overrides> <banner-json> <decision-json> <avatar-slug> <avatar-webp>"
                .into(),
        );
    };
    if args.next().is_some() {
        return Err("zzz_visualizer_contract received unexpected extra arguments".into());
    }

    let csv_root = PathBuf::from(csv_root);
    let out_root = PathBuf::from(out_root);
    let local_datetime = NaiveDateTime::parse_from_str(&local_datetime, "%Y-%m-%dT%H:%M:%S")?;

    let mut bundle = ArtifactBundle::default();
    for relative in ZZZ_VISUALIZER_CSVS {
        bundle.add_bytes(relative, fs::read(csv_root.join(relative))?)?;
    }
    for relative in ZZZ_VISUALIZER_RAW {
        let path = csv_root.join(relative);
        if path.is_file() {
            bundle.add_bytes(relative, fs::read(path)?)?;
        }
    }

    let mut context = VisualizerContext::new_with_local_datetime(local_datetime);
    for (name, path) in [
        ("zzz_endgame_phase_overrides.json", phase_overrides),
        ("zzz_banner_plan.json", banner_json),
        ("decision_cards.json", decision_json),
    ] {
        context.add_sidecar_bytes(name, fs::read(path)?)?;
    }
    context.add_avatar_webp(&avatar_slug, fs::read(avatar_webp)?)?;

    attach_zzz_visualizer(&mut bundle, &context)?;
    bundle.refresh_manifest("artifact_manifest.json")?;
    bundle.write_to(&out_root)?;
    Ok(())
}
