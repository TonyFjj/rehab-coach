#!/usr/bin/env python3
"""
ONNX → RKNN（YOLOv8n-Pose，RK3588）。

须在 x86 Linux + rknn-toolkit2 上运行（Windows 请用 WSL + wsl_convert_rknn.sh）。

YOLOv8-Pose 全 INT8 会把置信度/关键点 sigmoid 压成 0，板端无法检出人体。
RK3588 默认使用 hybrid 量化（检测头 INT8 + pose 头 FP16），与 rknn_model_zoo 一致。

用法（项目根目录）:
  python scripts/convert_yolov8_pose_rknn.py \\
    --onnx models/yolov8n-pose.onnx \\
    --out models/yolov8n-pose-int8.rknn \\
    --dataset models/rknn_pose_dataset.txt

  python scripts/convert_yolov8_pose_rknn.py --no-quant --out models/yolov8n-pose-fp16.rknn
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# rk3588 hybrid：pose 分支激活保持 FP16（避免 conf/kpt 全 0）
HYBRID_LAYERS_RK3588 = [
    ['/model.22/cv4.0/cv4.0.0/act/Mul_output_0', '/model.22/Concat_6_output_0'],
    ['/model.22/cv4.1/cv4.1.0/act/Mul_output_0', '/model.22/Concat_6_output_0'],
    ['/model.22/cv4.2/cv4.2.0/act/Mul_output_0', '/model.22/Concat_6_output_0'],
]


def resolve_dataset(path: str, calib_dir: str | None) -> str:
    if calib_dir:
        images = sorted(
            glob.glob(os.path.join(calib_dir, '*.jpg'))
            + glob.glob(os.path.join(calib_dir, '*.jpeg'))
            + glob.glob(os.path.join(calib_dir, '*.png'))
        )
        if not images:
            raise FileNotFoundError(f'校准目录无图片: {calib_dir}')
        out = os.path.join(ROOT, 'models', '_rknn_calib_list.txt')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as f:
            for p in images:
                f.write(os.path.abspath(p) + '\n')
        print(f'[Calib] {len(images)} 张 -> {out}')
        return out

    if not path or not os.path.isfile(path):
        raise FileNotFoundError(
            f'找不到 dataset: {path}\n'
            '请指定 --dataset models/rknn_pose_dataset.txt 或 --calib-dir models/quant_images'
        )
    return os.path.abspath(path)


def convert(
    onnx_path: str,
    out_path: str,
    dataset: str,
    platform: str = 'rk3588',
    do_quant: bool = True,
    hybrid: bool = True,
) -> int:
    try:
        from rknn.api import RKNN
    except ImportError:
        print('错误: 需要 rknn-toolkit2（x86 Linux），板端 rknnlite 不能转换')
        print('  WSL: bash scripts/wsl_install_rknn.sh && source .venv-rknn-wsl/bin/activate')
        return 1

    onnx_path = os.path.abspath(onnx_path)
    out_path = os.path.abspath(out_path)
    if not os.path.isfile(onnx_path):
        print(f'错误: 找不到 ONNX: {onnx_path}')
        print('  Windows: python scripts/export_yolov8_pose_onnx.py')
        return 1

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    model_stem = os.path.splitext(os.path.basename(onnx_path))[0]

    rknn = RKNN(verbose=True)
    print(f'[RKNN] platform={platform} quant={do_quant} hybrid={hybrid and do_quant}')
    rknn.config(
        mean_values=[[0, 0, 0]],
        std_values=[[255, 255, 255]],
        target_platform=platform,
    )

    print(f'[RKNN] load_onnx {onnx_path}')
    if rknn.load_onnx(model=onnx_path) != 0:
        print('load_onnx 失败')
        return 1

    if not do_quant:
        print('[RKNN] build (no quant)')
        if rknn.build(do_quantization=False) != 0:
            print('build 失败')
            return 1
    elif hybrid and platform in ('rk3588', 'rk3576', 'rk3568', 'rk3566', 'rk3562'):
        print('[RKNN] hybrid_quantization_step1 (pose 头 FP16)')
        try:
            rknn.hybrid_quantization_step1(
                dataset=dataset,
                proposal=False,
                custom_hybrid=HYBRID_LAYERS_RK3588,
            )
        except Exception as e:
            print(f'[WARN] hybrid step1 失败 ({e})，回退全 INT8（可能板端 conf=0）')
            if rknn.build(do_quantization=True, dataset=dataset) != 0:
                print('build 失败')
                return 1
        else:
            rknn.release()
            rknn = RKNN(verbose=True)
            rknn.config(
                mean_values=[[0, 0, 0]],
                std_values=[[255, 255, 255]],
                target_platform=platform,
            )
            model_input = os.path.join(os.path.dirname(onnx_path), f'{model_stem}.model')
            data_input = os.path.join(os.path.dirname(onnx_path), f'{model_stem}.data')
            quant_cfg = os.path.join(os.path.dirname(onnx_path), f'{model_stem}.quantization.cfg')
            for p in (model_input, data_input, quant_cfg):
                if not os.path.isfile(p):
                    print(f'错误: hybrid 中间文件缺失: {p}')
                    return 1
            print('[RKNN] hybrid_quantization_step2')
            rknn.hybrid_quantization_step2(
                model_input=model_input,
                data_input=data_input,
                model_quantization_cfg=quant_cfg,
            )
    else:
        print('[RKNN] build INT8 (无 hybrid，pose 模型可能 conf 全 0)')
        if rknn.build(do_quantization=True, dataset=dataset) != 0:
            print('build 失败')
            return 1

    print(f'[RKNN] export -> {out_path}')
    if rknn.export_rknn(out_path) != 0:
        print('export 失败')
        return 1
    rknn.release()

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f'[OK] {out_path} ({size_mb:.2f} MB)')
    print('板端验证: python3 scripts/check_pose_rknn.py --model', out_path)
    return 0


def main():
    p = argparse.ArgumentParser(description='YOLOv8n-Pose ONNX → RKNN')
    p.add_argument('--onnx', default=os.path.join(ROOT, 'models', 'yolov8n-pose.onnx'))
    p.add_argument('--out', default=os.path.join(ROOT, 'models', 'yolov8n-pose-int8.rknn'))
    p.add_argument('--dataset', default=os.path.join(ROOT, 'models', 'rknn_pose_dataset.txt'))
    p.add_argument('--calib-dir', default='', help='校准图目录（自动生成 dataset 列表）')
    p.add_argument('--platform', default='rk3588')
    p.add_argument('--no-quant', action='store_true')
    p.add_argument('--no-hybrid', action='store_true', help='强制全 INT8（不推荐 pose）')
    args = p.parse_args()

    dataset = resolve_dataset(
        args.dataset,
        args.calib_dir or None,
    )
    return convert(
        args.onnx,
        args.out,
        dataset,
        platform=args.platform,
        do_quant=not args.no_quant,
        hybrid=not args.no_hybrid,
    )


if __name__ == '__main__':
    sys.exit(main())
