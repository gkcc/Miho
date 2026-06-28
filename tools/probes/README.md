# 米游社探针工具

这些工具只用于判断米游社 APP 是否存在可安全研究的数据来源。它们不是正式采集器，不写正式数据库，不自动登录，不输入账号密码，不抓包，不读取 cookie/token/session 内容。

所有输出写入 `data/probes/`，该目录必须保持在 `.gitignore` 中。

## 推荐验证顺序

1. 用户手动导出一张米游社官方分享图。
2. 将图片保存到 `data/probes/exported_images/`。
3. 优先运行一键验收：

```powershell
python tools/probes/review_export_image.py --image "data/probes/exported_images/xxx.jpg" --open
```

4. 查看 HTML 顶部的 `PASS` / `NEEDS_REVIEW` / `FAIL`。
5. 只有 `PASS` 才能继续 fixture / 导入原型；`NEEDS_REVIEW` 要人工确认；`FAIL` 继续修 OCR、版面解析或字段抽取。
6. 如果 OCR 质量差，优先尝试 PaddleOCR，或安装 Tesseract `chi_sim` 语言包。
7. 如果分享图字段不足，再研究多图组合、截图 RPA 或另开 ADR 评估底层 API。

## 官方导出/分享图路线

这是当前最高优先级路线。米游社 APP 是官方社区和数据工具，如果用户本地 APP 已登录，probe 可以操作官方 UI 来触发分享图或导出图。

允许：

* 点击官方 UI。
* 滚动官方页面。
* 等待页面加载。
* 保存官方分享图。
* 对分享图做 OCR / 图像识别 / 版面解析。
* 输出本地 probe JSON / Markdown。

禁止：

* 不自动登录。
* 不输入账号密码。
* 不读取 cookie/token/stoken/ltoken。
* 不抓包。
* 不绕过验证码或风控。
* 不控制游戏客户端。
* 不写正式数据库。
* 不提交真实导出图或 `data/probes/` 结果。

### RPA probe

manual-page 模式要求用户先手动进入角色详情页或分享图入口附近。`--dry-run` 只找按钮，不触发点击。

```powershell
python tools/probes/miyoushe_export_image_probe.py --game zzz --mode manual-page --window-title 米游社 --dry-run
python tools/probes/miyoushe_export_image_probe.py --game zzz --mode manual-page --window-title 米游社
```

assisted-rpa 模式目前只输出步骤框架，不要求完整跑通。

```powershell
python tools/probes/miyoushe_export_image_probe.py --game hsr --mode assisted-rpa --window-title 米游社 --dry-run
```

输出：

* 操作日志；
* 是否找到窗口；
* 是否找到分享 / 导出按钮；
* 是否成功触发导出；
* 是否发现新图片文件；
* 图片路径；
* 错误原因。

默认图片观察目录：

```text
data/probes/exported_images/
```

### RPA 坐标准备 probe

如果官方分享按钮无法通过 UIA 直接定位，可以先用窗口截图和相对坐标 dry-run 做标定。截图可能包含账号可见信息，只能保存在 `data/probes/`，不得提交。

```powershell
python tools/probes/window_screenshot_probe.py --window-title 米游社 --dry-run
python tools/probes/window_screenshot_probe.py --window-title 米游社 --grid-size 100
python tools/probes/click_relative_probe.py --window-title 米游社 --x 640 --y 360
```

`click_relative_probe.py` 默认只输出窗口相对坐标和绝对坐标，不点击。真实点击只用于 P0.6 官方 UI 探针，且必须显式加：

```powershell
python tools/probes/click_relative_probe.py --window-title 米游社 --x 640 --y 360 --execute --confirm-official-ui
```

禁止用该 probe 自动登录、处理验证码、读取 cookie/token、抓包或控制游戏客户端。

### Parse probe

对官方导出 / 分享图做 OCR 和字段分类草案。

```powershell
python tools/probes/export_image_parse_probe.py --image "data/probes/exported_images/example.png" --game zzz --layout zzz-agent-card --engine auto
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine paddle --lang chi_sim+eng --write-crops
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine rapidocr --write-crops
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine tesseract --lang eng
python tools/probes/export_image_parse_probe.py --image "data/probes/exported_images/example.png" --game zzz --layout zzz-agent-card --engine none
```

真实中文分享图优先显式使用 `--engine paddle`。默认 `--engine auto` 会先尝试 PaddleOCR，再降级到 Tesseract；如果 PaddleOCR 不可用，工具会提示安装。`--engine rapidocr` 是 Paddle 不达标后的可选本地 OCR fallback。`--engine tesseract --lang eng` 只适合固定区域数字调试，不可作为可导入解析结果。`--engine none` 可用于只验证图片加载、布局区域和 JSON/Markdown 输出结构。

新增参数：

* `--engine auto|tesseract|paddle|rapidocr|none`：默认 `auto`；`auto` 优先 PaddleOCR，失败后尝试 Tesseract。
* `--game zzz|hsr`：当前固定区域解析只支持 `zzz`。
* `--layout full|zzz-agent-card`：默认 `full`；`--game zzz --layout zzz-agent-card` 会按绝区零分享图固定区域裁剪并分别 OCR。
* `--write-crops`：把关键验收字段的裁剪图写到 `data/probes/crops/`，用于肉眼确认字段框是否准确。
* `--crop-output-dir`：自定义 crop 输出目录。

输出目录：

```text
data/probes/parsed/
```

输出重点：

* 识别到的文本块；
* 文本位置；
* 可能的字段分类；
* 是否匹配 ADR-0003 的 `Character`、`CharacterBuildSnapshot`、`Equipment`、`SkillOrTrace`、`ArtifactOrDriveDisc`；
* `extracted_draft` 字段草案；
* `coverage_summary` 覆盖率摘要；
* confidence / uncertain。

如果本地没有 OCR 依赖，工具会输出清晰提示。可选依赖：

```powershell
python -m pip install paddleocr
python -m pip install rapidocr-onnxruntime
python -m pip install pillow pytesseract
```

Tesseract 程序本体和中文语言包需要单独安装到本机。

### P0.7 HTML 验收页

P0.7 的目标是让用户肉眼验收分享图解析结果是否可靠。HTML 只是验收工具，不代表解析成功。

日常使用优先一条命令完成解析、HTML、overlay，并可选自动打开浏览器：

```powershell
python tools/probes/review_export_image.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --engine paddle --write-crops --open
```

输出会包含：

* `review_status`
* `coverage_level`
* parsed JSON / Markdown 路径
* review HTML 路径
* overlay PNG 路径
* field crop 数量
* 可手动打开的 `start ...` 命令

如果要把 `FAIL` 当作命令失败码，例如用于自动化回归，可以加：

```powershell
python tools/probes/review_export_image.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --strict-exit
```

拆开调试时，先解析官方分享图：

```powershell
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine paddle --write-crops
```

再用解析 JSON 生成本地 HTML 验收页和 overlay 图片：

```powershell
python tools/probes/render_export_review.py --json "data/probes/parsed/xxx.json"
```

打开验收页：

```powershell
start data/probes/parsed/xxx_review.html
```

输出：

* `data/probes/parsed/xxx_review.html`
* `data/probes/parsed/xxx_overlay.png`

HTML 验收页包含：

* 原始分享图；
* 解析区域 overlay；
* `extracted_draft` 字段卡片；
* `coverage_summary`；
* 总体验收状态：`PASS` / `NEEDS_REVIEW` / `FAIL`；
* 缺失字段和不确定字段；
* `invalid_candidate` 泛词字段；
* 下一步建议。

验收标准：

* `PASS`：才允许进入后续 fixture / 导入原型；
* `NEEDS_REVIEW`：必须人工确认，不能直接导入；
* `FAIL`：说明 OCR / 版面解析 / 字段抽取仍需修复；
* `coverage_level` 至少为 `medium` 只是最低观察条件，不等于解析成功；
* 角色等级正确；
* 核心属性至少 4 个正确；
* 六个技能等级至少 5 个正确；
* 音擎等级正确；
* 6 个驱动盘区域框基本对齐。

如果 `character.name`、`character.rank`、`drive_disc_main_stats` 或 `drive_disc_sub_stats` 缺失，不得称为“字段覆盖较完整”。如果 `equipment.name` 是 `驱动` / `音擎` / `装备` 这类泛词，或驱动盘套装识别成 `命中` / `共命中`，必须视为 `invalid_candidate`。

如果 JSON 里的 `metadata.input_image` 已移动或被脱敏，可以显式指定原图：

```powershell
python tools/probes/render_export_review.py --json "data/probes/parsed/xxx.json" --image "C:\Users\zy958\Downloads\1782409396884.jpg"
```

验收页仍是 probe 输出，不是正式采集结果。不要提交 `data/probes/`、真实图片或 HTML/overlay 输出。

### Expected diff

人工确认一份 expected JSON 后，可以用 diff 工具验证解析结果。该工具会输出 JSON 和 Markdown diff；只要任一关键字段不一致，整体就是 `FAIL`。

```powershell
python tools/probes/make_expected_template.py --parsed "data/probes/parsed/xxx.json" --output "data/probes/expected/xxx_expected.json"
python tools/probes/evaluate_export_parse.py --parsed "data/probes/parsed/xxx.json" --expected "data/probes/expected/xxx_expected.json"
```

`make_expected_template.py` 只生成验收字段空模板，不包含 OCR 文本块、layout、overlay 或其他噪声。人工填完后，`evaluate_export_parse.py` 会输出 `pass_rate`、失败字段分组、`blockers` 和 `next_action`。默认会把纯数字文本做宽松比较，例如 `08` 与 `8` 视为相等；如果要严格比较前导零，可加 `--strict-leading-zero`。百分号字段必须保留 `%`，`45.8` 不会等于 `45.8%`。

至少比较：

* `character.name` / `character.level` / `character.rank`
* 核心属性：`hp` / `atk` / `def` / `impact` / `crit_rate` / `crit_dmg` / `anomaly_mastery` / `anomaly_proficiency` / `pen` / `energy_regen` / `physical_dmg_bonus`
* 六个技能等级
* 音擎名称、等级、评级
* 六个驱动盘等级、主词条、副词条

### P1.0 标准化导入原型

P1.0 把 `export_image_parse_probe.py` 产出的 parsed JSON / `extracted_draft` 转换成项目内部标准化角色快照 JSON。该输出只是导入候选，不是正式数据库记录；当前阶段不写 SQLite，不自动导入，仍必须人工确认。

单个 parsed JSON 标准化：

```powershell
python tools/probes/normalize_export_parse.py --parsed "data/probes/parsed/xxx.json"
```

输出默认写入：

```text
data/probes/normalized/<stem>_normalized.json
data/probes/normalized/<stem>_normalized.md
```

也可以指定输出目录：

```powershell
python tools/probes/normalize_export_parse.py --parsed "data/probes/parsed/xxx.json" --output-dir "data/probes/normalized/manual_check"
```

标准化输出会保留每个字段的 `value`、`status`、`uncertain`、`evidence` 和 `source_region`。P0.9 阶段暂时归入 `physical_dmg_bonus` 的物理 / 元素伤害加成，在 P1.0 标准化中统一映射为 `build_snapshot.stats.damage_bonus`，后续再细分元素类型。

批量标准化：

```powershell
python tools/probes/normalize_export_batch.py --parsed "data/probes/parsed/a.json" --parsed "data/probes/parsed/b.json"
python tools/probes/normalize_export_batch.py --manifest "data/probes/normalized_manifest.json"
```

batch summary 默认写入：

```text
data/probes/normalized/batch_summary.json
data/probes/normalized/batch_summary.md
```

比较两个标准化快照：

```powershell
python tools/probes/diff_normalized_snapshots.py --old "old_normalized.json" --new "new_normalized.json"
```

diff 只把字段 `value` 的变化当作养成值变化，同时会记录 `status` / `uncertain` 的变化。只要旧值或新值不可信，diff 项会标记 `requires_review=true`，不得当作正式养成变化直接入库。

质量门禁：

* `can_import_without_review` 当前始终为 `false`；
* `requires_manual_review` 当前始终为 `true`；
* `quality.blockers` 会列出角色名、音擎、驱动盘、`invalid_candidate`、低 coverage 或 `review_status=FAIL` 等阻断项；
* normalized JSON 可以作为后续 importer prototype 的输入候选，但不是正式采集结果。

### P1.1 本地一键体验台

P1.1 提供一个本地 demo 入口，把官方分享图解析、expected diff、normalized snapshot 和总览 Dashboard 串起来。它不是正式 App，不初始化 Tauri，不写 SQLite，不自动导入，不提交真实图片或 `data/probes/` 输出。

成品体验优先用双击脚本：

```powershell
scripts/run_miho_demo.bat
```

PowerShell 方式：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_miho_demo.ps1
```

Python 方式：

```powershell
python tools/probes/run_demo_pipeline.py --images-dir figs --open
python tools/probes/run_demo_pipeline.py --parsed-dir data/probes/parsed --latest-only --open
python tools/probes/run_demo_pipeline.py --manifest data/probes/demo_manifest.json --open
python tools/probes/run_demo_pipeline.py --images-dir figs --targets data/probes/targets/endgame_targets.json --open
python tools/probes/run_demo_pipeline.py --images-dir figs --target-source-manifest data/probes/targets/endgame_sources_manifest.json --open
python tools/probes/run_demo_pipeline.py --images-dir figs --targets data/probes/targets/endgame_targets.json --daily-stamina 240 --horizon-days 7 --open
python tools/probes/run_demo_pipeline.py --images-dir figs --targets data/probes/targets/endgame_targets.json --character-catalog data/probes/catalog/zzz_characters.json --open
python tools/probes/run_demo_pipeline.py --images-dir figs --new-only --state-file data/probes/demo/update_state.json --targets data/probes/targets/endgame_targets.json --open
python tools/probes/run_demo_pipeline.py --parsed-dir data/probes/parsed --latest-only --history-dir data/probes/demo/snapshot_history --open
```

默认输入目录是本地 `figs/`，该目录只放用户手动保存的官方分享图，不提交 Git。默认输出：

```text
data/probes/demo/demo_summary.json
data/probes/demo/index.html
data/probes/demo/snapshot_history/index.json
```

`index.html` 是单文件静态 Dashboard，可以直接双击打开。Dashboard 会展示：

* 图片 / parsed case 数；
* 当前输入模式：`OCR fresh image mode`、`parsed replay mode` 或 `manifest controlled mode`；
* parsed-dir 模式下发现了多少历史 parsed JSON、实际使用了多少；
* review 状态；
* expected diff 平均 pass_rate；
* normalized snapshot 数；
* 需要人工确认的 case 数；
* Demo 状态、Parse 状态、Expected 状态、Normalized 状态和 Import 状态；
* 每张图的角色、音擎、expected JSON 文件名、review HTML、parsed JSON、normalized JSON/MD、expected diff 和 blockers。
* 如果提供 `--targets`，还会展示培养优先级候选和 planner 报告链接。
* 如果提供 `--character-catalog`，planner 会用本地角色标签补全做目标弱点 / 机制匹配。
* 如果提供 `--target-source-manifest`，会先用公开 URL 或本地保存的公开页面刷新 `endgame_targets.json`，再交给 planner。
* 如果提供 `--daily-stamina` / `--horizon-days`，planner 会把优先级转换成今日和规划窗口内的体力投入建议；默认按 240 / 7 天估算。
* image mode 会维护本地 `update_state.json`，记录分享图 sha256 和上次处理结果。
* 如果提供 `--new-only`，只处理新增或内容变更的分享图，未变化图片会跳过。
* `update_state` summary 会展示本轮处理到的角色、对应图片、review 状态，以及被 `--new-only` 跳过的未变更图片。
* demo 会维护本地 `snapshot_history/index.json`，保存每个角色最近一次 normalized snapshot，并在下次同角色出现时生成相邻快照 diff。
* planner 会读取本轮 `snapshot_history` 上下文，给近期已有变化的角色一个小的连续投入提示，避免只看静态缺口。
* `snapshot_history` 仍是 probe 输出，不是正式数据库；它只用于观察“这次相对上次练度变化了什么”。

输入隔离：

* 成品体验用 `scripts/run_miho_demo.bat`，它走 `figs/` 的 fresh OCR image mode。
* 增量体验用 `--new-only --state-file data/probes/demo/update_state.json`，用于模拟“用户新增导出图后自动进入解析链路”。
* 终局目标刷新用 `--target-source-manifest data/probes/targets/endgame_sources_manifest.json`；manifest 只允许公开 http(s) URL 或本地保存的公开文本/HTML，不允许登录态、cookie、token 或私有地址。
* 长期演进体验用 `--history-dir data/probes/demo/snapshot_history` 固定历史目录；如果配合 `--clean-demo` 清空同一输出目录，默认历史也会被清空。
* `--parsed-dir` 是 replay 调试入口，会扫描目录中的历史 parsed JSON，可能包含旧失败结果。
* parsed replay 只想看每张源图最新结果时加 `--latest-only`。
* 想清空 demo 输出再跑时加 `--clean-demo`，该开关只允许清理 `data/probes/` 下的输出目录。
* 准确率验收必须用 manifest，例如 `data/probes/replay_manifest.json`；不要扫描整个 `data/probes/parsed` 来判断 P0.9 通过率。
* demo manifest 的每个 case 可以显式写 `expected`，Dashboard 会显示实际命中的 expected JSON 文件名，方便确认没有对错模板。
* Dashboard 的 `requires_review` 是人工确认安全门禁，不代表解析失败；真正失败看 `Parse FAIL`、`Expected FAIL`、`Normalized FAILED` 或 `Import BLOCKED`。
* 当前阶段始终不会自动导入正式数据库，即使 `Parse PASS` / `Normalized GENERATED` 也只表示可以进入人工复核。

P0.9 replay batch 验收命令：

```powershell
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

expected JSON 缺失时不会报错，Dashboard 会显示 `expected: missing` / `N/A`，并继续生成 normalized snapshot。要补 expected，可以先运行：

```powershell
python tools/probes/make_expected_template.py --parsed "data/probes/parsed/xxx.json" --output "data/probes/expected/xxx_expected.json"
```

CLI 壳：

```powershell
python tools/probes/miho_probe_cli.py demo --images-dir figs --open
python tools/probes/miho_probe_cli.py demo --images-dir figs --targets data/probes/targets/endgame_targets.json --open
python tools/probes/miho_probe_cli.py demo --images-dir figs --target-source-manifest data/probes/targets/endgame_sources_manifest.json --open
python tools/probes/miho_probe_cli.py demo --images-dir figs --targets data/probes/targets/endgame_targets.json --character-catalog data/probes/catalog/zzz_characters.json --open
python tools/probes/miho_probe_cli.py demo --images-dir figs --new-only --state-file data/probes/demo/update_state.json --targets data/probes/targets/endgame_targets.json --open
python tools/probes/miho_probe_cli.py demo --parsed-dir data/probes/parsed --latest-only --history-dir data/probes/demo/snapshot_history --open
python tools/probes/miho_probe_cli.py normalize --parsed data/probes/parsed/xxx.json
python tools/probes/miho_probe_cli.py diff --old old_normalized.json --new new_normalized.json
```

可选 EXE 壳：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_miho_probe_exe.ps1
```

该脚本使用 PyInstaller 构建 `MihoProbe.exe` 命令壳。P1.1 不要求把 PaddleOCR 完整打包进 EXE，真正 release 包是后续 P1.2+。

### P1.2 本地培养优先级 planner probe

P1.2 把 P1.0 的 normalized snapshot 和本地终局目标配置连起来，生成“先确认哪些数据、再投入哪些体力”的候选报告。它是 planner 消费端原型，不联网、不抓当前活动、不写 SQLite，不代表当前线上高难结论。

单角色：

```powershell
python tools/probes/plan_training_priorities.py `
  --snapshot "data/probes/normalized/xxx_normalized.json" `
  --targets "data/probes/targets/zzz_endgame_targets.json"
```

多角色 manifest：

```powershell
python tools/probes/plan_training_priorities.py `
  --snapshot-manifest "data/probes/planner/snapshots_manifest.json" `
  --targets "data/probes/targets/zzz_endgame_targets.json"
```

带长期演进上下文：

```powershell
python tools/probes/plan_training_priorities.py `
  --snapshot "data/probes/normalized/xxx_normalized.json" `
  --targets "data/probes/targets/zzz_endgame_targets.json" `
  --character-catalog "data/probes/catalog/zzz_characters.json" `
  --history-index "data/probes/demo/snapshot_history/index.json" `
  --daily-stamina 240 `
  --horizon-days 7
```

CLI 壳：

```powershell
python tools/probes/miho_probe_cli.py plan `
  --snapshot "data/probes/normalized/xxx_normalized.json" `
  --targets "data/probes/targets/zzz_endgame_targets.json" `
  --character-catalog "data/probes/catalog/zzz_characters.json" `
  --history-index "data/probes/demo/snapshot_history/index.json" `
  --daily-stamina 240 `
  --horizon-days 7
```

输出：

```text
data/probes/planner/training_priority_report.json
data/probes/planner/training_priority_report.md
```

报告中的 `resource_plan` 会包含：

* `budget`：每日体力、规划天数、总可用体力；
* `today`：今日优先投入项；
* `horizon`：规划窗口内可覆盖的投入项；
* `no_stamina_actions`：不消耗体力但应先做的人工确认或整理项；
* `overflow`：规划窗口内排不进去的候选项。

报告中的 `target_coverage` 会按当前 targets 反向汇总：

* `covered`：当前 normalized snapshots 中至少有一个角色命中该目标；
* `unmatched`：当前 box 暂无角色命中该目标的 preferred character、队伍模板或标签；
* `matched_characters`：命中的角色、匹配类型、匹配标签和分数。
* `catalog_candidates`：当前 snapshots 未覆盖该目标时，角色 catalog 中命中 preferred character、推荐队伍模板或标签接近的候选；这只提示“确认是否拥有 / 是否需要补录分享图 / 长期候选”，不能直接当作已拥有角色。
* `evidence`：来自 target intake 的来源标题、来源路径 / URL、内容 hash 和命中关键词摘要；Markdown 报告会渲染为“目标来源证据”。

如果 targets 来源是 fresh 的当前高难来源，且存在 `unmatched` 目标，planner 会给出 warning，提示当前 box 对该高难目标暂无匹配角色。
如果 `unmatched` 目标存在 catalog 候选，planner 会额外提示应先确认是否拥有或补录分享图。

报告中的 `coverage_gap_actions` 会把这类未覆盖目标转换成长期补洞动作：

* `confirm_ownership`：catalog 命中目标缺口，但 owned 状态未知，先确认是否拥有；
* `record_owned_snapshot`：catalog 标记已拥有，但当前 snapshots 没有可用练度快照，先补录官方分享图；
* `long_term_candidate`：catalog 标记未拥有，只能作为长期抽取或培养观察项。

这些动作默认 `uses_stamina=false`，不会进入 `resource_plan` 的体力分配；只有补录快照并进入当前 box 后，具体培养项才会被纳入体力预算。

报告中的 `target_source_status` 会把目标来源分成：

* `current`：fresh 的官方 / 公开高难来源，可作为当前高难候选输入；
* `stale`：来源已过期，训练动作会被降为低置信度；
* `local_draft`：本地 mock / 人工配置，只能用于体验链路和规则调试；
* `needs_freshness` / `unverified`：来源类型或 freshness 不足，不能当作当前高难事实。

只要 `current_endgame_ready=false`，planner 仍会输出候选项，但非数据确认类训练动作会被来源置信度限制，报告和 Dashboard 都会显示 warning。

目标匹配顺序：

* `preferred_characters` 精确命中；
* `recommended_team_templates[].preferred_characters` 命中；
* normalized snapshot 的 `combat_tags` / `character.tags` / `character.element` / `character.role` 与目标 `weakness_tags`、`mechanic_tags`、`preferred_tags`、`required_tags` 有交集。

第三种是给“当前高难弱点 / 机制标签 -> 角色长期培养候选”的衔接口，可由 `--character-catalog` 或人工确认后的 normalized snapshot 补充角色元素、定位和机制标签。

角色 catalog 是本地非敏感配置，不提交真实账号数据。最小格式：

```json
{
  "characters": [
    {
      "name": "星见雅",
      "aliases": ["Miyabi"],
      "element": "ice",
      "role": "attack",
      "combat_tags": ["anomaly", "slash"]
    }
  ]
}
```

targets JSON 是本地配置，后续可以由官方公告 / 官方活动页解析器生成。当前建议结构：

```json
{
  "game": "zzz",
  "source": {
    "type": "manual",
    "note": "本地人工配置，不代表当前线上高难"
  },
  "default_minimums": {
    "character_level": 60,
    "equipment_level": 60,
    "skill_level": 8,
    "drive_disc_level": 12,
    "stats": {
      "atk": 2000,
      "crit_rate": 45
    }
  },
  "targets": [
    {
      "goal_id": "zzz_shiyu_mock",
      "activity_name": "式舆防卫战",
      "target_tier": "稳定通关",
      "priority": "high",
      "preferred_characters": ["星见雅"],
      "minimums": {
        "skill_level": 9
      }
    }
  ]
}
```

报告会优先暴露 `requires_manual_review` 和 quality blockers。只要 normalized snapshot 来自 OCR 或存在 blocker，建议都只能作为人工确认前的候选，不能直接写正式数据库或自动生成最终养成计划。

### P1.3 公开高难目标 intake

P1.3 负责把公开网页或本地保存的官方 / 攻略文本整理成 planner 可消费的 targets JSON。它只访问公开 http(s) URL 或本地文本文件，不登录、不带 cookie、不读取 session、不抓包，也会拒绝 `file://`、localhost 和私网地址。

target intake 会记录来源 freshness：

* 公开 URL：按本次抓取时间记录为 fresh；
* 本地保存文件：按文件 mtime 计算 age；
* 默认 `max_source_age_hours=168`，可在 manifest 或命令行覆盖；
* stale 来源会继续输出 targets，但会进入 warnings，不能当作“当前高难挑战”事实。

target intake 也会记录轻量证据，方便审计但不保存网页全文：

* `sources[].content_sha256`：公开 URL / 本地文本内容的 hash，用于确认来源内容是否变化；
* `sources[].matched_aliases`：活动名、弱点标签、机制标签分别命中了哪些关键词；
* `targets[].evidence.source_ref`、`title`、`excerpt`、`matched_aliases`：planner 解释目标标签时使用的来源证据。

从本地保存的网页 / 文本生成 targets：

```powershell
python tools/probes/prepare_endgame_targets.py `
  --input "data/probes/targets/saved_endgame_page.html" `
  --game zzz `
  --source-type official_snapshot `
  --target-tier "稳定通关" `
  --priority high `
  --preferred-character "星见雅" `
  --stat atk=2000 `
  --max-source-age-hours 72
```

从公开网页生成 targets：

```powershell
python tools/probes/prepare_endgame_targets.py `
  --url "https://example.com/public-endgame-news" `
  --game zzz `
  --source-type public_web_snapshot `
  --preferred-character "星见雅"
```

用 manifest 管理多个来源：

```powershell
python tools/probes/prepare_endgame_targets.py --manifest "data/probes/targets/endgame_sources_manifest.json"
```

CLI 壳：

```powershell
python tools/probes/miho_probe_cli.py targets `
  --input "data/probes/targets/saved_endgame_page.html" `
  --game zzz `
  --preferred-character "星见雅"
```

输出：

```text
data/probes/targets/endgame_targets.json
```

命令行会输出 `freshness_level` 和 `stale_source_count`；Dashboard 的“终局目标刷新”也会展示 freshness。若 `freshness_level=stale`，应重新保存公开页面或改用公开 URL 抓取。

targets 可以直接喂给 P1.2 planner：

```powershell
python tools/probes/plan_training_priorities.py `
  --snapshot "data/probes/normalized/xxx_normalized.json" `
  --targets "data/probes/targets/endgame_targets.json"
```

当前 intake 只做保守关键词提取：活动名、弱点标签、机制标签、人工指定的 preferred characters 和最低练度线。真实“当前高难挑战配对”仍需要后续接官方公告 / 官方活动页的结构化解析，并在报告里标明来源等级与置信度。

### P0.8 OCR 实验矩阵

真实识别率提升必须以 expected diff 的 `pass_rate` 为硬验收，`coverage_summary` 只能辅助定位。

```powershell
python tools/probes/run_export_ocr_matrix.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --expected "data/probes/expected/1782409396884_expected.json" --write-crops
```

默认矩阵会依次运行：

* `tesseract_eng`：数字 baseline，只能调试固定区域；
* `tesseract_chi_sim_eng`：Tesseract 中文对照；
* `paddle`：P0.8 主线；
* `rapidocr`：Paddle 不达标后的本地 OCR fallback；
* `vision_baseline`：local-only 视觉模型占位，不上传图片，未配置模型时输出 unavailable。

输出目录：

```text
data/probes/experiments/<image_stem>/
```

矩阵 summary 会写出每个 engine 的 parsed JSON、review HTML、expected diff、`pass_rate`、`failed_groups` 和 `next_action`。不要提交 `data/probes/experiments/`、`data/probes/crops/` 或真实图片。

## Visible UI Probe

用途：只读当前米游社窗口的 Windows UI Automation 控件树和可见文本，判断角色名、等级、装备、技能、遗器 / 驱动盘，以及分享 / 导出按钮是否出现在可访问文本里。

```powershell
python tools/probes/miyoushe_uia_dump.py --window-title 米游社 --depth 8
```

限制：

* 不点击。
* 不滚动。
* 不截图。
* 不自动登录。
* 不读取 cookie/token/stoken/ltoken。

可选依赖：

```powershell
python -m pip install comtypes
```

## Local App Data Inventory

用途：只读用户手动指定的米游社 APP 数据目录，判断是否存在可解析 JSON / SQLite / HTML / cache。该工具只做 inventory，不做正式采集。

```powershell
python tools/probes/miyoushe_local_inventory.py --root "用户手动指定的米游社数据目录" --max-depth 4 --max-files 500
```

限制：

* 不自动猜测 APP profile。
* 不读取疑似 cookie/token/session/storage/login/auth 文件内容。
* 不输出大块原文。
* 不写 SQLite。
* 不上传。

## 结果判定

* 分享图覆盖字段足够：下一步做字段抽取 prototype。
* 分享图字段不足：研究 UIA 翻页、详情页逐项读取或多个分享图组合。
* 分享图不可用但 UIA 可读：做 UIA 字段抽取 prototype。
* 本地缓存有非敏感 JSON / SQLite / HTML：做 importer prototype。
* 只有 token/session/login/auth：不开采集，另开 ADR。
* 什么都没有：回到手动 JSON 或人工截图导入。
