use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
};

use chrono::{NaiveDateTime, Timelike};
use miho_app::{
    execute_task_result_v1, execute_task_v1, parse_task_intent_v1, AppInvocation, CoverageIntentV1,
    CoverageTaskV1, DecisionIntentV1, DecisionTaskV1, EvidenceIntentV1, EvidenceTaskV1, PullTaskV1,
    PullValueIntentV1, ReviewPacketIntentV1, TaskFailureV1, TaskIntentSpecV1, TaskIntentV1,
    TaskOperationV1, TaskReceiptV1, TaskRequestV1, TaskSpecV1, WorkspaceLayout,
    TASK_FAILURE_SCHEMA_V1, TASK_INTENT_SCHEMA_V1, TASK_RECEIPT_SCHEMA_V1,
};

static NEXT_ID: AtomicU64 = AtomicU64::new(0);
static ENV_LOCK: Mutex<()> = Mutex::new(());

fn fixed_datetime() -> NaiveDateTime {
    NaiveDateTime::parse_from_str("2026-07-13T09:10:11.123456789", "%Y-%m-%dT%H:%M:%S%.f").unwrap()
}

fn pull_fixture_datetime() -> NaiveDateTime {
    NaiveDateTime::parse_from_str("2026-07-12T13:14:15", "%Y-%m-%dT%H:%M:%S").unwrap()
}

fn review_fixture_datetime() -> NaiveDateTime {
    NaiveDateTime::parse_from_str("2026-07-13T09:10:11", "%Y-%m-%dT%H:%M:%S").unwrap()
}

fn temp_root(label: &str) -> PathBuf {
    let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!("miho-app-{label}-{}-{id}", std::process::id()));
    if root.exists() {
        fs::remove_dir_all(&root).unwrap();
    }
    fs::create_dir_all(&root).unwrap();
    root
}

fn copy_tree(source: &Path, target: &Path) {
    fs::create_dir_all(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy_tree(&source_path, &target_path);
        } else {
            fs::copy(source_path, target_path).unwrap();
        }
    }
}

fn fixture(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures")
        .join(name)
}

fn normalized_output(path: &Path, runtime_root: &Path) -> String {
    let root = runtime_root.to_string_lossy();
    fs::read_to_string(path)
        .unwrap()
        .replace("\r\n", "\n")
        .replace(&root.replace('\\', "\\\\"), "<ROOT>")
        .replace(root.as_ref(), "<ROOT>")
}

fn pull_workspace() -> (PathBuf, WorkspaceLayout, AppInvocation) {
    let root = temp_root("pull-workspace");
    copy_tree(
        &fixture("pull_value_v1_contract/input"),
        &root.join("input"),
    );
    let workspace = WorkspaceLayout {
        data_dir: PathBuf::from("input/data"),
        box_path: PathBuf::from("input/box.json"),
    };
    let invocation = AppInvocation::new(root.clone(), pull_fixture_datetime()).unwrap();
    (root, workspace, invocation)
}

#[test]
fn pathless_intent_schema_is_strict_and_parse_failures_are_structured() {
    let valid = serde_json::json!({
        "schema_version": TASK_INTENT_SCHEMA_V1,
        "task": {"operation": "evidence", "params": {}}
    });
    let intent = parse_task_intent_v1(&serde_json::to_vec(&valid).unwrap()).unwrap();
    assert_eq!(intent.operation(), TaskOperationV1::Evidence);
    assert_eq!(intent.schema_version, TASK_INTENT_SCHEMA_V1);

    for pointer in ["intent", "task", "parameters"] {
        let mut value = valid.clone();
        match pointer {
            "intent" => value["unknown"] = serde_json::json!(true),
            "task" => value["task"]["unknown"] = serde_json::json!(true),
            "parameters" => value["task"]["params"]["unknown"] = serde_json::json!(true),
            _ => unreachable!(),
        }
        let failure = parse_task_intent_v1(&serde_json::to_vec(&value).unwrap()).unwrap_err();
        assert_eq!(failure.code, "request.invalid", "{pointer} unknown field");
        assert_eq!(failure.operation, Some(TaskOperationV1::Evidence));
    }
    let mut unknown_variant = valid.clone();
    unknown_variant["task"]["operation"] = serde_json::json!("future");
    let failure = parse_task_intent_v1(&serde_json::to_vec(&unknown_variant).unwrap()).unwrap_err();
    assert_eq!(failure.code, "request.invalid");
    assert_eq!(failure.operation, None);

    let mut wrong_schema = valid;
    wrong_schema["schema_version"] = serde_json::json!("future");
    let failure = parse_task_intent_v1(&serde_json::to_vec(&wrong_schema).unwrap()).unwrap_err();
    assert_eq!(failure.code, "request.unsupported_schema");
    assert_eq!(failure.operation, Some(TaskOperationV1::Evidence));

    let failure = parse_task_intent_v1(b"{broken").unwrap_err();
    assert_eq!(failure.code, "request.invalid");
    assert_eq!(failure.operation, None);

    let intents = [
        TaskIntentV1::new(TaskIntentSpecV1::Decision(DecisionIntentV1 {
            method: "legacy-v0".to_owned(),
        })),
        TaskIntentV1::new(TaskIntentSpecV1::Evidence(EvidenceIntentV1::default())),
        TaskIntentV1::new(TaskIntentSpecV1::Coverage(CoverageIntentV1::default())),
        TaskIntentV1::new(TaskIntentSpecV1::PullValue(PullValueIntentV1::default())),
        TaskIntentV1::new(TaskIntentSpecV1::ReviewPacket(
            ReviewPacketIntentV1::default(),
        )),
    ];
    for intent in intents {
        let json = serde_json::to_string(&intent).unwrap().to_ascii_lowercase();
        for forbidden in ["workspace", "path", "output", "file"] {
            assert!(!json.contains(forbidden), "{forbidden} leaked into {json}");
        }
    }

    let receipt = TaskReceiptV1 {
        schema_version: TASK_RECEIPT_SCHEMA_V1.to_owned(),
        operation: TaskOperationV1::Evidence,
        method_version: "method".to_owned(),
        output_schema: "schema".to_owned(),
        local_datetime: "2026-07-13T09:10:11".to_owned(),
        outputs: vec![PathBuf::from("out.md")],
        notices: Vec::new(),
    };
    let mut receipt_json = serde_json::to_value(receipt).unwrap();
    receipt_json["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<TaskReceiptV1>(receipt_json).is_err());

    let failure = TaskFailureV1 {
        schema_version: TASK_FAILURE_SCHEMA_V1.to_owned(),
        operation: Some(TaskOperationV1::Evidence),
        code: "task.failed".to_owned(),
        message: "failed".to_owned(),
        retryable: false,
    };
    let mut failure_json = serde_json::to_value(failure).unwrap();
    failure_json["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<TaskFailureV1>(failure_json).is_err());
}

#[test]
fn invocation_normalizes_paths_truncates_one_clock_and_exposes_debug_seam() {
    let root = temp_root("invocation");
    let invocation = AppInvocation::new(root.join("a/../b"), fixed_datetime()).unwrap();
    assert_eq!(invocation.cwd(), root.join("b"));
    assert_eq!(
        invocation.resolve(Path::new("x/./y/../z")),
        root.join("b/x/z")
    );
    assert_eq!(invocation.local_datetime().nanosecond(), 123_456_000);

    #[cfg(debug_assertions)]
    {
        let _guard = ENV_LOCK.lock().unwrap();
        let previous = std::env::var_os("MIHO_REPORT_LOCAL_DATETIME");
        std::env::set_var("MIHO_REPORT_LOCAL_DATETIME", "2026-07-13T01:02:03.456789");
        let captured = AppInvocation::capture().unwrap();
        match previous {
            Some(value) => std::env::set_var("MIHO_REPORT_LOCAL_DATETIME", value),
            None => std::env::remove_var("MIHO_REPORT_LOCAL_DATETIME"),
        }
        assert_eq!(
            captured.local_datetime(),
            NaiveDateTime::parse_from_str("2026-07-13T01:02:03.456789", "%Y-%m-%dT%H:%M:%S%.f")
                .unwrap()
        );
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn evidence_coverage_pull_and_review_share_the_application_boundary() {
    let (root, workspace, invocation) = pull_workspace();
    let evidence = TaskRequestV1::new(
        workspace.clone(),
        TaskSpecV1::Evidence(EvidenceTaskV1 {
            plan_path: Some(PathBuf::from("input/plan.json")),
            plan_statuses: vec!["current".to_owned()],
            min_a_app_rate: "sd=8;default=9".to_owned(),
            ..EvidenceTaskV1::default()
        }),
    );
    let evidence_receipt = execute_task_v1(&evidence, &invocation).unwrap();
    assert_eq!(evidence_receipt.operation, TaskOperationV1::Evidence);
    assert_eq!(evidence_receipt.outputs.len(), 1);
    assert_eq!(
        evidence_receipt.outputs[0],
        root.join("input/data/evidence_pool_summary.md")
    );
    assert!(evidence_receipt.outputs[0].is_file());

    let coverage = TaskRequestV1::new(
        workspace.clone(),
        TaskSpecV1::Coverage(CoverageTaskV1 {
            plan_path: Some(PathBuf::from("input/plan.json")),
            ..CoverageTaskV1::default()
        }),
    );
    let coverage_receipt = execute_task_v1(&coverage, &invocation).unwrap();
    assert_eq!(coverage_receipt.outputs.len(), 3);
    assert!(coverage_receipt.outputs.iter().all(|path| path.is_file()));

    let pull_options = PullTaskV1 {
        plan_path: PathBuf::from("input/plan.json"),
        plan_statuses: Vec::new(),
        mechanism_notes_dir: Some(PathBuf::from("input/mechanism_notes")),
        decision_baseline_path: PathBuf::from("input/baseline.json"),
        ..PullTaskV1::default()
    };
    let pull = TaskRequestV1::new(
        workspace.clone(),
        TaskSpecV1::PullValue(pull_options.clone()),
    );
    let pull_receipt = execute_task_v1(&pull, &invocation).unwrap();
    assert_eq!(pull_receipt.operation, TaskOperationV1::PullValue);
    assert_eq!(pull_receipt.outputs.len(), 2);
    assert_eq!(
        pull_receipt.outputs,
        vec![
            root.join("input/data/current_pull_value_report.md"),
            root.join("input/data/next_pull_value_report.md"),
        ]
    );
    assert!(pull_receipt.method_version.starts_with("evidence-first-v1"));
    assert_eq!(pull_receipt.local_datetime, "2026-07-12T13:14:15");
    assert!(pull_receipt.outputs.iter().all(|path| path.is_file()));
    for status in ["current", "next"] {
        let actual = normalized_output(
            &root.join(format!("input/data/{status}_pull_value_report.md")),
            &root,
        );
        let expected = fs::read_to_string(
            fixture("pull_value_v1_contract")
                .join(format!("expected/{status}_pull_value_report.md")),
        )
        .unwrap()
        .replace("\r\n", "\n");
        assert_eq!(actual, expected, "{status} app pull report");
    }

    fs::copy(
        fixture("review_packet_v1_contract/input_overrides/mechanism_notes/alpha.json"),
        root.join("input/mechanism_notes/alpha.json"),
    )
    .unwrap();

    let review = TaskRequestV1::new(workspace, TaskSpecV1::ReviewPacket(pull_options));
    let review_invocation = AppInvocation::new(root.clone(), review_fixture_datetime()).unwrap();
    let review_receipt = execute_task_v1(&review, &review_invocation).unwrap();
    assert_eq!(review_receipt.operation, TaskOperationV1::ReviewPacket);
    assert_eq!(review_receipt.outputs.len(), 2);
    assert_eq!(
        review_receipt.outputs,
        vec![
            root.join("input/data/current_gpt_pull_reviewer_packet.md"),
            root.join("input/data/next_gpt_pull_reviewer_packet.md"),
        ]
    );
    assert_eq!(review_receipt.output_schema, "review-packet-v1-markdown");
    assert!(review_receipt.outputs.iter().all(|path| path.is_file()));
    let packet = fs::read_to_string(&review_receipt.outputs[0]).unwrap();
    assert!(packet.contains("\"generated_at\": \"2026-07-13T09:10:11\""));
    for status in ["current", "next"] {
        let actual = normalized_output(
            &root.join(format!("input/data/{status}_gpt_pull_reviewer_packet.md")),
            &root,
        );
        let expected = fs::read_to_string(
            fixture("review_packet_v1_contract")
                .join(format!("expected/{status}_gpt_pull_reviewer_packet.md")),
        )
        .unwrap()
        .replace("\r\n", "\n");
        assert_eq!(actual, expected, "{status} app review packet");
    }

    fs::remove_dir_all(root).unwrap();
}

#[test]
fn decision_executes_and_failures_adapt_without_partial_outputs() {
    let root = temp_root("decision");
    copy_tree(
        &fixture("decision_legacy_v0_contract/input"),
        &root.join("input"),
    );
    let workspace = WorkspaceLayout {
        data_dir: PathBuf::from("input/data"),
        box_path: PathBuf::from("input/box.yaml"),
    };
    let invocation = AppInvocation::new(root.clone(), fixed_datetime()).unwrap();
    let request = TaskRequestV1::new(
        workspace.clone(),
        TaskSpecV1::Decision(DecisionTaskV1 {
            method: "legacy-v0".to_owned(),
            rules_path: PathBuf::from("input/rules.yaml"),
        }),
    );
    let receipt = execute_task_v1(&request, &invocation).unwrap();
    assert_eq!(receipt.operation, TaskOperationV1::Decision);
    assert_eq!(receipt.outputs.len(), 2);
    assert_eq!(
        receipt.outputs,
        vec![
            root.join("input/data/decision_cards.json"),
            root.join("input/data/decision_report.md"),
        ]
    );
    assert!(receipt.outputs.iter().all(|path| path.is_file()));
    assert_eq!(receipt.method_version, "legacy-v0");
    assert_eq!(receipt.notices.len(), 1);
    assert_eq!(
        receipt.notices[0],
        "legacy-v0 compatibility only: formal evidence-first advice is provided by pull-value"
    );

    let bad_request = TaskRequestV1 {
        schema_version: "future".to_owned(),
        workspace,
        task: TaskSpecV1::Evidence(EvidenceTaskV1::default()),
    };
    let failure = execute_task_result_v1(&bad_request, &invocation).unwrap_err();
    assert_eq!(failure.operation, Some(TaskOperationV1::Evidence));
    assert_eq!(failure.schema_version, TASK_FAILURE_SCHEMA_V1);
    assert_eq!(failure.code, "task.failed");
    assert!(failure.message.contains("unsupported task request schema"));

    fs::remove_dir_all(root).unwrap();
}

#[test]
fn pull_status_collision_fails_before_mutating_an_old_output() {
    let (root, workspace, invocation) = pull_workspace();
    let old_output = root.join("input/data/current_gpt_pull_reviewer_packet.md");
    fs::write(&old_output, b"old-packet").unwrap();
    let request = TaskRequestV1::new(
        workspace,
        TaskSpecV1::ReviewPacket(PullTaskV1 {
            plan_path: PathBuf::from("input/plan.json"),
            plan_statuses: vec!["current".to_owned(), "CURRENT".to_owned()],
            mechanism_notes_dir: Some(PathBuf::from("input/mechanism_notes")),
            decision_baseline_path: PathBuf::from("input/baseline.json"),
            ..PullTaskV1::default()
        }),
    );
    let failure = execute_task_result_v1(&request, &invocation).unwrap_err();
    assert_eq!(failure.code, "task.failed");
    assert!(failure
        .message
        .contains("plan statuses resolve to the same review-packet output"));
    assert_eq!(fs::read(&old_output).unwrap(), b"old-packet");
    assert!(!root
        .join("input/data/next_gpt_pull_reviewer_packet.md")
        .exists());
    fs::remove_dir_all(root).unwrap();
}
