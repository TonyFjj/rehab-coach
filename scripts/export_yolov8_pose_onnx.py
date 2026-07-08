"""
将 yolov8n-pose.pt 导出为 ONNX（Windows / Linux 均可）。

用法（项目根目录）:
  python scripts/export_yolov8_pose_onnx.py
  python scripts/export_yolov8_pose_onnx.py --pt models/yolov8n-pose.pt --imgsz 640

输出默认: models/yolov8n-pose.onnx
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser(description='导出 YOLOv8-Pose ONNX')
    parser.add_argument(
        '--pt',
        default=os.path.join(ROOT, 'yolov8n-pose.pt'),
        help='Ultralytics .pt 路径',
    )
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument(
        '--out-dir',
        default=os.path.join(ROOT, 'models'),
        help='ONNX 输出目录',
    )
    args = parser.parse_args()

    if not os.path.isfile(args.pt):
        print(f"错误: 找不到 {args.pt}")
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("请先安装: pip install ultralytics")
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    print(f"加载 {args.pt} ...")
    model = YOLO(args.pt)
    print(f"导出 ONNX imgsz={args.imgsz} ...")
    out = model.export(
        format='onnx',
        imgsz=args.imgsz,
        simplify=True,
        opset=12,
    )
    out_path = str(out)
    target = os.path.join(args.out_dir, 'yolov8n-pose.onnx')
    if os.path.abspath(out_path) != os.path.abspath(target):
        import shutil
        shutil.copy2(out_path, target)
        print(f"已复制到 {target}")
    else:
        print(f"ONNX: {out_path}")

    print("\n下一步（须在 x86 Linux + rknn-toolkit2 上）:")
    print("  python scripts/convert_yolov8_pose_rknn.py")
    return 0


if __name__ == '__main__':
    sys.exit(main())
