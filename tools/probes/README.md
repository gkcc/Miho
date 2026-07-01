# ZZZ Box / Tier 工具

本目录只保留 box / tier / 配队规划主线。

## 1. 公开 Meta

读取公开 Prydwen ZZZ tier list、式舆防卫战和危局强袭战统计：

```powershell
python tools/probes/prepare_zzz_meta_snapshot.py `
  --output data/probes/meta/zzz_prydwen_meta_all_phases.json
```

调试时只取当前 phase：

```powershell
python tools/probes/prepare_zzz_meta_snapshot.py `
  --current-only `
  --output data/probes/meta/zzz_prydwen_meta_current.json
```

该命令只访问公开网页和公开 API，不读取账号、不读取 cookie/token、不抓包。

## 2. 读取 Box

优先使用已人工确认的脱敏 roster JSON。也可以从用户显式提供的官方 ZZZ box 总览图生成本地 roster 草案：

```powershell
python tools/probes/extract_zzz_box_roster.py `
  --image data/probes/exported_images/zzz_box_overview.png `
  --meta-snapshot data/probes/meta/zzz_prydwen_meta_all_phases.json `
  --output-json data/probes/box/zzz_box_roster.json `
  --output-markdown data/probes/box/zzz_box_roster.md
```

输出只保留角色名、slug、等级、影画等规划字段；不会保存 UID、昵称或 header 原始识别文本。识别结果仍是草案，人工确认前只能作为候选 box。

## 3. 价值、配队、培养与未来观察

一条命令生成报告：

```powershell
python tools/probes/run_zzz_box_value_pipeline.py `
  --roster-json data/probes/box/zzz_box_roster.json `
  --meta-snapshot data/probes/meta/zzz_prydwen_meta_all_phases.json `
  --output-dir data/probes/value/current
```

也可以直接传 box 图：

```powershell
python tools/probes/run_zzz_box_value_pipeline.py `
  --box-image data/probes/exported_images/zzz_box_overview.png `
  --meta-snapshot data/probes/meta/zzz_prydwen_meta_all_phases.json `
  --output-dir data/probes/value/zzz_box_overview
```

主要输出：

```text
data/probes/value/current/agent_value_cards.json
data/probes/value/current/agent_value_cards.md
```

报告包含：

- 账号内代理人 Tier；
- 现实价值 / 潜力价值；
- 当前高难全 owned 队伍候选；
- 培养优先级；
- 缺一名角色的观察队；
- 低等级高价值角色的投入成本提示；
- 低价值角色不为过关强拉的警告。

## 4. EXE 壳

```powershell
dist\MihoProbe.exe meta --current-only
dist\MihoProbe.exe box-roster --image data\probes\exported_images\zzz_box_overview.png
dist\MihoProbe.exe box-value --roster-json data\probes\box\zzz_box_roster.json --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json
dist\MihoProbe.exe status
```

`status` 只做本地文件检查，不联网、不识别图片。

## 5. 边界

- Prydwen appearance rate 是公开使用信号，不是持有率，也不是抽卡价值。
- 缺失角色只能进入未来观察，不算当前可用队。
- box 图不能证明音擎、驱动盘、技能等级或毕业度。
- 输出仍写入 `data/probes/`，不得提交真实图片、真实 roster、账号标识或本地数据产物。
