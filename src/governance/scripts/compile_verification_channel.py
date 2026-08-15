# -*- coding: utf-8 -*-
"""S66: 生成验证通道产物 (declaration_only 盲点缓解实证)。

产物:
  1. config/verification_channel.generated.json — 验证通道状态 + 样本裁决实证
  2. config/vce_scan_report.json (重扫) — Verification_Channel 字段出现,
     declaration_only 盲点消除 (VCE 联动验收项)

Usage: python scripts/compile_verification_channel.py [protocols_dir] [out_path]
Defaults: config/protocols → config/verification_channel.generated.json
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # cp950 控制台无法编码中文 (Windows)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.protocol_gateway import ProtocolGateway  # noqa: E402
from src.verification import BaselineDeclarationValidator  # noqa: E402
from src.vce_scanner import summarize_scan  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(REPO, "config", "protocols")
DEFAULT_OUT = os.path.join(REPO, "config", "verification_channel.generated.json")
VCE_OUT = os.path.join(REPO, "config", "vce_scan_report.json")


def _sample_verdicts(gw) -> list:
    """三类代表性裁决样本: 合法锚定 / 零成本谎报 / 矛盾声明。"""
    r = {}
    for rule in gw.rules:
        r[rule.name] = rule
    samples = [
        {
            "label": "legitimate_with_anchor (合法声明+证据锚点)",
            "body": {"governance": {"protocols": {"feynman_test": {
                "satisfied": True,
                "evidence": "feynman_self_check_passed_v2"}}}},
        },
        {
            "label": "zero_cost_bypass_attempt (零成本谎报: 无锚点)",
            "body": {"governance": {"protocols": {"feynman_test": {
                "satisfied": True}}}},
        },
        {
            "label": "contradictory_declaration (violation+satisfied 矛盾)",
            "body": {"governance": {"protocols": {"entropy_denoise": {
                "satisfied": True, "violation": "e7d9"}}}},
        },
    ]
    out = []
    for s in samples:
        verdict = gw.evaluate_verified("/gateway", "POST", s["body"])
        out.append({
            "label": s["label"],
            "body": s["body"],
            "matched_rule": verdict["rule"],
            "final_action": verdict["action"],
            "verification": verdict["verification"],
        })
    return out


def main() -> int:
    in_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    out_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT

    gw = ProtocolGateway(protocols_dir=in_dir,
                         validator=BaselineDeclarationValidator())

    # 1) 验证通道产物
    channel_artifact = {
        "channel": {
            "type": "pluggable-validator",
            "validator": gw.validator.name,
            "interface": "DeclarationValidator.validate(rule, path, method, body)",
            "design_doc": "docs/s66_verification_channel.md",
        },
        "mitigated_blindspot": "declaration_only (satisfied 谎报绕过 enforce)",
        "baseline_checks": [
            "violation+satisfied 矛盾 → verified=False (c=0.95)",
            "satisfied+证据锚点 → verified=True (c=0.8)",
            "satisfied 无锚点 → verified=False (c=0.6) [盲点缓解主路径]",
            "协议状态缺失/非 dict → verified=False (c=0.9)",
            "非声明依赖规则 → 平凡通过 (c=1.0)",
        ],
        "honest_boundary": "基线只做一致性检查, 不证明 agent 真的执行了协议; "
                           "深层语义验证留给 LLM 层插槽",
        "sample_verdicts": _sample_verdicts(gw),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(channel_artifact, f, ensure_ascii=False, indent=2)
    print(f"written: {out_path}")

    # 2) VCE 联动: 重扫 (验证器已注入 → declaration_only 消除)
    report = gw.scan()
    with open(VCE_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(summarize_scan(report))
    print(f"written: {VCE_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
