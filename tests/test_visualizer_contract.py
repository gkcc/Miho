from __future__ import annotations

import base64
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hsr_endgame_exporter.cli import run_visualizer as run_hsr_visualizer
from hsr_endgame_exporter.visualizer import (
    _safe_avatar_url as safe_hsr_avatar_url,
    _safe_link_url as safe_hsr_link_url,
    write_visualizer_app as write_hsr_visualizer_app,
)
from miho_core.banner_plan import effective_phase_status
from tests.test_workbook_contract import (
    _write_hsr_oracle,
    _write_zzz_oracle,
)
from tests.visualizer_contract import (
    LOCAL_DATE_POINTER,
    assert_json_contract_equal,
    binary_sha256,
    compare_json_contract,
    load_json,
    normalized_utf8,
    normalized_utf8_sha256,
    relative_file_set,
)
from zzz_endgame_exporter.cli import (
    _write_final_outputs_and_visualizer as write_final_zzz_outputs_and_visualizer,
)
from zzz_endgame_exporter.cli import run_visualizer as run_zzz_visualizer
from zzz_endgame_exporter.hub import _html as visualizer_hub_html
from zzz_endgame_exporter.hub import _safe_directory_segment
from zzz_endgame_exporter.visualizer import (
    _safe_link_url as safe_zzz_link_url,
    _safe_same_origin_relative_url as safe_zzz_avatar_url,
    write_visualizer_app as write_zzz_visualizer_app,
)


FIXTURES = Path(__file__).parent / "fixtures" / "visualizer_contract"
SECURITY_TEXT = (
    '=HYPERLINK("https://invalid.example/formula",'
    '"<img src=x onerror=window.__MIHO_XSS__=1>")'
)
HTML_PAYLOAD = "</script><svg onload=window.__MIHO_XSS__=1>"
_UID_RE = re.compile(r"(?<!\d)\d{9,12}(?!\d)")
LOCAL_DATETIME = "2026-07-12T13:00:00"


@pytest.mark.parametrize("game", ["hsr", "zzz"])
def test_desktop_box_bootstrap_uses_server_before_enabling_ui(game: str) -> None:
    app = (
        ROOT / "crates" / "miho-core" / "assets" / "visualizer" / game / "app.js"
    ).read_text(encoding="utf-8")

    assert "const desktopMode=globalThis.__MIHO_DESKTOP__===true" in app
    assert "if(desktopMode)await syncBoxFromServer();else loadBox();init();render();" in app
    assert f"function syncBoxFromServer(){{return fetch('/api/{game}/box'" in app
    assert "if(!desktopMode){localStorage.setItem" in app
    assert "loadBox();loadRec" not in app
    assert "render();syncBoxFromServer();" not in app


@pytest.mark.parametrize("game", ["hsr", "zzz"])
def test_visualizer_distinguishes_stale_samples_from_missing_data(game: str) -> None:
    app = (
        ROOT / "crates" / "miho-core" / "assets" / "visualizer" / game / "app.js"
    ).read_text(encoding="utf-8")

    assert "function ensureBannerPhase()" in app
    assert "卡池数据未生成或为空" in app
    assert "卡池数据已载入 ${allRows.length} 条" in app
    assert "最新采样 ${sample.date} · ${sample.label}" in app
    assert "status==='current'?'当前周期':status==='expired'?'历史样本':'周期未知'" in app
    assert "当前筛选无匹配" in app
    assert "该模式数据未生成" in app
    assert "当前数据包尚未包含新周期统计，以下队伍仅作历史参考" in app
    assert "上游尚未发布新周期统计" not in app
    assert "请和我对话手动更新" not in app

    if game == "hsr":
        assert "status==='recent'||status==='previous'" in app


def test_hsr_final_target_controls_remain_responsive() -> None:
    styles = (
        ROOT / "crates" / "miho-core" / "assets" / "visualizer" / "hsr" / "styles.css"
    ).read_text(encoding="utf-8")

    assert (
        "@media(max-width:900px){.rec-plan-controls:not(.custom)"
        "{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}"
    ) in styles
    assert (
        "@media(max-width:620px){.rec-plan-controls:not(.custom)"
        "{grid-template-columns:1fr}}"
    ) in styles
    assert (
        ".rec-controls{grid-template-columns:1fr .62fr 1.45fr .72fr .55fr .58fr .5fr 1fr}"
    ) in styles
    assert "@media(max-width:1180px){.rec-controls{grid-template-columns:1fr 1fr 1fr}}" in styles
    assert "@media(max-width:720px){.rec-controls{grid-template-columns:1fr 1fr}" in styles
    assert (
        "#recTooltip{width:520px;max-width:calc(100vw - 28px);"
        "max-height:calc(100vh - 28px);overflow-x:hidden;overflow-y:auto;"
        "overflow-wrap:anywhere;overscroll-behavior:contain}"
    ) in styles
    assert "#recTooltip .tooltip-grid>div{min-width:0;overflow-wrap:anywhere}" in styles


class _FixedLocalDateTime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> "_FixedLocalDateTime":
        value = cls.fromisoformat(LOCAL_DATETIME)
        return value if tz is None else value.replace(tzinfo=tz)  # type: ignore[arg-type]


class _FixedLocalDate(date):
    @classmethod
    def today(cls) -> "_FixedLocalDate":
        return cls.fromisoformat(LOCAL_DATETIME[:10])


@pytest.fixture(scope="module")
def visualizer_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace = tmp_path_factory.mktemp("miho-visualizer-contract") / "中文 空格 workspace"
    hsr_root = workspace / "out"
    zzz_root = workspace / "out_zzz"

    # Reuse the Workbook contract's existing Python writers to obtain the
    # complete, final CSV boundary. The visualizers are invoked only after all
    # CSVs exist, matching the independent `visualizer` CLI commands.
    _write_hsr_oracle(hsr_root)
    _write_zzz_oracle(zzz_root)
    _densify_hsr_visualizer_csvs(hsr_root)
    _stabilize_final_csvs(hsr_root, "hsr")
    _stabilize_final_csvs(zzz_root, "zzz")
    _densify_zzz_visualizer_inputs(zzz_root)
    _write_hsr_official_roster_fixture(hsr_root)

    _write_dense_hsr_banner_plan(
        FIXTURES / "hsr_banner_plan.json", hsr_root / "hsr_banner_plan.json"
    )
    _write_dense_zzz_banner_plan(
        FIXTURES / "zzz_banner_plan.json", zzz_root / "zzz_banner_plan.json"
    )
    _write_dense_zzz_decision_cards(
        FIXTURES / "decision_cards.json", zzz_root / "decision_cards.json"
    )
    _preseed_avatar(hsr_root)
    _preseed_avatar(zzz_root)

    def forbidden_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("visualizer oracle attempted an outbound request")

    workspace.mkdir(parents=True, exist_ok=True)
    with _working_directory(workspace), patch(
        "miho_core.banner_plan.datetime", _FixedLocalDateTime
    ), patch(
        "hsr_endgame_exporter.visualizer.date", _FixedLocalDate
    ), patch(
        "zzz_endgame_exporter.visualizer.date", _FixedLocalDate
    ), patch("urllib.request.urlopen", side_effect=forbidden_network):
        run_hsr_visualizer(Namespace(out=str(hsr_root)))
        run_zzz_visualizer(Namespace(out=str(zzz_root)))
    return workspace


@pytest.fixture(scope="module")
def rust_hsr_visualizer_root(
    tmp_path_factory: pytest.TempPathFactory,
    visualizer_workspace: Path,
) -> Path:
    csv_root = visualizer_workspace / "out"
    python_root = _visualizer_root(visualizer_workspace, "hsr")
    assert load_json(python_root / "data.json")["meta"]["localDate"] == LOCAL_DATETIME[:10]
    out_root = (
        tmp_path_factory.mktemp("miho-rust-hsr-visualizer-contract")
        / "Rust 中文 空格 output"
    )
    subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-core",
            "--example",
            "hsr_visualizer_contract",
            "--",
            str(csv_root),
            str(out_root),
            LOCAL_DATETIME,
            str(csv_root / "hsr_banner_plan.json"),
            "agent-alpha",
            str(python_root / "assets" / "avatars" / "agent-alpha.webp"),
        ],
        cwd=ROOT,
        check=True,
    )
    return out_root / "visualizer"


@pytest.fixture(scope="module")
def rust_zzz_visualizer_root(
    tmp_path_factory: pytest.TempPathFactory,
    visualizer_workspace: Path,
) -> Path:
    csv_root = visualizer_workspace / "out_zzz"
    python_root = _visualizer_root(visualizer_workspace, "zzz")
    assert load_json(python_root / "data.json")["meta"]["localDate"] == LOCAL_DATETIME[:10]
    out_root = (
        tmp_path_factory.mktemp("miho-rust-zzz-visualizer-contract")
        / "Rust ZZZ 中文 空格 output"
    )
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-core",
            "--example",
            "zzz_visualizer_contract",
            "--",
            str(csv_root),
            str(out_root),
            LOCAL_DATETIME,
            str(csv_root / "zzz_endgame_phase_overrides.json"),
            str(csv_root / "zzz_banner_plan.json"),
            str(csv_root / "decision_cards.json"),
            "agent-alpha",
            str(python_root / "assets" / "avatars" / "agent-alpha.webp"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_root / "visualizer"


@pytest.fixture(scope="module")
def cli_hsr_visualizer_root(
    tmp_path_factory: pytest.TempPathFactory,
    visualizer_workspace: Path,
) -> tuple[Path, Path]:
    source_root = visualizer_workspace / "out"
    out_root = (
        tmp_path_factory.mktemp("miho-cli-hsr-visualizer-contract")
        / "CLI 中文 空格 output"
    )
    shutil.copytree(source_root, out_root)
    with _working_directory(out_root.parent), patch(
        "urllib.request.urlopen",
        side_effect=AssertionError("real-clock HSR oracle attempted network"),
    ):
        run_hsr_visualizer(Namespace(out=str(out_root)))
    expected_root = out_root.parent / "python-real-clock-hsr"
    shutil.copytree(out_root / "visualizer", expected_root)
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-cli",
            "--",
            "hsr",
            "visualizer",
            "--out",
            str(out_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_root / "visualizer", expected_root


@pytest.fixture(scope="module")
def cli_zzz_visualizer_root(
    tmp_path_factory: pytest.TempPathFactory,
    visualizer_workspace: Path,
) -> tuple[Path, Path, Path, Path]:
    source_root = visualizer_workspace / "out_zzz"
    out_root = (
        tmp_path_factory.mktemp("miho-cli-zzz-visualizer-contract")
        / "CLI ZZZ 中文 空格 output"
    )
    shutil.copytree(source_root, out_root)

    with _working_directory(out_root.parent), patch(
        "urllib.request.urlopen",
        side_effect=AssertionError("real-clock ZZZ oracle attempted network"),
    ):
        run_zzz_visualizer(Namespace(out=str(out_root)))
    expected_root = out_root.parent / "python-real-clock-zzz"
    shutil.copytree(out_root / "visualizer", expected_root)
    actual_hub = out_root.parent / "visualizer"
    expected_hub = out_root.parent / "python-real-clock-hub"
    shutil.copytree(actual_hub, expected_hub)

    # Invalid highest-priority candidates must not mask the valid parent
    # fallback. Decision cards intentionally remain at their top-level path.
    fallback_root = out_root.parent / "configs"
    fallback_root.mkdir()
    for name in ("zzz_banner_plan.json", "zzz_endgame_phase_overrides.json"):
        shutil.copyfile(out_root / name, fallback_root / name)
    (out_root / "zzz_banner_plan.json").write_text("[]\n", encoding="utf-8")
    (out_root / "zzz_endgame_phase_overrides.json").write_text(
        '{"phases":"not-a-list"}\n', encoding="utf-8"
    )

    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-cli",
            "--",
            "zzz",
            "visualizer",
            "--out",
            str(out_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return out_root / "visualizer", expected_root, actual_hub, expected_hub


def test_rust_hsr_visualizer_matches_python_json_exactly(
    visualizer_workspace: Path,
    rust_hsr_visualizer_root: Path,
) -> None:
    expected = load_json(_visualizer_root(visualizer_workspace, "hsr") / "data.json")
    actual = load_json(rust_hsr_visualizer_root / "data.json")

    assert_json_contract_equal(expected, actual, dynamic_pointers=())


def test_rust_hsr_visualizer_file_set_and_asset_hashes_are_exact(
    rust_hsr_visualizer_root: Path,
) -> None:
    contract = load_json(FIXTURES / "contract.json")
    assert relative_file_set(rust_hsr_visualizer_root) == contract["file_sets"]["hsr"]

    for name, expected_hash in contract["static_text_sha256"]["hsr"].items():
        assert normalized_utf8_sha256(rust_hsr_visualizer_root / name) == expected_hash
    for name, expected_hash in contract["binary_sha256"]["hsr"].items():
        assert binary_sha256(rust_hsr_visualizer_root / name) == expected_hash


@pytest.mark.live
def test_real_hsr_cli_visualizer_matches_the_complete_python_oracle(
    cli_hsr_visualizer_root: tuple[Path, Path],
) -> None:
    actual_root, expected_root = cli_hsr_visualizer_root
    expected_data = load_json(expected_root / "data.json")
    actual_data = load_json(actual_root / "data.json")
    assert_json_contract_equal(expected_data, actual_data, dynamic_pointers=())

    contract = load_json(FIXTURES / "contract.json")
    expected_files = relative_file_set(expected_root)
    assert expected_files == contract["file_sets"]["hsr"]
    assert relative_file_set(actual_root) == expected_files

    for name, contract_hash in contract["static_text_sha256"]["hsr"].items():
        expected_hash = normalized_utf8_sha256(expected_root / name)
        assert expected_hash == contract_hash
        assert normalized_utf8_sha256(actual_root / name) == expected_hash
    for name, contract_hash in contract["binary_sha256"]["hsr"].items():
        expected_hash = binary_sha256(expected_root / name)
        assert expected_hash == contract_hash
        assert binary_sha256(actual_root / name) == expected_hash


def test_rust_zzz_visualizer_matches_python_json_exactly(
    visualizer_workspace: Path,
    rust_zzz_visualizer_root: Path,
) -> None:
    expected = load_json(_visualizer_root(visualizer_workspace, "zzz") / "data.json")
    actual = load_json(rust_zzz_visualizer_root / "data.json")
    assert_json_contract_equal(expected, actual, dynamic_pointers=())


def test_rust_zzz_visualizer_file_set_and_asset_hashes_are_exact(
    rust_zzz_visualizer_root: Path,
) -> None:
    contract = load_json(FIXTURES / "contract.json")
    assert relative_file_set(rust_zzz_visualizer_root) == contract["file_sets"]["zzz"]

    for name, expected_hash in contract["static_text_sha256"]["zzz"].items():
        assert normalized_utf8_sha256(rust_zzz_visualizer_root / name) == expected_hash
    for name, expected_hash in contract["binary_sha256"]["zzz"].items():
        assert binary_sha256(rust_zzz_visualizer_root / name) == expected_hash


@pytest.mark.live
def test_real_zzz_cli_visualizer_matches_the_complete_python_oracle(
    cli_zzz_visualizer_root: tuple[Path, Path, Path, Path],
) -> None:
    actual_root, expected_root, actual_hub, expected_hub = cli_zzz_visualizer_root
    expected_data = load_json(expected_root / "data.json")
    actual_data = load_json(actual_root / "data.json")
    assert_json_contract_equal(expected_data, actual_data, dynamic_pointers=())

    contract = load_json(FIXTURES / "contract.json")
    expected_files = relative_file_set(expected_root)
    assert expected_files == contract["file_sets"]["zzz"]
    assert relative_file_set(actual_root) == expected_files

    for name, contract_hash in contract["static_text_sha256"]["zzz"].items():
        expected_hash = normalized_utf8_sha256(expected_root / name)
        assert expected_hash == contract_hash
        assert normalized_utf8_sha256(actual_root / name) == expected_hash
    for name, contract_hash in contract["binary_sha256"]["zzz"].items():
        expected_hash = binary_sha256(expected_root / name)
        assert expected_hash == contract_hash
        assert binary_sha256(actual_root / name) == expected_hash

    expected_hub_files = relative_file_set(expected_hub)
    assert expected_hub_files == contract["file_sets"]["hub"]
    assert relative_file_set(actual_hub) == expected_hub_files
    for name in expected_hub_files:
        expected_content = normalized_utf8(expected_hub / name)
        actual_content = normalized_utf8(actual_hub / name)
        assert actual_content == expected_content
        assert normalized_utf8_sha256(actual_hub / name) == normalized_utf8_sha256(
            expected_hub / name
        )

    for name in ("app.js", "styles.css"):
        assert (
            normalized_utf8_sha256(expected_hub / name)
            == contract["static_text_sha256"]["hub"][name]
        )

    hub_html = normalized_utf8(actual_hub / "index.html").decode("utf-8")
    assert 'data-src="../out/visualizer/index.html"' in hub_html
    assert (
        'data-src="../CLI%20ZZZ%20%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC%20output/'
        'visualizer/index.html"'
    ) in hub_html


@pytest.mark.parametrize("game", ["hsr", "zzz"])
def test_python_visualizer_matches_strict_json_oracle(
    visualizer_workspace: Path,
    game: str,
) -> None:
    actual = load_json(_visualizer_root(visualizer_workspace, game) / "data.json")
    expected = load_json(FIXTURES / game / "data.json")

    assert_json_contract_equal(expected, actual)
    assert set(actual) == set(expected)
    for key, value in actual.items():
        if key == "meta":
            continue
        assert value, f"oracle does not exercise top-level collection {game}:{key}"


def test_hsr_dense_oracle_exercises_phase_team_banner_tier_and_alias_contracts(
    visualizer_workspace: Path,
) -> None:
    data = load_json(_visualizer_root(visualizer_workspace, "hsr") / "data.json")

    phases = data["phaseInfoRows"]
    assert sum(
        row["mode"] == "moc" and row["phase_ver"] == "4.2.1" for row in phases
    ) == 2
    assert {
        (row["mode"], row["phase_name"])
        for row in phases
        if row["mechanic_name"]
    } == {
        ("moc", "Duty Action"),
        ("pf", "Falsehood to Fact"),
        ("aa", "The Humming Laughter"),
    }

    teams = data["teamTemplates"]
    assert [(row["mode"], row["scope_key"]) for row in teams] == [
        ("aa", "2-1"),
        ("moc", "all"),
        ("pf", "4-2"),
    ]
    assert len(
        {
            (row["mode"], row["scope_key"], tuple(sorted(row["chars"])))
            for row in teams
        }
    ) == len(teams)

    alpha_tiers = [
        row for row in data["tierRows"] if row["character_slug"] == "agent-alpha"
    ]
    assert [(row["role_group"], row["rating"]) for row in alpha_tiers] == [
        ("damage", "9"),
        ("damage", "7"),
        ("support", "8"),
    ]
    alpha = next(
        row for row in data["rosterRows"] if row["character_slug"] == "agent-alpha"
    )
    assert alpha["role_groups"] == "support;damage"

    topaz = next(
        row
        for row in data["rosterRows"]
        if row["character_slug"] == "topaz-and-numby"
    )
    assert topaz["alias_slugs"] == "topaz-and-numby;topaz"
    assert topaz["icon_url"] == "./assets/avatars/agent-alpha.webp?alias=topaz#safe"

    banner = next(
        row for row in data["bannerRows"] if row["character_slug"] == "agent-zeta"
    )
    assert banner["phase_status"] == "previous"
    assert banner["source_label"] == 789
    assert banner["source_url"] == "1e-07"
    banner_only = next(
        row for row in data["rosterRows"] if row["character_slug"] == "agent-zeta"
    )
    assert banner_only["source"] == "banner_plan"
    clock_banner = next(
        row for row in data["bannerRows"] if row["phase_id"] == "same-day-clock-window"
    )
    assert clock_banner["phase_status"] == "current"
    assert clock_banner["source_url"] == "100000000000000000000000000001"


def test_zzz_dense_oracle_exercises_explicit_context_and_selection_contracts(
    visualizer_workspace: Path,
) -> None:
    data = load_json(_visualizer_root(visualizer_workspace, "zzz") / "data.json")

    phases = {
        (row["mode"], row["phase_ver"]): row for row in data["phaseInfoRows"]
    }
    raw_phase = phases[("sd", "3.2")]
    assert raw_phase["collect_date"] == "2026-07-10"
    assert raw_phase["source_limited"] is True
    assert raw_phase["phase_status"] == "unknown"
    assert raw_phase["mechanic_source"] == (
        "Prydwen phase selector + ShiyuDataProcessed"
    )
    override_phase = phases[("da", "4.0")]
    assert override_phase["collect_date"] == "2026-07-11"
    assert override_phase["phase_status"] == "expired"
    assert override_phase["mechanic_source"] == "dense override"
    assert override_phase["mechanic_url"] == "123"

    teams = data["teamTemplates"]
    assert [(row["mode"], row["source_file"], row["rank"]) for row in teams] == [
        ("da", "4.0/override-team.json", 3.0),
        ("sd", "3.2/second-key.json", 2.0),
        ("sd", "3.2/stable-first.json", 5.0),
    ]
    assert all(row["bangboo_name"] == "邦布甲密" for row in teams)
    assert not any(
        row["source_file"] in {"3.1/old-team.json", "3.2/permuted-later.json"}
        for row in teams
    )

    roster = {row["character_slug"]: row for row in data["rosterRows"]}
    assert roster["agent-official"]["character_name_cn"] == "代理官方"
    assert roster["agent-official"]["tier"] == "未分档"
    assert roster["agent-alpha"]["tier"] == "T0.5"
    assert roster["agent-alpha"]["rating"] == "10"
    assert roster["agent-usage"]["character_name_en"] == "Usage First All"
    assert roster["agent-usage"]["rarity"] == "A"
    assert "bangboo-alpha" not in roster

    names = {row["character_slug"]: row for row in data["nameRows"]}
    assert names["bangboo-alpha"]["kind"] == "bangboo"
    assert names["bangboo-alpha"]["aliases"] == "boo-alpha"

    tiers = {row["tier_snapshot_id"]: row for row in data["tierRows"]}
    assert tiers["2026-07-12-best"]["icon_url"] == (
        "./assets/avatars/agent-alpha.webp?tier=best#safe"
    )
    assert tiers["2026-07-12-best"]["source_url"] == "docs/tier-best.html"
    assert tiers["2026-07-12-worse"]["icon_url"] == ""
    assert tiers["2026-07-12-worse"]["source_url"] == ""

    banner = next(
        row
        for row in data["bannerRows"]
        if row["character_slug"] == "agent-banner-only"
    )
    assert (banner["declared_phase_status"], banner["phase_status"]) == (
        "current",
        "previous",
    )
    assert roster["agent-banner-only"]["source"] == "banner_plan"
    assert banner["source_label"] == 789
    assert banner["source_url"] == "123"
    assert banner["icon_source_label"] == 456
    assert banner["icon_source_url"] == "456"

    assert data["decisionMethodVersion"] == "legacy-v0"
    decision = data["decisionCards"]
    assert decision["summary"]["source_url"] == "docs/decision-summary.html#safe"
    dense_card = decision["cards"][1]
    assert dense_card["source_url"] == "docs/decision-card.html?candidate=banner#safe"
    assert dense_card["icon_url"] == ""
    assert dense_card["reference_url"] == ""
    scalar_urls = decision["cards"][0]
    assert type(decision["summary"]["underflow_score"]) is float
    assert decision["summary"]["underflow_score"] == 0.0
    assert type(decision["summary"]["negative_zero_integer"]) is int
    assert decision["summary"]["negative_zero_integer"] == 0
    assert scalar_urls["source_url"] == "100000000000000000000000000000"
    assert scalar_urls["other_url"] == "1e-07"
    assert scalar_urls["negative_url"] == "-100000000000000000000000000001"
    assert scalar_urls["fixed_boundary_url"] == "0.0001"
    assert scalar_urls["scientific_boundary_url"] == "1e-05"
    assert scalar_urls["fixed_large_boundary_url"] == "1000000000000000.0"
    assert scalar_urls["scientific_large_boundary_url"] == "1e+16"
    assert scalar_urls["float_integer_url"] == "1.0"
    assert scalar_urls["zero_url"] == ""
    assert scalar_urls["true_url"] == "True"
    assert scalar_urls["false_url"] == ""
    assert scalar_urls["null_url"] == ""
    assert scalar_urls["uppercase_url"] == "HTTPS://example.com/X"
    assert scalar_urls["mixed_case_ipv6_url"] == "hTtPs://[::1]/X"
    assert scalar_urls["invalid_ipv6_url"] == ""
    assert scalar_urls["unmatched_bracket_url"] == ""
    assert scalar_urls["fullwidth_slash_url"] == ""
    assert scalar_urls["fullwidth_colon_url"] == ""
    assert scalar_urls["fullwidth_at_url"] == ""
    assert scalar_urls["fullwidth_question_url"] == ""
    assert scalar_urls["invalid_zone_url"] == ""
    assert scalar_urls["underflow_url"] == ""
    assert scalar_urls["negative_zero_url"] == ""
    clock_banner = next(
        row for row in data["bannerRows"] if row["phase_id"] == "same-day-clock-window"
    )
    assert clock_banner["phase_status"] == "current"


def test_python_banner_clock_uses_time_of_day_for_same_date_window() -> None:
    phase = {
        "status": "current",
        "start_at": "2026-07-12 12:00:00",
        "end_at": "2026-07-12 14:00:00",
    }
    assert effective_phase_status(phase, now=datetime(2026, 7, 12, 10)) == "next"
    assert effective_phase_status(phase, now=datetime(2026, 7, 12, 13)) == "current"
    assert effective_phase_status(phase, now=datetime(2026, 7, 12, 15)) == "previous"

    for separator in ("\u3000", "\u00a0"):
        unicode_whitespace = {
            "status": "current",
            "start_at": f"2026-07-12{separator}12:00:00",
            "end_at": f"2026-07-12{separator}14:00:00",
        }
        assert (
            effective_phase_status(
                unicode_whitespace, now=datetime(2026, 7, 12, 13)
            )
            == "current"
        )

    for start_at, end_at in (
        (
            "２０２６-０７-１２　１２:００:００",
            "２０２６-０７-１２　１４:００:００",
        ),
        (
            "٢٠٢٦-٠٧-١٢ ١٢:٠٠:٠٠",
            "٢٠٢٦-٠٧-١٢ ١٤:٠٠:٠٠",
        ),
    ):
        assert (
            effective_phase_status(
                {"status": "current", "start_at": start_at, "end_at": end_at},
                now=datetime(2026, 7, 12, 13),
            )
            == "current"
        )

    missing_whitespace = {
        "status": "current",
        "start_at": "2026-07-1212:00",
        "end_at": "2026-07-1214:00",
    }
    assert (
        effective_phase_status(missing_whitespace, now=datetime(2026, 7, 12, 13))
        == "previous"
    )


def test_json_comparator_is_type_and_array_order_strict() -> None:
    expected = {
        "meta": {"localDate": "2026-07-12", "source": "fixture"},
        "rows": [1, True, {"a/b~c": "value"}],
    }
    reordered_object = {
        "rows": [1, True, {"a/b~c": "value"}],
        "meta": {"source": "fixture", "localDate": "2030-01-02"},
    }
    assert compare_json_contract(expected, reordered_object) == []

    differences = compare_json_contract(
        expected,
        {
            "meta": {"localDate": "not-a-date", "source": "fixture"},
            "rows": [1.0, 1, {"a/b~c": "changed"}],
        },
    )
    assert any("/meta/localDate" in item and "YYYY-MM-DD" in item for item in differences)
    assert any("/rows/0: type int != float" in item for item in differences)
    assert any("/rows/1: type bool != int" in item for item in differences)
    assert any("/rows/2/a~1b~0c" in item for item in differences)

    swapped = compare_json_contract(
        {"meta": {"localDate": "2026-07-12"}, "rows": ["a", "b"]},
        {"meta": {"localDate": "2026-07-12"}, "rows": ["b", "a"]},
    )
    assert [item.split(":", 1)[0] for item in swapped] == ["/rows/0", "/rows/1"]


@pytest.mark.parametrize("target", ["hsr", "zzz", "hub"])
def test_visualizer_directory_file_set_is_exact(
    visualizer_workspace: Path,
    target: str,
) -> None:
    contract = load_json(FIXTURES / "contract.json")
    root = (
        visualizer_workspace / "visualizer"
        if target == "hub"
        else _visualizer_root(visualizer_workspace, target)
    )
    assert relative_file_set(root) == contract["file_sets"][target]
    assert all("\\" not in name and ":" not in name for name in relative_file_set(root))


@pytest.mark.parametrize("target", ["hsr", "zzz", "hub"])
def test_static_assets_are_utf8_and_match_normalized_lf_hashes(
    visualizer_workspace: Path,
    target: str,
) -> None:
    contract = load_json(FIXTURES / "contract.json")
    root = (
        visualizer_workspace / "visualizer"
        if target == "hub"
        else _visualizer_root(visualizer_workspace, target)
    )
    expected_names = {
        name
        for name in contract["file_sets"][target]
        if Path(name).suffix in {".html", ".css", ".js"}
    }
    assert set(contract["static_text_sha256"][target]) == expected_names
    for name, expected_hash in contract["static_text_sha256"][target].items():
        path = root / name
        normalized = normalized_utf8(path)
        assert normalized
        assert normalized_utf8_sha256(path) == expected_hash


@pytest.mark.parametrize("game", ["hsr", "zzz"])
def test_avatar_is_valid_preseeded_local_artifact(
    visualizer_workspace: Path,
    game: str,
) -> None:
    contract = load_json(FIXTURES / "contract.json")
    visualizer = _visualizer_root(visualizer_workspace, game)
    avatar = visualizer / "assets" / "avatars" / "agent-alpha.webp"
    payload = avatar.read_bytes()

    assert binary_sha256(avatar) == contract["binary_sha256"][game][
        "assets/avatars/agent-alpha.webp"
    ]
    assert payload[:4] == b"RIFF"
    assert payload[8:12] == b"WEBP"
    assert int.from_bytes(payload[4:8], "little") == len(payload) - 8

    data = load_json(visualizer / "data.json")
    icon_urls = list(_values_for_key(data, "icon_url"))
    assert icon_urls
    safe_avatar_url = safe_hsr_avatar_url if game == "hsr" else safe_zzz_avatar_url
    for icon_url in icon_urls:
        assert safe_avatar_url(icon_url) == icon_url
        if icon_url:
            asset_path = re.split(r"[?#]", icon_url, maxsplit=1)[0]
            assert asset_path == "./assets/avatars/agent-alpha.webp"
            resolved = (visualizer / asset_path).resolve()
            assert resolved.is_relative_to(visualizer.resolve())
            assert resolved.is_file()


@pytest.mark.parametrize("game", ["hsr", "zzz"])
def test_formula_and_html_payloads_remain_data_not_static_markup(
    visualizer_workspace: Path,
    game: str,
) -> None:
    visualizer = _visualizer_root(visualizer_workspace, game)
    data_text = (visualizer / "data.json").read_text(encoding="utf-8")
    data = json.loads(data_text)

    # JSON must escape the payload's quote characters. Compare the serialized
    # string body here, then assert the decoded value below.
    serialized_security_text = json.dumps(SECURITY_TEXT, ensure_ascii=False)[1:-1]
    assert serialized_security_text in data_text
    assert HTML_PAYLOAD in data_text
    assert data["changelogRows"][0]["text"] == SECURITY_TEXT
    assert type(data["changelogRows"][0]["text"]) is str
    for name in ("index.html", "styles.css", "app.js"):
        static_text = (visualizer / name).read_text(encoding="utf-8")
        assert SECURITY_TEXT not in static_text
        assert HTML_PAYLOAD not in static_text
    app = (visualizer / "app.js").read_text(encoding="utf-8")
    assert "replace(/[&<>\"']/g" in app


def test_outputs_are_portable_and_do_not_leak_workspace_path(
    visualizer_workspace: Path,
) -> None:
    workspace_spellings = {
        str(visualizer_workspace),
        str(visualizer_workspace).replace("\\", "/"),
    }
    for game in ("hsr", "zzz"):
        data_text = (_visualizer_root(visualizer_workspace, game) / "data.json").read_text(
            encoding="utf-8"
        )
        assert all(spelling not in data_text for spelling in workspace_spellings)

    hub = (visualizer_workspace / "visualizer" / "index.html").read_text(encoding="utf-8")
    assert 'data-src="../out/visualizer/index.html"' in hub
    assert 'data-src="../out_zzz/visualizer/index.html"' in hub


def test_fixture_is_desensitized_and_documents_single_dynamic_field() -> None:
    contract = load_json(FIXTURES / "contract.json")
    assert contract["schema_version"] == 1
    assert contract["oracle"] == (
        "final CSV + versioned sidecars + preseeded local avatars "
        "-> independent Python visualizer command"
    )
    assert contract["dynamic_json_pointers"] == [LOCAL_DATE_POINTER]
    assert contract["object_member_order"] == "ignored"
    assert contract["array_order"] == "strict"
    assert contract["json_types"] == "strict"

    fixture_texts: list[str] = []
    semantic_fixture_texts = [
        json.dumps(
            {key: value for key, value in contract.items() if not key.endswith("_sha256")},
            ensure_ascii=False,
            sort_keys=True,
        )
    ]
    for path in FIXTURES.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".b64"}:
            text = path.read_text(encoding="utf-8")
            fixture_texts.append(text)
            if path.name != "contract.json":
                semantic_fixture_texts.append(text)
    joined = "\n".join(fixture_texts)
    for forbidden in ("zy958", "C:\\Users\\", "C:/Users/", "/Users/", "/home/"):
        assert forbidden not in joined
    # Static SHA-256 digests can legitimately contain 9–12 consecutive digits;
    # only semantic fixture payloads can carry a user identifier.
    assert _UID_RE.search("\n".join(semantic_fixture_texts)) is None
    assert re.findall(r"https://([A-Za-z0-9.-]+)", joined)
    assert set(re.findall(r"https://([A-Za-z0-9.-]+)", joined)) == {
        "hsr.hoyoverse.com",
        "invalid.example",
        "wiki.biligame.com",
    }


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html,owned",
        "file:///C:/secret.txt",
        "//invalid.example/avatar.webp",
        "../escape.webp",
        "%2e%2e/escape.webp",
        "%252e%252e/escape.webp",
        ".\\escape.webp",
        "/absolute/avatar.webp",
    ],
)
def test_visualizer_url_sanitizers_reject_active_and_traversal_urls(value: str) -> None:
    assert safe_hsr_avatar_url(value) == ""
    assert safe_zzz_avatar_url(value) == ""
    assert safe_hsr_link_url(value) == ""
    assert safe_zzz_link_url(value) == ""


def test_visualizer_url_sanitizers_keep_explicit_safe_forms() -> None:
    relative = "./assets/avatars/agent-alpha.webp"
    external = "https://invalid.example/source"
    assert safe_hsr_avatar_url(relative) == relative
    assert safe_zzz_avatar_url(relative) == relative
    assert safe_hsr_link_url(external) == external
    assert safe_zzz_link_url(external) == external


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "../out", "out/zzz", "out\\zzz", "out\nzzz"],
)
def test_visualizer_hub_rejects_non_segment_output_names(value: str) -> None:
    with pytest.raises(ValueError):
        _safe_directory_segment(value)


def test_visualizer_hub_percent_encodes_attribute_payloads() -> None:
    html = visualizer_hub_html("HSR 中文 空格", 'zzz\"><img onerror=alert(1)>')
    assert '../HSR%20%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC/visualizer/index.html' in html
    assert '<img onerror=alert(1)>' not in html
    assert "zzz%22%3E%3Cimg%20onerror%3Dalert%281%29%3E" in html


def test_zzz_export_crosses_the_same_final_csv_visualizer_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[tuple[str, Path, object]] = []

    def fake_write_outputs(out_dir: Path, **rows: object) -> None:
        events.append(("write", out_dir, rows))

    def fake_rebuild(out_dir: Path) -> None:
        events.append(("rebuild", out_dir, None))

    monkeypatch.setattr("zzz_endgame_exporter.cli.write_outputs", fake_write_outputs)
    monkeypatch.setattr("zzz_endgame_exporter.cli.rebuild_visualizer_from_outputs", fake_rebuild)
    write_final_zzz_outputs_and_visualizer(tmp_path, usage_rows=[{"value": 1}])

    assert events == [
        ("write", tmp_path, {"usage_rows": [{"value": 1}]}),
        ("rebuild", tmp_path, None),
    ]


def test_visualizer_json_rejects_non_finite_numbers(tmp_path: Path) -> None:
    hsr_root = tmp_path / "hsr"
    zzz_root = tmp_path / "zzz"
    with _working_directory(tmp_path):
        with pytest.raises(ValueError, match="JSON compliant"):
            write_hsr_visualizer_app(
                hsr_root,
                trend_rows=[{"character_slug": "agent-alpha", "app_rate": float("nan")}],
                tier_rows=[],
                changelog_rows=[],
                chart_rows=[],
                character_usage_rows=[],
                team_rank_rows=[],
            )
        with pytest.raises(ValueError, match="JSON compliant"):
            write_zzz_visualizer_app(
                zzz_root,
                usage_rows=[{"character_slug": "agent-alpha", "app_rate": float("nan")}],
                tier_rows=[],
                team_rows=[],
                name_rows=[],
                changelog_rows=[],
            )
    assert not (hsr_root / "visualizer" / "data.json").exists()
    assert not (zzz_root / "visualizer" / "data.json").exists()


def test_zzz_decision_nan_fails_python_and_rust_without_data(
    visualizer_workspace: Path,
    tmp_path: Path,
) -> None:
    source_root = visualizer_workspace / "out_zzz"
    bad_root = tmp_path / "bad decision 中文 input"
    shutil.copytree(source_root, bad_root)
    shutil.rmtree(bad_root / "visualizer")
    (bad_root / "decision_cards.json").write_text(
        json.dumps({"summary": {"score": float("nan")}, "cards": []}) + "\n",
        encoding="utf-8",
    )

    with _working_directory(tmp_path), patch(
        "miho_core.banner_plan.datetime", _FixedLocalDateTime
    ), pytest.raises(ValueError, match="JSON compliant"):
        run_zzz_visualizer(Namespace(out=str(bad_root)))
    assert not (bad_root / "visualizer" / "data.json").exists()

    rust_out = tmp_path / "bad decision Rust output"
    python_avatar = (
        _visualizer_root(visualizer_workspace, "zzz")
        / "assets"
        / "avatars"
        / "agent-alpha.webp"
    )
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-core",
            "--example",
            "zzz_visualizer_contract",
            "--",
            str(bad_root),
            str(rust_out),
            LOCAL_DATETIME,
            str(bad_root / "zzz_endgame_phase_overrides.json"),
            str(bad_root / "zzz_banner_plan.json"),
            str(bad_root / "decision_cards.json"),
            "agent-alpha",
            str(python_avatar),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not (rust_out / "visualizer" / "data.json").exists()


def test_zzz_decision_exponent_overflow_fails_python_core_and_real_cli(
    visualizer_workspace: Path,
    tmp_path: Path,
) -> None:
    source_root = visualizer_workspace / "out_zzz"
    bad_root = tmp_path / "overflow decision 中文 input"
    shutil.copytree(source_root, bad_root)
    shutil.rmtree(bad_root / "visualizer")
    (bad_root / "decision_cards.json").write_text(
        '{"summary":{"positive":1e400,"negative":-1e400},"cards":[]}\n',
        encoding="utf-8",
    )

    with _working_directory(tmp_path), patch(
        "miho_core.banner_plan.datetime", _FixedLocalDateTime
    ), pytest.raises(ValueError, match="JSON compliant"):
        run_zzz_visualizer(Namespace(out=str(bad_root)))
    assert not (bad_root / "visualizer" / "data.json").exists()

    python_avatar = (
        _visualizer_root(visualizer_workspace, "zzz")
        / "assets"
        / "avatars"
        / "agent-alpha.webp"
    )
    core_out = tmp_path / "overflow decision core output"
    core_result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-core",
            "--example",
            "zzz_visualizer_contract",
            "--",
            str(bad_root),
            str(core_out),
            LOCAL_DATETIME,
            str(bad_root / "zzz_endgame_phase_overrides.json"),
            str(bad_root / "zzz_banner_plan.json"),
            str(bad_root / "decision_cards.json"),
            "agent-alpha",
            str(python_avatar),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert core_result.returncode != 0
    assert not (core_out / "visualizer" / "data.json").exists()

    cli_result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "-p",
            "miho-cli",
            "--",
            "zzz",
            "visualizer",
            "--out",
            str(bad_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert cli_result.returncode != 0
    assert "non-finite JSON number" in cli_result.stderr
    assert not (bad_root / "visualizer" / "data.json").exists()


def _visualizer_root(workspace: Path, game: str) -> Path:
    directory = "out" if game == "hsr" else "out_zzz"
    return workspace / directory / "visualizer"


def _stabilize_final_csvs(out_dir: Path, game: str) -> None:
    _mutate_csv(
        out_dir / "phase_index.csv",
        lambda row: {
            **row,
            "start_date": "1900-01-01",
            "end_date": "2999-12-31",
        },
    )
    for name in ("prydwen_tier_current.csv", "prydwen_tier_usage_trend.csv"):
        _mutate_csv(
            out_dir / name,
            lambda row: {
                **row,
                "icon_url": "./assets/avatars/agent-alpha.webp",
            },
        )
    _mutate_csv(
        out_dir / "prydwen_tier_changelog_history.csv",
        lambda row: {**row, "text": SECURITY_TEXT},
    )
    if game == "hsr":
        # HSR recommender fills dates from phase_index when team CSV dates are
        # absent. Keeping this explicit makes that cross-file contract visible.
        assert (out_dir / "team_rank_raw.csv").exists()
    else:
        assert (out_dir / "team_rank_dedup_unordered.csv").exists()


def _mutate_csv(path: Path, mutate: object) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [mutate(dict(row)) for row in reader]  # type: ignore[operator]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def _append_csv_rows(path: Path, additions: list[dict[str, object]]) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    rows.extend(
        {field: str(addition.get(field, "")) for field in fieldnames}
        for addition in additions
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def _first_csv_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.DictReader(handle))


def _densify_hsr_visualizer_csvs(out_dir: Path) -> None:
    phase_seed = _first_csv_row(out_dir / "phase_index.csv")
    phase_specs = [
        ("moc-duty", "moc", "混沌回忆", "4.2.1", "Duty Action"),
        ("moc-parallel", "moc", "混沌回忆", "4.2.1", "Parallel Trial"),
        ("pf-falsehood", "pf", "虚构叙事", "4.3.1", "Falsehood to Fact"),
        ("aa-humming", "aa", "异相仲裁", "4.3.1", "The Humming Laughter"),
    ]
    phases: list[dict[str, object]] = []
    for snapshot, mode, mode_cn, version, name in phase_specs:
        phases.append(
            {
                **phase_seed,
                "snapshot_id": snapshot,
                "collect_date": "2026-07-12",
                "mode": mode,
                "mode_cn": mode_cn,
                "phase_ver": version,
                "phase_name": name,
                "source": "dense-fixture",
                "source_path": f"dense/{snapshot}/",
                "note": f"dense phase {snapshot}",
            }
        )
    _append_csv_rows(out_dir / "phase_index.csv", phases)

    team_seed = _first_csv_row(out_dir / "team_rank_raw.csv")
    teams = [
        {
            **team_seed,
            "snapshot_id": "fixture-1-permuted",
            "rank": 2,
            "char_1_slug": team_seed["char_2_slug"],
            "char_2_slug": team_seed["char_1_slug"],
            "char_1_name_cn": team_seed["char_2_name_cn"],
            "char_2_name_cn": team_seed["char_1_name_cn"],
            "source_file": "fixture/teams-permuted.json",
            "raw_index": 2,
        },
        {
            **team_seed,
            "snapshot_id": "pf-falsehood",
            "mode": "pf",
            "mode_cn": "虚构叙事",
            "phase_ver": "4.3.1",
            "phase_name": "Falsehood to Fact",
            "scope": "2",
            "rank": 3,
            "source_file": "fixture/pf-teams.json",
            "raw_index": 3,
        },
        {
            **team_seed,
            "snapshot_id": "aa-humming",
            "mode": "aa",
            "mode_cn": "异相仲裁",
            "phase_ver": "4.3.1",
            "phase_name": "The Humming Laughter",
            "scope": "4",
            "rank": 4,
            "source_file": "fixture/aa-teams.json",
            "raw_index": 4,
        },
    ]
    _append_csv_rows(out_dir / "team_rank_raw.csv", teams)

    tier_seed = _first_csv_row(out_dir / "prydwen_tier_current.csv")
    tiers = [
        {
            **tier_seed,
            "tier_snapshot_id": "2026-07-12-low",
            "tier": "T2",
            "rating": 7,
            "tags": "same-role-lower-rating",
        },
        {
            **tier_seed,
            "tier_snapshot_id": "2026-07-12-support",
            "tier_mode": "pf",
            "tier_mode_cn": "虚构叙事",
            "prydwen_category": "Support",
            "prydwen_role": "Support",
            "role_group": "support",
            "role_group_cn": "辅助",
            "tier": "T0.5",
            "rating": 8,
            "tags": "cross-role",
        },
        {
            **tier_seed,
            "tier_snapshot_id": "2026-07-12-alias",
            "tier_mode": "aa",
            "tier_mode_cn": "异相仲裁",
            "character_slug": "topaz",
            "character_name_en": "Topaz and Numby",
            "character_name_cn": "托帕&账账",
            "prydwen_category": "Damage",
            "prydwen_role": "Damage",
            "role_group": "main_dps",
            "role_group_cn": "主C",
            "tier": "T0",
            "rating": 10,
            "tags": "safe-relative-alias",
            "element": "Fire",
            "path": "Hunt",
            "icon_url": "./assets/avatars/agent-alpha.webp?alias=topaz#safe",
        },
    ]
    _append_csv_rows(out_dir / "prydwen_tier_current.csv", tiers)


def _densify_zzz_visualizer_inputs(out_dir: Path) -> None:
    phase_seed = _first_csv_row(out_dir / "phase_index.csv")
    _append_csv_rows(
        out_dir / "phase_index.csv",
        [
            {
                **phase_seed,
                "snapshot_id": "3.2",
                "collect_date": "",
                "mode": "sd",
                "mode_cn": "式舆防卫",
                "phase_ver": "3.2",
                "phase_name": "Raw compensated phase",
                "start_date": "",
                "end_date": "",
                "source": "dense-fixture",
                "source_path": "dense/sd-3.2/",
                "note": "collect date comes from raw Prydwen option",
            },
            {
                **phase_seed,
                "snapshot_id": "4.0",
                "collect_date": "",
                "mode": "da",
                "mode_cn": "危局强袭",
                "phase_ver": "4.0",
                "phase_name": "Override phase",
                "start_date": "",
                "end_date": "",
                "source": "dense-fixture",
                "source_path": "dense/da-4.0/",
                "note": "dates come from explicit override",
            },
        ],
    )

    raw_prydwen = out_dir / "raw" / "prydwen"
    raw_prydwen.mkdir(parents=True, exist_ok=True)
    (raw_prydwen / "sd.html").write_text(
        "<select><option>3.2 - 10/July/2026 (2,468 users)</option></select>",
        encoding="utf-8",
    )
    (out_dir / "zzz_endgame_phase_overrides.json").write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "mode": "da",
                        "phase_ver": "4.0",
                        "collect_date": "2026-07-11",
                        "start_date": "1900-01-01",
                        "end_date": "1900-12-31",
                        "source_label": "dense override",
                        "source_url": 123,
                        "note": "expired explicit override",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    usage_seed = _first_csv_row(out_dir / "character_usage_long.csv")
    _append_csv_rows(
        out_dir / "character_usage_long.csv",
        [
            {
                **usage_seed,
                "snapshot_id": "usage-detail",
                "character_slug": "agent-usage",
                "character_name_en": "Detail Row",
                "sub_mode": "7-1",
                "sub_mode_cn": "7-1",
                "rarity": "B",
                "app_rate": 99,
            },
            {
                **usage_seed,
                "snapshot_id": "usage-first-all",
                "character_slug": "agent-usage",
                "character_name_en": "Usage First All",
                "sub_mode": "all",
                "sub_mode_cn": "全部",
                "rarity": "A",
                "app_rate": 17,
            },
            {
                **usage_seed,
                "snapshot_id": "usage-later-all",
                "character_slug": "agent-usage",
                "character_name_en": "Usage Later All",
                "sub_mode": "all",
                "sub_mode_cn": "全部",
                "rarity": "S",
                "app_rate": 88,
            },
        ],
    )

    tier_seed = _first_csv_row(out_dir / "prydwen_tier_current.csv")
    _append_csv_rows(
        out_dir / "prydwen_tier_current.csv",
        [
            {
                **tier_seed,
                "tier_snapshot_id": "2026-07-12-best",
                "tier": "T0.5",
                "rating": 10,
                "tags": "best-tier-wins",
                "icon_url": "./assets/avatars/agent-alpha.webp?tier=best#safe",
                "source_url": "docs/tier-best.html",
            },
            {
                **tier_seed,
                "tier_snapshot_id": "2026-07-12-worse",
                "tier": "T2",
                "rating": 7,
                "tags": "worse-tier-ignored-by-roster",
                "icon_url": "javascript:alert(1)",
                "source_url": "data:text/html,active",
            },
        ],
    )

    team_seed = _first_csv_row(out_dir / "team_rank_dedup_unordered.csv")
    _append_csv_rows(
        out_dir / "team_rank_dedup_unordered.csv",
        [
            {
                **team_seed,
                "snapshot_id": "3.1",
                "collect_date": "",
                "phase_ver": "3.1",
                "phase_name": "Old team phase",
                "rank": 0,
                "source_file": "3.1/old-team.json",
                "bangboo_name_cn": "",
            },
            {
                **team_seed,
                "snapshot_id": "3.2",
                "collect_date": "",
                "phase_ver": "3.2",
                "phase_name": "Raw compensated phase",
                "rank": 5,
                "source_file": "3.2/stable-first.json",
                "bangboo_name_cn": "",
            },
            {
                **team_seed,
                "snapshot_id": "3.2",
                "collect_date": "",
                "phase_ver": "3.2",
                "phase_name": "Raw compensated phase",
                "rank": 1,
                "char_1_slug": team_seed["char_2_slug"],
                "char_2_slug": team_seed["char_1_slug"],
                "source_file": "3.2/permuted-later.json",
                "bangboo_name_cn": "",
            },
            {
                **team_seed,
                "snapshot_id": "3.2",
                "collect_date": "",
                "phase_ver": "3.2",
                "phase_name": "Raw compensated phase",
                "rank": 2,
                "char_3_slug": "agent-official",
                "char_3_name_cn": "",
                "source_file": "3.2/second-key.json",
                "bangboo_name_cn": "",
            },
            {
                **team_seed,
                "snapshot_id": "4.0",
                "collect_date": "",
                "mode": "da",
                "mode_cn": "危局强袭",
                "phase_ver": "4.0",
                "phase_name": "Override phase",
                "rank": 3,
                "char_1_slug": "agent-official",
                "char_3_slug": "agent-gamma",
                "char_1_name_cn": "",
                "source_file": "4.0/override-team.json",
                "bangboo_name_cn": "",
            },
        ],
    )

    name_seed = _first_csv_row(out_dir / "name_map.csv")
    _append_csv_rows(
        out_dir / "name_map.csv",
        [
            {
                **name_seed,
                "character_slug": "agent-beta",
                "character_name_en": "Agent Beta",
                "character_name_cn": "代理乙",
                "aliases": "beta-alias",
                "kind": "agent",
                "release_order": 20,
            },
            {
                **name_seed,
                "character_slug": "agent-gamma",
                "character_name_en": "Agent Gamma",
                "character_name_cn": "代理丙",
                "aliases": "",
                "kind": "agent",
                "release_order": 30,
            },
            {
                **name_seed,
                "character_slug": "agent-official",
                "character_name_en": "",
                "character_name_cn": "",
                "source": "HoYoWiki official-only",
                "aliases": "official-alias",
                "kind": "agent",
                "release_order": "",
            },
            {
                **name_seed,
                "character_slug": "bangboo-alpha",
                "character_name_en": "Bangboo Alpha",
                "character_name_cn": "邦布甲密",
                "source": "HoYoWiki bangboo",
                "aliases": "boo-alpha",
                "kind": "bangboo",
                "release_order": 1001,
            },
        ],
    )
    _write_zzz_official_roster_fixture(out_dir)


def _write_zzz_official_roster_fixture(out_dir: Path) -> None:
    raw = out_dir / "raw" / "hoyowiki"
    raw.mkdir(parents=True, exist_ok=True)
    en = [
        {
            "entry_page_id": "1",
            "name": "Agent Alpha",
            "filter_values": {
                "agent_stats": {"values": ["Ether"]},
                "agent_specialties": {"values": ["Attack"]},
                "agent_rarity": {"values": ["S"]},
            },
            "icon_url": "./assets/avatars/agent-alpha.webp",
        },
        {
            "entry_page_id": "2",
            "name": "Agent Official",
            "filter_values": {
                "agent_stats": {"values": ["Electric"]},
                "agent_specialties": {"values": ["Support"]},
                "agent_rarity": {"values": ["S"]},
            },
            "icon_url": "javascript:alert(1)",
        },
    ]
    zh = [
        {
            "entry_page_id": "1",
            "name": "代理甲",
            "filter_values": {
                "agent_stats": {"values": ["以太属性"]},
                "agent_specialties": {"values": ["强攻"]},
                "agent_rarity": {"values": ["S"]},
            },
            "icon_url": "./assets/avatars/agent-alpha.webp",
        },
        {
            "entry_page_id": "2",
            "name": "代理官方",
            "filter_values": {
                "agent_stats": {"values": ["电属性"]},
                "agent_specialties": {"values": ["支援"]},
                "agent_rarity": {"values": ["S"]},
            },
            "icon_url": "javascript:alert(1)",
        },
    ]
    (raw / "zzz_agents_en-us.json").write_text(
        json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (raw / "zzz_agents_zh-cn.json").write_text(
        json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_dense_zzz_banner_plan(source: Path, destination: Path) -> None:
    plan = json.loads(source.read_text(encoding="utf-8"))
    plan["phases"].append(
        {
            "id": "date-effective-banner-only",
            "status": "current",
            "title": "Date-effective ZZZ fixture",
            "subtitle": "Declared current but expired by dates",
            "date_range": "1900-01-01 - 1900-12-31",
            "source_label": 789,
            "source_url": 123,
            "characters": [
                {
                    "slug": "agent-banner-only",
                    "name_cn": "代理卡池",
                    "name_en": "Agent Banner Only",
                    "banner_role": "banner-only",
                    "rarity": "S",
                    "element_cn": "冰",
                    "style_cn": "支援",
                    "role_group_cn": "辅助",
                    "icon_url": "./assets/avatars/agent-alpha.webp?banner=zzz#safe",
                    "icon_source_label": 456,
                    "icon_source_url": 456,
                    "analysis_tags": ["date-effective", "banner-only"],
                    "focus": "explicit local datetime",
                }
            ],
        }
    )
    plan["phases"].append(
        {
            "id": "same-day-clock-window",
            "status": "current",
            "title": "Same-day ZZZ clock fixture",
            "start_at": "2026-07-12 12:00:00",
            "end_at": "2026-07-12 14:00:00",
            "source_label": "fixed clock fixture",
            "source_url": "docs/zzz-clock.html",
            "characters": [
                {
                    "slug": "agent-alpha",
                    "name_cn": "代理甲",
                    "name_en": "Agent Alpha",
                    "icon_url": "./assets/avatars/agent-alpha.webp",
                    "analysis_tags": ["same-day", "clock"],
                    "focus": "13:00 must be current",
                }
            ],
        }
    )
    destination.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_dense_zzz_decision_cards(source: Path, destination: Path) -> None:
    decision = json.loads(source.read_text(encoding="utf-8"))
    decision["summary"]["candidate_count"] = 2
    decision["summary"]["source_url"] = "docs/decision-summary.html#safe"
    decision["summary"]["underflow_score"] = "__RAW_UNDERFLOW_SCORE__"
    decision["summary"]["negative_zero_integer"] = "__RAW_NEGATIVE_ZERO_INTEGER__"
    decision["cards"][0]["source_url"] = 100000000000000000000000000000
    decision["cards"][0]["other_url"] = 1e-7
    decision["cards"][0]["negative_url"] = -100000000000000000000000000001
    decision["cards"][0]["fixed_boundary_url"] = 1e-4
    decision["cards"][0]["scientific_boundary_url"] = 1e-5
    decision["cards"][0]["fixed_large_boundary_url"] = 1e15
    decision["cards"][0]["scientific_large_boundary_url"] = 1e16
    decision["cards"][0]["float_integer_url"] = 1.0
    decision["cards"][0]["zero_url"] = 0
    decision["cards"][0]["true_url"] = True
    decision["cards"][0]["false_url"] = False
    decision["cards"][0]["null_url"] = None
    decision["cards"][0]["uppercase_url"] = "HTTPS://example.com/X"
    decision["cards"][0]["mixed_case_ipv6_url"] = "hTtPs://[::1]/X"
    decision["cards"][0]["invalid_ipv6_url"] = "https://[not-an-ipv6]/X"
    decision["cards"][0]["unmatched_bracket_url"] = "https://["
    decision["cards"][0]["fullwidth_slash_url"] = "https://example.com／evil"
    decision["cards"][0]["fullwidth_colon_url"] = "https://example.com：80/x"
    decision["cards"][0]["fullwidth_at_url"] = "https://user＠example.com/x"
    decision["cards"][0]["fullwidth_question_url"] = "https://example.com？x"
    decision["cards"][0]["invalid_zone_url"] = "http://[fe80::1%eth%0]/"
    decision["cards"][0]["underflow_url"] = "__RAW_UNDERFLOW_URL__"
    decision["cards"][0]["negative_zero_url"] = "__RAW_NEGATIVE_ZERO_URL__"
    decision["cards"].append(
        {
            "character_slug": "agent-banner-only",
            "character_name_cn": "代理卡池",
            "decision": "observe",
            "reason": "dense decision contract",
            "source_url": "docs/decision-card.html?candidate=banner#safe",
            "icon_url": "javascript:alert(1)",
            "reference_url": "data:text/html,active",
        }
    )
    payload = json.dumps(decision, ensure_ascii=False, indent=2) + "\n"
    payload = payload.replace('"__RAW_UNDERFLOW_SCORE__"', "1e-400")
    payload = payload.replace('"__RAW_UNDERFLOW_URL__"', "1e-400")
    payload = payload.replace('"__RAW_NEGATIVE_ZERO_INTEGER__"', "-0")
    payload = payload.replace('"__RAW_NEGATIVE_ZERO_URL__"', "-0")
    destination.write_text(payload, encoding="utf-8")


def _write_dense_hsr_banner_plan(source: Path, destination: Path) -> None:
    plan = json.loads(source.read_text(encoding="utf-8"))
    plan["phases"].append(
        {
            "id": "date-driven-previous",
            "status": "current",
            "title": "Date-driven fixture",
            "subtitle": "Declared current, dates make it previous",
            "date_range": "1900-01-01 - 1900-12-31",
            "source_label": 789,
            "source_url": 1e-7,
            "characters": [
                {
                    "slug": "agent-zeta",
                    "name_cn": "代理己",
                    "name_en": "Agent Zeta",
                    "banner_role": "banner-only",
                    "rarity": "5",
                    "element_cn": "冰",
                    "path_cn": "记忆",
                    "role_group_cns": "辅助",
                    "icon_url": "./assets/avatars/agent-alpha.webp?banner=zeta#safe",
                    "analysis_tags": ["date-driven", "banner-only"],
                    "focus": "date-derived status",
                }
            ],
        }
    )
    plan["phases"].append(
        {
            "id": "same-day-clock-window",
            "status": "current",
            "title": "Same-day HSR clock fixture",
            "start_at": "2026-07-12 12:00:00",
            "end_at": "2026-07-12 14:00:00",
            "source_label": "fixed clock fixture",
            "source_url": 100000000000000000000000000001,
            "characters": [
                {
                    "slug": "agent-alpha",
                    "name_cn": "代理甲",
                    "name_en": "Agent Alpha",
                    "icon_url": "./assets/avatars/agent-alpha.webp",
                    "analysis_tags": ["same-day", "clock"],
                    "focus": "13:00 must be current",
                }
            ],
        }
    )
    destination.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _preseed_avatar(out_dir: Path) -> None:
    encoded = (FIXTURES / "avatar.webp.b64").read_text(encoding="ascii").strip()
    destination = out_dir / "visualizer" / "assets" / "avatars" / "agent-alpha.webp"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(encoded, validate=True))


def _write_hsr_official_roster_fixture(out_dir: Path) -> None:
    raw = out_dir / "raw" / "hoyowiki"
    raw.mkdir(parents=True, exist_ok=True)
    common = {
        "character_rarity": {"values": ["5-star"]},
        "character_combat_type": {"values": ["Imaginary"]},
        "character_paths": {"values": ["Hunt"]},
    }
    en = [
        {
            "entry_page_id": "1",
            "name": "Agent Alpha",
            "filter_values": common,
            "icon_url": "./assets/avatars/agent-alpha.webp",
        },
        {
            "entry_page_id": "2",
            "name": "Agent Epsilon",
            "filter_values": {
                "character_rarity": {"values": ["4-star"]},
                "character_combat_type": {"values": ["Fire"]},
                "character_paths": {"values": ["Harmony"]},
            },
        },
        {"entry_page_id": "3", "name": ""},
        {
            "entry_page_id": "4",
            "name": "Topaz",
            "filter_values": {
                "character_rarity": {"values": ["5-star"]},
                "character_combat_type": {"values": ["Fire"]},
                "character_paths": {"values": ["Hunt"]},
            },
            "icon_url": "./assets/avatars/agent-alpha.webp?alias=topaz#safe",
        },
    ]
    zh = [
        {
            "entry_page_id": "1",
            "name": "代理甲",
            "filter_values": {
                "character_rarity": {"values": ["五星"]},
                "character_combat_type": {"values": ["虚数"]},
                "character_paths": {"values": ["巡猎"]},
            },
            "icon_url": "./assets/avatars/agent-alpha.webp",
        },
        {
            "entry_page_id": "2",
            "name": "代理戊",
            "filter_values": {
                "character_rarity": {"values": ["四星"]},
                "character_combat_type": {"values": ["火"]},
                "character_paths": {"values": ["同谐"]},
            },
            "icon_url": "javascript:alert(1)",
        },
        {"entry_page_id": "3", "name": "仅中文角色"},
        {
            "entry_page_id": "4",
            "name": "托帕&账账",
            "filter_values": {
                "character_rarity": {"values": ["五星"]},
                "character_combat_type": {"values": ["火"]},
                "character_paths": {"values": ["巡猎"]},
            },
            "icon_url": "./assets/avatars/agent-alpha.webp?alias=topaz#safe",
        },
    ]
    (raw / "hsr_characters_en-us.json").write_text(
        json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (raw / "hsr_characters_zh-cn.json").write_text(
        json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _values_for_key(value: object, target: str):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == target:
                yield item
            yield from _values_for_key(item, target)
    elif isinstance(value, list):
        for item in value:
            yield from _values_for_key(item, target)


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _regenerate_oracles() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="miho-visualizer-oracle-") as temporary:
        class Factory:
            def mktemp(self, _name: str) -> Path:
                return Path(temporary)

        workspace = visualizer_workspace.__wrapped__(Factory())  # type: ignore[attr-defined]
        for game in ("hsr", "zzz"):
            source = _visualizer_root(workspace, game) / "data.json"
            target = FIXTURES / game / "data.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

        roots = {
            "hsr": _visualizer_root(workspace, "hsr"),
            "zzz": _visualizer_root(workspace, "zzz"),
            "hub": workspace / "visualizer",
        }
        static_text_sha256 = {
            target: {
                path.relative_to(root).as_posix(): normalized_utf8_sha256(path)
                for path in sorted(root.rglob("*"))
                if path.is_file() and path.suffix in {".html", ".css", ".js"}
            }
            for target, root in roots.items()
        }
        contract = {
            "schema_version": 1,
            "oracle": (
                "final CSV + versioned sidecars + preseeded local avatars "
                "-> independent Python visualizer command"
            ),
            "dynamic_json_pointers": [LOCAL_DATE_POINTER],
            "object_member_order": "ignored",
            "array_order": "strict",
            "json_types": "strict",
            "file_sets": {
                target: relative_file_set(root) for target, root in roots.items()
            },
            "static_text_sha256": static_text_sha256,
            "binary_sha256": {
                target: {
                    path.relative_to(root).as_posix(): binary_sha256(path)
                    for path in sorted(root.rglob("*"))
                    if path.is_file()
                    and path.suffix not in {".json", ".html", ".css", ".js"}
                }
                for target, root in roots.items()
            },
        }
        (FIXTURES / "contract.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    _regenerate_oracles()
