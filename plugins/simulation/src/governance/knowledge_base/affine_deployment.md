# AFFiNE 部署实录 (Sprint 57)

> 状态: ✅ 全栈已部署 (0.27.3, 含测试 SMTP) · ✅ Web UI 可注册
> 日期: 2026-08-10 (v2: 修复"按钮无法按"根因)

## 架构（4 容器）

| 容器 | 镜像 | 端口 | 状态 |
| :--- | :--- | :--- | :--- |
| affine | ghcr.io/toeverything/affine:stable | 宿主 3001 → 容器 **3010** | ✅ Running |
| affine-postgres | postgres:16 | 5432 | ✅ Running |
| affine-redis | redis:7-alpine | 6379 | ✅ Running |
| affine-mailpit | mailhog/mailhog | SMTP 1025 · Web 8025 | ✅ Running |

网络: `affine-net`（自定义 bridge）

## ⚠️ 正确入口: http://localhost:3001/admin/ （非根路径!）

`affine:stable` **内置 Web UI**，SPA publicPath=`/admin/`。浏览器必须访问 `/admin/`。

## 认证机制（selfhost 会话制）

- AFFiNE 0.27.3 用**邮箱验证码**登录/注册（错误码族: EMAIL_TOKEN_NOT_FOUND / INVALID_EMAIL_TOKEN / WRONG_SIGN_IN_METHOD）
- `createUser` 需已认证会话（匿名 401 AUTHENTICATION_REQUIRED）→ **无法纯 API 匿名注册**
- **SMTP 缺失 = 验证码发不出 = 按钮无反应**（PM 实测"按钮无法按"根因）
- 修复: 本地 Mailpit 测试 SMTP (`MAILER_HOST=affine-mailpit:1025`, `MAILER_IGNORE_TLS=true`)
- 验证码查看: **http://localhost:8025**（Mailpit Web UI）

## 部署步骤（可复现）

```bash
docker network create affine-net
docker run -d --network affine-net --name affine-postgres \
  -e POSTGRES_USER=affine -e POSTGRES_PASSWORD=affine -e POSTGRES_DB=affine \
  -p 5432:5432 postgres:16
docker run -d --network affine-net --name affine-redis -p 6379:6379 redis:7-alpine
docker run -d --network affine-net --name affine-mailpit -p 1025:1025 -p 8025:8025 mailhog/mailhog
# 数据库迁移 (115 个迁移, 需先清空 schema 若曾有残留)
docker exec affine-postgres psql -U affine -d affine \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO affine; GRANT ALL ON SCHEMA public TO public;"
docker run --rm --network affine-net --entrypoint sh ghcr.io/toeverything/affine:stable \
  -c "cd /app && DATABASE_URL='postgres://affine:affine@affine-postgres:5432/affine' npx prisma migrate deploy"
# 主服务 (boot.sh 生成 RSA 私钥 + MAILER 指向 Mailpit)
docker run -d -p 3001:3010 --network affine-net --name affine \
  -v <repo>/infra_affine/affine_boot.sh:/boot.sh:ro --entrypoint sh \
  -e MAILER_HOST=affine-mailpit -e MAILER_PORT=1025 \
  -e MAILER_SENDER=no-reply@affine.local -e MAILER_IGNORE_TLS=true \
  ghcr.io/toeverything/affine:stable /boot.sh
```

## 关键调试实录（避免重蹈覆辙）

| 错误 | 根因 | 修复 |
| :--- | :--- | :--- |
| pool timed out (postgres) | 镜像读 `DATABASE_URL` 而非 DB_HOST 系变量 | 用 `DATABASE_URL=postgres://user:pass@host:5432/db` |
| ERR_OSSL_UNSUPPORTED | `AFFINE_PRIVATE_KEY` 需 **PEM 格式 RSA 私钥**，给了普通字符串 | boot.sh 内 `openssl genrsa` 生成 + 注入 |
| P2021 app_configs 不存在 | 数据库未迁移 / schema 残留冲突 (P3005) | drop schema 重建 + `prisma migrate deploy` (115 迁移) |
| ECONNREFUSED 6379 | 缺少 Redis | 加 `REDIS_SERVER_HOST=affine-redis` `REDIS_SERVER_PORT=6379` |
| 容器监听 3010 非 3000 | AFFiNE 后端默认端口 3010 | `-p 3001:3010` |
| 宿主 3000 被占用 | 已有 gov-grafana 治理栈 | AFFiNE 用 **3001** |
| **按钮无法按 (PM 实测)** | **selfhost 无 SMTP → 邮箱验证码发不出 → 流程卡死** | Mailpit 测试 SMTP + `MAILER_*` 配置 |
| 根路径空白 | SPA publicPath=`/admin/` | 访问 `http://localhost:3001/admin/` |

## 验证命令

```bash
docker ps --filter "name=affine" --format "{{.Names}} | {{.Status}}"  # 4 容器 Running
curl -X POST http://localhost:3001/graphql -H "Content-Type: application/json" \
  -d '{"query":"query { serverConfig { version } }"}'   # → {"serverConfig":{"version":"0.27.3"}}
# 邮件捕获验证: 触发验证码后访问 http://localhost:8025
```

## ✅ v3: P0 自动化注册 + API 写入验证全通 (2026-08-10)

### 管理员账号（自动化创建）

- **账号**: `kb-admin@local.dev` / `AffineLocal2026!`
- **ID**: `69470377-bb59-438f-8223-7f020d8fad66`
- 管理面板: http://localhost:3001/admin/ （settings/queue/about/accounts 全通）

### ⚠️ 关键根因: React 受控组件 state 不同步（v4→v8 失败原因）

AFFiNE setup/login 表单是 **React 受控组件**。`page.fill()`、原生 value setter hack
都只改 DOM 不改 React state → 点 Continue 时校验读到的 email 是**空串** → 报
"Invalid email address"（校验函数在点击时才执行，不在 onChange 时）。

**解法: `page.keyboard.insert_text()`** —— 触发原生 input 事件，React state 正确同步。

### P0 自动化证据链

| 步骤 | API | 结果 |
| :--- | :--- | :--- |
| 创建管理员 | `POST /api/setup/create-admin-user` | 200 |
| 登录 | `POST /api/auth/sign-in` | 200 + session cookie |
| 建工作区 | GraphQL `createWorkspace` mutation | 200 → ws `aa432014-...` |
| 读回验证 | GraphQL `getWorkspaces` | 新 ws 可见 |
| 文档持久化 | UI 建 doc + 输入 + **重启浏览器重开** | 标题/正文 100% 保留 |

### 发现: AFFiNE selfhost 是 persisted operations 模式

- GraphQL 只接受前端预注册的 operation 名（"Unknown operation named"）
- 管理面板白名单仅 5 个 admin 操作；主前端有 createWorkspace / publishPage 等
- 需用浏览器上下文 fetch（自动带 cookie + CSRF）才能调用

### 本地 vs Cloud workspace

- **本地**: 浏览器 IndexedDB（"saved in this browser"），换 context 即 404
- **Cloud**: 服务端 GraphQL 创建（`initialized: false`），需前端初始化流程
- E2E 验证用**持久化 context**（user-data-dir 落盘）跨重启验证
