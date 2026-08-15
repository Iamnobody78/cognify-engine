#!/usr/bin/env python3
"""
BottleSumo Renode Simulation Firmware Patcher
============================================
Patches all blocking peripheral polling loops to work in Renode simulation
where hardware peripherals (I2C, SPI) are not fully modeled.

Patch List:
1. i2c1_wait_txe:   bpl.n → nop (skip TXE poll)
2. i2c1_wait_txe:   timeout return -1 → return 0
3. i2c1_wait_addr:  bpl.n → nop (skip ADDR poll)
4. i2c1_wait_addr:  timeout return -1 → return 0
5. i2c1_wait_sb:    bpl.n → nop (skip SB poll)
6. i2c1_wait_sb:    timeout return -1 → return 0
7. spi2_transfer:   bpl.n → nop (skip TXE poll)
8. spi2_transfer:   bpl.n → nop (skip RXNE poll)
9. BSS zeroing loop: bne → correct target (already done)
"""

import struct

ELF_MAIN = r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\bottlesumo_pi\firmware\stm32_mcu\build\bottlesumo_main.elf"
ELF_AUX = r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\bottlesumo_pi\firmware\stm32_mcu\build\bottlesumo_aux.elf"


def find_file_offset(flash_addr, data):
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


def apply_patches(elf_path, patches):
    with open(elf_path, "rb") as f:
        data = bytearray(f.read())

    results = []
    for addr, desc, old_le, new_le in patches:
        fo = find_file_offset(addr, data)
        if fo is None:
            results.append(f"FAIL: cant find offset for 0x{addr:08x} - {desc}")
            continue
        current = bytes(data[fo : fo + len(old_le)])
        if current == new_le:
            results.append(f"SKIP: already patched - {desc}")
        elif current == old_le:
            data[fo : fo + len(new_le)] = new_le
            results.append(f"OK: {desc}")
        else:
            results.append(f"MISMATCH: {desc} - expected {old_le.hex()} got {current.hex()}")

    with open(elf_path, "wb") as f:
        f.write(data)
    return results


# ════════════════════════════════════════════════════════════
# Main F407 patches
# ════════════════════════════════════════════════════════════
main_patches = [
    # I2C1 wait functions - make bpl.n (loop if bit not set) → nop
    # Format: (flash_addr, description, old_LE_bytes, new_LE_bytes)
    (0x0800007E, "i2c1_wait_txe bpl.n->nop", b"\x01\xd5", b"\x00\xbf"),
    (0x0800008C, "i2c1_wait_txe timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000A6, "i2c1_wait_addr bpl.n->nop", b"\x02\xd5", b"\x00\xbf"),
    (0x080000B6, "i2c1_wait_addr timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    (0x080000CE, "i2c1_wait_sb bpl.n->nop", b"\x01\xd5", b"\x00\xbf"),
    (0x080000DC, "i2c1_wait_sb timeout -1->0", b"\x4f\xf0\xff\x30", b"\x4f\xf0\x00\x30"),
    # SPI2 transfer - infinite polling loops
    # spi2_transfer_byte: bpl.n 0x800005a → nop (wait TXE)
    (0x0800005E, "spi2 wait TXE bpl.n->nop", b"\xfc\xd5", b"\x00\xbf"),
    # spi2_transfer_byte: bpl.n 0x8000062 → nop (wait RXNE)
    (0x08000066, "spi2 wait RXNE bpl.n->nop", b"\xfc\xd5", b"\x00\xbf"),
    # BSS zeroing loop fix
    (0x08000988, "BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
]

# ════════════════════════════════════════════════════════════
# Aux F103 patches
# ════════════════════════════════════════════════════════════
aux_patches = [
    # BSS zeroing loop fix (F103)
    (0x080006F0, "F103 BSS loop bne fix", b"\xf5\xd1", b"\xf9\xd1"),
]

print("=== Patch Main ELF (F407) ===")
for r in apply_patches(ELF_MAIN, main_patches):
    print(f"  {r}")

print("\n=== Patch Aux ELF (F103) ===")
for r in apply_patches(ELF_AUX, aux_patches):
    print(f"  {r}")

print("\nDone.")
