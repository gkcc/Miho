# HSR Endgame Export Report

- 导出时间: 2026-07-04T23:56:16
- from_date / to_date: 2026-01-04 / 2026-07-04
- 数据源: Hugging Face dataset `LvlUrArti/MocDataProcessed`; Prydwen visible page data when available
- 成功读取的 snapshot 数: 9

## 各模式 snapshot 覆盖情况

- 混沌回忆 (moc): 9
- 虚构叙事 (pf): 9
- 末日幻影 (as): 9
- 异相仲裁 (aa): 9

## 表行数

- 角色表行数: 3424
- 队伍 raw 行数: 105680
- 队伍有序去重后行数: 44522
- 队伍无序去重后行数: 44340
- raw -> 无序去重移除重复行数: 61340
- 未解析角色数量: 0
- 官方中文名补全数量: 87
- 简洁视图: `overview.csv`, `latest_usage_cn.csv`, `top_teams_latest.csv`（四人无序去重，每模式 Top 100），Excel 同名 sheet
- Prydwen 当前 T 榜行数: 279
- Prydwen T 榜本地历史行数: 279
- Prydwen changelog 日期段数: 7
- T0-T2 出场率趋势行数: 1866
- T0-T2 趋势图数量: 12
- 交互可视化入口: `visualizer/index.html`（含异相仲裁本地趋势与本地 Box 维护页）

## 异相仲裁拆分情况

- 本次未取得骑士关卡 / 王棋关卡角色出场率拆分数据。
- AA 数据已按 `all_bosses` / `全 Boss / 未拆分` 标记。

## Warning 列表

- 3.8.2: config is in requested date range but no dataset directory was listed
- 3.8.3: config is in requested date range but no dataset directory was listed
- 3.8.4: config is in requested date range but no dataset directory was listed

## Error 列表

- 无
