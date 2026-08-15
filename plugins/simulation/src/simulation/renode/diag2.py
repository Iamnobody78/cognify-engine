#!/usr/bin/env python3
"""Quick diagnostic: read correct sys_tick_ms address (0x20000088) and frame_count"""

import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load MCUs
print("Loading...")
for name, plat, elf in [
    ("F407", "stm32f4.repl", "bottlesumo_main.elf"),
    ("F103", "stm32f103.repl", "bottlesumo_aux.elf"),
]:
    rc.cmd(f'mach add "{name}"')
    rc.cmd(f'mach set "{name}"')
    rc.cmd(f"machine LoadPlatformDescription @platforms/cpus/{plat}")
    rc.cmd(f"sysbus LoadELF @{BASE}/{elf}")
    print(f"  {name}: loaded")

# Check pre-start state
print("\nPre-start:")
print(f"  sys_tick_ms (0x20000088) = {rc.read_u32('F407', 0x20000088)}")
print(f"  frame_count (0x2000001C) = {rc.read_u32('F407', 0x2000001C)}")
print(f"  PC = skip")

# Start both
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(0.5)

# Monitor every 500ms for 3 seconds
print("\nMonitoring (every 500ms):")
for i in range(6):
    t0 = rc.read_u32("F407", 0x20000088)
    fc = rc.read_u32("F407", 0x2000001C)
    print(f"  t={(i * 0.5):.1f}s: sys_tick_ms=0x{t0:08x} ({t0:>12d}), frame_count={fc}")
    time.sleep(0.5)

rc.shutdown()
print("\nDone.")
