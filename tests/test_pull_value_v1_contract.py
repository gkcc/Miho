from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from miho_core.pull_value import PullValueCard, build_pull_value_cards
import zzz_endgame_exporter.cli as zzz_cli


FIXTURE = Path(__file__).parent / "fixtures" / "pull_value_v1_contract"
EXPECTED = FIXTURE / "expected"
FIXED_CLOCK = datetime(2026, 7, 12, 13, 14, 15)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 12, 13, 14, 15)
        return value if tz is None else value.astimezone(tz)


def _contract() -> dict[str, Any]:
    return json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))


def _copy_real_inputs(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "pull_value_v1_contract"
    shutil.copytree(FIXTURE / "input", runtime_root / "input")
    return runtime_root


def _build(runtime_root: Path, status: str) -> dict[str, Any]:
    root = runtime_root / "input"
    return build_pull_value_cards(
        root / "data",
        box_path=root / "box.json",
        plan_path=root / "plan.json",
        statuses=[status],
        mechanism_notes_dir=root / "mechanism_notes",
        decision_baseline_path=root / "baseline.json",
        local_datetime=FIXED_CLOCK,
    )


def _normalize(value: Any, runtime_root: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(runtime_root), "<ROOT>")
    if isinstance(value, dict):
        return {key: _normalize(item, runtime_root) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item, runtime_root) for item in value]
    return value


def _typed_cards_json(result: dict[str, Any], runtime_root: Path) -> str:
    payload = {
        "summary": result["summary"],
        "cards": [asdict(card) for card in result["cards"]],
    }
    return json.dumps(_normalize(payload, runtime_root), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _normalized_file(path: Path, runtime_root: Path) -> str:
    return path.read_text(encoding="utf-8").replace(str(runtime_root), "<ROOT>")


@pytest.mark.parametrize("status", ["current", "next"])
def test_python_core_matches_dense_pull_value_v1_typed_card_golden(tmp_path: Path, status: str) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    actual = _typed_cards_json(_build(runtime_root, status), runtime_root)
    assert actual == (EXPECTED / f"{status}_pull_cards.json").read_text(encoding="utf-8")


def test_dense_oracle_freezes_pull_value_invariants(tmp_path: Path) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    current = _build(runtime_root, "current")
    next_result = _build(runtime_root, "next")
    current_cards = {card.slug: card for card in current["cards"]}
    next_cards = {card.slug: card for card in next_result["cards"]}

    assert current["summary"]["generated_at"] == "2026-07-12T13:14:15"
    assert current["summary"]["method_version"] == "evidence-first-v1-20260712"
    assert current["summary"]["planned_slugs"] == ["alpha", "beta", "gamma", "nova", "low-a"]
    assert next_result["summary"]["planned_slugs"] == ["delta", "epsilon", "zeta"]
    assert current["summary"]["filtered_low_rarity_slugs"] == ["low-a"]
    assert "low-a" not in current_cards

    assert (current_cards["alpha"].candidate_type, current_cards["alpha"].pull_value) == ("rerun", "高")
    assert (current_cards["beta"].candidate_type, current_cards["beta"].pull_value) == ("rerun", "中高")
    assert (current_cards["gamma"].candidate_type, current_cards["gamma"].pull_value) == ("rerun", "中")
    assert (current_cards["nova"].candidate_type, current_cards["nova"].pull_value) == ("new", "等实测")
    assert (next_cards["delta"].candidate_type, next_cards["delta"].pull_value) == ("rerun", "中高")
    assert (next_cards["epsilon"].candidate_type, next_cards["epsilon"].pull_value) == ("rerun", "中")
    assert (next_cards["zeta"].candidate_type, next_cards["zeta"].pull_value) == ("new", "等实测")

    alpha = current_cards["alpha"]
    assert alpha.name_cn == "阿尔法候选名"
    assert alpha.mechanism_summary.startswith("候选元素 / 候选特性 / 候选定位；候选 focus 优先")
    assert alpha.local_rule_stage == "0+0"
    assert alpha.prior_final_stage == "1+1"
    assert alpha.final_stage == "1+1"
    assert alpha.stage_delta == "0+0 -> 1+1"
    assert alpha.delta_requires_review is True
    assert alpha.change_allowed_reason == "only_with_new_evidence"
    assert current_cards["beta"].stage_delta == "none"
    assert current_cards["nova"].final_stage == "0+1"
    assert current_cards["nova"].delta_requires_review is True

    assert [ref["confidence"] for ref in next_cards["delta"].evidence_refs] == ["B", "B"]
    epsilon = next_cards["epsilon"]
    assert [(ref["confidence"], ref["plan_dependency"]) for ref in epsilon.evidence_refs] == [
        ("B", ["epsilon"]),
    ]
    assert [(ref["confidence"], ref["plan_dependency"]) for ref in epsilon.risk_evidence_refs] == [
        ("B+", ["epsilon", "zeta"]),
    ]
    assert any("conditional risk" in note for note in epsilon.risk_notes)
    assert next_cards["zeta"].evidence_ids == ()
    assert next_cards["zeta"].risk_evidence_refs[0]["plan_dependency"] == ["epsilon", "zeta"]

    stable_ids = _contract()["stable_evidence_ids"]
    refs = [
        ref
        for result in (current, next_result)
        for card in result["cards"]
        for ref in (*card.evidence_refs, *card.risk_evidence_refs)
    ]
    by_key = {ref["evidence_key"]: ref for ref in refs}
    assert {key: by_key[key]["evidence_id"] for key in stable_ids} == stable_ids
    assert all(ref["mode"] == "sd" for ref in refs)
    assert all(ref["phase_versions"] and ref["scopes"] and ref["observation_keys"] for ref in refs)


def test_python_cli_default_dual_markdown_matches_golden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    root = runtime_root / "input"
    data = root / "data"
    monkeypatch.setattr(zzz_cli, "datetime", _FixedDateTime)

    assert zzz_cli.main(
        [
            "pull-value",
            "--box", str(root / "box.json"),
            "--out", str(data),
            "--plan", str(root / "plan.json"),
            "--mechanism-notes-dir", str(root / "mechanism_notes"),
            "--decision-baseline", str(root / "baseline.json"),
        ]
    ) == 0

    assert not (data / "pull_value_report.md").exists()
    for status in ("current", "next"):
        actual = _normalized_file(data / f"{status}_pull_value_report.md", runtime_root)
        expected = (EXPECTED / f"{status}_pull_value_report.md").read_text(encoding="utf-8")
        assert actual == expected


def test_python_cli_explicit_single_output_keeps_required_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    root = runtime_root / "input"
    output = runtime_root / "combined.md"
    monkeypatch.setattr(zzz_cli, "datetime", _FixedDateTime)

    assert zzz_cli.main(
        [
            "pull-value",
            "--box", str(root / "box.json"),
            "--out", str(root / "data"),
            "--plan", str(root / "plan.json"),
            "--plan-status", "current,next",
            "--mechanism-notes-dir", str(root / "mechanism_notes"),
            "--decision-baseline", str(root / "baseline.json"),
            "--output", str(output),
        ]
    ) == 0

    text = output.read_text(encoding="utf-8")
    assert "- 生成时间：2026-07-12T13:14:15" in text
    assert "- 方法版本：evidence-first-v1-20260712" in text
    assert f"- 数据目录：`{root / 'data'}`" in text
    assert f"- Box：`{root / 'box.json'}`" in text
    assert f"- 卡池计划：`{root / 'plan.json'}`" in text
    assert f"- 机制笔记：`{root / 'mechanism_notes'}`" in text
    assert f"- 定档 baseline：`{root / 'baseline.json'}`" in text
    assert "- 候选角色：7；planned_slugs：alpha, beta, gamma, nova, low-a, delta, epsilon, zeta" in text
    assert not (root / "data" / "current_pull_value_report.md").exists()
    assert not (root / "data" / "next_pull_value_report.md").exists()


def test_contract_freezes_inputs_outputs_schemas_hashes_and_rust_seam() -> None:
    contract = _contract()
    input_files = sorted(
        path.relative_to(FIXTURE / "input").as_posix()
        for path in (FIXTURE / "input").rglob("*")
        if path.is_file()
    )
    output_files = sorted(path.name for path in EXPECTED.iterdir() if path.is_file())
    assert input_files == contract["input_files"]
    assert output_files == contract["output_files"]
    assert contract["normalizations"] == ["temporary_root"]
    assert contract["fixed_local_clock"] == FIXED_CLOCK.isoformat(timespec="seconds")

    schema = contract["schemas"]["typed_cards_json"]
    assert schema["top_level_fields"] == ["summary", "cards"]
    assert schema["card_fields"] == [field.name for field in fields(PullValueCard)]
    for status in ("current", "next"):
        payload = json.loads((EXPECTED / f"{status}_pull_cards.json").read_text(encoding="utf-8"))
        assert list(payload) == schema["top_level_fields"]
        assert list(payload["summary"]) == schema["summary_fields"]
        assert all(list(card) == schema["card_fields"] for card in payload["cards"])
        for card in payload["cards"]:
            for ref in [*card["evidence_refs"], *card["risk_evidence_refs"]]:
                assert list(ref) == schema["evidence_ref_fields"]

    markdown_header = next(
        line
        for line in (EXPECTED / "current_pull_value_report.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| character |")
    )
    columns = [part.strip() for part in markdown_header.strip("|").split("|")]
    assert columns == contract["schemas"]["markdown"]["summary_table_columns"]

    for name in output_files:
        canonical = (EXPECTED / name).read_text(encoding="utf-8")
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert digest == contract["normalized_sha256"][name]

    seam = contract["rust_command_comparison_seam"]
    assert seam["status"] == "executed_by_rust_contract"
    assert [command[2] for command in seam["commands"]] == ["pull-value"]
