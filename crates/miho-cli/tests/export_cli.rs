//! Binary-level offline export contract for the enabled HSR/ZZZ export commands.

use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT_ID: AtomicU64 = AtomicU64::new(0);

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_miho")
}

fn fixture(game: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures")
        .join(format!("offline_{game}"))
}

fn temp_output(label: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "miho-cli-{label}-{}-{}",
        std::process::id(),
        NEXT_ID.fetch_add(1, Ordering::Relaxed)
    ));
    let _ = fs::remove_dir_all(&path);
    path
}

fn export(game: &str, fixture_path: Option<&Path>, out: &Path) -> Output {
    let mut command = Command::new(binary());
    command.args([game, "export", "--out"]).arg(out);
    if let Some(path) = fixture_path {
        command.env("MIHO_OFFLINE_FIXTURE", path);
        if game == "hsr" {
            command.env(
                "MIHO_HSR_SUPPLEMENTAL_FIXTURE",
                Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/hsr_supplemental"),
            );
        } else if game == "zzz" {
            command.env(
                "MIHO_ZZZ_SUPPLEMENTAL_FIXTURE",
                Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("../../tests/fixtures/zzz_supplemental_source"),
            );
        }
    } else {
        command.env_remove("MIHO_OFFLINE_FIXTURE");
    }
    command.output().expect("miho binary should start")
}

fn assert_core_export(game: &str, files: &[&str]) {
    let out = temp_output(game);
    let result = export(game, Some(&fixture(game)), &out);
    assert!(
        result.status.success(),
        "{game} export failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(String::from_utf8_lossy(&result.stderr).contains("fixture mode:"));
    for relative in files {
        let path = out.join(relative);
        assert!(path.is_file(), "missing core artifact: {}", path.display());
        assert!(
            fs::metadata(&path).unwrap().len() > 0,
            "empty artifact: {}",
            path.display()
        );
    }
    fs::remove_dir_all(out).unwrap();
}

#[test]
fn hsr_offline_export_writes_complete_core_set() {
    assert_core_export(
        "hsr",
        &[
            "phase_index.csv",
            "character_usage_long.csv",
            "team_rank_raw.csv",
            "name_map.csv",
            "prydwen_tier_current.csv",
            "prydwen_tier_history.csv",
            "prydwen_tier_changelog_history.csv",
            "raw/prydwen_tier/tier-list_latest.html",
            "export_report.md",
            "artifact_manifest.json",
        ],
    );
}

#[test]
fn zzz_offline_export_writes_complete_core_set() {
    assert_core_export(
        "zzz",
        &[
            "phase_index.csv",
            "character_usage_long.csv",
            "character_usage_phase_latest.csv",
            "team_rank_raw.csv",
            "team_rank_dedup_unordered.csv",
            "name_map.csv",
            "name_map_unresolved.csv",
            "prydwen_tier_current.csv",
            "prydwen_tier_history.csv",
            "prydwen_tier_changelog.csv",
            "prydwen_tier_changelog_history.csv",
            "prydwen_tier_usage_trend.csv",
            "raw/prydwen/sd.html",
            "raw/prydwen_tier/tier-list_latest.html",
            "raw/hoyowiki/zzz_agents_zh-cn.json",
            "raw/hoyowiki/zzz_bangboo_en-us.json",
            "export_report.md",
            "artifact_manifest.json",
        ],
    );
}

#[test]
fn missing_offline_fixture_path_exits_one() {
    let out = temp_output("missing");
    let missing = temp_output("does-not-exist");
    let result = export("zzz", Some(&missing), &out);
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).starts_with("export failed: "));
}

#[test]
fn malformed_offline_fixture_exits_one() {
    let out = temp_output("bad-out");
    let bad = temp_output("bad-fixture");
    fs::create_dir_all(&bad).unwrap();
    fs::write(bad.join("invalid.json"), b"{not-json").unwrap();
    let result = export("hsr", Some(&bad), &out);
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).starts_with("export failed: "));
    fs::remove_dir_all(bad).unwrap();
}

#[test]
fn unknown_argument_keeps_clap_exit_two() {
    let result = Command::new(binary())
        .args(["zzz", "export", "--definitely-unknown"])
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(2));
}

#[test]
fn zzz_default_online_export_keeps_the_complete_directory_gate() {
    let out = temp_output("online-gate");
    let result = export("zzz", None, &out);
    assert_eq!(result.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.starts_with("export failed: "));
    assert!(stderr.contains("XLSX and visualizer"));
    assert!(!stderr.contains("not yet migrated"));
    assert!(!out.exists());
}

#[test]
fn zzz_hf_only_online_export_also_keeps_the_product_level_gate() {
    let out = temp_output("zzz-hf-only-online-gate");
    let result = Command::new(binary())
        .args([
            "zzz",
            "export",
            "--no-include-prydwen-visible",
            "--no-include-prydwen-tier",
            "--no-official-name-map",
            "--out",
        ])
        .arg(&out)
        .env_remove("MIHO_OFFLINE_FIXTURE")
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.contains("XLSX and visualizer"));
    assert!(!out.exists());
}

#[test]
fn hsr_default_online_export_keeps_the_complete_directory_gate() {
    let out = temp_output("hsr-online-gate");
    let result = export("hsr", None, &out);
    assert_eq!(result.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.contains("XLSX and visualizer"));
    assert!(!stderr.contains("supplemental capabilities are not yet migrated"));
    assert!(!out.exists());
}

#[test]
fn invalid_date_is_a_business_error() {
    let out = temp_output("invalid-date");
    let result = Command::new(binary())
        .args(["hsr", "export", "--from-date", "not-a-date", "--out"])
        .arg(&out)
        .env("MIHO_OFFLINE_FIXTURE", fixture("hsr"))
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr)
        .starts_with("export failed: invalid date: not-a-date"));
    assert!(!out.exists());
}

#[test]
fn zzz_migrated_top_n_is_accepted() {
    let out = temp_output("zzz-top-n");
    let result = Command::new(binary())
        .args(["zzz", "export", "--prydwen-top-n", "7", "--out"])
        .arg(&out)
        .env("MIHO_OFFLINE_FIXTURE", fixture("zzz"))
        .env(
            "MIHO_ZZZ_SUPPLEMENTAL_FIXTURE",
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../tests/fixtures/zzz_supplemental_source"),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(out.join("raw/prydwen/sd.html").is_file());
    fs::remove_dir_all(out).unwrap();
}

#[test]
fn hsr_migrated_top_n_and_name_seed_are_accepted() {
    let out = temp_output("hsr-options");
    let seed = temp_output("hsr-seed").with_extension("csv");
    fs::write(
        &seed,
        b"character_slug,character_name_en,character_name_cn\ntopaz-and-numby,Topaz and Numby,Topaz CN\n",
    )
    .unwrap();
    let result = Command::new(binary())
        .args(["hsr", "export", "--prydwen-top-n", "1", "--name-map-seed"])
        .arg(&seed)
        .args(["--out"])
        .arg(&out)
        .env("MIHO_OFFLINE_FIXTURE", fixture("hsr"))
        .env(
            "MIHO_HSR_SUPPLEMENTAL_FIXTURE",
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/hsr_supplemental"),
        )
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let names = fs::read_to_string(out.join("name_map.csv")).unwrap();
    assert!(names.contains("topaz-and-numby,Topaz and Numby,Topaz CN"));
    fs::remove_file(seed).unwrap();
    fs::remove_dir_all(out).unwrap();
}
