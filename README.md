# Miho

本仓库当前仍处于本地 probe / demo 阶段，不初始化完整 Tauri 工程，不自动导入正式数据库。

## Demo 与验收入口

成品体验入口：

```powershell
scripts/run_miho_demo.bat
```

准确率验收使用 manifest，不要扫描整个 `data/probes/parsed`：

```powershell
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

本地 demo 可以额外传入 tier / 保值快照，用于把本地 tier list 观察项和已确认 Box 对齐：

```powershell
python tools/probes/run_demo_pipeline.py `
  --parsed-dir data/probes/parsed `
  --latest-only `
  --tier-snapshot data/probes/tier/zzz_tier_snapshot.json `
  --tier-stale-days 60
```

`--tier-snapshot` 只读取本地 JSON，不联网抓取，不生成最终抽取建议。只有 `data/probes/roster/roster_index.json` 中的 accepted roster 才会被标记为已确认拥有练度；demo normalized snapshot 仍然需要人工确认。同一角色多次人工确认时，roster index 只保留 `accepted_at` 最新的一份作为当前 box，旧快照会写入 `duplicates` / `superseded_snapshots` 供追溯。若同时生成 action cards / team cards，tier / 保值信号只用于解释、降级本地行动优先级，或辅助已确认队伍排序，避免为了短期奖励继续加码低保值角色。`stale` / `unverified` tier 只能作为弱参考，不会提升队伍排序。

人工确认后可生成本次 box 变化影响报告。`apply_review_decisions.py` 会在重建当前 `roster_index.json` 前，把旧 index 备份到 `data/probes/roster/history/`；demo pipeline 检测到 previous/current roster index 时，会生成 `roster_delta.json/md` 并在 Dashboard 展示“本次练度更新影响”。该 delta 只比较 accepted roster 当前保留版本，不包含 pending snapshot、rejected snapshot 或 catalog candidate。

如果已有 accepted roster 和 team cards，demo pipeline 还会生成 `demo_command.json/md` 记录本次可回放命令，再生成 `run_manifest.json`、`endgame_plan.json/md`、`refresh_status.json/md`、`final_brief.json/md`、`action_checklist.json/md`、`review_decision_preview.json/md` 和 `demo_doctor.json/md`。Dashboard 顶部会先展示“当前状态诊断”，如果存在 latest launcher report 则紧接着展示“启动器执行记录”，再展示“刷新状态”“今日作战简报”和“执行清单”：apply receipt 只证明复核决策产生了副作用，不代表高难方案已经基于最新 roster 重算；如果 receipt 比 run manifest 新、当前 roster hash 与 run manifest 不一致，或刷新状态为 `unknown`，`refresh_status` 会把 `try_now` 降级/阻断，并显示真实重跑命令。`demo_doctor` 会把 refresh、preview、apply、review inbox 和 checklist 合成一个下一步判断：需要重跑、需要复核、需要 safe apply，或可以执行 try_now；同时用 `evidence_check.status` 和 `evidence_check.strict_status` 校验当前 preview、apply receipt、run_manifest 和 demo command 是否来自同一批证据。旧 apply receipt、缺失 preview/decision hash、decision hash 错批、preview/run manifest 错批或不可回放的重跑命令会把诊断降级为 `needs_apply` 或 `blocked`；`action_contract` 会明确下一步是否只读、是否写 roster、是否需要人工确认、是否允许后续 launcher 只打印/执行。简报和清单只聚合本地 run manifest、accepted roster、review inbox、roster delta、本期高难方案和本地 tier / 保值观察；如果 run manifest 缺失、错批、refresh stale/unknown，会先显示数据警告，并阻断可执行 `try_now`。它不是抽卡建议，不输出“必抽 / 建议抽 / 跳过”，也不保证自动通关；`pending_snapshot`、`catalog_candidate`、stale/unverified tier、错批产物、stale/unknown apply refresh 或缺少 target evidence 都不能提升为可信 `try_now`。待复核快照只会生成 `review_decisions_template.json`，默认 `decision=pending`，不会自动 accept；人工改成 accept 前必须先跑 `preview_review_decisions.py`，确认 template/run/normalized hash 未错批，且 preview 只显示 `would_enter_roster`，不会写 accepted/rejected。真正 apply 时必须带同一个 decision manifest 对应的 `--preview-result` 和 `--require-preview-ready`；accepted snapshot 会写入 `review_apply_audit` 供追溯，apply 还会写 `review_apply_receipt.json/md`。demo pipeline 会读取 receipt 并在 Dashboard 的“复核应用回执”面板展示每条 decision 是否写入 accepted/rejected、是否进入 roster index、是否经过 preview 校验。

`tools/probes/doctor_launcher.py` 是 P3.0-lite 的安全引导器：默认只读取 `demo_doctor.json`、打印下一步和生成 `launcher_report.json/md`。只有显式 `--execute-rerun`，且 `primary_next_action=rerun_demo_pipeline`、`action_contract.allowed_for_launcher=true`、`writes_roster=false`、`requires_manual_confirmation=false`、`evidence_check.strict_status` 非 `blocked`，并且命令白名单确认为 `python tools/probes/run_demo_pipeline.py ...` 时，才允许执行重跑命令；P3.4-lite 还会把脚本路径 canonicalize，要求它 resolve 后等于当前仓库内的 `tools/probes/run_demo_pipeline.py`，否则阻断为 `launcher_command_path_not_canonical`。launcher 永远不会执行 safe apply、try_now、`.bat/.cmd/.ps1/.sh` 或任何写 roster 动作。`--fail-on-blocked` 可让只打印模式在发现 blocker 时返回非零，适合脚本验收。

P3.4-lite 可在安全重跑成功后追加 `--follow-up-doctor data/probes/demo/demo_doctor/demo_doctor.json`。launcher 只读取重跑后的新 doctor，并在 report 里写入 `rerun_started_at`、`rerun_finished_at`、`command_script_resolved`、`follow_up.sha256`、`follow_up.changed_from_initial_doctor`、`follow_up.mtime_epoch`、`follow_up.updated_after_rerun`、`follow_up.doctor_status`、`follow_up.primary_next_action`、`follow_up.try_now_allowed`、`follow_up.strict_status`、`follow_up.evidence_status`、`follow_up.evidence_blockers`、`follow_up.blocking_reasons` 和相关 warnings；即使 follow-up 显示 `needs_apply` 或 `try_now`，launcher 也只打印下一步，不执行后续动作。follow-up doctor 缺失、JSON 损坏、不是对象、未更新、mtime 早于 rerun 开始或 blocked 会产生 `executed_with_followup_warning`，默认不把成功重跑判失败；脚本验收可加 `--fail-on-followup-warning` 让这些 follow-up warning 返回非零。launcher 会保留 latest `launcher_report.json/md`，并追加写入 `launcher/history/launcher_report_<timestamp>.json/md`。

P3.5-lite 起，demo pipeline 如果发现 `data/probes/demo/launcher/launcher_report.json`，Dashboard 会只读展示“启动器执行记录”：`launcher_status`、`executed`、`returncode`、canonical script path、rerun 起止时间、follow-up doctor 状态、warnings/blockers 和 history report 链接。P3.6-lite 会用 latest launcher report 里的 `initial_doctor_sha256` / `follow_up.sha256` 对比当前 `demo_doctor.json`，并显示 `launcher_report_freshness=current/stale/unknown`；P3.6-fix 进一步区分 `follow_up_matches_current_doctor` 和 `launcher_report_operation_state`，只有 `follow_up.sha256` 本身匹配当前 doctor 时才展示 follow-up 的当前操作态。仅 `initial_doctor_sha256` 匹配时，report 仍可视为当前 Dashboard 的历史审计记录，但 follow-up 只能审计，不能显示“游戏内可尝试”或 safe apply 操作态。stale/unknown report 也只作为历史审计，不提供 safe apply、try_now 或任何写 roster 的执行入口。

P3.7-lite 起，`doctor_launcher.py` 可在写入 latest launcher report 后追加 `--refresh-dashboard`。该参数只读取既有 `data/probes/demo/demo_summary.json`，重新注入 latest launcher report，并调用 Dashboard renderer 生成 `data/probes/demo/index.html`；它不会重跑 demo pipeline、不会 OCR、不会 normalize、不会 planner、不会写 roster，也不会执行 safe apply 或 try_now。缺失或损坏的 `demo_summary.json` 只会把 `dashboard_refresh.status` 标成 `warning` 并写入 launcher report，不改变 rerun 本身的成功/失败口径。

## Tier Snapshot 草案

本地 tier snapshot 可以使用如下结构：

```json
{
  "source": {
    "name": "manual tier snapshot",
    "source_type": "manual",
    "source_ref": "local",
    "period": "2026-06",
    "captured_at": "2026-06-29T00:00:00+08:00",
    "content_sha256": "local-source-content-sha256",
    "trust_level": "high"
  },
  "entries": [
    {
      "character": "星见雅",
      "tier": "S",
      "retention_score": 0.9,
      "usage_rate": "40%",
      "trend": "stable",
      "modes": ["危局强袭战"],
      "value_tags": ["high_retention"]
    }
  ]
}
```

真实图片、UID、OCR 原始结果、cookie/token、账号标识和本地账号数据不得提交。
