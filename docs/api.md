# API 参考

## 认知服务 (`cognify serve`, P0)

FastAPI 服务, 默认端口 8080。

### GET /health
存活检查。

```json
{"status": "ok", "service": "cognify-engine", "version": "2.1.0"}
```

### POST /mce — 认知编译 (MCE)

请求: `{"input": "文本"}` → 返回主导认知模型识别 + 模型外化 + 并行模型。

### POST /vce — 价值扫描 (VCE)

请求: `{"input": "文本"}` → 返回极化程度 + 冲突价值对。

### POST /cee — 演化推演 (CEE)

请求: `{"input": "文本", "vce": {...可选}}` → 返回三阶段演化计划
(24h 最小可行行动 / 中期加固 / 长期演化)。

## 治理网关 (P1)

### POST /governance/evaluate — 五层裁决

请求: `{"path": "/v1/chat/completions", "method": "POST", "body": {...}}`

返回: 五层裁决 `ALLOW / ALLOW_WITH_WARNING / ESCALATE / DENY / SUSPEND`
(带验证通道 verification/channel)。

## 示例

```bash
curl -X POST http://localhost:8080/vce \
     -H "Content-Type: application/json" \
     -d '{"input": "强制元思考 解耦化 自举解决"}'
```
