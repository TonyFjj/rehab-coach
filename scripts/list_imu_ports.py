#!/usr/bin/env python3
"""列出 IMU 串口及推荐配置。"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO_ROOT, 'src', 'backend')
sys.path.insert(0, BACKEND)

from interface.imu_port_detect import (  # noqa: E402
    autodetect_dual_ports,
    list_imu_ports,
    resolve_imu_ports,
)


def main():
    by_id, acm = list_imu_ports()
    print('=== /dev/serial/by-id ===')
    if by_id:
        for p in by_id:
            print(f'  {p} -> {os.path.realpath(p)}')
    else:
        print('  (无)')

    print('\n=== /dev/ttyACM* ===')
    if acm:
        for p in acm:
            print(f'  {p}')
    else:
        print('  (无)')

    print('\n=== 自动解析 ===')
    ports = resolve_imu_ports({'left': 'auto', 'right': 'auto'})
    print(f"  left : {ports['left']}")
    print(f"  right: {ports['right']}")

    print('\n=== config/imu_config.yaml 建议 ===')
    if len(by_id) >= 2:
        print('ports:')
        print(f"  left: {by_id[0]}")
        print(f"  right: {by_id[1]}")
    elif autodetect_dual_ports(verbose=False):
        p = autodetect_dual_ports(verbose=False)
        print('ports:')
        print(f"  left: {p['left']}")
        print(f"  right: {p['right']}")
    else:
        print('ports:')
        print('  left: auto')
        print('  right: auto')


if __name__ == '__main__':
    main()
