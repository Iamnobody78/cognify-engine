#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S63: compile protocol YAML → protocol_policies.generated.yaml (executable by PolicyEngine).

Usage: python scripts/compile_protocol_policies.py [protocols_dir] [out_path]
Defaults: config/protocols → config/protocol_policies.generated.yaml
"""
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # cp950 控制台无法编码中文 (Windows)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import yaml  # noqa: E402

from src.protocol_gateway import ProtocolGateway  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(REPO, "config", "protocols")
DEFAULT_OUT = os.path.join(REPO, "config", "protocol_policies.generated.yaml")


def main() -> int:
    in_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    out_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT

    gw = ProtocolGateway(protocols_dir=in_dir)
    policy = gw.to_policy_yaml()
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(policy, f, allow_unicode=True, sort_keys=False)

    print(f"protocols: {len(gw.protocols)}")
    print(f"modules:   {gw.modules}")
    print(f"rules:     {len(gw.rules)}")
    print(f"written:   {out_path}")
    for p in gw.protocols:
        print(f"  - {p.module} [{p.level}] {p.category} | trigger={p.trigger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
