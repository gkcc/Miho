from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from miho_core.evidence import (
    AGGREGATE_COLUMNS,
    COVERAGE_COLUMNS,
    build_evidence_pool_from_paths,
    format_evidence_report,
    load_name_index,
    load_planned_slugs_from_banner_plan,
)
import zzz_endgame_exporter.cli as zzz_cli


FIXTURE = Path(__file__).parent / "fixtures" / "evidence_v1_contract"
EXPECTED = FIXTURE / "expected"
FIXED_CLOCK = datetime(2026, 7, 12, 13, 14, 15)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 12, 13, 14, 15)
        return value if tz is None else value.astimezone(tz)


def _contract() -> dict:
    return json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))


def _normalized(text: str, temporary_root: Path) -> str:
    # The V1 contract intentionally permits exactly these two substitutions.
    text = text.replace(str(temporary_root), "<ROOT>")
    return text.replace(FIXED_CLOCK.isoformat(timespec="seconds"), "<GENERATED_AT>")


def _normalized_file(path: Path, temporary_root: Path) -> str:
    # utf-8-sig consumes the aggregate CSV's transport BOM; read_text also gives
    # platform-independent text lines. Neither changes the report semantics.
    return _normalized(path.read_text(encoding="utf-8-sig"), temporary_root)


def _copy_real_inputs(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "evidence_v1_contract"
    shutil.copytree(FIXTURE / "input", runtime_root / "input")
    return runtime_root


def _planned(runtime_root: Path) -> list[str]:
    data_dir = runtime_root / "input" / "data"
    return load_planned_slugs_from_banner_plan(
        runtime_root / "input" / "plan.json",
        statuses=["current"],
        names=load_name_index(data_dir),
        local_datetime=FIXED_CLOCK,
    )


def test_python_core_matches_dense_evidence_v1_golden(tmp_path: Path) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    data_dir = runtime_root / "input" / "data"
    box = runtime_root / "input" / "box.json"
    planned = _planned(runtime_root)

    assert planned == ["sunna"]
    pool = build_evidence_pool_from_paths(
        data_dir,
        box_path=box,
        planned_slugs=planned,
        include_missing=True,
    )
    rendered = format_evidence_report(
        pool,
        title="绝区零目标账号证据池队伍覆盖",
        local_datetime=FIXED_CLOCK,
    )
    expected = (EXPECTED / "evidence_pool_summary.md").read_text(encoding="utf-8")
    assert _normalized(rendered, runtime_root) == expected

    contract = _contract()
    by_key = {record.evidence_key: record for record in pool.records}
    assert {key: row.evidence_id for key, row in by_key.items()} == contract["stable_evidence_ids"]

    sd_owned = by_key["sd|lucy|miyabi|nicole-demara|bangboo:biggest-fan"]
    da_owned = by_key["da|lucy|miyabi|nicole-demara|bangboo:biggest-fan"]
    planned_team = by_key["sd|lucy|miyabi|sunna|bangboo:biggest-fan"]
    missing_team = by_key["sd|lucy|miyabi|zhao|bangboo:biggest-fan"]

    assert sd_owned.modes == ("sd",) and sd_owned.best_score == 30011
    assert da_owned.modes == ("da",) and da_owned.best_score == 900003
    assert sd_owned.evidence_id != da_owned.evidence_id
    assert (sd_owned.source_confidence, sd_owned.confidence) == ("A", "A")
    assert (planned_team.source_confidence, planned_team.confidence) == ("B+", "B")
    assert (missing_team.source_confidence, missing_team.confidence) == ("B-", "C")
    assert (sd_owned.record_count, sd_owned.duplicate_count) == (12, 15)
    assert (planned_team.non_sentinel_score_count, planned_team.sentinel_score_count) == (4, 2)


def test_python_cli_matches_all_four_frozen_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    output = runtime_root / "output"
    output.mkdir()
    data_dir = runtime_root / "input" / "data"
    box = runtime_root / "input" / "box.json"
    plan = runtime_root / "input" / "plan.json"
    monkeypatch.setattr(zzz_cli, "datetime", _FixedDateTime)

    common = [
        "--box", str(box),
        "--out", str(data_dir),
        "--plan", str(plan),
        "--plan-status", "current",
    ]
    assert zzz_cli.main(
        [
            "evidence", *common,
            "--include-missing",
            "--output", str(output / "evidence_pool_summary.md"),
        ]
    ) == 0
    assert zzz_cli.main(
        [
            "coverage", *common,
            "--current-output", str(output / "current_box_team_coverage.md"),
            "--target-output", str(output / "target_box_team_coverage.md"),
            "--aggregate-output", str(output / "team_signature_aggregates.csv"),
        ]
    ) == 0

    contract = _contract()
    actual_files = sorted(path.name for path in output.iterdir() if path.is_file())
    assert actual_files == contract["output_files"]
    for name in actual_files:
        actual = _normalized_file(output / name, runtime_root)
        expected = (EXPECTED / name).read_text(encoding="utf-8-sig")
        assert actual == expected, name
        digest = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        assert digest == contract["normalized_sha256"][name]


def test_contract_freezes_file_sets_schemas_hashes_and_rust_seam() -> None:
    contract = _contract()
    input_files = sorted(
        path.relative_to(FIXTURE / "input").as_posix()
        for path in (FIXTURE / "input").rglob("*")
        if path.is_file()
    )
    expected_files = sorted(path.name for path in EXPECTED.iterdir() if path.is_file())
    assert input_files == contract["input_files"]
    assert expected_files == contract["output_files"]
    assert contract["normalizations"] == ["temporary_root", "generated_at"]

    for name in expected_files:
        canonical = (EXPECTED / name).read_text(encoding="utf-8-sig")
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == contract["normalized_sha256"][name]

    with (EXPECTED / "team_signature_aggregates.csv").open(encoding="utf-8-sig", newline="") as handle:
        aggregate_header = next(csv.reader(handle))
    assert aggregate_header == AGGREGATE_COLUMNS

    markdown_header = next(
        line for line in (EXPECTED / "target_box_team_coverage.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| evidence_id |")
    )
    coverage_header = [part.strip() for part in markdown_header.strip("|").split("|")]
    assert coverage_header == COVERAGE_COLUMNS

    seam = contract["rust_command_comparison_seam"]
    assert seam["status"] == "reserved_not_executed_by_python_contract"
    assert [command[2] for command in seam["commands"]] == ["evidence", "coverage"]
