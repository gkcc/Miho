# 绝区零 Pull Value Report

- 生成时间：2026-07-06T23:25:40
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
| 叶瞬光 `ye-shunguang` | rerun | 高 | 等技能/影画/专武/首轮数据 | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E0006 | T 榜最好评级 T0 / rating 11；历史出场点 16，近三期最高均值 77.59%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖 | 已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序 |
| 妮可·德玛拉 `nicole-demara` | rerun | 中 | 等技能/影画/专武/首轮数据 | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E0002, E0007 | T 榜最好评级 T0.5 / rating 10；历史出场点 16，近三期最高均值 3.19%；目标 Box 可组历史队伍 2 条，但不是该角色作为新增依赖 | 已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序 |
| 派派·韦尔 `piper` | rerun | 中 | 等技能/影画/专武/首轮数据 | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E0003 | T 榜最好评级 T1 / rating 9；历史出场点 16，近三期最高均值 0.567%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖 | 已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序 |
| 维琳娜·艾嘉德 `velina` | new | 等实测 | 等技能/影画/专武/首轮数据 | 暂不预设 | 0+0 / 0+1 / 1+0 / 1+1 / 2+1 | low | 暂不判断 | 技能机制、影画、专武、实战队伍、首轮高难数据 | E0003 | 新角色没有历史队伍记录属于正常未实测状态，不作为负面；风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；先验证是否补当前 Box 拼图，还是要求后续售后队友 | 等技能/影画/专武/首轮数据；替代风险无法从当前历史数据判断 |

## 角色明细

### 叶瞬光 `ye-shunguang`：高

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
- 历史走势：sd: points 8 / latest 78.29% / avg_last3 77.59% / trend -0.69；da: points 8 / latest 62.83% / avg_last3 67.693% / trend -13.6
- 全局出场：best_latest=78.29%；best_avg_last3=77.59%；worst_trend=-13.6
- 队伍覆盖：current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：物理 / 强攻 / 直伤主C；复刻角色应优先看长期趋势、主推队友占用和你 Box 里是否已有同定位主C。
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E0006
- 依据：T 榜最好评级 T0 / rating 11；历史出场点 16，近三期最高均值 77.59%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖；当前 Box 已有相关队伍 1 条；mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
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
- 历史走势：sd: points 8 / latest 2.46% / avg_last3 2.797% / trend -3.73；da: points 8 / latest 3.75% / avg_last3 3.19% / trend -0.88
- 全局出场：best_latest=3.75%；best_avg_last3=3.19%；worst_trend=-3.73
- 队伍覆盖：current 2(B- 1 / C 1)；target 2(B- 1 / C 1)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：以太 / 支援 / 辅助；以太支援老角色，更多看你是否缺对应辅助和影画。
- 替代风险：辅助/支援通常看覆盖面和不可替代机制；当前先按历史出场与成队覆盖判断
- 证据：E0002, E0007
- 依据：T 榜最好评级 T0.5 / rating 10；历史出场点 16，近三期最高均值 3.19%；目标 Box 可组历史队伍 2 条，但不是该角色作为新增依赖；当前 Box 已有相关队伍 2 条；mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
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
- 历史走势：sd: points 8 / latest 0.32% / avg_last3 0.36% / trend -0.16；da: points 8 / latest 0.54% / avg_last3 0.567% / trend 0.07
- 全局出场：best_latest=0.54%；best_avg_last3=0.567%；worst_trend=-0.16
- 队伍覆盖：current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：物理 / 异常 / 异常主C；陪跑只作为顺带收益，不单独驱动抽卡。
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E0003
- 依据：T 榜最好评级 T1 / rating 9；历史出场点 16，近三期最高均值 0.567%；目标 Box 可组历史队伍 1 条，但不是该角色作为新增依赖；当前 Box 已有相关队伍 1 条；mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 风险：已拥有时优先比较补档收益，而不是重新按未拥有抽取价值排序

### 维琳娜·艾嘉德 `velina`：等实测

- 类型：new；状态：current
- recommended_stage：等技能/影画/专武/首轮数据
- acceptable_stage：暂不预设
- unresolved_stage：0+0 / 0+1 / 1+0 / 1+1 / 2+1
- stage_confidence：low
- not_recommended_stage：暂不判断
- stage_reason：缺少 mechanism_notes，不能把 coverage=0 当负面，也不能凭模板推 X+X
- missing_data：技能机制、影画、专武、实战队伍、首轮高难数据
- source_quality：-
- stage_notes：-
- 历史走势：sd: points 1 / latest 10.34% / avg_last3 10.34% / trend 0；da: points 1 / latest 48.99% / avg_last3 48.99% / trend 0
- 全局出场：best_latest=48.99%；best_avg_last3=48.99%；worst_trend=0
- 队伍覆盖：current 1(B- 1)；target 1(B- 1)；新增依赖 0(0)
- mechanism_review：暂无 mechanism_notes；等技能/影画/专武/首轮数据
- 机制/拼图：风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。
- 替代风险：主C/输出位需和 Box 已有同定位输出比较；当前报告不把未知新角色缺历史视为负面
- 证据：E0003
- 依据：新角色没有历史队伍记录属于正常未实测状态，不作为负面；风 / 异常 / 异常主C；新角色历史样本少，重点看她是否是独立主C，还是更依赖特定异常/风体系。；先验证是否补当前 Box 拼图，还是要求后续售后队友
- 风险：等技能/影画/专武/首轮数据；替代风险无法从当前历史数据判断

## 本地 GPT 评判接入状态

- 当前报告由本地确定性规则生成，可离线复现。
- 当前采用无 API key 交互版：本地自动生成 `current_gpt_pull_reviewer_packet.md` / `next_gpt_pull_reviewer_packet.md`，你登录后让我读取 packet 做 X+X 评审。
- 如果未来要无人值守自动调用模型，再接入 OpenAI API key；未配置密钥时，本地规则报告不受影响。
