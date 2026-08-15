#!/usr/bin/env python3
"""Test Renode cpu command syntax for setting PC."""

import re
import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10.0)
sock.connect(("127.0.0.1", 3333))
time.sleep(0.5)
data = sock.recv(4096)
for chunk in data.split(b"\xff"):
    if len(chunk) >= 2 and chunk[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + chunk[1:2])

FW = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"


def cmd(c):
    sock.sendall((c + "\n").encode())
    time.sleep(0.1)
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"(monitor)" in chunk or b"(F407" in chunk:
                break
    except TimeoutError:
        pass
    return re.sub(rb"\x1b\[[0-9;]*m", b"", buf).decode(errors="replace")


# Load minimal setup
cmd('mach add "F407"')
cmd('mach set "F407"')
cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
cmd(f"sysbus LoadELF @{FW}")

# Read initial PC (should be reset vector)
r = cmd("cpu PC")
print(f"Initial PC: {r.strip()}")

# Try different set syntaxes
print("\n=== Trying PC set commands ===")

# Method 1: cpu PC value
r = cmd("cpu PC 0x080002A8")
print(f"Method 1 (cpu PC addr): {r.strip()}")

r = cmd("cpu PC")
print(f"  PC after: {r.strip()}")

# Method 2: cpu SetRegisterUnsafe
r = cmd("cpu SetRegisterUnsafe 15 0x080002A8")
print(f"Method 2 (SetRegisterUnsafe): {r.strip()}")
r = cmd("cpu PC")
print(f"  PC after: {r.strip()}")

# Method 3: set cpu PerformanceInMips
r = cmd("cpu PCvalue 0x080002A8")
print(f"Method 3 (PCvalue): {r.strip()}")

# Method 4: sysbus WriteDoubleWord to PC register (NVIC CP15?)
# Cortex-M PC is R15, which is at system level
r = cmd("sysbus WriteDoubleWord 0xE000EDF8 0x080002A8")
print(f"Method 4 (write to core debug reg): {r.strip()}")

# Method 5: machine Reset and then set
# Maybe the machine needs to be started briefly first
cmd("start")
time.sleep(0.1)
cmd("cpu Stop")
r = cmd("cpu PC")
print(f"\nAfter start+stop, PC: {r.strip()}")

# Try setting PC now
r = cmd("cpu PC 0x080002A8")
print(f"cpu PC addr: {r.strip()}")
r = cmd("cpu PC")
print(f"  New PC: {r.strip()}")

sock.close()
