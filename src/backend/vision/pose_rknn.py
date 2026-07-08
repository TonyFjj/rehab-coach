"""
YOLOv8-Pose RKNN 推理（RK3588 NPU）
与 ultralytics 输出格式对齐，供 PoseEstimator 在 device=rknn 时使用。
"""

import time
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from rknnlite.api import RKNNLite
    HAS_RKNN = True
except ImportError:
    HAS_RKNN = False
    RKNNLite = None


class RknnPoseBackend:
    """RKNN Lite 运行的 YOLOv8n-Pose 后端。"""

    KEYPOINT_NAMES = {
        0: 'nose', 1: 'left_eye', 2: 'right_eye',
        3: 'left_ear', 4: 'right_ear',
        5: 'left_shoulder', 6: 'right_shoulder',
        7: 'left_elbow', 8: 'right_elbow',
        9: 'left_wrist', 10: 'right_wrist',
        11: 'left_hip', 12: 'right_hip',
        13: 'left_knee', 14: 'right_knee',
        15: 'left_ankle', 16: 'right_ankle',
    }

    def __init__(
        self,
        model_path: str,
        imgsz: int = 640,
        conf_threshold: float = 0.5,
        iou_threshold: float = 0.45,
    ):
        if not HAS_RKNN:
            raise ImportError(
                "rknnlite 未安装。板端: pip install rknn-toolkit2-lite"
            )
        if not HAS_CV2:
            raise ImportError("opencv-python 未安装")

        self.model_path = model_path
        self.imgsz = int(imgsz)
        if str(model_path).lower().endswith('.rknn') and self.imgsz != 640:
            print(
                f"[Pose-RKNN] inference_imgsz={self.imgsz} 与模型 640 不符，"
                f"已改用 640"
            )
            self.imgsz = 640
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self._rknn = RKNNLite()
        self._infer_lock = threading.Lock()
        self._inference_time = 0.0
        self._frame_count = 0
        self._zero_score_warned = False
        self._track_bbox = None
        self._pick_mode = 'default'
        self._last_num_persons = 0
        self._last_frame_size: Optional[tuple] = None

        print(f"[Pose-RKNN] 加载: {model_path}")
        ret = self._rknn.load_rknn(model_path)
        if ret != 0:
            raise RuntimeError(f"load_rknn 失败: {ret}")
        ret = self._rknn.init_runtime()
        if ret != 0:
            raise RuntimeError(f"init_runtime 失败: {ret}")
        print("[Pose-RKNN] NPU 运行时就绪")

        # 预热（_preprocess 返回 blob + meta，勿把 tuple 直接传给 inference）
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        blob, _ = self._preprocess(dummy)
        self._infer_tensor(blob)

    def release(self):
        if self._rknn is not None:
            try:
                self._rknn.release()
            except Exception:
                pass
            self._rknn = None

    def set_track_bbox(self, bbox):
        self._track_bbox = list(bbox) if bbox else None

    def set_pick_mode(self, mode: str):
        self._pick_mode = mode if mode in ('default', 'supine_bed') else 'default'

    def detect(self, image: np.ndarray) -> Optional[Dict]:
        if image is None:
            return None
        if len(image.shape) >= 2:
            self._last_frame_size = (image.shape[1], image.shape[0])
        blob, meta = self._preprocess(image)
        start = time.time()
        outputs = self._infer_tensor(blob)
        self._inference_time = (time.time() - start) * 1000
        self._frame_count += 1
        return self._decode(outputs, meta, image.shape)

    def detect_stereo(self, left: np.ndarray, right: np.ndarray):
        return self.detect(left), self.detect(right)

    def _infer_tensor(self, blob: np.ndarray):
        with self._infer_lock:
            out = self._rknn.inference(inputs=[blob])
        if not out:
            raise RuntimeError("RKNN inference 无输出")
        return out[0]

    def _preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, dict]:
        """Letterbox 到 imgsz×imgsz，与 YOLOv8 一致。"""
        h, w = image.shape[:2]
        r = min(self.imgsz / h, self.imgsz / w)
        new_unpad = (int(round(w * r)), int(round(h * r)))
        dw = self.imgsz - new_unpad[0]
        dh = self.imgsz - new_unpad[1]
        dw /= 2
        dh /= 2

        if (w, h) != new_unpad:
            resized = cv2.resize(
                image, new_unpad, interpolation=cv2.INTER_LINEAR
            )
        else:
            resized = image

        top = int(round(dh - 0.1))
        bottom = int(round(dh + 0.1))
        left = int(round(dw - 0.1))
        right = int(round(dw + 0.1))
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )

        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
        blob = np.expand_dims(rgb, axis=0).astype(np.uint8)
        meta = {
            'ratio': r,
            'pad': (left, top),
            'orig_hw': (h, w),
        }
        return blob, meta

    def _decode(
        self,
        output: np.ndarray,
        meta: dict,
        orig_shape: tuple,
    ) -> Optional[Dict]:
        pred = np.asarray(output)
        if pred.ndim == 3:
            pred = pred[0]
        if pred.shape[0] in (56, 57) and pred.shape[0] < pred.shape[1]:
            pred = pred.T

        if pred.shape[1] < 56:
            return None

        boxes_xywh = pred[:, :4].astype(np.float32)
        scores = pred[:, 4].astype(np.float32)
        kpts_raw = pred[:, 5:56].reshape(-1, 17, 3)

        valid = (
            np.isfinite(scores)
            & np.isfinite(boxes_xywh).all(axis=1)
            & (boxes_xywh[:, 2] > 1.0)
            & (boxes_xywh[:, 3] > 1.0)
        )
        if valid.any() and float(np.max(scores[valid])) <= 1e-6:
            if not self._zero_score_warned:
                self._zero_score_warned = True
                print(
                    "[Pose-RKNN] 警告: 模型置信度全为 0，"
                    "多为 INT8 全量化导致，请用 hybrid 重转或换回 yolov8n-pose.rknn"
                )
        mask = valid & (scores >= self.conf_threshold)
        if not np.any(mask):
            return None

        boxes_xywh = boxes_xywh[mask]
        scores = scores[mask]
        kpts_raw = kpts_raw[mask]

        boxes_xyxy = self._xywh2xyxy(boxes_xywh)
        if not np.isfinite(boxes_xyxy).all():
            return None
        indices = self._nms(boxes_xyxy, scores, self.iou_threshold)
        if len(indices) == 0:
            return None

        boxes_nms = boxes_xyxy[indices]
        self._last_num_persons = len(indices)
        frame_size = self._last_frame_size
        if len(indices) > 1:
            from core.vision_quality import pick_person_index
            pick = pick_person_index(
                boxes_nms, self._track_bbox, frame_size,
                pick_mode=getattr(self, '_pick_mode', 'default'),
            )
            best = int(indices[pick])
        else:
            best = int(indices[0])

        box = boxes_xyxy[best]
        score = float(scores[best])
        kpts = kpts_raw[best]

        ratio = meta['ratio']
        pad_x, pad_y = meta['pad']
        oh, ow = meta['orig_hw']

        def to_orig_xy(x, y):
            x = (x - pad_x) / ratio
            y = (y - pad_y) / ratio
            return float(np.clip(x, 0, ow - 1)), float(np.clip(y, 0, oh - 1))

        box_orig = [
            (box[0] - pad_x) / ratio,
            (box[1] - pad_y) / ratio,
            (box[2] - pad_x) / ratio,
            (box[3] - pad_y) / ratio,
        ]

        keypoints_2d = {}
        for idx, name in self.KEYPOINT_NAMES.items():
            x, y, kc = kpts[idx]
            if not (np.isfinite(x) and np.isfinite(y) and np.isfinite(kc)):
                continue
            ox, oy = to_orig_xy(float(x), float(y))
            if not (np.isfinite(ox) and np.isfinite(oy)):
                continue
            keypoints_2d[name] = {
                'x': ox,
                'y': oy,
                'conf': float(kc),
            }

        if not keypoints_2d:
            return None

        return {
            'keypoints_2d': keypoints_2d,
            'bbox': [float(v) for v in box_orig],
            'person_conf': score,
            'num_persons': self._last_num_persons,
            'inference_ms': round(self._inference_time, 1),
        }

    @staticmethod
    def _xywh2xyxy(boxes: np.ndarray) -> np.ndarray:
        out = np.empty_like(boxes)
        out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
        out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
        return out

    @staticmethod
    def _nms(
        boxes: np.ndarray,
        scores: np.ndarray,
        iou_thres: float,
    ) -> List[int]:
        if len(boxes) == 0:
            return []
        x1, y1, x2, y2 = boxes.T
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = int(order[0])
            keep.append(i)
            if order.size == 1:
                break
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            inds = np.where(iou <= iou_thres)[0]
            order = order[inds + 1]
        return keep

    def get_diagnostics(self) -> dict:
        return {
            'backend': 'rknn',
            'model_path': self.model_path,
            'imgsz': self.imgsz,
            'frame_count': self._frame_count,
            'last_inference_ms': round(self._inference_time, 1),
        }
