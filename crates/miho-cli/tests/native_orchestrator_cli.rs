use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    thread,
    time::{Duration, Instant},
};

use miho_app::WorkspaceWriteLease;
use serde_json::Value;

#[test]
fn fixture_runner_succeeds_without_python_and_commits_verified_state() {
    let root = workspace("success");
    seed_workspace(&root, true);
    let output = run_fixture(&root);
    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(root.join("out/artifact_manifest.json").is_file());
    assert!(root.join("out_zzz/artifact_manifest.json").is_file());
    assert!(root.join("visualizer/index.html").is_file());
    for path in [
        "out_zzz/current_box_team_coverage.md",
        "out_zzz/target_box_team_coverage.md",
        "out_zzz/team_signature_aggregates.csv",
        "out_zzz/current_pull_value_report.md",
        "out_zzz/next_pull_value_report.md",
        "out_zzz/current_gpt_pull_reviewer_packet.md",
        "out_zzz/next_gpt_pull_reviewer_packet.md",
    ] {
        assert!(root.join(path).is_file(), "missing {path}");
    }
    let state = json(&root.join(".miho/update-state-v1.json"));
    assert_eq!(state["schema_version"], "miho-update-state-v1");
    assert!(state["games"]["hsr"]["artifacts"]
        .as_array()
        .is_some_and(|items| !items.is_empty()));
    assert!(state["games"]["zzz"]["artifacts"]
        .as_array()
        .is_some_and(|items| !items.is_empty()));
    let receipt = json(&root.join(".miho/last-update-receipt-v1.json"));
    assert_eq!(receipt["status"], "succeeded");
    assert_eq!(receipt["state_committed"], true);
    assert_eq!(receipt["receipt_committed"], true);
    let serialized = serde_json::to_string(&receipt).unwrap();
    assert!(!serialized.contains(&root.to_string_lossy().to_string()));
    let healthy = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "health", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(
        healthy.status.success(),
        "{}",
        String::from_utf8_lossy(&healthy.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&healthy.stdout).unwrap()["healthy"],
        true
    );
    let artifact_path = root.join("out/export_report.md");
    let original = fs::read(&artifact_path).unwrap();
    let mut tampered = original.clone();
    tampered[0] ^= 1;
    fs::write(&artifact_path, &tampered).unwrap();
    let unhealthy = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "health", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(unhealthy.status.code(), Some(1));
    assert_eq!(
        serde_json::from_slice::<Value>(&unhealthy.stdout).unwrap()["failure"]["code"],
        "update.health_artifact_invalid"
    );
    fs::write(&artifact_path, original).unwrap();
    let state_path = root.join(".miho/update-state-v1.json");
    let mut state = json(&state_path);
    for game in ["hsr", "zzz"] {
        for artifact in state["games"][game]["artifacts"].as_array_mut().unwrap() {
            artifact.as_object_mut().unwrap().remove("sha256");
        }
    }
    fs::write(&state_path, serde_json::to_vec_pretty(&state).unwrap()).unwrap();
    let missing_hash = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "health", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(missing_hash.status.code(), Some(1));
    assert_eq!(
        serde_json::from_slice::<Value>(&missing_hash.stdout).unwrap()["failure"]["code"],
        "update.state_invalid"
    );
    cleanup(&root);
}

#[test]
fn force_flag_is_preserved_in_the_public_receipt() {
    let root = workspace("force");
    seed_workspace(&root, true);
    let output = run_fixture_args(&root, &["--force"]);
    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let receipt = json(&root.join(".miho/last-update-receipt-v1.json"));
    assert_eq!(receipt["status"], "succeeded");
    assert_eq!(receipt["force"], true);
    assert_eq!(receipt["games"][0]["status"], "succeeded");
    assert_eq!(receipt["games"][1]["status"], "succeeded");
    cleanup(&root);
}

#[test]
fn custom_top_level_outputs_are_reflected_in_the_generated_hub() {
    let root = workspace("custom-output-hub");
    seed_workspace(&root, true);
    let config_path = root.join("configs/update_v1.json");
    let config = fs::read_to_string(&config_path)
        .unwrap()
        .replace("\"output\":\"out\"", "\"output\":\"hsr_data\"")
        .replace("\"output\":\"out_zzz\"", "\"output\":\"zzz_data\"");
    fs::write(&config_path, config).unwrap();

    let output = run_fixture(&root);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(root.join("hsr_data/artifact_manifest.json").is_file());
    assert!(root.join("zzz_data/artifact_manifest.json").is_file());
    let hub = fs::read_to_string(root.join("visualizer/index.html")).unwrap();
    assert!(hub.contains("../hsr_data/visualizer/index.html"), "{hub}");
    assert!(hub.contains("../zzz_data/visualizer/index.html"), "{hub}");
    assert!(!hub.contains("../out/visualizer/index.html"), "{hub}");
    cleanup(&root);
}

#[test]
fn health_rejects_an_unsafe_canonical_attempt_identifier() {
    let root = workspace("unsafe-canonical-attempt");
    seed_workspace(&root, true);
    let output = run_fixture(&root);
    assert!(output.status.success());
    let receipt_path = root.join(".miho/last-update-receipt-v1.json");
    let original = json(&receipt_path);
    for (attempt_id, remove_games) in [
        ("../CANARY_PATH", false),
        ("forged-valid-id", true),
        (original["attempt_id"].as_str().unwrap(), true),
    ] {
        let mut receipt = original.clone();
        receipt["attempt_id"] = Value::String(attempt_id.to_owned());
        if remove_games {
            receipt["games"] = Value::Array(Vec::new());
        }
        fs::write(&receipt_path, serde_json::to_vec_pretty(&receipt).unwrap()).unwrap();

        let health = Command::new(env!("CARGO_BIN_EXE_miho"))
            .args(["update", "health", "--workspace", root.to_str().unwrap()])
            .output()
            .unwrap();
        assert_eq!(health.status.code(), Some(1));
        let payload = serde_json::from_slice::<Value>(&health.stdout).unwrap();
        assert_eq!(payload["healthy"], false);
        assert_eq!(payload["failure"]["code"], "update.health_receipt_invalid");
        assert!(!String::from_utf8_lossy(&health.stdout).contains("CANARY_PATH"));
    }
    cleanup(&root);
}

#[cfg(windows)]
#[test]
fn health_rejects_attempt_history_junctions_outside_the_workspace() {
    let root = workspace("attempt-history-junction");
    let external_root = workspace("attempt-history-junction-external");
    seed_workspace(&root, true);
    let output = run_fixture_args(&root, &["--skip-zzz"]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );

    let attempts = root.join(".miho").join("update-attempts");
    let canonical_before = fs::read(root.join(".miho/last-update-receipt-v1.json")).unwrap();
    let external_attempts = external_root.join("attempts");
    fs::rename(&attempts, &external_attempts).unwrap();
    let linked = Command::new("cmd.exe")
        .args(["/d", "/c", "mklink", "/J"])
        .arg(&attempts)
        .arg(&external_attempts)
        .output()
        .unwrap();
    assert!(
        linked.status.success(),
        "mklink failed: stdout={} stderr={}",
        String::from_utf8_lossy(&linked.stdout),
        String::from_utf8_lossy(&linked.stderr)
    );

    let health = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "update",
            "health",
            "--workspace",
            root.to_str().unwrap(),
            "--skip-zzz",
        ])
        .output()
        .unwrap();
    assert_eq!(health.status.code(), Some(1));
    let payload = serde_json::from_slice::<Value>(&health.stdout).unwrap();
    assert_eq!(payload["healthy"], false);
    assert_eq!(payload["failure"]["code"], "update.health_receipt_invalid");

    let rerun = run_fixture_args(&root, &["--skip-zzz"]);
    assert_eq!(rerun.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&rerun.stderr).contains("update.receipt_history_invalid"));
    assert_eq!(
        fs::read(root.join(".miho/last-update-receipt-v1.json")).unwrap(),
        canonical_before
    );

    fs::remove_dir(&attempts).unwrap();
    cleanup(&external_root);
    cleanup(&root);
}

#[test]
fn independent_hsr_and_zzz_success_generations_form_one_healthy_workspace() {
    let root = workspace("split-generations");
    seed_workspace(&root, true);
    let hsr = run_fixture_args(&root, &["--skip-zzz"]);
    assert!(
        hsr.status.success(),
        "{}",
        String::from_utf8_lossy(&hsr.stderr)
    );
    let zzz = run_fixture_args(&root, &["--skip-hsr"]);
    assert!(
        zzz.status.success(),
        "{}",
        String::from_utf8_lossy(&zzz.stderr)
    );
    let health = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "health", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(
        health.status.success(),
        "{}",
        String::from_utf8_lossy(&health.stderr)
    );
    assert_eq!(
        serde_json::from_slice::<Value>(&health.stdout).unwrap()["healthy"],
        true
    );
    cleanup(&root);
}

#[test]
fn health_binds_every_required_generation_to_the_selected_config_bytes() {
    let root = workspace("config-identity");
    seed_workspace(&root, true);
    let output = run_fixture(&root);
    assert!(output.status.success());
    let config_path = root.join("configs/update_v1.json");
    let original_path = root.join("configs/original_update_v1.json");
    fs::copy(&config_path, &original_path).unwrap();
    let changed = fs::read_to_string(&config_path).unwrap().replacen(
        "\"revision\":\"main\"",
        "\"revision\":\"next\"",
        1,
    );
    fs::write(&config_path, changed).unwrap();

    let stale = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "health", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(stale.status.code(), Some(1));
    assert_eq!(
        serde_json::from_slice::<Value>(&stale.stdout).unwrap()["failure"]["code"],
        "update.health_config_mismatch"
    );

    let original = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "update",
            "health",
            "--workspace",
            root.to_str().unwrap(),
            "--config",
            "configs/original_update_v1.json",
        ])
        .output()
        .unwrap();
    assert!(
        original.status.success(),
        "{}",
        String::from_utf8_lossy(&original.stderr)
    );
    cleanup(&root);
}

#[test]
fn missing_box_is_exit_one_and_never_advances_state_or_date_marker() {
    let root = workspace("missing-box");
    seed_workspace(&root, false);
    fs::create_dir_all(root.join(".miho")).unwrap();
    let marker = root.join(".miho/update_local_date.txt");
    fs::write(&marker, b"2000-01-01\n").unwrap();
    let output = run_fixture(&root);
    assert_eq!(output.status.code(), Some(1));
    assert!(!root.join(".miho/update-state-v1.json").exists());
    assert_eq!(fs::read(&marker).unwrap(), b"2000-01-01\n");
    let receipt = json(&root.join(".miho/last-update-receipt-v1.json"));
    assert_eq!(receipt["status"], "partial");
    assert_eq!(receipt["state_committed"], false);
    assert_eq!(receipt["games"][1]["steps"][1]["status"], "failed");
    assert_eq!(receipt["games"][1]["steps"][2]["status"], "skipped");
    cleanup(&root);
}

#[test]
fn incomplete_supplemental_diagnostics_cannot_commit_success_state() {
    let root = workspace("degraded-source");
    seed_workspace(&root, true);
    let repository = repository_root();
    let empty_path = root.join("empty-path");
    fs::create_dir_all(&empty_path).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "update",
            "run",
            "--workspace",
            root.to_str().unwrap(),
            "--skip-hsr",
        ])
        .env("PATH", &empty_path)
        .env(
            "MIHO_ZZZ_OFFLINE_FIXTURE",
            repository.join("tests/fixtures/offline_zzz"),
        )
        .env(
            "MIHO_ZZZ_SUPPLEMENTAL_FIXTURE",
            repository.join("tests/fixtures/zzz_supplemental"),
        )
        // The lock identity must come from the absolute output parent, not
        // from an arbitrary ancestor working directory.
        .current_dir(root.parent().unwrap())
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(root.join("out_zzz/artifact_manifest.json").is_file());
    assert!(!root.join(".miho/update-state-v1.json").exists());
    let receipt = json(&root.join(".miho/last-update-receipt-v1.json"));
    assert_eq!(receipt["status"], "failed");
    assert_eq!(
        receipt["games"][1]["steps"][0]["failure"]["code"],
        "update.zzz_export.degraded"
    );
    cleanup(&root);
}

#[test]
fn both_games_skipped_is_a_business_failure_not_clap_usage() {
    let root = workspace("no-games");
    seed_workspace(&root, true);
    let output = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "update",
            "run",
            "--workspace",
            root.to_str().unwrap(),
            "--skip-hsr",
            "--skip-zzz",
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("update.no_games_selected"));
    assert!(!root.join(".miho/last-update-receipt-v1.json").exists());
    cleanup(&root);
}

#[test]
fn invalid_update_cli_usage_is_exit_two_and_never_enters_the_runner() {
    let missing_workspace = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "run"])
        .output()
        .unwrap();
    assert_eq!(missing_workspace.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&missing_workspace.stderr).contains("--workspace"));

    let unknown_option = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "update",
            "run",
            "--workspace",
            ".",
            "--unknown-update-option",
        ])
        .output()
        .unwrap();
    assert_eq!(unknown_option.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&unknown_option.stderr).contains("unexpected argument"));
}

#[test]
fn malformed_config_writes_a_path_safe_failure_receipt() {
    let root = workspace("bad-config");
    seed_workspace(&root, true);
    fs::write(root.join("configs/update_v1.json"), b"{broken").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "run", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    let receipt_path = root.join(".miho/last-update-receipt-v1.json");
    let receipt = json(&receipt_path);
    assert_eq!(receipt["status"], "failed");
    assert_eq!(
        receipt["games"][0]["steps"][0]["failure"]["code"],
        "update.config_invalid"
    );
    assert_eq!(
        receipt["games"][1]["steps"][0]["failure"]["code"],
        "update.config_invalid"
    );
    assert!(!root.join(".miho/update-state-v1.json").exists());
    assert!(!serde_json::to_string(&receipt)
        .unwrap()
        .contains(&root.to_string_lossy().to_string()));
    cleanup(&root);
}

#[test]
fn overlapping_game_outputs_are_rejected_before_any_export_or_state_commit() {
    let root = workspace("overlap");
    seed_workspace(&root, true);
    let config_path = root.join("configs/update_v1.json");
    let config = fs::read_to_string(&config_path)
        .unwrap()
        .replace("\"output\":\"out_zzz\"", "\"output\":\"OUT. \"");
    fs::write(&config_path, config).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "run", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(!root.join("out").exists());
    assert!(!root.join("OUT. ").exists());
    assert!(!root.join(".miho/update-state-v1.json").exists());
    let receipt = json(&root.join(".miho/last-update-receipt-v1.json"));
    assert_eq!(
        receipt["games"][0]["steps"][0]["failure"]["code"],
        "update.config_invalid"
    );
    cleanup(&root);
}

#[test]
fn non_ascii_output_aliases_are_rejected_before_the_runner_starts() {
    let root = workspace("unicode-output");
    seed_workspace(&root, true);
    let config_path = root.join("configs/update_v1.json");
    let config = fs::read_to_string(&config_path)
        .unwrap()
        .replace("\"output\":\"out\"", "\"output\":\"Öut\"")
        .replace("\"output\":\"out_zzz\"", "\"output\":\"öut\"");
    fs::write(&config_path, config).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args(["update", "run", "--workspace", root.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(!root.join("Öut").exists());
    assert!(!root.join("öut").exists());
    assert!(!root.join(".miho/update-state-v1.json").exists());
    let receipt = json(&root.join(".miho/last-update-receipt-v1.json"));
    assert_eq!(
        receipt["games"][0]["steps"][0]["failure"]["code"],
        "update.config_invalid"
    );
    cleanup(&root);
}

#[test]
fn direct_export_contends_on_the_same_workspace_lease_as_the_runner() {
    let root = workspace("direct-busy");
    seed_workspace(&root, true);
    let lease = WorkspaceWriteLease::acquire(&root).unwrap();
    let repository = repository_root();
    let output = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "zzz",
            "export",
            "--out",
            root.join("out_zzz").to_str().unwrap(),
        ])
        .env(
            "MIHO_OFFLINE_FIXTURE",
            repository.join("tests/fixtures/offline_zzz"),
        )
        .env(
            "MIHO_ZZZ_SUPPLEMENTAL_FIXTURE",
            repository.join("tests/fixtures/zzz_supplemental"),
        )
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&output.stderr).contains("workspace.write_busy"));
    assert!(!root.join("out_zzz").exists());
    let report = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "zzz",
            "coverage",
            "--box",
            root.join(".miho/zzz_box_state.json").to_str().unwrap(),
            "--out",
            root.join("out_zzz").to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(report.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&report.stderr).contains("workspace.write_busy"));
    let explicit = root.join("out_zzz/explicit.md");
    let explicit_report = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "zzz",
            "evidence",
            "--box",
            root.join(".miho/zzz_box_state.json").to_str().unwrap(),
            "--out",
            root.join("out_zzz").to_str().unwrap(),
            "--output",
            explicit.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(explicit_report.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&explicit_report.stderr).contains("workspace.write_busy"));
    assert!(!explicit.exists());
    assert!(!root.join("out_zzz/.miho").exists());
    let external_root = workspace("external-report");
    let external = external_root.join("report.md");
    let external_report = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "zzz",
            "evidence",
            "--box",
            root.join(".miho/zzz_box_state.json").to_str().unwrap(),
            "--out",
            root.join("out_zzz").to_str().unwrap(),
            "--output",
            external.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(external_report.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&external_report.stderr).contains("workspace.write_busy"));
    assert!(!external.exists());
    drop(lease);
    cleanup(&external_root);
    cleanup(&root);
}

#[test]
fn two_real_update_processes_contend_without_replacing_owner_evidence() {
    let root = workspace("two-update-processes");
    seed_workspace(&root, true);
    let pause = root.join("first-update.pause");
    fs::write(&pause, b"hold while the workspace lease is owned").unwrap();

    let mut owner_command = fixture_command(&root, &["--skip-zzz"]);
    owner_command.env("MIHO_UPDATE_TEST_PAUSE_FILE", &pause);
    let mut owner = owner_command.spawn().unwrap();
    let deadline = Instant::now() + Duration::from_secs(15);
    let owner_attempt = loop {
        assert!(
            owner.try_wait().unwrap().is_none(),
            "owner exited before reaching the debug synchronization gate"
        );
        let attempt_dir = root.join(".miho/update-attempts");
        let running = fs::read_dir(&attempt_dir).ok().and_then(|entries| {
            entries.filter_map(Result::ok).find_map(|entry| {
                let value = serde_json::from_slice::<Value>(&fs::read(entry.path()).ok()?).ok()?;
                (value["status"] == "running")
                    .then(|| value["attempt_id"].as_str().unwrap().to_owned())
            })
        });
        if let Some(attempt_id) = running {
            break attempt_id;
        }
        assert!(
            Instant::now() < deadline,
            "owner did not write its running receipt"
        );
        thread::sleep(Duration::from_millis(5));
    };

    let contender = fixture_command(&root, &["--skip-zzz"]).output().unwrap();
    assert_eq!(contender.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&contender.stderr).contains("workspace.write_busy"));
    assert!(!root.join(".miho/last-update-receipt-v1.json").exists());
    let running_receipts = fs::read_dir(root.join(".miho/update-attempts"))
        .unwrap()
        .filter_map(Result::ok)
        .collect::<Vec<_>>();
    assert_eq!(running_receipts.len(), 1);
    assert_eq!(
        json(&running_receipts[0].path())["attempt_id"],
        owner_attempt
    );

    fs::remove_file(&pause).unwrap();
    let owner_output = owner.wait_with_output().unwrap();
    assert!(
        owner_output.status.success(),
        "owner stderr: {}",
        String::from_utf8_lossy(&owner_output.stderr)
    );
    assert_eq!(
        json(&root.join(".miho/last-update-receipt-v1.json"))["attempt_id"],
        owner_attempt
    );
    let health = Command::new(env!("CARGO_BIN_EXE_miho"))
        .args([
            "update",
            "health",
            "--workspace",
            root.to_str().unwrap(),
            "--skip-zzz",
        ])
        .output()
        .unwrap();
    assert!(
        health.status.success(),
        "{}",
        String::from_utf8_lossy(&health.stderr)
    );
    cleanup(&root);
}

fn run_fixture(root: &Path) -> std::process::Output {
    run_fixture_args(root, &[])
}

fn run_fixture_args(root: &Path, extra: &[&str]) -> std::process::Output {
    fixture_command(root, extra).output().unwrap()
}

fn fixture_command(root: &Path, extra: &[&str]) -> Command {
    let repository = repository_root();
    let empty_path = root.join("empty-path");
    fs::create_dir_all(&empty_path).unwrap();
    let mut command = Command::new(env!("CARGO_BIN_EXE_miho"));
    command
        .args(["update", "run", "--workspace", root.to_str().unwrap()])
        .args(extra)
        .env("PATH", &empty_path)
        .env(
            "MIHO_HSR_OFFLINE_FIXTURE",
            repository.join("tests/fixtures/offline_hsr"),
        )
        .env(
            "MIHO_ZZZ_OFFLINE_FIXTURE",
            repository.join("tests/fixtures/offline_zzz"),
        )
        .env(
            "MIHO_HSR_SUPPLEMENTAL_FIXTURE",
            repository.join("tests/fixtures/hsr_supplemental"),
        )
        .env(
            "MIHO_ZZZ_SUPPLEMENTAL_FIXTURE",
            repository.join("tests/fixtures/zzz_supplemental_source"),
        )
        .env_remove("MIHO_UPDATE_TEST_PAUSE_FILE");
    command
}

fn seed_workspace(root: &Path, with_box: bool) {
    let repository = repository_root();
    fs::create_dir_all(root.join("configs/zzz_mechanism_notes")).unwrap();
    fs::copy(
        repository.join("configs/zzz_banner_plan.json"),
        root.join("configs/zzz_banner_plan.json"),
    )
    .unwrap();
    fs::copy(
        repository.join("configs/zzz_decision_baseline.json"),
        root.join("configs/zzz_decision_baseline.json"),
    )
    .unwrap();
    fs::write(
        root.join("configs/update_v1.json"),
        br#"{
  "schema_version":"miho-update-config-v1",
  "days":183,
  "hsr":{"output":"out","repo_id":"LvlUrArti/MocDataProcessed","revision":"main","modes":["moc"],"prydwen_top_n":100},
  "zzz":{"output":"out_zzz","repo_id":"LvlUrArti/ShiyuDataProcessed","revision":"main","modes":["sd"],"prydwen_top_n":100,"box":".miho/zzz_box_state.json","banner_plan":"configs/zzz_banner_plan.json","mechanism_notes":"configs/zzz_mechanism_notes","decision_baseline":"configs/zzz_decision_baseline.json"}
}
"#,
    )
    .unwrap();
    if with_box {
        fs::create_dir_all(root.join(".miho")).unwrap();
        fs::write(
            root.join(".miho/zzz_box_state.json"),
            br#"{"version":1,"updatedAt":"","owned":[],"buildSlug":"","builds":{}}
"#,
        )
        .unwrap();
    }
}

fn json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn workspace(label: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let id = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "miho-native-orchestrator-{label}-{}-{id}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    root
}

fn cleanup(root: &Path) {
    let _ = fs::remove_dir_all(root);
}
