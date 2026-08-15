"""T-03..T-10: API integration tests against seeded in-memory DB."""
from __future__ import annotations

import json
from pathlib import Path

USAGE_LOG = (
    Path(__file__).resolve().parent.parent.parent.parent / "meta_harness" / "mcp_usage_report.jsonl"
)


def _usage_records() -> list[dict]:
    recs = []
    with open(USAGE_LOG, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                recs.append(json.loads(line))
    return recs


def test_ping(client):
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_returns_three_servers(client):
    """T-03: exactly 3 servers with complete fields."""
    r = client.get("/api/health")
    assert r.status_code == 200
    servers = r.json()["servers"]
    assert len(servers) == 3
    names = {s["name"] for s in servers}
    assert names == {
        "meta_cognition_server",
        "semantic_retrieval_server",
        "environment_bootstrap_server",
    }
    for s in servers:
        assert {"name", "calls", "ok", "error", "success_rate", "avg_ms", "p95_ms"} <= set(s)


def test_health_success_rate(client):
    """T-04: per-server success rate matches raw jsonl status counts."""
    recs = _usage_records()
    expected: dict[str, tuple[int, int]] = {}
    for r in recs:
        ok, err = expected.get(r["server"], (0, 0))
        if r["status"] == "ok":
            ok += 1
        else:
            err += 1
        expected[r["server"]] = (ok, err)

    servers = {s["name"]: s for s in client.get("/api/health").json()["servers"]}
    for name, (ok, err) in expected.items():
        s = servers[name]
        assert s["ok"] == ok and s["error"] == err
        assert abs(s["success_rate"] - ok / (ok + err)) < 1e-5


def test_usage_summary_counts(client):
    """T-05: summary total/ok/error align with source."""
    recs = _usage_records()
    r = client.get("/api/usage/summary")
    assert r.status_code == 200
    s = r.json()
    assert s["total_calls"] == len(recs)
    assert s["ok"] == sum(1 for x in recs if x["status"] == "ok")
    assert s["error"] == sum(1 for x in recs if x["status"] != "ok")
    assert s["p95_ms"] >= s["min_ms"]
    assert s["max_ms"] >= s["avg_ms"]


def test_usage_summary_by_tool(client):
    """T-06: by_tool contains expected tools from the log."""
    s = client.get("/api/usage/summary").json()
    tools = {t["tool"] for t in s["by_tool"]}
    assert "hypothesis_stats" in tools
    assert "semantic_search" in tools
    assert "environment_snapshot" in tools


def test_usage_latency_outliers(client):
    """T-07: outliers include slow calls AND error records."""
    recs = _usage_records()
    slow_count = sum(1 for x in recs if x["duration_ms"] > 2000 or x["status"] != "ok")
    r = client.get("/api/usage/latency", params={"threshold": 2000})
    assert r.status_code == 200
    outliers = r.json()
    assert len(outliers) == slow_count
    # nonexistent_tool error must be present
    assert any(o["status"] != "ok" for o in outliers)


def test_hypotheses_summary_aggregation(client):
    """T-08: ca_rules_01 aggregates 39 attempts with confidence hits/attempts."""
    r = client.get("/api/hypotheses/summary")
    assert r.status_code == 200
    variants = {v["variant_id"]: v for v in r.json()["variants"]}
    assert "ca_rules_01" in variants
    v = variants["ca_rules_01"]
    assert v["attempts"] == 39
    assert v["confidence"] is not None and 0.0 <= v["confidence"] <= 1.0
    assert v["hits"] <= v["attempts"]


def test_hypotheses_trend_order(client):
    """T-09: trend sorted by ts, cumulative_attempts monotonic non-decreasing."""
    r = client.get("/api/hypotheses/trend")
    assert r.status_code == 200
    trend = r.json()["trend"]
    assert trend
    tss = [t["ts"] for t in trend]
    assert tss == sorted(tss)
    # per-variant cumulative attempts must be monotonic
    prev: dict[str, int] = {}
    for t in trend:
        prev_attempts = prev.get(t["variant_id"], 0)
        assert t["cumulative_attempts"] >= prev_attempts
        prev[t["variant_id"]] = t["cumulative_attempts"]


def test_api_error_handling(client):
    """T-10: unknown route -> 404; invalid bucket -> 422."""
    assert client.get("/api/nonexistent").status_code == 404
    r = client.get("/api/usage/timeline", params={"bucket": "invalid"})
    assert r.status_code == 422


def test_timeline_day_buckets(client):
    """Timeline day buckets are non-empty and errors bucket is sane."""
    r = client.get("/api/usage/timeline", params={"bucket": "day"})
    assert r.status_code == 200
    buckets = r.json()
    assert buckets
    total = sum(b["calls"] for b in buckets)
    assert total == len(_usage_records())
