# 纯手势三维建模 Demo：验收结果

> 本文件保留 2026-09-21 原工作分支的自动化和打包证据。2026-09-27 拆出的独立仓库已通过 `153` 项建模测试，但尚未为当前代码快照重新生成安装包，因此下方 EXE 和 SHA256 不代表当前提交。

验收日期：2026-09-21  
结论：自动化与打包 smoke 通过；真实摄像头验收 **NOT RUN**。

## 自动化证据

| Check | Result | Evidence |
|---|---|---|
| Original complete-project pytest suite | PASS | `492 passed in 8.39s` on the 2026-09-21 source snapshot |
| Packaged onedir smoke | PASS | `dist-hand-modeling\HandModelingDemo\HandModelingDemo.exe` |
| Packaged onefile smoke | PASS | `dist-hand-modeling\HandModelingDemo.exe` |
| Smoke starts on start page | PASS | report state `start` |
| Smoke keeps camera closed | PASS | `camera_open=false`, `tracking_running=false` |
| Smoke exits cleanly | PASS | `clean_shutdown=true` |

自动 smoke 只验证打包程序可启动、停留在起始状态且不会打开摄像头，不代表手势识别通过真机验收。

| Artifact | SHA256 |
|---|---|
| onedir `HandModelingDemo.exe` | `AE306CD8E7EF83DB0E7261959DBC46BA4FB9CE36FE173CAEB60A0FA0646E88AC` |
| onefile `HandModelingDemo.exe` | `7826122AB86953BA5B5ED46CA70DB73A5FDEBFA5B868F08A9D2784A4B4BB7652` |

## 真机环境

| 项目 | 记录 |
|---|---|
| Windows 版本 | NOT RECORDED |
| CPU / GPU | NOT RECORDED |
| 摄像头 | NOT RECORDED |
| 主显示器 | 1707 × 1067（仅系统查询，未用于真机验收） |
| 光照 / 背景 / 距离 | NOT RUN |
| 处理 FPS / 响应延迟 | NOT RUN |

## 真机手势结果

| Check | Attempts | Pass | Miss | False trigger | Result | Notes |
|---|---:|---:|---:|---:|---|---|
| Both open hands pan opposite motion | 20 |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| Both fists apart zoom in | 20 |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| Both fists together zoom out | 20 |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| Right fist orbits with hand direction | 20 |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| Five primitive creation gestures | 20 each |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| One-hand move and two-hand same-model transform | 20 each |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| Intersecting stationary union and non-intersection rejection | 20 each |  |  |  | NOT RUN | Physical webcam acceptance not performed. |
| Two clockwise/counterclockwise circles redo/undo | 20 each |  |  |  | NOT RUN | Physical webcam acceptance not performed. |

## 真机状态与安全结果

启动页摄像头关闭、暂停指示、稳定恢复、五种几何体、悬停/锁定反馈、非相交拒绝、追踪丢失回滚、返回起始页丢弃场景和干净退出均为 **NOT RUN**。详尽执行表见 `tests/manual/hand-modeling-acceptance.md`。

在真实摄像头完成全部项目并记录环境、次数及观察结果前，不得把本 Demo 标记为“真机验收通过”。
