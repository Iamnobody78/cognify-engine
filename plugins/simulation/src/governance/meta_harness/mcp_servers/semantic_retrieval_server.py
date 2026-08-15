# -*- coding: utf-8 -*-
"""semantic_retrieval_server.py — P1-3 MCP 服务器: 语义检索封装.

对齐 project-synapse MCP 服务器定位: Wiki & Neo4j 语义索引知识检索。
P1-V3 的 bge-m3 本地检索是其等价物, 本服务器将其封装为标准 MCP 接口。

封装 semantic_retriever.py:
- retrieve(query, top_k, min_score): 三源血缘检索 (failure_analysis /
  pareto_frontier / hypotheses)
- format_experience(hits): 压缩注入文本

工具:
- semantic_search   : 语义检索历史经验 (bge-m3 嵌入, 余弦相似度)
- index_status      : 检索索引状态 (源文件 mtime / 缓存块数)

启动: python -m mcp_servers.semantic_retrieval_server (stdio)
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
sys.path.insert(0, META_DIR)

mcp = FastMCP(
    "semantic-retrieval",
    instructions="BottleSumo 语义检索: bge-m3 嵌入 + 三源血缘检索 (bge-m3:latest)",
)


@mcp.tool()
def semantic_search(query: str, top_k: int = 3, min_score: float = 0.45) -> str:
    """语义检索历史经验 (bge-m3 嵌入, 余弦相似度).

    Args:
        query: 检索查询 (聚焦问题描述/目标文件)
        top_k: 返回命中数 (默认 3)
        min_score: 最低相似度阈值 (默认 0.45)
    Returns:
        JSON: [{source, score, text(excerpt), chunk_id}]
    """
    try:
        from semantic_retriever import format_experience, retrieve
    except ImportError as e:
        return json.dumps({"error": f"semantic_retriever 不可用: {e}"})
    try:
        hits = retrieve(query, top_k=top_k, min_score=min_score)
        # 过滤规则语法块 (与 code_agent_proposer 一致, 防注入带偏)
        hits = [h for h in hits
                if "sensor(" not in h["text"] and "TIMESTEP" not in h["text"]
                and ".abdl" not in h["text"]]
        return json.dumps({
            "query": query,
            "hits": len(hits),
            "results": [{
                "source": h.get("source", "?"),
                "score": round(h.get("score", 0), 4),
                "chunk_id": h.get("chunk_id", h.get("id", "")),
                "text_excerpt": h["text"][:200],
            } for h in hits],
            "formatted_experience": format_experience(hits)[:400],
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def index_status() -> str:
    """查询语义检索索引状态 (源文件 mtime / 缓存块数 / 失效检测)."""
    try:
        from semantic_retriever import CACHE_PATH, SOURCES
        import time
        cache_mtime = None
        n_blocks = 0
        if os.path.exists(CACHE_PATH):
            cache_mtime = time.strftime(
                "%Y%m%d_%H%M%S", time.localtime(os.path.getmtime(CACHE_PATH)))
            try:
                with open(CACHE_PATH, encoding="utf-8") as f:
                    n_blocks = len(json.load(f).get("blocks", []))
            except Exception:
                pass
        srcs = {}
        for name, path in SOURCES.items():
            srcs[name] = {
                "exists": os.path.exists(path),
                "mtime": time.strftime(
                    "%Y%m%d_%H%M%S", time.localtime(os.path.getmtime(path)))
                if os.path.exists(path) else None,
            }
        return json.dumps({
            "embed_model": "bge-m3:latest",
            "cache_path": CACHE_PATH,
            "cache_mtime": cache_mtime,
            "cached_blocks": n_blocks,
            "sources": srcs,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
