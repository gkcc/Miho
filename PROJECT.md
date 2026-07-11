# 终局数据工具迁移项目

## 产品愿景

将现有 HSR/ZZZ Python 工具完整迁移到 Tauri 2 + Rust，最终运行时不依赖 Python，同时保持 GUI、CLI、JSON/YAML/CSV、Box State v2、报告和计算语义兼容。迁移期间 Python 是行为基准；Rust 命令只有通过黄金对比后才能解除门禁。

## 当前状态

- 工作区治理完成：业务资产已归档到 `C:\Users\zy958\Documents\终局内容提取-archive\20260712-005035`，清单含 761 个文件及 SHA-256。
- Cargo workspace 已建立：`miho-core`、`miho-cli`、`miho-desktop`。
- Rust 已实现 HF 在线/离线统一 `SnapshotSource`、日期与部分失败语义、两游戏多 snapshot/mode 聚合，以及 HSR histograph/fallback、动态视图、完整队伍去重和 ZZZ Bangboo/name fallback。
- Rust CLI 已接通 HSR/ZZZ `export`、原子写出和 0/1/2 退出码；离线 fixture 与显式关闭补充来源后的 HF 核心路径可用。Prydwen/官方名称默认开启时仍主动门禁，尚不能替代 Python 默认导出。
- 版本化 `ExportRequestV1`、可信 `ExportContext`、结构化 diagnostics/stats/IPC receipt/failure 已进入 CLI 执行链；请求会核对实际 dataset 身份，报告完成后重建 artifact manifest。
- 最近验证：契约 4 项、报告 1 项、pipeline 14 项、CLI 15 项定向测试通过；上一完整基线为 Rust workspace 60 项、Python 71 项和严格 clippy 全部通过。
- Python 仍负责 Prydwen/官方名称抓取、历史合并、Excel、正式报告、visualizer，以及 evidence、coverage、decision、pull-value、review-packet。

## 阶段路线

1. **工作区治理**：完成。
2. **兼容基线**：固化 CLI、输入输出和允许差异，建立黄金比较器。
3. **Rust 基础内核**：完成强类型配置、规范化、解析模型、稳定标识、可靠存储与网络边界。
4. **数据抓取与导出**：移植 Hugging Face、Prydwen、官方名称及 HSR/ZZZ 导出。
5. **决策与报告**：移植 evidence、coverage、decision、pull-value、review-packet。
6. **Tauri 产品化**：等价迁移可视化，加入任务、进度、取消、错误和文件选择。
7. **自动化与发布**：切换计划任务，验证 NSIS/便携版和无 Python 环境，最后退役 Python。

## 当前三目标（第九批）

| 子目标 | 状态 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| 建立补充来源与导出上下文契约 | 已完成 | 主智能体 | 现有 hsr/zzz source parser、PipelineRun、报告参数 | 游戏隔离的补充资源 trait；版本化 request/receipt/failure；可信 context 与结构化 diagnostics/stats；最终报告和清单 | 契约/报告/pipeline/CLI 共 34 项定向测试；dataset 错配与未知 wire 字段被拒绝 | generic pipeline |
| 接通 HSR 补充来源 | 进行中 | 子智能体移植、主智能体整合 | Prydwen visible/tier/changelog、Hoyowiki、name seed、top-N | HSR 默认来源生成真实 team/tier/name/history/trend，移除对应门禁 | 完整目录 Python/Rust 对比，部分来源失败仍可导出 | 补充来源契约 |
| 接通 ZZZ 补充来源 | 进行中 | 独立子智能体移植、主智能体整合 | Prydwen visible/tier/changelog、官方 agent/Bangboo 名称 | ZZZ 默认来源生成真实 team/tier/name/history/trend，移除对应门禁 | 完整目录 Python/Rust 对比，Bangboo 与 agent 名称覆盖 | 补充来源契约 |

## 决策记录

| 日期 | 决策 | 影响 | 复核条件 |
| --- | --- | --- | --- |
| 2026-07-12 | 采用纯 Tauri + Rust，GUI 与 CLI 全兼容，分阶段替换 | Python 保留为迁移 oracle，禁止一次性切换 | 全部黄金测试通过 |
| 2026-07-12 | 业务资产归档到仓库外，缓存直接清除 | 工作区只保留源码、配置、测试和项目文档 | 需要恢复历史数据时使用归档清单 |
| 2026-07-12 | 每个子目标一个本地提交，每三个子目标复盘 | 提高可回退性；不自动推送远端 | 项目规模或协作方式显著改变 |
| 2026-07-12 | 首发仅维护 Windows 图标和安装配置 | 删除自动生成的 Android/iOS 图标 | 正式纳入其他平台时 |
| 2026-07-12 | Rust export 先开放 fixture/HF 核心路径，默认补充来源保持显式门禁 | 避免把缺 Prydwen/官方名称的残缺目录误报为兼容成功 | 两游戏完整目录黄金对比通过 |
| 2026-07-12 | V1 wire 请求拒绝未知字段，运行时路径只由 Rust 构造；成功回执和失败回执分离 | 防止 CLI/Tauri 静默忽略能力或由 WebView 注入缓存/历史路径 | IPC schema 升级或新增可信输入来源时 |

## 风险登记

| 风险 | 当前状态 | 缓解措施 |
| --- | --- | --- |
| Python/Rust 计算或默认值漂移 | 高 | 先固化 CLI 与黄金输出，逐命令解除门禁 |
| 补充来源未接通导致默认导出缺数据 | 高 | CLI 默认门禁；第九批建立 injectable source 并分别接通两游戏 |
| 历史合并与 Excel 尚未进入统一 outcome | 高 | 报告已消费 request/context/diagnostics 并在最后刷新 manifest；后续让历史和 Workbook 在报告前完成 |
| `atomic::write` Windows 替换存在极短路径缺口 | 中 | 唯一临时文件、同步、备份与失败回滚已覆盖；安装环境继续压力测试 |
| Tauri 后台任务、取消和完整 visualizer 尚未迁移 | 高 | 数据与报告默认路径稳定后再接 IPC，前端不复制规则 |
| 外部数据源随时间变化 | 高 | 归档历史 raw 数据，黄金测试只用固定离线输入 |
| 子智能体共享工作树冲突 | 中 | 并行任务划定互斥路径；公共类型由主智能体串行整合 |
| pnpm/esbuild 安装策略导致前端构建不可复现 | 中 | 固化根锁文件和批准配置，增加干净环境构建验证 |
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

## 恢复入口

- 项目状态：本文件。
- 兼容规则：`docs/migration-compatibility.md`。
- Rust workspace：根目录 `Cargo.toml`。
- 当前定向验证：`cargo test -p miho-core contract::tests; cargo test -p miho-core report::tests; cargo test -p miho-core pipeline::tests; cargo test -p miho-cli`；批次完成时仍执行 workspace、clippy 与 Python 全量回归。
- Python 基准：`python -m hsr_endgame_exporter --help`、`python -m zzz_endgame_exporter --help`。
- 业务归档：`C:\Users\zy958\Documents\终局内容提取-archive\20260712-005035\manifest.json`。
- 最危险的未验证假设：变化中的 Prydwen/Hoyowiki 页面与历史文件能通过可注入 Rust 来源边界稳定复刻，并让两游戏默认完整目录只保留批准差异。
