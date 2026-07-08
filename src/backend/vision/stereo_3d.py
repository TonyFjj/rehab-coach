"""
双目三角测量
将左右摄像头检测到的2D关键点，通过三角测量恢复3D坐标
"""

import numpy as np
from typing import Dict, Optional, Tuple

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class StereoTriangulator:
    """
    双目三角测量器

    原理：
    同一个3D点在左右摄像头中各有一个2D投影
    通过两个投影 + 摄像头的投影矩阵，反求3D坐标

    前提：摄像头已完成双目标定（CameraManager.calibrate_stereo）
    """

    def __init__(
        self,
        calib_params: dict = None,
        baseline_mm: float = 60.0,
        simulate: bool = False
    ):
        """
        Args:
            calib_params: 双目标定参数（来自CameraManager）
            baseline_mm: 基线距离（两摄像头间距，mm），模拟模式用
            simulate: 模拟模式
        """
        self.simulate = simulate
        self.baseline_mm = baseline_mm
        self._fallback_warned = False

        # 投影矩阵
        self.P1 = None  # 左摄像头投影矩阵 3x4
        self.P2 = None  # 右摄像头投影矩阵 3x4
        self.Q = None   # 视差-深度映射矩阵 4x4

        if calib_params:
            self.load_calibration(calib_params)

    def load_calibration(self, calib_params: dict):
        """加载标定参数"""
        try:
            self.P1 = np.array(calib_params['P1'])
            self.P2 = np.array(calib_params['P2'])
            self.Q = np.array(calib_params['Q'])
            if 'baseline_mm' in calib_params:
                self.baseline_mm = float(calib_params['baseline_mm'])
            print("[Stereo] 标定参数加载成功")
        except KeyError as e:
            print(f"[Stereo] 标定参数缺失: {e}")

    def triangulate(
        self,
        kpts_left: Dict[str, Dict],
        kpts_right: Dict[str, Dict],
        min_conf: float = 0.25
    ) -> Dict[str, Dict]:
        """
        双目三角测量：2D关键点对 → 3D坐标

        Args:
            kpts_left: 左图关键点
                {"left_shoulder": {"x": 320, "y": 180, "conf": 0.92}, ...}
            kpts_right: 右图关键点（同格式）
            min_conf: 最低置信度阈值

        Returns:
            3D关键点:
            {
                "left_shoulder": {
                    "position": np.array([x, y, z]),  # mm
                    "confidence": 0.89,
                },
                ...
            }
        """
        if self.simulate:
            return self._triangulate_simulate(kpts_left, kpts_right)

        if self.P1 is None or self.P2 is None:
            if not self._fallback_warned:
                print(
                    "[Stereo] 未加载标定参数，使用模拟三角测量"
                    "（请生成 config/stereo_calib.json，见 camera_config.yaml）"
                )
                self._fallback_warned = True
            return self._triangulate_simulate(kpts_left, kpts_right)

        results = {}

        for name in kpts_left:
            if name not in kpts_right:
                continue

            left_pt = kpts_left[name]
            right_pt = kpts_right[name]

            # 置信度过滤
            conf = min(left_pt['conf'], right_pt['conf'])
            if conf < min_conf:
                continue

            # 2D点
            pt_l = np.array([left_pt['x'], left_pt['y']])
            pt_r = np.array([right_pt['x'], right_pt['y']])

            # 三角测量
            point_3d = self._do_triangulate(pt_l, pt_r)

            if point_3d is not None:
                results[name] = {
                    'position': point_3d,
                    'confidence': conf,
                }

        return results

    def _do_triangulate(
        self,
        pt_left: np.ndarray,
        pt_right: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        对单个点进行三角测量

        Args:
            pt_left: 左图2D坐标 [x, y]
            pt_right: 右图2D坐标 [x, y]

        Returns:
            3D坐标 [X, Y, Z]（mm），失败返回None
        """
        if not HAS_CV2:
            return None

        try:
            pts_l = pt_left.reshape(1, 1, 2).astype(np.float64)
            pts_r = pt_right.reshape(1, 1, 2).astype(np.float64)

            # OpenCV三角测量
            points_4d = cv2.triangulatePoints(
                self.P1, self.P2, pts_l, pts_r
            )

            # 齐次坐标 → 3D坐标
            points_3d = points_4d[:3] / points_4d[3]
            point = points_3d.flatten()

            # 合理性检查：深度应为正，且不应太远
            if point[2] <= 0 or point[2] > 10000:
                return None

            return point

        except Exception as e:
            return None

    def _triangulate_simulate(
        self,
        kpts_left: Dict,
        kpts_right: Dict
    ) -> Dict[str, Dict]:
        """
        模拟三角测量：根据视差估算深度

        简化模型：
        depth ≈ focal_length × baseline / disparity
        """
        results = {}

        # 假设焦距（像素）
        focal_px = 500.0

        for name in kpts_left:
            if name not in kpts_right:
                continue

            left_pt = kpts_left[name]
            right_pt = kpts_right[name]

            conf = min(left_pt['conf'], right_pt['conf'])

            # 视差 = 左x - 右x
            disparity = left_pt['x'] - right_pt['x']
            if disparity <= 0.5:
                disparity = 0.5  # 避免除以零

            # 深度估算
            z = focal_px * self.baseline_mm / disparity

            # X, Y从左图像素坐标 + 深度反推
            cx, cy = 320.0, 240.0  # 假设图像中心
            x = (left_pt['x'] - cx) * z / focal_px
            y = (left_pt['y'] - cy) * z / focal_px

            # 添加少量噪声模拟真实误差
            noise = np.random.normal(0, 2, 3)

            results[name] = {
                'position': np.array([x + noise[0],
                                      y + noise[1],
                                      z + noise[2]]),
                'confidence': conf,
            }

        return results

    def get_diagnostics(self) -> dict:
        """获取诊断信息"""
        return {
            'has_calibration': self.P1 is not None,
            'baseline_mm': self.baseline_mm,
            'simulate': self.simulate,
        }

