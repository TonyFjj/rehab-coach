#!/bin/bash
# 编译 IMU_measure 并对接 rehab-coach/data/imu
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$ROOT/data/imu"
mkdir -p "$DATA_DIR"

# 优先 src/imu，若目录不可写则使用 dual/IMU_measure
for IMU_DIR in "$ROOT/src/imu" "$ROOT/src/imu/dual/IMU_measure"; do
  if [[ ! -f "$IMU_DIR/CMakeLists.txt" ]]; then
    continue
  fi
  if ! mkdir -p "$IMU_DIR/build" 2>/dev/null; then
    echo "[build_imu] 跳过不可写目录: $IMU_DIR"
    continue
  fi
  echo "[build_imu] 编译 $IMU_DIR"
  if [[ -f "$IMU_DIR/build/CMakeCache.txt" ]]; then
    cached="$(grep -m1 '^CMAKE_HOME_DIRECTORY:' "$IMU_DIR/build/CMakeCache.txt" | cut -d= -f2-)"
    if [[ -n "$cached" && "$cached" != "$IMU_DIR" ]]; then
      echo "[build_imu] 清理旧 CMake 缓存 ($cached)"
      rm -rf "$IMU_DIR/build"
      mkdir -p "$IMU_DIR/build"
    fi
  fi
  cmake -S "$IMU_DIR" -B "$IMU_DIR/build"
  cmake --build "$IMU_DIR/build" -j"$(nproc)"
  BIN="$IMU_DIR/build/IMU_measure"
  if [[ -f "$BIN" ]]; then
    chmod +x "$BIN"
    echo "[build_imu] 成功: $BIN"
    echo "[build_imu] 数据目录（IMU_DATA_DIR）: $DATA_DIR"
    echo "[build_imu] 评估日志: $DATA_DIR/assessment_log.csv"
    echo "[build_imu] 完成"
    exit 0
  fi
done

echo "[build_imu] 未找到可执行文件"
exit 1
