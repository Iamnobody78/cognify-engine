"""通用 Python Agent 接入示例（P9）— 进程内 agent_tools 治理。

证明: 任意 Python Agent 可通过 `src.agent_tools` 三工具被治理——
  run_self_critic() 自我审查输出草案
  get_self_trace()  追溯决策因果链
  heal_candidate()  对不可部署候选生成修正建议

运行: .venv-b2/Scripts/python.exe examples/external_agent_demo.py
证据: stdout 含 [CRITIC] verdict=... / [TRACE] node_count=... /
      [HEAL] fixes=... 行 = 治理真实生效。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp950 兼容

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.agent_tools import get_self_trace, heal_candidate, run_self_critic  # noqa: E402


def main() -> int:
    print("=== 通用 Python Agent：经 agent_tools 被治理 ===")

    # 1. 元审计: 输出草案前自我审查（Sense）
    report = run_self_critic(REPO_ROOT)
    print(f"[CRITIC] verdict={report['verdict']} "
          f"high={report['high_count']} "
          f"per_critic={report['per_critic']}")
    if report["verdict"] == "REJECT":
        print("[CRITIC] 草案被拒绝 — 治理拦截生效（不进入部署）")
        return 1

    # 2. 元追踪: 追溯最近决策的因果链（Diagnose）
    trace = get_self_trace("p9-demo-trace", storage=None)
    print(f"[TRACE] trace_id={trace['trace_id']} "
          f"node_count={trace['node_count']} depth={trace['depth']}")

    # 3. 元代码: 对不可部署候选生成修正建议（Remediate）
    #    用不存在的候选文件 → 语法校验失败 → 产出 fixes 修正建议
    missing = REPO_ROOT / "pending_rules" / "p9_candidate.yaml"
    heal = heal_candidate(missing, REPO_ROOT / "config" / "policies.yaml")
    print(f"[HEAL] deployable={heal['deployable']} fixes={len(heal['fixes'])}")
    for fix in heal["fixes"]:
        print(f"  [HEAL][{fix['category']}] {fix['hint']}")

    print("=== 治理证据输出完毕：CRITIC + TRACE + HEAL 三工具均真实执行 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
