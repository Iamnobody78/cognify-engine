#!/usr/bin/env python3
"""Full control: start Renode, load MCUs, test SysTick all from Python."""

import re
import socket
import subprocess
import time

FW_MAIN = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"
FW_AUX = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_aux.elf"

subprocess.run("pkill -f renode", shell=True, capture_output=True)
time.sleep(1)

# Start Renode WITHOUT -e (just monitor mode)
proc = subprocess.Popen(
    ["renode", "--port", "3333", "--disable-xwt"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(f"Renode PID={proc.pid}")

for i in range(30):  # noqa: B007
    try:
        s = socket.create_connection(("127.0.0.1", 3333), timeout=1)
        s.close()
        break
    except Exception:
        time.sleep(1)
print(f"Monitor ready after {i + 1}s")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10.0)
sock.connect(("127.0.0.1", 3333))
time.sleep(0.5)
data = sock.recv(4096)
for chunk in data.split(b"\xff"):
    if len(chunk) >= 2 and chunk[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + chunk[1:2])


def cmd(c, quiet=False):
    sock.sendall((c + "\n").encode())
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"(monitor)" in chunk:
                break
    except TimeoutError:
        pass
    return re.sub(rb"\x1b\[[0-9;]*m", b"", buf).decode(errors="replace")


# ── Load machines ──
print("\n=== Creating F407 ===")
r = cmd('mach add "F407"')
print(r.strip()[:200])

cmd('mach set "F407"')
r = cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
print(r.strip()[:200])

r = cmd(f"sysbus LoadELF @{FW_MAIN}")
print(r.strip()[:200])

print("\n=== Creating F103 ===")
r = cmd('mach add "F103"')
print(r.strip()[:200])

cmd('mach set "F103"')
r = cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
print(r.strip()[:200])

r = cmd(f"sysbus LoadELF @{FW_AUX}")
print(r.strip()[:200])

# ── Check state before start ──
print("\n=== Pre-start state ===")
cmd('mach set "F407"')
r = cmd("sysbus ReadDoubleWord 0x20000004")


def p(r):
    for line in r.split("\n"):
        if "0x" in line:
            try:
                return int(line.strip().split("0x")[1], 16)
            except Exception:

                pass
    return None


print(f"  sys_tick_ms = {p(r)} (expect ~0 before start)")

# ── Start both ──
print("\n=== Starting machines ===")
cmd('mach set "F407"')
cmd("start")
cmd('mach set "F103"')
cmd("start")

# ── Verify with time ──
print("\n=== After 1 second ===")
time.sleep(1.0)

cmd('mach set "F407"')
r = cmd("sysbus ReadDoubleWord 0x20000004")
t1 = p(r)
print(f"  sys_tick_ms = {t1}")

r = cmd("sysbus ReadDoubleWord 0x2000001C")
fc1 = p(r)
print(f"  frame_count = {fc1}")

r = cmd("cpu PC")
pc1 = p(r)
print(f"  PC = {hex(pc1) if pc1 else 0}")

if fc1 and fc1 > 0:
    print(f"\n  ✓ FIRMWARE RUNNING! frame_count={fc1}")
else:
    print(f"\n  ✗ Firmware stuck. PC={hex(pc1) if pc1 else 0}")

# Check if SysTick is enabled at all via NVIC
r = cmd("sysbus ReadDoubleWord 0xE000E100")  # ISER[0] should have bit 15 (SysTick)
print(f"  NVIC ISER[0] = {p(r)}")

sock.close()
proc.kill()
