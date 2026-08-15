#!/usr/bin/env python3
"""Inline patcher - works from CWD"""

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
            print(f"  FAIL no offset: {desc}")
            continue
        cur = bytes(data[fo : fo + len(old)])
        if cur == new:
            print(f"  SKIP (already): {desc}")
        elif cur == old:
            data[fo : fo + len(new)] = new
            print(f"  OK: {desc}")
        else:
            print(f"  MISMATCH: {desc} exp={old.hex()} got={cur.hex()}")
    with open(elf, "wb") as f:
        f.write(data)


main_patches = [
    (0x0800007E, "i2c1_wait_txe bpl->nop", b"\x01\xd5", b"\x00\xbf"),
    (0x0800008C, "i2c1_wait_txe timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000A6, "i2c1_wait_addr bpl->nop", b"\x02\xd5", b"\x00\xbf"),
    (0x080000B6, "i2c1_wait_addr timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000CE, "i2c1_wait_sb bpl->nop", b"\x01\xd5", b"\x00\xbf"),
    (0x080000DC, "i2c1_wait_sb timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x0800005E, "spi2 TXE wait nop", b"\xfc\xd5", b"\x00\xbf"),
    (0x08000066, "spi2 RXNE wait nop", b"\xfc\xd5", b"\x00\xbf"),
    (0x08000988, "BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
]
aux_patches = [
    (0x080006F0, "F103 BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
]

print("=== Main ELF ===")
patch(sys.argv[1], main_patches)
print("=== Aux ELF ===")
patch(sys.argv[2], aux_patches)
print("Done")
