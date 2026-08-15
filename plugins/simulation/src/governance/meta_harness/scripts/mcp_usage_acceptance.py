# -*- coding: utf-8 -*-
"""Sprint 13 A2 验收: 使用监控采集 — 模拟 12 次外部调用覆盖三服务器全部工具.

覆盖: meta_cognition(3) + semantic_retrieval(2) + environment_bootstrap(3)
     = 8 个工具, 含 1 次故意失败 (非法 write_scope) 以记录 error 状态.
验收标准: mcp_usage_report.jsonl >= 10 条, 含工具/参数/耗时/返回状态.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
META_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, META_DIR)

import mcp_client  # noqa: E402

# (server, tool, callable, kwargs, expect_error)
CALLS = [
    ("meta_cognition", "hypothesis_stats", mcp_client.hypothesis_stats, {"top_n": 5}, False),
    ("meta_cognition", "meta_config_status", mcp_client.meta_config, {}, False),
    ("meta_cognition", "reasoning_chain_query", mcp_client.reasoning_chain, {"latest_n": 2}, False),
    ("semantic_retrieval", "semantic_search", mcp_client.semantic_search, {"query": "grip decay fallback", "top_k": 2}, False),
    ("semantic_retrieval", "semantic_search", mcp_client.semantic_search, {"query": "mcp integration", "top_k": 3}, False),
    ("environment_bootstrap", "environment_snapshot", mcp_client.env_snapshot, {}, False),
    ("environment_bootstrap", "check_write_scope", mcp_client.check_write_scope, {"target_file": "governance/meta_harness/meta_config.py"}, False),
    ("environment_bootstrap", "check_write_scope", mcp_client.check_write_scope, {"target_file": "../outside_scope.txt"}, False),  # 越权: 返回 allowed=false (非异常, 安全语义)
    ("meta_cognition", "hypothesis_stats", mcp_client.hypothesis_stats, {"top_n": 3}, False),
    ("semantic_retrieval", "semantic_search", mcp_client.semantic_search, {"query": "pareto frontier", "top_k": 1}, False),
    ("environment_bootstrap", "environment_snapshot", mcp_client.env_snapshot, {}, False),
    ("meta_cognition", "meta_config_status", mcp_client.meta_config, {}, False),
]

ok = err = 0
for server, tool, fn, kwargs, expect_err in CALLS:
    try:
        r = fn(**kwargs)
        ok += 1
        # 越权场景: 校验 allowed=false 语义
        if tool == "check_write_scope" and isinstance(r, dict) and r.get("allowed") is False:
            print(f"  [ok  ] {server}.{tool} -> allowed=false (越权拒绝语义正确)")
        else:
            print(f"  [ok  ] {server}.{tool}")
    except Exception as e:
        err += 1
        tag = "EXPECT-ERR" if expect_err else "FAIL"
        print(f"  [{tag}] {server}.{tool}: {type(e).__name__}: {e}")

# 第 13 条: 故意调用不存在工具 -> 真实 error 记录
try:
    mcp_client._call("semantic_retrieval_server", "nonexistent_tool", {})
    print("  [FAIL] nonexistent_tool 未抛错")
except Exception as e:
    err += 1
    print(f"  [EXPECT-ERR] semantic_retrieval.nonexistent_tool: {type(e).__name__}")

recs = mcp_client.read_usage_report()
print(f"\nusage report: {len(recs)} records")
print(f"ok={ok} err={err}")
statuses = {}
for r in recs:
    statuses[r["status"]] = statuses.get(r["status"], 0) + 1
print(f"statuses: {statuses}")
tools = {}
for r in recs:
    tools[r["tool"]] = tools.get(r["tool"], 0) + 1
print(f"tools: {tools}")
durations = [r["duration_ms"] for r in recs]
print(f"duration_ms: min={min(durations):.1f} max={max(durations):.1f} "
      f"avg={sum(durations)/len(durations):.1f}")
has_err_rec = any(r["status"] == "error" for r in recs)
print("A2_ACCEPT:", "PASS" if len(recs) >= 10 and has_err_rec else "FAIL")
