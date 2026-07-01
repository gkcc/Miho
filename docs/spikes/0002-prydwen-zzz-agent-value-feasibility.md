# Spike 0002: Prydwen ZZZ 公开数据用于 Box 价值判断

## 背景

项目主线从“完整练度工具”收敛到“当前 box 代理人价值判断”。用户希望：

- 读取 Prydwen ZZZ Tier List；
- 读取 Shiyu Defense 与 Deadly Assault 的所有 phase；
- 获取出场率、分数、队伍使用情况；
- 结合官方 box 截图识别结果；
- 给出两个高难的配队建议与 box 内代理人 Tier；
- 形成可解释方法论，减少纯大模型随机性。

## 结论

可行。Prydwen 的 ZZZ 高难页面已经在公开 HTML 中提供 phase 下拉列表，并通过公开接口提供结构化数据：

```text
https://www.prydwen.gg/api/zenless/analytics?phaseId=<id>
```

页面当前暴露的 phase：

- Shiyu Defense: 1, 3, 5, 7, 9, 11, 18, 20
- Deadly Assault: 2, 4, 6, 8, 10, 12, 19, 21

该接口返回：

- `phase`
- `charStats`
- `bangbooStats`
- `teams`
- `characterFilters`

首版原型已新增：

```text
tools/probes/prepare_zzz_meta_snapshot.py
```

后续补充的本地 box 图转 roster 草案：

```text
tools/probes/extract_zzz_box_roster.py
tools/probes/run_zzz_box_value_pipeline.py --box-image ...
```

该草案只读取用户显式传入的米游社官方 box 总览图，输出脱敏 roster JSON / Markdown，不保存 header UID、昵称或原始 OCR 文本块，不读取 cookie/token，不写正式数据库。`needs_review_count > 0` 时只能作为 probe 输入，人工确认前不得进入 accepted roster。`box-status` 已补充 `box_status_review_gate`、`box_status_blocks_accepted_roster`、`box_status_roster_review_markdown`、`box_status_roster_review_markdown_status` 和 `box_status_review_repair_command`，用于区分“可继续生成 probe 价值报告”“该看哪份复核 Markdown”和“是否允许进入 accepted roster”；即使质量检查为 `ok`，如果 paired 复核 Markdown 缺失、旧于 roster JSON 或状态无法确认，也会阻断进入 accepted roster，并给出重新生成复核材料的本地命令。该命令必须手动执行，只覆盖本地 probe JSON/Markdown；如果 roster 源图已不匹配或 roster 本身需要刷新，则优先执行 `box_status_next`。

`box-status` 决策边界固定为：`source_hash_mismatch` / `roster_stale_by_mtime` 先执行 `box_status_next` 刷新 roster；只有 roster 与最新 box 图仍可对齐、但复核 Markdown 缺失/过期/未知时，才允许执行 `box_status_review_repair_command`；若 `box_status_review_repair_command_status=blocked_by_roster_refresh`，不得用旧 roster 的 repair command 覆盖新 box 图对应的探针材料；只要 `box_status_blocks_accepted_roster=True`，就只能继续做 probe 报告或人工复核，不能汇入 accepted roster。

默认输出到：

```text
data/probes/meta/zzz_prydwen_meta_snapshot.json
```

`data/probes/` 已被 `.gitignore` 忽略，不提交真实抓取产物。

## 数据字段

### Tier List

从 Prydwen Tier List 的 Next/RSC payload 中抽取：

- `agent_slug`
- `name`
- `rarity`
- `element`
- `specialty`
- `faction`
- `is_upcoming`
- `is_new`
- `tier_ratings`
  - `category`
  - `rating`
  - `tags`
  - `marks`
  - `has_potential`

### Endgame Phase

每个 phase 保留：

- `phase_id`
- `mode`
- `phase`
- `label`
- `update_date`
- `total_users`
- `source_counts`
- `boss_names`
- `new_agent_slugs`

### Character Stats

每个角色保留：

- `agent_slug`
- `name`
- `current_app_rate`
- `previous_app_rate`
- `current_avg_score`
- `previous_avg_score`
- `app_free`
- `app_dupes`
- `avg_score_free`
- `avg_score_dupes`
- `boss_usage`
- `boss_avg_score`
- `boss_usage_free`
- `boss_usage_dupes`
- `boss_avg_score_free`
- `boss_avg_score_dupes`

### Team Usage

每条队伍保留：

- `scope_key`
- `rank`
- `agent_1_slug`
- `agent_2_slug`
- `agent_3_slug`
- `bangboo_slug`
- `app_rate`
- `avg_score`
- `avg_score_m1plus`

## 验证结果

本地验证命令：

```powershell
python tools/probes/prepare_zzz_meta_snapshot.py --current-only --output data/probes/meta/zzz_prydwen_meta_current.json
```

结果：

```text
tier_entries: 64
shiyu_defense: phases=1 character_rows=55 team_rows=985
deadly_assault: phases=1 character_rows=55 team_rows=772
```

全 phase 验证命令：

```powershell
python tools/probes/prepare_zzz_meta_snapshot.py --output data/probes/meta/zzz_prydwen_meta_all_phases.json
```

结果：

```text
tier_entries: 64
shiyu_defense: phases=8 character_rows=411 team_rows=8104
deadly_assault: phases=8 character_rows=411 team_rows=6971
```

## 边界

允许：

- 读取公开 Prydwen 页面；
- 读取公开 Prydwen analytics API；
- 读取公开 banner 页面作为未来可获得性信号；
- 把公开数据写入本地 `data/probes/meta/`；
- 将归一化后的公开 meta snapshot 作为评分器输入。

禁止：

- 自动登录；
- 读取 cookie/token/stoken/ltoken；
- 抓包；
- 绕过 Cloudflare、验证码、风控或加密；
- 高频请求；
- 将真实用户图片、UID、二维码、`data/probes/` 输出提交 Git；
- 把 appearance rate 当作持有率或抽取价值；
- 把未拥有角色算进当前可用队伍。

## Banner 页

Prydwen 存在 ZZZ banner 页面：

```text
https://www.prydwen.gg/zenless/banners
```

它可以作为：

- 当前/未来 banner 时间线；
- 已公开未来角色；
- 潜力价值和资源规划信号。

它不能作为：

- 当前 box 队伍成员；
- 当前可过关能力；
- 高置信抽取建议。

如果后续接入 banner 数据，必须保存来源与抓取时间，并将信号归类为 `future_availability_signal`。

## 后续任务

1. `build_agent_value_cards.py` 首版 probe 已新增：
   - 输入 accepted roster；
   - 输入 `zzz_prydwen_meta_snapshot.json`；
   - 输出 box 内代理人现实价值、潜力价值、推荐状态、证据链。

2. 继续收口 box roster 识别草案：
   - 增加更多不同分辨率 / 语言 / 缩放 fixture 的人工对照；
   - `box-status` 已输出 `review_gate`，阻止把待复核 roster probe 误当作 accepted roster；
   - 人工确认前仍不得进入 accepted roster，后续如果要自动汇入必须另走 review decision / safe apply 流。

3. 新增配队匹配：
   - 从公开 team usage 生成候选队伍；
   - 只保留当前 box 已拥有角色；
   - 对式舆/危局分别评分；
   - 做多队冲突分配。

4. 新增 banner snapshot：
   - 只影响潜力价值；
   - 不影响当前可用队伍；
   - 来源冲突时进入人工复核。
