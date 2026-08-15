# -*- coding: utf-8 -*-
"""mcp_client.py — Sprint 11: MCP 服务器集成客户端. (Sprint 13 A2: 使用监控)

将三台 MCP 服务器 (mcp_servers/) 封装为进程内可调用的异步客户端,
供 outer_loop 主循环在 code_agent 提议前获取增强上下文:

- env_snapshot()      : environment_bootstrap.environment_snapshot
- semantic_search()   : semantic_retrieval.semantic_search
- meta_config()       : meta_cognition.meta_config_status
- hypothesis_stats()  : meta_cognition.hypothesis_stats
- reasoning_chain()   : meta_cognition.reasoning_chain_query
- check_write_scope() : environment_bootstrap.check_write_scope

设计: 直接复用 mcp_servers 的 FastMCP 实例 (in-process call_tool),
避免 stdio 子进程开销; 保持 MCP 协议语义 (工具即接口), 未来可平滑
切换为远程 stdio/streamable-http 连接。

Sprint 13 A2 使用监控: 每次 _call 记录 {ts, server, tool, args, duration_ms,
status, error} 追加到 MCP_USAGE_REPORT (mcp_usage_report.jsonl), 供 A4 分析
工具使用分布/成功率/延迟。
"""
import json
import os
import sys
import threading
import time

META_DIR = os.path.dirname(os.path.abspath(__file__))
if META_DIR not in sys.path:
    sys.path.insert(0, META_DIR)

# A2: 使用监控报告路径 (与 mcp_client.py 同目录)
MCP_USAGE_REPORT = os.path.join(META_DIR, "mcp_usage_report.jsonl")
_MCP_LOCK = threading.Lock()
_MAX_ARG_CHARS = 200  # args 序列化截断, 避免日志膨胀


def _log_usage(server: str, tool: str, args: dict, duration_ms: float,
               status: str, error: str = ""):
    """A2: 追加一条使用记录到 mcp_usage_report.jsonl (线程安全)."""
    import datetime
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="milliseconds"),
        "server": server,
        "tool": tool,
        "args": json.dumps(args, ensure_ascii=False, default=str)[:_MAX_ARG_CHARS],
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "error": error[:300] if error else "",
    }
    try:
        with _MCP_LOCK:
            with open(MCP_USAGE_REPORT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # 记录失败不阻塞调用
        print(f"[mcp_client] usage log failed: {e}", file=sys.stderr)


def read_usage_report(limit: int = 0) -> list:
    """A2: 读取使用监控报告 (供 A4 分析). limit=0 读全部."""
    if not os.path.exists(MCP_USAGE_REPORT):
        return []
    recs = []
    with open(MCP_USAGE_REPORT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs[-limit:] if limit > 0 else recs


class MCPServerError(RuntimeError):
    """MCP 调用失败 (服务器未就绪/工具异常)."""


def _call(mcp_mod_name: str, tool: str, args: dict):
    """同步包装: 进程内调用 FastMCP.call_tool (跑 asyncio 事件循环)."""
    import asyncio
    t0 = time.perf_counter()

    def _do():
        import importlib
        mod = importlib.import_module(f"mcp_servers.{mcp_mod_name}")
        r = asyncio.run(mod.mcp.call_tool(tool, args))
        content = r[0][0] if isinstance(r, tuple) else r.content[0]
        return json.loads(content.text)

    try:
        result = _do()
        _log_usage(mcp_mod_name, tool, args,
                   (time.perf_counter() - t0) * 1000.0, "ok")
        return result
    except Exception as e:
        _log_usage(mcp_mod_name, tool, args,
                   (time.perf_counter() - t0) * 1000.0, "error", str(e))
        raise MCPServerError(f"[mcp:{mcp_mod_name}:{tool}] {e}") from e


def env_snapshot() -> dict:
    """环境引导: 采集当前环境快照 (对齐 Terminal-Bench 2.0)."""
    return _call("environment_bootstrap_server", "environment_snapshot", {})


def semantic_search(query: str, top_k: int = 3, min_score: float = 0.45) -> dict:
    """语义检索: bge-m3 三源血缘检索."""
    return _call("semantic_retrieval_server", "semantic_search",
                 {"query": query, "top_k": top_k, "min_score": min_score})


def meta_config() -> dict:
    """元认知: 查询 P2-V4 门裁决配置与决策历史."""
    return _call("meta_cognition_server", "meta_config_status", {})


def hypothesis_stats(top_n: int = 10) -> list:
    """元认知: 查询假设命中率/置信度."""
    return _call("meta_cognition_server", "hypothesis_stats", {"top_n": top_n})


def reasoning_chain(latest_n: int = 1) -> list:
    """元认知: 查询最近会话推理链."""
    return _call("meta_cognition_server", "reasoning_chain_query",
                 {"latest_n": latest_n})


def check_write_scope(target_file: str) -> dict:
    """环境引导: 写作用域校验 (越权拒绝)."""
    return _call("environment_bootstrap_server", "check_write_scope",
                 {"target_file": target_file})


def build_mcp_context(query: str = "") -> dict:
    """聚合三服务器上下文 (供 propose 注入系统提示).

    Returns:
        {"env_snapshot": {...}, "meta_config": {...},
         "top_hypotheses": [...], "retrieved": {...}}
    任一服务器失败时, 该字段置 None 并记 warning, 不阻塞主流程 (容错降级).
    """
    ctx = {"env_snapshot": None, "meta_config": None,
           "top_hypotheses": None, "retrieved": None}
    for name, fn in [
        ("env_snapshot", lambda: env_snapshot()),
        ("meta_config", lambda: meta_config()),
        ("top_hypotheses", lambda: hypothesis_stats(top_n=5)),
    ]:
        try:
            ctx[name] = fn()
        except MCPServerError as e:
            print(f"[mcp_client] {name} 降级: {e}", file=sys.stderr)
    if query:
        try:
            ctx["retrieved"] = semantic_search(query, top_k=3)
        except MCPServerError as e:
            print(f"[mcp_client] retrieved 降级: {e}", file=sys.stderr)
    return ctx


def format_mcp_context(ctx: dict, max_chars: int = 600) -> str:
    """将 MCP 上下文压缩为注入文本 (控制 prompt 体积)."""
    lines = ["MCP 增强上下文:"]
    if ctx.get("env_snapshot"):
        s = ctx["env_snapshot"]
        ok = [os.path.basename(p) for p in s.get("harness_files_ready", [])]
        lines.append(f"- env: python={s.get('python')} git={s.get('git_head')} "
                     f"disk_free={s.get('disk_free_gb')}G harness={len(ok)}/5")
    if ctx.get("meta_config"):
        c = ctx["meta_config"].get("config", {})
        lines.append(f"- meta_config: temp={c.get('temperature')} "
                     f"thr={c.get('retrieval_threshold')} "
                     f"target={c.get('target_priority')}")
    if ctx.get("top_hypotheses"):
        hyps = ctx["top_hypotheses"][:3]
        parts = []
        for h in hyps:
            parts.append(f"{h.get('id')}(conf={h.get('confidence')},"
                         f"att={h.get('attempts')})")
        lines.append(f"- 高置信假设: {', '.join(parts) if parts else '无'}")
    if ctx.get("retrieved"):
        r = ctx["retrieved"]
        lines.append(f"- 语义检索: {r.get('hits', 0)} 命中 "
                     f"(score={[(x['source'], x['score']) for x in r.get('results', [])[:2]]})")
    txt = "\n".join(lines)
    return txt[:max_chars]
