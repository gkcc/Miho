# Miho

Miho 要做的是一个本地优先的游戏练度更新与规划软件：米游社 APP 已登录后，最终目标是一键保存官方分享图、解析练度、更新本地 box，再结合高难数据、Tier / 保值观察和已有角色，给出“只练高价值角色，顺手拿奖励”的配队建议。

当前还不是正式 Tauri 桌面应用，而是 probe / demo 版本。它不会自动登录，不读取 cookie/token，不控制游戏客户端，也不会把 OCR 结果直接写进正式数据库。

## 现在先点哪里

先记住一句：**验收界面点缓存入口，识别新图才点 Fresh OCR。**

- 想看软件体验：点 `MihoProbe`，或运行 `dist\MihoProbe.exe`。它只打开已有 Dashboard，不跑 OCR。
- 新放了官方分享图：点 `MihoProbe Fresh OCR`，或运行 `dist\MihoProbe.exe fresh`。这一步会跑 PaddleOCR，可能慢。
- 验收解析准确率：点 `MihoProbe Accuracy Check`，或运行 `dist\MihoProbe.exe replay --no-open`。它不重新 OCR。

没有 EXE 时才用脚本版入口：

- `scripts\run_miho_demo.bat`：打开缓存 Dashboard，不跑 OCR。
- `scripts\run_miho_demo.bat --fresh`：识别 `figs/` 下新增或变更的分享图。

如果你只想验收页面，不要先跑 OCR。先用“秒开缓存”的入口看 Dashboard 是否可读：

1. 构建一次本地 EXE：

```powershell
scripts\build_miho_probe_exe.bat
```

仓库路径：`scripts/build_miho_probe_exe.bat`。
构建配置：`packaging/MihoProbe.spec`。

等价 PowerShell 入口：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_miho_probe_exe.ps1
```

2. 安装桌面快捷方式：

```powershell
scripts/install_miho_demo_shortcut.bat
```

3. 桌面优先点这些：

- `MihoProbe`：像软件一样打开已有 Dashboard，不重新 OCR，正常应该很快。
- `MihoProbe Fresh OCR`：只在 `figs/` 里放了新的官方分享图后再点；会跑 PaddleOCR。
- `MihoProbe Accuracy Check`：跑 P0.9 replay 准确率验收，不重新 OCR。
- `MihoProbe CLI`：打开命令壳，给开发调试用。

默认入口现在不会自动跑 OCR。如果 `MihoProbe Fresh OCR`、`Miho Demo Fresh OCR` 或 `scripts/run_miho_demo.bat --fresh` 十分钟没反应，通常是 PaddleOCR 首次加载模型或图片识别卡住；先关掉它，改点 `MihoProbe` / `Miho Demo` 看缓存结果。

命令行等价入口：

```powershell
dist\MihoProbe.exe
dist\MihoProbe.exe dashboard --open
scripts\run_miho_demo.bat
```

确实要重新识别新图时才用：

```powershell
dist\MihoProbe.exe fresh
scripts\run_miho_demo.bat --fresh
```

`dist\MihoProbe.exe fresh` 默认只处理新增或变更图片；要强制全量重扫时加 `--rescan-all`。

## Dashboard 怎么看

打开页面先只看第一屏：

- `当前结论`：能不能直接用本地建议。
- `下一步`：该刷新数据、复核字段、人工应用，还是可以看队伍建议。
- `今日作战简报`：只回答“现在能不能用、卡在哪里、下一步点哪里”。
- `待确认快照`：OCR / 解析候选，人工确认前不算已拥有练度。

颜色规则只记一句：绿色才是可继续，黄色是先复核，红色是先处理数据一致性。

如果页面提示缺少运行清单或待复核，不要按配队行动；先点卡片里的复核入口确认字段。只有字段明显是旧图或图片缺失，才重新跑 Fresh OCR。

## 当前三个验收入口

### 1. 成品体验

```powershell
dist\MihoProbe.exe
```

目标：秒开缓存 Dashboard，像软件入口一样可交互、可视化、可读。

### 2. 新分享图识别

```powershell
dist\MihoProbe.exe fresh
```

目标：读取 `figs/` 下官方分享图，解析练度，生成待人工确认的本地结果。这个入口可能慢，因为它会真的跑图片识别。

单张图调试用：

```powershell
python tools/probes/review_export_image.py --image "C:\path\to\share.jpg" --engine paddle --lang chi_sim+eng --write-crops --open
```

### 3. 准确率怎么验收

解析准确率只用 manifest 验收，不要扫整个历史目录：

```powershell
dist\MihoProbe.exe replay --no-open
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

通过口径：

- 3 张以上图平均通过率达标。
- 每张图不能低于门槛。
- 角色或音擎不能全错还通过。
- 驱动盘主词条和副词条不能全缺还通过。

## Codex / GPT 审查流

右侧 GPT 只负责出方案和挑代码缺陷，Codex 负责落地、测试和推送。不要再临时摸索聊天流程，直接生成固定审查包：

```powershell
dist\MihoProbe.exe gpt-review `
  --focus "本轮要推进的用户可见结果" `
  --evidence "关键命令或页面现象" `
  --changed-file "path/to/file.py: 改了什么"
```

还没构建 EXE 时，用 `python tools/probes/build_gpt_review_prompt.py`，参数相同。

协议说明见 [docs/notes/codex-gpt-adversarial-loop.md](docs/notes/codex-gpt-adversarial-loop.md)。

## 当前能做和不能做

现在能做：

- 从官方分享图或已有 parsed JSON 生成本地 Dashboard。
- 解析结果进入人工复核区，确认后才进入本地角色库。
- 基于本地角色库、目标配置和本地 Tier snapshot 生成今日简报、队伍卡、行动卡。
- 用 replay manifest 做解析准确率回归。
- 构建 `dist\MihoProbe.exe` 作为本地软件入口。

现在不能做：

- 自动登录米游社。
- 读取或保存 cookie、token、stoken、ltoken。
- 控制游戏客户端。
- 自动联网刷新真实 Tier list 或高难出场率。
- 把真实分享图、UID、OCR 原始结果或 `data/probes/` 产物提交到 Git。

## 开发入口

- Probe 命令细节：[tools/probes/README.md](tools/probes/README.md)
- GPT 审查包生成器：[tools/probes/build_gpt_review_prompt.py](tools/probes/build_gpt_review_prompt.py)
- Replay batch 验收：[tools/probes/run_export_replay_batch.py](tools/probes/run_export_replay_batch.py)
- 单图解析复核：[tools/probes/review_export_image.py](tools/probes/review_export_image.py)
- 技术栈边界：[docs/adr/0001-tech-stack-selection.md](docs/adr/0001-tech-stack-selection.md)、[docs/adr/0002-mvp-boundary-and-module-layering.md](docs/adr/0002-mvp-boundary-and-module-layering.md)、[docs/adr/0003-local-data-model-and-snapshot-strategy.md](docs/adr/0003-local-data-model-and-snapshot-strategy.md)
- 米游社 APP 探针边界：[docs/spikes/0001-miyoushe-app-feasibility.md](docs/spikes/0001-miyoushe-app-feasibility.md)
- 分享图解析记录：[docs/notes/share-image-parsing-result.md](docs/notes/share-image-parsing-result.md)

永远不要提交真实账号数据、登录态文件、数据库文件、`.env`、真实图片或 `data/probes/` 探针产物。
