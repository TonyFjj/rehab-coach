#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${PROJECT_DIR}/build-linux/prograss_copy"
GIF_DIR="${PROJECT_DIR}/build-linux/res/pic/training_gifs"

if [ ! -x "${APP}" ]; then
  if [ -f "${APP}" ]; then
    chmod +x "${APP}"
  else
    echo "未找到可执行文件，先执行: ${PROJECT_DIR}/scripts/build_linux.sh"
    exit 1
  fi
fi

export LANG="${LANG:-zh_CN.UTF-8}"
export LC_ALL="${LC_ALL:-${LANG}}"

# 桌面 Linux 默认走 xcb；Wayland 环境若有问题可自动回退。
if [ -z "${QT_QPA_PLATFORM:-}" ]; then
  if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM="wayland;xcb"
  else
    export QT_QPA_PLATFORM="xcb"
  fi
fi

cd "${PROJECT_DIR}"

# GIF 解码依赖 Qt imageformats 插件（libqgif.so，随 libqt5gui5 提供，无需 libqt5imageformats5）
QT_PLUGINS=""
if [ -d /usr/lib/aarch64-linux-gnu/qt5/plugins/imageformats ]; then
  QT_PLUGINS="/usr/lib/aarch64-linux-gnu/qt5/plugins"
elif [ -d /usr/lib/x86_64-linux-gnu/qt5/plugins/imageformats ]; then
  QT_PLUGINS="/usr/lib/x86_64-linux-gnu/qt5/plugins"
fi
if [ -n "${QT_PLUGINS}" ]; then
  export QT_PLUGIN_PATH="${QT_PLUGINS}${QT_PLUGIN_PATH:+:${QT_PLUGIN_PATH}}"
fi

mkdir -p "${PROJECT_DIR}/build-linux/res/pic"
if [ ! -e "${GIF_DIR}" ]; then
  ln -sf "${PROJECT_DIR}/res/pic/training_gifs" "${GIF_DIR}" 2>/dev/null || true
fi
export REHAB_GIF_DIR="${REHAB_GIF_DIR:-${GIF_DIR}}"

LIBQGIF=""
for p in \
  /usr/lib/aarch64-linux-gnu/qt5/plugins/imageformats/libqgif.so \
  /usr/lib/x86_64-linux-gnu/qt5/plugins/imageformats/libqgif.so; do
  if [ -f "${p}" ]; then
    LIBQGIF="${p}"
    break
  fi
done

echo "[Qt] build-linux/prograss_copy"
echo "[Qt] REHAB_GIF_DIR=${REHAB_GIF_DIR}"
echo "[Qt] QT_PLUGIN_PATH=${QT_PLUGIN_PATH:-（未设置）}"
if [ -n "${LIBQGIF}" ]; then
  echo "[Qt] GIF 插件: ${LIBQGIF}"
elif [ -z "${QT_PLUGINS}" ]; then
  echo "[提示] 未找到 Qt imageformats 插件目录，训练 GIF 可能无法播放。"
  echo "       Ubuntu 请确认已安装: sudo apt install -y libqt5gui5"
fi
if [ ! -d "${REHAB_GIF_DIR}" ]; then
  echo "[WARN] GIF 目录不存在: ${REHAB_GIF_DIR}"
fi

exec "${APP}"
