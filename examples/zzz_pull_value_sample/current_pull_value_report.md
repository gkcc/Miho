# 绝区零 Pull Value Report

- 生成时间：2026-07-06T23:39:23
- 数据目录：`out_zzz`
- Box：`.miho\zzz_box_state.json`
- 卡池计划：`configs\zzz_banner_plan.json`
- 机制笔记：`configs\zzz_mechanism_notes`
- 候选角色：4；planned_slugs：velina, ye-shunguang, piper, nicole-demara
- current coverage records：7；target coverage records：7

## 口径

- 复刻角色：按历史走势、全局出场、队伍覆盖、T 榜定位和 X+X 档位必要性评估。
- 新角色：按机制信息完整度、拼图关系、售后确定性和替代风险评估；没有历史队伍记录是未实测状态，不作为负面扣分。
- target coverage 只说明加入计划角色后的队伍覆盖，不单独决定抽取价值。
- mechanism_review 来自 `configs/zzz_mechanism_notes/*.yaml`，用于判断 0+0、0+1、1+0、1+1、2+1 等档位断点。
- 队伍证据只引用 A / B+ / B / B- 聚合记录；C 只作为风险。

## 总览

| character | type | pull_value | recommended_stage | acceptable_stage | unresolved_stage | stage_confidence | not_recommended_stage | missing_data | evidence_ids | key_basis | risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 叶瞬光 `ye-shunguang` | rerun | 高 | 0+0 | 0+0 | 0+1 / 1+0 / 1+1 / 2+1 | medium | 未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据 | 专武对比、1 影与 2 影文本、影画收益量化、0+1/1+0/1+1 的边际收益、是否绑定特定辅助、当前 Box 同定位主C替代关系。 | E0006 | T 榜最好评级 T0 / rating 11；历史出场点 18，近三期最高均值 77.59%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖 | 已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序 |
| 妮可·德玛拉 `nicole-demara` | rerun | 中 | 等技能/影画/专武/首轮数据 | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E0002, E0007 | T 榜最好评级 T0.5 / rating 10；历史出场点 18，近三期最高均值 3.19%；目标 Box 可组历史队伍 2 条，但不是该角色作为新增依赖 | 已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序 |
| 派派·韦尔 `piper` | rerun | 中 | 等技能/影画/专武/首轮数据 | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E0003 | T 榜最好评级 T1 / rating 9；历史出场点 18，近三期最高均值 0.567%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖 | 已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序 |
| 维琳娜·艾嘉德 `velina` | new | 等实测 | 等技能/影画/专武/首轮后续数据 | 暂不预设；若机制与 Box 拼图高度吻合，先评估 0+0。 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据 | 正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。 | E0003 | 新角色没有历史队伍记录属于正常未实测状态，不作为负面；风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；稀有度=S；archetype=风异常、异常主C、当前新 S；先验证是否补当前 Box 拼图，还是要求后续售后队友 | 正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。；替代风险无法从当前历史数据判断 |

## 角色明细

### 叶瞬光 `ye-shunguang`：高

- 类型：rerun；状态：current
- recommended_stage：0+0
- acceptable_stage：0+0
- unresolved_stage：0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：medium
- not_recommended_stage：未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据
- stage_reason：historical_usage 与 T0 定位支持本体价值；但纵向档位不能只靠历史队伍和覆盖推断。
- missing_data：专武对比、1 影与 2 影文本、影画收益量化、0+1/1+0/1+1 的边际收益、是否绑定特定辅助、当前 Box 同定位主C替代关系。
- source_quality：identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending
- stage_notes：0+0(value_type=本体完整度; evidence=本地 Prydwen tier/usage 显示叶瞬光为 SD/DA T0，近半年多期高出场。; missing_data=当前版本指南是否仍推荐 0+0 作为长期 auto 奖励投入线。)；0+1(value_type=专武价值; evidence=主C专武通常可能影响输出阈值，但当前 notes 没有稳定断点证据。; missing_data=专武数值、通用音擎替代、伤害/循环/阈值对比。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否优先于补其他角色。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、与低档位的边际收益差。)
- 历史走势：sd: points 9 / latest 78.29% / avg_last3 77.59% / trend 0；da: points 9 / latest 62.83% / avg_last3 67.693% / trend -14.14
- 全局出场：best_latest=78.29%；best_avg_last3=77.59%；worst_trend=-14.14
- 队伍覆盖：current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)
- mechanism_review：source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=本地 Prydwen tier/usage 显示叶瞬光为 SD/DA T0，近半年多期高出场。; missing_data=当前版本指南是否仍推荐 0+0 作为长期 auto 奖励投入线。)；0+1(value_type=专武价值; evidence=主C专武通常可能影响输出阈值，但当前 notes 没有稳定断点证据。; missing_data=专武数值、通用音擎替代、伤害/循环/阈值对比。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否优先于补其他角色。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、与低档位的边际收益差。)
- 机制/拼图：物理 / 强攻 / 直伤主C；复刻角色应优先看长期趋势、主推队友占用和你 Box 里是否已有同定位主C。；稀有度=S；archetype=物理强攻、直伤主C、高历史出场主C；关键队友=sunna、zhao、lucy
- 替代风险：主C纵向投入容易和新体系本体竞争；高档位保持未判定，缺资料只能记为缺证据。
- 证据：E0006
- 依据：T 榜最好评级 T0 / rating 11；历史出场点 18，近三期最高均值 77.59%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖；当前 Box 已有相关队伍 1 条；mechanism_review：source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=本地 Prydwen tier/usage 显示叶瞬光为 SD/DA T0，近半年多期高出场。; missing_data=当前版本指南是否仍推荐 0+0 作为长期 auto 奖励投入线。)；0+1(value_type=专武价值; evidence=主C专武通常可能影响输出阈值，但当前 notes 没有稳定断点证据。; missing_data=专武数值、通用音擎替代、伤害/循环/阈值对比。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否优先于补其他角色。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、与低档位的边际收益差。)
- 风险：已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序

### 妮可·德玛拉 `nicole-demara`：中

- 类型：rerun；状态：current
- recommended_stage：等技能/影画/专武/首轮数据
- acceptable_stage：暂不预设
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断
- stage_reason：缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X
- missing_data：技能机制、影画、专武、实战队伍、首轮高难数据
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 9 / latest 2.46% / avg_last3 2.797% / trend 0；da: points 9 / latest 3.75% / avg_last3 3.19% / trend 2.08
- 全局出场：best_latest=3.75%；best_avg_last3=3.19%；worst_trend=0
- 队伍覆盖：current 2(B- 1 / C 1)；target 2(B- 1 / C 1)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：以太 / 支援 / 辅助；以太支援老角色，更多看你是否缺对应辅助和影画。
- 替代风险：辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断
- 证据：E0002, E0007
- 依据：T 榜最好评级 T0.5 / rating 10；历史出场点 18，近三期最高均值 3.19%；目标 Box 可组历史队伍 2 条，但不是该角色作为新增依赖；当前 Box 已有相关队伍 2 条；mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 风险：已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序

### 派派·韦尔 `piper`：中

- 类型：rerun；状态：current
- recommended_stage：等技能/影画/专武/首轮数据
- acceptable_stage：暂不预设
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断
- stage_reason：缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X
- missing_data：技能机制、影画、专武、实战队伍、首轮高难数据
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 9 / latest 0.32% / avg_last3 0.36% / trend 0；da: points 9 / latest 0.54% / avg_last3 0.567% / trend -0.23
- 全局出场：best_latest=0.54%；best_avg_last3=0.567%；worst_trend=-0.23
- 队伍覆盖：current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：物理 / 异常 / 异常主C；陪跑只作为顺带收益，不单独驱动抽卡。
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E0003
- 依据：T 榜最好评级 T1 / rating 9；历史出场点 18，近三期最高均值 0.567%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖；当前 Box 已有相关队伍 1 条；mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 风险：已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序

### 维琳娜·艾嘉德 `velina`：等实测

- 类型：new；状态：current
- recommended_stage：等技能/影画/专武/首轮后续数据
- acceptable_stage：暂不预设；若机制与 Box 拼图高度吻合，先评估 0+0。
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：未判定 / 缺证据：0+1、1+0、1+1、2+1 需要机制、专武、影画、指南证据
- stage_reason：维琳娜是当前新 S，已有首轮 usage/tier 但历史窗口短；不能因为 coverage 或首轮单点直接给 X+X 结论。
- missing_data：正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。
- source_quality：identity=official_or_exported；historical_usage=first_cycle_only；target_coverage=low；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending
- stage_notes：0+0(value_type=本体完整度; evidence=本地数据已有 3.0.1 首轮 SD/DA usage 和 Prydwen T0.5 记录。; missing_data=后续期数复测、队伍稳定性、当前 Box 可组核心队。)；0+1(value_type=专武价值; evidence=暂无可确认断点。; missing_data=专武数值、通用音擎替代、异常积蓄/伤害/循环收益。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否绑定特定异常队友。)；2+1(value_type=高档位必要性; evidence=暂无资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、长期环境。)
- 历史走势：sd: points 2 / latest 10.34% / avg_last3 10.34% / trend 0；da: points 2 / latest 48.99% / avg_last3 57.97% / trend -17.96
- 全局出场：best_latest=48.99%；best_avg_last3=57.97%；worst_trend=-17.96
- 队伍覆盖：current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)
- mechanism_review：source_quality=identity=official_or_exported；historical_usage=first_cycle_only；target_coverage=low；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=low；0+0(value_type=本体完整度; evidence=本地数据已有 3.0.1 首轮 SD/DA usage 和 Prydwen T0.5 记录。; missing_data=后续期数复测、队伍稳定性、当前 Box 可组核心队。)；0+1(value_type=专武价值; evidence=暂无可确认断点。; missing_data=专武数值、通用音擎替代、异常积蓄/伤害/循环收益。)；1+0(value_type=影画断点; evidence=暂无可确认断点。; missing_data=1 影文本、收益量化、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无组合收益证据。; missing_data=0+1 与 1+0 是否互相放大、是否绑定特定异常队友。)；2+1(value_type=高档位必要性; evidence=暂无资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、长期环境。)
- 机制/拼图：风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；稀有度=S；archetype=风异常、异常主C、当前新 S
- 替代风险：新角色首轮数据波动大；高档位保持未判定，缺资料只能记为缺证据。
- 证据：E0003
- 依据：新角色没有历史队伍记录属于正常未实测状态，不作为负面；风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；稀有度=S；archetype=风异常、异常主C、当前新 S；先验证是否补当前 Box 拼图，还是要求后续售后队友
- 风险：正式机制细读、专武对比、影画文本、核心队友、首轮后续 SD/DA 复测、长期环境、是否要求后续售后队友。；替代风险无法从当前历史数据判断

## 本地 GPT 评判接入状态

- 当前报告由本地确定性规则生成，可离线复现。
- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。
- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。
