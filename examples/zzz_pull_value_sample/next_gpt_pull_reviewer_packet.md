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
        "acceptable_stage": "0+0",
        "unresolved_stage": "0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "medium",
        "not_recommended_stage": "2+1以上仅在机制/指南/实战证明必要时考虑",
        "reason": "historical_usage 很强，支持 0+0 本体价值；target_coverage 在当前 Box 只给弱覆盖，不能单独推高档；专武/影画/2+1 属于待机制与实战确认。",
        "missing_data": "专武对比、1+0 影画文本与实战收益、1+1 组合收益、2+1 是否有长期 auto 质变、当前 Box 主队绑定度、下版本环境是否继续抬物理/支援。"
      },
      "history_summary": "sd: points 8 / latest 53.72% / avg_last3 53.947% / trend 24.53；da: points 8 / latest 46.41% / avg_last3 52.06% / trend 4.45",
      "global_usage_summary": "best_latest=53.72%；best_avg_last3=53.947%；worst_trend=4.45",
      "team_coverage_summary": "current 0(0)；target 7(B- 6 / C 1)；新增依赖 7(B- 6 / C 1)",
      "mechanism_review_summary": "source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=历史 usage 与 tier 数据支持复刻辅助本体价值；本地 target coverage 只作为辅助证据。; missing_data=需要确认当前版本实战指南是否仍认定 0+0 即可承担核心辅助功能。)；0+1(value_type=专武价值; evidence=目前只可判断为潜在增强，不能从历史队伍记录直接推断必需。; missing_data=专武数值、触发条件、覆盖率、循环改善、相对通用音擎收益。)；1+0(value_type=影画断点; evidence=可能改善循环或覆盖面，但当前 notes 未取得稳定攻略共识。; missing_data=1 影文本、收益量化、是否改变 auto 手感或队伍阈值。)；1+1(value_type=本体+专武+影画组合; evidence=组合收益需建立在 0+1 和 1+0 均明确有价值的前提上。; missing_data=专武与 1 影是否互相放大、是否绑定特定主队、是否优先于其他角色本体。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、和 0+0/0+1/1+0 的边际收益差。)",
      "mechanism_notes": {
        "slug": "sunna",
        "name_cn": "千夏",
        "identity": {
          "element_cn": "物理",
          "style_cn": "支援",
          "role_group_cn": "辅助",
          "rarity": "S"
        },
        "mechanism_status": "复刻辅助；历史表现充足，但专武、影画和高档位断点仍需机制/指南/实战交叉确认。",
        "source_quality": {
          "identity": "official_or_exported",
          "historical_usage": "high",
          "target_coverage": "medium",
          "guide_consensus": "pending",
          "skill_text": "pending",
          "cinema_signature_breakpoints": "pending"
        },
        "stage_confidence": "medium",
        "body_completeness_0_0": "0+0 已具备复刻辅助的核心功能；历史全局出场和 T0 定位支持先拿本体。",
        "signature_value_0_1": "0+1 可能是可选增强；需要专武相对通用音擎的收益、覆盖率和循环改善实测。",
        "cinema_value_1_0": "1+0 可能提供循环、覆盖率或易用性改善；当前资料不足以证明优先级。",
        "combo_value_1_1": "1+1 需要本体、专武、影画组合收益都明确后再判断。",
        "necessity_2_1": "2+1 不能仅因缺少断点数据就判为不推荐；等待机制/指南/实战证明是否有长期 auto 质变。",
        "higher_stage_note": "2+1 以上默认归为竞速/真爱/高预算，除非机制、指南和实战数据证明长期高难 auto 必要。",
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "0+1 / 1+0 / 1+1 / 2+1",
        "not_recommended_stage": "2+1以上仅在机制/指南/实战证明必要时考虑",
        "stage_reason": "historical_usage 很强，支持 0+0 本体价值；target_coverage 在当前 Box 只给弱覆盖，不能单独推高档；专武/影画/2+1 属于待机制与实战确认。",
        "missing_data": "专武对比、1+0 影画文本与实战收益、1+1 组合收益、2+1 是否有长期 auto 质变、当前 Box 主队绑定度、下版本环境是否继续抬物理/支援。",
        "stage_notes": {
          "0+0": {
            "value_type": "本体完整度",
            "evidence": "历史 usage 与 tier 数据支持复刻辅助本体价值；本地 target coverage 只作为辅助证据。",
            "missing_data": "需要确认当前版本实战指南是否仍认定 0+0 即可承担核心辅助功能。"
          },
          "0+1": {
            "value_type": "专武价值",
            "evidence": "目前只可判断为潜在增强，不能从历史队伍记录直接推断必需。",
            "missing_data": "专武数值、触发条件、覆盖率、循环改善、相对通用音擎收益。"
          },
          "1+0": {
            "value_type": "影画断点",
            "evidence": "可能改善循环或覆盖面，但当前 notes 未取得稳定攻略共识。",
            "missing_data": "1 影文本、收益量化、是否改变 auto 手感或队伍阈值。"
          },
          "1+1": {
            "value_type": "本体+专武+影画组合",
            "evidence": "组合收益需建立在 0+1 和 1+0 均明确有价值的前提上。",
            "missing_data": "专武与 1 影是否互相放大、是否绑定特定主队、是否优先于其他角色本体。"
          },
          "2+1": {
            "value_type": "高档位必要性",
            "evidence": "当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。",
            "missing_data": "2 影文本、2+1 实战质变、指南共识、和 0+0/0+1/1+0 的边际收益差。"
          }
        },
        "key_teammates": [
          "ye-shunguang",
          "zhao",
          "miyabi",
          "lucy"
        ],
        "archetypes": [
          "物理辅助",
          "泛用支援",
          "主C增益拼图"
        ],
        "risks_and_counterevidence": "target coverage 新增队伍多为 B-/C，不能单靠 box 覆盖定性；高档位不能因“缺少资料”直接判死刑，应保持 unresolved。",
        "source_url": "https://www.prydwen.gg/zenless/tier-list",
        "source_summary": "本地 Prydwen tier/usage 数据显示 sunna 为 SD/DA 高评级且历史全局出场率稳定；机制断点仍需专武、影画、攻略和首轮实战补证。"
      },
      "mechanism_summary": "物理 / 支援 / 辅助；复刻辅助重点看泛用性、队友覆盖面，以及是否能补你 Box 的主C缺口。；稀有度=S；archetype=物理辅助、泛用支援、主C增益拼图；关键队友=ye-shunguang、zhao、miyabi、lucy",
      "replacement_risk": "target coverage 新增队伍多为 B-/C，不能单靠 box 覆盖定性；高档位不能因“缺少资料”直接判死刑，应保持 unresolved。",
      "decision_basis": [
        "T 榜最好评级 T0 / rating 11",
        "历史出场点 16，近三期最高均值 53.947%",
        "目标 Box 新增依赖队伍 7 条，其中 A/B+ 0 条、A/B+/B 0 条",
        "mechanism_review：source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=历史 usage 与 tier 数据支持复刻辅助本体价值；本地 target coverage 只作为辅助证据。; missing_data=需要确认当前版本实战指南是否仍认定 0+0 即可承担核心辅助功能。)；0+1(value_type=专武价值; evidence=目前只可判断为潜在增强，不能从历史队伍记录直接推断必需。; missing_data=专武数值、触发条件、覆盖率、循环改善、相对通用音擎收益。)；1+0(value_type=影画断点; evidence=可能改善循环或覆盖面，但当前 notes 未取得稳定攻略共识。; missing_data=1 影文本、收益量化、是否改变 auto 手感或队伍阈值。)；1+1(value_type=本体+专武+影画组合; evidence=组合收益需建立在 0+1 和 1+0 均明确有价值的前提上。; missing_data=专武与 1 影是否互相放大、是否绑定特定主队、是否优先于其他角色本体。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、和 0+0/0+1/1+0 的边际收益差。)"
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
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断；资料不足阶段不规划高档位",
        "reason": "新角色没有历史队伍记录是未实测状态，不是负面；目前只确认火、击破、新 S 身份，不能根据 coverage=0 或模板规则下 X+X 结论。",
        "missing_data": "正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。"
      },
      "history_summary": "暂无历史出场；若为新角色，这是未实测状态，不作为负面",
      "global_usage_summary": "best_latest=0%；best_avg_last3=0%；worst_trend=0",
      "team_coverage_summary": "current 0(0)；target 0(0)；新增依赖 0(0)",
      "mechanism_review_summary": "source_quality=identity=official_profile；historical_usage=none_new_character；target_coverage=not_applicable_until_release；guide_consensus=missing；skill_text=missing；cinema_signature_breakpoints=missing；stage_confidence=low；0+0(value_type=本体完整度; evidence=已知身份信息为火属性、击破、新 S；机制未实测。; missing_data=正式技能组、击破定位细节、站场/速切需求、首轮高难表现。)；0+1(value_type=专武价值; evidence=暂无可评估资料。; missing_data=专武数值、触发条件、替代音擎对比、是否改变循环或阈值。)；1+0(value_type=影画断点; evidence=暂无可评估资料。; missing_data=1 影文本、收益类型、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无可评估资料。; missing_data=0+1 与 1+0 是否互相放大、是否依赖特定队友。)；2+1(value_type=高档位必要性; evidence=暂无可评估资料。; missing_data=2 影文本、2+1 是否有长期 auto 必要性、指南与实战共识。)",
      "mechanism_notes": {
        "slug": "nom",
        "name_cn": "诺姆·霍洛维尔",
        "identity": {
          "element_cn": "火",
          "style_cn": "击破",
          "role_group_cn": "击破",
          "rarity": "S"
        },
        "mechanism_status": "新 S 火属性击破；机制未实测，技能、专武、影画和首轮高难队伍记录等待正式数据。",
        "source_quality": {
          "identity": "official_profile",
          "historical_usage": "none_new_character",
          "target_coverage": "not_applicable_until_release",
          "guide_consensus": "missing",
          "skill_text": "missing",
          "cinema_signature_breakpoints": "missing"
        },
        "stage_confidence": "low",
        "body_completeness_0_0": "已知身份为火 / 击破 / 新 S；本体机制完整度等待正式技能与首轮实战。",
        "signature_value_0_1": "未知；等待专武数值、触发条件和替代音擎对比。",
        "cinema_value_1_0": "未知；等待影画文本和实战收益。",
        "combo_value_1_1": "未知；等待本体、专武、影画组合收益。",
        "necessity_2_1": "未知；新角色实测前不能预设高档位必要性。",
        "higher_stage_note": "高档位不预设；只在正式机制、指南和高难数据证明长期收益时再考虑。",
        "recommended_stage": "等技能/影画/专武/首轮数据",
        "acceptable_stage": "暂不预设；若机制与 Box 拼图高度吻合，首轮数据后再评估 0+0 / 0+1。",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "not_recommended_stage": "暂不判断；资料不足阶段不规划高档位",
        "stage_reason": "新角色没有历史队伍记录是未实测状态，不是负面；目前只确认火、击破、新 S 身份，不能根据 coverage=0 或模板规则下 X+X 结论。",
        "missing_data": "正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。",
        "stage_notes": {
          "0+0": {
            "value_type": "本体完整度",
            "evidence": "已知身份信息为火属性、击破、新 S；机制未实测。",
            "missing_data": "正式技能组、击破定位细节、站场/速切需求、首轮高难表现。"
          },
          "0+1": {
            "value_type": "专武价值",
            "evidence": "暂无可评估资料。",
            "missing_data": "专武数值、触发条件、替代音擎对比、是否改变循环或阈值。"
          },
          "1+0": {
            "value_type": "影画断点",
            "evidence": "暂无可评估资料。",
            "missing_data": "1 影文本、收益类型、是否改善 auto 稳定性。"
          },
          "1+1": {
            "value_type": "本体+专武+影画组合",
            "evidence": "暂无可评估资料。",
            "missing_data": "0+1 与 1+0 是否互相放大、是否依赖特定队友。"
          },
          "2+1": {
            "value_type": "高档位必要性",
            "evidence": "暂无可评估资料。",
            "missing_data": "2 影文本、2+1 是否有长期 auto 必要性、指南与实战共识。"
          }
        },
        "key_teammates": [],
        "archetypes": [
          "火击破",
          "新 S",
          "机制未实测"
        ],
        "risks_and_counterevidence": "目前只能确认身份信息；任何 X+X 结论都应等待正式技能、专武、影画和首轮数据。",
        "source_url": "https://www.miyoushe.com/zzz/article/75009674",
        "source_summary": "官方代理人档案足以确认角色身份和卡池计划，但不足以评估抽取档位；X+X 暂停在资料等待状态。"
      },
      "mechanism_summary": "火 / 击破 / 击破；新 S 火属性击破；技能、专武、影画和首轮高难数据未落地，先只做关系识别。；稀有度=S；archetype=火击破、新 S、机制未实测",
      "replacement_risk": "目前只能确认身份信息；任何 X+X 结论都应等待正式技能、专武、影画和首轮数据。",
      "decision_basis": [
        "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
        "火 / 击破 / 击破；新 S 火属性击破；技能、专武、影画和首轮高难数据未落地，先只做关系识别。；稀有度=S；archetype=火击破、新 S、机制未实测",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。",
        "替代风险无法从当前历史数据判断"
      ],
      "evidence_ids": []
    }
  ]
}
```

## 相关文件

- pull value reports: `out_zzz\current_pull_value_report.md` / `out_zzz\next_pull_value_report.md`
- current coverage: `out_zzz\current_box_team_coverage.md`
- target coverage: `out_zzz\target_box_team_coverage.md`
- team signature aggregates: `out_zzz\team_signature_aggregates.csv`
