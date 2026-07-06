# 绝区零 Pull Value Report

- 生成时间：2026-07-06T23:39:23
- 数据目录：`out_zzz`
- Box：`.miho\zzz_box_state.json`
- 卡池计划：`configs\zzz_banner_plan.json`
- 机制笔记：`configs\zzz_mechanism_notes`
- 候选角色：2；planned_slugs：nom, sunna
- current coverage records：7；target coverage records：14

## 口径

- 复刻角色：按历史走势、全局出场、队伍覆盖、T 榜定位和 X+X 档位必要性评估。
- 新角色：按机制信息完整度、拼图关系、售后确定性和替代风险评估；没有历史队伍记录是未实测状态，不作为负面扣分。
- target coverage 只说明加入计划角色后的队伍覆盖，不单独决定抽取价值。
- mechanism_review 来自 `configs/zzz_mechanism_notes/*.yaml`，用于判断 0+0、0+1、1+0、1+1、2+1 等档位断点。
- 队伍证据只引用 A / B+ / B / B- 聚合记录；C 只作为风险。

## 总览

| character | type | pull_value | recommended_stage | acceptable_stage | unresolved_stage | stage_confidence | not_recommended_stage | missing_data | evidence_ids | key_basis | risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 千夏 `sunna` | rerun | 高 | 0+0 | 0+0 | 0+1 / 1+0 / 1+1 / 2+1 | medium | 未判定 / 缺证据：2+1以上缺机制、指南和实战必要性证据 | 专武对比、1+0 影画文本与实战收益、1+1 组合收益、2+1 是否有长期 auto 质变、当前 Box 主队绑定度、下版本环境是否继续抬物理/支援。 | E0007, E0008, E0009, E0010, E0011 | T 榜最好评级 T0 / rating 11；历史出场点 18，近三期最高均值 53.947%；目标 Box 新增依赖队伍 7 条，其中 A/B+ 0 条、A/B+/B 0 条 | 新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性 |
| 诺姆·霍洛维尔 `nom` | new | 等实测 | 等技能/影画/专武/首轮数据 | 暂不预设；若机制与 Box 拼图高度吻合，首轮数据后再评估 0+0 / 0+1。 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断；资料不足阶段不规划高档位 | 正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。 | - | 新角色没有历史队伍记录属于正常未实测状态，不作为负面；火 / 击破 / 击破；新 S 火属性击破；技能、专武、影画和首轮高难数据未落地，先只做关系识别。；稀有度=S；archetype=火击破、新 S、机制未实测；先验证是否补当前 Box 拼图，还是要求后续售后队友 | 正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。；替代风险无法从当前历史数据判断 |

## 角色明细

### 千夏 `sunna`：高

- 类型：rerun；状态：next
- recommended_stage：0+0
- acceptable_stage：0+0
- unresolved_stage：0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：medium
- not_recommended_stage：未判定 / 缺证据：2+1以上缺机制、指南和实战必要性证据
- stage_reason：historical_usage 很强，支持 0+0 本体价值；target_coverage 在当前 Box 只给弱覆盖，不能单独推高档；专武/影画/2+1 属于待机制与实战确认。
- missing_data：专武对比、1+0 影画文本与实战收益、1+1 组合收益、2+1 是否有长期 auto 质变、当前 Box 主队绑定度、下版本环境是否继续抬物理/支援。
- source_quality：identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending
- stage_notes：0+0(value_type=本体完整度; evidence=历史 usage 与 tier 数据支持复刻辅助本体价值；本地 target coverage 只作为辅助证据。; missing_data=需要确认当前版本实战指南是否仍认定 0+0 即可承担核心辅助功能。)；0+1(value_type=专武价值; evidence=目前只可判断为潜在增强，不能从历史队伍记录直接推断必需。; missing_data=专武数值、触发条件、覆盖率、循环改善、相对通用音擎收益。)；1+0(value_type=影画断点; evidence=可能改善循环或覆盖面，但当前 notes 未取得稳定攻略共识。; missing_data=1 影文本、收益量化、是否改变 auto 手感或队伍阈值。)；1+1(value_type=本体+专武+影画组合; evidence=组合收益需建立在 0+1 和 1+0 均明确有价值的前提上。; missing_data=专武与 1 影是否互相放大、是否绑定特定主队、是否优先于其他角色本体。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、和 0+0/0+1/1+0 的边际收益差。)
- 历史走势：sd: points 9 / latest 53.72% / avg_last3 53.947% / trend 0；da: points 9 / latest 46.41% / avg_last3 52.06% / trend -7.93
- 全局出场：best_latest=53.72%；best_avg_last3=53.947%；worst_trend=-7.93
- 队伍覆盖：current 0(0)；target 7(B- 6 / C 1)；新增依赖 7(B- 6 / C 1)
- mechanism_review：source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=历史 usage 与 tier 数据支持复刻辅助本体价值；本地 target coverage 只作为辅助证据。; missing_data=需要确认当前版本实战指南是否仍认定 0+0 即可承担核心辅助功能。)；0+1(value_type=专武价值; evidence=目前只可判断为潜在增强，不能从历史队伍记录直接推断必需。; missing_data=专武数值、触发条件、覆盖率、循环改善、相对通用音擎收益。)；1+0(value_type=影画断点; evidence=可能改善循环或覆盖面，但当前 notes 未取得稳定攻略共识。; missing_data=1 影文本、收益量化、是否改变 auto 手感或队伍阈值。)；1+1(value_type=本体+专武+影画组合; evidence=组合收益需建立在 0+1 和 1+0 均明确有价值的前提上。; missing_data=专武与 1 影是否互相放大、是否绑定特定主队、是否优先于其他角色本体。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、和 0+0/0+1/1+0 的边际收益差。)
- 机制/拼图：物理 / 支援 / 辅助；复刻辅助重点看泛用性、队友覆盖面，以及是否能补你 Box 的主C缺口。；稀有度=S；archetype=物理辅助、泛用支援、主C增益拼图；关键队友=ye-shunguang、zhao、miyabi、lucy
- 替代风险：target coverage 新增队伍多为 B-/C，不能单靠 box 覆盖定性；高档位不能因“缺少资料”直接判死刑，应保持 unresolved。
- 证据：E0007, E0008, E0009, E0010, E0011
- 依据：T 榜最好评级 T0 / rating 11；历史出场点 18，近三期最高均值 53.947%；目标 Box 新增依赖队伍 7 条，其中 A/B+ 0 条、A/B+/B 0 条；mechanism_review：source_quality=identity=official_or_exported；historical_usage=high；target_coverage=medium；guide_consensus=pending；skill_text=pending；cinema_signature_breakpoints=pending；stage_confidence=medium；0+0(value_type=本体完整度; evidence=历史 usage 与 tier 数据支持复刻辅助本体价值；本地 target coverage 只作为辅助证据。; missing_data=需要确认当前版本实战指南是否仍认定 0+0 即可承担核心辅助功能。)；0+1(value_type=专武价值; evidence=目前只可判断为潜在增强，不能从历史队伍记录直接推断必需。; missing_data=专武数值、触发条件、覆盖率、循环改善、相对通用音擎收益。)；1+0(value_type=影画断点; evidence=可能改善循环或覆盖面，但当前 notes 未取得稳定攻略共识。; missing_data=1 影文本、收益量化、是否改变 auto 手感或队伍阈值。)；1+1(value_type=本体+专武+影画组合; evidence=组合收益需建立在 0+1 和 1+0 均明确有价值的前提上。; missing_data=专武与 1 影是否互相放大、是否绑定特定主队、是否优先于其他角色本体。)；2+1(value_type=高档位必要性; evidence=当前没有足够资料证明 2+1 是长期 auto 高难奖励必需。; missing_data=2 影文本、2+1 实战质变、指南共识、和 0+0/0+1/1+0 的边际收益差。)
- 风险：新增覆盖来自 target scenario，需和历史全局强度一起看，不能单靠 target coverage 定性

### 诺姆·霍洛维尔 `nom`：等实测

- 类型：new；状态：next
- recommended_stage：等技能/影画/专武/首轮数据
- acceptable_stage：暂不预设；若机制与 Box 拼图高度吻合，首轮数据后再评估 0+0 / 0+1。
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断；资料不足阶段不规划高档位
- stage_reason：新角色没有历史队伍记录是未实测状态，不是负面；目前只确认火、击破、新 S 身份，不能根据 coverage=0 或模板规则下 X+X 结论。
- missing_data：正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。
- source_quality：identity=official_profile；historical_usage=none_new_character；target_coverage=not_applicable_until_release；guide_consensus=missing；skill_text=missing；cinema_signature_breakpoints=missing
- stage_notes：0+0(value_type=本体完整度; evidence=已知身份信息为火属性、击破、新 S；机制未实测。; missing_data=正式技能组、击破定位细节、站场/速切需求、首轮高难表现。)；0+1(value_type=专武价值; evidence=暂无可评估资料。; missing_data=专武数值、触发条件、替代音擎对比、是否改变循环或阈值。)；1+0(value_type=影画断点; evidence=暂无可评估资料。; missing_data=1 影文本、收益类型、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无可评估资料。; missing_data=0+1 与 1+0 是否互相放大、是否依赖特定队友。)；2+1(value_type=高档位必要性; evidence=暂无可评估资料。; missing_data=2 影文本、2+1 是否有长期 auto 必要性、指南与实战共识。)
- 历史走势：暂无历史出场；若为新角色，这是未实测状态，不作为负面
- 全局出场：best_latest=0%；best_avg_last3=0%；worst_trend=0
- 队伍覆盖：current 0(0)；target 0(0)；新增依赖 0(0)
- mechanism_review：source_quality=identity=official_profile；historical_usage=none_new_character；target_coverage=not_applicable_until_release；guide_consensus=missing；skill_text=missing；cinema_signature_breakpoints=missing；stage_confidence=low；0+0(value_type=本体完整度; evidence=已知身份信息为火属性、击破、新 S；机制未实测。; missing_data=正式技能组、击破定位细节、站场/速切需求、首轮高难表现。)；0+1(value_type=专武价值; evidence=暂无可评估资料。; missing_data=专武数值、触发条件、替代音擎对比、是否改变循环或阈值。)；1+0(value_type=影画断点; evidence=暂无可评估资料。; missing_data=1 影文本、收益类型、是否改善 auto 稳定性。)；1+1(value_type=本体+专武+影画组合; evidence=暂无可评估资料。; missing_data=0+1 与 1+0 是否互相放大、是否依赖特定队友。)；2+1(value_type=高档位必要性; evidence=暂无可评估资料。; missing_data=2 影文本、2+1 是否有长期 auto 必要性、指南与实战共识。)
- 机制/拼图：火 / 击破 / 击破；新 S 火属性击破；技能、专武、影画和首轮高难数据未落地，先只做关系识别。；稀有度=S；archetype=火击破、新 S、机制未实测
- 替代风险：目前只能确认身份信息；任何 X+X 结论都应等待正式技能、专武、影画和首轮数据。
- 证据：-
- 依据：新角色没有历史队伍记录属于正常未实测状态，不作为负面；火 / 击破 / 击破；新 S 火属性击破；技能、专武、影画和首轮高难数据未落地，先只做关系识别。；稀有度=S；archetype=火击破、新 S、机制未实测；先验证是否补当前 Box 拼图，还是要求后续售后队友
- 风险：正式技能、专武、影画、核心队友、首轮 SD/DA 队伍记录、替代关系、是否要求后续售后队友。；替代风险无法从当前历史数据判断

## 本地 GPT 评判接入状态

- 当前报告由本地确定性规则生成，可离线复现。
- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。
- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。
