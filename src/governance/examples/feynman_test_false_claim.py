"""S66 谎报缓解示例: 裸 satisfied 声明 → ESCALATE 降级 (c=0.6)

演示 ProtocolGateway.evaluate_verified 的声明验证通道:
  - 带证据锚点 (evidence/output/result/proof) 的 satisfied → verified=True
  - 裸 satisfied (declaration_only) → verified=False → ok 规则降级为 ESCALATE
  - 矛盾声明 (violation) → 触发 ethics 硬阻断 → DENY (验证通道平凡通过)

运行:
    python examples/feynman_test_false_claim.py
预期:
    claim_same_day   → verified=True  (有证据锚点, c=0.8) → ALLOW_WITH_WARNING
    claim_next_day   → verified=False (裸声明, c=0.6)     → ESCALATE
    contradiction    → verified=True  (DENY 无需放行背书) → DENY
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.protocol_gateway import ProtocolGateway
from src.verification import BaselineDeclarationValidator

PROTOCOLS_DIR = REPO_ROOT / "config" / "protocols"


def make_claim(satisfied: bool, with_evidence: bool) -> dict:
    body = {"governance": {"protocols": {"feynman_test": {"satisfied": satisfied}}}}
    if with_evidence:
        body["governance"]["protocols"]["feynman_test"]["evidence"] = {
            "qa_pair": {"Q": "什么是费曼测试？", "A": "用大白话解释一个概念，看能否讲明白。"},
            "score": 0.85,
        }
    return body


def main() -> None:
    gw = ProtocolGateway(
        protocols_dir=str(PROTOCOLS_DIR),
        validator=BaselineDeclarationValidator(),
    )

    print(f"验证通道: {gw.validator.name} (baseline)")
    print("=" * 64)

    # 场景 1: 带证据锚点 (有 context 支撑) — 应放行
    with_evidence = make_claim(satisfied=True, with_evidence=True)
    r1 = gw.evaluate_verified("/api/task", "POST", body=with_evidence)
    print(f"[1] 有证据锚点   → action={r1['action']:<22} "
          f"verified={r1['verification']['verified']} c={r1['verification']['confidence']}")

    # 场景 2: 裸 satisfied (declaration_only 谎报盲点) — 应降级 ESCALATE
    bare_claim = make_claim(satisfied=True, with_evidence=False)
    r2 = gw.evaluate_verified("/api/task", "POST", body=bare_claim)
    print(f"[2] 裸声明       → action={r2['action']:<22} "
          f"verified={r2['verification']['verified']} c={r2['verification']['confidence']}")

    # 场景 3: 矛盾声明 (violation + satisfied) — 应降级
    contradiction = {
        "governance": {"protocols": {"feynman_test": {
            "satisfied": True, "violation": "未做费曼测试直接断言通过"}}}
    }
    r3 = gw.evaluate_verified("/api/task", "POST", body=contradiction)
    print(f"[3] 矛盾声明     → action={r3['action']:<22} "
          f"verified={r3['verification']['verified']} c={r3['verification']['confidence']}")

    # 断言 (作为 exit code)
    #   [1] 有证据 → 非 ESCALATE (放行)     [2] 裸声明 → ESCALATE (降级)
    #   [3] 矛盾声明 → DENY (伦理硬阻断, 优先于降级)
    ok = (r1["action"] != "ESCALATE"
          and r2["action"] == "ESCALATE"
          and r3["action"] == "DENY")
    print("=" * 64)
    print("验证通道判定:", "PASS — 谎报被拦截" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
