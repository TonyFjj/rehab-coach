"""
摄像头自动检测（RK3588 / Linux 上 device_id 经常变化时使用）

扫描可用 V4L2 设备，选择能稳定出帧且分辨率最接近配置的一项。
支持 /dev/v4l/by-id/usb-* 稳定路径与环境变量 CAMERA_DEVICE。
"""

import os
import re
import struct
import sys
from typing import List, Optional, Tuple, Union

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

DeviceId = Union[int, str]
DeviceSpec = Tuple[str, Optional[Union[int, str]]]  # ('index'|'path', value)


def is_auto_device(device_id: DeviceId, auto_detect: bool = False) -> bool:
    if auto_detect:
        return True
    if isinstance(device_id, str):
        return device_id.strip().lower() in ('auto', 'any', '-1')
    if device_id is None:
        return auto_detect
    return int(device_id) < 0


def normalize_device_id(device_id: DeviceId, default: int = 0) -> DeviceId:
    if device_id is None:
        return default
    if isinstance(device_id, str):
        s = device_id.strip().lower()
        if s in ('auto', 'any', '-1'):
            return 'auto'
        try:
            return int(s)
        except ValueError:
            return default
    return int(device_id)


def _capture_backend() -> int:
    if sys.platform == 'win32' and hasattr(cv2, 'CAP_DSHOW'):
        return cv2.CAP_DSHOW
    if hasattr(cv2, 'CAP_V4L2'):
        return cv2.CAP_V4L2
    return 0


def _open_capture(index_or_path: Union[int, str]):
    backend = _capture_backend()
    if isinstance(index_or_path, str):
        if backend:
            return cv2.VideoCapture(index_or_path, backend)
        return cv2.VideoCapture(index_or_path)
    if backend:
        return cv2.VideoCapture(int(index_or_path), backend)
    return cv2.VideoCapture(int(index_or_path))


def _read_probe_frame(cap, retries: int = 3):
    for _ in range(retries):
        try:
            ok, frame = cap.read()
        except cv2.error:
            ok, frame = False, None
        if ok and frame is not None and frame.size > 0:
            h, w = frame.shape[:2]
            if w >= 32 and h >= 32:
                return True, w, h, frame
    return False, 0, 0, None


def _try_mjpg_modes(cap, target_w: int, target_h: int, fps: int) -> Tuple[int, int]:
    """尝试 MJPG + 目标分辨率（AR0144 等 USB 双目）。"""
    if not hasattr(cv2, 'VideoWriter_fourcc'):
        return 0, 0
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    modes = [
        (target_w, target_h),
        (2560, 720),
        (1280, 720),
        (1280, 480),
    ]
    seen = set()
    for w, h in modes:
        if (w, h) in seen:
            continue
        seen.add((w, h))
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if fps:
            cap.set(cv2.CAP_PROP_FPS, fps)
        ok, aw, ah, _ = _read_probe_frame(cap, retries=2)
        if ok:
            return aw, ah
    return 0, 0


def _score_candidate(
    index: int,
    width: int,
    height: int,
    target_w: int,
    target_h: int,
    name: str = '',
) -> float:
    """分数越高越优先。"""
    area = width * height
    target_area = max(target_w * target_h, 1)
    area_ratio = min(area / target_area, target_area / max(area, 1))
    stereo_bonus = 2.0 if width >= 2000 else (1.0 if width >= 1000 else 0.0)
    name_penalty = 0.0
    if name:
        lower = name.lower()
        if 'metadata' in lower or ('isp' in lower and 'main' not in lower):
            name_penalty = -5.0
    return area_ratio * 10.0 + stereo_bonus + min(index, 3) * 0.01 + name_penalty


def _is_rk_internal_node(name: str) -> bool:
    """RK3588 板载 ISP/MIPI 节点，通常不是 USB 双目。"""
    if not name:
        return False
    lower = name.lower()
    internal_markers = (
        'stream_cif', 'rkcif', 'rkisp', 'mipi_id',
        'cif_mipi', 'tools_id', 'scale_ch',
        'hdmirx', 'statistics', 'input-params', 'iqtool',
        'fbcpath', 'selfpath', 'rawrd',
    )
    return any(m in lower for m in internal_markers)


def _is_usb_camera_name(name: str) -> bool:
    if not name:
        return False
    lower = name.lower()
    markers = ('camera', 'ccb', 'ar0144', 'uvc', 'usb')
    return any(m in lower for m in markers)


def _has_video_capture(index: int) -> bool:
    """通过 V4L2 QUERYCAP 判断节点是否可采集（跳过 metadata 节点）。"""
    path = f'/dev/video{index}'
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        import fcntl
        buf = bytearray(104)
        fcntl.ioctl(fd, 0x80685600, buf)  # VIDIOC_QUERYCAP
        caps = struct.unpack_from('I', buf, 84)[0]
        device_caps = struct.unpack_from('I', buf, 88)[0]
        effective = device_caps if device_caps else caps
        capture = 0x00000001
        capture_mplane = 0x00001000
        return bool(effective & (capture | capture_mplane))
    except OSError:
        return False
    finally:
        os.close(fd)


def _video_index_from_path(path: str) -> Optional[int]:
    if not path:
        return None
    real = os.path.realpath(path)
    match = re.search(r'video(\d+)$', real)
    if match:
        return int(match.group(1))
    return None


def find_usb_camera_by_id(prefer_index0: bool = True) -> Optional[str]:
    """
    在 /dev/v4l/by-id 下查找 USB 外接摄像头稳定路径。
    UVC 通常 index0=采集、index1=metadata，优先 index0。
    """
    by_id = '/dev/v4l/by-id'
    if not os.path.isdir(by_id):
        return None

    usb_entries = []
    for name in sorted(os.listdir(by_id)):
        if not name.startswith('usb-'):
            continue
        full = os.path.join(by_id, name)
        if not os.path.islink(full):
            continue
        usb_entries.append((name, full))

    if not usb_entries:
        return None

    if prefer_index0:
        for name, full in usb_entries:
            if name.endswith('-video-index0'):
                idx = _video_index_from_path(full)
                if idx is not None and _has_video_capture(idx):
                    return full

    for name, full in usb_entries:
        idx = _video_index_from_path(full)
        if idx is not None and _has_video_capture(idx):
            return full

    return usb_entries[0][1]


def resolve_device_from_env() -> Optional[DeviceSpec]:
    raw = os.environ.get('CAMERA_DEVICE', '').strip()
    if not raw:
        return None
    if raw.startswith('/dev/'):
        return ('path', raw)
    if raw.lower() in ('auto', 'any'):
        return None
    try:
        return ('index', int(raw))
    except ValueError:
        return ('path', raw)


def _linux_video_names(max_probe: int) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    base = '/sys/class/video4linux'
    if not os.path.isdir(base):
        return out
    for entry in sorted(os.listdir(base)):
        if not entry.startswith('video'):
            continue
        try:
            idx = int(entry.replace('video', ''))
        except ValueError:
            continue
        name_path = os.path.join(base, entry, 'name')
        name = ''
        if os.path.isfile(name_path):
            try:
                with open(name_path, 'r', encoding='utf-8', errors='ignore') as f:
                    name = f.read().strip()
            except OSError:
                pass
        out.append((idx, name))
    return out


def _prioritize_linux_indices(
    named: List[Tuple[int, str]],
    max_probe: int,
) -> List[int]:
    """
    优先 USB/UVC 外接摄像头；跳过 RK3588 板载与不可采集节点。
    """
    if not named:
        return list(range(max_probe))

    usable = [
        (idx, name) for idx, name in named
        if not _is_rk_internal_node(name) and _has_video_capture(idx)
    ]
    if not usable:
        usable = [
            (idx, name) for idx, name in named
            if _has_video_capture(idx)
        ]

    if not usable:
        return list(range(max_probe))

    usb_first = sorted(
        usable,
        key=lambda item: (
            0 if _is_usb_camera_name(item[1]) else 1,
            item[0],
        ),
    )
    return [idx for idx, _ in usb_first]


def iter_candidate_indices(max_probe: int = 32) -> List[int]:
    """候选 device 索引；Linux 优先外接 UVC，跳过板载 MIPI。"""
    if sys.platform == 'linux':
        named = _linux_video_names(max_probe)
        if named:
            return _prioritize_linux_indices(named, max_probe)
    return list(range(max_probe))


def _probe_generic_modes(
    cap,
    target_w: int,
    target_h: int,
    fps: int,
) -> Tuple[int, int]:
    """非 AR0144 或 MJPG 失败时的通用分辨率试探。"""
    modes = [
        (target_w, target_h),
        (2560, 720),
        (1280, 720),
        (1280, 480),
        (640, 480),
    ]
    seen = set()
    for w, h in modes:
        if (w, h) in seen:
            continue
        seen.add((w, h))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if fps:
            cap.set(cv2.CAP_PROP_FPS, fps)
        ok, aw, ah, _ = _read_probe_frame(cap, retries=3)
        if ok:
            return aw, ah
    return 0, 0


def open_linux_capture(
    index_or_path: Union[int, str],
    target_w: int = 2560,
    target_h: int = 720,
    fps: int = 30,
    camera_model: str = 'AR0144',
    retries: int = 3,
    warmup_sec: float = 1.0,
) -> Tuple[Optional['cv2.VideoCapture'], int, int]:
    """
    Linux V4L2 打开摄像头（RK3588 板端）。
    AR0144 等 USB 双目优先 MJPG + 2560×720。
    Returns:
        (cap, actual_w, actual_h)，失败时 cap 为 None
    """
    if not HAS_CV2:
        return None, 0, 0

    import time

    attempts = max(1, int(retries))
    warmup = max(0.0, float(warmup_sec))
    last_err = None

    for attempt in range(attempts):
        if attempt > 0 and warmup > 0:
            delay = warmup * attempt
            print(
                f'[Camera] 拓展坞/USB 重试 ({attempt + 1}/{attempts})，'
                f'等待 {delay:.1f}s ...'
            )
            time.sleep(delay)

        cap = _open_capture(index_or_path)
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            last_err = 'open failed'
            continue

        try:
            model = (camera_model or 'generic').upper()
            aw, ah = 0, 0
            if model in ('AR0144', 'CCB'):
                aw, ah = _try_mjpg_modes(cap, target_w, target_h, fps)
            if aw <= 0:
                aw, ah = _probe_generic_modes(cap, target_w, target_h, fps)
            if aw <= 0:
                ok, aw, ah, _ = _read_probe_frame(cap, retries=5)
                if not ok:
                    cap.release()
                    last_err = 'no frame'
                    continue
            return cap, aw, ah
        except cv2.error as exc:
            last_err = str(exc)
            cap.release()
            continue

    if last_err:
        print(f'[Camera] V4L2 打开/读帧失败: {last_err}')
        print(
            '[Camera] 拓展坞提示: 摄像头尽量接 USB3 口；IMU 与相机'
            '分不同口；可运行 python3 scripts/list_cameras.py'
        )
    return None, 0, 0


def probe_device(
    index_or_path: Union[int, str],
    target_w: int = 2560,
    target_h: int = 720,
    fps: int = 30,
    camera_model: str = 'generic',
    device_name: str = '',
) -> Optional[dict]:
    """
    试探单个 device_id 是否可用。
    Returns:
        dict(index, width, height, score, name) 或 None
    """
    if not HAS_CV2:
        return None

    cap = _open_capture(index_or_path)
    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        return None

    try:
        model = (camera_model or 'generic').upper()
        aw, ah = 0, 0
        if model in ('AR0144', 'CCB'):
            aw, ah = _try_mjpg_modes(cap, target_w, target_h, fps)
        if aw <= 0:
            aw, ah = _probe_generic_modes(cap, target_w, target_h, fps)
        if aw <= 0:
            ok, aw, ah, _ = _read_probe_frame(cap)
            if not ok:
                return None

        if isinstance(index_or_path, int):
            index = index_or_path
        else:
            index = _video_index_from_path(str(index_or_path)) or -1

        score = _score_candidate(index, aw, ah, target_w, target_h, device_name)
        if _is_usb_camera_name(device_name):
            score += 3.0
        return {
            'index': index,
            'path': index_or_path if isinstance(index_or_path, str) else '',
            'width': aw,
            'height': ah,
            'score': score,
            'name': device_name,
        }
    finally:
        cap.release()


def autodetect_device(
    target_w: int = 2560,
    target_h: int = 720,
    fps: int = 30,
    camera_model: str = 'AR0144',
    max_probe: int = 32,
    verbose: bool = True,
) -> Optional[Union[int, str]]:
    """
    自动选择最佳摄像头 device_id 或 /dev/v4l/by-id 路径。
    板端 USB 摄像头索引常变化（如 video21），优先 by-id 再扫索引。
    """
    if not HAS_CV2:
        if verbose:
            print('[Camera] OpenCV 不可用，无法自动检测')
        return None

    by_id_path = find_usb_camera_by_id()
    if by_id_path:
        result = probe_device(
            by_id_path, target_w, target_h, fps, camera_model, 'usb-by-id'
        )
        if result is not None:
            if verbose:
                print(
                    f'[Camera] 选用稳定路径 {by_id_path} '
                    f'{result["width"]}x{result["height"]}'
                )
            return by_id_path

    names = {}
    if sys.platform == 'linux':
        for idx, name in _linux_video_names(max_probe):
            names[idx] = name

    candidates = []
    indices = iter_candidate_indices(max_probe)
    if verbose:
        print(f'[Camera] 自动检测摄像头 (探测 {indices}) ...')

    for idx in indices:
        name = names.get(idx, '')
        result = probe_device(
            idx, target_w, target_h, fps, camera_model, name
        )
        if result is None:
            if verbose:
                tag = f' "{name}"' if name else ''
                print(f'  video{idx}{tag}: 不可用')
            continue
        candidates.append(result)
        if verbose:
            tag = f' "{name}"' if name else ''
            print(
                f'  video{idx}{tag}: OK '
                f'{result["width"]}x{result["height"]} '
                f'score={result["score"]:.2f}'
            )

    if not candidates:
        if verbose:
            print('[Camera] 自动检测失败：未发现可用摄像头')
            print('[Camera] 请运行: python3 scripts/list_cameras.py')
            print('[Camera] 或在 config/camera_config.rk3588.yaml 设置 device_id: 21')
        return None

    best = max(candidates, key=lambda c: c['score'])
    if verbose:
        bn = best.get('name') or ''
        tag = f' ({bn})' if bn else ''
        picked = best.get('path') or best['index']
        print(
            f'[Camera] 选用 device={picked}{tag} '
            f'{best["width"]}x{best["height"]}'
        )
    if best.get('path'):
        return best['path']
    return int(best['index'])


def resolve_camera_open_target(
    device_id: DeviceId,
    device_path: Optional[str] = None,
    auto_detect: bool = False,
    target_w: int = 2560,
    target_h: int = 720,
    fps: int = 30,
    camera_model: str = 'AR0144',
    max_probe: int = 32,
    verbose: bool = True,
) -> Optional[Union[int, str]]:
    """
    解析最终打开目标：环境变量 > device_path > auto > 固定 device_id。
    Returns:
        int 索引、/dev/... 路径，或 None
    """
    env_spec = resolve_device_from_env()
    if env_spec is not None:
        kind, value = env_spec
        if verbose:
            print(f'[Camera] 使用环境变量 CAMERA_DEVICE={value}')
        return value

    path_cfg = (device_path or '').strip()
    if path_cfg.startswith('/dev/') and path_cfg.lower() != 'auto':
        if verbose:
            print(f'[Camera] 使用配置路径: {path_cfg}')
        return path_cfg

    if auto_detect or is_auto_device(device_id) or path_cfg.lower() == 'auto':
        return autodetect_device(
            target_w=target_w,
            target_h=target_h,
            fps=fps,
            camera_model=camera_model,
            max_probe=max_probe,
            verbose=verbose,
        )

    return normalize_device_id(device_id, 0)
