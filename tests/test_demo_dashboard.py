from __future__ import annotations

import argparse
import contextlib
import io
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


def dashboard_minimal_summary() -> dict:
    return {
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
    }


def write_demo_doctor(output_dir: Path, doctor: dict | None = None) -> str:
    doctor_dir = output_dir / "demo_doctor"
    doctor_dir.mkdir(parents=True, exist_ok=True)
    doctor_path = doctor_dir / "demo_doctor.json"
    doctor_path.write_text(json.dumps(doctor or {"doctor_status": "ready_to_try"}, ensure_ascii=False), encoding="utf-8")
    return pipeline_tool.sha256_file(doctor_path)


def write_launcher_report(output_dir: Path, report: dict) -> Path:
    launcher_dir = output_dir / "launcher"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    report_path = launcher_dir / "launcher_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return report_path


class DemoDashboardTests(unittest.TestCase):
    def test_humanize_text_explains_internal_gate_terms(self) -> None:
        self.assertEqual(
            dashboard_tool.humanize_text("缺少 run_manifest；无法确认本轮产物是否同批生成。"),
            "缺少本轮运行清单：这批识别结果、复核预览和建议可能不是同一次生成，先刷新本地演示。",
        )
        self.assertEqual(
            dashboard_tool.humanize_text("pending snapshot 尚未进入 accepted roster；确认前不能进入 try_now。"),
            "这张解析结果还没人工确认：确认前不能当作已拥有练度，也不会进入可尝试队伍。",
        )
        self.assertEqual(
            dashboard_tool.humanize_text("没有发现可处理的图片或 parsed JSON。"),
            "没有发现可处理的图片或已解析结果。",
        )

    def test_final_brief_first_layer_is_reader_friendly(self) -> None:
        summary = dashboard_minimal_summary()
        repeated_review_card = {
            "rank": 2,
            "card_type": "review_snapshot",
            "title": "复核 珂蕾妲 的解析快照",
            "reason": "pending snapshot 尚未进入 accepted roster；确认前不能进入 try_now。",
            "character": "珂蕾妲",
            "evidence": {"review_html": "data/probes/demo/cases/kole_review.html"},
            "command_hint": "python tools/probes/apply_review_decisions.py --decision-manifest data/probes/review_decisions.json",
            "warnings": [],
        }
        summary["final_brief"] = {
            "brief_status": "needs_review",
            "output_json": "data/probes/demo/final_brief/final_brief.json",
            "output_md": "data/probes/demo/final_brief/final_brief.md",
            "summary": {
                "trusted_plan_count": 0,
                "pending_review_count": 2,
                "ready_now_target_count": 0,
                "needs_recording_target_count": 0,
                "watch_only_target_count": 1,
            },
            "warnings": ["缺少 run_manifest；无法确认本轮产物是否同批生成。"],
            "top_cards": [
                {
                    "rank": 1,
                    "card_type": "data_warning",
                    "title": "先确认本轮数据一致性",
                    "reason": "run_manifest 显示输入缺失、错批或无法确认；这里不会把方案当作可信 ready。",
                    "evidence": {"artifact": "data/probes/demo/run_manifest.json"},
                    "command_hint": "python tools/probes/run_demo_pipeline.py --images-dir figs --open",
                    "warnings": [],
                },
                repeated_review_card,
                {**repeated_review_card, "rank": 3, "title": "复核 星徽·比利 的解析快照", "character": "星徽·比利"},
                {**repeated_review_card, "rank": 4, "title": "复核 潘引壶 的解析快照", "character": "潘引壶"},
            ],
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("一眼结论", html)
        self.assertIn("验收助手", html)
        self.assertIn("先别把这页当验收结果", html)
        self.assertIn("准确率验收", html)
        self.assertIn("dist\\MihoProbe.exe check --open", html)
        self.assertIn("看软件体验", html)
        self.assertIn("dist\\MihoProbe.exe", html)
        self.assertIn("更新练度", html)
        self.assertIn("APP 自动点击还在工作流校准", html)
        self.assertIn("更新高难配队", html)
        self.assertIn("不要扫整个历史解析目录", html)
        self.assertIn("这不是验收结果", html)
        self.assertIn("不代表准确率验收", html)
        self.assertIn("先点 MihoProbe 打开缓存页面", html)
        self.assertIn("当前可采信范围", html)
        self.assertIn("现在能信", html)
        self.assertIn("只能把这页当排查入口", html)
        self.assertIn("现在不能信", html)
        self.assertIn("不能按配队、培养或高难建议行动", html)
        self.assertIn("下一步入口", html)
        self.assertIn("MihoProbe Update", html)
        self.assertIn("现在先做", html)
        self.assertIn("先处理数据一致性", html)
        self.assertIn("推荐操作路线", html)
        self.assertIn("刷新本地演示", html)
        self.assertIn("确认复核结果", html)
        self.assertIn("再看配队建议", html)
        self.assertIn("本轮数据来源缺失或不一致", html)
        self.assertIn("先刷新本地演示", html)
        self.assertIn("刷新本地演示流程", html)
        self.assertIn("为什么不能直接用", html)
        self.assertIn("总判断", html)
        self.assertIn("可直接行动", html)
        self.assertIn("待确认快照", html)
        self.assertIn("证据明细", html)
        self.assertIn("还有 1 个待处理项", html)
        self.assertIn("下一步说明", html)
        self.assertIn("诊断统计（展开看）", html)
        self.assertNotIn("查看原始产物", html)
        self.assertNotIn("简报 Markdown", html)
        self.assertNotIn("简报 JSON", html)
        self.assertNotIn("技术细节", html)
        self.assertNotIn("python tools/probes/run_demo_pipeline.py --images-dir figs --open", html)
        self.assertNotIn("Fresh OCR", html)
        self.assertNotIn("P0.9", html)
        self.assertNotIn("Brief Warning", html)
        self.assertNotIn("brief status", html)
        self.assertNotIn("trusted ready", html)
        self.assertNotIn("pending review", html)
        self.assertNotIn("watch only", html)
        self.assertNotIn("先重跑 demo", html)
        self.assertNotIn("OCR、复核", html)
        self.assertNotIn("run_miho_本地演示.bat", html)

    def test_dashboard_shows_plan_update_readiness_panel(self) -> None:
        summary = dashboard_minimal_summary()
        summary["plan_update_readiness"] = {
            "source_status": "sources_missing_local_only",
            "warning": "当前包含缺失数据源，平均结果只代表本地/demo 诊断，不代表 P0/P1 高难规划验收。",
            "missing_blockers": ["endgame_targets", "tier_snapshot"],
            "output_json": "data/probes/demo/plan_update_readiness/plan_update_readiness.json",
            "output_md": "data/probes/demo/plan_update_readiness/plan_update_readiness.md",
            "items": [
                {
                    "id": "accepted_roster",
                    "title": "已确认角色库",
                    "status": "ready",
                    "path": "data/probes/roster/roster_index.json",
                    "detail": "accepted roster 已就绪，当前确认角色数 3。",
                },
                {
                    "id": "endgame_targets",
                    "title": "高难目标数据",
                    "status": "missing",
                    "path": None,
                    "detail": "缺少高难目标输入；规划只能显示本地/demo 诊断。",
                },
            ],
            "next_actions": ["补充 --targets 或 --target-source-manifest，再运行 MihoProbe.exe plan-update --open。"],
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("Plan Update 数据源", html)
        self.assertIn("缺少规划数据源", html)
        self.assertIn("已确认角色库", html)
        self.assertIn("高难目标数据", html)
        self.assertIn("补充 --targets", html)
        self.assertIn("readiness.md", html)

    def test_dashboard_shows_app_export_readiness_panel(self) -> None:
        summary = dashboard_minimal_summary()
        summary["app_export_readiness"] = {
            "status": "ready_for_calibration",
            "workflow_html": "data/probes/demo/app_export_workflow/miyoushe_export_workflow.html",
            "workflow_json": "data/probes/demo/app_export_workflow/miyoushe_export_workflow.json",
            "calibration_template_json": "data/probes/demo/app_export_workflow/miyoushe_app_export_calibration_template.json",
            "route_status": "calibration_required",
            "automation_status": "disabled_until_calibrated",
            "next_command": "python tools/probes/window_screenshot_probe.py --window-title 米游社 --dry-run",
            "dry_run_command": r"dist\MihoProbe.exe app-export-run --no-open",
            "execute_command": r"dist\MihoProbe.exe app-export-run --execute --confirm-official-ui --no-open",
            "update_command": r"dist\MihoProbe.exe update --open",
            "manual_save_to_figs_step": "在米游社官方 UI 保存分享图到 figs，或手动把官方分享图放进该目录。",
            "review_gate": "Dashboard 人工复核通过后，才允许进入本地 accepted roster / 高难建议。",
            "forbidden_boundaries": ["auto_login", "token_read", "cookie_read", "game_client_control"],
            "warnings": ["4 navigation step(s) still need UIA selector calibration."],
            "route_steps": [
                {
                    "label": "1. 打开官方 APP",
                    "status": "manual",
                    "description": "用户手动打开已登录的米游社 APP；工具不登录、不读 cookie/token。",
                    "command": "",
                },
                {
                    "label": "4. 本地更新 Dashboard",
                    "status": "implemented",
                    "description": "只处理本地官方分享图，失败时必须显式非 0 或显示阻断状态。",
                    "command": r"dist\MihoProbe.exe update --open",
                },
            ],
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("一键更新练度准备状态", html)
        self.assertIn("已沉淀路线，等待校准", html)
        self.assertIn("当前不会自动点击米游社", html)
        self.assertIn("校准清单状态", html)
        self.assertIn("先 dry-run", html)
        self.assertIn("确认后执行", html)
        self.assertIn("app-export-run", html)
        self.assertIn("本地更新入口", html)
        self.assertIn("MihoProbe.exe update", html)
        self.assertIn("Dashboard 人工复核", html)
        self.assertIn("APP 导出流程页", html)
        self.assertIn("APP 导出流程数据", html)
        self.assertIn("APP 导出校准清单", html)

    def test_dashboard_layout_is_bounded_for_wide_screens(self) -> None:
        html = dashboard_tool.render_html(dashboard_minimal_summary())

        self.assertIn("width: min(100%, 1440px)", html)
        self.assertIn("repeat(auto-fit, minmax(220px, 1fr))", html)
        self.assertIn("repeat(auto-fit, minmax(180px, 1fr))", html)
        self.assertIn("repeat(auto-fit, minmax(420px, 1fr))", html)
        self.assertIn("grid-template-columns: minmax(280px, 0.9fr) minmax(420px, 1.6fr)", html)
        self.assertIn("max-height: 220px; overflow: auto", html)

    def test_action_checklist_visible_copy_hides_internal_terms(self) -> None:
        summary = dashboard_minimal_summary()
        summary["action_checklist"] = {
            "checklist_status": "blocked",
            "summary": {"item_count": 0, "ready_count": 0, "needs_review_count": 0, "blocked_count": 1},
            "warnings": ["缺少 run_manifest；无法确认本轮产物是否同批生成。"],
            "output_json": "data/probes/demo/action_checklist/action_checklist.json",
            "output_md": "data/probes/demo/action_checklist/action_checklist.md",
            "review_decisions_template": "data/probes/demo/action_checklist/review_decisions_template.json",
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("待确认项只会生成复核模板，仅观察项不是抽卡建议", html)
        self.assertIn("缺少本轮运行清单", html)
        self.assertNotIn("pending 只会生成复核模板", html)
        self.assertNotIn("watch_only 不是抽卡建议", html)
        self.assertNotIn("缺少 run_manifest；无法确认本轮产物是否同批生成。", html)

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
            "demo_doctor": {
                "schema_version": "p2.9-lite-demo-doctor",
                "doctor_status": "needs_rerun",
                "headline": "先重跑 demo pipeline，刷新本轮建议",
                "try_now_allowed": False,
                "rerun_required": True,
                "review_required": False,
                "safe_apply_required": False,
                "primary_next_action": "rerun_demo_pipeline",
                "summary": {
                    "refresh_status": "stale_after_apply",
                    "brief_status": "ready",
                    "checklist_status": "ready",
                    "preview_status": "ready",
                    "apply_status": "applied",
                    "pending_review_count": 0,
                    "ready_try_now_count": 1,
                    "preview_accept_count": 0,
                    "preview_would_update_roster_count": 1,
                    "run_manifest_exists": True,
                    "demo_command_safe_to_rerun": True,
                },
                "commands": {
                    "rerun_demo": "python tools/probes/run_demo_pipeline.py --parsed-dir data/probes/parsed --latest-only --clean-demo",
                    "preview": "python tools/probes/preview_review_decisions.py --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json",
                    "safe_apply": "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json --roster-dir data/probes/roster --preview-result data/probes/demo/review_preview/review_decision_preview.json --require-preview-ready",
                },
                "evidence_check": {
                    "status": "warning",
                    "strict_status": "needs_apply",
                    "matched_preview_apply": False,
                    "matched_refresh_command": True,
                    "matched_run_manifest": True,
                    "warnings": ["apply_receipt_preview_result_sha256_mismatch"],
                    "blockers": [],
                },
                "action_contract": {
                    "primary_next_action": "rerun_demo_pipeline",
                    "is_read_only": False,
                    "writes_roster": False,
                    "requires_manual_confirmation": False,
                    "allowed_for_launcher": True,
                    "reason": "demo rerun command is safe to print",
                },
                "blocking_reasons": ["ready_try_now_not_actionable_under_current_doctor_status"],
                "warnings": [],
                "output_json": "data/probes/demo/demo_doctor/demo_doctor.json",
                "output_md": "data/probes/demo/demo_doctor/demo_doctor.md",
            },
            "launcher_report": {
                "schema_version": "p3.5-lite-dashboard-launcher-report",
                "loaded": True,
                "launcher_report_freshness": "current",
                "matches_current_doctor": True,
                "follow_up_matches_current_doctor": True,
                "launcher_report_operation_state": "follow_up_current",
                "freshness_match_source": "follow_up",
                "current_demo_doctor_sha256": "a" * 64,
                "report_initial_doctor_sha256": "b" * 64,
                "report_follow_up_sha256": "a" * 64,
                "freshness_warnings": [],
                "launcher_status": "executed_with_followup_warning",
                "executed": True,
                "returncode": 0,
                "command_script_resolved": str(PROJECT_ROOT / "tools" / "probes" / "run_demo_pipeline.py"),
                "rerun_started_at": "2026-06-29T10:00:00+08:00",
                "rerun_finished_at": "2026-06-29T10:00:03+08:00",
                "warnings": ["follow_up_doctor_not_updated_after_rerun"],
                "blockers": [],
                "output_json": "data/probes/demo/launcher/launcher_report.json",
                "output_md": "data/probes/demo/launcher/launcher_report.md",
                "output_history_json": "data/probes/demo/launcher/history/launcher_report_20260629.json",
                "output_history_md": "data/probes/demo/launcher/history/launcher_report_20260629.md",
                "follow_up": {
                    "loaded": True,
                    "doctor_status": "needs_apply",
                    "primary_next_action": "safe_apply_review_decisions",
                    "try_now_allowed": False,
                    "strict_status": "needs_apply",
                    "updated_after_rerun": False,
                    "warnings": ["follow_up_doctor_not_updated_after_rerun"],
                    "doctor_warnings": [],
                    "evidence_blockers": [],
                    "blocking_reasons": ["preview_ready_but_apply_missing"],
                },
            },
            "refresh_status": {
                "schema_version": "p2.7-lite-refresh-status",
                "refresh_status": "stale_after_apply",
                "output_json": "data/probes/demo/refresh_status/refresh_status.json",
                "output_md": "data/probes/demo/refresh_status/refresh_status.md",
                "summary": {
                    "receipt_exists": True,
                    "needs_demo_refresh": True,
                    "did_enter_roster_count": 1,
                    "did_write_accepted_count": 1,
                    "did_write_rejected_count": 0,
                },
                "stale_reasons": ["review_apply_receipt.created_at is newer than run_manifest.created_at"],
                "affected_artifacts": ["final_brief", "action_checklist"],
                "refresh_command": "python tools/probes/run_demo_pipeline.py --parsed-dir data/probes/parsed --latest-only --clean-demo",
                "command_state": {
                    "safe_to_rerun": True,
                    "missing_inputs": [],
                    "source_mode": "parsed_dir",
                    "demo_command_json": "data/probes/demo/demo_command.json",
                    "demo_command_md": "data/probes/demo/demo_command.md",
                },
                "action_state": {
                    "try_now_allowed": False,
                    "review_allowed": True,
                    "safe_apply_allowed": True,
                    "rerun_required": True,
                    "primary_next_action": "rerun_demo_pipeline",
                },
                "warnings": [],
            },
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
                "preview_command": "python tools/probes/preview_review_decisions.py --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json",
                "safe_apply_command": "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized --decision-manifest data/probes/demo/action_checklist/review_decisions_template.json --roster-dir data/probes/roster --preview-result data/probes/demo/review_preview/review_decision_preview.json --require-preview-ready",
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
            "review_decision_preview": {
                "schema_version": "p2.3-lite-review-decision-preview",
                "preview_status": "ready",
                "output_json": "data/probes/demo/review_preview/review_decision_preview.json",
                "output_md": "data/probes/demo/review_preview/review_decision_preview.md",
                "summary": {"would_update_roster_count": 1},
            },
            "review_apply": {
                "schema_version": "p2.6-lite-review-apply-dashboard",
                "apply_status": "applied",
                "output_json": "data/probes/roster/review_apply_receipt.json",
                "output_md": "data/probes/roster/review_apply_receipt.md",
                "review_log_json": "data/probes/roster/review_log.json",
                "summary": {
                    "accepted_count": 1,
                    "rejected_count": 0,
                    "pending_count": 0,
                    "did_enter_roster_count": 1,
                    "did_write_accepted_count": 1,
                    "did_write_rejected_count": 0,
                    "preview_validated_count": 1,
                    "preview_not_provided_count": 0,
                },
                "records": [
                    {
                        "character": "星见雅",
                        "decision": "accept",
                        "status": "accepted",
                        "did_enter_roster": True,
                        "did_write_accepted": True,
                        "did_write_rejected": False,
                        "preview_validation_status": "validated",
                    }
                ],
                "warnings": [],
            },
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("当前状态诊断", html)
        self.assertIn("诊断结论", html)
        self.assertIn("需重跑", html)
        self.assertIn("不建议直接尝试", html)
        self.assertIn("诊断证据", html)
        self.assertIn("严格状态", html)
        self.assertIn("needs_apply", html)
        self.assertIn("动作边界说明", html)
        self.assertIn("启动器允许", html)
        self.assertIn("会写角色库", html)
        self.assertIn("演示重跑命令可安全展示", html)
        self.assertIn("应用回执与复核预览校验不一致", html)
        self.assertIn("当前诊断状态不允许直接尝试", html)
        self.assertIn("demo_doctor.json", html)
        self.assertIn("启动器执行记录", html)
        self.assertIn("executed_with_followup_warning", html)
        self.assertIn("launcher report freshness", html)
        self.assertIn("follow_up_matches_current_doctor", html)
        self.assertIn("operation_state", html)
        self.assertIn("freshness_match_source", html)
        self.assertIn("command_script_resolved", html)
        self.assertIn("rerun_started_at", html)
        self.assertIn("follow_up.doctor_status", html)
        self.assertIn("follow_up.updated_after_rerun", html)
        self.assertIn("应用复核结果前需要人工确认", html)
        self.assertIn("launcher_report_20260629.json", html)
        self.assertIn("后续诊断没有在重跑后更新", html)
        self.assertIn("软件入口", html)
        self.assertIn("看软件体验", html)
        self.assertIn("一键更新练度", html)
        self.assertIn("评级快检", html)
        self.assertIn("准确率验收", html)
        self.assertIn("APP 导出流程", html)
        self.assertIn(r"dist\MihoProbe.exe update --open", html)
        self.assertIn(r"dist\MihoProbe.exe rank-check --open", html)
        self.assertIn("只看角色头像左上角和音擎评级区的 A/S 艺术字", html)
        self.assertIn("不会在页面里自动应用数据、控制游戏或登录账号", html)
        self.assertIn("会不会重新识别", html)
        self.assertIn("本地安全边界", html)
        self.assertIn("不会登录账号、不会读取 token/cookie", html)
        self.assertIn("今日作战简报", html)
        self.assertIn("刷新状态", html)
        self.assertIn("当前简报可能过期", html)
        self.assertIn("应用后已过期", html)
        self.assertIn("人工应用时间晚于运行清单", html)
        self.assertIn("当前下一步", html)
        self.assertIn("重跑演示流程", html)
        self.assertIn("允许去游戏里试", html)
        self.assertIn(">否<", html)
        self.assertIn("--parsed-dir data/probes/parsed --latest-only --clean-demo", html)
        self.assertIn("demo_command.json", html)
        self.assertIn("执行清单", html)
        self.assertIn("先看这一块就够了", html)
        self.assertIn("证据明细", html)
        self.assertIn("诊断统计（展开看）", html)
        self.assertIn("推荐操作路线", html)
        self.assertNotIn("查看原始产物", html)
        self.assertNotIn("final_brief.md", html)
        self.assertIn("review_decisions_template.json", html)
        self.assertIn("review_decision_preview.md", html)
        self.assertIn("复核决策必须先预览，再人工应用", html)
        self.assertIn("复核命令（确认后再复制）", html)
        self.assertIn("应用命令", html)
        self.assertIn("--require-preview-ready", html)
        self.assertIn("复核应用回执", html)
        self.assertIn("进入 roster", html)
        self.assertIn("review_apply_receipt.md", html)
        self.assertIn("可先尝试：危局强袭战", html)
        self.assertLess(html.index("软件入口"), html.index("验收助手"))
        self.assertLess(html.index("软件入口"), html.index("当前结论"))
        self.assertLess(html.index("当前结论"), html.index("今日作战简报"))
        self.assertLess(html.index("今日作战简报"), html.index("执行清单"))
        self.assertLess(html.index("执行清单"), html.index("调试与产物明细"))
        self.assertLess(html.index("调试与产物明细"), html.index("当前状态诊断"))
        self.assertLess(html.index("调试与产物明细"), html.index("<h2>刷新状态</h2>"))
        self.assertLess(html.index("调试与产物明细"), html.index("输入模式"))

    def test_dashboard_hides_launcher_report_when_missing(self) -> None:
        html = dashboard_tool.render_html(dashboard_minimal_summary())

        self.assertNotIn("启动器执行记录", html)

    def test_dashboard_explains_new_only_cache_refresh_without_claiming_missing_data(self) -> None:
        summary = dashboard_minimal_summary()
        update_state = {
            "discovered_image_count": 4,
            "processed_image_count": 0,
            "skipped_unchanged_count": 4,
        }
        summary["input"] = {
            "source_mode": "OCR fresh image mode",
            "new_only": True,
            "images_dir": "figs",
            "update_state": update_state,
        }
        summary["update_state"] = update_state

        html = dashboard_tool.render_html(summary)

        self.assertIn("没有新分享图", html)
        self.assertIn("已扫描 figs 中 4 张官方分享图", html)
        self.assertIn("本次只刷新缓存页面，不会重新跑图片识别", html)
        self.assertIn("放入新分享图或强制重扫", html)
        self.assertIn(r"dist\MihoProbe.exe update --rescan-all --open", html)
        self.assertNotIn("还没有本地数据", html)

    def test_dashboard_surfaces_visual_rank_check_panel(self) -> None:
        summary = dashboard_minimal_summary()
        summary["rank_check"] = {
            "summary_status": "pass",
            "recommendation": "评级视觉快检通过：完整解析失败时，可以优先相信 A/S 艺术字 fallback，再检查名称、等级和驱动盘字段。",
            "image_count": 1,
            "region_count": 2,
            "ok_region_count": 2,
            "review_region_count": 0,
            "output_html": "data/probes/demo/rank_check/rank_check.html",
            "output_json": "data/probes/demo/rank_check/rank_check.json",
            "entries": [
                {
                    "image_name": "1782409461508.jpg",
                    "rank_summary": "角色 S / 音擎 A",
                }
            ],
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("评级视觉快检", html)
        self.assertIn("A/S 艺术字区域已通过", html)
        self.assertIn("评级视觉快检通过", html)
        self.assertIn("A/S 艺术字识别", html)
        self.assertNotIn("fallback", html)
        self.assertIn("1782409461508.jpg", html)
        self.assertIn("角色 S / 音擎 A", html)
        self.assertIn("评级快检页", html)
        self.assertIn("评级快检数据", html)

    def test_dashboard_update_command_ready_is_copy_only(self) -> None:
        summary = dashboard_minimal_summary()
        summary["demo_doctor"] = {
            "doctor_status": "needs_rerun",
            "primary_next_action": "rerun_demo_pipeline",
            "try_now_allowed": False,
            "action_contract": {"allowed_for_launcher": True, "writes_roster": False, "requires_manual_confirmation": False},
            "evidence_check": {"status": "trusted", "strict_status": "trusted"},
        }
        summary["update_command"] = {
            "schema_version": "p3.9-lite-update-command",
            "status": "ready",
            "command": "python tools/probes/doctor_launcher.py --doctor data/probes/demo/demo_doctor/demo_doctor.json --execute-rerun --follow-up-doctor data/probes/demo/demo_doctor/demo_doctor.json --refresh-dashboard --dashboard-summary data/probes/demo/demo_summary.json --dashboard-html data/probes/demo/index.html --max-history 30",
            "argv": ["python", "tools/probes/doctor_launcher.py"],
            "updates": ["accepted roster based local suggestions", "endgame plan", "tier watchlist view", "dashboard visualization"],
            "does_not_update": ["official account data", "tokens/cookies/login state", "online tier data", "formal database"],
            "blockers": [],
            "warnings": [],
            "input": {"max_history": 30},
            "output_json": "data/probes/demo/update_command/update_command.json",
            "output_md": "data/probes/demo/update_command/update_command.md",
        }
        summary["launcher_report"] = {
            "loaded": True,
            "launcher_report_freshness": "current",
            "matches_current_doctor": True,
            "follow_up_matches_current_doctor": False,
            "launcher_status": "printed",
            "executed": False,
            "blockers": [],
            "warnings": [],
            "follow_up": {},
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("本地更新命令", html)
        self.assertIn("可复制命令", html)
        self.assertIn("--refresh-dashboard", html)
        self.assertIn("--dashboard-summary", html)
        self.assertIn("--dashboard-html", html)
        self.assertIn("--max-history 30", html)
        self.assertIn("update_command.json", html)
        self.assertIn("不会刷新", html)
        self.assertIn("官方账号数据", html)
        self.assertNotIn("<button", html)
        self.assertNotIn("自动 apply", html)
        self.assertLess(html.index("<h2>当前状态诊断</h2>"), html.index("<h2>本地更新命令</h2>"))
        self.assertLess(html.index("<h2>本地更新命令</h2>"), html.index("<h2>启动器执行记录</h2>"))

    def test_dashboard_update_command_blocked_does_not_show_runnable_copy(self) -> None:
        summary = dashboard_minimal_summary()
        summary["update_command"] = {
            "schema_version": "p3.9-lite-update-command",
            "status": "blocked",
            "command": None,
            "argv": [],
            "updates": [],
            "does_not_update": [],
            "blockers": ["primary_next_action_not_rerun_demo_pipeline"],
            "warnings": [],
            "input": {"max_history": 30},
            "output_json": "data/probes/demo/update_command/update_command.json",
            "output_md": "data/probes/demo/update_command/update_command.md",
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("本地更新命令", html)
        self.assertIn("当前不可作为本地更新命令运行", html)
        self.assertIn("primary_next_action_not_rerun_demo_pipeline", html)
        self.assertNotIn("<h3>可复制命令</h3>", html)

    def test_dashboard_launcher_report_shows_blockers(self) -> None:
        summary = dashboard_minimal_summary()
        summary["launcher_report"] = {
            "loaded": True,
            "launcher_report_freshness": "current",
            "matches_current_doctor": True,
            "follow_up_matches_current_doctor": False,
            "launcher_report_operation_state": "initial_current",
            "freshness_match_source": "initial_doctor",
            "launcher_status": "blocked",
            "executed": False,
            "returncode": None,
            "command_script_resolved": str(PROJECT_ROOT / "outside" / "tools" / "probes" / "run_demo_pipeline.py"),
            "rerun_started_at": None,
            "rerun_finished_at": None,
            "blockers": ["launcher_command_path_not_canonical"],
            "warnings": [],
            "output_json": "data/probes/demo/launcher/launcher_report.json",
            "output_md": "data/probes/demo/launcher/launcher_report.md",
            "output_history_json": "data/probes/demo/launcher/history/launcher_report_blocked.json",
            "output_history_md": "data/probes/demo/launcher/history/launcher_report_blocked.md",
            "follow_up": {},
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("启动器执行记录", html)
        self.assertIn("启动器已阻断", html)
        self.assertIn("启动器命令路径不在允许范围", html)
        self.assertIn("launcher_report_blocked.json", html)
        self.assertIn("executed", html)
        self.assertIn(">否<", html)

    def test_dashboard_launcher_ready_to_try_is_read_only(self) -> None:
        summary = dashboard_minimal_summary()
        summary["launcher_report"] = {
            "loaded": True,
            "launcher_report_freshness": "current",
            "matches_current_doctor": True,
            "follow_up_matches_current_doctor": True,
            "launcher_report_operation_state": "follow_up_current",
            "freshness_match_source": "follow_up",
            "freshness_warnings": [],
            "launcher_status": "executed",
            "executed": True,
            "returncode": 0,
            "command_script_resolved": str(PROJECT_ROOT / "tools" / "probes" / "run_demo_pipeline.py"),
            "rerun_started_at": "2026-06-29T10:00:00+08:00",
            "rerun_finished_at": "2026-06-29T10:00:02+08:00",
            "blockers": [],
            "warnings": [],
            "output_json": "data/probes/demo/launcher/launcher_report.json",
            "output_md": "data/probes/demo/launcher/launcher_report.md",
            "output_history_json": "data/probes/demo/launcher/history/launcher_report_ready.json",
            "output_history_md": "data/probes/demo/launcher/history/launcher_report_ready.md",
            "dashboard_refresh": {
                "attempted": True,
                "status": "refreshed",
                "summary_json": "data/probes/demo/demo_summary.json",
                "dashboard_html": "data/probes/demo/index.html",
                "warnings": [],
            },
            "follow_up": {
                "loaded": True,
                "doctor_status": "ready_to_try",
                "primary_next_action": "try_now",
                "try_now_allowed": True,
                "strict_status": "trusted",
                "updated_after_rerun": True,
                "warnings": [],
                "doctor_warnings": [],
                "evidence_blockers": [],
                "blocking_reasons": [],
            },
        }

        html = dashboard_tool.render_html(summary)

        self.assertIn("游戏内可尝试", html)
        self.assertIn("follow_up.primary_next_action", html)
        self.assertIn("dashboard_refresh", html)
        self.assertIn("refreshed", html)
        self.assertIn("按执行清单去游戏内尝试", html)
        self.assertIn("launcher_report_ready.json", html)
        self.assertNotIn("执行 try_now", html)
        self.assertNotIn("自动 apply", html)

    def test_launcher_report_summary_marks_followup_hash_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "demo"
            current_sha = write_demo_doctor(output_dir)
            write_launcher_report(
                output_dir,
                {
                    "launcher_status": "executed",
                    "executed": True,
                    "warnings": [],
                    "blockers": [],
                    "follow_up": {"sha256": current_sha, "doctor_status": "ready_to_try"},
                    "dashboard_refresh": {
                        "attempted": True,
                        "status": "refreshed",
                        "summary_json": str(output_dir / "demo_summary.json"),
                        "dashboard_html": str(output_dir / "index.html"),
                        "warnings": [],
                    },
                    "output_history_json": str(output_dir / "launcher" / "history" / "launcher_report_current.json"),
                },
            )

            report = pipeline_tool.build_launcher_report_summary(output_dir)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["launcher_report_freshness"], "current")
            self.assertTrue(report["matches_current_doctor"])
            self.assertTrue(report["follow_up_matches_current_doctor"])
            self.assertEqual(report["launcher_report_operation_state"], "follow_up_current")
            self.assertEqual(report["freshness_match_source"], "follow_up")
            self.assertEqual(report["current_demo_doctor_sha256"], current_sha)
            self.assertEqual(report["report_follow_up_sha256"], current_sha)
            self.assertEqual(report["dashboard_refresh"]["status"], "refreshed")
            self.assertEqual(report["freshness_warnings"], [])

    def test_launcher_report_summary_marks_initial_hash_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "demo"
            current_sha = write_demo_doctor(output_dir)
            write_launcher_report(
                output_dir,
                {
                    "launcher_status": "printed",
                    "executed": False,
                    "initial_doctor_sha256": current_sha,
                    "warnings": [],
                    "blockers": [],
                    "follow_up": {},
                },
            )

            report = pipeline_tool.build_launcher_report_summary(output_dir)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["launcher_report_freshness"], "current")
            self.assertTrue(report["matches_current_doctor"])
            self.assertFalse(report["follow_up_matches_current_doctor"])
            self.assertEqual(report["launcher_report_operation_state"], "initial_current")
            self.assertEqual(report["freshness_match_source"], "initial_doctor")
            self.assertTrue(report["report_is_initial_doctor_state"])
            self.assertEqual(report["report_initial_doctor_sha256"], current_sha)

    def test_initial_current_with_stale_followup_suppresses_try_now(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "demo"
            current_sha = write_demo_doctor(output_dir)
            write_launcher_report(
                output_dir,
                {
                    "launcher_status": "executed",
                    "executed": True,
                    "initial_doctor_sha256": current_sha,
                    "warnings": [],
                    "blockers": [],
                    "follow_up": {
                        "sha256": "c" * 64,
                        "loaded": True,
                        "doctor_status": "ready_to_try",
                        "primary_next_action": "try_now",
                        "try_now_allowed": True,
                    },
                },
            )
            report = pipeline_tool.build_launcher_report_summary(output_dir)
            summary = dashboard_minimal_summary()
            summary["launcher_report"] = report

            html = dashboard_tool.render_html(summary)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["launcher_report_freshness"], "current")
            self.assertEqual(report["launcher_report_operation_state"], "initial_current")
            self.assertFalse(report["follow_up_matches_current_doctor"])
            self.assertIn("launcher_report_follow_up_not_for_current_dashboard", report["freshness_warnings"])
            self.assertIn("launcher report 匹配启动前 doctor", html)
            self.assertIn("follow-up 仅供审计", html)
            self.assertIn("启动器后续建议不属于当前页面", html)
            self.assertNotIn("游戏内可尝试", html)

    def test_initial_current_with_stale_followup_suppresses_safe_apply_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "demo"
            current_sha = write_demo_doctor(output_dir)
            write_launcher_report(
                output_dir,
                {
                    "launcher_status": "printed",
                    "executed": False,
                    "initial_doctor_sha256": current_sha,
                    "warnings": [],
                    "blockers": [],
                    "follow_up": {
                        "sha256": "d" * 64,
                        "loaded": True,
                        "doctor_status": "needs_apply",
                        "primary_next_action": "safe_apply_review_decisions",
                        "try_now_allowed": False,
                    },
                },
            )
            report = pipeline_tool.build_launcher_report_summary(output_dir)
            summary = dashboard_minimal_summary()
            summary["launcher_report"] = report

            html = dashboard_tool.render_html(summary)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["launcher_report_operation_state"], "initial_current")
            self.assertFalse(report["follow_up_matches_current_doctor"])
            self.assertIn("follow-up 仅供审计", html)
            self.assertNotIn("应用复核结果前需要人工确认", html)

    def test_launcher_report_summary_marks_stale_and_dashboard_suppresses_action_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "demo"
            write_demo_doctor(output_dir, {"doctor_status": "blocked"})
            write_launcher_report(
                output_dir,
                {
                    "launcher_status": "executed",
                    "executed": True,
                    "initial_doctor_sha256": "a" * 64,
                    "warnings": [],
                    "blockers": [],
                    "output_history_json": str(output_dir / "launcher" / "history" / "launcher_report_stale.json"),
                    "follow_up": {
                        "sha256": "b" * 64,
                        "loaded": True,
                        "doctor_status": "ready_to_try",
                        "primary_next_action": "try_now",
                        "try_now_allowed": True,
                    },
                },
            )
            report = pipeline_tool.build_launcher_report_summary(output_dir)
            summary = dashboard_minimal_summary()
            summary["launcher_report"] = report

            html = dashboard_tool.render_html(summary)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["launcher_report_freshness"], "stale")
            self.assertFalse(report["matches_current_doctor"])
            self.assertIn("launcher_report_not_for_current_dashboard", report["freshness_warnings"])
            self.assertIn("启动器记录不属于当前页面", html)
            self.assertIn("历史 launcher report，仅供审计", html)
            self.assertIn("launcher_report_stale.json", html)
            self.assertNotIn("游戏内可尝试", html)
            self.assertNotIn("按执行清单去游戏内尝试", html)

    def test_launcher_report_unknown_hash_keeps_history_link_and_suppresses_action_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "demo"
            write_demo_doctor(output_dir)
            write_launcher_report(
                output_dir,
                {
                    "launcher_status": "executed",
                    "executed": True,
                    "warnings": [],
                    "blockers": [],
                    "output_history_json": str(output_dir / "launcher" / "history" / "launcher_report_unknown.json"),
                    "follow_up": {
                        "loaded": True,
                        "doctor_status": "ready_to_try",
                        "primary_next_action": "try_now",
                        "try_now_allowed": True,
                    },
                },
            )
            report = pipeline_tool.build_launcher_report_summary(output_dir)
            summary = dashboard_minimal_summary()
            summary["launcher_report"] = report

            html = dashboard_tool.render_html(summary)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report["launcher_report_freshness"], "unknown")
            self.assertIn("launcher_report_doctor_hash_missing", report["freshness_warnings"])
            self.assertIn("launcher report freshness 未知", html)
            self.assertIn("launcher_report_unknown.json", html)
            self.assertNotIn("游戏内可尝试", html)

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
                        "rank_sources": {
                            "character": {
                                "rank": "S",
                                "source": "visual_fallback",
                                "region": "character_rank",
                                "confidence": 0.91,
                            },
                            "equipment": {
                                "rank": "A",
                                "source": "ocr_or_text",
                                "region": "equipment_rank",
                            },
                        },
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
                    "safe_apply_status": "applied",
                    "review_apply_receipt_json": str(root / "review_apply_receipt.json"),
                    "review_apply_receipt_md": str(root / "review_apply_receipt.md"),
                    "review_log_json": str(root / "review_log.json"),
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
                    "decision_command": "python tools/probes/apply_review_decisions.py --normalized-dir data/probes/demo/normalized --decision-manifest data/probes/review_decisions.json --roster-dir data/probes/roster --preview-result data/probes/demo/review_preview/review_decision_preview.json --require-preview-ready",
                },
            }

            dashboard_tool.render_dashboard(summary, output)
            html = output.read_text(encoding="utf-8")

            self.assertIn("米游社练度识别体验台", html)
            self.assertIn("当前结论", html)
            self.assertIn("调试与产物明细", html)
            self.assertIn("parsed replay mode", html)
            self.assertIn("case_a", html)
            self.assertIn("星见雅", html)
            self.assertIn("角色评级", html)
            self.assertIn("音擎评级", html)
            self.assertIn("A/S 艺术字识别", html)
            self.assertIn("OCR/文本识别", html)
            self.assertIn("character_rank", html)
            self.assertIn("标准化结果", html)
            self.assertIn("复核页", html)
            self.assertIn("case_expected.json", html)
            self.assertIn("演示状态", html)
            self.assertIn("MISSING_EXPECTED", html)
            self.assertIn("Parse PASS", html)
            self.assertIn("Expected N/A", html)
            self.assertIn("Normalized Snapshot", html)
            self.assertIn("GENERATED", html)
            self.assertIn("Manual Review Gate", html)
            self.assertIn("REQUIRES_REVIEW", html)
            self.assertIn("不会自动写入正式数据", html)
            self.assertIn("下一步行动", html)
            self.assertIn("候选 ≠ 已拥有", html)
            self.assertIn("高优先级行动", html)
            self.assertIn("需补录/确认", html)
            self.assertIn("保值观察", html)
            self.assertIn("高保值行动", html)
            self.assertIn("低保值复核", html)
            self.assertIn("练度更新收件箱", html)
            self.assertIn("只有已确认角色库可以作为已拥有练度", html)
            self.assertIn("待确认快照", html)
            self.assertIn("已接收快照", html)
            self.assertIn("复核应用命令（确认后再复制）", html)
            self.assertIn("apply_review_decisions.py", html)
            self.assertIn("--preview-result", html)
            self.assertIn("review_apply_receipt.json", html)
            self.assertIn("review_apply_receipt.md", html)
            self.assertIn("安全应用", html)
            self.assertIn("applied", html)
            self.assertNotIn("safe apply</span>", html)
            self.assertIn("复核应用回执", html)
            self.assertIn("tier_snapshot", html)
            self.assertIn("Tier / 保值观察", html)
            self.assertIn("已有高保值", html)
            self.assertIn("观察候选", html)
            self.assertIn("已验证", html)
            self.assertIn("过期保值观察", html)
            self.assertIn("未验证保值观察", html)
            self.assertIn("tier_watchlist.json", html)
            self.assertIn("owned_high_value", html)
            self.assertIn("non_owned_watch_only", html)
            self.assertIn("不是最终抽取建议", html)
            self.assertIn("action_cards.json", html)
            self.assertIn("确认是否拥有 珂蕾妲", html)
            self.assertIn("高难配队候选", html)
            self.assertIn("可用队伍", html)
            self.assertIn("高保值可用队伍", html)
            self.assertIn("队伍保值", html)
            self.assertIn("需补录队伍", html)
            self.assertIn("候选队伍", html)
            self.assertIn("team_cards.json", html)
            self.assertIn("pending_snapshot", html)
            self.assertIn("catalog_candidate", html)
            self.assertIn("待确认快照 尚未进入 已确认角色库", html)
            self.assertIn("目录候选 不代表已拥有", html)
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
            self.assertIn("可信度", html)
            self.assertIn("来源状态", html)
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
            self.assertIn("变化报告", html)
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
            launcher_dir = output_dir / "launcher"
            launcher_dir.mkdir(parents=True)
            (launcher_dir / "launcher_report.json").write_text(
                json.dumps(
                    {
                        "schema_version": "p3.4-lite-doctor-launcher",
                        "launcher_status": "executed",
                        "executed": True,
                        "returncode": 0,
                        "command_script_resolved": str(PROJECT_ROOT / "tools" / "probes" / "run_demo_pipeline.py"),
                        "rerun_started_at": "2026-06-29T10:00:00+08:00",
                        "rerun_finished_at": "2026-06-29T10:00:02+08:00",
                        "warnings": [],
                        "blockers": [],
                        "output_json": str(launcher_dir / "launcher_report.json"),
                        "output_md": str(launcher_dir / "launcher_report.md"),
                        "output_history_json": str(launcher_dir / "history" / "launcher_report_20260629.json"),
                        "output_history_md": str(launcher_dir / "history" / "launcher_report_20260629.md"),
                        "follow_up": {
                            "loaded": True,
                            "doctor_status": "ready_to_try",
                            "primary_next_action": "try_now",
                            "try_now_allowed": True,
                            "strict_status": "trusted",
                            "updated_after_rerun": True,
                            "warnings": [],
                            "doctor_warnings": [],
                            "evidence_blockers": [],
                            "blocking_reasons": [],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            original_run_review = pipeline_tool.review_once.run_review

            def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("parsed-dir mode must not run OCR image review")

            pipeline_tool.review_once.run_review = fail_if_called
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
                pipeline_tool.review_once.run_review = original_run_review

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
            self.assertIn("demo_doctor", summary)
            self.assertIn("Demo Doctor", steps)
            self.assertIn("update_command", summary)
            self.assertEqual(summary["update_command"]["status"], "blocked")
            self.assertTrue(Path(summary["update_command"]["output_json"]).exists())
            self.assertIn("Update Command", steps)
            self.assertIn("launcher_report", summary)
            self.assertEqual(summary["launcher_report"]["launcher_status"], "executed")
            self.assertEqual(summary["launcher_report"]["launcher_report_freshness"], "unknown")
            self.assertIn("launcher_report_doctor_hash_missing", summary["launcher_report"]["freshness_warnings"])
            self.assertEqual(summary["launcher_report"]["follow_up"]["doctor_status"], "ready_to_try")
            self.assertTrue(Path(summary["demo_doctor"]["output_json"]).exists())
            self.assertTrue(Path(summary["dashboard_html"]).exists())
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")
            self.assertIn("当前状态诊断", dashboard_html)
            self.assertIn("本地更新命令", dashboard_html)
            self.assertIn("当前不可作为本地更新命令运行", dashboard_html)
            self.assertIn("启动器执行记录", dashboard_html)
            self.assertIn("launcher report freshness 未知", dashboard_html)
            self.assertIn("launcher_report_20260629.json", dashboard_html)
            self.assertNotIn("游戏内可尝试", dashboard_html)
            self.assertIn("parsed found", dashboard_html)
            self.assertIn("parsed used", dashboard_html)
            self.assertIn("不会自动写入正式数据", dashboard_html)
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
            self.assertEqual(summary["overall"]["hard_failure_count"], 1)
            self.assertEqual(summary["overall"]["review_failed_count"], 1)
            self.assertEqual(summary["overall"]["normalization_failed_count"], 1)
            self.assertEqual(pipeline_tool.exit_code_for_summary(summary), 3)
            steps = {item["name"]: item["status"] for item in summary["pipeline_steps"]}
            self.assertEqual(steps["OCR Review"], "FAIL")
            self.assertEqual(steps["Manual Review Gate"], "BLOCKED")
            output = root / "dashboard.html"
            dashboard_tool.render_dashboard(summary, output)
            html = output.read_text(encoding="utf-8")
            self.assertIn("本轮识别失败", html)
            self.assertIn("有 1 张图没有成功解析", html)
            self.assertIn("fresh/update 会返回非 0", html)

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

    def test_run_demo_pipeline_includes_plan_update_readiness_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "demo"
            readiness_dir = output_dir / "plan_update_readiness"
            readiness_dir.mkdir(parents=True)
            readiness_path = readiness_dir / "plan_update_readiness.json"
            readiness_md = readiness_dir / "plan_update_readiness.md"
            readiness_path.write_text(
                json.dumps(
                    {
                        "schema_version": "p4.4-plan-update-readiness",
                        "source_status": "needs_accepted_roster",
                        "warning": "缺少 accepted roster，本轮不能把 pending/demo snapshot 当作已拥有 box。",
                        "missing_blockers": ["accepted_roster"],
                        "items": [
                            {
                                "id": "accepted_roster",
                                "title": "已确认角色库",
                                "status": "missing",
                                "path": str(root / "roster" / "roster_index.json"),
                                "detail": "缺少 accepted roster。",
                            }
                        ],
                        "next_actions": ["先运行 MihoProbe.exe update --open。"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readiness_md.write_text("# readiness\n", encoding="utf-8")
            manifest_path = root / "empty_manifest.json"
            manifest_path.write_text(json.dumps({"cases": []}, ensure_ascii=False), encoding="utf-8")

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=None,
                manifest=manifest_path,
                output_dir=output_dir,
                roster_dir=root / "roster",
                open_dashboard=False,
            )

            self.assertIn("plan_update_readiness", summary)
            self.assertEqual(summary["plan_update_readiness"]["source_status"], "needs_accepted_roster")
            self.assertEqual(summary["plan_update_readiness"]["output_json"], str(readiness_path))
            self.assertEqual(summary["plan_update_readiness"]["output_md"], str(readiness_md))
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")
            self.assertIn("Plan Update 数据源", dashboard_html)
            self.assertIn("先补已确认角色库", dashboard_html)

    def test_run_demo_pipeline_includes_app_export_readiness_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "demo"
            workflow_dir = output_dir / "app_export_workflow"
            workflow_dir.mkdir(parents=True)
            workflow_json = workflow_dir / "miyoushe_export_workflow.json"
            workflow_html = workflow_dir / "miyoushe_export_workflow.html"
            calibration_template = workflow_dir / "miyoushe_app_export_calibration_template.json"
            workflow_json.write_text(
                json.dumps(
                    {
                        "workflow": {
                            "workflow_name": "米游社官方分享图一键更新练度",
                            "does_not": ["auto_login", "token_read", "cookie_read", "game_client_control"],
                            "operator_route": {
                                "current_route_status": "calibration_required",
                                "automation_status": "disabled_until_calibrated",
                                "next_command": "python tools/probes/window_screenshot_probe.py --window-title 米游社 --dry-run",
                                "manual_save_to_figs_step": "在米游社官方 UI 保存分享图到 figs。",
                                "update_command": r"dist\MihoProbe.exe update --open",
                                "review_gate": "Dashboard 人工复核通过后，才允许进入本地 accepted roster / 高难建议。",
                                "route_steps": [
                                    {
                                        "label": "1. 打开官方 APP",
                                        "status": "manual",
                                        "description": "用户手动打开已登录的米游社 APP。",
                                        "command": "",
                                    },
                                    {
                                        "label": "4. 本地更新 Dashboard",
                                        "status": "implemented",
                                        "description": "只处理本地官方分享图。",
                                        "command": r"dist\MihoProbe.exe update --open",
                                    },
                                ],
                            },
                        },
                        "validation": {
                            "status": "ready_for_calibration",
                            "warnings": ["4 navigation step(s) still need UIA selector calibration."],
                            "readiness_gate_count": 6,
                            "planned_step_count": 4,
                            "implemented_step_count": 1,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            workflow_html.write_text("<!doctype html><title>workflow</title>", encoding="utf-8")
            calibration_template.write_text(json.dumps({"schema_version": "p4.4-miyoushe-app-export-calibration"}, ensure_ascii=False), encoding="utf-8")
            manifest_path = root / "empty_manifest.json"
            manifest_path.write_text(json.dumps({"cases": []}, ensure_ascii=False), encoding="utf-8")

            summary = pipeline_tool.run_pipeline(
                images_dir=None,
                parsed_dir=None,
                manifest=manifest_path,
                output_dir=output_dir,
                roster_dir=root / "roster",
                open_dashboard=False,
            )

            self.assertIn("app_export_readiness", summary)
            self.assertEqual(summary["app_export_readiness"]["status"], "ready_for_calibration")
            self.assertEqual(summary["app_export_readiness"]["workflow_json"], str(workflow_json))
            self.assertEqual(summary["app_export_readiness"]["workflow_html"], str(workflow_html))
            self.assertEqual(summary["app_export_readiness"]["calibration_template_json"], str(calibration_template))
            dashboard_html = Path(summary["dashboard_html"]).read_text(encoding="utf-8")
            self.assertIn("一键更新练度准备状态", dashboard_html)
            self.assertIn("已沉淀路线，等待校准", dashboard_html)
            self.assertIn("校准清单状态", dashboard_html)
            self.assertIn("APP 导出校准清单", dashboard_html)

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
            self.assertIn("review_decision_preview", summary)
            self.assertTrue(Path(summary["review_decision_preview"]["output_json"]).exists())
            self.assertTrue(Path(summary["review_decision_preview"]["output_md"]).exists())
            self.assertIn("Review Decision Preview", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("review_apply", summary)
            self.assertEqual(summary["review_apply"]["apply_status"], "not_applied")
            self.assertIn("Review Apply Receipt", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("refresh_status", summary)
            self.assertEqual(summary["refresh_status"]["refresh_status"], "not_applied")
            self.assertTrue(Path(summary["refresh_status"]["output_json"]).exists())
            self.assertTrue(Path(summary["refresh_status"]["output_md"]).exists())
            self.assertIn("Refresh Status", {item["name"] for item in summary["pipeline_steps"]})
            self.assertIn("demo_doctor", summary)
            self.assertTrue(Path(summary["demo_doctor"]["output_json"]).exists())
            self.assertTrue(Path(summary["demo_doctor"]["output_md"]).exists())
            self.assertIn("Demo Doctor", {item["name"] for item in summary["pipeline_steps"]})
            self.assertEqual(summary["review_inbox"]["pending_count"], 1)
            self.assertEqual(summary["review_inbox"]["safe_apply_status"], "not_applied")
            self.assertEqual(summary["team_cards"]["summary"]["pending_snapshot_count"], 1)
            self.assertIn("当前状态诊断", dashboard_html)
            self.assertIn("今日作战简报", dashboard_html)
            self.assertIn("执行清单", dashboard_html)
            self.assertIn("复核决策必须先预览，再人工应用", dashboard_html)
            self.assertIn("复核命令（确认后再复制）", dashboard_html)
            self.assertIn("--require-preview-ready", dashboard_html)
            self.assertIn("先看这一块就够了", dashboard_html)
            self.assertIn("证据明细", dashboard_html)
            self.assertIn("培养优先级候选", dashboard_html)
            self.assertIn("下一步行动", dashboard_html)
            self.assertIn("高难配队候选", dashboard_html)
            self.assertIn("练度更新收件箱", dashboard_html)
            self.assertIn("Tier / 保值观察", dashboard_html)
            self.assertIn("tier_watchlist.json", dashboard_html)
            self.assertIn("保值观察", dashboard_html)
            self.assertIn("队伍保值", dashboard_html)
            self.assertIn("目录候选 不代表已拥有", dashboard_html)
            self.assertIn("待确认快照 尚未进入 已确认角色库", dashboard_html)
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
            self.assertIn("变化报告", dashboard_html)

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

    def test_run_demo_pipeline_image_mode_prints_rank_source_per_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "figs"
            output_dir = root / "demo"
            images_dir.mkdir()
            (images_dir / "a.jpg").write_bytes(b"image-a")
            original_process = pipeline_tool.process_image_case

            def fake_process_image_case(image_path, *, name, output_dir, expected_dir, engine, game, layout):  # noqa: ANN001, ANN003
                case = pipeline_tool.case_template(name)
                case["image"] = str(Path(image_path).resolve())
                case["character"] = {"name": "角色a", "level": "60", "rank": "A"}
                case["equipment"] = {"name": "音擎a", "level": "60", "rank": "S"}
                case["review_status"] = "PASS"
                case["rank_sources"] = {
                    "character": {"rank": "A", "source": "visual_fallback", "region": "character_rank"},
                    "equipment": {"rank": "S", "source": "ocr_or_text", "region": "equipment_rank"},
                }
                case["quality"] = {"requires_manual_review": False}
                return case

            pipeline_tool.process_image_case = fake_process_image_case
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    pipeline_tool.run_pipeline(
                        images_dir=images_dir,
                        parsed_dir=None,
                        manifest=None,
                        output_dir=output_dir,
                        state_file=root / "update_state.json",
                        roster_dir=root / "roster",
                        open_dashboard=False,
                    )
            finally:
                pipeline_tool.process_image_case = original_process

        log = output.getvalue()
        self.assertIn("[Miho Demo] OCR 1/1: rank source:", log)
        self.assertIn("角色=A source=visual_fallback region=character_rank", log)
        self.assertIn("音擎=S source=ocr_or_text region=equipment_rank", log)

    def test_run_demo_pipeline_image_mode_propagates_visual_rank_sources_from_review_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images_dir = root / "figs"
            output_dir = root / "demo"
            images_dir.mkdir()
            image_path = images_dir / "share.jpg"
            image_path.write_bytes(b"official-share-image")
            original_run_review = pipeline_tool.review_once.run_review

            def fake_run_review(*, image_path, output_dir, engine, lang, game, layout, write_crops, crop_output_dir):  # noqa: ANN001, ANN003
                parsed = parsed_json("可琳", image=str(Path(image_path).resolve()))
                parsed["metadata"]["visual_rank_fallback"] = [
                    {
                        "region": "character_rank",
                        "rank": "A",
                        "confidence": 0.91,
                        "reason": "purple_local_peak",
                        "method": "color_ratio_with_local_peak",
                    },
                    {
                        "region": "equipment_rank",
                        "rank": "S",
                        "confidence": 0.95,
                        "reason": "orange_global",
                        "method": "color_ratio_with_local_peak",
                    },
                ]
                parsed["extracted_draft"]["character"]["rank"] = field("A")
                parsed["extracted_draft"]["character"]["rank"]["source_region"] = "character_rank"
                parsed["extracted_draft"]["equipment"]["rank"] = field("S")
                parsed["extracted_draft"]["equipment"]["rank"]["source_region"] = "equipment_rank"
                parsed_path = Path(output_dir) / "share_parsed.json"
                markdown_path = Path(output_dir) / "share_parsed.md"
                review_html = Path(output_dir) / "share_review.html"
                overlay_png = Path(output_dir) / "share_overlay.png"
                parsed_path.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
                markdown_path.write_text("# parsed\n", encoding="utf-8")
                review_html.write_text("<html>review</html>", encoding="utf-8")
                overlay_png.write_bytes(b"png")
                return {
                    "json_path": str(parsed_path),
                    "markdown_path": str(markdown_path),
                    "review_html": str(review_html),
                    "overlay_png": str(overlay_png),
                    "review_status": "PASS",
                    "coverage_level": "medium",
                    "errors": [],
                }

            pipeline_tool.review_once.run_review = fake_run_review
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    summary = pipeline_tool.run_pipeline(
                        images_dir=images_dir,
                        parsed_dir=None,
                        manifest=None,
                        output_dir=output_dir,
                        state_file=root / "update_state.json",
                        roster_dir=root / "roster",
                        open_dashboard=False,
                    )
            finally:
                pipeline_tool.review_once.run_review = original_run_review

        self.assertEqual(summary["overall"]["case_count"], 1)
        rank_sources = summary["cases"][0]["rank_sources"]
        self.assertEqual(rank_sources["character"]["rank"], "A")
        self.assertEqual(rank_sources["character"]["source"], "visual_fallback")
        self.assertEqual(rank_sources["character"]["region"], "character_rank")
        self.assertEqual(rank_sources["character"]["confidence"], 0.91)
        self.assertEqual(rank_sources["equipment"]["rank"], "S")
        self.assertEqual(rank_sources["equipment"]["source"], "visual_fallback")
        self.assertEqual(rank_sources["equipment"]["region"], "equipment_rank")
        self.assertEqual(rank_sources["equipment"]["confidence"], 0.95)
        log = output.getvalue()
        self.assertIn("角色=A source=visual_fallback region=character_rank", log)
        self.assertIn("音擎=S source=visual_fallback region=equipment_rank", log)

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
