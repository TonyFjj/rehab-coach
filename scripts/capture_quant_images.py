#!/usr/bin/env python3
"""
采集 RKNN INT8 量化用代表图（建议 50～100 张）。

用法（项目根目录）:
  python3 scripts/capture_quant_images.py --guided --count 80 --interval 2 --preview
  python3 scripts/capture_quant_images.py --device 21 --guided --count 80 --preview
  python3 scripts/capture_quant_images.py --auto --count 60 --interval 1.5 --preview

输出:
  models/quant_images/quant_0001.jpg ...
  models/rknn_pose_dataset.txt
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import cv2
except ImportError:
    print("请先安装: pip install opencv-python")
    sys.exit(1)

GUIDED_PHASES = [
    ("站立自然", "面向相机，双手自然下垂", 8),
    ("肩前屈/上举", "双手从体前向上举至头顶", 12),
    ("肩外展", "双手向两侧平举、举高", 10),
    ("半蹲", "缓慢下蹲再站起", 10),
    ("躯干旋转", "双手平举，左右转体", 10),
    ("迈步", "前后左右各迈一步并收脚", 12),
    ("单脚平衡", "抬脚保持，左右各试", 8),
    ("远近/侧身", "稍近稍远或略侧身，大半身入镜", 10),
]


def load_camera_settings(config_path: Optional[str], device_override=None) -> dict:
    from vision.camera_config_loader import (
        build_camera_runtime_config,
        camera_yaml_path,
        load_camera_yaml,
    )

    config_dir = os.path.join(ROOT, "config")
    if config_path and os.path.isfile(config_path):
        yaml_path, raw = load_camera_yaml(config_dir, config_path)
    else:
        yaml_path = camera_yaml_path(config_dir)
        _, raw = load_camera_yaml(config_dir, yaml_path)

    settings = build_camera_runtime_config(
        raw,
        ROOT,
        device_override=device_override,
    )
    print(f"[Config] {yaml_path}")
    print(
        f"[Config] device_id={settings.get('device_id')} "
        f"auto_detect={settings.get('auto_detect')} "
        f"path={settings.get('device_path') or '-'} "
        f"{settings.get('width')}x{settings.get('height')}"
    )
    return settings


def open_camera(settings: dict):
    from vision.camera_manager import CameraManager

    cam = CameraManager(
        device_id=settings.get("device_id", "auto"),
        width=int(settings.get("width", 2560)),
        height=int(settings.get("height", 720)),
        fps=int(settings.get("fps", 30)),
        mode=settings.get("mode", "single_device"),
        camera_model=settings.get("camera_model", "AR0144"),
        calibration_file=settings.get("calibration_file", "config/stereo_calib.json"),
        simulate=False,
        rectify=bool(settings.get("rectify", False)),
        rectify_alpha=float(settings.get("rectify_alpha", 0.0)),
        rectify_crop=bool(settings.get("rectify_crop", True)),
        rectify_preview=bool(settings.get("rectify_preview", False)),
        auto_detect=bool(settings.get("auto_detect", True)),
        max_probe=int(settings.get("max_probe", 32)),
        device_path=str(settings.get("device_path", "") or ""),
        open_retries=int(settings.get("open_retries", 3)),
        hub_warmup_sec=float(settings.get("hub_warmup_sec", 1.0)),
    )
    if not cam.open():
        raise RuntimeError(
            "CameraManager 打开失败。"
            "请确认 USB 相机已接好，或运行: python3 scripts/list_cameras.py"
        )
    print("[Camera] CameraManager 已打开")
    return cam, "manager"


def read_frame(handle, backend: str) -> Optional[Tuple[object, object]]:
    if backend == "manager":
        ok, left, right = handle.read()
        if not ok or (left is None and right is None):
            return None
        return left, right

    ok, frame = handle.read()
    if not ok or frame is None:
        return None
    h, w = frame.shape[:2]
    if w >= h * 1.8:
        mid = w // 2
        return frame[:, :mid].copy(), frame[:, mid:].copy()
    return frame, None


def pick_left_frame(left, right):
    if left is not None:
        return left
    return right


def save_image(img, out_dir: str, index: int) -> str:
    path = os.path.join(out_dir, f"quant_{index:04d}.jpg")
    cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return os.path.abspath(path)


def write_dataset_txt(paths: List[str], dataset_file: str):
    os.makedirs(os.path.dirname(dataset_file) or ".", exist_ok=True)
    with open(dataset_file, "w", encoding="utf-8") as f:
        for p in paths:
            f.write(p + "\n")
    print(f"[OK] {dataset_file} ({len(paths)} 张)")


def run_capture(args):
    device_override = args.device
    if device_override is not None and str(device_override).lower() in ("auto", ""):
        device_override = "auto"

    settings = load_camera_settings(
        args.config if os.path.isfile(args.config) else None,
        device_override=device_override,
    )
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    dataset_file = (
        args.dataset_txt
        if os.path.isabs(args.dataset_txt)
        else os.path.join(ROOT, args.dataset_txt)
    )

    handle, backend = open_camera(settings)
    saved_paths: List[str] = []
    existing = sorted(
        f for f in os.listdir(out_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if existing and not args.overwrite:
        for fn in existing:
            saved_paths.append(os.path.join(out_dir, fn))
        index = len(existing) + 1
        print(f"[INFO] 已有 {len(existing)} 张，续拍从 #{index}")
    else:
        index = 1
        if args.overwrite:
            for fn in existing:
                try:
                    os.remove(os.path.join(out_dir, fn))
                except OSError:
                    pass

    phase_idx = phase_saved = 0
    last_auto = 0.0
    win = "Quant Capture (q=quit, SPACE=save)"
    use_preview = args.preview and os.environ.get("DISPLAY")
    if args.preview and not use_preview:
        print("[WARN] 无 DISPLAY，已关闭预览窗口，仅自动/引导存图")

    if use_preview:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    def hints():
        if args.guided and phase_idx < len(GUIDED_PHASES):
            t, d, _ = GUIDED_PHASES[phase_idx]
            return [f"[引导] {t}", d]
        mode = "[自动] 做康复动作" if args.auto else "[交互] 空格拍照"
        return [mode, f"已存 {len(saved_paths)}/{args.count}"]

    print("\n=== RKNN 量化代表图采集 ===")
    print(f"目标 {args.count} 张 -> {out_dir}\n")

    try:
        while len(saved_paths) < args.count:
            pair = read_frame(handle, backend)
            if pair is None:
                time.sleep(0.02)
                continue
            left, right = pair
            img = pick_left_frame(left, right)
            if img is None:
                continue

            do_save = False
            now = time.time()
            if args.auto or args.guided:
                if now - last_auto >= args.interval:
                    do_save = True
                    last_auto = now

            if use_preview:
                vis = img.copy()
                y = 28
                for line in hints():
                    cv2.putText(
                        vis, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 0), 2,
                    )
                    y += 24
                cv2.imshow(win, vis)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("[INFO] 用户退出")
                    break
                if key == ord(" ") and not (args.auto or args.guided):
                    do_save = True

            if do_save:
                path = save_image(img, out_dir, index)
                saved_paths.append(path)
                print(f"  [{len(saved_paths)}/{args.count}] {path}")
                index += 1
                phase_saved += 1
                if args.guided and phase_idx < len(GUIDED_PHASES):
                    _, _, need = GUIDED_PHASES[phase_idx]
                    if phase_saved >= need:
                        phase_idx += 1
                        phase_saved = 0
                        if phase_idx < len(GUIDED_PHASES):
                            t, d, _ = GUIDED_PHASES[phase_idx]
                            print(f"\n>>> 下一阶段: {t} — {d}\n")
    finally:
        if use_preview:
            cv2.destroyAllWindows()
        if backend == "manager":
            handle.close()

    if saved_paths:
        write_dataset_txt(saved_paths, dataset_file)
        if len(saved_paths) < 50:
            print("[WARN] 建议至少 50 张，可再次运行续拍")
        else:
            print("[OK] 数量满足量化建议")
    else:
        print("[WARN] 未保存任何图片")
    return 0 if saved_paths else 1


def main():
    p = argparse.ArgumentParser(description="采集 RKNN 量化代表图")
    default_yaml = os.path.join(ROOT, "config", "camera_config.rk3588.yaml")
    p.add_argument("--config", default=default_yaml, help="相机 yaml（板端默认 rk3588）")
    p.add_argument(
        "--device",
        default=None,
        help="覆盖 device_id，如 21 或 auto（默认读 yaml：auto_detect）",
    )
    p.add_argument("--out-dir", default=os.path.join(ROOT, "models", "quant_images"))
    p.add_argument(
        "--dataset-txt",
        default=os.path.join(ROOT, "models", "rknn_pose_dataset.txt"),
    )
    p.add_argument("--count", type=int, default=80)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--guided", action="store_true")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    if args.guided:
        args.auto = True
    if not args.auto and not args.guided:
        args.preview = True
    return run_capture(args)


if __name__ == "__main__":
    sys.exit(main())
