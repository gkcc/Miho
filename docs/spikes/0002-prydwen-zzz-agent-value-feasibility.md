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

1. 新增 `build_agent_value_cards.py`：
   - 输入 accepted roster；
   - 输入 `zzz_prydwen_meta_snapshot.json`；
   - 输出 box 内代理人现实价值、潜力价值、推荐状态、证据链。

2. 新增 box roster 识别草案：
   - 将官方 box 图转为脱敏 roster JSON；
   - 不保存明文 UID、昵称、二维码；
   - 人工确认前不进入 accepted roster。

3. 新增配队匹配：
   - 从公开 team usage 生成候选队伍；
   - 只保留当前 box 已拥有角色；
   - 对式舆/危局分别评分；
   - 做多队冲突分配。

4. 新增 banner snapshot：
   - 只影响潜力价值；
   - 不影响当前可用队伍；
   - 来源冲突时进入人工复核。
