"""
通信协议定义
定义Python核心引擎与IMU同学、Qt同学之间的数据交换格式
所有数据以JSON格式通过Unix Socket / TCP Socket传输
"""

import json
import time
from enum import Enum
from typing import Dict, Any, Optional


class MessageType(Enum):
    """消息类型枚举"""

    # ============ IMU同学 → 核心引擎 ============
    IMU_DATA = "imu_data"                    # IMU原始数据帧
    IMU_CALIBRATION = "imu_calibration"      # IMU标定数据
    IMU_STATUS = "imu_status"                # IMU连接状态

    # ============ 核心引擎 → Qt同学 ============
    SKELETON_3D = "skeleton_3d"              # 融合后的3D骨骼坐标
    JOINT_ANGLES = "joint_angles"            # 各关节角度
    ACTION_STATUS = "action_status"          # 动作状态机状态
    SCORING = "scoring"                      # 评分数据
    CORRECTION = "correction"                # 纠正指令
    ENCOURAGEMENT = "encouragement"          # 鼓励语
    TRAINING_PROGRESS = "training_progress"  # 训练进度
    SESSION_SUMMARY = "session_summary"      # 训练总结
    LEVEL_CHANGE = "level_change"            # 等级变化
    SAFETY_ALERT = "safety_alert"            # 安全警报
    SYSTEM_STATUS = "system_status"          # 系统状态
    TRAINING_STATE = "training_state"        # 训练会话阶段（idle/running/paused/stopped）
    TRAINING_PLAN = "training_plan"          # 等级动作方案（来自 yaml）
    ASSESSMENT_PLAN = "assessment_plan"      # 初评指导方案
    ASSESSMENT_PHASE = "assessment_phase"    # 初评当前阶段（语音/计时）
    VISION_PREVIEW = "vision_preview"        # 双目调试画面（JPEG base64）


def create_message(
    msg_type: MessageType,
    payload: Dict[str, Any],
    timestamp: Optional[float] = None
) -> str:
    """
    构造消息的JSON字符串

    Args:
        msg_type: 消息类型
        payload: 消息负载（字典形式）
        timestamp: 时间戳，默认当前时间

    Returns:
        JSON字符串
    """
    if timestamp is None:
        timestamp = time.time()

    message = {
        "type": msg_type.value,
        "timestamp": timestamp,
        "payload": payload
    }

    return json.dumps(message, ensure_ascii=False)


def parse_message(message_str: str) -> Optional[Dict[str, Any]]:
    """
    解析收到的消息JSON字符串

    Args:
        message_str: JSON字符串

    Returns:
        字典格式消息，至少包含：
          - type (str)
          - timestamp (float)
          - payload (dict)
        解析失败返回None
    """
    try:
        msg = json.loads(message_str)
        if 'type' in msg and 'timestamp' in msg and 'payload' in msg:
            return msg
        else:
            return None
    except json.JSONDecodeError:
        return None


# ===================== 各类具体消息构造示例 =====================

def create_imu_data_message(
    imu_id: str,
    accel: list,
    gyro: list,
    mag: Optional[list] = None,
    timestamp: Optional[float] = None
) -> str:
    """
    构造IMU数据消息，供IMU同学发送

    accel: [ax, ay, az], 单位 m/s²
    gyro: [gx, gy, gz], 单位 °/s
    mag: [mx, my, mz], 单位 µT，选填
    """
    payload = {
        "imu_id": imu_id,
        "acceleration": accel,
        "gyroscope": gyro,
        "magnetometer": mag or [0, 0, 0],
    }
    return create_message(MessageType.IMU_DATA, payload, timestamp)


def create_skeleton_3d_message(
    joints_3d: Dict[str, list],
    confidences: Dict[str, float],
    timestamp: Optional[float] = None
) -> str:
    """
    构造3D骨骼坐标消息，供核心引擎发给Qt

    joints_3d: {joint_name: [x, y, z], ...}
    confidences: {joint_name: float, ...}
    """
    payload = {
        "joints": joints_3d,
        "confidences": confidences,
    }
    return create_message(MessageType.SKELETON_3D, payload, timestamp)


def create_action_status_message(
    action_id: str,
    state: str,
    rep_count: int,
    target_reps: int,
    current_angle: float,
    peak_angle: float,
    progress_percent: float,
    action_name: Optional[str] = None,
    metric_name: Optional[str] = None,
    metric_unit: Optional[str] = None,
    timestamp: Optional[float] = None
) -> str:
    """
    构造动作状态机状态消息
    """
    payload = {
        "action_id": action_id,
        "state": state,
        "rep_count": rep_count,
        "target_reps": target_reps,
        "current_angle": current_angle,
        "peak_angle": peak_angle,
        "progress_percent": progress_percent,
    }
    if action_name:
        payload["action_name"] = action_name
    if metric_name:
        payload["metric_name"] = metric_name
    if metric_unit:
        payload["metric_unit"] = metric_unit
    return create_message(MessageType.ACTION_STATUS, payload, timestamp)


def create_scoring_message(
    total_score: float,
    dimension_scores: dict,
    level: str,
    level_name: Optional[str] = None,
    action_names: Optional[list] = None,
    action_scores: Optional[list] = None,
    advice: Optional[str] = None,
    source: Optional[str] = None,
    imu_total_score: Optional[float] = None,
    imu_dimension_scores: Optional[dict] = None,
    vision_assessment: Optional[dict] = None,
    imu_only_reason: Optional[str] = None,
    lr_scores: Optional[dict] = None,
    lr_note: Optional[str] = None,
    timestamp: Optional[float] = None
) -> str:
    """
    构造评分消息，发给Qt用于界面显示
    """
    payload = {
        "total_score": total_score,
        "dimension_scores": dimension_scores,
        "level": level
    }
    if level_name:
        payload["level_name"] = level_name
    if action_names:
        payload["action_names"] = action_names
    if action_scores is not None:
        payload["action_scores"] = action_scores
    if advice:
        payload["advice"] = advice
    if source:
        payload["source"] = source
    if imu_total_score is not None:
        payload["imu_total_score"] = imu_total_score
    if imu_dimension_scores:
        payload["imu_dimension_scores"] = imu_dimension_scores
    if vision_assessment:
        payload["vision_assessment"] = vision_assessment
    if imu_only_reason:
        payload["imu_only_reason"] = imu_only_reason
    if lr_scores:
        payload["lr_scores"] = lr_scores
    if lr_note:
        payload["lr_note"] = lr_note
    return create_message(MessageType.SCORING, payload, timestamp)


def create_correction_message(
    corrections: list,
    timestamp: Optional[float] = None
) -> str:
    """
    构造纠正指令消息
    corrections为列表，每项示例：
      {
        'type': 'angle_low_shoulder',
        'message': '肩膀抬高一些',
        'severity': 'warning'
      }
    """
    payload = {
        "corrections": corrections
    }
    return create_message(MessageType.CORRECTION, payload, timestamp)


def create_encouragement_message(
    text: str,
    timestamp: Optional[float] = None
) -> str:
    """
    构造鼓励语消息
    """
    payload = {
        "text": text
    }
    return create_message(MessageType.ENCOURAGEMENT, payload, timestamp)


def create_training_progress_message(
    level: str,
    completed_actions: int,
    total_actions: int,
    completion_rate: float,
    current_action_id: Optional[str] = None,
    current_action_name: Optional[str] = None,
    action_scores: Optional[list] = None,
    timestamp: Optional[float] = None
) -> str:
    """
    构造训练进度消息
    """
    payload = {
        "level": level,
        "completed_actions": completed_actions,
        "total_actions": total_actions,
        "completion_rate": completion_rate
    }
    if current_action_id:
        payload["current_action_id"] = current_action_id
    if current_action_name:
        payload["current_action_name"] = current_action_name
    if action_scores is not None:
        payload["action_scores"] = action_scores
    return create_message(MessageType.TRAINING_PROGRESS, payload, timestamp)


def create_training_plan_message(
    level: str,
    level_name: str,
    description: str,
    actions: list,
    body_region: Optional[str] = None,
    block_label: Optional[str] = None,
    camera_preset: Optional[str] = None,
    setup_hint: Optional[str] = None,
    suggest_integration: bool = False,
    has_integration: bool = False,
    timestamp: Optional[float] = None,
) -> str:
    """构造训练方案消息（动作列表来自 config/actions/*.yaml）。"""
    payload = {
        "level": level,
        "level_name": level_name,
        "description": description,
        "actions": actions,
        "body_region": body_region or "upper",
        "block_label": block_label or "",
        "camera_preset": camera_preset or "upper_body",
        "setup_hint": setup_hint or "",
        "suggest_integration": bool(suggest_integration),
        "has_integration": bool(has_integration),
    }
    return create_message(MessageType.TRAINING_PLAN, payload, timestamp)


def create_assessment_plan_message(
    plan: dict,
    timestamp: Optional[float] = None,
) -> str:
    """构造初评指导方案（动作、时长、语音文案）。"""
    return create_message(MessageType.ASSESSMENT_PLAN, plan, timestamp)


def create_assessment_phase_message(
    phase: str,
    action_index: int = 0,
    total_actions: int = 0,
    action_name: Optional[str] = None,
    instruction: Optional[str] = None,
    duration: int = 0,
    sub_phase: Optional[str] = None,
    vision_completion: Optional[float] = None,
    vision_accuracy: Optional[float] = None,
    vision_current_angle: Optional[float] = None,
    vision_max_angle: Optional[float] = None,
    vision_quality: Optional[float] = None,
    vision_status: Optional[str] = None,
    vision_warning: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    初评阶段通知（Qt 同步文字提示与倒计时）

    phase: intro | precheck | action | collecting | rest | analyzing | done
    sub_phase: prep | motion（collecting 阶段可选）
    """
    payload = {
        "phase": phase,
        "action_index": action_index,
        "total_actions": total_actions,
        "duration": duration,
    }
    if action_name:
        payload["action_name"] = action_name
    if instruction:
        payload["instruction"] = instruction
    if sub_phase:
        payload["sub_phase"] = sub_phase
    if vision_completion is not None:
        payload["vision_completion"] = vision_completion
    if vision_accuracy is not None:
        payload["vision_accuracy"] = vision_accuracy
    if vision_current_angle is not None:
        payload["vision_current_angle"] = vision_current_angle
    if vision_max_angle is not None:
        payload["vision_max_angle"] = vision_max_angle
    if vision_quality is not None:
        payload["vision_quality"] = vision_quality
    if vision_status:
        payload["vision_status"] = vision_status
    if vision_warning:
        payload["vision_warning"] = vision_warning
    return create_message(MessageType.ASSESSMENT_PHASE, payload, timestamp)


def create_session_summary_message(
    summary_text: str,
    timestamp: Optional[float] = None
) -> str:
    """
    构造训练总结消息
    """
    payload = {
        "summary_text": summary_text
    }
    return create_message(MessageType.SESSION_SUMMARY, payload, timestamp)


def create_level_change_message(
    old_level: str,
    new_level: str,
    reason: str,
    timestamp: Optional[float] = None
) -> str:
    """
    构造等级变化消息
    """
    payload = {
        "old_level": old_level,
        "new_level": new_level,
        "reason": reason
    }
    return create_message(MessageType.LEVEL_CHANGE, payload, timestamp)


def create_safety_alert_message(
    alert_text: str,
    alert_type: Optional[str] = None,
    timestamp: Optional[float] = None
) -> str:
    """
    构造安全警报消息
    """
    payload = {
        "alert_text": alert_text,
        "alert_type": alert_type or "general"
    }
    return create_message(MessageType.SAFETY_ALERT, payload, timestamp)


def create_system_status_message(
    status_text: str,
    cpu_usage: Optional[float] = None,
    memory_usage: Optional[float] = None,
    tts_volume: Optional[float] = None,
    tts_rate: Optional[int] = None,
    imu: Optional[dict] = None,
    timestamp: Optional[float] = None
) -> str:
    """
    构造系统状态消息
    """
    payload = {
        "status_text": status_text,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
    }
    if tts_volume is not None:
        payload["tts_volume"] = tts_volume
    if tts_rate is not None:
        payload["tts_rate"] = tts_rate
    if imu is not None:
        payload["imu"] = imu
    return create_message(MessageType.SYSTEM_STATUS, payload, timestamp)


def create_training_state_message(
    phase: str,
    level: Optional[str] = None,
    action_id: Optional[str] = None,
    action_ids: Optional[list] = None,
    message: Optional[str] = None,
    body_region: Optional[str] = None,
    block_label: Optional[str] = None,
    suggest_next_region: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> str:
    """
    训练会话阶段通知（Qt 用于按钮态与提示）

    phase: idle | running | paused | stopped | busy | block_complete
    """
    payload = {"phase": phase}
    if level is not None:
        payload["level"] = level
    if action_id is not None:
        payload["action_id"] = action_id
    if action_ids is not None:
        payload["action_ids"] = action_ids
    if message is not None:
        payload["message"] = message
    if body_region is not None:
        payload["body_region"] = body_region
    if block_label is not None:
        payload["block_label"] = block_label
    if suggest_next_region is not None:
        payload["suggest_next_region"] = suggest_next_region
    return create_message(MessageType.TRAINING_STATE, payload, timestamp)


def create_vision_preview_message(
    image_b64: str,
    width: int,
    height: int,
    overlay: str = "",
    vision_quality: Optional[float] = None,
    vision_status: Optional[str] = None,
    vision_warning: Optional[str] = None,
    depth_mode: Optional[str] = None,
    skeleton_3d_joints: Optional[int] = None,
    timestamp: Optional[float] = None,
) -> str:
    """构造双目调试画面（JPEG base64），供 Qt 显示。"""
    payload = {
        "format": "jpeg",
        "encoding": "base64",
        "image": image_b64,
        "width": width,
        "height": height,
        "overlay": overlay,
    }
    if vision_quality is not None:
        payload["vision_quality"] = vision_quality
    if vision_status:
        payload["vision_status"] = vision_status
    if vision_warning:
        payload["vision_warning"] = vision_warning
    if depth_mode:
        payload["depth_mode"] = depth_mode
    if skeleton_3d_joints is not None:
        payload["skeleton_3d_joints"] = int(skeleton_3d_joints)
    return create_message(MessageType.VISION_PREVIEW, payload, timestamp)

