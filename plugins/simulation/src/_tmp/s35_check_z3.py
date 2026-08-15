#!/usr/bin/env python3
# S35: 检查 z3-solver 是否可用
try:
    import z3
    print("z3-solver OK:", z3.get_version_string())
except ImportError as e:
    print("z3-solver NOT INSTALLED:", e)
