# 当前 Box 队伍覆盖

- 生成时间：<GENERATED_AT>
- 方法版本：`evidence-first-v1-20260712`
- scenario：`current_box`
- 队伍数据源：`<ROOT>\input\data\team_rank_dedup_unordered.csv`
- team signature 聚合数：4
- composition 数：3
- 当前拥有：3；计划角色：none；目标账号角色数：3
- 可组 team signature：2
- A 档 min_app_rate 阈值：10
- Bangboo 拥有信息：已读取
- Build 信息：已读取显式 built/builds
- 模式分布：sd 1 / da 1
- 数据质量：原始 22 行 / 纳入 22 行；无效 app_rate 0；空队 0；不完整队 0；重复角色 0。
- 表现质量：metric `avg_score`；missing/non-finite 0；sentinel 3。
- Alias/稳定性目录：alias 10；stability role 5。
- 置信度分布：A 1 / B 1
- 源证据置信度：A 1 / B 1
- 计划依赖分布：none 2

## 置信度口径

- A：单一 mode 内跨多期、多 Boss/范围且出场率较高，非 sentinel 分数充足并有明确稳定组件。
- B+：重复度和出场率都较好，但广度或稳定性略弱于 A。
- B：有真实记录和一定重复度，可证明可组与存在感，但不能直接推断长期 auto 稳定。
- B-：真实记录稀疏、出场率低或 sentinel 较多，只能作为弱证据。
- C：缺目标账号成员、无有效表现，或证据不足以支撑覆盖结论。

## 数据口径

- 先按无序三代理人 `agent_signature` 做账号覆盖，再按三代理人 + Bangboo 的 `full_team_signature` 聚合真实队伍证据。
- planned 只作为 target scenario 的增量成员，不和 current_box 结论混写；target 表保留 `plan_dependency`。
- `0`/缺失表现按 sentinel / missing 处理；`99.99` 只是 HSR `avg_round` sentinel，ZZZ 合法分数 `99.99` 仍是有效表现。
- `metric_direction` 控制 best_score 取值方向；SD/DA 本地原始 JSON 的 `avg_round` 实为分数，按 `higher_better` 处理，但 SD/DA 分数仍不互相横比。
- 同一 composition 在不同 mode 生成独立 `evidence_key=mode|full_team_signature`；分数、出场率与置信度均不跨模式合并。
- A 需满足模式策略的重复度、非 sentinel 比例且有明确稳定组件；稳定性未知时最高 B+。
- `source_confidence` 表示真实队伍数据强度；正式 `confidence` 再结合目标账号 build readiness，未提供或未培养会将源 A/B+ 降为 B。
- Bangboo 写入 full evidence signature；只有 box 提供 Bangboo 拥有信息时才校验，否则标记 `邦布未校验`，不影响三代理人可组判断。

## 覆盖记录

| evidence_id | evidence_key | scenario | mode | mode_cn | source_confidence | confidence | team_signature | agent_signature | full_team_signature | team_slugs | team_cn | bangboo_slug | bangboo_name_cn | bangboo_checked | owned_count | built_count | build_checked | unbuilt_parts | plan_dependency | missing_parts | record_count | duplicate_count | snapshot_count | phase_count | scope_count | boss_count | source_kind_count | max_app_rate | median_app_rate | best_rank | best_score | metric_name | metric_direction | non_sentinel_score_count | sentinel_score_count | valid_score_ratio | phase_versions | phase_names | scopes | source_kinds | observation_keys | stability_status | evidence_comment | risk_comment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E-SD-DA019C43D7 | sd\|lucy\|miyabi\|nicole-demara\|bangboo:biggest-fan | current_box | sd | 式舆防卫 | A | A | lucy\|miyabi\|nicole-demara\|bangboo:biggest-fan | lucy\|miyabi\|nicole-demara | lucy\|miyabi\|nicole-demara\|bangboo:biggest-fan | lucy, miyabi, nicole-demara | 露西 / 星见雅 / 妮可 | biggest-fan | 阿饭 | 已拥有 | 3 | 3 | 已读取 | none | none | none | 12 | 15 | 12 | 6 | 3 | 3 | 1 | 12.5 | 7 | 1 | 30011 | avg_score | higher_better | 11 | 1 | 0.916667 | sd:2.8.1, sd:2.8.2, sd:2.8.3, sd:2.8.4, sd:2.8.5, sd:2.8.6 | SD 2.8.1, SD 2.8.2, SD 2.8.3, SD 2.8.4, SD 2.8.5, SD 2.8.6 | 5-1_combined.json, 5-2_combined.json, 5-3_combined.json | dedup | sd-281-a:sd:2.8.1:SD 2.8.1:5-1_combined.json:-:2; sd-281-b:sd:2.8.1:SD 2.8.1:5-2_combined.json:-:1; sd-282-a:sd:2.8.2:SD 2.8.2:5-3_combined.json:-:3; sd-282-b:sd:2.8.2:SD 2.8.2:5-1_combined.json:-:4; sd-283-a:sd:2.8.3:SD 2.8.3:5-2_combined.json:-:5; sd-283-b:sd:2.8.3:SD 2.8.3:5-3_combined.json:-:6; sd-284-a:sd:2.8.4:SD 2.8.4:5-1_combined.json:-:7; sd-284-b:sd:2.8.4:SD 2.8.4:5-2_combined.json:-:8; sd-285-a:sd:2.8.5:SD 2.8.5:5-3_combined.json:-:9; sd-285-b:sd:2.8.5:SD 2.8.5:5-1_combined.json:-:10; sd-286-a:sd:2.8.6:SD 2.8.6:5-2_combined.json:-:11; sd-286-b:sd:2.8.6:SD 2.8.6:5-3_combined.json:-:12 | present | record_count=12；phase_count=6；mode_count=1；boss_count=3；scope_count=3；valid_score_count=11；sentinel_ratio=0.0833333；stability_status=present；max_app_rate=12.5；median_app_rate=7；min_a_app_rate=10 | 包含 1 条 sentinel/missing 分数 |
| E-DA-DB7F5133D3 | da\|lucy\|miyabi\|nicole-demara\|bangboo:biggest-fan | current_box | da | 危局强袭 | B | B | lucy\|miyabi\|nicole-demara\|bangboo:biggest-fan | lucy\|miyabi\|nicole-demara | lucy\|miyabi\|nicole-demara\|bangboo:biggest-fan | lucy, miyabi, nicole-demara | 露西 / 星见雅 / 妮可 | biggest-fan | 阿饭 | 已拥有 | 3 | 3 | 已读取 | none | none | none | 3 | 4 | 3 | 3 | 1 | 0 | 1 | 3 | 2 | 1 | 900003 | avg_score | higher_better | 3 | 0 | 1 | da:2.8.1, da:2.8.2, da:2.8.3 | DA 2.8.1, DA 2.8.2, DA 2.8.3 | all | raw | da-281:da:2.8.1:DA 2.8.1:all:-:3; da-282:da:2.8.2:DA 2.8.2:all:-:2; da-283:da:2.8.3:DA 2.8.3:all:-:1 | present | record_count=3；phase_count=3；mode_count=1；boss_count=0；scope_count=1；valid_score_count=3；sentinel_ratio=0；stability_status=present；max_app_rate=3；median_app_rate=2；min_a_app_rate=10 | 有重复记录，可作普通证据 |
