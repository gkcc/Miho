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
fn alias_only_usage_is_canonicalized_into_rerun_history_and_medium_value() {
    let mut inputs = inputs();
    inputs
        .evidence
        .name_map_csv
        .as_mut()
        .unwrap()
        .extend_from_slice(b"alias-medium,Alias Medium,Alias Medium,medium-usage-alias,agent\n");
    inputs.usage_csv = Some(
        b"collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\n2026-07-12,sd,all,3.0,medium-usage-alias,7.5\n"
            .to_vec(),
    );

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["alias-medium".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let candidate = bundle
        .cards
        .iter()
        .find(|card| card.slug == "alias-medium")
        .unwrap();

    assert_eq!(candidate.candidate_type, "rerun");
    assert_eq!(candidate.pull_value, "中");
    assert_eq!(
        candidate.history_summary,
        "sd: points 1 / latest 7.5% / avg_last3 7.5% / trend 0"
    );
    assert_eq!(
        candidate.global_usage_summary,
        "best_latest=7.5%；best_avg_last3=7.5%；worst_trend=0"
    );
}

#[test]
fn rerun_without_mechanism_notes_uses_history_aware_stage_copy() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\n2026-07-12,sd,all,3.0,history-only,7.5\n"
            .to_vec(),
    );

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["history-only".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let candidate = bundle
        .cards
        .iter()
        .find(|card| card.slug == "history-only")
        .unwrap();

    assert_eq!(candidate.candidate_type, "rerun");
    assert_eq!(
        candidate.mechanism_review_summary,
        "暂无 mechanism_notes；已有历史实战仅支持本体价值，X+X 档位等待机制评审"
    );
    assert_eq!(
        candidate.stage_recommendation.recommended_stage,
        "等机制档位评审"
    );
    assert_eq!(candidate.stage_recommendation.acceptable_stage, "暂不预设");
    assert_eq!(
        candidate.stage_recommendation.unresolved_stage,
        "0+0 / 0+1 / 1+0 / 1+1 / 2+1"
    );
    assert_eq!(candidate.stage_recommendation.stage_confidence, "low");
    assert_eq!(
        candidate.stage_recommendation.not_recommended_stage,
        "暂不判断"
    );
    assert_eq!(
        candidate.stage_recommendation.reason,
        "已有历史 usage/队伍证据，但缺少 mechanism_notes，不能据此推导 X+X 档位"
    );
    assert_eq!(
        candidate.stage_recommendation.missing_data,
        "mechanism_notes、专武与影画断点、攻略共识、当前版本档位收益对比"
    );
    assert!(candidate.decision_basis.iter().any(|basis| basis
        == "mechanism_review：暂无 mechanism_notes；已有历史实战仅支持本体价值，X+X 档位等待机制评审"));
}

#[test]
fn tier_only_rerun_without_mechanism_notes_does_not_invent_history() {
    let mut inputs = inputs();
    inputs
        .evidence
        .tier_csv
        .as_mut()
        .unwrap()
        .extend_from_slice(b"sd,tier-only,\xe5\x8f\xaa\xe6\x9c\x89T\xe6\xa6\x9c,\xe5\xbc\xba\xe6\x94\xbb,T1,8,\xe7\x81\xab,\xe5\xbc\xba\xe6\x94\xbb,S\n");

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["tier-only".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let candidate = bundle
        .cards
        .iter()
        .find(|card| card.slug == "tier-only")
        .unwrap();

    assert_eq!(candidate.candidate_type, "rerun");
    assert!(!candidate.stage_recommendation.reason.contains("已有历史"));
    assert!(!candidate.stage_recommendation.reason.contains("首轮"));
    assert!(candidate
        .stage_recommendation
        .missing_data
        .contains("历史实战"));
    assert_eq!(
        candidate.mechanism_review_summary,
        "暂无 mechanism_notes；复刻角色档位等待机制评审与历史实战复核"
    );
}

#[test]
fn first_cycle_uses_global_complete_teams_without_box_coverage_or_usage() {
    let bundle = build_pull_value_bundle_v1(
        &inputs(),
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let nova = bundle
        .cards
        .iter()
        .find(|card| card.slug == "nova")
        .unwrap();

    assert_eq!(nova.candidate_type, "new");
    assert_eq!(nova.pull_value, "等实测");
    assert_eq!(
        nova.history_summary,
        "暂无全局 usage 出场点；完整真实队伍表已有首轮实测（1 snapshot）"
    );
    assert!(nova.evidence_ids.is_empty());
    assert_eq!(
        nova.team_coverage_summary,
        "current 0(0)；target 0(0)；新增依赖 0(0)"
    );
    assert_eq!(
        nova.decision_basis[0],
        "新角色首轮实测已到：1 个 snapshot，当前仅单期/B- 证据；等待跨期复测，不自动提升推荐档位"
    );
    assert_eq!(
        nova.risk_notes[0],
        "首轮数据不能替代跨期稳定性验证；SD/DA 同 snapshot 只计一次"
    );
    assert_eq!(
        nova.risk_notes[1],
        "首轮已到，仍需跨期 SD/DA 复测和机制资料"
    );
    assert!(!nova
        .risk_notes
        .iter()
        .any(|risk| risk.contains("等技能/影画/专武/首轮数据")));
    assert_eq!(nova.stage_recommendation.recommended_stage, "等实测");
    assert_eq!(
        nova.stage_recommendation.reason,
        "首轮实测已到，但当前仅 1 个 snapshot 的单期/B- 证据，不能据此预设 X+X 档位"
    );
    assert_eq!(
        nova.stage_recommendation.missing_data,
        "技能机制、影画、专武、跨期高难复测"
    );
    assert_eq!(
        nova.mechanism_review_summary,
        "暂无 mechanism_notes；首轮已到，等待机制资料与跨期复测"
    );
    assert!(!nova
        .decision_basis
        .iter()
        .any(|basis| basis.contains("没有历史队伍记录")));
}

#[test]
fn alias_only_complete_team_is_a_first_cycle_observation() {
    let mut inputs = inputs();
    inputs.usage_csv = None;
    inputs
        .evidence
        .name_map_csv
        .as_mut()
        .unwrap()
        .extend_from_slice(b"nova,Nova,Nova,nova-alias,agent\n");
    inputs.evidence.team_rank_dedup_unordered_csv = b"snapshot_id,collect_date,mode,phase_ver,app_rate,avg_score,char_1_slug,char_2_slug,char_3_slug\nalias-cycle,2026-07-01,sd,3.0.1,1.5,50101,nova-alias,anchor-uno,support-alias\n".to_vec();

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let nova = bundle
        .cards
        .iter()
        .find(|card| card.slug == "nova")
        .unwrap();

    assert_eq!(nova.candidate_type, "new");
    assert_eq!(
        nova.history_summary,
        "暂无全局 usage 出场点；完整真实队伍表已有首轮实测（1 snapshot）"
    );
    assert!(nova.decision_basis[0].contains("1 个 snapshot"));
    assert!(!nova.decision_basis[0].contains("跨期实测："));
}

#[test]
fn usage_snapshot_and_snapshotless_team_on_same_date_and_phase_are_one_cycle() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"snapshot_id,collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\nusage-cycle,2026-07-01,sd,all,3.0.1,nova,11.7\n"
            .to_vec(),
    );
    inputs.evidence.team_rank_dedup_unordered_csv = b"snapshot_id,collect_date,mode,phase_ver,app_rate,avg_score,char_1_slug,char_2_slug,char_3_slug\n,2026-07-01,da,3.0.1,14.94,60101,nova,offbox-one,offbox-two\n".to_vec();

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let nova = bundle
        .cards
        .iter()
        .find(|card| card.slug == "nova")
        .unwrap();

    assert!(nova.decision_basis[0].contains("1 个 snapshot"));
    assert!(!nova.decision_basis[0].contains("新角色已有跨期实测"));
}

#[test]
fn distinct_snapshots_in_the_same_phase_remain_repeated_observations() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"snapshot_id,collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\ncycle-a,2026-07-01,sd,all,3.0.1,nova,11.7\ncycle-b,2026-07-01,da,all,3.0.1,nova,14.94\n,2026-07-01,sd,all,3.0.1,nova,12.5\n"
            .to_vec(),
    );
    inputs.evidence.team_rank_dedup_unordered_csv = b"snapshot_id,collect_date,mode,phase_ver,app_rate,avg_score,char_1_slug,char_2_slug,char_3_slug\n".to_vec();

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let nova = bundle
        .cards
        .iter()
        .find(|card| card.slug == "nova")
        .unwrap();

    assert!(nova.decision_basis[0].contains("新角色已有跨期实测：2 个 snapshot"));
}

#[test]
fn padded_case_insensitive_all_keeps_usage_and_observation_state_consistent() {
    let mut inputs = inputs();
    inputs.usage_csv = Some(
        b"snapshot_id,collect_date,mode,sub_mode,phase_ver,character_slug,app_rate\nspace-all-cycle,2026-07-01,sd, ALL ,3.0.1,nova,11.7\n"
            .to_vec(),
    );
    inputs.evidence.team_rank_dedup_unordered_csv = b"snapshot_id,collect_date,mode,phase_ver,app_rate,avg_score,char_1_slug,char_2_slug,char_3_slug\n".to_vec();

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let nova = bundle
        .cards
        .iter()
        .find(|card| card.slug == "nova")
        .unwrap();

    assert!(nova.history_summary.starts_with("sd: points 1"));
    assert!(nova.decision_basis[0].contains("1 个 snapshot"));
    assert!(!nova.decision_basis[0].contains("尚无全局 usage"));
}

#[test]
fn new_observation_states_keep_unobserved_and_repeated_distinct() {
    let repeated = build_pull_value_bundle_v1(
        &inputs(),
        &PullValueRequestV1 {
            plan_statuses: vec!["next".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let zeta = repeated
        .cards
        .iter()
        .find(|card| card.slug == "zeta")
        .unwrap();
    assert_eq!(zeta.candidate_type, "new");
    assert_eq!(zeta.pull_value, "等实测");
    assert_eq!(
        zeta.decision_basis[0],
        "新角色已有跨期实测：6 个 snapshot；仍需结合机制与账号价值复核，不自动提升推荐档位"
    );
    assert_eq!(
        zeta.risk_notes[0],
        "已有跨期记录不等于推荐档位自动升级，仍需复核证据质量与机制必要性"
    );
    assert_eq!(
        zeta.risk_notes[1],
        "已有跨期数据，仍需补齐机制、专属收益和替代关系"
    );
    assert_eq!(
        zeta.history_summary,
        "暂无全局 usage 出场点；完整真实队伍表已有跨期实测（6 snapshots）"
    );
    assert_eq!(zeta.stage_recommendation.recommended_stage, "等实测");
    assert_eq!(
        zeta.stage_recommendation.reason,
        "已有 6 个 snapshot 的跨期实测，但缺少 mechanism_notes，不能据此自动升级 X+X 档位"
    );
    assert_eq!(
        zeta.mechanism_review_summary,
        "暂无 mechanism_notes；已有跨期实测，等待机制资料与证据质量复核"
    );

    let unobserved = build_pull_value_bundle_v1(
        &inputs(),
        &PullValueRequestV1 {
            explicit_planned_slugs: vec!["unseen-new".to_owned()],
            plan_statuses: vec!["absent-status".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let unseen = unobserved
        .cards
        .iter()
        .find(|card| card.slug == "unseen-new")
        .unwrap();
    assert_eq!(unseen.candidate_type, "new");
    assert_eq!(
        unseen.decision_basis[0],
        "新角色尚无全局 usage 或完整队伍实测，属于正常未实测状态，不作为负面"
    );
    assert_eq!(
        unseen.stage_recommendation.recommended_stage,
        "等技能/影画/专武/首轮数据"
    );
}

#[test]
fn observed_new_mechanism_status_overrides_stale_focus_only_for_observed_new_characters() {
    let mut inputs = inputs();
    inputs.evidence.banner_plan_json = Some(
        r#"{
            "phases": [{
                "status": "current",
                "characters": [
                    {
                        "slug": "nova",
                        "banner_role": "限定 S 级新角色",
                        "focus": "首轮旧 focus"
                    },
                    {
                        "slug": "zeta",
                        "banner_role": "限定 S 级新角色",
                        "focus": "跨期旧 focus"
                    },
                    {
                        "slug": "unseen-new",
                        "banner_role": "限定 S 级新角色",
                        "focus": "未观测旧 focus"
                    },
                    {
                        "slug": "beta",
                        "banner_role": "限定 S 级复刻",
                        "focus": "复刻旧 focus"
                    }
                ]
            }]
        }"#
        .as_bytes()
        .to_vec(),
    );
    for (slug, status) in [
        ("nova", "首轮新机制摘要"),
        ("zeta", "跨期新机制摘要"),
        ("unseen-new", "未观测新机制摘要"),
        ("beta", "复刻新机制摘要"),
    ] {
        inputs.mechanism_notes.insert(
            slug.to_owned(),
            format!("mechanism_status: {status}\n").into_bytes(),
        );
    }

    let bundle = build_pull_value_bundle_v1(
        &inputs,
        &PullValueRequestV1 {
            plan_statuses: vec!["current".to_owned()],
            ..PullValueRequestV1::default()
        },
        &context(),
    )
    .unwrap();
    let card = |slug: &str| bundle.cards.iter().find(|card| card.slug == slug).unwrap();

    let nova = card("nova");
    assert_eq!(nova.candidate_type, "new");
    assert!(nova.mechanism_summary.contains("首轮新机制摘要"));
    assert!(!nova.mechanism_summary.contains("首轮旧 focus"));
    assert!(nova
        .decision_basis
        .iter()
        .any(|basis| basis.contains("首轮新机制摘要")));

    let zeta = card("zeta");
    assert_eq!(zeta.candidate_type, "new");
    assert!(zeta.mechanism_summary.contains("跨期新机制摘要"));
    assert!(!zeta.mechanism_summary.contains("跨期旧 focus"));

    let unseen = card("unseen-new");
    assert_eq!(unseen.candidate_type, "new");
    assert!(unseen.mechanism_summary.contains("未观测旧 focus"));
    assert!(!unseen.mechanism_summary.contains("未观测新机制摘要"));

    let beta = card("beta");
    assert_eq!(beta.candidate_type, "rerun");
    assert!(beta.mechanism_summary.contains("复刻旧 focus"));
    assert!(!beta.mechanism_summary.contains("复刻新机制摘要"));
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
