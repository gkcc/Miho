# 终局数据工具迁移项目

## 产品愿景

将现有 HSR/ZZZ Python 工具完整迁移到 Tauri 2 + Rust，最终运行时不依赖 Python，同时保持 GUI、CLI、JSON/YAML/CSV、Box State v2、报告和计算语义兼容。迁移期间 Python 是行为基准；Rust 命令只有通过黄金对比后才能解除门禁。

## 当前状态

- 工作区已安全迁移到 `D:\Projects\终局内容提取`；6,111 个不可再生项目文件与 16,301 个归档文件逐路径 SHA-256 校验均为零差异，迁移回执保存在归档目录。
- D 盘迁移后重建验证：Rust workspace 迁移测试持续通过，frozen pnpm install、Vite build 与 Tauri `--no-bundle` 通过；双游戏 visualizer 契约、Rust 实现、真实 CLI、Hub 与浏览器冒烟现已全部收口。
- 工作区治理完成：业务资产已归档到 `D:\Projects\终局内容提取-archive\20260712-005035`，清单含 761 个文件及 SHA-256。
- Cargo workspace 已建立：`miho-core`、`miho-cli`、`miho-desktop`。
- Rust 已实现 HF 在线/离线统一 `SnapshotSource`、日期与部分失败语义、两游戏多 snapshot/mode 聚合，以及 HSR histograph/fallback、动态视图、完整队伍去重和 ZZZ Bangboo/name fallback。
- Rust CLI 已接通 HSR/ZZZ `export`、原子写出和 0/1/2 退出码；两游戏的 Prydwen visible/tier/changelog、HoYoWiki 官方名称、历史、趋势、raw 与 Workbook 产物均已进入共享 Rust pipeline，补充来源或 Workbook 失败只降级为结构化 warning。
- 版本化 `ExportRequestV1`、可信 `ExportContext`、结构化 diagnostics/stats/IPC receipt/failure 已进入 CLI 执行链；请求会核对实际 dataset 身份，报告完成后重建 artifact manifest。
- HSR 的 `--prydwen-top-n`/`--name-map-seed` 与 ZZZ 的 `--prydwen-top-n` 已解除选项门禁；离线 CLI 默认生成 Workbook，两游戏在线 export 均在 visualizer 完整目录验收后解除总门禁。
- ZZZ 已覆盖 visible scope 保序、版本优先的最新阶段、phase selector/override、agent/Bangboo 双语名称、alias、完整 26/4/32 列 history/trend，以及 Cloudflare/retcode 语义失败的 last-good cache 回退。
- 最近完整回归：Rust workspace 218 项、Python 181 项（含 visualizer、Evidence V1、LegacyV0 decision、pull-value V1 与 review-packet V1 契约）、workspace 严格 clippy、Python compileall 与 diff check 通过；前端 Vite build 与 Tauri `--no-bundle` 仍沿用第十一批已通过基线。
- Tauri/Vite 构建基线已固定 pnpm 11.7.0、Node `>=20.19 <25`、esbuild 布尔 allowlist 和 `127.0.0.1:1420` strict port，根脚本可从干净依赖状态复现。
- 双游戏 Workbook 语义契约已冻结：HSR 18-sheet、ZZZ 12-sheet 脱敏 oracle 与比较器覆盖顺序、值/类型、公式、样式、冻结、筛选、列宽和数值格式；10 项契约测试及 30 张工作表渲染核验通过。
- 共享 Rust Workbook writer 已直接消费最终 CSV bundle：显式类型、HSR 样式/列宽/数值格式、ZZZ pandas 默认语义、安全公式文本、BestEffort diagnostics、manifest/receipt 与 CLI 原子写出均已通过双游戏语义对比。
- 双游戏 visualizer 产物契约已冻结并由 Rust 实现：严格 `data.json`、精确目录集合、静态资源与头像哈希、禁网/便携/XSS/URL/非有限数值约束，以及 Hub/HSR/ZZZ 浏览器交互冒烟均已通过；两游戏 export 与独立 visualizer 共用最终磁盘产物重建边界。
- `evidence-first-v1-20260712` 已由 Python oracle 与共享 Rust core/CLI 双实现：跨 mode 隔离、A 的 sentinel/稳定性门槛、owned/built 分离、稳定 E-ID、显式时钟、JSON/YAML/BOM、四产物黄金和任意路径整批回滚均已验收；Rust evidence/coverage 门禁已解除。
- Python 继续作为决策/报告迁移 oracle；Rust `decision` 已作为显式 `legacy-v0` compatibility 完成迁移，不将其跨模式 heuristic、raw team 依赖和 alias 缺口宣称为 evidence-first 完成。Rust `pull-value` 已成为唯一正式推荐入口；Rust `review-packet` 已解除 core/CLI 门禁，只序列化同一批 pull cards、refs、stable IDs/keys/trace，不生成第二套推荐。共享报告 IPC、后台任务与 Tauri UI 仍待产品化。

## 阶段路线

1. **工作区治理**：完成。
2. **兼容基线**：固化 CLI、输入输出和允许差异，建立黄金比较器。
3. **Rust 基础内核**：完成强类型配置、规范化、解析模型、稳定标识、可靠存储与网络边界。
4. **数据抓取与导出**：移植 Hugging Face、Prydwen、官方名称及 HSR/ZZZ 导出。
5. **决策与报告**：完成 evidence、coverage、decision compatibility、pull-value、review-packet 的 Rust core/CLI 迁移。
6. **Tauri 产品化**：等价迁移可视化，加入任务、进度、取消、错误和文件选择。
7. **自动化与发布**：切换计划任务，验证 NSIS/便携版和无 Python 环境，最后退役 Python。

## 阶段完成对抗复核门槛

每个阶段性任务在提交前必须留下可审计记录，不能只给出“测试通过”的结论：

1. **显式提问**：本阶段我最有把握的完成证据是什么？最值得质疑、最可能被现有测试漏掉的点是什么？
2. **主判断**：分别回答把握点与质疑点，并给出文件、测试、运行结果或产物证据。
3. **独立对抗判断**：由未参与该实现的子智能体按原始目标和实际 diff 复审，只报告 Blocker/High 或明确无阻断。
4. **主线程回应**：逐项接受、反驳或补证；Blocker/High 未清零不得提交，也不得解除门禁。
5. **关键留痕**：把提问、双方判断、最终处理和路线微调写回本文件对应阶段，并在提交信息中保持阶段边界清晰。

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

## 决策记录

| 日期 | 决策 | 影响 | 复核条件 |
| --- | --- | --- | --- |
| 2026-07-12 | 采用纯 Tauri + Rust，GUI 与 CLI 全兼容，分阶段替换 | Python 保留为迁移 oracle，禁止一次性切换 | 全部黄金测试通过 |
| 2026-07-12 | 工作区采用复制、全量哈希、Git 校验后切换的方式从 C 盘迁移到 D 盘 | `D:\Projects\终局内容提取` 是后续唯一开发入口；C 盘旧源码仅作为短期回滚副本 | 再次迁盘或 D 盘健康状态异常时 |
| 2026-07-12 | 业务资产归档到仓库外，缓存直接清除 | 工作区只保留源码、配置、测试和项目文档 | 需要恢复历史数据时使用归档清单 |
| 2026-07-12 | 每个子目标一个本地提交，每三个子目标复盘 | 提高可回退性；不自动推送远端 | 项目规模或协作方式显著改变 |
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
| 2026-07-12 | 每个阶段提交前增加显式信心/质疑提问与独立对抗复核 | 测试通过不再自动等于阶段完成；Blocker/High 必须修复并复验，双方判断与路线调整写回 PROJECT.md | 项目转为单人一次性原型或用户明确撤销该门槛时 |
| 2026-07-12 | ZZZ visualizer 通过致密跨语言、真实 CLI/Hub、浏览器与独立对抗复核后解除在线 export 总门禁 | 两游戏默认在线路径均由 Rust 生成 CSV、Workbook、visualizer、manifest；Python visualizer 降为 oracle | 完整目录出现未批准差异、来源协议变化或 sidecar schema 升级时 |
| 2026-07-12 | legacy 无 manifest 输出只从游戏正式命名空间恢复 ownership；未知文件保留但不进入新 manifest | `raw/hf/**` 因动态 source path 被保留为 export-owned 命名空间，用户私有文件不得放入其中 | 正式 artifact schema/manifest 增加显式 ownership metadata 时 |
| 2026-07-12 | 决策/报告以 `evidence-first-v1-20260712` 为正式方法；旧 decision 标记 `legacy-v0` | 同队不跨 mode 合并分数/置信度；A 需有效表现与稳定组件；高/中高抽取必须引用 A/B 主证据；LegacyV0 精确兼容不等于方法完成 | 证据策略/schema 升级或用户明确要求旧 heuristic 默认化时 |
| 2026-07-12 | Rust evidence/coverage 报告是 export 目录中的 unmanaged consumer artifact；报告命令只捕获一次 cwd/local datetime，任意输出整批安装并拒绝父链 symlink/reparse point | 不刷新或占有 `artifact_manifest.json`/visualizer；debug 固定时钟只用于黄金测试，release 始终使用本地时钟；路径别名不能绕过三输出互异性 | 报告进入正式 artifact schema、支持受信任 reparse 输出或事务协议升级时 |
| 2026-07-12 | `decision` 只迁移显式 `legacy-v0` compatibility；正式 evidence-first 推荐唯一入口是 `pull-value`，`review-packet` 直接序列化同一批卡片 | 禁止再造第二套 Decision V1 与 pull-value 竞争；Legacy 继续保留 raw team、跨 mode heuristic 和旧 payload/hash，但 CLI/help/receipt 必须标 compatibility only，UI 不得当正式推荐 | 产品明确批准独立 Decision V1 的版本化规则/schema，或正式推荐入口发生变更时 |
| 2026-07-12 | LegacyV0 compatibility 按 Python 的字段存在性、truthiness、`str(float)`、DictReader 与 PyYAML 1.1 语义做显式 adapter，不以 serde 默认行为代替兼容契约 | 六 CSV 的 missing/null/empty、JSON/YAML quoted/plain scalar、非有限失败和旧两文件事务进入 Rust 门禁；visualizer sidecar 根字段标记 `decisionMethodVersion=legacy-v0` | 删除 LegacyV0、升级其公开 schema，或 Python oracle 被版本化替代时 |
| 2026-07-13 | `pull-value` 作为唯一正式推荐入口解除 Rust 门禁；未拥有候选的主证据只接受 exact single dependency，多计划依赖进入 conditional risk | current/next 或显式合并报告使用单次时钟和批事务；PyYAML/JSON/BOM/非有限值走共享安全解析；manifest/visualizer/legacy sidecar 不归报告命令管理 | Evidence 方法/schema 升级、报告进入正式 manifest，或 review-packet/IPC 改变卡片所有权时 |
| 2026-07-13 | Rust `review-packet` 解除 core/CLI 门禁，并固定为 `PullValueBundleV1` 的安全 serializer | 不重新读取输入或重算推荐；split/combined 与 pull-value 共用 adapter、单次时钟和批事务；manifest、visualizer、decision、pull/coverage 产物仍为 unmanaged | pull card/schema、Evidence 方法、JSON renderer、报告 ownership 或 IPC 所有权变化时 |

## 风险登记

| 风险 | 当前状态 | 缓解措施 |
| --- | --- | --- |
| Python/Rust 计算或默认值漂移 | 高 | 先固化 CLI 与黄金输出，逐命令解除门禁 |
| Legacy decision 与 evidence-first 方法冲突 | 低（兼容迁移已验证，正式方法仍隔离） | `decision --method legacy-v0` 仅作 compatibility；正式推荐只由 pull-value 产生并以 dedup A/B 主证据支撑高优先级 |
| 双游戏 visualizer 与 Python 语义漂移 | 低（已验证） | 46 项跨语言/真实 CLI 契约、118 项 core、浏览器冒烟与独立对抗反例；sidecar/schema 变化时重新关门复核 |
| Workbook 单元格类型和样式可能与 Python 漂移 | 低（已验证） | 双游戏 oracle、显式/混合类型、thin border、样式/列宽语义规范化与 Rust 全局零公式断言已固化 |
| `atomic::write` Windows 替换存在极短路径缺口 | 中 | 唯一临时文件、同步、备份与失败回滚已覆盖；安装环境继续压力测试 |
| Tauri 后台任务、取消和 visualizer 产品集成尚未迁移 | 高 | 数据与报告默认路径稳定后再接 IPC，前端不复制规则 |
| 外部数据源随时间变化 | 高 | 归档历史 raw 数据，黄金测试只用固定离线输入 |
| 子智能体共享工作树冲突 | 中 | 并行任务划定互斥路径；公共类型由主智能体串行整合 |
| pnpm/esbuild 构建审批或端口再次漂移 | 低（已验证） | 布尔 allowlist、packageManager/Node engines、1420 strict port 与根级复现脚本已固化 |
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

## 恢复入口

- 项目状态：本文件。
- 当前工作区：`D:\Projects\终局内容提取`。
- 兼容规则：`docs/migration-compatibility.md`。
- Rust workspace：根目录 `Cargo.toml`。
- 当前完整验证：`cargo test --workspace --no-fail-fast; cargo clippy --workspace --all-targets -- -D warnings; python -m pytest -q; pnpm run deps:install; pnpm run build; pnpm run tauri:build:no-bundle`。
- Python 基准：`python -m hsr_endgame_exporter --help`、`python -m zzz_endgame_exporter --help`。
- 业务归档：`D:\Projects\终局内容提取-archive\20260712-005035\manifest.json`。
- 迁移校验：`D:\Projects\终局内容提取-archive\migration-manifests\20260712-c-to-d\receipt.json`。
- 最危险的未验证假设：共享报告 IPC/后台任务接入 Tauri 后能否保持 typed bundle 单一所有权、单次时钟、取消/进度和批事务，以及自动化切换与无 Python 发布能否在真实安装环境复现；Evidence/Pull/Review 已证明“先冻结显式输入与时钟，再做路径/失败对抗反例”的路线有效。
