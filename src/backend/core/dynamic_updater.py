"""
动态评分更新器
每次训练后更新患者健康评分，管理升降级逻辑
"""

import time
from typing import List, Optional, Tuple


class DynamicScoreUpdater:
    """
    动态评分更新器

    使用指数移动平均（EMA）平滑评分变化，
    并根据连续训练表现判定是否触发升级或降级。
    """

    def __init__(
        self,
        initial_score: float,
        initial_level: str = 'L1',
        ema_alpha: float = 0.7,
        upgrade_consecutive: int = 3,
        downgrade_drop: float = 10.0
    ):
        """
        Args:
            initial_score: 初评得分 (0-100)
            initial_level: 初始等级
            ema_alpha: EMA系数，越大越依赖历史，越小越敏感
            upgrade_consecutive: 连续N次达标才建议升级
            downgrade_drop: 连续下降超过N分触发降级
        """
        self.current_score = float(initial_score)
        self.current_level = initial_level

        self.ema_alpha = ema_alpha
        self.upgrade_consecutive = upgrade_consecutive
        self.downgrade_drop = downgrade_drop

        # 历史记录
        self.score_history: List[dict] = [{
            'score': initial_score,
            'level': initial_level,
            'type': 'initial_assessment',
            'timestamp': time.time(),
        }]

        # 升级计数器
        self._upgrade_counter = 0
        # 峰值评分（用于降级判断）
        self._peak_score = initial_score

    def update(
        self,
        session_score: float,
        session_details: dict = None
    ) -> dict:
        """
        训练结束后更新评分

        Args:
            session_score: 本次训练的评分 (0-100)
            session_details: 本次训练的详细数据（可选）

        Returns:
            result: 更新结果，包含新评分、等级变化建议等
        """
        old_score = self.current_score
        old_level = self.current_level

        # 1. EMA更新评分
        new_score = (
            self.ema_alpha * self.current_score +
            (1 - self.ema_alpha) * session_score
        )
        new_score = round(max(0, min(100, new_score)), 1)
        self.current_score = new_score

        # 2. 更新峰值
        if new_score > self._peak_score:
            self._peak_score = new_score

        # 3. 确定新等级
        new_level = self._map_level(new_score)

        # 4. 升级判断
        upgrade_suggestion = None
        if new_level > old_level:
            self._upgrade_counter += 1
            if self._upgrade_counter >= self.upgrade_consecutive:
                upgrade_suggestion = {
                    'from': old_level,
                    'to': new_level,
                    'reason': f'连续{self._upgrade_counter}次训练评分达到'
                              f'{new_level}级标准',
                    'confirmed': False,  # 需要患者确认
                }
        else:
            self._upgrade_counter = 0

        # 5. 降级判断
        downgrade_suggestion = None
        score_drop = self._peak_score - new_score
        if score_drop >= self.downgrade_drop:
            lower_level = self._map_level(new_score)
            if lower_level < old_level:
                downgrade_suggestion = {
                    'from': old_level,
                    'to': lower_level,
                    'reason': f'评分从峰值 {self._peak_score:.0f} 下降至 '
                              f'{new_score:.0f}，降幅 {score_drop:.0f} 分',
                    'auto_applied': True,
                }
                self.current_level = lower_level
                self._peak_score = new_score  # 重置峰值

        # 6. 记录历史
        record = {
            'score': new_score,
            'session_score': session_score,
            'level': self.current_level,
            'type': 'training_update',
            'timestamp': time.time(),
            'details': session_details,
        }
        self.score_history.append(record)

        return {
            'old_score': old_score,
            'new_score': new_score,
            'old_level': old_level,
            'new_level': self.current_level,
            'score_change': round(new_score - old_score, 1),
            'upgrade_suggestion': upgrade_suggestion,
            'downgrade_suggestion': downgrade_suggestion,
            'total_sessions': len(self.score_history) - 1,  # 不算初评
        }

    def confirm_upgrade(self, target_level: str) -> bool:
        """
        确认升级（需要患者或家属确认后调用）

        Args:
            target_level: 目标等级

        Returns:
            是否成功升级
        """
        valid_upgrades = {
            'L1': 'L2', 'L2': 'L3', 'L3': 'L4'
        }

        expected = valid_upgrades.get(self.current_level)
        if expected == target_level:
            self.current_level = target_level
            self._upgrade_counter = 0
            self.score_history.append({
                'score': self.current_score,
                'level': target_level,
                'type': 'level_upgrade',
                'timestamp': time.time(),
            })
            return True
        return False

    def get_trend(self, last_n: int = 5) -> dict:
        """
        获取最近N次训练的趋势

        Returns:
            trend: 包含趋势方向、平均分变化等
        """
        training_records = [
            r for r in self.score_history
            if r['type'] == 'training_update'
        ]

        if len(training_records) < 2:
            return {
                'direction': 'insufficient_data',
                'sessions': len(training_records),
                'avg_change': 0,
            }

        recent = training_records[-last_n:]
        scores = [r['score'] for r in recent]

        # 计算趋势
        changes = [
            scores[i] - scores[i-1]
            for i in range(1, len(scores))
        ]
        avg_change = sum(changes) / len(changes) if changes else 0

        if avg_change > 1:
            direction = 'improving'
        elif avg_change < -1:
            direction = 'declining'
        else:
            direction = 'stable'

        return {
            'direction': direction,
            'sessions': len(recent),
            'avg_change': round(avg_change, 2),
            'recent_scores': scores,
            'current_score': self.current_score,
            'current_level': self.current_level,
        }

    def get_full_history(self) -> List[dict]:
        """获取完整评分历史"""
        return self.score_history.copy()

    def _map_level(self, score: float) -> str:
        """评分映射到等级"""
        if score <= 30:
            return 'L1'
        elif score <= 60:
            return 'L2'
        elif score <= 80:
            return 'L3'
        else:
            return 'L4'
