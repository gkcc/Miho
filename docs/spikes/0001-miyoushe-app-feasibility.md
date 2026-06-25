# 米游社 APP 可读性与官方导出探针

状态：待验证
类型：P0.6 feasibility spike / probe-first / 人工确认
边界：不是正式采集器，不接底层 API，不自动登录，不输入账号密码，不抓包，不读取 token，不写正式数据库。

## 目标

判断米游社 APP 是否存在可安全研究的数据入口，用于后续决定是否值得做字段抽取 prototype 或 importer prototype。

本 spike 现在按三条并行探针验证：

1. Official Export Image RPA Probe：最高优先级。
2. Visible UI Probe：辅助判断控件树和按钮可见性。
3. Local App Data Inventory：辅助判断缓存是否有结构化来源。

优先级调整原因：

* 米游社 APP 是官方社区和数据工具，不是游戏客户端。
* 用户本地 APP 已登录时，操作官方 UI 生成“导出 / 分享图”比读取底层登录态或猜缓存格式更清晰。
* 官方分享图天然适合人工确认、回放和离线 OCR。
* 分享图失败后，才需要继续研究 UIA 翻页、详情页逐项读取、本地缓存或单独 ADR 评估授权 API。

## 非目标

本 spike 明确不是：

* 正式采集功能。
* 自动登录。
* 账号密码输入。
* 底层 API 接入。
* 抓包。
* 读取明文 cookie/token/stoken/ltoken。
* 绕过验证码、风控、加密或登录保护。
* 控制游戏客户端。
* 写正式数据库。
* 自动把识别结果入库。
* MVP 主链路。

所有 probe 输出必须写入 `data/probes/`，真实导出图和 probe 结果不得提交 Git。

## A. Official Export Image RPA Probe

### 目标

验证能否自动或半自动操作已登录米游社 APP，找到官方导出 / 分享图入口，保存官方生成的分享图，并判断分享图是否覆盖角色练度字段。

具体目标：

* 自动或半自动操作已登录米游社 APP。
* 找到官方导出 / 分享图入口。
* 保存官方生成的分享图。
* 判断分享图是否覆盖角色练度字段。
* 从分享图提取结构化字段草案。

### 允许范围

* 点击米游社 APP 内的官方 UI。
* 滚动官方页面。
* 等待页面加载。
* 保存官方分享图。
* 对分享图做 OCR / 图像识别 / 版面解析。
* 输出 `data/probes/exported_images/` 和 `data/probes/parsed/` 下的本地结果。
* 输出操作日志、失败原因和人工确认建议。

### 禁止范围

* 不自动登录。
* 不输入账号密码。
* 不读取 cookie/token/stoken/ltoken。
* 不抓包。
* 不绕过验证码或风控。
* 不高频点击。
* 不控制游戏客户端。
* 不把识别结果直接写入正式数据库。
* 不提交真实图片或 probe 输出。

### 建议命令

用户先手动打开米游社 APP，进入某个角色详情页或分享入口附近：

```powershell
python tools/probes/miyoushe_export_image_probe.py --game zzz --mode manual-page --window-title 米游社 --dry-run
python tools/probes/miyoushe_export_image_probe.py --game zzz --mode manual-page --window-title 米游社
```

找到导出图片后再运行解析探针：

```powershell
python tools/probes/export_image_parse_probe.py --image "data/probes/exported_images/example.png"
```

### 判定重点

| 检查项 | 期望结论 |
|---|---|
| 是否找到米游社窗口 | 能 / 不能 / 标题不稳定 |
| 是否找到分享、导出或保存图片按钮 | 能 / 部分 / 不能 |
| 是否能通过 UIA 安全触发按钮 | 能 / 不能 / 需要图像模板 |
| 是否生成官方分享图 | 是 / 否 / 需要人工保存 |
| 分享图是否覆盖角色名和等级 | 是 / 部分 / 否 |
| 分享图是否覆盖装备、技能、遗器 / 驱动盘 | 是 / 部分 / 否 |
| OCR / 版面解析是否可用 | 是 / 部分 / 否 |
| 是否需要正式字段抽取 prototype | 是 / 否 / 不确定 |

## B. Visible UI Probe

### 目的

辅助验证当前米游社窗口的 UIA 控件树和可见文本，尤其是官方分享 / 导出按钮是否能被识别。

### 允许范围

* 用户手动打开米游社 APP。
* 用户手动进入角色详情页或分享入口附近。
* 工具只读当前窗口控件树和可见文本。
* 输出控件 depth、name、control_type、automation_id、class_name、bounding_rectangle、is_offscreen。
* 收集非空可见文本，并自动脱敏。
* 输出 JSON 和 Markdown 摘要到 `data/probes/`。

### 禁止范围

* 不点击。
* 不滚动。
* 不截图。
* 不自动登录。
* 不抓包。
* 不读取 cookie/token/stoken/ltoken。
* 不写 SQLite。

### 建议命令

```powershell
python tools/probes/miyoushe_uia_dump.py --window-title 米游社 --depth 8
```

## C. Local App Data Inventory

### 目的

辅助判断用户显式指定的米游社 APP 本地数据目录里是否存在非敏感、可解析的 JSON / SQLite / HTML / cache 数据来源。

### 允许范围

* 用户通过参数显式传入扫描目录。
* 工具在该目录内按最大深度和最大文件数限制扫描文件。
* 输出脱敏相对路径、扩展名、大小、mtime、文件类型判断。
* 对 `.json` / `.txt` / `.html` / `.log` 只读取少量头部样本，并先脱敏。
* 对 `.sqlite` / `.db` 只读取表名和 schema 摘要，不读取表数据。
* 对二进制文件只记录类型和大小。
* 输出 JSON 和 Markdown 摘要到 `data/probes/`。

### 禁止范围

* 不自动猜测 APP profile。
* 不读取疑似 cookie/token/session/storage/login/auth 文件内容。
* 不打印、不保存、不提交登录态。
* 不抓包。
* 不上传。
* 不写 SQLite。

### 建议命令

```powershell
python tools/probes/miyoushe_local_inventory.py --root "用户手动指定的米游社数据目录" --max-depth 4 --max-files 500
```

## 字段与 ADR-0003 映射

| 分享图 / 页面字段类别 | ADR-0003 目标实体 |
|---|---|
| 角色名称、等级、星魂、影画 | `Character` / `CharacterBuildSnapshot` |
| 音擎、光锥、等级、叠影 / 精炼 | `Equipment` |
| 技能等级、核心技、行迹 | `SkillOrTrace` |
| 驱动盘、遗器、位面饰品、主词条 | `ArtifactOrDriveDisc` |
| 攻击、暴击、速度、击破等关键属性 | `CharacterBuildSnapshot.key_stats` |
| 页面来源、导出时间、警告 | `SourceRecord` |

## 输出要求

probe 输出目录：

```text
data/probes/
data/probes/exported_images/
data/probes/parsed/
```

输出要求：

* JSON 用于后续机器分析。
* Markdown 用于人工快速判断。
* 官方导出图片只能本地保存，不得提交 Git。
* 识别结果必须标记 confidence 或 uncertain。
* 不保存 token/session/cookie 内容。
* 不写正式 SQLite。
* 不提交 `data/probes/`。

## 风险判断

| 风险 | 等级 | 缓解方式 |
|---|---|---|
| 官方 UI 改版风险 | 中 | RPA 只做 probe；正式 prototype 前保留失败退出和人工确认 |
| 分辨率和缩放风险 | 中 | 优先 UIA Invoke，不盲点固定坐标 |
| 登录状态风险 | 高 | 只使用用户已登录状态，不自动登录，不输入账号密码 |
| 弹窗和验证码风险 | 高 | 不绕过，记录为失败条件 |
| 导出图片隐私风险 | 高 | 图片只保存在 `data/probes/exported_images/`，不得提交 Git |
| OCR 误差风险 | 中 | 输出 confidence / uncertain，不自动入库 |
| 平台规则风险 | 中 | 不抓包、不逆向、不控制游戏客户端、不高频点击 |

## 结论模板

```text
结论：
- Official Export Image RPA：可行 / 部分可行 / 不可行 / 不确定
- Visible UI Probe：可辅助 / 不可辅助 / 不确定
- Local App Data Inventory：有非敏感结构化来源 / 只有敏感登录态 / 无可用来源 / 不确定

证据摘要：
- 官方分享图：
- OCR / 图像识别：
- UIA：
- local inventory：

主要风险：
- （待填写）

后续建议：
- （待填写）
```

## 下一步决策

根据 probe 结果选择下一步：

* 官方分享图覆盖字段足够：做字段抽取 prototype，输入为本地图片，输出为脱敏 JSON 草案。
* 官方分享图可导出但字段不足：研究 UIA 翻页、详情页逐项读取或多个分享图组合。
* 分享图导出不可自动触发但可人工保存：保留手动导出 + parse probe 路线。
* 分享图不可用但 UIA 可读：做 UIA 字段抽取 prototype。
* 本地缓存有非敏感 JSON / SQLite / HTML：做 importer prototype。
* 只有 token/session/login/auth 或必须底层 API：不开采集，另开 ADR。
* 什么都没有：回到手动 JSON 或人工截图导入。

无论选择哪条路线，都必须继续遵守：

* 不自动登录。
* 不输入账号密码。
* 不读取明文 cookie/token/stoken/ltoken。
* 不抓包。
* 不绕过验证码、风控、加密或登录保护。
* 不控制游戏客户端。
* 不把 OCR / 解析结果自动写入正式数据库。
