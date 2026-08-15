#!/usr/bin/env python3
"""
Frame rate measurement test for dual-MCU BottleSumo firmware in Renode.
Measures F407 and F103 frame rates, SysTick advancement.
"""

import re
import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()
print("Renode ready.")


def read_u32_filtered(mach, addr):
    """Read a 32-bit word, filtering out address echoes via regex."""
    rc.cmd(f'mach set "{mach}"', timeout=1)
    resp = rc.cmd(f"sysbus ReadDoubleWord {hex(addr)}", timeout=3)
    text = resp.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("0x"):
            try:
                val = int(line, 16)
                if val != addr:
                    return val
            except Exception:
                pass
    # Fallback: regex
    for line in text.split("\n"):
        line_clean = line.strip()
        m = re.match(r"^0x([0-9a-fA-F]{8})$", line_clean)
        if m:
            val = int(m.group(1), 16)
            if val != addr:
                return val
    return None


# Load both MCUs
print("Loading MCUs...")
rc.cmd('mach add "F407"')
rc.cmd('mach set "F407"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_main.elf")
rc.cmd('mach add "F103"')
rc.cmd('mach set "F103"')
rc.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
rc.cmd(f"sysbus LoadELF @{BASE}/bottlesumo_aux.elf")

print("Starting both MCUs...")
rc.cmd('mach set "F407"')
rc.cmd("start")
rc.cmd('mach set "F103"')
rc.cmd("start")
time.sleep(2)

print("\n=== Frame Rate Test ===")
print(f"{'Wall':>7s}  {'Tick407':>9s}  {'FC407':>6s}  {'FC103':>6s}  {'FPS407':>7s}")
print("-" * 50)

last_fc407 = 0
last_fc103 = 0
last_time = time.time()
test_start = time.time()

for _i in range(20):
    t0 = time.time()
    fc407 = read_u32_filtered("F407", 0x2000001C)
    fc103 = read_u32_filtered("F103", 0x2000001C)
    tick407 = read_u32_filtered("F407", 0x20000088)

    elapsed = t0 - last_time
    fps407 = (fc407 - last_fc407) / elapsed if (elapsed > 0 and fc407 is not None) else 0
    fps103 = (fc103 - last_fc103) / elapsed if (elapsed > 0 and fc103 is not None) else 0

    wall_s = t0 - test_start
    fc407_str = f"{fc407:6d}" if fc407 is not None else "   N/A"
    fc103_str = f"{fc103:6d}" if fc103 is not None else "   N/A"
    tick_str = f"{tick407:9d}" if tick407 is not None else "    N/A"

    print(f"{wall_s:7.1f}  {tick_str}  {fc407_str}  {fc103_str}  {fps407:7.1f}")

    last_fc407 = fc407 if fc407 is not None else last_fc407
    last_fc103 = fc103 if fc103 is not None else last_fc103
    last_time = t0
    time.sleep(0.5)

# Final rate
total_elapsed = time.time() - test_start
fc_final = read_u32_filtered("F407", 0x2000001C)
if fc_final is not None and fc_final > 0:
    avg_fps = fc_final / total_elapsed
    print(f"\nAverage F407 frame rate: {avg_fps:.1f} fps ({total_elapsed:.1f}s, {fc_final} frames)")

rc.shutdown()
print("Done.")
