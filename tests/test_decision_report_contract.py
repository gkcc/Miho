from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re

import miho_core.evidence as evidence_module
import miho_core.pull_value as pull_value_module
import zzz_endgame_exporter.decision_report as decision_report_module
import zzz_endgame_exporter.cli as cli_module
from tests.test_pull_value import (
    _write_box,
    _write_decision_baseline,
    _write_mechanism_notes,
    _write_plan,
    _write_pull_fixture,
)
from zzz_endgame_exporter.cli import main


FIXTURES = Path(__file__).parent / "fixtures" / "decision_report_contract"
FIXED_NOW = "2026-07-12T13:14:15"
TIMESTAMP_PATTERN = re.compile(r"2026-07-12T13:14:15")


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 12, 13, 14, 15)
        return value if tz is None else value.replace(tzinfo=tz)


def test_python_cli_report_bundle_matches_frozen_contract(tmp_path, monkeypatch):
    _freeze_clock(monkeypatch)
    outputs, exit_codes = _build_python_oracles(tmp_path)
    actual = {
        "schema_version": 1,
        "oracle": (
            "complete deduped team/name/tier/usage inputs + explicit Box/banner plan/"
            "rules/mechanism notes/baseline -> Python ZZZ report CLI"
        ),
        "gating_scope": "bundle smoke only; decision/pull require dedicated adversarial matrices",
        "method_versions": {
            "evidence_coverage": "evidence-first-v1-20260712",
            "decision": "legacy-v0",
            "pull_value_review_packet": "evidence-first-v1-20260712",
        },
        "dynamic_fields": ["generated timestamp", "temporary fixture root"],
        "exit_codes": exit_codes,
        "canonical_sha256": {
            name: hashlib.sha256(_canonical_bytes(path, tmp_path)).hexdigest()
            for name, path in sorted(outputs.items())
        },
    }
    expected = json.loads((FIXTURES / "contract.json").read_text(encoding="utf-8"))
    if os.environ.get("MIHO_PRINT_DECISION_REPORT_CONTRACT") == "1":
        print(json.dumps(actual, ensure_ascii=False, indent=2))
    assert actual == expected


def test_contract_exercises_all_five_gated_commands():
    contract = json.loads((FIXTURES / "contract.json").read_text(encoding="utf-8"))
    assert contract["exit_codes"] == {
        "coverage": 0,
        "decision": 0,
        "evidence": 0,
        "pull-value": 0,
        "review-packet": 0,
    }
    assert set(contract["canonical_sha256"]) == {
        "coverage/current_box_team_coverage.md",
        "coverage/target_box_team_coverage.md",
        "coverage/team_signature_aggregates.csv",
        "decision/decision_cards.json",
        "decision/decision_report.md",
        "evidence/evidence_pool_summary.md",
        "pull-value/current_pull_value_report.md",
        "pull-value/next_pull_value_report.md",
        "review-packet/current_gpt_pull_reviewer_packet.md",
        "review-packet/next_gpt_pull_reviewer_packet.md",
    }


def _freeze_clock(monkeypatch) -> None:
    monkeypatch.setattr(evidence_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(pull_value_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(decision_report_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(cli_module, "datetime", _FixedDateTime)


def _build_python_oracles(root: Path) -> tuple[dict[str, Path], dict[str, int]]:
    report_root = root / "中文 空格 report oracle"
    report_root.mkdir()

    pull_case = report_root / "pull"
    pull_case.mkdir()
    pull_out = _write_pull_fixture(pull_case)
    pull_box = _write_box(pull_case)
    pull_plan = _write_plan(pull_case)
    _write_mechanism_notes(pull_case)
    baseline = _write_decision_baseline(pull_case)

    evidence_output = report_root / "evidence" / "evidence_pool_summary.md"
    evidence_output.parent.mkdir()
    evidence_exit = main(
        [
            "evidence",
            "--box",
            str(pull_box),
            "--out",
            str(pull_out),
            "--planned-slugs",
            "sunna,nom",
            "--min-a-app-rate",
            "sd=5;da=10",
            "--include-missing",
            "--output",
            str(evidence_output),
        ]
    )

    coverage_root = report_root / "coverage"
    coverage_root.mkdir()
    current_coverage = coverage_root / "current_box_team_coverage.md"
    target_coverage = coverage_root / "target_box_team_coverage.md"
    aggregate_csv = coverage_root / "team_signature_aggregates.csv"
    coverage_exit = main(
        [
            "coverage",
            "--box",
            str(pull_box),
            "--out",
            str(pull_out),
            "--plan",
            str(pull_plan),
            "--plan-status",
            "current;next",
            "--min-a-app-rate",
            "sd=5;da=10",
            "--current-output",
            str(current_coverage),
            "--target-output",
            str(target_coverage),
            "--aggregate-output",
            str(aggregate_csv),
        ]
    )

    decision_root = report_root / "decision"
    decision_root.mkdir()
    decision_box, rules = _write_decision_fixture(decision_root)
    decision_exit = main(
        [
            "decision",
            "--box",
            str(decision_box),
            "--out",
            str(decision_root),
            "--rules",
            str(rules),
        ]
    )

    pull_value_exit = main(
        [
            "pull-value",
            "--box",
            str(pull_box),
            "--out",
            str(pull_out),
            "--plan",
            str(pull_plan),
            "--mechanism-notes-dir",
            str(pull_case / "zzz_mechanism_notes"),
            "--decision-baseline",
            str(baseline),
        ]
    )
    review_exit = main(
        [
            "review-packet",
            "--box",
            str(pull_box),
            "--out",
            str(pull_out),
            "--plan",
            str(pull_plan),
            "--mechanism-notes-dir",
            str(pull_case / "zzz_mechanism_notes"),
            "--decision-baseline",
            str(baseline),
        ]
    )

    outputs = {
        "evidence/evidence_pool_summary.md": evidence_output,
        "coverage/current_box_team_coverage.md": current_coverage,
        "coverage/target_box_team_coverage.md": target_coverage,
        "coverage/team_signature_aggregates.csv": aggregate_csv,
        "decision/decision_cards.json": decision_root / "decision_cards.json",
        "decision/decision_report.md": decision_root / "decision_report.md",
        "pull-value/current_pull_value_report.md": pull_out / "current_pull_value_report.md",
        "pull-value/next_pull_value_report.md": pull_out / "next_pull_value_report.md",
        "review-packet/current_gpt_pull_reviewer_packet.md": pull_out
        / "current_gpt_pull_reviewer_packet.md",
        "review-packet/next_gpt_pull_reviewer_packet.md": pull_out
        / "next_gpt_pull_reviewer_packet.md",
    }
    assert all(path.is_file() for path in outputs.values())
    return outputs, {
        "evidence": evidence_exit,
        "coverage": coverage_exit,
        "decision": decision_exit,
        "pull-value": pull_value_exit,
        "review-packet": review_exit,
    }


def _write_decision_fixture(root: Path) -> tuple[Path, Path]:
    _write_csv(
        root / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn"],
        [
            {"character_slug": "zhao", "character_name_en": "Zhao", "character_name_cn": "照"},
            {
                "character_slug": "alice",
                "character_name_en": "Alice Thymefield",
                "character_name_cn": "爱丽丝·泰姆菲尔德",
            },
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
        root / "prydwen_tier_current.csv",
        tier_columns,
        [
            _tier("zhao", "照", "crit_dps", "直伤主C", "T0", 11, "Fire", "火", "Attack", "强攻"),
            _tier(
                "alice",
                "爱丽丝·泰姆菲尔德",
                "anomaly_dps",
                "异常主C",
                "T0.5",
                10,
                "Physical",
                "物理",
                "Anomaly",
                "异常",
            ),
            _tier("miyabi", "星见雅", "anomaly_dps", "异常主C", "T0.5", 10, "Ice", "冰", "Anomaly", "异常"),
        ],
    )
    _write_csv(
        root / "character_usage_long.csv",
        ["collect_date", "mode", "mode_cn", "sub_mode", "character_slug", "app_rate"],
        [
            {"collect_date": "2026-05-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "zhao", "app_rate": "15"},
            {"collect_date": "2026-06-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "zhao", "app_rate": "18"},
            {"collect_date": "2026-05-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "alice", "app_rate": "12"},
            {"collect_date": "2026-06-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "alice", "app_rate": "14"},
            {"collect_date": "2026-06-01", "mode": "sd", "mode_cn": "式舆防卫", "sub_mode": "all", "character_slug": "miyabi", "app_rate": "22"},
        ],
    )
    _write_csv(root / "team_rank_raw.csv", ["collect_date", "char_1_slug", "char_2_slug", "char_3_slug", "rank", "app_rate"], [])
    _write_csv(root / "prydwen_tier_changelog_history.csv", ["changelog_date", "character_slugs", "text"], [])
    box = root / "box.yaml"
    box.write_text(
        """agents:
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
    rules = root / "rules.yaml"
    rules.write_text(
        """candidate_min_rating: 10
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
    return box, rules


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


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _canonical_bytes(path: Path, root: Path) -> bytes:
    raw = path.read_bytes()
    if path.suffix == ".csv":
        return raw
    text = raw.decode("utf-8")
    for value in (str(root).replace("\\", "\\\\"), str(root), root.as_posix()):
        text = text.replace(value, "<FIXTURE_ROOT>")
    text = TIMESTAMP_PATTERN.sub("<GENERATED_AT>", text)
    return text.encode("utf-8")
