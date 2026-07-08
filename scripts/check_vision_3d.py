#!/usr/bin/env python3
"""快速检查双目 3D / 步态指标是否可用（需在 main.py --real 运行时另开终端执行）。"""
from __future__ import annotations

import json
import socket
import sys
import time

SOCK = "/tmp/rehab_engine.sock"


def main():
    if not __import__("os").path.exists(SOCK):
        print(f"引擎未运行或未创建 {SOCK}")
        print("请先启动: python main.py --real --qt-service")
        return 1

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3.0)
    s.connect(SOCK)
    s.sendall(b'{"type":"command","payload":{"command":"request_status"}}\n')

    buf = b""
    deadline = time.time() + 5.0
    while time.time() < deadline:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype == "vision_preview":
                overlay = (msg.get("payload") or {}).get("overlay", "")
                print("[vision_preview]", overlay)
                if "3D:" in overlay and "2D-only" not in overlay:
                    print("结论: 3D 三角测量已生效")
                    return 0
            elif mtype == "joint_angles":
                p = msg.get("payload") or {}
                ang = p.get("angles") or {}
                if ang:
                    print(
                        "[joint_angles] step_distance="
                        f"{ang.get('step_distance', 0)} "
                        f"step_dx_L={ang.get('step_dx_left', 0)} "
                        f"step_dx_R={ang.get('step_dx_right', 0)}"
                    )
    print("结论: 当前未观察到 3D 数据，请检查 pose_mode: both 与 stereo_calib.json")
    return 2


if __name__ == "__main__":
    sys.exit(main())
