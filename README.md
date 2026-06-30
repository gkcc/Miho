# Miho

Miho 是一个本地优先的米哈游练度更新与规划工具。最终想做成一个桌面软件：

1. 米游社 APP 已打开且已登录时，一键按既定流程保存官方分享图。
2. 本地解析练度、保留复核证据，并用 Dashboard 展示。
3. 更新高难、Tier、保值观察和已有 box，给出“优先练高价值角色，顺手拿奖励”的配队建议。

现在还在 probe / demo 阶段，不是完整 Tauri 桌面应用。它不会自动登录，不读取 cookie/token，不控制游戏客户端，也不会把 OCR 结果直接写入正式数据库。

## 我只想像软件一样用

先这样用，第一次只做两步：

```powershell
scripts\build_miho_probe_exe.bat
scripts\install_miho_demo_shortcut.bat
```

以后日常点桌面图标即可。最重要的一句：

**只看界面点 `MihoProbe`；识别新分享图才点 `MihoProbe Update`。不要先跑 OCR，也不要先点 Fresh OCR。**

如果你只是验收“这个工具现在长什么样”，点 `MihoProbe`。第一次没有缓存时，它会打开初次启动页，不是报错。

## 点哪个图标

| 目标 | 图标 / 命令 | 说明 |
| --- | --- | --- |
| 看软件界面 | `MihoProbe` 或 `dist\MihoProbe.exe` | 打开缓存 Dashboard，不跑 OCR。 |
| 一键更新练度 | `MihoProbe Update` 或 `dist\MihoProbe.exe update` | 只处理 `figs\` 里的官方分享图。 |
| 查看 APP 导出路线 | `MihoProbe App Export Workflow` 或 `dist\MihoProbe.exe app-export` | 生成官方分享图路线、readiness gates 和校准命令，不自动点击。 |
| 更新高难配队 | `MihoProbe Plan Update` 或 `dist\MihoProbe.exe plan-update` | 只重算本地高难、Tier / 保值观察、行动卡和队伍卡。 |
| 排查 A/S 评级 | `MihoProbe Rank Check` 或 `dist\MihoProbe.exe rank-check` | 不跑 OCR，只看头像左上角和音擎评级区域的艺术字。 |
| 准确率验收 | `MihoProbe Accuracy Check` 或 `dist\MihoProbe.exe check --no-open` | 用 expected diff 回放，不重新 OCR。 |
| 开发慢路径 | `MihoProbe Fresh OCR` 或 `dist\MihoProbe.exe fresh` | 会加载 PaddleOCR，日常不要先点。 |

`app-export` 不是“自动导出已可用”的按钮。它当前只告诉你：米游社官方分享图应该怎么走、哪些步骤还需要校准、下一条安全命令是什么。

## Dashboard 怎么看

打开页面先看第一屏：

- `当前结论`：现在能不能用本地建议。
- `下一步`：该刷新数据、复核字段、人工应用，还是可以看队伍建议。
- `待确认快照`：OCR / 解析候选，人工确认前不算已拥有练度。

颜色只记一句：**绿色才是可继续，黄色先复核，红色先处理数据一致性。**

如果页面说“缺少运行清单”“待复核”“解析失败”，不要按配队行动。先处理页面给出的阻断原因。

## 更新和验收

把米游社官方分享图放进 `figs\` 后：

```powershell
dist\MihoProbe.exe update
```

如果 frozen EXE 缺 PaddleOCR，它会快速失败并给出 Python fallback，不会假装更新成功。

准确率只用 manifest 验收，不要扫整个历史目录：

```powershell
dist\MihoProbe.exe check --no-open
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

如果 manifest 还没准备好，`MihoProbe Accuracy Check` 会打开“准确率验收缺少样例清单”说明页，告诉你下一步是先跑 update、补 expected，还是只差写 manifest。

如果怀疑失败点在评级，先跑：

```powershell
dist\MihoProbe.exe rank-check --no-open
```

强制重扫旧图时才用：

```powershell
dist\MihoProbe.exe update --rescan-all --open
```

## 当前边界

能做：

- 从官方分享图或已有 parsed JSON 生成本地 Dashboard。
- 生成米游社官方分享图工作流、校准命令和人工复核路线。
- 对 `figs\` 中新增或变更的分享图做本地解析。
- 用 replay manifest 做解析准确率回归。
- 本地重算高难、Tier / 保值观察、行动卡和队伍卡。

不能做：

- 自动登录米游社。
- 读取或保存 cookie、token、stoken、ltoken。
- 控制游戏客户端。
- 自动联网刷新真实 Tier list 或高难出场率。
- 提交真实分享图、UID、OCR 原始结果或 `data/probes\` 产物。

## 开发协作

右侧 GPT 负责出方案和挑 P0/P1 风险，Codex 负责实现、测试、提交和推送。不要再让 Codex 反复探索右侧 ChatGPT 页面。

固定入口：

- `dist\MihoProbe.exe ask-gpt --focus "本轮要审的问题" --copy`
- `dist\MihoProbe.exe gpt-review --mode progress --focus "本轮已完成，继续找 P0/P1" --copy`

剪贴板不可用时，工具会写 `data\probes\demo\gpt_review_prompt.md`，手动复制给右侧 GPT 即可。协议细节在 `docs/notes/codex-gpt-adversarial-loop.md`。

## 详细资料

- 构建 EXE：`scripts/build_miho_probe_exe.bat`、`scripts/build_miho_probe_exe.ps1`、`packaging/MihoProbe.spec`
- 安装桌面入口：`scripts/install_miho_demo_shortcut.bat`
- EXE-first 兼容脚本入口：`scripts/run_miho_demo.bat`。如果 `dist\MihoProbe.exe` 不存在，它会提示先构建，不会自动掉进慢 OCR 脚本。
- Probe 命令细节：`tools/probes/README.md`
- GPT 审查包生成器：`tools/probes/build_gpt_review_prompt.py`
- Replay batch 验收：`tools/probes/run_export_replay_batch.py`
- 单图解析复核：`tools/probes/review_export_image.py`
- 技术边界：`docs/adr/0001-tech-stack-selection.md`、`docs/adr/0002-mvp-boundary-and-module-layering.md`、`docs/adr/0003-local-data-model-and-snapshot-strategy.md`
- 米游社 APP 探针边界：`docs/spikes/0001-miyoushe-app-feasibility.md`
- 分享图解析记录：`docs/notes/share-image-parsing-result.md`

永远不要提交真实账号数据、登录态文件、数据库文件、`.env`、真实图片或 `data/probes\` 探针产物。
