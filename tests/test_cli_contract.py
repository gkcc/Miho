from __future__ import annotations

from datetime import date, timedelta

import pytest

from hsr_endgame_exporter import cli as hsr_cli
from zzz_endgame_exporter import cli as zzz_cli


def test_hsr_cli_commands_and_export_defaults() -> None:
    parser = hsr_cli.build_parser()

    export = parser.parse_args(["export"])
    assert export.command == "export"
    assert export.from_date == (date.today() - timedelta(days=183)).isoformat()
    assert export.to_date == date.today().isoformat()
    assert export.out == "./hsr_endgame_export"
    assert export.modes == "moc,pf,as,aa"
    assert export.include_teams is True
    assert export.include_prydwen_visible is True
    assert export.include_prydwen_tier is True
    assert export.official_name_map is True
    assert export.prydwen_top_n == 100
    assert export.name_map_seed == ""
    assert export.repo_id == "LvlUrArti/MocDataProcessed"

    visualizer = parser.parse_args(["visualizer"])
    assert visualizer.command == "visualizer"
    assert visualizer.out == "./hsr_endgame_export"


@pytest.mark.parametrize(
    "flag,attribute",
    [
        ("include-teams", "include_teams"),
        ("include-prydwen-visible", "include_prydwen_visible"),
        ("include-prydwen-tier", "include_prydwen_tier"),
        ("official-name-map", "official_name_map"),
    ],
)
def test_hsr_boolean_optional_flags(flag: str, attribute: str) -> None:
    parser = hsr_cli.build_parser()
    assert getattr(parser.parse_args(["export", f"--{flag}"]), attribute) is True
    assert getattr(parser.parse_args(["export", f"--no-{flag}"]), attribute) is False


def test_zzz_cli_commands_and_key_defaults() -> None:
    parser = zzz_cli.build_parser()

    export = parser.parse_args(["export"])
    assert export.from_date == (date.today() - timedelta(days=183)).isoformat()
    assert export.to_date == date.today().isoformat()
    assert export.out == "./zzz_endgame_export"
    assert export.modes == "sd,da"
    assert export.repo_id == "LvlUrArti/ShiyuDataProcessed"
    assert export.prydwen_top_n == 100

    decision = parser.parse_args(["decision", "--box", "box.json"])
    assert decision.out == "./zzz_endgame_export"
    assert decision.rules == "./configs/zzz_decision_rules.yaml"

    evidence = parser.parse_args(["evidence", "--box", "box.json"])
    assert evidence.plan_status == "next"
    assert evidence.limit == 0
    assert evidence.min_a_app_rate == "10.0"
    assert evidence.include_missing is False

    coverage = parser.parse_args(["coverage", "--box", "box.json"])
    assert coverage.plan_status == "next"
    assert coverage.aggregate_output == ""
    assert coverage.current_output == ""
    assert coverage.target_output == ""

    for command in ("pull-value", "review-packet"):
        args = parser.parse_args([command, "--box", "box.json"])
        assert args.plan == "./configs/zzz_banner_plan.json"
        assert args.plan_status == "current,next"
        assert args.decision_baseline == "./configs/zzz_decision_baseline.json"
        assert args.output == ""

    assert parser.parse_args(["visualizer"]).out == "./zzz_endgame_export"
    serve = parser.parse_args(["serve"])
    assert serve.root == "."
    assert serve.host == "127.0.0.1"
    assert serve.port == 8765


@pytest.mark.parametrize(
    "flag,attribute,default",
    [
        ("include-teams", "include_teams", True),
        ("include-prydwen-visible", "include_prydwen_visible", True),
        ("include-prydwen-tier", "include_prydwen_tier", True),
        ("official-name-map", "official_name_map", True),
    ],
)
def test_zzz_export_boolean_optional_flags(flag: str, attribute: str, default: bool) -> None:
    parser = zzz_cli.build_parser()
    assert getattr(parser.parse_args(["export"]), attribute) is default
    assert getattr(parser.parse_args(["export", f"--{flag}"]), attribute) is True
    assert getattr(parser.parse_args(["export", f"--no-{flag}"]), attribute) is False


def test_zzz_evidence_include_missing_boolean_optional_flags() -> None:
    parser = zzz_cli.build_parser()
    base = ["evidence", "--box", "box.json"]
    assert parser.parse_args([*base, "--include-missing"]).include_missing is True
    assert parser.parse_args([*base, "--no-include-missing"]).include_missing is False


@pytest.mark.parametrize("module", [hsr_cli, zzz_cli])
def test_cli_without_command_returns_two(module: object, capsys: pytest.CaptureFixture[str]) -> None:
    assert module.main([]) == 2  # type: ignore[attr-defined]
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("module", [hsr_cli, zzz_cli])
def test_export_business_exception_returns_one(
    module: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(_args: object) -> None:
        raise RuntimeError("contract failure")

    monkeypatch.setattr(module, "run_export", fail)
    assert module.main(["export"]) == 1  # type: ignore[attr-defined]
    assert "export failed: contract failure" in capsys.readouterr().err
