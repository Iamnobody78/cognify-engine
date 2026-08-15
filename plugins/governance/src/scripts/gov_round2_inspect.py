# -*- coding: utf-8 -*-
"""GOV Round 2 step 0: inspect decision response structure for SQL probes."""
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
        return e.code, e.read().decode("utf-8", errors="replace")

for label, sql in [("mal DELETE", "DELETE FROM users;"), ("ben SELECT", "SELECT * FROM users WHERE id=1;")]:
    st, d = post("/v1/chat/completions", {"model": "gpt-4o",
                 "messages": [{"role": "user", "content": "run query"}],
                 "sql": {"query": sql}})
    print(f"== {label} [{sql}] -> {st}")
    print(json.dumps(d, ensure_ascii=False, indent=1)[:1500])
    print()
