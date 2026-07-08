"""
微雪 AR0144 双目摄像头（USB / Windows DSHOW）打开与 MJPG 协商。
供 CameraManager 与 tests/test_camera.py 共用。
"""

import sys
import time

try:
    import cv2
except ImportError:
    cv2 = None

STEREO_DEVICE_ID = 0
LAPTOP_DEVICE_ID = 1

AR0144_WIDTH = 2560
AR0144_HEIGHT = 720
AR0144_FPS = 30
AR0144_FOURCC = None
if cv2 is not None:
    AR0144_FOURCC = cv2.VideoWriter_fourcc(*'MJPG')

AR0144_MJPG_MODES = (
    (2560, 720),
    (1600, 600),
    (1280, 720),
    (1280, 480),
)

_IS_WIN = sys.platform == 'win32'

if cv2 is not None and hasattr(cv2, 'setLogLevel'):
    cv2.setLogLevel(getattr(cv2, 'LOG_LEVEL_ERROR', 3))


def _v4l2_backend() -> int:
    if not _IS_WIN and hasattr(cv2, 'CAP_V4L2'):
        return cv2.CAP_V4L2
    return 0


def _open_with_backend(device_id: int, backend: int = 0):
    backend = backend or _v4l2_backend()
    if backend:
        return cv2.VideoCapture(device_id, backend)
    return cv2.VideoCapture(device_id)


def _fourcc_to_str(fourcc_val: int) -> str:
    raw = "".join(chr((int(fourcc_val) >> (8 * i)) & 0xFF) for i in range(4))
    cleaned = "".join(c if c.isprintable() else "?" for c in raw).strip()
    return cleaned or raw


def _safe_grab(cap) -> bool:
    try:
        return bool(cap.grab())
    except cv2.error:
        return False


def _safe_read_frame(cap):
    try:
        if not cap.grab():
            return False, None
        ret, frame = cap.retrieve()
    except cv2.error:
        return False, None
    if not ret or frame is None or frame.size == 0 or len(frame.shape) < 2:
        return False, None
    h, w = frame.shape[:2]
    if w < 2 or h < 2:
        return False, None
    return True, frame


def read_frame(cap):
    """
    DSHOW + MJPG：优先 cap.read()（与 AMCap 一致），失败再用 grab/retrieve。
    斜纹花屏常见于 read/grab 与当前编码不匹配。
    """
    try:
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0 and len(frame.shape) >= 2:
            h, w = frame.shape[:2]
            if w >= 2 and h >= 2:
                return True, frame
    except cv2.error:
        pass
    return _safe_read_frame(cap)


def flush_capture(cap, count: int = 15) -> None:
    """丢弃启动后前几帧（缓冲里常有损坏帧）。"""
    for _ in range(count):
        read_frame(cap)


def reapply_mjpg_mode(cap, width: int, height: int) -> None:
    """重新锁定 MJPG + 分辨率（fourcc_last 在 DSHOW 上最稳）。"""
    _apply_capture_mode(cap, width, height, 'fourcc_last')
    flush_capture(cap, 8)


def is_garbled_frame(frame) -> bool:
    """
    粗判斜纹/花屏：MJPG 未就绪或按 YUY2 解析时常见。
    """
    import numpy as np
    if frame is None or frame.size == 0:
        return True
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    row_jump = float(np.abs(np.diff(gray.mean(axis=1))).mean())
    col_jump = float(np.abs(np.diff(gray.mean(axis=0))).mean())
    if lap_var > 12000 and max(row_jump, col_jump) > 35:
        return True
    if row_jump > 55 and col_jump > 55:
        return True
    return False


def _open_dshow_primed(device_id: int):
    cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FOURCC, AR0144_FOURCC)
        _safe_grab(cap)
        cap.release()
    cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FOURCC, AR0144_FOURCC)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _apply_capture_mode(cap, width: int, height: int, order: str) -> None:
    mjpg = AR0144_FOURCC
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if order == "fourcc_first":
        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    elif order == "fourcc_last":
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
    elif order == "ffmpeg_order":
        cap.set(cv2.CAP_PROP_FPS, AR0144_FPS)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
    for _ in range(3):
        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        _safe_grab(cap)


def _frame_size(cap) -> tuple[int, int]:
    ok, frame = _safe_read_frame(cap)
    if ok:
        h, w = frame.shape[:2]
        return w, h
    return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))


def _open_dshow_settings_dialog(cap) -> None:
    if not _IS_WIN or not hasattr(cv2, 'CAP_PROP_SETTINGS'):
        return
    print("[Camera] 请在弹出窗口选择 MJPG 2560×720")
    cap.set(cv2.CAP_PROP_SETTINGS, 1)
    time.sleep(0.5)
    for _ in range(8):
        _safe_grab(cap)


def _measure_capture_fps(cap, sample_seconds: float = 0.35) -> float:
    for _ in range(5):
        _safe_grab(cap)
    n = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < sample_seconds:
        ok, _ = _safe_read_frame(cap)
        if ok:
            n += 1
    elapsed = time.perf_counter() - t0
    if elapsed <= 0 or n == 0:
        return 0.0
    fps = n / elapsed
    return 0.0 if fps > 120 else fps


def _score_ar0144_candidate(fw: int, measured_fps: float) -> float:
    if fw >= AR0144_WIDTH:
        if measured_fps >= 18:
            return 2000 + measured_fps
        return 150 + measured_fps
    if fw >= AR0144_WIDTH // 2 and measured_fps >= 18:
        return 400 + measured_fps
    return measured_fps


def _negotiate_ar0144(cap) -> tuple[int, int, float, str]:
    orders = ("fourcc_last", "ffmpeg_order", "fourcc_first")
    best = (0, 0, 0.0, "")
    for width, height in AR0144_MJPG_MODES:
        for order in orders:
            _apply_capture_mode(cap, width, height, order)
            fw, fh = _frame_size(cap)
            fps = _measure_capture_fps(cap, sample_seconds=0.45)
            tag = f"{order}@{fw}x{fh}"
            if _score_ar0144_candidate(fw, fps) > _score_ar0144_candidate(best[0], best[2]):
                best = (fw, fh, fps, tag)
            if fw >= AR0144_WIDTH and fps >= 18:
                return fw, fh, fps, tag
    return best


def open_ar0144(device_id: int = STEREO_DEVICE_ID, verbose: bool = True):
    """
    打开 AR0144 并协商 MJPG。
    Returns:
        (cap, info) 失败时 cap 为 None
    """
    if cv2 is None:
        return None, {}

    if verbose:
        print("[Camera] 正在协商 AR0144 MJPG...")
    t0 = time.perf_counter()

    cap = _open_dshow_primed(device_id) if _IS_WIN else _open_with_backend(device_id, 0)
    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        return None, {}

    try:
        fw, fh, measured_fps, strategy = _negotiate_ar0144(cap)
        if measured_fps < 18 and _IS_WIN:
            if verbose:
                print("[Camera] 自动协商未得到 MJPG，打开属性页...")
            _open_dshow_settings_dialog(cap)
            fw, fh, measured_fps, strategy = _negotiate_ar0144(cap)
    except cv2.error:
        cap.release()
        return None, {}

    info = {
        'fourcc': _fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC)),
        'width': fw,
        'height': fh,
        'fps': cap.get(cv2.CAP_PROP_FPS),
        'measured_fps': measured_fps,
        'backend': 'DSHOW' if _IS_WIN else 'AUTO',
        'strategy': strategy,
        'open_ms': (time.perf_counter() - t0) * 1000,
    }
    info['codec_guess'] = (
        'MJPG' if measured_fps >= 18 else
        ('YUY2' if measured_fps <= 10 else 'unknown')
    )

    if measured_fps < 18:
        if verbose:
            print(f"[Camera] MJPG 未就绪 (实测 {measured_fps:.1f} fps)")
        cap.release()
        return None, info

    if verbose:
        print(f"[Camera] AR0144 {fw}x{fh} {info['codec_guess']} "
              f"~{measured_fps:.0f}fps ({info['open_ms']:.0f}ms)")
    return cap, info
