"""
训练会话
管理一次完整的训练流程：加载动作 → 逐个执行 → 实时纠正 → 评分 → 总结
"""

import time
import numpy as np
from typing import Dict, List, Optional

from core.scoring_engine import HealthScoringEngine
from core.action_state_machine import ActionStateMachine, ActionState
from core.correction_engine import CorrectionEngine
from core.level_manager import LevelManager

from fusion.kalman_fusion import SensorFusionEngine

from llm.prompt_builder import PromptBuilder
from llm.llm_inference import LLMInference
from llm.tts_engine import TTSEngine
from llm.tts_text import (
    action_intro_description,
    action_intro_title,
    rest_between_actions,
)

from interface.imu_interface import IMUInterface
from interface.qt_interface import QtInterface


class TrainingSession:
    """
    训练会话控制器

    一次训练的完整流程：
    1. 加载当前等级的动作列表
    2. 逐个动作执行：
       a. 语音播报动作说明
       b. 启动状态机
       c. 每帧更新状态机 + 纠正引擎
       d. 实时播报纠正/鼓励
       e. 动作完成后评分
    3. 所有动作完成后汇总评分
    """

    def __init__(
        self,
        level: str,
        level_manager: LevelManager,
        scoring_engine: HealthScoringEngine,
        fusion_engine: SensorFusionEngine,
        imu_interface: IMUInterface,
        llm: LLMInference,
        tts: TTSEngine,
        prompt_builder: PromptBuilder,
        qt_interface: QtInterface,
        simulate: bool = True,
        vision_pipeline=None,
        action_ids: Optional[List[str]] = None,
        body_region: Optional[str] = None,
    ):
        self.level = level
        self.action_ids = action_ids
        self.body_region = body_region
        self.level_manager = level_manager
        self.scoring_engine = scoring_engine
        self.fusion_engine = fusion_engine
        self.imu_interface = imu_interface
        self.llm = llm
        self.tts = tts
        self.prompt_builder = prompt_builder
        self.qt_interface = qt_interface
        self.simulate = simulate
        self.vision_pipeline = vision_pipeline

        # 训练结果
        self.actions_completed: List[dict] = []
        self.session_scores: List[float] = []
        self.is_running = False
        self.is_paused = False
        self._current_state_machine: Optional[ActionStateMachine] = None

    def run(self) -> dict:
        """
        运行完整训练会话

        Returns:
            {
                'session_score': float,
                'actions_completed': list,
                'level': str,
                'duration': float,
            }
        """
        self.is_running = True
        start_time = time.time()

        # 获取动作列表（可按 action_ids / body_region 筛选）
        actions = self.level_manager.get_training_sequence(
            self.level, body_region=self.body_region
        )
        actions = self._filter_actions(actions)

        if not actions:
            print(f"[WARNING] {self.level}级没有可用的动作配置")
            self.tts.speak("抱歉，当前等级没有训练动作，请联系管理员。")
            return {
                'session_score': 0,
                'actions_completed': [],
                'level': self.level,
                'duration': 0,
            }

        if self.action_ids:
            print(f"\n本次训练（指定动作）共 {len(actions)} 个动作\n")
        else:
            print(f"\n本次训练共 {len(actions)} 个动作\n")

        # 逐个执行动作
        for i, action_config in enumerate(actions):
            if not self.is_running:
                print("[训练] 训练被中断")
                break

            action_name = action_config.get('name', f'动作{i+1}')
            action_id = action_config.get('id', f'action_{i+1}')

            print(f"\n{'='*40}")
            print(f"  动作 {i+1}/{len(actions)}: {action_name}")
            print(f"{'='*40}")

            # 播报动作说明（名称 + 简介分两句，使用预生成音频）
            description = action_config.get(
                'description', f'请按照提示完成{action_name}'
            )
            title_text = action_intro_title(i + 1, action_name)
            desc_text = action_intro_description(description)
            self.tts.speak_and_wait(title_text)
            self.tts.speak_and_wait(desc_text)
            time.sleep(0.5)

            # 执行动作
            action_result = self._execute_action(action_config)
            self.actions_completed.append(action_result)
            self.session_scores.append(action_result.get('score', 0))

            # 记录到等级管理器
            self.level_manager.record_action_completion(
                level=self.level,
                action_id=action_id,
                score=action_result.get('score', 0),
                details=action_result
            )

            # 推送进度
            completed_scores = [
                round(float(a.get('score', 0)), 1)
                for a in self.actions_completed
            ]
            self.qt_interface.send_training_progress(
                level=self.level,
                completed_actions=i + 1,
                total_actions=len(actions),
                completion_rate=(i + 1) / len(actions),
                current_action_id=action_id,
                current_action_name=action_name,
                action_scores=completed_scores,
            )

            # 动作间休息
            if i < len(actions) - 1 and self.is_running:
                rest_time = action_config.get('rest_between_sets', 5)
                rest_text = rest_between_actions(rest_time)
                self.tts.speak_and_wait(rest_text)
                time.sleep(min(rest_time, 3.0) if self.simulate else rest_time)

        # 计算会话总评分
        session_score = (
            sum(self.session_scores) / len(self.session_scores)
            if self.session_scores else 0
        )

        duration = time.time() - start_time
        self.is_running = False

        result = {
            'session_score': round(session_score, 1),
            'actions_completed': self.actions_completed,
            'level': self.level,
            'duration': round(duration, 1),
        }

        print(f"\n训练完成！会话评分: {session_score:.1f}")
        return result

    def _filter_actions(self, actions: List[dict]) -> List[dict]:
        """按 action_ids 过滤；未配置则返回完整序列。"""
        if not self.action_ids:
            return actions
        wanted = set(self.action_ids)
        filtered = [a for a in actions if a.get('id') in wanted]
        if filtered:
            return filtered
        for aid in self.action_ids:
            ac = self.level_manager.get_action_by_id(self.level, aid)
            if ac:
                filtered.append(ac)
        return filtered

    def pause(self):
        """暂停当前动作（计时与状态机冻结）。"""
        self.is_paused = True
        if self._current_state_machine:
            self._current_state_machine.pause()

    def resume(self):
        """从暂停恢复。"""
        self.is_paused = False
        if self._current_state_machine:
            self._current_state_machine.resume()

    def stop(self):
        """结束训练会话（当前动作一并结束）。"""
        self.is_running = False
        self.is_paused = False
        if self._current_state_machine:
            self._current_state_machine.stop()

    def _execute_action(self, action_config: dict) -> dict:
        """
        执行单个动作

        Args:
            action_config: 动作配置

        Returns:
            动作结果字典
        """
        action_id = action_config.get('id', 'unknown')
        action_name = action_config.get('name', '未知动作')

        # 创建状态机和纠正引擎
        state_machine = ActionStateMachine(action_config)
        correction_engine = CorrectionEngine(action_config)

        # 设置状态机回调
        state_machine.set_callbacks(
            on_state_change=lambda old, new:
                self._on_state_change(old, new, action_name),
            on_rep_complete=lambda count, rep_data:
                self._on_rep_complete(
                    count, rep_data, action_name, state_machine
                ),
            on_action_complete=lambda total, records:
                self._on_all_complete(total, records, action_name),
        )

        # 启动状态机（动作说明已在上方语音播报）
        state_machine.start(skip_preparing=True)
        self._current_state_machine = state_machine
        if hasattr(self.fusion_engine, 'reset_supine_leg_baselines'):
            self.fusion_engine.reset_supine_leg_baselines()
        if hasattr(self.fusion_engine, 'reset_gait_baselines'):
            self.fusion_engine.reset_gait_baselines()

        # 主循环
        dt = 1.0 / 30.0  # 30fps
        frame_count = 0
        max_frames = 60 * 30  # 最多60秒

        while state_machine.is_active() and \
              frame_count < max_frames and \
              self.is_running:

            if self.is_paused:
                if frame_count % 15 == 0:
                    qt_status = self._pack_qt_action_status(
                        action_config,
                        state_machine._get_status(),
                        state_machine.current_angles or {},
                    )
                    qt_status['state'] = ActionState.PAUSED.value
                    self.qt_interface.send_action_status(**qt_status)
                time.sleep(0.05)
                continue

            # 获取当前关节角度
            if self.simulate:
                joint_angles = self._simulate_joint_angles(
                    action_config, frame_count, dt
                )
                imu_features = self._simulate_imu_features(frame_count, dt)
                vision_features = {}
            else:
                if self.vision_pipeline is not None:
                    latest = self.vision_pipeline.get_latest_skeleton()
                    if latest:
                        k2d = latest.get('keypoints_2d_left') or {}
                        self.fusion_engine.set_vision_2d_left(k2d)
                        sk3d = latest.get('skeleton_3d') or {}
                        self.fusion_engine.set_raw_skeleton_3d(sk3d)
                joint_angles = self.fusion_engine.compute_joint_angles()
                imu_features = self._extract_imu_features()
                vision_features = self.fusion_engine.compute_pose_features()

            # 更新状态机
            status = state_machine.update(joint_angles, imu_features, dt)

            if not self.simulate and frame_count % 90 == 0:
                jname = state_machine.primary_metric_name
                unit = 'cm' if jname in ('foot_height', 'step_distance') else '°'
                n2d = len(self.fusion_engine._last_kpts_2d_left)
                fd = self.fusion_engine.get_fusion_diagnostics()
                src = '3D+2D' if fd.get('raw_3d_fresh') else '2D'
                print(
                    f"  [训练] 状态={status.get('state')} "
                    f"次数={status.get('rep_count', 0)} "
                    f"{jname}={joint_angles.get(jname, 0):.1f}{unit} "
                    f"({src}, 2d点={n2d}, 3d点={fd.get('raw_3d_joints', 0)})"
                )

            # 纠正引擎评估（降低频率，避免语音过密）
            if frame_count % 15 == 0:
                errors, corrections = correction_engine.evaluate(
                    joint_angles=joint_angles,
                    imu_features=imu_features,
                    vision_features=vision_features,
                    timing_info={
                        'current_phase': status.get('state', ''),
                        **status.get('phase_timings', {}),
                    },
                )

                if corrections:
                    self.qt_interface.send_correction(corrections)
                    corr = corrections[0]
                    msg = corr.get('message', '')
                    severity = corr.get('severity', 'info')
                    if severity == 'info':
                        pass
                    elif severity == 'critical':
                        self.tts.speak_alert(msg)
                    elif severity == 'warning':
                        self.tts.speak_correction(msg)

            # 推送动作状态 / 关节角给 Qt（字段与 main 终端 [训练] 日志一致）
            if frame_count % 3 == 0:
                qt_status = self._pack_qt_action_status(
                    action_config, status, joint_angles
                )
                self.qt_interface.send_action_status(**qt_status)
            if frame_count % 2 == 0:
                self.qt_interface.send_joint_angles(joint_angles)

            frame_count += 1
            time.sleep(dt if not self.simulate else dt * 0.1)

        # 动作完成，计算评分
        quality = state_machine.get_completion_quality()
        correction_summary = correction_engine.get_summary()

        # 简易评分计算
        score = self._calculate_action_score(quality, correction_summary)

        result = {
            'action_id': action_id,
            'name': action_name,
            'score': score,
            'reps': quality.get('total_reps', 0),
            'peak_angle': quality.get('avg_peak_angle', 0),
            'reach_rate': quality.get('reach_rate', 0),
            'total_corrections': correction_summary.get(
                'total_corrections', 0
            ),
            'quality': quality,
        }

        print(f"  动作完成: {action_name}, "
              f"得分: {score:.0f}, "
              f"完成次数: {quality.get('total_reps', 0)}")

        self._current_state_machine = None
        return result

    # ==================== 模拟数据生成 ====================

    def _simulate_joint_angles(
        self, action_config: dict, frame: int, dt: float
    ) -> Dict[str, float]:
        """
        模拟关节角度数据

        生成一个周期性的举手动作：
        每次持续约 rise + hold + fall ≈ 8秒 = 240帧
        """
        joints = action_config.get('joints', [])
        if action_config.get('sequence'):
            mode = 'sequence'
        elif action_config.get('parameters') and not joints:
            mode = 'gait'
        elif joints:
            mode = joints[0].get('name', 'shoulder_flexion')
        else:
            mode = 'shoulder_flexion'

        cycle = 240
        phase = frame % cycle
        cycle_f = float(cycle)
        rise_end = int(cycle_f * 0.35)
        hold_end = int(cycle_f * 0.65)
        fall_end = int(cycle_f * 0.90)

        if phase < rise_end:
            progress = phase / rise_end
            angle = 10 + (90 - 10) * progress
        elif phase < hold_end:
            angle = 90 + np.random.normal(0, 2)
        elif phase < fall_end:
            progress = (phase - hold_end) / (fall_end - hold_end)
            angle = 90 - (90 - 10) * progress
        else:
            angle = 10 + np.random.normal(0, 1)

        if mode == 'foot_height':
            angle = max(0, 18 + np.random.normal(0, 2)) if phase < hold_end else 2
        elif mode == 'trunk_rotation':
            angle = max(0, 75 + np.random.normal(0, 5)) if phase < hold_end else 5
        elif mode == 'step_distance':
            angle = 35 + 25 * np.sin(frame * 0.05) + np.random.normal(0, 3)
        elif mode == 'sequence':
            beat = (frame // 60) % 4
            seq_vals = [85, 88, 165, 110]
            angle = seq_vals[beat] + np.random.normal(0, 3)
        elif joints:
            target = joints[0].get('target_angle', joints[0].get('target_value', 90))
            if phase < rise_end:
                angle = 10 + (target - 10) * (phase / rise_end)
            elif phase < hold_end:
                angle = target + np.random.normal(0, 2)
            else:
                angle = 10 + np.random.normal(0, 1)

        angle = max(5, min(180, angle))
        primary_joint = mode if mode not in ('sequence', 'gait') else (
            'step_distance' if mode == 'gait' else 'shoulder_flexion'
        )
        if mode == 'sequence':
            primary_joint = ['shoulder_flexion', 'shoulder_abduction',
                             'shoulder_combined', 'shoulder_flexion_rotation'][
                (frame // 60) % 4
            ]

        angles = {primary_joint: angle, 'shoulder_flexion': angle}
        if mode == 'foot_height':
            angles['foot_height'] = angle
        elif mode == 'trunk_rotation':
            angles['trunk_rotation'] = angle
        elif mode == 'step_distance' or mode == 'gait':
            angles['step_distance'] = angle
        elif mode == 'sequence':
            for k in ('shoulder_flexion', 'shoulder_abduction',
                      'shoulder_combined', 'shoulder_flexion_rotation'):
                angles[k] = angle if k == primary_joint else angle * 0.6

        return angles

    def _simulate_imu_features(
        self, frame: int, dt: float
    ) -> Dict[str, float]:
        """模拟IMU特征"""
        return {
            'jerk': abs(np.random.normal(15, 8)),
            'tremor_ratio': abs(np.random.normal(0.05, 0.03)),
            'angular_velocity': abs(np.random.normal(20, 10)),
        }

    def _extract_imu_features(self) -> Dict[str, float]:
        """从真实IMU数据中提取特征"""
        data_items = self.imu_interface.get_all_pending_data()
        if not data_items:
            return {'jerk': 0, 'tremor_ratio': 0, 'angular_velocity': 0}

        # 取最近的数据计算
        gyros = [d['gyro'] for d in data_items[-10:]]
        if len(gyros) < 2:
            return {'jerk': 0, 'tremor_ratio': 0, 'angular_velocity': 0}

        gyros = np.array(gyros)
        angular_vel = np.mean(np.linalg.norm(gyros, axis=1))

        # 急动度
        diffs = np.diff(gyros, axis=0)
        jerk = np.mean(np.linalg.norm(diffs, axis=1)) * 100

        return {
            'jerk': float(jerk),
            'tremor_ratio': 0.05,
            'angular_velocity': float(angular_vel),
        }

    # ==================== 评分计算 ====================

    def _calculate_action_score(
        self, quality: dict, correction_summary: dict
    ) -> float:
        """
        计算单个动作的评分

        评分维度：
        - 完成度（是否达到目标次数和角度）: 40%
        - 纠正次数（越少越好）: 30%
        - 角度达标率: 30%
        """
        total_reps = quality.get('total_reps', 0)
        reach_rate = quality.get('reach_rate', 0)
        total_corrections = correction_summary.get('total_corrections', 0)

        # 完成度得分
        if total_reps >= 10:
            completion_score = 100
        elif total_reps >= 7:
            completion_score = 80
        elif total_reps >= 5:
            completion_score = 60
        elif total_reps >= 3:
            completion_score = 40
        else:
            completion_score = 20

        # 纠正扣分
        correction_penalty = min(40, total_corrections * 5)
        correction_score = max(0, 100 - correction_penalty)

        # 角度达标率
        angle_score = reach_rate * 100

        # 加权计算
        final_score = (
            completion_score * 0.4 +
            correction_score * 0.3 +
            angle_score * 0.3
        )

        return round(max(0, min(100, final_score)), 1)

    @staticmethod
    def _pack_qt_action_status(
        action_config: dict,
        status: dict,
        joint_angles: dict,
    ) -> dict:
        """从状态机 status 组装 Qt action_status，与 main [训练] 日志同源。"""
        joints_cfg = action_config.get('joints', [])
        if action_config.get('sequence'):
            beats = action_config.get('sequence', [])
            primary_name = beats[0].get('joint', 'sequence') if beats else 'sequence'
        elif action_config.get('parameters') and not joints_cfg:
            primary_name = 'step_distance'
        elif joints_cfg:
            primary_name = joints_cfg[0].get('name', '')
        else:
            primary_name = ''
        current_angles = status.get('current_angles') or {}
        current_angle = current_angles.get(primary_name)
        if current_angle is None and primary_name == 'leg_raise_angle':
            current_angle = joint_angles.get(
                'leg_raise_active',
                joint_angles.get('leg_raise_angle', 0.0),
            )
        if current_angle is None and primary_name:
            current_angle = joint_angles.get(primary_name, 0.0)
        if current_angle is None:
            current_angle = 0.0

        metric_unit = '°'
        if primary_name in ('foot_height', 'step_distance'):
            metric_unit = 'cm'
        elif primary_name == 'leg_raise_angle':
            metric_unit = '°'

        return {
            'action_id': status.get('action_id', ''),
            'action_name': action_config.get('name', ''),
            'state': status.get('state', ''),
            'rep_count': status.get('rep_count', 0),
            'target_reps': status.get('target_reps_min', 0),
            'current_angle': round(float(current_angle), 1),
            'peak_angle': float(status.get('peak_angle', 0)),
            'progress_percent': float(status.get('progress_pct', 0)),
            'metric_name': primary_name,
            'metric_unit': metric_unit,
        }

    # ==================== 状态机回调 ====================

    def _on_state_change(self, old_state, new_state, action_name):
        """状态变化回调（仅第一次重复示范节奏，后续不再重复）。"""
        sm = self._current_state_machine
        if sm is None or sm.rep_count > 0:
            return
        if new_state == ActionState.HOLDING:
            self.tts.speak_encouragement("好，保持住！")
        elif new_state == ActionState.FALLING:
            self.tts.speak_encouragement("慢慢放下来。")

    def _on_rep_complete(
        self, count, rep_data, action_name, state_machine
    ):
        """单次完成回调"""
        target_reps = state_machine.target_reps_min
        peak_angle = rep_data.get('peak_angle', 0.0)

        # 每完成 3 次鼓励一次（末次不播，避免与完成语叠在一起）
        if count % 3 == 0 and count < target_reps - 1:
            prompt = self.prompt_builder.build_encouragement(
                action_name=action_name,
                rep_count=count,
                target_reps=target_reps,
                peak_angle=peak_angle,
                target_angle=state_machine.target_angle
            )
            if prompt.get('use_llm'):
                text = self.llm.generate(
                    prompt['system'], prompt['user']
                )
            else:
                text = prompt.get('direct_output', '继续加油！')

            self.tts.speak_encouragement(text)

        print(f"  第{count}次完成，峰值角度: {peak_angle:.0f}°")

    def _on_all_complete(self, total_reps, records, action_name):
        """全部完成回调"""
        self.tts.speak(f"{action_name}完成了，做得非常好！")
        print(f"  {action_name} 全部完成: {total_reps}次")

    def _on_timing_warning(self, warning_type, message):
        """时间节奏警告回调"""
        self.tts.speak_correction(message)
