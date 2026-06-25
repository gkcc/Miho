# ADR-0003 本地数据模型与快照策略

状态：草案  
日期：2026-06-26（Asia/Shanghai）  
前置决策：ADR-0001 已采纳 MVP 主路线；ADR-0002 已定义 MVP 边界与模块分层。

## 背景

项目需要在不接入真实账号、不读取真实 cookie/token、不做自动登录的前提下，先跑通本地可信数据闭环。MVP 的输入来自 mock 数据或用户手动 JSON 导入，输出包括本地标准化模型、SQLite 快照、快照 diff、终局目标缺口、培养优先级、体力/开拓力规划和卡片化 Dashboard mock。

本 ADR 定义本地数据模型和快照策略的草案，目标是让后续 Rust domain model、SQLite schema、importers、planner、reports 和 fixtures 有共同语言。本文档不是数据库迁移脚本，不是业务代码，也不代表最终 schema 已锁定。

## 决策

本地数据模型采用“来源记录与标准化模型分离”的策略：

- SourceRecord 保存来源类型、导入时间、来源摘要、脱敏后的 raw 片段或引用。
- 标准化模型保存可 diff、可规划、可展示的结构化字段。
- 每次导入都生成 Snapshot。
- Snapshot 支持 partial success：单个角色、装备或字段解析失败不会导致全量导入失败。
- Diff 只比较标准化结构化字段，不比较 raw 文本、HTML、截图、cookie/token 或未确认 OCR 内容。
- 隐私脱敏是导入、存储、报告、fixture 和日志的默认前置动作。

MVP 阶段先用 JSON 草案表达模型，不急于锁死完整 SQLite 表结构。SQLite schema 应在 mock JSON、snapshot 和 diff 输出稳定后再单独设计。

## 游戏维度

MVP 至少覆盖两个游戏维度：

- `zzz`：《绝区零》
- `hsr`：《崩坏：星穹铁道》

游戏维度用于：

- 区分账号与角色所属游戏。
- 区分装备类型：绝区零是音擎和驱动盘；星铁是光锥、遗器和位面饰品。
- 区分技能体系：绝区零是普通攻击、闪避、支援、特殊技、连携技、核心技等；星铁是普攻、战技、终结技、天赋、秘技、行迹节点等。
- 区分终局目标：绝区零包括式舆防卫战、危局强袭战等；星铁包括混沌回忆、虚构叙事、末日幻影等。

## 核心实体草案

### GameAccount

表示一个本地游戏账号视图，不保存真实登录凭据。

建议字段：

- `local_account_id`：本地生成 ID，不等同于官方 account_id。
- `game`：`zzz` 或 `hsr`。
- `display_name`：用户手动填写或 mock 名称。
- `region`：区服标识，例如 `cn`、`global`、`asia`。
- `masked_uid`：脱敏后的 UID，可为空。
- `created_at` / `updated_at`：本地时间。

禁止字段：

- 真实 cookie。
- 真实 token。
- 未脱敏 account_id。
- 登录态文件路径。
- 浏览器 profile 路径。

### Snapshot

表示一次导入或一次本地状态确认后的结构化快照。

建议字段：

- `snapshot_id`
- `local_account_id`
- `game`
- `source_record_id`
- `created_at`
- `import_status`：`success`、`partial_success`、`failed`
- `schema_version`
- `character_count`
- `warnings`
- `errors`

### Character

表示角色静态或半静态身份。

建议字段：

- `character_id`
- `game`
- `name`
- `rarity`
- `element`
- `path_or_specialty`：星铁命途或绝区零特性。
- `faction`
- `roles`：如主 C、副 C、辅助、生存、击破、异常等。

### CharacterBuildSnapshot

表示某个 snapshot 中某个角色的练度状态。

建议字段：

- `snapshot_id`
- `character_id`
- `owned`
- `level`
- `ascension_or_promotion`
- `eidolon_or_mindscape`
- `equipment`
- `skills_or_traces`
- `artifacts_or_drive_discs`
- `key_stats`
- `notes`

### Equipment

表示武器类装备。

绝区零对应音擎，星铁对应光锥。

建议字段：

- `equipment_id`
- `game`
- `type`：`w_engine` 或 `light_cone`
- `name`
- `level`
- `rank`：精炼、叠影、改装等抽象等级。
- `rarity`
- `equipped_by`

### SkillOrTrace

表示技能或行迹节点。

建议字段：

- `skill_id`
- `game`
- `character_id`
- `kind`
- `name`
- `level`
- `unlocked`
- `is_key_node`

### ArtifactOrDriveDisc

表示遗器、位面饰品或驱动盘。

建议字段：

- `piece_id`
- `game`
- `kind`：`drive_disc`、`relic`、`planar_ornament`
- `slot`
- `set_name`
- `level`
- `main_stat`
- `sub_stats`
- `equipped_by`
- `quality_note`

### EndgameGoal

表示一个终局目标配置。

建议字段：

- `goal_id`
- `game`
- `activity_name`
- `period`
- `target_tier`
- `required_teams`
- `mechanic_tags`
- `weakness_tags`
- `recommended_team_templates`
- `completion_status`
- `confidence`

### TeamTemplate

表示一个目标队伍模板，不要求绑定固定角色。

建议字段：

- `template_id`
- `game`
- `name`
- `roles_required`
- `preferred_characters`
- `allowed_substitutes`
- `mechanic_tags`
- `conflict_notes`

### BuildGap

表示当前 box 面向某个目标的缺口。

建议字段：

- `gap_id`
- `snapshot_id`
- `goal_id`
- `character_id`
- `gap_type`
- `severity`
- `reason`
- `recommended_action`
- `estimated_days`
- `confidence`

### PlanItem

表示一条培养或规划建议。

建议字段：

- `plan_item_id`
- `snapshot_id`
- `game`
- `priority`
- `target_type`
- `target_id`
- `action`
- `expected_benefit`
- `resource_cost_note`
- `estimated_days`
- `depends_on`
- `confidence`

### SourceRecord

表示导入来源和脱敏后的原始记录引用。

建议字段：

- `source_record_id`
- `source_type`：`mock_json`、`manual_json`、`manual_csv`、`saved_html`、`ocr_reviewed`
- `game`
- `imported_at`
- `redaction_status`
- `raw_ref`
- `raw_hash`
- `warnings`
- `errors`

禁止字段：

- 明文 cookie。
- 明文 token。
- 明文 stoken / ltoken。
- 明文 account_id / uid。
- 浏览器 profile 或 APP profile 真实路径。

## 快照策略

- 每次导入生成 snapshot，即使导入结果是 partial success。
- 原始数据与标准化数据分离。
- raw 数据默认脱敏；未脱敏 raw 不允许进入 SQLite、fixture、日志或报告。
- snapshot 可 diff，可比较任意两个同游戏、同本地账号的 snapshot。
- diff 只比较结构化字段，例如角色等级、装备等级、技能/行迹等级、驱动盘/遗器主词条、目标完成状态。
- diff 不比较 raw HTML、截图、OCR 原文、cookie/token 或未确认字段。
- 不因为单角色解析失败导致全量失败。
- 支持 partial success：导入结果必须返回成功项、失败项、警告、错误和可解释原因。
- 标准化模型必须保留 `source_record_id` 或 `snapshot_id` 追溯来源，但不暴露敏感字段。
- 每个 snapshot 记录 `schema_version`，为后续迁移和回放测试留出口。
- 失败项可以进入 SourceRecord 的错误列表，但不能污染正式 CharacterBuildSnapshot。

建议的导入流程：

```text
manual file/mock fixture
  -> importer parse
  -> privacy/redaction
  -> normalize to domain model
  -> validate
  -> create SourceRecord
  -> create Snapshot
  -> persist standardized records
  -> generate warnings/errors
```

建议的 diff 流程：

```text
snapshot A
  + snapshot B
  -> load standardized records
  -> compare structured fields
  -> emit diff events
  -> reports/planner consume diff summary
```

## mock JSON 格式草案

以下示例只用于格式讨论，不包含真实账号、真实 uid、cookie/token 或可识别个人信息。

```json
{
  "schema_version": "miyo.mock.v0",
  "source": {
    "source_type": "mock_json",
    "created_at": "2026-06-26T00:00:00+08:00",
    "redaction_status": "not_required_mock"
  },
  "accounts": [
    {
      "local_account_id": "mock-zzz-main",
      "game": "zzz",
      "display_name": "ZZZ Mock Account",
      "region": "cn",
      "masked_uid": "uid_***_zzz",
      "characters": [
        {
          "character_id": "zzz_ellen",
          "name": "艾莲",
          "owned": true,
          "level": 60,
          "rarity": "S",
          "element": "ice",
          "path_or_specialty": "attack",
          "faction": "维多利亚家政",
          "roles": ["dps"],
          "eidolon_or_mindscape": 0,
          "equipment": {
            "type": "w_engine",
            "name": "深海访客",
            "level": 60,
            "rank": 1,
            "rarity": "S"
          },
          "skills_or_traces": [
            { "kind": "basic", "name": "普通攻击", "level": 11, "unlocked": true, "is_key_node": true },
            { "kind": "core", "name": "核心技", "level": 6, "unlocked": true, "is_key_node": true }
          ],
          "artifacts_or_drive_discs": [
            {
              "kind": "drive_disc",
              "slot": 4,
              "set_name": "极地重金属",
              "level": 15,
              "main_stat": "crit_rate",
              "sub_stats": { "crit_damage": 18.7, "atk_percent": 9.9 }
            }
          ],
          "key_stats": {
            "atk": 2800,
            "crit_rate": 72.5,
            "crit_damage": 148.2
          }
        },
        {
          "character_id": "zzz_soukaku",
          "name": "苍角",
          "owned": true,
          "level": 50,
          "rarity": "A",
          "element": "ice",
          "path_or_specialty": "support",
          "faction": "对空六课",
          "roles": ["support"],
          "eidolon_or_mindscape": 4,
          "equipment": {
            "type": "w_engine",
            "name": "含羞恶面",
            "level": 50,
            "rank": 5,
            "rarity": "A"
          },
          "skills_or_traces": [
            { "kind": "special", "name": "特殊技", "level": 9, "unlocked": true, "is_key_node": true },
            { "kind": "core", "name": "核心技", "level": 4, "unlocked": true, "is_key_node": true }
          ],
          "artifacts_or_drive_discs": [],
          "key_stats": {
            "atk": 2100,
            "energy_regen": 120.0
          }
        }
      ]
    },
    {
      "local_account_id": "mock-hsr-main",
      "game": "hsr",
      "display_name": "HSR Mock Account",
      "region": "cn",
      "masked_uid": "uid_***_hsr",
      "characters": [
        {
          "character_id": "hsr_firefly",
          "name": "流萤",
          "owned": true,
          "level": 80,
          "rarity": "5",
          "element": "fire",
          "path_or_specialty": "destruction",
          "faction": "星核猎手",
          "roles": ["dps", "break"],
          "eidolon_or_mindscape": 0,
          "equipment": {
            "type": "light_cone",
            "name": "梦应归于何处",
            "level": 80,
            "rank": 1,
            "rarity": "5"
          },
          "skills_or_traces": [
            { "kind": "skill", "name": "战技", "level": 10, "unlocked": true, "is_key_node": true },
            { "kind": "trace", "name": "关键行迹", "level": 1, "unlocked": true, "is_key_node": true }
          ],
          "artifacts_or_drive_discs": [
            {
              "kind": "relic",
              "slot": "body",
              "set_name": "荡除蠹灾的铁骑",
              "level": 15,
              "main_stat": "atk_percent",
              "sub_stats": { "break_effect": 18.1, "speed": 4 }
            }
          ],
          "key_stats": {
            "break_effect": 245.0,
            "speed": 154,
            "atk": 2600
          }
        },
        {
          "character_id": "hsr_ruanmei",
          "name": "阮·梅",
          "owned": true,
          "level": 80,
          "rarity": "5",
          "element": "ice",
          "path_or_specialty": "harmony",
          "faction": "天才俱乐部",
          "roles": ["support"],
          "eidolon_or_mindscape": 0,
          "equipment": {
            "type": "light_cone",
            "name": "记忆中的模样",
            "level": 80,
            "rank": 5,
            "rarity": "4"
          },
          "skills_or_traces": [
            { "kind": "ultimate", "name": "终结技", "level": 10, "unlocked": true, "is_key_node": true },
            { "kind": "trace", "name": "关键行迹", "level": 1, "unlocked": true, "is_key_node": true }
          ],
          "artifacts_or_drive_discs": [],
          "key_stats": {
            "break_effect": 180.0,
            "speed": 145
          }
        }
      ]
    }
  ],
  "endgame_goals": [
    {
      "goal_id": "goal-hsr-apocalyptic-shadow-mock",
      "game": "hsr",
      "activity_name": "末日幻影",
      "period": "mock-period-2026-06",
      "target_tier": "full_clear",
      "required_teams": 2,
      "mechanic_tags": ["break", "burst_window"],
      "weakness_tags": ["fire", "ice"],
      "recommended_team_templates": ["template-break-core"],
      "completion_status": "not_started",
      "confidence": "medium"
    }
  ],
  "plan_items": [
    {
      "plan_item_id": "plan-001",
      "game": "hsr",
      "priority": 1,
      "target_type": "character",
      "target_id": "hsr_firefly",
      "action": "补齐关键行迹并确认击破绳主词条",
      "expected_benefit": "提高末日幻影击破队可用线",
      "resource_cost_note": "预计 3-5 天开拓力",
      "estimated_days": 4,
      "depends_on": ["goal-hsr-apocalyptic-shadow-mock"],
      "confidence": "medium"
    }
  ]
}
```

## diff 规则草案

Diff 输出应按事件或条目表达，每条 diff 至少包含：

- `diff_type`
- `game`
- `snapshot_from`
- `snapshot_to`
- `target_id`
- `field`
- `before`
- `after`
- `severity`
- `summary`

MVP 至少覆盖：

- 新增角色：上一 snapshot 未拥有，当前 snapshot 拥有。
- 等级变化：角色等级、突破/晋阶阶段变化。
- 武器/光锥变化：装备名称、等级、rank、rarity、装备归属变化。
- 技能/行迹变化：技能等级、关键节点解锁状态变化。
- 驱动盘/遗器变化：套装、槽位、主词条、等级、关键副词条变化。
- 关键属性变化：攻击、暴击、暴伤、速度、击破特攻、能量回复等 key_stats 变化。
- 目标完成状态变化：终局目标从未开始、进行中、已完成、放弃等状态变化。

建议 diff 类型：

- `character_added`
- `character_removed_or_unowned`
- `character_level_changed`
- `equipment_changed`
- `equipment_level_changed`
- `skill_or_trace_changed`
- `artifact_or_drive_disc_changed`
- `key_stat_changed`
- `endgame_goal_status_changed`
- `source_warning_added`
- `parse_error_added`

Diff 不做：

- 不比较 raw HTML。
- 不比较截图或 OCR 原始文本。
- 不比较真实 uid、cookie/token 或账号标识。
- 不因为缺失副词条评分就阻塞角色级 diff。
- 不把 planner 分数变化伪装成事实字段变化；planner 输出应单独记录。

## 隐私字段和脱敏策略

以下字段均视为敏感字段：

- cookie
- token
- stoken
- ltoken
- account_id
- uid
- 手机号
- 邮箱
- 设备标识
- 浏览器 profile
- APP profile
- 登录态文件
- 本地 APP 数据目录
- 原始请求头
- 原始响应中包含的账号标识

脱敏策略：

- 默认不保存真实 cookie/token/stoken/ltoken。
- 默认不保存明文 account_id/uid；如展示需要，只允许保存 `masked_uid`。
- 手机号只允许保存掩码，例如 `138****0000`；MVP 默认不需要保存。
- 邮箱只允许保存掩码，例如 `u***@example.com`；MVP 默认不需要保存。
- 设备标识不保存；如必须调试，只允许写入不可逆 hash，且不得进入 Git。
- 浏览器 profile 和 APP profile 不保存真实路径。
- raw 数据进入 SourceRecord 前必须经过 privacy/redaction。
- fixture 必须只使用 mock 或脱敏数据。
- 日志默认不记录原始导入内容，只记录 source type、schema version、导入状态、错误码和脱敏摘要。
- 报告和 Dashboard 只展示标准化字段和脱敏名称。
- 任何未通过脱敏校验的来源记录不得进入 SQLite snapshot。

建议脱敏示例：

```text
uid: 123456789 -> uid_***_6789
account_id: 987654321 -> account_***_4321
email: user@example.com -> u***@example.com
phone: 13800000000 -> 138****0000
cookie: any value -> [REDACTED_COOKIE]
token: any value -> [REDACTED_TOKEN]
browser profile path -> [REDACTED_BROWSER_PROFILE]
app profile path -> [REDACTED_APP_PROFILE]
```

## 后续任务

1. 基于本 ADR 拆出更正式的 mock JSON schema 文档。
2. 定义 Rust domain model 的最小类型集合，但在开始前先确认不初始化完整工程。
3. 设计 SQLite schema 草案：accounts、source_records、snapshots、characters、build_snapshots、equipment、skills_or_traces、artifacts_or_drive_discs、endgame_goals、team_templates、build_gaps、plan_items。
4. 定义 snapshot diff 输出 JSON 草案和报告 DTO 草案。
5. 定义 partial success 错误模型，包括 parse warning、parse error、validation error、redaction error。
6. 为 privacy/redaction 制定测试 fixture 清单，确保敏感字段不会进入日志、报告和 snapshot。
7. 设计 P0 Dashboard mock 所需的数据 DTO，保持 UI 不直接接触 storage 和敏感字段。
8. 在进入真实数据导入前，单独写数据采集 ADR，明确用户授权、限流、缓存、脱敏和失败恢复策略。
