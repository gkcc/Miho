from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from hsr_endgame_exporter.normalize import normalize_character_id, parse_percent

from .box import load_config
from .evidence import (
    CONFIDENCE_ORDER,
    EvidencePool,
    build_evidence_pool,
    canonical_slug,
    load_name_index,
    load_owned_slugs,
    load_planned_slugs_from_banner_plan,
)


@dataclass(frozen=True)
class PullValueCard:
    slug: str
    name_cn: str
    candidate_type: str
    status: str
    pull_value: str
    stage_recommendation: dict[str, str]
    history_summary: str
    global_usage_summary: str
    team_coverage_summary: str
    mechanism_review_summary: str
    mechanism_notes: dict[str, Any]
    mechanism_summary: str
    replacement_risk: str
    decision_basis: tuple[str, ...]
    risk_notes: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def write_pull_value_report(
    data_dir: str | Path,
    *,
    box_path: str | Path,
    plan_path: str | Path | None = None,
    planned_slugs: Iterable[str] = (),
    statuses: Sequence[str] = ("next",),
    mechanism_notes_dir: str | Path | None = None,
    output_path: str | Path,
) -> dict[str, Any]:
    result = build_pull_value_cards(
        data_dir,
        box_path=box_path,
        plan_path=plan_path,
        planned_slugs=planned_slugs,
        statuses=statuses,
        mechanism_notes_dir=mechanism_notes_dir,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_pull_value_report(result), encoding="utf-8")
    return result


def write_gpt_review_packet(
    data_dir: str | Path,
    *,
    box_path: str | Path,
    plan_path: str | Path | None = None,
    planned_slugs: Iterable[str] = (),
    statuses: Sequence[str] = ("next",),
    mechanism_notes_dir: str | Path | None = None,
    output_path: str | Path,
) -> dict[str, Any]:
    result = build_pull_value_cards(
        data_dir,
        box_path=box_path,
        plan_path=plan_path,
        planned_slugs=planned_slugs,
        statuses=statuses,
        mechanism_notes_dir=mechanism_notes_dir,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_gpt_review_packet(result), encoding="utf-8")
    return result


def build_pull_value_cards(
    data_dir: str | Path,
    *,
    box_path: str | Path,
    plan_path: str | Path | None = None,
    planned_slugs: Iterable[str] = (),
    statuses: Sequence[str] = ("next",),
    mechanism_notes_dir: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(data_dir)
    names = load_name_index(out)
    owned = load_owned_slugs(box_path, names)
    candidates = _load_candidates(plan_path, statuses=statuses, names=names) if plan_path else []
    explicit_slugs = [canonical_slug(slug, names) for slug in planned_slugs if canonical_slug(slug, names)]
    for slug in explicit_slugs:
        if slug not in {candidate["slug"] for candidate in candidates}:
            candidates.append({"slug": slug, "status": "planned", "analysis_tags": [], "banner_role": "planned"})
    planned = list(dict.fromkeys([candidate["slug"] for candidate in candidates] + explicit_slugs))
    current_pool = build_evidence_pool(out, owned_slugs=owned, planned_slugs=[], scenario="current_box")
    target_pool = build_evidence_pool(out, owned_slugs=owned, planned_slugs=planned, scenario="target_box")
    usage_rows = _read_csv(out / "character_usage_long.csv")
    tier_rows = _read_csv(out / "prydwen_tier_current.csv")
    tier_index = _tier_index(tier_rows)
    mechanism_notes = load_mechanism_notes(
        mechanism_notes_dir or _default_mechanism_notes_dir(plan_path),
        candidates=[candidate["slug"] for candidate in candidates],
    )
    cards = [
        _build_card(
            candidate,
            names=names.names_cn,
            owned=owned,
            current_pool=current_pool,
            target_pool=target_pool,
            usage_rows=usage_rows,
            tier_index=tier_index,
            mechanism_notes=mechanism_notes,
        )
        for candidate in candidates
    ]
    cards.sort(key=lambda card: (_value_sort_key(card.pull_value), card.slug))
    return {
        "summary": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "data_dir": str(out),
            "box_path": str(box_path),
            "plan_path": str(plan_path or ""),
            "candidate_count": len(cards),
            "planned_slugs": planned,
            "current_coverage_records": len(current_pool.records),
            "target_coverage_records": len(target_pool.records),
            "mechanism_notes_dir": str(mechanism_notes_dir or _default_mechanism_notes_dir(plan_path) or ""),
        },
        "cards": cards,
    }


def load_mechanism_notes(notes_dir: str | Path | None, *, candidates: Iterable[str] = ()) -> dict[str, dict[str, Any]]:
    if not notes_dir:
        return {}
    root = Path(notes_dir)
    if not root.exists():
        return {}
    wanted = {normalize_character_id(slug) for slug in candidates if normalize_character_id(slug)}
    output: dict[str, dict[str, Any]] = {}
    paths = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")) + sorted(root.glob("*.json"))
    for path in paths:
        slug = normalize_character_id(path.stem)
        if wanted and slug not in wanted:
            continue
        data = load_config(path)
        output[slug] = data
    return output


def format_pull_value_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    cards: list[PullValueCard] = result["cards"]
    lines = [
        "# 绝区零 Pull Value Report",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 数据目录：`{summary['data_dir']}`",
        f"- Box：`{summary['box_path']}`",
        f"- 卡池计划：`{summary['plan_path'] or '-'}`",
        f"- 机制笔记：`{summary.get('mechanism_notes_dir') or '-'}`",
        f"- 候选角色：{summary['candidate_count']}；planned_slugs：{', '.join(summary['planned_slugs']) or 'none'}",
        f"- current coverage records：{summary['current_coverage_records']}；target coverage records：{summary['target_coverage_records']}",
        "",
        "## 口径",
        "",
        "- 复刻角色：按历史走势、全局出场、队伍覆盖、T 榜定位和 X+X 档位必要性评估。",
        "- 新角色：按机制信息完整度、拼图关系、售后确定性和替代风险评估；没有历史队伍记录是未实测状态，不作为负面扣分。",
        "- target coverage 只说明加入计划角色后的队伍覆盖，不单独决定抽取价值。",
        "- mechanism_review 来自 `configs/zzz_mechanism_notes/*.yaml`，用于判断 0+0、0+1、1+0、1+1、2+1 等档位断点。",
        "- 队伍证据只引用 A / B+ / B / B- 聚合记录；C 只作为风险。",
        "",
        "## 总览",
        "",
        "| character | type | pull_value | recommended_stage | acceptable_stage | unresolved_stage | stage_confidence | not_recommended_stage | missing_data | evidence_ids | key_basis | risk |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for card in cards:
        stage = card.stage_recommendation
        lines.append(
            "| {name} | {type} | {value} | {recommended} | {acceptable} | {unresolved} | {confidence} | {not_recommended} | {missing} | {evidence} | {basis} | {risk} |".format(
                name=_md(f"{card.name_cn} `{card.slug}`"),
                type=_md(card.candidate_type),
                value=_md(card.pull_value),
                recommended=_md(stage.get("recommended_stage", "-")),
                acceptable=_md(stage.get("acceptable_stage", "-")),
                unresolved=_md(stage.get("unresolved_stage", "-")),
                confidence=_md(stage.get("stage_confidence", "-")),
                not_recommended=_md(stage.get("not_recommended_stage", "-")),
                missing=_md(stage.get("missing_data", "-")),
                evidence=_md(", ".join(card.evidence_ids) or "-"),
                basis=_md("；".join(card.decision_basis[:3]) or "-"),
                risk=_md("；".join(card.risk_notes[:3]) or "无"),
            )
        )
    lines.extend(["", "## 角色明细", ""])
    for card in cards:
        lines.extend(_card_lines(card))
    lines.extend(
        [
            "## 本地 GPT 评判接入状态",
            "",
            "- 当前报告由本地确定性规则生成，可离线复现。",
            "- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。",
            "- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。",
            "",
        ]
    )
    return "\n".join(lines)


def format_gpt_review_packet(result: dict[str, Any]) -> str:
    summary = result["summary"]
    cards: list[PullValueCard] = result["cards"]
    payload = {
        "summary": summary,
        "candidates": [
            {
                "slug": card.slug,
                "name_cn": card.name_cn,
                "candidate_type": card.candidate_type,
                "status": card.status,
                "local_rule_pull_value": card.pull_value,
                "stage_recommendation": card.stage_recommendation,
                "history_summary": card.history_summary,
                "global_usage_summary": card.global_usage_summary,
                "team_coverage_summary": card.team_coverage_summary,
                "mechanism_review_summary": card.mechanism_review_summary,
                "mechanism_notes": card.mechanism_notes,
                "mechanism_summary": card.mechanism_summary,
                "replacement_risk": card.replacement_risk,
                "decision_basis": list(card.decision_basis),
                "risk_notes": list(card.risk_notes),
                "evidence_ids": list(card.evidence_ids),
            }
            for card in cards
        ],
    }
    lines = [
        "# GPT Pull Reviewer Packet",
        "",
        "## 使用方式",
        "",
        "把本文件交给 Codex/GPT，要求它基于证据重新评审每个候选角色的 X+X 档位。",
        "这是无 API key 的交互版：本地负责自动更新数据和证据包，GPT 评判由你登录后发起。",
        "",
        "## 评审规则",
        "",
        "- 不要只按 target coverage 定性；复刻角色必须同时看历史走势、全局出场、T 榜定位、current/target 覆盖和 X+X 必要性。",
        "- 必须把 historical_usage、target_coverage、mechanism_review 三类证据分开列出，再综合判断。",
        "- 新角色没有历史队伍记录只能标记为未实测，不能作为负面扣分。",
        "- C 档或 theoretical-only 不能作为抽取/档位主依据。",
        "- sentinel 分数不能当真实表现。",
        "- 输出每个角色的 recommended_stage、unresolved_stage、stage_confidence、not_recommended_stage、理由、反证、需要等待的数据，以及是否建议立刻抽。",
        "",
        "## 建议提问",
        "",
        "请读取这个 packet，按长期 auto 高难奖励目标，评审每个候选角色应该抽到 X+X。输出：结论表、每人证据链、风险、需要等的数据。",
        "",
        "## Evidence Payload",
        "",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 相关文件",
        "",
        f"- pull value reports: `{Path(summary['data_dir']) / 'current_pull_value_report.md'}` / `{Path(summary['data_dir']) / 'next_pull_value_report.md'}`",
        f"- current coverage: `{Path(summary['data_dir']) / 'current_box_team_coverage.md'}`",
        f"- target coverage: `{Path(summary['data_dir']) / 'target_box_team_coverage.md'}`",
        f"- team signature aggregates: `{Path(summary['data_dir']) / 'team_signature_aggregates.csv'}`",
        "",
    ]
    return "\n".join(lines)


def _build_card(
    candidate: dict[str, Any],
    *,
    names: dict[str, str],
    owned: set[str],
    current_pool: EvidencePool,
    target_pool: EvidencePool,
    usage_rows: list[dict[str, Any]],
    tier_index: dict[str, dict[str, Any]],
    mechanism_notes: dict[str, dict[str, Any]],
) -> PullValueCard:
    slug = candidate["slug"]
    candidate_type = _candidate_type(candidate, slug, usage_rows, tier_index)
    usage = _usage_summary(slug, usage_rows)
    tier = tier_index.get(slug, {})
    mechanism = mechanism_notes.get(slug, {})
    current_records = _records_for_slug(current_pool, slug)
    target_records = _records_for_slug(target_pool, slug)
    dependent_records = [record for record in target_records if slug in record.plan_dependency]
    evidence_ids = tuple(record.evidence_id for record in _top_records(dependent_records or target_records))
    coverage_summary = _coverage_text(current_records, target_records, dependent_records)
    if candidate_type == "new":
        pull_value = "等实测"
        stage = _stage_from_mechanism(candidate_type, mechanism)
        basis = [
            "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
            _mechanism_text(candidate, tier, mechanism),
            "先验证是否补当前 Box 拼图，还是要求后续售后队友",
        ]
        risks = [
            _missing_mechanism_data(mechanism) or "机制、倍率、专属收益和售后环境尚未落地",
            "替代风险无法从当前历史数据判断",
        ]
    else:
        pull_value, stage, basis, risks = _rerun_value(candidate, usage, tier, current_records, target_records, dependent_records, slug in owned, mechanism)
    return PullValueCard(
        slug=slug,
        name_cn=str(candidate.get("name_cn") or names.get(slug) or tier.get("character_name_cn") or slug),
        candidate_type=candidate_type,
        status=str(candidate.get("status") or ""),
        pull_value=pull_value,
        stage_recommendation=stage,
        history_summary=_history_text(usage),
        global_usage_summary=_global_usage_text(usage),
        team_coverage_summary=coverage_summary,
        mechanism_review_summary=_mechanism_review_text(mechanism),
        mechanism_notes=dict(mechanism) if isinstance(mechanism, dict) else {},
        mechanism_summary=_mechanism_text(candidate, tier, mechanism),
        replacement_risk=_replacement_text(candidate, tier, owned, mechanism),
        decision_basis=tuple(basis),
        risk_notes=tuple(risks),
        evidence_ids=evidence_ids,
    )


def _rerun_value(
    candidate: dict[str, Any],
    usage: dict[str, Any],
    tier: dict[str, Any],
    current_records: list[Any],
    target_records: list[Any],
    dependent_records: list[Any],
    owned: bool,
    mechanism: dict[str, Any],
) -> tuple[str, dict[str, str], list[str], list[str]]:
    best_rating = _float(tier.get("best_rating"))
    avg_last3 = _float(usage.get("best_avg_last3"))
    usage_points = int(usage.get("points") or 0)
    strong_target = sum(1 for record in dependent_records if record.confidence in {"A", "B+"})
    good_target = sum(1 for record in dependent_records if record.confidence in {"A", "B+", "B"})
    basis = []
    risks = []
    if best_rating:
        basis.append(f"T 榜最好评级 {tier.get('best_tier') or '-'} / rating {best_rating:g}")
    if usage_points:
        basis.append(f"历史出场点 {usage_points}，近三期最高均值 {avg_last3:g}%")
    if dependent_records:
        basis.append(f"目标 Box 新增依赖队伍 {len(dependent_records)} 条，其中 A/B+ {strong_target} 条、A/B+/B {good_target} 条")
    elif target_records:
        basis.append(f"目标 Box 可组历史队伍 {len(target_records)} 条，但不是该角色作为新增依赖")
    else:
        risks.append("目标 Box 暂无可组历史队伍证据")
    if current_records:
        basis.append(f"当前 Box 已有相关队伍 {len(current_records)} 条")
    if best_rating >= 11 and avg_last3 >= 30 and usage_points >= 6:
        pull_value = "高"
    elif best_rating >= 10 and avg_last3 >= 10:
        pull_value = "中高"
    elif usage_points > 0:
        pull_value = "中"
    else:
        pull_value = "等实测"
        risks.append("复刻角色在本地历史样本不足")
    stage = _stage_from_mechanism("rerun", mechanism, role=str(tier.get("role_group_cn") or candidate.get("role_group_cn") or ""))
    basis.append("mechanism_review：" + _mechanism_review_text(mechanism))
    if owned:
        risks.append("已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序")
    if dependent_records and not current_records:
        risks.append("新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性")
    return pull_value, stage, basis, risks


def _load_candidates(plan_path: str | Path, *, statuses: Sequence[str], names: Any) -> list[dict[str, Any]]:
    data = load_config(plan_path)
    status_set = {str(status).strip().lower() for status in statuses if str(status).strip()}
    output: list[dict[str, Any]] = []
    for phase in data.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        status = str(phase.get("status") or "").strip().lower()
        if status_set and status not in status_set:
            continue
        for character in phase.get("characters") or []:
            if not isinstance(character, dict):
                continue
            slug = canonical_slug(str(character.get("slug") or ""), names)
            if not slug:
                continue
            output.append(
                {
                    **character,
                    "slug": slug,
                    "status": status,
                    "phase_title": phase.get("title", ""),
                    "phase_subtitle": phase.get("subtitle", ""),
                }
            )
    return output


def _usage_summary(slug: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [row for row in rows if normalize_character_id(row.get("character_slug")) == slug and str(row.get("sub_mode") or "") == "all"]
    by_mode: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in matched:
        app = parse_percent(row.get("app_rate"))
        if app is None:
            continue
        by_mode[str(row.get("mode") or "")].append((str(row.get("collect_date") or ""), app))
    modes = {}
    for mode, points in by_mode.items():
        points.sort(key=lambda item: item[0])
        values = [value for _, value in points]
        if not values:
            continue
        modes[mode] = {
            "points": len(values),
            "latest": values[-1],
            "avg_last3": round(sum(values[-3:]) / min(3, len(values)), 3),
            "peak": max(values),
            "trend_delta": round(values[-1] - values[0], 3) if len(values) >= 2 else 0,
        }
    return {
        "points": sum(item["points"] for item in modes.values()),
        "modes": modes,
        "best_avg_last3": max((item["avg_last3"] for item in modes.values()), default=0),
        "best_latest": max((item["latest"] for item in modes.values()), default=0),
        "worst_trend_delta": min((item["trend_delta"] for item in modes.values()), default=0),
    }


def _tier_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        slug = normalize_character_id(row.get("character_slug"))
        if slug:
            grouped[slug].append(row)
    output: dict[str, dict[str, Any]] = {}
    for slug, items in grouped.items():
        best = sorted(items, key=lambda row: _float(row.get("rating")), reverse=True)[0]
        output[slug] = {
            **best,
            "best_rating": _float(best.get("rating")),
            "best_tier": best.get("tier", ""),
            "modes": ", ".join(sorted({str(row.get("tier_mode") or "") for row in items if row.get("tier_mode")})),
        }
    return output


def _records_for_slug(pool: EvidencePool, slug: str) -> list[Any]:
    records = [record for record in pool.records if slug in record.team_slugs]
    return sorted(records, key=lambda record: (CONFIDENCE_ORDER.get(record.confidence, 9), -(record.max_app_rate or 0), -record.record_count))


def _top_records(records: list[Any], limit: int = 5) -> list[Any]:
    return records[:limit]


def _coverage_text(current_records: list[Any], target_records: list[Any], dependent_records: list[Any]) -> str:
    def counts(records: list[Any]) -> str:
        counter = Counter(record.confidence for record in records)
        return " / ".join(f"{key} {counter[key]}" for key in sorted(counter, key=lambda item: CONFIDENCE_ORDER.get(item, 9))) if counter else "0"

    return f"current {len(current_records)}({counts(current_records)})；target {len(target_records)}({counts(target_records)})；新增依赖 {len(dependent_records)}({counts(dependent_records)})"


def _candidate_type(candidate: dict[str, Any], slug: str, usage_rows: list[dict[str, Any]], tier_index: dict[str, dict[str, Any]]) -> str:
    text = " ".join(
        [
            str(candidate.get("banner_role") or ""),
            str(candidate.get("status") or ""),
            " ".join(str(item) for item in candidate.get("analysis_tags") or []),
        ]
    )
    if "新角色" in text or "new" in text.lower():
        return "new"
    if "复刻" in text or "rerun" in text.lower() or slug in tier_index:
        return "rerun"
    if any(normalize_character_id(row.get("character_slug")) == slug for row in usage_rows):
        return "rerun"
    return "new"


def _history_text(usage: dict[str, Any]) -> str:
    if not usage.get("points"):
        return "暂无历史出场；若为新角色，这是未实测状态，不作为负面"
    parts = []
    for mode, item in usage["modes"].items():
        parts.append(f"{mode}: points {item['points']} / latest {item['latest']:g}% / avg_last3 {item['avg_last3']:g}% / trend {item['trend_delta']:g}")
    return "；".join(parts)


def _global_usage_text(usage: dict[str, Any]) -> str:
    return f"best_latest={_number_text(usage.get('best_latest'))}%；best_avg_last3={_number_text(usage.get('best_avg_last3'))}%；worst_trend={_number_text(usage.get('worst_trend_delta'))}"


def _mechanism_text(candidate: dict[str, Any], tier: dict[str, Any], mechanism: dict[str, Any]) -> str:
    identity = mechanism.get("identity") if isinstance(mechanism.get("identity"), dict) else {}
    role = candidate.get("role_group_cn") or tier.get("role_group_cn") or identity.get("role_group_cn") or "未知定位"
    element = candidate.get("element_cn") or tier.get("element_cn") or identity.get("element_cn") or "未知属性"
    style = candidate.get("style_cn") or tier.get("style_cn") or identity.get("style_cn") or "未知特性"
    focus = candidate.get("focus") or mechanism.get("mechanism_status") or "暂无机制文本"
    rarity = candidate.get("rarity") or identity.get("rarity")
    archetypes = _list_text(mechanism.get("archetypes"))
    teammates = _list_text(mechanism.get("key_teammates"))
    extra = []
    if rarity:
        extra.append(f"稀有度={rarity}")
    if archetypes:
        extra.append(f"archetype={archetypes}")
    if teammates:
        extra.append(f"关键队友={teammates}")
    suffix = "；" + "；".join(extra) if extra else ""
    return f"{element} / {style} / {role}；{focus}{suffix}"


def _mechanism_review_text(mechanism: dict[str, Any]) -> str:
    if not mechanism:
        return "暂无 mechanism_notes；等技能/影画/专武/首轮数据"
    parts = []
    source_quality = _source_quality_text(mechanism.get("source_quality"))
    if source_quality:
        parts.append(f"source_quality={source_quality}")
    if mechanism.get("stage_confidence"):
        parts.append(f"stage_confidence={mechanism.get('stage_confidence')}")
    stage_notes = _stage_notes_text(mechanism.get("stage_notes"))
    if stage_notes:
        parts.append(stage_notes)
    else:
        parts.extend(
            [
                f"0+0={mechanism.get('body_completeness_0_0') or '-'}",
                f"0+1={mechanism.get('signature_value_0_1') or '-'}",
                f"1+0={mechanism.get('cinema_value_1_0') or '-'}",
                f"1+1={mechanism.get('combo_value_1_1') or '-'}",
                f"2+1={mechanism.get('necessity_2_1') or '-'}",
            ]
        )
    return "；".join(str(part) for part in parts)


def _stage_from_mechanism(candidate_type: str, mechanism: dict[str, Any], *, role: str = "") -> dict[str, str]:
    if not mechanism:
        return {
            "recommended_stage": "等技能/影画/专武/首轮数据",
            "acceptable_stage": "暂不预设",
            "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
            "stage_confidence": "low",
            "not_recommended_stage": "暂不判断",
            "reason": "缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X",
            "missing_data": "技能机制、影画、专武、实战队伍、首轮高难数据",
        }
    recommended = str(mechanism.get("recommended_stage") or "")
    acceptable = str(mechanism.get("acceptable_stage") or "")
    unresolved = str(mechanism.get("unresolved_stage") or "")
    confidence = str(mechanism.get("stage_confidence") or "")
    not_recommended = str(mechanism.get("not_recommended_stage") or "")
    if not recommended:
        recommended = "0+0" if ("辅助" in role or "支援" in role or candidate_type == "rerun") else "等实测"
    if not acceptable:
        acceptable = recommended
    if not unresolved:
        unresolved = _unresolved_stage_text(mechanism)
    if not confidence:
        confidence = "medium" if mechanism.get("stage_notes") else "low"
    if not not_recommended:
        not_recommended = str(mechanism.get("higher_stage_note") or "高档位暂不判断；只在机制/指南/实战证明必要时考虑")
    return {
        "recommended_stage": recommended,
        "acceptable_stage": acceptable,
        "unresolved_stage": unresolved,
        "stage_confidence": confidence,
        "not_recommended_stage": not_recommended,
        "reason": str(mechanism.get("stage_reason") or mechanism.get("reason") or _mechanism_review_text(mechanism)),
        "missing_data": str(mechanism.get("missing_data") or _stage_missing_data_text(mechanism) or "持续观察后续版本实战、队友和环境变化"),
    }


def _missing_mechanism_data(mechanism: dict[str, Any]) -> str:
    if not mechanism:
        return "等技能/影画/专武/首轮数据"
    return str(mechanism.get("missing_data") or "")


def _replacement_text(candidate: dict[str, Any], tier: dict[str, Any], owned: set[str], mechanism: dict[str, Any]) -> str:
    counter = _list_text(mechanism.get("risks_and_counterevidence"))
    if counter:
        return counter
    role = candidate.get("role_group_cn") or tier.get("role_group_cn") or ""
    if not role:
        return "机制未知，替代风险无法判定"
    if "辅助" in role or "支援" in role:
        return "辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断"
    return "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面"


def _card_lines(card: PullValueCard) -> list[str]:
    stage = card.stage_recommendation
    lines = [
        f"### {card.name_cn} `{card.slug}`：{card.pull_value}",
        "",
        f"- 类型：{card.candidate_type}；状态：{card.status or '-'}",
        f"- recommended_stage：{stage.get('recommended_stage', '-')}",
        f"- acceptable_stage：{stage.get('acceptable_stage', '-')}",
        f"- unresolved_stage：{stage.get('unresolved_stage', '-')}",
        f"- stage_confidence：{stage.get('stage_confidence', '-')}",
        f"- not_recommended_stage：{stage.get('not_recommended_stage', '-')}",
        f"- stage_reason：{stage.get('reason', '-')}",
        f"- missing_data：{stage.get('missing_data', '-')}",
        f"- source_quality：{_source_quality_text(card.mechanism_notes.get('source_quality')) or '-'}",
        f"- stage_notes：{_stage_notes_text(card.mechanism_notes.get('stage_notes')) or '-'}",
        f"- 历史走势：{card.history_summary}",
        f"- 全局出场：{card.global_usage_summary}",
        f"- 队伍覆盖：{card.team_coverage_summary}",
        f"- mechanism_review：{card.mechanism_review_summary}",
        f"- 机制/拼图：{card.mechanism_summary}",
        f"- 替代风险：{card.replacement_risk}",
        f"- 证据：{', '.join(card.evidence_ids) if card.evidence_ids else '-'}",
        f"- 依据：{'；'.join(card.decision_basis) if card.decision_basis else '-'}",
        f"- 风险：{'；'.join(card.risk_notes) if card.risk_notes else '无'}",
        "",
    ]
    return lines


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _value_sort_key(value: str) -> int:
    return {"高": 0, "中高": 1, "中": 2, "等实测": 3, "低": 4}.get(value, 9)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _number_text(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "-"


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _default_mechanism_notes_dir(plan_path: str | Path | None) -> Path:
    if plan_path:
        return Path(plan_path).parent / "zzz_mechanism_notes"
    return Path("configs") / "zzz_mechanism_notes"


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item))
    if value in {None, ""}:
        return ""
    return str(value)


def _source_quality_text(value: Any) -> str:
    if isinstance(value, dict):
        return "；".join(f"{key}={item}" for key, item in value.items() if str(item))
    return _list_text(value)


def _stage_notes_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts = []
    for stage in ("0+0", "0+1", "1+0", "1+1", "2+1"):
        note = value.get(stage)
        if not isinstance(note, dict):
            continue
        fields = []
        if note.get("value_type"):
            fields.append(f"value_type={note.get('value_type')}")
        if note.get("evidence"):
            fields.append(f"evidence={note.get('evidence')}")
        if note.get("missing_data"):
            fields.append(f"missing_data={note.get('missing_data')}")
        if fields:
            parts.append(f"{stage}({'; '.join(fields)})")
    return "；".join(parts)


def _unresolved_stage_text(mechanism: dict[str, Any]) -> str:
    stage_notes = mechanism.get("stage_notes")
    if not isinstance(stage_notes, dict):
        return ""
    unresolved = []
    for stage in ("0+1", "1+0", "1+1", "2+1"):
        note = stage_notes.get(stage)
        if isinstance(note, dict) and note.get("missing_data"):
            unresolved.append(stage)
    return " / ".join(unresolved)


def _stage_missing_data_text(mechanism: dict[str, Any]) -> str:
    stage_notes = mechanism.get("stage_notes")
    if not isinstance(stage_notes, dict):
        return ""
    missing = []
    for stage in ("0+0", "0+1", "1+0", "1+1", "2+1"):
        note = stage_notes.get(stage)
        if isinstance(note, dict) and note.get("missing_data"):
            missing.append(f"{stage}: {note.get('missing_data')}")
    return "；".join(missing)
