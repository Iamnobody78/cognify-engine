# ARCH-COMPLETE 补全计划 (completion_plan.md)

> 规划时间: 2026-08-10 | 依据: gap_diagnosis_report.md（4 P0 / 11 P1 / 8 P2）
> 原则: 每项独立分支 → GATE（测试+lint+build）→ 文档同步 → 证据链（commit hash）

---

## 阶段节奏（遵循 PM 路线图 v2.x 稳固核心）

| 周期 | 处理项 | 目标 |
|------|--------|------|
| **ARCH-ROUND 1（本周期）** | 4 × P0 | ✅ **完成 2026-08-10**（main 3de1fb9, 详见 completion_report.md / verification_report.md）|
| ARCH-ROUND 2（下 Sprint） | P1 首 4 项 | RBAC / 性能基准 / 密钥管理 / 审计日志管道 |
| ARCH-ROUND 3+ | 其余 P1 → P2 | 实验管理 / 教程 / 扩展点 / 生态 |

---

## P0 补全任务（ARCH-ROUND 1）

### T0.1 GAP-6.1 生产化路线图 [feature/arch-6.1-roadmap] — 预估 0.5h
- 新建 `docs/architecture/ROADMAP_PRODUCTION.md`：三阶段路线图（v2.x 稳固核心 / v3.0 能力增强 / v4.0+ 生态构建）+ 每阶段可验证门（Definition of Done）
- 链接入 mkdocs nav + ARCHITECTURE.md 引用
- GATE: mkdocs build 通过
- 依赖: 无（先行）

### T0.2 GAP-2.1 PostgreSQL 支持 [feature/arch-2.1-postgres] — 预估 2h
- 改造 `dashboard/backend/database.py`：`GOV_DASH_DB_URL` 环境变量优先（标准 SQLAlchemy URL），默认仍为 SQLite（向后兼容）
- 新增 `.env.example` + 配置说明（SQLite/PG 一键切换）
- 新增 `docs/architecture/database.md`：选型依据、连接串、迁移策略（SQLAlchemy `create_all` + 未来 Alembic 建议）
- 新增 CI 矩阵任务：`postgres:16` service + `DATABASE_URL=postgresql+psycopg://...` 跑 backend 28/28
- GATE: SQLite 28/28 + PG 28/28 + E2E 9/9
- 依赖: T0.1（路线图引用数据库章节）

### T0.3 GAP-1.1 可观测性指标 [feature/arch-1.1-observability] — 预估 2h
- 引入 `prometheus-client`；main.py 挂载 `GET /metrics`（Counter: governance_requests_total{outcome} / audit_writes_total；Histogram: request_duration_seconds）
- 结构化日志：`structlog` 或标准 logging JSON formatter（审计路径与业务路径分离）
- 新增 `docs/architecture/observability.md`：指标清单、Grafana 面板建议、日志格式规范
- 测试: `/metrics` 端点返回 200 + 指标存在性断言（新增 test_metrics.py）
- GATE: pytest 全量 + /metrics 断言 + E2E 9/9
- 依赖: 无

### T0.4 GAP-5.1 容器化部署 [feature/arch-5.1-container] — 预估 2.5h
- 根级 `Dockerfile`（backend：python:3.11-slim + uvicorn）+ `dashboard/frontend/Dockerfile`（node:20-alpine + nginx 静态托管）
- 根级 `docker-compose.yml`：backend + frontend + **postgres:16** + prometheus（可选 profile）+ grafana（可选 profile）
- `.dockerignore` + `docs/architecture/deployment.md`：构建/启动/健康检查/端口
- GATE: `docker compose config` 校验通过（本机有 docker 则实测启动 + healthcheck）
- 依赖: T0.2（compose 引用 PG service）、T0.3（compose 引用 metrics）

### P0 完成判据（ARCH-ROUND 1 Done）
- [ ] 全量回归: backend 28/28 + 引擎 1042 + E2E 9/9（PG 模式 28/28 额外）
- [ ] 新功能: `/metrics` 可访问、`docker compose config` 合法、PG 连接串切换有效
- [ ] 文档: ROADMAP_PRODUCTION.md / database.md / observability.md / deployment.md 全部入库
- [ ] 证据链: 每分支 commit hash 记入 completion_report.md

---

## P1 首 4 项（ARCH-ROUND 2，预告）

| 任务 | 缺口 | 内容 |
|------|------|------|
| T1.1 RBAC + JWT | GAP-3.1 | fastapi 依赖 + 登录端点 + 角色（viewer/auditor/admin）策略权限矩阵 + 前端登录态 |
| T1.2 性能基准 | GAP-4.1 | pytest-benchmark 决策延迟/审计吞吐基线 + CI nightly 任务 |
| T1.3 密钥管理 | GAP-3.2 | SECURITY.md secrets 章节 + .env.example + 12-factor 规范 |
| T1.4 审计日志管道 | GAP-1.2 | 日志抽象（sink → SQLite/JSON stdout/Loki 可选） + 轮转归档 |

## P2 预告（ARCH-ROUND 3+）

实验管理（MLflow）→ 资产版本化（DVC+manifest）→ 状态同步协议 → ESCALATE 流程文档 → API v1 版本前缀 → 教程 → 扩展点 → SemVer 策略 → C4 图 → 备份恢复 → 策略生命周期 → 插件机制 → 策略市场（v4.0）

---

## 风险与红线

1. **兼容性**：PG 切换必须保持 SQLite 默认可用（现有测试/开发不破坏）
2. **红线 #2**：每项补全必须同步文档，否则不提交
3. **红线 #3**：GATE 失败不得声称完成
4. **红线 #5**：P0 不延后——ARCH-ROUND 1 一次完成 4 项 P0
5. **引擎耦合**：governance_engine.py 同进程导入保持现状（v3.0 解耦），本周期仅加文档约束
