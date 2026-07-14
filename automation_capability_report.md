# 自更新与本地评判能力报告

- 初版生成时间：2026-07-06
- 最近审计：2026-07-15
- 当前结论：单一 Rust native update runner、配置摘要绑定的 state/receipt/health、跨进程 workspace writer lease、安装/portable 候选切换事务和 hash-bound NSIS/portable 发布链均已有实现、回归与真实 Windows 矩阵证据；下述 Python 编排只保留为历史说明。真实升级、回滚、canonical Task Scheduler、portable online update 与最终卸载均在空 PATH/零 Python 下通过。当前外部状态是“产品已完整卸载、用户 AppData 原样保留”，矩阵候选仍是 `verification-only` 且 `NotSigned`；待独立终审和提交后才能从 clean HEAD 构建 active。

## 当前外部状态与剩余边界（2026-07-15）

- 真实 failure-upgrade 在 `VerifyDynamic` 删除 Start Menu shortcut 后返回 1603，durable failure receipt 保存精确 mode；rollback 恢复静态 payload、automation owner、任务 generation、快捷方式 Target/WorkingDirectory、typed registry tree 与 DACL，随后 transaction root 正常 Finalize 删除。
- 真实 success-upgrade 返回 0；candidate run + exact config-bound health 对 HSR/ZZZ 均 healthy，owner identity 保持不变。canonical `MiHoYoEndgameDailyUpdate` 已真实 Running→Ready，`LastTaskResult=0` 且 generation/attempt 由 Rust health 精确确认，整个矩阵未观察到 Python 进程。
- portable 在空 PATH 下通过 CLI version/help、桌面 5 秒与 online update；最终 uninstall 返回 0，并删除安装根、任务、automation owner、产品/卸载注册表与快捷方式。`%APPDATA%\com.miho.endgame` 的 753 文件、520 目录、297,219,938 字节及整树摘要 `a650910ec18ec50542d980cd926f3ae46c5c7b9e8cc1a6e001b6f5cb689076cc` 前后不变；仅保留 0 字节 installer lease 文件。
- 默认完整构建即使源码 clean 也保持 `verification-only`；真实矩阵虽已完成，仍须把独立 `Blocker=0 / High=0` 和主线程回应写回 `PROJECT.md` 并提交，才可从 clean HEAD 显式使用 `-ProjectGatesApproved`。dirty、`-NoBundle` 或非 Release 调用携带该批准都会失败。
- 仍未完成且不得过度声称的边界：Authenticode 正式签名、跨账户/跨 session release lease 实测、安装过程中强杀/掉电的完整 journal recovery。它们不否定当前同账户真机可用性，但必须与最终 `NotSigned` active 产物一起明确披露。

## 当前 native 自动化基线（实现与真实切换已验证，最终外部状态为卸载）

- `miho update run --workspace ... --config ...` 在一个 OS lease 内按 HSR export → ZZZ export → coverage → pull-value → review-packet 顺序运行；任一所选步骤失败均退出 1，不推进成功 state。
- online update 对 HF 主源拒绝 last-good cache fallback；手动 direct export 仍保留兼容回退。补充来源降级继续通过结构化 diagnostic 使 update 失败，不能用旧数据伪造新完成时间。
- `.miho/update-state-v1.json`、canonical receipt 与逐 attempt receipt 绑定精确 config SHA-256 和全部产物 hash；health 会重读 generation receipt 并逐文件验证。
- `.miho/workspace-write-v1.lock` 由 update、direct export/report、TaskManager 与桌面 Box writer 共用；receipt/cache/产物读取在跟随 symlink/junction 前 fail closed。
- `scripts/update_endgame_data.ps1` 现仅解析 native CLI、调用 `update run` 再调用 `update health`；不再包含 Python probe、`python -m`、旧 freshness marker 或业务编排。
- `scripts/native_command.ps1` 在 Windows PowerShell 5.1 和 PowerShell 7（含 native error preference + EAP Stop）精确保留 native 0/2/7，真正的 launch failure 不会被伪装成 native exit。

## 历史：旧 Python 脚本设计上能自动更新的部分

| 项目 | 当前能力 | 证据 |
|---|---|---|
| HSR 终局数据 | 可按日期窗口重新拉取 HF 数据、Prydwen 可见队伍、Prydwen Tier List，并重建 `out/` | `python -m hsr_endgame_exporter export` |
| ZZZ 终局数据 | 可按日期窗口重新拉取 HF 数据、Prydwen 可见队伍、Prydwen Tier List，并重建 `out_zzz/` | `python -m zzz_endgame_exporter export` |
| ZZZ 队伍覆盖 | 可在刷新后自动重建 `team_signature_aggregates.csv`、`current_box_team_coverage.md`、`target_box_team_coverage.md` | `python -m zzz_endgame_exporter coverage` |
| ZZZ 抽取价值 | 可在刷新后自动重建 `current_pull_value_report.md` / `next_pull_value_report.md`，并合并 historical_usage / target_coverage / mechanism_review | `python -m zzz_endgame_exporter pull-value` |
| 无 key GPT 交互评审 | 可在刷新后自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，登录后交给 Codex/GPT 做 X+X 评判 | `python -m zzz_endgame_exporter review-packet` |
| 定时执行 | 可注册 Windows Task Scheduler 每日任务；每天触发但按数据源状态跳过重复导出 | `scripts/install_daily_update_task.ps1` |

## 还不能完全自动的部分

| 项目 | 当前限制 | 下一步 |
|---|---|---|
| 卡池计划自动识别 | `configs/zzz_banner_plan.json` 和 `configs/hsr_banner_plan.json` 仍是结构化输入；官方新闻变化不会自动改配置 | 增加官方新闻/公告解析器，输出标准 banner plan JSON，并做人工确认或 diff 报告 |
| 机制断点资料 | `configs/zzz_mechanism_notes/*.yaml` 已可接入报告，并记录 source_quality、stage_confidence、stage_notes | 后续卡池更新时补充技能、专武、影画和攻略来源 |
| HSR 目标账号 pull value | 当前 HSR 已有数据导出与方法论产物，但 pull-value CLI 先落在 ZZZ | 复用 `miho_core.evidence` 做 HSR 角色计划报告适配 |
| 无人值守 GPT 模型评判 | 当前选择不使用 API key，因此不能做到无人值守调用 GPT | 使用 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md` 作为交互版；若未来要全自动，再接入 `OPENAI_API_KEY` |

## 当前兼容 launcher 手动入口（需已有 native CLI）

手动运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_endgame_data.ps1
```

注册每日任务（源码级兼容入口；正式安装应优先由 installer-owned transaction 创建和管理）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_update_task.ps1 -At "09:30"
```

以下是已退役 Python 编排过去会执行的逻辑，仅作迁移审计记录；当前 launcher 不再执行这些 signature/mtime 分支：

1. 检查 HSR/ZZZ Hugging Face `config.json` 与顶层 snapshot 目录，生成源数据 signature。
2. 若源数据 signature 与 `.miho/update_source_state.json` 记录一致，并且核心输出存在，则跳过对应游戏的 export。
3. 若 ZZZ 源数据未变化但 Box、banner plan、mechanism notes 或 baseline 有变化，仍会重建 coverage / pull-value / review-packet。
4. `.miho/update_source_state.json` 记录的是数据源最新 snapshot / collect_date，不用本地任务触发时间当“最后更新时间”。
5. 需要强制全量刷新时可加 `-Force`。

## GPT 本地集成方案

当前采用无 API key 的交互版：

- 本地规则层：负责拉数据、清洗、聚合、置信度、coverage、候选角色基础分。
- GPT reviewer 层：你登录后让我读取 `out_zzz/current_gpt_pull_reviewer_packet.md` 或 `out_zzz/next_gpt_pull_reviewer_packet.md`，我基于证据包输出 X+X 档位建议、理由和反证。
- 校验层：禁止 GPT 使用 C 档或 theoretical-only 作为主证据；禁止把新角色无历史记录当负面。
- 降级层：即使不进行 GPT 对话，仍输出本地规则报告。

如果未来要做到“无需登录、每日自动调用模型”，仍需要先确认是否复用/创建 `OPENAI_API_KEY`，不能把密钥写死在仓库里。
