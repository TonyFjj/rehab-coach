#!/usr/bin/env python3
"""板端快速验证 RKNN 姿态模型是否可用（max score > 0 且能解出关键点）。"""

import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', default=os.path.join(ROOT, 'models', 'yolov8n-pose.rknn'))
    p.add_argument('--image', default='')
    args = p.parse_args()

    try:
        import cv2
        from vision.pose_rknn import RknnPoseBackend
    except ImportError as e:
        print(f'依赖缺失: {e}')
        return 1

    img_path = args.image
    if not img_path:
        imgs = sorted(glob.glob(os.path.join(ROOT, 'models', 'quant_images', '*.jpg')))
        img_path = imgs[0] if imgs else ''
    if not img_path or not os.path.isfile(img_path):
        print('请指定 --image 或放置 models/quant_images/*.jpg')
        return 1

    img = cv2.imread(img_path)
    backend = RknnPoseBackend(args.model, conf_threshold=0.5)
    res = backend.detect(img)
    backend.release()

    print(f'model: {args.model}')
    print(f'image: {img_path}')
    if res is None:
        print('[FAIL] conf>=0.5 无检测 — 模型可能量化损坏（INT8 全量化时 conf 常为 0）')
        print('  建议: WSL 用 hybrid 重转 bash scripts/wsl_convert_rknn.sh')
        return 1

    n = len(res.get('keypoints_2d') or {})
    print(f'[OK] person_conf={res["person_conf"]:.3f} keypoints={n}')
    ls = res['keypoints_2d'].get('left_shoulder')
    if ls:
        print(f'  left_shoulder: x={ls["x"]:.1f} y={ls["y"]:.1f} conf={ls["conf"]:.3f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
