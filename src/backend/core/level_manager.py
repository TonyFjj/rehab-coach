"""
等级管理器
管理L1-L4各等级的动作方案加载、切换和训练进度
"""

import os
import yaml
from typing import Dict, List, Optional


class LevelManager:
    """
    等级管理器

    职责：
    1. 加载各等级的动作配置文件
    2. 根据当前等级返回对应的动作列表
    3. 管理训练进度（哪些动作已完成）
    4. 提供等级切换时的首次训练降难度策略
    """

    LEVELS = ['L1', 'L2', 'L3', 'L4']

    LEVEL_INFO = {
        'L1': {
            'name': '卧床主动级',
            'description': '卧床位主动关节活动',
            'score_range': (0, 30),
            'sensor_strategy': 'IMU主导，视觉辅助',
        },
        'L2': {
            'name': '坐姿辅助级',
            'description': '坐姿主动运动+辅助抵抗',
            'score_range': (31, 60),
            'sensor_strategy': 'IMU+视觉并重',
        },
        'L3': {
            'name': '站立主动级',
            'description': '站立全幅运动+平衡训练',
            'score_range': (61, 80),
            'sensor_strategy': '视觉主导，IMU辅助',
        },
        'L4': {
            'name': '全幅主动级',
            'description': '复合功能训练+协调性训练',
            'score_range': (81, 100),
            'sensor_strategy': '视觉主导，IMU微调',
        },
    }

    def __init__(self, config_dir: str):
        """
        Args:
            config_dir: 动作配置文件目录路径
                        例: "config/actions/"
        """
        self.config_dir = config_dir
        self.actions_cache: Dict[str, dict] = {}
        self.training_progress: Dict[str, Dict[str, dict]] = {}

        # 预加载所有等级配置
        self._load_all_configs()

    def _load_all_configs(self):
        """加载所有等级的动作配置"""
        for level in self.LEVELS:
            filename = f"{level}_actions.yaml"
            filepath = os.path.join(self.config_dir, filename)

            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.actions_cache[level] = config
            else:
                print(f"[WARNING] 配置文件不存在: {filepath}")
                self.actions_cache[level] = {
                    'level': level,
                    'actions': []
                }

    def get_level_info(self, level: str) -> dict:
        """获取等级基本信息"""
        return self.LEVEL_INFO.get(level, {})

    def get_actions(self, level: str) -> List[dict]:
        """获取指定等级的所有动作配置"""
        config = self.actions_cache.get(level, {})
        return config.get('actions', [])

    @staticmethod
    def infer_body_region(action: dict) -> str:
        from core.training_blocks import infer_body_region
        return infer_body_region(action)

    def get_actions_by_region(
        self,
        level: str,
        body_region: str,
    ) -> List[dict]:
        """获取指定分块的动作（上肢/下肢/整合课）。"""
        from core.training_blocks import filter_actions_by_region
        return filter_actions_by_region(self.get_actions(level), body_region)

    def get_action_by_id(
        self, level: str, action_id: str
    ) -> Optional[dict]:
        """根据ID获取单个动作配置"""
        actions = self.get_actions(level)
        for action in actions:
            if action.get('id') == action_id:
                return action
        return None

    def get_action_count(self, level: str) -> int:
        """获取等级的动作数量"""
        return len(self.get_actions(level))

    def get_training_sequence(
        self,
        level: str,
        is_first_session: bool = False,
        body_region: str = None,
    ) -> List[dict]:
        """
        获取训练序列（动作列表，按推荐顺序排列）

        Args:
            level: 当前等级
            is_first_session: 是否为升级后的首次训练
            body_region: upper | lower | integration，None 表示全部

        Returns:
            动作配置列表（可能经过降难度处理）
        """
        actions = self.get_actions(level)
        if body_region:
            actions = self.get_actions_by_region(level, body_region)

        if is_first_session and actions:
            # 升级后首次训练：降低难度
            # 策略：减少重复次数，放宽容差范围
            adjusted = []
            for action in actions:
                adj = self._reduce_difficulty(action)
                adjusted.append(adj)
            return adjusted

        return actions

    def _reduce_difficulty(self, action: dict) -> dict:
        """
        降低动作难度（升级后首次训练用）

        策略：
        - 重复次数减少30%
        - 角度容差放宽20%
        - 时间容差放宽50%
        """
        import copy
        adj = copy.deepcopy(action)

        # 减少重复次数
        reps = adj.get('repetitions')
        if isinstance(reps, list) and len(reps) == 2:
            adj['repetitions'] = [
                max(3, int(reps[0] * 0.7)),
                max(5, int(reps[1] * 0.7))
            ]
        elif isinstance(reps, int):
            adj['repetitions'] = max(3, int(reps * 0.7))

        # 放宽角度容差
        for joint in adj.get('joints', []):
            target = joint.get('target_angle', 90)
            min_a = joint.get('min_angle', target - 20)
            max_a = joint.get('max_angle', target + 20)
            margin = (max_a - min_a) * 0.1  # 额外放宽10%
            joint['min_angle'] = min_a - margin
            joint['max_angle'] = max_a + margin

        # 放宽时间容差
        timing = adj.get('timing', {})
        for key in ['rise_tolerance', 'hold_tolerance', 'fall_tolerance']:
            if key in timing:
                timing[key] = timing[key] * 1.5

        return adj

    def record_action_completion(
        self,
        level: str,
        action_id: str,
        score: float,
        details: dict = None
    ):
        """
        记录动作完成情况

        Args:
            level: 等级
            action_id: 动作ID
            score: 动作得分
            details: 详细数据
        """
        if level not in self.training_progress:
            self.training_progress[level] = {}

        if action_id not in self.training_progress[level]:
            self.training_progress[level][action_id] = {
                'attempts': 0,
                'best_score': 0,
                'scores': [],
            }

        record = self.training_progress[level][action_id]
        record['attempts'] += 1
        record['scores'].append(score)
        record['best_score'] = max(record['best_score'], score)
        record['last_details'] = details

    def get_completion_rate(self, level: str) -> float:
        """
        获取等级动作完成率

        Returns:
            完成率 (0.0 - 1.0)，当所有动作至少完成一次且得分>=60即为完成
        """
        actions = self.get_actions(level)
        if not actions:
            return 0.0

        progress = self.training_progress.get(level, {})
        completed = 0

        for action in actions:
            action_id = action.get('id', '')
            record = progress.get(action_id, {})
            if record.get('best_score', 0) >= 60:
                completed += 1

        return completed / len(actions)

    def suggest_next_action(self, level: str) -> Optional[dict]:
        """
        建议下一个应该练习的动作

        策略：优先推荐得分最低的动作，如果没有练过则优先
        """
        actions = self.get_actions(level)
        if not actions:
            return None

        progress = self.training_progress.get(level, {})

        # 找到未练习过的动作
        unpracticed = [
            a for a in actions
            if a.get('id', '') not in progress
        ]
        if unpracticed:
            return unpracticed[0]

        # 找到得分最低的动作
        scored = []
        for action in actions:
            action_id = action.get('id', '')
            record = progress.get(action_id, {})
            best = record.get('best_score', 0)
            scored.append((best, action))

        scored.sort(key=lambda x: x[0])
        return scored[0][1] if scored else actions[0]
