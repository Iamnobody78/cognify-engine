#!/usr/bin/env python3
# S35: 检查现有依赖状态
import sys
mods = ["numpy", "yaml", "gym"]
for m in mods:
    try:
        mod = __import__(m)
        v = getattr(mod, "__version__", "?")
        print(f"{m}: OK ({v})")
    except ImportError as e:
        print(f"{m}: MISSING ({e})")
print("python:", sys.version)
