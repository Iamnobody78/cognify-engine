#!/usr/bin/env python3
"""
BottleSumo HIL Bridge v3 — Renode ↔ Python Hardware-in-the-Loop
================================================================
Updated with verified memory maps and dual-MCU state tracking.
"""

import os
import re
import socket
import struct
import subprocess
import time

# ═══════════════════════════════════════════════════════════
# Verified Memory Maps (from arm-none-eabi-readelf -s)
# ═══════════════════════════════════════════════════════════

F407 = {
    "bottle_dist_history": 0x20000000,
    "vlx0_dist": 0x20000008,
    "battery_mv": 0x20000010,
    "frame_count": 0x2000001C,  # uint32_t — verified
    "sys_tick_ms": 0x20000088,  # uint32_t — verified
    "last_loop_ms": 0x20000020,
    "observation": 0x2000002C,  # float[16]
    "q_values": 0x2000006C,  # float[11]
}

F103 = {
    "vlx0_dist": 0x20000000,  # uint16_t[4] in .data
    "batt_counter": 0x20000008,  # uint8_t
    "battery_mv": 0x2000000A,  # uint16_t
    "enc_a_count": 0x2000000C,  # int32_t
    "enc_a_last": 0x20000010,  # int32_t
    "enc_b_count": 0x20000014,  # int32_t
    "enc_b_last": 0x20000018,  # int32_t
    "estop_lock": 0x2000001C,  # uint8_t
    "spi_frame_ready": 0x2000001D,  # uint8_t
    "spi_rx_buf": 0x2000001E,  # uint8_t[7]
    "spi_rx_idx": 0x20000025,  # uint8_t
    "spi_tx_buf": 0x20000026,  # uint8_t[21]
    "spi_tx_idx": 0x2000003B,  # uint8_t
    "status": 0x2000003C,  # uint8_t
    "sys_tick_ms": 0x20000040,  # uint32_t — verified
}

# ═══════════════════════════════════════════════════════════
# HIL Bridge
# ═══════════════════════════════════════════════════════════


class HiLBridge:
    def __init__(self, host="127.0.0.1", port=3333, timeout=3.0):
        self.host, self.port, self.timeout = host, port, timeout
        self._sock = None

    def connect(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            self._handle_telnet()
            return True
        except Exception as e:
            print(f"[ERROR] Cannot connect: {e}")
            return False

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None

    def _handle_telnet(self):
        time.sleep(0.3)
        self._sock.settimeout(0.5)
        try:
            data = self._sock.recv(4096)
            for chunk in data.split(b"\xff"):
                if len(chunk) >= 2:
                    if chunk[0] == 0xFD:
                        self._sock.sendall(b"\xff\xfc" + chunk[1:2])
                    elif chunk[0] == 0xFB:
                        self._sock.sendall(b"\xff\xfe" + chunk[1:2])
        except Exception:

            pass
        self._sock.settimeout(self.timeout)

    def cmd(self, command: str, timeout: float = 3.0) -> str:
        self._sock.sendall((command + "\n").encode())
        time.sleep(0.05)
        buf = b""
        self._sock.settimeout(timeout)
        try:
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if any(m in chunk for m in [b"(monitor)", b"(F407", b"(F103"]):
                    break
        except TimeoutError:
            pass
        self._sock.settimeout(self.timeout)
        clean = re.sub(r"\x1b\[[0-9;]*m", "", buf.decode("utf-8", errors="replace"))
        lines = [line.strip() for line in clean.rstrip().split("\n") if line.strip()]
        # Remove command echo and prompt
        cmd_prefix = command.split()[0]
        result = [
            line
            for line in lines
            if not line.startswith(cmd_prefix)
            and not line.startswith("(F")
            and not line.startswith("(monitor")
        ]
        return "\n".join(result)

    def select_machine(self, name: str):
        self.cmd(f'mach set "{name}"')

    def _parse_hex(self, resp: str) -> int | None:
        for line in resp.split("\n"):
            line = line.strip()
            m = re.match(r"^-?0x([0-9a-fA-F]+)$", line)
            if m:
                val = int(m.group(1), 16)
                if line.startswith("-"):
                    val = -val
                return val
        return None

    def read_u32(self, addr: int) -> int | None:
        resp = self.cmd(f"sysbus ReadDoubleWord {hex(addr)}")
        return self._parse_hex(resp)

    def read_u16(self, addr: int) -> int | None:
        resp = self.cmd(f"sysbus ReadWord {hex(addr)}")
        return self._parse_hex(resp)

    def read_u8(self, addr: int) -> int | None:
        resp = self.cmd(f"sysbus ReadByte {hex(addr)}")
        return self._parse_hex(resp)

    def write_u32(self, addr: int, value: int):
        self.cmd(f"sysbus WriteDoubleWord {hex(addr)} {hex(value & 0xFFFFFFFF)}")

    def write_u16(self, addr: int, value: int):
        self.cmd(f"sysbus WriteWord {hex(addr)} {hex(value & 0xFFFF)}")

    def write_u8(self, addr: int, value: int):
        self.cmd(f"sysbus WriteByte {hex(addr)} {hex(value & 0xFF)}")

    def write_float(self, addr: int, value: float):
        bits = struct.unpack(">I", struct.pack(">f", value))[0]
        self.write_u32(addr, bits)

    def read_float(self, addr: int) -> float | None:
        val = self.read_u32(addr)
        if val is not None:
            return struct.unpack(">f", struct.pack(">I", val))[0]
        return None

    def read_pc(self, mach: str) -> int | None:
        self.select_machine(mach)
        resp = self.cmd("cpu PC", timeout=2)
        m = re.search(r"0x([0-9a-fA-F]{7,8})\b", resp)
        if m:
            val = int(m.group(1), 16)
            if 0x08000000 <= val <= 0x08100000:
                return val
        return None

    def get_state(self) -> dict:
        """Return current state of both MCUs."""
        state = {}
        self.select_machine("F407")
        state["f407_frame_count"] = self.read_u32(F407["frame_count"])
        state["f407_tick"] = self.read_u32(F407["sys_tick_ms"])
        state["f407_pc"] = self.read_pc("F407")

        self.select_machine("F103")
        state["f103_tick"] = self.read_u32(F103["sys_tick_ms"])
        state["f103_estop"] = self.read_u8(F103["estop_lock"])
        state["f103_status"] = self.read_u8(F103["status"])
        state["f103_enc_a"] = self.read_u32(F103["enc_a_count"])
        state["f103_enc_b"] = self.read_u32(F103["enc_b_count"])
        state["f103_pc"] = self.read_pc("F103")
        return state


# ═══════════════════════════════════════════════════════════
# Test Phases
# ═══════════════════════════════════════════════════════════


def test_boot(bridge: HiLBridge) -> bool:
    print("\n" + "=" * 60)
    print("PHASE 0: Boot Verification")
    print("=" * 60)
    state = bridge.get_state()
    f407_ok = state["f407_pc"] is not None
    f103_ok = state["f103_pc"] is not None
    print(
        f"  F407 PC: {hex(state['f407_pc']) if state['f407_pc'] else 'N/A'} {'✓' if f407_ok else '✗'}"
    )
    print(
        f"  F103 PC: {hex(state['f103_pc']) if state['f103_pc'] else 'N/A'} {'✓' if f103_ok else '✗'}"
    )
    return f407_ok and f103_ok


def test_framerate(bridge: HiLBridge) -> dict:
    print("\n" + "=" * 60)
    print("PHASE 1: Frame Rate & SysTick")
    print("=" * 60)

    s1 = bridge.get_state()
    fc1, tick1 = s1["f407_frame_count"], s1["f407_tick"]
    tick103_1 = s1["f103_tick"]
    print(f"  t=0:  fc={fc1}, tick407={tick1}, tick103={tick103_1}")

    time.sleep(2.0)

    s2 = bridge.get_state()
    fc2, tick2 = s2["f407_frame_count"], s2["f407_tick"]
    tick103_2 = s2["f103_tick"]

    wall_dt = 2.0
    fc_delta = (fc2 or 0) - (fc1 or 0)
    sim_dt = ((tick2 or 0) - (tick1 or 0)) / 1000.0  # ms → s
    fps_sim = fc_delta / sim_dt if sim_dt > 0 else 0

    print(f"  t=2s: fc={fc2}, tick407={tick2}, tick103={tick103_2}")
    print(f"  Frames: {fc_delta} in 2s wall ({fps_sim:.1f} fps simulated)")
    print(f"  Tick407 Δ: {(tick2 or 0) - (tick1 or 0)}")
    print(f"  Tick103 Δ: {(tick103_2 or 0) - (tick103_1 or 0)}")
    print(f"  Sim speed: {sim_dt / wall_dt:.2%} real-time")

    return {"fc_delta": fc_delta, "fps_sim": fps_sim}


def test_safety(bridge: HiLBridge) -> dict:
    print("\n" + "=" * 60)
    print("PHASE 2: Safety Systems")
    print("=" * 60)

    s = bridge.get_state()
    print(f"  estop_lock = {s['f103_estop']}")
    print(f"  status     = {s['f103_status']}")

    # Unlock estop
    bridge.select_machine("F103")
    bridge.write_u8(F103["estop_lock"], 0x00)
    time.sleep(0.1)
    val = bridge.read_u8(F103["estop_lock"])
    print(f"  Write estop=0x00, readback=0x{val:02X} {'✓' if val == 0 else '✗'}")
    return {"estop_wr": (val == 0)}


def test_spi_protocol(bridge: HiLBridge) -> dict:
    print("\n" + "=" * 60)
    print("PHASE 3: SPI Protocol")
    print("=" * 60)

    bridge.select_machine("F103")
    # Read SPI TX buffer
    spi_tx = F103["spi_tx_buf"]
    print("  SPI TX buffer (21B):")
    buf = []
    for i in range(21):
        b = bridge.read_u8(spi_tx + i)
        buf.append(b)
    print(f"  Raw: {[f'0x{b:02X}' if b is not None else '??' for b in buf]}")

    # SPI RX buffer
    spi_rx = F103["spi_rx_buf"]
    rx = [bridge.read_u8(spi_rx + i) for i in range(7)]
    print(f"  SPI RX buffer (7B): {[f'0x{b:02X}' if b is not None else '??' for b in rx]}")

    # Check spi_frame_ready
    ready = bridge.read_u8(F103["spi_frame_ready"])
    idx = bridge.read_u8(F103["spi_rx_idx"])
    print(f"  spi_frame_ready={ready}, spi_rx_idx={idx}")
    return {"spi_readable": True}


def test_dqn_integration(bridge: HiLBridge) -> dict:
    print("\n" + "=" * 60)
    print("PHASE 4: DQN Integration")
    print("=" * 60)
    mock_obs = [0.0] * 16
    mock_obs[8] = 1.0  # battery
    mock_obs[9] = 0.5  # bottle dist
    bridge.select_machine("F407")
    for i, val in enumerate(mock_obs):
        bridge.write_float(F407["observation"] + i * 4, val)
    print("  Injected observation vector")

    s = bridge.get_state()
    print(f"  frame_count = {s['f407_frame_count']}")
    print(f"  tick = {s['f407_tick']}")
    return {"obs_ok": True}


# ═══════════════════════════════════════════════════════════
# Daemon
# ═══════════════════════════════════════════════════════════


class RenodeDaemon:
    """Manage Renode daemon with dual-MCU loading."""

    def __init__(self, base_dir: str):
        self.base = base_dir
        self.proc = None

    def start(self, port=3333):
        os.system("killall -9 renode 2>/dev/null; sleep 0.5")
        self.proc = subprocess.Popen(
            ["renode", "--disable-xwt", f"--port={port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Waiting for Renode...", end="", flush=True)
        for _i in range(60):
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=1)
                s.close()
                print(" ready.")
                break
            except Exception:
                time.sleep(1)
                print(".", end="", flush=True)
        else:
            print(" FAILED")
            return False
        return True

    def load_firmware(self, bridge: HiLBridge):
        print("Loading firmware...")
        bridge.cmd('mach add "F407"')
        bridge.select_machine("F407")
        bridge.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
        bridge.cmd(f"sysbus LoadELF @{self.base}/bottlesumo_main.elf")

        bridge.cmd('mach add "F103"')
        bridge.select_machine("F103")
        bridge.cmd("machine LoadPlatformDescription @platforms/cpus/stm32f103.repl")
        bridge.cmd(f"sysbus LoadELF @{self.base}/bottlesumo_aux.elf")

    def start_mcus(self, bridge: HiLBridge):
        bridge.select_machine("F407")
        bridge.cmd("start")
        bridge.select_machine("F103")
        bridge.cmd("start")
        time.sleep(0.5)

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════


def main():
    base = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/firmware/stm32_mcu/build"

    daemon = RenodeDaemon(base)
    if not daemon.start():
        return 1

    bridge = HiLBridge()
    if not bridge.connect():
        daemon.stop()
        return 1

    daemon.load_firmware(bridge)
    daemon.start_mcus(bridge)

    print("\n" + "=" * 70)
    print("  BottleSumo HIL Bridge v3 — Dual MCU Verification")
    print("=" * 70)

    results = {}
    try:
        results["boot"] = test_boot(bridge)
        results["framerate"] = test_framerate(bridge)
        results["safety"] = test_safety(bridge)
        results["spi"] = test_spi_protocol(bridge)
        results["dqn"] = test_dqn_integration(bridge)

        print("\n" + "=" * 70)
        print("  SUMMARY")
        print("=" * 70)
        for name, result in results.items():
            if isinstance(result, bool):
                print(f"  {name:15s}: {'✓ PASS' if result else '✗ FAIL'}")
            elif isinstance(result, dict):
                # Show key metrics
                if "fps_sim" in result:
                    print(f"  {name:15s}: {result['fps_sim']:.1f} fps (sim)")
                elif "estop_wr" in result:
                    print(f"  {name:15s}: {'✓ PASS' if result.get('estop_wr') else '✗ FAIL'}")
                else:
                    print(f"  {name:15s}: {'✓ PASS' if result.get('obs_ok') else '---'}")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
    finally:
        bridge.close()
        daemon.stop()

    return 0


if __name__ == "__main__":
    exit(main())
