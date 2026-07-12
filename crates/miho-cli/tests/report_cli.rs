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
