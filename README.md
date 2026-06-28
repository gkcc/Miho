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
  --tier-snapshot data/probes/tier/zzz_tier_snapshot.json
```

`--tier-snapshot` 只读取本地 JSON，不联网抓取，不生成最终抽取建议。只有 `data/probes/roster/roster_index.json` 中的 accepted roster 才会被标记为已确认拥有练度；demo normalized snapshot 仍然需要人工确认。若同时生成 action cards，tier / 保值信号只用于解释或降级本地行动优先级，避免为了短期奖励继续加码低保值角色。

## Tier Snapshot 草案

本地 tier snapshot 可以使用如下结构：

```json
{
  "source": {
    "name": "manual tier snapshot",
    "source_type": "manual",
    "source_ref": "local"
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
