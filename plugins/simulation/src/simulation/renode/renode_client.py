#!/usr/bin/env python3
"""
Renode Monitor Client — shared Telnet infrastructure for all Renode debug scripts.

Usage as module-level convenience functions:
    from renode_client import cmd, read_u32, read_pc, connect, shutdown

    sock = connect()
    cmd("mach add F407")
    cmd("machine LoadPlatformDescription @platforms/cpus/stm32f4.repl")
    cmd("sysbus LoadELF @/path/to/firmware.elf")
    cmd("start")
    pc = read_pc("F407")
    val = read_u32("F407", 0x20000000)
    shutdown()

Usage as RenodeClient class:
    from renode_client import RenodeClient

    rc = RenodeClient()
    rc.connect()
    rc.load_firmware("/path/to/main.elf", "/path/to/aux.elf")
    rc.start()
    pc = rc.read_pc("F407")
    rc.shutdown()
"""

import os
import socket
import subprocess
import sys
import time

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3333
RENODE_BIN = os.environ.get("RENODE_BIN", "renode")
CONNECT_RETRIES = 60
RETRY_INTERVAL = 1.0
PROMPT_MARKERS = [b"(monitor)", b"F407)", b"F103)"]


class RenodeClient:
    """Telnet-based Renode monitor client with connection management."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock = None
        self.proc = None

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self):
        """Start Renode and establish Telnet connection. Returns connected socket."""
        _kill_renode()
        self.proc = subprocess.Popen(
            [RENODE_BIN, "--disable-xwt", f"--port={self.port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _i in range(CONNECT_RETRIES):
            try:
                s = socket.create_connection((self.host, self.port), timeout=1)
                s.close()
                break
            except Exception:
                time.sleep(RETRY_INTERVAL)
        else:
            raise RuntimeError(f"Renode did not start within {CONNECT_RETRIES}s")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((self.host, self.port))
        time.sleep(0.3)
        self.sock.settimeout(0.5)
        _telnet_handshake(self.sock)
        return self.sock

    def shutdown(self):
        """Close connection and terminate Renode process."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    # ── Monitor commands ─────────────────────────────────────────────────

    def cmd(self, command, timeout=5):
        """Send a Renode monitor command string and return raw bytes response."""
        if self.sock is None:
            raise RuntimeError("Not connected. Call connect() first.")
        self.sock.settimeout(timeout)
        self.sock.sendall((command + "\n").encode())
        time.sleep(0.1)
        buf = b""
        self.sock.settimeout(timeout)
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if any(marker in chunk for marker in PROMPT_MARKERS):
                    break
        except TimeoutError:
            pass
        return buf

    # ── Memory & register access ─────────────────────────────────────────

    def read_u32(self, machine, addr):
        """Set machine context and read a 32-bit word from addr. Returns int or None."""
        self.cmd(f'mach set "{machine}"', timeout=1)
        resp = self.cmd(f"sysbus ReadDoubleWord {hex(addr)}", timeout=3)
        return _parse_hex_response(resp, exclude=addr)

    def read_pc(self, machine):
        """Set machine context and read program counter. Returns int or None."""
        self.cmd(f'mach set "{machine}"', timeout=1)
        resp = self.cmd("cpu PC", timeout=3)
        return _parse_hex_response(resp)

    def write_u32(self, machine, addr, value):
        """Write a 32-bit word to addr."""
        self.cmd(f'mach set "{machine}"', timeout=1)
        self.cmd(f"sysbus WriteDoubleWord {hex(addr)} {hex(value)}", timeout=3)

    # ── Machine lifecycle ────────────────────────────────────────────────

    def add_machine(self, name, platform_desc):
        """Add and configure a Renode machine."""
        self.cmd(f'mach add "{name}"')
        self.cmd(f'mach set "{name}"')
        self.cmd(f"machine LoadPlatformDescription {platform_desc}")

    def load_firmware(self, main_elf, aux_elf=None):
        """Load firmware ELF(s) — main into F407, optional aux into F103."""
        self.cmd(f'sysbus LoadELF @{main_elf}')
        if aux_elf:
            self.cmd(f'mach set "F103"')
            self.cmd(f'sysbus LoadELF @{aux_elf}')
            self.cmd(f'mach set "F407"')

    def start(self):
        """Start all machines."""
        self.cmd("start")

    def pause(self):
        """Pause all machines."""
        self.cmd("pause")


# ── Module internals ────────────────────────────────────────────────────────

_default_client = None


def _kill_renode():
    os.system("killall -9 renode 2>/dev/null; sleep 0.5")


def _telnet_handshake(sock):
    """Perform Telnet IAC negotiation (WONT/WILL echo, suppress go-ahead, etc.)."""
    try:
        data = sock.recv(4096)
        for chunk in data.split(b"\xff"):
            if len(chunk) >= 2:
                if chunk[0] == 0xFD:  # DO → WONT
                    sock.sendall(b"\xff\xfc" + chunk[1:2])
                elif chunk[0] == 0xFB:  # WILL → DONT
                    sock.sendall(b"\xff\xfe" + chunk[1:2])
    except Exception:
        pass


def _parse_hex_response(resp, exclude=None):
    """Find the first 0x-prefixed hex value in response bytes, skipping exclude."""
    text = resp.decode("utf-8", errors="replace")
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("0x"):
            try:
                val = int(line, 16)
                if exclude is not None and val == exclude:
                    continue
                return val
            except Exception:
                pass
    return None


# ── Module-level convenience API ────────────────────────────────────────────


def connect(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """Connect and return the socket (backward-compatible with old scripts)."""
    global _default_client
    _default_client = RenodeClient(host, port)
    return _default_client.connect()


def cmd(command, timeout=5):
    """Send a command to the default Renode client."""
    if _default_client is None:
        raise RuntimeError("Call connect() first")
    return _default_client.cmd(command, timeout)


def read_u32(machine, addr):
    """Read a 32-bit word from the default Renode client."""
    if _default_client is None:
        raise RuntimeError("Call connect() first")
    return _default_client.read_u32(machine, addr)


def read_pc(machine):
    """Read program counter from the default Renode client."""
    if _default_client is None:
        raise RuntimeError("Call connect() first")
    return _default_client.read_pc(machine)


def shutdown():
    """Shut down the default Renode client."""
    global _default_client
    if _default_client:
        _default_client.shutdown()
        _default_client = None
