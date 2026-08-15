# -*- coding: utf-8 -*-
"""GOV-EVOLVE Round 1 v2: correct request formats - SQL field + non-shell tool names."""
import sys, json, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:9000"

def post(path, body):
    req = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:500]

def chat(body):
    return post("/v1/chat/completions", body)

# 1. MALICIOUS SQL: DELETE without WHERE
st, d = chat({"model": "gpt-4o", "messages": [{"role": "user", "content": "run query"}],
              "sql": {"query": "DELETE FROM users;"}})
print(f"[MAL SQL DELETE no-WHERE] {st}")
print(json.dumps(d, ensure_ascii=False)[:400])

# 2. BENIGN SQL: SELECT
st2, d2 = chat({"model": "gpt-4o", "messages": [{"role": "user", "content": "query"}],
                "sql": {"query": "SELECT * FROM users WHERE id=1;"}})
print(f"\n[BEN SQL SELECT] {st2}")
print(json.dumps(d2, ensure_ascii=False)[:400])

# 3. BENIGN chat only (no sql, no tools)
st3, d3 = chat({"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]})
print(f"\n[BEN chat] {st3}")
print(json.dumps(d3, ensure_ascii=False)[:400])

# 4. Tool call with NON-shell tool (calculator style, allowed name)
st4, d4 = chat({"model": "gpt-4o", "messages": [{"role": "user", "content": "calc 2+2"}],
                "tools": [{"type": "function", "function": {"name": "math_calculator", "parameters": {"type": "object", "properties": {"expr": {"type": "string"}}}}}],
                "tool_choice": "auto"})
print(f"\n[BEN tool math_calculator] {st4}")
print(json.dumps(d4, ensure_ascii=False)[:400])

# 5. Traces
try:
    tr = urllib.request.urlopen(f"{BASE}/v1/traces?limit=10", timeout=10).read().decode("utf-8", errors="replace")
    print(f"\n=== TRACES ===")
    print(tr[:1000])
except Exception as e:
    print("\ntraces:", e)
