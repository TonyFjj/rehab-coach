"""
视觉质量分析：遮挡 / 多人 / 逆光检测与会话级 quality_score。
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# 评估 / 上肢动作关键关节
_ARM_KEYS = (
    'left_shoulder', 'right_shoulder',
    'left_elbow', 'right_elbow',
    'left_wrist', 'right_wrist',
)

# 下肢训练关键关节
_LOWER_KEYS = (
    'left_hip', 'right_hip',
    'left_knee', 'right_knee',
    'left_ankle', 'right_ankle',
)

_OCCLUSION_MSG = {
    'upper': '请露出肩、肘和手腕',
    'lower': '请露出髋、膝和脚踝',
    'integration': '请确保肩、髋和四肢都在画面内且未被遮挡',
}


def bbox_iou(a: List[float], b: List[float]) -> float:
    """计算两个 xyxy bbox 的 IoU。"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


TRACK_IOU_MATCH = 0.30      # 认定同一人的 IoU 下限
TRACK_IOU_REFRESH = 0.35    # 更新锁定框所需 IoU
TRACK_IOU_LOOSE = 0.10      # 丢失重关联时的最低重叠


def _bbox_center(b: List[float]) -> tuple:
    return (b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5


def score_bbox_for_supine_patient(
    box: list,
    frame_size: Optional[tuple],
) -> float:
    """
    卧床场景：优先选「躺卧患者」而非站立护理者。
    躺卧者通常 bbox 更宽、中心更靠画面下方；站立者更高窄。
    """
    if not box or len(box) < 4 or not frame_size or len(frame_size) < 2:
        return 0.0
    fw, fh = float(frame_size[0]), float(frame_size[1])
    if fw <= 0 or fh <= 0:
        return 0.0
    x1, y1, x2, y2 = [float(v) for v in box[:4]]
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    bcx, bcy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
    aspect = w / h
    # 画面 Y 向下：bcy 越大越靠下（床面区域）
    lower_score = bcy / fh
    flat_score = min(aspect, 2.5) if aspect >= 1.05 else aspect * 0.35
    area_ratio = (w * h) / (fw * fh)
    # 站立者惩罚：明显竖长且中心偏高
    standing_penalty = 0.0
    if h > w * 1.25 and bcy < fh * 0.55:
        standing_penalty = 0.45 + min(0.35, (h / w - 1.25) * 0.2)
    return (
        lower_score * 2.2
        + flat_score * 0.55
        + area_ratio * 1.5
        - standing_penalty
    )


def pick_person_index(
    boxes_xyxy: np.ndarray,
    track_bbox: Optional[list] = None,
    frame_size: Optional[tuple] = None,
    pick_mode: str = 'default',
) -> int:
    """
    多人时：优先 IoU 跟踪锁定 bbox；
    无锁定时：选画面中心最近的人；
    有锁定但 IoU 不足时：按与锁定框中心距离选，避免跳到更大目标。
    """
    if boxes_xyxy is None or len(boxes_xyxy) == 0:
        return 0
    if len(boxes_xyxy) == 1:
        return 0

    if track_bbox:
        ious = [
            bbox_iou(box.tolist(), track_bbox)
            for box in boxes_xyxy
        ]
        best_idx = int(np.argmax(ious))
        if ious[best_idx] >= TRACK_IOU_MATCH:
            return best_idx

        tcx, tcy = _bbox_center(track_bbox)
        candidates = [
            i for i, iou in enumerate(ious) if iou >= TRACK_IOU_LOOSE
        ]
        if not candidates:
            candidates = list(range(len(boxes_xyxy)))

        def _center_dist(i: int) -> float:
            bcx, bcy = _bbox_center(boxes_xyxy[i].tolist())
            return (bcx - tcx) ** 2 + (bcy - tcy) ** 2

        return min(candidates, key=_center_dist)

    if pick_mode == 'supine_bed' and frame_size and len(frame_size) >= 2:
        scores = [
            score_bbox_for_supine_patient(box.tolist(), frame_size)
            for box in boxes_xyxy
        ]
        return int(np.argmax(scores))

    if frame_size and len(frame_size) >= 2:
        fw, fh = float(frame_size[0]), float(frame_size[1])
        cx, cy = fw * 0.5, fh * 0.5
        dists = []
        for box in boxes_xyxy:
            bcx, bcy = _bbox_center(box.tolist())
            dists.append((bcx - cx) ** 2 + (bcy - cy) ** 2)
        return int(np.argmin(dists))
    areas = [
        max(0.0, (b[2] - b[0]) * (b[3] - b[1]))
        for b in boxes_xyxy
    ]
    return int(np.argmax(areas))


def track_bbox_match_iou(box: Optional[list], track_bbox: Optional[list]) -> float:
    """当前检测框与锁定框的 IoU。"""
    if not box or not track_bbox:
        return 0.0
    return bbox_iou(box, track_bbox)


def analyze_brightness(image: np.ndarray, cfg: dict) -> Tuple[float, bool]:
    """
    分析亮度，检测逆光/过曝/欠曝。

    Returns:
        (lighting_score 0~1, is_backlight)
    """
    if image is None or not HAS_CV2:
        return 1.0, False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_val = float(np.mean(gray))
    bright_ratio = float(np.mean(gray > 230))
    dark_ratio = float(np.mean(gray < 35))

    bright_thr = float(cfg.get('backlight_bright_ratio', 0.15))
    dark_thr = float(cfg.get('backlight_dark_ratio', 0.40))

    is_backlight = bright_ratio >= bright_thr or dark_ratio >= dark_thr

    # 理想均值约 90~170
    if 80 <= mean_val <= 180:
        mean_score = 1.0
    elif mean_val < 80:
        mean_score = max(0.0, mean_val / 80.0)
    else:
        mean_score = max(0.0, 1.0 - (mean_val - 180) / 75.0)

    lighting_score = max(
        0.0,
        min(1.0, 0.5 * mean_score + 0.25 * (1.0 - bright_ratio / 0.3)
            + 0.25 * (1.0 - dark_ratio / 0.5)),
    )
    if is_backlight:
        lighting_score = min(lighting_score, 0.45)
    return lighting_score, is_backlight


def _keys_for_region(body_region: str) -> Tuple[str, ...]:
    region = (body_region or 'upper').strip().lower()
    if region in ('lower', 'lower_body'):
        return _LOWER_KEYS
    if region in ('integration', 'full', 'full_body'):
        return _ARM_KEYS + _LOWER_KEYS
    return _ARM_KEYS


def joint_occlusion_score(
    keypoints_2d: Dict[str, dict],
    conf_min: float = 0.45,
    body_region: str = 'upper',
) -> Tuple[float, bool]:
    """
    关键关节置信度 → 遮挡评分。

    Returns:
        (occlusion_score 0~1 越高越好, is_occluded)
    """
    if not keypoints_2d:
        return 0.0, True

    confs = []
    for name in _keys_for_region(body_region):
        kp = keypoints_2d.get(name)
        if kp:
            confs.append(float(kp.get('conf', 0.0)))

    if not confs:
        return 0.0, True

    avg_conf = float(np.mean(confs))
    low_ratio = sum(1 for c in confs if c < conf_min) / len(confs)
    score = max(0.0, min(1.0, avg_conf * (1.0 - 0.5 * low_ratio)))
    is_occluded = avg_conf < conf_min or low_ratio >= 0.5
    return score, is_occluded


def analyze_frame(
    skeleton: Optional[dict],
    image: Optional[np.ndarray],
    cfg: dict,
    body_region: str = 'upper',
) -> dict:
    """单帧质量分析。"""
    conf_min = float(cfg.get('joint_conf_min', 0.45))
    kpts = (skeleton or {}).get('keypoints_2d_left') or {}
    num_persons = int((skeleton or {}).get('num_persons') or 0)
    pose_ok = bool(kpts)

    occ_score, is_occluded = joint_occlusion_score(
        kpts, conf_min, body_region=body_region,
    )
    light_score, is_backlight = analyze_brightness(image, cfg)
    is_multi = num_persons > 1

    multi_warn = float(cfg.get('multi_person_warn_ratio', 0.25))
    frame_ok = (
        pose_ok
        and not is_backlight
        and not is_occluded
        and not is_multi
    )

    frame_score = (
        0.35 * (1.0 if pose_ok else 0.0)
        + 0.25 * occ_score
        + 0.20 * light_score
        + 0.20 * (0.0 if is_multi else 1.0)
    )

    status = 'ok'
    if is_backlight:
        status = 'backlight'
    elif is_multi:
        status = 'multi_person'
    elif is_occluded or not pose_ok:
        status = 'occlusion'

    return {
        'frame_score': round(frame_score, 3),
        'frame_ok': frame_ok,
        'pose_ok': pose_ok,
        'occlusion_score': round(occ_score, 3),
        'lighting_score': round(light_score, 3),
        'is_occluded': is_occluded,
        'is_backlight': is_backlight,
        'is_multi_person': is_multi,
        'num_persons': num_persons,
        'status': status,
        'bbox': (skeleton or {}).get('bbox'),
    }


def aggregate_quality(
    frames: List[dict],
    cfg: dict,
    allow_companion: bool = False,
    body_region: str = 'upper',
) -> dict:
    """汇总多帧质量 → 会话级 quality_score 与告警。"""
    if not frames:
        return {
            'quality_score': 0.0,
            'pose_rate': 0.0,
            'occlusion_ratio': 1.0,
            'multi_person_ratio': 0.0,
            'backlight_ratio': 0.0,
            'use_vision_fusion': False,
            'vision_status': 'no_signal',
            'warnings': ['未检测到摄像头画面或骨骼'],
            'primary_warning': '未检测到有效视觉信号',
        }

    n = len(frames)
    pose_ok_count = sum(1 for f in frames if f.get('pose_ok'))
    occ_count = sum(1 for f in frames if f.get('is_occluded'))
    multi_count = sum(1 for f in frames if f.get('is_multi_person'))
    backlight_count = sum(1 for f in frames if f.get('is_backlight'))

    pose_rate = pose_ok_count / n
    occlusion_ratio = occ_count / n
    multi_person_ratio = multi_count / n
    backlight_ratio = backlight_count / n
    avg_frame_score = float(np.mean([f.get('frame_score', 0) for f in frames]))

    quality_score = max(0.0, min(1.0, (
        0.35 * pose_rate
        + 0.25 * (1.0 - occlusion_ratio)
        + 0.20 * (1.0 - backlight_ratio)
        + 0.20 * (1.0 - multi_person_ratio)
    )))

    fusion_min = float(cfg.get('fusion_min_quality', 0.40))
    partial_min = float(cfg.get('partial_fusion_quality', 0.70))
    use_fusion = quality_score >= fusion_min
    partial_fusion = fusion_min <= quality_score < partial_min

    warnings = []
    primary = ''
    if backlight_ratio >= 0.30:
        warnings.append('逆光，请转身或避开窗户')
        primary = primary or '逆光'
    if multi_person_ratio >= float(cfg.get('multi_person_warn_ratio', 0.25)):
        if not allow_companion:
            warnings.append('请其他人暂时离开画面')
            primary = primary or '多人入镜'
    if occlusion_ratio >= 0.35:
        region = (body_region or 'upper').strip().lower()
        if region in ('lower', 'lower_body'):
            msg_key = 'lower'
        elif region in ('integration', 'full', 'full_body'):
            msg_key = 'integration'
        else:
            msg_key = 'upper'
        warnings.append(_OCCLUSION_MSG[msg_key])
        primary = primary or '遮挡'
    if pose_rate < 0.50:
        warnings.append('请站进画面中央')
        primary = primary or '检测不稳定'

    if not use_fusion:
        warnings.append('视觉信号弱，本次以传感器为准')
        primary = primary or '视觉不可用'

    status = 'ok'
    if not use_fusion:
        status = 'poor'
    elif partial_fusion:
        status = 'degraded'
    elif primary == '逆光':
        status = 'backlight'
    elif primary == '多人入镜' and not allow_companion:
        status = 'multi_person'
    elif primary == '遮挡':
        status = 'occlusion'
    elif allow_companion and multi_person_ratio >= float(
        cfg.get('multi_person_warn_ratio', 0.25)
    ):
        status = 'caregiver_present'

    return {
        'quality_score': round(quality_score, 3),
        'pose_rate': round(pose_rate, 3),
        'occlusion_ratio': round(occlusion_ratio, 3),
        'multi_person_ratio': round(multi_person_ratio, 3),
        'backlight_ratio': round(backlight_ratio, 3),
        'avg_frame_score': round(avg_frame_score, 3),
        'valid_frames': n,
        'use_vision_fusion': use_fusion,
        'partial_fusion': partial_fusion,
        'vision_status': status,
        'warnings': warnings,
        'primary_warning': primary,
        'fusion_min_quality': fusion_min,
        'partial_fusion_quality': partial_min,
    }


def build_user_message(quality: dict) -> str:
    """生成 TTS / 字幕用提示语。"""
    if quality.get('vision_status') == 'ok':
        return '摄像头检测正常，请开始动作。'
    warnings = quality.get('warnings') or []
    if warnings:
        return warnings[0]
    return '请调整站位与光线后重试。'


def blend_coef_toward_one(coef: float, quality_score: float, partial_min: float) -> float:
    """部分可信时把视觉系数向 1.0 插值，减少误伤。"""
    if quality_score >= partial_min:
        return coef
    if partial_min <= 0:
        return coef
    t = quality_score / partial_min
    return coef * t + 1.0 * (1.0 - t)
