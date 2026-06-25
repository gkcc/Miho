# ADR-0001 技术栈选择

状态：草案  
日期：2026-06-26（Asia/Shanghai）  
范围：技术选型调研与阶段性架构决策，不包含工程初始化、业务实现、真实账号接入或真实 cookie/token 处理。

## 背景

本项目计划做一个本地优先的游戏练度跟踪与规划桌面应用，覆盖《绝区零》和《崩坏：星穹铁道》的角色练度、装备、技能/行迹、终局活动目标、培养优先级、体力/开拓力规划和抽卡建议。

产品目标不是临时脚本或纯命令行工具，而是一个卡片化、美观、可长期维护的桌面应用。当前阶段仍处于技术选型和 MVP 边界确认阶段，在完成本 ADR 前不创建完整工程骨架，不初始化 Tauri / Flutter / Python / WinUI 项目，不接真实账号，不读取或处理真实 cookie/token。

本次调研通过 6 个只读 subagent 并行分析了 Tauri + Rust、Flutter、Python + PySide6、C# + WinUI 3、纯 Rust GUI，以及独立数据采集方案。主 agent 对结论进行归纳，而不是简单拼接。

## 目标

本 ADR 要回答以下问题：

- 原型阶段应使用什么路线验证数据模型、快照 diff、规划算法和卡片化信息架构。
- MVP 阶段应使用什么路线跑通本地数据闭环。
- 最终产品阶段应优先选择什么技术栈。
- 数据采集是否应该和 UI / 核心规划逻辑分离。
- 哪些方案适合作为主路线，哪些只适合作为备选或阶段性工具。

本 ADR 不解决：

- 具体数据库 schema。
- 具体推荐算法实现。
- 真实米游社 / HoYoLAB 接入。
- 自动登录、APP 自动点击、OCR 自动入库。
- UI 视觉稿或完整工程目录。

## 约束条件

- 本地可信数据闭环优先，AI 推荐靠后。
- MVP 不追求全自动，先支持 mock 数据或手动导入数据。
- 数据采集必须可复现、可回放、可降级。
- 结构化数据和用户手动导入优先，网页自动化只能作为后续 P2 可选方案。
- 不把 UI 自动点击、截图 OCR 作为主链路；OCR 只能兜底，且结果必须人工确认。
- 不绕过验证码、风控、加密或登录保护。
- 不高频请求米游社 / HoYoLAB。
- 不上传、不打印、不提交 cookie、token、stoken、ltoken、account_id、uid、设备标识、浏览器 profile 或登录态文件。
- 推荐结论必须可解释，包含依赖数据、目标活动、优先原因、置信度和不确定项。
- UI 不能做成只有普通表格的管理后台，主要页面必须以卡片为主。
- SQLite 是当前最合理的本地存储候选，但 schema 与迁移策略需另行验证。

## 候选方案

### Tauri + Rust + Svelte/React/Tailwind

Web 前端负责卡片化 UI，Rust 后端负责本地数据模型、SQLite、快照 diff、规划算法、隐私脱敏和前后端命令。Tauri 支持任意编译为 HTML/CSS/JS 的前端，并提供 command、plugin、权限和打包能力。

### Flutter / Dart

Flutter 负责跨平台桌面 UI、本地交互、状态管理和轻量业务逻辑。Dart 生态可接 SQLite，但复杂采集和浏览器自动化不应放在 Flutter 主应用内。

### Python + PySide6

Python 负责快速原型、数据清洗、导入解析、fixture 回放和采集可行性验证，PySide6 负责桌面 UI。优势在数据与原型速度，弱点在最终 UI 精致度、打包体积和长期产品维护。

### C# + WinUI 3

面向 Windows-first 的原生路线，使用 WinUI 3 / Windows App SDK / Fluent UI，C#/.NET 负责 SQLite、模型、diff 和规划逻辑。Windows 体验强，但跨平台弱。

### Rust + Slint / Iced / egui

纯 Rust GUI 路线。Slint 最接近最终产品，Iced 工程化可选但仍需验证复杂 UI 效率，egui 更适合内部工具、调试面板和快速 mock。

### Electron + TypeScript

Electron 使用 Chromium + Node.js 提供成熟的跨平台 Web 桌面方案。UI 生态、Node 工具链和发布生态强，但包体、内存、启动速度和安全边界成本高于 Tauri。

### 独立数据采集工具链

数据采集不应被 UI 框架绑死。建议按来源 adapter 设计：`manual_json`、`manual_csv`、`saved_html`、`browser_page`、`ocr_reviewed`。原型阶段可用 Python 或 TypeScript 做解析实验；稳定后的脱敏、schema 校验、snapshot 和 diff 可沉淀到核心模块。

## 对比矩阵

评价口径：强 / 较强 / 中 / 较弱 / 弱。这里的评价面向本项目约束，不代表技术本身优劣。

| 维度 | Tauri + Rust + Web | Flutter / Dart | Python + PySide6 | C# + WinUI 3 | Rust Native GUI | Electron + TS |
|---|---|---|---|---|---|---|
| UI 美观度 | 强：Web/Tailwind/图表生态成熟 | 强：Material 3、动画和响应式强 | 中：可做但美观成本高 | 较强：Fluent 原生感好 | 中：Slint 较好，Iced/egui 偏工程或工具 | 强：Web 生态最成熟 |
| UI 开发效率 | 较强：前端生态快，但双栈 | 强：热重载和组件化好 | 中：QtWidgets 快但易后台化，QML 增加双栈 | 中：XAML/MVVM 成本较高 | 中到较弱：组件需自建 | 强：Web + Node 生态快 |
| 数据采集能力 | 中：适合手动导入，不适合复杂采集主力 | 中到较弱：不适合采集主力 | 强：Python 解析/Playwright/OCR 生态好 | 中：.NET 可用但不如 Python/TS 灵活 | 中：HTTP 可行，浏览器自动化弱 | 较强：TS/Node/Playwright 方便 |
| 本地数据库 | 强：Rust 后端直管 SQLite 最清晰 | 强：drift/sqlite3 可行 | 强：sqlite3/QtSql 成熟 | 强：Microsoft.Data.Sqlite/EF Core | 强：rusqlite/sqlx 可行 | 强：better-sqlite3/sqlite 等成熟 |
| 快照 / diff / 规划算法 | 强：Rust 类型系统和测试适合长期核心 | 较强：Dart 足够 MVP，复杂后可抽核心库 | 较强：原型快，长期类型约束弱 | 强：C# 强类型与测试友好 | 强：全 Rust 类型一致 | 中到较强：TS 可行但运行时约束弱于 Rust/C# |
| 打包体积 | 强：通常小于 Electron，依赖 WebView2 | 中：通常大于 Tauri/WinUI | 较弱：Python + Qt 包体偏大 | 较强：原生路线较好，但发布配置复杂 | 强到中：二进制轻，发布链需自补 | 弱：需捆 Chromium/Node |
| 启动速度 | 较强：WebView + Rust | 中到较强 | 中到较弱 | 较强 | 强到较强 | 中到较弱 |
| Windows 体验 | 较强：WebView2、安装器、通知插件 | 较强：Windows desktop 支持成熟 | 中：可用但原生感一般 | 强：Windows 原生 | 中到较强：取决于 toolkit | 较强：成熟但资源重 |
| 跨平台潜力 | 强：桌面跨平台，移动也有路线 | 强：桌面和移动跨平台 | 较强：Qt 跨平台但打包复杂 | 弱：基本 Windows 锁定 | 较强：Rust GUI 多跨平台但生态不均 | 强：成熟跨平台 |
| 学习成本 | 中到较高：Rust + 前端 + Tauri 权限 | 中：Dart/Flutter 新栈但统一 | 低到中：Python 快，Qt/QML 有成本 | 中到较高：XAML/WinAppSDK | 较高：Rust + GUI 生态 | 中：Web 熟悉，Electron 安全需学 |
| 长期维护成本 | 中：双栈但边界清晰 | 中：插件和架构需控制 | 中到高：UI、打包、动态类型压力 | 中：强类型好，Windows 发布复杂 | 中到高：UI 生态和组件沉淀成本 | 中到高：依赖、安全、包体成本 |
| Codex 可维护性 | 较强：Rust 核心 + 前端组件边界清楚 | 较强：Dart 结构清楚，但 UI 树需约束 | 中：Python 友好，QML/打包较难 | 中到较强：C# 友好，XAML 细节难 | 中：Slint DSL 或复杂 Rust view 成本 | 较强：TS/React 友好，但依赖面大 |
| 隐私安全边界 | 强：Tauri 权限、Rust 后端、前端不碰敏感字段 | 中到较强：需强制分层 | 中：脚本灵活但容易散落敏感处理 | 强：DPAPI/Credential Locker 可用 | 强：本地单语言边界清晰 | 中：Node 权限强，需严格隔离 |

## 分方案分析

### Tauri + Rust + Svelte/React/Tailwind

推荐等级：强推荐，但不是无条件定案。

适合原因：

- 卡片化 UI 能直接利用 Web 前端生态，适合 Dashboard、角色卡、目标卡、规划卡、抽卡风险卡、图表和筛选。
- Rust 适合长期维护本地领域模型、快照 diff、规划算法、脱敏规则和 SQLite 访问层。
- Tauri v2 的 permissions / capabilities / scopes 能帮助形成最小权限边界。
- 前后端通信可通过 command/event/channel 收敛，前端只消费脱敏后的应用数据。
- 包体和资源占用通常优于 Electron，Windows 侧使用 WebView2，适合桌面应用。
- 对 Codex 后续维护较友好：UI 组件、Rust domain/service/repository、SQLite migration、测试 fixture 可以分层修改。

不适合原因：

- Rust + Node + 前端框架 + Tauri 权限配置属于双栈甚至多栈，启动成本高于 Python 或 Flutter。
- Tauri 不是复杂采集工具，真实账号采集、浏览器自动化、OCR、APP 自动点击都不应塞进主应用。
- 若过早创建完整工程，容易同时锁死 UI、核心模型、采集策略和打包策略。

阶段判断：

- 原型阶段：可选。若验证 UI 桌面体验，适合；若只验证数据模型和算法，Python 更快。
- MVP 阶段：主推荐候选。
- 最终产品阶段：主推荐候选。
- 数据采集阶段：只消费采集结果，不做采集唯一承载。

需要验证：

- Svelte vs React：个人长期维护更倾向 Svelte；生态最大化更倾向 React。
- SQLite 由 Rust 后端直管，还是使用 Tauri SQL 插件；当前倾向 Rust 后端直管。
- Windows 打包体积、冷启动、WebView2 依赖、通知、自动更新和数据库迁移体验。

### Flutter / Dart

推荐等级：可选，偏推荐用于原型 / MVP UI，不推荐作为数据采集主力。

适合原因：

- Flutter 官方支持 Windows、macOS、Linux 桌面，卡片、响应式布局、动画和 Material 3 体验成熟。
- Dart 空安全和强类型对中小型本地应用足够友好。
- SQLite 可通过 drift、sqlite3、sqflite_common_ffi 等路线实现。
- 热重载和组件化适合快速迭代卡片化 Dashboard。

不适合原因：

- Dart 不是复杂数据采集强项，浏览器自动化、会话调试、HTML 清洗、OCR 和采集 fixture 生态不如 Python / TypeScript。
- 桌面端插件质量不完全均衡，托盘、通知、自动更新、开机启动等需要逐项验证。
- 若把 UI、采集、脱敏、规划算法全塞进 Flutter，会形成长期耦合。

阶段判断：

- 原型阶段：推荐，尤其适合 UI mock。
- MVP 阶段：推荐备选。
- 最终产品阶段：可选偏推荐，前提是采集器和核心逻辑保持解耦。

### Python + PySide6

推荐等级：可选；强适合原型，不建议作为最终产品首选。

适合原因：

- Python 在 JSON/CSV/HTML 导入、数据清洗、fixture 回放、Playwright、OCR 和采集可行性验证方面效率最高。
- SQLite 可直接使用标准库 sqlite3。
- PySide6 是 Qt for Python 官方绑定，基础桌面能力完整。

不适合原因：

- QtWidgets 容易做成传统后台；QML/Qt Quick 更美观但会引入 Python + QML 双栈。
- PySide6 打包体积和依赖冻结成本高，若再加入 Playwright、OCR、WebEngine，包体和复杂度会快速膨胀。
- 长期产品维护可能被动态类型、打包兼容、UI 复杂度和采集耦合拖累。

阶段判断：

- 原型阶段：强推荐，用来验证数据模型、导入格式、快照 diff、规则评分和采集 adapter。
- MVP 阶段：可选，适合个人内部验证版。
- 最终产品阶段：谨慎，不作为默认首选。

### C# + WinUI 3

推荐等级：可选。

适合原因：

- Windows 原生体验最好，Fluent UI、通知、凭据保护和系统集成路线清晰。
- C#/.NET 强类型、测试、SQLite、JSON 和规划算法能力成熟。
- 如果项目明确 Windows-only，WinUI 3 是有竞争力的最终产品方案。

不适合原因：

- 跨平台弱，未来支持 macOS/Linux 时 UI 层大概率要重写。
- XAML/MVVM/Windows App SDK 配置和 MSIX/unpackaged 发布有门槛。
- 高度定制的游戏练度卡片、复杂图表和视觉风格效率不如 Web/Tailwind 或 Flutter。
- 数据采集不应由 WinUI 主导。

阶段判断：

- 原型阶段：可选但不是最高效。
- MVP 阶段：仅当明确 Windows-first 时可选。
- 最终产品阶段：适合 Windows 原生路线，不适合作为跨平台主路线。

### Rust + Slint / Iced / egui

推荐等级：可选。

适合原因：

- 领域模型、SQLite、快照 diff、规划算法、脱敏规则和 UI 都在 Rust 类型系统中，核心一致性好。
- Slint 是三者中最接近最终产品的路线，声明式 UI、样式和桌面控件能力比 egui 更产品化。
- egui 很适合作为内部调试面板、算法 inspector 或快速 mock。

不适合原因：

- 精致复杂产品 UI 的生态密度不如 Web/Flutter。
- 卡片系统、图表、虚拟列表、多页面导航、动画、空状态和桌面发布细节可能需要大量自研。
- Rust 对浏览器自动化和数据采集快速试错不如 Python/TypeScript。

阶段判断：

- 原型阶段：egui 或 Slint 可做小 mock。
- MVP 阶段：Slint 可验证，Iced 备选。
- 最终产品阶段：只有 Slint 视觉质量、组件复用、打包发布都验证通过后再考虑。

### Electron + TypeScript

推荐等级：可选，但不作为本项目默认首选。

适合原因：

- Web UI 生态最成熟，React/Svelte/Tailwind/图表/虚拟列表/动画都非常顺手。
- TypeScript + Node 对手动导入、HTML 解析、Playwright、SQLite 和本地工具链集成友好。
- Electron 发布、托盘、通知、自动更新和跨平台经验非常成熟。

不适合原因：

- 需要捆绑 Chromium 和 Node.js，包体、内存和启动速度压力最大。
- 安全边界成本高，Electron 官方安全文档也强调文件系统、shell 等能力带来的风险。
- 对本项目这种本地隐私数据应用，Node 权限和庞大 npm 依赖面需要额外治理。
- 若 Tauri 能提供同样的 Web UI 体验和更小的本地边界，Electron 的优势主要剩下成熟度和 Node 生态。

阶段判断：

- 原型阶段：可选，Web UI 原型速度快。
- MVP 阶段：可选但不优先。
- 最终产品阶段：仅当 Tauri/Flutter 在关键桌面能力上验证失败，或 Node/Playwright 深度集成成为硬需求时再考虑。

### 数据采集独立方案

推荐等级：强推荐。

核心结论：

- UI 技术栈不应决定采集策略。
- MVP 只做 mock 数据、手动 JSON/CSV/HTML 导入和 fixture 回放。
- P2 以后再验证用户主动保存官方战绩页、低频浏览器自动化、登录失效检测、缓存和限流。
- APP 自动点击、验证码绕过、游戏客户端控制、内部接口逆向、OCR 自动入库不进入 MVP。

语言判断：

- Python 最适合采集原型、解析、OCR、数据清洗和 fixture 生成。
- TypeScript 最适合浏览器自动化和 Web 周边。
- Rust 最适合稳定 schema、脱敏、snapshot、diff 和规划核心。
- C#/.NET 在 Windows 集成和凭据保护上可用。
- Dart/Flutter 不应承担采集核心。

## 推荐结论

### 原型阶段推荐

原型阶段不要直接锁最终工程栈。推荐拆成两条轻量验证线：

- 数据闭环原型：优先使用 Python 做 mock/手动导入格式、脱敏、标准化、快照 diff 和规则评分验证。此阶段不接真实账号，不读取 cookie/token，不做自动登录。
- UI 信息架构原型：优先使用 Flutter 或 Web/Tauri 前端技术验证卡片化 Dashboard、角色卡、目标卡和规划卡的信息密度。如果目的是验证最终桌面壳，可做 Tauri 小范围 mock；如果目的是最快看视觉和交互，可先用 Flutter 或普通 Web mock。

原型阶段不建议使用 WinUI 3 或纯 Rust GUI 作为第一选择，除非要专门验证 Windows 原生体验或 Slint 可行性。

### MVP 阶段推荐

MVP 阶段主推荐：

> Tauri + Rust + Svelte/Tailwind + SQLite，本地数据和规划核心由 Rust 管理，UI 只消费脱敏后的应用数据；采集模块保持独立 adapter，MVP 只支持 mock/手动导入/fixture 回放。

推荐理由不是“Rust 性能强”，而是综合考虑：

- Web UI 更容易做出漂亮的卡片化桌面体验。
- Rust 适合承载可解释规划器、快照 diff、脱敏和本地数据库边界。
- Tauri 的权限模型比 Electron 更适合本地隐私应用。
- SQLite 与本地优先闭环匹配。
- 前后端边界清晰，适合 Codex 后续小步维护。

MVP 备选：

- Flutter + SQLite：如果 UI 迭代速度优先，且暂时不想承担 Rust/Tauri 双栈成本，可作为 MVP 备选。
- Python + PySide6：如果目标是快速内部验证算法和导入闭环，而不是最终产品质感，可作为内部 MVP。

### 最终产品推荐

最终产品主推荐仍是：

> Tauri + Rust + Web UI + SQLite + 独立采集工具链。

最终产品保留备选条件：

- 如果 Tauri 的 Windows 打包、通知、WebView2、启动速度或前后端类型同步验证失败，考虑 Flutter。
- 如果明确放弃跨平台，只做 Windows 原生体验，考虑 C# + WinUI 3。
- 如果 Slint 原型证明 UI 质感、复杂列表、图表和发布链路都可接受，纯 Rust GUI 可进入候选，但不作为默认主路线。
- 如果 Tauri 无法满足某些 Node/Playwright 深度集成，Electron 可作为成熟但更重的 Web 桌面备选。

## 不选择其他方案的原因

- 不把 Flutter 作为默认最终主线：Flutter UI 很强，但采集和桌面系统插件需要逐项验证；若业务核心也写在 Dart 里，未来抽离 Rust/Python 核心会增加成本。
- 不把 PySide6 作为默认最终主线：原型效率强，但最终 UI 美观、打包体积、启动速度和长期产品维护不占优。
- 不把 WinUI 3 作为默认最终主线：Windows 原生体验强，但跨平台潜力弱，且 XAML/发布体系会提前锁定平台。
- 不把纯 Rust GUI 作为默认最终主线：核心类型系统好，但 UI 生态、组件效率、图表和发布体验仍需大量验证。
- 不把 Electron 作为默认最终主线：Web UI 与 Node 生态成熟，但包体、内存、启动速度和安全边界压力大；本项目更偏本地隐私数据，Tauri 更契合默认边界。
- 不把数据采集塞进主 UI 技术栈：采集风险、隐私风险和维护节奏都与 UI 不同，必须解耦。

## 最大风险

- 数据来源风险：目前没有确认存在稳定、公开、正式授权的米游社 / HoYoLAB 练度数据 API。官方战绩页面是用户产品，不等同于开发者 API。
- 隐私风险：cookie/token/account_id/uid/设备标识一旦进入日志、fixture、崩溃报告或 Git，影响严重。
- 自动化边界风险：为了自动化滑向验证码绕过、风控绕过、内部接口逆向、APP 自动点击或 OCR 自动入库。
- 过早工程化风险：在数据模型、MVP 边界和采集策略尚未稳定前创建完整工程，会把错误抽象固化。
- UI 质量风险：如果只重视核心算法，最终可能做成表格管理后台，偏离“卡片化、美观、长期可维护”的产品目标。
- 双栈维护风险：Tauri + Rust + Web 前端需要清晰目录、类型同步、测试边界和权限治理，否则复杂度会上升。

## 后续验证任务

1. 写 `ADR-0002 MVP 边界与模块分层`，明确 P0/P1/P2/P3 不混做。
2. 写 `ADR-0003 本地数据模型与快照策略`，只定义 mock 数据、标准化模型、快照、diff 和脱敏字段。
3. 做一份手动导入格式草案：JSON 优先，CSV 辅助，HTML 保存页作为 P2 待验证来源。
4. 验证 Tauri + Svelte/Tailwind 与 Flutter 各自做 3 个静态卡片页面的开发效率和视觉质量；验证时仍不接真实账号。
5. 验证 SQLite 方案：快照表、diff 表、规划结果表、迁移、备份、脱敏 raw fixture。
6. 验证 Rust 后端直管 SQLite 与 Tauri SQL 插件的边界，优先考虑 Rust 后端直管。
7. 验证 Windows 包体、冷启动、WebView2 依赖、通知、托盘、自动更新和本地数据库位置。
8. 验证采集 adapter 的脱敏规则，覆盖 cookie、token、stoken、ltoken、account_id、uid、手机号、邮箱、设备标识、浏览器 profile。
9. 验证 HoYoLAB / 米游社战绩页是否可由用户手动保存为可解析 HTML；此验证不得读取真实 cookie/token，不得绕过登录保护。
10. 明确日志策略：默认不记录原始响应，不记录敏感字段，测试 fixture 必须脱敏。

## 下一步建议

短期下一步不应初始化完整项目。建议先完成两份文档和一个极小 mock：

- 先写 MVP 边界文档，确认第一版只做 mock/手动导入、本地快照、diff、目标缺口、培养优先级和卡片化报告。
- 再写本地数据模型 ADR，明确角色、装备、技能/行迹、终局目标、资源、快照和 diff 的最小字段。
- 最后做极小范围 UI mock 对比，最多验证 Tauri/Svelte 与 Flutter 两条路线的卡片表现，不接真实账号，不读取 cookie/token，不创建完整工程骨架。

在当前证据下，阶段性主路线是：

> 原型：Python 验证数据闭环 + Flutter/Web 验证 UI 信息架构。  
> MVP：Tauri + Rust + Svelte/Tailwind + SQLite，采集 adapter 独立。  
> 最终产品：优先 Tauri + Rust + Web UI；Flutter、WinUI 3、Slint、Electron 作为有条件备选。

## 参考资料

- [Tauri: What is Tauri](https://v2.tauri.app/start/)
- [Tauri SQL Plugin](https://v2.tauri.app/plugin/sql/)
- [Tauri Capabilities](https://v2.tauri.app/security/capabilities/)
- [Tauri Notifications](https://v2.tauri.app/plugin/notification/)
- [Flutter Desktop Support](https://docs.flutter.dev/platform-integration/desktop)
- [Flutter Windows Deployment](https://docs.flutter.dev/deployment/windows)
- [Qt for Python](https://doc.qt.io/qtforpython-6/)
- [pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
- [WinUI 3](https://learn.microsoft.com/en-us/windows/apps/winui/winui3/)
- [SQLite in Windows apps](https://learn.microsoft.com/en-us/windows/apps/develop/data-access/sqlite-data-access)
- [Slint](https://slint.dev/)
- [Iced](https://docs.rs/iced/latest/iced/)
- [Electron Introduction](https://www.electronjs.org/docs/latest/)
- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [Playwright Supported Languages](https://playwright.dev/docs/languages)
- [SQLite](https://www.sqlite.org/index.html)
- [HoYoLAB Battle Chronicle](https://act.hoyolab.com/app/community-game-records-sea/index.html)
- [HoYoLAB Agreement](https://www.hoyolab.com/agreement)
