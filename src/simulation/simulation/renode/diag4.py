#!/usr/bin/env python3
"""
diag4.py - PC-tracing diagnostic to find frame_count=10 stall point.
Samples PC every 200ms for 3 seconds after frame_count reaches 10,
resolving addresses via addr2line.
"""

import re
import subprocess
import sys
import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"
ADDR2LINE = "arm-none-eabi-addr2line"

rc = RenodeClient()
rc.connect()
print("Renode ready.")

# ── Custom read_pc with regex parsing ──

def read_pc(mach):
    rc.cmd(f'mach set "{mach}"', timeout=1)
    resp = rc.cmd("cpu PC", timeout=3)
    text = resp.decode("utf-8", errors="replace")
    m = re.search(r"0x([0-9a-fA-F]{8})", text)
    if m:
        return int(m.group(1), 16)
    return None


def resolve(addr, elf_path):
    """Resolve address to source location."""
    if addr is None or addr < 0x08000000 or addr > 0x08100000:
        return "invalid"
    r = subprocess.run(
        [ADDR2LINE, "-e", elf_path, f"0x{addr:08x}"], capture_output=True, text=True, timeout=5
    )
    out = r.stdout.strip()
    if out and "??" not in out:
        return out
    return f"0x{addr:08x} (unknown)"


# ═══ Load MCUs ═══
print("\n=== Loading MCUs ===")
rc.cmd('mach add "F407"')
rc.cmd('mach set "F407"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_main.elf")
print("F407: loaded")

rc.cmd('mach add "F103"')
rc.cmd('mach set "F103"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_aux.elf")
print("F103: loaded")

# Check pre-start
print("\n=== Pre-start State ===")
tick = rc.read_u32("F407", 0x20000088)
fc = rc.read_u32("F407", 0x2000001C)
pc = read_pc("F407")
print(f"F407: sys_tick_ms={tick}, frame_count={fc}, PC={hex(pc) if pc else '???'}")
fc_aux = rc.read_u32("F103", 0x2000001C)
print(f"F103: frame_count={fc_aux}")

# Start both
print("\n=== Starting ===")
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(0.5)

# Phase 1: Wait for frame_count to reach 10
print("\n=== Phase 1: Waiting for frame_count >= 10 ===")
stall_start = None
for i in range(30):
    fc = rc.read_u32("F407", 0x2000001C)
    tick = rc.read_u32("F407", 0x20000088)
    print(f"  t={i * 0.2:.1f}s  fc={fc}  tick={tick}")
    if fc and fc >= 10:
        stall_start = time.time()
        print(f"\n!!! Frame count reached 10 at t={i * 0.2:.1f}s. Beginning PC trace.")
        break
    time.sleep(0.2)

if stall_start is None:
    print("ERROR: frame_count never reached 10")
    fc = rc.read_u32("F407", 0x2000001C)
    tick = rc.read_u32("F407", 0x20000088)
    pc = read_pc("F407")
    print(f"Final state: fc={fc}, tick={tick}, PC={hex(pc) if pc else '???'}")
    rc.shutdown()
    sys.exit(1)

# Phase 2: PC tracing at stall
print("\n=== Phase 2: PC trace (every 200ms for 4s) ===")
ELF_MAIN = f"{BASE}/bottlesumo_main.elf"
ELF_AUX = f"{BASE}/bottlesumo_aux.elf"

for _i in range(20):
    elapsed = time.time() - stall_start
    pc407 = read_pc("F407")
    fc407 = rc.read_u32("F407", 0x2000001C)
    tick407 = rc.read_u32("F407", 0x20000088)
    pc103 = read_pc("F103")
    fc103 = rc.read_u32("F103", 0x2000001C)
    loc407 = resolve(pc407, ELF_MAIN) if pc407 else "???"
    loc103 = resolve(pc103, ELF_AUX) if pc103 else "???"
    print(
        f"[{elapsed:5.1f}s] F407 PC={hex(pc407) if pc407 else '???'} ({loc407}) fc={fc407} tick={tick407} | F103 PC={hex(pc103) if pc103 else '???'} fc={fc103}"
    )
    time.sleep(0.2)

# Phase 3: Memory dump around frame_count
print("\n=== Phase 3: Memory snapshot ===")
rc.cmd('mach set "F407"')
for offset in range(0, 0x80, 4):
    addr = 0x20000000 + offset
    val = rc.read_u32("F407", addr)
    print(f"  [0x{addr:08x}] = 0x{val:08x} ({val})")

rc.shutdown()
print("\nDone.")
