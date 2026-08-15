#!/usr/bin/env python3
"""诊断: 列出 ollama/python 进程的 CPU 时间与内存, 定位负载源。"""
import subprocess

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Process | Where-Object {$_.ProcessName -match 'ollama|python'} "
     "| ForEach-Object { '{0} {1} {2} {3}' -f $_.Id, $_.ProcessName, "
     "$_.CPU, [math]::Round($_.WS/1MB,0) }"],
    capture_output=True, text=True, encoding="utf-8", errors="replace")
print("=== PROCESSES ===")
print(out.stdout or "(none)")
print(out.stderr[:500] if out.stderr else "")

# CPU 总负载
out2 = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "(Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue"],
    capture_output=True, text=True, encoding="utf-8", errors="replace")
print("=== CPU LOAD % ===")
print(out2.stdout.strip() or out2.stderr[:200])
