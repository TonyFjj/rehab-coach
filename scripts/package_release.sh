#!/usr/bin/env bash
# 生成交付压缩包（zip；本系统 apt 无 rar 打包命令，仅有 unrar 解压）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-${ROOT}/rehab-coach-release.zip}"

cd "${ROOT}"

required=(
  README.md
  start_rk3588_system.sh
  models/yolov8n-pose-int8.rknn
  models/tiny_tcn.onnx
)

for f in "${required[@]}"; do
  if [[ ! -e "${f}" ]]; then
    echo "[ERROR] 缺少文件: ${f}"
    exit 1
  fi
done

rm -f "${OUT}"

zip -r "${OUT}" \
  README.md \
  .gitignore \
  start_rk3588_system.sh \
  scripts/ \
  docs/ \
  src/backend/ \
  src/qt_gui/ \
  src/gateway/ \
  apps/ \
  models/yolov8n-pose-int8.rknn \
  models/tiny_tcn.onnx \
  models/rknn_pose_dataset.txt \
  models/README.md \
  -x "*/build-linux/*" \
  -x "*/training_gifs/*" \
  -x "*/data/*" \
  -x "*imu_stream.txt*" \
  -x "*/__pycache__/*" \
  -x "*.rkllm" \
  -x "*/tts_cache/*" \
  -x "*/apps/android/**/build/*" \
  -x "*/apps/android/.gradle/*" \
  -x "*.apk" \
  -x "*.zip" \
  -x "*.rar"

echo
ls -lh "${OUT}"
echo
echo "完成: ${OUT}"
echo "解压: unzip rehab-coach-release.zip -d 目标目录"
