"""Fix double-patch: restore main ELF byte to correct value."""

import struct

path = r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\bottlesumo_pi\firmware\stm32_mcu\build\bottlesumo_main.elf"

with open(path, "rb") as f:
    data = bytearray(f.read())

# Correct value: D1F9 (bne.n with -7 offset → target 0x0800097E)
struct.pack_into("<H", data, 0x10988, 0xD1F9)

with open(path, "wb") as f:
    f.write(data)

print(f"Restored: {data[0x10988]:02X} {data[0x10988 + 1]:02X} (should be F9 D1 = 0xD1F9)")
print("Done.")
