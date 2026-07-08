"""
动作纠正引擎
检测关节角度误差、代偿动作、时间节奏偏差，生成纠正建议
"""

import time
import numpy as np
from typing import Dict, List, Tuple, Optional


class CorrectionEngine:
    """
    动作纠正引擎

    职责：
    1. 检测关节角度是否偏离标准轨迹
    2. 检测代偿动作（耸肩、躯干前倾、膝关节内扣等）
    3. 检测时间节奏偏差（过快、过慢、停顿）
    4. 生成纠正指令（文本），供LLM润色或直接播报
    """

    # 同类型纠正的冷却时间（秒），避免反复播报同一条
    COOLDOWN = 10.0
    # 任意纠正之间的最短间隔（秒）
    GLOBAL_COOLDOWN = 8.0

    JOINT_NAMES_ZH = {
        'shoulder_flexion': '肩关节',
        'shoulder_abduction': '肩关节',
        'knee_flexion': '膝关节',
        'ankle_dorsiflexion': '踝关节',
        'ankle_plantarflexion': '踝关节',
        'foot_height': '抬脚高度',
        'leg_raise_angle': '抬腿角度',
        'knee_flexion_active': '膝关节',
        'trunk_rotation': '躯干旋转',
        'body_sway': '身体晃动',
    }

    # 仅在主动作阶段才检查“角度偏低”
    ANGLE_CHECK_PHASES = frozenset({'rising', 'holding', 'preparing'})

    def __init__(self, action_config: dict):
        """
        Args:
            action_config: 单个动作的YAML配置（如L1_A1的整个字典）
        """
        self.config = action_config
        self.action_id = action_config.get('id', 'unknown')
        self.action_name = action_config.get('name', '未知动作')

        # 上次触发各类型纠正的时间戳，用于冷却控制
        self.last_correction_time: Dict[str, float] = {}
        self._last_any_correction_time = 0.0

        # 历史纠正记录（用于训练报告）
        self.correction_history: List[dict] = []

        # 帧计数器
        self.frame_count = 0

    def evaluate(
        self,
        joint_angles: Dict[str, float],
        imu_features: Dict[str, float] = None,
        vision_features: Dict[str, float] = None,
        timing_info: Dict[str, float] = None
    ) -> Tuple[List[dict], List[dict]]:
        """
        评估当前帧的动作质量，输出误差和纠正指令

        Args:
            joint_angles: 各关节当前角度
                例: {"shoulder_flexion": 85.2, "shoulder_abduction": 42.0}
            imu_features: IMU提取的特征
                例: {"jerk": 25.3, "tremor_ratio": 0.08, "angular_velocity": 15.0}
            vision_features: 视觉提取的特征
                例: {"shoulder_hike": 3.5, "trunk_lean": 12.0, "knee_valgus": True}
            timing_info: 当前时间节奏信息
                例: {"rise_time": 1.5, "hold_time": 2.0, "fall_time": 0.8,
                     "current_phase": "rising"}

        Returns:
            errors: 检测到的误差列表
            corrections: 需要播报的纠正指令列表
        """
        self.frame_count += 1
        if imu_features is None:
            imu_features = {}
        if vision_features is None:
            vision_features = {}
        if timing_info is None:
            timing_info = {}

        errors = []
        corrections = []

        # ---- 1. 关节角度误差检测 ----
        angle_errors, angle_corrections = self._check_joint_angles(
            joint_angles, timing_info
        )
        errors.extend(angle_errors)
        corrections.extend(angle_corrections)

        # ---- 2. 代偿动作检测 ----
        comp_corrections = self._check_compensations(vision_features)
        corrections.extend(comp_corrections)

        # ---- 3. 时间节奏检测 ----
        timing_corrections = self._check_timing(timing_info)
        corrections.extend(timing_corrections)

        # ---- 4. IMU特征异常检测 ----
        imu_corrections = self._check_imu_features(imu_features)
        corrections.extend(imu_corrections)

        # ---- 5. 配置文件中的自定义纠正条件 ----
        custom_corrections = self._check_custom_conditions(
            joint_angles, imu_features, vision_features
        )
        corrections.extend(custom_corrections)

        corrections = self._pick_top_correction(corrections)

        # 记录历史
        for corr in corrections:
            corr['frame'] = self.frame_count
            corr['action_id'] = self.action_id
            self.correction_history.append(corr)

        return errors, corrections

    # ==================== 1. 关节角度检测 ====================

    def _check_joint_angles(
        self,
        joint_angles: Dict[str, float],
        timing_info: Dict[str, float] = None,
    ) -> Tuple[List[dict], List[dict]]:
        """检查各关节角度是否在标准范围内"""
        errors = []
        corrections = []
        timing_info = timing_info or {}
        current_phase = timing_info.get('current_phase', '')

        joints_config = self.config.get('joints', [])

        for joint_cfg in joints_config:
            name = joint_cfg['name']
            actual = joint_angles.get(name)

            if actual is None:
                continue

            target = joint_cfg.get(
                'target_angle', joint_cfg.get('target_value', 90.0)
            )
            min_angle = joint_cfg.get(
                'min_angle',
                joint_cfg.get('min_value', target - 20 if target else 70)
            )
            max_angle = joint_cfg.get(
                'max_angle',
                joint_cfg.get('max_value', target + 20 if target else 110)
            )
            alert_min = joint_cfg.get('alert_min', min_angle - 10)
            alert_max = joint_cfg.get('alert_max', max_angle + 10)
            name_zh = self.JOINT_NAMES_ZH.get(name, '关节')
            is_height = 'target_value' in joint_cfg or name == 'foot_height'

            # 计算误差
            error = actual - target
            error_info = {
                'joint': name,
                'actual': round(actual, 1),
                'target': round(target, 1),
                'min': round(min_angle, 1),
                'max': round(max_angle, 1),
                'error': round(error, 1),
                'severity': 'normal',
            }

            # idle/下降/rest 阶段角度低是正常的，不播报
            if current_phase not in self.ANGLE_CHECK_PHASES:
                if actual < min_angle:
                    continue

            # 判定严重程度
            if actual < alert_min:
                error_info['severity'] = 'critical_low'
                errors.append(error_info)

                msg = self._lookup_prompt('angle_low') or (
                    f"{name_zh}再{'抬高' if is_height else '往上举'}一点，您可以的！"
                )
                corr = self._try_trigger(
                    f"angle_low_{name}",
                    msg,
                    severity='critical'
                )
                if corr:
                    corrections.append(corr)

            elif actual < min_angle:
                error_info['severity'] = 'warning_low'
                errors.append(error_info)

                msg = self._lookup_prompt('angle_low') or (
                    f"{name_zh}还可以再{'高一点' if is_height else '高一点哦'}"
                )
                corr = self._try_trigger(
                    f"angle_low_{name}",
                    msg,
                    severity='warning'
                )
                if corr:
                    corrections.append(corr)

            elif actual > alert_max:
                error_info['severity'] = 'critical_high'
                errors.append(error_info)

                corr = self._try_trigger(
                    f"angle_high_{name}",
                    f"{name_zh}角度偏大了，动作幅度小一点，以舒适为准",
                    severity='critical'
                )
                if corr:
                    corrections.append(corr)

            elif actual > max_angle:
                error_info['severity'] = 'warning_high'
                errors.append(error_info)

                corr = self._try_trigger(
                    f"angle_high_{name}",
                    f"{name_zh}稍微收一点，别超过舒适范围",
                    severity='warning'
                )
                if corr:
                    corrections.append(corr)

            else:
                error_info['severity'] = 'normal'

        return errors, corrections

    def _lookup_prompt(self, corr_type: str) -> Optional[str]:
        """从动作 YAML 的 corrections 段查找预设中文指导语。"""
        for corr_cfg in self.config.get('corrections', []):
            if corr_cfg.get('type') == corr_type:
                return corr_cfg.get('prompt') or None
        return None

    # ==================== 2. 代偿动作检测 ====================

    def _check_compensations(
        self, vision_features: Dict[str, float]
    ) -> List[dict]:
        """检查代偿动作"""
        corrections = []

        comp_checks = self.config.get('compensation_checks', [])

        for check in comp_checks:
            comp_type = check.get('type', '')
            threshold = check.get('threshold', 0)
            prompt = check.get(
                'prompt',
                f'检测到代偿动作: {comp_type}'
            )

            # 获取视觉特征值
            actual = vision_features.get(comp_type, 0)

            # 布尔型特征
            if isinstance(actual, bool):
                if actual:
                    corr = self._try_trigger(
                        f"comp_{comp_type}",
                        prompt,
                        severity='warning'
                    )
                    if corr:
                        corrections.append(corr)
            # 数值型特征
            elif isinstance(actual, (int, float)):
                if actual > threshold:
                    corr = self._try_trigger(
                        f"comp_{comp_type}",
                        prompt,
                        severity='warning'
                    )
                    if corr:
                        corrections.append(corr)

        return corrections

    # ==================== 3. 时间节奏检测 ====================

    def _check_timing(
        self, timing_info: Dict[str, float]
    ) -> List[dict]:
        """检查动作时间节奏"""
        corrections = []
        timing_config = self.config.get('timing', {})
        current_phase = timing_info.get('current_phase', '')

        # 上升阶段速度检查
        if current_phase == 'rising':
            rise_time = timing_info.get('rise_time', 0)
            rise_range = timing_config.get('rise_time', [2, 5])
            rise_tol = timing_config.get('rise_tolerance', 1)

            if isinstance(rise_range, list) and len(rise_range) == 2:
                if rise_time > 0 and rise_time < rise_range[0] - rise_tol:
                    corr = self._try_trigger(
                        "speed_fast_rise",
                        f"上升速度过快 ({rise_time:.1f}秒)，建议 {rise_range[0]}-{rise_range[1]} 秒完成",
                        severity='warning'
                    )
                    if corr:
                        corrections.append(corr)

        # 下降阶段速度检查
        if current_phase == 'falling':
            fall_time = timing_info.get('fall_time', 0)
            fall_range = timing_config.get('fall_time', [2, 5])
            fall_tol = timing_config.get('fall_tolerance', 1)

            if isinstance(fall_range, list) and len(fall_range) == 2:
                if fall_time > 0 and fall_time < fall_range[0] - fall_tol:
                    corr = self._try_trigger(
                        "speed_fast_fall",
                        f"下降速度过快 ({fall_time:.1f}秒)，请慢慢放下，控制住速度",
                        severity='warning'
                    )
                    if corr:
                        corrections.append(corr)

        # 保持阶段时间检查
        if current_phase == 'holding':
            hold_time = timing_info.get('hold_time', 0)
            hold_range = timing_config.get('hold_time', [2, 3])
            hold_tol = timing_config.get('hold_tolerance', 1)

            if isinstance(hold_range, list) and len(hold_range) == 2:
                if hold_time > hold_range[1] + hold_tol:
                    corr = self._try_trigger(
                        "hold_too_long",
                        "保持时间够了，可以慢慢放下了",
                        severity='info'
                    )
                    if corr:
                        corrections.append(corr)

        return corrections

    # ==================== 4. IMU特征异常检测 ====================

    def _check_imu_features(
        self, imu_features: Dict[str, float]
    ) -> List[dict]:
        """检查IMU提取的特征异常"""
        corrections = []

        # Jerk异常（动作不平滑）
        jerk = imu_features.get('jerk', 0)
        if jerk > 40:
            corr = self._try_trigger(
                "jerk_high",
                "动作不太平稳，请尽量匀速、流畅地完成",
                severity='warning'
            )
            if corr:
                corrections.append(corr)
        elif jerk > 30:
            corr = self._try_trigger(
                "jerk_moderate",
                "动作再平稳一些，不要一下一下的",
                severity='info'
            )
            if corr:
                corrections.append(corr)

        # 震颤检测
        tremor = imu_features.get('tremor_ratio', 0)
        if tremor > 0.3:
            corr = self._try_trigger(
                "tremor_high",
                "手部抖动比较明显，如果感到吃力可以适当减小动作幅度",
                severity='warning'
            )
            if corr:
                corrections.append(corr)

        # 肌肉紧张/抵抗检测
        resistance = imu_features.get('muscle_tension_detected', False)
        if resistance:
            corr = self._try_trigger(
                "resistance",
                "感觉到有些紧张，请先放松一下，深呼吸，然后再继续",
                severity='warning'
            )
            if corr:
                corrections.append(corr)

        return corrections

    # ==================== 5. 自定义纠正条件 ====================

    def _check_custom_conditions(
        self,
        joint_angles: Dict[str, float],
        imu_features: Dict[str, float],
        vision_features: Dict[str, float]
    ) -> List[dict]:
        """检查YAML配置中定义的自定义纠正条件"""
        corrections = []
        corrections_config = self.config.get('corrections', [])

        for corr_cfg in corrections_config:
            corr_type = corr_cfg.get('type', 'unknown')
            condition = corr_cfg.get('condition', '')
            prompt = corr_cfg.get('prompt', '')

            if not condition or not prompt:
                continue

            triggered = self._parse_and_evaluate_condition(
                condition, joint_angles, imu_features, vision_features
            )

            if triggered:
                corr = self._try_trigger(
                    f"custom_{corr_type}",
                    prompt,
                    severity=corr_cfg.get('severity', 'warning')
                )
                if corr:
                    corrections.append(corr)

        return corrections

    def _parse_and_evaluate_condition(
        self,
        condition: str,
        joint_angles: Dict[str, float],
        imu_features: Dict[str, float],
        vision_features: Dict[str, float]
    ) -> bool:
        """
        解析并评估条件表达式

        支持的格式:
            "variable < threshold"
            "variable > threshold"
            "variable_detected"
        """
        # 合并所有数据源
        all_data = {}
        all_data.update(joint_angles)
        all_data.update(imu_features)
        all_data.update(vision_features)

        try:
            if '<' in condition and '>' not in condition:
                parts = condition.split('<')
                key = parts[0].strip()
                threshold = float(parts[1].strip())
                value = all_data.get(key)
                if value is not None and isinstance(value, (int, float)):
                    return value < threshold

            elif '>' in condition and '<' not in condition:
                parts = condition.split('>')
                key = parts[0].strip()
                threshold = float(parts[1].strip())
                value = all_data.get(key)
                if value is not None and isinstance(value, (int, float)):
                    return value > threshold

            elif 'detected' in condition:
                key = condition.replace('_detected', '').strip()
                return bool(all_data.get(key, False)) or \
                       bool(all_data.get(condition, False))

        except (ValueError, IndexError, TypeError):
            pass

        return False

    # ==================== 冷却控制 ====================

    _SEVERITY_RANK = {'critical': 3, 'warning': 2, 'info': 1}

    def _pick_top_correction(
        self, corrections: List[dict]
    ) -> List[dict]:
        """每轮评估最多返回一条最严重的纠正。"""
        if not corrections:
            return []
        best = max(
            corrections,
            key=lambda c: self._SEVERITY_RANK.get(
                c.get('severity', 'info'), 0
            ),
        )
        return [best]

    def _try_trigger(
        self,
        correction_type: str,
        message: str,
        severity: str = 'warning'
    ) -> Optional[dict]:
        """
        尝试触发一条纠正指令，受冷却时间控制

        Args:
            correction_type: 纠正类型标识符
            message: 纠正提示语
            severity: 严重程度 (info/warning/critical)

        Returns:
            纠正指令字典，如果在冷却中则返回None
        """
        now = time.time()

        global_gap = (
            self.GLOBAL_COOLDOWN / 2
            if severity == 'critical'
            else self.GLOBAL_COOLDOWN
        )
        if now - self._last_any_correction_time < global_gap:
            return None

        # 冷却检查
        if correction_type in self.last_correction_time:
            elapsed = now - self.last_correction_time[correction_type]
            # critical级别冷却时间减半
            cooldown = self.COOLDOWN if severity != 'critical' \
                else self.COOLDOWN / 2
            if elapsed < cooldown:
                return None

        # 记录触发时间
        self.last_correction_time[correction_type] = now
        self._last_any_correction_time = now

        return {
            'type': correction_type,
            'message': message,
            'severity': severity,
            'timestamp': now,
        }

    # ==================== 统计与报告 ====================

    def get_summary(self) -> dict:
        """获取本次训练的纠正统计摘要"""
        if not self.correction_history:
            return {
                'action_id': self.action_id,
                'action_name': self.action_name,
                'total_corrections': 0,
                'by_type': {},
                'by_severity': {},
                'most_frequent': None,
            }

        # 按类型统计
        by_type = {}
        for corr in self.correction_history:
            t = corr.get('type', 'unknown')
            by_type[t] = by_type.get(t, 0) + 1

        # 按严重程度统计
        by_severity = {}
        for corr in self.correction_history:
            s = corr.get('severity', 'unknown')
            by_severity[s] = by_severity.get(s, 0) + 1

        # 最频繁的纠正类型
        most_frequent = max(by_type, key=by_type.get) if by_type else None

        return {
            'action_id': self.action_id,
            'action_name': self.action_name,
            'total_corrections': len(self.correction_history),
            'by_type': by_type,
            'by_severity': by_severity,
            'most_frequent': most_frequent,
        }

    def reset(self):
        """重置引擎状态（新动作开始时调用）"""
        self.last_correction_time.clear()
        self._last_any_correction_time = 0.0
        self.correction_history.clear()
        self.frame_count = 0
