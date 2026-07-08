#!/usr/bin/env python3
"""列出当前系统可用摄像头及推荐配置。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from vision.camera_detect import (  # noqa: E402
    _has_video_capture,
    _linux_video_names,
    find_usb_camera_by_id,
    iter_candidate_indices,
    probe_device,
)


def main():
    print('=== V4L2 设备列表 ===')
    named = _linux_video_names(64)
    if not named:
        print('未发现 /sys/class/video4linux 节点')
    for idx, name in named:
        cap_ok = _has_video_capture(idx)
        tag = 'CAPTURE' if cap_ok else 'skip'
        print(f'  /dev/video{idx:2d}  [{tag:7s}]  {name or "(无名称)"}')

    print('\n=== /dev/v4l/by-id (USB 稳定路径) ===')
    by_id = '/dev/v4l/by-id'
    if os.path.isdir(by_id):
        usb = [n for n in sorted(os.listdir(by_id)) if n.startswith('usb-')]
        if usb:
            for name in usb:
                path = os.path.join(by_id, name)
                real = os.path.realpath(path)
                print(f'  {path}\n    -> {real}')
        else:
            print('  (未找到 usb-* 设备，请确认 USB 摄像头已插入)')
    else:
        print('  目录不存在')

    stable = find_usb_camera_by_id()
    if stable:
        print(f'\n推荐 device_path: {stable}')

    print('\n=== 自动探测可出帧设备 ===')
    for idx in iter_candidate_indices(32):
        name = dict(named).get(idx, '')
        result = probe_device(idx, camera_model='CCB', device_name=name)
        if result:
            print(
                f'  video{idx} OK {result["width"]}x{result["height"]} '
                f'score={result["score"]:.1f}  {name}'
            )

    print('\n=== 配置建议 (config/camera_config.rk3588.yaml) ===')
    print('  device_id: auto')
    print('  device_path: auto')
    print('  auto_detect: true')
    print('  max_probe: 32')
    print('\n或临时指定:')
    print('  export CAMERA_DEVICE=21')
    print('  # 或 export CAMERA_DEVICE=/dev/v4l/by-id/usb-...-video-index0')


if __name__ == '__main__':
    main()
