#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pytest 子进程运行器: 输出直接写文件, 无管道"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent  # 自定位 (cognify-engine plugins/governance/src)
OUT = Path(r"C:\Users\ivy\.aionui-tri-sync\debt\pytest_full_20260815.txt")

args = sys.argv[1:] or ["tests/", "-q", "--tb=line", "--no-header"]
with open(OUT, "w", encoding="utf-8", errors="replace") as f:
    r = subprocess.run([sys.executable, "-m", "pytest", *args],
                       stdout=f, stderr=subprocess.STDOUT, cwd=str(REPO))
print(f"exit={r.returncode} output={OUT} ({OUT.stat().st_size} bytes)")
sys.exit(r.returncode)
