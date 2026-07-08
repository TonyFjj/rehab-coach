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

本仓库**自有代码**（`src/`、`scripts/`、`start_rk3588_system.sh` 等）采用 [MIT License](LICENSE)。

以下第三方组件、模型与运行时**不随本仓库一并授权**，使用前请阅读各自许可条款；若对外分发二进制或提供服务，须自行确认合规义务（尤其 YOLOv8 的 AGPL、Qt 的 LGPL、Rockchip SDK 等）。

### 第三方组件与许可

| 组件 | 用途 | 许可 | 说明 |
|------|------|------|------|
| [Qt 5](https://www.qt.io/) | `src/qt_gui/` 图形界面 | **LGPL v3** | Linux 下动态链接；修改 Qt 库本身须开源修改部分 |
| [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) | 姿态估计（开发机 `.pt` / 导出 ONNX） | **AGPL-3.0** | 权重与 `ultralytics` 包受其约束；对外提供网络服务或分发修改版时需特别注意 |
| YOLOv8n-Pose 权重 | `models/yolov8n-pose*.rknn` / `.pt` | **AGPL-3.0**（随 Ultralytics） | 由官方权重转换；**未包含在 Git 仓库**，需自行获取 |
| [OpenCV](https://opencv.org/) | 摄像头、图像处理、标定 | **Apache 2.0** | Python `opencv-python` |
| [NumPy](https://numpy.org/) | 数值计算 | **BSD 3-Clause** | |
| [PyYAML](https://pyyaml.org/) | 配置文件 | **MIT** | |
| [pyserial](https://github.com/pyserial/pyserial) | IMU 串口 | **BSD 3-Clause** | |
| [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) | RK3588 离线 TTS 推理 | **Apache 2.0** | `sherpa-onnx` Python 包 |
| [Piper](https://github.com/rhasspy/piper) / VITS 语音模型 | TTS 模型来源（如 `vits-melo-tts-zh_en`） | **MIT**（Piper）/ 见模型包内 `LICENSE` | 模型文件在 `assets/tts_models/`，**未包含在 Git**；`start_rk3588.sh` 可从 `third_party/piper-tts/` 链接 |
| [Qwen2.5](https://github.com/QwenLM/Qwen2.5) | 本地 LLM 权重（`.rkllm`） | **Apache 2.0**（模型） | 可选；权重**未包含在 Git** |
| [RKNN Toolkit 2 / rknn-toolkit2-lite](https://github.com/airockchip/rknn-toolkit2) | YOLO RKNN 推理 | **Rockchip 专有 SDK 条款** | 须从 Rockchip 渠道安装并接受其许可 |
| [RKLLM Runtime](https://github.com/airockchip/rknn-llm) | Qwen `.rkllm` 推理（`librkllmrt.so`） | **Rockchip 专有 SDK 条款** | 置于 `third_party/`，**未包含在 Git** |
| `tiny_tcn.onnx` | IMU 左右手评分（可选） | **MIT**（本仓库训练导出） | 见 `models/` |
| [pyttsx3](https://github.com/nateshmbhat/pyttsx3) | 开发调试 TTS（可选） | **MPL 2.0** | 非板端默认后端 |
| Android SDK / Gradle | `apps/android/` 蓝牙网关 App | **Apache 2.0** 等（Google 条款） | 编译需本机 Android SDK |
| [Noto CJK](https://fonts.google.com/noto) | 中文字体（系统包 `fonts-noto-cjk`） | **SIL OFL 1.1** | 通过 apt 安装，不随仓库分发 |

### 未随仓库分发的资源

以下目录/文件在 [`.gitignore`](.gitignore) 中排除，**许可与获取方式以提供方为准**：

- `models/*.rknn`、`models/*.rkllm` — 见 [`models/README.md`](models/README.md)
- `assets/tts_models/` — Sherpa-ONNX / Piper 兼容 VITS 模型
- `third_party/` — `librkllmrt.so`、Piper 模型等 Rockchip / 第三方二进制
- `docs/` — 内部文档
- `src/qt_gui/res/pic/training_gifs/` — 训练示范动图

### 免责声明

本项目为康复辅助软件，**不构成医疗诊断或治疗建议**。部署与使用前请遵守当地法规及上述第三方许可。
