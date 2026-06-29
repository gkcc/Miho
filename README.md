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

如果已有 accepted roster 和 team cards，demo pipeline 还会生成 `demo_command.json/md` 记录本次可回放命令，再生成 `run_manifest.json`、`endgame_plan.json/md`、`refresh_status.json/md`、`final_brief.json/md`、`action_checklist.json/md` 和 `review_decision_preview.json/md`。Dashboard 顶部会先展示“刷新状态”，再展示“今日作战简报”和“执行清单”：apply receipt 只证明复核决策产生了副作用，不代表高难方案已经基于最新 roster 重算；如果 receipt 比 run manifest 新、当前 roster hash 与 run manifest 不一致，或刷新状态为 `unknown`，`refresh_status` 会把 `try_now` 降级/阻断，并显示真实重跑命令。简报和清单只聚合本地 run manifest、accepted roster、review inbox、roster delta、本期高难方案和本地 tier / 保值观察；如果 run manifest 缺失、错批、refresh stale/unknown，会先显示数据警告，并阻断可执行 `try_now`。它不是抽卡建议，不输出“必抽 / 建议抽 / 跳过”，也不保证自动通关；`pending_snapshot`、`catalog_candidate`、stale/unverified tier、错批产物、stale/unknown apply refresh 或缺少 target evidence 都不能提升为可信 `try_now`。待复核快照只会生成 `review_decisions_template.json`，默认 `decision=pending`，不会自动 accept；人工改成 accept 前必须先跑 `preview_review_decisions.py`，确认 template/run/normalized hash 未错批，且 preview 只显示 `would_enter_roster`，不会写 accepted/rejected。真正 apply 时必须带同一个 decision manifest 对应的 `--preview-result` 和 `--require-preview-ready`；accepted snapshot 会写入 `review_apply_audit` 供追溯，apply 还会写 `review_apply_receipt.json/md`。demo pipeline 会读取 receipt 并在 Dashboard 的“复核应用回执”面板展示每条 decision 是否写入 accepted/rejected、是否进入 roster index、是否经过 preview 校验。

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
