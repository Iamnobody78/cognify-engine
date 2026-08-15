# ARCH-COMPLETE 补全报告 [#ARCH-ROUND 1] (completion_report.md)

> 时间: 2026-08-10 | 分支: feature/arch-* ×4 → main | 依据: completion_plan.md

## Phase D: Diagnose
- P0 缺口: 4 项（GAP-1.1 可观测 / GAP-2.1 PostgreSQL / GAP-5.1 容器化 / GAP-6.1 生产路线图）
- P1 缺口: 11 项 | P2 缺口: 8 项
- 诊断报告: `governance/architecture/gap_diagnosis_report.md`（含 23 项缺口全表 + 实测证据）

## Phase P: Plan
- 本周期处理: 4 × P0（ARCH-ROUND 1）
- 计划文档: `governance/architecture/completion_plan.md`

## Phase E: Execute

| 任务 | 缺口 | 分支 | Commit | GATE |
|------|------|------|--------|------|
| T0.1 生产化路线图 | GAP-6.1 | feature/arch-6.1-roadmap | 93181ee | ✅ mkdocs YAML + nav 存在性 |
| T0.2 PostgreSQL | GAP-2.1 | feature/arch-2.1-postgres | c5fbc81 | ✅ 33/33 + E2E 9/9 + ci.yml 合法 |
| T0.3 可观测性 | GAP-1.1 | feature/arch-1.1-observability | df2d6d4 | ✅ 37/37 + E2E 9/9 |
| T0.4 容器化 | GAP-5.1 | feature/arch-5.1-container | 3de1fb9 | ✅ compose VALID + 镜像构建 317MB + 容器 healthy + /metrics 200 |

### 代码变更清单（227 行新增/修改）
- 生产代码: `dashboard/backend/database.py`（resolve_db_url + make_url 分支）、`metrics.py`（Counter/Histogram + Middleware）、`logging_setup.py`（JSON/plain 双格式）、`main.py`（挂载 /metrics + setup_logging + version 更新）
- 测试: `tests/test_database_url.py`（5 例）、`tests/test_metrics.py`（4 例）
- 部署: `Dockerfile`、`dashboard/frontend/Dockerfile`、`dashboard/frontend/nginx.conf`、`docker-compose.yml`、`.dockerignore`、`deployment/prometheus.yml`
- 文档: `docs/architecture/ROADMAP_PRODUCTION.md`、`database.md`、`observability.md`、`deployment.md`、根级 `.env.example`、`CHANGELOG.md`（v2.1.0 + 跨项目影响章节）
- CI: `.github/workflows/ci.yml`（+dashboard-backend-pg job，gate 扩为 4 依赖）

## 迭代失败记录（诚实披露）

| 迭代 | 失败 | 根因 | 修复 |
|------|------|------|------|
| T0.2 GATE ×1 | `_factory` NameError 28 例 | 重写 database.py 遗漏模块级 `_factory = None` | 补回初始化（GATE 捕获回归 ✓）|
| T0.2 GATE ×2 | env URL 测试失败 | `DB_URL` 模块级常量不响应 monkeypatch | `resolve_db_url` 改实时读环境变量 |
| T0.2 GATE ×3 | PG URL 测试 ModuleNotFoundError | SQLAlchemy create_engine **eager 加载 dbapi** | 单测改用 `make_url` 纯解析（不加载驱动）|
| T0.3 GATE | 既有测试 12≠9 两例 | **E2E 部署残留** `e2e_demo.yaml` 污染真实协议目录（E2E 设计缺陷，非本分支引入）| 清理残留；E2E 自清理列入 P1 |

## Honest Boundary
- 本次完成范围: **P0 ×4**（生产基线）
- 本次不处理项: P1 ×11 + P2 ×8（RBAC 为 P1 首项，下轮优先）；E2E 自清理缺陷（P1）；mkdocs 完整 build 本地未装（CI docs.yml 执行）

---

# ARCH-COMPLETE 补全报告 [#ARCH-ROUND 2] (completion_report.md)

> 时间: 2026-08-11 | 分支: feature/arch-2-rbac → PR #17（待合并）| 依据: PM 裁决 "security over experience"

## Phase D: Diagnose
- P0 缺口: **RBAC+JWT**（GAP-3.1 首项，无认证/无授权，任何人可调 deploy/VCE/policy_validate）
- 证据: 治理中心 MVP（S68）端点裸奔——`/api/policies/deploy` 无鉴权、`/api/agents` 可枚举、audit 可读
- 约束: engine-integration 端点（evaluate/audit_ingest）保持开放（v3.0 服务解耦），仅 human-facing 端点门控

## Phase P: Plan
- 分支策略: `feature/arch-2-rbac`（独立分支，遵循 D.P.E.V. + GATE 硬门）
- 设计决策: 角色层级 viewer(1) < auditor(2) < admin(3)；`require_role` Depends factory；bcrypt 原生 API（弃 passlib）；JWT HS256 + GOV_AUTH_SECRET（缺省启动警告）+ TTL 12h
- 集成面: 后端 models/auth/routers ×3 + 前端 api/App/LoginView + E2E 适配 + 文档

## Phase E: Execute

| 任务 | 缺口 | Commit | GATE |
|------|------|--------|------|
| T0.1 users 表 + auth（bcrypt + JWT + seed_admin_if_empty） | GAP-3.1 | 30c78f0（单 commit 全栈） | ✅ 46/46 |
| T0.2 require_role 门控（agents/audit/policies/vce 矩阵） | GAP-3.1 | 30c78f0 | ✅ 46/46 + E2E 9/9 |
| T0.3 用户管理 API（login/me/users CRUD + DELETE 幂等） | GAP-3.1 | 30c78f0 | ✅ 46/46 ×2 |
| T0.4 前端（LoginView/路由守卫/角色徽章/logout + authApi） | GAP-3.1 | 30c78f0 | ✅ 前端 build 39 modules |

### 代码变更清单
- 生产代码: `dashboard/backend/models.py`（User 表）、`auth.py`（bcrypt/JWT/get_current_user/require_role）、`routers/auth.py`（login/me/users ×4）、`routers/governance.py`（require_role 门控矩阵）、`main.py`（挂载 auth + seed_admin）
- 前端: `src/services/api.js`（authApi + token 注入）、`src/App.jsx`（守卫/徽章/logout）、`src/pages/LoginView.jsx`
- 测试: `tests/test_auth.py`（9 例：401/登录/me/令牌/角色矩阵/用户管理 admin-only）
- E2E: `e2e/e2e_policy_editor.py`（启动时 login() 注入 JWT）
- 文档: `docs/architecture/authz.md`（角色矩阵 + 与 engine tenant auth 集成设计）
- 变更统计: **+14 文件 / +890 行**（实现 5 文件 ~300 行，测试 9 例，前端 3 文件，文档 1）

## 迭代失败记录（诚实披露）

| 迭代 | 失败 | 根因 | 修复 |
|------|------|------|------|
| T0.1 | passlib 1.7.4 × bcrypt 5.0.0 哈希错误 | passlib 引用已移除的 `bcrypt.__about__` → 72-byte 截断错误 | **弃用 passlib**，直接用 bcrypt 原生 `hashpw/checkpw` |
| T0.3 | 重复 pytest 409（用户已存在） | 测试写真实 DB，无清理路径 | 新增 `DELETE /api/auth/users/{username}`（admin）+ 先删后建幂等模式 → ×2 全量 46/46 |
| GATE | rootdir 解析漂移（本地从仓库根跑 pytest 收集失败） | 外层 pyproject.toml 捕获 rootdir | 统一 `working-directory: dashboard/backend` 运行（与 CI 一致）|

## 合并状态（阻塞项 — 需 PM 裁决）

| PR | 仓库 | 状态 | 阻塞原因 |
|----|------|------|----------|
| #17 RBAC+JWT | bottlesumo_pi | ✅ 实现完成，⛔ REVIEW_REQUIRED | 单账号 + 禁 self-review + enforce_admins = 合并死锁 |
| #13 AUDIT-0072 | agent-governance-v2 | ✅ 已推送已建 PR，⛔ REVIEW_REQUIRED | 同上 |

## Honest Boundary
- 本次完成范围: **GAP-3.1 RBAC+JWT 全栈实现**（后端 + 前端 + 测试 + 文档），GATE 实测通过
- 未完成: **PR 合并**（死锁依赖 PM 行动：bot 账号 or 独立 review 账号 or override 窗口）
- 不处理项: DUAL-ECO 剩余 P0（版本矩阵/E2E demo/Grafana/C4）、性能基准（GAP-4.1）、密钥管理（GAP-3.2）、审计管道（GAP-1.2）、E2E 自清理（RULE-ARCH-004）
