#!/usr/bin/env python3
"""Definitive BSS read/write test for HIL bridge."""

import re
import socket
import sys
import time

HOST, PORT = "127.0.0.1", 3333


def start_renode():
    """Start Renode with HIL rescue script."""
    import subprocess

    resc = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/simulation/renode/hil_startup.resc"
    proc = subprocess.Popen(
        ["renode", "--port", "3333", "--disable-xwt", "-e", f"i @{resc}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Renode PID={proc.pid}, waiting for port...")
    for i in range(30):
        try:
            s = socket.create_connection((HOST, PORT), timeout=1)
            s.close()
            print(f"Port ready after {i + 1}s")
            return proc
        except Exception:
            time.sleep(1)
    print("ERROR: Renode didn't start")
    proc.kill()
    sys.exit(1)


def handle_telnet(sock):
    """Respond WONT to any DO negotiation."""
    time.sleep(0.5)
    sock.settimeout(0.5)
    try:
        data = sock.recv(1024)
        for chunk in data.split(b"\xff"):
            if len(chunk) >= 2 and chunk[0] == 0xFD:  # DO
                sock.sendall(b"\xff\xfc" + chunk[1:2])
            elif len(chunk) >= 2 and chunk[0] == 0xFB:  # WILL
                sock.sendall(b"\xff\xfe" + chunk[1:2])
        return data
    except TimeoutError:
        return b""


def send_cmd(sock, cmd_str):
    """Send command, read all chunks, return stripped response."""
    sock.sendall((cmd_str + "\n").encode())
    buf = b""
    sock.settimeout(2.0)
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            # Check for prompt pattern (raw bytes with ANSI)
            if b"(F103" in chunk or b"(F407" in chunk or b"(monitor" in chunk:
                break
    except TimeoutError:
        pass
    # Strip ANSI
    clean = re.sub(rb"\x1b\[[0-9;]*m", b"", buf)
    return clean.decode(errors="replace")


def main():
    # Kill old renode
    import subprocess

    subprocess.run(["pkill", "-f", "renode.*hil_startup"], capture_output=True)
    time.sleep(1)

    proc = start_renode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    handle_telnet(sock)
    sock.settimeout(3.0)

    print("\n=== Test: Write then read BSS on F407 ===")
    # Stay on monitor first
    send_cmd(sock, 'mach set "F407"')

    # Write test values
    send_cmd(sock, "sysbus WriteDoubleWord 0x2000001C 0x2A")
    send_cmd(sock, "sysbus WriteDoubleWord 0x20000010 0x1CE8")

    # Read back
    r1 = send_cmd(sock, "sysbus ReadDoubleWord 0x2000001C")
    r2 = send_cmd(sock, "sysbus ReadDoubleWord 0x20000010")
    print(f"frame_count (0x2000001C): {r1.strip()}")
    print(f"battery_mv  (0x20000010): {r2.strip()}")

    print("\n=== Test: F103 BSS ===")
    send_cmd(sock, 'mach set "F103"')

    send_cmd(sock, "sysbus WriteDoubleWord 0x2000000A 0x1CE8")
    send_cmd(sock, "sysbus WriteDoubleWord 0x2000001C 0x01")

    r3 = send_cmd(sock, "sysbus ReadDoubleWord 0x2000000A")
    r4 = send_cmd(sock, "sysbus ReadDoubleWord 0x2000001C")
    print(f"battery_mv  (0x2000000A): {r3.strip()}")
    print(f"estop_lock  (0x2000001C): {r4.strip()}")

    print("\n=== Test: Free RAM (known good) ===")
    send_cmd(sock, 'mach set "F407"')
    send_cmd(sock, "sysbus WriteDoubleWord 0x20005000 0xCAFEBABE")
    r5 = send_cmd(sock, "sysbus ReadDoubleWord 0x20005000")
    print(f"free_ram     (0x20005000): {r5.strip()}")

    sock.close()

    print("\n=== Parsing results ===")
    for label, resp in [
        ("F407 frame_count", r1),
        ("F407 battery", r2),
        ("F103 battery", r3),
        ("F103 estop", r4),
        ("Free RAM", r5),
    ]:
        lines = resp.strip().split("\n")
        vals = [line.strip() for line in lines if line.strip().startswith("0x")]
        if vals:
            print(f"  {label}: value={vals[0]}")
        else:
            print(f"  {label}: NO VALUE FOUND (lines: {lines})")

    proc.kill()
    proc.wait()


if __name__ == "__main__":
    main()
