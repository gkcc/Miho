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
    "generated_at": "2026-07-06T23:39:23",
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
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "medium",
        "not_recommended_stage": "未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据",
        "reason": "historical_usage 与 T0 定位支持本体价值；但纵向档位不能只靠历史队伍和覆盖推断。",
        "missing_data": "专武对比、1 影与 2 影文本、影画收益量化、0+1/1+0/1+1 的边际收益、是否绑定特定辅助、当前 Box 同定位主C替代关系。"
      },
      "history_summary": "sd: points 9 / latest 78.29% / avg_last3 77.59% / trend 0；da: points 9 / latest 62.83% / avg_last3 67.693% / trend -14.14",
      "global_usage_summary": "best_latest=78.29%；best_avg_last3=77.59%；worst_trend=-14.14",
      "team_coverage_summary": "current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)",
      "mechanism_review_summary": "source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=本地 Prydwen tier/usage 显示叶瞬光为 SD/DA T0，近半年多期高出场。; missing_data=当前版本指南是否仍推荐 0+0 作为长期 auto 奖励投入线。)；0+1(value_type=专武价值; evidence=主C专武通常可能影响输出阈值，但当前 notes 没有稳定断点证据。; missing_data=专武数值、通用音擎替代、伤害/循环/阈值对比。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否优先于补其他角色。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、与低档位的边际收益差。)",
      "mechanism_notes": {
        "slug": "ye-shunguang",
        "name_cn": "叶瞬光",
        "identity": {
          "element_cn": "物理",
          "style_cn": "强攻",
          "role_group_cn": "直伤主C",
          "rarity": "S"
        },
        "mechanism_status": "复刻物理强攻主C；历史 SD/DA usage 和 tier 证据充分，但专武、影画和高档位断点仍需机制/指南证据。",
        "source_quality": {
          "identity": "official_or_exported",
          "historical_usage": "high",
          "target_coverage": "medium",
          "guide_consensus": "pending",
          "skill_text": "pending",
          "cinema_signature_breakpoints": "pending"
        },
        "stage_confidence": "medium",
        "body_completeness_0_0": "0+0 的历史 usage 和 T0 定位足以证明角色本体强度与长期存在感。",
        "signature_value_0_1": "0+1 可能是主C纵向补强；缺专武相对通用音擎的收益、循环和阈值数据。",
        "cinema_value_1_0": "1+0 可能是输出或手感断点；缺影画文本、收益量化和 auto 稳定性证据。",
        "combo_value_1_1": "1+1 需确认专武与 1 影是否互相放大，且是否优先于补其他体系本体。",
        "necessity_2_1": "2+1 未判定；当前资料不能证明长期 auto 高难奖励必需。",
        "higher_stage_note": "未判定：2+1 以上缺少机制、指南和实战数据证明长期高难 auto 必要。",
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "0+1 / 1+0 / 1+1 / 2+1",
        "not_recommended_stage": "未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据",
        "stage_reason": "historical_usage 与 T0 定位支持本体价值；但纵向档位不能只靠历史队伍和覆盖推断。",
        "missing_data": "专武对比、1 影与 2 影文本、影画收益量化、0+1/1+0/1+1 的边际收益、是否绑定特定辅助、当前 Box 同定位主C替代关系。",
        "stage_notes": {
          "0+0": {
            "value_type": "本体完整度",
            "evidence": "本地 Prydwen tier/usage 显示叶瞬光为 SD/DA T0，近半年多期高出场。",
            "missing_data": "当前版本指南是否仍推荐 0+0 作为长期 auto 奖励投入线。"
          },
          "0+1": {
            "value_type": "专武价值",
            "evidence": "主C专武通常可能影响输出阈值，但当前 notes 没有稳定断点证据。",
            "missing_data": "专武数值、通用音擎替代、伤害/循环/阈值对比。"
          },
          "1+0": {
            "value_type": "影画断点",
            "evidence": "暂无可确认断点。",
            "missing_data": "1 影文本、收益量化、是否改善 auto 稳定性。"
          },
          "1+1": {
            "value_type": "本体+专武+影画组合",
            "evidence": "暂无组合收益证据。",
            "missing_data": "0+1 与 1+0 是否互相放大、是否优先于补其他角色。"
          },
          "2+1": {
            "value_type": "高档位必要性",
            "evidence": "当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。",
            "missing_data": "2 影文本、2+1 实战质变、指南共识、与低档位的边际收益差。"
          }
        },
        "key_teammates": [
          "sunna",
          "zhao",
          "lucy"
        ],
        "archetypes": [
          "物理强攻",
          "直伤主C",
          "高历史出场主C"
        ],
        "risks_and_counterevidence": "主C纵向投入容易和新体系本体竞争；高档位保持未判定，缺资料只能记为缺证据。",
        "source_url": "https://www.prydwen.gg/zenless/tier-list",
        "source_summary": "本地 tier/usage 显示叶瞬光长期 SD/DA 高评级和高出场；X+X 断点仍需专武、影画和攻略证据。"
      },
      "mechanism_summary": "物理 / 强攻 / 直伤主C；复刻角色应优先看长期趋势、主推队友占用和你 Box 里是否已有同定位主C。；稀有度=S；archetype=物理强攻、直伤主C、高历史出场主C；关键队友=sunna、zhao、lucy",
      "replacement_risk": "主C纵向投入容易和新体系本体竞争；高档位保持未判定，缺资料只能记为缺证据。",
      "decision_basis": [
        "T 榜最好评级 T0 / rating 11",
        "历史出场点 18，近三期最高均值 77.59%",
        "目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖",
        "当前 Box 已有相关队伍 1 条",
        "mechanism_review：source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=本地 Prydwen tier/usage 显示叶瞬光为 SD/DA T0，近半年多期高出场。; missing_data=当前版本指南是否仍推荐 0+0 作为长期 auto 奖励投入线。)；0+1(value_type=专武价值; evidence=主C专武通常可能影响输出阈值，但当前 notes 没有稳定断点证据。; missing_data=专武数值、通用音擎替代、伤害/循环/阈值对比。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否优先于补其他角色。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、与低档位的边际收益差。)"
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
      "history_summary": "sd: points 9 / latest 2.46% / avg_last3 2.797% / trend 0；da: points 9 / latest 3.75% / avg_last3 3.19% / trend 2.08",
      "global_usage_summary": "best_latest=3.75%；best_avg_last3=3.19%；worst_trend=0",
      "team_coverage_summary": "current 2(B- 1 / C 1)；target 2(B- 1 / C 1)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "以太 / 支援 / 辅助；以太支援老角色，更多看你是否缺对应辅助和影画。",
      "replacement_risk": "辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断",
      "decision_basis": [
        "T 榜最好评级 T0.5 / rating 10",
        "历史出场点 18，近三期最高均值 3.19%",
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
      "history_summary": "sd: points 9 / latest 0.32% / avg_last3 0.36% / trend 0；da: points 9 / latest 0.54% / avg_last3 0.567% / trend -0.23",
      "global_usage_summary": "best_latest=0.54%；best_avg_last3=0.567%；worst_trend=-0.23",
      "team_coverage_summary": "current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "物理 / 异常 / 异常主C；陪跑只作为顺带收益，不单独驱动抽卡。",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T1 / rating 9",
        "历史出场点 18，近三期最高均值 0.567%",
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
        "recommended_stage": "等技能/影画/专武/首轮后续数据",
        "acceptable_stage": "暂不预设；若机制与 Box 拼图高度吻合，先评估 0+0。",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据",
        "reason": "维琳娜是当前新 S，已有首轮 usage/tier 但历史窗口短；不能因为 coverage 或首轮单点直接给 X+X 结论。",
        "missing_data": "正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。"
      },
      "history_summary": "sd: points 2 / latest 10.34% / avg_last3 10.34% / trend 0；da: points 2 / latest 48.99% / avg_last3 57.97% / trend -17.96",
      "global_usage_summary": "best_latest=48.99%；best_avg_last3=57.97%；worst_trend=-17.96",
      "team_coverage_summary": "current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)",
      "mechanism_review_summary": "source_quality=identity=official_or_exported；historical_usage=first_cycle_only；target_coverage=low；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=low；0+0(value_type=本体完整度; evidence=本地数据已有 3.0.1 首轮 SD/DA usage 和 Prydwen T0.5 记录。; missing_data=后续期数复测、队伍稳定性、当前 Box 可组核心队。)；0+1(value_type=专武价值; evidence=暂无可确认断点。; missing_data=专武数值、通用音擎替代、异常积蓄/伤害/循环收益。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否绑定特定异常队友。)；2+1(value_type=高档位必要性; evidence=暂无资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、长期环境。)",
      "mechanism_notes": {
        "slug": "velina",
        "name_cn": "维琳娜·艾嘉德",
        "identity": {
          "element_cn": "风",
          "style_cn": "异常",
          "role_group_cn": "异常主C",
          "rarity": "S"
        },
        "mechanism_status": "当前新 S 风属性异常主C；已有首轮 tier/usage，但技能、专武、影画和长期环境仍需更多实战验证。",
        "source_quality": {
          "identity": "official_or_exported",
          "historical_usage": "first_cycle_only",
          "target_coverage": "low",
          "guide_consensus": "pending",
          "skill_text": "pending",
          "cinema_signature_breakpoints": "pending"
        },
        "stage_confidence": "low",
        "body_completeness_0_0": "0+0 本体完整度未判定；已有首轮 SD/DA 记录，但新角色长期表现仍需后续期数验证。",
        "signature_value_0_1": "0+1 未判定；缺专武相对通用音擎和异常体系队友的收益对比。",
        "cinema_value_1_0": "1+0 未判定；缺影画文本、伤害/异常积蓄收益和 auto 稳定性证据。",
        "combo_value_1_1": "1+1 未判定；缺本体、专武、影画组合收益。",
        "necessity_2_1": "2+1 未判定；新角色首轮资料不足，不能预设高档位必要性。",
        "higher_stage_note": "未判定：高档位缺机制、指南、首轮后续复测和长期环境证据。",
        "recommended_stage": "等技能/影画/专武/首轮后续数据",
        "acceptable_stage": "暂不预设；若机制与 Box 拼图高度吻合，先评估 0+0。",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "not_recommended_stage": "未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据",
        "stage_reason": "维琳娜是当前新 S，已有首轮 usage/tier 但历史窗口短；不能因为 coverage 或首轮单点直接给 X+X 结论。",
        "missing_data": "正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。",
        "stage_notes": {
          "0+0": {
            "value_type": "本体完整度",
            "evidence": "本地数据已有 3.0.1 首轮 SD/DA usage 和 Prydwen T0.5 记录。",
            "missing_data": "后续期数复测、队伍稳定性、当前 Box 可组核心队。"
          },
          "0+1": {
            "value_type": "专武价值",
            "evidence": "暂无可确认断点。",
            "missing_data": "专武数值、通用音擎替代、异常积蓄/伤害/循环收益。"
          },
          "1+0": {
            "value_type": "影画断点",
            "evidence": "暂无可确认断点。",
            "missing_data": "1 影文本、收益量化、是否改善 auto 稳定性。"
          },
          "1+1": {
            "value_type": "本体+专武+影画组合",
            "evidence": "暂无组合收益证据。",
            "missing_data": "0+1 与 1+0 是否互相放大、是否绑定特定异常队友。"
          },
          "2+1": {
            "value_type": "高档位必要性",
            "evidence": "暂无资料证明 2+1 是长期 auto 高难奖励必需。",
            "missing_data": "2 影文本、2+1 实战质变、指南共识、长期环境。"
          }
        },
        "key_teammates": [],
        "archetypes": [
          "风异常",
          "异常主C",
          "当前新 S"
        ],
        "risks_and_counterevidence": "新角色首轮数据波动大；高档位保持未判定，缺资料只能记为缺证据。",
        "source_url": "https://www.prydwen.gg/zenless/tier-list",
        "source_summary": "本地 tier/usage 已有维琳娜首轮 SD/DA 记录和 T0.5 定位；X+X 断点仍需正式机制、专武、影画、指南和后续期数数据。"
      },
      "mechanism_summary": "风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；稀有度=S；archetype=风异常、异常主C、当前新 S",
      "replacement_risk": "新角色首轮数据波动大；高档位保持未判定，缺资料只能记为缺证据。",
      "decision_basis": [
        "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
        "风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；稀有度=S；archetype=风异常、异常主C、当前新 S",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。",
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
