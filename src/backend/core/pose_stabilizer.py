"""
卧床/下肢场景：关键点时序平滑，减轻单腿动时双腿骨架联动抖动。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

_LEG_KEYS = (
    'left_hip', 'right_hip',
    'left_knee', 'right_knee',
    'left_ankle', 'right_ankle',
)

_UPPER_KEYS = (
    'left_shoulder', 'right_shoulder',
    'left_elbow', 'right_elbow',
    'left_wrist', 'right_wrist',
)

_SMOOTH_LEG = 0.30
_SMOOTH_UPPER = 0.35
_DECOUPLE_MIN_PX = 10.0
_IDLE_BLEND = 0.12


def _kp(kpts: dict, name: str):
    k = kpts.get(name)
    if not k or k.get('conf', 0) < 0.25:
        return None
    x, y = k.get('x'), k.get('y')
    if x is None or y is None:
        return None
    return float(x), float(y), float(k.get('conf', 0))


def _flex_proxy(hip, knee, ankle) -> float:
    """膝屈曲代理：髋-膝-踝夹角（与融合层一致）。"""
    if hip is None or knee is None or ankle is None:
        return 0.0
    a = np.array([hip[0] - knee[0], hip[1] - knee[1]], dtype=np.float64)
    b = np.array([ankle[0] - knee[0], ankle[1] - knee[1]], dtype=np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    cos_a = np.clip(float(np.dot(a / na, b / nb)), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_a)))


def _ema_keys(
    out: Dict[str, dict],
    prev: Dict[str, dict],
    keys: Tuple[str, ...],
    alpha: float,
) -> None:
    for name in keys:
        cur = out.get(name)
        old = prev.get(name)
        if not cur or not old:
            continue
        if cur.get('conf', 0) < 0.2:
            continue
        cur['x'] = alpha * cur['x'] + (1.0 - alpha) * old['x']
        cur['y'] = alpha * cur['y'] + (1.0 - alpha) * old['y']


def _blend_idle_leg(
    out: Dict[str, dict],
    prev: Dict[str, dict],
    side: str,
) -> None:
    for part in ('knee', 'ankle'):
        name = f'{side}_{part}'
        cur = out.get(name)
        old = prev.get(name)
        if cur and old:
            b = _IDLE_BLEND
            cur['x'] = b * cur['x'] + (1.0 - b) * old['x']
            cur['y'] = b * cur['y'] + (1.0 - b) * old['y']


def _pick_active_leg(
    dflex_l: float,
    dflex_r: float,
    ankle_up_l: float,
    ankle_up_r: float,
) -> Optional[str]:
    """返回应保留活动的一侧：'left' | 'right' | None。"""
    flex_active = None
    if abs(dflex_l) >= 4.0 or abs(dflex_r) >= 4.0:
        flex_active = 'left' if abs(dflex_l) >= abs(dflex_r) else 'right'

    lift_active = None
    if ankle_up_l > _DECOUPLE_MIN_PX or ankle_up_r > _DECOUPLE_MIN_PX:
        if ankle_up_l >= ankle_up_r * 0.85:
            if ankle_up_l > _DECOUPLE_MIN_PX * 0.6:
                lift_active = 'left'
        if ankle_up_r > ankle_up_l * 0.85:
            if ankle_up_r > _DECOUPLE_MIN_PX * 0.6:
                lift_active = 'right'
        if ankle_up_l > _DECOUPLE_MIN_PX and ankle_up_r > _DECOUPLE_MIN_PX:
            lift_active = 'left' if ankle_up_l >= ankle_up_r else 'right'

    if flex_active and lift_active:
        return flex_active if flex_active == lift_active else lift_active
    return flex_active or lift_active


def stabilize_supine_legs(
    keypoints_2d: Dict[str, dict],
    prev: Optional[Dict[str, dict]] = None,
) -> Dict[str, dict]:
    """
    1. 上下肢关键点 EMA 平滑
    2. 单腿动时抑制另一腿膝/踝被模型联动带起（屈膝或直腿抬高）
    """
    if not keypoints_2d:
        return keypoints_2d

    out = {k: dict(v) for k, v in keypoints_2d.items()}

    if prev:
        _ema_keys(out, prev, _LEG_KEYS, _SMOOTH_LEG)
        _ema_keys(out, prev, _UPPER_KEYS, _SMOOTH_UPPER)

    if not prev:
        return out

    lh = _kp(out, 'left_hip')
    rh = _kp(out, 'right_hip')
    lk = _kp(out, 'left_knee')
    rk = _kp(out, 'right_knee')
    la = _kp(out, 'left_ankle')
    ra = _kp(out, 'right_ankle')
    plk = _kp(prev, 'left_knee')
    prk = _kp(prev, 'right_knee')
    pla = _kp(prev, 'left_ankle')
    pra = _kp(prev, 'right_ankle')

    if not all((lh, rh, lk, rk, la, ra, plk, prk, pla, pra)):
        return out

    flex_l = _flex_proxy(lh, lk, la)
    flex_r = _flex_proxy(rh, rk, ra)
    pflex_l = _flex_proxy(_kp(prev, 'left_hip'), plk, pla)
    pflex_r = _flex_proxy(_kp(prev, 'right_hip'), prk, pra)
    dflex_l = flex_l - pflex_l
    dflex_r = flex_r - pflex_r

    ankle_up_l = pla[1] - la[1]
    ankle_up_r = pra[1] - ra[1]

    both_lift = (
        ankle_up_l > _DECOUPLE_MIN_PX
        and ankle_up_r > _DECOUPLE_MIN_PX
    )
    one_side_moves = (
        both_lift
        or (abs(dflex_l) >= 5.0 and abs(dflex_r) < 3.0)
        or (abs(dflex_r) >= 5.0 and abs(dflex_l) < 3.0)
    )
    if not one_side_moves:
        return out

    active = _pick_active_leg(dflex_l, dflex_r, ankle_up_l, ankle_up_r)
    if active == 'left':
        _blend_idle_leg(out, prev, 'right')
    elif active == 'right':
        _blend_idle_leg(out, prev, 'left')

    return out
