# 米游社 APP 可读性探针

状态：待验证
类型：只读 feasibility spike / probe-first / 人工 fallback
边界：不是 MVP 功能，不实现正式采集，不自动登录，不自动点击完整流程，不抓包，不读取 token，不写正式数据库。

## 目标

判断米游社 APP 是否存在可安全研究的数据入口，用于后续决定是否值得做半自动字段抽取或 importer prototype。

本 spike 只回答一个问题：

```text
米游社 APP 当前可见界面或用户显式指定的本地数据目录里，
是否存在足够稳定、非敏感、可解析的练度数据来源？
```

重点验证：

* 当前可见页面里是否能读到角色名、等级、装备、技能、遗器 / 驱动盘等文本。
* 用户指定的本地目录里是否存在非敏感 JSON / SQLite / HTML / cache 数据。
* 可读字段是否覆盖 ADR-0003 的本地数据模型草案。
* UIA、非敏感本地缓存、人工导入、截图 / OCR 各自的价值和风险。

## 非目标

本 spike 明确不是：

* 正式采集功能。
* 自动登录。
* 自动点击完整流程。
* 抓包。
* 读取 token。
* 读取明文 cookie/stoken/ltoken。
* 读取疑似 session/login/auth 文件内容。
* 绕过验证码、风控、加密或登录保护。
* 写正式数据库。
* 自动 OCR 入库。
* 控制游戏客户端。
* MVP 主链路。

所有 probe 输出必须脱敏后写入 `data/probes/`，并且不得提交 Git。

## Probe 1：Visible UI Probe

### 目的

验证用户手动打开米游社 APP 并进入角色概览或详情页后，Windows UI Automation 是否能读到当前窗口控件树和可见文本。

### 允许范围

* 用户手动打开米游社 APP。
* 用户手动进入《绝区零》或《崩坏：星穹铁道》的角色概览或角色详情页。
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
* 不把 dump 当正式练度数据入库。

### 建议命令

```powershell
python tools/probes/miyoushe_uia_dump.py --window-title 米游社 --depth 8
```

### 判定重点

| 检查项 | 期望结论 |
|---|---|
| 是否找到米游社窗口 | 能找到 / 找不到 / 标题不稳定 |
| 是否能读到角色名 | 能 / 部分 / 不能 |
| 是否能读到等级 | 能 / 部分 / 不能 |
| 是否能读到装备或光锥 / 音擎 | 能 / 部分 / 不能 |
| 是否能读到技能 / 行迹 / 核心技 | 能 / 部分 / 不能 |
| 是否能读到遗器 / 驱动盘 | 能 / 部分 / 不能 |
| 是否只能看到 WebView 外壳 | 是 / 否 / 不确定 |
| 是否出现敏感字段并被脱敏 | 无 / 已脱敏 / 脱敏不足 |

## Probe 2：Local App Data Inventory Probe

### 目的

验证用户显式指定的米游社 APP 本地数据目录里，是否存在非敏感、可解析的 JSON / SQLite / HTML / cache 数据来源。

这个 probe 只做 inventory，不做采集，不读登录态内容，不写正式数据库。

### 允许范围

* 用户通过参数显式传入扫描目录。
* 工具在该目录内按最大深度和最大文件数限制扫描文件。
* 输出脱敏相对路径、扩展名、大小、mtime、文件类型判断。
* 对 `.json` / `.txt` / `.html` / `.log` 只读取少量头部样本，并先脱敏。
* 对 JSON 只提取 key 摘要，不输出大块原文。
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
* 不把 inventory 结果当正式数据入库。

### 建议命令

```powershell
python tools/probes/miyoushe_local_inventory.py --root "用户手动指定的米游社数据目录" --max-depth 4 --max-files 500
```

### 判定重点

| 检查项 | 期望结论 |
|---|---|
| 是否存在 JSON | 有 / 无 / 只有敏感文件 |
| 是否存在 SQLite / DB | 有 / 无 / 只有敏感文件 |
| 是否存在 HTML / cache | 有 / 无 / 不确定 |
| JSON key 是否像角色练度数据 | 是 / 否 / 不确定 |
| SQLite 表名是否像角色练度数据 | 是 / 否 / 不确定 |
| 是否主要只有 token/session/login 文件 | 是 / 否 / 不确定 |
| 是否出现敏感字段并被脱敏 | 无 / 已脱敏 / 脱敏不足 |

## 人工 checklist fallback

如果两个 probe 都无法提供稳定结论，再用人工 checklist。人工记录只写观察结论，不要求逐项抄录真实字段值，也不得记录真实 uid、手机号、邮箱、cookie/token 或其他敏感信息。

| 检查项 | 记录 |
|---|---|
| APP 版本 |  |
| Windows 版本 |  |
| 屏幕缩放 |  |
| 显示器分辨率 |  |
| 登录状态 | 已登录 / 未登录 / 登录过期 / 不确定 |
| 游戏 | 绝区零 / 崩坏：星穹铁道 |
| 是否能手动进入角色概览 | 是 / 否 / 不稳定 |
| 是否能手动进入角色详情 | 是 / 否 / 不稳定 |
| 页面是否显示角色名、等级、装备 | 是 / 部分 / 否 |
| 页面是否显示技能、行迹、遗器 / 驱动盘 | 是 / 部分 / 否 |
| 是否出现弹窗或验证码 | 无 / 有，说明 |
| 是否可复制文本 | 否 / 部分 / 大部分 / 不确定 |
| 是否疑似 WebView | 是 / 否 / 不确定 |
| 是否必须截图才能识别 | 是 / 否 / 部分 |
| 备注 |  |

## 字段与 ADR-0003 映射

| 页面或缓存字段类别 | ADR-0003 目标实体 |
|---|---|
| 角色名称、等级、星魂、影画 | `Character` / `CharacterBuildSnapshot` |
| 音擎、光锥、等级、叠影 / 精炼 | `Equipment` |
| 技能等级、核心技、行迹 | `SkillOrTrace` |
| 驱动盘、遗器、位面饰品、主词条 | `ArtifactOrDriveDisc` |
| 攻击、暴击、速度、击破等关键属性 | `CharacterBuildSnapshot.key_stats` |
| 页面来源、验证时间、警告 | `SourceRecord` |

## 输出要求

probe 输出目录：

```text
data/probes/
```

输出要求：

* JSON 用于后续机器分析。
* Markdown 用于人工快速判断。
* 所有文本必须先脱敏。
* 默认不输出大块原文。
* 不保存截图。
* 不保存 token/session/cookie 内容。
* 不提交 `data/probes/`。

## 风险判断

| 风险 | 等级 | 缓解方式 |
|---|---|---|
| UI 改版风险 | 高 | UIA 只做可读性验证，不作为 MVP 主链路 |
| 分辨率和缩放风险 | 中 | 不做坐标点击，不截图识别主链路 |
| 登录状态风险 | 高 | 不自动登录，不保存登录态 |
| 弹窗和验证码风险 | 高 | 不绕过，记录为失败条件 |
| 本地缓存敏感信息风险 | 高 | 疑似敏感文件只记录存在，不读取内容 |
| OCR 误差风险 | 中 | OCR 只作为人工确认兜底，不自动入库 |
| 平台规则风险 | 中 | 不抓包、不逆向、不高频请求、不绕过保护 |

## 结论模板

```text
结论：
- UIA 可读 / UIA 不可读 / 不确定
- 本地非敏感缓存可用 / 只有敏感登录态 / 不确定 / 无可用缓存

证据摘要：
- Visible UI Probe：
- Local App Data Inventory：
- 人工 fallback：

主要风险：
- （待填写）

后续建议：
- （待填写）
```

## 下一步决策

根据 probe 结果选择下一步：

* UIA 可读：做字段抽取 prototype。prototype 仍只读当前可见文本，不点击、不滚动、不写正式数据库。
* 本地缓存有非敏感 JSON / SQLite / HTML：做 importer prototype，只解析脱敏样本和结构化字段。
* 只有 token/session/login/auth：不开采集，另开 ADR，评估用户授权、本地存储、脱敏、限流、失败处理和 Git 防泄漏。
* 什么都没有：回到手动 JSON 或人工截图导入。

无论选择哪条路线，都必须继续遵守：

* 不自动登录。
* 不读取明文 cookie/token/stoken/ltoken。
* 不抓包。
* 不绕过验证码、风控、加密或登录保护。
* 不控制游戏客户端。
* 不把 OCR 结果自动写入正式数据库。
