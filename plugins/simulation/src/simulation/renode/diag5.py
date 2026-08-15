#!/usr/bin/env python3
"""diag5.py - Minimal PC tracing with fixed parsing."""

import re
import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()
print("Renode ready.")

# ── Custom parsing for read_pc (returns raw bytes for debugging) ──

def read_pc_raw(mach):
    """Return raw bytes response from 'cpu PC' command."""
    rc.cmd(f'mach set "{mach}"', timeout=1)
    return rc.cmd("cpu PC", timeout=3)

def read_u32_custom(mach, addr):
    """Read a 32-bit word using regex-based parsing (handles both decimal and hex)."""
    rc.cmd(f'mach set "{mach}"', timeout=1)
    resp = rc.cmd(f"sysbus ReadDoubleWord {hex(addr)}", timeout=3)
    text = resp.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^[0-9]+$", line):
            return int(line)
        m = re.search(r"0x([0-9a-fA-F]{8})", line)
        if m:
            return int(m.group(1), 16)
    return None


# Load both MCUs
print("Loading...")
rc.cmd('mach add "F407"')
rc.cmd('mach set "F407"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_main.elf")
rc.cmd('mach add "F103"')
rc.cmd('mach set "F103"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_aux.elf")

# Start
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(1)

# Test raw PC response
print("\n=== Raw PC response test ===")
pc_raw = read_pc_raw("F407")
print(f"F407 raw PC response: {pc_raw!r}")
pc_raw2 = read_pc_raw("F103")
print(f"F103 raw PC response: {pc_raw2!r}")

# Quick frame check
fc407 = read_u32_custom("F407", 0x2000001C)
fc103 = read_u32_custom("F103", 0x2000001C)
tick407 = read_u32_custom("F407", 0x20000088)
print(f"\nF407: fc={fc407}, tick={tick407}")
print(f"F103: fc={fc103}")

# Wait and check again
time.sleep(2)
fc407 = read_u32_custom("F407", 0x2000001C)
fc103 = read_u32_custom("F103", 0x2000001C)
tick407 = read_u32_custom("F407", 0x20000088)
print("\nAfter 2s:")
print(f"F407: fc={fc407}, tick={tick407}")
print(f"F103: fc={fc103}")

# Dump more F103 state
print("\n=== F103 Memory Dump ===")
rc.cmd('mach set "F103"')
for offset in range(0, 0x80, 4):
    addr = 0x20000000 + offset
    val = read_u32_custom("F103", addr)
    sym = ""
    if offset == 0x1C:
        sym = "  <-- frame_count"
    elif offset == 0x88:
        sym = "  <-- sys_tick_ms if F407-style"
    if val is not None:
        print(f"  [0x{addr:08x}] = 0x{val:08x} {sym}")

rc.shutdown()
print("\nDone.")
