from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
from pathlib import Path
import math
import os
import re
from statistics import median
from typing import Any, Iterable, Sequence
from uuid import uuid4

from hsr_endgame_exporter.normalize import normalize_character_id, parse_number, parse_percent

from .banner_plan import effective_banner_phases
from .box import load_config


DEFAULT_SENTINELS = {0.0, 99.99}
CONFIDENCE_ORDER = {"A": 0, "B+": 1, "B": 2, "B-": 3, "C": 4}
EVIDENCE_METHOD_VERSION = "evidence-first-v1-20260712"


@dataclass(frozen=True)
class NameIndex:
    aliases: dict[str, str]
    names_cn: dict[str, str]
    kinds: dict[str, str]


@dataclass(frozen=True)
class TeamSignatureAggregate:
    mode: str
    mode_cn: str
    evidence_key: str
    team_signature: str
    agent_signature: str
    full_team_signature: str
    team_slugs: tuple[str, ...]
    team_cn: tuple[str, ...]
    bangboo_slug: str
    bangboo_name_cn: str
    record_count: int
    duplicate_count: int
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
    metric_name: str
    metric_direction: str
    non_sentinel_score_count: int
    sentinel_score_count: int
    valid_score_ratio: float
    confidence: str
    modes: tuple[str, ...]
    phase_versions: tuple[str, ...]
    phase_names: tuple[str, ...]
    scopes: tuple[str, ...]
    source_kinds: tuple[str, ...]
    observation_keys: tuple[str, ...]
    stability_status: str
    evidence_comment: str
    risk_comment: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    scenario: str
    mode: str
    mode_cn: str
    evidence_key: str
    team_signature: str
    agent_signature: str
    full_team_signature: str
    team_slugs: tuple[str, ...]
    team_cn: tuple[str, ...]
    bangboo_slug: str
    bangboo_name_cn: str
    bangboo_checked: str
    owned_count: int
    built_count: int
    build_checked: str
    unbuilt_parts: tuple[str, ...]
    plan_dependency: tuple[str, ...]
    missing_parts: tuple[str, ...]
    source_confidence: str
    confidence: str
    record_count: int
    duplicate_count: int
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
    metric_name: str
    metric_direction: str
    non_sentinel_score_count: int
    sentinel_score_count: int
    valid_score_ratio: float
    modes: tuple[str, ...]
    phase_versions: tuple[str, ...]
    phase_names: tuple[str, ...]
    scopes: tuple[str, ...]
    source_kinds: tuple[str, ...]
    observation_keys: tuple[str, ...]
    stability_status: str
    evidence_comment: str
    risk_comment: str


@dataclass(frozen=True)
class EvidencePool:
    records: list[EvidenceRecord]
    summary: dict[str, Any]
    aggregates: list[TeamSignatureAggregate]


@dataclass(frozen=True)
class ConfidencePolicy:
    a_records: int
    a_phases: int
    a_breadth: int
    a_valid_scores: int
    a_max_sentinel_ratio: float
    b_plus_records: int
    b_plus_phases: int
    b_plus_breadth: int
    b_plus_valid_scores: int
    b_plus_max_sentinel_ratio: float
    require_stability_for_a: bool = True


DEFAULT_CONFIDENCE_POLICY = ConfidencePolicy(12, 4, 3, 8, 0.25, 6, 3, 2, 4, 0.5)
MODE_CONFIDENCE_POLICIES = {
    "sd": DEFAULT_CONFIDENCE_POLICY,
    "da": DEFAULT_CONFIDENCE_POLICY,
    "moc": ConfidencePolicy(8, 4, 1, 6, 0.25, 4, 2, 1, 3, 0.5),
    "pf": ConfidencePolicy(8, 4, 1, 6, 0.25, 4, 2, 1, 3, 0.5),
    "as": ConfidencePolicy(8, 4, 1, 6, 0.25, 4, 2, 1, 3, 0.5),
    "aa": ConfidencePolicy(8, 4, 1, 6, 0.25, 4, 2, 1, 3, 0.5),
}


AGGREGATE_COLUMNS = [
    "mode",
    "mode_cn",
    "evidence_key",
    "team_signature",
    "agent_signature",
    "full_team_signature",
    "team_slugs",
    "team_cn",
    "bangboo_slug",
    "bangboo_name_cn",
    "confidence",
    "record_count",
    "duplicate_count",
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
    "metric_name",
    "metric_direction",
    "non_sentinel_score_count",
    "sentinel_score_count",
    "valid_score_ratio",
    "modes",
    "phase_versions",
    "phase_names",
    "scopes",
    "source_kinds",
    "observation_keys",
    "stability_status",
    "evidence_comment",
    "risk_comment",
]

COVERAGE_COLUMNS = [
    "evidence_id",
    "evidence_key",
    "scenario",
    "mode",
    "mode_cn",
    "source_confidence",
    "confidence",
    "team_signature",
    "agent_signature",
    "full_team_signature",
    "team_slugs",
    "team_cn",
    "bangboo_slug",
    "bangboo_name_cn",
    "bangboo_checked",
    "owned_count",
    "built_count",
    "build_checked",
    "unbuilt_parts",
    "plan_dependency",
    "missing_parts",
    "record_count",
    "duplicate_count",
    "snapshot_count",
    "phase_count",
    "scope_count",
    "boss_count",
    "source_kind_count",
    "max_app_rate",
    "median_app_rate",
    "best_rank",
    "best_score",
    "metric_name",
    "metric_direction",
    "non_sentinel_score_count",
    "sentinel_score_count",
    "valid_score_ratio",
    "phase_versions",
    "phase_names",
    "scopes",
    "source_kinds",
    "observation_keys",
    "stability_status",
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
    indexed_rows: list[tuple[str, dict[str, Any]]] = []
    for row in _read_csv(path):
        slug = normalize_character_id(row.get("character_slug"))
        if not slug:
            continue
        indexed_rows.append((slug, row))
        if slug in aliases and aliases[slug] != slug:
            raise ValueError(f"alias conflict: {slug} -> {aliases[slug]} / {slug}")
        aliases[slug] = slug
        names_cn[slug] = str(row.get("character_name_cn") or row.get("character_name_en") or slug)
        kinds[slug] = str(row.get("kind") or "")
    for slug, row in indexed_rows:
        for value in _split_aliases(row.get("aliases")):
            normalized = normalize_character_id(value)
            if normalized:
                existing = aliases.get(normalized)
                if existing is not None and existing != slug:
                    raise ValueError(f"alias conflict: {normalized} -> {existing} / {slug}")
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


def load_built_slugs(box_path: str | Path, names: NameIndex | None = None) -> tuple[bool, set[str]]:
    """Read only explicit build state; levels or ownership never imply ready."""
    name_index = names or NameIndex({}, {}, {})
    data = load_config(box_path)
    known = False
    built: set[str] = set()
    builds = data.get("builds")
    if isinstance(builds, dict):
        known = True
        for slug, value in builds.items():
            if _explicit_built(value, allow_payload_mapping=True):
                built.add(canonical_slug(str(slug), name_index))
    agents = data.get("agents")
    rows: list[tuple[str, Any]] = []
    if isinstance(agents, list):
        for row in agents:
            if isinstance(row, dict):
                slug = row.get("slug") or row.get("id") or row.get("name_en") or row.get("name")
                rows.append((str(slug or ""), row))
    elif isinstance(agents, dict):
        rows.extend((str(slug), value) for slug, value in agents.items())
    for raw_slug, value in rows:
        if isinstance(value, dict) and "built" in value:
            known = True
            if _explicit_built(value.get("built"), allow_payload_mapping=False):
                built.add(canonical_slug(raw_slug, name_index))
    return known, {slug for slug in built if slug}


def load_planned_slugs_from_banner_plan(
    plan_path: str | Path,
    *,
    statuses: Sequence[str] = ("next",),
    names: NameIndex | None = None,
    local_datetime: datetime | None = None,
) -> list[str]:
    name_index = names or NameIndex({}, {}, {})
    status_set = {str(status).strip().lower() for status in statuses if str(status).strip()}
    data = load_config(plan_path)
    planned: list[str] = []
    for phase in effective_banner_phases(data, now=local_datetime):
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
    quality_out: dict[str, Any] | None = None,
) -> list[TeamSignatureAggregate]:
    _validate_min_a_app_rate(min_a_app_rate)
    out = Path(data_dir)
    names = load_name_index(out)
    team_path = out / "team_rank_dedup_unordered.csv"
    if not team_path.exists():
        raise FileNotFoundError(f"队伍证据表不存在：{team_path}")
    rows = _read_csv(team_path)
    columns = list(rows[0].keys()) if rows else _read_header(team_path)
    char_columns = _detect_team_columns(columns)
    if len(char_columns) not in {3, 4}:
        raise ValueError(f"队伍证据表需要 3 或 4 个 char_<n>_slug 列：{team_path}")
    if "mode" not in columns:
        raise ValueError(f"队伍证据表缺少 mode 列：{team_path}")
    metric_column = _detect_metric_column(columns)
    stability_roles = _load_stability_roles(out, names)
    # A team signature may appear in several endgame modes, but their score
    # scales and confidence breadth are not interchangeable.  Keep one
    # aggregate per mode so best_score, medians and A/B confidence never gain
    # strength by mixing SD/DA (or distinct HSR modes).
    grouped: dict[tuple[str, tuple[str, ...], str], list[dict[str, Any]]] = defaultdict(list)
    quality = {
        "rows_total": len(rows),
        "rows_included": 0,
        "skipped_app_rate": 0,
        "skipped_empty_team": 0,
        "skipped_partial_team": 0,
        "skipped_duplicate_agents": 0,
        "missing_or_non_finite_score_rows": 0,
        "sentinel_score_rows": 0,
        "alias_entries": len(names.aliases),
        "stability_catalog_entries": len(stability_roles),
        "metric_name": metric_column,
        "modes": [],
    }

    for row in rows:
        app_rate = parse_percent(row.get("app_rate"))
        if app_rate is None or not math.isfinite(float(app_rate)) or app_rate <= 0:
            quality["skipped_app_rate"] += 1
            continue
        team = tuple(canonical_slug(str(row.get(column) or ""), names) for column in char_columns if row.get(column))
        team = tuple(slug for slug in team if slug)
        if not team:
            quality["skipped_empty_team"] += 1
            continue
        if len(team) != len(char_columns):
            quality["skipped_partial_team"] += 1
            continue
        if len(set(team)) != len(team):
            quality["skipped_duplicate_agents"] += 1
            continue
        agent_signature_tuple = tuple(sorted(team))
        bangboo_slug = canonical_slug(str(row.get("bangboo_slug") or ""), names)
        mode = str(row.get("mode") or "").strip().lower()
        if not mode:
            raise ValueError(f"队伍证据行缺少 mode：{team_path}")
        if mode not in MODE_CONFIDENCE_POLICIES:
            raise ValueError(f"队伍证据行包含未声明 mode policy：{mode}")
        score = parse_number(row.get(metric_column)) if metric_column else None
        if score is not None and not math.isfinite(float(score)):
            score = None
        sentinels = sentinel_values if sentinel_values is not None else _default_sentinels(mode, metric_column)
        score_sentinel = _is_sentinel(score, sentinels)
        quality["rows_included"] += 1
        if score is None:
            quality["missing_or_non_finite_score_rows"] += 1
        if score_sentinel:
            quality["sentinel_score_rows"] += 1
        grouped[(mode, agent_signature_tuple, bangboo_slug)].append(
            {
                "row": row,
                "app_rate": app_rate,
                "rank": _int_or_none(row.get("rank")),
                "score": score,
                "score_sentinel": score_sentinel,
                "metric_direction": _metric_direction(row, metric_column),
                "duplicate_count": max(1, _int_or_none(row.get("duplicate_count")) or 1),
            }
        )

    aggregates: list[TeamSignatureAggregate] = []
    for (mode, agent_signature_tuple, bangboo_slug), items in grouped.items():
        app_rates = [item["app_rate"] for item in items if item.get("app_rate") is not None]
        non_sentinel_scores = [item["score"] for item in items if not item["score_sentinel"] and item.get("score") is not None]
        sentinel_count = sum(1 for item in items if item["score_sentinel"])
        valid_score_ratio = len(non_sentinel_scores) / len(items) if items else 0.0
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
        modes = [mode] if mode else []
        mode_names = sorted({str(item["row"].get("mode_cn") or "") for item in items if item["row"].get("mode_cn")})
        phase_names = sorted({str(item["row"].get("phase_name") or "") for item in items if item["row"].get("phase_name")})
        scopes = sorted({str(item["row"].get("scope") or item["row"].get("sub_mode") or "") for item in items if item["row"].get("scope") or item["row"].get("sub_mode")})
        boss_keys = sorted({_boss_key(item["row"]) for item in items if _boss_key(item["row"])})
        source_kinds = sorted({str(item["row"].get("source_kind") or "") for item in items if item["row"].get("source_kind")})
        observation_keys = sorted({_observation_key(item["row"]) for item in items})
        stability_status = _stability_status(agent_signature_tuple, stability_roles, mode=mode)
        confidence, evidence_comment, risk_comment = _classify_aggregate(
            mode=mode,
            record_count=len(items),
            phase_count=len(phase_keys),
            mode_count=len(modes),
            scope_count=len(scopes),
            boss_count=len(boss_keys),
            max_app_rate=max(app_rates, default=None),
            median_app_rate=median(app_rates) if app_rates else None,
            non_sentinel_score_count=len(non_sentinel_scores),
            sentinel_score_count=sentinel_count,
            modes=modes,
            min_a_app_rate=min_a_app_rate,
            stability_status=stability_status,
        )
        if metric_direction == "mixed":
            risk_comment = _append_comment(risk_comment, "混合指标方向，best_score 不做跨方向比较")
        full_signature = _full_team_signature(agent_signature_tuple, bangboo_slug)
        evidence_key = f"{mode or 'unknown'}|{full_signature}"
        aggregates.append(
            TeamSignatureAggregate(
                mode=mode,
                mode_cn=mode_names[0] if mode_names else "",
                evidence_key=evidence_key,
                team_signature=full_signature,
                agent_signature="|".join(agent_signature_tuple),
                full_team_signature=full_signature,
                team_slugs=agent_signature_tuple,
                team_cn=tuple(_name_cn(slug, names) for slug in agent_signature_tuple),
                bangboo_slug=bangboo_slug,
                bangboo_name_cn=_bangboo_name_cn(bangboo_slug, names, items),
                record_count=len(items),
                duplicate_count=sum(item["duplicate_count"] for item in items),
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
                metric_name=metric_column,
                metric_direction=metric_direction,
                non_sentinel_score_count=len(non_sentinel_scores),
                sentinel_score_count=sentinel_count,
                valid_score_ratio=valid_score_ratio,
                confidence=confidence,
                modes=tuple(modes),
                phase_versions=tuple(phase_keys),
                phase_names=tuple(phase_names),
                scopes=tuple(scopes),
                source_kinds=tuple(source_kinds),
                observation_keys=tuple(observation_keys),
                stability_status=stability_status,
                evidence_comment=evidence_comment,
                risk_comment=risk_comment,
            )
        )
    quality["modes"] = sorted({aggregate.mode for aggregate in aggregates if aggregate.mode})
    if quality_out is not None:
        quality_out.clear()
        quality_out.update(quality)
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
    built_slugs: Iterable[str] | None = None,
    build_state_known: bool = False,
) -> EvidencePool:
    names = load_name_index(data_dir)
    owned = {canonical_slug(slug, names) for slug in owned_slugs if canonical_slug(slug, names)}
    planned_order = [canonical_slug(slug, names) for slug in planned_slugs if canonical_slug(slug, names)]
    planned_order = list(dict.fromkeys(planned_order))
    target = owned | set(planned_order)
    owned_bangboo = {canonical_slug(slug, names) for slug in (owned_bangboo_slugs or []) if canonical_slug(slug, names)}
    built = {canonical_slug(slug, names) for slug in (built_slugs or []) if canonical_slug(slug, names)}
    data_quality: dict[str, Any] = {}
    aggregates = build_team_signature_aggregates(
        data_dir,
        sentinel_values=sentinel_values,
        min_a_app_rate=min_a_app_rate,
        quality_out=data_quality,
    )
    records: list[EvidenceRecord] = []
    for aggregate in aggregates:
        team_set = set(aggregate.team_slugs)
        missing = tuple(slug for slug in aggregate.team_slugs if slug not in target)
        if missing and not include_missing:
            continue
        dependency = tuple(slug for slug in planned_order if slug in team_set and slug not in owned) or ("none",)
        risk_comment = aggregate.risk_comment
        if missing:
            risk_comment = _append_comment(risk_comment, "缺目标账号成员：" + ", ".join(missing))
        bangboo_checked = _bangboo_checked(
            aggregate.bangboo_slug,
            owned_bangboo,
            ownership_known=bangboo_ownership_known,
        )
        unbuilt = tuple(slug for slug in aggregate.team_slugs if slug not in built) if build_state_known else ()
        build_checked = "已读取" if build_state_known else "未提供"
        confidence = _account_confidence(
            aggregate.confidence,
            missing=bool(missing),
            build_state_known=build_state_known,
            unbuilt=bool(unbuilt),
        )
        if bangboo_checked == "缺邦布":
            risk_comment = _append_comment(risk_comment, "Bangboo 记录缺拥有校验：" + aggregate.bangboo_slug)
        elif bangboo_checked == "邦布未校验":
            risk_comment = _append_comment(risk_comment, "Bangboo 未参与账号覆盖校验")
        if unbuilt:
            risk_comment = _append_comment(risk_comment, "已拥有但未标记已培养：" + ", ".join(unbuilt))
        elif not build_state_known:
            risk_comment = _append_comment(risk_comment, "Box 未提供显式 build 状态，不推断已可上场")
        records.append(
            EvidenceRecord(
                evidence_id=_stable_evidence_id(aggregate.evidence_key, aggregate.mode),
                scenario=scenario,
                mode=aggregate.mode,
                mode_cn=aggregate.mode_cn,
                evidence_key=aggregate.evidence_key,
                team_signature=aggregate.team_signature,
                agent_signature=aggregate.agent_signature,
                full_team_signature=aggregate.full_team_signature,
                team_slugs=aggregate.team_slugs,
                team_cn=aggregate.team_cn,
                bangboo_slug=aggregate.bangboo_slug,
                bangboo_name_cn=aggregate.bangboo_name_cn,
                bangboo_checked=bangboo_checked,
                owned_count=sum(1 for slug in aggregate.team_slugs if slug in owned),
                built_count=sum(1 for slug in aggregate.team_slugs if slug in built),
                build_checked=build_checked,
                unbuilt_parts=unbuilt or ("none",),
                plan_dependency=dependency,
                missing_parts=missing or ("none",),
                source_confidence=aggregate.confidence,
                confidence=confidence,
                record_count=aggregate.record_count,
                duplicate_count=aggregate.duplicate_count,
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
                metric_name=aggregate.metric_name,
                metric_direction=aggregate.metric_direction,
                non_sentinel_score_count=aggregate.non_sentinel_score_count,
                sentinel_score_count=aggregate.sentinel_score_count,
                valid_score_ratio=aggregate.valid_score_ratio,
                modes=aggregate.modes,
                phase_versions=aggregate.phase_versions,
                phase_names=aggregate.phase_names,
                scopes=aggregate.scopes,
                source_kinds=aggregate.source_kinds,
                observation_keys=aggregate.observation_keys,
                stability_status=aggregate.stability_status,
                evidence_comment=aggregate.evidence_comment,
                risk_comment=risk_comment,
            )
        )
    records.sort(key=_coverage_sort_key)
    summary = {
        "method_version": EVIDENCE_METHOD_VERSION,
        "data_dir": str(Path(data_dir)),
        "team_source": str(Path(data_dir) / "team_rank_dedup_unordered.csv"),
        "scenario": scenario,
        "owned_count": len(owned),
        "planned": planned_order,
        "target_count": len(target),
        "aggregate_count": len(aggregates),
        "composition_count": len({aggregate.full_team_signature for aggregate in aggregates}),
        "included_records": len(records),
        "confidence_counts": dict(Counter(record.confidence for record in records)),
        "source_confidence_counts": dict(Counter(record.source_confidence for record in records)),
        "dependency_counts": dict(Counter(",".join(record.plan_dependency) for record in records)),
        "mode_counts": dict(Counter(record.mode for record in records if record.mode)),
        "include_missing": include_missing,
        "min_a_app_rate": min_a_app_rate if min_a_app_rate is not None else 10.0,
        "bangboo_ownership_known": bangboo_ownership_known,
        "build_state_known": build_state_known,
        "data_quality": data_quality,
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
    build_known, built = load_built_slugs(box_path, names)
    return build_evidence_pool(
        data_dir,
        owned_slugs=owned,
        planned_slugs=planned_slugs,
        scenario=scenario,
        include_missing=include_missing,
        min_a_app_rate=min_a_app_rate,
        owned_bangboo_slugs=owned_bangboo,
        bangboo_ownership_known=bangboo_known,
        built_slugs=built,
        build_state_known=build_known,
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
    local_datetime: datetime | None = None,
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
    _atomic_write_batch(
        {
            output: _platform_text_bytes(
                format_evidence_report(pool, title=title, limit=limit, local_datetime=local_datetime)
            )
        }
    )
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
    local_datetime: datetime | None = None,
) -> tuple[EvidencePool, EvidencePool]:
    names = load_name_index(data_dir)
    owned = load_owned_slugs(box_path, names)
    bangboo_known, owned_bangboo = load_owned_bangboo_slugs(box_path, names)
    build_known, built = load_built_slugs(box_path, names)
    current_pool = build_evidence_pool(
        data_dir,
        owned_slugs=owned,
        planned_slugs=[],
        scenario="current_box",
        include_missing=False,
        min_a_app_rate=min_a_app_rate,
        owned_bangboo_slugs=owned_bangboo,
        bangboo_ownership_known=bangboo_known,
        built_slugs=built,
        build_state_known=build_known,
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
        built_slugs=built,
        build_state_known=build_known,
    )
    current_path = Path(current_output_path)
    target_path = Path(target_output_path)
    output_paths = [current_path, target_path]
    if aggregate_output_path:
        output_paths.append(Path(aggregate_output_path))
    _validate_distinct_paths(output_paths)
    generated_at = local_datetime or datetime.now()
    outputs = {
        current_path: _platform_text_bytes(
            format_coverage_report(current_pool, title="当前 Box 队伍覆盖", limit=limit, local_datetime=generated_at)
        ),
        target_path: _platform_text_bytes(
            format_coverage_report(target_pool, title="目标 Box 队伍覆盖", limit=limit, local_datetime=generated_at)
        ),
    }
    if aggregate_output_path:
        outputs[Path(aggregate_output_path)] = format_team_signature_aggregates_csv(target_pool.aggregates)
    _atomic_write_batch(outputs)
    return current_pool, target_pool


def write_team_signature_aggregates_csv(aggregates: Sequence[TeamSignatureAggregate], output_path: str | Path) -> None:
    _atomic_write_batch({Path(output_path): format_team_signature_aggregates_csv(aggregates)})


def format_team_signature_aggregates_csv(aggregates: Sequence[TeamSignatureAggregate]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=AGGREGATE_COLUMNS)
    writer.writeheader()
    for aggregate in aggregates:
        writer.writerow(_aggregate_row(aggregate))
    return handle.getvalue().encode("utf-8-sig")


def format_evidence_report(
    pool: EvidencePool,
    *,
    title: str = "证据池队伍覆盖报告",
    limit: int = 0,
    local_datetime: datetime | None = None,
) -> str:
    return format_coverage_report(pool, title=title, limit=limit, local_datetime=local_datetime)


def format_coverage_report(
    pool: EvidencePool,
    *,
    title: str = "队伍覆盖报告",
    limit: int = 0,
    local_datetime: datetime | None = None,
) -> str:
    summary = pool.summary
    quality = summary.get("data_quality") or {}
    records = pool.records[:limit] if limit and limit > 0 else pool.records
    lines = [
        f"# {title}",
        "",
        f"- 生成时间：{(local_datetime or datetime.now()).isoformat(timespec='seconds')}",
        f"- 方法版本：`{summary.get('method_version')}`",
        f"- scenario：`{summary.get('scenario')}`",
        f"- 队伍数据源：`{summary.get('team_source')}`",
        f"- team signature 聚合数：{summary.get('aggregate_count', 0)}",
        f"- composition 数：{summary.get('composition_count', 0)}",
        f"- 当前拥有：{summary.get('owned_count', 0)}；计划角色：{', '.join(summary.get('planned') or []) or 'none'}；目标账号角色数：{summary.get('target_count', 0)}",
        f"- 可组 team signature：{summary.get('included_records', 0)}",
        f"- A 档 min_app_rate 阈值：{_threshold_text(summary.get('min_a_app_rate'))}",
        f"- Bangboo 拥有信息：{'已读取' if summary.get('bangboo_ownership_known') else '未提供，报告标记为邦布未校验'}",
        f"- Build 信息：{'已读取显式 built/builds' if summary.get('build_state_known') else '未提供，不从拥有或等级推断已可上场'}",
        f"- 模式分布：{_dict_text(summary.get('mode_counts') or {})}",
        f"- 数据质量：原始 {quality.get('rows_total', 0)} 行 / 纳入 {quality.get('rows_included', 0)} 行；无效 app_rate {quality.get('skipped_app_rate', 0)}；空队 {quality.get('skipped_empty_team', 0)}；不完整队 {quality.get('skipped_partial_team', 0)}；重复角色 {quality.get('skipped_duplicate_agents', 0)}。",
        f"- 表现质量：metric `{quality.get('metric_name') or 'none'}`；missing/non-finite {quality.get('missing_or_non_finite_score_rows', 0)}；sentinel {quality.get('sentinel_score_rows', 0)}。",
        f"- Alias/稳定性目录：alias {quality.get('alias_entries', 0)}；stability role {quality.get('stability_catalog_entries', 0)}。",
        f"- 置信度分布：{_dict_text(summary.get('confidence_counts') or {})}",
        f"- 源证据置信度：{_dict_text(summary.get('source_confidence_counts') or {})}",
        f"- 计划依赖分布：{_dict_text(summary.get('dependency_counts') or {})}",
        "",
        "## 置信度口径",
        "",
        "- A：单一 mode 内跨多期、多 Boss/范围且出场率较高，非 sentinel 分数充足并有明确稳定组件。",
        "- B+：重复度和出场率都较好，但广度或稳定性略弱于 A。",
        "- B：有真实记录和一定重复度，可证明可组与存在感，但不能直接推断长期 auto 稳定。",
        "- B-：真实记录稀疏、出场率低或 sentinel 较多，只能作为弱证据。",
        "- C：缺目标账号成员、无有效表现，或证据不足以支撑覆盖结论。",
        "",
        "## 数据口径",
        "",
        "- 先按无序三代理人 `agent_signature` 做账号覆盖，再按三代理人 + Bangboo 的 `full_team_signature` 聚合真实队伍证据。",
        "- planned 只作为 target scenario 的增量成员，不和 current_box 结论混写；target 表保留 `plan_dependency`。",
        "- `0`/缺失表现按 sentinel / missing 处理；`99.99` 只是 HSR `avg_round` sentinel，ZZZ 合法分数 `99.99` 仍是有效表现。",
        "- `metric_direction` 控制 best_score 取值方向；SD/DA 本地原始 JSON 的 `avg_round` 实为分数，按 `higher_better` 处理，但 SD/DA 分数仍不互相横比。",
        "- 同一 composition 在不同 mode 生成独立 `evidence_key=mode|full_team_signature`；分数、出场率与置信度均不跨模式合并。",
        "- A 需满足模式策略的重复度、非 sentinel 比例且有明确稳定组件；稳定性未知时最高 B+。",
        "- `source_confidence` 表示真实队伍数据强度；正式 `confidence` 再结合目标账号 build readiness，未提供或未培养会将源 A/B+ 降为 B。",
        "- Bangboo 写入 full evidence signature；只有 box 提供 Bangboo 拥有信息时才校验，否则标记 `邦布未校验`，不影响三代理人可组判断。",
        "",
        "## 覆盖记录",
        "",
        _markdown_table_row(COVERAGE_COLUMNS),
        _markdown_table_row(["---"] * len(COVERAGE_COLUMNS)),
    ]
    if not records:
        empty = {column: "-" for column in COVERAGE_COLUMNS}
        for column in (
            "owned_count",
            "built_count",
            "record_count",
            "duplicate_count",
            "snapshot_count",
            "phase_count",
            "scope_count",
            "boss_count",
            "source_kind_count",
            "non_sentinel_score_count",
            "sentinel_score_count",
        ):
            empty[column] = "0"
        empty["evidence_comment"] = "无可组真实队伍记录"
        empty["risk_comment"] = "检查 box、计划角色或数据源"
        lines.append(_markdown_table_row([empty[column] for column in COVERAGE_COLUMNS]))
    for record in records:
        values = _coverage_record_values(record)
        lines.append(_markdown_table_row([values[column] for column in COVERAGE_COLUMNS]))
    lines.append("")
    return "\n".join(lines)


def _coverage_record_values(record: EvidenceRecord) -> dict[str, str]:
    return {
        "evidence_id": record.evidence_id,
        "evidence_key": _md(record.evidence_key),
        "scenario": _md(record.scenario),
        "mode": _md(record.mode or "-"),
        "mode_cn": _md(record.mode_cn or "-"),
        "source_confidence": record.source_confidence,
        "confidence": record.confidence,
        "team_signature": _md(record.team_signature),
        "agent_signature": _md(record.agent_signature),
        "full_team_signature": _md(record.full_team_signature),
        "team_slugs": _md(", ".join(record.team_slugs)),
        "team_cn": _md(" / ".join(record.team_cn)),
        "bangboo_slug": _md(record.bangboo_slug or "-"),
        "bangboo_name_cn": _md(record.bangboo_name_cn or "-"),
        "bangboo_checked": _md(record.bangboo_checked),
        "owned_count": str(record.owned_count),
        "built_count": str(record.built_count),
        "build_checked": _md(record.build_checked),
        "unbuilt_parts": _md(", ".join(record.unbuilt_parts)),
        "plan_dependency": _md(", ".join(record.plan_dependency)),
        "missing_parts": _md(", ".join(record.missing_parts)),
        "record_count": str(record.record_count),
        "duplicate_count": str(record.duplicate_count),
        "snapshot_count": str(record.snapshot_count),
        "phase_count": str(record.phase_count),
        "scope_count": str(record.scope_count),
        "boss_count": str(record.boss_count),
        "source_kind_count": str(record.source_kind_count),
        "max_app_rate": _number_text(record.max_app_rate),
        "median_app_rate": _number_text(record.median_app_rate),
        "best_rank": str(record.best_rank) if record.best_rank is not None else "-",
        "best_score": _number_text(record.best_score),
        "metric_name": _md(record.metric_name or "-"),
        "metric_direction": _md(record.metric_direction),
        "non_sentinel_score_count": str(record.non_sentinel_score_count),
        "sentinel_score_count": str(record.sentinel_score_count),
        "valid_score_ratio": _number_text(record.valid_score_ratio),
        "phase_versions": _md(", ".join(record.phase_versions)),
        "phase_names": _md(", ".join(record.phase_names)),
        "scopes": _md(", ".join(record.scopes)),
        "source_kinds": _md(", ".join(record.source_kinds)),
        "observation_keys": _md("; ".join(record.observation_keys)),
        "stability_status": _md(record.stability_status),
        "evidence_comment": _md(record.evidence_comment),
        "risk_comment": _md(record.risk_comment),
    }


def _markdown_table_row(values: Sequence[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def _classify_aggregate(
    *,
    mode: str,
    record_count: int,
    phase_count: int,
    mode_count: int,
    scope_count: int,
    boss_count: int,
    max_app_rate: float | None,
    median_app_rate: float | None,
    non_sentinel_score_count: int,
    sentinel_score_count: int,
    modes: Sequence[str] = (),
    min_a_app_rate: float | dict[str, float] | None = None,
    stability_status: str = "unknown",
) -> tuple[str, str, str]:
    max_app = max_app_rate or 0.0
    median_app = median_app_rate or 0.0
    min_a = _min_a_threshold(modes, min_a_app_rate)
    min_b_plus = max(1.0, min_a / 2)
    policy = MODE_CONFIDENCE_POLICIES.get(mode, DEFAULT_CONFIDENCE_POLICY)
    total_scores = non_sentinel_score_count + sentinel_score_count
    sentinel_ratio = sentinel_score_count / total_scores if total_scores else 1.0
    breadth_count = max(boss_count, scope_count)
    notes = [
        f"record_count={record_count}",
        f"phase_count={phase_count}",
        f"mode_count={mode_count}",
        f"boss_count={boss_count}",
        f"scope_count={scope_count}",
        f"valid_score_count={non_sentinel_score_count}",
        f"sentinel_ratio={sentinel_ratio:g}",
        f"stability_status={stability_status}",
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
    if stability_status == "absent":
        risks.append("未检出稳定组件，不给 A")
    elif stability_status == "unknown":
        risks.append("缺角色职能数据，稳定组件未校验，不给 A")
    stability_allows_a = not policy.require_stability_for_a or stability_status == "present"
    if (
        record_count >= policy.a_records
        and phase_count >= policy.a_phases
        and breadth_count >= policy.a_breadth
        and non_sentinel_score_count >= policy.a_valid_scores
        and sentinel_ratio <= policy.a_max_sentinel_ratio
        and max_app >= min_a
        and median_app >= 1
        and stability_allows_a
    ):
        return "A", "；".join(notes), "；".join(risks) if risks else "无"
    if (
        record_count >= policy.b_plus_records
        and phase_count >= policy.b_plus_phases
        and breadth_count >= policy.b_plus_breadth
        and non_sentinel_score_count >= policy.b_plus_valid_scores
        and sentinel_ratio <= policy.b_plus_max_sentinel_ratio
        and max_app >= min_b_plus
    ):
        return "B+", "；".join(notes), "；".join(risks) if risks else "重复度较好，但未达到 A 档广度/强度"
    if record_count >= 3 and phase_count >= 2 and max_app >= 1:
        return "B", "；".join(notes), "；".join(risks) if risks else "有重复记录，可作普通证据"
    if record_count >= 1:
        risks.append("记录稀疏或出场率较低")
        return "B-", "；".join(notes), "；".join(risks)
    return "C", "；".join(notes), "无真实记录"


def _aggregate_row(aggregate: TeamSignatureAggregate) -> dict[str, Any]:
    return {
        "mode": aggregate.mode,
        "mode_cn": aggregate.mode_cn,
        "evidence_key": aggregate.evidence_key,
        "team_signature": aggregate.team_signature,
        "agent_signature": aggregate.agent_signature,
        "full_team_signature": aggregate.full_team_signature,
        "team_slugs": ", ".join(aggregate.team_slugs),
        "team_cn": " / ".join(aggregate.team_cn),
        "bangboo_slug": aggregate.bangboo_slug,
        "bangboo_name_cn": aggregate.bangboo_name_cn,
        "confidence": aggregate.confidence,
        "record_count": aggregate.record_count,
        "duplicate_count": aggregate.duplicate_count,
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
        "metric_name": aggregate.metric_name,
        "metric_direction": aggregate.metric_direction,
        "non_sentinel_score_count": aggregate.non_sentinel_score_count,
        "sentinel_score_count": aggregate.sentinel_score_count,
        "valid_score_ratio": _number_text(aggregate.valid_score_ratio),
        "modes": ", ".join(aggregate.modes),
        "phase_versions": ", ".join(aggregate.phase_versions),
        "phase_names": ", ".join(aggregate.phase_names),
        "scopes": ", ".join(aggregate.scopes),
        "source_kinds": ", ".join(aggregate.source_kinds),
        "observation_keys": "; ".join(aggregate.observation_keys),
        "stability_status": aggregate.stability_status,
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


def _stable_evidence_id(evidence_key: str, mode: str) -> str:
    digest = hashlib.sha256(evidence_key.encode("utf-8")).hexdigest()[:10].upper()
    label = re.sub(r"[^A-Za-z0-9]+", "-", mode.upper()).strip("-") or "UNKNOWN"
    return f"E-{label}-{digest}"


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


def _observation_key(row: dict[str, Any]) -> str:
    values = (
        row.get("snapshot_id"),
        row.get("mode"),
        row.get("phase_ver"),
        row.get("phase_name"),
        row.get("scope") or row.get("sub_mode"),
        row.get("source_file"),
        row.get("rank"),
    )
    return ":".join(str(value or "-").strip() for value in values)


def _load_stability_roles(data_dir: Path, names: NameIndex) -> dict[str, str]:
    roles: dict[str, str] = {}
    for row in _read_csv(data_dir / "prydwen_tier_current.csv"):
        slug = canonical_slug(str(row.get("character_slug") or ""), names)
        if not slug:
            continue
        text = " ".join(
            str(row.get(key) or "").strip().lower()
            for key in ("role_group", "role_group_cn", "style", "style_cn", "path", "path_cn")
        )
        roles[slug] = f"{roles.get(slug, '')} {text}".strip()
    return roles


def _stability_status(team_slugs: Sequence[str], stability_roles: dict[str, str], *, mode: str) -> str:
    known = [slug for slug in team_slugs if slug in stability_roles]
    if mode in {"moc", "pf", "as", "aa"}:
        markers = (
            "sustain",
            "healer",
            "preservation",
            "abundance",
            "tank",
            "存护",
            "丰饶",
            "治疗",
            "生存",
            "护盾",
        )
    else:
        markers = (
            "support",
            "stun",
            "defense",
            "sustain",
            "healer",
            "辅助",
            "支援",
            "击破",
            "防护",
            "治疗",
        )
    if any(any(marker in stability_roles[slug] for marker in markers) for slug in known):
        return "present"
    if len(known) == len(team_slugs) and known:
        return "absent"
    return "unknown"


def _is_sentinel(value: Any, sentinel_values: set[float]) -> bool:
    number = _float_or_none(value)
    return number is None or number in sentinel_values


def _default_sentinels(mode: str, metric_name: str) -> set[float]:
    if mode in {"sd", "da"} or metric_name in {"avg_score", "score"}:
        return {0.0}
    return DEFAULT_SENTINELS


def _bangboo_checked(bangboo_slug: str, owned_bangboo: set[str], *, ownership_known: bool) -> str:
    if not bangboo_slug:
        return "无邦布记录"
    if not ownership_known:
        return "邦布未校验"
    return "已拥有" if bangboo_slug in owned_bangboo else "缺邦布"


def _account_confidence(
    source_confidence: str,
    *,
    missing: bool,
    build_state_known: bool,
    unbuilt: bool,
) -> str:
    if missing:
        return "C"
    if (not build_state_known or unbuilt) and source_confidence in {"A", "B+"}:
        return "B"
    return source_confidence


def _name_cn(slug: str, names: NameIndex) -> str:
    return names.names_cn.get(slug) or slug


def _aggregate_sort_key(aggregate: TeamSignatureAggregate) -> tuple[int, float, int, str, str]:
    return (
        CONFIDENCE_ORDER.get(aggregate.confidence, 9),
        -(aggregate.max_app_rate or 0),
        -(aggregate.record_count),
        aggregate.mode,
        aggregate.team_signature,
    )


def _coverage_sort_key(record: EvidenceRecord) -> tuple[int, str, float, int, str, str]:
    dependency_group = "0" if record.plan_dependency == ("none",) else "1"
    return (
        CONFIDENCE_ORDER.get(record.confidence, 9),
        dependency_group,
        -(record.max_app_rate or 0),
        -record.record_count,
        record.mode,
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


def _validate_min_a_app_rate(value: float | dict[str, float] | None) -> None:
    values = value.values() if isinstance(value, dict) else (() if value is None else (value,))
    for item in values:
        number = _float_or_none(item)
        if number is None or number < 0:
            raise ValueError(f"invalid min_a_app_rate: {item}")


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
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
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


def _explicit_built(value: Any, *, allow_payload_mapping: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, dict):
        if "built" in value:
            return _explicit_built(value.get("built"), allow_payload_mapping=False)
        return allow_payload_mapping and bool(value)
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in {"1", "true", "yes", "y", "built", "ready", "已培养"}


def _platform_text_bytes(text: str) -> bytes:
    if os.linesep != "\n":
        text = text.replace("\n", os.linesep)
    return text.encode("utf-8")


def _atomic_write_batch(outputs: dict[Path, bytes]) -> None:
    resolved: dict[Path, tuple[Path, bytes]] = {}
    for raw_path, content in outputs.items():
        path = Path(raw_path)
        key = path.resolve(strict=False)
        if key in resolved:
            raise ValueError(f"输出路径冲突：{path}")
        resolved[key] = (path, content)

    token = uuid4().hex
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for path, content in resolved.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            stage = path.with_name(f".{path.name}.{token}.stage")
            stage.write_bytes(content)
            staged[path] = stage
        for path, _ in resolved.values():
            backup = path.with_name(f".{path.name}.{token}.backup")
            if path.exists():
                os.replace(path, backup)
                backups[path] = backup
            os.replace(staged[path], path)
            installed.append(path)
    except Exception:
        for path in reversed(installed):
            path.unlink(missing_ok=True)
        for path, backup in backups.items():
            if backup.exists():
                os.replace(backup, path)
        raise
    else:
        for backup in backups.values():
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                # The new batch is already committed. A stale hidden backup is
                # safer than rolling back after some backups were deleted.
                pass
    finally:
        for stage in staged.values():
            stage.unlink(missing_ok=True)


def _validate_distinct_paths(paths: Sequence[Path]) -> None:
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            raise ValueError(f"输出路径冲突：{path}")
        seen.add(resolved)
