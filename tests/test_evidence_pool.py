import csv
import json

from miho_core.evidence import build_evidence_pool_from_paths, build_team_signature_aggregates, format_evidence_report
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

    assert owned_team.confidence == "B+"
    assert owned_team.plan_dependency == ("none",)
    assert owned_team.agent_signature == "lucy|miyabi|nicole-demara"
    assert owned_team.full_team_signature == "lucy|miyabi|nicole-demara|bangboo:biggest-fan"
    assert owned_team.team_signature == owned_team.full_team_signature
    assert owned_team.bangboo_slug == "biggest-fan"
    assert owned_team.bangboo_name_cn == "阿饭"
    assert owned_team.bangboo_checked == "邦布未校验"
    assert owned_team.record_count == 6
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
            "--output",
            str(output),
        ]
    )

    assert result == 0
    text = output.read_text(encoding="utf-8")
    assert "# 绝区零目标账号证据池队伍覆盖" in text
    assert "lucy, miyabi, nicole-demara" in text
    assert "lucy, miyabi, sunna" in text


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
    assert "agent_signature,full_team_signature" in aggregate_csv
    assert "record_count,snapshot_count,phase_count,mode_count,scope_count,boss_count" in aggregate_csv


def test_min_a_app_rate_changes_classification(tmp_path):
    out = _write_threshold_fixture(tmp_path)

    default_aggregate = build_team_signature_aggregates(out)[0]
    relaxed_aggregate = build_team_signature_aggregates(out, min_a_app_rate=5)[0]

    assert default_aggregate.confidence == "B+"
    assert relaxed_aggregate.confidence == "A"
    assert "min_a_app_rate=5" in relaxed_aggregate.evidence_comment


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
    for index in range(12):
        mode = "sd" if index < 6 else "da"
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
