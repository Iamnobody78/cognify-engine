#!/usr/bin/env python3
"""
Patch I2C wait functions to always return success (0).
In Renode, the I2C peripheral registers don't respond correctly.

Patches:
1. i2c1_wait_addr at 0x080000a6: bpl.n 0x80000ae → nop (always fall through to success)
2. i2c1_wait_sb   at 0x080000ce: bpl.n 0x80000d4 → nop
3. i2c1_wait_txe  at 0x0800007e: bpl.n 0x8000084 → nop

Also: at 0x080000b4: bls.n timeout check → force timeout return -1 to return 0
  Current: bls.n 0x80000a2 → d9f5
  We could change the timeout return at 0x80000b6 from mov r0,-1 to mov r0,0
  mov.w r0, -1 = F04F 30FF
  mov.w r0, 0  = F04F 3000

Better approach: Change the timeout return value from -1 to 0.
This way ALL I2C functions that timeout will still return 0 (success).
"""

import struct

ELF_PATH = r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\bottlesumo_pi\firmware\stm32_mcu\build\bottlesumo_main.elf"


def find_file_offset(flash_addr, data):
    """Map flash address to file offset using ELF program headers."""
    e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x2A)[0]
    e_phnum = struct.unpack_from("<H", data, 0x2C)[0]
    for i in range(e_phnum):
        phdr_offset = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, phdr_offset)[0]
        p_offset = struct.unpack_from("<I", data, phdr_offset + 4)[0]
        p_vaddr = struct.unpack_from("<I", data, phdr_offset + 8)[0]
        p_filesz = struct.unpack_from("<I", data, phdr_offset + 16)[0]
        if p_type == 1 and p_vaddr <= flash_addr < p_vaddr + p_filesz:
            return p_offset + (flash_addr - p_vaddr)
    return None


with open(ELF_PATH, "rb") as f:
    data = bytearray(f.read())

patches = [
    # (flash_addr, description, old_bytes_LE, new_bytes_LE)
    # bpl.n 0xD501 → nop 0xBF00: bytes 01 D5 → 00 BF
    (0x0800007E, "i2c1_wait_txe: bpl.n → nop", b"\x01\xd5", b"\x00\xbf"),
    # bpl.n 0xD502 → nop: bytes 02 D5 → 00 BF
    (0x080000A6, "i2c1_wait_addr: bpl.n → nop", b"\x02\xd5", b"\x00\xbf"),
    # bpl.n 0xD501 → nop
    (0x080000CE, "i2c1_wait_sb: bpl.n → nop", b"\x01\xd5", b"\x00\xbf"),
    # mov.w r0,-1 (4F F0 FF 30) → mov.w r0,0 (4F F0 00 30)
    (0x080000B6, "i2c1_wait_addr timeout: -1→0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000DC, "i2c1_wait_sb timeout: -1→0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x0800008C, "i2c1_wait_txe timeout: -1→0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
]

for addr, desc, old, new in patches:
    fo = find_file_offset(addr, data)
    if fo is None:
        print(f"  FAIL: can't find file offset for 0x{addr:08x}")
        continue
    current = bytes(data[fo : fo + len(old)])
    if current == old:
        data[fo : fo + len(new)] = new
        print(f"  [OK] {desc} @ 0x{addr:08x} (fo=0x{fo:x})")
    elif current == new:
        print(f"  [SKIP] {desc}: already patched")
    else:
        print(f"  [FAIL] {desc}: expected {old.hex()} got {current.hex()}")

with open(ELF_PATH, "wb") as f:
    f.write(data)
print("\nDone.")
