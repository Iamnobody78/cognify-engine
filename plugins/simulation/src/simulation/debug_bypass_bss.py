#!/usr/bin/env python3
"""Bypass buggy BSS zeroing by setting PC directly to main() then start."""

import re
import socket
import time

FW_MAIN = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"
FW_AUX = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_aux.elf"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(15.0)
sock.connect(("127.0.0.1", 3333))
time.sleep(0.5)
data = sock.recv(4096)
for chunk in data.split(b"\xff"):
    if len(chunk) >= 2 and chunk[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + chunk[1:2])


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
            if b"(monitor)" in chunk or b"(F103" in chunk or b"(F407" in chunk:
                break
    except TimeoutError:
        pass
    return re.sub(rb"\x1b\[[0-9;]*m", b"", buf).decode(errors="replace")


def parse_hex(r):
    for line in r.split("\n"):
        s = line.strip()
        if s.startswith("0x") or s.startswith("-0x"):
            try:
                return int(s, 16)
            except Exception:

                pass
    return None


# Load both machines
print("Loading F407...")
cmd('mach add "F407"')
cmd('mach set "F407"')
cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
cmd(f"sysbus LoadELF @{FW_MAIN}")

print("Loading F103...")
cmd('mach add "F103"')
cmd('mach set "F103"')
cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
cmd(f"sysbus LoadELF @{FW_AUX}")

# ── Bypass BSS zeroing: set PC to main() ──
print("\nBypassing buggy BSS zeroing...")

# Set PC to main() on F407
cmd('mach set "F407"')
c = cmd("cpu PC 0x080002A8")  # main() address
print(f"  F407 PC set to main(): {parse_hex(c)}")

# Set PC to main() on F103
cmd('mach set "F103"')
c = cmd("cpu PC 0x08000158")  # F103 main() address (verified via nm)
print(f"  F103 PC tentative: {parse_hex(c)}")

# ── Now start both ──
print("\nStarting both...")
cmd('mach set "F407"')
cmd("start")
cmd('mach set "F103"')
cmd("start")

# ── Verify execution ──
for t in [0.5, 1.0, 2.0]:
    time.sleep(t)
    print(f"\n--- t={t}s ---")
    cmd('mach set "F407"')
    pc = parse_hex(cmd("cpu PC"))
    fc = parse_hex(cmd("sysbus ReadDoubleWord 0x2000001C"))
    st = parse_hex(cmd("sysbus ReadDoubleWord 0x20000004"))
    print(f"  F407 PC={hex(pc) if pc else 0}, frame_count={fc}, sys_tick_ms={st}")

    if fc and fc > 0:
        print("  ✓ FIRMWARE RUNNING! Frame count increasing!")
        break

sock.close()
