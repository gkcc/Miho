# 米游社探针工具

这些工具只用于判断米游社 APP 是否存在可安全研究的数据来源。它们不是正式采集器，不写正式数据库，不自动登录，不输入账号密码，不抓包，不读取 cookie/token/session 内容。

所有输出写入 `data/probes/`，该目录必须保持在 `.gitignore` 中。

## 推荐验证顺序

1. 用户手动打开米游社 APP，进入某个角色详情页。
2. 运行 UIA dump，确认窗口和分享 / 导出按钮能否被读到。
3. 运行 export image probe，尝试点击官方分享 / 导出按钮。
4. 找到导出图片后，运行 parse probe。
5. 检查 JSON / Markdown 中是否能识别角色名、等级、装备、技能、遗器 / 驱动盘。
6. 如果分享图覆盖字段足够，下一步做字段抽取 prototype。
7. 如果分享图字段不足，再研究 UIA 翻页、详情页逐项读取或底层 API。

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

### Parse probe

对官方导出 / 分享图做 OCR 和字段分类草案。

```powershell
python tools/probes/export_image_parse_probe.py --image "data/probes/exported_images/example.png"
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --lang chi_sim+eng
python tools/probes/export_image_parse_probe.py --image "C:\Users\zy958\Downloads\1782409396884.jpg" --game zzz --layout zzz-agent-card --lang eng
```

如果本机已安装 Tesseract 中文语言包，优先使用 `--lang chi_sim+eng`。如果没有 `chi_sim`，先用 `--lang eng` 跑通固定区域解析，确认数字字段覆盖率。

新增参数：

* `--engine tesseract|paddle|none`：默认 `tesseract`；`paddle` 是可选分支，未安装依赖时只会给出提示。
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
python -m pip install pillow pytesseract
```

Tesseract 程序本体和中文语言包需要单独安装到本机。

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
