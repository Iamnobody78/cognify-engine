"""伦理边界示例: ethics 规则 → DENY

演示 11-col-v1 协议中 ethics_boundary 编译出的 ethics 规则:
  触发伦理边界 (violation) → action=DENY, 且该规则不依赖 satisfied 声明
  → 验证通道平凡通过 (verified=True, c=1.0), 因为 DENY 不需要"放行声明"背书。

运行:
    python examples/ethics_deny_demo.py
预期:
    DENY (ethics) — verified=True (平凡), action 保持 DENY
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


def main() -> None:
    gw = ProtocolGateway(
        protocols_dir=str(PROTOCOLS_DIR),
        validator=BaselineDeclarationValidator(),
    )

    # 故意触发费曼测试协议伦理边界: 用误导性简化伪装解释
    bad_request = {
        "governance": {"protocols": {"feynman_test": {
            "satisfied": True,
            "violation": "用『量子退相干』术语掩盖不确定的解释",
        }}}
    }
    r = gw.evaluate_verified("/api/explain", "POST", body=bad_request)

    print("规则命中:", r["rule"])
    print("最终动作:", r["action"])
    print("验证通道:", r["channel"])
    print("验证详情:", r["verification"])

    # 伦理 DENY 应保持 DENY (不被验证通道覆盖), 平凡通过因为无需放行背书
    ok = (r["action"] == "DENY"
          and r["verification"]["verified"] is True)
    print("=" * 64)
    print("伦理边界判定:", "PASS — DENY 不受谎报通道影响" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
