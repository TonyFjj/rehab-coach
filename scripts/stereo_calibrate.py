"""
双目标定（棋盘格）

用法（项目根目录）:
  # Windows 笔记本 + AR0144（读 config/camera_config.yaml）
  python scripts/stereo_calibrate.py

  # RK3588 板端
  python scripts/stereo_calibrate.py --config config/camera_config.rk3588.yaml

  # 指定 device
  python scripts/stereo_calibrate.py --device 21

标定结果: config/stereo_calib.json（与 yaml 中 calibration_file 一致）
备份目录: yaml 中 calibration.output_dir（默认 calibration/）
"""

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from vision.camera_config_loader import (
    build_camera_runtime_config,
    camera_yaml_path,
    is_rk3588_board,
    load_camera_yaml,
)
from vision.camera_manager import CameraManager


def _resolve_path(path: str) -> str:
    if not path:
        return path
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(ROOT, path))


def build_settings(raw: dict, device_override=None, force_auto: bool = False) -> dict:
    cam_cfg = build_camera_runtime_config(
        raw,
        ROOT,
        device_override=device_override,
        force_auto=force_auto,
    )
    cam = raw.get('camera', raw)
    cal = raw.get('calibration', {})
    output_dir = _resolve_path(cal.get('output_dir', 'calibration/'))
    pattern = cal.get('pattern_size', [9, 6])
    if isinstance(pattern, (list, tuple)) and len(pattern) >= 2:
        pattern_size = (int(pattern[0]), int(pattern[1]))
    else:
        pattern_size = (9, 6)

    return {
        'camera': cam_cfg,
        'calibration': {
            'pattern_size': pattern_size,
            'square_size_mm': float(cal.get('square_size_mm', 28)),
            'num_images': int(cal.get('num_images', 40)),
            'output_dir': output_dir,
            'baseline_mm': float(cam.get('baseline_mm', 52)),
            'camera_model': cam.get('model', 'AR0144'),
            'interface': cam.get('interface', 'USB'),
        },
    }


def backup_calibration(calib_path: str, output_dir: str, meta: dict):
    os.makedirs(output_dir, exist_ok=True)
    if os.path.isfile(calib_path):
        stamp_name = 'stereo_calib.json'
        backup_path = os.path.join(output_dir, stamp_name)
        shutil.copy2(calib_path, backup_path)
        meta_path = os.path.join(output_dir, 'calibration_meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"[Calibrate] 备份: {backup_path}")
        print(f"[Calibrate] 元数据: {meta_path}")


def main():
    parser = argparse.ArgumentParser(description='AR0144 双目标定（棋盘格）')
    parser.add_argument(
        '--config',
        default=None,
        help='相机/标定 yaml（RK3588 默认 camera_config.rk3588.yaml）',
    )
    parser.add_argument(
        '--device', type=int, default=None,
        help='覆盖 yaml 中的 device_id（板端常用，如 21）',
    )
    parser.add_argument(
        '--auto', action='store_true',
        help='强制自动扫描 USB 摄像头（等同 device_id: auto）',
    )
    parser.add_argument(
        '--num-images', type=int, default=None,
        help='覆盖 yaml 中的 num_images',
    )
    parser.add_argument(
        '--square-mm', type=float, default=None,
        help='覆盖 yaml 中的 square_size_mm',
    )
    args = parser.parse_args()

    cfg_path = _resolve_path(args.config) if args.config else camera_yaml_path(
        os.path.join(ROOT, 'config')
    )
    if not os.path.isfile(cfg_path):
        print(f"[Calibrate] 错误: 找不到配置文件 {cfg_path}")
        return 1

    _, raw = load_camera_yaml(os.path.join(ROOT, 'config'), cfg_path)
    settings = build_settings(
        raw,
        device_override=args.device,
        force_auto=args.auto,
    )
    cam_cfg = settings['camera']
    cal_cfg = settings['calibration']

    if args.num_images is not None:
        cal_cfg['num_images'] = args.num_images
    if args.square_mm is not None:
        cal_cfg['square_size_mm'] = args.square_mm

    print('=' * 60)
    print('  AR0144 双目标定')
    print('=' * 60)
    print(f"  配置: {cfg_path}")
    print(f"  设备: {cam_cfg['device_id']}  auto_detect={cam_cfg['auto_detect']}")
    if is_rk3588_board():
        print('  平台: RK3588/Linux（V4L2 + 自动跳过板载 MIPI 节点）')
    print(f"  分辨率: {cam_cfg['width']}x{cam_cfg['height']} @ {cam_cfg['fps']}fps")
    print(f"  棋盘格: {cal_cfg['pattern_size']}  格宽: {cal_cfg['square_size_mm']}mm")
    print(f"  采集帧数: {cal_cfg['num_images']}")
    print(f"  rectify: {cam_cfg['rectify']}  alpha: {cam_cfg['rectify_alpha']}")
    print(f"  输出: {cam_cfg['calibration_file']}")
    print('=' * 60)
    print('  操作: 在摄像头前移动棋盘格，按 q 取消')
    print('=' * 60)

    camera = CameraManager(
        device_id=cam_cfg['device_id'],
        width=cam_cfg['width'],
        height=cam_cfg['height'],
        fps=cam_cfg['fps'],
        mode=cam_cfg['mode'],
        camera_model=cam_cfg['camera_model'],
        calibration_file=cam_cfg['calibration_file'],
        auto_detect=cam_cfg['auto_detect'],
        max_probe=cam_cfg['max_probe'],
        rectify=cam_cfg['rectify'],
        rectify_alpha=cam_cfg['rectify_alpha'],
    )

    if not camera.open():
        print('[Calibrate] 打开摄像头失败')
        if is_rk3588_board():
            print(
                '[Calibrate] 提示: 可尝试 '
                'python3 scripts/stereo_calibrate.py --auto '
                '或 --device 21'
            )
        return 1

    ok = camera.calibrate_stereo(
        chess_size=cal_cfg['pattern_size'],
        square_size=cal_cfg['square_size_mm'],
        num_frames=cal_cfg['num_images'],
        save=True,
        baseline_mm=cal_cfg['baseline_mm'],
        camera_model=cal_cfg['camera_model'],
        interface=cal_cfg['interface'],
    )
    camera.close()

    if not ok:
        print('[Calibrate] 标定失败或被取消')
        return 1

    meta = {
        'config_file': cfg_path,
        'pattern_size': list(cal_cfg['pattern_size']),
        'square_size_mm': cal_cfg['square_size_mm'],
        'num_images': cal_cfg['num_images'],
        'baseline_mm': cal_cfg['baseline_mm'],
        'camera_model': cal_cfg['camera_model'],
        'interface': cal_cfg['interface'],
        'rectify': cam_cfg['rectify'],
        'rectify_alpha': cam_cfg['rectify_alpha'],
        'reprojection_error': camera.calib_params.get('reprojection_error'),
    }
    backup_calibration(cam_cfg['calibration_file'], cal_cfg['output_dir'], meta)

    err = camera.calib_params.get('reprojection_error', 0)
    print(f'[Calibrate] 完成，重投影误差: {err:.4f}')
    if err > 1.5:
        print('[Calibrate] 警告: 误差偏大，建议增加采集帧数或检查棋盘格尺寸')
    if not cam_cfg['rectify']:
        print(
            '[Calibrate] 当前 rectify=false，运行时不做立体校正。'
            '确认画面正常后可在 yaml 设 rectify: true'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
