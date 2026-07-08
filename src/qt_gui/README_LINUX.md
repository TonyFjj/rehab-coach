# Linux 运行说明（对接 rehab-coach-rknn）

## 1. 安装依赖

```bash
sudo apt update
sudo apt install build-essential cmake qtbase5-dev qt5-qmake libgl1-mesa-dev fonts-noto-cjk python3
```

## 2. 编译 Qt 界面

```bash
cd embedded_QT_section_modified_by_chatgpt/prograss_copy
./scripts/build_linux.sh
```

## 3. 启动顺序（重要）

**必须先启动 Python 后端，再启动 Qt 界面。**

终端 1 — 康复引擎（RK3588，Qt 服务模式）：

```bash
cd /path/to/rehab-coach-rknn
./start_rk3588.sh
# 或: python3 main.py --real --rknn --qt-service
```

终端 2 — Qt 界面：

```bash
cd embedded_QT_section_modified_by_chatgpt/prograss_copy
./scripts/run_linux.sh
```

也可使用：`./scripts/start_backend.sh`（从 Qt 目录一键启动后端）

## 4. 视觉调试画面

后端启动后会自动向已连接的 Qt 推送 `vision_preview`（与 `main.py --show-vision` 相同内容：左右目 + 骨骼点 + FPS）。

- **训练页 / 评估页** 顶部黑色区域即为实时画面
- 无需再单独开 OpenCV 窗口；开发调试仍可用 `--show-vision`

## 5. 通信方式

| 平台 | 传输 |
|------|------|
| Linux / RK3588 | Unix Socket `/tmp/rehab_engine.sock` |
| Windows 开发 | TCP `127.0.0.1:9002` |

协议：UTF-8 JSON，一行一条消息（详见 `rehab-coach-rknn/docs/qt_integration.md`）。

## 5. Qt 功能对接

| 页面 | Qt → 后端 | 后端 → Qt |
|------|-----------|-----------|
| 评估 | `start_assessment` | `vision_preview`, `scoring` |
| 训练 | `start/pause/resume/stop_training` | `vision_preview`, `training_state`, `action_status`, `training_progress`, `correction`, `encouragement`, `session_summary`, `scoring` |

IMU 仍由后端文件/模拟提供；Qt 侧 ImuBridge 不参与计分。

训练页选择 L1–L4 后点「开始训练」，会发送 `"level":"L2"` 等字符串（不再是数字 2）。

## 6. 联调检查

训练页顶部应显示：**引擎：已连接（/tmp/rehab_engine.sock）**

若显示未连接：

1. 确认 `main.py` 已启动且无报错
2. 检查 socket：`ls -l /tmp/rehab_engine.sock`
3. 重新打开 Qt 程序（会自动重连）

## 7. 数据保存位置

```bash
~/.local/share/prograss_copy/
```

可选冒烟脚本（Linux/RK3588 使用 Unix Socket）：

```bash
# 在后端项目目录
python3 scripts/qt_socket_smoke.py --send request_status

# 或在 Qt 项目目录
python3 scripts/qt_client_smoke.py --send request_status
```

## 8. Android App 蓝牙同步

Qt 将训练/评估记录保存到 `~/.local/share/prograss_copy/` 后，由蓝牙网关推送到手机 App：

```bash
# 在项目根目录
./start_rk3588_system.sh gateway
# 或
python3 app/rk3588_gateway/bt_rehab_gateway.py --project-root /home/elf/Desktop/rknn
```

手机需先在系统蓝牙中与 RK3588 配对，再在 App 内连接 `RK3588-Rehab`。

## 9. 一键启动（推荐）

```bash
cd /home/elf/Desktop/rknn
./start_rk3588_system.sh backend   # 终端1
./start_rk3588_system.sh qt        # 终端2
./start_rk3588_system.sh gateway   # 终端3（可选，供手机 App）
```

## 本次适配说明

- 新增 `ipc/enginebridge.cpp`：统一对接 rehab-coach-rknn JSON 协议
- 训练页/评估页改为通过 EngineBridge 收发指令与状态
- Linux 默认连 `/tmp/rehab_engine.sock`，不再仅依赖 mock TCP 后端
- 未连接后端时，训练页仍可使用本地演示计时模式
