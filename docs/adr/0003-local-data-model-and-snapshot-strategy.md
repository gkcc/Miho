# ADR-0003：本地数据模型与报告策略

状态：已更新

## 背景

当前阶段不设计正式数据库。先用 JSON 文件表达输入、过程和输出，让评分、配队、培养和未来观察逻辑稳定下来。

## 约束条件

- 本地输出放在 `data/probes/`，不得提交。
- roster JSON 必须脱敏。
- 公开 meta 必须记录来源和生成时间。
- 报告必须同时生成 JSON 和 Markdown。
- 图片识别得到的 roster 只能作为候选 box。

## 数据对象

| 对象 | 来源 | 用途 |
| --- | --- | --- |
| `meta_snapshot` | 公开 Prydwen 页面和统计接口 | tier、出场率、队伍使用率、高难统计 |
| `roster` | 本地 box 图或脱敏 JSON | 当前账号拥有角色、等级、影画 |
| `agent_values` | meta + roster | 账号内价值排序 |
| `team_recommendations` | meta + roster + value | 当前高难候选队伍 |
| `future_watchlist` | 缺一名角色队伍 | 未来观察和抽取前问题 |

## 候选方案

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| JSON/Markdown | 易 diff、易测试、易人工复核 | 不是长期存储 | 当前采用 |
| 正式数据库 | 查询强、适合应用 | 当前过早 | 暂缓 |
| 只输出 Markdown | 人读方便 | 难测试 | 不选 |

## 推荐结论

当前继续以 JSON 为机器可测输出，以 Markdown 为用户验收输出。

核心输出：

```text
agent_value_cards.json
agent_value_cards.md
```

## 原型阶段建议

- JSON 字段保持向后兼容。
- Markdown 以“一屏结论”为第一阅读层。
- 所有评分结论必须有原因文本。
- 缺失角色只出现在未来观察区。

## 最终产品建议

当 JSON 字段稳定后，再迁移到正式本地存储。迁移前必须保留 JSON fixture 回归测试。

## 不选择其他方案的原因

- 当前评分逻辑仍在变化，数据库会增加重构成本。
- 只做 Markdown 无法可靠验证算法。

## 后续验证任务

1. 固定 `agent_values` 字段契约。
2. 固定 `team_recommendations` 字段契约。
3. 增加 `future_watchlist` 的置信度和来源说明。
4. 增加本地 report fixture。

## 风险清单

- 字段命名频繁变化会让测试和 CLI 不稳定。
- 当前 roster 只有角色粗信息，没有完整练度。
- 未来观察容易被误读为抽取建议，报告必须持续强调边界。
