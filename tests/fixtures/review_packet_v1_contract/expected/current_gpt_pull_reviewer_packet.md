# GPT Pull Reviewer Packet

## 使用方式

把本文件交给 Codex/GPT，要求它基于证据重新评审每个候选角色的 X+X 档位。
这是无 API key 的交互版：本地负责自动更新数据和证据包，GPT 评判由你登录后发起。

## 评审规则

- 不要只按 target coverage 定性；复刻角色必须同时看历史走势、全局出场、T 榜定位、current/target 覆盖和 X+X 必要性。
- 必须把 historical_usage、target_coverage、mechanism_review 三类证据分开列出，再综合判断。
- 新角色观测状态必须由全局 usage 与完整真实队伍记录共同判断，不能依赖目标 Box 是否可组。
- 新角色观测按 snapshot 去重；同一 snapshot 的 SD/DA 只算一次。first_cycle 表示首轮已到但仍需跨期复测，不能自动升级抽取结论或推荐档位。
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
    "candidate_count": 4,
    "planned_slugs": [
      "alpha",
      "beta",
      "gamma",
      "nova",
      "low-a"
    ],
    "reviewed_slugs": [
      "alpha",
      "beta",
      "gamma",
      "nova"
    ],
    "filtered_low_rarity_slugs": [
      "low-a"
    ],
    "current_coverage_records": 0,
    "target_coverage_records": 3,
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
      "slug": "alpha",
      "name_cn": "阿尔法候选名",
      "candidate_type": "rerun",
      "status": "current",
      "local_rule_pull_value": "高",
      "stage_recommendation": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "high",
        "not_recommended_stage": "2+1 以上缺少收益证据",
        "reason": "危险文本 </script> | Markdown pipe\n第二行仍在 JSON 字符串内",
        "missing_data": "1+1 与 2+1 的长线收益"
      },
      "prior_final_stage": "1+1",
      "prior_decision_status": "locked",
      "prior_confidence": "high",
      "prior_reason": "冻结基线保留 1+1",
      "local_rule_stage": "0+0",
      "recommended_stage_for_review": "1+1",
      "final_stage": "1+1",
      "stage_delta": "0+0 -> 1+1",
      "delta_requires_review": true,
      "delta_reason": "本地规则与既有 baseline 不同；未登记新增证据，本地规则不能覆盖既有 GPT/人工定档。",
      "change_allowed_reason": "only_with_new_evidence",
      "new_evidence_categories": [],
      "history_summary": "sd: points 7 / latest 48% / avg_last3 46% / trend 12",
      "global_usage_summary": "best_latest=48%；best_avg_last3=46%；worst_trend=12",
      "team_coverage_summary": "current 0(0)；target 1(A 1)；新增依赖 1(A 1)",
      "mechanism_review_summary": "source_quality=identity=official；breakpoints=reviewed；stage_confidence=high；0+0(value_type=本体完整度; evidence=机制笔记显式支持 | 不应破坏 packet; missing_data=无)",
      "mechanism_notes": {
        "identity": {
          "role_group_cn": "机制笔记定位",
          "element_cn": "机制笔记元素",
          "style_cn": "机制笔记特性",
          "rarity": "S"
        },
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0",
        "unresolved_stage": "0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "high",
        "not_recommended_stage": "2+1 以上缺少收益证据",
        "stage_reason": "危险文本 </script> | Markdown pipe\n第二行仍在 JSON 字符串内",
        "missing_data": "1+1 与 2+1 的长线收益",
        "source_quality": {
          "identity": "official",
          "breakpoints": "reviewed"
        },
        "stage_notes": {
          "0+0": {
            "value_type": "本体完整度",
            "evidence": "机制笔记显式支持 | 不应破坏 packet",
            "missing_data": "无"
          }
        },
        "risks_and_counterevidence": [
          "反证 </script> | 保留",
          "跨行风险第一行\n跨行风险第二行"
        ]
      },
      "mechanism_summary": "候选元素 / 候选特性 / 候选定位；候选 focus 优先；稀有度=S",
      "replacement_risk": "反证 </script> | 保留、跨行风险第一行\n跨行风险第二行",
      "decision_basis": [
        "T 榜最好评级 T0 / rating 11",
        "历史出场点 7，近三期最高均值 46%",
        "目标 Box 新增依赖队伍 1 条，其中 A/B+ 1 条、A/B+/B 1 条",
        "mechanism_review：source_quality=identity=official；breakpoints=reviewed；stage_confidence=high；0+0(value_type=本体完整度; evidence=机制笔记显式支持 | 不应破坏 packet; missing_data=无)",
        "同模式判定 sd: 高"
      ],
      "risk_notes": [
        "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性"
      ],
      "evidence_ids": [
        "E-SD-078BE089A7"
      ],
      "risk_evidence_ids": [],
      "evidence_keys": [
        "sd|alpha|anchor-one|support"
      ],
      "risk_evidence_keys": [],
      "evidence_refs": [
        {
          "evidence_id": "E-SD-078BE089A7",
          "evidence_key": "sd|alpha|anchor-one|support",
          "confidence": "A",
          "source_confidence": "A",
          "mode": "sd",
          "team_slugs": [
            "alpha",
            "anchor-one",
            "support"
          ],
          "plan_dependency": [
            "alpha"
          ],
          "phase_versions": [
            "sd:1.0.1",
            "sd:1.0.2",
            "sd:1.0.3",
            "sd:1.0.4"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json",
            "boss-c_combined.json"
          ],
          "observation_keys": [
            "alpha-p1-a:sd:1.0.1:SD 1.0.1:boss-a_combined.json:-:1",
            "alpha-p1-b:sd:1.0.1:SD 1.0.1:boss-b_combined.json:-:2",
            "alpha-p1-c:sd:1.0.1:SD 1.0.1:boss-c_combined.json:-:3",
            "alpha-p2-a:sd:1.0.2:SD 1.0.2:boss-a_combined.json:-:1",
            "alpha-p2-b:sd:1.0.2:SD 1.0.2:boss-b_combined.json:-:2",
            "alpha-p2-c:sd:1.0.2:SD 1.0.2:boss-c_combined.json:-:3",
            "alpha-p3-a:sd:1.0.3:SD 1.0.3:boss-a_combined.json:-:1",
            "alpha-p3-b:sd:1.0.3:SD 1.0.3:boss-b_combined.json:-:2",
            "alpha-p3-c:sd:1.0.3:SD 1.0.3:boss-c_combined.json:-:3",
            "alpha-p4-a:sd:1.0.4:SD 1.0.4:boss-a_combined.json:-:1",
            "alpha-p4-b:sd:1.0.4:SD 1.0.4:boss-b_combined.json:-:2",
            "alpha-p4-c:sd:1.0.4:SD 1.0.4:boss-c_combined.json:-:3"
          ]
        }
      ],
      "risk_evidence_refs": []
    },
    {
      "slug": "beta",
      "name_cn": "贝塔",
      "candidate_type": "rerun",
      "status": "current",
      "local_rule_pull_value": "中高",
      "stage_recommendation": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0 / 0+1",
        "unresolved_stage": "",
        "stage_confidence": "medium",
        "not_recommended_stage": "高档位暂不判断；只在机制/指南/实战证明必要时考虑",
        "reason": "B+ 主证据支持本体，专武待比较",
        "missing_data": "专武对比"
      },
      "prior_final_stage": "0+0",
      "prior_decision_status": "locked",
      "prior_confidence": "medium",
      "prior_reason": "与本地机制档一致",
      "local_rule_stage": "0+0",
      "recommended_stage_for_review": "0+0",
      "final_stage": "0+0",
      "stage_delta": "none",
      "delta_requires_review": false,
      "delta_reason": "本地规则与 baseline 一致；无需 delta review。",
      "change_allowed_reason": "baseline_consistent",
      "new_evidence_categories": [],
      "history_summary": "sd: points 3 / latest 22% / avg_last3 20% / trend 4",
      "global_usage_summary": "best_latest=22%；best_avg_last3=20%；worst_trend=4",
      "team_coverage_summary": "current 0(0)；target 1(B+ 1)；新增依赖 1(B+ 1)",
      "mechanism_review_summary": "stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-",
      "mechanism_notes": {
        "recommended_stage": "0+0",
        "acceptable_stage": "0+0 / 0+1",
        "stage_confidence": "medium",
        "stage_reason": "B+ 主证据支持本体，专武待比较",
        "missing_data": "专武对比"
      },
      "mechanism_summary": "冰 / 异常 / 异常；暂无机制文本",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T0.5 / rating 10",
        "历史出场点 3，近三期最高均值 20%",
        "目标 Box 新增依赖队伍 1 条，其中 A/B+ 1 条、A/B+/B 1 条",
        "mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-",
        "同模式判定 sd: 中高"
      ],
      "risk_notes": [
        "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性"
      ],
      "evidence_ids": [
        "E-SD-A412C67114"
      ],
      "risk_evidence_ids": [],
      "evidence_keys": [
        "sd|anchor-one|beta|support"
      ],
      "risk_evidence_keys": [],
      "evidence_refs": [
        {
          "evidence_id": "E-SD-A412C67114",
          "evidence_key": "sd|anchor-one|beta|support",
          "confidence": "B+",
          "source_confidence": "B+",
          "mode": "sd",
          "team_slugs": [
            "anchor-one",
            "beta",
            "support"
          ],
          "plan_dependency": [
            "beta"
          ],
          "phase_versions": [
            "sd:1.0.2",
            "sd:1.0.3",
            "sd:1.0.4"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "beta-p1-a:sd:1.0.2:SD 1.0.2:boss-a_combined.json:-:4",
            "beta-p1-b:sd:1.0.2:SD 1.0.2:boss-b_combined.json:-:5",
            "beta-p2-a:sd:1.0.3:SD 1.0.3:boss-a_combined.json:-:4",
            "beta-p2-b:sd:1.0.3:SD 1.0.3:boss-b_combined.json:-:5",
            "beta-p3-a:sd:1.0.4:SD 1.0.4:boss-a_combined.json:-:4",
            "beta-p3-b:sd:1.0.4:SD 1.0.4:boss-b_combined.json:-:5"
          ]
        }
      ],
      "risk_evidence_refs": []
    },
    {
      "slug": "gamma",
      "name_cn": "伽马",
      "candidate_type": "rerun",
      "status": "current",
      "local_rule_pull_value": "中",
      "stage_recommendation": {
        "recommended_stage": "等机制档位评审",
        "acceptable_stage": "暂不预设",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断",
        "reason": "已有历史 usage/队伍证据，但缺少 mechanism_notes，不能据此推导 X+X 档位",
        "missing_data": "mechanism_notes、专武与影画断点、攻略共识、当前版本档位收益对比"
      },
      "prior_final_stage": "",
      "prior_decision_status": "",
      "prior_confidence": "",
      "prior_reason": "",
      "local_rule_stage": "等机制档位评审",
      "recommended_stage_for_review": "等机制档位评审",
      "final_stage": "等机制档位评审",
      "stage_delta": "none",
      "delta_requires_review": false,
      "delta_reason": "无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。",
      "change_allowed_reason": "no_prior_baseline",
      "new_evidence_categories": [],
      "history_summary": "sd: points 3 / latest 22% / avg_last3 20% / trend 4",
      "global_usage_summary": "best_latest=22%；best_avg_last3=20%；worst_trend=4",
      "team_coverage_summary": "current 0(0)；target 1(B 1)；新增依赖 1(B 1)",
      "mechanism_review_summary": "暂无 mechanism_notes；已有历史实战仅支持本体价值，X+X 档位等待机制评审",
      "mechanism_notes": {},
      "mechanism_summary": "电 / 强攻 / 强攻；暂无机制文本",
      "replacement_risk": "主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面",
      "decision_basis": [
        "T 榜最好评级 T0.5 / rating 10",
        "历史出场点 3，近三期最高均值 20%",
        "目标 Box 新增依赖队伍 1 条，其中 A/B+ 0 条、A/B+/B 1 条",
        "mechanism_review：暂无 mechanism_notes；已有历史实战仅支持本体价值，X+X 档位等待机制评审",
        "同模式判定 sd: 中"
      ],
      "risk_notes": [
        "同 mode 主证据仅支持中优先级",
        "新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性"
      ],
      "evidence_ids": [
        "E-SD-FCD5C791C5"
      ],
      "risk_evidence_ids": [],
      "evidence_keys": [
        "sd|anchor-one|gamma|support"
      ],
      "risk_evidence_keys": [],
      "evidence_refs": [
        {
          "evidence_id": "E-SD-FCD5C791C5",
          "evidence_key": "sd|anchor-one|gamma|support",
          "confidence": "B",
          "source_confidence": "B",
          "mode": "sd",
          "team_slugs": [
            "anchor-one",
            "gamma",
            "support"
          ],
          "plan_dependency": [
            "gamma"
          ],
          "phase_versions": [
            "sd:1.0.3",
            "sd:1.0.4"
          ],
          "scopes": [
            "boss-a_combined.json",
            "boss-b_combined.json"
          ],
          "observation_keys": [
            "gamma-p1-a:sd:1.0.3:SD 1.0.3:boss-a_combined.json:-:6",
            "gamma-p2-a:sd:1.0.4:SD 1.0.4:boss-a_combined.json:-:6",
            "gamma-p2-b:sd:1.0.4:SD 1.0.4:boss-b_combined.json:-:7"
          ]
        }
      ],
      "risk_evidence_refs": []
    },
    {
      "slug": "nova",
      "name_cn": "新星",
      "candidate_type": "new",
      "status": "current",
      "local_rule_pull_value": "等实测",
      "stage_recommendation": {
        "recommended_stage": "等实测",
        "acceptable_stage": "暂不预设",
        "unresolved_stage": "0+0 / 0+1 / 1+0 / 1+1 / 2+1",
        "stage_confidence": "low",
        "not_recommended_stage": "暂不判断",
        "reason": "首轮实测已到，但当前仅 1 个 snapshot 的单期/B- 证据，不能据此预设 X+X 档位",
        "missing_data": "技能机制、影画、专武、跨期高难复测"
      },
      "prior_final_stage": "0+1",
      "prior_decision_status": "soft_locked",
      "prior_confidence": "low",
      "prior_reason": "新角色首轮单快照 B- 证据仅作 delta 审核反例",
      "local_rule_stage": "等实测",
      "recommended_stage_for_review": "0+1",
      "final_stage": "0+1",
      "stage_delta": "等实测 -> 0+1",
      "delta_requires_review": true,
      "delta_reason": "本地规则与既有 baseline 不同；未登记新增证据，本地规则不能覆盖既有 GPT/人工定档。",
      "change_allowed_reason": "wait_for_repeated_data",
      "new_evidence_categories": [],
      "history_summary": "暂无全局 usage 出场点；完整真实队伍表已有首轮实测（1 snapshot）",
      "global_usage_summary": "best_latest=0%；best_avg_last3=0%；worst_trend=0",
      "team_coverage_summary": "current 0(0)；target 0(0)；新增依赖 0(0)",
      "mechanism_review_summary": "暂无 mechanism_notes；首轮已到，等待机制资料与跨期复测",
      "mechanism_notes": {},
      "mechanism_summary": "未知属性 / 未知特性 / 未知定位；暂无机制文本",
      "replacement_risk": "机制未知，替代风险无法判定",
      "decision_basis": [
        "新角色首轮实测已到：1 个 snapshot，当前仅单期/B- 证据；等待跨期复测，不自动提升推荐档位",
        "未知属性 / 未知特性 / 未知定位；暂无机制文本",
        "先验证是否补当前 Box 拼图，还是要求后续售后队友"
      ],
      "risk_notes": [
        "首轮数据不能替代跨期稳定性验证；SD/DA 同 snapshot 只计一次",
        "首轮已到，仍需跨期 SD/DA 复测和机制资料"
      ],
      "evidence_ids": [],
      "risk_evidence_ids": [],
      "evidence_keys": [],
      "risk_evidence_keys": [],
      "evidence_refs": [],
      "risk_evidence_refs": []
    }
  ]
}
```

## 相关文件

- pull value reports: `<ROOT>\input\data\current_pull_value_report.md` / `<ROOT>\input\data\next_pull_value_report.md`
- current coverage: `<ROOT>\input\data\current_box_team_coverage.md`
- target coverage: `<ROOT>\input\data\target_box_team_coverage.md`
- team signature aggregates: `<ROOT>\input\data\team_signature_aggregates.csv`
