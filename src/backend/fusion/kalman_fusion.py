"""
多传感器卡尔曼滤波融合引擎
将双目视觉3D骨骼坐标与双手IMU数据融合，输出高精度骨骼状态
"""

import time
import numpy as np
from typing import Dict, Tuple, Optional, Set
from filterpy.kalman import KalmanFilter


class SensorFusionEngine:
    """
    视觉 + IMU 多传感器融合引擎

    融合策略：
    - 视觉（双目3D骨骼）：低频(30fps)、高空间精度、有遮挡风险
    - IMU（MPU6050×2）：高频(100Hz)、角度/角速度准、有零漂
    - 融合后：取两者之长，输出稳定、高精度的3D骨骼状态

    每个需要融合的关节点使用一个独立的卡尔曼滤波器
    状态向量：[x, y, z, vx, vy, vz]（位置+速度）
    """

    # 需要融合的关键关节点（与YOLOv8-Pose的17个关键点对应）
    JOINT_NAMES = [
        'left_shoulder', 'right_shoulder',
        'left_elbow', 'right_elbow',
        'left_wrist', 'right_wrist',
        'left_hip', 'right_hip',
        'left_knee', 'right_knee',
        'left_ankle', 'right_ankle',
    ]

    # IMU绑定位置映射：哪些关节可以用IMU数据增强
    IMU_JOINT_MAP = {
        'left_wrist': 'imu_left',
        'right_wrist': 'imu_right',
    }

    # 关节角：2D 更稳（正对镜头）；空间量：3D 更准
    _JOINT_ANGLE_KEYS: Set[str] = {
        'shoulder_flexion', 'shoulder_abduction', 'knee_flexion', 'knee_extension',
        'push_shoulder_flexion', 'pull_shoulder_abduction',
        'shoulder_flexion_left', 'shoulder_flexion_right',
        'shoulder_abduction_left', 'shoulder_abduction_right',
        'knee_flexion_left', 'knee_flexion_right',
        'knee_extension_left', 'knee_extension_right',
        'elbow_flexion_left', 'elbow_flexion_right',
    }

    _SPATIAL_KEYS: Set[str] = {
        'foot_height', 'step_distance', 'trunk_rotation', 'body_sway',
        'shoulder_combined', 'shoulder_flexion_rotation',
        'head_level', 'shoulder_stability', 'trunk_sway',
        'step_dx_left', 'step_dx_right', 'step_dy_left', 'step_dy_right',
        'leg_raise_angle', 'leg_raise_left', 'leg_raise_right',
        'leg_raise_active',
    }

    _RAW_3D_STALE_SEC = 0.35
    _MIN_3D_JOINTS = 6

    def __init__(
        self,
        dt_vision: float = 1.0 / 30.0,
        dt_imu: float = 1.0 / 100.0,
        process_noise: float = 0.1,
        vision_noise: float = 5.0,
        imu_noise: float = 2.0
    ):
        """
        Args:
            dt_vision: 视觉帧间隔（秒）
            dt_imu: IMU采样间隔（秒）
            process_noise: 过程噪声（运动模型不确定性）
            vision_noise: 视觉测量噪声（mm）
            imu_noise: IMU测量噪声
        """
        self.dt_vision = dt_vision
        self.dt_imu = dt_imu
        self.process_noise = process_noise
        self.vision_noise = vision_noise
        self.imu_noise = imu_noise

        # 为每个关节创建卡尔曼滤波器
        self.filters: Dict[str, KalmanFilter] = {}
        for joint in self.JOINT_NAMES:
            self.filters[joint] = self._create_filter()

        # 上一帧的融合结果
        self.last_fused_state: Dict[str, np.ndarray] = {}

        # IMU零漂补偿值
        self.imu_bias = {
            'imu_left': np.zeros(3),
            'imu_right': np.zeros(3),
        }

        # 融合帧计数
        self.frame_count = 0

        # 左目 2D 关键点（3D 缺髋/三角失败时用 2D 算角度）
        self._last_kpts_2d_left: Dict[str, Dict] = {}

        # 原始三角测量 3D（每帧刷新，训练计次优先用它而非 Kalman 预测）
        self._last_raw_3d: Dict[str, np.ndarray] = {}
        self._last_raw_3d_conf: Dict[str, float] = {}
        self._last_raw_3d_time: float = 0.0
        self._last_blend_stats: Dict[str, int] = {}
        self._joint_last_obs_time: Dict[str, float] = {}
        self._ankle_baseline_y: Dict[str, float] = {}
        self._gait_baseline_2d: Dict[str, np.ndarray] = {}
        self._gait_baseline_3d: Dict[str, np.ndarray] = {}

    def reset_supine_leg_baselines(self):
        """新动作开始时重置抬腿基线。"""
        self._ankle_baseline_y.clear()

    def reset_gait_baselines(self):
        """步态训练开始时重置双足中立站姿基线。"""
        self._gait_baseline_2d.clear()
        self._gait_baseline_3d.clear()

    @staticmethod
    def _pixel_scale_to_cm_2d(
        left_hip: Optional[np.ndarray],
        left_ankle: Optional[np.ndarray],
        right_hip: Optional[np.ndarray],
        right_ankle: Optional[np.ndarray],
    ) -> float:
        """用髋宽（约 30cm）估算 px→cm，比单用腿长更适合步态横向位移。"""
        if left_hip is not None and right_hip is not None:
            hip_width_px = float(np.linalg.norm(right_hip - left_hip))
            if hip_width_px > 1e-3:
                return 30.0 / hip_width_px
        leg_ref = 0.0
        if left_hip is not None and left_ankle is not None:
            leg_ref = float(np.linalg.norm(left_ankle - left_hip))
        if leg_ref < 1e-3 and right_hip is not None and right_ankle is not None:
            leg_ref = float(np.linalg.norm(right_ankle - right_hip))
        return 80.0 / leg_ref if leg_ref > 1e-3 else 0.15

    def _compute_gait_step_metrics_2d(
        self,
        left_hip: Optional[np.ndarray],
        right_hip: Optional[np.ndarray],
        left_ankle: Optional[np.ndarray],
        right_ankle: Optional[np.ndarray],
    ) -> Dict[str, float]:
        """
        步态步距：相对中立站姿的踝部位移（cm），并减去髋部整体平移。
        比「踝-髋中心距离」更能反映前后/左右迈步幅度。
        """
        metrics: Dict[str, float] = {}
        if left_hip is None or right_hip is None:
            return metrics

        hip_mid = (left_hip + right_hip) / 2.0
        scale = self._pixel_scale_to_cm_2d(
            left_hip, left_ankle, right_hip, right_ankle,
        )

        if not self._gait_baseline_2d:
            if left_ankle is not None:
                self._gait_baseline_2d['left_ankle'] = left_ankle.copy()
                self._gait_baseline_2d['left_leg_len'] = float(
                    np.linalg.norm(left_ankle - left_hip),
                )
            if right_ankle is not None:
                self._gait_baseline_2d['right_ankle'] = right_ankle.copy()
                self._gait_baseline_2d['right_leg_len'] = float(
                    np.linalg.norm(right_ankle - right_hip),
                )
            self._gait_baseline_2d['hip_mid'] = hip_mid.copy()
            if left_ankle is not None and right_ankle is not None:
                self._gait_baseline_2d['ankle_spread_cm'] = float(
                    np.linalg.norm(right_ankle - left_ankle) * scale,
                )
            metrics['step_distance'] = 0.0
            return metrics

        base_hip = self._gait_baseline_2d.get('hip_mid')
        hip_shift = hip_mid - base_hip if base_hip is not None else np.zeros(2)

        step_dists = []
        if left_ankle is not None and right_ankle is not None:
            spread_cm = float(np.linalg.norm(right_ankle - left_ankle) * scale)
            base_spread = float(
                self._gait_baseline_2d.get('ankle_spread_cm', spread_cm),
            )
            step_dists.append(abs(spread_cm - base_spread))

        for side, ankle, hip in (
            ('left', left_ankle, left_hip),
            ('right', right_ankle, right_hip),
        ):
            base = self._gait_baseline_2d.get(f'{side}_ankle')
            if ankle is None or base is None or hip is None:
                continue

            disp_px = (ankle - base) - hip_shift
            dx_cm = float(disp_px[0]) * scale
            dy_cm = float(disp_px[1]) * scale

            leg_now = float(np.linalg.norm(ankle - hip))
            base_leg = float(self._gait_baseline_2d.get(f'{side}_leg_len', leg_now))
            ext_cm = abs(leg_now - base_leg) * scale

            disp_cm = max(
                float(np.hypot(dx_cm, dy_cm)),
                abs(dx_cm),
                abs(dy_cm) * 0.85,
                ext_cm * 0.9,
            )
            metrics[f'step_dx_{side}'] = round(dx_cm, 1)
            metrics[f'step_dy_{side}'] = round(dy_cm, 1)
            step_dists.append(disp_cm)

        peak = max(step_dists) if step_dists else 0.0
        metrics['step_distance'] = round(peak, 1) if step_dists else 0.0

        if peak < 3.0:
            blend = 0.04
            if left_ankle is not None and 'left_ankle' in self._gait_baseline_2d:
                b = self._gait_baseline_2d['left_ankle']
                self._gait_baseline_2d['left_ankle'] = (
                    (1.0 - blend) * b + blend * left_ankle
                )
            if right_ankle is not None and 'right_ankle' in self._gait_baseline_2d:
                b = self._gait_baseline_2d['right_ankle']
                self._gait_baseline_2d['right_ankle'] = (
                    (1.0 - blend) * b + blend * right_ankle
                )
            if base_hip is not None:
                self._gait_baseline_2d['hip_mid'] = (
                    (1.0 - blend) * base_hip + blend * hip_mid
                )
            if left_ankle is not None and right_ankle is not None:
                spread_cm = float(np.linalg.norm(right_ankle - left_ankle) * scale)
                old = float(self._gait_baseline_2d.get('ankle_spread_cm', spread_cm))
                self._gait_baseline_2d['ankle_spread_cm'] = (
                    (1.0 - blend) * old + blend * spread_cm
                )
            for side, ankle, hip in (
                ('left', left_ankle, left_hip),
                ('right', right_ankle, right_hip),
            ):
                if ankle is None or hip is None:
                    continue
                key = f'{side}_leg_len'
                leg_now = float(np.linalg.norm(ankle - hip))
                old = float(self._gait_baseline_2d.get(key, leg_now))
                self._gait_baseline_2d[key] = (1.0 - blend) * old + blend * leg_now

        return metrics

    def _compute_gait_step_metrics_3d(
        self,
        left_hip: Optional[np.ndarray],
        right_hip: Optional[np.ndarray],
        left_ankle: Optional[np.ndarray],
        right_ankle: Optional[np.ndarray],
    ) -> Dict[str, float]:
        """3D 步距：水平面(X-Z)相对基线位移，单位 cm。"""
        metrics: Dict[str, float] = {}
        if left_hip is None or right_hip is None:
            return metrics

        hip_mid = (left_hip + right_hip) / 2.0

        if not self._gait_baseline_3d:
            if left_ankle is not None:
                self._gait_baseline_3d['left_ankle'] = left_ankle.copy()
            if right_ankle is not None:
                self._gait_baseline_3d['right_ankle'] = right_ankle.copy()
            self._gait_baseline_3d['hip_mid'] = hip_mid.copy()
            if left_ankle is not None and right_ankle is not None:
                spread_mm = float(np.linalg.norm(right_ankle - left_ankle))
                self._gait_baseline_3d['ankle_spread_cm'] = spread_mm / 10.0
            metrics['step_distance'] = 0.0
            return metrics

        base_hip = self._gait_baseline_3d.get('hip_mid')
        hip_shift = hip_mid - base_hip if base_hip is not None else np.zeros(3)

        step_dists = []
        if left_ankle is not None and right_ankle is not None:
            spread_cm = float(np.linalg.norm(right_ankle - left_ankle) / 10.0)
            base_spread = float(
                self._gait_baseline_3d.get('ankle_spread_cm', spread_cm),
            )
            step_dists.append(abs(spread_cm - base_spread))

        for side, ankle in (('left', left_ankle), ('right', right_ankle)):
            base = self._gait_baseline_3d.get(f'{side}_ankle')
            if ankle is None or base is None:
                continue

            disp_mm = (ankle - base) - hip_shift
            dx_cm = float(disp_mm[0]) / 10.0
            dz_cm = float(disp_mm[2]) / 10.0
            disp_cm = max(
                float(np.hypot(dx_cm, dz_cm)),
                abs(dx_cm),
                abs(dz_cm),
            )

            metrics[f'step_dx_{side}'] = round(dx_cm, 1)
            metrics[f'step_dy_{side}'] = round(dz_cm, 1)
            step_dists.append(disp_cm)

        peak = max(step_dists) if step_dists else 0.0
        metrics['step_distance'] = round(peak, 1) if step_dists else 0.0

        if peak < 3.0:
            blend = 0.04
            for side, ankle in (('left', left_ankle), ('right', right_ankle)):
                base = self._gait_baseline_3d.get(f'{side}_ankle')
                if ankle is not None and base is not None:
                    self._gait_baseline_3d[f'{side}_ankle'] = (
                        (1.0 - blend) * base + blend * ankle
                    )
            if base_hip is not None:
                self._gait_baseline_3d['hip_mid'] = (
                    (1.0 - blend) * base_hip + blend * hip_mid
                )
            if left_ankle is not None and right_ankle is not None:
                spread_cm = float(np.linalg.norm(right_ankle - left_ankle) / 10.0)
                old = float(self._gait_baseline_3d.get('ankle_spread_cm', spread_cm))
                self._gait_baseline_3d['ankle_spread_cm'] = (
                    (1.0 - blend) * old + blend * spread_cm
                )

        return metrics

    @staticmethod
    def _leg_raise_elevation_2d(
        hip: np.ndarray,
        knee: Optional[np.ndarray],
        ankle: Optional[np.ndarray],
    ) -> Optional[float]:
        """
        仰卧直腿抬高：大腿相对床面（画面水平）抬起的角度。
        比两踝 Y 差分更适应前后腿遮挡。
        """
        if hip is None:
            return None
        foot = ankle if ankle is not None else knee
        if foot is None:
            return None
        v = foot - hip
        length = float(np.linalg.norm(v))
        if length < 1e-3:
            return None
        down = np.array([0.0, 1.0], dtype=np.float64)
        cos_a = np.clip(float(np.dot(v / length, down)), -1.0, 1.0)
        # 相对床面（画面水平）的抬腿角：放平≈0°，竖起≈90°
        elev = 90.0 - float(np.degrees(np.arccos(cos_a)))
        return max(0.0, min(75.0, elev))

    def _baseline_leg_lift_deg(
        self,
        side: str,
        ankle_y: float,
        leg_len: float,
    ) -> float:
        """相对本侧「腿放平」基线的抬腿角度估计。"""
        if leg_len < 1e-3:
            return 0.0
        base = self._ankle_baseline_y.get(side)
        if base is None:
            self._ankle_baseline_y[side] = ankle_y
            return 0.0
        if ankle_y > base - 2.0:
            self._ankle_baseline_y[side] = max(base, ankle_y)
        lift_px = self._ankle_baseline_y[side] - ankle_y
        if lift_px <= 0:
            return 0.0
        return max(0.0, min(75.0, lift_px / leg_len * 65.0))

    def _compute_supine_leg_raise_metrics(
        self,
        kpts: Dict[str, Dict],
        min_conf: float = 0.22,
    ) -> Dict[str, float]:
        if not kpts:
            return {}

        def pt(name):
            k = kpts.get(name)
            if not k or k.get('conf', 0) < min_conf:
                return None
            return np.array([k['x'], k['y']], dtype=np.float64)

        out: Dict[str, float] = {}
        per_side = []
        for side in ('left', 'right'):
            hip = pt(f'{side}_hip')
            knee = pt(f'{side}_knee')
            ankle = pt(f'{side}_ankle')
            # 踝被遮挡时用膝部延长估计足端（直腿抬高时髋-膝-踝近似共线）
            foot = ankle
            if foot is None and hip is not None and knee is not None:
                thigh = knee - hip
                thigh_len = float(np.linalg.norm(thigh))
                if thigh_len > 1e-3:
                    foot = knee + thigh / thigh_len * (thigh_len * 0.85)
            elev = self._leg_raise_elevation_2d(hip, knee, foot)
            if elev is None:
                continue
            leg_len = 1.0
            if hip is not None and foot is not None:
                leg_len = max(leg_len, float(np.linalg.norm(foot - hip)))
            elif hip is not None and knee is not None:
                leg_len = max(leg_len, float(np.linalg.norm(knee - hip)) * 1.85)
            baseline = 0.0
            if ankle is not None:
                baseline = self._baseline_leg_lift_deg(
                    side, float(ankle[1]), leg_len,
                )
            elif knee is not None:
                baseline = self._baseline_leg_lift_deg(
                    f'{side}_knee', float(knee[1]), leg_len,
                )
            combined = max(elev, baseline)
            out[f'leg_raise_{side}'] = round(combined, 1)
            per_side.append(combined)

        if per_side:
            active = max(per_side)
            out['leg_raise_active'] = round(active, 1)
            out['leg_raise_angle'] = round(active, 1)
            # 兼容旧 foot_height 阈值（约 cm）→ 度数的 1/2 映射
            out['foot_height'] = round(active * 0.45, 1)
        return out

    def _create_filter(self) -> KalmanFilter:
        """
        创建单个关节点的卡尔曼滤波器

        状态向量 x = [px, py, pz, vx, vy, vz]  (6维)
        观测向量 z = [px, py, pz]                (3维)
        """
        kf = KalmanFilter(dim_x=6, dim_z=3)

        dt = self.dt_vision

        # 状态转移矩阵（匀速运动模型）
        kf.F = np.array([
            [1, 0, 0, dt, 0,  0],
            [0, 1, 0, 0,  dt, 0],
            [0, 0, 1, 0,  0,  dt],
            [0, 0, 0, 1,  0,  0],
            [0, 0, 0, 0,  1,  0],
            [0, 0, 0, 0,  0,  1],
        ])

        # 观测矩阵（只观测位置）
        kf.H = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
        ])

        # 过程噪声
        q = self.process_noise
        kf.Q = np.eye(6) * q
        kf.Q[3:, 3:] *= 2  # 速度的过程噪声更大

        # 测量噪声（初始为视觉噪声）
        kf.R = np.eye(3) * (self.vision_noise ** 2)

        # 初始协方差
        kf.P = np.eye(6) * 100

        return kf

    def update_vision(
        self,
        keypoints_3d: Dict[str, np.ndarray],
        confidences: Dict[str, float] = None
    ):
        """
        视觉数据更新（双目3D骨骼关键点到达时调用）

        Args:
            keypoints_3d: 各关节的3D坐标
                例: {"left_wrist": np.array([100, 200, 500]), ...}
                坐标单位: mm
            confidences: 各关节的检测置信度 (0-1)
                例: {"left_wrist": 0.85, ...}
        """
        if confidences is None:
            confidences = {k: 0.8 for k in keypoints_3d}

        for joint_name, position in keypoints_3d.items():
            if joint_name not in self.filters:
                continue

            kf = self.filters[joint_name]
            conf = confidences.get(joint_name, 0.5)

            # 根据置信度动态调整测量噪声
            # 置信度低 → 噪声大 → 更相信预测
            # 置信度高 → 噪声小 → 更相信观测
            adjusted_noise = self.vision_noise / max(conf, 0.1)
            kf.R = np.eye(3) * (adjusted_noise ** 2)

            # 预测 + 更新
            kf.predict()
            kf.update(position.reshape(3, 1))

            kf.predict()
            kf.update(position.reshape(3, 1))
            self._joint_last_obs_time[joint_name] = time.time()

        self.frame_count += 1

    def set_raw_skeleton_3d(self, skeleton_3d: Dict[str, dict]):
        """
        缓存本帧原始三角测量 3D（不经过 Kalman 预测）。
        训练混合策略优先使用此数据计算 3D 角度/步距/脚高。
        """
        if not skeleton_3d:
            return

        now = time.time()
        self._last_raw_3d_time = now
        self._last_raw_3d = {}
        self._last_raw_3d_conf = {}

        for name, data in skeleton_3d.items():
            if isinstance(data, dict):
                pos = data.get('position')
                conf = float(data.get('confidence', 0.5))
            else:
                pos = data
                conf = 0.8
            if pos is None:
                continue
            p = np.asarray(pos, dtype=np.float64).reshape(-1)[:3]
            if np.linalg.norm(p) <= 1e-3:
                continue
            self._last_raw_3d[name] = p
            self._last_raw_3d_conf[name] = conf

    def set_vision_2d_left(self, keypoints_2d: Dict[str, Dict]):
        """缓存左目 2D 姿态，供 compute_joint_angles 在 3D 不足时回退。"""
        if keypoints_2d:
            self._last_kpts_2d_left = keypoints_2d

    def update_imu(
        self,
        imu_id: str,
        accel: np.ndarray,
        gyro: np.ndarray,
        dt: float = None
    ):
        """
        IMU数据更新（每个IMU采样到达时调用，频率高于视觉）

        Args:
            imu_id: IMU标识符 ('imu_left' 或 'imu_right')
            accel: 加速度 [ax, ay, az] (m/s²)
            gyro: 角速度 [gx, gy, gz] (°/s)
            dt: 采样间隔（秒），默认使用初始化时设置的值
        """
        if dt is None:
            dt = self.dt_imu

        # 零漂补偿
        accel_compensated = accel - self.imu_bias.get(imu_id, np.zeros(3))

        # 找到对应的关节
        joint_name = None
        for joint, imu in self.IMU_JOINT_MAP.items():
            if imu == imu_id:
                joint_name = joint
                break

        if joint_name is None or joint_name not in self.filters:
            return

        kf = self.filters[joint_name]

        # IMU提供的是加速度，可以用来修正速度估计
        # 将加速度积分到状态中（作为控制输入）

        # 控制输入矩阵 B
        B = np.zeros((6, 3))
        B[3, 0] = dt      # ax → vx
        B[4, 1] = dt      # ay → vy
        B[5, 2] = dt      # az → vz
        B[0, 0] = 0.5 * dt * dt  # ax → px
        B[1, 1] = 0.5 * dt * dt
        B[2, 2] = 0.5 * dt * dt

        # 更新状态转移矩阵的dt
        kf.F[0, 3] = dt
        kf.F[1, 4] = dt
        kf.F[2, 5] = dt

        # 使用加速度作为控制输入进行预测
        u = accel_compensated.reshape(3, 1)
        kf.predict(u=u, B=B)

    def get_fused_state(self) -> Dict[str, dict]:
        """
        获取当前融合后的骨骼状态

        Returns:
            各关节的融合结果:
            {
                "left_wrist": {
                    "position": np.array([x, y, z]),   # mm
                    "velocity": np.array([vx, vy, vz]), # mm/s
                    "confidence": 0.92,
                },
                ...
            }
        """
        result = {}

        for joint_name, kf in self.filters.items():
            state = kf.x.flatten()
            covariance = kf.P

            position = state[:3]
            velocity = state[3:]

            trace = np.trace(covariance[:3, :3])
            confidence = 1.0 / (1.0 + trace / 1000.0)

            last_obs = self._joint_last_obs_time.get(joint_name, 0.0)
            stale = (time.time() - last_obs) > self._RAW_3D_STALE_SEC * 2

            result[joint_name] = {
                'position': position.copy(),
                'velocity': velocity.copy(),
                'confidence': float(np.clip(confidence, 0, 1)),
                'stale': stale,
            }

        self.last_fused_state = result
        return result

    def compute_joint_angles(
        self, fused_state: Dict[str, dict] = None
    ) -> Dict[str, float]:
        """
        混合 2D/3D 关节指标：
        - 肩/膝等关节角：2D 为主，3D 新鲜时加权融合
        - 步距/脚高/躯干旋转等：3D 为主，2D 回退
        """
        angles_3d = self._compute_angles_from_3d(self._last_raw_3d)
        angles_2d = self._compute_angles_from_2d(self._last_kpts_2d_left)
        merged = self._merge_hybrid_angles(angles_3d, angles_2d)
        return merged

    def _raw_3d_is_fresh(self) -> bool:
        if not self._last_raw_3d:
            return False
        if time.time() - self._last_raw_3d_time > self._RAW_3D_STALE_SEC:
            return False
        return len(self._last_raw_3d) >= self._MIN_3D_JOINTS

    @staticmethod
    def _calc_angle_3pts(p1, p2, p3) -> float:
        v1 = p1 - p2
        v2 = p3 - p2
        cos_angle = np.dot(v1, v2) / (
            np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8
        )
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_angle)))

    def _get_raw_pos(self, name: str) -> Optional[np.ndarray]:
        p = self._last_raw_3d.get(name)
        if p is None:
            return None
        if np.linalg.norm(p) <= 1e-3:
            return None
        return p

    def _compute_angles_from_3d(
        self, raw_3d: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """由原始三角测量 3D 计算角度与空间指标（mm 坐标系）。"""
        if not raw_3d:
            return {}

        angles: Dict[str, float] = {}

        for side in ('left', 'right'):
            shoulder = self._get_raw_pos(f'{side}_shoulder')
            elbow = self._get_raw_pos(f'{side}_elbow')
            hip = self._get_raw_pos(f'{side}_hip')
            knee = self._get_raw_pos(f'{side}_knee')
            ankle = self._get_raw_pos(f'{side}_ankle')
            other_sh = self._get_raw_pos(
                f'{"right" if side == "left" else "left"}_shoulder'
            )

            if shoulder is not None and elbow is not None and hip is not None:
                a = self._calc_angle_3pts(hip, shoulder, elbow)
                angles[f'shoulder_flexion_{side}'] = a
                angles['shoulder_flexion'] = a

            if shoulder is not None and elbow is not None and other_sh is not None:
                a = self._calc_angle_3pts(other_sh, shoulder, elbow)
                angles[f'shoulder_abduction_{side}'] = a
                angles['shoulder_abduction'] = a

            if shoulder is not None and elbow is not None and knee is not None:
                wrist = self._get_raw_pos(f'{side}_wrist')
                if wrist is not None:
                    a = self._calc_angle_3pts(shoulder, elbow, wrist)
                    angles[f'elbow_flexion_{side}'] = a

            if hip is not None and knee is not None and ankle is not None:
                a = self._calc_angle_3pts(hip, knee, ankle)
                angles[f'knee_flexion_{side}'] = a

        knee_vals = [
            angles[k] for k in ('knee_flexion_left', 'knee_flexion_right')
            if k in angles
        ]
        if knee_vals:
            angles['knee_flexion_active'] = max(knee_vals)
            angles['knee_flexion'] = angles['knee_flexion_active']

        if 'knee_flexion' in angles:
            angles['knee_extension'] = max(0.0, 180.0 - angles['knee_flexion'])
        if 'shoulder_flexion' in angles:
            angles['push_shoulder_flexion'] = angles['shoulder_flexion']
        if 'shoulder_abduction' in angles:
            angles['pull_shoulder_abduction'] = angles['shoulder_abduction']

        spatial = self._compute_spatial_metrics_3d()
        angles.update(spatial)
        if 'shoulder_flexion' in angles or 'shoulder_abduction' in angles:
            angles['shoulder_combined'] = max(
                angles.get('shoulder_flexion', 0.0),
                angles.get('shoulder_abduction', 0.0),
            )
        return angles

    def _compute_spatial_metrics_3d(self) -> Dict[str, float]:
        """
        3D 空间指标（相机坐标：X 右、Y 下、Z 前，单位 mm）。
        竖直方向用 -Y；水平位移用 X-Z 平面。
        """
        metrics: Dict[str, float] = {}

        left_sh = self._get_raw_pos('left_shoulder')
        right_sh = self._get_raw_pos('right_shoulder')
        left_hip = self._get_raw_pos('left_hip')
        right_hip = self._get_raw_pos('right_hip')
        left_ankle = self._get_raw_pos('left_ankle')
        right_ankle = self._get_raw_pos('right_ankle')
        nose = self._get_raw_pos('nose')

        # 脚离地高度（cm）：较高脚 -Y 更大（Y 向下）
        foot_heights = []
        for ankle, other in ((left_ankle, right_ankle), (right_ankle, left_ankle)):
            if ankle is None or other is None:
                continue
            lift_mm = float(-ankle[1] - (-other[1]))
            if lift_mm > 0:
                foot_heights.append(lift_mm / 10.0)
        if foot_heights:
            metrics['foot_height'] = max(foot_heights)

        if left_sh is not None and right_sh is not None:
            sh_vec = right_sh - left_sh
            # 水平面（X-Z）肩线相对 X 轴夹角 → 旋转代理
            horiz = np.array([float(sh_vec[0]), float(sh_vec[2])])
            hn = float(np.linalg.norm(horiz))
            if hn > 1e-3:
                metrics['trunk_rotation'] = float(np.degrees(np.arctan2(
                    abs(float(sh_vec[2])), abs(float(sh_vec[0])) + 1e-6
                )))

            if nose is not None:
                shoulder_mid = (left_sh + right_sh) / 2.0
                sw = float(np.linalg.norm(right_sh - left_sh))
                if sw > 1e-3:
                    nose_off = abs(float(nose[0] - shoulder_mid[0]))
                    rot_proxy = nose_off / (sw * 0.5 + 1e-6) * 45.0
                    metrics['shoulder_flexion_rotation'] = rot_proxy
                    metrics['head_level'] = abs(
                        float(nose[1] - shoulder_mid[1])
                    ) / sw * 30.0
                    metrics['shoulder_stability'] = abs(
                        float(left_sh[1] - right_sh[1])
                    ) / sw * 15.0

        if (
            left_sh is not None and right_sh is not None
            and left_hip is not None and right_hip is not None
        ):
            shoulder_mid = (left_sh + right_sh) / 2.0
            hip_mid = (left_hip + right_hip) / 2.0
            torso = shoulder_mid - hip_mid
            tn = float(np.linalg.norm(torso))
            if tn > 1e-6:
                up = np.array([0.0, -1.0, 0.0])
                cos_a = np.clip(np.dot(torso / tn, up), -1.0, 1.0)
                metrics['body_sway'] = float(np.degrees(np.arccos(cos_a)))

        if left_hip is not None and right_hip is not None:
            gait = self._compute_gait_step_metrics_3d(
                left_hip, right_hip, left_ankle, right_ankle,
            )
            metrics.update(gait)
            if 'step_distance' in metrics:
                metrics['trunk_sway'] = metrics.get('body_sway', 0.0)

        return metrics

    def _merge_hybrid_angles(
        self,
        angles_3d: Dict[str, float],
        angles_2d: Dict[str, float],
    ) -> Dict[str, float]:
        """2D/3D 混合：空间量 3D 优先，关节角 2D 优先。"""
        out: Dict[str, float] = {}
        stats = {'3d': 0, '2d': 0, 'blend': 0}

        all_keys = set(angles_2d.keys()) | set(angles_3d.keys())
        use_3d = self._raw_3d_is_fresh()

        for key in all_keys:
            if key.startswith('_'):
                continue

            v2 = angles_2d.get(key)
            v3 = angles_3d.get(key) if use_3d else None

            if key in self._SPATIAL_KEYS:
                if v3 is not None:
                    out[key] = v3
                    stats['3d'] += 1
                elif v2 is not None:
                    out[key] = v2
                    stats['2d'] += 1
                continue

            if v2 is not None and v3 is not None:
                if abs(v2 - v3) > 45.0:
                    out[key] = v2
                    stats['2d'] += 1
                else:
                    out[key] = round(0.65 * v2 + 0.35 * v3, 1)
                    stats['blend'] += 1
            elif v2 is not None:
                out[key] = v2
                stats['2d'] += 1
            elif v3 is not None:
                out[key] = v3
                stats['3d'] += 1

        self._last_blend_stats = stats
        return out

    def get_fusion_diagnostics(self) -> dict:
        """训练调试：混合策略状态。"""
        return {
            'raw_3d_fresh': self._raw_3d_is_fresh(),
            'raw_3d_joints': len(self._last_raw_3d),
            'raw_3d_age_ms': round(
                max(0.0, (time.time() - self._last_raw_3d_time) * 1000), 1
            ),
            'kpts_2d': len(self._last_kpts_2d_left),
            'blend_stats': dict(self._last_blend_stats),
        }

    def compute_pose_features(
        self, kpts: Dict[str, Dict] = None, min_conf: float = 0.3
    ) -> Dict[str, float]:
        """代偿特征：2D 为基础，3D 新鲜时补充空间量。"""
        features = self._compute_pose_features_2d(kpts, min_conf)
        if self._raw_3d_is_fresh():
            spatial_3d = self._compute_spatial_metrics_3d()
            for key in (
                'body_sway', 'trunk_sway', 'foot_height', 'step_distance',
                'trunk_rotation', 'shoulder_stability', 'head_level',
            ):
                if key in spatial_3d:
                    features[key] = spatial_3d[key]
        return features

    def _compute_pose_features_2d(
        self, kpts: Dict[str, Dict] = None, min_conf: float = 0.3
    ) -> Dict[str, float]:
        """从 2D 关键点提取代偿/平衡/步态等视觉特征（供纠正引擎使用）。"""
        if kpts is None:
            kpts = self._last_kpts_2d_left
        if not kpts:
            return {}

        def pt(name):
            k = kpts.get(name)
            if not k or k.get('conf', 0) < min_conf:
                return None
            return np.array([k['x'], k['y']], dtype=np.float64)

        features: Dict[str, float] = {}
        left_sh = pt('left_shoulder')
        right_sh = pt('right_shoulder')
        left_hip = pt('left_hip')
        right_hip = pt('right_hip')
        nose = pt('nose')

        if left_sh is not None and right_sh is not None:
            shoulder_mid = (left_sh + right_sh) / 2.0
            shoulder_width = float(np.linalg.norm(right_sh - left_sh))
            features['shoulder_hike'] = abs(float(left_sh[1] - right_sh[1]))

            if left_hip is not None and right_hip is not None:
                hip_mid = (left_hip + right_hip) / 2.0
                torso = shoulder_mid - hip_mid
                tn = float(np.linalg.norm(torso))
                if tn > 1e-6:
                    down = np.array([0.0, 1.0])
                    cos_a = np.clip(np.dot(torso / tn, down), -1.0, 1.0)
                    features['trunk_lean'] = float(np.degrees(np.arccos(cos_a)))
                    features['body_sway'] = features['trunk_lean']

            if nose is not None and shoulder_width > 1e-6:
                head_tilt = abs(float(nose[1] - shoulder_mid[1])) / shoulder_width * 30.0
                features['head_level'] = head_tilt
                features['shoulder_stability'] = features['shoulder_hike']

        left_knee = pt('left_knee')
        right_knee = pt('right_knee')
        left_ankle = pt('left_ankle')
        right_ankle = pt('right_ankle')

        if left_knee is not None and left_ankle is not None and left_hip is not None:
            shin = left_ankle - left_knee
            if float(np.linalg.norm(shin)) > 1e-6:
                down = np.array([0.0, 1.0])
                cos_a = np.clip(np.dot(shin / np.linalg.norm(shin), down), -1.0, 1.0)
                if float(np.degrees(np.arccos(cos_a))) > 75.0:
                    features['heel_off_ground'] = 1.0

        if left_knee is not None and left_hip is not None and left_ankle is not None:
            if left_ankle[0] > left_knee[0] + 5:
                features['knee_over_toe'] = 1.0
                features['knee_valgus'] = 1.0

        return features

    def _compute_angles_from_2d(
        self, kpts: Dict[str, Dict], min_conf: float = 0.3
    ) -> Dict[str, float]:
        """由 2D 像素坐标估算关节角（与 3D 同名键）。"""
        if not kpts:
            return {}

        def pt(name):
            k = kpts.get(name)
            if not k or k.get('conf', 0) < min_conf:
                return None
            return np.array([k['x'], k['y']], dtype=np.float64)

        def calc_angle_2d(p1, p2, p3):
            v1 = p1 - p2
            v2 = p3 - p2
            cos_angle = np.dot(v1, v2) / (
                np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8
            )
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            return float(np.degrees(np.arccos(cos_angle)))

        def calc_shoulder_flexion_2d(shoulder, elbow, hip=None):
            """
            肩前屈：取较大值
            - 髋-肩-肘（斜侧/侧身时准）
            - 上臂与画面「向下」夹角（正对镜头体前举手时准）
            """
            candidates = []
            if hip is not None:
                candidates.append(calc_angle_2d(hip, shoulder, elbow))
            v = elbow - shoulder
            n = np.linalg.norm(v)
            if n > 1e-6:
                # 图像坐标 y 向下；手臂下垂≈0°，前平举≈90°，上举≈180°
                down = np.array([0.0, 1.0])
                cos_a = np.clip(np.dot(v / n, down), -1.0, 1.0)
                candidates.append(float(np.degrees(np.arccos(cos_a))))
            return max(candidates) if candidates else None

        angles = {}

        for side in ['left', 'right']:
            hip = pt(f'{side}_hip')
            shoulder = pt(f'{side}_shoulder')
            elbow = pt(f'{side}_elbow')
            knee = pt(f'{side}_knee')
            ankle = pt(f'{side}_ankle')
            other_sh = pt(
                f'{"right" if side == "left" else "left"}_shoulder'
            )

            if shoulder is not None and elbow is not None:
                a = calc_shoulder_flexion_2d(shoulder, elbow, hip)
                if a is not None:
                    angles[f'shoulder_flexion_{side}'] = a
                    angles['shoulder_flexion'] = a

            if shoulder is not None and elbow is not None and other_sh is not None:
                a = calc_angle_2d(other_sh, shoulder, elbow)
                angles[f'shoulder_abduction_{side}'] = a
                angles['shoulder_abduction'] = a

            if hip is not None and knee is not None and ankle is not None:
                a = calc_angle_2d(hip, knee, ankle)
                angles[f'knee_flexion_{side}'] = a

            ext = self._calc_knee_extension_2d(hip, knee, ankle)
            if ext is not None:
                angles[f'knee_extension_{side}'] = ext

        knee_vals = [
            angles[k] for k in ('knee_flexion_left', 'knee_flexion_right')
            if k in angles
        ]
        if knee_vals:
            angles['knee_flexion_active'] = max(knee_vals)
            angles['knee_flexion'] = angles['knee_flexion_active']

        ext_vals = [
            angles[k] for k in ('knee_extension_left', 'knee_extension_right')
            if k in angles
        ]
        if ext_vals:
            angles['knee_extension'] = max(ext_vals)

        if 'knee_flexion' in angles and 'knee_extension' not in angles:
            angles['knee_extension'] = max(0.0, 180.0 - angles['knee_flexion'])
        if 'shoulder_flexion' in angles:
            angles['push_shoulder_flexion'] = angles['shoulder_flexion']
        if 'shoulder_abduction' in angles:
            angles['pull_shoulder_abduction'] = angles['shoulder_abduction']

        extra = self._compute_extended_pose_metrics(kpts)
        angles.update(extra)
        leg_raise = self._compute_supine_leg_raise_metrics(kpts)
        angles.update(leg_raise)

        return angles

    def _compute_extended_pose_metrics(
        self, kpts: Dict[str, Dict], min_conf: float = 0.3
    ) -> Dict[str, float]:
        """L3/L4 专用：脚离地高度、躯干旋转、步距、复合肩角等。"""
        if not kpts:
            return {}

        def pt(name):
            k = kpts.get(name)
            if not k or k.get('conf', 0) < min_conf:
                return None
            return np.array([k['x'], k['y']], dtype=np.float64)

        metrics: Dict[str, float] = {}

        left_sh = pt('left_shoulder')
        right_sh = pt('right_shoulder')
        left_hip = pt('left_hip')
        right_hip = pt('right_hip')
        left_knee = pt('left_knee')
        right_knee = pt('right_knee')
        left_ankle = pt('left_ankle')
        right_ankle = pt('right_ankle')
        nose = pt('nose')

        # ---- 单脚平衡 / 旧抬腿：保留站立场景 ----
        foot_heights = []
        for ankle, knee, other_ankle in (
            (left_ankle, left_knee, right_ankle),
            (right_ankle, right_knee, left_ankle),
        ):
            if ankle is None or knee is None:
                continue
            shank_len = float(np.linalg.norm(ankle - knee))
            if shank_len < 1e-3:
                continue
            lift_px = 0.0
            if other_ankle is not None:
                lift_px = max(0.0, float(other_ankle[1] - ankle[1]))
            foot_heights.append(lift_px / shank_len * 40.0)

        if foot_heights:
            metrics['foot_height'] = max(foot_heights)

        metrics.update(self._compute_supine_leg_raise_metrics(kpts, min_conf))

        # ---- 躯干旋转：肩线相对水平面的倾斜（0=正对，90=侧对）----
        if left_sh is not None and right_sh is not None:
            dx = abs(float(left_sh[0] - right_sh[0]))
            dy = abs(float(left_sh[1] - right_sh[1]))
            metrics['trunk_rotation'] = float(
                np.degrees(np.arctan2(dy, dx + 1e-6))
            )

            flex_vals = []
            abd_vals = []
            for side in ('left', 'right'):
                sh = pt(f'{side}_shoulder')
                el = pt(f'{side}_elbow')
                hip = pt(f'{side}_hip')
                other_sh = pt(
                    f'{"right" if side == "left" else "left"}_shoulder'
                )
                if sh is not None and el is not None and hip is not None:
                    v1 = hip - sh
                    v2 = el - sh
                    cos_a = np.dot(v1, v2) / (
                        np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8
                    )
                    flex_vals.append(float(np.degrees(np.arccos(
                        np.clip(cos_a, -1.0, 1.0)
                    ))))
                if sh is not None and el is not None and other_sh is not None:
                    v1 = other_sh - sh
                    v2 = el - sh
                    cos_a = np.dot(v1, v2) / (
                        np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8
                    )
                    abd_vals.append(float(np.degrees(np.arccos(
                        np.clip(cos_a, -1.0, 1.0)
                    ))))

            flex = max(flex_vals) if flex_vals else 0.0
            abd = max(abd_vals) if abd_vals else 0.0
            metrics['shoulder_combined'] = max(flex, abd)

            if nose is not None:
                shoulder_mid = (left_sh + right_sh) / 2.0
                shoulder_width = float(np.linalg.norm(right_sh - left_sh))
                if shoulder_width > 1e-6:
                    nose_offset = abs(float(nose[0] - shoulder_mid[0]))
                    rot_proxy = nose_offset / (shoulder_width * 0.5 + 1e-6) * 45.0
                    metrics['shoulder_flexion_rotation'] = max(flex, rot_proxy)
                    metrics['head_level'] = abs(
                        float(nose[1] - shoulder_mid[1])
                    ) / shoulder_width * 30.0
                    metrics['shoulder_stability'] = dy / (shoulder_width + 1e-6) * 15.0

        # ---- 身体晃动：躯干偏离竖直的角度 ----
        if (
            left_sh is not None and right_sh is not None
            and left_hip is not None and right_hip is not None
        ):
            shoulder_mid = (left_sh + right_sh) / 2.0
            hip_mid = (left_hip + right_hip) / 2.0
            torso = shoulder_mid - hip_mid
            tn = float(np.linalg.norm(torso))
            if tn > 1e-6:
                down = np.array([0.0, 1.0])
                cos_a = np.clip(np.dot(torso / tn, down), -1.0, 1.0)
                metrics['body_sway'] = float(np.degrees(np.arccos(cos_a)))

        # ---- 步态：相对中立站姿的踝部位移（cm）----
        if left_hip is not None and right_hip is not None:
            gait = self._compute_gait_step_metrics_2d(
                left_hip, right_hip, left_ankle, right_ankle,
            )
            metrics.update(gait)
            if 'step_distance' in metrics:
                metrics['trunk_sway'] = metrics.get('body_sway', 0.0)

        return metrics

    @staticmethod
    def _calc_knee_extension_2d(hip, knee, ankle) -> Optional[float]:
        """
        膝伸直（坐姿）：髋-膝-踝 夹角 + 小腿偏离竖直，取较大值。
        正对镜头时比单纯 180-flexion 更灵敏。
        """
        candidates = []

        def calc_angle_2d(p1, p2, p3):
            v1 = p1 - p2
            v2 = p3 - p2
            cos_angle = np.dot(v1, v2) / (
                np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8
            )
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            return float(np.degrees(np.arccos(cos_angle)))

        if hip is not None and knee is not None and ankle is not None:
            flex = calc_angle_2d(hip, knee, ankle)
            candidates.append(max(0.0, 180.0 - flex))

        if knee is not None and ankle is not None:
            shin = ankle - knee
            n = np.linalg.norm(shin)
            if n > 1e-6:
                down = np.array([0.0, 1.0])
                cos_a = np.clip(np.dot(shin / n, down), -1.0, 1.0)
                # 小腿越水平（前伸），角度越大
                candidates.append(float(np.degrees(np.arccos(cos_a))))

        if not candidates:
            return None
        return max(candidates)

    def calibrate_imu_bias(
        self,
        imu_id: str,
        static_samples: np.ndarray
    ):
        """
        标定IMU零漂（静止状态下采集若干秒数据取平均）

        Args:
            imu_id: 'imu_left' 或 'imu_right'
            static_samples: 静止状态的加速度数据，shape (N, 3)
        """
        if len(static_samples) == 0:
            return

        # 静止时加速度应该只有重力分量
        mean_accel = np.mean(static_samples, axis=0)
        # 理论静止值（假设Z轴朝上）
        gravity = np.array([0, 0, 9.81])
        self.imu_bias[imu_id] = mean_accel - gravity

        print(f"[Fusion] {imu_id} 零漂标定完成: {self.imu_bias[imu_id]}")

    def reset(self):
        """重置所有滤波器"""
        for joint in self.JOINT_NAMES:
            self.filters[joint] = self._create_filter()
        self.last_fused_state = {}
        self.frame_count = 0
        self._last_raw_3d = {}
        self._last_raw_3d_conf = {}
        self._last_raw_3d_time = 0.0
        self._joint_last_obs_time = {}
        self._last_blend_stats = {}

    def get_diagnostics(self) -> dict:
        """获取融合引擎诊断信息（供调试用）"""
        diag = {
            'frame_count': self.frame_count,
            'active_joints': len(self.filters),
            'imu_bias': {
                k: v.tolist() for k, v in self.imu_bias.items()
            },
            'filter_health': {},
        }

        for joint, kf in self.filters.items():
            trace = float(np.trace(kf.P[:3, :3]))
            diag['filter_health'][joint] = {
                'covariance_trace': round(trace, 2),
                'healthy': trace < 10000,
            }

        return diag
