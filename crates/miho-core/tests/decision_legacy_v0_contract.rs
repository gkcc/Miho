use std::{
    fs,
    path::{Path, PathBuf},
};

use chrono::NaiveDateTime;
use miho_core::decision_legacy::{
    build_decision_legacy_v0, render_decision_json_legacy_v0, render_decision_markdown_legacy_v0,
    DecisionLegacyContextV0, DecisionLegacyInputsV0, DecisionLegacyRequestV0,
    DECISION_LEGACY_METHOD,
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/decision_legacy_v0_contract")
}

fn read(relative: &str) -> Vec<u8> {
    fs::read(root().join(relative)).unwrap()
}

fn inputs() -> DecisionLegacyInputsV0 {
    DecisionLegacyInputsV0 {
        box_config: read("input/box.yaml"),
        rules_config: Some(read("input/rules.yaml")),
        tier_current_csv: Some(read("input/data/prydwen_tier_current.csv")),
        tier_history_csv: Some(read("input/data/prydwen_tier_history.csv")),
        usage_csv: Some(read("input/data/character_usage_long.csv")),
        team_raw_csv: Some(read("input/data/team_rank_raw.csv")),
        name_map_csv: Some(read("input/data/name_map.csv")),
        changelog_history_csv: Some(read("input/data/prydwen_tier_changelog_history.csv")),
    }
}

fn request() -> DecisionLegacyRequestV0 {
    DecisionLegacyRequestV0 {
        method: DECISION_LEGACY_METHOD.to_owned(),
    }
}

fn empty_box() -> Vec<u8> {
    br#"{"agents":[]}"#.to_vec()
}

fn normalize(text: &str) -> String {
    text.replace("\r\n", "\n")
        .replace("2026-07-12T13:14:15", "<GENERATED_AT>")
}

#[test]
fn rust_matches_frozen_legacy_v0_json_and_markdown() {
    let result = build_decision_legacy_v0(&inputs(), &request()).unwrap();
    let json = String::from_utf8(render_decision_json_legacy_v0(&result).unwrap()).unwrap();
    let markdown = render_decision_markdown_legacy_v0(
        &result,
        &DecisionLegacyContextV0 {
            local_datetime: NaiveDateTime::parse_from_str(
                "2026-07-12T13:14:15",
                "%Y-%m-%dT%H:%M:%S",
            )
            .unwrap(),
        },
    );
    let expected_json = String::from_utf8(read("expected/decision_cards.json")).unwrap();
    let expected_markdown = String::from_utf8(read("expected/decision_report.md")).unwrap();
    assert_eq!(normalize(&json), normalize(&expected_json));
    assert_eq!(normalize(&markdown), normalize(&expected_markdown));
}

#[test]
fn legacy_v0_keeps_explicit_method_and_strict_config_boundaries() {
    let empty = DecisionLegacyInputsV0 {
        box_config: b"\xEF\xBB\xBF{\"agents\": []}".to_vec(),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&empty, &request()).unwrap();
    assert_eq!(result.payload["summary"]["candidate_count"], 0);
    let mut empty_yaml_rules = empty.clone();
    empty_yaml_rules.rules_config = Some(Vec::new());
    assert!(build_decision_legacy_v0(&empty_yaml_rules, &request()).is_ok());

    let wrong_method = DecisionLegacyRequestV0 {
        method: "evidence-first-v1-20260712".to_owned(),
    };
    assert!(build_decision_legacy_v0(&empty, &wrong_method).is_err());

    let mut broken_rules = empty.clone();
    broken_rules.rules_config = Some(b"[not, a, mapping]".to_vec());
    assert!(build_decision_legacy_v0(&broken_rules, &request()).is_err());

    let mut non_finite = empty;
    non_finite.tier_current_csv = Some(b"character_slug,tier_mode,rating\nbad,sd,NaN\n".to_vec());
    assert!(build_decision_legacy_v0(&non_finite, &request()).is_err());
}

#[test]
fn legacy_v0_explicitly_preserves_cross_mode_splice_and_ignored_aliases() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: br#"{"agents":[{"slug":"alias-x","owned":true}]}"#.to_vec(),
        tier_current_csv: Some(b"tier_mode,tier_mode_cn,character_slug,character_name_cn,role_group,tier,rating\nsd,SD,x,X,dps,T0,10\n".to_vec()),
        usage_csv: Some(b"collect_date,mode,mode_cn,sub_mode,character_slug,app_rate\n2026-01-01,sd,SD,all,x,10\n2026-02-01,sd,SD,all,x,0\n2026-01-01,da,DA,all,x,30\n2026-02-01,da,DA,all,x,30\n".to_vec()),
        name_map_csv: Some(b"character_slug,character_name_cn,aliases\nx,X,alias-x\n".to_vec()),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    let card = &result.payload["cards"][0];
    assert_eq!(card["slug"], "x");
    assert_eq!(
        card["owned"], false,
        "LegacyV0 intentionally ignores aliases"
    );
    assert_eq!(card["decision"], "抽");
    assert_eq!(card["decision_score"], 124.0);
    assert_eq!(card["history_summary"]["modes"]["sd"]["trend_delta"], -10.0);
    assert_eq!(
        card["history_summary"]["modes"]["da"]["avg_last3_app_rate"],
        30.0
    );
}

#[test]
fn legacy_v0_preserves_python_presence_truthiness_and_payload_scalars() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: br#"{"agents":[{"slug":"x","owned":false},{"slug":"y","owned":true,"cinema":0,"signature":0}]}"#.to_vec(),
        rules_config: Some(br#"{"candidate_min_rating":9,"candidates":[{"slug":"y","allow_additional_copies":"false"}]}"#.to_vec()),
        tier_current_csv: Some(b"tier_mode,character_slug,character_name_cn,role_group,style,element,tier,rating\nsd,x,X,other,,,T3,1\nsd,y,Y,dps,,,T0,10\nsd,z,Z,dps,,,T0,10\n".to_vec()),
        usage_csv: Some(b"collect_date,mode,mode_cn,sub_mode,character_slug,app_rate\n2026-01-01,sd,SD,all,y,10\n2026-01-01,sd,SD,all,z,10\n".to_vec()),
        team_raw_csv: Some(b"collect_date,mode_cn,sub_mode_cn,char_1_slug,char_2_slug,char_3_slug,rank,app_rate\n2026-01-01,SD,all,z,a,b,1,\n".to_vec()),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    let cards = result.payload["cards"].as_array().unwrap();
    let card = |slug: &str| cards.iter().find(|card| card["slug"] == slug).unwrap();
    assert!(
        card("x").is_object(),
        "owned=false Box entries still become Legacy candidates"
    );
    assert_eq!(
        card("y")["decision"],
        "抽",
        "non-empty string 'false' is Python-truthy"
    );
    assert_eq!(
        card("z")["replacement_risk"]["replacements"][0]["same_style"],
        ""
    );
    assert!(card("z")["history_summary"]["latest_team_examples"][0]["app_rate"].is_null());

    let infinity = DecisionLegacyInputsV0 {
        box_config: br#"{"agents":[{"slug":"x","cinema":"Infinity"}]}"#.to_vec(),
        ..Default::default()
    };
    assert!(build_decision_legacy_v0(&infinity, &request()).is_err());
}

#[test]
fn legacy_v0_preserves_raw_get_fields_falsey_or_values_and_python_slices() {
    let base = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","source":"","notes":null,"banner_type":false,"release_type":"new","max_recommended_stage":false,"force_decision":"抽"}],"stage_ladder":[{"stage":0,"label":7,"pull_cost":1}]}"#.as_bytes().to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&base, &request()).unwrap();
    let card = &result.payload["cards"][0];
    assert_eq!(card["source"], "");
    assert!(card["notes"].is_null());
    assert_eq!(card["candidate_type"], "new");
    assert_eq!(card["stage_comparison"][0]["stage"], "");
    assert_eq!(card["stage_comparison"][0]["label"], 7);
    let markdown = render_decision_markdown_legacy_v0(
        &result,
        &DecisionLegacyContextV0 {
            local_datetime: NaiveDateTime::default(),
        },
    );
    assert!(!markdown.contains("- 备注："));

    let tiers = b"tier_mode,character_slug,tier,rating\nsd,x,T0,10\nsd,y,T0,10\n".to_vec();
    for (limit, expected) in [("-1", vec!["x"]), ("true", vec!["x"])] {
        let sliced = DecisionLegacyInputsV0 {
            box_config: empty_box(),
            rules_config: Some(
                format!("{{\"candidate_min_rating\":true,\"max_generated_candidates\":{limit}}}")
                    .into_bytes(),
            ),
            tier_current_csv: Some(tiers.clone()),
            ..Default::default()
        };
        let result = build_decision_legacy_v0(&sliced, &request()).unwrap();
        let slugs = result.payload["cards"]
            .as_array()
            .unwrap()
            .iter()
            .map(|card| card["slug"].as_str().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(slugs, expected);
    }

    for invalid in ["null", "\"bad\"", "[]"] {
        let inputs = DecisionLegacyInputsV0 {
            box_config: empty_box(),
            rules_config: Some(format!("{{\"candidate_min_rating\":{invalid}}}").into_bytes()),
            tier_current_csv: Some(b"tier_mode,character_slug,tier,rating\nsd,x,T3,1\n".to_vec()),
            ..Default::default()
        };
        let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
        assert_eq!(result.payload["summary"]["candidate_count"], 1);
    }
    let null_threshold = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(r#"{"candidate_min_rating":0,"pull_rating":null}"#.as_bytes().to_vec()),
        tier_current_csv: Some(b"tier_mode,character_slug,tier,rating\nsd,x,T3,1\n".to_vec()),
        usage_csv: Some(
            b"collect_date,mode,sub_mode,character_slug,app_rate\n2026-01-01,sd,all,x,10\n"
                .to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&null_threshold, &request()).unwrap();
    assert_eq!(result.payload["cards"][0]["decision"], "抽");
}

#[test]
fn legacy_v0_accepts_textual_infinity_but_rejects_numeric_non_finite_fields() {
    let textual = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","name_cn":"NaN","source":"Infinity","notes":"Infinity","force_decision":"抽"}]}"#.as_bytes().to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&textual, &request()).unwrap();
    assert_eq!(result.payload["cards"][0]["name_cn"], "NaN");
    assert_eq!(result.payload["cards"][0]["source"], "Infinity");
    assert_eq!(result.payload["cards"][0]["notes"], "Infinity");

    let non_finite_rank = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","force_decision":"抽"}]}"#
                .as_bytes()
                .to_vec(),
        ),
        team_raw_csv: Some(
            b"collect_date,char_1_slug,rank,app_rate\n2026-01-01,x,Infinity,5\n".to_vec(),
        ),
        ..Default::default()
    };
    assert!(build_decision_legacy_v0(&non_finite_rank, &request()).is_err());
}

#[test]
fn legacy_v0_matches_python_numeric_whitespace_and_float_repr() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","force_decision":"抽"}]}"#.as_bytes().to_vec(),
        ),
        tier_current_csv: Some(
            b"tier_mode,tier_mode_cn,character_slug,tier,rating\nsd,SD,x,T0, 1e-7 \n"
                .to_vec(),
        ),
        usage_csv: Some(
            b"collect_date,mode,mode_cn,sub_mode,character_slug,app_rate\n2026-01-01,sd,SD,all,x, 1e-7 \n"
                .to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    assert_eq!(
        result.payload["cards"][0]["tier_summary"]["best_rating"],
        1e-7
    );
    assert_eq!(
        result.payload["cards"][0]["history_summary"]["modes"]["sd"]["latest_app_rate"],
        1e-7
    );
    let json = String::from_utf8(render_decision_json_legacy_v0(&result).unwrap()).unwrap();
    assert!(json.matches("1e-07").count() >= 3, "{json}");
    let markdown = render_decision_markdown_legacy_v0(
        &result,
        &DecisionLegacyContextV0 {
            local_datetime: NaiveDateTime::default(),
        },
    );
    assert!(markdown.contains("\u{6700}\u{8fd1}1e-07%"), "{markdown}");
}

#[test]
fn legacy_v0_uses_python_float_repr_when_config_numbers_become_strings() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","force_decision":1e-7}],"stage_ladder":[{"stage":1e-7,"pull_cost":1}]}"#
                .as_bytes()
                .to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    assert_eq!(result.payload["cards"][0]["decision"], "1e-07");
    assert_eq!(
        result.payload["cards"][0]["stage_comparison"][0]["stage"],
        "1e-07"
    );

    let warning = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(r#"{"min_pull_avg_usage":1e-7}"#.as_bytes().to_vec()),
        tier_current_csv: Some(b"tier_mode,character_slug,tier,rating\nsd,x,T0,10\n".to_vec()),
        usage_csv: Some(
            b"collect_date,mode,sub_mode,character_slug,app_rate\n2026-01-01,sd,all,x,0\n".to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&warning, &request()).unwrap();
    assert!(result.payload["cards"][0]["warnings"][0]
        .as_str()
        .unwrap()
        .contains("1e-07%"));
}

#[test]
fn legacy_v0_matches_python_numeric_underscore_grammar() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: r#"{"agents":[{"slug":"x","cinema":"1_0"}]}"#.as_bytes().to_vec(),
        rules_config: Some(
            r#"{"candidate_min_rating":"1_0","candidates":[{"slug":"x","force_decision":"抽"}]}"#
                .as_bytes()
                .to_vec(),
        ),
        tier_current_csv: Some(b"tier_mode,character_slug,tier,rating\nsd,x,T0,1_0\n".to_vec()),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    let card = &result.payload["cards"][0];
    assert_eq!(card["current_stage"], "10+0");
    assert_eq!(card["tier_summary"]["best_rating"], 10.0);

    let invalid = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(r#"{"candidate_min_rating":"1__0"}"#.as_bytes().to_vec()),
        tier_current_csv: Some(b"tier_mode,character_slug,tier,rating\nsd,x,T0,1\n".to_vec()),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&invalid, &request()).unwrap();
    assert_eq!(result.payload["summary"]["candidate_count"], 1);
}

#[test]
fn legacy_v0_matches_dict_reader_ragged_rows_and_pyyaml_semantics() {
    let yaml = r#"
base: &base
  force_decision: 抽
candidates:
  - <<: *base
    slug: x
    source: yes
    notes: off
  - slug: y
    force_decision: 抽
    source: "yes"
    notes: "off"
  - slug: z
    force_decision: 抽
    source: 012
    notes: 1:20
"#;
    let inputs = DecisionLegacyInputsV0 {
        box_config: b"agents: []\n".to_vec(),
        rules_config: Some(yaml.as_bytes().to_vec()),
        tier_current_csv: Some(
            b"tier_mode,character_slug,tier,rating\nsd,x,T0\nsd,y,T0,10,ignored\n".to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    let cards = result.payload["cards"].as_array().unwrap();
    let card = |slug: &str| cards.iter().find(|card| card["slug"] == slug).unwrap();
    assert_eq!(card("x")["decision"], "\u{62bd}");
    assert_eq!(card("x")["source"], true);
    assert_eq!(card("x")["notes"], false);
    assert_eq!(card("x")["tier_summary"]["best_rating"], 0.0);
    assert_eq!(card("y")["source"], "yes");
    assert_eq!(card("y")["notes"], "off");
    assert_eq!(card("z")["source"], 10);
    assert_eq!(card("z")["notes"], 80);

    let null_cells = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        tier_current_csv: Some(
            b"tier_mode,character_slug,tier,rating,style\nsd,x,T0,10\nsd,y,T0,10,\n".to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&null_cells, &request()).unwrap();
    let cards = result.payload["cards"].as_array().unwrap();
    let card = |slug: &str| cards.iter().find(|card| card["slug"] == slug).unwrap();
    assert!(card("x")["tier_summary"]["style"].is_null());
    assert_eq!(card("y")["tier_summary"]["style"], "");
}

#[test]
fn legacy_v0_rejects_unquoted_pyyaml_timestamp_only_when_it_reaches_json() {
    let raw_date = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            "candidates:\n  - slug: x\n    force_decision: 抽\n    notes: 2026-01-01\n"
                .as_bytes()
                .to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&raw_date, &request()).unwrap();
    assert!(render_decision_json_legacy_v0(&result).is_err());

    let quoted = DecisionLegacyInputsV0 {
        rules_config: Some(
            "candidates:\n  - slug: x\n    force_decision: 抽\n    notes: \"2026-01-01\"\n"
                .as_bytes()
                .to_vec(),
        ),
        ..raw_date
    };
    let result = build_decision_legacy_v0(&quoted, &request()).unwrap();
    assert!(render_decision_json_legacy_v0(&result).is_ok());
    assert_eq!(result.payload["cards"][0]["notes"], "2026-01-01");
}

#[test]
fn legacy_v0_normalizes_pyyaml_11_plain_scalars_inside_flow_collections() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            "candidates: [{slug: x, force_decision: 抽, source: 012, notes: yes}, {slug: y, force_decision: 抽, source: \"012\", notes: \"yes\"}]\n"
                .as_bytes()
                .to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    let cards = result.payload["cards"].as_array().unwrap();
    let card = |slug: &str| cards.iter().find(|card| card["slug"] == slug).unwrap();
    assert_eq!(card("x")["source"], 10);
    assert_eq!(card("x")["notes"], true);
    assert_eq!(card("y")["source"], "012");
    assert_eq!(card("y")["notes"], "yes");
}

#[test]
fn legacy_v0_keeps_quoted_non_finite_text_in_raw_stage_fields() {
    let quoted = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","force_decision":"抽"}],"stage_ladder":[{"stage":"0+0","pull_cost":"Infinity"}]}"#
                .as_bytes()
                .to_vec(),
        ),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&quoted, &request()).unwrap();
    assert_eq!(
        result.payload["cards"][0]["stage_comparison"][0]["pull_cost"],
        "Infinity"
    );
    assert!(render_decision_json_legacy_v0(&result).is_ok());

    let plain_yaml = DecisionLegacyInputsV0 {
        rules_config: Some(
            "candidates:\n  - slug: x\n    force_decision: 抽\nstage_ladder:\n  - stage: 0+0\n    pull_cost: .inf\n"
                .as_bytes()
                .to_vec(),
        ),
        ..quoted
    };
    let result = build_decision_legacy_v0(&plain_yaml, &request()).unwrap();
    assert!(render_decision_json_legacy_v0(&result).is_err());
}

#[test]
fn legacy_v0_distinguishes_missing_mode_label_from_present_empty_cell() {
    let make = |usage_csv: &[u8]| DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","force_decision":"抽"}]}"#
                .as_bytes()
                .to_vec(),
        ),
        usage_csv: Some(usage_csv.to_vec()),
        ..Default::default()
    };
    let missing = build_decision_legacy_v0(
        &make(b"collect_date,mode,sub_mode,character_slug,app_rate\n2026-01-01,sd,all,x,12\n"),
        &request(),
    )
    .unwrap();
    assert_eq!(
        missing.payload["cards"][0]["history_summary"]["modes"]["sd"]["mode_cn"],
        "sd"
    );
    let empty = build_decision_legacy_v0(
        &make(b"collect_date,mode,mode_cn,sub_mode,character_slug,app_rate\n2026-01-01,sd,,all,x,12\n"),
        &request(),
    )
    .unwrap();
    assert_eq!(
        empty.payload["cards"][0]["history_summary"]["modes"]["sd"]["mode_cn"],
        ""
    );
}

#[test]
fn legacy_v0_preserves_dict_reader_none_in_team_and_changelog_raw_fields() {
    let inputs = DecisionLegacyInputsV0 {
        box_config: empty_box(),
        rules_config: Some(
            r#"{"candidates":[{"slug":"x","force_decision":"抽"}]}"#
                .as_bytes()
                .to_vec(),
        ),
        team_raw_csv: Some(b"char_1_slug,rank,collect_date\nx,1\n".to_vec()),
        changelog_history_csv: Some(b"character_slugs,changelog_date\nx\n".to_vec()),
        ..Default::default()
    };
    let result = build_decision_legacy_v0(&inputs, &request()).unwrap();
    let history = &result.payload["cards"][0]["history_summary"];
    assert!(history["latest_team_examples"][0]["collect_date"].is_null());
    assert_eq!(history["latest_team_examples"][0]["mode_cn"], "");
    assert_eq!(history["latest_team_examples"][0]["sub_mode_cn"], "");
    assert_eq!(history["latest_team_examples"][0]["rank"], "1");
    assert!(history["changelog_latest"].is_null());
}
