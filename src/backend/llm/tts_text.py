"""
TTS 文本规范化与常用播报句构建。
"""

import re
from typing import List, Optional

_DIGITS = '零一二三四五六七八九'
_UNITS = ('', '十', '百', '千')


def int_to_zh(n: int) -> str:
    """将非负整数转为中文读法（如 5→五，12→十二，105→一百零五）。"""
    if n < 0:
        return '负' + int_to_zh(-n)
    if n == 0:
        return '零'
    if n < 10:
        return _DIGITS[n]
    if n < 20:
        tail = _DIGITS[n % 10] if n % 10 else ''
        return '十' + tail
    if n < 100:
        tens, ones = divmod(n, 10)
        text = _DIGITS[tens] + '十'
        if ones:
            text += _DIGITS[ones]
        return text
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        text = _DIGITS[hundreds] + '百'
        if rem == 0:
            return text
        if rem < 10:
            return text + '零' + _DIGITS[rem]
        return text + int_to_zh(rem)
    if n < 10000:
        thousands, rem = divmod(n, 1000)
        text = _DIGITS[thousands] + '千'
        if rem == 0:
            return text
        if rem < 100:
            return text + '零' + int_to_zh(rem)
        return text + int_to_zh(rem)
    return str(n)


def _replace_number_match(match: re.Match) -> str:
    raw = match.group(0)
    if '.' in raw:
        whole, frac = raw.split('.', 1)
        whole_zh = int_to_zh(int(whole)) if whole else '零'
        frac_zh = ''.join(_DIGITS[int(ch)] for ch in frac if ch.isdigit())
        return whole_zh + '点' + frac_zh if frac_zh else whole_zh
    return int_to_zh(int(raw))


# 关节英文名 → 中文（TTS 友好）
JOINT_NAMES_ZH = {
    'shoulder_flexion': '肩关节',
    'shoulder_abduction': '肩关节',
    'knee_flexion': '膝关节',
    'ankle_dorsiflexion': '踝关节',
    'ankle_plantarflexion': '踝关节',
}

_DEGREE_CHARS = (
    '°', 'º', '˚', '℃', '℉', '∘',
    '\u00b0', '\u00ba', '\u02da',
)


def sanitize_for_tts(text: str) -> str:
    """将播报文本转为 Sherpa 中文 TTS 可合成的口语化句子。"""
    if not text:
        return text

    for en, zh in JOINT_NAMES_ZH.items():
        text = text.replace(en, zh)

    for ch in _DEGREE_CHARS:
        text = text.replace(ch, '度')

    text = text.replace('->', '到').replace('→', '到').replace('—', '到')
    text = re.sub(r'\(\s*目标\s*[^)]+\)', '', text)
    text = re.sub(r'\(\s*建议[^)]+\)', '', text)
    text = re.sub(r'\(\s*最大[^)]+\)', '', text)
    text = re.sub(r'[():]', ' ', text)
    text = re.sub(r'关节\s+肩关节', '肩关节', text)
    text = re.sub(r'\d+(?:\.\d+)?', _replace_number_match, text)
    text = re.sub(r'\s+到\s+', '到', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if text and text[-1] not in '。！？；':
        text += '。'
    return text


def action_intro_title(index: int, name: str) -> str:
    """如：第一个动作：坐姿肩关节主动前屈。"""
    return f"第{int_to_zh(index)}个动作：{name}。"


def action_intro_description(description: str) -> str:
    desc = (description or '').strip()
    if not desc:
        return '请按照提示完成动作。'
    if desc[-1] not in '。！？':
        desc += '。'
    return desc


def rest_between_actions(rest_seconds: int) -> str:
    sec = max(0, int(rest_seconds))
    if sec <= 0:
        return '做得很好，准备下一个动作。'
    return f'做得很好，休息{int_to_zh(sec)}秒，准备下一个动作。'


def collect_standard_phrases() -> List[str]:
    """系统固定播报句（启动时可预生成）。"""
    phrases = [
        '训练已暂停。',
        '继续训练，加油！',
        '训练已结束，辛苦了。',
        '训练已结束。',
        '好，保持住！',
        '慢慢放下来。',
        '抱歉，当前等级没有训练动作，请联系管理员。',
        '好的，做得很好，休息一下。',
    ]
    try:
        from assessment_plan import assessment_tts_phrases
        phrases.extend(assessment_tts_phrases())
    except ImportError:
        pass
    return phrases


def collect_training_phrases(
    level_name: str,
    actions: List[dict],
) -> List[str]:
    """一次训练会话中可提前合成的播报句。"""
    phrases = [
        f'开始{level_name}训练，请做好准备。',
    ]
    phrases.extend(collect_standard_phrases())

    rest_values = set()
    for i, action in enumerate(actions):
        phrases.append(action_intro_title(i + 1, action.get('name', f'动作{i + 1}')))
        phrases.append(
            action_intro_description(action.get('description', ''))
        )
        name = action.get('name', '动作')
        phrases.append(f'{name}完成了，做得非常好！')
        rest_values.add(int(action.get('rest_between_sets', 5)))

    for sec in sorted(rest_values):
        phrases.append(rest_between_actions(sec))

    return phrases
