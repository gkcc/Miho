from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import re
from statistics import median
from typing import Any, Iterable, Sequence

from hsr_endgame_exporter.normalize import normalize_character_id, parse_number, parse_percent

from .box import load_config


DEFAULT_SENTINELS = {0.0, 99.99}
CONFIDENCE_ORDER = {"A": 0, "B+": 1, "B": 2, "B-": 3, "C": 4}


@dataclass(frozen=True)
class NameIndex:
    aliases: dict[str, str]
    names_cn: dict[str, str]
    kinds: dict[str, str]


@dataclass(frozen=True)
class TeamSignatureAggregate:
    team_signature: str
    agent_signature: str
    full_team_signature: str
    team_slugs: tuple[str, ...]
    team_cn: tuple[str, ...]
    bangboo_slug: str
    bangboo_name_cn: str
    record_count: int
    snapshot_count: int
    phase_count: int
    mode_count: int
    scope_count: int
    boss_count: int
    source_kind_count: int
    max_app_rate: float | None
    median_app_rate: float | None
    best_rank: int | None
    best_score: float | int | None
    metric_direction: str
    non_sentinel_score_count: int
    sentinel_score_count: int
    confidence: str
    modes: tuple[str, ...]
    phase_versions: tuple[str, ...]
    scopes: tuple[str, ...]
    source_kinds: tuple[str, ...]
    evidence_comment: str
    risk_comment: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    scenario: str
    team_signature: str
    agent_signature: str
    full_team_signature: str
    team_slugs: tuple[str, ...]
    team_cn: tuple[str, ...]
    bangboo_slug: str
    bangboo_name_cn: str
    bangboo_checked: str
    owned_count: int
    plan_dependency: tuple[str, ...]
    missing_parts: tuple[str, ...]
    confidence: str
    record_count: int
    snapshot_count: int
    phase_count: int
    mode_count: int
    scope_count: int
    boss_count: int
    source_kind_count: int
    max_app_rate: float | None
    median_app_rate: float | None
    best_rank: int | None
    best_score: float | int | None
    metric_direction: str
    non_sentinel_score_count: int
    sentinel_score_count: int
    modes: tuple[str, ...]
    phase_versions: tuple[str, ...]
    scopes: tuple[str, ...]
    evidence_comment: str
    risk_comment: str


@dataclass(frozen=True)
class EvidencePool:
    records: list[EvidenceRecord]
    summary: dict[str, Any]
    aggregates: list[TeamSignatureAggregate]


AGGREGATE_COLUMNS = [
    "team_signature",
    "agent_signature",
    "full_team_signature",
    "team_slugs",
    "team_cn",
    "bangboo_slug",
    "bangboo_name_cn",
    "confidence",
    "record_count",
    "snapshot_count",
    "phase_count",
    "mode_count",
    "scope_count",
    "boss_count",
    "source_kind_count",
    "max_app_rate",
    "median_app_rate",
    "best_rank",
    "best_score",
    "metric_direction",
    "non_sentinel_score_count",
    "sentinel_score_count",
    "modes",
    "phase_versions",
    "scopes",
    "source_kinds",
    "evidence_comment",
    "risk_comment",
]


def split_slugs(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[;,]", value)
    else:
        parts = list(value)
    return [normalize_character_id(str(part)) for part in parts if normalize_character_id(str(part))]


def load_name_index(data_dir: str | Path) -> NameIndex:
    path = Path(data_dir) / "name_map.csv"
    aliases: dict[str, str] = {}
    names_cn: dict[str, str] = {}
    kinds: dict[str, str] = {}
    if not path.exists():
        return NameIndex(aliases=aliases, names_cn=names_cn, kinds=kinds)
    for row in _read_csv(path):
        slug = normalize_character_id(row.get("character_slug"))
        if not slug:
            continue
        aliases[slug] = slug
        names_cn[slug] = str(row.get("character_name_cn") or row.get("character_name_en") or slug)
        kinds[slug] = str(row.get("kind") or "")
        for value in _split_aliases(row.get("aliases")):
            normalized = normalize_character_id(value)
            if normalized:
                aliases[normalized] = slug
    return NameIndex(aliases=aliases, names_cn=names_cn, kinds=kinds)


def canonical_slug(value: str | None, names: NameIndex) -> str:
    slug = normalize_character_id(value)
    if not slug:
        return ""
    return names.aliases.get(slug, slug)


def load_owned_slugs(box_path: str | Path, names: NameIndex | None = None) -> set[str]:
    name_index = names or NameIndex({}, {}, {})
    data = load_config(box_path)
    owned: set[str] = set()
    if isinstance(data.get("owned"), list):
        owned.update(canonical_slug(str(item), name_index) for item in data["owned"])
    agents = data.get("agents")
    if isinstance(agents, list):
        for row in agents:
            if not isinstance(row, dict):
                continue
            if _truthy(row.get("owned", True)):
                slug = row.get("slug") or row.get("id") or row.get("name_en") or row.get("name")
                owned.add(canonical_slug(str(slug), name_index))
    elif isinstance(agents, dict):
        for slug, value in agents.items():
            is_owned = _truthy(value.get("owned", True)) if isinstance(value, dict) else _truthy(value)
            if is_owned:
                owned.add(canonical_slug(str(slug), name_index))
    return {slug for slug in owned if slug}


def load_owned_bangboo_slugs(box_path: str | Path, names: NameIndex | None = None) -> tuple[bool, set[str]]:
    name_index = names or NameIndex({}, {}, {})
    data = load_config(box_path)
    known = False
    owned: set[str] = set()
    for key in ("bangboo", "bangboos", "owned_bangboo", "owned_bangboos"):
        if key not in data:
            continue
        known = True
        owned.update(_owned_slug_rows(data.get(key), name_index))
    return known, {slug for slug in owned if slug}


def load_planned_slugs_from_banner_plan(
    plan_path: str | Path,
    *,
    statuses: Sequence[str] = ("next",),
    names: NameIndex | None = None,
) -> list[str]:
    name_index = names or NameIndex({}, {}, {})
    status_set = {str(status).strip().lower() for status in statuses if str(status).strip()}
    data = load_config(plan_path)
    planned: list[str] = []
    for phase in data.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        status = str(phase.get("status") or "").strip().lower()
        if status_set and status not in status_set:
            continue
        for character in phase.get("characters") or []:
            if not isinstance(character, dict):
                continue
            slug = canonical_slug(str(character.get("slug") or ""), name_index)
            if slug and slug not in planned:
                planned.append(slug)
    return planned


def build_team_signature_aggregates(
    data_dir: str | Path,
    *,
    sentinel_values: set[float] | None = None,
    min_a_app_rate: float | dict[str, float] | None = None,
) -> list[TeamSignatureAggregate]:
    out = Path(data_dir)
    names = load_name_index(out)
    team_path = out / "team_rank_dedup_unordered.csv"
    if not team_path.exists():
        raise FileNotFoundError(f"队伍证据表不存在：{team_path}")
    rows = _read_csv(team_path)
    columns = list(rows[0].keys()) if rows else _read_header(team_path)
    char_columns = _detect_team_columns(columns)
    metric_column = _detect_metric_column(columns)
    sentinels = sentinel_values if sentinel_values is not None else DEFAULT_SENTINELS
    grouped: dict[tuple[tuple[str, ...], str], list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        app_rate = parse_percent(row.get("app_rate"))
        if app_rate is None or app_rate <= 0:
            continue
        team = tuple(canonical_slug(str(row.get(column) or ""), names) for column in char_columns if row.get(column))
        team = tuple(slug for slug in team if slug)
        if not team:
            continue
        agent_signature_tuple = tuple(sorted(team))
        bangboo_slug = canonical_slug(str(row.get("bangboo_slug") or ""), names)
        score = parse_number(row.get(metric_column)) if metric_column else None
        grouped[(agent_signature_tuple, bangboo_slug)].append(
            {
                "row": row,
                "app_rate": app_rate,
                "rank": _int_or_none(row.get("rank")),
                "score": score,
                "score_sentinel": _is_sentinel(score, sentinels),
                "metric_direction": _metric_direction(row, metric_column),
            }
        )

    aggregates: list[TeamSignatureAggregate] = []
    for (agent_signature_tuple, bangboo_slug), items in grouped.items():
        app_rates = [item["app_rate"] for item in items if item.get("app_rate") is not None]
        non_sentinel_scores = [item["score"] for item in items if not item["score_sentinel"] and item.get("score") is not None]
        sentinel_count = sum(1 for item in items if item["score_sentinel"])
        best_rank = min((item["rank"] for item in items if item.get("rank") is not None), default=None)
        metric_direction = _combined_metric_direction(item["metric_direction"] for item in items)
        best_score = _best_score_by_direction(
            (item["score"], item["metric_direction"])
            for item in items
            if not item["score_sentinel"] and item.get("score") is not None
        )
        snapshots = sorted({str(item["row"].get("snapshot_id") or "") for item in items if item["row"].get("snapshot_id")})
        phase_keys = sorted(
            {
                f"{item['row'].get('mode') or ''}:{item['row'].get('phase_ver') or ''}"
                for item in items
                if item["row"].get("phase_ver")
            }
        )
        modes = sorted({str(item["row"].get("mode") or "") for item in items if item["row"].get("mode")})
        scopes = sorted({str(item["row"].get("scope") or item["row"].get("sub_mode") or "") for item in items if item["row"].get("scope") or item["row"].get("sub_mode")})
        boss_keys = sorted({_boss_key(item["row"]) for item in items if _boss_key(item["row"])})
        source_kinds = sorted({str(item["row"].get("source_kind") or "") for item in items if item["row"].get("source_kind")})
        confidence, evidence_comment, risk_comment = _classify_aggregate(
            record_count=len(items),
            phase_count=len(phase_keys),
            mode_count=len(modes),
            boss_count=len(boss_keys),
            max_app_rate=max(app_rates, default=None),
            median_app_rate=median(app_rates) if app_rates else None,
            non_sentinel_score_count=len(non_sentinel_scores),
            sentinel_score_count=sentinel_count,
            modes=modes,
            min_a_app_rate=min_a_app_rate,
        )
        if metric_direction == "mixed":
            risk_comment = _append_comment(risk_comment, "混合指标方向，best_score 不做跨方向比较")
        full_signature = _full_team_signature(agent_signature_tuple, bangboo_slug)
        aggregates.append(
            TeamSignatureAggregate(
                team_signature=full_signature,
                agent_signature="|".join(agent_signature_tuple),
                full_team_signature=full_signature,
                team_slugs=agent_signature_tuple,
                team_cn=tuple(_name_cn(slug, names) for slug in agent_signature_tuple),
                bangboo_slug=bangboo_slug,
                bangboo_name_cn=_bangboo_name_cn(bangboo_slug, names, items),
                record_count=len(items),
                snapshot_count=len(snapshots),
                phase_count=len(phase_keys),
                mode_count=len(modes),
                scope_count=len(scopes),
                boss_count=len(boss_keys),
                source_kind_count=len(source_kinds),
                max_app_rate=max(app_rates, default=None),
                median_app_rate=median(app_rates) if app_rates else None,
                best_rank=best_rank,
                best_score=best_score,
                metric_direction=metric_direction,
                non_sentinel_score_count=len(non_sentinel_scores),
                sentinel_score_count=sentinel_count,
                confidence=confidence,
                modes=tuple(modes),
                phase_versions=tuple(phase_keys),
                scopes=tuple(scopes),
                source_kinds=tuple(source_kinds),
                evidence_comment=evidence_comment,
                risk_comment=risk_comment,
            )
        )
    return sorted(aggregates, key=_aggregate_sort_key)


def build_evidence_pool(
    data_dir: str | Path,
    *,
    owned_slugs: Iterable[str],
    planned_slugs: Iterable[str] = (),
    scenario: str = "target_box",
    include_missing: bool = False,
    sentinel_values: set[float] | None = None,
    min_a_app_rate: float | dict[str, float] | None = None,
    owned_bangboo_slugs: Iterable[str] | None = None,
    bangboo_ownership_known: bool = False,
) -> EvidencePool:
    names = load_name_index(data_dir)
    owned = {canonical_slug(slug, names) for slug in owned_slugs if canonical_slug(slug, names)}
    planned_order = [canonical_slug(slug, names) for slug in planned_slugs if canonical_slug(slug, names)]
    planned_order = list(dict.fromkeys(planned_order))
    target = owned | set(planned_order)
    owned_bangboo = {canonical_slug(slug, names) for slug in (owned_bangboo_slugs or []) if canonical_slug(slug, names)}
    aggregates = build_team_signature_aggregates(
        data_dir,
        sentinel_values=sentinel_values,
        min_a_app_rate=min_a_app_rate,
    )
    records: list[EvidenceRecord] = []
    for aggregate in aggregates:
        team_set = set(aggregate.team_slugs)
        missing = tuple(slug for slug in aggregate.team_slugs if slug not in target)
        if missing and not include_missing:
            continue
        dependency = tuple(slug for slug in planned_order if slug in team_set and slug not in owned) or ("none",)
        confidence = "C" if missing else aggregate.confidence
        risk_comment = aggregate.risk_comment
        if missing:
            risk_comment = _append_comment(risk_comment, "缺目标账号成员：" + ", ".join(missing))
        bangboo_checked = _bangboo_checked(
            aggregate.bangboo_slug,
            owned_bangboo,
            ownership_known=bangboo_ownership_known,
        )
        if bangboo_checked == "缺邦布":
            risk_comment = _append_comment(risk_comment, "Bangboo 记录缺拥有校验：" + aggregate.bangboo_slug)
        elif bangboo_checked == "邦布未校验":
            risk_comment = _append_comment(risk_comment, "Bangboo 未参与账号覆盖校验")
        records.append(
            EvidenceRecord(
                evidence_id=f"E{len(records) + 1:04d}",
                scenario=scenario,
                team_signature=aggregate.team_signature,
                agent_signature=aggregate.agent_signature,
                full_team_signature=aggregate.full_team_signature,
                team_slugs=aggregate.team_slugs,
                team_cn=aggregate.team_cn,
                bangboo_slug=aggregate.bangboo_slug,
                bangboo_name_cn=aggregate.bangboo_name_cn,
                bangboo_checked=bangboo_checked,
                owned_count=sum(1 for slug in aggregate.team_slugs if slug in owned),
                plan_dependency=dependency,
                missing_parts=missing or ("none",),
                confidence=confidence,
                record_count=aggregate.record_count,
                snapshot_count=aggregate.snapshot_count,
                phase_count=aggregate.phase_count,
                mode_count=aggregate.mode_count,
                scope_count=aggregate.scope_count,
                boss_count=aggregate.boss_count,
                source_kind_count=aggregate.source_kind_count,
                max_app_rate=aggregate.max_app_rate,
                median_app_rate=aggregate.median_app_rate,
                best_rank=aggregate.best_rank,
                best_score=aggregate.best_score,
                metric_direction=aggregate.metric_direction,
                non_sentinel_score_count=aggregate.non_sentinel_score_count,
                sentinel_score_count=aggregate.sentinel_score_count,
                modes=aggregate.modes,
                phase_versions=aggregate.phase_versions,
                scopes=aggregate.scopes,
                evidence_comment=aggregate.evidence_comment,
                risk_comment=risk_comment,
            )
        )
    records.sort(key=_coverage_sort_key)
    records = [replace(record, evidence_id=f"E{index + 1:04d}") for index, record in enumerate(records)]
    summary = {
        "data_dir": str(Path(data_dir)),
        "team_source": str(Path(data_dir) / "team_rank_dedup_unordered.csv"),
        "scenario": scenario,
        "owned_count": len(owned),
        "planned": planned_order,
        "target_count": len(target),
        "aggregate_count": len(aggregates),
        "included_records": len(records),
        "confidence_counts": dict(Counter(record.confidence for record in records)),
        "dependency_counts": dict(Counter(",".join(record.plan_dependency) for record in records)),
        "mode_counts": dict(Counter(mode for record in records for mode in record.modes)),
        "include_missing": include_missing,
        "min_a_app_rate": min_a_app_rate if min_a_app_rate is not None else 10.0,
        "bangboo_ownership_known": bangboo_ownership_known,
    }
    return EvidencePool(records=records, summary=summary, aggregates=aggregates)


def build_evidence_pool_from_paths(
    data_dir: str | Path,
    *,
    box_path: str | Path,
    planned_slugs: Iterable[str] = (),
    scenario: str = "target_box",
    include_missing: bool = False,
    min_a_app_rate: float | dict[str, float] | None = None,
) -> EvidencePool:
    names = load_name_index(data_dir)
    owned = load_owned_slugs(box_path, names)
    bangboo_known, owned_bangboo = load_owned_bangboo_slugs(box_path, names)
    return build_evidence_pool(
        data_dir,
        owned_slugs=owned,
        planned_slugs=planned_slugs,
        scenario=scenario,
        include_missing=include_missing,
        min_a_app_rate=min_a_app_rate,
        owned_bangboo_slugs=owned_bangboo,
        bangboo_ownership_known=bangboo_known,
    )


def write_evidence_report(
    data_dir: str | Path,
    *,
    box_path: str | Path,
    planned_slugs: Iterable[str] = (),
    output_path: str | Path,
    title: str = "证据池队伍覆盖报告",
    include_missing: bool = False,
    limit: int = 0,
    scenario: str = "target_box",
    min_a_app_rate: float | None = None,
) -> EvidencePool:
    pool = build_evidence_pool_from_paths(
        data_dir,
        box_path=box_path,
        planned_slugs=planned_slugs,
        scenario=scenario,
        include_missing=include_missing,
        min_a_app_rate=min_a_app_rate,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(format_evidence_report(pool, title=title, limit=limit), encoding="utf-8")
    return pool


def write_coverage_reports(
    data_dir: str | Path,
    *,
    box_path: str | Path,
    planned_slugs: Iterable[str] = (),
    current_output_path: str | Path,
    target_output_path: str | Path,
    aggregate_output_path: str | Path | None = None,
    limit: int = 0,
    min_a_app_rate: float | dict[str, float] | None = None,
) -> tuple[EvidencePool, EvidencePool]:
    names = load_name_index(data_dir)
    owned = load_owned_slugs(box_path, names)
    bangboo_known, owned_bangboo = load_owned_bangboo_slugs(box_path, names)
    current_pool = build_evidence_pool(
        data_dir,
        owned_slugs=owned,
        planned_slugs=[],
        scenario="current_box",
        include_missing=False,
        min_a_app_rate=min_a_app_rate,
        owned_bangboo_slugs=owned_bangboo,
        bangboo_ownership_known=bangboo_known,
    )
    target_pool = build_evidence_pool(
        data_dir,
        owned_slugs=owned,
        planned_slugs=planned_slugs,
        scenario="target_box",
        include_missing=False,
        min_a_app_rate=min_a_app_rate,
        owned_bangboo_slugs=owned_bangboo,
        bangboo_ownership_known=bangboo_known,
    )
    current_path = Path(current_output_path)
    target_path = Path(target_output_path)
    current_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(format_coverage_report(current_pool, title="当前 Box 队伍覆盖", limit=limit), encoding="utf-8")
    target_path.write_text(format_coverage_report(target_pool, title="目标 Box 队伍覆盖", limit=limit), encoding="utf-8")
    if aggregate_output_path:
        write_team_signature_aggregates_csv(target_pool.aggregates, aggregate_output_path)
    return current_pool, target_pool


def write_team_signature_aggregates_csv(aggregates: Sequence[TeamSignatureAggregate], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=AGGREGATE_COLUMNS)
        writer.writeheader()
        for aggregate in aggregates:
            writer.writerow(_aggregate_row(aggregate))


def format_evidence_report(pool: EvidencePool, *, title: str = "证据池队伍覆盖报告", limit: int = 0) -> str:
    return format_coverage_report(pool, title=title, limit=limit)


def format_coverage_report(pool: EvidencePool, *, title: str = "队伍覆盖报告", limit: int = 0) -> str:
    summary = pool.summary
    records = pool.records[:limit] if limit and limit > 0 else pool.records
    lines = [
        f"# {title}",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- scenario：`{summary.get('scenario')}`",
        f"- 队伍数据源：`{summary.get('team_source')}`",
        f"- team signature 聚合数：{summary.get('aggregate_count', 0)}",
        f"- 当前拥有：{summary.get('owned_count', 0)}；计划角色：{', '.join(summary.get('planned') or []) or 'none'}；目标账号角色数：{summary.get('target_count', 0)}",
        f"- 可组 team signature：{summary.get('included_records', 0)}",
        f"- A 档 min_app_rate 阈值：{_threshold_text(summary.get('min_a_app_rate'))}",
        f"- Bangboo 拥有信息：{'已读取' if summary.get('bangboo_ownership_known') else '未提供，报告标记为邦布未校验'}",
        f"- 置信度分布：{_dict_text(summary.get('confidence_counts') or {})}",
        f"- 计划依赖分布：{_dict_text(summary.get('dependency_counts') or {})}",
        "",
        "## 置信度口径",
        "",
        "- A：跨多期、多 Boss/范围、多模式且出场率较高，非 sentinel 分数充足。",
        "- B+：重复度和出场率都较好，但广度或稳定性略弱于 A。",
        "- B：有真实记录和一定重复度，可证明可组与存在感，但不能直接推断长期 auto 稳定。",
        "- B-：真实记录稀疏、出场率低或 sentinel 较多，只能作为弱证据。",
        "- C：缺目标账号成员、无有效表现，或证据不足以支撑覆盖结论。",
        "",
        "## 数据口径",
        "",
        "- 先按无序三代理人 `agent_signature` 做账号覆盖，再按三代理人 + Bangboo 的 `full_team_signature` 聚合真实队伍证据。",
        "- planned 只作为 target scenario 的增量成员，不和 current_box 结论混写；target 表保留 `plan_dependency`。",
        "- `0`、`99.99`、缺失分数按 sentinel / missing 处理，不作为真实表现。",
        "- `metric_direction` 控制 best_score 取值方向；SD/DA 本地原始 JSON 的 `avg_round` 实为分数，按 `higher_better` 处理，但 SD/DA 分数仍不互相横比。",
        "- Bangboo 写入 full evidence signature；只有 box 提供 Bangboo 拥有信息时才校验，否则标记 `邦布未校验`，不影响三代理人可组判断。",
        "",
        "## 覆盖记录",
        "",
        "| evidence_id | scenario | confidence | team_signature | agent_signature | full_team_signature | team_slugs | team_cn | bangboo_slug | bangboo_name_cn | bangboo_checked | owned_count | plan_dependency | missing_parts | record_count | snapshot_count | phase_count | mode_count | scope_count | boss_count | source_kind_count | max_app_rate | median_app_rate | best_rank | best_score | metric_direction | non_sentinel_score_count | sentinel_score_count | modes | evidence_comment | risk_comment |",
        "|---|---|---|---|---|---|---|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|---|---|",
    ]
    if not records:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | 0 | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | - | - | - | 0 | 0 | - | 无可组真实队伍记录 | 检查 box、计划角色或数据源 |")
    for record in records:
        lines.append(
            "| {evidence_id} | {scenario} | {confidence} | {signature} | {agent_signature} | {full_team_signature} | {team_slugs} | {team_cn} | {bangboo_slug} | {bangboo_name_cn} | {bangboo_checked} | {owned_count} | {plan_dependency} | {missing_parts} | {record_count} | {snapshot_count} | {phase_count} | {mode_count} | {scope_count} | {boss_count} | {source_kind_count} | {max_app_rate} | {median_app_rate} | {best_rank} | {best_score} | {metric_direction} | {non_sentinel} | {sentinel} | {modes} | {evidence_comment} | {risk_comment} |".format(
                evidence_id=record.evidence_id,
                scenario=_md(record.scenario),
                confidence=record.confidence,
                signature=_md(record.team_signature),
                agent_signature=_md(record.agent_signature),
                full_team_signature=_md(record.full_team_signature),
                team_slugs=_md(", ".join(record.team_slugs)),
                team_cn=_md(" / ".join(record.team_cn)),
                bangboo_slug=_md(record.bangboo_slug or "-"),
                bangboo_name_cn=_md(record.bangboo_name_cn or "-"),
                bangboo_checked=_md(record.bangboo_checked),
                owned_count=record.owned_count,
                plan_dependency=_md(", ".join(record.plan_dependency)),
                missing_parts=_md(", ".join(record.missing_parts)),
                record_count=record.record_count,
                snapshot_count=record.snapshot_count,
                phase_count=record.phase_count,
                mode_count=record.mode_count,
                scope_count=record.scope_count,
                boss_count=record.boss_count,
                source_kind_count=record.source_kind_count,
                max_app_rate=_number_text(record.max_app_rate),
                median_app_rate=_number_text(record.median_app_rate),
                best_rank=record.best_rank if record.best_rank is not None else "-",
                best_score=_number_text(record.best_score),
                metric_direction=_md(record.metric_direction),
                non_sentinel=record.non_sentinel_score_count,
                sentinel=record.sentinel_score_count,
                modes=_md(", ".join(record.modes)),
                evidence_comment=_md(record.evidence_comment),
                risk_comment=_md(record.risk_comment),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _classify_aggregate(
    *,
    record_count: int,
    phase_count: int,
    mode_count: int,
    boss_count: int,
    max_app_rate: float | None,
    median_app_rate: float | None,
    non_sentinel_score_count: int,
    sentinel_score_count: int,
    modes: Sequence[str] = (),
    min_a_app_rate: float | dict[str, float] | None = None,
) -> tuple[str, str, str]:
    max_app = max_app_rate or 0.0
    median_app = median_app_rate or 0.0
    min_a = _min_a_threshold(modes, min_a_app_rate)
    min_b_plus = max(1.0, min_a / 2)
    notes = [
        f"record_count={record_count}",
        f"phase_count={phase_count}",
        f"mode_count={mode_count}",
        f"boss_count={boss_count}",
        f"max_app_rate={_number_text(max_app_rate)}",
        f"median_app_rate={_number_text(median_app_rate)}",
        f"min_a_app_rate={_number_text(min_a)}",
    ]
    risks: list[str] = []
    if non_sentinel_score_count == 0:
        risks.append("全部表现分数为 sentinel/missing")
        return ("C" if record_count <= 1 else "B-"), "；".join(notes), "；".join(risks)
    if sentinel_score_count:
        risks.append(f"包含 {sentinel_score_count} 条 sentinel/missing 分数")
    if record_count >= 12 and phase_count >= 4 and mode_count >= 2 and boss_count >= 3 and max_app >= min_a and median_app >= 1:
        return "A", "；".join(notes), "；".join(risks) if risks else "无"
    if record_count >= 6 and phase_count >= 3 and (mode_count >= 2 or boss_count >= 2) and max_app >= min_b_plus:
        return "B+", "；".join(notes), "；".join(risks) if risks else "重复度较好，但未达到 A 档广度/强度"
    if record_count >= 3 and phase_count >= 2 and max_app >= 1:
        return "B", "；".join(notes), "；".join(risks) if risks else "有重复记录，可作普通证据"
    if record_count >= 1:
        risks.append("记录稀疏或出场率较低")
        return "B-", "；".join(notes), "；".join(risks)
    return "C", "；".join(notes), "无真实记录"


def _aggregate_row(aggregate: TeamSignatureAggregate) -> dict[str, Any]:
    return {
        "team_signature": aggregate.team_signature,
        "agent_signature": aggregate.agent_signature,
        "full_team_signature": aggregate.full_team_signature,
        "team_slugs": ", ".join(aggregate.team_slugs),
        "team_cn": " / ".join(aggregate.team_cn),
        "bangboo_slug": aggregate.bangboo_slug,
        "bangboo_name_cn": aggregate.bangboo_name_cn,
        "confidence": aggregate.confidence,
        "record_count": aggregate.record_count,
        "snapshot_count": aggregate.snapshot_count,
        "phase_count": aggregate.phase_count,
        "mode_count": aggregate.mode_count,
        "scope_count": aggregate.scope_count,
        "boss_count": aggregate.boss_count,
        "source_kind_count": aggregate.source_kind_count,
        "max_app_rate": _number_text(aggregate.max_app_rate),
        "median_app_rate": _number_text(aggregate.median_app_rate),
        "best_rank": aggregate.best_rank if aggregate.best_rank is not None else "",
        "best_score": _number_text(aggregate.best_score) if aggregate.best_score is not None else "",
        "metric_direction": aggregate.metric_direction,
        "non_sentinel_score_count": aggregate.non_sentinel_score_count,
        "sentinel_score_count": aggregate.sentinel_score_count,
        "modes": ", ".join(aggregate.modes),
        "phase_versions": ", ".join(aggregate.phase_versions),
        "scopes": ", ".join(aggregate.scopes),
        "source_kinds": ", ".join(aggregate.source_kinds),
        "evidence_comment": aggregate.evidence_comment,
        "risk_comment": aggregate.risk_comment,
    }


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _split_aliases(value: Any) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[;,]", str(value)) if part.strip()]


def _detect_team_columns(columns: Sequence[str]) -> list[str]:
    return sorted(
        [column for column in columns if re.fullmatch(r"char_\d+_slug", column)],
        key=lambda column: int(re.search(r"\d+", column).group(0)),  # type: ignore[union-attr]
    )


def _detect_metric_column(columns: Sequence[str]) -> str:
    for column in ("avg_round", "avg_score", "score"):
        if column in columns:
            return column
    return ""


def _metric_direction(row: dict[str, Any], metric_column: str) -> str:
    mode = str(row.get("mode") or "").strip().lower()
    if metric_column in {"avg_score", "score"}:
        return "higher_better"
    if metric_column == "avg_round" and mode in {"sd", "da"}:
        return "higher_better"
    if metric_column == "avg_round":
        return "lower_better"
    return "unknown"


def _combined_metric_direction(values: Iterable[str]) -> str:
    directions = {str(value or "unknown") for value in values if str(value or "")}
    if not directions:
        return "unknown"
    if len(directions) == 1:
        return next(iter(directions))
    return "mixed"


def _best_score_by_direction(values: Iterable[tuple[Any, str]]) -> float | int | None:
    scores_by_direction = [(score, direction) for score, direction in values if score is not None]
    if not scores_by_direction:
        return None
    directions = {direction for _, direction in scores_by_direction}
    scores = [score for score, _ in scores_by_direction]
    if directions == {"lower_better"}:
        return min(scores)
    if directions == {"higher_better"}:
        return max(scores)
    return None


def _full_team_signature(agent_signature: Sequence[str], bangboo_slug: str) -> str:
    parts = list(agent_signature)
    if bangboo_slug:
        parts.append(f"bangboo:{bangboo_slug}")
    return "|".join(parts)


def _bangboo_name_cn(bangboo_slug: str, names: NameIndex, items: Sequence[dict[str, Any]]) -> str:
    if not bangboo_slug:
        return ""
    indexed = _name_cn(bangboo_slug, names)
    if indexed and indexed != bangboo_slug:
        return indexed
    for item in items:
        name = str(item.get("row", {}).get("bangboo_name_cn") or "").strip()
        if name:
            return name
    return indexed


def _boss_key(row: dict[str, Any]) -> str:
    mode = str(row.get("mode") or "")
    sub_mode = str(row.get("sub_mode") or "").strip().lower()
    scope = str(row.get("scope") or "").replace("_combined.json", "").replace(".json", "").strip().lower()
    value = sub_mode or scope
    if value in {"", "all", "top", "bangboo"} or scope == "top":
        return ""
    return f"{mode}:{value}"


def _is_sentinel(value: Any, sentinel_values: set[float]) -> bool:
    number = _float_or_none(value)
    return number is None or number in sentinel_values


def _bangboo_checked(bangboo_slug: str, owned_bangboo: set[str], *, ownership_known: bool) -> str:
    if not bangboo_slug:
        return "无邦布记录"
    if not ownership_known:
        return "邦布未校验"
    return "已拥有" if bangboo_slug in owned_bangboo else "缺邦布"


def _name_cn(slug: str, names: NameIndex) -> str:
    return names.names_cn.get(slug) or slug


def _aggregate_sort_key(aggregate: TeamSignatureAggregate) -> tuple[int, float, int, str]:
    return (
        CONFIDENCE_ORDER.get(aggregate.confidence, 9),
        -(aggregate.max_app_rate or 0),
        -(aggregate.record_count),
        aggregate.team_signature,
    )


def _coverage_sort_key(record: EvidenceRecord) -> tuple[int, str, float, int, str]:
    dependency_group = "0" if record.plan_dependency == ("none",) else "1"
    return (
        CONFIDENCE_ORDER.get(record.confidence, 9),
        dependency_group,
        -(record.max_app_rate or 0),
        -record.record_count,
        record.team_signature,
    )


def _dict_text(value: dict[str, Any]) -> str:
    if not value:
        return "-"
    return " / ".join(f"{key or '-'} {count}" for key, count in value.items())


def _threshold_text(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}:{_number_text(item)}" for key, item in value.items()) or "-"
    return _number_text(_float_or_none(value) if value is not None else None)


def _min_a_threshold(modes: Sequence[str], min_a_app_rate: float | dict[str, float] | None) -> float:
    if min_a_app_rate is None:
        return 10.0
    if isinstance(min_a_app_rate, dict):
        values = [
            _float_or_none(min_a_app_rate.get(mode))
            for mode in modes
            if mode in min_a_app_rate
        ]
        values = [value for value in values if value is not None]
        default = _float_or_none(min_a_app_rate.get("default"))
        if values:
            return max(values)
        return default if default is not None else 10.0
    value = _float_or_none(min_a_app_rate)
    return value if value is not None else 10.0


def _append_comment(base: str, addition: str) -> str:
    if not base or base == "无":
        return addition
    return f"{base}；{addition}"


def _number_text(value: float | int | None) -> str:
    if value is None:
        return "-"
    number = float(value)
    return f"{number:g}"


def _md(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _owned_slug_rows(value: Any, names: NameIndex) -> set[str]:
    owned: set[str] = set()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if not _truthy(item.get("owned", True)):
                    continue
                slug = item.get("slug") or item.get("id") or item.get("name_en") or item.get("name")
                owned.add(canonical_slug(str(slug), names))
            else:
                owned.add(canonical_slug(str(item), names))
    elif isinstance(value, dict):
        for slug, item in value.items():
            is_owned = _truthy(item.get("owned", True)) if isinstance(item, dict) else _truthy(item)
            if is_owned:
                owned.add(canonical_slug(str(slug), names))
    elif isinstance(value, str):
        owned.update(canonical_slug(slug, names) for slug in split_slugs(value))
    return {slug for slug in owned if slug}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "n", "未拥有"}
