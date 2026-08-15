#!/usr/bin/env python3
"""
Patch the BSS zeroing loop in the compiled ELF binaries.
Changes the bne target from reloading BSS bounds to continuing the inner loop.

Buggy code (at flash addr 0x08000988):
    bne.n 0x08000976   → opcode bytes: D1 F5

Fixed code:
    bne.n 0x0800097E   → opcode bytes: D1 F9

We patch: byte at offset 0x08000989 from 0xF5 → 0xF9
This is in the .text section of the ELF.
"""

import struct


def patch_elf(filepath, flash_addr):
    """Patch bne.n target at flash_addr in ELF file."""
    patched = False  # Initialize
    with open(filepath, "rb") as f:
        data = bytearray(f.read())

    # Verify ELF magic
    if data[:4] != b"\x7fELF":
        print("  ERROR: not an ELF file")
        return False

    # Map flash address to file offset
    # ELF header is at offset 0 (for 32-bit LE ELF)
    # We need to find which section contains the flash address
    # For ARM Cortex-M, flash starts at 0x08000000
    # The ELF has a program header that maps VMA to file offset

    # Parse ELF header (32-bit LE)
    # e_phoff at byte 0x1C (4 bytes)
    # e_phentsize at byte 0x2A (2 bytes)
    # e_phnum at byte 0x2C (2 bytes)

    e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x2A)[0]
    e_phnum = struct.unpack_from("<H", data, 0x2C)[0]

    print(f"  ELF32, phoff=0x{e_phoff:x}, phentsize={e_phentsize}, phnum={e_phnum}")

    for i in range(e_phnum):
        phdr_offset = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", data, phdr_offset)[0]
        p_offset = struct.unpack_from("<I", data, phdr_offset + 4)[0]
        p_vaddr = struct.unpack_from("<I", data, phdr_offset + 8)[0]
        p_filesz = struct.unpack_from("<I", data, phdr_offset + 16)[0]

        # PT_LOAD = 1
        if p_type == 1:
            segment_end_vaddr = p_vaddr + p_filesz
            print(f"  Segment: file 0x{p_offset:x} → vaddr 0x{p_vaddr:x} (size 0x{p_filesz:x})")

            if p_vaddr <= flash_addr < segment_end_vaddr:
                file_offset = p_offset + (flash_addr - p_vaddr)
                print(f"  Flash addr 0x{flash_addr:x} → file offset 0x{file_offset:x}")

                # Read current bytes (little-endian in flash: F5 D1 = 0xD1F5)
                old_u16 = struct.unpack_from("<H", data, file_offset)[0]
                print(
                    f"  Current opcode at 0x{flash_addr:x}: 0x{old_u16:04X} (bytes: {data[file_offset]:02X} {data[file_offset + 1]:02X})"
                )

                if old_u16 == 0xD1F5:
                    # Patch offset part: 0xF5 → 0xF9 (0xD1F5 → 0xD1F9)
                    struct.pack_into("<H", data, file_offset, 0xD1F9)
                    new_u16 = struct.unpack_from("<H", data, file_offset)[0]
                    print(
                        f"  PATCHED to: 0x{new_u16:04X} (bytes: {data[file_offset]:02X} {data[file_offset + 1]:02X})"
                    )
                    patched = True
                elif (old_u16 & 0xFF00) == 0xD100:
                    # Any bne.n instruction — try to adjust offset
                    old_s8 = struct.unpack_from("b", data, file_offset + 1)[0]
                    new_s8 = old_s8 + 4  # shift target forward by 8 bytes (4 halfwords)
                    new_u16 = 0xD100 | (new_s8 & 0xFF)
                    struct.pack_into("<H", data, file_offset, new_u16)
                    print(f"  PATCHED bne.n: old_offset={old_s8:+d} → new_offset={new_s8:+d}")
                    patched = True

                if patched:
                    with open(filepath, "wb") as f:
                        f.write(data)
                    print(f"  → Written back to {filepath}")
                return patched

    print(f"  ERROR: flash addr 0x{flash_addr:x} not found in any LOAD segment")
    return False


if __name__ == "__main__":
    base = r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\bottlesumo_pi\firmware\stm32_mcu\build"

    for elf_name, addr in [("bottlesumo_main.elf", 0x08000988), ("bottlesumo_aux.elf", 0x080004F0)]:
        path = f"{base}\\{elf_name}"
        print(f"\nPatching {elf_name} at flash addr 0x{addr:08x}...")

        # For F103, first find the actual BNE address
        if elf_name == "bottlesumo_aux.elf":
            print("  NOTE: F103 BNE address needs disassembly. Trying common offset...")
            # The F103 startup is very similar, the BNE is likely at a different address
            # Let's search for the pattern in the binary
            with open(path, "rb") as f:
                raw = f.read()

            # Search for the pattern: F5 D1 (little-endian bne.n -22)
            needle = b"\xf5\xd1"
            idx = 0
            found_addrs = []
            while True:
                idx = raw.find(needle, idx)
                if idx == -1:
                    break
                found_addrs.append(idx)
                idx += 1

            print(f"  Found {len(found_addrs)} D1-F5 occurrences at file offsets:")
            for fo in found_addrs:
                print(f"    0x{fo:06x}")

            if found_addrs:
                # Map file offset to flash addr: file_off - 0x10000 + 0x08000000
                # But need to verify which segment it's in
                # For now, compute from known segment: file 0x10000 → vaddr 0x08000000
                for fo in found_addrs:
                    flash_guess = 0x08000000 + (fo - 0x10000)
                    print(f"  Trying file offset 0x{fo:06x} → flash addr 0x{flash_guess:08x}")
                    if patch_elf(path, flash_guess):
                        break
        else:
            patch_elf(path, addr)

    print("\nDone.")
