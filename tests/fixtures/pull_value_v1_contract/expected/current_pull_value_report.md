# 绝区零 Pull Value Report

- 方法版本：evidence-first-v1-20260712
- 生成时间：2026-07-12T13:14:15
- 数据目录：`<ROOT>\input\data`
- Box：`<ROOT>\input\box.json`
- 卡池计划：`<ROOT>\input\plan.json`
- 机制笔记：`<ROOT>\input\mechanism_notes`
- 定档 baseline：`<ROOT>\input\baseline.json`；已有基线：alpha, beta, nova
- 候选角色：4；planned_slugs：alpha, beta, gamma, nova, low-a
- current coverage records：0；target coverage records：3

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
| 阿尔法候选名 `alpha` | rerun | 高 | 1+1 | 0+0 | 1+1 | 0+0 -> 1+1 | yes | only_with_new_evidence | 0+0 | 0+1 / 1+0 / 1+1 / 2+1 | high | 2+1 以上缺少收益证据 | 1+1 与 2+1 的长线收益 | E-SD-078BE089A7 | sd\|alpha\|anchor-one\|support | - | - | T 榜最好评级 T0 / rating 11；历史出场点 7，近三期最高均值 46%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 1 条、A/B+/B 1 条 | 新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性 |
| 贝塔 `beta` | rerun | 中高 | 0+0 | 0+0 | 0+0 | none | no | baseline_consistent | 0+0 / 0+1 |  | medium | 高档位暂不判断；只在机制/指南/实战证明必要时考虑 | 专武对比 | E-SD-A412C67114 | sd\|anchor-one\|beta\|support | - | - | T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 1 条、A/B+/B 1 条 | 新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性 |
| 伽马 `gamma` | rerun | 中 | - | 等技能/影画/专武/首轮数据 | 等技能/影画/专武/首轮数据 | none | no | no_prior_baseline | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E-SD-FCD5C791C5 | sd\|anchor-one\|gamma\|support | - | - | T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 0 条、A/B+/B 1 条 | 同 mode 主证据仅支持中优先级；新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性 |
| 新星 `nova` | new | 等实测 | 0+1 | 等实测 | 0+1 | 等实测 -> 0+1 | yes | wait_for_repeated_data | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、跨期高难复测 | - | - | - | - | 新角色首轮实测已到：1 个 snapshot，当前仅单期/B- 证据；等待跨期复测，不自动提升推荐档位；未知属性 / 未知特性 / 未知定位；暂无机制文本；先验证是否补当前 Box 拼图，还是要求后续售后队友 | 首轮数据不能替代跨期稳定性验证；SD/DA 同 snapshot 只计一次；首轮已到，仍需跨期 SD/DA 复测和机制资料 |

## 角色明细

### 阿尔法候选名 `alpha`：高

- 类型：rerun；状态：current
- prior_final_stage：1+1
- prior_decision_status：locked；prior_confidence：high
- prior_reason：冻结基线保留 1+1
- local_rule_stage：0+0
- recommended_stage_for_review：1+1
- final_stage：1+1
- stage_delta：0+0 -> 1+1；delta_requires_review：yes
- delta_reason：本地规则与既有 baseline 不同；未登记新增证据，本地规则不能覆盖既有 GPT/人工定档。
- change_allowed_reason：only_with_new_evidence
- new_evidence_categories：-
- recommended_stage(local_rule)：0+0
- acceptable_stage：0+0
- unresolved_stage：0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：high
- not_recommended_stage：2+1 以上缺少收益证据
- stage_reason：显式 mechanism_notes 定档优先于默认回退
- missing_data：1+1 与 2+1 的长线收益
- source_quality：identity=official；breakpoints=reviewed
- stage_notes：0+0(value_type=本体完整度; evidence=机制笔记显式支持; missing_data=无)
- 历史走势：sd: points 7 / latest 48% / avg_last3 46% / trend 12
- 全局出场：best_latest=48%；best_avg_last3=46%；worst_trend=12
- 队伍覆盖：current 0(0)；target 1(A 1)；新增依赖 1(A 1)
- mechanism_review：source_quality=identity=official；breakpoints=reviewed；stage_confidence=high；0+0(value_type=本体完整度; evidence=机制笔记显式支持; missing_data=无)
- 机制/拼图：候选元素 / 候选特性 / 候选定位；候选 focus 优先；稀有度=S
- 替代风险：专武替代品未完整测试、高影画的机会成本高
- 证据：E-SD-078BE089A7
- 稳定证据键：sd|alpha|anchor-one|support
- 风险/条件证据（conditional 或 B-/C）：-
- 风险证据键：-
- 依据：T 榜最好评级 T0 / rating 11；历史出场点 7，近三期最高均值 46%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 1 条、A/B+/B 1 条；mechanism_review：source_quality=identity=official；breakpoints=reviewed；stage_confidence=high；0+0(value_type=本体完整度; evidence=机制笔记显式支持; missing_data=无)；同模式判定 sd: 高
- 风险：新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性

### 贝塔 `beta`：中高

- 类型：rerun；状态：current
- prior_final_stage：0+0
- prior_decision_status：locked；prior_confidence：medium
- prior_reason：与本地机制档一致
- local_rule_stage：0+0
- recommended_stage_for_review：0+0
- final_stage：0+0
- stage_delta：none；delta_requires_review：no
- delta_reason：本地规则与 baseline 一致；无需 delta review。
- change_allowed_reason：baseline_consistent
- new_evidence_categories：-
- recommended_stage(local_rule)：0+0
- acceptable_stage：0+0 / 0+1
- unresolved_stage：
- stage_confidence：medium
- not_recommended_stage：高档位暂不判断；只在机制/指南/实战证明必要时考虑
- stage_reason：B+ 主证据支持本体，专武待比较
- missing_data：专武对比
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 3 / latest 22% / avg_last3 20% / trend 4
- 全局出场：best_latest=22%；best_avg_last3=20%；worst_trend=4
- 队伍覆盖：current 0(0)；target 1(B+ 1)；新增依赖 1(B+ 1)
- mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-
- 机制/拼图：冰 / 异常 / 异常；暂无机制文本
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E-SD-A412C67114
- 稳定证据键：sd|anchor-one|beta|support
- 风险/条件证据（conditional 或 B-/C）：-
- 风险证据键：-
- 依据：T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 1 条、A/B+/B 1 条；mechanism_review：stage_confidence=medium；0+0=-；0+1=-；1+0=-；1+1=-；2+1=-；同模式判定 sd: 中高
- 风险：新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性

### 伽马 `gamma`：中

- 类型：rerun；状态：current
- prior_final_stage：-
- prior_decision_status：-；prior_confidence：-
- prior_reason：-
- local_rule_stage：等技能/影画/专武/首轮数据
- recommended_stage_for_review：等技能/影画/专武/首轮数据
- final_stage：等技能/影画/专武/首轮数据
- stage_delta：none；delta_requires_review：no
- delta_reason：无 prior baseline；沿用本地规则建议，仍需 GPT/人工评审。
- change_allowed_reason：no_prior_baseline
- new_evidence_categories：-
- recommended_stage(local_rule)：等技能/影画/专武/首轮数据
- acceptable_stage：暂不预设
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断
- stage_reason：缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X
- missing_data：技能机制、影画、专武、实战队伍、首轮高难数据
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 3 / latest 22% / avg_last3 20% / trend 4
- 全局出场：best_latest=22%；best_avg_last3=20%；worst_trend=4
- 队伍覆盖：current 0(0)；target 1(B 1)；新增依赖 1(B 1)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：电 / 强攻 / 强攻；暂无机制文本
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E-SD-FCD5C791C5
- 稳定证据键：sd|anchor-one|gamma|support
- 风险/条件证据（conditional 或 B-/C）：-
- 风险证据键：-
- 依据：T 榜最好评级 T0.5 / rating 10；历史出场点 3，近三期最高均值 20%；目标 Box 新增依赖队伍 1 条，其中 A/B+ 0 条、A/B+/B 1 条；mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据；同模式判定 sd: 中
- 风险：同 mode 主证据仅支持中优先级；新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性

### 新星 `nova`：等实测

- 类型：new；状态：current
- prior_final_stage：0+1
- prior_decision_status：soft_locked；prior_confidence：low
- prior_reason：新角色首轮单快照 B- 证据仅作 delta 审核反例
- local_rule_stage：等实测
- recommended_stage_for_review：0+1
- final_stage：0+1
- stage_delta：等实测 -> 0+1；delta_requires_review：yes
- delta_reason：本地规则与既有 baseline 不同；未登记新增证据，本地规则不能覆盖既有 GPT/人工定档。
- change_allowed_reason：wait_for_repeated_data
- new_evidence_categories：-
- recommended_stage(local_rule)：等实测
- acceptable_stage：暂不预设
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断
- stage_reason：首轮实测已到，但当前仅 1 个 snapshot 的单期/B- 证据，不能据此预设 X+X 档位
- missing_data：技能机制、影画、专武、跨期高难复测
- source_quality：-
- stage_notes：-
- 历史走势：暂无全局 usage 出场点；完整真实队伍表已有首轮实测（1 snapshot）
- 全局出场：best_latest=0%；best_avg_last3=0%；worst_trend=0
- 队伍覆盖：current 0(0)；target 0(0)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；首轮已到，等待机制资料与跨期复测
- 机制/拼图：未知属性 / 未知特性 / 未知定位；暂无机制文本
- 替代风险：机制未知，替代风险无法判定
- 证据：-
- 稳定证据键：-
- 风险/条件证据（conditional 或 B-/C）：-
- 风险证据键：-
- 依据：新角色首轮实测已到：1 个 snapshot，当前仅单期/B- 证据；等待跨期复测，不自动提升推荐档位；未知属性 / 未知特性 / 未知定位；暂无机制文本；先验证是否补当前 Box 拼图，还是要求后续售后队友
- 风险：首轮数据不能替代跨期稳定性验证；SD/DA 同 snapshot 只计一次；首轮已到，仍需跨期 SD/DA 复测和机制资料

## 本地 GPT 评判接入状态

- 当前报告由本地确定性规则生成，可离线复现。
- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。
- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。
