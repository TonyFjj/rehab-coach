# models 目录说明

本目录存放推理权重。

## 必需（评估 / 训练主流程）

| 文件 | 大小 | 说明 |
|------|------|------|
| `yolov8n-pose-int8.rknn` | ~5.7 MB | RK3588 INT8 姿态模型 |

使用 `scripts/convert_yolov8_pose_rknn.py` 等脚本可在本地转换；详见仓库内 `scripts/`。

## 可选

| 文件 | 大小 | 说明 |
|------|------|------|
| `yolov8n-pose.rknn` | ~8.8 MB | 非 INT8 备用 |
| `tiny_tcn.onnx` | ~251 KB | IMU TinyTCN；需配合 `preprocess.npz` 方可完整推理 |
| `qwen2.5-1.5b-instruct-w8a8_rk3588.rkllm` | ~2 GB | 本地 LLM 推理 |

## 放置方式

将权重文件放在本目录，例如：

```text
models/
├── yolov8n-pose-int8.rknn
├── tiny_tcn.onnx          # 可选
└── rknn_pose_dataset.txt
```
