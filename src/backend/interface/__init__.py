 
"""
接口模块
负责核心引擎与IMU同学、Qt界面同学的通信
"""

from .protocol import (
    MessageType,
    create_message,
    parse_message,
    create_imu_data_message,
    create_skeleton_3d_message,
    create_action_status_message,
    create_scoring_message,
    create_correction_message,
    create_encouragement_message,
    create_training_progress_message,
    create_session_summary_message,
    create_level_change_message,
    create_safety_alert_message,
    create_system_status_message,
)
from .imu_interface import IMUInterface
from .qt_interface import QtInterface

__all__ = [
    'MessageType',
    'create_message',
    'parse_message',
    'IMUInterface',
    'QtInterface',
]
