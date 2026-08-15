# Builder Report — TASK-REAL-001

**Role**: Builder (v2) — committed the diffs designed by Builder (v1) through the MCP bus and verified. No redesign performed.

## Channel Discipline
All repo writes went through the MCP bus (`scripts/mcp_client.py call write_file`), confirmed via `file_info`:
- `src/policy.py` — **4154 bytes** (write reported 4032 chars) — full-file replacement (DIFF 1)
- `src/main.py` — **23449 bytes** (write reported 22150 chars) — 2 exact-string insertions (DIFF 2)
- `scripts/check_policy.py` — **3686 bytes** (write reported 3574 chars) — 1-line replacement (DIFF 3)

## Implementation Summary
- **reload/maybe_reload mtime semantics**: `PolicyEngine._load()` records `os.path.getmtime()` after a successful read; `maybe_reload()` returns False when mtime is unchanged and only calls `reload()` when mtime differs (DEBT-0005 hot reload). `reload()` swallows all exceptions (missing file / invalid YAML) and keeps the previous rules — fail-safe.
- **Atomic `_load` swap**: rules are built into a fresh `new_rules` list and only assigned to `self.rules` after the entire YAML parses and all `Rule.__post_init__` validations pass (fail-closed on invalid action); a failed parse never leaves a half-loaded state.
- **Exact-token matching**: `check_policy.py` Gate 3 now uses `key_lower in ("allow", "deny", "block", "escalate", "rule")` — exact-token comparison, no substring false positives. `main.py` gained two `await asyncio.to_thread(policy_engine.maybe_reload)` calls (pre-gate and pre-chat).
- **Deviation A (transport bug)**: `mcp_client.py` converts every literal `\n` to a real newline, corrupting the `print(f"\n  Policy must be…")` f-string in check_policy.py. Fixed by driving the same MCP server directly (JSON-RPC tools/call with exact content) — still 100% through the MCP bus.
- **Deviation B (test contract)**: the Tester's pinned contract requires `_config_path` stored as `str(path)` and `PolicyEngine(None)` falling back to the default `config/policies.yaml`. Two minimal lines added to `__init__` (str coercion + None fallback); nothing else changed.

## Verification Results
- `pytest tests/test_policy_hot_reload.py tests/test_check_policy_ast.py -q` → **10 passed**
- Hot-reload probe (temp YAML v1→v2 + `os.utime`, evaluate /secret) → **HOT-RELOAD OK**
- `python scripts/check_policy.py src` → **exit 0** (`[PASS] GATE 3: no hardcoded policy patterns in 8 source files`)
- Full suite `pytest tests\ -q` → **152 passed** (142 pre-existing + 10 new), 63 warnings (pre-existing deprecation warnings only)
