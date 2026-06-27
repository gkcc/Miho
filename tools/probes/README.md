# 米游社探针工具

这些工具只用于判断米游社 APP 是否存在可安全研究的数据来源。它们不是正式采集器，不写正式数据库，不自动登录，不输入账号密码，不抓包，不读取 cookie/token/session 内容。

所有输出写入 `data/probes/`，该目录必须保持在 `.gitignore` 中。

## 推荐验证顺序

1. 用户手动导出一张米游社官方分享图。
2. 将图片保存到 `data/probes/exported_images/`。
3. 运行 parse probe：

```powershell
python tools/probes/export_image_parse_probe.py --image "data/probes/exported_images/xxx.jpg" --game zzz --layout zzz-agent-card --engine auto
```

4. 查看 `data/probes/parsed/*.md` 和同名 JSON。
5. 如果 `coverage_level` 为 `high` 或 `medium`，继续做字段抽取 prototype。
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
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine auto --lang chi_sim+eng
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine tesseract --lang eng
python tools/probes/export_image_parse_probe.py --image "data/probes/exported_images/example.png" --game zzz --layout zzz-agent-card --engine none
```

默认 `--engine auto` 会先尝试 PaddleOCR，再降级到 Tesseract。PaddleOCR 未安装时不会影响 Tesseract 路线；Tesseract 缺少 `chi_sim` 时，先用 `--lang eng` 跑通固定区域解析，确认数字字段覆盖率。`--engine none` 可用于只验证图片加载、布局区域和 JSON/Markdown 输出结构。

新增参数：

* `--engine auto|tesseract|paddle|none`：默认 `auto`；`auto` 优先 PaddleOCR，失败后尝试 Tesseract。
* `--game zzz|hsr`：当前固定区域解析只支持 `zzz`。
* `--layout full|zzz-agent-card`：默认 `full`；`--game zzz --layout zzz-agent-card` 会按绝区零分享图固定区域裁剪并分别 OCR。

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
python -m pip install pillow pytesseract
```

Tesseract 程序本体和中文语言包需要单独安装到本机。

### P0.7 HTML 验收页

P0.7 的目标是让用户肉眼验收分享图解析结果是否可靠。HTML 只是验收工具，不代表解析成功。先解析官方分享图：

```powershell
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --engine auto
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
python tools/probes/evaluate_export_parse.py --parsed "data/probes/parsed/xxx.json" --expected "data/probes/expected/xxx_expected.json"
```

至少比较：

* `character.name` / `character.level` / `character.rank`
* 核心属性：`hp` / `atk` / `def` / `crit_rate` / `crit_dmg`
* 六个技能等级
* 音擎名称、等级、评级
* 六个驱动盘等级、主词条、副词条

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
