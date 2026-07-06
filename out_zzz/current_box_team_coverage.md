# 当前 Box 队伍覆盖

- 生成时间：2026-07-06T20:43:34
- scenario：`current_box`
- 队伍数据源：`out_zzz\team_rank_dedup_unordered.csv`
- team signature 聚合数：1423
- 当前拥有：19；计划角色：none；目标账号角色数：19
- 可组 team signature：7
- 置信度分布：B- 6 / C 1
- 计划依赖分布：none 7

## 置信度口径

- A：跨多期、多 Boss/范围、多模式且出场率较高，非 sentinel 分数充足。
- B+：重复度和出场率都较好，但广度或稳定性略弱于 A。
- B：有真实记录和一定重复度，可证明可组与存在感，但不能直接推断长期 auto 稳定。
- B-：真实记录稀疏、出场率低或 sentinel 较多，只能作为弱证据。
- C：缺目标账号成员、无有效表现，或证据不足以支撑覆盖结论。

## 数据口径

- 先按无序三代理人 team signature 聚合，再做 current/target coverage。
- planned 只作为 target scenario 的增量成员，不和 current_box 结论混写；target 表保留 `plan_dependency`。
- `0`、`99.99`、缺失分数按 sentinel / missing 处理，不作为真实表现。
- SD/DA 分数不互相横比；这里只在同一 team signature 内做证据强弱聚合。
- Bangboo 不参与账号拥有覆盖判断。

## 覆盖记录

| evidence_id | scenario | confidence | team_signature | team_slugs | team_cn | owned_count | plan_dependency | missing_parts | record_count | snapshot_count | phase_count | mode_count | scope_count | boss_count | source_kind_count | max_app_rate | median_app_rate | best_rank | best_score | non_sentinel_score_count | sentinel_score_count | modes | evidence_comment | risk_comment |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---|---|
| E0001 | current_box | B- | billy-starlight\|koleda\|pan-yinhu | billy-starlight, koleda, pan-yinhu | 星徽·比利 / 珂蕾妲·贝洛伯格 / 潘引壶 | 3 | none | none | 10 | 3 | 5 | 2 | 5 | 4 | 1 | 0.07 | 0.035 | 65 | 28184 | 10 | 0 | da, sd | record_count=10；phase_count=5；mode_count=2；boss_count=4；max_app_rate=0.07；median_app_rate=0.035 | 记录稀疏或出场率较低 |
| E0002 | current_box | B- | nicole-demara\|qingyi\|zhu-yuan | nicole-demara, qingyi, zhu-yuan | 妮可·德玛拉 / 青衣 / 朱鸢 | 3 | none | none | 17 | 6 | 8 | 2 | 6 | 5 | 1 | 0.06 | 0.02 | 64 | 46171 | 11 | 6 | da, sd | record_count=17；phase_count=8；mode_count=2；boss_count=5；max_app_rate=0.06；median_app_rate=0.02 | 包含 6 条 sentinel/missing 分数；记录稀疏或出场率较低 |
| E0003 | current_box | B- | lucy\|piper\|velina | lucy, piper, velina | 露西亚娜·德·蒙特夫 / 派派·韦尔 / 维琳娜·艾嘉德 | 3 | none | none | 2 | 1 | 1 | 1 | 2 | 1 | 1 | 0.02 | 0.02 | 105 | 21155 | 2 | 0 | da | record_count=2；phase_count=1；mode_count=1；boss_count=1；max_app_rate=0.02；median_app_rate=0.02 | 记录稀疏或出场率较低 |
| E0004 | current_box | B- | billy-starlight\|pan-yinhu\|qingyi | billy-starlight, pan-yinhu, qingyi | 星徽·比利 / 潘引壶 / 青衣 | 3 | none | none | 2 | 1 | 2 | 2 | 2 | 2 | 1 | 0.01 | 0.01 | 134 | 20145 | 1 | 1 | da, sd | record_count=2；phase_count=2；mode_count=2；boss_count=2；max_app_rate=0.01；median_app_rate=0.01 | 包含 1 条 sentinel/missing 分数；记录稀疏或出场率较低 |
| E0005 | current_box | B- | billy-starlight\|lucy\|pan-yinhu | billy-starlight, lucy, pan-yinhu | 星徽·比利 / 露西亚娜·德·蒙特夫 / 潘引壶 | 3 | none | none | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0.01 | 0.01 | 160 | 25620 | 1 | 0 | sd | record_count=1；phase_count=1；mode_count=1；boss_count=1；max_app_rate=0.01；median_app_rate=0.01 | 记录稀疏或出场率较低 |
| E0006 | current_box | B- | koleda\|lucy\|ye-shunguang | koleda, lucy, ye-shunguang | 珂蕾妲·贝洛伯格 / 露西亚娜·德·蒙特夫 / 叶瞬光 | 3 | none | none | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0.01 | 0.01 | 114 | 25032 | 1 | 0 | sd | record_count=1；phase_count=1；mode_count=1；boss_count=1；max_app_rate=0.01；median_app_rate=0.01 | 记录稀疏或出场率较低 |
| E0007 | current_box | C | nekomata\|nicole-demara\|qingyi | nekomata, nicole-demara, qingyi | 猫宫 又奈 / 妮可·德玛拉 / 青衣 | 3 | none | none | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 0.01 | 0.01 | 314 | - | 0 | 1 | da | record_count=1；phase_count=1；mode_count=1；boss_count=0；max_app_rate=0.01；median_app_rate=0.01 | 全部表现分数为 sentinel/missing |
