#!/usr/bin/env python3
"""Find all backward-jumping conditional branches (tight loops) in ELF."""

import re
import subprocess
import sys

elf = sys.argv[1]
result = subprocess.run(["arm-none-eabi-objdump", "-d", elf], capture_output=True, text=True)

lines = result.stdout.split("\n")

# We need to match tab-separated lines like:
# " 8000224:\td508      \tbpl.n\t8000238 <i2c1_write_register.isra.0+0x6c>"

jumps = []
for line in lines:
    m = re.match(
        r"\s+([0-9a-f]+):\s+([0-9a-f ]+?)\s+(bpl|bmi|bne|beq|bls|bhi|bcc|bcs|bvs|bvc|ble|bgt|bge|blt)\.(n|w)",
        line,
    )
    if not m:
        continue

    addr = int(m.group(1), 16)
    instr = f"{m.group(3)}.{m.group(4)}"

    # Find the target address (no 0x prefix in ARM objdump): "8000238 <name>"
    t = re.search(r"\t([0-9a-f]+)\s+<", line)
    if not t:
        continue

    target_hex = t.group(1)
    # Pad to 8 hex digits
    target_hex = target_hex.zfill(8)
    target = int(target_hex, 16)

    if target < addr:
        dist = addr - target
        jumps.append((addr, instr, target, dist, line.strip()))

print(f"Found {len(jumps)} backward conditional branches:")
for addr, instr, target, dist, _code in sorted(jumps):
    flag = " *** TIGHT ***" if dist < 0x30 else ""
    print(f"  0x{addr:08x}: {instr} -> 0x{target:08x} (len={dist}){flag}")
