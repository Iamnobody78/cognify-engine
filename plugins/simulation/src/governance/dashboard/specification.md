# SEED-ROUND-1 规格文档 (specification.md)

> **任务**：将 Sprint 13 积累的 MCP 调用数据（52 条 mcp_usage_report.jsonl + 43 条 hypotheses.jsonl）
> 转化为可交互的全栈监控仪表板，用于实时查看 MCP 服务器健康、工具延迟分布、假设命中率趋势。
> **协议**：SEFS-ARCH v1.0（S.E.E.D. 四阶循环 Phase S 输出）
> **日期**：2026-08-05 | 分支：feature/sprint14_fullstack_seed

---

## 1. 功能规格（用户故事 + 验收标准）

| ID | 用户故事 | 验收标准 |
| :--- | :--- | :--- |
| US-1 | 作为治理智能体，我想在一屏内看到三台 MCP 服务器（meta_cognition / semantic_retrieval / environment_bootstrap）的健康状态 | 每个服务器显示：调用总数、成功率、平均延迟、最近状态；健康卡片实时反映 ok/error 计数 |
| US-2 | 作为治理智能体，我想分析工具调用延迟分布，定位慢调用 | 显示延迟 min/max/avg/p95；按工具分组的延迟表格；高亮 >2s 的异常调用 |
| US-3 | 作为治理智能体，我想追踪假设（hypothesis）命中率趋势，评估候选质量 | 按 variant_id 聚合显示 attempts/hits/confidence；命中率趋势折线（按 ts 排序） |
| US-4 | 作为治理智能体，我想查看调用量随时间的变化 | 按天/小时聚合的调用量柱状图 |

**非功能需求**：
- 后端 API 响应 < 200ms（本地）
- 前端无构建依赖即可预览（提供静态构建产物）
- 数据库层可切换 SQLite（开发）/ PostgreSQL（生产），ORM 方言兼容

---

## 2. 技术规格（架构决策 + 接口定义）

### 2.1 技术栈

| 层 | 技术 | 理由 |
| :--- | :--- | :--- |
| L3 数据库 | SQLAlchemy 2.0 ORM + SQLite（当前环境）/ PostgreSQL 14（生产，DATABASE_URL 切换） | 环境无 PG 服务/Docker daemon 未运行；ORM 保证方言可移植 |
| L2 后端 | FastAPI 0.133 + uvicorn + pydantic v2 | 异步、自动 OpenAPI 文档、与 MCP 生态一致 |
| L1 前端 | React 18 + Vite + Recharts | 轻量、图表库成熟、Vite 快速开发 |
| L4 质量 | pytest + httpx TestClient + React Testing Library（可选） | TDD 强制：先写测试后实现 |

### 2.2 目录结构

```
bottlesumo_pi/governance/dashboard/
├── specification.md            # 本文档
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI 入口 + CORS + 路由挂载
│   │   ├── database.py         # engine/session 工厂（DATABASE_URL 切换）
│   │   ├── models.py           # SQLAlchemy 声明式模型
│   │   ├── schemas.py          # Pydantic 响应模型
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── health.py       # GET /api/health
│   │       ├── usage.py        # GET /api/usage/summary, /api/usage/latency, /api/usage/timeline
│   │       └── hypotheses.py   # GET /api/hypotheses/summary, /api/hypotheses/trend
│   ├── seed.py                 # ETL: jsonl -> DB
│   └── tests/
│       ├── __init__.py
│       ├── test_seed.py
│       └── test_api.py
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── HealthCards.jsx
│           ├── LatencyTable.jsx
│           ├── UsageTimeline.jsx
│           └── HypothesisPanel.jsx
└── deployment/
    └── docker-compose.yml      # 生产形态: postgres + backend + frontend(nginx)
```

### 2.3 API 接口定义

```
GET /api/health                     -> { servers: [{name, calls, ok, error, success_rate, avg_ms, p95_ms, last_status, last_ts}] }
GET /api/usage/summary              -> { total_calls, ok, error, success_rate, avg_ms, p95_ms, min_ms, max_ms, by_tool: [{tool, calls, avg_ms, p95_ms, error}] }
GET /api/usage/latency?threshold=2000 -> { outliers: [{ts, server, tool, duration_ms, status}] }
GET /api/usage/timeline?bucket=day  -> { buckets: [{bucket, calls, errors}] }
GET /api/hypotheses/summary         -> { variants: [{variant_id, attempts, hits, confidence}] }
GET /api/hypotheses/trend           -> { trend: [{variant_id, ts, cumulative_hits, cumulative_attempts}] }
```

---

## 3. 数据模型（Schema 设计）

### 3.1 实体关系

```
mcp_usage (usage 表)                    hypotheses (hypotheses 表)
+------------------+                    +----------------------+
| id (PK)          |                    | id (PK)              |
| ts (DATETIME,idx)|                    | ts (DATETIME, idx)   |
| server (VARCHAR) |                    | variant_id (VARCHAR) |
| tool (VARCHAR)   |                    | layer (VARCHAR)      |
| args (TEXT)      |                    | hypothesis (TEXT)    |
| duration_ms (FLOAT)|                  | outcome (VARCHAR)    |
| status (VARCHAR) |                    | score (FLOAT)        |
| error (TEXT NULL)|                    | confidence (FLOAT)   |
+------------------+                    +----------------------+
```

### 3.2 DDL（方言兼容写法）

```sql
CREATE TABLE IF NOT EXISTS mcp_usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,      -- PG: BIGSERIAL
    ts          TIMESTAMP NOT NULL,                    -- PG: TIMESTAMPTZ
    server      VARCHAR(64) NOT NULL,
    tool        VARCHAR(128) NOT NULL,
    args        TEXT,
    duration_ms FLOAT NOT NULL,
    status      VARCHAR(16) NOT NULL,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON mcp_usage (ts);
CREATE INDEX IF NOT EXISTS idx_usage_server ON mcp_usage (server);

CREATE TABLE IF NOT EXISTS hypotheses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TIMESTAMP NOT NULL,
    variant_id  VARCHAR(64) NOT NULL,
    layer       VARCHAR(32),
    hypothesis  TEXT,
    outcome     VARCHAR(16),
    score       FLOAT,
    confidence  FLOAT
);
CREATE INDEX IF NOT EXISTS idx_hyp_ts ON hypotheses (ts);
CREATE INDEX IF NOT EXISTS idx_hyp_variant ON hypotheses (variant_id);
```

---

## 4. 测试规格（TDD 测试先行）

### 4.1 后端单元/集成测试（pytest + httpx TestClient）

| ID | 测试 | 断言 |
| :--- | :--- | :--- |
| T-01 | `test_seed_loads_usage_rows` | seed 后 mcp_usage 表行数 == 52（jsonl 行数） |
| T-02 | `test_seed_loads_hypothesis_rows` | seed 后 hypotheses 表行数 == 43 |
| T-03 | `test_health_returns_three_servers` | GET /api/health → 3 个 server，字段完整 |
| T-04 | `test_health_success_rate` | meta_cognition_server 成功率 == 25/25 = 1.0；semantic_retrieval_server == 12/13 |
| T-05 | `test_usage_summary_p95` | /api/usage/summary → p95_ms >= max 中除极端值外的合理值（验证聚合正确） |
| T-06 | `test_usage_summary_by_tool` | by_tool 含 hypothesis_stats(13)、semantic_search(12)、environment_snapshot(12) |
| T-07 | `test_usage_latency_outliers` | /api/usage/latency?threshold=2000 → 含 duration_ms > 2000 的调用；含 nonexistent_tool 错误记录 |
| T-08 | `test_hypotheses_summary_aggregation` | ca_rules_01 → attempts=39, confidence≈0.7~0.9（按 F-110 聚合语义） |
| T-09 | `test_hypotheses_trend_order` | trend 按 ts 升序，cumulative_attempts 单调不减 |
| T-10 | `test_api_error_handling` | 未知路由 → 404 JSON；`/api/usage/timeline?bucket=invalid` → 400/422 |

### 4.2 前端测试（可选，若环境允许）

| ID | 测试 | 断言 |
| :--- | :--- | :--- |
| F-01 | HealthCards 渲染 3 个服务器卡片 | 挂载后含 3 个卡片元素 |
| F-02 | HypothesisPanel 显示 variant 聚合 | 含 ca_rules_01 文本 |

### 4.3 静态分析

- `python -m compileall` 无语法错误
- ruff/flake8 无致命错误（若可用）

---

## 5. 部署形态（Phase D 预告）

1. **开发验证**：uvicorn backend.app.main:app --port 8010；前端 vite dev server 代理 /api
2. **生产形态**（docker-compose.yml，deployment/ 下）：
   - postgres:14-alpine（环境可用时）
   - backend: uvicorn + DATABASE_URL=postgresql://... 
   - frontend: vite build → nginx 静态托管 + /api 反代
3. **数据更新**：seed.py 可重复执行（INSERT OR IGNORE 按 ts+server+tool 去重或 TRUNCATE 重灌）

---

## 6. 验收标准汇总（Phase E 检查点）

- [ ] 后端 10 个测试全绿（T-01..T-10）
- [ ] seed 后 DB 行数精确匹配（52 usage / 43 hypotheses）
- [ ] API 全部 6 个端点可访问且返回合法 JSON
- [ ] 前端构建成功且核心组件渲染（HealthCards / LatencyTable / UsageTimeline / HypothesisPanel）
- [ ] 双端现有回归不受影响（Windows 57/57，WSL mujoco 73/73）
