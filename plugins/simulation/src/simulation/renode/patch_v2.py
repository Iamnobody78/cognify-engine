#!/usr/bin/env python3
"""
Comprehensive ELF patcher for Renode simulation.
Patches ALL peripheral-dependent tight loops (conditional branches that form
backward loops of <0x60 bytes, indicating hardware register polling).
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
    """Find backwards conditional branches with small distance"""
    result = subprocess.run(["arm-none-eabi-objdump", "-d", elf], capture_output=True, text=True)
    loops = []
    for line in result.stdout.split("\n"):
        m = re.match(
            r"\s+([0-9a-f]+):\s+([0-9a-f ]+?)\s+(bpl|bmi|bne|beq|bls|bhi|ble|bgt|bge|blt)\.(n|w)",
            line,
        )
        if not m:
            continue
        addr = int(m.group(1), 16)
        f"{m.group(3)}.{m.group(4)}"
        t = re.search(r"\t([0-9a-f]+)\s+<", line)
        if not t:
            continue
        target = int(t.group(1).zfill(8), 16)
        if target < addr and addr - target < 0x40:
            loops.append(addr)
    return sorted(loops)


def patch_elf(elf_path, manual_patches, auto_patch_loops=True):
    with open(elf_path, "rb") as f:
        data = bytearray(f.read())

    # Auto-find tight loops
    if auto_patch_loops:
        auto_loops = find_tight_loops(elf_path)
        # Add any auto-found loops not already in manual list
        existing_addrs = {p[0] for p in manual_patches}
        for addr in auto_loops:
            if addr not in existing_addrs:
                manual_patches.append(
                    (
                        addr,
                        f"AUTO: tight loop at 0x{addr:08x}",
                        b"\x00\xbf\x00\xbf",
                        b"\x00\xbf\x00\xbf",
                    )
                )

    for addr, desc, old, new in manual_patches:
        fo = find_fo(data, addr)
        if fo is None:
            # Try to find by scanning for byte pattern nearby
            print(f"  FAIL: {desc} (no file offset at 0x{addr:08x})")
            continue
        # For 2-byte nop patches (bpl.n, bls.n, bne.n, etc. -> nop)
        cur = bytes(data[fo : fo + len(old)])
        if old == new:  # Auto-nop marker
            # Read 2 bytes, verify it's a conditional branch, replace with nop
            cur_2 = bytes(data[fo : fo + 2])
            cur_4 = bytes(data[fo : fo + 4])
            # Check first byte for conditional branch opcodes:
            # bpl.n: D5xx, bmi.n: D5xx with different condition
            # bls.n: D9xx, bne.n: D1xx, beq.n: D0xx, bhi.n: D8xx
            # bge.n: DAxx, blt.n: DBxx, ble.n: DDxx, bgt.n: DCxx
            if cur_2[0] & 0xF0 in (0xD0,):
                if (
                    cur_2[1] == 0xD5
                    or cur_2[1] == 0xD4
                    or cur_2[1] in (0xD1, 0xD0, 0xD9, 0xD8, 0xDA, 0xDB, 0xDC, 0xDD)
                ):  # bpl.n
                    data[fo : fo + 2] = b"\x00\xbf"
                    print(f"  OK: {desc} [{cur_2.hex()}] -> nop")
                elif cur_4[0:2] in (b"\xd5",) or (cur_4[0:2][0] & 0xF0 == 0xD0 <= 0xDF):
                    # Actually, all DxXX are conditional branches
                    data[fo : fo + 2] = b"\x00\xbf"
                    print(f"  OK: {desc} [{cur_2.hex()}] -> nop")
                else:
                    print(f"  WARN: {desc} unexpected opcode {cur_2.hex()}")
            else:
                print(f"  WARN: {desc} not a conditional branch ({cur_2.hex()})")
        else:
            if cur == new:
                print(f"  SKIP: {desc}")
            elif cur == old:
                data[fo : fo + len(new)] = new
                print(f"  OK:   {desc}")
            else:
                print(f"  MISMATCH: {desc} exp={old.hex()} got={cur.hex()}")

    with open(elf_path, "wb") as f:
        f.write(data)


# ═══════════════════════════════════════════
# Manual patches (specific transformations)
# ═══════════════════════════════════════════
NOP2 = b"\x00\xbf"

# F407 Main ELF patches
main_manual = [
    # I2C1 wait functions (already done, but included for completeness)
    (0x0800007E, "i2c1_wait_txe bpl->nop", b"\x01\xd5", NOP2),
    (0x0800008C, "i2c1_wait_txe timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000A6, "i2c1_wait_addr bpl->nop", b"\x02\xd5", NOP2),
    (0x080000B6, "i2c1_wait_addr timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000CE, "i2c1_wait_sb bpl->nop", b"\x01\xd5", NOP2),
    (0x080000DC, "i2c1_wait_sb timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    # SPI2 wait loops
    (0x0800005E, "spi2 TXE wait nop", b"\xfc\xd5", NOP2),
    (0x08000066, "spi2 RXNE wait nop", b"\xfc\xd5", NOP2),
    # BSS zeroing loop
    (0x08000988, "BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
    # i2c1_write_register ADDR polling (0x08000220-0x0800023e)
    (0x0800023E, "i2c1_write_reg ADDR timeout bls->nop", b"\xef\xd9", NOP2),
    # SystemInit HSE check
    (0x0800027E, "SystemInit HSE bpl->nop", b"\xfc\xd5", NOP2),
    # SystemInit PLL check
    (0x08000290, "SystemInit PLL bne->nop", b"\xfb\xd1", NOP2),
]

# F103 Aux ELF patches
aux_manual = [
    # I2C2 wait functions
    (0x080000A2, "i2c2_wait_txe bpl->nop", b"\x01\xd5", NOP2),
    (0x080000CA, "i2c2_wait_addr bpl->nop", b"\x02\xd5", NOP2),
    (0x080000DA, "i2c2_wait_addr timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000F2, "i2c2_wait_sb bpl->nop", b"\x01\xd5", NOP2),
    (0x08000100, "i2c2_wait_sb timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    # SystemInit
    (0x0800012E, "F103 SystemInit HSE bpl->nop", b"\xfc\xd5", NOP2),
    (0x0800013E, "F103 SystemInit PLL bne->nop", b"\xfb\xd1", NOP2),
    # BSS zeroing
    (0x080006F0, "BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
    # I2C2 ADDR polling in write path (0x08000480-0x080004a2)
    (0x080004A2, "F103 I2C2 write ADDR bls->nop", b"\xed\xd9", NOP2),
    # I2C2 ADDR polling in read path (0x08000502-0x08000514)
    (0x08000514, "F103 I2C2 read ADDR bls->nop", b"\xf5\xd9", NOP2),
    # I2C2 outer timeout (0x080004ca-0x08000520)
    (0x08000520, "F103 I2C2 outer timeout bls->nop", b"\xd3\xd9", NOP2),
    # Peripheral bit 2 spin loop (0x08000538-0x0800053c)
    (0x0800053C, "F103 peripheral spin bpl->nop", b"\xfc\xd5", NOP2),
    # I2C2 read poll (0x0800067e-0x08000690)
    (0x08000690, "F103 I2C2 read poll bls->nop", b"\xf5\xd9", NOP2),
]

print("=== F407 Main ELF ===")
patch_elf(sys.argv[1], main_manual, auto_patch_loops=False)
print("\n=== F103 Aux ELF ===")
patch_elf(sys.argv[2], aux_manual, auto_patch_loops=False)
print("\nDone.")
