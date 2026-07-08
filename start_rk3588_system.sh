#!/usr/bin/env bash
# RK3588 一键启动：Python 后端 + Qt 界面 + 蓝牙网关（可选）
set -euo pipefail

RKNN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${RKNN_ROOT}/src/backend"
QT_DIR="${RKNN_ROOT}/src/qt_gui"
GATEWAY_DIR="${RKNN_ROOT}/src/gateway"
SOCKET="/tmp/rehab_engine.sock"
QT_APP="${QT_DIR}/build-linux/prograss_copy"

usage() {
  cat <<EOF
用法: $0 [backend|qt|gateway|all|status|stop]

  backend     前台启动 Python 引擎（日志在本终端，推荐测试时用）
  backend-bg  后台启动 Python 引擎（日志写入 /tmp/rehab_backend.log）
  qt          仅启动 Qt 界面（需 backend 已运行）
  gateway     仅启动蓝牙网关（供 Android App 同步训练/评估记录）
  all         后台 backend + gateway，前台启动 Qt
  status      检查 socket / 进程状态
  logs        跟踪 backend / gateway 后台日志
  stop        停止本脚本启动的后端与网关

推荐顺序（测试阶段，两终端看完整日志）:
  终端1: $0 backend          # 前台，与以前 ./start_rk3588.sh 类似
  终端2: $0 qt
  终端3: $0 gateway          # 手机蓝牙同步时

EOF
}

wait_for_socket() {
  local timeout="${1:-60}"
  local i=0
  while [ ! -S "${SOCKET}" ] && [ "$i" -lt "$timeout" ]; do
    sleep 1
    i=$((i + 1))
  done
  if [ ! -S "${SOCKET}" ]; then
    echo "[ERROR] 等待 ${SOCKET} 超时，请检查 backend 日志"
    return 1
  fi
  echo "[OK] ${SOCKET} 已就绪"
}

start_backend() {
  local background="${1:-0}"

  if [ -S "${SOCKET}" ]; then
    if python3 -c "import socket; s=socket.socket(socket.AF_UNIX); s.settimeout(1); s.connect('${SOCKET}'); s.close()" 2>/dev/null; then
      echo "[INFO] backend 已在运行 (${SOCKET})"
      if [ -f /tmp/rehab_backend.pid ] && kill -0 "$(cat /tmp/rehab_backend.pid)" 2>/dev/null; then
        echo "[INFO] 后台 PID=$(cat /tmp/rehab_backend.pid)"
      fi
      echo "[INFO] 查看日志: $0 logs"
      echo "[INFO] 重新启动: $0 stop && $0 backend"
      return 0
    fi
    echo "[WARN] 发现陈旧 socket，正在清理..."
    rm -f "${SOCKET}"
  fi

  if [ ! -x "${BACKEND_DIR}/start_rk3588.sh" ]; then
    chmod +x "${BACKEND_DIR}/start_rk3588.sh" 2>/dev/null || true
  fi

  cd "${BACKEND_DIR}"
  if [ "${background}" = "1" ]; then
    echo "[INFO] 后台启动 backend: ${BACKEND_DIR}"
    nohup ./start_rk3588.sh > /tmp/rehab_backend.log 2>&1 &
    echo $! > /tmp/rehab_backend.pid
    echo "[INFO] backend PID=$(cat /tmp/rehab_backend.pid), 日志: /tmp/rehab_backend.log"
    wait_for_socket 90
    return 0
  fi

  echo "[INFO] 前台启动 backend（日志在本终端，Ctrl+C 退出）"
  echo "[INFO] 目录: ${BACKEND_DIR}"
  echo "[INFO] 如需后台: $0 backend-bg"
  rm -f /tmp/rehab_backend.pid
  exec ./start_rk3588.sh
}

start_qt() {
  if [ ! -f "${QT_APP}" ]; then
    echo "[ERROR] 未找到 Qt 程序，请先编译:"
    echo "  cd ${QT_DIR} && BUILD_JOBS=1 ./scripts/build_linux.sh"
    exit 1
  fi
  chmod +x "${QT_APP}" 2>/dev/null || true
  if [ ! -S "${SOCKET}" ]; then
    echo "[WARN] ${SOCKET} 不存在，Qt 将显示「引擎未连接」"
    echo "       请先运行: $0 backend"
  fi
  echo "[INFO] 启动 Qt: ${QT_APP}"
  cd "${QT_DIR}"
  exec ./scripts/run_linux.sh
}

start_gateway() {
  if [ ! -f "${GATEWAY_DIR}/bt_rehab_gateway.py" ]; then
    echo "[ERROR] 未找到蓝牙网关: ${GATEWAY_DIR}/bt_rehab_gateway.py"
    exit 1
  fi
  export REHAB_QT_STORAGE_DIR="${REHAB_QT_STORAGE_DIR:-${HOME}/.local/share/prograss_copy}"
  echo "[INFO] 启动蓝牙网关 (Qt 数据: ${REHAB_QT_STORAGE_DIR})"
  cd "${GATEWAY_DIR}"
  exec python3 bt_rehab_gateway.py --project-root "${RKNN_ROOT}"
}

show_status() {
  echo "=== RK3588 康复系统状态 ==="
  if [ -S "${SOCKET}" ]; then
    ls -l "${SOCKET}"
  else
    echo "Socket: 不存在 (${SOCKET})"
  fi
  if [ -f /tmp/rehab_backend.pid ] && kill -0 "$(cat /tmp/rehab_backend.pid)" 2>/dev/null; then
    echo "backend: 后台运行中 PID=$(cat /tmp/rehab_backend.pid)"
  elif [ -S "${SOCKET}" ]; then
    echo "backend: 运行中（前台或其它方式启动，无 pid 文件）"
  else
    echo "backend: 未运行"
  fi
  if [ -f /tmp/rehab_bt_gateway.pid ] && kill -0 "$(cat /tmp/rehab_bt_gateway.pid)" 2>/dev/null; then
    echo "gateway: 运行中 PID=$(cat /tmp/rehab_bt_gateway.pid)"
  else
    echo "gateway: 未运行"
  fi
  if pgrep -f "prograss_copy" >/dev/null 2>&1; then
    echo "qt: 运行中"
  else
    echo "qt: 未运行"
  fi
  echo "Qt 数据: ${HOME}/.local/share/prograss_copy/"
  echo "Backend 日志: /tmp/rehab_backend.log"
  echo "Gateway 日志: /tmp/rehab_bt_gateway.log"
}

tail_logs() {
  local target="${1:-backend}"
  case "$target" in
    backend)
      if [ ! -f /tmp/rehab_backend.log ]; then
        echo "[WARN] 无后台日志文件，若用前台 backend 请直接看启动终端"
        return 1
      fi
      tail -f /tmp/rehab_backend.log
      ;;
    gateway)
      if [ ! -f /tmp/rehab_bt_gateway.log ]; then
        echo "[WARN] 无 gateway 日志，请先: $0 gateway"
        return 1
      fi
      tail -f /tmp/rehab_bt_gateway.log
      ;;
    *)
      echo "用法: $0 logs [backend|gateway]"
      return 1
      ;;
  esac
}

stop_all() {
  for pf in /tmp/rehab_backend.pid /tmp/rehab_bt_gateway.pid; do
    if [ -f "$pf" ]; then
      pid="$(cat "$pf")"
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        echo "[INFO] 已停止 PID $pid"
      fi
      rm -f "$pf"
    fi
  done
  # 清理可能由前台 ./start_rk3588.sh 启动的进程
  if pgrep -f "python3 main.py --real.*--qt-service" >/dev/null 2>&1; then
    pkill -f "python3 main.py --real.*--qt-service" 2>/dev/null || true
    echo "[INFO] 已停止 rehab main.py 进程"
  fi
  rm -f "${SOCKET}" 2>/dev/null || true
}

cmd="${1:-all}"
case "$cmd" in
  backend)    start_backend 0 ;;
  backend-bg) start_backend 1 ;;
  qt)         start_qt ;;
  gateway)
    export REHAB_QT_STORAGE_DIR="${REHAB_QT_STORAGE_DIR:-${HOME}/.local/share/prograss_copy}"
    cd "${GATEWAY_DIR}"
    echo "[INFO] 前台启动蓝牙网关 (Ctrl+C 退出)"
    exec python3 bt_rehab_gateway.py --project-root "${RKNN_ROOT}"
    ;;
  gateway-bg)
    export REHAB_QT_STORAGE_DIR="${REHAB_QT_STORAGE_DIR:-${HOME}/.local/share/prograss_copy}"
    cd "${GATEWAY_DIR}"
    nohup python3 bt_rehab_gateway.py --project-root "${RKNN_ROOT}" > /tmp/rehab_bt_gateway.log 2>&1 &
    echo $! > /tmp/rehab_bt_gateway.pid
    echo "[INFO] gateway PID=$(cat /tmp/rehab_bt_gateway.pid), 日志: /tmp/rehab_bt_gateway.log"
    ;;
  all)
    start_backend 1
    if [ "${START_BT_GATEWAY:-1}" = "1" ] && [ -f "${GATEWAY_DIR}/bt_rehab_gateway.py" ]; then
      REHAB_QT_STORAGE_DIR="${HOME}/.local/share/prograss_copy" \
        nohup python3 "${GATEWAY_DIR}/bt_rehab_gateway.py" --project-root "${RKNN_ROOT}" \
        > /tmp/rehab_bt_gateway.log 2>&1 &
      echo $! > /tmp/rehab_bt_gateway.pid
      echo "[INFO] gateway PID=$(cat /tmp/rehab_bt_gateway.pid)"
    fi
    start_qt
    ;;
  status) show_status ;;
  logs)   tail_logs "${2:-backend}" ;;
  stop)   stop_all ;;
  -h|--help|help) usage ;;
  *) echo "未知命令: $cmd"; usage; exit 1 ;;
esac
