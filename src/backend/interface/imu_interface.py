"""
IMU 数据接口

运行模式：
  1. bluetooth / usb_serial — 本模块读串口并解析二进制/JSON 帧（旧方案）
  2. txt — 读 IMU 同学写入的 txt（推荐：对方负责采集与运算，你们只读文件）
  3. simulate — 开发用模拟数据

txt 模式：支持单文件（每行含左右手 id）或左右各一个文件；默认 tail 追新行。
"""

import os
import time
import threading
import queue
import struct
import json
import numpy as np
from typing import Dict, Optional, Callable, List, Union


def _looks_numeric(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


class IMUInterface:
    """
    IMU蓝牙串口数据接收接口

    支持两种数据格式：
    1. JSON文本格式（调试用，带宽大但可读）
    2. 二进制紧凑格式（正式用，带宽小延迟低）

    支持四种运行模式：
    1. bluetooth: 蓝牙串口 /dev/rfcommX
    2. usb_serial: USB 串口 /dev/ttyUSBX 或 COMx
    3. txt: 读取 IMU 同学输出的 txt（无需串口协议）
    4. simulate: 模拟数据（开发调试）
    """

    DEFAULT_IMU_HZ = 100

    # ============ 二进制帧协议定义 ============
    # 帧头(2) + IMU_ID(1) + accel(12) + gyro(12) + 校验(1) + 帧尾(1)
    # 总计 29 字节
    FRAME_HEADER = b'\xAA\x55'
    FRAME_TAIL = b'\xFF'
    FRAME_LENGTH = 29

    # IMU ID映射
    IMU_ID_MAP = {
        0x01: 'imu_left',
        0x02: 'imu_right',
    }

    def __init__(
        self,
        mode: str = 'txt',
        port: str = '/dev/rfcomm0',
        baudrate: int = 115200,
        data_format: str = 'binary',
        simulate: bool = False,
        txt_path: Union[str, Dict[str, str], None] = None,
        txt_follow: bool = True,
        txt_poll_interval: float = 0.01,
        dual_ports: Optional[Dict[str, str]] = None,
        stream_path: Optional[str] = None,
        write_stream_file: bool = True,
    ):
        """
        Args:
            mode: 'bluetooth' | 'usb_serial' | 'txt' | 'dual_serial' | 'simulate'
            port: 串口路径（txt 模式可忽略）
            baudrate: 串口波特率
            data_format: 串口数据格式 ('binary' | 'json')
            simulate: 强制模拟模式
            txt_path: txt 模式路径。可为：
                - 单文件 str（每行一条记录，含 imu_id）
                - dict {'imu_left': '...', 'imu_right': '...'}
                默认 data/imu/imu_stream.txt
            txt_follow: True=实时追读文件末尾；False=按 100Hz 回放整个文件
            txt_poll_interval: 追读时轮询间隔(秒)
        """
        self.mode = mode if not simulate else 'simulate'
        self.port = port
        self.baudrate = baudrate
        self.data_format = data_format
        self.txt_follow = txt_follow
        self.txt_poll_interval = txt_poll_interval
        self._txt_files: Dict[str, str] = self._normalize_txt_paths(txt_path)
        self._txt_offsets: Dict[str, int] = {k: 0 for k in self._txt_files}
        self._dual_ports = dual_ports or {
            'left': '/dev/ttyACM0',
            'right': '/dev/ttyACM1',
        }
        self._stream_path = stream_path
        self._write_stream_file = write_stream_file
        self._wit_reader = None

        # 数据缓冲队列
        self._data_queue: queue.Queue = queue.Queue(maxsize=500)

        # 回调
        self._on_imu_data: Optional[Callable] = None
        self._on_imu_status: Optional[Callable] = None

        # 线程
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None

        # 串口连接
        self._serial_conn = None

        # 连接状态
        self._connected_imus: Dict[str, dict] = {}
        self._last_data_time: Dict[str, float] = {}

        # 标定
        self._calibrating = False
        self._calibration_samples: Dict[str, list] = {
            'imu_left': [],
            'imu_right': [],
        }
        self._calibration_target_count = 300

        # 左右手映射校准（按物理串口 port_left/port_right 统计，不受 lr_swap 影响）
        self._lr_swap: bool = False
        self._lr_motion_collecting: bool = False
        self._lr_motion_energy: Dict[str, float] = {
            'port_left': 0.0,
            'port_right': 0.0,
        }
        self._lr_motion_samples: Dict[str, int] = {
            'port_left': 0,
            'port_right': 0,
        }
        self._lr_lock = threading.Lock()

        # 二进制解析缓冲区
        self._recv_buffer = bytearray()

        # 统计
        self._frame_count = 0
        self._error_count = 0
        self._crc_error_count = 0
        self._txt_line_errors = 0

    @staticmethod
    def _normalize_txt_paths(
        txt_path: Union[str, Dict[str, str], None],
    ) -> Dict[str, str]:
        if isinstance(txt_path, dict):
            return dict(txt_path)
        if isinstance(txt_path, str) and txt_path:
            return {'_single': txt_path}
        default = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'imu', 'imu_stream.txt',
        )
        return {'_single': default}

    # ==================== 回调设置 ====================

    def set_callbacks(
        self,
        on_imu_data: Callable = None,
        on_imu_status: Callable = None
    ):
        """
        设置回调函数

        Args:
            on_imu_data: IMU数据到达回调
                签名: (imu_id: str, accel: np.ndarray, gyro: np.ndarray,
                        timestamp: float) -> None
            on_imu_status: IMU状态变化回调
                签名: (imu_id: str, status: str, info: dict) -> None
        """
        self._on_imu_data = on_imu_data
        self._on_imu_status = on_imu_status

    # ==================== 初评结果文件 ====================

    @staticmethod
    def load_assessment_result(path: str) -> Optional[dict]:
        """
        读取 IMU 同学写入的 assessment_result.txt（一行 JSON）。

        Returns:
            {'total_score', 'level', 'dimension_scores', 'timestamp'} 或 None
        """
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        except OSError:
            return None
        if not lines:
            return None

        for line in reversed(lines):
            if line.startswith('#'):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get('event') != 'assessment_result':
                continue
            dims = data.get('dimension_scores') or {}
            total = float(data.get('total_score', 0))
            if dims:
                total = round(float(sum(float(v) for v in dims.values())), 1)
            return {
                'total_score': total,
                'level': str(data['level']),
                'dimension_scores': dims,
                'timestamp': data.get('timestamp'),
                'source': data.get('source', 'imu_file'),
                'lr_scores': data.get('lr_scores') or {},
                'note': data.get('note', ''),
                'scoring_mode': data.get('scoring_mode', ''),
                'tcn_lr': data.get('tcn_lr') or {},
            }
        return None

    # ==================== 启动/停止 ====================

    def start(self):
        """启动IMU数据接收"""
        if self._running:
            print("[IMU] 已经在运行中")
            return

        self._running = True
        if self.mode == 'dual_serial':
            ports = self._dual_ports
            print(
                f"[IMU] 启动接收，模式: dual_serial, "
                f"L={ports.get('left')} R={ports.get('right')}"
            )
        elif self.mode in ('bluetooth', 'usb_serial'):
            print(f"[IMU] 启动接收，模式: {self.mode}, 端口: {self.port}")
        else:
            print(f"[IMU] 启动接收，模式: {self.mode}")

        if self.mode in ('bluetooth', 'usb_serial'):
            self._start_serial()
        elif self.mode == 'txt':
            self._start_txt()
        elif self.mode == 'dual_serial':
            self._start_dual_serial()
        elif self.mode == 'simulate':
            self._start_simulate()
        else:
            print(f"[IMU] 未知模式 {self.mode}，回退为 simulate")
            self.mode = 'simulate'
            self._start_simulate()

    def stop(self):
        """停止IMU数据接收"""
        self._running = False

        if self._serial_conn:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None

        if self._wit_reader:
            self._wit_reader.stop()
            self._wit_reader = None

        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=3.0)

        print("[IMU] 已停止")

    # ==================== 串口模式（蓝牙/USB通用） ====================

    def _start_serial(self):
        """启动串口接收（蓝牙串口和USB串口共用逻辑）"""
        self._recv_thread = threading.Thread(
            target=self._serial_recv_loop,
            daemon=True,
            name="imu-serial"
        )
        self._recv_thread.start()

    def _serial_recv_loop(self):
        """串口接收主循环"""
        # 尝试连接，支持自动重连
        while self._running:
            if not self._open_serial():
                print(f"[IMU] 等待 5 秒后重试连接 {self.port} ...")
                time.sleep(5.0)
                continue

            # 连接成功，开始收数据
            self._notify_status('system', 'serial_opened', {
                'port': self.port,
                'mode': self.mode,
                'baudrate': self.baudrate,
            })

            self._recv_buffer = bytearray()

            while self._running:
                try:
                    if self.data_format == 'binary':
                        self._recv_binary()
                    else:
                        self._recv_json()
                except Exception as e:
                    self._error_count += 1
                    if self._error_count % 50 == 1:
                        print(f"[IMU] 读取错误 (累计{self._error_count}): {e}")

                    # 连接可能断了，跳出内层循环触发重连
                    if 'disconnected' in str(e).lower() or \
                       'device' in str(e).lower() or \
                       'Input/output error' in str(e):
                        self._notify_status('system', 'disconnected', {})
                        break

                    time.sleep(0.01)

            # 关闭旧连接
            if self._serial_conn:
                try:
                    self._serial_conn.close()
                except Exception:
                    pass
                self._serial_conn = None

    def _open_serial(self) -> bool:
        """打开串口连接"""
        try:
            import serial
            self._serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            print(f"[IMU] 串口已打开: {self.port} @ {self.baudrate}")
            return True

        except ImportError:
            print("[IMU] pyserial未安装，请执行: pip install pyserial")
            print("[IMU] 切换到模拟模式")
            self.mode = 'simulate'
            self._start_simulate()
            return False

        except Exception as e:
            print(f"[IMU] 串口打开失败: {e}")
            return False

    # ==================== 二进制帧解析 ====================

    def _recv_binary(self):
        """
        接收并解析二进制帧

        帧格式（29字节）：
        +------+------+--------+-------------------+-------------------+------+------+
        | 0xAA | 0x55 | IMU_ID | accel_x/y/z(f32)  | gyro_x/y/z(f32)   | CRC8 | 0xFF |
        +------+------+--------+-------------------+-------------------+------+------+
        | 1B   | 1B   | 1B     | 4B×3 = 12B        | 4B×3 = 12B        | 1B   | 1B   |
        +------+------+--------+-------------------+-------------------+------+------+

        accel单位: m/s²（float32, 小端序）
        gyro单位:  °/s （float32, 小端序）
        CRC8: 从IMU_ID到gyro_z的所有字节的异或校验
        """
        if not self._serial_conn or not self._serial_conn.is_open:
            time.sleep(0.1)
            return

        # 读取可用数据
        available = self._serial_conn.in_waiting
        if available > 0:
            raw = self._serial_conn.read(available)
            self._recv_buffer.extend(raw)

        # 解析缓冲区中的完整帧
        while len(self._recv_buffer) >= self.FRAME_LENGTH:
            # 寻找帧头
            header_pos = self._find_header()
            if header_pos < 0:
                # 没找到帧头，清空垃圾数据
                self._recv_buffer.clear()
                break

            # 跳过帧头前的垃圾数据
            if header_pos > 0:
                self._recv_buffer = self._recv_buffer[header_pos:]

            # 检查是否有完整帧
            if len(self._recv_buffer) < self.FRAME_LENGTH:
                break

            # 提取一帧
            frame = bytes(self._recv_buffer[:self.FRAME_LENGTH])
            self._recv_buffer = self._recv_buffer[self.FRAME_LENGTH:]

            # 校验帧尾
            if frame[-1:] != self.FRAME_TAIL:
                self._error_count += 1
                continue

            # CRC校验（IMU_ID到gyro_z，即 frame[2:27]）
            data_section = frame[2:27]
            crc_received = frame[27]
            crc_calc = self._calc_crc8(data_section)
            if crc_calc != crc_received:
                self._crc_error_count += 1
                if self._crc_error_count % 20 == 1:
                    print(f"[IMU] CRC校验失败 "
                          f"(累计{self._crc_error_count})")
                continue

            # 解析数据
            imu_id_byte = frame[2]
            imu_id = self.IMU_ID_MAP.get(imu_id_byte, f'imu_{imu_id_byte}')

            # 小端序float32解包
            accel = np.array(
                struct.unpack('<3f', frame[3:15]),
                dtype=np.float64
            )
            gyro = np.array(
                struct.unpack('<3f', frame[15:27]),
                dtype=np.float64
            )

            self._process_imu_data(imu_id, accel, gyro, time.time())

    def _find_header(self) -> int:
        """在缓冲区中查找帧头 0xAA 0x55 的位置"""
        for i in range(len(self._recv_buffer) - 1):
            if self._recv_buffer[i] == 0xAA and \
               self._recv_buffer[i + 1] == 0x55:
                return i
        return -1

    @staticmethod
    def _calc_crc8(data: bytes) -> int:
        """计算CRC8校验（异或校验）"""
        crc = 0
        for b in data:
            crc ^= b
        return crc

    # ==================== JSON文本帧解析 ====================

    def _recv_json(self):
        """
        接收JSON格式数据（调试用）

        每行一条JSON：
        {"id":"L","ax":0.1,"ay":-0.2,"az":9.8,"gx":1.5,"gy":-0.8,"gz":0.3}
        """
        import json

        if not self._serial_conn or not self._serial_conn.is_open:
            time.sleep(0.1)
            return

        line = self._serial_conn.readline()
        if not line:
            return

        try:
            text = line.decode('utf-8', errors='ignore').strip()
            if not text:
                return

            data = json.loads(text)

            # 解析IMU ID
            raw_id = data.get('id', data.get('imu_id', 'L'))
            if raw_id in ('L', 'left', '1', 1):
                imu_id = 'imu_left'
            elif raw_id in ('R', 'right', '2', 2):
                imu_id = 'imu_right'
            else:
                imu_id = f'imu_{raw_id}'

            accel = np.array([
                data.get('ax', 0),
                data.get('ay', 0),
                data.get('az', 9.81),
            ], dtype=np.float64)

            gyro = np.array([
                data.get('gx', 0),
                data.get('gy', 0),
                data.get('gz', 0),
            ], dtype=np.float64)

            self._process_imu_data(imu_id, accel, gyro, time.time())

        except (json.JSONDecodeError, ValueError):
            self._error_count += 1

    # ==================== 双串口 Wit 协议（IMU_measure） ====================

    def _start_dual_serial(self):
        try:
            from .imu_wit_dual import WitDualIMUReader
        except ImportError as e:
            print(f'[IMU] dual_serial 不可用: {e}，回退 txt')
            self.mode = 'txt'
            self._start_txt()
            return

        stream = self._stream_path if self._write_stream_file else None
        self._wit_reader = WitDualIMUReader(
            port_left=self._dual_ports.get('left', '/dev/ttyACM0'),
            port_right=self._dual_ports.get('right', '/dev/ttyACM1'),
            baudrate=self.baudrate,
            on_frame=self._on_wit_frame,
            on_status=self._on_wit_serial_status,
            stream_path=stream,
        )
        self._wit_reader.start()
        print(
            f'[IMU] dual_serial 启动: '
            f"L={self._dual_ports.get('left')} "
            f"R={self._dual_ports.get('right')}"
        )
        self._notify_status('system', 'dual_serial_started', {
            'ports': self._dual_ports,
            'stream_path': stream,
        })

    def _on_wit_serial_status(self, imu_id: str, status: str, info: dict):
        if status == 'connection_error':
            print(
                f"[IMU] {imu_id} 串口连接失败 "
                f"({info.get('port')}): {info.get('error')}"
            )
        self._notify_status(imu_id, status, info)

    def _on_wit_frame(self, imu_id: str, phys: dict, timestamp: float):
        accel = np.array([
            phys.get('ax', 0),
            phys.get('ay', 0),
            phys.get('az', 9.81),
        ], dtype=np.float64)
        gyro = np.array([
            phys.get('gx', 0),
            phys.get('gy', 0),
            phys.get('gz', 0),
        ], dtype=np.float64)
        port_key = (
            'port_left' if imu_id == 'imu_left' else 'port_right'
        )
        self._accumulate_lr_motion(port_key, accel, gyro)
        if self._lr_swap:
            if imu_id == 'imu_left':
                imu_id = 'imu_right'
            elif imu_id == 'imu_right':
                imu_id = 'imu_left'
        self._process_imu_data(imu_id, accel, gyro, timestamp)

    # ==================== TXT 文件模式 ====================

    def _start_txt(self):
        """从 txt 读 IMU 同学已处理好的数据"""
        for imu_id, path in self._txt_files.items():
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if not os.path.exists(path):
                open(path, 'a', encoding='utf-8').close()
                print(f"[IMU] 已创建空数据文件: {path}")

        paths = ', '.join(self._txt_files.values())
        print(f"[IMU] TXT 模式启动，读取: {paths}")
        self._notify_status('system', 'txt_watching', {
            'files': self._txt_files,
            'follow': self.txt_follow,
        })

        self._recv_thread = threading.Thread(
            target=self._txt_loop,
            daemon=True,
            name="imu-txt",
        )
        self._recv_thread.start()

    def _txt_loop(self):
        if self.txt_follow:
            while self._running:
                self._txt_poll_once()
                time.sleep(self.txt_poll_interval)
        else:
            self._txt_replay_file()

    def _txt_poll_once(self):
        for key, path in self._txt_files.items():
            default_id = key if key != '_single' else None
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(self._txt_offsets.get(key, 0))
                    for line in f:
                        parsed = self._parse_txt_line(line, default_id)
                        if parsed:
                            self._process_imu_data(**parsed)
                    self._txt_offsets[key] = f.tell()
            except OSError as e:
                self._error_count += 1
                if self._error_count % 100 == 1:
                    print(f"[IMU] 读文件失败 {path}: {e}")
                time.sleep(0.5)

    def _txt_replay_file(self):
        interval = 1.0 / self.DEFAULT_IMU_HZ
        all_rows = []
        for key, path in self._txt_files.items():
            default_id = key if key != '_single' else None
            if not os.path.exists(path):
                continue
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    parsed = self._parse_txt_line(line, default_id)
                    if parsed:
                        all_rows.append(parsed)
        all_rows.sort(key=lambda r: r['timestamp'])
        idx = 0
        while self._running:
            if not all_rows:
                time.sleep(0.2)
                continue
            row = all_rows[idx % len(all_rows)]
            self._process_imu_data(**row)
            idx += 1
            time.sleep(interval)

    def _parse_txt_line(
        self, line: str, default_imu_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        解析一行 txt。支持：
          - JSON: {"id":"L","ax":0,"ay":0,"az":9.81,"gx":0,"gy":0,"gz":0,"t":123.4}
          - CSV:  timestamp,imu_id,ax,ay,az,gx,gy,gz  （可有表头）
          - 空格分隔: imu_left 0 0 9.81 0 0 0
        与 IMU 同学对齐列顺序后可在文档中固定一种格式。
        """
        text = line.strip()
        if not text or text.startswith('#'):
            return None

        try:
            if text.startswith('{'):
                data = json.loads(text)
                raw_id = data.get('id', data.get('imu_id', default_imu_id or 'L'))
                imu_id = self._map_imu_id(raw_id)
                ts = float(data.get('t', data.get('timestamp', time.time())))
                accel = np.array([
                    data.get('ax', 0), data.get('ay', 0), data.get('az', 9.81),
                ], dtype=np.float64)
                gyro = np.array([
                    data.get('gx', 0), data.get('gy', 0), data.get('gz', 0),
                ], dtype=np.float64)
                return {
                    'imu_id': imu_id, 'accel': accel, 'gyro': gyro,
                    'timestamp': ts,
                }

            parts = [p.strip() for p in text.replace(',', ' ').split()]
            if len(parts) < 7:
                return None

            # 可选表头行
            if parts[0].lower() in ('timestamp', 'time', 't'):
                return None

            idx = 0
            ts = time.time()
            if _looks_numeric(parts[0]) and len(parts) >= 8:
                ts = float(parts[0])
                idx = 1

            if _looks_numeric(parts[idx]) and len(parts) >= 7:
                imu_id = default_imu_id or 'imu_left'
                vals = list(map(float, parts[idx:idx + 6]))
            else:
                imu_id = self._map_imu_id(parts[idx])
                vals = list(map(float, parts[idx + 1:idx + 7]))

            if len(vals) < 6:
                return None

            return {
                'imu_id': imu_id,
                'accel': np.array(vals[:3], dtype=np.float64),
                'gyro': np.array(vals[3:6], dtype=np.float64),
                'timestamp': ts,
            }
        except (ValueError, json.JSONDecodeError, KeyError):
            self._txt_line_errors += 1
            return None

    @staticmethod
    def _map_imu_id(raw_id) -> str:
        if raw_id in ('L', 'left', '1', 1, 'imu_left'):
            return 'imu_left'
        if raw_id in ('R', 'right', '2', 2, 'imu_right'):
            return 'imu_right'
        if isinstance(raw_id, str) and raw_id.startswith('imu_'):
            return raw_id
        return f'imu_{raw_id}'

    # ==================== 模拟模式 ====================

    def _start_simulate(self):
        """启动模拟数据生成"""
        self._recv_thread = threading.Thread(
            target=self._simulate_loop,
            daemon=True,
            name="imu-simulate"
        )
        self._recv_thread.start()
        print("[IMU] 模拟模式启动")

    def _simulate_loop(self):
        """
        生成模拟IMU数据
        模拟一个缓慢举手然后放下的周期动作
        """
        interval = 1.0 / self.DEFAULT_IMU_HZ
        t = 0.0

        while self._running:
            now = time.time()

            for imu_id in ['imu_left', 'imu_right']:
                # 模拟加速度（m/s²）
                ax = 0.5 * np.sin(2 * np.pi * 0.2 * t) + \
                    np.random.normal(0, 0.1)
                ay = 0.3 * np.sin(2 * np.pi * 0.15 * t) + \
                    np.random.normal(0, 0.1)
                az = 9.81 + 0.2 * np.sin(2 * np.pi * 0.1 * t) + \
                    np.random.normal(0, 0.05)
                accel = np.array([ax, ay, az])

                # 模拟角速度（°/s）
                gx = 15.0 * np.sin(2 * np.pi * 0.2 * t) + \
                    np.random.normal(0, 1.0)
                gy = 10.0 * np.sin(2 * np.pi * 0.15 * t) + \
                    np.random.normal(0, 1.0)
                gz = 5.0 * np.sin(2 * np.pi * 0.1 * t) + \
                    np.random.normal(0, 0.5)
                gyro = np.array([gx, gy, gz])

                self._process_imu_data(imu_id, accel, gyro, now)

            t += interval
            time.sleep(interval)

    # ==================== 统一数据处理 ====================

    def _process_imu_data(
        self,
        imu_id: str,
        accel: np.ndarray,
        gyro: np.ndarray,
        timestamp: float
    ):
        """
        处理一帧IMU数据（所有模式统一入口）
        """
        self._frame_count += 1
        self._last_data_time[imu_id] = time.time()

        # 首次检测到IMU
        if imu_id not in self._connected_imus:
            self._connected_imus[imu_id] = {
                'first_seen': time.time(),
                'status': 'connected',
            }
            print(f"[IMU] 检测到IMU: {imu_id}")
            self._notify_status(imu_id, 'connected', {})

        # 标定模式：收集静止数据
        if self._calibrating and imu_id in self._calibration_samples:
            samples = self._calibration_samples[imu_id]
            if len(samples) < self._calibration_target_count:
                samples.append(accel.copy())
                if len(samples) % 100 == 0:
                    print(f"[IMU] {imu_id} 标定采集: "
                          f"{len(samples)}/{self._calibration_target_count}")
                return  # 标定期间不触发数据回调

        # 非 dual_serial 模式：按逻辑左右手累计（模拟/txt）
        if self.mode != 'dual_serial' and self._lr_motion_collecting:
            port_key = (
                'port_left' if imu_id == 'imu_left' else 'port_right'
            )
            self._accumulate_lr_motion(port_key, accel, gyro)

        # 放入队列
        data_item = {
            'imu_id': imu_id,
            'accel': accel,
            'gyro': gyro,
            'timestamp': timestamp,
        }

        try:
            self._data_queue.put_nowait(data_item)
        except queue.Full:
            try:
                self._data_queue.get_nowait()
            except queue.Empty:
                pass
            self._data_queue.put_nowait(data_item)

        # 触发回调
        if self._on_imu_data:
            self._on_imu_data(imu_id, accel, gyro, timestamp)

    def _notify_status(self, imu_id: str, status: str, info: dict):
        """通知IMU状态变化"""
        if self._on_imu_status:
            self._on_imu_status(imu_id, status, info)

    # ==================== 标定接口 ====================

    def start_calibration(self, duration_seconds: float = 3.0):
        """
        开始IMU零漂标定
        要求：患者保持静止，双手自然下垂
        """
        self._calibration_target_count = int(
            duration_seconds * self.DEFAULT_IMU_HZ
        )
        self._calibration_samples = {
            'imu_left': [],
            'imu_right': [],
        }
        self._calibrating = True
        print(f"[IMU] 标定开始，请保持静止 {duration_seconds} 秒...")
        self._notify_status('system', 'calibration_started', {
            'duration': duration_seconds,
        })

    def get_calibration_result(self) -> Optional[Dict[str, dict]]:
        """
        获取标定结果

        Returns:
            {
                'imu_left': {
                    'bias': np.array([bx, by, bz]),
                    'mean': np.array([mx, my, mz]),
                    'std': np.array([sx, sy, sz]),
                    'sample_count': 300
                },
                ...
            }
        """
        result = {}

        for imu_id, samples in self._calibration_samples.items():
            if len(samples) < 50:
                print(f"[IMU] {imu_id} 标定样本不足: {len(samples)}")
                continue

            samples_arr = np.array(samples)
            mean_accel = np.mean(samples_arr, axis=0)
            std_accel = np.std(samples_arr, axis=0)

            gravity = np.array([0, 0, 9.81])
            bias = mean_accel - gravity

            result[imu_id] = {
                'bias': bias,
                'mean': mean_accel,
                'std': std_accel,
                'sample_count': len(samples),
            }

            print(f"[IMU] {imu_id} 标定完成:")
            print(f"  均值: [{mean_accel[0]:.4f}, {mean_accel[1]:.4f}, "
                  f"{mean_accel[2]:.4f}]")
            print(f"  零漂: [{bias[0]:.4f}, {bias[1]:.4f}, {bias[2]:.4f}]")

        self._calibrating = False
        self._notify_status('system', 'calibration_completed', result)

        return result if result else None

    def is_calibration_complete(self) -> bool:
        """标定数据是否采集完毕"""
        if not self._calibrating:
            return False
        for samples in self._calibration_samples.values():
            if len(samples) < self._calibration_target_count:
                return False
        return True

    # ==================== 左右手映射校准 ====================

    @staticmethod
    def _lr_motion_metric(accel: np.ndarray, gyro: np.ndarray) -> float:
        """抬手动作：角速度变化最明显，叠加加速度模长。"""
        gyro_rad = gyro * (np.pi / 180.0)
        gyro_mag2 = float(np.dot(gyro_rad, gyro_rad))
        accel_mag2 = float(np.dot(accel, accel))
        return gyro_mag2 * 8.0 + accel_mag2

    def _accumulate_lr_motion(
        self,
        port_key: str,
        accel: np.ndarray,
        gyro: np.ndarray,
    ):
        if port_key not in ('port_left', 'port_right'):
            return
        with self._lr_lock:
            if not self._lr_motion_collecting:
                return
            self._lr_motion_energy[port_key] += self._lr_motion_metric(accel, gyro)
            self._lr_motion_samples[port_key] += 1

    def start_lr_motion_capture(self):
        """开始左右手运动能量采集（按物理串口 port_left/port_right）"""
        with self._lr_lock:
            self._lr_motion_energy = {
                'port_left': 0.0,
                'port_right': 0.0,
            }
            self._lr_motion_samples = {
                'port_left': 0,
                'port_right': 0,
            }
            self._lr_motion_collecting = True
        print('[IMU] 左右手运动能量采集开始')

    def snapshot_lr_motion(self) -> dict:
        """读取当前累计值但不停止采集。"""
        with self._lr_lock:
            energy = dict(self._lr_motion_energy)
            samples = dict(self._lr_motion_samples)
        return {
            'port_left': energy.get('port_left', 0.0),
            'port_right': energy.get('port_right', 0.0),
            'port_left_samples': samples.get('port_left', 0),
            'port_right_samples': samples.get('port_right', 0),
        }

    def reset_lr_motion_counters(self):
        """清零计数器，保持采集开关不变（用于基线/动作分段）。"""
        with self._lr_lock:
            self._lr_motion_energy = {
                'port_left': 0.0,
                'port_right': 0.0,
            }
            self._lr_motion_samples = {
                'port_left': 0,
                'port_right': 0,
            }

    def stop_lr_motion_capture(self) -> dict:
        """停止采集并返回 port_left/port_right 能量与样本数。"""
        with self._lr_lock:
            self._lr_motion_collecting = False
            energy = dict(self._lr_motion_energy)
            samples = dict(self._lr_motion_samples)
        pl = energy.get('port_left', 0.0)
        pr = energy.get('port_right', 0.0)
        nl = samples.get('port_left', 0)
        nr = samples.get('port_right', 0)
        result = {
            'port_left': pl,
            'port_right': pr,
            'port_left_samples': nl,
            'port_right_samples': nr,
            # 兼容旧字段名
            'imu_left': pl,
            'imu_right': pr,
            'imu_left_samples': nl,
            'imu_right_samples': nr,
        }
        print(
            f"[IMU] 左右手运动能量采集结束: "
            f"port_L={pl:.3f}({nl}帧) port_R={pr:.3f}({nr}帧) "
            f"串口 L={self._dual_ports.get('left')} R={self._dual_ports.get('right')}"
        )
        return result

    def get_dual_ports(self) -> Dict[str, str]:
        return dict(self._dual_ports)

    def swap_dual_ports_and_restart(self) -> Dict[str, str]:
        """
        交换左右物理串口并重启 dual_serial 读取。
        交换后清除 lr_swap（映射由端口承担）。
        """
        left = self._dual_ports.get('left', '/dev/ttyACM0')
        right = self._dual_ports.get('right', '/dev/ttyACM1')
        self._dual_ports = {'left': right, 'right': left}
        print(
            f'[IMU] 交换串口: L={self._dual_ports["left"]} R={self._dual_ports["right"]}'
        )
        if self.mode == 'dual_serial' and self._running:
            if self._wit_reader:
                self._wit_reader.stop()
                self._wit_reader = None
            self._connected_imus.clear()
            self._last_data_time.clear()
            self._start_dual_serial()
        self.apply_lr_swap(False)
        self._notify_status('system', 'ports_swapped', {
            'ports': dict(self._dual_ports),
        })
        return dict(self._dual_ports)

    def apply_lr_swap(self, swap: bool):
        """设置运行时左右手交换标志"""
        self._lr_swap = bool(swap)
        print(f"[IMU] 左右手映射 swap = {self._lr_swap}")
        self._notify_status('system', 'lr_swap_changed', {
            'lr_swap': self._lr_swap,
        })

    def get_lr_swap(self) -> bool:
        return self._lr_swap

    # ==================== 数据读取接口 ====================

    def get_latest_data(
        self, timeout: float = 0.01
    ) -> Optional[dict]:
        """从队列中取出一帧IMU数据"""
        try:
            return self._data_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_all_pending_data(self) -> List[dict]:
        """取出队列中所有待处理的IMU数据"""
        items = []
        while not self._data_queue.empty():
            try:
                items.append(self._data_queue.get_nowait())
            except queue.Empty:
                break
        return items

    # ==================== 状态查询 ====================

    def get_connected_imus(self) -> Dict[str, dict]:
        """获取已连接的IMU信息"""
        return self._connected_imus.copy()

    def is_imu_connected(self, imu_id: str) -> bool:
        """检查指定IMU是否在线（2秒超时）"""
        if imu_id not in self._last_data_time:
            return False
        return (time.time() - self._last_data_time[imu_id]) < 2.0

    def get_diagnostics(self) -> dict:
        """获取诊断信息"""
        return {
            'mode': self.mode,
            'port': self.port,
            'baudrate': self.baudrate,
            'data_format': self.data_format,
            'dual_ports': self._dual_ports if self.mode == 'dual_serial' else None,
            'stream_path': self._stream_path,
            'txt_files': self._txt_files if self.mode == 'txt' else None,
            'txt_line_errors': self._txt_line_errors,
            'running': self._running,
            'serial_connected': (
                self._serial_conn is not None and
                self._serial_conn.is_open
                if self._serial_conn else False
            ),
            'frame_count': self._frame_count,
            'error_count': self._error_count,
            'crc_error_count': self._crc_error_count,
            'queue_size': self._data_queue.qsize(),
            'connected_imus': list(self._connected_imus.keys()),
            'imu_online': {
                imu_id: self.is_imu_connected(imu_id)
                for imu_id in self._connected_imus
            },
            'calibrating': self._calibrating,
            'serial_errors': (
                dict(self._wit_reader.last_error)
                if getattr(self, '_wit_reader', None) else {}
            ),
        }
