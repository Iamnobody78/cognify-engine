# MCP Governance Dashboard

BottleSumo Meta-Harness 治理监控仪表板 —— 将 `mcp_usage_report.jsonl`（52 条）与
`hypotheses.jsonl`（43 条）转化为可交互的全栈可视化（SEED-ROUND-1 交付物）。

## 技术栈

| 层 | 技术 |
| :--- | :--- |
| L3 数据库 | SQLAlchemy 2.0 ORM + SQLite（开发）/ PostgreSQL（生产，`DATABASE_URL` 切换） |
| L2 后端 | FastAPI + uvicorn（端口 8010），pydantic v2 |
| L1 前端 | React 18 + Vite + Recharts（端口 5173 dev / 80 容器） |
| L4 质量 | pytest + httpx TestClient（13 测试全绿） |

## 快速开始（开发模式）

```powershell
# 1. 数据装载（幂等重灌）
cd backend
python seed.py
# -> [seed] usage=52 hypotheses=43 OK

# 2. 启动后端
python -m uvicorn app.main:app --port 8010

# 3. 启动前端（另一终端）
cd frontend
npm install
npm run dev
# -> http://localhost:5173 （/api 自动代理到 8010）
```

## API 端点

| 端点 | 说明 |
| :--- | :--- |
| `GET /api/health` | 三服务器健康聚合（calls/ok/error/rate/avg/p95） |
| `GET /api/usage/summary` | 全量统计 + 按工具分组 |
| `GET /api/usage/latency?threshold=2000` | 慢调用/失败调用清单 |
| `GET /api/usage/timeline?bucket=day\|hour` | 调用量时间线 |
| `GET /api/hypotheses/summary` | 按 variant_id 聚合（F-110 语义：attempts/hits/confidence） |
| `GET /api/hypotheses/trend` | 累计命中趋势 |

交互式文档：`http://localhost:8010/docs`

## 测试

```powershell
cd backend
python -m pytest tests/ -q
# 13 passed
```

## 生产部署（PostgreSQL）

```bash
docker compose -f deployment/docker-compose.yml up -d --build
# postgres:5432 + backend:8010 + frontend:80(5173)
```

## 目录

```
backend/        FastAPI + SQLAlchemy + seed ETL + 13 测试
frontend/       React + Vite + Recharts 仪表板
deployment/     docker-compose 生产形态
specification.md  SEED-ROUND-1 Phase S 规格
learning_report.md Phase D 学习报告（RULE-FS-001..005）
```

## 验证记录

- 双端回归不受影响：Windows 57/57，WSL mujoco 73/73
- 聚合正确性交叉校验：ca_rules_01 39 尝试/39 命中（与 _verify_f110.py 一致）
- 1 次失败调用（nonexistent_tool）在 health/latency 正确反映
