#!/usr/bin/env python3
"""Quick F103 diagnostic - what's it doing?"""

import subprocess
import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()

# Load both machines
rc.cmd('mach add "F407"')
rc.cmd('mach set "F407"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_main.elf")
rc.cmd('mach add "F103"')
rc.cmd('mach set "F103"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_aux.elf")

rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(3)

# F103 memory scan - find the real frame counter
print("=== F103 Memory Scan (0x20000000 - 0x20000100) ===")
rc.cmd('mach set "F103"')
for offset in range(0, 0x100, 4):
    addr = 0x20000000 + offset
    val = rc.read_u32("F103", addr)
    if val is not None and val > 0:
        print(f"  0x{addr:08x} = 0x{val:08x} ({val})", end="")
        if 0 < val < 1000:
            print("  <-- possible counter!")
        else:
            print()

# F103 PC
pc103 = rc.read_pc("F103")
print(f"\nF103 PC: {hex(pc103) if pc103 else '???'}")

# Resolve
if pc103:
    r = subprocess.run(
        ["arm-none-eabi-addr2line", "-e", f"{BASE}/bottlesumo_aux.elf", f"0x{pc103:08x}"],
        capture_output=True,
        text=True,
    )
    print(f"F103 PC resolves to: {r.stdout.strip()}")

# Dump disassembly around PC
if pc103:
    r2 = subprocess.run(
        [
            "arm-none-eabi-objdump",
            "-d",
            "--start-address",
            f"0x{pc103 - 0x20:08x}",
            "--stop-address",
            f"0x{pc103 + 0x10:08x}",
            f"{BASE}/bottlesumo_aux.elf",
        ],
        capture_output=True,
        text=True,
    )
    print("\nDisassembly around PC:")
    for line in r2.stdout.split("\n"):
        if ":" in line:
            print(line)

# Also check F407 for comparison
print("\n=== F407 State ===")
fc407 = rc.read_u32("F407", 0x2000001C)
tick = rc.read_u32("F407", 0x20000088)
pc407 = rc.read_pc("F407")
print(f"FC={fc407}, Tick={tick}, PC={hex(pc407) if pc407 else '???'}")

rc.shutdown()
print("Done.")
