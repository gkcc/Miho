use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

use chrono::NaiveDateTime;
use miho_core::{
    evidence::EvidenceInputsV1,
    pull_value::{
        build_pull_value_bundle_v1, render_gpt_review_packet_v1, render_pull_value_json_v1,
        render_pull_value_markdown_v1, validate_mechanism_note_v1, PullValueContextV1,
        PullValueInputsV1, PullValueRequestV1,
    },
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/pull_value_v1_contract")
}

fn read(relative: &str) -> Vec<u8> {
    fs::read(root().join(relative)).unwrap()
}

fn read_text(relative: &str) -> String {
    String::from_utf8(read(relative))
        .unwrap()
        .replace("\r\n", "\n")
}

fn inputs() -> PullValueInputsV1 {
    let mut mechanism_notes = BTreeMap::new();
    for slug in ["alpha", "beta", "delta", "epsilon"] {
        mechanism_notes.insert(
            slug.to_owned(),
            read(&format!("input/mechanism_notes/{slug}.yaml")),
        );
    }
    PullValueInputsV1 {
        evidence: EvidenceInputsV1 {
            team_rank_dedup_unordered_csv: read("input/data/team_rank_dedup_unordered.csv"),
            name_map_csv: Some(read("input/data/name_map.csv")),
            tier_csv: Some(read("input/data/prydwen_tier_current.csv")),
            box_json: read("input/box.json"),
            banner_plan_json: Some(read("input/plan.json")),
        },
        usage_csv: Some(read("input/data/character_usage_long.csv")),
        mechanism_notes,
        decision_baseline: Some(read("input/baseline.json")),
    }
}

fn context() -> PullValueContextV1 {
    PullValueContextV1 {
        local_datetime: NaiveDateTime::parse_from_str("2026-07-12T13:14:15", "%Y-%m-%dT%H:%M:%S")
            .unwrap(),
        data_dir: "<ROOT>\\input\\data".to_owned(),
        box_path: "<ROOT>\\input\\box.json".to_owned(),
        plan_path: "<ROOT>\\input\\plan.json".to_owned(),
        mechanism_notes_dir: "<ROOT>\\input\\mechanism_notes".to_owned(),
        decision_baseline_path: "<ROOT>\\input\\baseline.json".to_owned(),
    }
}

#[test]
fn rust_matches_current_and_next_typed_cards_and_markdown() {
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
        let json = render_pull_value_json_v1(&bundle).unwrap();
        let markdown = render_pull_value_markdown_v1(&bundle);
        let actual_json = String::from_utf8(json).unwrap();
        let expected_json = read_text(&format!("expected/{status}_pull_cards.json"));
        if actual_json != expected_json {
            let index = actual_json
                .bytes()
                .zip(expected_json.bytes())
                .position(|(left, right)| left != right)
                .unwrap_or_else(|| actual_json.len().min(expected_json.len()));
            let start = index.saturating_sub(80);
            let actual_end = (index + 160).min(actual_json.len());
            let expected_end = (index + 160).min(expected_json.len());
            panic!(
                "{status} typed cards first differ at byte {index}:\nactual={:?}\nexpected={:?}",
                &actual_json.as_bytes()[start..actual_end],
                &expected_json.as_bytes()[start..expected_end]
            );
        }
        assert_eq!(
            markdown,
            read_text(&format!("expected/{status}_pull_value_report.md")),
            "{status} markdown"
        );
    }
}

#[test]
fn exact_dependency_drives_main_evidence_and_conditional_stays_risk() {
    let bundle = build_pull_value_bundle_v1(
        &inputs(),
        &PullValueRequestV1 {
            plan_statuses: vec!["next".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let epsilon = bundle
        .cards
        .iter()
        .find(|card| card.slug == "epsilon")
        .unwrap();
    assert_eq!(epsilon.pull_value, "中");
    assert_eq!(epsilon.evidence_refs.len(), 1);
    assert_eq!(epsilon.evidence_refs[0].plan_dependency, ["epsilon"]);
    assert_eq!(epsilon.risk_evidence_refs.len(), 1);
    assert_eq!(
        epsilon.risk_evidence_refs[0].plan_dependency,
        ["epsilon", "zeta"]
    );
    assert!(epsilon
        .risk_notes
        .iter()
        .any(|note| note.contains("conditional risk")));
}

#[test]
fn empty_review_set_skips_unrelated_notes_but_matching_layers_validate_individually() {
    let mut inputs = inputs();
    inputs
        .mechanism_notes
        .insert("unrelated".to_owned(), b"broken: [".to_vec());
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    assert!(bundle.cards.is_empty());
    assert!(bundle.summary.reviewed_slugs.is_empty());

    assert!(validate_mechanism_note_v1(b"broken: [").is_err());
    assert!(validate_mechanism_note_v1(b"[not, a, mapping]").is_err());
    assert!(validate_mechanism_note_v1(b"").is_ok());
    assert!(validate_mechanism_note_v1(b"stage_confidence: high\n").is_ok());
}

#[test]
fn equal_tier_ratings_keep_the_first_csv_row_like_python_stable_sort() {
    let mut inputs = inputs();
    inputs
        .evidence
        .tier_csv
        .as_mut()
        .unwrap()
        .extend_from_slice(b"sd,beta,late-beta,support,T9,10,ice,support,S\n");
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let beta = bundle
        .cards
        .iter()
        .find(|card| card.slug == "beta")
        .unwrap();
    assert!(beta
        .decision_basis
        .iter()
        .any(|basis| basis.contains("T0.5 / rating 10")));
    assert!(!beta.decision_basis.iter().any(|basis| basis.contains("T9")));
}

#[test]
fn baseline_mapping_inner_slug_overrides_outer_key() {
    let mut inputs = inputs();
    inputs.decision_baseline = Some(
        br#"{"decisions":{"beta":{"slug":"gamma","final_stage":"9+9","decision_status":"locked"}}}"#
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let beta = bundle
        .cards
        .iter()
        .find(|card| card.slug == "beta")
        .unwrap();
    let gamma = bundle
        .cards
        .iter()
        .find(|card| card.slug == "gamma")
        .unwrap();
    assert!(beta.prior_final_stage.is_empty());
    assert_eq!(gamma.prior_final_stage, "9+9");
    assert_eq!(gamma.final_stage, "9+9");
}

#[test]
fn empty_baseline_fields_fall_through_like_python_or() {
    let mut inputs = inputs();
    inputs.decision_baseline = Some(
        br#"{"decisions":[],"characters":{"gamma":{"final_stage":"9+9","new_evidence_categories":[],"new_evidence":["legacy-change"]}}}"#
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let gamma = bundle
        .cards
        .iter()
        .find(|card| card.slug == "gamma")
        .unwrap();
    assert_eq!(gamma.final_stage, "9+9");
    assert_eq!(gamma.new_evidence_categories, ["legacy-change"]);
}

#[test]
fn raw_usage_presence_marks_rerun_without_creating_valid_history() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\n2026-07-12,sd,role,3.0,odd,10\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["odd".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let odd = bundle.cards.iter().find(|card| card.slug == "odd").unwrap();
    assert_eq!(odd.candidate_type, "rerun");
    assert!(odd.history_summary.starts_with("暂无历史出场"));
}

#[test]
fn usage_history_keeps_first_seen_mode_order() {
    let mut inputs = inputs();
    inputs
        .usage_csv
        .as_mut()
        .unwrap()
        .extend_from_slice(b"2026-07-01,da,all,2.0,beta,12\n");
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let beta = bundle
        .cards
        .iter()
        .find(|card| card.slug == "beta")
        .unwrap();
    assert!(beta.history_summary.starts_with("sd:"));
    assert!(beta.history_summary.contains("；da:"));
}

#[test]
fn decimal_overflow_is_rejected_and_python_rounding_cannot_cross_threshold() {
    assert!(validate_mechanism_note_v1(br#"{"value":1e400}"#).is_err());
    assert!(
        validate_mechanism_note_v1(br#"{"value":1234567890123456789012345678901234567890}"#)
            .is_ok()
    );

    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\n2026-07-12,sd,all,3.0,beta,9.9995\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let beta = bundle
        .cards
        .iter()
        .find(|card| card.slug == "beta")
        .unwrap();
    assert_eq!(beta.pull_value, "中");
    assert!(beta.history_summary.contains("avg_last3 9.999%"));
}

#[test]
fn negative_usage_values_are_not_clamped_to_zero() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\n2026-07-12,sd,all,3.0,beta,-5\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let beta = bundle
        .cards
        .iter()
        .find(|card| card.slug == "beta")
        .unwrap();
    assert!(beta.global_usage_summary.contains("best_latest=-5%"));
    assert!(beta.global_usage_summary.contains("best_avg_last3=-5%"));
}

#[test]
fn finite_usage_rows_whose_average_overflows_do_not_panic_or_raise_priority() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\n2026-01-01,sd,all,3.0,beta,1e308\n2026-02-01,sd,all,3.0,beta,1e308\n2026-03-01,sd,all,3.0,beta,1e308\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let beta = bundle
        .cards
        .iter()
        .find(|card| card.slug == "beta")
        .unwrap();
    assert_eq!(beta.pull_value, "中");
    assert!(beta.history_summary.contains("avg_last3 inf%"));
    assert!(beta.global_usage_summary.contains("best_avg_last3=-%"));
    assert!(beta
        .decision_basis
        .iter()
        .any(|basis| basis.contains("近三期最高均值 0%")));
}

#[test]
fn falsey_mechanism_identity_values_do_not_block_unknown_fallbacks() {
    let mut inputs = inputs();
    inputs.mechanism_notes.insert(
        "odd".to_owned(),
        b"identity:\n  role_group_cn: null\n  element_cn: false\n  style_cn: 0\n  rarity: null\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["odd".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let odd = bundle.cards.iter().find(|card| card.slug == "odd").unwrap();
    assert!(odd
        .mechanism_summary
        .starts_with("未知属性 / 未知特性 / 未知定位"));
    assert!(!odd.mechanism_summary.contains("稀有度="));
}

#[test]
fn pyyaml_11_booleans_empty_docs_and_non_finite_values_match_python_loader() {
    assert!(validate_mechanism_note_v1(b"recommended_stage: .nan\n").is_err());
    assert!(validate_mechanism_note_v1(b"recommended_stage: 1.0E+400\n").is_err());
    assert!(validate_mechanism_note_v1(b"recommended_stage: 1e400\n").is_ok());

    let mut inputs = inputs();
    inputs.evidence.banner_plan_json = Some(
        b"phases:\n  - status: current\n    include_low_rarity: off\n    characters:\n      - slug: low-a\n        banner_role: A level\n        rarity: A\n"
            .to_vec(),
    );
    inputs.decision_baseline = Some(
        b"decisions:\n  - slug: low-a\n    final_stage: off\n    decision_status: locked\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    assert!(bundle.cards.is_empty());
    assert_eq!(bundle.summary.filtered_low_rarity_slugs, ["low-a"]);

    inputs.evidence.banner_plan_json = Some(Vec::new());
    inputs.decision_baseline = Some(
        b"decisions:\n  - slug: odd\n    final_stage: off\n    decision_status: locked\n".to_vec(),
    );
    let falsey_stage = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["odd".to_owned()],
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let odd = falsey_stage
        .cards
        .iter()
        .find(|card| card.slug == "odd")
        .unwrap();
    assert!(odd.prior_final_stage.is_empty());
    assert_ne!(odd.final_stage, "off");

    inputs.evidence.banner_plan_json = Some(Vec::new());
    inputs.decision_baseline = Some(Vec::new());
    let empty = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    assert!(empty.cards.is_empty());

    inputs.evidence.banner_plan_json = Some(br#"{"phases":[],"unused":1e400}"#.to_vec());
    assert!(build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .is_err());
}

#[test]
fn quoted_falsey_scalar_text_is_preserved_outside_flag_fields() {
    let mut inputs = inputs();
    inputs.mechanism_notes.insert(
        "odd".to_owned(),
        b"source_quality: \"no\"\narchetypes: \"false\"\nrisks_and_counterevidence: \"0\"\n"
            .to_vec(),
    );
    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["odd".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let odd = bundle.cards.iter().find(|card| card.slug == "odd").unwrap();
    assert!(odd.mechanism_review_summary.contains("source_quality=no"));
    assert!(odd.mechanism_summary.contains("archetype=false"));
    assert_eq!(odd.replacement_risk, "0");
}

#[test]
fn review_packet_serializes_existing_cards_without_recomputing_and_keeps_fence_safe() {
    let mut bundle = build_pull_value_bundle_v1(
        &inputs(),
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    bundle.cards[0].pull_value = "SERIALIZER-SENTINEL".to_owned();
    bundle.cards[0].mechanism_notes = serde_json::json!({
        "danger": "````\n</script>\nA|B",
        "weird_small": 1e-7,
        "negative_zero": -0.0,
        "large_integer": 12345678901234567890_u64,
        "integer_negative_zero": serde_json::from_str::<serde_json::Value>("-0").unwrap()
    });
    let packet = render_gpt_review_packet_v1(&bundle).unwrap();
    assert!(packet.contains("\"local_rule_pull_value\": \"SERIALIZER-SENTINEL\""));
    assert!(!packet.contains("\"pull_value\":"));
    assert!(packet.contains("````\\n</script>\\nA|B"));
    assert!(packet.contains("\"weird_small\": 1e-07"));
    assert!(packet.contains("\"negative_zero\": -0.0"));
    assert!(packet.contains("\"large_integer\": 12345678901234567890"));
    assert!(packet.contains("\"integer_negative_zero\": 0"));
    assert_eq!(packet.lines().filter(|line| *line == "`````").count(), 1);
    assert_eq!(
        packet.lines().filter(|line| *line == "`````json").count(),
        1
    );
    let payload = packet
        .split_once("`````json\n")
        .unwrap()
        .1
        .split_once("\n`````\n")
        .unwrap()
        .0;
    let payload: serde_json::Value = serde_json::from_str(payload).unwrap();
    assert_eq!(
        payload["candidates"][0]["local_rule_pull_value"],
        "SERIALIZER-SENTINEL"
    );
}
