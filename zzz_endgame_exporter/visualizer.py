from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id

from .constants import ELEMENT_CN, MODE_CN, ROLE_ORDER, STYLE_CN


def write_visualizer_app(
    out_dir: Path,
    *,
    usage_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    team_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
    changelog_rows: list[dict[str, Any]],
) -> None:
    visualizer_dir = out_dir / "visualizer"
    visualizer_dir.mkdir(parents=True, exist_ok=True)
    roster_rows = _build_roster(usage_rows, tier_rows, name_rows)
    team_templates = _build_team_templates(team_rows, roster_rows, name_rows)
    phase_info_rows = _build_phase_info_rows(out_dir)
    data = {
        "meta": {
            "game": "绝区零",
            "generatedAt": _latest(tier_rows, "fetched_at"),
            "tierUpdatedAt": _latest(tier_rows, "tier_updated_at"),
            "source": "ShiyuDataProcessed + Prydwen ZZZ + HoYoWiki",
        },
        "usageRows": usage_rows,
        "tierRows": tier_rows,
        "teamTemplates": team_templates,
        "rosterRows": roster_rows,
        "nameRows": name_rows,
        "phaseInfoRows": phase_info_rows,
        "changelogRows": changelog_rows[:80],
    }
    (visualizer_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (visualizer_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (visualizer_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (visualizer_dir / "app.js").write_text(APP_JS, encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _build_phase_info_rows(out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(out_dir / "phase_index.csv"):
        mode = str(row.get("mode") or "")
        mode_cn = str(row.get("mode_cn") or MODE_CN.get(mode, mode))
        phase_ver = str(row.get("phase_ver") or "")
        start = str(row.get("start_date") or "")
        end = str(row.get("end_date") or "")
        rows.append(
            {
                "snapshot_id": row.get("snapshot_id", ""),
                "collect_date": row.get("collect_date", ""),
                "mode": mode,
                "mode_cn": mode_cn,
                "phase_ver": phase_ver,
                "phase_name": row.get("phase_name", "") or f"{mode_cn} {phase_ver}".strip(),
                "phase_name_cn": row.get("phase_name", "") or f"{mode_cn} {phase_ver}".strip(),
                "start_date": start,
                "end_date": end,
                "mechanic_name": "当期数据",
                "mechanic_text": f"采样日期 {row.get('collect_date') or '未知'}；周期 {start or '未知'} 至 {end or '未知'}。推荐只使用同模式、同关卡的当前最新队伍模板。",
                "mechanic_source": "ShiyuDataProcessed config.json",
                "mechanic_url": "",
            }
        )
    return rows


def _build_roster(
    usage_rows: list[dict[str, Any]],
    tier_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {normalize_character_id(row.get("character_slug")): row for row in name_rows}
    tier_meta: dict[str, dict[str, Any]] = {}
    for row in tier_rows:
        slug = normalize_character_id(row.get("character_slug"))
        if not slug:
            continue
        current = tier_meta.get(slug)
        if current is None or _tier_rank(row.get("tier")) < _tier_rank(current.get("tier")):
            tier_meta[slug] = row
    usage_meta: dict[str, dict[str, Any]] = {}
    for row in usage_rows:
        slug = normalize_character_id(row.get("character_slug"))
        if slug and row.get("sub_mode") == "all":
            usage_meta.setdefault(slug, row)
    slugs = sorted(set(tier_meta) | set(usage_meta))
    rows: list[dict[str, Any]] = []
    for index, slug in enumerate(slugs):
        tier = tier_meta.get(slug, {})
        name = names.get(slug, {})
        usage = usage_meta.get(slug, {})
        element = tier.get("element") or usage.get("element") or ""
        style = tier.get("style") or ""
        role_group = tier.get("role_group") or _role_from_style(style)
        rows.append(
            {
                "character_slug": slug,
                "character_name_en": name.get("character_name_en") or tier.get("character_name_en") or usage.get("character_name_en") or slug,
                "character_name_cn": name.get("character_name_cn") or "",
                "element_en": element,
                "element_cn": tier.get("element_cn") or ELEMENT_CN.get(str(element), ""),
                "style_en": style,
                "style_cn": tier.get("style_cn") or STYLE_CN.get(str(style), ""),
                "role_group": role_group,
                "role_group_cn": tier.get("role_group_cn") or _role_cn(role_group),
                "rarity": tier.get("rarity") or usage.get("rarity") or "",
                "tier": tier.get("tier") or "未分档",
                "rating": tier.get("rating") or "",
                "tags": tier.get("tags") or "",
                "icon_url": tier.get("icon_url") or "",
                "release_order": _num(name.get("release_order")) if name.get("release_order") not in {"", None} else 9999 + index,
            }
        )
    return sorted(rows, key=lambda r: (_release_order_value(r.get("release_order")), str(r.get("character_slug"))))


def _build_team_templates(
    team_rows: list[dict[str, Any]],
    roster_rows: list[dict[str, Any]],
    name_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {row["character_slug"]: row for row in roster_rows}
    name_map = {normalize_character_id(row.get("character_slug")): row for row in name_rows}
    latest: dict[str, str] = {}
    for row in team_rows:
        mode = str(row.get("mode") or "")
        collect_date = str(row.get("collect_date") or "")
        if mode and collect_date >= latest.get(mode, ""):
            latest[mode] = collect_date
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in team_rows:
        mode = str(row.get("mode") or "")
        if not mode or str(row.get("collect_date") or "") != latest.get(mode, ""):
            continue
        chars = [normalize_character_id(row.get(f"char_{i}_slug")) for i in range(1, 4)]
        if any(not c for c in chars):
            continue
        key = "|".join([mode, str(row.get("sub_mode") or ""), ">".join(sorted(chars))])
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "mode": mode,
                "mode_cn": row.get("mode_cn") or MODE_CN.get(mode, mode),
                "scope_key": row.get("sub_mode") or "all",
                "scope_label": row.get("sub_mode_cn") or row.get("sub_mode") or "全部",
                "collect_date": row.get("collect_date", ""),
                "phase_ver": row.get("phase_ver", ""),
                "phase_name": row.get("phase_name", ""),
                "rank": _num(row.get("rank")),
                "app_rate": _num(row.get("app_rate")),
                "avg_score": _num(row.get("avg_score")),
                "bangboo": row.get("bangboo_slug", ""),
                "bangboo_name": row.get("bangboo_name_cn") or name_map.get(normalize_character_id(row.get("bangboo_slug")), {}).get("character_name_cn", ""),
                "source_kind": row.get("source_kind", ""),
                "source_file": row.get("source_file", ""),
                "chars": chars,
                "names_cn": [names.get(char, {}).get("character_name_cn") or names.get(char, {}).get("character_name_en") or char for char in chars],
            }
        )
    return sorted(output, key=lambda r: (str(r["mode"]), str(r["scope_key"]), _num(r.get("rank")) or 9999))[:20000]


def _latest(rows: list[dict[str, Any]], key: str) -> str:
    values = [str(row.get(key, "")) for row in rows if row.get(key)]
    return max(values) if values else ""


def _tier_rank(tier: Any) -> float:
    return {"T0": 0, "T0.5": 0.5, "T1": 1, "T1.5": 1.5, "T2": 2, "T3": 3, "T4": 4, "T5": 5}.get(str(tier), 99)


def _role_from_style(style: str) -> str:
    if style in {"Attack", "Rupture"}:
        return "crit_dps"
    if style == "Anomaly":
        return "anomaly_dps"
    if style in {"Support", "Stun", "Defence", "Defense"}:
        return "support"
    return "unknown"


def _role_cn(role: str) -> str:
    return {"crit_dps": "直伤主C", "anomaly_dps": "异常主C", "support": "辅助", "unknown": "未分类"}.get(role, "未分类")


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _release_order_value(value: Any) -> float:
    number = _num(value)
    return number if number is not None else 9999.0


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ZZZ 高难与本地 Box 可视化</title>
  <link rel="stylesheet" href="./styles.css" />
</head>
<body>
<main class="app">
  <header class="topbar">
    <div><h1>绝区零高难可视化</h1><p id="metaLine"></p></div>
    <nav id="tabs" class="tabs"></nav>
  </header>

  <section id="analysisView">
    <section class="controls">
      <label>模式<div id="modeControl" class="segmented"></div></label>
      <label>职能<div id="roleControl" class="segmented"></div></label>
      <label>视图<div id="viewControl" class="segmented"></div></label>
      <label>数量<select id="limitSelect"><option value="10">Top 10</option><option value="16" selected>Top 16</option><option value="30">Top 30</option></select></label>
      <label>搜索<input id="searchInput" type="search" placeholder="中文名 / 英文名 / slug" /></label>
    </section>
    <section class="analysis-layout">
      <section class="panel chart-panel"><div class="panel-head"><div><h2 id="chartTitle">趋势</h2><p id="chartSubtitle"></p></div><div id="badges" class="badges"></div></div><svg id="chart"></svg><div id="tooltip" class="tooltip" hidden></div></section>
      <aside class="panel side-panel">
        <div class="side-section characters"><h3>角色数据</h3><div id="characterList" class="character-list"></div></div>
        <div class="side-section changelog"><h3>Changelog</h3><div id="changelogList" class="changelog-list"></div></div>
      </aside>
    </section>
  </section>

  <section id="boxView" class="hidden">
    <section class="controls">
      <label>属性<div id="boxElementControl" class="segmented"></div></label>
      <label>特性<div id="boxStyleControl" class="segmented"></div></label>
      <label>状态<select id="boxOwnedSelect"><option value="all">全部</option><option value="owned">已拥有</option><option value="missing">未拥有</option></select></label>
      <label>搜索<input id="boxSearchInput" type="search" placeholder="中文名 / 英文名 / slug" /></label>
      <div class="actions"><button id="boxExportBtn">导出Box</button><button id="boxImportBtn">导入</button><button id="boxMarkVisibleBtn">筛选设为已拥有</button><button id="boxBuildVisibleBtn">筛选设为练满</button><button id="boxClearBuildVisibleBtn">清筛选练度</button><input id="boxImportInput" type="file" accept="application/json,.json" hidden /></div>
    </section>
    <section id="buildEditor" class="build hidden"><img id="buildIcon" alt=""><div><h2 id="buildTitle">练度</h2><p id="buildSubtitle"></p></div><label>等级<select id="buildLevel"></select></label><label>音擎<select id="buildEngine"></select></label><label>技能<select id="buildSkill"></select></label><label>驱动盘<select id="buildDisc"></select></label><span id="buildScore"></span><button id="buildMaxBtn">设为练满</button><button id="buildClearBtn">清空练度</button></section>
    <section class="panel"><div class="panel-head"><div><h2>我的 Box</h2><p id="boxSubtitle"></p></div><div id="boxBadges" class="badges"></div></div><div id="boxGrid" class="box-grid"></div><div id="boxTooltip" class="tooltip" hidden></div></section>
  </section>

  <section id="recommenderView" class="hidden">
    <section class="controls rec-controls">
      <label>模式<div id="recModeControl" class="segmented"></div></label>
      <label>关卡<select id="recScopeSelect"></select></label>
      <label>推荐属性<div id="recElementControl" class="segmented"></div></label>
      <label>缺口<select id="recGapSelect"><option value="0">只看可成队</option><option value="1" selected>最多缺1人</option><option value="3">显示全部</option></select></label>
      <label>风险<select id="recRiskSelect"><option value="warn" selected>仅提醒</option><option value="filter">过滤风险</option><option value="off">忽略风险</option></select></label>
      <label>数量<select id="recLimitSelect"><option value="8" selected>Top 8</option><option value="12">Top 12</option><option value="20">Top 20</option></select></label>
      <label>搜索<input id="recSearchInput" type="search" placeholder="角色 / 队伍 / 邦布" /></label>
    </section>
    <section id="phaseMechanics" class="phase-mechanics"><div><h2 id="phaseTitle">当期数据</h2><p id="phaseDates"></p></div><p id="phaseText"></p></section>
    <section class="rec-layout">
      <section class="panel"><div class="panel-head"><div><h2 id="recTitle">组队推荐</h2><p id="recSubtitle"></p></div><div id="recBadges" class="badges"></div></div><div id="recList" class="rec-list"></div></section>
      <aside class="panel rec-slate"><div class="panel-head"><div><h2>多队方案</h2><p id="recSlateSubtitle"></p></div></div><div id="recSlateList" class="rec-slate-list"></div></aside>
    </section>
    <div id="recTooltip" class="tooltip" hidden></div>
  </section>
</main>
<script src="./app.js"></script>
</body>
</html>
"""


STYLES_CSS = """*{box-sizing:border-box}body{margin:0;background:#f4f7f8;color:#172126;font-family:Inter,Segoe UI,Arial,'Microsoft YaHei',sans-serif}.hidden{display:none!important}.app{padding:18px 20px 26px}.topbar{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}.topbar h1{margin:0 0 5px;font-size:24px}.topbar p,.panel-head p{margin:0;color:#64757d;font-size:12px}.tabs,.segmented,.badges,.actions{display:flex;gap:6px;flex-wrap:wrap}.tabs button,.segmented button,.actions button,.build button{border:1px solid #c6d2d7;background:white;color:#1d3942;border-radius:6px;padding:7px 10px;cursor:pointer}.tabs button.active,.segmented button.active{background:#174c5a;color:white;border-color:#174c5a}.controls{display:grid;grid-template-columns:1fr 1fr 1fr .55fr 1.2fr;gap:10px;align-items:end;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.controls label{display:block;color:#607079;font-size:12px}.controls input,.controls select,.build select{width:100%;height:34px;border:1px solid #c8d4d9;border-radius:6px;background:white;padding:6px 8px;margin-top:5px}.panel{background:white;border:1px solid #d8e1e5;border-radius:8px;min-height:650px}.panel-head{display:flex;justify-content:space-between;gap:12px;padding:14px 16px 10px;border-bottom:1px solid #edf1f3}.panel-head h2,.build h2{margin:0 0 4px;font-size:18px}.badges span{border:1px solid #d6e1e5;background:#f8fafb;border-radius:999px;padding:4px 8px;color:#39505a;font-size:11px;font-weight:650}.analysis-layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:14px}.chart-panel{min-width:0}.side-panel{padding:12px;display:flex;flex-direction:column;gap:12px;max-height:722px;overflow:hidden}.side-section{min-height:0;display:flex;flex-direction:column}.side-section.characters{flex:1 1 auto}.side-section.changelog{flex:0 0 245px}.side-section h3{margin:0 0 8px;font-size:15px}.character-list,.changelog-list{overflow:auto;display:flex;flex-direction:column;gap:7px;padding-right:4px}.character-card{border:1px solid #d8e1e5;background:#fbfcfd;border-radius:7px;padding:8px;display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:8px;align-items:center;cursor:pointer;text-align:left}.character-card:hover{border-color:#86a6af;background:#f4f9fa}.character-card img{width:38px;height:38px;border-radius:50%;background:#e7ecef;object-fit:cover}.character-card .name{font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.character-card .meta{color:#6b7c84;font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.character-card .rate{font-size:13px;font-weight:800;color:#174c5a;text-align:right}.changelog-item{border-left:3px solid #8aa3ad;background:#f8fafb;border-radius:5px;padding:8px 9px}.changelog-item time{font-weight:700;font-size:12px;color:#174c5a}.changelog-item p{margin:4px 0 0;color:#405158;font-size:12px;line-height:1.45}#chart{width:100%;height:620px;display:block}.axis{fill:#546870;font-size:11px}.grid{stroke:#e7ecef}.line{fill:none;stroke-width:2.2}.bar{stroke-width:10;stroke-linecap:round}.avatar,.box-card img,.rec-member img{border-radius:50%;background:#e7ecef;object-fit:cover}.avatar-ring{stroke:white;stroke-width:2;filter:drop-shadow(0 1px 2px rgba(0,0,0,.24));pointer-events:none}.tooltip{position:fixed;z-index:20;width:320px;background:#101820;color:white;border-radius:8px;padding:12px;box-shadow:0 16px 36px rgba(0,0,0,.24);pointer-events:none}.tooltip b{color:#9fb7c0}.tooltip-grid{display:grid;grid-template-columns:84px 1fr;gap:5px 8px;font-size:12px}.heat-cell{rx:4;ry:4;stroke:#fff;stroke-width:1}.heat-name{fill:#263a43;font-size:12px;font-weight:650}.box-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:10px;padding:14px}.box-card{position:relative;border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;min-height:150px;padding:10px 8px;text-align:center;cursor:pointer}.box-card.owned{border-color:#2f7b69;background:#f3fbf7}.box-card.missing img{filter:grayscale(1);opacity:.38}.box-card.selected{outline:2px solid #174c5a;outline-offset:2px}.box-card img{width:64px;height:64px}.box-card .name{font-size:12px;font-weight:700;line-height:1.25;min-height:31px;display:flex;align-items:center;justify-content:center}.box-card .meta{font-size:11px;color:#64777f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.build-btn{position:absolute;left:7px;top:7px;font-size:11px;border:1px solid #c6d2d7;background:white;border-radius:6px;padding:3px 6px}.build{display:grid;grid-template-columns:46px minmax(150px,.8fr) repeat(4,minmax(80px,1fr)) auto auto auto;gap:10px;align-items:center;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px;margin-bottom:14px}.build img{width:46px;height:46px;border-radius:50%}.build label{font-size:12px;color:#607079}.rec-controls{grid-template-columns:1fr .62fr 1.2fr .55fr .55fr .5fr 1fr}.phase-mechanics{display:grid;grid-template-columns:minmax(220px,.62fr) minmax(0,1fr);gap:14px;align-items:center;background:white;border:1px solid #d8e1e5;border-radius:8px;padding:12px 14px;margin-bottom:14px}.phase-mechanics h2{margin:0 0 4px;font-size:16px}.phase-mechanics p{margin:0;color:#42565f;font-size:12px;line-height:1.5}.rec-layout{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:14px}.rec-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:12px;padding:14px}.rec-card{border:1px solid #d8e1e5;background:#fbfcfd;border-radius:8px;padding:12px}.rec-card.risky,.rec-slate-card.risky{border-color:#d09b3d;background:#fffaf1}.rec-head{display:flex;justify-content:space-between;gap:10px}.rec-head h3{margin:0;font-size:15px}.score{text-align:right;color:#174c5a;font-weight:800}.rec-team{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0}.rec-member{border:1px solid #d8e1e5;border-radius:7px;background:white;text-align:center;padding:8px 6px;min-width:0}.rec-member.owned{border-color:#2f7b69;background:#f3fbf7}.rec-member.missing{border-color:#d1a24c;background:#fffaf1}.rec-member.risky{box-shadow:inset 0 0 0 1px #c88724}.rec-member img{width:46px;height:46px}.rec-member .name{font-size:11px;font-weight:700;line-height:1.2;min-height:26px}.rec-member .meta,.rec-meta,.risk-note{font-size:12px;color:#657780}.tags{display:flex;gap:6px;flex-wrap:wrap}.tags span{border:1px solid #d6e1e5;background:white;border-radius:999px;padding:3px 7px;color:#39505a;font-size:11px}.tags .warn{border-color:#dfb86a;background:#fff8e8;color:#7a5200}.tags .danger{border-color:#cb7a33;background:#fff1e6;color:#7a3300}.risk-note{margin-top:8px;border:1px solid #e4bd72;background:#fff8e8;border-radius:6px;padding:7px 8px;color:#724d00}.rec-slate{min-height:650px}.rec-slate-list{padding:14px;display:flex;flex-direction:column;gap:10px}.rec-slate-card{border:1px solid #d8e1e5;border-radius:8px;background:#fbfcfd;padding:10px}.rec-slate-card h3{margin:0 0 8px;font-size:14px}.rec-slate-team{display:flex;gap:6px;flex-wrap:wrap}.rec-slate-team img{width:34px;height:34px;border-radius:50%;background:#e7ecef}.rec-slate-team img.missing{filter:grayscale(1);opacity:.38}.rec-slate-team img.risky{outline:2px solid #c88724}.empty{padding:28px;text-align:center;color:#657780}@media(max-width:1100px){.controls,.rec-controls,.build{grid-template-columns:1fr 1fr}.panel-head{flex-direction:column}.analysis-layout,.rec-layout,.phase-mechanics{grid-template-columns:1fr}.side-panel{max-height:none}.side-section.changelog{flex-basis:auto}}@media(max-width:720px){.app{padding:14px 12px}.topbar{flex-direction:column}.rec-list{grid-template-columns:1fr}.box-grid{grid-template-columns:repeat(auto-fill,minmax(92px,1fr))}}"""


APP_JS = r"""const MODES=[['sd','式舆防卫'],['da','危局强袭']];
const ROLES=[['all','全部'],['crit_dps','直伤主C'],['anomaly_dps','异常主C'],['support','辅助'],['unknown','未分类']];
const VIEWS=[['trend','趋势'],['latest','排行'],['heatmap','热力']];
const ELEMENTS=['物理','火','冰','电','以太','风','玄墨'];
const STYLES=['强攻','异常','击破','支援','防护','命破'];
const TIER_RANK={'T0':0,'T0.5':.5,'T1':1,'T1.5':1.5,'T2':2,'T3':3,'T4':4,'T5':5,'未分档':9};
const BUILD_LEVELS=[0,20,40,50,55,60], BUILD_SKILLS=[['unset','未录入',0],['low','低',.35],['mid','中',.6],['high','高',.84],['max','满',1]], BUILD_DISCS=[['unset','未录入',0],['none','未刷',.12],['ok','可用',.58],['good','成型',.84],['great','毕业',1]];
const BOX_KEY='zzz_endgame_box_v1', REC_KEY='zzz_endgame_rec_v1';
let DATA=null,state={page:'analysis',mode:'sd',role:'all',view:'trend',limit:'16',search:''},box={owned:new Set(),builds:{},buildSlug:'',element:'all',style:'all',status:'all',search:''},rec={mode:'sd',scope:'',elements:{},gap:'1',riskMode:'warn',limit:'8',search:''};
const $=id=>document.getElementById(id), num=v=>{const n=Number(v);return Number.isFinite(n)?n:null}, esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])), pct=v=>num(v)==null?'-':`${num(v).toFixed(2)}%`;
fetch('./data.json').then(r=>r.json()).then(d=>{DATA=d;loadBox();loadRec();init();render();}).catch(e=>document.body.innerHTML=`<main class="app"><h1>数据加载失败</h1><p>${esc(e.message)}</p></main>`);
function init(){ $('metaLine').textContent=`Prydwen更新：${DATA.meta.tierUpdatedAt||'未知'} · 本地生成：${DATA.meta.generatedAt||'未知'}`; buttons('tabs',[['analysis','趋势分析'],['box','我的Box'],['recommender','组队推荐']],state.page,v=>{state.page=v;render();}); buttons('modeControl',MODES,state.mode,v=>{state.mode=v;render();}); buttons('roleControl',ROLES,state.role,v=>{state.role=v;render();}); buttons('viewControl',VIEWS,state.view,v=>{state.view=v;render();}); $('limitSelect').onchange=e=>{state.limit=e.target.value;renderAnalysis();}; $('searchInput').oninput=e=>{state.search=e.target.value.trim().toLowerCase();renderAnalysis();}; initBox(); initRec();}
function buttons(id,items,current,onClick){const el=$(id); el.innerHTML=''; items.forEach(([v,l])=>{const b=document.createElement('button');b.type='button';b.textContent=l;b.dataset.value=v;b.className=v===current?'active':'';b.onclick=()=>{[...el.children].forEach(x=>x.classList.remove('active'));b.classList.add('active');onClick(v);};el.appendChild(b);});}
function render(){ $('analysisView').classList.toggle('hidden',state.page!=='analysis');$('boxView').classList.toggle('hidden',state.page!=='box');$('recommenderView').classList.toggle('hidden',state.page!=='recommender');[...$('tabs').children].forEach(b=>b.classList.toggle('active',b.dataset.value===state.page)); if(state.page==='box')renderBox();else if(state.page==='recommender')renderRec();else renderAnalysis();}
function charInfo(slug){return (DATA.rosterRows||[]).find(r=>r.character_slug===slug)||{character_slug:slug,character_name_cn:'',character_name_en:slug,element_cn:'',style_cn:'',role_group:'unknown',role_group_cn:'未分类',tier:'未分档',icon_url:''};}
function charName(slug){const r=charInfo(slug);return r.character_name_cn||r.character_name_en||slug}
function bangbooName(slug, fallback=''){const r=(DATA.nameRows||[]).find(x=>x.character_slug===slug);return fallback||r?.character_name_cn||r?.character_name_en||slug||'-'}
function filteredUsage(){const q=state.search; return (DATA.usageRows||[]).filter(r=>r.mode===state.mode&&r.sub_mode==='all'&&(state.role==='all'||(charInfo(r.character_slug).role_group===state.role))&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,charInfo(r.character_slug).element_cn,charInfo(r.character_slug).style_cn].some(x=>String(x||'').toLowerCase().includes(q))));}
function seriesRows(){const map=new Map();filteredUsage().forEach(r=>{if(!map.has(r.character_slug))map.set(r.character_slug,[]);map.get(r.character_slug).push(r);});return [...map.entries()].map(([slug,rows])=>{rows.sort((a,b)=>String(a.collect_date).localeCompare(String(b.collect_date)));return{slug,rows,latest:rows[rows.length-1]};}).sort((a,b)=>(num(b.latest.app_rate)||0)-(num(a.latest.app_rate)||0)).slice(0,Number(state.limit)||16);}
function renderAnalysis(){const series=seriesRows();$('chartTitle').textContent=`${MODES.find(x=>x[0]===state.mode)?.[1]} · ${ROLES.find(x=>x[0]===state.role)?.[1]} · ${VIEWS.find(x=>x[0]===state.view)?.[1]}`;$('chartSubtitle').textContent=`展示 ${series.length} 个代理人，指标为出场率 / 平均分`; $('badges').innerHTML=[`角色 ${DATA.rosterRows.length}`,`样本点 ${filteredUsage().length}`].map(x=>`<span>${x}</span>`).join(''); state.view==='latest'?drawBars(series):state.view==='heatmap'?drawHeatmap(series):drawLines(series);renderCharacterList(series);renderChangelog(series);}
function chartBox(){const svg=$('chart');svg.innerHTML='';const rect=svg.getBoundingClientRect();const w=Math.max(760,rect.width||1000),h=620;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);return{svg,w,h};}
function add(svg,tag,attrs){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));svg.appendChild(n);return n;}
function drawLines(series){const {svg,w,h}=chartBox();if(!series.length){add(svg,'text',{x:40,y:60,class:'axis'}).textContent='暂无数据';return;}const defs=add(svg,'defs',{});const dates=[...new Set(series.flatMap(s=>s.rows.map(r=>r.collect_date)))].sort();const max=Math.max(1,...series.flatMap(s=>s.rows.map(r=>num(r.app_rate)||0)));const m={l:70,r:44,t:42,b:60},cw=w-m.l-m.r,ch=h-m.t-m.b;const x=d=>m.l+(dates.indexOf(d)/Math.max(1,dates.length-1))*cw,y=v=>m.t+ch-(v/max)*ch;for(let i=0;i<=5;i++){const yy=m.t+ch*i/5;add(svg,'line',{x1:m.l,y1:yy,x2:m.l+cw,y2:yy,class:'grid'});add(svg,'text',{x:m.l-8,y:yy+4,'text-anchor':'end',class:'axis'}).textContent=(max*(1-i/5)).toFixed(0);}dates.forEach((d,i)=>{if(dates.length>12&&i%2)return;add(svg,'text',{x:x(d),y:m.t+ch+24,'text-anchor':'middle',class:'axis'}).textContent=d.slice(5);});series.forEach((s,i)=>{const color=['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2'][i%6];const pts=s.rows.map(r=>[x(r.collect_date),y(num(r.app_rate)||0),r]).filter(p=>Number.isFinite(p[1]));add(svg,'path',{d:pts.map((p,j)=>`${j?'L':'M'}${p[0]} ${p[1]}`).join(' '),stroke:color,class:'line'});pts.forEach(([xx,yy,row],pi)=>drawAvatarPoint(svg,defs,xx,yy,row,s.slug,color,i,pi));});}
function drawAvatarPoint(svg,defs,x,y,row,slug,color,seriesIndex,pointIndex){const info=charInfo(slug),r=11,href=info.icon_url||row.icon_url;if(href){const clipId=`clip-${seriesIndex}-${pointIndex}-${Math.round(x)}-${Math.round(y)}`;const clip=add(defs,'clipPath',{id:clipId});add(clip,'circle',{cx:x,cy:y,r});const img=add(svg,'image',{href,x:x-r,y:y-r,width:r*2,height:r*2,'clip-path':`url(#${clipId})`,class:'avatar'});add(svg,'circle',{cx:x,cy:y,r,fill:'none',stroke:color,class:'avatar-ring'});img.addEventListener('mouseenter',e=>showChartTip(e,row));img.addEventListener('mousemove',moveTip);img.addEventListener('mouseleave',()=>{$('tooltip').hidden=true;});}else{const c=add(svg,'circle',{cx:x,cy:y,r:4.8,fill:color});c.addEventListener('mouseenter',e=>showChartTip(e,row));c.addEventListener('mousemove',moveTip);c.addEventListener('mouseleave',()=>{$('tooltip').hidden=true;});}}
function drawBars(series){const {svg,w,h}=chartBox();const m={l:170,r:80,t:36,b:36},rowH=Math.max(32,Math.min(44,(h-m.t-m.b)/Math.max(series.length,1)));const max=Math.max(1,...series.map(s=>num(s.latest.app_rate)||0));series.forEach((s,i)=>{const y=m.t+i*rowH+rowH/2,val=num(s.latest.app_rate)||0,x=m.l+(val/max)*(w-m.l-m.r),info=charInfo(s.slug);add(svg,'text',{x:18,y:y+4,class:'axis'}).textContent=`${i+1}. ${charName(s.slug)}`;add(svg,'line',{x1:m.l,y1:y,x2:x,y2:y,stroke:'#174c5a',class:'bar'});add(svg,'text',{x:x+14,y:y+4,class:'axis'}).textContent=pct(val);});}
function drawHeatmap(series){const {svg,w,h}=chartBox();if(!series.length){add(svg,'text',{x:40,y:60,class:'axis'}).textContent='暂无数据';return;}const dates=[...new Set(series.flatMap(s=>s.rows.map(r=>r.collect_date)))].sort();const m={l:180,r:30,t:54,b:42},gap=3,rowH=Math.max(24,Math.min(34,(h-m.t-m.b)/Math.max(series.length,1))),cw=Math.max(12,(w-m.l-m.r-(dates.length-1)*gap)/Math.max(dates.length,1));const max=Math.max(1,...series.flatMap(s=>s.rows.map(r=>num(r.app_rate)||0)));dates.forEach((d,j)=>{if(dates.length>14&&j%2)return;add(svg,'text',{x:m.l+j*(cw+gap)+cw/2,y:m.t-18,'text-anchor':'middle',class:'axis'}).textContent=d.slice(5);});series.forEach((s,i)=>{const y=m.t+i*rowH;add(svg,'text',{x:18,y:y+rowH/2+4,class:'heat-name'}).textContent=`${i+1}. ${charName(s.slug)}`;const byDate=new Map(s.rows.map(r=>[r.collect_date,r]));dates.forEach((d,j)=>{const r=byDate.get(d),val=num(r?.app_rate)||0,intensity=Math.max(.06,Math.min(1,val/max));const rect=add(svg,'rect',{x:m.l+j*(cw+gap),y:y+4,width:cw,height:rowH-8,fill:`rgba(23,76,90,${intensity})`,class:'heat-cell'});if(r){rect.addEventListener('mouseenter',e=>showChartTip(e,r));rect.addEventListener('mousemove',moveTip);rect.addEventListener('mouseleave',()=>{$('tooltip').hidden=true;});}});});}
function showChartTip(evt,row){const tt=$('tooltip');tt.innerHTML=`<div class="tooltip-grid"><b>角色</b><span>${esc(charName(row.character_slug))}</span><b>日期</b><span>${esc(row.collect_date)}</span><b>出场率</b><span>${pct(row.app_rate)}</span><b>平均分</b><span>${esc(row.avg_score||'-')}</span><b>期数</b><span>${esc(row.phase_name||row.phase_ver||'-')}</span></div>`;tt.hidden=false;moveTip(evt);}
function moveTip(evt){const tt=$('tooltip');let x=evt.clientX+16,y=evt.clientY+16;const r=tt.getBoundingClientRect();if(x+r.width+12>innerWidth)x=evt.clientX-r.width-16;if(y+r.height+12>innerHeight)y=evt.clientY-r.height-16;tt.style.left=`${Math.max(12,x)}px`;tt.style.top=`${Math.max(12,y)}px`;}
function renderCharacterList(series){const boxEl=$('characterList');if(!boxEl)return;boxEl.innerHTML='';if(!series.length){boxEl.innerHTML='<div class="empty">暂无角色数据</div>';return;}series.forEach((s,i)=>{const row=s.latest,info=charInfo(s.slug),card=document.createElement('button');card.type='button';card.className='character-card';card.innerHTML=`<img src="${esc(info.icon_url)}" alt=""><div><div class="name">${esc(charName(s.slug))}</div><div class="meta">${esc(info.tier||'未分档')} · ${esc(info.element_cn||'')} · ${esc(info.style_cn||info.role_group_cn||'')}</div></div><div class="rate">${pct(row.app_rate)}</div>`;card.onclick=()=>{$('searchInput').value=charName(s.slug);state.search=charName(s.slug).toLowerCase();renderAnalysis();};boxEl.appendChild(card);});}
function renderChangelog(series){const boxEl=$('changelogList');if(!boxEl)return;boxEl.innerHTML='';const slugs=new Set(series.map(s=>s.slug));const related=(DATA.changelogRows||[]).filter(r=>String(r.character_slugs||'').split(';').some(slug=>slugs.has(slug)));const rows=(related.length?related:(DATA.changelogRows||[])).slice(0,8);if(!rows.length){boxEl.innerHTML='<div class="empty">暂无 changelog</div>';return;}rows.forEach(r=>{const item=document.createElement('div');item.className='changelog-item';const text=String(r.text||'');item.innerHTML=`<time>${esc(r.changelog_date||'')}</time><p>${esc(text.slice(0,420))}${text.length>420?'...':''}</p>`;boxEl.appendChild(item);});}
function initBox(){buttons('boxElementControl',[['all','全部'],...ELEMENTS.map(x=>[x,x])],box.element,v=>{box.element=v;renderBox();});buttons('boxStyleControl',[['all','全部'],...STYLES.map(x=>[x,x])],box.style,v=>{box.style=v;renderBox();});$('boxOwnedSelect').onchange=e=>{box.status=e.target.value;renderBox();};$('boxSearchInput').oninput=e=>{box.search=e.target.value.trim().toLowerCase();renderBox();};$('boxExportBtn').onclick=exportBox;$('boxImportBtn').onclick=()=>$('boxImportInput').click();$('boxImportInput').onchange=importBox;$('boxMarkVisibleBtn').onclick=()=>{filteredRoster().forEach(r=>box.owned.add(r.character_slug));saveBox();renderBox();};$('boxBuildVisibleBtn').onclick=()=>setVisibleBuild(true);$('boxClearBuildVisibleBtn').onclick=()=>setVisibleBuild(false);initBuild();}
function initBuild(){const levels=BUILD_LEVELS.map(v=>`<option value="${v}">${v?`${v}级`:'未录入'}</option>`).join('');$('buildLevel').innerHTML=levels;$('buildEngine').innerHTML=levels;$('buildSkill').innerHTML=BUILD_SKILLS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('buildDisc').innerHTML=BUILD_DISCS.map(([v,l])=>`<option value="${v}">${l}</option>`).join('');$('buildLevel').onchange=e=>buildSet('level',Number(e.target.value));$('buildEngine').onchange=e=>buildSet('engine',Number(e.target.value));$('buildSkill').onchange=e=>buildSet('skills',e.target.value);$('buildDisc').onchange=e=>buildSet('discs',e.target.value);$('buildMaxBtn').onclick=()=>{if(box.buildSlug){box.builds[box.buildSlug]=fullBuild();box.owned.add(box.buildSlug);saveBox();renderBox();}};$('buildClearBtn').onclick=()=>{delete box.builds[box.buildSlug];saveBox();renderBox();};}
function loadBox(){try{const raw=JSON.parse(localStorage.getItem(BOX_KEY)||'{}');box.owned=new Set(raw.owned||[]);box.builds=raw.builds||{};box.buildSlug=raw.buildSlug||'';}catch{box.owned=new Set();box.builds={};box.buildSlug='';}}
function saveBox(){localStorage.setItem(BOX_KEY,JSON.stringify({version:1,updatedAt:new Date().toISOString(),owned:[...box.owned].sort(),buildSlug:box.buildSlug,builds:box.builds}));}
function normBuild(b={}){const skills=BUILD_SKILLS.some(x=>x[0]===b.skills)?b.skills:'unset',discs=BUILD_DISCS.some(x=>x[0]===b.discs)?b.discs:'unset';return{level:BUILD_LEVELS.includes(Number(b.level))?Number(b.level):0,engine:BUILD_LEVELS.includes(Number(b.engine))?Number(b.engine):0,skills,discs};}
function optScore(opts,v){return opts.find(x=>x[0]===v)?.[2]||0}
function buildState(slug){const b=normBuild(box.builds[slug]||{}),score=(b.level/60)*.25+(b.engine/60)*.2+optScore(BUILD_SKILLS,b.skills)*.25+optScore(BUILD_DISCS,b.discs)*.3,recorded=!!(b.level||b.engine||b.skills!=='unset'||b.discs!=='unset'),ready=recorded&&score>=.86&&b.level>=55&&b.engine>=50&&optScore(BUILD_SKILLS,b.skills)>=.84&&optScore(BUILD_DISCS,b.discs)>=.84;return{...b,score,recorded,ready,percent:Math.round(score*100),label:ready?'已成型':recorded&&score>=.72?'可用':recorded?'待练':'练度未录入'};}
function fullBuild(){return{level:60,engine:60,skills:'max',discs:'great'}}
function setVisibleBuild(value){filteredRoster().forEach(r=>{if(value){box.owned.add(r.character_slug);box.builds[r.character_slug]=fullBuild();}else delete box.builds[r.character_slug];});saveBox();renderBox();}
function filteredRoster(){const q=box.search;return DATA.rosterRows.filter(r=>(box.element==='all'||r.element_cn===box.element)&&(box.style==='all'||r.style_cn===box.style)&&(box.status==='all'||(box.status==='owned')===box.owned.has(r.character_slug))&&(!q||[r.character_name_cn,r.character_name_en,r.character_slug,r.element_cn,r.style_cn].some(x=>String(x||'').toLowerCase().includes(q))));}
function renderBox(){const rows=filteredRoster(),owned=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)).length,built=DATA.rosterRows.filter(r=>box.owned.has(r.character_slug)&&buildState(r.character_slug).ready).length;renderBuild();$('boxSubtitle').textContent=`展示 ${rows.length}/${DATA.rosterRows.length} 个代理人，已拥有 ${owned}，已成型 ${built}`;$('boxBadges').innerHTML=[box.element==='all'?'全部属性':box.element,box.style==='all'?'全部特性':box.style,`成型 ${built}/${owned||0}`].map(x=>`<span>${esc(x)}</span>`).join('');const grid=$('boxGrid');grid.innerHTML='';rows.forEach(r=>{const owned=box.owned.has(r.character_slug),bs=buildState(r.character_slug);const card=document.createElement('article');card.className=`box-card ${owned?'owned':'missing'} ${box.buildSlug===r.character_slug?'selected':''}`;card.innerHTML=`<button class="build-btn">练度</button><img src="${esc(r.icon_url)}" alt=""><div class="name">${esc(r.character_name_cn||r.character_name_en)}</div><div class="meta">${esc(r.element_cn)} · ${esc(r.style_cn)}</div><div class="meta">${owned?`${bs.label} ${bs.recorded?bs.percent+'%':''}`:'未拥有'}</div>`;card.onclick=()=>{owned?box.owned.delete(r.character_slug):box.owned.add(r.character_slug);box.buildSlug=r.character_slug;saveBox();renderBox();};card.querySelector('.build-btn').onclick=e=>{e.stopPropagation();box.owned.add(r.character_slug);box.buildSlug=r.character_slug;saveBox();renderBox();};grid.appendChild(card);});}
function renderBuild(){const p=$('buildEditor');if(!box.buildSlug||!box.owned.has(box.buildSlug)){p.classList.add('hidden');return;}const r=charInfo(box.buildSlug),bs=buildState(box.buildSlug),b=normBuild(box.builds[box.buildSlug]||{});p.classList.remove('hidden');$('buildIcon').src=r.icon_url;$('buildTitle').textContent=`${charName(box.buildSlug)} · 练度`;$('buildSubtitle').textContent=`${r.element_cn} · ${r.style_cn}`;$('buildLevel').value=b.level;$('buildEngine').value=b.engine;$('buildSkill').value=b.skills;$('buildDisc').value=b.discs;$('buildScore').textContent=`${bs.label} · ${bs.percent}%`;}
function buildSet(k,v){if(!box.buildSlug)return;box.builds[box.buildSlug]={...normBuild(box.builds[box.buildSlug]||{}),[k]:v};box.owned.add(box.buildSlug);saveBox();renderBox();}
function exportBox(){const blob=new Blob([JSON.stringify({version:1,exportedAt:new Date().toISOString(),owned:[...box.owned].sort(),builds:box.builds},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='zzz_box_state.json';a.click();URL.revokeObjectURL(a.href);}
function importBox(e){const file=e.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{try{const d=JSON.parse(String(reader.result||'{}'));box.owned=new Set(d.owned||[]);box.builds=d.builds||{};box.buildSlug='';saveBox();renderBox();}catch(err){alert(`导入失败：${err.message}`);}finally{e.target.value='';}};reader.readAsText(file);}
function initRec(){buttons('recModeControl',MODES,rec.mode,v=>{rec.mode=v;ensureScope();saveRec();syncRec();renderRec();});ELEMENTS.forEach(el=>{const b=document.createElement('button');b.textContent=el;b.onclick=()=>{const s=elementSet();s.has(el)?s.delete(el):s.add(el);rec.elements[key()]=[...s];saveRec();syncRec();renderRec();};$('recElementControl').appendChild(b);});$('recScopeSelect').onchange=e=>{rec.scope=e.target.value;saveRec();renderRec();};$('recGapSelect').onchange=e=>{rec.gap=e.target.value;saveRec();renderRec();};$('recRiskSelect').onchange=e=>{rec.riskMode=e.target.value;saveRec();renderRec();};$('recLimitSelect').onchange=e=>{rec.limit=e.target.value;saveRec();renderRec();};$('recSearchInput').oninput=e=>{rec.search=e.target.value.trim().toLowerCase();saveRec();renderRec();};ensureScope();}
function loadRec(){try{rec={...rec,...JSON.parse(localStorage.getItem(REC_KEY)||'{}')};}catch{}}
function saveRec(){localStorage.setItem(REC_KEY,JSON.stringify({...rec,updatedAt:new Date().toISOString()}));}
function key(){return `${rec.mode}|${rec.scope}`}
function elementSet(){return new Set(rec.elements?.[key()]||[])}
function scopes(){const map=new Map();DATA.teamTemplates.filter(t=>t.mode===rec.mode).forEach(t=>map.set(t.scope_key,{key:t.scope_key,label:t.scope_label}));return [...map.values()].sort((a,b)=>a.key.localeCompare(b.key));}
function ensureScope(){const ss=scopes();if(ss.length&&!ss.some(s=>s.key===rec.scope))rec.scope=ss[0].key;}
function syncRec(){const ss=scopes();$('recScopeSelect').innerHTML=ss.map(s=>`<option value="${esc(s.key)}">${esc(s.label)}</option>`).join('');$('recScopeSelect').value=rec.scope;$('recGapSelect').value=rec.gap;$('recRiskSelect').value=rec.riskMode;$('recLimitSelect').value=rec.limit||'8';$('recSearchInput').value=rec.search;const s=elementSet();[...$('recElementControl').children].forEach(b=>b.classList.toggle('active',s.has(b.textContent)));}
function tierMeta(slug){return DATA.tierRows.filter(r=>r.character_slug===slug&&r.tier_mode===rec.mode).sort((a,b)=>(TIER_RANK[a.tier]??9)-(TIER_RANK[b.tier]??9))[0]||{}}
function memberRisk(m){const risks=[],tier=tierMeta(m.slug),rank=TIER_RANK[tier.tier]??9,bs=m.build;if(m.owned){if(!bs.recorded)risks.push({text:'练度未录入',penalty:m.core?42:22});else if(bs.score<.68)risks.push({text:`练度待补 ${bs.percent}%`,penalty:m.core?70:36,severe:m.core});}if(rank>=5)risks.push({text:`${tier.tier}不建议投入${bs.ready?'（已练，降权）':''}`,penalty:bs.ready?35:90,severe:true});else if(rank>=3)risks.push({text:`${tier.tier}非主流低档${bs.ready?'（已练，降权）':''}`,penalty:bs.ready?25:62,severe:true});else if(rank>=1&&!bs.ready)risks.push({text:`${tier.tier}投入谨慎`,penalty:m.core?32:18});return risks;}
function scoreTeam(t,used=new Set()){const selected=elementSet();const members=t.chars.map(slug=>{const info=charInfo(slug),bs=buildState(slug),core=['crit_dps','anomaly_dps'].includes(info.role_group);return{slug,info,build:bs,owned:box.owned.has(slug),selected:selected.has(info.element_cn),core,conflict:used.has(slug)};});members.forEach(m=>m.risks=memberRisk(m));const owned=members.filter(m=>m.owned).length,ready=members.filter(m=>m.owned&&m.build.ready).length,miss=3-owned,elementHits=members.filter(m=>m.selected).length,coreHits=members.filter(m=>m.core&&m.selected).length,conflictCount=members.filter(m=>m.conflict&&m.owned).length,risks=members.flatMap(m=>m.risks.map(r=>({...r,name:charName(m.slug)})));if(selected.size&&members.some(m=>m.core)&&coreHits===0)risks.push({text:'主C均未命中推荐属性',penalty:145,severe:true});const penalty=rec.riskMode==='off'?0:risks.reduce((s,r)=>s+(r.penalty||0),0);let score=owned*46+members.filter(m=>m.owned).reduce((s,m)=>s+m.build.score*88,0)-miss*72-conflictCount*160+elementHits*12+coreHits*56+Math.min(num(t.app_rate)||0,35)*2.1-penalty;if(t.rank!=null)score+=Math.max(0,130-t.rank)*.4;if(selected.size&&elementHits===0)score-=35;return{template:t,members,ownedCount:owned,readyCount:ready,missingCount:miss,elementHits,coreHits,conflictCount,risks,score,search:[t.phase_name,t.scope_label,t.bangboo,t.bangboo_name,...t.chars,...t.names_cn,...risks.map(r=>r.text)].join(' ').toLowerCase()};}
function rankedFor(mode=rec.mode,scope=rec.scope,used=new Set(),ignoreSearch=false){return DATA.teamTemplates.filter(t=>t.mode===mode&&t.scope_key===scope).map(t=>scoreTeam(t,used)).filter(i=>i.missingCount<=Number(rec.gap)&&(rec.riskMode!=='filter'||!i.risks.length)&&(ignoreSearch||!rec.search||i.search.includes(rec.search))).sort((a,b)=>b.score-a.score||a.conflictCount-b.conflictCount||a.missingCount-b.missingCount||(a.template.rank||9999)-(b.template.rank||9999));}
function ranked(){return rankedFor();}
function phaseInfo(){const templates=DATA.teamTemplates.filter(t=>t.mode===rec.mode&&t.scope_key===rec.scope),latest=templates.slice().sort((a,b)=>String(b.collect_date).localeCompare(String(a.collect_date)))[0];const rows=DATA.phaseInfoRows||[];return rows.find(r=>r.mode===rec.mode&&r.phase_ver===latest?.phase_ver&&r.collect_date===latest?.collect_date)||rows.filter(r=>r.mode===rec.mode).sort((a,b)=>String(b.collect_date).localeCompare(String(a.collect_date)))[0]||{};}
function renderPhaseInfo(){const p=phaseInfo();$('phaseTitle').textContent=`${p.mode_cn||MODES.find(x=>x[0]===rec.mode)?.[1]||rec.mode} · ${p.phase_name_cn||p.phase_name||p.phase_ver||'当期数据'}`;$('phaseDates').textContent=`${p.start_date||'未知'} 至 ${p.end_date||'未知'} · 采样 ${p.collect_date||'未知'}`;$('phaseText').textContent=p.mechanic_text||'推荐限定当前同模式、同关卡数据源。';}
function renderRec(){ensureScope();syncRec();renderPhaseInfo();const rows=ranked().slice(0,Number(rec.limit)||8),sel=[...elementSet()],templates=DATA.teamTemplates.filter(t=>t.mode===rec.mode&&t.scope_key===rec.scope);$('recTitle').textContent=`${MODES.find(x=>x[0]===rec.mode)?.[1]} · ${scopes().find(s=>s.key===rec.scope)?.label||rec.scope}`;$('recSubtitle').textContent=`当前同模式同关卡模板 ${templates.length} 队`;const riskLabel=rec.riskMode==='filter'?'过滤风险':rec.riskMode==='off'?'忽略风险':'仅提醒';$('recBadges').innerHTML=[sel.length?sel.join(' / '):'未选属性',`缺口 ≤ ${rec.gap}`,riskLabel,rec.riskMode==='off'?'T档不提醒':'T1及以下提醒',`Box ${box.owned.size}`].map(x=>`<span>${esc(x)}</span>`).join('');const list=$('recList');list.innerHTML='';if(!rows.length){list.innerHTML='<div class="empty">当前筛选没有可展示队伍</div>';renderRecSlate();return;}rows.forEach((item,i)=>list.appendChild(recCard(item,i+1)));renderRecSlate();}
function recCard(item,i){const t=item.template,card=document.createElement('article');card.className=`rec-card ${item.risks.length&&rec.riskMode!=='off'?'risky':''}`;card.innerHTML=`<div class="rec-head"><div><h3>${i}. ${esc(t.names_cn.join(' / '))}</h3><div class="rec-meta">${esc(t.scope_label)} · Rank ${t.rank??'-'} · ${pct(t.app_rate)} · 邦布 ${esc(bangbooName(t.bangboo,t.bangboo_name))}</div></div><div class="score">${Math.round(item.score)}<br><span>${item.ownedCount}/3</span></div></div><div class="rec-team">${item.members.map(m=>memberHtml(m)).join('')}</div><div class="tags"><span class="${item.missingCount?'warn':''}">${item.missingCount?`缺 ${item.missingCount}`:'可成队'}</span>${item.ownedCount?`<span class="${item.readyCount<item.ownedCount?'warn':''}">练度 ${item.readyCount}/${item.ownedCount}</span>`:''}<span>属性命中 ${item.elementHits}</span>${item.conflictCount?`<span class="warn">多队冲突 ${item.conflictCount}</span>`:''}${item.risks.length&&rec.riskMode!=='off'?`<span class="${item.risks.some(r=>r.severe)?'danger':'warn'}">风险 ${item.risks.length}</span>`:''}</div>${riskHtml(item)}`;return card;}
function memberHtml(m){const risky=(m.risks.length&&rec.riskMode!=='off')||m.conflict;return `<div class="rec-member ${m.owned?'owned':'missing'} ${risky?'risky':''}"><img src="${esc(m.info.icon_url)}" alt=""><div class="name">${esc(charName(m.slug))}</div><div class="meta">${esc(m.info.element_cn)} · ${esc(m.info.style_cn)}${m.owned?` · ${esc(m.build.label)}`:''}${m.conflict?' · 冲突':''}</div></div>`;}
function riskHtml(item){if(!item.risks.length||rec.riskMode==='off')return '';return `<div class="risk-note">${esc(item.risks.slice(0,4).map(r=>r.name?`${r.name}：${r.text}`:r.text).join('；'))}${item.risks.length>4?'；...':''}</div>`;}
function renderRecSlate(){const list=$('recSlateList'),scopeList=scopes().filter(s=>s.key!=='all');list.innerHTML='';const used=new Set(),chosen=[];scopeList.forEach(scope=>{const item=rankedFor(rec.mode,scope.key,used,true).find(x=>x.conflictCount===0)||rankedFor(rec.mode,scope.key,used,true)[0];if(item){item.members.filter(m=>m.owned).forEach(m=>used.add(m.slug));}chosen.push({scope,item});});$('recSlateSubtitle').textContent=`${chosen.filter(x=>x.item).length}/${scopeList.length} 队 · 尽量不复用已拥有角色`;if(!chosen.length){list.innerHTML='<div class="empty">暂无当前模式关卡模板</div>';return;}chosen.forEach(({scope,item})=>{const card=document.createElement('div');card.className=`rec-slate-card ${item?.risks?.length&&rec.riskMode!=='off'?'risky':''}`;if(!item){card.innerHTML=`<h3>${esc(scope.label)}</h3><div class="rec-meta">没有符合缺口限制的队伍</div>`;}else{card.innerHTML=`<h3>${esc(scope.label)} · ${Math.round(item.score)} · ${item.ownedCount}/3</h3><div class="rec-slate-team">${item.members.map(m=>`<img class="${m.owned?'':'missing'} ${m.risks.length&&rec.riskMode!=='off'?'risky':''}" src="${esc(m.info.icon_url)}" title="${esc(charName(m.slug))}" alt="">`).join('')}</div>${riskHtml(item)}`;}list.appendChild(card);});}
"""
