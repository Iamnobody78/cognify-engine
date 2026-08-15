#!/usr/bin/env python3
"""PC trace with addr2line to find what code blocks at frame 10."""

import subprocess
import time

from renode_client import RenodeClient

ELF = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build/bottlesumo_main.elf"
BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load both MCUs
for name, plat, elf_file in [
    ("F407", "stm32f4.repl", "bottlesumo_main.elf"),
    ("F103", "stm32f103.repl", "bottlesumo_aux.elf"),
]:
    r = rc.cmd(f'mach add "{name}"')
    print(f"  mach add {name}: {r[:50].decode('utf-8', errors='replace').strip()}...")
    r = rc.cmd(f'mach set "{name}"')
    print(f"  mach set {name}: {r[:50].decode('utf-8', errors='replace').strip()}...")
    r = rc.cmd(f"machine LoadPlatformDescription @platforms/cpus/{plat}")
    print(f"  platform {plat}: {r[:60].decode('utf-8', errors='replace').strip()}...")
    r = rc.cmd(f"sysbus LoadELF @{BASE}/{elf_file}")
    print(f"  LoadELF {elf_file}: {r[:80].decode('utf-8', errors='replace').strip()}...")

# Verify flash
rc.cmd('mach set "F407"')
r = rc.cmd("sysbus ReadDoubleWord 0x08000000")
print(f"  F407 flash[0]: {r.decode('utf-8', errors='replace').strip()}")

# Start both
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(0.3)

# Monitor
prev_fc = -1
for i in range(10):
    time.sleep(1)
    fc = rc.read_u32("F407", 0x2000001C) or 0
    tick = rc.read_u32("F407", 0x20000088) or 0
    pc = rc.read_pc("F407") or 0

    # Resolve symbol
    sym = ""
    if pc:
        try:
            r = subprocess.run(
                ["arm-none-eabi-addr2line", "-e", ELF, hex(pc)],
                capture_output=True,
                text=True,
                timeout=3,
            )
            sym = r.stdout.strip().split("\n")[0].split("/")[-1]
        except Exception:
            pass

    delta_fc = fc - prev_fc if prev_fc >= 0 else 0
    marker = " << STALL" if delta_fc == 0 and fc >= 10 else ""
    print(
        f"t={i + 1:2d}s  tick={tick:6d}  fc={fc:2d} (d={delta_fc:2d})  PC=0x{pc:08x}  {sym}{marker}"
    )
    prev_fc = fc

    if delta_fc == 0 and fc >= 10:
        if pc:
            rc.cmd('mach set "F407"')
            for a in range(pc, pc + 16, 2):
                resp = rc.cmd(f"sysbus ReadWord {hex(a)}")
                for line in resp.decode("utf-8", errors="replace").split("\n"):
                    line = line.strip()
                    if line.startswith("0x"):
                        print(f"  [{hex(a)}] = {line}")
                        break
        break

rc.shutdown()
