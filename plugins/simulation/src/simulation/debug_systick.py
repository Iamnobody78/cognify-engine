#!/usr/bin/env python3
"""Check if SysTick advances in Renode."""

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


def parse_hex(resp):
    for line in resp.split("\n"):
        line = line.strip()
        if line.startswith("0x"):
            try:
                return int(line, 16)
            except Exception:

                pass
    return None


# F407: sys_tick_ms is at 0x20000004 (from ELF: 20000004 d sys_tick_ms)
SYS_TICK_ADDR = 0x20000004

cmd('mach set "F407"')

print("=== SysTick Check ===")
# Read PC first
r = cmd("cpu PC")
print(f"  Current PC: {parse_hex(r)}")

# Read sys_tick_ms
r = cmd(f"sysbus ReadDoubleWord {hex(SYS_TICK_ADDR)}")
t1 = parse_hex(r)
print(f"  sys_tick_ms @ t=0: {t1} ({r.strip()})")

# Also check SysTick registers
print("\n=== SysTick Peripheral ===")
for name, offset in [("CTRL", 0xE000E010), ("LOAD", 0xE000E014), ("VAL", 0xE000E018)]:
    r = cmd(f"sysbus ReadDoubleWord {hex(offset)}")
    print(f"  SysTick {name}: {parse_hex(r)}")

# Read NVIC to see if SysTick IRQ is pending
print("\n=== NVIC ISER ===")
for i in range(8):
    r = cmd(f"sysbus ReadDoubleWord {hex(0xE000E100 + i * 4)}")
    print(f"  ISER[{i}]: {parse_hex(r)}")

sock.close()
