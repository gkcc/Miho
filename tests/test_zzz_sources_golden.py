from __future__ import annotations

import json
from pathlib import Path

from zzz_endgame_exporter.official_names import load_official_agents, load_official_bangboo
from zzz_endgame_exporter.prydwen import extract_phase_updates_from_html


FIXTURE = Path(__file__).parent / "fixtures" / "zzz_sources_minimal.json"


def test_python_oracle_for_minimal_zzz_sources(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert extract_phase_updates_from_html(fixture["phase_html"]) == {
        "3.1": {"collect_date": "2026-07-07", "users": "1234"},
        "3.2": {"collect_date": "2026-07-08", "users": ""},
    }

    raw = tmp_path / "raw"
    raw.mkdir()
    for key, filename in (
        ("agents_en", "zzz_agents_en-us.json"), ("agents_zh", "zzz_agents_zh-cn.json"),
        ("bangboo_en", "zzz_bangboo_en-us.json"), ("bangboo_zh", "zzz_bangboo_zh-cn.json"),
    ):
        (raw / filename).write_text(json.dumps(fixture[key], ensure_ascii=False), encoding="utf-8")

    warnings: list[str] = []
    agents = load_official_agents(raw, warnings)
    bangboo = load_official_bangboo(raw, warnings)
    assert warnings == []
    assert agents == [{
        "character_slug": "alice-thymefield", "character_name_en": "Alice Thymefield",
        "character_name_cn": "爱丽丝", "element_en": "Physical", "element_cn": "物理",
        "style_en": "Anomaly", "style_cn": "异常", "faction_en": "Sample",
        "faction_cn": "测试阵营", "rarity": "S", "icon_url": "zh.webp",
        "source": "HoYoWiki official zzz agent menu_id=8", "kind": "agent", "release_order": 1,
    }]
    assert bangboo == [{
        "character_slug": "ultra-jake", "character_name_en": "Ultra Jake",
        "character_name_cn": "超极杰克", "source": "HoYoWiki official zzz bangboo menu_id=15",
        "kind": "bangboo", "release_order": 1001,
    }]
