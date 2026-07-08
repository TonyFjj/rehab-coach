"""
视觉流水线
串联: 摄像头采集 → 姿态检测 → 双目三角测量 → 输出3D骨骼
对外提供一个统一的 get_skeleton_3d() 接口
"""

import time
import threading
import numpy as np
from typing import Dict, Optional, Callable

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from .camera_manager import CameraManager
from .pose_estimator import PoseEstimator
from .stereo_3d import StereoTriangulator


class VisionPipeline:
    """
    视觉处理流水线

    数据流：
    双目摄像头 → 左右图像 → YOLOv8-Pose检测(各一次)
    → 双目三角测量 → 3D骨骼关键点 → 送往融合引擎

    可以独立线程运行，通过回调输出结果
    """

    def __init__(
        self,
        camera_config: dict = None,
        pose_model: str = 'yolov8n-pose.pt',
        simulate: bool = False
    ):
        """
        Args:
            camera_config: 摄像头配置字典
            pose_model: YOLOv8-Pose模型路径
            simulate: 模拟模式（不需要真实摄像头和模型）
        """
        self.simulate = simulate

        # 默认摄像头配置
        if camera_config is None:
            camera_config = {
                'device_id': 0,
                'width': 2560,
                'height': 720,
                'fps': 30,
                'mode': 'single_device',
                'camera_model': 'AR0144',
            }

        # 创建子模块
        self.camera = CameraManager(
            device_id=camera_config.get('device_id', 0),
            width=camera_config.get('width', 2560),
            height=camera_config.get('height', 720),
            fps=camera_config.get('fps', 30),
            mode=camera_config.get('mode', 'single_device'),
            camera_model=camera_config.get('camera_model', 'AR0144'),
            calibration_file=camera_config.get(
                'calibration_file', 'config/stereo_calib.json'
            ),
            simulate=simulate,
            rectify=camera_config.get('rectify', True),
            rectify_alpha=float(camera_config.get('rectify_alpha', 1.0)),
            rectify_crop=bool(camera_config.get('rectify_crop', True)),
            rectify_preview=bool(camera_config.get('rectify_preview', False)),
            auto_detect=bool(camera_config.get('auto_detect', False)),
            max_probe=int(camera_config.get('max_probe', 32)),
            device_path=str(camera_config.get('device_path', '') or ''),
            open_retries=int(camera_config.get('open_retries', 3)),
            hub_warmup_sec=float(camera_config.get('hub_warmup_sec', 1.0)),
        )

        pose_device = camera_config.get('pose_device', 'cpu')
        if camera_config.get('pose_backend') == 'rknn':
            pose_device = 'rknn'

        self.pose_estimator = PoseEstimator(
            model_path=pose_model,
            conf_threshold=0.5,
            device=pose_device,
            simulate=simulate,
            inference_imgsz=int(camera_config.get('inference_imgsz', 640)),
        )
        self._pose_mode = camera_config.get('pose_mode', 'both')
        self._pose_stride = max(1, int(camera_config.get('pose_stride', 1)))

        self.stereo = StereoTriangulator(
            calib_params=(
                self.camera.calib_params
                if self.camera.calibrated
                else None
            ),
            simulate=simulate,
        )

        # 运行控制
        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._pipeline_thread: Optional[threading.Thread] = None
        self._target_fps = camera_config.get('fps', 30)

        # 回调
        self._on_skeleton_3d: Optional[Callable] = None
        self._on_frame: Optional[Callable] = None

        # 最新结果缓存
        self._latest_result: Optional[Dict] = None
        self._latest_left_frame = None
        self._latest_right_frame = None
        self._lock = threading.Lock()

        # 统计
        self._frame_count = 0
        self._total_latency = 0.0
        self._fps = 0.0
        self._capture_fps = 0.0
        self._last_infer_ms = 0.0
        self._cached_kpts_left = None
        self._cached_kpts_right = None
        self._loop_counter = 0
        self._patient_bbox: Optional[list] = None

    # ==================== 主用户锁定 ====================

    def lock_patient(self, bbox: list, reason: str = ''):
        """锁定画面中的主用户（评估/训练开始前调用）。"""
        if not bbox or len(bbox) < 4:
            return
        self._patient_bbox = [float(v) for v in bbox[:4]]
        self.pose_estimator.set_track_bbox(self._patient_bbox)
        if reason and reason != 'track':
            print(f'[Vision] 已锁定主用户 bbox ({reason})')

    def clear_patient_lock(self):
        self._patient_bbox = None
        self.pose_estimator.set_track_bbox(None)

    def set_patient_pick_mode(self, mode: str = 'default'):
        """default=常规；supine_bed=L1 卧床，优先跟踪躺卧者。"""
        if hasattr(self.pose_estimator, 'set_pick_mode'):
            self.pose_estimator.set_pick_mode(mode)

    def _copy_keypoints(self, kpts: Optional[Dict]) -> Dict:
        if not kpts:
            return {}
        return {name: dict(pt) for name, pt in kpts.items()}

    def _render_stereo_preview(
        self,
        left_snap,
        right_snap,
        kpts_l: Dict,
        kpts_r: Dict,
    ):
        """在与检测同一帧上绘制骨架，避免预览线程二次绑定导致错位。"""
        pe = self.pose_estimator
        vis_l = (
            pe.draw_keypoints(left_snap.copy(), kpts_l)
            if kpts_l else left_snap.copy()
        )
        if right_snap is None:
            return vis_l, None, vis_l

        vis_r = (
            pe.draw_keypoints(right_snap.copy(), kpts_r)
            if kpts_r else right_snap.copy()
        )
        combined = np.hstack([vis_l, vis_r])
        if HAS_CV2:
            mid = vis_l.shape[1]
            cv2.line(
                combined, (mid, 0), (mid, combined.shape[0]),
                (0, 0, 255), 2,
            )
        return vis_l, vis_r, combined

    def _sync_preview_bundle(
        self,
        left_snap,
        right_snap,
        kpts_left,
        kpts_right,
    ):
        """
        跟踪保持(track_held)时，关键点来自上一帧，须复用同一帧画面，
        否则会出现骨架相对人体整体偏移。
        """
        held = bool(
            (kpts_left and kpts_left.get('track_held'))
            or (kpts_right and kpts_right.get('track_held'))
        )
        prev = None
        if held:
            with self._lock:
                prev = self._latest_result
        if held and prev:
            # 任一侧 track_held 时，必须整包复用上一帧（画面+关键点），
            # 不能左右混用新旧帧，否则会出现「左图右偏、右图左偏」。
            left_snap = prev.get('preview_left', left_snap)
            right_snap = prev.get('preview_right', right_snap)
            kpts_l = self._copy_keypoints(prev.get('keypoints_2d_left') or {})
            kpts_r = self._copy_keypoints(prev.get('keypoints_2d_right') or {})
        else:
            kpts_l = self._copy_keypoints(
                kpts_left['keypoints_2d'] if kpts_left else {}
            )
            kpts_r = self._copy_keypoints(
                kpts_right['keypoints_2d'] if kpts_right else {}
            )
        vis_l, vis_r, combined = self._render_stereo_preview(
            left_snap, right_snap, kpts_l, kpts_r,
        )
        return left_snap, right_snap, kpts_l, kpts_r, vis_l, vis_r, combined

    def _refresh_patient_lock(self, bbox: list):
        """检测成功后平滑更新锁定框（不重复打印日志）。"""
        if self._patient_bbox is None:
            return
        if not bbox or len(bbox) < 4:
            return
        bbox = [float(v) for v in bbox[:4]]
        from core.vision_quality import bbox_iou, TRACK_IOU_REFRESH
        iou = bbox_iou(bbox, self._patient_bbox)
        if iou < TRACK_IOU_REFRESH:
            return
        merged = [
            0.7 * self._patient_bbox[i] + 0.3 * bbox[i]
            for i in range(4)
        ]
        self._patient_bbox = merged
        self.pose_estimator.set_track_bbox(self._patient_bbox)

    # ==================== 回调设置 ====================

    def set_callbacks(
        self,
        on_skeleton_3d: Callable = None,
        on_frame: Callable = None
    ):
        """
        设置回调

        Args:
            on_skeleton_3d: 3D骨骼结果回调
                (skeleton_3d: dict, timestamp: float) -> None
            on_frame: 原始帧回调（供Qt显示用）
                (left: ndarray, right: ndarray) -> None
        """
        self._on_skeleton_3d = on_skeleton_3d
        self._on_frame = on_frame

    # ==================== 启动/停止 ====================

    def start(self) -> bool:
        """
        启动视觉流水线

        Returns:
            是否成功启动
        """
        if self._running:
            return True

        # 打开摄像头
        if not self.camera.open():
            print("[Vision] 摄像头打开失败")
            return False

        self._running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="vision-capture",
        )
        self._pipeline_thread = threading.Thread(
            target=self._pipeline_loop,
            daemon=True,
            name="vision-pipeline",
        )
        self._capture_thread.start()
        self._pipeline_thread.start()

        print(
            f"[Vision] 视觉流水线已启动 "
            f"(mode={self._pose_mode}, imgsz={self.pose_estimator.inference_imgsz}, "
            f"stride={self._pose_stride})"
        )
        return True

    def stop(self):
        """停止视觉流水线"""
        self._running = False

        for th in (self._capture_thread, self._pipeline_thread):
            if th and th.is_alive():
                th.join(timeout=3.0)

        self.camera.close()
        print("[Vision] 视觉流水线已停止")

    # ==================== 主循环 ====================

    def _capture_loop(self):
        """独立采集线程：不被 YOLO 阻塞，保证 Cam FPS 接近摄像头上限。"""
        cap_counter = 0
        cap_t0 = time.time()

        while self._running:
            ret, left, right = self.camera.read()
            if not ret:
                time.sleep(0.005)
                continue

            with self._lock:
                self._latest_left_frame = left
                self._latest_right_frame = right

            cap_counter += 1
            now = time.time()
            if now - cap_t0 >= 1.0:
                self._capture_fps = cap_counter / (now - cap_t0)
                cap_counter = 0
                cap_t0 = now

    def _pipeline_loop(self):
        """推理线程：只读最新帧做 Pose，不拖慢采集。"""
        pipe_counter = 0
        pipe_t0 = time.time()

        while self._running:
            frame_start = time.time()
            self._loop_counter += 1

            with self._lock:
                left = self._latest_left_frame
                right = self._latest_right_frame

            if left is None or right is None:
                time.sleep(0.01)
                continue

            # 与本次推理绑定的画面快照，避免预览骨架与显示帧不同步导致错位
            left_snap = left.copy()
            right_snap = right.copy() if right is not None else None

            run_pose = (
                self._loop_counter % self._pose_stride == 0
                or self._cached_kpts_left is None
            )

            if not run_pose:
                time.sleep(0.005)
                continue

            if self._pose_mode == 'left_only':
                kpts_left = self.pose_estimator.detect(left_snap)
                kpts_right = None
            else:
                kpts_left, kpts_right = self.pose_estimator.detect_stereo(
                    left_snap, right_snap
                )

            if kpts_left is not None:
                self._cached_kpts_left = kpts_left
                if kpts_left.get('bbox'):
                    self._refresh_patient_lock(kpts_left['bbox'])
            if kpts_right is not None:
                self._cached_kpts_right = kpts_right
            self._last_infer_ms = self.pose_estimator._inference_time

            kpts_left = self._cached_kpts_left
            if kpts_left is None:
                time.sleep(0.01)
                continue

            kpts_right = self._cached_kpts_right
            if kpts_right is not None:
                kl = kpts_left['keypoints_2d']
                kr = kpts_right['keypoints_2d']
                if (
                    self.camera.rectify_enabled
                    and not self.camera.rectify_preview
                ):
                    kl = self.camera.map_keypoints_to_rectified(kl, 'left')
                    kr = self.camera.map_keypoints_to_rectified(kr, 'right')
                skeleton_3d = self.stereo.triangulate(kl, kr)
            else:
                skeleton_3d = {}

            (
                left_snap, right_snap, kpts_l, kpts_r,
                vis_l, vis_r, combined,
            ) = self._sync_preview_bundle(
                left_snap, right_snap, kpts_left, kpts_right,
            )

            now = time.time()
            latency = (now - frame_start) * 1000

            brightness_score = 1.0
            try:
                from core.vision_quality import analyze_brightness
                va_cfg = {}
                brightness_score, _ = analyze_brightness(left, va_cfg)
            except Exception:
                pass

            result = {
                'skeleton_3d': skeleton_3d,
                'keypoints_2d_left': kpts_l,
                'keypoints_2d_right': kpts_r,
                'preview_left': left_snap,
                'preview_right': right_snap,
                'preview_left_vis': vis_l,
                'preview_right_vis': vis_r,
                'preview_combined': combined,
                'skeleton_3d_count': len(skeleton_3d),
                'person_conf': kpts_left['person_conf'],
                'num_persons': int(kpts_left.get('num_persons') or 1),
                'bbox': kpts_left.get('bbox'),
                'brightness_score': brightness_score,
                'inference_ms_left': kpts_left.get('inference_ms', 0),
                'inference_ms_right': (
                    kpts_right.get('inference_ms', 0) if kpts_right else 0
                ),
                'total_latency_ms': round(latency, 1),
                'timestamp': now,
                'frame_number': self._frame_count,
            }

            with self._lock:
                self._latest_result = result

            self._frame_count += 1
            self._total_latency += latency

            pipe_counter += 1
            if now - pipe_t0 >= 1.0:
                self._fps = pipe_counter / (now - pipe_t0)
                pipe_counter = 0
                pipe_t0 = now

            if self._on_skeleton_3d:
                self._on_skeleton_3d(skeleton_3d, now)

            if self._on_frame:
                self._on_frame(left, right)

    # ==================== 单次处理（非线程模式） ====================

    def process_one_frame(self) -> Optional[Dict]:
        """
        处理单帧（不启动后台线程，手动调用）

        Returns:
            3D骨骼结果字典，失败返回None
        """
        ret, left, right = self.camera.read()
        if not ret:
            return None

        kpts_left = self.pose_estimator.detect(left)
        kpts_right = self.pose_estimator.detect(right)

        if kpts_left is None or kpts_right is None:
            return None

        kl = kpts_left['keypoints_2d']
        kr = kpts_right['keypoints_2d']
        if self.camera.rectify_enabled and not self.camera.rectify_preview:
            kl = self.camera.map_keypoints_to_rectified(kl, 'left')
            kr = self.camera.map_keypoints_to_rectified(kr, 'right')
        skeleton_3d = self.stereo.triangulate(kl, kr)

        return {
            'skeleton_3d': skeleton_3d,
            'keypoints_2d_left': kpts_left['keypoints_2d'],
            'keypoints_2d_right': kpts_right['keypoints_2d'],
            'timestamp': time.time(),
        }

    # ==================== 数据获取 ====================

    def get_latest_skeleton(self) -> Optional[Dict]:
        """获取最新的3D骨骼数据（线程安全）"""
        with self._lock:
            return self._latest_result

    def get_latest_frames(self):
        """获取最新的左右帧图像（副本，避免与采集线程竞态）。"""
        with self._lock:
            left = self._latest_left_frame
            right = self._latest_right_frame
        if left is not None:
            left = left.copy()
        if right is not None:
            right = right.copy()
        return left, right

    # ==================== 标定快捷接口 ====================

    def calibrate(
        self,
        chess_size=(9, 6),
        square_size=25.0,
        num_frames=20
    ) -> bool:
        """
        执行双目标定

        标定完成后自动更新三角测量器的参数
        """
        if not self.camera.is_opened():
            if not self.camera.open():
                print("[Vision] 打开摄像头失败，无法标定")
                return False

        success = self.camera.calibrate_stereo(
            chess_size=chess_size,
            square_size=square_size,
            num_frames=num_frames,
        )

        if success:
            self.stereo.load_calibration(self.camera.calib_params)
            print("[Vision] 标定完成，三角测量器已更新")

        return success

    # ==================== 诊断 ====================

    def get_diagnostics(self) -> dict:
        """获取视觉流水线诊断信息"""
        avg_latency = (
            self._total_latency / max(self._frame_count, 1)
        )

        return {
            'running': self._running,
            'fps': round(self._fps, 1),
            'pipeline_fps': round(self._fps, 1),
            'capture_fps': round(self._capture_fps, 1),
            'last_infer_ms': round(self._last_infer_ms, 1),
            'pose_mode': self._pose_mode,
            'frame_count': self._frame_count,
            'avg_latency_ms': round(avg_latency, 1),
            'simulate': self.simulate,
            'camera': self.camera.get_diagnostics(),
            'pose_estimator': self.pose_estimator.get_diagnostics(),
            'stereo': self.stereo.get_diagnostics(),
        }
