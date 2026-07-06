# 绝区零方法论迁移试算

本文件用 `endgame-evidence-planner` 方法论试迁移到绝区零。它不是抽取榜，也不是最终培养榜；目标是验证“先数据质量、再队伍覆盖、最后才谈培养/抽取”的流程能否适配 ZZZ。

## 试算口径

- 当前 box：`.miho/zzz_box_state.json`
- 当前 owned：19 名代理人
- 试算 planned：`nom`, `sunna`
- planned 来源：`configs/zzz_banner_plan.json` 的 3.0 下半调频配置；这里只作为迁移演示输入，不等于正式抽取建议。
- 主数据源：`out_zzz/team_rank_dedup_unordered.csv`
- 辅助来源：`out_zzz/name_map.csv`, `out_zzz/prydwen_tier_current.csv`, `out_zzz/phase_index.csv`, `out_zzz/export_report.md`

## 数据质量摘要

| item | value |
|---|---:|
| 导出时间 | 2026-07-05T12:49:22 |
| 数据源 | `LvlUrArti/ShiyuDataProcessed` + Prydwen ZZZ + HoYoWiki |
| 成功读取 snapshot | 8 |
| 模式 | `sd` 式舆防卫 / `da` 危局强袭 |
| phase rows | 16 |
| character_usage_long rows | 3908 |
| team_rank_raw rows | 15875 |
| team_rank_dedup_unordered rows | 14306 |
| unresolved names | 1 |
| export warnings / errors | 0 / 0 |

### 迁移限制

- ZZZ 队伍是 3 名代理人 + 邦布；本试算只用代理人判断账号可组，邦布只作为队伍记录附属信息。
- `out_zzz/team_rank_dedup_unordered.csv` 没有 HSR 那种 `duplicate_count` 字段，因此不能直接复用 HSR 的“重复记录数”置信规则。
- 当前目标账号命中的队伍 `app_rate` 最高只有 0.07，全部偏低；本次不强行给 A 档。
- `avg_score=0` 视为 sentinel，不当作真实分数。
- SD / DA 都是分数量纲，但仍不做跨模式横向数值比较。
- Box 只有 `ye-shunguang` 的练度细节，其他 owned 不能默认视作高难 auto-ready。

## 目标账号覆盖摘要

| item | value |
|---|---:|
| owned_count | 19 |
| planned_count | 2 |
| target_count | 21 |
| target team records | 80 |
| unique agent teams | 14 |
| mode split | SD 41 / DA 39 |
| plan_dependency=none | 34 |
| plan_dependency=sunna | 46 |
| plan_dependency=nom | 0 |
| confidence | A 0 / B 80 / C 0 |

`nom` 在当前真实队伍记录里没有目标账号可组证据，应按新角色/未实测处理。`sunna` 有大量 B 档覆盖，但因为这是试算 planned，且记录出场率低，不应直接变成抽取结论。

## 队伍覆盖样例

| confidence | mode | phase_ver | scope | team_slugs | team_cn | plan_dependency | records | max_app_rate | best_score_note |
|---|---|---|---|---|---|---|---:|---:|---|
| B | sd/da | multi | multi | zhu-yuan, qingyi, nicole-demara | 朱鸢 / 青衣 / 妮可 | none | 17 | 0.06 | 非 sentinel；当前 owned 可组 |
| B | sd/da | multi | multi | billy-starlight, koleda, pan-yinhu | 星徽·比利 / 珂蕾妲 / 潘引壶 | none | 10 | 0.07 | 非 sentinel；当前 owned 可组 |
| B | da | 3.0.1 | 1-1/top | piper, velina, lucy | 派派 / 维琳娜 / 露西 | none | 2 | 0.02 | 非 sentinel；当前 owned 可组但样本少 |
| B | sd/da | multi | multi | ye-shunguang, qingyi, sunna | 叶瞬光 / 青衣 / 千夏 | sunna | 14 | 0.03 | 非 sentinel；依赖计划千夏 |
| B | sd/da | multi | multi | ye-shunguang, orphie-and-magus, sunna | 叶瞬光 / 奥菲丝&鬼火 / 千夏 | sunna | 8 | 0.04 | 非 sentinel；依赖计划千夏 |
| B | sd/da | multi | multi | zhu-yuan, sunna, nicole-demara | 朱鸢 / 千夏 / 妮可 | sunna | 7 | 0.06 | 非 sentinel；依赖计划千夏 |
| B | sd/da | multi | multi | ye-shunguang, sunna, nicole-demara | 叶瞬光 / 千夏 / 妮可 | sunna | 8 | 0.02 | 非 sentinel；依赖计划千夏 |

## 代理人覆盖解读

### 当前 owned 主线

| group | agents | evidence | interpretation |
|---|---|---|---|
| 以太旧队 | `zhu-yuan`, `qingyi`, `nicole-demara` | 17 条 B 记录，SD/DA 都有 | 当前 box 最明确的已有队伍骨架；但朱鸢 Prydwen 当前为 T1.5，不应因此重投入到核心级别。 |
| 物理 / 命破队 | `billy-starlight`, `koleda`, `pan-yinhu` | 10 条 B 记录，SD/DA 都有 | 星徽·比利和潘引壶有队伍覆盖，适合作为已有队补练度观察点。 |
| 风异常试队 | `piper`, `velina`, `lucy` | 2 条 B 记录，只在 DA 命中 | 维琳娜已 owned，但本地目标队记录少；更多是“等更多周期”而不是直接核心化。 |

### planned 试算线

| group | agents | evidence | interpretation |
|---|---|---|---|
| 千夏 + 叶瞬光 | `ye-shunguang`, `qingyi`, `sunna` | 14 条 B 记录 | 若把千夏纳入目标账号，她优先服务叶瞬光线；但记录低出场，不能单独推出抽取结论。 |
| 千夏 + 叶瞬光 / 奥菲丝 | `ye-shunguang`, `orphie-and-magus`, `sunna` | 8 条 B 记录 | 奥菲丝已 owned，说明千夏可能扩展已有火/物理相关骨架。 |
| 千夏 + 朱鸢 | `zhu-yuan`, `sunna`, `nicole-demara` | 7 条 B 记录 | 可作为朱鸢替代辅助线，但不如当前 `qingyi + nicole` 队伍直接。 |
| Nom | `nom` | 0 条目标账号可组真实记录 | 新角色/未进入历史队伍池，当前只能等实测，不能用理论队伍做主依据。 |

## 暂定培养动作

这不是排榜，只是迁移方法下的动作分层。

| category | agents | evidence basis | action |
|---|---|---|---|
| 核心保留 | `ye-shunguang`, `qingyi`, `nicole-demara` | 当前 owned 队伍覆盖高；叶瞬光本地有练度记录 | 保持为主要高难骨架，优先补齐叶瞬光练度和关键辅助基础练度。 |
| 成队补练 | `zhu-yuan`, `billy-starlight`, `pan-yinhu`, `koleda` | 多条 B 记录覆盖 SD/DA | 只在已有练度接近可用时补，不新增重资源到低置信队。 |
| 模式观察 | `velina`, `piper`, `lucy`, `orphie-and-magus` | B 记录少或依赖特定 planned | 记录存在但不足，等后续 snapshot 或实际体验。 |
| planned 观察 | `sunna` | 46 条 B 记录，但全部低 app-rate且依赖计划口径 | 可以作为下一步重点观察对象，不在本试算直接定“抽”。 |
| 暂缓 | `nom` | 0 条真实队伍记录 | 等实测和下一轮导出；理论队伍不能作为培养依据。 |

## 迁移结论

这套方法可以迁移到 ZZZ，但需要两点项目级调整：

1. 不能照搬 HSR 的 `duplicate_count` 置信规则。ZZZ 去重表目前没有该字段，应在程序里按 team signature 聚合 `record_count`、`snapshot_count`、`mode_count` 来替代。
2. ZZZ 需要把邦布从“账号可组核心条件”里拆出来：有邦布数据时作为风险字段，没有时不阻断代理人队伍覆盖。

本次试算的实际结论很克制：当前 ZZZ box 可以先围绕 `ye-shunguang` 与现有 `zhu-yuan/qingyi/nicole`、`billy-starlight/koleda/pan-yinhu` 骨架补练度；`sunna` 有计划后覆盖潜力但仍是 B 档观察；`nom` 暂时没有真实队伍依据。
