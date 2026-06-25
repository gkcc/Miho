# ADR-0002 MVP 边界与模块分层

状态：草案  
日期：2026-06-26（Asia/Shanghai）  
前置决策：ADR-0001 已采纳，MVP 主路线暂定为 Tauri + Rust + Svelte/Tailwind + SQLite，采集 adapter 独立。

## 背景

ADR-0001 已完成技术栈调研，并给出阶段性结论：MVP 优先采用 Tauri + Rust + Svelte/Tailwind + SQLite；Rust 负责本地核心、快照 diff、规划算法、SQLite 访问边界和隐私脱敏；Svelte/Tailwind 负责卡片化 UI；采集 adapter 独立于 UI 技术栈。

当前项目仍不能初始化完整工程，不能接入真实账号，不能读取或处理真实 cookie/token。本 ADR 的目标是把 MVP 的内外范围和模块分层固定下来，让后续 mock 数据、数据模型、UI 信息架构和规划规则可以沿着同一条边界推进。

## 决策

MVP 只实现本地可信数据闭环，不实现真实账号自动采集。

MVP 的核心闭环是：

1. 使用 mock 数据或用户手动 JSON 导入作为输入。
2. 将输入标准化为本地统一模型。
3. 保存 SQLite 快照。
4. 对快照生成结构化 diff。
5. 配置一个或少量终局目标。
6. 分析当前 box 与目标之间的缺口。
7. 输出培养优先级和体力/开拓力规划。
8. 用卡片化 Dashboard mock 或报告展示结果。

模块上采用分层架构：

```text
app shell
  -> ui
  -> commands/api
  -> domain
  -> storage
  -> importers
  -> planner
  -> reports
  -> privacy
  -> fixtures
```

实际依赖方向必须更严格：UI 只能通过 commands/api 访问应用能力；storage 不依赖 UI 或具体游戏规则；planner 不依赖 UI；importers 不直接写 UI；privacy/redaction 作为横切能力被 importers、storage、reports 和 fixtures 使用。

## MVP 内范围

MVP 内范围必须服务本地闭环，不追求全自动。

- mock 数据：维护一组不含真实账号、cookie/token、uid 的样例数据，用于 UI、导入、快照、diff 和 planner 验证。
- 手动 JSON 导入：优先支持用户选择本地 JSON 文件；JSON 格式由 ADR-0003 草案约束。
- 本地标准化模型：把不同游戏、不同来源的输入转换为统一结构，例如账号、角色、装备、技能/行迹、终局目标、计划项。
- SQLite 快照：每次导入生成一个 snapshot，保留标准化后的结构化数据和脱敏来源元信息。
- 快照 diff：比较相邻或指定两个 snapshot 的结构化字段，输出新增角色、等级变化、装备变化、技能变化、目标状态变化等结果。
- 终局目标配置：支持人工配置至少一个终局目标，包括游戏、活动、目标层级、需要队伍数、机制标签和完成状态。
- 当前 box 缺口分析：基于已有角色、练度、目标要求和队伍模板，输出缺口项。
- 培养优先级：按终局收益、资源成本、泛用性、时效性和“是否让队伍从不可用变可用”排序。
- 体力/开拓力规划：输出今日/本周建议，不要求自动读取游戏内体力值。
- 卡片化 Dashboard mock：展示当前最重要培养目标、快照变化、终局目标状态和规划摘要。
- 隐私脱敏规则：对所有来源记录、日志、fixture 和报告执行默认脱敏。
- fixture 回放：允许用脱敏 mock fixture 回放导入、标准化、snapshot、diff 和 planner。

## MVP 外范围

以下能力明确不进入 MVP：

- 自动登录。
- 自动点击米游社 APP。
- 真实 cookie/token 处理。
- OCR 自动入库。
- 浏览器自动化。
- 联网抽卡建议自动化。
- 完整终局活动自动解析。
- 自动打包发布。
- 多账号云同步。
- 控制游戏客户端。
- 绕过验证码、风控、加密或登录保护。
- 高频请求米游社 / HoYoLAB。
- 自动读取浏览器 profile 或 APP profile。
- 自动生成完美抽卡建议。
- 全角色、全遗器、全驱动盘的精细评分系统。
- 真正后台长期运行或开机自启采集。

这些能力可以在 P2/P3 重新评估，但必须通过新的 ADR 或明确设计文档约束权限、隐私、限流、失败恢复和 fixture 回归测试。

## 模块分层

### app shell

职责：

- 桌面应用入口、窗口生命周期、Tauri 权限边界、应用级配置加载。
- 后续可承载通知、单实例、应用设置入口，但 MVP 不做完整自动更新或后台采集。

不负责：

- 不直接处理游戏规则。
- 不直接读取真实账号凭据。
- 不直接访问数据库表细节。

### ui

职责：

- Svelte/Tailwind 卡片化界面、Dashboard mock、角色卡、目标卡、规划卡、导入结果展示。
- 只展示 commands/api 返回的脱敏应用数据。

不负责：

- 不直接访问 SQLite。
- 不直接读写 cookie/token/account_id/uid。
- 不直接执行导入解析、快照 diff 或 planner。

### commands/api

职责：

- Tauri command 或本地 API 边界。
- 将 UI 操作转换为应用服务调用。
- 返回面向 UI 的 DTO，确保输出已脱敏、结构稳定、错误可解释。

不负责：

- 不包含复杂游戏规则。
- 不绕过 domain、planner 或 privacy 直接操作底层数据。

### domain

职责：

- 核心实体、值对象、枚举、校验规则和跨游戏统一概念。
- 定义 GameAccount、Snapshot、Character、Equipment、EndgameGoal、PlanItem 等模型。

不负责：

- 不依赖 UI 框架。
- 不依赖 Tauri command。
- 不依赖具体 SQLite 表实现。

### storage

职责：

- SQLite 存储、迁移草案、snapshot 持久化、diff 结果持久化、本地配置持久化。
- 提供 repository 或 storage service 给上层使用。

不负责：

- 不依赖 UI。
- 不依赖具体游戏规则评分。
- 不保存未脱敏敏感字段。

### importers

职责：

- mock JSON、手动 JSON、后续可选 CSV/HTML 的输入适配。
- 将输入解析为 SourceRecord 和标准化 domain 模型。
- 支持 partial success：单角色解析失败不导致全量失败。

不负责：

- 不直接写 UI。
- 不直接决定 planner 优先级。
- MVP 不处理真实 cookie/token，不做浏览器自动化。

### planner

职责：

- 当前 box 缺口分析。
- 队伍模板匹配。
- 培养优先级排序。
- 体力/开拓力规划。
- 输出解释、置信度和不确定项。

不负责：

- 不依赖 UI。
- 不读取原始敏感来源。
- 不直接写 SQLite，持久化由 storage 或应用服务协调。

### reports

职责：

- 将 planner、snapshot diff、目标状态组合为报告或 Dashboard 展示模型。
- 输出卡片化 UI 所需摘要，例如今日计划、本周计划、重要变化、风险提示。

不负责：

- 不执行采集。
- 不保存敏感原始数据。

### privacy

职责：

- 敏感字段识别、脱敏、日志过滤、fixture 脱敏校验。
- 统一处理 cookie、token、stoken、ltoken、account_id、uid、手机号、邮箱、设备标识、浏览器 profile、APP profile。

不负责：

- 不决定业务规划逻辑。
- 不绕过上层模块直接修改 UI 状态。

### fixtures

职责：

- 存放或生成脱敏 mock fixture。
- 支持导入、标准化、snapshot、diff、planner 和 reports 的回放测试。

不负责：

- 不保存真实账号数据。
- 不保存真实 cookie/token。
- 不混入用户本地数据目录。

## 模块依赖方向

必须遵守以下依赖方向：

- UI 不直接访问数据库。
- UI 不接触敏感字段。
- UI 只通过 commands/api 调用导入、查询、规划和报告能力。
- commands/api 可以调用 domain、storage、importers、planner、reports、privacy。
- planner 不依赖 UI。
- planner 只消费标准化 domain 模型和目标配置。
- importers 不直接写 UI。
- importers 输出标准化结果、错误列表和脱敏来源记录。
- storage 不依赖具体游戏规则。
- storage 不直接计算培养优先级。
- reports 可以读取 planner 输出和 diff 输出，但不执行导入和采集。
- privacy/redaction 是横切能力，importers、storage、reports、fixtures 和日志都必须使用。
- 采集 adapter 独立于 UI 技术栈；后续即使更换 Svelte、Flutter 或其他 UI，adapter 的输入输出契约不应随之改变。

建议的依赖形态：

```text
ui -> commands/api -> application services
application services -> domain
application services -> importers
application services -> planner
application services -> reports
application services -> storage
importers -> privacy
storage -> privacy
reports -> privacy
fixtures -> privacy
planner -> domain
storage -> domain-shaped records, not game-specific scoring rules
```

禁止的依赖形态：

```text
ui -> storage
ui -> raw source records with sensitive fields
planner -> ui
storage -> planner game scoring
importers -> ui components
browser automation -> ui state
OCR -> formal database without manual confirmation
```

## P0 / P1 / P2 / P3 分期

### P0：本地数据闭环

目标：跑通 mock/手动 JSON 到本地快照、diff、基础报告的闭环。

包含：

- mock 数据格式。
- 手动 JSON 导入。
- 本地标准化模型。
- SQLite snapshot 草案。
- 快照 diff。
- 基础 Dashboard mock。
- 隐私脱敏规则。
- fixture 回放。

不包含：

- 真实账号。
- 自动登录。
- 浏览器自动化。
- APP 自动点击。
- OCR 自动入库。

### P1：目标缺口与培养规划

目标：在 P0 数据闭环上加入可解释规划。

包含：

- 终局目标配置。
- 队伍模板配置。
- 当前 box 匹配度评分。
- BuildGap 输出。
- 培养优先级。
- 今日/本周体力或开拓力规划。
- 报告解释、置信度和不确定项。

### P2：真实数据导入与半自动采集验证

目标：在安全边界内验证真实数据来源，但不牺牲本地可信闭环。

可评估：

- 用户手动导入真实 JSON/CSV。
- 用户手动保存 HTML 后本地解析。
- 登录失效检测。
- 缓存和限流。
- 原始数据脱敏保存。
- 采集 fixture 回归测试。
- 低频、用户触发的浏览器自动化可行性调研。

仍禁止：

- 绕过验证码/风控/加密。
- 自动控制游戏客户端。
- APP 自动点击作为主链路。
- 真实 cookie/token 入库或入日志。

### P3：联网研究与抽取建议

目标：在用户 box、目标缺口和资源预算基础上，加入公开来源研究和抽取建议。

包含：

- 当前卡池和官方公告来源记录。
- 来源分级和置信度。
- 抽取建议报告。
- 不抽风险、资源培养能力、后续预算影响。

不包含：

- 把未实装卫星当确定规划。
- 不看用户 box 直接推荐抽卡。
- 自动高频联网抓取。

## 风险

- 范围膨胀：MVP 容易从本地闭环滑向真实采集、抽卡自动化和完整 UI，实现成本失控。
- 隐私误伤：真实 cookie/token、uid、浏览器 profile 或 APP profile 一旦进入日志、fixture 或数据库，后果严重。
- 模块耦合：UI 直接访问数据库或 importers 直接操纵 UI 会破坏后续可维护性。
- 规则过早复杂化：终局评分、遗器/驱动盘细分评分和抽卡建议如果过早进入 MVP，会掩盖本地快照闭环问题。
- Tauri 双栈复杂度：Rust、Tauri command、Svelte/Tailwind、SQLite 需要清晰边界，否则 Codex 后续修改成本会上升。
- mock 偏差：mock 数据如果过于理想化，可能无法暴露 partial success、字段缺失、版本变更和脱敏失败问题。

## 后续任务

1. 完成 ADR-0003，本地数据模型与快照策略。
2. 定义最小 mock JSON schema，覆盖 zzz、hsr、角色、装备、技能/行迹、终局目标和计划项。
3. 设计 P0 Dashboard 信息架构，只画卡片结构，不实现真实 UI。
4. 定义 snapshot diff 输出格式和错误模型。
5. 定义 privacy/redaction 规则和 fixture 脱敏检查清单。
6. 评估 Rust domain model 的最小边界，但在 ADR-0003 完成前不写业务代码。
7. 评估 Tauri/Svelte 极小 mock UI 的可行性，但在明确 mock 范围前不初始化完整工程。
