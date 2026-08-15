#!/usr/bin/env python3
"""Try different ways to read/set PC in current Renode."""

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
    time.sleep(0.15)
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
    return buf  # Return raw bytes for inspection


# Load
cmd('mach add "F407"')
cmd('mach set "F407"')
cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
cmd(f"sysbus LoadELF @{FW}")

# Try cpu PC (raw)
r = cmd("cpu PC")
print(f"cpu PC raw: {r}")

# Try to list cpu methods
r = cmd("cpu")
print(f"\ncpu methods:\n{r.decode(errors='replace')[:500]}")

# Try pc (no cpu prefix)
r = cmd("pc")
print(f"\npc raw: {r}")

# Try reading reset vector from flash (0x08000004)
cmd("start")
time.sleep(0.2)
r = cmd("sysbus ReadDoubleWord 0x08000004")
print(f"\nsysbus ReadDoubleWord 0x08000004 (reset vector): {r}")

# Try reading SP from 0x08000000
r = cmd("sysbus ReadDoubleWord 0x08000000")
print(f"Initial SP: {r}")

# Try reading frame_count to verify we can read SRAM
r = cmd("sysbus ReadDoubleWord 0x2000001C")
print(f"frame_count @ 0x2000001C: {r}")

sock.close()
