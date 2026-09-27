# Gesture-Controlled 3D Modeling

一个面向儿童和 3D 建模初学者的 Windows 纯手势建模原型。程序通过普通摄像头识别双手，让用户直接创建、选中和变换基础三维实体。

当前版本不使用眼动、面部识别或云端服务，也不包含键鼠控制项目。摄像头画面和完整关键点只在本机内存中处理，不会保存或上传。

## 当前进度

- 使用 MediaPipe Hand Landmarker 识别双手和关键点。
- 使用 Panda3D 显示三维场景，并支持实体悬停高亮和拾取。
- 支持球体、正方体、圆柱体、圆锥体和圆环体五种基础实体。
- 支持单手抓取移动，以及双手移动、缩放和旋转同一实体。
- 支持对两个已经相交的实体执行布尔并集。
- 支持撤销和重做。
- 包含启动页、教学页、设置页、暂停/恢复和运行状态反馈。
- 包含自动化测试、PyInstaller 打包脚本和暂停状态 smoke 检查。

## 操作方式

| 输入 | 操作 |
| --- | --- |
| `1` / `2` / `3` / `4` / `5` | 选择球体、正方体、圆柱体、圆锥体或圆环体 |
| 选择实体后双手捏合并向外拉伸，随后松开 | 创建实体并提交 |
| 双手张开并移动 | 向双手移动的反方向平移摄像机 |
| 双手握拳并改变两拳距离 | 两拳远离时拉近，两拳靠近时拉远 |
| 仅右手握拳并移动 | 环绕摄像机 |
| 将手移到实体上 | 悬停实体以显示高亮反馈 |
| 单手拇指和食指在高亮实体上捏合并移动 | 抓取实体，在屏幕平行平面内移动；松开后提交 |
| 双手捏住同一实体 | 中点控制移动，双手距离控制缩放，连线角度控制旋转 |
| 双手分别捏住两个已相交实体并向内靠拢 | 达到阈值后执行布尔并集 |
| 仅右食指画两圈 | 顺时针重做，逆时针撤销 |
| `Space` | 暂停并释放摄像头；再次按下后恢复 |

发生短暂追踪丢失时，正在进行的操作会暂时冻结；持续丢失会取消本次操作并回滚，避免错误提交。

## 运行要求

- Windows 10/11 x64
- 普通摄像头
- 64 位 Python 3.12
- 建议使用均匀正面光线，并确保双手完整进入画面

## 从源码运行

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m hand_modeling_demo.main
```

也可以在安装后运行：

```powershell
.\.venv\Scripts\hand-modeling-demo.exe
```

## 测试

自动化测试使用模拟摄像头和离屏图形环境，不会操作真实设备：

```powershell
$env:HAND_MODELING_HEADLESS = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
```

自动化测试不能替代真实摄像头验收。人工验收步骤见 [`tests/manual/hand-modeling-acceptance.md`](tests/manual/hand-modeling-acceptance.md)，当前验收记录见 [`tests/manual/hand-modeling-results.md`](tests/manual/hand-modeling-results.md)。

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build-hand-modeling.ps1
```

脚本依次生成文件夹版和单文件版，并对两种版本执行不会打开摄像头的启动及图形 smoke 检查。输出目录为 `dist-hand-modeling`。

## 验证状态

- 当前独立仓库：2026-09-27 运行建模测试，`153 passed`。
- 历史打包证据：2026-09-21 的文件夹版和单文件版 smoke 均通过；该证据早于当前代码快照，最新提交仍需重新打包验证。
- 真实摄像头、手势准确率和实际性能：尚未执行人工验收。

## 项目结构

```text
src/hand_modeling_demo/          建模应用、手势解释、场景、实体与界面
src/gesture_control/core/        建模所需的手部分类、几何和数据模型
src/gesture_control/vision/      摄像头与 MediaPipe 手部追踪
tests/hand_modeling_demo/        建模项目自动化测试
tests/manual/                    真机验收步骤和记录
packaging/                       PyInstaller 配置、构建和 smoke 检查
```

## 隐私与已知限制

- 程序运行时不需要账号，不上传摄像头画面，也不保存视频、图像或完整关键点。
- 启动页、教学页、设置页和暂停状态不会占用摄像头；进入建模或恢复后才会开启。
- 当前原型不支持保存、打开、导入、导出、删除和自动恢复模型。
- 遮挡、逆光、低帧率和双手交叉会降低识别稳定性。
- 布尔并集只接受封闭且已经相交的实体；失败时保留原实体并显示错误反馈。
- 当前自动化结果不代表真实摄像头和手势操作已经验收通过。
