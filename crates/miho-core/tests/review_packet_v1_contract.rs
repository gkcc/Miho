use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

use chrono::NaiveDateTime;
use miho_core::{
    evidence::EvidenceInputsV1,
    pull_value::{
        build_pull_value_bundle_v1, render_gpt_review_packet_v1, PullValueContextV1,
        PullValueInputsV1, PullValueRequestV1,
    },
};

fn fixture_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/review_packet_v1_contract")
}

fn shared_input_root() -> PathBuf {
    fixture_root().join("../pull_value_v1_contract/input")
}

fn read(path: impl AsRef<Path>) -> Vec<u8> {
    fs::read(path).unwrap()
}

fn inputs() -> PullValueInputsV1 {
    let input = shared_input_root();
    let mut mechanism_notes = BTreeMap::new();
    mechanism_notes.insert(
        "alpha".to_owned(),
        read(fixture_root().join("input_overrides/mechanism_notes/alpha.json")),
    );
    for slug in ["beta", "delta", "epsilon"] {
        mechanism_notes.insert(
            slug.to_owned(),
            read(input.join(format!("mechanism_notes/{slug}.yaml"))),
        );
    }
    PullValueInputsV1 {
        evidence: EvidenceInputsV1 {
            team_rank_dedup_unordered_csv: read(input.join("data/team_rank_dedup_unordered.csv")),
            name_map_csv: Some(read(input.join("data/name_map.csv"))),
            tier_csv: Some(read(input.join("data/prydwen_tier_current.csv"))),
            box_json: read(input.join("box.json")),
            banner_plan_json: Some(read(input.join("plan.json"))),
        },
        usage_csv: Some(read(input.join("data/character_usage_long.csv"))),
        mechanism_notes,
        decision_baseline: Some(read(input.join("baseline.json"))),
    }
}

fn context() -> PullValueContextV1 {
    PullValueContextV1 {
        local_datetime: NaiveDateTime::parse_from_str("2026-07-13T09:10:11", "%Y-%m-%dT%H:%M:%S")
            .unwrap(),
        data_dir: "<ROOT>\\input\\data".to_owned(),
        box_path: "<ROOT>\\input\\box.json".to_owned(),
        plan_path: "<ROOT>\\input\\plan.json".to_owned(),
        mechanism_notes_dir: "<ROOT>\\input\\mechanism_notes".to_owned(),
        decision_baseline_path: "<ROOT>\\input\\baseline.json".to_owned(),
    }
}

#[test]
fn rust_packet_renderer_matches_current_and_next_python_goldens() {
    for status in ["current", "next"] {
        let bundle = build_pull_value_bundle_v1(
            &inputs(),
            &PullValueRequestV1 {
                plan_statuses: vec![status.to_owned()],
                ..PullValueRequestV1::default()
            },
            &context(),
        )
        .unwrap();
        let actual = render_gpt_review_packet_v1(&bundle).unwrap();
        let expected = String::from_utf8(read(
            fixture_root().join(format!("expected/{status}_gpt_pull_reviewer_packet.md")),
        ))
        .unwrap()
        .replace("\r\n", "\n");
        assert_eq!(actual, expected, "{status} review packet");
    }
}
