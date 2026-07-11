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
        "character_usage_phase_latest.csv": CHARACTER_USAGE_COLUMNS,
        "team_rank_dedup_unordered.csv": TEAM_RAW_COLUMNS,
        "name_map_unresolved.csv": NAME_MAP_COLUMNS,
    }
    manifest = []
    for name, columns in expected.items():
        text = (root / name).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        reader = csv.DictReader(text.splitlines())
        list(reader)
        assert reader.fieldnames == columns
        manifest.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    tier = ["tier_snapshot_id","fetched_at","tier_updated_at","tier_updated_date","tier_mode","tier_mode_cn","character_slug","character_name_en","character_name_cn","prydwen_category","prydwen_role","role_group","role_group_cn","tier","rating","tags","marks","is_new","element","element_cn","style","style_cn","faction","rarity","icon_url","source_url"]
    for name, columns in {"prydwen_tier_current.csv":tier,"prydwen_tier_history.csv":tier,"prydwen_tier_changelog.csv":["changelog_date","source_url","character_slugs","text"],"prydwen_tier_changelog_history.csv":["changelog_date","source_url","character_slugs","text"],"prydwen_tier_usage_trend.csv":tier+["collect_date","phase_ver","phase_name","app_rate","avg_score","quality_flag"]}.items():
        text=(root/name).read_text(encoding="utf-8-sig").replace("\r\n","\n").replace("\r","\n"); raw=b"\xef\xbb\xbf"+text.replace("\n","\r\n").encode(); assert next(csv.reader(text.splitlines()))==columns; manifest.append({"path":name,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
    report=(root/"export_report.md").read_bytes(); manifest.append({"path":"export_report.md","bytes":len(report),"sha256":hashlib.sha256(report).hexdigest()})
    manifest.sort(key=lambda row: row["path"])
    # artifact_manifest describes the four payload artifacts, not itself.
    assert json.loads((root / "artifact_manifest.json").read_text(encoding="utf-8")) == manifest
