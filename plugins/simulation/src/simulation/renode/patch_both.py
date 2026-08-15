#!/usr/bin/env python3
"""Patch both F407 main and F103 aux ELFs for Renode simulation."""

import struct
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


def patch(elf, patches):
    with open(elf, "rb") as f:
        data = bytearray(f.read())
    for addr, desc, old, new in patches:
        fo = find_fo(data, addr)
        if fo is None:
            print(f"  FAIL: {desc} (no file offset)")
            continue
        cur = bytes(data[fo : fo + len(old)])
        if cur == new:
            print(f"  SKIP: {desc}")
        elif cur == old:
            data[fo : fo + len(new)] = new
            print(f"  OK:   {desc}")
        else:
            print(f"  MISMATCH: {desc} exp={old.hex()} got={cur.hex()}")
    with open(elf, "wb") as f:
        f.write(data)


# ═══════════════════════════════════
# F407 Main ELF Patches
# ═══════════════════════════════════
main_patches = [
    # I2C1 wait loops (bpl.n -> nop, timeout -1 -> 0)
    (0x0800007E, "F407 i2c1_wait_txe bpl->nop", b"\x01\xd5", b"\x00\xbf"),
    (0x0800008C, "F407 i2c1_wait_txe timeout 0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000A6, "F407 i2c1_wait_addr bpl->nop", b"\x02\xd5", b"\x00\xbf"),
    (0x080000B6, "F407 i2c1_wait_addr timeout 0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000CE, "F407 i2c1_wait_sb bpl->nop", b"\x01\xd5", b"\x00\xbf"),
    (0x080000DC, "F407 i2c1_wait_sb timeout 0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    # SPI2 wait loops
    (0x0800005E, "F407 spi2 TXE wait nop", b"\xfc\xd5", b"\x00\xbf"),
    (0x08000066, "F407 spi2 RXNE wait nop", b"\xfc\xd5", b"\x00\xbf"),
    # BSS zeroing loop
    (0x08000988, "F407 BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
]

# ═══════════════════════════════════
# F103 Aux ELF Patches
# ═══════════════════════════════════
# I2C2 base: 0x40005800
# I2C2 wait functions use bpl.n + mov.w timeout -1 pattern
aux_patches = [
    # I2C2 wait_txe: bpl.n 0xd501 at 0x080000a2 -> nop
    (0x080000A2, "F103 i2c2_wait_txe bpl->nop", b"\x01\xd5", b"\x00\xbf"),
    # I2C2 wait_addr: bpl.n 0xd502 at 0x080000ca -> nop
    (0x080000CA, "F103 i2c2_wait_addr bpl->nop", b"\x02\xd5", b"\x00\xbf"),
    # I2C2 wait_addr: timeout -1->0 at 0x080000da
    (0x080000DA, "F103 i2c2_wait_addr timeout 0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    # I2C2 wait_sb: bpl.n 0xd501 at 0x080000f2 -> nop
    (0x080000F2, "F103 i2c2_wait_sb bpl->nop", b"\x01\xd5", b"\x00\xbf"),
    # I2C2 wait_sb: timeout -1->0 at 0x08000100
    (0x08000100, "F103 i2c2_wait_sb timeout 0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    # SystemInit: HSE ready check bpl.n at 0x0800012e -> nop
    (0x0800012E, "F103 SystemInit HSE bpl->nop", b"\xfc\xd5", b"\x00\xbf"),
    # SystemInit: PLL ready check bne.n at 0x0800013e -> nop
    (0x0800013E, "F103 SystemInit PLL bne->nop", b"\xfb\xd1", b"\x00\xbf"),
    # BSS zeroing loop
    (0x080006F0, "F103 BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
]

print("=== F407 Main ELF ===")
patch(sys.argv[1], main_patches)
print("=== F103 Aux ELF ===")
patch(sys.argv[2], aux_patches)
print("\nDone patching both ELFs.")
