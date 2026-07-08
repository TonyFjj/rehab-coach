"""
Wit-motion 双 IMU 串口读取（0x55 0x61 帧）
与 IMU_measure/collect_data.c 协议一致。
"""

import json
import os
import struct
import threading
import time
from typing import Callable, Dict, Optional

import numpy as np

ACC_RANGE = 16.0
GYRO_RANGE = 2000.0
ACC_SCALE = ACC_RANGE * 9.80665 / 32768.0
GYRO_SCALE = GYRO_RANGE / 32768.0

FRAME_HDR = bytes([0x55, 0x61])
FRAME_LEN = 20


def _parse_frame(buf: bytes) -> Optional[Dict[str, float]]:
    if len(buf) < FRAME_LEN:
        return None
    vals = struct.unpack('<9h', buf[2:20])
    ax, ay, az, wx, wy, wz, roll, pitch, yaw = vals
    return {
        'ax': ax * ACC_SCALE,
        'ay': ay * ACC_SCALE,
        'az': az * ACC_SCALE,
        'gx': wx * GYRO_SCALE,
        'gy': wy * GYRO_SCALE,
        'gz': wz * GYRO_SCALE,
        'roll': roll * 180.0 / 32768.0,
        'pitch': pitch * 180.0 / 32768.0,
        'yaw': yaw * 180.0 / 32768.0,
    }


class WitDualIMUReader:
    """左右手各一线程，解析 Wit 协议并回调。"""

    def __init__(
        self,
        port_left: str = '/dev/ttyACM0',
        port_right: str = '/dev/ttyACM1',
        baudrate: int = 115200,
        on_frame: Optional[Callable[[str, dict, float], None]] = None,
        on_status: Optional[Callable[[str, str, dict], None]] = None,
        stream_path: Optional[str] = None,
    ):
        self.port_left = port_left
        self.port_right = port_right
        self.baudrate = baudrate
        self.on_frame = on_frame
        self.on_status = on_status
        self.stream_path = stream_path
        self._running = False
        self._threads = []
        self._stream_fp = None
        self._stream_lock = threading.Lock()
        self.frame_count = {'imu_left': 0, 'imu_right': 0}
        self.last_error: Dict[str, str] = {}

    def start(self):
        if self._running:
            return
        self._running = True
        if self.stream_path:
            folder = os.path.dirname(self.stream_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            self._stream_fp = open(self.stream_path, 'a', encoding='utf-8')

        for port, imu_id in (
            (self.port_left, 'imu_left'),
            (self.port_right, 'imu_right'),
        ):
            t = threading.Thread(
                target=self._read_loop,
                args=(port, imu_id),
                daemon=True,
                name=f'wit-imu-{imu_id}',
            )
            t.start()
            self._threads.append(t)

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()
        if self._stream_fp:
            try:
                self._stream_fp.close()
            except OSError:
                pass
            self._stream_fp = None

    def _write_stream(self, imu_id: str, phys: dict, ts: float):
        if not self._stream_fp:
            return
        sid = 'L' if imu_id == 'imu_left' else 'R'
        line = json.dumps({
            'id': sid,
            'ax': round(phys['ax'], 5),
            'ay': round(phys['ay'], 5),
            'az': round(phys['az'], 5),
            'gx': round(phys['gx'], 5),
            'gy': round(phys['gy'], 5),
            'gz': round(phys['gz'], 5),
            't': ts,
        }, ensure_ascii=False)
        with self._stream_lock:
            self._stream_fp.write(line + '\n')
            self._stream_fp.flush()

    def _read_loop(self, port: str, imu_id: str):
        import serial

        while self._running:
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=self.baudrate,
                    timeout=0.05,
                )
                self.last_error.pop(imu_id, None)
                if self.on_status:
                    self.on_status(imu_id, 'connected', {'port': port})
                buf = bytearray()
                while self._running:
                    chunk = ser.read(256)
                    if not chunk:
                        continue
                    buf.extend(chunk)
                    while len(buf) >= FRAME_LEN:
                        idx = buf.find(FRAME_HDR)
                        if idx < 0:
                            buf.clear()
                            break
                        if idx > 0:
                            del buf[:idx]
                        if len(buf) < FRAME_LEN:
                            break
                        frame = bytes(buf[:FRAME_LEN])
                        del buf[:FRAME_LEN]
                        phys = _parse_frame(frame)
                        if phys is None:
                            continue
                        ts = time.time()
                        self.frame_count[imu_id] = (
                            self.frame_count.get(imu_id, 0) + 1
                        )
                        if self.on_frame:
                            self.on_frame(imu_id, phys, ts)
                        self._write_stream(imu_id, phys, ts)
                ser.close()
            except Exception as e:
                self.last_error[imu_id] = str(e)
                if self.on_status:
                    self.on_status(
                        imu_id, 'connection_error',
                        {'port': port, 'error': str(e)},
                    )
                time.sleep(2.0)

    def is_online(self, imu_id: str, timeout: float = 2.0) -> bool:
        # 由 IMUInterface 维护 last_data_time；此处仅辅助
        return self.frame_count.get(imu_id, 0) > 0
