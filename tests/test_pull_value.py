import csv
import json

from miho_core.pull_value import build_pull_value_cards, write_gpt_review_packet
from zzz_endgame_exporter.cli import main


def test_pull_value_distinguishes_rerun_and_new_character(tmp_path):
    out = _write_pull_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = _write_plan(tmp_path)
    _write_mechanism_notes(tmp_path)

    result = build_pull_value_cards(out, box_path=box, plan_path=plan, statuses=["next"])
    cards = {card.slug: card for card in result["cards"]}

    assert cards["sunna"].candidate_type == "rerun"
    assert cards["sunna"].pull_value in {"高", "中高"}
    assert "历史出场点" in "；".join(cards["sunna"].decision_basis)
    assert "mechanism_review" in "；".join(cards["sunna"].decision_basis)
    assert "target coverage 定性" in "；".join(cards["sunna"].risk_notes)
    assert cards["sunna"].stage_recommendation["recommended_stage"] == "0+0"
    assert cards["sunna"].stage_recommendation["unresolved_stage"] == "0+1 / 1+0 / 1+1 / 2+1"
    assert cards["sunna"].stage_recommendation["stage_confidence"] == "medium"
    assert "未判定" in cards["sunna"].stage_recommendation["not_recommended_stage"]
    assert cards["sunna"].evidence_ids
    assert cards["nom"].candidate_type == "new"
    assert cards["nom"].pull_value == "等实测"
    assert "没有历史队伍记录属于正常未实测状态" in "；".join(cards["nom"].decision_basis)
    assert cards["nom"].stage_recommendation["recommended_stage"] == "等技能/影画/专武/首轮数据"


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
    assert "新角色没有历史队伍记录只能标记为未实测" in text


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
        ],
    )
    _write_csv(
        out / "prydwen_tier_current.csv",
        ["tier_mode", "character_slug", "character_name_cn", "role_group_cn", "tier", "rating", "element_cn", "style_cn"],
        [
            {"tier_mode": "sd", "character_slug": "sunna", "character_name_cn": "千夏", "role_group_cn": "辅助", "tier": "T0", "rating": 11, "element_cn": "物理", "style_cn": "支援"},
            {"tier_mode": "da", "character_slug": "sunna", "character_name_cn": "千夏", "role_group_cn": "辅助", "tier": "T0", "rating": 11, "element_cn": "物理", "style_cn": "支援"},
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
        ],
    )
    return out


def _write_box(tmp_path):
    box = tmp_path / "box.json"
    box.write_text(json.dumps({"owned": ["miyabi", "lucy"]}), encoding="utf-8")
    return box


def _write_plan(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "status": "current",
                        "characters": [
                            {"slug": "sunna", "name_cn": "千夏", "banner_role": "限定 S 级复刻", "analysis_tags": ["复刻", "辅助"]},
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


def _write_mechanism_notes(tmp_path):
    notes = tmp_path / "zzz_mechanism_notes"
    notes.mkdir()
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
