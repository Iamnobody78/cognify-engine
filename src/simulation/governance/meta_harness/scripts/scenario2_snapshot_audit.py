# -*- coding: utf-8 -*-
"""Sprint 13 A3 试点场景 ②: 治理审计脚本 — environment_bootstrap 检查快照一致性

场景: 治理审计在 Sprint 边界执行快照一致性检查: 取环境快照 (repo_root/
python/model/git_head), 与本地 git HEAD 交叉验证, 输出审计结论。
"""
import json
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = "http://127.0.0.1:18012/mcp"
HEADERS = {"Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}


def rpc(sid, payload, timeout=30):
    hh = dict(HEADERS)
    if sid:
        hh["Mcp-Session-Id"] = sid
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers=hh, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers.get("Mcp-Session-Id", sid), r.read().decode()


def parse(body):
    if body.startswith("event:"):
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return json.loads(body)


def main():
    sid, _ = rpc("", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-03-26",
                                 "capabilities": {},
                                 "clientInfo": {"name": "s13-pilot-audit",
                                                "version": "1"}}})
    rpc(sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    sid, body = rpc(sid, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": "environment_snapshot",
                                     "arguments": {}}})
    res = parse(body).get("result", parse(body))
    content = res.get("content", []) if isinstance(res, dict) else []
    text = " ".join(c.get("text", "") for c in content
                    if isinstance(c, dict)) if isinstance(content, list) else str(res)
    try:
        snap = json.loads(text)
    except json.JSONDecodeError:
        snap = {"raw": text[:300]}

    print("[snapshot from MCP]")
    for k, v in snap.items():
        print(f"  {k}: {str(v)[:120]}")

    # 本地交叉验证: git HEAD
    local_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704"
    ).stdout.strip()
    print(f"[local git HEAD] {local_head[:12]}")

    snap_head = snap.get("git_head", "")
    # MCP 快照存短哈希(7位), 本地为完整哈希(12位) -> 本地应 startswith 快照
    match = bool(snap_head) and local_head.startswith(snap_head)
    print(f"[consistency] MCP git_head={snap_head} vs local={local_head[:12]} "
          f"-> {'MATCH' if match else 'MISMATCH'}")
    # 关键字段完整性检查
    required = ["repo_root", "python", "model", "git_head"]
    missing = [k for k in required if k not in snap]
    print(f"[fields] required={required} missing={missing or 'none'}")
    ok = match and not missing
    print("\nSCENARIO2_RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
