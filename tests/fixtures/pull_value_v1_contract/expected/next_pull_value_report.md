# 绝区零 Pull Value Report

- 方法版本：evidence-first-v1-20260712
- 生成时间：2026-07-12T13:14:15
- 数据目录：`<ROOT>\input\data`
- Box：`<ROOT>\input\box.json`
- 卡池计划：`<ROOT>\input\plan.json`
- 机制笔记：`<ROOT>\input\mechanism_notes`
- 定档 baseline：`<ROOT>\input\baseline.json`；已有基线：alpha, beta, nova
- 候选角色：3；planned_slugs：delta, epsilon, zeta
- current coverage records：0；target coverage records：4

## 口径

- 复刻角色：按历史走势、全局出场、队伍覆盖、T 榜定位和 X+X 档位必要性评估。
- 新角色：按机制信息完整度、拼图关系、售后确定性和替代风险评估；观测状态由全局 usage 与完整真实队伍记录共同判断，不依赖 Box 是否可组。
- 新角色观测按 snapshot 去重；同一 snapshot 的 SD/DA 只算一次。0 次为 unobserved，1 次为 first_cycle，2 次及以上为 repeated。
- A 级 / 四星角色默认不作为独立抽取价值候选；只作为陪跑顺带收益、队友或 coverage 证据保留。
- target coverage 只说明加入计划角色后的队伍覆盖，不单独决定抽取价值。
- mechanism_review 来自 `configs/zzz_mechanism_notes/*.yaml`，用于判断 0+0、0+1、1+0、1+1、2+1 等档位断点。
- 若存在 decision baseline，最终档位沿用 prior_final_stage；本地规则只作为 delta review 输入，不能在无新增证据时覆盖既有 GPT/人工定档。
- 队伍证据只引用 A / B+ / B / B- 聚合记录；C 只作为风险。
- 未拥有候选的主证据只接受 `plan_dependency == [candidate]`；同时依赖其他计划角色的队伍进入 conditional risk。

## 总览

| character | type | pull_value | prior_final_stage | local_rule_stage | final_stage | stage_delta | delta_requires_review | change_allowed_reason | acceptable_stage | unresolved_stage | stage_confidence | not_recommended_stage | missing_data | evidence_ids | evidence_keys | risk_evidence_ids | risk_evidence_keys | key_basis | risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 德尔塔 `delta` | rerun | 中高 | - | 0+0 | 0+0 | none | no | no_prior_baseline | 0+0 |  | medium | 高档位暂不判断；只在机制/指南/实战证明必要时考虑 | 高档位收益 | E-SD-49044A37B0, E-SD-C4150B39C3 | sd\|anchor-one\|delta\|support, sd\|anchor-two\|delta\|support | - | - | T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 2 条，其中 A/B+ 0 条、A/B+/B 2 条 | 新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性 |
| 伊普西龙 `epsilon` | rerun | 中 | - | 0+0 | 0+0 | none | no | no_prior_baseline | 0+0 |  | medium | 高档位暂不判断；只在机制/指南/实战证明必要时考虑 | 与 zeta 捆绑的多候选队伍不能当单抽主证据 | E-SD-12A6377412 | sd\|anchor-one\|epsilon\|support | E-SD-46AB991DE4 | sd\|epsilon\|support\|zeta | T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 0 条、A/B+/B 1 条 | 同 mode 主证据仅支持中优先级；新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性；1 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据 |
| 泽塔 `zeta` | new | 等实测 | - | 等实测 | 等实测 | none | no | no_prior_baseline | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、跨期高难复测 | - | - | E-SD-46AB991DE4 | sd\|epsilon\|support\|zeta | 新角色已有跨期实测：6 个 snapshot；仍需结合机制与账号价值复核，不自动提升推荐档位；未知属性 / 未知特性 / 未知定位；暂无机制文本；先验证是否补当前 Box 拼图，还是要求后续售后队友 | 已有跨期记录不等于推荐档位自动升级，仍需复核证据质量与机制必要性；已有跨期数据，仍需补齐机制、专属收益和替代关系；1 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据 |

## 角色明细

### 德尔塔 `delta`：中高

- 类型：rerun；状态：next
- prior_final_stage：-
- prior_decision_status：-；prior_confidence：-
- prior_reason：-
- local_rule_stage：0+0
- recommended_stage_for_review：0+0
- final_stage：0+0
- stage_delta：none；delta_requires_review：no
- delta_reason：无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。
- change_allowed_reason：no_prior_baseline
- new_evidence_categories：-
- recommended_stage(local_rule)：0+0
- acceptable_stage：0+0
- unresolved_stage：
- stage_confidence：medium
- not_recommended_stage：高档位暂不判断；只在机制/指南/实战证明必要时考虑
- stage_reason：两条独立 B 只支持本体优先级
- missing_data：高档位收益
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 3 / latest 22% / avg_last3 20% / trend 4
- 全局出场：best_latest=22%；best_avg_last3=20%；worst_trend=4
- 队伍覆盖：current 0(0)；target 2(B 2)；新增依赖 2(B 2)
- mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-
- 机制/拼图：以太 / 强攻 / 强攻；暂无机制文本
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E-SD-49044A37B0, E-SD-C4150B39C3
- 稳定证据键：sd|anchor-one|delta|support, sd|anchor-two|delta|support
- 风险/条件证据（conditional 或 B-/C）：-
- 风险证据键：-
- 依据：T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 2 条，其中 A/B+ 0 条、A/B+/B 2 条；mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-；同模式判定 sd: 中高
- 风险：新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性

### 伊普西龙 `epsilon`：中

- 类型：rerun；状态：next
- prior_final_stage：-
- prior_decision_status：-；prior_confidence：-
- prior_reason：-
- local_rule_stage：0+0
- recommended_stage_for_review：0+0
- final_stage：0+0
- stage_delta：none；delta_requires_review：no
- delta_reason：无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。
- change_allowed_reason：no_prior_baseline
- new_evidence_categories：-
- recommended_stage(local_rule)：0+0
- acceptable_stage：0+0
- unresolved_stage：
- stage_confidence：medium
- not_recommended_stage：高档位暂不判断；只在机制/指南/实战证明必要时考虑
- stage_reason：单候选主证据可支持本体
- missing_data：与 zeta 捆绑的多候选队伍不能当单抽主证据
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 3 / latest 22% / avg_last3 20% / trend 4
- 全局出场：best_latest=22%；best_avg_last3=20%；worst_trend=4
- 队伍覆盖：current 0(0)；target 2(B+ 1 / B 1)；新增依赖 2(B+ 1 / B 1)
- mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-
- 机制/拼图：火 / 异常 / 异常；暂无机制文本
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E-SD-12A6377412
- 稳定证据键：sd|anchor-one|epsilon|support
- 风险/条件证据（conditional 或 B-/C）：E-SD-46AB991DE4
- 风险证据键：sd|epsilon|support|zeta
- 依据：T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 0 条、A/B+/B 1 条；mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-；同模式判定 sd: 中
- 风险：同 mode 主证据仅支持中优先级；新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性；1 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据

### 泽塔 `zeta`：等实测

- 类型：new；状态：next
- prior_final_stage：-
- prior_decision_status：-；prior_confidence：-
- prior_reason：-
- local_rule_stage：等实测
- recommended_stage_for_review：等实测
- final_stage：等实测
- stage_delta：none；delta_requires_review：no
- delta_reason：无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。
- change_allowed_reason：no_prior_baseline
- new_evidence_categories：-
- recommended_stage(local_rule)：等实测
- acceptable_stage：暂不预设
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断
- stage_reason：已有 6 个 snapshot 的跨期实测，但缺少 mechanism_notes，不能据此自动升级 X+X 档位
- missing_data：技能机制、影画、专武、跨期高难复测
- source_quality：-
- stage_notes：-
- 历史走势：暂无全局 usage 出场点；完整真实队伍表已有跨期实测（6 snapshots）
- 全局出场：best_latest=0%；best_avg_last3=0%；worst_trend=0
- 队伍覆盖：current 0(0)；target 1(B+ 1)；新增依赖 1(B+ 1)
- mechanism_review：暂无 mechanism_notes；已有跨期实测，等待机制资料与证据质量复核
- 机制/拼图：未知属性 / 未知特性 / 未知定位；暂无机制文本
- 替代风险：机制未知，替代风险无法判定
- 证据：-
- 稳定证据键：-
- 风险/条件证据（conditional 或 B-/C）：E-SD-46AB991DE4
- 风险证据键：sd|epsilon|support|zeta
- 依据：新角色已有跨期实测：6 个 snapshot；仍需结合机制与账号价值复核，不自动提升推荐档位；未知属性 / 未知特性 / 未知定位；暂无机制文本；先验证是否补当前 Box 拼图，还是要求后续售后队友
- 风险：已有跨期记录不等于推荐档位自动升级，仍需复核证据质量与机制必要性；已有跨期数据，仍需补齐机制、专属收益和替代关系；1 条候选相关队伍同时依赖其他计划角色，只作为 conditional risk，不作为抽取主证据

## 本地 GPT 评判接入状态

- 当前报告由本地确定性规则生成，可离线复现。
- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。
- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。
