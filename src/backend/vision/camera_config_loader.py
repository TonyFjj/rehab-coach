"""
camera_config.yaml 加载（Windows 开发机 / RK3588 板端）

RK3588 上自动选用 config/camera_config.rk3588.yaml，
并启用 USB 摄像头自动检测（跳过 /dev/video0 等板载节点）。
"""

import os
import platform
import sys
from typing import Optional, Tuple

import yaml

from .camera_detect import is_auto_device, normalize_device_id

RKNN_POSE_IMGSZ = 640


def is_rk3588_board() -> bool:
    return sys.platform == 'linux' and platform.machine() in (
        'aarch64', 'arm64', 'armv8', 'armv7l',
    )


def camera_yaml_path(config_dir: str) -> str:
    """返回应使用的 camera yaml 绝对路径。"""
    rk3588 = os.path.join(config_dir, 'camera_config.rk3588.yaml')
    generic = os.path.join(config_dir, 'camera_config.yaml')
    if is_rk3588_board() and os.path.isfile(rk3588):
        return rk3588
    return generic


def load_camera_yaml(config_dir: str, yaml_path: Optional[str] = None) -> Tuple[str, dict]:
    path = yaml_path or camera_yaml_path(config_dir)
    if not os.path.isfile(path):
        return path, {}
    with open(path, 'r', encoding='utf-8') as f:
        return path, yaml.safe_load(f) or {}


def build_camera_runtime_config(
    raw: dict,
    project_root: str,
    *,
    device_override=None,
    force_auto: bool = False,
    use_rknn: bool = False,
) -> dict:
    cam = raw.get('camera', raw) if raw else {}
    cal = raw.get('calibration', {}) if raw else {}
    vis = raw.get('vision', {}) if raw else {}

    if device_override is not None:
        device_id = normalize_device_id(device_override, 0)
    else:
        device_id = normalize_device_id(cam.get('device_id', 0), 0)

    auto_detect = bool(cam.get('auto_detect', False))
    auto_detect = auto_detect or is_auto_device(device_id) or force_auto

    if is_rk3588_board() and device_override is None and not force_auto:
        if not auto_detect and device_id in (0, 'auto'):
            auto_detect = True
            device_id = 'auto'

    cal_file = cam.get('calibration_file', 'config/stereo_calib.json')
    if not os.path.isabs(cal_file):
        cal_file = os.path.join(project_root, cal_file)

    inference_imgsz = int(vis.get('inference_imgsz', 640))
    pose_backend = vis.get('pose_backend', 'pt')
    if use_rknn or pose_backend == 'rknn':
        pose_backend = 'rknn'
        if inference_imgsz != RKNN_POSE_IMGSZ:
            print(
                f"[Config] RKNN 模型输入为 {RKNN_POSE_IMGSZ}×{RKNN_POSE_IMGSZ}，"
                f"已将 inference_imgsz 从 {inference_imgsz} 调整为 {RKNN_POSE_IMGSZ}"
            )
            inference_imgsz = RKNN_POSE_IMGSZ

    return {
        'device_id': device_id,
        'width': int(cam.get('width', 2560)),
        'height': int(cam.get('height', 720)),
        'fps': int(cam.get('fps', 30)),
        'mode': cam.get('mode', 'single_device'),
        'camera_model': cam.get('model', 'AR0144'),
        'auto_detect': auto_detect,
        'max_probe': int(cam.get('max_probe', 32)),
        'device_path': str(cam.get('device_path', '') or '').strip(),
        'open_retries': int(cam.get('open_retries', 3)),
        'hub_warmup_sec': float(cam.get('hub_warmup_sec', 1.0)),
        'calibration_file': cal_file,
        'rectify': bool(cal.get('rectify', False)),
        'rectify_alpha': float(cal.get('rectify_alpha', 0.0)),
        'rectify_crop': bool(cal.get('rectify_crop', True)),
        'rectify_preview': bool(cal.get('rectify_preview', False)),
        'pose_mode': vis.get('pose_mode', 'both'),
        'inference_imgsz': inference_imgsz,
        'pose_stride': int(vis.get('pose_stride', 1)),
        'pose_backend': pose_backend,
        'pose_device': vis.get('pose_device', 'cpu'),
        'pose_model': vis.get('pose_model', ''),
        'debug_max_width': int(vis.get('debug_max_width', 1280)),
        'debug_max_height': int(vis.get('debug_max_height', 360)),
    }


def resolve_alsa_device(audio_cfg: dict) -> Optional[str]:
    """
    解析 TTS 播放设备。
    优先级: 环境变量 REHAB_ALSA_DEVICE > 配置文件 > USB 自动检测。
    """
    from llm.tts_engine import detect_usb_alsa_device

    env = os.environ.get('REHAB_ALSA_DEVICE', '').strip()
    if env:
        return env

    audio_cfg = audio_cfg or {}
    device = str(audio_cfg.get('device', '') or '').strip()
    if device and device.lower() not in ('auto', 'default', ''):
        return device

    card = audio_cfg.get('card')
    if card is not None:
        sub = int(audio_cfg.get('subdevice', 0))
        return f'plughw:{int(card)},{sub}'

    prefer_usb = device.lower() == 'auto' or bool(audio_cfg.get('prefer_usb', False))
    if prefer_usb or is_rk3588_board():
        usb = detect_usb_alsa_device()
        if usb:
            return usb

    if device.lower() == 'default':
        return None
    return None


def build_audio_runtime_config(raw: dict, project_root: str) -> dict:
    """从 camera_config.yaml 的 audio 段构建 TTS 运行时参数。"""
    audio = raw.get('audio', {}) if raw else {}

    tts_model = audio.get('tts_model', 'assets/tts_models/vits-melo-tts-zh_en')
    if tts_model and not os.path.isabs(tts_model):
        tts_model = os.path.join(os.path.dirname(os.path.dirname(project_root)), tts_model)

    return {
        'alsa_device': resolve_alsa_device(audio),
        'backend': audio.get('backend', 'auto'),
        'rate': int(audio.get('rate', 160)),
        'volume': float(audio.get('volume', 0.9)),
        'tts_model_dir': tts_model,
        'output_dir': os.path.join(
            os.path.dirname(os.path.dirname(project_root)),
            'assets',
            audio.get('output_dir', 'tts_cache'),
        ),
    }
