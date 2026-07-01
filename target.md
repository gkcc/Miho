# 当前目标：ZZZ box / tier 规划工具

## 当前状态

- 旧工作流已从代码、脚本、README、测试和主要文档中移除。
- 当前保留主线是：公开 Prydwen meta + 本地 box roster + 账号内价值报告。
- 当前可用入口：
  - `tools/probes/prepare_zzz_meta_snapshot.py`
  - `tools/probes/extract_zzz_box_roster.py`
  - `tools/probes/build_agent_value_cards.py`
  - `tools/probes/run_zzz_box_value_pipeline.py`
  - `tools/probes/miho_probe_cli.py`

## 下一阶段目标

把现有报告继续打磨成“打开就知道该练谁、用哪队、未来缺谁”的工具。

优先级：

1. 改善 `agent_value_cards.md` 的可读性，让一屏结论更像规划报告。
2. 增强培养优先级：区分当前可用、低等级高价值、过渡角色、不建议投入。
3. 增强配队建议：按式舆防卫战、危局强袭战分别解释推荐原因。
4. 增强未来观察：缺一名角色的队伍要说明缺谁、解决什么队伍问题、置信度是多少。
5. 增强 CLI 验收：`status` 要更明确告诉用户下一步该跑什么。

## 当前不做

- 不初始化完整桌面应用工程。
- 不做账号自动化。
- 不读取登录态、账号标识或本地 profile。
- 不提交 `data/probes/`、`figs/`、真实图片、真实 roster、数据库或本地运行产物。
- 不输出确定抽卡结论。

## 验收命令

```powershell
python -m unittest discover tests
python tools/probes/miho_probe_cli.py status
python tools/probes/miho_probe_cli.py box-value --roster-json data\probes\box\zzz_box_roster.json --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json --output-dir data\probes\value\current
```

如果本机 roster 文件名不同，先运行 `status` 看最新路径。
