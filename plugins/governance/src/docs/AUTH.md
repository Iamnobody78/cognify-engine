# 认证授权层（AuthN/AuthZ）— P13

> 版本: v1.23.0 · 审计: AUDIT-0043 · 状态: ✅ 已验收（P6 骨架 + P13 独立验收）

## 1. 架构概览

```
请求 ──► /v1/intercept ──► _auth_gate ──► PolicyEngine ──► 决策
          │  (401/403)        │
          │                   └── TenantAuth.authenticate(headers)
          │                        ├── Authorization: Bearer <key>   (AC7)
          │                        └── X-API-Key: <key>               (AC7)
          │
          ▼
   config/tenants.yaml (tenant_id → api_keys[])
```

- **认证（AuthN）**: `src/auth.py::TenantAuth` — API Key → tenant_id 映射
- **授权（AuthZ）**: `policy.py` 的 `tenant` 字段 — 租户私有规则隔离
- **密钥体系**: `.keys/` ED25519（P8，防篡改）与本层 API Key（认证）互补——前者证明"数据未被改"，后者证明"谁在调用"

## 2. 配置（config/tenants.yaml）

```yaml
tenants:
  - id: tenant-a
    api_keys: [bsum-dev-key-a-0001]
  - id: tenant-b
    api_keys: [bsum-dev-key-b-0001]
```

**生产必读**: 示例 key 仅用于本地开发，生产必须轮换为高熵随机 key。

## 3. 验证

```bash
# AC1: 无 key → 401
curl -X POST http://localhost:8080/v1/intercept \
  -H "Content-Type: application/json" \
  -d '{"path":"/api/chat","method":"POST","messages":[]}'
# → 401

# AC2: 无效 key → 401
curl -X POST ... -H "X-API-Key: invalid" → 401

# AC3/AC7: 有效 key（两种头格式）→ 200/403
curl ... -H "Authorization: Bearer bsum-dev-key-a-0001" → 200/403
curl ... -H "X-API-Key: bsum-dev-key-a-0001" → 200/403

# AC4: 租户冒称 → 403
curl ... -H "Authorization: Bearer bsum-dev-key-a-0001" \
         -H "X-Tenant-ID: tenant-b" → 403
```

## 4. 验收矩阵（P13）

| AC | 内容 | 结果 | 证据 |
|----|------|------|------|
| AC1 | 无 API Key → 401 | ✅ | aiohttp TestClient + 手动探测 |
| AC2 | 无效 API Key → 401 | ✅ | test_invalid_key_returns_401 |
| AC3 | 有效 API Key → 正常处理 | ✅ | test_valid_key_without_declared_tenant_passes |
| AC4 | 租户隔离生效 | ✅ | test_cross_tenant_cannot_see_other_private_rule |
| AC5 | 全量 ≥542 | ✅ | 542 passed（29 auth + 513 其余） |
| AC6 | 快照 v1.23.0 | ✅ | TRIPLE_LOOP_SNAPSHOT.md |
| AC7 | Bearer + X-API-Key 双格式 | ✅ | test_x_api_key_header_alternative + 手动探测 |

## 5. 与 P8 的边界

| 层 | 解决 | 密钥 |
|----|------|------|
| P8 认证链 | 数据防篡改 | ED25519（`.keys/`） |
| P13 AuthN | 谁在调用 | API Key（tenants.yaml） |
| P13 AuthZ | 谁能访问什么 | policy tenant 字段 |
