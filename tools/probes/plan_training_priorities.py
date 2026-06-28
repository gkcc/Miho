#!/usr/bin/env python
"""Generate a local P1.2 draft training priority report from normalized snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "probes" / "planner"


class PlannerError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PlannerError(f"JSON file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlannerError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise PlannerError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def field_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status") or "")
    return "ok" if value not in (None, "", []) else "missing"


def field_uncertain(value: Any) -> bool:
    return bool(value.get("uncertain")) if isinstance(value, dict) else False


def as_number(value: Any) -> float | None:
    raw = field_value(value)
    if raw in (None, "", []):
        return None
    text = str(raw).replace("%", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def field_trusted(value: Any) -> bool:
    return field_status(value) == "ok" and not field_uncertain(value)


def character_name(snapshot: dict[str, Any]) -> str:
    name = field_value(snapshot.get("character", {}).get("name"))
    return str(name) if name else "unknown_character"


def load_manifest_snapshots(manifest: Path) -> list[Path]:
    data = load_json(manifest)
    raw = data.get("snapshots")
    if not isinstance(raw, list):
        raise PlannerError("Snapshot manifest must contain a snapshots list")
    paths = []
    for item in raw:
        if isinstance(item, str):
            paths.append(resolve_path(item))
        elif isinstance(item, dict) and item.get("path"):
            paths.append(resolve_path(str(item["path"])))
        else:
            raise PlannerError("Each snapshot manifest item must be a path string or object with path")
    return paths


def load_targets(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data.get("targets"), list):
        raise PlannerError("Targets JSON must contain a targets list")
    return data


def load_history_index(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data.get("characters"), dict):
        raise PlannerError("History index JSON must contain a characters object")
    return data


def history_items_by_character(history_context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(history_context, dict):
        return {}
    items = history_context.get("items")
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        character = str(item.get("character") or "")
        if character:
            result[character] = item
    return result


def history_index_by_character(history_index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(history_index, dict):
        return {}
    characters = history_index.get("characters")
    if not isinstance(characters, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in characters.values():
        if not isinstance(entry, dict):
            continue
        character = str(entry.get("character") or "")
        if character:
            result[character] = entry
    return result


def history_for_character(
    name: str,
    *,
    history_context: dict[str, Any] | None = None,
    history_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context_item = history_items_by_character(history_context).get(name)
    index_item = history_index_by_character(history_index).get(name)
    if context_item:
        return {
            "tracked": True,
            "status": context_item.get("status") or "tracked",
            "recent_change_count": int(context_item.get("change_count") or 0),
            "recent_requires_review_change_count": int(context_item.get("requires_review_change_count") or 0),
            "current_snapshot": context_item.get("current_snapshot"),
            "previous_snapshot": context_item.get("previous_snapshot"),
            "diff_md": context_item.get("diff_md"),
            "last_seen_at": index_item.get("last_seen_at") if index_item else None,
        }
    if index_item:
        return {
            "tracked": True,
            "status": "indexed",
            "recent_change_count": 0,
            "recent_requires_review_change_count": 0,
            "current_snapshot": index_item.get("latest_snapshot"),
            "previous_snapshot": None,
            "diff_md": None,
            "last_seen_at": index_item.get("last_seen_at"),
        }
    return {
        "tracked": False,
        "status": "not_tracked",
        "recent_change_count": 0,
        "recent_requires_review_change_count": 0,
        "current_snapshot": None,
        "previous_snapshot": None,
        "diff_md": None,
        "last_seen_at": None,
    }


def match_targets(snapshot: dict[str, Any], targets: dict[str, Any]) -> list[dict[str, Any]]:
    name = character_name(snapshot)
    matched = []
    for target in targets.get("targets", []):
        if not isinstance(target, dict):
            continue
        preferred = target.get("preferred_characters")
        if isinstance(preferred, list) and name in {str(item) for item in preferred}:
            matched.append(target)
            continue
        templates = target.get("recommended_team_templates")
        if isinstance(templates, list):
            for template in templates:
                if isinstance(template, dict) and name in {str(item) for item in template.get("preferred_characters", [])}:
                    matched.append(target)
                    break
    return matched


def target_priority(targets: list[dict[str, Any]]) -> int:
    if not targets:
        return 1
    priority_map = {"high": 3, "medium": 2, "low": 1}
    return max(priority_map.get(str(target.get("priority") or "medium"), 2) for target in targets)


def target_names(targets: list[dict[str, Any]]) -> list[str]:
    names = []
    for target in targets:
        activity = target.get("activity_name") or target.get("goal_id") or "unknown_goal"
        tier = target.get("target_tier")
        names.append(f"{activity} {tier}".strip())
    return names


def minimums_for_targets(targets: list[dict[str, Any]], defaults: dict[str, Any]) -> dict[str, Any]:
    minimums = dict(defaults)
    for target in targets:
        raw = target.get("minimums")
        if isinstance(raw, dict):
            minimums.update(raw)
    return minimums


def add_gap(gaps: list[dict[str, Any]], *, kind: str, severity: int, action: str, reason: str, estimated_days: float, confidence: str) -> None:
    gaps.append(
        {
            "gap_type": kind,
            "severity": severity,
            "action": action,
            "reason": reason,
            "estimated_days": estimated_days,
            "confidence": confidence,
        }
    )


def skill_levels(snapshot: dict[str, Any]) -> list[float]:
    raw = snapshot.get("build_snapshot", {}).get("skill_levels", [])
    if not isinstance(raw, list):
        return []
    levels = []
    for item in raw:
        if isinstance(item, dict):
            level = as_number(item.get("level"))
            if level is not None:
                levels.append(level)
    return levels


def drive_disc_levels(snapshot: dict[str, Any]) -> list[float]:
    raw = snapshot.get("build_snapshot", {}).get("drive_discs", [])
    if not isinstance(raw, list):
        return []
    levels = []
    for item in raw:
        if isinstance(item, dict):
            level = as_number(item.get("level"))
            if level is not None:
                levels.append(level)
    return levels


def drive_disc_quality_gaps(snapshot: dict[str, Any]) -> tuple[int, int]:
    raw = snapshot.get("build_snapshot", {}).get("drive_discs", [])
    if not isinstance(raw, list):
        return 6, 6
    missing_main = 0
    missing_subs = 0
    if len(raw) < 6:
        missing_main += 6 - len(raw)
        missing_subs += 6 - len(raw)
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not field_trusted(item.get("main_stat")):
            missing_main += 1
        sub_stats = item.get("sub_stats")
        if not isinstance(sub_stats, list) or not sub_stats:
            missing_subs += 1
    return missing_main, missing_subs


def stat_gaps(snapshot: dict[str, Any], minimums: dict[str, Any]) -> list[dict[str, Any]]:
    stats = snapshot.get("build_snapshot", {}).get("stats", {})
    if not isinstance(stats, dict):
        return []
    gaps = []
    min_stats = minimums.get("stats")
    if not isinstance(min_stats, dict):
        return gaps
    for stat_name, min_value in min_stats.items():
        current = as_number(stats.get(str(stat_name)))
        required = as_number(min_value)
        if current is None or required is None:
            continue
        if current < required:
            gaps.append(
                {
                    "stat": str(stat_name),
                    "current": current,
                    "required": required,
                    "missing": round(required - current, 2),
                }
            )
    return gaps


def character_gaps(
    snapshot: dict[str, Any],
    targets: dict[str, Any],
    *,
    history_context: dict[str, Any] | None = None,
    history_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matched_targets = match_targets(snapshot, targets)
    defaults = targets.get("default_minimums", {}) if isinstance(targets.get("default_minimums"), dict) else {}
    minimums = minimums_for_targets(matched_targets, defaults)
    gaps: list[dict[str, Any]] = []
    character = snapshot.get("character", {})
    build = snapshot.get("build_snapshot", {})
    equipment = build.get("equipment", {}) if isinstance(build.get("equipment"), dict) else {}
    quality = snapshot.get("quality", {}) if isinstance(snapshot.get("quality"), dict) else {}
    blocker_count = len(quality.get("blockers", [])) if isinstance(quality.get("blockers"), list) else 0
    priority = target_priority(matched_targets)
    name = character_name(snapshot)
    history = history_for_character(name, history_context=history_context, history_index=history_index)

    if blocker_count:
        add_gap(
            gaps,
            kind="data_review",
            severity=4,
            action="先人工确认解析结果",
            reason=f"normalized quality 存在 {blocker_count} 个 blocker，不能把 OCR 结果直接当作养成规划依据。",
            estimated_days=0.0,
            confidence="high",
        )

    required_level = as_number(minimums.get("character_level"))
    current_level = as_number(character.get("level"))
    if required_level is not None and (current_level is None or current_level < required_level):
        missing = required_level if current_level is None else required_level - current_level
        add_gap(
            gaps,
            kind="character_level",
            severity=3 + priority,
            action=f"角色等级提升到 {int(required_level)}",
            reason=f"当前等级 {current_level if current_level is not None else '缺失'}，目标需要 {int(required_level)}。",
            estimated_days=max(1.0, round(missing / 10, 1)),
            confidence="medium" if current_level is not None else "low",
        )

    required_equipment = as_number(minimums.get("equipment_level"))
    current_equipment = as_number(equipment.get("level"))
    if required_equipment is not None and (current_equipment is None or current_equipment < required_equipment):
        missing = required_equipment if current_equipment is None else required_equipment - current_equipment
        add_gap(
            gaps,
            kind="equipment_level",
            severity=2 + priority,
            action=f"音擎等级提升到 {int(required_equipment)}",
            reason=f"当前音擎等级 {current_equipment if current_equipment is not None else '缺失'}，目标需要 {int(required_equipment)}。",
            estimated_days=max(1.0, round(missing / 15, 1)),
            confidence="medium" if current_equipment is not None else "low",
        )

    required_skill = as_number(minimums.get("skill_level"))
    levels = skill_levels(snapshot)
    low_skill_count = sum(1 for level in levels if required_skill is not None and level < required_skill)
    if required_skill is not None and low_skill_count:
        add_gap(
            gaps,
            kind="skill_level",
            severity=2 + priority,
            action=f"补关键技能到 {int(required_skill)} 左右",
            reason=f"{low_skill_count} 个技能低于目标线 {int(required_skill)}；优先补主输出或关键辅助技能。",
            estimated_days=round(low_skill_count * 0.5, 1),
            confidence="medium",
        )

    required_disc = as_number(minimums.get("drive_disc_level"))
    disc_levels = drive_disc_levels(snapshot)
    low_disc_count = sum(1 for level in disc_levels if required_disc is not None and level < required_disc)
    if required_disc is not None and low_disc_count:
        add_gap(
            gaps,
            kind="drive_disc_level",
            severity=1 + priority,
            action=f"驱动盘等级补到 +{int(required_disc)}",
            reason=f"{low_disc_count} 个驱动盘低于 +{int(required_disc)}，属于低成本补强项。",
            estimated_days=round(low_disc_count * 0.3, 1),
            confidence="medium",
        )

    missing_main, missing_subs = drive_disc_quality_gaps(snapshot)
    if missing_main or missing_subs >= 3:
        add_gap(
            gaps,
            kind="drive_disc_quality",
            severity=2 + priority,
            action="确认驱动盘主词条和副词条",
            reason=f"主词条不可信 {missing_main} 个，副词条缺失 {missing_subs} 个；先确认再决定是否刷盘。",
            estimated_days=0.0,
            confidence="high",
        )

    for gap in stat_gaps(snapshot, minimums):
        add_gap(
            gaps,
            kind=f"stat_{gap['stat']}",
            severity=2 + priority,
            action=f"补 {gap['stat']} 到 {gap['required']}",
            reason=f"当前 {gap['stat']}={gap['current']}，目标线 {gap['required']}，缺口 {gap['missing']}。",
            estimated_days=1.0,
            confidence="low",
        )

    return {
        "character": name,
        "matched_targets": target_names(matched_targets),
        "target_priority": priority,
        "quality_blockers": quality.get("blockers", []) if isinstance(quality.get("blockers"), list) else [],
        "history": history,
        "gaps": sorted(gaps, key=lambda item: (-int(item["severity"]), str(item["gap_type"]))),
    }


def plan_items(character_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for report in character_reports:
        character = report["character"]
        matched_targets = report.get("matched_targets", [])
        target_label = "、".join(matched_targets) if matched_targets else "长期通用练度"
        history = report.get("history", {}) if isinstance(report.get("history"), dict) else {}
        recent_change_count = int(history.get("recent_change_count") or 0)
        continuity_bonus = min(3, recent_change_count)
        for gap in report.get("gaps", []):
            score = int(gap["severity"]) * 10 + int(report.get("target_priority", 1))
            if gap["gap_type"] == "data_review":
                score += 8
                item_bonus = 0
                reason = gap["reason"]
            else:
                item_bonus = continuity_bonus
                score += item_bonus
                reason = gap["reason"]
                if item_bonus:
                    reason = f"{reason} 历史快照显示近期已有 {recent_change_count} 项变化，适合延续投入。"
            items.append(
                {
                    "priority_score": score,
                    "character": character,
                    "target": target_label,
                    "gap_type": gap["gap_type"],
                    "action": gap["action"],
                    "reason": reason,
                    "estimated_days": gap["estimated_days"],
                    "confidence": gap["confidence"],
                    "continuity_bonus": item_bonus,
                    "recent_change_count": recent_change_count,
                    "recent_diff_md": history.get("diff_md"),
                }
            )
    items.sort(key=lambda item: (-int(item["priority_score"]), str(item["character"]), str(item["gap_type"])))
    for index, item in enumerate(items, start=1):
        item["priority_rank"] = index
    return items


def build_warnings(targets: dict[str, Any], snapshots: list[dict[str, Any]]) -> list[str]:
    warnings = []
    source = targets.get("source") if isinstance(targets.get("source"), dict) else {}
    source_type = source.get("type")
    if source_type not in {"official_current", "official_snapshot"}:
        warnings.append("终局目标来自本地配置或 mock，不代表当前线上高难；后续需要接官方公告/活动数据源。")
    if any(snapshot.get("quality", {}).get("requires_manual_review") for snapshot in snapshots if isinstance(snapshot.get("quality"), dict)):
        warnings.append("存在 requires_manual_review 的 normalized snapshot，规划建议只能作为人工确认前的候选。")
    return warnings


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 本地培养优先级报告",
        "",
        "## 输入",
        f"- game: {report.get('game') or ''}",
        f"- snapshot_count: {len(report.get('snapshots', []))}",
        f"- target_source: {report.get('target_source', {}).get('type') or ''}",
        "",
    ]
    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    lines.extend(["## 优先级", "", "| rank | character | target | action | reason | days | confidence |", "|---|---|---|---|---|---:|---|"])
    for item in report.get("plan_items", []):
        lines.append(
            "| {rank} | {character} | {target} | {action} | {reason} | {days} | {confidence} |".format(
                rank=item["priority_rank"],
                character=item["character"],
                target=item["target"],
                action=item["action"],
                reason=item["reason"],
                days=item["estimated_days"],
                confidence=item["confidence"],
            )
        )
    lines.extend(["", "## 角色缺口", ""])
    for character in report.get("characters", []):
        lines.append(f"### {character['character']}")
        targets = "、".join(character.get("matched_targets", [])) or "长期通用练度"
        lines.append(f"- matched_targets: {targets}")
        blockers = character.get("quality_blockers", [])
        if blockers:
            lines.append(f"- quality_blockers: {'; '.join(blockers)}")
        history = character.get("history", {}) if isinstance(character.get("history"), dict) else {}
        if history.get("tracked"):
            lines.append(
                "- history: status={status}, recent_change_count={changes}, recent_requires_review_change_count={review}".format(
                    status=history.get("status"),
                    changes=history.get("recent_change_count", 0),
                    review=history.get("recent_requires_review_change_count", 0),
                )
            )
        for gap in character.get("gaps", []):
            lines.append(f"- [{gap['gap_type']}] {gap['action']}：{gap['reason']}")
        lines.append("")
    return "\n".join(lines)


def generate_report(
    snapshot_paths: list[Path],
    targets_path: Path,
    output_dir: Path,
    *,
    history_context: dict[str, Any] | None = None,
    history_index: Path | None = None,
) -> dict[str, Any]:
    if not snapshot_paths:
        raise PlannerError("At least one normalized snapshot is required")
    snapshots = [load_json(path) for path in snapshot_paths]
    targets = load_targets(targets_path)
    loaded_history_index = load_history_index(history_index) if history_index else None
    characters = [
        character_gaps(snapshot, targets, history_context=history_context, history_index=loaded_history_index)
        for snapshot in snapshots
    ]
    report = {
        "schema_version": "p1.2-planner-draft",
        "created_at": now_iso(),
        "game": targets.get("game") or snapshots[0].get("game"),
        "input": {
            "snapshots": [str(path) for path in snapshot_paths],
            "targets": str(targets_path),
            "history_index": str(history_index) if history_index else None,
        },
        "target_source": targets.get("source", {}),
        "snapshots": [
            {
                "character": character_name(snapshot),
                "source_image": snapshot.get("source", {}).get("image") if isinstance(snapshot.get("source"), dict) else None,
                "review_status": snapshot.get("source", {}).get("review_status") if isinstance(snapshot.get("source"), dict) else None,
                "coverage_level": snapshot.get("source", {}).get("coverage_level") if isinstance(snapshot.get("source"), dict) else None,
            }
            for snapshot in snapshots
        ],
        "characters": characters,
        "plan_items": plan_items(characters),
        "history_context": {
            "available": bool(history_context or loaded_history_index),
            "character_count": sum(1 for item in characters if item.get("history", {}).get("tracked")),
        },
        "warnings": build_warnings(targets, snapshots),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "training_priority_report.json"
    md_path = output_dir / "training_priority_report.md"
    write_json(json_path, report)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["output_json"] = str(json_path)
    report["output_md"] = str(md_path)
    write_json(json_path, report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a local training priority report from normalized snapshots.")
    parser.add_argument("--snapshot", action="append", default=[], help="Normalized snapshot JSON. Can be repeated.")
    parser.add_argument("--snapshot-manifest", default=None, help="JSON manifest containing a snapshots list.")
    parser.add_argument("--targets", required=True, help="Local endgame target configuration JSON.")
    parser.add_argument("--history-index", default=None, help="Optional snapshot_history/index.json for long-term continuity context.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory. Default: data/probes/planner.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        snapshot_paths = [resolve_path(value) for value in args.snapshot]
        if args.snapshot_manifest:
            snapshot_paths.extend(load_manifest_snapshots(resolve_path(args.snapshot_manifest)))
        report = generate_report(
            snapshot_paths,
            resolve_path(args.targets),
            resolve_path(args.output_dir),
            history_index=resolve_path(args.history_index) if args.history_index else None,
        )
    except PlannerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"plan_item_count: {len(report['plan_items'])}")
    print(f"output_json: {report['output_json']}")
    print(f"output_md: {report['output_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
