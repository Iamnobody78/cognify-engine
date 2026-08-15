# 三方 MCP 统一接入 (UNIFIED MCP REGISTRY · 书同文车同轨)

## 架构: 一处配置, 三处使用

```
~/.aionui-tri-sync/config/mcp_registry.yaml   ← 唯一配置源 (52 项)
        │
        ├── daemon/mcp_sync.py
        │     ├── → Hermes: config.yaml mcp_servers
        │     ├── → AionUi: aionui-backend.db mcp_servers 表
        │     └── → DSH:    profiles/cognify/MCP_REFERENCE.md (cordis 无原生 MCP, 参考路径)
```

## 已接入 (ready, 现网可用)

| 服务器 | 域 | 说明 |
|--------|-----|------|
| filesystem | 基础 | npx @modelcontextprotocol/server-filesystem |
| git | 开发 | npx server-git |
| github | 开发 | npx server-github (GITHUB_PERSONAL_ACCESS_TOKEN 已注入) |
| fetch | 检索 | npx server-fetch |
| memory | 记忆 | npx server-memory (KVS) |
| sequential-thinking | 推理 | npx server-sequential-thinking |
| sqlite | 数据库 | npx server-sqlite (state/unified.db) |
| playwright | 浏览器 | npx @playwright/mcp |
| chrome-devtools | 浏览器 | 既有 (两系统 connected) |
| cognify | 认知操作 | 自研 (governance/cognitive/sync/meta/debt 5 工具) |

Hermes: 8 新增 + 既有 = 可调用集 | AionUi: 9 新增 (pending → 测试后 connected) | DSH: 参考清单

## 待接入队列 (状态标注, 请示点)

| 类别 | 条目 |
|------|------|
| pending-key (凭据) | serper / brave-search / multi-search / notion / slack / stripe / apify / sentry / google-cloud / browserbase |
| pending-app (软件) | ltspice / inventor / ansys-mechanical / pymapdl / cad-cae-copilot / eplan / blender / unreal / grafana / kubernetes / terraform / argo-cd / memorious / memory-qdrant |
| pending-hardware (硬件) | embodied-claude (USB 摄像头) / vectorclaw (Anki Vector) / embodied-arm (ROS2 机械臂) |
| registry-only (生态) | vision-primitives / image-recognition / visionsearch / visionpower / neo / tabicl / mlloop / ai-data-science / universal-netlist / mcsa / electronics / metamcp / agentset / mcp-run-python / mcp-browser-agent |

## 验证

- mcp_sync 幂等可重跑: `python daemon/mcp_sync.py`
- AionUi: mcp_servers 表 16 行 (9 新增) | Hermes: config.yaml mcp_servers 12+ 项
- npx 类服务器由 Hermes/AionUi 各自运行时拉起 (chrome-devtools 同机制 connected 佐证)
- cognify MCP: MCP 握手测试 PASS (initialize/tools/list/tools/call)

## 同步命令

```bash
python C:\Users\ivy\.aionui-tri-sync\daemon\mcp_sync.py
```
