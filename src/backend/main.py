"""
康复训练系统主入口
整合所有模块，提供完整的训练流程控制
支持模拟模式运行（无需硬件）
"""

import os
import sys
import time
import argparse
import threading
from typing import Optional

import yaml
import numpy as np

# 将项目根目录加入路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_ROOT))
sys.path.insert(0, PROJECT_ROOT)


def _resolve_repo_path(rel: str) -> str:
    """将相对路径解析为仓库根目录下的绝对路径。"""
    if os.path.isabs(rel):
        return rel
    return os.path.join(REPO_ROOT, rel)

from core.scoring_engine import HealthScoringEngine
from core.action_state_machine import ActionStateMachine, ActionState
from core.correction_engine import CorrectionEngine
from core.dynamic_updater import DynamicScoreUpdater
from core.level_manager import LevelManager
from core.training_blocks import (
    TrainingSessionLog,
    get_block_info,
    normalize_region,
    training_allows_companion,
)
from core.vision_assessment import (
    VisionAssessmentMonitor,
    apply_vision_to_imu_result,
)

from llm.prompt_builder import PromptBuilder
from llm.llm_inference import LLMInference, default_qwen_model_path
from llm.tts_engine import TTSEngine

from fusion.kalman_fusion import SensorFusionEngine

from interface.imu_interface import IMUInterface
from interface.imu_port_detect import resolve_imu_ports
from interface.qt_interface import QtInterface

from assessment_plan import (
    ACTION_TEXT,
    ACTION_TTS,
    ANALYZING_TEXT,
    ANALYZING_TTS,
    COLLECT_SECONDS,
    COLLECT_START_TTS,
    DATA_OK_TTS,
    DATA_WARN_TTS,
    DONE_TEXT,
    DONE_TTS,
    INTRO_TEXT,
    INTRO_TTS,
    PREPARE_AFTER_INSTRUCTION,
    PREP_SECONDS,
    PREP_TEXT,
    MOTION_TEXT,
    RAISE_HANDS_DELAY_SEC,
    RAISE_HANDS_TTS,
    SYNC_FAIL_TTS,
    TEST_ACTIONS,
    plan_for_qt,
)
from initial_assessment import InitialAssessment
from training_session import TrainingSession
from vision.vision_pipeline import VisionPipeline
from vision.camera_config_loader import (
    build_audio_runtime_config,
    build_camera_runtime_config,
    camera_yaml_path,
    is_rk3588_board,
    load_camera_yaml,
)


class RehabSystem:
    """
    康复训练系统主控制器

    管理所有子模块的生命周期和数据流
    """

    def __init__(
        self,
        config_path: str = None,
        simulate: bool = True,
        show_vision_debug: bool = False,
        use_rknn: bool = False,
    ):
        """
        Args:
            config_path: 配置文件目录路径
            simulate: 是否使用模拟模式（无硬件时设为True）
            show_vision_debug: 弹出 OpenCV 调试窗口（开发用，正式由 Qt 显示）
            use_rknn: 使用 RKNN NPU 姿态模型（RK3588）；Windows 开发请保持 False
        """
        self.simulate = simulate
        self.show_vision_debug = show_vision_debug
        self.use_rknn = use_rknn
        self._debug_thread = None

        # 配置路径
        if config_path is None:
            config_path = os.path.join(PROJECT_ROOT, 'config')
        self.config_path = config_path
        self.actions_path = os.path.join(config_path, 'actions')
        self._camera_yaml_path = camera_yaml_path(config_path)
        _, self._camera_yaml_raw = load_camera_yaml(config_path)

        # 加载评分配置
        scoring_config_path = os.path.join(config_path, 'scoring_config.yaml')
        self.scoring_config = self._load_yaml(scoring_config_path)

        print("=" * 60)
        print("   智能康复训练系统 v1.0")
        print("   模式:", "模拟（无硬件）" if simulate else "真实硬件")
        print("=" * 60)

        # ========== 初始化所有模块 ==========

        # 1. 评分引擎
        self.scoring_engine = HealthScoringEngine(
            config=self.scoring_config
        )
        print("[✓] 评分引擎就绪")

        # 2. 等级管理器
        self.level_manager = LevelManager(
            config_dir=self.actions_path
        )
        self._session_log = TrainingSessionLog()
        self._last_training_body_region = 'upper'
        print("[✓] 等级管理器就绪")

        # 3. 传感器融合
        self.fusion_engine = SensorFusionEngine()
        print("[✓] 传感器融合引擎就绪")

        # 4. LLM推理（有 .rkllm 模型时自动启用 Qwen RKLLM）
        llm_model = default_qwen_model_path(PROJECT_ROOT)
        llm_simulate = not os.path.isfile(llm_model)
        self.llm = LLMInference(
            model_path=llm_model,
            simulate=llm_simulate,
            project_root=PROJECT_ROOT,
        )
        llm_mode = "模拟" if self.llm.simulate else "Qwen RKLLM"
        print(f"[✓] LLM推理引擎就绪（{llm_mode}）")

        # 5. TTS语音（配置见 camera_config*.yaml → audio 段）
        self._audio_config = build_audio_runtime_config(
            self._camera_yaml_raw, PROJECT_ROOT
        )
        self.tts = TTSEngine(
            backend=self._audio_config.get('backend', 'auto'),
            simulate=False,
            rate=self._audio_config.get('rate', 160),
            volume=self._audio_config.get('volume', 0.9),
            output_dir=self._audio_config.get(
                'output_dir', os.path.join(PROJECT_ROOT, 'tts_cache')
            ),
            model_dir=self._audio_config.get('tts_model_dir'),
            alsa_device=self._audio_config.get('alsa_device'),
        )
        print("[✓] TTS语音引擎就绪")
        self.tts.precache_assessment(background=True)

        # 6. Prompt构建器
        self.prompt_builder = PromptBuilder(patient_name="")

        # 7. IMU接口
        self._imu_config = self._load_yaml(
            os.path.join(self.config_path, 'imu_config.yaml')
        )
        imu_data_dir = _resolve_repo_path(
            self._imu_config.get('data_dir', 'data/imu')
        )
        os.makedirs(imu_data_dir, exist_ok=True)
        stream_rel = self._imu_config.get(
            'stream_path', 'data/imu/imu_stream.txt'
        )
        stream_path = _resolve_repo_path(stream_rel)
        imu_mode = 'simulate' if simulate else self._imu_config.get(
            'mode', 'dual_serial'
        )
        dual_ports = resolve_imu_ports(
            self._imu_config.get('ports'),
            verbose=True,
        )
        self.imu_interface = IMUInterface(
            mode=imu_mode,
            baudrate=int(self._imu_config.get('baudrate', 115200)),
            txt_path={
                'imu_left': os.path.join(imu_data_dir, 'imu_left.txt'),
                'imu_right': os.path.join(imu_data_dir, 'imu_right.txt'),
            },
            txt_follow=True,
            simulate=simulate,
            dual_ports=dual_ports,
            stream_path=stream_path,
            write_stream_file=bool(
                self._imu_config.get('write_stream_file', True)
            ),
        )
        self.imu_interface.set_callbacks(
            on_imu_data=self._on_imu_data,
            on_imu_status=self._on_imu_status
        )
        print(f"[✓] IMU接口就绪 (mode={imu_mode}, L={dual_ports['left']}, R={dual_ports['right']})")

        # 7b. 摄像头 / 视觉流水线
        self.camera_config = self._build_camera_config()
        self._debug_max_width = int(
            self.camera_config.get('debug_max_width', 1280)
        )
        self._debug_max_height = int(
            self.camera_config.get('debug_max_height', 360)
        )
        pose_model, pose_device = self._resolve_pose_model()
        self.camera_config['pose_device'] = pose_device
        if pose_device == 'rknn':
            self.camera_config['pose_backend'] = 'rknn'
        self.vision_pipeline = VisionPipeline(
            camera_config=self.camera_config,
            pose_model=pose_model,
            simulate=simulate,
        )
        self.vision_pipeline.set_callbacks(
            on_skeleton_3d=self._on_skeleton_3d,
        )
        print("[✓] 视觉流水线就绪")

        # 8. Qt接口
        self.qt_interface = QtInterface(
            tcp_fallback_port=9002,
            simulate=simulate,
        )
        print("[✓] Qt通信接口就绪")

        # 应用左右手映射初始状态（来自 imu_config.yaml: lr_swap）
        # 放在 qt_interface 创建之后，避免 _on_imu_status 回调访问未初始化属性
        self.imu_interface.apply_lr_swap(
            bool(self._imu_config.get('lr_swap', False))
        )

        # ========== 运行时状态 ==========
        self.current_level = None
        self.current_score = None
        self._last_dimension_scores = {}
        self.dynamic_updater = None
        self.is_running = False
        self.is_training = False
        self._vision_frame_count = 0
        self._active_session: Optional[TrainingSession] = None
        self._training_thread: Optional[threading.Thread] = None
        self._assessment_thread: Optional[threading.Thread] = None
        self._assessment_collecting = False
        self._last_vision_assessment_summary = None
        va_cfg = self.scoring_config.get('vision_assessment', {})
        self._vision_assessment_monitor = VisionAssessmentMonitor(
            self.fusion_engine,
            vision_pipeline=self.vision_pipeline,
            config=va_cfg,
            on_live_update=self._push_vision_assessment_live,
        )
        self._vision_quality_buffer = []
        self._last_vision_quality = {}
        self._last_vision_tts_warn = 0.0
        self._allow_companion_in_frame = False

        self._imu_lr_calibrating = False

        # 注册Qt控制指令
        self._register_qt_commands()

    def _build_camera_config(self) -> dict:
        """从 camera_config.yaml（RK3588 自动用 .rk3588.yaml）加载。"""
        if is_rk3588_board():
            print(f"[Config] 板端配置: {self._camera_yaml_path}")
        return build_camera_runtime_config(
            self._camera_yaml_raw,
            PROJECT_ROOT,
            use_rknn=self.use_rknn,
        )

    def _resolve_pose_model(self):
        """
        Windows 默认根目录 yolov8n-pose.pt + ultralytics。
        RK3588: --rknn 或配置 pose_backend=rknn → models/yolov8n-pose.rknn。
        """
        vis = self._camera_yaml_raw.get('vision', {}) if self._camera_yaml_raw else {}
        ROOT_DIR = os.path.dirname(os.path.dirname(PROJECT_ROOT))

        use_rknn = self.use_rknn or vis.get('pose_backend') == 'rknn'
        if use_rknn:
            candidates = [
                os.path.join(ROOT_DIR, 'models', 'yolov8n-pose.rknn'),
                os.path.join(PROJECT_ROOT, 'yolov8n-pose.rknn'),
            ]
            custom = vis.get('pose_model', '')
            if custom:
                candidates.insert(
                    0,
                    custom if os.path.isabs(custom)
                    else os.path.join(ROOT_DIR, custom),
                )
            for path in candidates:
                if os.path.isfile(path):
                    print(f"[Pose] RKNN 模型: {path}")
                    return path, 'rknn'
            print("[WARNING] 未找到 .rknn，回退到 yolov8n-pose.pt（仅适合 Windows 开发）")
            use_rknn = False

        pt_candidates = [
            os.path.join(PROJECT_ROOT, 'yolov8n-pose.pt'),
            os.path.join(ROOT_DIR, 'models', 'yolov8n-pose.pt'),
        ]
        custom_pt = vis.get('pose_model', '')
        if custom_pt and not str(custom_pt).endswith('.rknn'):
            pt_candidates.insert(
                0,
                custom_pt if os.path.isabs(custom_pt)
                else os.path.join(ROOT_DIR, custom_pt),
            )
        for path in pt_candidates:
            if os.path.isfile(path):
                return path, 'cpu'
        return os.path.join(PROJECT_ROOT, 'yolov8n-pose.pt'), 'cpu'

    def _load_yaml(self, path: str) -> dict:
        """加载YAML配置文件"""
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        else:
            print(f"[WARNING] 配置文件不存在: {path}")
            return {}

    def _register_qt_commands(self):
        """注册Qt界面发来的控制指令"""
        self.qt_interface.register_command(
            'start_assessment', self._start_assessment_async
        )
        self.qt_interface.register_command(
            'start_training', self.run_training_session
        )
        self.qt_interface.register_command(
            'pause_training', self.pause_training
        )
        self.qt_interface.register_command(
            'resume_training', self.resume_training
        )
        self.qt_interface.register_command(
            'stop_training', self.stop_training
        )
        self.qt_interface.register_command(
            'end_training', self.stop_training
        )
        self.qt_interface.register_command(
            'confirm_upgrade', lambda p: self._handle_upgrade_confirm(p)
        )
        self.qt_interface.register_command(
            'request_status', lambda p: self._send_system_status()
        )
        self.qt_interface.register_command(
            'request_training_plan', self._send_training_plan
        )
        self.qt_interface.register_command(
            'request_assessment_plan', lambda p: self._send_assessment_plan()
        )
        self.qt_interface.register_command(
            'request_assessment_result', self._refresh_assessment_from_csv
        )
        self.qt_interface.register_command(
            'set_volume', self._set_tts_volume
        )
        self.qt_interface.register_command(
            'set_speed', self._set_tts_speed
        )
        self.qt_interface.register_command(
            'start_imu_calibration', self._start_imu_calibration
        )
        self.qt_interface.register_command(
            'finish_imu_calibration', self._finish_imu_calibration
        )
        self.qt_interface.register_command(
            'start_imu_assessment', self._start_imu_assessment_async
        )
        self.qt_interface.register_command(
            'start_imu_lr_calibration', self._start_imu_lr_calibration
        )

    def _start_imu_assessment_async(self, payload: dict = None):
        threading.Thread(
            target=self._run_imu_hardware_assessment,
            args=(payload,),
            daemon=True,
            name='imu-assessment',
        ).start()

    def _imu_status_payload(self) -> dict:
        diag = self.imu_interface.get_diagnostics()
        ports = diag.get('dual_ports') or diag.get('port')
        return {
            'mode': diag.get('mode'),
            'left_online': self.imu_interface.is_imu_connected('imu_left'),
            'right_online': self.imu_interface.is_imu_connected('imu_right'),
            'frame_count': diag.get('frame_count', 0),
            'calibrating': diag.get('calibrating', False),
            'lr_swap': self.imu_interface.get_lr_swap(),
            'ports': ports,
            'serial_errors': diag.get('serial_errors', {}),
        }

    def _push_imu_status_to_qt(self):
        self.qt_interface.send_system_status(
            status_text='IMU状态更新',
            imu=self._imu_status_payload(),
        )

    def _start_imu_calibration(self, payload: dict = None):
        duration = 3.0
        if payload and payload.get('duration'):
            try:
                duration = float(payload['duration'])
            except (TypeError, ValueError):
                pass
        self.imu_interface.start_calibration(duration)
        self.tts.speak('请保持双手自然下垂，不要移动，正在进行传感器校准。')
        self._push_imu_status_to_qt()

    def _finish_imu_calibration(self, payload: dict = None):
        if not self.imu_interface.is_calibration_complete():
            self.tts.speak('校准数据尚未采集完成，请再保持静止几秒。')
            return
        result = self.imu_interface.get_calibration_result()
        if result:
            for imu_id, info in result.items():
                bias = info.get('bias')
                if bias is not None and hasattr(bias, '__len__'):
                    self.fusion_engine.imu_bias[imu_id] = np.asarray(
                        bias[:3], dtype=np.float64
                    )
            self.tts.speak('传感器校准完成。')
        else:
            self.tts.speak('校准失败，请检查 IMU 连接后重试。')
        self._push_imu_status_to_qt()

    def _start_imu_lr_calibration(self, payload: dict = None):
        """左右手 IMU 映射校准（异步线程）。"""
        if self._imu_lr_calibrating:
            print('[IMU][LR] 校准已在进行中，忽略重复请求')
            return
        self._imu_lr_calibrating = True
        threading.Thread(
            target=self._run_imu_lr_calibration,
            args=(payload,),
            daemon=True,
            name='imu-lr-calibration',
        ).start()

    def _run_imu_lr_calibration(self, payload: dict = None):
        try:
            baseline_seconds = 1.5
            capture_seconds = 4.0
            min_samples = 40

            if not self.imu_interface._running:
                self.imu_interface.start()
                time.sleep(0.5)

            ports = self._resolved_imu_ports()
            print(
                f'[IMU][LR] 开始校准 L={ports["left"]} R={ports["right"]} '
                f'lr_swap={self.imu_interface.get_lr_swap()}'
            )

            self.qt_interface.send_system_status(
                status_text='IMU左右手校准开始',
                imu={
                    'lr_calibrating': True,
                    'lr_phase': 'baseline',
                    **self._imu_status_payload(),
                },
            )

            # 1) 基线：双手自然下垂
            self.imu_interface.start_lr_motion_capture()
            time.sleep(baseline_seconds)
            baseline = self.imu_interface.snapshot_lr_motion()
            self.imu_interface.reset_lr_motion_counters()

            # 2) 语音提示后采集抬手动作
            self.qt_interface.send_system_status(
                status_text='IMU左右手校准：请听语音提示',
                imu={
                    'lr_calibrating': True,
                    'lr_phase': 'prompt',
                    **self._imu_status_payload(),
                },
            )
            self.tts.speak_and_wait('请抬起左手')

            self.qt_interface.send_system_status(
                status_text='IMU左右手校准：采集中',
                imu={
                    'lr_calibrating': True,
                    'lr_phase': 'capturing',
                    **self._imu_status_payload(),
                },
            )
            time.sleep(capture_seconds)
            motion = self.imu_interface.stop_lr_motion_capture()

            pl = max(
                0.0,
                float(motion.get('port_left', 0.0))
                - float(baseline.get('port_left', 0.0)),
            )
            pr = max(
                0.0,
                float(motion.get('port_right', 0.0))
                - float(baseline.get('port_right', 0.0)),
            )
            nl = int(motion.get('port_left_samples', 0))
            nr = int(motion.get('port_right_samples', 0))

            print(
                f'[IMU][LR] 基线 L={baseline.get("port_left", 0):.3f} '
                f'R={baseline.get("port_right", 0):.3f} | '
                f'动作 L={pl:.3f}({nl}) R={pr:.3f}({nr})'
            )

            if nl < min_samples or nr < min_samples:
                self.tts.speak_and_wait(
                    '未收到足够 IMU 数据，请检查左右传感器连接后重试。'
                )
                self.qt_interface.send_system_status(
                    status_text='IMU左右手校准失败',
                    imu={
                        'lr_calibrating': False,
                        'lr_result': 'no_data',
                        'energy_left': pl,
                        'energy_right': pr,
                        'samples_left': nl,
                        'samples_right': nr,
                        **self._imu_status_payload(),
                    },
                )
                return

            max_e = max(pl, pr)
            min_e = max(min(pl, pr), 1e-6)
            if max_e / min_e < 1.25:
                self.tts.speak_and_wait('未检测到明显的抬手动作，请重试。')
                self.qt_interface.send_system_status(
                    status_text='IMU左右手校准未通过',
                    imu={
                        'lr_calibrating': False,
                        'lr_result': 'inconclusive',
                        'energy_left': pl,
                        'energy_right': pr,
                        **self._imu_status_payload(),
                    },
                )
                return

            # port_left 对应左串口：抬左手应 left 能量更大
            if pl > pr:
                self.tts.speak_and_wait('左手识别正确，校准完成。')
                result = 'ok'
                self._persist_imu_ports()
            else:
                if self.imu_interface.mode == 'dual_serial':
                    new_ports = self.imu_interface.swap_dual_ports_and_restart()
                    self._persist_imu_ports(new_ports)
                    self.tts.speak_and_wait('已自动交换左右手串口，校准完成。')
                else:
                    new_swap = not self.imu_interface.get_lr_swap()
                    self.imu_interface.apply_lr_swap(new_swap)
                    self._persist_imu_lr_swap()
                    self.tts.speak_and_wait('已自动校正左右手映射。')
                result = 'swapped'

            self.qt_interface.send_system_status(
                status_text='IMU左右手校准完成',
                imu={
                    'lr_calibrating': False,
                    'lr_result': result,
                    'energy_left': pl,
                    'energy_right': pr,
                    'lr_swap': self.imu_interface.get_lr_swap(),
                    **self._imu_status_payload(),
                },
            )
        except Exception as e:
            print(f'[IMU][LR] 校准异常: {e}')
            import traceback
            traceback.print_exc()
            self.tts.speak('左右手校准过程出错，请查看日志。')
            self.qt_interface.send_system_status(
                status_text='IMU左右手校准异常',
                imu={
                    'lr_calibrating': False,
                    'lr_result': 'error',
                    'error': str(e),
                    **self._imu_status_payload(),
                },
            )
        finally:
            self._imu_lr_calibrating = False

    def _persist_imu_ports(self, ports: dict = None):
        """将当前解析到的左右串口写回 imu_config.yaml（避免 auto 重启后顺序错乱）。"""
        cfg_path = os.path.join(self.config_path, 'imu_config.yaml')
        ports = ports or self._resolved_imu_ports()
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or {}
        except OSError as e:
            print(f'[IMU][LR] 读取 {cfg_path} 失败: {e}')
            return

        raw['ports'] = {
            'left': ports.get('left', '/dev/ttyACM0'),
            'right': ports.get('right', '/dev/ttyACM1'),
        }
        raw['lr_swap'] = False
        self._imu_config = raw
        self.imu_interface.apply_lr_swap(False)

        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)
            print(f'[IMU][LR] 已写回端口: L={raw["ports"]["left"]} R={raw["ports"]["right"]}')
        except OSError as e:
            print(f'[IMU][LR] 写回 {cfg_path} 失败: {e}')

    def _persist_imu_lr_swap(self):
        """把交换后的左右手端口写回 imu_config.yaml。
        若 ports.left/right 配置为 'auto'，则仅写入 lr_swap: true/false 字段。
        """
        cfg_path = os.path.join(self.config_path, 'imu_config.yaml')
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or {}
        except OSError as e:
            print(f'[IMU][LR] 读取 {cfg_path} 失败: {e}')
            return

        ports = raw.get('ports') or {}
        left = ports.get('left', 'auto')
        right = ports.get('right', 'auto')
        if (
            isinstance(left, str) and isinstance(right, str)
            and left.lower() != 'auto' and right.lower() != 'auto'
        ):
            ports['left'], ports['right'] = right, left
            raw['ports'] = ports
            raw['lr_swap'] = False  # 端口已物理对调，运行时不需再 swap
            self._imu_config = raw
            self.imu_interface.apply_lr_swap(False)
        else:
            raw['lr_swap'] = bool(self.imu_interface.get_lr_swap())
            self._imu_config = raw

        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)
            print(f'[IMU][LR] 已写回配置: {cfg_path}')
        except OSError as e:
            print(f'[IMU][LR] 写回 {cfg_path} 失败: {e}')

    def _resolve_imu_measure_bin(self) -> Optional[str]:
        candidates = []
        rel = self._imu_config.get('measure_bin')
        if rel:
            candidates.append(
                rel if os.path.isabs(rel)
                else os.path.normpath(os.path.join(PROJECT_ROOT, rel))
            )
        candidates.extend([
            os.path.join(REPO_ROOT, 'src', 'imu', 'build', 'IMU_measure'),
            os.path.join(
                REPO_ROOT, 'src', 'imu', 'dual', 'IMU_measure',
                'build', 'IMU_measure',
            ),
        ])
        path = None
        for cand in candidates:
            if os.path.isfile(cand):
                path = cand
                break
        if not path:
            return None
        if not os.access(path, os.X_OK):
            try:
                os.chmod(path, 0o755)
                print(f'[IMU] 已为 IMU_measure 添加执行权限: {path}')
            except OSError as e:
                print(f'[IMU] IMU_measure 无执行权限且无法修复: {path} ({e})')
                print('[IMU] 请执行: chmod +x', path)
                return None
        return path

    def _resolve_imu_assessment_log(self) -> Optional[str]:
        """返回最新的 assessment_log.csv（按文件修改时间）。"""
        candidates = []
        rel = self._imu_config.get(
            'assessment_log_path', 'data/imu/assessment_log.csv'
        )
        candidates.append(_resolve_repo_path(rel))
        candidates.append(_resolve_repo_path('data/imu/assessment_log.csv'))
        measure_bin = self._resolve_imu_measure_bin()
        if measure_bin:
            candidates.append(os.path.normpath(os.path.join(
                os.path.dirname(measure_bin), '..', 'data',
                'assessment_log.csv',
            )))

        existing = []
        seen = set()
        for raw in candidates:
            path = os.path.normpath(raw)
            if path in seen or not os.path.isfile(path):
                continue
            seen.add(path)
            existing.append(path)

        if not existing:
            return None
        best = max(existing, key=os.path.getmtime)
        print(f'[IMU] 使用 assessment_log: {best}')
        return best

    def _assessment_result_path(self) -> str:
        out_rel = self._imu_config.get(
            'assessment_result_path', 'data/imu/assessment_result.txt'
        )
        return _resolve_repo_path(out_rel)

    def _sync_imu_assessment_files(self) -> bool:
        import shutil

        log_path = self._resolve_imu_assessment_log()
        out_path = self._assessment_result_path()
        if not log_path:
            print('[IMU] 未找到 assessment_log.csv')
            return False

        script_path = os.path.join(
            REPO_ROOT, 'scripts', 'sync_imu_assessment.py'
        )
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                'sync_imu_assessment', script_path,
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sync_assessment = mod.sync_assessment
        except Exception as e:
            print(f'[IMU] 加载 sync_imu_assessment 失败: {e}')
            return False

        ok = sync_assessment(log_path, out_path)
        if ok:
            dest_log = _resolve_repo_path('data/imu/assessment_log.csv')
            try:
                os.makedirs(os.path.dirname(dest_log), exist_ok=True)
                if os.path.abspath(log_path) != os.path.abspath(dest_log):
                    shutil.copy2(log_path, dest_log)
            except OSError as e:
                print(f'[IMU] 复制 assessment_log 失败: {e}')
        return ok

    def _emit_assessment_phase(self, phase: str, **kwargs):
        if self.qt_interface is not None:
            self.qt_interface.send_assessment_phase(phase=phase, **kwargs)

    def _push_vision_assessment_live(self, partial: dict):
        """评估采集中：向 Qt 推送实时视觉完成度/准确度/质量。"""
        if not self.qt_interface or not self.qt_interface.is_connected():
            return
        warnings = partial.get('warnings') or []
        self.qt_interface.send_assessment_phase(
            phase='collecting',
            vision_completion=partial.get('completion_coef'),
            vision_accuracy=partial.get('accuracy_coef'),
            vision_current_angle=partial.get('current_angle'),
            vision_max_angle=partial.get('max_angle'),
            vision_quality=partial.get('quality_score'),
            vision_status=partial.get('vision_status'),
            vision_warning=warnings[0] if warnings else None,
        )

    def _lock_patient_from_camera(
        self, seconds: float = 2.5, pick_mode: str = 'default',
    ) -> bool:
        """采集前锁定主用户（评估/训练共用）。"""
        if self.simulate or not hasattr(self, 'vision_pipeline'):
            return False
        from core.vision_quality import analyze_frame, score_bbox_for_supine_patient

        va_cfg = self.scoring_config.get('vision_assessment', {})
        deadline = time.time() + max(0.8, seconds)
        best_bbox = None
        best_rank = -1e9
        while time.time() < deadline:
            skel = self.vision_pipeline.get_latest_skeleton()
            left, _ = self.vision_pipeline.get_latest_frames()
            fr = analyze_frame(
                skel, left, va_cfg,
                body_region=getattr(self, '_last_training_body_region', 'upper'),
            )
            bbox = fr.get('bbox')
            if bbox and fr.get('pose_ok'):
                fw = float(left.shape[1]) if left is not None else 0.0
                fh = float(left.shape[0]) if left is not None else 0.0
                if pick_mode == 'supine_bed' and fw > 0 and fh > 0:
                    rank = score_bbox_for_supine_patient(bbox, (fw, fh)) * 1000.0
                else:
                    cx, cy = fw * 0.5, fh * 0.5
                    x1, y1, x2, y2 = bbox[:4]
                    bcx = (x1 + x2) * 0.5
                    bcy = (y1 + y2) * 0.5
                    dist = ((bcx - cx) ** 2 + (bcy - cy) ** 2) if fw > 0 else 0.0
                    rank = float(fr.get('frame_score', 0)) * 1000.0 - dist
                if rank > best_rank:
                    best_rank = rank
                    best_bbox = bbox
            time.sleep(0.12)
        if best_bbox:
            self.vision_pipeline.lock_patient(best_bbox, 'session')
            return True
        return False

    def _poll_vision_quality(self) -> dict:
        """实时画面质量（评估/训练共用，供 Qt 预览与 TTS 告警）。"""
        if self.simulate or not hasattr(self, 'vision_pipeline'):
            return {}
        from core.vision_quality import aggregate_quality, analyze_frame

        va_cfg = self.scoring_config.get('vision_assessment', {})
        skel = self.vision_pipeline.get_latest_skeleton()
        left, _ = self.vision_pipeline.get_latest_frames()
        fr = analyze_frame(
            skel, left, va_cfg,
            body_region=getattr(self, '_last_training_body_region', 'upper'),
        )
        if not fr:
            return self._last_vision_quality

        buf = self._vision_quality_buffer
        buf.append(fr)
        if len(buf) > 24:
            del buf[:-24]
        agg = aggregate_quality(
            buf[-12:],
            va_cfg,
            allow_companion=self._allow_companion_in_frame,
            body_region=getattr(self, '_last_training_body_region', 'upper'),
        )
        self._last_vision_quality = agg

        warn = (agg.get('warnings') or [None])[0]
        active = (
            self.is_training
            or getattr(self, '_assessment_collecting', False)
        )
        now = time.time()
        if (
            active
            and warn
            and now - self._last_vision_tts_warn > 12.0
            and agg.get('vision_status') in (
                'backlight', 'multi_person', 'occlusion', 'poor',
            )
        ):
            self._last_vision_tts_warn = now
            if hasattr(self, 'tts') and self.tts:
                self.tts.speak(warn)
        return agg

    def _run_vision_precheck(self) -> dict:
        """评估采集前视觉预检，并同步 Qt / TTS。"""
        seconds = int(
            self.scoring_config.get('vision_assessment', {}).get(
                'precheck_seconds', 3,
            )
        )
        self._emit_assessment_phase(
            'precheck',
            instruction=(
                '请正对摄像头，确保只有您一人在画面中，'
                '肩肘腕无遮挡，避免逆光。正在检测环境…'
            ),
            duration=seconds,
        )
        self.tts.speak(
            '请正对摄像头，确保只有您一人在画面中，肩肘腕不要被遮挡，'
            '避免窗户在身后造成逆光。正在检测画面…'
        )
        if not self.simulate:
            self._vision_quality_buffer.clear()
            self._last_vision_quality = {}
            self.vision_pipeline.clear_patient_lock()
        precheck = self._vision_assessment_monitor.run_precheck()
        if precheck.get('passed') and not precheck.get('skipped'):
            self._lock_patient_from_camera(1.5)
        warnings = precheck.get('warnings') or []
        self._emit_assessment_phase(
            'precheck',
            instruction=precheck.get('message', ''),
            duration=seconds,
            vision_quality=precheck.get('quality_score'),
            vision_status=precheck.get('vision_status'),
            vision_warning=warnings[0] if warnings else None,
        )
        if precheck.get('passed'):
            self.tts.speak('画面检测通过，请准备开始动作。')
        elif not precheck.get('skipped'):
            self.tts.speak_and_wait(precheck.get('message', '请调整站位与光线。'))
        return precheck

    def _should_use_imu_hardware_assessment(self) -> bool:
        if self.simulate:
            return False
        mode = str(self._imu_config.get('mode', 'simulate'))
        if mode not in ('dual_serial', 'txt'):
            return False
        return self._resolve_imu_measure_bin() is not None

    @staticmethod
    def _count_csv_data_rows(path: str) -> int:
        if not path or not os.path.isfile(path):
            return 0
        rows = 0
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('ax_') or line.startswith('time,'):
                    continue
                rows += 1
        return rows

    def _find_latest_dual_csvs(self, min_mtime: float = 0.0):
        """返回同一采集批次（时间戳配对）的 L/R CSV。"""
        import glob
        import re

        bases = []
        measure_bin = self._resolve_imu_measure_bin()
        if measure_bin:
            bases.append(os.path.normpath(os.path.join(
                os.path.dirname(measure_bin), '..', 'data',
            )))
        data_dir = self._imu_config.get('data_dir', 'data/imu')
        if data_dir:
            bases.append(_resolve_repo_path(data_dir))

        pair_re = re.compile(r'IMU_data_([LR])_(\d{8}_\d{6})\.csv$')
        pairs: dict = {}
        for base in bases:
            if not os.path.isdir(base):
                continue
            for path in glob.glob(os.path.join(base, 'IMU_data_*.csv')):
                name = os.path.basename(path)
                m = pair_re.match(name)
                if not m:
                    continue
                label, stamp = m.group(1), m.group(2)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if mtime < min_mtime:
                    continue
                bucket = pairs.setdefault(stamp, {})
                prev = bucket.get(label)
                if not prev or mtime >= os.path.getmtime(prev):
                    bucket[label] = path

        complete = [
            stamp for stamp, files in pairs.items()
            if 'L' in files and 'R' in files
        ]
        if not complete:
            return None, None
        best = max(complete)
        files = pairs[best]
        return files['L'], files['R']

    def _resolved_imu_ports(self) -> dict:
        diag = self.imu_interface.get_diagnostics()
        ports = diag.get('dual_ports') or getattr(
            self.imu_interface, '_dual_ports', None
        ) or {}
        return {
            'left': ports.get('left', '/dev/ttyACM0'),
            'right': ports.get('right', '/dev/ttyACM1'),
        }

    def _run_imu_measure_subprocess(self, seconds: int) -> bool:
        import subprocess

        bin_path = self._resolve_imu_measure_bin()
        if not bin_path:
            return False

        ports = self._resolved_imu_ports()
        env = os.environ.copy()
        env['IMU_LEFT'] = ports['left']
        env['IMU_RIGHT'] = ports['right']
        data_dir = self._imu_config.get('data_dir', 'data/imu')
        if data_dir:
            imu_data = _resolve_repo_path(data_dir)
            os.makedirs(imu_data, exist_ok=True)
            env['IMU_DATA_DIR'] = imu_data

        release_serial = (
            self.imu_interface.mode == 'dual_serial'
            and self.imu_interface._running
        )
        if release_serial:
            print(
                f'[IMU] 暂停 Python 串口读取，交给 IMU_measure 采集 '
                f"L={ports['left']} R={ports['right']}"
            )
            self.imu_interface.stop()
            time.sleep(0.8)

        print(f'[IMU] 运行硬件采集: {bin_path} {seconds}s')
        ok = False
        try:
            proc = subprocess.run(
                [bin_path, str(seconds)],
                check=False,
                timeout=seconds + 120,
                env=env,
                capture_output=True,
                text=True,
            )
            if proc.stdout:
                print(proc.stdout.rstrip())
            if proc.stderr:
                print(proc.stderr.rstrip())
            ok = proc.returncode == 0
            print(f'[IMU] IMU_measure 退出码: {proc.returncode}')
        except subprocess.TimeoutExpired:
            print('[IMU] IMU_measure 超时')
        except OSError as e:
            print(f'[IMU] 无法运行 IMU_measure: {e}')
        finally:
            if release_serial:
                print('[IMU] 恢复 Python 串口读取')
                self.imu_interface.start()
                self._push_imu_status_to_qt()
        return ok

    def _push_assessment_scoring_to_qt(self, result: dict = None):
        """将六维评估分数推送到 Qt（综合分优先使用 dynamic_updater 的 current_score）。"""
        result = result or {}
        level = self.current_level or result.get('level', 'L1')
        dims = self._last_dimension_scores or result.get('dimension_scores') or {}
        dim_sum = round(float(sum(float(v) for v in dims.values())), 1) if dims else 0.0
        # 方案 A：初评结果以六维之和为总分；训练中仍保留 dynamic_updater 动态分
        if result.get('scoring_mode') == 'A' and dims and self.dynamic_updater is None:
            total = dim_sum
        elif self.current_score is not None:
            total = self.current_score
        else:
            total = result.get('total_score', dim_sum)
        level_info = self.level_manager.get_level_info(level)
        vision_meta = result.get('vision_assessment')
        lr = result.get('lr_scores') or {}
        note = result.get('note') or ''
        if lr and not note:
            note = f"左{lr.get('left', 0):.1f} 右{lr.get('right', 0):.1f}"
        self.qt_interface.send_scoring(
            total_score=total,
            dimension_scores=dims,
            level=level,
            level_name=level_info.get('name', level),
            source='assessment',
            imu_total_score=result.get('imu_total_score'),
            imu_dimension_scores=result.get('imu_dimension_scores'),
            vision_assessment=vision_meta,
            imu_only_reason=result.get('imu_only_reason'),
            lr_scores=lr if lr else None,
            lr_note=note or None,
        )

    def _ensure_assessment_tts(self):
        """评估开始前确保短播报已缓存，避免现场合成等待。"""
        if hasattr(self, 'tts') and self.tts:
            self.tts.ensure_assessment_cached()

    def _run_guided_imu_assessment(self, payload: dict = None):
        """统一 IMU 评估：一个动作（自然下垂 → 侧平举过顶），带 Qt 阶段字幕。"""
        import threading

        self._ensure_assessment_tts()

        payload = payload or {}
        action = TEST_ACTIONS[0]
        seconds = int(payload.get('seconds') or self._imu_config.get(
            'measure_seconds', action.get('total_duration', COLLECT_SECONDS)
        ))
        total_actions = len(TEST_ACTIONS)

        print("\n" + "=" * 50)
        print("   开始 IMU 健康评估（侧平举过顶）")
        print("=" * 50)

        try:
            self._emit_assessment_phase(
                'intro',
                action_index=0,
                total_actions=total_actions,
                instruction=INTRO_TEXT,
                duration=0,
            )
            self.tts.speak_and_wait(INTRO_TTS)

            self._emit_assessment_phase(
                'action',
                action_index=1,
                total_actions=total_actions,
                action_name=action['name'],
                instruction=action['instruction'],
                duration=seconds,
            )
            self.tts.speak_and_wait(ACTION_TTS)
            time.sleep(PREPARE_AFTER_INSTRUCTION)

            if not self.simulate:
                precheck = self._run_vision_precheck()
                if not precheck.get('passed') and not precheck.get('skipped'):
                    print(
                        f"[Vision] 预检未通过 quality="
                        f"{precheck.get('quality_score', 0):.2f}: "
                        f"{precheck.get('message')}"
                    )

            if not self._resolve_imu_measure_bin():
                msg = (
                    '未找到 IMU_measure 可执行文件，请执行 '
                    'bash scripts/build_imu_measure.sh'
                )
                print(f'[IMU] {msg}')
                self.tts.speak(msg)
                return None

            ports = self._resolved_imu_ports()
            diag = self.imu_interface.get_diagnostics()
            left_ok = self.imu_interface.is_imu_connected('imu_left')
            right_ok = self.imu_interface.is_imu_connected('imu_right')
            print(
                f'[IMU] 采集前: 左={left_ok} 右={right_ok} '
                f'实时帧={diag.get("frame_count", 0)} mode={diag.get("mode")} '
                f'ports L={ports["left"]} R={ports["right"]}'
            )
            if not left_ok and not right_ok:
                self.tts.speak(
                    '未检测到左右 IMU 实时数据，仍将尝试硬件采集；'
                    '若失败请检查 USB 连接与佩戴。'
                )

            proc_state = {'done': False, 'ok': False}
            collect_started_at = time.time()

            def _worker():
                proc_state['ok'] = self._run_imu_measure_subprocess(seconds)
                proc_state['done'] = True

            self._emit_assessment_phase(
                'collecting',
                action_index=1,
                total_actions=total_actions,
                action_name=action['name'],
                instruction=ACTION_TEXT,
                duration=seconds,
            )
            self.tts.speak(COLLECT_START_TTS)

            self._assessment_collecting = True
            if not self.simulate:
                self._vision_assessment_monitor.start(seconds)

            def _raise_hands_cue():
                time.sleep(RAISE_HANDS_DELAY_SEC)
                if getattr(self, '_assessment_collecting', False):
                    self.tts.speak(RAISE_HANDS_TTS)

            threading.Thread(
                target=_raise_hands_cue, daemon=True, name='raise-hands-cue',
            ).start()

            worker = threading.Thread(
                target=_worker, daemon=True, name='imu-measure',
            )
            worker.start()
            worker.join(timeout=seconds + 120)

            self._assessment_collecting = False
            if not self.simulate:
                self._last_vision_assessment_summary = (
                    self._vision_assessment_monitor.stop()
                )
                va = self._last_vision_assessment_summary or {}
                print(
                    f"[Vision] 会话质量 {va.get('quality_score', 0):.2f} "
                    f"status={va.get('vision_status')} "
                    f"fusion={'是' if va.get('use_vision_fusion') else '否(IMU only)'}"
                )
            else:
                self._last_vision_assessment_summary = None

            if not proc_state['ok']:
                fail_msg = (
                    'IMU 硬件采集失败，本次评估已取消。'
                    '请确认 IMU_measure 可执行，或重新编译后再试。'
                )
                print(f'[IMU] {fail_msg}')
                self.tts.speak_and_wait(fail_msg)
                self._emit_assessment_phase(
                    'failed',
                    action_index=1,
                    total_actions=total_actions,
                    instruction=fail_msg,
                    duration=0,
                )
                return None

            self._emit_assessment_phase(
                'analyzing',
                action_index=1,
                total_actions=total_actions,
                instruction=ANALYZING_TEXT,
                duration=0,
            )
            self.tts.speak(ANALYZING_TTS)

            csv_l, csv_r = self._find_latest_dual_csvs(
                min_mtime=collect_started_at - 5.0,
            )
            rows_l = self._count_csv_data_rows(csv_l)
            rows_r = self._count_csv_data_rows(csv_r)
            min_rows = max(100, int(seconds * 80))
            print(
                f'[IMU] 采集文件: 左={rows_l}帧 ({csv_l or "无"}) '
                f'右={rows_r}帧 ({csv_r or "无"})'
            )
            if not csv_l or not csv_r:
                fail_msg = '未找到本次评估新生成的 IMU 数据文件，评估已取消。'
                print(f'[IMU] {fail_msg}')
                self.tts.speak_and_wait(fail_msg)
                self._emit_assessment_phase(
                    'failed',
                    action_index=1,
                    total_actions=total_actions,
                    instruction=fail_msg,
                    duration=0,
                )
                return None
            if rows_l < min_rows or rows_r < min_rows:
                warn = (
                    f'IMU 数据可能不足（左 {rows_l} 帧，右 {rows_r} 帧，'
                    f'建议各不少于 {min_rows} 帧），请检查传感器连接与佩戴位置。'
                )
                print(f'[IMU] {warn}')
                self.tts.speak(DATA_WARN_TTS)
            elif rows_l >= min_rows and rows_r >= min_rows:
                print('[IMU] 双侧数据采集正常')
                self.tts.speak(DATA_OK_TTS)

            self._sync_imu_assessment_files()
            self._push_imu_status_to_qt()

            if self._try_load_imu_assessment():
                self._emit_assessment_phase(
                    'done',
                    action_index=1,
                    total_actions=total_actions,
                    instruction=DONE_TEXT,
                    duration=0,
                )
                self.tts.speak(DONE_TTS)
            else:
                self.tts.speak(SYNC_FAIL_TTS)
        except Exception as e:
            print(f'[IMU] 评估异常: {e}')
            import traceback
            traceback.print_exc()
            self.tts.speak('评估过程出错，请查看后端日志后重试。')
        return None

    def _run_imu_hardware_assessment(self, payload: dict = None):
        """设置页「IMU初评」与评估页共用同一引导流程。"""
        return self._run_guided_imu_assessment(payload)

    # ==================== IMU回调 ====================

    def _on_imu_data(self, imu_id, accel, gyro, timestamp):
        """IMU数据到达回调"""
        # 送入融合引擎
        self.fusion_engine.update_imu(
            imu_id=imu_id,
            accel=accel,
            gyro=gyro
        )

    def _on_imu_status(self, imu_id, status, info):
        """IMU状态变化回调"""
        print(f"[IMU] {imu_id}: {status}")
        self._push_imu_status_to_qt()

    def _on_skeleton_3d(self, skeleton_3d: dict, timestamp: float):
        """视觉流水线 3D 骨骼回调 → 融合 + Qt"""
        keypoints = {}
        confidences = {}
        joints_qt = {}

        for name, data in skeleton_3d.items():
            pos = data.get('position')
            conf = float(data.get('confidence', 0.5))
            if pos is None:
                continue
            keypoints[name] = np.asarray(pos, dtype=np.float64)
            confidences[name] = conf
            joints_qt[name] = pos.tolist()

        if keypoints:
            self.fusion_engine.update_vision(keypoints, confidences)
            self.fusion_engine.set_raw_skeleton_3d(skeleton_3d)

        latest = self.vision_pipeline.get_latest_skeleton()
        if latest:
            k2d = latest.get('keypoints_2d_left') or {}
            self.fusion_engine.set_vision_2d_left(k2d)

        self._vision_frame_count += 1
        if self._vision_frame_count % 3 == 0 and joints_qt:
            self.qt_interface.send_skeleton_3d(joints_qt, confidences)

    def _try_load_imu_assessment(self, sync_csv: bool = True):
        """从 assessment_log.csv 同步并导入初评结果，推送到 Qt。"""
        if sync_csv:
            self._sync_imu_assessment_files()

        path = self._assessment_result_path()
        result = IMUInterface.load_assessment_result(path)
        if not result:
            return False

        if getattr(self, '_last_vision_assessment_summary', None):
            result = apply_vision_to_imu_result(
                result, self._last_vision_assessment_summary,
            )
            self._last_vision_assessment_summary = None
            va = result.get('vision_assessment') or {}
            if va:
                print(
                    f"[Vision] 评估分数使用 IMU {result['total_score']:.1f} 分；"
                    f"视觉参考 完成度={va.get('completion_coef', 0):.2f} "
                    f"准确度={va.get('accuracy_coef', 0):.2f} "
                    f"(不参与计分)"
                )

        self.current_score = result['total_score']
        self.current_level = result['level']
        self._last_dimension_scores = result.get('dimension_scores', {})
        self.dynamic_updater = DynamicScoreUpdater(
            initial_score=self.current_score,
            initial_level=self.current_level,
        )
        print(
            f"[IMU] 已导入初评: {self.current_level} / "
            f"{self.current_score:.1f} 分"
        )
        self._push_assessment_scoring_to_qt(result)
        return True

    def _refresh_assessment_from_csv(self, payload: dict = None):
        """Qt 请求：从最新 assessment_log.csv 刷新六维分数并推送（保留训练后的动态综合分）。"""
        self._sync_imu_assessment_files()
        path = self._assessment_result_path()
        result = IMUInterface.load_assessment_result(path)
        if not result:
            if self.current_score is not None:
                self._push_assessment_scoring_to_qt()
                return {'ok': True, 'total_score': self.current_score}
            return {'ok': False}

        self._last_dimension_scores = result.get('dimension_scores', {})
        if self.dynamic_updater is None:
            self.current_score = result['total_score']
            self.current_level = result.get('level', 'L1')
            self.dynamic_updater = DynamicScoreUpdater(
                initial_score=self.current_score,
                initial_level=self.current_level,
            )
        self._push_assessment_scoring_to_qt(result)
        return {'ok': True, 'total_score': self.current_score}

    # ==================== 主流程 ====================

    def start(self):
        """启动系统"""
        self.is_running = True

        # 启动通信接口
        self.imu_interface.start()
        self.qt_interface.start()

        threading.Timer(5.0, self._push_imu_status_to_qt).start()

        self._try_load_imu_assessment()

        if not self.simulate:
            if self.vision_pipeline.start():
                print("[✓] 双目视觉已启动")
                self._start_vision_preview_thread()
            else:
                print("[WARNING] 视觉流水线启动失败，训练将缺少视觉数据")
        elif self.show_vision_debug:
            print("[WARNING] --show-vision 需配合 --real 使用，当前为模拟模式无画面")

        print("\n" + "=" * 60)
        print("   系统已启动，等待指令...")
        print("   输入 'a' 开始初评")
        print("   输入 't' 开始训练")
        print("   输入 's' 状态")
        print("   输入 'q' 退出")
        if self.show_vision_debug and not self.simulate:
            print("   OpenCV 调试窗口按 Q 可关闭（并退出系统）")
        if not self.simulate:
            print("   Qt 连接后将自动推送双目调试画面")
        print("=" * 60 + "\n")

    def _start_vision_preview_thread(self):
        """独立线程：OpenCV 调试窗 + 向 Qt 推送 vision_preview。"""
        self._debug_thread = threading.Thread(
            target=self._vision_preview_loop,
            daemon=True,
            name="vision-preview",
        )
        self._debug_thread.start()
        if self.show_vision_debug:
            print("[✓] OpenCV 视觉调试窗口已开启 (Rehab Vision Debug)")
        print("[✓] 视觉预览线程已启动（Qt 连接后自动推流）")

    def _build_vision_display_frame(self, import_cv2, burn_overlay: bool = True):
        """渲染与 --show-vision 相同的左右拼接调试画面。

        burn_overlay=False 时不烧录 Cam/Pose 文字，供 Qt 预览（由 Qt 底部条显示质量提示）。
        """
        import numpy as np

        cv2 = import_cv2
        pe = self.vision_pipeline.pose_estimator
        max_w = max(320, self._debug_max_width)
        max_h = max(180, self._debug_max_height)

        def _scale(img):
            h, w = img.shape[:2]
            scale = min(max_w / w, max_h / h, 1.0)
            disp_w = max(1, int(w * scale))
            disp_h = max(1, int(h * scale))
            if scale < 1.0 or (disp_w, disp_h) != (w, h):
                return cv2.resize(
                    img, (disp_w, disp_h), interpolation=cv2.INTER_LINEAR
                )
            return img

        res = self.vision_pipeline.get_latest_skeleton() or {}

        combined_pre = res.get('preview_combined')
        if combined_pre is not None:
            diag = self.vision_pipeline.get_diagnostics()
            overlay = (
                f"Cam:{diag.get('capture_fps', 0):.0f} "
                f"Pose:{diag.get('pipeline_fps', 0):.0f} "
                f"Infer:{diag.get('last_infer_ms', 0):.0f}ms"
            )
            if self.is_training and self._active_session:
                sm = getattr(self._active_session, '_current_state_machine', None)
                if sm and getattr(sm, '_action_mode', '') == 'gait':
                    ang = self.fusion_engine.compute_joint_angles()
                    overlay += (
                        f" | 步幅:{ang.get('step_distance', 0):.0f}cm"
                        f" dxL:{ang.get('step_dx_left', 0):.0f}"
                        f" dxR:{ang.get('step_dx_right', 0):.0f}"
                    )
            if getattr(self, '_assessment_collecting', False):
                live = self._vision_assessment_monitor.live_stats
                if live.get('valid_frames', 0) > 0:
                    overlay += (
                        f" | 评估角:{live.get('current_angle', 0):.0f}"
                        f"/{live.get('max_angle', 0):.0f}°"
                    )
            frame = combined_pre.copy()
            if burn_overlay:
                cv2.putText(
                    frame, overlay, (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
                )
            return _scale(frame), overlay

        left, right = self.vision_pipeline.get_latest_frames()
        snap_l = res.get('preview_left')
        snap_r = res.get('preview_right')
        if snap_l is not None:
            left = snap_l
        if snap_r is not None:
            right = snap_r
        if left is None or right is None:
            frame = np.zeros((max_h, max_w, 3), np.uint8)
            cv2.putText(
                frame, "Waiting for camera...",
                (20, max_h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (0, 255, 255), 2,
            )
            return frame, "等待摄像头画面..."

        kpts_l = res.get('keypoints_2d_left') or {}
        kpts_r = res.get('keypoints_2d_right') or {}
        vis_l = pe.draw_keypoints(left, kpts_l) if kpts_l else left
        vis_r = pe.draw_keypoints(right, kpts_r) if kpts_r else right
        combined = np.hstack([vis_l, vis_r])
        mid = vis_l.shape[1]
        cv2.line(combined, (mid, 0), (mid, combined.shape[0]), (0, 0, 255), 2)

        diag = self.vision_pipeline.get_diagnostics()
        overlay = (
            f"Cam:{diag.get('capture_fps', 0):.0f} "
            f"Pose:{diag.get('pipeline_fps', 0):.0f} "
            f"Infer:{diag.get('last_infer_ms', 0):.0f}ms"
        )
        if self.is_training and self._active_session:
            sm = getattr(self._active_session, '_current_state_machine', None)
            if sm and getattr(sm, '_action_mode', '') == 'gait':
                ang = self.fusion_engine.compute_joint_angles()
                overlay += (
                    f" | 步幅:{ang.get('step_distance', 0):.0f}cm"
                    f" dxL:{ang.get('step_dx_left', 0):.0f}"
                    f" dxR:{ang.get('step_dx_right', 0):.0f}"
                )
        if getattr(self, '_assessment_collecting', False):
            live = self._vision_assessment_monitor.live_stats
            if live.get('valid_frames', 0) > 0:
                overlay += (
                    f" | 评估角:{live.get('current_angle', 0):.0f}"
                    f"/{live.get('max_angle', 0):.0f}°"
                )
        if burn_overlay:
            cv2.putText(
                combined, overlay, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
            )
        return _scale(combined), overlay

    def _vision_preview_loop(self):
        import base64
        import cv2

        window_name = 'Rehab Vision Debug'
        ui_interval = 1.0 / 15.0
        last_ui = 0.0
        window_created = False

        while self.is_running:
            now = time.time()
            if now - last_ui < ui_interval:
                time.sleep(0.005)
                continue
            last_ui = now

            display, overlay = self._build_vision_display_frame(
                cv2, burn_overlay=False
            )
            quality = self._poll_vision_quality()

            if self.qt_interface.is_connected():
                ok, buf = cv2.imencode(
                    '.jpg', display, [cv2.IMWRITE_JPEG_QUALITY, 72]
                )
                if ok:
                    b64 = base64.b64encode(buf.tobytes()).decode('ascii')
                    h, w = display.shape[:2]
                    warnings = quality.get('warnings') or []
                    self.qt_interface.send_vision_preview(
                        b64, w, h, overlay,
                        vision_quality=quality.get('quality_score'),
                        vision_status=quality.get('vision_status'),
                        vision_warning=warnings[0] if warnings else None,
                    )

            if self.show_vision_debug:
                display_dbg = display.copy()
                cv2.putText(
                    display_dbg, overlay, (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2,
                )
                if not window_created:
                    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
                    window_created = True
                try:
                    cv2.imshow(window_name, display_dbg)
                except cv2.error as exc:
                    print(f"[Vision Debug] imshow 失败: {exc}")
                    self.show_vision_debug = False
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.is_running = False
                    break

        if window_created:
            cv2.destroyWindow(window_name)

    def run_interactive(self):
        """交互式运行（终端模式，用于开发调试）"""
        self.start()

        try:
            while self.is_running:
                try:
                    cmd = input("\n请输入指令 (a=初评, t=训练, s=状态, q=退出): ").strip().lower()
                except EOFError:
                    break

                if cmd == 'q':
                    break
                elif cmd == 'a':
                    self.run_initial_assessment()
                elif cmd == 't':
                    self.run_training_session()
                elif cmd == 's':
                    self._print_status()
                else:
                    print("未知指令，请输入 a/t/s/q")
        except KeyboardInterrupt:
            print("\n收到中断信号")
        finally:
            self.shutdown()

    def run_qt_service(self):
        """Qt 界面模式：无终端交互，由 Qt 通过 Socket 发指令。"""
        self.start()
        print("[Qt Service] 后端已就绪，等待 Qt 连接…")
        print(f"[Qt Service] Socket: {self.qt_interface.socket_path or 'TCP 9002'}")
        heartbeat_sec = float(os.environ.get('REHAB_HEARTBEAT_SEC', '10'))
        if heartbeat_sec > 0:
            print(
                f"[Qt Service] 测试模式：每 {heartbeat_sec:.0f}s 打印运行心跳"
                "（关闭: export REHAB_HEARTBEAT_SEC=0）"
            )
        last_hb = 0.0
        qt_connected = False
        try:
            while self.is_running:
                time.sleep(0.5)
                connected = self.qt_interface.is_connected()
                if connected and not qt_connected:
                    qt_connected = True
                    print("[Qt Service] Qt 已连接，开始推送视觉预览")
                elif not connected and qt_connected:
                    qt_connected = False
                    print("[Qt Service] Qt 已断开，等待重连…")
                if heartbeat_sec > 0:
                    now = time.time()
                    if now - last_hb >= heartbeat_sec:
                        last_hb = now
                        self._print_runtime_heartbeat(qt_connected)
        except KeyboardInterrupt:
            print("\n收到中断信号")
        finally:
            self.shutdown()

    def _print_runtime_heartbeat(self, qt_connected: bool = False):
        """测试阶段定期输出一行运行状态，便于确认各模块是否正常。"""
        qt_state = "已连接" if qt_connected else "等待"
        diag = {}
        if self.vision_pipeline:
            diag = self.vision_pipeline.get_diagnostics()
        cam_fps = diag.get('capture_fps', 0)
        pose_fps = diag.get('pipeline_fps', 0)
        infer_ms = diag.get('last_infer_ms', 0)
        quality = self._poll_vision_quality()
        q_score = quality.get('quality_score', 0)
        q_status = quality.get('vision_status', '-')
        paused = (
            self._active_session.is_paused
            if self._active_session else False
        )
        train_state = "训练中" if self.is_training else "空闲"
        if self.is_training and paused:
            train_state = "暂停"
        imu_diag = self.imu_interface.get_diagnostics()
        imu_ok = imu_diag.get('connected', imu_diag.get('running', False))
        parts = [
            f"[心跳] Qt={qt_state}",
            f"视觉={q_status}({q_score}%)",
            f"Cam={cam_fps:.0f}fps",
            f"Pose={pose_fps:.0f}fps",
            f"Infer={infer_ms:.0f}ms",
            f"等级={self.current_level or '-'}",
            f"状态={train_state}",
            f"IMU={'OK' if imu_ok else '无'}",
            f"融合帧={self.fusion_engine.frame_count}",
        ]
        if self.is_training and self._active_session:
            sm = getattr(self._active_session, '_current_state_machine', None)
            if sm:
                action = getattr(sm, 'action_name', '') or getattr(sm, '_action_name', '')
                if action:
                    parts.append(f"动作={action}")
                reps = getattr(sm, 'rep_count', None)
                if reps is not None:
                    parts.append(f"次数={reps}")
        print(' | '.join(parts))

    def _start_assessment_async(self, payload: dict = None):
        """Qt 触发初评：后台线程执行，避免阻塞 socket；始终播放动作引导。"""
        payload = payload or {}
        force = bool(payload.get('force', True))
        if self._assessment_thread and self._assessment_thread.is_alive():
            print('[初评] 评估已在进行中')
            return
        self._assessment_thread = threading.Thread(
            target=self.run_initial_assessment,
            kwargs={'force': force},
            daemon=True,
            name='initial-assessment',
        )
        self._assessment_thread.start()

    def run_initial_assessment(self, force: bool = False):
        """运行初始评估；IMU 文件仅在没有 force 时跳过（Qt 点「开始评估」默认 force=True）。"""
        self._ensure_assessment_tts()
        if self.current_level and not force:
            print("\n[初评] 已存在 IMU 初评结果，跳过视觉初评。"
                  "（Qt 点「开始评估」会重新做完整动作测试）")
            return {
                'total_score': self.current_score,
                'level': self.current_level,
                'dimension_scores': {},
                'source': 'imu_import',
            }

        print("\n" + "=" * 50)
        print("   开始初始健康评估")
        print("=" * 50)

        if self._should_use_imu_hardware_assessment():
            print('[初评] 使用 IMU 硬件评估（侧平举过顶）')
            return self._run_guided_imu_assessment()

        assessment = InitialAssessment(
            scoring_engine=self.scoring_engine,
            fusion_engine=self.fusion_engine,
            imu_interface=self.imu_interface,
            tts=self.tts,
            simulate=self.simulate,
            qt_interface=self.qt_interface,
        )

        result = assessment.run()

        # 保存评估结果
        self.current_score = result['total_score']
        self.current_level = result['level']
        self._last_dimension_scores = result.get('dimension_scores', {})

        # 初始化动态评分更新器
        self.dynamic_updater = DynamicScoreUpdater(
            initial_score=self.current_score,
            initial_level=self.current_level
        )

        # 设置Prompt构建器的患者称呼
        self.prompt_builder = PromptBuilder(patient_name="您")

        # LLM生成播报语
        prompt = self.prompt_builder.build_assessment_report(
            total_score=self.current_score,
            level=self.current_level,
            dimension_scores=result['dimension_scores']
        )
        report_text = self.llm.generate(
            prompt['system'], prompt['user']
        )

        print(f"\n[播报] {report_text}")
        self.tts.speak(report_text)

        # 推送给Qt
        level_info = self.level_manager.get_level_info(self.current_level)
        self.qt_interface.send_scoring(
            total_score=self.current_score,
            dimension_scores=self._last_dimension_scores,
            level=self.current_level,
            level_name=level_info.get('name', self.current_level),
            source='assessment',
        )

        print(f"\n评估完成！评分: {self.current_score:.0f}  等级: {self.current_level}")
        return result

    def _level_has_integration(self, level: str) -> bool:
        return bool(
            self.level_manager.get_actions_by_region(level, 'integration')
        )

    def _parse_training_payload(self, payload: dict) -> dict:
        """从 Qt 指令 payload 解析 level / body_region / action_ids。"""
        payload = payload or {}
        level = payload.get('level') or self.current_level
        if isinstance(level, int):
            level = f'L{level}'
        elif isinstance(level, str):
            level = level.strip().upper()
            if level.isdigit():
                level = f'L{level}'
        action_ids = payload.get('action_ids')
        if payload.get('action_id'):
            action_ids = [payload['action_id']]
        elif isinstance(action_ids, str):
            action_ids = [action_ids]
        body_region = normalize_region(payload.get('body_region'))
        return {
            'level': level,
            'action_ids': action_ids,
            'body_region': body_region,
        }

    def _emit_training_state(self, phase: str, **kwargs):
        self.qt_interface.send_training_state(phase=phase, **kwargs)

    def run_training_session(self, payload: dict = None):
        """
        开始训练（后台线程，便于 Qt 随时暂停/继续/结束）。

        payload 可选字段:
          level: L1-L4，默认当前初评等级
          action_id / action_ids: 只练指定动作，如 L2_A3
        """
        if self._training_thread and self._training_thread.is_alive():
            self._emit_training_state(
                phase='busy',
                message='训练已在进行中',
            )
            return None

        opts = self._parse_training_payload(payload)
        level = opts['level']
        action_ids = opts['action_ids']
        body_region = opts['body_region']
        block = get_block_info(body_region)
        self._last_training_body_region = body_region

        if level is None:
            print("[WARNING] 尚未完成初评，先运行初评...")
            self.run_initial_assessment()
            level = self.current_level
        if level is None:
            self._emit_training_state(
                phase='idle', message='无法开始：缺少等级'
            )
            return None

        block_label = block.get('label', '训练')
        print("\n" + "=" * 50)
        if action_ids:
            print(
                f"   开始 {level} {block_label}（动作: {', '.join(action_ids)}）"
            )
        else:
            print(f"   开始 {level} {block_label}")
        print("=" * 50)

        level_info = self.level_manager.get_level_info(level)
        if action_ids:
            actions = self.level_manager.get_training_sequence(level)
            wanted = set(action_ids)
            actions = [a for a in actions if a.get('id') in wanted]
            if not actions:
                for aid in action_ids:
                    ac = self.level_manager.get_action_by_id(level, aid)
                    if ac:
                        actions.append(ac)
        else:
            actions = self.level_manager.get_training_sequence(
                level, body_region=body_region
            )

        if not actions:
            msg = f'当前等级没有「{block_label}」动作，请换一项试试。'
            self.tts.speak(msg)
            self._emit_training_state(phase='idle', message=msg)
            return None

        if not actions:
            msg = f'当前等级没有「{block_label}」动作，请换一项试试。'
            self.tts.speak(msg)
            self._emit_training_state(phase='idle', message=msg)
            return None

        level_name = level_info.get('name', level)

        def _training_worker():
            result = None
            try:
                self.is_training = True
                self._allow_companion_in_frame = training_allows_companion(
                    actions,
                )
                self._emit_training_state(
                    phase='busy',
                    message='正在准备训练，请稍候…',
                )

                print(f"[TTS] 正在预生成训练语音（{len(actions)} 个动作）...")
                self.tts.precache_training_session(
                    level_name=level_name,
                    actions=actions,
                    background=False,
                )

                setup_tts = block.get('setup_tts', '')
                if body_region == 'lower' and level != 'L1':
                    setup_tts = (
                        '请把摄像头对准髋、膝和双脚，略偏侧方；'
                        '双手可叉腰或自然下垂，不要遮挡腿部。'
                    )
                if setup_tts:
                    self.tts.speak_and_wait(setup_tts)
                if body_region == 'integration':
                    self.tts.speak_and_wait(
                        '今天是全身协调整合课，请后退一步到标记线，确保全身入镜。'
                    )

                start_text = f"开始{block_label}，请做好准备。"
                self.tts.speak_and_wait(start_text)

                if not self.simulate:
                    self._vision_quality_buffer.clear()
                    self._last_vision_quality = {}
                    self.vision_pipeline.clear_patient_lock()
                    bed_mode = level == 'L1'
                    pick_mode = 'supine_bed' if bed_mode else 'default'
                    self.vision_pipeline.set_patient_pick_mode(pick_mode)
                    lock_hint = block.get(
                        'lock_hint', '请站在画面中央…'
                    )
                    if body_region == 'lower' and level != 'L1':
                        lock_hint = (
                            '请单独站在画面内，露出髋、膝和双脚；'
                            '双手不要拿物品挡在身前。'
                        )
                    if bed_mode:
                        lock_hint = (
                            '请让摄像头主要对准床上的患者；'
                            '护理者尽量站在画面边缘或稍后一步。'
                        )
                    self._emit_training_state(
                        phase='busy',
                        message=lock_hint,
                    )
                    if self._lock_patient_from_camera(2.5, pick_mode=pick_mode):
                        if bed_mode:
                            self.tts.speak_and_wait(
                                '已锁定床上患者，请保持患者主要在画面里。'
                            )
                        else:
                            self.tts.speak_and_wait(
                                '已锁定您为主用户，请保持在画面中央。'
                            )
                    else:
                        if bed_mode:
                            self.tts.speak_and_wait(
                                '未能稳定锁定患者，请调整摄像头对准床面，'
                                '尽量让患者占画面大部分区域。'
                            )
                        else:
                            self.tts.speak_and_wait(
                                '未能稳定锁定主用户，请尽量单独站在画面中央。'
                            )

                self._send_training_plan({
                    'level': level,
                    'body_region': body_region,
                })

                session = TrainingSession(
                    level=level,
                    level_manager=self.level_manager,
                    scoring_engine=self.scoring_engine,
                    fusion_engine=self.fusion_engine,
                    imu_interface=self.imu_interface,
                    llm=self.llm,
                    tts=self.tts,
                    prompt_builder=self.prompt_builder,
                    qt_interface=self.qt_interface,
                    simulate=self.simulate,
                    vision_pipeline=(
                        self.vision_pipeline
                        if hasattr(self, 'vision_pipeline') else None
                    ),
                    action_ids=action_ids,
                    body_region=body_region if not action_ids else None,
                )
                self._active_session = session
                self._emit_training_state(
                    phase='running',
                    level=level,
                    action_ids=action_ids,
                    body_region=body_region,
                    block_label=block_label,
                    message='请跟随语音完成第一个动作。',
                )
                result = session.run()
            except Exception as exc:
                print(f"[训练] 会话异常: {exc}")
                import traceback
                traceback.print_exc()
                self._emit_training_state(
                    phase='idle',
                    message=f'训练异常中断：{exc}',
                )
            finally:
                self.is_training = False
                self._active_session = None
                self._allow_companion_in_frame = False
                if hasattr(self, 'vision_pipeline') and self.vision_pipeline:
                    self.vision_pipeline.set_patient_pick_mode('default')

            self._emit_training_state(phase='stopped', level=level)
            self._finish_training_session(level, result)
            return result

        self._training_thread = threading.Thread(
            target=_training_worker,
            daemon=True,
            name='training-session',
        )
        self._training_thread.start()
        return None

    def _finish_training_session(self, level: str, result: dict):
        """训练线程结束后：评分更新、总结播报。"""
        if not result or not result.get('actions_completed'):
            self.tts.speak("训练已结束。")
            return

        self._session_log.record_session(self._last_training_body_region)

        summary_text = ''
        if self.dynamic_updater:
            update = self.dynamic_updater.update(
                session_score=result['session_score'],
                session_details=result
            )

            old_score = update['old_score']
            new_score = update['new_score']
            self.current_score = new_score

            prompt = self.prompt_builder.build_session_summary(
                level=level,
                actions_completed=result.get('actions_completed', []),
                old_score=old_score,
                new_score=new_score,
                upgrade_suggestion=update.get('upgrade_suggestion'),
            )
            summary_text = self.llm.generate(
                prompt['system'], prompt['user']
            )

            print(f"\n[训练总结] {summary_text}")
            self.tts.speak_and_wait(summary_text)
            self.qt_interface.send_session_summary(summary_text)

            if update.get('upgrade_suggestion'):
                suggestion = update['upgrade_suggestion']
                upgrade_text = (
                    f"您的表现非常好！建议从{suggestion['from']}级"
                    f"升到{suggestion['to']}级，是否同意？"
                )
                self.tts.speak(upgrade_text)
                self.qt_interface.send_level_change(
                    old_level=suggestion['from'],
                    new_level=suggestion['to'],
                    reason=suggestion['reason']
                )

            if update.get('downgrade_suggestion'):
                down = update['downgrade_suggestion']
                self.current_level = down['to']
                self.tts.speak(
                    f"最近几次训练有些吃力，我们先回到"
                    f"{down['to']}级巩固一下。"
                )

            print(f"\n训练结束！评分: {old_score:.0f} → {new_score:.0f}")

        train_scoring = self._build_training_scoring_payload(level, result)
        if summary_text:
            train_scoring['advice'] = summary_text
        self.qt_interface.send_scoring(**train_scoring)

        # 同步更新评估页/首页的综合分（六维仍来自最近一次 IMU 评估）
        if self.current_score is not None and self._last_dimension_scores:
            self._push_assessment_scoring_to_qt()

        region = self._last_training_body_region
        if region == 'upper' and self.level_manager.get_actions_by_region(
            level, 'lower'
        ):
            self._emit_training_state(
                phase='block_complete',
                body_region=region,
                suggest_next_region='lower',
                message=(
                    '上肢练好了！可以休息两分钟，再点「下肢训练」继续。'
                    '请稍向后半步，画面对准腿部。'
                ),
            )

    def pause_training(self, payload: dict = None):
        """暂停训练（冻结计次与纠正）。"""
        if not self._active_session:
            self._emit_training_state(phase='idle', message='当前无训练')
            return
        self._active_session.pause()
        self._emit_training_state(phase='paused', level=self._active_session.level)
        self.tts.speak("训练已暂停。")

    def resume_training(self, payload: dict = None):
        """继续训练。"""
        if not self._active_session:
            self._emit_training_state(phase='idle', message='当前无训练')
            return
        self._active_session.resume()
        self._emit_training_state(
            phase='running', level=self._active_session.level
        )
        self.tts.speak("继续训练，加油！")

    def stop_training(self, payload: dict = None):
        """结束训练会话。"""
        if self._active_session:
            self._active_session.stop()
        self.is_training = False
        self._emit_training_state(phase='stopped', message='训练已结束')
        self.tts.speak("训练已结束，辛苦了。")

    def _handle_upgrade_confirm(self, payload: dict):
        """处理升级确认"""
        target = payload.get('target_level', '')
        if self.dynamic_updater and target:
            success = self.dynamic_updater.confirm_upgrade(target)
            if success:
                self.current_level = target
                self.tts.speak(f"恭喜！已升级到{target}级！")
                print(f"[升级] 已升级到 {target}")

    def _print_status(self):
        """打印系统状态"""
        print("\n--- 系统状态 ---")
        print(f"  当前等级: {self.current_level or '未评估'}")
        print(f"  当前评分: {self.current_score or '未评估'}")
        paused = (
            self._active_session.is_paused
            if self._active_session else False
        )
        print(f"  训练中: {self.is_training}  暂停: {paused}")
        print(f"  IMU: {self.imu_interface.get_diagnostics()}")
        print(f"  Qt: {self.qt_interface.get_diagnostics()}")
        print(f"  融合帧数: {self.fusion_engine.frame_count}")

        if self.dynamic_updater:
            trend = self.dynamic_updater.get_trend()
            print(f"  趋势: {trend['direction']}")
        print("---")

    def _send_assessment_plan(self):
        """向 Qt 推送初评指导方案。"""
        if hasattr(self, 'tts') and self.tts:
            self.tts.precache_assessment(background=True)
        self.qt_interface.send_assessment_plan(plan_for_qt())

    def _set_tts_volume(self, payload: dict = None):
        payload = payload or {}
        volume = payload.get('volume')
        if volume is None:
            return
        try:
            v = float(volume)
        except (TypeError, ValueError):
            return
        if v > 1.0:
            v = v / 100.0
        self.tts.set_volume(v)
        self._audio_config['volume'] = self.tts.get_volume()
        print(f"[TTS] 音量已设为 {self.tts.get_volume():.0%}")

    def _set_tts_speed(self, payload: dict = None):
        payload = payload or {}
        rate = payload.get('tts_rate')
        speed = payload.get('speed')
        if rate is None and speed is not None:
            try:
                rate = int(float(speed) / 100.0 * 160)
            except (TypeError, ValueError):
                return
        if rate is None:
            return
        try:
            self.tts.set_rate(int(rate))
        except (TypeError, ValueError):
            return
        self._audio_config['rate'] = self.tts.get_rate()
        print(f"[TTS] 语速已设为 {self.tts.get_rate()}")

    def _send_training_plan(self, payload: dict = None):
        """向 Qt 推送指定等级与分块的训练方案。"""
        payload = payload or {}
        level = payload.get('level') or self.current_level or 'L2'
        if isinstance(level, int):
            level = f'L{level}'
        elif isinstance(level, str):
            level = level.strip().upper()
            if level.isdigit():
                level = f'L{level}'

        body_region = normalize_region(payload.get('body_region', 'upper'))
        block = get_block_info(body_region)
        level_info = self.level_manager.get_level_info(level)
        actions_cfg = self.level_manager.get_training_sequence(
            level, body_region=body_region
        )
        actions = []
        for ac in actions_cfg:
            joints = ac.get('joints') or []
            target = joints[0].get('target_angle') if joints else None
            actions.append({
                'id': ac.get('id', ''),
                'name': ac.get('name', ''),
                'description': ac.get('description', ''),
                'target_angle': target,
                'body_region': ac.get('body_region', body_region),
            })

        has_integration = self._level_has_integration(level)
        suggest_integration = (
            body_region != 'integration'
            and has_integration
            and (
                level == 'L4'
                or self._session_log.should_suggest_integration()
            )
        )

        self.qt_interface.send_training_plan(
            level=level,
            level_name=level_info.get('name', level),
            description=level_info.get('description', ''),
            actions=actions,
            body_region=body_region,
            block_label=block.get('label', ''),
            camera_preset=block.get('camera_preset', 'upper_body'),
            setup_hint=block.get('setup_tts', ''),
            suggest_integration=suggest_integration,
            has_integration=has_integration,
        )

    def _build_training_scoring_payload(self, level: str, result: dict) -> dict:
        """从训练结果组装 scoring 消息字段。"""
        actions = result.get('actions_completed') or []
        action_names = [
            a.get('name', f'动作{i + 1}') for i, a in enumerate(actions)
        ]
        action_scores = [
            round(float(a.get('score', 0)), 1) for a in actions
        ]
        dimension_scores = {
            f'block_{i + 1}': score
            for i, score in enumerate(action_scores)
        }
        level_info = self.level_manager.get_level_info(level)
        return {
            'total_score': result.get('session_score', 0),
            'dimension_scores': dimension_scores,
            'level': level,
            'level_name': level_info.get('name', level),
            'action_names': action_names,
            'action_scores': action_scores,
            'source': 'training',
        }

    def _push_training_scoring(self, level: str, result: dict):
        """训练结束后推送真实得分给 Qt。"""
        if not result:
            return
        payload = self._build_training_scoring_payload(level, result)
        self.qt_interface.send_scoring(**payload)

    def _send_system_status(self):
        """推送系统状态给Qt"""
        phase = 'idle'
        if self.is_training and self._active_session:
            phase = 'paused' if self._active_session.is_paused else 'running'
        self.qt_interface.send_system_status(
            status_text="系统运行正常",
            cpu_usage=0,
            memory_usage=0,
            tts_volume=self.tts.get_volume(),
            tts_rate=self.tts.get_rate(),
            imu=self._imu_status_payload(),
        )
        self.qt_interface.send_training_state(
            phase=phase,
            level=self.current_level,
        )
        self._send_assessment_plan()
        if self.current_score is not None and self.current_level:
            self.qt_interface.send_scoring(
                total_score=self.current_score,
                dimension_scores=getattr(
                    self, '_last_dimension_scores', {}
                ),
                level=self.current_level,
                source='assessment',
            )
        self._send_training_plan({'level': self.current_level or 'L2'})

    def shutdown(self):
        """关闭系统"""
        print("\n正在关闭系统...")
        self.is_running = False
        self.is_training = False

        if self._debug_thread and self._debug_thread.is_alive():
            self._debug_thread.join(timeout=2.0)

        if hasattr(self, 'vision_pipeline'):
            self.vision_pipeline.stop()
        self.imu_interface.stop()
        self.qt_interface.stop()
        if hasattr(self, 'tts') and hasattr(self.tts, 'stop_worker'):
            self.tts.stop_worker()
        if hasattr(self, 'llm') and hasattr(self.llm, 'release'):
            self.llm.release()

        print("系统已安全关闭。")


# ==================== 程序入口 ====================

def main():
    parser = argparse.ArgumentParser(
        description='智能康复训练系统'
    )
    parser.add_argument(
        '--simulate', action='store_true', default=True,
        help='使用模拟模式（无需硬件）'
    )
    parser.add_argument(
        '--real', action='store_true',
        help='使用真实硬件模式'
    )
    parser.add_argument(
        '--config', type=str, default=None,
        help='配置文件目录路径'
    )
    parser.add_argument(
        '--show-vision', action='store_true',
        help='显示 OpenCV 调试窗口（需 --real）'
    )
    parser.add_argument(
        '--rknn', action='store_true',
        help='使用 RKNN 姿态模型（RK3588 NPU，需 models/yolov8n-pose.rknn）'
    )
    parser.add_argument(
        '--qt-service', action='store_true',
        help='Qt 界面服务模式（无终端交互，由 Qt 发指令）'
    )

    args = parser.parse_args()

    simulate = not args.real

    system = RehabSystem(
        config_path=args.config,
        simulate=simulate,
        show_vision_debug=args.show_vision,
        use_rknn=args.rknn,
    )

    if args.qt_service:
        system.run_qt_service()
    else:
        system.run_interactive()


if __name__ == '__main__':
    main()
