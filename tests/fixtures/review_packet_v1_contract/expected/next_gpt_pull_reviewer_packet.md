# GPT Pull Reviewer Packet

## 使用方式

把本文件交给 Codex/GPT，要求它基于证据重新评审每个候选角色的 X+X 档位。
这是无 API key 的交互版：本地负责自动更新数据和证据包，GPT 评判由你登录后发起。

## 评审规则

- 不要只按 target coverage 定性；复刻角色必须同时看历史走势、全局出场、T 榜定位、current/target 覆盖和 X+X 必要性。
- 必须把 historical_usage、target_coverage、mechanism_review 三类证据分开列出，再综合判断。
- 新角色没有历史队伍记录只能标记为未实测，不能作为负面扣分。
- A 级 / 四星角色默认不作为独立抽取价值候选；它们只作为队友、陪跑顺带收益或 coverage 证据。
- 如果 Evidence Payload 含 prior_final_stage / final_stage，最终档位先沿用 baseline；local_rule_stage 只能触发 delta review，不能直接覆盖既有结论。
- C 档或 theoretical-only 不能作为抽取/档位主依据。
- sentinel 分数不能当真实表现。
- 输出每个角色的 recommended_stage、unresolved_stage、stage_confidence、not_recommended_stage、理由、反证、需要等待的数据，以及是否建议立刻抽。

## 建议提问

请读取这个 packet，按长期 auto 高难奖励目标，评审每个候选角色应该抽到 X+X。输出：结论表、每人证据链、风险、需要等的数据。

## Evidence Payload

```json
{
  "summary": {
    "method_version": "evidence-first-v1-20260712",
    "generated_at": "2026-07-13T09:10:11",
    "data_dir": "<ROOT>\\input\\data",
    "box_path": "<ROOT>\\input\\box.json",
    "plan_path": "<ROOT>\\input\\plan.json",
    "candidate_count": 3,
    "planned_slugs": [
      "delta",
      "epsilon",
      "zeta"
    ],
    "reviewed_slugs": [
      "delta",
      "epsilon",
      "zeta"
    ],
    "filtered_low_rarity_slugs": [],
    "current_coverage_records": 0,
    "target_coverage_records": 4,
    "mechanism_notes_dir": "<ROOT>\\input\\mechanism_notes",
    "decision_baseline_path": "<ROOT>\\input\\baseline.json",
    "decision_baseline_slugs": [
      "alpha",
      "beta",
      "nova"
    ],
    "new_evidence_categories": [
      "新一期 SD/DA 出场率显著变化",
      "新队伍 coverage 从 B-/C 提升到 A/B+",
      "专武/影画机制 notes 更新",
      "主流指南共识变化",
      "当前 Box 变化",
      "用户目标或预算变化"
    ]
  },
  "candidates": [
    {
      "slug": "delta",
      "name_cn": "德尔塔",
      "candidate_type": "rerun",
      "status": "next",
      "local_rule_pull_value": "中高",
      "stage_recommendation": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "",
        "stage_confidence": "medium",
        "not_recommended_stage": "高档位暂不判断；只在机制/指南/实战证明必要时考虑",
        "reason": "两条独立 B 只支持本体优先级",
        "missing_data": "高档位收益"
      },
      "prior_final_stage": "",
      "prior_decision_status": "",
      "prior_confidence": "",
      "prior_reason": "",
      "local_rule_stage": "0+0",
      "recommended_stage_for_review": "0+0",
      "final_stage": "0+0",
      "stage_delta": "none",
      "delta_requires_review": false,
      "delta_reason": "无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。",
      "change_allowed_reason": "no_prior_baseline",
      "new_evidence_categories": [],
      "history_summary": "sd: points 3 / latest 22% / avg_last3 20% / trend 4",
      "global_usage_summary": "best_latest=22%；best_avg_last3=20%；worst_trend=4",
      "team_coverage_summary": "current 0(0)；target 2(B 2)；新增依赖 2(B 2)",
      "mechanism_review_summary": "stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-",
      "mechanism_notes": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "stage_confidence": "medium",
        "stage_reason": "两条独立 B 只支持本体优先级",
        "missing_data": "高档位收益"
      },
      "mechanism_summary": "以太 / 强攻 / 强攻；暂无机制文本",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T0.5 / rating 10",
        "历史出场点 3，近三期最高均值 20%",
        "目标 Box 新增依赖队伍 2 条，其中 A/B+ 0 条、A/B+/B 2 条",
        "mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-",
        "同模式判定 sd: 中高"
      ],
      "risk_notes": [
        "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性"
      ],
      "evidence_ids": [
        "E-SD-49044A37B0",
        "E-SD-C4150B39C3"
      ],
      "risk_evidence_ids": [],
      "evidence_keys": [
        "sd|anchor-one|delta|support",
        "sd|anchor-two|delta|support"
      ],
      "risk_evidence_keys": [],
      "evidence_refs": [
        {
          "evidence_id": "E-SD-49044A37B0",
          "evidence_key": "sd|anchor-one|delta|support",
          "confidence": "B",
          "source_confidence": "B",
          "mode": "sd",
          "team_slugs": [
            "anchor-one",
            "delta",
            "support"
          ],
          "plan_dependency": [
            "delta"
          ],
          "phase_versions": [
            "sd:2.0.1",
            "sd:2.0.2"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "delta-one-p1-a:sd:2.0.1:SD 2.0.1:boss-a_combined.json:-:1",
            "delta-one-p2-a:sd:2.0.2:SD 2.0.2:boss-a_combined.json:-:1",
            "delta-one-p2-b:sd:2.0.2:SD 2.0.2:boss-b_combined.json:-:2"
          ]
        },
        {
          "evidence_id": "E-SD-C4150B39C3",
          "evidence_key": "sd|anchor-two|delta|support",
          "confidence": "B",
          "source_confidence": "B",
          "mode": "sd",
          "team_slugs": [
            "anchor-two",
            "delta",
            "support"
          ],
          "plan_dependency": [
            "delta"
          ],
          "phase_versions": [
            "sd:2.0.1",
            "sd:2.0.2"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "delta-two-p1-a:sd:2.0.1:SD 2.0.1:boss-a_combined.json:-:3",
            "delta-two-p2-a:sd:2.0.2:SD 2.0.2:boss-a_combined.json:-:3",
            "delta-two-p2-b:sd:2.0.2:SD 2.0.2:boss-b_combined.json:-:4"
          ]
        }
      ],
      "risk_evidence_refs": []
    },
    {
      "slug": "epsilon",
      "name_cn": "伊普西龙",
      "candidate_type": "rerun",
      "status": "next",
      "local_rule_pull_value": "中",
      "stage_recommendation": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "",
        "stage_confidence": "medium",
        "not_recommended_stage": "高档位暂不判断；只在机制/指南/实战证明必要时考虑",
        "reason": "单候选主证据可支持本体",
        "missing_data": "与 zeta 捆绑的多候选队伍不能当单抽主证据"
      },
      "prior_final_stage": "",
      "prior_decision_status": "",
      "prior_confidence": "",
      "prior_reason": "",
      "local_rule_stage": "0+0",
      "recommended_stage_for_review": "0+0",
      "final_stage": "0+0",
      "stage_delta": "none",
      "delta_requires_review": false,
      "delta_reason": "无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。",
      "change_allowed_reason": "no_prior_baseline",
      "new_evidence_categories": [],
      "history_summary": "sd: points 3 / latest 22% / avg_last3 20% / trend 4",
      "global_usage_summary": "best_latest=22%；best_avg_last3=20%；worst_trend=4",
      "team_coverage_summary": "current 0(0)；target 2(B+ 1 / B 1)；新增依赖 2(B+ 1 / B 1)",
      "mechanism_review_summary": "stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-",
      "mechanism_notes": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "stage_confidence": "medium",
        "stage_reason": "单候选主证据可支持本体",
        "missing_data": "与 zeta 捆绑的多候选队伍不能当单抽主证据"
      },
      "mechanism_summary": "火 / 异常 / 异常；暂无机制文本",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T0.5 / rating 10",
        "历史出场点 3，近三期最高均值 20%",
        "目标 Box 新增依赖队伍 1 条，其中 A/B+ 0 条、A/B+/B 1 条",
        "mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-",
        "同模式判定 sd: 中"
      ],
      "risk_notes": [
        "同 mode 主证据仅支持中优先级",
        "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性",
        "1 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据"
      ],
      "evidence_ids": [
        "E-SD-12A6377412"
      ],
      "risk_evidence_ids": [
        "E-SD-46AB991DE4"
      ],
      "evidence_keys": [
        "sd|anchor-one|epsilon|support"
      ],
      "risk_evidence_keys": [
        "sd|epsilon|support|zeta"
      ],
      "evidence_refs": [
        {
          "evidence_id": "E-SD-12A6377412",
          "evidence_key": "sd|anchor-one|epsilon|support",
          "confidence": "B",
          "source_confidence": "B",
          "mode": "sd",
          "team_slugs": [
            "anchor-one",
            "epsilon",
            "support"
          ],
          "plan_dependency": [
            "epsilon"
          ],
          "phase_versions": [
            "sd:2.0.1",
            "sd:2.0.2"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "epsilon-single-p1-a:sd:2.0.1:SD 2.0.1:boss-a_combined.json:-:5",
            "epsilon-single-p2-a:sd:2.0.2:SD 2.0.2:boss-a_combined.json:-:5",
            "epsilon-single-p2-b:sd:2.0.2:SD 2.0.2:boss-b_combined.json:-:6"
          ]
        }
      ],
      "risk_evidence_refs": [
        {
          "evidence_id": "E-SD-46AB991DE4",
          "evidence_key": "sd|epsilon|support|zeta",
          "confidence": "B+",
          "source_confidence": "B+",
          "mode": "sd",
          "team_slugs": [
            "epsilon",
            "support",
            "zeta"
          ],
          "plan_dependency": [
            "epsilon",
            "zeta"
          ],
          "phase_versions": [
            "sd:2.0.1",
            "sd:2.0.2",
            "sd:2.0.3"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "epsilon-multi-p1-a:sd:2.0.1:SD 2.0.1:boss-a_combined.json:-:7",
            "epsilon-multi-p1-b:sd:2.0.1:SD 2.0.1:boss-b_combined.json:-:8",
            "epsilon-multi-p2-a:sd:2.0.2:SD 2.0.2:boss-a_combined.json:-:7",
            "epsilon-multi-p2-b:sd:2.0.2:SD 2.0.2:boss-b_combined.json:-:8",
            "epsilon-multi-p3-a:sd:2.0.3:SD 2.0.3:boss-a_combined.json:-:7",
            "epsilon-multi-p3-b:sd:2.0.3:SD 2.0.3:boss-b_combined.json:-:8"
          ]
        }
      ]
    },
    {
      "slug": "zeta",
      "name_cn": "泽塔",
      "candidate_type": "new",
      "status": "next",
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
      "prior_final_stage": "",
      "prior_decision_status": "",
      "prior_confidence": "",
      "prior_reason": "",
      "local_rule_stage": "等技能/影画/专武/首轮数据",
      "recommended_stage_for_review": "等技能/影画/专武/首轮数据",
      "final_stage": "等技能/影画/专武/首轮数据",
      "stage_delta": "none",
      "delta_requires_review": false,
      "delta_reason": "无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。",
      "change_allowed_reason": "no_prior_baseline",
      "new_evidence_categories": [],
      "history_summary": "暂无历史出场；若为新角色，这是未实测状态，不作为负面",
      "global_usage_summary": "best_latest=0%；best_avg_last3=0%；worst_trend=0",
      "team_coverage_summary": "current 0(0)；target 1(B+ 1)；新增依赖 1(B+ 1)",
      "mechanism_review_summary": "暂无 mechanism_notes；等技能/影画/专武/首轮数据",
      "mechanism_notes": {},
      "mechanism_summary": "未知属性 / 未知特性 / 未知定位；暂无机制文本",
      "replacement_risk": "机制未知，替代风险无法判定",
      "decision_basis": [
        "新角色没有历史队伍记录属于正常未实测状态，不作为负面",
        "未知属性 / 未知特性 / 未知定位；暂无机制文本",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "等技能/影画/专武/首轮数据",
        "替代风险无法从当前历史数据判断",
        "1 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据"
      ],
      "evidence_ids": [],
      "risk_evidence_ids": [
        "E-SD-46AB991DE4"
      ],
      "evidence_keys": [],
      "risk_evidence_keys": [
        "sd|epsilon|support|zeta"
      ],
      "evidence_refs": [],
      "risk_evidence_refs": [
        {
          "evidence_id": "E-SD-46AB991DE4",
          "evidence_key": "sd|epsilon|support|zeta",
          "confidence": "B+",
          "source_confidence": "B+",
          "mode": "sd",
          "team_slugs": [
            "epsilon",
            "support",
            "zeta"
          ],
          "plan_dependency": [
            "epsilon",
            "zeta"
          ],
          "phase_versions": [
            "sd:2.0.1",
            "sd:2.0.2",
            "sd:2.0.3"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "epsilon-multi-p1-a:sd:2.0.1:SD 2.0.1:boss-a_combined.json:-:7",
            "epsilon-multi-p1-b:sd:2.0.1:SD 2.0.1:boss-b_combined.json:-:8",
            "epsilon-multi-p2-a:sd:2.0.2:SD 2.0.2:boss-a_combined.json:-:7",
            "epsilon-multi-p2-b:sd:2.0.2:SD 2.0.2:boss-b_combined.json:-:8",
            "epsilon-multi-p3-a:sd:2.0.3:SD 2.0.3:boss-a_combined.json:-:7",
            "epsilon-multi-p3-b:sd:2.0.3:SD 2.0.3:boss-b_combined.json:-:8"
          ]
        }
      ]
    }
  ]
}
```

## 相关文件

- pull value reports: `<ROOT>\input\data\current_pull_value_report.md` / `<ROOT>\input\data\next_pull_value_report.md`
- current coverage: `<ROOT>\input\data\current_box_team_coverage.md`
- target coverage: `<ROOT>\input\data\target_box_team_coverage.md`
- team signature aggregates: `<ROOT>\input\data\team_signature_aggregates.csv`
