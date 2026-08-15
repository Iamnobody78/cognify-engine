# 部署与运维 (deployment.md)

> 状态: v1.0 (ARCH T0.4 / GAP-5.1) | 2026-08-10

## 1. 一键部署（Docker Compose）

```bash
# 标准栈: backend + frontend + postgres
docker compose up --build

# 可观测性栈（追加 prometheus + grafana）
docker compose --profile observability up --build

# 停止
docker compose down            # 保留数据卷
docker compose down -v         # 连数据卷一起删（生产勿用）
```

| 服务 | 端口 | 说明 |
|------|------|------|
| frontend (nginx) | 5173 | SPA 静态托管 + /api 反向代理 |
| backend (uvicorn) | 8000 | 治理 API + /metrics + /api/health |
| postgres 16 | 5432 | 生产数据库（GOV_DASH_DB_URL 自动注入）|
| prometheus | 9090 | 指标采集（profile: observability）|
| grafana | 3000 | 监控面板（admin/admin, profile: observability）|

## 2. 镜像构建架构

- **backend**: 多阶段 Dockerfile —— stage 1 从 GitHub 拉取 `agent-governance-v2`（`GOV_ENGINE_REF` ARG 锁定 ref）并安装引擎依赖；stage 2 安装 dashboard 依赖并启动
- **frontend**: node:20 构建 → nginx:1.27-alpine 托管（SPA fallback + /api 代理到 backend:8000）
- 引擎同进程集成：镜像内 `GOV_AGENTS_V2_PATH=/app/engine`（v3.0 解耦前）

## 3. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `GOV_DASH_DB_URL` | (SQLite) | 生产用 compose 注入 PG URL；开发默认 SQLite |
| `GOV_AGENTS_V2_PATH` | /app/engine | 引擎路径（容器内固定；本地开发指向本地 clone）|
| `GOV_LOG_FORMAT` | json (容器) | 结构化日志格式 |
| `GOV_ENGINE_REF` | main | 构建时引擎锁定 ref（建议固定 commit/tag）|

## 4. 健康检查与就绪

- backend HEALTHCHECK: 30s 间隔 GET /api/health（容器级 liveness）
- postgres healthcheck: pg_isready（compose depends_on 门）
- 发布/回滚（GAP-5.2 预告）: 镜像 tag = 语义版本（v2.1.0）→ 回滚 = 切回上一 tag 重启；v2.x 补 CI 发布流水线

## 5. 备份（GAP-5.3 预告）

- PostgreSQL: `docker compose exec postgres pg_dump -U bottlesumo bottlesumo > backup.sql`
- 140GB 仿真资产: 与代码解耦（DVC 版本管理，v3.0）；容器不含资产

## 6. GATE 记录（本项验证）

- `docker compose config` 校验: ✅ 合法
- 镜像构建: 见 completion_report.md 实测记录
- 回归: backend 37/37 + E2E 9/9（本地非容器路径不受影响）
