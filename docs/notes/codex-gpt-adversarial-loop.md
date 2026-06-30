# Codex/GPT 对抗协作协议

目标：让右侧 GPT 负责方案审视、风险发现和验收口径收敛；Codex 负责读仓库、改代码、跑测试、提交和推送。不要每轮重新探索浏览器、页面结构或对话历史。

## 禁止重复探索

默认不再让 Codex 读取右侧 GPT 的长历史，也不再临时摸索输入框、页面结构或复制方式。每轮只做这四步：

1. Codex 用本地仓库、测试结果和当前用户目标生成审查包。
2. 工具把审查包复制到剪贴板，用户完整粘贴给右侧 GPT；剪贴板不可用时，使用 `data/probes/demo/gpt_review_prompt.md`。
3. 用户把 GPT 的 `Findings / Risks / Next experiment / Acceptance` 回复贴回当前线程。
4. Codex 只根据贴回来的结构化结论、本地代码和命令输出实现、验证、提交、推送。

如果右侧 GPT 要求“再看历史”“再浏览页面”“让 Codex 去读聊天记录”，视为无效建议；让它只基于审查包给出风险排序。

## 右侧 GPT 发送规则

优先让用户手动把审查包发给右侧 GPT；这是最稳、最省 token 的路径。

如果用户明确要求 Codex 直接发送，只允许一次固定动作，不再反复探索页面：

1. 先生成短审查包，不超过 1200 字。
2. 用浏览器剪贴板写入审查包。
3. 只定位当前会话底部的 `与 ChatGPT 聊天` 输入框。
4. 粘贴后点击 `发送提示`。
5. 如果发送或截图超时一次，不继续循环试探；改为告诉用户“审查包已生成，请手动粘贴”，然后继续本地可推进工作。

不要为了右侧 GPT 做这些事：

- 不读取长历史。
- 不截图反复定位。
- 不翻聊天记录。
- 不把浏览器自动化问题当主线 blocker。
- 不在同一轮里尝试三种以上输入方式。

## 固定分工

| 角色 | 负责 | 不负责 |
| --- | --- | --- |
| GPT | 提方案、挑漏洞、指出验收缺口、给下一轮最小实验 | 改代码、跑本地命令、判断 Git 状态 |
| Codex | 实现代码、修测试、生成本地报告、提交推送、反馈真实结果 | 把 GPT 的建议当无条件正确、跳过本地验证 |

## 给 GPT 的固定输入包

优先用工具生成，不要手写长上下文：

```powershell
dist\MihoProbe.exe gpt-review `
  --focus "本轮要推进的用户可见结果" `
  --evidence "关键命令结果，最多 5 行" `
  --changed-file "path/to/file.py: 改了什么" `
  --copy
```

未构建 `dist\MihoProbe.exe` 时，使用 `python tools/probes/build_gpt_review_prompt.py`，参数保持一致。

每次只发一个紧凑包，不要贴长日志。工具会自动带上固定约束和当前 `git status --short`；需要手写时使用同样结构：

```text
目标：
- 本轮要推进的用户可见结果。

当前证据：
- 关键命令结果，最多 5 行。
- 关键截图/页面现象，最多 3 点。
- 当前失败字段或测试名。

已改文件：
- path A：改了什么。
- path B：改了什么。

请审：
- 这个方案有没有方向性问题？
- 有没有会污染数据/绕过人工确认/误判通过率的风险？
- 下一步最小可验证实验是什么？

约束：
- 不换 OCR 引擎。
- 不 UIA。
- 不初始化 Tauri。
- 不读 cookie/token。
- 不提交 data/probes、真实图片、UID、OCR 原始结果。
```

## GPT 回包格式

要求 GPT 用这个格式回复，方便 Codex 直接执行：

```text
Findings：
- [P0/P1/P2] 问题、影响、证据。

Risks：
- 可能误伤或需要守住的边界。

Next experiment：
- 一条最小命令或一个最小改动。

Acceptance：
- 通过/失败应该看哪条硬证据。
```

## Codex 执行规则

- 先用本地仓库和命令结果确认 GPT 的说法。
- 只实现和当前目标直接相关的改动。
- 每次改动后跑对应测试；风险大时跑全量 `python -m unittest discover tests`。
- 提交前检查 `git status --short`，只 stage 本轮相关文件。
- 提交前扫描敏感词和禁止产物。
- 推送后把 commit id、测试命令、剩余未跟踪文件反馈给用户。

## 什么时候需要 GPT

需要：

- 方案方向分歧。
- Dashboard/README 等用户理解问题，需要另一视角挑刺。
- 解析规则通过率卡住，需要风险排序。
- 验收口径容易自欺，需要外部审稿。

不需要：

- 单个测试红了。
- 明确的 copy/UI 文案调整。
- 机械重命名。
- 本地命令失败但原因已经清楚。

## 本轮常用口径

- Demo 体验：`scripts/run_miho_demo.bat`
- Fresh OCR：`scripts/run_miho_demo.bat --fresh`
- GPT 审查包：`dist\MihoProbe.exe gpt-review --focus "..."`
- P0.9 准确率：`python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json`
- 全量回归：`python -m unittest discover tests`

这份协议本身不改变项目架构，只约束协作方式，避免把 token 花在重复摸索对话和工具入口上。
