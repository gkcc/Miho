from __future__ import annotations

import json

import pytest

from miho_core.visualizer_data import (
    VISUALIZER_DATA_SCHEMA_VERSION,
    compact_visualizer_data,
    expand_visualizer_data,
)


def test_columnar_visualizer_data_round_trips_and_keeps_sparse_rows() -> None:
    original = {
        "meta": {"generatedAt": "2026-07-23"},
        "denseRows": [
            {"a": 1, "b": "one"},
            {"a": 2, "b": "two"},
            {"a": 3, "b": "three"},
            {"a": 4, "b": "four"},
        ],
        "sparseRows": [
            {"a": 1, "b": None},
            {"a": 2},
            {"a": 3, "b": None},
            {"a": 4},
        ],
    }
    encoded = compact_visualizer_data(original)
    assert encoded["schema_version"] == VISUALIZER_DATA_SCHEMA_VERSION
    assert "denseRows" in encoded["tables"]
    assert "sparseRows" in encoded["payload"]
    assert expand_visualizer_data(encoded) == original


def test_v2_encoder_keeps_an_explicit_envelope_without_dense_tables() -> None:
    original = {"meta": {"generatedAt": "2026-07-23"}, "rows": [{"a": 1}]}
    encoded = compact_visualizer_data(original)

    assert encoded == {
        "schema_version": VISUALIZER_DATA_SCHEMA_VERSION,
        "payload": original,
        "tables": {},
    }
    assert expand_visualizer_data(encoded) == original


@pytest.mark.parametrize(
    "value",
    [
        {
            "schema_version": VISUALIZER_DATA_SCHEMA_VERSION,
            "payload": {},
            "tables": {"rows": {"columns": ["a", "b"], "rows": [[1]]}},
        },
        {
            "schema_version": VISUALIZER_DATA_SCHEMA_VERSION,
            "payload": {"rows": []},
            "tables": {"rows": {"columns": ["a"], "rows": [[1]]}},
        },
    ],
)
def test_columnar_visualizer_decoder_rejects_ambiguous_envelopes(value: dict) -> None:
    with pytest.raises(ValueError):
        expand_visualizer_data(value)


def test_columnar_visualizer_data_reduces_representative_dense_wire_by_30_percent() -> None:
    original = {
        "meta": {"generatedAt": "2026-07-23"},
        "teamTemplates": [
            {
                "mode": "moc",
                "scope": f"12-{index % 2 + 1}",
                "rank": index + 1,
                "app_rate": f"{20 - index / 10:.2f}",
                "chars": [f"agent-{offset}" for offset in range(4)],
                "source_kind": "complete_deduped_evidence_pool",
            }
            for index in range(200)
        ],
    }
    legacy = json.dumps(original, ensure_ascii=False, separators=(",", ":")).encode()
    compact = json.dumps(
        compact_visualizer_data(original), ensure_ascii=False, separators=(",", ":")
    ).encode()

    assert len(compact) <= len(legacy) * 0.70
