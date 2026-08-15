# Builder Report S1 — TASK-REAL-003

**Role:** Builder S1 (main group) — Coordinator fallback (R3)
**Repo:** agent-governance-v2
**Status:** COMPLETE (via R3 fallback; original sub-agent reported BLOCKED with 0 edits)

## Why fallback (audit trail)

The S1 sub-agent misread the harness instruction "do not call tools" as a global
prohibition, performed 0 edits, and returned BLOCKED — but it DID verify every
anchor (B1 constants L30-32, B2 `_is_dangerous` L51-73, B3 `app=web.Application`,
B4 before `create_app`, B5 `web.run_app` L573) with count==1 uniqueness, and
flagged the `storage.flush_pending()` pre-existence risk (later confirmed by S2's
successful storage edits). Per protocol R3, the Coordinator executed the exact
verified design. This is the 2nd occurrence of sub-agent truncation/blocking →
will be extracted in the learning loop as a new constraint.

## Edits applied

1. **CREATE `src/danger.py` (new, 2003 chars):** module docstring; constants
   `DANGEROUS_PREFIXES = ("/api/delete", "/api/admin", "/api/config", "/api/model")`;
   `DANGEROUS_METHODS = ("DELETE", "POST", "PUT", "PATCH")`; `is_dangerous(path, method)`
   with the identical 3-layer defense (normpath → boundary prefix match → segment
   fallback); `__all__` re-export. Behavior-binary-identical to old `_is_dangerous`.
2. **EDIT B1 (main.py):** removed module-level `DANGEROUS_PREFIXES`/`DANGEROUS_METHODS`
   constant block (anchors L30-32).
3. **EDIT B2 (main.py):** removed `_is_dangerous` function body (anchors L51-73);
   removed now-unused `import posixpath`.
4. **EDIT B3 (main.py):** added `from .danger import DANGEROUS_PREFIXES, DANGEROUS_METHODS,
   is_dangerous as _is_dangerous` — keeps `src.main._is_dangerous` importable for
   tests/test_security_hardening.py L18 while the logic lives in the public module
   (DEBT-0002: no private coupling).
5. **EDIT B4 (main.py):** added `async def _flush_pending_on_shutdown(app)` +
   `app.on_cleanup.append(_flush_pending_on_shutdown)` in `create_app()` (DEBT-0010:
   flush degraded-mode `_pending` on graceful shutdown).
6. **EDIT B5 (main.py):** `web.run_app(app, port=9000, shutdown_timeout=10)` (DEBT-0007).
7. **EDIT B6 (policy_sync.py — NEW, Coordinator discovery):** `load_dangerous_prefixes()`
   AST-scanned `src/main.py` for the constant; migrated to scan `src/danger.py` first,
   fall back to `src/main.py` for older checkouts. Without this, G3 health gate would
   silently read `[]` and false-report YAML drift (DEBT-0002 full semantics: ALL
   consumers of the private symbol must migrate, not just the gateway).

## Defects caught during verification (real-value)

- **D1 (awaitable contract):** `_flush_pending_on_shutdown` was sync; aiohttp
  `on_cleanup` signals `await` each receiver → `TypeError: object NoneType can't be
  used in 'await' expression` crashed test fixture teardown (6 tests red). Fixed to
  `async def`. The planned S1 design had this bug; only execution-time verification
  caught it — evidence for the protocol's AUDIT→PLAN→SPAWN→**VERIFY** loop.

## Verification evidence (.venv-b2)

1. `py_compile src\main.py src\danger.py scripts\policy_sync.py` → **COMPILE_OK**
2. `python scripts\policy_sync.py` → **GATE 7 PASS, 4 prefixes read from src/danger.py**
3. Import contract probe: `from src.main import create_app, _is_dangerous, DANGEROUS_PREFIXES`
   + `from src.danger import is_dangerous` → equivalence asserts all True (boundary
   match, segment fallback, query-string strip, GET pass-through) → **IMPORT_CONTRACT_OK**
4. `pytest tests\test_security_hardening.py tests\test_storage_degraded.py tests\test_check_policy_ast.py -q`
   → **23 passed** (after D1 fix; 17 passed + 6 failed before)

## Handoff notes

- `src/main.py` no longer owns the heuristic; private name kept as alias only.
- `scripts/policy_sync.py` now resolves constants from `src/danger.py` (fallback chain).
- Tester (S3) must add `tests/test_danger_module.py` (public API standalone tests) and
  extend `tests/test_storage_degraded.py` (pending cap + shutdown flush).
