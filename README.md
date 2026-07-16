# Miho Endgame（终局数据中心）

这是 HSR / ZZZ 终局数据导出、Box 管理、可视化和报告生成工具。正式 Windows 运行链为 Tauri + Rust，不要求用户安装 Python。

当前本机交付直接更新 Tauri 程序 `D:\Miho Endgame\miho-desktop.exe`。普通使用、Box、导出、报告和结果目录见 [中文使用说明](docs/用户使用说明.md)；其中安装器章节仅保留为历史说明。

## 当前运行方式

- 直接运行 `D:\Miho Endgame\miho-desktop.exe`。
- Box 与工作区数据位于 `%APPDATA%\com.miho.endgame`；替换桌面 EXE 不会删除这些数据。
- 当前产品修复直接构建并替换 Tauri EXE，不要求 NSIS 或安装器。历史 bundle/manifest 不再代表当前桌面程序。

## 开发与交付

项目目标、完成证据和剩余边界见 [PROJECT.md](PROJECT.md)。默认构建命令是 `pnpm run tauri:build`，产物为 `target\release\miho-desktop.exe`，验证后直接替换当前程序。旧 NSIS/发布事务只在用户明确要求时使用，见 [历史发布契约](docs/release-contract.md)。
