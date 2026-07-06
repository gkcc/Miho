# GPT Pull Reviewer Packet

## 使用方式

把本文件交给 Codex/GPT，要求它基于证据重新评审每个候选角色的 X+X 档位。
这是无 API key 的交互版：本地负责自动更新数据和证据包，GPT 评判由你登录后发起。

## 评审规则

- 不要只按 target coverage 定性；复刻角色必须同时看历史走势、全局出场、T 榜定位、current/target 覆盖和 X+X 必要性。
- 新角色没有历史队伍记录只能标记为未实测，不能作为负面扣分。
- C 档或 theoretical-only 不能作为抽取/档位主依据。
- sentinel 分数不能当真实表现。
- 输出每个角色的建议档位、理由、反证、需要等待的数据，以及是否建议立刻抽。

## 建议提问

请读取这个 packet，按长期 auto 高难奖励目标，评审每个候选角色应该抽到 X+X。输出：结论表、每人证据链、风险、需要等的数据。

## Evidence Payload

```json
{
  "summary": {
    "generated_at": "2026-07-06T21:03:58",
    "data_dir": "out_zzz",
    "box_path": ".miho\\zzz_box_state.json",
    "plan_path": "configs\\zzz_banner_plan.json",
    "candidate_count": 2,
    "planned_slugs": [
      "nom",
      "sunna"
    ],
    "current_coverage_records": 7,
    "target_coverage_records": 14
  },
  "candidates": [
    {
      "slug": "sunna",
      "name_cn": "千夏",
      "candidate_type": "rerun",
      "status": "next",
      "local_rule_pull_value": "高",
      "local_rule_stage": "0+0 优先；0+1 只在专属/影画收益实测显著时考虑；当前数据不能证明 1+1 或 2+1 必要",
      "history_summary": "sd: points 8 / latest 53.72% / avg_last3 53.947% / trend 24.53；da: points 8 / latest 46.41% / avg_last3 52.06% / trend 4.45",
      "global_usage_summary": "best_latest=53.72%；best_avg_last3=53.947%；worst_trend=4.45",
      "team_coverage_summary": "current 0(0)；target 7(B- 6 / C 1)；新增依赖 7(B- 6 / C 1)",
      "mechanism_summary": "物理 / 支援 / 辅助；复刻辅助重点看泛用性、队友覆盖面，以及是否能补你 Box 的主C缺口。",
      "replacement_risk": "辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断",
      "decision_basis": [
        "T 榜最好评级 T0 / rating 11",
        "历史出场点 16，近三期最高均值 53.947%",
        "目标 Box 新增依赖队伍 7 条，其中 A/B+ 0 条、A/B+/B 0 条"
      ],
      "risk_notes": [
        "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性"
      ],
      "evidence_ids": [
        "E0007",
        "E0008",
        "E0009",
        "E0010",
        "E0011"
      ]
    },
    {
      "slug": "nom",
      "name_cn": "诺姆·霍洛维尔",
      "candidate_type": "new",
      "status": "next",
      "local_rule_pull_value": "等实测",
      "local_rule_stage": "暂不预设 X+X；等机制与首轮高难数据后再评估 0+0 / 0+1",
      "history_summary": "暂无历史出场；若为新角色，这是未实测状态，不作为负面",
      "global_usage_summary": "best_latest=0%；best_avg_last3=0%；worst_trend=0",
      "team_coverage_summary": "current 0(0)；target 0(0)；新增依赖 0(0)",
      "mechanism_summary": "未知 / 未知 / 未知；新角色在实测前只做关系识别：属性、特性、核心队友、是否替代已有主推体系。",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
        "未知 / 未知 / 未知；新角色在实测前只做关系识别：属性、特性、核心队友、是否替代已有主推体系。",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "机制、倍率、专属收益和售后环境尚未落地",
        "替代风险无法从当前历史数据判断"
      ],
      "evidence_ids": []
    }
  ]
}
```

## 相关文件

- pull value report: `out_zzz\pull_value_report.md`
- current coverage: `out_zzz\current_box_team_coverage.md`
- target coverage: `out_zzz\target_box_team_coverage.md`
- team signature aggregates: `out_zzz\team_signature_aggregates.csv`
