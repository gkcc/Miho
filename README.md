# Miho

Miho 是一个本地优先的米哈游练度更新与规划工具。最终想做成一个桌面软件：

1. 米游社 APP 已打开且已登录时，一键按既定流程保存官方分享图。
2. 本地解析练度、保留复核证据，并用 Dashboard 展示。
3. 更新高难、Tier、保值观察和已有 box，给出“优先练高价值角色，顺手拿奖励”的配队建议。

现在还在 probe / demo 阶段，不是完整 Tauri 桌面应用。它不会自动登录，不读取 cookie/token，不控制游戏客户端，也不会把图片识别结果直接写入正式数据库。

## 我只想像软件一样用

先这样用，第一次只做两步：

```powershell
scripts\build_miho_probe_exe.bat
scripts\install_miho_demo_shortcut.bat
```

以后日常点桌面图标即可。最重要的一句：

**只看界面点 `MihoProbe`；识别新分享图才点 `MihoProbe Update`。不要先跑图片识别，也不要先点开发慢路径。**

如果你只是验收“这个工具现在长什么样”，点 `MihoProbe`。第一次没有缓存时，它会打开初次启动页，不是报错。

## 卡住时先看这里

- 双击 `MihoProbe` 或运行 `scripts\run_miho_demo.bat`：只打开本地 Dashboard，不跑图片识别，正常应很快有浏览器页面。
- 看到窗口提示 `Opening cached Dashboard only. Image recognition will NOT run.`：说明没有进入慢图片识别。
- 只有 `MihoProbe Update`、`MihoProbe Fresh OCR`、`dist\MihoProbe.exe update`、`dist\MihoProbe.exe fresh` 才会加载图片识别模型。
- 如果你等了 30 秒还没有页面，先跑 `dist\MihoProbe.exe dashboard --no-open`。它应该打印 `dashboard_html: ...\index.html`；然后直接打开那个 HTML。
- 不要用“跑了很久”判断准确率。准确率只看 `MihoProbe Accuracy Check` 或 `dist\MihoProbe.exe check --no-open`。

## 当前验收怎么看

| 要验收什么 | 看哪里 | 通过口径 |
| --- | --- | --- |
| 软件入口是否能打开 | `MihoProbe` / `dist\MihoProbe.exe` | 浏览器打开 Dashboard 或初次启动页；不启动图片识别。 |
| A/S 评级是否稳 | `MihoProbe Rank Check` | `ok_region_count` 覆盖所有角色/音擎评级区域，报告有 crop 和颜色/形状证据。 |
| 分享图解析准确率 | `MihoProbe Accuracy Check` | manifest 控制的 expected diff 达标，不扫历史 parsed 目录。 |
| APP 一键导出准备度 | `MihoProbe App Export Workflow` -> `MihoProbe App Export Calibrate` | 有工作流页、网格截图、待填坐标清单；默认不点击。 |
| 配队/规划页面是否可信 | Dashboard 顶部 `当前结论` 和 `下一步` | 绿色继续；黄色先复核；红色先处理数据一致性。 |

## 点哪个图标

| 目标 | 图标 / 命令 | 说明 |
| --- | --- | --- |
| 看软件界面 | `MihoProbe` 或 `dist\MihoProbe.exe` | 打开缓存 Dashboard，不跑图片识别。 |
| 一键更新练度 | `MihoProbe Update` 或 `dist\MihoProbe.exe update` | 只处理 `figs\` 里的官方分享图。 |
| 查看 APP 导出路线 | `MihoProbe App Export Workflow` 或 `dist\MihoProbe.exe app-export` | 生成官方分享图路线、readiness gates 和校准命令，不自动点击。 |
| 生成 APP 坐标网格 | `dist\MihoProbe.exe app-export-calibrate` | 捕获米游社窗口网格截图，显示每一步需要填的 x/y。 |
| 校准 APP 导出点击 | `dist\MihoProbe.exe app-export-run --no-open` | 读取校准清单，默认输出预检路线图；缺坐标会明确提示，不会点击。 |
| 更新高难配队 | `MihoProbe Plan Update` 或 `dist\MihoProbe.exe plan-update` | 重算高难、Tier / 保值观察、行动卡和队伍卡；默认不联网。 |
| 检查 box 输入 | `MihoProbe Box Status` 或 `dist\MihoProbe.exe box-status` | 只读检查 box 图、公开 meta、roster probe 和价值报告，给出下一步命令。 |
| 识别 box 总览 | `dist\MihoProbe.exe box-roster --image ... --no-open` | 从官方 box 总览图生成脱敏 roster probe；人工确认前不算 accepted roster。 |
| 生成 box 价值报告 | `dist\MihoProbe.exe box-value --box-image ... --meta-snapshot ...` | 用本地 box 图或 roster JSON 加公开 Prydwen meta 生成价值报告。 |
| 排查 A/S 评级 | `MihoProbe Rank Check` 或 `dist\MihoProbe.exe rank-check` | 不跑图片识别，只看头像左上角和音擎评级区域的艺术字。 |
| 准确率验收 | `MihoProbe Accuracy Check` 或 `dist\MihoProbe.exe check --no-open` | 用人工对照答案回放，不重新图片识别。 |
| 开发慢路径 | `MihoProbe Fresh OCR` 或 `dist\MihoProbe.exe fresh` | 会加载图片识别模型，日常不要先点。 |

`app-export` 不是“自动导出已可用”的按钮。它会生成工作流页和 `miyoushe_app_export_calibration_template.json`。下一步先跑 `dist\MihoProbe.exe app-export-calibrate` 生成米游社窗口网格截图；把坐标填进清单后，再跑 `dist\MihoProbe.exe app-export-run --no-open`。这个命令默认先给预检路线图：当前状态、下一步命令、推荐路线和安全边界。只有当 dry-run 报告显示坐标已就绪，并且你逐步确认每个坐标都是米游社官方 UI 后，才允许加 `--execute --confirm-official-ui`。这仍然不会登录、不会读 token/cookie、不会控制游戏客户端。

## Dashboard 怎么看

打开页面先看第一屏：

- `当前结论`：现在能不能用本地建议。
- `下一步`：该刷新数据、复核字段、人工应用，还是可以看队伍建议。
- `待确认快照`：图片识别 / 解析候选，人工确认前不算已拥有练度。

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
```

如果 manifest 还没准备好，`MihoProbe Accuracy Check` 会打开“准确率验收缺少样例清单”说明页，告诉你下一步是先跑 update、补 expected，还是只差写 manifest。

底层开发调字段时才直接跑 replay 脚本：`python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json`。

如果怀疑失败点在评级，先跑：

```powershell
dist\MihoProbe.exe rank-check --no-open
```

如果想从米游社官方 box 总览图看账号内代理人价值，先把 box 总览图放到 `data\probes\exported_images\`，再跑 `dist\MihoProbe.exe box-status` 看本地缺什么。`box-status` 会输出 `box_status_freshness`：新 roster 会用源图 hash 对齐最新 box 图，旧 roster 才会退回 mtime 判断；还会输出 `box_status_roster_quality`、`box_status_roster_needs_review_count`、`box_status_review_gate`、`box_status_roster_review_markdown` 和 `box_status_roster_review_markdown_status`，用于区分“可跑 probe 价值报告”“能否进入 accepted roster”以及“该看哪份 Markdown 复核”。如果复核 Markdown 缺失或旧于 roster JSON，即使 roster 质量检查为 ok，也不能进入 accepted roster。输入齐了以后再跑：`dist\MihoProbe.exe box-value --box-image data\probes\exported_images\zzz_box.png --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json`。

这条链路只读本地图片和公开 Prydwen 数据；不会登录、不会读 cookie/token、不会写正式数据库。图片识别出的 roster 仍是 probe 草案，人工确认前不能进入 accepted roster。

强制重扫旧图时才用：

```powershell
dist\MihoProbe.exe update --rescan-all --open
```

`plan-update` 默认不联网。只有显式传入 `--target-source-manifest`，且 manifest 里写了公开 http(s) URL 时，它才会访问这些公开页面生成本地高难目标；它仍然不读取账号、cookie、token，也不会联网刷新 Tier list 或出场率。

## 当前边界

能做：

- 从官方分享图或已有 parsed JSON 生成本地 Dashboard。
- 生成米游社官方分享图工作流、校准命令和人工复核路线。
- 对 `figs\` 中新增或变更的分享图做本地解析。
- 用 replay manifest 做解析准确率回归。
- 默认本地重算高难、Tier / 保值观察、行动卡和队伍卡；显式公开 source manifest 只允许访问公开页面。

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
- `dist\MihoProbe.exe ask-gpt --mode progress --focus "本轮已完成，继续找 P0/P1" --copy`

剪贴板不可用时，工具会写 `data\probes\demo\gpt_review_prompt.md`，手动复制给右侧 GPT 即可。协议细节在 `docs/notes/codex-gpt-adversarial-loop.md`。

## 详细资料

- 构建 EXE：`scripts/build_miho_probe_exe.bat`、`scripts/build_miho_probe_exe.ps1`、`packaging/MihoProbe.spec`
- 安装桌面入口：`scripts/install_miho_demo_shortcut.bat`
- EXE-first 兼容脚本入口：`scripts/run_miho_demo.bat`。如果 `dist\MihoProbe.exe` 不存在，它会提示先构建，不会自动掉进慢图片识别脚本。
- Probe 命令细节：`tools/probes/README.md`
- GPT 审查包生成器：`tools/probes/build_gpt_review_prompt.py`
- Replay batch 验收：`tools/probes/run_export_replay_batch.py`
- 单图解析复核：`tools/probes/review_export_image.py`
- 技术边界：`docs/adr/0001-tech-stack-selection.md`、`docs/adr/0002-mvp-boundary-and-module-layering.md`、`docs/adr/0003-local-data-model-and-snapshot-strategy.md`
- 米游社 APP 探针边界：`docs/spikes/0001-miyoushe-app-feasibility.md`
- 分享图解析记录：`docs/notes/share-image-parsing-result.md`

永远不要提交真实账号数据、登录态文件、数据库文件、`.env`、真实图片或 `data/probes\` 探针产物。
