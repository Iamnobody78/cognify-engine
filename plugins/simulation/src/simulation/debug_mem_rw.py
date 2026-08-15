#!/usr/bin/env python3
"""Isolate write-read: does Renode sysbus actually modify memory?"""

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
    """Send command, read ALL chunks until prompt, return raw bytes."""
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
    return buf


def strip_ansi(s):
    return re.sub(rb"\x1b\[[0-9;]*m", b"", s)


# Pick unused RAM area (top of SRAM)
TEST_ADDR = 0x20005000
TEST_VAL = 0xA5A5BEEF

cmd_raw('mach set "F407"')

print("=== Test 1: Write known value, read back ===")
r = cmd_raw(f"sysbus WriteDoubleWord {hex(TEST_ADDR)} {hex(TEST_VAL)}")
print(f"Write response: {strip_ansi(r)}")
time.sleep(0.1)
r = cmd_raw(f"sysbus ReadDoubleWord {hex(TEST_ADDR)}")
print(f"Read response raw: {r}")
print(f"Read response clean: {strip_ansi(r)}")

# Parse: find any hex value in response
clean = strip_ansi(r).decode(errors="replace")
print(f"Parsed lines: {clean.split(chr(10))}")

print("\n=== Test 2: Read unmodified BSS ===")
r = cmd_raw("sysbus ReadDoubleWord 0x2000001C")
clean = strip_ansi(r).decode(errors="replace")
print(f"frame_count @ 0x2000001C: [{clean}]")

r = cmd_raw("sysbus ReadByte 0x2000001C")
clean = strip_ansi(r).decode(errors="replace")
print(f"frame_count byte @ 0x2000001C: [{clean}]")

# Also check on F103
cmd_raw('mach set "F103"')
print("\n=== Test 3: F103 BSS ===")
for name, addr in [("battery_mv", 0x2000000A), ("estop_lock", 0x2000001C)]:
    r = cmd_raw(f"sysbus ReadDoubleWord {hex(addr)}")
    clean = strip_ansi(r).decode(errors="replace")
    print(f"{name} @ {hex(addr)}: [{clean.strip()}]")

sock.close()
