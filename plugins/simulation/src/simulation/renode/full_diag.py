#!/usr/bin/env python3
"""Comprehensive dual-MCU state check."""

import re
import subprocess
import time

from renode_client import RenodeClient

BASE = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

rc = RenodeClient()
rc.connect()


def read_pc(mach):
    rc.cmd(f'mach set "{mach}"', timeout=1)
    resp = rc.cmd("cpu PC", timeout=3)
    text = resp.decode("utf-8", errors="replace")
    m = re.search(r"0x([0-9a-fA-F]{7,8})\b", text)
    if m:
        val = int(m.group(1), 16)
        if 0x08000000 <= val <= 0x08100000:
            return val
    return None


def resolve(addr, elf):
    if addr is None:
        return "N/A"
    r = subprocess.run(
        ["arm-none-eabi-addr2line", "-e", elf, f"0x{addr:08x}"], capture_output=True, text=True
    )
    return r.stdout.strip()


# Load
print("Loading...")
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

print("Running for 3s...")
time.sleep(3)

# ─── F407 State ───
print("\n" + "=" * 60)
print("F407 MAIN MCU")
print("=" * 60)
fc = rc.read_u32("F407", 0x2000001C)
tick = rc.read_u32("F407", 0x20000088)
pc = read_pc("F407")
print(f"  frame_count  = {fc}")
print(f"  sys_tick_ms  = {tick}")
print(f"  PC           = {hex(pc) if pc else '???'}")
if pc:
    print(f"  → {resolve(pc, f'{BASE}/bottlesumo_main.elf')}")

# ─── F103 State ───
print("\n" + "=" * 60)
print("F103 AUX MCU (Sensor/Actuator)")
print("=" * 60)
tick103 = rc.read_u32("F103", 0x20000040)
pc103 = read_pc("F103")
word_1c = rc.read_u32("F103", 0x2000001C) or 0
estop = word_1c & 0xFF
spi_ready = (word_1c >> 8) & 0xFF
status = (rc.read_u32("F103", 0x2000003C) or 0) & 0xFF
enc_a = rc.read_u32("F103", 0x2000000C)
enc_b = rc.read_u32("F103", 0x20000014)
batt = (rc.read_u32("F103", 0x2000000A) or 0) & 0xFFFF

print(f"  sys_tick_ms  = {tick103}")
print(f"  estop_lock   = {estop}")
print(f"  status       = {status}")
print(f"  enc_a_count  = {enc_a}")
print(f"  enc_b_count  = {enc_b}")
print(f"  battery_mv   = {batt}")
print(f"  PC           = {hex(pc103) if pc103 else '???'}")
if pc103:
    print(f"  → {resolve(pc103, f'{BASE}/bottlesumo_aux.elf')}")

# SPI communication check
print("\n" + "=" * 60)
print("SPI Communication")
print("=" * 60)
print("F103 SPI TX buffer:")
rc.cmd('mach set "F103"')
for offset in range(0x26, 0x3C, 4):
    addr = 0x20000000 + (offset & ~3)
    val = rc.read_u32("F103", addr)
    if val is not None and val != 0:
        print(f"  0x{addr:08x} = 0x{val:08x}")

# Check if both tick counters advance
tick407_before = rc.read_u32("F407", 0x20000088)
tick103_before = rc.read_u32("F103", 0x20000040)
time.sleep(1)
tick407_after = rc.read_u32("F407", 0x20000088)
tick103_after = rc.read_u32("F103", 0x20000040)
print("\nSysTick advancement over 1s wall:")
print(
    f"  F407: {tick407_before} → {tick407_after} (Δ={tick407_after - tick407_before if tick407_after and tick407_before else 'N/A'})"
)
print(
    f"  F103: {tick103_before} → {tick103_after} (Δ={tick103_after - tick103_before if tick103_after and tick103_before else 'N/A'})"
)

rc.shutdown()
print("\nDone.")
