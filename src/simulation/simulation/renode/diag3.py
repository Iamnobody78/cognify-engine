#!/usr/bin/env python3
"""diag3: Extended from working diag2.py — reads PC when frame_count stalls."""

import subprocess
import time

from renode_client import RenodeClient

ELF = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"
BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load both machines
for name, plat, elf in [
    ("F407", "stm32f4.repl", "bottlesumo_main.elf"),
    ("F103", "stm32f103.repl", "bottlesumo_aux.elf"),
]:
    rc.cmd(f'mach add "{name}"')
    rc.cmd(f'mach set "{name}"')
    rc.cmd(f"machine LoadPlatformDescription @platforms/cpus/{plat}")
    rc.cmd(f"sysbus LoadELF @{BASE}/{elf}")

# Start
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(0.5)

print("Monitoring: tick, fc, PC, symbol")
print("-" * 65)
prev_fc = -1
stall_count = 0

for i in range(12):
    tick = rc.read_u32("F407", 0x20000088) or 0
    fc = rc.read_u32("F407", 0x2000001C) or 0
    pc = rc.read_pc("F407") or 0
    delta = fc - prev_fc if prev_fc >= 0 else 0

    # Resolve symbol via addr2line
    sym = ""
    if pc:
        try:
            r = subprocess.run(
                ["arm-none-eabi-addr2line", "-e", ELF, hex(pc)],
                capture_output=True,
                text=True,
                timeout=3,
            )
            sym = r.stdout.strip().split("\n")[0].split("/")[-1] if r.stdout else ""
        except Exception:
            pass

    marker = ""
    if fc == prev_fc and prev_fc >= 5:
        stall_count += 1
    else:
        stall_count = 0
    if stall_count >= 2:
        marker = f" << STALL({stall_count})"

    print(f"t={i * 0.5:4.1f}s tick={tick:5d} fc={fc:2d} d={delta:2d} PC=0x{pc:08x} {sym}{marker}")
    prev_fc = fc

    if stall_count >= 3:
        # Read surrounding code
        print(f"\nPC stuck at 0x{pc:08x}. Nearby instructions:")
        rc.cmd('mach set "F407"')
        for a in range(max(0, pc - 8), pc + 16, 2):
            resp = rc.cmd(f"sysbus ReadHalfWord {hex(a)}")
            # Parse for 0xXXXX pattern
            for line in resp.split("\n"):
                line = line.strip()
                parts = line.split()
                for p in parts:
                    if p.startswith("0x") and len(p) == 6:
                        val = int(p, 16)
                        marker2 = " <-- PC" if a == pc else ""
                        print(f"  0x{a:08x}: 0x{val:04x}{marker2}")
                        break
        break

    time.sleep(0.5)

rc.shutdown()
