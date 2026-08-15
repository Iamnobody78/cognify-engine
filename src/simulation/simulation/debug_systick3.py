#!/usr/bin/env python3
"""Connect to running Renode, load MCUs, test SysTick."""

import re
import socket
import time

FW_MAIN = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"
FW_AUX = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_aux.elf"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(15.0)
sock.connect(("127.0.0.1", 3333))

# Telnet negotiation
time.sleep(0.5)
data = sock.recv(4096)
for chunk in data.split(b"\xff"):
    if len(chunk) >= 2 and chunk[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + chunk[1:2])


def cmd(c):
    sock.sendall((c + "\n").encode())
    time.sleep(0.2)
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


# ── Load F407 ──
print("Loading F407...")
cmd('mach add "F407"')
cmd('mach set "F407"')
r = cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
print(f"  F4 platform: {r.strip()[:100]}")
r = cmd(f"sysbus LoadELF @{FW_MAIN}")
print(f"  ELF loaded: {r.strip()[:100]}")

# ── Load F103 ──
print("Loading F103...")
cmd('mach add "F103"')
cmd('mach set "F103"')
r = cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
print(f"  F1 platform: {r.strip()[:100]}")
r = cmd(f"sysbus LoadELF @{FW_AUX}")
print(f"  ELF loaded: {r.strip()[:100]}")

# ── Pre-start reads ──
print("\n=== PRE-START ===")
cmd('mach set "F407"')
r = cmd("sysbus ReadDoubleWord 0x20000004")
print(f"  sys_tick_ms: {parse_hex(r)}")
r = cmd("sysbus ReadDoubleWord 0x2000001C")
print(f"  frame_count: {parse_hex(r)}")

# ── Start both ──
print("\n=== STARTING ===")
cmd('mach set "F407"')
cmd("start")
cmd('mach set "F103"')
cmd("start")
print("  Started both machines")

# ── Wait and check ──
for delay in [1, 2, 3]:
    time.sleep(delay)
    print(f"\n  After {delay}s:")
    cmd('mach set "F407"')
    try:
        r = cmd("sysbus ReadDoubleWord 0x20000004")
        t = parse_hex(r)
        r2 = cmd("sysbus ReadDoubleWord 0x2000001C")
        fc = parse_hex(r2)
        r3 = cmd("cpu PC")
        pc = parse_hex(r3)
        print(f"    sys_tick_ms={t}, frame_count={fc}, PC={hex(pc) if pc else 0}")
        if fc and fc > 0:
            print("    ✓ FIRMWARE RUNNING")
            break
    except Exception as e:
        print(f"    ERROR: {e}")

sock.close()
