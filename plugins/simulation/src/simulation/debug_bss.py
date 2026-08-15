#!/usr/bin/env python3
"""Debug: verify Renode memory read/write at BSS addresses."""

import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(3.0)
sock.connect(("127.0.0.1", 3333))

# Handle telnet negotiation
time.sleep(0.3)
data = sock.recv(1024)
# Respond WONT to DO
for cmd in data.split(b"\xff"):
    if len(cmd) >= 2 and cmd[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + cmd[1:2])


def cmd(c):
    sock.sendall((c + "\n").encode())
    time.sleep(0.05)
    try:
        resp = sock.recv(4096)
        return resp.decode(errors="replace")
    except TimeoutError:
        return ""


# F103 memory verification
print("=== F103 BSS Memory Map ===")
cmd('mach set "F103"')
time.sleep(0.1)

# Read raw values at key BSS addresses
addrs = {
    "battery_mv": 0x2000000A,
    "enc_a_count": 0x2000000C,
    "estop_lock": 0x2000001C,
    "spi_frame_ready": 0x2000001D,
}

for name, addr in addrs.items():
    r = cmd(f"sysbus ReadDoubleWord {hex(addr)}")
    print(f"  {name} @ {hex(addr)}: {r.strip()}")

# Test write/read cycle
print("\n=== Write-Read Test ===")
cmd("sysbus WriteDoubleWord 0x2000001C 0xDEAD")  # estop_lock with test value
time.sleep(0.1)
r = cmd("sysbus ReadByte 0x2000001C")
print(f"  Write 0xDEAD → ReadByte 0x2000001C: {r.strip()}")
r = cmd("sysbus ReadDoubleWord 0x2000001C")
print(f"  Write 0xDEAD → ReadDWord 0x2000001C: {r.strip()}")

# Direct write known value
cmd("sysbus WriteDoubleWord 0x20000050 0x12345678")
r = cmd("sysbus ReadDoubleWord 0x20000050")
print(f"  Write 0x12345678 @ 0x20000050 → Read: {r.strip()}")

# Check F407
print("\n=== F407 BSS (key vars) ===")
cmd('mach set "F407"')
time.sleep(0.1)

addrs_f407 = {
    "frame_count": 0x2000001C,
    "enc_a_delta": 0x20000014,
    "battery_mv": 0x20000010,
}
for name, addr in addrs_f407.items():
    r = cmd(f"sysbus ReadDoubleWord {hex(addr)}")
    print(f"  {name} @ {hex(addr)}: {r.strip()}")

cmd("sysbus ReadDoubleWord 0x20000050")
print(
    f"  Test addr 0x20000050 (should be 0x12345678): {cmd('sysbus ReadDoubleWord 0x20000050').strip()}"
)

sock.close()
