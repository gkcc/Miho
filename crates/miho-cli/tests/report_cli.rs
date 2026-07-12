//! Binary-level contract for the evidence-first V1 report commands.

use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT_ID: AtomicU64 = AtomicU64::new(0);
const FIXED_CLOCK: &str = "2026-07-12T13:14:15";

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_miho")
}

fn fixture_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/evidence_v1_contract")
}

fn temp_root(label: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "miho-report-cli-{label}-{}-{}",
        std::process::id(),
        NEXT_ID.fetch_add(1, Ordering::Relaxed)
    ));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    path
}

fn report_command(command: &str, box_path: &Path, data_dir: &Path) -> Command {
    let mut process = Command::new(binary());
    process
        .args(["zzz", command, "--box"])
        .arg(box_path)
        .arg("--out")
        .arg(data_dir)
        .env("MIHO_REPORT_LOCAL_DATETIME", FIXED_CLOCK);
    process
}

fn run(command: &mut Command) -> Output {
    command.output().expect("miho binary should start")
}

fn normalized(path: &Path, data_dir: &Path) -> String {
    let team_source = data_dir.join("team_rank_dedup_unordered.csv");
    fs::read_to_string(path)
        .unwrap()
        .trim_start_matches('\u{feff}')
        .replace("\r\n", "\n")
        .replace(
            team_source.to_string_lossy().as_ref(),
            "<ROOT>\\input\\data\\team_rank_dedup_unordered.csv",
        )
        .replace(FIXED_CLOCK, "<GENERATED_AT>")
}

fn expected(name: &str) -> String {
    fs::read_to_string(fixture_root().join("expected").join(name))
        .unwrap()
        .trim_start_matches('\u{feff}')
        .replace("\r\n", "\n")
}

fn copy_data(target: &Path) {
    fs::create_dir_all(target).unwrap();
    let source = fixture_root().join("input/data");
    for name in [
        "team_rank_dedup_unordered.csv",
        "name_map.csv",
        "prydwen_tier_current.csv",
    ] {
        fs::copy(source.join(name), target.join(name)).unwrap();
    }
}

fn decision_fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/decision_legacy_v0_contract")
}

fn pull_value_fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/pull_value_v1_contract")
}

fn copy_pull_value_inputs(target: &Path) {
    let source = pull_value_fixture().join("input");
    fs::create_dir_all(target.join("data")).unwrap();
    fs::create_dir_all(target.join("mechanism_notes")).unwrap();
    for name in ["box.json", "plan.json", "baseline.json"] {
        fs::copy(source.join(name), target.join(name)).unwrap();
    }
    for name in [
        "team_rank_dedup_unordered.csv",
        "name_map.csv",
        "prydwen_tier_current.csv",
        "character_usage_long.csv",
    ] {
        fs::copy(
            source.join("data").join(name),
            target.join("data").join(name),
        )
        .unwrap();
    }
    for name in ["alpha.yaml", "beta.yaml", "delta.yaml", "epsilon.yaml"] {
        fs::copy(
            source.join("mechanism_notes").join(name),
            target.join("mechanism_notes").join(name),
        )
        .unwrap();
    }
}

fn pull_value_command(root: &Path) -> Command {
    let mut process = report_command("pull-value", &root.join("box.json"), &root.join("data"));
    process
        .arg("--plan")
        .arg(root.join("plan.json"))
        .arg("--mechanism-notes-dir")
        .arg(root.join("mechanism_notes"))
        .arg("--decision-baseline")
        .arg(root.join("baseline.json"));
    process
}

fn normalized_pull_value(path: &Path, runtime_root: &Path) -> String {
    fs::read_to_string(path)
        .unwrap()
        .replace("\r\n", "\n")
        .replace(runtime_root.to_string_lossy().as_ref(), "<ROOT>")
}

fn copy_decision_data(target: &Path) {
    fs::create_dir_all(target).unwrap();
    for name in [
        "prydwen_tier_current.csv",
        "prydwen_tier_history.csv",
        "character_usage_long.csv",
        "team_rank_raw.csv",
        "name_map.csv",
        "prydwen_tier_changelog_history.csv",
    ] {
        fs::copy(
            decision_fixture().join("input/data").join(name),
            target.join(name),
        )
        .unwrap();
    }
}

#[test]
fn explicit_legacy_decision_matches_goldens_and_preserves_unmanaged_files() {
    let root = temp_root("legacy-decision");
    let data = root.join("out");
    copy_decision_data(&data);
    let manifest = data.join("artifact_manifest.json");
    let visualizer = data.join("visualizer/data.json");
    fs::write(&manifest, b"manifest-before").unwrap();
    fs::create_dir_all(visualizer.parent().unwrap()).unwrap();
    fs::write(&visualizer, b"visualizer-before").unwrap();
    let result = run(Command::new(binary())
        .args(["zzz", "decision", "--method", "legacy-v0", "--box"])
        .arg(decision_fixture().join("input/box.yaml"))
        .arg("--out")
        .arg(&data)
        .arg("--rules")
        .arg(decision_fixture().join("input/rules.yaml"))
        .env("MIHO_REPORT_LOCAL_DATETIME", FIXED_CLOCK));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(String::from_utf8_lossy(&result.stderr).contains("compatibility only"));
    let actual_json = fs::read_to_string(data.join("decision_cards.json"))
        .unwrap()
        .replace("\r\n", "\n");
    let expected_json = fs::read_to_string(decision_fixture().join("expected/decision_cards.json"))
        .unwrap()
        .replace("\r\n", "\n");
    assert_eq!(actual_json, expected_json);
    let actual_md = fs::read_to_string(data.join("decision_report.md"))
        .unwrap()
        .replace("\r\n", "\n")
        .replace(FIXED_CLOCK, "<GENERATED_AT>");
    let expected_md = fs::read_to_string(decision_fixture().join("expected/decision_report.md"))
        .unwrap()
        .replace("\r\n", "\n");
    assert_eq!(actual_md, expected_md);
    assert_eq!(fs::read(manifest).unwrap(), b"manifest-before");
    assert_eq!(fs::read(visualizer).unwrap(), b"visualizer-before");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn legacy_decision_strict_failure_keeps_both_old_outputs() {
    let root = temp_root("legacy-decision-failure");
    let data = root.join("out");
    copy_decision_data(&data);
    fs::write(data.join("decision_cards.json"), b"old-json").unwrap();
    fs::write(data.join("decision_report.md"), b"old-markdown").unwrap();
    fs::write(
        data.join("prydwen_tier_current.csv"),
        b"character_slug,tier_mode,rating\nbad,sd,NaN\n",
    )
    .unwrap();
    let result = run(Command::new(binary())
        .args(["zzz", "decision", "--method", "legacy-v0", "--box"])
        .arg(decision_fixture().join("input/box.yaml"))
        .arg("--out")
        .arg(&data)
        .arg("--rules")
        .arg(decision_fixture().join("input/rules.yaml"))
        .env("MIHO_REPORT_LOCAL_DATETIME", FIXED_CLOCK));
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).starts_with("decision failed:"));
    assert_eq!(
        fs::read(data.join("decision_cards.json")).unwrap(),
        b"old-json"
    );
    assert_eq!(
        fs::read(data.join("decision_report.md")).unwrap(),
        b"old-markdown"
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn evidence_and_coverage_match_goldens_across_distinct_output_parents() {
    let root = temp_root("golden");
    let data = root.join("input").join("data");
    copy_data(&data);
    let box_path = fixture_root().join("input/box.json");
    let plan_path = fixture_root().join("input/plan.json");
    let manifest_path = data.join("artifact_manifest.json");
    let manifest = br#"[{"path":"owned-export.csv","sha256":"unchanged"}]"#;
    fs::write(&manifest_path, manifest).unwrap();
    let private_visualizer = data.join("visualizer/private.txt");
    fs::create_dir_all(private_visualizer.parent().unwrap()).unwrap();
    fs::write(&private_visualizer, b"preserve me").unwrap();

    let evidence_output = root.join("evidence/evidence_pool_summary.md");
    let evidence = run(report_command("evidence", &box_path, &data)
        .arg("--plan")
        .arg(&plan_path)
        .args(["--plan-status", "current", "--include-missing", "--output"])
        .arg(&evidence_output));
    assert!(
        evidence.status.success(),
        "{}",
        String::from_utf8_lossy(&evidence.stderr)
    );

    let current = root.join("current/current_box_team_coverage.md");
    let target = root.join("target/target_box_team_coverage.md");
    let aggregate = root.join("aggregate/team_signature_aggregates.csv");
    let coverage = run(report_command("coverage", &box_path, &data)
        .arg("--plan")
        .arg(&plan_path)
        .args(["--plan-status", "current", "--current-output"])
        .arg(&current)
        .arg("--target-output")
        .arg(&target)
        .arg("--aggregate-output")
        .arg(&aggregate));
    assert!(
        coverage.status.success(),
        "{}",
        String::from_utf8_lossy(&coverage.stderr)
    );

    for (actual, name) in [
        (&evidence_output, "evidence_pool_summary.md"),
        (&current, "current_box_team_coverage.md"),
        (&target, "target_box_team_coverage.md"),
        (&aggregate, "team_signature_aggregates.csv"),
    ] {
        assert_eq!(normalized(actual, &data), expected(name), "{name}");
    }
    assert_eq!(fs::read(&manifest_path).unwrap(), manifest);
    assert_eq!(fs::read(&private_visualizer).unwrap(), b"preserve me");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn report_exit_codes_and_failure_prefixes_are_command_specific() {
    let missing_argument = run(Command::new(binary()).args(["zzz", "evidence"]));
    assert_eq!(missing_argument.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&missing_argument.stderr).contains("--box"));

    let missing_method = run(Command::new(binary()).args(["zzz", "decision", "--box", "box.yaml"]));
    assert_eq!(missing_method.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&missing_method.stderr).contains("--method"));

    let missing_pull_box = run(Command::new(binary()).args(["zzz", "pull-value"]));
    assert_eq!(missing_pull_box.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&missing_pull_box.stderr).contains("--box"));

    let root = temp_root("failure-prefix");
    let runtime_failure = run(report_command(
        "coverage",
        &root.join("missing-box.json"),
        &fixture_root().join("input/data"),
    )
    .arg("--current-output")
    .arg(root.join("current.md")));
    assert_eq!(runtime_failure.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&runtime_failure.stderr).starts_with("coverage failed:"));

    let pull_runtime_failure = run(Command::new(binary())
        .args(["zzz", "pull-value", "--box"])
        .arg(root.join("missing-box.json"))
        .arg("--out")
        .arg(root.join("missing-data")));
    assert_eq!(pull_runtime_failure.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&pull_runtime_failure.stderr).starts_with("pull-value failed:"));

    let gated_review_packet = run(Command::new(binary())
        .args(["zzz", "review-packet", "--box"])
        .arg(root.join("missing-box.json")));
    assert_eq!(gated_review_packet.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&gated_review_packet.stderr).starts_with("review-packet failed:")
    );
    assert!(String::from_utf8_lossy(&gated_review_packet.stderr).contains("not yet enabled"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn coverage_rejects_colliding_paths_without_changing_existing_files() {
    let root = temp_root("collision");
    let shared = root.join("shared.md");
    let aggregate = root.join("aggregate.csv");
    fs::write(&shared, b"old-shared").unwrap();
    fs::write(&aggregate, b"old-aggregate").unwrap();
    let result = run(report_command(
        "coverage",
        &fixture_root().join("input/box.json"),
        &fixture_root().join("input/data"),
    )
    .arg("--current-output")
    .arg(&shared)
    .arg("--target-output")
    .arg(&shared)
    .arg("--aggregate-output")
    .arg(&aggregate));
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).starts_with("coverage failed:"));
    assert_eq!(fs::read(&shared).unwrap(), b"old-shared");
    assert_eq!(fs::read(&aggregate).unwrap(), b"old-aggregate");
    assert_eq!(fs::read_dir(&root).unwrap().count(), 2);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn evidence_accepts_utf8_bom_yaml_box_and_plan_configs() {
    let root = temp_root("yaml");
    let box_path = root.join("box.yaml");
    let plan_path = root.join("plan.yaml");
    fs::write(
        &box_path,
        "\u{feff}owned: [lucy, miyabi, nicole-demara]\nbuilt: {}\nbuilds:\n  lucy: true\n  miyabi: true\n  nicole-demara: true\nbangboo_owned: [biggest-fan]\n",
    )
    .unwrap();
    fs::write(
        &plan_path,
        "\u{feff}phases:\n  - status: next\n    start_at: 2026-07-12 13:00:00\n    end_at: 2026-07-12 14:00:00\n    characters:\n      - slug: sun-na\n",
    )
    .unwrap();
    let output = root.join("report.md");
    let result = run(
        report_command("evidence", &box_path, &fixture_root().join("input/data"))
            .arg("--plan")
            .arg(&plan_path)
            .args(["--plan-status", "current", "--output"])
            .arg(&output),
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let report = fs::read_to_string(output).unwrap();
    assert!(report.contains("计划角色：sunna"));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn pull_value_default_dual_reports_match_python_goldens_without_touching_sidecars() {
    let runtime = temp_root("pull-value-golden");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    let manifest = root.join("data/artifact_manifest.json");
    let visualizer = root.join("data/visualizer/data.json");
    let decision = root.join("data/decision_cards.json");
    fs::write(&manifest, b"manifest-before").unwrap();
    fs::create_dir_all(visualizer.parent().unwrap()).unwrap();
    fs::write(&visualizer, b"visualizer-before").unwrap();
    fs::write(&decision, b"decision-before").unwrap();

    let result = run(&mut pull_value_command(&root));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    for status in ["current", "next"] {
        let actual = normalized_pull_value(
            &root.join(format!("data/{status}_pull_value_report.md")),
            &runtime,
        );
        let expected = fs::read_to_string(
            pull_value_fixture().join(format!("expected/{status}_pull_value_report.md")),
        )
        .unwrap()
        .replace("\r\n", "\n");
        assert_eq!(actual, expected, "{status} pull-value report");
    }
    assert!(!root.join("data/pull_value_report.md").exists());
    assert_eq!(fs::read(manifest).unwrap(), b"manifest-before");
    assert_eq!(fs::read(visualizer).unwrap(), b"visualizer-before");
    assert_eq!(fs::read(decision).unwrap(), b"decision-before");
    fs::remove_dir_all(runtime).unwrap();
}

#[test]
fn pull_value_explicit_output_combines_statuses_and_skips_broken_unrelated_notes() {
    let runtime = temp_root("pull-value-combined");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    fs::write(root.join("mechanism_notes/unrelated.yaml"), b"broken: [").unwrap();
    fs::write(
        root.join("mechanism_notes/alpha.json"),
        br#"{"source_quality":"json precedence"}"#,
    )
    .unwrap();
    let output = runtime.join("combined.md");
    let result = run(pull_value_command(&root).arg("--output").arg(&output));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let report = fs::read_to_string(output).unwrap();
    assert!(report.contains("planned_slugs：alpha, beta, gamma, nova, low-a, delta, epsilon, zeta"));
    assert!(report.contains("source_quality：json precedence"));
    assert!(!root.join("data/current_pull_value_report.md").exists());
    assert!(!root.join("data/next_pull_value_report.md").exists());
    fs::remove_dir_all(runtime).unwrap();
}

#[test]
fn pull_value_rejects_status_output_collisions_before_mutation() {
    let runtime = temp_root("pull-value-collision");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    let output = root.join("data/current_pull_value_report.md");
    fs::write(&output, b"old-report").unwrap();
    let result = run(pull_value_command(&root).args(["--plan-status", "current,current"]));
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).starts_with("pull-value failed:"));
    assert_eq!(fs::read(output).unwrap(), b"old-report");
    fs::remove_dir_all(runtime).unwrap();
}

#[test]
fn pull_value_rejects_broken_earlier_candidate_note_even_when_json_would_override_it() {
    let runtime = temp_root("pull-value-note-layer");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    fs::write(root.join("mechanism_notes/alpha.yml"), b"broken: [").unwrap();
    fs::write(
        root.join("mechanism_notes/alpha.json"),
        br#"{"source_quality":"valid final layer"}"#,
    )
    .unwrap();
    let output = runtime.join("combined.md");
    fs::write(&output, b"old-report").unwrap();
    let result = run(pull_value_command(&root).arg("--output").arg(&output));
    assert_eq!(result.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&result.stderr).starts_with("pull-value failed:"));
    assert_eq!(fs::read(output).unwrap(), b"old-report");
    fs::remove_dir_all(runtime).unwrap();
}

#[test]
fn pull_value_empty_candidate_set_does_not_read_any_mechanism_note() {
    let runtime = temp_root("pull-value-empty");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    fs::write(root.join("plan.json"), br#"{"phases":[]}"#).unwrap();
    fs::write(root.join("mechanism_notes/broken.yaml"), b"broken: [").unwrap();
    fs::create_dir(root.join("mechanism_notes/unreadable.json")).unwrap();
    let output = runtime.join("empty.md");
    let result = run(pull_value_command(&root).arg("--output").arg(&output));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let report = fs::read_to_string(output).unwrap();
    assert!(report.contains("候选角色：0；planned_slugs：none"));
    fs::remove_dir_all(runtime).unwrap();
}

#[test]
fn pull_value_accepts_all_optional_inputs_missing() {
    let runtime = temp_root("pull-value-optional");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    for path in [
        root.join("data/name_map.csv"),
        root.join("data/prydwen_tier_current.csv"),
        root.join("data/character_usage_long.csv"),
        root.join("baseline.json"),
    ] {
        fs::remove_file(path).unwrap();
    }
    fs::remove_dir_all(root.join("mechanism_notes")).unwrap();
    let output = runtime.join("optional.md");
    let result = run(pull_value_command(&root).arg("--output").arg(&output));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(fs::read_to_string(output)
        .unwrap()
        .contains("# 绝区零 Pull Value Report"));
    fs::remove_dir_all(runtime).unwrap();
}

#[test]
fn pull_value_accepts_windows_case_insensitive_note_extensions() {
    let runtime = temp_root("pull-value-uppercase-note");
    let root = runtime.join("input");
    copy_pull_value_inputs(&root);
    fs::rename(
        root.join("mechanism_notes/alpha.yaml"),
        root.join("mechanism_notes/alpha.YAML"),
    )
    .unwrap();
    let output = runtime.join("uppercase.md");
    let result = run(pull_value_command(&root)
        .args(["--plan-status", "current"])
        .arg("--output")
        .arg(&output));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let report = fs::read_to_string(output).unwrap();
    assert!(report.contains("source_quality：identity=official；breakpoints=reviewed"));
    fs::remove_dir_all(runtime).unwrap();
}
