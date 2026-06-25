# 米游社只读探针

这些工具只用于判断米游社 APP 是否存在可安全研究的数据来源。它们不是正式采集器，不写正式数据库，不自动登录，不自动点击完整流程，不抓包，不读取 cookie/token/session 内容。

所有输出写入 `data/probes/`，该目录必须保持在 `.gitignore` 中。

## Visible UI Probe

用途：只读当前米游社窗口的 Windows UI Automation 控件树和可见文本，判断角色名、等级、装备、技能、遗器 / 驱动盘等信息是否出现在可访问文本里。

运行方式：

1. 手动打开米游社 APP。
2. 手动进入《绝区零》或《崩坏：星穹铁道》的角色概览或角色详情页。
3. 运行：

```powershell
python tools/probes/miyoushe_uia_dump.py --window-title 米游社 --depth 8
```

查看输出摘要中是否出现：

* 角色名；
* 等级；
* 音擎 / 光锥；
* 技能 / 行迹 / 核心技；
* 遗器 / 驱动盘；
* 关键属性。

限制：

* 不点击。
* 不滚动。
* 不截图。
* 不自动登录。
* 不读取 cookie/token/stoken/ltoken。

## Local App Data Inventory

用途：只读用户手动指定的米游社 APP 数据目录，判断是否存在可解析 JSON / SQLite / HTML / cache。该工具只做 inventory，不做正式采集。

运行方式：

1. 用户手动找到或指定米游社 APP 数据目录。
2. 运行：

```powershell
python tools/probes/miyoushe_local_inventory.py --root "用户手动指定的米游社数据目录" --max-depth 4 --max-files 500
```

查看输出摘要中是否存在：

* 非敏感 JSON key；
* SQLite 表名和 schema 摘要；
* HTML 或 cache 文件；
* 看起来像角色练度数据的结构。

限制：

* 不自动猜测 APP profile。
* 不读取疑似 cookie/token/session/storage/login/auth 文件内容。
* 不输出大块原文。
* 不写 SQLite。
* 不上传。

## 结果判定

* UIA 可读：下一步做字段抽取 prototype。
* 本地缓存有非敏感 JSON / SQLite / HTML：下一步做 importer prototype。
* 只有 token/session/login/auth：不开采集，另开 ADR。
* 什么都没有：回到手动 JSON 或人工截图导入。
