"""
初始健康评估
引导患者完成6个维度的测试动作，计算初始评分和等级
"""

import time
import numpy as np
from typing import Dict, Optional

from core.scoring_engine import HealthScoringEngine
from fusion.kalman_fusion import SensorFusionEngine
from interface.imu_interface import IMUInterface
from llm.tts_engine import TTSEngine


from assessment_plan import (
    ANALYZING_TEXT,
    ANALYZING_TTS,
    ACTION_TTS,
    COLLECT_START_TTS,
    DONE_TEXT,
    INTRO_TEXT,
    INTRO_TTS,
    PREPARE_AFTER_INSTRUCTION,
    REST_BETWEEN_ACTIONS,
    REST_TEXT,
    TEST_ACTIONS,
)


class InitialAssessment:
    """
    初始健康评估

    流程：
    1. 引导患者做3-4个标准测试动作
    2. 实时采集传感器数据
    3. 提取六维度特征
    4. 计算综合评分和等级

    模拟模式下使用随机生成的传感器数据
    """

    def __init__(
        self,
        scoring_engine: HealthScoringEngine,
        fusion_engine: SensorFusionEngine,
        imu_interface: IMUInterface,
        tts: TTSEngine,
        simulate: bool = True,
        qt_interface=None,
    ):
        self.scoring_engine = scoring_engine
        self.fusion_engine = fusion_engine
        self.imu_interface = imu_interface
        self.tts = tts
        self.simulate = simulate
        self.qt_interface = qt_interface

        # 采集到的原始特征
        self.raw_features: Dict[str, list] = {
            'angles': [],          # 各帧的关节角度
            'angular_velocities': [],  # 角速度
            'jerks': [],           # 急动度
            'tremor_ratios': [],   # 震颤比
            'symmetry_diffs': [],  # 左右差异
            'hold_times': [],      # 保持时间
        }

    def _emit_phase(self, phase: str, **kwargs):
        if self.qt_interface is None:
            return
        self.qt_interface.send_assessment_phase(phase=phase, **kwargs)

    def run(self) -> dict:
        """
        运行完整评估流程

        Returns:
            {
                'total_score': float,
                'level': str,
                'dimension_scores': {
                    'range_of_motion': float,
                    'smoothness': float,
                    'tremor': float,
                    'symmetry': float,
                    'speed': float,
                    'endurance': float,
                },
                'raw_features': dict,
            }
        """
        print("\n--- 初始健康评估开始 ---\n")
        total = len(TEST_ACTIONS)

        self._emit_phase(
            'intro',
            action_index=0,
            total_actions=total,
            instruction=INTRO_TEXT,
            duration=0,
        )
        self.tts.speak_and_wait(INTRO_TTS)

        for i, action in enumerate(TEST_ACTIONS):
            print(f"\n[评估 {i+1}/{total}] {action['name']}")

            self._emit_phase(
                'action',
                action_index=i + 1,
                total_actions=total,
                action_name=action['name'],
                instruction=action['instruction'],
                duration=action.get('total_duration', action['duration']),
            )
            self.tts.speak_and_wait(ACTION_TTS)
            time.sleep(PREPARE_AFTER_INSTRUCTION)

            prep_dur = int(action.get('prep_duration', 0))
            motion_dur = int(action.get('duration', 10))
            motion_text = action.get('motion_instruction', action['instruction'])
            collect_dur = int(action.get('total_duration', motion_dur))
            if prep_dur > 0:
                prep_text = action.get('prep_instruction', action['instruction'])
                self._emit_phase(
                    'collecting',
                    action_index=i + 1,
                    total_actions=total,
                    action_name=action['name'],
                    instruction=prep_text,
                    duration=prep_dur,
                    sub_phase='prep',
                )
                self.tts.speak_and_wait(prep_text)
                if self.simulate:
                    time.sleep(min(prep_dur * 0.25, 1.5))
                else:
                    time.sleep(prep_dur)

                self._emit_phase(
                    'collecting',
                    action_index=i + 1,
                    total_actions=total,
                    action_name=action['name'],
                    instruction=motion_text,
                    duration=motion_dur,
                    sub_phase='motion',
                )
                self.tts.speak('请现在开始侧平举并举过头顶。')
            else:
                self._emit_phase(
                    'collecting',
                    action_index=i + 1,
                    total_actions=total,
                    action_name=action['name'],
                    instruction=action['instruction'],
                    duration=collect_dur,
                )
                self.tts.speak(COLLECT_START_TTS)

            collect_action = dict(action)
            collect_action['duration'] = prep_dur + collect_dur if prep_dur > 0 else collect_dur
            features = self._collect_action_data(collect_action)
            self._merge_features(features)

            # 动作间休息
            if REST_BETWEEN_ACTIONS > 0 and i < total - 1:
                self._emit_phase(
                    'rest',
                    action_index=i + 1,
                    total_actions=total,
                    action_name=action['name'],
                    instruction=REST_TEXT,
                    duration=int(REST_BETWEEN_ACTIONS),
                )
                self.tts.speak_and_wait(REST_TEXT)
                time.sleep(REST_BETWEEN_ACTIONS)

        self._emit_phase(
            'analyzing',
            action_index=total,
            total_actions=total,
            instruction=ANALYZING_TEXT,
            duration=0,
        )
        self.tts.speak(ANALYZING_TTS)

        dimension_inputs = self._compute_dimension_inputs()

        print("\n--- 计算评分中... ---")
        result = self.scoring_engine.evaluate(dimension_inputs)

        total_score = result['total_score']
        level = result['level']
        dimension_scores = result['dimension_scores']

        print(f"\n===== 评估结果 =====")
        print(f"  综合评分: {total_score:.1f}")
        print(f"  康复等级: {level}")
        print(f"  各维度:")
        for dim, score in dimension_scores.items():
            print(f"    {dim}: {score:.1f}")
        print(f"====================\n")

        self._emit_phase(
            'done',
            action_index=total,
            total_actions=total,
            instruction=DONE_TEXT,
            duration=0,
        )

        return {
            'total_score': total_score,
            'level': level,
            'dimension_scores': dimension_scores,
            'raw_features': self.raw_features,
        }

    def _collect_action_data(self, action: dict) -> dict:
        """
        采集单个测试动作的传感器数据

        Args:
            action: 测试动作配置

        Returns:
            提取的特征字典
        """
        duration = action['duration']
        features = {
            'angles': [],
            'angular_velocities': [],
            'jerks': [],
            'tremor_samples': [],
            'left_angles': [],
            'right_angles': [],
            'peak_angle': 0,
            'hold_time': 0,
        }

        if self.simulate:
            features = self._simulate_action_data(action)
        else:
            features = self._real_action_data(action, duration)

        return features

    def _simulate_action_data(self, action: dict) -> dict:
        """模拟模式：生成随机但合理的测试数据"""

        # 模拟一个举手动作的角度轨迹
        duration = action['duration']
        fps = 30
        total_frames = duration * fps

        # 基础能力（随机，代表患者的实际能力）
        ability = np.random.uniform(0.3, 0.9)

        # 最大角度 = 能力 × 180°
        max_angle = ability * 160 + 20

        # 生成角度轨迹（上升-保持-下降）
        rise_frames = int(total_frames * 0.35)
        hold_frames = int(total_frames * 0.3)
        fall_frames = total_frames - rise_frames - hold_frames

        rise = np.linspace(10, max_angle, rise_frames)
        hold = np.full(hold_frames, max_angle) + \
            np.random.normal(0, 2, hold_frames)
        fall = np.linspace(max_angle, 10, fall_frames)

        angles = np.concatenate([rise, hold, fall])

        # 添加噪声和震颤
        tremor_level = np.random.uniform(0.02, 0.15)
        noise = np.random.normal(0, 1.5, len(angles))
        tremor = tremor_level * 10 * np.sin(
            2 * np.pi * 8 * np.arange(len(angles)) / fps
        )
        angles = angles + noise + tremor

        # 计算角速度
        dt = 1.0 / fps
        velocities = np.diff(angles) / dt

        # 计算急动度（加速度的变化率）
        accels = np.diff(velocities) / dt
        jerks_arr = np.diff(accels) / dt

        # 左右对称性差异
        symmetry_noise = np.random.uniform(2, 15)

        # 保持时间
        hold_duration = hold_frames / fps

        features = {
            'angles': angles.tolist(),
            'angular_velocities': velocities.tolist(),
            'jerks': np.abs(jerks_arr).tolist(),
            'tremor_samples': tremor.tolist(),
            'left_angles': angles.tolist(),
            'right_angles': (angles - symmetry_noise +
                             np.random.normal(0, 1, len(angles))).tolist(),
            'peak_angle': float(max_angle),
            'hold_time': hold_duration,
        }

        # 打印模拟结果
        print(f"  [模拟] 能力系数: {ability:.2f}, "
              f"峰值角度: {max_angle:.0f}°, "
              f"震颤: {tremor_level:.2f}, "
              f"对称差: {symmetry_noise:.1f}°")

        # 模拟采集时间
        time.sleep(min(duration * 0.3, 2.0))

        return features

    def _real_action_data(self, action: dict, duration: float) -> dict:
        """真实模式：从传感器采集数据"""
        features = {
            'angles': [],
            'angular_velocities': [],
            'jerks': [],
            'tremor_samples': [],
            'left_angles': [],
            'right_angles': [],
            'peak_angle': 0,
            'hold_time': 0,
        }

        start_time = time.time()
        prev_angle = 0
        prev_velocity = 0

        while time.time() - start_time < duration:
            # 获取融合后的骨骼状态
            fused = self.fusion_engine.get_fused_state()
            angles = self.fusion_engine.compute_joint_angles(fused)

            measure = action.get('measure', 'shoulder_flexion')

            # 主测量关节
            angle_left = angles.get(f'{measure}_left', 0)
            angle_right = angles.get(f'{measure}_right', 0)
            angle = max(angle_left, angle_right)

            features['angles'].append(angle)
            features['left_angles'].append(angle_left)
            features['right_angles'].append(angle_right)

            if angle > features['peak_angle']:
                features['peak_angle'] = angle

            # 角速度
            dt = 1.0 / 30.0
            velocity = (angle - prev_angle) / dt
            features['angular_velocities'].append(velocity)

            # 急动度
            accel = (velocity - prev_velocity) / dt
            features['jerks'].append(abs(accel))

            prev_angle = angle
            prev_velocity = velocity

            time.sleep(dt)

        return features

    def _merge_features(self, features: dict):
        """合并单次动作的特征到总特征中"""
        self.raw_features['angles'].extend(features.get('angles', []))
        self.raw_features['angular_velocities'].extend(
            features.get('angular_velocities', [])
        )
        self.raw_features['jerks'].extend(features.get('jerks', []))
        self.raw_features['hold_times'].append(features.get('hold_time', 0))

        # 震颤比
        tremor_samples = features.get('tremor_samples', [])
        if tremor_samples:
            tremor_power = np.mean(np.array(tremor_samples) ** 2)
            total_power = np.mean(np.array(features['angles']) ** 2) + 1e-8
            self.raw_features['tremor_ratios'].append(
                tremor_power / total_power
            )

        # 左右对称差异
        left = features.get('left_angles', [])
        right = features.get('right_angles', [])
        if left and right:
            min_len = min(len(left), len(right))
            diffs = np.abs(
                np.array(left[:min_len]) - np.array(right[:min_len])
            )
            self.raw_features['symmetry_diffs'].append(float(np.mean(diffs)))

    def _compute_dimension_inputs(self) -> dict:
        """从原始特征计算六维度评分输入"""
        angles = np.array(self.raw_features['angles'])
        velocities = np.array(self.raw_features['angular_velocities'])
        jerks_arr = np.array(self.raw_features['jerks'])

        # 1. 关节活动度 ROM（0-180° → 0-100分）
        peak = np.max(angles) if len(angles) > 0 else 0
        rom_score = min(100, peak / 1.6)

        # 2. 平滑度（基于急动度，急动度越小越平滑）
        avg_jerk = np.mean(jerks_arr) if len(jerks_arr) > 0 else 50
        smoothness_score = max(0, 100 - avg_jerk * 0.5)

        # 3. 震颤（震颤比越小越好）
        tremor_ratios = self.raw_features['tremor_ratios']
        avg_tremor = np.mean(tremor_ratios) if tremor_ratios else 0.05
        tremor_score = max(0, 100 - avg_tremor * 500)

        # 4. 对称性（左右差异越小越好）
        sym_diffs = self.raw_features['symmetry_diffs']
        avg_sym = np.mean(sym_diffs) if sym_diffs else 10
        symmetry_score = max(0, 100 - avg_sym * 3)

        # 5. 速度（在合理范围内得高分）
        avg_vel = np.mean(np.abs(velocities)) if len(velocities) > 0 else 20
        # 理想速度 20-40 °/s
        if 15 <= avg_vel <= 45:
            speed_score = 90
        elif 10 <= avg_vel <= 60:
            speed_score = 70
        else:
            speed_score = max(0, 50 - abs(avg_vel - 30))

        # 6. 耐力（保持时间越接近目标越好）
        hold_times = self.raw_features['hold_times']
        avg_hold = np.mean(hold_times) if hold_times else 2
        # 理想保持 2-5 秒
        if 2 <= avg_hold <= 5:
            endurance_score = 85
        elif 1 <= avg_hold <= 8:
            endurance_score = 65
        else:
            endurance_score = 40

        return {
            'range_of_motion': float(np.clip(rom_score, 0, 100)),
            'smoothness': float(np.clip(smoothness_score, 0, 100)),
            'tremor': float(np.clip(tremor_score, 0, 100)),
            'symmetry': float(np.clip(symmetry_score, 0, 100)),
            'speed': float(np.clip(speed_score, 0, 100)),
            'endurance': float(np.clip(endurance_score, 0, 100)),
        }
