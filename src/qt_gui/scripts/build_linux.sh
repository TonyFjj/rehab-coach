#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_DIR}/build-linux"

echo "[1/3] 检查 Linux Qt 构建环境"
if ! command -v cmake >/dev/null 2>&1; then
  echo "缺少 cmake。Ubuntu/Debian 可执行: sudo apt install cmake build-essential"
  exit 1
fi

if ! command -v g++ >/dev/null 2>&1; then
  echo "缺少 g++。Ubuntu/Debian 可执行: sudo apt install build-essential"
  exit 1
fi

if ! ldconfig -p 2>/dev/null | grep -Eq "libQt5Widgets|libQt6Widgets"; then
  echo "未检测到 Qt Widgets 运行库。Ubuntu/Debian 可执行:"
  echo "  sudo apt install qtbase5-dev qt5-qmake build-essential cmake"
  echo "或使用 Qt6:"
  echo "  sudo apt install qt6-base-dev build-essential cmake"
fi

echo "[2/3] 配置 CMake"
cmake -S "${PROJECT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release

echo "[3/3] 编译"
# training GIF 从磁盘加载（见 pic.qrc 注释），不再嵌入 qrc，避免 qrc_pic.cpp 膨胀导致 OOM
BUILD_JOBS="${BUILD_JOBS:-2}"
SWAP_KB="$(awk '/SwapTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
if [ "${SWAP_KB:-0}" -lt 1048576 ] 2>/dev/null; then
  echo "[WARN] 未配置 swap 或 swap < 1GB，若编译失败可尝试:"
  echo "       BUILD_JOBS=1 bash scripts/build_linux.sh"
  echo "       或: sudo fallocate -l 4G /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
fi
cmake --build "${BUILD_DIR}" --parallel "${BUILD_JOBS}"

# 运行时 GIF 目录（与 run_linux.sh 一致）
mkdir -p "${BUILD_DIR}/res/pic"
if [ ! -e "${BUILD_DIR}/res/pic/training_gifs" ]; then
  ln -sf "${PROJECT_DIR}/res/pic/training_gifs" "${BUILD_DIR}/res/pic/training_gifs" 2>/dev/null || true
fi

chmod +x "${BUILD_DIR}/prograss_copy" 2>/dev/null || true

echo
echo "构建完成: ${BUILD_DIR}/prograss_copy"
echo "运行: ${PROJECT_DIR}/scripts/run_linux.sh"
