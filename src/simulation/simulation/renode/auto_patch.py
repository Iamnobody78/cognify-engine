#!/usr/bin/env python3
"""
Auto-patcher: Find ALL conditional branches that form tight loops (<0x40 bytes)
and convert them to NOP. This handles both peripheral polling and timer-based
loops in I2C, SPI, and other driver functions.
"""

import re
import struct
import subprocess
import sys


def find_fo(data, flash_addr):
    e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x2A)[0]
    e_phnum = struct.unpack_from("<H", data, 0x2C)[0]
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        p_offset = struct.unpack_from("<I", data, off + 4)[0]
        p_vaddr = struct.unpack_from("<I", data, off + 8)[0]
        p_filesz = struct.unpack_from("<I", data, off + 16)[0]
        if p_type == 1 and p_vaddr <= flash_addr < p_vaddr + p_filesz:
            return p_offset + (flash_addr - p_vaddr)
    return None


def find_tight_loops(elf):
    result = subprocess.run(["arm-none-eabi-objdump", "-d", elf], capture_output=True, text=True)
    loops = []
    for line in result.stdout.split("\n"):
        m = re.match(
            r"\s+([0-9a-f]+):\s+[0-9a-f ]+?\s+(bpl|bmi|bne|beq|bls|bhi|ble|bgt|bge|blt)\.(n|w)",
            line,
        )
        if not m:
            continue
        addr = int(m.group(1), 16)
        instr = f"{m.group(2)}.{m.group(3)}"
        t = re.search(r"\t([0-9a-f]+)\s+<", line)
        if not t:
            continue
        target = int(t.group(1).zfill(8), 16)
        if target < addr and addr - target < 0x40:
            loops.append((addr, target, instr))
    return loops


def patch_elf(elf_path):
    loops = find_tight_loops(elf_path)
    print(f"\nFound {len(loops)} tight loops (len < 0x40):")
    for addr, target, instr in loops:
        print(f"  0x{addr:08x}: {instr} -> 0x{target:08x} (len={addr - target})")

    with open(elf_path, "rb") as f:
        data = bytearray(f.read())

    patched = 0
    for addr, _, instr in loops:
        fo = find_fo(data, addr)
        if fo is None:
            print(f"  FAIL: 0x{addr:08x} no file offset")
            continue

        # Read 2 bytes at file offset (little-endian: low byte first)
        cur = bytes(data[fo : fo + 2])

        # Verify it's a conditional branch (Thumb-2: encoding Dx xx in memory)
        # bne D1xx, beq D0xx, bpl D5xx, bmi D4xx, bls D9xx, bhi D8xx, etc.
        # In little-endian: byte[0] = offset, byte[1] = 0xDx
        if (cur[1] & 0xF0) == 0xD0:
            pass  # OK
        else:
            print(f"  WARN: 0x{addr:08x} unexpected opcode: {cur.hex()}")
            continue

        # Replace with NOP (0xBF00 → bytes 0x00 0xBF)
        data[fo : fo + 2] = b"\x00\xbf"
        print(f"  NOP: 0x{addr:08x} ({instr}, {cur.hex()}) -> NOP")
        patched += 1

    with open(elf_path, "wb") as f:
        f.write(data)

    return patched


if __name__ == "__main__":
    for elf in sys.argv[1:]:
        print(f"\n{'=' * 60}")
        print(f"Patching: {elf}")
        print(f"{'=' * 60}")
        n = patch_elf(elf)
        print(f"Patched {n} instructions -> NOP")
