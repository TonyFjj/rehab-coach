"""
YOLOv8-Pose 骨骼关键点检测
对单张图像检测17个人体关键点
"""

import time
import numpy as np
from typing import Dict, List, Optional, Tuple

from core.vision_quality import pick_person_index
from core.pose_stabilizer import stabilize_supine_legs

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False
    YOLO = None


class PoseEstimator:
    """
    基于YOLOv8-Pose的人体骨骼关键点检测

    YOLOv8-Pose的17个关键点定义（COCO格式）：
    0:  nose           鼻子
    1:  left_eye       左眼
    2:  right_eye      右眼
    3:  left_ear       左耳
    4:  right_ear      右耳
    5:  left_shoulder   左肩
    6:  right_shoulder  右肩
    7:  left_elbow     左肘
    8:  right_elbow    右肘
    9:  left_wrist     左手腕
    10: right_wrist    右手腕
    11: left_hip       左髋
    12: right_hip      右髋
    13: left_knee      左膝
    14: right_knee     右膝
    15: left_ankle     左踝
    16: right_ankle    右踝
    """

    # 关键点索引→名称映射
    KEYPOINT_NAMES = {
        0: 'nose',
        1: 'left_eye', 2: 'right_eye',
        3: 'left_ear', 4: 'right_ear',
        5: 'left_shoulder', 6: 'right_shoulder',
        7: 'left_elbow', 8: 'right_elbow',
        9: 'left_wrist', 10: 'right_wrist',
        11: 'left_hip', 12: 'right_hip',
        13: 'left_knee', 14: 'right_knee',
        15: 'left_ankle', 16: 'right_ankle',
    }

    # 我们重点关注的康复相关关键点
    REHAB_KEYPOINTS = [
        5, 6,    # 肩
        7, 8,    # 肘
        9, 10,   # 腕
        11, 12,  # 髋
        13, 14,  # 膝
        15, 16,  # 踝
    ]

    def __init__(
        self,
        model_path: str = 'yolov8n-pose.pt',
        conf_threshold: float = 0.5,
        device: str = 'cpu',
        simulate: bool = False,
        inference_imgsz: int = 640,
    ):
        """
        Args:
            model_path: YOLOv8-Pose模型路径
                - 'yolov8n-pose.pt': nano版，速度快，精度一般
                - 'yolov8s-pose.pt': small版，推荐RK3588使用
                - 'yolov8m-pose.pt': medium版，精度更高但更慢
            conf_threshold: 检测置信度阈值
            device: 推理设备 ('cpu', '0'=GPU0, 'rknn'=RK3588 NPU)
            simulate: 模拟模式
        """
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.device = device
        self.simulate = simulate
        self.inference_imgsz = int(inference_imgsz)

        self._model = None
        self._rknn_backend = None
        self._backend = 'simulate'
        self._inference_time = 0.0
        self._frame_count = 0
        self._last_num_persons = 0
        self._track_bbox: Optional[list] = None
        self._last_frame_size: Optional[tuple] = None
        self._last_valid_result: Optional[Dict] = None
        self._last_valid_left: Optional[Dict] = None
        self._last_valid_right: Optional[Dict] = None
        self._smooth_kpts_prev: Optional[Dict[str, dict]] = None
        self._pick_mode: str = 'default'

        if not simulate:
            self._load_model()

    def _use_rknn(self) -> bool:
        return (
            self.device == 'rknn'
            or str(self.model_path).lower().endswith('.rknn')
        )

    def _load_model(self):
        """加载 YOLOv8-Pose（Ultralytics .pt 或 RKNN .rknn）"""
        if self._use_rknn():
            self._load_rknn()
            return
        self._load_ultralytics()

    def _load_rknn(self):
        try:
            from .pose_rknn import RknnPoseBackend
            print(f"[Pose] RKNN 加载: {self.model_path}")
            self._rknn_backend = RknnPoseBackend(
                model_path=self.model_path,
                imgsz=self.inference_imgsz,
                conf_threshold=self.conf_threshold,
            )
            self._backend = 'rknn'
            self.device = 'rknn'
            print("[Pose] RKNN 模型就绪")
        except Exception as e:
            print(f"[Pose] RKNN 加载失败: {e}")
            print("[Pose] 切换到模拟模式")
            self.simulate = True
            self._backend = 'simulate'

    def _load_ultralytics(self):
        if not HAS_YOLO:
            print("[Pose] ultralytics未安装，姿态检测不可用")
            print("[Pose] 安装命令: pip install ultralytics")
            print("[Pose] 切换到模拟模式")
            self.simulate = True
            return

        try:
            print(f"[Pose] 加载模型: {self.model_path}")
            self._model = YOLO(self.model_path)
            self._backend = 'ultralytics'
            print(f"[Pose] 模型加载成功, 设备: {self.device}")

            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            self._model.predict(dummy, verbose=False)
            print("[Pose] 模型预热完成")

        except Exception as e:
            print(f"[Pose] 模型加载失败: {e}")
            print("[Pose] 切换到模拟模式")
            self.simulate = True
            self._backend = 'simulate'

    def _finalize_track_result(
        self, result: Optional[Dict], side: str = 'mono'
    ) -> Optional[Dict]:
        """锁定主用户后，拒绝跳到 IoU 过低的其他人；短时保持上一帧骨架。"""
        last_valid = (
            self._last_valid_left if side == 'left'
            else self._last_valid_right if side == 'right'
            else self._last_valid_result
        )

        if result is None:
            if self._track_bbox and last_valid:
                held = dict(last_valid)
                held['track_held'] = True
                return held
            return None

        if self._track_bbox and result.get('bbox'):
            from core.vision_quality import track_bbox_match_iou, TRACK_IOU_LOOSE
            iou = track_bbox_match_iou(result['bbox'], self._track_bbox)
            if iou < TRACK_IOU_LOOSE:
                if last_valid:
                    held = dict(last_valid)
                    held['track_held'] = True
                    return held
                return None

        k2d = result.get('keypoints_2d')
        if k2d:
            result = dict(result)
            if self._pick_mode == 'supine_bed':
                smoothed = stabilize_supine_legs(k2d, self._smooth_kpts_prev)
                result['keypoints_2d'] = smoothed
                self._smooth_kpts_prev = smoothed
            else:
                result['keypoints_2d'] = {
                    k: dict(v) for k, v in k2d.items()
                }

        if side == 'left':
            self._last_valid_left = result
        elif side == 'right':
            self._last_valid_right = result
        else:
            self._last_valid_result = result
        return result

    def set_track_bbox(self, bbox: Optional[list]):
        """预检通过后锁定主用户 bbox，多人场景优先跟踪同一人。"""
        self._track_bbox = list(bbox) if bbox else None
        if not bbox:
            self._last_valid_result = None
            self._last_valid_left = None
            self._last_valid_right = None
            self._smooth_kpts_prev = None
        if self._rknn_backend is not None and hasattr(
            self._rknn_backend, 'set_track_bbox'
        ):
            self._rknn_backend.set_track_bbox(bbox)

    def set_pick_mode(self, mode: str):
        """default | supine_bed — 卧床 L1 优先选躺卧者而非站立护理者。"""
        self._pick_mode = mode if mode in ('default', 'supine_bed') else 'default'
        if self._rknn_backend is not None and hasattr(
            self._rknn_backend, 'set_pick_mode'
        ):
            self._rknn_backend.set_pick_mode(self._pick_mode)

    @property
    def last_num_persons(self) -> int:
        return self._last_num_persons

    def _pick_person_index(self, boxes_xyxy) -> int:
        """从多个检测框中选择主用户索引。"""
        if boxes_xyxy is None or len(boxes_xyxy) == 0:
            self._last_num_persons = 0
            return 0
        n = len(boxes_xyxy)
        self._last_num_persons = n
        if n == 1:
            return 0
        if self._track_bbox:
            arr = np.asarray(boxes_xyxy)
            return pick_person_index(
                arr, self._track_bbox, self._last_frame_size,
                pick_mode=self._pick_mode,
            )
        if self._last_frame_size:
            arr = np.asarray(boxes_xyxy)
            return pick_person_index(
                arr, None, self._last_frame_size,
                pick_mode=self._pick_mode,
            )
        areas = []
        for box in boxes_xyxy:
            x1, y1, x2, y2 = box
            areas.append((x2 - x1) * (y2 - y1))
        return int(np.argmax(areas))

    def detect(
        self, image: np.ndarray
    ) -> Optional[Dict[str, Dict]]:
        """
        对单张图像进行姿态检测

        Args:
            image: BGR格式图像 (H, W, 3)

        Returns:
            检测结果字典，如果未检测到人则返回None
            {
                'keypoints_2d': {
                    'left_shoulder': {'x': 320, 'y': 180, 'conf': 0.92},
                    'right_shoulder': {'x': 380, 'y': 175, 'conf': 0.89},
                    ...
                },
                'bbox': [x1, y1, x2, y2],
                'person_conf': 0.95,
                'inference_ms': 12.5,
            }
        """
        if self.simulate:
            return self._detect_simulate(image)

        if image is not None and len(image.shape) >= 2:
            self._last_frame_size = (image.shape[1], image.shape[0])

        if self._backend == 'rknn' and self._rknn_backend:
            return self._finalize_track_result(self._rknn_backend.detect(image))

        if self._model is None:
            return None

        try:
            start = time.time()
            results = self._model.predict(
                image,
                conf=self.conf_threshold,
                verbose=False,
                device=self.device,
                imgsz=self.inference_imgsz,
            )
            self._inference_time = (time.time() - start) * 1000
            self._frame_count += 1
            return self._parse_yolo_result(results[0] if results else None)

        except Exception as e:
            print(f"[Pose] 检测失败: {e}")
            return None

    def detect_stereo(
        self,
        left: np.ndarray,
        right: np.ndarray,
    ):
        """
        左右图批量推理（比两次 detect 更快）。
        Returns:
            (kpts_left, kpts_right) 未检出时为 None
        """
        if self.simulate:
            return self._detect_simulate(left), self._detect_simulate(right)

        if self._backend == 'rknn' and self._rknn_backend:
            kl, kr = self._rknn_backend.detect_stereo(left, right)
            return (
                self._finalize_track_result(kl, side='left'),
                self._finalize_track_result(kr, side='right'),
            )

        if self._model is None:
            return None, None

        try:
            start = time.time()
            results = self._model.predict(
                [left, right],
                conf=self.conf_threshold,
                verbose=False,
                device=self.device,
                imgsz=self.inference_imgsz,
            )
            self._inference_time = (time.time() - start) * 1000
            self._frame_count += 1
            kpts_l = self._parse_yolo_result(
                results[0] if len(results) > 0 else None
            )
            kpts_r = self._parse_yolo_result(
                results[1] if len(results) > 1 else None
            )
            return kpts_l, kpts_r
        except Exception as e:
            print(f"[Pose] 双目检测失败: {e}")
            return None, None

    def _parse_yolo_result(self, result) -> Optional[Dict]:
        if result is None or result.keypoints is None:
            return None
        if len(result.keypoints.data) == 0:
            return None

        boxes_xyxy = None
        if result.boxes is not None and len(result.boxes) > 0:
            boxes_xyxy = result.boxes.xyxy.cpu().numpy()
        best_idx = self._pick_person_index(boxes_xyxy) if boxes_xyxy is not None else 0
        if boxes_xyxy is not None:
            best_idx = min(best_idx, len(boxes_xyxy) - 1)

        kpts = result.keypoints.data[best_idx].cpu().numpy()
        keypoints_2d = {}
        for idx, name in self.KEYPOINT_NAMES.items():
            if idx < len(kpts):
                x, y, conf = kpts[idx]
                keypoints_2d[name] = {
                    'x': float(x),
                    'y': float(y),
                    'conf': float(conf),
                }

        bbox = None
        person_conf = 0.0
        if result.boxes is not None and len(result.boxes) > best_idx:
            bbox = result.boxes.xyxy[best_idx].cpu().numpy().tolist()
            person_conf = float(result.boxes.conf[best_idx].cpu().numpy())

        parsed = {
            'keypoints_2d': keypoints_2d,
            'bbox': bbox,
            'person_conf': person_conf,
            'num_persons': self._last_num_persons,
            'inference_ms': round(self._inference_time, 1),
        }
        return self._finalize_track_result(parsed)

    def _detect_simulate(
        self, image: np.ndarray
    ) -> Dict:
        """模拟检测：返回假关键点数据"""
        h, w = image.shape[:2] if image is not None else (480, 640)

        # 模拟一个站立姿势的人
        simulated_kpts = {
            'nose':             (w * 0.50, h * 0.15),
            'left_eye':         (w * 0.48, h * 0.13),
            'right_eye':        (w * 0.52, h * 0.13),
            'left_ear':         (w * 0.45, h * 0.14),
            'right_ear':        (w * 0.55, h * 0.14),
            'left_shoulder':    (w * 0.40, h * 0.28),
            'right_shoulder':   (w * 0.60, h * 0.28),
            'left_elbow':       (w * 0.35, h * 0.42),
            'right_elbow':      (w * 0.65, h * 0.42),
            'left_wrist':       (w * 0.33, h * 0.55),
            'right_wrist':      (w * 0.67, h * 0.55),
            'left_hip':         (w * 0.43, h * 0.55),
            'right_hip':        (w * 0.57, h * 0.55),
            'left_knee':        (w * 0.42, h * 0.72),
            'right_knee':       (w * 0.58, h * 0.72),
            'left_ankle':       (w * 0.41, h * 0.90),
            'right_ankle':      (w * 0.59, h * 0.90),
        }

        # 添加微小随机抖动模拟真实检测
        keypoints_2d = {}
        for name, (x, y) in simulated_kpts.items():
            noise_x = np.random.normal(0, 2)
            noise_y = np.random.normal(0, 2)
            keypoints_2d[name] = {
                'x': float(x + noise_x),
                'y': float(y + noise_y),
                'conf': float(np.random.uniform(0.75, 0.98)),
            }

        self._frame_count += 1
        self._inference_time = np.random.uniform(8, 15)

        return {
            'keypoints_2d': keypoints_2d,
            'bbox': [w * 0.3, h * 0.1, w * 0.7, h * 0.95],
            'person_conf': 0.92,
            'num_persons': 1,
            'inference_ms': round(self._inference_time, 1),
        }

    # COCO 骨架连线（索引对）
    _SKELETON_EDGES = (
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
        (5, 11), (6, 12), (11, 12),
        (11, 13), (13, 15), (12, 14), (14, 16),
        (0, 1), (0, 2), (1, 3), (2, 4),
    )

    def draw_keypoints(
        self, image: np.ndarray, keypoints_2d: Dict[str, Dict]
    ) -> np.ndarray:
        """在图像上绘制 2D 关键点（调试用）。"""
        if image is None or not HAS_CV2:
            return image
        out = image.copy()
        idx_to_pt = {}
        for idx, name in self.KEYPOINT_NAMES.items():
            kp = keypoints_2d.get(name)
            if not kp or kp.get('conf', 0) < 0.3:
                continue
            x, y = kp.get('x'), kp.get('y')
            if x is None or y is None:
                continue
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            pt = (int(x), int(y))
            idx_to_pt[idx] = pt
            cv2.circle(out, pt, 4, (0, 255, 0), -1)

        for i, j in self._SKELETON_EDGES:
            if i in idx_to_pt and j in idx_to_pt:
                cv2.line(out, idx_to_pt[i], idx_to_pt[j], (0, 255, 255), 2)
        return out

    def detect_batch(
        self, images: List[np.ndarray]
    ) -> List[Optional[Dict]]:
        """批量检测多张图像"""
        return [self.detect(img) for img in images]

    def get_diagnostics(self) -> dict:
        """获取诊断信息"""
        if self._backend == 'rknn' and self._rknn_backend:
            d = self._rknn_backend.get_diagnostics()
            d['simulate'] = self.simulate
            return d
        return {
            'backend': self._backend,
            'model_path': self.model_path,
            'device': self.device,
            'simulate': self.simulate,
            'frame_count': self._frame_count,
            'last_inference_ms': round(self._inference_time, 1),
            'avg_fps': round(
                1000.0 / max(self._inference_time, 1), 1
            ),
        }
