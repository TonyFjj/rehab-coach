#!/bin/bash
# RK3588 板端启动脚本
set -e
cd "$(dirname "$0")"

if [ -d venv ]; then
  source venv/bin/activate
fi

# USB 音响等设备请在 config/camera_config.rk3588.yaml 的 audio 段配置

if ! python3 -c "from rknnlite.api import RKNNLite" 2>/dev/null; then
  echo "[ERROR] 未安装 rknn-toolkit2-lite，请先: pip install rknn-toolkit2-lite"
  exit 1
fi

if [ ! -f ../third_party/librkllmrt.so ]; then
  RKLLM_LIB="../../rkllm_demo/deploy/lib/librkllmrt.so"
  if [ -f "$RKLLM_LIB" ]; then
    ln -sf "$(readlink -f "$RKLLM_LIB")" ../third_party/librkllmrt.so
    echo "[INFO] 已自动链接 ../third_party/librkllmrt.so"
  else
    echo "[ERROR] 缺少 ../third_party/librkllmrt.so，请链接 rkllm_demo/deploy/lib/librkllmrt.so"
    exit 1
  fi
fi

QWEN_MODEL="../../models/qwen2.5-1.5b-instruct.rkllm"
if [ ! -f "$QWEN_MODEL" ]; then
  for CAND in \
    "../../models/qwen2.5-1.5b-instruct-w8a8_rk3588.rkllm" \
    "$HOME/Desktop/rknn/qwen2.5-1.5b-instruct-w8a8_rk3588.rkllm"; do
    if [ -f "$CAND" ]; then
      ln -sf "$(readlink -f "$CAND")" "$QWEN_MODEL"
      echo "[INFO] 已自动链接 $QWEN_MODEL -> $(readlink -f "$CAND")"
      break
    fi
  done
fi
if [ ! -f "$QWEN_MODEL" ]; then
  echo "[ERROR] 缺少 Qwen RKLLM 模型 $QWEN_MODEL"
  exit 1
fi

if [ ! -f ../../assets/tts_models/vits-melo-tts-zh_en/model.onnx ]; then
  TTS_DIR="../../assets/tts_models/vits-melo-tts-zh_en"
  mkdir -p "$TTS_DIR"
  for CAND in \
    "$HOME/Desktop/rehab-coach-rknn/rehab-coach-m2-rknn/tts_models/vits-melo-tts-zh_en" \
    "../../third_party/piper-tts/vits-melo-tts-zh_en"; do
    if [ -f "$CAND/model.onnx" ] || [ -f "$CAND/model.int8.onnx" ]; then
      for f in model.onnx model.int8.onnx tokens.txt lexicon.txt dict date.fst number.fst phone.fst new_heteronym.fst LICENSE README.md; do
        if [ -e "$CAND/$f" ] && [ ! -e "$TTS_DIR/$f" ]; then
          ln -sf "$(readlink -f "$CAND/$f")" "$TTS_DIR/$f"
        fi
      done
      if [ ! -f "$TTS_DIR/model.onnx" ] && [ -f "$TTS_DIR/model.int8.onnx" ]; then
        ln -sf model.int8.onnx "$TTS_DIR/model.onnx"
      fi
      echo "[INFO] 已自动链接 TTS 模型 -> $CAND"
      break
    fi
  done
fi
if [ ! -f ../../assets/tts_models/vits-melo-tts-zh_en/model.onnx ]; then
  echo "[ERROR] 缺少 Sherpa-ONNX TTS 模型 ../../assets/tts_models/vits-melo-tts-zh_en/model.onnx"
  exit 1
fi

if [ ! -f ../../models/yolov8n-pose.rknn ]; then
  echo "[ERROR] 缺少 ../../models/yolov8n-pose.rknn，见 ../../docs/rknn_pose.md"
  exit 1
fi

IMU_LEFT="${IMU_LEFT:-}"
IMU_RIGHT="${IMU_RIGHT:-}"
if [ -z "$IMU_LEFT" ] || [ -z "$IMU_RIGHT" ]; then
  ACM_LIST=$(ls /dev/ttyACM* 2>/dev/null | tr '\n' ' ')
  if [ -n "$ACM_LIST" ]; then
    echo "[INFO] IMU 串口: $ACM_LIST"
    echo "       配置 auto 时将自动选用；也可 export IMU_LEFT=/dev/ttyACM2"
  else
    echo "[WARN] 未发现 ttyACM 串口，请确认拓展坞上 IMU 已连接"
  fi
fi

CAM_LIST=$(ls /dev/v4l/by-id/usb-* 2>/dev/null | tr '\n' ' ')
if [ -n "$CAM_LIST" ]; then
  echo "[INFO] USB 摄像头: $CAM_LIST"
else
  echo "[WARN] 未发现 USB 摄像头 by-id 路径"
fi

IMU_BIN="../../src/imu/dual/IMU_measure/build/IMU_measure"
if [ ! -f "$IMU_BIN" ]; then
  IMU_BIN="../../src/imu/build/IMU_measure"
fi
if [ ! -f "$IMU_BIN" ]; then
  echo "[WARN] 未找到 IMU_measure，设置页「IMU初评」不可用"
  echo "       运行: bash ../../scripts/build_imu_measure.sh"
fi

exec python3 main.py --real --rknn --qt-service "$@"
