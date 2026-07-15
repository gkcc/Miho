# 自更新与本地评判能力报告

- 初版生成时间：2026-07-06
- 最近审计：2026-07-16
- 当前结论：单一 Rust native update runner、配置摘要绑定的 state/receipt/health、跨进程 workspace writer lease、安装/portable 候选切换事务和 hash-bound NSIS/portable 发布链均已有实现。历史 active 的 installed-owner 读取和生产前端嵌入缺陷已在 clean `1f8352be0bbcdae3c306be603bac010338cb343c` 修复并发布新 active；实际安装目录已原位升级，DOM、计划任务、HSR/ZZZ exact health、AppData/Box/owner 保留和零 Python检查通过。当前精确 commit/hash 以 active manifest 为准，安装包仍为 `NotSigned`。

## 已验收外部矩阵与剩余边界（2026-07-15）

- 真实 failure-upgrade 在 `VerifyDynamic` 删除 Start Menu shortcut 后返回 1603，durable failure receipt 保存精确 mode；rollback 恢复静态 payload、automation owner、任务 generation、快捷方式 Target/WorkingDirectory、typed registry tree 与 DACL，随后 transaction root 正常 Finalize 删除。
- 真实 success-upgrade 返回 0；candidate run + exact config-bound health 对 HSR/ZZZ 均 healthy，owner identity 保持不变。canonical `MiHoYoEndgameDailyUpdate` 已真实 Running→Ready，`LastTaskResult=0` 且 generation/attempt 由 Rust health 精确确认，整个矩阵未观察到 Python 进程。
- 前序 verification 矩阵的 portable 在空 PATH 下通过 CLI version/help、桌面 5 秒与 online update；该轮卸载时 `%APPDATA%\com.miho.endgame` 的 753 文件、520 目录、297,219,938 字节及整树摘要 `a650910ec18ec50542d980cd926f3ae46c5c7b9e8cc1a6e001b6f5cb689076cc` 前后不变。
- 首次 active 最终字节又独立完成 clean install/health/uninstall：卸载前后含测试 canary 的 AppData 均为 755 文件、520 目录、297,294,737 字节，整树摘要均为 `0c0637cb2c971c96c749f3efa38112815b0c2585e30c7fbb2aef8d34242f2c28`；随后只精确删除测试 canary。该轮验收结束时安装根、任务、automation owner、产品/卸载注册表、快捷方式与 transaction/failure receipt 均不存在，仅允许 0 字节 installer lease 文件保留；这不是用户后续安装后的当前状态。
- 默认完整构建即使源码 clean 也保持 `verification-only`；只有独立 `Blocker=0 / High=0` 和项目门禁留痕齐备后，clean full Release 才能显式使用 `-ProjectGatesApproved`。首次 active 的 NSIS SHA-256 为 `a807a21a6efe57f579c5552192661a9c4cc6918fb54b9e090c82e0db4f73f66b`、portable ZIP 为 `89d7b51893864c5dcf818a8aaaedb47ef134e366d86814237efc2a3dddc1b660`；后续重建不复用历史哈希，当前值只读 `target/release/bundle/miho-release-artifacts-v1.json`。dirty、`-NoBundle` 或非 Release 调用携带批准仍会硬失败。
- installer helper 的 abrupt recovery 已补机器门禁：PowerShell 5.1/7 都在第一项静态文件完成后强杀一次、进入 durable `rolling-back` 后再强杀一次，最后由原始未插桩 helper 恢复 clean before-image、删除 owner 与事务根。该证据不外推为物理掉电或 NSIS 所有 phase 的完整恢复。
- 仍未完成且不得过度声称的边界：Authenticode 正式签名、跨账户/跨 session release lease 实测、完整 NSIS Prepare/Commit 强杀与物理掉电 recovery。当前 medium-integrity 非提权令牌能注册 interactive task，但 S4U 非交互 task 精确返回 `0x80070005`，所以没有拿同 session 子进程冒充跨 session 证据。这些属于后续扩展可靠性；最终交付仍须明确披露 `NotSigned`。

## installed GUI 现场纠偏与升级保护基线（2026-07-15）

- 用户随后把历史 active 安装到 `D:\Miho Endgame`。安装与首次 HSR/ZZZ update 成功，但 installed desktop 双击在约 25 ms 后以 101 退出，stderr 为 `installed automation owner identity is invalid`；WebView2 尚未进入创建阶段。现场 owner `9d8fbf93-afa2-45dd-8a06-5cb0da2ec3af` 在注册表、automation owner/authority 中完全一致，计划任务 `MihoEndgameDailyUpdate-4bfbc997e809d2ec` 为 `Ready`，因此不能删除 owner 绕过。
- Win32 复刻证明同一合法 `REG_SZ` 的第一次 `RegGetValueW` 容量探测为 76 字节、第二次成功读取为 74 字节。旧桌面错误要求两次长度精确相等；修复改为校验第二次长度不小于 2、为偶数且不超过 buffer 后按实际长度截断，再执行原有 canonical UUID/NUL/type 校验。真实 HKCU 唯一键与 76→74 合成回归均通过，完整临时 installed-mode 布局也已建立窗口、存活 5 秒并正常退出 0。
- 纠偏前升级保护基线：AppData 为 757 文件、521 目录（含根）、297,650,034 字节、0 reparse，规范化逐路径树摘要为 `4c7a8884bb320880a4db5bbf4b42b3581927fa125557fb03496fa7a9c7a9746a`；task XML SHA-256 为 `6651f845340dba46e5a0595eaf9911d202b494e91ee3504ff1f7c83c8beba99b`；安装根 19 文件、35,510,740 字节，17/17 static payload 精确匹配，旧 desktop SHA-256 为 `701609ad583f85faf35fc44f34286d7ff31d22ad543ed52d4906b46063afc3fc`。
- 当时要求的最终验证是：先从新 clean HEAD 构建 full `verification-only` 候选，以其精确 NSIS 原位升级这个旧版现场，保留同一 owner 并核对新 static manifest、task/authority/owner、exact update health、AppData canary 和零 transaction/failure 残留；随后从完整安装目录启动 desktop，要求非零窗口、至少 5 秒存活、正常关闭、退出 0、stderr 空和零 Python。门禁与独立复核清零后，同一 clean HEAD 才能用 `-ProjectGatesApproved` 重建 active；active NSIS 哈希若与已测候选不同，就必须对 active 精确字节重跑同一 smoke。先卸载会删除最有价值的已有 owner/task 现场，不能用 clean install 取代这条升级证据；portable smoke 也因绕过 installed-owner 分支而无资格代证。该要求已由下文记录的 clean `1f8352b` active 完成。

## 前端嵌入与真实页面门禁纠偏（2026-07-16）

- owner 读取修复让候选进入 WebView 后，完整发布构建仍被真实页面门禁挡住：生产首页是已清理 release staging 的 `file:///.../frontend-dist`，用户截图对应 WebView2 `ERR_FILE_NOT_FOUND`。根因是生成 overlay 把 `frontendDist` 写成 Windows 绝对路径，而 Tauri 的 untagged `FrontendDist` 先按 URL 解析；这条路径因此没有进入资产嵌入分支。
- 发布脚本现从隔离 build workspace 的 `crates/miho-desktop/src-tauri` 生成到 immutable `frontend-dist` 的安全相对路径。producer 和一次性 staged verifier 都拒绝绝对路径、反斜杠、URL、reparse 或错误 round-trip；`custom-protocol` feature 显式映射到 `tauri/custom-protocol`，所有 release Cargo/Tauri pass 均携带该 feature，release entry point 缺失时编译失败。
- dirty full verification build 以 exit 0 收口。精确候选 desktop SHA-256 为 `cde1cecb8c03dd7fc98c1d224f08b7ed77b29b01cfc9ac3544c5edca46b55950`；installed-mode CDP 回执要求并得到 `https://tauri.localhost/#miho-app-ready-v1`、真实 `data-miho-app-ready=v1`、`MIHO ENDGAME`、DOM complete、Tauri internals、非错误页、至少 5 秒、正常退出 0、空 stdout/stderr、零 Python和清理后代/调试端口。owner/task/workspace/Roaming AppData 未变；默认 WebView cache 的预期变化单独披露为 SHA `08cffe88…` → `5fd02fab…`、`+1391` bytes。
- 提交前最终对抗复核发现首版 cache 回执只按 Mode 声称默认目录，未证明真实 WebView2 没有受 `WEBVIEW2_USER_DATA_FOLDER` 或策略重定向；历史默认目录存在时可能假绿。门禁现先从子进程环境移除继承 override，再绑定实际调试监听者的进程代际和唯一 `--user-data-dir`，要求精确等于默认 cache 的 `EBWebView` 子目录，并在关闭后重做无 reparse 路径核验；既有 parent tree 差分因此覆盖已证明被浏览器使用的目录。缺失、相对、重复、空值和外部路径反例在 WinPS 5.1/pwsh 7 均通过，真实 dirty installed DOM 冒烟也返回 `webview_user_data_directory_bound=true`。
- clean `1f8352be0bbcdae3c306be603bac010338cb343c` 随后完成 verification-only、实际安装目录原位升级、installed DOM/owner/task/exact health/AppData/零 Python复验和最终 active 发布。最终 active 与早期 verification 哈希不同，因此又对 active 精确字节重跑安装、GUI、任务和 health；当前该门禁已收口。

## 已验收 native 自动化基线（历史矩阵终态为卸载）

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
