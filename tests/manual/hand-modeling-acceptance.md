# 纯手势三维建模 Demo：真机验收清单

本清单只用于普通摄像头真机验收。每次尝试从中性手势开始，完成动作后回到中性手势；误触发是未执行目标动作时发生了命令。自动化测试或打包 smoke 不能替代本表的真机结果。

## 环境记录

| 项目 | 记录 |
|---|---|
| 日期/测试人 |  |
| Windows 版本 |  |
| CPU / GPU |  |
| 摄像头型号与设备编号 |  |
| 主显示器分辨率 / 缩放 |  |
| 光照、背景、人与摄像头距离 |  |
| 处理 FPS（中位数） |  |
| 响应延迟（中位数，ms） |  |
| 使用构建与 SHA256 |  |

## 手势可靠性（每项 20 次）

| Check | Attempts | Pass | Miss | False trigger | Result | Notes |
|---|---:|---:|---:|---:|---|---|
| Both open hands pan opposite motion | 20 |  |  |  | NOT RUN | |
| Both fists apart zoom in | 20 |  |  |  | NOT RUN | |
| Both fists together zoom out | 20 |  |  |  | NOT RUN | |
| Right fist orbits with hand direction | 20 |  |  |  | NOT RUN | |
| Pinch creates sphere from center point | 20 |  |  |  | NOT RUN | |
| Pinch creates cube from center point | 20 |  |  |  | NOT RUN | |
| Pinch creates cylinder from center point | 20 |  |  |  | NOT RUN | |
| Pinch creates cone from center point | 20 |  |  |  | NOT RUN | |
| Pinch creates torus from center point | 20 |  |  |  | NOT RUN | |
| One-hand pinch moves model and release commits | 20 |  |  |  | NOT RUN | |
| Two-hand pinch on same model moves/scales/rotates | 20 |  |  |  | NOT RUN | |
| Two-hand inward pinch unions two intersecting stationary models | 20 |  |  |  | NOT RUN | |
| Two-hand inward pinch rejects non-intersecting models | 20 |  |  |  | NOT RUN | |
| Two clockwise right-index circles redo one step | 20 |  |  |  | NOT RUN | |
| Two counterclockwise right-index circles undo one step | 20 |  |  |  | NOT RUN | |

## 状态、安全和反馈

每项填写 `PASS`、`FAIL` 或 `NOT RUN`，失败时写明复现步骤与观察结果。

| Check | Result | Notes |
|---|---|---|
| Start page keeps camera off | NOT RUN | |
| Entering modeling opens the selected camera | NOT RUN | |
| Space pauses, closes camera, and shows pause window | NOT RUN | |
| Continue keeps pause visible until tracking is stable | NOT RUN | |
| Left and right pointers are visible and correctly mapped | NOT RUN | |
| Hover highlight and pinch lock feedback are distinct | NOT RUN | |
| Digits 1–5 arm the correct primitive, with creation priority | NOT RUN | |
| Union leaves intersecting models stationary until commit | NOT RUN | |
| Union failure preserves both original models | NOT RUN | |
| Tracking loss cancels and rolls back the active operation | NOT RUN | |
| Return to start discards the current unsaved scene | NOT RUN | |
| Exit closes camera and process cleanly | NOT RUN | |
| Chinese/English switch and settings persistence work | NOT RUN | |

## 执行方法

1. 运行 `dist-hand-modeling\HandModelingDemo\HandModelingDemo.exe`。
2. 先完成状态、安全和反馈检查，再逐行执行手势可靠性测试。
3. 每行必须实际执行全部尝试次数；记录成功、漏检和误触发，三者应能解释全部观察。
4. 发现规格内缺陷时，先增加确定性的失败测试，再做最小修复并重新执行受影响行；新增行为必须返回设计评审。
5. 将结果复制到 `tests/manual/hand-modeling-results.md`，不得把未执行项目写成 PASS。
