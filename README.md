# Miho

本项目是一个本地优先的游戏练度跟踪与规划桌面应用原型。当前阶段只做本地 probe / demo：验证米游社官方分享图能否稳定解析、人工确认后能否形成本地 box、再生成高难配队和培养建议。

现在还不是正式桌面软件：不初始化完整 Tauri 工程，不自动登录，不读取 cookie/token，不写正式数据库。

## 现在能做什么

- 从官方分享图或已有 parsed JSON 生成本地 Dashboard。
- 用 expected diff 回放 3 张以上官方分享图，检查解析准确率。
- 把解析结果放进人工复核区，确认后再进入本地 accepted roster。
- 基于本地 roster、目标配置和本地 tier snapshot 生成候选行动卡、队伍卡、今日简报。
- 在 Dashboard 中展示“现在能不能行动、卡在哪里、下一步点哪个复核页”。

## 现在不能做什么

- 不能自动登录米游社。
- 不能读取或保存 cookie、token、stoken、ltoken。
- 不能控制游戏客户端。
- 不能把 OCR 结果直接写入正式数据库。
- 不能把真实图片、UID、OCR 原始结果或 `data/probes/` 产物提交到 Git。
- 不能把 tier list 或高难出场率当作联网实时数据，当前只支持本地快照。

## 体验入口

第一次使用，先装桌面快捷方式：

```powershell
scripts/install_miho_demo_shortcut.bat
```

它会在桌面创建两个入口：

- `Miho Demo`：优先秒开已经生成的 Dashboard；如果没有缓存，才会跑一次 OCR。
- `Miho Demo Fresh OCR`：重新识别 `figs/` 下的官方分享图，完成后打开 Dashboard。
- `MihoProbe CLI`：如果已经构建 `dist/MihoProbe.exe`，会打开本地 EXE 命令壳说明。

这只是当前 probe 阶段的一键入口，不是正式 Tauri 桌面应用，也不会自动登录、读取 token 或写正式数据库。

可选：构建本地 EXE 命令壳：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_miho_probe_exe.ps1
scripts/install_miho_demo_shortcut.bat
```

也可以直接从命令行打开当前本地 demo：

```powershell
scripts/run_miho_demo.bat
```

只打开已经生成的 Dashboard，不重新 OCR：

```powershell
scripts/run_miho_demo.bat --open-only
```

重新跑官方分享图 OCR：

```powershell
scripts/run_miho_demo.bat --fresh
```

如果 `--fresh` 等很久，先看命令行是否打印了 `[Miho Demo] OCR 1/N...`。PaddleOCR 第一次加载模型会慢；普通验收优先用 `--open-only` 看现有 Dashboard。

## 准确率验收

P0.9 解析准确率不要扫整个历史目录，必须用 manifest：

```powershell
python tools/probes/run_export_replay_batch.py --manifest data/probes/replay_manifest.json
```

通过口径：

- 3 张图平均 pass rate 达标。
- 每张图不能低于门槛。
- 不允许 character / equipment 全错还通过。
- 不允许 drive disc 主副词条全缺还通过。

生成单张分享图解析验收页：

```powershell
python tools/probes/review_export_image.py --image "C:\path\to\share.jpg" --engine paddle --lang chi_sim+eng --write-crops --open
```

更多 probe 命令放在 [tools/probes/README.md](tools/probes/README.md)。

## Codex / GPT 对抗审查

需要右侧 GPT 审方案时，不要重新摸索对话流程，直接生成固定审查包：

```powershell
python tools/probes/build_gpt_review_prompt.py `
  --focus "本轮要推进的用户可见结果" `
  --evidence "关键命令或页面现象" `
  --changed-file "path/to/file.py: 改了什么"
```

协议说明见 [docs/notes/codex-gpt-adversarial-loop.md](docs/notes/codex-gpt-adversarial-loop.md)。

## 本地 tier snapshot

本地 tier snapshot 只作为“保值/高优先级”弱信号，不是抽卡建议。示例：

```json
{
  "source": {
    "name": "manual tier snapshot",
    "source_type": "manual",
    "source_ref": "local",
    "period": "2026-06",
    "captured_at": "2026-06-29T00:00:00+08:00",
    "content_sha256": "local-source-content-sha256",
    "trust_level": "high"
  },
  "entries": [
    {
      "character": "星见雅",
      "tier": "S",
      "retention_score": 0.9,
      "usage_rate": "40%",
      "trend": "stable",
      "modes": ["危局强袭战"],
      "value_tags": ["high_retention"]
    }
  ]
}
```

运行 demo 时可传入本地 tier 快照：

```powershell
python tools/probes/run_demo_pipeline.py `
  --parsed-dir data/probes/parsed `
  --latest-only `
  --tier-snapshot data/probes/tier/zzz_tier_snapshot.json `
  --tier-stale-days 60 `
  --open
```

## 文档入口

- 技术栈与边界：[docs/adr/0001-tech-stack-selection.md](docs/adr/0001-tech-stack-selection.md)、[docs/adr/0002-mvp-boundary-and-module-layering.md](docs/adr/0002-mvp-boundary-and-module-layering.md)、[docs/adr/0003-local-data-model-and-snapshot-strategy.md](docs/adr/0003-local-data-model-and-snapshot-strategy.md)
- 米游社 APP 探针边界：[docs/spikes/0001-miyoushe-app-feasibility.md](docs/spikes/0001-miyoushe-app-feasibility.md)
- 分享图解析结果记录：[docs/notes/share-image-parsing-result.md](docs/notes/share-image-parsing-result.md)
- Codex/GPT 对抗协作协议：[docs/notes/codex-gpt-adversarial-loop.md](docs/notes/codex-gpt-adversarial-loop.md)

## 安全边界

永远不要提交：

- `data/probes/` 里的真实探针产物。
- 真实分享图、UID、账号标识。
- OCR 原始结果、登录态文件、APP profile、浏览器 profile。
- cookie、token、stoken、ltoken、`.env`、数据库文件。

当前仓库只提交代码、测试、文档和脱敏 mock。
