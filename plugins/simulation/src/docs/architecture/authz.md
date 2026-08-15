# 认证与授权架构 (authz.md)

> 状态: v1.0 (ARCH-ROUND 2 / GAP-3.1) | 2026-08-10

## 1. 设计原则

1. **默认拒绝**：人类端点一律要求 JWT，无 token → 401
2. **最小权限**：角色自上而下（viewer < auditor < admin），每个端点声明所需最低角色
3. **写操作收紧**：策略部署（治理规则变更）仅 admin；VCE 扫描 auditor+；读操作 viewer+
4. **引擎集成例外**：evaluate/audit_ingest（agent → dashboard）无人类用户上下文，保持开放——v3.0 服务化解耦时补 API-Key 鉴权
5. **诚实安全**：种子用户 admin/admin123 仅限开发；生产必须 `GOV_AUTH_SECRET` + 改密

## 2. 数据模型（users 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增 |
| username | String unique | 登录名 |
| password_hash | String | bcrypt 哈希（原生 API, 弃用 passlib——1.7.4 与 bcrypt≥4.1 不兼容）|
| role | String | viewer / auditor / admin |
| created_at | DateTime | 创建时间 |
| last_login | DateTime | 最近登录 |

## 3. 角色矩阵

| 端点 | viewer | auditor | admin |
|------|:---:|:---:|:---:|
| GET /agents /audit /policies /vce /me | ✅ | ✅ | ✅ |
| GET /policies/{p}/source（编辑器加载）| ✅ | ✅ | ✅ |
| POST /policies/validate | ✅ | ✅ | ✅ |
| POST /vce/scan | ❌ 403 | ✅ | ✅ |
| POST /policies/deploy | ❌ 403 | ❌ 403 | ✅ |
| POST /auth/users（用户管理）| ❌ 403 | ❌ 403 | ✅ |
| POST /evaluate /audit/ingest（引擎集成）| 开放（无 JWT）| 开放 | 开放 |

## 4. 认证流

```
登录: POST /api/auth/login {username,password}
  → 校验 bcrypt → 签发 JWT (HS256, GOV_AUTH_SECRET, TTL=GOV_AUTH_TTL_HOURS 默认12h)
  → {token, user:{id,username,role}}

访问: Authorization: Bearer <token>
  → get_current_user 依赖: 解析 token → 查 users 表 → 返回 User
  → require_role(min_role) 依赖: 角色等级比较, 不足 → 403

前端: token 存 localStorage (gov_token/gov_user) → 无 token 路由守卫重定向登录页
  → 401 时后端拒绝, 前端显示错误
```

## 5. 与 agent-governance-v2 租户认证打通（DUAL-ECO P1 设计）

**目标**：dashboard 用户体系 ↔ 引擎租户认证，单点登录 + 角色同步。

**方案（推荐：共享密钥 + 角色映射）**：
1. 共享 `GOV_AUTH_SECRET`（两系统同源）——dashboard 签发的 JWT 引擎可直接验签
2. 角色映射表：dashboard `viewer/auditor/admin` → 引擎租户角色（如 `tenant-reader/tenant-auditor/tenant-admin`）
3. 打通点：引擎侧审计记录携带 `subject=username`（跨系统审计关联）
4. 演进：v3.0 引擎服务化后，JWT 中加 `tenant` claim，网关统一验签

**暂缓项**：引擎侧无 HTTP 人类端点（同进程调用），打通的实际收益在引擎服务化后显现——故列为 DUAL-ECO P1，非本版实现。

## 6. 安全注意事项

- `GOV_AUTH_SECRET` 未设置 → 开发默认值 + 启动警告（生产必须配置，建议 `python -c "import secrets; print(secrets.token_hex(32))"`）
- 种子 admin/admin123 仅首次启动创建（users 空时）；生产建议首个动作改密 + 创建专属用户
- bcrypt 成本因子: gensalt() 默认 12 轮（可配置）
- 前端角色 UI（部署按钮仅 admin 显示）是 UX 层；**安全以后端 403 为准**（不可依赖前端隐藏）

## 7. 测试矩阵

- `tests/test_auth.py` 9 例: 401 无凭据 / login 成功失败 / me / 无效 token / viewer 读可部署禁 / auditor 验证可部署禁 / admin 可达引擎 / 用户管理 admin only
- 全量: 46/46 + E2E 9/9（含 RBAC 登录）
