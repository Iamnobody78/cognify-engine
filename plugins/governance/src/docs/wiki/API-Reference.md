# API Reference

所有治理端点 + 请求/响应格式。

## 端点概览

| 端点 | 方法 | 描述 |
|------|------|------|
| `/v1/intercept` | POST | 治理拦截主入口 |
| `/v1/health` | GET | 健康检查 |
| `/v1/decisions` | GET | 决策记录查询 |
| `/v1/trace/{trace_id}` | GET | 因果链追踪 |
| `/v1/chat/completions` | POST | 兼容 OpenAI API 代理 |
| `/v1/bench/intercept` | POST | 性能基准入口（P14） |

## `/v1/intercept`

**请求格式**：

```json
{
  "path": "/api/tools/exec",
  "method": "POST",
  "headers": {"authorization": "Bearer <key>"},
  "body": "{\"tool\": \"delete_file\"}"
}
```

**响应格式**（五级判定）：

```json
{
  "verdict": "DENY",
  "reason": "规则 'block-shell-tool' 匹配；AST-BLOCK python code-execution L1:1 sexp=(call ...)",
  "decision_id": "uuid",
  "trace_id": "uuid",
  "rationale": "工具调用 delete_file 被策略阻断"
}
```

**AST 硬阻断行为**（v1.25.0）：请求体含代码片段（如 `{"language": "python", "code": "..."}`）时，危险模式直接返回 `DENY`，`reason` 携带精确行号 + S-expression 标签。

## `/v1/health`

```json
{
  "status": "ok",
  "version": "0.4.0",
  "timestamp": "2026-08-03T12:00:00Z"
}
```

## `/v1/decisions`

查询历史决策记录（支持 tenant 过滤）。

```json
{
  "decisions": [
    {
      "decision_id": "uuid",
      "verdict": "DENY",
      "reason": "...",
      "rationale": "...",
      "matched_rule": "block-shell-tool",
      "trace_id": "uuid",
      "timestamp": "..."
    }
  ]
}
```

## `/v1/trace/{trace_id}`

因果链追踪（Trace CTE 递归查询）。

```json
{
  "trace_id": "uuid",
  "nodes": [
    {"id": "uuid", "span_id": "...", "parent_span_id": "...", "verdict": "DENY"}
  ],
  "root": "uuid"
}
```

## `/v1/chat/completions`

兼容 OpenAI API 代理（Sidecar 拦截 Agent 调用）。

```json
{
  "model": "gpt-4o",
  "messages": [{"role": "user", "content": "..."}]
}
```

## 认证（P13）

- 头部：`Authorization: Bearer <api_key>` 或 `X-API-Key: <api_key>`
- 无 key → 401；无效 key → 401；有效 key → 200（租户隔离）
- 常量时间比较（`secrets.compare_digest`），fail-closed

## 错误码

| 状态码 | 含义 |
|--------|------|
| 200 | ALLOW / ALLOW_WITH_WARNING |
| 202 | ESCALATE（升级人工） |
| 401 | 认证失败（无 key / 无效 key） |
| 403 | DENY / SUSPEND（含 AST 硬阻断） |
| 500 | 内部错误（fail-closed） |
