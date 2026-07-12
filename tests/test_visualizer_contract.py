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
    _write_hsr_official_roster_fixture(hsr_root)

    _write_dense_hsr_banner_plan(
        FIXTURES / "hsr_banner_plan.json", hsr_root / "hsr_banner_plan.json"
    )
    shutil.copyfile(FIXTURES / "zzz_banner_plan.json", zzz_root / "zzz_banner_plan.json")
    shutil.copyfile(FIXTURES / "decision_cards.json", zzz_root / "decision_cards.json")
    _preseed_avatar(hsr_root)
    _preseed_avatar(zzz_root)

    def forbidden_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("visualizer oracle attempted an outbound request")

    workspace.mkdir(parents=True, exist_ok=True)
    with _working_directory(workspace), patch(
        "urllib.request.urlopen",
        side_effect=forbidden_network,
    ):
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
    local_date = load_json(python_root / "data.json")["meta"]["localDate"]
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
            local_date,
            str(csv_root / "hsr_banner_plan.json"),
            "agent-alpha",
            str(python_root / "assets" / "avatars" / "agent-alpha.webp"),
        ],
        cwd=ROOT,
        check=True,
    )
    return out_root / "visualizer"


@pytest.fixture(scope="module")
def cli_hsr_visualizer_root(
    tmp_path_factory: pytest.TempPathFactory,
    visualizer_workspace: Path,
) -> Path:
    source_root = visualizer_workspace / "out"
    out_root = (
        tmp_path_factory.mktemp("miho-cli-hsr-visualizer-contract")
        / "CLI 中文 空格 output"
    )
    shutil.copytree(source_root, out_root)
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
    return out_root / "visualizer"


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


def test_real_hsr_cli_visualizer_matches_the_complete_python_oracle(
    visualizer_workspace: Path,
    cli_hsr_visualizer_root: Path,
) -> None:
    expected_root = _visualizer_root(visualizer_workspace, "hsr")
    expected_data = load_json(expected_root / "data.json")
    actual_data = load_json(cli_hsr_visualizer_root / "data.json")
    assert_json_contract_equal(expected_data, actual_data, dynamic_pointers=())

    contract = load_json(FIXTURES / "contract.json")
    expected_files = relative_file_set(expected_root)
    assert expected_files == contract["file_sets"]["hsr"]
    assert relative_file_set(cli_hsr_visualizer_root) == expected_files

    for name, contract_hash in contract["static_text_sha256"]["hsr"].items():
        expected_hash = normalized_utf8_sha256(expected_root / name)
        assert expected_hash == contract_hash
        assert normalized_utf8_sha256(cli_hsr_visualizer_root / name) == expected_hash
    for name, contract_hash in contract["binary_sha256"]["hsr"].items():
        expected_hash = binary_sha256(expected_root / name)
        assert expected_hash == contract_hash
        assert binary_sha256(cli_hsr_visualizer_root / name) == expected_hash


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
    assert banner["source_url"] == "docs/banner-source.html"
    banner_only = next(
        row for row in data["rosterRows"] if row["character_slug"] == "agent-zeta"
    )
    assert banner_only["source"] == "banner_plan"


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
    for path in FIXTURES.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".b64"}:
            fixture_texts.append(path.read_text(encoding="utf-8"))
    joined = "\n".join(fixture_texts)
    for forbidden in ("zy958", "C:\\Users\\", "C:/Users/", "/Users/", "/home/"):
        assert forbidden not in joined
    assert _UID_RE.search(joined) is None
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


def _write_dense_hsr_banner_plan(source: Path, destination: Path) -> None:
    plan = json.loads(source.read_text(encoding="utf-8"))
    plan["phases"].append(
        {
            "id": "date-driven-previous",
            "status": "current",
            "title": "Date-driven fixture",
            "subtitle": "Declared current, dates make it previous",
            "date_range": "1900-01-01 - 1900-12-31",
            "source_label": "dense fixture",
            "source_url": "docs/banner-source.html",
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
