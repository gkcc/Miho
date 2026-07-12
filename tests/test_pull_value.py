import csv
import json
from types import SimpleNamespace

import pytest

from miho_core.evidence import build_evidence_pool
from miho_core.pull_value import (
    _build_card,
    _rerun_value,
    _usage_summary,
    build_pull_value_cards,
    load_mechanism_notes,
    write_gpt_review_packet,
    write_pull_value_report,
)
from zzz_endgame_exporter.cli import main


def test_pull_value_distinguishes_rerun_and_new_character(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)

    result = build_pull_value_cards(out, box_path=box, plan_path=plan, statuses=["next"])
    cards = {card.slug: card for card in result["cards"]}

    assert cards["sunna"].candidate_type == "rerun"
    assert cards["sunna"].pull_value == "中"
    assert "历史出场点" in "；".join(cards["sunna"].decision_basis)
    assert "mechanism_review" in "；".join(cards["sunna"].decision_basis)
    assert "target coverage 定性" in "；".join(cards["sunna"].risk_notes)
    assert cards["sunna"].stage_recommendation["recommended_stage"] == "0+0"
    assert cards["sunna"].stage_recommendation["unresolved_stage"] == "0+1 / 1+0 / 1+1 / 2+1"
    assert cards["sunna"].stage_recommendation["stage_confidence"] == "medium"
    assert "未判定" in cards["sunna"].stage_recommendation["not_recommended_stage"]
    assert cards["sunna"].evidence_ids
    assert cards["sunna"].evidence_keys
    assert cards["sunna"].evidence_refs[0]["evidence_key"] == cards["sunna"].evidence_keys[0]
    assert isinstance(cards["sunna"].risk_evidence_ids, tuple)
    assert cards["nom"].candidate_type == "new"
    assert cards["nom"].pull_value == "等实测"
    assert "没有历史队伍记录属于正常未实测状态" in "；".join(cards["nom"].decision_basis)
    assert cards["nom"].stage_recommendation["recommended_stage"] == "等技能/影画/专武/首轮数据"


@pytest.mark.parametrize(
    ("confidences", "expected"),
    [
        (["A"], "高"),
        (["B+"], "中高"),
        (["B", "B"], "中高"),
        (["B"], "中"),
        ([], "中"),
    ],
)
def test_rerun_priority_is_capped_by_qualifying_evidence(confidences, expected):
    primary = [SimpleNamespace(confidence=value, mode="sd") for value in confidences]

    value, _, _, risks = _rerun_value(
        {},
        {
            "best_avg_last3": 40,
            "points": 6,
            "modes": {"sd": {"avg_last3": 40, "points": 6}},
        },
        {
            "best_rating": 11,
            "best_tier": "T0",
            "by_mode": {"sd": {"best_rating": 11}},
        },
        [],
        primary,
        primary,
        primary,
        False,
        {},
    )

    assert value == expected
    if expected == "中":
        assert any("A/B" in risk or "同 mode" in risk for risk in risks)


def test_pull_priority_does_not_join_tier_usage_and_evidence_across_modes():
    primary = [SimpleNamespace(confidence="A", mode="sd")]

    value, _, _, risks = _rerun_value(
        {},
        {
            "best_avg_last3": 40,
            "points": 6,
            "modes": {"da": {"avg_last3": 40, "points": 6}},
        },
        {
            "best_rating": 11,
            "best_tier": "T0",
            "by_mode": {"sd": {"best_rating": 11}},
        },
        [],
        primary,
        primary,
        primary,
        False,
        {},
    )

    assert value == "中"
    assert any("同一 mode" in risk for risk in risks)


def test_unowned_candidate_uses_only_exact_plan_dependency_as_main_evidence():
    def record(evidence_id, confidence, dependencies):
        return SimpleNamespace(
            evidence_id=evidence_id,
            evidence_key=f"sd|{evidence_id}",
            confidence=confidence,
            source_confidence=confidence,
            mode="sd",
            team_slugs=("candidate", "owned-a", "owned-b"),
            plan_dependency=tuple(dependencies),
            phase_versions=("3.0",),
            scopes=("all",),
            observation_keys=(f"obs-{evidence_id}",),
            max_app_rate=40.0,
            record_count=12,
        )

    exact_b = record("E-exact", "B", ["candidate"])
    conditional_a = record("E-conditional", "A", ["candidate", "other-planned"])
    empty_pool = SimpleNamespace(records=[])
    target_pool = SimpleNamespace(records=[conditional_a, exact_b])
    usage_rows = [
        {
            "collect_date": f"2026-0{month}-01",
            "mode": "sd",
            "sub_mode": "all",
            "character_slug": "candidate",
            "app_rate": "40",
        }
        for month in range(1, 7)
    ]
    card = _build_card(
        {"slug": "candidate", "banner_role": "rerun", "status": "next"},
        names={"candidate": "候选"},
        owned=set(),
        current_pool=empty_pool,
        target_pool=target_pool,
        usage_rows=usage_rows,
        tier_index={
            "candidate": {
                "best_rating": 11,
                "best_tier": "T0",
                "by_mode": {"sd": {"best_rating": 11}},
            }
        },
        mechanism_notes={},
        decision_baseline={},
    )

    assert card.pull_value == "中"
    assert card.evidence_ids == ("E-exact",)
    assert card.risk_evidence_ids == ("E-conditional",)
    assert any("新增依赖队伍 1 条" in basis for basis in card.decision_basis)
    assert any("同时依赖其他计划角色" in risk for risk in card.risk_notes)


def test_non_finite_usage_is_not_counted_as_history():
    usage = _usage_summary(
        "agent-a",
        [
            {
                "character_slug": "agent-a",
                "sub_mode": "all",
                "mode": "sd",
                "collect_date": "2026-07-12",
                "app_rate": "NaN",
            }
        ],
    )

    assert usage["points"] == 0
    assert usage["modes"] == {}


def test_non_finite_mechanism_note_is_rejected(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "agent-a.yaml").write_text("stage_confidence: .nan\n", encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite number"):
        load_mechanism_notes(notes, candidates=["agent-a"])


def test_empty_mechanism_candidate_set_skips_unrelated_broken_notes(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "agent-a.yaml").write_text("broken: [\n", encoding="utf-8")

    assert load_mechanism_notes(notes, candidates=[]) == {}


@pytest.mark.parametrize("token", ["NaN", "Infinity", "1e400"])
def test_non_finite_banner_plan_is_rejected(tmp_path, token):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = tmp_path / "non_finite_plan.json"
    plan.write_text(f'{{"phases": [], "unused": {token}}}', encoding="utf-8")

    with pytest.raises(ValueError, match="non-finite number"):
        build_pull_value_cards(out, box_path=box, plan_path=plan, statuses=["current"])


def test_pull_value_cli_writes_report(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)
    output = tmp_path / "pull_value.md"

    result = main(["pull-value", "--box", str(box), "--out", str(out), "--plan", str(plan), "--output", str(output)])

    assert result == 0
    text = output.read_text(encoding="utf-8")
    assert "# 绝区零 Pull Value Report" in text
    assert "千夏 `sunna`" in text
    assert "诺姆 `nom`" in text
    assert "没有历史队伍记录是未实测状态，不作为负面扣分" in text
    assert "recommended_stage" in text
    assert "unresolved_stage" in text
    assert "stage_confidence" in text
    assert "mechanism_review" in text


def test_gpt_review_packet_writes_no_key_prompt(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)
    output = tmp_path / "packet.md"

    write_gpt_review_packet(out, box_path=box, plan_path=plan, output_path=output)

    text = output.read_text(encoding="utf-8")
    assert "# GPT Pull Reviewer Packet" in text
    assert "无 API key 的交互版" in text
    assert '"slug": "sunna"' in text
    assert '"slug": "nom"' in text
    assert '"recommended_stage": "0+0"' in text
    assert '"stage_confidence": "medium"' in text
    assert '"mechanism_notes"' in text
    assert '"risk_evidence_ids"' in text
    assert '"evidence_refs"' in text
    assert '"final_stage"' in text
    assert '"local_rule_stage"' in text
    assert "新角色没有历史队伍记录只能标记为未实测" in text


def test_low_rarity_plan_candidates_are_filtered_but_kept_in_coverage(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)

    result = build_pull_value_cards(out, box_path=box, plan_path=plan, statuses=["current"])
    slugs = {card.slug for card in result["cards"]}

    assert "sunna" in slugs
    assert "piper" not in slugs
    assert "nicole-demara" not in slugs
    assert "piper" in result["summary"]["planned_slugs"]
    assert "nicole-demara" in result["summary"]["planned_slugs"]
    assert "piper" in result["summary"]["filtered_low_rarity_slugs"]
    assert "nicole-demara" in result["summary"]["filtered_low_rarity_slugs"]

    pool = build_evidence_pool(
        out,
        owned_slugs=["miyabi", "lucy"],
        planned_slugs=result["summary"]["planned_slugs"],
        scenario="target_box",
    )

    assert any("piper" in record.team_slugs for record in pool.records)
    assert any("nicole-demara" in record.team_slugs for record in pool.records)


def test_gpt_review_packet_excludes_low_rarity_by_default(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)
    output = tmp_path / "current_packet.md"

    write_gpt_review_packet(out, box_path=box, plan_path=plan, statuses=["current"], output_path=output)

    text = output.read_text(encoding="utf-8")
    assert '"slug": "sunna"' in text
    assert '"slug": "piper"' not in text
    assert '"slug": "nicole-demara"' not in text
    assert "A 级 / 四星角色默认不作为独立抽取价值候选" in text


def test_low_rarity_can_be_force_reviewed(tmp_path):
    for flag in ("force_review", "include_low_rarity"):
        case = tmp_path / flag
        case.mkdir()
        out = _write_pull_fixture(case)
        box = _write_box(case)
        plan = _write_plan(case, piper_extra={flag: True})
        _write_mechanism_notes(case)

        result = build_pull_value_cards(out, box_path=box, plan_path=plan, statuses=["current"])
        slugs = {card.slug for card in result["cards"]}

        assert "piper" in slugs


def test_decision_baseline_keeps_prior_final_stage_when_local_rule_differs(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    baseline = _write_decision_baseline(tmp_path)
    _write_mechanism_notes(tmp_path)

    result = build_pull_value_cards(out, box_path=box, plan_path=plan, statuses=["current"], decision_baseline_path=baseline)
    cards = {card.slug: card for card in result["cards"]}

    ye = cards["ye-shunguang"]
    assert ye.local_rule_stage == "0+0"
    assert ye.prior_final_stage == "1+1"
    assert ye.final_stage == "1+1"
    assert ye.recommended_stage_for_review == "1+1"
    assert ye.stage_delta == "0+0 -> 1+1"
    assert ye.delta_requires_review is True
    assert ye.change_allowed_reason == "only_with_new_evidence"

    velina = cards["velina"]
    assert velina.local_rule_stage == "等实测"
    assert velina.prior_final_stage == "0+1"
    assert velina.final_stage == "0+1"
    assert velina.stage_delta == "等实测 -> 0+1"
    assert velina.delta_requires_review is True


def test_pull_value_report_shows_baseline_final_stage_and_delta(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    baseline = _write_decision_baseline(tmp_path)
    _write_mechanism_notes(tmp_path)
    output = tmp_path / "pull_value.md"

    write_pull_value_report(
        out,
        box_path=box,
        plan_path=plan,
        statuses=["current"],
        decision_baseline_path=baseline,
        output_path=output,
    )

    text = output.read_text(encoding="utf-8")
    assert "prior_final_stage | local_rule_stage | final_stage | stage_delta | delta_requires_review | change_allowed_reason" in text
    assert "叶瞬光 `ye-shunguang` | rerun | 中 | 1+1 | 0+0 | 1+1 | 0+0 -> 1+1 | yes | only_with_new_evidence" in text
    assert "维琳娜 `velina` | new | 等实测 | 0+1 | 等实测 | 0+1 | 等实测 -> 0+1 | yes | only_with_new_evidence" in text
    assert "派派 `piper`" not in text
    assert "妮可 `nicole-demara`" not in text


def test_review_packet_includes_baseline_delta_fields(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    baseline = _write_decision_baseline(tmp_path)
    _write_mechanism_notes(tmp_path)
    output = tmp_path / "current_packet.md"

    write_gpt_review_packet(
        out,
        box_path=box,
        plan_path=plan,
        statuses=["current"],
        decision_baseline_path=baseline,
        output_path=output,
    )

    text = output.read_text(encoding="utf-8")
    assert '"slug": "ye-shunguang"' in text
    assert '"prior_final_stage": "1+1"' in text
    assert '"local_rule_stage": "0+0"' in text
    assert '"final_stage": "1+1"' in text
    assert '"delta_requires_review": true' in text
    assert '"risk_evidence_ids"' in text
    assert '"slug": "piper"' not in text


def test_review_packet_cli_writes_packet(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)
    output = tmp_path / "packet_cli.md"

    result = main(["review-packet", "--box", str(box), "--out", str(out), "--plan", str(plan), "--output", str(output)])

    assert result == 0
    assert "GPT Pull Reviewer Packet" in output.read_text(encoding="utf-8")


def test_pull_value_cli_writes_current_and_next_reports_by_default(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)

    result = main(["pull-value", "--box", str(box), "--out", str(out), "--plan", str(plan)])

    assert result == 0
    assert (out / "current_pull_value_report.md").exists()
    assert (out / "next_pull_value_report.md").exists()
    assert not (out / "pull_value_report.md").exists()


def test_review_packet_cli_writes_current_and_next_packets_by_default(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)

    result = main(["review-packet", "--box", str(box), "--out", str(out), "--plan", str(plan)])

    assert result == 0
    assert (out / "current_gpt_pull_reviewer_packet.md").exists()
    assert (out / "next_gpt_pull_reviewer_packet.md").exists()
    assert not (out / "gpt_pull_reviewer_packet.md").exists()


def _write_pull_fixture(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _write_csv(
        out / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn", "aliases", "kind"],
        [
            {"character_slug": "miyabi", "character_name_en": "Miyabi", "character_name_cn": "星见雅", "aliases": "", "kind": "agent"},
            {"character_slug": "lucy", "character_name_en": "Lucy", "character_name_cn": "露西", "aliases": "", "kind": "agent"},
            {"character_slug": "sunna", "character_name_en": "Sunna", "character_name_cn": "千夏", "aliases": "", "kind": "agent"},
            {"character_slug": "nom", "character_name_en": "Nom", "character_name_cn": "诺姆", "aliases": "", "kind": "agent"},
            {"character_slug": "piper", "character_name_en": "Piper", "character_name_cn": "派派", "aliases": "", "kind": "agent"},
            {"character_slug": "nicole-demara", "character_name_en": "Nicole Demara", "character_name_cn": "妮可", "aliases": "", "kind": "agent"},
            {"character_slug": "ye-shunguang", "character_name_en": "Ye Shunguang", "character_name_cn": "叶瞬光", "aliases": "", "kind": "agent"},
            {"character_slug": "velina", "character_name_en": "Velina", "character_name_cn": "维琳娜", "aliases": "", "kind": "agent"},
        ],
    )
    _write_csv(
        out / "character_usage_long.csv",
        ["collect_date", "mode", "sub_mode", "phase_ver", "character_slug", "app_rate"],
        [
            {"collect_date": "2026-04-01", "mode": "sd", "sub_mode": "all", "phase_ver": "2.7.1", "character_slug": "sunna", "app_rate": 40},
            {"collect_date": "2026-05-01", "mode": "sd", "sub_mode": "all", "phase_ver": "2.8.1", "character_slug": "sunna", "app_rate": 50},
            {"collect_date": "2026-06-01", "mode": "sd", "sub_mode": "all", "phase_ver": "2.8.3", "character_slug": "sunna", "app_rate": 60},
            {"collect_date": "2026-04-01", "mode": "da", "sub_mode": "all", "phase_ver": "2.7.1", "character_slug": "sunna", "app_rate": 35},
            {"collect_date": "2026-05-01", "mode": "da", "sub_mode": "all", "phase_ver": "2.8.1", "character_slug": "sunna", "app_rate": 45},
            {"collect_date": "2026-06-01", "mode": "da", "sub_mode": "all", "phase_ver": "2.8.3", "character_slug": "sunna", "app_rate": 55},
            {"collect_date": "2026-06-01", "mode": "sd", "sub_mode": "all", "phase_ver": "3.0.1", "character_slug": "ye-shunguang", "app_rate": 44},
            {"collect_date": "2026-06-01", "mode": "sd", "sub_mode": "all", "phase_ver": "3.0.1", "character_slug": "velina", "app_rate": 12},
        ],
    )
    _write_csv(
        out / "prydwen_tier_current.csv",
        ["tier_mode", "character_slug", "character_name_cn", "role_group_cn", "tier", "rating", "element_cn", "style_cn", "rarity"],
        [
            {"tier_mode": "sd", "character_slug": "sunna", "character_name_cn": "千夏", "role_group_cn": "辅助", "tier": "T0", "rating": 11, "element_cn": "物理", "style_cn": "支援", "rarity": "S"},
            {"tier_mode": "da", "character_slug": "sunna", "character_name_cn": "千夏", "role_group_cn": "辅助", "tier": "T0", "rating": 11, "element_cn": "物理", "style_cn": "支援", "rarity": "S"},
            {"tier_mode": "sd", "character_slug": "piper", "character_name_cn": "派派", "role_group_cn": "异常主C", "tier": "T1", "rating": 9, "element_cn": "物理", "style_cn": "异常", "rarity": "A"},
            {"tier_mode": "sd", "character_slug": "nicole-demara", "character_name_cn": "妮可", "role_group_cn": "支援", "tier": "T1", "rating": 8, "element_cn": "以太", "style_cn": "支援", "rarity": "A"},
            {"tier_mode": "sd", "character_slug": "ye-shunguang", "character_name_cn": "叶瞬光", "role_group_cn": "直伤主C", "tier": "T0", "rating": 11, "element_cn": "物理", "style_cn": "强攻", "rarity": "S"},
            {"tier_mode": "sd", "character_slug": "velina", "character_name_cn": "维琳娜", "role_group_cn": "异常主C", "tier": "T0.5", "rating": 10, "element_cn": "风", "style_cn": "异常", "rarity": "S"},
        ],
    )
    _write_csv(
        out / "team_rank_dedup_unordered.csv",
        [
            "snapshot_id",
            "collect_date",
            "mode",
            "mode_cn",
            "sub_mode",
            "sub_mode_cn",
            "phase_ver",
            "phase_name",
            "scope",
            "rank",
            "char_1_slug",
            "char_2_slug",
            "char_3_slug",
            "bangboo_slug",
            "app_rate",
            "avg_score",
            "source_kind",
        ],
        [
            _team("2.8.1", "sd", "5-1", "miyabi", "lucy", "sunna", 14, 33000),
            _team("2.8.1", "sd", "5-2", "miyabi", "lucy", "sunna", 12, 33100),
            _team("2.8.2", "sd", "5-1", "miyabi", "lucy", "sunna", 11, 33200),
            _team("2.8.2", "sd", "5-2", "miyabi", "lucy", "sunna", 10, 33300),
            _team("2.8.3", "sd", "5-1", "miyabi", "lucy", "sunna", 9, 33400),
            _team("2.8.3", "sd", "5-2", "miyabi", "lucy", "sunna", 8, 33500),
            _team("2.8.3", "sd", "5-3", "miyabi", "piper", "sunna", 2, 31000),
            _team("2.8.3", "sd", "5-4", "miyabi", "nicole-demara", "sunna", 2, 30900),
        ],
    )
    return out


def _write_box(tmp_path):
    box = tmp_path / "box.json"
    box.write_text(json.dumps({"owned": ["miyabi", "lucy"]}), encoding="utf-8")
    return box


def _write_plan(tmp_path, *, piper_extra=None):
    plan = tmp_path / "plan.json"
    piper = {"slug": "piper", "name_cn": "派派", "banner_role": "A 级陪跑", "analysis_tags": ["A 级", "物理", "异常"]}
    if piper_extra:
        piper.update(piper_extra)
    plan.write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "status": "current",
                        "characters": [
                            {"slug": "velina", "name_cn": "维琳娜", "banner_role": "限定 S 级 UP", "analysis_tags": ["新角色", "风", "异常"]},
                            {"slug": "ye-shunguang", "name_cn": "叶瞬光", "banner_role": "限定 S 级复刻", "analysis_tags": ["复刻", "物理", "强攻"]},
                            {"slug": "sunna", "name_cn": "千夏", "banner_role": "限定 S 级复刻", "analysis_tags": ["复刻", "辅助"]},
                            piper,
                            {"slug": "nicole-demara", "name_cn": "妮可", "banner_role": "A 级陪跑", "analysis_tags": ["A 级", "以太", "支援"]},
                        ],
                    },
                    {
                        "status": "next",
                        "characters": [
                            {"slug": "nom", "name_cn": "诺姆", "banner_role": "限定 S 级 UP", "analysis_tags": ["新角色"], "focus": "机制未知，等实测"},
                            {"slug": "sunna", "name_cn": "千夏", "banner_role": "限定 S 级复刻", "analysis_tags": ["复刻", "辅助"]},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return plan


def _write_decision_baseline(tmp_path):
    baseline = tmp_path / "zzz_decision_baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "new_evidence_categories": [
                    "新一期 SD/DA 出场率显著变化",
                    "新队伍 coverage 从 B-/C 提升到 A/B+",
                    "专武/影画机制 notes 更新",
                    "主流指南共识变化",
                    "当前 Box 变化",
                    "用户目标或预算变化",
                ],
                "decisions": [
                    {
                        "slug": "ye-shunguang",
                        "final_stage": "1+1",
                        "decision_status": "locked",
                        "confidence": "medium_high",
                        "source": "manual_gpt_review",
                        "reason": "测试基线：叶瞬光 1+1",
                        "change_policy": "only_with_new_evidence",
                    },
                    {
                        "slug": "velina",
                        "final_stage": "0+1",
                        "decision_status": "soft_locked",
                        "confidence": "medium",
                        "source": "manual_gpt_review",
                        "reason": "测试基线：维琳娜 0+1",
                        "change_policy": "only_with_new_evidence",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return baseline


def _write_mechanism_notes(tmp_path):
    notes = tmp_path / "zzz_mechanism_notes"
    notes.mkdir()
    (notes / "ye-shunguang.yaml").write_text(
        """
recommended_stage: 0+0
acceptable_stage: 0+0
unresolved_stage: 0+1 / 1+0 / 1+1 / 2+1
stage_confidence: medium
not_recommended_stage: 未判定
stage_reason: 测试机制笔记支持本体
missing_data: 专武和影画收益
source_quality:
  historical_usage: high
stage_notes:
  "0+0":
    value_type: 本体完整度
    evidence: 历史强
    missing_data: 无
""",
        encoding="utf-8",
    )
    (notes / "velina.yaml").write_text(
        """
recommended_stage: 等实测
acceptable_stage: 暂不预设
unresolved_stage: 0+0 / 0+1 / 1+0 / 1+1 / 2+1
stage_confidence: low
not_recommended_stage: 暂不判断
stage_reason: 新角色测试笔记等待实测
missing_data: 首轮数据
source_quality:
  historical_usage: first_cycle_only
stage_notes:
  "0+0":
    value_type: 本体完整度
    evidence: 新角色身份确认
    missing_data: 首轮数据
""",
        encoding="utf-8",
    )
    (notes / "sunna.yaml").write_text(
        """
body_completeness_0_0: 本体完整
signature_value_0_1: 专武可选
cinema_value_1_0: 影画可选
combo_value_1_1: 组合非必需
necessity_2_1: 非必要
higher_stage_note: 2+1 以上只在机制/指南/实战证明必要时考虑
recommended_stage: 0+0
acceptable_stage: 0+0
unresolved_stage: 0+1 / 1+0 / 1+1 / 2+1
stage_confidence: medium
not_recommended_stage: 未判定 / 缺证据：2+1以上需要机制、指南、实战证据
stage_reason: 机制评审支持本体，其他档位待实证
missing_data: 专武对比和影画收益
source_quality:
  identity: test
  historical_usage: high
  breakpoints: pending
stage_notes:
  "0+0":
    value_type: 本体完整度
    evidence: 本体完整
    missing_data: 无
  "0+1":
    value_type: 专武价值
    evidence: 专武可选
    missing_data: 专武对比
  "1+0":
    value_type: 影画断点
    evidence: 影画可选
    missing_data: 影画收益
  "1+1":
    value_type: 组合价值
    evidence: 待组合收益
    missing_data: 组合实测
  "2+1":
    value_type: 高档位必要性
    evidence: 未证明必要
    missing_data: 2+1 实测
key_teammates: [miyabi, lucy]
archetypes: [辅助]
risks_and_counterevidence: target coverage 不能单独定性
source_url: https://example.com/sunna
source_summary: 测试机制笔记
""",
        encoding="utf-8",
    )
    return notes


def _team(phase, mode, sub_mode, char_1, char_2, char_3, app_rate, avg_score):
    return {
        "snapshot_id": phase,
        "collect_date": "2026-06-01",
        "mode": mode,
        "mode_cn": "式舆防卫",
        "sub_mode": sub_mode,
        "sub_mode_cn": sub_mode,
        "phase_ver": phase,
        "phase_name": f"{mode} {phase}",
        "scope": f"{sub_mode}_combined.json",
        "rank": 1,
        "char_1_slug": char_1,
        "char_2_slug": char_2,
        "char_3_slug": char_3,
        "bangboo_slug": "",
        "app_rate": app_rate,
        "avg_score": avg_score,
        "source_kind": "hf_comps",
    }


def _write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
