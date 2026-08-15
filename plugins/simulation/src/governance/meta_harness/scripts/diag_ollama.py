#!/usr/bin/env python3
"""轻量诊断: ollama 驻留状态 + 负载探测 (纯 python, 无 shell 转义问题)。"""
import json
import time
import urllib.request

def get(url, timeout=12):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

print("=== ollama /api/ps ===")
ps = get("http://127.0.0.1:11434/api/ps")
if "models" in ps:
    for m in ps["models"]:
        print(f"  {m['name']} size={m['size']/1e9:.1f}GB "
              f"expires={m.get('expires_at','')}")
else:
    print(" ", ps)

print("=== 轻量探针: qwen2.5:7b 文本 (非VL) 延迟 ===")
t0 = time.time()
try:
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({"model": "qwen2.5:7b", "prompt": "ok",
                         "stream": False}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    print(f"  qwen2.5:7b 文本 OK wall={time.time()-t0:.1f}s "
          f"total={d.get('total_duration',0)/1e9:.1f}s")
except Exception as e:
    print(f"  qwen2.5:7b FAIL wall={time.time()-t0:.1f}s {type(e).__name__}: {e}")

print("=== 空闲等待 10s 后 CPU 感知 (Get-Process 采样) ===")
time.sleep(10)
try:
    import subprocess
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process ollama,ollama_llama_server -ErrorAction SilentlyContinue "
         "| ForEach-Object { '{0} {1} CPU={2}' -f $_.Id, $_.ProcessName, "
         "$_.CPU }"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=25)
    print(out.stdout or "(no ollama procs)")
except Exception as e:
    print(f"  proc query FAIL: {e}")
