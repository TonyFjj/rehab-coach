"""
双目摄像头管理器
负责：
1. 打开/关闭双目摄像头
2. 同步采集左右画面
3. 立体标定（棋盘格）
4. 畸变矫正
"""

import os
import sys
import time
import json
import numpy as np
from typing import Tuple, Optional, Dict, Union

from .camera_detect import (
    is_auto_device,
    normalize_device_id,
    open_linux_capture,
    resolve_camera_open_target,
)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[Camera] OpenCV未安装，视觉功能不可用")
    print("[Camera] 安装命令: pip install opencv-python")


def _resolve_calibration_path(path: str) -> str:
    """相对路径解析到项目根目录（rehab-coach/），避免误存到盘符根目录。"""
    if os.path.isabs(path):
        return os.path.normpath(path)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.normpath(os.path.join(root, path))


class CameraManager:
    """
    双目摄像头管理器

    支持两种硬件方案：
    1. 单USB双目摄像头（左右画面拼在一帧中，如MYNT EYE/普通双目模组）
    2. 两个独立USB摄像头

    默认方案1：一个设备输出拼接画面，左右各一半
    """

    def __init__(
        self,
        device_id: Union[int, str] = 0,
        width: int = 1280,
        height: int = 480,
        fps: int = 30,
        mode: str = 'single_device',
        left_device_id: int = 0,
        right_device_id: int = 1,
        calibration_file: str = 'config/stereo_calib.json',
        camera_model: str = 'generic',
        simulate: bool = False,
        rectify: bool = True,
        rectify_alpha: float = 1.0,
        rectify_crop: bool = True,
        rectify_preview: bool = False,
        auto_detect: bool = False,
        max_probe: int = 32,
        device_path: str = '',
        open_retries: int = 3,
        hub_warmup_sec: float = 1.0,
    ):
        """
        Args:
            device_id: 设备 ID，或 'auto' / -1 表示自动检测
            device_path: /dev/v4l/by-id/... 或 auto（优先 USB 稳定路径）
            auto_detect: True 时启动前扫描可用摄像头（RK3588 推荐）
            max_probe: 自动检测时最多探测的 video 索引数量
        """
        self.device_id = normalize_device_id(device_id, 0)
        self.device_path = (device_path or '').strip()
        self.auto_detect = auto_detect or is_auto_device(self.device_id)
        self.camera_model = camera_model.upper()
        self.width = width
        self.height = height
        self.fps = fps
        self.mode = mode
        self.left_device_id = left_device_id
        self.right_device_id = right_device_id
        self.calibration_file = _resolve_calibration_path(calibration_file)
        self.simulate = simulate
        self.rectify_enabled = rectify
        self.rectify_alpha = float(rectify_alpha)
        self._rectify_crop = bool(rectify_crop)
        self.rectify_preview = bool(rectify_preview)
        self.max_probe = max(1, int(max_probe))
        self.open_retries = max(1, int(open_retries))
        self.hub_warmup_sec = max(0.0, float(hub_warmup_sec))
        self._mtx_l = self._dist_l = None
        self._mtx_r = self._dist_r = None
        self._R1 = self._R2 = self._P1 = self._P2 = None

        # 摄像头实例
        self._cap = None
        self._cap_left = None
        self._cap_right = None
        self._opened = False

        # 单目画面尺寸
        self.single_width = width // 2
        self.single_height = height

        # 标定参数
        self.calibrated = False
        self.calib_params: Dict = {}

        # 畸变矫正映射表（预计算，加速运行时矫正）
        self._map_left_x = None
        self._map_left_y = None
        self._map_right_x = None
        self._map_right_y = None
        self._common_roi = None

        # 帧计数
        self.frame_count = 0
        self._garbled_streak = 0
        self._ar0144_info: Dict = {}

        # 尝试加载已有标定文件
        self._load_calibration()

    # ==================== 打开/关闭 ====================

    def open(self) -> bool:
        """打开摄像头"""
        if self.simulate:
            print("[Camera] 模拟模式，不打开真实摄像头")
            self._opened = True
            return True

        if not HAS_CV2:
            print("[Camera] OpenCV未安装，无法打开摄像头")
            return False

        if self.mode == 'single_device' and (
            self.auto_detect
            or self.device_path
            or is_auto_device(self.device_id)
        ):
            picked = resolve_camera_open_target(
                device_id=self.device_id,
                device_path=self.device_path or 'auto',
                auto_detect=self.auto_detect or is_auto_device(self.device_id),
                target_w=self.width,
                target_h=self.height,
                fps=self.fps,
                camera_model=self.camera_model,
                max_probe=self.max_probe,
                verbose=True,
            )
            if picked is None:
                print("[Camera] 自动检测未找到摄像头")
                return False
            self.device_id = picked
            self.auto_detect = False

        open_target = self.device_id
        open_label = (
            open_target if isinstance(open_target, str)
            else str(int(open_target))
        )

        try:
            if self.mode == 'single_device':
                use_linux_v4l2 = sys.platform == 'linux'
                if self.camera_model == 'AR0144' and sys.platform == 'win32':
                    from .ar0144_dshow import (
                        open_ar0144,
                        flush_capture,
                        reapply_mjpg_mode,
                        read_frame,
                        is_garbled_frame,
                    )
                    self._cap, info = open_ar0144(
                        int(open_target) if not isinstance(open_target, str) else 0,
                        verbose=True
                    )
                    if self._cap is None:
                        print(f"[Camera] AR0144 打开失败 (设备 {open_label})")
                        return False
                    self._ar0144_info = info
                    actual_w = info.get('width', self.width)
                    actual_h = info.get('height', self.height)
                    actual_fps = info.get('measured_fps', self.fps)
                    reapply_mjpg_mode(self._cap, actual_w, actual_h)
                    flush_capture(self._cap, 20)
                    ok, probe = read_frame(self._cap)
                    if ok and is_garbled_frame(probe):
                        print(
                            "[Camera] 警告: 画面疑似花屏(MJPG未锁定)。"
                            "请用 AMCap 选 MJPG 2560×720，或运行 "
                            "python tests/test_camera.py"
                        )
                    codec = info.get('codec_guess', '?')
                    print("[Camera] AR0144 单设备双目打开成功")
                    print(
                        f"  分辨率: {actual_w}x{actual_h}, "
                        f"实测 FPS: {actual_fps:.1f}, 编码: {codec}"
                    )
                    if actual_w < 2000:
                        print(
                            "  提示: 宽度<2000 可能不是左右拼接双目，"
                            "检查 USB/驱动是否支持 2560×720 MJPG"
                        )
                elif use_linux_v4l2:
                    self._cap, actual_w, actual_h = open_linux_capture(
                        open_target,
                        target_w=self.width,
                        target_h=self.height,
                        fps=self.fps,
                        camera_model=self.camera_model,
                        retries=self.open_retries,
                        warmup_sec=self.hub_warmup_sec,
                    )
                    if self._cap is None:
                        print(
                            f"[Camera] V4L2 打开失败 (设备 {open_label})"
                        )
                        return False
                    actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
                    print("[Camera] V4L2 单设备双目打开成功")
                    print(
                        f"  设备: {open_label}, 分辨率: {actual_w}x{actual_h}, FPS: {actual_fps}"
                    )
                    if actual_w < 2000:
                        print(
                            "  提示: 宽度<2000 可能不是左右拼接双目，"
                            "检查 USB/驱动是否支持 2560×720 MJPG"
                        )
                else:
                    backend = 0
                    if sys.platform == 'linux' and hasattr(cv2, 'CAP_V4L2'):
                        backend = cv2.CAP_V4L2
                    if backend:
                        self._cap = cv2.VideoCapture(open_target, backend)
                    else:
                        self._cap = cv2.VideoCapture(open_target)
                    self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self._cap.set(cv2.CAP_PROP_FPS, self.fps)

                    if not self._cap.isOpened():
                        print(f"[Camera] 无法打开设备 {open_label}")
                        return False

                    actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
                    print("[Camera] 单设备双目打开成功")
                    print(f"  分辨率: {actual_w}x{actual_h}, FPS: {actual_fps}")

                self.width = actual_w
                self.height = actual_h
                self.single_width = actual_w // 2
                self.single_height = actual_h

            elif self.mode == 'dual_device':
                self._cap_left = cv2.VideoCapture(self.left_device_id)
                self._cap_right = cv2.VideoCapture(self.right_device_id)

                for cap, name in [
                    (self._cap_left, '左'),
                    (self._cap_right, '右')
                ]:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width // 2)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    cap.set(cv2.CAP_PROP_FPS, self.fps)

                    if not cap.isOpened():
                        print(f"[Camera] {name}摄像头打开失败")
                        return False

                print("[Camera] 双独立摄像头打开成功")

            self._opened = True
            return True

        except Exception as e:
            print(f"[Camera] 打开摄像头失败: {e}")
            return False

    def close(self):
        """关闭摄像头"""
        if self._cap:
            self._cap.release()
            self._cap = None
        if self._cap_left:
            self._cap_left.release()
            self._cap_left = None
        if self._cap_right:
            self._cap_right.release()
            self._cap_right = None

        self._opened = False
        print("[Camera] 摄像头已关闭")

    def is_opened(self) -> bool:
        return self._opened

    # ==================== 采集 ====================

    def read(self) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray]]:
        """
        采集一帧双目图像

        Returns:
            (success, left_frame, right_frame)
            left_frame, right_frame: shape (H, W, 3), BGR格式
        """
        if self.simulate:
            return self._read_simulate()

        if not self._opened:
            return False, None, None

        try:
            if self.mode == 'single_device':
                if self.camera_model == 'AR0144' and sys.platform == 'win32':
                    from .ar0144_dshow import (
                        read_frame,
                        is_garbled_frame,
                        reapply_mjpg_mode,
                        flush_capture,
                    )
                    ret, frame = read_frame(self._cap)
                    if ret and is_garbled_frame(frame):
                        self._garbled_streak += 1
                        if self._garbled_streak in (1, 8):
                            reapply_mjpg_mode(
                                self._cap, self.width, self.height
                            )
                            flush_capture(self._cap, 6)
                            ret, frame = read_frame(self._cap)
                    else:
                        self._garbled_streak = 0
                else:
                    ret, frame = self._cap.read()

                if not ret or frame is None:
                    return False, None, None

                # 左右分割
                mid = frame.shape[1] // 2
                left = frame[:, :mid, :]
                right = frame[:, mid:, :]

            elif self.mode == 'dual_device':
                ret_l, left = self._cap_left.read()
                ret_r, right = self._cap_right.read()
                if not ret_l or not ret_r:
                    return False, None, None

            else:
                return False, None, None

            # 立体校正：默认仅用于 3D（预览/姿态用原图，避免“放大”感）
            if self.calibrated and self.rectify_enabled and self.rectify_preview:
                left = self._rectify(left, 'left')
                right = self._rectify(right, 'right')
                left, right = self._apply_rectify_crop(left, right)

            self.frame_count += 1
            return True, left, right

        except Exception as e:
            print(f"[Camera] 采集失败: {e}")
            return False, None, None

    def _read_simulate(self):
        """模拟采集：生成假图像"""
        h, w = self.single_height, self.single_width
        left = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        right = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)

        # 画个简单的人形轮廓方便调试
        if HAS_CV2:
            for img in [left, right]:
                # 头
                cv2.circle(img, (w // 2, h // 4), 30, (0, 255, 0), 2)
                # 躯干
                cv2.line(img, (w // 2, h // 4 + 30),
                         (w // 2, h // 2 + 50), (0, 255, 0), 2)
                # 左臂
                cv2.line(img, (w // 2, h // 4 + 50),
                         (w // 3, h // 2), (0, 255, 0), 2)
                # 右臂
                cv2.line(img, (w // 2, h // 4 + 50),
                         (2 * w // 3, h // 2), (0, 255, 0), 2)

        self.frame_count += 1
        return True, left, right

    # ==================== 畸变矫正 ====================

    @staticmethod
    def _compute_common_roi(roi1, roi2) -> Tuple[int, int, int, int]:
        """左右眼校正后有效区域的交集。"""
        x1, y1, w1, h1 = roi1
        x2, y2, w2, h2 = roi2
        x = max(x1, x2)
        y = max(y1, y2)
        x_end = min(x1 + w1, x2 + w2)
        y_end = min(y1 + h1, y2 + h2)
        w = max(0, x_end - x)
        h = max(0, y_end - y)
        return (x, y, w, h)

    def _validate_rectify_maps(self, img_size):
        """启动时检查左右目 remap 是否大面积黑屏。"""
        if not HAS_CV2 or self._map_left_x is None:
            return
        probe = np.full((img_size[1], img_size[0], 3), 128, np.uint8)
        left = cv2.remap(
            probe, self._map_left_x, self._map_left_y,
            cv2.INTER_LINEAR, borderValue=(0, 0, 0),
        )
        right = cv2.remap(
            probe, self._map_right_x, self._map_right_y,
            cv2.INTER_LINEAR, borderValue=(0, 0, 0),
        )
        vl = float((left.sum(axis=2) > 0).mean())
        vr = float((right.sum(axis=2) > 0).mean())
        if vl < 0.3 or vr < 0.3:
            print(
                f"[Camera] 警告: 立体校正后有效画面过小 "
                f"(左={vl:.0%}, 右={vr:.0%}, alpha={self.rectify_alpha})。"
            )
            print(
                "[Camera] 右目全黑时请将 rectify_alpha 调到 0.5 左右，"
                "或设 rectify: false 先用 2D；重新标定前勿用 alpha=1.0"
            )

    def _update_rectify_roi(self, roi1, roi2, img_size):
        self._common_roi = self._compute_common_roi(roi1, roi2)
        x, y, w, h = self._common_roi
        if not self.rectify_enabled:
            return
        if w <= 0:
            print(
                f"[Camera] 警告: rectify_alpha={self.rectify_alpha} 下 "
                f"无有效裁剪区 roi1={roi1}, roi2={roi2}，右目可能全黑"
            )
            return
        offset_ratio = x / max(1, img_size[0])
        if offset_ratio > 0.15:
            print(
                f"[Camera] 立体校正有效区偏移: roi1={roi1}, roi2={roi2}，"
                f"左目约 {offset_ratio*100:.0f}% 为黑边（已 rectify_crop 裁切）"
            )

    def _apply_rectify_crop(
        self, left: np.ndarray, right: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        if not self._rectify_crop or not self._common_roi:
            return left, right
        x, y, w, h = self._common_roi
        if w <= 8 or h <= 8:
            return left, right
        return left[y:y + h, x:x + w], right[y:y + h, x:x + w]

    def _build_rectify_maps(
        self, mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, img_size
    ):
        """预计算立体校正 remap 表"""
        self._map_left_x, self._map_left_y = cv2.initUndistortRectifyMap(
            mtx_l, dist_l, R1, P1, img_size, cv2.CV_32FC1
        )
        self._map_right_x, self._map_right_y = cv2.initUndistortRectifyMap(
            mtx_r, dist_r, R2, P2, img_size, cv2.CV_32FC1
        )

    def _rectify(self, frame: np.ndarray, side: str) -> np.ndarray:
        """对单张图像做畸变矫正"""
        if not HAS_CV2:
            return frame

        if side == 'left' and self._map_left_x is not None:
            return cv2.remap(
                frame, self._map_left_x, self._map_left_y,
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
        elif side == 'right' and self._map_right_x is not None:
            return cv2.remap(
                frame, self._map_right_x, self._map_right_y,
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )

        return frame

    def map_keypoints_to_rectified(
        self, kpts: Dict[str, Dict], side: str
    ) -> Dict[str, Dict]:
        """
        将原图上的 2D 关键点映射到立体校正坐标系（供 3D 三角测量）。
        预览用原图时仍需对点做校正，P 矩阵才匹配。
        """
        if not self.rectify_enabled or not HAS_CV2 or not kpts:
            return kpts
        if side == 'left':
            mtx, dist, Rr, P = (
                self._mtx_l, self._dist_l, self._R1, self._P1
            )
        else:
            mtx, dist, Rr, P = (
                self._mtx_r, self._dist_r, self._R2, self._P2
            )
        if mtx is None or Rr is None or P is None:
            return kpts

        mapped = {}
        for name, pt in kpts.items():
            src = np.array(
                [[[float(pt['x']), float(pt['y'])]]], dtype=np.float64
            )
            dst = cv2.undistortPoints(src, mtx, dist, R=Rr, P=P)
            mapped[name] = {
                **pt,
                'x': float(dst[0, 0, 0]),
                'y': float(dst[0, 0, 1]),
            }
        return mapped

    # ==================== 标定 ====================

    def calibrate_stereo(
        self,
        chess_size: Tuple[int, int] = (9, 6),
        square_size: float = 25.0,
        num_frames: int = 20,
        save: bool = True,
        baseline_mm: float = None,
        camera_model: str = None,
        interface: str = None,
    ) -> bool:
        """
        双目标定（棋盘格法）

        使用方法：
        1. 打印一张棋盘格图案
        2. 在摄像头前各角度展示
        3. 自动采集足够帧数后完成标定

        Args:
            chess_size: 棋盘格内角点数量 (列, 行)
            square_size: 棋盘格每格的实际尺寸（mm）
            num_frames: 需要采集的有效帧数
            save: 是否保存标定结果

        Returns:
            是否标定成功
        """
        if not HAS_CV2:
            print("[Camera] OpenCV未安装，无法标定")
            return False

        if not self._opened:
            print("[Camera] 请先打开摄像头")
            return False

        print(f"[Camera] 开始双目标定")
        print(f"  棋盘格: {chess_size[0]}x{chess_size[1]}, "
              f"格子大小: {square_size}mm")
        print(f"  请在摄像头前展示棋盘格...")

        # 3D世界坐标
        objp = np.zeros((chess_size[0] * chess_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[
            0:chess_size[0], 0:chess_size[1]
        ].T.reshape(-1, 2) * square_size

        obj_points = []
        img_points_left = []
        img_points_right = []

        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30, 0.001
        )

        collected = 0

        while collected < num_frames:
            ret, left, right = self.read()
            if not ret:
                continue

            gray_l = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)

            found_l, corners_l = cv2.findChessboardCorners(
                gray_l, chess_size, None
            )
            found_r, corners_r = cv2.findChessboardCorners(
                gray_r, chess_size, None
            )

            if found_l and found_r:
                corners_l = cv2.cornerSubPix(
                    gray_l, corners_l, (11, 11), (-1, -1), criteria
                )
                corners_r = cv2.cornerSubPix(
                    gray_r, corners_r, (11, 11), (-1, -1), criteria
                )

                obj_points.append(objp)
                img_points_left.append(corners_l)
                img_points_right.append(corners_r)

                collected += 1
                print(f"  采集 {collected}/{num_frames}")

                # 显示检测结果
                vis_l = left.copy()
                vis_r = right.copy()
                cv2.drawChessboardCorners(vis_l, chess_size, corners_l, True)
                cv2.drawChessboardCorners(vis_r, chess_size, corners_r, True)

                combined = np.hstack([vis_l, vis_r])
                cv2.imshow('Stereo Calibration', combined)

                # 采集间隔
                cv2.waitKey(500)
            else:
                # 显示原画面
                combined = np.hstack([left, right])
                cv2.imshow('Stereo Calibration', combined)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[Camera] 标定被用户取消")
                cv2.destroyAllWindows()
                return False

        cv2.destroyAllWindows()

        # 单目标定
        print("[Camera] 计算标定参数...")
        img_size = (self.single_width, self.single_height)

        ret_l, mtx_l, dist_l, _, _ = cv2.calibrateCamera(
            obj_points, img_points_left, img_size, None, None
        )
        ret_r, mtx_r, dist_r, _, _ = cv2.calibrateCamera(
            obj_points, img_points_right, img_size, None, None
        )

        # 双目标定
        flags = (
            cv2.CALIB_FIX_INTRINSIC
        )
        ret, mtx_l, dist_l, mtx_r, dist_r, R, T, E, F = \
            cv2.stereoCalibrate(
                obj_points, img_points_left, img_points_right,
                mtx_l, dist_l, mtx_r, dist_r,
                img_size, criteria=criteria, flags=flags
            )

        print(f"[Camera] 双目标定完成，重投影误差: {ret:.4f}")

        # 立体校正（alpha=1 减少黑边；0 裁剪狠易一侧全黑）
        R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
            mtx_l, dist_l, mtx_r, dist_r,
            img_size, R, T,
            alpha=self.rectify_alpha,
        )
        if self.rectify_enabled:
            self._build_rectify_maps(
                mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, img_size
            )
            self._validate_rectify_maps(img_size)
            self._mtx_l, self._dist_l = mtx_l, dist_l
            self._mtx_r, self._dist_r = mtx_r, dist_r
            self._R1, self._R2, self._P1, self._P2 = R1, R2, P1, P2
        self._update_rectify_roi(roi1, roi2, img_size)

        measured_baseline = float(np.linalg.norm(T))
        if baseline_mm is None:
            baseline_mm = measured_baseline

        # 存储标定参数
        self.calib_params = {
            'camera_matrix_left': mtx_l.tolist(),
            'camera_matrix_right': mtx_r.tolist(),
            'dist_coeffs_left': dist_l.tolist(),
            'dist_coeffs_right': dist_r.tolist(),
            'R': R.tolist(),
            'T': T.tolist(),
            'R1': R1.tolist(),
            'R2': R2.tolist(),
            'P1': P1.tolist(),
            'P2': P2.tolist(),
            'Q': Q.tolist(),
            'image_size': list(img_size),
            'reprojection_error': float(ret),
            'rectify_alpha': self.rectify_alpha,
            'roi1': list(roi1),
            'roi2': list(roi2),
            'baseline_mm': float(baseline_mm),
            'measured_baseline_mm': measured_baseline,
            'pattern_size': list(chess_size),
            'square_size_mm': float(square_size),
        }
        if camera_model:
            self.calib_params['camera_model'] = str(camera_model)
        if interface:
            self.calib_params['interface'] = str(interface)

        self.calibrated = True
        if ret > 1.5:
            print(
                f"[Camera] 警告: 重投影误差 {ret:.2f} 偏大，"
                "画面可能异常，建议重新标定"
            )

        if save:
            self._save_calibration()

        return True

    def _save_calibration(self):
        """保存标定参数到文件"""
        os.makedirs(os.path.dirname(self.calibration_file), exist_ok=True)

        with open(self.calibration_file, 'w') as f:
            json.dump(self.calib_params, f, indent=2)

        print(f"[Camera] 标定参数已保存: {self.calibration_file}")

    def _load_calibration(self):
        """加载已有的标定参数"""
        if not os.path.exists(self.calibration_file):
            print(
                f"[Camera] 未找到标定文件: {self.calibration_file}，"
                "3D 将使用近似三角测量；可用 calibrate_stereo() 生成"
            )
            return

        try:
            with open(self.calibration_file, 'r') as f:
                self.calib_params = json.load(f)

            if not HAS_CV2:
                return

            img_size = tuple(self.calib_params['image_size'])

            mtx_l = np.array(self.calib_params['camera_matrix_left'])
            dist_l = np.array(self.calib_params['dist_coeffs_left'])
            mtx_r = np.array(self.calib_params['camera_matrix_right'])
            dist_r = np.array(self.calib_params['dist_coeffs_right'])
            R = np.array(self.calib_params['R'])
            T = np.array(self.calib_params['T'])

            alpha = self.rectify_alpha
            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                mtx_l, dist_l, mtx_r, dist_r,
                img_size, R, T, alpha=alpha,
            )
            self.calib_params['R1'] = R1.tolist()
            self.calib_params['R2'] = R2.tolist()
            self.calib_params['P1'] = P1.tolist()
            self.calib_params['P2'] = P2.tolist()
            self.calib_params['Q'] = Q.tolist()
            self.calib_params['rectify_alpha'] = alpha
            self.calib_params['roi1'] = list(roi1)
            self.calib_params['roi2'] = list(roi2)

            if self.rectify_enabled:
                self._build_rectify_maps(
                    mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, img_size
                )
                self._validate_rectify_maps(img_size)
                self._mtx_l, self._dist_l = mtx_l, dist_l
                self._mtx_r, self._dist_r = mtx_r, dist_r
                self._R1, self._R2, self._P1, self._P2 = R1, R2, P1, P2
            self._update_rectify_roi(roi1, roi2, img_size)

            self.calibrated = True
            err = self.calib_params.get('reprojection_error', 0)
            rectify_note = (
                f"rectify=on, alpha={alpha}"
                if self.rectify_enabled else "rectify=off"
            )
            if self.rectify_enabled and not self.rectify_preview:
                rectify_note += ", 预览=原图"
            print(
                f"[Camera] 已加载标定参数: {self.calibration_file} "
                f"({rectify_note}, reproj={err:.2f})"
            )
            if self.rectify_enabled and err > 1.5:
                print(
                    "[Camera] 重投影误差偏大，若四周拉伸/黑边可设 "
                    "calibration.rectify: false 或重新标定"
                )

        except Exception as e:
            print(f"[Camera] 加载标定参数失败: {e}")

    # ==================== 诊断 ====================

    def get_diagnostics(self) -> dict:
        """获取摄像头诊断信息"""
        return {
            'opened': self._opened,
            'mode': self.mode,
            'resolution': f"{self.width}x{self.height}",
            'single_resolution': f"{self.single_width}x{self.single_height}",
            'fps': self.fps,
            'frame_count': self.frame_count,
            'calibrated': self.calibrated,
            'simulate': self.simulate,
            'reprojection_error': self.calib_params.get(
                'reprojection_error', None
            ),
        }
