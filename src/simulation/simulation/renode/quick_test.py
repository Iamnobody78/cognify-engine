#!/usr/bin/env python3
"""Quick F103 check + frame_rate test"""

import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load both
for name, plat, elf in [
    ("F407", "stm32f4.repl", "bottlesumo_main.elf"),
    ("F103", "stm32f103.repl", "bottlesumo_aux.elf"),
]:
    rc.cmd(f'mach add "{name}"')
    rc.cmd(f'mach set "{name}"')
    rc.cmd(f"machine LoadPlatformDescription @platforms/cpus/{plat}")
    rc.cmd(f"sysbus LoadELF @{BASE}/{elf}")

# Start both
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(1.0)

# Read baseline
fc_start = rc.read_u32("F407", 0x2000001C) or 0
tick_start = rc.read_u32("F407", 0x20000088) or 0

# Wait 3 seconds
time.sleep(3)

fc_end = rc.read_u32("F407", 0x2000001C) or 0
tick_end = rc.read_u32("F407", 0x20000088) or 0

delta_fc = fc_end - fc_start
delta_tick = tick_end - tick_start

print(f"Frame count: {fc_start} → {fc_end} (delta={delta_fc})")
print(f"SysTick ms:  {tick_start} → {tick_end} (delta={delta_tick})")
print(f"Effective frame rate: {delta_fc / (delta_tick / 1000.0):.1f} Hz")
print(f"Sim speed: {delta_tick / 3000.0 * 100:.1f}% real-time")

# Check F103 state
rc.cmd('mach set "F103"')
resp = rc.cmd("cpu PC")
pc103 = rc.read_pc("F103")
print(f"\nF103 PC: 0x{pc103:08x}" if pc103 else "F103 PC: ???")

estop = rc.read_u32("F103", 0x2000001C)
spi_tx = rc.read_u32("F103", 0x20000080)
print(f"F103 estop_lock: {estop}, spi_tx_buf[0]: {spi_tx}")

rc.shutdown()
