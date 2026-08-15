#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S65 Phase 2: 生成 VCE 2.0 扫描报告产物 (规则自审冲突/盲点)。

Usage: python scripts/compile_vce_scan.py [protocols_dir] [out_path]
Defaults: config/protocols → config/vce_scan_report.json
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # cp950 控制台无法编码中文 (Windows)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.protocol_gateway import ProtocolGateway  # noqa: E402
from src.vce_scanner import summarize_scan  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(REPO, "config", "protocols")
DEFAULT_OUT = os.path.join(REPO, "config", "vce_scan_report.json")


def main() -> int:
    in_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    out_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT

    gw = ProtocolGateway(protocols_dir=in_dir)
    report = gw.scan()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(summarize_scan(report))
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
