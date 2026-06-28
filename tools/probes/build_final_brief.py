#!/usr/bin/env python
"""Build a compact user-facing final brief from local demo artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.1-lite-final-brief"
MAX_READY_NOW_CARDS = 3


class FinalBriefError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FinalBriefError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FinalBriefError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise FinalBriefError(f"Expected JSON object: {path}")
    return data


def load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return load_json(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def short_hash(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    return text[:12] if len(text) > 12 else text


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_warnings(items: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def artifact_warnings(run_manifest: dict[str, Any] | None) -> list[str]:
    if not isinstance(run_manifest, dict):
        return ["缺少 run_manifest；无法确认本轮产物是否同批生成。"]
    status = run_manifest.get("artifact_status") if isinstance(run_manifest.get("artifact_status"), dict) else {}
    warnings: list[Any] = []
    if status.get("missing"):
        warnings.append(f"缺少输入产物：{', '.join(str(item) for item in as_list(status.get('missing')))}。")
    if status.get("stale_or_mismatched"):
        warnings.append(
            "产物可能不是同一批生成："
            + ", ".join(str(item) for item in as_list(status.get("stale_or_mismatched")))
            + "。"
        )
    warnings.extend(as_list(status.get("warnings")))
    if status.get("consistent") is False and not warnings:
        warnings.append("run_manifest 标记为不一致。")
    return unique_warnings(warnings)


def roster_character_count(roster_index: dict[str, Any] | None) -> int:
    if not isinstance(roster_index, dict):
        return 0
    return sum(1 for item in as_list(roster_index.get("characters")) if isinstance(item, dict) and item.get("name"))


def trusted_ready_plans(endgame_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(endgame_plan, dict):
        return []
    plans = []
    for item in as_list(endgame_plan.get("target_plans")):
        if not isinstance(item, dict):
            continue
        if item.get("plan_status") != "ready_now" or item.get("plan_trust_level") != "trusted":
            continue
        teams = item.get("team_candidates") if isinstance(item.get("team_candidates"), list) else []
        first_team = teams[0] if teams and isinstance(teams[0], dict) else {}
        members = first_team.get("members") if isinstance(first_team.get("members"), list) else []
        if not members:
            continue
        if any(
            isinstance(member, dict)
            and (member.get("source_class_effective") or member.get("source_class")) != "owned_snapshot"
            for member in members
        ):
            continue
        plans.append(item)
    return plans


def card(
    *,
    rank: int,
    card_type: str,
    title: str,
    reason: str,
    target: Any = None,
    character: Any = None,
    evidence: dict[str, Any] | None = None,
    command_hint: Any = None,
    warnings: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "rank": rank,
        "card_type": card_type,
        "title": title,
        "reason": reason,
        "target": target,
        "character": character,
        "evidence": evidence or {},
        "command_hint": command_hint,
        "warnings": unique_warnings(warnings or []),
    }


def data_warning_card(rank: int, warnings: list[str], run_manifest: Path | None) -> dict[str, Any]:
    return card(
        rank=rank,
        card_type="data_warning",
        title="先确认本轮数据一致性",
        reason="run_manifest 显示输入缺失、错批或无法确认；这里不会把方案当作可信 ready。",
        evidence={"artifact": str(run_manifest) if run_manifest else None},
        command_hint="重新运行 demo pipeline，或确认 run_manifest 中的输入产物来自同一批生成。",
        warnings=warnings,
    )


def try_now_card(rank: int, plan: dict[str, Any], endgame_plan_path: Path | None) -> dict[str, Any]:
    teams = plan.get("team_candidates") if isinstance(plan.get("team_candidates"), list) else []
    first_team = teams[0] if teams and isinstance(teams[0], dict) else {}
    members = first_team.get("members") if isinstance(first_team.get("members"), list) else []
    member_names = [str(member.get("character")) for member in members if isinstance(member, dict) and member.get("character")]
    evidence = plan.get("evidence") if isinstance(plan.get("evidence"), dict) else {}
    return card(
        rank=rank,
        card_type="try_now",
        title=f"可先尝试：{plan.get('target')}",
        reason=plan.get("recommended_line") or first_team.get("rank_reason") or "该目标有 trusted ready_now 本地队伍。",
        target=plan.get("target"),
        character="、".join(member_names),
        evidence={
            "source": evidence.get("target_source"),
            "hash": evidence.get("target_hash"),
            "artifact": str(endgame_plan_path) if endgame_plan_path else None,
        },
        command_hint="打开 Dashboard 的本期高难方案，按该队伍先试一次。",
        warnings=plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
    )


def review_snapshot_cards(rank: int, review_inbox: dict[str, Any] | None, review_inbox_path: Path | None) -> list[dict[str, Any]]:
    if not isinstance(review_inbox, dict):
        return []
    result = []
    command = review_inbox.get("decision_command")
    for item in as_list(review_inbox.get("pending")):
        if not isinstance(item, dict):
            continue
        character = item.get("character") or "未知角色"
        blockers = item.get("blockers") if isinstance(item.get("blockers"), list) else []
        result.append(
            card(
                rank=rank + len(result),
                card_type="review_snapshot",
                title=f"复核 {character} 的解析快照",
                reason="pending snapshot 尚未进入 accepted roster；确认前不能进入 try_now。",
                character=character,
                evidence={"source": item.get("review_html"), "artifact": str(review_inbox_path) if review_inbox_path else None},
                command_hint=command,
                warnings=blockers,
            )
        )
    return result


def record_character_cards(rank: int, endgame_plan: dict[str, Any] | None, endgame_plan_path: Path | None) -> list[dict[str, Any]]:
    if not isinstance(endgame_plan, dict):
        return []
    result = []
    for plan in as_list(endgame_plan.get("target_plans")):
        if not isinstance(plan, dict) or plan.get("plan_status") != "needs_recording":
            continue
        actions = [item for item in as_list(plan.get("next_actions")) if isinstance(item, dict)]
        record_actions = [item for item in actions if item.get("action_type") == "record_missing_character"] or actions[:1]
        for action in record_actions[:1]:
            character = action.get("character") or "待补录角色"
            result.append(
                card(
                    rank=rank + len(result),
                    card_type="record_character",
                    title=action.get("title") or f"补录 {character} 的官方分享图",
                    reason="该目标需要已拥有但缺练度快照的角色；先补录官方分享图再判断。",
                    target=plan.get("target"),
                    character=character,
                    evidence={"artifact": str(endgame_plan_path) if endgame_plan_path else None},
                    command_hint="用官方分享图流程补录该角色，再人工确认进入 accepted roster。",
                    warnings=plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
                )
            )
    return result


def watch_only_cards(rank: int, endgame_plan: dict[str, Any] | None, endgame_plan_path: Path | None) -> list[dict[str, Any]]:
    if not isinstance(endgame_plan, dict):
        return []
    result = []
    for plan in as_list(endgame_plan.get("target_plans")):
        if not isinstance(plan, dict) or plan.get("plan_status") != "watch_only":
            continue
        result.append(
            card(
                rank=rank + len(result),
                card_type="watch_only",
                title=f"仅观察：{plan.get('target')}",
                reason="watch_only 不是抽卡建议；catalog candidate 不能当作已拥有战力。",
                target=plan.get("target"),
                evidence={"artifact": str(endgame_plan_path) if endgame_plan_path else None},
                command_hint="只做观察或确认拥有状态，不生成抽卡建议。",
                warnings=as_list(plan.get("warnings")) + ["不是抽卡建议。"],
            )
        )
    return result


def status_from_cards(cards: list[dict[str, Any]], trusted_ready_count: int, data_warnings: list[str]) -> str:
    if data_warnings:
        return "needs_review"
    if trusted_ready_count > 0:
        return "ready"
    if cards:
        return "needs_review"
    return "blocked"


def render_markdown(brief: dict[str, Any]) -> str:
    lines = [
        "# 今日作战简报",
        "",
        "## 今天先做什么",
        "",
    ]
    cards = as_list(brief.get("top_cards"))
    if not cards:
        lines.append("- 暂无可执行事项；先补齐本地确认数据。")
    for item in cards:
        if not isinstance(item, dict):
            continue
        lines.append(f"- [{item.get('card_type')}] {item.get('title')}: {item.get('reason')}")
    lines.extend(["", "## Summary", ""])
    summary = brief.get("summary") if isinstance(brief.get("summary"), dict) else {}
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    red_flags = as_list(brief.get("red_flags"))
    if red_flags:
        lines.extend(["", "## Red Flags", ""])
        for item in red_flags:
            lines.append(f"- {item}")
    commands = as_list(brief.get("next_commands"))
    if commands:
        lines.extend(["", "## Next Commands", ""])
        for item in commands:
            lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def build_final_brief(
    *,
    output_dir: Path,
    run_manifest: Path | None = None,
    roster_index: Path | None = None,
    review_inbox: Path | None = None,
    roster_delta: Path | None = None,
    endgame_plan: Path | None = None,
    tier_watchlist: Path | None = None,
) -> dict[str, Any]:
    review_data = load_optional_json(review_inbox)
    if review_inbox is not None and review_data is None:
        raise FinalBriefError(f"review_inbox does not exist: {review_inbox}")
    manifest_data = load_optional_json(run_manifest)
    roster_data = load_optional_json(roster_index)
    delta_data = load_optional_json(roster_delta)
    endgame_data = load_optional_json(endgame_plan)
    tier_data = load_optional_json(tier_watchlist)

    manifest_warnings = artifact_warnings(manifest_data)
    ready_plans = trusted_ready_plans(endgame_data)
    endgame_summary = endgame_data.get("summary") if isinstance(endgame_data, dict) and isinstance(endgame_data.get("summary"), dict) else {}
    review_pending_count = int(review_data.get("pending_count") or 0) if isinstance(review_data, dict) else 0
    summary = {
        "accepted_character_count": roster_character_count(roster_data),
        "pending_review_count": review_pending_count,
        "ready_now_target_count": len(ready_plans),
        "needs_review_target_count": int(endgame_summary.get("needs_review_count") or 0),
        "needs_recording_target_count": int(endgame_summary.get("needs_recording_count") or 0),
        "watch_only_target_count": int(endgame_summary.get("watch_only_count") or 0),
        "trusted_plan_count": int(endgame_summary.get("trusted_plan_count") or len(ready_plans)),
        "warning_plan_count": int(endgame_summary.get("warning_plan_count") or 0),
        "roster_delta_change_count": len(as_list(delta_data.get("character_changes"))) if isinstance(delta_data, dict) else 0,
        "tier_watch_entry_count": len(as_list(tier_data.get("entries"))) if isinstance(tier_data, dict) else 0,
    }

    candidate_cards: list[dict[str, Any]] = []
    rank = 1
    if manifest_warnings:
        candidate_cards.append(data_warning_card(rank, manifest_warnings, run_manifest))
        rank += 1
    for plan in ready_plans[:MAX_READY_NOW_CARDS]:
        candidate_cards.append(try_now_card(rank, plan, endgame_plan))
        rank += 1
    for item in review_snapshot_cards(rank, review_data, review_inbox):
        candidate_cards.append(item)
        rank += 1
    for item in record_character_cards(rank, endgame_data, endgame_plan):
        candidate_cards.append(item)
        rank += 1
    for item in watch_only_cards(rank, endgame_data, endgame_plan):
        candidate_cards.append(item)
        rank += 1
    top_cards = candidate_cards
    for index, item in enumerate(top_cards, start=1):
        item["rank"] = index

    red_flags = unique_warnings(manifest_warnings + as_list(endgame_data.get("warnings") if isinstance(endgame_data, dict) else []))
    next_commands = []
    if isinstance(review_data, dict) and review_data.get("decision_command"):
        next_commands.append(str(review_data["decision_command"]))
    if manifest_warnings:
        next_commands.append("python tools/probes/run_demo_pipeline.py --manifest data/probes/demo_manifest.json --clean-demo")

    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "brief_status": status_from_cards(top_cards, len(ready_plans), manifest_warnings),
        "input": {
            "run_manifest": str(run_manifest) if run_manifest else None,
            "roster_index": str(roster_index) if roster_index else None,
            "review_inbox": str(review_inbox) if review_inbox else None,
            "roster_delta": str(roster_delta) if roster_delta else None,
            "endgame_plan": str(endgame_plan) if endgame_plan else None,
            "tier_watchlist": str(tier_watchlist) if tier_watchlist else None,
        },
        "summary": summary,
        "top_cards": top_cards,
        "red_flags": red_flags,
        "next_commands": next_commands,
        "warnings": red_flags,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "final_brief.json"
    md_path = output_dir / "final_brief.md"
    result["output_json"] = str(json_path)
    result["output_md"] = str(md_path)
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build local final demo brief.")
    parser.add_argument("--run-manifest", default=None, help="Optional run_manifest.json.")
    parser.add_argument("--roster-index", default=None, help="Optional accepted roster_index.json.")
    parser.add_argument("--review-inbox", required=True, help="review_inbox.json from demo pipeline.")
    parser.add_argument("--roster-delta", default=None, help="Optional roster_delta.json.")
    parser.add_argument("--endgame-plan", default=None, help="Optional endgame_plan.json.")
    parser.add_argument("--tier-watchlist", default=None, help="Optional tier_watchlist.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for final_brief.json/md.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_final_brief(
            run_manifest=resolve_path(args.run_manifest) if args.run_manifest else None,
            roster_index=resolve_path(args.roster_index) if args.roster_index else None,
            review_inbox=resolve_path(args.review_inbox),
            roster_delta=resolve_path(args.roster_delta) if args.roster_delta else None,
            endgame_plan=resolve_path(args.endgame_plan) if args.endgame_plan else None,
            tier_watchlist=resolve_path(args.tier_watchlist) if args.tier_watchlist else None,
            output_dir=resolve_path(args.output_dir),
        )
    except FinalBriefError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"brief_status: {result['brief_status']}")
    print(f"top_card_count: {len(result['top_cards'])}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
