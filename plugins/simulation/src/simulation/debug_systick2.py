#!/usr/bin/env python3
"""Load both MCUs, check SysTick, then test if firmware runs."""

import re as re_mod
import socket
import subprocess
import time

# Kill old
subprocess.run("pkill -f renode", shell=True, capture_output=True)
time.sleep(1)

# Start Renode
RESC = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/simulation/renode/debug_nostart.resc"
proc = subprocess.Popen(
    ["renode", "--port", "3333", "--disable-xwt", "-e", f"i @{RESC}"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(f"Renode PID={proc.pid}")

# Wait for port
for i in range(30):
    try:
        s = socket.create_connection(("127.0.0.1", 3333), timeout=1)
        s.close()
        print(f"Port ready after {i + 1}s")
        break
    except Exception:
        time.sleep(1)

# Connect
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5.0)
sock.connect(("127.0.0.1", 3333))
time.sleep(0.5)
data = sock.recv(4096)
for chunk in data.split(b"\xff"):
    if len(chunk) >= 2 and chunk[0] == 0xFD:
        sock.sendall(b"\xff\xfc" + chunk[1:2])



def cmd(c):
    sock.sendall((c + "\n").encode())
    time.sleep(0.05)
    buf = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            if b"(monitor)" in chunk or b"(F103" in chunk or b"(F407" in chunk:
                break
    except TimeoutError:
        pass
    return re_mod.sub(rb"\x1b\[[0-9;]*m", b"", buf).decode(errors="replace")


def parse_hex(resp):
    for line in resp.split("\n"):
        line = line.strip()
        if line.startswith("0x"):
            try:
                return int(line, 16)
            except Exception:

                pass
    return None


# Check which machines exist
print("\n=== Machines ===")
r = cmd("mach")
print(r[:200])

# Read sys_tick_ms without starting CPU
SYS_TICK_ADDR = 0x20000004
print("\n=== Before CPU start ===")
cmd('mach set "F407"')
r = cmd(f"sysbus ReadDoubleWord {hex(SYS_TICK_ADDR)}")
t0 = parse_hex(r)
print(f"sys_tick_ms: {t0}")

r = cmd("sysbus ReadDoubleWord 0x2000001C")
fc0 = parse_hex(r)
print(f"frame_count: {fc0}")

# Start the CPU
print("\n=== Starting F407 ===")
cmd("start")
time.sleep(1.0)

r = cmd(f"sysbus ReadDoubleWord {hex(SYS_TICK_ADDR)}")
t1 = parse_hex(r)
print(f"sys_tick_ms after 1s: {t1}")
print(f"Delta: {(t1 or 0) - (t0 or 0)}")

r = cmd("sysbus ReadDoubleWord 0x2000001C")
fc1 = parse_hex(r)
print(f"frame_count after 1s: {fc1}")
print(f"frame_count delta: {(fc1 or 0) - (fc0 or 0)}")

# Read PC
r = cmd("cpu PC")
print(f"PC: {parse_hex(r)}")

# Also start F103
print("\n=== Starting F103 ===")
cmd('mach set "F103"')
cmd("start")
time.sleep(0.5)
r = cmd("cpu PC")
print(f"F103 PC: {parse_hex(r)}")

sock.close()
proc.kill()
