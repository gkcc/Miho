from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

import pytest

import zzz_endgame_exporter.decision_report as decision_report_module
from zzz_endgame_exporter.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "decision_legacy_v0_contract"
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
    # The LegacyV0 oracle permits exactly these two dynamic substitutions.
    for value in (
        str(temporary_root).replace("\\", "\\\\"),
        str(temporary_root),
        temporary_root.as_posix(),
    ):
        text = text.replace(value, "<ROOT>")
    return text.replace(FIXED_CLOCK.isoformat(timespec="seconds"), "<GENERATED_AT>")


def _normalized_file(path: Path, temporary_root: Path) -> str:
    # Universal-newline decoding is transport-neutral; no payload field is removed.
    return _normalized(path.read_text(encoding="utf-8"), temporary_root)


def _copy_real_inputs(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "decision legacy v0 中文 contract"
    shutil.copytree(FIXTURE / "input", runtime_root / "input")
    return runtime_root


def test_python_cli_matches_both_frozen_legacy_v0_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    input_root = runtime_root / "input"
    data_dir = input_root / "data"
    monkeypatch.setattr(decision_report_module, "datetime", _FixedDateTime)

    assert main(
        [
            "decision",
            "--box", str(input_root / "box.yaml"),
            "--out", str(data_dir),
            "--rules", str(input_root / "rules.yaml"),
        ]
    ) == 0

    contract = _contract()
    actual_files = sorted(path.name for path in data_dir.glob("decision_*") if path.is_file())
    assert actual_files == contract["output_files"]
    for name in actual_files:
        actual = _normalized_file(data_dir / name, runtime_root)
        expected = (EXPECTED / name).read_text(encoding="utf-8")
        assert actual == expected, name
        assert hashlib.sha256(actual.encode("utf-8")).hexdigest() == contract["normalized_sha256"][name]


def test_legacy_v0_payload_freezes_all_four_decisions_and_complete_schema() -> None:
    payload = json.loads((EXPECTED / "decision_cards.json").read_text(encoding="utf-8"))
    contract = _contract()
    schema = contract["payload_schema"]

    assert set(payload) == set(schema["payload"])
    assert "method_version" not in payload
    assert set(payload["summary"]) == set(schema["summary"])
    assert set(payload["summary"]["data_rows"]) == set(schema["data_rows"])
    assert payload["summary"]["decision_counts"] == {
        "抽": 1,
        "等实测": 1,
        "停止加仓": 1,
        "不抽": 1,
    }
    assert {card["slug"]: card["decision"] for card in payload["cards"]} == contract["expected_decisions"]

    replacements = []
    for card in payload["cards"]:
        assert set(card) == set(schema["card"])
        assert "method_version" not in card
        assert set(card["tier_summary"]) == set(schema["tier_summary"])
        assert set(card["history_summary"]) == set(schema["history_summary"])
        assert set(card["release_risk"]) == set(schema["release_risk"])
        assert set(card["replacement_risk"]) == set(schema["replacement_risk"])
        assert set(card["investment"]) == set(schema["investment"])
        assert all(set(mode) == set(schema["tier_mode"]) for mode in card["tier_summary"]["modes"].values())
        assert all(set(mode) == set(schema["history_mode"]) for mode in card["history_summary"]["modes"].values())
        assert all(
            set(example) == set(schema["team_example"])
            for example in card["history_summary"]["latest_team_examples"]
        )
        assert all(set(stage) == set(schema["stage"]) for stage in card["stage_comparison"])
        replacements.extend(card["replacement_risk"]["replacements"])

    assert replacements
    assert all(set(replacement) == set(schema["replacement"]) for replacement in replacements)


def test_contract_freezes_inputs_outputs_hashes_and_executed_rust_seam() -> None:
    contract = _contract()
    input_files = sorted(
        path.relative_to(FIXTURE / "input").as_posix()
        for path in (FIXTURE / "input").rglob("*")
        if path.is_file()
    )
    expected_files = sorted(path.name for path in EXPECTED.iterdir() if path.is_file())

    assert input_files == contract["input_files"]
    assert expected_files == contract["output_files"]
    assert contract["method_version"] == "legacy-v0"
    assert contract["normalizations"] == ["temporary_root", "generated_at"]
    assert "data/prydwen_tier_history.csv" in input_files
    for name in expected_files:
        canonical = (EXPECTED / name).read_text(encoding="utf-8")
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == contract["normalized_sha256"][name]

    seam = contract["rust_command_comparison_seam"]
    assert seam["status"] == "executed_by_rust_contract"
    assert [command[2] for command in seam["commands"]] == ["decision"]
    assert all(command[3:5] == ["--method", "legacy-v0"] for command in seam["commands"])
