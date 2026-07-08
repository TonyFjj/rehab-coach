"""
Qt界面进程间通信接口
核心引擎与Qt界面运行在同一台RK3588上，使用Unix Domain Socket通信

通信方式：
  - Unix Domain Socket（Linux进程间通信，零网络开销）
  - 备选：共享内存（未来高帧率骨骼渲染时使用）

数据流：
  核心引擎 ←→ /tmp/rehab_engine.sock ←→ Qt界面进程
"""

import json
import os
import time
import socket
import threading
import queue
from typing import Dict, Optional, Callable, Any

from .protocol import (
    MessageType,
    create_message,
    parse_message,
    create_skeleton_3d_message,
    create_action_status_message,
    create_scoring_message,
    create_correction_message,
    create_encouragement_message,
    create_training_progress_message,
    create_session_summary_message,
    create_level_change_message,
    create_safety_alert_message,
    create_system_status_message,
    create_training_state_message,
    create_vision_preview_message,
    create_training_plan_message,
    create_assessment_plan_message,
    create_assessment_phase_message,
)


class QtInterface:
    """
    与Qt界面的进程间通信接口

    使用 Unix Domain Socket，核心引擎作为服务端，Qt进程作为客户端。
    同一台机器上的进程间通信，延迟极低（< 0.1ms），
    比TCP Socket少了网络协议栈开销。

    Windows开发环境下自动降级为 TCP localhost。
    """

    # Unix Socket 文件路径
    DEFAULT_SOCKET_PATH = '/tmp/rehab_engine.sock'

    def __init__(
        self,
        socket_path: str = None,
        tcp_fallback_port: int = 9002,
        simulate: bool = False
    ):
        """
        Args:
            socket_path: Unix Domain Socket路径
                         Linux: '/tmp/rehab_engine.sock'
                         Windows: 自动降级为TCP
            tcp_fallback_port: Windows降级TCP端口
            simulate: 模拟模式（不建立实际连接，只打印日志）
        """
        self.simulate = simulate
        self.tcp_fallback_port = tcp_fallback_port

        # 判断平台
        import platform
        self._is_linux = platform.system() == 'Linux'

        if self._is_linux:
            self.socket_path = socket_path or self.DEFAULT_SOCKET_PATH
            self._use_unix_socket = True
        else:
            self.socket_path = None
            self._use_unix_socket = False
            print("[Qt] Windows环境，使用TCP localhost降级")

        # 发送队列
        self._send_queue: queue.Queue = queue.Queue(maxsize=200)

        # 线程
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None

        # Socket
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._client_info = None

        # 控制指令回调
        self._command_callbacks: Dict[str, Callable] = {}

        # 状态
        self._connected = False
        self._send_count = 0
        self._recv_count = 0

        # 发送频率控制
        self._send_interval = {
            MessageType.SKELETON_3D.value: 1.0 / 30.0,
            MessageType.JOINT_ANGLES.value: 1.0 / 15.0,
            MessageType.ACTION_STATUS.value: 1.0 / 10.0,
            MessageType.VISION_PREVIEW.value: 1.0 / 12.0,
            MessageType.SCORING.value: 1.0,
            MessageType.CORRECTION.value: 0,
            MessageType.SAFETY_ALERT.value: 0,
        }
        self._last_type_send_time: Dict[str, float] = {}

    # ==================== 控制指令注册 ====================

    def register_command(self, command: str, callback: Callable):
        """
        注册来自Qt界面的控制指令回调

        可注册的指令：
            'start_training'    - 开始训练
            'pause_training'    - 暂停训练
            'resume_training'   - 恢复训练
            'stop_training'     - 停止训练
            'next_action'       - 下一个动作
            'prev_action'       - 上一个动作
            'start_assessment'  - 开始初评
            'confirm_upgrade'   - 确认升级
            'request_status'    - 请求状态
            'set_volume'        - 设置音量
            'set_speed'         - 设置语速
        """
        self._command_callbacks[command] = callback

    # ==================== 启动/停止 ====================

    def start(self):
        """启动通信接口"""
        if self._running:
            return

        self._running = True

        if self.simulate:
            print("[Qt] 模拟模式启动")
            return

        # 启动服务器线程
        self._server_thread = threading.Thread(
            target=self._server_loop,
            daemon=True,
            name="qt-server"
        )
        self._server_thread.start()

        # 启动发送线程
        self._send_thread = threading.Thread(
            target=self._send_loop,
            daemon=True,
            name="qt-sender"
        )
        self._send_thread.start()

    def stop(self):
        """停止通信接口"""
        self._running = False

        if self._client_socket:
            try:
                self._client_socket.close()
            except Exception:
                pass
            self._client_socket = None

        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None

        # 清理Unix Socket文件
        if self._use_unix_socket and self.socket_path and \
                os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except Exception:
                pass

        self._connected = False

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=3.0)
        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=3.0)

        print("[Qt] 通信接口已停止")

    # ==================== 数据推送接口 ====================

    def send_skeleton_3d(
        self,
        joints_3d: Dict[str, list],
        confidences: Dict[str, float]
    ):
        """推送3D骨骼坐标（30fps）"""
        msg = create_skeleton_3d_message(joints_3d, confidences)
        self._enqueue(MessageType.SKELETON_3D.value, msg)

    def send_joint_angles(self, angles: Dict[str, float]):
        """推送关节角度（15fps）"""
        msg = create_message(
            MessageType.JOINT_ANGLES,
            {"angles": angles}
        )
        self._enqueue(MessageType.JOINT_ANGLES.value, msg)

    def send_action_status(
        self,
        action_id: str,
        state: str,
        rep_count: int,
        target_reps: int,
        current_angle: float,
        peak_angle: float,
        progress_percent: float,
        action_name: str = None,
        metric_name: str = None,
        metric_unit: str = None,
    ):
        """推送动作状态（10fps）"""
        msg = create_action_status_message(
            action_id, state, rep_count, target_reps,
            current_angle, peak_angle, progress_percent,
            action_name=action_name,
            metric_name=metric_name,
            metric_unit=metric_unit,
        )
        self._enqueue(MessageType.ACTION_STATUS.value, msg)

    def send_scoring(
        self,
        total_score: float,
        dimension_scores: dict,
        level: str,
        level_name: str = None,
        action_names: list = None,
        action_scores: list = None,
        advice: str = None,
        source: str = None,
        imu_total_score: float = None,
        imu_dimension_scores: dict = None,
        vision_assessment: dict = None,
        imu_only_reason: str = None,
        lr_scores: dict = None,
        lr_note: str = None,
    ):
        """推送评分"""
        msg = create_scoring_message(
            total_score,
            dimension_scores,
            level,
            level_name=level_name,
            action_names=action_names,
            action_scores=action_scores,
            advice=advice,
            source=source,
            imu_total_score=imu_total_score,
            imu_dimension_scores=imu_dimension_scores,
            vision_assessment=vision_assessment,
            imu_only_reason=imu_only_reason,
            lr_scores=lr_scores,
            lr_note=lr_note,
        )
        self._enqueue(MessageType.SCORING.value, msg, priority=True)

    def send_correction(self, corrections: list):
        """推送纠正指令（立即发送）"""
        msg = create_correction_message(corrections)
        self._enqueue(MessageType.CORRECTION.value, msg, priority=True)

    def send_encouragement(self, text: str):
        """推送鼓励语"""
        msg = create_encouragement_message(text)
        self._enqueue(MessageType.ENCOURAGEMENT.value, msg)

    def send_training_progress(
        self,
        level: str,
        completed_actions: int,
        total_actions: int,
        completion_rate: float,
        current_action_id: str = None,
        current_action_name: str = None,
        action_scores: list = None,
    ):
        """推送训练进度"""
        msg = create_training_progress_message(
            level,
            completed_actions,
            total_actions,
            completion_rate,
            current_action_id=current_action_id,
            current_action_name=current_action_name,
            action_scores=action_scores,
        )
        self._enqueue(MessageType.TRAINING_PROGRESS.value, msg)

    def send_training_plan(
        self,
        level: str,
        level_name: str,
        description: str,
        actions: list,
        body_region: str = None,
        block_label: str = None,
        camera_preset: str = None,
        setup_hint: str = None,
        suggest_integration: bool = False,
        has_integration: bool = False,
    ):
        """推送等级训练方案（动作名称/描述来自 yaml）。"""
        msg = create_training_plan_message(
            level,
            level_name,
            description,
            actions,
            body_region=body_region,
            block_label=block_label,
            camera_preset=camera_preset,
            setup_hint=setup_hint,
            suggest_integration=suggest_integration,
            has_integration=has_integration,
        )
        self._enqueue(MessageType.TRAINING_PLAN.value, msg, priority=True)

    def send_assessment_plan(self, plan: dict):
        """推送初评指导方案。"""
        msg = create_assessment_plan_message(plan)
        self._enqueue(MessageType.ASSESSMENT_PLAN.value, msg, priority=True)

    def send_assessment_phase(
        self,
        phase: str,
        action_index: int = 0,
        total_actions: int = 0,
        action_name: str = None,
        instruction: str = None,
        duration: int = 0,
        sub_phase: str = None,
        vision_completion: float = None,
        vision_accuracy: float = None,
        vision_current_angle: float = None,
        vision_max_angle: float = None,
        vision_quality: float = None,
        vision_status: str = None,
        vision_warning: str = None,
    ):
        """推送初评当前阶段（供 Qt 显示指令与倒计时）。"""
        msg = create_assessment_phase_message(
            phase=phase,
            action_index=action_index,
            total_actions=total_actions,
            action_name=action_name,
            instruction=instruction,
            duration=duration,
            sub_phase=sub_phase,
            vision_completion=vision_completion,
            vision_accuracy=vision_accuracy,
            vision_current_angle=vision_current_angle,
            vision_max_angle=vision_max_angle,
            vision_quality=vision_quality,
            vision_status=vision_status,
            vision_warning=vision_warning,
        )
        self._enqueue(MessageType.ASSESSMENT_PHASE.value, msg, priority=True)

    def send_session_summary(self, summary_text: str):
        """推送训练总结"""
        msg = create_session_summary_message(summary_text)
        self._enqueue(MessageType.SESSION_SUMMARY.value, msg)

    def send_level_change(
        self, old_level: str, new_level: str, reason: str
    ):
        """推送等级变化"""
        msg = create_level_change_message(old_level, new_level, reason)
        self._enqueue(MessageType.LEVEL_CHANGE.value, msg, priority=True)

    def send_safety_alert(
        self, alert_text: str, alert_type: str = 'general'
    ):
        """推送安全警报（最高优先级）"""
        msg = create_safety_alert_message(alert_text, alert_type)
        self._enqueue(MessageType.SAFETY_ALERT.value, msg, priority=True)

    def send_system_status(
        self,
        status_text: str,
        cpu_usage: float = None,
        memory_usage: float = None,
        tts_volume: float = None,
        tts_rate: int = None,
        imu: dict = None,
    ):
        """推送系统状态"""
        msg = create_system_status_message(
            status_text,
            cpu_usage,
            memory_usage,
            tts_volume=tts_volume,
            tts_rate=tts_rate,
            imu=imu,
        )
        self._enqueue(MessageType.SYSTEM_STATUS.value, msg)

    def send_training_state(
        self,
        phase: str,
        level: str = None,
        action_id: str = None,
        action_ids: list = None,
        message: str = None,
        body_region: str = None,
        block_label: str = None,
        suggest_next_region: str = None,
    ):
        """推送训练会话阶段（idle / running / paused / stopped / busy / block_complete）"""
        msg = create_training_state_message(
            phase=phase,
            level=level,
            action_id=action_id,
            action_ids=action_ids,
            message=message,
            body_region=body_region,
            block_label=block_label,
            suggest_next_region=suggest_next_region,
        )
        self._enqueue(MessageType.TRAINING_STATE.value, msg, priority=True)

    def send_vision_preview(
        self,
        image_b64: str,
        width: int,
        height: int,
        overlay: str = "",
        vision_quality: float = None,
        vision_status: str = None,
        vision_warning: str = None,
        depth_mode: str = None,
        skeleton_3d_joints: int = None,
    ):
        """推送双目调试画面（JPEG base64，约 12fps）。"""
        if not self._connected:
            return
        msg = create_vision_preview_message(
            image_b64, width, height, overlay,
            vision_quality=vision_quality,
            vision_status=vision_status,
            vision_warning=vision_warning,
            depth_mode=depth_mode,
            skeleton_3d_joints=skeleton_3d_joints,
        )
        self._enqueue(MessageType.VISION_PREVIEW.value, msg)

    # ==================== 内部网络实现 ====================

    def _server_loop(self):
        """服务器主循环"""
        try:
            if self._use_unix_socket:
                self._server_loop_unix()
            else:
                self._server_loop_tcp()
        except Exception as e:
            print(f"[Qt] 服务器错误: {e}")

    def _server_loop_unix(self):
        """Unix Domain Socket 服务器"""
        # 清理旧的socket文件
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        self._server_socket = socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM
        )
        self._server_socket.settimeout(1.0)
        self._server_socket.bind(self.socket_path)
        self._server_socket.listen(1)

        # 设置权限，让Qt进程可以连接
        os.chmod(self.socket_path, 0o777)

        print(f"[Qt] Unix Socket 服务器启动: {self.socket_path}")
        self._accept_and_handle()

    def _server_loop_tcp(self):
        """TCP localhost 服务器（Windows降级用）"""
        self._server_socket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        )
        self._server_socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )
        self._server_socket.settimeout(1.0)
        self._server_socket.bind(('127.0.0.1', self.tcp_fallback_port))
        self._server_socket.listen(1)

        print(f"[Qt] TCP服务器启动: 127.0.0.1:{self.tcp_fallback_port}")
        self._accept_and_handle()

    def _accept_and_handle(self):
        """等待Qt客户端连接并处理收发"""
        while self._running:
            # 等待连接
            if not self._connected:
                try:
                    client, info = self._server_socket.accept()
                    self._client_socket = client
                    self._client_info = info
                    self._connected = True
                    print(f"[Qt] Qt界面已连接: {info}")

                    # 发送就绪消息
                    welcome = create_system_status_message("核心引擎已就绪")
                    self._do_send(welcome)

                except socket.timeout:
                    continue
                except OSError:
                    break

            # 接收控制指令
            if self._connected and self._client_socket:
                try:
                    self._client_socket.settimeout(0.1)
                    data = self._client_socket.recv(4096)

                    if not data:
                        self._handle_disconnect()
                        continue

                    text = data.decode('utf-8', errors='ignore')
                    for line in text.strip().split('\n'):
                        line = line.strip()
                        if line:
                            self._process_command(line)

                except socket.timeout:
                    continue
                except ConnectionResetError:
                    self._handle_disconnect()
                except Exception:
                    self._handle_disconnect()

    def _send_loop(self):
        """发送线程"""
        while self._running:
            try:
                msg_type, msg_str = self._send_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self._connected or self.simulate:
                self._do_send(msg_str)
            self._send_queue.task_done()

    def _enqueue(
        self, msg_type: str, msg_str: str, priority: bool = False
    ):
        """放入发送队列（带频率控制）"""
        if self.simulate:
            # 模拟模式只打印关键消息
            if msg_type in (
                MessageType.CORRECTION.value,
                MessageType.SAFETY_ALERT.value,
                MessageType.SCORING.value,
                MessageType.SESSION_SUMMARY.value,
                MessageType.LEVEL_CHANGE.value,
            ):
                try:
                    parsed = json.loads(msg_str)
                    payload_str = json.dumps(
                        parsed['payload'], ensure_ascii=False
                    )[:120]
                    print(f"[Qt→] {msg_type}: {payload_str}")
                except Exception:
                    print(f"[Qt→] {msg_type}")
            return

        # 频率控制
        if not priority:
            min_interval = self._send_interval.get(msg_type, 0.1)
            now = time.time()
            last = self._last_type_send_time.get(msg_type, 0)
            if now - last < min_interval:
                return

        self._last_type_send_time[msg_type] = time.time()

        try:
            self._send_queue.put_nowait((msg_type, msg_str))
        except queue.Full:
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                pass
            self._send_queue.put_nowait((msg_type, msg_str))

    def _do_send(self, msg_str: str):
        """实际发送"""
        if self.simulate:
            return

        if not self._connected or not self._client_socket:
            return

        try:
            data = (msg_str + '\n').encode('utf-8')
            self._client_socket.sendall(data)
            self._send_count += 1
        except BrokenPipeError:
            self._handle_disconnect()
        except ConnectionResetError:
            self._handle_disconnect()
        except Exception as e:
            print(f"[Qt] 发送失败: {e}")

    def _process_command(self, raw: str):
        """处理Qt界面发来的控制指令"""
        msg = parse_message(raw)
        if msg is None:
            return

        self._recv_count += 1
        payload = msg.get('payload', {})
        command = payload.get('command', msg.get('type', ''))

        print(f"[Qt←] 收到指令: {command}")

        if command in self._command_callbacks:
            try:
                self._command_callbacks[command](payload)
            except Exception as e:
                print(f"[Qt] 指令回调失败 ({command}): {e}")
        else:
            print(f"[Qt] 未注册的指令: {command}")

    def _handle_disconnect(self):
        """处理Qt断开"""
        print("[Qt] Qt界面已断开")
        self._connected = False
        if self._client_socket:
            try:
                self._client_socket.close()
            except Exception:
                pass
            self._client_socket = None

    # ==================== 状态查询 ====================

    def is_connected(self) -> bool:
        """Qt界面是否已连接"""
        return self._connected

    def get_diagnostics(self) -> dict:
        """获取诊断信息"""
        return {
            'transport': 'unix_socket' if self._use_unix_socket
                         else 'tcp_localhost',
            'socket_path': self.socket_path,
            'connected': self._connected,
            'client_info': str(self._client_info),
            'send_count': self._send_count,
            'recv_count': self._recv_count,
            'send_queue_size': self._send_queue.qsize(),
            'simulate': self.simulate,
            'registered_commands': list(self._command_callbacks.keys()),
        }
