#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ci_smoke.py — CI 插件平台冒烟 (与 GitHub Actions 一致, 本地可复现)。
验证: 插件数 ≥7 / 依赖排序 / 生命周期冒烟。退出码 0=通过。"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.plugin_manager import PluginManager  # noqa: E402

pm = PluginManager(ROOT)
recs = pm.discover()
assert len(recs) >= 7, f"插件数 {len(recs)} < 7"
pm.resolve_order()
rep = pm.lifecycle_smoke()
assert rep["ok"], rep
print(f"[ci-smoke] OK: {len(recs)} 插件, 生命周期冒烟通过")
