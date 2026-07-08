"""
动作状态机
管理单个动作的执行生命周期：
IDLE → RISING → HOLDING → FALLING → COMPLETED
支持重复次数计数、组间休息、异常检测
"""

import time
from enum import Enum
from typing import Dict, List, Optional, Callable


class ActionState(Enum):
    """动作执行状态"""
    IDLE = "idle"                # 等待开始
    PREPARING = "preparing"      # 准备阶段（语音提示动作要领）
    RISING = "rising"            # 上升/伸展阶段
    HOLDING = "holding"          # 保持阶段
    FALLING = "falling"          # 下降/回收阶段
    REP_COMPLETE = "rep_complete" # 单次完成（短暂）
    REST = "rest"                # 组间休息
    COMPLETED = "completed"      # 全部完成
    PAUSED = "paused"            # 暂停（用户请求或安全触发）
    ERROR = "error"              # 异常


class ActionStateMachine:
    """
    单个动作的状态机

    根据实时关节角度和时间自动判定当前阶段，
    输出状态信息供纠正引擎和UI使用。

    典型动作生命周期：
    IDLE → PREPARING → [RISING → HOLDING → FALLING → REP_COMPLETE] × N → COMPLETED
    """

    def __init__(self, action_config: dict):
        """
        Args:
            action_config: 单个动作的YAML配置字典
        """
        self.config = action_config
        self.action_id = action_config.get('id', 'unknown')
        self.action_name = action_config.get('name', '未知动作')

        # 状态
        self.state = ActionState.IDLE
        self.previous_state = ActionState.IDLE

        # 计数
        self.rep_count = 0
        self._parse_target_reps()

        # 时间戳
        self.state_enter_time = 0.0
        self.action_start_time = 0.0

        # 角度追踪
        self.current_angles: Dict[str, float] = {}
        self.peak_angle = 0.0           # 本次重复的峰值角度
        self.baseline_angle = 10.0      # 基线角度（静止状态）
        self._angle_history: List[float] = []  # 最近N帧角度

        # 时间追踪（当前重复的各阶段耗时）
        self.phase_timings: Dict[str, float] = {
            'rise_time': 0.0,
            'hold_time': 0.0,
            'fall_time': 0.0,
        }

        # 误差和纠正记录
        self.errors: List[dict] = []
        self.rep_scores: List[dict] = []  # 每次重复的评分

        # 回调函数
        self._on_state_change: Optional[Callable] = None
        self._on_correction: Optional[Callable] = None
        self._on_rep_complete: Optional[Callable] = None
        self._on_action_complete: Optional[Callable] = None

        # 动作模式：standard / balance / sequence / gait / rotation
        self._action_mode = self._detect_action_mode()
        self._seq_beat_idx = 0
        self._seq_beat_met_since: Optional[float] = None
        self._seq_rep_start = 0.0
        self._gait_step_count = 0
        self._gait_baseline_dist = 0.0
        self._gait_last_high = False

    def _detect_action_mode(self) -> str:
        if self.config.get('sequence'):
            return 'sequence'
        if self.config.get('parameters') and not self.config.get('joints'):
            return 'gait'
        joints = self.config.get('joints', [])
        if joints:
            name = joints[0].get('name', '')
            if name == 'foot_height':
                return 'balance'
            if name == 'trunk_rotation':
                return 'rotation'
        return 'standard'

    @property
    def primary_metric_name(self) -> str:
        """训练日志 / Qt 显示用的主指标名。"""
        if self._action_mode == 'sequence':
            beats = self.config.get('sequence', [])
            if beats and 0 <= self._seq_beat_idx < len(beats):
                return beats[self._seq_beat_idx].get('joint', 'sequence')
            return 'sequence'
        if self._action_mode == 'gait':
            return 'step_distance'
        joint = self._get_primary_joint_config()
        if joint:
            return joint.get('name', 'angle')
        return 'angle'

    def _parse_target_reps(self):
        """解析目标重复次数"""
        reps = self.config.get('repetitions')
        if isinstance(reps, list) and len(reps) == 2:
            self.target_reps_min = reps[0]
            self.target_reps_max = reps[1]
        elif isinstance(reps, int):
            self.target_reps_min = reps
            self.target_reps_max = reps
        else:
            self.target_reps_min = 8
            self.target_reps_max = 12

    # ==================== 外部接口 ====================

    def set_callbacks(
        self,
        on_state_change: Callable = None,
        on_correction: Callable = None,
        on_rep_complete: Callable = None,
        on_action_complete: Callable = None
    ):
        """设置各种事件的回调函数"""
        self._on_state_change = on_state_change
        self._on_correction = on_correction
        self._on_rep_complete = on_rep_complete
        self._on_action_complete = on_action_complete

    def start(self, skip_preparing: bool = False):
        """开始执行动作"""
        self.rep_count = 0
        self.peak_angle = 0.0
        self.errors = []
        self.rep_scores = []
        self._angle_history = []
        self._seq_beat_idx = 0
        self._seq_beat_met_since = None
        self._seq_rep_start = 0.0
        self._gait_step_count = 0
        self._gait_baseline_dist = 0.0
        self._gait_last_high = False
        self.action_start_time = time.time()
        if skip_preparing:
            if self._action_mode == 'sequence':
                self._seq_beat_idx = 0
                self._seq_beat_met_since = None
                self._seq_rep_start = time.time()
                self._change_state(ActionState.RISING)
            elif self._action_mode == 'gait':
                self._gait_step_count = 0
                self._gait_last_high = False
                self._change_state(ActionState.RISING)
            else:
                self._change_state(ActionState.IDLE)
        else:
            self._change_state(ActionState.PREPARING)

    def pause(self):
        """暂停动作"""
        if self.state not in (ActionState.COMPLETED, ActionState.ERROR):
            self.previous_state = self.state
            self._change_state(ActionState.PAUSED)

    def resume(self):
        """恢复动作"""
        if self.state == ActionState.PAUSED:
            self._change_state(self.previous_state)

    def stop(self):
        """强制停止"""
        self._change_state(ActionState.COMPLETED)

    def is_active(self) -> bool:
        """训练循环是否应继续（未完成且未出错）。"""
        return self.state not in (ActionState.COMPLETED, ActionState.ERROR)

    @property
    def target_angle(self) -> float:
        """主关节目标角度（供训练会话 / Prompt 使用）。"""
        joint = self._get_primary_joint_config()
        if joint:
            if 'target_angle' in joint:
                return float(joint['target_angle'])
            if 'target_value' in joint:
                return float(joint['target_value'])
        if self._action_mode == 'sequence':
            beats = self.config.get('sequence', [])
            if beats:
                return float(beats[0].get('target_angle', 90))
        if self._action_mode == 'gait':
            params = self.config.get('parameters', {})
            dist = params.get('step_distance_cm', [30, 50])
            if isinstance(dist, list) and dist:
                return float(dist[0])
        return 90.0

    def get_completion_quality(self) -> dict:
        """
        动作结束后的完成质量统计。

        Returns:
            total_reps, target_reps, avg_peak_angle, reach_rate, avg_rep_score, rep_scores
        """
        total_reps = self.rep_count
        peaks = [float(r.get('peak_angle', 0)) for r in self.rep_scores]

        avg_peak_angle = (
            sum(peaks) / len(peaks) if peaks else 0.0
        )

        joint = self._get_primary_joint_config()
        if joint:
            if 'target_angle' in joint:
                target = float(joint['target_angle'])
                min_reach = float(joint.get('min_angle', target * 0.8))
            elif 'target_value' in joint:
                target = float(joint['target_value'])
                min_reach = float(joint.get('min_value', target * 0.5))
            else:
                target = 90.0
                min_reach = 70.0
        elif self._action_mode == 'gait':
            target = self.target_angle
            min_reach = target * 0.6
        else:
            target = 90.0
            min_reach = 70.0

        if total_reps > 0 and peaks:
            reached = sum(1 for p in peaks if p >= min_reach)
            reach_rate = reached / total_reps
        else:
            reach_rate = 0.0

        if self.rep_scores:
            avg_rep_score = sum(
                r.get('score', 0) for r in self.rep_scores
            ) / len(self.rep_scores)
        else:
            avg_rep_score = 0.0

        return {
            'total_reps': total_reps,
            'target_reps': self.target_reps_min,
            'avg_peak_angle': round(avg_peak_angle, 1),
            'reach_rate': round(reach_rate, 3),
            'avg_rep_score': round(avg_rep_score, 1),
            'rep_scores': list(self.rep_scores),
        }

    def update(
        self,
        joint_angles: Dict[str, float],
        imu_features: Dict[str, float] = None,
        dt: float = 0.033
    ) -> dict:
        """
        每帧更新状态机（由主循环调用）

        Args:
            joint_angles: 当前各关节角度
                例: {"shoulder_flexion": 85.2}
            imu_features: IMU特征（可选）
                例: {"jerk": 15.3, "tremor_ratio": 0.08}
            dt: 帧间隔（秒），默认30fps

        Returns:
            status: 当前状态信息字典
        """
        if self.state in (ActionState.COMPLETED, ActionState.ERROR,
                          ActionState.PAUSED):
            return self._get_status()

        self.current_angles = joint_angles
        now = time.time()
        elapsed_in_state = now - self.state_enter_time

        # 获取主关节当前角度
        primary_angle = self._get_primary_angle(joint_angles)

        # 更新角度历史
        self._angle_history.append(primary_angle)
        if len(self._angle_history) > 60:  # 保留最近2秒(30fps)
            self._angle_history = self._angle_history[-60:]

        # 更新峰值
        if primary_angle > self.peak_angle:
            self.peak_angle = primary_angle

        # 根据当前状态执行对应逻辑
        if self._action_mode == 'sequence':
            self._update_sequence(joint_angles, elapsed_in_state, imu_features)
        elif self._action_mode == 'gait':
            self._update_gait(joint_angles, elapsed_in_state, imu_features)
        elif self._action_mode == 'balance':
            self._update_balance(primary_angle, elapsed_in_state, imu_features)
        else:
            handler = {
                ActionState.PREPARING: self._handle_preparing,
                ActionState.IDLE: self._handle_idle,
                ActionState.RISING: self._handle_rising,
                ActionState.HOLDING: self._handle_holding,
                ActionState.FALLING: self._handle_falling,
                ActionState.REP_COMPLETE: self._handle_rep_complete,
                ActionState.REST: self._handle_rest,
            }.get(self.state)

            if handler:
                handler(primary_angle, elapsed_in_state, imu_features)

        return self._get_status()

    # ==================== 状态处理函数 ====================

    def _handle_preparing(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        准备阶段：等待语音播报完动作要领
        自动持续3秒后进入IDLE
        """
        if elapsed >= 3.0:
            self._change_state(ActionState.IDLE)

    def _handle_idle(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        空闲状态：等待用户开始动作
        当关节角度开始增加超过基线+阈值时，认为动作开始
        """
        joint = self._get_primary_joint_config()
        min_angle = 70.0
        metric_name = ''
        if joint:
            metric_name = joint.get('name', '')
            if 'min_angle' in joint:
                min_angle = float(joint['min_angle'])
            elif 'min_value' in joint:
                min_angle = float(joint['min_value'])
        if metric_name == 'leg_raise_angle':
            start_threshold = max(min_angle * 0.55, 6.0)
        else:
            start_threshold = max(
                self.baseline_angle + 25,
                min_angle * 0.45,
            )

        if angle > start_threshold:
            self.peak_angle = angle  # 重置峰值
            self._change_state(ActionState.RISING)

    def _handle_rising(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        上升阶段：关节角度正在增加
        当角度达到目标最小值，或角度开始下降，进入HOLDING
        """
        primary_joint = self._get_primary_joint_config()
        if not primary_joint:
            return

        min_angle = primary_joint.get(
            'min_angle',
            primary_joint.get(
                'min_value',
                primary_joint.get('target_angle', 90) * 0.7,
            ),
        )

        # 检测角度是否到达目标范围
        if angle >= min_angle:
            self.phase_timings['rise_time'] = elapsed
            self._change_state(ActionState.HOLDING)
            return

        # 检测角度是否开始下降（可能患者能力不足，到不了目标）
        if len(self._angle_history) >= 10:
            recent = self._angle_history[-10:]
            if all(recent[i] >= recent[i+1] for i in range(len(recent)-1)):
                # 连续下降，认为已达到峰值，跳到HOLDING
                self.phase_timings['rise_time'] = elapsed
                self._change_state(ActionState.HOLDING)
                return

        # 上升超时检查
        timing_config = self.config.get('timing', {})
        rise_range = timing_config.get('rise_time', [2, 5])
        if isinstance(rise_range, list) and len(rise_range) == 2:
            max_rise = rise_range[1] + timing_config.get('rise_tolerance', 1)
            if elapsed > max_rise:
                self.phase_timings['rise_time'] = elapsed
                self._change_state(ActionState.HOLDING)

    def _handle_holding(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        保持阶段：关节角度应保持在目标附近
        保持足够时间后进入FALLING
        """
        timing_config = self.config.get('timing', {})
        hold_range = timing_config.get('hold_time', [2, 3])

        min_hold = hold_range[0] if isinstance(hold_range, list) else hold_range

        # 检测角度是否开始下降（用户主动放下）
        if len(self._angle_history) >= 5:
            recent = self._angle_history[-5:]
            drop = self.peak_angle - angle

            # 角度下降超过20°且持续下降，认为进入下降阶段
            if drop > 20 and all(
                recent[i] >= recent[i+1]
                for i in range(len(recent)-1)
            ):
                self.phase_timings['hold_time'] = elapsed
                self._change_state(ActionState.FALLING)
                return

        # 保持时间到
        if elapsed >= min_hold:
            # 再给1秒缓冲，如果角度开始降就切换
            if elapsed >= min_hold + 1.0:
                self.phase_timings['hold_time'] = elapsed
                self._change_state(ActionState.FALLING)

    def _handle_falling(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        下降阶段：关节角度正在回到起始位置
        当角度回到接近基线时，本次重复完成
        """
        joint = self._get_primary_joint_config()
        min_angle = 70.0
        metric_name = ''
        if joint:
            metric_name = joint.get('name', '')
            if 'min_angle' in joint:
                min_angle = float(joint['min_angle'])
            elif 'min_value' in joint:
                min_angle = float(joint['min_value'])
        if metric_name == 'leg_raise_angle':
            return_threshold = max(min_angle * 0.3, 4.0)
        else:
            return_threshold = min(
                self.baseline_angle + 15,
                min_angle * 0.35,
            )

        if angle <= return_threshold:
            self.phase_timings['fall_time'] = elapsed
            self._complete_one_rep()
            return

        # 下降超时（可能用户停顿了）
        timing_config = self.config.get('timing', {})
        fall_range = timing_config.get('fall_time', [2, 5])
        if isinstance(fall_range, list) and len(fall_range) == 2:
            max_fall = fall_range[1] + timing_config.get('fall_tolerance', 2)
            if elapsed > max_fall:
                self.phase_timings['fall_time'] = elapsed
                self._complete_one_rep()

    def _handle_rep_complete(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        单次完成：短暂停留后判断是否继续
        """
        if elapsed >= 0.5:  # 停留0.5秒
            if self.rep_count >= self.target_reps_min:
                self._change_state(ActionState.COMPLETED)
                if self._on_action_complete:
                    self._on_action_complete(
                        self.rep_count, self.rep_scores
                    )
            else:
                # 检查是否需要组间休息
                rest_time = self.config.get('rest_between_sets', 0)
                if rest_time > 0 and self.rep_count % 5 == 0:
                    self._change_state(ActionState.REST)
                elif self._action_mode == 'sequence':
                    self._seq_beat_idx = 0
                    self._seq_beat_met_since = None
                    self._seq_rep_start = time.time()
                    self._change_state(ActionState.RISING)
                elif self._action_mode == 'gait':
                    self._gait_step_count = 0
                    self._gait_last_high = False
                    self._change_state(ActionState.RISING)
                else:
                    self._change_state(ActionState.IDLE)

    def _handle_rest(
        self, angle: float, elapsed: float,
        imu_features: dict = None
    ):
        """
        组间休息
        """
        rest_time = self.config.get('rest_between_sets', 10)

        if elapsed >= rest_time:
            self._change_state(ActionState.IDLE)

    # ==================== 特殊动作模式 ====================

    def _update_balance(
        self, foot_height: float, elapsed: float,
        imu_features: dict = None
    ):
        """单脚平衡：抬脚 → 保持 → 放下。"""
        joint = self._get_primary_joint_config()
        min_val = float(joint.get('min_value', 5)) if joint else 5.0
        target_val = float(joint.get('target_value', 15)) if joint else 15.0
        timing = self.config.get('timing', {})
        hold_range = timing.get('hold_time', [10, 30])
        min_hold = hold_range[0] if isinstance(hold_range, list) else float(hold_range)

        if self.state == ActionState.PREPARING:
            if elapsed >= 3.0:
                self._change_state(ActionState.IDLE)
            return

        if self.state == ActionState.REP_COMPLETE:
            self._handle_rep_complete(foot_height, elapsed, imu_features)
            return

        if self.state == ActionState.IDLE:
            if foot_height >= min_val * 0.5:
                self.peak_angle = foot_height
                self._change_state(ActionState.RISING)
            return

        if self.state == ActionState.RISING:
            if foot_height >= min_val:
                self.phase_timings['rise_time'] = elapsed
                self._change_state(ActionState.HOLDING)
            elif elapsed > 5.0:
                self._change_state(ActionState.IDLE)
            return

        if self.state == ActionState.HOLDING:
            if foot_height < min_val * 0.4:
                self.phase_timings['hold_time'] = elapsed
                self._change_state(ActionState.FALLING)
                return
            if elapsed >= min_hold:
                self.phase_timings['hold_time'] = elapsed
                self._change_state(ActionState.FALLING)
            return

        if self.state == ActionState.FALLING:
            if foot_height < min_val * 0.3 or elapsed > 3.0:
                self.phase_timings['fall_time'] = elapsed
                self._complete_one_rep()
            return

    @staticmethod
    def _sequence_beat_met(
        joint_name: str,
        current: float,
        target: float,
        tol: float,
    ) -> bool:
        """序列节拍是否达标（肩类动作用「达到幅度」而非「贴近目标值」）。"""
        if joint_name in (
            'shoulder_flexion', 'shoulder_abduction',
            'shoulder_combined', 'shoulder_flexion_rotation',
        ):
            return current >= max(0.0, target - tol)
        return abs(current - target) <= tol or current >= target - tol

    def _update_sequence(
        self, joint_angles: Dict[str, float], elapsed: float,
        imu_features: dict = None
    ):
        """太极拳式复合动作：按节拍依次检测各关节。"""
        beats = self.config.get('sequence', [])
        if not beats:
            self._change_state(ActionState.COMPLETED)
            return

        if self.state == ActionState.IDLE:
            self._seq_beat_idx = 0
            self._seq_beat_met_since = None
            self._seq_rep_start = time.time()
            self._change_state(ActionState.RISING)
            return

        if self.state == ActionState.PREPARING:
            if elapsed >= 3.0:
                self._seq_beat_idx = 0
                self._seq_beat_met_since = None
                self._seq_rep_start = time.time()
                self._change_state(ActionState.RISING)
            return

        if self.state == ActionState.REP_COMPLETE:
            self._handle_rep_complete(0.0, elapsed, imu_features)
            return

        if self.state != ActionState.RISING:
            return

        timing = self.config.get('timing', {})
        full_range = timing.get('full_sequence_time', [15, 25])
        max_time = (
            full_range[1] + timing.get('tolerance', 5)
            if isinstance(full_range, list) and len(full_range) == 2
            else 30.0
        )

        if time.time() - self._seq_rep_start > max_time:
            if self._seq_beat_idx >= max(1, len(beats) // 2):
                self._complete_sequence_rep()
            else:
                self._seq_beat_idx = 0
                self._seq_beat_met_since = None
                self._seq_rep_start = time.time()
            return

        beat = beats[self._seq_beat_idx]
        joint_name = beat.get('joint', 'shoulder_flexion')
        target = float(beat.get('target_angle', 90))
        tol = float(beat.get('tolerance', 10))
        current = float(joint_angles.get(joint_name, 0.0))
        if current <= 0.0 and joint_name.startswith('shoulder_'):
            for side in ('left', 'right'):
                alt = joint_angles.get(f'{joint_name}_{side}')
                if alt is not None:
                    current = max(current, float(alt))
            if joint_name == 'shoulder_combined':
                current = max(
                    current,
                    float(joint_angles.get('shoulder_flexion', 0.0)),
                    float(joint_angles.get('shoulder_abduction', 0.0)),
                )

        met = self._sequence_beat_met(joint_name, current, target, tol)
        hold_sec = 0.5
        if met:
            if self._seq_beat_met_since is None:
                self._seq_beat_met_since = time.time()
            elif time.time() - self._seq_beat_met_since >= hold_sec:
                self.peak_angle = max(self.peak_angle, current)
                self._seq_beat_idx += 1
                self._seq_beat_met_since = None
                if self._seq_beat_idx >= len(beats):
                    self._complete_sequence_rep()
        elif current < max(0.0, target - tol - 20.0):
            self._seq_beat_met_since = None

    def _update_gait(
        self, joint_angles: Dict[str, float], elapsed: float,
        imu_features: dict = None
    ):
        """四方向步态：检测迈步位移，4 步计 1 次。"""
        params = self.config.get('parameters', {})
        dist_range = params.get('step_distance_cm', [30, 50])
        min_step = (
            float(dist_range[0]) - float(params.get('step_distance_tolerance', 10))
            if isinstance(dist_range, list) and dist_range
            else 20.0
        )
        step_dist = float(joint_angles.get('step_distance', 0.0))

        if self.state == ActionState.PREPARING:
            if elapsed >= 3.0:
                self._gait_step_count = 0
                self._gait_last_high = False
                self._change_state(ActionState.RISING)
            return

        if self.state == ActionState.REP_COMPLETE:
            self._handle_rep_complete(step_dist, elapsed, imu_features)
            return

        if self.state != ActionState.RISING:
            return

        if self._gait_step_count == 0 and elapsed < 0.15:
            pass  # 步距已相对中立站姿基线，无需再采 baseline

        timing = self.config.get('timing', {})
        cycle_range = timing.get('full_cycle_time', [8, 12])
        max_cycle = (
            cycle_range[1] + timing.get('tolerance', 2)
            if isinstance(cycle_range, list) and len(cycle_range) == 2
            else 15.0
        )

        delta = step_dist
        is_high = delta >= min_step

        if is_high and not self._gait_last_high:
            self._gait_step_count += 1
            self.peak_angle = max(self.peak_angle, delta)
            self._gait_last_high = True
        elif not is_high:
            self._gait_last_high = False

        if self._gait_step_count >= 4:
            self._complete_gait_rep()
            return

        if elapsed > max_cycle:
            if self._gait_step_count >= 2:
                self._complete_gait_rep(partial=True)
            else:
                self._gait_step_count = 0
                self._gait_last_high = False
                self.state_enter_time = time.time()

    def _complete_sequence_rep(self):
        """完成一套太极拳序列。"""
        rep_data = {
            'rep': self.rep_count + 1,
            'peak_angle': round(self.peak_angle, 1),
            'rise_time': round(time.time() - self._seq_rep_start, 2),
            'hold_time': 0.0,
            'fall_time': 0.0,
            'timestamp': time.time(),
        }
        beats = self.config.get('sequence', [])
        target = float(beats[0].get('target_angle', 90)) if beats else 90.0
        rep_data['score'] = round(
            min(100.0, self.peak_angle / max(target, 1.0) * 100.0), 1
        )
        self.rep_count += 1
        self.rep_scores.append(rep_data)
        if self._on_rep_complete:
            self._on_rep_complete(self.rep_count, rep_data)
        self.peak_angle = 0.0
        self._seq_beat_idx = 0
        self._seq_beat_met_since = None
        self._change_state(ActionState.REP_COMPLETE)

    def _complete_gait_rep(self, partial: bool = False):
        """完成一轮四方向步态。"""
        params = self.config.get('parameters', {})
        dist_range = params.get('step_distance_cm', [30, 50])
        target = float(dist_range[0]) if isinstance(dist_range, list) else 30.0
        steps = self._gait_step_count
        if partial and steps < 4:
            self.peak_angle = max(self.peak_angle, steps / 4.0 * target)

        rep_data = {
            'rep': self.rep_count + 1,
            'peak_angle': round(self.peak_angle, 1),
            'rise_time': 0.0,
            'hold_time': 0.0,
            'fall_time': 0.0,
            'timestamp': time.time(),
            'steps': steps,
        }
        ratio = min(steps / 4.0, 1.0)
        rep_data['score'] = round(ratio * 100.0, 1)
        self.rep_count += 1
        self.rep_scores.append(rep_data)
        if self._on_rep_complete:
            self._on_rep_complete(self.rep_count, rep_data)
        self.peak_angle = 0.0
        self._gait_step_count = 0
        self._gait_last_high = False
        self._change_state(ActionState.REP_COMPLETE)

    # ==================== 内部辅助 ====================

    def _min_angle_required(self) -> float:
        joint = self._get_primary_joint_config()
        if joint:
            if 'min_angle' in joint:
                return float(joint['min_angle'])
            if 'min_value' in joint:
                return float(joint['min_value'])
        if self._action_mode == 'gait':
            params = self.config.get('parameters', {})
            dist = params.get('step_distance_cm', [30, 50])
            if isinstance(dist, list) and dist:
                return float(dist[0]) * 0.6
        return 70.0

    def _complete_one_rep(self):
        """完成一次重复（峰值未达 min_angle 视为抖动，不计次）"""
        min_required = self._min_angle_required()
        if self.peak_angle < min_required:
            self.peak_angle = 0.0
            self.phase_timings = {
                'rise_time': 0.0, 'hold_time': 0.0, 'fall_time': 0.0
            }
            self._angle_history = []
            self._change_state(ActionState.IDLE)
            return

        self.rep_count += 1

        # 记录本次重复的数据
        rep_data = {
            'rep': self.rep_count,
            'peak_angle': round(self.peak_angle, 1),
            'rise_time': round(self.phase_timings.get('rise_time', 0), 2),
            'hold_time': round(self.phase_timings.get('hold_time', 0), 2),
            'fall_time': round(self.phase_timings.get('fall_time', 0), 2),
            'timestamp': time.time(),
        }

        # 计算本次重复得分
        rep_data['score'] = self._score_single_rep(rep_data)
        self.rep_scores.append(rep_data)

        # 回调
        if self._on_rep_complete:
            self._on_rep_complete(self.rep_count, rep_data)

        # 重置
        self.peak_angle = 0.0
        self.phase_timings = {
            'rise_time': 0.0, 'hold_time': 0.0, 'fall_time': 0.0
        }
        self._angle_history = []

        self._change_state(ActionState.REP_COMPLETE)

    def _score_single_rep(self, rep_data: dict) -> float:
        """
        评估单次重复的质量 (0-100)

        基于：峰值角度达标率 + 时间节奏得分
        """
        score = 0.0

        # 角度得分 (60%)
        primary_joint = self._get_primary_joint_config()
        if primary_joint:
            target = primary_joint.get(
                'target_angle', primary_joint.get('target_value', 90)
            )
            peak = rep_data.get('peak_angle', 0)
            angle_ratio = min(peak / target, 1.0) if target > 0 else 0
            score += angle_ratio * 60
        elif self._action_mode in ('sequence', 'gait'):
            score += min(rep_data.get('score', 0), 100) * 0.6

        # 时间节奏得分 (40%)
        timing_config = self.config.get('timing', {})

        timing_score = 40.0
        for phase in ['rise_time', 'hold_time', 'fall_time']:
            expected_range = timing_config.get(phase)
            actual = rep_data.get(phase, 0)

            if isinstance(expected_range, list) and len(expected_range) == 2:
                tol = timing_config.get(f'{phase.split("_")[0]}_tolerance', 1)
                low = expected_range[0] - tol
                high = expected_range[1] + tol

                if low <= actual <= high:
                    pass  # 在范围内，不扣分
                else:
                    deviation = min(
                        abs(actual - low),
                        abs(actual - high)
                    )
                    penalty = min(deviation * 3, 13.3)  # 每相最多扣13.3分
                    timing_score -= penalty

        score += max(0, timing_score)

        return round(min(100, max(0, score)), 1)

    def _get_primary_angle(self, joint_angles: Dict[str, float]) -> float:
        """获取主关节的当前角度/指标值。"""
        if self._action_mode == 'sequence':
            beats = self.config.get('sequence', [])
            if beats and 0 <= self._seq_beat_idx < len(beats):
                jname = beats[self._seq_beat_idx].get('joint', '')
                val = joint_angles.get(jname, 0.0)
                if float(val or 0) <= 0.0 and jname.startswith('shoulder_'):
                    for side in ('left', 'right'):
                        alt = joint_angles.get(f'{jname}_{side}')
                        if alt is not None:
                            val = max(float(val or 0), float(alt))
                    if jname == 'shoulder_combined':
                        val = max(
                            float(val or 0),
                            float(joint_angles.get('shoulder_flexion', 0.0)),
                            float(joint_angles.get('shoulder_abduction', 0.0)),
                        )
                return float(val or 0.0)
            return 0.0
        if self._action_mode == 'gait':
            return joint_angles.get('step_distance', 0.0)

        joints_config = self.config.get('joints', [])
        if joints_config:
            name = joints_config[0].get('name', '')
            if name == 'knee_flexion':
                active = joint_angles.get('knee_flexion_active')
                if active is not None:
                    return float(active)
                left = joint_angles.get('knee_flexion_left', 0.0)
                right = joint_angles.get('knee_flexion_right', 0.0)
                return max(left, right, joint_angles.get(name, 0.0))
            if name == 'leg_raise_angle':
                active = joint_angles.get('leg_raise_active')
                if active is not None:
                    return float(active)
                left = joint_angles.get('leg_raise_left', 0.0)
                right = joint_angles.get('leg_raise_right', 0.0)
                return max(left, right, joint_angles.get(name, 0.0))
            return joint_angles.get(name, 0.0)
        return 0.0

    def _get_primary_joint_config(self) -> Optional[dict]:
        """获取主关节的配置"""
        joints_config = self.config.get('joints', [])
        return joints_config[0] if joints_config else None

    def _change_state(self, new_state: ActionState):
        """切换状态"""
        old_state = self.state
        self.state = new_state
        self.state_enter_time = time.time()

        if self._on_state_change and old_state != new_state:
            self._on_state_change(old_state, new_state)

    def _get_status(self) -> dict:
        """获取当前完整状态（供Qt接口和纠正引擎使用）"""
        now = time.time()

        # 进度百分比
        progress = 0.0
        if self.target_reps_min > 0:
            progress = min(
                self.rep_count / self.target_reps_min * 100, 100
            )

        # 各阶段剩余时间提示
        remaining_info = ""
        elapsed_in_state = now - self.state_enter_time
        timing_config = self.config.get('timing', {})

        if self.state == ActionState.HOLDING:
            hold_range = timing_config.get('hold_time', [2, 3])
            if isinstance(hold_range, list):
                remaining = max(0, hold_range[0] - elapsed_in_state)
                remaining_info = f"保持 {remaining:.0f}秒"

        elif self.state == ActionState.REST:
            rest = self.config.get('rest_between_sets', 10)
            remaining = max(0, rest - elapsed_in_state)
            remaining_info = f"休息 {remaining:.0f}秒"

        return {
            'action_id': self.action_id,
            'action_name': self.action_name,
            'state': self.state.value,
            'rep_count': self.rep_count,
            'target_reps_min': self.target_reps_min,
            'target_reps_max': self.target_reps_max,
            'progress_pct': round(progress, 1),
            'peak_angle': round(self.peak_angle, 1),
            'current_angles': {
                k: round(v, 1) for k, v in self.current_angles.items()
            },
            'phase_timings': self.phase_timings.copy(),
            'elapsed_total': round(now - self.action_start_time, 1),
            'elapsed_in_state': round(elapsed_in_state, 1),
            'remaining_info': remaining_info,
            'rep_scores': self.rep_scores[-5:],  # 最近5次
            'avg_rep_score': round(
                sum(r['score'] for r in self.rep_scores) / len(self.rep_scores),
                1
            ) if self.rep_scores else 0.0,
        }
