#!/usr/bin/env bash
# 板端：启动 rehab-coach-rknn 后端（Qt 服务模式）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRESS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RKNN_ROOT="$(cd "${PROGRESS_DIR}/../../.." && pwd)"
BACKEND_DIR="${RKNN_ROOT}/rehab-coach-rknn"

if [ ! -d "${BACKEND_DIR}" ]; then
  echo "[ERROR] 未找到后端目录: ${BACKEND_DIR}"
  echo "       请确认 rehab-coach-rknn 位于 ${RKNN_ROOT}/rehab-coach-rknn"
  exit 1
fi

cd "${BACKEND_DIR}"
exec ./start_rk3588.sh "$@"
