#!/usr/bin/env python3
"""Read PC and frame_count at each step to pinpoint what blocks after frame 10."""

import subprocess
import time

from renode_client import RenodeClient

ELF = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"
BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load both machines
for name, plat, elf_file in [
    ("F407", "stm32f4.repl", "bottlesumo_main.elf"),
    ("F103", "stm32f103.repl", "bottlesumo_aux.elf"),
]:
    rc.cmd(f'mach add "{name}"')
    rc.cmd(f'mach set "{name}"')
    rc.cmd(f"machine LoadPlatformDescription @platforms/cpus/{plat}")
    rc.cmd(f"sysbus LoadELF @{BASE}/{elf_file}")

# Start both
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(0.8)

print(f"{'Time':>8s}  {'Tick':>8s}  {'Frame':>6s}  PC         Symbol")
print("-" * 70)
prev_pc = 0
prev_fc = 0
stall_count = 0

for i in range(30):
    tick = rc.read_u32("F407", 0x20000088) or 0
    fc = rc.read_u32("F407", 0x2000001C) or 0
    pc = rc.read_pc("F407") or 0

    # Resolve symbol
    sym = ""
    try:
        r = subprocess.run(
            ["arm-none-eabi-addr2line", "-e", ELF, hex(pc)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        sym = r.stdout.strip().split("\n")[0]
        if "/" in sym:
            sym = sym.split("/")[-1]
    except Exception:
        pass

    marker = ""
    if pc == prev_pc:
        stall_count += 1
    else:
        stall_count = 0
    if stall_count >= 3:
        marker = " << STUCK"

    print(f"{i * 0.2:7.1f}s  {tick:8d}  {fc:6d}  0x{pc:08x}  {sym}{marker}")
    prev_pc, prev_fc = pc, fc

    if stall_count >= 5:
        print(f"\nPC stuck at 0x{pc:08x} for {stall_count} samples. Breaking.")
        break

    time.sleep(0.2)

rc.shutdown()
