#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linux 训练联调后端：给 Qt 训练页提供 127.0.0.1:9002 TCP 服务。
作用：
1. 接收 Qt 的 start_training 指令；
2. 持续发送 action_status，让训练页进度条和开始训练流程可在 Linux 下完整运行；
3. 不依赖 interface.protocol，直接运行即可。
"""
import argparse
import json
import socket
import threading
import time
from datetime import datetime

def now_ms():
    return int(time.time() * 1000)

def line_message(msg_type, payload):
    return (json.dumps({
        "type": msg_type,
        "timestamp": str(now_ms()),
        "payload": payload,
    }, ensure_ascii=False) + "\n").encode("utf-8")

class ClientSession:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.training = False
        self.level = 2
        self._lock = threading.Lock()

    def send(self, msg_type, payload):
        try:
            self.conn.sendall(line_message(msg_type, payload))
        except OSError:
            raise

    def start_training(self, level=2):
        with self._lock:
            self.training = True
            self.level = int(level or 2)
        threading.Thread(target=self._training_loop, daemon=True).start()

    def _training_loop(self):
        actions = ["block_1", "block_2", "block_3", "block_4"]
        target_reps = 32
        for rep in range(target_reps + 1):
            with self._lock:
                if not self.training:
                    break
                level = self.level
            block_index = min(3, rep // 8)
            payload = {
                "action_id": actions[block_index],
                "state": "running" if rep < target_reps else "finished",
                "level": level,
                "rep_count": rep,
                "target_reps": target_reps,
                "current_angle": 35 + rep % 50,
            }
            try:
                self.send("action_status", payload)
            except OSError:
                break
            time.sleep(0.5)
        with self._lock:
            self.training = False

    def run(self):
        buf = b""
        self.send("system_status", {"status": "connected", "time": datetime.now().isoformat()})
        while True:
            try:
                data = self.conn.recv(4096)
            except OSError:
                break
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                payload = msg.get("payload", {})
                cmd = payload.get("command", "")
                if cmd == "start_training":
                    self.start_training(payload.get("level", 2))
                elif cmd == "stop_training":
                    with self._lock:
                        self.training = False
        try:
            self.conn.close()
        except OSError:
            pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9002)
    args = parser.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(8)
    print(f"Linux 训练联调后端已启动: {args.host}:{args.port}")
    print("保持此窗口运行，再启动 Qt 程序并点击“开始训练”。")
    while True:
        conn, addr = srv.accept()
        print("Qt 已连接:", addr)
        session = ClientSession(conn, addr)
        threading.Thread(target=session.run, daemon=True).start()

if __name__ == "__main__":
    main()
