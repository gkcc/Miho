//! Binary-level offline export contract for the enabled HSR/ZZZ export commands.

use std::{
    collections::BTreeSet,
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

fn visualizer(game: &str, out: &Path) -> Output {
    Command::new(binary())
        .args([game, "visualizer", "--out"])
        .arg(out)
        .output()
        .expect("miho binary should start")
}

fn assert_no_transaction_residue(parent: &Path, output_name: &str) {
    let prefix = format!(".{output_name}.miho-");
    let residue = fs::read_dir(parent)
        .unwrap()
        .filter_map(Result::ok)
        .filter_map(|entry| entry.file_name().into_string().ok())
        .filter(|name| name.starts_with(&prefix))
        .collect::<Vec<_>>();
    assert!(residue.is_empty(), "transaction residue: {residue:?}");
}

fn manifest_paths(path: &Path) -> BTreeSet<String> {
    serde_json::from_slice::<Vec<serde_json::Value>>(&fs::read(path).unwrap())
        .unwrap()
        .into_iter()
        .map(|entry| entry["path"].as_str().unwrap().to_owned())
        .collect()
}

fn assert_core_export(game: &str, files: &[&str]) {
    let root = temp_output(&format!("{game}-export-root"));
    let out = root.join(format!("{game}-out"));
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
    let workbook = out.join(format!("{game}_endgame_dataset.xlsx"));
    assert_eq!(
        &fs::read(&workbook).unwrap()[..4],
        &[0x50, 0x4b, 0x03, 0x04]
    );
    let manifest = fs::read_to_string(out.join("artifact_manifest.json")).unwrap();
    assert!(manifest.contains(&format!("\"path\": \"{game}_endgame_dataset.xlsx\"")));
    if game == "zzz" {
        for name in ["index.html", "styles.css", "app.js"] {
            assert!(root.join("visualizer").join(name).is_file());
        }
    }
    fs::remove_dir_all(root).unwrap();
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
            "hsr_endgame_dataset.xlsx",
            "visualizer/index.html",
            "visualizer/styles.css",
            "visualizer/app.js",
            "visualizer/data.json",
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
            "zzz_endgame_dataset.xlsx",
            "visualizer/index.html",
            "visualizer/styles.css",
            "visualizer/app.js",
            "visualizer/data.json",
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
    let root = temp_output("zzz-top-n-root");
    let out = root.join("out");
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
    fs::remove_dir_all(root).unwrap();
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

#[test]
fn hsr_visualizer_rebuilds_existing_artifacts_and_refreshes_manifest() {
    let root = temp_output("hsr-visualizer-root");
    let out = root.join("中文 空格 output");
    let exported = export("hsr", Some(&fixture("hsr")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );

    let avatar = b"RIFF\x1e\x00\x00\x00WEBPVP8L\x11\x00\x00\x00/\x01@\x00\x00\x07\xd0\xb1\x96t\xbd\xff\x81\x88\xe8\x7f\x00\x00";
    let avatar_path = out.join("visualizer/assets/avatars/agent-alpha.webp");
    fs::create_dir_all(avatar_path.parent().unwrap()).unwrap();
    fs::write(&avatar_path, avatar).unwrap();
    fs::write(out.join("visualizer/stale.txt"), "stale").unwrap();
    fs::write(out.join("keep-me.txt"), "unmanaged").unwrap();
    fs::write(out.join("hsr_banner_plan.json"), "{broken}").unwrap();
    let fallback = root.join("configs/hsr_banner_plan.json");
    fs::create_dir_all(fallback.parent().unwrap()).unwrap();
    fs::copy(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/visualizer_contract/hsr_banner_plan.json"),
        &fallback,
    )
    .unwrap();

    let result = visualizer("hsr", &out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(out.join("visualizer/index.html").is_file());
    assert!(out.join("visualizer/styles.css").is_file());
    assert!(out.join("visualizer/app.js").is_file());
    assert_eq!(fs::read(&avatar_path).unwrap(), avatar);
    assert!(!out.join("visualizer/stale.txt").exists());
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "unmanaged"
    );

    let data = fs::read_to_string(out.join("visualizer/data.json")).unwrap();
    assert!(data.contains("fixture-phase"));
    assert!(data.contains("./assets/avatars/agent-alpha.webp"));
    let manifest = fs::read_to_string(out.join("artifact_manifest.json")).unwrap();
    for path in [
        "visualizer/index.html",
        "visualizer/styles.css",
        "visualizer/app.js",
        "visualizer/data.json",
        "visualizer/assets/avatars/agent-alpha.webp",
    ] {
        assert!(manifest.contains(path), "manifest is missing {path}");
    }
    assert!(!manifest.contains("visualizer/stale.txt"));
    assert!(!manifest.contains("keep-me.txt"));
    assert!(!manifest.contains("hsr_banner_plan.json"));
    assert_no_transaction_residue(&root, "中文 空格 output");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn hsr_visualizer_adopts_only_formal_artifacts_from_legacy_output_without_manifest() {
    let root = temp_output("hsr-legacy-no-manifest-root");
    let out = root.join("legacy-output");
    let exported = export("hsr", Some(&fixture("hsr")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    let manifest_path = out.join("artifact_manifest.json");
    let prior_managed = manifest_paths(&manifest_path);
    fs::remove_file(&manifest_path).unwrap();
    fs::write(out.join("keep-me.txt"), "legacy unmanaged").unwrap();

    let result = visualizer("hsr", &out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let refreshed = manifest_paths(&manifest_path);
    assert!(
        prior_managed.is_subset(&refreshed),
        "legacy formal artifacts lost ownership: {:?}",
        prior_managed.difference(&refreshed).collect::<Vec<_>>()
    );
    assert!(refreshed.contains("hsr_endgame_dataset.xlsx"));
    assert!(refreshed.contains("export_report.md"));
    assert!(refreshed.iter().any(|path| path.starts_with("raw/")));
    assert!(!refreshed.contains("keep-me.txt"));
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "legacy unmanaged"
    );
    assert_no_transaction_residue(&root, "legacy-output");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn hsr_visualizer_failure_before_swap_keeps_old_output_unchanged() {
    let root = temp_output("hsr-visualizer-rollback-root");
    let out = root.join("rollback-output");
    let exported = export("hsr", Some(&fixture("hsr")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    fs::write(out.join("visualizer/stale.txt"), "old-stale").unwrap();
    fs::write(out.join("keep-me.txt"), "old-unmanaged").unwrap();
    let old_data = fs::read(out.join("visualizer/data.json")).unwrap();
    let old_manifest = fs::read(out.join("artifact_manifest.json")).unwrap();

    let result = Command::new(binary())
        .args(["hsr", "visualizer", "--out"])
        .arg(&out)
        .env("MIHO_TEST_FAIL_OUTPUT_TRANSACTION_BEFORE_SWAP", "1")
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).contains("before swap"));
    assert_eq!(
        fs::read_to_string(out.join("visualizer/stale.txt")).unwrap(),
        "old-stale"
    );
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "old-unmanaged"
    );
    assert_eq!(
        fs::read(out.join("visualizer/data.json")).unwrap(),
        old_data
    );
    assert_eq!(
        fs::read(out.join("artifact_manifest.json")).unwrap(),
        old_manifest
    );
    assert_no_transaction_residue(&root, "rollback-output");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_visualizer_rebuilds_with_fallback_sidecars_and_bangboo() {
    let root = temp_output("zzz-visualizer-root");
    let out = root.join("ZZZ 中文 空格 output");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );

    let avatar = b"RIFF\x1e\x00\x00\x00WEBPVP8L\x11\x00\x00\x00/\x01@\x00\x00\x07\xd0\xb1\x96t\xbd\xff\x81\x88\xe8\x7f\x00\x00";
    let avatar_path = out.join("visualizer/assets/avatars/agent-alpha.webp");
    fs::create_dir_all(avatar_path.parent().unwrap()).unwrap();
    fs::write(&avatar_path, avatar).unwrap();
    fs::write(out.join("visualizer/stale.txt"), "stale").unwrap();
    fs::write(out.join("keep-me.txt"), "unmanaged").unwrap();
    fs::write(root.join("visualizer/stale-hub.txt"), "stale hub").unwrap();
    fs::write(out.join("zzz_banner_plan.json"), "[]").unwrap();
    fs::create_dir(out.join("zzz_endgame_phase_overrides.json")).unwrap();
    fs::copy(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/visualizer_contract/decision_cards.json"),
        out.join("decision_cards.json"),
    )
    .unwrap();

    let phase_csv = fs::read_to_string(out.join("phase_index.csv")).unwrap();
    let phase = phase_csv
        .lines()
        .nth(1)
        .unwrap()
        .split(',')
        .collect::<Vec<_>>();
    let configs = root.join("configs");
    fs::create_dir_all(&configs).unwrap();
    fs::write(
        configs.join("zzz_endgame_phase_overrides.json"),
        serde_json::to_vec(&serde_json::json!({"phases":[{
            "mode":phase[2], "phase_ver":phase[4], "note":"cli-fallback-marker"
        }]}))
        .unwrap(),
    )
    .unwrap();
    fs::copy(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures/visualizer_contract/zzz_banner_plan.json"),
        configs.join("zzz_banner_plan.json"),
    )
    .unwrap();

    let result = visualizer("zzz", &out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    for path in [
        "visualizer/index.html",
        "visualizer/styles.css",
        "visualizer/app.js",
        "visualizer/data.json",
    ] {
        assert!(out.join(path).is_file(), "missing {path}");
    }
    assert_eq!(fs::read(&avatar_path).unwrap(), avatar);
    assert!(!out.join("visualizer/stale.txt").exists());
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "unmanaged"
    );

    let data: serde_json::Value =
        serde_json::from_slice(&fs::read(out.join("visualizer/data.json")).unwrap()).unwrap();
    assert_eq!(data["bannerRows"][0]["phase_id"], "fixture-phase");
    assert_eq!(data["decisionCards"]["summary"]["candidate_count"], 1);
    assert!(data["phaseInfoRows"]
        .as_array()
        .unwrap()
        .iter()
        .any(|row| row["source_note"] == "cli-fallback-marker"));
    let teams = data["teamTemplates"].as_array().unwrap();
    assert!(!teams.is_empty());
    assert!(teams
        .iter()
        .all(|row| row.get("bangboo").is_some() && row.get("bangboo_name").is_some()));
    assert!(teams.iter().any(|row| {
        row["bangboo"]
            .as_str()
            .is_some_and(|value| !value.is_empty())
            && row["bangboo_name"]
                .as_str()
                .is_some_and(|value| !value.is_empty())
    }));
    assert!(data
        .to_string()
        .contains("./assets/avatars/agent-alpha.webp"));

    let manifest = fs::read_to_string(out.join("artifact_manifest.json")).unwrap();
    for path in [
        "visualizer/index.html",
        "visualizer/styles.css",
        "visualizer/app.js",
        "visualizer/data.json",
        "visualizer/assets/avatars/agent-alpha.webp",
    ] {
        assert!(manifest.contains(path), "manifest is missing {path}");
    }
    assert!(!manifest.contains("visualizer/stale.txt"));
    for unmanaged in [
        "keep-me.txt",
        "zzz_endgame_phase_overrides.json",
        "zzz_banner_plan.json",
        "decision_cards.json",
    ] {
        assert!(!manifest.contains(unmanaged));
        assert!(
            out.join(unmanaged).exists(),
            "missing preserved {unmanaged}"
        );
    }
    assert_no_transaction_residue(&root, "ZZZ 中文 空格 output");
    let hub = root.join("visualizer");
    let hub_files = fs::read_dir(&hub)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().into_string().unwrap())
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(
        hub_files,
        std::collections::BTreeSet::from([
            "app.js".to_owned(),
            "index.html".to_owned(),
            "styles.css".to_owned(),
        ])
    );
    let hub_html = fs::read_to_string(hub.join("index.html")).unwrap();
    assert!(hub_html.contains(
        "../ZZZ%20%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC%20output/visualizer/index.html"
    ));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_visualizer_adopts_only_formal_artifacts_from_legacy_output_without_manifest() {
    let root = temp_output("zzz-legacy-no-manifest-root");
    let out = root.join("legacy-output");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    let manifest_path = out.join("artifact_manifest.json");
    let prior_managed = manifest_paths(&manifest_path);
    fs::remove_file(&manifest_path).unwrap();
    fs::write(out.join("keep-me.txt"), "legacy unmanaged").unwrap();

    let result = visualizer("zzz", &out);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let refreshed = manifest_paths(&manifest_path);
    assert!(
        prior_managed.is_subset(&refreshed),
        "legacy formal artifacts lost ownership: {:?}",
        prior_managed.difference(&refreshed).collect::<Vec<_>>()
    );
    assert!(refreshed.contains("zzz_endgame_dataset.xlsx"));
    assert!(refreshed.contains("export_report.md"));
    assert!(refreshed.iter().any(|path| path.starts_with("raw/")));
    assert!(!refreshed.contains("keep-me.txt"));
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "legacy unmanaged"
    );
    assert_no_transaction_residue(&root, "legacy-output");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_visualizer_failure_before_swap_keeps_old_output_unchanged() {
    let root = temp_output("zzz-visualizer-rollback-root");
    let out = root.join("rollback-output");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    fs::write(out.join("visualizer/stale.txt"), "old-stale").unwrap();
    fs::write(out.join("keep-me.txt"), "old-unmanaged").unwrap();
    let old_data = fs::read(out.join("visualizer/data.json")).unwrap();
    let old_manifest = fs::read(out.join("artifact_manifest.json")).unwrap();

    let result = Command::new(binary())
        .args(["zzz", "visualizer", "--out"])
        .arg(&out)
        .env("MIHO_TEST_FAIL_OUTPUT_TRANSACTION_BEFORE_SWAP", "1")
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(out.join("visualizer/stale.txt").is_file());
    assert_eq!(
        fs::read(out.join("visualizer/data.json")).unwrap(),
        old_data
    );
    assert_eq!(
        fs::read(out.join("artifact_manifest.json")).unwrap(),
        old_manifest
    );
    assert_no_transaction_residue(&root, "rollback-output");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_visualizer_rejects_non_finite_decision_constants_without_mutation() {
    let root = temp_output("zzz-visualizer-non-finite-decision-root");
    let out = root.join("out");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    fs::write(out.join("visualizer/stale.txt"), "old-visualizer").unwrap();
    let old_index = fs::read(out.join("visualizer/index.html")).unwrap();
    let old_data = fs::read(out.join("visualizer/data.json")).unwrap();
    let old_manifest = fs::read(out.join("artifact_manifest.json")).unwrap();

    for constant in ["NaN", "Infinity", "-Infinity"] {
        fs::write(
            out.join("decision_cards.json"),
            format!(r#"{{"summary":{{"score":{constant}}},"cards":[]}}"#),
        )
        .unwrap();
        let result = visualizer("zzz", &out);
        assert_eq!(
            result.status.code(),
            Some(1),
            "{constant} unexpectedly succeeded"
        );
        assert!(
            String::from_utf8_lossy(&result.stderr)
                .contains("non-finite JSON constant in decision_cards.json"),
            "unexpected {constant} error: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(
            fs::read_to_string(out.join("visualizer/stale.txt")).unwrap(),
            "old-visualizer"
        );
        assert_eq!(
            fs::read(out.join("visualizer/index.html")).unwrap(),
            old_index
        );
        assert_eq!(
            fs::read(out.join("visualizer/data.json")).unwrap(),
            old_data
        );
        assert_eq!(
            fs::read(out.join("artifact_manifest.json")).unwrap(),
            old_manifest
        );
        assert_no_transaction_residue(&root, "out");
    }

    for surrogate in [r#"\ud800"#, r#"\udc00"#] {
        fs::write(
            out.join("decision_cards.json"),
            format!(r#"{{"summary":{{"x":"{surrogate}"}},"cards":[]}}"#),
        )
        .unwrap();
        let result = visualizer("zzz", &out);
        assert_eq!(result.status.code(), Some(1));
        assert!(
            String::from_utf8_lossy(&result.stderr)
                .contains("unpaired JSON surrogate escape in decision_cards.json"),
            "unexpected surrogate error: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(
            fs::read_to_string(out.join("visualizer/stale.txt")).unwrap(),
            "old-visualizer"
        );
        assert_eq!(
            fs::read(out.join("visualizer/index.html")).unwrap(),
            old_index
        );
        assert_eq!(
            fs::read(out.join("visualizer/data.json")).unwrap(),
            old_data
        );
        assert_eq!(
            fs::read(out.join("artifact_manifest.json")).unwrap(),
            old_manifest
        );
        assert_no_transaction_residue(&root, "out");
    }

    fs::write(out.join("decision_cards.json"), "{ordinary malformed").unwrap();
    let malformed = visualizer("zzz", &out);
    assert!(
        malformed.status.success(),
        "ordinary malformed JSON should retain Python fallback semantics: {}",
        String::from_utf8_lossy(&malformed.stderr)
    );
    let data: serde_json::Value =
        serde_json::from_slice(&fs::read(out.join("visualizer/data.json")).unwrap()).unwrap();
    assert_eq!(
        data["decisionCards"],
        serde_json::json!({"summary": {}, "cards": []})
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn visualizer_rejects_invalid_utf8_sidecars_without_mutating_old_output() {
    for (game, sidecars) in [
        ("hsr", &["hsr_banner_plan.json"][..]),
        (
            "zzz",
            &[
                "zzz_endgame_phase_overrides.json",
                "zzz_banner_plan.json",
                "decision_cards.json",
            ][..],
        ),
    ] {
        let root = temp_output(&format!("{game}-visualizer-invalid-utf8-root"));
        let out = root.join("中文 old output");
        let exported = export(game, Some(&fixture(game)), &out);
        assert!(
            exported.status.success(),
            "{game} export failed: {}",
            String::from_utf8_lossy(&exported.stderr)
        );
        fs::write(
            out.join("visualizer/strict-utf8-sentinel.txt"),
            "old visualizer",
        )
        .unwrap();
        let old_data = fs::read(out.join("visualizer/data.json")).unwrap();
        let old_manifest = fs::read(out.join("artifact_manifest.json")).unwrap();
        let old_hub =
            (game == "zzz").then(|| fs::read(root.join("visualizer/index.html")).unwrap());

        for sidecar in sidecars {
            fs::write(out.join(sidecar), [b'{', 0xff, b'}']).unwrap();
            let result = visualizer(game, &out);
            assert_eq!(
                result.status.code(),
                Some(1),
                "{game} {sidecar} unexpectedly accepted invalid UTF-8"
            );
            let stderr = String::from_utf8_lossy(&result.stderr);
            assert!(
                stderr.contains("invalid UTF-8") && stderr.contains(sidecar),
                "unexpected {game} {sidecar} error: {stderr}"
            );
            assert_eq!(
                fs::read_to_string(out.join("visualizer/strict-utf8-sentinel.txt")).unwrap(),
                "old visualizer"
            );
            assert_eq!(
                fs::read(out.join("visualizer/data.json")).unwrap(),
                old_data
            );
            assert_eq!(
                fs::read(out.join("artifact_manifest.json")).unwrap(),
                old_manifest
            );
            if let Some(expected) = &old_hub {
                assert_eq!(
                    fs::read(root.join("visualizer/index.html")).unwrap(),
                    *expected
                );
            }
            assert_no_transaction_residue(&root, "中文 old output");
            fs::remove_file(out.join(sidecar)).unwrap();
        }
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn zzz_visualizer_rejects_a_symlinked_visualizer_directory() {
    let root = temp_output("zzz-visualizer-symlink-root");
    let out = root.join("out");
    let external = root.join("external");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(exported.status.success());
    fs::create_dir_all(&external).unwrap();
    fs::write(external.join("sentinel.txt"), "outside").unwrap();
    fs::remove_dir_all(out.join("visualizer")).unwrap();

    #[cfg(windows)]
    let linked = std::os::windows::fs::symlink_dir(&external, out.join("visualizer"));
    #[cfg(unix)]
    let linked = std::os::unix::fs::symlink(&external, out.join("visualizer"));
    if let Err(error) = linked {
        if error.kind() == std::io::ErrorKind::PermissionDenied
            || error.raw_os_error() == Some(1314)
        {
            fs::remove_dir_all(root).unwrap();
            return;
        }
        panic!("failed to create test symlink: {error}");
    }

    let result = visualizer("zzz", &out);
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).contains("unsafe directory path"));
    assert_eq!(
        fs::read_to_string(external.join("sentinel.txt")).unwrap(),
        "outside"
    );
    fs::remove_dir(out.join("visualizer")).unwrap();
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_reexport_removes_obsolete_managed_but_preserves_unmanaged_and_sidecars() {
    let root = temp_output("zzz-reexport-ownership-root");
    let out = root.join("out");
    let first = export("zzz", Some(&fixture("zzz")), &out);
    assert!(first.status.success());
    fs::write(out.join("obsolete-managed.txt"), "obsolete").unwrap();
    fs::write(out.join("keep-me.txt"), "unmanaged").unwrap();
    fs::write(
        out.join("decision_cards.json"),
        r#"{"summary":{},"cards":[]}"#,
    )
    .unwrap();
    let manifest_path = out.join("artifact_manifest.json");
    let mut manifest: Vec<serde_json::Value> =
        serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
    manifest.push(serde_json::json!({
        "path":"obsolete-managed.txt", "bytes":8, "sha256":"fixture"
    }));
    fs::write(
        &manifest_path,
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();

    let second = export("zzz", Some(&fixture("zzz")), &out);
    assert!(
        second.status.success(),
        "{}",
        String::from_utf8_lossy(&second.stderr)
    );
    assert!(!out.join("obsolete-managed.txt").exists());
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "unmanaged"
    );
    assert!(out.join("decision_cards.json").is_file());
    let refreshed = fs::read_to_string(&manifest_path).unwrap();
    assert!(!refreshed.contains("obsolete-managed.txt"));
    assert!(!refreshed.contains("keep-me.txt"));
    assert!(!refreshed.contains("decision_cards.json"));
    assert_no_transaction_residue(&root, "out");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn invalid_existing_manifest_fails_without_changing_output() {
    let root = temp_output("invalid-manifest-ownership-root");
    let out = root.join("out");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(exported.status.success());
    fs::write(out.join("keep-me.txt"), "unmanaged").unwrap();
    fs::write(out.join("artifact_manifest.json"), "{broken").unwrap();
    let old_data = fs::read(out.join("visualizer/data.json")).unwrap();

    let result = visualizer("zzz", &out);
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).contains("invalid existing artifact manifest"));
    assert_eq!(
        fs::read(out.join("visualizer/data.json")).unwrap(),
        old_data
    );
    assert_eq!(
        fs::read_to_string(out.join("artifact_manifest.json")).unwrap(),
        "{broken"
    );
    assert_eq!(
        fs::read_to_string(out.join("keep-me.txt")).unwrap(),
        "unmanaged"
    );
    assert_no_transaction_residue(&root, "out");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_hub_failure_before_swap_keeps_the_old_hub_complete() {
    let root = temp_output("zzz-hub-rollback-root");
    let out = root.join("out_zzz");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(exported.status.success());
    let hub = root.join("visualizer");
    let old_index = fs::read(hub.join("index.html")).unwrap();
    fs::write(hub.join("stale.txt"), "old-hub-stale").unwrap();

    let result = Command::new(binary())
        .args(["zzz", "visualizer", "--out"])
        .arg(&out)
        .env("MIHO_TEST_FAIL_HUB_TRANSACTION_BEFORE_SWAP", "1")
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).contains("Hub transaction failure"));
    assert_eq!(fs::read(hub.join("index.html")).unwrap(), old_index);
    assert_eq!(
        fs::read_to_string(hub.join("stale.txt")).unwrap(),
        "old-hub-stale"
    );
    assert_no_transaction_residue(&root, "visualizer");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn zzz_unsafe_hub_target_is_rejected_before_output_mutation() {
    let root = temp_output("zzz-unsafe-hub-preflight-root");
    let out = root.join("out_zzz");
    let exported = export("zzz", Some(&fixture("zzz")), &out);
    assert!(exported.status.success());

    let old_data = fs::read(out.join("visualizer/data.json")).unwrap();
    let old_manifest = fs::read(out.join("artifact_manifest.json")).unwrap();
    fs::write(
        out.join("decision_cards.json"),
        r#"{"summary":{"preflight_marker":"must-not-be-installed"},"cards":[]}"#,
    )
    .unwrap();
    let hub = root.join("visualizer");
    fs::remove_dir_all(&hub).unwrap();
    fs::write(&hub, "unsafe-hub-file").unwrap();

    let result = visualizer("zzz", &out);
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).contains("unsafe hub directory"));
    assert_eq!(
        fs::read(out.join("visualizer/data.json")).unwrap(),
        old_data
    );
    assert_eq!(
        fs::read(out.join("artifact_manifest.json")).unwrap(),
        old_manifest
    );
    assert_eq!(fs::read_to_string(&hub).unwrap(), "unsafe-hub-file");
    assert_no_transaction_residue(&root, "out_zzz");
    assert_no_transaction_residue(&root, "visualizer");
    fs::remove_dir_all(root).unwrap();
}
