# 基于ELF 2 视觉与端侧大模型的‘离线式’居家康复动作指导教练

基于ELF 2 视觉与端侧大模型的‘离线式’居家康复动作指导教练：Python 引擎 + Qt 界面 + 双目视觉 +（可选）IMU + 蓝牙网关。

适用于健康评估（六维雷达图）、分级康复训练、训练/评估记录、医疗建议展示与适老「大字模式」。

---

## 系统组成

| 模块 | 路径 | 说明 |
|------|------|------|
| Python 引擎 | `src/backend/` | 视觉、评分、训练状态机、TTS、Qt 服务 |
| Qt 界面 | `src/qt_gui/` | 首页 / 评估 / 训练 / 记录 / 医疗建议 / 设置 |
| 蓝牙网关 | `src/gateway/` | Android App 同步记录（可选） |
| 模型 | `models/` | YOLOv8-Pose RKNN、TinyTCN ONNX 等 |

通信：UTF-8 JSON 行协议；RK3588 使用 Unix Socket `/tmp/rehab_engine.sock`。

---

## 硬件与环境

- **板卡**：RK3588（推荐）
- **摄像头**：双目（左右拼接预览）
- **可选**：WIT 系列 IMU（左右手各一）
- **系统**：Linux（Ubuntu / Debian 系），Python 3.8+

### 依赖安装（Ubuntu / Debian 示例）

```bash
sudo apt update
sudo apt install -y \
  build-essential cmake git \
  python3 python3-pip \
  qtbase5-dev qt5-qmake libgl1-mesa-dev \
  fonts-noto-cjk
```

Python 依赖以后端 `src/backend/start_rk3588.sh` 实际导入为准；首次部署可在板子上按报错 `pip install` 补齐。

---

## 快速启动

### 1. 编译 Qt

```bash
cd src/qt_gui
BUILD_JOBS=2 ./scripts/build_linux.sh
```

产物：`src/qt_gui/build-linux/prograss_copy`

### 2. 启动（推荐一键脚本）

**终端 1 — 引擎：**

```bash
./start_rk3588_system.sh backend
```

**终端 2 — 界面：**

```bash
./start_rk3588_system.sh qt
```

**可选 — 蓝牙网关：**

```bash
./start_rk3588_system.sh gateway
```

其他子命令：`status`、`logs`、`stop`、`all`（见 `./start_rk3588_system.sh help`）。

### 3. 手动启动（与脚本等价）

```bash
# 终端 1
cd src/backend && ./start_rk3588.sh

# 终端 2
cd src/qt_gui && ./scripts/run_linux.sh
```

---

## 模型文件

| 文件 | 约大小 | 是否必需 | 说明 |
|------|--------|----------|------|
| `models/yolov8n-pose-int8.rknn` | 5.7 MB | **是** | 姿态估计（RK3588 INT8） |
| `models/yolov8n-pose.rknn` | 8.8 MB | 否 | 非 INT8 备用 |
| `models/tiny_tcn.onnx` | 251 KB | 否 | IMU TinyTCN，用于左右手评分补充 |
| `models/qwen2.5-*.rkllm` | ~2 GB | 否 | 本地 LLM 推理（可选） |
| `src/qt_gui/res/pic/training_gifs/` | ~198 MB | 否 | 训练示范 GIF；缺失时左侧仍显示摄像头 |

权重获取与放置方式见 [`models/README.md`](models/README.md)。

---

## 目录结构

```text
rehab-coach/
├── start_rk3588_system.sh    # 一键启停
├── src/
│   ├── backend/              # Python 引擎
│   ├── qt_gui/               # Qt 界面
│   └── gateway/              # 蓝牙网关
├── scripts/                  # 工具脚本
├── models/                   # RKNN / ONNX 权重
└── apps/android/             # Android 配套（可选）
```

---

## 文档索引

- [Qt Linux 编译运行](src/qt_gui/README_LINUX.md)
- [后端部署摘要](src/backend/README_DEPLOY.txt)
- [Android 配套说明](apps/android/README.md)

---

## 常见问题

**Qt 显示「引擎未连接」**  
先启动 `backend`，确认存在 `/tmp/rehab_engine.sock`。

**编译 Qt OOM**  
`BUILD_JOBS=1 ./scripts/build_linux.sh`，或增加 swap。

**逆光 / 环境预检**  
评估页摄像头画面底部 overlay 会提示；预检阶段请看画面内提示与下方大字字幕。

**大字模式**  
设置页切换；评估 / 训练 / 记录等页已接入 `FontScale`。

---

## 许可证

开源发布前请补充根目录 `LICENSE`，并在本文列出第三方组件（YOLOv8、Qt、Piper TTS 等）许可说明。
