# ARCH-COMPLETE 验证报告 [#ARCH-ROUND 1] (verification_report.md)

> 时间: 2026-08-10 | 验证人: ARCH-COMPLETE v1.0 | 基线: main 3de1fb9

## 1. 回归测试

| 套件 | 结果 | 说明 |
|------|------|------|
| Dashboard backend（SQLite） | ✅ **37/37** | 原 28 + URL 5 + metrics 4 |
| Dashboard backend（PostgreSQL） | ✅ CI 矩阵配置就位 | 本地无 PG 服务；`make_url` 语义测试覆盖解析层；CI postgres:16 service 验证连通性 |
| 治理引擎（agent-governance-v2） | ✅ 1042 passed + 1 skipped | 引擎零代码变更（S69 基线）|
| E2E（真实 HTTP） | ✅ **9/9** | uvicorn 8010 + 全链路（T0.2/T0.3 各验一次）|
| 前端构建 | ✅ 39 modules | S69 基线；本轮无前端代码变更（frontend Dockerfile 除外）|

## 2. 新功能验证（硬 GATE 实测）

| 功能 | 验证方式 | 结果 |
|------|----------|------|
| `/metrics` 端点 | TestClient + 容器内 HTTP | ✅ 200 + Prometheus 文本 + `governance_*` 命名空间存在（4016 bytes）|
| 指标计数语义 | test_metrics.py | ✅ counter 递增 / 自身排除 / outcome 标签 |
| PG URL 一键切换 | test_database_url.py ×5 | ✅ 优先级/兼容/实时 env/参数覆盖/make_url 语义 |
| 容器化 | `docker build` + `docker run` | ✅ 镜像 317MB；`Up 12 seconds (healthy)`；HEALTHCHECK `/api/health 200 OK`；容器内 `/api/health` ok + `/metrics` 200 |
| docker-compose | `docker compose config --quiet` | ✅ VALID（5 服务 + observability profile）|
| Dockerfile 静态 | `docker build --check` | ✅ no warnings found |

## 3. 端到端验证（Dashboard 治理数据）

- 引擎集成（同进程 import）未变：`/api/health` → `engine=agent-governance-v2` ✅
- 策略编辑器全链路：E2E 9/9（validate 语义错误 / deploy 422 / rollback .bak / source 回环）✅
- 容器内同链路：health + metrics 200 ✅（策略 CRUD 由 E2E 本地覆盖）

## 4. 性能对比

| 指标 | 基线（S69） | ARCH-ROUND 1 后 | 变化 |
|------|-------------|-----------------|------|
| backend 测试数 | 28 | 37 | +9（URL 5 + metrics 4）|
| CI jobs | 5 | 6（+dashboard-backend-pg）| +1 矩阵 |
| 镜像大小 | 无 | 317MB（python:3.11-slim）| 新增部署物 |

## 5. 遗留（Honest Boundary）

- PG 真实连通性: 由 CI postgres service 首次运行验证（本地无 PG 实例，未本地实测连库）
- frontend 容器: Dockerfile 就位，未本地 build（nginx 配置静态校验；CI 或本地 docker 可验）
- mkdocs 完整 build: 本地未装 mkdocs（CI docs.yml 执行）
- E2E 残留协议自清理: P1（GAP-4.2 周边）

---

## 6. 增补: GitHub 生态配置验证（DUAL-ECO GAP-6.10, 2026-08-10 同日本轮）

零 UI 纯 API 完成（gh 2.97.0 + REST/GraphQL），双仓库验证回读:

| 配置 | bottlesumo-pi | agent-governance-v2 | 方式 |
|------|:---:|:---:|------|
| Issues | ✅ true | ✅ true | REST PATCH has_issues |
| Discussions | ✅ true | ✅ true | **GraphQL** updateRepository（REST 无此字段）|
| 分支保护 (1 review) | ✅ | ✅ | REST PUT branch protection |
| enforce_admins | ✅ | ✅ | 同上 |
| strict status checks | ✅ | ✅ | 同上 |
| allow_force_pushes | ✅ false | ✅ false | 同上 |

迭代教训（PM 脚本实测修正）:
1. **`has_discussions=true` 在 REST 不存在** → 409/静默失败；必须 GraphQL `updateRepository(hasDiscussionsEnabled)` 用 node_id
2. **PowerShell `Set-Content -Encoding utf8` 写 BOM** → gh --input 解析 JSON 失败；改 `[IO.File]::WriteAllText`
3. **分支保护反向拦截**：直写 main 409（must be through PR）→ CODEOWNERS 改走 PR 流程（bottlesumo-pi #15 / agent-governance-v2 #11, 待 PM 审批）
4. **GitHub 禁 self-review**：PR 合并必须 PM 操作

状态: GAP-6.10 ✅（CODEOWNERS 合并待 PM review）

