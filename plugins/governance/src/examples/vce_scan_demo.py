"""VCE 2.0 扫描示例: 治理规则自审 (冲突 / 盲点 / 极化)

演示 ProtocolGateway.scan() — S65 治理"自审"能力:
  消费 MCE 自省产物, 检测协议规则间的极化/冲突/盲点,
  并报告验证通道状态 (verification_channel: baseline)。

运行:
    python examples/vce_scan_demo.py
预期:
    输出扫描报告: Polarization_Index, RuleConflicts, BlindSpots 等字段
"""

import json
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

    report = gw.scan()

    print(f"VCE 2.0 扫描报告 (channel={report.get('verification_channel', '?')})")
    print("=" * 64)
    for key in ("Polarization_Index", "RuleConflicts", "BlindSpots",
                "Asymmetric_Perspectives", "honest_boundary"):
        if key in report:
            print(f"  {key}: {json.dumps(report[key], ensure_ascii=False, default=str)}")
    print(f"  协议模块: {gw.modules}")

    # MCE 自省也可独立查看 (S64)
    intro = gw.introspect()
    print(f"  MCE 自省: {len(intro['protocols'])} 个协议, "
          f"版本 {intro['version']}")

    ok = "RuleConflicts" in report
    print("=" * 64)
    print("VCE 扫描判定:", "PASS — 扫描报告可生成" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
