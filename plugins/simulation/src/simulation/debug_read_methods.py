#!/usr/bin/env python3
"""Test machine-qualified sysbus commands and different read approaches."""

import re
import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(3.0)
sock.connect(("127.0.0.1", 3333))
time.sleep(0.3)
data = sock.recv(1024)
for cmd in data.split(b"\xff"):
    if len(cmd) >= 2 and cmd[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + cmd[1:2])


def cmd(c):
    sock.sendall((c + "\n").encode())
    buf = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"(F103" in chunk or b"(F407" in chunk or b"(monitor" in chunk:
                break
        except TimeoutError:
            break
    return re.sub(rb"\x1b\[[0-9;]*m", b"", buf).decode(errors="replace")


# First, write known values to BSS while machines are fresh
# Then read back using various methods

print("=== Method 1: mach set + sysbus ReadDoubleWord ===")
cmd('mach set "F407"')
cmd("sysbus WriteDoubleWord 0x2000001C 0x42")  # frame_count = 66
r = cmd("sysbus ReadDoubleWord 0x2000001C")
print(f"  F407 frame_count: {r.strip()}")

cmd("sysbus WriteDoubleWord 0x20000010 0x1CE8")  # battery = 7400
r = cmd("sysbus ReadDoubleWord 0x20000010")
print(f"  F407 battery_mv: {r.strip()}")

print("\n=== Method 2: Machine-qualified (F407.sysbus ...) ===")
r = cmd("F407.sysbus ReadDoubleWord 0x2000001C")
print(f"  F407.sysbus frame_count: {r.strip()}")

cmd("F407.sysbus WriteDoubleWord 0x2000001C 0x99")
r = cmd("F407.sysbus ReadDoubleWord 0x2000001C")
print(f"  After write 0x99: {r.strip()}")

print("\n=== Method 3: Read free RAM region ===")
cmd('mach set "F407"')
cmd("sysbus WriteDoubleWord 0x20000400 0xDEADBEEF")
r = cmd("sysbus ReadDoubleWord 0x20000400")
print(f"  0x20000400: {r.strip()}")

print("\n=== Method 4: F103 BSS ===")
cmd('mach set "F103"')
cmd("sysbus WriteDoubleWord 0x2000000A 0x1CE8")  # battery_mv
r = cmd("sysbus ReadDoubleWord 0x2000000A")
print(f"  F103 battery_mv: {r.strip()}")

cmd("sysbus WriteDoubleWord 0x2000001C 0x01")  # estop_lock = 1
r = cmd("sysbus ReadDoubleWord 0x2000001C")
print(f"  F103 estop_lock: {r.strip()}")

print("\n=== All done ===")
sock.close()
