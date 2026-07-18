# 终局数据工具迁移项目

## 产品愿景

将现有 HSR/ZZZ Python 工具完整迁移到 Tauri 2 + Rust，最终运行时不依赖 Python，并持续打磨美观、易用的高质量前端，同时保持 GUI、CLI、JSON/YAML/CSV、Box State v2、报告和计算语义兼容。迁移期间 Python 是行为基准；Rust 命令只有通过黄金对比后才能解除门禁。

## 当前目标（完成优先）

迁移与首个可用 Windows active 已完成。当前默认目标不再是继续扩张迁移流程，而是：

1. 用户报告的问题先在真实使用入口形成“复现 → 最小修复 → 定点验证 → 可直接使用的交付”闭环。
2. 完成条件是实际入口可用、相关测试通过、交付物/用法明确并完成一个本地提交；不要求顺带完成重构、性能或文档美化。
3. 优化项在交付闭环后单独排期，不得反向阻塞已经可用的结果。
4. 发布、安全、数据删除/迁移和权限边界仍保留高风险门禁；普通改动不默认触发全量矩阵或多轮对抗复审。
5. 默认交付是直接构建并更新当前 Tauri EXE；NSIS、安装器、portable 和发布包只在用户明确要求时进入范围。

## 当前状态

- 工作区已安全迁移到 `D:\Projects\终局内容提取`；6,111 个不可再生项目文件与 16,301 个归档文件逐路径 SHA-256 校验均为零差异，迁移回执保存在归档目录。
- D 盘迁移后重建验证：Rust workspace 迁移测试持续通过，frozen pnpm install、Vite build 与 Tauri `--no-bundle` 通过；双游戏 visualizer 契约、Rust 实现、真实 CLI、Hub 与浏览器冒烟现已全部收口。
- 工作区治理完成：业务资产已归档到 `D:\Projects\终局内容提取-archive\20260712-005035`，清单含 761 个文件及 SHA-256。
- Cargo workspace 已建立：`miho-core`、`miho-app`、`miho-cli`、`miho-desktop`。
- Rust 已实现 HF 在线/离线统一 `SnapshotSource`、日期与部分失败语义、两游戏多 snapshot/mode 聚合，以及 HSR histograph/fallback、动态视图、完整队伍去重和 ZZZ Bangboo/name fallback。
- Rust CLI 已接通 HSR/ZZZ `export`、原子写出和 0/1/2 退出码；两游戏的 Prydwen visible/tier/changelog、HoYoWiki 官方名称、历史、趋势、raw 与 Workbook 产物均已进入共享 Rust pipeline，补充来源或 Workbook 失败只降级为结构化 warning。
- 版本化 `ExportRequestV1`、可信 `ExportContext`、结构化 diagnostics/stats/IPC receipt/failure 已进入 CLI 执行链；请求会核对实际 dataset 身份，报告完成后重建 artifact manifest。
- HSR 的 `--prydwen-top-n`/`--name-map-seed` 与 ZZZ 的 `--prydwen-top-n` 已解除选项门禁；离线 CLI 默认生成 Workbook，两游戏在线 export 均在 visualizer 完整目录验收后解除总门禁。
- ZZZ 已覆盖 visible scope 保序、版本优先的最新阶段、phase selector/override、agent/Bangboo 双语名称、alias、完整 26/4/32 列 history/trend，以及 Cloudflare/retcode 语义失败的 last-good cache 回退。
- 最近完整回归：Rust workspace 435 项、Python 181 项（含 native update runner、workspace bootstrap、安装/portable 计划任务事务、跨进程 writer lease、共享 app task/TaskManager、Tauri backend、安全 frontend/visualizer protocol、Evidence V1、LegacyV0 decision、pull-value V1 与 review-packet V1 契约）、workspace 严格 clippy、Rust fmt、Python compileall、PowerShell 5.1/7 native/installer/scheduler/release 契约、Vite 与 Tauri `--no-bundle` 通过。Rust 全量首轮曾有一次 `invalid_date_is_a_business_error` 瞬时失败；手工 stderr 精确正确、定点连续 20/20 后，独占全量 435 项通过，该抖动保留为项目监测项。
- Tauri/Vite 构建基线已固定 pnpm 11.7.0、Node `>=20.19 <25`、esbuild 布尔 allowlist 和 `127.0.0.1:5173` strict port，根脚本可从干净依赖状态复现；1420 落入本机 Windows 保留端口段，已由真实 dev 启动反例纠正。
- 双游戏 Workbook 语义契约已冻结：HSR 18-sheet、ZZZ 12-sheet 脱敏 oracle 与比较器覆盖顺序、值/类型、公式、样式、冻结、筛选、列宽和数值格式；10 项契约测试及 30 张工作表渲染核验通过。
- 共享 Rust Workbook writer 已直接消费最终 CSV bundle：显式类型、HSR 样式/列宽/数值格式、ZZZ pandas 默认语义、安全公式文本、BestEffort diagnostics、manifest/receipt 与 CLI 原子写出均已通过双游戏语义对比。
- 双游戏 visualizer 产物契约已冻结并由 Rust 实现：严格 `data.json`、精确目录集合、静态资源与头像哈希、禁网/便携/XSS/URL/非有限数值约束，以及 Hub/HSR/ZZZ 浏览器交互冒烟均已通过；两游戏 export 与独立 visualizer 共用最终磁盘产物重建边界。
- `evidence-first-v1-20260712` 已由 Python oracle 与共享 Rust core/CLI 双实现：跨 mode 隔离、A 的 sentinel/稳定性门槛、owned/built 分离、稳定 E-ID、显式时钟、JSON/YAML/BOM、四产物黄金和任意路径整批回滚均已验收；Rust evidence/coverage 门禁已解除。
- Python 继续作为决策/报告迁移 oracle，但安装、计划任务、portable 与桌面/CLI 运行时均已证明不启动 Python。五类报告共用 `miho-app` executor；纯 Rust TaskManager、Tauri capabilities/select/start/get/list/cancel、安全任务前端和 workspace-scoped visualizer/data/avatar/Box 协议桥已接通。单一 Rust update runner、failure receipt、config-bound health、跨进程 workspace writer lease、安装/portable 候选切换与发布事务均已接通并完成真实失败升级回滚、成功升级、计划任务 Running→Ready、portable online update、无 Python 与最终卸载矩阵。
- 历史 NSIS/portable 链曾完成 frozen inputs、container manifest 与真实安装矩阵；`target/release/bundle/miho-release-artifacts-v1.json` 仅作为那条旧安装器链的事实源保留，不再决定当前桌面程序。
- 当前桌面程序直接由 Tauri/Rust Release 构建并更新到 `D:\Miho Endgame\miho-desktop.exe`。Box、AppData、计划任务和 Rust CLI 保持原位；当前 EXE 以直接构建哈希和后台产品探针为交付证据。

## 阶段路线

1. **工作区治理**：完成。
2. **兼容基线**：完成；CLI、输入输出、允许差异与黄金比较器均已固化。
3. **Rust 基础内核**：完成；强类型配置、规范化、解析模型、稳定标识、可靠存储与网络边界均已接通。
4. **数据抓取与导出**：完成；Hugging Face、Prydwen、官方名称及 HSR/ZZZ export 均由 Rust 正式路径承担。
5. **决策与报告**：完成；evidence、coverage、decision compatibility、pull-value、review-packet 的 Rust core/CLI 已解除门禁。
6. **Tauri 产品化**：完成；可视化、任务、进度、取消、错误、原生目录选择与安全 workspace 协议均已验收。
7. **自动化与历史发布链**：已完成迁移期验收；当前普通产品交付不再运行 NSIS/portable 矩阵。Python 源码仅保留为迁移 oracle，不进入产品运行链。

## 当前执行方式

- 普通任务：实现最小闭环 → 跑相关定点测试 → 给用户可直接使用的结果 → 本地提交。
- 高风险任务（发布、安全、数据删除/迁移、权限、公共事务边界）：增加必要的真实路径验证和一次独立 Blocker/High 复审。
- 只在状态、决策、证据或重要风险变化时回填追踪文档；中间探索不强制形成独立阶段或提交。
- 全量回归只用于大范围变更或最终发布，不作为普通修复的默认前置条件。
- 运行时变化默认重建并直接更新 Tauri EXE；NSIS/portable/发布包仅在用户明确要求时重建。纯文档提交不触发程序重建。
- 完成交付后再处理非阻断优化，避免验证和文档流程本身成为关键路径。

## 第十二批三目标（已完成）

| 子目标 | 状态 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 盘点五类决策/报告契约 | 完成 | 三个互斥只读审计子智能体、主智能体 | Python evidence/coverage/decision/pull-value/review-packet、CLI、config、tests | 依赖图、LegacyV0/V1 分界、bundle smoke hash、对抗 fixture 矩阵 | `docs/decision-report-contract.md`；10 个输出规范化 hash；审计明确 decision/pull 未解门条件 | 双游戏最终 CSV 已稳定 |
| 定标 Evidence V1 Python oracle | 完成 | 主智能体、独立对抗审查子智能体 | 完整 dedup team、name/tier、Box/builds、plan、显式 local datetime | mode-scoped evidence key、A/B/C、observation trace、current/target/aggregate、pull 主/风险证据分离 | 159 项 Python；跨 mode、sentinel/stability/build、alias、schema、clock、路径冲突和回滚反例；独立 `Blocker=0 / High=0` | 契约盘点 |
| 迁移 Rust evidence/coverage | 完成 | 主智能体、Rust core/fixture 子智能体、独立对抗审查子智能体 | EvidenceInputs/Request/Context V1、Python oracle | 共享 Rust evidence core、两命令 CLI、事务安装 | 四产物跨语言黄金；真实 CLI 0/1/2、YAML/BOM、manifest/visualizer 保留、junction/回滚反例；独立 `Blocker=0 / High=0` | Evidence V1 复核清零 Blocker/High |

## 第十三批三目标（已完成）

| 子目标 | 状态 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 迁移 Rust decision compatibility | 完成 | 三个只读边界/fixture 审计子智能体、主智能体、独立对抗审查子智能体 | `legacy-v0` 六 CSV/Box/rules 契约 | 仅在显式 `--method legacy-v0` 下运行的 Rust compatibility core/CLI | 旧 JSON/Markdown 精确兼容、两文件事务、0/1/2；独立 `Blocker=0 / High=0`；不得成为正式推荐默认 | Rust evidence/coverage 已解门 |
| 迁移 Rust pull-value | 完成 | 主智能体、CLI/fixture 子智能体、两名独立对抗审查子智能体 | Evidence V1 主/风险证据、tier/usage、Banner plan、baseline | typed pull cards、同 mode A/B 支撑的抽取价值报告、Rust CLI | current/next 跨语言黄金；exact dependency、PyYAML/非有限/rounding/事务/0-1-2 对抗；独立 `Blocker=0 / High=0` | Rust decision 边界固定 |
| 迁移 Rust review-packet | 完成 | 主智能体、两名独立只读/对抗审查子智能体 | pull-value typed bundle、current/next Python packet | 只序列化同一批 pull cards 的 Rust packet/core/CLI | current/next 跨语言 hash、字段顺序/trace、sentinel 不重算、动态 fence、Python JSON 数值、split/combined、单时钟/批事务、0/1/2；独立 `Blocker=0 / High=0` | Rust pull-value 已解门 |

## 第十四批三目标（已完成）

| 子目标 | 状态 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 共享报告应用层与 V1 intent/receipt/failure | 完成 | 主智能体、应用层实现子智能体、两名独立对抗审查子智能体 | CLI 五类私有报告 adapter、现有 core/黄金/事务契约 | `miho-app`、trusted native request、pathless intent、共享 executor、CLI 薄适配 | app 6 项、真实 CLI 16 项、Rust 223 项；malformed/unknown/schema failure；junction/later-install；独立 `Blocker=0 / High=0` | 第十三批完成 |
| Rust TaskManager 与 Tauri 薄命令 | 完成 | 主智能体、TaskManager 实现子智能体、Tauri 后端子智能体、独立对抗审查子智能体 | pathless intent、trusted workspace、共享 executor | start/get/list/cancel、capabilities、native workspace 选择、连续状态事件 | 全局单任务；commit 前取消不改输出、commit 后 too-late；A/B/C active 竞态；panic/spawn；opaque/reparse/persist；事件 1..N 补发；独立 `Blocker=0 / High=0` | 共享应用层完成 |
| 安全前端与 visualizer 协议桥 | 完成 | 主智能体、协议/契约只读审计子智能体、独立对抗终审子智能体 | Tauri TaskManager、Box State、Rust visualizer 静态资产 | 安全任务面板、错误/诊断/产物、native workspace 选择、内嵌双游戏 visualizer | main UI 无 unsafe HTML sink；isolation + access/storage scope；有界 data/avatar/Box、A→B/Windows AppData 真机；Rust 268、Python 181、Vite/Tauri release；独立 `Blocker=0 / High=0` | TaskManager 完成 |

## 第十五批三目标（已完成）

| 子目标 | 状态 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 单一 Rust native update orchestrator、failure receipt 与 writer lease | 完成 | 主智能体、runner 契约审查子智能体、两名独立 Windows/对抗终审子智能体 | 双游戏 Rust export、五类报告 executor、旧 PowerShell 自动化、workspace 安全边界 | `miho update run/health`、严格 config/state/attempt/canonical receipt、config-bound generation health、全 writer OS lease、native launcher | Rust 325、Python 181、PowerShell 5.1/7、真实双进程/cwd/junction/失败恢复/CrossesDevices；独立 `Blocker=0 / High=0` | 第十四批完成 |
| 安装资源与计划任务候选验证后原子切换 | 完成（2026-07-15 真机验收） | 主智能体、独立安装/任务审查子智能体 | release `miho.exe`、默认 config、原 Disabled 旧路径任务 | 安装/portable 稳定资源路径、candidate run+exact health、旧任务所有权与回滚 | 真实升级失败回滚、成功升级、canonical Task Scheduler Running→Ready 与 exact health 均通过；最终卸载删除任务/owner/产品状态 | native runner 完成 |
| NSIS/portable、无 Python 矩阵与 Python runtime 退役 | 完成（2026-07-15 active 发布与最终 smoke） | 主智能体、独立发布终审子智能体 | 候选任务切换链、安装资源 | install/upgrade/uninstall/portable 发布链与 runtime 清理 | clean HEAD active NSIS/portable、空 PATH/零 Python、真实 upgrade/rollback、最终 clean install/health/uninstall 与 AppData canary 通过；Python 仅保留为源码 oracle，不再是安装、CLI、桌面、更新或任务 runtime | 计划任务切换完成 |

## 决策记录

| 日期 | 决策 | 影响 | 复核条件 |
| --- | --- | --- | --- |
| 2026-07-12 | 采用纯 Tauri + Rust，GUI 与 CLI 全兼容，分阶段替换 | Python 保留为迁移 oracle，禁止一次性切换 | 全部黄金测试通过 |
| 2026-07-12 | 工作区采用复制、全量哈希、Git 校验后切换的方式从 C 盘迁移到 D 盘 | `D:\Projects\终局内容提取` 是后续唯一开发入口；C 盘旧源码仅作为短期回滚副本 | 再次迁盘或 D 盘健康状态异常时 |
| 2026-07-12 | 业务资产归档到仓库外，缓存直接清除 | 工作区只保留源码、配置、测试和项目文档 | 需要恢复历史数据时使用归档清单 |
| 2026-07-12 | 每个子目标一个本地提交，每三个子目标复盘（历史流程，已于 2026-07-16 精简） | 迁移期提高可回退性；不自动推送远端 | 见 2026-07-16 完成优先决策 |
| 2026-07-12 | 首发仅维护 Windows 图标和安装配置 | 删除自动生成的 Android/iOS 图标 | 正式纳入其他平台时 |
| 2026-07-12 | Rust export 先开放 fixture/HF 核心路径，默认补充来源保持显式门禁 | 避免把缺 Prydwen/官方名称的残缺目录误报为兼容成功 | 两游戏完整目录黄金对比通过 |
| 2026-07-12 | V1 wire 请求拒绝未知字段，运行时路径只由 Rust 构造；成功回执和失败回执分离 | 防止 CLI/Tauri 静默忽略能力或由 WebView 注入缓存/历史路径 | IPC schema 升级或新增可信输入来源时 |
| 2026-07-12 | 外部 HTTP 2xx 也必须通过业务 payload 校验后才覆盖 last-good cache | Cloudflare challenge 与 HoYoWiki retcode 错误会回退缓存并保留原因，不污染离线基线 | 来源协议改版或引入新补充站点时 |
| 2026-07-12 | HSR 补充选项已迁移，但默认在线入口继续受完整目录总门禁保护 | 可用 fixture/核心 API 验收真实 Rust 链路；XLSX/visualizer 未完成时不声称替代 Python | HSR 完整目录仅剩批准差异时 |
| 2026-07-12 | ZZZ 补充选项已迁移，但在线 CLI（含显式关闭补充源的 HF-only 形式）继续受产品级总门禁保护 | phase/usage/team 分别保留 Python 的日期回填语义；fixture 可验收完整 Rust 链路；XLSX/visualizer 未完成时不声称替代 Python | ZZZ 完整目录仅剩批准差异时 |
| 2026-07-12 | 决策命令继续排在导出产品完整性之后；第十批先修前端构建并完成 Workbook | 避免让 evidence/decision 依赖仍受 XLSX/visualizer 总门禁保护的目录；visualizer 数据契约紧随 Workbook | 双游戏导出仅剩批准差异时 |
| 2026-07-12 | Workbook 比较规范化 RGB alpha、继承字体元数据、solid fill 未使用背景和合并列宽区间；实际 Rust 文件另行强制全局零公式 | 保留视觉/数据语义而不追逐库级 OOXML 表示差异；表头 thin border、类型、格式和宽度仍严格比较 | 更换 XLSX 库或主题默认字体时 |
| 2026-07-12 | CLI 使用 `WorkbookPolicy::BestEffort`；成功产物进入内嵌 manifest/receipt，失败只记结构化 warning 且不留半成品 | 离线双游戏导出已包含 XLSX；在线总门禁缩小为仅等待 visualizer | visualizer 完整目录黄金对比通过时 |
| 2026-07-12 | visualizer 契约边界定义为最终 ArtifactBundle 加显式 VisualizerContext，而非声称可由 CSV 单独逆向 | Banner/Decision sidecar、官方/raw 补充信息、clock 与头像存储必须成为 Rust API 的显式输入；两游戏 export 先落最终 CSV 再走独立重建 | Rust context/schema 升级或 sidecar 被并入正式 artifact manifest 时 |
| 2026-07-12 | HSR visualizer 通过致密跨语言、真实 CLI 整目录与浏览器验收后解除在线 export 总门禁；ZZZ 门禁保持 | HSR 默认在线路径可直接生成 CSV、Workbook、visualizer 与最终 manifest；Python 保留为 oracle，不再是 HSR 正式运行时依赖 | HSR 完整目录出现未批准差异或外部来源协议变化时 |
| 2026-07-12 | 每个阶段提交前增加显式信心/质疑提问与独立对抗复核（历史迁移门槛，已于 2026-07-16 收敛到高风险任务） | 迁移/发布期防止 fixture 假绿；普通任务不再默认执行 | 发布、安全、数据删除/迁移、权限或公共事务边界变化时 |
| 2026-07-12 | ZZZ visualizer 通过致密跨语言、真实 CLI/Hub、浏览器与独立对抗复核后解除在线 export 总门禁 | 两游戏默认在线路径均由 Rust 生成 CSV、Workbook、visualizer、manifest；Python visualizer 降为 oracle | 完整目录出现未批准差异、来源协议变化或 sidecar schema 升级时 |
| 2026-07-12 | legacy 无 manifest 输出只从游戏正式命名空间恢复 ownership；未知文件保留但不进入新 manifest | `raw/hf/**` 因动态 source path 被保留为 export-owned 命名空间，用户私有文件不得放入其中 | 正式 artifact schema/manifest 增加显式 ownership metadata 时 |
| 2026-07-12 | 决策/报告以 `evidence-first-v1-20260712` 为正式方法；旧 decision 标记 `legacy-v0` | 同队不跨 mode 合并分数/置信度；A 需有效表现与稳定组件；高/中高抽取必须引用 A/B 主证据；LegacyV0 精确兼容不等于方法完成 | 证据策略/schema 升级或用户明确要求旧 heuristic 默认化时 |
| 2026-07-12 | Rust evidence/coverage 报告是 export 目录中的 unmanaged consumer artifact；报告命令只捕获一次 cwd/local datetime，任意输出整批安装并拒绝父链 symlink/reparse point | 不刷新或占有 `artifact_manifest.json`/visualizer；debug 固定时钟只用于黄金测试，release 始终使用本地时钟；路径别名不能绕过三输出互异性 | 报告进入正式 artifact schema、支持受信任 reparse 输出或事务协议升级时 |
| 2026-07-12 | `decision` 只迁移显式 `legacy-v0` compatibility；正式 evidence-first 推荐唯一入口是 `pull-value`，`review-packet` 直接序列化同一批卡片 | 禁止再造第二套 Decision V1 与 pull-value 竞争；Legacy 继续保留 raw team、跨 mode heuristic 和旧 payload/hash，但 CLI/help/receipt 必须标 compatibility only，UI 不得当正式推荐 | 产品明确批准独立 Decision V1 的版本化规则/schema，或正式推荐入口发生变更时 |
| 2026-07-12 | LegacyV0 compatibility 按 Python 的字段存在性、truthiness、`str(float)`、DictReader 与 PyYAML 1.1 语义做显式 adapter，不以 serde 默认行为代替兼容契约 | 六 CSV 的 missing/null/empty、JSON/YAML quoted/plain scalar、非有限失败和旧两文件事务进入 Rust 门禁；visualizer sidecar 根字段标记 `decisionMethodVersion=legacy-v0` | 删除 LegacyV0、升级其公开 schema，或 Python oracle 被版本化替代时 |
| 2026-07-13 | `pull-value` 作为唯一正式推荐入口解除 Rust 门禁；未拥有候选的主证据只接受 exact single dependency，多计划依赖进入 conditional risk | current/next 或显式合并报告使用单次时钟和批事务；PyYAML/JSON/BOM/非有限值走共享安全解析；manifest/visualizer/legacy sidecar 不归报告命令管理 | Evidence 方法/schema 升级、报告进入正式 manifest，或 review-packet/IPC 改变卡片所有权时 |
| 2026-07-13 | Rust `review-packet` 解除 core/CLI 门禁，并固定为 `PullValueBundleV1` 的安全 serializer | 不重新读取输入或重算推荐；split/combined 与 pull-value 共用 adapter、单次时钟和批事务；manifest、visualizer、decision、pull/coverage 产物仍为 unmanaged | pull card/schema、Evidence 方法、JSON renderer、报告 ownership 或 IPC 所有权变化时 |
| 2026-07-13 | 五类报告路径/时钟/渲染/批事务从 CLI 私有实现迁入共享 `miho-app`；WebView 只接受 pathless `TaskIntentV1` | pathful `TaskRequestV1/WorkspaceLayout` 不实现 serde，仅供可信原生 adapter；malformed/unknown/wrong schema 进入版本化 failure；CLI 只翻译参数并调用唯一 executor | intent/schema、workspace 授权、TaskManager 取消/commit 边界或报告 ownership 变化时 |
| 2026-07-13 | TaskManager 以锁内 `before_commit` 作为取消/提交线性化点，首版全局单活动；Tauri 仅以 opaque workspace ID 解析 pathless intent | queued/running 可请求取消且 commit 前无写；committing 后返回 too-late；事件按 native history prefix 连续补发，query 始终权威；公开 snapshot 不含路径或 raw error | 放宽并发、增加 export、持久任务历史、跨进程锁/journal、abrupt-kill 恢复或 public schema 变化时 |
| 2026-07-13 | 桌面 visualizer 使用 Tauri isolation、编译期可信代码和 workspace-scoped custom protocol；静态 artifact 字节不注入桌面逻辑 | 所有 index/app/styles/data/avatar/Box 请求带短期 opaque access token；app 响应动态封装 fetch，并以 canonical workspace SHA-256 scope 隔离/恢复 localStorage；data 响应只改写安全本地头像；stale A→B 统一拒绝 | Tauri/Wry isolation 机制、workspace/access/storage identity grammar、visualizer asset/schema、protocol route 或 Box ownership 变化时 |
| 2026-07-13 | Windows AppData 同目录 rename 仍可能返回 `CrossesDevices`，设置替换的 backup/install/rollback 均使用 synced copy fallback | 首写和已有 settings 的连续 A→B→A 在正常运行/错误路径可用；source 删除失败会撤销新 target，不假报 move 成功；不声称强杀/掉电原子性 | 更换设置存储位置、Windows 打包身份/虚拟化层、实现 crash journal/recovery 或 atomic storage 时 |
| 2026-07-13 | 自动更新业务收敛为单一 Rust `update run/health`，PowerShell 只作精确退出码 launcher；所有 managed workspace writer 共用一把 OS lease | online HF update 禁止 last-good cache 伪造 freshness；state/canonical/attempt/generation 均绑定精确 config digest 与产物 hash；symlink/junction/reparse fail-closed；失败不前移 state | update config/schema、产物 ownership、freshness policy、writer identity、receipt/health 协议或 crash-recovery 承诺变化时 |
| 2026-07-14 | 发布状态不再由 clean/full 自动升级为 active；默认 clean/full 也只生成 `verification-only`，active 必须显式 `-ProjectGatesApproved` | 项目级 installer/upgrade/uninstall/真实矩阵与独立终审成为机器入口上的显式批准边界；dirty、no-bundle 或非 Release 批准硬失败 | 发布批准改由外部签名/CI attestation 承担，或项目门禁契约版本升级时 |
| 2026-07-15 | 真实 verification-only 候选完成失败升级回滚、成功升级、canonical Task Scheduler、portable、空 PATH/零 Python 与最终卸载矩阵 | installer 项目门禁可在本阶段独立终审和提交后用于 clean full active 构建；`NotSigned` 不得被 active 状态掩盖，AppData 用户数据不属于默认卸载边界 | 最终 clean 构建与 manifest 复核失败、真实矩阵证据漂移、签名策略变化或用户数据删除策略升级时 |
| 2026-07-15 | clean `85ed31d` 通过显式项目门禁发布 active NSIS/portable，并以最终字节重做 clean install/health/uninstall/AppData canary | 第十五批和“运行时不依赖 Python”的迁移主线完成；Python 源码继续作为黄金 oracle，不进入安装、CLI、桌面、更新或计划任务运行链；active manifest 是精确产物事实源 | runtime 代码/资源变化、active manifest 漂移、签名策略变化或任一最终 smoke 失败时重新关门 |
| 2026-07-15 | installer recovery 增加真实 helper 进程终止门禁 | PowerShell 5.1/7 均在第一项静态 payload 已提交后强杀，并在 durable `rolling-back` 后再次强杀；原始未插桩 helper 必须恢复 clean before-image、owner 与事务根 | installer journal/phase、静态写入、rollback、scheduler handoff 或 NSIS hook 变化时 |
| 2026-07-15 | installed GUI 启动门禁与 portable 冒烟分离；NSIS owner 建立后必须从完整安装布局启动窗口并存活五秒 | portable marker 会绕过 installed-owner 注册表分支，不能再替代安装版启动证据；退出 101、setup-hook 错误或未建窗口一律重新关门 | installed owner schema/registry API、桌面 setup hook、安装布局或 portable 检测变化时 |
| 2026-07-16 | 生产前端必须由相对 `frontendDist` 嵌入，并以 custom-protocol + 真实 CDP/DOM sentinel 守门 | Windows 绝对 staging 路径会被 URL-first `FrontendDist` 误解析为 `file:///`；窗口存活不再等于页面可用，Edge 错误页、开发 URL、假 sentinel 或缺 Tauri internals 均阻断发布 | Tauri config/codegen、custom-protocol feature、config parent、前端 ready sentinel、WebView2/CDP 或 staging 布局变化时 |
| 2026-07-16 | 执行方式改为完成优先：一个可交付里程碑一次提交，定点验证默认，优化后置 | 普通任务不再强制多轮复审、全量回归或重复留痕；高风险边界继续保留真实验证与一次独立复审 | 用户要求恢复更严格流程，或普通流程再次漏掉系统性高风险缺陷时 |
| 2026-07-16 | 发布重建改由 runtime inputs 变化触发；纯流程、说明或测试文档提交不使既有 active 失效 | 最大困难是 tracked 留痕若也强制重建会形成自引用循环；manifest 继续绑定实际构建 commit/hash，文档 HEAD 不冒充新的程序版本 | runtime inputs/digest 变化，或需要把新 HEAD 声明为新的程序版本时 |
| 2026-07-17 | 产品交付回到 Tauri 本体：Rust 后端 + 高质量前端，默认直接构建并替换当前 EXE；后台 CDP/DOM 模拟点击属于允许的真实入口验证 | 普通修复不再进入 NSIS、安装器、portable 或 active 发布仪式；旧发布资产只作历史兼容保留 | 用户明确要求安装器/发布包，或直接 EXE 交付无法满足运行需求时 |

## 风险登记

| 风险 | 当前状态 | 缓解措施 |
| --- | --- | --- |
| Python/Rust 计算或默认值漂移 | 高 | 先固化 CLI 与黄金输出，逐命令解除门禁 |
| Legacy decision 与 evidence-first 方法冲突 | 低（兼容迁移已验证，正式方法仍隔离） | `decision --method legacy-v0` 仅作 compatibility；正式推荐只由 pull-value 产生并以 dedup A/B 主证据支撑高优先级 |
| 双游戏 visualizer 与 Python 语义漂移 | 低（已验证） | 46 项跨语言/真实 CLI 契约、118 项 core、浏览器冒烟与独立对抗反例；sidecar/schema 变化时重新关门复核 |
| Workbook 单元格类型和样式可能与 Python 漂移 | 低（已验证） | 双游戏 oracle、显式/混合类型、thin border、样式/列宽语义规范化与 Rust 全局零公式断言已固化 |
| `atomic::write` Windows 替换存在极短路径缺口 | 中 | 唯一临时文件、同步、备份与失败回滚已覆盖；virtualized AppData 的首写/替换 `CrossesDevices` 真机通过，安装环境仍需压力测试 |
| Tauri visualizer 子 frame 获得 Wry 初始化脚本或跨 workspace 浏览器状态 | 低（当前门禁已验证） | isolation origin 校验、visualizer CSP、opaque token、动态 localStorage scope、stale 409、A→B 真机与 `docs/desktop-visualizer-security.md`；Tauri/Wry 升级时重新关门 |
| 已安装每日任务仍指向不存在的 C 盘旧脚本 | 已清零（2026-07-15 最终卸载后任务不存在） | 真机已完成 candidate run+exact health、原子替换及 Running→Ready 重放；最终卸载复核任务、automation owner 和产品状态均不存在 |
| PowerShell launcher 丢失 native `$LASTEXITCODE` 或业务失败后前移 state | 低（runner/launcher 与真实任务均已验证，当前产品已卸载） | PowerShell 仅调用 `update run/health`；WinPS 5.1 与 pwsh 7 EAP/退出码 0/2/7 回归；成功 state 只由 Rust 事务提交 |
| 历史 NSIS/便携版与 active 发布可能过度声称完成 | 非当前交付阻断（旧链仍未签名） | 仅在用户明确要求启用旧链时重新核对 manifest、签名和安装边界；普通 Tauri 修复不引用它证明当前 EXE |
| 构建与验证缓存再次膨胀工作区 | 低（本轮再次清理 2.15 GB Release 缓存） | 保留当前 Tauri EXE及仍需留存的历史 bundle，及时删除 `target/debug`、Release 编译缓存、smoke 临时目录与 Git 临时垃圾，绝不删除 AppData 用户数据 |
| 外部数据源随时间变化 | 高 | 归档历史 raw 数据，黄金测试只用固定离线输入 |
| 子智能体共享工作树冲突 | 中 | 并行任务划定互斥路径；公共类型由主智能体串行整合 |
| pnpm/esbuild 构建审批或端口再次漂移 | 低（已验证） | 布尔 allowlist、packageManager/Node engines、5173 strict port 与根级复现脚本已固化；端口需避开 Windows excluded range |
| Rust 网络层误重试永久性 4xx | 中 | 按状态码分类，只重试瞬时错误并增加缓存/离线测试 |

## 三目标复盘

### 复盘 1：工作区治理（2026-07-12）

- 完成：归档并校验 761 个业务文件；清除约 4.49 GB Rust 构建缓存及 Node/Python 可再生产物；整理 `.gitignore`；提交 Rust/Tauri 源码基线；建立本文件。
- 偏差：首次归档安全检查因同级目录名称共享前缀而误拦截；修正为带目录分隔符的真实父子判断。缓存清理还发现绝对路径被重复拼接，确认归档已完成后单独补清。
- 失败原因：早期脚本把字符串前缀等同目录包含关系，并混用了绝对/相对缓存路径。
- 调整：不改变最终迁移目标；将“可靠存储与稳定数据根目录”提升到第二批，优先于 exporter 移植。
- 下一批：CLI 契约、存储/数据目录边界、规范化双跑基线。

### 复盘 2：兼容与基础边界（2026-07-12）

- 完成：新增 15 项 Python CLI 契约测试；加固唯一临时文件、同步、并发写和失败回滚；Tauri 改用应用数据目录并支持 `MIHO_DATA_ROOT`；建立 Python/Rust 共用规范化 fixture。
- 偏差：审计发现 Rust 百分比按比例值解析，和 Python 百分点语义相差 100 倍；已在继续 parser 前修复。Windows 标准库不能直接调用 `ReplaceFile`，当前实现通过备份和失败回滚保证可恢复，但替换时仍有极短路径缺口。
- 失败原因：初始 Rust scaffold 根据通用百分比惯例实现，没有先锁定项目既有语义；原子写设计低估了 Windows 替换差异。
- 调整：最终目标不变。第三批将 HSR/ZZZ parser 分开移植，并优先对齐 Rust CLI 默认值；暂不启用 exporter。
- 下一批：HSR parser、ZZZ parser、Rust CLI 默认值与门禁。

### 复盘 3：Parser 与 CLI 边界（2026-07-12）

- 完成：建立 HSR/ZZZ 脱敏 parser fixture 和双语言 oracle；Rust 强类型行模型覆盖阶段、角色使用率、队伍、签名、scope、rank 与 bangboo；Rust CLI 按游戏拆分 help 并对齐动态日期、路径、数据源、top-N 和布尔双旗标。
- 偏差：原共享 CLI 命令树会向 HSR 泄漏 ZZZ 命令，且 `ArgAction::Set` 不等价 Python BooleanOptionalAction；已重构为独立 HSR/ZZZ 命令树。原子并发测试曾由子智能体观察到一次权限错误，整合后连续 10 次未复现，保留为监测项。
- 失败原因：初始 scaffold 优先减少类型数量，牺牲了 help 面和游戏特定默认值；现已确认公共实现可共享，但公开命令类型必须分离。
- 调整：最终目标不变。进入 exporter 前先加固 HTTP/缓存并移植三个外部数据源，避免把不可靠网络语义扩散到导出层。
- 下一批：网络可靠性、Hugging Face 客户端、Prydwen/官方名称来源。

### 复盘 4：外部数据源边界（2026-07-12）

- 完成：HTTP 仅重试连接、超时、408/425/429/5xx；在线失败回退缓存，离线明确 cache miss；移植 HF URL/树响应、两游戏 Prydwen 固定输入和官方中英文名称映射。
- 偏差：两个来源模块初次注册后才暴露 HSR lifetime 编译错误，且子智能体只做了格式检查、没有把模块接入 Cargo 测试图；主智能体补充 Rust fixture 测试并用 clippy 严格验收。ZZZ 来源曾复制 slug 逻辑，已改为调用共享 normalize。
- 失败原因：为避免共享 `lib.rs` 冲突，子任务模块未注册，导致局部格式检查不足以发现类型错误。
- 调整：后续子智能体仍不直接修改共享入口，但必须提供可独立编译的临时检查方式；主智能体注册后必须补 Rust oracle，不接受只有 Python fixture。进入正式 exporter 前先统一产物写入和比较规则。
- 下一批：产物比较器、HSR 离线 exporter、ZZZ 离线 exporter。

### 复盘 5：核心导出产物（2026-07-12）

- 完成：统一安全相对路径、BOM/CRLF、固定表头、CSV quoting、JSON、SHA-256 manifest 与目录比较器；HSR/ZZZ 均能从固定强类型行生成四张核心表并通过字节级黄金对比。
- 偏差：初始共享浮点格式去掉 `.0`，不符合 Python float；ZZZ 手写 fixture 未包含第二条 usage 和 `raw_json`，不能作为真实 oracle。严格字节测试暴露后，改为 Python 实际输出、区分 parse_percent 浮点与 parse_number 整数，并启用 serde JSON 输入顺序保持。
- 失败原因：把“数值相等”误当作“CSV 表示兼容”，且子智能体的 ZZZ fixture 只验证列名，没有真正调用 Python exporter 生成值。
- 调整：坚持字节级固定输入比较，不再接受只检查文件存在或表头。当前仍是最小 bundle，不解除 CLI export 门禁；第六批补齐派生表和目录编排。
- 下一批：HSR 派生表、ZZZ 派生表、缓存快照到完整 bundle 的离线编排。

### 复盘 6：派生表与离线编排（2026-07-12）

- 完成：HSR 增加 latest、两类 team dedup、name map、tier 派生、overview/report；ZZZ 增加 latest、dedup、unresolved、tier 空表/report；引入带 schema、tree、failure 模拟和安全 raw 路径的 offline pipeline。
- 偏差：HSR 派生表当前只对 Python 冻结了表头/行数，并非所有文件都有字节 fixture；offline pipeline 目前一次只构建单 snapshot/mode，不能直接承载正式 CLI 的多版本合并。
- 失败原因：最初的 `build_minimal_*` API 以验证垂直切片为目标，继续叠加会导致每个 mode 单独创建并覆盖相同文件。
- 调整：保持 CLI 门禁。第七批先引入聚合 dataset 和通用 source trait，再补全剩余文件；只有完整目录测试通过才启用 export。
- 下一批：多 snapshot/mode 聚合、在线 HF adapter、剩余产物与 Excel 可选边界。

### 复盘 7：聚合模型与统一数据源（2026-07-12）

- 完成：HSR/ZZZ exporter 新增 dataset/slice API，跨 snapshot/mode 统一计算 latest、team dedup、name 与 tier；旧单切片 API 保留包装。新增 `SnapshotSource`，在线 HF 与离线缓存共用 tree/raw 接口，并以本地 HTTP 验证缓存落盘。
- 偏差：原计划一个“聚合模型”目标实际需要分别重构两套 exporter，形成两个独立子目标，因此剩余文件与 Excel 没有在本批实现。
- 失败原因：HSR/ZZZ 的列、队伍签名和派生规则不同，强行放在一个共享实现会重演早期命令树泄漏问题。
- 调整：接受两套聚合实现、共享 source/output 边界。下一批 generic pipeline 必须真正基于 trait 执行，而非保留当前 OfflineFixture 专用路径；CLI export 仅在完整表集合通过后解锁。
- 下一批：generic pipeline、剩余 HSR/空目录产物、CLI export 门禁解除。

### 复盘 8：Generic Pipeline 与受控 CLI 接线（2026-07-12）

- 完成：HF generic pipeline 现统一处理在线/离线、闭区间日期、未知日期保留、config/子树部分失败、真实来源元数据和空匹配；HSR 补齐 histograph、fallback、完整角色数值、latest/top 视图、name map 与两级队伍去重；ZZZ 补齐 Bangboo、phase flags、fallback name、latest 与队伍选择；CLI 完成目录写出和 0/1/2 退出边界。
- 偏差：原估计“补三张 HSR 表”实际暴露角色字段丢失、队伍 best/count/files 语义、动态列顺序、两游戏 phase flag、ZZZ Bangboo 与 name map 等底层缺口；范围扩大后才允许提交。CLI 原方案会把默认开启但未接通的补充来源只记 warning 并退出 0，复审后改为联网前门禁。
- 失败原因：前几批最小 exporter 只证明文件/表头垂直切片，不能代表完整目录语义；fixture 对成功路径覆盖较多，但对“目录存在却禁用下载”“仅队伍出现的名字”“历史期覆盖”不足。
- 调整：最终无 Python 目标不变，generic HF 假设已由本地 HTTP 与离线缓存逐产物一致验证。默认 CLI 切换延后；第九批先建立补充来源与 report context，再并行接通 HSR/ZZZ。Excel、visualizer 和决策报告不抢在默认导出完整之前。
- 下一批：补充来源/导出上下文契约、HSR 补充来源、ZZZ 补充来源。

### 复盘 9：补充来源与完整导出上下文（2026-07-12）

- 完成：建立版本化 request/context/receipt/failure 与结构化 diagnostics/stats；HSR、ZZZ 均接通 Prydwen visible/tier/changelog、HoYoWiki、历史、趋势、raw 和部分失败回退；两游戏补充选项门禁解除，产品级在线总门禁继续保留。
- 偏差：原估计主要是 adapter 接线，实际还需处理 HTTP 2xx 业务校验、双语任一侧失败、visible scope 保序、版本优先 latest、phase/usage/team 不同日期回填语义、短历史行、空 HF slice 全局名称和完全同分队伍稳定顺序。ZZZ 未因补充源完成而提前放开 HF-only 在线形式。
- 失败原因：此前最小 bundle 把名称和日期都隐含在 snapshot slice 中，不能表达“无 HF slice 但有 tier/name”或 Python 只回填 phase/team 的行为；外部页面成功状态也不能只用 HTTP 状态码判断。前端回归另暴露 `pnpm-workspace.yaml` 的 esbuild 审批仍是 scaffold 占位值。
- 验证结果：Rust workspace 111 项、Python 74 项与 workspace 严格 clippy 通过；前端 `pnpm --dir crates/miho-desktop build` 在干净依赖状态因 `ERR_PNPM_IGNORED_BUILDS` 失败，临时生成的 `node_modules` 已清除。
- 调整：最终无 Python 目标不变，继续保持在线总门禁。第十批先修复可复现 Tauri/Vite 构建，再用语义而非 XLSX 字节比较固化 Workbook，随后由共享 Rust writer 接入两游戏；visualizer 数据契约与等价 UI 排在下一批，决策报告不提前穿插。
- 下一批：可复现前端构建基线、双游戏 Workbook 语义契约、共享 Rust Workbook writer。

### 复盘 10：可复现前端与双游戏 Workbook（2026-07-12）

- 完成：固定 pnpm/Node/esbuild/Vite/Tauri 可复现构建；建立 HSR 18-sheet、ZZZ 12-sheet 脱敏 Workbook oracle 和语义比较器；共享 Rust writer 直接消费最终 CSV，覆盖显式/混合类型、两套样式、冻结/筛选/列宽、`0.00`、全局零公式、BestEffort warning、manifest/receipt 与 CLI 原子写出。离线双游戏 CLI 已默认包含 XLSX，在线门禁只剩 visualizer。
- 偏差：初版契约漏掉 pandas 表头四边 thin border，也会用 `EXTERNAL_TEXT` 同时掩盖 actual 公式；`rust_xlsxwriter` 与 openpyxl 对 RGB alpha、继承字体、solid fill 背景和连续列宽有不同但等价的 OOXML 表示。真实 HSR fixture 还发现 `special_rating` 同列可同时出现数值和 `E6` 文本，且旧 Rust `overview.csv` 将趋势、图表和 warning 固定为 0。视觉 QA 确认 HSR 两张 dedup 表有签名裁剪，ZZZ 维持 pandas 默认窄列的系统性截断；本轮按等价迁移保留，产品化阶段再改善。
- 失败原因：单行 oracle 能冻结主路径，却不足以揭示混合列与空数值格；最初比较器把库级 XML 表示误当业务语义；早期最小 exporter 的 overview 只验证了垂直切片，未随补充来源能力同步扩展。
- 调整：最终无 Python 目标不变。Workbook 采用显式语义规范化并对 Rust actual 独立执行零公式断言，不做 ZIP 字节追逐；混合类型必须按已知列声明，禁止全局自动推断。下一批先冻结 visualizer 的 `data.json`、静态资源、头像与动态字段边界，再分别移植 HSR/ZZZ，避免两套大型交互实现共享错误规则。
- 下一批：双游戏 visualizer 产物契约、HSR visualizer bundle、ZZZ visualizer bundle。

### 第十一批进度：visualizer 产物契约（子目标 1/3，2026-07-12）

- 完成：从两游戏完整最终 CSV、版本化 Banner/Decision sidecar 和预置本地头像生成脱敏 oracle；比较器严格检查 JSON 类型与数组顺序，仅允许 `/meta/localDate` 动态；目录集合、UTF-8/LF 静态哈希、逐目标二进制哈希、禁网、便携路径、XSS 载荷、URL traversal/active scheme 和 NaN/Infinity 均已锁定。Hub、HSR、ZZZ 的加载/切换/Box 交互与 XSS 标记已在真实浏览器冒烟通过。
- 偏差：初始半成品只缺 fixture 看似简单，但审计发现 ZZZ export 仍直接消费内存 rows，绕过独立 visualizer 的最终磁盘边界；Hub 目录名可进入 HTML 属性；旧 HSR 测试还要求远程头像下载失败后保留网络 URL。现已统一磁盘重建、编码 Hub 路径，并把失败头像明确降级为空。
- 最大困难：Python visualizer 实际还读取 raw Prydwen/HoYoWiki、phase override、Banner/Decision sidecar 与头像缓存，无法从最终 CSV 单独重建。若按原表述直接设计 Rust writer，会把隐式 cwd/文件探测复制进内核，并在 HSR/ZZZ 之间产生不同的隐藏依赖。
- 主流程审视与调整：不改变纯 Rust/Tauri 终点，但把后两目标的公共前置从“CSV reader”微调为“最终 ArtifactBundle + 版本化 VisualizerContext（clock、sidecar、avatar store/resolver）”。HSR/ZZZ 仍分别实现，先把 context/schema 和静态资产 writer 固定，再做各自 data builder；在线总门禁继续保持，不因 Python oracle 完成而提前解除。
- 下一步：先建立共享 Rust visualizer context、路径/URL/JSON 安全边界和静态资产 writer；随后迁移 HSR data builder，再迁移 ZZZ 的代理人/邦布/卡池/Decision 语义。

### 第十一批进度：HSR visualizer 共享边界（子目标 2 前置，2026-07-12）

- 完成：新增版本化 Rust `VisualizerContext`，显式承载 local date、sidecar 与预置 WebP；建立 HSR 编译期静态资源、共享头像附加、BOM/字符串保真的 CSV reader、紧凑 JSON、URL/traversal 与 WebP 完整性校验。静态文件、头像、精确 visualizer 文件集合和刷新后 manifest 均直接对照版本化契约。
- 最大困难：静态资源目录会被根级 `visualizer/` 忽略规则误吞，而且 `ArtifactBundle::write_to` 只做逐文件原子写出；若资源在 `refresh_manifest` 后才加入，实际目录与 receipt/manifest 会不一致。当前用精确反向 ignore 规则和“Visualizer 必须先于最终 manifest”测试消除第一类静默失败，脏目录清理仍留给可信 CLI adapter 处理，core 不扫描输出目录。
- 主流程审视与调整：共享 core 只接受显式头像 bytes/store，不复制 Python 的 cwd 与旧输出目录探测。HSR data builder 将从最终 CSV 字节重建并在 report/manifest 前附加；独立 CLI 负责按兼容优先级解析 Banner 与既有头像后构造 context。在线门禁保持不变，直到完整 JSON oracle、CLI、目录和浏览器验证全部通过。
- 下一步：实现 HSR `meta/trend/tier/changelog/chart` 直通集合，再按 phase → roster/official → usage → banner → team 顺序移植派生集合，并接跨语言黄金 harness。

### 第十一批进度：HSR visualizer 黄金 bundle（子目标 2 进行中，2026-07-12）

- 完成：Rust 已从 8 张最终 CSV、显式 Banner sidecar 与预置头像生成完整 HSR `data.json`；跨语言 harness 在中文/空格路径下严格比较 JSON 类型、数组顺序、精确文件集合和全部静态/二进制哈希，2 项新增黄金测试零差异。直通集合、phase、tier/usage roster、usage、Banner 合并与 team template 主路径均已进入 Rust。
- 最大困难：现有冻结 oracle 没有写入 HoYoWiki raw，因此它能证明 Prydwen/usage fallback 主路径，却不能证明正式 export 默认开启的官方 roster 合并。为避免“黄金通过”掩盖真实在线残缺，Rust 检测到 HSR HoYoWiki raw 时会显式失败，不允许生成部分 visualizer。
- 主流程审视与调整：HSR 在线门禁继续保持；下一步必须先移植官方中英 roster 的 entry id 合并、顺序、filter values、别名和图标优先级，并增加 Rust 原生分支测试。完成后再把同一 builder 接入独立 `visualizer` 和 export，最后做真实浏览器冒烟，不能仅凭当前单行 oracle 解锁。
- 下一步：补齐 HoYoWiki roster 与完整 phase/scope seed，再接可信 CLI adapter 的 Banner/旧头像读取、visualizer 子树替换和 manifest 刷新。

### 第十一批进度：HSR visualizer 完成（子目标 2/3，2026-07-12）

- 完成：HoYoWiki 中英 roster 已按 `entry_page_id`、双侧顺序、英文名门槛和首个 filter value 合并，官方-only、tier/usage fallback、alias、source、角色职能与本地头像优先级均有原生测试。HSR builder 补齐 16 个 phase 中文名、4 类机制、MOC/PF/AS/AA scope、team 精确 phase 回退/置换去重/来源排序/240 与 1000 限额、usage 按 mode+role 最高 rating、日期有效 Banner 与 banner-only roster，以及整数/非有限数值语义。
- CLI 与验收：独立 `miho hsr visualizer` 会从最终磁盘 artifact 显式加载 Banner 与旧 WebP；离线/在线 HSR export 在最终写出边界复用同一 core。输出先在同卷 sibling staging 完整构建，再通过 backup/swap 安装，失败回滚旧目录且新 manifest 只在整体成功后可见。致密跨语言契约 39 项、真实 CLI 整目录 JSON/文件集/hash 零差异、Rust workspace 131 项、Python 123 项与严格 clippy 通过。真实浏览器确认页面、Banner、Box 状态/练度可交互，XSS 标记为空且 console warning/error 为零。
- 最大困难：严格比较器本身没有问题，但原黄金只有单角色、单模式、单 team 和静态 Banner；“逐字段零差异”会掩盖跨行聚合键、精确 phase 选择、置换去重、rating 取优与日期状态没有被触发，形成已经完整迁移的错觉。
- 主流程审视与调整：HSR 门禁按预定证据解除，但后续不再把“严格黄金”自动等同“覆盖充分”。ZZZ 致密主路径黄金通过后，独立对抗复核发现 visualizer 间接调用 `miho_core.banner_plan.effective_banner_phases()`，实际使用含时分的 `datetime.now()`；此前只检查 visualizer.py 的直接 import 而得出 date-only 结论是错误的。共享 context 必须升级为显式版本化 datetime，并连带回归 HSR Banner；两游戏继续共享 ArtifactBundle/安全 writer，不共享各自排序与派生规则。
- 下一步：清零对抗复核的 datetime Blocker，以及 Decision 非有限/URL 类型、sidecar fallback、manifest ownership/stale 与 Hub High；随后重跑真实 CLI、Hub 浏览器和全量门禁验收。

### 第十一批进度：ZZZ visualizer 完成（子目标 3/3，2026-07-12）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：致密 Python/Rust oracle 与真实 `miho zzz visualizer` 已同时覆盖 phase raw 补偿/override、官方代理人和邦布、版本优先 team 去重、tier/usage 选择、Banner-only、Decision、头像、静态资源、精确文件集合和 sibling Hub；46 项 visualizer 契约、118 项 core、CLI 12+21 项、workspace 严格 clippy、Vite/Tauri build 全绿。浏览器从 Hub 切入 ZZZ，展示 3 组 Banner；Box 拥有状态和 60 级练度重载后仍保留；XSS marker 为 null，直达 ZZZ 页面 console warning/error 为零。Hub iframe 中两条 `MutationObserver` 错误来自 browser-client 注入，项目 assets 全局不存在该 API，故不归入应用日志。
- **主判断—最值得质疑**：最危险的不是主路径排序，而是 Python 间接依赖和失败边界：Banner 实际通过共享模块使用秒级 `datetime.now()`；`json.loads` 的 NaN/Infinity、指数溢出/下溢、任意精度整数、URL scalar、Unicode 日期数字、非法 UTF-8 与 surrogate；无 manifest legacy ownership；以及 ZZZ 写 sibling Hub 的事务顺序。原先 39 项绿色契约没有触发这些反例，若没有独立对抗复核会错误解锁。
- **独立对抗判断**：未参与实现的审查子智能体最终给出 `Blocker=0 / High=0` 并接受解除门禁。它逐项重放 NaN/Infinity/`1e400`、大整数/`1e-7`、NFKC/IPv6/zone URL、Unicode whitespace/数字/无空白/year 0000、invalid UTF-8/unpaired surrogate、legacy keep-me、phase/Banner/HSR numeric URL 与 Hub 事务反例，均与 Python 或预期安全失败一致。保留两个 Medium：合法 UTF-8 但整体 JSON 已坏且同时含 NaN 时 Rust 选择安全失败而 Python fallback；legacy `raw/hf/**` 是正式 managed 命名空间。一个 Low：date-range date-only end 的微秒上界与纳秒 context 存在理论最后不足 1 微秒边界。
- **主线程回应与处理**：所有 Blocker/High 均接受并修复，没有用文档豁免代替实现。`VisualizerContext` 升级为显式 local datetime；共享 Banner parser 对齐秒、date-only end、Unicode whitespace/Unicode 15 Nd、无空白和 year 1..9999；JSON 保留任意精度整数、按 Python binary64 规范化浮点并拒绝非有限输出；URL 对齐 falsey/数字 repr、大小写 scheme、IPv6/zone 与 NFKC authority；所有 raw/sidecar 先严格 UTF-8 并拒绝未配对 surrogate；Decision 原始字节进入 core；phase OSError fallback 保留；旧 manifest-managed stale 被清理，未知文件不晋升；Hub 与输出均用 sibling stage/swap，非法 Hub 在输出变更前预检。Medium 的安全失败差异获准保留并纳入兼容说明；`raw/hf/**` ownership 约束提升为项目级记忆。
- **最大困难与路线修正**：最大困难是“精确黄金已绿”仍可能没有覆盖 Python 的间接模块、Unicode/JSON parser 和长期 re-export 状态。主流程不改变纯 Rust/Tauri 终点，但后续 evidence/coverage/decision/pull-value/review-packet 必须先画出全部文件探测、clock/config 与失败语义，再建立对抗输入；不得只翻译主函数或只比较一个 happy-path Markdown。两游戏 visualizer 在线门禁现已解除，Python 保留为 oracle；第十二批转入决策与报告迁移，完成后再接 Tauri 后台任务/进度/取消。
- **最终验收**：ZZZ core、独立 CLI、export 与 Hub 共用同一最终磁盘重建边界；在线 gate 已解除。阶段提交前最后执行 `cargo test --workspace --no-fail-fast`、`cargo clippy --workspace --all-targets -- -D warnings`、`python -m pytest -q`、`pnpm run build` 与 `pnpm run tauri:build:no-bundle`。
- 下一步：盘点并冻结 evidence、coverage、decision、pull-value、review-packet 的输入/输出/排序/Markdown/失败语义，按共享 evidence core → coverage → decision → pull-value/review-packet 分解 Rust 子目标。

### 第十二批进度：Evidence V1 Python oracle 定标（子目标 1/3，2026-07-12）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：`evidence-first-v1-20260712` 已把同一 composition 按 mode 拆成稳定 `evidence_key`与内容 hash ID，并在单 mode 内计算 metric/app-rate/confidence。A 同时要求 mode policy、有效表现比例与游戏特定稳定组件；source/account confidence 分离，build 未知或未完成会降为 B。Pull 只能在 tier、usage 和 A/B 主证据同 mode 对齐时给高/中高，packet 内嵌稳定 key 与 trace。完整 159 项 Python、定向 46 项、bundle 的 10 个规范化 hash、`compileall` 和 `git diff --check` 全绿。
- **主判断—最值得质疑**：最危险的是“旧 Python 就是 oracle，所以只需冻结”。实际它会跨 SD/DA 比分、让未知 build 保持 A、让无 A/B 队伍的角色得到高优先级，且 E-ID 随无关计划改号。只做 happy-path Markdown hash 会把方法缺陷永久迁入 Rust。此外 stability adapter 与 account build 降档是保守方法政策，后续真实数据定标可能需要版本升级，但不允许无版本放宽。
- **独立对抗判断**：未参与实现的审查子智能体先后复现了 alias last-row-wins、NaN/Infinity usage 与 packet、PyYAML 静默 fallback、E-ID 随 plan 改号、build 未知仍 A、pull 跨 mode 拼接、Markdown 表列错位、缺 mode/部分队伍/未声明 mode policy、falsey built 被当真以及 HSR/ZZZ stability marker 串用等 High。最终重放所有反例后给出 `Blocker=0 / High=0`，并确认 159 项 Python、定向契约、`compileall` 与 diff check 通过。
- **主线程回应与处理**：上述 High 全部接受并以代码+反例清零，没有用兼容豁免代替修复。非有限值现在过滤或严格失败；alias 冲突和损坏 schema 不再生成“零 coverage”；coverage 预渲染、路径冲突预检并整批回滚。Rust evidence/coverage、decision、pull/review 门禁都没有因 Python oracle 完成而解除。
- **最大困难与路线修正**：最大困难是兼容迁移与方法正确性在此处直接冲突；“精确复制 Python”会违反项目已采用的 evidence-first 硬规则。主流程因此微调为先版本化区分 `legacy-v0` 与正式 Evidence V1，先修 oracle 再冻结 Rust 契约；不改变纯 Rust/Tauri 终点，也不删除旧兼容边界。
- **下一步**：以 `EvidenceInputsV1 + EvidenceRequestV1 + EvidenceContextV1` 实现共享 Rust evidence core，先对齐规范结构与排序，再接 evidence/coverage CLI 的命令级 stderr、0/1/2 和整批安装；完整跨语言与真实 CLI 契约通过前不解门。

### 第十二批进度：Rust evidence/coverage 完成（子目标 3/3，2026-07-12）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：Rust `EvidenceInputsV1 + EvidenceRequestV1 + EvidenceContextV1` 不读取 cwd/clock，已对齐稳定 E-ID/key、SD/DA 隔离、source/account confidence、sentinel/stability/build、duplicate 与 observation trace。致密 fixture 的四份 Markdown/CSV 在仅规范化临时根目录和生成时间后逐字一致；真实 `miho zzz evidence/coverage` 覆盖自定义不同父目录、JSON/YAML/UTF-8 BOM、0/1/2、命令级 stderr、manifest/visualizer 字节保留。最终 Rust workspace 174 项、Python 162 项和严格 clippy 全绿。
- **主判断—最值得质疑**：最危险的点不是 happy-path 数值，而是路径身份与 invocation context。core 黄金通过仍不能证明 CLI 只取一次本地时间，也不能证明词法不同的三个目标真是不同文件；进程在多文件 rename 中被强制终止的 crash-consistency 仍不等同于本阶段已验证的运行时失败回滚，继续作为存储层剩余风险，不在文档中夸大为断电原子事务。
- **独立对抗判断**：未参与实现的审查子智能体首次给出 `Blocker=0 / High=1`：Windows junction `alias/ -> real/` 可让 current/target 两条路径指向同一 `same.md`，命令仍返回 0 且 target 静默覆盖 current。主线程修复后，它重新构建 binary 并重放真实 junction CLI 反例：现返回 1，stderr 为 `coverage failed:`，旧 current/aggregate 字节不变，无 stage/backup 残留；最终结论 `Blocker=0 / High=0`。
- **主线程回应与处理**：接受该 High，没有用“用户不会传 junction”作豁免。`atomic::write_batch` 现在在任何 `create_dir`/stage 前遍历所有目标父链，跨平台拒绝 symlink，Windows 额外检查 `FILE_ATTRIBUTE_REPARSE_POINT`；新增父链 alias、路径碰撞、第二文件安装失败整批回滚反例。CLI 在消费命令前确定 failure prefix，报告 invocation 只捕获一次词法归一化绝对 cwd 与微秒截断 local datetime；debug 固定时钟不会进入 release。
- **最大困难与路线修正**：最大困难是同时保持“core 无隐式路径/时钟”和 Python 报告必须显示数据源、按当前时刻解析 Banner plan。路线调整为：可信 CLI adapter 一次捕获 `ReportInvocation`，把文件字节、显式 datetime 和仅用于展示的 source path 传入纯 core；输出作为 unmanaged consumer artifact 用独立批事务安装，不进入 export manifest ownership。后续 decision/pull/review 继续复用这一边界，禁止各命令重新探测 cwd/clock 或自行写 manifest。
- **下一步**：先固定 Rust decision 的 `legacy-v0` 兼容与 Evidence V1 正式边界，再迁移 pull-value/review-packet；任何高/中高抽取仍必须由同 mode A/B 主证据支撑。

### 第十二批三目标复盘（2026-07-12）

- 完成：五类报告依赖图与 LegacyV0/V1 分界、Evidence V1 Python oracle、Rust evidence/coverage core 与真实 CLI 均已提交前验收；门禁从“Python 方法正确”推进到“Rust 正式运行时可用”。
- 最大偏差与困难：原估计主要是翻译聚合/渲染，实际先修正了 oracle 的跨 mode、build 与高优先级证据缺陷，又发现精确黄金无法覆盖 CLI 时钟和 Windows junction 路径身份。若没有两轮独立对抗复核，会把错误方法或伪事务直接冻结进 Rust。
- 路线总结：保持纯 Rust/Tauri 终点；后续报告统一使用版本化纯 core + 单次 `ReportInvocation` + unmanaged 批事务 writer。第十三批先处理 decision 的兼容/正式方法双边界，再按 pull-value → review-packet/IPC 顺序推进，不把 LegacyV0 精确兼容误写成 evidence-first 完成。

### 第十三批进度：decision 产品边界审计（子目标 1 前置，2026-07-12）

- 完成：三个互斥只读子智能体分别审计 LegacyV0 精确契约、正式 Evidence V1 决策设计和可复用 fixture。共同结论是当前没有独立 Decision V1 的完整规则/schema；若临场发明，会与已经冻结证据门槛的 pull-value 产生两套正式结论。
- 产品收敛：`decision` 只保留显式 `--method legacy-v0` compatibility，固定读取六个 CSV、Box 和可选 rules，输出旧 `decision_cards.json`/`decision_report.md`；正式推荐只由 pull-value 生成，review-packet 不重算。旧 payload 为保留 hash 不新增 method 字段，版本在 CLI request/help/receipt 与 visualizer adapter 边界显式标记。
- 最有把握的依据：现有 smoke 已有四类决策和稳定 hash（JSON `65045aee…772d`、Markdown `d29a13b…7da8`），Python 代码明确展示全局最高 tier、跨 mode 最大 usage/最差 trend、`team_rank_raw.csv`、忽略 aliases 和 arbitrary force_decision；这些只能作为兼容行为，不能升级为 evidence-first。
- 最大困难与路线修正：最大困难是“迁移 decision”在命令名上看似正式推荐，实际只是一套旧 visualizer sidecar heuristic。主流程从“实现 Legacy 与一个新 Decision V1”修正为“Legacy compatibility + pull-value 唯一正式推荐”，减少重复规则和冲突 UI。下一步先物化 dedicated Legacy fixture，完成纯 Rust core、显式 method、两文件事务与独立对抗；随后直接进入 pull-value。
- 关键反例：planned union 中某 A 队同时依赖候选 A/B，不能在 A 卡上伪装成“抽 A 即可成队”；正式 pull 主证据只接受 `plan_dependency == [candidate]`，额外计划依赖只能进入 conditional risk。SD tier、DA usage、SD evidence 也不得拼成高档。

### 第十三批进度：Rust LegacyV0 decision compatibility 完成（子目标 1/3，2026-07-12）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：纯 Rust `DecisionLegacyInputsV0 + DecisionLegacyRequestV0 + DecisionLegacyContextV0` 已在显式 `--method legacy-v0` 下读取旧六 CSV、Box 与 rules，生成冻结的四类决策和完整嵌套 payload；JSON/Markdown 与 Python oracle 逐字一致。真实 CLI 只写 `decision_cards.json`/`decision_report.md`，通过共享批事务保持旧两文件、manifest 与 visualizer 不变，成功 stderr 明确 `compatibility only`。ZZZ visualizer 根字段同时固定 `decisionMethodVersion: legacy-v0`，旧 decision payload/hash 不加 method 字段。
- **主判断—最值得质疑**：最大漏测面不是四类决策主路径，而是 Python 动态类型边界。`dict.get` 的 key absent 与 present-null、`or` truthiness、`csv.DictReader` 的 ragged row、PyYAML 1.1 的 yes/off、merge、flow、八进制/六十进制/timestamp，以及 Python binary64 的 `1e-07` 表示，都可能在 serde/标准 Rust parse 下产生“语义看似相近、旧文件却不精确”的差分。非有限输入还必须在写出前失败并保留旧两文件，不能用饱和转换掩盖。
- **独立对抗判断**：未参与实现的审查子智能体持续用真实 Python/Rust CLI 构造反例，先后报告 visualizer method 标记、Box owned/cinema、字符串 truthiness、replacement 空值、raw team null、config presence/slice、team rank NaN/Infinity、有限指数表示、文本 Infinity 误拒、数字空白/underscore、ragged CSV、PyYAML 1.1/merge/flow/timestamp、missing/null/empty、quoted non-finite raw field 与 numeric-to-string repr 等 High。全部修复后，它重放所有已报告反例，最终给出 `Blocker=0 / High=0`，且无保留 Medium/Low。
- **主线程回应与处理**：所有 Blocker/High 均接受并转成门禁，没有以“Legacy 输入不该这样写”豁免。Rust Row 保留 header presence 与 missing cell；config adapter 显式区分 raw string 与数值消费字段；PyYAML adapter 对齐 1.1 scalar/merge；所有 Python `str(float)` 路径共用 number repr；非有限、timestamp 与批写失败在安装前终止。最终专用 Rust contract 15 项、CLI report 6 项、Python decision/visualizer 49 项与独立真实 CLI 复合差分均通过。
- **最大困难与路线修正**：最大困难是“精确兼容”不能靠翻译算法主体完成，真正工作量集中在 Python 运行时的 presence/type/parser/renderer 语义。如果继续用一个通用 serde helper 覆盖所有字段，会在安全数值和合法文本之间反复误判。主流程因此明确：LegacyV0 保留专用兼容 adapter，不外溢为正式方法；下一批 `pull-value` 使用版本化 typed schema 和 Evidence V1，不继承 Legacy 的宽松 YAML/CSV 动态语义。只读路线审计还发现 `review-packet` 与 Tauri IPC 被错误捆绑，现拆为 pull-value core/CLI → review-packet serializer/core/CLI → 共享报告 IPC/后台任务 → Tauri UI/visualizer 集成。
- **最终验收**：`cargo test --workspace --no-fail-fast` 共 191 项、`cargo clippy --workspace --all-targets -- -D warnings`、`python -m pytest -q` 共 165 项、Python compileall 与 `git diff --check` 全绿；独立结论 `Blocker=0 / High=0`。前端 Vite/Tauri 构建未受本批代码触及，继续沿用第十一批全绿基线。
- **下一步**：只迁移 Rust pull-value core + CLI，冻结 typed pull cards 与 current/next Markdown；高/中高仍必须由同 mode tier/usage/A-B 主证据和单候选 `plan_dependency` 支撑。`review-packet` 与 Tauri IPC 不并入该最小提交。

### 第十三批进度：Rust pull-value 正式推荐完成（子目标 2/3，2026-07-13）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：纯 Rust `PullValueInputsV1 + PullValueRequestV1 + PullValueContextV1` 直接复用 Evidence V1 的稳定 E-ID/key/trace，冻结 typed cards 与 current/next Markdown。未拥有候选只有 `plan_dependency == [candidate]` 的 A/B+/B 能进入主证据，多计划依赖只进入 conditional risk；tier、usage、证据必须同 mode 对齐。真实 `miho zzz pull-value` 支持默认双报告和显式合并输出，共用单次本地时钟并一次批事务安装，不刷新 manifest、visualizer 或 Legacy sidecar。
- **主判断—最值得质疑**：最大漏测面不是黄金 fixture 的高/中高公式，而是 Python 运行时与文件系统边界：同 rating 稳定排序、binary64 `round`、usage 聚合溢出、baseline 外层 key/内层 slug、原始 usage presence、PyYAML 1.1 `off/on`/merge/空文档、JSON/YAML 非有限数、Windows 扩展名大小写和 junction 都能在 happy-path 逐字一致时继续漂移。跨午夜时 visualizer fixture 还暴露了测试只冻结 Banner clock、未冻结 `localDate` 的基础设施缺口。
- **独立对抗判断**：未参与实现的两名审查子智能体先后用真实 Python/Rust CLI 报告 tier tie、baseline fallback/slug、raw usage rerun、mode 顺序、9.9995 rounding、finite-row 聚合溢出、identity falsey、PyYAML boolean/merge/empty/non-finite、大小写扩展、plan 1e400、Box ownership 与 junction 等 Blocker/High 候选。主线程逐项修复并转成回归后，终审重放全 YAML+BOM、current/next/combined、0/1/2、sidecar 保留和 Windows junction，最终结论 `Blocker=0 / High=0 / Medium=0`；仅保留一个维护性 Low：共享 PyYAML helper 暂位于 `decision_legacy.rs`，未来退役 Legacy 前必须迁到中性 config 模块。
- **主线程回应与处理**：接受所有语义与安全 High，没有以 typed schema 或“生产数据不会这样写”豁免。共享 config reader 现对齐 PyYAML 1.1 plain boolean、merge、空/falsey root、BOM 与非有限拒绝；机制 notes 先按 reviewed slugs 过滤，再按 yaml→yml→json 对每层逐文件校验，早层错误不能被后层覆盖。usage/tier/baseline 的稳定顺序、truthiness、rounding、overflow 和 falsey fallback 均有专用 Rust 反例；Python oracle同步收紧 exact dependency、空候选 notes 与 plan 非有限校验。visualizer 契约测试同时补齐固定 `date.today()`，消除跨午夜漂移。
- **最大困难与路线修正**：最大困难是“正式 typed core”仍必须精确承接 Python 的文件探测、PyYAML 与 binary64 语义，同时不能把 Legacy 的任意动态字段面扩散成第二套推荐规则。主流程不改变 Evidence V1 与纯 Rust/Tauri 终点，但把共享配置兼容提升为 Evidence/Pull 公共基础设施；后续应先把该 helper 从 Legacy 模块迁到中性 config 模块，再让 `review-packet` 只序列化同一批 Rust pull cards，禁止重新读取输入或重算结论。
- **最终验收**：`cargo test --workspace --no-fail-fast` 共 213 项、`cargo clippy --workspace --all-targets -- -D warnings`、`python -m pytest -q` 共 176 项、Python compileall 与 `git diff --check` 全绿；专用 pull core 14 项、真实报告 CLI 13 项，独立结论 `Blocker=0 / High=0 / Medium=0`。前端 Vite/Tauri 构建未受本批产品代码触及，继续沿用第十一批全绿基线。
- **下一步**：迁移 Rust `review-packet` serializer/core/CLI；它必须直接消费同一批 pull cards 与 refs，冻结 packet hash/trace、Markdown fence/JSON 安全、current/next 批事务和 0/1/2，并继续保持 Tauri IPC/UI 在下一独立子目标。

### 第十三批进度：Rust review-packet 完成（子目标 3/3，2026-07-13）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：专用 Python oracle、Rust core golden 和真实 Rust CLI 已共同冻结 current/next packet。规范化 SHA-256 分别为 current `893ee23ebc38135482165fbfda5c9cead737b35cab16734babfc8b0c7bde5461`、next `3dd1e707fd8d1f5ec801dfc5d2a241a669bf9468c7416a0f33e452ecb19886de`；字段顺序、stable refs/keys/trace 均逐字一致。直接篡改已有 bundle card 的 sentinel 后 packet 原样输出，证明 renderer 没有第二次计算推荐。
- **主判断—最值得质疑**：JSON 语义相同不代表 packet 字节相同；mechanism note 中的小指数、负零、大整数，以及 payload 的连续反引号、Unicode、跨行文本、路径和平台换行都可能破坏 hash 或 Markdown。默认 split 与显式 combined 还必须证明共用同一次时钟、预渲染边界和批事务，不能只验证 renderer happy path。
- **独立对抗判断**：未参与实现的终审曾发现一个 High：Python 把 `1e-7` 写为 `1e-07`，Rust 写为 `1e-7`。修复后真实 Python/Rust CLI 覆盖 `0.0000001`、`1e-7`、`1e+20`、`-0.0` 与大整数并逐字一致；五反引号 fence、Windows junction、第二文件安装失败回滚、notes precedence、0/1/2 和所有 consumer sidecar 保留均通过，最终 `Blocker=0 / High=0 / Medium=0 / Low=0`。另一静态审计仅保留一个非阻断 Low：合法路径自身含反引号时“相关文件”区 inline-code 显示可能异常，但 payload、JSON 与结论不受影响，且与 Python 既有行为一致。
- **主线程回应与处理**：接受 JSON lexical High，将 `normalize_python_json_numbers` 提升为共享 helper，补齐 `1e-07`、`-0.0`、大整数和整数 `-0` 回归。fence 固定为 `max(3, payload 最长连续反引号 + 1)`；CLI 复用 `run_zzz_pull_artifact`，只分叉文件名与 renderer，因此 card 构建、单次时钟、碰撞预检和批事务没有第二条规则链。
- **最大困难与路线修正**：最大困难是既要保持普通 packet 的旧 hash，又要修复固定 fence 注入和 Python/Rust 浮点指数格式；即便“只做 serializer”，仍存在 JSON lexical、Markdown fence、路径、换行和 ownership 风险。主流程不改变纯 Rust/Tauri 终点，但下一阶段必须让 IPC/Tauri 传递 typed request/bundle/context 并复用现有 renderer/事务所有权，禁止前端复制 serializer 或重算推荐。
- **最终验收**：`cargo test --workspace --no-fail-fast` 共 218 项、`cargo clippy --workspace --all-targets -- -D warnings`、`python -m pytest -q` 共 181 项、Python compileall 与 `git diff --check` 全绿；packet 专用 Python 5 项、Rust golden 1 项、真实 Rust CLI 3 项，独立终审 `Blocker=0 / High=0 / Medium=0 / Low=0`。前端 Vite/Tauri 构建未受本批产品代码触及，继续沿用第十一批全绿基线。
- **下一步**：进入共享报告 IPC/后台任务，随后接 Tauri 任务、进度、取消、错误和文件选择；自动化、发布、无 Python 环境验收与 Python 退役仍未完成。

### 第十三批三目标复盘（2026-07-13）

- **完成**：LegacyV0 decision compatibility、Evidence V1 `pull-value` 正式推荐与 `review-packet` 安全 serializer 均完成 Rust core/CLI 迁移；每个子目标分别提交或进入本次提交，并在独立对抗复核清零 Blocker/High 后解除门禁。
- **最大偏差与困难**：review-packet 的算法工作量很小，但 Python JSON lexical、动态 Markdown fence、Windows 路径/事务和 consumer ownership 仍足以造成 hash、安全或回滚漂移；“不重算”不能替代字节与真实 CLI 证据。
- **路线修正**：决策/报告 core+CLI 阶段至此收口。下一批不再新增推荐规则，而是建立共享报告 IPC/后台任务，把同一 typed pull-card 所有权、单次时钟、取消/进度和批事务带入 Tauri UI；之后再做自动化发布和无 Python 环境退役验收。
- **项目状态**：第十三批完成不等于整个项目完成；Tauri 产品化、自动化发布、计划任务切换与 Python 退役仍是剩余主线。

### 第十四批进度：共享报告应用层与安全 intent 完成（子目标 1/3，2026-07-13）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：新增 `miho-app` 后，CLI 中五类报告的 direct core renderer、输入探测和 `atomic::write_batch` 路径已全部删除；CLI 只拆分参数、构造 trusted native request、捕获一次 `AppInvocation` 并调用 `execute_task_v1`。app fixture、真实 CLI 黄金、junction 与 later-install rollback 都穿过同一 executor，decision 成功 notice 也保持原字节。
- **主判断—最值得质疑**：最大风险不是报告字节，而是把“共享 native request”误当成“安全 WebView wire”。最初 `TaskRequestV1/WorkspaceLayout` 仍可 `Deserialize` 任意 `PathBuf`，unknown nested 又会在 serde 阶段绕过 `TaskFailureV1`；若下一步直接挂到 `#[tauri::command]`，会形成任意本地文件读写面。同步 executor 目前也还没有取消 checkpoint，不能据此声称后台任务完成。
- **独立对抗判断**：两名未参与 CLI 集成的审查子智能体均把 pathful wire 与非结构化 parse failure 判为 High；另发现 decision notice 冒号变分号的 Low。修复后终审确认 pathless intent、malformed/unknown/schema failure、真实 CLI 五报告、Windows junction、第二文件安装失败回滚和 locked metadata，最终 `Blocker=0 / High=0 / Medium=0 / Low=0`。
- **主线程回应与处理**：接受两个 IPC High。`WorkspaceLayout/TaskRequestV1/TaskSpecV1` 及五类 pathful task 参数全部移除 serde，只能由可信原生 adapter 构造；新增不含 workspace/path/output/file 的严格 `TaskIntentV1`。`parse_task_intent_v1` 将 malformed/unknown 映射为 `request.invalid`，wrong schema 映射为 `request.unsupported_schema`，能安全识别时保留 operation；native 执行错误稳定为 `task.failed`。notice 恢复原冒号并锁入测试。
- **最大困难与路线修正**：最大困难是 CLI 为兼容必须接受任意用户路径，而 WebView 又绝不能获得同等权限；仅靠注释区分 trusted/untrusted 不足以形成安全边界。主流程因此从“把 CLI request 直接序列化给 Tauri”修正为“pathless intent → Rust 保存的 workspace/opaque selection → trusted native request → 单一 executor”。下一子目标必须先实现 workspace 授权和 TaskManager，再暴露薄 Tauri 命令。
- **最终验收**：`cargo test --workspace --locked --no-fail-fast` 共 223 项、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`python -m pytest -q` 共 181 项、Python compileall 与 `git diff --check` 全绿。一次与独立终审并发运行时既有 atomic concurrency test 遇到 Windows `PermissionDenied`；所有子智能体停止后该单测和全量均立即通过，未改生产代码。独立终审 `Blocker=0 / High=0 / Medium=0 / Low=0`。
- **下一步**：实现纯 Rust TaskManager 与 Tauri 薄命令，状态至少覆盖 queued/running/committing/succeeded/failed/cancelling/cancelled；同 workspace/output 互斥，commit 前取消不改输出，commit 后明确 too-late，事件丢失可由 get/list 补偿。
- **并行项目记忆**：自动化只读审计确认已安装 `MiHoYoEndgameDailyUpdate` 仍指向不存在的 C 盘脚本，旧 PowerShell 还可能忽略 native 非零码并错误前移 freshness state。它们不混入本提交，但已提升为项目 High；TaskManager/UI 后应优先实现单一 Rust update runner，再切换计划任务。

### 第十四批进度：TaskManager 与 Tauri 薄后端完成（子目标 2/3，2026-07-13）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：`TaskManager` 对五类真实 executor 的每个 `atomic::write_batch` 都在同一 `ExecutionObserver::before_commit` 门前线性化；首版全局单活动消除进程内同/异 operation 并发。Tauri 只接收 `workspace_id + intent_json`，native picker 产生并持久化真实路径，WebView capability 未授予 dialog open。public snapshot/artifact/failure、capabilities 与 workspace summary 均有路径/原始错误 canary。
- **主判断—最值得质疑**：最大漏测面是取消、旧 worker 收口和事件轮询的竞态。A 在 observer 取消后若提前释放 active，旧 worker 可能清掉后继 B 的锁并让 C 并发；普通 error 也可能被 cancel request 错报为 Cancelled。50ms 只取最新 snapshot 还会让快速任务从 event seq 1 跳到 4，虽然 query 有 history，实时事件仍不完整。进程被强杀、掉电与 GUI/CLI 跨进程并发则仍超出本阶段承诺。
- **独立对抗判断**：独立审查先后给出两个 High。第一轮用确定性 A/B/C barrier 证明 cancelled A 会抹掉 B 的 active；第二轮证明轮询 monitor 会漏发 Running/Committing/Cancelling。主线程逐项修复后，终审重放 app/desktop 30 项、strict clippy、连续事件分页和 public payload，最终 `Blocker=0 / High=0 / Medium=0 / Low=0`。
- **主线程回应与处理**：observer 取消不再释放 active，所有 worker 收口均 compare-and-clear 当前 task ID；普通 executor Err 即使已有 cancel request 仍为 Failed，只有明确 control cancellation 才为 Cancelled。spawn 失败回滚 queued/active，panic 转 `task.panicked` 且 manager 可继续接单，poison lock 可恢复，ID 含 pid/epoch/manager counter。`public_updates_since` 按真实 status history prefix 重建 seq 1..N，Desktop monitor 用游标逐条补发；Succeeded 最后一条才含 artifacts，Failed 最后一条才含安全 failure。
- **最大困难与路线修正**：最大困难是让 UI 状态与磁盘事实共享同一个 commit 决策点，同时又不能把 native 路径、panic/error 链带进 WebView。路线从“spawn blocking + abort + 最新 snapshot 轮询”修正为“合作式 commit permit + 全局串行 + native/public 双快照 + 可分页历史事件”。下一阶段前端只能使用 public 类型与权威 query；不得直接打开 dialog plugin 或接触 native receipt。
- **最终验收**：`cargo test --workspace --locked --no-fail-fast` 共 244 项、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`python -m pytest -q` 共 181 项、Python compileall、`pnpm run build`、`pnpm run tauri:build:no-bundle` 与 `git diff --check` 全绿。TaskManager 10 项、Desktop 13 项；独立终审 `Blocker=0 / High=0 / Medium=0 / Low=0`。
- **明确延期边界**：当前只承诺进程内全局单任务和可查询的内存历史；不承诺 GUI/CLI 跨进程互斥、TaskManager shutdown/join、进程强杀/掉电后的 journal/recovery。capabilities 明确返回 abrupt/cross-process false，底层 atomic 的既有 crash-consistency 风险没有被扩大为已解决。
- **下一步**：安全重写前端 DOM，接 capabilities/workspace/task query/event/cancel 与正式 pull/review 入口；随后实现受限 visualizer 资源/Box 协议桥。前端和 visualizer 通过后才开始 Rust update runner、计划任务切换与发布验收。

### 第十四批进度：安全前端与 visualizer 协议桥完成（子目标 3/3，2026-07-13）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：main WebView 的所有动态内容都经过 `createElement/textContent/replaceChildren`，任务事件只唤醒权威 query；公开 task/workspace/artifact/failure schema 不含路径或 raw error。桌面 visualizer 只执行编译期 index/app/styles，workspace 仅提供有界 data/avatar/Box；每个请求先校验短期 opaque access token，localStorage 另用 canonical workspace SHA-256 stable scope。Windows WebView2 已真实渲染双游戏数据/头像、完成 Box 写入、A→B 空 Box 无回灌、B→A、settings revision 2→3→4 和重启 persisted=4。
- **主判断—最值得质疑**：最危险面不是 UI happy path，而是 Windows Wry 会向子 frame 注入初始化脚本、同源 localStorage 会跨 workspace 延续、异步 Box/任务响应会跨 game/revision 回写，以及 virtualized AppData 即使 sibling rename 也会返回 `CrossesDevices`。真实 DevTools 还要求绕过 self-XSS paste barrier 才能直接执行 iframe `invoke` probe；该保护没有被绕过，因此直接攻击调用不是本批证据。
- **独立对抗判断**：早期审查把 Wry 子 frame IPC 与固定 localStorage A→B 回灌列为 Blocker，并把 `.miho`/报告输入 junction、跨 workspace 异步响应列为 High；主线程以 Tauri isolation、workspace gate/token/scope 和 generation 复核修复。最终未参与实现的终审又发现三个 High：Box GET 无界及 compact 通过但 pretty 落盘超 1 MiB、data/avatar readiness/GET 无界读取、把会话 access token 当 storage identity 导致重启/重选后 browser-only Box/REC 丢失。修复后终审重放 34 项 desktop、7 项 atomic、strict clippy、Vite 与 diff-check，最终 `Blocker=0 / High=0`。
- **主线程回应与处理**：接受全部 Blocker/High，不以“用户选择了 workspace”视作任意字节可信。Box 的 GET metadata、深度 32、pretty JSON+LF 1 MiB 由 main/protocol 共用；data 限 64 MiB、avatar 限 8 MiB，readiness 对头像只查安全 metadata。access token 只负责请求授权，stable storage scope 负责同一物理 workspace 的重启恢复。设置首写和已有目标 backup/install/rollback 都支持 synced-copy `CrossesDevices` fallback；source 删除失败会撤销新 target。强杀/掉电中间态仍明确 `abrupt=false`，没有被误报为原子恢复。
- **最大困难与路线修正**：最大困难是“一个 iframe”实际上横跨主 origin、custom protocol origin、isolation origin、浏览器 storage origin、Rust workspace revision 和 Windows 虚拟文件系统；单独依靠 CSP、sandbox、session token 或单元测试都不能覆盖完整链。主流程由“嵌入静态 visualizer + CSP”修正为“isolation 前置 + 编译期代码/可变数据分层 + 短期 access/stable storage 双 identity + 全 route fail-closed + 有界 allocation + Windows 真机 A/B/restart”。该契约固定在 `docs/desktop-visualizer-security.md`，Tauri/Wry、storage identity 或 visualizer schema 变化时必须重新关门。
- **最终验收**：`cargo test --workspace --locked --no-fail-fast` 共 268 项、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`python -m pytest -q` 共 181 项、Python compileall、`pnpm run build`、`pnpm -w run tauri:build:no-bundle` 与 `git diff --check` 全绿；release 产出 `target/release/miho-desktop.exe`。真实 DevTools 观察到 main、visualizer、main isolation frame，visualizer 自身 isolation child 被 CSP 阻断；结合 generated Context isolation 测试与上游 origin 校验作为 IPC 证据，未把未执行的 console probe 写成通过。
- **下一步**：第十四批至此收口。立即进入单一 Rust native update orchestrator + failure receipt，修复旧 PowerShell `$LASTEXITCODE` 假绿后再原子切换计划任务；随后补 NSIS/portable 的 CLI/config 资源，完成无 Python 安装/升级/卸载/计划任务矩阵，最后退役 Python runtime。

### 第十四批三目标复盘（2026-07-13）

- **完成**：共享报告应用层、纯 Rust TaskManager/Tauri 后端、安全任务前端与双游戏 visualizer/Box 产品桥全部完成；每个子目标都在独立 Blocker/High 清零后解除门禁。
- **最大偏差与困难**：原计划把前端与协议桥视为一个常规 UI 子目标，实际暴露了 Wry 子 frame IPC、浏览器跨 workspace storage、reparse 输入、无界本地资源和 Windows AppData `CrossesDevices` 等系统级边界；真机证据推翻了多项只靠 Rust 单测成立的假设。
- **路线修正**：Tauri 产品集成今后必须把 isolation、短期授权 identity、稳定 storage identity、allocation limit 和真实 Windows A/B/restart smoke 当作前置。自动化阶段不得继续拼接 Python/PowerShell 业务链，而应先建立一个 Rust update runner 和单一 failure receipt，再迁移外部计划任务。
- **项目状态**：第十四批完成不等于整个项目完成。export 后台任务、更新 runner、计划任务切换、NSIS/portable 完整打包、无 Python 验收与 Python runtime 退役仍是剩余主线。

### 第十五批进度：native update orchestrator 完成（子目标 1/3，2026-07-13）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：`miho update run` 已把 HSR → ZZZ → coverage → pull-value → review-packet 收敛到一个 Rust owner 和一把 `.miho/workspace-write-v1.lock`；任一所选步骤失败都退出 1、保留 failure receipt 且不前移成功 state。canonical/state/每游戏 generation receipt 同时绑定精确 config SHA-256，`update health` 重读每个 artifact 的 size/hash。真实双进程竞争、从父 cwd 发起的 direct writer、杀死 owner 后重获 lease、完整成功/逐步骤失败/receipt 安装失败均走同一生产边界。
- **主判断—最值得质疑**：最危险的漏测面是“看起来有 receipt/锁”但仍能假绿或越界：update 若复用 last-good HF cache 会把旧数据伪造成 freshness；direct CLI 若按 cwd 而非输出父 workspace 取锁可绕过 runner；canonical/attempt/history/artifact 任一祖先 junction 都可能让 health 读到工作区外证据；PowerShell 7 的 native error preference 与 `ErrorActionPreference=Stop` 可能把真实 2/7 改成 1；Windows virtualized 路径的 `CrossesDevices` 若只覆盖 install、不覆盖 backup/rollback，会在错误路径破坏旧目标。当前 installed task、NSIS/portable 与无 Python 安装矩阵仍未验证，不能由 runner 单测外推。
- **独立对抗判断**：两名未参与实现的终审分别重放网络 500/不可达/200 非 JSON、cached bytes、父 cwd 双锁、真实双进程、owner 强杀、custom Hub、state/canonical/attempt/generation digest 篡改、receipt/artifact junction、PowerShell 5.1/7 EAP 和 backup/install/rollback `CrossesDevices`。最终一致结论 `Blocker=0 / High=0`。其中一名审查者的 atomic 并发压力首次遇到既有 Windows `PermissionDenied` 抖动，精确重放 1/1 与主线程全量 workspace 均通过，保留为监测项而未伪装成未发生。
- **主线程回应与处理**：接受早期审查提出的全部 Blocker/High：update 专用 HF policy 禁止 online fallback，direct export/report、TaskManager 和 desktop Box writer 统一 OS lease；锁 identity 改为真实输出父 workspace；receipt/state/history/artifact 在读取前逐组件拒绝 reparse；generation receipt 加入 config digest；自定义顶层 HSR/ZZZ 输出名进入 Hub；batch backup/install/rollback 全部支持 synced-copy fallback；`native_command.ps1` 精确保留 native exit。所有修复均有反例测试，没有用文档豁免替代实现。
- **最大困难与路线修正**：最大困难是 freshness、互斥、证据和 Windows 文件系统其实是同一条提交协议，分散修补脚本、CLI、TaskManager 或 health 任一层都会留下可绕过的第二事实源。主流程因此从“修旧 PowerShell 后切任务”微调为“Rust owner + config-bound receipts/health + 全 writer lease 先闭环，再把安装资源放进稳定位置，以 candidate run+health 作为计划任务切换事务的唯一提交门”。强杀/掉电完整恢复仍不冒充已解决；旧 task、打包和无 Python 矩阵进入后两个显式子目标。
- **最终验收**：`cargo test --workspace --locked --no-fail-fast` 共 325 项、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`cargo fmt --all -- --check`、`python -m pytest -q` 共 181 项、Python compileall、PowerShell 5.1/7 回归、`pnpm run build`、`pnpm -w run tauri:build:no-bundle` 与 `git diff --check` 全绿；release 产出 `target/release/miho-desktop.exe`，`scripts/build_rust_app.ps1` 同时要求 release `miho.exe`。独立终审 `Blocker=0 / High=0`。
- **明确延期边界**：已安装 `MiHoYoEndgameDailyUpdate` 仍指向不存在的旧 C 盘脚本，WorkingDirectory 为空；Ready 与迁移前 `LastTaskResult=0` 不是健康证据。本子目标不声称该任务、NSIS/portable 资源、无 Python install/upgrade/uninstall 或 Python runtime 已迁移。
- **下一步**：把 `miho.exe` 与默认 config 放入安装/portable 最终位置，建立 installer-owned candidate action；只有 candidate `update run` 和 config-bound `update health` 成功后才替换旧任务，并验证失败回滚、升级和卸载所有权。

### 第十五批进度：安装、计划任务与发布事务（子目标 2/3 进行中，2026-07-14）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
- **主判断—最有把握**：安装与 portable 现在共用版本化 workspace bootstrap、automation coordinator、candidate generation、显式 attempt ID、config-bound `update run/health` 和 ownership manifest；NSIS/portable 同时携带 `miho-desktop.exe`、`miho.exe`、默认 configs 与 automation。发布 wrapper 从隔离源码和全依赖树构建，冻结 staging，先校准再反向提取 NSIS 内嵌 patched PE，以同一字节身份生成 portable/ownership，最终逐文件复核容器。Rust workspace 432 项、freshness fixture 连续 5 轮、PowerShell 5.1/7 release contract 与 full verification build 提供实现证据。
- **主判断—最值得质疑**：最危险的误判是把“生成了 setup.exe、CLI/GUI 能启动”外推成正式发布或已迁移外部任务。当前真实 `MiHoYoEndgameDailyUpdate` 仍 Disabled 且指向不存在的 C 盘脚本；fixture/隔离 registry 不能代替真实 create/run/health/replace/rollback。EXE 与 NSIS 未签名，无 Python clean install/upgrade/uninstall、跨账户/跨 session release lease 和强杀恢复矩阵仍未完成。
- **独立对抗判断**：未参与实现的发布终审首先指出，早期 verification manifest 在测试修复后不再绑定最新 workspace digest，旧产物不得继续冒充“最新”；又把 clean/full 自动写 active 而不接收项目门禁输入列为条件性 High。主线程接受两项并修复；终审还发现批准参数一度误加在 writer 而非最终 assertion，已在 actual full build 前纠正。最终独立重算 workspace `760088f7…e2afe`/262、Git status `3f2c003b…cefca3`/41 与 manifest 精确一致；ZIP 20 个 managed + manifest、NSIS、17 个 ownership + self 共 18 个 container records、active/pending/context 残留和未签名声明全部闭环，结论 `Blocker=0 / High=0`。严格只读终审没有重新执行会写临时目录的 NSIS `/MIHO_VERIFY_STATIC`，但已复核本次 build 的 content-addressed receipt、NSIS 哈希与全部源记录，不构成 High。
- **主线程回应与处理**：没有用“测试改动不影响 EXE”豁免 provenance；runtime input digest 有意只覆盖根 Cargo/Node 输入、`configs/`、`scripts/` 与 `crates/`，而 manifest 的 `source.commit/status` 绑定构建时精确 clean HEAD，因此测试或文档提交后旧 manifest 仍只能作为历史证据。Vite 6 空 `.vite-temp` 只允许在普通且为空时清除；Tauri 只做一次 `build --no-bundle`，随后 calibration/final 两次 bundle 不重新链接；最终 installed main identity取自真实 NSIS 内嵌 patched PE，非主静态路径和字节必须精确相同。测试又暴露 TaskManager fixture 保留 canary repo/revision，以及 nonblocking TCP fixture 分段读取导致 1/2/3 次重试抖动；分别改为 fixture manifest 身份和 blocking+timeout+完整 header 后，全量复验通过。
- **最大困难与路线修正**：最大困难是 source、dependency、Tauri PE patch、NSIS container、portable、installer ownership 和 publication approval 不是七个独立检查，而是一条不可自证的发布事务；任何“最后再改一行测试/文档”都会让旧 provenance 失效。主流程因此从“clean full build 自动 active”修正为“所有 build 默认 verification-only + 项目门禁显式批准”，并把反向容器提取、外部 hash/启动冒烟和独立终审保留为最终提交前证据。外部任务替换与无 Python 真机矩阵继续守门，不因 verification build 成功而提前标完成。
- **当前验收**：`cargo test --workspace --locked --no-fail-fast` 432 项通过；freshness native-runner 18 项连续 5 轮通过；WinPS 5.1/pwsh 7 `test_release_contract.ps1` 通过；CLI `--version/--help` 与桌面 5 秒启动冒烟通过，冒烟创建的 portable `data/` 已精确清理并恢复静态文件集合。最终源码稳定后的 full verification manifest、ZIP、两个 EXE 与 NSIS SHA-256 由 ignored `target/release/bundle` 外部清单留痕。
- **明确延期边界**：本进度只证明候选事务与 verification-only 打包可复核，不批准 active，不切换真实 Disabled 任务，不声称签名、真实安装升级卸载、隔离 PATH/无 Python、跨账户 lease 或 Python runtime 退役完成。
- **下一步**：在独立终审清零后提交本阶段实现；随后以最终候选包完成真实 clean install → candidate run/health → 旧任务替换 → upgrade/rollback → uninstall/ownership → 无 Python 矩阵，最后才允许 `-ProjectGatesApproved` 和 Python 退役。

### 第十五批进度：真实安装/任务/无 Python 矩阵完成，待最终 active 构建（2026-07-15）

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试或上一轮候选漏掉的点是什么？
- **主判断—最有把握**：最强证据不是 fixture，而是同一未签名 NSIS 候选 `6ec4167352004e2ea59f635ad507b2b646c18abf33346cfc524cf018a044bf47` 在真实 Windows 状态上完成一条故障升级事务和一条成功升级事务。故障事务 `89e573fb08fa4469ba2d83543389a9c9` 在 `VerifyDynamic` 人为删除 Start Menu shortcut 后 setup 精确返回 1603，durable failure receipt 记录 `mode=VerifyDynamic`，自动 `Rollback → Finalize` 后事务根删除；旧静态文件、owner、task generation、快捷方式的哈希/Target/WorkingDirectory、注册表 typed tree 与 DACL 共 23/23 项精确恢复。成功事务 `773a62f27536475b9e986a1e4ebbee03` 返回 0，owner UUID 保持 `6c5f0da3-5687-46de-82cf-0109ccd60822`，18 项静态 payload 零差异，新 CLI SHA-256 为 `b5e0a03628d6264bf3844c46d0dc2422f002c626434be5ea1e4abef42cd4345e`，exact health `installer-f73aa4c7dec04e359a6b125c714db503` 对两游戏均 healthy；全程空 PATH 且没有 Python 进程。
- **真实外部矩阵**：canonical Task Scheduler V2 真实重放 Running→Ready，`LastTaskResult=0`，只观察到最新 Rust generation，Python PID 基线和新增均为空，health attempt 为 `20260714T224216568791Z-49264-0`。portable `da37cf6c08db125a` 的 ZIP SHA-256 为 `faa82fb16083f9aabba03d223902b82dbc2694066d840142eefe7620a2ebdb9c`；空 PATH/零 Python 下 CLI version/help、桌面存活 5 秒和 online update 均通过，online attempt 为 `portable-20260714T2305363268742Z` 且两游戏 healthy。
- **卸载与用户数据边界**：最终 uninstall 返回 0，零 Python；安装根、计划任务、automation owner、产品/卸载注册表和快捷方式全部不存在。`%APPDATA%\com.miho.endgame` 的 753 文件、520 目录、297,219,938 字节整树摘要在卸载前后均为 `a650910ec18ec50542d980cd926f3ae46c5c7b9e8cc1a6e001b6f5cb689076cc`；只保留契约允许的 0 字节 installer lease 文件。用户数据不是清理目标。
- **主判断—最值得质疑**：上述候选来自 dirty-source verification 构建，只能证明真实矩阵，不能成为“最新代码最终 EXE”。当前最危险的过度外推是直接复用它，或在文档/独立终审/提交前使用 `-ProjectGatesApproved`。最终 active 字节还必须由 clean HEAD 重建并重新校验 source/manifest、NSIS/portable 容器、CLI/桌面启动和 `Authenticode=NotSigned`。本轮终审又要求移除虚假的 Delete AppData UI/死分支并前移发布 scratch cleanup，发布输入因此会改变；最终 NSIS 至少必须补一次真实 clean install → ownership/shortcut/registry/task/health → uninstall/AppData canary smoke。跨账户/跨 session lease、安装中强杀/掉电 journal recovery 与正式代码签名仍无证据，不能因矩阵通过而宣称完成。
- **回归与瞬时失败留痕**：WinPS 5.1 与 pwsh 7 下 scheduler、installer transaction、native exit、release contract 共 8/8 通过；Rust fmt、strict clippy、Python 181、compileall、Vite 与 Tauri `--no-bundle` 通过。Rust workspace 首轮 435 项中 `invalid_date_is_a_business_error` 曾瞬时失败一次；手工 stderr 精确正确、定点连续 20/20 后独占全量 435 项通过。该事件不抹除，后续若再次出现应优先检查并发/本地 HTTP fixture，而不是放宽业务断言。
- **磁盘治理留痕**：删除 `target/debug` 释放 11,931,918,213 字节，删除 superseded bundle 释放 228,960,673 字节，删除 portable smoke `data/` 释放 304,733,131 字节；当前工作区约 2.47 GiB。最终 active 构建完成前仅保留与上述矩阵绑定的 NSIS/portable 及各自 release/static manifest；最终产物替代后立即删除这些 verification artifacts。
- **独立对抗判断（首轮）**：未参与实现的 `Epicurus / release_adversarial_review` 只读核对实际 21 文件完整 diff和真机证据，给出 `Blocker=0 / High=2`。High 1：uninstaller 可见 Delete AppData 复选框，但 template/hook 又把状态强制归零，界面承诺与“始终保留用户数据”政策相反。High 2：active manifest 发布后 `finally` 仍执行可失败 calibration/scratch 清理，可能出现 active 已替换但 wrapper 返回失败。终审同时确认真实矩阵候选的 release input digest `f41bb5b7a473cfd0f9cb5e06b042cbe65421d7d3fb42b632f000f9eb4dfd1d6e`/262 在首轮审查时未漂移。
- **主线程回应与处理**：两项 High 全部接受，不做文档豁免。卸载模板已删除复选框、状态变量、hook 强制归零与两个 AppData 递归删除分支；静态回归同时拒绝 UI/hook token 和 `%APPDATA%`/`%LOCALAPPDATA%` 递归删除。发布 wrapper 新增单一 prepublication helper：退出 isolated cwd 后先删除 calibration 与两类 scratch，全部成功才允许 atomic publish；cleanup poison 时旧 active 字节不变且 ephemeral pending 被删除，解除 poison并重建 pending 后才可替换。发布成功后的显式 lease dispose 异常只降级为 warning，避免把已完成发布误报为失败。WinPS 5.1 installer transaction/release contract 与 pwsh 7 installer transaction/release contract 全部通过，`git diff --check` 通过。
- **独立对抗判断（二次终审）**：Epicurus 对稳定 diff 复核后结论 `Blocker=0 / High=0`。它确认 AppData UI/实现/契约已统一为始终保留，prepublication cleanup、pending 删除策略、active 原子替换和发布后 lease warning 边界一致；没有新增阻断。终审同时要求：两项修复已改变真机矩阵后的 installer/release 源码，最终 active 不得只靠旧候选交付；至少执行一次真实 clean install → 静态 payload、shortcut Target/WorkingDirectory、registry/owner/task 与 candidate health → uninstall ownership/AppData canary smoke。只有后续再改 upgrade/journal/rollback 逻辑时才必须追加故障升级回滚。
- **最大困难与路线审视**：最大困难是“通过真实矩阵的旧候选”和“来自最终 clean HEAD 的交付字节”天然不能是同一次构建：真实矩阵需要先验证改动，而文档/提交又会推进 Git commit identity，即使 runtime input digest 不变也会使旧 active 不再代表当前 HEAD；本轮还证明，表面上“始终保留用户数据”和“构建结束会清 scratch”若仍保留相反 UI 或放在 publication 之后，就会形成第二事实源。主流程因此不循环重跑整套破坏性矩阵，也不复用旧候选：先用 content-addressed verification 候选封闭升级/回滚门禁，独立终审修正契约，再提交 clean source 构建 active；由于修复触及 uninstall UI/发布事务，最终字节必须补容器/manifest、CLI/GUI 和一次真实 clean install/uninstall+AppData canary smoke。若该 smoke 暴露 upgrade/journal/rollback 字节漂移，则升级为故障升级回滚复验，不能用路线说明豁免。
- **下一步**：取得二次独立 `Blocker=0 / High=0` 并提交当前阶段；确认 clean 后运行 `scripts/build_rust_app.ps1 -Release -ProjectGatesApproved`，验证最终 active manifest 和未签名状态，执行最终 NSIS clean install/uninstall+AppData canary smoke，清理所有被替代 verification 产物，再交付 EXE/ZIP 路径与 SHA-256。

### 第十五批完成：最终 active 发布、Python runtime 退役与强杀恢复补证（子目标 3/3，2026-07-15）

> 历史说明：本节记录迁移发布阶段当时的门禁；其中“任何 tracked 提交都重建 active”的通用规则已于 2026-07-16 被上方“当前执行方式”和决策记录取代。涉及 runtime inputs 的重建要求仍然有效。

- **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被已有矩阵或 active manifest 漏掉的点是什么？
- **主判断—最有把握**：首次 active 收口的最强证据是 clean commit `85ed31d6636f91f7ff24fa78724c62f508042aa6` 的 262 个 release inputs 与 manifest 精确绑定，workspace digest 为 `edbf6c4de848b88e1341c6e17c7ee98498fa830dab33c2e756f1a256a0a78c3a`。该次 NSIS SHA-256 `a807a21a6efe57f579c5552192661a9c4cc6918fb54b9e090c82e0db4f73f66b`、portable ZIP `89d7b51893864c5dcf818a8aaaedb47ef134e366d86814237efc2a3dddc1b660`、static manifest 与 ZIP/目录 21 项均被独立重算，publication 为 `active`，scratch/pending/verification manifest 均为 0。后续 evidence commit 的交付字节同样必须由 active manifest 自证，而不是复用这些历史哈希。
- **最终字节真机证据**：portable 在空 PATH 下 `miho --version/--help` 返回 0、桌面存活 5 秒后正常退出且零 Python。最终 NSIS clean install 返回 0，18/18 static payload 精确匹配，Start Menu Target/WorkingDirectory、owner、canonical task 与 HSR/ZZZ exact health 全部通过且零 Python；uninstall 返回 0。卸载前后的 AppData 都是 755 文件、520 目录、297,294,737 字节，整树 SHA-256 均为 `0c0637cb2c971c96c749f3efa38112815b0c2585e30c7fbb2aef8d34242f2c28`，canary 未变；最终安装根、automation root、task、owner、产品/卸载注册表、快捷方式和 failure/transaction receipt 均不存在。
- **主判断—最值得质疑**：active 只证明发布时刻的 clean snapshot，不应被误写成“以后任意 HEAD 都与该 EXE 相同”；正式 Authenticode、跨账户/跨 session release lease、完整 NSIS Prepare/Commit 任意切点强杀与物理掉电仍无证据。当前 medium-integrity 非提权令牌能注册 interactive task，但 S4U 非交互 task 注册精确失败为 `0x80070005`，因此没有用同 session 子进程冒充跨 session 通过。
- **强杀恢复新增证据**：`tests/powershell/test_installer_transaction.ps1` 从生产 helper 精确生成临时插桩副本；在第一项静态文件达到精确 size/hash 后真实 `Kill/WaitForExit`，恢复进入 durable `rolling-back` 后再次强杀，最后只用原始未插桩 helper 恢复。Windows PowerShell 5.1 启动的测试在内部对 WinPS 5.1/pwsh 7 各跑一轮，82.4 秒完成并输出 `installer-transaction-tests: PASS`；恢复后 clean before-image、owner、install root 与 transaction root 全部清零。该门禁只覆盖两个精确进程终止切点，不外推成掉电、partial upgrade 或 scheduler/registry 恢复中任意位置。
- **独立对抗判断**：最终 active 发布前，Epicurus 对 AppData 卸载边界和 prepublication cleanup 修复二次终审为 `Blocker=0 / High=0`；本次又逐行核对 fault injection、signal、journal phase、partial payload、真实进程退出与原始 helper 收口，首轮为 `Blocker=0 / High=0`。稳定四文件 full diff 终审随后给出 `Blocker=0 / High=1`：能力报告的“当前外部状态”混入前序 verification 的 753 文件摘要，与首次 active 的 755 文件摘要冲突。修复为明确区分两轮历史并说明 canary 后续清理后，复审为 `Blocker=0 / High=0`。提交 `2ada434` 后的中间 active 又以 manifest 反证出第二个文档 High：Git commit 已变化但 runtime workspace digest 正确保持 `edbf6c4d…`，说明旧文案把 Git provenance 和 runtime input digest 混为一谈；终审要求 PROJECT、能力报告与 release contract 全部拆清两者，并以 `manifest.source.commit == HEAD` 守最终交付。
- **主线程回应与处理**：接受“两个 crash point 不等于完整掉电恢复”的限制，也接受两项文档 High。能力报告现分别标记 verification 与首次 active，并把产品当前外部状态单独写为清零；provenance 现拆为完整 clean Git commit/status 与有界 runtime input digest，明确后者不含测试/文档且在 evidence-only commit 后可以不变。最终交付只接受 manifest source commit 精确等于当前 HEAD。跨 session 的权限失败保留为真实结果，不降级成跳过即通过。Python 退役按产品愿景定义为 runtime 退役：安装、CLI、桌面、update、health 和计划任务均不启动 Python；Python 源码继续作为黄金 oracle，避免删除可复核基准。
- **最大困难与路线微调**：最大困难是发布后证据回填会推进 Git HEAD，而 active manifest 必须永远指向它实际构建的 immutable commit；若要求 tracked 文档同时写入“未来构建产生的哈希”并让该构建又包含这份文档，会形成不可满足的自引用循环。主流程微调为：精确 source commit/hash 永远只由 active manifest 留痕，tracked 文档记录门禁与历史证据但不预写未来值。runtime input digest 不包含测试/文档且可保持不变，但 manifest 仍记录精确 `source.commit/status`；因此本次 evidence commit 必须在提交后从新 clean HEAD 重建 active。重建产生的新哈希直接留在 manifest，不再为抄写哈希制造第二个 dirty 文档提交。
- **磁盘治理**：删除 `target/debug`、被替代 bundle/verification artifacts、portable smoke `data/`、可再生 release 编译缓存和 Git 临时垃圾后，最终工作区实测约 0.91 GiB；只保留 active manifest、NSIS、portable 目录/ZIP 与 static manifest。
- **阶段结论**：第十五批三目标及七阶段迁移主线完成。程序为可验证的 Windows active 内部发布版，运行时不依赖 Python；每个后续 tracked 提交仍须完成 clean active 重建才能作为“当前 HEAD”交付。`NotSigned` 和其余扩展可靠性边界仍是明确限制，不被“完成”措辞掩盖。

### 发布收口补正：AppData 保留门禁纠偏（2026-07-15）

- **显式提问**：本轮最有把握的证据是什么？最可能被已有门禁漏掉的点是什么？
- **主判断—最有把握**：生产 `installer.nsi` 与 `installer-hooks.nsh` 已不包含 Delete AppData UI/token 或 AppData 递归删除，但 Rust 静态回归仍反向要求旧 token 存在。第一次定点命令因 `--exact` 少模块前缀而实际运行 0 项，没有计为通过；按完整测试名重跑后精确在旧断言处 1/1 失败。修正为 installer/hook 负向断言后，同一测试 1/1 通过，`cargo fmt --all -- --check` 与 `git diff --check` 通过。
- **主判断—最值得质疑**：只把正向断言改成负向 token 断言仍可能漏掉不带旧 UI 变量、直接写入 hook 的 `RMDir /r`，尤其是额外 `/REBOOTOK`、flags 换序或 `${BUNDLEID}` 子路径变体；文档中“checkbox clear”的旧措辞也会重新形成第二事实源。旧 `650c3f0` active 因 tracked 修正而只能作为历史证据，不能继续交付。
- **独立对抗判断**：Epicurus 首轮给出 `Blocker=0 / High=1`，要求同一条递归 AppData 删除正则同时扫描 Uninstall section 与 hooks，并清除不存在 checkbox 的文档表述。主线程全部接受；门禁加入三种危险反例和两种安全反例后，WinPS 5.1 启动并覆盖 PowerShell 5.1/7 的 installer transaction 测试 81.2 秒通过，旧政策 token 扫描 0 命中。二次复核为 `Blocker=0 / High=0`。
- **主线程回应与路线微调**：测试不是天然可信的旁观者；当生产政策删除一个旧分支时，静态断言和说明文档都必须作为同级事实源反向审计。主流程因此固定为“正确测试全名确认红测 → token 与危险行为双门禁 → 恶意/安全 regex fixture → 双壳事务测试 → 独立复核清零”。本提交推进 HEAD 后必须从新 clean HEAD 重建 `ProjectGatesApproved` active，再做 NSIS AppData canary；新 commit/hash 继续只由 active manifest 留痕，不在本文预写未来产物哈希。
- **最大困难**：最大的困难是一个仅位于 `#[cfg(test)]` 的错误断言既不会改变 release 二进制行为，却位于有界 runtime input digest 的 `crates/` 范围内；不能用“只改测试”豁免 provenance，也不能为追求 clean manifest 而保留已知红测。解决方式是接受一次新的提交、active 重建和真机 canary，并在交付后立即删除由定点 release 测试产生的可再生缓存。

### 发布收口补正：installed owner 注册表读取与 GUI 启动门禁（2026-07-15）

- **显式提问**：本轮最有把握的完成证据是什么？最值得质疑、最可能继续被已有发布门禁漏掉的点是什么？
- **主判断—最有把握**：旧安装版 `D:\Miho Endgame\miho-desktop.exe` 在约 25 ms 后以 101 退出，stderr 精确为 `installed automation owner identity is invalid`；同一现场的 owner `9d8fbf93-afa2-45dd-8a06-5cb0da2ec3af` 在注册表、automation-owner 与 authority JSON 中完全一致。直接复刻 Win32 调用证明第一次 `RegGetValueW` 容量探测返回 76 字节，第二次成功读取返回 74 字节；旧代码把两次长度不相等误判为损坏。修复把第二次成功返回值视为实际长度，在拒绝小于 2、奇数或超出容量后截断 UTF-16 buffer，再沿用严格 `REG_SZ`、单末尾 NUL、无 embedded NUL、canonical lowercase UUID 校验。合成 76→74 回归与真实唯一 HKCU `REG_SZ` 测试均通过，真实测试键由 guard 删除且不再留下空父键。
- **真实启动证据**：修复后的 debug 桌面与精确 `installer/task_scheduler_v1.ps1` 组成完整临时 installed-mode 布局，在保留现有 owner、task 和 AppData 的情况下建立非零主窗口，持续存活 5 秒，正常 `CloseMainWindow` 后退出 0，stdout/stderr 均为空。裸跑 `target/debug/miho-desktop.exe` 因缺少相邻 installer probe 脚本而 fail-closed，只是一个不完整布局负例，不能反向推翻完整 staging 的正向证据，也不能被包装成第二个产品 bug。
- **主判断—最值得质疑**：当前最危险的盲区是历史发布只做 portable desktop 5 秒冒烟；portable marker 会绕过 installed-owner 注册表读取，因此可以在安装版必闪退时仍然全绿。debug staging 也不能替代最终 NSIS 字节，旧 active manifest 和已经安装的 EXE 都必须失效；只有从本轮 clean commit 构建完整 NSIS，以升级方式保留真实 owner，再从安装目录观察窗口、5 秒存活和正常退出，才可交付。
- **独立对抗判断**：未参与实现的 `win32_registry_review` 与 `Epicurus / release_adversarial_review` 分别审查 Windows API 边界及稳定四文件 full diff，结论均为 `Blocker=0 / High=0`。两者确认第二次返回长度的下界/偶数/容量约束、truncate-before-parse、类型/NUL/UTF-16/canonical UUID fail-closed、76→74 与真实 HKCU 回归均闭环；Epicurus 另核对三份追踪文档和现有 3/3 定点、85/85 desktop lib、clippy/fmt、完整 staging 5 秒证据一致。Win32 审查只留下两个低级备注：Drop 清理原先未检查返回值，以及 `RegGetValueW` 可能给原始缺 NUL 的值补 terminator。
- **主线程回应与路线微调**：两个低级备注均正面处理：正常测试路径现显式断言 `RegDeleteTreeW` 成功，Drop 只作 assertion-failure fallback，测试后枚举残留键为 0；release contract 改为精确声明“校验 API 返回表示”，不再过度声称拒绝注册表原始字节。主流程不把单元测试或 portable 成功外推成产品可用。`docs/release-contract.md` 已把 installed GUI 启动固定为独立项目门禁：owner/task 存在、`MIHO_DATA_ROOT` 未覆盖、完整安装布局、非零窗口、至少 5 秒存活、正常关闭与退出 0 缺一不可；退出 101 或 setup-hook 错误直接阻断交付。测试范围按改动面收敛到 owner 回归、整个 `miho-desktop` lib、严格 clippy、fmt 和真实 installed-mode 启动，不重复运行与本缺陷无关的 435 项全 workspace。
- **最大困难**：最大的困难不是解析 UUID，而是先前“桌面能启动”的证据来自另一条 portable 分支；它看起来覆盖同一个 EXE，实际上跳过了安装身份和计划任务绑定。主流程必须把包容器正确、portable 可启动和 installed 可启动视为三个独立事实，最终 NSIS 启动不得再由 portable smoke 代证。本提交推进 HEAD 后先构建 clean full `verification-only` 候选，用其精确 NSIS 在旧安装现场完成原位升级和 installed GUI 补证；独立复核清零后，同一 clean HEAD 才能用 `-ProjectGatesApproved` 重建 active。active NSIS 必须与已测候选哈希相同，否则还要对 active 精确字节重跑 installed smoke。精确 commit、产物哈希与签名状态继续只写入 ignored manifest，避免 tracked 文档自引用。

### 发布收口补正：生产前端嵌入与真实 DOM 门禁（2026-07-16）

- **显式提问**：本轮我最有把握的完成证据是什么？最值得质疑、最可能被窗口存活或 fixture 契约漏掉的点是什么？
- **主判断—最有把握**：用户截图明确是 WebView2 `ERR_FILE_NOT_FOUND`，不是业务界面或数据损坏。owner 修复让候选越过旧的 25 ms / exit 101 后，首轮完整 dirty build 的真实页面门禁仍抓到 `file:///.../release-staging/.../frontend-dist`，且没有发布 verification manifest。源码追踪确认 Tauri 2 的 untagged `FrontendDist` 按 `Url`、`Directory`、`Files` 顺序反序列化；生成 overlay 写入 Windows 绝对路径，使 codegen 进入 URL 分支而不嵌入资产。修复现从 isolated build workspace 的 `crates/miho-desktop/src-tauri` 生成到 immutable staging 的相对路径，producer 与 staged verifier 都拒绝 rooted/backslash/absolute URI/reparse/错误 round-trip；workspace `custom-protocol` 精确映射 `tauri/custom-protocol`，所有 release Cargo/Tauri pass 强制携带，release entry point 缺失时编译失败。
- **真实候选证据**：修复 staged verifier 后，完整 dirty `scripts/build_rust_app.ps1 -Release` 在 1144.2 秒后 exit 0，生成 verification-only closure；候选 desktop SHA-256 为 `cde1cecb8c03dd7fc98c1d224f08b7ed77b29b01cfc9ac3544c5edca46b55950`，并与 portable、static manifest 和 NSIS 18/18 反向容器映射精确绑定。installed-mode GUI 回执为 `https://tauri.localhost/#miho-app-ready-v1`、`data-miho-app-ready=v1`、DOM `complete`、品牌 `MIHO ENDGAME`、app child count 2、Tauri internals true、error page rejected true、至少 5 秒、正常退出 0、空 stdout/stderr、后代与调试端口清理、未观察到 Python；owner/task/workspace/Roaming AppData 未变。默认 installed WebView cache 的预期写入单独披露为 SHA `08cffe88…` → `5fd02fab…`、`+1391` bytes。release workspace/staging/context 最终均清零，工作区回落约 1.12 GiB。
- **主判断—最值得质疑**：最危险的误判仍是把 dirty 临时 installed layout 的成功外推成“用户当前安装已修”或“active 可交付”。用户的 `D:\Miho Endgame` 和 active manifest 仍指向旧坏字节；200 ms bound-snapshot 进程采样也明确不等于连续 ETW 审计。fixture 契约能证明路径算法和错误页拒绝，却不能替代最终 PE 的嵌入结果；因此还必须从本提交后的 clean HEAD 重建 verification-only，用其精确 NSIS 原位升级现有 owner/task 现场，复核安装目录 DOM、AppData、任务 exact health 与零 Python，再决定 active。
- **独立对抗判断**：未参与实现的 `candidate_release_review` 从本机 Tauri CLI/helpers、tauri-macros、tauri-codegen 与 tauri-utils 源码核对真实 `config_parent`、URL-first enum 和 Directory embed 分支，并在稳定脚本哈希下独立重跑 WinPS 5.1 / pwsh 7 release contract，结论 `Blocker=0 / High=0`。它随后把成功 GUI receipt 与 desktop、portable、static manifest、NSIS 18/18 closure 交叉绑定，再次给 dirty verification 阶段 `Blocker=0 / High=0`。文档首轮复审另报 `Blocker=1 / High=1`：PROJECT 尚无本阶段留痕，且 README/傻瓜说明的“最新安装包”无法在多代 bundle 中唯一定位；首轮修正清零这两项后又发现 `High=1`，因为两处恢复文字把历史首次 active 矩阵写成当前可用。统一改成“历史首次 active/既有矩阵”并明确修复版 pending 后，提交前复审一度为 `Blocker=0 / High=0`。扩大到最终 staged diff 后又发现 `High=1`：cache scope 只按 Mode 硬编码，真实 WebView2 可被环境或策略重定向到外部目录，旧默认 cache 存在时 receipt 仍可能假绿；修正后同一审查者核对 child env、实际 listener PID/start/command line、唯一绝对路径、退出后 no-reparse、build receipt 和反例，最终结论 `Blocker=0 / High=0`，仅保留已披露的 200 ms sampling/本地恶意端口竞态低级边界。
- **主线程回应与流程微调**：接受 staged verifier 仍要求绝对路径这一首轮构建反例，改为与 producer 相同的 `src-tauri` round-trip，并加入绝对、`file:///` 和错误相对目录三类永久反例；双壳 release contract 与 GUI contract 均通过。接受文档 Blocker/High，README 和傻瓜说明改为只认本次最终交付块中的绝对路径、完整 content-addressed 文件名、SHA-256 与 `NotSigned`，禁止按时间猜“最新”；能力报告与恢复入口也不再把历史矩阵冒充当前修复版。另接受测试卫生低级意见：owner fixture 的随机叶子删除后只在 `tests` 父键确实无子键、无值时非递归删除，并断言叶子零残留；现场历史空测试键经 0/0 复核后已精确删除。最终双壳 release contract 后父键实测 absent。对 cache scope High 也全部接受：probe 先移除继承的 `WEBVIEW2_USER_DATA_FOLDER`，再绑定实际 debug listener 所属 `msedgewebview2` 进程代际，解析唯一 `--user-data-dir` 并要求精确等于受快照父树覆盖的 `EBWebView`，关闭后再做无 reparse 核验；缺失、相对、重复、空值、外部路径和恶意环境 override 反例在 WinPS 5.1/pwsh 7 GUI contract 均通过，双壳 release contract 分别 43.4/87.9 秒通过，真实 dirty installed DOM 冒烟返回 `webview_user_data_directory_bound=true`、正常退出 0。
- **最大困难与路线微调**：最大困难是“窗口能活五秒”跨越不了 Tauri 配置反序列化、codegen 嵌入、WebView origin、真实 DOM 和浏览器副作用范围五层边界；绝对路径在 Windows 和 JSON 上看似合法，却因 untagged enum 顺序改变了产品语义，默认 cache 目录存在也不等于浏览器实际使用它。主流程由“窗口/alive/close”升级为“feature 编译保护 → 相对路径 producer/staged verifier → immutable bytes/容器绑定 → exact `tauri.localhost` → 真实 frontend sentinel/品牌/Tauri internals → error-page 拒绝 → 实际 `--user-data-dir` 绑定 → installed 外部状态差分”。dirty 候选只关闭实现盲区；提交后仍按 clean verification → 原位升级 → installed health/DOM → 独立复审 → 同 commit active 的顺序推进，不能跳步。
- **最终收口**：clean commit `1f8352be0bbcdae3c306be603bac010338cb343c` 已发布 active，最终 NSIS 原位升级实际安装目录后重新通过 DOM、计划任务 Ready → Running → Ready、HSR/ZZZ exact health、用户数据/owner 保留和零 Python检查。当前交付已完成，后续改进按“先完成、再优化”的新流程单独处理。

### 产品入口补正：Box、Visualizer 与角色头像（2026-07-16，已完成）

- **显式提问**：本轮最有把握的修复证据是什么？最值得质疑、最容易被“页面能打开”掩盖的点是什么？
- **现场原因**：旧桌面把工作区、导出、slug 文本框、报告和技术任务历史放在 Visualizer 之前；桌面 textarea 与 iframe 又会写同一 Box，存在用旧 `builds` 覆盖新修改的竞态。生产 HSR/ZZZ visualizer 分别有 92/59 个 roster，但头像 URL 为 0/92、0/59，头像目录也不存在；此前 readiness 对零头像引用空集通过，因此“health 通过”没有证明头像可用。
- **Box 恢复**：从业务归档的 `.miho` 恢复并与现场安全合并，当前 HSR 为 57 人、SHA-256 `66C6A38D762EB0D3D1392EBD31FCBC3F30B603B9FEC597D54AF2C9A1A495245F`，ZZZ 为 20 人、SHA-256 `C677733006B569CBFB96EB95BF1827FB26A58292C1F17A9180AC7FF01E4D7491`。回执位于 `%APPDATA%\com.miho.endgame\.miho\recovery\20260716-081526Z-box-recovery-v1\receipt.json`；正式更新、冷启动、双游戏切换和重启后哈希均零漂移。
- **最小产品修复**：Visualizer 成为首屏并默认进入“我的 Box”；旧 slug textarea 和第二个 `save_box_state` 写入口删除；更新、报告、运行记录与工作区进入默认关闭的“更新数据、生成报告与设置”。任务改成人话，运行编号、状态流水和 artifact kind 收入“技术详情”。desktop Box 采用 server-first：本机 API 成功读取后才初始化可编辑 UI，desktop localStorage 不再自动反写磁盘；用户修改按 revision 串行 PUT，失败明确显示“保存失败，请重试”。静态独立 Visualizer 仍保留浏览器缓存模式。
- **头像生产修复**：release 内置按 `game + canonical slug + SHA-256` 固定的 151 张权威 WebP seed（HSR 92、ZZZ 59）。每次正式导出重建都会注入；已知 slug 的错误旧缓存由 seed 覆盖，未来未知 slug 仍可保留。当前生产更新已重建到 HSR 92/92、ZZZ 59/59 非空本地 URL，151 个文件哈希互异且路径 basename 与角色 slug 一致。
- **定点证据**：Vite desktop build、头像 Rust 3 项、visualizer core 23 项、desktop lib 85 项、相关 Python 11 项、PowerShell GUI contract、严格 clippy/fmt 与 `git diff --check` 均通过。installed-mode staging 的跨源 iframe 深测连续两次冷启动通过：首屏/折叠工具区/默认 `#box` 正确，HSR 57/92、ZZZ 20/59，151 张图全部实际解码，basename/slug 零错配、无空图片，ZZZ → HSR → ZZZ 不串 Box，正常退出且调试端口无残留。按完成优先规则未重复运行与改动面无关的全 workspace 435 项和 Python 181 项。
- **主判断—最有把握**：旧 Box 已有可复核来源、独立回执、精确人数和稳定哈希；头像缺失生产者和双 Box 写入口也都有源码与生产目录直接证据。最终 active 精确字节已经从 `D:\Miho Endgame` 完成两轮深层 DOM 验收，第二轮位于正式计划任务重建 Visualizer 之后；真实角色卡、151 张图片解码、游戏切换、正常退出和端口关闭均不是由编译成功外推。
- **主判断—最值得质疑**：同一 clean commit 的 verification 与 active PE/NSIS 字节不同，候选验证不能跨构建复用；自动化也只能证明头像的 canonical slug、文件存在、唯一哈希和浏览器解码，不能等同逐张人工目视画面语义。本轮已用 active manifest 的精确字节原位安装、任务后复测和 canonical seed 来源链闭环；以后每次发布仍必须按 active 精确字节重验，并继续披露 `NotSigned`。
- **独立对抗判断**：首轮 Box 复审报 `Blocker=0 / High=3`：一项针对旧的异步启动顺序，另两项针对一次性恢复脚本的并发与双文件失败安全。当前两套 app.js 已逐项证明在 `init/render` 前 await 权威 GET，desktop 不从 localStorage 反写；恢复脚本随后从交付面删除，只保留成功回执与哈希证据。二次复审为 `Blocker=0 / High=0`。post-active 终审又先因 active 与 verification 字节不同、缺少 active 精确 GUI 回执而报 `Blocker=1 / High=0`；补齐 active 原位安装、两轮 ZZZ → HSR → ZZZ 深测及任务后复测后，独立读盘交叉核对安装字节、151 张 live WebP、Box、owner、任务、receipt、health 和零残留，最终为 `Blocker=0 / High=0`。
- **发布与真实入口收口**：clean commit `dc9b802a230018d35dfe5a77920bdd7f9560e031` 的 active NSIS 为 `D:\Projects\终局内容提取\target\release\bundle\nsis\Miho Endgame_0.1.0_x64-setup.sha256-c54e3bd244f4b6f82ea7e681bfc850d95184ad0064c7e43b724c7e2987ff43a2.exe`，SHA-256 `c54e3bd244f4b6f82ea7e681bfc850d95184ad0064c7e43b724c7e2987ff43a2`，签名 `NotSigned`。原位升级后 desktop 为 `44bd4a7a87fda24895129728476000ed2e086ecb7c44e31889f8eb1e4d65b3bb`，CLI 为 `f4b504a9ca28fa656d37579bfa92ec00fb499f3277c4eac3f436a52229558d60`，与 active portable 闭包精确一致。安装后及正式更新后均为 ZZZ 20/59 → HSR 57/92 → ZZZ 20/59，151 张图全部解码、空图 0、映射错误 0；Box 首屏、工具区关闭、技术任务 ID 不可见、正常退出 0、stdout/stderr 空、调试端口关闭。
- **自动化与中断留痕**：第一次 active 安装的候选 attempt 在持续正常写入缓存 92 秒后以 `0xC000013A` 中止，Task Scheduler Operational 当时未启用，不能声称已定位外部终止者；正式 token-only rollback `995ca2c722bd4100b63dce85e48fe7cb` 恢复旧任务/manifest/generation 并生成 `rollback-receipt-995ca2c722bd4100b63dce85e48fe7cb.json`。第二次不受外部等待中断的 active 安装越过同一位置并成功，旧 attempt 被 runner 标为 `interrupted`；正式任务随后明确 `Ready → Running → Ready`，`LastTaskResult=0`，attempt `20260716T103004147851Z-7900-0` 为 succeeded 且 state/receipt committed，exact health 为 `healthy=true` 并精确检查 HSR/ZZZ。owner registry/authority/manifest 三处仍为 `9d8fbf93-afa2-45dd-8a06-5cb0da2ec3af`，Box 两哈希零漂移。
- **空间清理**：先前已删除可再生 `target/debug`，释放约 15.9 GiB；最终 active 验收后又删除 installed UI staging、release 编译 scratch、旧 verification/旧 active 候选，共释放 2.386 GiB。`target` 最终约 0.083 GiB，D 盘空闲约 289.75 GiB；active manifest、content-addressed NSIS、portable 闭包、安装目录、AppData、Box/recovery、production owner/task/generation 均保留。

### 卡池与终局数据新鲜度补正（2026-07-16，已完成）

- **显式提问**：本轮最有把握的证据是什么？最值得质疑、最容易把“文件里有数据”误当成“用户页面可用”的点是什么？
- **现场根因与来源**：生产数据没有丢失；HSR 有 2,878 条 usage、11,313 条 team、13 条 banner，ZZZ 有 4,428 条 usage、1,663 条 team、10 条 banner。误报来自 `hsr_banner_plan.json` 停在 4.3，以及页面没有区分“数据未生成”和“当前筛选/阶段为空”。HSR 4.4 当期以米游社官方[4.4版本活动跃迁（其一）](https://www.miyoushe.com/sr/article/76661906)为依据：姬子•启行持续 2026-07-15 至 2026-08-25 15:00；火花、丹恒•腾荒、长夜月为 2026-07-15 至 2026-08-05 11:59。新角色仍不因卡池公告直接获得强度结论。
- **最小产品修复**：HSR 当期恢复为四名五星；卡池所选阶段为空时自动落到首个有记录阶段；空态分别显示“卡池数据未生成”和“当前搜索/阶段无匹配”。双游戏终局页显示最新采样日期及“当前周期 / 历史样本 / 周期未知”，筛选为零时仍从该模式全量数据给出采样日期；过期推荐统一为“当前数据包尚未包含新周期统计，仅作历史参考”。Python oracle 与 Rust runtime 前端保持精确一致；功能提交为 `45ff3629ef41baa08f8bd1611b94fa368f950692`，发布校验修复为 `7f670774dd71fcee22fe33b33b308823b7b2f85e`。
- **active 与安装**：权威 manifest 已为 `publication.state=active`、source commit `7f670774dd71fcee22fe33b33b308823b7b2f85e`。NSIS 为 `target/release/bundle/nsis/Miho Endgame_0.1.0_x64-setup.sha256-3bd32aa2af94a6e1efb83b51926bd66ffa911faf6ffc587e270768bac660f4b2.exe`，SHA-256 `3bd32aa2af94a6e1efb83b51926bd66ffa911faf6ffc587e270768bac660f4b2`；portable ZIP SHA-256 为 `cecc1cb0bc2dc1425dc6ba1606a9cb4a42040fc2eefc0012648acc57df37718c`；均为 `NotSigned`。原位升级 `D:\Miho Endgame` 返回 0，18/18 installed payload 精确匹配，desktop/CLI SHA-256 分别为 `bcf4870cfe29f33d976fc4d8e5eb158dce569f1fe39d822eb521be943a612ca0` / `13f31369ac6b21de309c244be3de8fee77b468615b0bc1213ebb35c1d9e6fa74`，事务与 failure receipt 均不存在，任务为 Ready，exact health `installer-f2af7331296b4441b03615e44b42e15e` 对 HSR/ZZZ 返回 `healthy=true`。
- **现行 Box 基线**：安装前、安装后、双游戏 DOM 深测和正常退出后均为 HSR 59 owned、SHA-256 `C7387DA68F23B5483037B0C87DFDF31D8601E383D5E2EE5CC5B48674D848F32B`；ZZZ 20 owned、SHA-256 `C677733006B569CBFB96EB95BF1827FB26A58292C1F17A9180AC7FF01E4D7491`。这两项取代上一节历史时点的 HSR 57 人基线；同字节恢复副本位于 `%APPDATA%\com.miho.endgame\.miho\recovery\20260716-120119Z-pre-banner-freshness-v1`。
- **真实入口证据**：最终 installed EXE 的 CDP/DOM 深测实际执行 ZZZ → HSR → ZZZ。ZZZ 为 Box 20/59、59/59 头像解码、终局“最新采样 2026-07-06 · 历史样本”、current 卡池 4 人（诺姆·霍洛维尔、千夏、可琳·威克斯、波可娜·费雷尼）；HSR 为 Box 59/92、92/92 头像解码、终局“最新采样 2026-06-25 · 历史样本”、current 卡池精确四人（姬子•启行、火花、丹恒•腾荒、长夜月）。两页可见缺数据警告均为 0；进程正常退出 0，stdout/stderr 为空，Box 零漂移。持久化 `scripts/probe_product_ui_v1.mjs` 随后补强为唯一 iframe/target、祖先 computed visibility、实际 SVG mark、可见角色卡/图片、卡池图片 slug 及全模式断言；installed 重跑中 ZZZ `sd/da` 分别有 297/287 个可见 chart marks 和 16/16 张角色卡，HSR `moc/pf/as/aa` 分别有 324/360/324/336 个 marks 和各 12 张角色卡，两边卡池各 4 张、图片零破损/零错配、缺数据提示 0。该探针属于测试留痕，不改变 active runtime inputs。
- **定点验证**：Rust visualizer 23 项、确定性跨语言契约 6 项、Vite build、JS/Python 语法、Python/Rust `app.js` 精确一致、PowerShell 5.1/7 GUI 契约及空 `PSModulePath` SHA-256 路径均通过；新增产品探针通过 `node --check`、`git diff --check` 和上述 installed DOM 实跑。没有重复运行与改动面无关的全 workspace/Python 全量。两个会联网补头像的 live CLI exact-oracle 旧闭包分别遇到 HSR 托帕头像路径变化和 ZZZ 新增 59 个在线头像，未计为通过；确定性离线/跨语言契约已通过，该外部头像漂移不属于本次状态修复。
- **主判断—最有把握**：最强证据不是 JSON 行数，而是 active 精确字节原位安装后，真实 iframe 页面完成 Box、终局、卡池和游戏切换；渲染卡片数量、精确角色名、采样标签、可见错误文案、头像解码、正常退出和 Box 哈希同时受检。
- **主判断—最值得质疑**：自动化能证明 DOM 中当前可见卡片、标签和 canonical 头像映射，不能替代逐张人工审美判断；当前 HSR/ZZZ 终局统计本身仍是历史样本，不应包装成最新周期。`NotSigned`、物理掉电、跨账户/跨 session 和连续 ETW 审计仍是长期边界，不因本次完成而消失。
- **独立发布与 post-install 对抗判断**：安装前只读终审独立重算 active NSIS、portable、static manifest 及 ZIP 20 项闭包，核对 clean source、Box/备份、无半成品和安装前进程，结论 `Blocker=0 / High=0`。安装后独立对抗复审又实际覆盖 ZZZ 两模式、HSR 四模式、空搜索、双卡池图片/名称、正常退出和 Box 零漂移，结论仍为 `Blocker=0 / High=0`；它提出的持久探针 computed visibility/图表/角色列表、全模式和唯一 frame 绑定 Medium 已由上项逐一固化。逐张头像是否符合人工审美仍不是 DOM 自动化能证明的事项，不把它伪装成机器已验收。
- **空间清理**：在解析 active manifest 并确认候选绝对路径均位于工作区、无 reparse、且不包含 active 闭包后，删除 `target/debug`、空 scratch、3 套旧 NSIS、3 套旧 portable 目录/ZIP、旧 verification/superseded/static manifests，共 17 项、4,319,268,436 逻辑字节；D 盘实测空闲增加 3,729,780,736 字节，`target` 降至 88,745,346 字节（0.083 GiB），D 盘空闲 283.906 GiB。清理后 active manifest 仍为 `active`，NSIS/portable SHA-256 仍为 `3bd32aa2…` / `cecc1cb0…`；安装目录、AppData、Box/recovery、owner、任务和 automation generation 均未进入删除集合。

### Box 原生导出与 GUI 子系统修复（2026-07-17，已交付）

- **根因与修复**：前一版 iframe 下载权限已使文件实际落入 Downloads，但 Blob 导出没有开始、成功或失败状态，连续点击只会静默生成重复文件；旧探针又用 `Browser/Page.setDownloadBehavior` 指定测试目录，不能证明普通入口。桌面模式现改走受 workspace token 保护的 Rust `POST /api/{game}/box/export`：严格校验 HSR v2 / ZZZ v3、1 MiB 与嵌套深度，在系统下载目录以 `create_new` 避免覆盖，并返回文件名/字节数；按钮在请求中禁用，成功显示实际文件名，失败显示明确错误。standalone 页面仍保留延迟 revoke 的 Blob fallback。
- **黑框修复**：release 入口加入 Windows GUI subsystem 属性；GUI 验证脚本现在直接解析 PE header 并要求 `Subsystem=2 / WINDOWS_GUI`，不再由 `CreateNoWindow` 掩盖控制台子系统错误。
- **定点验证与直接交付**：Rust temp-dir 落盘/碰撞/版本/非法请求测试、Python Visualizer 契约、JS/Python 语法、PowerShell GUI 契约、Rust fmt、diff check、Vite build 和 `pnpm run tauri:build` 均通过。`target/release/miho-desktop.exe` 与 `D:\Miho Endgame\miho-desktop.exe` SHA-256 均为 `9FB7744CB88EFAE51BA4A5197C2C10CB120EC51E89A92FD56BE92E3A3455587F`，PE subsystem 均为 2；直接原位替换，未生成或使用 NSIS/安装器/portable。
- **真实入口证据**：安装版先完成后台渲染、存活五秒、正常退出且 stdout/stderr 为空；随后在未调用任何 `setDownloadBehavior` 的情况下完成 ZZZ → HSR → ZZZ，并只点击一次“导出Box”。Rust 原生生成 `hsr_box_state.json`（1,311 bytes、59 人），按钮显示“已导出到下载文件夹”且回执文件名一致，导出内容与当前 Box 一致、源 Box 前后哈希不变；验证创建的单个文件已按精确文件名清理。

### 组队推荐双路径与角色硬约束（2026-07-17，已交付）

- **产品语义**：HSR 推荐拆为“末层实战”和“按弱点配队”。末层继续按最新同战斗侧真实阵容排序，弱点默认只标注且不改变分数/顺序，只有选择“过滤风险”才硬筛；普通层或自定义敌人可独立配置 2/3 队，每队分别保存弱点、必须上场和排除角色。
- **候选池与联合选队**：自定义路径使用当前模式全部具体战斗侧的真实阵容并集，排除截断的 `all/综合队伍池`，按无序四人签名去重；弱点以核心输出命中任一所选属性为适配，辅助同属性不算。多队联合搜索不复用角色、为后续必上角色留位，常态 Top 50/beam 180，无完整方案时扩大到 Top 240/beam 720。生产末日幻影实测候选池为 1,990 套，来源覆盖 `4-1/4-2/4-3`，不再只搜 `4-1`。ZZZ 同步支持按模式与关卡保存必须上场/排除硬约束。
- **节点语义**：PF/AS 的 `4-X` 攵称第 X 战斗侧，`4-3` 和 MoC `12-3` 明确标注星芒第三侧；AA 的 `1-1/1-2/1-3` 标为骑士三侧，`2-1` 标为王棋，`all` 标为综合队伍池，避免把侧数误读成层数。
- **验证与直接交付**：推荐器逻辑 11 项、离线跨语言精确对照 4 项、`miho-core` 176 项、静态/文件集相关 7 项和 `pnpm run tauri:build` 通过。两项 live CLI 完整目录测试仍因项目既有的托帕头像别名与 ZZZ 在线补入 59 张头像而失败，未误报为通过，且与本次推荐静态逻辑无关。新 EXE 已直接更新到 `D:\Miho Endgame\miho-desktop.exe`，与构建产物 SHA-256 同为 `1590E6060CDFCBEC2F6EC77B4FDEF4CAAA1ED95A763E4A7919F6899FF1AE1FB2`，未生成安装器。
- **真实入口证据**：后台 DOM 实际完成 ZZZ → HSR → 组队推荐，点击“按弱点配队”、2 队切 3 队、在 `as|custom-1` 添加必上/排除并切换 `custom-2` 验证隔离，再切回末层实战核对弱点提示。回执显示 1,990 套跨三侧池、设置快照已恢复、HSR/ZZZ Box 哈希不变、程序正常退出、stdout/stderr 为空且调试端口关闭。

### ZZZ 卫星排序与诺姆身份归一（2026-07-17，已交付）

- **根因与产品修复**：官方 roster/Prydwen 已使用 `norma`，卡池计划、决策基线和机制笔记仍使用旧 `nom`；Visualizer 只按精确 slug 合并，因此生成两张“诺姆·霍洛维尔”。卫星又是 banner-only 角色，原始 `release_order` 被追加到尾部，而前端直接沿用该顺序。生产配置现统一为 `norma`；Box 与卡池“全部”只调整展示为 `current → next → satellite → other/previous`，不篡改发布日期或证据顺序。
- **旧状态兼容**：前端加载时归一 stale `nom → norma`，合并 roster/banner 同身份行，并迁移 Box owned、builds、buildSlug 及按关卡保存的必上/排除约束；若两份练度同时存在则逐字段保留更完整进度。Workspace bootstrap 新种子为 `norma.yaml`，旧受管 `nom.yaml` 从 ownership 退役但不删除或改写用户文件。Rust/Python 两套 ZZZ `app.js` 字节一致，静态 SHA-256 为 `1b97c038ca6203993ecfe5b3eebb8f50b3daa2e9e0bb2d852695d900d49190a8`。
- **生产数据与真实入口证据**：本机受管配置升级后重新生成 ZZZ visualizer，原始 roster 从 59 降为 58；诺姆唯一为 `norma/current`，卫星 `remiel/sigrid` 均保留，`data.json` SHA-256 为 `889E2E669B998DF6EB46BECC54706288149C52A0AB37C74D073AA80BF68BFEAC`。隐藏窗口 CDP/DOM 实跑 ZZZ → HSR → ZZZ：诺姆卡片始终 1 张；当期 4 人位于索引 0–3、卫星 2 人位于 4–5、普通/已结束从 6 开始；两次检查排序均通过，全部分析模式、卡池与图片门禁同时通过，程序正常退出且 stdout/stderr 为空。
- **验证与直接交付**：推荐/身份契约 13/13、workspace bootstrap 34/34、pull-value 25/25、Rust/Python 静态契约与 visualizer 定点测试、JS/Python 语法、Rust fmt、Vite 和 `pnpm run tauri:build` 均通过；完整 live CLI oracle 仍只受项目既有“多 59 个内置头像”文件集漂移影响，未冒充通过。`target/release/miho-desktop.exe` 已直接更新到 `D:\Miho Endgame\miho-desktop.exe`，两者 SHA-256 均为 `4ED9342312A12A0C5CE1698D0B9D78558B306C5B115F677F9537194D0F13F64F`，未生成安装器。验收前后 ZZZ Box SHA-256 均为 `C677733006B569CBFB96EB95BF1827FB26A58292C1F17A9180AC7FF01E4D7491`，HSR Box 均为 `146CDBFD582F39080DE2DFAEB15B3892EF64FC1110B7509811350F47A09A785E`。

### 桌面视觉一体化与单滚动工作区（2026-07-18，已交付）

- **视觉根因与修复**：旧界面把深色 Tauri 外壳、居中暗色卡片、白色 iframe 和内页标题逐层画出，宽屏还受 1600px 上限留下大块黑边。桌面现改为 64px 紧凑品牌栏、全宽浅色连续画布和 46px 轻量上下文栏；Visualizer 外层边框、圆角、阴影与 padding 全部移除，外壳与 HSR/ZZZ 内页共用系统字体、青绿色操作强调和一致的浅色表面。
- **单滚动与工具层级**：主窗口固定为一屏，iframe 成为唯一内容滚动容器；“更新数据、生成报告与设置”与重新载入并入上下文栏，默认关闭，打开后以带遮罩的固定抽屉展示，不再把工具区堆到 iframe 下方形成第二根滚动条。iframe sandbox、custom protocol、安全 token、Box 保存和所有既有产品 selector 保持不变。
- **验证与直接交付**：Vite、`pnpm run tauri:build`、desktop lib 86 项、GUI contract、Rust fmt/diff check 均通过。后台实拍检查默认 1200×820 的抽屉关闭/打开状态，关闭态只剩一根内容滚动条；installed GUI 回执继续满足 production URL、ready sentinel、Tauri internals、5 秒存活、正常退出、空 stdout/stderr 和调试端口清理。
- **真实入口证据**：安装版后台 CDP/DOM 完整执行 ZZZ → HSR → ZZZ，覆盖 Box、六种终局模式、双卡池和 HSR 组队推荐；序列回执为 `zzz/hsr/zzz`，两份 Box 文件前后哈希不变。`target/release/miho-desktop.exe` 已直接更新到 `D:\Miho Endgame\miho-desktop.exe`，两者 SHA-256 均为 `0DAE1E8D9209B57B738E2072BED76941D1AA4E0752492DA9DB621942704B73A8`，未生成安装器或 portable。

### ZZZ 中文先发角色身份与发行顺序（2026-07-18，已交付）

- **根因与修复**：HoYoWiki 中文代理人名册已收录 `1082 / 佩洛伊斯`，英文名册尚未同步；旧解析只遍历英文行，导致 `pyrois` 丢失官方中文身份并回退到 `unknown / release_order=9999`。现以稳定 `entry_page_id` 桥接 Norma、Velina、Pyrois 的外部数据 slug，中文名、属性、特性、阵营、稀有度、头像与发行顺序均取当次中文名册；顺序随中文列表前插动态变化，英文以后补录同 ID 时仍只保留一条 canonical 记录。Visualizer 复用同一官方解析器，不再维护第二套 EN-only 合并。
- **仓库与安装版数据证据**：首次联网重建仓库 `out_zzz` 只证明开发输出，不代表安装版已经更新。随后已在安装版真实工作区 `C:\Users\zy958\AppData\Roaming\com.miho.endgame` 事务式重建 ZZZ；`name_map` 为 `norma=0 / velina=1 / pyrois=2`，Pyrois 显示“佩洛伊斯”、`kind=agent`、无需人工确认，并已从 unresolved 移除；usage、当前 Tier 与 roster 同步回填中文。真实安装版 WebView 的 `#boxGrid` 共 58 张卡，`pyrois` 唯一且位于索引 7，为 current/next/satellite 特殊状态角色之后的普通角色首位，不据此改写 T 档或强度结论。
- **验证与直接交付**：ZZZ 定点测试 39 项、`cargo clippy -p miho-core --all-targets --locked -- -D warnings`、Rust fmt、真实在线 export、后台 Box DOM、Vite/Tauri release 构建和 installed GUI 探针均通过。新 EXE 已直接更新到 `D:\Miho Endgame\miho-desktop.exe`，与 `target/release/miho-desktop.exe` SHA-256 同为 `3C3A94C6455E1685652F06DD69768ACAFD6A2D0BEA66EE94BA060112216D5B76`；未生成安装器或 portable，安装版 ZZZ Box SHA-256 前后均为 `C677733006B569CBFB96EB95BF1827FB26A58292C1F17A9180AC7FF01E4D7491`。
- **剩余风险**：计划任务仍引用 7 月 16 日的旧 CLI generation；在 automation generation 正式升级前，下次计划更新可能再次把 Pyrois 覆盖为 `unknown / 9999`。该任务链未在本次普通产品修复中擅自改写。

## 恢复入口

- 项目状态：本文件。
- 当前工作区：`D:\Projects\终局内容提取`。
- 兼容规则：`docs/migration-compatibility.md`。
- Rust workspace：根目录 `Cargo.toml`。
- 当前默认构建/验证：`pnpm run tauri:build` 直接生成 `target/release/miho-desktop.exe`，按风险运行相关 Rust/前端定点测试，再用后台 CDP/DOM 探针验证真实入口。全 workspace 回归只用于大范围变化；`scripts/build_rust_app.ps1 -Release` 及其 NSIS/manifest 门禁仅在用户明确要求旧发布链时运行。
- Python 基准：`python -m hsr_endgame_exporter --help`、`python -m zzz_endgame_exporter --help`。
- 业务归档：`D:\Projects\终局内容提取-archive\20260712-005035\manifest.json`。
- 迁移校验：`D:\Projects\终局内容提取-archive\migration-manifests\20260712-c-to-d\receipt.json`。
- update runner 契约：`docs/update-runner-contract.md`；外部现状与迁移阻断：`automation_capability_report.md`。
- 当前剩余长期边界：历史安装器链仍未做 Authenticode、跨账户 release lease 和完整 NSIS 任意切点强杀/物理掉电恢复；这些不是当前 Tauri 直接交付的阻断。后台进程采样也不等于连续 ETW 审计。
