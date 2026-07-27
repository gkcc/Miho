from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from miho_core.pull_value import build_pull_value_cards, format_gpt_review_packet
import zzz_endgame_exporter.cli as zzz_cli


FIXTURE = Path(__file__).parent / "fixtures" / "review_packet_v1_contract"
EXPECTED = FIXTURE / "expected"
FIXED_CLOCK = datetime(2026, 7, 13, 9, 10, 11)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 13, 9, 10, 11)
        return value if tz is None else value.astimezone(tz)


def _contract() -> dict[str, Any]:
    return json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))


def _shared_input() -> Path:
    return (FIXTURE / _contract()["shared_input_reference"]).resolve()


def _copy_real_inputs(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "review packet V1 中文 空格"
    shutil.copytree(_shared_input(), runtime_root / "input")
    shutil.copy2(
        FIXTURE / "input_overrides" / "mechanism_notes" / "alpha.json",
        runtime_root / "input" / "mechanism_notes" / "alpha.json",
    )
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


def _normalize(text: str, runtime_root: Path) -> str:
    root = str(runtime_root)
    return text.replace(root.replace("\\", "\\\\"), "<ROOT>").replace(root, "<ROOT>")


def _packet(runtime_root: Path, status: str) -> str:
    return _normalize(format_gpt_review_packet(_build(runtime_root, status)), runtime_root)


def _payload(packet: str) -> dict[str, Any]:
    prefix = "## Evidence Payload\n\n```json\n"
    assert packet.count(prefix) == 1
    payload_text, separator, _rest = packet.partition(prefix)[2].partition("\n```\n")
    assert separator == "\n```\n"
    return json.loads(payload_text)


@pytest.mark.parametrize("status", ["current", "next"])
def test_python_core_matches_review_packet_v1_markdown_golden(tmp_path: Path, status: str) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    assert _packet(runtime_root, status) == (
        EXPECTED / f"{status}_gpt_pull_reviewer_packet.md"
    ).read_text(encoding="utf-8")


def test_dense_packet_oracle_freezes_current_next_trace_and_decision_semantics(tmp_path: Path) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    current = _payload(_packet(runtime_root, "current"))
    next_payload = _payload(_packet(runtime_root, "next"))
    current_cards = {card["slug"]: card for card in current["candidates"]}
    next_cards = {card["slug"]: card for card in next_payload["candidates"]}

    assert current["summary"]["generated_at"] == "2026-07-13T09:10:11"
    assert current["summary"]["method_version"] == "evidence-first-v1-20260712"
    assert list(current_cards) == ["alpha", "beta", "gamma", "nova"]
    assert list(next_cards) == ["delta", "epsilon", "zeta"]
    assert current["summary"]["filtered_low_rarity_slugs"] == ["low-a"]

    alpha = current_cards["alpha"]
    assert alpha["local_rule_pull_value"] == "高"
    assert alpha["prior_final_stage"] == "1+1"
    assert alpha["local_rule_stage"] == "0+0"
    assert alpha["final_stage"] == "1+1"
    assert alpha["stage_delta"] == "0+0 -> 1+1"
    assert alpha["delta_requires_review"] is True
    assert alpha["change_allowed_reason"] == "only_with_new_evidence"

    nova = current_cards["nova"]
    assert nova["candidate_type"] == "new"
    assert nova["local_rule_pull_value"] == "等实测"
    assert nova["final_stage"] == "0+1"
    assert nova["delta_requires_review"] is True
    assert nova["change_allowed_reason"] == "wait_for_repeated_data"
    assert nova["history_summary"] == "暂无全局 usage 出场点；完整真实队伍表已有首轮实测（1 snapshot）"
    assert nova["team_coverage_summary"] == "current 0(0)；target 0(0)；新增依赖 0(0)"
    assert nova["stage_recommendation"]["recommended_stage"] == "等实测"
    assert nova["decision_basis"][0] == (
        "新角色首轮实测已到：1 个 snapshot，当前仅单期/B- 证据；等待跨期复测，不自动提升推荐档位"
    )
    assert nova["risk_notes"][0] == "首轮数据不能替代跨期稳定性验证；SD/DA 同 snapshot 只计一次"
    assert nova["evidence_ids"] == []
    assert nova["risk_evidence_ids"] == []

    delta = next_cards["delta"]
    assert [ref["confidence"] for ref in delta["evidence_refs"]] == ["B", "B"]
    epsilon = next_cards["epsilon"]
    assert [(ref["confidence"], ref["plan_dependency"]) for ref in epsilon["evidence_refs"]] == [
        ("B", ["epsilon"]),
    ]
    assert [
        (ref["confidence"], ref["plan_dependency"]) for ref in epsilon["risk_evidence_refs"]
    ] == [("B+", ["epsilon", "zeta"])]
    assert any("conditional risk" in note for note in epsilon["risk_notes"])
    assert next_cards["zeta"]["evidence_ids"] == []
    assert next_cards["zeta"]["risk_evidence_refs"][0]["plan_dependency"] == ["epsilon", "zeta"]

    refs = [
        ref
        for payload in (current, next_payload)
        for card in payload["candidates"]
        for ref in [*card["evidence_refs"], *card["risk_evidence_refs"]]
    ]
    by_key = {ref["evidence_key"]: ref for ref in refs}
    stable_ids = _contract()["stable_evidence_ids"]
    assert {key: by_key[key]["evidence_id"] for key in stable_ids} == stable_ids
    assert all(ref["mode"] == "sd" for ref in refs)
    assert all(ref["phase_versions"] and ref["scopes"] and ref["observation_keys"] for ref in refs)


def test_python_cli_default_dual_packet_matches_golden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = _copy_real_inputs(tmp_path)
    root = runtime_root / "input"
    data = root / "data"
    monkeypatch.setattr(zzz_cli, "datetime", _FixedDateTime)

    assert zzz_cli.main(
        [
            "review-packet",
            "--box", str(root / "box.json"),
            "--out", str(data),
            "--plan", str(root / "plan.json"),
            "--mechanism-notes-dir", str(root / "mechanism_notes"),
            "--decision-baseline", str(root / "baseline.json"),
        ]
    ) == 0

    assert not (data / "gpt_pull_reviewer_packet.md").exists()
    for status in ("current", "next"):
        actual = _normalize(
            (data / f"{status}_gpt_pull_reviewer_packet.md").read_text(encoding="utf-8"),
            runtime_root,
        )
        expected = (EXPECTED / f"{status}_gpt_pull_reviewer_packet.md").read_text(encoding="utf-8")
        assert actual == expected


def test_contract_freezes_payload_schema_fences_hashes_and_rust_seam(tmp_path: Path) -> None:
    contract = _contract()
    runtime_root = _copy_real_inputs(tmp_path)
    fixture_files = sorted(
        path.relative_to(FIXTURE).as_posix()
        for path in (FIXTURE / "input_overrides").rglob("*")
        if path.is_file()
    )
    output_files = sorted(path.name for path in EXPECTED.iterdir() if path.is_file())
    assert fixture_files == contract["fixture_files"]
    assert output_files == contract["output_files"]
    assert _shared_input().is_dir()
    assert contract["normalizations"] == ["temporary_root"]
    assert contract["fixed_local_clock"] == FIXED_CLOCK.isoformat(timespec="seconds")

    schema = contract["schemas"]["evidence_payload"]
    for status in ("current", "next"):
        canonical = (EXPECTED / f"{status}_gpt_pull_reviewer_packet.md").read_text(encoding="utf-8")
        actual = _packet(runtime_root, status)
        payload = _payload(canonical)
        assert list(payload) == schema["top_level_fields"]
        assert list(payload["summary"]) == schema["summary_fields"]
        assert all(list(card) == schema["candidate_fields"] for card in payload["candidates"])
        assert all(
            list(card["stage_recommendation"]) == schema["stage_recommendation_fields"]
            for card in payload["candidates"]
        )
        for card in payload["candidates"]:
            for ref in [*card["evidence_refs"], *card["risk_evidence_refs"]]:
                assert list(ref) == schema["evidence_ref_fields"]

        markdown_schema = contract["schemas"]["markdown"]
        assert canonical.startswith(markdown_schema["title"] + "\n")
        assert [line for line in canonical.splitlines() if line.startswith("## ")] == markdown_schema[
            "section_headings"
        ]
        assert canonical.count("```json") == 1
        assert canonical.count("\n```\n") == 1
        assert _payload(actual) == payload
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert digest == contract["normalized_sha256"][f"{status}_gpt_pull_reviewer_packet.md"]

    current_text = (EXPECTED / "current_gpt_pull_reviewer_packet.md").read_text(encoding="utf-8")
    current_payload = _payload(current_text)
    alpha = next(card for card in current_payload["candidates"] if card["slug"] == "alpha")
    danger = contract["dangerous_text_contract"]
    assert danger["python_fixture_excluded_literal"] not in json.dumps(alpha, ensure_ascii=False)
    assert danger["rust_dynamic_fence_policy"] == "max(3, longest_payload_backtick_run + 1)"
    assert "</script>" in current_text
    assert "| Markdown pipe\\n第二行" in current_text
    assert alpha["mechanism_notes"]["stage_reason"] == (
        "危险文本 </script> | Markdown pipe\n第二行仍在 JSON 字符串内"
    )
    assert alpha["mechanism_notes"]["risks_and_counterevidence"][1] == (
        "跨行风险第一行\n跨行风险第二行"
    )

    seam = contract["rust_command_comparison_seam"]
    assert seam["status"] == "executed_by_rust_contract"
    assert [command[2] for command in seam["commands"]] == ["review-packet"]
    assert seam["expected_outputs"] == [
        "<ROOT>/input/data/current_gpt_pull_reviewer_packet.md",
        "<ROOT>/input/data/next_gpt_pull_reviewer_packet.md",
    ]
