from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "render_demo_dashboard.py"
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "run_demo_pipeline.py"
CLI_SCRIPT_PATH = PROJECT_ROOT / "tools" / "probes" / "miho_probe_cli.py"

dashboard_spec = importlib.util.spec_from_file_location("render_demo_dashboard", DASHBOARD_SCRIPT_PATH)
assert dashboard_spec is not None
dashboard_tool = importlib.util.module_from_spec(dashboard_spec)
assert dashboard_spec.loader is not None
sys.modules[dashboard_spec.name] = dashboard_tool
dashboard_spec.loader.exec_module(dashboard_tool)

pipeline_spec = importlib.util.spec_from_file_location("run_demo_pipeline", PIPELINE_SCRIPT_PATH)
assert pipeline_spec is not None
pipeline_tool = importlib.util.module_from_spec(pipeline_spec)
assert pipeline_spec.loader is not None
sys.modules[pipeline_spec.name] = pipeline_tool
pipeline_spec.loader.exec_module(pipeline_tool)

cli_spec = importlib.util.spec_from_file_location("miho_probe_cli", CLI_SCRIPT_PATH)
assert cli_spec is not None
cli_tool = importlib.util.module_from_spec(cli_spec)
assert cli_spec.loader is not None
sys.modules[cli_spec.name] = cli_tool
cli_spec.loader.exec_module(cli_tool)


def field(value, *, uncertain: bool = False, status: str = "ok") -> dict:
    if value is None:
        uncertain = True
        status = "missing"
    return {
        "value": value,
        "status": status,
        "uncertain": uncertain,
        "evidence": ["mock"],
        "source_region": "mock",
    }


def parsed_json(name: str = "星见雅", image: str = "figs/mock.jpg", atk: str = "200") -> dict:
    return {
        "metadata": {
            "input_image": image,
            "ocr_engine": "paddle",
            "game": "zzz",
            "layout": "zzz-agent-card",
        },
        "coverage_summary": {"coverage_level": "medium"},
        "extracted_draft": {
            "game": "zzz",
            "source_type": "official_export_image",
            "character": {
                "name": field(name, uncertain=True, status="uncertain"),
                "level": field("60"),
                "rank": field("S"),
            },
            "stats": {
                "hp": field("100"),
                "atk": field(atk),
                "def": field("300"),
                "impact": field("90"),
                "crit_rate": field("10%"),
                "crit_dmg": field("50%"),
                "anomaly_mastery": field("100"),
                "anomaly_proficiency": field("120"),
                "pen": field("0"),
                "energy_regen": field("1.2"),
                "physical_dmg_bonus": field("30%"),
            },
            "skill_levels": [{"slot": slot, "level": field(str(slot))} for slot in range(1, 7)],
            "equipment": {"name": field("幻变魔方"), "level": field("60"), "rank": field("A")},
            "drive_discs": [
                {
                    "slot": slot,
                    "set_name": field(f"套装{slot}"),
                    "level": field("15"),
                    "main_stat": field("暴击率 24%"),
                    "sub_stats": field(
                        [{"stat": "攻击力", "value": "19", "enhancement": None, "uncertain": False, "evidence": ["攻击力", "19"]}]
                    ),
                }
                for slot in range(1, 7)
            ],
        },
    }


def targets_json() -> dict:
    return {
        "game": "zzz",
        "source": {"type": "manual", "note": "unit test fixture"},
        "default_minimums": {
            "character_level": 60,
            "equipment_level": 60,
            "skill_level": 8,
            "drive_disc_level": 12,
            "stats": {"atk": 250, "crit_rate": 20},
        },
        "targets": [
            {
                "goal_id": "zzz_mock_crisis",
                "activity_name": "危局强袭战",
                "target_tier": "稳定通关",
                "priority": "high",
                "preferred_characters": ["星见雅"],
                "minimums": {"skill_level": 8},
            }
        ],
    }


def tier_snapshot_json() -> dict:
    return {
        "source": {
            "name": "unit test tier snapshot",
            "source_type": "manual",
            "source_ref": "local",
            "period": "2026-06",
            "captured_at": "2026-06-29T00:00:00+08:00",
            "content_sha256": "a" * 64,
            "trust_level": "high",
        },
        "entries": [
            {
                "character": "星见雅",
                "tier": "S",
                "retention_score": 0.9,
                "usage_rate": "40%",
                "trend": "stable",
                "modes": ["危局强袭战"],
                "value_tags": ["high_retention"],
            },
            {
                "character": "珂蕾妲",
                "tier": "A",
                "retention_score": 0.74,
                "trend": "unknown",
                "modes": ["式舆防卫战"],
            },
        ],
    }


class DemoDashboardTests(unittest.TestCase):
    def test_dashboard_shows_final_brief_before_details(self) -> None:
        summary = {
            "overall": {
                "case_count": 0,
                "parse_success_count": 0,
                "review_status_counts": {},
                "parse_status_counts": {},
                "expected_status_counts": {},
                "normalized_status_counts": {},
                "import_status_counts": {},
                "demo_status": "READY",
                "average_pass_rate": None,
                "normalized_count": 0,
                "requires_manual_review_count": 0,
                "conclusion": "demo",
            },
            "input": {"source_mode": "manifest controlled mode"},
            "cases": [],
            "final_brief": {
                "schema_version": "p2.1-lite-final-brief",
                "brief_status": "ready",
                "output_json": "data/probes/demo/final_brief/final_brief.json",
                "output_md": "data/probes/demo/final_brief/final_brief.md",
                "summary": {
                    "trusted_plan_count": 1,
                    "pending_review_count": 0,
                    "ready_now_target_count": 1,
                    "needs_recording_target_count": 0,
                    "watch_only_target_count": 0,
                },
                "top_cards": [
                    {
                        "rank": 1,
                        "card_type": "try_now",
                        "title": "可先尝试：危局强袭战",
                        "reason": "全员来自 accepted roster。",
                        "target": "危局强袭战",
                        "character": "星见雅、苍角",
                        "evidence": {"source": "local", "hash": "abcdef123456", "artifact": "data/probes/demo/endgame_plan/endgame_plan.json"},
                        "command_hint": "打开 Dashboard 的本期高难方案。",
                        "warnings": [],
                    }
                ],
                "warnings": [],
            },
            "action_checklist": {
                "schema_version": "p2.2-lite-action-checklist",
                "checklist_status": "ready",
                "output_json": "data/probes/demo/action_checklist/action_checklist.json",
                "output_md": "data/probes/demo/action_checklist/action_checklist.md",
                "review_decisions_template": "data/probes/demo/action_checklist/review_decisions_template.json",
                "summary": {"item_count": 1, "ready_count": 1, "needs_review_count": 0, "blocked_count": 0, "hidden_item_count": 0},
                "items": [
                    {
                        "rank": 1,
                        "item_type": "try_now",
                        "status": "ready",
                        "title": "可先尝试：危局强袭战",
                        "target": "危局强袭战",
                        "character": "星见雅、苍角",
                        "evidence": {"artifact": "data/probes/demo/endgame_plan/endgame_plan.json", "target_hash": "abcdef123456"},
                        "command_hint": "打开 Dashboard 的本期高难方案。",
                        "warnings": [],
                    }
                ],
                "warnings": [],
            },
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("今日作战简报", html)
        self.assertIn("执行清单", html)
        self.assertIn("今天先做什么", html)
        self.assertIn("final_brief.md", html)
        self.assertIn("review_decisions_template.json", html)
        self.assertIn("可先尝试：危局强袭战", html)
        self.assertLess(html.index("今日作战简报"), html.index("输入模式"))
        self.assertLess(html.index("今日作战简报"), html.index("执行清单"))
        self.assertLess(html.index("执行清单"), html.index("输入模式"))

    def test_dashboard_html_contains_case_links_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "index.html"
            summary = {
                "overall": {
                    "case_count": 1,
                    "parse_success_count": 1,
                    "review_status_counts": {"NEEDS_REVIEW": 1},
                    "parse_status_counts": {"PASS": 1},
                    "expected_status_counts": {"N/A": 1},
                    "normalized_status_counts": {"GENERATED": 1},
                    "import_status_counts": {"REQUIRES_REVIEW": 1},
                    "demo_status": "MISSING_EXPECTED",
                    "average_pass_rate": None,
                    "normalized_count": 1,
                    "requires_manual_review_count": 1,
                    "conclusion": "demo",
                },
                "input": {
                    "source_mode": "parsed replay mode",
                    "images_dir": None,
                    "parsed_dir": "data/probes/parsed",
                    "manifest": None,
                    "latest_only": False,
                    "clean_demo": False,
                    "target_source_manifest": str(root / "target_sources.json"),
                    "history_dir": str(root / "snapshot_history"),
                    "roster_dir": str(root / "roster"),
                    "tier_snapshot": str(root / "tier_snapshot.json"),
                },
                "warnings": ["当前包含历史 parsed 结果，平均通过率不代表 P0.9 replay batch"],
                "training_plan": {
                    "targets_json": str(root / "targets.json"),
                    "output_json": str(root / "training_priority_report.json"),
                    "output_md": str(root / "training_priority_report.md"),
                    "plan_item_count": 1,
                    "top_plan_items": [
                        {
                            "priority_rank": 1,
                            "character": "星见雅",
                            "target": "危局强袭战 稳定通关",
                            "action": "先人工确认解析结果",
                            "reason": "mock reason",
                            "estimated_days": 0.0,
                            "confidence": "high",
                        }
                    ],
                    "warnings": ["终局目标来自本地配置或 mock"],
                    "target_source_status": {
                        "status": "local_draft",
                        "freshness_level": "unknown",
                        "current_endgame_ready": False,
                        "planning_confidence": "low",
                    },
                    "target_coverage": [
                        {
                            "target": "危局强袭战 稳定通关",
                            "coverage_status": "covered",
                            "match_count": 1,
                            "matched_characters": [{"character": "星见雅", "match_type": "tag_overlap", "score": 65}],
                            "catalog_candidates": [],
                            "evidence": {
                                "source_ref": str(root / "target_source.html"),
                                "content_sha256_short": "abcdef123456",
                                "title": "危局强袭战 本期目标",
                            },
                        },
                        {
                            "target": "式舆防卫战 满星尝试",
                            "coverage_status": "unmatched",
                            "match_count": 0,
                            "matched_characters": [],
                            "catalog_candidates": [{"character": "珂蕾妲", "matched_tags": ["fire", "stun"], "score": 60}],
                        }
                    ],
                    "coverage_gap_actions": [
                        {
                            "rank": 1,
                            "target": "式舆防卫战 满星尝试",
                            "character": "珂蕾妲",
                            "action": "先确认是否拥有，拥有后补录官方分享图",
                            "confidence": "low",
                            "uses_stamina": False,
                        }
                    ],
                    "resource_plan": {
                        "budget": {"daily_stamina": 240.0, "horizon_days": 7, "total_stamina": 1680.0},
                        "today": [
                            {
                                "rank": 1,
                                "character": "星见雅",
                                "action": "补关键技能到 8 左右",
                                "allocated_stamina": 120.0,
                            }
                        ],
                        "remaining_stamina": 1560.0,
                    },
                    "error": None,
                },
                "action_cards": {
                    "output_json": str(root / "action_cards.json"),
                    "output_md": str(root / "action_cards.md"),
                    "summary": {
                        "owned_character_count": 0,
                        "pending_snapshot_count": 1,
                        "snapshot_file_count": 1,
                        "target_count": 2,
                        "covered_target_count": 1,
                        "uncovered_target_count": 1,
                        "needs_recording_count": 2,
                        "high_priority_action_count": 1,
                        "tier_signal_count": 1,
                        "high_value_owned_action_count": 0,
                        "low_value_action_count": 0,
                        "low_value_review_count": 0,
                    },
                    "warnings": ["pending snapshot 和 catalog candidate 都不代表可用练度；只有 accepted roster 才算已确认拥有练度。"],
                    "cards": [
                        {
                            "rank": 1,
                            "action_type": "review_pending_snapshot",
                            "priority": "high",
                            "title": "复核 星见雅 的解析快照",
                            "character": "星见雅",
                            "target": "危局强袭战 稳定通关",
                            "reason": "该角色只有 demo normalized snapshot，尚未进入 accepted roster。原动作：补关键技能到 8 左右。",
                            "source_class": "pending_snapshot",
                            "status": "needs_review",
                            "tier_signal": {
                                "recommendation": "watch_candidate",
                                "tier": "S",
                                "tier_score": 90,
                                "retention_score": 0.9,
                                "trend": "stable",
                            },
                            "evidence": {
                                "target_source": str(root / "target_source.html"),
                                "target_hash": "abcdef123456",
                                "snapshot_source": str(root / "case.jpg"),
                            },
                            "links": {},
                        },
                        {
                            "rank": 2,
                            "action_type": "review_candidate",
                            "priority": "medium",
                            "title": "确认是否拥有 珂蕾妲",
                            "character": "珂蕾妲",
                            "target": "式舆防卫战 满星尝试",
                            "reason": "catalog 候选命中目标缺口。",
                            "source_class": "catalog_candidate",
                            "status": "needs_review",
                            "evidence": {"target_hash": "222222222222"},
                            "links": {},
                        },
                    ],
                    "error": None,
                },
                "team_cards": {
                    "output_json": str(root / "team_cards.json"),
                    "output_md": str(root / "team_cards.md"),
                    "summary": {
                        "target_count": 2,
                        "team_card_count": 2,
                        "playable_now_count": 0,
                        "needs_recording_count": 0,
                        "catalog_candidate_count": 1,
                        "pending_snapshot_count": 1,
                        "accepted_high_value_member_count": 0,
                        "high_value_playable_team_count": 0,
                        "stale_meta_count": 0,
                        "unverified_meta_count": 0,
                    },
                    "warnings": ["队伍候选基于 accepted roster、本地快照和本地 catalog；catalog candidate 不代表已拥有。"],
                    "cards": [
                        {
                            "rank": 1,
                            "target": "危局强袭战 稳定通关",
                            "target_priority": "high",
                            "team_status": "needs_review",
                            "team_title": "待确认快照队伍: 危局强袭战 稳定通关",
                            "coverage_reason": "星见雅 已有本地 normalized snapshot，但尚未进入 accepted roster。",
                            "team_value": {
                                "accepted_high_value_members": 0,
                                "accepted_low_value_members": 0,
                                "stale_meta_count": 0,
                                "unverified_meta_count": 0,
                                "weak_meta_count": 0,
                                "ranking_reason": "没有 verified 高保值 tier 信号。",
                            },
                            "members": [
                                {
                                    "slot": "core",
                                    "character": "星见雅",
                                    "source_class": "pending_snapshot",
                                    "snapshot_json": str(root / "case_normalized.json"),
                                    "confidence": "medium",
                                    "tier_signal": {
                                        "tier": "S",
                                        "observation_status": "non_owned_watch_only",
                                        "entry_status": "verified",
                                        "period": "2026-06",
                                        "content_sha256_short": "aaaaaaaaaaaa",
                                    },
                                }
                            ],
                            "evidence": {
                                "target_source": str(root / "target_source.html"),
                                "target_hash": "abcdef123456",
                            },
                            "warnings": ["pending snapshot 尚未进入 accepted roster，不能视为可出战练度。"],
                        },
                        {
                            "rank": 2,
                            "target": "式舆防卫战 满星尝试",
                            "target_priority": "high",
                            "team_status": "needs_candidate_confirmation",
                            "team_title": "待确认队伍候选: 式舆防卫战 满星尝试",
                            "coverage_reason": "珂蕾妲 仍是 catalog 候选，先确认拥有状态。",
                            "team_value": {
                                "accepted_high_value_members": 0,
                                "accepted_low_value_members": 0,
                                "stale_meta_count": 0,
                                "unverified_meta_count": 0,
                                "weak_meta_count": 0,
                                "ranking_reason": "没有 verified 高保值 tier 信号。",
                            },
                            "members": [
                                {
                                    "slot": "core",
                                    "character": "珂蕾妲",
                                    "source_class": "catalog_candidate",
                                    "snapshot_json": None,
                                    "confidence": "low",
                                }
                            ],
                            "evidence": {"target_hash": "222222222222"},
                            "warnings": ["catalog candidate 不代表已拥有；需要人工确认或补录官方分享图。"],
                        },
                    ],
                    "error": None,
                },
                "tier_watchlist": {
                    "schema_version": "p1.5-lite-tier-watchlist",
                    "output_json": str(root / "tier_watchlist.json"),
                    "output_md": str(root / "tier_watchlist.md"),
                    "summary": {
                        "entry_count": 2,
                        "accepted_roster_count": 1,
                        "candidate_count": 1,
                        "owned_high_value_count": 1,
                        "watch_candidate_count": 1,
                        "low_value_owned_count": 0,
                        "verified_entry_count": 2,
                        "stale_entry_count": 0,
                        "unverified_entry_count": 0,
                        "source_name": "unit test tier snapshot",
                        "source_type": "manual",
                    },
                    "warnings": ["tier watchlist 只读取本地 snapshot；它不是联网爬取，也不是最终抽取建议。"],
                    "entries": [
                        {
                            "character": "星见雅",
                            "owned_status": "accepted_roster",
                            "tier": "S",
                            "tier_score": 90,
                            "retention_score": 0.9,
                            "usage_rate": 0.4,
                            "trend": "stable",
                            "modes": ["危局强袭战"],
                            "observation_status": "owned_high_value",
                            "recommendation": "protect_investment",
                            "entry_status": "verified",
                            "evidence": {
                                "period": "2026-06",
                                "content_sha256_short": "aaaaaaaaaaaa",
                            },
                            "reason": "已在 accepted roster 中，且 tier/保值信号较强；后续培养和配队建议应优先保护这类投入。",
                        },
                        {
                            "character": "耀嘉音",
                            "owned_status": "not_in_roster",
                            "tier": "S+",
                            "tier_score": 92,
                            "retention_score": 0.88,
                            "usage_rate": None,
                            "trend": "up",
                            "modes": ["式舆防卫战"],
                            "observation_status": "non_owned_watch_only",
                            "recommendation": "watch_candidate",
                            "entry_status": "verified",
                            "evidence": {
                                "period": "2026-06",
                                "content_sha256_short": "aaaaaaaaaaaa",
                            },
                            "reason": "未在 accepted roster 中，但 tier/保值信号较强；这里只做观察候选，不直接生成抽取建议。",
                        },
                    ],
                    "error": None,
                },
                "roster_delta": {
                    "schema_version": "p1.8-lite-roster-delta",
                    "output_json": str(root / "roster_delta.json"),
                    "output_md": str(root / "roster_delta.md"),
                    "summary": {
                        "new_character_count": 0,
                        "updated_character_count": 1,
                        "removed_character_count": 0,
                        "unchanged_character_count": 0,
                        "team_impact_count": 1,
                        "tier_impact_count": 1,
                    },
                    "warnings": [
                        "roster_delta 只基于 accepted roster 的当前 roster_index；pending snapshot、rejected snapshot 和 catalog candidate 不参与已拥有 box 变化。"
                    ],
                    "character_changes": [
                        {
                            "character": "星见雅",
                            "change_type": "updated",
                            "old_snapshot_json": str(root / "accepted" / "miyabi_old.json"),
                            "new_snapshot_json": str(root / "accepted" / "miyabi_new.json"),
                            "field_changes": [{"field": "level", "old": "50", "new": "60"}],
                            "impacted_targets": ["危局强袭战 稳定通关"],
                            "impacted_teams": [
                                {
                                    "target": "危局强袭战 稳定通关",
                                    "team_title": "星见雅 核心队",
                                    "team_status": "playable_now",
                                    "source_class": "owned_snapshot",
                                }
                            ],
                            "tier_observation": {
                                "tier": "S",
                                "status": "verified",
                                "trend": "stable",
                                "retention_score": 0.9,
                            },
                            "warnings": ["该角色有 superseded accepted snapshot；delta 只比较 roster_index 当前保留版本。"],
                        }
                    ],
                    "error": None,
                },
                "run_manifest": {
                    "schema_version": "p2.0-lite-run-manifest",
                    "run_id": "demo_test_run",
                    "created_at": "2026-06-29T00:00:00+08:00",
                    "output_json": str(root / "run_manifest.json"),
                    "inputs": {
                        "roster_index": {"path": str(root / "roster_index.json"), "sha256": "a" * 64, "exists": True},
                        "targets": {"path": str(root / "targets.json"), "sha256": "b" * 64, "exists": True},
                        "team_cards": {"path": str(root / "team_cards.json"), "sha256": "c" * 64, "exists": True},
                        "action_cards": {"path": str(root / "action_cards.json"), "sha256": "d" * 64, "exists": True},
                        "tier_watchlist": {"path": str(root / "tier_watchlist.json"), "sha256": "e" * 64, "exists": True},
                        "roster_delta": {"path": str(root / "roster_delta.json"), "sha256": "f" * 64, "exists": True},
                    },
                    "artifact_status": {
                        "consistent": True,
                        "missing": [],
                        "stale_or_mismatched": [],
                        "warnings": [],
                    },
                },
                "endgame_plan": {
                    "schema_version": "p2.0-lite-endgame-plan",
                    "output_json": str(root / "endgame_plan.json"),
                    "output_md": str(root / "endgame_plan.md"),
                    "plan_trust_level": "warning",
                    "summary": {
                        "target_count": 4,
                        "ready_now_count": 1,
                        "needs_review_count": 1,
                        "needs_recording_count": 1,
                        "watch_only_count": 1,
                        "blocked_count": 0,
                        "trusted_plan_count": 1,
                        "warning_plan_count": 3,
                        "blocked_plan_count": 0,
                        "stale_or_unverified_count": 1,
                        "artifact_consistent": True,
                        "artifact_warning_count": 0,
                    },
                    "artifact_status": {
                        "consistent": True,
                        "missing": [],
                        "stale_or_mismatched": [],
                        "warnings": [],
                    },
                    "warnings": ["本期高难方案只聚合本地 accepted roster；不是抽卡建议。"],
                    "target_plans": [
                        {
                            "target": "危局强袭战 稳定通关",
                            "target_priority": "high",
                            "plan_status": "ready_now",
                            "source_plan_status": "ready_now",
                            "plan_trust_level": "trusted",
                            "recommended_line": "可先尝试：星见雅 核心队。",
                            "team_candidates": [
                                {
                                    "team_title": "星见雅 核心队",
                                    "team_status": "ready_now",
                                    "rank_reason": "全员来自 accepted roster，可作为本期高难候选。1 名成员有 verified 高保值本地证据。",
                                    "verified_high_value_member_count": 1,
                                    "weak_tier_count": 0,
                                    "members": [
                                        {
                                            "character": "星见雅",
                                            "source_class": "owned_snapshot",
                                            "source_class_effective": "owned_snapshot",
                                            "tier": "S",
                                            "retention_score": 0.9,
                                            "tier_entry_status": "verified",
                                            "delta_change_type": "updated",
                                        }
                                    ],
                                    "warnings": [],
                                }
                            ],
                            "next_actions": [],
                            "evidence": {
                                "target_source": str(root / "target_source.html"),
                                "target_hash": "abcdef123456",
                                "input_artifact_hashes": {
                                    "team_cards": {"path": str(root / "team_cards.json"), "sha256_short": "111111111111"}
                                },
                            },
                            "warnings": [],
                        },
                        {
                            "target": "待确认目标",
                            "target_priority": "high",
                            "plan_status": "needs_review",
                            "source_plan_status": "needs_review",
                            "plan_trust_level": "warning",
                            "recommended_line": "先复核 pending snapshot，确认后再作为可出战练度。",
                            "team_candidates": [
                                {
                                    "team_title": "待确认快照队",
                                    "team_status": "needs_review",
                                    "rank_reason": "包含 pending snapshot，需要先人工复核解析快照。",
                                    "members": [
                                        {
                                            "character": "莱特",
                                            "source_class": "pending_snapshot",
                                            "source_class_effective": "pending_snapshot",
                                            "tier": None,
                                            "retention_score": None,
                                            "tier_entry_status": "missing",
                                            "delta_change_type": "missing",
                                        }
                                    ],
                                    "warnings": ["莱特 仍是 pending snapshot，不能当作 ready_now 战力。"],
                                }
                            ],
                            "next_actions": [{"action_type": "review_pending_snapshot", "title": "复核 莱特 的解析快照"}],
                            "evidence": {"target_source": None, "target_hash": None, "input_artifact_hashes": {}},
                            "warnings": [],
                        },
                        {
                            "target": "补录目标",
                            "target_priority": "medium",
                            "plan_status": "needs_recording",
                            "source_plan_status": "needs_recording",
                            "plan_trust_level": "warning",
                            "recommended_line": "先补录官方分享图，避免只凭 catalog 拿来排队。",
                            "team_candidates": [],
                            "next_actions": [{"action_type": "record_missing_character", "title": "补录 珂蕾妲 的官方分享图"}],
                            "evidence": {"input_artifact_hashes": {}},
                            "warnings": [],
                        },
                        {
                            "target": "观察目标",
                            "target_priority": "low",
                            "plan_status": "watch_only",
                            "source_plan_status": "watch_only",
                            "plan_trust_level": "warning",
                            "recommended_line": "仅观察候选或确认拥有状态；这里不生成抽卡建议。",
                            "team_candidates": [],
                            "next_actions": [],
                            "evidence": {"input_artifact_hashes": {}},
                            "warnings": ["watch_only 不是抽卡建议；catalog candidate 不能当作已拥有战力。"],
                        },
                    ],
                    "error": None,
                },
                "pipeline_steps": [
                    {"name": "Normalized Snapshot", "status": "GENERATED"},
                    {"name": "Manual Review Gate", "status": "REQUIRES_REVIEW"},
                    {"name": "Action Cards", "status": "done"},
                    {"name": "Review Inbox", "status": "done"},
                    {"name": "Tier Watchlist", "status": "done"},
                    {"name": "Team Cards", "status": "done"},
                    {"name": "Roster Delta", "status": "done"},
                    {"name": "Run Manifest", "status": "done"},
                    {"name": "Endgame Plan", "status": "done"},
                ],
                "target_refresh": {
                    "manifest": str(root / "target_sources.json"),
                    "output_json": str(root / "targets" / "endgame_targets.json"),
                    "source_count": 1,
                    "target_count": 1,
                    "warnings": ["目标来源不是 official_current / official_snapshot"],
                    "error": None,
                    "source_type": "public_web_snapshot",
                    "game": "zzz",
                    "freshness": {"level": "fresh", "stale_source_count": 0, "max_source_age_hours": 168},
                },
                "snapshot_history": {
                    "history_dir": str(root / "snapshot_history"),
                    "index_json": str(root / "snapshot_history" / "index.json"),
                    "snapshot_count": 1,
                    "diff_count": 1,
                    "changed_character_count": 1,
                    "no_previous_count": 0,
                    "diff_failed_count": 0,
                    "items": [
                        {
                            "character": "星见雅",
                            "case_name": "case_a",
                            "current_snapshot": str(root / "snapshot_history" / "current.json"),
                            "previous_snapshot": str(root / "snapshot_history" / "previous.json"),
                            "diff_md": str(root / "snapshot_history" / "diff.md"),
                            "change_count": 2,
                            "requires_review_change_count": 0,
                            "status": "diffed",
                        }
                    ],
                },
                "cases": [
                    {
                        "name": "case_a",
                        "image": None,
                        "review_html": str(root / "case_review.html"),
                        "parsed_json": str(root / "case.json"),
                        "normalized_md": str(root / "case_normalized.md"),
                        "normalized_json": str(root / "case_normalized.json"),
                        "expected_json": str(root / "case_expected.json"),
                        "expected_json_name": "case_expected.json",
                        "expected_diff_md": None,
                        "review_status": "NEEDS_REVIEW",
                        "coverage_level": "medium",
                        "pass_rate": None,
                        "parse_status": "PASS",
                        "expected_status": "N/A",
                        "normalized_status": "GENERATED",
                        "import_status": "REQUIRES_REVIEW",
                        "import_blockers": [],
                        "character": {"name": "星见雅", "level": "60", "rank": "S"},
                        "equipment": {"name": "幻变魔方"},
                        "quality": {
                            "trusted_field_count": 10,
                            "field_count": 12,
                            "requires_manual_review": True,
                            "blockers": ["character.name 缺失或 uncertain"],
                        },
                        "errors": [],
                    }
                ],
                "review_inbox": {
                    "schema_version": "p1.4-lite-review-inbox",
                    "roster_dir": str(root / "roster"),
                    "roster_index_json": None,
                    "accepted_count": 0,
                    "rejected_count": 0,
                    "pending_count": 1,
                    "needs_manual_review_count": 1,
                    "pending": [
                        {
                            "character": "星见雅",
                            "level": "60",
                            "equipment": "幻变魔方",
                            "trusted_field_count": 10,
                            "field_count": 12,
                            "blockers": ["character.name 缺失或 uncertain"],
                            "normalized_json": str(root / "case_normalized.json"),
                            "review_html": str(root / "case_review.html"),
                        }
                    ],
                    "accepted": [],
                    "rejected": [],
                    "decision_command": "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized --decision-manifest data/probes/review_decisions.json --roster-dir data/probes/roster",
                },
            }

            dashboard_tool.render_dashboard(summary, output)
            html = output.read_text(encoding="utf-8")

            self.assertIn("Miho 本地练度识别体验台", html)
            self.assertIn("parsed replay mode", html)
            self.assertIn("case_a", html)
            self.assertIn("星见雅", html)
            self.assertIn("normalized_json", html)
            self.assertIn("review_html", html)
            self.assertIn("case_expected.json", html)
            self.assertIn("Demo 状态", html)
            self.assertIn("MISSING_EXPECTED", html)
            self.assertIn("Parse PASS", html)
            self.assertIn("Expected N/A", html)
            self.assertIn("Normalized Snapshot", html)
            self.assertIn("GENERATED", html)
            self.assertIn("Manual Review Gate", html)
            self.assertIn("REQUIRES_REVIEW", html)
            self.assertIn("requires_review 不代表解析失败", html)
            self.assertIn("下一步行动", html)
            self.assertIn("候选 ≠ 已拥有", html)
            self.assertIn("高优先级行动", html)
            self.assertIn("需补录/确认", html)
            self.assertIn("tier signal", html)
            self.assertIn("高保值行动", html)
            self.assertIn("低保值复核", html)
            self.assertIn("练度更新收件箱", html)
            self.assertIn("只有 accepted roster 可以作为已拥有练度", html)
            self.assertIn("待确认快照", html)
            self.assertIn("已接收快照", html)
            self.assertIn("apply_review_decisions.py", html)
            self.assertIn("tier_snapshot", html)
            self.assertIn("Tier / 保值观察", html)
            self.assertIn("已有高保值", html)
            self.assertIn("Tier 观察候选", html)
            self.assertIn("verified", html)
            self.assertIn("stale tier", html)
            self.assertIn("unverified tier", html)
            self.assertIn("tier_watchlist.json", html)
            self.assertIn("owned_high_value", html)
            self.assertIn("non_owned_watch_only", html)
            self.assertIn("不是最终抽取建议", html)
            self.assertIn("action_cards.json", html)
            self.assertIn("确认是否拥有 珂蕾妲", html)
            self.assertIn("高难配队候选", html)
            self.assertIn("可用队伍", html)
            self.assertIn("高保值可用队伍", html)
            self.assertIn("team value", html)
            self.assertIn("需补录队伍", html)
            self.assertIn("候选队伍", html)
            self.assertIn("team_cards.json", html)
            self.assertIn("pending_snapshot", html)
            self.assertIn("catalog_candidate", html)
            self.assertIn("pending snapshot 尚未进入 accepted roster", html)
            self.assertIn("catalog candidate 不代表已拥有", html)
            self.assertIn("本次练度更新影响", html)
            self.assertIn("roster_delta.json", html)
            self.assertIn("delta 只基于 accepted roster", html)
            self.assertIn("更新角色", html)
            self.assertIn("Tier 命中", html)
            self.assertIn("运行一致性", html)
            self.assertIn("run_manifest.json", html)
            self.assertIn("输入产物 hash", html)
            self.assertIn("demo_test_run", html)
            self.assertIn("方案 Trust", html)
            self.assertIn("本期高难方案", html)
            self.assertIn("endgame_plan.json", html)
            self.assertIn("不是抽卡建议", html)
            self.assertIn("可直接尝试", html)
            self.assertIn("先复核", html)
            self.assertIn("需补录", html)
            self.assertIn("仅观察", html)
            self.assertIn("ready_now", html)
            self.assertIn("needs_review", html)
            self.assertIn("needs_recording", html)
            self.assertIn("watch_only", html)
            self.assertIn("trusted", html)
            self.assertIn("source_status", html)
            self.assertIn("owned_snapshot-&gt;owned_snapshot", html)
            self.assertIn("review_pending_snapshot", html)
            self.assertIn("培养优先级候选", html)
            self.assertIn("source status", html)
            self.assertIn("local_draft", html)
            self.assertIn("目标覆盖", html)
            self.assertIn("covered", html)
            self.assertIn("abcdef123456", html)
            self.assertIn("候选：珂蕾妲", html)
            self.assertIn("长期补洞候选", html)
            self.assertIn("先确认是否拥有", html)
            self.assertIn("今日投入建议", html)
            self.assertIn("终局目标刷新", html)
            self.assertIn("endgame_targets.json", html)
            self.assertIn("fresh", html)
            self.assertIn("快照历史", html)
            self.assertIn("snapshot_diff_md", html)
            self.assertIn("先人工确认解析结果", html)
            self.assertIn("training_priority_report.json", html)
            self.assertIn("当前包含历史 parsed 结果", html)
            self.assertIn("character.name 缺失或 uncertain", html)
            self.assertIn("N/A", html)

    def test_run_demo_pipeline_parsed_dir_does_not_run_ocr_and_renders_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            parsed_dir.mkdir()
            parsed_path = parsed_dir / "case_a.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False), encoding="utf-8")
            parsed_path.with_name("case_a_review.html").write_text("<html>review</html>", encoding="utf-8")

            original_subprocess_run = pipeline_tool.subprocess.run

            def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("parsed-dir mode must not run OCR review subprocess")

            pipeline_tool.subprocess.run = fail_if_called
            try:
                summary = pipeline_tool.run_pipeline(
                    images_dir=None,
                    parsed_dir=parsed_dir,
                    manifest=None,
                    output_dir=output_dir,
                    roster_dir=root / "roster",
                    open_dashboard=False,
                )
            finally:
                pipeline_tool.subprocess.run = original_subprocess_run

            self.assertEqual(summary["overall"]["case_count"], 1)
            self.assertEqual(summary["overall"]["average_pass_rate"], None)
            self.assertEqual(summary["input"]["source_mode"], "parsed replay mode")
            self.assertEqual(summary["input"]["parsed_dir_discovered_count"], 1)
            self.assertEqual(summary["input"]["parsed_dir_selected_count"], 1)
            self.assertIn("parsed-dir 模式会扫描历史 parsed JSON", summary["warnings"][0])
            self.assertNotIn("action_cards", summary)
            self.assertNotIn("team_cards", summary)
            self.assertEqual(summary["review_inbox"]["pending_count"], 1)
            self.assertEqual(summary["snapshot_history"]["snapshot_count"], 1)
            self.assertEqual(summary["snapshot_history"]["no_previous_count"], 1)
            self.assertEqual(summary["cases"][0]["parse_status"], "PASS")
            self.assertEqual(summary["cases"][0]["expected_status"], "N/A")
            self.assertEqual(summary["cases"][0]["normalized_status"], "GENERATED")
            self.assertEqual(summary["cases"][0]["import_status"], "REQUIRES_REVIEW")
            self.assertNotIn("action_cards", summary)
            steps = {item["name"]: item["status"] for item in summary["pipeline_steps"]}
            self.assertEqual(steps["Normalized Snapshot"], "GENERATED")
            self.assertEqual(steps["Manual Review Gate"], "REQUIRES_REVIEW")
            self.assertEqual(steps["Review Inbox"], "done")
            self.assertTrue(Path(summary["dashboard_html"]).exists())
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")
            self.assertIn("parsed found", dashboard_html)
            self.assertIn("parsed used", dashboard_html)
            self.assertIn("requires_review 不代表解析失败", dashboard_html)
            self.assertIn("练度更新收件箱", dashboard_html)
            self.assertTrue(Path(summary["cases"][0]["normalized_json"]).exists())
            self.assertEqual(summary["cases"][0]["review_html"], str(parsed_path.with_name("case_a_review.html").resolve()))

    def test_run_demo_pipeline_marks_review_fail_as_parse_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case = pipeline_tool.case_template("bad_case")
            case["parsed_json"] = str(root / "bad_case.json")
            case["review_status"] = "FAIL"
            summary = pipeline_tool.summarize(
                [case],
                root,
                {"source_mode": "OCR fresh image mode", "images_dir": str(root / "figs")},
            )

            self.assertEqual(summary["cases"][0]["parse_status"], "FAIL")
            self.assertEqual(summary["cases"][0]["normalized_status"], "FAILED")
            self.assertEqual(summary["cases"][0]["import_status"], "BLOCKED")
            self.assertEqual(summary["overall"]["demo_status"], "HAS_PARSE_FAILURE")
            steps = {item["name"]: item["status"] for item in summary["pipeline_steps"]}
            self.assertEqual(steps["OCR Review"], "FAIL")
            self.assertEqual(steps["Manual Review Gate"], "BLOCKED")

    def test_run_demo_pipeline_latest_only_keeps_newest_parsed_per_source_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            parsed_dir.mkdir()
            older = parsed_dir / "shared_parsed_20260627_100000.json"
            newer = parsed_dir / "shared_parsed_20260628_100000.json"
            older.write_text(json.dumps(parsed_json("旧结果", image="figs/shared.jpg"), ensure_ascii=False), encoding="utf-8")
            newer.write_text(json.dumps(parsed_json("新结果", image="figs/shared.jpg"), ensure_ascii=False), encoding="utf-8")

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=parsed_dir,
                manifest=None,
                output_dir=output_dir,
                open_dashboard=False,
                roster_dir=root / "roster",
                latest_only=True,
            )

            self.assertEqual(summary["overall"]["case_count"], 1)
            self.assertEqual(summary["cases"][0]["character"]["name"], "新结果")
            self.assertEqual(summary["input"]["parsed_dir_discovered_count"], 2)
            self.assertEqual(summary["input"]["parsed_dir_selected_count"], 1)
            self.assertIn("latest-only", summary["warnings"][0])

    def test_run_demo_pipeline_builds_endgame_plan_from_roster_and_team_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            roster_path = root / "roster_index.json"
            targets_path = root / "targets.json"
            team_path = root / "team_cards.json"
            actions_path = root / "action_cards.json"
            tiers_path = root / "tier_watchlist.json"
            delta_path = root / "roster_delta.json"
            roster_path.write_text(
                json.dumps({"characters": [{"name": "星见雅"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            targets_path.write_text(
                json.dumps(
                    {
                        "targets": [
                            {
                                "target": "危局强袭战 稳定通关",
                                "priority": "high",
                                "source": {"source_ref": "targets/crisis.html", "content_sha256": "a" * 64},
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            team_path.write_text(
                json.dumps(
                    {
                        "cards": [
                            {
                                "target": "危局强袭战 稳定通关",
                                "team_title": "星见雅 核心队",
                                "team_status": "playable_now",
                                "target_priority": "high",
                                "members": [{"character": "星见雅", "source_class": "owned_snapshot"}],
                                "evidence": {"target_source": "targets/crisis.html", "target_hash": "aaaaaaaaaaaa"},
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actions_path.write_text(json.dumps({"cards": []}, ensure_ascii=False), encoding="utf-8")
            tiers_path.write_text(json.dumps({"entries": []}, ensure_ascii=False), encoding="utf-8")
            delta_path.write_text(json.dumps({"character_changes": []}, ensure_ascii=False), encoding="utf-8")
            manifest = pipeline_tool.build_demo_run_manifest(
                output_dir=root / "demo",
                roster_index=roster_path,
                targets_path=targets_path,
                team_cards_path=team_path,
                action_cards_path=actions_path,
                tier_watchlist_path=tiers_path,
                roster_delta_path=delta_path,
            )
            self.assertIsNotNone(manifest)
            assert manifest is not None
            manifest_path = Path(str(manifest["output_json"]))

            result = pipeline_tool.build_demo_endgame_plan(
                roster_index=roster_path,
                output_dir=root / "demo",
                team_cards_path=team_path,
                targets_path=targets_path,
                action_cards_path=actions_path,
                tier_watchlist_path=tiers_path,
                roster_delta_path=delta_path,
                run_manifest_path=manifest_path,
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["schema_version"], "p2.0-lite-endgame-plan")
            self.assertEqual(result["summary"]["ready_now_count"], 1)
            self.assertEqual(result["summary"]["trusted_plan_count"], 1)
            self.assertTrue(Path(result["output_json"]).exists())
            self.assertEqual(result["target_plans"][0]["plan_trust_level"], "trusted")

    def test_run_demo_pipeline_manifest_uses_explicit_expected_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_path = root / "parsed_case.json"
            expected_path = root / "custom_expected.json"
            manifest_path = root / "demo_manifest.json"
            output_dir = root / "demo"
            data = parsed_json()
            parsed_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            expected_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "name": "manifest_case",
                                "parsed": str(parsed_path),
                                "expected": str(expected_path),
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=None,
                manifest=manifest_path,
                output_dir=output_dir,
                roster_dir=root / "roster",
                open_dashboard=False,
            )

            self.assertEqual(summary["input"]["source_mode"], "manifest controlled mode")
            self.assertEqual(summary["overall"]["expected_available_count"], 1)
            self.assertEqual(summary["cases"][0]["expected_json_name"], "custom_expected.json")
            self.assertEqual(summary["cases"][0]["pass_rate"], 1.0)

    def test_run_demo_pipeline_with_targets_generates_training_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            targets_path = root / "targets.json"
            tier_snapshot_path = root / "tier_snapshot.json"
            parsed_dir.mkdir()
            parsed_path = parsed_dir / "case_a.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False), encoding="utf-8")
            targets_path.write_text(json.dumps(targets_json(), ensure_ascii=False), encoding="utf-8")
            tier_snapshot_path.write_text(json.dumps(tier_snapshot_json(), ensure_ascii=False), encoding="utf-8")

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=parsed_dir,
                manifest=None,
                output_dir=output_dir,
                open_dashboard=False,
                targets=targets_path,
                roster_dir=root / "roster",
                tier_snapshot=tier_snapshot_path,
            )
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")

            self.assertIn("training_plan", summary)
            self.assertGreater(summary["training_plan"]["plan_item_count"], 0)
            self.assertTrue(summary["training_plan"]["history_context"]["available"])
            self.assertEqual(summary["training_plan"]["history_context"]["character_count"], 1)
            self.assertEqual(summary["training_plan"]["resource_plan"]["budget"]["daily_stamina"], 240.0)
            self.assertTrue(summary["training_plan"]["resource_plan"]["today"])
            self.assertIn("action_cards", summary)
            self.assertTrue(Path(summary["action_cards"]["output_json"]).exists())
            self.assertTrue(Path(summary["action_cards"]["output_md"]).exists())
            self.assertGreater(summary["action_cards"]["summary"]["high_priority_action_count"], 0)
            self.assertGreater(summary["action_cards"]["summary"]["tier_signal_count"], 0)
            self.assertEqual(
                Path(summary["action_cards"]["input"]["tier_watchlist"]).name,
                "tier_watchlist.json",
            )
            self.assertIn("team_cards", summary)
            self.assertTrue(Path(summary["team_cards"]["output_json"]).exists())
            self.assertTrue(Path(summary["team_cards"]["output_md"]).exists())
            self.assertGreater(summary["team_cards"]["summary"]["team_card_count"], 0)
            self.assertIn("high_value_playable_team_count", summary["team_cards"]["summary"])
            self.assertIn("tier_watchlist", summary)
            self.assertTrue(Path(summary["tier_watchlist"]["output_json"]).exists())
            self.assertTrue(Path(summary["tier_watchlist"]["output_md"]).exists())
            self.assertGreater(summary["tier_watchlist"]["summary"]["watch_candidate_count"], 0)
            self.assertGreater(summary["tier_watchlist"]["summary"]["verified_entry_count"], 0)
            self.assertTrue(Path(summary["training_plan"]["output_json"]).exists())
            self.assertTrue(Path(summary["training_plan"]["output_md"]).exists())
            self.assertIn("Training Plan", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("Action Cards", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("Review Inbox", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("Tier Watchlist", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("Team Cards", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("Final Brief", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("final_brief", summary)
            self.assertTrue(Path(summary["final_brief"]["output_json"]).exists())
            self.assertTrue(Path(summary["final_brief"]["output_md"]).exists())
            self.assertNotEqual(summary["final_brief"]["brief_status"], "ready")
            self.assertIn("action_checklist", summary)
            self.assertTrue(Path(summary["action_checklist"]["output_json"]).exists())
            self.assertTrue(Path(summary["action_checklist"]["output_md"]).exists())
            self.assertTrue(Path(summary["action_checklist"]["review_decisions_template"]).exists())
            self.assertIn("Action Checklist", {item["name"] for item in summary["pipeline_steps"]})
            self.assertEqual(summary["review_inbox"]["pending_count"], 1)
            self.assertEqual(summary["team_cards"]["summary"]["pending_snapshot_count"], 1)
            self.assertIn("今日作战简报", dashboard_html)
            self.assertIn("执行清单", dashboard_html)
            self.assertIn("今天先做什么", dashboard_html)
            self.assertIn("培养优先级候选", dashboard_html)
            self.assertIn("下一步行动", dashboard_html)
            self.assertIn("高难配队候选", dashboard_html)
            self.assertIn("练度更新收件箱", dashboard_html)
            self.assertIn("Tier / 保值观察", dashboard_html)
            self.assertIn("tier_watchlist.json", dashboard_html)
            self.assertIn("tier signal", dashboard_html)
            self.assertIn("team value", dashboard_html)
            self.assertIn("catalog candidate 不代表已拥有", dashboard_html)
            self.assertIn("pending snapshot 尚未进入 accepted roster", dashboard_html)
            self.assertIn("今日投入建议", dashboard_html)
            self.assertIn("先人工确认解析结果", dashboard_html)

    def test_run_demo_pipeline_refreshes_targets_from_source_manifest_before_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parsed_dir = root / "parsed"
            output_dir = root / "demo"
            source_path = root / "endgame_source.html"
            manifest_path = root / "target_sources.json"
            parsed_dir.mkdir()
            parsed_path = parsed_dir / "case_a.json"
            parsed_path.write_text(json.dumps(parsed_json(), ensure_ascii=False), encoding="utf-8")
            source_path.write_text(
                "<html><title>危局强袭战 本期目标</title><body>危局强袭战 推荐冰属性与异常队伍。</body></html>",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "game": "zzz",
                        "source_type": "official_snapshot",
                        "default_minimums": {"character_level": 60, "equipment_level": 60, "skill_level": 8},
                        "sources": [
                            {
                                "input": str(source_path),
                                "goal_id": "zzz_mock_refresh",
                                "target_tier": "稳定通关",
                                "priority": "high",
                                "preferred_characters": ["星见雅"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=parsed_dir,
                manifest=None,
                output_dir=output_dir,
                open_dashboard=False,
                target_source_manifest=manifest_path,
                roster_dir=root / "roster",
            )
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")

            self.assertEqual(summary["target_refresh"]["target_count"], 1)
            self.assertEqual(summary["target_refresh"]["source_count"], 1)
            self.assertEqual(summary["target_refresh"]["freshness"]["level"], "fresh")
            self.assertTrue(Path(summary["target_refresh"]["output_json"]).exists())
            self.assertIn("training_plan", summary)
            self.assertEqual(summary["training_plan"]["targets_json"], summary["target_refresh"]["output_json"])
            self.assertEqual(summary["training_plan"]["target_source_status"]["status"], "current")
            self.assertTrue(summary["training_plan"]["target_coverage"])
            self.assertGreater(summary["training_plan"]["plan_item_count"], 0)
            self.assertIn("Target Refresh", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("终局目标刷新", dashboard_html)
            self.assertIn("source status", dashboard_html)
            self.assertIn("current", dashboard_html)
            self.assertIn("endgame_targets.json", dashboard_html)

    def test_run_demo_pipeline_rejects_static_targets_and_target_source_manifest_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(pipeline_tool.DemoPipelineError):
                pipeline_tool.run_pipeline(
                    images_dir=None,
                    parsed_dir=root,
                    manifest=None,
                    output_dir=root / "demo",
                    open_dashboard=False,
                    targets=root / "targets.json",
                    target_source_manifest=root / "target_sources.json",
                    roster_dir=root / "roster",
                )

    def test_run_demo_pipeline_records_snapshot_history_and_diffs_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_parsed_dir = root / "parsed_first"
            second_parsed_dir = root / "parsed_second"
            first_output_dir = root / "demo_first"
            second_output_dir = root / "demo_second"
            history_dir = root / "history"
            first_parsed_dir.mkdir()
            second_parsed_dir.mkdir()
            first_path = first_parsed_dir / "case_first.json"
            second_path = second_parsed_dir / "case_second.json"
            first_path.write_text(json.dumps(parsed_json(atk="200"), ensure_ascii=False), encoding="utf-8")
            second_path.write_text(json.dumps(parsed_json(atk="260"), ensure_ascii=False), encoding="utf-8")

            first = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=first_parsed_dir,
                manifest=None,
                output_dir=first_output_dir,
                history_dir=history_dir,
                roster_dir=root / "roster",
                open_dashboard=False,
            )
            second = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=second_parsed_dir,
                manifest=None,
                output_dir=second_output_dir,
                history_dir=history_dir,
                roster_dir=root / "roster",
                open_dashboard=False,
            )

            self.assertEqual(first["snapshot_history"]["snapshot_count"], 1)
            self.assertEqual(first["snapshot_history"]["diff_count"], 0)
            self.assertEqual(first["snapshot_history"]["no_previous_count"], 1)
            self.assertEqual(second["snapshot_history"]["snapshot_count"], 1)
            self.assertEqual(second["snapshot_history"]["diff_count"], 1)
            self.assertEqual(second["snapshot_history"]["changed_character_count"], 1)
            item = second["snapshot_history"]["items"][0]
            self.assertGreater(item["change_count"], 0)
            self.assertTrue(Path(item["current_snapshot"]).exists())
            self.assertTrue(Path(item["previous_snapshot"]).exists())
            self.assertTrue(Path(item["diff_md"]).exists())
            self.assertTrue((history_dir / "index.json").exists())
            dashboard_html = Path(second["dashboard_html"]).read_text(encoding="utf-8")
            self.assertIn("快照历史", dashboard_html)
            self.assertIn("snapshot_diff_md", dashboard_html)

    def test_run_demo_pipeline_image_mode_writes_update_state_and_new_only_skips_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "figs"
            output_dir = root / "demo"
            state_file = root / "update_state.json"
            images_dir.mkdir()
            image_a = images_dir / "a.jpg"
            image_b = images_dir / "b.jpg"
            image_a.write_bytes(b"image-a-v1")
            image_b.write_bytes(b"image-b-v1")
            processed: list[str] = []
            original_process = pipeline_tool.process_image_case

            def fake_process_image_case(image_path, *, name, output_dir, expected_dir, engine, game, layout):  # noqa: ANN001, ANN003
                processed.append(Path(image_path).name)
                case = pipeline_tool.case_template(name)
                case["image"] = str(Path(image_path).resolve())
                case["character"] = {"name": f"角色{name}", "level": "60", "rank": "S"}
                case["review_status"] = "PASS"
                case["quality"] = {"requires_manual_review": False}
                return case

            pipeline_tool.process_image_case = fake_process_image_case
            try:
                first = pipeline_tool.run_pipeline(
                    images_dir=images_dir,
                    parsed_dir=None,
                    manifest=None,
                    output_dir=output_dir,
                    state_file=state_file,
                    roster_dir=root / "roster",
                    open_dashboard=False,
                )
                self.assertEqual(processed, ["a.jpg", "b.jpg"])
                self.assertTrue(state_file.exists())
                self.assertEqual(first["update_state"]["processed_image_count"], 2)
                self.assertEqual(first["update_state"]["processed_character_count"], 2)
                self.assertEqual(first["update_state"]["processed_characters"], ["角色a", "角色b"])

                processed.clear()
                second = pipeline_tool.run_pipeline(
                    images_dir=images_dir,
                    parsed_dir=None,
                    manifest=None,
                    output_dir=output_dir,
                    state_file=state_file,
                    new_only=True,
                    roster_dir=root / "roster",
                    open_dashboard=False,
                )
                self.assertEqual(processed, [])
                self.assertEqual(second["overall"]["case_count"], 0)
                self.assertEqual(second["update_state"]["skipped_unchanged_count"], 2)
                self.assertEqual(second["update_state"]["skipped_images"], ["a.jpg", "b.jpg"])
                self.assertIn("new-only 模式没有发现新增或变更图片", second["warnings"][0])

                image_b.write_bytes(b"image-b-v2")
                processed.clear()
                third = pipeline_tool.run_pipeline(
                    images_dir=images_dir,
                    parsed_dir=None,
                    manifest=None,
                    output_dir=output_dir,
                    state_file=state_file,
                    new_only=True,
                    roster_dir=root / "roster",
                    open_dashboard=False,
                )
                self.assertEqual(processed, ["b.jpg"])
                self.assertEqual(third["update_state"]["status_counts"]["changed"], 1)
                self.assertEqual(third["update_state"]["processed_image_count"], 1)
                self.assertEqual(third["update_state"]["processed_characters"], ["角色b"])
                dashboard_html = Path(third["dashboard_html"]).read_text(encoding="utf-8")
                self.assertIn("本轮角色更新", dashboard_html)
                self.assertIn("角色b", dashboard_html)
                self.assertIn("跳过未变更图片", dashboard_html)
            finally:
                pipeline_tool.process_image_case = original_process

    def test_cli_demo_command_calls_pipeline_core(self) -> None:
        calls = []
        original_run_pipeline = cli_tool.demo_tool.run_pipeline

        def fake_run_pipeline(**kwargs):  # noqa: ANN003
            calls.append(kwargs)
            return {"dashboard_html": "demo.html", "summary_json": "summary.json"}

        cli_tool.demo_tool.run_pipeline = fake_run_pipeline
        try:
            exit_code = cli_tool.run_demo(
                argparse.Namespace(
                    images_dir="figs",
                    parsed_dir=None,
                    manifest=None,
                    output_dir="data/probes/demo",
                    expected_dir="data/probes/expected",
                    engine="paddle",
                    game="zzz",
                    layout="zzz-agent-card",
                    open=False,
                    latest_only=False,
                    new_only=False,
                    clean_demo=False,
                    state_file=None,
                    targets=None,
                    history_dir=None,
                    target_source_manifest=None,
                    character_catalog=None,
                    roster_dir="data/probes/roster",
                    tier_snapshot=None,
                    daily_stamina=None,
                    horizon_days=None,
                )
            )
        finally:
            cli_tool.demo_tool.run_pipeline = original_run_pipeline

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["engine"], "paddle")
        self.assertIsNotNone(calls[0]["images_dir"])
        self.assertFalse(calls[0]["latest_only"])
        self.assertFalse(calls[0]["new_only"])
        self.assertIsNone(calls[0]["state_file"])
        self.assertIsNone(calls[0]["targets"])
        self.assertIsNone(calls[0]["history_dir"])
        self.assertIsNone(calls[0]["target_source_manifest"])
        self.assertIsNone(calls[0]["character_catalog"])
        self.assertIsNotNone(calls[0]["roster_dir"])
        self.assertIsNone(calls[0]["tier_snapshot"])
        self.assertIsNone(calls[0]["daily_stamina"])
        self.assertIsNone(calls[0]["horizon_days"])


if __name__ == "__main__":
    unittest.main()
