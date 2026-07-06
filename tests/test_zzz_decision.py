import csv
import json

from zzz_endgame_exporter.decision_report import run_decision_report


def test_zzz_decision_report_outputs_cards_and_report(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _write_csv(
        out / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn"],
        [
            {"character_slug": "zhao", "character_name_en": "Zhao", "character_name_cn": "照"},
            {"character_slug": "alice", "character_name_en": "Alice Thymefield", "character_name_cn": "爱丽丝·泰姆菲尔德"},
            {"character_slug": "miyabi", "character_name_en": "Miyabi", "character_name_cn": "星见雅"},
        ],
    )
    tier_columns = [
        "tier_mode",
        "tier_mode_cn",
        "character_slug",
        "character_name_en",
        "character_name_cn",
        "role_group",
        "role_group_cn",
        "tier",
        "rating",
        "element",
        "element_cn",
        "style",
        "style_cn",
        "rarity",
        "is_new",
    ]
    _write_csv(
        out / "prydwen_tier_current.csv",
        tier_columns,
        [
            _tier("zhao", "照", "crit_dps", "直伤主C", "T0", 11, "Fire", "火", "Attack", "强攻"),
            _tier("alice", "爱丽丝·泰姆菲尔德", "anomaly_dps", "异常主C", "T0.5", 10, "Physical", "物理", "Anomaly", "异常"),
            _tier("miyabi", "星见雅", "anomaly_dps", "异常主C", "T0.5", 10, "Ice", "冰", "Anomaly", "异常"),
        ],
    )
    usage_columns = ["collect_date", "mode", "mode_cn", "sub_mode", "character_slug", "app_rate"]
    _write_csv(
        out / "character_usage_long.csv",
        usage_columns,
        [
            {"collect_date": "2026-05-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "zhao", "app_rate": "15"},
            {"collect_date": "2026-06-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "zhao", "app_rate": "18"},
            {"collect_date": "2026-05-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "alice", "app_rate": "12"},
            {"collect_date": "2026-06-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "alice", "app_rate": "14"},
            {"collect_date": "2026-06-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "miyabi", "app_rate": "22"},
        ],
    )
    _write_csv(out / "team_rank_raw.csv", ["collect_date", "char_1_slug", "char_2_slug", "char_3_slug", "rank", "app_rate"], [])
    _write_csv(out / "prydwen_tier_changelog_history.csv", ["changelog_date", "character_slugs", "text"], [])

    box = tmp_path / "box.yaml"
    box.write_text(
        """
agents:
  - slug: miyabi
    name_cn: 星见雅
    owned: true
    cinema: 0
    signature: 1
    level: 60
    w_engine_level: 60
    core_skill: 7
""",
        encoding="utf-8",
    )
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        """
candidate_min_rating: 10
max_generated_candidates: 10
pull_rating: 10
skip_rating: 8
low_tier_warning_rating: 9
default_max_recommended_stage: 0+1
candidates:
  - slug: seed-agent
    name_cn: 卫星代理人
    banner_type: satellite
    role_group: support
""",
        encoding="utf-8",
    )

    result = run_decision_report(box, out, rules)
    cards = {card["slug"]: card for card in result["cards"]}

    assert (out / "decision_report.md").exists()
    assert (out / "decision_cards.json").exists()
    assert json.loads((out / "decision_cards.json").read_text(encoding="utf-8"))["summary"]["candidate_count"] == len(cards)
    assert cards["zhao"]["decision"] == "抽"
    assert cards["seed-agent"]["decision"] == "等实测"
    assert cards["seed-agent"]["release_risk"]["level"] == "高"
    assert cards["miyabi"]["decision"] == "停止加仓"
    assert cards["alice"]["decision"] == "不抽"
    assert cards["alice"]["replacement_risk"]["level"] == "高"


def _tier(slug, name_cn, role, role_cn, tier, rating, element, element_cn, style, style_cn):
    return {
        "tier_mode": "sd",
        "tier_mode_cn": "式舆防卫",
        "character_slug": slug,
        "character_name_en": slug.title(),
        "character_name_cn": name_cn,
        "role_group": role,
        "role_group_cn": role_cn,
        "tier": tier,
        "rating": rating,
        "element": element,
        "element_cn": element_cn,
        "style": style,
        "style_cn": style_cn,
        "rarity": "S",
        "is_new": "",
    }


def _write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
