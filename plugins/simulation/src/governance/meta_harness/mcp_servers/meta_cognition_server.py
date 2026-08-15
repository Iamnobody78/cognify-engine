# -*- coding: utf-8 -*-
"""meta_cognition_server.py — P1-3 MCP 服务器: 元认知封装.

对齐 angrysky56/meta-harness 的 advanced-reasoning MCP 服务器定位:
元认知监控、置信度追踪、假设检验。

封装 P0-V2 模块:
- hypotheses.jsonl: 假设命中率追踪 (置信度 = 命中/尝试)
- reasoning_chain (P1-1): 会话推理链查询
- meta_config (P2-V4): 门裁决状态查询

工具:
- hypothesis_stats      : 查询假设命中率/置信度
- reasoning_chain_query : 查询最新会话的推理链
- meta_config_status    : 查询 meta_config 门裁决配置与决策历史

启动: python -m mcp_servers.meta_cognition_server (stdio)
"""
import json
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("需要 MCP SDK: pip install mcp", file=sys.stderr)
    sys.exit(1)

META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HYPOTHESES = os.path.join(META_DIR, "experience", "hypotheses.jsonl")
SESSIONS = os.path.join(META_DIR, "experience", "sessions.jsonl")

mcp = FastMCP(
    "meta-cognition",
    instructions="BottleSumo 元认知: 假设置信度追踪 + 会话推理链 + 门裁决状态",
)


def _read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


@mcp.tool()
def hypothesis_stats(top_n: int = 10) -> str:
    """查询假设命中率/置信度统计 (P0-V2 置信度追踪).

    Args:
        top_n: 返回假设数 (按尝试次数排序取前 N)
    Returns:
        JSON: [{id, layer, target, attempts, hits, confidence, last_ts}]
    """
    hyps = _read_jsonl(HYPOTHESES)
    # 按 variant_id 聚合: 每条记录是一次尝试, outcome=confirmed 计为命中
    # (F-110 修复: 原实现按行输出, 从记录读不存在的 id/attempts/hits 字段
    #  -> 显示占位符; 现从记录结构派生)
    agg = {}
    for h in hyps:
        vid = h.get("variant_id") or h.get("id") or h.get("ts", "?")
        a = agg.setdefault(vid, {
            "id": vid, "layer": "?", "target": "",
            "attempts": 0, "hits": 0, "confidence": 0.0, "last_ts": "",
        })
        a["attempts"] += 1
        if h.get("layer"):
            a["layer"] = h["layer"]
        if h.get("target_file"):
            a["target"] = h["target_file"]
        if h.get("outcome") == "confirmed":
            a["hits"] += 1
        if h.get("ts", "") > a["last_ts"]:
            a["last_ts"] = h["ts"]
    out = list(agg.values())
    for a in out:
        a["confidence"] = round(a["hits"] / a["attempts"], 3) if a["attempts"] else 0.0
    out.sort(key=lambda x: (x["attempts"], x["confidence"]), reverse=True)
    return json.dumps(out[:top_n], ensure_ascii=False, indent=2)


@mcp.tool()
def reasoning_chain_query(latest_n: int = 1) -> str:
    """查询最近会话的完整推理链 (P1-1 reasoning_chain).

    Args:
        latest_n: 取最近 N 个会话
    Returns:
        JSON: [{session_id, ts, model, token_usage, tool_calls,
               reasoning_chain_steps}]
    """
    sess = _read_jsonl(SESSIONS)
    out = []
    for s in sess[-latest_n:]:
        chain = s.get("reasoning_chain", [])
        out.append({
            "session_id": s.get("session_id", ""),
            "ts": s.get("ts", ""),
            "model": s.get("model", ""),
            "token_usage": s.get("token_usage", {}),
            "tool_calls": s.get("tool_calls", []),
            "reasoning_chain_steps": [e.get("step") for e in chain],
            "scope_violations": next(
                (e for e in chain if e.get("step") == "scope_violations"), None),
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp.tool()
def meta_config_status() -> str:
    """查询 P2-V4 meta_config 门裁决配置与决策历史."""
    try:
        sys.path.insert(0, META_DIR)
        import meta_config as mc
        cfg = mc.load_meta_config()
        decisions = []
        dec_path = os.path.join(META_DIR, "meta_decisions.jsonl")
        if os.path.exists(dec_path):
            with open(dec_path, encoding="utf-8") as f:
                decisions = [json.loads(l) for l in f if l.strip()][-5:]
        return json.dumps({
            "config": cfg,
            "recent_decisions": decisions,
            "temperature_bounds": [0.1, 0.6],
            "threshold_bounds": [0.45, 0.90],
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
