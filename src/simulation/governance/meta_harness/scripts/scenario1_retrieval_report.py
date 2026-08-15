# -*- coding: utf-8 -*-
"""Sprint 13 A3 试点场景 ①: 数据分析脚本 — semantic_retrieval 检索历史实验报告

场景: 数据分析流水线需要为新一轮实验检索历史结论 (grip decay 相关),
通过 HTTP 调用 semantic_retrieval 服务器, 将命中结果组织成检索报告。
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = "http://127.0.0.1:18011/mcp"
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
        return {"error": "no data event"}
    return json.loads(body)


def search(query, top_k=3):
    sid, _ = rpc("", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-03-26",
                                 "capabilities": {},
                                 "clientInfo": {"name": "s13-pilot-ds",
                                                "version": "1"}}})
    rpc(sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    sid, body = rpc(sid, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": "semantic_search",
                                     "arguments": {"query": query,
                                                   "top_k": top_k}}})
    res = parse(body).get("result", parse(body))
    return res


def main():
    queries = [
        "grip decay fallback strategy",
        "pareto frontier 214 steps",
    ]
    report = {"scenario": "pilot-1: historical report retrieval",
              "queries": [], "hits_total": 0}
    for q in queries:
        res = search(q, top_k=2)
        content = res.get("content", []) if isinstance(res, dict) else []
        text = " ".join(c.get("text", "") for c in content
                        if isinstance(c, dict)) if isinstance(content, list) else str(res)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"raw": text[:300]}
        hits = payload if isinstance(payload, list) else payload.get("results", payload.get("hits", []))
        report["queries"].append({"query": q, "hits": hits})
        report["hits_total"] += len(hits) if isinstance(hits, list) else 0
        print(f"[query] {q}")
        if isinstance(hits, list):
            for h in hits:
                if isinstance(h, dict):
                    print(f"  - {h.get('source','?')} score={h.get('score','?'):.4f}" if isinstance(h.get('score'), (int, float)) else f"  - {h}")
                else:
                    print(f"  - {str(h)[:120]}")
        else:
            print(f"  {str(hits)[:200]}")
    print("\nSCENARIO1_RESULT:", "PASS" if report["hits_total"] > 0 else "FAIL")
    sys.exit(0 if report["hits_total"] > 0 else 1)


if __name__ == "__main__":
    main()
