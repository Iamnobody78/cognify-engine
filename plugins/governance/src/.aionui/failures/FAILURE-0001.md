# 失败归档 — failures/

> 规则：每次失败（bug、CI 失败、审查 REJECT）单独归档。
> 格式：日期 + 现象 + 根因 + 修复 + 预防。

---

## FAILURE-0001 — 2026-08-03T05:10:00Z

**现象**: `python -m pytest tests/` 从 agent-governance-v2 目录运行时报 28 failed（500 Internal Server Error），而 `pytest.exe` 运行 53 passed。

**根因**: pytest rootdir 判定向上漂移到父工作区（bottlesumo 的 pyproject.toml 含 `[tool.pytest.ini_options]`），导致 `src` 包解析错位 → 所有 aiohttp 集成测试 500。

**修复**: 在 agent-governance-v2/pyproject.toml 添加 `[tool.pytest.ini_options] testpaths=["tests"]`，锁死 rootdir。

**预防**: health_score.py 的 gate_tests 用 `sys.executable -m pytest`（依赖 rootdir 正确）——本次失败由它暴露。

---

## FAILURE-0002 — 2026-08-03T04:50:00Z

**现象**: GATE 7 policy_sync 场景 B（小写 `deny` 篡改）漏检——返回 PASS 而非 FAIL。

**根因**: `load_policy_deny_paths` 用 `.upper()` 归一化 action，小写 `deny` 变 `DENY` 后通过白名单检查，恰好掩盖了 AUDIT-0004 要防的漏洞。

**修复**: 检查**原始值**（`action_raw not in ALLOWED_ACTIONS`），不归一化。场景 B 现在正确 REJECT。

**预防**: 对抗性篡改验证必须包含"与修复目标相同的绕过向量"（.upper() 归一化本身是绕过向量）。
