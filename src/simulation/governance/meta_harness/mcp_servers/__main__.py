# -*- coding: utf-8 -*-
"""mcp_servers 统一启动入口 (P1-3).

用法:
  python -m mcp_servers --server meta_cognition          # stdio (默认)
  python -m mcp_servers --server semantic_retrieval
  python -m mcp_servers --server environment_bootstrap
  python -m mcp_servers --server all                     # 依次验证 import + 工具注册
  python -m mcp_servers --server meta_cognition --transport streamable-http

每个服务器暴露标准 list_tools / call_tool 接口 (FastMCP)。
"""
import argparse
import asyncio
import sys


def _build(name: str):
    if name == "meta_cognition":
        from mcp_servers.meta_cognition_server import mcp
    elif name == "semantic_retrieval":
        from mcp_servers.semantic_retrieval_server import mcp
    elif name == "environment_bootstrap":
        from mcp_servers.environment_bootstrap_server import mcp
    else:
        raise ValueError(f"未知服务器: {name}")
    return mcp


def main():
    ap = argparse.ArgumentParser(description="BottleSumo Meta-Harness MCP 服务器")
    ap.add_argument("--server", default="all",
                    choices=["meta_cognition", "semantic_retrieval",
                             "environment_bootstrap", "all"])
    ap.add_argument("--transport", default="stdio",
                    choices=["stdio", "streamable-http"])
    ap.add_argument("--host", default="127.0.0.1",
                    help="streamable-http 监听地址 (默认 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000,
                    help="streamable-http 监听端口 (默认 8000)")
    args = ap.parse_args()

    if args.server == "all":
        names = ["meta_cognition", "semantic_retrieval", "environment_bootstrap"]
        for n in names:
            mcp = _build(n)
            tools = asyncio.run(mcp.list_tools())
            names_ = sorted(t.name for t in tools)
            print(f"[OK] {n}: {len(names_)} tools: {', '.join(names_)}")
        print("ALL SERVERS import + tool registration OK")
        return

    mcp = _build(args.server)
    print(f"[START] {args.server} @ {args.transport} "
          f"({args.host}:{args.port})", file=sys.stderr)
    if args.transport == "streamable-http":
        # 旧版 FastMCP: run() 不接受 host/port 关键字, 需先写 settings
        # (Settings.host/port 是 pydantic 字段, 可运行时赋值)
        try:
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        except Exception as e:
            print(f"[WARN] settings override failed: {e}", file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
