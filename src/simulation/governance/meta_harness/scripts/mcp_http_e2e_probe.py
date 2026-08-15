# -*- coding: utf-8 -*-
"""Sprint 13 A1 验收: Windows 主环境 HTTP 端到端 MCP 会话"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

TARGETS = [
    ("meta_cognition", "http://127.0.0.1:18010/mcp"),
    ("semantic_retrieval", "http://127.0.0.1:18011/mcp"),
    ("environment_bootstrap", "http://127.0.0.1:18012/mcp"),
]
HEADERS = {"Content-Type": "application/json",
           "Accept": "application/json, text/event-stream"}


def rpc(url, sid, payload, timeout=30):
    hh = dict(HEADERS)
    if sid:
        hh["Mcp-Session-Id"] = sid
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=hh, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.headers.get("Mcp-Session-Id", sid), resp.read().decode()


def parse(body):
    if body.startswith("event:"):
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {"error": "no data event"}
    return json.loads(body)


def call_tool(url, sid, name, args, timeout=60):
    return rpc(url, sid, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": name, "arguments": args}},
               timeout=timeout)


def main():
    ok = True
    for name, url in TARGETS:
        print(f"===== {name} =====")
        try:
            sid, body = rpc(url, "", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                      "params": {"protocolVersion": "2025-03-26",
                                                 "capabilities": {},
                                                 "clientInfo": {"name": "s13-accept", "version": "1"}}})
            init = parse(body)
            print("  [init ]", json.dumps(init.get("result", init), ensure_ascii=False)[:120])
            rpc(url, sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            sid2, body2 = rpc(url, sid, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = parse(body2)
            names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
            print(f"  [tools] {len(names)}: {', '.join(names)}")
            # 每台执行一个代表性工具
            sid2, body3 = call_tool(url, sid2, names[0], {})
            res = parse(body3)
            r = res.get("result", res)
            content = r.get("content", []) if isinstance(r, dict) else []
            text = " ".join(c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list) else str(r)
            print(f"  [call ] {names[0]} -> {text[:200]}")
        except Exception as e:
            ok = False
            print(f"  [FAIL ] {type(e).__name__}: {e}")
        print()
    # semantic_retrieval 真实参数调用 (bge-m3)
    print("===== semantic_search (real query) =====")
    try:
        url = "http://127.0.0.1:18011/mcp"
        sid, _ = rpc(url, "", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2025-03-26",
                                          "capabilities": {},
                                          "clientInfo": {"name": "s13-accept", "version": "1"}}})
        rpc(url, sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        sid2, body = call_tool(url, sid, "semantic_search",
                               {"query": "grip decay fallback", "top_k": 2})
        res = parse(body)
        r = res.get("result", res)
        content = r.get("content", []) if isinstance(r, dict) else []
        text = " ".join(c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list) else str(r)
        print("  RESULT:", text[:500])
        if not text or "error" in text.lower():
            ok = False
    except Exception as e:
        ok = False
        print(f"  [FAIL ] {type(e).__name__}: {e}")
    print()
    print("E2E_RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
