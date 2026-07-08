#!/usr/bin/env bash
# 在 Windows/Android Studio 或已配置 JDK+SDK 的环境编译 APK。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE="${ROOT}/app/mobile"
OUT_APK="${ROOT}/app/居家康复助手.apk"
BUILD_ID="20260621"

echo "[build] App BUILD_ID=${BUILD_ID}"
echo "[build] 请在 Android Studio 打开: ${MOBILE}"
echo "[build] 或使用 gradle:"

if [ ! -d "${MOBILE}" ]; then
  echo "[ERROR] 未找到 ${MOBILE}"
  exit 1
fi

if [ -x "${MOBILE}/gradlew" ]; then
  cd "${MOBILE}"
  ./gradlew assembleDebug
  DEBUG_APK="${MOBILE}/app/build/outputs/apk/debug/app-debug.apk"
  if [ -f "${DEBUG_APK}" ]; then
    cp -f "${DEBUG_APK}" "${OUT_APK}"
    echo "[OK] 已复制到 ${OUT_APK}"
    ls -la "${OUT_APK}"
    exit 0
  fi
fi

cat <<EOF

未找到可执行的 gradlew，请在 Windows 上操作：

1. Android Studio 打开文件夹: app/mobile
2. Build -> Build APK(s)
3. 将生成的 app-debug.apk 复制为:
   ${OUT_APK}
4. 安装到手机后，在 App 设置页应看到版本: ${BUILD_ID}

本次源码关键修复:
- 蓝牙优先 RFCOMM channel 1（匹配 RK3588 网关）
- 接收改用 byte 流，避免大 JSON 断行
- 日志截断 + 后台解析 JSON

EOF
