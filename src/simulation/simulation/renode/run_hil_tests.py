#!/usr/bin/env python3
"""
BottleSumo HIL Bridge — End-to-End Test Runner
================================================
Starts Renode daemon, loads dual-MCU firmware, runs phase tests.
Runs INSIDE WSL (uses /mnt/c/... paths for ELF files).
"""

import os
import socket
import subprocess
import time

# ══════════════════════════════════════════════════════════════════════
# Paths (WSL-style for use inside WSL)
# ══════════════════════════════════════════════════════════════════════
WIN_BASE = (
    "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704"
)
ELF_DIR = f"{WIN_BASE}/bottlesumo_pi/firmware/stm32_mcu/build"
F407_ELF = f"{ELF_DIR}/bottlesumo_main.elf"
F103_ELF = f"{ELF_DIR}/bottlesumo_aux.elf"
HIL_BRIDGE = f"{WIN_BASE}/bottlesumo_pi/simulation/hil_bridge.py"

HOST = "127.0.0.1"
PORT = 3333

# ══════════════════════════════════════════════════════════════════════
# Phase 0: Start Renode daemon (bare, no .resc)
# ══════════════════════════════════════════════════════════════════════


def start_renode():
    """Start Renode daemon without any resc script. Returns Popen handle."""
    print(f"[DAEMON] Starting Renode on port {PORT}...")
    proc = subprocess.Popen(
        ["/usr/local/bin/renode", "--disable-xwt", f"--port={PORT}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for port to open
    for i in range(60):
        try:
            s = socket.create_connection((HOST, PORT), timeout=1)
            s.close()
            print(f"[DAEMON] Port ready after {i + 1}s, PID={proc.pid}")
            return proc
        except (TimeoutError, ConnectionRefusedError, OSError):
            time.sleep(1)
    proc.kill()
    raise RuntimeError("Renode daemon failed to start within 60s")


# ══════════════════════════════════════════════════════════════════════
# Phase 1: Load MCUs via monitor commands
# ══════════════════════════════════════════════════════════════════════


def load_firmware():
    """Connect to Renode, load both MCUs, start them."""
    print("[LOAD] Connecting to Renode monitor...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect((HOST, PORT))

    # Handle Telnet IAC negotiation
    time.sleep(0.3)
    sock.settimeout(0.5)
    try:
        data = sock.recv(4096)
        for chunk in data.split(b"\xff"):
            if len(chunk) >= 2:
                if chunk[0] == 0xFD:  # DO
                    sock.sendall(b"\xff\xfc" + chunk[1:2])
                elif chunk[0] == 0xFB:  # WILL
                    sock.sendall(b"\xff\xfe" + chunk[1:2])
    except TimeoutError:
        pass

    def cmd(command, timeout=2.0):
        """Send command, return raw bytes."""
        sock.settimeout(5.0)
        sock.sendall((command + "\n").encode())
        time.sleep(0.1)
        buf = b""
        sock.settimeout(timeout)
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"(monitor)" in chunk or b"F407)" in chunk or b"F103)" in chunk:
                    break
        except TimeoutError:
            pass
        return buf.decode("utf-8", errors="replace")

    def phex(raw_str):
        """Extract hex value from response string."""
        for line in raw_str.split("\n"):
            line = line.strip()
            if line.startswith("0x") and len(line) < 16:
                try:
                    return int(line, 16)
                except ValueError:
                    pass
        return None

    # ── Create and load F407 ──
    print("[LOAD] Creating F407 machine...")
    r = cmd('mach add "F407"')
    print(f"  mach add F407: {r[:100].strip()}")

    r = cmd('mach set "F407"')
    print(f"  mach set F407: {r[:100].strip()}")

    r = cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
    print(f"  LoadPlatformDescription: {r[:100].strip()}")

    r = cmd(f"sysbus LoadELF @{F407_ELF}")
    print(f"  LoadELF main: {r[:100].strip()}")

    # Verify F407 PC
    r = cmd("cpu PC")
    pc = phex(r)
    print(f"  F407 PC (pre-start): {hex(pc) if pc else 'N/A'}")

    # ── Create and load F103 ──
    print("[LOAD] Creating F103 machine...")
    r = cmd('mach add "F103"')
    print(f"  mach add F103: {r[:100].strip()}")

    r = cmd('mach set "F103"')
    print(f"  mach set F103: {r[:100].strip()}")

    r = cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
    print(f"  LoadPlatformDescription: {r[:100].strip()}")

    r = cmd(f"sysbus LoadELF @{F103_ELF}")
    print(f"  LoadELF aux: {r[:100].strip()}")

    # Verify F103 PC
    r = cmd("cpu PC")
    pc = phex(r)
    print(f"  F103 PC (pre-start): {hex(pc) if pc else 'N/A'}")

    # ── Start both MCUs ──
    print("[LOAD] Starting F407...")
    cmd('mach set "F407"')
    cmd("start")
    time.sleep(0.3)
    r = cmd("cpu PC")
    pc = phex(r)
    print(f"  F407 PC (post-start): {hex(pc) if pc else 'N/A'}")

    print("[LOAD] Starting F103...")
    cmd('mach set "F103"')
    cmd("start")
    time.sleep(0.3)
    r = cmd("cpu PC")
    pc = phex(r)
    print(f"  F103 PC (post-start): {hex(pc) if pc else 'N/A'}")

    sock.close()
    print("[LOAD] Both MCUs loaded and started.")

    # Give firmware a moment to initialize
    time.sleep(1.0)
    return True


# ══════════════════════════════════════════════════════════════════════
# Phase 2: Quick pre-check (frame_count, sys_tick_ms)
# ══════════════════════════════════════════════════════════════════════


def pre_check():
    """Verify firmware is actually running (frame_count increments)."""
    print("\n[PRECHECK] Verifying firmware execution...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    sock.connect((HOST, PORT))
    time.sleep(0.3)
    sock.settimeout(0.5)
    try:
        data = sock.recv(4096)
        for chunk in data.split(b"\xff"):
            if len(chunk) >= 2:
                if chunk[0] == 0xFD:
                    sock.sendall(b"\xff\xfc" + chunk[1:2])
                elif chunk[0] == 0xFB:
                    sock.sendall(b"\xff\xfe" + chunk[1:2])
    except TimeoutError:
        pass

    def cmd(command):
        sock.settimeout(5.0)
        sock.sendall((command + "\n").encode())
        time.sleep(0.1)
        buf = b""
        sock.settimeout(2.0)
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"(monitor)" in chunk or b"F407)" in chunk or b"F103)" in chunk:
                    break
        except TimeoutError:
            pass
        return buf.decode("utf-8", errors="replace")

    def read_u32(mach, addr):
        cmd(f'mach set "{mach}"')
        resp = cmd(f"sysbus ReadDoubleWord {hex(addr)}")
        for line in resp.split("\n"):
            line = line.strip()
            if line.startswith("0x"):
                try:
                    return int(line, 16)
                except ValueError:
                    pass
        return None

    def read_pc(mach):
        cmd(f'mach set "{mach}"')
        resp = cmd("cpu PC")
        for line in resp.split("\n"):
            line = line.strip()
            if line.startswith("0x"):
                try:
                    return int(line, 16)
                except ValueError:
                    pass
        return None

    # Read frame_count at t0
    fc1 = read_u32("F407", 0x2000001C)
    sys_tick1 = read_u32("F407", 0x20000004)
    pc1 = read_pc("F407")
    print(f"  F407 frame_count @ t0:     {fc1}")
    print(f"  F407 sys_tick_ms @ t0:   {sys_tick1}")
    print(f"  F407 PC @ t0:             {hex(pc1) if pc1 else 'N/A'}")

    # Wait 1 second
    time.sleep(1.0)

    # Read frame_count at t1
    fc2 = read_u32("F407", 0x2000001C)
    sys_tick2 = read_u32("F407", 0x20000004)
    pc2 = read_pc("F407")
    print(f"  F407 frame_count @ t1:     {fc2}")
    print(f"  F407 sys_tick_ms @ t1:   {sys_tick2}")
    print(f"  F407 PC @ t1:             {hex(pc2) if pc2 else 'N/A'}")

    delta_fc = (fc2 or 0) - (fc1 or 0)
    delta_tick = (sys_tick2 or 0) - (sys_tick1 or 0)
    print(f"  frame_count delta:          {delta_fc} {'✓ RUNNING' if delta_fc > 0 else '✗ STUCK'}")
    print(
        f"  sys_tick_ms delta:        {delta_tick} {'✓ ADVANCING' if delta_tick > 0 else '✗ FROZEN'}"
    )

    sock.close()
    return delta_fc > 0


# ══════════════════════════════════════════════════════════════════════
# Phase 3: Run HIL Bridge tests
# ══════════════════════════════════════════════════════════════════════


def run_hil_bridge(test="framerate"):
    """Run the HIL bridge v2 against the running Renode."""
    print(f"\n[HIL] Running HIL bridge --test {test}...")
    result = subprocess.run(
        ["python3", HIL_BRIDGE, "--test", test, "--host", HOST, "--port", str(PORT)],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(HIL_BRIDGE),
    )
    print(result.stdout)
    if result.stderr:
        print(f"[HIL STDERR]:\n{result.stderr}")
    return result.returncode == 0


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════


def main():
    renode_proc = None
    try:
        renode_proc = start_renode()
        load_firmware()
        running = pre_check()

        if not running:
            print("\n⚠ FIRMWARE IS NOT RUNNING — frame_count didn't increment.")
            print("  Possible causes:")
            print("  1. BSS zeroing loop bug in Reset_Handler")
            print("  2. SysTick peripheral not emulated → HAL_Delay hangs")
            print("  3. Firmware stuck in estop check (no sensors = emergency)")
            print("\n  Attempting to diagnose...")

            # Quick diagnosis: check if PC is in an infinite loop
            import socket as sk

            s = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect((HOST, PORT))
            time.sleep(0.3)
            try:
                d = s.recv(4096)
                for chunk in d.split(b"\xff"):
                    if len(chunk) >= 2 and chunk[0] == 0xFD:
                        s.sendall(b"\xff\xfc" + chunk[1:2])
            except Exception:

                pass

            s.sendall(b'mach set "F407"\n')
            time.sleep(0.1)
            s.sendall(b"cpu PC\n")
            time.sleep(0.3)
            try:
                chunks = []
                while True:
                    c = s.recv(4096)
                    if not c:
                        break
                    chunks.append(c)
                    if b"(F407)" in c or b"(monitor)" in c:
                        break
            except Exception:

                pass
            raw = b"".join(chunks)
            print(f"  F407 PC raw: {raw}")

            # Read nearby instructions for context
            s.sendall(b"sysbus ReadDoubleWord 0x20000004\n")
            time.sleep(0.2)
            try:
                chunks = []
                while True:
                    c = s.recv(4096)
                    if not c:
                        break
                    chunks.append(c)
                    if b"(F407)" in c or b"(monitor)" in c:
                        break
            except Exception:

                pass
            raw = b"".join(chunks)
            print(f"  sys_tick_ms raw: {raw}")

            s.close()
        else:
            print("\n✓ Firmware is running. Proceeding to HIL bridge tests...")
            run_hil_bridge("framerate")

    finally:
        if renode_proc:
            print("\n[CLEANUP] Stopping Renode...")
            renode_proc.terminate()
            try:
                renode_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                renode_proc.kill()
            print("[CLEANUP] Done.")


if __name__ == "__main__":
    main()
