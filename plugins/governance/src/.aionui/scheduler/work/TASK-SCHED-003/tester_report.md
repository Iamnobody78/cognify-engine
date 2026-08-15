# Tester Report — TASK-SCHED-003 (MCP Tool Sharing)

## Role
Tester — write `tests/test_rate_limiter.py` (12 tests) against the contract.

## Channel discipline
Every artifact below was written through the **MCP shared tool bus**
(`mcp_client.py` → `filesystem_mcp_server.py`, stdio, JSON-RPC 2.0).
No native file writes by the sub-agent.

## Commands (audit trail)
- `mcp_client.py call write_file path=tests/test_rate_limiter.py content=...`
  → 3185 bytes.
- `mcp_client.py call file_info path=tests/test_rate_limiter.py` → verify.

## Test coverage
12 tests: happy-path allow/refill/remaining, capacity cap, atomic
non-consumption, and **empty/whitespace key rejection** (`allow`, `refill`,
`remaining` all must raise `ValueError`).

## Contract ruling (Coordinator, after parallel divergence)
- Tester read the contract strictly: `remaining()` must validate the key
  too (defense in depth).
- Builder v1's lenient `remaining()` (no key check) conflicted.
- **Ruling: tests win** — stricter interpretation, matches contract text
  and stronger protection. Builder round 2 added `_check_key` to
  `remaining()`.
- Final: `pytest tests/test_rate_limiter.py -q` → **12 passed**.

## Note on the earlier "written but missing" report
The first tester_report.md write was claimed but `file_info` reported
Not found (sub-agent truncated before flush). Per write-early protocol the
report was rebuilt through the MCP channel with full command trail above.
