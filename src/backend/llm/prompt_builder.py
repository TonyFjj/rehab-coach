"""
Prompt构建器
将评分结果、动作误差、患者状态封装为结构化Prompt，供LLM生成自然语言指导
"""

from typing import Dict, List, Optional


class PromptBuilder:
    """
    Prompt构建器

    根据不同场景（初评播报、动作纠正、训练总结、鼓励语）
    构建系统Prompt和用户Prompt
    """

    # 系统人设
    SYSTEM_PROMPT = (
        "你是一位亲切温柔的康复医生，名叫\"小康\"。"
        "你正在通过智能康复系统远程指导一位老年患者进行居家康复训练。"
        "请注意以下要求：\n"
        "1. 用口语化的表达，不要使用医学术语\n"
        "2. 语气温暖、鼓励，像对待家中长辈一样\n"
        "3. 指导语简短清晰，每次不超过3句话\n"
        "4. 如果患者做得好，要及时表扬\n"
        "5. 如果需要纠正，先肯定再指出问题\n"
        "6. 称呼患者为\"您\"，并适当使用患者的名字\n"
    )

    def __init__(self, patient_name: str = ""):
        """
        Args:
            patient_name: 患者称呼，如 "王爷爷"、"李奶奶"
        """
        self.patient_name = patient_name or "您"

    def build_assessment_report(
        self,
        total_score: float,
        level: str,
        dimension_scores: Dict[str, float]
    ) -> dict:
        """
        构建初评结果播报的Prompt

        Returns:
            {"system": str, "user": str}
        """
        # 找出最好和最差的维度
        sorted_dims = sorted(
            dimension_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        best_dim = sorted_dims[0] if sorted_dims else ('', 0)
        worst_dim = sorted_dims[-1] if sorted_dims else ('', 0)

        dim_names = {
            'range_of_motion': '手臂抬举高度',
            'smoothness': '动作流畅度',
            'tremor': '手部稳定性',
            'symmetry': '左右手协调性',
            'speed': '动作速度',
            'endurance': '保持耐力',
        }

        level_names = {
            'L1': '基础卧床训练',
            'L2': '坐姿训练',
            'L3': '站立训练',
            'L4': '综合协调训练',
        }

        user_prompt = (
            f"患者{self.patient_name}刚刚完成了初始健康评估。\n"
            f"综合评分：{total_score:.0f}分（满分100分）\n"
            f"康复等级：{level}（{level_names.get(level, level)}）\n"
            f"表现最好的方面：{dim_names.get(best_dim[0], best_dim[0])}"
            f"（{best_dim[1]:.0f}分）\n"
            f"需要重点改善：{dim_names.get(worst_dim[0], worst_dim[0])}"
            f"（{worst_dim[1]:.0f}分）\n\n"
            f"请生成一段温暖的评估结果播报语，"
            f"告诉患者评分情况和接下来的训练安排。"
        )

        return {
            'system': self.SYSTEM_PROMPT,
            'user': user_prompt,
        }

    def build_correction(
        self,
        action_name: str,
        errors: List[dict],
        corrections: List[dict],
        rep_count: int = 0,
        target_reps: int = 10
    ) -> dict:
        """
        构建动作纠正的Prompt

        Args:
            action_name: 当前动作名称
            errors: 角度误差列表
            corrections: 纠正指令列表
            rep_count: 当前完成次数
            target_reps: 目标次数
        """
        # 如果已有预设的纠正语，直接使用，不需要LLM
        if corrections and corrections[0].get('message'):
            return {
                'system': '',
                'user': '',
                'direct_output': corrections[0]['message'],
                'use_llm': False,
            }

        # 需要LLM生成纠正语的情况
        error_desc = ""
        for err in errors[:3]:  # 最多取3个误差
            error_desc += (
                f"- {err.get('joint', '关节')}: "
                f"当前 {err.get('actual', 0):.0f}°, "
                f"目标 {err.get('target', 0):.0f}°, "
                f"偏差 {err.get('error', 0):+.0f}°\n"
            )

        user_prompt = (
            f"患者{self.patient_name}正在做{action_name}，"
            f"第{rep_count}/{target_reps}次。\n"
            f"检测到以下问题：\n{error_desc}\n"
            f"请生成一句简短的纠正指导语（不超过20个字）。"
        )

        return {
            'system': self.SYSTEM_PROMPT,
            'user': user_prompt,
            'use_llm': True,
        }

    def build_encouragement(
        self,
        action_name: str,
        rep_count: int,
        target_reps: int,
        peak_angle: float = 0,
        target_angle: float = 0
    ) -> dict:
        """
        构建鼓励语的Prompt（动作完成得好时使用）
        """
        progress_pct = (rep_count / target_reps * 100) if target_reps > 0 \
            else 0
        angle_pct = (peak_angle / target_angle * 100) if target_angle > 0 \
            else 0

        user_prompt = (
            f"患者{self.patient_name}正在做{action_name}。\n"
            f"进度：{rep_count}/{target_reps}次"
            f"（{progress_pct:.0f}%）\n"
            f"最大角度达到目标的 {angle_pct:.0f}%\n"
            f"患者做得很好！请生成一句鼓励语（不超过15个字）。"
        )

        return {
            'system': self.SYSTEM_PROMPT,
            'user': user_prompt,
            'use_llm': True,
        }

    def build_session_summary(
        self,
        level: str,
        actions_completed: List[dict],
        old_score: float,
        new_score: float,
        upgrade_suggestion: dict = None
    ) -> dict:
        """
        构建训练总结播报的Prompt
        """
        names = '、'.join(
            a.get('name', '动作') for a in actions_completed[:6]
        )
        total_reps = sum(int(a.get('reps', 0)) for a in actions_completed)
        actions_desc = (
            f"共 {len(actions_completed)} 个动作（{names}），"
            f"合计约 {total_reps} 次。"
        )

        score_change = new_score - old_score
        trend = "提高" if score_change > 0 else \
                "下降" if score_change < 0 else "持平"

        user_prompt = (
            f"患者{self.patient_name}完成了今天的{level}级训练。\n"
            f"{actions_desc}\n"
            f"评分：{old_score:.0f} 到 {new_score:.0f}（{trend}"
            f"{abs(score_change):.0f} 分）。\n"
        )

        if upgrade_suggestion:
            user_prompt += (
                f"可建议从 {upgrade_suggestion['from']} 级"
                f"升到 {upgrade_suggestion['to']} 级（一句带过即可）。\n"
            )

        user_prompt += (
            "请用1到2句话生成训练总结播报，"
            "总共不超过60个字。"
            "先简要肯定今天的表现，再提一句评分变化或鼓励即可。"
            "不要逐条念动作数据，不要医学术语。"
        )

        return {
            'system': self.SYSTEM_PROMPT,
            'user': user_prompt,
            'use_llm': True,
        }

    def build_safety_alert(
        self,
        alert_type: str,
        details: str = ""
    ) -> dict:
        """
        构建安全警报（不经过LLM，直接播报）
        """
        alerts = {
            'fall_risk': "注意安全！检测到身体不稳，请扶好身边的支撑物。",
            'pain_detected': "检测到您可能不太舒服，我们先暂停一下，休息休息。",
            'tremor_severe': "手部抖动有些严重，建议今天先到这里，"
                            "下次训练前请咨询您的医生。",
            'heart_rate_high': "运动强度可能有点大了，我们休息一会儿再继续。",
            'out_of_frame': "您好像走出了摄像头范围，请回到摄像头前方。",
        }

        message = alerts.get(alert_type, f"安全提示：{details}")

        return {
            'system': '',
            'user': '',
            'direct_output': message,
            'use_llm': False,
            'priority': 'high',
        }
