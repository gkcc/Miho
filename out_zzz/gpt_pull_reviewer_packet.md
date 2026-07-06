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
- 输出每个角色的建议档位、理由、反证、需要等待的数据，以及是否建议立刻抽。

## 建议提问

请读取这个 packet，按长期 auto 高难奖励目标，评审每个候选角色应该抽到 X+X。输出：结论表、每人证据链、风险、需要等的数据。

## Evidence Payload

```json
{
  "summary": {
    "generated_at": "2026-07-06T23:11:27",
    "data_dir": "out_zzz",
    "box_path": ".miho\\zzz_box_state.json",
    "plan_path": "configs\\zzz_banner_plan.json",
    "candidate_count": 2,
    "planned_slugs": [
      "nom",
      "sunna"
    ],
    "current_coverage_records": 7,
    "target_coverage_records": 14,
    "mechanism_notes_dir": "configs\\zzz_mechanism_notes"
  },
  "candidates": [
    {
      "slug": "sunna",
      "name_cn": "千夏",
      "candidate_type": "rerun",
      "status": "next",
      "local_rule_pull_value": "高",
      "stage_recommendation": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0；若专武实测显著提升泛用辅助价值，可上调到 0+1。",
        "not_recommended_stage": "1+1、2+1 或更高暂不建议作为目标。",
        "reason": "historical_usage 很强，但 target_coverage 在当前 Box 只给弱覆盖；mechanism_review 支持先拿本体，不支持高档位。",
        "missing_data": "专武对比、影画断点实测、当前 Box 主队绑定度、下版本环境是否继续抬物理/支援。"
      },
      "history_summary": "sd: points 8 / latest 53.72% / avg_last3 53.947% / trend 24.53；da: points 8 / latest 46.41% / avg_last3 52.06% / trend 4.45",
      "global_usage_summary": "best_latest=53.72%；best_avg_last3=53.947%；worst_trend=4.45",
      "team_coverage_summary": "current 0(0)；target 7(B- 6 / C 1)；新增依赖 7(B- 6 / C 1)",
      "mechanism_review_summary": "0+0=0+0 已具备复刻辅助的核心功能，历史全局出场和 T0 定位足以支持先拿本体。；0+1=0+1 属于可选增强，需要确认专武相对通用音擎的收益；当前历史数据不能单独证明专武必需。；1+0=1+0 若提供关键循环、覆盖率或易用性改善可考虑，但不应优先于本体覆盖和队伍成型。；1+1=1+1 只在本体和专武实测收益都明确、且长期绑定主队时考虑。；2+1=2+1 不是长期 auto 高难奖励必需，除非后续机制证明确有质变。",
      "mechanism_summary": "物理 / 支援 / 辅助；复刻辅助重点看泛用性、队友覆盖面，以及是否能补你 Box 的主C缺口。；archetype=物理辅助、泛用支援、主C增益拼图；关键队友=ye-shunguang、zhao、miyabi、lucy",
      "replacement_risk": "target coverage 新增队伍多为 B-/C，不能单靠 box 覆盖定性；高档位收益需要专武/影画实测。",
      "decision_basis": [
        "T 榜最好评级 T0 / rating 11",
        "历史出场点 16，近三期最高均值 53.947%",
        "目标 Box 新增依赖队伍 7 条，其中 A/B+ 0 条、A/B+/B 0 条",
        "mechanism_review：0+0=0+0 已具备复刻辅助的核心功能，历史全局出场和 T0 定位足以支持先拿本体。；0+1=0+1 属于可选增强，需要确认专武相对通用音擎的收益；当前历史数据不能单独证明专武必需。；1+0=1+0 若提供关键循环、覆盖率或易用性改善可考虑，但不应优先于本体覆盖和队伍成型。；1+1=1+1 只在本体和专武实测收益都明确、且长期绑定主队时考虑。；2+1=2+1 不是长期 auto 高难奖励必需，除非后续机制证明确有质变。"
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
      "stage_recommendation": {
        "recommended_stage": "等技能/影画/专武/首轮数据",
        "acceptable_stage": "暂不预设；若机制与 Box 拼图高度吻合，首轮数据后再评估 0+0 / 0+1。",
        "not_recommended_stage": "1+1、2+1 或更高在资料不足阶段不建议规划。",
        "reason": "新角色没有历史队伍记录是未实测状态，不是负面；机制资料不足，不能根据 coverage=0 下结论。",
        "missing_data": "正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系。"
      },
      "history_summary": "暂无历史出场；若为新角色，这是未实测状态，不作为负面",
      "global_usage_summary": "best_latest=0%；best_avg_last3=0%；worst_trend=0",
      "team_coverage_summary": "current 0(0)；target 0(0)；新增依赖 0(0)",
      "mechanism_review_summary": "0+0=未知；等待正式技能与首轮实战。；0+1=未知；等待专武数值、触发条件和替代音擎对比。；1+0=未知；等待影画文本和实战收益。；1+1=未知；等待本体、专武、影画组合收益。；2+1=未知；新角色实测前不能预设高档位必要性。",
      "mechanism_summary": "未知 / 未知 / 未知；新角色在实测前只做关系识别：属性、特性、核心队友、是否替代已有主推体系。；archetype=未知",
      "replacement_risk": "目前缺少机制和队伍实测；任何 X+X 结论都应等待数据。",
      "decision_basis": [
        "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
        "未知 / 未知 / 未知；新角色在实测前只做关系识别：属性、特性、核心队友、是否替代已有主推体系。；archetype=未知",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系。",
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
