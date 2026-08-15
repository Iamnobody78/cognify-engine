#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S64 Phase 1: 生成 MCE 2.0 自省产物 (规则可反问"我为什么存在")。

Usage: python scripts/compile_mce_introspection.py [protocols_dir] [out_path]
Defaults: config/protocols → config/mce_introspection.generated.json
"""
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # cp950 控制台无法编码中文 (Windows)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.protocol_gateway import ProtocolGateway  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(REPO, "config", "protocols")
DEFAULT_OUT = os.path.join(REPO, "config", "mce_introspection.generated.json")


def main() -> int:
    in_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    out_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT

    gw = ProtocolGateway(protocols_dir=in_dir)
    intro = gw.introspect()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(intro, f, ensure_ascii=False, indent=2)

    print(f"protocols: {len(intro['protocols'])}")
    total = sum(len(rmcs) for rmcs in intro["protocols"].values())
    print(f"rules introspected: {total}")
    for mod, rmcs in intro["protocols"].items():
        for rmc in rmcs:
            print(f"  [{mod}] {rmc['rule']} → {rmc['ast']['Core_Directive'][:70]}")
    print(f"written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
