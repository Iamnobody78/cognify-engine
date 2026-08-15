#!/usr/bin/env python3
"""Raw Renode monitor test - check what Renode actually sends"""

import socket
import subprocess
import time

HOST, PORT = "127.0.0.1", 3333

proc = subprocess.Popen(
    ["/usr/local/bin/renode", "--disable-xwt", f"--port={PORT}"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
for _i in range(60):
    try:
        s = socket.create_connection((HOST, PORT), timeout=1)
        s.close()
        break
    except Exception:
        time.sleep(1)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5.0)
sock.connect((HOST, PORT))

# Read initial bytes without processing
sock.settimeout(1.0)
time.sleep(0.5)
try:
    init = sock.recv(4096)
    print(f"Initial bytes ({len(init)}): {init.hex()}")
    print(f"Raw: {repr(init)}")
except TimeoutError:
    print("No initial bytes received (timeout)")

# Send a command
sock.settimeout(5.0)
sock.sendall(b"help\n")
time.sleep(0.5)
sock.settimeout(1.0)
try:
    resp = sock.recv(8192)
    print(f"\nResponse to 'help' ({len(resp)} bytes):")
    print(repr(resp[:500]))
except TimeoutError:
    print("No response received")

sock.close()
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
