# Builder Report — TASK-SCHED-003 (MCP Tool Sharing)

## Role
Builder — implement `src/rate_limiter.py` (token-bucket) per contract.

## Channel discipline
Every artifact below was written through the **MCP shared tool bus**
(`mcp_client.py` → `filesystem_mcp_server.py`, stdio, JSON-RPC 2.0).
No native file writes by the sub-agent.

## Commands (audit trail)
- `mcp_client.py call write_file path=src/rate_limiter.py content=...`
  → first write: 1347 chars (pre-fix).
- `mcp_client.py call write_file path=src/rate_limiter.py content=...`
  → second write: **1479 chars** — `remaining()` gained `_check_key`
    (empty/whitespace key now raises `ValueError`, matching contract and
    Tester's stricter interpretation).
- `mcp_client.py call file_info path=src/rate_limiter.py` → verify size.

## Implementation summary
- `RateLimiter(capacity=10)` token bucket, per-key.
- `_check_key` / `_check_tokens` validation; `ValueError` on bad input.
- `allow()` — atomic consume, no consumption on failure.
- `refill()` — capped at capacity.
- `remaining()` — returns capacity for unknown key; **validates key** (fixed
  in round 2 after Coordinator's contract ruling: test wins over lenient impl).

## Verification (Coordinator side)
- `pytest tests/test_rate_limiter.py -q` → **12 passed** after fix.
- File size verified via MCP `file_info` (1479 chars) — no truncation.
