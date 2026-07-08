"""训练播报短句模板（不经 LLM，减少延迟）。"""

from typing import Dict, List, Optional

from .tts_text import int_to_zh, sanitize_for_tts


def build_session_summary_direct(
    level: str,
    actions_completed: List[dict],
    old_score: float,
    new_score: float,
    upgrade_suggestion: Optional[dict] = None,
) -> str:
    """
    生成简短训练总结（约两句话），可直接 TTS，无需 LLM。
    """
    n = len(actions_completed)
    if n == 0:
        return '今天的训练结束了，辛苦了。'

    total_reps = sum(int(a.get('reps', 0)) for a in actions_completed)
    delta = new_score - old_score

    if delta > 0.5:
        trend = f'提高了{int_to_zh(int(round(delta)))}分'
    elif delta < -0.5:
        trend = f'下降了{int_to_zh(int(round(abs(delta))))}分'
    else:
        trend = '基本稳定'

    level_num = level.upper().replace('L', '').strip()
    if level_num.isdigit():
        level_label = f'{int_to_zh(int(level_num))}级'
    else:
        level_label = level

    text = (
        f'今天的{level_label}训练完成了，'
        f'一共完成{int_to_zh(n)}个动作，'
        f'共{int_to_zh(total_reps)}次。'
        f'健康评分{trend}，目前是{int_to_zh(int(round(new_score)))}分。'
        f'坚持得很好，下次继续加油。'
    )

    if upgrade_suggestion:
        text += (
            f'建议从{upgrade_suggestion["from"]}级'
            f'升到{upgrade_suggestion["to"]}级，您可以考虑一下。'
        )

    return sanitize_for_tts(text)
