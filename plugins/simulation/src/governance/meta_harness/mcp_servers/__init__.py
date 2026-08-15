# -*- coding: utf-8 -*-
"""mcp_servers 包 — P1-3 MCP 服务器封装 (Sprint 10).

将 BottleSumo Meta-Harness 的三个核心模块封装为标准 MCP 服务器,
每个暴露 list_tools/call_tool 接口 (FastMCP, stdio 传输):

- meta_cognition_server     : P0-V2 元认知 (置信度追踪 + 假设检验)
  ~ angrysky56/meta-harness advanced-reasoning MCP
- semantic_retrieval_server : P1-V3 语义检索 (bge-m3)
  ~ project-synapse MCP (Wiki & 语义索引检索)
- environment_bootstrap_server : P1-2 环境引导 (快照 + 写作用域)
  ~ SuperagenticAI 环境引导 + 写作用域强制

启动: python -m mcp_servers.<server> (stdio) 或
       python -m mcp_servers --server meta_cognition --transport streamable-http
"""
