use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use chrono::NaiveDateTime;
use miho_core::evidence::{
    build_evidence_bundle_v1, render_aggregate_csv_v1, render_coverage_markdown_v1,
    EvidenceConfidenceV1, EvidenceContextV1, EvidenceGameV1, EvidenceInputsV1, EvidenceRequestV1,
};
use serde_json::Value;

const FIXED_LOCAL_DATETIME: &str = "2026-07-12T13:14:15";
const NORMALIZED_GENERATED_AT: &str = "<GENERATED_AT>";

fn fixture_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/evidence_v1_contract")
}

fn read(path: impl AsRef<Path>) -> Vec<u8> {
    fs::read(path.as_ref()).unwrap_or_else(|error| {
        panic!(
            "failed to read fixture {}: {error}",
            path.as_ref().display()
        )
    })
}

fn inputs() -> EvidenceInputsV1 {
    let input = fixture_root().join("input");
    EvidenceInputsV1 {
        team_rank_dedup_unordered_csv: read(input.join("data/team_rank_dedup_unordered.csv")),
        name_map_csv: Some(read(input.join("data/name_map.csv"))),
        tier_csv: Some(read(input.join("data/prydwen_tier_current.csv"))),
        box_json: read(input.join("box.json")),
        banner_plan_json: Some(read(input.join("plan.json"))),
    }
}

fn request(include_missing: bool) -> EvidenceRequestV1 {
    EvidenceRequestV1 {
        game: EvidenceGameV1::Zzz,
        plan_statuses: vec!["current".to_owned()],
        include_missing,
        ..EvidenceRequestV1::default()
    }
}

fn context() -> EvidenceContextV1 {
    EvidenceContextV1 {
        local_datetime: NaiveDateTime::parse_from_str(FIXED_LOCAL_DATETIME, "%Y-%m-%dT%H:%M:%S")
            .expect("fixed fixture clock must parse"),
    }
}

fn team_source() -> String {
    fixture_root()
        .join("input")
        .join("data")
        .join("team_rank_dedup_unordered.csv")
        .to_string_lossy()
        .into_owned()
}

fn utf8_sig(bytes: &[u8]) -> String {
    let bytes = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    String::from_utf8(bytes.to_vec()).expect("golden output must be UTF-8")
}

fn normalize_text(text: &str) -> String {
    // These are the only two content substitutions allowed by contract.json.
    // Line-ending conversion mirrors Python's text-mode read and is transport,
    // not report-content, normalization.
    let fixture = fixture_root();
    let fixture_text = fixture.to_string_lossy();
    text.replace("\r\n", "\n")
        .replace(fixture_text.as_ref(), "<ROOT>")
        .replace(&fixture_text.replace('/', "\\"), "<ROOT>")
        .replace(FIXED_LOCAL_DATETIME, NORMALIZED_GENERATED_AT)
}

fn expected(name: &str) -> String {
    normalize_text(&utf8_sig(&read(fixture_root().join("expected").join(name))))
}

fn mismatch(name: &str, actual: &str, expected: &str) -> Option<String> {
    if actual == expected {
        return None;
    }
    let actual_lines = actual.lines().collect::<Vec<_>>();
    let expected_lines = expected.lines().collect::<Vec<_>>();
    let line = actual_lines
        .iter()
        .zip(&expected_lines)
        .position(|(actual, expected)| actual != expected)
        .unwrap_or_else(|| actual_lines.len().min(expected_lines.len()));
    Some(format!(
        "{name}: first mismatch at line {}\n  expected: {:?}\n    actual: {:?}\n  expected bytes: {}\n    actual bytes: {}",
        line + 1,
        expected_lines.get(line).copied().unwrap_or("<EOF>"),
        actual_lines.get(line).copied().unwrap_or("<EOF>"),
        expected.len(),
        actual.len(),
    ))
}

#[test]
fn dense_fixture_preserves_evidence_v1_semantics() {
    let bundle = build_evidence_bundle_v1(&inputs(), &request(true), &context())
        .expect("dense evidence fixture must build");

    assert_eq!(bundle.generated_at, FIXED_LOCAL_DATETIME);
    assert_eq!(bundle.planned_slugs, ["sunna"]);

    let contract: Value = serde_json::from_slice(&read(fixture_root().join("contract.json")))
        .expect("contract.json must parse");
    let expected_ids = contract["stable_evidence_ids"]
        .as_object()
        .expect("stable_evidence_ids must be an object");
    let by_key = bundle
        .target
        .records
        .iter()
        .map(|record| (record.evidence_key.as_str(), record))
        .collect::<BTreeMap<_, _>>();

    assert_eq!(by_key.len(), expected_ids.len());
    for (key, evidence_id) in expected_ids {
        assert_eq!(
            by_key
                .get(key.as_str())
                .map(|record| record.evidence_id.as_str()),
            evidence_id.as_str(),
            "stable ID drift for {key}"
        );
    }

    let sd_owned = by_key["sd|lucy|miyabi|nicole-demara|bangboo:biggest-fan"];
    let da_owned = by_key["da|lucy|miyabi|nicole-demara|bangboo:biggest-fan"];
    let planned = by_key["sd|lucy|miyabi|sunna|bangboo:biggest-fan"];
    let missing = by_key["sd|lucy|miyabi|zhao|bangboo:biggest-fan"];

    assert_eq!(sd_owned.modes, ["sd"]);
    assert_eq!(sd_owned.best_score, Some(30_011.0));
    assert_eq!(da_owned.modes, ["da"]);
    assert_eq!(da_owned.best_score, Some(900_003.0));
    assert_ne!(sd_owned.evidence_id, da_owned.evidence_id);
    assert_eq!(
        (sd_owned.source_confidence, sd_owned.confidence),
        (EvidenceConfidenceV1::A, EvidenceConfidenceV1::A)
    );
    assert_eq!(
        (planned.source_confidence, planned.confidence),
        (EvidenceConfidenceV1::BPlus, EvidenceConfidenceV1::B)
    );
    assert_eq!(
        (missing.source_confidence, missing.confidence),
        (EvidenceConfidenceV1::BMinus, EvidenceConfidenceV1::C)
    );
    assert_eq!((sd_owned.record_count, sd_owned.duplicate_count), (12, 15));
    assert_eq!(
        (
            planned.non_sentinel_score_count,
            planned.sentinel_score_count
        ),
        (4, 2)
    );
    assert_eq!(bundle.target.summary.data_quality.sentinel_score_rows, 3);
}

#[test]
fn rust_core_matches_all_four_cross_language_goldens() {
    let coverage = build_evidence_bundle_v1(&inputs(), &request(false), &context())
        .expect("coverage fixture must build");
    let evidence = build_evidence_bundle_v1(&inputs(), &request(true), &context())
        .expect("evidence fixture must build");

    let outputs = [
        (
            "current_box_team_coverage.md",
            render_coverage_markdown_v1(&coverage.current, "当前 Box 队伍覆盖", &team_source(), 0),
        ),
        (
            "target_box_team_coverage.md",
            render_coverage_markdown_v1(&coverage.target, "目标 Box 队伍覆盖", &team_source(), 0),
        ),
        (
            "evidence_pool_summary.md",
            render_coverage_markdown_v1(
                &evidence.target,
                "绝区零目标账号证据池队伍覆盖",
                &team_source(),
                0,
            ),
        ),
        (
            "team_signature_aggregates.csv",
            utf8_sig(
                &render_aggregate_csv_v1(&coverage.target.aggregates)
                    .expect("aggregate CSV must render"),
            ),
        ),
    ];

    let failures = outputs
        .into_iter()
        .filter_map(|(name, actual)| {
            let actual = normalize_text(&actual);
            let expected = expected(name);
            mismatch(name, &actual, &expected)
        })
        .collect::<Vec<_>>();

    assert!(
        failures.is_empty(),
        "cross-language evidence V1 golden drift:\n{}",
        failures.join("\n\n")
    );
}
