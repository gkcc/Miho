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
fn default_online_export_is_gated_before_network_for_supplemental_sources() {
    let out = temp_output("online-gate");
    let result = export("hsr", None, &out);
    assert_eq!(result.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&result.stderr);
    assert!(stderr.starts_with("export failed: "));
    assert!(stderr.contains("prydwen-visible"));
    assert!(stderr.contains("prydwen-tier"));
    assert!(stderr.contains("official-name-map"));
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
fn explicitly_unimplemented_export_options_do_not_succeed_silently() {
    for game in ["hsr", "zzz"] {
        let out = temp_output("unsupported-option");
        let result = Command::new(binary())
            .args([game, "export", "--prydwen-top-n", "7", "--out"])
            .arg(&out)
            .env("MIHO_OFFLINE_FIXTURE", fixture(game))
            .output()
            .unwrap();
        assert_eq!(result.status.code(), Some(1));
        assert!(String::from_utf8_lossy(&result.stderr).contains("--prydwen-top-n"));
        assert!(!out.exists());
    }
}
