# Miho Endgame（终局数据中心）

这是 HSR / ZZZ 终局数据导出、Box 管理、可视化和报告生成工具。正式 Windows 运行链为 Tauri + Rust，不要求用户安装 Python。

普通用户请直接阅读 [傻瓜版中文使用说明](docs/用户使用说明.md)。里面包含安装等待、第一次启动、导出、Box、报告、结果目录、每日更新和常见故障。

## 重要提醒

- 首次安装会在线下载并验证两款游戏的数据，通常需要 3–10 分钟；安装窗口可能暂时不刷新，不要强行关闭。
- 当前内部发布包没有 Authenticode 签名，Windows 可能显示 SmartScreen 警告。只使用项目交付的精确文件，并先核对交付的 SHA-256。
- 不要按文件时间、名称中的“最新”或 `bundle` 目录里的排列自行挑安装包。只认维护者本次最终交付块给出的**绝对路径、完整 content-addressed 文件名和 SHA-256**；三者缺一或不一致就不要运行。历史 verification/失败候选即使时间较新也不是交付包。
- 当前发布产物、来源提交、SHA-256 和签名状态的唯一事实源是 `target/release/bundle/miho-release-artifacts-v1.json`。
- 卸载会移除程序和每日任务，但保留 `%APPDATA%\com.miho.endgame` 中的工作区数据。

## 开发与发布

项目目标、完成证据和剩余边界见 [PROJECT.md](PROJECT.md)，发布事务与门禁见 [docs/release-contract.md](docs/release-contract.md)。每个新的 tracked 提交都必须从 clean HEAD 重新构建，旧 EXE 不能自动代表新源码。
