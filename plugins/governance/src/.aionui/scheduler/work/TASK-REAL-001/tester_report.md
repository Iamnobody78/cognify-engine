# Tester Report — TASK-REAL-001 (Real-World Debt Repayment)

- **Role**: Tester (contract-authority for DEBT-0005 / DEBT-0006). Tests pin expected behavior; Coordinator rules in favor of tests if Builder implementation contradicts them.
- **Channel discipline**: All file writes/verifications performed through the MCP bus
  (`scripts/mcp_client.py call write_file` / `file_info`) using `.venv-b2\Scripts\python.exe`.
  Temp staging files were authored natively only to avoid shell-quoting corruption of multi-line content.
- **Note**: MCP transport (`scripts/mcp_client.py` line ~89) converts literal `
` to real newlines;
  both test files are therefore authored with triple-quoted strings (no backslash-n escapes).

## Test Files (verified via MCP file_info)

| path | size (bytes) | status |
|------|-------------|--------|
| tests/test_policy_hot_reload.py | 4550 | written via MCP, file_info OK |
| tests/test_check_policy_ast.py | 2670 | written via MCP, file_info OK (2nd write after fix) |

## Test List (10 tests)

### tests/test_policy_hot_reload.py — DEBT-0005 (PolicyEngine hot reload)
1. test_initial_load — engine from file: `_config_path` recorded, version '1', no rule matches => ALLOW
2. test_none_or_omitted_path_keeps_default — `PolicyEngine()` and `PolicyEngine(None)` keep default behavior (config/policies.yaml)
3. test_mtime_unchanged_no_reload — `maybe_reload()` right after init => False
4. test_reload_picks_up_changes — edit to version '2' + DENY rule, os.utime bump => `maybe_reload()` True, evaluate => DENY (fix proves no-restart reload)
5. test_reload_missing_file_keeps_old — delete file => `reload()` False, old rules (ALLOW) kept
6. test_reload_invalid_yaml_keeps_old — garbage yaml + mtime bump => `reload()` False, old rules kept

### tests/test_check_policy_ast.py — DEBT-0006 (exact-token matching)
7. test_no_false_positive_on_substring_keys — {'allow_retry','deny_attempt','blocked_by'} => NO violation
8. test_detects_exact_action_keys — {'allow','deny'} => violation (old capability preserved)
9. test_single_exact_key_not_enough — {'allow'} only => NOT a violation (len>=2 threshold)
10. test_clean_file — clean code => no violation

## Pytest Result

Command: `.\.venv-b2\Scripts\python.exe -m pytest tests\test_policy_hot_reload.py tests\test_check_policy_ast.py -q`

- **PASS: 3, FAIL: 7** (10 total, 0.67s)
- Passing: tests 8, 9, 10 (AST exact-keys / threshold / clean-file) — confirm test harness itself is sound.

## Parallel-Race Failures (pending Builder fix — Coordinator must re-run after Builder completes)

1. **DEBT-0005 (6 failures)**: `PolicyEngine` has no `_config_path`, `reload()`, `maybe_reload()`,
   and `PolicyEngine(None)` raises `TypeError: expected str... not NoneType` in `_load`.
   Builder must implement: path-or-None init + `_config_path` + `reload()`/`maybe_reload()` (mtime-based).
2. **DEBT-0006 (1 failure)**: test_no_false_positive_on_substring_keys — current `scan_file` still uses
   substring `in` matching and flags `allow_retry/deny_attempt/blocked_by` (reported
   `hardcoded_dict` violation). Builder must switch to exact-token matching.

## Other Notes

- Test-infra bug fixed during session (not a Builder race): `check_policy.scan_file` annotates
  `filepath: Path` and calls `.read_text()`; fixtures now pass `Path` objects (initial version passed `str`).
- No sleeps in tests (mtime bumped via `os.utime`, not `time.sleep`).
- After Builder lands both debts, expected result: 10/10 pass with no test changes.
