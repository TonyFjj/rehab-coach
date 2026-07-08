#!/usr/bin/env bash
# WSL2 x86：YOLOv8n-Pose ONNX → RKNN（INT8 hybrid，默认不覆盖原 yolov8n-pose.rknn）
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="${VENV:-.venv-rknn-wsl}"
OUT="${OUT:-models/yolov8n-pose-int8.rknn}"
ONNX="${ONNX:-models/yolov8n-pose.onnx}"
DATASET="${DATASET:-models/rknn_pose_dataset.txt}"
NO_QUANT=""
NO_HYBRID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --onnx) ONNX="$2"; shift 2 ;;
    --dataset) DATASET="$2"; shift 2 ;;
    --no-quant) NO_QUANT="--no-quant"; shift ;;
    --no-hybrid) NO_HYBRID="--no-hybrid"; shift ;;
    -h|--help)
      echo "用法: bash scripts/wsl_convert_rknn.sh [--out models/yolov8n-pose-int8.rknn] [--no-quant]"
      exit 0
      ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

if [[ ! -d "$VENV" ]]; then
  echo "[ERROR] 未找到 $VENV，请先: bash scripts/wsl_install_rknn.sh"
  exit 1
fi
# shellcheck disable=SC1090
source "$VENV/bin/activate"

if [[ ! -f "$ONNX" ]]; then
  echo "[ERROR] 缺少 $ONNX"
  echo "  Windows PowerShell: python scripts/export_yolov8_pose_onnx.py"
  exit 1
fi

echo "[INFO] ONNX=$ONNX"
echo "[INFO] OUT=$OUT (不会覆盖 models/yolov8n-pose.rknn，除非 --out 指定)"
echo "[INFO] DATASET=$DATASET"

python scripts/convert_yolov8_pose_rknn.py \
  --onnx "$ONNX" \
  --out "$OUT" \
  --dataset "$DATASET" \
  $NO_QUANT $NO_HYBRID

echo "[OK] 完成。板端验证后改 config/camera_config.rk3588.yaml 的 pose_model"
