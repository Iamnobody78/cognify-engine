#!/usr/bin/env python3
"""Test: stop CPU then read BSS."""

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


def cmd_raw(c):
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
    return re.sub(rb"\x1b\[[0-9;]*m", b"", buf)


def parse_value(raw):
    """Extract hex value from response lines."""
    lines = raw.decode(errors="replace").split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("0x") or line.startswith("\r0x"):
            return line.lstrip("\r")
    return "(no value)"


print("=== F407 BSS reads WHILE RUNNING ===")
cmd_raw('mach set "F407"')
for addr, name in [
    (0x2000001C, "frame_count"),
    (0x20000014, "enc_a_delta"),
    (0x20000010, "battery_mv"),
]:
    r = cmd_raw(f"sysbus ReadDoubleWord {hex(addr)}")
    print(f"  RUNNING: {name} @ {hex(addr)}: {parse_value(r)}")

print("\n=== STOP F407, then read ===")
cmd_raw("cpu Stop")
time.sleep(0.2)
for addr, name in [
    (0x2000001C, "frame_count"),
    (0x20000014, "enc_a_delta"),
    (0x20000010, "battery_mv"),
]:
    r = cmd_raw(f"sysbus ReadDoubleWord {hex(addr)}")
    print(f"  STOPPED: {name} @ {hex(addr)}: {parse_value(r)}")

print("\n=== F103 BSS reads ===")
cmd_raw('mach set "F103"')
for addr, name in [
    (0x2000000A, "battery_mv"),
    (0x2000001C, "estop_lock"),
    (0x2000000C, "enc_a_count"),
]:
    r = cmd_raw(f"sysbus ReadDoubleWord {hex(addr)}")
    print(f"  RUNNING: {name} @ {hex(addr)}: {parse_value(r)}")

print("\n=== STOP F103, then read ===")
cmd_raw("cpu Stop")
time.sleep(0.2)
for addr, name in [
    (0x2000000A, "battery_mv"),
    (0x2000001C, "estop_lock"),
    (0x2000000C, "enc_a_count"),
]:
    r = cmd_raw(f"sysbus ReadDoubleWord {hex(addr)}")
    print(f"  STOPPED: {name} @ {hex(addr)}: {parse_value(r)}")

# Restart for further tests
print("\n=== Restarting both ===")
cmd_raw('mach set "F407"')
cmd_raw("cpu Start")
cmd_raw('mach set "F103"')
cmd_raw("cpu Start")
print("Done.")

sock.close()
