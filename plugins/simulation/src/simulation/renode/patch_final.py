#!/usr/bin/env python3
"""Final targeted patches for remaining I2C polling loops."""

import struct
import sys


def find_fo(data, flash_addr):
    e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x2A)[0]
    e_phnum = struct.unpack_from("<H", data, 0x2C)[0]
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, off)[0]
        if p_type == 1:
            p_offset = struct.unpack_from("<I", data, off + 4)[0]
            p_vaddr = struct.unpack_from("<I", data, off + 8)[0]
            p_filesz = struct.unpack_from("<I", data, off + 16)[0]
            if p_vaddr <= flash_addr < p_vaddr + p_filesz:
                return p_offset + (flash_addr - p_vaddr)
    return None


main_patches = [
    # RXNE check in i2c1_read_data
    (0x0800014E, "i2c1_read RXNE bpl->nop", b"\x24\xd5", b"\x00\xbf"),
    # RXNE timeout in i2c1_read_data
    (0x080001A2, "i2c1_read RXNE timeout bls->nop", b"\xd2\xd9", b"\x00\xbf"),
    # BTF check in i2c1_read_data (during read sequence)
    (0x08000180, "i2c1_read BTF bpl->nop", b"\x19\xd5", b"\x00\xbf"),
    # BTF timeout (after read sequence)
    (0x080001BE, "i2c1_read BTF timeout bls->nop", b"\xdd\xd9", b"\x00\xbf"),
]

elf = sys.argv[1]
with open(elf, "rb") as f:
    data = bytearray(f.read())

for addr, desc, old, new in main_patches:
    fo = find_fo(data, addr)
    if fo is None:
        print(f"FAIL: {desc}")
        continue
    cur = bytes(data[fo : fo + 2])
    if cur == old:
        data[fo : fo + 2] = new
        print(f"OK:   {desc}")
    elif cur == new:
        print(f"SKIP: {desc}")
    else:
        print(f"MISMATCH: {desc} exp={old.hex()} got={cur.hex()}")

with open(elf, "wb") as f:
    f.write(data)
print("Done")
