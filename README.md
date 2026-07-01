# Miho

Miho 现在收敛为一个本地优先的 ZZZ box / tier / 配队规划工具。

项目当前主线只做四件事：

1. 读取公开 Prydwen ZZZ tier、式舆防卫战、危局强袭战统计。
2. 读取你的本地 box：优先用已脱敏 roster JSON，也可以从你显式提供的官方 ZZZ box 总览图生成本地 roster 草案。
3. 基于当前 box 生成账号内代理人价值、配队候选和培养优先级。
4. 输出缺一名角色的观察队，作为未来视 / 抽取前问题，不把它当确定抽卡建议。

## 快速验收

如果已经有本地 meta 和 roster：

```powershell
python tools/probes/run_zzz_box_value_pipeline.py `
  --roster-json data/probes/box/zzz_box_roster.json `
  --meta-snapshot data/probes/meta/zzz_prydwen_meta_all_phases.json `
  --output-dir data/probes/value/current
```

看这份报告：

```text
data/probes/value/current/agent_value_cards.md
```

通过口径：

- 有“当前优先看”：告诉你账号内哪些角色值得先练。
- 有“队伍需要就拉起”：低等级高价值角色只作为队伍需要时的培养项。
- 有“不为了过关强拉”：避免把低价值角色硬拉满。
- 有“当前高难候选队伍”：按公开 team usage 和当前 box 给式舆 / 危局候选。
- 有“缺一名角色的观察队”：这是未来视，不是必抽结论。

## 常用命令

准备公开 meta：

```powershell
python tools/probes/prepare_zzz_meta_snapshot.py `
  --output data/probes/meta/zzz_prydwen_meta_all_phases.json
```

只拉当前 phase 调试：

```powershell
python tools/probes/prepare_zzz_meta_snapshot.py `
  --current-only `
  --output data/probes/meta/zzz_prydwen_meta_current.json
```

从官方 ZZZ box 总览图生成 roster 草案：

```powershell
python tools/probes/extract_zzz_box_roster.py `
  --image data/probes/exported_images/zzz_box_overview.png `
  --meta-snapshot data/probes/meta/zzz_prydwen_meta_all_phases.json `
  --output-json data/probes/box/zzz_box_roster.json `
  --output-markdown data/probes/box/zzz_box_roster.md
```

生成 box 价值 / 配队 / 培养 / 未来观察报告：

```powershell
python tools/probes/run_zzz_box_value_pipeline.py `
  --box-image data/probes/exported_images/zzz_box_overview.png `
  --meta-snapshot data/probes/meta/zzz_prydwen_meta_all_phases.json `
  --output-dir data/probes/value/zzz_box_overview
```

EXE 壳等价入口：

```powershell
dist\MihoProbe.exe meta --current-only
dist\MihoProbe.exe box-roster --image data\probes\exported_images\zzz_box_overview.png
dist\MihoProbe.exe box-value --roster-json data\probes\box\zzz_box_roster.json --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json
dist\MihoProbe.exe status
```

## 报告怎么看

`agent_value_cards.md` 是当前第一验收文件：

- `账号内代理人 Tier`：只在你的 box 内排序，不是全角色榜单。
- `现实价值`：更偏当前高难、公开出场和已有队伍。
- `潜力价值`：更偏未来队友、公开强度和保值观察。
- `当前高难候选队伍`：只把你已拥有的角色算入当前队伍。
- `缺一名角色的观察队`：回答“缺谁会改变这个 box 的队伍形态”，不回答“必须抽谁”。

## 当前边界

能做：

- 拉取公开 Prydwen tier / endgame / team usage 数据。
- 读取本地 roster JSON。
- 从用户显式提供的官方 ZZZ box 总览图生成脱敏 roster 草案。
- 生成账号内价值、配队候选、培养优先级和未来观察。

不能做：

- 不自动登录。
- 不读取 cookie、token、stoken、ltoken。
- 不抓包。
- 不控制游戏客户端。
- 不把图片识别出的 roster 草案自动当作最终 box。
- 不把缺失角色观察队当成确定抽卡建议。
- 不提交 `data/probes/`、真实图片、真实 roster、数据库或账号标识。

## 构建 EXE

```powershell
scripts\build_miho_probe_exe.bat
```

构建后运行：

```powershell
dist\MihoProbe.exe --help
```

## 开发验证

```powershell
python -m unittest discover tests
git diff --check
```

保留的核心文件：

- `tools/probes/prepare_zzz_meta_snapshot.py`
- `tools/probes/extract_zzz_box_roster.py`
- `tools/probes/build_agent_value_cards.py`
- `tools/probes/run_zzz_box_value_pipeline.py`
- `tools/probes/miho_probe_cli.py`
- `docs/notes/zzz-agent-value-method.md`
- `docs/spikes/0002-prydwen-zzz-agent-value-feasibility.md`
