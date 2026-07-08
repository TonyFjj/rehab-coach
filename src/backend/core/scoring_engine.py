"""
六维度健康评分引擎
将传感器数据转化为 0-100 分健康评分，映射到 L1-L4 康复等级

评分维度：
  1. 抬举幅度 (30分) - 肩关节外展角度
  2. 运动平滑度 (25分) - Jerk RMS值
  3. 震颤程度 (20分) - 4-12Hz频段能量占比
  4. 双侧对称性 (15分) - 左右角度/速度/延迟差异
  5. 运动速度 (5分) - 完成时间
  6. 运动耐力 (5分) - 保持阶段角度标准差
"""

import numpy as np
from typing import Dict, Tuple, Optional


class HealthScoringEngine:
    """六维度健康评分引擎"""

    def __init__(self, config: dict = None):
        """
        Args:
            config: scoring_config.yaml 中的配置字典
        """
        default_weights = {
            'range_of_motion': 0.30,
            'smoothness': 0.25,
            'tremor': 0.20,
            'symmetry': 0.15,
            'speed': 0.05,
            'endurance': 0.05,
        }
        default_max_scores = {
            'range_of_motion': 30,
            'smoothness': 25,
            'tremor': 20,
            'symmetry': 15,
            'speed': 5,
            'endurance': 5,
        }

        if config:
            self.weights = config.get('weights', default_weights)
            self.max_scores = config.get('max_scores', default_max_scores)
        else:
            self.weights = default_weights
            self.max_scores = default_max_scores

    def evaluate(self, dimension_inputs: Dict[str, float]) -> Dict:
        """
        根据各维度 0-100 分输入，计算总分与等级（初评/联调用）。

        Args:
            dimension_inputs: 如 {'range_of_motion': 60, 'smoothness': 70, ...}

        Returns:
            {'total_score', 'level', 'dimension_scores'}
        """
        dimension_scores = {}
        for key, max_pts in self.max_scores.items():
            raw = float(dimension_inputs.get(key, 0))
            raw = float(np.clip(raw, 0, 100))
            dimension_scores[key] = round(raw / 100.0 * max_pts, 1)

        total_score = float(np.clip(sum(dimension_scores.values()), 0, 100))
        level = self._map_level(total_score)

        return {
            'total_score': total_score,
            'level': level,
            'dimension_scores': dimension_scores,
        }

    def compute_score(
        self,
        imu_data_left: dict,
        imu_data_right: dict,
        vision_data: dict = None,
        test_duration: float = 25.0
    ) -> Tuple[float, str, Dict[str, float]]:
        """
        计算综合健康评分

        Args:
            imu_data_left: 左手IMU数据
                {
                    'accel': np.ndarray (N, 3),     # 加速度 m/s²
                    'gyro': np.ndarray (N, 3),      # 角速度 rad/s
                    'timestamps': np.ndarray (N,),  # 时间戳
                    'sample_rate': float             # 采样率Hz
                }
            imu_data_right: 右手IMU数据 (同上)
            vision_data: 双目视觉数据 (可选，摄像头到后填充)
                {
                    'keypoints_3d': list[np.ndarray],  # 每帧3D关键点
                    'timestamps': np.ndarray,
                    'fps': float
                }
            test_duration: 测试总时长(秒)

        Returns:
            (total_score, level, dimension_scores)
            total_score: 0-100
            level: 'L1'/'L2'/'L3'/'L4'
            dimension_scores: 各维度得分字典
        """
        features = self._extract_features(
            imu_data_left, imu_data_right, vision_data, test_duration
        )

        scores = {
            'range_of_motion': self._score_rom(
                features['max_angle_left'],
                features['max_angle_right']
            ),
            'smoothness': self._score_smoothness(
                features['rmsj_left'],
                features['rmsj_right']
            ),
            'tremor': self._score_tremor(
                features['tremor_ratio_left'],
                features['tremor_ratio_right']
            ),
            'symmetry': self._score_symmetry(
                features['max_angle_left'],
                features['max_angle_right'],
                features['completion_time_left'],
                features['completion_time_right'],
                features['start_delay']
            ),
            'speed': self._score_speed(
                features['completion_time_left'],
                features['completion_time_right'],
                features.get('trunk_compensation', False)
            ),
            'endurance': self._score_endurance(
                features['hold_std_left'],
                features['hold_std_right'],
                features['hold_angle_drop_left'],
                features['hold_angle_drop_right']
            ),
        }

        total_score = sum(scores.values())
        total_score = float(np.clip(total_score, 0, 100))

        level = self._map_level(total_score)

        return total_score, level, scores

    # ==================== 特征提取 ====================

    def _extract_features(
        self,
        imu_left: dict,
        imu_right: dict,
        vision_data: dict,
        test_duration: float
    ) -> dict:
        """从原始传感器数据中提取六维度特征"""

        sample_rate = imu_left.get('sample_rate', 100.0)
        accel_left = np.array(imu_left['accel'])
        accel_right = np.array(imu_right['accel'])
        gyro_left = np.array(imu_left['gyro'])
        gyro_right = np.array(imu_right['gyro'])

        # 1. 抬举幅度
        max_angle_left = self._calc_max_angle(accel_left)
        max_angle_right = self._calc_max_angle(accel_right)

        # 2. 运动平滑度 (Jerk RMS)
        rmsj_left = self._calc_rmsj(accel_left, sample_rate)
        rmsj_right = self._calc_rmsj(accel_right, sample_rate)

        # 3. 震颤程度 (4-12Hz能量占比)
        tremor_ratio_left = self._calc_tremor_ratio(gyro_left, sample_rate)
        tremor_ratio_right = self._calc_tremor_ratio(gyro_right, sample_rate)

        # 4. 完成时间
        completion_time_left = self._calc_completion_time(
            accel_left, sample_rate
        )
        completion_time_right = self._calc_completion_time(
            accel_right, sample_rate
        )

        # 5. 启动延迟
        start_delay = self._calc_start_delay(
            accel_left, accel_right, sample_rate
        )

        # 6. 保持阶段指标 (测试第15-20秒)
        hold_start = int(15 * sample_rate)
        hold_end = int(20 * sample_rate)

        hold_angles_left = self._calc_angle_series(
            accel_left[hold_start:hold_end] if hold_start < len(accel_left) else accel_left[-100:]
        )
        hold_angles_right = self._calc_angle_series(
            accel_right[hold_start:hold_end] if hold_start < len(accel_right) else accel_right[-100:]
        )

        hold_std_left = float(np.std(hold_angles_left)) if len(hold_angles_left) > 0 else 20.0
        hold_std_right = float(np.std(hold_angles_right)) if len(hold_angles_right) > 0 else 20.0

        hold_angle_drop_left = self._calc_hold_drop(hold_angles_left, max_angle_left)
        hold_angle_drop_right = self._calc_hold_drop(hold_angles_right, max_angle_right)

        return {
            'max_angle_left': max_angle_left,
            'max_angle_right': max_angle_right,
            'rmsj_left': rmsj_left,
            'rmsj_right': rmsj_right,
            'tremor_ratio_left': tremor_ratio_left,
            'tremor_ratio_right': tremor_ratio_right,
            'completion_time_left': completion_time_left,
            'completion_time_right': completion_time_right,
            'start_delay': start_delay,
            'hold_std_left': hold_std_left,
            'hold_std_right': hold_std_right,
            'hold_angle_drop_left': hold_angle_drop_left,
            'hold_angle_drop_right': hold_angle_drop_right,
            'trunk_compensation': False,  # 视觉模块到后填充
        }

    # ==================== 特征计算函数 ====================

    def _calc_max_angle(self, accel: np.ndarray) -> float:
        """通过加速度计算手臂抬起的最大角度"""
        if len(accel) == 0:
            return 0.0
        angles = np.degrees(
            np.arctan2(
                np.sqrt(accel[:, 0]**2 + accel[:, 1]**2),
                accel[:, 2]
            )
        )
        return float(np.max(angles))

    def _calc_angle_series(self, accel: np.ndarray) -> np.ndarray:
        """计算角度时间序列"""
        if len(accel) == 0:
            return np.array([])
        angles = np.degrees(
            np.arctan2(
                np.sqrt(accel[:, 0]**2 + accel[:, 1]**2),
                accel[:, 2]
            )
        )
        return angles

    def _calc_rmsj(self, accel: np.ndarray, sample_rate: float) -> float:
        """
        计算 Jerk 的 RMS 值
        Jerk = 加速度的三阶导数，RMSJ越大动作越不平滑
        """
        if len(accel) < 4:
            return 60.0
        dt = 1.0 / sample_rate
        jerk = np.diff(accel, n=3, axis=0) / (dt ** 3)
        jerk_magnitude = np.linalg.norm(jerk, axis=1)
        rmsj = np.sqrt(np.mean(jerk_magnitude ** 2))
        return float(rmsj)

    def _calc_tremor_ratio(self, gyro: np.ndarray, sample_rate: float) -> float:
        """
        通过FFT计算4-12Hz频段能量占比
        该频段覆盖生理性震颤(4-6Hz)和帕金森震颤(4-8Hz)
        """
        if len(gyro) < 10:
            return 0.5
        gyro_mag = np.linalg.norm(gyro, axis=1)
        n = len(gyro_mag)
        fft_vals = np.fft.rfft(gyro_mag)
        fft_power = np.abs(fft_vals) ** 2
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

        total_power = np.sum(fft_power)
        if total_power == 0:
            return 0.0

        mask = (freqs >= 4.0) & (freqs <= 12.0)
        tremor_power = np.sum(fft_power[mask])
        return float(tremor_power / total_power)

    def _calc_completion_time(self, accel: np.ndarray, sample_rate: float) -> float:
        """计算从动作开始到达最大角度的时间"""
        if len(accel) == 0:
            return 20.0
        angles = self._calc_angle_series(accel)
        # 跳过前5秒准备阶段
        start_idx = int(5 * sample_rate)
        if start_idx >= len(angles):
            return 20.0
        test_angles = angles[start_idx:]
        if len(test_angles) == 0:
            return 20.0
        max_idx = np.argmax(test_angles)
        return float(max_idx / sample_rate)

    def _calc_start_delay(
        self, accel_left: np.ndarray, accel_right: np.ndarray,
        sample_rate: float
    ) -> float:
        """计算左右手开始动作的时间差"""
        threshold = 5.0

        def find_start(accel):
            angles = self._calc_angle_series(accel)
            start_idx = int(5 * sample_rate)
            if start_idx >= len(angles):
                return 0
            baseline = np.mean(angles[start_idx:start_idx + int(sample_rate)])
            for i in range(start_idx, len(angles)):
                if angles[i] - baseline > threshold:
                    return i
            return start_idx

        start_left = find_start(accel_left)
        start_right = find_start(accel_right)
        return float(abs(start_left - start_right) / sample_rate)

    def _calc_hold_drop(self, hold_angles: np.ndarray, max_angle: float) -> float:
        """计算保持阶段角度下降比例"""
        if len(hold_angles) == 0 or max_angle == 0:
            return 1.0
        min_hold = np.min(hold_angles)
        return float((max_angle - min_hold) / max_angle)

    # ==================== 评分函数 ====================

    def _score_rom(self, max_left: float, max_right: float) -> float:
        """抬举幅度评分 (0-30分)"""
        avg_angle = (max_left + max_right) / 2.0
        score = (avg_angle / 180.0) * 30.0
        if abs(max_left - max_right) > 20:
            score -= 2.0
        return float(np.clip(score, 0, 30))

    def _score_smoothness(self, rmsj_left: float, rmsj_right: float) -> float:
        """运动平滑度评分 (0-25分)"""
        avg_rmsj = (rmsj_left + rmsj_right) / 2.0
        score = 25.0 * max(0.0, 1.0 - avg_rmsj / 60.0)
        return float(np.clip(score, 0, 25))

    def _score_tremor(self, tremor_left: float, tremor_right: float) -> float:
        """震颤程度评分 (0-20分)"""
        avg_tremor = (tremor_left + tremor_right) / 2.0
        score = 20.0 * max(0.0, 1.0 - avg_tremor / 0.5)
        return float(np.clip(score, 0, 20))

    def _score_symmetry(
        self, angle_left: float, angle_right: float,
        time_left: float, time_right: float,
        start_delay: float
    ) -> float:
        """双侧对称性评分 (0-15分)"""
        angle_diff = abs(angle_left - angle_right)
        angle_score = 15.0 * max(0.0, 1.0 - angle_diff / 50.0) * 0.5

        time_diff = abs(time_left - time_right)
        speed_score = 15.0 * max(0.0, 1.0 - time_diff / 5.0) * 0.3

        delay_score = 15.0 * max(0.0, 1.0 - start_delay / 3.0) * 0.2

        return float(np.clip(angle_score + speed_score + delay_score, 0, 15))

    def _score_speed(
        self, time_left: float, time_right: float,
        trunk_compensation: bool = False
    ) -> float:
        """运动速度评分 (0-5分)"""
        avg_time = (time_left + time_right) / 2.0
        score = 5.0 * max(0.0, 1.0 - avg_time / 20.0)
        if trunk_compensation:
            score -= 1.0
        return float(np.clip(score, 0, 5))

    def _score_endurance(
        self, std_left: float, std_right: float,
        drop_left: float, drop_right: float
    ) -> float:
        """运动耐力评分 (0-5分)"""
        avg_std = (std_left + std_right) / 2.0
        score = 5.0 * max(0.0, 1.0 - avg_std / 20.0)
        avg_drop = (drop_left + drop_right) / 2.0
        if avg_drop > 0.3:
            score = min(score, 2.0)
        return float(np.clip(score, 0, 5))

    def _map_level(self, score: float) -> str:
        """评分映射到康复等级"""
        if score <= 30:
            return 'L1'
        elif score <= 60:
            return 'L2'
        elif score <= 80:
            return 'L3'
        else:
            return 'L4'
