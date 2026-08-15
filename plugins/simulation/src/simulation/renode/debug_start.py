#!/usr/bin/env python3
"""Direct debug: check if start works and PC is readable"""

import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load F407
r = rc.cmd('mach add "F407"')
print("add F407:", repr(r[:80]))

r = rc.cmd('mach set "F407"')
print("set F407:", repr(r[:80]))

r = rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
print("plat F4:", repr(r[:120]))

r = rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_main.elf")
print("LoadELF main:", repr(r[:120]))

# Check pre-start PC
r = rc.cmd("cpu PC")
print("PC pre-start:", repr(r))

# Read a known flash location to verify ELF loaded
r = rc.cmd("sysbus ReadDoubleWord 0x08000000")
print("flash[0x08000000]:", repr(r))

r = rc.cmd("sysbus ReadDoubleWord 0x08000004")
print("flash[0x08000004] (reset vector):", repr(r))

# Start
r = rc.cmd("start")
print("start result:", repr(r))

# Wait
time.sleep(1)

# Check post-start PC
r = rc.cmd("cpu PC")
print("PC post-start:", repr(r))

# Read frame_count and sys_tick
r = rc.cmd("sysbus ReadDoubleWord 0x2000001C")
print("frame_count:", repr(r))

r = rc.cmd("sysbus ReadDoubleWord 0x20000088")
print("sys_tick_ms:", repr(r))

rc.shutdown()
