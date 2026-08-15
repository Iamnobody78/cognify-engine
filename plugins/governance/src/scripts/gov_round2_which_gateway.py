# -*- coding: utf-8 -*-
"""Which gateway answers? A6 (UPDATE no WHERE) via IPv4 vs IPv6 loopback."""
import sys, json, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def probe(base, sql):
    req = urllib.request.Request(f"{base}/v1/chat/completions",
                                 data=json.dumps({"model": "gpt-4o",
                                                  "messages": [{"role": "user", "content": "run query"}],
                                                  "sql": {"query": sql}}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, resp.read().decode("utf-8", errors="replace")[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:300]

for base in ["http://127.0.0.1:9000", "http://[::1]:9000", "http://localhost:9000"]:
    for label, sql in [("A1 DELETE", "DELETE FROM users;"), ("A6 UPDATE-nowhere", "UPDATE users SET active=0;")]:
        try:
            st, body = probe(base, sql)
            v = "DENY" if "governance_denied" in body else "ALLOW"
            print(f"{base:<26} {label:<18} -> {st} {v}  {body[:120]}")
        except Exception as e:
            print(f"{base:<26} {label:<18} -> EXC {e}")
    print()
