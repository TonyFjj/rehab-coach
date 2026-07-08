"""
IMU 串口自动检测（拓展坞 / USB Hub 下 ttyACM 编号常变化）

优先 /dev/serial/by-id 稳定路径，其次按 ttyACM 编号排序取前两个。
"""

import glob
import os
from typing import Dict, Optional, Tuple


def _is_auto(value) -> bool:
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ('', 'auto', 'any', '-1')


def _list_by_id_ports() -> list:
    by_id = '/dev/serial/by-id'
    if not os.path.isdir(by_id):
        return []
    ports = []
    for name in sorted(os.listdir(by_id)):
        lower = name.lower()
        if not (
            'nordic' in lower
            or 'wit' in lower
            or 'ch340' in lower
            or 'cp210' in lower
            or 'usb_serial' in lower
            or 'cdc' in lower
        ):
            continue
        path = os.path.join(by_id, name)
        if os.path.islink(path):
            ports.append(path)
    return ports


def _list_ttyacm_ports() -> list:
    return sorted(glob.glob('/dev/ttyACM*'))


def autodetect_dual_ports(verbose: bool = True) -> Optional[Dict[str, str]]:
    """返回 left/right 串口路径；至少需要 2 个 ACM 设备。"""
    by_id = _list_by_id_ports()
    if len(by_id) >= 2:
        left, right = by_id[0], by_id[1]
        if verbose:
            print(f'[IMU] 自动检测 by-id: L={left}')
            print(f'[IMU] 自动检测 by-id: R={right}')
        return {'left': left, 'right': right}

    acm = _list_ttyacm_ports()
    if len(acm) >= 2:
        left, right = acm[0], acm[1]
        if verbose:
            print(f'[IMU] 自动检测 ttyACM: L={left} R={right}')
        return {'left': left, 'right': right}

    if verbose and acm:
        print(f'[IMU] 仅发现 {len(acm)} 个串口: {acm}')
    elif verbose:
        print('[IMU] 未发现 ttyACM 设备')
    return None


def resolve_imu_ports(
    ports_cfg: Optional[Dict[str, str]] = None,
    verbose: bool = True,
) -> Dict[str, str]:
    """
    解析 IMU 左右端口。
    环境变量 IMU_LEFT / IMU_RIGHT 优先；
    配置 ports.left/right 为 auto 时自动扫描。
    """
    env_left = os.environ.get('IMU_LEFT', '').strip()
    env_right = os.environ.get('IMU_RIGHT', '').strip()
    if env_left and env_right:
        if verbose:
            print(f'[IMU] 环境变量: L={env_left} R={env_right}')
        return {'left': env_left, 'right': env_right}

    cfg = ports_cfg or {}
    left = str(cfg.get('left', 'auto')).strip()
    right = str(cfg.get('right', 'auto')).strip()

    if not _is_auto(left) and not _is_auto(right):
        if os.path.exists(left) and os.path.exists(right):
            return {'left': left, 'right': right}
        if verbose:
            print(
                f'[IMU] 配置的串口不存在 (L={left} R={right})，尝试自动检测'
            )
        detected = autodetect_dual_ports(verbose=verbose)
        if detected:
            return detected
        return {'left': left, 'right': right}

    detected = autodetect_dual_ports(verbose=verbose)
    if detected:
        if not _is_auto(left):
            detected['left'] = left
        if not _is_auto(right):
            detected['right'] = right
        return detected

    return {
        'left': left if not _is_auto(left) else '/dev/ttyACM0',
        'right': right if not _is_auto(right) else '/dev/ttyACM1',
    }


def list_imu_ports() -> Tuple[list, list]:
    """(by-id 列表, ttyACM 列表)"""
    return _list_by_id_ports(), _list_ttyacm_ports()
