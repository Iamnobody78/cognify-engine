#!/usr/bin/env python3
"""内存占用诊断: 列出 top 内存进程。"""
import subprocess

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process | Sort-Object WS -Descending | Select-Object -First 12 "
     "| ForEach-Object { '{0,8} {1,10:N1}MB {2}' -f $_.Id, "
     "($_.WS/1MB), $_.ProcessName }"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    timeout=40)
print(out.stdout or "(none)")
print(out.stderr[:400] if out.stderr else "")
