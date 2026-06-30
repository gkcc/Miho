# Miho

Miho 是一个本地优先的游戏练度更新与规划工具。最终目标很简单：

1. 米游社 APP 已登录时，一键保存官方分享图并解析练度。
2. 本地保存高难、Tier / 保值观察和已有 box。
3. 用漂亮的 Dashboard 给出“只练高价值角色，顺手拿奖励”的配队建议。

现在仍是 probe / demo 阶段，不是正式 Tauri 桌面应用。它不会自动登录，不读取 cookie/token，不控制游戏客户端，也不会把 OCR 结果直接写进正式数据库。

## 我只想像软件一样用

第一次只做两件事：

1. 构建本地 EXE：`scripts\build_miho_probe_exe.bat`。
2. 安装桌面快捷方式：`scripts\install_miho_demo_shortcut.bat`。

以后日常只点桌面图标，不用记参数。

最重要的一句：**只看界面点 `MihoProbe`；识别新分享图才点 `MihoProbe Update`。不要先跑 OCR。**

如果你只是在验收“这个工具现在长什么样”，不要点 Fresh OCR。那个入口会加载 PaddleOCR，第一次很慢。

## 桌面图标怎么选

| 想做什么 | 点哪个 / 跑哪个 | 会不会重新识别图片 |
| --- | --- | --- |
| 看软件体验 | `MihoProbe` 或 `dist\MihoProbe.exe` | 不会 |
| 查看 APP 一键导出流程/校准 | `MihoProbe App Export Workflow` 或 `dist\MihoProbe.exe app-export` | 不会 |
| 一键更新练度 | `MihoProbe Update` 或 `dist\MihoProbe.exe update` | 会，只处理 `figs/` 里的官方分享图 |
| 一键更新高难配队 | `MihoProbe Plan Update` 或 `dist\MihoProbe.exe plan-update` | 不会 |
| 快速排查评级 | `MihoProbe Rank Check` 或 `dist\MihoProbe.exe rank-check` | 不会，只看 A/S 艺术字区域 |
| 新分享图识别 | `MihoProbe Fresh OCR` 或 `dist\MihoProbe.exe fresh` | 会，可能慢 |
| 准确率验收 | `MihoProbe Accuracy Check` 或 `dist\MihoProbe.exe check --no-open` | 不会 |
| 找右侧 GPT 挑刺 | `dist\MihoProbe.exe ask-gpt --focus "本轮要审的问题"` | 不会 |

默认入口现在不会自动跑 OCR。第一次还没有 Dashboard 缓存时，`MihoProbe` 会打开初次启动页，不是报错。

`app-export` 当前只生成“官方分享图路线 + readiness gates + 校准命令”。它不是自动导出按钮；只有用户确认官方 UI 坐标后，后续才可能逐步打开确认式点击。

如果 `MihoProbe Fresh OCR` 或 `scripts\run_miho_demo.bat --fresh` 十分钟没反应，先关掉它，改点 `MihoProbe` 看缓存 Dashboard。Fresh OCR 慢通常是 PaddleOCR 模型加载或图片识别，不代表缓存界面坏了。

评级失败先别重跑整张图。`MihoProbe Rank Check` 只检查角色头像左上角和音擎区域的 A/S 艺术字，几秒内就能判断是不是评级 crop 问题。

## 安装本地入口

构建 EXE：

```powershell
scripts\build_miho_probe_exe.bat
```

仓库路径：`scripts/build_miho_probe_exe.bat`。

等价 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_miho_probe_exe.ps1
```

然后安装桌面快捷方式：

```powershell
scripts/install_miho_demo_shortcut.bat
```

构建配置在 `packaging/MihoProbe.spec`。脚本版兼容入口是 `scripts\run_miho_demo.bat`；有 `dist\MihoProbe.exe` 时它会优先走 EXE 快入口。

## Dashboard 怎么看

打开页面先只看第一屏：

- `当前结论`：能不能直接用本地建议。
- `下一步`：该刷新数据、复核字段、人工应用，还是可以看队伍建议。
- `今日作战简报`：只回答“现在能不能用、卡在哪里、下一步点哪里”。
- `待确认快照`：OCR / 解析候选，人工确认前不算已拥有练度。

颜色规则只记一句：**绿色才是可继续，黄色是先复核，红色是先处理数据一致性。**

如果页面说“缺少运行清单”“待复核”“解析失败”，不要按配队行动；先处理页面给出的阻断原因。只有字段明显来自旧图或图片缺失时，才重新跑 Fresh OCR。

如果页面上出现“不是验收结果”，意思不是软件坏了，而是当前打开的是演示/排查页；准确率要去点 `MihoProbe Accuracy Check`。

## 准确率怎么验收

解析准确率只用 manifest 验收，不要扫整个历史目录：

```powershell
dist\MihoProbe.exe replay --no-open
dist\MihoProbe.exe check --no-open
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

如果 `data\probes\replay_manifest.json` 还没准备好，`dist\MihoProbe.exe check --open` 会打开“准确率验收缺少样例清单”说明页。那不是 OCR 失败，只是缺固定验收样例。页面会同时显示当前检测到几张 `figs\` 分享图、几个 parsed JSON、几个 expected JSON，并告诉你下一步是先跑 `update`、补 expected，还是只差写 manifest。

如果怀疑失败点在角色/音擎评级，先跑 `dist\MihoProbe.exe rank-check --no-open`。评级不是按中文识别，它只看角色头像左上角和音擎右侧的 A/S 艺术字区域；这个命令不会重新 OCR。

通过口径：

- 3 张以上图平均通过率达标。
- 每张图不能低于门槛。
- 角色或音擎不能全错还通过。
- 驱动盘主词条和副词条不能全缺还通过。

强制全量重扫图片时才加：

```powershell
dist\MihoProbe.exe fresh --rescan-all
```

## 当前能做和不能做

能做：

- 从官方分享图或已有 parsed JSON 生成本地 Dashboard。
- `dist\MihoProbe.exe app-export` 生成米游社官方分享图路线、readiness gates 和校准命令包，当前不自动点击。
- `dist\MihoProbe.exe update` 处理 `figs/` 中新增或变更的官方分享图。
- `dist\MihoProbe.exe plan-update` 只重算高难、Tier / 保值观察、行动卡和队伍卡。
- `dist\MihoProbe.exe rank-check` 快速检查角色/音擎 A/S 评级区域。
- 用 replay manifest 做解析准确率回归。

不能做：

- 自动登录米游社。
- 读取或保存 cookie、token、stoken、ltoken。
- 控制游戏客户端。
- 自动联网刷新真实 Tier list 或高难出场率。
- 提交真实分享图、UID、OCR 原始结果或 `data/probes/` 产物。

## Codex / GPT 审查流

右侧 GPT 负责出方案和挑代码缺陷，Codex 负责落地、测试和推送。不要再临时摸索聊天流程，直接生成固定审查包：

```powershell
dist\MihoProbe.exe ask-gpt `
  --focus "本轮要推进的用户可见结果" `
  --evidence "关键命令或页面现象" `
  --changed-file "path/to/file.py: 改了什么" `
  --copy
```

完成一刀后，让 GPT 继续挑下一刀，用进展同步包：

```powershell
dist\MihoProbe.exe ask-gpt `
  --mode progress `
  --focus "本轮已完成，继续找 P0/P1" `
  --completed "EXE update 缺 OCR 依赖时 1 秒内退出 5" `
  --commit "2628cf6 Gate frozen update on OCR dependency" `
  --evidence "python -m unittest discover -s tests -p test*.py：264 OK" `
  --copy
```

`--copy` 会尽量把审查包放进剪贴板，你直接粘贴到右侧 GPT。若系统剪贴板被占用，工具会改写 `data\probes\demo\gpt_review_prompt.md`，打开这个文件复制即可。不要再让 Codex 反复探索 ChatGPT 页面。`dist\MihoProbe.exe gpt-review` 是同一个入口。还没构建 EXE 时，用 `python tools/probes/build_gpt_review_prompt.py`，参数相同。

协议说明见 `docs/notes/codex-gpt-adversarial-loop.md`。

## 开发入口

主 README 只放用户入口，细节去这里：

- Probe 命令细节：`tools/probes/README.md`
- GPT 审查包生成器：`tools/probes/build_gpt_review_prompt.py`
- Replay batch 验收：`tools/probes/run_export_replay_batch.py`
- 单图解析复核：`tools/probes/review_export_image.py`
- 技术栈边界：`docs/adr/0001-tech-stack-selection.md`、`docs/adr/0002-mvp-boundary-and-module-layering.md`、`docs/adr/0003-local-data-model-and-snapshot-strategy.md`
- 米游社 APP 探针边界：`docs/spikes/0001-miyoushe-app-feasibility.md`
- 分享图解析记录：`docs/notes/share-image-parsing-result.md`

永远不要提交真实账号数据、登录态文件、数据库文件、`.env`、真实图片或 `data/probes/` 探针产物。
