#!/usr/bin/env python3
"""Smoke test for rehab-coach-rknn Qt Unix socket on Linux/RK3588."""
import argparse
import json
import select
import socket
import sys
import time

DEFAULT_SOCKET = "/tmp/rehab_engine.sock"


def make_command(command: str, **extra) -> bytes:
    payload = {"command": command, **extra}
    msg = {
        "type": "command",
        "timestamp": time.time(),
        "payload": payload,
    }
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def read_lines(sock: socket.socket, deadline: float, skip_types: set) -> None:
    buf = b""
    sock.setblocking(False)
    while time.time() < deadline:
        timeout = max(0.0, min(0.5, deadline - time.time()))
        readable, _, _ = select.select([sock], [], [], timeout)
        if not readable:
            continue
        try:
            chunk = sock.recv(8192)
        except BlockingIOError:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            text = line.decode("utf-8", errors="replace")
            if skip_types:
                try:
                    msg = json.loads(text)
                    if msg.get("type") in skip_types:
                        print(f"[skip] {msg.get('type')}")
                        continue
                except json.JSONDecodeError:
                    pass
            print(text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Qt engine Unix socket smoke test")
    ap.add_argument("--socket", default=DEFAULT_SOCKET)
    ap.add_argument("--send", default="request_status")
    ap.add_argument("--level", default="L2")
    ap.add_argument("--duration", type=float, default=8.0)
    ap.add_argument("--skip-preview", action="store_true", default=True,
                    help="Skip vision_preview / skeleton_3d (default: on)")
    args = ap.parse_args()

    skip = {"vision_preview", "skeleton_3d", "joint_angles"} if args.skip_preview else set()

    extra = {}
    if args.send == "start_training":
        extra["level"] = args.level

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(args.socket)
    except OSError as exc:
        print(f"[FAIL] 无法连接 {args.socket}: {exc}", file=sys.stderr)
        print("请先启动: ./start_rk3588.sh 或 ../start_rk3588_system.sh backend", file=sys.stderr)
        return 1

    print(f"[OK] connected to {args.socket}")
    sock.sendall(make_command(args.send, **extra))
    read_lines(sock, time.time() + args.duration, skip)
    sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
