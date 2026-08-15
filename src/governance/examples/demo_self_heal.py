"""自愈链路演示（阶段 B）— Sense → Diagnose → Remediate 完整闭环。

演示治理网关的自我修复能力：
  1. Sense     — 自我审查：对当前代码库跑 5 批判者，得到 verdict
  2. Diagnose  — 因果追踪：追溯最近一次决策的 trace 因果链
  3. Remediate — 沙箱评估候选：对"冲突候选"生成结构化修正建议
  4. 熔断演示  — 用 PolicyEngine 演示 FAIL-CLOSED 语义（降级=拒绝而非放行）

运行: .venv-b2/Scripts/python.exe examples/demo_self_heal.py
证据: stdout 含 [SENSE] verdict=... / [DIAGNOSE] node_count=... /
      [REMEDIATE] fixes=... / [CIRCUIT] fail_closed=... 行。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp950 兼容

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.agent_tools import get_self_trace, heal_candidate, run_self_critic  # noqa: E402
from src.meta_harness.adapter import validate_candidate  # noqa: E402
from src.policy import PolicyEngine  # noqa: E402


def _write_candidate(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def main() -> int:
    print("=== 自愈链路演示：Sense → Diagnose → Remediate ===")

    # ── 1. SENSE: 自我审查（L4 批判者团队）─────────────────────────────
    print("\n[1/4] SENSE — 自我审查代码库")
    report = run_self_critic(REPO_ROOT)
    print(f"[SENSE] verdict={report['verdict']} "
          f"high={report['high_count']} medium_critics={report['medium_critics']} "
          f"per_critic={report['per_critic']}")
    if report["verdict"] == "REJECT":
        print("[SENSE] 高优先级问题存在 — 治理拦截生效")

    # ── 2. DIAGNOSE: 因果追踪（MH-1 trace 链）─────────────────────────
    print("\n[2/4] DIAGNOSE — 追溯决策因果链")
    trace = get_self_trace("self-heal-demo", storage=None)
    print(f"[DIAGNOSE] trace_id={trace['trace_id']} "
          f"node_count={trace['node_count']} depth={trace['depth']}")

    # ── 3. REMEDIATE: 沙箱评估候选（L5 自愈）───────────────────────────
    print("\n[3/4] REMEDIATE — 沙箱评估候选策略")
    with tempfile.TemporaryDirectory() as td:
        # 3a. 语法合法但路径冲突的候选 → 沙箱应给出 conflict 修正建议
        bad = Path(td) / "conflict_candidate.yaml"
        _write_candidate(bad, """
name: conflict-candidate
version: 0.1.0
rules:
  - name: allow-delete-file
    path_pattern: /api/delete/*
    method: POST
    action: ALLOW
    reason: 与既有 /api/delete/* DENY 规则冲突
""")
        heal = heal_candidate(bad, REPO_ROOT / "config" / "policies.yaml")
        print(f"[REMEDIATE] deployable={heal['deployable']} fixes={len(heal['fixes'])}")
        for fix in heal["fixes"]:
            print(f"  [REMEDIATE][{fix['category']}] {fix['hint']}")

        # 3b. 语法合法且无冲突的候选 → 应可部署
        good = Path(td) / "good_candidate.yaml"
        _write_candidate(good, """
name: good-candidate
version: 0.1.0
rules:
  - name: audit-metrics-read
    path_pattern: /v1/metrics
    method: GET
    action: ALLOW
    reason: 只读指标端点
""")
        heal2 = heal_candidate(good, REPO_ROOT / "config" / "policies.yaml")
        print(f"[REMEDIATE] good: deployable={heal2['deployable']} fixes={len(heal2['fixes'])}")

    # ── 4. FAIL-CLOSED 熔断语义（降级=拒绝，不是放行）──────────────────
    print("\n[4/4] CIRCUIT — FAIL-CLOSED 熔断语义")
    engine = PolicyEngine(
        config_path=str(REPO_ROOT / "config" / "policies.yaml"),
        ast_guard=None,
    )
    # 模拟熔断器打开时（无可用规则）——空策略文件必须拒绝加载
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty.yaml"
        empty.write_text("# no rules\n", encoding="utf-8")
        try:
            PolicyEngine(config_path=str(empty), ast_guard=None)
            fail_closed = False
        except ValueError:
            fail_closed = True
        print(f"[CIRCUIT] empty_policy_refused={fail_closed} "
              f"(fail-closed: 无法验证即拒绝，绝不静默 ALLOW)")
        if not fail_closed:
            return 1

    print("\n=== 自愈链路闭环完成：SENSE + DIAGNOSE + REMEDIATE + FAIL-CLOSED 全部真实执行 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
