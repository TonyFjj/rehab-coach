"""
初始健康评估指导方案（时间与语音文案）
与 initial_assessment.py / IMU_measure / Qt 评估页共用同一数据源。

评估仅做一次，整段连续动作 30 秒：
  从双手自然下垂 → 手心朝外侧平举 → 举过头顶 → 在头顶保持，直至倒计时结束。

界面字幕（较长）与 TTS 播报（较短）分开：字幕看屏幕，语音只播要点。
"""

COLLECT_SECONDS = 30

# ---- 界面大字字幕（Qt 显示）----
INTRO_TEXT = (
    "您好，现在开始进行健康评估。\n"
    "本次只做一次连续动作，共三十秒：\n"
    "从双手自然下垂，到侧平举举过头顶后保持。\n"
    "请同时看屏幕大字字幕，并听语音引导。"
)

ACTION_TEXT = (
    "【侧平举过顶·保持】请在一个连续动作中完成：\n"
    "① 开始时双手自然下垂；\n"
    "② 手心朝外，像侧平举一样缓慢向外抬起；\n"
    "③ 继续举过头顶，到达最高点后保持不动，直到倒计时结束。\n"
    "只做一次，不要重复，左右尽量对称、动作平稳。"
)

ANALYZING_TEXT = "三十秒动作已完成，正在分析 IMU 数据，请稍候。"
DONE_TEXT = "评估完成，请查看屏幕上的评分结果。"

# ---- TTS 短播报（预生成缓存，减少等待）----
INTRO_TTS = "开始健康评估。"
ACTION_TTS = (
    "下面做一个动作：双手自然下垂，手心朝外，"
    "像侧平举一样抬过头顶并保持，一共三十秒，只做一次。"
)
COLLECT_START_TTS = "开始，请做动作。"
RAISE_HANDS_TTS = "请抬手。"
RAISE_HANDS_DELAY_SEC = 5  # 30 秒倒计时显示 00:25 时播报
ANALYZING_TTS = "正在分析，请稍候。"
DONE_TTS = "评估完成。"
DATA_OK_TTS = "采集完成。"
DATA_WARN_TTS = "数据可能不足，请检查传感器。"
SYNC_FAIL_TTS = "结果同步失败，请查看日志。"

PREP_TEXT = ACTION_TEXT
MOTION_TEXT = ACTION_TEXT
PREP_SECONDS = 0

REST_TEXT = ""
REST_BETWEEN_ACTIONS = 0.0
PREPARE_AFTER_INSTRUCTION = 1.0

TEST_ACTIONS = [
    {
        'name': '侧平举过顶保持',
        'instruction': ACTION_TEXT,
        'prep_instruction': ACTION_TEXT,
        'motion_instruction': ACTION_TEXT,
        'prep_duration': 0,
        'duration': COLLECT_SECONDS,
        'total_duration': COLLECT_SECONDS,
        'measure': 'overhead_abduction_hold',
    },
]


def assessment_tts_phrases() -> list:
    """评估流程全部短播报句，供 TTS 预生成。"""
    return [
        INTRO_TTS,
        ACTION_TTS,
        COLLECT_START_TTS,
        RAISE_HANDS_TTS,
        ANALYZING_TTS,
        DONE_TTS,
        DATA_OK_TTS,
        DATA_WARN_TTS,
        SYNC_FAIL_TTS,
    ]


def total_estimated_seconds() -> int:
    """估算整段评估时长（秒），供 Qt 进度条上限参考。"""
    action = TEST_ACTIONS[0]
    return 8 + int(action.get('total_duration', COLLECT_SECONDS)) + 8


def plan_for_qt() -> dict:
    """序列化为 Qt 可消费的评估方案。"""
    actions = []
    for i, action in enumerate(TEST_ACTIONS, start=1):
        actions.append({
            'index': i,
            'name': action['name'],
            'instruction': action['instruction'],
            'prep_instruction': action.get('prep_instruction', ACTION_TEXT),
            'motion_instruction': action.get('motion_instruction', ACTION_TEXT),
            'prep_duration': action.get('prep_duration', 0),
            'duration': action.get('duration', COLLECT_SECONDS),
            'total_duration': action.get('total_duration', COLLECT_SECONDS),
        })
    return {
        'intro_text': INTRO_TEXT,
        'action_text': ACTION_TEXT,
        'prep_text': PREP_TEXT,
        'motion_text': MOTION_TEXT,
        'rest_text': REST_TEXT,
        'analyzing_text': ANALYZING_TEXT,
        'done_text': DONE_TEXT,
        'rest_between_actions': REST_BETWEEN_ACTIONS,
        'prepare_seconds': PREPARE_AFTER_INSTRUCTION,
        'collect_seconds': COLLECT_SECONDS,
        'total_estimated_seconds': total_estimated_seconds(),
        'actions': actions,
    }
