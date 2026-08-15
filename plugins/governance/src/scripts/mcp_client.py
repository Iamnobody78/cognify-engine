"""MCP client CLI — shared-tool channel for scheduler sub-agents (TASK-SCHED-003).

Spawns the BottleSumo Platform Filesystem MCP server (self-contained Python,
JSON-RPC 2.0 over stdio, JSON-lines framing) and forwards tool calls to it.

Why this exists: sub-agents in the scheduler relay (Builder/Tester/Reviewer)
need a SHARED tool bus. Instead of each agent doing raw file I/O, all roles
call the SAME MCP server through this CLI — output lands via MCP write_file,
reviewers read via MCP read_file, and the server enforces a path sandbox
(BOTTLESUMO_ROOT) so no role can escape the repo.

Usage (PowerShell):
    python scripts/mcp_client.py tools
    python scripts/mcp_client.py call write_file path=.aionui/scheduler/work/TASK-SCHED-003/x.txt content="hello"
    python scripts/mcp_client.py call read_file path=.aionui/scheduler/work/TASK-SCHED-003/x.txt
    python scripts/mcp_client.py call list_directory path=.aionui/scheduler/work
    python scripts/mcp_client.py call file_info path=src/task_scheduler.py

Exit codes: 0 = success, 1 = tool error / protocol error.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER = Path(os.environ.get(
    "BOTTLESUMO_MCP_SERVER",
    r"C:\Users\ivy\AppData\Roaming\AionUi\.aionui\mcp\filesystem_mcp_server.py",
))
SANDBOX = os.environ.get("BOTTLESUMO_ROOT", str(REPO_ROOT))


def _spawn_server():
    """Start the MCP server subprocess (stdio), return (proc, stdin, stdout)."""
    env = dict(os.environ)
    env["BOTTLESUMO_ROOT"] = SANDBOX
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc


def _send(proc, payload: dict, expect_response: bool = True) -> dict | None:
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    if not expect_response:
        return None  # notification: server never replies
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("MCP server closed stdout (no response)")
    return json.loads(line)


def main(argv) -> int:
    proc = _spawn_server()
    try:
        # 1. initialize (protocol handshake)
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "notifications/initialized"},
              expect_response=False)

        if argv and argv[0] == "tools":
            resp = _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            tools = resp.get("result", {}).get("tools", [])
            for t in tools:
                print(f"{t['name']}: {(t.get('description') or '').splitlines()[0][:100]}")
            return 0

        if argv and argv[0] == "call" and len(argv) >= 2:
            tool_name = argv[1]
            # parse key=value args; values stay strings (server coerces)
            arguments = {}
            for kv in argv[2:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    # literal \n in single-line command → real newline, so
                    # multi-line content can flow through one MCP write_file
                    arguments[k] = v.replace("\\n", "\n")
                else:
                    arguments[kv] = True
            resp = _send(proc, {
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            })
            result = resp.get("result", {})
            if result.get("isError"):
                text = "\n".join(c.get("text", "") for c in result.get("content", []))
                print(f"MCP-ERROR: {text}", file=sys.stderr)
                return 1
            for c in result.get("content", []):
                if c.get("type") == "text":
                    print(c.get("text", ""))
            return 0

        print(__doc__)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"MCP-CLIENT-ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
