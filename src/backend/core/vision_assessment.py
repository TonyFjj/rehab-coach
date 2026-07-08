"""
评估阶段视觉监测：采集侧平举过顶动作的角度、对称性与姿态质量，
并结合遮挡/多人/逆光质量门控；视觉指标仅供界面参考，不参与 IMU 计分。
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

import numpy as np

from core.vision_quality import (
    aggregate_quality,
    analyze_frame,
    blend_coef_toward_one,
    build_user_message,
)

# 六维英文键 ↔ 视觉系数权重（完成度 vs 准确度）
DEFAULT_DIM_VISION_WEIGHTS = {
    'range_of_motion': {'completion': 0.70, 'accuracy': 0.30},
    'smoothness': {'completion': 0.20, 'accuracy': 0.80},
    'tremor': {'completion': 0.10, 'accuracy': 0.90},
    'symmetry': {'completion': 0.30, 'accuracy': 0.70},
    'speed': {'completion': 0.60, 'accuracy': 0.40},
    'endurance': {'completion': 0.80, 'accuracy': 0.20},
}

CN_TO_EN = {
    '抬举幅度': 'range_of_motion',
    '运动平滑度': 'smoothness',
    '震颤程度': 'tremor',
    '双侧对称性': 'symmetry',
    '运动速度': 'speed',
    '运动耐力': 'endurance',
    'endurance': 'endurance',
    'fatigue': 'endurance',
}


def _normalize_dim_key(key: str) -> str:
    if key in DEFAULT_DIM_VISION_WEIGHTS:
        return key
    return CN_TO_EN.get(key, key)


def _map_level(total_score: float) -> str:
    if total_score <= 30:
        return 'L1'
    if total_score <= 60:
        return 'L2'
    if total_score <= 80:
        return 'L3'
    return 'L4'


class VisionAssessmentMonitor:
    """IMU 采集窗口内并行采样视觉，输出系数 + 质量门控。"""

    def __init__(
        self,
        fusion_engine,
        vision_pipeline=None,
        config: dict = None,
        on_live_update: Callable[[dict], None] = None,
    ):
        cfg = config or {}
        self.fusion_engine = fusion_engine
        self.vision_pipeline = vision_pipeline
        self.cfg = cfg
        self.target_abduction = float(cfg.get('target_abduction_deg', 150))
        self.hold_angle = float(cfg.get('hold_angle_deg', 120))
        self.min_coef = float(cfg.get('min_coef', 0.35))
        self.sample_interval = float(cfg.get('sample_interval_sec', 0.1))
        self.precheck_seconds = float(cfg.get('precheck_seconds', 3.0))
        self.precheck_pass_score = float(cfg.get('precheck_pass_score', 0.55))
        self.precheck_retries = int(cfg.get('precheck_retries', 1))
        self.on_live_update = on_live_update

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._deadline = 0.0
        self._lock = threading.Lock()
        self._samples: list = []
        self._quality_frames: list = []
        self._live: dict = {}

    @property
    def live_stats(self) -> dict:
        with self._lock:
            return dict(self._live)

    def run_precheck(self) -> dict:
        """
        采集前预检（默认 3 秒）：检测遮挡/多人/逆光。
        通过后锁定主用户 bbox。
        """
        if self.vision_pipeline is None:
            return {
                'passed': True,
                'skipped': True,
                'quality_score': 1.0,
                'message': '无摄像头，跳过视觉预检',
                'vision_status': 'skipped',
                'warnings': [],
            }

        best_result = None
        attempts = 1 + max(0, self.precheck_retries)

        for attempt in range(attempts):
            frames = self._collect_quality_frames(self.precheck_seconds)
            quality = aggregate_quality(frames, self.cfg)
            quality['attempt'] = attempt + 1
            quality['message'] = build_user_message(quality)
            quality['passed'] = (
                quality.get('quality_score', 0) >= self.precheck_pass_score
            )
            quality['skipped'] = False

            if quality['passed']:
                best_result = quality
                self._lock_track_from_frames(frames)
                break
            best_result = quality
            if attempt + 1 < attempts:
                time.sleep(0.5)

        if best_result is None:
            best_result = aggregate_quality([], self.cfg)
            best_result['passed'] = False
            best_result['message'] = build_user_message(best_result)

        with self._lock:
            self._live['precheck'] = best_result
        return best_result

    def _lock_track_from_frames(self, frames: list):
        """预检通过：锁定画面中央、姿态质量最好的主用户。"""
        if not self.vision_pipeline:
            return
        left, _ = self.vision_pipeline.get_latest_frames()
        fw = float(left.shape[1]) if left is not None else 0.0
        fh = float(left.shape[0]) if left is not None else 0.0
        cx, cy = fw * 0.5, fh * 0.5

        best_bbox = None
        best_rank = -1e9
        for fr in frames:
            bbox = fr.get('bbox')
            if not bbox or not fr.get('pose_ok'):
                continue
            x1, y1, x2, y2 = bbox[:4]
            bcx = (x1 + x2) * 0.5
            bcy = (y1 + y2) * 0.5
            dist = ((bcx - cx) ** 2 + (bcy - cy) ** 2) if fw > 0 else 0.0
            rank = float(fr.get('frame_score', 0)) * 1000.0 - dist
            if rank > best_rank:
                best_rank = rank
                best_bbox = bbox

        if best_bbox:
            self.vision_pipeline.lock_patient(best_bbox, 'precheck')
            return
        skel = self.vision_pipeline.get_latest_skeleton()
        if skel and skel.get('bbox'):
            self.vision_pipeline.lock_patient(skel['bbox'], 'precheck-skeleton')

    def _collect_quality_frames(self, duration: float) -> list:
        deadline = time.time() + max(0.5, duration)
        frames = []
        while time.time() < deadline:
            fr = self._read_quality_frame()
            if fr is not None:
                frames.append(fr)
            time.sleep(0.12)
        return frames

    def _read_quality_frame(self) -> Optional[dict]:
        if self.vision_pipeline is None:
            return None
        skel = self.vision_pipeline.get_latest_skeleton()
        left, _ = self.vision_pipeline.get_latest_frames()
        return analyze_frame(skel, left, self.cfg)

    def start(self, duration_sec: float):
        """开始采集（与 IMU_measure 同步）。"""
        self.stop(wait=False)
        with self._lock:
            self._samples = []
            self._quality_frames = []
            self._live = {
                'completion_coef': 0.0,
                'accuracy_coef': 0.0,
                'quality_score': 0.0,
                'vision_status': 'collecting',
                'current_angle': 0.0,
                'max_angle': 0.0,
                'pose_rate': 0.0,
                'hold_ratio': 0.0,
                'symmetry': 0.0,
                'valid_frames': 0,
                'warnings': [],
            }
        self._deadline = time.time() + max(1.0, duration_sec)
        self._running = True
        self._thread = threading.Thread(
            target=self._sample_loop, daemon=True, name='vision-assessment',
        )
        self._thread.start()

    def stop(self, wait: bool = True) -> dict:
        """停止采集并返回汇总系数。"""
        self._running = False
        if self._thread and wait:
            self._thread.join(timeout=2.0)
        self._thread = None
        return self.summarize()

    def summarize(self) -> dict:
        with self._lock:
            samples = list(self._samples)
            qframes = list(self._quality_frames)

        quality = aggregate_quality(qframes, self.cfg)

        if not samples:
            empty = {
                'completion_coef': 1.0,
                'accuracy_coef': 1.0,
                'combined_coef': 1.0,
                'max_angle': 0.0,
                'hold_ratio': 0.0,
                'symmetry_score': 1.0,
                'pose_rate': 0.0,
                'smoothness_score': 1.0,
                'valid_frames': 0,
                'vision_available': False,
                'use_vision_fusion': False,
                'dimension_coefficients': _build_dim_coefficients(
                    1.0, 1.0, DEFAULT_DIM_VISION_WEIGHTS, self.min_coef,
                ),
            }
            empty.update(quality)
            return empty

        angles = [s['angle'] for s in samples]
        left_angles = [s['left'] for s in samples if s['left'] > 0]
        right_angles = [s['right'] for s in samples if s['right'] > 0]
        max_angle = max(angles) if angles else 0.0
        hold_count = sum(1 for a in angles if a >= self.hold_angle)
        hold_ratio = hold_count / len(samples)

        reach_ratio = min(1.0, max_angle / max(self.target_abduction, 1.0))
        completion_coef = max(
            self.min_coef,
            min(1.0, 0.65 * reach_ratio + 0.35 * hold_ratio),
        )

        if left_angles and right_angles:
            avg_l = float(np.mean(left_angles))
            avg_r = float(np.mean(right_angles))
            sym_diff = abs(avg_l - avg_r) / max(avg_l, avg_r, 1.0)
            symmetry_score = max(0.0, 1.0 - sym_diff)
        else:
            symmetry_score = 0.6

        if len(angles) >= 3:
            jitter = float(np.std(np.diff(angles)))
            smoothness_score = max(0.0, min(1.0, 1.0 - jitter / 25.0))
        else:
            smoothness_score = 0.7

        pose_rate = len(samples) / max(
            1.0, (samples[-1]['t'] - samples[0]['t']) / self.sample_interval
        )
        pose_rate = min(1.0, pose_rate)

        accuracy_coef = max(
            self.min_coef,
            min(
                1.0,
                0.40 * symmetry_score
                + 0.35 * smoothness_score
                + 0.25 * pose_rate,
            ),
        )

        q_score = float(quality.get('quality_score', 0))
        partial_min = float(quality.get('partial_fusion_quality', 0.70))
        use_fusion = bool(quality.get('use_vision_fusion', False))

        if use_fusion and quality.get('partial_fusion'):
            completion_coef = blend_coef_toward_one(
                completion_coef, q_score, partial_min,
            )
            accuracy_coef = blend_coef_toward_one(
                accuracy_coef, q_score, partial_min,
            )

        dim_coefs = _build_dim_coefficients(
            completion_coef, accuracy_coef,
            DEFAULT_DIM_VISION_WEIGHTS, self.min_coef,
        )

        summary = {
            'completion_coef': round(completion_coef, 3),
            'accuracy_coef': round(accuracy_coef, 3),
            'combined_coef': round(completion_coef * accuracy_coef, 3),
            'max_angle': round(max_angle, 1),
            'hold_ratio': round(hold_ratio, 3),
            'symmetry_score': round(symmetry_score, 3),
            'pose_rate': round(pose_rate, 3),
            'smoothness_score': round(smoothness_score, 3),
            'valid_frames': len(samples),
            'vision_available': use_fusion,
            'use_vision_fusion': use_fusion,
            'dimension_coefficients': dim_coefs,
        }
        summary.update(quality)

        with self._lock:
            self._live.update({
                'completion_coef': summary['completion_coef'],
                'accuracy_coef': summary['accuracy_coef'],
                'quality_score': summary.get('quality_score', 0),
                'vision_status': summary.get('vision_status', 'ok'),
                'warnings': summary.get('warnings', []),
                'current_angle': angles[-1] if angles else 0.0,
                'max_angle': summary['max_angle'],
                'pose_rate': summary['pose_rate'],
                'hold_ratio': summary['hold_ratio'],
                'symmetry': summary['symmetry_score'],
                'valid_frames': summary['valid_frames'],
            })
        return summary

    def _sample_loop(self):
        last_push = 0.0
        while self._running and time.time() < self._deadline:
            qfr = self._read_quality_frame()
            if qfr is not None:
                with self._lock:
                    self._quality_frames.append(qfr)

            sample = self._read_motion_sample(qfr)
            if sample is not None:
                with self._lock:
                    self._samples.append(sample)
                    self._live['current_angle'] = sample['angle']
                    self._live['max_angle'] = max(
                        self._live.get('max_angle', 0.0), sample['angle'],
                    )
                    self._live['valid_frames'] = len(self._samples)

            now = time.time()
            if self.on_live_update and now - last_push >= 0.5:
                last_push = now
                partial = self.summarize()
                partial['current_angle'] = self._live.get('current_angle', 0.0)
                self.on_live_update(partial)

            time.sleep(self.sample_interval)

    def _read_motion_sample(self, qfr: Optional[dict]) -> Optional[dict]:
        """质量不合格帧不参与角度采样（遮挡/逆光/多人）。"""
        if qfr is not None:
            if qfr.get('is_backlight') or qfr.get('is_multi_person'):
                return None
            if qfr.get('is_occluded') or not qfr.get('pose_ok'):
                return None

        try:
            angles = self.fusion_engine.compute_joint_angles()
        except Exception:
            return None
        if not angles:
            return None

        left = float(
            angles.get('shoulder_abduction_left')
            or angles.get('shoulder_flexion_left')
            or 0.0
        )
        right = float(
            angles.get('shoulder_abduction_right')
            or angles.get('shoulder_flexion_right')
            or 0.0
        )
        combined = float(
            angles.get('shoulder_combined')
            or angles.get('shoulder_abduction')
            or angles.get('shoulder_flexion')
            or max(left, right)
        )
        if combined <= 1.0 and left <= 1.0 and right <= 1.0:
            return None

        return {
            't': time.time(),
            'angle': combined,
            'left': left,
            'right': right,
        }


def _build_dim_coefficients(
    completion: float,
    accuracy: float,
    weights: dict,
    min_coef: float,
) -> Dict[str, float]:
    out = {}
    for key, w in weights.items():
        raw = w['completion'] * completion + w['accuracy'] * accuracy
        out[key] = round(max(min_coef, min(1.0, raw)), 3)
    return out


def apply_vision_to_imu_result(
    imu_result: dict,
    vision_summary: dict,
) -> dict:
    """附带视觉监测摘要；综合分与六维分保持 IMU 原始结果不变。"""
    if not imu_result:
        return imu_result

    out = dict(imu_result)
    if vision_summary:
        out['vision_assessment'] = vision_summary
    return out
