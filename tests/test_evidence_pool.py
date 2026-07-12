import builtins
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re

import pytest

from miho_core.evidence import (
    _atomic_write_batch,
    COVERAGE_COLUMNS,
    EvidencePool,
    build_evidence_pool_from_paths,
    build_team_signature_aggregates,
    format_evidence_report,
    load_name_index,
    load_built_slugs,
    load_planned_slugs_from_banner_plan,
    write_coverage_reports,
)
from miho_core.box import _load_yaml
from zzz_endgame_exporter.cli import main


def test_evidence_pool_includes_owned_and_planned_records(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)

    pool = build_evidence_pool_from_paths(
        out,
        box_path=box,
        planned_slugs=["sunna"],
        include_missing=True,
    )

    owned_team = [record for record in pool.records if set(record.team_slugs) == {"miyabi", "lucy", "nicole-demara"}][0]
    planned_team = [record for record in pool.records if set(record.team_slugs) == {"miyabi", "lucy", "sunna"}][0]
    missing_team = [record for record in pool.records if "zhao" in record.team_slugs][0]

    assert owned_team.source_confidence == "B+"
    assert owned_team.confidence == "B"
    assert owned_team.mode == "sd"
    assert owned_team.plan_dependency == ("none",)
    assert owned_team.agent_signature == "lucy|miyabi|nicole-demara"
    assert owned_team.full_team_signature == "lucy|miyabi|nicole-demara|bangboo:biggest-fan"
    assert owned_team.team_signature == owned_team.full_team_signature
    assert owned_team.bangboo_slug == "biggest-fan"
    assert owned_team.bangboo_name_cn == "阿饭"
    assert owned_team.bangboo_checked == "邦布未校验"
    assert owned_team.record_count == 6
    assert owned_team.duplicate_count == 6
    assert owned_team.snapshot_count == 3
    assert owned_team.phase_count == 3
    assert owned_team.boss_count == 2
    assert owned_team.non_sentinel_score_count == 6
    assert owned_team.sentinel_score_count == 0
    assert owned_team.metric_direction == "higher_better"
    assert owned_team.best_score == 30500
    assert planned_team.confidence == "C"
    assert planned_team.plan_dependency == ("sunna",)
    assert planned_team.sentinel_score_count == 1
    assert missing_team.confidence == "C"
    assert missing_team.missing_parts == ("zhao",)
    assert pool.summary["aggregate_count"] == 3
    assert pool.summary["composition_count"] == 3
    assert pool.summary["data_quality"]["rows_total"] == 8
    assert pool.summary["data_quality"]["rows_included"] == 8

    report = format_evidence_report(pool, title="测试证据池")
    assert "plan_dependency" in report
    assert "team signature" in report
    assert "full_team_signature" in report
    assert "bangboo_checked" in report
    assert "邦布未校验" in report
    assert "metric_direction" in report
    assert "sentinel" in report


def test_zzz_evidence_cli_writes_markdown(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)
    output = tmp_path / "evidence.md"

    result = main(
        [
            "evidence",
            "--box",
            str(box),
            "--out",
            str(out),
            "--planned-slugs",
            "sunna",
            "--min-a-app-rate",
            "sd=5,da=10",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    text = output.read_text(encoding="utf-8")
    assert "# 绝区零目标账号证据池队伍覆盖" in text
    assert "lucy, miyabi, nicole-demara" in text
    assert "lucy, miyabi, sunna" in text
    assert "A 档 min_app_rate 阈值：sd:5, da:10" in text
    assert "min_a_app_rate=5" in text


def test_zzz_coverage_cli_writes_split_reports(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)

    result = main(
        [
            "coverage",
            "--box",
            str(box),
            "--out",
            str(out),
            "--planned-slugs",
            "sunna",
            "--min-a-app-rate",
            "sd=5;da=10",
        ]
    )

    assert result == 0
    current_text = (out / "current_box_team_coverage.md").read_text(encoding="utf-8")
    target_text = (out / "target_box_team_coverage.md").read_text(encoding="utf-8")
    aggregate_csv = (out / "team_signature_aggregates.csv").read_text(encoding="utf-8-sig")
    assert "scenario：`current_box`" in current_text
    assert "scenario：`target_box`" in target_text
    assert "lucy, miyabi, sunna" not in current_text
    assert "lucy, miyabi, sunna" in target_text
    assert "bangboo_slug" in target_text
    assert "full_team_signature" in target_text
    assert "metric_direction" in target_text
    assert "邦布未校验" in target_text
    assert "A 档 min_app_rate 阈值：sd:5, da:10" in target_text
    assert "mode,mode_cn,evidence_key,team_signature,agent_signature,full_team_signature" in aggregate_csv
    assert "record_count,duplicate_count,snapshot_count,phase_count,mode_count,scope_count,boss_count" in aggregate_csv


def test_min_a_app_rate_changes_classification(tmp_path):
    out = _write_threshold_fixture(tmp_path)

    default_aggregate = [row for row in build_team_signature_aggregates(out) if row.modes == ("sd",)][0]
    relaxed_aggregate = [
        row for row in build_team_signature_aggregates(out, min_a_app_rate=5) if row.modes == ("sd",)
    ][0]

    assert default_aggregate.confidence == "B+"
    assert relaxed_aggregate.confidence == "A"
    assert "min_a_app_rate=5" in relaxed_aggregate.evidence_comment


def test_same_team_is_not_numerically_aggregated_across_modes(tmp_path):
    out = _write_cross_mode_fixture(tmp_path)

    aggregates = build_team_signature_aggregates(out, min_a_app_rate={"sd": 5, "da": 10})

    assert len(aggregates) == 2
    by_mode = {aggregate.modes: aggregate for aggregate in aggregates}
    assert by_mode[("sd",)].best_score == 33333
    assert by_mode[("da",)].best_score == 999999
    assert by_mode[("sd",)].record_count == 1
    assert by_mode[("da",)].record_count == 1
    assert all(aggregate.mode_count == 1 for aggregate in aggregates)
    assert by_mode[("sd",)].evidence_key.startswith("sd|")
    assert by_mode[("da",)].evidence_key.startswith("da|")
    assert by_mode[("sd",)].metric_name == "avg_score"
    assert by_mode[("sd",)].observation_keys


def test_a_requires_stability_and_enough_non_sentinel_scores(tmp_path):
    out = _write_threshold_fixture(tmp_path)
    path = out / "team_rank_dedup_unordered.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0])
    seen_sd = 0
    for row in rows:
        if row["mode"] == "sd":
            seen_sd += 1
            if seen_sd > 1:
                row["avg_score"] = "0"
    _write_csv(path, columns, rows)

    sparse_valid = [row for row in build_team_signature_aggregates(out, min_a_app_rate=5) if row.mode == "sd"][0]
    assert sparse_valid.confidence not in {"A", "B+"}
    assert sparse_valid.non_sentinel_score_count == 1
    assert sparse_valid.sentinel_score_count == 11

    (out / "prydwen_tier_current.csv").unlink()
    no_stability = [row for row in build_team_signature_aggregates(out, min_a_app_rate=5) if row.mode == "da"][0]
    assert no_stability.confidence == "B+"
    assert no_stability.stability_status == "unknown"


def test_box_build_state_is_explicit_and_never_inferred_from_ownership(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = tmp_path / "box_with_builds.json"
    box.write_text(
        json.dumps(
            {
                "owned": ["miyabi", "lucy", "nicole-demara"],
                "builds": {"miyabi": {"level": 60}, "lucy": {"level": 60}},
            }
        ),
        encoding="utf-8",
    )

    pool = build_evidence_pool_from_paths(out, box_path=box)
    record = pool.records[0]
    assert record.build_checked == "已读取"
    assert record.built_count == 2
    assert record.unbuilt_parts == ("nicole-demara",)
    assert record.source_confidence == "B+"
    assert record.confidence == "B"
    assert "未标记已培养" in record.risk_comment

    fully_built = tmp_path / "box_fully_built.json"
    fully_built.write_text(
        json.dumps(
            {
                "owned": ["miyabi", "lucy", "nicole-demara"],
                "builds": {
                    "miyabi": {"level": 60},
                    "lucy": {"level": 60},
                    "nicole-demara": {"level": 60},
                },
            }
        ),
        encoding="utf-8",
    )
    ready_record = build_evidence_pool_from_paths(out, box_path=fully_built).records[0]
    assert ready_record.unbuilt_parts == ("none",)
    assert ready_record.confidence == "B+"


def test_falsey_built_values_never_mark_agents_ready(tmp_path):
    box = tmp_path / "falsey_builds.json"
    box.write_text(
        json.dumps(
            {
                "agents": [
                    {"slug": "a", "built": None},
                    {"slug": "b", "built": ""},
                    {"slug": "c", "built": 0},
                    {"slug": "d", "built": True},
                ],
                "builds": {"e": 0, "f": {}, "g": {"level": 60}},
            }
        ),
        encoding="utf-8",
    )

    known, built = load_built_slugs(box)
    assert known is True
    assert built == {"d", "g"}


def test_account_a_requires_explicitly_built_team(tmp_path):
    out = _write_threshold_fixture(tmp_path)
    unknown_box = tmp_path / "unknown_build.json"
    unknown_box.write_text(json.dumps({"owned": ["miyabi", "lucy", "sunna"]}), encoding="utf-8")
    unknown_record = [
        record
        for record in build_evidence_pool_from_paths(
            out,
            box_path=unknown_box,
            min_a_app_rate=5,
        ).records
        if record.mode == "sd"
    ][0]
    assert unknown_record.source_confidence == "A"
    assert unknown_record.confidence == "B"

    built_box = tmp_path / "built_team.json"
    built_box.write_text(
        json.dumps(
            {
                "owned": ["miyabi", "lucy", "sunna"],
                "builds": {
                    "miyabi": {"level": 60},
                    "lucy": {"level": 60},
                    "sunna": {"level": 60},
                },
            }
        ),
        encoding="utf-8",
    )
    built_record = [
        record
        for record in build_evidence_pool_from_paths(
            out,
            box_path=built_box,
            min_a_app_rate=5,
        ).records
        if record.mode == "sd"
    ][0]
    assert built_record.source_confidence == "A"
    assert built_record.confidence == "A"


def test_non_finite_app_rate_is_skipped_and_score_is_missing(tmp_path):
    out = _write_cross_mode_fixture(tmp_path)
    path = out / "team_rank_dedup_unordered.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0])
    rows.append({**rows[0], "snapshot_id": "bad-app", "app_rate": "Infinity", "avg_score": "123"})
    rows[0]["avg_score"] = "NaN"
    _write_csv(path, columns, rows)

    aggregates = build_team_signature_aggregates(out)
    sd = [row for row in aggregates if row.mode == "sd"][0]
    assert sd.record_count == 1
    assert sd.non_sentinel_score_count == 0
    assert sd.sentinel_score_count == 1
    assert sd.best_score is None


def test_zzz_score_99_99_is_not_hsr_round_sentinel(tmp_path):
    out = _write_cross_mode_fixture(tmp_path)
    path = out / "team_rank_dedup_unordered.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0])
    rows[0]["avg_score"] = "99.99"
    _write_csv(path, columns, rows)

    sd = [row for row in build_team_signature_aggregates(out) if row.mode == "sd"][0]
    assert sd.non_sentinel_score_count == 1
    assert sd.sentinel_score_count == 0
    assert sd.best_score == 99.99


def test_non_finite_confidence_threshold_is_rejected(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)
    output = tmp_path / "should-not-exist.md"

    result = main(
        [
            "evidence",
            "--box",
            str(box),
            "--out",
            str(out),
            "--min-a-app-rate",
            "sd=Infinity",
            "--output",
            str(output),
        ]
    )

    assert result == 1
    assert not output.exists()


def test_alias_conflict_fails_independently_of_name_map_row_order(tmp_path):
    for index, rows in enumerate(
        (
            [
                {"character_slug": "a", "aliases": "shared"},
                {"character_slug": "b", "aliases": "shared"},
            ],
            [
                {"character_slug": "b", "aliases": "shared"},
                {"character_slug": "a", "aliases": "shared"},
            ],
        )
    ):
        out = tmp_path / str(index)
        out.mkdir()
        _write_csv(out / "name_map.csv", ["character_slug", "aliases"], rows)
        with pytest.raises(ValueError, match="alias conflict: shared"):
            load_name_index(out)


def test_evidence_id_is_stable_when_unrelated_plan_members_change(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)
    first = build_evidence_pool_from_paths(out, box_path=box, planned_slugs=["sunna"])
    second = build_evidence_pool_from_paths(out, box_path=box, planned_slugs=["sunna", "zhao"])
    first_record = [record for record in first.records if "sunna" in record.team_slugs][0]
    second_record = [record for record in second.records if "sunna" in record.team_slugs][0]

    assert first_record.evidence_id == second_record.evidence_id
    assert first_record.evidence_key == second_record.evidence_key
    assert first_record.evidence_id.startswith("E-SD-")


def test_yaml_dependency_failure_is_explicit(monkeypatch):
    original_import = builtins.__import__

    def reject_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("injected missing PyYAML")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_yaml)
    with pytest.raises(RuntimeError, match="PyYAML is required"):
        _load_yaml("agents: []")


def test_team_table_without_character_columns_is_rejected(tmp_path):
    out = tmp_path / "invalid_schema"
    out.mkdir()
    _write_csv(out / "team_rank_dedup_unordered.csv", ["mode", "app_rate"], [{"mode": "sd", "app_rate": 10}])

    with pytest.raises(ValueError, match="char_<n>_slug"):
        build_team_signature_aggregates(out)


def test_team_table_requires_mode_column_and_nonempty_mode_values(tmp_path):
    columns = ["char_1_slug", "char_2_slug", "char_3_slug", "app_rate", "avg_score"]
    missing_column = tmp_path / "missing_mode"
    missing_column.mkdir()
    _write_csv(
        missing_column / "team_rank_dedup_unordered.csv",
        columns,
        [{"char_1_slug": "a", "char_2_slug": "b", "char_3_slug": "c", "app_rate": 10, "avg_score": 1}],
    )
    with pytest.raises(ValueError, match="缺少 mode 列"):
        build_team_signature_aggregates(missing_column)

    blank_value = tmp_path / "blank_mode"
    blank_value.mkdir()
    _write_csv(
        blank_value / "team_rank_dedup_unordered.csv",
        ["mode", *columns],
        [{"mode": "", "char_1_slug": "a", "char_2_slug": "b", "char_3_slug": "c", "app_rate": 10, "avg_score": 1}],
    )
    with pytest.raises(ValueError, match="证据行缺少 mode"):
        build_team_signature_aggregates(blank_value)

    empty_but_valid = tmp_path / "empty_valid"
    empty_but_valid.mkdir()
    _write_csv(empty_but_valid / "team_rank_dedup_unordered.csv", ["mode", *columns], [])
    assert build_team_signature_aggregates(empty_but_valid) == []


def test_partial_team_is_skipped_and_unknown_mode_is_rejected(tmp_path):
    out = _write_cross_mode_fixture(tmp_path)
    path = out / "team_rank_dedup_unordered.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0])
    rows.append({**rows[0], "snapshot_id": "partial", "char_3_slug": ""})
    _write_csv(path, columns, rows)
    quality = {}
    build_team_signature_aggregates(out, quality_out=quality)
    assert quality["skipped_partial_team"] == 1
    assert quality["rows_included"] == 2

    rows[0]["mode"] = "sdd"
    _write_csv(path, columns, rows)
    with pytest.raises(ValueError, match="未声明 mode policy：sdd"):
        build_team_signature_aggregates(out)


def test_stability_role_adapter_differs_between_zzz_and_hsr_modes(tmp_path):
    out = _write_cross_mode_fixture(tmp_path)
    _write_csv(
        out / "prydwen_tier_current.csv",
        ["character_slug", "role_group", "role_group_cn"],
        [
            {"character_slug": "a", "role_group": "support", "role_group_cn": "辅助"},
            {"character_slug": "b", "role_group": "crit_dps", "role_group_cn": "直伤主C"},
            {"character_slug": "c", "role_group": "break_dps", "role_group_cn": "击破主C"},
        ],
    )
    zzz = [row for row in build_team_signature_aggregates(out) if row.mode == "sd"][0]
    assert zzz.stability_status == "present"

    path = out / "team_rank_dedup_unordered.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0])
    for row in rows:
        row["mode"] = "moc"
    _write_csv(path, columns, rows)
    hsr = build_team_signature_aggregates(out)[0]
    assert hsr.stability_status == "absent"


def test_plan_status_and_report_share_explicit_local_datetime(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "status": "next",
                        "start_at": "2026-07-12 13:00:00",
                        "end_at": "2026-07-12 14:00:00",
                        "characters": [{"slug": "sunna"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fixed = datetime(2026, 7, 12, 13, 14, 15)
    planned = load_planned_slugs_from_banner_plan(
        plan,
        statuses=["current"],
        names=load_name_index(out),
        local_datetime=fixed,
    )
    assert planned == ["sunna"]
    pool = build_evidence_pool_from_paths(out, box_path=box, planned_slugs=planned)
    report = format_evidence_report(pool, local_datetime=fixed)
    assert "2026-07-12T13:14:15" in report


def test_coverage_rejects_output_collisions_before_replacing_old_file(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)
    collision = tmp_path / "same.md"
    collision.write_text("old", encoding="utf-8")

    try:
        write_coverage_reports(
            out,
            box_path=box,
            current_output_path=collision,
            target_output_path=collision,
        )
    except ValueError as error:
        assert "路径冲突" in str(error)
    else:
        raise AssertionError("expected output collision")
    assert collision.read_text(encoding="utf-8") == "old"


def test_coverage_markdown_table_has_one_schema_for_empty_and_nonempty_rows(tmp_path):
    out = _write_evidence_fixture(tmp_path)
    box = _write_box(tmp_path)
    populated = build_evidence_pool_from_paths(out, box_path=box)
    empty = EvidencePool(
        records=[],
        summary={"method_version": "test", "data_quality": {}},
        aggregates=[],
    )

    for pool in (populated, empty):
        table_rows = [line for line in format_evidence_report(pool).splitlines() if line.startswith("|")]
        assert len(table_rows) >= 3
        assert all(len(re.split(r"(?<!\\)\|", line)[1:-1]) == len(COVERAGE_COLUMNS) for line in table_rows)


def test_atomic_batch_rolls_back_when_second_install_fails(tmp_path, monkeypatch):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    original_replace = os.replace
    failed = False

    def fail_second_stage(source, target):
        nonlocal failed
        source_path = str(source)
        if not failed and source_path.endswith(".stage") and Path(target).name == "second.md":
            failed = True
            raise OSError("injected second install failure")
        return original_replace(source, target)

    monkeypatch.setattr("miho_core.evidence.os.replace", fail_second_stage)
    try:
        _atomic_write_batch({first: b"new-first", second: b"new-second"})
    except OSError as error:
        assert "injected" in str(error)
    else:
        raise AssertionError("expected injected failure")

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["first.md", "second.md"]


def test_avg_round_lower_better_uses_min_score(tmp_path):
    out = _write_avg_round_fixture(tmp_path)

    aggregate = build_team_signature_aggregates(out)[0]

    assert aggregate.metric_direction == "lower_better"
    assert aggregate.best_score == 3


def _write_evidence_fixture(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    _write_csv(
        out / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn", "aliases", "kind"],
        [
            {"character_slug": "miyabi", "character_name_en": "Miyabi", "character_name_cn": "星见雅", "aliases": "", "kind": "agent"},
            {"character_slug": "lucy", "character_name_en": "Lucy", "character_name_cn": "露西", "aliases": "", "kind": "agent"},
            {
                "character_slug": "nicole-demara",
                "character_name_en": "Nicole Demara",
                "character_name_cn": "妮可",
                "aliases": "nicole",
                "kind": "agent",
            },
            {"character_slug": "sunna", "character_name_en": "Sunna", "character_name_cn": "千夏", "aliases": "", "kind": "agent"},
            {"character_slug": "zhao", "character_name_en": "Zhao", "character_name_cn": "照", "aliases": "", "kind": "agent"},
            {
                "character_slug": "biggest-fan",
                "character_name_en": "Biggest Fan",
                "character_name_cn": "阿饭",
                "aliases": "",
                "kind": "bangboo",
            },
        ],
    )
    columns = [
        "snapshot_id",
        "collect_date",
        "mode",
        "mode_cn",
        "sub_mode",
        "sub_mode_cn",
        "phase_ver",
        "phase_name",
        "scope",
        "rank",
        "char_1_slug",
        "char_2_slug",
        "char_3_slug",
        "bangboo_slug",
        "char_1_name_cn",
        "char_2_name_cn",
        "char_3_name_cn",
        "bangboo_name_cn",
        "app_rate",
        "avg_score",
    ]
    _write_csv(
        out / "team_rank_dedup_unordered.csv",
        columns,
        [
            _team("2.8.1", "sd", "5-1", "miyabi", "lucy", "nicole", 12.5, 30000),
            _team("2.8.1", "sd", "5-2", "miyabi", "lucy", "nicole-demara", 10.4, 30100),
            _team("2.8.2", "sd", "5-1", "miyabi", "lucy", "nicole-demara", 11.4, 30200),
            _team("2.8.2", "sd", "5-2", "miyabi", "lucy", "nicole-demara", 10.8, 30300),
            _team("2.8.3", "sd", "5-1", "miyabi", "lucy", "nicole-demara", 9.4, 30400),
            _team("2.8.3", "sd", "5-2", "miyabi", "lucy", "nicole-demara", 8.8, 30500),
            _team("2.8.2", "sd", "5-1", "miyabi", "lucy", "sunna", 8.0, 0),
            _team("2.8.2", "sd", "5-1", "miyabi", "zhao", "lucy", 20.0, 32000),
        ],
    )
    return out


def _write_threshold_fixture(tmp_path):
    out = tmp_path / "threshold_out"
    out.mkdir()
    _write_csv(
        out / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn", "aliases", "kind"],
        [
            {"character_slug": "miyabi", "character_name_en": "Miyabi", "character_name_cn": "星见雅", "aliases": "", "kind": "agent"},
            {"character_slug": "lucy", "character_name_en": "Lucy", "character_name_cn": "露西", "aliases": "", "kind": "agent"},
            {"character_slug": "sunna", "character_name_en": "Sunna", "character_name_cn": "千夏", "aliases": "", "kind": "agent"},
        ],
    )
    _write_csv(
        out / "prydwen_tier_current.csv",
        ["character_slug", "role_group", "role_group_cn"],
        [
            {"character_slug": "miyabi", "role_group": "anomaly_dps", "role_group_cn": "异常主C"},
            {"character_slug": "lucy", "role_group": "support", "role_group_cn": "辅助"},
            {"character_slug": "sunna", "role_group": "support", "role_group_cn": "辅助"},
        ],
    )
    columns = [
        "snapshot_id",
        "collect_date",
        "mode",
        "sub_mode",
        "phase_ver",
        "scope",
        "rank",
        "char_1_slug",
        "char_2_slug",
        "char_3_slug",
        "bangboo_slug",
        "app_rate",
        "avg_score",
    ]
    rows = []
    for index in range(24):
        mode = "sd" if index < 12 else "da"
        sub_mode = f"{1 + index % 3}-{1 + index % 2}"
        phase = f"2.8.{1 + index // 2}"
        rows.append(
            {
                "snapshot_id": phase,
                "collect_date": "2026-06-01",
                "mode": mode,
                "sub_mode": sub_mode,
                "phase_ver": phase,
                "scope": f"{sub_mode}_combined.json",
                "rank": 1,
                "char_1_slug": "miyabi",
                "char_2_slug": "lucy",
                "char_3_slug": "sunna",
                "bangboo_slug": "",
                "app_rate": 8,
                "avg_score": 30000 + index,
            }
        )
    _write_csv(out / "team_rank_dedup_unordered.csv", columns, rows)
    return out


def _write_cross_mode_fixture(tmp_path):
    out = tmp_path / "cross_mode_out"
    out.mkdir()
    _write_csv(
        out / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn", "aliases", "kind"],
        [
            {"character_slug": "a", "character_name_en": "A", "character_name_cn": "A", "aliases": "", "kind": "agent"},
            {"character_slug": "b", "character_name_en": "B", "character_name_cn": "B", "aliases": "", "kind": "agent"},
            {"character_slug": "c", "character_name_en": "C", "character_name_cn": "C", "aliases": "", "kind": "agent"},
        ],
    )
    columns = [
        "snapshot_id",
        "mode",
        "sub_mode",
        "phase_ver",
        "scope",
        "rank",
        "char_1_slug",
        "char_2_slug",
        "char_3_slug",
        "app_rate",
        "avg_score",
    ]
    common = {
        "snapshot_id": "1",
        "sub_mode": "all",
        "phase_ver": "1",
        "scope": "all",
        "rank": 1,
        "char_1_slug": "a",
        "char_2_slug": "b",
        "char_3_slug": "c",
        "app_rate": 12,
    }
    _write_csv(
        out / "team_rank_dedup_unordered.csv",
        columns,
        [
            {**common, "mode": "sd", "avg_score": 33333},
            {**common, "mode": "da", "avg_score": 999999},
        ],
    )
    return out


def _write_avg_round_fixture(tmp_path):
    out = tmp_path / "avg_round_out"
    out.mkdir()
    _write_csv(
        out / "name_map.csv",
        ["character_slug", "character_name_en", "character_name_cn", "aliases", "kind"],
        [
            {"character_slug": "a", "character_name_en": "A", "character_name_cn": "A", "aliases": "", "kind": "agent"},
            {"character_slug": "b", "character_name_en": "B", "character_name_cn": "B", "aliases": "", "kind": "agent"},
            {"character_slug": "c", "character_name_en": "C", "character_name_cn": "C", "aliases": "", "kind": "agent"},
        ],
    )
    columns = [
        "snapshot_id",
        "mode",
        "sub_mode",
        "phase_ver",
        "scope",
        "rank",
        "char_1_slug",
        "char_2_slug",
        "char_3_slug",
        "app_rate",
        "avg_round",
    ]
    _write_csv(
        out / "team_rank_dedup_unordered.csv",
        columns,
        [
            {"snapshot_id": "1", "mode": "moc", "sub_mode": "all", "phase_ver": "1", "scope": "all", "rank": 2, "char_1_slug": "a", "char_2_slug": "b", "char_3_slug": "c", "app_rate": 2, "avg_round": 5},
            {"snapshot_id": "2", "mode": "moc", "sub_mode": "all", "phase_ver": "2", "scope": "all", "rank": 1, "char_1_slug": "a", "char_2_slug": "b", "char_3_slug": "c", "app_rate": 2, "avg_round": 3},
        ],
    )
    return out


def _write_box(tmp_path):
    box = tmp_path / "box.json"
    box.write_text(json.dumps({"owned": ["miyabi", "lucy", "nicole-demara"]}), encoding="utf-8")
    return box


def _team(phase, mode, sub_mode, char_1, char_2, char_3, app_rate, avg_score):
    return {
        "snapshot_id": phase,
        "collect_date": "2026-06-01",
        "mode": mode,
        "mode_cn": "式舆防卫" if mode == "sd" else "危局强袭",
        "sub_mode": sub_mode,
        "sub_mode_cn": sub_mode.replace("-", " / "),
        "phase_ver": phase,
        "phase_name": f"{mode} {phase}",
        "scope": f"{sub_mode}_combined.json",
        "rank": 1,
        "char_1_slug": char_1,
        "char_2_slug": char_2,
        "char_3_slug": char_3,
        "bangboo_slug": "biggest-fan",
        "char_1_name_cn": "",
        "char_2_name_cn": "",
        "char_3_name_cn": "",
        "bangboo_name_cn": "阿饭",
        "app_rate": app_rate,
        "avg_score": avg_score,
    }


def _write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
