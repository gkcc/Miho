# Miho

本项目要做的是一个本地优先的练度跟踪与规划工具：从米游社官方分享图更新角色练度，再结合本地高难目标、Tier/保值观察和已确认 box，给出“练高价值角色，顺手拿奖励”的配队与培养建议。

当前还处在 probe / demo 阶段，不是正式 Tauri 桌面应用。它不会自动登录，不读取 cookie/token，不控制游戏客户端，也不会把 OCR 结果直接写进正式数据库。

## 现在先点哪里

如果你只是想验收当前体验，不要先跑 OCR。按这个顺序：

1. 第一次使用先装桌面入口。
2. 点桌面的 `Miho Demo`，它只打开已有 Dashboard，正常应该很快。
3. 只有分享图换了，才点 `Miho Demo Fresh OCR` 重新识别图片。

安装桌面入口：

```powershell
scripts/install_miho_demo_shortcut.bat
```

桌面会出现这些入口：

- `Miho Demo`：秒开已有 Dashboard。普通验收先点这个。
- `Miho Demo Fresh OCR`：重新识别 `figs/` 下的官方分享图。PaddleOCR 首次加载会慢。
- `MihoProbe`：构建过 `dist/MihoProbe.exe` 后出现，像软件入口一样直接打开本地 Dashboard。
- `MihoProbe Accuracy Check`：构建过 EXE 后出现，一键跑 P0.9 replay 准确率验收，不重新 OCR。
- `MihoProbe CLI`：打开 EXE 命令壳和常用命令示例。

如果 `scripts/run_miho_demo.bat` 等了十分钟还没反应，通常是你正在跑 fresh OCR。PaddleOCR 首次加载模型会慢；只想看结果请直接点 `Miho Demo`，或运行：

```powershell
scripts\run_miho_demo.bat
```

它会打开缓存 Dashboard，不会重新 OCR。确实要重扫 `figs/` 时才运行：

```powershell
scripts\run_miho_demo.bat --fresh
```

想先生成 EXE 命令壳：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_miho_probe_exe.ps1
scripts/install_miho_demo_shortcut.bat
```

构建后也可以直接运行：

```powershell
dist\MihoProbe.exe
```

无参数会打开缓存 Dashboard，不会重新 OCR。

准确率验收也可以走 EXE：

```powershell
dist\MihoProbe.exe replay
```

它默认读取 `data/probes/replay_manifest.json`，生成 replay batch 报告并打开 Markdown 摘要。

## Dashboard 怎么看

打开 Dashboard 后先看第一屏：

- `当前结论`：能不能直接用本地建议。
- `下一步`：重跑、复核、人工应用，还是可以看队伍建议。
- `今日作战简报`：只回答“现在能不能用、卡在哪里、下一步点哪里”。
- `待确认快照`：OCR/解析候选，人工确认前不算已拥有练度。

如果页面提示缺少运行清单或待复核，不要按配队行动；先点卡片里的 `打开复核页` 确认字段。只有字段明显是旧图或图片缺失，才重新跑 `Miho Demo Fresh OCR`。

看不懂时只记一句：绿色才是可继续，黄色是先复核，红色是先处理数据一致性。

## 准确率怎么验收

解析准确率只用 manifest 验收，不要扫整个历史目录：

```powershell
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

等价的软件入口：

```powershell
dist\MihoProbe.exe replay --no-open
```

通过口径：

- 3 张以上图平均通过率达标。
- 每张图不能低于门槛。
- 角色或音擎不能全错还通过。
- 驱动盘主词条和副词条不能全缺还通过。

单张图调试用：

```powershell
python tools/probes/review_export_image.py --image "C:\path\to\share.jpg" --engine paddle --lang chi_sim+eng --write-crops --open
```

## Codex / GPT 审查流

需要右侧 GPT 审方案时，直接生成固定审查包，不再重新摸索聊天流程：

```powershell
python tools/probes/build_gpt_review_prompt.py `
  --focus "本轮要推进的用户可见结果" `
  --evidence "关键命令或页面现象" `
  --changed-file "path/to/file.py: 改了什么"
```

协议说明见 [docs/notes/codex-gpt-adversarial-loop.md](docs/notes/codex-gpt-adversarial-loop.md)。

## 当前边界

现在能做：

- 从官方分享图或已有 parsed JSON 生成本地 Dashboard。
- 解析结果进入人工复核区，确认后才进入本地角色库。
- 基于本地角色库、目标配置和本地 Tier snapshot 生成今日简报、队伍卡、行动卡。
- 用 replay manifest 做解析准确率回归。

现在不能做：

- 自动登录米游社。
- 读取或保存 cookie、token、stoken、ltoken。
- 控制游戏客户端。
- 自动联网刷新真实 Tier list 或高难出场率。
- 把真实分享图、UID、OCR 原始结果或 `data/probes/` 产物提交到 Git。

## 深入文档

- Probe 命令细节：[tools/probes/README.md](tools/probes/README.md)
- 技术栈边界：[docs/adr/0001-tech-stack-selection.md](docs/adr/0001-tech-stack-selection.md)、[docs/adr/0002-mvp-boundary-and-module-layering.md](docs/adr/0002-mvp-boundary-and-module-layering.md)、[docs/adr/0003-local-data-model-and-snapshot-strategy.md](docs/adr/0003-local-data-model-and-snapshot-strategy.md)
- 米游社 APP 探针边界：[docs/spikes/0001-miyoushe-app-feasibility.md](docs/spikes/0001-miyoushe-app-feasibility.md)
- 分享图解析记录：[docs/notes/share-image-parsing-result.md](docs/notes/share-image-parsing-result.md)

永远不要提交真实账号数据、登录态文件、数据库文件、`.env`、真实图片或 `data/probes/` 探针产物。
