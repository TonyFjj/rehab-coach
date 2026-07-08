# 居家康复助手 App

`app` 是一个 Android 原生工程，用于让手机通过蓝牙连接 RK3588，接收现有 Qt/后端康复系统输出的医疗建议和训练得分，并提供居家康复知识查询。

## 已实现

- 经典蓝牙 SPP 数据连接，UUID 为 `00001101-0000-1000-8000-00805F9B34FB`。
- 支持扫描周围蓝牙设备，不再只限制为已配对设备。
- 选择未配对设备后会先发起系统配对，配对成功后自动连接。
- UTF-8 JSON Lines 数据传输，一行一条消息。
- 解析现有后端 `scoring` 消息：`total_score`、`level`、`level_name`、`advice`、`dimension_scores`、`action_names`、`action_scores`。
- 兼容 `rehab-coach-rknn/data/imu/assessment_result.txt` 的原始 JSON。
- 兼容 Qt 本地保存的 `latest_assessment.json`。
- 应用名称已改为“居家康复助手”。
- 应用图标改为居家康复品牌图标，不再使用蓝牙图形作为桌面图标。
- 手机端采用四模块结构：主页、康复知识、训练记录、设置。
- 主页展示综合得分、等级、最近建议摘要和快捷操作。
- 康复知识模块独立展示训练建议、六维评估，并新增“康复锻炼建议 / 常见康复药物 / 锻炼动作”三大类详情页。
- 康复知识内容覆盖肌肉损伤、肌肉拉伤、老年人锻炼、肌无力、帕金森康复、上肢训练和下肢训练，并配有应用内插画。
- 训练记录模块保存本次打开 App 后收到的最近训练结果，并展示动作得分。
- 设置模块集中管理蓝牙扫描连接、自动同步、权限状态和通信日志。
- `rk3588_gateway` 中提供 RK3588 蓝牙网关示例脚本。

## 工程结构

```text
app/
  mobile/                 Android App 模块
  rk3588_gateway/         RK3588 蓝牙 SPP 服务示例
  docs/PROTOCOL.md        手机和 RK3588 的 JSON 协议
  居家康复助手.apk        可直接安装到 Android 手机的安装包
```

## 使用流程

1. 在 RK3588 上启动原康复系统和 Qt 程序。
2. 在 RK3588 上启动 `rk3588_gateway/bt_rehab_gateway.py`。
3. 将 `app/居家康复助手.apk` 发送到 Android 手机并安装。
4. 打开 App，允许蓝牙扫描/连接权限。
5. 在底部进入“设置”，点击“扫描周围设备”，等待列表中出现 RK3588 或其他目标蓝牙设备。
6. 选中设备后点击“连接选中设备”；如果未配对，App 会先触发系统配对，再继续连接。
7. 回到“主页”查看综合得分，也可以进入“康复知识”查看建议正文、六维评估和康复知识分类。
8. 进入“训练记录”查看最近收到的训练结果和动作得分。

## 康复知识内容

App 内新增三个大类：

- 康复锻炼建议：肌肉损伤、肌肉拉伤、老年人日常锻炼、肌无力与疲劳管理、帕金森康复、上肢下肢训练安排。
- 常见康复药物：肌肉损伤疼痛管理、肌肉拉伤恢复用药、老年人用药注意、肌无力相关药物、帕金森常见用药类别、用药安全提醒。
- 锻炼动作：肌肉损伤早期动作、肌肉拉伤恢复动作、上肢动作、下肢动作、老年人基础动作、肌无力低疲劳训练、帕金森运动动作与注意事项。

这些内容用于健康教育，不替代医生诊断、处方或康复治疗师的个体化训练方案。

医学内容主要参考：

- NHS：Sprains and strains、Parkinson's disease treatment。
- MedlinePlus：Sprains and Strains、Hamstring strain aftercare。
- AAOS OrthoInfo：Muscle strains、shoulder conditioning、knee conditioning。
- Parkinson's Foundation：Exercise and Parkinson's disease。

## 构建 App

当前仓库已经包含本地构建工具，命令行构建示例：

```powershell
cd C:\Users\ysy\Desktop\rknn\app
$root='C:\Users\ysy\Desktop\rknn\app'
$tools=Join-Path $root '.build-tools'
$env:JAVA_HOME=Join-Path $tools 'jdk-17.0.19+10'
$env:ANDROID_SDK_ROOT=Join-Path $tools 'android-sdk'
$env:ANDROID_HOME=$env:ANDROID_SDK_ROOT
$env:GRADLE_USER_HOME=Join-Path $root '.gradle-cache'
& (Join-Path $tools 'gradle-8.10.2\bin\gradle.bat') :mobile:assembleDebug --no-daemon
```

生成的 APK 位于：

```text
app/mobile/build/outputs/apk/debug/mobile-debug.apk
```

对外使用时可以直接安装：

```text
app/居家康复助手.apk
```
