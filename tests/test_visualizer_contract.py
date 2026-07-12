from __future__ import annotations

import base64
import csv
import json
import os
import re
import shutil
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
    _stabilize_final_csvs(hsr_root, "hsr")
    _stabilize_final_csvs(zzz_root, "zzz")

    shutil.copyfile(FIXTURES / "hsr_banner_plan.json", hsr_root / "hsr_banner_plan.json")
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
    for icon_url in icon_urls:
        assert icon_url in {"", "./assets/avatars/agent-alpha.webp"}
        if icon_url:
            resolved = (visualizer / icon_url).resolve()
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
        "invalid.example"
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


def _preseed_avatar(out_dir: Path) -> None:
    encoded = (FIXTURES / "avatar.webp.b64").read_text(encoding="ascii").strip()
    destination = out_dir / "visualizer" / "assets" / "avatars" / "agent-alpha.webp"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(encoded, validate=True))


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
