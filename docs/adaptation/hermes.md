# Hermes 使用指南 — Cognify MCP 工具 (SELF-ADAPT v1.0)

## 工具清单

| 工具 | 功能 |
|------|------|
| `cognify_governance` | 治理裁决 (五层) — 参数 {input} |
| `cognify_cognitive` | MCE 认知编译 — 参数 {input} |
| `cognify_sync` | 三方同步状态 |
| `cognify_meta` | 25 维元能力状态 |
| `cognify_debt` | 债务扫描 |

## 对话示例

- "使用 cognify_governance 评估这段输入: <文本>" → 裁决结果
- "使用 cognify_cognitive 编译: <文本>" → 主导模型 + 外化
- "检查三方同步状态" → cognify_sync

## 配置位置

- 服务器: `cognify-engine/mcp/cognify_mcp_server.py` (MCP stdio, JSON-RPC 2.0)
- 注册: `AppData\Local\hermes\config.yaml` → mcp_servers.cognify (enabled: true)
- Catalog: `hermes-agent/optional-mcps/cognify/manifest.yaml`
- 生效: Hermes 重载 MCP 配置后 (hermes mcp list 可见)

## 独立测试

```bash
python cognify-engine/mcp/cognify_mcp_server.py   # MCP 握手后 tools/list 返回 5 工具
```
