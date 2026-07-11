import csv
import hashlib
import json
from pathlib import Path

from zzz_endgame_exporter.constants import (
    CHARACTER_USAGE_COLUMNS,
    NAME_MAP_COLUMNS,
    PHASE_COLUMNS,
    TEAM_RAW_COLUMNS,
)
from zzz_endgame_exporter.exporters import build_name_rows, dedup_teams, latest_usage


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
        text = (
            (root / name)
            .read_text(encoding="utf-8-sig")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        reader = csv.DictReader(text.splitlines())
        list(reader)
        assert reader.fieldnames == columns
        manifest.append(
            {
                "path": name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    tier = [
        "tier_snapshot_id",
        "fetched_at",
        "tier_updated_at",
        "tier_updated_date",
        "tier_mode",
        "tier_mode_cn",
        "character_slug",
        "character_name_en",
        "character_name_cn",
        "prydwen_category",
        "prydwen_role",
        "role_group",
        "role_group_cn",
        "tier",
        "rating",
        "tags",
        "marks",
        "is_new",
        "element",
        "element_cn",
        "style",
        "style_cn",
        "faction",
        "rarity",
        "icon_url",
        "source_url",
    ]
    table_columns = {
        "prydwen_tier_current.csv": tier,
        "prydwen_tier_history.csv": tier,
        "prydwen_tier_changelog.csv": [
            "changelog_date",
            "source_url",
            "character_slugs",
            "text",
        ],
        "prydwen_tier_changelog_history.csv": [
            "changelog_date",
            "source_url",
            "character_slugs",
            "text",
        ],
        "prydwen_tier_usage_trend.csv": tier
        + [
            "collect_date",
            "phase_ver",
            "phase_name",
            "app_rate",
            "avg_score",
            "quality_flag",
        ],
    }
    for name, columns in table_columns.items():
        text = (
            (root / name)
            .read_text(encoding="utf-8-sig")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode()
        assert next(csv.reader(text.splitlines())) == columns
        manifest.append(
            {
                "path": name,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    report = (root / "export_report.md").read_bytes()
    manifest.append(
        {
            "path": "export_report.md",
            "bytes": len(report),
            "sha256": hashlib.sha256(report).hexdigest(),
        }
    )
    manifest.sort(key=lambda row: row["path"])
    assert json.loads((root / "artifact_manifest.json").read_text(encoding="utf-8")) == manifest


def test_latest_usage_orders_by_mode_sub_mode_and_slug():
    rows = [
        {
            "mode": "sd",
            "sub_mode": "all",
            "phase_ver": "2",
            "character_slug": "b",
            "collect_date": "2026-02-01",
        },
        {
            "mode": "sd",
            "sub_mode": "5-1",
            "phase_ver": "1",
            "character_slug": "a",
            "collect_date": "2026-01-01",
        },
    ]
    assert [row["sub_mode"] for row in latest_usage(rows)] == ["5-1", "all"]


def test_team_dedup_uses_rank_then_app_rate_then_average_score():
    common = {
        "mode": "sd",
        "sub_mode": "all",
        "phase_ver": "1",
        "char_1_slug": "a",
        "char_2_slug": "b",
        "char_3_slug": "c",
        "bangboo_slug": "",
    }
    rows = [
        {**common, "rank": 3, "app_rate": 99, "avg_score": 99, "raw_index": 1},
        {**common, "rank": 2, "app_rate": 90, "avg_score": 1, "raw_index": 2},
    ]
    assert dedup_teams(rows)[0]["raw_index"] == 2


def test_fallback_name_rows_cover_usage_and_team_slugs():
    usage = [{"character_slug": "agent-a"}, {"character_slug": "bangboo-a"}]
    names, unresolved = build_name_rows({row["character_slug"] for row in usage}, {}, [])
    assert [row["character_slug"] for row in names] == ["agent-a", "bangboo-a"]
    assert all(row["needs_manual_check"] == "1" for row in unresolved)
