# 自更新与本地评判能力报告

- 生成时间：2026-07-06
- 当前实现：`scripts/update_endgame_data.ps1` 一键刷新；`scripts/install_daily_update_task.ps1` 可注册 Windows 每日任务；脚本会先检查 HF 数据源最新 snapshot / collect_date，源数据未变化时跳过重导出。

## 已经能自动更新的部分

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

## 每日更新建议

手动运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_endgame_data.ps1
```

注册每日任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_update_task.ps1 -At "09:30"
```

任务每天会执行：

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
