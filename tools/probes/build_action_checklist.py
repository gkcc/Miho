#!/usr/bin/env python
"""Build an executable local checklist from final brief cards."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "p2.2-lite-action-checklist"
DECISION_TEMPLATE_SCHEMA = "p2.2-lite-review-decisions-template"
MAX_CHECKLIST_ITEMS = 5


class ActionChecklistError(RuntimeError):
    pass


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ActionChecklistError(f"JSON does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionChecklistError(f"Invalid JSON: {path}. Details: {exc}") from exc
    if not isinstance(data, dict):
        raise ActionChecklistError(f"Expected JSON object: {path}")
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


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def unique_strings(items: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def manifest_warnings(run_manifest: dict[str, Any] | None) -> list[str]:
    if not isinstance(run_manifest, dict):
        return []
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
    return unique_strings(warnings)


def pending_by_character(review_inbox: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result = {}
    if not isinstance(review_inbox, dict):
        return result
    for item in as_list(review_inbox.get("pending")):
        if isinstance(item, dict) and item.get("character"):
            result[str(item["character"])] = item
    return result


def review_template(review_inbox: dict[str, Any] | None, review_inbox_path: Path | None) -> dict[str, Any]:
    decisions = []
    if isinstance(review_inbox, dict):
        for item in as_list(review_inbox.get("pending")):
            if not isinstance(item, dict):
                continue
            decisions.append(
                {
                    "normalized_json": item.get("normalized_json"),
                    "decision": "pending",
                    "character": item.get("character"),
                    "review_html": item.get("review_html"),
                    "note": "",
                    "blockers": as_list(item.get("blockers")),
                }
            )
    return {
        "schema_version": DECISION_TEMPLATE_SCHEMA,
        "created_at": now_iso(),
        "source_review_inbox": str(review_inbox_path) if review_inbox_path else None,
        "decisions": decisions,
    }


def evidence_from_card(card: dict[str, Any], review_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence = dict(card.get("evidence")) if isinstance(card.get("evidence"), dict) else {}
    character = str(card.get("character") or "")
    pending = review_lookup.get(character)
    if pending:
        evidence.setdefault("review_html", pending.get("review_html"))
        evidence.setdefault("normalized_json", pending.get("normalized_json"))
    return {
        "artifact": evidence.get("artifact"),
        "review_html": evidence.get("review_html") or evidence.get("source"),
        "normalized_json": evidence.get("normalized_json"),
        "target_hash": evidence.get("hash") or evidence.get("target_hash"),
        "source": evidence.get("source"),
    }


def unsafe_try_now(card: dict[str, Any]) -> bool:
    blob = json.dumps(card, ensure_ascii=False).lower()
    return any(marker in blob for marker in ("pending_snapshot", "catalog_candidate", "catalog_owned_missing_snapshot"))


def item_from_card(
    rank: int,
    card: dict[str, Any],
    *,
    data_warning_present: bool,
    review_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    card_type = str(card.get("card_type") or "unknown")
    warnings = as_list(card.get("warnings"))
    status = "needs_review"
    if card_type == "data_warning":
        status = "blocked"
    elif card_type == "try_now":
        status = "ready"
        if data_warning_present:
            status = "blocked"
            warnings.append("blocked_by_data_warning")
        if unsafe_try_now(card):
            status = "blocked"
            warnings.append("pending/catalog 不得进入 ready try_now。")
    elif card_type == "watch_only":
        warnings.append("不是抽卡建议。")
    return {
        "rank": rank,
        "item_type": card_type,
        "status": status,
        "title": card.get("title"),
        "target": card.get("target"),
        "character": card.get("character"),
        "source_card_type": card_type,
        "evidence": evidence_from_card(card, review_lookup),
        "command_hint": card.get("command_hint"),
        "warnings": unique_strings(warnings),
    }


def checklist_status(items: list[dict[str, Any]], data_warning_present: bool) -> str:
    if data_warning_present:
        return "blocked"
    if any(item.get("status") == "needs_review" for item in items):
        return "needs_review"
    if any(item.get("status") == "blocked" for item in items):
        return "blocked"
    if any(item.get("status") == "ready" for item in items):
        return "ready"
    return "blocked"


def render_markdown(result: dict[str, Any]) -> str:
    lines = ["# 执行清单", "", "## 今天最多 5 件事", ""]
    items = as_list(result.get("items"))
    if not items:
        lines.append("- 暂无可执行事项。")
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(f"- [{item.get('status')}] {item.get('item_type')}: {item.get('title')}")
    lines.extend(["", "## Review Decision Template", ""])
    lines.append(f"- {result.get('review_decisions_template')}")
    warnings = as_list(result.get("warnings"))
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def build_action_checklist(
    *,
    final_brief: Path,
    output_dir: Path,
    review_inbox: Path | None = None,
    endgame_plan: Path | None = None,
    run_manifest: Path | None = None,
) -> dict[str, Any]:
    brief_data = load_json(final_brief)
    review_data = load_optional_json(review_inbox)
    endgame_data = load_optional_json(endgame_plan)
    manifest_data = load_optional_json(run_manifest)
    review_lookup = pending_by_character(review_data)
    run_warnings = manifest_warnings(manifest_data)
    warnings = unique_strings(as_list(brief_data.get("warnings")) + run_warnings)
    top_cards = [item for item in as_list(brief_data.get("top_cards")) if isinstance(item, dict)]
    data_warning_present = bool(run_warnings) or any(card.get("card_type") == "data_warning" for card in top_cards)
    if data_warning_present and not any(card.get("card_type") == "data_warning" for card in top_cards):
        top_cards.insert(
            0,
            {
                "card_type": "data_warning",
                "title": "先确认本轮数据一致性",
                "reason": "run_manifest 显示输入缺失、错批或无法确认；执行清单会阻断 try_now。",
                "warnings": warnings,
                "evidence": {"artifact": str(run_manifest) if run_manifest else None},
            },
        )
    items = [
        item_from_card(index, card, data_warning_present=data_warning_present, review_lookup=review_lookup)
        for index, card in enumerate(top_cards[:MAX_CHECKLIST_ITEMS], start=1)
    ]
    hidden_item_count = max(0, len(top_cards) - MAX_CHECKLIST_ITEMS)

    output_dir.mkdir(parents=True, exist_ok=True)
    template_path = output_dir / "review_decisions_template.json"
    checklist_path = output_dir / "action_checklist.json"
    markdown_path = output_dir / "action_checklist.md"
    template = review_template(review_data, review_inbox)
    write_json(template_path, template)
    result = {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_iso(),
        "checklist_status": checklist_status(items, data_warning_present),
        "input": {
            "final_brief": str(final_brief),
            "review_inbox": str(review_inbox) if review_inbox else None,
            "endgame_plan": str(endgame_plan) if endgame_plan else None,
            "run_manifest": str(run_manifest) if run_manifest else None,
        },
        "summary": {
            "item_count": len(items),
            "hidden_item_count": hidden_item_count,
            "ready_count": sum(1 for item in items if item.get("status") == "ready"),
            "needs_review_count": sum(1 for item in items if item.get("status") == "needs_review"),
            "blocked_count": sum(1 for item in items if item.get("status") == "blocked"),
            "review_decision_count": len(template["decisions"]),
        },
        "items": items,
        "hidden_item_count": hidden_item_count,
        "review_decisions_template": str(template_path),
        "output_json": str(checklist_path),
        "output_md": str(markdown_path),
        "warnings": warnings,
    }
    write_json(checklist_path, result)
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build local action checklist from final brief.")
    parser.add_argument("--final-brief", required=True, help="final_brief.json.")
    parser.add_argument("--review-inbox", default=None, help="Optional review_inbox.json.")
    parser.add_argument("--endgame-plan", default=None, help="Optional endgame_plan.json.")
    parser.add_argument("--run-manifest", default=None, help="Optional run_manifest.json.")
    parser.add_argument("--output-dir", required=True, help="Output directory for action_checklist artifacts.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        result = build_action_checklist(
            final_brief=resolve_path(args.final_brief),
            review_inbox=resolve_path(args.review_inbox) if args.review_inbox else None,
            endgame_plan=resolve_path(args.endgame_plan) if args.endgame_plan else None,
            run_manifest=resolve_path(args.run_manifest) if args.run_manifest else None,
            output_dir=resolve_path(args.output_dir),
        )
    except ActionChecklistError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"checklist_status: {result['checklist_status']}")
    print(f"item_count: {result['summary']['item_count']}")
    print(f"output_json: {result['output_json']}")
    print(f"output_md: {result['output_md']}")
    print(f"review_decisions_template: {result['review_decisions_template']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
