# ADR-0002：MVP 边界与模块分层

状态：已更新

## 背景

当前 MVP 只围绕 ZZZ box / tier 规划闭环，不再扩展到其他采集路线或完整应用壳。

## 约束条件

- 输入必须来自公开 meta、本地 box 图或脱敏 roster JSON。
- 输出必须是可复核 JSON/Markdown。
- 不写正式数据库。
- 不提交本地运行产物。
- 不输出确定抽卡结论。

## 模块边界

| 模块 | 文件 | 责任 |
| --- | --- | --- |
| 公开 meta | `prepare_zzz_meta_snapshot.py` | 读取公开 Prydwen tier 与高难统计 |
| box roster | `extract_zzz_box_roster.py` | 从本地 box 图生成候选 roster |
| 价值报告 | `build_agent_value_cards.py` | 生成账号内价值、配队、培养和未来观察 |
| pipeline | `run_zzz_box_value_pipeline.py` | 串联 meta、roster 和价值报告 |
| CLI | `miho_probe_cli.py` | 提供 `meta`、`box-roster`、`box-value`、`status` |

## 候选方案

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| 单 pipeline 脚本 | 简单 | 难测试、难复用 | 不选 |
| 多模块 CLI | 边界清晰、可测试 | 文件稍多 | 当前采用 |
| 完整应用服务层 | 接近最终形态 | 当前过重 | 暂缓 |

## 推荐结论

采用多模块 CLI。每个模块保留独立函数和单元测试，pipeline 只负责编排。

## 原型阶段建议

- 优先改 `build_agent_value_cards.py` 的评分和报告。
- 优先补 `test_agent_value_cards.py` 的行为测试。
- `status` 只做只读检查，不自动执行下一步。

## 最终产品建议

当报告结构稳定后，再把 JSON/Markdown 输出升级为正式应用 DTO 和本地存储模型。

## 不选择其他方案的原因

- 单脚本容易重新变成不可维护工具。
- 现在做完整应用服务层会把数据模型过早固定。

## 后续验证任务

1. 为未来观察增加置信度。
2. 为培养建议增加资源成本分类。
3. 为队伍候选增加“为什么不是另一队”的解释。
4. 为 status 增加更清晰的下一步提示。

## 风险清单

- 公开 meta 缺字段或字段改名。
- roster 图识别结果未经人工确认。
- 当前没有装备、技能、驱动盘毕业度，报告只能做中等置信度规划。
