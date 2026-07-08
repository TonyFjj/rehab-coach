#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import select
import socket
import sys
import time

DEFAULT_UNIX = "/tmp/rehab_engine.sock"

def make_message(command, level="L2"):
    payload = {"command": command}
    if command == "start_training":
        payload["level"] = level
    return (json.dumps({
        "type": "command",
        "timestamp": time.time(),
        "payload": payload,
    }, ensure_ascii=False) + "\n").encode("utf-8")

def read_responses(sock, deadline):
    buf = b""
    sock.setblocking(False)
    while time.time() < deadline:
        timeout = max(0.0, min(0.5, deadline - time.time()))
        readable, _, _ = select.select([sock], [], [], timeout)
        if not readable:
            continue
        try:
            chunk = sock.recv(4096)
        except BlockingIOError:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if line:
                print(line.decode("utf-8", "ignore"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=os.environ.get("REHAB_ENGINE_SOCKET", DEFAULT_UNIX),
                    help="Linux Unix socket path")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9002)
    ap.add_argument("--send", default="request_status")
    ap.add_argument("--level", default="L2")
    ap.add_argument("--duration", type=float, default=10)
    args = ap.parse_args()

    deadline = time.time() + args.duration
    use_unix = os.name != "nt" and args.socket and os.path.exists(os.path.dirname(args.socket) or "/tmp")

    if use_unix:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(args.socket)
            print(f"[OK] Unix socket: {args.socket}")
        except OSError:
            use_unix = False

    if not use_unix:
        sock = socket.create_connection((args.host, args.port), timeout=3)
        print(f"[OK] TCP: {args.host}:{args.port}")

    sock.sendall(make_message(args.send, args.level))
    try:
        read_responses(sock, deadline)
    finally:
        sock.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
