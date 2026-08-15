# -*- coding: utf-8 -*-
"""Sprint 13 A3 试点场景 ③: 报告生成器 — meta_cognition 汇总假设命中率

场景: 报告生成器在迭代结束时汇总历史假设统计 (hypothesis_stats) 与
最近推理链 (reasoning_chain_query), 生成迭代摘要报告。
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = "http://127.0.0.1:18010/mcp"
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


def call(tool, args):
    sid, _ = rpc("", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-03-26",
                                 "capabilities": {},
                                 "clientInfo": {"name": "s13-pilot-report",
                                                "version": "1"}}})
    rpc(sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    sid, body = rpc(sid, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": tool, "arguments": args}})
    res = parse(body).get("result", parse(body))
    content = res.get("content", []) if isinstance(res, dict) else []
    text = " ".join(c.get("text", "") for c in content
                    if isinstance(c, dict)) if isinstance(content, list) else str(res)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:300]}


def main():
    stats = call("hypothesis_stats", {"top_n": 5})
    chain = call("reasoning_chain_query", {"latest_n": 3})
    cfg = call("meta_config_status", {})

    print("[hypothesis_stats]")
    print(" ", json.dumps(stats, ensure_ascii=False)[:400])
    print("[reasoning_chain (latest 3)]")
    print(" ", json.dumps(chain, ensure_ascii=False)[:400])
    print("[meta_config_status]")
    print(" ", json.dumps(cfg, ensure_ascii=False)[:300])

    # 汇总: 假设命中率 (hypothesis_stats 返回列表, 每条含 attempts/hits)
    if isinstance(stats, list) and stats:
        total_attempts = sum(h.get("attempts", 0) for h in stats)
        total_hits = sum(h.get("hits", 0) for h in stats)
        active = sum(1 for h in stats if h.get("attempts", 0) > 0)
        if total_attempts:
            rate = total_hits / total_attempts
            print(f"\n[summary] hypotheses={len(stats)} active={active} "
                  f"attempts={total_attempts} hits={total_hits} "
                  f"hit_rate={rate:.1%}")
        else:
            print(f"\n[summary] hypotheses={len(stats)} active={active} "
                  f"(无已评估假设, attempts=0)")
    else:
        print(f"\n[summary] {stats}")

    ok = isinstance(stats, list) and isinstance(chain, (list, dict)) and len(stats) > 0
    print("\nSCENARIO3_RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
