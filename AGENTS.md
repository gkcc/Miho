# AGENTS.md

## 项目定位

Miho 当前收敛为一个本地优先的 ZZZ box / tier / 配队 / 培养 / 未来观察工具。

当前主线只做：

1. 读取公开 Prydwen ZZZ tier 与高难统计。
2. 读取用户显式提供的本地官方 ZZZ box 总览图，或读取已脱敏 roster JSON。
3. 生成账号内代理人价值、当前高难配队候选、培养优先级。
4. 输出缺一名角色的观察队，作为未来视和抽取前问题，不输出确定抽卡结论。

最终可以演进为本地桌面应用，但当前仓库不做完整桌面工程初始化。当前成果形态是可验证的 Python CLI、JSON/Markdown 报告和文档。

## 当前阶段

当前阶段是 box/tier 规划主线收敛。

保留入口：

```text
tools/probes/prepare_zzz_meta_snapshot.py
tools/probes/extract_zzz_box_roster.py
tools/probes/build_agent_value_cards.py
tools/probes/run_zzz_box_value_pipeline.py
tools/probes/miho_probe_cli.py
```

保留测试：

```text
tests/test_prepare_zzz_meta_snapshot.py
tests/test_zzz_box_roster_extract.py
tests/test_agent_value_cards.py
tests/test_zzz_box_value_pipeline.py
tests/test_miho_probe_cli.py
```

允许做：

1. 改进公开 meta 快照解析。
2. 改进本地 box roster 识别与脱敏。
3. 改进账号内价值评分、配队排序、培养优先级和未来观察。
4. 改进 CLI、README、方法论文档和测试。
5. 生成或更新 `data/probes/` 下的本地验证输出，但不得提交这些输出。

禁止做：

1. 自动登录任何账号。
2. 读取、处理、保存或提交登录态、账号标识、设备标识或浏览器/APP profile。
3. 抓包、绕过风控、绕过验证码、控制游戏客户端。
4. 把缺失角色观察队当作确定抽卡建议。
5. 把本地图片识别草案直接当作最终 box。
6. 提交 `data/probes/`、`figs/`、真实图片、真实 roster、数据库、本地运行产物。
7. 在未明确需求时初始化完整桌面应用工程。

## 数据来源

当前数据来源分三层：

1. 公开 Prydwen ZZZ 页面和公开统计接口。
2. 用户显式提供的本地官方 ZZZ box 总览图。
3. 用户人工确认后的脱敏 roster JSON。

公开统计只能作为强度、出场、队伍使用和未来观察信号。Appearance rate 不是持有率，也不是抽卡价值。

## 输出原则

报告必须解释：

1. 用了哪些输入文件。
2. 当前 box 内哪些代理人值得优先看。
3. 哪些队伍是当前已拥有成员可组成的候选。
4. 哪些角色只是低成本过渡或不建议为过关强拉。
5. 哪些缺失角色只属于未来观察。
6. 置信度和限制条件。

禁止输出：

1. “必抽”式结论。
2. 不看当前 box 的抽取建议。
3. 把社区统计说成官方结论。
4. 把低等级直接等同于低价值。
5. 建议为极限优化无限刷装备。

## 当前验收

常用验收命令：

```powershell
python -m unittest discover tests
python tools/probes/miho_probe_cli.py status
python tools/probes/miho_probe_cli.py box-value --roster-json data\probes\box\zzz_box_roster.json --meta-snapshot data\probes\meta\zzz_prydwen_meta_all_phases.json --output-dir data\probes\value\current
```

实际本机可用文件名可能不同，先用 `status` 查看最新本地 meta、roster 和报告路径。

## 版本控制

每次修改文档或代码并完成验证后，必须同步到远程仓库。

要求：

1. 提交前运行相关测试。
2. 提交前检查 `git status --short --branch`。
3. 不提交 `data/probes/`、`figs/`、真实图片、真实 roster、数据库、`.env` 或本地私有配置。
4. 如果当前目录不是 Git 仓库、未配置远程、没有权限推送，或用户明确要求不推送，最终回复中说明原因。
5. 推送失败必须报告失败原因。

## 修改前说明

每次修改代码或文档前必须说明：

1. 本次要解决的问题。
2. 涉及哪些文件。
3. 是否引入新依赖。
4. 是否改变数据结构。
5. 如何验证。

修改后必须输出：

1. 修改摘要。
2. 测试命令。
3. 已知风险。
4. 后续建议。

## 安全边界

敏感内容包括但不限于：

```text
cookie
token
stoken
ltoken
account_id
uid
手机号
邮箱
设备标识
登录态文件
浏览器 profile
APP profile
本地数据库
真实图片
真实 roster
```

禁止提交：

```gitignore
data/probes/
data/raw/
data/processed/
figs/
*.sqlite
*.db
configs/account.yaml
.env
.env.*
cookies.json
tokens.json
browser-profile/
app-profile/
```

## 文档维护

保留并维护：

```text
README.md
tools/probes/README.md
docs/notes/zzz-agent-value-method.md
docs/spikes/0002-prydwen-zzz-agent-value-feasibility.md
docs/adr/0001-tech-stack-selection.md
docs/adr/0002-mvp-boundary-and-module-layering.md
docs/adr/0003-local-data-model-and-snapshot-strategy.md
```

这些文档必须围绕当前 box/tier 主线，不再引导到已删除的旧工作流。
