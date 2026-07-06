# GPT Pull Reviewer Packet

## 使用方式

把本文件交给 Codex/GPT，要求它基于证据重新评审每个候选角色的 X+X 档位。
这是无 API key 的交互版：本地负责自动更新数据和证据包，GPT 评判由你登录后发起。

## 评审规则

- 不要只按 target coverage 定性；复刻角色必须同时看历史走势、全局出场、T 榜定位、current/target 覆盖和 X+X 必要性。
- 必须把 historical_usage、target_coverage、mechanism_review 三类证据分开列出，再综合判断。
- 新角色没有历史队伍记录只能标记为未实测，不能作为负面扣分。
- C 档或 theoretical-only 不能作为抽取/档位主依据。
- sentinel 分数不能当真实表现。
- 输出每个角色的 recommended_stage、unresolved_stage、stage_confidence、not_recommended_stage、理由、反证、需要等待的数据，以及是否建议立刻抽。

## 建议提问

请读取这个 packet，按长期 auto 高难奖励目标，评审每个候选角色应该抽到 X+X。输出：结论表、每人证据链、风险、需要等的数据。

## Evidence Payload

```json
{
  "summary": {
    "generated_at": "2026-07-06T23:25:41",
    "data_dir": "out_zzz",
    "box_path": ".miho\\zzz_box_state.json",
    "plan_path": "configs\\zzz_banner_plan.json",
    "candidate_count": 4,
    "planned_slugs": [
      "velina",
      "ye-shunguang",
      "piper",
      "nicole-demara"
    ],
    "current_coverage_records": 7,
    "target_coverage_records": 7,
    "mechanism_notes_dir": "configs\\zzz_mechanism_notes"
  },
  "candidates": [
    {
      "slug": "ye-shunguang",
      "name_cn": "叶瞬光",
      "candidate_type": "rerun",
      "status": "current",
      "local_rule_pull_value": "高",
      "stage_recommendation": {
        "recommended_stage": "等技能/影画/专武/首轮数据",
        "acceptable_stage": "暂不预设",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断",
        "reason": "缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X",
        "missing_data": "技能机制、影画、专武、实战队伍、首轮高难数据"
      },
      "history_summary": "sd: points 8 / latest 78.29% / avg_last3 77.59% / trend -0.69；da: points 8 / latest 62.83% / avg_last3 67.693% / trend -13.6",
      "global_usage_summary": "best_latest=78.29%；best_avg_last3=77.59%；worst_trend=-13.6",
      "team_coverage_summary": "current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "物理 / 强攻 / 直伤主C；复刻角色应优先看长期趋势、主推队友占用和你 Box 里是否已有同定位主C。",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T0 / rating 11",
        "历史出场点 16，近三期最高均值 77.59%",
        "目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖",
        "当前 Box 已有相关队伍 1 条",
        "mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据"
      ],
      "risk_notes": [
        "已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序"
      ],
      "evidence_ids": [
        "E0006"
      ]
    },
    {
      "slug": "nicole-demara",
      "name_cn": "妮可·德玛拉",
      "candidate_type": "rerun",
      "status": "current",
      "local_rule_pull_value": "中",
      "stage_recommendation": {
        "recommended_stage": "等技能/影画/专武/首轮数据",
        "acceptable_stage": "暂不预设",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断",
        "reason": "缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X",
        "missing_data": "技能机制、影画、专武、实战队伍、首轮高难数据"
      },
      "history_summary": "sd: points 8 / latest 2.46% / avg_last3 2.797% / trend -3.73；da: points 8 / latest 3.75% / avg_last3 3.19% / trend -0.88",
      "global_usage_summary": "best_latest=3.75%；best_avg_last3=3.19%；worst_trend=-3.73",
      "team_coverage_summary": "current 2(B- 1 / C 1)；target 2(B- 1 / C 1)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "以太 / 支援 / 辅助；以太支援老角色，更多看你是否缺对应辅助和影画。",
      "replacement_risk": "辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断",
      "decision_basis": [
        "T 榜最好评级 T0.5 / rating 10",
        "历史出场点 16，近三期最高均值 3.19%",
        "目标 Box 可组历史队伍 2 条，但不是该角色作为新增依赖",
        "当前 Box 已有相关队伍 2 条",
        "mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据"
      ],
      "risk_notes": [
        "已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序"
      ],
      "evidence_ids": [
        "E0002",
        "E0007"
      ]
    },
    {
      "slug": "piper",
      "name_cn": "派派·韦尔",
      "candidate_type": "rerun",
      "status": "current",
      "local_rule_pull_value": "中",
      "stage_recommendation": {
        "recommended_stage": "等技能/影画/专武/首轮数据",
        "acceptable_stage": "暂不预设",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断",
        "reason": "缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X",
        "missing_data": "技能机制、影画、专武、实战队伍、首轮高难数据"
      },
      "history_summary": "sd: points 8 / latest 0.32% / avg_last3 0.36% / trend -0.16；da: points 8 / latest 0.54% / avg_last3 0.567% / trend 0.07",
      "global_usage_summary": "best_latest=0.54%；best_avg_last3=0.567%；worst_trend=-0.16",
      "team_coverage_summary": "current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "物理 / 异常 / 异常主C；陪跑只作为顺带收益，不单独驱动抽卡。",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T1 / rating 9",
        "历史出场点 16，近三期最高均值 0.567%",
        "目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖",
        "当前 Box 已有相关队伍 1 条",
        "mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据"
      ],
      "risk_notes": [
        "已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序"
      ],
      "evidence_ids": [
        "E0003"
      ]
    },
    {
      "slug": "velina",
      "name_cn": "维琳娜·艾嘉德",
      "candidate_type": "new",
      "status": "current",
      "local_rule_pull_value": "等实测",
      "stage_recommendation": {
        "recommended_stage": "等技能/影画/专武/首轮数据",
        "acceptable_stage": "暂不预设",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断",
        "reason": "缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X",
        "missing_data": "技能机制、影画、专武、实战队伍、首轮高难数据"
      },
      "history_summary": "sd: points 1 / latest 10.34% / avg_last3 10.34% / trend 0；da: points 1 / latest 48.99% / avg_last3 48.99% / trend 0",
      "global_usage_summary": "best_latest=48.99%；best_avg_last3=48.99%；worst_trend=0",
      "team_coverage_summary": "current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
        "风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "等技能/影画/专武/首轮数据",
        "替代风险无法从当前历史数据判断"
      ],
      "evidence_ids": [
        "E0003"
      ]
    }
  ]
}
```

## 相关文件

- pull value reports: `out_zzz\current_pull_value_report.md` / `out_zzz\next_pull_value_report.md`
- current coverage: `out_zzz\current_box_team_coverage.md`
- target coverage: `out_zzz\target_box_team_coverage.md`
- team signature aggregates: `out_zzz\team_signature_aggregates.csv`
