# 终局数据工具迁移项目

## 产品愿景

将现有 HSR/ZZZ Python 工具完整迁移到 Tauri 2 + Rust，最终运行时不依赖 Python，同时保持 GUI、CLI、JSON/YAML/CSV、Box State v2、报告和计算语义兼容。迁移期间 Python 是行为基准；Rust 命令只有通过黄金对比后才能解除门禁。

## 当前状态

- 工作区已安全迁移到 `D:\Projects\终局内容提取`；6,111 个不可再生项目文件与 16,301 个归档文件逐路径 SHA-256 校验均为零差异，迁移回执保存在归档目录。
- D 盘迁移后重建验证：Rust workspace 131 项通过，frozen pnpm install、Vite build 与 Tauri `--no-bundle` 通过；原暂停的 visualizer 契约半成品现已完成 fixture、旧断言和浏览器冒烟收口。
- 工作区治理完成：业务资产已归档到 `D:\Projects\终局内容提取-archive\20260712-005035`，清单含 761 个文件及 SHA-256。
- Cargo workspace 已建立：`miho-core`、`miho-cli`、`miho-desktop`。
- Rust 已实现 HF 在线/离线统一 `SnapshotSource`、日期与部分失败语义、两游戏多 snapshot/mode 聚合，以及 HSR histograph/fallback、动态视图、完整队伍去重和 ZZZ Bangboo/name fallback。
- Rust CLI 已接通 HSR/ZZZ `export`、原子写出和 0/1/2 退出码；两游戏的 Prydwen visible/tier/changelog、HoYoWiki 官方名称、历史、趋势、raw 与 Workbook 产物均已进入共享 Rust pipeline，补充来源或 Workbook 失败只降级为结构化 warning。
- 版本化 `ExportRequestV1`、可信 `ExportContext`、结构化 diagnostics/stats/IPC receipt/failure 已进入 CLI 执行链；请求会核对实际 dataset 身份，报告完成后重建 artifact manifest。
- HSR 的 `--prydwen-top-n`/`--name-map-seed` 与 ZZZ 的 `--prydwen-top-n` 已解除选项门禁；离线 CLI 已默认生成 Workbook，HSR 在线 export 在 visualizer 完整目录验收后解除总门禁，ZZZ 在线入口继续受 visualizer 门禁保护。
- ZZZ 已覆盖 visible scope 保序、版本优先的最新阶段、phase selector/override、agent/Bangboo 双语名称、alias、完整 26/4/32 列 history/trend，以及 Cloudflare/retcode 语义失败的 last-good cache 回退。
- 最近完整回归：Rust workspace 131 项、Python 123 项和 workspace 严格 clippy 通过；前端 frozen install、esbuild 0.25.12、Vite build 与 Tauri `--no-bundle` 均已通过。
- Tauri/Vite 构建基线已固定 pnpm 11.7.0、Node `>=20.19 <25`、esbuild 布尔 allowlist 和 `127.0.0.1:1420` strict port，根脚本可从干净依赖状态复现。
- 双游戏 Workbook 语义契约已冻结：HSR 18-sheet、ZZZ 12-sheet 脱敏 oracle 与比较器覆盖顺序、值/类型、公式、样式、冻结、筛选、列宽和数值格式；10 项契约测试及 30 张工作表渲染核验通过。
- 共享 Rust Workbook writer 已直接消费最终 CSV bundle：显式类型、HSR 样式/列宽/数值格式、ZZZ pandas 默认语义、安全公式文本、BestEffort diagnostics、manifest/receipt 与 CLI 原子写出均已通过双游戏语义对比。
- 双游戏 Python visualizer 产物契约已冻结：严格 `data.json`、精确目录集合、静态资源与头像哈希、禁网/便携/XSS/URL/非有限数值约束，以及 Hub/HSR/ZZZ 浏览器交互冒烟均已通过；两游戏 export 与独立 visualizer 共用最终磁盘产物重建边界。
- Python 仍作为全部导出语义的对照实现，并暂时负责 ZZZ 正式 visualizer，以及 evidence、coverage、decision、pull-value、review-packet；HSR visualizer 的 core、独立 CLI 与 export 接线已由 Rust 接管。

## 阶段路线

1. **工作区治理**：完成。
2. **兼容基线**：固化 CLI、输入输出和允许差异，建立黄金比较器。
3. **Rust 基础内核**：完成强类型配置、规范化、解析模型、稳定标识、可靠存储与网络边界。
4. **数据抓取与导出**：移植 Hugging Face、Prydwen、官方名称及 HSR/ZZZ 导出。
5. **决策与报告**：移植 evidence、coverage、decision、pull-value、review-packet。
6. **Tauri 产品化**：等价迁移可视化，加入任务、进度、取消、错误和文件选择。
7. **自动化与发布**：切换计划任务，验证 NSIS/便携版和无 Python 环境，最后退役 Python。

## 当前三目标（第十一批）

| 子目标 | 状态 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 固化双游戏 visualizer 产物契约 | 完成 | 兼容测试子智能体、主智能体定标 | 两套 Python visualizer、最终 CSV、版本化 Banner/Decision sidecar、本地头像种子 | 脱敏 `data.json` oracle；HTML/CSS/JS/本地头像/Hub 精确文件集合；单动态字段白名单与版本化比较器 | 当前 39 项契约测试；Hub/HSR/ZZZ 浏览器加载、切换、Box 与 XSS 冒烟 | 最终 CSV 与 Workbook 已稳定 |
| 迁移 HSR visualizer bundle | 完成 | HSR Rust 子智能体、CLI 子智能体、契约子智能体、主智能体整合 | HSR visualizer 契约、最终 ArtifactBundle、共享缓存/网络层 | Rust 生成等价 `visualizer/data.json` 与静态资源；离线头像回退；export/visualizer CLI 共用核心实现 | 致密 Rust/Python JSON、目录与 hash 零差异；真实 CLI 整目录零差异；浏览器 Banner/Box/XSS/console 冒烟；线上门禁解除 | visualizer 契约 |
| 迁移 ZZZ visualizer bundle | 待开始（字段审计完成） | ZZZ Rust 子智能体、主智能体整合 | ZZZ visualizer 契约、最终 ArtifactBundle、共享缓存/网络层 | Rust 生成等价 `visualizer/data.json` 与静态资源；代理人/邦布与卡池语义；export/visualizer CLI 共用核心实现 | ZZZ JSON 语义对比、目录比较、CLI fixture、浏览器交互冒烟、严格 clippy | visualizer 契约；显式本地 datetime context |

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

## 风险登记

| 风险 | 当前状态 | 缓解措施 |
| --- | --- | --- |
| Python/Rust 计算或默认值漂移 | 高 | 先固化 CLI 与黄金输出，逐命令解除门禁 |
| ZZZ visualizer 尚未进入 Rust 完整目录 | 高 | Python 契约已冻结并完成真实浏览器冒烟；字段/排序/sidecar 审计已完成，下一步按 ArtifactBundle + 显式 datetime context 迁移 |
| Workbook 单元格类型和样式可能与 Python 漂移 | 低（已验证） | 双游戏 oracle、显式/混合类型、thin border、样式/列宽语义规范化与 Rust 全局零公式断言已固化 |
| `atomic::write` Windows 替换存在极短路径缺口 | 中 | 唯一临时文件、同步、备份与失败回滚已覆盖；安装环境继续压力测试 |
| Tauri 后台任务、取消和完整 visualizer 尚未迁移 | 高 | 数据与报告默认路径稳定后再接 IPC，前端不复制规则 |
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
- 主流程审视与调整：HSR 门禁按预定证据解除，但后续不再把“严格黄金”自动等同“覆盖充分”。ZZZ 必须先建立能触发多行选择/回退的致密 fixture，再做 core/CLI/浏览器验收；同时把 ZZZ Banner 依赖的含时分本地时钟升级为显式版本化 context，不能用 `NaiveDate` 静默近似。两游戏继续共享 ArtifactBundle/安全 writer，不共享各自排序与派生规则。
- 下一步：新增 `zzz_visualizer` 独立模块和 ZZZ 静态资产，先锁定 phase override/raw 补偿、official roster、Bangboo/team、Banner/Decision 与 datetime context，再接真实 CLI 和 Hub 浏览器冒烟。

## 恢复入口

- 项目状态：本文件。
- 当前工作区：`D:\Projects\终局内容提取`。
- 兼容规则：`docs/migration-compatibility.md`。
- Rust workspace：根目录 `Cargo.toml`。
- 当前完整验证：`cargo test --workspace --no-fail-fast; cargo clippy --workspace --all-targets -- -D warnings; python -m pytest -q; pnpm run deps:install; pnpm run build; pnpm run tauri:build:no-bundle`。
- Python 基准：`python -m hsr_endgame_exporter --help`、`python -m zzz_endgame_exporter --help`。
- 业务归档：`D:\Projects\终局内容提取-archive\20260712-005035\manifest.json`。
- 迁移校验：`D:\Projects\终局内容提取-archive\migration-manifests\20260712-c-to-d\receipt.json`。
- 最危险的未验证假设：ZZZ 能否在不复制 Python 隐式 cwd/raw 文件探测的前提下，用显式版本化 datetime、phase/Banner/Decision sidecar 与头像 context 生成等价完整目录；HSR 已证明该边界可行，但 ZZZ 的 Bangboo、Decision 和含时分 Banner 状态仍未迁移。
