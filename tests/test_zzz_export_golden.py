import csv
import hashlib
import json
from pathlib import Path

from zzz_endgame_exporter.constants import CHARACTER_USAGE_COLUMNS, NAME_MAP_COLUMNS, PHASE_COLUMNS, TEAM_RAW_COLUMNS


def test_expected_minimal_export_has_python_contract_and_manifest():
    root = Path(__file__).parent / "fixtures" / "zzz_export_expected"
    expected = {
        "phase_index.csv": PHASE_COLUMNS,
        "character_usage_long.csv": CHARACTER_USAGE_COLUMNS,
        "team_rank_raw.csv": TEAM_RAW_COLUMNS,
        "name_map.csv": NAME_MAP_COLUMNS,
    }
    manifest = []
    for name, columns in expected.items():
        text = (root / name).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        rows = list(csv.DictReader(text.splitlines()))
        assert list(rows[0]) == columns
        manifest.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    manifest.sort(key=lambda row: row["path"])
    # artifact_manifest describes the four payload artifacts, not itself.
    assert json.loads((root / "artifact_manifest.json").read_text(encoding="utf-8")) == manifest
