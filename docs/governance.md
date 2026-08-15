# 治理网关

## 五层裁决 (S63-S66)

| 裁决 | 含义 |
|------|------|
| ALLOW | 放行 |
| ALLOW_WITH_WARNING | 放行 + 警告 |
| ESCALATE | 升级人工 |
| DENY | 拒绝 |
| SUSPEND | 挂起 |

## 端点

`POST /governance/evaluate` (经 `cognify serve` 暴露)

```bash
curl -X POST http://localhost:8080/governance/evaluate \
     -H "Content-Type: application/json" \
     -d '{"path": "/v1/chat/completions", "method": "POST", "body": {"role": "user"}}'
```

返回 `{rule, action, verification, channel}` — 带验证通道的裁决结果。

## 验证通道 (S66)

- BaselineDeclarationValidator: 确定性一致性检查
- LLMSemanticValidator (DEBT-001): 语义验证插槽 (PR #15)

## 回归

```bash
cognify test --plugin governance   # 全量治理回归 (1038 passed / 0 failed)
```
