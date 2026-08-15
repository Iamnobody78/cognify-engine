#!/usr/bin/env python3
"""Debug script: test raw Renode monitor communication."""

import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(3.0)
sock.connect(("127.0.0.1", 3333))

# Drain initial buffer
time.sleep(0.3)
try:
    initial = sock.recv(4096)
    print(f"=== Initial buffer ({len(initial)} bytes) ===")
    print(repr(initial))
except TimeoutError:
    print("No initial data")


def send_cmd(cmd):
    sock.sendall((cmd + "\n").encode())
    time.sleep(0.1)
    try:
        resp = sock.recv(4096)
        return resp
    except TimeoutError:
        return b""


# Test 1: mach set
print("\n=== Test: mach set F407 ===")
r = send_cmd('mach set "F407"')
print(repr(r))

# Test 2: cpu PC
print("\n=== Test: cpu PC ===")
r = send_cmd("cpu PC")
print(repr(r))

# Test 3: sysbus ReadDoubleWord
print("\n=== Test: sysbus ReadDoubleWord 0x2000001C (frame_count) ===")
r = send_cmd("sysbus ReadDoubleWord 0x2000001C")
print(repr(r))

# Test 4: mach set F103
print("\n=== Test: mach set F103 ===")
r = send_cmd('mach set "F103"')
print(repr(r))

# Test 5: cpu PC on F103
print("\n=== Test: cpu PC (F103) ===")
r = send_cmd("cpu PC")
print(repr(r))

# Test 6: sysbus ReadByte
print("\n=== Test: sysbus ReadByte 0x2000001C (estop_lock) ===")
r = send_cmd("sysbus ReadByte 0x2000001C")
print(repr(r))

sock.close()
