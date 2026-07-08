#!/usr/bin/env bash
# RK3588 蓝牙：可被发现 + 配对代理（供手机 App 连接）
set -euo pipefail

echo "[1/3] 检查 bluez / PyBluez"
if ! command -v bluetoothctl >/dev/null; then
  echo "请先: sudo apt install -y bluez python3-bluez"
  exit 1
fi
python3 -c "import bluetooth" 2>/dev/null || {
  echo "请先: sudo apt install -y python3-bluez"
  exit 1
}

echo "[2/3] 配置蓝牙可被发现、可配对"
sudo bluetoothctl <<'EOF'
power on
agent on
default-agent
discoverable on
pairable on
show
EOF

echo
echo "[3/3] 完成。接下来在另一个终端启动网关："
echo "  cd ~/Desktop/rknn && ./start_rk3588_system.sh gateway"
echo
echo "手机端：App → 设置 → 扫描周围设备 → 选 RK3588/elf2-desktop → 连接"
echo "（未配对设备会先弹出系统配对框，点配对/确认即可）"
