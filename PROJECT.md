# 终局数据工具迁移项目

## 产品愿景

将现有 HSR/ZZZ Python 工具完整迁移到 Tauri 2 + Rust，最终运行时不依赖 Python，同时保持 GUI、CLI、JSON/YAML/CSV、Box State v2、报告和计算语义兼容。迁移期间 Python 是行为基准；Rust 命令只有通过黄金对比后才能解除门禁。

## 当前状态

- 工作区治理完成：业务资产已归档到 `C:\Users\zy958\Documents\终局内容提取-archive\20260712-005035`，清单含 761 个文件及 SHA-256。
- Cargo workspace 已建立：`miho-core`、`miho-cli`、`miho-desktop`。
- Rust 已实现配置加载、Box State v2、基础规范化、原子写入雏形和 HTTP 重试；Tauri 已打通 HSR/ZZZ Box 读写。
- Rust CLI 已注册 HSR 2 个、ZZZ 8 个命令，但所有业务命令仍处于迁移门禁，不能替代 Python。
- 最近验证：`cargo test --workspace --no-fail-fast`，5 个测试通过。
- Python 仍负责全部抓取、解析、证据池、覆盖率、决策、抽取价值、报告和正式导出。

## 阶段路线

1. **工作区治理**：完成。
2. **兼容基线**：固化 CLI、输入输出和允许差异，建立黄金比较器。
3. **Rust 基础内核**：完成强类型配置、规范化、解析模型、稳定标识、可靠存储与网络边界。
4. **数据抓取与导出**：移植 Hugging Face、Prydwen、官方名称及 HSR/ZZZ 导出。
5. **决策与报告**：移植 evidence、coverage、decision、pull-value、review-packet。
6. **Tauri 产品化**：等价迁移可视化，加入任务、进度、取消、错误和文件选择。
7. **自动化与发布**：切换计划任务，验证 NSIS/便携版和无 Python 环境，最后退役 Python。

## 当前三目标（第二批）

| 子目标 | 负责人 | 输入 | 输出 | 验收 | 依赖 |
| --- | --- | --- | --- | --- | --- |
| 固化 Python CLI 契约 | 子智能体审计，主智能体整合 | 两套 `cli.py` 与现有测试 | CLI 快照测试：命令、参数、默认值、布尔双旗标、0/1/2 退出码 | `python -m pytest tests/test_cli_contract.py -q` | 无 |
| 修复存储与数据目录边界 | 主智能体 | `atomic.rs`、Tauri IPC | 无先删窗口且并发安全的原子写；稳定的应用数据根目录；旧路径兼容测试 | `cargo test -p miho-core && cargo test -p miho-desktop` | 兼容契约中的 Box v2 规则 |
| 建立规范化双跑基线 | 子智能体提取样本，主智能体实现 | Python normalize/parsers 与脱敏 fixture | Rust 规范化/稳定标识实现、Python/Rust 同输入黄金结果 | 定向 Python 测试与 `cargo test -p miho-core` | CLI 契约中的格式约定 |

## 决策记录

| 日期 | 决策 | 影响 | 复核条件 |
| --- | --- | --- | --- |
| 2026-07-12 | 采用纯 Tauri + Rust，GUI 与 CLI 全兼容，分阶段替换 | Python 保留为迁移 oracle，禁止一次性切换 | 全部黄金测试通过 |
| 2026-07-12 | 业务资产归档到仓库外，缓存直接清除 | 工作区只保留源码、配置、测试和项目文档 | 需要恢复历史数据时使用归档清单 |
| 2026-07-12 | 每个子目标一个本地提交，每三个子目标复盘 | 提高可回退性；不自动推送远端 | 项目规模或协作方式显著改变 |
| 2026-07-12 | 首发仅维护 Windows 图标和安装配置 | 删除自动生成的 Android/iOS 图标 | 正式纳入其他平台时 |

## 风险登记

| 风险 | 当前状态 | 缓解措施 |
| --- | --- | --- |
| Python/Rust 计算或默认值漂移 | 高 | 先固化 CLI 与黄金输出，逐命令解除门禁 |
| `atomic::write` 先删除目标再改名，存在丢失窗口 | 高 | 第二批改为唯一临时文件和 Windows 安全替换语义 |
| Tauri 用当前工作目录定位 `.miho`，安装后不稳定 | 高 | 引入稳定应用数据根，并保留显式 workspace/旧路径导入 |
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

## 恢复入口

- 项目状态：本文件。
- 兼容规则：`docs/migration-compatibility.md`。
- Rust workspace：根目录 `Cargo.toml`。
- 当前验证：`$env:Path="$env:USERPROFILE\.cargo\bin;$env:Path"; cargo test --workspace --no-fail-fast`。
- Python 基准：`python -m hsr_endgame_exporter --help`、`python -m zzz_endgame_exporter --help`。
- 业务归档：`C:\Users\zy958\Documents\终局内容提取-archive\20260712-005035\manifest.json`。
- 最危险的未验证假设：Rust 能在不改变默认值、排序、缺失数据处理和报告语义的前提下完整复刻 Python 行为。
